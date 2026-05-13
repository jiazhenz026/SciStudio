"""Category (c) MCP tools — run and data inspection (7 stubs).

T-ECA-201 (scaffold). Implementation lands in T-ECA-203. See
``docs/specs/embedded-coding-agent-spec.md`` §6 T-ECA-203 for per-tool
implementation notes.

All stubs raise :class:`NotImplementedError`. Signatures, return-type
annotations, and docstrings are the contract for T-ECA-203.
"""

from __future__ import annotations

from typing import Any


def get_block_output(run_id: str, block_id: str, port: str) -> dict[str, Any]:
    """Resolve the recorded output of one block port from a run.

    Looks up the run's recorded output map and returns the
    ``StorageReference`` plus the ``TypeSignature`` for the requested
    port. Does *not* materialise data — the agent calls
    :func:`inspect_data` / :func:`preview_data` separately if needed.

    Parameters
    ----------
    run_id
        Identifier of a workflow run.
    block_id
        Identifier of a node within that run's DAG.
    port
        Output port name on that block.

    Returns
    -------
    dict
        ``{"ref": {...}, "type": {...}, "produced_at": str}``.

    Side effects
    ------------
    None. Read-only.

    Raises
    ------
    KeyError
        If the triple does not resolve to a recorded output.
    NotImplementedError
        Until T-ECA-203 lands.
    """
    raise NotImplementedError("get_block_output lands in T-ECA-203")


def inspect_data(ref: dict[str, Any]) -> dict[str, Any]:
    """Return metadata about a stored data reference.

    Queries the ``MetadataStore`` (per ADR-032) without loading the
    payload. Honours the 8 MiB read-cap from the Phase 2 audit
    checklist.

    Parameters
    ----------
    ref
        A ``StorageReference`` envelope (URI + type signature).

    Returns
    -------
    dict
        ``{"size": int, "dtype": str, "shape": tuple, "axes": [...],
        "summary": {...}}``. Exact fields are type-dependent.

    Side effects
    ------------
    None. Read-only metadata access.

    Raises
    ------
    NotImplementedError
        Until T-ECA-203 lands.
    """
    raise NotImplementedError("inspect_data lands in T-ECA-203")


def preview_data(ref: dict[str, Any], fmt: str) -> dict[str, Any]:
    """Compute a small preview of stored data without OOM risk.

    Type dispatch (T-ECA-203 contract):

    * ``DataFrame`` → first 100 rows via Arrow slice.
    * ``Array`` → PIL thumbnail clamped to 256x256, base64 PNG;
      implementation must use ``iter_chunks`` not ``to_memory`` so a
      4 GB array does not exhaust RAM.
    * ``Series`` → first 200 entries.
    * ``Text`` → first 4096 chars.
    * ``Artifact`` → size + thumbnail if image-like.

    Parameters
    ----------
    ref
        A ``StorageReference`` envelope.
    fmt
        Preview format hint (e.g. ``"png_base64"``, ``"json"``,
        ``"text"``). Honoured on a best-effort basis.

    Returns
    -------
    dict
        ``{"fmt": str, "payload": Any, "truncated": bool}``.

    Side effects
    ------------
    None. Read-only. Bounded memory.

    Raises
    ------
    NotImplementedError
        Until T-ECA-203 lands.
    """
    raise NotImplementedError("preview_data lands in T-ECA-203")


def get_lineage(ref: dict[str, Any]) -> dict[str, Any]:
    """Return the transitive lineage ancestors of a data reference.

    Calls ``MetadataStore.ancestors_recursive(...)``. Returns the full
    DAG of upstream artifacts and the blocks that produced them.

    Parameters
    ----------
    ref
        A ``StorageReference`` envelope.

    Returns
    -------
    dict
        ``{"nodes": [...], "edges": [...]}`` — a directed acyclic
        graph rooted at *ref*.

    Side effects
    ------------
    None. Read-only.

    Raises
    ------
    NotImplementedError
        Until T-ECA-203 lands.
    """
    raise NotImplementedError("get_lineage lands in T-ECA-203")


def get_block_config(workflow_path: str, block_id: str) -> dict[str, Any]:
    """Return the static configuration of one block in a workflow file.

    Loads the workflow YAML, locates the node by ``block_id``, returns
    ``node.config.params``.

    Parameters
    ----------
    workflow_path
        Filesystem path to the workflow YAML.
    block_id
        Identifier of the node within the workflow.

    Returns
    -------
    dict
        ``{"block_id": str, "type": str, "params": {...}}``.

    Side effects
    ------------
    None. Read-only.

    Raises
    ------
    KeyError
        If *block_id* is not present in the workflow.
    NotImplementedError
        Until T-ECA-203 lands.
    """
    raise NotImplementedError("get_block_config lands in T-ECA-203")


def update_block_config(
    workflow_path: str,
    block_id: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Patch one block's configuration in a workflow YAML on disk.

    File-locked update per ADR-033 OQ7. Uses ``ruamel.yaml`` (not
    ``pyyaml``) to preserve comments and key order. Write-class tool:
    requires permission approval in STRICT mode. Logs an INFO line
    summarising the diff (per Phase 2 audit item).

    Parameters
    ----------
    workflow_path
        Filesystem path to the workflow YAML.
    block_id
        Identifier of the node to update.
    params
        New parameter dict. Merge semantics (replace vs deep-merge) are
        defined in T-ECA-203.

    Returns
    -------
    dict
        ``{"block_id": str, "diff_summary": str, "bytes_written": int}``.

    Side effects
    ------------
    Modifies the workflow YAML in place. Acquires a file lock.

    Raises
    ------
    KeyError
        If *block_id* is not present.
    PermissionError
        If the permission policy denies the call.
    NotImplementedError
        Until T-ECA-203 lands.
    """
    raise NotImplementedError("update_block_config lands in T-ECA-203")


def get_block_logs(run_id: str, block_id: str) -> dict[str, Any]:
    """Return captured stdout / stderr from a block's execution.

    Reads the run's log store for the named block. Output is truncated
    to fit within the MCP frame budget; full logs remain available via
    the GUI log viewer.

    Parameters
    ----------
    run_id
        Identifier of a workflow run.
    block_id
        Identifier of the node within that run.

    Returns
    -------
    dict
        ``{"stdout": str, "stderr": str, "truncated": bool,
        "started_at": str, "finished_at": str | None}``.

    Side effects
    ------------
    None. Read-only.

    Raises
    ------
    KeyError
        If the (run, block) pair is unknown.
    NotImplementedError
        Until T-ECA-203 lands.
    """
    raise NotImplementedError("get_block_logs lands in T-ECA-203")
