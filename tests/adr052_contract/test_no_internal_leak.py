"""No internal/undecorated symbol leaks into any canonical root ``__all__``.

Spec: ADR-052 §2/§5 (only stable|provisional symbols are public); spec §3.9,
§4.3-§4.6, §4.8, §6.3/§6.5, §8.1/§8.2 (the explicit demotions).

Two guarantees:
  1. Every name in a root's live ``__all__`` resolves to a symbol decorated
     stable|provisional -- never @internal, never undecorated.
  2. The spec-named demoted symbols are absent from their root's ``__all__``.

EXPECTED TO FAIL in the pre-implementation tree: the demoted symbols
(TypeRegistry/TypeSpec, Port + 4 port helpers, BlockState/BlockResult, the
interactive internals, LoadData/SaveData, normalize_*, the 7 previewer-model
internals, the DEFAULT_MAX_* constants) are still exported, and live symbols are
not yet decorated. Written correct-by-spec, not weakened to pass.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest
from _spec_data import DEMOTIONS, NON_MARKABLE_PUBLIC_SYMBOLS, ROOTS, import_root, module_all

from scistudio.stability import get_stability

_PUBLIC_TIERS = {"stable", "provisional"}


@pytest.mark.parametrize("root", ROOTS)
def test_no_internal_or_undecorated_in_all(root: str) -> None:
    """No ``__all__`` member is @internal or undecorated (ADR-052 §2/§5)."""
    module = import_root(root)
    assert module is not None, f"canonical public root {root!r} failed to import"

    offenders: list[str] = []
    for name in sorted(module_all(module)):
        obj = getattr(module, name, None)
        if obj is None:
            offenders.append(f"{name}: in __all__ but not resolvable on the module")
            continue
        if (root, name) in NON_MARKABLE_PUBLIC_SYMBOLS:
            # Non-markable public symbol (ADR-052 §15): a constant / type-alias
            # that cannot carry a runtime marker — NOT an undecorated/internal
            # leak. Its public tier is pinned by the expected fixture.
            continue
        info = get_stability(obj)
        if info is None:
            offenders.append(f"{name}: undecorated (no stability tier)")
        elif info.tier not in _PUBLIC_TIERS:
            offenders.append(f"{name}: tier {info.tier!r} is not public")

    assert not offenders, f"{root}: __all__ contains internal/undecorated members:\n  " + "\n  ".join(offenders)


@pytest.mark.parametrize("root", sorted(DEMOTIONS))
def test_demoted_symbols_absent_from_all(root: str) -> None:
    """The spec-demoted symbols must not appear in the root's ``__all__``."""
    module = import_root(root)
    assert module is not None, f"canonical public root {root!r} failed to import"

    live = module_all(module)
    leaked = [name for name in DEMOTIONS[root] if name in live]
    assert not leaked, f"{root}: demoted-to-internal symbols still in __all__ (must be dropped in #1817): {leaked}"
