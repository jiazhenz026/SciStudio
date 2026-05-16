"""Write project-scoped hook config + scripts (ADR-040 §3.6).

Provisions ``<project>/.claude/settings.json`` and the 6 hook scripts at
``<project>/.claude/hooks/`` for Claude Code's hook system.

Per ADR §3.6:

  PreToolUse (3):
    - hook_deny_scieasy_cli.py                      (matcher: Bash)
    - hook_protect_workflow_yaml.py                 (matcher: Edit|Write)
    - hook_enforce_list_blocks_before_block_write.py
        (matcher: Edit|Write|Bash|mcp__scieasy__scaffold_block)

  PostToolUse (3):
    - hook_remind_poll_status.py                    (matcher: mcp__scieasy__run_workflow)
    - hook_mark_list_blocks_called.py               (matcher: mcp__scieasy__list_blocks)
    - hook_enforce_concrete_port_types.py
        (matcher: Edit|Write|mcp__scieasy__scaffold_block)

Hook scripts read JSON from stdin (Claude Code's hook stdin contract);
exit code 2 blocks the tool call (PreToolUse only); exit code 0 passes.
"""

from __future__ import annotations

import importlib.resources
import json
import os
import stat
from pathlib import Path

_HOOKS_DIR_REL = ".claude/hooks"
_SETTINGS_REL = ".claude/settings.json"

# (template_filename, destination_filename) — strip the "hook_" prefix.
_HOOK_FILES: tuple[tuple[str, str], ...] = (
    ("hook_deny_scieasy_cli.py", "deny_scieasy_cli.py"),
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
            importlib.resources.files("scieasy.agent_provisioning.templates")
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

    Hook command lines explicitly invoke ``python`` so the executable
    bit is not required on Windows. Paths are project-relative via
    ``$CLAUDE_PROJECT_DIR`` so the settings.json survives moving the
    project directory.
    """
    py = "python"  # interpreter resolved by PATH in the user's shell
    pre = [
        ("Bash", "deny_scieasy_cli.py"),
        ("Edit|Write", "protect_workflow_yaml.py"),
        (
            "Edit|Write|Bash|mcp__scieasy__scaffold_block",
            "enforce_list_blocks_before_block_write.py",
        ),
    ]
    post = [
        ("mcp__scieasy__run_workflow", "remind_poll_status.py"),
        ("mcp__scieasy__list_blocks", "mark_list_blocks_called.py"),
        ("Edit|Write|mcp__scieasy__scaffold_block", "enforce_concrete_port_types.py"),
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
