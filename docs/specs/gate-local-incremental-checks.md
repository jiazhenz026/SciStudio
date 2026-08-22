---
spec_id: gate-local-incremental-checks
title: "Local Gate Checks Run Incrementally While CI Runs The Full Suite"
status: Implemented
feature_branch: guided/1646-gate-check-incrementality
created: 2026-08-21
input: "Owner-directed live session (guided) on gate workflow speed. The owner's measured complaint is latency: pre-commit, pre-PR, and post-PR gate checks are slow because every local check runs the whole repository even when one file changed. Owner decision: every local check becomes incremental (changed-file scoped, including the Python test suite); CI keeps running the full suite and stays the authoritative pass. Deliverable: a spec listing the change surface, plus an assessment of whether the AI governance rule documents need updating."
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
related_specs:
  - adr-042-gate-ledger-runtime
scope:
  in:
    - A per-check local command variant, scoped to the observed diff, distinct from the CI-mirror command already recorded in CHECK_CATALOG.
    - Changed-file test selection for the local python_tests variant, with the coverage floor enforced by CI only.
    - Finer covered-surface granularity so lint, type, and test evidence stop sharing one fingerprint and invalidating each other.
    - Narrower reusable-evidence inputs for full_audit and deferral_discipline, which currently treat every changed file as an input.
    - Local auto-formatting instead of a failing format check.
    - Local required-check breadth per mode, extending the existing ci-mode and pre-commit-mode role splits to local and pre-pr modes.
    - The meaning of --force-checks as the opt-in that runs the full CI-mirror commands locally.
    - An assessment of which AI governance documents and which ADR-042 statements the change falsifies.
  out:
    - Any change to the checks CI runs. ci.yml already runs the full matrix on every PR and is unchanged by this spec.
    - Weakening issue linkage, scope reconciliation, docs obligations, test-file obligations, guard evaluation, protected-path authorization, label provenance, or committed ledger evidence.
    - Removing any check from the repository. Every check named here continues to run in CI at full breadth.
    - Tool-version pinning. #1981 is already fixed in the parity environment, which installs the CI-resolved pins explicitly; #2099 (onnxruntime) is a separately tracked chore and stays out of this focused change.
    - Guard pruning, persona and task-kind consolidation, and governance document size reduction, which are separate concerns raised in the same session and not part of the owner's speed directive.
