---
title: "AI Test Engineering Specific Rules"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
language_source: en
---

# AI Test Engineering Specific Rules

## 1. Purpose

- Use these rules for AI-authored test engineering work.

- MUST also run `docs/ai-developer/specific_rules/gated-workflow.md`.

- MUST use `docs/ai-developer/personas/test-engineer.md` when the selected
  persona is `test_engineer`.

## 2. Allowed Work

- Test architecture and layer design.

- Test-case design and test matrices.

- Unit, contract, integration, frontend, runtime validation, e2e, and
  regression tests.

- Fixtures, mocks, golden files, sample projects, and test harnesses.

- Runtime validation reports, e2e scenario files, screenshots, traces, console
  logs, network logs, and audit evidence.

- QA/governance or validation tooling only when explicitly assigned by the
  issue, spec, owner, or manager.

## 3. Production-Code Stop Rules

- MUST NOT edit production code by default.

- MUST stop before changing product runtime, API, block, scheduler, lineage,
  plugin, MCP, frontend production UI, or product build/package behavior.

- MUST NOT fix a product bug just because a test exposes it.

- MUST hand product defects to an `implementer` with executable evidence, or
  wait for an owner or manager gate-record amendment that changes scope and
  persona authority.

- MUST treat `frontend/**` as too broad for allowlist use. Frontend write
  permission must use explicit test or e2e patterns such as `*.test.*`,
  `*.spec.*`, `__tests__`, `__fixtures__`, `__mocks__`, `frontend/e2e/**`,
  `frontend/tests/**`, and test runner config files.

## 4. Runtime Validation

- Runtime validation means executing or observing the behavior being claimed.

- Runtime validation is not the same as ADR-042 full audit.

- Acceptable runtime validation evidence includes command output, API/schema
  probes, backend truth endpoints, artifact checks, lineage checks, browser
  screenshots, traces, console logs, network logs, and e2e verdicts.

- Evidence must name the command or scenario, result, timestamp when relevant,
  and output path when an artifact is written.

## 5. Test Quality Rules

- Tests should target contracts, requirements, regressions, and user-observable
  behavior rather than implementation coincidences.

- Prefer focused tests with clear fixtures over broad tests that hide the
  assertion being made.

- A failing test that demonstrates a product bug is valid output, but the gate
  record or checklist must state whether the failing test is expected handoff
  evidence or must pass before merge.

- Do not weaken assertions, skip tests, or lower thresholds to make a gate pass
  unless the owner explicitly approved that scope and the deferral is tracked.

## 6. Required Evidence

- Record changed test paths.

- Record test commands and results.

- Record runtime validation or e2e artifact paths when produced.

- Record any product bug handoff with the failing test, reproduction command,
  or scenario evidence.

- Record N/A rationales for docs, changelog, e2e, or runtime validation when
  they are not required by the task.

## 7. Route

Use these rules with:

- `docs/ai-developer/rules.md`
- `docs/ai-developer/specific_rules/gated-workflow.md`
- `docs/ai-developer/personas/test-engineer.md`
- `docs/ai-developer/skills/scistudio-e2e-test/SKILL.md` when running live e2e
- `docs/ai-developer/specific_rules/agent-dispatch.md` when dispatched by a
  manager

ADR-042 Addendum 6 folds receipt behavior into the gate ledger. Record test
obligations and outcomes with `gate_record amend --test-path ... --check ...`,
then run `gate_record check` in the required mode so the ledger reconciles the
observed diff and required checks. Raw stdout/stderr transcripts may be kept
under ignored `.workflow/local/**` paths when a long test run needs local
evidence, but there is no separate `gate_receipt` command. The
`scripts/scistudio_pr_create.py` wrapper is the required final-PR entry point
for any test-engineering PR (see
`docs/ai-developer/specific_rules/gated-workflow.md` §3.7).
