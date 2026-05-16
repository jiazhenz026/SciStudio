"""``scieasy install`` — wire SciEasy's MCP server + skill into external CLIs.

Issue #787. Lets developers use their **own** ``claude`` or ``codex``
CLI against SciEasy projects with the full 25-tool MCP surface and a
SciEasy-aware skill installed.

Layout of supported targets:

| Target | Scope     | File(s) mutated                                                                            |
|--------|-----------|--------------------------------------------------------------------------------------------|
| claude | user      | ``~/.claude.json`` (top-level ``mcpServers``)                                              |
| claude | project   | ``<cwd>/.mcp.json`` (top-level ``mcpServers``)                                             |
| codex  | user      | ``~/.codex/config.toml`` (``[mcp_servers.…]``)                                             |
| codex  | project   | ``<cwd>/.codex/config.toml`` (``[mcp_servers.…]``)                                         |
| skill  | user      | ``~/.claude/skills/scieasy/`` AND ``~/.agents/skills/scieasy/``                            |
| skill  | project   | ``<cwd>/.claude/skills/scieasy/`` AND ``<cwd>/.agents/skills/scieasy/``                    |

All operations are idempotent. ``--remove`` reverses any install.

ADR-040 §3.7 (Codex project-scope config) and §3.9 (skill cross-install
across Claude + Codex skill providers) are implemented here in I40d
Phase 2a — see #1014.

The exact file layouts above were determined empirically (not
guessed): we inspected ``~/.claude.json`` to confirm Claude Code uses
a top-level ``mcpServers`` map for user scope, and we ran
``codex mcp add`` to observe the TOML mutation Codex performs.
"""

from __future__ import annotations

import importlib.resources
import json
import logging
import os
import shutil
import sys
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


def _scieasy_command_for_env() -> tuple[str, list[str]]:
    """Return ``(command, prefix_args)`` for Claude/Codex to invoke the bridge.

    Hotfix 2026-05-14: prior version returned the result of
    ``shutil.which("scieasy")`` and the caller wrote that into
    ``mcp.json`` as the ``command``. ``shutil.which`` searches PATH —
    when the user has multiple scieasy installs on PATH (e.g. a stale
    ``.venv-agent-test`` venv left over from a previous test run), the
    wrong scieasy gets pinned into every project's ``.scieasy/mcp.json``
    and claude's MCP bridge silently uses the stale install. The
    user-visible symptom is "scieasy MCP server failed" inside the AI
    Block PTY, which kills ADR-035 §3.5 path (a).

    Now anchors at the **current interpreter's** scieasy via
    ``{sys.executable} -m scieasy ...`` so the bridge always runs from
    the same install as the engine that emitted the manifest. ``-m``
    invocation is robust against renamed venvs, PATH order, and
    Windows ``.exe`` shim differences.
    """
    return sys.executable, ["-m", "scieasy"]


