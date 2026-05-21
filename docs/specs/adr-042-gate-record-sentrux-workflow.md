---
spec_id: adr-042-gate-record-sentrux-workflow
title: "ADR-042 Gate Record And Sentrux Workflow Implementation Specification"
status: Draft
feature_branch: docs/adr-042-addendum
created: 2026-05-20
input: "Owner-approved ADR-042 Addendum 1: implement CI-reviewed gate records, required issue-closing PRs, QA full audit evidence, and Sentrux free-tier architecture checks."
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
related_specs:
  - adr-042-ai-governance-tools
  - adr-042-consistency-tools
  - adr-042-code-quality-tools
scope:
  in:
    - Standalone ADR addendum frontmatter and lint support.
    - Architecture document frontmatter and lint support for `docs/architecture/ARCHITECTURE.md`.
    - Committed gate record schema and validator.
    - Orchestration of ADR-042 custom hard-fail guards already defined for issue linkage, docs landing, persona policy, governance protection, and CI weakening.
    - Human bypass guard integration and contributor-facing bypass procedure.
    - Administrator override label consistency and provenance checks.
    - Mandatory changed-test-file enforcement for implementation-category tasks.
    - Six-stage gate workflow from ADR-042 Addendum 1.
    - Sentrux free-tier evidence collection and CI verification.
    - ADR-042 QA full audit evidence and technical-debt classification.
    - Architecture document truthfulness checks for code blocks, symbol names,
      module paths, and signatures in `docs/architecture/ARCHITECTURE.md`.
    - Local pre-commit, commit-msg, pre-push, and PR-create interception.
    - GitHub Actions workflow-gate updates.
    - "`.gitignore` handling for generated gate/audit artifacts and any explicit migration away from conflict-prone tracked workflow files."
    - "Removal of obsolete `.workflow/gate.py` and replacement of current hook references with the gate-record CLI."
  out:
    - Requiring Sentrux Pro or Pro-only diagnostics.
    - Replacing normal CI, branch protection, owner review, or GitHub issue tracking.
    - Replacing ADR-042 custom guard semantics with new gate-record-only checks.
    - Automatic application of GitHub labels or administrator approvals.
governs:
  modules:
    - scistudio.qa.governance
    - scistudio.qa.schemas.frontmatter
    - scistudio.qa.audit.frontmatter_lint
    - scistudio.qa.audit.architecture_drift
    - scistudio.qa.governance.gate_record
    - scistudio.qa.governance.sentrux_gate
    - scistudio.qa.governance.issue_link
    - scistudio.qa.governance.docs_landing
    - scistudio.qa.governance.persona_policy
    - scistudio.qa.governance.human_bypass_guard
    - scistudio.qa.governance.core_change_guard
    - scistudio.qa.governance.pr_merge_guard
    - scistudio.qa.governance.mod_guard
    - scistudio.qa.governance.weakened_ci_check
  contracts:
    - scistudio.qa.schemas.frontmatter.ADRAddendumFrontmatter
    - scistudio.qa.schemas.frontmatter.ArchitectureFrontmatter
    - scistudio.qa.audit.frontmatter_lint.lint_file
    - scistudio.qa.audit.architecture_drift.check
    - scistudio.qa.governance.gate_record.GateRecord
    - scistudio.qa.governance.gate_record.GateStage
    - scistudio.qa.governance.gate_record.CheckEvidence
    - scistudio.qa.governance.gate_record.SentruxEvidence
    - scistudio.qa.governance.gate_record.FullAuditEvidence
    - scistudio.qa.governance.gate_record.validate_gate_record
    - scistudio.qa.governance.gate_record.check_pre_commit
    - scistudio.qa.governance.gate_record.check_commit_msg
    - scistudio.qa.governance.gate_record.check_pr
    - scistudio.qa.governance.sentrux_gate.parse_sentrux_result
    - scistudio.qa.governance.sentrux_gate.verify_free_tier_claims
    - scistudio.qa.governance.issue_link.resolve_or_create
    - scistudio.qa.governance.docs_landing.check
    - scistudio.qa.governance.persona_policy.check
    - scistudio.qa.governance.human_bypass_guard.check
    - scistudio.qa.governance.core_change_guard.check
    - scistudio.qa.governance.pr_merge_guard.check
    - scistudio.qa.governance.mod_guard.check
    - scistudio.qa.governance.weakened_ci_check.verify_no_weakening
  files:
    - docs/specs/adr-042-gate-record-sentrux-workflow.md
    - docs/adr/ADR-042-addendum1.md
    - docs/architecture/ARCHITECTURE.md
    - src/scistudio/qa/schemas/frontmatter.py
    - src/scistudio/qa/audit/frontmatter_lint.py
    - src/scistudio/qa/audit/architecture_drift.py
    - src/scistudio/qa/audit/loaders.py
    - src/scistudio/qa/governance/gate_record.py
    - src/scistudio/qa/governance/sentrux_gate.py
    - src/scistudio/qa/governance/issue_link.py
    - src/scistudio/qa/governance/docs_landing.py
    - src/scistudio/qa/governance/persona_policy.py
    - src/scistudio/qa/governance/human_bypass_guard.py
    - src/scistudio/qa/governance/core_change_guard.py
    - src/scistudio/qa/governance/pr_merge_guard.py
    - src/scistudio/qa/governance/mod_guard.py
    - src/scistudio/qa/governance/weakened_ci_check.py
    - src/scistudio/qa/governance/__init__.py
    - tests/qa/test_gate_record.py
    - tests/qa/test_gate_record_hooks.py
    - tests/qa/test_gate_record_ci.py
    - tests/qa/test_sentrux_gate.py
    - tests/qa/test_audit_frontmatter_lint.py
    - tests/qa/test_issue_link.py
    - tests/qa/test_docs_landing.py
    - tests/qa/test_persona_policy.py
    - tests/qa/test_human_bypass_guard.py
    - tests/qa/test_core_change_guard.py
    - tests/qa/test_pr_merge_guard.py
    - .workflow/records/.gitkeep
    - .workflow/gate-record.schema.json
    - .gitignore
    - .pre-commit-config.yaml
    - .github/workflows/workflow-gate.yml
    - scripts/hooks/check-gate-before-pr.sh
    - scripts/hooks/check-gate-before-push.sh
    - docs/contributing/workflows/human-bypass.md
