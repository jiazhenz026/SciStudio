"""``scieasy install`` — wire SciEasy's MCP server + skill into external CLIs.

Issue #787. Lets developers use their **own** ``claude`` or ``codex``
CLI against SciEasy projects with the full 25-tool MCP surface and a
SciEasy-aware skill installed.

Layout of supported targets:

| Target | Scope     | File mutated                                     |
|--------|-----------|--------------------------------------------------|
| claude | user      | ``~/.claude.json`` (top-level ``mcpServers``)    |
| claude | project   | ``<cwd>/.mcp.json`` (top-level ``mcpServers``)   |
| codex  | user      | ``~/.codex/config.toml`` (``[mcp_servers.…]``)   |
| skill  | user      | ``~/.claude/skills/scieasy/``                    |
| skill  | project   | ``<cwd>/.claude/skills/scieasy/``                |

All operations are idempotent. ``--remove`` reverses any install.

The exact file layouts above were determined empirically (not
guessed): we inspected ``~/.claude.json`` to confirm Claude Code uses
a top-level ``mcpServers`` map for user scope, and we ran
``codex mcp add`` to observe the TOML mutation Codex performs.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

import typer

logger = logging.getLogger(__name__)

# The name we register under in each tool's MCP server map.
# Prefixed-name in agent transcripts: ``mcp__scieasy__list_blocks`` etc.
MCP_SERVER_NAME = "scieasy"


@dataclass(frozen=True)
class InstallResult:
    """Single mutation record returned by an install/remove call."""

    target: str
    """``claude`` | ``codex`` | ``skill``."""

    scope: str
    """``user`` | ``project``."""

    path: Path
    """The file or directory mutated."""

    action: str
    """``"installed"`` | ``"updated"`` | ``"removed"`` | ``"noop"``."""

    detail: str = ""
    """Human-readable explanation surfaced via ``typer.echo``."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _scieasy_command_for_env() -> str:
    """Return the executable path Claude/Codex should invoke for the bridge.

    Prefer the resolved ``scieasy`` console script on PATH so the
    install is robust against virtualenv changes.  Fall back to
    ``"scieasy"`` (assume it's on PATH) when ``shutil.which`` doesn't
    find it — Claude/Codex will surface a clear error on first use if
    that turns out to be wrong.
    """
    resolved = shutil.which("scieasy")
    return resolved or "scieasy"


def _mcp_entry_payload(project_dir: Path | None) -> dict[str, object]:
    """Build the MCP server entry written into Claude/Codex config.

    The env var ``SCIEASY_PROJECT_DIR`` is the contract the standalone
    bridge uses to locate the project; we pin it at install time when
    a project scope is in play, or leave it unset (the bridge falls
    back to ``cwd``) at user scope.
    """
    entry: dict[str, object] = {
        "command": _scieasy_command_for_env(),
        "args": ["mcp-bridge"],
    }
    if project_dir is not None:
        entry["env"] = {"SCIEASY_PROJECT_DIR": str(project_dir)}
    return entry


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    """Write *payload* as JSON to *path* atomically (write-then-rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Claude target
# ---------------------------------------------------------------------------


def _claude_user_config_path() -> Path:
    return Path.home() / ".claude.json"


def _claude_project_config_path(cwd: Path) -> Path:
    return cwd / ".mcp.json"


def _install_claude(scope: str, cwd: Path) -> InstallResult:
    """Write the ``scieasy`` MCP entry into Claude's config (user|project)."""
    if scope == "user":
        path = _claude_user_config_path()
        project_dir: Path | None = None  # user scope: bridge resolves cwd dynamically
    elif scope == "project":
        path = _claude_project_config_path(cwd)
        project_dir = cwd
    else:
        raise ValueError(f"unsupported scope for claude: {scope!r}")

    data: dict[str, object] = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"refusing to overwrite malformed JSON at {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise RuntimeError(f"refusing to overwrite non-object JSON at {path}")

    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
    data["mcpServers"] = servers  # type: ignore[assignment]

    new_entry = _mcp_entry_payload(project_dir)
    existing = servers.get(MCP_SERVER_NAME)
    action = "installed" if existing is None else ("noop" if existing == new_entry else "updated")
    servers[MCP_SERVER_NAME] = new_entry  # type: ignore[index]

    _atomic_write_json(path, data)
    return InstallResult(
        target="claude",
        scope=scope,
        path=path,
        action=action,
        detail=f"wrote mcpServers.{MCP_SERVER_NAME} ({action})",
    )


