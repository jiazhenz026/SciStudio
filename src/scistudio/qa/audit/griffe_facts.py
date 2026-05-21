"""Generate Python symbol facts with griffe for ADR-042."""

from __future__ import annotations

import subprocess
from collections.abc import Iterable
from pathlib import Path

import griffe

from scistudio.qa.schemas.facts import Fact, FactsRegistry


def _current_sha(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return result.stdout.strip()


def _stringify(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _file_path(obj: object, repo_root: Path) -> str | None:
    path = getattr(obj, "filepath", None)
    if path is None:
        return None
    try:
        return str(Path(path).resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _parameter_values(function: object) -> list[dict[str, object]]:
    parameters: list[dict[str, object]] = []
    for parameter in getattr(function, "parameters", ()):
        kind = getattr(parameter, "kind", None)
        parameters.append(
            {
                "name": parameter.name,
                "kind": getattr(kind, "value", str(kind)),
                "annotation": _stringify(getattr(parameter, "annotation", None)),
                "default": _stringify(getattr(parameter, "default", None)),
                "required": getattr(parameter, "default", None) is None,
            }
        )
    return parameters


def _symbol_value(obj: object, repo_root: Path) -> dict[str, object]:
    kind = type(obj).__name__.lower()
    value: dict[str, object] = {
        "kind": kind,
        "path": getattr(obj, "path", ""),
        "filepath": _file_path(obj, repo_root),
        "lineno": getattr(obj, "lineno", None),
        "endlineno": getattr(obj, "endlineno", None),
    }
    if type(obj).__name__ == "Function":
        value["parameters"] = _parameter_values(obj)
        value["return_annotation"] = _stringify(getattr(obj, "returns", None))
    elif type(obj).__name__ == "Class":
        value["members"] = sorted(
            name for name, member in getattr(obj, "members", {}).items() if _is_public(name, member)
        )
    elif type(obj).__name__ == "Attribute":
        value["annotation"] = _stringify(getattr(obj, "annotation", None))
        value["value"] = _stringify(getattr(obj, "value", None))
    return value


def _is_public(name: str, obj: object) -> bool:
    if name.startswith("_"):
        return False
    if getattr(obj, "is_alias", False):
        return False
    return type(obj).__name__ in {"Module", "Class", "Function", "Attribute"}


def _walk_public_symbols(obj: object) -> Iterable[object]:
    for name, member in sorted(getattr(obj, "members", {}).items()):
        if not _is_public(name, member):
            continue
        yield member
        if type(member).__name__ in {"Module", "Class"}:
            yield from _walk_public_symbols(member)


def extract_symbol_facts(
    repo_root: Path | None = None,
    *,
    package: str = "scistudio",
    search_paths: list[Path] | None = None,
    source_sha: str | None = None,
) -> list[Fact]:
    """Extract public Python symbol facts using griffe's static loader."""

    root = Path(repo_root or Path.cwd()).resolve()
    paths = search_paths or [root / "src"]
    sha = source_sha if source_sha is not None else _current_sha(root)
    package_obj = griffe.load(
        package,
        search_paths=[str(path) for path in paths],
        submodules=True,
        allow_inspection=False,
        store_source=False,
    )

    facts: list[Fact] = []
    for obj in _walk_public_symbols(package_obj):
        subject = str(getattr(obj, "path", ""))
        if not subject:
            continue
        facts.append(
            Fact(
                id=f"symbol:{subject}",
                kind="symbol",
                source="griffe",
                subject=subject,
                value=_symbol_value(obj, root),
                source_sha=sha,
                confidence="generated",
                stability="unknown",
            )
        )
    return facts


def generate_registry(
    repo_root: Path | None = None,
    *,
    package: str = "scistudio",
    search_paths: list[Path] | None = None,
    source_sha: str | None = None,
) -> FactsRegistry:
    """Generate a facts registry containing griffe-backed symbol facts."""

    root = Path(repo_root or Path.cwd()).resolve()
    sha = source_sha if source_sha is not None else _current_sha(root)
    return FactsRegistry(
        source_sha=sha,
        facts=extract_symbol_facts(
            root,
            package=package,
            search_paths=search_paths,
            source_sha=sha,
        ),
    )
