"""Write project-scoped hook config + scripts (ADR-040 §3.6).

Provisions ``<project>/.claude/settings.json`` and the 7 hook scripts at
``<project>/.claude/hooks/`` for Claude Code's hook system.

Per ADR §3.6 (matcher list expanded with ``MultiEdit`` per Codex P1
review on PR #1047 — Claude Code treats ``MultiEdit`` as a distinct
tool name; omitting it leaves a bypass path):

  PreToolUse (4):
    - hook_deny_scistudio_cli.py                      (matcher: Bash)
    - hook_protect_workflow_yaml.py                 (matcher: Edit|Write|MultiEdit)
    - hook_protect_data_dir.py                       (matcher: Edit|Write|MultiEdit|Bash)
    - hook_enforce_list_blocks_before_block_write.py
        (matcher: Edit|Write|MultiEdit|Bash|mcp__scistudio__scaffold_block)

  PostToolUse (3):
    - hook_remind_poll_status.py                    (matcher: mcp__scistudio__run_workflow)
    - hook_mark_list_blocks_called.py               (matcher: mcp__scistudio__list_blocks)
    - hook_enforce_concrete_port_types.py
        (matcher: Edit|Write|MultiEdit|mcp__scistudio__scaffold_block)

Hook scripts read JSON from stdin (Claude Code's hook stdin contract);
exit code 2 blocks the tool call (PreToolUse only); exit code 0 passes.

Self-healing the baked interpreter (#2040)
------------------------------------------

:func:`hook_interpreter` resolves an absolute path once, at provisioning time,
and that path is then frozen into every generated command. It is correct when
written — the venv branch checks ``is_file`` and the fallback returns the
running ``sys.executable`` — but nothing keeps it correct afterwards. Uninstall
the desktop app, delete a virtualenv or upgrade Python and every hook in every
project provisioned against that interpreter becomes a command whose first word
does not exist.

Nothing repaired that. :func:`_upgrade_legacy_settings_commands` matches only
the pre-#1994 bare-``python`` spelling, and :func:`_merge_missing_canonical_hooks`
appends only hooks that are *absent* — a hook that is present but dead satisfies
it. Re-opening the project, which is what a user would try, rewrote nothing.

It matters more than a broken command usually would, because the failure is
silent and fails *open*: a hook that cannot start exits 127, a non-blocking
status, so the tool call proceeds unguarded while the UI shows only a transient
warning. ``protect_data_dir.py`` and its siblings stop enforcing without ever
saying so. :func:`_repair_dead_interpreter_commands` re-renders the path;
the fail-open semantics itself is TODO(#2041).
"""

from __future__ import annotations

import importlib.resources
import json
import os
import re
import stat
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

_HOOKS_DIR_REL = ".claude/hooks"
_SETTINGS_REL = ".claude/settings.json"

#: Qoder CLI's project-scope settings file, and the project-root variable its
#: hook command strings expand (#1994 finding 3).
#:
#: Qoder is a Claude Code fork and reads the *same* settings shape from its own
#: directory. Both facts were established by running the installed CLI rather
#: than inferred: ``qoderclicn hooks migrate --from-claude`` at 1.1.15, given a
#: project SciStudio had just provisioned, wrote ``<project>/.qoder/settings.json``
#: containing our seven hook entries verbatim with ``$CLAUDE_PROJECT_DIR``
#: rewritten to ``$QODER_PROJECT_DIR``.
#:
#: ``.qoder`` — not ``.qoder-cn`` — is correct for **both** channels: the fact
#: above was observed using the China-channel binary ``qoderclicn``, whose user
#: config root is ``~/.qoder-cn`` but whose *project* scope is still ``.qoder``.
#: One file therefore serves both descriptors.
#:
#: The hook scripts themselves are not duplicated. Qoder points at the same
#: ``.claude/hooks/*.py`` files Claude Code and Codex use, which is what Qoder's
#: own migration tool does.
_QODER_SETTINGS_REL = ".qoder/settings.json"
_CLAUDE_PROJECT_DIR_VAR = "CLAUDE_PROJECT_DIR"
_QODER_PROJECT_DIR_VAR = "QODER_PROJECT_DIR"

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
    ("hook_protect_data_dir.py", "protect_data_dir.py"),
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


