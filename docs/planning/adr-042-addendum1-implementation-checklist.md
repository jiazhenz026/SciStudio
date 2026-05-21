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

- [x] Add `ADRAddendumFrontmatter` and loader support for standalone `ADR-NNN-addendumM.md` files. [ADR-042 Addendum 1 Section 3; Spec User Story 2] Result: `python -m scistudio.qa.audit.frontmatter_lint docs/adr/ADR-042-addendum1.md` passed with `PYTHONPATH=src`.
- [x] Update `frontmatter_lint` filename/H1/Decision Summary checks for addenda without weakening ordinary ADR checks. [Spec FR-001..FR-003] Result: `pytest tests/qa/test_audit_frontmatter_lint.py --timeout=60 --no-cov` passed 15 tests with `PYTHONPATH=src`.
- [x] Add or update tests in `tests/qa/test_audit_frontmatter_lint.py` for valid and invalid addenda. Result: valid addendum, malformed filename, mismatched addendum number, missing addendum number, wrong H1, unresolved detail section, and loader selection cases covered.
- [x] Add `ArchitectureFrontmatter` and include `docs/architecture/ARCHITECTURE.md` in repo-wide `frontmatter_lint` checks. [Spec User Story 2a; FR-002a] Result: `PYTHONPATH=src python -m scistudio.qa.audit.frontmatter_lint docs/architecture/ARCHITECTURE.md` passed; repo-wide command now includes architecture but still reports pre-existing non-Track-A ADR/spec frontmatter debt.
- [x] Validate architecture document H1 against frontmatter title and reject missing owner/governed ADR metadata. Result: architecture tests cover valid metadata, invalid `doc_type`, missing owner, wrong H1, repo `ARCHITECTURE.md`, and repo-wide `check()` inclusion.

### Verification

- [!] `pytest tests/qa/test_audit_frontmatter_lint.py --timeout=60` Result: test assertions passed, but the repository global coverage fail-under rejected this targeted run at 9%; rerun with `PYTHONPATH=src` and `--no-cov` passed 21 tests.

## Track A2 - Architecture Drift Audit

Sub-issue: #1278

### Phase 2 Implementation (Owner: I-A2)

- [x] Add `src/scistudio/qa/audit/architecture_drift.py` to validate `docs/architecture/ARCHITECTURE.md` code blocks, module paths, class names, function names, method names, and signatures against generated repository facts. [Spec User Story 2b; FR-002b; commit `763d52e1`; `PYTHONPATH=src PYTEST_ADDOPTS=--no-cov pytest tests/qa/test_architecture_drift.py tests/qa/test_audit_full_audit.py --timeout=60` -> 8 passed]
- [x] Treat architecture examples as normative by default; skip only examples explicitly marked non-normative, illustrative, or pseudocode. [FR-002c; `tests/qa/test_architecture_drift.py::test_architecture_drift_skips_explicit_non_normative_examples`]
- [x] Wire architecture drift into `src/scistudio/qa/audit/full_audit.py` as a child report. [FR-002d; `tests/qa/test_audit_full_audit.py` asserts child report rendering]
- [x] Add tests in `tests/qa/test_architecture_drift.py` for stale signature, missing symbol, missing module, valid reference, and explicit non-normative skip. [`ruff check` and `ruff format --check` passed on A2 files]

### Verification

- [x] `PYTHONPATH=src PYTEST_ADDOPTS=--no-cov pytest tests/qa/test_architecture_drift.py tests/qa/test_audit_full_audit.py --timeout=60` -> 8 passed.
- [!] Extra full audit smoke run: `PYTHONPATH=src python -m scistudio.qa.audit.full_audit --repo-root . --format json --output $TEMP/scistudio-a2-full-audit.json` exits 1 because the new architecture drift child reports existing `docs/architecture/ARCHITECTURE.md` findings; Track A2 scope forbids rewriting that document.

## Track B - Gate Record Core

Sub-issue: #1267

### Phase 2 Implementation (Owner: I-B)

