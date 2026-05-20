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

## 2. Commands

Start the workflow:

```bash
python .workflow/gate.py start "Brief description of the task"
```

Create or link the GitHub issue, then record it:

```bash
python .workflow/gate.py advance <TASK_ID> create_issue \
  --data '{"issue_number": 1257, "issue_url": "https://github.com/.../issues/1257"}'
```

Write the change plan as an issue comment, then record it:

```bash
python .workflow/gate.py advance <TASK_ID> write_change_plan \
  --data '{"change_plan_comment_url": "https://github.com/...#issuecomment-...","files_to_modify":["AGENTS.md"]}'
```

Create or use the task branch, implement scoped changes, commit, then record
the branch and commit SHAs:

```bash
python .workflow/gate.py advance <TASK_ID> create_branch \
  --data '{"branch_name":"docs/issue-1257/example","commit_shas":["abc1234"]}'
```

Record documentation landing:

```bash
python .workflow/gate.py advance <TASK_ID> update_docs \
  --data '{"docs_updated":["ai_developers/rules/gate-workflow.md"]}'
```

Record changelog landing:

```bash
python .workflow/gate.py advance <TASK_ID> update_changelog \
  --data '{"changelog_entry":"#1257"}'
```

Push, create the PR, then record it:

```bash
python .workflow/gate.py advance <TASK_ID> submit_pr \
  --data '{"pr_number":1260,"pr_url":"https://github.com/.../pull/1260"}'
```

## 3. Self-Check

Before each gate transition, run:

```bash
python .workflow/gate.py status <TASK_ID>
```

Do not advance a stage while the gate reports it as locked.

If advancement is blocked, run status, complete the missing prerequisite, and
retry. Do not work around the gate.

## 4. Scope Rules

- Only modify files listed in the change plan.
- If more files are needed, update the issue change plan first.
- Keep one issue, one branch, and one PR per task.
- Do not merge into local `main`.
- Do not push directly to `main`.

Small changes still use the gate. A typo fix may have a short change plan and
explicit "docs not applicable" rationale, but it still needs issue linkage and
PR traceability.

## 5. Commit Metadata

- Use focused conventional commit messages.
- Include the issue number when practical, for example
  `docs(#1257): add AI developer skill rules`.
- Record commit SHAs in the `create_branch` gate stage.

ADR-042 note:

ADR-042 `.git/scieasy/gates/` local gate sessions and commit trailers are not
active yet. Do not require them until their tools exist and are wired.
