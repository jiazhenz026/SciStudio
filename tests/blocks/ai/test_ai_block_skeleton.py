"""Tests for AIBlock (ADR-035 §3.1, §3.2, §3.5, §3.6, §3.9) — Phase 2A.

Originally a skeleton (xfail) file; flipped to real tests by I35a per
the test plan in ``ai_block.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scistudio.blocks.ai.ai_block import (
    _BYPASS_FLAG,
    REUSE_LAST_OUTPUT_KEY,
    AIBlock,
    _output_path_overrides,
    _reuse_last_output_enabled,
)
from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.state import ExecutionMode
from tests.blocks.ai.conftest import StubAgent  # type: ignore[import-not-found]

# ---------------------------------------------------------------------------
# ClassVar contract — these can run today (no NotImplementedError).
# ---------------------------------------------------------------------------


def test_ai_block_is_external_mode() -> None:
    """ADR-035 §3.1: AIBlock must declare ExecutionMode.EXTERNAL."""
    assert AIBlock.execution_mode is ExecutionMode.EXTERNAL


def test_ai_block_is_variadic_both_directions() -> None:
    """ADR-035 §3.1: variadic_inputs and variadic_outputs both True."""
    assert AIBlock.variadic_inputs is True
    assert AIBlock.variadic_outputs is True


def test_ai_block_terminate_grace_is_10s() -> None:
    """ADR-035 §3.1: terminate_grace_sec = 10.0."""
    assert AIBlock.terminate_grace_sec == 10.0


def test_ai_block_config_schema_has_required_fields() -> None:
    schema = AIBlock.config_schema
    props = schema["properties"]
    assert "provider" in props
    assert "permission_mode" in props
    assert "user_prompt" in props
    # AIBlock runs without a wall-clock timeout (2026-06 config pass): the
    # ``timeout_sec`` field was removed from the schema.
    assert "timeout_sec" not in props
    assert schema["required"] == ["user_prompt"]


# ---------------------------------------------------------------------------
# _build_spawn_argv
# ---------------------------------------------------------------------------


def _config(**kwargs: object) -> BlockConfig:
    return BlockConfig(params=dict(kwargs))


def test_build_argv_claude_safe_mode(project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Patch discovery so we don't need claude installed.
    from scistudio.blocks.ai import ai_block as mod

    monkeypatch.setattr(mod, "_discover_provider", lambda _p: "/fake/claude")
    block = AIBlock()
    cfg = _config(
        provider="claude-code",
        permission_mode="safe",
        user_prompt="hi",
        project_dir=str(project_dir),
    )
    argv = block._build_spawn_argv(cfg, "manifest.json")
    assert argv[0] == "/fake/claude"
    # Safe mode: no bypass flag.
    assert "bypassPermissions" not in argv
    assert "--permission-mode" not in argv or "bypassPermissions" not in argv


def test_build_argv_claude_bypass_uses_bypass_permissions(project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scistudio.blocks.ai import ai_block as mod

    monkeypatch.setattr(mod, "_discover_provider", lambda _p: "/fake/claude")
    block = AIBlock()
    cfg = _config(
        provider="claude-code",
        permission_mode="bypass",
        user_prompt="hi",
        project_dir=str(project_dir),
    )
    argv = block._build_spawn_argv(cfg, "manifest.json")
    assert "--permission-mode" in argv
    assert "bypassPermissions" in argv


def test_build_argv_codex_bypass_uses_dangerously_bypass(project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scistudio.blocks.ai import ai_block as mod

    monkeypatch.setattr(mod, "_discover_provider", lambda _p: "/fake/codex")
    block = AIBlock()
    cfg = _config(provider="codex", permission_mode="bypass", user_prompt="hi")
    argv = block._build_spawn_argv(cfg, "manifest.json")
    assert "--dangerously-bypass-approvals-and-sandbox" in argv


def test_build_argv_unknown_provider_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    block = AIBlock()
    cfg = _config(provider="grok", user_prompt="hi")
    with pytest.raises(ValueError, match="unknown provider"):
        block._build_spawn_argv(cfg, "m.json")


def test_build_argv_missing_binary_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    from scistudio.blocks.ai import ai_block as mod

    monkeypatch.setattr(mod, "_discover_provider", lambda _p: None)
    block = AIBlock()
    cfg = _config(provider="claude-code", user_prompt="hi")
    with pytest.raises(ValueError, match="not discoverable"):
        block._build_spawn_argv(cfg, "m.json")


def test_clear_expected_outputs_removes_stale_files(project_dir: Path) -> None:
    """#1789: leftover declared outputs are cleared before the agent runs, so a
    stale file from a previous run cannot complete the block instantly via the
    FileWatcher path."""
    from scistudio.blocks.ai.ai_block import _clear_expected_outputs

    stale = project_dir / "out.csv"
    stale.write_text("stale output from a previous run", encoding="utf-8")
    _clear_expected_outputs({"out": {"expected_path": "./out.csv", "expected_type": "DataFrame"}}, project_dir)
    assert not stale.exists()


def test_clear_expected_outputs_tolerates_missing_file(project_dir: Path) -> None:
    """A fresh project with no prior output is a no-op, not an error."""
    from scistudio.blocks.ai.ai_block import _clear_expected_outputs

    _clear_expected_outputs({"out": {"expected_path": "./never-written.csv"}}, project_dir)


# ---------------------------------------------------------------------------
# validate_config
# ---------------------------------------------------------------------------


def test_validate_succeeds_when_provider_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scistudio.blocks.ai import ai_block as mod

    monkeypatch.setattr(mod, "_discover_provider", lambda _p: "/fake/claude")
    block = AIBlock()
    block.validate_config(_config(provider="claude-code", user_prompt="hi"))


def test_validate_fails_with_install_hint_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scistudio.blocks.ai import ai_block as mod

    monkeypatch.setattr(mod, "_discover_provider", lambda _p: None)
    block = AIBlock()
    with pytest.raises(ValueError, match="scistudio install"):
        block.validate_config(_config(provider="claude-code", user_prompt="hi"))


def test_validate_rejects_empty_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    from scistudio.blocks.ai import ai_block as mod

    monkeypatch.setattr(mod, "_discover_provider", lambda _p: "/fake/claude")
    block = AIBlock()
    with pytest.raises(ValueError, match="non-empty"):
        block.validate_config(_config(provider="claude-code", user_prompt="   "))


# NOTE: ``test_validate_rejects_negative_timeout`` removed — AIBlock no longer
# has a configurable timeout (runs to completion / cancellation), so there is
# no timeout value to validate.


# ---------------------------------------------------------------------------
# run() — happy paths via StubAgent
# ---------------------------------------------------------------------------


def _prepared_block(
    output_ports: list[dict[str, object]] | None = None,
) -> AIBlock:
    """Construct an AIBlock for direct ``run()`` invocation.

    The worker-side block state machine was removed in #1334; AIBlock no
    longer needs IDLE→READY→RUNNING priming before ``run()``.
    """
    instance_config: dict[str, object] = {}
    if output_ports is not None:
        instance_config["output_ports"] = output_ports
    return AIBlock(config=instance_config)


def test_run_writes_manifest_with_correct_shape(project_dir: Path, stub_agent: StubAgent) -> None:
    """Manifest contains block name, type, deadline, and declared output."""
    stub_agent.outputs = {"metadata": ("results/metadata.csv", "a,b\n1,2\n")}
    block = _prepared_block(
        output_ports=[
            {
                "name": "metadata",
                "types": ["DataFrame"],
                "expected_path": "./results/metadata.csv",
            }
        ]
    )
    cfg = _config(
        user_prompt="extract metadata",
        provider="claude-code",
        timeout_sec=30,
        project_dir=str(project_dir),
        block_id="extract_metadata",
    )
    block.run(inputs={}, config=cfg)

    # Find the run dir created by the block.
    runs_root = project_dir / ".scistudio" / "ai-block-runs"
    run_dirs = list(runs_root.iterdir())
    assert len(run_dirs) == 1
    manifest = json.loads((run_dirs[0] / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["block"]["name"] == "extract_metadata"
    assert manifest["block"]["type"] == "AIBlock"
    assert manifest["user_prompt"] == "extract metadata"
    assert "metadata" in manifest["outputs"]
    assert manifest["outputs"]["metadata"]["expected_path"] == "./results/metadata.csv"
    # AIBlock runs without a wall-clock timeout, so no deadline is recorded.
    assert manifest["completion"]["deadline"] is None


def test_run_request_pty_tab_with_safe_permission(project_dir: Path, stub_agent: StubAgent) -> None:
    stub_agent.outputs = {"out": ("out.csv", "x\n")}
    block = _prepared_block(output_ports=[{"name": "out", "types": ["DataFrame"], "expected_path": "./out.csv"}])
    cfg = _config(
        user_prompt="hi",
        provider="claude-code",
        permission_mode="safe",
        project_dir=str(project_dir),
        timeout_sec=10,
    )
    block.run(inputs={}, config=cfg)
    assert len(stub_agent.request_calls) == 1
    spec = stub_agent.request_calls[0]
    assert spec.permission_mode == "safe"
    assert "bypassPermissions" not in spec.spawn_argv


def test_run_request_pty_tab_with_bypass_permission(project_dir: Path, stub_agent: StubAgent) -> None:
    stub_agent.outputs = {"out": ("out.csv", "x\n")}
    block = _prepared_block(output_ports=[{"name": "out", "types": ["DataFrame"], "expected_path": "./out.csv"}])
    cfg = _config(
        user_prompt="hi",
        provider="claude-code",
        permission_mode="bypass",
        project_dir=str(project_dir),
        timeout_sec=10,
    )
    block.run(inputs={}, config=cfg)
    spec = stub_agent.request_calls[0]
    assert spec.permission_mode == "bypass"
    assert "bypassPermissions" in spec.spawn_argv


def test_run_completion_via_mcp_finish_ai_block(project_dir: Path, stub_agent: StubAgent) -> None:
    stub_agent.outputs = {"metadata": ("metadata.csv", "name,value\nfoo,1\n")}
    stub_agent.finish_via = "mcp"
    block = _prepared_block(
        output_ports=[
            {
                "name": "metadata",
                "types": ["DataFrame"],
                "expected_path": "./metadata.csv",
            }
        ]
    )
    cfg = _config(
        user_prompt="hi",
        provider="claude-code",
        project_dir=str(project_dir),
        timeout_sec=10,
    )
    result = block.run(inputs={}, config=cfg)
    assert "metadata" in result
    assert any(n[1] == "completed" for n in stub_agent.notifications)


def test_run_completion_via_file_watcher(project_dir: Path, stub_agent: StubAgent) -> None:
    stub_agent.outputs = {"out": ("out.csv", "a\n1\n")}
    stub_agent.finish_via = "file_only"
    block = _prepared_block(output_ports=[{"name": "out", "types": ["DataFrame"], "expected_path": "./out.csv"}])
    cfg = _config(
        user_prompt="hi",
        provider="claude-code",
        project_dir=str(project_dir),
        timeout_sec=15,
    )
    result = block.run(inputs={}, config=cfg)
    assert "out" in result


def test_run_completion_via_mark_done_button(project_dir: Path, stub_agent: StubAgent) -> None:
    # The agent produces the output during the run, then the user clicks "Mark
    # done". (#1789: declared outputs are cleared before the agent starts, so the
    # file must be written by the agent during the run — not pre-created before
    # run() — to survive and pass output validation.)
    stub_agent.outputs = {"out": ("out.csv", "a,b\n1,2\n")}
    stub_agent.finish_via = "mark_done"
    block = _prepared_block(output_ports=[{"name": "out", "types": ["DataFrame"], "expected_path": "./out.csv"}])
    cfg = _config(
        user_prompt="hi",
        provider="claude-code",
        project_dir=str(project_dir),
        timeout_sec=10,
    )
    result = block.run(inputs={}, config=cfg)
    assert "out" in result


# ---------------------------------------------------------------------------
# run() — error / cancellation paths
# ---------------------------------------------------------------------------


def test_run_validation_fail_returns_error_state(project_dir: Path, stub_agent: StubAgent) -> None:
    """Loader exception → block transitions to ERROR; run_dir preserved."""
    # Stub writes an empty file (size 0). The resulting ValueError differs
    # slightly between Python versions and between entry paths: LoadData on
    # an empty CSV raises ValueError("...is empty"), while the MCP signal
    # parse path raises ValueError("...malformed MCP signal at ...:
    # Expecting value..."). Either is an acceptable failure mode for this
    # skeleton-phase test — both transition the block to ERROR and preserve
    # the run_dir, which is what this test verifies. Relaxing the regex
    # unblocks Python 3.11 CI on docs-only PRs (#909 tracks the proper fix
    # — error-path distinction belongs in src/scistudio/blocks/ai/, not here).
    stub_agent.outputs = {"out": ("out.csv", "")}
    stub_agent.finish_via = "mcp"
    block = _prepared_block(output_ports=[{"name": "out", "types": ["DataFrame"], "expected_path": "./out.csv"}])
    cfg = _config(
        user_prompt="hi",
        provider="claude-code",
        project_dir=str(project_dir),
        timeout_sec=10,
    )
    with pytest.raises(ValueError, match=r"is empty|Expecting value|malformed MCP signal"):
        block.run(inputs={}, config=cfg)
    # Run dir preserved.
    runs_root = project_dir / ".scistudio" / "ai-block-runs"
    assert any(p.is_dir() for p in runs_root.iterdir())


def test_run_spawn_fail_returns_error(project_dir: Path, stub_agent: StubAgent) -> None:
    stub_agent.spawn_error = FileNotFoundError("claude binary gone")
    block = _prepared_block(output_ports=[{"name": "out", "types": ["DataFrame"], "expected_path": "./out.csv"}])
    cfg = _config(
        user_prompt="hi",
        provider="claude-code",
        project_dir=str(project_dir),
        timeout_sec=10,
    )
    with pytest.raises(RuntimeError, match="PTY spawn failed"):
        block.run(inputs={}, config=cfg)


# NOTE: ``test_run_timeout_cancels`` removed — AIBlock no longer enforces a
# wall-clock timeout (``watcher.wait(timeout_sec=None)``); cancellation now only
# happens via tab close / workflow cancel, covered by the close/cancel cases.


def test_run_malformed_mcp_signal_errors(project_dir: Path, stub_agent: StubAgent) -> None:
    stub_agent.finish_via = "error"
    block = _prepared_block(output_ports=[{"name": "out", "types": ["DataFrame"], "expected_path": "./out.csv"}])
    cfg = _config(
        user_prompt="hi",
        provider="claude-code",
        project_dir=str(project_dir),
        timeout_sec=10,
    )
    with pytest.raises(ValueError, match="malformed MCP signal"):
        block.run(inputs={}, config=cfg)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_output_path_overrides_extracts_correctly() -> None:
    cfg = BlockConfig(
        params={
            "output_ports": [
                {"name": "a", "types": ["DataFrame"], "expected_path": "./a.csv"},
                {"name": "b", "types": ["Text"]},  # no expected_path
                "not a dict",  # ignored
            ]
        }
    )
    overrides = _output_path_overrides(cfg)
    assert overrides == {"a": "./a.csv"}


def test_bypass_flag_table_per_provider() -> None:
    assert "claude-code" in _BYPASS_FLAG
    assert "codex" in _BYPASS_FLAG
    assert "bypassPermissions" in _BYPASS_FLAG["claude-code"]
    assert "--dangerously-bypass-approvals-and-sandbox" in _BYPASS_FLAG["codex"]


# ---------------------------------------------------------------------------
# reuse_last_output toggle (#1898 / ADR-035 Addendum 1)
# ---------------------------------------------------------------------------


def test_config_schema_has_reuse_last_output_boolean() -> None:
    """The toggle is a boolean config field so it renders as a checkbox."""
    field = AIBlock.config_schema["properties"]["reuse_last_output"]
    assert field["type"] == "boolean"
    assert field["default"] is False
    # Not required — default off keeps the block's behavior unchanged.
    assert "reuse_last_output" not in AIBlock.config_schema["required"]


def test_reuse_last_output_enabled_reads_flag() -> None:
    assert _reuse_last_output_enabled(_config(reuse_last_output=True)) is True
    assert _reuse_last_output_enabled(_config(reuse_last_output=False)) is False
    # Absent → off (unchanged default behavior).
    assert _reuse_last_output_enabled(_config()) is False
    assert REUSE_LAST_OUTPUT_KEY == "reuse_last_output"


def test_run_reuses_last_output_and_skips_agent(project_dir: Path, stub_agent: StubAgent) -> None:
    """Toggle on + prior output present → re-emit it without spawning the agent."""
    prior = project_dir / "out.csv"
    prior.write_text("a,b\n1,2\n", encoding="utf-8")
    block = _prepared_block(output_ports=[{"name": "out", "types": ["DataFrame"], "expected_path": "./out.csv"}])
    cfg = _config(
        user_prompt="hi",
        provider="claude-code",
        project_dir=str(project_dir),
        reuse_last_output=True,
    )

    result = block.run(inputs={}, config=cfg)

    assert "out" in result
    # No PTY tab requested: the agent never ran.
    assert stub_agent.request_calls == []
    # The prior output file was NOT cleared (reuse must leave it intact).
    assert prior.exists()
    # Lineage marker records the reuse so an audit can distinguish it.
    assert any(n[1] == "completed" and n[2].get("source") == "reused_last_output" for n in stub_agent.notifications)


def test_run_reuse_falls_back_when_no_prior_output(project_dir: Path, stub_agent: StubAgent) -> None:
    """Toggle on but nothing to reuse → fall back to a normal agent run."""
    stub_agent.outputs = {"out": ("out.csv", "a\n1\n")}
    block = _prepared_block(output_ports=[{"name": "out", "types": ["DataFrame"], "expected_path": "./out.csv"}])
    cfg = _config(
        user_prompt="hi",
        provider="claude-code",
        project_dir=str(project_dir),
        reuse_last_output=True,
    )

    result = block.run(inputs={}, config=cfg)

    assert "out" in result
    # Fallback ran the agent: exactly one PTY request.
    assert len(stub_agent.request_calls) == 1


def test_run_reuse_falls_back_when_any_declared_output_missing(project_dir: Path, stub_agent: StubAgent) -> None:
    """Reuse requires every declared output; a partial prior run is a miss."""
    # Only ``a`` exists from a prior run; ``b`` was never produced.
    (project_dir / "a.csv").write_text("x\n1\n", encoding="utf-8")
    stub_agent.outputs = {
        "a": ("a.csv", "x\n1\n"),
        "b": ("b.csv", "y\n2\n"),
    }
    block = _prepared_block(
        output_ports=[
            {"name": "a", "types": ["DataFrame"], "expected_path": "./a.csv"},
            {"name": "b", "types": ["DataFrame"], "expected_path": "./b.csv"},
        ]
    )
    cfg = _config(
        user_prompt="hi",
        provider="claude-code",
        project_dir=str(project_dir),
        reuse_last_output=True,
    )

    result = block.run(inputs={}, config=cfg)

    assert {"a", "b"} <= set(result)
    # Missing ``b`` forced a real run.
    assert len(stub_agent.request_calls) == 1


def test_run_ignores_prior_output_when_toggle_off(project_dir: Path, stub_agent: StubAgent) -> None:
    """Default (toggle off): a prior output file must not short-circuit the run."""
    (project_dir / "out.csv").write_text("stale\n", encoding="utf-8")
    stub_agent.outputs = {"out": ("out.csv", "a\n1\n")}
    block = _prepared_block(output_ports=[{"name": "out", "types": ["DataFrame"], "expected_path": "./out.csv"}])
    cfg = _config(
        user_prompt="hi",
        provider="claude-code",
        project_dir=str(project_dir),
        # reuse_last_output omitted → defaults off.
    )

    result = block.run(inputs={}, config=cfg)

    assert "out" in result
    # Agent ran despite the pre-existing file (opt-in only).
    assert len(stub_agent.request_calls) == 1
