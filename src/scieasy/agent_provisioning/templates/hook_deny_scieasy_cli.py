#!/usr/bin/env python
"""hook_deny_scieasy_cli.py — PreToolUse / Bash matcher (ADR-040 §3.6).

Purpose:
  Block ``scieasy <subcommand>`` invocations via Bash to enforce
  MCP-only access. Closes the CLI-vs-MCP half of issue #875.

Hook contract (Claude Code):
  - Stdin: JSON payload with ``tool_input.command`` for Bash matchers.
  - Matcher (settings.json): ``"Bash"``.
  - Exit 2 + stderr line: blocks the tool call, surfaces stderr to agent.
  - Exit 0: allows the tool call.

Behavior to implement in I40c:
  1. Read stdin as JSON.
  2. Extract ``tool_input.command``.
  3. Regex ``^\\s*(.*/)?scieasy[\\s$]`` — matches ``scieasy ...``,
     ``./scieasy ...``, ``/abs/path/to/scieasy ...``.
  4. On match: print to stderr
       "SciEasy CLI calls bypass the GUI and lineage. Use
        mcp__scieasy__* tools instead: list_blocks, write_workflow,
        run_workflow, get_run_status."
     then ``sys.exit(2)``.
  5. Otherwise ``sys.exit(0)``.

S40c skeleton: exits 0 unconditionally so this hook is a NO-OP until
I40c authors the matcher. Importantly, S40c MUST NOT exit 2 — a
half-finished blocker would break every Bash call in a provisioned
project.

TODO(#1013): I40c Phase 2a — implement matcher + stderr message per
  ADR §3.6. Out of scope per ADR-040 §3.6 (S40c skeleton).
  Followup: https://github.com/zjzcpj/SciEasy/issues/1013.
"""

import sys

# TODO(#1013): regex matcher + exit 2 (see module docstring above).
sys.exit(0)
