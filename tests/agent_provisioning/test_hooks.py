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

from scistudio.agent_provisioning.hooks import (
    _build_settings_json,
    _merge_missing_canonical_hooks,
    write_hooks,
)

_HOOK_NAMES = (
    "deny_scistudio_cli.py",
    "protect_workflow_yaml.py",
    "protect_data_dir.py",
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
    assert len(pre) == 4  # +protect_data_dir.py (#1858)
    assert len(post) == 3

    # #1858: the data/ guard is registered for both file tools and Bash.
    data_dir_entries = [e for e in pre if "protect_data_dir.py" in e["hooks"][0]["command"]]
    assert len(data_dir_entries) == 1
    assert data_dir_entries[0]["matcher"] == "Edit|Write|MultiEdit|Bash"

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


def test_write_hooks_excludes_worktree_write_guard(tmp_project_dir: Path) -> None:
    """#1793: the SciStudio repo-dev worktree guard must not leak into user projects."""
    written = write_hooks(tmp_project_dir, force=False)
    assert not any("worktree_write_guard" in path for path in written)
    assert not (tmp_project_dir / ".claude" / "hooks" / "worktree_write_guard.py").exists()

    data = json.loads((tmp_project_dir / ".claude" / "settings.json").read_text(encoding="utf-8"))
    commands = [
        handler["command"]
        for group in (data["hooks"]["PreToolUse"] + data["hooks"]["PostToolUse"])
        for handler in group["hooks"]
    ]
    assert not any("worktree_write_guard" in command for command in commands)


def test_write_hooks_idempotent_when_all_canonical_present(tmp_project_dir: Path) -> None:
    """force=False does not rewrite settings.json when nothing is missing."""
    settings = _build_settings_json(".claude/hooks")
    settings["hooks"]["_custom"] = "user-added"
    settings_path = tmp_project_dir / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings), encoding="utf-8")

    written = write_hooks(tmp_project_dir, force=False)
    assert ".claude/settings.json" not in written
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    assert data["hooks"]["_custom"] == "user-added"


def test_write_hooks_tops_up_missing_canonical_hook(tmp_project_dir: Path) -> None:
    """#1858: an existing settings.json missing the data/ guard gets it added.

    Simulates an old project provisioned before ``protect_data_dir.py`` existed:
    its settings.json already exists, so the plain write-if-absent path would
    never register the new hook. The additive top-up must add it on next open,
    while preserving the user's own entries.
    """
    settings = _build_settings_json(".claude/hooks")
    # Drop the data/ guard to mimic a pre-#1858 project, and add a user hook.
    settings["hooks"]["PreToolUse"] = [
        e for e in settings["hooks"]["PreToolUse"] if "protect_data_dir.py" not in e["hooks"][0]["command"]
    ]
    settings["hooks"]["PreToolUse"].append(
        {"matcher": "Bash", "hooks": [{"type": "command", "command": "my-own-hook.sh"}]}
    )
    settings_path = tmp_project_dir / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(settings), encoding="utf-8")

    written = write_hooks(tmp_project_dir, force=False)

    assert ".claude/settings.json" in written
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    commands = [h["command"] for e in data["hooks"]["PreToolUse"] for h in e["hooks"]]
    # New canonical hook registered...
    assert any("protect_data_dir.py" in c for c in commands)
    # ...the script file is present...
    assert (tmp_project_dir / ".claude" / "hooks" / "protect_data_dir.py").is_file()
    # ...and the user's own hook is left intact.
    assert "my-own-hook.sh" in commands


def test_merge_missing_canonical_hooks_is_additive_only() -> None:
    """The merge adds missing canonical entries and never duplicates present ones."""
    settings = _build_settings_json(".claude/hooks")
    # Everything already present → no change.
    assert _merge_missing_canonical_hooks(settings) is False

    # Remove one canonical entry → exactly that one is re-added, idempotently.
    settings["hooks"]["PreToolUse"] = [
        e for e in settings["hooks"]["PreToolUse"] if "protect_data_dir.py" not in e["hooks"][0]["command"]
    ]
    assert _merge_missing_canonical_hooks(settings) is True
    assert _merge_missing_canonical_hooks(settings) is False
    cmds = [h["command"] for e in settings["hooks"]["PreToolUse"] for h in e["hooks"]]
    assert sum("protect_data_dir.py" in c for c in cmds) == 1


