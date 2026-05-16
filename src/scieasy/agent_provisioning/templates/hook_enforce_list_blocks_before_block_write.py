#!/usr/bin/env python
"""hook_enforce_list_blocks_before_block_write.py — PreToolUse (ADR-040 §3.6).

Enforces the block-reuse half of #875: BEFORE writing a custom block,
the agent MUST have called ``mcp__scieasy__list_blocks`` in the current
session so they can confirm no existing block matches the I/O contract.

Hook contract:
  - Matcher: ``"Edit|Write|Bash|mcp__scieasy__scaffold_block"``.
  - Exit 2 = block; exit 0 = allow.

Known hook-layer blind spot (per ADR §3.6 + §7.3):
  Exotic Bash writes (``python -c '...'``, ``mv``, here-doc piping
  through ``sh -c``) bypass the regex. This is defense-in-depth, not
  absolute prevention.

# TODO(#1015): Layer 7 filesystem ACL on <project>/blocks/ is the
#   bulletproof escalation path — out of scope per ADR-040 §3.10
#   (cross-cutting policy decision affecting human-authored blocks too;
#   deferred to a future ADR if drift surfaces in production).
#   Followup: https://github.com/zjzcpj/SciEasy/issues/1015.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

_BLOCK_FILE_RE = re.compile(r"(?:^|/)blocks/[^/]+\.py$", re.IGNORECASE)
_BASH_WRITE_RE = re.compile(
    # Captures: > blocks/x.py | >> blocks/x.py | tee blocks/x.py | cp ... blocks/x.py
    r"(>>?|tee|cp\s+\S+)\s+\S*blocks/[^\s]+\.py",
    re.IGNORECASE,
)
_MESSAGE = (
    "Authoring a custom block requires calling mcp__scieasy__list_blocks "
    "first to confirm no existing block matches your I/O contract. Call "
    "list_blocks now, then retry."
)


def _read_payload() -> dict:
    try:
        raw = sys.stdin.read()
    except OSError:
        return {}
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _is_block_write(payload: dict) -> bool:
    """Decide whether this tool call is about to author a block file."""
    tool_name = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return False

    # scaffold_block: always counts as block authoring.
    if tool_name == "mcp__scieasy__scaffold_block":
        return True

    # Edit / Write: file_path matches blocks/*.py
    file_path = str(tool_input.get("file_path") or "")
    file_path_norm = file_path.replace("\\", "/")
    if _BLOCK_FILE_RE.search(file_path_norm):
        return True

    # Bash: command contains a redirect/tee/cp writing into blocks/*.py
    command = str(tool_input.get("command") or "")
    command_norm = command.replace("\\", "/")
    if _BASH_WRITE_RE.search(command_norm):
        return True

    return False


def _marker_path(payload: dict) -> Path | None:
    """Compute the session marker path or return None if unable."""
    session_id = str(payload.get("session_id") or "")
    if not session_id:
        return None
    # Sanitize session_id — disallow filesystem-meaningful chars defensively.
    if re.search(r"[\\/\x00]", session_id):
        return None

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if not project_dir:
        return None
    return Path(project_dir) / ".scieasy" / ".session-state" / session_id / "list_blocks_called"


def main() -> int:
    payload = _read_payload()
    if not _is_block_write(payload):
        return 0

    marker = _marker_path(payload)
    if marker is not None and marker.is_file():
        return 0

    print(_MESSAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
