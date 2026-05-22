[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Decompose `src/scistudio/qa/governance/gate_record.py` (1402 LOC) into a sub-package along the natural 6-stage seam while preserving the public CLI surface AND every importable symbol; pure structural refactor with no behavior change.
- Task kind: refactor
- Persona: implementer
- Issue: #1433
- Issue URL: https://github.com/zjzcpj/SciStudio/issues/1433
- Umbrella PR: #1429 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: umbrella/backend-god-file-refactor
- Agent branch: refactor/issue-1433/gate-record (pre-created off origin/umbrella/backend-god-file-refactor)
- Agent worktree: C:\Users\jiazh\Desktop\workspace\SciStudio\.claude\worktrees\refactor-b1-gate-record
- Gate record: .workflow/records/1433-gate-record-refactor.json
- Checklist: docs/planning/backend-god-file-refactor-checklist.md (read-only)

## Critical: Protected Path + Self-Hosting Hazard

- **Your refactor target IS the gate-record tool itself.** You are using `python -m scistudio.qa.governance.gate_record ...` to record evidence of refactoring `python -m scistudio.qa.governance.gate_record`. Avoid touching the module's `__main__` invocation behavior under any circumstance.
- **Path `src/scistudio/qa/governance/**` is a protected core path.** Your PR MUST be opened with the label `admin-approved:core-change` (owner authorized this on 2026-05-22 specifically for this file). Use `gh pr edit <N> --add-label admin-approved:core-change` immediately after opening the PR if the wrapper does not set it.
- **`gate_record start --task-kind refactor --governance-touch` MUST be set true** because this is a governance-file refactor.
- **CI parity check**: run `gate_record ci` locally with the real PR body BEFORE pushing (memory says local pre-push ≠ CI).

## Required Rules

Read and follow:

- GitHub issue #1433 and umbrella #1427.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/personas/implementer.md
- ADR-042 and ADR-042 Addendum 1 (the gate-record spec — your refactor must keep all its rules intact).

## Scope

You own only:

- `src/scistudio/qa/governance/gate_record.py` (will become a sub-package `gate_record/`).
- New files under `src/scistudio/qa/governance/gate_record/`.
- New or updated tests under `tests/qa/governance/`.
- `scripts/check_god_files.py` — remove `src/scistudio/qa/governance/gate_record.py` from `GOD_FILE_SIZE_WAIVERS` once new files are <750 LOC. Do NOT remove other waivers.

You must not touch:

- Any other file under `src/scistudio/qa/governance/` (e.g., `paths.py`).
- `src/scistudio/qa/schemas/**` or `src/scistudio/qa/audit/**`.
- Any other Phase 1 source: `src/scistudio/api/runtime.py`, `src/scistudio/ai/agent/mcp/tools_workflow.py`, `src/scistudio/ai/agent/mcp/tools_inspection.py`, `src/scistudio/api/routes/ai_pty.py`.
- `scripts/scistudio_pr_create.py` (the PR wrapper depends on `gate_record` — leave its API stable).
- `.github/workflows/**` (CI calls `gate_record ci` — leave invocation stable).
- `docs/planning/backend-god-file-refactor-checklist.md` (manager-owned).
- Other agents' worktrees / branches.
- `frontend/`, `desktop/`, `packages/`.

If you need an out-of-scope path, stop and report back.

## Coordination

- Three other agents are running in parallel. Stay strictly in your branch + worktree.
- MUST work on branch `refactor/issue-1433/gate-record`.
- MUST work in `.claude/worktrees/refactor-b1-gate-record`.
- MUST NOT `pip install -e .`. Use `PYTHONPATH=src python ...`.
- MUST target PR to `umbrella/backend-god-file-refactor`, NOT `main`.
- MUST NOT merge.

## TODO And Deferral Rule

Use `TODO(#NNN): <reason>` for any deferred work. No hidden V1/MVP/later.

Known deferred items: none beyond umbrella-level.

## Work To Do

1. Read `gate_record.py` end-to-end. Inventory:
   - Every CLI subcommand (`start`, `plan`, `amend`, `docs`, `check`, `sentrux`, `finalize`, `pre-commit`, `commit-msg`, `pre-push`, `ci`, `pr-ready`).
   - Every public function (`validate_gate_record`, `check_pr`, `check_pr_ready`, etc.).
   - Every public class / dataclass / enum (`GateRecord`, `GateStage`, `CheckEvidence`, `ScopeAmendment`, `IMPLEMENTATION_TASK_KINDS`, etc.).
2. Design a sub-package layout under `src/scistudio/qa/governance/gate_record/`. Suggested seams (you choose; document your choice in the PR body):
   - `models.py` — `GateRecord`, `GateStage`, `CheckEvidence`, `ScopeAmendment`, etc. (pydantic models + enums).
   - `validation.py` — `validate_gate_record`, `check_pr`, `check_pr_ready`, `_finding`, guard implementations.
   - `stages/` — one module per stage (`_mark_stage` helpers + per-stage logic).
   - `cli.py` — argparse setup and dispatch.
   - `paths.py` — constants like `IMPLEMENTATION_PATTERNS`, `CLOSING_KEYWORD_RE`, `VALID_OVERRIDE_LABELS`.
   - `__init__.py` — re-export every public name + provide the CLI entry point as `main()`.
   - `__main__.py` — calls `from .cli import main` so `python -m scistudio.qa.governance.gate_record` keeps working.
3. Each new file <750 LOC.
4. Move code; delete the old single-file module.
5. Add tests under `tests/qa/governance/` covering import-surface preservation (every name still importable via `from scistudio.qa.governance.gate_record import X`) + CLI smoke test for each subcommand (`--help` should exit 0 and show the same usage).
6. Run `ruff check` + `ruff format` until clean.
7. Run targeted pytest:
   - `pytest tests/qa/governance/ --timeout=60 -x`
   - Self-hosting smoke: invoke the refactored CLI against a temp record to confirm every subcommand still works.
8. Update `scripts/check_god_files.py`: remove `gate_record.py` from waivers; `python scripts/check_god_files.py --enforce` — expect 0 NEW.
9. ADR-042 gate-record workflow:
   - `gate_record start --task-kind refactor --issue 1433 --slug gate-record-refactor --branch refactor/issue-1433/gate-record --governance-touch --owner-directive "<one-line>" --include "src/scistudio/qa/governance/gate_record/**" --include "src/scistudio/qa/governance/gate_record.py" --include "tests/qa/governance/**" --include "scripts/check_god_files.py" --record-path .workflow/records/1433-gate-record-refactor.json`
   - `gate_record plan ...`
   - Run full_audit + sentrux; record both via `check` and `sentrux`.
   - `gate_record docs --updated <path or N/A:reason>`.
10. Commit with required AI trailers.
11. `gate_record ci --base origin/umbrella/backend-god-file-refactor --head HEAD --pr-body "<actual body text, not a filename>"` — pass before push (memory says local pre-push ≠ CI's Verify Workflow Compliance).
12. Push branch.
13. Open sub-PR via wrapper: title `refactor(#1433): split qa/governance/gate_record.py into sub-package`, base=`umbrella/backend-god-file-refactor`, body MUST `Closes #1433`. Then `gh pr edit <N> --add-label admin-approved:core-change`.
14. `gate_record finalize`.
15. Commit finalized record + push.

## Required Tests And Checks

- ruff check + ruff format --check — pass.
- `pytest tests/qa/governance/ --timeout=60 -x` — pass.
- CLI smoke test (every subcommand `--help` exits 0).
- `python scripts/check_god_files.py --enforce` — pass.
- full_audit — pass; record.
- Sentrux MCP (`scan`+`check_rules`+`health`) — record evidence.
- `gate_record ci` with actual PR body — pass before push.
- `gate_record pr-ready` — pass.

## Output Required

- Changed file paths (the new sub-package layout).
- Tests/checks results.
- Sub-PR number + URL.
- Confirmation that `admin-approved:core-change` label is set on the PR.
- Gate record path + finalize confirmation.
- Blockers / TODOs.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file.
- Any existing test under `tests/qa/governance/` starts failing — root-cause before continuing; do not relax assertions.
- Self-hosting hits a circular dependency (the refactored gate_record fails when invoked on its own gate record).
- The `admin-approved:core-change` label cannot be applied.
- The CLI surface cannot be preserved byte-identical.
- Another agent blocks yours.
