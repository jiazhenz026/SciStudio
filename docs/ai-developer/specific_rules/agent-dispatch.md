---
title: "AI Agent Dispatch Specific Rules"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
language_source: en
---

# AI Agent Dispatch Specific Rules

## 1. Purpose

- Use these rules when a manager agent dispatches two or more agents for one
  coordinated task.

- MUST also run `docs/ai-developer/specific_rules/gated-workflow.md` for the
  manager-owned final delivery.

## 2. Dispatch Entry Rules

- MUST dispatch agents only when parallel work is useful and the owner request
  allows manager-style coordination.

- MUST NOT dispatch agents for a small single-agent task.

- MUST create one manager checklist before dispatch.
  The checklist is the shared task state.

- MUST create the checklist as a committed file at
  `docs/planning/<scope>-checklist.md`.

- MUST use `docs/ai-developer/templates/agent-dispatch-checklist-template.md`
  as the checklist template.

- MUST use the correct prompt template for each dispatched agent.
  Non-audit work uses `agent-dispatch-prompt-template.md`.

- MUST choose the audit mode before dispatching an audit agent:
  `with-context` or `no-context`.

- MUST use `agent-dispatch-audit-with-context-prompt-template.md` when the
  audit agent may read issue, checklist, PR, and claimed-work context.

- MUST use `agent-dispatch-audit-no-context-prompt-template.md` when the audit
  agent must independently compare repository docs, code, tests, and behavior.

- MUST define task kind (one of `hotfix`, `bugfix`, `feature`, `refactor`,
  `docs`, `maintenance`, `manager`, `guided`), issue, branch/worktree plan,
  scope, owners, and expected artifacts before dispatch.

- MUST create an umbrella branch before dispatch.
  The branch protects integration work from the protected target branch.

- MUST open an umbrella PR before dispatch.
  The checklist must record the protected branch and umbrella PR number.

- MUST title the umbrella PR with `[DO NOT MERGE]`.
  It is a protection and visibility PR, not the final merge PR.

- MUST give every dispatched agent a dedicated branch and worktree.
  MUST NOT let agents share a writable working tree.

- MUST NOT use `pip install -e .` in any dispatched worktree.

## 3. Scope Rules

- MUST give each agent a clear write set.
  Two agents MUST NOT own the same file unless the manager sequences them.

- MUST give `test_engineer` agents test, fixture, validation, e2e, or audit
  evidence write sets by default.
  Production code paths require an explicit manager or owner scope amendment.

- MUST give each agent explicit out-of-scope paths.
  If the agent needs one, it must stop and report back.

- MUST restate the tracked TODO rule in every implementation dispatch.
  Deferred work needs an issue, ADR, spec, or follow-up ticket.

- MUST tell agents they are not alone in the codebase.
  They must not revert or overwrite other agents' work.

- MUST NOT hide broad refactors inside dispatch work.
  Open or assign a separate issue when scope changes.

## 4. Prompt Rules

- MUST include owner request, issue, task kind, persona, scope, branch,
  worktree, expected files, tests, docs, and checks in non-audit and
  with-context audit prompts.

- MUST NOT include owner request, issue, checklist, PR claims, commit messages,
  dispatch prompts, or manager summaries in no-context audit prompts.

- MUST include the relevant common rules and specific rules.
  Do not paste unrelated policy.

- MUST tell implementation agents to edit files directly and report changed
  paths.

- MUST tell audit agents to report findings first and stay read-only unless
  assigned a fix.

- MUST tell audit agents to write the audit report to a repository file.
  Audit reports must not exist only in chat.

- MUST ensure audit report files are merged into the final PR or an audit PR
  that feeds the final PR.

- MUST tell no-context audit agents to use only repository docs, code, tests,
  committed generated facts, and tool output they run themselves.

- MUST include PR and CI expectations when an agent owns a PR.

- MUST save or link each filled dispatch prompt in the checklist.
  The manager must be able to review what each agent was told.

## 5. Manager Control Rules

- MUST keep the checklist current while agents run.
  Stale checklist state is a dispatch failure.

- MUST review each returned change before integrating it.
  Do not trust a summary alone.

- MUST verify that each agent stayed inside scope before merging or reusing
  its work.

- MUST resolve conflicts intentionally.
  Do not blindly accept one agent's version over another.

- MUST record blockers, drift, and follow-up issues in the checklist.

## 6. Local Gate Hook Bypass

- MUST use normal local gate validation unless the owner authorized a bypass
  label for the current manager task.

