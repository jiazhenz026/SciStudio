---
title: "Issue 1384 E2E Audit Dispatch Prompt"
status: Draft
owners:
  - "@jiazhenz026"
related_issues:
  - 1384
related_prs:
  - 1364
language_source: en
---

# Issue 1384 E2E Audit Dispatch Prompt

Use `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`.

## Task Identity

- Repository: SciStudio
- Owner request: Audit the GUI E2E discovery suite.
- Task kind: `manager`
- Persona: `audit_reviewer`
- Audit mode: `with-context`
- Issue: `#1384`
- Umbrella PR: pending `[DO NOT MERGE]`
- Integration base branch: `umbrella/adr-039-addendum-1-impl`
- Umbrella branch: `track/issue-1384-e2e-discovery`
- Agent branch: `audit/issue-1384/e2e-discovery`
- Agent worktree: `../SciStudio-e2e-audit-1384`
- Checklist: `docs/planning/issue-1384-e2e-discovery-checklist.md`

## Required Rules

Read and follow:

- GitHub issue `#1384`
- PR `#1364`
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/personas/audit-reviewer.md

## Scope

You own only:

- `docs/audit/2026-05-21-issue-1384-e2e-discovery-audit.md`
- Your audit rows in `docs/planning/issue-1384-e2e-discovery-checklist.md`

You are read-only for all implementation files unless the manager assigns a
fix.

## Audit Questions

1. Are these true GUI E2E tests, not component tests in disguise?
2. Do they avoid over-mocking runtime/API/project-dir behavior?
3. Are expected failures traceable to product behavior rather than test bugs?
4. Do workflow-mutating actions assert canvas, tab, API, and disk consistency?
5. Do Git tests follow PR #1364 post-refactor behavior?
6. Is CI automatic and non-blocking, while still preserving failure evidence?
7. Are existing tests left in place?

## Output Required

- Findings first, ordered P1/P2/P3.
- Audit report file committed under `docs/audit/`.
- Commands inspected/run and results.
- Recommendation: pass, pass-with-fixes, or block.
