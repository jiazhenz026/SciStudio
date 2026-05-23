"""Find import cycles in src/scistudio/ to corroborate sentrux's 5-cycle count."""
from __future__ import annotations

import ast
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def module_name(path: Path) -> str:
    rel = path.relative_to(SRC).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def collect_imports(path: Path, this_module: str) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return set()
    deps: set[str] = set()
    pkg_parts = this_module.split(".")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                deps.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = pkg_parts[: len(pkg_parts) - node.level] if node.module is None else pkg_parts[: len(pkg_parts) - node.level]
                mod = ".".join(filter(None, base + ([node.module] if node.module else [])))
            else:
                mod = node.module or ""
            if not mod:
                continue
            deps.add(mod)
            for alias in node.names:
                deps.add(f"{mod}.{alias.name}")
    return deps


def build_graph() -> tuple[dict[str, set[str]], dict[str, Path]]:
    files = list(SRC.rglob("*.py"))
    name_to_path: dict[str, Path] = {}
    for f in files:
        name_to_path[module_name(f)] = f
    graph: dict[str, set[str]] = defaultdict(set)
    for mod, path in name_to_path.items():
        deps = collect_imports(path, mod)
        for dep in deps:
            # Resolve dep to a module we know about (longest prefix match).
            candidate = dep
            while candidate and candidate not in name_to_path:
                candidate = candidate.rsplit(".", 1)[0] if "." in candidate else ""
            if candidate and candidate != mod and candidate in name_to_path:
                graph[mod].add(candidate)
    return graph, name_to_path


def tarjan_sccs(graph: dict[str, set[str]]) -> list[list[str]]:
    index = {}
    lowlink = {}
    on_stack = set()
    stack: list[str] = []
    idx = [0]
    sccs: list[list[str]] = []

    def strongconnect(v: str) -> None:
        index[v] = idx[0]
        lowlink[v] = idx[0]
        idx[0] += 1
        stack.append(v)
        on_stack.add(v)
        for w in graph.get(v, ()):  # iterate
            if w not in index:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in on_stack:
                lowlink[v] = min(lowlink[v], index[w])
        if lowlink[v] == index[v]:
            comp = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                comp.append(w)
                if w == v:
                    break
            sccs.append(comp)

    sys.setrecursionlimit(10000)
    nodes = list(graph.keys()) + [n for n in {d for deps in graph.values() for d in deps} if n not in graph]
    for v in nodes:
        if v not in index:
            strongconnect(v)
    return sccs


def main() -> None:
    graph, _ = build_graph()
    sccs = tarjan_sccs(graph)
    cycles = [c for c in sccs if len(c) > 1]
    cycles.sort(key=lambda c: (-len(c), c[0]))
    print(f"Found {len(cycles)} cycle(s) among {len(graph)} modules")
    for i, comp in enumerate(cycles, 1):
        print(f"\nCycle {i} ({len(comp)} modules):")
        for m in sorted(comp):
            print(f"  - {m}")
            for dep in sorted(graph.get(m, set()) & set(comp)):
                print(f"        -> {dep}")


if __name__ == "__main__":
    main()
