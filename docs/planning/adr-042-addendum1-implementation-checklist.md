# ADR-042 Addendum 1 Implementation Checklist

> Mandatory tracking doc. Every agent edits the rows it owns and only those rows.
> Drift = protocol violation.

## Conventions

- [ ] not started - [~] in progress - [x] done - [!] blocked
- Each completed row MUST append a PR, commit, or test link/result.
- Tracking branch: `track/adr-042/addendum1-gate-record`
- Umbrella issue: #1266
- Dependency: docs PR #1265 must merge before final integration to `main`.

## Manager Assumptions And Drift Log

- [~] Tracking branch is temporarily based on `origin/docs/adr-042-addendum` so workers can read the accepted addendum/spec before #1265 merges. Rebase to `origin/main` after #1265 lands.
- [ ] No worker may edit `docs/adr/ADR-042.md`; ADR-042 is locked.
- [ ] Any deferred behavior MUST use a tracked `TODO(#NNN)` per AGENTS.md section 7.6.

## Track A - ADR Addendum Frontmatter

Sub-issue: #1268

### Phase 2 Implementation (Owner: I-A)

- [ ] Add `ADRAddendumFrontmatter` and loader support for standalone `ADR-NNN-addendumM.md` files. [ADR-042 Addendum 1 Section 3; Spec User Story 2]
- [ ] Update `frontmatter_lint` filename/H1/Decision Summary checks for addenda without weakening ordinary ADR checks. [Spec FR-001..FR-003]
- [ ] Add or update tests in `tests/qa/test_audit_frontmatter_lint.py` for valid and invalid addenda.

### Verification

- [ ] `pytest tests/qa/test_audit_frontmatter_lint.py --timeout=60`

## Track B - Gate Record Core

Sub-issue: #1267

### Phase 2 Implementation (Owner: I-B)

- [ ] Add `.workflow/gate-record.schema.json` and `.workflow/records/.gitkeep`. [ADR-042 Addendum 1 Section 3]
- [ ] Implement `src/scieasy/qa/governance/gate_record.py` models and validators for six-stage records, scope/diff matching, PR issue-closing checks, full-audit evidence, Sentrux evidence hooks, exact override labels, and changed-test-file enforcement. [Spec User Stories 1, 4, 6, 9, 10]
- [ ] Export stable governance APIs from `src/scieasy/qa/governance/__init__.py`.
- [ ] Add tests in `tests/qa/test_gate_record.py` and `tests/qa/test_gate_record_ci.py`.

### Verification

- [ ] `pytest tests/qa/test_gate_record.py tests/qa/test_gate_record_ci.py --timeout=60`

## Track C - Existing Guard Orchestration

Sub-issue: #1271

### Phase 2 Implementation (Owner: I-C)

- [ ] Implement or complete ADR-042 guard modules without replacing their policy with gate-record-only checks: `issue_link`, `docs_landing`, `persona_policy`, `human_bypass_guard`, `core_change_guard`, and `pr_merge_guard`. [Spec User Stories 3, 7, 10]
- [ ] Reuse exact override labels: `human-authored`, `admin-approved:ai-override`, `admin-approved:core-change`, `admin-approved:merge`.
- [ ] Keep existing `mod_guard` and `weakened_ci_check` hard-fail semantics intact.
- [ ] Add tests in `tests/qa/test_issue_link.py`, `tests/qa/test_docs_landing.py`, `tests/qa/test_persona_policy.py`, `tests/qa/test_human_bypass_guard.py`, `tests/qa/test_core_change_guard.py`, and `tests/qa/test_pr_merge_guard.py`.

### Verification

- [ ] `pytest tests/qa/test_issue_link.py tests/qa/test_docs_landing.py tests/qa/test_persona_policy.py tests/qa/test_human_bypass_guard.py tests/qa/test_core_change_guard.py tests/qa/test_pr_merge_guard.py tests/qa/test_governance_mod_guard.py tests/qa/test_governance_weakened_ci_check.py --timeout=60`

## Track D - Sentrux Free-Tier Gate

Sub-issue: #1270

### Phase 2 Implementation (Owner: I-D)

- [ ] Implement `src/scieasy/qa/governance/sentrux_gate.py` parsing and free-tier honesty validation. [ADR-042 Addendum 1 Section 2; Spec User Story 5]
- [ ] Reject Pro-only or unchecked-rule claims even when free-tier check output is otherwise passing.
- [ ] Add tests in `tests/qa/test_sentrux_gate.py`.

### Verification

- [ ] `pytest tests/qa/test_sentrux_gate.py --timeout=60`

## Track E - Hooks And CI

Sub-issue: #1269

### Phase 2 Implementation (Owner: I-E)

- [~] Replace the legacy `.github/workflows/workflow-gate.yml` local-state check with committed gate-record validation; do not keep the old CI gate as a second authority. Bootstrap removes `.workflow/active` as CI authority and probes `gate_record ci` only when Track B makes it available; final mandatory validation remains under #1269. [ADR-042 Addendum 1 Sections 3 and 5]
- [!] Update `.github/workflows/workflow-gate.yml` to validate committed gate records, PR closing keywords, hard-fail guards, full-audit evidence, Sentrux evidence, override labels, and changed tests. Bootstrap preserves PR closing-keyword and changed-test checks, but full gate-record/guard/full-audit/Sentrux/label validation is blocked until Track B/C/D interfaces land; tracked by #1269. [ADR-042 Addendum 1 Sections 3 and 5]
- [ ] Update `.pre-commit-config.yaml` and add `scripts/hooks/check-gate-before-push.sh` and `scripts/hooks/check-gate-before-pr.sh` wrappers.
- [~] Update `.gitignore` for conflict-prone generated gate/audit artifacts and document any canonical tracked-file migration. Bootstrap ignores generated audit outputs and local gate scratch files; `CHANGELOG.md` remains tracked because changing its canonical status requires a separate gate semantics migration under #1269.
- [ ] Add tests in `tests/qa/test_gate_record_hooks.py`.
- [ ] Preserve human `--no-verify` and documented skip-all behavior; CI remains final enforcement.

### Verification

- [ ] `pytest tests/qa/test_gate_record_hooks.py --timeout=60`

## Manager E2E Checklist

- [ ] `ruff check .`
- [ ] `ruff format --check .`
- [ ] `pytest tests/qa --timeout=60`
- [ ] `python -m scieasy.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json`
- [ ] Sentrux MCP or CLI evidence captured when available.
- [ ] Implementation PR closes #1266 or explicitly closes all sub-issues.

## Acceptance Criteria

- [ ] All worker outputs reviewed and merged into `track/adr-042/addendum1-gate-record`.
- [ ] #1265 merged or tracking branch rebased onto `origin/main` with the addendum/spec present.
- [ ] Every changed implementation task includes changed tests.
- [ ] Exact override-label vocabulary is consistent across ADR addendum, spec, docs, code, tests, and CI.
- [ ] Full audit evidence is present; known debt is classified rather than hidden.
- [ ] Final PR body closes all listed issues.
