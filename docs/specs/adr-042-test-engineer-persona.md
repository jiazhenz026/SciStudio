---
spec_id: adr-042-test-engineer-persona
title: "ADR-042 Test Engineer Persona Implementation Specification"
status: Planned
feature_branch: docs/issue-1466/adr-042-test-engineer-persona
created: 2026-05-22
input: "Owner-approved ADR-042 Addendum 4: add a test_engineer AI persona for test architecture, test design, test additions, runtime validation, and e2e evidence, with a hard no-production-code default and deterministic scope guard."
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
related_specs:
  - adr-042-ai-governance-tools
  - adr-042-gate-record-sentrux-workflow
scope:
  in:
    - Add `test_engineer` to ADR-042 persona policy and durable gate-record evidence.
    - Add a required `persona` field to new gate records and require `--persona` in `gate_record start`.
    - Add a deterministic `test_engineer_scope_guard` that blocks non-test and non-validation-evidence changes for `test_engineer`.
    - Add canonical test-engineer persona docs, test-engineering specific rules, and runtime skill pointers for supported runtimes.
    - Update dispatch templates, manager checklist templates, e2e skill metadata, and AI developer routing docs.
    - Add targeted QA tests for persona policy, gate record persona validation, and test-engineer scope guard behavior.
  out:
    - Modifying production runtime, API, frontend, block, scheduler, lineage, plugin, or MCP behavior to fix bugs found by test engineers.
    - Adding a new task kind.
    - Changing Sentrux advisory semantics, semantic-duplication semantics, or administrator bypass label names.
    - Making e2e mandatory for every PR.
