"""Foundation type + support-helper tests (skeleton-safe).

Type contracts cover SC-001..SC-003 and SC-007 of
``docs/specs/spectroscopy-package.md``: exactly two package types; ``Spectrum``
subclasses core ``Series`` with the canonical axis names and the FR-005/FR-006
``Meta`` fields; ``SpectralDataset`` subclasses ``CompositeData`` with exactly
the ``index`` + ``spectra`` slots and its FR-013 dataset ``Meta`` fields; and no
package code imports the legacy ``scistudio_blocks_srs`` package.
"""

from __future__ import annotations

import sys

import numpy as np
import pyarrow as pa
import pytest
from scistudio_blocks_spectroscopy import _support
from scistudio_blocks_spectroscopy.types import SpectralDataset, Spectrum

from scistudio.blocks.base.block import Block
from scistudio.core.storage.flush_context import clear, get_output_dir, set_output_dir
from scistudio.core.types.composite import CompositeData
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.registry import TypeRegistry
from scistudio.core.types.serialization import _reconstruct_one, _serialise_one
from scistudio.core.types.series import Series


def test_spectrum_is_series_with_canonical_names() -> None:
    spec = Spectrum()
    assert isinstance(spec, Series)
    # SC-002: Spectrum is a Series, NOT an Array (no axes/shape/dtype surface).
    assert not hasattr(spec, "axes")
    assert not hasattr(spec, "shape")
    assert spec.index_name == "lambda"
    assert spec.value_name == "intensity"


def test_spectrum_meta_required_fields_exist() -> None:
    fields = set(Spectrum.Meta.model_fields)
    # FR-005 (units) + FR-006 (lambda_kind / modality) — must exist, nullable.
    assert {"lambda_unit", "intensity_unit", "lambda_kind", "modality"}.issubset(fields)


def test_spectrum_meta_unit_fields_nullable_and_settable() -> None:
    # SC-002: the unit metadata is exposed (settable + readable).
    meta = Spectrum.Meta()
    assert meta.lambda_unit is None and meta.intensity_unit is None
    populated = Spectrum.Meta(lambda_unit="nm", intensity_unit="a.u.")
    assert populated.lambda_unit == "nm"
    assert populated.intensity_unit == "a.u."


def test_spectral_dataset_two_slots() -> None:
    assert issubclass(SpectralDataset, CompositeData)
    # SC-001 / SC-003 / FR-008: exactly the two semantic slots, both DataFrame.
    assert SpectralDataset.expected_slots == {"index": DataFrame, "spectra": DataFrame}


def test_spectral_dataset_slot_type_is_enforced() -> None:
    # FR-008 / SC-003: slots are isinstance-checked against expected_slots.
    spectra = _support.dataframe_from_rows([{"spectrum_id": "a", "lambda": 1.0, "intensity": 2.0}])
    index = _support.dataframe_from_rows([{"spectrum_id": "a"}])
    dataset = _support.build_spectral_dataset(index, spectra)
    assert set(dataset.slot_names) == {"index", "spectra"}
    assert isinstance(dataset.get("index"), DataFrame)
    assert isinstance(dataset.get("spectra"), DataFrame)


def test_spectral_dataset_requires_exact_slots_at_construction() -> None:
    # FR-008 / SC-003: empty, partial, or extra slots are invalid datasets.
    spectra = _support.dataframe_from_rows([{"spectrum_id": "a", "lambda": 1.0, "intensity": 2.0}])
    index = _support.dataframe_from_rows([{"spectrum_id": "a"}])
    extra = _support.dataframe_from_rows([{"spectrum_id": "a"}])

    bad_slots = [
        None,
        {},
        {"index": index},
        {"spectra": spectra},
        {"index": index, "spectra": spectra, "metadata": extra},
    ]
    for slots in bad_slots:
        with pytest.raises(ValueError, match="exactly slots"):
            SpectralDataset(slots=slots)


