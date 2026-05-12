"""Generate Claude Code config files at session start.

Two static config files are written to ``{project_dir}/.scieasy/`` whenever
a chat session is spawned:

* ``mcp.json`` — passed to Claude Code via ``--mcp-config``. Configures
  the ``scieasy`` MCP server bridge (see ADR-033 §3 D2.3).
* ``claude-hooks.json`` — registers the ``PreToolUse`` hook that proxies
  per-tool approval requests through ``scieasy hook-bridge`` (see
  ADR-033 §3 D4.3). In bypass mode the hook is omitted entirely.

Both writers are deterministic and idempotent: same inputs produce
byte-identical files (sorted keys, two-space indent, LF newlines). This
keeps the files diff-clean across re-spawns and matches the spec's
acceptance criterion in §5 T-ECA-108.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from scieasy.ai.agent.provider import PermissionMode

logger = logging.getLogger(__name__)

_SCIEASY_DIR_NAME = ".scieasy"
_MCP_FILE_NAME = "mcp.json"
_HOOKS_FILE_NAME = "claude-hooks.json"


def _scieasy_dir(project_dir: Path) -> Path:
    """Return ``{project_dir}/.scieasy``, creating it if missing."""
    target = project_dir / _SCIEASY_DIR_NAME
    target.mkdir(parents=True, exist_ok=True)
    return target


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write ``payload`` to ``path`` with stable formatting and LF newlines."""
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    # ``newline=""`` ensures the trailing ``\n`` is written verbatim instead of
    # being translated to ``\r\n`` on Windows, guaranteeing byte-stability.
    path.write_text(text, encoding="utf-8", newline="")


def write_mcp_config(project_dir: Path, chat_id: str) -> Path:
    """Emit ``{project_dir}/.scieasy/mcp.json`` for the given chat session.

    The configuration points Claude Code at the ``scieasy`` CLI's
    ``mcp-bridge`` subcommand, which proxies JSON-RPC frames to the
    running FastAPI process's in-process MCP server (ADR-033 §3 D2.3).

    Parameters
    ----------
    project_dir
        Absolute path to the SciEasy project directory. ``.scieasy/`` is
        auto-created beneath it if missing.
    chat_id
        Stable chat identifier; baked into the bridge subprocess's env
        as ``SCIEASY_CHAT_ID`` so the bridge can correlate requests.

    Returns
    -------
    pathlib.Path
        Absolute path of the written ``mcp.json``.
    """
    scieasy_dir = _scieasy_dir(project_dir)
    abs_project = str(project_dir.resolve()) if project_dir.exists() else str(project_dir)
    payload: dict[str, Any] = {
        "mcpServers": {
            "scieasy": {
                "args": ["mcp-bridge"],
                "command": "scieasy",
                "env": {
                    "SCIEASY_CHAT_ID": chat_id,
                    "SCIEASY_PROJECT_DIR": abs_project,
                },
            }
        }
    }
    target = scieasy_dir / _MCP_FILE_NAME
    _write_json(target, payload)
    logger.info("write_mcp_config: wrote %s for chat_id=%s", target, chat_id)
    return target


def write_hook_config(project_dir: Path, permission_mode: PermissionMode) -> Path:
    """Emit ``{project_dir}/.scieasy/claude-hooks.json``.

    In :attr:`PermissionMode.STRICT` mode the ``PreToolUse`` hook is
    registered to invoke ``scieasy hook-bridge``; in
    :attr:`PermissionMode.BYPASS` mode the file is written with an empty
    ``hooks`` dict so the agent operates without per-call approval (the
    user has explicitly opted into bypass; ADR-033 §3 D4.2).

    Parameters
    ----------
    project_dir
        Absolute path to the SciEasy project directory.
    permission_mode
        Selects strict vs. bypass enforcement.

    Returns
    -------
    pathlib.Path
        Absolute path of the written ``claude-hooks.json``.
    """
    scieasy_dir = _scieasy_dir(project_dir)
    payload: dict[str, Any]
    if permission_mode is PermissionMode.STRICT:
        payload = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "",
                        "hooks": [
                            {"command": "scieasy hook-bridge", "type": "command"},
                        ],
                    }
                ]
            }
        }
    elif permission_mode is PermissionMode.BYPASS:
        payload = {"hooks": {}}
    else:  # pragma: no cover - defensive; enum is closed.
        raise ValueError(f"Unknown PermissionMode: {permission_mode!r}")
    target = scieasy_dir / _HOOKS_FILE_NAME
    _write_json(target, payload)
    logger.info(
        "write_hook_config: wrote %s for mode=%s",
        target,
        permission_mode.value,
    )
    return target
