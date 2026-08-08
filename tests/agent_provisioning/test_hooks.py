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
        # #1994: the pinned interpreter is now hook_interpreter(), not
        # sys.executable. They differ when provisioning runs inside a
        # virtualenv, which is precisely the case that shipped a dead
        # command pointing into a disposable scratch venv.
        assert hook_interpreter() in cmd
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
    # #1994: pinned to the stable base interpreter rather than whichever
    # one happened to run provisioning.
    assert cmd.startswith(f'"{hook_interpreter()}" ')
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


# ---------------------------------------------------------------------------
# #1994 finding 3 — Qoder hook parity.
#
# The owner found that SciStudio's data-protection and tool-use hooks did not
# take effect for Qoder. They were not merely misconfigured: nothing was ever
# written for Qoder at all. Every fact these tests encode was established by
# running the installed CLI at 1.1.15, not read off documentation:
#
#   * ``qoderclicn hooks migrate --from-claude``, run in a project SciStudio
#     had just provisioned, wrote ``<project>/.qoder/settings.json`` holding
#     our seven entries with ``$CLAUDE_PROJECT_DIR`` rewritten to
#     ``$QODER_PROJECT_DIR``. That is where Qoder looks and what it expects.
#   * ``.qoder`` — not ``.qoder-cn`` — is the project scope for *both*
#     channels: the observation above was made with the China-channel binary,
#     whose user config root is ``~/.qoder-cn``.
#   * A blocking hook placed in that file and run through ``qoderclicn``
#     stopped the Bash tool call and surfaced the hook's stderr, so exit-code-2
#     blocking works exactly as it does for Claude Code.
# ---------------------------------------------------------------------------


def test_write_hooks_creates_qoder_settings(tmp_project_dir: Path) -> None:
    """Qoder gets the same hook set in the file Qoder actually reads."""
    written = write_hooks(tmp_project_dir, force=False)
    assert ".qoder/settings.json" in written

    data = json.loads((tmp_project_dir / ".qoder" / "settings.json").read_text(encoding="utf-8"))
    assert len(data["hooks"]["PreToolUse"]) == 4
    assert len(data["hooks"]["PostToolUse"]) == 3


def test_qoder_hooks_expand_qoders_own_project_dir_variable(tmp_project_dir: Path) -> None:
    """``$CLAUDE_PROJECT_DIR`` is not a variable Qoder sets.

    Copying the Claude Code file verbatim would leave every command pointing at
    an empty path, so the hooks would "exist" and silently never run — the same
    user-visible outcome as not provisioning them.
    """
    write_hooks(tmp_project_dir, force=False)
    raw = (tmp_project_dir / ".qoder" / "settings.json").read_text(encoding="utf-8")

    assert "$QODER_PROJECT_DIR" in raw
    assert "$CLAUDE_PROJECT_DIR" not in raw


def test_qoder_hooks_reuse_the_shared_hook_scripts(tmp_project_dir: Path) -> None:
    """One set of scripts serves every provider, as Qoder's own migration does."""
    write_hooks(tmp_project_dir, force=False)
    raw = (tmp_project_dir / ".qoder" / "settings.json").read_text(encoding="utf-8")

    for name in _HOOK_NAMES:
        assert f".claude/hooks/{name}" in raw
        assert (tmp_project_dir / ".claude" / "hooks" / name).is_file()


def test_qoder_and_claude_hook_coverage_cannot_drift(tmp_project_dir: Path) -> None:
    """The two files declare the same matchers against the same scripts.

    Both are rendered by one builder precisely so a hook added for Claude Code
    cannot quietly skip Qoder. Comparing them after normalising the project-dir
    variable is what holds that guarantee in place.
    """
    write_hooks(tmp_project_dir, force=False)
    claude = (tmp_project_dir / ".claude" / "settings.json").read_text(encoding="utf-8")
    qoder = (tmp_project_dir / ".qoder" / "settings.json").read_text(encoding="utf-8")

    assert qoder.replace("$QODER_PROJECT_DIR", "$CLAUDE_PROJECT_DIR") == claude


def test_existing_qoder_settings_are_topped_up_not_clobbered(tmp_project_dir: Path) -> None:
    """A user-authored Qoder hook survives; missing canonical ones are added."""
    qoder_settings = tmp_project_dir / ".qoder" / "settings.json"
    qoder_settings.parent.mkdir(parents=True, exist_ok=True)
    qoder_settings.write_text(
        json.dumps(
            {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "my-own-hook"}]}]}}
        ),
        encoding="utf-8",
    )

    write_hooks(tmp_project_dir, force=False)
    raw = qoder_settings.read_text(encoding="utf-8")

    assert "my-own-hook" in raw
    for name in _HOOK_NAMES:
        assert name in raw


