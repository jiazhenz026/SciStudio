---
title: "Issue 1467 Agent A Code Guard Dispatch"
status: Draft
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
language_source: en
---

# Issue 1467 Agent A Code Guard Dispatch

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: implement ADR-042 Addendum 4 test_engineer persona with code
  changes owned by implementation agents.
- Task kind: maintenance
- Persona: implementer
- Issue: #1467
- Issue URL: https://github.com/zjzcpj/SciStudio/issues/1467
- Umbrella PR: pending `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/issue-1467/test-engineer-persona
- Agent branch: feat/issue-1467/test-engineer-scope-guard
- Agent worktree: C:/Users/jiazh/Desktop/workspace/SciStudio-issue1467-agent-a
- Gate record: .workflow/records/1467-test-engineer-persona-implementation.json
- Checklist: docs/planning/adr-042-test-engineer-persona-implementation-checklist.md

## Required Rules

Read and follow:

- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/personas/implementer.md
- docs/specs/adr-042-test-engineer-persona.md
- docs/adr/ADR-042-addendum4.md

## Scope

You own only:

- src/scistudio/qa/governance/persona_policy.py
- src/scistudio/qa/governance/test_engineer_scope_guard.py
- tests/qa/test_persona_policy.py
- tests/qa/test_test_engineer_scope_guard.py

You must not touch:

- src/scistudio/qa/governance/gate_record/**
- docs/**
- .workflow/**
- .agents/**
- .codex/**
- .claude/**
- frontend/**
- src/scistudio/blocks/**
- src/scistudio/engine/**
- src/scistudio/api/**
- src/scistudio/core/**
- product runtime, block, scheduler, API, lineage, plugin, MCP, or frontend
  production behavior.

If you need an out-of-scope path, stop and report back. Do not edit it.

## Coordination

- You are not alone in this codebase.
- MUST work only on your assigned branch.
- MUST work only in your assigned worktree.
- MUST NOT use `pip install -e .`.
- Do not revert or overwrite other agents' work.
- Do not broaden scope.
- MUST target any PR to `track/issue-1467/test-engineer-persona`.
- MUST NOT target your PR to `main`.
- MUST NOT merge any PR unless the owner explicitly authorizes it.
- Edit only your checklist rows if you edit the checklist.

## TODO And Deferral Rule

Deferred work must be tracked in the repo.
Use `TODO(#1467): <reason>` and cite ADR-042 Addendum 4 or the implementation
spec. Do not leave hidden V1, MVP, or later work.

Known deferred items:

- N/A.

## Work To Do

1. Create or update persona-policy support so `test_engineer` is accepted as
   the fifth ADR-042 persona and maps to required skill `test-engineer`.
2. Implement `src/scistudio/qa/governance/test_engineer_scope_guard.py` as a
   deterministic path-classification guard for changed files when
   `persona == "test_engineer"`.
3. The frontend allowlist MUST use explicit patterns only:
   `frontend/**/*.test.*`, `frontend/**/*.spec.*`,
   `frontend/**/__tests__/**`, `frontend/**/__fixtures__/**`,
   `frontend/**/__mocks__/**`, `frontend/e2e/**`, `frontend/tests/**`,
   `frontend/test/**`, `frontend/playwright.config.*`,
   `frontend/vitest.config.*`, and `frontend/vitest.setup.*`.
   Do not implement `frontend/**` as an allowlist.
4. The guard MUST block product runtime paths, frontend production paths, and
   product build/package behavior by default.
5. Add focused tests for persona policy and scope-guard allow/block/amendment
   behavior.

## Required Tests And Checks

- `pytest tests/qa/test_persona_policy.py tests/qa/test_test_engineer_scope_guard.py -q`
- `ruff check src/scistudio/qa/governance/persona_policy.py src/scistudio/qa/governance/test_engineer_scope_guard.py tests/qa/test_persona_policy.py tests/qa/test_test_engineer_scope_guard.py`
- `ruff format --check src/scistudio/qa/governance/persona_policy.py src/scistudio/qa/governance/test_engineer_scope_guard.py tests/qa/test_persona_policy.py tests/qa/test_test_engineer_scope_guard.py`

## Output Required

Before reporting done, provide:

- Changed file paths.
- Tests/checks run and results.
- Commit hash or branch pushed.
- Any blocker or scope issue.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file.
- Gate-record validation changes appear necessary.
- The task conflicts with AGENTS.md, ADR, spec, or gate record.
- Local checks fail for unclear reasons.
- Another agent's work blocks yours.
- You cannot add/update required tests.
```
