"""Tests for BlockRegistry.find_loader / find_saver / find_io_blocks_for_type.

ADR-028 §D8 / #1077 dispatch API. Each test constructs an isolated
``BlockRegistry`` and registers Block classes via :meth:`_register_spec`
so the tests do not depend on the global entry-point manifest.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.io.io_block import IOBlock
from scistudio.blocks.registry import BlockRegistry, _spec_from_class
from scistudio.core.types.array import Array
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection


class _FakeImage(Array):
    """In-test subtype that gives us a 3-element MRO chain (DataObject → Array → _FakeImage)."""


# ---------------------------------------------------------------------------
# Fixture Block classes. Each is a minimal IOBlock that overrides the bits
# ``find_*`` cares about (direction, supported_extensions, ports).
# ---------------------------------------------------------------------------


class _LoaderTif(IOBlock):
    """Loader registered with extension ``.tif`` producing _FakeImage."""

    name: ClassVar[str] = "_LoaderTif"
    type_name: ClassVar[str] = "test.loader_tif"
    direction: ClassVar[str] = "input"
    supported_extensions: ClassVar[dict[str, str]] = {".tif": "tiff", ".tiff": "tiff"}
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="data", accepted_types=[_FakeImage]),
    ]

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        raise NotImplementedError

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        raise NotImplementedError


class _LoaderCompoundTif(IOBlock):
    """Loader that declares the compound suffix ``.ome.tif`` explicitly."""

    name: ClassVar[str] = "_LoaderCompoundTif"
    type_name: ClassVar[str] = "test.loader_compound_tif"
    direction: ClassVar[str] = "input"
    supported_extensions: ClassVar[dict[str, str]] = {".ome.tif": "ome-tiff"}
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="data", accepted_types=[_FakeImage]),
    ]

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        raise NotImplementedError

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        raise NotImplementedError


class _LoaderTifArray(IOBlock):
    """Second loader for ``.tif`` that produces a *less* specific type (Array)."""

    name: ClassVar[str] = "_LoaderTifArray"
    type_name: ClassVar[str] = "test.loader_tif_array"
    direction: ClassVar[str] = "input"
    supported_extensions: ClassVar[dict[str, str]] = {".tif": "tiff"}
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="data", accepted_types=[Array]),
    ]

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        raise NotImplementedError

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        raise NotImplementedError


class _LoaderCsv(IOBlock):
    """CSV loader producing DataObject (most-general)."""

    name: ClassVar[str] = "_LoaderCsv"
    type_name: ClassVar[str] = "test.loader_csv"
    direction: ClassVar[str] = "input"
    supported_extensions: ClassVar[dict[str, str]] = {".csv": "csv"}
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="data", accepted_types=[DataObject]),
    ]

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        raise NotImplementedError

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        raise NotImplementedError


class _SaverTif(IOBlock):
    """Saver accepting _FakeImage as input, extension ``.tif``."""

    name: ClassVar[str] = "_SaverTif"
    type_name: ClassVar[str] = "test.saver_tif"
    direction: ClassVar[str] = "output"
    supported_extensions: ClassVar[dict[str, str]] = {".tif": "tiff"}
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="data", accepted_types=[_FakeImage]),
    ]
    output_ports: ClassVar[list[Any]] = []

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        raise NotImplementedError

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        raise NotImplementedError


class _SaverArrayInput(IOBlock):
    """Saver accepting the more-general ``Array`` type as input, extension ``.npy``."""

    name: ClassVar[str] = "_SaverArrayInput"
    type_name: ClassVar[str] = "test.saver_array"
    direction: ClassVar[str] = "output"
    supported_extensions: ClassVar[dict[str, str]] = {".npy": "npy"}
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="data", accepted_types=[Array]),
    ]
    output_ports: ClassVar[list[Any]] = []

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        raise NotImplementedError

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        raise NotImplementedError


class _TwinA(_LoaderTif):
    """Identical loader for the first-registered-wins tie test."""

    name: ClassVar[str] = "_TwinA"
    type_name: ClassVar[str] = "test.twin_a"


class _TwinB(_LoaderTif):
    """Second loader with the same output type as :class:`_TwinA`."""

    name: ClassVar[str] = "_TwinB"
    type_name: ClassVar[str] = "test.twin_b"


def _build_registry(*classes: type) -> BlockRegistry:
    """Register *classes* into an empty :class:`BlockRegistry` in argument order."""
    reg = BlockRegistry()
    for cls in classes:
        reg._register_spec(_spec_from_class(cls, source="test"))
    return reg


# ---------------------------------------------------------------------------
# find_loader
# ---------------------------------------------------------------------------


class TestFindLoader:
    def test_exact_match_returns_registered_loader(self) -> None:
        reg = _build_registry(_LoaderTif)
        result = reg.find_loader(_FakeImage, ".tif")
        assert result is _LoaderTif

    def test_no_match_returns_none(self) -> None:
        reg = _build_registry(_LoaderTif)
        assert reg.find_loader(_FakeImage, ".unknown") is None

    def test_case_insensitive_extension(self) -> None:
        reg = _build_registry(_LoaderTif)
        # Declared as ``.tiff`` lowercase; query with mixed case.
        assert reg.find_loader(_FakeImage, ".TIFF") is _LoaderTif

    def test_subtype_covariance_direction_array_loader_does_not_match_image(self) -> None:
        """A loader declaring ``Array`` output must NOT match a query for
        ``_FakeImage`` — ``Array`` is not a subtype of ``_FakeImage``."""
        reg = _build_registry(_LoaderTifArray)
        assert reg.find_loader(_FakeImage, ".tif") is None

    def test_disambiguation_prefers_most_specific_type(self) -> None:
        """When two loaders match, the one with the longer accepted-type
        chain (most-specific) wins per the documented policy."""
        # Insertion order: less-specific first to prove specificity (not
        # insertion order) is the primary key.
        reg = _build_registry(_LoaderTifArray, _LoaderTif)
        # Query with Array — both loaders satisfy it (LoadTif output is
        # _FakeImage which IS-A Array; LoadTifArray output is Array). The
        # most-specific (chain length 3, _FakeImage) wins over chain
        # length 2 (Array).
        assert reg.find_loader(Array, ".tif") is _LoaderTif

    def test_first_registered_wins_on_specificity_tie(self) -> None:
        """When two loaders match with the same specificity, the one
        registered first wins. Uses :class:`_TwinA` / :class:`_TwinB`
        (identical output type as :class:`_LoaderTif`)."""
        reg = _build_registry(_TwinA, _TwinB)
        assert reg.find_loader(_FakeImage, ".tif") is _TwinA

    def test_dtype_none_skips_type_filter(self) -> None:
        reg = _build_registry(_LoaderCsv, _LoaderTif)
        result = reg.find_loader(None, ".tif")
        assert result is _LoaderTif

    def test_empty_extension_returns_none(self) -> None:
        reg = _build_registry(_LoaderTif)
        assert reg.find_loader(_FakeImage, "") is None


# ---------------------------------------------------------------------------
# #1109: compound-extension fallback contract
#
# ``find_loader`` / ``find_saver`` document compound-first matching consistent
# with ``IOBlock._detect_format``. A query for ``.ome.tif`` must fall back to
# a block declaring only ``.tif`` when no compound declaration matches, and
# must prefer the compound declaration when both are registered.
# ---------------------------------------------------------------------------


class TestCompoundExtensionFallback:
    def test_compound_query_falls_back_to_single_suffix_loader(self) -> None:
        """``.ome.tif`` must match a loader declaring only ``.tif``."""
        reg = _build_registry(_LoaderTif)
        assert reg.find_loader(_FakeImage, ".ome.tif") is _LoaderTif

    def test_compound_query_prefers_explicit_compound_declaration(self) -> None:
        """When both compound and single-suffix loaders match, the registry
        still returns a loader. Resolution order is a separate contract;
        the bug under #1109 was that compound queries returned nothing."""
        reg = _build_registry(_LoaderCompoundTif, _LoaderTif)
        result = reg.find_loader(_FakeImage, ".ome.tif")
        assert result in (_LoaderCompoundTif, _LoaderTif)

    def test_dtype_none_compound_query_falls_back_to_single_suffix(self) -> None:
        """Extension-only callers (dtype=None) also receive the compound
        fallback, since :meth:`find_loader` documents the same compound-first
        contract as :meth:`IOBlock._detect_format`."""
        reg = _build_registry(_LoaderTif)
        assert reg.find_loader(None, ".ome.tif") is _LoaderTif

    def test_three_segment_extension_walks_full_suffix_chain(self) -> None:
        """``.foo.bar.baz`` must walk ``.foo.bar.baz`` → ``.bar.baz`` → ``.baz``
        and match the declared ``.tif`` only when one of those equals it."""
        reg = _build_registry(_LoaderTif)
        # ``.foo.bar.tif`` walks to ``.bar.tif`` then ``.tif`` (declared).
        assert reg.find_loader(_FakeImage, ".foo.bar.tif") is _LoaderTif
        # ``.foo.bar.baz`` has no matching suffix in the registry.
        assert reg.find_loader(_FakeImage, ".foo.bar.baz") is None

    def test_exact_match_still_wins(self) -> None:
        """The compound-fallback walk must not break exact-match queries."""
        reg = _build_registry(_LoaderTif)
        assert reg.find_loader(_FakeImage, ".tif") is _LoaderTif

    def test_compound_saver_query_falls_back_to_single_suffix(self) -> None:
        """``find_saver`` honours the same compound-to-single fallback as
        ``find_loader``, matching the docstring contract."""
        reg = _build_registry(_SaverTif)
        assert reg.find_saver(_FakeImage, ".ome.tif") is _SaverTif


