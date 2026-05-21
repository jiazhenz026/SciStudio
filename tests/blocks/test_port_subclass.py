"""Regression tests for #437: port type subclass matching via validate_connection."""

from __future__ import annotations

from scistudio.blocks.base.ports import InputPort, OutputPort, validate_connection
from scistudio.core.types.base import DataObject

# --- Stub type hierarchy for testing ---


class Image(DataObject):
    """Base image type."""

    def save(self, path: str) -> None:
        pass

    @classmethod
    def load(cls, path: str) -> Image:
        return cls()


class Mask(Image):
    """Mask is a subclass of Image."""

    pass


class Label(Image):
    """Label is a subclass of Image."""

    pass


class Table(DataObject):
    """Unrelated type."""

    def save(self, path: str) -> None:
        pass

    @classmethod
    def load(cls, path: str) -> Table:
        return cls()


# --- Tests ---


def test_subclass_source_connects_to_superclass_target() -> None:
    """A Mask output should connect to an Image input (subclass -> superclass)."""
    src = OutputPort(name="mask_out", accepted_types=[Mask])
    tgt = InputPort(name="image_in", accepted_types=[Image])

    ok, reason = validate_connection(src, tgt)
    assert ok, f"Mask -> Image should be compatible, got: {reason}"


def test_exact_type_connects() -> None:
    """Image output connects to Image input."""
    src = OutputPort(name="out", accepted_types=[Image])
    tgt = InputPort(name="in", accepted_types=[Image])

    ok, reason = validate_connection(src, tgt)
    assert ok, f"Image -> Image should be compatible, got: {reason}"


def test_unrelated_types_rejected() -> None:
    """Table output should NOT connect to Image input."""
    src = OutputPort(name="out", accepted_types=[Table])
    tgt = InputPort(name="in", accepted_types=[Image])

    ok, _reason = validate_connection(src, tgt)
    assert not ok, "Table -> Image should be incompatible"


def test_superclass_to_subclass_accepted_bidirectional() -> None:
    """#601: Image output connects to Mask-only input (bidirectional subclass check)."""
    src = OutputPort(name="out", accepted_types=[Image])
    tgt = InputPort(name="in", accepted_types=[Mask])

    ok, reason = validate_connection(src, tgt)
    assert ok, f"Image -> Mask should be compatible (bidirectional), got: {reason}"


def test_multiple_accepted_types_one_matches() -> None:
    """Label output connects if target accepts [Mask, Image]."""
    src = OutputPort(name="out", accepted_types=[Label])
    tgt = InputPort(name="in", accepted_types=[Mask, Image])

    ok, reason = validate_connection(src, tgt)
    assert ok, f"Label -> [Mask, Image] should be compatible via Image, got: {reason}"


def test_empty_accepted_types_always_compatible() -> None:
    """Empty accepted_types on either side means accept anything."""
    src = OutputPort(name="out", accepted_types=[])
    tgt = InputPort(name="in", accepted_types=[Image])

    ok, _ = validate_connection(src, tgt)
    assert ok

    src2 = OutputPort(name="out", accepted_types=[Mask])
    tgt2 = InputPort(name="in", accepted_types=[])

    ok2, _ = validate_connection(src2, tgt2)
    assert ok2
