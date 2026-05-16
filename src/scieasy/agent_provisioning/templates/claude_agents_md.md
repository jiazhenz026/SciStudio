# SciEasy project — agent guide

You are working inside a **SciEasy project**. SciEasy is an AI-native
workflow runtime for multimodal scientific data. The backend (FastAPI
+ MCP server) is **already running** when this prompt loads — you do
**not** start it.

## Core rules

1. **Use MCP tools, not the `scieasy` CLI.** Every block, workflow,
   run, and lineage query is exposed as `mcp__scieasy__<tool>`. Calling
   `scieasy <subcommand>` via Bash bypasses the GUI and lineage — the
   provisioned PreToolUse hook will block it.

2. **Call `mcp__scieasy__list_blocks` before authoring a new block.**
   Most needs are covered by existing blocks; reuse beats re-implementation.
   The hook layer enforces this: writing a `blocks/*.py` file without a
   prior `list_blocks` call in the current session is blocked.

3. **Edit workflow YAML through MCP, not directly.** `workflows/*.yaml`
   is owned by `mcp__scieasy__write_workflow` (schema-validated) and
   `mcp__scieasy__update_block_config` (preserves comments). Direct
   `Edit` / `Write` on workflow YAML is blocked by a hook because it
   bypasses validation and lineage updates.

4. **Use concrete port types.** Custom blocks must declare concrete
   `PortSpec(type=...)` — `DataObject` is reserved for `SubWorkflowBlock`
   and generic `AppBlock`-class blocks. Use `mcp__scieasy__list_types`
   to pick a registered type; the PostToolUse hook stderr-warns when a
   block file declares a generic port type.

5. **Poll run status, do not assume completion.** After
   `mcp__scieasy__run_workflow`, poll `mcp__scieasy__get_run_status`
   until status is `completed`, `failed`, or `cancelled` before
   reasoning about results.

## What lives where

- `workflows/` — workflow YAML (managed via MCP).
- `blocks/` — user-authored custom blocks (`*.py`). Edit through
  `mcp__scieasy__scaffold_block` when possible.
- `data/` — raw inputs and persisted outputs (zarr, parquet, artifacts).
- `types/` — user-registered data type schemas (managed via MCP).
- `.scieasy/` — runtime state (lineage.db, session markers). Do not
  edit by hand.

## When in doubt

Skills under `.claude/skills/scieasy/` (Claude Code) and
`.agents/skills/scieasy/` (Codex) provide task-scoped guidance:

- `scieasy-build-workflow` — design a new workflow
- `scieasy-write-block` — author a custom block
- `scieasy-debug-run` — diagnose a failed run
- `scieasy-inspect-data` — explore data references / lineage
- `scieasy-project-qa` — project structure / docs Q&A

The base `scieasy` skill provides the tool catalog and environment
assumptions; load it first when starting a new task.