tests:
  - tests/qa/test_gate_record.py
  - tests/qa/test_gate_record_hooks.py
  - tests/qa/test_gate_record_ci.py
  - tests/qa/test_sentrux_gate.py
  - tests/qa/test_audit_frontmatter_lint.py
  - tests/qa/test_architecture_drift.py
  - tests/qa/test_issue_link.py
  - tests/qa/test_docs_landing.py
  - tests/qa/test_persona_policy.py
  - tests/qa/test_human_bypass_guard.py
  - tests/qa/test_core_change_guard.py
  - tests/qa/test_pr_merge_guard.py
acceptance_source: adr
language_source: en
---

# ADR-042 Gate Record And Sentrux Workflow Implementation Specification

## 1. Change Summary

This spec implements ADR-042 Addendum 1. The implementation first teaches
ADR-042 tooling to understand standalone addendum files such as
`docs/adr/ADR-042-addendum1.md`. It then replaces the ADR-042 local-only gate
model with committed gate records that CI validates against the pull request
diff.

The gate record is an evidence container and orchestration surface. It does not
replace ADR-042 custom guards. Existing ADR-042 guards such as `issue_link`,
`docs_landing`, `persona_policy`, `human_bypass_guard`,
`governance_mod_guard`, and `weakened_ci_check` remain the normative hard-fail
tools for their domains. The gate record records their inputs and results, and
CI re-runs or verifies those guards where possible.

The spec also makes Sentrux free-tier architecture evidence and ADR-042 QA full
audit evidence part of the gate.

The resulting workflow has six stages:

1. Scope And Issue.
2. Plan.
3. Implement.
4. Update Docs.
5. Test And Checks.
6. Commit And Submit PR.

The implementation must keep Sentrux free-tier limits explicit. Gate records
may claim only checks the installed tool actually executed. PRs must close every
issue listed in the gate record unless the record and PR body include an
owner-approved rationale for a non-closing follow-up reference.

The override label vocabulary is fixed by ADR-042 and ADR-042 Addendum 1:
`human-authored`, `admin-approved:ai-override`,
`admin-approved:core-change`, and `admin-approved:merge`. Implementation code,
CI, specs, and contributor docs must use these exact strings.

The implementation must also replace the legacy CI gate check. The old
`.workflow/active` local-state lookup in `.github/workflows/workflow-gate.yml`
must not remain as a parallel source of authority after committed gate records
are implemented. The old `.workflow/gate.py` command is obsolete and must be
deleted from the repository; current hooks and contributor instructions must
call `python -m scistudio.qa.governance.gate_record` instead.

Generated or local workflow artifacts that cause recurring branch conflicts
must be ignored where they are not canonical repository documentation. If an
already tracked canonical file such as `CHANGELOG.md` is intentionally moved out
of version control, the implementation must remove it from the index with
`git rm --cached` and update the gate semantics accordingly; adding an already
tracked file to `.gitignore` alone is not sufficient.

## 2. User Scenarios & Testing

### User Story 1 - Gate records are committed and CI-verifiable (Priority: P1)

As a maintainer, I need every AI-authored PR to include a committed gate record
that CI can compare with the PR diff.

Independent Test: Validate gate-record fixtures for a matching PR diff, missing
record, branch mismatch, unplanned file, denied path, and missing amendment.

Acceptance Scenarios:

1. Given a valid gate record and matching changed files, when CI validation
   runs, then the gate passes.
2. Given changed files outside `scope.include`, when CI validation runs, then
   the gate fails.
3. Given a governance file change with `governance_touch=false`, when CI
   validation runs, then the gate fails.

### User Story 2 - Standalone ADR addenda pass frontmatter lint (Priority: P1)

As a maintainer, I need accepted ADR addenda to live in separate files while
still being validated by ADR-042 frontmatter and first-section rules.

Independent Test: Run `frontmatter_lint.lint_file` against
`docs/adr/ADR-042-addendum1.md` and fixtures with invalid addendum filenames,
missing addendum numbers, wrong H1 titles, and unresolved problem sections.

