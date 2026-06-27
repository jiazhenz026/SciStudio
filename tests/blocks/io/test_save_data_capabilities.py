"""Tests for :attr:`SaveData.format_capabilities` (ADR-043 / spec FR-002).

These tests pin the explicit ``FormatCapability`` declarations on
:class:`scistudio.blocks.io.savers.save_data.SaveData` introduced in the
ADR-043 in-tree-core-IO migration (spec ``adr-043-package-migration``
Phase A1, T-002 / T-005 / FR-016). They cover:

* capability count, IDs, defaults, metadata fidelity per declared
  ``(data_type, format_id)`` pair (FR-016);
* roundtrip group pairing with :attr:`LoadData.format_capabilities`
  (FR-015);
* registry resolution via :meth:`BlockRegistry.find_saver_capability`
  returning the explicit (non-synthesized) record for each declared
  extension;
* ambiguity error when two SaveData-like blocks declare the same
  ``(data_type, extension)`` pair;
* pickle gating still works at runtime (``allow_pickle=True``
  required for ``.pkl``);
* backward-compat round-trip parity: existing single-path
  DataFrame+CSV / Array+npy / Text+md flows still work.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, ClassVar

import numpy as np
import pyarrow as pa
import pytest

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort
from scistudio.blocks.io.capabilities import FormatCapability, MetadataFidelity
from scistudio.blocks.io.io_block import IOBlock
from scistudio.blocks.io.loaders.load_data import LoadData
from scistudio.blocks.io.savers.save_data import (
    _SAVE_CAPABILITIES,
    _SAVE_EXTENSION_MAP,
    SaveData,
    _supported_save_extensions,
)
from scistudio.blocks.registry import (
    AmbiguousCapabilityError,
    BlockRegistry,
    MissingCapabilityError,
    _spec_from_class,
)
from scistudio.core.types.array import Array
from scistudio.core.types.artifact import Artifact
from scistudio.core.types.base import DataObject
from scistudio.core.types.composite import CompositeData
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.series import Series
from scistudio.core.types.text import Text

# ---------------------------------------------------------------------------
# Declaration-shape tests (FR-002 + FR-015 + FR-016).
# ---------------------------------------------------------------------------


class TestSaveDataFormatCapabilitiesShape:
    """:attr:`SaveData.format_capabilities` MUST be an explicit
    ``ClassVar[tuple[FormatCapability, ...]]`` (no synthesis fallback)
    covering every legacy ``(core_type, format_id)`` pair on the save
    side."""

    def test_format_capabilities_classvar_is_a_tuple_of_format_capability(self) -> None:
        assert isinstance(SaveData.format_capabilities, tuple)
        assert len(SaveData.format_capabilities) > 0
        for capability in SaveData.format_capabilities:
            assert isinstance(capability, FormatCapability)

    def test_format_capabilities_identity_matches_module_constant(self) -> None:
        assert SaveData.format_capabilities is _SAVE_CAPABILITIES

    def test_no_capability_is_synthesized(self) -> None:
        """FR-002: every record MUST have ``is_synthesized=False``."""
        for capability in SaveData.format_capabilities:
            assert capability.is_synthesized is False, (
                f"capability {capability.id!r} must be explicit (is_synthesized=False) per ADR-043 FR-002"
            )

    def test_all_directions_are_save(self) -> None:
        for capability in SaveData.format_capabilities:
            assert capability.direction == "save"

    def test_all_block_types_are_save_data(self) -> None:
        for capability in SaveData.format_capabilities:
            assert capability.block_type == "SaveData"

    def test_capability_ids_follow_fr015_naming_convention(self) -> None:
        """FR-015: capability id MUST be ``core.{lower(type)}.{format_id}.save``."""
        type_name_lookup = {
            Array: "array",
            DataFrame: "dataframe",
            Series: "series",
            Text: "text",
            Artifact: "artifact",
            CompositeData: "compositedata",
        }
        for capability in SaveData.format_capabilities:
            type_token = type_name_lookup[capability.data_type]
            expected = f"core.{type_token}.{capability.format_id}.save"
            assert capability.id == expected, (
                f"capability id {capability.id!r} must match FR-015 convention {expected!r}"
            )

    def test_every_capability_has_unique_id(self) -> None:
        ids = [capability.id for capability in SaveData.format_capabilities]
        duplicates = [identifier for identifier, count in Counter(ids).items() if count > 1]
        assert not duplicates, f"duplicate capability ids: {duplicates}"

    def test_one_capability_per_type_format_pair(self) -> None:
        """FR-016: capability count MUST be one record per ``(type, format_id)`` pair."""
        keys = [(capability.data_type, capability.format_id) for capability in SaveData.format_capabilities]
        duplicates = [key for key, count in Counter(keys).items() if count > 1]
        assert not duplicates, f"duplicate (data_type, format_id) pairs: {duplicates}; FR-016 requires one per pair"

    def test_no_capability_claims_default(self) -> None:
        """FR-002 cross-package collision rule: core IO capabilities are
        declared ``is_default=False`` so installed package-specific
        savers (e.g. ``scistudio-blocks-lcms.table.csv.save`` for
        ``(DataFrame, .csv)``) keep ownership of the default slot
        without triggering a registration-time
        :class:`CapabilityRegistrationError`. When no package declares a
        default for a given ``(data_type, extension)`` slot, the
        registry returns the unique non-default core capability via
        :meth:`BlockRegistry.find_saver_capability`."""
        for capability in SaveData.format_capabilities:
            assert capability.is_default is False, (
                f"capability {capability.id!r} must be is_default=False "
                "to avoid cross-package default-slot conflicts (per A1 CI run "
                "and ADR-043 §8 cross-package collision rule)"
            )

    def test_metadata_fidelity_is_pixel_only(self) -> None:
        """FR-002: every record's ``metadata_fidelity.level`` MUST be ``pixel_only``."""
        for capability in SaveData.format_capabilities:
            assert capability.metadata_fidelity.level == "pixel_only", (
                f"capability {capability.id!r} must have pixel_only fidelity"
            )

    def test_pickle_capabilities_carry_allow_pickle_note(self) -> None:
        """Spec: pickle records carry ``notes='requires allow_pickle=True'``."""
        pickle_capabilities = [c for c in SaveData.format_capabilities if c.format_id == "pickle"]
        assert pickle_capabilities, "expected at least one pickle capability"
        for capability in pickle_capabilities:
            note = capability.metadata_fidelity.notes
            assert note is not None and "allow_pickle" in note, (
                f"pickle capability {capability.id!r} must declare allow_pickle note, got {note!r}"
            )

    def test_roundtrip_group_uses_fr015_convention(self) -> None:
        type_name_lookup = {
            Array: "array",
            DataFrame: "dataframe",
            Series: "series",
            Text: "text",
            Artifact: "artifact",
            CompositeData: "compositedata",
        }
        for capability in SaveData.format_capabilities:
            type_token = type_name_lookup[capability.data_type]
            expected_group = f"core.{type_token}.{capability.format_id}"
            assert capability.roundtrip_group == expected_group, (
                f"capability {capability.id!r} roundtrip_group {capability.roundtrip_group!r} "
                f"must equal {expected_group!r}"
            )

    def test_extension_map_derives_legacy_set(self) -> None:
        """The capability-derived extension map covers the legacy
        ``supported_extensions`` union for all six core types."""
        legacy_union = {
            ".npy",
            ".npz",
            ".zarr",
            ".parquet",
            ".pq",
            ".pkl",
            ".pickle",
            ".csv",
            ".tsv",
            ".json",
            ".txt",
            ".log",
            ".md",
            ".html",
            ".xml",
            ".yaml",
            ".yml",
            ".toml",
        }
        for extension in legacy_union:
            assert extension in _SAVE_EXTENSION_MAP, (
                f"legacy extension {extension!r} missing from capability-derived map"
            )

    def test_supported_save_extensions_helper_is_sorted_tuple(self) -> None:
        result = _supported_save_extensions()
        assert isinstance(result, tuple)
        assert list(result) == sorted(result)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# Per-type coverage assertions (FR-002: all six core types x supported extensions).
