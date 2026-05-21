"""Tests for ``scistudio.core.units.PhysicalQuantity``.

Covers ADR-027 D6 (dataclass contract, unit tables, conversion,
comparison, equality, hash) and ADR-027 Addendum 1 §4 (Pydantic v2
round-trip contract).

See ``docs/specs/phase10-implementation-standards.md`` T-003 §e for the
enumerated list of required tests.
"""

from __future__ import annotations

import dataclasses

import pytest
from pydantic import BaseModel, ValidationError

from scistudio.core.units import PhysicalQuantity

# ---------------------------------------------------------------------------
# Construction & validation (ADR-027 D6 §"unit tables").
# ---------------------------------------------------------------------------


def test_construction_valid_unit() -> None:
    """Known units build cleanly and round-trip through the dataclass."""
    q = PhysicalQuantity(value=0.108, unit="um")
    assert q.value == pytest.approx(0.108)
    assert q.unit == "um"


def test_construction_invalid_unit_raises() -> None:
    """Unknown units are rejected at construction time."""
    with pytest.raises(ValueError, match="Unknown unit"):
        PhysicalQuantity(value=1.0, unit="xyz")


# ---------------------------------------------------------------------------
# Conversion via ``.to()`` (ADR-027 D6 §"conversion").
# ---------------------------------------------------------------------------


def test_to_within_kind_length() -> None:
    """``0.108 um`` converts to ``108 nm`` within length."""
    q_um = PhysicalQuantity(0.108, "um")
    q_nm = q_um.to("nm")
    assert q_nm.unit == "nm"
    assert q_nm.value == pytest.approx(108.0)
    # And the two compare equal (see __eq__ tests below).
    assert q_nm == PhysicalQuantity(108.0, "nm")


def test_to_within_kind_time() -> None:
    """``1 min`` converts to ``60 s``."""
    q = PhysicalQuantity(1.0, "min").to("s")
    assert q.unit == "s"
    assert q.value == pytest.approx(60.0)


def test_to_invalid_target_raises() -> None:
    """Unknown target units raise before any conversion logic runs."""
    with pytest.raises(ValueError, match="Unknown target unit"):
        PhysicalQuantity(0.108, "um").to("xyz")


def test_to_cross_kind_raises() -> None:
    """Cross-kind conversions raise ``ValueError``."""
    with pytest.raises(ValueError, match="Cannot convert"):
        PhysicalQuantity(1.0, "s").to("m")


# ---------------------------------------------------------------------------
# Ordering (ADR-027 D6 §"comparison").
# ---------------------------------------------------------------------------


def test_lt_within_kind() -> None:
    """Ordering normalises to the common base unit."""
    assert PhysicalQuantity(108, "nm") < PhysicalQuantity(0.2, "um")


def test_lt_cross_kind_raises() -> None:
    """Cross-kind ``<`` raises ``TypeError`` — ordering is not defined."""
    with pytest.raises(TypeError, match="Cannot compare"):
        _ = PhysicalQuantity(1.0, "s") < PhysicalQuantity(1.0, "m")


def test_comparison_suite_consistent() -> None:
    """``<``, ``<=``, ``>``, ``>=`` agree for same-kind quantities."""
    small = PhysicalQuantity(100, "nm")
    big = PhysicalQuantity(0.2, "um")
    same = PhysicalQuantity(0.1, "um")

    assert small < big
    assert small <= big
    assert big > small
    assert big >= small
    # Same-value different-unit — le/ge but not lt/gt.
    assert small <= same
    assert small >= same
    assert not (small < same)
    assert not (small > same)


# ---------------------------------------------------------------------------
# Equality (ADR-027 D6 §"comparison").
# ---------------------------------------------------------------------------


def test_eq_within_kind() -> None:
    """``0.108 um == 108 nm`` after base-unit normalisation."""
    assert PhysicalQuantity(0.108, "um") == PhysicalQuantity(108.0, "nm")


def test_eq_cross_kind_false() -> None:
    """Cross-kind equality returns ``False`` — it must not raise."""
    # Equality is defined for any pair of objects; never raising.
    # Use the dunder directly to bypass ruff's ``!=`` simplification and
    # pin the semantics of ``__eq__`` specifically (not ``__ne__``).
    q_s = PhysicalQuantity(1.0, "s")
    q_m = PhysicalQuantity(1.0, "m")
    assert q_s.__eq__(q_m) is False


