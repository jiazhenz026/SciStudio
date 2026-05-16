#!/usr/bin/env python
"""hook_enforce_list_blocks_before_block_write.py — PreToolUse (ADR-040 §3.6).

Purpose:
  Enforce the block-reuse half of #875: BEFORE writing a custom block,
  the agent MUST have called ``mcp__scieasy__list_blocks`` in the current
  session so they can confirm no existing block matches the I/O contract.

Hook contract:
  - Stdin: JSON payload. Required fields: ``tool_input``, ``session_id``.
  - Matcher: ``"Edit|Write|Bash|mcp__scieasy__scaffold_block"``.
  - Exit 2 = block; exit 0 = allow.

Behavior to implement in I40c:
  1. Read stdin JSON.
  2. Determine whether the call is about to write a block file:
       - Edit/Write: ``tool_input.file_path`` matches ``blocks/.*\\.py$``.
       - Bash:       ``tool_input.command`` contains ``> blocks/``,
                     ``>> blocks/``, ``tee blocks/``, ``cp ... blocks/``.
       - scaffold_block: always-on (always counts as block authoring).
  3. If yes, look for the session marker at
     ``$CLAUDE_PROJECT_DIR/.scieasy/.session-state/<session_id>/list_blocks_called``.
     - Marker present: exit 0.
     - Marker absent: print to stderr
         "Authoring a custom block requires calling
          mcp__scieasy__list_blocks first to confirm no existing block
          matches your I/O contract. Call list_blocks now, then retry."
       then sys.exit(2).
  4. If no block write detected, exit 0.

Known hook-layer blind spot (per ADR §3.6 + §7.3):
  Exotic Bash writes (``python -c '...'``, ``mv``, here-doc piping
  through ``sh -c``) bypass the regex. This is defense-in-depth, not
  absolute prevention.

# TODO(#1015): Layer 7 filesystem ACL on <project>/blocks/ is the
#   bulletproof escalation path — out of scope per ADR-040 §3.10 (cross-cutting
#   policy decision affecting human-authored blocks too; deferred to a
#   future ADR if drift surfaces in production).
#   Followup: https://github.com/zjzcpj/SciEasy/issues/1015.

S40c skeleton: exits 0 unconditionally.

TODO(#1013): I40c Phase 2a — implement matcher + marker lookup + stderr.
  Out of scope per ADR-040 §3.6 (S40c skeleton).
  Followup: https://github.com/zjzcpj/SciEasy/issues/1013.
"""

import sys

# TODO(#1013): block-detection + marker lookup + exit 2 (see docstring).
sys.exit(0)
