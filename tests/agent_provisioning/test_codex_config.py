"""Tests for ``agent_provisioning.codex_config`` (ADR-040 §3.7)."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

from scistudio.agent_provisioning import codex_config as _cc
from scistudio.agent_provisioning.codex_config import _toml_escape, write_codex_config
from scistudio.agent_provisioning.hooks import _HOOK_FILES, _build_settings_json, hook_interpreter


def test_every_provisioned_hook_is_wired_for_both_providers() -> None:
    """#1858 parity guard: every provisioned hook script is registered for BOTH
    Claude Code (``.claude/settings.json``) and Codex (``.codex/config.toml``).

    Locks the two provider configs and the provisioned script set together so a
    future hook added to one provider can't silently miss the other.
    """
    provisioned = {dest for _template, dest in _HOOK_FILES}

    settings = _build_settings_json(".claude/hooks")
    claude_wired: set[str] = set()
    for entries in settings["hooks"].values():
        for entry in entries:
            for handler in entry["hooks"]:
                for name in provisioned:
                    if name in handler["command"]:
                        claude_wired.add(name)

    codex_wired = {s for _m, s, _msg in _cc._PRE_HOOKS} | {s for _m, s, _msg in _cc._POST_HOOKS}

    assert provisioned == claude_wired, f"Claude missing: {provisioned - claude_wired}"
    assert provisioned == codex_wired, f"Codex missing: {provisioned - codex_wired}"


def test_data_dir_guard_matcher_covers_file_tools_and_bash_for_both_providers() -> None:
    """The data/ guard must fire for file edits AND Bash on both providers."""
    settings = _build_settings_json(".claude/hooks")
    claude_matcher = next(
        e["matcher"] for e in settings["hooks"]["PreToolUse"] if "protect_data_dir.py" in e["hooks"][0]["command"]
    )
    for tool in ("Edit", "Write", "MultiEdit", "Bash"):
        assert tool in claude_matcher

    codex_matcher = next(m for m, s, _ in _cc._PRE_HOOKS if s == "protect_data_dir.py")
    for tool in ("Edit", "Write", "MultiEdit", "apply_patch", "Bash"):
        assert tool in codex_matcher


def test_writes_codex_config_toml(tmp_project_dir: Path) -> None:
    """``.codex/config.toml`` exists with expected mcp_servers.scistudio block."""
    written = write_codex_config(tmp_project_dir, force=False)
    assert written == [".codex/config.toml"]

    raw = (tmp_project_dir / ".codex" / "config.toml").read_text(encoding="utf-8")
    data = tomllib.loads(raw)
    assert "mcp_servers" in data
    block = data["mcp_servers"]["scistudio"]
    assert block["args"] == ["-m", "scistudio", "mcp-bridge"]
    assert block["env"]["SCISTUDIO_PROJECT_DIR"] == str(tmp_project_dir.resolve())


def test_codex_config_mcp_block_matches_install_render(tmp_project_dir: Path) -> None:
    """The ``[mcp_servers.scistudio]`` block matches ``_render_codex_block`` exactly.

    Per ADR §3.7 / §3.9 unification contract the MCP server block must
    be byte-identical to what ``scistudio install --target codex`` emits.
    Per ADR Addendum 4 the auto-provisioned file additionally appends a
    hooks block — so the contract is now "MCP block is the prefix" rather
    than "whole file is equal".
    """
    from scistudio.cli.install import _render_codex_block

    write_codex_config(tmp_project_dir, force=False)
    actual = (tmp_project_dir / ".codex" / "config.toml").read_text(encoding="utf-8")
    expected_mcp = _render_codex_block(tmp_project_dir.resolve())
    assert actual.startswith(expected_mcp), (
        "MCP-server block must be the unmodified prefix; "
        "scistudio install --target codex must keep producing the same bytes."
    )


def test_codex_config_emits_hooks(tmp_project_dir: Path) -> None:
    """ADR-040/042: Codex gets the same hook surface as Claude.

    Asserts ``features.hooks = true``, 4 PreToolUse + 3 PostToolUse
    matcher groups, and each hook command line references a script
    under ``.claude/hooks/`` (the cross-provider canonical home).
    """
    write_codex_config(tmp_project_dir, force=False)
    raw = (tmp_project_dir / ".codex" / "config.toml").read_text(encoding="utf-8")
    data = tomllib.loads(raw)

    assert data.get("features", {}).get("hooks") is True, (
        "features.hooks must be true to enable Codex 0.130+'s hook surface"
    )

    pre = data.get("hooks", {}).get("PreToolUse", [])
    post = data.get("hooks", {}).get("PostToolUse", [])
    assert len(pre) == 4, f"expected 4 PreToolUse hooks, got {len(pre)}"
    assert len(post) == 3, f"expected 3 PostToolUse hooks, got {len(post)}"

    expected_pre_scripts = {
        "deny_scistudio_cli.py",
        "protect_workflow_yaml.py",
        "protect_data_dir.py",
        "enforce_list_blocks_before_block_write.py",
    }
    expected_post_scripts = {
        "remind_poll_status.py",
        "mark_list_blocks_called.py",
        "enforce_concrete_port_types.py",
    }

    def _script_names(groups: list[dict]) -> set[str]:
        names: set[str] = set()
        for group in groups:
            for handler in group.get("hooks", []):
                cmd = handler.get("command", "")
                # Extract trailing script name from the command.
                for known in expected_pre_scripts | expected_post_scripts:
                    if known in cmd:
                        names.add(known)
                # Every hook command must invoke a .claude/hooks/ script
                # (cross-provider DRY — no Codex-specific script tree).
                #
                # #1994: compared separator-agnostically. The command now
                # embeds the project's absolute hook directory rather than a
                # forward-slash literal, so on Windows the separator is a
                # backslash. The claim is about which tree the command targets,
                # not how the OS spells a path.
                assert ".claude/hooks/" in cmd.replace("\\", "/"), (
                    f"hook command should target .claude/hooks/, got: {cmd!r}"
                )
                # #1994: separator-agnostic for the same reason as above — the
                # command now spells paths with forward slashes so one string
                # parses in cmd.exe, PowerShell and sh alike.
                # #1994: pinned to hook_interpreter(), the stable base
                # interpreter, rather than whichever one ran provisioning —
                # the owner's was a disposable gate venv.
                assert hook_interpreter().replace("\\", "/") in cmd.replace("\\", "/"), (
                    f"hook command should pin a stable Python, got: {cmd!r}"
                )
        return names

    assert _script_names(pre) == expected_pre_scripts
    assert _script_names(post) == expected_post_scripts


def test_codex_config_excludes_worktree_write_guard(tmp_project_dir: Path) -> None:
    """#1793: the SciStudio repo-dev worktree guard must not leak into user projects."""
    write_codex_config(tmp_project_dir, force=False)
    raw = (tmp_project_dir / ".codex" / "config.toml").read_text(encoding="utf-8")
    assert "worktree_write_guard" not in raw


