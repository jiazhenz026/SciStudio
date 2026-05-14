"""Skeleton-phase tests for AIBlock (ADR-035 §3.1, §3.2, §3.5, §3.6, §3.9).

All tests are ``xfail`` with the test plan in their docstring. The
implementation phase (I35a) flips each one to ``run=True`` once the
behavior is implemented.

References:
    docs/adr/ADR-035.md §3
    docs/planning/agent-prompt-templates/skeleton-agent.md §3
"""

from __future__ import annotations

import pytest

from scieasy.blocks.ai.ai_block import AIBlock
from scieasy.blocks.base.state import ExecutionMode

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
    """Config schema must declare provider, permission_mode, user_prompt, timeout."""
    schema = AIBlock.config_schema
    props = schema["properties"]
    assert "provider" in props
    assert "permission_mode" in props
    assert "user_prompt" in props
    assert "timeout_sec" in props
    assert schema["required"] == ["user_prompt"]


# ---------------------------------------------------------------------------
# Behavioral tests — xfail until I35a implements run() / validate().
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_run_writes_manifest_with_correct_shape() -> None:
    """ADR-035 §3.4 manifest schema.

    Test plan:
        1. Construct AIBlock with one input port "files" (Artifact list)
           and one output port "metadata" (DataFrame, expected_path
           "./out.csv").
        2. Mock RunDir.write_manifest to capture its args.
        3. Mock request_pty_tab to return a fake tab_id and immediately
           write a finish_ai_block signal file.
        4. Call AIBlock.run() with the inputs dict.
        5. Assert RunDir.write_manifest was called with:
           - block name + type matching the AIBlock instance
           - inputs dict with verbatim file paths (no rewriting)
           - outputs dict with the expected_path verbatim
           - completion deadline as ISO-8601 UTC string
    """
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_run_request_pty_tab_with_safe_permission() -> None:
    """ADR-035 §3.7: safe mode passes default --permission-mode to spawn.

    Test plan:
        1. Configure AIBlock with permission_mode="safe".
        2. Mock request_pty_tab; capture spawn_argv.
        3. Run.
        4. Assert spawn_argv contains "--permission-mode" with the
           provider's safe-mode value (NOT "bypassPermissions").
    """
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_run_request_pty_tab_with_bypass_permission() -> None:
    """ADR-035 §3.7: bypass mode passes the right flag per provider.

    Test plan:
        1. permission_mode="bypass", provider="claude-code".
        2. Mock request_pty_tab.
        3. Assert spawn_argv contains "--permission-mode" "bypassPermissions".
        4. Repeat for provider="codex" → expect
           "--dangerously-bypass-approvals-and-sandbox".
    """
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_run_completion_via_mcp_finish_ai_block() -> None:
    """ADR-035 §3.5 path (a): MCP signal triggers validation+done.

    Test plan:
        1. Configure block with output port "metadata" (DataFrame, ./out.csv).
        2. Pre-create ./out.csv with valid CSV content.
        3. Mock request_pty_tab; immediately write
           {"outputs": {"metadata": "./out.csv"}} to the MCP signal file.
        4. Run.
        5. Assert returned dict has key "metadata" wrapped in a Collection.
        6. Assert the loaded DataFrame matches the file content.
    """
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_run_completion_via_file_watcher() -> None:
    """ADR-035 §3.5 path (b): all expected_path files exist + stable for 2s.

    Test plan:
        1. Mock request_pty_tab; do NOT write the MCP signal.
        2. Wait briefly, then create the expected_path file with valid content.
        3. Wait 2.5s (> stability_period).
        4. Assert run() returns successfully via FILE_WATCHER source.
    """
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_run_completion_via_mark_done_button() -> None:
    """ADR-035 §3.5 path (c): user-button signal file triggers completion.

    Test plan:
        1. Pre-create expected_path file (so validation succeeds).
        2. Mock request_pty_tab; write mark_done.json to signal dir.
        3. Assert run() returns via USER_MARK_DONE source.
    """
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_run_validation_fail_returns_error_state() -> None:
    """ADR-035 §3.6: loader exception → ERROR with termination_detail.

    Test plan:
        1. Configure output port type=DataFrame, expected_path "./bad.csv".
        2. Pre-create ./bad.csv with malformed CSV.
        3. Trigger MCP signal completion.
        4. Assert run() raises (or returns ERROR per Block contract) with
           the loader exception text and the path.
        5. Assert the .scieasy/ai-block-runs/{run_id}/ dir is preserved.
    """
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_run_spawn_fail_returns_error() -> None:
    """ADR-035 §3.8 run-time tier: spawn failure → ERROR.

    Test plan:
        1. Mock request_pty_tab to raise FileNotFoundError("claude binary").
        2. Assert run() ERRORs with that exception in termination_detail.
    """
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_run_user_close_tab_cancels() -> None:
    """ADR-035 §3.9: user closes tab → CANCELLED.

    Test plan:
        1. Mock request_pty_tab; do NOT signal completion.
        2. After short delay, simulate user-tab-close via worker IPC.
        3. Assert block transitions to CANCELLED, no outputs returned.
    """
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_run_timeout_cancels() -> None:
    """ADR-035 §3.9: timeout exceeded → CANCELLED with detail="timeout".

    Test plan:
        1. Configure timeout_sec=1.
        2. Mock request_pty_tab; never signal completion.
        3. Wait 1.5s.
        4. Assert run() raises TimeoutError or returns CANCELLED.
    """
    raise NotImplementedError("skeleton")


@pytest.mark.xfail(reason="skeleton — implementation phase fills in", run=False)
def test_validate_fails_with_install_hint_when_missing() -> None:
    """ADR-035 §3.8 validate-time tier.

    Test plan:
        1. Monkeypatch discover_claude_code() to return None.
        2. AIBlock.validate(config) must raise ValueError whose message
           contains the exact ``scieasy install`` invocation.
    """
    raise NotImplementedError("skeleton")
