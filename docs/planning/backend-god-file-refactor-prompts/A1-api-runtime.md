[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Decompose `src/scistudio/api/runtime.py` (1839 LOC) into a sub-package while preserving the public import surface and adding tests; pure structural refactor with no behavior change.
- Task kind: refactor
- Persona: implementer
- Issue: #1430
- Issue URL: https://github.com/zjzcpj/SciStudio/issues/1430
- Umbrella PR: #1429 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: umbrella/backend-god-file-refactor
- Agent branch: refactor/issue-1430/api-runtime (pre-created off origin/umbrella/backend-god-file-refactor)
- Agent worktree: C:\Users\jiazh\Desktop\workspace\SciStudio\.claude\worktrees\refactor-a1-api-runtime
- Gate record: .workflow/records/1430-api-runtime.json (you create this with `gate_record start`)
- Checklist: docs/planning/backend-god-file-refactor-checklist.md (read-only for you; manager edits)

## Required Rules

Read and follow:

- GitHub issue #1430 and umbrella issue #1427.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/new-feature.md is NOT applicable. This is a `refactor` task. Follow the gated-workflow rules with task-kind=refactor.
- docs/ai-developer/personas/implementer.md

## Scope

You own only:

- `src/scistudio/api/runtime.py` (will become a sub-package).
- New files under `src/scistudio/api/runtime/` (the sub-package you create).
- New or updated tests under `tests/api/` for the new sub-package.
- `scripts/check_god_files.py` — remove `src/scistudio/api/runtime.py` from `GOD_FILE_SIZE_WAIVERS` when each new file is <750 LOC. Do NOT remove other files' waivers.

You must not touch:

- Any other Phase 1 source file: `src/scistudio/ai/agent/mcp/tools_workflow.py`, `src/scistudio/ai/agent/mcp/tools_inspection.py`, `src/scistudio/api/routes/ai_pty.py`, `src/scistudio/qa/governance/gate_record.py`.
- Any other source file that imports from `scistudio.api.runtime` (verify by grep, but do not edit those callers — the public import surface preservation is your responsibility, callers stay unchanged).
- `docs/planning/backend-god-file-refactor-checklist.md` (manager-owned).
- Other agents' worktrees / branches.
- Anything under `frontend/`, `desktop/`, `packages/`.
- Bucket C / Bucket D god files.

If you need an out-of-scope path, stop and report back.
Do not edit it.

## Coordination

- You are not alone in this codebase. Three other agents (A2 MCP tools, A3 ai_pty, B1 gate_record) are running in parallel against the same umbrella branch.
- MUST work only on your assigned branch `refactor/issue-1430/api-runtime`.
- MUST work only in your assigned worktree at `.claude/worktrees/refactor-a1-api-runtime`.
- MUST NOT use `pip install -e .`. Use `PYTHONPATH=src python ...` for module invocation.
- Do not revert or overwrite other agents' work.
- Do not broaden scope.
- MUST target your PR to `umbrella/backend-god-file-refactor`, NOT `main`.
- MUST NOT merge any PR. Owner does merges.
- Update only your gate record. Manager updates the checklist.
- Record every completed step with PR, commit, test run, or gate-record entry.

## TODO And Deferral Rule

Deferred work must be tracked in the repo.
Use `TODO(#NNN): <reason>` and cite an issue, ADR, spec, or follow-up ticket.
Do not leave hidden V1, MVP, or later work.

Known deferred items:

- Lowering threshold from 750 to 500 — TODO(#1427-followup) after Phase 1+2+3 complete.

## Work To Do

1. Read `src/scistudio/api/runtime.py` end-to-end. List every top-level class, dataclass, function, and module-level constant that is imported from outside the file (grep `from scistudio.api.runtime import` and `from scistudio.api import runtime`).
2. Design a sub-package layout under `src/scistudio/api/runtime/` that:
   - Has an `__init__.py` re-exporting every public name (preserving import surface).
   - Has each sub-module <750 LOC.
   - Groups related concerns (e.g. preview caching, image data-uri, ApiRuntime, dataclasses, log broadcaster) into separate modules.
3. Move code into the new sub-modules. Convert the original `runtime.py` file into the package's `__init__.py` (delete the old `runtime.py` after moving; create `runtime/` directory).
4. Add or update tests under `tests/api/` covering at least one behavior in each new sub-module. Minimum: import-surface preservation test that asserts every previously-public name is still importable via `from scistudio.api.runtime import X`.
5. Run `ruff check` and `ruff format` until clean.
6. Run targeted pytest:
   - `pytest tests/api/ --timeout=60 -x`
   - Plus any callers' tests that import from `scistudio.api.runtime` (find via grep; do not edit the tests, just run them to confirm green).
7. Update `scripts/check_god_files.py`: remove `src/scistudio/api/runtime.py` from `GOD_FILE_SIZE_WAIVERS` once all new files are <750 LOC. Run `python scripts/check_god_files.py --enforce` to confirm 0 NEW violations.
8. Drive the ADR-042 gate-record workflow with task-kind=refactor:
   - `gate_record start --task-kind refactor --issue 1430 --slug api-runtime-refactor --branch refactor/issue-1430/api-runtime --owner-directive "<one-line>" --include "src/scistudio/api/runtime/**" --include "src/scistudio/api/runtime.py" --include "tests/api/**" --include "scripts/check_god_files.py" --record-path .workflow/records/1430-api-runtime.json`
   - `gate_record plan ...` with files, docs (N/A reason if no doc changes), tests, checks=ruff,format,pytest,god_file_advisory,full_audit,sentrux
   - Run full_audit and sentrux (MCP if available, CLI fallback otherwise). Record each via `gate_record check` and `gate_record sentrux`.
   - `gate_record docs --updated <path or N/A:reason>`.
9. Commit with required trailers (`Gate-Record`, `Task-Kind: refactor`, `Issue: #1430`, `Assisted-by`). Use HEREDOC for the commit message.
10. Run `gate_record pr-ready --gate-record <path> --base origin/umbrella/backend-god-file-refactor --head HEAD --pr-body "<draft>"` BEFORE pushing.
11. Push the branch: `git push -u origin refactor/issue-1430/api-runtime`.
12. Open sub-PR via `python scripts/scistudio_pr_create.py --title "refactor(#1430): split api/runtime.py into sub-package" --body-file <body.md> --base umbrella/backend-god-file-refactor`. PR body MUST include `Closes #1430`.
13. `gate_record finalize --commit-sha <sha> --pr-number <N> --pr-url <url> --body-closes-issue 1430`.
14. Commit the finalized gate record on the same branch and push.

## Required Tests And Checks

- `ruff check <changed files>` — pass.
- `ruff format --check <changed files>` — pass.
- `pytest tests/api/ --timeout=60 -x` — pass.
- `python scripts/check_god_files.py --enforce` — pass (after removing `api/runtime.py` from waivers).
- `python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json` — status=pass.
- Sentrux MCP (`scan` + `check_rules` + `health`) or CLI fallback (`sentrux scan . && sentrux check .`) — record evidence.
- `gate_record pr-ready` — pass before push.

## Output Required

Before reporting done, provide:

- Changed file paths (final list).
- All tests/checks run and their results.
- Sub-PR number (e.g. #1XXX) and URL.
- Gate record path and finalize confirmation.
- Any blocker, scope issue, or known follow-up TODO.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file.
- The task conflicts with AGENTS.md, ADR, spec, or gate record.
- CI or local checks fail for unclear reasons.
- Another agent's work blocks yours.
- You cannot add/update required tests.
- A test that previously passed starts failing — root-cause before continuing.
- The public import surface cannot be preserved cleanly — stop and request guidance.