def test_idempotent_preserves_user_managed_toml(tmp_project_dir: Path) -> None:
    """Pre-existing config.toml preserved on force=False."""
    codex_dir = tmp_project_dir / ".codex"
    codex_dir.mkdir(parents=True, exist_ok=True)
    user_body = "# user-managed config\n[some_other_section]\nkey = 'value'\n"
    (codex_dir / "config.toml").write_text(user_body, encoding="utf-8")

    written = write_codex_config(tmp_project_dir, force=False)
    assert written == []
    assert (codex_dir / "config.toml").read_text(encoding="utf-8") == user_body


def test_existing_codex_config_upgrades_legacy_python_hook_command(tmp_project_dir: Path) -> None:
    codex_dir = tmp_project_dir / ".codex"
    codex_dir.mkdir(parents=True, exist_ok=True)
    legacy_body = (
        "[features]\n"
        "hooks = true\n"
        "[[hooks.PreToolUse]]\n"
        'matcher = "^Bash$"\n'
        "[[hooks.PreToolUse.hooks]]\n"
        'type = "command"\n'
        'command = "python \\"$(git rev-parse --show-toplevel)/.claude/hooks/deny_scistudio_cli.py\\""\n'
    )
    target = codex_dir / "config.toml"
    target.write_text(legacy_body, encoding="utf-8")

    written = write_codex_config(tmp_project_dir, force=False)

    assert written == [".codex/config.toml"]
    upgraded = target.read_text(encoding="utf-8")
    # #1994: this assertion used to compare the raw ``sys.executable`` against a
    # TOML basic string, so it passed only on POSIX — where the path has no
    # backslashes — and failed on every Windows run, the platform where the
    # upgrade actually matters. It is now compared the way the upgraded command
    # actually spells a path: forward slashes, so one command string parses in
    # cmd.exe, PowerShell and sh alike.
    assert hook_interpreter().replace("\\", "/") in upgraded.replace("\\\\", "/").replace("\\", "/")
    assert "$(git rev-parse" not in upgraded, "the POSIX-only substitution survived the upgrade"


