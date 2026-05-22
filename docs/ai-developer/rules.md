---
title: "AI Developer Common Rules"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
language_source: en
---

# AI Developer Common Rules

## 1. Purpose

- These rules apply to every AI persona.
  `AGENTS.md` is still the main policy.

- Read this file before choosing a specific rule or persona guide.
  This file does not replace `AGENTS.md`.

## 2. Authority

- MUST follow `AGENTS.md` first.
  Then follow accepted ADRs, specs, this file, specific rules, personas, and
  skills.

- MUST NOT create new policy in runtime files, skills, or memory.
  Those files may only point to policy or explain runtime mechanics.

## 3. Common Rules

- MUST use a dedicated branch and a dedicated worktree for each task.
  This avoids conflicts with parallel agents.

- MUST NOT use `pip install -e .`.
  It can pollute the shared environment.

- MUST choose one task kind before work starts:
  `hotfix`, `bugfix`, `feature`, `refactor`, `docs`, `maintenance`, or
  `manager`.

- MUST choose one persona before work starts:
  `manager`, `implementer`, `adr_author`, `audit_reviewer`, or
  `test_engineer`.

- MUST stay inside the owner request, issue, spec, ADR, and gate record.
  MUST NOT quietly expand the task.

- MUST NOT create a new issue when an open issue already tracks the work.

- MUST make the PR close an open issue.
  Referencing an issue is not enough.

- MUST NOT bypass schemas, lineage, runtime checks, CI, review, or branch
  protection.

- MUST keep backend/runtime as the source of workflow truth.
  MUST NOT make frontend state the source of truth.

- MUST keep plugin logic out of core unless an ADR or spec says otherwise.
  MUST NOT move code across boundaries just to make a task easier.

- MUST NOT implement placeholder modules unless the task explicitly assigns
  them.

- MUST label planned behavior as planned.
  MUST NOT describe future or missing behavior as implemented.

- MUST run the gated workflow for AI-authored work.
  Task-specific rules are not valid without it.

- MUST add or modify tests for implementation work.
  Running tests is not enough if no test file changed.

- MUST write tracked TODOs for deferred work.
  The TODO must cite an issue, ADR, spec, or follow-up ticket.

- MUST keep generated docs generated.

- MUST NOT merge PRs as an AI agent unless an administrator explicitly
  authorized it.

- MUST NOT weaken governance, CI, Sentrux, quality thresholds, or protected
  paths unless the owner explicitly approved that scope.

- MUST expect pre-commit hooks, audits, and CI to hard-block protected rules.
  Do not work around these checks.

- MUST wait for CI to pass before treating the task as complete.

- MUST keep runtime pointers and skills short.
  They must point to canonical docs and must not copy policy.

## 4. Authorization Labels

- `admin-approved:ai-override` authorizes a one-off AI gate override.

- `admin-approved:core-change` authorizes protected core path changes.

- `admin-approved:merge` authorizes approved merge automation.

- If the owner authorizes one of these actions in chat, the PR must carry the
  matching label before the action is considered approved.

- CI must validate label provenance.
  Chat authorization alone is not enough for final PR readiness.

## 5. Routing

Task-specific rules MUST include `docs/ai-developer/specific_rules/gated-workflow.md`
unless the owner explicitly authorizes hotfix mode.

| Need | Read |
|---|---|
| Gate execution | `docs/ai-developer/specific_rules/gated-workflow.md` |
| New feature | `docs/ai-developer/specific_rules/new-feature.md` |
| Bug fix | `docs/ai-developer/specific_rules/bug-fix.md` |
| Hotfix | `docs/ai-developer/specific_rules/hotfix.md` |
| Docs change | `docs/ai-developer/specific_rules/docs-change.md` |
| Agent dispatch | `docs/ai-developer/specific_rules/agent-dispatch.md` |
| Manager persona | `docs/ai-developer/personas/manager.md` |
| Implementer persona | `docs/ai-developer/personas/implementer.md` |
| ADR author persona | `docs/ai-developer/personas/adr-author.md` |
| Audit reviewer persona | `docs/ai-developer/personas/audit-reviewer.md` |
| Test engineer persona | `docs/ai-developer/personas/test-engineer.md` |
| Test engineering | `docs/ai-developer/specific_rules/test-engineering.md` |
