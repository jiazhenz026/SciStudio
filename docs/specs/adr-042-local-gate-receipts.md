---
spec_id: adr-042-local-gate-receipts
title: "ADR-042 Local Gate Receipts And Worktree Guard Specification"
status: Implemented
feature_branch: docs/issue-1492-adr042-local-gate-receipts
created: 2026-05-23
input: "Owner-approved ADR-042 Addendum 5: implement CI-parity local gate receipts, scoped override semantics, and AI worktree write guards."
owners:
  - "@jiazhenz026"
related_adrs: []
related_specs:
  - adr-042-ai-governance-tools
  - adr-042-code-quality-tools
  - adr-042-gate-record-sentrux-workflow
scope:
  in:
    - Shared local/CI workflow-gate orchestration.
    - "`gate_receipt` JSON/log receipt generation and validation."
    - Phase 5 required-check completeness enforcement.
    - Diff-inferred CI parity checks.
    - Scoped local and CI override semantics.
    - AI write-time worktree and path guards for supported runtimes.
    - AI developer documentation for receipt-based preflight.
    - AI-facing rules, workflow guidance, dispatch templates, and wrapper usage
      notes updated for the new receipt gate.
  out:
    - Replacing committed gate records.
    - Committing local receipt logs.
    - Weakening CI, branch protection, Sentrux, or governance checks.
    - Applying GitHub labels or administrator approvals automatically.
    - Requiring Sentrux Pro diagnostics.
