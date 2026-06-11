---
title: "ADR-048 PR Fix Dispatch Checklist"
status: Draft
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 48
language_source: en
---

# ADR-048 PR Fix Dispatch Checklist

> Mandatory manager checklist for the 2026-06-11 owner-directed repair pass.
> Existing DO NOT MERGE PRs #1577, #1580, and #1581 are the umbrella PRs for this pass.
> This is an owner-directed deviation from creating new umbrella PRs; no new umbrella PR is opened.

## 1. Change Summary

- Owner request: dispatch three agents to repair the three ADR-048 DO NOT MERGE PRs, push commits, then run three no-context audits.
- Task kind: `manager`
- Manager persona: `manager`
- Issues: `#1574`, `#1575`, `#1576`
- Gate records:
  - `.workflow/records/1574-track-adr-048-spec1-preview-system.json`
  - `.workflow/records/1575-track-adr-048-spec2-plot-tools.json`
  - `.workflow/records/1576-track-adr-048-spec3-docs.json`
- Branch/worktree plan:
  - SPEC 1: `track/adr-048-spec1-preview-system`, `C:\Users\jiazh\Desktop\workspace\sci-wt\spec1-mgr`
  - SPEC 2: `track/adr-048-spec2-plot-tools`, `C:\Users\jiazh\Desktop\workspace\sci-wt\spec2-mgr`
  - SPEC 3: `track/adr-048-spec3-docs`, `C:\Users\jiazh\Desktop\workspace\sci-wt\spec3-mgr`
- Protected branch: `main`
- Umbrella PRs:
  - #1577 `[DO NOT MERGE] ADR-048 SPEC 1: extensible preview system`
  - #1580 `[DO NOT MERGE] ADR-048 SPEC 2: AI plot tools + preview-side plot jobs`
  - #1581 `[DO NOT MERGE] ADR-048 SPEC 3: developer docs delete-and-rewrite`
- Dispatch prompt record: `docs/planning/adr-048-pr-fix-dispatch-prompts.md`

## 2. Scope

- In scope:
  - SPEC 1 preview session/resource bugs and regression tests.
  - SPEC 2 plot MCP/path confinement bugs and regression tests.
  - SPEC 3 active skill/template drift and regression tests.
  - Refresh gate records for touched PR branches.
- Out of scope:
  - Merging any PR.
  - Broad architecture rewrites outside ADR-048 implementation surfaces.
  - Governance/gate fixes except issue #1584 if separately assigned.
- Protected paths:
  - `src/scistudio/qa/governance/**`
  - `.github/workflows/**`
  - `docs/ai-developer/**`
- Deferred work:
  - `TODO(#1584)` only if a local gate finalized-ledger hook deadlock blocks legal post-PR provenance commits.

## 3. Conventions

- `[ ]` not started
- `[~]` in progress
- `[x]` done
- `[!]` blocked
- Every completed row must include an artifact: commit, test command, report path, PR link, or gate-record event.
- Chat messages are not checklist evidence.
- Agents edit only their own rows and assigned PR branch/worktree.

## 4. Manager Preflight

- [x] Existing PR branches and worktrees identified -> `git worktree list`
- [x] Existing umbrella PRs recorded -> #1577, #1580, #1581
- [x] Owner-directed umbrella-PR deviation recorded -> this checklist
- [x] Smoke server PID 75468 stopped before dispatch -> `Stop-Process -Id 75468`
- [x] Dispatch checklist committed -> commit `89e9ea7f`
- [ ] Implementation agents dispatched.
- [ ] Implementation outputs reviewed.
- [ ] No-context audit agents dispatched after implementation commits are pushed.

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `N/A`
- Owner authorization source: `N/A`
- Reason: `No bypass authorized for this repair pass. If hooks fail due issue #1584, stop and report.`

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scistudio.qa.governance.gate_record check --mode pre-commit` | `N/A` | `[ ]` | Pending per branch |
| Commit message | `python -m scistudio.qa.governance.gate_record check --mode commit-msg` | `N/A` | `[ ]` | Pending per branch |
| Pre-push | `python -m scistudio.qa.governance.gate_record check --mode pre-push` | `N/A` | `[ ]` | Pending per branch |
| Pre-PR reconcile | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file <body-file>` | `N/A` | `[ ]` | Pending per branch |

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| SPEC1-FIX | implementer | N/A | `docs/planning/adr-048-pr-fix-dispatch-prompts.md#spec1-fix` | Preview resource params, plot export, focused regressions | `track/adr-048-spec1-preview-system` | `sci-wt/spec1-mgr` | Preview session/API/frontend/tests/docs as needed | SPEC2/SPEC3/gate governance | #1574/#1577 | `[ ]` |
| SPEC2-FIX | implementer | N/A | `docs/planning/adr-048-pr-fix-dispatch-prompts.md#spec2-fix` | Plot path confinement, workflow_path traversal, stale artifact/dynamic targets as feasible | `track/adr-048-spec2-plot-tools` | `sci-wt/spec2-mgr` | Plot MCP/runtime/tests/docs as needed | SPEC1/SPEC3/gate governance | #1575/#1580 | `[ ]` |
| SPEC3-FIX | implementer | N/A | `docs/planning/adr-048-pr-fix-dispatch-prompts.md#spec3-fix` | Active skill/template drift, docs contract tests | `track/adr-048-spec3-docs` | `sci-wt/spec3-mgr` | Packaged skills/templates/docs tests | SPEC1/SPEC2 runtime/gate governance | #1576/#1581 | `[ ]` |
| SPEC1-AUDIT | audit_reviewer | no-context | `docs/planning/adr-048-pr-fix-dispatch-prompts.md#spec1-audit-no-context` | No-context preview-system audit | TBD | TBD | Audit report only | Manager context/PR claims | #1574/#1577 | `[ ]` |
| SPEC2-AUDIT | audit_reviewer | no-context | `docs/planning/adr-048-pr-fix-dispatch-prompts.md#spec2-audit-no-context` | No-context plot-tools audit | TBD | TBD | Audit report only | Manager context/PR claims | #1575/#1580 | `[ ]` |
| SPEC3-AUDIT | audit_reviewer | no-context | `docs/planning/adr-048-pr-fix-dispatch-prompts.md#spec3-audit-no-context` | No-context developer-docs audit | TBD | TBD | Audit report only | Manager context/PR claims | #1576/#1581 | `[ ]` |

