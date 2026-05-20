---
name: implementation-worker
description: Implement scoped SciEasy repository changes. Use for code, tests, docs, tooling, or governance asset edits when the task has an issue, change plan, branch, and acceptance criteria; obey the current .workflow/gate.py workflow and ai_developers/rules.
---

# Implementation Worker

Use this skill when directly editing files for a scoped repository task.

Start by reading:

- `AGENTS.md`
- `ai_developers/rules/gate-workflow.md`
- `ai_developers/rules/root-policy.md`
- `ai_developers/rules/code-quality.md`
- `ai_developers/rules/docs-governance.md`

Rules:

- Verify the gate status before implementation.
- Modify only files listed in the change plan.
- Update the change plan before touching newly discovered files.
- Add or update tests for behavior changes.
- Update docs and changelog when required.
- Leave tracked `TODO(#NNN)` comments for intentional deferrals.

Examples:

- "Implement issue #1257's canonical AI developer rules and mirrored skills."
- "Fix a failing test in the scoped module listed by the change plan."
- "Add documentation and changelog entries for a behavior change."
- "Wire a small QA tool without changing protected core paths."

Before finishing, run the relevant checks from `code-quality.md` and report any
checks that could not be run.