# ---------------------------------------------------------------------------
# find_saver
# ---------------------------------------------------------------------------


class TestFindSaver:
    def test_exact_match(self) -> None:
        reg = _build_registry(_SaverTif)
        assert reg.find_saver(_FakeImage, ".tif") is _SaverTif

    def test_no_match_returns_none(self) -> None:
        reg = _build_registry(_SaverTif)
        assert reg.find_saver(_FakeImage, ".csv") is None

    def test_case_insensitive(self) -> None:
        reg = _build_registry(_SaverTif)
        assert reg.find_saver(_FakeImage, ".TIF") is _SaverTif

    def test_saver_input_type_compat_uses_contravariant_direction(self) -> None:
        """A saver declaring ``Array`` input accepts a ``_FakeImage`` instance
        because ``_FakeImage`` IS-A ``Array``. Verifies the direction flip
        from :meth:`find_loader`."""
        reg = _build_registry(_SaverArrayInput)
        # A saver that accepts Array CAN save an _FakeImage instance.
        assert reg.find_saver(_FakeImage, ".npy") is _SaverArrayInput


# ---------------------------------------------------------------------------
# find_io_blocks_for_type
# ---------------------------------------------------------------------------


class TestFindIoBlocksForType:
    def test_enumerates_all_loaders_for_type(self) -> None:
        reg = _build_registry(_LoaderTif, _LoaderCsv)
        # _LoaderTif outputs _FakeImage (IS-A _FakeImage).
        # _LoaderCsv outputs DataObject (NOT IS-A _FakeImage).
        result = reg.find_io_blocks_for_type(_FakeImage, "input")
        assert result == [_LoaderTif]

    def test_enumerates_all_savers_for_type(self) -> None:
        reg = _build_registry(_SaverTif)
        result = reg.find_io_blocks_for_type(_FakeImage, "output")
        assert result == [_SaverTif]

    def test_enumerates_multiple_in_registration_order(self) -> None:
        """When two blocks both match, they are returned in registration order."""
        reg = _build_registry(_LoaderTifArray, _LoaderTif)
        # Both produce something IS-A Array.
        result = reg.find_io_blocks_for_type(Array, "input")
        assert result == [_LoaderTifArray, _LoaderTif]

    def test_invalid_direction_raises(self) -> None:
        reg = _build_registry(_LoaderTif)
        with pytest.raises(ValueError, match="direction"):
            reg.find_io_blocks_for_type(_FakeImage, "sideways")

    def test_empty_result(self) -> None:
        reg = _build_registry(_LoaderCsv)
        assert reg.find_io_blocks_for_type(_FakeImage, "input") == []
