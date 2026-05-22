---
adr: 42
addendum: 4
title: "Test Engineer AI Persona"
status: Accepted
date_created: 2026-05-22
date_accepted: 2026-05-22
date_superseded: null

supersedes: []
superseded_by: null
related: [42]
closes_issues: [1466]
tracking_issue: 1467

is_code_implementation: true
governs:
  modules:
    - scistudio.qa.governance
    - scistudio.qa.governance.gate_record
  contracts:
    - scistudio.qa.governance.persona_policy.check
    - scistudio.qa.governance.gate_record.models.GateRecord
    - scistudio.qa.governance.gate_record.cli.main
    - scistudio.qa.governance.gate_record.validation.validate_gate_record
  entry_points: []
  files:
    - docs/adr/ADR-042-addendum4.md
    - docs/specs/adr-042-test-engineer-persona.md
    - docs/adr/ADR-042.md
    - docs/specs/adr-042-ai-governance-tools.md
    - docs/ai-developer/rules.md
    - docs/ai-developer/specific_rules/gated-workflow.md
    - docs/ai-developer/specific_rules/agent-dispatch.md
    - docs/ai-developer/templates/agent-dispatch-*.md
    - docs/ai-developer/checklists/agent-manager-rules-review.md
    - docs/ai-developer/skills/scistudio-e2e-test/SKILL.md
    - src/scistudio/qa/governance/persona_policy.py
    - src/scistudio/qa/governance/gate_record/**
    - tests/qa/test_persona_policy.py
    - tests/qa/test_gate_record.py
    - tests/qa/test_gate_record_ci.py
  excludes: []

tests:
  - tests/qa/test_persona_policy.py
  - tests/qa/test_test_engineer_scope_guard.py
  - tests/qa/test_gate_record.py
  - tests/qa/test_gate_record_ci.py

agent_editable: false
assisted_by:
  - "Codex:gpt-5"

phase: planning
tags: [qa, ai-governance, persona, testing, e2e, runtime-validation]
owner: "@jiazhenz026"
co_authors: ["@codex"]
language_source: en
translations: []
---

# ADR-042 Addendum 4: Test Engineer AI Persona

## 1. Decision Summary

This addendum proposes a fifth ADR-042 AI persona, `test_engineer`, for
test architecture, test design, regression coverage, runtime validation, and
end-to-end verification. The new persona is evidence-producing and
coverage-building. It is not feature-owning.

The `test_engineer` persona MUST NOT modify production code by default. When it
finds a product defect, it records executable evidence, failing tests, runtime
validation output, e2e evidence, and findings; production fixes remain owned by
`implementer` unless the owner or manager explicitly amends scope and persona.

| Decision | Change | Enforcement target | Detailed section |
|---|---|---|---|
| D1. Add `test_engineer` as a formal persona | ADR-042 Section 7.3 changes from four repository personas to five | Persona policy and AI developer rules | Section 3 |
| D2. Keep test engineering separate from production fixes | The persona may write tests, fixtures, test utilities, validation scripts, e2e scenarios, and test reports, but not production runtime/API/frontend code by default | Gate scope, dispatch prompts, review | Section 4 |
| D3. Update committed gate records to carry persona | Gate records must record `persona`; the CLI must accept `--persona` on `start` | `gate_record` CLI/schema/validation | Section 5 |
| D4. Do not add a new task kind | `test_engineer` is a persona, not a task kind; existing task kinds remain sufficient | Gate CLI task-kind list | Section 5 |
| D5. Add a test-engineering rule document and runtime skill pointers | Every supported runtime receives a `test-engineer` skill that points to canonical docs | `persona_policy` and `skill_pointer_sync` | Section 6 |
| D6. Make runtime validation and e2e first-class test-engineer work | Scenario files, browser evidence, runtime probes, API/schema checks, and validation matrices are owned test artifacts | Dispatch and e2e docs | Section 7 |
| D7. Add a persona-scoped test-engineer write guard | When `persona == test_engineer`, non-test and non-validation-evidence changes are blocked unless explicitly amended by the owner or manager | Local hooks and CI gate validation | Section 8 |

### 1.1 Problems Addressed

| Problem | Risk | Decision | Detailed section |
|---|---|---|---|
| Testing work is split between implementer, manager, and audit reviewer | Coverage gaps are noticed late, e2e evidence becomes manager-only, and test architecture lacks a clear owner | Add `test_engineer` as a dedicated persona | Section 3 |
| Audit reviewers can identify missing tests but are read-only by default | Findings remain prose-only unless an implementer is separately assigned | Let test engineers add tests and validation artifacts while remaining outside production-code fixes | Section 4 |
| Implementers can add tests but are biased toward proving their implementation | Tests may mirror implementation shape instead of testing the contract | Assign independent test design and test-layer ownership to `test_engineer` | Section 7 |
| Manager agents coordinate e2e but should not be the testing specialist | PR readiness depends on one coordinator's manual testing discipline | Make runtime validation and e2e executable evidence a test-engineer responsibility | Section 7 |
| Current committed gate-record CLI does not record persona | `persona_policy` cannot validate the selected persona from durable gate evidence | Add `persona` to `GateRecord` and `--persona` to `gate_record start` | Section 5 |
| A test engineer could accidentally become an implementer | The agent may fix production code to make tests pass, weakening independence | Define a hard no-production-code default and escalation path | Section 4 |
| Prompt-only boundaries are not enough to keep test engineers out of product code | A test engineer can accidentally stage runtime, API, or frontend behavior changes while chasing a failing test | Add a deterministic `test_engineer_scope_guard` hook and CI check | Section 8 |

## 2. Scope

This addendum changes the AI developer governance model. It does not implement
the persona. Implementation is tracked by issue #1467.

In scope:

- adding the `test_engineer` persona to ADR-042 governance;
- defining its authority, allowed artifacts, and stop conditions;
- defining the gate workflow and CLI impact;
- defining the expected docs, runtime skills, tests, and CI validation updates;
- defining how test-engineer work interacts with runtime validation and e2e.

Out of scope:

- changing product runtime behavior;
- fixing production defects found by a test engineer;
- adding a new task kind;
- changing branch protection, Sentrux semantics, full-audit semantics, or
  administrator bypass labels;
- making e2e mandatory for every PR.

## 3. Persona Contract

ADR-042 Section 7.3 is extended from four personas to five:

| Persona | Use | Required skill | Root policy |
|---|---|---|---|
| `test_engineer` | Design test architecture and layers, design test cases, add tests and fixtures, run runtime validation, run e2e, report coverage and validation evidence | `test-engineer` | Must obey root `AGENTS.md`, gate scope, no-production-code default, test-quality rules, runtime validation evidence rules, and e2e evidence rules |

The existing four personas remain unchanged:

- `manager`
- `implementer`
- `adr_author`
- `audit_reviewer`

Every AI task still declares exactly one persona. If a task begins as
`test_engineer` and later needs a production fix, the task must stop and either:

1. hand the defect to an `implementer`, or
2. receive an explicit owner or manager scope/persona amendment before any
   production code is edited.

The `test_engineer` persona is AI-runtime agnostic. Codex, Claude Code, Gemini,
local CLI agents, and future agent runtimes use the same persona name and the
same policy checks.

## 4. Production-Code Boundary

The `test_engineer` persona MUST NOT modify production code by default.

For this addendum, production code means code or assets that implement product
behavior for users or runtime execution, including:

- `src/scistudio/**` except repository QA/governance/test-tooling modules
  explicitly included in the gate scope;
- `frontend/src/**` product components, hooks, runtime state, API clients, and
  UI behavior;
- package metadata or build configuration when the purpose is to change product
  behavior;
- workflow runtime, block registry, API routes, MCP tools, data model, lineage,
  scheduler, plugin, or frontend production surfaces.

Allowed default write surfaces for `test_engineer` include:

- `tests/**`;
- frontend test and e2e paths that match explicit test-only patterns:
  `frontend/**/*.test.*`, `frontend/**/*.spec.*`, `frontend/**/__tests__/**`,
  `frontend/**/__fixtures__/**`, `frontend/**/__mocks__/**`,
  `frontend/e2e/**`, `frontend/tests/**`, `frontend/test/**`,
  `frontend/playwright.config.*`, `frontend/vitest.config.*`, and
  `frontend/vitest.setup.*`;
- `docs/ai-developer/e2e/**` scenario files and e2e verdicts;
- `docs/audit/**` test reports and validation reports;
- test-only fixtures, golden files, mocks, sample projects, and test data;
- runtime validation scripts when they are test harnesses and do not change
  product runtime behavior;
- `src/scistudio/qa/**` only when the issue explicitly assigns QA/governance or
  validation tooling changes.

If a `test_engineer` discovers that production behavior is wrong, the expected
output is a finding plus evidence, not a product fix. Acceptable evidence
includes a failing test, a runtime validation transcript, API/schema mismatch,
browser screenshot, Playwright trace, console/network log, or a concise
reproduction note.

## 5. Gate Workflow And CLI Impact

Yes: the gate workflow CLI and schema must change if `test_engineer` is accepted
as a formal persona.

ADR-042 and Addendum 1 require agents to choose a persona, and `persona_policy`
is supposed to verify that choice. The current committed gate-record CLI
records `task_kind` but does not record `persona`. That means a durable
committed gate record cannot currently prove whether work was performed as
`manager`, `implementer`, `adr_author`, `audit_reviewer`, or the proposed
`test_engineer`.

The implementation must therefore update the committed gate workflow:

| Surface | Required change | Reason |
|---|---|---|
| `GateRecord` schema | Add `persona: manager|implementer|adr_author|audit_reviewer|test_engineer` | Make persona durable PR evidence |
| `gate_record start` CLI | Add required `--persona <persona>` | Ensure every gate record captures the chosen persona at stage 1 |
| Gate validation | Reject missing or unsupported personas | Prevent unreviewable AI role drift |
| `persona_policy.check` | Accept `test_engineer` and require `test-engineer` skill | Align code with ADR-042 Section 7.3 as amended |
| PR/CI gate validation | Validate persona from committed gate record | Make CI, not chat, the enforcement boundary |
| Gate examples and docs | Update all command examples to include `--persona` | Prevent agents from following stale procedures |

No new task kind is required. `test_engineer` work can use existing task kinds:

| Work shape | Task kind |
|---|---|
| Add or improve tests for an existing bug or regression issue | `bugfix` when the PR closes the bug with test evidence only, or `maintenance` when the work is coverage hardening |
| Build or adjust test harness, validation tooling, or e2e infrastructure | `maintenance` |
| Write test architecture docs or validation plan docs | `docs` |
| Coordinate multiple test engineers or combine test/e2e evidence | `manager` |

Commit trailers do not need a new mandatory `Persona:` trailer in this
addendum. `Gate-Record`, `Task-Kind`, `Issue`, and `Assisted-by` remain the
commit trailer set; persona is stored in the committed gate record. A future
addendum may add a `Persona:` trailer if reviewers need faster commit-log
filtering, but it is not required for correctness.

## 6. Documentation, Skill, And Policy Impact

Implementation of this addendum must update all persona lists and runtime
pointers at equivalent fidelity.

| Artifact | Required change |
|---|---|
| `docs/ai-developer/rules.md` | Add `test_engineer` to the required persona list and routing table |
| `docs/ai-developer/specific_rules/gated-workflow.md` | Add `test_engineer` to persona selection and `gate_record start --persona` examples |
| `docs/ai-developer/specific_rules/agent-dispatch.md` | Allow managers to dispatch `test_engineer`; require write sets to exclude production code by default |
| `docs/ai-developer/specific_rules/test-engineering.md` | Create canonical rules for test architecture, test design, runtime validation, e2e, evidence, and production-code stop conditions |
| `docs/ai-developer/personas/test-engineer.md` | Create the persona guide |
| `docs/ai-developer/templates/agent-dispatch-prompt-template.md` | Add `test_engineer` as a non-audit dispatch persona and include production-code stop conditions |
| `docs/ai-developer/templates/agent-dispatch-checklist-template.md` | Add test-engineer rows/status expectations and evidence fields where needed |
| `docs/ai-developer/checklists/agent-manager-rules-review.md` | Register the new persona docs and skills |
| `.agents/skills/test-engineer/SKILL.md` | Add runtime-neutral skill pointer |
| `.codex/skills/test-engineer/SKILL.md` | Add Codex skill pointer |
| `.claude/skills/test-engineer/SKILL.md` | Add Claude skill pointer |
| `docs/ai-developer/skills/scistudio-e2e-test/SKILL.md` | Add `test_engineer` as a related persona |

Skill files must stay pointer-only. They must not duplicate policy or create a
runtime-specific rule that is absent from canonical docs.

## 7. Test Engineering Work Model

The `test_engineer` persona owns the test evidence path for a task. Typical
outputs include:

- test architecture and layer plans;
- test matrices mapped to ADR/spec/issue requirements;
- unit, contract, integration, frontend, runtime validation, and e2e tests;
- fixtures, sample projects, golden files, mocks, and test helpers;
- runtime validation scripts and reports;
- e2e scenario files, screenshots, traces, console/network evidence, and
  verdicts;
- coverage gap analysis and risk classification;
- failing tests that demonstrate a bug for implementer handoff.

The expected testing layers are:

| Layer | Purpose | Example evidence |
|---|---|---|
| Unit | Local behavior of a function, class, parser, or helper | Focused `pytest` or Vitest tests |
| Contract | Stable API/schema/runtime boundary behavior | API schema assertions, block schema contracts, event/state-machine tests |
| Integration | Multiple backend/frontend/runtime components interacting | Backend workflow execution tests, API plus engine tests |
| Runtime validation | Real runtime behavior beyond static audit | run status probes, backend truth endpoints, artifact checks, lineage checks |
| Frontend validation | UI behavior at component or browser-test level | Vitest, Playwright, DOM state, console/network evidence |
| E2E | User-observable flow through the real app | scenario file, screenshots, trace, pass/fail verdict |
| Regression | Reproduce a known issue and lock the fix path | failing-before/passing-after test or preserved failing evidence |

Runtime validation is not a synonym for `full_audit`. ADR-042 full audit covers
static governance, frontmatter, facts, signatures, closure, documentation drift,
architecture drift, and related checks. Runtime validation must execute or
observe the runtime behavior being claimed.

## 8. Test Engineer Scope Guard

Implementation of this addendum MUST add a persona-scoped deterministic guard
named `test_engineer_scope_guard`.

The guard runs whenever a gate record declares `persona == "test_engineer"`.
It must run in local hook paths and CI gate validation. It may be implemented as
a standalone audit module, a gate-record validation child, or both, but the
public check name must remain stable so reports can cite it.

The guard blocks changed files outside the test-engineer artifact allowlist.

Allowed by default:

- `tests/**`;
- `frontend/**/*.test.*`;
- `frontend/**/*.spec.*`;
- `frontend/**/__tests__/**`;
- `frontend/**/__fixtures__/**`;
- `frontend/**/__mocks__/**`;
- `frontend/e2e/**`;
- `frontend/tests/**`;
- `frontend/test/**`;
- `frontend/playwright.config.*`;
- `frontend/vitest.config.*`;
- `frontend/vitest.setup.*`;
- `docs/ai-developer/e2e/**`;
- `docs/audit/**` validation reports and test reports;
- test fixtures, golden files, sample projects, and generated test evidence
  under repository paths designated for tests or audit evidence;
- `src/scistudio/qa/**` only when the gate record explicitly includes QA,
  governance, or validation-tooling scope.

Blocked by default:

- product runtime code under `src/scistudio/**`;
- frontend product code under `frontend/src/**` unless the exact path also
  matches one of the explicit frontend test-file or test-directory patterns
  above; a repo-wide `frontend/**` allowlist is not permitted;
- workflow runtime, block, API, MCP, data model, lineage, scheduler, plugin, or
  product UI implementation files;
- package/build/dependency changes whose purpose is product behavior rather
  than test execution;
- governance or CI changes unless the owner directive explicitly assigns test
  governance/tooling work.

Escape path:

1. The test engineer stops before editing the blocked path.
2. The manager or owner either assigns an `implementer` production-code fix or
   amends the gate record with a specific allowed path and rationale.
3. The amended gate must state why the change is test tooling rather than a
   production fix, or must explicitly change persona/scope for production code.

The guard must report findings with enough evidence for reviewers to see:

- persona;
- blocked path;
- matched reason or missing allowlist match;
- whether a gate amendment attempted to allow the path;
- recommended handoff (`implementer` fix, manager amendment, or remove path).

The initial implementation should add:

- `src/scistudio/qa/governance/test_engineer_scope_guard.py`;
- `tests/qa/test_test_engineer_scope_guard.py`;
- integration in `gate_record pre-commit`, `pre-push`, `pr-ready`, and `ci`
  validation paths, or an equivalent shared validator called from those paths.

## 9. Verification Plan

The implementation issue #1467 must verify this addendum with at least:

- `tests/qa/test_persona_policy.py`: `test_engineer` is accepted, requires the
  `test-engineer` skill, and unsupported personas still fail.
- `tests/qa/test_test_engineer_scope_guard.py`: `test_engineer` changes to
  production code are blocked, test/e2e/audit evidence paths are allowed, and
  explicit amendments are reported correctly.
- `tests/qa/test_gate_record.py`: gate records require and validate `persona`.
- `tests/qa/test_gate_record_ci.py`: CI validation rejects missing or invalid
  gate-record persona data and invokes the test-engineer scope guard.
- Documentation checks for `docs/ai-developer/personas/test-engineer.md` and
  `docs/ai-developer/specific_rules/test-engineering.md`.
- Skill pointer checks across `.agents`, `.codex`, and `.claude`.
- A targeted e2e-skill metadata check or documentation check confirming
  `test_engineer` is a related persona for e2e work.
- ADR-042 full audit after docs and code changes.

Manual review must confirm that the new persona does not grant permission to
modify production code by default.

## 10. Implementation Sequence

Implement #1467 in this order:

1. Update `GateRecord` schema, CLI `start`, validators, and docs examples to
   record `persona`.
2. Update `persona_policy` and its tests for the five-persona set and
   `test-engineer` skill mapping.
3. Add `test_engineer_scope_guard` and integrate it with local and CI gate
   validation.
4. Add canonical test-engineer persona and test-engineering specific-rule docs.
5. Add runtime skill pointers in `.agents`, `.codex`, and `.claude`.
6. Update dispatch templates, checklist template, e2e skill metadata, and
   manager rules review checklist.
7. Run targeted QA tests.
8. Run ADR-042 full audit and record gate evidence.

This sequence intentionally updates gate/schema enforcement before adding broad
dispatch usage so that the new persona is machine-checkable as soon as agents
can select it.

## 11. Consequences And Risks

Positive consequences:

- Testing becomes an owned engineering function rather than an afterthought of
  implementation or audit.
- Runtime validation and e2e evidence become normal test artifacts.
- Implementers can receive higher-quality failing tests and reproduction
  evidence before fixing production code.
- Managers can dispatch testing work without blurring audit, implementation,
  and coordination responsibilities.

Risks:

- Adding a fifth persona increases governance surface area.
- A test engineer may need narrow test-tooling changes under `src/scistudio/qa`.
  Gate scope must distinguish those changes from production fixes.
- Dispatch prompts must be explicit enough to prevent accidental production
  code edits.
- Gate CLI/schema changes can temporarily break older records unless migration
  behavior is defined.

Migration guidance:

- Existing gate records without `persona` may remain valid as historical
  records if their schema version predates the implementation.
- New gate records after implementation must include `persona`.
- If the schema version changes, validation must document whether old records
  are grandfathered, migrated, or rejected only for new PRs.

## 12. Alternatives Considered

| Alternative | Rejected because |
|---|---|
| Keep testing under `implementer` | Implementers should test their own changes, but independent test architecture, runtime validation, and e2e ownership need a separate route |
| Keep testing under `audit_reviewer` | Audit reviewers are read-only by default; test engineers must be able to add tests and validation artifacts |
| Keep e2e under `manager` only | Managers coordinate readiness but should not be the only persona allowed to produce e2e evidence |
| Add a `test` task kind instead of a persona | The work type is role-specific; existing task kinds already express docs, maintenance, bugfix, and manager workflows |
| Let test engineers fix production bugs | That collapses the independence boundary with `implementer` and makes tests less trustworthy as external evidence |
| Rely on prompt instructions to block production changes | ADR-042 requires deterministic enforcement for AI failure modes; a hook/CI guard is needed |

## 13. Out Of Scope

This addendum does not:

- implement #1467;
- authorize test engineers to modify production code by default;
- remove implementer responsibility to add tests for implementation-category
  work;
- make audit reviewers responsible for writing tests;
- make managers responsible for detailed test architecture;
- require e2e for every PR;
- change Sentrux advisory semantics from Addendum 3;
- change semantic-duplication gate semantics from Addendum 2.
