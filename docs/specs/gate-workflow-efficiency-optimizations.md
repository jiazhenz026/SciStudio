---
spec_id: gate-workflow-efficiency-optimizations
title: "Gate Workflow Efficiency Optimization Specification"
status: Draft
feature_branch: docs/gate-workflow-efficiency-spec
created: 2026-06-13
input: "Owner requested a planning spec for improving gate workflow efficiency after ADR-048 PR #1577 repair exposed repeated heavy checks, late scope failures, and inconsistent diff views."
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
related_specs:
  - adr-042-gate-ledger-runtime
scope:
  in:
    - Planned gate evaluator, CLI, hook, wrapper, and workflow efficiency changes.
    - Requirements that preserve issue linkage, committed ledger evidence, CI authority, Sentrux, governance checks, and branch protection.
    - Diff-view consistency, cheap reconciliation, check-result reuse, inherited-scope handling, wrapper/finalize consolidation, and CI status ownership.
    - Verification expectations for the eventual implementation.
  out:
    - Implementing the gate runtime changes in this docs-only spec.
    - Weakening required checks or changing protected branch policy.
    - Adding bypass labels or bypass paths.
    - Rewriting ADR-042 Addendum 6.
governs:
  modules:
    - scistudio.qa.governance
    - scistudio.qa.governance.gate_record
  contracts:
    - scistudio.qa.governance.gate_record.check
    - scistudio.qa.governance.gate_record.finalize
  entry_points:
    - python -m scistudio.qa.governance.gate_record
  files:
    - docs/specs/gate-workflow-efficiency-optimizations.md
    - docs/specs/adr-042-gate-ledger-runtime.md
    - docs/ai-developer/rules.md
    - docs/ai-developer/specific_rules/gated-workflow.md
    - scripts/scistudio_pr_create.py
    - scripts/hooks/**
    - src/scistudio/qa/governance/**
    - tests/qa/**
    - .github/workflows/**
  excludes: []
tests:
  - tests/qa/test_gate_record.py
  - tests/qa/test_gate_evaluator.py
  - tests/qa/test_gate_record_hooks.py
  - tests/scripts/test_scistudio_pr_create.py
acceptance_source: issue
language_source: en
---

# Gate Workflow Efficiency Optimization Specification

## 1. Change Summary

This spec defines planned efficiency improvements for the ADR-042 gate workflow
without reducing governance strength. It responds to issue #1646 and to the
observed ADR-048 PR #1577 repair workflow, where the final delivery path spent
substantial time on repeated heavy checks, late metadata failures, and different
diff interpretations between manual gate checks, commit hooks, finalize, the PR
wrapper, and CI.

The current system already protects important invariants: work is issue-linked,
scope is recorded, evidence is committed, CI remains authoritative, and
governance/quality checks block unsafe changes. The problem is execution order
and reuse. Cheap structural failures should appear before expensive checks.
Equivalent checks should not rerun when the source diff has not changed. Every
gate entry point should observe the same candidate unless the caller explicitly
asks for a different diff view.

This is a planning spec. It does not claim these optimizations are implemented.
The implementation must update the gate runtime, hooks, wrapper, tests, and AI
developer docs in a separate tracked issue or PR.

## 2. User Scenarios & Testing

### User Story 1 - Fail Fast Before Heavy Checks (Priority: P1)

As an AI agent or reviewer preparing a PR, I want gate scope, issue, governance,
PR-body, and evidence-shape errors reported before full test execution, so that
obvious metadata defects do not waste minutes of CI-equivalent runtime.

**Why this priority**: This is the highest observed waste. A full Tier 1 run can
complete and then fail on a missing scope include.

**Independent Test**: Create a fixture branch with an out-of-scope changed file
and a Tier 1 surface. `gate_record check --mode pre-pr` must fail before running
heavy commands such as pytest, frontend, semantic duplication, or mypy.

**Acceptance Scenarios**:

- Given a candidate with a changed file outside effective scope, when
  `gate_record check --mode pre-pr` runs, then it reports `scope.out-of-scope`
  during cheap reconciliation and does not execute heavyweight checks.
- Given a candidate missing `governance_touch=true` for governed docs, when the
  gate runs, then it reports that defect before running heavyweight checks.
- Given a candidate whose PR body does not close a ledger issue, when pre-PR
  validation runs, then it reports the closure defect before heavyweight checks.

### User Story 2 - Use Explicit Diff Views (Priority: P2)

As an AI agent working before commit, I want the gate command to clearly state
whether it is checking working tree, staged diff, committed HEAD, or PR base
diff, so that a clean result cannot hide dirty or staged changes.

**Why this priority**: The observed workflow produced misleading clean checks
when `--head HEAD` did not include uncommitted work.

**Independent Test**: Create dirty and staged fixture changes, run the gate with
each supported diff view, and verify the observed changed-file set and warnings.

**Acceptance Scenarios**:

- Given dirty unstaged files and a command that observes only `HEAD`, when the
  gate runs, then it warns that working-tree changes are excluded.
- Given staged files, when `--diff staged` runs, then the observed diff includes
  only staged files.
- Given a PR-on-feature-branch candidate, when `--diff target-base` runs, then
  the observed diff is computed against the declared PR base, not always
  `origin/main`.

### User Story 3 - Reuse Valid Check Evidence (Priority: P3)

As an AI agent iterating on ledger metadata, I want previously passed heavy
checks reused when the source diff and tool versions are unchanged, so that
fixing scope/docs metadata does not force a full re-run.

**Why this priority**: Re-running Tier 1 checks after metadata-only ledger
corrections is the largest avoidable time cost after fail-fast ordering.

**Independent Test**: Run a full check, change only ledger metadata that does
not alter source files or check obligations, then verify final readiness can
reuse valid check events for the same fingerprint.

**Acceptance Scenarios**:

- Given a valid `check_event` for `type_check` with the current source
  fingerprint and tool versions, when only scope metadata is amended, then final
  pre-PR reconciliation may reuse the `type_check` event.
- Given source files change after a check event, when final readiness runs, then
  only affected surfaces are invalidated.
- Given a tool version changes, when final readiness runs, then matching old
  check events are not reused.

### User Story 4 - Avoid PR-on-PR Scope Noise (Priority: P4)

As a manager repairing a feature PR with a child PR, I want the gate to separate
inherited base-branch changes from the repair PR's own diff, so that the repair
ledger does not need to claim ownership of upstream feature work.

**Why this priority**: Repair PRs into feature branches are common in this repo.
Scope noise weakens traceability because the repair ledger is forced to list
files it did not change.

**Independent Test**: Create a fixture feature branch with existing changes, then
create a child repair branch. Verify the repair ledger only owns child-branch
diff while CI can still evaluate the full PR-to-main context when needed.

**Acceptance Scenarios**:

- Given a child PR targeting a feature branch, when the gate checks repair scope,
  then inherited files from the feature branch are classified separately.
- Given CI needs full branch-to-main context, when it runs, then it can import
  inherited scope from the parent branch or mark it as inherited evidence without
  requiring the child ledger to own it.

### Edge Cases

- Dirty working tree plus staged changes must not be silently collapsed into one
  ambiguous diff.
- Check reuse must fail closed when a command, tool version, environment marker,
  or source fingerprint differs.
- Metadata-only ledger edits that change obligations must invalidate only
  affected reconciliation evidence, not unrelated source checks.
- Local-only log paths must remain uncommitted and sanitized summaries must stay
  repo-relative.
- CI final status must not require a follow-up commit that retriggers CI.

## 3. Requirements

### Functional Requirements

- **FR-001**: The gate evaluator MUST run a cheap reconciliation phase before
  any heavyweight command execution in `local`, `pre-push`, `pre-pr`, and
  wrapper preflight modes.
- **FR-002**: Cheap reconciliation MUST validate scope coverage,
  `governance_touch`, issue linkage, PR-body closure, docs/test obligations,
  protected-path authorization shape, and dirty/staged/HEAD ambiguity.
- **FR-003**: If cheap reconciliation finds a blocking defect, the evaluator
  MUST exit before running heavyweight checks and MUST print repair hints.
- **FR-004**: The gate CLI MUST support explicit diff-view selection or an
  equivalent unambiguous mode contract for working tree, staged, committed HEAD,
  and target-base diff.
- **FR-005**: The evaluator MUST warn when excluded dirty or staged changes
  exist for the selected diff view.
- **FR-006**: Check events MUST include enough identity to support safe reuse:
  check name, command identity, covered surface, source/input fingerprint,
  tool versions, environment marker, mode constraints, and result.
- **FR-007**: Final readiness MAY reuse existing check events only when all
  reuse identity fields match and the obligation set has not changed for that
  check.
- **FR-008**: `--skip-execution` or its replacement MUST distinguish recovery
  diagnostics from final-readiness reuse; final-readiness reuse is allowed only
  after validating all required check identities.
- **FR-009**: The evaluator MUST invalidate check evidence by covered surface,
  not by all-or-nothing branch state.
- **FR-010**: PR-on-feature-branch workflows MUST distinguish child-branch
  changed files from inherited target-branch files.
- **FR-011**: Commit hooks, manual gate commands, PR wrapper preflight,
  finalize, and CI MUST share the same evaluator and diff-view semantics.
- **FR-012**: The PR wrapper SHOULD support a consolidated flow that runs final
  preflight, creates the PR, performs post-PR finalize, and commits/pushes
  ledger provenance once.
- **FR-013**: CI final status MUST remain GitHub Actions state; docs/checklists
  MUST NOT require a post-green commit solely to record "CI passed".
- **FR-014**: The implementation MUST NOT weaken required checks, Sentrux,
  governance guards, issue closure, protected-path authorization, or committed
  gate evidence.
- **FR-015**: All new ledger/check summaries MUST remain sanitized and MUST NOT
  commit raw transcripts, absolute local paths, environment dumps, or local user
  details.

### Key Entities

| Entity | Description | Attributes | Relationships |
|---|---|---|---|
| `DiffView` | Explicit view of the candidate diff being evaluated. | `kind`, `base`, `head`, `includes_dirty`, `includes_staged`, `warning_state` | Produces `ObservedDiff`; selected by CLI mode or argument. |
| `CheapReconciliationResult` | Structural validation result before heavy checks. | `blocking_findings`, `repair_hints`, `required_checks`, `tier` | Gates `CheckExecutionPlan`. |
| `CheckReuseKey` | Identity proving a previous check event applies to the current candidate. | `check_name`, `command_id`, `covered_surface`, `input_fingerprint`, `tool_versions`, `environment_marker` | Matches `check_events`; invalidated by source or environment changes. |
| `InheritedScope` | Files changed in a parent feature branch but not in a child repair PR. | `base_branch`, `parent_fingerprint`, `files`, `source` | Used by PR-on-PR reconciliation; not owned by child ledger scope. |
| `WrapperDeliveryPlan` | One-shot PR delivery orchestration. | `preflight_result`, `created_pr`, `post_pr_finalize`, `ledger_commit` | Coordinates wrapper, gate ledger, and GitHub PR creation. |

## 4. Implementation Plan

### 4.1 Technical Approach

The implementation should extend the ADR-042 Addendum 6 single-evaluator model
rather than create another wrapper layer. The evaluator should split the current
`check` path into two explicit phases:

1. Cheap reconciliation: observe the selected diff, classify surfaces, derive
   tier and obligations, validate scope/docs/tests/issues/PR body/governance
   shape, and fail fast on structural blockers.
2. Check execution/reuse: build the required check plan, reuse matching valid
   check events when permitted, execute only missing or invalid checks, append
   sanitized events, then write a final reconcile event.

The diff observer should make the selected candidate explicit. Existing modes
may map to defaults, but the output must state what was included and what was
excluded. If dirty or staged changes exist outside the selected view, the gate
must warn or fail depending on mode.

Check reuse should be conservative. It is acceptable to rerun more than needed;
it is not acceptable to reuse stale evidence. The reuse key must include source
fingerprint, command identity, tool versions, and environment marker.

For child PRs targeting a feature branch, the evaluator should compute two
diffs: repair diff (`target_branch...HEAD`) for child ledger ownership and, when
needed, integration diff (`origin/main...HEAD`) for CI/global checks. Inherited
files must be reported as inherited, not silently folded into the child scope.

The PR wrapper should become the delivery orchestrator for AI-authored PRs:
preflight once, create PR, post-PR finalize, commit/push ledger provenance once.
If the post-PR evidence commit triggers CI, the wrapper should avoid additional
checklist-only commits after CI turns green.

### 4.2 Affected Files

| File or glob | Action | Rationale |
|---|---|---|
| `src/scistudio/qa/governance/**` | modify | Evaluator, diff observer, check planning, event reuse, and reconciliation logic. |
| `scripts/scistudio_pr_create.py` | modify | Consolidated PR delivery flow and wrapper preflight behavior. |
| `scripts/hooks/**` | modify | Ensure hooks call the same evaluator and diff-view semantics. |
| `.github/workflows/**` | modify if needed | Keep CI mode authoritative and aligned with local evaluator semantics. |
| `docs/ai-developer/rules.md` | modify | Update command guidance after implementation. |
| `docs/ai-developer/specific_rules/gated-workflow.md` | modify | Document fail-fast, diff-view, reuse, and wrapper behavior. |
| `docs/specs/adr-042-gate-ledger-runtime.md` | modify if needed | Align the existing ADR-042 gate runtime spec with accepted optimization behavior. |
| `tests/qa/**` | modify/create | Cover evaluator phases, diff views, reuse, PR-on-PR scope, hooks, and CI parity. |
| `tests/scripts/test_scistudio_pr_create.py` | modify | Cover consolidated wrapper delivery flow. |

### 4.3 Implementation Sequence

1. Add evaluator fixtures for dirty, staged, committed, target-base, and
   PR-on-feature-branch candidates.
2. Implement cheap reconciliation as a separate internal phase with tests that
   prove heavyweight checks do not run when structural blockers exist.
3. Add explicit diff-view reporting and warnings for excluded dirty/staged
   changes.
4. Add check event reuse keys and conservative reuse validation.
5. Add PR-on-PR inherited-scope classification and reporting.
6. Align manual gate commands, hooks, finalize, wrapper, and CI around the same
   evaluator entry points and diff defaults.
7. Implement consolidated wrapper delivery or a narrowly scoped equivalent that
   reduces post-PR ledger evidence churn.
8. Update AI developer docs and ADR-042 gate runtime spec after behavior lands.
9. Run full gate, CI, and representative fixture tests before merge.

### 4.4 Verification Plan

- Unit tests for cheap reconciliation ordering and no-heavy-check execution on
  structural failures.
- Unit tests for each diff view and warning/fail behavior with dirty/staged
  changes.
- Unit tests for check reuse acceptance and rejection cases.
- Integration tests proving hooks, manual gate command, finalize, wrapper, and
  CI use the same evaluator semantics.
- PR-on-PR fixture tests for inherited scope classification.
- Wrapper tests for preflight-create-finalize-commit behavior.
- Full local `gate_record check --mode pre-pr` on the implementation PR.
- GitHub Actions must pass; CI remains the final authority.

### 4.5 Risks And Rollback

| Risk | Mitigation | Rollback |
|---|---|---|
| Reusing stale check evidence | Use conservative reuse keys and fail closed on ambiguity. | Disable final-readiness reuse while keeping cheap reconciliation. |
| Diff-view options confuse agents | Print selected view, included/excluded changes, and repair hints in every check. | Keep mode defaults and make explicit options advanced-only. |
| PR-on-PR classification hides real risk | Still allow CI/global integration diff checks; separate ownership from quality coverage. | Require explicit inherited-scope import from parent ledger. |
| Wrapper consolidation increases complexity | Keep internal steps visible and test each step independently. | Preserve current wrapper flow but keep fail-fast and reuse improvements. |

## 5. Success Criteria

### Measurable Outcomes

- **SC-001**: A missing scope include on a Tier 1 candidate fails before any
  heavyweight check command starts.
- **SC-002**: A metadata-only ledger correction after a successful full check
  completes final pre-PR readiness without rerunning unchanged heavyweight
  checks.
- **SC-003**: Manual gate, pre-commit hook, commit-msg hook, PR wrapper, and CI
  report the same changed-file ownership for the same fixture candidate.
- **SC-004**: A child repair PR into a feature branch no longer requires its
  ledger to claim inherited feature-branch files as owned scope.
- **SC-005**: No implementation test permits bypassing required checks,
  governance guards, issue closure, Sentrux, or CI authority.
- **SC-006**: AI-authored PR delivery requires at most one post-PR evidence
  commit after the initial implementation commits.

## 6. Assumptions

- The ADR-042 Addendum 6 single-evaluator model remains accepted.
- CI remains authoritative; local optimization is for earlier feedback and less
  repeated work, not for replacing CI.
- Check reuse is acceptable only when reuse identity is complete and validated.
- GitHub PR status is acceptable as final CI evidence; committed checklist text
  does not need to record the final green state after checks complete.
- Repair PRs into feature branches are a supported workflow in this repository.
