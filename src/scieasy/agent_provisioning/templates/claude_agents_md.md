# SciEasy project — agent guide

You are an embedded agent inside a SciEasy project workspace. The user
is a researcher building scientific data workflows. The SciEasy GUI is
already running on http://localhost:8000; do NOT start a second
backend.

## Identity & non-negotiable rules

- Use `mcp__scieasy__*` tools for anything touching blocks, workflows,
  runs, or data. Do NOT use the `scieasy` CLI via Bash — it bypasses
  live GUI updates and ADR-038 lineage tracking. A PreToolUse hook
  blocks such calls with exit code 2.
- Do NOT directly Edit/Write `workflows/*.yaml`. Use
  `mcp__scieasy__write_workflow` / `update_block_config` so the
  runtime sees changes through the validated path. Hooks block direct
  edits.
- BEFORE writing a new block, list existing blocks via
  `mcp__scieasy__list_blocks` and reuse one if its I/O contract
  matches. Build new only when nothing fits (#875). A PostToolUse
  hook blocks `blocks/*.py` writes if `list_blocks` was not called
  earlier in the session.
- BEFORE selecting port types for a new block, call
  `mcp__scieasy__list_types`. Pick the most specific applicable type;
  `DataObject` is reserved for `SubWorkflowBlock` and generic
  `AppBlock` patterns (ADR-040 §3.2a). A PostToolUse hook
  stderr-warns when a block file declares a generic port type.
- After every write-class MCP tool call, READ the `next_step` field in
  the result envelope and follow it. After `scaffold_block`, READ
  every entry in `warnings: list[str]` before proceeding.
- Poll `mcp__scieasy__get_run_status` until terminal (`succeeded` /
  `failed` / `cancelled`) before reasoning about results. Do not
  declare "done" on `running`.
- Working directory (`cwd`) is the project root. Use relative paths
  (`data/raw/x.tif`, `workflows/foo.yaml`); MCP tools resolve them
  against the project root and reject paths escaping it.
- All workflow YAML changes are git-tracked (ADR-039). The user sees
  your diffs and can revert.

## Skills available

Invoke the relevant skill before deep work in that area. Skills under
`.claude/skills/scieasy/` (Claude Code) and `.agents/skills/scieasy/`
(Codex) are mirrored — both providers see the same teaching surface.

- `scieasy-build-workflow` — design a new workflow (YAML schema,
  validation, run lifecycle).
- `scieasy-write-block` — author a custom block (Block ABC, port
  types, scaffold → edit → reload).
- `scieasy-debug-run` — diagnose a failed run (run status, logs,
  lineage, `finish_ai_block`).
- `scieasy-inspect-data` — explore data references (inspect / preview
  / lineage) without materialising.
- `scieasy-project-qa` — project structure / docs / installed
  plugins / data layout Q&A.

The skill body is the canonical teaching surface. This file is the
identity + non-negotiable-rules index. If a rule here conflicts with
a skill body, ask the user — do not silently pick one.

## What lives where

- `workflows/` — workflow YAML, managed via MCP.
- `blocks/` — user-authored custom blocks (`*.py`). Edit through
  `mcp__scieasy__scaffold_block` when possible.
- `data/` — raw inputs and persisted outputs (zarr, parquet,
  artifacts).
- `types/` — user-registered data type schemas, managed via MCP.
- `.scieasy/` — runtime state (lineage.db, session markers). Do not
  edit by hand.

## What this file is NOT

This file is intentionally short. Detailed contract teaching (YAML
schemas, block-authoring patterns, error-signature catalogs) lives in
the skills — load the relevant one and follow its guidance.
