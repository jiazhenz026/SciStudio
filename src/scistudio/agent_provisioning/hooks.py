"""Write project-scoped hook config + scripts (ADR-040 §3.6).

Provisions ``<project>/.claude/settings.json`` and the 6 hook scripts at
``<project>/.claude/hooks/`` for Claude Code's hook system.

Per ADR §3.6 (matcher list expanded with ``MultiEdit`` per Codex P1
review on PR #1047 — Claude Code treats ``MultiEdit`` as a distinct
tool name; omitting it leaves a bypass path):

  PreToolUse (3):
    - hook_deny_scistudio_cli.py                      (matcher: Bash)
    - hook_protect_workflow_yaml.py                 (matcher: Edit|Write|MultiEdit)
    - hook_enforce_list_blocks_before_block_write.py
        (matcher: Edit|Write|MultiEdit|Bash|mcp__scistudio__scaffold_block)

  PostToolUse (3):
    - hook_remind_poll_status.py                    (matcher: mcp__scistudio__run_workflow)
    - hook_mark_list_blocks_called.py               (matcher: mcp__scistudio__list_blocks)
    - hook_enforce_concrete_port_types.py
        (matcher: Edit|Write|MultiEdit|mcp__scistudio__scaffold_block)

Hook scripts read JSON from stdin (Claude Code's hook stdin contract);
exit code 2 blocks the tool call (PreToolUse only); exit code 0 passes.
"""

from __future__ import annotations

import importlib.resources
import json
import os
import stat
import sys
from pathlib import Path

_HOOKS_DIR_REL = ".claude/hooks"
_SETTINGS_REL = ".claude/settings.json"

# (template_filename, destination_filename) — strip the "hook_" prefix.
#
# NOTE: ``hook_worktree_write_guard.py`` is intentionally NOT provisioned into
# user projects (#1793). It enforces SciStudio *repository* development policy
# (ADR-042 worktree + gate scope) and has no meaning in an end-user data
# project; provisioned into production it could even wrongly block the in-app
# agent's writes. It remains available for SciStudio-repo development via
# ``scripts/hooks/check-worktree-write-guard.sh``.
_HOOK_FILES: tuple[tuple[str, str], ...] = (
    ("hook_deny_scistudio_cli.py", "deny_scistudio_cli.py"),
    ("hook_protect_workflow_yaml.py", "protect_workflow_yaml.py"),
    (
        "hook_enforce_list_blocks_before_block_write.py",
        "enforce_list_blocks_before_block_write.py",
    ),
    ("hook_remind_poll_status.py", "remind_poll_status.py"),
    ("hook_mark_list_blocks_called.py", "mark_list_blocks_called.py"),
    ("hook_enforce_concrete_port_types.py", "enforce_concrete_port_types.py"),
)


def _load_template(filename: str) -> str:
    """Read a bundled hook template via importlib.resources."""
    try:
        return (
            importlib.resources.files("scistudio.agent_provisioning.templates")
            .joinpath(filename)
            .read_text(encoding="utf-8")
        )
    except (FileNotFoundError, ModuleNotFoundError):
        here = Path(__file__).resolve()
        candidate = here.parent / "templates" / filename
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
        raise


