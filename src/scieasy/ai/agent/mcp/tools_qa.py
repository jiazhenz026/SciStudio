"""Category (d) MCP tools — documentation and project Q&A (4 stubs).

T-ECA-201 (scaffold). Implementation lands in T-ECA-204. See
``docs/specs/embedded-coding-agent-spec.md`` §6 T-ECA-204 for per-tool
implementation notes.

All stubs raise :class:`NotImplementedError`. Signatures, return-type
annotations, and docstrings are the contract for T-ECA-204.
"""

from __future__ import annotations

from typing import Any


def search_docs(query: str, scope: str | None = None) -> list[dict[str, Any]]:
    """Search the on-disk ``docs/`` tree for matches to a free-text query.

    Walks the ``docs/`` directory tree, optionally restricted by
    *scope*, and returns the top-N matches with file paths and line
    numbers. The initial implementation does a simple substring /
    fuzzy match; a future revision may swap in a proper index.

    Parameters
    ----------
    query
        Free-text search query.
    scope
        Optional path prefix within ``docs/`` (e.g. ``"specs"``,
        ``"adr"``). ``None`` means search everything.

    Returns
    -------
    list of dict
        ``[{"path": str, "line": int, "snippet": str, "score": float}, ...]``,
        sorted by descending ``score``.

    Side effects
    ------------
    None. Read-only filesystem access.

    Raises
    ------
    NotImplementedError
        Until T-ECA-204 lands.
    """
    raise NotImplementedError("search_docs lands in T-ECA-204")


def get_doc(path: str) -> dict[str, Any]:
    """Return the full text of one documentation file.

    Validates that *path* resolves within the ``docs/`` tree (to
    prevent the agent from reading arbitrary files via this tool) and
    returns the file content.

    Parameters
    ----------
    path
        Path relative to the project root; must start with ``docs/``.

    Returns
    -------
    dict
        ``{"path": str, "content": str, "bytes": int}``.

    Side effects
    ------------
    None. Read-only.

    Raises
    ------
    PermissionError
        If *path* escapes the ``docs/`` tree.
    FileNotFoundError
        If *path* does not exist.
    NotImplementedError
        Until T-ECA-204 lands.
    """
    raise NotImplementedError("get_doc lands in T-ECA-204")


def list_data(project_dir: str) -> dict[str, Any]:
    """Enumerate the data assets present in the project workspace.

    Walks ``data/zarr/``, ``data/parquet/``, ``data/artifacts/`` under
    *project_dir* and returns one entry per top-level dataset. Does
    *not* open the datasets — payload reads are reserved for
    :func:`inspect_data` / :func:`preview_data`.

    Parameters
    ----------
    project_dir
        Filesystem path to the project workspace root.

    Returns
    -------
    dict
        ``{"zarr": [...], "parquet": [...], "artifacts": [...]}`` where
        each list entry has ``name``, ``path``, ``size_bytes``,
        ``modified_at``.

    Side effects
    ------------
    None. Read-only filesystem access.

    Raises
    ------
    FileNotFoundError
        If *project_dir* does not exist.
    NotImplementedError
        Until T-ECA-204 lands.
    """
    raise NotImplementedError("list_data lands in T-ECA-204")


def get_project_info() -> dict[str, Any]:
    """Return high-level information about the active project workspace.

    Reads ``project.yaml``, lists workflows, and returns the last-N
    run summaries from the lineage store.

    Returns
    -------
    dict
        ``{"project": {...}, "workflows": [...],
        "recent_runs": [...]}``.

    Side effects
    ------------
    None. Read-only.

    Raises
    ------
    NotImplementedError
        Until T-ECA-204 lands.
    """
    raise NotImplementedError("get_project_info lands in T-ECA-204")
