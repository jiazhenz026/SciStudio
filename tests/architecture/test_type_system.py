"""Architecture enforcement: type system invariants.

Validates structural properties of the ``scistudio.core.types`` hierarchy
that survived ADR-027 D2:

* Every public base class in the type modules inherits from
  :class:`DataObject`.
* No base class is descended from more than one base-type family.
* :class:`Array` subclasses CAN tighten their ``required_axes`` /
  ``allowed_axes`` schema (ADR-027 D1).
* :class:`CompositeData` subclasses CAN declare ``expected_slots``
  (the ADR-027 D2 plugin extension hook).

ADR-027 D2 removed all domain subclasses (``Image``, ``FluorImage``,
``SRSImage``, ``MSImage``, ``Spectrum``, ``RamanSpectrum``,
``MassSpectrum``, ``PeakTable``, ``MetabPeakTable``, ``AnnData``,
``SpatialData``) from core; they now live in plugin packages.  This
module therefore tests:

1. The seven remaining base types (``Array``, ``Series``, ``DataFrame``,
   ``Text``, ``Artifact``, ``CompositeData``, plus ``Collection``).
2. Local fixture subclasses, which exercise the schema-declaration
   mechanism without depending on any specific plugin.
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from scistudio.core.types.array import Array
from scistudio.core.types.artifact import Artifact
from scistudio.core.types.base import DataObject, TypeSignature
from scistudio.core.types.composite import CompositeData
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.series import Series
from scistudio.core.types.text import Text

# ---------------------------------------------------------------------------
# Local fixture subclasses.
#
# These exercise the schema-declaration capability that ADR-027 D1 / D2
# preserves on Array and CompositeData. They are intentionally minimal
# and live entirely within this test module — the architecture test
# does not depend on the scistudio-blocks-imaging plugin (or any other
# plugin) being installed.
# ---------------------------------------------------------------------------


class _ImageFixture(Array):
    """Local Array subclass that tightens ``required_axes``."""

    required_axes: ClassVar[frozenset[str]] = frozenset({"y", "x"})
    allowed_axes: ClassVar[frozenset[str] | None] = frozenset({"t", "z", "c", "lambda", "y", "x"})
    canonical_order: ClassVar[tuple[str, ...]] = ("t", "z", "c", "lambda", "y", "x")


class _AnnDataFixture(CompositeData):
    """Local CompositeData subclass that declares ``expected_slots``."""

    expected_slots: ClassVar[dict[str, type]] = {
        "X": Array,
        "obs": DataFrame,
        "var": DataFrame,
        "uns": Artifact,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# The seven remaining public base types after ADR-027 D2.
BASE_TYPE_CLASSES: list[type] = [
    Array,
    Series,
    DataFrame,
    Text,
    Artifact,
    CompositeData,
]

# The "base-type families" — direct children of DataObject. No class
# should inherit from more than one of these along an unrelated branch.
BASE_TYPE_FAMILIES: list[type] = [
    Array,
    Series,
    DataFrame,
    Text,
    Artifact,
    CompositeData,
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cls",
    BASE_TYPE_CLASSES,
    ids=[c.__name__ for c in BASE_TYPE_CLASSES],
)
def test_base_type_inherits_from_dataobject(cls: type) -> None:
    """Every public base type class inherits from DataObject."""
    assert issubclass(cls, DataObject), f"{cls.__name__} does not inherit from DataObject"


def test_no_multi_base_type_inheritance() -> None:
    """No base type inherits from more than one base-type family."""
    for cls in BASE_TYPE_CLASSES:
        inherited_families = [family for family in BASE_TYPE_FAMILIES if issubclass(cls, family)]
        # A class may match itself; the families it does match must
        # form a single inheritance line.
        for i, fam_a in enumerate(inherited_families):
            for fam_b in inherited_families[i + 1 :]:
                assert issubclass(fam_a, fam_b) or issubclass(fam_b, fam_a), (
                    f"{cls.__name__} inherits from unrelated base families {fam_a.__name__} and {fam_b.__name__}"
                )


# ---------------------------------------------------------------------------
# ADR-027 D1: Array subclasses can tighten the axis schema.
# ---------------------------------------------------------------------------


def test_array_base_has_permissive_schema() -> None:
    """Plain ``Array`` accepts any axes (no required, no allowed bound)."""
    assert Array.required_axes == frozenset()
    assert Array.allowed_axes is None
    # An Array with arbitrary axes can be constructed without error.
    obj = Array(axes=["y", "x"], shape=(2, 2))
    assert obj.axes == ["y", "x"]


def test_array_subclass_can_declare_required_axes() -> None:
    """An Array subclass that declares ``required_axes`` enforces them."""
    assert _ImageFixture.required_axes == frozenset({"y", "x"})
    # Constructing with the required axes succeeds.
    img = _ImageFixture(axes=["y", "x"], shape=(8, 8))
    assert img.required_axes == frozenset({"y", "x"})

    # Missing a required axis raises ValueError per ADR-027 D1.
    with pytest.raises(ValueError, match="requires axes"):
        _ImageFixture(axes=["x"], shape=(8,))


def test_array_subclass_can_declare_allowed_axes() -> None:
    """An Array subclass with ``allowed_axes`` rejects axes outside that set."""
    # Within the allowed set is OK.
    img = _ImageFixture(axes=["c", "y", "x"], shape=(3, 8, 8))
    assert "c" in img.axes

    # An axis name not in the allowed set raises.
    with pytest.raises(ValueError, match="accepts only"):
        _ImageFixture(axes=["mz", "y", "x"], shape=(10, 8, 8))


# ---------------------------------------------------------------------------
# ADR-027 D2: CompositeData subclasses can declare expected_slots.
# ---------------------------------------------------------------------------


def test_composite_base_has_no_expected_slots() -> None:
    """Plain ``CompositeData`` declares no expected_slots."""
    # Either {} or None — both are valid permissive defaults.
    slots = getattr(CompositeData, "expected_slots", {}) or {}
    assert isinstance(slots, dict)
    assert len(slots) == 0


def test_composite_subclass_can_declare_expected_slots() -> None:
    """A CompositeData subclass can declare expected_slots typed by base classes."""
    slots = _AnnDataFixture.expected_slots
    assert slots is not None
    assert isinstance(slots, dict)
    assert len(slots) > 0
    # Every slot type is a DataObject subclass.
    for slot_name, slot_type in slots.items():
        assert issubclass(slot_type, DataObject), (
            f"_AnnDataFixture.expected_slots['{slot_name}'] = {slot_type.__name__} which is not a DataObject subclass"
        )


# ---------------------------------------------------------------------------
# TypeSignature is a metadata descriptor, not a DataObject.
# ---------------------------------------------------------------------------


def test_type_signature_is_not_a_dataobject() -> None:
    """TypeSignature is a metadata descriptor, not a DataObject."""
    assert not issubclass(TypeSignature, DataObject)
