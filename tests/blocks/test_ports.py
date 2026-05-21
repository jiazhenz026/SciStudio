"""Tests for port type matching, constraint validation, and connection checking."""

from __future__ import annotations

from typing import Any

from scistudio.blocks.base.ports import (
    InputPort,
    OutputPort,
    port_accepts_signature,
    port_accepts_type,
    ports_from_config_dicts,
    validate_connection,
    validate_port_constraint,
)
from scistudio.core.types.array import Array
from scistudio.core.types.base import DataObject, TypeSignature
from scistudio.core.types.composite import CompositeData
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.series import Series

# ---------------------------------------------------------------------------
# Local test fixtures.
#
# ADR-027 D2: core no longer ships ``Image``, ``Spectrum``, ``AnnData``
# or ``PeakTable`` — those live in plugin packages. These tests need
# concrete subclasses of the four base types to exercise subtype /
# multi-accepted-types port matching, so we declare minimal fixtures
# here (same pattern as ``tests/core/test_types.py``).
# ---------------------------------------------------------------------------


class Image(Array):
    """Local 2D Array test fixture."""

    def __init__(
        self,
        *,
        shape: tuple[int, ...] | None = None,
        ndim: int | None = None,
        dtype: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(axes=["y", "x"], shape=shape, dtype=dtype, **kwargs)


class Spectrum(Series):
    """Local Series subclass test fixture."""


class PeakTable(DataFrame):
    """Local DataFrame subclass test fixture."""


class AnnData(CompositeData):
    """Local CompositeData subclass test fixture."""


class TestPortAcceptsType:
    """port_accepts_type — isinstance-based, inheritance-aware matching."""

    def test_exact_match(self) -> None:
        port = InputPort(name="in", accepted_types=[Array])
        assert port_accepts_type(port, Array)

    def test_subtype_accepted(self) -> None:
        port = InputPort(name="in", accepted_types=[Array])
        assert port_accepts_type(port, Image)

    def test_unrelated_rejected(self) -> None:
        port = InputPort(name="in", accepted_types=[Array])
        assert not port_accepts_type(port, DataFrame)

    def test_empty_accepts_anything(self) -> None:
        port = InputPort(name="in", accepted_types=[])
        assert port_accepts_type(port, DataFrame)
        assert port_accepts_type(port, Image)

    def test_multiple_accepted_types(self) -> None:
        port = InputPort(name="in", accepted_types=[Array, DataFrame])
        assert port_accepts_type(port, Image)
        assert port_accepts_type(port, PeakTable)
        assert not port_accepts_type(port, Series)

    def test_dataobject_accepts_all(self) -> None:
        port = InputPort(name="in", accepted_types=[DataObject])
        assert port_accepts_type(port, Image)
        assert port_accepts_type(port, DataFrame)
        assert port_accepts_type(port, Spectrum)


class TestPortAcceptsSignature:
    """port_accepts_signature — TypeSignature matching."""

    def test_exact_signature(self) -> None:
        port = InputPort(name="in", accepted_types=[Array])
        sig = TypeSignature.from_type(Array)
        assert port_accepts_signature(port, sig)

    def test_subtype_signature(self) -> None:
        port = InputPort(name="in", accepted_types=[Array])
        sig = TypeSignature.from_type(Image)
        assert port_accepts_signature(port, sig)

    def test_incompatible_signature(self) -> None:
        port = InputPort(name="in", accepted_types=[Array])
        sig = TypeSignature.from_type(DataFrame)
        assert not port_accepts_signature(port, sig)

    def test_empty_accepts_all_signatures(self) -> None:
        port = InputPort(name="in", accepted_types=[])
        sig = TypeSignature.from_type(DataFrame)
        assert port_accepts_signature(port, sig)

    def test_composite_slot_constraint(self) -> None:
        """CompositeData subtype's signature is accepted by CompositeData port."""
        port = InputPort(name="in", accepted_types=[CompositeData])
        sig = TypeSignature.from_type(AnnData)
        assert port_accepts_signature(port, sig)


class TestValidatePortConstraint:
    """validate_port_constraint — constraint function checking."""

    def test_no_constraint_passes(self) -> None:
        port = InputPort(name="in", accepted_types=[])
        ok, desc = validate_port_constraint(port, "anything")
        assert ok
        assert desc == ""

    def test_constraint_passes(self) -> None:
        port = InputPort(
            name="in",
            accepted_types=[],
            constraint=lambda v: v > 0,
            constraint_description="Must be positive",
        )
        ok, _desc = validate_port_constraint(port, 5)
        assert ok

    def test_constraint_fails(self) -> None:
        port = InputPort(
            name="in",
            accepted_types=[],
            constraint=lambda v: v > 0,
            constraint_description="Must be positive",
        )
        ok, desc = validate_port_constraint(port, -1)
        assert not ok
        assert "Must be positive" in desc

    def test_constraint_exception(self) -> None:
        port = InputPort(
            name="in",
            accepted_types=[],
            constraint=lambda v: v.nonexistent_attr,
        )
        ok, desc = validate_port_constraint(port, 42)
        assert not ok
        assert "AttributeError" in desc


class TestValidateConnection:
    """validate_connection — source port -> target port compatibility."""

    def test_compatible(self) -> None:
        src = OutputPort(name="out", accepted_types=[Image])
        tgt = InputPort(name="in", accepted_types=[Array])
        ok, _reason = validate_connection(src, tgt)
        assert ok

    def test_incompatible(self) -> None:
        src = OutputPort(name="out", accepted_types=[DataFrame])
        tgt = InputPort(name="in", accepted_types=[Array])
        ok, reason = validate_connection(src, tgt)
        assert not ok
        assert "DataFrame" in reason
        assert "Array" in reason

    def test_empty_source_always_compatible(self) -> None:
        src = OutputPort(name="out", accepted_types=[])
        tgt = InputPort(name="in", accepted_types=[Array])
        ok, _ = validate_connection(src, tgt)
        assert ok

    def test_empty_target_always_compatible(self) -> None:
        src = OutputPort(name="out", accepted_types=[DataFrame])
        tgt = InputPort(name="in", accepted_types=[])
        ok, _ = validate_connection(src, tgt)
        assert ok

    def test_subtype_in_multi_type_port(self) -> None:
        src = OutputPort(name="out", accepted_types=[PeakTable])
        tgt = InputPort(name="in", accepted_types=[Array, DataFrame])
        ok, _ = validate_connection(src, tgt)
        assert ok

    def test_bidirectional_parent_to_child(self) -> None:
        """#601: Source produces parent type, target accepts child type — allowed."""
        src = OutputPort(name="out", accepted_types=[Array])
        tgt = InputPort(name="in", accepted_types=[Image])
        ok, _ = validate_connection(src, tgt)
        assert ok

    def test_bidirectional_child_to_parent(self) -> None:
        """#601: Source produces child type, target accepts parent type — allowed (original direction)."""
        src = OutputPort(name="out", accepted_types=[Image])
        tgt = InputPort(name="in", accepted_types=[Array])
        ok, _ = validate_connection(src, tgt)
        assert ok

    def test_bidirectional_unrelated_still_rejected(self) -> None:
        """#601: Unrelated types still rejected even with bidirectional check."""
        src = OutputPort(name="out", accepted_types=[DataFrame])
        tgt = InputPort(name="in", accepted_types=[Array])
        ok, reason = validate_connection(src, tgt)
        assert not ok
        assert "DataFrame" in reason


class TestCollectionTransparency:
    """ADR-020: Collection-transparent type checking."""

    def test_collection_image_matches_image_port(self) -> None:
        """Collection[Image] should be accepted by a port accepting Image."""
        from scistudio.core.types.collection import Collection

        port = InputPort(name="in", accepted_types=[Image])
        img = Image(shape=(5, 5), ndim=2, dtype="uint8")
        c = Collection([img])
        # Collection-transparent: checks item_type
        assert port_accepts_type(port, c)

    def test_collection_dataframe_rejected_by_image_port(self) -> None:
        """ADR-020-Add6: Collection[DataFrame] should NOT match Image port."""
        from scistudio.core.types.collection import Collection
        from scistudio.core.types.dataframe import DataFrame

        port = InputPort(name="in", accepted_types=[Image])
        df = DataFrame(columns=["a"], row_count=1)
        c = Collection([df])
        assert not port_accepts_type(port, c)

    def test_collection_subtype_matches(self) -> None:
        """Collection[Image] (subtype of Array) should match Array port."""
        from scistudio.core.types.collection import Collection

        port = InputPort(name="in", accepted_types=[Array])
        img = Image(shape=(5, 5), ndim=2, dtype="uint8")
        c = Collection([img])
        assert port_accepts_type(port, c)

    def test_collection_type_object_does_not_match(self) -> None:
        """Issue #129: passing type(collection) instead of instance fails.

        This documents the old bug — Block.validate() was calling
        port_accepts_type(port, type(value)) which passes the Collection
        *class*, not a Collection *instance*. The isinstance check in
        port_accepts_type() correctly requires an instance.
        """
        from scistudio.core.types.collection import Collection

        port = InputPort(name="in", accepted_types=[Image])
        img = Image(shape=(5, 5), ndim=2, dtype="uint8")
        c = Collection([img])
        # type(c) is the Collection class, not a Collection instance
        # This should NOT match — Collection class is not a subclass of Image
        assert not port_accepts_type(port, type(c))


class TestPortsFromConfigDicts:
    """ADR-029 D1: ports_from_config_dicts — convert config dicts to port objects."""

    def test_input_direction_creates_input_ports(self) -> None:
        dicts = [{"name": "img", "types": ["DataObject"]}]
        ports = ports_from_config_dicts(dicts, "input")
        assert len(ports) == 1
        assert isinstance(ports[0], InputPort)
        assert ports[0].name == "img"

    def test_output_direction_creates_output_ports(self) -> None:
        dicts = [{"name": "result", "types": ["DataObject"]}]
        ports = ports_from_config_dicts(dicts, "output")
        assert len(ports) == 1
        assert isinstance(ports[0], OutputPort)
        assert ports[0].name == "result"

    def test_empty_types_defaults_to_dataobject(self) -> None:
        dicts = [{"name": "x", "types": []}]
        ports = ports_from_config_dicts(dicts, "input")
        assert ports[0].accepted_types == [DataObject]

    def test_missing_types_key_defaults_to_dataobject(self) -> None:
        dicts = [{"name": "x"}]
        ports = ports_from_config_dicts(dicts, "input")
        assert ports[0].accepted_types == [DataObject]

    def test_unknown_type_name_falls_back_to_dataobject(self) -> None:
        dicts = [{"name": "x", "types": ["NonExistentType99"]}]
        ports = ports_from_config_dicts(dicts, "input")
        assert ports[0].accepted_types == [DataObject]

    def test_multiple_ports(self) -> None:
        dicts = [
            {"name": "a", "types": ["DataObject"]},
            {"name": "b", "types": ["DataObject"]},
        ]
        ports = ports_from_config_dicts(dicts, "input")
        assert len(ports) == 2
        assert ports[0].name == "a"
        assert ports[1].name == "b"

    def test_duplicate_names_deduplicated(self) -> None:
        dicts = [
            {"name": "x", "types": ["DataObject"]},
            {"name": "x", "types": ["DataObject"]},
        ]
        ports = ports_from_config_dicts(dicts, "input")
        assert len(ports) == 1
        assert ports[0].name == "x"

    def test_empty_list_returns_empty(self) -> None:
        ports = ports_from_config_dicts([], "input")
        assert ports == []

    def test_known_type_name_resolves_correctly(self) -> None:
        """A registered type name like 'Array' or 'DataObject' resolves to the class."""
        dicts = [{"name": "data", "types": ["DataObject"]}]
        ports = ports_from_config_dicts(dicts, "input")
        assert DataObject in ports[0].accepted_types