## 7. Track Status

### SPEC 1

- [ ] Child resource params propagated from frontend/API to session manager.
- [ ] Plot `export` resource either implemented end-to-end or removed from advertised resources with docs/tests aligned.
- [ ] Regression tests added for child resources and plot export behavior.
- [ ] Gate record refreshed for #1577.
- [ ] Commit pushed to `track/adr-048-spec1-preview-system`.

### SPEC 2

- [ ] `read_plot_source` and `run_plot_job` enforce plot script confinement.
- [ ] `list_plot_targets(workflow_path=...)` enforces project-root confinement.
- [ ] Regression tests added for path traversal rejection.
- [ ] High-risk stale artifact / dynamic target issues fixed or tracked with repository TODO and issue reference.
- [ ] Gate record refreshed for #1580.
- [ ] Commit pushed to `track/adr-048-spec2-plot-tools`.

### SPEC 3

- [x] Active skill docs updated for `preview_data` signature. -> `scistudio-inspect-data`, `scistudio-build-workflow`; `python -m pytest tests\docs\test_block_development_docs.py -q --no-cov`
- [x] Active skill docs updated for `get_block_output` signature/return envelope. -> `scistudio-inspect-data`, `scistudio-debug-run`, `scistudio-build-workflow`; `python -m pytest tests\docs\test_block_development_docs.py -q --no-cov`
- [x] Entry-point examples updated to callable factory contract. -> `scistudio-write-block`; `python -m pytest tests\docs\test_block_development_docs.py -q --no-cov`
- [x] Forbidden editable-install template guidance removed. -> `src/scistudio/cli/templates/block_package/README.md.tpl`; `python -m pytest tests\cli\test_new_block_package.py -q --no-cov`
- [x] Contract regression tests added. -> `tests/docs/test_block_development_docs.py`; `ruff check tests\docs\test_block_development_docs.py`
- [!] Gate record refreshed for #1581. -> `.workflow/records/1576-track-adr-048-spec3-docs.json`; full `gate_record check --mode pre-pr --base origin/track/adr-048-spec2-plot-tools --head HEAD --pr-body-file .workflow/local/pr-body.md` ran and remains blocked by broad `python_tests` failures (12 failed, 4342 passed in latest completed log).
- [ ] Commit pushed to `track/adr-048-spec3-docs`.

## 8. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| SPEC 1 targeted tests | TBD by SPEC1-FIX | `[ ]` | Pending |
| SPEC 2 targeted tests | TBD by SPEC2-FIX | `[ ]` | Pending |
| SPEC 3 targeted tests | `ruff check tests\docs\test_block_development_docs.py`; `python -m pytest tests\docs\test_block_development_docs.py -q --no-cov`; `python -m pytest tests\cli\test_new_block_package.py -q --no-cov`; `python -m pytest tests\packaging\test_wheel_skills.py tests\agent_provisioning\test_skills.py -q --no-cov` | `[x]` | All focused SPEC3 checks passed locally. |
| SPEC 1 no-context audit | TBD | `[ ]` | Pending |
| SPEC 2 no-context audit | TBD | `[ ]` | Pending |
| SPEC 3 no-context audit | TBD | `[ ]` | Pending |

## 9. Drift Log

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| 2026-06-11 | manager | Existing PRs already serve as DO NOT MERGE umbrella PRs; no new umbrella PR opened. | Recorded as owner-directed deviation. | N/A |

## 10. Final Readiness

- [ ] All implementation agents finished.
- [ ] All implementation commits pushed.
- [ ] CI status checked for #1577, #1580, #1581.
- [ ] Three no-context audit reports completed and committed.
- [ ] Manager reviewed changed files and audit findings.
- [ ] Remaining blockers reported to owner.
