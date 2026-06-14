"""Spectrum previewer contract tests (SC-004, SC-006).

Drives the package spectrum provider against a real bounded
``PreviewDataAccess`` reading an on-disk parquet payload, asserting:

- exact ``Spectrum`` refs route to the spectrum previewer (SC-004);
- the envelope is a SERIES envelope carrying true (x, y) points;
- export/save controls exist for the figure and the visible data (SC-006);
- honest sampling metadata flags are present and boolean;
- a bad input yields an error envelope rather than crashing.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pyarrow as pa
import pyarrow.parquet as pq
from scistudio_blocks_spectroscopy.previewers import (
    SPECTRUM_PREVIEWER_ID,
    get_previewers,
)
from scistudio_blocks_spectroscopy.previewers.providers import spectrum_provider

from scistudio.previewers.data_access import PreviewDataAccess
from scistudio.previewers.models import (
    EnvelopeKind,
    OwnerKind,
    PreviewerSpec,
    PreviewLimits,
    PreviewRequest,
    PreviewTarget,
    TargetKind,
)

_SPECTRUM_CHAIN = ("DataObject", "Series", "Spectrum")


def _spec() -> PreviewerSpec:
    for spec in get_previewers():
        if spec.previewer_id == SPECTRUM_PREVIEWER_ID:
            return cast(PreviewerSpec, spec)
    raise AssertionError(SPECTRUM_PREVIEWER_ID)


def _request(path: Path, record_md: dict | None = None) -> PreviewRequest:
    query: dict = {"_storage": {"backend": "filesystem", "path": str(path), "format": "parquet"}}
    if record_md is not None:
        query["_record_metadata"] = record_md
    return PreviewRequest(
        target=PreviewTarget(
            kind=TargetKind.DATA_REF, ref=str(path), recorded_type="Spectrum", type_chain=_SPECTRUM_CHAIN
        ),
        spec=_spec(),
        query=query,
        data_access=PreviewDataAccess(),
        limits=PreviewLimits(),
        session_id=None,
    )


def _parquet(path: Path, columns: dict) -> Path:
    pq.write_table(pa.table(columns), path)
    return path


def test_spectrum_previewer_is_package_owned() -> None:
    """SC-004: the spectrum previewer is a PACKAGE-owned spec for ``Spectrum``."""
    spec = _spec()
    assert spec.owner_kind is OwnerKind.PACKAGE
    assert spec.owner_name == "scistudio-blocks-spectroscopy"
    assert spec.target_type == "Spectrum"
    assert spec.supports_collection is False


def test_spectrum_provider_builds_series_envelope_with_points(tmp_path: Path) -> None:
    path = _parquet(
        tmp_path / "spectrum.parquet",
        {"lambda": [400.0, 401.0, 402.0], "intensity": [0.1, 0.5, 0.3]},
    )
    env = spectrum_provider(_request(path, record_md={"lambda_unit": "nm", "intensity_unit": "a.u."}))
    assert env.previewer_id == SPECTRUM_PREVIEWER_ID
    assert env.kind is EnvelopeKind.SERIES
    assert env.error is None
    assert env.payload["points"] == [
        {"x": 400.0, "y": 0.1},
        {"x": 401.0, "y": 0.5},
        {"x": 402.0, "y": 0.3},
    ]
    assert env.payload["total"] == 3
    assert env.payload["axes"]["x"]["unit"] == "nm"


def test_spectrum_previewer_export_controls_exist(tmp_path: Path) -> None:
    """SC-006: export/save controls for figures and visible data."""
    path = _parquet(tmp_path / "s.parquet", {"lambda": [1.0, 2.0], "intensity": [3.0, 4.0]})
    env = spectrum_provider(_request(path, record_md={"lambda_unit": "nm", "intensity_unit": "au"}))
    resource_ids = {r.resource_id for r in env.resources}
    # Figure export (vector + raster) and visible-data export.
    assert {"export_figure_svg", "export_figure_png", "export_figure_pdf", "export_points_csv"} <= resource_ids


def test_spectrum_previewer_metadata_flags_are_honest(tmp_path: Path) -> None:
    path = _parquet(tmp_path / "s.parquet", {"lambda": [1.0, 2.0], "intensity": [3.0, 4.0]})
    env = spectrum_provider(_request(path, record_md={"lambda_unit": "nm", "intensity_unit": "au"}))
    flags = env.metadata.to_dict()
    for name in ("sampled", "truncated", "complete", "failed"):
        assert name in flags and isinstance(flags[name], bool)
    # A small fully-read spectrum is complete and not failed.
    assert env.metadata.complete is True
    assert env.metadata.failed is False


def test_spectrum_provider_error_envelope_on_missing_file() -> None:
    env = spectrum_provider(_request(Path("/does/not/exist.parquet"), record_md={}))
    assert env.kind is EnvelopeKind.ERROR
    assert env.metadata.failed is True
    assert env.metadata.complete is False
    assert env.error is not None
