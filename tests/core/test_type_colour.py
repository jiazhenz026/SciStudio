"""Backend-declared type colour (ADR-053 §7.1, FR-049 / FR-050 / FR-052).

``docs/specs/adr-053-personal-tool-library.md`` §2.8, issues #2023 and #2024.
Before this, a type could not influence its own colour: every type colour in
the product was decided frontend-side from a hand-written table plus a hash of
the name, and the one backend hook that existed —
``TypeHierarchyEntry.ui_ring_color`` — was never populated by anything.

Three things are pinned here:

* A type that declares a colour has it collected onto its registry spec, for
  every discovery tier, because the types listing endpoint reads the spec and
  is the single source of type colour for the product (FR-049, FR-050).
* An unusable declaration is dropped with a warning and the type keeps its
  registration (FR-052). This is the case that matters: the declaration lives
  in a hand-edited file in the user's own library, which is an ordinary place
  for a typo, and one typo must not be able to take out the palette.
* A type that declares nothing is byte-identical to before, which is what
  bounds the blast radius of touching ``DataObject`` at all (§14).

The colour is validated here, at collection time, rather than at render time —
one check on the way in, instead of one per consumer on the way out.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import ClassVar

import pytest

from scistudio.core.types.base import DataObject
from scistudio.core.types.registry import TypeRegistry

_REGISTRY_LOGGER = "scistudio.core.types.registry"

DROPIN_TYPE = '''\
from typing import ClassVar

from scistudio.core.types import DataObject


class {class_name}(DataObject):
    """Drop-in type used to pin the ADR-053 colour collection."""

    ui_color: ClassVar[str | None] = "{ui_color}"
'''


def _spec_for(cls: type) -> object:
    """Register *cls* in a fresh registry and hand back its spec."""
    registry = TypeRegistry()
    registry.register_class(cls)
    return registry.resolve(cls.__name__)


# ---------------------------------------------------------------------------
# FR-049 — the declaration exists on the base class
# ---------------------------------------------------------------------------


def test_data_object_declares_both_colour_attributes_defaulting_to_none() -> None:
    """``DataObject`` carries both hooks, unset (FR-049).

    Defaulting to ``None`` is what makes the change additive: every existing
    type inherits "I declare nothing" and renders exactly as it did.
    """
    assert DataObject.ui_color is None
    assert DataObject.ui_ring_color is None


# ---------------------------------------------------------------------------
# FR-050 — the registry collects what the class declared
# ---------------------------------------------------------------------------


def test_declared_colours_reach_the_spec() -> None:
    """A type declaring both colours surfaces both on its spec (FR-050)."""

    class Painted(DataObject):
        """A type with opinions about how it looks."""

        ui_color: ClassVar[str | None] = "#4F8EF7"
        ui_ring_color: ClassVar[str | None] = "#1B4F9C"

    spec = _spec_for(Painted)
    assert spec.ui_color == "#4f8ef7"  # type: ignore[attr-defined]
    assert spec.ui_ring_color == "#1b4f9c"  # type: ignore[attr-defined]


def test_a_fill_without_a_ring_is_allowed() -> None:
    """Declaring only the fill leaves the ring to be derived downstream."""

    class FillOnly(DataObject):
        """A type that names a fill and lets the ring follow."""

        ui_color: ClassVar[str | None] = "#4f8ef7"

    spec = _spec_for(FillOnly)
    assert spec.ui_color == "#4f8ef7"  # type: ignore[attr-defined]
    assert spec.ui_ring_color is None  # type: ignore[attr-defined]


def test_short_hex_forms_are_expanded() -> None:
    """``#f80`` and ``#f80c`` reach consumers as their long equivalents.

    All four CSS hex forms are accepted, and every one of them leaves here as
    ``#rrggbb`` or ``#rrggbbaa`` so no consumer has to parse two shapes.
    """

    class ShortHand(DataObject):
        """A type declared in the short CSS hex form."""

        ui_color: ClassVar[str | None] = "#F80"
        ui_ring_color: ClassVar[str | None] = "#f80c"

    spec = _spec_for(ShortHand)
    assert spec.ui_color == "#ff8800"  # type: ignore[attr-defined]
    assert spec.ui_ring_color == "#ff8800cc"  # type: ignore[attr-defined]


def test_an_undeclared_type_is_unchanged() -> None:
    """A type declaring nothing carries no colour, and the core types do not.

    FR-051's precedence only kicks in when there is something to prefer, so
    "declares nothing" must reach the frontend as null rather than as some
    backend-chosen default that would silently replace today's appearance.
    """
    registry = TypeRegistry()
    registry.scan_builtins()
    for name in ("DataObject", "Array", "Series", "DataFrame", "Text", "Artifact", "CompositeData"):
        spec = registry.resolve(name)
        assert spec.ui_color is None, f"{name} must not acquire a backend colour"
        assert spec.ui_ring_color is None, f"{name} must not acquire a backend ring"


def test_every_pass_records_the_file_and_the_tier_flag() -> None:
    """Built-in specs carry a file path and are not marked as drop-ins.

    The types listing reports ``file_path`` for every tier (FR-026) and reads
    ``is_dropin`` to pick the origin, so a discovery pass that forgot either
    would mis-file its types rather than fail loudly.
    """
    registry = TypeRegistry()
    registry.scan_builtins()
    spec = registry.resolve("Array")
    assert spec.file_path.endswith("array.py")
    assert spec.is_dropin is False
    assert spec.module_path == "scistudio.core.types.array"


# ---------------------------------------------------------------------------
# FR-052 — a bad declaration is dropped, not propagated and not fatal
# ---------------------------------------------------------------------------


def test_invalid_colour_is_ignored_with_a_warning(caplog: pytest.LogCaptureFixture) -> None:
    """A malformed hex string warns, yields ``None``, and still registers."""

    class Malformed(DataObject):
        """A type whose author fat-fingered the colour."""

        ui_color: ClassVar[str | None] = "not-a-colour"

    registry = TypeRegistry()
    with caplog.at_level(logging.WARNING, logger=_REGISTRY_LOGGER):
        registry.register_class(Malformed)

    spec = registry.resolve("Malformed")
    assert spec.ui_color is None
    assert "Malformed" in caplog.text
    assert "not-a-colour" in caplog.text
    # The type itself is still usable — only the colour was refused.
    assert "Malformed" in registry.all_types()


@pytest.mark.parametrize(
    "declared",
    [
        "4f8ef7",  # no leading hash
        "#4f8ef",  # five digits is not a CSS hex form
        "#4f8ef7f",  # seven digits is not either
        "#gggggg",  # right length, not hexadecimal
        "rgb(79, 142, 247)",  # a CSS colour, but not the hex form
        "",  # declared and then left blank
    ],
)
def test_unusable_declarations_all_fall_through(declared: str, caplog: pytest.LogCaptureFixture) -> None:
    """Every shape that is not a CSS hex colour falls through to ``None``."""
    namespace = {"__doc__": "A type with an unusable colour.", "ui_color": declared}
    cls = type("Unusable", (DataObject,), namespace)

    registry = TypeRegistry()
    with caplog.at_level(logging.WARNING, logger=_REGISTRY_LOGGER):
        registry.register_class(cls)

    assert registry.resolve("Unusable").ui_color is None
    assert "Unusable" in caplog.text


def test_a_non_string_declaration_is_ignored(caplog: pytest.LogCaptureFixture) -> None:
    """A number is not a colour, and must not reach the frontend as one."""
    cls = type("NumericColour", (DataObject,), {"__doc__": "A type with a numeric colour.", "ui_color": 0xFF0000})

    registry = TypeRegistry()
    with caplog.at_level(logging.WARNING, logger=_REGISTRY_LOGGER):
        registry.register_class(cls)

    assert registry.resolve("NumericColour").ui_color is None


def test_one_bad_colour_does_not_affect_the_other(caplog: pytest.LogCaptureFixture) -> None:
    """The valid half of a declaration survives the invalid half."""

    class HalfPainted(DataObject):
        """A type with one good colour and one bad one."""

        ui_color: ClassVar[str | None] = "#4f8ef7"
        ui_ring_color: ClassVar[str | None] = "#nope"

    registry = TypeRegistry()
    with caplog.at_level(logging.WARNING, logger=_REGISTRY_LOGGER):
        registry.register_class(HalfPainted)

    spec = registry.resolve("HalfPainted")
    assert spec.ui_color == "#4f8ef7"
    assert spec.ui_ring_color is None


# ---------------------------------------------------------------------------
# FR-050 across the drop-in tier — the one that reaches a user's own file
# ---------------------------------------------------------------------------


def test_a_dropin_type_carries_its_colour_file_and_tier_flag(tmp_path: Path) -> None:
    """A colour declared in a drop-in file arrives on the spec (FR-050).

    The drop-in is also where ``is_dropin`` earns its keep: the file is loaded
    by path under a synthetic module name, which is not an import path, so the
    flag is the only thing that can tell the origin resolver this is a drop-in
    and not a plugin distribution.
    """
    scan_dir = tmp_path / "types"
    scan_dir.mkdir()
    target = scan_dir / "painted_dropin.py"
    target.write_text(DROPIN_TYPE.format(class_name="PaintedDropin", ui_color="#0a7d55"), encoding="utf-8")

    registry = TypeRegistry()
    registry.add_scan_dir(scan_dir)
    registry.scan_all()

    spec = registry.resolve("PaintedDropin")
    assert spec.ui_color == "#0a7d55"
    assert spec.is_dropin is True
    assert Path(spec.file_path) == target
    assert spec.module_path.startswith("_scistudio_type_dropin_")


def test_a_dropin_with_a_broken_colour_still_registers(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """A typo in a user's own type file costs the colour and nothing else."""
    scan_dir = tmp_path / "types"
    scan_dir.mkdir()
    (scan_dir / "broken_colour.py").write_text(
        DROPIN_TYPE.format(class_name="BrokenColour", ui_color="octarine"), encoding="utf-8"
    )

    registry = TypeRegistry()
    registry.add_scan_dir(scan_dir)
    with caplog.at_level(logging.WARNING, logger=_REGISTRY_LOGGER):
        registry.scan_all()

    spec = registry.resolve("BrokenColour")
    assert spec.ui_color is None
    assert spec.is_dropin is True
    assert "octarine" in caplog.text
