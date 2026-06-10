---
title: "Agent Dispatch Audit No Context Prompt Template"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
language_source: en
---

# Agent Dispatch Audit No Context Prompt Template

Use this template when the audit agent must not know the current task,
manager plan, issue, checklist, PR claims, or intended implementation.
This audit independently compares repository documents and code behavior.

```markdown
[DISPATCH-TEMPLATE-V1: audit-no-context]

## Task Identity

- Repository: SciStudio
- Persona: audit_reviewer
- Audit mode: no-context
- Audit branch: <branch>
- Audit worktree: <path>
- Allowed audit surfaces:
  - <docs path, code path, or subsystem>
- Audit report path: docs/audit/<YYYY-MM-DD>-<scope>-no-context.md

## Context Limits

You must not read or use:

- The current owner request.
- The current GitHub issue.
- Manager checklist files for the current work.
- Dispatch prompts for the current work.
- PR descriptions, PR comments, or commit messages for the current work.
- Chat summaries or manager summaries of what changed.

You may read only:

- Repository docs.
- Repository code.
- Tests.
- Generated facts or audit outputs already committed in the repository.
- Tool output from commands you run yourself.

## Required Reading

Read and follow:

- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/personas/audit-reviewer.md
- Governing ADRs, specs, and docs discovered from the allowed audit surfaces.

## Audit Goal

Independently check whether docs, code, tests, and declared contracts agree.
Do not assume what the manager intended to change.

Look for:

- Docs that claim behavior code does not implement.
- Code behavior not covered by the governing docs.
- Tests missing for documented contracts.
- ADR/spec governed paths that do not exist.
- Public signatures or schemas that drift from docs.
- Generated docs edited by hand.

## Coordination

- MUST work only on your assigned audit branch.
- MUST work only in your assigned audit worktree.
- MUST NOT use `pip install -e .`.
- MUST NOT merge any PR.
- MUST NOT edit implementation files.
- MUST NOT edit the manager checklist.
- MUST write the audit report to the repository file named above.
- MUST make the audit report available for merge into the final PR or an audit
  PR that feeds the final PR.

## Checks

Run or verify:

- <lint/check command>
- <test command>
- <audit command>
- <Sentrux MCP/CLI command or N/A reason>
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr` to confirm the gate ledger reconciliation for the current branch (receipt behavior is folded into the ledger per ADR-042 Addendum 6; there is no separate `gate_receipt` command; this does not require manager context)

## Output Required

- Audit report path.
- Commit or PR that contains the audit report file.
- Findings ordered by severity.
- Evidence from docs, code, tests, or tool output.
- No statement about manager intent unless it is visible in repository docs.
- Recommendation: pass, pass-with-fixes, or block.

## Stop Conditions

Stop and report back if:

- You are asked to read issue/checklist/PR context.
- The audit requires hidden manager context.
- You need to edit implementation code.
```
