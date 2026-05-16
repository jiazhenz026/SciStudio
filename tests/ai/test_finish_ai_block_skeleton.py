"""Skeleton tests for the finish_ai_block MCP tool (ADR-035 §3.5 path a).

Path placed under ``tests/ai/`` to match the existing MCP test layout
(``test_mcp_tools_workflow.py`` etc.).

ADR-040 §3.1 migration note: the ADR-033-era ``_registry.TOOL_REGISTRY``
tuple was deleted as part of S40a — FastMCP discovers tools by
``@mcp.tool()`` decorator. The original three registry-shape tests in
this file (``test_finish_ai_block_is_registered``,
``test_registry_now_has_26_tools``,
``test_finish_ai_block_handler_has_docstring``) are rewritten to use
FastMCP's ``mcp.list_tools()`` surface. Until I40a wires the real
FastMCP instance, all tests in this module are marked skip.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Registry-shape tests — now FastMCP-backed (ADR-040 §3.1).
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="S40a skeleton — I40a impl in Phase 2a. TODO(#1012): wire FastMCP list_tools() lookup.")
def test_finish_ai_block_is_registered() -> None:
    """Tool exists in FastMCP's tool catalogue.

    Pre-ADR-040: asserted ``_registry.lookup('finish_ai_block')`` was non-None
    with category="workflow", mutation="write".

    Post-ADR-040: iterates ``mcp.list_tools()`` looking for a tool named
    ``finish_ai_block``. Category + mutation move to FastMCP tool
    annotations (decision deferred to I40a — see manifest §1.3 and
    system_prompt.py's _render_tool_catalog TODO comment).
    """
    from scieasy.ai.agent.mcp.server import mcp

    names = [tool["name"] for tool in mcp.list_tools()]
    assert "finish_ai_block" in names


@pytest.mark.skip(reason="S40a skeleton — I40a impl in Phase 2a. TODO(#1012): FastMCP 26-tool count.")
def test_registry_now_has_26_tools() -> None:
    """ADR-035 §3.5 + ADR-040 §3.1: FastMCP exposes 26 tools."""
    from scieasy.ai.agent.mcp.server import mcp

    assert len(mcp.list_tools()) == 26


def test_finish_ai_block_handler_has_docstring() -> None:
    """Every MCP tool must carry a non-empty docstring (existing convention).

    The function object is still importable in S40a — only its body
    raises NotImplementedError. Docstring conventions are enforced on
    the source object regardless of impl status.
    """
    from scieasy.ai.agent.mcp import tools_workflow

    assert (tools_workflow.finish_ai_block.__doc__ or "").strip()


# ---------------------------------------------------------------------------
# Behavioral tests — skip until implementation phase (I40a / I35b).
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="S40a skeleton — I40a impl in Phase 2a. TODO(#1012): not_in_ai_block_context envelope.")
def test_finish_ai_block_outside_context_returns_error_envelope() -> None:
    """ADR-035 §3.5: tool returns ``not_in_ai_block_context`` error when
    no active AI Block context is set on the MCP runtime.

    Test plan:
        1. Construct an MCP context where ``ai_block_run_dir`` is None.
        2. Call ``finish_ai_block({"out": "/tmp/x.csv"})``.
        3. Assert response is ``{"status": "error",
           "code": "not_in_ai_block_context", "message": ...}``.
    """
    raise NotImplementedError("skeleton")


@pytest.mark.skip(reason="S40a skeleton — I40a impl in Phase 2a. TODO(#1012): signal file happy path.")
def test_finish_ai_block_writes_signal_file() -> None:
    """ADR-035 §3.5 path (a) happy path.

    Test plan:
        1. Set up MCP context with ``ai_block_run_dir = tmp_path``.
        2. Create signals/ subdir.
        3. Call ``finish_ai_block({"metadata": "./out.csv"})``.
        4. Assert ``signals/finish_ai_block.json`` exists with
           ``{"outputs": {"metadata": "./out.csv"}, "timestamp": ...}``.
        5. Assert response is ``{"status": "ok", "signal_path": ...}``.
    """
    raise NotImplementedError("skeleton")


@pytest.mark.skip(reason="S40a skeleton — I40a impl in Phase 2a. TODO(#1012): already_finished envelope.")
def test_finish_ai_block_second_call_rejected() -> None:
    """ADR-035 §8 OQ-1 (tentative): second call returns already_finished."""
    raise NotImplementedError("skeleton")


@pytest.mark.skip(reason="S40a skeleton — I40a impl in Phase 2a. TODO(#1012): empty outputs allowed.")
def test_finish_ai_block_empty_outputs_allowed() -> None:
    """outputs={} signals 'trust expected_path' — still writes signal file."""
    raise NotImplementedError("skeleton")


@pytest.mark.skip(reason="S40a skeleton — I40a impl in Phase 2a. TODO(#1012): relative paths preserved.")
def test_finish_ai_block_relative_paths_preserved_in_signal() -> None:
    """Relative paths preserved verbatim — CompletionWatcher resolves them."""
    raise NotImplementedError("skeleton")


@pytest.mark.skip(reason="S40a skeleton — I40a impl in Phase 2a. TODO(#1012): io_error envelope.")
def test_finish_ai_block_disk_error_returns_error_envelope() -> None:
    """OS error during signal-file write → generic error envelope."""
    raise NotImplementedError("skeleton")
