"""Category (d) MCP tools — documentation and project Q&A (4 tools).

T-ECA-204. See ``docs/specs/embedded-coding-agent-spec.md`` §6 T-ECA-204.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from scieasy.ai.agent.mcp._context import _resolve_project_root, get_context

logger = logging.getLogger(__name__)


_SEARCH_MAX_RESULTS = 20
_SEARCH_SNIPPET_CHARS = 200
_DATA_LIST_MAX_ENTRIES = 500


# ---------------------------------------------------------------------------
# (d.1) search_docs
# ---------------------------------------------------------------------------


def _docs_root() -> Path:
    """Locate the ``docs/`` tree.

    Searches upward from the active project for a ``docs/`` directory,
    falling back to the repo-level ``docs/`` when running against the
    SciEasy source tree.
    """
    ctx = get_context()
    if ctx.project_dir is not None:
        candidate = ctx.project_dir / "docs"
        if candidate.is_dir():
            return candidate
    # Fall back to repo-rooted docs/ relative to this file.
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "docs").is_dir():
            return parent / "docs"
    raise FileNotFoundError("No docs/ directory found")


def search_docs(query: str, scope: str | None = None) -> list[dict[str, Any]]:
    """Search the on-disk ``docs/`` tree for matches to a free-text query.

    Substring match (case-insensitive). Returns up to 20 results sorted
    by descending hit count within the file.
    """
    if not query:
        return []
    root = _docs_root()
    if scope:
        scoped = root / scope
        if not scoped.exists():
            return []
        search_root = scoped
    else:
        search_root = root

    q = query.lower()
    results: list[dict[str, Any]] = []
    for md_path in sorted(search_root.rglob("*.md")):
        try:
            text = md_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lower = text.lower()
        idx = lower.find(q)
        if idx == -1:
            continue
        # Compute line number of first hit + snippet around it.
        line_no = text[:idx].count("\n") + 1
        start = max(0, idx - 60)
        end = min(len(text), idx + _SEARCH_SNIPPET_CHARS - 60)
        snippet = text[start:end].replace("\n", " ")
        results.append(
            {
                "path": str(md_path.relative_to(root.parent)) if md_path.is_relative_to(root.parent) else str(md_path),
                "line": line_no,
                "snippet": snippet,
                "score": float(lower.count(q)),
            }
        )
        if len(results) >= _SEARCH_MAX_RESULTS:
            break
    results.sort(key=lambda r: r["score"], reverse=True)
    return results


# ---------------------------------------------------------------------------
# (d.2) get_doc
# ---------------------------------------------------------------------------


def get_doc(path: str) -> dict[str, Any]:
    """Return the full text of one documentation file.

    Path validation: must resolve within the ``docs/`` tree.
    """
    root = _docs_root()
    # Accept either ``docs/foo.md`` or ``foo.md`` (already inside docs).
    p = Path(path)
    candidates = [p, root / p, root.parent / p]
    resolved: Path | None = None
    for cand in candidates:
        try:
            r = cand.resolve()
        except OSError:
            continue
        try:
            r.relative_to(root.resolve())
        except ValueError:
            continue
        if r.exists():
            resolved = r
            break
    if resolved is None:
        # Either escapes docs/ or doesn't exist.
        try:
            attempted = (root / p).resolve()
            attempted.relative_to(root.resolve())
        except ValueError as exc:
            raise PermissionError(f"Path '{path}' escapes the docs/ tree") from exc
        raise FileNotFoundError(f"Doc not found: {path}")

    content = resolved.read_text(encoding="utf-8", errors="replace")
    return {"path": str(resolved), "content": content, "bytes": len(content.encode("utf-8"))}


# ---------------------------------------------------------------------------
# (d.3) list_data
# ---------------------------------------------------------------------------


def list_data(project_dir: str) -> dict[str, Any]:
    """Enumerate data assets in the project workspace.

    Walks ``data/zarr/``, ``data/parquet/``, ``data/artifacts/`` and
    returns one entry per top-level dataset. Does not open the
    datasets — payload reads stay in :func:`preview_data`.
    """
    root = Path(project_dir)
    if not root.exists():
        raise FileNotFoundError(f"Project directory not found: {project_dir}")

    out: dict[str, list[dict[str, Any]]] = {"zarr": [], "parquet": [], "artifacts": []}
    for kind, subdir in (("zarr", "data/zarr"), ("parquet", "data/parquet"), ("artifacts", "data/artifacts")):
        dpath = root / subdir
        if not dpath.is_dir():
            continue
        for entry in sorted(dpath.iterdir()):
            try:
                stat = entry.stat()
            except OSError:
                continue
            out[kind].append(
                {
                    "name": entry.name,
                    "path": str(entry),
                    "size_bytes": stat.st_size if entry.is_file() else 0,
                    "modified_at": stat.st_mtime,
                    "is_directory": entry.is_dir(),
                }
            )
            if sum(len(v) for v in out.values()) >= _DATA_LIST_MAX_ENTRIES:
                return out
    return out


# ---------------------------------------------------------------------------
# (d.4) get_project_info
# ---------------------------------------------------------------------------


def get_project_info() -> dict[str, Any]:
    """Return high-level information about the active project workspace."""
    import yaml

    ctx = get_context()
    root = _resolve_project_root(ctx)
    project_file = root / "project.yaml"
    if not project_file.exists():
        raise FileNotFoundError(f"No project.yaml in {root}")
    raw = yaml.safe_load(project_file.read_text(encoding="utf-8")) or {}
    project_meta = raw.get("project", {}) if isinstance(raw, dict) else {}

    workflows_dir = root / "workflows"
    workflows: list[str] = []
    if workflows_dir.is_dir():
        workflows = sorted(p.stem for p in workflows_dir.glob("*.yaml"))

    recent_runs: list[dict[str, Any]] = []
    try:
        from scieasy.core.metadata_store import get_metadata_store

        store = get_metadata_store()
        if store is not None:
            # Recent runs: derive workflow_ids from list_by_workflow if
            # the store supports an enumeration helper. Otherwise leave
            # empty — this is best-effort.
            pass
    except Exception:
        logger.debug("get_project_info: MetadataStore lookup failed", exc_info=True)

    return {
        "project": project_meta,
        "path": str(root),
        "workflows": workflows,
        "recent_runs": recent_runs,
    }
