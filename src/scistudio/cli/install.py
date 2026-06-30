"""``scistudio install`` — wire SciStudio's MCP server + skill into external CLIs.

Issue #787; cross-install + project-scope codex landed in I40d (ADR-040 §3.7
+ §3.9, #1035). Lets developers use their **own** ``claude`` or ``codex`` CLI
against SciStudio projects with the full 25-tool MCP surface and SciStudio-aware
skills installed.

Layout of supported targets:

| Target | Scope     | File(s) mutated                                                       |
|--------|-----------|-----------------------------------------------------------------------|
| claude | user      | ``~/.claude.json`` (top-level ``mcpServers``)                         |
| claude | project   | ``<cwd>/.mcp.json`` (top-level ``mcpServers``)                        |
| codex  | user      | ``~/.codex/config.toml`` (``[mcp_servers.…]``)                        |
| codex  | project   | ``<cwd>/.codex/config.toml`` (``[mcp_servers.…]``) — Codex 2026       |
| skill  | user      | ``~/.claude/skills/scistudio/`` AND ``~/.agents/skills/scistudio/``       |
| skill  | project   | ``<cwd>/.claude/skills/scistudio/`` AND ``<cwd>/.agents/skills/scistudio/`` |

All operations are idempotent. ``--remove`` reverses any install.

The exact file layouts above were determined empirically (not
guessed): we inspected ``~/.claude.json`` to confirm Claude Code uses
a top-level ``mcpServers`` map for user scope, and we ran
``codex mcp add`` to observe the TOML mutation Codex performs.
"""

from __future__ import annotations

import importlib.resources as importlib_resources
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
# Prefixed-name in agent transcripts: ``mcp__scistudio__list_blocks`` etc.
MCP_SERVER_NAME = "scistudio"


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


def _scistudio_command_for_env() -> tuple[str, list[str]]:
    """Return ``(command, prefix_args)`` for Claude/Codex to invoke the bridge.

    Hotfix 2026-05-14: prior version returned the result of
    ``shutil.which("scistudio")`` and the caller wrote that into
    ``mcp.json`` as the ``command``. ``shutil.which`` searches PATH —
    when the user has multiple scistudio installs on PATH (e.g. a stale
    ``.venv-agent-test`` venv left over from a previous test run), the
    wrong scistudio gets pinned into every project's ``.scistudio/mcp.json``
    and claude's MCP bridge silently uses the stale install. The
    user-visible symptom is "scistudio MCP server failed" inside the AI
    Block PTY, which kills ADR-035 §3.5 path (a).

    Now anchors at the **current interpreter's** scistudio via
    ``{sys.executable} -m scistudio ...`` so the bridge always runs from
    the same install as the engine that emitted the manifest. ``-m``
    invocation is robust against renamed venvs, PATH order, and
    Windows ``.exe`` shim differences.
    """
    return sys.executable, ["-m", "scistudio"]


def _mcp_bridge_pythonpath() -> str | None:
    """PYTHONPATH that lets ``<python> -m scistudio mcp-bridge`` import scistudio.

    The bridge command pins ``sys.executable`` (see
    :func:`_scistudio_command_for_env`), but in dev checkouts and the packaged
    desktop app the ``scistudio`` package is **not** in that interpreter's
    site-packages — it is importable only via ``PYTHONPATH`` pointing at the
    backend ``src`` snapshot.

    The two embedded providers launch the MCP server with different inherited
    environments, which is why Claude Code worked while Codex did not (#1889):

    * **Claude Code** launches the stdio MCP server inheriting the backend
      process's full environment, so its ``PYTHONPATH`` carries through and
      ``-m scistudio`` resolves.
    * **Codex** launches the stdio MCP server in a *stripped* environment that
      drops ``PYTHONPATH``; the only env it sees is what we inject. With no
      ``PYTHONPATH`` the bridge dies with ``No module named scistudio`` and
      Codex reports ``MCP server failed``.

    Injecting ``PYTHONPATH`` into the server ``env`` makes the launch
    environment self-contained and identical for both providers regardless of
    whether the launcher inherits the parent environment. Returns ``None`` only
    when no path can be determined (``scistudio`` already on the default path
    and no ambient ``PYTHONPATH``).
    """
    import scistudio

    parts: list[str] = [str(Path(scistudio.__file__).resolve().parents[1])]
    existing = os.environ.get("PYTHONPATH")
    if existing:
        parts.extend(existing.split(os.pathsep))
    seen: set[str] = set()
    ordered: list[str] = []
    for part in parts:
        if part and part not in seen:
            seen.add(part)
            ordered.append(part)
    return os.pathsep.join(ordered) if ordered else None


