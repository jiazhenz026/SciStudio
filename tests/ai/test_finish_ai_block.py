"""Behavioural tests for the finish_ai_block MCP tool (ADR-035 §3.5 path a).

The skeleton-only registry-shape tests live in
``tests/ai/test_finish_ai_block_skeleton.py``; this file adds the
behavioural tests the skeleton's test plan listed.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

# TODO(#1012): module-level skip during ADR-040 §3.1 FastMCP skeleton
#   phase. finish_ai_block body is a NotImplementedError stub in S40a;
#   I40a Phase 2a restores behavior. Out of scope per ADR-040 §3.1 /
#   phase: 2a I40a. Followup: #1012.
pytestmark = pytest.mark.skip(
    reason="S40a skeleton — finish_ai_block body is NotImplementedError. TODO(#1012): I40a Phase 2a restores."
)

from scieasy.ai.agent.mcp import _context, tools_workflow  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Clear AI Block env vars between tests."""
    monkeypatch.delenv("SCIEASY_AI_BLOCK_RUN_DIR", raising=False)
    # Ensure no stale MCPContext leaks across tests.
    saved = _context.get_optional_context()
    _context.set_context(None)
    yield
    _context.set_context(saved)


# ---------------------------------------------------------------------------
# not_in_ai_block_context envelope
# ---------------------------------------------------------------------------


def test_finish_ai_block_outside_context_returns_envelope() -> None:
    result = tools_workflow.finish_ai_block({"out": "/tmp/x.csv"})
    assert result["status"] == "error"
    assert result["code"] == "not_in_ai_block_context"
    assert "AI Block" in result["message"]