governs:
  modules:
    - scistudio.qa.governance
    - scistudio.qa.governance.gate_record
  contracts:
    - scistudio.qa.governance.persona_policy.check
    - scistudio.qa.governance.test_engineer_scope_guard.check
    - scistudio.qa.governance.gate_record.models.GateRecord
    - scistudio.qa.governance.gate_record.cli.main
    - scistudio.qa.governance.gate_record.validation.validate_gate_record
  files:
    - docs/specs/adr-042-test-engineer-persona.md
    - docs/adr/ADR-042-addendum4.md
    - docs/ai-developer/rules.md
    - docs/ai-developer/specific_rules/gated-workflow.md
    - docs/ai-developer/specific_rules/agent-dispatch.md
    - docs/ai-developer/specific_rules/test-engineering.md
    - docs/ai-developer/personas/test-engineer.md
    - docs/ai-developer/templates/agent-dispatch-prompt-template.md
    - docs/ai-developer/templates/agent-dispatch-checklist-template.md
    - docs/ai-developer/checklists/agent-manager-rules-review.md
    - docs/ai-developer/skills/scistudio-e2e-test/SKILL.md
    - .agents/skills/test-engineer/SKILL.md
    - .codex/skills/test-engineer/SKILL.md
    - .claude/skills/test-engineer/SKILL.md
    - src/scistudio/qa/governance/persona_policy.py
    - src/scistudio/qa/governance/test_engineer_scope_guard.py
    - src/scistudio/qa/governance/gate_record/**
    - tests/qa/test_persona_policy.py
    - tests/qa/test_test_engineer_scope_guard.py
    - tests/qa/test_gate_record.py
    - tests/qa/test_gate_record_ci.py
tests:
  - tests/qa/test_persona_policy.py
  - tests/qa/test_test_engineer_scope_guard.py
  - tests/qa/test_gate_record.py
  - tests/qa/test_gate_record_ci.py
acceptance_source: adr
language_source: en
---

# ADR-042 Test Engineer Persona Implementation Specification

## 1. Change Summary

This spec implements ADR-042 Addendum 4. It adds `test_engineer` as a formal
AI persona for test architecture, test-layer design, test-case design, test
additions, runtime validation, and e2e evidence.

The persona is deliberately not a production-code fixer. A `test_engineer`
may create or update tests, fixtures, e2e scenarios, runtime validation
harnesses, QA reports, and test evidence. It must not modify product runtime,
API, frontend, block, scheduler, lineage, plugin, or MCP behavior by default.
When a test engineer finds a product defect, the expected output is executable
evidence and a handoff to `implementer`, unless the owner or manager explicitly
amends scope and persona.

The implementation must also close a current governance gap: committed gate
records record `task_kind` but not `persona`. Since ADR-042 requires persona
selection and `persona_policy` validation, new gate records must include a
durable `persona` field, and `gate_record start` must require `--persona`.

Finally, the implementation adds a deterministic
`test_engineer_scope_guard`. Prompt-only instructions are insufficient for this
boundary. When `persona == "test_engineer"`, local hooks and CI must block
changed files outside the test/evidence allowlist unless an explicit owner or
manager amendment authorizes the path.

## 2. User Scenarios & Testing

### User Story 1 - Gate records declare the test engineer persona (Priority: P1)

As a maintainer, I need every new gate record to state the agent persona so CI
can verify that `test_engineer` work is using the correct restrictions.

Why this priority: Without durable persona evidence, `persona_policy` and the
test-engineer scope guard cannot decide whether the PR should be treated as
test-engineer work.

Independent Test: Validate gate-record fixtures with missing persona, invalid
persona, and `test_engineer` persona.

Acceptance Scenarios:

1. Given `gate_record start --persona test_engineer`, when the record is
   written, then `persona` is stored in the committed JSON.
2. Given a new gate record without `persona`, when validation runs, then it
   fails for new-record schema validation.
3. Given `persona: freeform_agent`, when validation runs, then it fails with
   an unsupported-persona finding.

### User Story 2 - Test engineers cannot modify production code by default (Priority: P1)

As a repository owner, I need `test_engineer` changes to stay in test,
validation, and evidence paths unless a manager or owner explicitly amends
scope.

Why this priority: The persona's value depends on independence from production
fixes. If it can quietly change product code, it becomes another implementer
and weakens test evidence.

Independent Test: Run `test_engineer_scope_guard.check` against changed-file
fixtures for test paths, e2e paths, audit evidence paths, product source paths,
frontend product paths, QA tooling paths, and amended exceptions.

Acceptance Scenarios:

1. Given `persona: test_engineer` and changed `tests/engine/test_state.py`,
   when the guard runs, then it passes.
2. Given `persona: test_engineer` and changed
   `src/scistudio/engine/scheduler.py`, when the guard runs, then it fails.
3. Given `persona: test_engineer` and changed
   `src/scistudio/qa/governance/test_engineer_scope_guard.py` with the path
   explicitly included in the gate scope, when the guard runs, then it passes.
4. Given `persona: implementer`, when the same product source path changes,
   then `test_engineer_scope_guard` does not apply.

### User Story 3 - Persona policy recognizes the fifth persona (Priority: P1)

As an agent manager, I need runtime skill parity and persona validation to
accept `test_engineer` across supported runtime roots.

Why this priority: ADR-042 requires runtime-agnostic persona policy and skill
pointers. A new persona is incomplete until `.agents`, `.codex`, and `.claude`
can all load it at equivalent fidelity.

Independent Test: Run `persona_policy.check` fixtures for `test_engineer`,
missing test-engineer skill path, wrong required skill, and unsupported runtime
root.

Acceptance Scenarios:

1. Given `persona: test_engineer` and skill `test-engineer`, when
   `persona_policy` runs, then it passes.
2. Given `persona: test_engineer` and skill `implementation-worker`, when
   `persona_policy` runs, then it fails.
3. Given `.agents`, `.codex`, and `.claude` test-engineer skills, when
   skill-pointer checks run, then each points to canonical docs.

### User Story 4 - Managers can dispatch test engineers safely (Priority: P2)

As a manager agent, I need dispatch templates and checklists to express
test-engineer scope, stop conditions, and evidence expectations.

Why this priority: Test engineers will often be dispatched after specs, audits,
or implementation PRs. Their prompt must make the production-code boundary and
evidence outputs explicit.

Independent Test: Review template updates and run documentation checks that
validate persona references and canonical docs.

Acceptance Scenarios:

1. Given a non-audit dispatch prompt with `Persona: test_engineer`, when a
   manager fills it, then it contains test/evidence write sets and production
   code stop conditions.
2. Given a manager checklist, when a test-engineer row is added, then evidence
   fields can record tests, runtime validation, e2e reports, and blockers.

### User Story 5 - Runtime validation and e2e are test-engineer evidence (Priority: P2)

As a maintainer, I need runtime validation and e2e artifacts to be treated as
test-engineer outputs, distinct from static full audit.

Why this priority: ADR-042 full audit proves static governance consistency, not
runtime behavior. Test engineers need a clear route for executable validation.

Independent Test: Confirm e2e skill metadata includes `test_engineer` and that
test-engineering docs distinguish static audit from runtime validation.

Acceptance Scenarios:

1. Given an e2e scenario under `docs/ai-developer/e2e/**`, when a test engineer
   runs it, then the verdict and evidence are valid test artifacts.
2. Given a runtime validation report under `docs/audit/**`, when the scope
   guard runs, then the report path is allowed.

### Edge Cases

- A test engineer needs to add a helper under `src/scistudio/qa/**` for the
  guard or validation tooling itself.
- A test engineer finds a product bug and writes a failing test that now fails
  CI until an implementer fixes it.
- A historical gate record lacks `persona` because it predates this
  implementation.
- A frontend file under `frontend/src/**` is a test file, such as
  `*.test.tsx`, while adjacent product files are blocked.
- A manager intentionally changes persona from `test_engineer` to
  `implementer` for a follow-up fix.

## 3. Requirements

### Functional Requirements

- FR-001: `GateRecord` MUST include a `persona` field for new records.
- FR-002: The accepted persona values MUST be `manager`, `implementer`,
  `adr_author`, `audit_reviewer`, and `test_engineer`.
- FR-003: `gate_record start` MUST require `--persona` and write it to the
  committed record.
- FR-004: Gate validation MUST reject unsupported persona values.
- FR-005: The implementation MUST define whether historical records without
  `persona` are grandfathered, migrated, or rejected only for new PRs.
- FR-006: `persona_policy.check` MUST accept `test_engineer` only with the
  required skill `test-engineer`.
- FR-007: Runtime skill pointers for `.agents`, `.codex`, and `.claude` MUST
  exist and point to canonical AI developer docs.
- FR-008: `test_engineer_scope_guard.check` MUST run when
  `persona == "test_engineer"`.
- FR-009: `test_engineer_scope_guard.check` MUST not apply when persona is not
  `test_engineer`.
- FR-010: The scope guard MUST allow test files, fixtures, e2e scenarios,
  runtime validation reports, audit evidence, and explicitly scoped QA tooling.
- FR-011: The scope guard MUST block production source, frontend product code,
  runtime/API/MCP/block/scheduler/lineage/plugin/UI implementation files, and
  product-behavior build/package changes by default.
- FR-012: The scope guard MUST report blocked path, persona, allowlist decision,
  amendment state, and recommended handoff.
- FR-013: Local `pre-commit`, local `pre-push`, local `pr-ready`, and CI gate
  validation MUST invoke the guard or an equivalent shared validator.
- FR-014: `docs/ai-developer/personas/test-engineer.md` MUST define allowed
  work, prohibited production-code edits, evidence outputs, and stop
  conditions.
- FR-015: `docs/ai-developer/specific_rules/test-engineering.md` MUST define
  test architecture, test-case design, runtime validation, e2e, evidence, and
  handoff rules.
- FR-016: Dispatch templates MUST support `test_engineer` and include the
  no-production-code stop condition.
- FR-017: The e2e skill metadata MUST include `test_engineer` as a related
  persona.

### Key Entities

| Entity | Description | Attributes | Relationships |
|---|---|---|---|
| `Persona` | AI role declaration | name, required skill, canonical docs | Stored in `GateRecord`, checked by `persona_policy` |
| `GateRecord` | Committed AI work evidence | task id, task kind, persona, branch, issues, scope, stages, checks | Read by local hooks and CI |
| `TestEngineerScopeGuard` | Persona-scoped changed-file validator | persona, changed files, allowed patterns, blocked patterns, amendments | Runs from gate validation paths |
| `AllowedTestArtifact` | Path class that a test engineer may edit by default | path, class, rationale | Used by scope guard |
| `BlockedProductionSurface` | Product implementation path blocked for test engineers | path, matched rule, recommended handoff | Reported as findings |
| `TestEngineerSkill` | Runtime skill pointer | runtime root, skill path, canonical doc links | Checked by persona policy and skill pointer sync |
| `RuntimeValidationEvidence` | Runtime/e2e proof artifact | command, output path, verdict, logs/screenshots/traces | Recorded in gate checks, audit reports, or e2e scenario files |

## 4. Implementation Plan

### 4.1 Technical Approach

Treat `test_engineer` as a normal ADR-042 persona plus an additional
persona-scoped file guard.

Gate-record schema and CLI changes make persona durable. Persona policy changes
make the new role runtime-agnostic. The test-engineer scope guard enforces the
no-production-code default at the same boundaries already used by ADR-042 gate
validation: local pre-commit, pre-push, PR readiness, and CI.

The guard should use explicit path classification rather than vague string
matching. A small helper can classify paths as:

- allowed test artifact;
- allowed e2e artifact;
- allowed audit or runtime validation evidence;
- allowed explicitly scoped QA/governance tooling;
- blocked production source;
- blocked frontend product code;
- blocked product build/package behavior;
- unknown blocked path.

### 4.2 Affected Files

| File or glob | Action | Rationale |
|---|---|---|
| `src/scistudio/qa/governance/gate_record/models.py` | modify | Add `persona` to `GateRecord` |
| `src/scistudio/qa/governance/gate_record/cli.py` | modify | Require `--persona` on `start` |
| `src/scistudio/qa/governance/gate_record/stages.py` | modify | Persist persona during record creation |
| `src/scistudio/qa/governance/gate_record/validation.py` | modify | Validate persona and invoke test-engineer scope guard |
| `src/scistudio/qa/governance/persona_policy.py` | modify | Accept `test_engineer` and required skill mapping |
| `src/scistudio/qa/governance/test_engineer_scope_guard.py` | create | Implement persona-scoped path guard |
| `tests/qa/test_gate_record.py` | modify | Schema and CLI stage fixtures for persona |
| `tests/qa/test_gate_record_ci.py` | modify | CI validation rejects missing/invalid persona and applies guard |
| `tests/qa/test_persona_policy.py` | modify | Persona-policy fixtures for `test_engineer` |
| `tests/qa/test_test_engineer_scope_guard.py` | create | Guard allow/block/amendment coverage |
| `docs/ai-developer/personas/test-engineer.md` | create | Canonical persona guide |
| `docs/ai-developer/specific_rules/test-engineering.md` | create | Canonical task rules |
| `docs/ai-developer/rules.md` | modify | Persona list and routing table |
| `docs/ai-developer/specific_rules/gated-workflow.md` | modify | Add `--persona` to gate CLI examples |
| `docs/ai-developer/specific_rules/agent-dispatch.md` | modify | Add test-engineer dispatch and no-production-code rules |
| `docs/ai-developer/templates/agent-dispatch-prompt-template.md` | modify | Allow `test_engineer` and add stop condition |
| `docs/ai-developer/templates/agent-dispatch-checklist-template.md` | modify | Add test-engineer evidence expectations |
| `docs/ai-developer/checklists/agent-manager-rules-review.md` | modify | Register docs and runtime skills |
| `.agents/skills/test-engineer/SKILL.md` | create | Runtime-neutral pointer |
| `.codex/skills/test-engineer/SKILL.md` | create | Codex pointer |
| `.claude/skills/test-engineer/SKILL.md` | create | Claude pointer |
| `docs/ai-developer/skills/scistudio-e2e-test/SKILL.md` | modify | Add related persona |

### 4.3 Implementation Sequence

1. Add `persona` to gate-record model fixtures and decide historical-record
   compatibility.
2. Add `--persona` to `gate_record start` and update all examples/tests.
3. Update `persona_policy` and runtime skill mappings.
4. Create `test_engineer_scope_guard` with path-classification unit tests.
5. Invoke the guard from gate validation paths.
6. Add canonical persona docs and test-engineering rules.
7. Add runtime skill pointers.
8. Update dispatch templates, manager checklist template, e2e metadata, and
   manager rules review checklist.
9. Run targeted QA tests and full audit.

### 4.4 Verification Plan

Run:

```bash
pytest tests/qa/test_persona_policy.py tests/qa/test_test_engineer_scope_guard.py tests/qa/test_gate_record.py tests/qa/test_gate_record_ci.py -q
```

Run docs/governance checks:

```bash
python -m scistudio.qa.audit.frontmatter_lint docs/adr/ADR-042-addendum4.md docs/specs/adr-042-test-engineer-persona.md --repo-root . --format text
python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/adr-042-test-engineer-persona-implementation-full-audit.json
```

If frontend/e2e docs or test files are touched in implementation, also run the
relevant frontend checks declared by the implementation gate record.

### 4.5 Risks And Rollback

Risks:

- Requiring `persona` may break old gate-record fixtures or in-flight PRs.
- Path classification can be too strict and block legitimate test tooling.
- Path classification can be too loose and permit product changes.
- Dispatch docs may drift from actual guard behavior.

Rollback:

- If the schema change disrupts historical records, grandfather records whose
  schema version predates the implementation while requiring persona for new
  records.
- If the guard blocks legitimate test tooling, add explicit allowlist entries
  through code and tests, not prompt-only exceptions.
- If a production-code change is needed, change persona/scope through manager
  workflow and assign an implementer.

## 5. Success Criteria

### Measurable Outcomes

- SC-001: `gate_record start --persona test_engineer` creates a valid gate
  record containing `persona: test_engineer`.
- SC-002: New gate records missing `persona` fail validation.
- SC-003: `persona_policy.check` accepts `test_engineer` with `test-engineer`
  skill and rejects mismatched skills.
- SC-004: `test_engineer_scope_guard` allows representative test, e2e, audit,
  fixture, and explicitly scoped QA-tooling paths.
- SC-005: `test_engineer_scope_guard` blocks representative product source,
  frontend product, runtime/API/MCP/block/scheduler/lineage/plugin/UI paths.
- SC-006: Gate validation invokes the guard in local and CI validation paths.
- SC-007: Runtime skill pointers exist for `.agents`, `.codex`, and `.claude`.
- SC-008: Canonical docs define the no-production-code default and handoff path.
- SC-009: Targeted QA tests and ADR-042 full audit pass.

## 6. Assumptions

- The owner has accepted ADR-042 Addendum 4.
- `test_engineer` is a persona, not a task kind.
- Production fixes remain implementer-owned unless owner or manager explicitly
  amends scope/persona.
- Runtime validation and e2e evidence are test artifacts, while ADR-042 full
  audit remains static governance evidence.
- Supported runtime roots remain `.agents`, `.codex`, `.claude`, and `.gemini`
  where present; this implementation must at least keep existing supported
  repository roots at equivalent fidelity.
