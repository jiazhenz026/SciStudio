---
title: "Agent Dispatch Work Prompt Template"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
language_source: en
---

# Agent Dispatch Work Prompt Template

Use this template for manager-dispatched non-audit work.
Fill every placeholder before dispatch.

```markdown
[DISPATCH-TEMPLATE-V1: <manager|implementer|adr_author|test_engineer|fix>]

## Task Identity

- Repository: SciStudio
- Owner request: <one sentence>
- Task kind: <feature|bugfix|hotfix|refactor|docs|maintenance|manager>
- Persona: <manager|implementer|adr_author|test_engineer>
- Issue: #<issue>
- Issue URL: <url>
- Umbrella PR: #<pr> `[DO NOT MERGE]`
- Protected branch: <branch>
- Umbrella branch: <branch>
- Agent branch: <branch>
- Agent worktree: <path>
- Gate record: .workflow/records/<issue>-<task-slug>.json
- Checklist: docs/planning/<scope>-checklist.md

## Required Rules

Read and follow:

- The GitHub issue `#<issue>` and all owner instructions in it.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/personas/<persona>.md
- <task-specific rules, if any>

## Scope

You own only:

- <path or glob>
- <path or glob>

You must not touch:

- <path or glob>
- <path or glob>

If you need an out-of-scope path, stop and report back.
Do not edit it.

For `test_engineer` dispatches, production code is out of scope by default.
Only test, fixture, validation, e2e, audit evidence, and explicitly assigned
QA/governance tooling paths may be edited unless the manager or owner amends
the gate record.

## Coordination

- You are not alone in this codebase.
- MUST work only on your assigned branch.
- MUST work only in your assigned worktree.
- MUST NOT use `pip install -e .`.
- Do not revert or overwrite other agents' work.
- Do not broaden scope.
- MUST target your PR to the assigned umbrella or tracking branch.
- MUST NOT target your PR to the protected branch unless the manager explicitly
  assigns that final PR.
- MUST NOT merge any PR unless the owner explicitly authorizes it.
- Edit only your checklist rows.
- Record every completed row with a PR, commit, test, report, or gate evidence.

## TODO And Deferral Rule

Deferred work must be tracked in the repo.
Use `TODO(#NNN): <reason>` and cite an issue, ADR, spec, or follow-up ticket.
Do not leave hidden V1, MVP, or later work.

Known deferred items:

- <TODO item or N/A>

## Work To Do

1. <step>
2. <step>
3. <step>

## Required Tests And Checks

- <test command or N/A reason>
- <lint/check command>
- `python -m scistudio.qa.governance.gate_receipt run` or explicit
  `gate_receipt exec` commands for every required Phase 5 check
- `python scripts/scistudio_pr_create.py` for the final PR (do not use
  `gh pr create` directly; ADR-042 Addendum 5)
- <docs/audit command or N/A reason>
- <Sentrux MCP/CLI command or N/A reason>

If the task changes wrapper, hook, gate-record, receipt, CI, or AI-runtime
behavior, check whether these docs need updates and record updated paths or
N/A rationale: `docs/ai-developer/rules.md`,
`docs/ai-developer/specific_rules/gated-workflow.md`,
`docs/ai-developer/specific_rules/agent-dispatch.md`, and
`docs/ai-developer/templates/*dispatch*.md`.

## Output Required

Before reporting done, provide:

- Changed file paths.
- Tests/checks run and results.
- Checklist rows updated.
- PR number or commit.
- Any blocker or scope issue.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file.
- The task conflicts with AGENTS.md, ADR, spec, or gate record.
- CI or local checks fail for unclear reasons.
- Another agent's work blocks yours.
- You cannot add/update required tests.
```
