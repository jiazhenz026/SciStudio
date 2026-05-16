#!/usr/bin/env python
"""hook_mark_list_blocks_called.py — PostToolUse / list_blocks (ADR-040 §3.6).

Purpose:
  After ``mcp__scieasy__list_blocks`` returns, write a session-keyed
  marker file the companion PreToolUse hook
  (``hook_enforce_list_blocks_before_block_write.py``) reads to gate
  block-authoring tool calls.

Hook contract:
  - Stdin: JSON payload. Must include ``session_id``.
  - Matcher: ``"mcp__scieasy__list_blocks"``.
  - Always exit 0 (PostToolUse cannot block).

Behavior to implement in I40c:
  1. Read stdin JSON; extract ``session_id``.
  2. ``$CLAUDE_PROJECT_DIR`` is set by Claude Code; use it to compute
     ``<project>/.scieasy/.session-state/<session_id>/``.
  3. ``mkdir -p`` the directory (parents=True, exist_ok=True).
  4. ``Path(dir / "list_blocks_called").touch()``.
  5. sys.exit(0).

Marker semantics:
  - Session-keyed: a fresh chat tab gets a fresh session_id, so the
    confirmation does not persist across sessions (intentional per
    ADR §3.6).
  - Directory cleanup: stale ``<session_id>`` directories older than
    7 days are best-effort pruned on ``open_project`` — a Phase 3 task,
    not S40c / I40c responsibility.
  - Gitignored: ``.scieasy/`` is gitignored by ADR-039's default
    .gitignore, so this marker tree never lands in git.

S40c skeleton: exits 0 with no side effects.

TODO(#1013): I40c Phase 2a — implement marker write per ADR §3.6.
  Out of scope per ADR-040 §3.6 (S40c skeleton).
  Followup: https://github.com/zjzcpj/SciEasy/issues/1013.
"""

import sys

# TODO(#1013): read stdin, mkdir + touch marker, exit 0.
sys.exit(0)