Acceptance Scenarios:

1. Given `docs/adr/ADR-042-addendum1.md` with `adr: 42` and `addendum: 1`,
   when frontmatter lint runs, then it passes the addendum filename rule.
2. Given `docs/adr/ADR-042-addendum2.md` without `addendum: 2`, when lint runs,
   then it fails.
3. Given an addendum without `## 1. Decision Summary` or
   `### 1.1 Problems Addressed`, when lint runs, then it fails.

### User Story 2a - Architecture document frontmatter is audited (Priority: P1)

As a maintainer, I need the top-level architecture document to participate in
ADR-042 frontmatter audit so architecture metadata cannot drift outside the
quality gate.

Independent Test: Run `frontmatter_lint.lint_file` against
`docs/architecture/ARCHITECTURE.md` and fixtures with invalid `doc_type`,
missing owner, missing governed ADRs, and wrong H1.

Acceptance Scenarios:

1. Given `docs/architecture/ARCHITECTURE.md` with `doc_type: architecture`,
   when frontmatter lint runs, then it passes architecture metadata validation.
2. Given an architecture document without an owner, when lint runs, then it
   fails.
3. Given an architecture document whose H1 does not match the frontmatter title,
   when lint runs, then it fails.

### User Story 2b - Architecture document code truth is audited (Priority: P1)

As a maintainer, I need `docs/architecture/ARCHITECTURE.md` to be accurate when
it names repository modules, classes, functions, methods, or signatures.

Independent Test: Modify architecture-doc fixtures with stale function names,
wrong method signatures, missing modules, stale class names, and intentionally
non-normative examples.

Acceptance Scenarios:

1. Given an architecture document that references an existing module path and
   function signature, when architecture drift audit runs, then it passes.
2. Given an architecture document that changes an actual function signature to
   the wrong parameter list, when architecture drift audit runs, then it fails.
3. Given an architecture document that names a missing repository class or
   function in backticks or a code block, when audit runs, then it fails.
4. Given an illustrative example explicitly marked non-normative, when audit
   runs, then it is skipped.

### User Story 3 - Existing ADR-042 guards remain hard-fail (Priority: P1)

As a maintainer, I need the committed gate workflow to reuse ADR-042's existing
custom tools instead of redefining their policy in a parallel implementation.

Independent Test: Run gate-record validation with mocked or fixture outputs
from `issue_link`, `docs_landing`, `persona_policy`, `mod_guard`, and
`weakened_ci_check`.

Acceptance Scenarios:

1. Given `docs_landing.check` reports missing changelog or N/A rationale, when
   gate validation runs, then the gate fails.
2. Given `issue_link.resolve_or_create` cannot resolve an issue, when gate
   validation runs, then the gate fails.
3. Given `persona_policy.check` reports an unsupported persona or runtime
   policy, when gate validation runs, then the gate fails.
4. Given `mod_guard.check` or `weakened_ci_check.verify_no_weakening` reports a
   governance weakening, when CI validation runs, then the gate fails.

### User Story 4 - PRs close the issues they deliver (Priority: P1)

As a maintainer, I need completed work to close its issue so zombie issues do
not accumulate.

Independent Test: Validate PR-body fixtures with `Closes #N`, `Fixes #N`,
`Resolves #N`, plain references, multiple issues, and owner-approved follow-up
rationales.

Acceptance Scenarios:

1. Given a gate record listing issue `#1262`, when the PR body includes
   `Closes #1262`, then issue-closing validation passes.
2. Given the same record and a PR body that says `Refs #1262`, then validation
   fails.
3. Given multiple gate issues, when the PR body closes only one, then
   validation fails unless the non-closed issue has an owner-approved follow-up
   rationale in both the record and PR body.

### User Story 5 - Sentrux free-tier evidence is honest and repeatable (Priority: P1)

As a maintainer, I need architecture gate evidence that reflects the currently
available free-tier Sentrux tool, not unavailable Pro diagnostics.

Independent Test: Validate Sentrux evidence fixtures with pass/fail status,
`rules_checked`, `total_rules_defined`, `mode=free-tier`, and forbidden
Pro-only claims.

Acceptance Scenarios:

1. Given a source change and Sentrux free-tier pass evidence, when gate
   validation runs, then Sentrux validation passes.
2. Given a source change with missing Sentrux evidence, when gate validation
   runs, then validation fails.
3. Given evidence claiming Pro-only diagnostics, when validation runs, then it
   fails even if `check_rules` passed.

### User Story 6 - QA full audit evidence is present before PR readiness (Priority: P1)

As a maintainer, I need ADR-042 full audit evidence after docs are updated so
frontmatter, drift, facts, signatures, and closure problems are visible before
review.

Independent Test: Validate records with full-audit pass, known-debt findings,
missing full-audit output, and unclassified failures.

Acceptance Scenarios:

1. Given a gate record with full-audit output and no blocking findings, when CI
   validation runs, then full-audit evidence passes.
2. Given known findings classified under the technical-debt handling phase,
   when CI validation runs, then evidence is accepted but reported.
3. Given missing full-audit evidence, when CI validation runs, then validation
   fails.

### User Story 7 - Humans can use documented, reviewable bypasses (Priority: P1)