- [x] Add `.workflow/gate-record.schema.json` and `.workflow/records/.gitkeep`. [ADR-042 Addendum 1 Section 3] Local result: files added on `feat/issue-1267/gate-record-core`.
- [x] Implement `src/scistudio/qa/governance/gate_record.py` models and validators for six-stage records, scope/diff matching, PR issue-closing checks, full-audit evidence, Sentrux evidence hooks, exact override labels, and changed-test-file enforcement. [Spec User Stories 1, 4, 6, 9, 10] Local result: `ruff check` passed for Track B files.
- [x] Implement the AI-facing CLI commands `start`, `plan`, `amend`, `docs`, `check`, `sentrux`, `finalize`, `pre-commit`, `commit-msg`, and `ci`. [ADR-042 Addendum 1 Section 3.1] Local result: CLI accepts both `--record` and `--gate-record`; `tests/qa/test_gate_record.py::test_ai_facing_cli_records_canonical_workflow` covers the canonical sequence.
- [x] Export stable governance APIs from `src/scistudio/qa/governance/__init__.py`. Local result: exports added for `GateRecord`, `GateStage`, evidence models, and validation entry points.
- [x] Add tests in `tests/qa/test_gate_record.py` and `tests/qa/test_gate_record_ci.py`. Local result: `PYTHONPATH=src PYTEST_ADDOPTS=--no-cov pytest tests/qa/test_gate_record.py tests/qa/test_gate_record_ci.py --timeout=60` passed, 18 tests.

### Verification

- [x] `PYTHONPATH=src PYTEST_ADDOPTS=--no-cov pytest tests/qa/test_gate_record.py tests/qa/test_gate_record_ci.py --timeout=60` -> 18 passed.

## Track C - Existing Guard Orchestration

Sub-issue: #1271

### Phase 2 Implementation (Owner: I-C)

- [x] Implement or complete ADR-042 guard modules without replacing their policy with gate-record-only checks: `issue_link`, `docs_landing`, `persona_policy`, `human_bypass_guard`, `core_change_guard`, and `pr_merge_guard`. [Spec User Stories 3, 7, 10] Test result: Track C pytest 35 passed with `PYTHONPATH=src PYTEST_ADDOPTS=--no-cov`.
- [x] Reuse exact override labels: `human-authored`, `admin-approved:ai-override`, `admin-approved:core-change`, `admin-approved:merge`. Test result: `ruff check` passed and `tests/qa/test_human_bypass_guard.py` passed in Track C suite.
- [x] Keep existing `mod_guard` and `weakened_ci_check` hard-fail semantics intact. Test result: `tests/qa/test_governance_mod_guard.py` and `tests/qa/test_governance_weakened_ci_check.py` passed in Track C suite.
- [x] Add tests in `tests/qa/test_issue_link.py`, `tests/qa/test_docs_landing.py`, `tests/qa/test_persona_policy.py`, `tests/qa/test_human_bypass_guard.py`, `tests/qa/test_core_change_guard.py`, and `tests/qa/test_pr_merge_guard.py`. Test result: Track C pytest 35 passed with `PYTHONPATH=src PYTEST_ADDOPTS=--no-cov`.

### Verification

- [x] `pytest tests/qa/test_issue_link.py tests/qa/test_docs_landing.py tests/qa/test_persona_policy.py tests/qa/test_human_bypass_guard.py tests/qa/test_core_change_guard.py tests/qa/test_pr_merge_guard.py tests/qa/test_governance_mod_guard.py tests/qa/test_governance_weakened_ci_check.py --timeout=60` - `PYTHONPATH=src PYTEST_ADDOPTS=--no-cov`: 35 passed. Exact sub-suite without `--no-cov` collected and passed 35 tests, then failed repository-wide coverage fail-under.

## Track D - Sentrux Free-Tier Gate

Sub-issue: #1270

### Phase 2 Implementation (Owner: I-D)

- [x] Implement `src/scistudio/qa/governance/sentrux_gate.py` parsing and free-tier honesty validation. [ADR-042 Addendum 1 Section 2; Spec User Story 5] Test: `pytest tests/qa/test_sentrux_gate.py --timeout=60 --no-cov` -> 8 passed.
- [x] Reject Pro-only or unchecked-rule claims even when free-tier check output is otherwise passing. Test: `pytest tests/qa/test_sentrux_gate.py --timeout=60 --no-cov` -> 8 passed.
- [x] Add tests in `tests/qa/test_sentrux_gate.py`. Test: `ruff check src/scistudio/qa/governance/sentrux_gate.py tests/qa/test_sentrux_gate.py` -> passed.

### Verification

- [x] `pytest tests/qa/test_sentrux_gate.py --timeout=60` collected 8 passing tests, then failed repository-wide coverage fail-under from global pytest addopts; behavior verification rerun with `PYTEST_ADDOPTS=--no-cov` -> 8 passed.

## Track E - Hooks And CI

Sub-issue: #1269