# ---------------------------------------------------------------------------


class TestSaveDataPerTypeCapabilityCoverage:
    """FR-002: explicit ``format_capabilities`` MUST mirror FR-001 on
    the save side (one record per legacy supported pair)."""

    @pytest.mark.parametrize(
        ("data_type", "expected_format_ids"),
        [
            (Array, {"npy", "npz", "zarr", "parquet", "pickle"}),
            (DataFrame, {"csv", "tsv", "parquet", "json", "xlsx", "pickle"}),
            # Note: SaveData supports Series json (legacy code branch in
            # _save_series). LoadData does not — this asymmetry is
            # pre-existing and intentional.
            (Series, {"csv", "tsv", "parquet", "json", "xlsx", "pickle"}),
            # Text + .json is a legacy save-only extension declared as a
            # separate Text capability with format_id="json" (Codex P1 on
            # PR #1300); LoadData's Text capability still excludes .json
            # because _load_text doesn't parse JSON.
            (Text, {"text", "json"}),
            (CompositeData, {"json"}),
        ],
    )
    def test_per_type_format_id_coverage(
        self,
        data_type: type[DataObject],
        expected_format_ids: set[str],
    ) -> None:
        actual = {c.format_id for c in SaveData.format_capabilities if c.data_type is data_type}
        assert actual == expected_format_ids, (
            f"{data_type.__name__}: expected format_ids {expected_format_ids}, got {actual}"
        )

    def test_artifact_has_canonical_format_ids(self) -> None:
        """Artifact is a catch-all opaque saver at runtime; the explicit
        capability set lists (a) the canonical MIME-mapped subset
        (binary, pdf, png, jpeg, tiff) AND (b) the opaque variants for
        the legacy supported-extension union so the AppBlock wildcard-port
        flow (mapped to ``target_type=Artifact``) keeps resolving a
        saver. Mirror of the LoadData side."""
        actual = {c.format_id for c in SaveData.format_capabilities if c.data_type is Artifact}
        # MIME-mapped subset.
        assert actual >= {"binary", "pdf", "png", "jpeg", "tiff"}
        # Opaque-saver variants for the typed-core extension union.
        assert actual >= {"csv", "tsv", "json", "parquet", "npy", "npz", "zarr", "text", "pickle"}


