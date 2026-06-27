"""Tests for :attr:`LoadData.format_capabilities` (ADR-043 / spec FR-001).

These tests pin the explicit ``FormatCapability`` declarations on
:class:`scistudio.blocks.io.loaders.load_data.LoadData` introduced in
the ADR-043 in-tree-core-IO migration (spec
``adr-043-package-migration`` Phase A1, T-001 / T-002 / T-005 /
FR-016). They cover:

* capability count, IDs, defaults, metadata fidelity per declared
  ``(data_type, format_id)`` pair (FR-016);
* registry resolution via :meth:`BlockRegistry.find_loader_capability`
  returning the explicit (non-synthesized) record for each declared
  extension;
* ambiguity error when two LoadData-like blocks declare the same
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
import pytest

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import OutputPort
from scistudio.blocks.io.capabilities import FormatCapability, MetadataFidelity
from scistudio.blocks.io.io_block import IOBlock
from scistudio.blocks.io.loaders.load_data import (
    _LOAD_CAPABILITIES,
    _LOAD_EXTENSION_MAP,
    LoadData,
    _supported_load_extensions,
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
# Declaration-shape tests (FR-001 + FR-015 + FR-016).
# ---------------------------------------------------------------------------


class TestLoadDataFormatCapabilitiesShape:
    """:attr:`LoadData.format_capabilities` MUST be an explicit
    ``ClassVar[tuple[FormatCapability, ...]]`` (no synthesis fallback)
    covering every legacy ``(core_type, format_id)`` pair."""

    def test_format_capabilities_classvar_is_a_tuple_of_format_capability(self) -> None:
        assert isinstance(LoadData.format_capabilities, tuple)
        assert len(LoadData.format_capabilities) > 0
        for capability in LoadData.format_capabilities:
            assert isinstance(capability, FormatCapability)

    def test_format_capabilities_identity_matches_module_constant(self) -> None:
        """The class attribute is the same tuple instance as the
        module-level :data:`_LOAD_CAPABILITIES`."""
        assert LoadData.format_capabilities is _LOAD_CAPABILITIES

    def test_no_capability_is_synthesized(self) -> None:
        """FR-001: every record MUST have ``is_synthesized=False``."""
        for capability in LoadData.format_capabilities:
            assert capability.is_synthesized is False, (
                f"capability {capability.id!r} must be explicit (is_synthesized=False) per ADR-043 FR-001"
            )

    def test_all_directions_are_load(self) -> None:
        for capability in LoadData.format_capabilities:
            assert capability.direction == "load"

    def test_all_block_types_are_load_data(self) -> None:
        for capability in LoadData.format_capabilities:
            assert capability.block_type == "LoadData"

    def test_capability_ids_follow_fr015_naming_convention(self) -> None:
        """FR-015: capability id MUST be ``core.{lower(type)}.{format_id}.load``."""
        type_name_lookup = {
            Array: "array",
            DataFrame: "dataframe",
            Series: "series",
            Text: "text",
            Artifact: "artifact",
            CompositeData: "compositedata",
        }
        for capability in LoadData.format_capabilities:
            type_token = type_name_lookup[capability.data_type]
            expected = f"core.{type_token}.{capability.format_id}.load"
            assert capability.id == expected, (
                f"capability id {capability.id!r} must match FR-015 convention {expected!r}"
            )

    def test_every_capability_has_unique_id(self) -> None:
        ids = [capability.id for capability in LoadData.format_capabilities]
        duplicates = [identifier for identifier, count in Counter(ids).items() if count > 1]
        assert not duplicates, f"duplicate capability ids: {duplicates}"

    def test_one_capability_per_type_format_pair(self) -> None:
        """FR-016: capability count MUST be one record per ``(type, format_id)`` pair."""
        keys = [(capability.data_type, capability.format_id) for capability in LoadData.format_capabilities]
        duplicates = [key for key, count in Counter(keys).items() if count > 1]
        assert not duplicates, f"duplicate (data_type, format_id) pairs: {duplicates}; FR-016 requires one per pair"

    def test_no_capability_claims_default(self) -> None:
        """FR-001 cross-package collision rule: core IO capabilities are
        declared ``is_default=False`` so installed package-specific
        loaders (e.g. ``scistudio-blocks-lcms.table.csv.load`` for
        ``(DataFrame, .csv)``) keep ownership of the default slot
        without triggering a registration-time
        :class:`CapabilityRegistrationError`. When no package declares a
        default for a given ``(data_type, extension)`` slot, the
        registry returns the unique non-default core capability via
        :meth:`BlockRegistry.find_loader_capability`."""
        for capability in LoadData.format_capabilities:
            assert capability.is_default is False, (
                f"capability {capability.id!r} must be is_default=False "
                "to avoid cross-package default-slot conflicts (per A1 CI run "
                "and ADR-043 §8 cross-package collision rule)"
            )

    def test_metadata_fidelity_is_pixel_only(self) -> None:
        """FR-001: every record's ``metadata_fidelity.level`` MUST be ``pixel_only``."""
        for capability in LoadData.format_capabilities:
            assert capability.metadata_fidelity.level == "pixel_only", (
                f"capability {capability.id!r} must have pixel_only fidelity"
            )

    def test_pickle_capabilities_carry_allow_pickle_note(self) -> None:
        """Spec: pickle records carry ``notes='requires allow_pickle=True'``."""
        pickle_capabilities = [c for c in LoadData.format_capabilities if c.format_id == "pickle"]
        assert pickle_capabilities, "expected at least one pickle capability"
        for capability in pickle_capabilities:
            note = capability.metadata_fidelity.notes
            assert note is not None and "allow_pickle" in note, (
                f"pickle capability {capability.id!r} must declare allow_pickle note, got {note!r}"
            )

    def test_roundtrip_group_uses_fr015_convention(self) -> None:
        """Roundtrip group: ``core.{lower(type)}.{format_id}`` so load+save
        sibling records can be paired by the registry."""
        type_name_lookup = {
            Array: "array",
            DataFrame: "dataframe",
            Series: "series",
            Text: "text",
            Artifact: "artifact",
            CompositeData: "compositedata",
        }
        for capability in LoadData.format_capabilities:
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
            assert extension in _LOAD_EXTENSION_MAP, (
                f"legacy extension {extension!r} missing from capability-derived map"
            )

    def test_supported_load_extensions_helper_is_sorted_tuple(self) -> None:
        result = _supported_load_extensions()
        assert isinstance(result, tuple)
        assert list(result) == sorted(result)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# Per-type coverage assertions (FR-001: all six core types x supported extensions).
