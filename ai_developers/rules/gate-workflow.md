# Gate Workflow

## 1. Decision Summary

The currently active workflow gate is `.workflow/gate.py`. Until the ADR-042
local gate is implemented, every implementation, documentation, governance, or
maintenance task must use this six-stage workflow.

Required sequence:

1. Start workflow and create or link a GitHub issue.
2. Write a change plan as an issue comment.
3. Create or use the scoped branch and implement only files listed in the
   change plan.
4. Record documentation updates or an explicit not-applicable rationale.
5. Update `CHANGELOG.md` when the change is meaningful.
6. Push and open a GitHub PR.

Before each gate transition, run:

```bash
python .workflow/gate.py status <TASK_ID>
```

Do not advance a stage while the gate reports it as locked.

Scope rules:

- Only modify files listed in the change plan.
- If more files are needed, update the issue change plan first.
- Keep one issue, one branch, and one PR per task.
- Do not merge into local `main`.
- Do not push directly to `main`.

Commit metadata:

- Use focused conventional commit messages.
- Include the issue number when practical, for example
  `docs(#1257): add AI developer skill rules`.
- Record commit SHAs in the `create_branch` gate stage.

ADR-042 note:

ADR-042 `.git/scieasy/gates/` local gate sessions and commit trailers are not active yet. Do not require them until their tools exist and are wired.
