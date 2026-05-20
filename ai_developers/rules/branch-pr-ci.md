# Branch, PR, And CI

## 1. Decision Summary

All meaningful work is traceable through issue, plan, branch, commit, PR,
review, and CI. Local `main` is a read-only reference.

Branch rules:

- Create a task branch from current `main`.
- Use names such as `feat/issue-N/short-description`,
  `fix/issue-N/short-description`, or `docs/issue-N/short-description`.
- Never merge into local `main`.
- One branch should represent one issue and one scoped task.

Commit rules:

- Use focused commit messages.
- Avoid vague messages such as `fix`, `update`, `misc`, `changes`, or `final`.
- Do not commit files outside the change plan.

PR rules:

- Every change must be published through a GitHub PR.
- Link the issue.
- Link relevant ADRs, specs, and rule modules.
- Explain scope, verification, and known risks.
- AI agents must not merge PRs.

CI rules:

- Run relevant local checks before PR when feasible.
- After PR creation, check CI.
- If CI fails, diagnose, fix, push, and repeat until green or explicitly hand
  back the blocker.