# ---------------------------------------------------------------------------
# #1994 — the hook must RUN, not merely be well-formed.
#
# After the command-line fix Codex finally invoked the hooks, and all three
# died with `hook exited with code 1` before evaluating anything. Two separate
# causes, both invisible to a test that only inspects strings:
#
#   1. Every hook read stdin through a `_read_payload` that guarded only
#      OSError. A CLI that starts a hook with no usable stdin leaves
#      `sys.stdin is None`, so `sys.stdin.read()` raised AttributeError and the
#      process exited 1. A failed PreToolUse hook does not block, so the guard
#      silently stopped guarding.
#   2. The interpreter was captured from `sys.executable` at provisioning time,
#      which on the owner's machine was the gate's disposable parity venv.
# ---------------------------------------------------------------------------

from scistudio.agent_provisioning.hooks import hook_interpreter  # noqa: E402

_BLOCKING_PAYLOAD = json.dumps(
    {"session_id": "t", "cwd": ".", "tool_name": "Bash", "tool_input": {"command": "scistudio run wf.yaml"}}
)


def _deny_hook(project_dir: Path) -> Path:
    return project_dir / ".claude" / "hooks" / "deny_scistudio_cli.py"


def test_hook_interpreter_exists_and_is_executable(tmp_project_dir: Path) -> None:
    """The interpreter baked into every hook command must actually run.

    A path that merely looks plausible is what shipped: it pointed into a
    scratch venv. Executing it is the only assertion that can tell the
    difference.
    """
    interpreter = hook_interpreter()

    assert Path(interpreter).is_file(), f"hook interpreter does not exist: {interpreter}"
    result = subprocess.run([interpreter, "-c", "print('ok')"], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, f"hook interpreter failed to run: {interpreter}\n{result.stderr}"


def test_hook_interpreter_is_not_a_disposable_virtualenv() -> None:
    """Prefer the base installation the venv was built from.

    The hook scripts import only the standard library, so a venv buys them
    nothing, while the venv itself is the part that gets deleted — the owner's
    was ``.workflow/local/venv``, created by the gate and built to be thrown
    away.
    """
    if sys.prefix == sys.base_prefix:
        pytest.skip("not running inside a virtualenv; sys.executable is already the stable choice")

    assert hook_interpreter() != sys.executable
    assert Path(hook_interpreter()).is_file()


def test_generated_hook_blocks_a_scistudio_call(tmp_project_dir: Path) -> None:
    """End-to-end through the real interpreter: a blocked call exits 2.

    Exercises interpreter, script and payload together, which is what the
    reported defect broke and what no string comparison could have caught.
    """
    write_hooks(tmp_project_dir, force=True)

    result = subprocess.run(
        [hook_interpreter(), str(_deny_hook(tmp_project_dir))],
        input=_BLOCKING_PAYLOAD,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 2, f"expected the hook to block (exit 2), got {result.returncode}: {result.stderr}"
    assert "mcp__scistudio__" in result.stderr


@pytest.mark.parametrize("script", _HOOK_NAMES)
def test_hook_never_exits_one_when_stdin_is_unusable(script: str, tmp_project_dir: Path) -> None:
    """No hook may crash because its payload could not be read.

    ``stdin=DEVNULL`` stands in for the condition the owner hit: the hook is
    started without a readable payload stream. Before the fix every one of the
    seven raised ``AttributeError`` on ``sys.stdin.read()`` and exited 1, which
    the CLI surfaced as a failed hook and then ignored — so the protection was
    silently absent rather than loudly broken.

    Exit 1 is the specific assertion: 0 (allow) and 2 (block) are both
    legitimate answers, and 1 means the hook never reached an answer at all.
    """
    write_hooks(tmp_project_dir, force=True)
    target = tmp_project_dir / ".claude" / "hooks" / script

    # ``stdin=DEVNULL`` is NOT the failing condition: that still hands the hook
    # a real stream which simply reads EOF, and the old code coped with it. The
    # condition the owner hit is a *missing* stdin handle, where Python sets
    # ``sys.stdin`` to None — reproduced here by running the script with stdin
    # set to None, which is what makes this test fail on the pre-fix templates.
    driver = "import sys, runpy; sys.stdin = None; runpy.run_path(sys.argv[1], run_name='__main__')"
    result = subprocess.run(
        [hook_interpreter(), "-c", driver, str(target)],
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode != 1, (
        f"{script} crashed instead of degrading when stdin was unusable: exit 1\n{result.stderr}"
    )
    assert "AttributeError" not in result.stderr, f"{script} raised on a missing stdin:\n{result.stderr}"


# ---------------------------------------------------------------------------
# #1994 — provisioned hook SCRIPTS must be refreshed, not written once.
#
# The templates were fixed and the owner's Codex hooks kept failing identically,
# because `write_hooks` skipped any script that already existed. The repaired
# code never reached the file the CLI executes: re-provisioning was a no-op on
# every project that had ever been provisioned before. The Codex *config* had a
# repair path; the scripts it points at did not, which made that a half-fix.
# ---------------------------------------------------------------------------


def _stale_hook_body() -> str:
    """A prior-generation script: SciStudio's, but with the crashing reader."""
    return (
        "#!/usr/bin/env python\n"
        '"""hook_deny_scistudio_cli.py — PreToolUse / Bash matcher (ADR-040 §3.6)."""\n\n'
        "import json\nimport sys\n\n\n"
        "def _read_payload() -> dict:\n"
        "    try:\n"
        "        raw = sys.stdin.read()\n"
        "    except OSError:\n"
        "        return {}\n"
        "    return json.loads(raw) if raw.strip() else {}\n\n\n"
        # Calls the reader, so this body genuinely reproduces the exit-1 crash
        # on a missing stdin. A stub that merely *contained* the old reader
        # would let the companion behaviour test pass without the fix.
        "_read_payload()\n"
        "sys.exit(0)\n"
    )


def test_stale_provisioned_hook_script_is_refreshed(tmp_project_dir: Path) -> None:
    """Re-provisioning repairs a SciStudio hook script left over from before.

    Without this, a project provisioned by any earlier SciStudio keeps its
    original scripts forever and no template fix can ever reach it.
    """
    write_hooks(tmp_project_dir, force=False)
    target = tmp_project_dir / ".claude" / "hooks" / "deny_scistudio_cli.py"
    target.write_text(_stale_hook_body(), encoding="utf-8")

    written = write_hooks(tmp_project_dir, force=False)

    assert ".claude/hooks/deny_scistudio_cli.py" in written
    refreshed = target.read_text(encoding="utf-8")
    assert refreshed != _stale_hook_body()
    assert "stream = sys.stdin" in refreshed, "the repaired payload reader did not reach the provisioned script"


def test_refreshed_script_survives_the_condition_that_broke_it(tmp_project_dir: Path) -> None:
    """The repaired script no longer exits 1 when stdin is unusable.

    Ties the refresh to the behaviour it exists to restore, so a refresh that
    delivered the wrong content would still fail here.
    """
    write_hooks(tmp_project_dir, force=False)
    target = tmp_project_dir / ".claude" / "hooks" / "deny_scistudio_cli.py"
    target.write_text(_stale_hook_body(), encoding="utf-8")
    write_hooks(tmp_project_dir, force=False)

    driver = "import sys, runpy; sys.stdin = None; runpy.run_path(sys.argv[1], run_name='__main__')"
    result = subprocess.run(
        [hook_interpreter(), "-c", driver, str(target)],
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode != 1, f"refreshed script still crashes on a missing stdin:\n{result.stderr}"


def test_user_authored_hook_script_is_not_clobbered(tmp_project_dir: Path) -> None:
    """A script the user replaced wholesale stays theirs.

    The refresh is keyed on SciStudio's own provenance marker precisely so that
    repairing our stale copies cannot destroy someone else's file.
    """
    write_hooks(tmp_project_dir, force=False)
    target = tmp_project_dir / ".claude" / "hooks" / "protect_data_dir.py"
    mine = "# entirely my own hook\nimport sys\n\nsys.exit(0)\n"
    target.write_text(mine, encoding="utf-8")

    write_hooks(tmp_project_dir, force=False)

    assert target.read_text(encoding="utf-8") == mine


def test_unchanged_scripts_are_not_rewritten(tmp_project_dir: Path) -> None:
    """A project already holding current scripts reports no churn.

    Keeps the refresh honest: it must repair drift, not rewrite every file on
    every project open and report phantom changes.
    """
    write_hooks(tmp_project_dir, force=False)

    written = write_hooks(tmp_project_dir, force=False)

    assert not [path for path in written if path.startswith(".claude/hooks/")]


# ---------------------------------------------------------------------------
# #2040 — a baked interpreter that has since disappeared.
#
# hook_interpreter() is correct when it runs: the venv branch checks is_file()
# and the fallback returns the running sys.executable. Nothing keeps it correct
# afterwards. Uninstall the desktop app, delete a virtualenv or upgrade Python
# and every provisioned project holds hook commands whose first word is gone.
# Neither existing repair reached that state: the legacy upgrade matches only
# the bare-`python` spelling, and the canonical merge appends only hooks that
# are absent -- a hook that is present but dead satisfies it.
# ---------------------------------------------------------------------------

_DEAD_INTERPRETER = "C:/nonexistent-scistudio/resources/python/python.exe"


def _settings_with_interpreter(interpreter: str, project_dir_var: str = "CLAUDE_PROJECT_DIR") -> dict:
    """A generated-shape settings file pinned to *interpreter*."""
    return {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": (f'"{interpreter}" "${project_dir_var}/.claude/hooks/deny_scistudio_cli.py"'),
                        }
                    ],
                }
            ],
            "PostToolUse": [],
        }
    }