def _build_settings_json(hooks_dir_rel: str) -> dict:
    """Build the canonical ``.claude/settings.json`` content per ADR §3.6.

    Hook command lines explicitly invoke the Python executable running
    SciStudio so they do not depend on a ``python`` shim being present on
    PATH. Hook script paths are project-relative via ``$CLAUDE_PROJECT_DIR``
    so the settings.json survives moving the project directory.
    """
    py = _quote_shell_path(sys.executable)
    # Codex P1 reconcile (PR #1047): include MultiEdit in every Edit|Write
    # matcher so multi-edit operations are not a bypass path. Claude Code
    # treats MultiEdit as a distinct tool name.
    pre = [
        ("Bash", "deny_scistudio_cli.py"),
        ("Edit|Write|MultiEdit", "protect_workflow_yaml.py"),
        (
            "Edit|Write|MultiEdit|Bash|mcp__scistudio__scaffold_block",
            "enforce_list_blocks_before_block_write.py",
        ),
    ]
    post = [
        ("mcp__scistudio__run_workflow", "remind_poll_status.py"),
        ("mcp__scistudio__list_blocks", "mark_list_blocks_called.py"),
        (
            "Edit|Write|MultiEdit|mcp__scistudio__scaffold_block",
            "enforce_concrete_port_types.py",
        ),
    ]

    def _entry(matcher: str, script: str) -> dict:
        cmd = f'{py} "$CLAUDE_PROJECT_DIR/{hooks_dir_rel}/{script}"'
        return {
            "matcher": matcher,
            "hooks": [{"type": "command", "command": cmd}],
        }

    return {
        "hooks": {
            "PreToolUse": [_entry(m, s) for m, s in pre],
            "PostToolUse": [_entry(m, s) for m, s in post],
        }
    }


def _quote_shell_path(path: str | Path) -> str:
    """Quote an executable path for hook command strings."""
    escaped = str(path).replace('"', '\\"')
    return f'"{escaped}"'


def _legacy_python_hook_command(script: str, hooks_dir_rel: str) -> str:
    return f'python "$CLAUDE_PROJECT_DIR/{hooks_dir_rel}/{script}"'


def _upgrade_legacy_settings_commands(settings: dict, hooks_dir_rel: str) -> bool:
    """Replace old PATH-dependent SciStudio hook commands in-place.

    User-owned custom commands are preserved. Only the exact command strings
    emitted by older SciStudio versions are upgraded.
    """
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return False
    scripts = {dest for _template, dest in _HOOK_FILES}
    py = _quote_shell_path(sys.executable)
    changed = False
    for groups in hooks.values():
        if not isinstance(groups, list):
            continue
        for entry in groups:
            if not isinstance(entry, dict):
                continue
            handlers = entry.get("hooks")
            if not isinstance(handlers, list):
                continue
            for handler in handlers:
                if not isinstance(handler, dict):
                    continue
                command = handler.get("command")
                if not isinstance(command, str):
                    continue
                for script in scripts:
                    if command == _legacy_python_hook_command(script, hooks_dir_rel):
                        handler["command"] = f'{py} "$CLAUDE_PROJECT_DIR/{hooks_dir_rel}/{script}"'
                        changed = True
                        break
    return changed


def write_hooks(
    project_dir: Path,
    *,
    force: bool = False,
) -> list[str]:
    """Write ``<project>/.claude/settings.json`` + 6 hook scripts.

    Returns list of project-relative paths actually written.
    """
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / ".claude").mkdir(parents=True, exist_ok=True)
    hooks_dir = project_dir / _HOOKS_DIR_REL
    hooks_dir.mkdir(parents=True, exist_ok=True)

    written: list[str] = []

    settings_path = project_dir / _SETTINGS_REL
    if not settings_path.exists() or force:
        settings_path.write_text(
            json.dumps(_build_settings_json(_HOOKS_DIR_REL), indent=2) + "\n",
            encoding="utf-8",
        )
        written.append(_SETTINGS_REL)
    else:
        try:
            existing = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = None
        if isinstance(existing, dict) and _upgrade_legacy_settings_commands(existing, _HOOKS_DIR_REL):
            settings_path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
            written.append(_SETTINGS_REL)

    for template_name, dest_name in _HOOK_FILES:
        dest = hooks_dir / dest_name
        rel_path = f"{_HOOKS_DIR_REL}/{dest_name}"
        if dest.exists() and not force:
            continue
        body = _load_template(template_name)
        dest.write_text(body, encoding="utf-8")
        if os.name == "posix":
            try:
                mode = dest.stat().st_mode
                dest.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            except OSError:
                pass
        written.append(rel_path)

    return written