# ---------------------------------------------------------------------------
# Roundtrip pairing with LoadData (FR-015).
# ---------------------------------------------------------------------------


class TestSaveLoadRoundtripPairing:
    """Each save capability MUST share its ``roundtrip_group`` with the
    matching load capability so the registry can pair them for
    ADR-043 metadata-fidelity reasoning."""

    def test_every_save_pairs_with_a_load_via_roundtrip_group(self) -> None:
        """Every save capability's roundtrip group MUST have at least one
        matching load capability (modulo legacy save-only edge cases like
        ``core.series.json`` / ``core.text.json`` where the load side
        never implemented JSON)."""
        load_groups = {c.roundtrip_group for c in LoadData.format_capabilities}
        save_groups = {c.roundtrip_group for c in SaveData.format_capabilities}
        # Save-only legacy edge cases:
        # - SaveData supports Series JSON via ``_save_series``'s json
        #   branch, but LoadData has never implemented JSON for Series.
        # - SaveData supports Text JSON via ``_save_text`` (just writes
        #   obj.content to .json); LoadData's Text capability excludes
        #   .json because _load_text doesn't parse JSON (Codex P1 on PR
        #   #1300).
        save_only_legacy = {"core.series.json", "core.text.json"}
        unpaired = save_groups - load_groups - save_only_legacy
        assert not unpaired, f"save capabilities without a matching load roundtrip_group: {unpaired}"

    def test_paired_load_and_save_share_format_id(self) -> None:
        load_by_group = {c.roundtrip_group: c for c in LoadData.format_capabilities}
        for save_capability in SaveData.format_capabilities:
            load = load_by_group.get(save_capability.roundtrip_group)
            if load is None:
                continue  # save-only legacy edge case
            assert load.format_id == save_capability.format_id


# ---------------------------------------------------------------------------
# BlockRegistry round-trip via find_saver_capability (FR-016).
# ---------------------------------------------------------------------------


def _registry_with_save_data() -> BlockRegistry:
    """Build a BlockRegistry containing just :class:`SaveData`."""
    registry = BlockRegistry()
    registry._register_spec(_spec_from_class(SaveData, source="test"))
    return registry


