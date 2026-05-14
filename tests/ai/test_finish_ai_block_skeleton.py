"""Skeleton tests for the finish_ai_block MCP tool (ADR-035 §3.5 path a).

Path placed under ``tests/ai/`` to match the existing MCP test layout
(``test_mcp_tools_workflow.py`` etc.). Implementation phase (I35b) flips
each xfail to run=True as the tool is implemented.
"""

from __future__ import annotations

import pytest

from scieasy.ai.agent.mcp import _registry, tools_workflow

# ---------------------------------------------------------------------------
# Registry-shape tests (no NotImplementedError dependency).
# ---------------------------------------------------------------------------


def test_finish_ai_block_is_registered() -> None:
    """Tool exists in TOOL_REGISTRY with correct category + mutation."""
    entry = _registry.lookup("finish_ai_block")
    assert entry is not None
    assert entry.category == "workflow"
    assert entry.mutation == "write"
    assert entry.handler is tools_workflow.finish_ai_block


def test_registry_now_has_26_tools() -> None:
    """ADR-035 §3.5 added the 26th tool."""
    assert len(_registry.TOOL_REGISTRY) == 26


def test_finish_ai_block_handler_has_docstring() -> None:
    """Every MCP tool must carry a non-empty docstring (existing convention)."""
    assert (tools_workflow.finish_ai_block.__doc__ or "").strip()


# ---------------------------------------------------------------------------
# Behavioral tests — xfail until implementation phase (I35b).
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
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


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
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


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_finish_ai_block_second_call_rejected() -> None:
    """ADR-035 §8 OQ-1 (tentative): second call returns already_finished."""
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_finish_ai_block_empty_outputs_allowed() -> None:
    """outputs={} signals "trust expected_path" — still writes signal file."""
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_finish_ai_block_relative_paths_preserved_in_signal() -> None:
    """Relative paths preserved verbatim — CompletionWatcher resolves them."""
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_finish_ai_block_disk_error_returns_error_envelope() -> None:
    """OS error during signal-file write → generic error envelope."""
    raise NotImplementedError("skeleton")