def _remove_claude(scope: str, cwd: Path) -> InstallResult:
    if scope == "user":
        path = _claude_user_config_path()
    elif scope == "project":
        path = _claude_project_config_path(cwd)
    else:
        raise ValueError(f"unsupported scope for claude: {scope!r}")

    if not path.is_file():
        return InstallResult(target="claude", scope=scope, path=path, action="noop", detail="no config file")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"refusing to edit malformed JSON at {path}: {exc}") from exc
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    if not isinstance(servers, dict) or MCP_SERVER_NAME not in servers:
        return InstallResult(target="claude", scope=scope, path=path, action="noop", detail="entry not present")
    servers.pop(MCP_SERVER_NAME, None)
    # If we just emptied the mcpServers map at project scope, keep the
    # key as an empty object so users can see the file still belongs
    # to Claude. At user scope ~/.claude.json is shared by many keys;
    # we leave the empty map there too for consistency.
    _atomic_write_json(path, data)
    return InstallResult(
        target="claude",
        scope=scope,
        path=path,
        action="removed",
        detail=f"removed mcpServers.{MCP_SERVER_NAME}",
    )


# ---------------------------------------------------------------------------
# Codex target
# ---------------------------------------------------------------------------


def _codex_config_path() -> Path:
    return Path.home() / ".codex" / "config.toml"


def _format_toml_string(s: str) -> str:
    """Conservative TOML basic-string escaper.

    We only need to handle path-like strings (Windows backslashes,
    quotes). Anything fancier and the user should be editing the file
    by hand.
    """
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _render_codex_block(project_dir: Path | None) -> str:
    """Render the ``[mcp_servers.scieasy]`` TOML block.

    Format matches what ``codex mcp add ... -- <cmd> [args...]``
    writes — see :func:`scieasy.cli.install._verify_codex_format` in
    the tests for the round-trip check.
    """
    command = _scieasy_command_for_env()
    lines = [
        f"[mcp_servers.{MCP_SERVER_NAME}]",
        f"command = {_format_toml_string(command)}",
        'args = ["mcp-bridge"]',
    ]
    if project_dir is not None:
        lines.append("")
        lines.append(f"[mcp_servers.{MCP_SERVER_NAME}.env]")
        lines.append(f"SCIEASY_PROJECT_DIR = {_format_toml_string(str(project_dir))}")
    return "\n".join(lines) + "\n"


def _read_text_or_empty(path: Path) -> str:
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return ""


def _strip_codex_block(existing: str) -> tuple[str, bool]:
    """Remove ``[mcp_servers.scieasy]`` (and nested table) from *existing*.

    Returns ``(new_text, did_remove)``. Conservative: only strips the
    block headed by exactly ``[mcp_servers.scieasy]`` and its
    nested ``[mcp_servers.scieasy.env]`` table; any other tables
    pass through untouched. We do not need full TOML parsing because
    the install path only ever writes the canonical block produced
    by :func:`_render_codex_block`.
    """
    lines = existing.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    removed = False
    targets = {
        f"[mcp_servers.{MCP_SERVER_NAME}]",
        f"[mcp_servers.{MCP_SERVER_NAME}.env]",
    }
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped in targets:
            removed = True
            # Skip header + everything until the next header or EOF.
            i += 1
            while i < len(lines) and not lines[i].lstrip().startswith("["):
                i += 1
            # Trim a single trailing blank line we may have just orphaned.
            if out and out[-1].strip() == "":
                out.pop()
            continue
        out.append(lines[i])
        i += 1
    new_text = "".join(out)
    # Normalise: ensure exactly one trailing newline.
    new_text = new_text.rstrip("\n") + ("\n" if new_text.strip() else "")
    return new_text, removed


