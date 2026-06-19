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
  `hotfix`, `bugfix`, `feature`, `refactor`, `docs`, `maintenance`,
  `manager`, or `guided`.

- MUST choose one persona before work starts:
  `manager`, `implementer`, `adr_author`, `audit_reviewer`,
  `test_engineer`, or `live_implementer`.

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

- MUST run `gate_record check` before PR creation.
  WIP pushes no longer run duplicate gate validation through the pre-push hook;
  PR creation and CI remain the hard governance checkpoints.
  Receipt behavior is folded into the gate record ledger as of ADR-042
  Addendum 6; separate `gate_receipt` commands are replaced by
  `gate_record check --mode pre-pr` and `gate_record finalize --pr-body-file`.
  Raw terminal output is not hard gate evidence; only committed ledger events
  and CI reconciliation count.

- MUST keep runtime pointers and skills short.
  They must point to canonical docs and must not copy policy.

## 4. Authorization Labels

- `admin-approved:bypass` authorizes a one-off AI gate workflow bypass.

- `admin-approved:core-change` authorizes protected core path changes only.
  It does not bypass scope, issue linkage, docs landing, ledger check evidence,
  tier-selected check obligations, or CI parity checks.

- `admin-approved:merge` authorizes approved merge automation.

- If the owner authorizes one of these actions in chat, the PR must carry the
  matching label before the action is considered approved.

- CI must validate label provenance.
  Chat authorization alone is not enough for final PR readiness.

- `admin-approved:bypass` is the only accepted label for a one-off broad
  AI workflow-gate override. It still does not bypass branch protection,
  normal repository CI, owner review, or administrator merge authorization.

## 5. Gate CLI Command Set

All AI-authored work uses these repository-owned commands. The gate record is
the single source of truth: it is an append-only ledger. Receipt behavior is
folded into the ledger as check and reconcile events. There is no separate
`gate_receipt` command after ADR-042 Addendum 6; the `gate_record check` and
`gate_record finalize` commands replace those workflows. The detailed procedure
and examples live in `docs/ai-developer/specific_rules/gated-workflow.md`;
this section is the quick command index every persona should route back to.

The full consolidated reference — every argument table, the `--mode` family,
exit codes, strictness tiers, per-task-kind and per-persona profiles, and a
soft-routing decision guide — is `docs/ai-developer/gate-cli-command-set.md`.
Use that document when you need the complete argument detail or want to
self-route a task; this section is only the quick index.

| Need | Command |
|---|---|
| Create or update the gate ledger for the current task | `python -m scistudio.qa.governance.gate_record init --task-kind <kind> --persona <persona> --runtime <runtime> --branch <branch> --owner-directive "<directive>" [--issue <n>] [--include <path>] [--exclude <path>] [--governance-touch true]` |
| Record or update the plan (scope, docs, tests, checks) | `python -m scistudio.qa.governance.gate_record plan [--owner-directive "<update>"] [--include <path>] [--issue <n>] [--docs-updated <path>] [--docs-na "<class>:<rationale>"] [--test-path <path>] [--test-na "<class>:<rationale>"] [--check <name>]` |
| Append a correction or scope change with rationale | `python -m scistudio.qa.governance.gate_record amend --reason "<why>" [--owner-directive "<directive>"] [--include <path>] [--issue <n>] [--test-path <path>] [--docs-updated <path>]` |
| Run tier-selected local CI-equivalent checks and reconcile | `python -m scistudio.qa.governance.gate_record check [--base origin/main] [--head HEAD] [--mode local\|pre-push\|pre-pr\|ci] [--pr-body-file <path>] [--only <name>] [--skip-execution]` |
| Record commit provenance (pre-PR, before PR exists) | `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#<issue>"` |
| Record PR provenance (post-PR, after PR is created) | `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr <url-or-number> --pr-body-file <path>` |
| Open AI-authored PR via gate-aware wrapper | `python scripts/scistudio_pr_create.py --title "<title>" --body "<body>"` |