governs:
  modules:
    - scistudio.qa.governance.gate_record.checks
    - scistudio.qa.governance.gate_record.evaluator
  # NOTE: contracts and entry_points are deliberately empty, matching
  # adr-042-gate-ledger-runtime. doc_drift.missing-adr-governance resolves only
  # one document per ADR number (the base ADR wins over its addenda, #2004), and
  # ADR-042.md does not govern the gate_record contracts this spec changes;
  # ADR-042 Addendum 6 does. Listing them here produces false alignment
  # findings until #2004 lands.
  contracts: []
  entry_points: []
  files:
    - src/scistudio/qa/governance/**
  excludes:
    - .github/workflows/ci.yml
    - src/scistudio/qa/governance/gate_record/guards/**
tests:
  - tests/qa/test_gate_incremental_checks.py
acceptance_source: issue
language_source: en
---

# Local Gate Checks Run Incrementally While CI Runs The Full Suite

## 1. Change Summary

`gate_record check` already decides *whether* a check must run by comparing a
per-surface input fingerprint against recorded evidence. It does not decide
*what* that check runs: every entry in `CHECK_CATALOG` is a whole-repository
command. Because a working agent changes files in the covered surface on almost
every iteration, the fingerprint almost always differs, the reuse branch almost
never fires, and each iteration pays the full-repository cost again.

This spec makes the local command incremental as well as the local decision.
Each check gains a diff-scoped local variant; the existing whole-repository
command is retained as the CI-mirror variant and remains what CI runs.

The role split this depends on is already accepted and already implemented for
one mode. `evaluator._CI_OWNED_QUALITY_CHECKS` drops the entire quality matrix
from required obligations in `ci` mode, on the recorded rationale that the
separate `ci.yml` jobs are authoritative for it on the same PR. The code comment
there calls this the role split, not a weakening. `_PRE_COMMIT_SKIP_CHECKS`
(#1628) applies the same reasoning to `pre-commit` by dropping the two slowest
checks. This spec extends that established reasoning to `local` and `pre-pr`:
those modes keep running every check, but at diff scope rather than repository
scope, because `ci.yml` still proves the full surface before merge.

Two measurements matter and they disagree, so both are reported.

Failure counts come from the 130 committed ledgers under `.workflow/records/`
(2,316 recorded check executions) and are exact:

| Check | Runs | Failures |
|---|---:|---:|
| `python_tests` | 308 | 222 |
| `format_check` | 304 | 98 |
| `full_audit` | 344 | 47 |
| `lint_format` | 262 | 27 |
| `semantic_dup` | 277 | 16 |
| `frontend` | 78 | 15 |
| `deferral_discipline` | 172 | 10 |
| `architecture_tests` | 148 | 9 |
| `type_check` | 197 | 7 |
| `import_contracts` | 198 | 2 |
| `wheel_release_smoke` | 28 | 0 |

Costs are measured directly on a warm parity environment. An elapsed-time proxy
derived from adjacent ledger timestamps was tried first and is not usable: it
charges agent think time to whichever check ran last, which made
`architecture_tests` look like the most expensive check in the repository when it
in fact costs 7.5 seconds. Every cost below is measured:

| Check | Repository-scoped | Diff-scoped |
|---|---:|---:|
| `python_tests` | 159s | 39s |
| `semantic_dup` | 135s | no narrow form |
| `type_check` | 25.4s | 0.9s |
| `full_audit` | 20s | no narrow form |
| `architecture_tests` | 7.5s | no narrow form |
| `deferral_discipline` | 2s | no narrow form |
| `lint_format` + `format_check` | 0.35s | 0.2s |
| **Tier 1 total** | **~349s** | **~205s** |

Narrowing alone takes a Tier 1 local run from ~349s to ~205s. Deferring
`semantic_dup` — the one check whose verdict is a property of the whole corpus
rather than of the current edit — takes it to ~70s.

Of 2,316 executions, 1,029 re-ran because the fingerprint genuinely changed and
278 re-ran on an unchanged fingerprint, of which 69 had a prior passing event.
The reuse mechanism is therefore working as designed; the cost is in the command
breadth, not in the reuse decision.

## 2. User Scenarios & Testing

### User Story 1 - An agent iterating on one file waits seconds, not minutes (Priority: P1)

An agent edits one module and runs `gate_record check`. The lint, type, and test
checks execute against the changed file and the tests that cover it, not against
the whole repository, so the agent gets a verdict fast enough to keep iterating.

Why this priority: this is the owner's stated problem. Every other item in this
spec is either a prerequisite for it or a smaller saving alongside it.

Independent Test: on a branch whose diff is a single Python module, run
`gate_record check` and confirm the recorded `python_tests` check event's command
names a test subset rather than the whole suite, and that the check event still
records `covered_surface` and an `input_fingerprint` for reuse.

Acceptance Scenarios:

- Given a branch whose diff touches one Python module under `src/`,
  When `gate_record check --mode local` runs,
  Then the executed `lint_format` and `format_check` commands are scoped to the
  changed Python files rather than to the repository root.
- Given the same branch,
  When `gate_record check --mode local` runs,
  Then the executed `python_tests` command selects the tests affected by the
  observed diff and does not enforce the coverage floor.
- Given the same branch,
  When `gate_record check --mode pre-pr` runs and every selected check passes,
  Then the ledger records passing check events and reconciliation passes without
  requiring whole-repository local evidence.
- Given a branch where the incremental local selection passes but a
  repository-wide invariant is violated,
  When the PR is opened,
  Then the corresponding `ci.yml` job fails and the PR is blocked.

### User Story 2 - A formatting difference never costs a gate cycle (Priority: P2)

An agent runs `gate_record check` with unformatted code. The formatter rewrites
the files instead of failing the gate, and the agent proceeds.

Why this priority: `format_check` failed 98 times across the ledgers, every
failure resolvable by a single formatter invocation. It is the largest zero-risk
saving, but it is smaller than User Story 1.

Independent Test: introduce a formatting deviation, run `gate_record check`, and
confirm the files are reformatted, the check event records a pass, and a
subsequent repository-scoped format check on the same tree exits zero.

Acceptance Scenarios:

- Given a working tree containing a formatting deviation in a changed file,
  When `gate_record check --mode local` runs,
  Then the changed files are reformatted in place and the `format_check` event
  records a pass with an indication that files were rewritten.
- Given a working tree with no formatting deviation,
  When `gate_record check` runs,
  Then no file is modified.

### User Story 3 - The governance documents describe what the gate actually does (Priority: P3)

An agent reading `docs/ai-developer/**` before starting work is told the truth
about what local `check` proves and what only CI proves.

Why this priority: required for correctness of the governance surface, but it is
a documentation obligation that follows the implementation rather than gating it.

Independent Test: grep the governance documents and ADR-042 Addendum 6 for the
full-local-mirror and CI-equivalence claims enumerated in section 4.2, and
confirm each either matches implemented behavior or is marked as superseded.

Acceptance Scenarios:

- Given the implementation has landed,
  When a reader consults `docs/ai-developer/specific_rules/gated-workflow.md`
  section 2.4,
  Then the tier-breadth table describes local breadth as diff-scoped and names
  `ci.yml` as the authority for full-surface proof.
- Given the implementation has landed,
  When the full audit runs,
  Then no doc-drift or fact-drift finding is reported against the gate
  documentation.

### Edge Cases

- The diff touches only non-Python files. Python-surface checks are not selected
  at all; behavior is unchanged from today.
- The diff touches a test helper or `conftest.py` that many tests import.
  Selection must resolve the dependency rather than silently under-select; when
  the dependency cannot be resolved the local run must widen to the full suite
  rather than under-report.
- The test-selection database is absent or stale on a fresh worktree. The first
  run widens to the full suite and populates it.
- `--force-checks` is passed. Every selected check runs its CI-mirror command at
  repository scope.
- A check has no meaningful diff-scoped variant, for example
  `wheel_release_smoke`. It keeps its repository-scoped command and its selection
  is governed by mode.
- The observed diff is empty. No check executes and reconciliation proceeds on
  the recorded evidence, as today.

## 3. Requirements

### Functional Requirements

- FR-001: `CheckSpec` MUST carry a diff-scoped local command in addition to the
  existing repository-scoped CI-mirror command, and a check event MUST record
  which of the two produced it.
- FR-002: `local`, `pre-commit`, and `pre-pr` modes MUST execute the diff-scoped
  variant when one exists; `--force-checks` MUST execute the CI-mirror variant.
- FR-003: The local `python_tests` variant MUST select the tests affected by the
  observed diff, MUST run with the coverage floor disabled, and MUST widen to the
  full suite when affected-test resolution is unavailable or incomplete.
- FR-004: The coverage floor MUST continue to be enforced by `ci.yml` at its
  current threshold. This spec MUST NOT change the configured floor.
- FR-005: The local `format_check` variant MUST apply formatting to the changed
  files rather than failing on deviation, and MUST record which files it rewrote.
- FR-006: `covered_surface` MUST distinguish Python lint inputs, Python type
  inputs, and Python test inputs, so that evidence for one is not invalidated by
  a change that can only affect another.
- FR-007: Reusable-evidence inputs for `full_audit` and `deferral_discipline`
  MUST be narrowed from every changed file to the file classes those checks
  actually read.
- FR-008: A check event produced by a diff-scoped variant MUST NOT satisfy a
  CI-mirror obligation in `ci` mode. The `ci` mode obligations are unchanged.
- FR-009: The `check` command MUST report, in its summary, which checks ran
  diff-scoped and which ran at repository scope, so the difference is visible
  rather than implicit.
- FR-010: A check with no diff-scoped form whose verdict is a property of the
  whole corpus rather than of the current edit MUST be deferred to CI in local
  modes, and MUST already be owned by a CI job. `--force-checks` MUST restore it.
  No check that can catch a defect introduced by the current edit may be deferred.
- FR-011: `select_checks` MUST answer only which checks are required. The tier
  branch whose two arms executed identical statements MUST be removed, and the
  breadth-per-mode decision MUST live where the mode is known, in the evaluator.
- FR-012: Every governance statement enumerated in section 4.2 that asserts local
  `check` proves a full CI mirror MUST be updated or superseded before the
  implementation is considered complete.

### Key Entities

- CheckSpec: gains a diff-scoped command alongside `command`, and a declaration
  of how the diff-scoped argument list is built from the observed changed files.
  Existing fields (`name`, `covered_surface`, `ci_job`, `cwd`, `pr_only`,
  `needs_src_import`) are unchanged. Relationship: consumed by `select_checks`
  and by the evaluator's execution step.
- CheckEvent: gains a field recording whether the event came from the diff-scoped
  or the CI-mirror variant. All existing fields, including `input_fingerprint`,
  `covered_surface`, and the sanitization rules, are unchanged. Relationship:
  appended to the committed ledger and read back by evidence reuse.

## 4. Implementation Plan

### 4.1 Technical Approach

The change is confined to check selection and check execution. Ledger schema,
guard calculators, scope reconciliation, obligation inference, issue linkage,
docs and test obligations, and CI workflows are untouched except for the
additive `CheckEvent` field in FR-001.

Three mechanisms carry the work.

First, command variants. `CheckSpec` gains a second command form built from the
observed changed files. `lint_format`, `format_check`, `type_check`, and
`frontend` take a file list directly. `python_tests` takes a selected node set.
`full_audit`, `semantic_dup`, `deferral_discipline`, `architecture_tests`, and
`wheel_release_smoke` have no natural file-list form; their breadth is governed
by mode selection instead.

Second, test selection. The local `python_tests` variant resolves the tests
affected by the observed diff. The mechanism is a zero-dependency mirrored-path
mapping: a changed module resolves to the longest existing mirrored `tests/`
directory, or to a mirrored `test_<stem>.py`; a changed test file selects itself;
a changed `conftest.py` selects its directory. An import-graph database such as
`pytest-testmon` was rejected in ADR-042 Addendum 7 section 6 because a stale
database under-selects, which is the one failure mode the widening rule exists to
prevent. The floor is disabled locally per FR-003 and FR-004; disabling
it is what makes any subset run possible at all, since the configured
repository-wide coverage floor makes every subset run fail by construction.

Third, surface granularity. The evaluator's check-input mapping today puts five
checks on one Python surface, so any Python edit invalidates all five including
the most expensive. Splitting the surface lets a formatting-only edit keep type
and test evidence current.

The role split this rests on is not new. `_CI_OWNED_QUALITY_CHECKS` already
removes all eleven quality checks from required obligations in `ci` mode because
`ci.yml` owns them; `_PRE_COMMIT_SKIP_CHECKS` already removes the two slowest
from `pre-commit`. This spec applies the same reasoning to the remaining local
modes and narrows the command rather than dropping the check.

### 4.2 Affected Files

| File or glob | Action | Rationale |
|---|---|---|
| `src/scistudio/qa/governance/gate_record/checks.py` | modify | CheckSpec variant field, catalog diff-scoped commands, test selection, dead tier branch removed (FR-001, FR-002, FR-003, FR-005, FR-010) |
| `src/scistudio/qa/governance/gate_record/evaluator.py` | modify | Surface split, input narrowing, variant dispatch, summary reporting (FR-006, FR-007, FR-008, FR-009) |
| `src/scistudio/qa/governance/gate_record/ledger.py` | modify | Additive CheckEvent `scope` field (FR-001) |
| `src/scistudio/qa/governance/gate_record/workflow.py` | modify | Report which checks ran diff-scoped (FR-009) |
| `src/scistudio/qa/governance/gate_record/instructions.py` | modify | The Tier 1 note printed to agents claimed a full local mirror |
| `src/scistudio/qa/testing/run_python_tests.py` | none | Already forwards paths to both phases and maps "no tests collected" to success, so the local variant needs no runner change |
| `pyproject.toml` | none | The coverage floor is deliberately unchanged (FR-004) and asserted by test |
| `tests/qa/test_gate_incremental_checks.py` | create | Selection widening, variant construction, ci-mode isolation, surface split, floor-unchanged regression |
| `docs/adr/ADR-042-addendum7.md` | create | Supersede the Addendum 6 full-local-mirror statements listed below |
| `docs/ai-developer/specific_rules/gated-workflow.md` | modify | Mode table, tier-breadth list, and the same-evaluator claim |
| `docs/ai-developer/specific_rules/guided-work.md` | modify | Tier 1 full-mirror statements |
| `docs/ai-developer/gate-cli-command-set.md` | modify | Mode table, tier table, and per-persona check breadth column |
| `docs/ai-developer/rules.md` | modify | Command-index description of what check runs |
| `.github/workflows/ci.yml` | none | Already runs the full matrix; unchanged by design |

The governance statements that the change falsifies, located for the
implementation PR:

| Location | Statement that becomes false |
|---|---|
| `docs/adr/ADR-042-addendum6.md` section 7.5 | Tier 1 runs a full local mirror of the repository's merge-blocking CI command surface |
| `docs/adr/ADR-042-addendum6.md` tier table | check must run a full local mirror of merge-blocking CI command surfaces |
| `docs/adr/ADR-042-addendum6.md` per-persona table | check must run the full merge-blocking CI mirror |
| `docs/adr/ADR-042-addendum6.md` section 7.10 summary | local checks run the same resolved tool versions as CI in a CI-equivalent environment; the environment claim survives, the identical-command implication does not |
| `docs/ai-developer/specific_rules/gated-workflow.md` section 2.4 | Tier 1 requires evidence for the full local mirror of the merge-blocking CI command surface |
| `docs/ai-developer/specific_rules/gated-workflow.md` mode table | Local and CI modes use the same evaluator; the only difference is that CI mode has real PR metadata. They will also differ in command breadth |
| `docs/ai-developer/specific_rules/guided-work.md` section 3 | check must prove the full local mirror of the merge-blocking CI command surface |
| `docs/ai-developer/specific_rules/guided-work.md` section 8.3 | When escalated to Tier 1, check proves the full local mirror of the merge-blocking CI surface |
| `docs/ai-developer/gate-cli-command-set.md` tier table | check must prove the full local mirror of merge-blocking CI command surfaces |
| `docs/ai-developer/gate-cli-command-set.md` mode table | Full local CI-equivalent preflight at the selected tier |
| `docs/ai-developer/gate-cli-command-set.md` persona table | Full merge-blocking CI mirror evidence |
| `docs/ai-developer/rules.md` section 5 | infers the tier-selected CI-equivalent check set, runs required commands |

Because Addendum 6 is the normative source for these claims and the others
restate it, the governance-document edits are not sufficient on their own: a new
ADR-042 addendum is required to supersede the decision. The ai-developer
documents must not be edited ahead of the implementation, since editing them
first would describe unimplemented behavior as current, which the common rules
forbid.

### 4.3 Implementation Sequence

- T-001: Confirm the tool-version pins are already correct rather than
  re-fixing them. `parity._install_deps` installs the CI-resolved pins as an
  explicit second step, and `resolve_ci_tool_versions` returns the pinned linter
  version, so #1981 is fixed in code and needs only issue closure. #2099
  (onnxruntime) stays with its own issue. Depends on: nothing.
  Verification: resolved versions match `.pre-commit-config.yaml`.
- T-002: Split the Python covered surface and narrow the `full_audit` and
  `deferral_discipline` inputs. Story: User Story 1. Files: `evaluator.py`,
  `tests/qa/test_gate_evaluator.py`. Depends on: nothing. Verification: unit
  tests asserting cross-surface evidence survival.
- T-003: Add the CheckSpec variant field and the CheckEvent variant record; wire
  force-checks to the CI-mirror variant. Story: User Story 1. Files: `checks.py`,
  `ledger.py`, `evaluator.py`, `tests/qa/test_gate_record.py`. Depends on: T-002.
  Verification: variant round-trips through the committed ledger.
- T-004: Diff-scoped commands for `lint_format`, `type_check`, and `frontend`;
  auto-formatting variant for `format_check`. Story: User Stories 1 and 2.
  Files: `checks.py`, `tests/qa/test_gate_record.py`. Depends on: T-003.
  Verification: acceptance scenarios of User Stories 1 and 2.
- T-005: Diff-scoped `python_tests` selection with the floor disabled locally and
  full-suite widening on unresolved dependencies. Story: User Story 1. Files:
  `checks.py`, `tests/qa/test_gate_incremental_checks.py`. Depends on: T-003.
  The largest and riskiest task; separately reviewable.
  Verification: widening test plus the floor-unchanged regression test.
- T-006: Remove the dead tier branch in `select_checks` and keep breadth-per-mode
  in the evaluator, where the mode is known. Story: cross-cutting. Files:
  `checks.py`, `tests/qa/test_gate_incremental_checks.py`. Depends on: T-003.
  Verification: tier-superset and scope-agnostic selection tests.
- T-007: ADR-042 Addendum 7 superseding the statements tabulated above. Story:
  User Story 3. Files: `docs/adr/ADR-042-addendum7.md`. Depends on: T-004,
  T-005, T-006. Verification: full audit doc checks.
- T-008: Governance document updates. Story: User Story 3. Files:
  `docs/ai-developer/**`. Depends on: T-007. Requires a governance_touch
  declaration and owner review. Verification: full audit doc and fact drift.

### 4.4 Verification Plan

- Unit tests in `tests/qa/test_gate_evaluator.py` covering: the surface split
  keeps type evidence current across a formatting-only edit; narrowed
  `full_audit` inputs are not invalidated by an unrelated frontend change; a
  diff-scoped event does not satisfy a ci-mode obligation.
- Unit tests in `tests/qa/test_gate_record.py` covering variant selection per
  mode and force-checks restoring repository scope.
- A regression test asserting the coverage floor is unchanged in `pyproject.toml`
  and that the local test variant disables coverage, so the floor cannot be
  silently relaxed for CI.
- A test asserting the full-suite widening path fires when affected-test
  resolution returns nothing for a changed source file.
- Measured before-and-after wall clock for `gate_record check --mode pre-pr` on a
  single-file diff and on a broad diff, recorded in the implementation PR. The
  ledger-derived table in section 1 is a proxy and is not sufficient evidence of
  the improvement.
- `ci.yml` unchanged and green on the implementation PR, which is the direct
  demonstration that full-surface enforcement survived.
- Lint, type, import-contract, and full-audit checks pass on the implementation
  PR through the standard gate flow.

### 4.5 Risks And Rollback

- Under-selection lets a real failure reach CI. This is the owner's stated
  concern about relaxing local checks and it is the principal risk. Mitigation:
  the widening rule in FR-003, keeping every check that answers whether the agent
  broke what it just wrote (lint, type, tests) local rather than deferring it,
  and the section 1 evidence that the checks proposed for reduced local breadth
  are repository-invariant checks whose failure rate does not scale with
  iteration count. Rollback: force-checks restores repository scope immediately;
  reverting T-003 restores it by default.
- Test-selection dependency. Adding an import-graph tool to the gate's execution
  path adds a dependency that can itself break or go stale. Mitigation: the
  fallback chain in FR-003 must widen to the full suite rather than under-select,
  so a broken database costs speed and never correctness.
- Coverage regression invisible locally. Disabling the floor locally means a
  coverage drop surfaces only in CI. Accepted: coverage is a repository-level
  invariant, and CI enforces it on the same PR at the unchanged threshold.
- Governance documents drifting ahead of implementation. Mitigated by sequencing
  T-007 and T-008 after the behavior lands.
- The ci-mode contract weakening by accident. FR-008 forbids a diff-scoped event
  from satisfying a ci-mode obligation; the corresponding test in section 4.4 is
  the guard against this.

## 5. Success Criteria

### Measurable Outcomes

- SC-001: A Tier 1 `gate_record check` completes in under half the time the same
  selection takes at repository scope, measured on the same machine with a warm
  parity environment. Measured on this change's own diff: 958s with
  `--force-checks` versus 58.8s diff-scoped, a 16.3x reduction against a 2x
  target. The ledger confirms the fast run executed all eight selected checks and
  reused no prior evidence. The baseline includes a 600s `semantic_dup` timeout
  (#2099 reproducing); excluding it the repository-scoped set is roughly 358s,
  still a 6.1x reduction.
- SC-002: `format_check` produces zero gate failures across the ledgers recorded
  after the change, measured over at least twenty subsequent sessions, compared
  with 98 failures in 304 runs before.
- SC-003: The proportion of non-dependabot PR branches that fail `ci.yml` at
  least once does not increase, measured over at least thirty branches after the
  change against the pre-change baseline of 12 of 81 branches, or 15 percent.
  This is the criterion that would falsify the change, and it can only be
  evaluated after the change has been in use; it is not satisfied by this PR.
- SC-004: A Python edit that changes only formatting no longer invalidates
  recorded `type_check` or `python_tests` evidence, verified by unit test.
- SC-005: The configured coverage floor is unchanged and `ci.yml` continues to
  run both test phases at full breadth, verified by test and by inspection of the
  merged diff.

## 6. Assumptions

- The owner has decided that local gate checks become incremental and that CI
  remains the authoritative full-suite pass. Source: owner.
- `ci.yml` already runs the full Python matrix on both supported interpreter
  versions for every PR, so no CI change is needed to preserve full-surface
  enforcement. Source: existing-system.
- The ci-mode role split in `_CI_OWNED_QUALITY_CHECKS` is settled repository
  policy and can be extended rather than re-argued. Source: existing-system.
- The cost figures in section 1 are direct measurements on one machine with a
  warm parity environment; the first run in a fresh worktree additionally pays
  parity-venv provisioning, which is a one-time cost per worktree and is excluded.
  Source: existing-system.
- Issue 1646 asked for this spec; the owner then directed that the
  implementation land in the same PR, tracked by issue 2102. Source: owner.
