"""Allow ``python -m scistudio`` to invoke the Typer CLI.

PEP 338 lets any package be runnable via ``python -m <pkg>`` when a
``__main__.py`` exists alongside ``__init__.py``. The mechanism predates
console-script entry points (2005) and is the canonical "this package
is runnable" marker — it works for every supported install layout
(venv, conda env, ``pip install --user``, frozen interpreters,
embedded Python) without relying on PATH lookup or guessing where pip
dropped the entry-point shim.

Hotfix #1014: ``scistudio.cli.install._scistudio_command_for_env`` writes
``[sys.executable, "-m", "scistudio", ...]`` into every project's
``.scistudio/mcp.json`` so Claude / Codex / etc. invoke the bridge through
the same interpreter that emitted the manifest. The 2026-05-14 hotfix
shipped that change without the accompanying ``__main__.py``, so every
newly-spawned AI Block / freshly-installed MCP client has been failing
with ``No module named scistudio.__main__`` since. The MCP client reports
"scistudio MCP server failed: connection closed" with no useful
diagnostic because the bridge subprocess died before writing any
frames.

This module is intentionally tiny — it only re-exports the Typer
``app`` so ``python -m scistudio`` resolves to the same dispatch table as
the console-script ``scistudio.EXE`` shim.
"""

from scistudio.cli.main import app

if __name__ == "__main__":
    app()
