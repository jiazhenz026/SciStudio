[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Decompose `src/scistudio/api/routes/ai_pty.py` (757 LOC) into a sub-package while preserving the FastAPI router public surface and adding tests; pure structural refactor with no behavior change.
- Task kind: refactor
- Persona: implementer
- Issue: #1432
- Issue URL: https://github.com/zjzcpj/SciStudio/issues/1432
- Umbrella PR: #1429 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: umbrella/backend-god-file-refactor
- Agent branch: refactor/issue-1432/api-ai-pty (pre-created off origin/umbrella/backend-god-file-refactor)
- Agent worktree: C:\Users\<user>\Desktop\workspace\SciStudio\.claude\worktrees\refactor-a3-ai-pty
- Gate record: .workflow/records/1432-api-ai-pty.json
- Checklist: docs/planning/backend-god-file-refactor-checklist.md (read-only)

## Required Rules

Read and follow:

- GitHub issue #1432 and umbrella #1427.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/personas/implementer.md

## Scope

You own only:

- `src/scistudio/api/routes/ai_pty.py` (will become a sub-package `ai_pty/`).
- New files under `src/scistudio/api/routes/ai_pty/`.
- New or updated tests under `tests/api/routes/`.
- `scripts/check_god_files.py` — remove `src/scistudio/api/routes/ai_pty.py` from `GOD_FILE_SIZE_WAIVERS` once new files are <750 LOC. Do NOT remove other waivers.

You must not touch:

- Any other Phase 1 source: `src/scistudio/api/runtime.py`, `src/scistudio/ai/agent/mcp/tools_workflow.py`, `src/scistudio/ai/agent/mcp/tools_inspection.py`, `src/scistudio/qa/governance/gate_record.py`.
- Any other `src/scistudio/api/routes/*.py` file.
- The API root assembler (where the router is registered) — your public surface preservation keeps that file unchanged.
- `docs/planning/backend-god-file-refactor-checklist.md` (manager-owned).
- Other agents' worktrees / branches.
- `frontend/`, `desktop/`, `packages/`.

If you need an out-of-scope path, stop and report back.

## Coordination

- Three other agents are running in parallel. Stay strictly in your branch + worktree.
- MUST work on branch `refactor/issue-1432/api-ai-pty`.
- MUST work in `.claude/worktrees/refactor-a3-ai-pty`.
- MUST NOT `pip install -e .`. Use `PYTHONPATH=src python ...`.
- MUST target PR to `umbrella/backend-god-file-refactor`, NOT `main`.
- MUST NOT merge.

## TODO And Deferral Rule

Use `TODO(#NNN): <reason>` for any deferred work, citing an issue/ADR/spec/PR.

Known deferred items: none beyond umbrella-level.

## Work To Do

1. Read the source file; list every public symbol imported externally (router, route handlers, etc.).
2. Design sub-package layout under `ai_pty/` with `__init__.py` re-exporting public names; sub-modules <750 LOC.
3. Move code; delete old single-file module.
4. Add tests under `tests/api/routes/` covering import-surface preservation + at least one behavior test per sub-module.
5. ruff check + ruff format until clean.
6. `pytest tests/api/routes/ --timeout=60 -x`.
7. Update `scripts/check_god_files.py` waivers; `python scripts/check_god_files.py --enforce` — expect 0 NEW.
8. ADR-042 gate-record workflow with task-kind=refactor, issue=1432, slug=api-ai-pty-refactor.
9. Commit with required trailers.
10. `gate_record pr-ready` before push.
11. Push branch.
12. Open sub-PR via wrapper: title `refactor(#1432): split api/routes/ai_pty.py into sub-package`, base=`umbrella/backend-god-file-refactor`, body MUST `Closes #1432`.
13. `gate_record finalize`.
14. Commit finalized record + push.

## Required Tests And Checks

- ruff check + ruff format --check — pass.
- `pytest tests/api/routes/ --timeout=60 -x` — pass.
- `python scripts/check_god_files.py --enforce` — pass.
- full_audit — pass; record.
- Sentrux MCP — record evidence.
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