# ---------------------------------------------------------------------------


class TestLoadDataPerTypeCapabilityCoverage:
    """FR-001: explicit ``format_capabilities`` MUST cover all six core
    ``DataObject`` types x supported extensions."""

    @pytest.mark.parametrize(
        ("data_type", "expected_format_ids"),
        [
            (Array, {"npy", "npz", "zarr", "parquet", "pickle"}),
            (DataFrame, {"csv", "tsv", "parquet", "json", "xlsx", "pickle"}),
            (Series, {"csv", "tsv", "parquet", "xlsx", "pickle"}),
            (Text, {"text"}),
            (CompositeData, {"json"}),
        ],
    )
    def test_per_type_format_id_coverage(
        self,
        data_type: type[DataObject],
        expected_format_ids: set[str],
    ) -> None:
        actual = {c.format_id for c in LoadData.format_capabilities if c.data_type is data_type}
        assert actual == expected_format_ids, (
            f"{data_type.__name__}: expected format_ids {expected_format_ids}, got {actual}"
        )

    def test_artifact_has_canonical_format_ids(self) -> None:
        """Artifact is a catch-all opaque loader at runtime; the explicit
        capability set lists (a) the canonical MIME-mapped subset
        (binary, pdf, png, jpeg, tiff — see ``_MIME_GUESS``) AND (b) the
        opaque variants for the legacy supported-extension union so the
        AppBlock wildcard-port binner (``types=['DataObject']`` mapped to
        ``target_type=Artifact``) keeps resolving a loader."""
        actual = {c.format_id for c in LoadData.format_capabilities if c.data_type is Artifact}
        # MIME-mapped subset.
        assert actual >= {"binary", "pdf", "png", "jpeg", "tiff"}
        # Opaque-loader variants for the typed-core extension union.
        assert actual >= {"csv", "tsv", "json", "parquet", "npy", "npz", "zarr", "text", "pickle"}


# ---------------------------------------------------------------------------
# BlockRegistry round-trip via find_loader_capability (FR-016).
# ---------------------------------------------------------------------------


def _registry_with_load_data() -> BlockRegistry:
    """Build a BlockRegistry containing just :class:`LoadData`."""
    registry = BlockRegistry()
    registry._register_spec(_spec_from_class(LoadData, source="test"))
    return registry