Supported `--task-kind` values: `hotfix`, `bugfix`, `feature`, `refactor`,
`docs`, `maintenance`, `manager`, `guided`.

Supported `--persona` values: `manager`, `implementer`, `adr_author`,
`audit_reviewer`, `test_engineer`, `live_implementer`.

Supported `--mode` values for `check`: `local` (default), `pre-push`,
`pre-pr`, `ci`. `pre-push` remains available as a manual compatibility mode,
but the installed pre-push hook is a fast allow shim; `pre-pr` and `ci` are the
hard governance checkpoints. The `check` command automatically observes the git
diff, infers the tier-selected CI-equivalent check set, runs required commands,
records sanitized ledger events, runs guard reconciliation, and exits nonzero
when required obligations remain unsatisfied.

`admin-approved:core-change` is not a broad bypass for these commands. It only
answers protected-core authorization where that guard applies.
`admin-approved:bypass` is the broad one-off AI gate override label.

The worktree write guard PreToolUse hook
(`scripts/hooks/check-worktree-write-guard.sh`) blocks AI Edit/Write when the
agent is operating in the main repository working tree (i.e., when the agent
forgot to create a dedicated worktree). It allows writes inside any linked
git worktree and allows writes outside the repository entirely (for example
to memory files or system paths). The guard does not enforce cwd-based scope;
it checks whether the target path is inside the main repo checkout vs. a
linked worktree. Use `gate_record amend` before touching files outside the
original plan when operating within a worktree. New worktrees are
auto-provisioned with this hook via
`src/scistudio/agent_provisioning/templates/hook_worktree_write_guard.py`.

`gate_record check --mode pre-pr` is the only local command that should execute
the full PR-ready check mirror by default. `finalize` and the PR wrapper reuse
existing current check evidence (`--skip-execution`) and fail fast when that
evidence is missing or stale. Use `finalize --force-checks` only when finalize
itself intentionally needs to rerun the tier-selected checks.

## 6. Routing

Task-specific rules MUST include `docs/ai-developer/specific_rules/gated-workflow.md`
unless the owner explicitly authorizes hotfix mode.

`docs/ai-developer/**` is a governance surface (ADR-042 Addendum 6 §7.8).
Editing any file under `docs/ai-developer/` requires a `governance_touch`
declaration in the gate ledger and the same focused scope and owner-review
requirements as other governance changes.

| Need | Read |
|---|---|
| Gate execution | `docs/ai-developer/specific_rules/gated-workflow.md` |
| Gate CLI command index | `docs/ai-developer/rules.md#5-gate-cli-command-set` |
| Gate CLI full reference (args, tiers, profiles, soft routing) | `docs/ai-developer/gate-cli-command-set.md` |
| New feature | `docs/ai-developer/specific_rules/new-feature.md` |
| Bug fix | `docs/ai-developer/specific_rules/bug-fix.md` |
| Hotfix | `docs/ai-developer/specific_rules/hotfix.md` |
| Owner-guided live implementation (`guided` task kind) | `docs/ai-developer/specific_rules/guided-work.md` |
| Docs change | `docs/ai-developer/specific_rules/docs-change.md` |
| Agent dispatch | `docs/ai-developer/specific_rules/agent-dispatch.md` |
| Manager persona | `docs/ai-developer/personas/manager.md` |
| Implementer persona | `docs/ai-developer/personas/implementer.md` |
| ADR author persona | `docs/ai-developer/personas/adr-author.md` |
| Audit reviewer persona | `docs/ai-developer/personas/audit-reviewer.md` |
| Test engineer persona | `docs/ai-developer/personas/test-engineer.md` |
| Live implementer persona (`guided` task kind) | `docs/ai-developer/personas/live-implementer.md` |
| Test engineering | `docs/ai-developer/specific_rules/test-engineering.md` |
