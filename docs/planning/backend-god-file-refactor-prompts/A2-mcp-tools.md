[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Decompose two cohesive MCP tool files (`tools_workflow.py` 884 + `tools_inspection.py` 809) into sub-packages while preserving the public tool registration surface and adding tests; pure structural refactor with no behavior change.
- Task kind: refactor
- Persona: implementer
- Issue: #1431
- Issue URL: https://github.com/zjzcpj/SciStudio/issues/1431
- Umbrella PR: #1429 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: umbrella/backend-god-file-refactor
- Agent branch: refactor/issue-1431/mcp-tools-pair (pre-created off origin/umbrella/backend-god-file-refactor)
- Agent worktree: C:\Users\<user>\Desktop\workspace\SciStudio\.claude\worktrees\refactor-a2-mcp-tools
- Gate record: .workflow/records/1431-mcp-tools-pair.json (you create this with `gate_record start`)
- Checklist: docs/planning/backend-god-file-refactor-checklist.md (read-only for you; manager edits)

## Required Rules

Read and follow:

- GitHub issue #1431 and umbrella issue #1427.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/personas/implementer.md

## Scope

You own only:

- `src/scistudio/ai/agent/mcp/tools_workflow.py` (will become a sub-package `tools_workflow/`).
- `src/scistudio/ai/agent/mcp/tools_inspection.py` (will become a sub-package `tools_inspection/`).
- New files under `src/scistudio/ai/agent/mcp/tools_workflow/` and `src/scistudio/ai/agent/mcp/tools_inspection/`.
- New or updated tests under `tests/ai/agent/mcp/`.
- `scripts/check_god_files.py` — remove these two files from `GOD_FILE_SIZE_WAIVERS` when each new file is <750 LOC. Do NOT remove other files' waivers.

You must not touch:

- Any other Phase 1 source file: `src/scistudio/api/runtime.py`, `src/scistudio/api/routes/ai_pty.py`, `src/scistudio/qa/governance/gate_record.py`.
- Any other `src/scistudio/ai/agent/mcp/*.py` file (other MCP modules).
- The MCP server registration entry point (where the tools are imported and registered) — your public surface preservation must keep that file unchanged.
- `docs/planning/backend-god-file-refactor-checklist.md` (manager-owned).
- Other agents' worktrees / branches.
- Anything under `frontend/`, `desktop/`, `packages/`.

If you need an out-of-scope path, stop and report back.
Do not edit it.

## Coordination

- You are not alone in this codebase. Three other agents (A1 api/runtime, A3 ai_pty, B1 gate_record) are running in parallel against the same umbrella branch.
- MUST work only on your assigned branch `refactor/issue-1431/mcp-tools-pair`.
- MUST work only in your assigned worktree at `.claude/worktrees/refactor-a2-mcp-tools`.
- MUST NOT use `pip install -e .`. Use `PYTHONPATH=src python ...`.
- Do not revert or overwrite other agents' work.
- Do not broaden scope.
- MUST target your PR to `umbrella/backend-god-file-refactor`, NOT `main`.
- MUST NOT merge any PR.

## TODO And Deferral Rule

Deferred work must be tracked in the repo with `TODO(#NNN): <reason>` and a citation. No hidden V1/MVP/later work.

Known deferred items: none beyond the umbrella-level deferrals (Bucket C/D, threshold lowering).

## Work To Do

1. Read both source files. List every public MCP tool function and module-level name imported from outside.
2. Design two parallel sub-package layouts under `tools_workflow/` and `tools_inspection/`, each with `__init__.py` re-exporting every public name and sub-modules <750 LOC.
3. Move code into the new sub-modules. Delete the old single-file modules; create the directories.
4. Add tests under `tests/ai/agent/mcp/` covering import-surface preservation for both packages plus at least one behavior test per new sub-module.
5. Run `ruff check`, `ruff format` until clean.
6. Run targeted pytest: `pytest tests/ai/agent/mcp/ --timeout=60 -x` plus any MCP-server-registration tests that import these modules.
7. Update `scripts/check_god_files.py`: remove both files from `GOD_FILE_SIZE_WAIVERS`. Run `python scripts/check_god_files.py --enforce` — expect 0 NEW.
8. ADR-042 gate-record workflow (same shape as A1; see umbrella scaffold gate record for reference). `task-kind=refactor`, `--issue 1431`, `--slug mcp-tools-pair`.
9. Commit with required AI trailers.
10. `gate_record pr-ready` before push.
11. Push branch.
12. Open sub-PR via wrapper: title `refactor(#1431): split MCP tools_workflow + tools_inspection into sub-packages`, base=`umbrella/backend-god-file-refactor`, body MUST `Closes #1431`.
13. `gate_record finalize`.
14. Commit finalized record + push.

## Required Tests And Checks

- ruff check + ruff format --check — pass.
- `pytest tests/ai/agent/mcp/ --timeout=60 -x` — pass.
- `python scripts/check_god_files.py --enforce` — pass.
- full_audit (record evidence).
- Sentrux (MCP `scan`+`check_rules`+`health`; record evidence).
- `gate_record pr-ready` — pass.

## Output Required

- Changed file paths.
- Tests/checks results.
- Sub-PR number + URL.
- Gate record path + finalize confirmation.
- Blockers / TODOs.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file.
- Tests previously passing start failing — root-cause before continuing.
- Public surface cannot be preserved cleanly.
- Another agent blocks yours.