class TestRegistryFindSaverCapability:
    """:meth:`BlockRegistry.find_saver_capability` MUST return the
    explicit (non-synthesized) SaveData record for each declared
    extension across the six core types."""

    @pytest.mark.parametrize(
        ("data_type", "extension", "expected_format_id"),
        [
            (Array, ".npy", "npy"),
            (Array, ".npz", "npz"),
            (Array, ".zarr", "zarr"),
            (Array, ".parquet", "parquet"),
            (Array, ".pq", "parquet"),
            (Array, ".pkl", "pickle"),
            (DataFrame, ".csv", "csv"),
            (DataFrame, ".tsv", "tsv"),
            (DataFrame, ".parquet", "parquet"),
            (DataFrame, ".json", "json"),
            (Series, ".csv", "csv"),
            (Series, ".parquet", "parquet"),
            (Series, ".json", "json"),
            (Text, ".txt", "text"),
            (Text, ".md", "text"),
            (Text, ".yaml", "text"),
            (CompositeData, ".json", "json"),
            (Artifact, ".bin", "binary"),
            (Artifact, ".png", "png"),
            (Artifact, ".jpeg", "jpeg"),
        ],
    )
    def test_find_saver_capability_returns_explicit_record(
        self,
        data_type: type[DataObject],
        extension: str,
        expected_format_id: str,
    ) -> None:
        registry = _registry_with_save_data()
        capability = registry.find_saver_capability(data_type, extension)
        assert capability.is_synthesized is False, (
            f"expected explicit (non-synthesized) capability for {data_type.__name__} {extension}, "
            f"got synthesized {capability.id!r}"
        )
        assert capability.format_id == expected_format_id
        assert capability.block_type == "SaveData"

    def test_unknown_extension_raises_missing(self) -> None:
        registry = _registry_with_save_data()
        with pytest.raises(MissingCapabilityError):
            registry.find_saver_capability(DataFrame, ".unknown_ext")


# ---------------------------------------------------------------------------
# Ambiguity test (FR-016: ambiguity error for type+extension matching multiple).
# ---------------------------------------------------------------------------


class TestRegistryAmbiguityForMultipleCapabilities:
    """FR-016: when two save blocks declare the same ``(direction,
    data_type, extension)`` and only one is default, the default wins.
    Two non-default candidates at the same slot trigger
    :class:`AmbiguousCapabilityError` at lookup time."""

    def test_default_alternate_wins_over_non_default_core(self) -> None:
        """SaveData's ``core.dataframe.csv.save`` is ``is_default=False``
        (cross-package collision rule per A1 CI run). When a third-party
        block declares the same slot with ``is_default=True``, the
        default declaration wins. This mirrors the LCMS pilot pattern
        where ``scistudio-blocks-lcms.table.csv.save`` claims default
        ownership of ``(DataFrame, .csv)`` and SaveData yields."""

        class _AltDataFrameSaver(IOBlock):
            direction: ClassVar[str] = "output"
            type_name: ClassVar[str] = "alt_dataframe_saver"
            name: ClassVar[str] = "Alt DataFrame Saver"
            input_ports: ClassVar[list[InputPort]] = [
                InputPort(name="data", accepted_types=[DataFrame], required=True),
            ]
            output_ports: ClassVar[list[Any]] = []
            format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
                FormatCapability(
                    id="alt.dataframe.csv.save",
                    direction="save",
                    data_type=DataFrame,
                    format_id="csv",
                    extensions=(".csv",),
                    label="Alt CSV saver",
                    block_type="_AltDataFrameSaver",
                    handler="save",
                    is_default=True,
                    metadata_fidelity=MetadataFidelity(level="pixel_only"),
                    is_synthesized=False,
                ),
            )

            def load(self, config: BlockConfig, output_dir: str = "") -> DataObject:
                raise NotImplementedError

            def save(self, obj: Any, config: BlockConfig) -> None:
                raise NotImplementedError

        registry = BlockRegistry()
        registry._register_spec(_spec_from_class(SaveData, source="test"))
        registry._register_spec(_spec_from_class(_AltDataFrameSaver, source="test"))
        capability = registry.find_saver_capability(DataFrame, ".csv")
        assert capability.block_type == "_AltDataFrameSaver"

    def test_two_non_default_capabilities_for_same_slot_raise_ambiguous_lookup(self) -> None:
        """Two ``is_default=False`` capabilities for the same slot trigger
        ambiguity at lookup time (registration-time validation rejects
        two ``is_default=True`` candidates earlier)."""

        class _NonDefaultSaverA(IOBlock):
            direction: ClassVar[str] = "output"
            type_name: ClassVar[str] = "non_default_saver_a"
            name: ClassVar[str] = "Non-default Saver A"
            input_ports: ClassVar[list[InputPort]] = [
                InputPort(name="data", accepted_types=[DataFrame], required=True),
            ]
            output_ports: ClassVar[list[Any]] = []
            format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
                FormatCapability(
                    id="ambiguity.a.dataframe.xyz.save",
                    direction="save",
                    data_type=DataFrame,
                    format_id="xyz",
                    extensions=(".xyz",),
                    label="Ambiguity-A xyz saver",
                    block_type="_NonDefaultSaverA",
                    handler="save",
                    is_default=False,
                    metadata_fidelity=MetadataFidelity(level="pixel_only"),
                    is_synthesized=False,
                ),
            )

            def load(self, config: BlockConfig, output_dir: str = "") -> DataObject:
                raise NotImplementedError

            def save(self, obj: Any, config: BlockConfig) -> None:
                raise NotImplementedError

        class _NonDefaultSaverB(IOBlock):
            direction: ClassVar[str] = "output"
            type_name: ClassVar[str] = "non_default_saver_b"
            name: ClassVar[str] = "Non-default Saver B"
            input_ports: ClassVar[list[InputPort]] = [
                InputPort(name="data", accepted_types=[DataFrame], required=True),
            ]
            output_ports: ClassVar[list[Any]] = []
            format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
                FormatCapability(
                    id="ambiguity.b.dataframe.xyz.save",
                    direction="save",
                    data_type=DataFrame,
                    format_id="xyz",
                    extensions=(".xyz",),
                    label="Ambiguity-B xyz saver",
                    block_type="_NonDefaultSaverB",
                    handler="save",
                    is_default=False,
                    metadata_fidelity=MetadataFidelity(level="pixel_only"),
                    is_synthesized=False,
                ),
            )

            def load(self, config: BlockConfig, output_dir: str = "") -> DataObject:
                raise NotImplementedError

            def save(self, obj: Any, config: BlockConfig) -> None:
                raise NotImplementedError

        registry = BlockRegistry()
        registry._register_spec(_spec_from_class(_NonDefaultSaverA, source="test"))
        registry._register_spec(_spec_from_class(_NonDefaultSaverB, source="test"))
        with pytest.raises(AmbiguousCapabilityError):
            registry.find_saver_capability(DataFrame, ".xyz")