def _first_command(settings_path: Path) -> str:
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    return str(data["hooks"]["PreToolUse"][0]["hooks"][0]["command"])


def test_dead_interpreter_command_is_repaired(tmp_project_dir: Path) -> None:
    """A hook pinned to an interpreter that no longer exists is re-rendered."""
    settings_path = tmp_project_dir / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(_settings_with_interpreter(_DEAD_INTERPRETER)), encoding="utf-8")

    written = write_hooks(tmp_project_dir, force=False)

    assert ".claude/settings.json" in written
    command = _first_command(settings_path)
    assert _DEAD_INTERPRETER not in command
    assert command == f'"{hook_interpreter()}" "$CLAUDE_PROJECT_DIR/.claude/hooks/deny_scistudio_cli.py"'


def test_dead_interpreter_command_is_repaired_for_qoder(tmp_project_dir: Path) -> None:
    """Qoder's own project-scope file is repaired on the same terms.

    Its commands expand ``$QODER_PROJECT_DIR``; a repair that only recognised
    Claude Code's variable would leave every Qoder tab unguarded.
    """
    settings_path = tmp_project_dir / ".qoder" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(_settings_with_interpreter(_DEAD_INTERPRETER, "QODER_PROJECT_DIR")), encoding="utf-8"
    )

    written = write_hooks(tmp_project_dir, force=False)

    assert ".qoder/settings.json" in written
    command = _first_command(settings_path)
    assert _DEAD_INTERPRETER not in command
    assert command == f'"{hook_interpreter()}" "$QODER_PROJECT_DIR/.claude/hooks/deny_scistudio_cli.py"'