def _mcp_entry_payload(project_dir: Path | None) -> dict[str, object]:
    """Build the MCP server entry written into Claude/Codex config.

    The env var ``SCIEASY_PROJECT_DIR`` is the contract the standalone
    bridge uses to locate the project; we pin it at install time when
    a project scope is in play, or leave it unset (the bridge falls
    back to ``cwd``) at user scope.
    """
    command, prefix_args = _scieasy_command_for_env()
    entry: dict[str, object] = {
        "command": command,
        "args": [*prefix_args, "mcp-bridge"],
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


def _codex_config_path(scope: str, cwd: Path) -> Path:
    """Return the Codex config path for the given *scope*.

    Per ADR-040 §3.7, Codex 2026+ discovers a project-scope
    ``<cwd>/.codex/config.toml`` when launched inside a project. For
    user scope we still write the global ``~/.codex/config.toml``.
    """
    if scope == "user":
        return Path.home() / ".codex" / "config.toml"
    if scope == "project":
        return cwd / ".codex" / "config.toml"
    raise ValueError(f"unsupported scope for codex: {scope!r}")


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
    command, prefix_args = _scieasy_command_for_env()
    args_literal = json.dumps([*prefix_args, "mcp-bridge"])
    lines = [
        f"[mcp_servers.{MCP_SERVER_NAME}]",
        f"command = {_format_toml_string(command)}",
        f"args = {args_literal}",
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
    """Write ``[mcp_servers.scieasy]`` block to Codex's config file.

    Per ADR-040 §3.7, Codex 2026+ supports both user-scope and
    project-scope config discovery:

      user scope:    ``~/.codex/config.toml``
      project scope: ``<cwd>/.codex/config.toml`` (with
                     ``SCIEASY_PROJECT_DIR`` pinned in the env table)

    Block content is rendered via :func:`_render_codex_block` regardless
    of scope; only the destination path differs.
    """
    if scope == "user":
        project_dir: Path | None = None
    elif scope == "project":
        project_dir = cwd
    else:
        raise ValueError(f"unsupported scope for codex: {scope!r}")

    path = _codex_config_path(scope, cwd)
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
    path = _codex_config_path(scope, cwd)
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


def _skill_dest(scope: str, cwd: Path) -> tuple[Path, Path]:
    """Return ``(claude_path, codex_path)`` skill destinations for *scope*.

    Per ADR-040 §3.9, ``scieasy install --skill`` cross-installs the
    bundled skill into BOTH provider trees so a single \"scieasy install\"
    call serves Claude Code (``.claude/skills/``) and Codex
    (``.agents/skills/``) without forcing the user to know which CLI
    they will reach for next:

      user scope:    ``~/.claude/skills/scieasy/`` and ``~/.agents/skills/scieasy/``
      project scope: ``<cwd>/.claude/skills/scieasy/`` and ``<cwd>/.agents/skills/scieasy/``
    """
    if scope == "user":
        base = Path.home()
    elif scope == "project":
        base = cwd
    else:
        raise ValueError(f"unsupported scope for skill: {scope!r}")
    claude_path = base / ".claude" / "skills" / MCP_SERVER_NAME
    codex_path = base / ".agents" / "skills" / MCP_SERVER_NAME
    return claude_path, codex_path


def _find_skill_source() -> Path:
    """Locate the bundled ``scieasy`` skill bundle on disk.

    Resolution order, per ADR-040 §3.4:

    1. **Packaged path** — ``importlib.resources.files("scieasy") /
       "_skills" / "scieasy"``. This is the canonical location for
       both editable and wheel installs: ``pyproject.toml``
       ``[tool.setuptools.package-data]`` declares
       ``_skills/scieasy/**/*.md`` as wheel data.
    2. **Walk-up fallback** — for dev checkouts where the packaged
       resource exists but is empty (e.g. before Phase 2c lands skill
       bodies), or for legacy editable installs that pre-date the
       relocation, walk parents of this module looking for
       ``skills/scieasy/SKILL.md`` at the repo root.

    TODO(#1011): Remove the walk-up fallback once Phase 2c (I40b)
    relocates and fills the packaged skill content. After that, the
    packaged path is the single source of truth. Followup: #1011.
    """
    # 1. Packaged path via importlib.resources (works in both wheel and
    #    editable installs).
    try:
        traversable = importlib.resources.files("scieasy") / "_skills" / MCP_SERVER_NAME
        # ``Traversable`` doesn't expose ``Path`` directly; use ``as_file``
        # only when we need to walk into it. Existence check first.
        skill_md = traversable / "SKILL.md"
        if skill_md.is_file():
            # On a real filesystem install ``traversable`` resolves to a
            # ``PosixPath``/``WindowsPath`` already. Otherwise we'd need
            # to materialise via ``as_file`` — but our package layout
            # always lives on disk (no zip imports), so we can cast.
            candidate = Path(str(traversable))
            if (candidate / "SKILL.md").is_file():
                return candidate
    except (FileNotFoundError, AttributeError, ModuleNotFoundError):
        # importlib lookup failed (rare — only if the package itself is
        # missing). Fall through to walk-up fallback.
        pass

    # 2. Walk-up fallback for dev checkouts where the packaged tree is
    #    empty / pre-relocation.
    # TODO(#1011): remove walk-up fallback once skill content (I40b Phase 2c)
    #   makes the relocated path canonical.
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
        "Could not locate the bundled SciEasy skill (expected "
        "scieasy/_skills/scieasy/SKILL.md via importlib.resources, or "
        "skills/scieasy/SKILL.md at the repo root). Ensure you installed "
        "scieasy from a wheel or are running from a source checkout."
    )


def _install_skill(scope: str, cwd: Path) -> list[InstallResult]:
    """Cross-install the SciEasy skill bundle to both Claude and Codex paths.

    Per ADR-040 §3.9, every ``--skill`` install lands in BOTH provider
    trees so a single ``scieasy install --skill`` call serves Claude
    Code (``.claude/skills/scieasy/``) and Codex
    (``.agents/skills/scieasy/``) symmetrically.

    Returns two ``InstallResult`` entries per call — one per destination.

    Always copies (never symlinks) for Windows compatibility: symbolic
    links require admin / developer mode on Windows.
    """
    src = _find_skill_source()
    claude_path, codex_path = _skill_dest(scope, cwd)
    results: list[InstallResult] = []
    for dest in (claude_path, codex_path):
        action = "updated" if dest.is_dir() else "installed"
        if dest.is_dir():
            # Wipe stale files so removed files in src don't linger.
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dest)
        results.append(
            InstallResult(
                target="skill",
                scope=scope,
                path=dest,
                action=action,
                detail=f"copied {src} -> {dest}",
            )
        )
    return results


