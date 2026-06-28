"""ADR-052 §5 stability decoration — API-surface usage check.

This is the *surface-level* companion to ``tests/stability/test_stability.py``.
That file unit-tests the decorator mechanism in isolation (no-op behaviour,
metadata attach/read, classmethod/staticmethod/property unwrapping). This file
asserts the mechanism is correctly *applied across the real public surface*:

* every symbol in every canonical root's ``__all__`` carries a readable
  ``StabilityInfo`` whose ``tier`` is ``stable`` or ``provisional`` (never
  ``internal``) and whose ``Since`` is the ``0.3.1`` baseline (ADR-052 §2.3);
* the markers remain runtime no-ops on the live surface — a decorated public
  class is still instantiable / a decorated function still callable;
* representative per-root reads return the tier the contract assigns.

It does not re-test the pure decorator mechanism (that is the stability unit
test) and it does not re-freeze the exact name set (that is
``test_public_surface.py``). Like the freeze test, parts fail until #1817
decorates the surface; that is expected.
"""

from __future__ import annotations

import importlib

import pytest

from scistudio.stability import StabilityInfo, get_stability

CANONICAL_ROOTS: tuple[str, ...] = (
    "scistudio.core.types",
    "scistudio.core.meta",
    "scistudio.blocks.base",
    "scistudio.blocks.process",
    "scistudio.blocks.io",
    "scistudio.blocks.app",
    "scistudio.blocks.code",
    "scistudio.previewers.models",
    "scistudio.previewers.data_access",
)

_BASELINE_SINCE = "0.3.1"
_PUBLIC_TIERS = {"stable", "provisional"}


def _public_symbols(root: str) -> list[tuple[str, object]]:
    module = importlib.import_module(root)
    return [(name, getattr(module, name)) for name in sorted(getattr(module, "__all__", []))]


@pytest.mark.parametrize("root", CANONICAL_ROOTS)
def test_every_public_symbol_carries_a_public_tier_and_baseline_since(root: str) -> None:
    """Each ``__all__`` symbol reads back a public tier + the 0.3.1 baseline Since."""
    bad: list[str] = []
    for name, obj in _public_symbols(root):
        info = get_stability(obj)
        if info is None:
            bad.append(f"{name}: no @stable/@provisional marker")
            continue
        if info.tier not in _PUBLIC_TIERS:
            bad.append(f"{name}: tier={info.tier!r} (must be stable/provisional)")
        if info.since != _BASELINE_SINCE:
            bad.append(f"{name}: since={info.since!r} (baseline must be {_BASELINE_SINCE!r})")
    assert not bad, f"{root} stability decoration problems (ADR-052 §5):\n  " + "\n  ".join(bad)


def test_get_stability_returns_stability_info_instances() -> None:
    """A spot-check that the surface really yields ``StabilityInfo`` objects."""
    from scistudio.core.types import DataObject

    info = get_stability(DataObject)
    assert isinstance(info, StabilityInfo), "DataObject must be decorated with a stability marker (§5)"
    assert info.tier == "stable"
    assert info.since == _BASELINE_SINCE


def test_representative_tiers_match_the_contract() -> None:
    """Representative per-root reads return the tier the spec assigns."""
    cases = [
        # (root, symbol, expected tier) — one stable + one provisional family.
        ("scistudio.core.types", "Array", "stable"),
        ("scistudio.core.meta", "FrameworkMeta", "stable"),
        ("scistudio.blocks.base", "Block", "stable"),
        ("scistudio.blocks.base", "PackageOtaSource", "provisional"),
        ("scistudio.blocks.process", "ProcessBlock", "stable"),
        ("scistudio.blocks.io", "IOBlock", "stable"),
        ("scistudio.blocks.app", "AppBlock", "provisional"),
        ("scistudio.blocks.code", "CodeBlock", "provisional"),
        ("scistudio.previewers.models", "PreviewerSpec", "provisional"),
        ("scistudio.previewers.data_access", "PreviewDataAccess", "provisional"),
    ]
    wrong: list[str] = []
    for root, symbol, expected_tier in cases:
        module = importlib.import_module(root)
        info = get_stability(getattr(module, symbol))
        actual = None if info is None else info.tier
        if actual != expected_tier:
            wrong.append(f"{root}.{symbol}: expected {expected_tier!r}, got {actual!r}")
    assert not wrong, "contract tier mismatches (ADR-052 §5):\n  " + "\n  ".join(wrong)


def test_decorators_are_no_ops_on_the_live_surface() -> None:
    """The markers change no behaviour: decorated public symbols still work."""
    from scistudio.core.types import Array, DataObject

    # Still a class, still instantiable (the decorator returns the same object).
    assert isinstance(DataObject(), DataObject)
    arr = Array(axes=["y", "x"], shape=(2, 2), dtype="uint8")
    assert arr.axes == ["y", "x"]