### Phase 2 Implementation (Owner: I-E)

- [x] Replace the legacy `.github/workflows/workflow-gate.yml` local-state check with committed gate-record validation; do not keep the old CI gate as a second authority. Final Track E workflow calls `gate_record ci`, orchestrates `issue_link`, `docs_landing`, `sentrux_gate`, `mod_guard`, and `weakened_ci_check`, and no longer probes `.workflow/active`. Local validation: YAML parse passed.
- [x] Update `.github/workflows/workflow-gate.yml` to validate committed gate records, PR closing keywords, hard-fail guards, full-audit evidence, Sentrux evidence, override labels, and changed tests. Result: `gate_record ci` enforces full audit, Sentrux, changed tests, override label vocabulary, closing issues, and all six stages done.
- [x] Update `.pre-commit-config.yaml` so gate interception calls `python -m scistudio.qa.governance.gate_record`, not `.workflow/gate.py`. Result: `tests/qa/test_gate_record_hooks.py` covers pre-commit and commit-msg hook entries.
- [x] Replace `scripts/hooks/check-gate-before-push.sh` with a thin wrapper around `python -m scistudio.qa.governance.gate_record pre-push` or the closest implemented gate-record validation command. Result: wrapper calls `gate_record pre-push`.
- [x] Replace `scripts/hooks/check-gate-before-pr.sh` with a thin wrapper around `python -m scistudio.qa.governance.gate_record pr-ready` or the closest implemented gate-record validation command. Result: wrapper calls `gate_record pr-ready` and requires PR closing keywords before PR creation.
- [x] Replace or remove `.workflow/hooks/pre-commit`; it must not reference `.workflow/gate.py` and must not read `.workflow/active`. Result: wrapper now delegates to `gate_record pre-commit --staged`.
- [x] Delete `.workflow/gate.py`. Result: `tests/qa/test_gate_record_hooks.py::test_legacy_gate_py_removed`.
- [x] Remove all current executable hook/CI references to `.workflow/gate.py`, `gate.py status/list/advance`, and `.workflow/active`. Result: `rg` over `.github .workflow scripts tests src` finds only test assertions and unrelated `sentrux_gate.py` token.
- [x] Add tests in `tests/qa/test_gate_record_hooks.py` proving hook/wrapper behavior uses the gate-record CLI and does not require the deleted `gate.py`. Result: `PYTHONPATH=src PYTEST_ADDOPTS=--no-cov pytest tests/qa/test_gate_record.py tests/qa/test_gate_record_ci.py tests/qa/test_gate_record_hooks.py --timeout=60` -> 25 passed.
- [~] Update `.gitignore` for conflict-prone generated gate/audit artifacts and document any canonical tracked-file migration. Bootstrap ignores generated audit outputs and local gate scratch files; `CHANGELOG.md` remains tracked because changing its canonical status requires a separate gate semantics migration under #1269. Bootstrap PR: #1277.
- [x] Preserve human `--no-verify` and documented skip-all behavior; CI remains final enforcement. Result: local pre-commit is lightweight and does not require a record before final push/PR; human `--no-verify` behavior remains documented in `docs/contributing/workflows/human-bypass.md`.
- [x] Avoid branch-name special cases for hotfix or other task kinds. Result: task behavior is declared by `gate_record start --task-kind`; local commit is lightweight for all task kinds, while push/PR/CI enforce final gate evidence for every AI-authored task.

### Verification

- [x] `PYTHONPATH=src PYTEST_ADDOPTS=--no-cov pytest tests/qa/test_gate_record.py tests/qa/test_gate_record_ci.py tests/qa/test_gate_record_hooks.py --timeout=60` -> 25 passed.

## Manager E2E Checklist

- [ ] `ruff check .`
- [ ] `ruff format --check .`
- [ ] `pytest tests/qa --timeout=60`
- [ ] `python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json`
- [ ] Sentrux MCP or CLI evidence captured when available.
- [ ] Implementation PR closes #1266 or explicitly closes all sub-issues.

## Acceptance Criteria

- [ ] All worker outputs reviewed and merged into `track/adr-042/addendum1-gate-record`.
- [ ] #1265 merged or tracking branch rebased onto `origin/main` with the addendum/spec present.
- [ ] Every changed implementation task includes changed tests.
- [ ] Exact override-label vocabulary is consistent across ADR addendum, spec, docs, code, tests, and CI.
- [ ] Full audit evidence is present; known debt is classified rather than hidden.
- [ ] Final PR body closes all listed issues.
