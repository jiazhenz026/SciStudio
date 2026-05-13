"""Phase-1 demo runner for the embedded coding agent runtime.

Runs a chat round-trip against the ``stub_claude.py`` test fixture (or
the real ``claude`` CLI when ``binary_override`` is ``None``) and prints
every canonical event to stdout in the form ``[<kind>] <fields>``.

This module is the runtime acceptance demo for T-ECA-109. It exercises
the full Phase 1 happy path:

1. Write static MCP + hook config files for ``project_dir`` via
   :mod:`scieasy.ai.agent.config_files`.
2. Spawn a session through the :class:`AgentSessionManager` using a
   placeholder system prompt (the real composition lives in T-ECA-204).
3. Send a synthetic "list files" user message.
4. Iterate ``session.stream_events()`` and print each event until the
   stream closes.

The demo is invocable as ``python -m scieasy.ai.agent.demo`` (with the
stub binary auto-discovered relative to this file's path) and is
shaped to keep its end-to-end runtime under five seconds against the
stub.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import logging
import sys
import tempfile
import uuid
from pathlib import Path

from scieasy.ai.agent.claude_code import ClaudeCodeProvider
from scieasy.ai.agent.config_files import write_hook_config, write_mcp_config
from scieasy.ai.agent.provider import AgentEvent, PermissionMode
from scieasy.ai.agent.session import AgentSessionManager

logger = logging.getLogger(__name__)


_PLACEHOLDER_PROMPT = (
    "You are the SciEasy embedded coding agent (Phase 1 placeholder).\n"
    "The real three-tier system prompt is composed in T-ECA-204."
)


def _stub_path_default() -> Path:
    """Best-effort path to the bundled ``tests/fixtures/stub_claude.py``."""
    # Walk up from this module to the repo root, then into tests/fixtures.
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "tests" / "fixtures" / "stub_claude.py"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("stub_claude.py not found; pass --binary-override explicitly")


def _format_event(event: AgentEvent) -> str:
    """Render one event as ``[<kind>] field1=v1 field2=v2`` for stdout."""
    if dataclasses.is_dataclass(event):
        fields = {f.name: getattr(event, f.name) for f in dataclasses.fields(event)}
    else:
        fields = {"kind": event.kind, "raw": event.raw}
    parts = [f"{k}={v!r}" for k, v in fields.items() if k != "kind"]
    return f"[{event.kind}] " + " ".join(parts)


async def main(
    project_dir: Path | None = None,
    binary_override: Path | None = None,
    user_message: str = "list files in this project",
) -> list[AgentEvent]:
    """Run the Phase-1 demo end-to-end and return the captured event sequence.

    Parameters
    ----------
    project_dir
        Project workspace path. Defaults to a fresh temp dir.
    binary_override
        Stub binary path. Defaults to the bundled
        ``tests/fixtures/stub_claude.py``.
    user_message
        Synthetic user message sent on the first turn.

    Returns
    -------
    list[AgentEvent]
        Every event seen during the session, in order.
    """
    if project_dir is None:
        project_dir = Path(tempfile.mkdtemp(prefix="scieasy-eca-demo-"))
    if binary_override is None:
        binary_override = _stub_path_default()

    chat_id = f"demo-{uuid.uuid4()}"
    permission_mode = PermissionMode.STRICT

    # Emit the static config files (T-ECA-108).
    write_mcp_config(project_dir, chat_id=chat_id)
    write_hook_config(project_dir, permission_mode=permission_mode)

    manager = AgentSessionManager()
    provider = ClaudeCodeProvider(binary_override=binary_override)
    session = await manager.start_session(
        project_dir=project_dir,
        chat_id=chat_id,
        provider=provider,
        system_prompt=_PLACEHOLDER_PROMPT,
        mcp_config={"mcpServers": {}},
        permission_mode=permission_mode,
    )

    captured: list[AgentEvent] = []
    try:
        await session.send_user_message(user_message)
        async for event in session.stream_events():
            print(_format_event(event), flush=True)
            captured.append(event)
    finally:
        await manager.close_session(project_dir, chat_id)

    return captured


def _parse_argv(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Embedded coding agent Phase 1 demo")
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=None,
        help="Project workspace dir (default: fresh temp dir)",
    )
    parser.add_argument(
        "--binary-override",
        type=Path,
        default=None,
        help="Stub binary path (default: tests/fixtures/stub_claude.py)",
    )
    parser.add_argument(
        "--message",
        default="list files in this project",
        help="User message to send on the first turn",
    )
    return parser.parse_args(argv)


def cli(argv: list[str] | None = None) -> int:
    """Console-script entry point."""
    args = _parse_argv(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
    asyncio.run(
        main(
            project_dir=args.project_dir,
            binary_override=args.binary_override,
            user_message=args.message,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(cli())


__all__ = ["cli", "main"]
