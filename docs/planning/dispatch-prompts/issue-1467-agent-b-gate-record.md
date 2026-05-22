---
title: "Issue 1467 Agent B Gate Record Dispatch"
status: Draft
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
language_source: en
---

# Issue 1467 Agent B Gate Record Dispatch

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
- Agent branch: feat/issue-1467/gate-record-persona
- Agent worktree: C:/Users/jiazh/Desktop/workspace/SciStudio-issue1467-agent-b
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

- src/scistudio/qa/governance/gate_record/**
- tests/qa/test_gate_record.py
- tests/qa/test_gate_record_ci.py
- tests/qa/test_gate_record_hooks.py

You must not touch:

- src/scistudio/qa/governance/persona_policy.py
- src/scistudio/qa/governance/test_engineer_scope_guard.py
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

- Historical gate records may be grandfathered only if tests document the rule
  and new records require persona.

## Work To Do

1. Add `persona` to the gate-record model for new records using accepted values:
   `manager`, `implementer`, `adr_author`, `audit_reviewer`, `test_engineer`.
2. Add required `--persona <persona>` to `gate_record start` and persist it.
3. Update gate-record validation to reject missing/unsupported persona for new
   records while preserving a deliberate historical-record compatibility rule.
4. Wire validation so `persona == "test_engineer"` invokes
   `test_engineer_scope_guard` if the module is available in the integration
   branch. If you need the concrete guard API from agent A, stop and report the
   expected interface instead of editing agent A files.
5. Add focused tests for CLI/model/CI validation behavior.

## Required Tests And Checks

- `pytest tests/qa/test_gate_record.py tests/qa/test_gate_record_ci.py tests/qa/test_gate_record_hooks.py -q`
- `ruff check src/scistudio/qa/governance/gate_record tests/qa/test_gate_record.py tests/qa/test_gate_record_ci.py tests/qa/test_gate_record_hooks.py`
- `ruff format --check src/scistudio/qa/governance/gate_record tests/qa/test_gate_record.py tests/qa/test_gate_record_ci.py tests/qa/test_gate_record_hooks.py`

## Output Required

Before reporting done, provide:

- Changed file paths.
- Tests/checks run and results.
- Commit hash or branch pushed.
- Any blocker or scope issue.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file.
- Persona-policy or scope-guard implementation changes appear necessary.
- The task conflicts with AGENTS.md, ADR, spec, or gate record.
- Local checks fail for unclear reasons.
- Another agent's work blocks yours.
- You cannot add/update required tests.
```
