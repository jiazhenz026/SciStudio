"""Conservative reachability helpers for change-contract gate checks.

The helpers in this module deliberately avoid depending on the change-contract
schema models. They accept small typed declarations and return structured
findings so the contract checker can adapt schema objects at its boundary.
"""

from __future__ import annotations

import ast
import importlib.metadata
import re
import tomllib
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from scistudio.qa.audit._util import normalise_path

ReachabilityKind = Literal["python_module", "frontend_component", "entry_point"]
ReachabilityStatus = Literal["reachable", "declared_canary", "declared_entry_point", "unreachable"]
Severity = Literal["error", "warning", "info"]

DEFAULT_PYTHON_SOURCE_ROOTS: tuple[str, ...] = ("src",)
DEFAULT_FRONTEND_SOURCE_ROOTS: tuple[str, ...] = ("frontend/src",)
PYTHON_TEST_PARTS = frozenset({"tests", "test", "__tests__"})
FRONTEND_TEST_PARTS = frozenset({"__tests__", "__mocks__", "test", "tests", "e2e"})
FRONTEND_EXTENSIONS: tuple[str, ...] = (".ts", ".tsx", ".js", ".jsx")
DEFAULT_FRONTEND_ALIASES: Mapping[str, str] = {"@/": "frontend/src/"}
CONSOLE_SCRIPTS_GROUP = "console_scripts"

_TS_STATIC_IMPORT_RE = re.compile(
    r"""(?mx)
    ^\s*
    (?:
        import\s+(?:type\s+)?(?:[^'";]*?\s+from\s+)? |
        export\s+(?:type\s+)?(?:[^'";]*?\s+from\s+)
    )
    ["'](?P<specifier>[^"']+)["']
    """
)


@dataclass(frozen=True, slots=True)
class ReachabilityFinding:
    """A schema-independent finding emitted by reachability checks."""

    rule_id: str
    severity: Severity
    kind: str
    target: str
    message: str
    evidence: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ReachabilityEvidence:
    """Machine-readable evidence for one reachability requirement."""

    kind: str
    target: str
    status: ReachabilityStatus
    roots: tuple[str, ...] = ()
    path: tuple[str, ...] = ()
    entry_point: str | None = None
    canaries: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReachabilityRequirement:
    """A minimal declaration A2 can build from change-contract schema objects."""

    kind: ReachabilityKind
    target: str
    roots: tuple[str, ...] = ()
    entry_point_group: str | None = None
    entry_point_name: str | None = None
    entry_point_value: str | None = None
    canaries: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReachabilityResult:
    """Aggregate result for a batch of reachability requirements."""

    findings: tuple[ReachabilityFinding, ...]
    evidence: tuple[ReachabilityEvidence, ...]

    @property
    def blocks_merge(self) -> bool:
        return any(finding.severity == "error" for finding in self.findings)


@dataclass(frozen=True, slots=True)
class ImportGraph:
    """Directed import graph with normalized node names."""

    nodes: frozenset[str]
    edges: Mapping[str, frozenset[str]]
    paths: Mapping[str, str]
    parse_errors: Mapping[str, str] = field(default_factory=dict)

    def normalize_node(self, target: str) -> str:
        """Normalize ``target`` to a known node when possible."""

        normalized = normalise_path(target).removesuffix("/")
        by_path = {path: node for node, path in self.paths.items()}
        if normalized in by_path:
            return by_path[normalized]
        if f"{normalized}.py" in by_path:
            return by_path[f"{normalized}.py"]
        for suffix in FRONTEND_EXTENSIONS:
            if f"{normalized}{suffix}" in by_path:
                return by_path[f"{normalized}{suffix}"]
            if f"{normalized}/index{suffix}" in by_path:
                return by_path[f"{normalized}/index{suffix}"]
        without_extension = normalized
        for suffix in (*FRONTEND_EXTENSIONS, ".py"):
            if without_extension.endswith(suffix):
                without_extension = without_extension[: -len(suffix)]
                break
        if without_extension in by_path:
            return by_path[without_extension]
        return target

    def reachable_path(self, target: str, roots: Sequence[str]) -> tuple[str, ...] | None:
        """Return a node path from ``roots`` to ``target`` if one exists."""

        target_node = self.normalize_node(target)
        root_nodes = [self.normalize_node(root) for root in roots]
        queue: deque[tuple[str, tuple[str, ...]]] = deque((root, (root,)) for root in root_nodes if root in self.nodes)
        visited = {root for root, _ in queue}
        while queue:
            node, path = queue.popleft()
            if node == target_node:
                return path
            for child in sorted(self.edges.get(node, frozenset())):
                if child in visited:
                    continue
                visited.add(child)
                queue.append((child, (*path, child)))
        return None


