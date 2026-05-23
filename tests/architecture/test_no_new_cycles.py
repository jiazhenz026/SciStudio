"""Architecture enforcement: import-cycle regression guard (#1482).

Issue #1482 broke four small import cycles to drop sentrux's
``max_cycles`` violation from 6 down to 2. This test holds the line:
it walks every ``.py`` file under ``src/scistudio``, builds the
runtime-import graph (TYPE_CHECKING edges excluded — they have no
runtime effect), and asserts the number of strongly-connected
components with size > 1 (i.e. import cycles) does not exceed the
post-#1482 baseline.

The baseline is intentionally loose:

* The two cycles left after #1482 (``core/storage`` ↔ ``core/types``
  tracked by #1342, and the larger ``mcp + blocks/*`` SCC tracked by
  #1336) are still present, so the threshold is set to allow them.
* Any **new** cycle introduced by a future change trips this guard
  and forces the author to either remove the cycle or argue for a
  threshold bump in the PR review.

Sentrux is the canonical guard in CI (``.sentrux/rules.toml``
``max_cycles=5``), but it pins on whole-file edges and is a free-tier
single-rule check. This unit test runs in seconds and complements it
with a Python-import-graph view that lives inside the test suite — so
a regression surfaces locally before push, not just in CI sentrux.
"""

from __future__ import annotations

import ast
import sys
from collections import defaultdict
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
SCISTUDIO_ROOT = SRC_ROOT / "scistudio"

# Post-#1482 baseline. Bumping this number ABOVE 4 requires a written
# justification in the PR (per ADR-042 Addendum 1 — weakening an
# architectural guard MUST be approved). Lower-or-equal bumps are
# routine improvements.
MAX_PYTHON_CYCLES = 4


def _module_name(path: Path) -> str:
    rel = path.relative_to(SRC_ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _collect_imports(path: Path, this_module: str) -> set[str]:
    """Return runtime-only imports from *path*; TYPE_CHECKING blocks skipped."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return set()
    deps: set[str] = set()
    pkg_parts = this_module.split(".")

    def _walk(nodes: list[ast.stmt]) -> None:
        for node in nodes:
            if isinstance(node, ast.If):
                test = node.test
                is_typecheck = (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
                    isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
                )
                if is_typecheck:
                    _walk(node.orelse)
                    continue
                _walk(node.body)
                _walk(node.orelse)
                continue
            if isinstance(node, ast.Try):
                _walk(node.body)
                for handler in node.handlers:
                    _walk(handler.body)
                _walk(node.orelse)
                _walk(node.finalbody)
                continue
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                _walk(node.body)
                continue
            if isinstance(node, ast.Import):
                for alias in node.names:
                    deps.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = pkg_parts[: len(pkg_parts) - node.level]
                    mod = ".".join(filter(None, [*base, node.module])) if node.module else ".".join(filter(None, base))
                else:
                    mod = node.module or ""
                if not mod:
                    continue
                deps.add(mod)
                for alias in node.names:
                    deps.add(f"{mod}.{alias.name}")

    _walk(tree.body)
    return deps


def _build_graph() -> dict[str, set[str]]:
    files = list(SCISTUDIO_ROOT.rglob("*.py"))
    name_to_path: dict[str, Path] = {_module_name(f): f for f in files}
    graph: dict[str, set[str]] = defaultdict(set)
    for mod, path in name_to_path.items():
        for dep in _collect_imports(path, mod):
            candidate = dep
            while candidate and candidate not in name_to_path:
                candidate = candidate.rsplit(".", 1)[0] if "." in candidate else ""
            if candidate and candidate != mod and candidate in name_to_path:
                graph[mod].add(candidate)
    return graph


def _tarjan_sccs(graph: dict[str, set[str]]) -> list[list[str]]:
    index: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    idx = [0]
    sccs: list[list[str]] = []

    def _strongconnect(v: str) -> None:
        index[v] = idx[0]
        lowlink[v] = idx[0]
        idx[0] += 1
        stack.append(v)
        on_stack.add(v)
        for w in graph.get(v, ()):
            if w not in index:
                _strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in on_stack:
                lowlink[v] = min(lowlink[v], index[w])
        if lowlink[v] == index[v]:
            comp: list[str] = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                comp.append(w)
                if w == v:
                    break
            sccs.append(comp)

    previous_recursion_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(max(previous_recursion_limit, 10_000))
    try:
        nodes = list(graph.keys()) + [n for n in {d for deps in graph.values() for d in deps} if n not in graph]
        for v in nodes:
            if v not in index:
                _strongconnect(v)
    finally:
        sys.setrecursionlimit(previous_recursion_limit)
    return sccs


def test_python_import_cycle_count_does_not_regress() -> None:
    """Assert ``src/scistudio`` has at most ``MAX_PYTHON_CYCLES`` SCCs.

    A regression here usually means a new direct ``mod_a → mod_b`` edge
    was added next to an existing ``mod_b → mod_a`` edge. Either remove
    the new edge (move a helper into a shared sibling) or argue for a
    threshold bump in the PR review.
    """
    graph = _build_graph()
    sccs = _tarjan_sccs(graph)
    cycles = [comp for comp in sccs if len(comp) > 1]
    if len(cycles) > MAX_PYTHON_CYCLES:
        lines = [
            f"Python import cycles exceed the post-#1482 baseline "
            f"({len(cycles)} > {MAX_PYTHON_CYCLES}). Cycles:",
        ]
        cycles.sort(key=lambda comp: (-len(comp), sorted(comp)[0]))
        for i, comp in enumerate(cycles, 1):
            lines.append(f"  Cycle {i} ({len(comp)} modules):")
            for mod in sorted(comp):
                lines.append(f"    - {mod}")
        raise AssertionError("\n".join(lines))