def test_force_overwrites(tmp_project_dir: Path) -> None:
    codex_dir = tmp_project_dir / ".codex"
    codex_dir.mkdir(parents=True, exist_ok=True)
    (codex_dir / "config.toml").write_text("# old\n", encoding="utf-8")

    written = write_codex_config(tmp_project_dir, force=True)
    assert written == [".codex/config.toml"]
    body = (codex_dir / "config.toml").read_text(encoding="utf-8")
    assert "mcp_servers.scistudio" in body


# ---------------------------------------------------------------------------
# #1994 — the generated hook command must EXECUTE, not merely look right.
#
# The owner reported Codex hooks failing with a repeating exit 1 even after the
# trust gate was answered. Cause: the command resolved the project root with
# "$(git rev-parse --show-toplevel)", POSIX command substitution that no native
# Windows shell performs. Measured against the generated command:
#
#   cmd.exe    passes it through literally -> python "can't open file ...
#              \$(git rev-parse --show-toplevel)\..." -> exit 2
#   powershell fails earlier still: a command line whose first token is a
#              quoted path parses as a string expression -> exit 1
#   git bash   works, which is why Claude Code and Qoder were unaffected and
#              the failure looked Codex-specific.
#
# Every test in this area compared strings, so none of them could see this.
# These run the command instead.
# ---------------------------------------------------------------------------

import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402

import pytest  # noqa: E402


def _generated_codex_hook_command(project_dir: Path) -> str:
    """The first PreToolUse command, read back the way Codex reads it."""
    write_codex_config(project_dir, force=True)
    parsed = tomllib.loads((project_dir / ".codex" / "config.toml").read_text(encoding="utf-8"))
    return str(parsed["hooks"]["PreToolUse"][0]["hooks"][0]["command"])


def _hook_stdin_payload(project_dir: Path) -> str:
    """A PreToolUse payload shaped like the one the CLI sends on stdin."""
    return json.dumps(
        {
            "session_id": "test",
            "cwd": str(project_dir),
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
        }
    )


def _run_in_shell(shell: str, command: str, project_dir: Path) -> subprocess.CompletedProcess:
    """Run *command* through *shell* exactly as written.

    The command text is placed in a script file rather than passed as an argv
    element, because Python re-quotes argv entries and that re-quoting is itself
    capable of masking (or inventing) a quoting bug.
    """
    scripts = project_dir / "_shell_probe"
    scripts.mkdir(exist_ok=True)
    if shell == "cmd":
        script = scripts / "hook.cmd"
        script.write_text("@echo off\n" + command + "\n", encoding="utf-8")
        argv = [str(script)]
    elif shell == "powershell":
        script = scripts / "hook.ps1"
        script.write_text(command + "\n", encoding="utf-8")
        argv = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
    else:
        script = scripts / "hook.sh"
        script.write_text("#!/bin/sh\n" + command + "\n", encoding="utf-8")
        argv = ["/bin/sh", str(script)]
    return subprocess.run(
        argv,
        input=_hook_stdin_payload(project_dir),
        capture_output=True,
        text=True,
        cwd=str(project_dir),
        env=dict(os.environ),
        timeout=120,
    )


def _native_shells() -> list[str]:
    """Shells the provisioned command could actually be run by, on this OS.

    Git Bash is deliberately excluded on Windows. If Codex ran hooks through it
    the previous ``$(git rev-parse ...)`` command would have worked and the
    owner would have had no defect, so the shell is a native one.
    """
    if sys.platform == "win32":
        return ["cmd", "powershell"] if shutil.which("powershell.exe") else ["cmd"]
    return ["sh"]


