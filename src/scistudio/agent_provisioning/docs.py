"""Provision the in-project documentation set (#1850, ADR-052 §7).

Copies two packaged doc trees into a project so the in-project human and the
embedded agent read the authoritative public-API docs instead of reaching into
internals:

  - ``<project>/user-guide/**``                 <- ``scistudio/_user_guide/**``
    (the human user guide *and* the self-contained API reference under
    ``user-guide/api-reference/``)
  - ``<project>/.scistudio/agent-reference/**`` <- ``scistudio/_agent_reference/**``
    (terse, agent-facing contract reference the skills point at)

Filesystem-only and wheel-safe (reads through ``importlib.resources`` exactly
like ``skills.py``), idempotent (skips existing files unless ``force=True``), and
run as a non-fatal sub-step by the orchestrator.

Installed package reference docs are discovered from package-local
``_scistudio_docs/`` trees and copied into managed project-local package
reference indexes. Those managed package docs refresh when the installed package
docs change; core-owned docs still preserve existing files unless ``force=True``.
"""

from __future__ import annotations

import importlib.resources
import json
import re
from collections.abc import Iterable
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

from scistudio.desktop import paths as desktop_paths

#: (source package, project-relative destination root).
_DOC_TREES: tuple[tuple[str, str], ...] = (
    ("scistudio._user_guide", "user-guide"),
    ("scistudio._agent_reference", ".scistudio/agent-reference"),
)
_PACKAGE_DOCS_DIR = "_scistudio_docs"
_PACKAGE_DOCS_AGENT_ROOT = ".scistudio/agent-reference/packages"
_PACKAGE_DOCS_AGENT_INDEX = ".scistudio/agent-reference/package-index.md"
_PACKAGE_DOCS_USER_ROOT = "user-guide/package-reference"
_PACKAGE_DOCS_USER_INDEX = "user-guide/package-reference/index.md"


def _copy_tree(
    src: Traversable | Path,
    dest: Path,
    *,
    force: bool,
    rel: str,
    written: list[str],
    refresh: bool = False,
) -> None:
    """Recursively copy a ``importlib.resources`` traversable into ``dest``."""
    for child in src.iterdir():
        name = child.name
        if name == "__pycache__" or name.endswith((".pyc", ".pyo")):
            continue
        child_rel = f"{rel}/{name}"
        if child.is_dir():
            _copy_tree(child, dest / name, force=force, rel=child_rel, written=written, refresh=refresh)
            continue
        target = dest / name
        data = child.read_bytes()
        if target.exists():
            if refresh and target.read_bytes() == data:
                continue
            if not refresh and not force:
                continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        written.append(child_rel)


def _write_text_if_changed(target: Path, body: str, *, rel: str, written: list[str]) -> None:
    if target.exists() and target.read_text(encoding="utf-8") == body:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    written.append(rel)


def _safe_slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("._-")
    return (cleaned or "package").lower()