def test_eq_with_non_quantity_returns_notimplemented() -> None:
    """Non-PQ inputs yield ``NotImplemented`` (Python turns into ``False``)."""
    q = PhysicalQuantity(1.0, "s")
    # The __eq__ dunder returns NotImplemented; Python falls back to the
    # default object-identity check, which yields False.
    assert (q == "string") is False
    assert (q == 1.0) is False
    assert (q == None) is False  # noqa: E711 — testing __eq__ semantics
    # Direct dunder inspection proves NotImplemented is returned.
    assert q.__eq__("string") is NotImplemented


# ---------------------------------------------------------------------------
# Hashing (ADR-027 D6 §"comparison" + addendum note in standards doc).
# ---------------------------------------------------------------------------


def test_hash_equal_quantities_equal_hashes() -> None:
    """``__hash__`` is consistent with the custom ``__eq__``."""
    q1 = PhysicalQuantity(0.108, "um")
    q2 = PhysicalQuantity(108.0, "nm")
    assert q1 == q2
    assert hash(q1) == hash(q2)

    # A meter-based length and a millimetre-based length also hash
    # equal if they are equal — the ADR names this case explicitly.
    assert PhysicalQuantity(1.0, "m") == PhysicalQuantity(1000.0, "mm")
    assert hash(PhysicalQuantity(1.0, "m")) == hash(PhysicalQuantity(1000.0, "mm"))


def test_hash_usable_in_sets_and_dicts() -> None:
    """Equal quantities collapse in sets/dicts even across units."""
    s: set[PhysicalQuantity] = {
        PhysicalQuantity(0.108, "um"),
        PhysicalQuantity(108.0, "nm"),
    }
    assert len(s) == 1


# ---------------------------------------------------------------------------
# Immutability (frozen dataclass).
# ---------------------------------------------------------------------------


def test_immutability_frozen() -> None:
    """Frozen dataclass forbids attribute assignment after construction."""
    q = PhysicalQuantity(1.0, "m")
    with pytest.raises(dataclasses.FrozenInstanceError):
        q.value = 2.0  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        q.unit = "mm"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Pydantic v2 integration (ADR-027 Addendum 1 §4).
# ---------------------------------------------------------------------------


class _SampleModel(BaseModel):
    """Inline Pydantic model used by the Pydantic integration tests.

    Mirrors the plugin-author pattern documented in ADR-027 Addendum 1
    §4: ``pixel_size: PhysicalQuantity`` declared directly as a field,
    no custom validators or serializers required.
    """

    pixel_size: PhysicalQuantity


def test_pydantic_round_trip() -> None:
    """``model_dump_json`` → ``model_validate_json`` round-trips cleanly."""
    original = _SampleModel(pixel_size=PhysicalQuantity(0.108, "um"))
    payload = original.model_dump_json()
    restored = _SampleModel.model_validate_json(payload)
    assert restored.pixel_size == original.pixel_size
    assert isinstance(restored.pixel_size, PhysicalQuantity)


def test_pydantic_dump_format() -> None:
    """Dumped shape is exactly ``{"value": ..., "unit": ...}``."""
    model = _SampleModel(pixel_size=PhysicalQuantity(0.108, "um"))
    dumped = model.model_dump()
    assert dumped == {"pixel_size": {"value": 0.108, "unit": "um"}}

    # JSON mode yields the same structure (value + unit dict).
    dumped_json_mode = model.model_dump(mode="json")
    assert dumped_json_mode == {"pixel_size": {"value": 0.108, "unit": "um"}}


def test_pydantic_validate_from_dict() -> None:
    """A raw ``{"value", "unit"}`` dict is accepted at validate time."""
    model = _SampleModel.model_validate({"pixel_size": {"value": 0.108, "unit": "um"}})
    assert isinstance(model.pixel_size, PhysicalQuantity)
    assert model.pixel_size == PhysicalQuantity(0.108, "um")


def test_pydantic_validate_from_instance() -> None:
    """An existing ``PhysicalQuantity`` instance is accepted as-is."""
    pq = PhysicalQuantity(0.108, "um")
    model = _SampleModel.model_validate({"pixel_size": pq})
    assert isinstance(model.pixel_size, PhysicalQuantity)
    assert model.pixel_size is pq or model.pixel_size == pq


def test_pydantic_validate_invalid_raises() -> None:
    """Garbage values raise ``ValidationError`` with a useful message."""
    with pytest.raises(ValidationError):
        _SampleModel.model_validate({"pixel_size": "not a dict"})
    with pytest.raises(ValidationError):
        _SampleModel.model_validate({"pixel_size": 42})


def test_pydantic_validate_rejects_unknown_unit() -> None:
    """Invalid unit strings propagate as ``ValidationError`` at parse time."""
    with pytest.raises(ValidationError):
        _SampleModel.model_validate({"pixel_size": {"value": 1.0, "unit": "xyz"}})
