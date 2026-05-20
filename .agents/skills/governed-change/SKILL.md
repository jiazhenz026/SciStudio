---
name: governed-change
description: Apply SciEasy's current governed-change workflow. Use as a helper for any repository task that needs issue linkage, scope control, the .workflow/gate.py stages, docs landing, changelog updates, PR creation, or runtime skill synchronization.
---

# Governed Change

Use this skill as the workflow helper for scoped SciEasy repository changes.

Start by reading:

- `AGENTS.md`
- `ai_developers/rules/gate-workflow.md`
- `ai_developers/rules/branch-pr-ci.md`
- `ai_developers/rules/docs-governance.md`

Workflow:

1. Confirm or create the GitHub issue.
2. Record the issue in `.workflow/gate.py`.
3. Write a change plan as an issue comment.
4. Implement only files listed in the plan.
5. Record docs landing and changelog handling.
6. Push a branch and create a PR.

Examples:

- "Turn this approved design into a gated implementation task."
- "Add a docs-only governance rule while preserving traceability."
- "Create mirrored runtime skills from the canonical skill source."
- "Verify that the changelog entry includes issue, date, branch, and session."

Do not require ADR-042 local gate sessions or commit trailers until those tools are implemented.