def test_merge_missing_canonical_hooks_leaves_malformed_hooks_untouched() -> None:
    """A non-dict ``hooks`` value is user data we must not clobber."""
    settings = {"hooks": "not-a-dict"}
    assert _merge_missing_canonical_hooks(settings) is False
    assert settings == {"hooks": "not-a-dict"}


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


# ---------------------------------------------------------------------------
# #1858 — protect_data_dir.py
# ---------------------------------------------------------------------------


def _data_hook(tmp_project_dir: Path) -> Path:
    write_hooks(tmp_project_dir, force=False)
    return tmp_project_dir / ".claude" / "hooks" / "protect_data_dir.py"


def _env_for(tmp_project_dir: Path) -> dict[str, str]:
    import os

    env = os.environ.copy()
    env["CLAUDE_PROJECT_DIR"] = str(tmp_project_dir)
    env.pop("SCISTUDIO_PROJECT_DIR", None)
    return env


def test_data_hook_blocks_file_edits_under_data(tmp_project_dir: Path) -> None:
    script = _data_hook(tmp_project_dir)
    env = _env_for(tmp_project_dir)
    for tool in ("Edit", "Write", "MultiEdit"):
        for fp in (
            "data/raw/file.csv",
            "data/zarr/array",
            str(tmp_project_dir / "data" / "artifacts" / "out.png"),
            "./data/exchange/x.json",
        ):
            proc = _run_hook(script, {"tool_name": tool, "tool_input": {"file_path": fp}}, env=env)
            assert proc.returncode == 2, f"expected block for {tool} {fp}"


def test_data_hook_allows_file_edits_outside_data(tmp_project_dir: Path) -> None:
    script = _data_hook(tmp_project_dir)
    env = _env_for(tmp_project_dir)
    for fp in (
        "blocks/my_block.py",
        "workflows/main.yaml",
        "README.md",
        "database.py",  # not the data/ dir
        "metadata/notes.txt",
        str(tmp_project_dir / "blocks" / "x.py"),
    ):
        proc = _run_hook(script, {"tool_name": "Write", "tool_input": {"file_path": fp}}, env=env)
        assert proc.returncode == 0, f"expected pass for {fp}"


def test_data_hook_blocks_obvious_bash_writes_and_deletes(tmp_project_dir: Path) -> None:
    script = _data_hook(tmp_project_dir)
    env = _env_for(tmp_project_dir)
    for cmd in (
        "rm -rf data/raw",
        "rm data/zarr/array",
        "echo hi > data/raw/out.txt",
        "cat foo >> data/exchange/log",
        "mv data/raw/a.csv /tmp/a.csv",  # moving OUT of data deletes the source
        "cp report.csv data/artifacts/report.csv",  # writing INTO data
        "truncate -s 0 data/raw/big.bin",
    ):
        proc = _run_hook(script, {"tool_name": "Bash", "tool_input": {"command": cmd}}, env=env)
        assert proc.returncode == 2, f"expected block for: {cmd}"


def test_data_hook_allows_reads_and_non_data_bash(tmp_project_dir: Path) -> None:
    script = _data_hook(tmp_project_dir)
    env = _env_for(tmp_project_dir)
    for cmd in (
        "cat data/raw/file.csv",  # reading data is fine
        "ls -la data/",
        "head -n 5 data/raw/file.csv",
        "rm -rf workflows/old.yaml",  # deleting non-data is allowed
        "mv blocks/a.py blocks/b.py",
        "echo hello > notes.txt",
    ):
        proc = _run_hook(script, {"tool_name": "Bash", "tool_input": {"command": cmd}}, env=env)
        assert proc.returncode == 0, f"expected pass for: {cmd}"


def test_data_hook_blocks_apply_patch_touching_data(tmp_project_dir: Path) -> None:
    script = _data_hook(tmp_project_dir)
    env = _env_for(tmp_project_dir)
    patch = "*** Begin Patch\n*** Update File: data/raw/file.csv\n+changed\n*** End Patch\n"
    proc = _run_hook(script, {"tool_name": "apply_patch", "tool_input": {"input": patch}}, env=env)
    assert proc.returncode == 2


def test_data_hook_empty_stdin_passes(tmp_project_dir: Path) -> None:
    script = _data_hook(tmp_project_dir)
    proc = subprocess.run([sys.executable, str(script)], input="", capture_output=True, text=True, timeout=15)
    assert proc.returncode == 0


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
