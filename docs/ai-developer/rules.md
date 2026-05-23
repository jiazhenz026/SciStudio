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

- MUST generate or validate the local Addendum 5 receipt before push or PR
  creation. Use `python -m scistudio.qa.governance.gate_receipt run` or wrap
  custom commands with `gate_receipt exec`; raw terminal output is not hard
  gate evidence.

- MUST keep runtime pointers and skills short.
  They must point to canonical docs and must not copy policy.

## 4. Authorization Labels

- `admin-approved:ai-override` authorizes a one-off AI gate override.

- `admin-approved:core-change` authorizes protected core path changes only.
  It does not bypass scope, issue linkage, docs landing, full-audit evidence,
  local receipt validation, required checks, or CI parity checks.

- `admin-approved:merge` authorizes approved merge automation.

- If the owner authorizes one of these actions in chat, the PR must carry the
  matching label before the action is considered approved.

- CI must validate label provenance.
  Chat authorization alone is not enough for final PR readiness.

- `admin-approved:ai-override` is the only accepted label for a one-off broad
  AI workflow-gate override. It still does not bypass branch protection,
  normal repository CI, owner review, or administrator merge authorization.

## 5. Gate CLI Command Set

All AI-authored work uses these repository-owned commands. The detailed
procedure and examples live in
`docs/ai-developer/specific_rules/gated-workflow.md`; this section is the
quick command index every persona should route back to.

| Need | Command |
|---|---|
| Start committed gate record | `python -m scistudio.qa.governance.gate_record start ...` |
| Record plan | `python -m scistudio.qa.governance.gate_record plan --record <record> ...` |
| Amend scope before new paths are edited | `python -m scistudio.qa.governance.gate_record amend --record <record> --reason <reason> --include <path>` |
| Record docs landing or N/A | `python -m scistudio.qa.governance.gate_record docs --record <record> --updated <path>` |
| Record a check in the committed gate record | `python -m scistudio.qa.governance.gate_record check --record <record> --name <name> --command <cmd> --status pass --exit-code 0` |
| Record Sentrux evidence | `python -m scistudio.qa.governance.gate_record sentrux --record <record> --status pass|fail|skipped` |
| Validate staged scope | `python -m scistudio.qa.governance.gate_record pre-commit --staged` |
| Validate commit message trailers | `python -m scistudio.qa.governance.gate_record commit-msg <commit-msg-file>` |
| Validate branch diff before push | `python -m scistudio.qa.governance.gate_record pre-push --base <base-ref> --head HEAD` |
| Validate shared local/CI workflow gate | `python -m scistudio.qa.governance.gate_record ci --gate-record <record> --base <base-ref> --head HEAD --pr-body <body>` |
| Generate exact-candidate local receipt | `python -m scistudio.qa.governance.gate_receipt run --gate-record <record> --base <base-ref> --pr-body-file .workflow/local/pr-body.md` |
| Record one custom command in the receipt | `python -m scistudio.qa.governance.gate_receipt exec --name <name> --gate-record <record> --base <base-ref> -- <command>` |
| Validate receipt freshness/completeness | `python -m scistudio.qa.governance.gate_receipt validate --gate-record <record> --base <base-ref> --pr-body-file .workflow/local/pr-body.md` |
| Open AI-authored PR via gate-aware wrapper | `python scripts/scistudio_pr_create.py --title "<title>" --body "<body>"` |
| Finalize commit and PR evidence | `python -m scistudio.qa.governance.gate_record finalize --record <record> --commit <sha> --pr <url> --closes "#<issue>"` |

`admin-approved:core-change` is not a broad bypass for these commands. It only
answers protected-core authorization where that guard applies.

The worktree write guard PreToolUse hook
(`scripts/hooks/check-worktree-write-guard.sh`) blocks Edit/Write outside the
active branch's committed gate scope. New worktrees are auto-provisioned with
this hook via
`src/scistudio/agent_provisioning/templates/hook_worktree_write_guard.py`.

## 6. Routing

Task-specific rules MUST include `docs/ai-developer/specific_rules/gated-workflow.md`
unless the owner explicitly authorizes hotfix mode.

| Need | Read |
|---|---|
| Gate execution | `docs/ai-developer/specific_rules/gated-workflow.md` |
| Gate CLI command index | `docs/ai-developer/rules.md#5-gate-cli-command-set` |
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
