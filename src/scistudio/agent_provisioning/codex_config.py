"""Write project-scope Codex MCP config + hook declarations (ADR-040 §3.7 + Addendum 4).

Writes ``<project>/.codex/config.toml`` containing:

  * A single ``[mcp_servers.scistudio]`` block (and nested
    ``[mcp_servers.scistudio.env]`` table) pinning ``SCISTUDIO_PROJECT_DIR``
    to the absolute project path. Rendered by
    :func:`scistudio.cli.install._render_codex_block` so this auto-installed
    TOML is byte-identical to what ``scistudio install --target codex
    --scope project`` emits.

  * ``features.hooks = true`` to enable Codex 0.130+'s hook surface.

  * Six ``[[hooks.PreToolUse]]`` / ``[[hooks.PostToolUse]]`` matcher
    groups that point at the **same** Python scripts under
    ``<project>/.claude/hooks/`` that Claude Code uses. Codex 0.130's
    hook system uses the same stdin-JSON contract (`session_id`, `cwd`,
    `tool_name`, `tool_input`, exit code 2 + stderr blocks the call) —
    so a single set of Python scripts covers both providers.

``worktree_write_guard.py`` is intentionally excluded (#1793): it enforces
SciStudio *repository* development policy (ADR-042 worktree + gate scope) and
must not be provisioned into end-user projects — see ``hooks.py``.

This reverses ADR-040 §3.10's original "Codex hook coverage deferred"
gap per Phase 4 e2e user directive — Codex must enforce the same rules
Claude Code does. See ADR-040 Addendum 4 for the rationale and the
matcher-table mapping.

Codex 2026 walks from project root to cwd loading every
``.codex/config.toml`` — so the project-scope file takes precedence
over ``~/.codex/config.toml`` for sessions opened inside this project.
"""

from __future__ import annotations

import sys
from pathlib import Path

_TARGET_REL = ".codex/config.toml"

# Codex 0.130 emits the user's shell-tool calls under the ``Bash`` tool
# name for Claude Code compatibility (per
# https://developers.openai.com/codex/config-reference). MCP-tool calls
# arrive under their fully-qualified ``mcp__scistudio__*`` name, identical
# to Claude Code's MCP tool naming. ``apply_patch`` is Codex's
# edit/write equivalent; we match both ``Edit|Write`` (for cross-tool
# compatibility) and ``^apply_patch$`` so the same hook fires regardless
# of which surface Codex routes through on a given turn.
_PRE_HOOKS: tuple[tuple[str, str, str], ...] = (
    ("^Bash$", "deny_scistudio_cli.py", "Checking SciStudio CLI usage"),
    (
        "^(Edit|Write|MultiEdit|apply_patch)$",
        "protect_workflow_yaml.py",
        "Protecting workflows/*.yaml from direct edits",
    ),
    (
        "^(Edit|Write|MultiEdit|apply_patch|Bash)$",
        "protect_data_dir.py",
        "Protecting project data/ from direct agent edits",
    ),
    (
        "^(Edit|Write|MultiEdit|apply_patch|Bash|mcp__scistudio__scaffold_block)$",
        "enforce_list_blocks_before_block_write.py",
        "Enforcing #875 block-reuse rule",
    ),
)

_POST_HOOKS: tuple[tuple[str, str, str], ...] = (
    (
        "^mcp__scistudio__run_workflow$",
        "remind_poll_status.py",
        "Reminding to poll run status",
    ),
    (
        "^mcp__scistudio__list_blocks$",
        "mark_list_blocks_called.py",
        "Marking list_blocks called in this session",
    ),
    (
        "^(Edit|Write|MultiEdit|apply_patch|mcp__scistudio__scaffold_block)$",
        "enforce_concrete_port_types.py",
        "Checking port types for §3.2a compliance",
    ),
)


