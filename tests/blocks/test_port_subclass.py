# mypy: ignore-errors
#
# The stub hierarchy below narrows DataObject.save's signature, which mypy
# reads as an incompatible override. CI type-checks src only; the
# pre-commit hook passes changed files explicitly and so bypasses
# pyproject's test excludes (#2115), which is the only reason this file is
# ever checked. The stubs predate this note and are not what any test here
# is about.
"""Regression tests for #437: port type subclass matching via validate_connection."""

from __future__ import annotations

import importlib.util
from pathlib import Path

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


# ---------------------------------------------------------------------------
# #2134 — the same declaration, imported twice
# ---------------------------------------------------------------------------


def _load_twice(source: Path, stem: str) -> tuple[type, type]:
    """Import *source* twice by path, the way two drop-in blocks would.

    Each drop-in import runs inside a window that evicts what it added from
    ``sys.modules`` on exit, so the second block's ``from image import Image``
    re-executes the file and binds a fresh class. This reproduces that without
    depending on the eviction machinery: load the module from its path twice
    under names that do not collide, and take the class out of each.
    """
    loaded: list[type] = []
    for index in (0, 1):
        spec = importlib.util.spec_from_file_location(f"{stem}_{index}", source)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        loaded.append(module.ProjectImage)
    first, second = loaded
    assert first is not second, "the two loads should be distinct class objects"
    return first, second


def test_a_project_type_imported_by_two_blocks_still_connects(tmp_path: Path) -> None:
    """The defect a reader meets: two ports of the same type refuse to connect.

    A project defines a type in ``types/`` and two of its blocks both import
    it. The class objects differ — that is what the drop-in import window
    guarantees — so an identity comparison says the edge is illegal and prints
    the same type name on both sides of the refusal. Nothing the user can act
    on, and it stops any two-block pipeline over a custom type.
    """
    source = tmp_path / "image.py"
    source.write_text(
        "from scistudio.core.types.base import DataObject\n\n\nclass ProjectImage(DataObject):\n    pass\n",
        encoding="utf-8",
    )
    produced, accepted = _load_twice(source, "project_image")

    src = OutputPort(name="labels", accepted_types=[produced])
    tgt = InputPort(name="labels", accepted_types=[accepted])

    ok, reason = validate_connection(src, tgt)
    assert ok, f"same project type on both ports must connect, got: {reason}"


def test_two_different_project_types_still_refuse_to_connect(tmp_path: Path) -> None:
    """The fallback must not make genuinely different types compatible."""
    first = tmp_path / "one.py"
    first.write_text(
        "from scistudio.core.types.base import DataObject\n\n\nclass ProjectImage(DataObject):\n    pass\n",
        encoding="utf-8",
    )
    second = tmp_path / "two.py"
    second.write_text(
        "from scistudio.core.types.base import DataObject\n\n\nclass ProjectTable(DataObject):\n    pass\n",
        encoding="utf-8",
    )
    spec_a = importlib.util.spec_from_file_location("one_mod", first)
    assert spec_a is not None and spec_a.loader is not None
    mod_a = importlib.util.module_from_spec(spec_a)
    spec_a.loader.exec_module(mod_a)
    spec_b = importlib.util.spec_from_file_location("two_mod", second)
    assert spec_b is not None and spec_b.loader is not None
    mod_b = importlib.util.module_from_spec(spec_b)
    spec_b.loader.exec_module(mod_b)

    src = OutputPort(name="out", accepted_types=[mod_a.ProjectImage])
    tgt = InputPort(name="in", accepted_types=[mod_b.ProjectTable])

    ok, reason = validate_connection(src, tgt)
    assert not ok, "two unrelated project types must not connect"
    assert "ProjectImage" in reason and "ProjectTable" in reason
