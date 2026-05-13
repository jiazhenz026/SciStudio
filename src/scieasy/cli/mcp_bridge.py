"""``scieasy mcp-bridge`` — stdio proxy between CC and the MCP socket.

T-ECA-201 (scaffold). Per ADR-033 §3 D2 / spec OQ2, Claude Code is
configured (via the generated ``mcp.json``) to spawn this subprocess
when the user opens a chat session. The bridge:

1. Accepts a ``--socket <path>`` argument (Unix domain socket on POSIX,
   named pipe on Windows) pointing at the in-process
   :class:`scieasy.ai.agent.mcp.server.MCPServer` instance owned by
   the FastAPI process.
2. Opens that transport.
3. Pipes JSON-RPC frames from its own stdin → socket and from socket →
   its own stdout.

The actual proxy loop is implemented in **T-ECA-205**. This scaffold
ships only the Typer command shell with a clear placeholder so:

* ``scieasy mcp-bridge --help`` exits 0 with usage text (acceptance
  criterion for T-ECA-201).
* ``scieasy mcp-bridge --socket whatever`` exits 2 with a message
  pointing at T-ECA-205, so anyone trying to use the bridge before
  Phase 2 implementation lands gets an explicit signal rather than a
  silent hang or a fail-open zero exit (the latter would mislead CC,
  per the same reasoning as :mod:`scieasy.cli.hook_bridge`).

The ``register`` helper mirrors the pattern established by
``hook_bridge.register(app)``: ``main.py`` calls it at import time so
the existing ``scieasy`` console script gains the subcommand without a
new ``[project.scripts]`` entry.
"""

from __future__ import annotations

import sys

import typer


def run(socket: str | None) -> int:
    """Execute the bridge once; return the process exit code.

    Scaffold behaviour: print a one-line message identifying the
    follow-up ticket and return ``2``. The non-zero exit prevents CC
    from interpreting the absence of a real bridge as a fail-open
    silent success (same reasoning as the hook bridge — only ``0`` and
    ``2`` are well-defined in CC's contract).

    Parameters
    ----------
    socket
        Filesystem path to the MCP socket / named pipe, or ``None`` if
        the caller omitted the argument. Stored for forward
        compatibility; ignored by the scaffold.

    Returns
    -------
    int
        ``2`` until T-ECA-205 lands; never ``0`` and never ``1``.
    """
    target = socket if socket is not None else "<unset>"
    print(
        f"scieasy mcp-bridge: not yet implemented (socket={target}). T-ECA-205 will implement this.",
        file=sys.stderr,
    )
    return 2


def _typer_command(
    socket: str = typer.Option(
        None,
        "--socket",
        help="Path to the MCP server's Unix socket (POSIX) or named pipe (Windows).",
    ),
) -> None:
    """Typer entry-point wrapper around :func:`run`.

    Translates the Typer-parsed arguments into a :class:`typer.Exit`
    with the bridge's return code so ``scieasy mcp-bridge`` exits with
    the exact integer returned by :func:`run`.
    """
    raise typer.Exit(code=run(socket))


def register(app: typer.Typer) -> None:
    """Register the ``mcp-bridge`` subcommand on the given Typer app.

    Called from :mod:`scieasy.cli.main` at module import time so the
    existing ``scieasy`` console script gains the subcommand without a
    new ``[project.scripts]`` entry. Mirrors the pattern used by
    :func:`scieasy.cli.hook_bridge.register`.
    """
    app.command(
        "mcp-bridge",
        help="Proxy MCP JSON-RPC frames between CC stdio and the SciEasy MCP socket.",
    )(_typer_command)


if __name__ == "__main__":
    sys.exit(run(None))