def _remove_skill(scope: str, cwd: Path) -> list[InstallResult]:
    """Symmetric removal across both Claude and Codex skill trees.

    Per ADR-040 §3.9, ``--remove --skill`` strips BOTH
    ``.claude/skills/scieasy/`` and ``.agents/skills/scieasy/`` under
    the requested scope. Returns one ``InstallResult`` per destination.
    """
    claude_path, codex_path = _skill_dest(scope, cwd)
    results: list[InstallResult] = []
    for dest in (claude_path, codex_path):
        if not dest.is_dir():
            results.append(InstallResult(target="skill", scope=scope, path=dest, action="noop", detail="not installed"))
            continue
        shutil.rmtree(dest)
        results.append(
            InstallResult(target="skill", scope=scope, path=dest, action="removed", detail="directory removed")
        )
    return results


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
        Convenience: target=claude + codex + skill at the chosen scope.

    Notes
    -----
    Per ADR-040 §3.7, ``target="codex"`` honours ``scope="project"``
    (writes ``<cwd>/.codex/config.toml``); no force-user-scope fallback.

    Per ADR-040 §3.9, ``skill=True`` cross-installs the bundle into BOTH
    ``.claude/skills/scieasy/`` AND ``.agents/skills/scieasy/`` under
    the chosen scope. Returns one ``InstallResult`` per destination.
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
            # ADR-040 §3.7 / §3.9 (I40d, #1014): Codex 2026+ supports
            # project-scope discovery via ``<cwd>/.codex/config.toml``,
            # so we no longer force user-scope when the caller picked
            # ``--scope project``. Call directly with the requested
            # scope; ``_install_codex`` / ``_remove_codex`` resolve the
            # destination path via ``_codex_config_path(scope, cwd)``.
            results.append(_remove_codex(scope, cwd) if remove else _install_codex(scope, cwd))

    if do_skill:
        # ADR-040 §3.9 (I40d, #1014): ``_install_skill`` /
        # ``_remove_skill`` return ``list[InstallResult]`` with TWO
        # entries — one for the Claude tree (``.claude/skills/``) and
        # one for the Codex tree (``.agents/skills/``). Use ``extend``.
        results.extend(_remove_skill(scope, cwd) if remove else _install_skill(scope, cwd))

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
        help="'user' (~/.claude.json or ~/.codex/config.toml) or 'project' (<cwd>/.mcp.json or <cwd>/.codex/config.toml).",
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