def _mcp_entry_payload(project_dir: Path | None) -> dict[str, object]:
    """Build the MCP server entry written into Claude/Codex config.

    The env var ``SCISTUDIO_PROJECT_DIR`` is the contract the standalone
    bridge uses to locate the project; we pin it at install time when
    a project scope is in play, or leave it unset (the bridge falls
    back to ``cwd``) at user scope. ``PYTHONPATH`` is injected so the bridge
    imports ``scistudio`` even when the launcher (Codex) strips the parent
    environment — see :func:`_mcp_bridge_pythonpath` (#1889).
    """
    command, prefix_args = _scistudio_command_for_env()
    entry: dict[str, object] = {
        "command": command,
        "args": [*prefix_args, "mcp-bridge"],
    }
    env: dict[str, str] = {}
    if project_dir is not None:
        env["SCISTUDIO_PROJECT_DIR"] = str(project_dir)
    pythonpath = _mcp_bridge_pythonpath()
    if pythonpath:
        env["PYTHONPATH"] = pythonpath
    if env:
        entry["env"] = env
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
    """Write the ``scistudio`` MCP entry into Claude's config (user|project)."""
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


def _codex_config_path(scope: str = "user", cwd: Path | None = None) -> Path:
    """Return the Codex config path for *scope*.

    Per ADR-040 §3.7, Codex 2026 supports project-scope ``.codex/config.toml``:
    Codex walks from project root to cwd loading every ``.codex/config.toml``
    it finds. So we can write a project-scope MCP entry that takes effect
    only when Codex is launched inside that project.

    Scopes:

    * ``user``:    ``~/.codex/config.toml``
    * ``project``: ``<cwd>/.codex/config.toml`` (cwd defaults to ``Path.cwd()``)
    """
    if scope == "user":
        return Path.home() / ".codex" / "config.toml"
    if scope == "project":
        base = cwd if cwd is not None else Path.cwd()
        return base / ".codex" / "config.toml"
    raise ValueError(f"unsupported scope for codex: {scope!r}")


def _format_toml_string(s: str) -> str:
    """Conservative TOML basic-string escaper.

    We only need to handle path-like strings (Windows backslashes,
    quotes). Anything fancier and the user should be editing the file
    by hand.
    """
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _render_codex_block(project_dir: Path | None) -> str:
    """Render the ``[mcp_servers.scistudio]`` TOML block.

    Format matches what ``codex mcp add ... -- <cmd> [args...]``
    writes — see :func:`scistudio.cli.install._verify_codex_format` in
    the tests for the round-trip check.
    """
    command, prefix_args = _scistudio_command_for_env()
    args_literal = json.dumps([*prefix_args, "mcp-bridge"])
    lines = [
        f"[mcp_servers.{MCP_SERVER_NAME}]",
        f"command = {_format_toml_string(command)}",
        f"args = {args_literal}",
    ]
    # Reuse the shared entry env so the codex TOML matches the claude mcp.json.
    env = _mcp_entry_payload(project_dir).get("env", {})
    if isinstance(env, dict) and env:
        lines.append("")
        lines.append(f"[mcp_servers.{MCP_SERVER_NAME}.env]")
        # SCISTUDIO_PROJECT_DIR first (when present), then PYTHONPATH (#1889).
        for key in ("SCISTUDIO_PROJECT_DIR", "PYTHONPATH"):
            if key in env:
                lines.append(f"{key} = {_format_toml_string(env[key])}")
    return "\n".join(lines) + "\n"


