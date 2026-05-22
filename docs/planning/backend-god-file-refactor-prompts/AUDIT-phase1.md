[DISPATCH-TEMPLATE-V1: audit-with-context]

## Task Identity

- Repository: SciStudio
- Persona: audit_reviewer
- Audit mode: with-context
- Issue: #1427
- Issue URL: https://github.com/zjzcpj/SciStudio/issues/1427
- Owner request: Independent post-implementation review of the 4 Phase 1 sub-PRs under umbrella #1427 — verify scope discipline, public-surface preservation, test coverage, ADR-042 gate compliance, and CI sufficiency. Owner authorized this audit on 2026-05-22 chat.
- Umbrella PR: #1429 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: umbrella/backend-god-file-refactor
- Audit branch: audit/issue-1427/phase1-review (pre-created off origin/umbrella/backend-god-file-refactor)
- Audit worktree: C:\Users\jiazh\Desktop\workspace\SciStudio\.claude\worktrees\audit-1427-phase1
- Manager gate record: .workflow/records/1427-backend-god-file-refactor.json
- Checklist: docs/planning/backend-god-file-refactor-checklist.md
- PRs to audit: #1441, #1442, #1444, #1445
- Audit report path: docs/audit/2026-05-22-umbrella-1427-phase1-with-context.md

## Required Reading

Read and follow:

- GitHub issue #1427 (umbrella) and the 4 sub-issues #1430 / #1431 / #1432 / #1433.
- The manager checklist at `docs/planning/backend-god-file-refactor-checklist.md`.
- Each sub-PR's description, changed files, gate record, and CI results.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/personas/audit-reviewer.md
- Governing ADRs referenced by the changed files (especially ADR-012, ADR-028 Addendum 1, ADR-034, ADR-035, ADR-038, ADR-039, ADR-042, ADR-044, ADR-045 — the agent reports cite these explicitly).
- Memory feedback notes that informed the dispatch (worth knowing about, available in `.claude/projects/.../memory/`):
  - `feedback_audit_agent_codex_review` — Codex auto-review reconcile (Codex did not fire here, 5-min cap reached; record this in findings).
  - `feedback_audit_p1_override` — P1 findings MUST be fixed in-PR; do not allow "non-blocking deferred" framing.

## Audit Goal

Verify the four Phase 1 sub-PRs match their dispatch prompts:

1. **Scope discipline**: each PR's changed files match the `Scope.in scope` declared in its dispatch prompt and the umbrella checklist. Anything outside is a finding (P1 if it crosses bucket boundaries; P2 otherwise).
2. **Public import surface preservation**: every name previously importable from the original god file is still importable via the same path. Run import smoke for each, not just trust the agents' tests.
3. **Test coverage**: per ADR-042 implementation-category rule, each PR adds/updates at least one test file. Tests must actually exercise the new sub-modules, not just import-pin them.
4. **Gate-record integrity**: each PR's `.workflow/records/<...>.json` has all 6 stages done, issue URL populated, governance_touch correct (true only for B1), `admin-approved:core-change` label present on B1's PR.
5. **CI sufficiency**: each PR has the `Verify Workflow Compliance` check green on the latest commit.
6. **Cross-PR coordination**: no two PRs touched the same file outside their declared scope.

Severity scheme:

- **P1**: blocks merge or breaks contract.
- **P2**: should fix before completion (manager will decide in-PR fix vs. deferred follow-up; per memory `feedback_audit_p1_override`, manager will override "non-blocking deferred" framing if Codex/audit calls something P1).
- **P3**: improvement or follow-up.

## Scope