As a human maintainer, I need a clear procedure for bypassing AI-only local
hooks without bypassing repository quality checks or hiding the bypass from CI.

Independent Test: Validate `human_bypass_guard` fixtures for administrator
label provenance, invalid label actor, AI-authored commits with human-authored
labels, and approved one-off override labels.

Acceptance Scenarios:

1. Given a PR with a maintainer-applied `human-authored` label and no AI
   evidence, when CI runs, then AI-only gate checks are marked
   `skipped-human` and repository quality checks still run.
2. Given a PR with a `human-authored` label applied by an unauthorized actor,
   when CI runs, then `human_bypass_guard` fails.
3. Given a PR with AI-authored commits or `Assisted-by` trailers, when the PR
   only has `human-authored`, then CI still requires normal AI gate evidence or
   an explicit administrator override.

### User Story 8 - Local hooks catch mistakes before CI (Priority: P2)

As an AI agent or maintainer, I need local hooks to fail early before a bad PR
is opened.

Independent Test: Run hook fixtures for pre-commit, commit-msg, pre-push, and
PR-create wrappers.

Acceptance Scenarios:

1. Given staged files outside scope, when pre-commit runs, then it fails.
2. Given a commit message missing `Gate-Record`, when commit-msg runs, then it
   fails.
3. Given a PR-create command with missing docs landing or issue-closing
   evidence, when the wrapper runs, then it fails.

### User Story 9 - Implementation tasks include changed tests (Priority: P1)

As a maintainer, I need feature, bugfix, hotfix, refactor, and implementation
maintenance work to include test changes, not only claims that existing tests
were run.

Independent Test: Validate PR-diff fixtures for implementation-category tasks
with source changes and no test changes, source changes with added tests, docs
tasks with no tests, and owner-approved human-authored bypasses.

Acceptance Scenarios:

1. Given a feature task that changes `src/` and no `tests/` or package test
   files, when CI gate validation runs, then it fails.
2. Given a bugfix task that changes source and adds a regression test, when CI
   gate validation runs, then it passes the changed-test-file requirement.
3. Given a docs task with no implementation files changed, when CI gate
   validation runs, then the changed-test-file requirement is not applicable.

### User Story 10 - Override labels are consistent (Priority: P1)

As a maintainer, I need bypass and administrator approval labels to use one
fixed vocabulary across docs, code, tests, and CI.

Independent Test: Validate label fixtures for `human-authored`,
`admin-approved:ai-override`, `admin-approved:core-change`,
`admin-approved:merge`, misspelled labels, and unauthorized label actors.

Acceptance Scenarios:

1. Given a PR with `admin-approved:core-change` applied by an authorized
   maintainer, when protected core validation runs, then the label is accepted.
2. Given a PR with `admin-approved:corechange`, when validation runs, then the
   label is ignored and the protected change fails.
3. Given a PR with `admin-approved:merge` applied by an unauthorized actor, when
   merge guard validation runs, then it fails.

## 3. Functional Requirements

- FR-001: The implementation MUST add `ADRAddendumFrontmatter` or equivalent
  support for standalone ADR addendum files named `ADR-NNN-addendumM.md`.
- FR-002: `frontmatter_lint` MUST validate addendum filenames, H1 titles,
  `## 1. Decision Summary`, `### 1.1 Problems Addressed`, and detailed-section
  references.
- FR-002a: `frontmatter_lint` MUST validate
  `docs/architecture/ARCHITECTURE.md` with an architecture frontmatter schema,
  include it in repo-wide checks, and fail when architecture metadata or H1
  structure is invalid.
- FR-002b: The implementation MUST add architecture drift checks for
  `docs/architecture/ARCHITECTURE.md` that validate code blocks, referenced
  repository module paths, class names, function names, method names, and
  signatures against generated code facts.
- FR-002c: Architecture examples are normative by default. The checker MAY skip
  examples only when the surrounding prose or fence metadata explicitly marks
  the example as non-normative, illustrative, or pseudocode.
- FR-002d: Architecture drift findings MUST be included in full audit and MUST
  block CI when `docs/architecture/ARCHITECTURE.md` changes unless classified as
  known debt during the technical-debt phase.
- FR-003: The implementation MUST define a Pydantic-backed `GateRecord` schema
  stored as JSON under `.workflow/records/`.
- FR-004: Gate record validation MUST call or consume the existing ADR-042
  `issue_link.resolve_or_create`, `docs_landing.check`, `persona_policy.check`,
  `human_bypass_guard.check`, `mod_guard.check`, and
  `weakened_ci_check.verify_no_weakening` contracts where their domains apply.
- FR-005: Failures from those existing ADR-042 guards MUST be hard-fail gate
  findings. The gate-record implementation MUST NOT downgrade them to advisory
  findings.
- FR-006: Gate records MUST include stage data for Scope And Issue, Plan,
  Implement, Update Docs, Test And Checks, and Commit And Submit PR.
- FR-007: Scope validation MUST compare staged files locally and PR changed
  files in CI against `scope.include`, `scope.exclude`, and amendments.
- FR-008: Gate records MUST include issue numbers and URLs before implementation
  is committable.