# ---------------------------------------------------------------------------
# Pickle runtime gating.
# ---------------------------------------------------------------------------


class TestPickleRuntimeGate:
    """Pickle save capabilities declare the opt-in note; the runtime gate
    still rejects ``.pkl`` writes without ``allow_pickle=True``."""

    def test_pickle_capability_declares_allow_pickle_note(self) -> None:
        capability = next(
            c for c in SaveData.format_capabilities if c.data_type is DataFrame and c.format_id == "pickle"
        )
        note = capability.metadata_fidelity.notes
        assert note is not None and "allow_pickle" in note

    def test_pickle_save_without_allow_pickle_raises(self, tmp_path: Path) -> None:
        target = tmp_path / "data.pkl"
        df = DataFrame(columns=["a"], row_count=1)
        df._arrow_table = pa.table({"a": [1]})  # type: ignore[attr-defined]
        block = SaveData(config={"params": {"core_type": "DataFrame", "path": str(target)}})
        with pytest.raises(ValueError, match="allow_pickle"):
            block.save(df, block.config)


# ---------------------------------------------------------------------------
# Backward-compat round-trip parity (FR-016: existing single-path save).
# ---------------------------------------------------------------------------


class TestBackwardCompatSaveRoundtrip:
    """Existing single-path save flows continue to work after the
    capability migration."""

    def test_dataframe_csv_save_round_trip(self, tmp_path: Path) -> None:
        target = tmp_path / "out.csv"
        df = DataFrame(columns=["a", "b"], row_count=2)
        df._arrow_table = pa.table({"a": [1, 3], "b": [2, 4]})  # type: ignore[attr-defined]
        block = SaveData(config={"params": {"core_type": "DataFrame", "path": str(target)}})
        block.save(df, block.config)
        assert target.exists()
        # Round-trip via pyarrow.csv
        import pyarrow.csv as pcsv

        table = pcsv.read_csv(str(target))
        assert table.column_names == ["a", "b"]
        assert table.num_rows == 2

    def test_array_npy_save_round_trip(self, tmp_path: Path) -> None:
        target = tmp_path / "out.npy"
        arr = Array(axes=["x"], shape=(3,), dtype="float64")
        arr._data = np.array([1.0, 2.0, 3.0])  # type: ignore[attr-defined]
        block = SaveData(config={"params": {"core_type": "Array", "path": str(target)}})
        block.save(arr, block.config)
        assert target.exists()
        loaded = np.load(str(target))
        np.testing.assert_array_equal(loaded, [1.0, 2.0, 3.0])

    def test_text_md_save_round_trip(self, tmp_path: Path) -> None:
        target = tmp_path / "out.md"
        text = Text(content="# heading\n\nbody\n", format="markdown", encoding="utf-8")
        block = SaveData(config={"params": {"core_type": "Text", "path": str(target)}})
        block.save(text, block.config)
        assert target.exists()
        assert target.read_text(encoding="utf-8") == "# heading\n\nbody\n"