def test_live_interpreter_command_is_left_alone(tmp_project_dir: Path) -> None:
    """A working interpreter survives, even when it is not the current choice.

    The trigger is death, not difference. A user who deliberately pointed the
    hooks at their own interpreter keeps it across project opens.
    """
    settings_path = tmp_project_dir / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    deliberate = sys.executable
    settings_path.write_text(json.dumps(_settings_with_interpreter(deliberate)), encoding="utf-8")

    write_hooks(tmp_project_dir, force=False)

    assert _first_command(settings_path) == (
        f'"{deliberate}" "$CLAUDE_PROJECT_DIR/.claude/hooks/deny_scistudio_cli.py"'
    )


def test_user_authored_command_is_not_repaired(tmp_project_dir: Path) -> None:
    """Only the shape SciStudio emits is a candidate.

    A user's own wrapper around the same script has its own reasons for the
    interpreter it names; rewriting it would be SciStudio editing someone
    else's configuration.
    """
    settings_path = tmp_project_dir / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    mine = f'{_DEAD_INTERPRETER} --flag "$CLAUDE_PROJECT_DIR/.claude/hooks/deny_scistudio_cli.py"'
    settings_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": mine}]}],
                    "PostToolUse": [],
                }
            }
        ),
        encoding="utf-8",
    )

    write_hooks(tmp_project_dir, force=False)

    assert _first_command(settings_path) == mine


def test_repaired_hook_blocks_again(tmp_project_dir: Path) -> None:
    """End-to-end: after repair the guard enforces rather than failing open.

    The defect's real cost is not the broken string. A hook that cannot start
    exits 127, which is a non-blocking status, so the tool call proceeds
    unguarded. Asserting the repaired command exits 2 is the only check that
    distinguishes a restored guard from a merely tidier settings file.
    """
    write_hooks(tmp_project_dir, force=True)
    settings_path = tmp_project_dir / ".claude" / "settings.json"
    settings_path.write_text(json.dumps(_settings_with_interpreter(_DEAD_INTERPRETER)), encoding="utf-8")

    write_hooks(tmp_project_dir, force=False)

    interpreter = _first_command(settings_path).split('" "')[0].lstrip('"')
    result = subprocess.run(
        [interpreter, str(_deny_hook(tmp_project_dir))],
        input=_BLOCKING_PAYLOAD,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 2, f"guard did not block after repair: {result.returncode}\n{result.stderr}"