Audit these claims (from each agent's final report):

- **A1 (#1430 / PR #1445)**: `api/runtime.py` 1839 LOC → 8 sub-modules under `src/scistudio/api/runtime/`, largest 476 LOC; 4 new tests in `tests/api/test_runtime_import_surface.py`; ADR frontmatter updates to ADR-012/038/039/044/045 governs.files; "ApiRuntime defined directly in `__init__.py`" design choice with class-body static binding of free functions.
- **A2 (#1431 / PR #1441)**: `tools_workflow.py` 884 + `tools_inspection.py` 809 → 13 modules across two sub-packages; 24 new tests; lazy lookup pattern preserved for existing monkeypatch sites (`tools_workflow._atomic_write_text`, `tools_inspection._MAX_PREVIEW_BYTES`).
- **A3 (#1432 / PR #1444)**: `api/routes/ai_pty.py` 757 → 6 modules under `src/scistudio/api/routes/ai_pty/` (engine/websocket/validation/subscribers/internal_routes); 41 new tests; ADR-034/ADR-035 frontmatter updated; "public-named submodules" design choice (not underscore-prefixed) so griffe emits the canonical contract facts.
- **B1 (#1433 / PR #1442)**: `gate_record.py` 1402 → `gate_record/` package with paths/models/io/stages/validation/cli/__main__/__init__; 18 new tests + 102 existing pass; `admin-approved:core-change` label applied; ADR-042 Addendum 1/3 + spec frontmatter governs.contracts updated to canonical sub-module paths.

Audit these surfaces:

- All files changed in PRs #1441, #1442, #1444, #1445.
- The manager checklist's dispatch matrix (cross-check claimed status vs. PR state).
- `scripts/check_god_files.py` final waiver count (should be 5: only Bucket C/D files left from the 10 ≥750 candidates).
- The 4 finalized gate records under each agent's worktree (paths in checklist Section 6).

Do NOT write feature code.
MUST write the audit report to `docs/audit/2026-05-22-umbrella-1427-phase1-with-context.md` and commit + push it on the audit branch, then open an audit PR targeting `umbrella/backend-god-file-refactor`.
Only edit the audit report file and the audit checklist rows in `docs/planning/backend-god-file-refactor-checklist.md` Section 7.4.

## Coordination

- MUST work only on branch `audit/issue-1427/phase1-review`.
- MUST work only in worktree `C:\Users\jiazh\Desktop\workspace\SciStudio\.claude\worktrees\audit-1427-phase1`.
- MUST NOT `pip install -e .`. Use `PYTHONPATH=src python ...`.
- MUST NOT merge any PR.
- MUST NOT fix implementation code. If you find a P1 that requires a code fix, report it; the manager will dispatch a fix agent or fix it directly.
- Do not overwrite the implementer agents' or manager's work.

## Checks

Run or verify:

- `ruff check` on every changed source file across the 4 PRs — confirm pass on each branch HEAD.
- `pytest <scoped-test-dirs> --timeout=60 -x` for at least one test from each PR — confirm pass.
- `python scripts/check_god_files.py --enforce` on each PR's HEAD — confirm 0 NEW + the right waivers removed.
- `python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json` on the audit branch — status must be pass.
- Sentrux MCP (`scan`, `check_rules`, `health`, optionally `session_start`/`session_end`) on the audit worktree — record quality_signal vs. pre-Phase-1 baseline (4442 at scaffold).
- Import-surface verification: for each refactored file, `PYTHONPATH=src python -c "from scistudio.<path> import <name1>, <name2>, ..."` for every name the audit can identify from the pre-refactor module — confirm import success without warning. Audit must independently grep callers, not trust the agent's tests alone.
- CI status check: `gh pr checks 1441 1442 1444 1445` — confirm all four green.
- `gate_record ci` on each sub-PR's gate record with the PR body — confirm pass on each (this is the check that found the original CI failures; audit must independently re-run).

## Output Required

- Audit report path: `docs/audit/2026-05-22-umbrella-1427-phase1-with-context.md` (committed + pushed on audit branch + audit PR opened against umbrella branch).
- Findings ordered by severity (P1, P2, P3), with file + line references where applicable.
- Checklist drift, if any.
- Scope drift, if any.
- Missing tests/docs/gate evidence, if any.
- CI status confirmation per PR.
- Codex auto-review reconcile note: Codex did NOT fire on these PRs within the 5-min cap from CI-green (per memory `feedback_codex_review_timeout`); record that as an audit observation.
- Per-PR recommendation: `pass`, `pass-with-fixes`, or `block`.
- Overall recommendation for the umbrella Phase 1 merge readiness.

## Stop Conditions

Stop and report back if:

- You need to change implementation code.
- Required evidence is unavailable (e.g., one of the 4 PRs gets force-pushed mid-audit).
- The audit scope conflicts with AGENTS.md, ADR, spec, or gate record.
- A P1 finding requires immediate manager action before the rest of the audit makes sense.