@pytest.mark.parametrize("shell", _native_shells())
def test_generated_codex_hook_command_executes_on_this_platform(shell: str, tmp_project_dir: Path) -> None:
    """The generated command runs and exits zero in this platform's shell.

    This is the assertion the previous string-comparison tests could not make.
    With the old ``$(git rev-parse --show-toplevel)`` form it fails on Windows
    in both native shells, which is exactly the reported defect.
    """
    from scistudio.agent_provisioning.hooks import write_hooks

    write_hooks(tmp_project_dir, force=True)  # the hook scripts the command invokes
    command = _generated_codex_hook_command(tmp_project_dir)

    result = _run_in_shell(shell, command, tmp_project_dir)

    assert result.returncode == 0, (
        f"generated Codex hook command failed in {shell}: exit {result.returncode}\n"
        f"command: {command}\nstderr: {result.stderr}"
    )


def test_generated_codex_hook_command_has_no_shell_substitution(tmp_project_dir: Path) -> None:
    """No construct that only one shell family understands.

    Kept alongside the executing test as a fast, OS-independent guard: CI on
    Linux would pass the execution test with a POSIX-only command, and this is
    what still catches it there.
    """
    command = _generated_codex_hook_command(tmp_project_dir)

    assert "$(" not in command, f"POSIX command substitution reached the hook command: {command}"
    assert "`" not in command, f"backtick substitution reached the hook command: {command}"


def test_upgraded_config_matches_a_freshly_written_one(tmp_project_dir: Path) -> None:
    """An existing project is repaired to exactly what a new project gets.

    ``write_codex_config`` preserves an existing file, so the upgrade path is
    the only route by which already-provisioned users receive the fix. If it
    produced a different command shape, the very users who hit the defect would
    keep a subtly different one.
    """
    from scistudio.agent_provisioning.hooks import write_hooks

    write_hooks(tmp_project_dir, force=True)
    target = tmp_project_dir / ".codex" / "config.toml"

    write_codex_config(tmp_project_dir, force=True)
    fresh = target.read_text(encoding="utf-8")

    # Rewrite the file into the broken legacy shape, then let the upgrade run.
    legacy = fresh
    for _matcher, script, _status in (*_cc._PRE_HOOKS, *_cc._POST_HOOKS):
        legacy = legacy.replace(
            _toml_escape(_cc._render_hook_command(tmp_project_dir, script)),
            _toml_escape(
                f'{_cc._quote_shell_path(sys.executable)} "$(git rev-parse --show-toplevel)/.claude/hooks/{script}"'
            ),
        )
    assert legacy != fresh, "failed to construct the legacy shape for this test"
    target.write_text(legacy, encoding="utf-8")

    write_codex_config(tmp_project_dir, force=False)

    assert target.read_text(encoding="utf-8") == fresh


# ---------------------------------------------------------------------------
# #2040 — the interpreter frozen into an already-modern config.
#
# _upgrade_legacy_hook_commands repairs configs written before the #2011
# command-syntax fix and only those: it matches the two spellings carrying
# `$(git rev-parse --show-toplevel)`. A config written after that fix is
# already in the current shape and can never match, so when its interpreter
# later disappears nothing rewrites it.
# ---------------------------------------------------------------------------

_DEAD_INTERPRETER = "C:/nonexistent-scistudio/resources/python/python.exe"


def _repin_interpreter(raw: str, project_dir: Path, interpreter: str) -> str:
    """Rewrite every generated hook command to run *interpreter* instead."""
    for _matcher, script, _status in (*_cc._PRE_HOOKS, *_cc._POST_HOOKS):
        current = _cc._render_hook_command(project_dir, script)
        repinned = f"{_cc._shell_word(interpreter)} {_cc._shell_word(_cc._hook_script_path(project_dir, script))}"
        raw = raw.replace(_toml_escape(current), _toml_escape(repinned))
    return raw


def test_dead_interpreter_hook_command_is_repaired(tmp_project_dir: Path) -> None:
    """A modern-shape config whose interpreter has gone is re-rendered.

    This is the state every project provisioned after #2011 lands in once the
    interpreter disappears, and the state the legacy upgrade cannot reach.
    """
    target = tmp_project_dir / ".codex" / "config.toml"
    write_codex_config(tmp_project_dir, force=True)
    fresh = target.read_text(encoding="utf-8")

    broken = _repin_interpreter(fresh, tmp_project_dir, _DEAD_INTERPRETER)
    assert broken != fresh, "failed to construct the dead-interpreter shape for this test"
    target.write_text(broken, encoding="utf-8")

    written = write_codex_config(tmp_project_dir, force=False)

    assert ".codex/config.toml" in written
    repaired = target.read_text(encoding="utf-8")
    assert _DEAD_INTERPRETER not in repaired
    assert repaired == fresh