def _install_codex(scope: str, cwd: Path) -> InstallResult:
    if scope == "user":
        project_dir: Path | None = None
    elif scope == "project":
        project_dir = cwd
    else:
        raise ValueError(f"unsupported scope for codex: {scope!r}")

    path = _codex_config_path()
    existing = _read_text_or_empty(path)
    stripped, had_existing = _strip_codex_block(existing)
    new_block = _render_codex_block(project_dir)

    if stripped and not stripped.endswith("\n"):
        stripped += "\n"
    final = stripped + ("\n" if stripped else "") + new_block

    # Idempotency: if the existing file already contains exactly our
    # block in the right spot, no need to rewrite.
    if new_block in existing and not had_existing:
        # had_existing == False but the substring is there means the
        # comparison missed because of trailing whitespace; treat as noop.
        action = "noop"
    else:
        # Avoid spurious "updated" when the content is equivalent.
        if existing == final:
            action = "noop"
        elif had_existing:
            action = "updated"
        else:
            action = "installed"

    path.parent.mkdir(parents=True, exist_ok=True)
    if action != "noop":
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(final, encoding="utf-8")
        os.replace(tmp, path)

    return InstallResult(
        target="codex",
        scope=scope,
        path=path,
        action=action,
        detail=f"wrote [mcp_servers.{MCP_SERVER_NAME}] ({action})",
    )


def _remove_codex(scope: str, cwd: Path) -> InstallResult:
    path = _codex_config_path()
    if not path.is_file():
        return InstallResult(target="codex", scope=scope, path=path, action="noop", detail="no config file")
    existing = path.read_text(encoding="utf-8")
    stripped, removed = _strip_codex_block(existing)
    if not removed:
        return InstallResult(target="codex", scope=scope, path=path, action="noop", detail="entry not present")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(stripped, encoding="utf-8")
    os.replace(tmp, path)
    return InstallResult(
        target="codex",
        scope=scope,
        path=path,
        action="removed",
        detail=f"removed [mcp_servers.{MCP_SERVER_NAME}]",
    )


# ---------------------------------------------------------------------------
# Skill target
# ---------------------------------------------------------------------------


def _skill_dest(scope: str, cwd: Path) -> Path:
    if scope == "user":
        return Path.home() / ".claude" / "skills" / MCP_SERVER_NAME
    if scope == "project":
        return cwd / ".claude" / "skills" / MCP_SERVER_NAME
    raise ValueError(f"unsupported scope for skill: {scope!r}")