- FR-009: PR validation MUST require GitHub closing keywords for every gate
  issue, unless an owner-approved follow-up rationale is present.
- FR-010: Gate records MUST include docs landing evidence before Test And Checks.
- FR-011: Gate records MUST include ADR-042 full audit evidence when
  `python -m scistudio.qa.audit.full_audit` is available.
- FR-012: During the technical-debt phase, full-audit findings MAY be accepted
  only when classified as known debt in the gate record.
- FR-013: Sentrux evidence MUST be required for source, package, workflow,
  architecture, governance, and `.sentrux/rules.toml` changes.
- FR-014: Sentrux evidence MUST declare `mode="free-tier"` and
  `pro_required=false`.
- FR-015: Sentrux validation MUST reject records that claim Pro-only diagnostics
  or unchecked rules as completed.
- FR-016: CI MUST re-run gate validation from repository state and PR metadata;
  local evidence is not authoritative.
- FR-017: Commit-message validation MUST require `Gate-Record`, `Task-Kind`,
  `Issue`, and `Assisted-by` trailers for AI-authored commits.
- FR-018: Existing `.workflow/gate.py` MUST be deleted. No current hook, CI
  workflow, or agent instruction may call it after this implementation.
- FR-019: The implementation MUST add a human-facing bypass procedure under
  `docs/contributing/workflows/human-bypass.md`.
- FR-020: Human bypass documentation MUST state that human maintainers may skip
  all local hooks, list the recommended human check set, explain how to request
  the `human-authored` label, and state that final code quality is decided by
  ordinary PR review and repository CI. An authorized `human-authored` PR may
  skip ADR-042 workflow-gate enforcement entirely because humans are allowed to
  change rules, protected core, and governance files when administrators approve
  the PR for merge.
- FR-021: The implementation MUST use these exact override labels:
  `human-authored`, `admin-approved:ai-override`,
  `admin-approved:core-change`, and `admin-approved:merge`.
- FR-022: `human_bypass_guard`, `core_change_guard`, and `pr_merge_guard` MUST
  validate label provenance and MUST reject misspelled, missing, or
  unauthorized labels.
- FR-023: Implementation-category tasks that change implementation files MUST
  add or modify at least one test file in the same PR.
- FR-024: Changed-test-file enforcement MUST apply to feature, bugfix, hotfix,
  refactor, and maintenance tasks that touch source, package, frontend,
  workflow, gate, or governance implementation files.
- FR-025: `gate_record` MUST expose the AI-facing CLI commands `start`, `plan`,
  `amend`, `docs`, `check`, `sentrux`, `finalize`, `pre-commit`,
  `commit-msg`, `pre-push`, `pr-ready`, and `ci`.
- FR-026: The push and PR hook wrappers MUST call the gate-record CLI and MUST
  NOT inspect `.workflow/active` or call `.workflow/gate.py`.

## 4. Edge Cases

- EC-001: Documentation-only PRs may mark Sentrux N/A unless they modify
  architecture or governance rules.
- EC-002: Hotfix batches may list multiple issues; the PR must close each fixed
  issue.
- EC-003: A non-closed follow-up issue must be recorded as follow-up in both the
  gate record and PR body with owner-approved rationale.
- EC-004: Sentrux MCP may be unavailable locally; the gate record must state the
  fallback and CI must run CLI validation where the CLI is configured.
- EC-005: Full audit may return known technical debt during rollout; the record
  must classify it instead of omitting the audit.
- EC-006: A PR that changes gate, CI, Sentrux, or governance rules must set
  `governance_touch=true` and pass weakening checks.
- EC-007: Human-authored PR bypass semantics still follow ADR-042 Section 9.
  An administrator-applied `human-authored` label is a skip-all signal for
  ADR-042 workflow-gate enforcement. Ordinary repository CI jobs and
  administrator PR review still decide whether the PR may merge.
- EC-008: If an existing ADR-042 guard has not yet been implemented, the gate
  implementation must record that as a tracked implementation gap instead of
  silently replacing the guard with weaker bespoke logic.
- EC-009: Human maintainers may use `git commit --no-verify` or equivalent
  skip-all local behavior. The PR still needs the administrator-applied
  `human-authored` label or another approved administrator override for AI-only
  CI bypass semantics.
- EC-010: Running an existing test suite is not enough for implementation
  tasks. The PR diff must include a changed test file.
- EC-011: Docs-only and planning-only tasks are exempt from changed-test-file
  enforcement unless they also touch implementation files.

## 5. Implementation Plan

### 5.1 Technical Approach

Implement gate records as repository-visible JSON files validated by Pydantic
models in `scistudio.qa.governance.gate_record`. The module exposes local hook
entry points and CI validation entry points that share the same schema and
scope-checking logic.

`gate_record` is an orchestrator. It delegates domain-specific policy to the
ADR-042 custom tools already designed for that purpose:

