"""Regression tests for Codex MCP ``-c`` overrides (#1889).

Codex launches the stdio MCP bridge in a *stripped* environment that does not
inherit the backend's ``PYTHONPATH`` (unlike Claude Code, which inherits the
full parent env). In dev + packaged-desktop installs ``scistudio`` is importable
only via ``PYTHONPATH``, so without injecting it the bridge dies with
``No module named scistudio`` and Codex reports ``MCP server failed``.

These tests pin that the embedded-GUI Codex spawn path injects ``PYTHONPATH``
into the MCP server ``env`` and that the rendered ``-c`` value is valid TOML
(Codex parses ``-c key=value`` as TOML).
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from scistudio.ai.agent.terminal import _codex_mcp_config_overrides


def _scistudio_src_root() -> str:
    import scistudio

    return str(Path(scistudio.__file__).resolve().parents[1])


def _env_override_line(project_dir: Path) -> str:
    overrides = _codex_mcp_config_overrides(project_dir)
    # Overrides are flat ``["-c", "<assignment>", "-c", "<assignment>", ...]``.
    for token in overrides:
        if token.startswith("mcp_servers.scistudio.env="):
            return token
    raise AssertionError(f"no env override found in {overrides!r}")


def test_codex_overrides_inject_pythonpath() -> None:
    line = _env_override_line(Path("/tmp/proj/x"))
    assert "PYTHONPATH=" in line
    assert _scistudio_src_root() in line


def test_codex_env_override_is_valid_toml_inline_table() -> None:
    # Codex parses ``-c key=value`` as TOML; the env inline table must round-trip.
    project_dir = Path("/tmp/some proj/oxidized-lipid-imaging")
    line = _env_override_line(project_dir)
    parsed = tomllib.loads(line)
    env = parsed["mcp_servers"]["scistudio"]["env"]
    assert env["SCISTUDIO_PROJECT_DIR"] == str(project_dir)
    assert _scistudio_src_root() in env["PYTHONPATH"].split(os.pathsep)
