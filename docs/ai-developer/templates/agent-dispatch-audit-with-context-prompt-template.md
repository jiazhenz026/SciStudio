---
title: "Agent Dispatch Audit With Context Prompt Template"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
language_source: en
---

# Agent Dispatch Audit With Context Prompt Template

Use this template when the audit agent should know the issue, checklist, PRs,
and claimed work. This audit verifies whether the claimed work is true,
complete, scoped, and tested.

```markdown
[DISPATCH-TEMPLATE-V1: audit-with-context]

## Task Identity

- Repository: SciEasy
- Persona: audit_reviewer
- Audit mode: with-context
- Issue: #<issue>
- Issue URL: <url>
- Owner request: <one sentence>
- Umbrella PR: #<pr> `[DO NOT MERGE]`
- Protected branch: <branch>
- Umbrella branch: <branch>
- Audit branch: <branch>
- Audit worktree: <path>
- Gate record: .workflow/records/<issue>-<task-slug>.json
- Checklist: docs/planning/<scope>-checklist.md
- PRs or commits to audit: <list>
- Audit report path: docs/audit/<YYYY-MM-DD>-<scope>-<phase>.md

## Required Reading

Read and follow:

- The GitHub issue `#<issue>` and all owner instructions in it.
- The manager checklist.
- The PR descriptions, changed files, and CI results for audited PRs.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/personas/audit-reviewer.md
- Governing ADRs, specs, and docs named by the issue or changed files.

## Audit Goal

Verify the claimed work against the issue, checklist, governing docs, code,
tests, gate evidence, and CI.

Report findings first. Use severity:

- P1: blocks merge or breaks contract.
- P2: should fix before completion.
- P3: improvement or follow-up.

## Scope

Audit these claims:

- <claim>
- <claim>

Audit these files or surfaces:

- <path or glob>
- <path or glob>

Do not write feature code.
MUST write the audit report to the repository file named above.
MUST make the audit report available for merge into the final PR or an audit
PR that feeds the final PR.
Only write the audit report and your assigned checklist audit rows.

## Coordination

- MUST work only on your assigned audit branch.
- MUST work only in your assigned audit worktree.
- MUST NOT use `pip install -e .`.
- MUST NOT merge any PR unless the owner explicitly authorizes it.
- MUST NOT fix implementation code unless the manager explicitly changes your
  role to fix agent.
- Edit only your checklist audit rows.

## Checks

Run or verify:

- <lint/check command>
- <test command>
- <audit command>
- <Sentrux MCP/CLI command or N/A reason>
- <frontend/browser smoke check or N/A reason>

## Output Required

- Audit report path.
- Commit or PR that contains the audit report file.
- Findings ordered by severity.
- Checklist drift, if any.
- Scope drift, if any.
- Missing tests/docs/gate evidence, if any.
- CI status.
- Recommendation: pass, pass-with-fixes, or block.

## Stop Conditions

Stop and report back if:

- You need to change implementation code.
- Required evidence is unavailable.
- The audit scope conflicts with AGENTS.md, ADR, spec, or gate record.
```