def _read_text_or_empty(path: Path) -> str:
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return ""


def _strip_codex_block(existing: str) -> tuple[str, bool]:
    """Remove ``[mcp_servers.scistudio]`` (and nested table) from *existing*.

    Returns ``(new_text, did_remove)``. Conservative: only strips the
    block headed by exactly ``[mcp_servers.scistudio]`` and its
    nested ``[mcp_servers.scistudio.env]`` table; any other tables
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
    """Write ``[mcp_servers.scistudio]`` block to Codex's config file.

    Per ADR-040 §3.7 (Codex 2026 project-scope support):

    * ``scope="user"`` writes ``~/.codex/config.toml`` with no
      ``SCISTUDIO_PROJECT_DIR`` env pin (the bridge resolves cwd dynamically).
    * ``scope="project"`` writes ``<cwd>/.codex/config.toml`` with the
      ``[mcp_servers.scistudio.env]`` table pinning ``SCISTUDIO_PROJECT_DIR``
      to ``str(cwd)``.

    Reuses ``_render_codex_block(project_dir)`` unchanged — block content
    differs only by whether ``project_dir`` is ``None`` (user) or ``cwd``
    (project).
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
    """Remove the ``[mcp_servers.scistudio]`` block from Codex's config file.

    Symmetric to :func:`_install_codex`: user scope edits
    ``~/.codex/config.toml``; project scope edits ``<cwd>/.codex/config.toml``
    (Codex 2026 project-scope support per ADR-040 §3.7).
    """
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


def _skill_tree_roots(scope: str, cwd: Path) -> tuple[Path, Path]:
    """Return ``(claude_skills_root, codex_skills_root)`` for *scope*.

    These are the ``skills/`` directories one level *above* each installed
    skill, i.e. the directory skill discovery walks. Per ADR-040 §3.9 the
    skill bundle is cross-installed to both Claude Code and Codex skill trees:

    * user scope:    ``~/.claude/skills/``   AND ``~/.agents/skills/``
    * project scope: ``<cwd>/.claude/skills/`` AND ``<cwd>/.agents/skills/``
    """
    if scope == "user":
        base = Path.home()
    elif scope == "project":
        base = cwd
    else:
        raise ValueError(f"unsupported scope for skill: {scope!r}")
    return (
        base / ".claude" / "skills",
        base / ".agents" / "skills",
    )


def _skill_dest(scope: str, cwd: Path) -> tuple[Path, Path]:
    """Return ``(claude_path, codex_path)`` base-skill destinations for *scope*.

    These are the on-disk locations of the base ``scistudio`` skill (the one
    that keeps its own ``scistudio/`` directory). Task-scoped sub-skills are
    installed as *siblings* of this directory — see :func:`_install_skill` and
    the module-level FLAT-layout note. Retained as a thin helper so callers and
    tests that only care about the base skill location keep working.

    * user scope:    ``~/.claude/skills/scistudio/``   AND ``~/.agents/skills/scistudio/``
    * project scope: ``<cwd>/.claude/skills/scistudio/`` AND ``<cwd>/.agents/skills/scistudio/``
    """
    claude_root, codex_root = _skill_tree_roots(scope, cwd)
    return (
        claude_root / MCP_SERVER_NAME,
        codex_root / MCP_SERVER_NAME,
    )


