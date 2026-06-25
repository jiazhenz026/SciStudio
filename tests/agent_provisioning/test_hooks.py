"""Tests for ``agent_provisioning.hooks`` (ADR-040 §3.6).

Covers settings.json shape, hook script provisioning, idempotency, and
per-hook behavior smoke-tests against synthetic JSON stdin payloads.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scistudio.agent_provisioning.hooks import write_hooks

_HOOK_NAMES = (
    "worktree_write_guard.py",
    "deny_scistudio_cli.py",
    "protect_workflow_yaml.py",
    "enforce_list_blocks_before_block_write.py",
    "remind_poll_status.py",
    "mark_list_blocks_called.py",
    "enforce_concrete_port_types.py",
)


def test_write_hooks_creates_settings_json(tmp_project_dir: Path) -> None:
    """``.claude/settings.json`` exists with PreToolUse + PostToolUse arrays."""
    written = write_hooks(tmp_project_dir, force=False)
    assert ".claude/settings.json" in written

    raw = (tmp_project_dir / ".claude" / "settings.json").read_text(encoding="utf-8")
    data = json.loads(raw)
    assert "hooks" in data
    pre = data["hooks"]["PreToolUse"]
    post = data["hooks"]["PostToolUse"]
    assert len(pre) == 4
    assert len(post) == 3

    # Every entry references a python interpreter and a hook script path.
    for entry in pre + post:
        cmd = entry["hooks"][0]["command"]
        assert sys.executable in cmd
        assert "$CLAUDE_PROJECT_DIR" in cmd
        assert ".claude/hooks/" in cmd

    # Codex P1 (PR #1047): MultiEdit must be in every Edit|Write matcher
    # so multi-edit operations are not a bypass path.
    write_or_multi_matchers = [entry["matcher"] for entry in pre + post if "Edit" in entry["matcher"]]
    assert write_or_multi_matchers, "expected at least one Edit|Write|... matcher"
    for matcher in write_or_multi_matchers:
        assert "MultiEdit" in matcher, f"matcher missing MultiEdit: {matcher!r}"


def test_write_hooks_copies_hook_scripts(tmp_project_dir: Path) -> None:
    """All canonical hook scripts land in .claude/hooks/."""
    write_hooks(tmp_project_dir, force=False)
    hooks_dir = tmp_project_dir / ".claude" / "hooks"
    for name in _HOOK_NAMES:
        assert (hooks_dir / name).is_file(), f"missing hook: {name}"


def test_write_hooks_idempotent_preserves_user_edits(tmp_project_dir: Path) -> None:
    """force=False does not overwrite user-customized settings.json."""
    write_hooks(tmp_project_dir, force=False)

    custom = {"hooks": {"PreToolUse": [], "PostToolUse": [], "_custom": "user-added"}}
    (tmp_project_dir / ".claude" / "settings.json").write_text(json.dumps(custom), encoding="utf-8")

    written = write_hooks(tmp_project_dir, force=False)
    assert ".claude/settings.json" not in written
    data = json.loads((tmp_project_dir / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert data.get("hooks", {}).get("_custom") == "user-added"


def test_write_hooks_upgrades_legacy_python_commands(tmp_project_dir: Path) -> None:
    """Old generated hooks used PATH ``python``; reopen should repair them."""
    settings_path = tmp_project_dir / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    legacy = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": 'python "$CLAUDE_PROJECT_DIR/.claude/hooks/deny_scistudio_cli.py"',
                        }
                    ],
                }
            ],
            "PostToolUse": [],
            "_custom": "user-added",
        }
    }
    settings_path.write_text(json.dumps(legacy), encoding="utf-8")

    written = write_hooks(tmp_project_dir, force=False)

    assert ".claude/settings.json" in written
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    cmd = data["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert cmd.startswith(f'"{sys.executable}" ')
    assert 'python "$CLAUDE_PROJECT_DIR' not in cmd
    assert data["hooks"]["_custom"] == "user-added"


def test_write_hooks_force_overwrites_settings_json(tmp_project_dir: Path) -> None:
    write_hooks(tmp_project_dir, force=False)
    (tmp_project_dir / ".claude" / "settings.json").write_text("{}", encoding="utf-8")

    written = write_hooks(tmp_project_dir, force=True)
    assert ".claude/settings.json" in written
    data = json.loads((tmp_project_dir / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert "PreToolUse" in data["hooks"]


# ---------------------------------------------------------------------------
# Hook script behavior — synthetic stdin
# ---------------------------------------------------------------------------


def _run_hook(script: Path, payload: dict, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=15,
        env=env,
    )


def test_hook_deny_scistudio_cli_blocks(tmp_project_dir: Path) -> None:
    write_hooks(tmp_project_dir, force=False)
    script = tmp_project_dir / ".claude" / "hooks" / "deny_scistudio_cli.py"
    proc = _run_hook(script, {"tool_input": {"command": "scistudio run workflow.yaml"}})
    assert proc.returncode == 2
    assert "MCP" in proc.stderr or "mcp__scistudio" in proc.stderr


def test_hook_deny_scistudio_cli_passes_safe(tmp_project_dir: Path) -> None:
    write_hooks(tmp_project_dir, force=False)
    script = tmp_project_dir / ".claude" / "hooks" / "deny_scistudio_cli.py"
    proc = _run_hook(script, {"tool_input": {"command": "ls -la"}})
    assert proc.returncode == 0


def test_hook_deny_scistudio_cli_blocks_relative_path(tmp_project_dir: Path) -> None:
    write_hooks(tmp_project_dir, force=False)
    script = tmp_project_dir / ".claude" / "hooks" / "deny_scistudio_cli.py"
    proc = _run_hook(script, {"tool_input": {"command": "./scistudio validate workflow.yaml"}})
    assert proc.returncode == 2


def test_hook_deny_scistudio_cli_empty_stdin(tmp_project_dir: Path) -> None:
    write_hooks(tmp_project_dir, force=False)
    script = tmp_project_dir / ".claude" / "hooks" / "deny_scistudio_cli.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        input="",
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0


def test_hook_protect_workflow_yaml_blocks(tmp_project_dir: Path) -> None:
    write_hooks(tmp_project_dir, force=False)
    script = tmp_project_dir / ".claude" / "hooks" / "protect_workflow_yaml.py"
    for fp in ("workflows/main.yaml", "workflows/sub/pipeline.yml", "/abs/workflows/x.yaml"):
        proc = _run_hook(script, {"tool_input": {"file_path": fp}})
        assert proc.returncode == 2, f"expected block for {fp}"


def test_hook_protect_workflow_yaml_passes_other_paths(tmp_project_dir: Path) -> None:
    write_hooks(tmp_project_dir, force=False)
    script = tmp_project_dir / ".claude" / "hooks" / "protect_workflow_yaml.py"
    for fp in ("README.md", "data/raw/file.csv", "workflows.yaml.bak"):
        proc = _run_hook(script, {"tool_input": {"file_path": fp}})
        assert proc.returncode == 0, f"expected pass for {fp}"


def test_hook_enforce_list_blocks_blocks_without_marker(tmp_project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_hooks(tmp_project_dir, force=False)
    script = tmp_project_dir / ".claude" / "hooks" / "enforce_list_blocks_before_block_write.py"
    import os

    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(tmp_project_dir)
    proc = _run_hook(
        script,
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "blocks/my_block.py"},
            "session_id": "test-session-1",
        },
        env=env,
    )
    assert proc.returncode == 2


def test_hook_enforce_list_blocks_passes_with_marker(tmp_project_dir: Path) -> None:
    write_hooks(tmp_project_dir, force=False)
    script = tmp_project_dir / ".claude" / "hooks" / "enforce_list_blocks_before_block_write.py"
    marker_dir = tmp_project_dir / ".scistudio" / ".session-state" / "test-session-2"
    marker_dir.mkdir(parents=True, exist_ok=True)
    (marker_dir / "list_blocks_called").touch()
    import os

    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(tmp_project_dir)
    proc = _run_hook(
        script,
        {
            "tool_name": "Write",
            "tool_input": {"file_path": "blocks/my_block.py"},
            "session_id": "test-session-2",
        },
        env=env,
    )
    assert proc.returncode == 0


def test_hook_enforce_list_blocks_passes_non_block_path(tmp_project_dir: Path) -> None:
    write_hooks(tmp_project_dir, force=False)
    script = tmp_project_dir / ".claude" / "hooks" / "enforce_list_blocks_before_block_write.py"
    proc = _run_hook(
        script,
        {"tool_name": "Write", "tool_input": {"file_path": "README.md"}, "session_id": "x"},
    )
    assert proc.returncode == 0


def test_hook_enforce_list_blocks_bash_no_space_redirect_blocked(tmp_project_dir: Path) -> None:
    """Codex P1 (PR #1047): no-space redirects like ``> blocks/new.py``.

    The regex must accept zero whitespace between ``>``/``>>`` and the
    target path, since ``echo x >blocks/foo.py`` is valid shell syntax.
    """
    write_hooks(tmp_project_dir, force=False)
    script = tmp_project_dir / ".claude" / "hooks" / "enforce_list_blocks_before_block_write.py"
    import os

    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(tmp_project_dir)
    proc = _run_hook(
        script,
        {
            "tool_name": "Bash",
            "tool_input": {"command": "echo foo >blocks/new_block.py"},
            "session_id": "test-session-nospace",
        },
        env=env,
    )
    assert proc.returncode == 2


def test_hook_enforce_list_blocks_bash_redirect_blocked(tmp_project_dir: Path) -> None:
    write_hooks(tmp_project_dir, force=False)
    script = tmp_project_dir / ".claude" / "hooks" / "enforce_list_blocks_before_block_write.py"
    import os

    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(tmp_project_dir)
    proc = _run_hook(
        script,
        {
            "tool_name": "Bash",
            "tool_input": {"command": "echo 'foo' > blocks/new_block.py"},
            "session_id": "test-session-3",
        },
        env=env,
    )
    assert proc.returncode == 2


def test_hook_remind_poll_status_exits_zero_with_stderr(tmp_project_dir: Path) -> None:
    write_hooks(tmp_project_dir, force=False)
    script = tmp_project_dir / ".claude" / "hooks" / "remind_poll_status.py"
    proc = _run_hook(script, {"tool_response": {"run_id": "run-abc"}})
    assert proc.returncode == 0
    assert "run-abc" in proc.stderr or "get_run_status" in proc.stderr


def test_hook_mark_list_blocks_called_writes_marker(tmp_project_dir: Path) -> None:
    write_hooks(tmp_project_dir, force=False)
    script = tmp_project_dir / ".claude" / "hooks" / "mark_list_blocks_called.py"
    import os

    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(tmp_project_dir)
    proc = _run_hook(script, {"session_id": "abc123"}, env=env)
    assert proc.returncode == 0
    marker = tmp_project_dir / ".scistudio" / ".session-state" / "abc123" / "list_blocks_called"
    assert marker.is_file()


def test_hook_mark_list_blocks_called_rejects_path_injection(tmp_project_dir: Path) -> None:
    write_hooks(tmp_project_dir, force=False)
    script = tmp_project_dir / ".claude" / "hooks" / "mark_list_blocks_called.py"
    import os

    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(tmp_project_dir)
    # Path-traversal-y session_id; should not write outside .session-state/.
    proc = _run_hook(script, {"session_id": "../escape"}, env=env)
    assert proc.returncode == 0
    assert not (tmp_project_dir.parent / "escape" / "list_blocks_called").exists()


def test_hook_enforce_concrete_port_types_warns_on_dataobject(tmp_project_dir: Path) -> None:
    """ADR-040 §3.6 (F1 rewrite): hook flags accepted_types=[DataObject] in live API.

    Pre-F1 the hook scanned for the legacy ``PortSpec(type='DataObject')``
    shape, which the live ``InputPort/OutputPort`` API does not emit;
    every real block escaped. Post-F1 the hook scans
    ``InputPort/OutputPort(accepted_types=[...])`` and flags
    ``DataObject`` elements.
    """
    write_hooks(tmp_project_dir, force=False)
    script = tmp_project_dir / ".claude" / "hooks" / "enforce_concrete_port_types.py"
    blocks = tmp_project_dir / "blocks"
    blocks.mkdir(parents=True, exist_ok=True)
    target = blocks / "demo_block.py"
    target.write_text(
        "from scistudio.blocks.base.ports import InputPort\n"
        "from scistudio.core.types.base import DataObject\n"
        "p = InputPort(name='x', accepted_types=[DataObject], required=True)\n",
        encoding="utf-8",
    )
    import os

    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(tmp_project_dir)
    proc = _run_hook(
        script,
        {"tool_name": "Write", "tool_input": {"file_path": str(target)}},
        env=env,
    )
    assert proc.returncode == 0
    assert "DataObject" in proc.stderr


def test_hook_enforce_concrete_port_types_silent_on_concrete(tmp_project_dir: Path) -> None:
    """Hook stays silent for concrete-typed ports."""
    write_hooks(tmp_project_dir, force=False)
    script = tmp_project_dir / ".claude" / "hooks" / "enforce_concrete_port_types.py"
    blocks = tmp_project_dir / "blocks"
    blocks.mkdir(parents=True, exist_ok=True)
    target = blocks / "demo_block.py"
    target.write_text(
        "from scistudio.blocks.base.ports import InputPort, OutputPort\n"
        "from scistudio_blocks_fixture.types import Image, Mask\n"
        "in_p = InputPort(name='x', accepted_types=[Image], required=True)\n"
        "out_p = OutputPort(name='y', accepted_types=[Mask])\n",
        encoding="utf-8",
    )
    proc = _run_hook(
        script,
        {"tool_name": "Write", "tool_input": {"file_path": str(target)}},
    )
    assert proc.returncode == 0
    assert "DataObject" not in proc.stderr


def test_hook_enforce_concrete_port_types_flags_empty_accepted_types(tmp_project_dir: Path) -> None:
    """F1 rewrite: ``accepted_types=[]`` is semantically equivalent to DataObject."""
    write_hooks(tmp_project_dir, force=False)
    script = tmp_project_dir / ".claude" / "hooks" / "enforce_concrete_port_types.py"
    blocks = tmp_project_dir / "blocks"
    blocks.mkdir(parents=True, exist_ok=True)
    target = blocks / "empty_accepted.py"
    target.write_text(
        "from scistudio.blocks.base.ports import InputPort\np = InputPort(name='x', accepted_types=[], required=True)\n",
        encoding="utf-8",
    )
    proc = _run_hook(
        script,
        {"tool_name": "Write", "tool_input": {"file_path": str(target)}},
    )
    assert proc.returncode == 0
    # Hook flags empty accepted_types lists with an "empty" message variant.
    assert "matches anything" in proc.stderr or "accepted_types=[]" in proc.stderr


def test_hook_enforce_concrete_port_types_flags_attribute_form(tmp_project_dir: Path) -> None:
    """F1 rewrite: matches ``accepted_types=[core.DataObject]`` (Attribute form)."""
    write_hooks(tmp_project_dir, force=False)
    script = tmp_project_dir / ".claude" / "hooks" / "enforce_concrete_port_types.py"
    blocks = tmp_project_dir / "blocks"
    blocks.mkdir(parents=True, exist_ok=True)
    target = blocks / "attr_form.py"
    target.write_text(
        "from scistudio.core.types import base as core\n"
        "from scistudio.blocks.base.ports import InputPort\n"
        "p = InputPort(name='x', accepted_types=[core.DataObject], required=True)\n",
        encoding="utf-8",
    )
    proc = _run_hook(
        script,
        {"tool_name": "Write", "tool_input": {"file_path": str(target)}},
    )
    assert proc.returncode == 0
    assert "DataObject" in proc.stderr


def test_hook_enforce_concrete_port_types_handles_syntax_error(tmp_project_dir: Path) -> None:
    write_hooks(tmp_project_dir, force=False)
    script = tmp_project_dir / ".claude" / "hooks" / "enforce_concrete_port_types.py"
    blocks = tmp_project_dir / "blocks"
    blocks.mkdir(parents=True, exist_ok=True)
    target = blocks / "broken.py"
    target.write_text("def(((\n", encoding="utf-8")
    proc = _run_hook(
        script,
        {"tool_name": "Write", "tool_input": {"file_path": str(target)}},
    )
    # Always exit 0 (PostToolUse cannot block); syntax error just suppresses scan.
    assert proc.returncode == 0


def test_hook_enforce_concrete_port_types_non_literal_accepted_types_silent(
    tmp_project_dir: Path,
) -> None:
    """Codex P2 fix (#1089): non-literal accepted_types (variable / call) is opaque,
    must NOT be flagged as generic/empty.
    """
    write_hooks(tmp_project_dir, force=False)
    script = tmp_project_dir / ".claude" / "hooks" / "enforce_concrete_port_types.py"
    blocks = tmp_project_dir / "blocks"
    blocks.mkdir(parents=True, exist_ok=True)
    target = blocks / "non_literal_accepted.py"
    target.write_text(
        "from scistudio.blocks.base.ports import InputPort\n"
        "MY_TYPES = [int]\n"
        "p1 = InputPort(name='var_ref', accepted_types=MY_TYPES)\n"
        "p2 = InputPort(name='call', accepted_types=list((int,)))\n",
        encoding="utf-8",
    )
    proc = _run_hook(
        script,
        {"tool_name": "Write", "tool_input": {"file_path": str(target)}},
    )
    # Always exit 0
    assert proc.returncode == 0
    # MUST NOT flag — runtime value is opaque
    assert "DataObject" not in proc.stderr, f"False generic-port warning on non-literal accepted_types:\n{proc.stderr}"
    assert "empty" not in proc.stderr.lower(), f"False 'empty' warning on non-literal accepted_types:\n{proc.stderr}"