def _build_settings_json(hooks_dir_rel: str, project_dir_var: str = _CLAUDE_PROJECT_DIR_VAR) -> dict:
    """Build the canonical settings content per ADR §3.6.

    Hook command lines explicitly invoke the Python executable running
    SciStudio so they do not depend on a ``python`` shim being present on
    PATH. Hook script paths are project-relative via the caller's
    ``project_dir_var`` so the settings file survives moving the project
    directory.

    ``project_dir_var`` is the only thing that differs between the Claude Code
    file and the Qoder file: Claude Code expands ``$CLAUDE_PROJECT_DIR`` and
    Qoder expands ``$QODER_PROJECT_DIR``. Everything else — matchers, script
    names, event groups — is byte-identical, which is why one builder serves
    both and the two cannot drift apart as hooks are added (#1994 finding 3).
    """
    py = _quote_shell_path(hook_interpreter())
    # Codex P1 reconcile (PR #1047): include MultiEdit in every Edit|Write
    # matcher so multi-edit operations are not a bypass path. Claude Code
    # treats MultiEdit as a distinct tool name.
    pre = [
        ("Bash", "deny_scistudio_cli.py"),
        ("Edit|Write|MultiEdit", "protect_workflow_yaml.py"),
        # #1858: one matcher covers file tools + Bash; the script branches on
        # tool_name (file-tool target check vs. best-effort Bash check).
        ("Edit|Write|MultiEdit|Bash", "protect_data_dir.py"),
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
        cmd = f'{py} "${project_dir_var}/{hooks_dir_rel}/{script}"'
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


#: Marker identifying a hook script as SciStudio's own, shipped from a template
#: in this package. Present in every version SciStudio has ever written — the
#: scripts all cite the ADR that defines them — so it is a reliable test for
#: "this file is ours" against copies already on disk in the field.
_HOOK_PROVENANCE_MARKER = "ADR-040"


def _hook_script_needs_refresh(dest: Path, template_body: str) -> bool:
    """Whether an existing hook script should be rewritten from its template.

    Hook scripts were previously written **once and never again**: the loop
    below skipped any file that already existed. That is how the owner's
    project kept running hooks whose payload reader crashed on a missing stdin
    long after the template was fixed — the repaired code never reached the file
    the CLI actually executes, so re-provisioning changed nothing (#1994).

    The Codex config already had a repair path for exactly this reason. The
    scripts it points at did not, which made the config path a half-fix.

    Refresh is limited to files that still carry SciStudio's provenance marker
    and whose content has drifted from the shipped template. A user who has
    replaced a script wholesale with their own is left alone; a stale SciStudio
    copy — every copy in the field today — is repaired. This deliberately
    narrows TODO(#1860)'s blanket deferral of content-aware refresh for these
    seven files only: they are enforcement code SciStudio ships, not a user
    extension point (``settings.json`` is), and a silently stale one disables
    the protection it exists to provide.
    """
    try:
        current = dest.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        # Unreadable: leave it. Overwriting a file we cannot inspect risks
        # destroying something that is not ours.
        return False
    if current == template_body:
        return False
    return _HOOK_PROVENANCE_MARKER in current


def hook_interpreter() -> str:
    """Absolute path of the interpreter that should run the hook scripts.

    Baked into every provider's hook command at provisioning time, so it has to
    outlive the process that did the provisioning. ``sys.executable`` does not:
    it is whatever interpreter happened to run, and on the owner's machine that
    was the gate's parity venv under ``.workflow/local/venv`` — a scratch
    directory built to be thrown away (#1994). A hook pointing into it dies the
    moment it is cleaned up, and nothing announces that.

    **Chosen: a stable absolute path, resolved once at provisioning**, rather
    than re-resolving at hook time. Re-resolving would mean emitting a bare
    ``python``, which is exactly the PATH dependence an earlier fix removed —
    on Windows there is frequently no ``python`` on PATH at all, and when there
    is it may be a Microsoft Store stub. An absolute path is also the only form
    that behaves the same in all three shells the command may run under.

    Stability then comes from *which* absolute path. When SciStudio is running
    inside a virtual environment, this returns the **base** interpreter that
    venv was created from. That is sound only because every one of the seven
    hook scripts imports the standard library and nothing else — ``ast``,
    ``json``, ``os``, ``re``, ``sys``, ``pathlib`` — so they gain nothing from
    the venv's site-packages, while the base installation is strictly more
    durable than a venv built on top of it.

    Outside a venv — notably a packaged desktop build with a bundled runtime —
    ``sys.prefix == sys.base_prefix`` and ``sys.executable`` is returned
    unchanged, which is already the stable answer there.

    This deliberately does **not** apply to the MCP server command in the same
    generated files: that one runs ``-m scistudio``, so it needs the
    environment SciStudio is installed in and cannot be moved to the base
    interpreter. See the spec for that exposure.
    """
    if sys.prefix != sys.base_prefix:
        base = getattr(sys, "_base_executable", None)
        if base and Path(base).is_file():
            return str(base)
    return sys.executable


def _quote_shell_path(path: str | Path) -> str:
    """Quote an executable path for hook command strings."""
    escaped = str(path).replace('"', '\\"')
    return f'"{escaped}"'


def _legacy_python_hook_command(script: str, hooks_dir_rel: str, project_dir_var: str) -> str:
    return f'python "${project_dir_var}/{hooks_dir_rel}/{script}"'


def _iter_settings_handlers(settings: dict) -> Iterator[dict]:
    """Yield every hook handler mapping declared anywhere in ``settings``.

    Both repair passes below walk the same four levels of a user-owned file
    whose shape is not guaranteed, so each level is type-checked rather than
    assumed. Sharing one traversal keeps a malformed-input tolerance fix from
    having to be made twice.
    """
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return
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
                if isinstance(handler, dict):
                    yield handler


def _rewrite_settings_commands(settings: dict, replacement_for: Callable[[str], str | None]) -> bool:
    """Apply one command rewrite across a settings file, in place.

    ``replacement_for`` receives a command string and returns what it should
    become, or ``None`` to leave it alone. Both rewrites below are that shape,
    so neither has to restate the traversal or the "was anything changed"
    bookkeeping.
    """
    changed = False
    for handler in _iter_settings_handlers(settings):
        command = handler.get("command")
        if not isinstance(command, str):
            continue
        replacement = replacement_for(command)
        if replacement is None:
            continue
        handler["command"] = replacement
        changed = True
    return changed


def _upgrade_legacy_settings_commands(
    settings: dict,
    hooks_dir_rel: str,
    project_dir_var: str = _CLAUDE_PROJECT_DIR_VAR,
) -> bool:
    """Replace old PATH-dependent SciStudio hook commands in-place.

    User-owned custom commands are preserved. Only the exact command strings
    emitted by older SciStudio versions are upgraded.
    """
    py = _quote_shell_path(hook_interpreter())

    def _upgraded(command: str) -> str | None:
        for _template, script in _HOOK_FILES:
            if command == _legacy_python_hook_command(script, hooks_dir_rel, project_dir_var):
                return f'{py} "${project_dir_var}/{hooks_dir_rel}/{script}"'
        return None

    return _rewrite_settings_commands(settings, _upgraded)


#: The exact command shape :func:`_build_settings_json` emits: a quoted
#: absolute interpreter, one space, then the hook script under the provider's
#: project-root variable. Matched structurally, so a command a user wrote by
#: hand is never a candidate for rewriting no matter what it invokes.
_GENERATED_COMMAND_RE = re.compile(r'^"(?P<interpreter>(?:[^"\\]|\\.)*)" "\$(?P<var>\w+)/(?P<script_path>[^"]+)"$')


def _generated_command_parts(
    command: str,
    hooks_dir_rel: str,
    project_dir_var: str,
    scripts: set[str],
) -> tuple[str, str] | None:
    """Split *command* into ``(interpreter, script_path)`` if SciStudio wrote it.

    Returns ``None`` unless the string is the shape this module emits *and*
    names one of the canonical hook scripts under the expected directory and
    project-root variable. Everything else — a user's own command, a command
    for some other tool, a canonical script invoked in a spelling we never
    produced — is reported as not ours and left alone.
    """
    match = _GENERATED_COMMAND_RE.match(command)
    if match is None or match.group("var") != project_dir_var:
        return None
    script_path = match.group("script_path")
    prefix = f"{hooks_dir_rel}/"
    if not script_path.startswith(prefix) or script_path.removeprefix(prefix) not in scripts:
        return None
    return match.group("interpreter").replace('\\"', '"'), script_path


def interpreter_is_live(interpreter: str) -> bool:
    """Whether a baked interpreter path still resolves to a real file.

    Public because :mod:`scistudio.agent_provisioning.codex_config` freezes the
    same interpreter into its own hook commands and needs the same answer; two
    spellings of "is this path still usable" would be two things to keep in
    step.
    """
    if not interpreter:
        return False
    try:
        return Path(interpreter).is_file()
    except (OSError, ValueError):
        # An unusable path — too long, bad drive, illegal characters — is as
        # dead as a missing one for the purpose of deciding to re-render.
        return False


def _repair_dead_interpreter_commands(
    settings: dict,
    hooks_dir_rel: str,
    project_dir_var: str = _CLAUDE_PROJECT_DIR_VAR,
) -> bool:
    """Re-render hook commands whose baked interpreter is gone — see module docs.

    A live interpreter is left alone even when it is not the one this process
    would choose now, so a deliberate choice survives re-provisioning.
    """
    scripts = {dest for _template, dest in _HOOK_FILES}
    py = _quote_shell_path(hook_interpreter())

    def _repaired(command: str) -> str | None:
        parts = _generated_command_parts(command, hooks_dir_rel, project_dir_var, scripts)
        if parts is None or interpreter_is_live(parts[0]):
            return None
        return f'{py} "${project_dir_var}/{parts[1]}"'

    return _rewrite_settings_commands(settings, _repaired)


def _entry_command_strings(entry: object) -> list[str]:
    """Return all ``command`` strings declared by a settings hook entry."""
    if not isinstance(entry, dict):
        return []
    handlers = entry.get("hooks")
    if not isinstance(handlers, list):
        return []
    out: list[str] = []
    for handler in handlers:
        if isinstance(handler, dict) and isinstance(handler.get("command"), str):
            out.append(handler["command"])
    return out


def _entry_script_name(entry: object, script_names: set[str]) -> str | None:
    """The canonical hook script a settings entry invokes, if any."""
    for command in _entry_command_strings(entry):
        for script in script_names:
            if script in command:
                return script
    return None


def _merge_missing_canonical_hooks(settings: dict, project_dir_var: str = _CLAUDE_PROJECT_DIR_VAR) -> bool:
    """Additively register canonical hook entries missing from ``settings``.

    ADR-040 Addendum 6 top-up (#1858): when a newer SciStudio version adds a
    canonical hook, existing projects already have a ``settings.json`` and so
    the plain "write only if absent" path never registers the new matcher.
    This merge appends any canonical hook entry whose script is not referenced
    in the corresponding event group.

    Strictly additive: user-authored entries and any already-present canonical
    entry (including a user-edited matcher/command for it) are left untouched.
    Returns True if the settings dict was modified.
    """
    canonical = _build_settings_json(_HOOKS_DIR_REL, project_dir_var)["hooks"]
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        if "hooks" in settings:
            return False  # malformed user config — do not touch
        hooks = {}
        settings["hooks"] = hooks
    script_names = {dest for _template, dest in _HOOK_FILES}
    changed = False
    for event, entries in canonical.items():
        group = hooks.get(event)
        if not isinstance(group, list):
            hooks[event] = json.loads(json.dumps(entries))
            changed = True
            continue
        present = {name for entry in group if (name := _entry_script_name(entry, script_names)) is not None}
        for entry in entries:
            script = _entry_script_name(entry, script_names)
            if script is not None and script not in present:
                group.append(json.loads(json.dumps(entry)))
                present.add(script)
                changed = True
    return changed


def _write_settings_file(
    project_dir: Path,
    settings_rel: str,
    project_dir_var: str,
    *,
    force: bool,
) -> list[str]:
    """Create or top up one provider's project-scope hook settings file.

    Shared by the Claude Code file and the Qoder file because they differ only
    in location and in the project-root variable their command strings expand;
    a second copy of this logic would be a second place for the two providers'
    hook coverage to drift apart.

    Same behaviour in both cases: write when absent or forced, otherwise
    upgrade legacy command strings, repair commands whose baked interpreter has
    since disappeared (#2040), and additively merge any canonical hook the
    user's existing file is missing — never touching user-authored entries
    (ADR-040 Addendum 6, #1858).
    """
    settings_path = project_dir / settings_rel
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    if not settings_path.exists() or force:
        settings_path.write_text(
            json.dumps(_build_settings_json(_HOOKS_DIR_REL, project_dir_var), indent=2) + "\n",
            encoding="utf-8",
        )
        return [settings_rel]

    try:
        existing = json.loads(settings_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if not isinstance(existing, dict):
        return []

    # Order matters: upgrade the legacy bare-``python`` spelling into the
    # current shape first, so the interpreter repair that follows can recognise
    # it; then top up any canonical hooks this SciStudio version adds (#1858).
    # Assigned to separate names rather than OR-ed inline so none of them is
    # short-circuited away.
    upgraded = _upgrade_legacy_settings_commands(existing, _HOOKS_DIR_REL, project_dir_var)
    repaired = _repair_dead_interpreter_commands(existing, _HOOKS_DIR_REL, project_dir_var)
    merged = _merge_missing_canonical_hooks(existing, project_dir_var)
    if upgraded or repaired or merged:
        settings_path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
        return [settings_rel]
    return []


def write_hooks(
    project_dir: Path,
    *,
    force: bool = False,
) -> list[str]:
    """Write the project-scope hook settings for every hook-capable provider.

    Writes ``<project>/.claude/settings.json`` (Claude Code),
    ``<project>/.qoder/settings.json`` (both Qoder channels) and the seven
    shared hook scripts under ``<project>/.claude/hooks/``. Codex's hook
    declarations live in ``<project>/.codex/config.toml`` and are written by
    :mod:`scistudio.agent_provisioning.codex_config`.

    Returns list of project-relative paths actually written.
    """
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / ".claude").mkdir(parents=True, exist_ok=True)
    hooks_dir = project_dir / _HOOKS_DIR_REL
    hooks_dir.mkdir(parents=True, exist_ok=True)

    written: list[str] = []

    written.extend(_write_settings_file(project_dir, _SETTINGS_REL, _CLAUDE_PROJECT_DIR_VAR, force=force))
    # #1994 finding 3: the same hook set, in Qoder's own project-scope file.
    # Without this, a Qoder chat tab ran with no data-protection and no
    # tool-use hooks at all — SciStudio provisioned Claude Code and Codex and
    # silently left both Qoder channels unguarded.
    written.extend(_write_settings_file(project_dir, _QODER_SETTINGS_REL, _QODER_PROJECT_DIR_VAR, force=force))

    for template_name, dest_name in _HOOK_FILES:
        dest = hooks_dir / dest_name
        rel_path = f"{_HOOKS_DIR_REL}/{dest_name}"
        body = _load_template(template_name)
        if dest.exists() and not force and not _hook_script_needs_refresh(dest, body):
            continue
        dest.write_text(body, encoding="utf-8")
        if os.name == "posix":
            try:
                mode = dest.stat().st_mode
                dest.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            except OSError:
                pass
        written.append(rel_path)

    return written