def _discover_skill_layout(src: Path) -> dict[str, Path]:
    """Map skill-name -> source directory for the FLAT install layout.

    The bundled source tree (``_find_skill_source``) is nested:

        <src>/SKILL.md                              # base "scistudio" skill
        <src>/scistudio-write-block/SKILL.md        # task-scoped sub-skill
        <src>/scistudio-debug-run/SKILL.md
        ...

    Claude Code and Codex skill discovery walk exactly one level under
    ``skills/`` (see :mod:`scistudio.agent_provisioning.skills` module
    docstring, confirmed by ADR-040 Phase 4 e2e). Copying the whole tree into
    a single ``skills/scistudio/`` directory buries every sub-skill one level
    too deep, yielding ``Skill(scistudio-write-block) -> Unknown skill``.

    This returns the FLAT mapping the installer must materialise: the base
    skill under its own ``scistudio/`` name, and each task-scoped sub-skill as
    a top-level sibling. Each value is the source directory to copy from.
    """
    layout: dict[str, Path] = {MCP_SERVER_NAME: src}
    for child in sorted(src.iterdir()):
        if child.is_dir() and (child / "SKILL.md").is_file():
            layout[child.name] = child
    return layout


def _find_skill_source() -> Path:
    """Locate the bundled ``scistudio`` skill tree.

    Resolution order per ADR-040 §3.4:

    1. **Packaged location** (preferred): ``importlib.resources.files("scistudio")
       / "_skills" / "scistudio"``. This is where the skill tree lives in both
       editable installs (since the S40b relocation, ``src/scistudio/_skills/``)
       and wheel installs (packaged as ``scistudio.data`` via setuptools).
    2. **Repo-root walk-up fallback** (dev checkouts): walk up from this
       module looking for ``<repo>/skills/scistudio/SKILL.md``. Retained because
       some editable-install configurations keep an authoring tree at the
       legacy repo-root path.

    TODO(#1011): Once the packaged ``src/scistudio/_skills/`` tree is the
    canonical source of truth across all install types (post-Phase 2c), the
    walk-up fallback should be removed. Out of scope for I40d.
    """
    # Path 1: importlib.resources (handles both editable and wheel installs)
    try:
        traversable = importlib_resources.files("scistudio") / "_skills" / MCP_SERVER_NAME
        # For editable installs the traversable is a real filesystem path; for
        # zipped wheels we'd materialise via as_file(). We only need to handle
        # the directory case — bail to fallback if it's not a directory.
        if traversable.is_dir():  # type: ignore[attr-defined]
            # Convert to Path. For editable installs traversable is a PosixPath
            # already; for resources-only zips we'd need as_file context, but
            # SciStudio ships as a normal directory install today.
            skill_path = Path(str(traversable))
            if (skill_path / "SKILL.md").is_file():
                return skill_path
    except (FileNotFoundError, ModuleNotFoundError, AttributeError, TypeError):
        # Fall through to walk-up fallback. The traversable.is_dir() guard
        # above covers the "directory missing" case for editable installs;
        # the except handles the "scistudio package not importable" /
        # "_skills resource not registered" / "non-traversable backend" cases.
        pass

    # Path 2: walk-up fallback for dev checkouts that keep skills/ at repo root
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "skills" / MCP_SERVER_NAME
        if (candidate / "SKILL.md").is_file():
            return candidate
        if (parent / "pyproject.toml").is_file():
            # Reached repo root; if skill isn't here, abort cleanly.
            break
    raise FileNotFoundError(
        "Could not locate the bundled SciStudio skill (expected "
        "src/scistudio/_skills/scistudio/SKILL.md or <repo>/skills/scistudio/SKILL.md). "
        "Ensure you are running from a SciStudio source checkout or installed wheel."
    )