| Domain | Existing tool | Gate behavior |
|---|---|---|
| Issue linkage | `issue_link.resolve_or_create` | Hard-fail when issue linkage is missing or invalid |
| Docs landing | `docs_landing.check` | Hard-fail when docs/changelog/checklist evidence or N/A rationale is missing |
| Persona/runtime policy | `persona_policy.check` | Hard-fail when persona, runtime config, root policy, or skill pointers are invalid |
| Human bypass provenance | `human_bypass_guard.check` | Hard-fail invalid `human-authored` or administrator override provenance |
| Protected core changes | `core_change_guard.check` | Hard-fail protected core changes without `admin-approved:core-change` or equivalent administrator review |
| Merge automation | `pr_merge_guard.check` | Hard-fail AI merge automation without `admin-approved:merge` |
| Governance modification | `mod_guard.check` | Hard-fail unauthorized governance changes |
| CI/test weakening | `weakened_ci_check.verify_no_weakening` | Hard-fail weakened checks, thresholds, or exemptions |

If one of these tools is not implemented when this spec is implemented, the PR
must either implement that tool according to its existing ADR-042 spec or record
a tracked implementation issue. The gate must not replace it with a weaker
parallel check.

Add `scistudio.qa.governance.sentrux_gate` for narrow Sentrux evidence parsing and
free-tier claim validation. This module does not implement Sentrux; it validates
evidence produced by Sentrux MCP or CLI and rejects Pro-only claims.

CI validates gate records in `.github/workflows/workflow-gate.yml` after
checkout. The workflow validates full audit and Sentrux free-tier evidence
recorded during the gate Test and Checks stage. It does not require CI to rerun
local MCP sessions or Pro-only Sentrux diagnostics.

### 5.2 Affected Files

| File | Action | Purpose |
|---|---|---|
| `src/scistudio/qa/governance/gate_record.py` | create | Gate record schema, local checks, commit-message checks, PR validation |
| `src/scistudio/qa/governance/sentrux_gate.py` | create | Sentrux free-tier evidence parsing and validation |
| `src/scistudio/qa/governance/issue_link.py` | use/complete if missing | Existing ADR-042 issue-link hard-fail guard |
| `src/scistudio/qa/governance/docs_landing.py` | use/complete if missing | Existing ADR-042 docs/changelog/checklist hard-fail guard |
| `src/scistudio/qa/governance/persona_policy.py` | use/complete if missing | Existing ADR-042 persona/runtime hard-fail guard |
| `src/scistudio/qa/governance/human_bypass_guard.py` | use/complete if missing | Existing ADR-042 human bypass provenance guard |
| `src/scistudio/qa/governance/core_change_guard.py` | use/complete if missing | Existing ADR-042 protected core change guard |
| `src/scistudio/qa/governance/pr_merge_guard.py` | use/complete if missing | Existing ADR-042 AI merge guard |
| `src/scistudio/qa/governance/mod_guard.py` | use | Existing ADR-042 governance modification guard |
| `src/scistudio/qa/governance/weakened_ci_check.py` | use | Existing ADR-042 CI weakening guard |
| `src/scistudio/qa/schemas/frontmatter.py` | modify | Add standalone ADR addendum frontmatter schema support |
| `src/scistudio/qa/audit/frontmatter_lint.py` | modify | Accept and validate `ADR-NNN-addendumM.md` and `docs/architecture/ARCHITECTURE.md` |
| `src/scistudio/qa/audit/architecture_drift.py` | create | Validate architecture code blocks, symbols, module paths, and signatures against repository facts |
| `src/scistudio/qa/audit/full_audit.py` | modify | Include architecture drift as a child audit report |
| `src/scistudio/qa/audit/loaders.py` | modify | Load addendum and architecture frontmatter for audit/facts tools |
| `src/scistudio/qa/governance/__init__.py` | modify | Export gate-record public contracts |
| `.workflow/gate.py` | delete | Remove obsolete local-only gate state machine |
| `.workflow/gate-record.schema.json` | create | JSON Schema mirror for committed gate records |
| `.workflow/records/.gitkeep` | create | Keep committed gate-record directory present |
| `.gitignore` | modify | Ignore generated gate/audit artifacts and document tracked-file migration requirements |
| `.pre-commit-config.yaml` | modify | Add gate-record pre-commit and commit-msg hooks |
| `scripts/hooks/check-gate-before-push.sh` | modify | Block push when gate record is incomplete |
| `scripts/hooks/check-gate-before-pr.sh` | modify | Block PR creation when final gate evidence is incomplete |
| `.github/workflows/workflow-gate.yml` | modify | Replace legacy local-state gate check with gate record, closing issue, full audit, Sentrux, and weakening validation |
| `tests/qa/test_gate_record.py` | create | Schema and scope validation tests |
| `tests/qa/test_gate_record_hooks.py` | create | Pre-commit and commit-msg behavior tests |
| `tests/qa/test_gate_record_ci.py` | create | PR body, issue closing, diff matching, technical-debt phase tests |
| `tests/qa/test_sentrux_gate.py` | create | Free-tier Sentrux evidence tests |
| `tests/qa/test_audit_frontmatter_lint.py` | modify | Add standalone ADR addendum lint cases |
| `tests/qa/test_architecture_drift.py` | create | Architecture code truthfulness and skip-marker tests |
| `tests/qa/test_issue_link.py` | use/complete if missing | Existing issue-link guard coverage |
| `tests/qa/test_docs_landing.py` | use/complete if missing | Existing docs-landing guard coverage |
| `tests/qa/test_persona_policy.py` | use/complete if missing | Existing persona-policy guard coverage |
| `tests/qa/test_human_bypass_guard.py` | use/complete if missing | Existing human-bypass provenance coverage |
| `tests/qa/test_core_change_guard.py` | use/complete if missing | Existing protected-core approval coverage |
| `tests/qa/test_pr_merge_guard.py` | use/complete if missing | Existing AI merge guard coverage |
| `docs/contributing/workflows/human-bypass.md` | create | Step-by-step human bypass procedure |

