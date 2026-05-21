"""PhysicalQuantity — value + unit dataclass for SciStudio metadata.

Implements ADR-027 D6 (``PhysicalQuantity`` definition and unit tables)
and ADR-027 Addendum 1 §4 (``PhysicalQuantity`` Pydantic v2 integration
via ``__get_pydantic_core_schema__``).

The class supports the small set of physical units SciStudio actually
needs (length, time, frequency, wavenumber). Cross-kind conversions and
comparisons are rejected; same-kind conversions are honoured. Pydantic
v2 integration makes ``pixel_size: PhysicalQuantity`` round-trip
transparently as ``{"value": float, "unit": str}`` inside any
``BaseModel`` without per-field boilerplate.

Out of scope for this module (see ADR-027 D6 §"Out of scope"):

* No ``pint`` integration — this is a deliberate minimalism choice.
* No dimensional algebra (``Q(2.0, "m") + Q(3.0, "mm")``).
* No units beyond the four kinds below.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Unit tables — ADR-027 D6 §"unit tables".
# Each maps a unit string to its scale factor relative to the SI base
# unit of its kind (metres, seconds, hertz, inverse-metres).
# ---------------------------------------------------------------------------
_LENGTH: dict[str, float] = {
    "m": 1.0,
    "mm": 1e-3,
    "um": 1e-6,
    "nm": 1e-9,
    "pm": 1e-12,
    "A": 1e-10,
}
_TIME: dict[str, float] = {
    "s": 1.0,
    "ms": 1e-3,
    "us": 1e-6,
    "ns": 1e-9,
    "min": 60.0,
    "hr": 3600.0,
}
_FREQ: dict[str, float] = {
    "Hz": 1.0,
    "kHz": 1e3,
    "MHz": 1e6,
    "GHz": 1e9,
}
_WAVENUM: dict[str, float] = {
    "cm-1": 100.0,
    "m-1": 1.0,
}

# Derived lookup tables. ``_KIND`` maps each unit string to its kind
# name; ``_SCALE`` merges all unit → scale-factor entries so that a
# single dict lookup gives the conversion factor to the kind's base
# unit.
_KIND: dict[str, str] = {
    **{u: "length" for u in _LENGTH},
    **{u: "time" for u in _TIME},
    **{u: "freq" for u in _FREQ},
    **{u: "wavenumber" for u in _WAVENUM},
}
_SCALE: dict[str, float] = {**_LENGTH, **_TIME, **_FREQ, **_WAVENUM}


@dataclass(frozen=True)
class PhysicalQuantity:
    """A physical quantity: a numeric value paired with a unit string.

    See ADR-027 D6 for the unit alphabet and conversion rules.
    See ADR-027 Addendum 1 §4 for the Pydantic v2 integration contract.

    The dataclass is frozen so that ``Meta`` Pydantic models containing
    ``PhysicalQuantity`` fields remain immutable in spirit (and so that
    ``with_meta(...)`` semantics on ``DataObject`` remain meaningful).

    Examples:
        >>> PhysicalQuantity(0.108, "um").to("nm")
        PhysicalQuantity(value=108.0, unit='nm')
        >>> PhysicalQuantity(108, "nm") == PhysicalQuantity(0.108, "um")
        True
        >>> PhysicalQuantity(1.0, "s") == PhysicalQuantity(1.0, "m")
        False
    """

    value: float
    unit: str

    def __post_init__(self) -> None:
        # ADR-027 D6: validate against ``_SCALE`` at construction time so
        # malformed metadata fails loudly where it is produced, not at
        # the first conversion attempt downstream.
        if self.unit not in _SCALE:
            raise ValueError(f"Unknown unit: {self.unit!r}. Known units: {sorted(_SCALE.keys())}")

    def to(self, target_unit: str) -> PhysicalQuantity:
        """Convert this quantity to ``target_unit`` of the same kind.

        Raises:
            ValueError: if ``target_unit`` is unknown or belongs to a
                different kind.
        """
        if target_unit not in _SCALE:
            raise ValueError(f"Unknown target unit: {target_unit!r}. Known units: {sorted(_SCALE.keys())}")
        if _KIND[self.unit] != _KIND[target_unit]:
            raise ValueError(f"Cannot convert {_KIND[self.unit]} ({self.unit}) to {_KIND[target_unit]} ({target_unit})")
        return PhysicalQuantity(
            value=self.value * _SCALE[self.unit] / _SCALE[target_unit],
            unit=target_unit,
        )

    # ------------------------------------------------------------------
    # Ordering (ADR-027 D6): cross-kind comparisons raise ``TypeError``.
    # Same-kind comparisons are performed on the normalised base value.
    # ------------------------------------------------------------------

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, PhysicalQuantity):
            return NotImplemented
        if _KIND[self.unit] != _KIND[other.unit]:
            raise TypeError(f"Cannot compare {_KIND[self.unit]} to {_KIND[other.unit]}")
        return self.value * _SCALE[self.unit] < other.value * _SCALE[other.unit]

    def __le__(self, other: object) -> bool:
        if not isinstance(other, PhysicalQuantity):
            return NotImplemented
        return self.__lt__(other) or self.__eq__(other)

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, PhysicalQuantity):
            return NotImplemented
        return not self.__le__(other)

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, PhysicalQuantity):
            return NotImplemented
        return not self.__lt__(other)

    # ------------------------------------------------------------------
    # Equality (ADR-027 D6): returns ``NotImplemented`` for non-PQ
    # inputs (letting Python fall back to the other operand); returns
    # ``False`` for cross-kind comparisons (equality is defined for
    # arbitrary pairs of objects and must not raise).
    # ------------------------------------------------------------------

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PhysicalQuantity):
            return NotImplemented
        if _KIND[self.unit] != _KIND[other.unit]:
            return False
        return abs(self.value * _SCALE[self.unit] - other.value * _SCALE[other.unit]) < 1e-12

    def __hash__(self) -> int:
        # ``@dataclass(frozen=True)`` generates a ``__hash__`` based on
        # ``(value, unit)``, but the custom ``__eq__`` above normalises
        # to the base unit so that ``Q(1.0, "m") == Q(1000.0, "mm")``.
        # The two hashes must therefore agree with the custom equality.
        #
        # We hash on ``(round(base_value, 12), kind)``: rounding to 12
        # decimal places matches the ``1e-12`` absolute tolerance used
        # by ``__eq__`` and absorbs the float-multiplication drift that
        # would otherwise split (e.g.) ``Q(0.108, "um")`` from
        # ``Q(108.0, "nm")`` — their raw products
        # (``0.108 * 1e-6`` vs ``108.0 * 1e-9``) differ at the 23rd
        # decimal place but both round to the same 12-decimal bucket.
        # ADR-027 D6 names the canonical case ``Q(1.0, "m") ==
        # Q(1000.0, "mm")``, which is representable exactly and so
        # would hash equal even without the rounding — the rounding is
        # a robustness guarantee for the more general case.
        base = self.value * _SCALE[self.unit]
        return hash((round(base, 12), _KIND[self.unit]))

    # ------------------------------------------------------------------
    # Pydantic v2 integration (ADR-027 Addendum 1 §4). Plugin authors
    # writing ``pixel_size: PhysicalQuantity`` get JSON round-trip for
    # free. The serialised form is ``{"value": float, "unit": str}``.
    # Validation accepts either an existing ``PhysicalQuantity`` or a
    # dict with the two keys.
    # ------------------------------------------------------------------

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: Any) -> Any:
        """Return the Pydantic v2 core schema for ``PhysicalQuantity``.

        See ADR-027 Addendum 1 §4 for the full contract.
        """
        # Imported lazily so importing ``scistudio.core.units`` does not
        # pay the pydantic_core import cost unless Pydantic integration
        # is actually exercised. pydantic_core ships as a transitive
        # dependency of pydantic>=2.0 (pinned in pyproject.toml).
        from pydantic_core import core_schema

        def _validate(v: Any) -> PhysicalQuantity:
            if isinstance(v, PhysicalQuantity):
                return v
            if isinstance(v, dict) and "value" in v and "unit" in v:
                return cls(value=float(v["value"]), unit=str(v["unit"]))
            raise ValueError(
                f"PhysicalQuantity expects {{value, unit}} dict or PhysicalQuantity instance, got {type(v).__name__}"
            )

        return core_schema.no_info_plain_validator_function(
            _validate,
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda obj: {"value": obj.value, "unit": obj.unit},
                return_schema=core_schema.dict_schema(),
            ),
        )
