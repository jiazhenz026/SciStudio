"""Allow ``python -m scieasy`` to invoke the Typer CLI.

Hotfix #1014: ``scieasy.cli.install._scieasy_command_for_env`` writes
``[sys.executable, "-m", "scieasy", ...]`` into every project's
``.scieasy/mcp.json`` so Claude / Codex / etc. invoke the bridge through
the same interpreter that emitted the manifest (avoids the PATH-shadowed
``scieasy.EXE`` foot-gun that 2026-05-14 hotfix originally addressed).

But ``python -m <pkg>`` needs a ``__main__.py`` next to ``__init__.py``;
without one Python raises ``No module named scieasy.__main__`` and exits
1. The MCP client then reports "scieasy MCP server failed: connection
closed" with no useful diagnostic. The 2026-05-14 hotfix shipped without
this file, so every newly-spawned AI Block / freshly-installed MCP
client has been hitting the broken invocation since.

This module is intentionally tiny — it only re-exports the Typer ``app``
so ``python -m scieasy`` resolves to the same dispatch table as the
console-script ``scieasy.EXE`` shim.
"""

from scieasy.cli.main import app

if __name__ == "__main__":
    app()
