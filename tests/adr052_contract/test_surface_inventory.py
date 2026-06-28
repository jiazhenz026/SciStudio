"""Per-root surface inventory vs the committed independent expected surface.

Spec: docs/specs/adr-052-public-api-surface.md §3-§8 (+ each "Net __all__
change" note); ADR-052 §2 (public = canonical-root ``__all__`` membership), §5
(tier + Since).

For each of the nine canonical roots, this asserts the live ``__all__`` matches
``expected_surface.json`` and that every symbol's stability tier + Since match.
Roots in "exact" mode require set equality (count + names); roots in "subset"
mode (blocks.code, previewers.models -- owner-deferred / count-discrepant per the
JSON ``ambiguity`` note) require every expected symbol present with the right
tier, tolerating extra live exports.

EXPECTED TO FAIL in the pre-implementation tree: the live ``__all__`` still
carries the old surface and the symbols are not yet decorated, so both the set
comparison and the tier/Since reads fail. The assertions are written
correct-by-spec and are not weakened to pass here.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest

from _spec_data import ROOTS, expected_symbols, root_mode
from conftest import import_root, module_all

from scistudio.stability import get_stability


@pytest.mark.parametrize("root", ROOTS)
def test_all_is_declared(root: str) -> None:
    """Every canonical root declares an explicit ``__all__`` (ADR-052 §2)."""
    module = import_root(root)
    assert module is not None, f"canonical public root {root!r} failed to import"
    assert hasattr(module, "__all__"), f"{root} must declare an explicit __all__ (ADR-052 §2)"


@pytest.mark.parametrize("root", ROOTS)
def test_surface_membership(root: str) -> None:
    """Live ``__all__`` matches the spec-derived expected set for ``root``."""
    module = import_root(root)
    assert module is not None, f"canonical public root {root!r} failed to import"

    live = module_all(module)
    expected = set(expected_symbols(root))
    mode = root_mode(root)

    missing = expected - live
    assert not missing, (
        f"{root}: spec-public symbols absent from live __all__: {sorted(missing)}"
    )

    if mode == "exact":
        extra = live - expected
        assert not extra, (
            f"{root}: live __all__ carries symbols not in the spec contract "
            f"(should be demoted/internal or never exported): {sorted(extra)}"
        )
    else:
        # subset mode: extras tolerated (spec defers exhaustive set); the
        # no-internal-leak test still forbids the named demotions + internals.
        assert mode == "subset", f"unknown mode {mode!r} for {root}"


@pytest.mark.parametrize("root", ROOTS)
def test_symbol_tiers_and_since(root: str) -> None:
    """Each expected public symbol carries its spec tier + Since=0.3.1."""
    module = import_root(root)
    assert module is not None, f"canonical public root {root!r} failed to import"

    failures: list[str] = []
    for name, want in expected_symbols(root).items():
        obj = getattr(module, name, None)
        if obj is None:
            failures.append(f"{name}: not importable from {root}")
            continue
        info = get_stability(obj)
        if info is None:
            failures.append(f"{name}: undecorated (no @stable/@provisional)")
            continue
        if info.tier != want["tier"]:
            failures.append(f"{name}: tier {info.tier!r} != expected {want['tier']!r}")
        if info.since != want["since"]:
            failures.append(f"{name}: since {info.since!r} != expected {want['since']!r}")

    assert not failures, f"{root} tier/Since mismatches:\n  " + "\n  ".join(failures)
