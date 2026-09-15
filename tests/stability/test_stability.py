"""Tests for :mod:`scistudio.stability` (ADR-052 §5 stability decorators)."""

from __future__ import annotations

from scistudio import stability
from scistudio.stability import (
    DeprecationInfo,
    StabilityInfo,
    deprecated,
    get_deprecation,
    get_stability,
    internal,
    provisional,
    stable,
)


def test_stable_stamps_tier_and_since() -> None:
    @stable(since="0.3.1")
    def f() -> int:
        return 1

    assert get_stability(f) == StabilityInfo(tier="stable", since="0.3.1")
    # no-op at runtime: the symbol is returned unchanged and still works.
    assert f() == 1


def test_provisional_and_internal_tiers() -> None:
    @provisional(since="0.3.1")
    def g() -> None: ...

    @internal()
    def h() -> None: ...

    assert get_stability(g) == StabilityInfo(tier="provisional", since="0.3.1")
    assert get_stability(h) == StabilityInfo(tier="internal", since=None)


def test_internal_accepts_explicit_since() -> None:
    @internal(since="0.3.1")
    def f() -> None: ...

    assert get_stability(f) == StabilityInfo(tier="internal", since="0.3.1")


def test_decorates_class() -> None:
    @stable(since="0.3.1")
    class C:
        pass

    assert get_stability(C) == StabilityInfo(tier="stable", since="0.3.1")
    assert isinstance(C(), C)  # still instantiable, unchanged


def test_classmethod_marker_readable() -> None:
    # Recommended order: @classmethod outermost, marker on the raw function.
    class C:
        @classmethod
        @stable(since="0.1.0")
        def make(cls) -> str:
            return "ok"

    assert get_stability(C.make) == StabilityInfo(tier="stable", since="0.1.0")
    assert C.make() == "ok"


def test_marker_outside_classmethod_also_works() -> None:
    # Reverse order: marker receives the classmethod object and unwraps it.
    class C:
        @stable(since="0.1.0")
        @classmethod
        def make(cls) -> str:
            return "ok"

    assert get_stability(C.make) == StabilityInfo(tier="stable", since="0.1.0")
    assert C.make() == "ok"


def test_staticmethod_marker_readable() -> None:
    class C:
        @staticmethod
        @provisional(since="0.1.0")
        def helper() -> int:
            return 2

    assert get_stability(C.helper) == StabilityInfo(tier="provisional", since="0.1.0")
    assert C.helper() == 2


def test_property_marker_readable() -> None:
    # Normal order: @property outermost, marker on the getter (fget). This is
    # how #1817 will decorate public properties like DataObject.framework.
    class C:
        @property
        @stable(since="0.3.1")
        def framework(self) -> str:
            return "core"

    assert get_stability(C.framework) == StabilityInfo(tier="stable", since="0.3.1")
    assert C().framework == "core"  # property still works


def test_property_setter_marker_readable() -> None:
    # Marker on the setter only — get_stability falls back fget -> fset -> fdel.
    class C:
        _v = 0

        @property
        def x(self) -> int:
            return self._v

        @x.setter
        @stable(since="0.3.1")
        def x(self, value: int) -> None:
            self._v = value

    assert get_stability(C.x) == StabilityInfo(tier="stable", since="0.3.1")
    obj = C()
    obj.x = 7
    assert obj.x == 7  # setter still works


def test_decorator_returns_same_object_identity() -> None:
    def f() -> None: ...

    assert stable(since="0.3.1")(f) is f


def test_get_stability_none_for_undecorated() -> None:
    def plain() -> None: ...

    assert get_stability(plain) is None
    assert get_stability(object()) is None
    assert get_stability(42) is None


def test_public_exports() -> None:
    assert set(stability.__all__) == {
        "DeprecationInfo",
        "StabilityInfo",
        "Tier",
        "deprecated",
        "get_deprecation",
        "get_stability",
        "internal",
        "provisional",
        "stable",
    }


_DEPRECATION = {"since": "0.3.5", "removed_in": "0.6.0", "replacement": "the new thing"}


def test_deprecated_composes_with_tier_in_either_order() -> None:
    @deprecated(**_DEPRECATION)
    @provisional(since="0.3.1")
    def outer() -> int:
        return 1

    @provisional(since="0.3.1")
    @deprecated(**_DEPRECATION)
    def inner() -> int:
        return 2

    for symbol in (outer, inner):
        assert get_deprecation(symbol) == DeprecationInfo(**_DEPRECATION)
        # Deprecation does not change the tier (ADR-052 §5).
        assert get_stability(symbol) == StabilityInfo(tier="provisional", since="0.3.1")
    assert outer() == 1
    assert inner() == 2


def test_deprecated_is_a_silent_no_op(recwarn: object) -> None:
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("error")

        @deprecated(**_DEPRECATION)
        class C:
            pass

        assert isinstance(C(), C)
    assert deprecated(**_DEPRECATION)(C) is C


def test_deprecated_unwraps_methods_and_properties() -> None:
    class C:
        @classmethod
        @deprecated(**_DEPRECATION)
        def make(cls) -> str:
            return "ok"

        @deprecated(**_DEPRECATION)
        @staticmethod
        def helper() -> int:
            return 2

        @property
        @deprecated(**_DEPRECATION)
        def value(self) -> int:
            return 3

    assert get_deprecation(C.make) == DeprecationInfo(**_DEPRECATION)
    assert get_deprecation(C.helper) == DeprecationInfo(**_DEPRECATION)
    assert get_deprecation(C.value) == DeprecationInfo(**_DEPRECATION)
    assert (C.make(), C.helper(), C().value) == ("ok", 2, 3)


def test_deprecation_is_not_inherited_by_subclasses() -> None:
    @deprecated(**_DEPRECATION)
    class Base:
        pass

    class Child(Base):
        pass

    assert get_deprecation(Base) is not None
    assert get_deprecation(Child) is None


def test_module_wide_deprecation() -> None:
    import types

    module = types.ModuleType("fake_root")
    module.CONSTANT = "1"  # type: ignore[attr-defined]
    deprecated(**_DEPRECATION)(module)

    assert get_deprecation(module) == DeprecationInfo(**_DEPRECATION)
    # A symbol does not inherit its module's marker through get_deprecation.
    assert get_deprecation(module.CONSTANT) is None  # type: ignore[attr-defined]


def test_get_deprecation_none_for_unmarked() -> None:
    @stable(since="0.3.1")
    def f() -> None: ...

    assert get_deprecation(f) is None
    assert get_deprecation(object()) is None