### 5.3 Module Contracts

`GateRecord` fields:

- `schema_version`;
- `record_path`;
- `task_id`;
- `task_kind`;
- `branch`;
- `owner_directive`;
- `issues`;
- `scope`;
- `governance_touch`;
- `planned_files`;
- `changed_test_paths`;
- `admin_labels`;
- `amendments`;
- `docs_landing`;
- `required_checks`;
- `check_results`;
- `sentrux`;
- `full_audit`;
- `commit`;
- `pull_request`.

`CheckEvidence` fields:

- `name`;
- `command_or_tool`;
- `status`;
- `exit_code`;
- `timestamp`;
- `output_path`;
- `summary`;

`SentruxEvidence` fields:

- `mode`;
- `command_or_tool`;
- `status`;
- `rules_checked`;
- `total_rules_defined`;
- `quality_signal`;
- `thresholds`;
- `pro_required`;
- `output_path`;

`FullAuditEvidence` fields:

- `command`;
- `status`;
- `exit_code`;
- `output_path`;
- `blocks_merge`;
- `known_debt`;
- `unclassified_failures`;

### 5.4 Hook Configuration

`.pre-commit-config.yaml` must add:

- `scistudio-gate-record-pre-commit`: runs
  `python -m scistudio.qa.governance.gate_record pre-commit --staged`.
- `scistudio-gate-record-commit-msg`: runs
  `python -m scistudio.qa.governance.gate_record commit-msg`.

The pre-commit hook is intentionally lightweight. If no gate record is present
yet, it reports a non-blocking skip so agents and humans can iterate through
commits before the final gate record is complete. If a gate record is present,
it validates staged files against `scope.include`, `scope.exclude`, and
`governance_touch`. It does not require changed-test-file evidence, docs
landing, Sentrux evidence, QA full audit evidence, or all six stages to be
complete.

The commit-msg hook checks `Gate-Record`, `Task-Kind`, `Issue`, and
`Assisted-by` trailers.

`scripts/hooks/check-gate-before-push.sh` must call
`python -m scistudio.qa.governance.gate_record pre-push` and enforce final gate
semantics before allowing `git push`: a gate record must exist, every gate
stage except `commit_and_submit_pr` must be complete,
implementation-category work must include changed tests, required full audit
and Sentrux evidence must be recorded, and changed files must remain in scope.

`scripts/hooks/check-gate-before-pr.sh` must call
`python -m scistudio.qa.governance.gate_record pr-ready` and enforce the same
final gate semantics (every gate stage except `commit_and_submit_pr` complete,
full audit and Sentrux evidence recorded, changed files in scope), plus
closing issue text and PR provenance. Hook behavior must not depend on
branch-name special cases such as `hotfix/*`; task behavior is declared by
`gate_record start --task-kind ...`.

The `commit_and_submit_pr` stage is intentionally excluded from `pre-push` and
`pr-ready` because it is only set to `done` by `gate_record finalize`, which
requires a commit SHA and PR URL. The PR URL exists only after `gh pr create`,
which is itself gated by `pr-ready`; requiring the stage at `pre-push` or
`pr-ready` would create an unsolvable chicken-and-egg loop. CI runs after the
PR exists and `finalize` should have been called, so CI continues to require
every stage to be `done` including `commit_and_submit_pr`.

All local intermediate hooks that can block PR submission must accept the four
ADR-042 override labels as local-only bypass inputs: `human-authored`,
`admin-approved:ai-override`, `admin-approved:core-change`, and
`admin-approved:merge`. The `gate_record` CLI must expose `--bypass-label` for
`pre-commit`, `commit-msg`, and `pre-push`, and `--pr-label` for `pr-ready`.
It must also read `SCISTUDIO_GATE_BYPASS_LABELS`. The pre-push wrapper should
read labels from an existing PR with `gh pr view` when available; the PR-create
wrapper should parse `gh pr create --label/-l`. These bypasses allow the PR to
be submitted for review; CI still runs and remains authoritative.

### 5.5 CI Configuration

`.github/workflows/workflow-gate.yml` must add or replace steps with:

1. Remove the legacy `.workflow/active` branch-state lookup as a CI authority.
2. Discover gate records changed in the PR.
3. Validate exactly one primary gate record for AI-authored task branches unless
   the PR is an approved human-authored bypass.
4. Fetch PR changed files, PR body, labels, label actor provenance, and review
   approval metadata.
5. Run:

```bash
python -m scistudio.qa.governance.gate_record ci \
  --gate-record .workflow/records/<record>.json \
  --base origin/${{ github.base_ref }} \
  --head HEAD \
  --pr-body "$PR_BODY"
```

6. Validate that the gate record includes full audit evidence produced by:
   `python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json`.