def test_live_interpreter_hook_command_is_left_alone(tmp_project_dir: Path) -> None:
    """A working interpreter is preserved even if it is not the current pick."""
    target = tmp_project_dir / ".codex" / "config.toml"
    write_codex_config(tmp_project_dir, force=True)
    fresh = target.read_text(encoding="utf-8")

    if sys.executable == hook_interpreter():
        deliberate = fresh
    else:
        deliberate = _repin_interpreter(fresh, tmp_project_dir, sys.executable)
        assert deliberate != fresh, "failed to construct a distinct live interpreter for this test"
    target.write_text(deliberate, encoding="utf-8")

    write_codex_config(tmp_project_dir, force=False)

    assert target.read_text(encoding="utf-8") == deliberate


def test_user_authored_codex_command_is_not_repaired(tmp_project_dir: Path) -> None:
    """A command that is not the generated shape is never rewritten.

    Identification is by the trailing script word this module would render
    today; an extra argument means the string is someone else's, so a dead
    interpreter in it is not SciStudio's to correct.
    """
    target = tmp_project_dir / ".codex" / "config.toml"
    write_codex_config(tmp_project_dir, force=True)
    fresh = target.read_text(encoding="utf-8")

    script = _cc._PRE_HOOKS[0][1]
    mine = f"{_DEAD_INTERPRETER} {_cc._shell_word(_cc._hook_script_path(tmp_project_dir, script))} --flag"
    customised = fresh.replace(_toml_escape(_cc._render_hook_command(tmp_project_dir, script)), _toml_escape(mine))
    assert customised != fresh, "failed to construct the user-authored shape for this test"
    target.write_text(customised, encoding="utf-8")

    write_codex_config(tmp_project_dir, force=False)

    assert _toml_escape(mine) in target.read_text(encoding="utf-8")


def test_legacy_command_is_upgraded_whatever_interpreter_wrote_it(tmp_project_dir: Path) -> None:
    """The legacy repair must not depend on who is running it.

    It used to match two fully spelled-out commands, one embedding
    ``sys.executable`` — the interpreter of the process running the *repair*,
    not the one that wrote the file. Those agree only when a project is
    re-provisioned from the very interpreter that provisioned it. A project
    provisioned by the packaged desktop app and reopened from any other install
    therefore kept its dead hooks, which is the state #2040 found on a real
    machine: a config still carrying ``$(git rev-parse ...)`` behind an
    interpreter that no longer existed, which re-provisioning did not touch.
    """
    target = tmp_project_dir / ".codex" / "config.toml"
    write_codex_config(tmp_project_dir, force=True)
    fresh = target.read_text(encoding="utf-8")

    legacy = fresh
    for _matcher, script, _status in (*_cc._PRE_HOOKS, *_cc._POST_HOOKS):
        legacy = legacy.replace(
            _toml_escape(_cc._render_hook_command(tmp_project_dir, script)),
            _toml_escape(f'"{_DEAD_INTERPRETER}" "$(git rev-parse --show-toplevel)/.claude/hooks/{script}"'),
        )
    assert legacy != fresh, "failed to construct the foreign-interpreter legacy shape for this test"
    target.write_text(legacy, encoding="utf-8")

    written = write_codex_config(tmp_project_dir, force=False)

    assert ".codex/config.toml" in written
    assert target.read_text(encoding="utf-8") == fresh


def test_toml_unescape_round_trips_escape() -> None:
    """`_toml_unescape` must invert `_toml_escape` exactly.

    Both repairs read a command back out of a TOML basic string before deciding
    anything about it, so a wrong inversion silently misjudges which commands
    are SciStudio's. The interesting inputs are the ones where the two escapes
    interact: undoing them with two `str.replace` calls does not commute, since
    unescaping quotes first turns a literal backslash followed by a quote into
    a string terminator, and unescaping backslashes first does the same in
    reverse.
    """
    for original in (
        r"C:\Users\jiazh\python.exe",
        r'a path with "quotes"',
        r"trailing backslash\\",
        r"\"",
        r"C:\dir\ \"odd\" name\\",
        "",
    ):
        assert _cc._toml_unescape(_toml_escape(original)) == original