def _copy_base_skill(src: Path, dest: Path) -> None:
    """Copy only the base-skill files (``SKILL.md`` + any top-level assets).

    Sub-skill directories under *src* are NOT copied here — they are installed
    as flat siblings of *dest* by :func:`_install_skill`. We copy the base
    skill's own files (top-level files and any non-skill asset subdirectories)
    but skip child directories that are themselves discoverable skills, so the
    base ``scistudio/`` directory stays a single discoverable skill rather than
    re-nesting the sub-skills.
    """
    dest.mkdir(parents=True, exist_ok=True)
    for child in sorted(src.iterdir()):
        if child.is_dir():
            # A child dir that is itself a skill is installed flat elsewhere;
            # skip it so it does not get buried under the base skill.
            if (child / "SKILL.md").is_file():
                continue
            shutil.copytree(child, dest / child.name)
        else:
            shutil.copy2(child, dest / child.name)


def _install_skill(scope: str, cwd: Path) -> list[InstallResult]:
    """Cross-install the SciStudio skill bundle FLAT to both provider trees.

    Per ADR-040 §3.9, the skill is cross-installed to both providers:

    * user scope:    ``~/.claude/skills/`` AND ``~/.agents/skills/``
    * project scope: ``<cwd>/.claude/skills/`` AND ``<cwd>/.agents/skills/``

    The layout is FLAT, matching
    :func:`scistudio.agent_provisioning.skills.write_skills`: the base
    ``scistudio`` skill lands at ``<tree>/scistudio/SKILL.md`` and each
    task-scoped sub-skill (``scistudio-build-workflow``, ``scistudio-write-block``,
    ``scistudio-debug-run``, ``scistudio-inspect-data``, ``scistudio-project-qa``)
    lands as a *sibling* at ``<tree>/<name>/SKILL.md``. This is required because
    Claude Code and Codex skill discovery walk exactly one level under
    ``skills/`` (#1521) — the previous nested ``skills/scistudio/<name>/``
    layout produced ``Skill(<name>) -> Unknown skill``.

    Source is resolved via :func:`_find_skill_source` (preferring the packaged
    ``src/scistudio/_skills/scistudio/`` tree, falling back to a repo-root
    walk-up for dev checkouts).

    Returns one ``InstallResult`` per destination *tree* (two per call: Claude +
    Codex); the ``path`` is the base ``scistudio`` skill directory. Always
    copies (never symlinks) for Windows compatibility — symlinks require
    admin / developer mode on Windows.
    """
    src = _find_skill_source()
    layout = _discover_skill_layout(src)
    claude_root, codex_root = _skill_tree_roots(scope, cwd)
    results: list[InstallResult] = []
    for root in (claude_root, codex_root):
        base_dest = root / MCP_SERVER_NAME
        action = "updated" if base_dest.is_dir() else "installed"
        for name, skill_src in layout.items():
            dest = root / name
            # Wipe stale files so removed files in src don't linger.
            if dest.is_dir():
                shutil.rmtree(dest)
            if name == MCP_SERVER_NAME:
                _copy_base_skill(skill_src, dest)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(skill_src, dest)
        results.append(
            InstallResult(
                target="skill",
                scope=scope,
                path=base_dest,
                action=action,
                detail=f"installed {len(layout)} flat skill(s) from {src} -> {root}",
            )
        )
    return results