7. Validate Sentrux free-tier evidence recorded from the applicable Sentrux
   MCP/CLI check. CI does not require Sentrux Pro and must reject Pro-only
   claims.
8. Fail if Sentrux is applicable and no free-tier evidence is recorded, unless
   the owner explicitly marks the PR as part of the tool-install bootstrap
   issue.
9. Fail if PR body does not close every gate-record issue.
10. Fail if full audit evidence is missing, or if unclassified full-audit
   failures remain after the technical-debt handling phase.
11. Fail if an implementation-category task changes implementation files
    without changed test files.
12. Fail if override labels are misspelled, missing, or applied by unauthorized
    actors. The only valid override labels are `human-authored`,
    `admin-approved:ai-override`, `admin-approved:core-change`, and
    `admin-approved:merge`.

### 5.6 Implementation Sequence

1. Add standalone ADR addendum frontmatter and lint support.
2. Add `GateRecord`, evidence models, and fixture tests.
3. Wire existing ADR-042 hard-fail guards into gate-record validation:
   `issue_link`, `docs_landing`, `persona_policy`, `human_bypass_guard`,
   `core_change_guard`, `pr_merge_guard`, `mod_guard`, and
   `weakened_ci_check`.
4. Add scope and PR-body validation, including issue-closing enforcement.
5. Add changed-test-file enforcement for implementation-category tasks.
6. Add override-label vocabulary and provenance tests.
7. Add Sentrux evidence validation.
8. Add full-audit evidence validation with known-debt classification support.
9. Add CLI subcommands for `start`, `plan`, `amend`, `docs`, `check`,
   `sentrux`, `finalize`, `pre-commit`, `commit-msg`, and `ci`.
10. Delete `.workflow/gate.py` and remove all current hook/CI references to it.
11. Wire `.pre-commit-config.yaml` hooks.
12. Update `.gitignore` for generated gate/audit artifacts and explicitly
    migrate any tracked canonical conflict-prone file before treating it as
    ignored.
13. Update shell wrappers for push and PR creation.
14. Replace the legacy GitHub Actions workflow-gate job with gate-record
    validation.
15. Add `docs/contributing/workflows/human-bypass.md`.
16. Add migration documentation in gate-record command help and PR template text
   if needed.

### 5.7 Verification Plan

Run:

```bash
pytest tests/qa/test_gate_record.py
pytest tests/qa/test_gate_record_hooks.py
pytest tests/qa/test_gate_record_ci.py
pytest tests/qa/test_sentrux_gate.py
pytest tests/qa/test_audit_frontmatter_lint.py
pytest tests/qa/test_issue_link.py
pytest tests/qa/test_docs_landing.py
pytest tests/qa/test_persona_policy.py
pytest tests/qa/test_human_bypass_guard.py
pytest tests/qa/test_core_change_guard.py
pytest tests/qa/test_pr_merge_guard.py
ruff check src/scistudio/qa/governance tests/qa/test_gate_record*.py tests/qa/test_sentrux_gate.py
ruff format --check src/scistudio/qa/governance tests/qa/test_gate_record*.py tests/qa/test_sentrux_gate.py
python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json
```

When Sentrux is available locally, also run:

```bash
sentrux scan .
sentrux check .
```

## 6. Risks And Rollback

| Risk | Mitigation |
|---|---|
| CI cannot install Sentrux free CLI reliably | Treat installation as part of the first implementation PR and fail applicable checks rather than silently passing missing evidence |
| Full audit has known existing findings | Require evidence and classification during the technical-debt phase; hard-fail unclassified findings after baseline acceptance |
| Gate records become stale boilerplate | CI compares records against PR diff and fails mismatches |
| Agents forget to close issues | CI checks PR body closing keywords against gate-record issues |
| Human maintainers bypass all hooks with `--no-verify` | Document that this is allowed for humans and make PR review plus CI the final quality decision |
| Existing `.workflow/gate.py` conflicts with the new model | Delete `.workflow/gate.py`; current hooks and CI must call `gate_record` instead |
| Conflict-prone generated artifacts create repeated merge conflicts | Ignore generated gate/audit artifacts; migrate already tracked canonical files explicitly before relying on ignore rules |

Rollback is limited to disabling the new CI gate job while preserving normal
CI, branch protection, and owner review. Rollback must not remove the gate
record files from already-open PRs; those remain audit artifacts.

## 7. Success Criteria

- SC-001: A valid AI-authored PR with a committed gate record passes local hook
  fixtures and CI gate validation.
- SC-002: A PR without a gate record fails CI.
- SC-003: A PR that references but does not close its gate issue fails CI.
- SC-004: A PR with source changes and missing Sentrux evidence fails CI.
- SC-005: A PR with missing QA full audit evidence fails CI.
- SC-006: Sentrux Pro-only claims are rejected.
- SC-007: Known full-audit technical debt can be reported without suppressing
  missing-evidence failures.

## 8. Assumptions

- Sentrux free-tier CLI or MCP is available to the implementation environment.
- Sentrux Pro is unavailable and not required.
- ADR-042 Addendum 1 is the governing source for this workflow.
- Human-authored bypass semantics remain governed by ADR-042 Section 9.
