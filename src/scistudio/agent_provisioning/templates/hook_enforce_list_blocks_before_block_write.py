#!/usr/bin/env python
"""hook_enforce_list_blocks_before_block_write.py — PreToolUse (ADR-040 §3.6).

Enforces the block-reuse half of #875: BEFORE writing a custom block,
the agent MUST have called ``mcp__scistudio__list_blocks`` in the current
session so they can confirm no existing block matches the I/O contract.

Hook contract:
  - Matcher: ``"Edit|Write|Bash|mcp__scistudio__scaffold_block"``.
  - Exit 2 = block; exit 0 = allow.

Known hook-layer blind spot (per ADR §3.6 + §7.3):
  Exotic Bash writes (``python -c '...'``, ``mv``, here-doc piping
  through ``sh -c``) bypass the regex. This is defense-in-depth, not
  absolute prevention.

# TODO(#1015): Layer 7 filesystem ACL on <project>/blocks/ is the
#   bulletproof escalation path — out of scope per ADR-040 §3.10
#   (cross-cutting policy decision affecting human-authored blocks too;
#   deferred to a future ADR if drift surfaces in production).
#   Followup: https://github.com/zjzcpj/SciStudio/issues/1015.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

_BLOCK_FILE_RE = re.compile(r"(?:^|/)blocks/[^/]+\.py$", re.IGNORECASE)
_BASH_WRITE_RE = re.compile(
    # Captures: > blocks/x.py | >>blocks/x.py | tee blocks/x.py | cp ... blocks/x.py
    # Codex P1 (PR #1047): allow ZERO whitespace between the redirect
    # operator and the path so ``echo x >blocks/new.py`` is also blocked
    # (valid shell syntax). ``tee`` / ``cp`` still require whitespace
    # because they are commands, not punctuation.
    r"(?:>>?\s*|\b(?:tee|cp\s+\S+)\s+)\S*blocks/\S+\.py",
    re.IGNORECASE,
)
_MESSAGE = (
    "Authoring a custom block requires calling mcp__scistudio__list_blocks "
    "first to confirm no existing block matches your I/O contract. Call "
    "list_blocks now, then retry."
)


def _read_payload() -> dict:
    """Read the hook payload, degrading to ``{}`` instead of ever crashing.

    #1994: this used to guard only ``OSError``. When a CLI starts a hook with
    no usable stdin, Python sets ``sys.stdin`` to ``None``, so
    ``sys.stdin.read()`` raised ``AttributeError`` — which nothing caught. The
    hook died with **exit 1** before evaluating anything, which the CLI reports
    as a failed hook and then proceeds, so the guard silently did not guard.
    It reproduced identically for all seven hooks, because they all share this
    function.

    An unreadable payload is indistinguishable from an empty one: in both cases
    the hook cannot tell what the agent is about to do. It returns ``{}`` and
    the caller allows the call, which is the behaviour an empty payload already
    had — and blocking every tool call on a stdin quirk would be far worse than
    the exposure it removes. ``BaseException`` is deliberately not caught; only
    the ways reading a missing or closed stream can fail.
    """
    stream = sys.stdin
    if stream is None:
        return {}
    try:
        raw = stream.read()
    except (OSError, ValueError, AttributeError):
        # ValueError: reading a closed file. AttributeError: a replaced stdin
        # that is not a stream at all.
        return {}
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _is_block_write(payload: dict) -> bool:
    """Decide whether this tool call is about to author a block file."""
    tool_name = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return False

    # scaffold_block: always counts as block authoring.
    if tool_name == "mcp__scistudio__scaffold_block":
        return True

    # Edit / Write: file_path matches blocks/*.py
    file_path = str(tool_input.get("file_path") or "")
    file_path_norm = file_path.replace("\\", "/")
    if _BLOCK_FILE_RE.search(file_path_norm):
        return True

    # Bash: command contains a redirect/tee/cp writing into blocks/*.py
    command = str(tool_input.get("command") or "")
    command_norm = command.replace("\\", "/")
    return bool(_BASH_WRITE_RE.search(command_norm))


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
    return Path(project_dir) / ".scistudio" / ".session-state" / session_id / "list_blocks_called"


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