@pytest.mark.parametrize(
    ("index_rows", "spectra_rows", "match"),
    [
        ([{"label": "a"}], [{"spectrum_id": "a", "lambda": 1.0, "intensity": 2.0}], "index table"),
        ([{"spectrum_id": "a"}], [{"spectrum_id": "a", "lambda": 1.0}], "missing"),
        (
            [{"spectrum_id": "a"}, {"spectrum_id": "a"}],
            [{"spectrum_id": "a", "lambda": 1.0, "intensity": 2.0}],
            "unique",
        ),
        ([{"spectrum_id": "a"}], [{"spectrum_id": "ghost", "lambda": 1.0, "intensity": 2.0}], "unknown"),
        (
            [{"spectrum_id": "a"}, {"spectrum_id": "b"}],
            [{"spectrum_id": "a", "lambda": 1.0, "intensity": 2.0}],
            "coverage",
        ),
        ([{"spectrum_id": "a"}], [{"spectrum_id": "a", "lambda": "bad", "intensity": 2.0}], "numeric"),
    ],
)
def test_spectral_dataset_validates_required_columns_and_join(
    index_rows: list[dict], spectra_rows: list[dict], match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        _support.build_spectral_dataset(
            _support.dataframe_from_rows(index_rows),
            _support.dataframe_from_rows(spectra_rows),
        )


def test_no_srs_import_anywhere_in_package() -> None:
    """SC-007: importing the package never pulls in ``scistudio_blocks_srs``."""
    import scistudio_blocks_spectroscopy  # noqa: F401  (ensure full import graph)

    assert "scistudio_blocks_srs" not in sys.modules


def test_spectral_dataset_meta_fields_exist() -> None:
    fields = set(SpectralDataset.Meta.model_fields)
    assert {
        "dataset_name",
        "dataset_role",
        "lambda_unit",
        "intensity_unit",
        "modality",
        "schema_version",
    }.issubset(fields)


def test_build_and_read_spectrum_roundtrip() -> None:
    spec = _support.build_spectrum([1.0, 2.0, 3.0], [10.0, 20.0, 30.0])
    lam, inten = _support.spectrum_arrays(spec)
    assert np.allclose(lam, [1.0, 2.0, 3.0])
    assert np.allclose(inten, [10.0, 20.0, 30.0])
    assert spec.length == 3


def test_spectrum_auto_flush_round_trips_arrow_payload(tmp_path) -> None:
    import scistudio.core.types.serialization as serialization_module

    spec = _support.build_spectrum([1.0, 2.0, 3.0], [10.0, 20.0, 30.0])

    previous_output_dir = get_output_dir()
    set_output_dir(str(tmp_path))
    try:
        flushed = Block._auto_flush(spec)
    finally:
        clear()
        if previous_output_dir is not None:
            set_output_dir(previous_output_dir)

    assert flushed is spec
    assert spec.storage_ref is not None
    assert spec.storage_ref.backend == "arrow"
    assert spec.storage_ref.format == "parquet"
    assert spec.storage_ref.path.endswith(".parquet")
    assert isinstance(_support.spectrum_table(spec), pa.Table)

    registry = TypeRegistry()
    registry.scan_builtins()
    registry.register_class(Spectrum)
    previous_registry = serialization_module._registry_instance
    serialization_module._registry_instance = registry
    try:
        restored = _reconstruct_one(_serialise_one(spec))
    finally:
        serialization_module._registry_instance = previous_registry

    assert isinstance(restored, Spectrum)
    assert restored.storage_ref is not None
    assert restored.storage_ref.backend == "arrow"
    lam, inten = _support.spectrum_arrays(restored)
    np.testing.assert_allclose(lam, [1.0, 2.0, 3.0])
    np.testing.assert_allclose(inten, [10.0, 20.0, 30.0])


def test_derive_spectrum_replaces_intensity_keeps_grid() -> None:
    spec = _support.build_spectrum([1.0, 2.0], [5.0, 6.0])
    derived = _support.derive_spectrum(spec, intensity_values=[7.0, 8.0])
    lam, inten = _support.spectrum_arrays(derived)
    assert np.allclose(lam, [1.0, 2.0])
    assert np.allclose(inten, [7.0, 8.0])


def test_spectra_collection_handles_empty() -> None:
    empty = _support.spectra_collection([])
    assert empty.item_type is Spectrum
    assert len(empty) == 0


def test_dataframe_collection_wraps_single_table() -> None:
    df = _support.dataframe_from_rows([{"spectrum_id": "a", "auc": 1.0}])
    coll = _support.dataframe_collection(df)
    assert coll.item_type is DataFrame
    assert len(coll) == 1
