"""Write project-scope Codex MCP config (ADR-040 §3.7).

Writes ``<project>/.codex/config.toml`` with a single
``[mcp_servers.scieasy]`` block + nested ``[mcp_servers.scieasy.env]``
table pinning ``SCIEASY_PROJECT_DIR`` to the absolute project path.

Codex 2026 walks from project root to cwd loading every
``.codex/config.toml`` — so the project-scope file takes precedence over
``~/.codex/config.toml`` for sessions opened inside this project.

Implementation reuses ``install._render_codex_block(project_dir)`` from
``src/scieasy/cli/install.py`` so the §3.7 auto-provisioned TOML is
byte-identical to what ``scieasy install --target codex --scope project``
emits.
"""

from __future__ import annotations

from pathlib import Path

_TARGET_REL = ".codex/config.toml"


def write_codex_config(
    project_dir: Path,
    *,
    force: bool = False,
) -> list[str]:
    """Write ``<project>/.codex/config.toml``.

    Inputs:
      project_dir : Path to project root (absolute path is encoded into
                    the TOML as the ``SCIEASY_PROJECT_DIR`` env var value).
      force       : True to overwrite; False to preserve.

    Returns:
      List of project-relative paths actually written.
    """
    dest = project_dir / _TARGET_REL
    if dest.exists() and not force:
        return []

    # Local import: avoid pulling scieasy.cli.install at module load time;
    # install.py imports typer + heavier deps.
    from scieasy.cli.install import _render_codex_block

    rendered = _render_codex_block(project_dir.resolve())

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(rendered, encoding="utf-8")
    return [_TARGET_REL]
