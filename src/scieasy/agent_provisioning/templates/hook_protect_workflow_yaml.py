#!/usr/bin/env python
"""hook_protect_workflow_yaml.py — PreToolUse / Edit|Write (ADR-040 §3.6).

Purpose:
  Block direct ``Edit`` / ``Write`` tool calls targeting
  ``workflows/*.yaml`` so workflow edits flow through the schema-validated
  MCP path (``write_workflow`` / ``update_block_config``). The latter
  preserves YAML comments and triggers ADR-038 lineage updates; the
  former does not.

Hook contract:
  - Stdin: JSON payload with ``tool_input.file_path`` for Edit/Write.
  - Matcher (settings.json): ``"Edit|Write"``.
  - Exit 2 = block; exit 0 = allow.

Behavior to implement in I40c:
  1. Read stdin JSON.
  2. Extract ``tool_input.file_path``.
  3. Regex ``workflows/.*\\.ya?ml$``.
  4. On match: print to stderr
       "workflows/*.yaml is managed by mcp__scieasy__write_workflow
        (schema-validated) and mcp__scieasy__update_block_config
        (preserves comments). Direct Edit/Write bypasses validation."
     then ``sys.exit(2)``.
  5. Otherwise ``sys.exit(0)``.

S40c skeleton: exits 0 unconditionally.

TODO(#1013): I40c Phase 2a — implement matcher + stderr message per
  ADR §3.6. Out of scope per ADR-040 §3.6 (S40c skeleton).
  Followup: https://github.com/zjzcpj/SciEasy/issues/1013.
"""

import sys

# TODO(#1013): regex matcher + exit 2.
sys.exit(0)