def test_finish_ai_block_env_var_pointing_at_missing_dir_falls_through(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Env var pointing at a non-existent dir is ignored — context check still wins."""
    monkeypatch.setenv("SCIEASY_AI_BLOCK_RUN_DIR", str(tmp_path / "does-not-exist"))
    result = tools_workflow.finish_ai_block({})
    assert result["code"] == "not_in_ai_block_context"


# ---------------------------------------------------------------------------
# Happy path via env var
# ---------------------------------------------------------------------------


def test_finish_ai_block_writes_signal_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCIEASY_AI_BLOCK_RUN_DIR", str(tmp_path))
    result = tools_workflow.finish_ai_block({"metadata": "./out.csv"})
    assert result["status"] == "ok"
    signal = Path(result["signal_path"])
    assert signal.exists()
    assert signal.parent.name == "signals"
    payload = json.loads(signal.read_text())
    assert payload["outputs"] == {"metadata": "./out.csv"}
    assert "timestamp" in payload


def test_finish_ai_block_empty_outputs_allowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCIEASY_AI_BLOCK_RUN_DIR", str(tmp_path))
    result = tools_workflow.finish_ai_block({})
    assert result["status"] == "ok"
    payload = json.loads(Path(result["signal_path"]).read_text())
    assert payload["outputs"] == {}


def test_finish_ai_block_none_outputs_allowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCIEASY_AI_BLOCK_RUN_DIR", str(tmp_path))
    result = tools_workflow.finish_ai_block(None)
    assert result["status"] == "ok"
    assert json.loads(Path(result["signal_path"]).read_text())["outputs"] == {}


def test_finish_ai_block_relative_paths_preserved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCIEASY_AI_BLOCK_RUN_DIR", str(tmp_path))
    rel = "./results/metadata.csv"
    result = tools_workflow.finish_ai_block({"out": rel})
    payload = json.loads(Path(result["signal_path"]).read_text())
    assert payload["outputs"]["out"] == rel


# ---------------------------------------------------------------------------
# Multi-call rejection (ADR-035 §8 OQ-1 tentative)
# ---------------------------------------------------------------------------


def test_finish_ai_block_second_call_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCIEASY_AI_BLOCK_RUN_DIR", str(tmp_path))
    first = tools_workflow.finish_ai_block({"out": "/tmp/a.csv"})
    assert first["status"] == "ok"
    second = tools_workflow.finish_ai_block({"out": "/tmp/b.csv"})
    assert second["status"] == "error"
    assert second["code"] == "already_finished"


# ---------------------------------------------------------------------------
# Invalid outputs shape
# ---------------------------------------------------------------------------


def test_finish_ai_block_non_string_value_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCIEASY_AI_BLOCK_RUN_DIR", str(tmp_path))
    result = tools_workflow.finish_ai_block({"out": 42})  # type: ignore[dict-item]
    assert result["status"] == "error"
    assert result["code"] == "invalid_outputs"


def test_finish_ai_block_non_dict_outputs_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCIEASY_AI_BLOCK_RUN_DIR", str(tmp_path))
    result = tools_workflow.finish_ai_block(["not-a-dict"])  # type: ignore[arg-type]
    assert result["code"] == "invalid_outputs"


# ---------------------------------------------------------------------------
# IO error path
# ---------------------------------------------------------------------------


def test_finish_ai_block_io_error_returns_envelope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCIEASY_AI_BLOCK_RUN_DIR", str(tmp_path))

    def boom(*a: object, **kw: object) -> object:
        raise OSError("disk full")

    monkeypatch.setattr(tools_workflow, "_atomic_write_text", boom)
    result = tools_workflow.finish_ai_block({"out": "/tmp/x.csv"})
    assert result["status"] == "error"
    assert result["code"] == "io_error"
    assert "disk full" in result["message"]


# ---------------------------------------------------------------------------
# MCPContext attribute path (production wiring)
# ---------------------------------------------------------------------------


def test_finish_ai_block_via_mcp_context_attr(tmp_path: Path) -> None:
    class _Ctx:
        block_registry = None  # type: ignore[assignment]
        type_registry = None  # type: ignore[assignment]
        project_dir = tmp_path
        ai_block_run_dir = tmp_path

    _context.set_context(_Ctx())  # type: ignore[arg-type]
    try:
        result = tools_workflow.finish_ai_block({"out": "./x.csv"})
        assert result["status"] == "ok"
        assert Path(result["signal_path"]).exists()
    finally:
        _context.set_context(None)


def test_finish_ai_block_context_attr_takes_priority_over_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When both context attr and env var are set, the context wins."""
    ctx_dir = tmp_path / "ctx"
    env_dir = tmp_path / "env"
    ctx_dir.mkdir()
    env_dir.mkdir()
    monkeypatch.setenv("SCIEASY_AI_BLOCK_RUN_DIR", str(env_dir))

    class _Ctx:
        block_registry = None  # type: ignore[assignment]
        type_registry = None  # type: ignore[assignment]
        project_dir = ctx_dir
        ai_block_run_dir = ctx_dir

    _context.set_context(_Ctx())  # type: ignore[arg-type]
    try:
        result = tools_workflow.finish_ai_block({})
        assert result["status"] == "ok"
        # The signal file landed in the context dir, NOT env dir.
        assert (ctx_dir / "signals" / "finish_ai_block.json").exists()
        assert not (env_dir / "signals" / "finish_ai_block.json").exists()
    finally:
        _context.set_context(None)


def test_finish_ai_block_env_var_used_when_context_attr_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Env var fallback fires when MCPContext lacks the attribute."""
    monkeypatch.setenv("SCIEASY_AI_BLOCK_RUN_DIR", str(tmp_path))

    class _Ctx:
        block_registry = None  # type: ignore[assignment]
        type_registry = None  # type: ignore[assignment]
        project_dir = tmp_path
        # No ai_block_run_dir attr at all.

    _context.set_context(_Ctx())  # type: ignore[arg-type]
    try:
        result = tools_workflow.finish_ai_block({})
        assert result["status"] == "ok"
    finally:
        _context.set_context(None)


# ---------------------------------------------------------------------------
# Module-level placement (sanity)
# ---------------------------------------------------------------------------


def test_run_dir_env_var_name_consumed_by_resolver() -> None:
    """The resolver function exists at module scope under its expected name."""
    assert hasattr(tools_workflow, "_resolve_ai_block_run_dir")
