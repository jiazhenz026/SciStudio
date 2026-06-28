"""Stability decorators are runtime no-ops; get_stability round-trips (ADR-052 §5).

Spec/ADR §5: the decorators "are no-ops at runtime: each attaches metadata (the
tier and the Since version) to the symbol and returns it unchanged, so they add
no runtime cost and change no behavior." ``get_stability`` is the single read
path and transparently unwraps classmethod/staticmethod/property.

The no-op + round-trip checks exercise the REAL ``scistudio.stability`` module
(present on main) and PASS in isolation. The per-root "representative symbol
carries its tier/Since" check reads the live public surface and is EXPECTED TO
FAIL until #1817 decorates it. Written correct-by-spec.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest
from _spec_data import NON_MARKABLE_PUBLIC_SYMBOLS, ROOTS, expected_symbols, import_root

from scistudio.stability import (
    StabilityInfo,
    get_stability,
    internal,
    provisional,
    stable,
)


def test_decorator_returns_same_object_for_function() -> None:
    def helper(x):
        return x * 2

    decorated = stable(since="0.3.1")(helper)
    assert decorated is helper, "@stable must return the same object (no-op)"
    assert decorated(21) == 42, "@stable must not change behavior"


def test_decorator_returns_same_object_for_class() -> None:
    class Widget:
        pass

    assert provisional(since="0.3.1")(Widget) is Widget, "@provisional must be a no-op"


@pytest.mark.parametrize(
    ("decorator", "tier", "since"),
    [
        (stable(since="0.3.1"), "stable", "0.3.1"),
        (provisional(since="0.3.1"), "provisional", "0.3.1"),
        (internal(), "internal", None),
    ],
)
def test_get_stability_roundtrips_tier_and_since(decorator, tier, since) -> None:
    def sym():
        return None

    info = get_stability(decorator(sym))
    assert isinstance(info, StabilityInfo)
    assert info.tier == tier
    assert info.since == since


def test_get_stability_unwraps_classmethod_staticmethod_property() -> None:
    class Holder:
        @classmethod
        @stable(since="0.3.1")
        def cm(cls):
            return None

        @staticmethod
        @provisional(since="0.3.1")
        def sm():
            return None

        @property
        @stable(since="0.3.1")
        def prop(self):
            return None

    assert get_stability(Holder.__dict__["cm"]).tier == "stable"
    assert get_stability(Holder.__dict__["sm"]).tier == "provisional"
    assert get_stability(Holder.__dict__["prop"]).tier == "stable"


def test_get_stability_none_for_undecorated() -> None:
    def bare():
        return None

    assert get_stability(bare) is None


@pytest.mark.parametrize("root", ROOTS)
def test_representative_symbol_decorated(root: str) -> None:
    """One representative public symbol per root carries its spec tier/Since."""
    module = import_root(root)
    assert module is not None, f"{root} failed to import"

    # Pick a representative that CAN carry a runtime marker: the nine
    # non-markable public symbols (ADR-052 §15) read get_stability() == None by
    # design, so they are not a meaningful "is it decorated?" probe.
    markable = [(n, w) for n, w in expected_symbols(root).items() if (root, n) not in NON_MARKABLE_PUBLIC_SYMBOLS]
    assert markable, f"{root} has no markable representative symbol"
    name, want = markable[0]
    obj = getattr(module, name, None)
    assert obj is not None, f"representative symbol {name} not importable from {root}"
    info = get_stability(obj)
    assert info is not None, f"{root}.{name} is undecorated (ADR-052 §5)"
    assert info.tier == want["tier"], f"{root}.{name} tier {info.tier!r} != {want['tier']!r}"
    assert info.since == want["since"], f"{root}.{name} since {info.since!r} != {want['since']!r}"