def _toml_escape(value: str) -> str:
    """TOML basic-string escape — backslash + double-quote only.

    Hook commands embed Windows paths with backslashes (when the user's
    project lives outside a git worktree); keep them literal by using
    TOML basic strings with the minimal escape set.
    """
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _render_hook_command(script_name: str) -> str:
    """Render the shell command that invokes one hook script.

    Uses ``git rev-parse --show-toplevel`` to resolve the project root
    so the same TOML works regardless of the user's CWD inside the
    project. The Claude-side `.claude/hooks/` directory is the canonical
    home for the scripts; Codex shares them rather than duplicating.

    On Windows the shell that executes this is whatever Codex spawns
    (PowerShell or bash via Git for Windows); `git rev-parse` works in
    both. The Python executable is pinned to the interpreter running
    SciStudio so hooks do not depend on a ``python`` shim being present
    on PATH.
    """
    return f'{_quote_shell_path(sys.executable)} "$(git rev-parse --show-toplevel)/.claude/hooks/{script_name}"'


def _quote_shell_path(path: str | Path) -> str:
    escaped = str(path).replace('"', '\\"')
    return f'"{escaped}"'


def _upgrade_legacy_hook_commands(raw: str) -> str:
    legacy = 'python "$(git rev-parse --show-toplevel)/.claude/hooks/'
    current = f'{_quote_shell_path(sys.executable)} "$(git rev-parse --show-toplevel)/.claude/hooks/'
    return raw.replace(_toml_escape(legacy), _toml_escape(current)).replace(legacy, current)


def _render_hooks_block() -> str:
    """Render the ``[features]`` + 6 ``[[hooks.*]]`` matcher groups."""
    lines: list[str] = []

    lines.append("[features]")
    lines.append("# ADR-040 §3.6 — same six hooks that Claude Code installs;")
    lines.append("# Codex 0.130+ honours them via the project-scope config.")
    lines.append("hooks = true")
    lines.append("")

    for matcher, script, status_message in _PRE_HOOKS:
        lines.append("[[hooks.PreToolUse]]")
        lines.append(f'matcher = "{_toml_escape(matcher)}"')
        lines.append("")
        lines.append("[[hooks.PreToolUse.hooks]]")
        lines.append('type = "command"')
        lines.append(f'command = "{_toml_escape(_render_hook_command(script))}"')
        lines.append("timeout = 30")
        lines.append(f'statusMessage = "{_toml_escape(status_message)}"')
        lines.append("")

    for matcher, script, status_message in _POST_HOOKS:
        lines.append("[[hooks.PostToolUse]]")
        lines.append(f'matcher = "{_toml_escape(matcher)}"')
        lines.append("")
        lines.append("[[hooks.PostToolUse.hooks]]")
        lines.append('type = "command"')
        lines.append(f'command = "{_toml_escape(_render_hook_command(script))}"')
        lines.append("timeout = 30")
        lines.append(f'statusMessage = "{_toml_escape(status_message)}"')
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


def write_codex_config(
    project_dir: Path,
    *,
    force: bool = False,
) -> list[str]:
    """Write ``<project>/.codex/config.toml`` with MCP block + hooks.

    Inputs:
      project_dir : Path to project root (absolute path is encoded into
                    the TOML as the ``SCISTUDIO_PROJECT_DIR`` env var value).
      force       : True to overwrite; False to preserve.

    Returns:
      List of project-relative paths actually written.
    """
    dest = project_dir / _TARGET_REL
    if dest.exists() and not force:
        try:
            raw = dest.read_text(encoding="utf-8")
        except OSError:
            return []
        upgraded = _upgrade_legacy_hook_commands(raw)
        if upgraded != raw:
            dest.write_text(upgraded, encoding="utf-8")
            return [_TARGET_REL]
        return []

    # Local import: avoid pulling scistudio.cli.install at module load time;
    # install.py imports typer + heavier deps.
    from scistudio.cli.install import _render_codex_block

    mcp_block = _render_codex_block(project_dir.resolve()).rstrip("\n") + "\n"
    hooks_block = _render_hooks_block()
    rendered = mcp_block + "\n" + hooks_block

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(rendered, encoding="utf-8")
    return [_TARGET_REL]
