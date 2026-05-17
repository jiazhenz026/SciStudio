# SciEasy project — agent guide

You are an embedded agent inside a SciEasy project workspace. The user
is a researcher building scientific data workflows. The SciEasy GUI is
already running on http://localhost:8000; do NOT start a second
backend.

## Hook safety net — Claude Code only

The rules below are backed by project-scoped hooks at
`<project>/.claude/settings.json` ONLY on Claude Code. On Codex 2026,
the project's `.codex/config.toml` wires the MCP server but there is
NO equivalent hook backstop — per ADR-040 §3.10, Codex hook coverage
is deferred (followup #1015).

What this means in practice:

- **Claude Code**: violating a rule below triggers a PreToolUse /
  PostToolUse hook with stderr feedback and (in some cases) exit
  code 2 hard blocks. You will see the failure immediately.
- **Codex**: the rules still apply — they're load-bearing for runtime
  correctness — but there is no safety net. If you violate one, the
  GUI breaks silently or your blocks fail to load on `reload_blocks`.
  **Codex agents have no margin for error here; self-police.**

## Identity & non-negotiable rules

- Use `mcp__scieasy__*` tools for anything touching blocks, workflows,
  runs, or data. Do NOT use the `scieasy` CLI via Bash — it bypasses
  live GUI updates and ADR-038 lineage tracking. (On Claude Code, a
  PreToolUse hook blocks such calls with exit code 2; on Codex, no
  hook fires — self-police.)
- Do NOT directly Edit/Write `workflows/*.yaml`. Use
  `mcp__scieasy__write_workflow` / `update_block_config` so the
  runtime sees changes through the validated path. (On Claude Code,
  hooks block direct edits; on Codex, no hook fires.)
- BEFORE writing a new block, list existing blocks via
  `mcp__scieasy__list_blocks` and reuse one if its I/O contract
  matches. Build new only when nothing fits (#875). (On Claude Code,
  a PostToolUse hook blocks `blocks/*.py` writes if `list_blocks`
  was not called earlier in the session; on Codex, no hook fires —
  self-police, your block-reuse compliance is on the honor system.)
- BEFORE selecting port types for a new block, call
  `mcp__scieasy__list_types`. Pick the most specific applicable type;
  `DataObject` is reserved for `SubWorkflowBlock`, generic
  `load_data` / `save_data` IOBlocks, and certain `AppBlock`
  patterns (ADR-040 §3.2a). (On Claude Code, a PostToolUse hook
  AST-scans the written file and stderr-warns when a port declares
  `accepted_types=[DataObject]` or omits `accepted_types`; on Codex,
  no hook fires.)
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
