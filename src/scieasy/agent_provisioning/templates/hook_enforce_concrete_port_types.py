#!/usr/bin/env python
"""hook_enforce_concrete_port_types.py — PostToolUse (ADR-040 §3.6).

Purpose:
  After a write touched ``<project>/blocks/*.py``, AST-parse the file and
  scan for generic-typed ports (``PortSpec(type="DataObject")`` or
  references to type names not registered in TypeRegistry). Stderr-warn
  the agent so the next turn corrects the type. Companion to §3.2a
  MCP-result soft validation; this hook catches the Edit/Write-bypass
  path that goes around ``scaffold_block``.

Hook contract:
  - Stdin: JSON payload.
  - Matcher: ``"Edit|Write|mcp__scieasy__scaffold_block"``.
  - Always exit 0 (PostToolUse cannot block); stderr surfaces in next
    agent turn.

Behavior to implement in I40c:
  1. Read stdin JSON.
  2. Determine target file:
     - Edit/Write: ``tool_input.file_path``; skip unless matches
       ``blocks/.*\\.py$``.
     - scaffold_block: pull the written path from the tool response.
  3. Read the file; ``ast.parse`` it.
  4. Walk the AST for ``PortSpec(type="DataObject")``, ``type=DataObject``
     (Name node, not subscript), and type names absent from a known
     TypeRegistry snapshot (call out via subprocess to MCP tool
     ``list_types`` — design decision deferred to I40c).
  5. For each finding, print to stderr:
       Block at {file}:{lineno} declares port '{port_name}' with generic
       DataObject. This degrades preview & edge-time type-check. Call
       mcp__scieasy__list_types and pick a concrete type; DataObject is
       reserved for SubWorkflowBlock and generic AppBlock-class blocks.
  6. sys.exit(0).

Known blind spot (per ADR §3.6 / §7.3):
  Exotic Bash writes can land in ``blocks/`` without this hook firing,
  same as ``hook_enforce_list_blocks_before_block_write.py``.

# TODO(#1016): BlockRegistry runtime rejection of DataObject-typed ports
#   is the hard enforcement — out of scope per ADR-040 §3.10 (cross-cutting
#   policy decision affecting human-authored blocks too; deferred to a
#   future ADR / ADR-041 if pursued).
#   Followup: https://github.com/zjzcpj/SciEasy/issues/1016.

S40c skeleton: exits 0 unconditionally.

TODO(#1013): I40c Phase 2a — implement AST scan + stderr per
  ADR §3.6. Out of scope per ADR-040 §3.6 (S40c skeleton).
  Followup: https://github.com/zjzcpj/SciEasy/issues/1013.
"""

import sys

# TODO(#1013): AST scan + stderr findings; always exit 0.
sys.exit(0)