def _find_skill_source() -> Path:
    """Locate the bundled ``skills/scieasy/`` directory.

    For editable installs (development), walk up from this module to
    the repo root.  For wheel installs we package the skill alongside
    the source (the ``skills/`` directory at repo root is included via
    a future ``MANIFEST.in`` / ``pyproject`` data entry — for now
    editable-install only).
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "skills" / MCP_SERVER_NAME
        if (candidate / "SKILL.md").is_file():
            return candidate
        if (parent / "pyproject.toml").is_file():
            # Reached repo root; if skill isn't here, abort cleanly.
            if (candidate / "SKILL.md").is_file():
                return candidate
            break
    raise FileNotFoundError(
        "Could not locate the bundled SciEasy skill (expected skills/scieasy/SKILL.md). "
        "Ensure you are running from a SciEasy source checkout or editable install."
    )


def _install_skill(scope: str, cwd: Path) -> InstallResult:
    """Copy the bundled skill directory into Claude's skills tree.

    Always copies (never symlinks) for Windows compatibility — symlinks
    require admin / developer mode on Windows.
    """
    src = _find_skill_source()
    dest = _skill_dest(scope, cwd)
    action = "updated" if dest.is_dir() else "installed"
    if dest.is_dir():
        # Wipe stale files so removed files in src don't linger.
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dest)
    return InstallResult(
        target="skill",
        scope=scope,
        path=dest,
        action=action,
        detail=f"copied {src} -> {dest}",
    )


def _remove_skill(scope: str, cwd: Path) -> InstallResult:
    dest = _skill_dest(scope, cwd)
    if not dest.is_dir():
        return InstallResult(target="skill", scope=scope, path=dest, action="noop", detail="not installed")
    shutil.rmtree(dest)
    return InstallResult(target="skill", scope=scope, path=dest, action="removed", detail="directory removed")


# ---------------------------------------------------------------------------
# Public entry — used by the Typer subcommand below and by tests
# ---------------------------------------------------------------------------


def perform_install(
    *,
    target: str | None,
    scope: str,
    skill: bool,
    do_all: bool,
    remove: bool,
    cwd: Path | None = None,
) -> list[InstallResult]:
    """Dispatch one ``scieasy install`` invocation.

    Encapsulates the install/remove logic in a callable form so tests
    (and any future programmatic caller) don't need to drive Typer.

    Parameters
    ----------
    target
        ``"claude"``, ``"codex"``, or ``None`` when only ``--skill`` /
        ``--all`` was passed.
    scope
        ``"user"`` or ``"project"``.
    skill
        Install the SciEasy skill as well.
    do_all
        Convenience: target=claude + skill + codex (user scope).
    remove
        Reverse a previous install rather than performing one.
    cwd
        Project scope's base directory. Defaults to the current
        working directory.
    """
    if cwd is None:
        cwd = Path.cwd()
    if scope not in {"user", "project"}:
        raise ValueError(f"unsupported scope {scope!r}; expected 'user' or 'project'")

    results: list[InstallResult] = []
    todo_targets: list[str] = []
    do_skill = bool(skill)

    if do_all:
        todo_targets.extend(["claude", "codex"])
        do_skill = True
    elif target:
        if target not in {"claude", "codex"}:
            raise ValueError(f"unsupported target {target!r}; expected 'claude' or 'codex'")
        todo_targets.append(target)

    if not todo_targets and not do_skill:
        raise ValueError("Nothing to do: pass --target {claude,codex}, --skill, or --all.")

    for tgt in todo_targets:
        if tgt == "claude":
            results.append(_remove_claude(scope, cwd) if remove else _install_claude(scope, cwd))
        elif tgt == "codex":
            # Codex has no project-scope config file; force user-scope
            # for codex even when the user picked --scope project for
            # claude. Surface that fact in the result's detail.
            results.append(_remove_codex("user", cwd) if remove else _install_codex("user", cwd))
            if scope == "project":
                results[-1] = InstallResult(
                    target=results[-1].target,
                    scope=results[-1].scope,
                    path=results[-1].path,
                    action=results[-1].action,
                    detail=results[-1].detail + " (codex has no project-scope config file; wrote to user scope)",
                )
    if do_skill:
        results.append(_remove_skill(scope, cwd) if remove else _install_skill(scope, cwd))

    return results


# ---------------------------------------------------------------------------
# Typer wiring
# ---------------------------------------------------------------------------


def _emit_results(results: list[InstallResult]) -> None:
    for r in results:
        typer.echo(f"[{r.target}/{r.scope}] {r.action}: {r.path}")
        if r.detail:
            typer.echo(f"    {r.detail}")


def _typer_command(
    target: str = typer.Option(
        None,
        "--target",
        "-t",
        help="Which CLI to install for: 'claude' or 'codex'.",
    ),
    scope: str = typer.Option(
        "user",
        "--scope",
        "-s",
        help="'user' (~/.claude.json or ~/.codex/config.toml) or 'project' (<cwd>/.mcp.json).",
    ),
    skill: bool = typer.Option(
        False,
        "--skill",
        help="Also install the SciEasy skill into Claude's skills directory.",
    ),
    do_all: bool = typer.Option(
        False,
        "--all",
        help="Convenience: install for claude + codex + skill at user scope.",
    ),
    remove: bool = typer.Option(
        False,
        "--remove",
        help="Reverse the install (remove SciEasy entry / delete skill dir).",
    ),
) -> None:
    try:
        results = perform_install(
            target=target,
            scope=scope,
            skill=skill,
            do_all=do_all,
            remove=remove,
        )
    except (ValueError, FileNotFoundError, RuntimeError) as exc:
        typer.echo(f"scieasy install: {exc}", err=True)
        raise typer.Exit(code=2) from None
    except Exception as exc:  # pragma: no cover - defensive
        typer.echo(f"scieasy install: unexpected error: {exc}", err=True)
        raise typer.Exit(code=1) from None
    _emit_results(results)


def register(app: typer.Typer) -> None:
    """Register the ``install`` subcommand on the given Typer app."""
    app.command(
        "install",
        help=("Wire SciEasy's MCP server (and optional skill) into an external CLI such as `claude` or `codex`."),
    )(_typer_command)


if __name__ == "__main__":  # pragma: no cover
    app = typer.Typer()
    register(app)
    app()