class TestRegistryFindLoaderCapability:
    """:meth:`BlockRegistry.find_loader_capability` MUST return the
    explicit (non-synthesized) LoadData record for each declared
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
            (Text, ".txt", "text"),
            (Text, ".md", "text"),
            (Text, ".yaml", "text"),
            (CompositeData, ".json", "json"),
            (Artifact, ".bin", "binary"),
            (Artifact, ".png", "png"),
            (Artifact, ".jpeg", "jpeg"),
        ],
    )
    def test_find_loader_capability_returns_explicit_record(
        self,
        data_type: type[DataObject],
        extension: str,
        expected_format_id: str,
    ) -> None:
        registry = _registry_with_load_data()
        capability = registry.find_loader_capability(data_type, extension)
        assert capability.is_synthesized is False, (
            f"expected explicit (non-synthesized) capability for {data_type.__name__} {extension}, "
            f"got synthesized {capability.id!r}"
        )
        assert capability.format_id == expected_format_id
        assert capability.block_type == "LoadData"

    def test_unknown_extension_raises_missing(self) -> None:
        registry = _registry_with_load_data()
        with pytest.raises(MissingCapabilityError):
            registry.find_loader_capability(DataFrame, ".unknown_ext")


# ---------------------------------------------------------------------------
# Ambiguity test (FR-016: ambiguity error for type+extension matching multiple).
# ---------------------------------------------------------------------------


class _AltDataFrameLoader(IOBlock):
    """Hypothetical second LoadData-like block declaring the same (type, ext)."""

    direction: ClassVar[str] = "input"
    type_name: ClassVar[str] = "alt_dataframe_loader"
    name: ClassVar[str] = "Alt DataFrame Loader"
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="data", accepted_types=[DataFrame]),
    ]
    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
        FormatCapability(
            id="alt.dataframe.csv.load",
            direction="load",
            data_type=DataFrame,
            format_id="csv",
            extensions=(".csv",),
            label="Alt CSV loader",
            block_type="_AltDataFrameLoader",
            handler="load",
            is_default=True,
            metadata_fidelity=MetadataFidelity(level="pixel_only"),
            is_synthesized=False,
        ),
    )

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject:
        raise NotImplementedError

    def save(self, obj: Any, config: BlockConfig) -> None:
        raise NotImplementedError


class TestRegistryAmbiguityForMultipleCapabilities:
    """FR-016: when two blocks declare the same ``(direction, data_type,
    extension)`` and only one is default, the default wins. When neither
    is default (or both are), an :class:`AmbiguousCapabilityError` is
    raised."""

    def test_default_alternate_wins_over_non_default_core(self) -> None:
        """LoadData's ``core.dataframe.csv.load`` is ``is_default=False``
        (cross-package collision rule per A1 CI run). When a third-party
        block declares the same slot with ``is_default=True``, the
        default declaration wins. This mirrors the LCMS pilot pattern
        where ``scistudio-blocks-lcms.table.csv.load`` claims default
        ownership of ``(DataFrame, .csv)`` and LoadData yields."""
        registry = BlockRegistry()
        registry._register_spec(_spec_from_class(LoadData, source="test"))
        registry._register_spec(_spec_from_class(_AltDataFrameLoader, source="test"))
        capability = registry.find_loader_capability(DataFrame, ".csv")
        assert capability.block_type == "_AltDataFrameLoader"

    def test_two_non_default_capabilities_for_same_slot_raise_ambiguous_lookup(self) -> None:
        """When two capabilities are both ``is_default=False`` and share
        the same specificity and priority for the same ``(direction,
        data_type, extension)`` slot, :meth:`find_loader_capability`
        raises :class:`AmbiguousCapabilityError`.

        Note: two ``is_default=True`` capabilities for the same slot are
        rejected at registration time with
        :class:`CapabilityRegistrationError` per
        :meth:`BlockRegistry._validate_capability_registration`, so the
        ambiguity-at-lookup error is only reachable when both candidates
        are non-default.
        """

        class _NonDefaultLoaderA(IOBlock):
            direction: ClassVar[str] = "input"
            type_name: ClassVar[str] = "non_default_loader_a"
            name: ClassVar[str] = "Non-default Loader A"
            output_ports: ClassVar[list[OutputPort]] = [
                OutputPort(name="data", accepted_types=[DataFrame]),
            ]
            format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
                FormatCapability(
                    id="ambiguity.a.dataframe.xyz.load",
                    direction="load",
                    data_type=DataFrame,
                    format_id="xyz",
                    extensions=(".xyz",),
                    label="Ambiguity-A xyz loader",
                    block_type="_NonDefaultLoaderA",
                    handler="load",
                    is_default=False,
                    metadata_fidelity=MetadataFidelity(level="pixel_only"),
                    is_synthesized=False,
                ),
            )

            def load(self, config: BlockConfig, output_dir: str = "") -> DataObject:
                raise NotImplementedError

            def save(self, obj: Any, config: BlockConfig) -> None:
                raise NotImplementedError

        class _NonDefaultLoaderB(IOBlock):
            direction: ClassVar[str] = "input"
            type_name: ClassVar[str] = "non_default_loader_b"
            name: ClassVar[str] = "Non-default Loader B"
            output_ports: ClassVar[list[OutputPort]] = [
                OutputPort(name="data", accepted_types=[DataFrame]),
            ]
            format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
                FormatCapability(
                    id="ambiguity.b.dataframe.xyz.load",
                    direction="load",
                    data_type=DataFrame,
                    format_id="xyz",
                    extensions=(".xyz",),
                    label="Ambiguity-B xyz loader",
                    block_type="_NonDefaultLoaderB",
                    handler="load",
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
        registry._register_spec(_spec_from_class(_NonDefaultLoaderA, source="test"))
        registry._register_spec(_spec_from_class(_NonDefaultLoaderB, source="test"))
        with pytest.raises(AmbiguousCapabilityError):
            registry.find_loader_capability(DataFrame, ".xyz")


# ---------------------------------------------------------------------------
# Pickle runtime gating (FR-001 notes + existing _check_pickle_allowed behaviour).
# ---------------------------------------------------------------------------


class TestPickleRuntimeGate:
    """Pickle capabilities declare the opt-in note; the runtime gate
    still rejects ``.pkl`` loads without ``allow_pickle=True``."""

    def test_pickle_capability_declares_allow_pickle_note(self) -> None:
        capability = next(
            c for c in LoadData.format_capabilities if c.data_type is DataFrame and c.format_id == "pickle"
        )
        note = capability.metadata_fidelity.notes
        assert note is not None and "allow_pickle" in note

    def test_pickle_load_without_allow_pickle_raises(self, tmp_path: Path) -> None:
        """Pickle gating still works at runtime."""
        import pickle

        target = tmp_path / "data.pkl"
        target.write_bytes(pickle.dumps({"value": 1}))
        block = LoadData(config={"params": {"core_type": "DataFrame", "path": str(target)}})
        with pytest.raises(ValueError, match="allow_pickle"):
            block.run(inputs={}, config=block.config)


# ---------------------------------------------------------------------------
# Backward-compat round-trip parity (FR-016: existing single-path load + save).
# ---------------------------------------------------------------------------


class TestBackwardCompatLoadRoundtrip:
    """Existing single-path load flows continue to work after the
    capability migration."""

    def test_dataframe_csv_load_round_trip(self, tmp_path: Path) -> None:
        target = tmp_path / "data.csv"
        target.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
        block = LoadData(config={"params": {"core_type": "DataFrame", "path": str(target)}})
        outputs = block.run(inputs={}, config=block.config)
        collection = outputs["data"]
        loaded = collection[0]
        assert isinstance(loaded, DataFrame)
        assert loaded.columns == ["a", "b"]
        assert loaded.row_count == 2

    def test_array_npy_load_round_trip(self, tmp_path: Path) -> None:
        target = tmp_path / "data.npy"
        np.save(str(target), np.array([1.0, 2.0, 3.0]))
        block = LoadData(config={"params": {"core_type": "Array", "path": str(target)}})
        outputs = block.run(inputs={}, config=block.config)
        collection = outputs["data"]
        loaded = collection[0]
        assert isinstance(loaded, Array)
        assert loaded.shape == (3,)

    def test_text_md_load_round_trip(self, tmp_path: Path) -> None:
        target = tmp_path / "doc.md"
        target.write_text("# heading\n\nbody\n", encoding="utf-8")
        block = LoadData(config={"params": {"core_type": "Text", "path": str(target)}})
        outputs = block.run(inputs={}, config=block.config)
        collection = outputs["data"]
        loaded = collection[0]
        assert isinstance(loaded, Text)
        assert loaded.format == "markdown"
        assert "# heading" in (loaded.content or "")
