#!/usr/bin/env python
"""hook_remind_poll_status.py — PostToolUse / run_workflow (ADR-040 §3.6).

Purpose:
  After ``mcp__scieasy__run_workflow`` returns, inject a reminder telling
  the agent to poll ``get_run_status`` until the run reaches a terminal
  state. PostToolUse hooks cannot block the call — they can only surface
  stderr feedback for the agent's next turn.

Hook contract:
  - Stdin: JSON payload (includes the tool response).
  - Matcher: ``"mcp__scieasy__run_workflow"``.
  - Always exit 0 (PostToolUse cannot block).
  - Stderr appears in the agent's next-turn context.

Behavior to implement in I40c:
  1. Read stdin JSON (the run_workflow response).
  2. Print to stderr a short reminder, e.g.
       "run_workflow has been kicked off. Poll
        mcp__scieasy__get_run_status periodically until status is
        'completed', 'failed', or 'cancelled' before proceeding."
  3. Optionally extract and echo the run_id from the response for
     concrete context.
  4. sys.exit(0).

S40c skeleton: exits 0 unconditionally with no stderr.

TODO(#1013): I40c Phase 2a — implement reminder injection per
  ADR §3.6. Out of scope per ADR-040 §3.6 (S40c skeleton).
  Followup: https://github.com/zjzcpj/SciEasy/issues/1013.
"""

import sys

# TODO(#1013): print stderr reminder; always exit 0.
sys.exit(0)
