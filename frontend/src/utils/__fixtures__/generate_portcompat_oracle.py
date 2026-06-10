#!/usr/bin/env python3
"""Generate the port-compat conformance oracle for the frontend (#1548).

DSN-9 (audit #1513 / PR #1514): ``frontend/src/utils/portCompat.ts`` and
``computeEffectivePorts.ts`` hand-mirror
``scistudio.blocks.base.ports.validate_connection`` and the ADR-028 type
hierarchy with no shared test fixture, so the two implementations can
silently drift.

This script is the *single source of truth* for the frontend conformance
fixture. It:

1. Builds a deterministic type hierarchy from the canonical core type
   registry (``TypeRegistry.scan_builtins``) plus a small set of
   synthetic subtypes that exercise multi-level subtype walking. We do
   NOT pull optional monorepo / entry-point plugins (they require extra
   third-party deps such as ``ome_types`` and would make the oracle
   non-deterministic across environments).
2. Enumerates connection attempts (pairs of source/target accepted-type
   lists) and records the verdict produced by the REAL backend
   ``validate_connection``.
3. Emits ``portcompat.oracle.json`` next to this script. That JSON is the
   oracle consumed by ``portCompat.conformance.test.ts`` (vitest).

Regenerate after any change to ``validate_connection`` or the core type
hierarchy::

    python3 frontend/src/utils/__fixtures__/generate_portcompat_oracle.py

The committed JSON must match what this script produces; the vitest
conformance test fails if ``portCompat.ts`` disagrees with the oracle,
and ``test_portcompat_oracle.py`` (pytest) fails if the committed JSON
drifts from the live backend.
"""

from __future__ import annotations

import json
import sys
from itertools import product
from pathlib import Path

# Resolve the repo's ``src`` so the backend is importable without install.
# __file__ = <repo>/frontend/src/utils/__fixtures__/generate_portcompat_oracle.py
#   parents[0]=__fixtures__ [1]=utils [2]=src [3]=frontend [4]=<repo>
_REPO_ROOT = Path(__file__).resolve().parents[4]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from scistudio.blocks.base.ports import (  # noqa: E402
    InputPort,
    OutputPort,
    validate_connection,
)
from scistudio.core.types.array import Array  # noqa: E402
from scistudio.core.types.base import DataObject  # noqa: E402
from scistudio.core.types.dataframe import DataFrame  # noqa: E402
from scistudio.core.types.series import Series  # noqa: E402
from scistudio.core.types.text import Text  # noqa: E402


# --- Synthetic subtypes to exercise multi-level subtype walking ----------
# The core registry only ships base classes (ADR-027 D2 moved domain
# subtypes to plugins). We add deterministic subtypes here so the oracle
# covers the "child is subtype of parent" / "parent is supertype of child"
# branches that real plugin types (Image -> Array, PeakTable -> DataFrame)
# exercise in production.


class ImageLike(Array):
    """Synthetic Array subtype (stands in for plugin Image)."""


class FluorImageLike(ImageLike):
    """Synthetic two-level Array subtype (Image -> Array)."""


class PeakTableLike(DataFrame):
    """Synthetic DataFrame subtype (stands in for plugin PeakTable)."""


# Name -> class. The frontend hierarchy uses these names verbatim.
_TYPES: dict[str, type] = {
    "DataObject": DataObject,
    "Array": Array,
    "Series": Series,
    "DataFrame": DataFrame,
    "Text": Text,
    "ImageLike": ImageLike,
    "FluorImageLike": FluorImageLike,
    "PeakTableLike": PeakTableLike,
}


def _base_name(cls: type) -> str:
    """Immediate registered base name, or '' for DataObject root."""
    for base in cls.__mro__[1:]:
        if base.__name__ in _TYPES:
            return base.__name__
    return ""


def build_type_hierarchy() -> list[dict[str, str]]:
    """Emit the frontend ``TypeHierarchyEntry[]`` shape (name + base_type)."""
    entries: list[dict[str, str]] = []
    for name, cls in _TYPES.items():
        entries.append({"name": name, "base_type": _base_name(cls)})
    return entries


def _verdict(source_types: list[str], target_types: list[str]) -> bool:
    src = OutputPort(name="out", accepted_types=[_TYPES[t] for t in source_types])
    tgt = InputPort(name="in", accepted_types=[_TYPES[t] for t in target_types])
    ok, _reason = validate_connection(src, tgt)
    return ok


def build_cases() -> list[dict[str, object]]:
    """Enumerate single-type and multi-type connection attempts.

    Includes the empty-list ("Any") cases on both sides, all single x
    single combinations, and a few representative multi-type lists.
    """
    names = list(_TYPES.keys())
    cases: list[dict[str, object]] = []

    # Empty (Any) source / target combinations.
    any_combos: list[tuple[list[str], list[str]]] = [
        ([], []),
        ([], ["Array"]),
        (["Array"], []),
        ([], ["FluorImageLike"]),
        (["DataObject"], []),
    ]

    # Single x single across every registered type.
    single_combos = [([a], [b]) for a, b in product(names, names)]

    # A few multi-type lists (variadic / union ports).
    multi_combos: list[tuple[list[str], list[str]]] = [
        (["Array", "Series"], ["Series"]),
        (["Text"], ["Array", "Series"]),
        (["Text"], ["Array", "DataFrame"]),
        (["ImageLike", "Text"], ["FluorImageLike"]),
        (["FluorImageLike"], ["Array", "PeakTableLike"]),
        (["PeakTableLike"], ["Text", "Series"]),
    ]

    for source_types, target_types in (*any_combos, *single_combos, *multi_combos):
        cases.append(
            {
                "source_accepted_types": source_types,
                "target_accepted_types": target_types,
                "expected_compatible": _verdict(source_types, target_types),
            }
        )
    return cases


def main() -> None:
    oracle = {
        "_comment": (
            "Conformance oracle for frontend port-compat (#1548 / DSN-9). "
            "GENERATED by generate_portcompat_oracle.py from the backend "
            "scistudio.blocks.base.ports.validate_connection. Do not hand-edit; "
            "regenerate via the script and re-run the pytest + vitest "
            "conformance suites."
        ),
        "source": "scistudio.blocks.base.ports.validate_connection",
        "type_hierarchy": build_type_hierarchy(),
        "cases": build_cases(),
    }
    out_path = Path(__file__).resolve().parent / "portcompat.oracle.json"
    out_path.write_text(json.dumps(oracle, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(oracle['cases'])} cases to {out_path}")


if __name__ == "__main__":
    main()
