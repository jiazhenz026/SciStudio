---
spec_id: adr-042-change-contract-gate
title: "ADR-042 Change Contract Gate Specification"
status: Draft
feature_branch: docs/change-contract-gate-spec
created: 2026-06-12
input: "Owner discussion: add a baseline-aware change contract layer so ADR/spec-driven migrations, refactors, removals, and additive architecture work can be checked for declared change intent, forbidden legacy references, and production reachability."
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
related_specs:
  - adr-042-consistency-tools
  - adr-042-gate-ledger-runtime
scope:
  in:
    - Change contract schema and authoring rules linked from ADR/spec frontmatter.
    - Baseline-aware no-new-violations checking.
    - Added, changed, removed, and retained surface declarations.
    - Forbidden production reference checks.
    - Basic production reachability checks for declared new surfaces.
    - Required canary declarations for public API, UI, CLI, plugin, workflow-runtime, and external-integration surfaces.
    - Full audit and gate_record check integration.
  out:
    - Immediate cleanup of existing historical drift.
    - Replacing existing ADR/spec frontmatter governs metadata.
    - Full semantic call-graph analysis for every dynamic loading pattern.
    - Making all Vulture findings blocking.
    - Implementing ADR-048-specific previewer checks directly in this spec.
governs:
  modules:
    - scistudio.qa.audit
    - scistudio.qa.schemas
    - scistudio.qa.schemas.change_contracts
    - scistudio.qa.governance.gate_record
  contracts:
    - scistudio.qa.schemas.change_contracts.ChangeContract
    - scistudio.qa.schemas.change_contracts.ChangeSurface
    - scistudio.qa.schemas.change_contracts.ChangeContractBaseline
  entry_points: []
  files:
    - docs/ai-developer/specific_rules/document-standards.md
    - src/scistudio/qa/audit/**
    - src/scistudio/qa/schemas/**
    - src/scistudio/qa/governance/gate_record/**
    - tests/qa/**
  excludes: []
planned_governs:
  modules:
    - scistudio.qa.audit.change_contracts
  contracts: []
  entry_points: []
  files:
    - docs/change-contracts/**
    - docs/audit/baselines/change-contract-baseline.json
    - tests/qa/test_change_contracts.py
  excludes: []
tests:
  - tests/qa/test_change_contract_schemas.py
  - tests/qa/test_change_contracts.py
acceptance_source: manual
language_source: en
---

# ADR-042 Change Contract Gate Specification

## 1. Change Summary

This spec adds a baseline-aware Change Contract gate to the existing ADR-042
governance tooling. Current ADR/spec frontmatter records long-term governed
surfaces through `governs` and `planned_governs`. That metadata is necessary but
does not record per-change intent: what the change adds, changes, removes,
retains, forbids, or proves through a live entrypoint.

The Change Contract layer records that per-change intent and validates it
through `full_audit` and `gate_record check`. The design must reuse existing
ADR/spec frontmatter as the authoritative governance index. It must not create a
second independent governance system.

Initial rollout is baseline-aware. Existing findings are recorded in a committed
baseline and are grandfathered only when unchanged. New findings, expanded
findings, expired waivers, and touched baseline findings without renewed
justification block CI.

## 2. User Scenarios & Testing

### User Story 1 - ADR/spec changes declare executable change intent (Priority: P1)

Why this priority: ADR/spec frontmatter can say which surfaces a document
governs, but it cannot say what a specific change intends to add, modify,
delete, retain, forbid, or verify.

Independent Test: Add a fixture implementation-affecting spec without a change
contract and verify the checker emits a blocking missing-contract finding.

Acceptance Scenarios:

1. Given a new implementation-affecting ADR or spec, when no change contract or
   explicit N/A reason is declared, then the checker fails.
2. Given a docs-only ADR or spec, when it declares `change_contract:
   not_applicable` with a rationale, then the checker passes.
3. Given a change contract that declares a changed surface outside the owning
   frontmatter `governs` or `planned_governs`, then the checker fails with
   `change-contract.surface-outside-governance`.

### User Story 2 - Existing repository debt is baselined instead of blocking adoption (Priority: P2)

Why this priority: The repository already contains legacy compatibility paths,
historical drift, and advisory dead-code findings. The new gate must prevent
regressions without requiring unrelated cleanup before adoption.

Independent Test: Create a baseline fixture with one known finding; verify the
unchanged finding passes, while a new similar finding fails.

Acceptance Scenarios:

1. Given a finding recorded in the committed baseline, when the same finding
   appears unchanged, then it is reported as grandfathered and does not block
   CI.
2. Given a new finding not present in the baseline, when the checker runs, then
   CI fails.
3. Given a baseline finding in a touched surface, when it is not fixed, then the
   checker requires renewed justification or an issue-backed waiver.

### User Story 3 - New implementation surfaces must be production-reachable or registered (Priority: P3)

Why this priority: A module or frontend component can have unit tests and still
remain unused by the live product.

Independent Test: Add a fixture module or component referenced only by tests and
declare it as an added surface; verify the checker reports an orphaned
implementation finding.

Acceptance Scenarios:

1. Given a declared added Python module, when no production root or registered
   extension point can reach it, then the checker fails.
2. Given a declared frontend component, when it is only imported by tests, then
   the checker fails.
3. Given a declared plugin, package, tool, or extension point, when its
   registration is missing or unresolvable, then the checker fails.

### User Story 4 - Retained compatibility surfaces are explicit and expiring (Priority: P4)

Why this priority: Temporary adapters and compatibility routes are a common
source of incomplete migrations. They must be visible, issue-backed, and
reviewable.

Independent Test: Add a contract with a retained legacy surface that lacks an
issue or reason; verify the checker fails.

Acceptance Scenarios:

1. Given a retained legacy surface, when it lacks `reason`, `owner`, or `issue`,
   then the checker fails.
2. Given a retained legacy surface with an expired `expires` condition, when the
   checker runs, then CI fails.
3. Given a forbidden production reference that appears only in tests or docs,
   when the contract allows that scope, then the checker does not fail.

### Edge Cases

- Dynamic imports may be validated by explicit entrypoint or canary
  declarations instead of static reachability.
- Deleted production surfaces may remain in tests, docs, changelog history, or
  migration notes when explicitly allowed by scope.
- A change contract may be physical YAML under `docs/change-contracts/` or an
  equivalent normalized object loaded from future SpecKit metadata.
- Baseline identity must be stable across unrelated line-number churn where
  possible.
- Generated files must not require hand-authored contracts unless the generated
  artifact is the public surface being changed.
- Docs-only changes may declare `not_applicable`, but the rationale must be
  explicit and machine-readable.

## 3. Requirements

### Functional Requirements

- FR-001: ADR/spec frontmatter must be able to link to a change contract file
  or declare a structured N/A reason.
- FR-002: Change contracts must classify surfaces as `added`, `changed`,
  `removed`, or `retained`.
- FR-003: Every contract surface must be covered by the parent ADR/spec
  `governs` or `planned_governs`.
- FR-004: Retained legacy surfaces must declare `reason`, `owner`, `issue`, and
  optional `expires`.
- FR-005: The checker must support `baseline_policy.mode:
  no_new_violations`.
- FR-006: New findings not present in the committed baseline must block merge.
- FR-007: Existing baseline findings must not block merge when unchanged.
- FR-008: Touched baseline findings must require resolution or renewed
  justification.
- FR-009: Forbidden production references must be checked separately from docs,
  tests, and generated history references.
- FR-010: Added implementation surfaces must be reachable from declared
  production roots, registered extension points, or required canaries.
- FR-011: Required canaries must be declared for public API, UI, CLI, plugin,
  workflow-runtime, and external-integration surfaces.
- FR-012: The checker must integrate with `full_audit`.
- FR-013: `gate_record check` must select the change-contract check for
  ADR/spec, architecture, governance, and broad refactor diffs.
- FR-014: The first rollout must be baseline-aware and must not require
  immediate cleanup of existing repository debt.
- FR-015: Contract findings must use stable identities so baseline
  reconciliation is deterministic.
- FR-016: Contract waivers must include owner, issue, reason, and optional
  expiry.
- FR-017: The checker must report a contract surface outside parent governance
  as a blocking error.
- FR-018: The checker must not treat the change contract as replacing
  `governs`; frontmatter remains the long-term governance index.

### Key Entities

`ChangeContract` describes per-change intent:

| Field | Meaning |
|---|---|
| `id` | Stable contract id matching or referencing an ADR/spec id. |
| `parent` | ADR or spec path that owns this contract. |
| `change_kind` | `additive`, `migration`, `refactor`, `removal`, `compatibility`, or `docs_only`. |
| `surfaces.added` | Surfaces newly introduced by this change. |
| `surfaces.changed` | Existing surfaces modified by this change. |
| `surfaces.removed` | Surfaces expected to disappear from production code. |
| `surfaces.retained` | Legacy or compatibility surfaces intentionally kept. |
| `forbidden_prod_references` | Symbols, imports, routes, files, or patterns forbidden in production code. |
| `required_reachability` | New surfaces and the production roots or registrations that must reach them. |
| `required_canaries` | Test or smoke evidence required for public or live behavior. |
| `waivers` | Narrow exceptions with owner, issue, reason, and expiry. |
| `baseline_policy` | Baseline behavior, initially `no_new_violations`. |

`ChangeSurface` identifies one target:

| Field | Meaning |
|---|---|
| `kind` | `module`, `symbol`, `file`, `glob`, `route`, `entry_point`, `frontend_component`, `cli`, or `tool`. |
| `target` | Normalized target identifier. |
| `scope` | `production`, `test`, `docs`, `generated`, or `any`. |
| `reason` | Required for retained and waiver surfaces. |
| `issue` | Required for retained legacy surfaces and waivers. |

`ChangeContractBaseline` records grandfathered findings:

| Field | Meaning |
|---|---|
| `version` | Baseline schema version. |
| `generated_from` | Commit SHA or audit source. |
| `findings` | Stable finding identities allowed to remain unchanged. |
| `expires` | Optional expiry for temporary baseline entries. |

## 4. Implementation Plan

### 4.1 Technical Approach

Extend the existing ADR-042 audit system rather than creating a separate gate.
ADR/spec frontmatter remains the long-term governance index. A linked change
contract records per-change action metadata. `full_audit` loads contracts,
validates schema and governance coverage, checks forbidden references, checks
basic reachability, reconciles findings against a committed baseline, and
reports blocking findings through the normal audit report model.

The first reachability implementation should be conservative:

1. Python modules: import graph rooted at declared production roots.
2. Frontend components: TypeScript import graph rooted at declared UI roots.
3. Entry points: parse Python packaging metadata and registered group names.
4. Dynamic cases: require explicit canary or entrypoint declarations.

### 4.2 Affected Files

| File | Action | Rationale |
|---|---|---|
| `src/scistudio/qa/schemas/change_contracts.py` | Create | Typed schema for contracts, surfaces, waivers, and baseline policy. |
| `src/scistudio/qa/audit/change_contracts.py` | Create | Contract loading, checking, and baseline reconciliation. |
| `docs/change-contracts/` | Create | Per-ADR/spec contract files. |
| `docs/audit/baselines/change-contract-baseline.json` | Create | Initial grandfathered finding baseline. |
| `src/scistudio/qa/audit/full_audit.py` | Modify | Add change-contract child report. |
| `src/scistudio/qa/governance/gate_record/checks.py` | Modify | Add selectable check name and diff-surface routing. |
| `docs/ai-developer/specific_rules/document-standards.md` | Modify | Document contract requirements and N/A rules. |
| `tests/qa/test_change_contracts.py` | Create | Schema, checker, baseline, and integration tests. |

### 4.3 Implementation Sequence

1. Define `ChangeContract`, `ChangeSurface`, waiver, and baseline schemas.
2. Add contract discovery from ADR/spec frontmatter.
3. Add schema validation and structured N/A validation.
4. Add governance coverage validation against parent `governs` and
   `planned_governs`.
5. Add forbidden production reference scanning.
6. Add basic reachability checks for Python imports, frontend imports, and
   declared entrypoints.
7. Add baseline reconciliation.
8. Wire checker into `full_audit`.
9. Wire check selection into `gate_record check`.
10. Generate the initial committed baseline.
11. Document authoring rules and examples.

### 4.4 Verification Plan

- Unit tests for valid and invalid contract schemas.
- Fixture tests for missing contract, valid N/A, and surface outside governance.
- Baseline tests for unchanged existing findings, new findings, and touched
  baseline findings.
- Forbidden-reference tests across production, test, docs, and generated scopes.
- Reachability tests for Python and frontend orphaned surfaces.
- Entry point tests for missing or unresolvable registrations.
- Full audit integration test proving the child report runs.
- Gate-record test proving relevant diffs select the check.

### 4.5 Risks And Rollback

Risk: The first checker produces too much noise.

Mitigation: Start with `no_new_violations`, committed baselining, and limited
blocking rules.

Risk: Reachability analysis gives false positives for dynamic loading.

Mitigation: Allow explicit entrypoint or canary declarations as the validation
path for dynamic cases.

Risk: Contracts duplicate frontmatter.

Mitigation: Keep frontmatter as ownership and governance metadata. Keep
contracts as per-change action metadata. Add a checker rule requiring contract
surfaces to be covered by frontmatter.

Risk: Waivers become permanent.

Mitigation: Require owner, issue, reason, and optional expiry; fail expired
waivers.

Rollback: Disable the `change_contracts` child report in `full_audit` while
leaving schemas and contract files in place. Existing frontmatter, doc drift,
closure, and signature drift checks continue unchanged.

## 5. Success Criteria

### Measurable Outcomes

- SC-001: Implementation-affecting ADR/spec changes fail without a linked
  change contract or explicit N/A reason.
- SC-002: Existing baseline findings do not block initial adoption.
- SC-003: New forbidden production references block CI.
- SC-004: Added surfaces declared in contracts must be production-reachable,
  registered, or covered by canary evidence.
- SC-005: Retained legacy surfaces require issue-backed justification.
- SC-006: Contract surfaces outside parent governance are rejected.
- SC-007: `full_audit` reports change-contract findings.
- SC-008: `gate_record check` selects the change-contract check for relevant
  diffs.
- SC-009: The baseline can be regenerated intentionally, but ordinary PRs
  cannot grow it without owner-approved scope.

## 6. Assumptions

- ADR/spec frontmatter remains the authoritative long-term governance index.
- Change contracts are per-change evidence, not a replacement for `governs`.
- Initial rollout should prevent new drift, not clean all historical debt.
- Some dynamic behavior cannot be inferred statically and must be validated
  through entrypoint or canary declarations.
- A future implementation issue will decide whether contracts live only under
  `docs/change-contracts/` or may also be generated from SpecKit metadata.
