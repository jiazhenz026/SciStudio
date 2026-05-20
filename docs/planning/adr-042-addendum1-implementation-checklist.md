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

- [x] Add `ADRAddendumFrontmatter` and loader support for standalone `ADR-NNN-addendumM.md` files. [ADR-042 Addendum 1 Section 3; Spec User Story 2] Result: `python -m scieasy.qa.audit.frontmatter_lint docs/adr/ADR-042-addendum1.md` passed with `PYTHONPATH=src`.
- [x] Update `frontmatter_lint` filename/H1/Decision Summary checks for addenda without weakening ordinary ADR checks. [Spec FR-001..FR-003] Result: `pytest tests/qa/test_audit_frontmatter_lint.py --timeout=60 --no-cov` passed 15 tests with `PYTHONPATH=src`.
- [x] Add or update tests in `tests/qa/test_audit_frontmatter_lint.py` for valid and invalid addenda. Result: valid addendum, malformed filename, mismatched addendum number, missing addendum number, wrong H1, unresolved detail section, and loader selection cases covered.
- [ ] Add `ArchitectureFrontmatter` and include `docs/architecture/ARCHITECTURE.md` in repo-wide `frontmatter_lint` checks. [Spec User Story 2a; FR-002a]
- [ ] Validate architecture document H1 against frontmatter title and reject missing owner/governed ADR metadata.

### Verification

- [!] `pytest tests/qa/test_audit_frontmatter_lint.py --timeout=60` Result: test assertions passed, but the repository global coverage fail-under rejected this targeted run at 9%; rerun with `PYTHONPATH=src` and `--no-cov` passed 15 tests.

## Track B - Gate Record Core

Sub-issue: #1267

### Phase 2 Implementation (Owner: I-B)

- [ ] Add `.workflow/gate-record.schema.json` and `.workflow/records/.gitkeep`. [ADR-042 Addendum 1 Section 3]
- [ ] Implement `src/scieasy/qa/governance/gate_record.py` models and validators for six-stage records, scope/diff matching, PR issue-closing checks, full-audit evidence, Sentrux evidence hooks, exact override labels, and changed-test-file enforcement. [Spec User Stories 1, 4, 6, 9, 10]
- [ ] Implement the AI-facing CLI commands `start`, `plan`, `amend`, `docs`, `check`, `sentrux`, `finalize`, `pre-commit`, `commit-msg`, and `ci`. [ADR-042 Addendum 1 Section 3.1]
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

- [ ] Replace the legacy `.github/workflows/workflow-gate.yml` local-state check with committed gate-record validation; do not keep the old CI gate as a second authority. [ADR-042 Addendum 1 Sections 3 and 5]
- [ ] Update `.github/workflows/workflow-gate.yml` to validate committed gate records, PR closing keywords, hard-fail guards, full-audit evidence, Sentrux evidence, override labels, and changed tests. [ADR-042 Addendum 1 Sections 3 and 5]
- [ ] Update `.pre-commit-config.yaml` so gate interception calls `python -m scieasy.qa.governance.gate_record`, not `.workflow/gate.py`.
- [ ] Replace `scripts/hooks/check-gate-before-push.sh` with a thin wrapper around `python -m scieasy.qa.governance.gate_record pre-push` or the closest implemented gate-record validation command.
- [ ] Replace `scripts/hooks/check-gate-before-pr.sh` with a thin wrapper around `python -m scieasy.qa.governance.gate_record pr-ready` or the closest implemented gate-record validation command.
- [ ] Replace or remove `.workflow/hooks/pre-commit`; it must not reference `.workflow/gate.py` and must not read `.workflow/active`.
- [ ] Delete `.workflow/gate.py`.
- [ ] Remove all current executable hook/CI references to `.workflow/gate.py`, `gate.py status/list/advance`, and `.workflow/active`.
- [ ] Add tests in `tests/qa/test_gate_record_hooks.py` proving hook/wrapper behavior uses the gate-record CLI and does not require the deleted `gate.py`.
- [ ] Update `.gitignore` for conflict-prone generated gate/audit artifacts and document any canonical tracked-file migration. If `CHANGELOG.md` itself is made untracked, the PR must use `git rm --cached CHANGELOG.md` and adjust changelog gate semantics; do not rely on `.gitignore` alone for already tracked files.
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