def _remove_skill(scope: str, cwd: Path) -> list[InstallResult]:
    """Symmetric removal across both Claude and Codex skill trees.

    Per ADR-040 §3.9, mirrors :func:`_install_skill`: removes the FLAT layout
    — the base ``scistudio/`` directory plus every task-scoped sibling
    sub-skill (``scistudio-*``) — under both ``.claude/skills/`` and
    ``.agents/skills/`` at the requested scope. Returns one ``InstallResult``
    per destination *tree* (``removed`` if anything was deleted, ``noop``
    otherwise); the ``path`` is the base ``scistudio`` skill directory.

    Discovery of which sibling skills to remove is best-effort: it uses the
    bundled source layout when locatable, and additionally sweeps any
    ``scistudio-*`` sibling directories present in the tree so an install whose
    sub-skill set has since changed still cleans up fully.
    """
    claude_root, codex_root = _skill_tree_roots(scope, cwd)
    # Determine the set of skill names to remove. Prefer the bundled layout;
    # fall back to the canonical base name if the source can't be located.
    names: set[str] = {MCP_SERVER_NAME}
    try:
        src = _find_skill_source()
        names |= set(_discover_skill_layout(src).keys())
    except FileNotFoundError:
        pass

    results: list[InstallResult] = []
    for root in (claude_root, codex_root):
        base_dest = root / MCP_SERVER_NAME
        targets = set(names)
        # Sweep any stray scistudio-* sibling skills regardless of current source.
        if root.is_dir():
            for child in root.iterdir():
                if child.is_dir() and (child.name == MCP_SERVER_NAME or child.name.startswith(f"{MCP_SERVER_NAME}-")):
                    targets.add(child.name)

        removed_any = False
        for name in targets:
            dest = root / name
            if dest.is_dir():
                shutil.rmtree(dest)
                removed_any = True

        if removed_any:
            results.append(
                InstallResult(
                    target="skill", scope=scope, path=base_dest, action="removed", detail="flat skills removed"
                )
            )
        else:
            results.append(
                InstallResult(target="skill", scope=scope, path=base_dest, action="noop", detail="not installed")
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
    """Dispatch one ``scistudio install`` invocation.

    Encapsulates the install/remove logic in a callable form so tests
    (and any future programmatic caller) don't need to drive Typer.

    Per ADR-040 §3.7 + §3.9, the ``--skill`` flag cross-installs to **both**
    Claude (``~/.claude/skills/``) and Codex (``~/.agents/skills/``) trees,
    and the ``--target codex --scope project`` combination now writes
    ``<cwd>/.codex/config.toml`` (Codex 2026 project-scope support).

    Parameters
    ----------
    target
        ``"claude"``, ``"codex"``, or ``None`` when only ``--skill`` /
        ``--all`` was passed.
    scope
        ``"user"`` or ``"project"``.
    skill
        Cross-install the SciStudio skill to both providers' skill trees.
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
            # Per ADR-040 §3.7: Codex 2026 supports project-scope
            # ``.codex/config.toml``, so we no longer force user-scope here.
            # ``_install_codex`` / ``_remove_codex`` handle both scopes
            # natively. The legacy "wrote to user scope" caveat is removed.
            results.append(_remove_codex(scope, cwd) if remove else _install_codex(scope, cwd))
    if do_skill:
        # ``_install_skill`` / ``_remove_skill`` return ``list[InstallResult]``
        # — two entries per call (Claude + Codex skill trees) per ADR-040 §3.9.
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
        help=(
            "'user' (~/.claude.json or ~/.codex/config.toml) or "
            "'project' (<cwd>/.mcp.json or <cwd>/.codex/config.toml — "
            "the latter requires Codex 2026)."
        ),
    ),
    skill: bool = typer.Option(
        False,
        "--skill",
        help="Cross-install the SciStudio skill into both Claude's and Codex's skills directories.",
    ),
    do_all: bool = typer.Option(
        False,
        "--all",
        help="Convenience: install for claude + codex + skill at user scope.",
    ),
    remove: bool = typer.Option(
        False,
        "--remove",
        help="Reverse the install (remove SciStudio entry / delete skill dir).",
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
        typer.echo(f"scistudio install: {exc}", err=True)
        raise typer.Exit(code=2) from None
    except Exception as exc:  # pragma: no cover - defensive
        typer.echo(f"scistudio install: unexpected error: {exc}", err=True)
        raise typer.Exit(code=1) from None
    _emit_results(results)


def register(app: typer.Typer) -> None:
    """Register the ``install`` subcommand on the given Typer app."""
    app.command(
        "install",
        help=("Wire SciStudio's MCP server (and optional skill) into an external CLI such as `claude` or `codex`."),
    )(_typer_command)


if __name__ == "__main__":  # pragma: no cover
    app = typer.Typer()
    register(app)
    app()