governs:
  modules:
    - scistudio.qa.governance
    - scistudio.qa.governance.gate_record
  contracts:
    # Restructured by ADR-042 Addendum 6: the standalone ``validation`` and
    # ``workflow`` modules (per-stage validators and ``run_ci``) collapsed into
    # the single shared ``evaluator.reconcile`` entry point, the guard modules
    # moved under ``gate_record.guards``, and the separate ``gate_receipt``
    # module (``validate_receipt``) was folded into the ledger and pruned.
    - scistudio.qa.governance.gate_record.evaluator.reconcile
    - scistudio.qa.governance.worktree_write_guard.check_hook_payload
    - scistudio.qa.governance.gate_record.guards.core_change_guard.check
    - scistudio.qa.governance.gate_record.guards.human_bypass_guard.check
  files:
    - docs/specs/adr-042-local-gate-receipts.md
    - docs/adr/ADR-042-addendum5.md
    - docs/ai-developer/rules.md
    - docs/ai-developer/specific_rules/gated-workflow.md
    - docs/ai-developer/specific_rules/agent-dispatch.md
    - docs/ai-developer/personas/*.md
    - docs/ai-developer/templates/agent-dispatch-checklist-template.md
    - docs/ai-developer/templates/agent-dispatch-prompt-template.md
    - AGENTS.md
    - .agents/rules/rules.md
    - .claude/rules/rules.md
    - .codex/rules/rules.md
    - scripts/scistudio_pr_create.py
    - scripts/hooks/**
    - src/scistudio/agent_provisioning/**
    - src/scistudio/qa/governance/**
    - tests/qa/**
    - .gitignore
tests:
  - tests/qa/test_gate_record.py
  - tests/qa/test_gate_record_ci.py
  - tests/qa/test_gate_record_hooks.py
  - tests/qa/test_core_change_guard.py
  - tests/qa/test_human_bypass_guard.py
  - tests/qa/test_gate_receipt.py
  - tests/qa/test_worktree_write_guard.py
  - tests/agent_provisioning/test_hooks.py
  - tests/agent_provisioning/test_codex_config.py
  - tests/scripts/test_scistudio_pr_create.py
acceptance_source: adr
language_source: en
---

# ADR-042 Local Gate Receipts And Worktree Guard Specification

> **Superseded command-surface note:** This spec records ADR-042 Addendum 5.
> ADR-042 Addendum 6 folded standalone `gate_receipt` behavior into committed
> gate-record ledger events. Current AI-authored work uses `gate_record check`
> modes instead of `gate_receipt run` / `exec` / `validate`.

## 1. Change Summary

> **Note (ADR-042 Addendum 6):** The implementation symbols this spec governs
> were restructured by Addendum 6. The per-stage `validation` validators and
> `workflow.run_ci` collapsed into the single shared `evaluator.reconcile`
> entry point, the guard modules moved under `gate_record.guards`, and the
> separate `gate_receipt` module (`validate_receipt`) was folded into the
> gate-record ledger and has no successor symbol. The `governs` block has been
> repointed to the surviving symbols.

This spec records the ADR-042 Addendum 5 receipt design. Current repository
workflow no longer exposes a separate `gate_receipt` command: ADR-042 Addendum
6 folded receipt behavior into the committed gate ledger through
`gate_record check` and `gate_record finalize`. Treat the command names and
receipt entities below as historical Addendum 5 design context unless a later
Addendum 6 note explicitly maps them to a surviving symbol.

The original spec implemented ADR-042 Addendum 5. It defined a local preflight
system that produced candidate-specific receipt JSON and stdout/stderr
transcripts for AI-authored work before push or PR creation.

The spec also narrows override-label semantics and adds write-time worktree
guards. The goal is to move predictable failures from GitHub CI to local hard
gates without replacing committed gate records or normal CI.

## 2. User Scenarios & Testing

### User Story 1 - Local gate matches CI gate behavior (Priority: P1)

As a repository owner, I need local preflight to evaluate the same blocking
workflow-gate rules as GitHub CI.

Why this priority: If local and CI use different rule sets, agents can pass
local checks and still fail predictable CI guards.

Independent Test: Run shared workflow-gate fixtures through the local command
and the CI orchestration entry point and assert identical blocking findings
after filtering only pre-PR-impossible PR-state facts.

Acceptance Scenarios:

1. Given a gate record with missing docs landing, when local preflight runs,
   then it reports the same blocking docs finding as CI.
2. Given a gate record with an issue URL/content error, when local preflight
   runs, then it reports the same issue-link finding as CI.
3. Given a pre-PR run where only the final PR URL is missing, when local
   preflight runs, then it may filter that PR-state finding and must report the
   filtered count.

### User Story 2 - Receipts prove exact candidate checks (Priority: P1)

As a maintainer, I need a local receipt to prove that the exact current
base/head/diff/gate-record/PR-body candidate passed its required checks.

Why this priority: A freshness-only rule cannot catch checks run before a later
change.

Independent Test: Generate a passing receipt, modify the diff or gate record,
and assert pre-push rejects the stale receipt.

Acceptance Scenarios:

1. Given all inputs match the receipt and all checks exited 0, when pre-push
   validates, then it passes.
2. Given `HEAD` changed after the receipt was written, when pre-push validates,
   then it fails.
3. Given the gate record changed after the receipt was written, when pre-push
   validates, then it fails.

### User Story 3 - Required checks are complete (Priority: P1)

As a repository owner, I need every Phase 5 required check and every
diff-inferred CI parity check to appear in the receipt.

Why this priority: Missing one local check lets predictable failures escape to
CI.

Independent Test: Use fixtures for frontend, Python, docs, and governance
diffs and assert the required check matrix includes the expected commands.

Acceptance Scenarios:

1. Given frontend files changed, when required checks are resolved, then lint,
   format, typecheck, test, and build are required.
2. Given Python source changed, when required checks are resolved, then lint,
   format, typecheck, tests, and relevant audit/import checks are required.
3. Given a receipt lacks one required check, when pre-push validates, then it
   fails.

### User Story 4 - Core-change approval is narrow (Priority: P1)

As a repository owner, I need `admin-approved:core-change` to authorize only
protected core path changes.

Why this priority: A narrow approval must not become a general escape from
scope, docs, issue, receipt, or required-check validation.

Independent Test: Validate gate records with `admin-approved:core-change`
against separate core path and outside-scope findings.

Acceptance Scenarios:

1. Given only a protected core path requires approval and the label is present,
   when validation runs, then the core path finding is satisfied.
2. Given a file is outside `scope.include`, when validation runs with
   `admin-approved:core-change`, then scope validation still fails.
3. Given receipt evidence is missing, when validation runs with
   `admin-approved:core-change`, then receipt validation still fails.

### User Story 5 - AI writes stay in assigned worktrees (Priority: P1)

As a manager, I need AI write tools to fail before editing the root worktree or
files outside the assigned scope.

Why this priority: Push-time checks are too late to prevent root worktree
collisions.

Independent Test: Run the write guard against target paths in the assigned
worktree, root `main` worktree, outside the repo, and outside gate scope.

Acceptance Scenarios:

1. Given the current branch is `main`, when an AI write tool targets a file,
   then the guard blocks.
2. Given the target path resolves outside the assigned worktree, when the guard
   runs, then it blocks.
3. Given the target path is in the gate scope and the branch matches, when the
   guard runs, then it passes.

### Edge Cases

- A PR body is not available before PR creation. The receipt must omit or hash
  an explicit body file and then require revalidation when the PR body changes.
- Pre-PR receipt generation must not require an existing PR URL or PR number;
  it uses the intended PR body that the wrapper will pass to `gh pr create`.
- Finalizing the gate record after PR creation changes the gate record hash and
  intentionally requires a fresh pre-push receipt.
- A local dependency is unavailable. The receipt runner must record the failure
  or an accepted N/A rule; it must not silently pass.
- A broad diff touches frontend and Python surfaces. The required check matrix
  must include both sets.
- A receipt log contains sensitive local details. Logs remain gitignored and
  are never committed.
- A stacked PR targets a non-main base. The base ref must be part of the
  receipt fingerprint.

## 3. Requirements

### Functional Requirements

- FR-001: The implementation MUST provide a shared workflow-gate orchestration
  entry point used by GitHub CI and local preflight.
- FR-002: Local preflight MUST only filter findings that are impossible to
  satisfy before PR creation.
- FR-003: `admin-approved:core-change` MUST satisfy only protected core path
  authorization.
- FR-004: `admin-approved:core-change` MUST NOT bypass scope, issue, docs,
  receipt, full-audit, required-check, or CI-parity validation.
- FR-005: The implementation MUST provide `gate_receipt run` to execute the
  required Phase 5 and CI-parity check matrix.
- FR-006: The implementation MUST provide `gate_receipt exec` to record one
  command into the receipt format.
- FR-007: Receipt JSON MUST include current branch, base ref, head SHA, diff
  fingerprint, gate record hash, PR body hash when available, required checks,
  command records, exit codes, and final status.
- FR-008: Receipt logs MUST contain stdout/stderr transcript text and remain
  local-only under `.workflow/local/gate-receipts/`.
- FR-009: Pre-push and pre-PR hooks MUST reject missing, stale, incomplete, or
  failing receipts.
- FR-010: Receipt validity MUST be based on input fingerprints. Freshness time
  limits MAY be added as a secondary stale-file guard only.
- FR-010A: The implementation MUST support a pre-PR receipt mode that hashes
  the intended PR body from `.workflow/local/pr-body.md` or another explicit
  local body file and does not require an existing PR.
- FR-010B: The implementation MUST support a pre-push receipt mode that omits
  PR-body hashing when no PR body is part of the push candidate.
- FR-011: Required-check resolution MUST combine gate-record Phase 5 checks
  with diff-inferred CI parity checks.
- FR-012: Frontend diffs MUST require frontend lint, format, typecheck, test,
  and build receipt entries.
- FR-013: Python/source/governance diffs MUST require the configured Python
  lint, format, type, test, audit, and import-contract checks where applicable.
- FR-014: Worktree write guards MUST run before supported AI write tools mutate
  files.
- FR-015: Worktree write guards MUST compare resolved filesystem paths, not
  only string prefixes.
- FR-016: Runtime-specific hook files MUST point to shared scripts and must not
  define separate policy.
- FR-017: AI developer docs MUST explain that raw command output is not hard
  gate evidence unless recorded through the receipt runner.
- FR-018: AI-facing rules and workflow guidance MUST document current wrapper
  usage after this change: `scripts/scistudio_pr_create.py` validates
  `gate_receipt validate` and shared `gate_record ci` before invoking
  `gh pr create`.
- FR-019: AI-facing rules and workflow guidance MUST document the gate-record
  CLI semantic change: `gate_record ci` is the shared local/CI workflow-gate
  orchestration entry point, while `gate_record pre-push` remains the
  structural branch-diff validator and receipt freshness/completeness is
  handled by `gate_receipt validate`.
- FR-020: AI workflow docs and dispatch templates MUST tell agents to check
  whether additional docs need updates whenever wrapper, hook, gate-record,
  receipt, CI, or AI-runtime behavior changes. The check must include at
  least `docs/ai-developer/rules.md`,
  `docs/ai-developer/specific_rules/gated-workflow.md`,
  `docs/ai-developer/specific_rules/agent-dispatch.md`, and dispatch
  templates.

### Key Entities

| Entity | Description | Attributes | Relationships |
|---|---|---|---|
| `GateReceipt` | Candidate-specific local preflight result | schema version, branch, base ref, head SHA, diff fingerprint, gate record hash, PR body hash, required checks, commands, final status | Validated by pre-push and pre-PR hooks |
| `ReceiptCommand` | One executed check command | name, argv, cwd, started_at, ended_at, exit_code, log references | Belongs to `GateReceipt` |
| `RequiredCheckSet` | Resolved check matrix for the current candidate | gate checks, diff-inferred checks, N/A decisions | Produced before receipt execution |
| `CandidateFingerprint` | Hashable identity of the exact push or PR candidate | base, head, diff summary/hash, gate record hash, PR body hash, labels/env hash | Compared against current state |
| `WorktreeWriteContext` | Pre-write validation context | cwd, target path, branch, assigned worktree, gate scope | Consumed by write guard |

## 4. Implementation Plan

### 4.1 Technical Approach

Move workflow-gate orchestration from inline GitHub Actions scripts into a
Python module under `scistudio.qa.governance`. GitHub Actions and local
preflight must call that same module.

Add a `gate_receipt` module with two public command surfaces: `run` and `exec`.
`run` resolves required checks, executes them, writes JSON/log output, and
returns nonzero on any failed required check. `exec` records an individual
command for advanced workflows but still computes and stores the same candidate
fingerprint.

Add a receipt validator used by pre-push and pre-PR hooks. The validator
compares the current candidate fingerprint with the receipt and verifies
required-check completeness and exit status.

Pre-PR validation and pre-push validation are different candidate modes.
Pre-PR validation includes the intended PR body hash because the wrapper has
the exact body it will submit. Pre-push validation validates only the branch
push candidate and does not require a PR URL or PR body. After PR creation,
`gate_record finalize` changes the committed gate record and requires a new
pre-push receipt before the finalize commit is pushed.

Add a worktree write guard script used by Claude Code and Codex project hooks.
The guard resolves filesystem paths and checks branch, worktree, and gate
scope before mutation.

### 4.2 Affected Files

| File or glob | Action | Rationale |
|---|---|---|
| `docs/adr/ADR-042-addendum5.md` | create | Accepted governance decision |
| `docs/specs/adr-042-local-gate-receipts.md` | create | Implementation contract |
| `src/scistudio/qa/governance/gate_receipt.py` or package | create | Receipt CLI, schema, execution, validation |
| `src/scistudio/qa/governance/gate_record/workflow.py` | create | Shared local/CI workflow-gate orchestration |
| `src/scistudio/qa/governance/workflow_gate.py` | create | CLI wrapper for shared workflow-gate orchestration |
| `src/scistudio/qa/governance/worktree_write_guard.py` | create | Pre-write worktree/scope enforcement |
| `src/scistudio/qa/governance/gate_record/**` | modify | Scoped override handling and validation integration |
| `scripts/scistudio_pr_create.py` | modify | Use shared orchestration and receipt validation |
| `scripts/hooks/**` | modify/create | Pre-push, pre-PR, and pre-write hook entry points |
| `.github/workflows/workflow-gate.yml` | no change in initial implementation | Existing CI calls `gate_record ci`; this spec changes that command to invoke shared orchestration |
| generated `.claude/settings.json` | modify via provisioning template | Wire receipt and write-guard hooks for Claude Code |
| generated `.codex/config.toml` | modify via provisioning template | Wire equivalent hooks for Codex when present |
| `src/scistudio/agent_provisioning/**` | modify | Provision equivalent runtime hooks |
| `.gitignore` | verify/modify | Keep `.workflow/local/**` local-only |
| `docs/ai-developer/rules.md` | modify | Explain scoped override semantics |
| `docs/ai-developer/specific_rules/gated-workflow.md` | modify | Explain receipt runner and hard gate behavior |
| `AGENTS.md`, runtime rules indexes, and persona docs | modify | Route every AI entry point to the shared gate CLI command set |
| `tests/qa/test_gate_receipt.py` | create | Receipt schema, fingerprint, required-check, stale-check tests |
| `tests/qa/test_worktree_write_guard.py` | create | Worktree/path/branch/scope guard tests |
| `tests/qa/test_gate_record_ci.py` | modify | Local/CI orchestration parity regression tests |
| `tests/qa/test_core_change_guard.py` | modify | Scoped `admin-approved:core-change` regression tests |

### 4.3 Implementation Sequence

1. Add failing regression tests for #1464 local/CI workflow-gate mismatch.
2. Extract shared workflow-gate orchestration and update CI to call it.
3. Refactor local override handling so labels satisfy only their intended
   guards.
4. Define `GateReceipt`, `ReceiptCommand`, `RequiredCheckSet`, and
   `CandidateFingerprint` models.
5. Implement required-check resolution from gate record Phase 5 plus diff
   surfaces.
6. Implement `gate_receipt run` and `gate_receipt exec`.
7. Implement receipt validation in pre-push and pre-PR hooks.
8. Implement worktree write guard and wire it into supported AI runtimes.
9. Update AI developer docs and dispatch templates, including wrapper usage,
   `gate_record` CLI semantics, receipt commands, and a required docs-impact
   check for future governance-tool changes.
10. Run focused QA tests, full audit, and the relevant frontend/Python checks.

### 4.4 Verification Plan

- `pytest tests/qa/test_gate_receipt.py --no-cov`
- `pytest tests/qa/test_worktree_write_guard.py --no-cov`
- `pytest tests/qa/test_gate_record_ci.py tests/qa/test_gate_record_hooks.py --no-cov`
- `pytest tests/qa/test_core_change_guard.py tests/qa/test_human_bypass_guard.py --no-cov`
- `ruff check src/scistudio/qa/governance tests/qa scripts`
- `ruff format --check src/scistudio/qa/governance tests/qa scripts`
- `mypy src/scistudio/ --ignore-missing-imports`
- `PYTHONPATH=src python -m scistudio.qa.audit.full_audit --repo-root . --format json --output .audit/full-audit.json`
- Frontend lint, format, typecheck, test, and build when frontend files or CI
  parity matrix code changes touch frontend surfaces.

### 4.5 Risks And Rollback

The main risk is over-blocking local work when dependencies are missing or the
required-check matrix is too conservative. Mitigate with explicit N/A rules
only when the governing ADR/spec permits them, and keep CI authoritative.

Rollback is to disable the new receipt hook while leaving CI Workflow Gate
active. Rollback must not restore broad override behavior or weaken CI.

## 5. Success Criteria

### Measurable Outcomes

- SC-001: Local preflight and GitHub Workflow Gate produce matching blocking
  findings for shared fixtures.
- SC-002: A receipt generated for an old commit is rejected after a new commit.
- SC-003: A receipt generated before a gate record edit is rejected after the
  edit.
- SC-004: A frontend diff without lint, format, typecheck, test, and build
  receipt entries is rejected.
- SC-005: `admin-approved:core-change` does not bypass outside-scope or missing
  receipt findings in tests.
- SC-006: An AI write attempt in the root `main` worktree is blocked by the
  write guard test fixture.
- SC-007: `.workflow/local/gate-receipts/**` remains untracked and ignored.

## 6. Assumptions

- The repository keeps `.workflow/local/**` ignored for local-only state.
- GitHub CI remains authoritative for final merge readiness.
- Some PR-state facts are unavailable before PR creation and may be filtered
  only with explicit reporting.
- The initial implementation may require conservative local checks before it
  learns finer-grained safe skip rules.
