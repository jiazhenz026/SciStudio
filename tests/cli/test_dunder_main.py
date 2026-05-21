"""Regression: ``python -m scistudio`` must dispatch to the Typer CLI.

Hotfix #1014 — every project's ``.scistudio/mcp.json`` invokes the bridge
via ``[sys.executable, "-m", "scistudio", "mcp-bridge"]`` (per
``scistudio.cli.install._scistudio_command_for_env``). That invocation
needs ``scistudio/__main__.py`` to exist, otherwise Python errors out
with ``No module named scistudio.__main__`` and the MCP client reports
"scistudio MCP server failed" with no useful diagnostic — the bridge
subprocess dies before writing any frames so nothing surfaces in logs.

This test exercises the bare ``python -m scistudio --help`` path so any
regression that breaks the dunder-main dispatch is caught at CI time
instead of when a user's AI Block silently loses its MCP tools.
"""

from __future__ import annotations

import subprocess
import sys


def test_python_dash_m_scistudio_dispatches_to_cli() -> None:
    """``python -m scistudio --help`` returns exit 0 and lists subcommands."""
    proc = subprocess.run(
        [sys.executable, "-m", "scistudio", "--help"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0, f"python -m scistudio --help failed (exit {proc.returncode}). stderr:\n{proc.stderr}"
    # Spot-check that the expected subcommands appear so a future
    # regression that ships a __main__.py pointing at an unrelated
    # entry-point would fail loudly.
    for cmd in ("mcp-bridge", "install", "gui"):
        assert cmd in proc.stdout, f"expected `{cmd}` subcommand in --help output; got:\n{proc.stdout}"