def _manifest(docs_root: Path) -> dict[str, Any]:
    manifest = docs_root / "manifest.json"
    if not manifest.is_file():
        return {}
    try:
        raw = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _manifest_str(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _iter_package_docs(package_dirs: list[Path]) -> list[tuple[str, str, str, Path]]:
    """Return ``(slug, display_name, version, docs_root)`` for installed docs."""
    found: list[tuple[str, str, str, Path]] = []
    seen: set[str] = set()
    for root_module, _module_name, import_roots in desktop_paths.iter_source_package_module_candidates(package_dirs):
        for import_root in import_roots:
            docs_root = Path(import_root) / root_module / _PACKAGE_DOCS_DIR
            if not docs_root.is_dir():
                continue
            key = str(docs_root.resolve())
            if key in seen:
                continue
            seen.add(key)
            data = _manifest(docs_root)
            package_name = _manifest_str(data, "package_name", "name", "title") or root_module.replace("_", "-")
            version = _manifest_str(data, "version")
            slug = _safe_slug(_manifest_str(data, "slug") or root_module.replace("_", "-"))
            found.append((slug, package_name, version, docs_root))
    return sorted(found, key=lambda item: item[0])


def _package_index_target(docs_root: Path, *, slug: str, hidden: bool) -> str:
    if hidden and (docs_root / "agent-reference" / "README.md").is_file():
        return f"packages/{slug}/README.md"
    if not hidden and (docs_root / "user-guide" / "README.md").is_file():
        return f"{slug}/README.md"
    if (docs_root / "api-reference" / "index.md").is_file():
        prefix = f"packages/{slug}" if hidden else slug
        return f"{prefix}/api-reference/index.md"
    prefix = f"packages/{slug}" if hidden else slug
    return f"{prefix}/"


def _render_package_index(packages: list[tuple[str, str, str, Path]], *, hidden: bool) -> str:
    title = "# Installed Package Reference\n"
    intro = (
        "Generated from documentation bundled inside installed SciStudio packages. "
        "Use these package references when authoring custom blocks against package "
        "types, constructors, and blocks.\n"
    )
    if not packages:
        return title + "\n" + intro + "\nNo installed package reference docs were found.\n"

    lines = [title, intro, "## Packages\n"]
    for slug, package_name, version, docs_root in packages:
        version_text = f" `{version}`" if version else ""
        has_agent = (docs_root / "agent-reference").is_dir()
        has_api = (docs_root / "api-reference").is_dir()
        target = _package_index_target(docs_root, slug=slug, hidden=hidden)
        parts = []
        if has_agent:
            parts.append("agent reference")
        if has_api:
            parts.append("API reference")
        kind = ", ".join(parts) if parts else "reference docs"
        lines.append(f"- [{package_name}]({target}){version_text} — {kind}")
    lines.append("")
    return "\n".join(lines)


def write_package_docs(
    project_dir: Path,
    *,
    package_dirs: Iterable[str | Path] | None = None,
) -> list[str]:
    """Copy installed package reference docs into ``project_dir``.

    Package docs are managed generated artifacts. Unlike the core user guide,
    they refresh changed files in place so package updates make the active
    project's reference match the currently installed package version.
    """
    project_dir = Path(project_dir)
    dirs = package_dirs if package_dirs is not None else desktop_paths.candidate_package_dirs()
    packages = _iter_package_docs([Path(path) for path in dirs])
    written: list[str] = []

    for slug, _package_name, _version, docs_root in packages:
        agent_dest = project_dir / _PACKAGE_DOCS_AGENT_ROOT / slug
        user_dest = project_dir / _PACKAGE_DOCS_USER_ROOT / slug

        agent_src = docs_root / "agent-reference"
        if agent_src.is_dir():
            _copy_tree(
                agent_src,
                agent_dest,
                force=True,
                rel=f"{_PACKAGE_DOCS_AGENT_ROOT}/{slug}",
                written=written,
                refresh=True,
            )

        api_src = docs_root / "api-reference"
        if api_src.is_dir():
            _copy_tree(
                api_src,
                agent_dest / "api-reference",
                force=True,
                rel=f"{_PACKAGE_DOCS_AGENT_ROOT}/{slug}/api-reference",
                written=written,
                refresh=True,
            )
            _copy_tree(
                api_src,
                user_dest / "api-reference",
                force=True,
                rel=f"{_PACKAGE_DOCS_USER_ROOT}/{slug}/api-reference",
                written=written,
                refresh=True,
            )

        user_src = docs_root / "user-guide"
        if user_src.is_dir():
            _copy_tree(
                user_src,
                user_dest,
                force=True,
                rel=f"{_PACKAGE_DOCS_USER_ROOT}/{slug}",
                written=written,
                refresh=True,
            )

    _write_text_if_changed(
        project_dir / _PACKAGE_DOCS_AGENT_INDEX,
        _render_package_index(packages, hidden=True),
        rel=_PACKAGE_DOCS_AGENT_INDEX,
        written=written,
    )
    _write_text_if_changed(
        project_dir / _PACKAGE_DOCS_USER_INDEX,
        _render_package_index(packages, hidden=False),
        rel=_PACKAGE_DOCS_USER_INDEX,
        written=written,
    )
    return written


def write_docs(
    project_dir: Path,
    *,
    force: bool = False,
    package_dirs: Iterable[str | Path] | None = None,
) -> list[str]:
    """Copy the user guide + API reference + agent reference into ``project_dir``.

    Returns the list of project-relative paths actually written (idempotent: an
    existing core-doc file is skipped unless ``force``). Installed package
    reference docs are refreshed as managed generated artifacts.
    """
    project_dir = Path(project_dir)
    written: list[str] = []
    for package, dest_root in _DOC_TREES:
        try:
            root = importlib.resources.files(package)
        except (ModuleNotFoundError, FileNotFoundError, NotADirectoryError):
            continue
        if not root.is_dir():
            continue
        _copy_tree(root, project_dir / dest_root, force=force, rel=dest_root, written=written)
    written.extend(write_package_docs(project_dir, package_dirs=package_dirs))
    return written
