"""Category (b) MCP tools — block authoring helpers (5 stubs).

T-ECA-201 (scaffold). Implementation lands in T-ECA-203. See
``docs/specs/embedded-coding-agent-spec.md`` §6 T-ECA-203 for per-tool
implementation notes.

All stubs raise :class:`NotImplementedError`. Signatures,
return-type annotations, and docstrings are the contract for T-ECA-203.
"""

from __future__ import annotations

from typing import Any


def read_block_source(type_name: str) -> dict[str, Any]:
    """Return the Python source file backing a registered block type.

    Calls ``inspect.getfile(block_cls)`` then ``Path.read_text()``.

    Parameters
    ----------
    type_name
        The block's registered type name.

    Returns
    -------
    dict
        ``{"path": str, "source": str, "language": "python"}``.

    Side effects
    ------------
    None. Read-only filesystem access.

    Raises
    ------
    KeyError
        If *type_name* is not registered.
    NotImplementedError
        Until T-ECA-203 lands.
    """
    raise NotImplementedError("read_block_source lands in T-ECA-203")


def list_block_examples(category: str) -> list[dict[str, Any]]:
    """List curated example blocks for a category.

    Initial implementation returns a hard-coded curated list rooted at
    ``src/scieasy/blocks/{category}/``; v2 will make the curation set
    configurable via project settings.

    Parameters
    ----------
    category
        Base category name (e.g. ``"io"``, ``"transform"``,
        ``"analysis"``).

    Returns
    -------
    list of dict
        One entry per example with ``name``, ``path``, ``description``.

    Side effects
    ------------
    None. Read-only.

    Raises
    ------
    NotImplementedError
        Until T-ECA-203 lands.
    """
    raise NotImplementedError("list_block_examples lands in T-ECA-203")


def scaffold_block(name: str, category: str) -> dict[str, Any]:
    """Render a new block module from the project's block templates.

    Reads templates from ``docs/block-development/templates/`` and
    writes the rendered output to ``{project}/blocks/{name}.py``.
    Write-class tool: requires permission approval in STRICT mode.

    Parameters
    ----------
    name
        Snake-case block name.
    category
        Base category to file the block under.

    Returns
    -------
    dict
        ``{"path": str, "created": bool, "template_used": str}``.

    Side effects
    ------------
    Writes a new Python file under the project workspace.

    Raises
    ------
    FileExistsError
        If the target path already exists.
    PermissionError
        If the permission policy denies the call.
    NotImplementedError
        Until T-ECA-203 lands.
    """
    raise NotImplementedError("scaffold_block lands in T-ECA-203")


def reload_blocks() -> dict[str, Any]:
    """Hot-reload the block registry to pick up authoring changes.

    Calls ``get_block_registry().hot_reload()``. Used after the agent
    edits or scaffolds a block and wants the new type to be visible to
    subsequent :func:`list_blocks` / :func:`get_block_schema` calls.

    Returns
    -------
    dict
        ``{"reloaded": int, "added": [str, ...], "removed": [str, ...]}``.

    Side effects
    ------------
    Mutates the in-process block registry. May invalidate cached
    schemas in dependent subsystems (those subsystems are expected to
    subscribe to the registry-change event).

    Raises
    ------
    NotImplementedError
        Until T-ECA-203 lands.
    """
    raise NotImplementedError("reload_blocks lands in T-ECA-203")


def run_block_tests(type_name: str) -> dict[str, Any]:
    """Run pytest against the test module associated with a block.

    Heuristic test-path discovery: ``tests/blocks/test_<name>.py``
    relative to the project root. Invokes ``pytest --tb=short`` and
    captures stdout / stderr / return code.

    Parameters
    ----------
    type_name
        The block's registered type name.

    Returns
    -------
    dict
        ``{"returncode": int, "stdout": str, "stderr": str,
        "test_path": str, "found": bool}``.

    Side effects
    ------------
    Spawns a pytest subprocess. Does *not* modify any persistent state.

    Raises
    ------
    NotImplementedError
        Until T-ECA-203 lands.
    """
    raise NotImplementedError("run_block_tests lands in T-ECA-203")