@dataclass(frozen=True, slots=True)
class EntryPointRecord:
    """One Python packaging entry point declaration."""

    group: str
    name: str
    value: str
    source: str

    @property
    def key(self) -> str:
        return f"{self.group}:{self.name}"


def _is_test_path(path: Path, test_parts: frozenset[str]) -> bool:
    lowered = tuple(part.lower() for part in path.parts)
    return any(part in test_parts for part in lowered) or any(
        path.name.endswith(suffix) for suffix in (".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")
    )


def _module_name(path: Path, source_root: Path) -> str | None:
    try:
        relative = path.relative_to(source_root)
    except ValueError:
        return None
    parts = list(relative.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts:
        return None
    return ".".join(parts)


def _python_modules(repo_root: Path, source_roots: Sequence[str | Path]) -> dict[str, Path]:
    modules: dict[str, Path] = {}
    for raw_root in source_roots:
        source_root = Path(raw_root)
        absolute_root = source_root if source_root.is_absolute() else repo_root / source_root
        if not absolute_root.exists():
            continue
        for path in sorted(absolute_root.rglob("*.py")):
            if _is_test_path(path.relative_to(repo_root), PYTHON_TEST_PARTS):
                continue
            module = _module_name(path, absolute_root)
            if module is not None:
                modules[module] = path
    return modules


def _package_for_import_from(module: str, *, is_package: bool) -> str:
    if is_package:
        return module
    return module.rsplit(".", 1)[0] if "." in module else ""


def _resolve_import_from_base(node: ast.ImportFrom, current_module: str, *, is_package: bool) -> str | None:
    if node.level == 0:
        return node.module
    package = _package_for_import_from(current_module, is_package=is_package)
    parts = package.split(".") if package else []
    if node.level > 1:
        trim = node.level - 1
        if trim > len(parts):
            return None
        parts = parts[:-trim] if trim else parts
    if node.module:
        parts.extend(node.module.split("."))
    return ".".join(part for part in parts if part)


def _known_prefixes(module: str, known_modules: set[str]) -> set[str]:
    parts = module.split(".")
    prefixes = {".".join(parts[:index]) for index in range(1, len(parts) + 1)}
    return prefixes & known_modules


def _python_import_edges(path: Path, module: str, known_modules: set[str]) -> tuple[set[str], str | None]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        return set(), str(exc)

    is_package = path.name == "__init__.py"
    edges: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                edges.update(_known_prefixes(alias.name, known_modules))
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_import_from_base(node, module, is_package=is_package)
            if not base:
                continue
            edges.update(_known_prefixes(base, known_modules))
            for alias in node.names:
                if alias.name == "*":
                    continue
                edges.update(_known_prefixes(f"{base}.{alias.name}", known_modules))
    edges.discard(module)
    return edges, None


def build_python_import_graph(
    repo_root: Path,
    *,
    source_roots: Sequence[str | Path] = DEFAULT_PYTHON_SOURCE_ROOTS,
) -> ImportGraph:
    """Build a conservative Python import graph rooted in production sources."""

    root = repo_root.resolve()
    modules = _python_modules(root, source_roots)
    known_modules = set(modules)
    edges: dict[str, frozenset[str]] = {}
    parse_errors: dict[str, str] = {}
    paths: dict[str, str] = {}
    for module, path in modules.items():
        imported, error = _python_import_edges(path, module, known_modules)
        edges[module] = frozenset(imported)
        relative = path.relative_to(root)
        paths[module] = normalise_path(relative)
        if error is not None:
            parse_errors[module] = error
    return ImportGraph(
        nodes=frozenset(modules),
        edges=edges,
        paths=paths,
        parse_errors=parse_errors,
    )


def _frontend_files(repo_root: Path, source_roots: Sequence[str | Path]) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for raw_root in source_roots:
        source_root = Path(raw_root)
        absolute_root = source_root if source_root.is_absolute() else repo_root / source_root
        if not absolute_root.exists():
            continue
        for path in sorted(absolute_root.rglob("*")):
            if path.suffix not in FRONTEND_EXTENSIONS:
                continue
            relative = path.relative_to(repo_root)
            if _is_test_path(relative, FRONTEND_TEST_PARTS):
                continue
            files[normalise_path(relative)] = path
    return files


def _iter_static_ts_specifiers(text: str) -> tuple[str, ...]:
    return tuple(match.group("specifier") for match in _TS_STATIC_IMPORT_RE.finditer(text))


def _candidate_frontend_paths(base: Path) -> tuple[Path, ...]:
    if base.suffix:
        return (base,)
    candidates = [base.with_suffix(extension) for extension in FRONTEND_EXTENSIONS]
    candidates.extend(base / f"index{extension}" for extension in FRONTEND_EXTENSIONS)
    return tuple(candidates)


def _resolve_frontend_specifier(
    specifier: str,
    *,
    importer: Path,
    repo_root: Path,
    aliases: Mapping[str, str],
    known_paths: set[str],
) -> str | None:
    if specifier.startswith("."):
        base = (importer.parent / specifier).resolve()
    else:
        base = None
        for prefix, replacement in aliases.items():
            if specifier.startswith(prefix):
                replacement_path = Path(replacement)
                replacement_base = replacement_path if replacement_path.is_absolute() else repo_root / replacement_path
                base = (replacement_base / specifier[len(prefix) :]).resolve()
                break
        if base is None:
            return None

    assert base is not None
    for candidate in _candidate_frontend_paths(base):
        try:
            relative = normalise_path(candidate.relative_to(repo_root))
        except ValueError:
            continue
        if relative in known_paths:
            return relative
    return None


def build_frontend_import_graph(
    repo_root: Path,
    *,
    source_roots: Sequence[str | Path] = DEFAULT_FRONTEND_SOURCE_ROOTS,
    aliases: Mapping[str, str] = DEFAULT_FRONTEND_ALIASES,
) -> ImportGraph:
    """Build a conservative static import graph for TypeScript/JavaScript sources."""

    root = repo_root.resolve()
    files = _frontend_files(root, source_roots)
    known_paths = set(files)
    edges: dict[str, frozenset[str]] = {}
    parse_errors: dict[str, str] = {}
    for node, path in files.items():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            edges[node] = frozenset()
            parse_errors[node] = str(exc)
            continue
        resolved = {
            imported
            for specifier in _iter_static_ts_specifiers(text)
            if (
                imported := _resolve_frontend_specifier(
                    specifier,
                    importer=path,
                    repo_root=root,
                    aliases=aliases,
                    known_paths=known_paths,
                )
            )
            is not None
        }
        edges[node] = frozenset(resolved)
    return ImportGraph(
        nodes=frozenset(files),
        edges=edges,
        paths={node: node for node in files},
        parse_errors=parse_errors,
    )


def _pyproject_entry_points(pyproject: Path) -> tuple[EntryPointRecord, ...]:
    if not pyproject.exists():
        return ()
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return ()
    project = data.get("project", {})
    if not isinstance(project, dict):
        return ()

    records: list[EntryPointRecord] = []
    scripts = project.get("scripts", {})
    if isinstance(scripts, dict):
        records.extend(
            EntryPointRecord(group=CONSOLE_SCRIPTS_GROUP, name=str(name), value=str(value), source="pyproject.toml")
            for name, value in scripts.items()
        )

    entry_points = project.get("entry-points", {})
    if isinstance(entry_points, dict):
        for group, entries in entry_points.items():
            if not isinstance(entries, dict):
                continue
            records.extend(
                EntryPointRecord(group=str(group), name=str(name), value=str(value), source="pyproject.toml")
                for name, value in entries.items()
            )
    return tuple(records)


def _installed_entry_points() -> tuple[EntryPointRecord, ...]:
    try:
        entry_points = importlib.metadata.entry_points()
    except Exception:
        return ()

    selected = entry_points
    if hasattr(entry_points, "select"):
        selected = entry_points.select()
    records: list[EntryPointRecord] = []
    for entry_point in selected:
        group = getattr(entry_point, "group", None)
        name = getattr(entry_point, "name", None)
        value = getattr(entry_point, "value", None)
        if group is None or name is None or value is None:
            continue
        records.append(
            EntryPointRecord(group=str(group), name=str(name), value=str(value), source="importlib.metadata")
        )
    return tuple(records)


def collect_python_entry_points(
    repo_root: Path,
    *,
    pyproject_path: str | Path = "pyproject.toml",
    include_installed: bool = False,
) -> tuple[EntryPointRecord, ...]:
    """Return Python entry points declared in repo packaging metadata."""

    root = repo_root.resolve()
    pyproject = Path(pyproject_path)
    if not pyproject.is_absolute():
        pyproject = root / pyproject
    records = list(_pyproject_entry_points(pyproject))
    if include_installed:
        records.extend(_installed_entry_points())
    return tuple(records)


def _entry_point_lookup(records: Sequence[EntryPointRecord]) -> Mapping[tuple[str, str], EntryPointRecord]:
    return {(record.group, record.name): record for record in records}


def _requirement_entry_point(requirement: ReachabilityRequirement) -> tuple[str | None, str | None]:
    if requirement.entry_point_group is not None:
        return requirement.entry_point_group, requirement.entry_point_name
    for separator in (":", "/"):
        if separator in requirement.target:
            group, name = requirement.target.split(separator, 1)
            return group, name
    return None, requirement.entry_point_name


def _entry_point_satisfies_target(record: EntryPointRecord, target: str, expected_value: str | None) -> bool:
    if expected_value is not None:
        return record.value == expected_value
    value_module = record.value.split(":", 1)[0]
    return value_module == target or value_module.startswith(f"{target}.")


def _matching_entry_point(
    requirement: ReachabilityRequirement,
    records: Sequence[EntryPointRecord],
) -> EntryPointRecord | None:
    group, name = _requirement_entry_point(requirement)
    if group is not None and name is not None:
        record = _entry_point_lookup(records).get((group, name))
        if record is None:
            return None
        if requirement.kind == "entry_point":
            if requirement.entry_point_value is not None and record.value != requirement.entry_point_value:
                return None
            return record
        return (
            record if _entry_point_satisfies_target(record, requirement.target, requirement.entry_point_value) else None
        )

    if group is None:
        return None
    for record in records:
        if record.group != group:
            continue
        if requirement.kind == "entry_point":
            if requirement.entry_point_value is None or record.value == requirement.entry_point_value:
                return record
            continue
        if _entry_point_satisfies_target(record, requirement.target, requirement.entry_point_value):
            return record
    return None


def _canary_evidence(requirement: ReachabilityRequirement) -> ReachabilityEvidence | None:
    if not requirement.canaries:
        return None
    return ReachabilityEvidence(
        kind=requirement.kind,
        target=requirement.target,
        status="declared_canary",
        canaries=requirement.canaries,
    )


def _entry_point_evidence(
    requirement: ReachabilityRequirement,
    records: Sequence[EntryPointRecord],
) -> ReachabilityEvidence | None:
    record = _matching_entry_point(requirement, records)
    if record is None:
        return None
    return ReachabilityEvidence(
        kind=requirement.kind,
        target=requirement.target,
        status="declared_entry_point",
        entry_point=record.key,
    )


def _unreachable_finding(
    requirement: ReachabilityRequirement,
    *,
    roots: Sequence[str] = (),
    rule_id: str,
    message: str,
) -> ReachabilityFinding:
    evidence: dict[str, Any] = {"target": requirement.target}
    if roots:
        evidence["roots"] = tuple(roots)
    if requirement.entry_point_group:
        evidence["entry_point_group"] = requirement.entry_point_group
    if requirement.entry_point_name:
        evidence["entry_point_name"] = requirement.entry_point_name
    return ReachabilityFinding(
        rule_id=rule_id,
        severity="error",
        kind=requirement.kind,
        target=requirement.target,
        message=message,
        evidence=evidence,
    )


def evaluate_reachability(
    repo_root: Path,
    requirements: Sequence[ReachabilityRequirement],
    *,
    python_roots: Sequence[str] = (),
    frontend_roots: Sequence[str] = (),
    python_source_roots: Sequence[str | Path] = DEFAULT_PYTHON_SOURCE_ROOTS,
    frontend_source_roots: Sequence[str | Path] = DEFAULT_FRONTEND_SOURCE_ROOTS,
    frontend_aliases: Mapping[str, str] = DEFAULT_FRONTEND_ALIASES,
    entry_points: Sequence[EntryPointRecord] | None = None,
) -> ReachabilityResult:
    """Evaluate production reachability declarations.

    Static graph evidence is preferred. Explicit canary declarations or
    resolvable entry-point registrations can satisfy dynamic cases without
    forcing this helper into framework-specific import analysis.
    """

    findings: list[ReachabilityFinding] = []
    evidence: list[ReachabilityEvidence] = []
    python_graph: ImportGraph | None = None
    frontend_graph: ImportGraph | None = None
    records = tuple(entry_points) if entry_points is not None else collect_python_entry_points(repo_root)

    for requirement in requirements:
        if requirement.kind == "python_module":
            python_graph = python_graph or build_python_import_graph(repo_root, source_roots=python_source_roots)
            roots = requirement.roots or tuple(python_roots)
            path = python_graph.reachable_path(requirement.target, roots)
            if path is not None:
                evidence.append(
                    ReachabilityEvidence(
                        kind=requirement.kind,
                        target=requirement.target,
                        status="reachable",
                        roots=tuple(roots),
                        path=path,
                    )
                )
                continue
            if canary := _canary_evidence(requirement):
                evidence.append(canary)
                continue
            if entry_point := _entry_point_evidence(requirement, records):
                evidence.append(entry_point)
                continue
            findings.append(
                _unreachable_finding(
                    requirement,
                    roots=roots,
                    rule_id="change-contract.reachability.python-module-unreachable",
                    message=(f"Python module '{requirement.target}' is not reachable from declared production roots"),
                )
            )
        elif requirement.kind == "frontend_component":
            frontend_graph = frontend_graph or build_frontend_import_graph(
                repo_root,
                source_roots=frontend_source_roots,
                aliases=frontend_aliases,
            )
            roots = requirement.roots or tuple(frontend_roots)
            path = frontend_graph.reachable_path(requirement.target, roots)
            if path is not None:
                evidence.append(
                    ReachabilityEvidence(
                        kind=requirement.kind,
                        target=requirement.target,
                        status="reachable",
                        roots=tuple(roots),
                        path=path,
                    )
                )
                continue
            if canary := _canary_evidence(requirement):
                evidence.append(canary)
                continue
            findings.append(
                _unreachable_finding(
                    requirement,
                    roots=roots,
                    rule_id="change-contract.reachability.frontend-component-unreachable",
                    message=(f"Frontend component '{requirement.target}' is not reachable from declared UI roots"),
                )
            )
        elif requirement.kind == "entry_point":
            if entry_point := _entry_point_evidence(requirement, records):
                evidence.append(entry_point)
                continue
            if canary := _canary_evidence(requirement):
                evidence.append(canary)
                continue
            group, name = _requirement_entry_point(requirement)
            findings.append(
                _unreachable_finding(
                    requirement,
                    rule_id="change-contract.reachability.entry-point-missing",
                    message=f"Entry point '{group or '<unspecified>'}:{name or '<unspecified>'}' is not registered",
                )
            )
    return ReachabilityResult(findings=tuple(findings), evidence=tuple(evidence))
