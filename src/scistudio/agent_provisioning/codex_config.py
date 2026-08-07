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

import os
import sys
from pathlib import Path

from scistudio.agent_provisioning.hooks import hook_interpreter

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


def _hook_script_path(project_dir: Path, script_name: str) -> Path:
    """Absolute path of one shared hook script inside *project_dir*."""
    return project_dir / ".claude" / "hooks" / script_name


def _render_hook_command(project_dir: Path, script_name: str) -> str:
    """Render the shell command that invokes one hook script.

    The project root is **baked in as an absolute path** (#1994). It used to be
    resolved at hook-execution time with ``"$(git rev-parse --show-toplevel)"``,
    which is POSIX command substitution that no native Windows shell performs.
    The docstring here previously claimed ``git rev-parse`` "works in both"
    PowerShell and bash on Windows. Measured against the generated command on a
    real machine, it works in neither:

    * ``cmd.exe`` passes the text through **literally**, so Python is handed a
      path still containing ``$(git rev-parse --show-toplevel)`` and reports
      ``can't open file`` — exit 2.
    * ``powershell.exe`` never gets that far: a command line whose first token
      is a quoted path parses as a *string expression* rather than an
      invocation, so it fails with ``Unexpected token`` — exit 1.
    * Only a POSIX shell (Git Bash) succeeded. Claude Code and both Qoder
      channels run hooks through Git Bash, which is why they were unaffected
      and why this looked Codex-specific.

    So every Codex hook exited nonzero on every invocation — the repeating
    ``exit 1`` the owner reported, and the reason no SciStudio hook has ever
    enforced anything under Codex on Windows.

    An absolute path removes the construct rather than translating it per
    shell, so no shell has anything left to interpret. It costs nothing in
    CWD-independence, and this file already bakes absolute paths for
    ``SCISTUDIO_PROJECT_DIR`` and the interpreter, so a moved project already
    needed re-provisioning — which happens on project open.
    """
    return f"{_shell_word(hook_interpreter())} {_shell_word(_hook_script_path(project_dir, script_name))}"


def _quote_shell_path(path: str | Path) -> str:
    escaped = str(path).replace('"', '\\"')
    return f'"{escaped}"'


#: Characters that occur in ordinary Windows and POSIX paths and need no
#: quoting in ``cmd.exe``, PowerShell or ``sh``. A path built only from these
#: can be emitted bare, which is what lets one string parse in all of them.
_SHELL_SAFE_PATH_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.:/\\+~")


def _shell_word(path: str | Path) -> str:
    """Render *path* as one shell word that parses in every candidate shell.

    Which shell Codex uses to run hooks on Windows is undocumented, and could
    not be established here: no hook could be made to execute under Codex at
    all in a scratch project, so the shell was never observable. Rather than
    bet on one, this produces a word that ``cmd.exe``, PowerShell and ``sh``
    all accept — verified by running the generated command through each
    (#1994). Two properties get it there, and both are needed:

    **Forward slashes.** A POSIX shell treats a backslash as an escape, so a
    bare Windows path collapses to ``C:UsersjiazhpythonPexe`` — ``command not
    found``. ``cmd.exe`` and PowerShell both accept forward slashes in an
    absolute path that starts with a drive letter, so one spelling serves all
    three. This is a no-op on POSIX, where paths already use them.

    **No quotes unless required.** PowerShell parses a command line whose
    *first* token is a quoted string as a string expression rather than an
    invocation, and fails with ``Unexpected token`` before running anything —
    exit 1. A bare first token is a command in all three shells. A path
    containing a space still has to be quoted, and that case remains exposed to
    PowerShell's behaviour; it is left rather than papered over, because the
    call operator that would fix it there is itself a syntax error in the other
    two.
    """
    text = str(path)
    if os.sep == "\\":
        # Windows only: pathlib emits backslashes, which a POSIX shell would
        # treat as escapes. Guarded so a POSIX filename that legitimately
        # contains a backslash is left alone.
        text = text.replace("\\", "/")
    if text and all(char in _SHELL_SAFE_PATH_CHARS for char in text):
        return text
    return _quote_shell_path(text)


#: The POSIX-only project-root construct every previously generated config
#: carries. Matched literally so the repair cannot touch anything else.
_LEGACY_ROOT_EXPR = '"$(git rev-parse --show-toplevel)/.claude/hooks/'


def _upgrade_legacy_hook_commands(raw: str, project_dir: Path) -> str:
    """Repair hook commands in an existing ``config.toml`` in place.

    This is the only route by which already-provisioned users receive the fix,
    because :func:`write_codex_config` preserves an existing file rather than
    rewriting it. Every Codex config SciStudio has ever written carries the
    broken substitution, so without this an existing project keeps dead hooks
    indefinitely.

    Each known hook script has its *whole* legacy command replaced with the
    freshly rendered one, so an upgraded file is byte-identical to one written
    from scratch. Patching only the substitution would have left the old
    quoting in place, and that quoting is itself half the defect — see
    :func:`_shell_word`.

    Only commands SciStudio emitted are matched, so a user-written hook command
    is untouched. Both the raw and TOML-escaped spellings are handled, since the
    value lives in a TOML basic string where backslashes are doubled.
    """
    for _matcher, script, _status in (*_PRE_HOOKS, *_POST_HOOKS):
        fixed = _render_hook_command(project_dir, script)
        legacy_forms = (
            f'python {_LEGACY_ROOT_EXPR}{script}"',
            f'{_quote_shell_path(sys.executable)} {_LEGACY_ROOT_EXPR}{script}"',
        )
        for old in legacy_forms:
            raw = raw.replace(_toml_escape(old), _toml_escape(fixed)).replace(old, fixed)
    return raw


def _render_hooks_block(project_dir: Path) -> str:
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
        lines.append(f'command = "{_toml_escape(_render_hook_command(project_dir, script))}"')
        lines.append("timeout = 30")
        lines.append(f'statusMessage = "{_toml_escape(status_message)}"')
        lines.append("")

    for matcher, script, status_message in _POST_HOOKS:
        lines.append("[[hooks.PostToolUse]]")
        lines.append(f'matcher = "{_toml_escape(matcher)}"')
        lines.append("")
        lines.append("[[hooks.PostToolUse.hooks]]")
        lines.append('type = "command"')
        lines.append(f'command = "{_toml_escape(_render_hook_command(project_dir, script))}"')
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
        upgraded = _upgrade_legacy_hook_commands(raw, project_dir)
        if upgraded != raw:
            dest.write_text(upgraded, encoding="utf-8")
            return [_TARGET_REL]
        return []

    # Local import: avoid pulling scistudio.cli.install at module load time;
    # install.py imports typer + heavier deps.
    from scistudio.cli.install import _render_codex_block

    mcp_block = _render_codex_block(project_dir.resolve()).rstrip("\n") + "\n"
    hooks_block = _render_hooks_block(project_dir)
    rendered = mcp_block + "\n" + hooks_block

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(rendered, encoding="utf-8")
    return [_TARGET_REL]