- MAY pass the authorized bypass label to local gate hook commands.
  Valid broad bypass labels (per ADR-042 Addendum 6): `human-authored` and
  `admin-approved:bypass`. `admin-approved:core-change` is narrow and must not
  bypass scope, docs, issue, or required-check validation.

- MUST record the bypass label, reason, and owner authorization in the
  checklist when any bypass label is used.

Per ADR-042 Addendum 6, `gate_record check` is the single local CI-equivalent
preflight command. Mode-specific aliases still exist, but new instructions
should spell the mode explicitly with `gate_record check --mode ...`:

```bash
# Pre-commit mode:
python -m scistudio.qa.governance.gate_record check --mode pre-commit

# With bypass label:
python -m scistudio.qa.governance.gate_record check --mode pre-commit \
  --admin-label admin-approved:bypass

# Commit-msg mode:
python -m scistudio.qa.governance.gate_record check --mode commit-msg <commit-msg-file>

# Pre-push mode:
python -m scistudio.qa.governance.gate_record check --mode pre-push \
  --base origin/main --head HEAD

# Pre-PR mode:
python -m scistudio.qa.governance.gate_record check --mode pre-pr \
  --base origin/main --head HEAD \
  --pr-body-file .workflow/local/pr-body.md
```

After integration, the manager must run a pre-PR check for the exact candidate.
Use `check --mode pre-pr` or pre-PR `finalize`; there is no separate receipt
validation command:

```bash
python -m scistudio.qa.governance.gate_record finalize \
  --base origin/main \
  --head HEAD \
  --commit <sha> \
  --pr-body-file .workflow/local/pr-body.md \
  --closes "#<issue>"
```

Each dispatched worktree is auto-provisioned with the worktree write guard
PreToolUse hook
(`scripts/hooks/check-worktree-write-guard.sh`,
`src/scistudio/agent_provisioning/templates/hook_worktree_write_guard.py`).
Per ADR-042 Addendum 6, the guard's role is narrowed to blocking writes from
an agent that did not create a dedicated worktree (i.e., the agent is operating
in the main checkout). It no longer enforces include/exclude scope at write
time; scope enforcement moves to `check` reconciliation. The manager does not
re-register the hook per dispatch.

## 7. Verification Rules

- MUST run the checks declared in the manager gate record after integration.

- MUST run relevant targeted tests for every implemented slice.

- MUST run frontend or browser smoke checks when dispatched work changes UI.

- MUST record each agent-owned test, docs update, and PR or commit evidence in
  the manager checklist or gate record.

- MUST check whether AI workflow docs or dispatch templates need updates when
  the work changes wrapper, hook, gate-record, CI, or AI-runtime behavior.
  Receipt behavior is now folded into the gate ledger; update `gated-workflow.md`
  and dispatch templates when the ledger CLI or evaluator behavior changes.

- MUST wait for CI to pass before calling the coordinated task complete.

## 8. Hard Fail Points

- Hard fail: two agents edit the same file without manager sequencing.

- Hard fail: dispatch starts without an umbrella branch and umbrella PR.

- Hard fail: checklist lacks protected branch or umbrella PR number.

- Hard fail: umbrella PR title does not include `[DO NOT MERGE]`.

- Hard fail: agents are dispatched before the checklist file exists.

- Hard fail: the checklist does not use the required template structure.

- Hard fail: a dispatched agent prompt does not use the required prompt
  template.

- Hard fail: audit mode is not recorded before dispatching an audit agent.

- Hard fail: a no-context audit receives issue, checklist, PR, or manager
  summary context.

- Hard fail: an agent works outside scope and the gate ledger or checklist is
  not amended.

- Hard fail: a dispatched implementation has no test change and no approved
  N/A reason.

- Hard fail: deferred work is mentioned in chat but not tracked in the repo.

- Hard fail: an audit report exists only in chat and is not committed.

- Hard fail: an audit report is not merged into the PR evidence path.

- Hard fail: a bypass label is used without checklist evidence.

- Hard fail: manager reports completion before reviewing agent outputs and CI.

## 9. Route

Use these rules with:

- `docs/ai-developer/rules.md`
- `docs/ai-developer/specific_rules/gated-workflow.md`
- `docs/ai-developer/personas/manager.md`
- `docs/ai-developer/personas/implementer.md` for implementation agents
- `docs/ai-developer/personas/audit-reviewer.md` for audit agents
- `docs/ai-developer/personas/test-engineer.md` for test-engineer agents
- `docs/ai-developer/specific_rules/test-engineering.md` for test-engineer
  work
