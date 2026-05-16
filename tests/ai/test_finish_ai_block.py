"""Behavioural tests for the finish_ai_block MCP tool (ADR-035 §3.5 path a).

Calls go through ``asyncio.run`` because FastMCP-decorated tools are
async coroutines.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from scieasy.ai.agent.mcp import _context, tools_workflow


def _finish(outputs):
    """Helper: drive the async finish_ai_block."""
    return asyncio.run(tools_workflow.finish_ai_block(outputs))


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Clear AI Block env vars between tests."""
    monkeypatch.delenv("SCIEASY_AI_BLOCK_RUN_DIR", raising=False)
    saved = _context.get_optional_context()
    _context.set_context(None)
    yield
    _context.set_context(saved)


# ---------------------------------------------------------------------------
# not_in_ai_block_context envelope
# ---------------------------------------------------------------------------


def test_finish_ai_block_outside_context_returns_envelope() -> None:
    result = _finish({"out": "/tmp/x.csv"})
    assert result.status == "error"
    assert result.code == "not_in_ai_block_context"
    assert "AI Block" in result.message


def test_finish_ai_block_env_var_pointing_at_missing_dir_falls_through(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SCIEASY_AI_BLOCK_RUN_DIR", str(tmp_path / "does-not-exist"))
    result = _finish({})
    assert result.code == "not_in_ai_block_context"


# ---------------------------------------------------------------------------
# Happy path via env var
# ---------------------------------------------------------------------------


def test_finish_ai_block_writes_signal_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCIEASY_AI_BLOCK_RUN_DIR", str(tmp_path))
    result = _finish({"metadata": "./out.csv"})
    assert result.status == "ok"
    signal = Path(result.signal_path)
    assert signal.exists()
    assert signal.parent.name == "signals"
    payload = json.loads(signal.read_text())
    assert payload["outputs"] == {"metadata": "./out.csv"}
    assert "timestamp" in payload


def test_finish_ai_block_empty_outputs_allowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCIEASY_AI_BLOCK_RUN_DIR", str(tmp_path))
    result = _finish({})
    assert result.status == "ok"
    payload = json.loads(Path(result.signal_path).read_text())
    assert payload["outputs"] == {}


def test_finish_ai_block_none_outputs_allowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCIEASY_AI_BLOCK_RUN_DIR", str(tmp_path))
    result = _finish(None)
    assert result.status == "ok"
    assert json.loads(Path(result.signal_path).read_text())["outputs"] == {}


def test_finish_ai_block_relative_paths_preserved(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCIEASY_AI_BLOCK_RUN_DIR", str(tmp_path))
    rel = "./results/metadata.csv"
    result = _finish({"out": rel})
    payload = json.loads(Path(result.signal_path).read_text())
    assert payload["outputs"]["out"] == rel


# ---------------------------------------------------------------------------
# Multi-call rejection (ADR-035 §8 OQ-1)
# ---------------------------------------------------------------------------


def test_finish_ai_block_second_call_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCIEASY_AI_BLOCK_RUN_DIR", str(tmp_path))
    first = _finish({"out": "/tmp/a.csv"})
    assert first.status == "ok"
    second = _finish({"out": "/tmp/b.csv"})
    assert second.status == "error"
    assert second.code == "already_finished"


# ---------------------------------------------------------------------------
# Invalid outputs shape
# ---------------------------------------------------------------------------


def test_finish_ai_block_non_string_value_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCIEASY_AI_BLOCK_RUN_DIR", str(tmp_path))
    result = _finish({"out": 42})  # type: ignore[dict-item]
    assert result.status == "error"
    assert result.code == "invalid_outputs"


def test_finish_ai_block_non_dict_outputs_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCIEASY_AI_BLOCK_RUN_DIR", str(tmp_path))
    result = _finish(["not-a-dict"])  # type: ignore[arg-type]
    assert result.code == "invalid_outputs"


# ---------------------------------------------------------------------------
# IO error path
# ---------------------------------------------------------------------------


def test_finish_ai_block_io_error_returns_envelope(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCIEASY_AI_BLOCK_RUN_DIR", str(tmp_path))

    def boom(*a: object, **kw: object) -> object:
        raise OSError("disk full")

    monkeypatch.setattr(tools_workflow, "_atomic_write_text", boom)
    result = _finish({"out": "/tmp/x.csv"})
    assert result.status == "error"
    assert result.code == "io_error"
    assert "disk full" in result.message


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
        result = _finish({"out": "./x.csv"})
        assert result.status == "ok"
        assert Path(result.signal_path).exists()
    finally:
        _context.set_context(None)


def test_finish_ai_block_context_attr_takes_priority_over_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
        result = _finish({})
        assert result.status == "ok"
        assert (ctx_dir / "signals" / "finish_ai_block.json").exists()
        assert not (env_dir / "signals" / "finish_ai_block.json").exists()
    finally:
        _context.set_context(None)


def test_finish_ai_block_env_var_used_when_context_attr_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SCIEASY_AI_BLOCK_RUN_DIR", str(tmp_path))

    class _Ctx:
        block_registry = None  # type: ignore[assignment]
        type_registry = None  # type: ignore[assignment]
        project_dir = tmp_path
        # No ai_block_run_dir attr.

    _context.set_context(_Ctx())  # type: ignore[arg-type]
    try:
        result = _finish({})
        assert result.status == "ok"
    finally:
        _context.set_context(None)


# ---------------------------------------------------------------------------
# Module-level placement sanity
# ---------------------------------------------------------------------------


def test_run_dir_env_var_name_consumed_by_resolver() -> None:
    assert hasattr(tools_workflow, "_resolve_ai_block_run_dir")
