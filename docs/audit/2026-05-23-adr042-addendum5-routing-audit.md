---
title: "ADR-042 Addendum 5 Routing Audit"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
language_source: en
---

# ADR-042 Addendum 5 Routing Audit

## 1. Change Summary

This audit verifies whether the AI-developer documentation under
`docs/ai-developer/` and the runtime rule indexes route agents to the new QA
behaviors introduced by ADR-042 Addendum 5 (PR #1495, merged 2026-05-23).

Source of audit: owner-requested 4-step plan on 2026-05-23.
Issue: #1496.

The audit finds that the core behaviors are fully wired only in
`docs/ai-developer/specific_rules/gated-workflow.md` and partially in
`docs/ai-developer/rules.md` and
`docs/ai-developer/specific_rules/agent-dispatch.md`. The remaining 14 docs
(all 5 personas, 5 of 7 specific_rules, 2 of 4 dispatch templates, AGENTS.md
§3.7, and the three runtime rule indexes) are silent or only transitively
link, so agents arriving through the persona or task-kind entry point never
learn about the wrapper, receipt, or write guard until something blocks
them.

This document records the matrix, the critical gaps, and the remediation
landed in PR #1496-followup so the corrected routing remains auditable.

## 2. Audit Scope And Method

In scope:

- `AGENTS.md`
- `docs/ai-developer/rules.md`
- `docs/ai-developer/specific_rules/*.md` (7 files)
- `docs/ai-developer/personas/*.md` (5 files)
- `docs/ai-developer/templates/*.md` (4 files)
- `.agents/rules/rules.md`, `.claude/rules/rules.md`, `.codex/rules/rules.md`

Method:

- enumerate the new QA behaviors landed by ADR-042 Addendum 5;
- grep each document for canonical keywords;
- inspect each `Where Your Rules Are`, `Route`, or `## Checks` section
  for explicit routing to the new behaviors;
- record whether the routing is direct, transitive via
  `docs/ai-developer/rules.md` §5, or missing.

Canonical keywords:

- `gate_receipt` (Addendum 5 receipt CLI)
- `gate_record ci` (shared local/CI workflow gate)
- `Addendum 5` (explicit naming)
- `scistudio_pr_create` (PR-creation wrapper)
- `worktree_write_guard` / `check-worktree-write-guard.sh` (PreToolUse hook)
- `admin-approved:core-change` (narrowed semantics)
- `.workflow/local/gate-receipts/` (receipt path)

## 3. Routing Coverage Matrix

`✓` direct mention. `△` partial or transitive. `✗` missing.

| Document | receipt CLI | `gate_record ci` | Addendum 5 named | wrapper | write guard | core-change narrowed |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| `AGENTS.md` | △ §3.7 one line | ✗ | ✗ | ✗ | ✗ | ✗ |
| `docs/ai-developer/rules.md` | ✓ §3+§5 | ✓ §5 | △ implicit | ✗ | ✗ | ✓ §4 |
| `.agents/rules/rules.md` | △ transitive | ✗ | ✗ | ✗ | ✗ | ✗ |
| `.claude/rules/rules.md` | △ transitive | ✗ | ✗ | ✗ | ✗ | ✗ |
| `.codex/rules/rules.md` | △ transitive | ✗ | ✗ | ✗ | ✗ | ✗ |
| `personas/manager.md` | △ transitive | ✗ | ✗ | ✗ | ✗ | ✗ |
| `personas/implementer.md` | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `personas/adr-author.md` | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `personas/audit-reviewer.md` | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `personas/test-engineer.md` | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `specific_rules/gated-workflow.md` | ✓ §2+§3.6 | ✓ §3.6 | ✓ §3.6/§3.7 | ✓ §3.7 | ✗ | △ mentioned |
| `specific_rules/agent-dispatch.md` | ✓ §6 | ✗ | ✗ | ✗ | ✗ | ✓ §6 |
| `specific_rules/bug-fix.md` | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `specific_rules/new-feature.md` | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `specific_rules/hotfix.md` | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `specific_rules/docs-change.md` | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `specific_rules/test-engineering.md` | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `templates/agent-dispatch-prompt-template.md` | ✓ L102 | ✗ | ✗ | ✗ | ✗ | ✗ |
| `templates/agent-dispatch-checklist-template.md` | ✓ §5 L87 | ✗ | ✗ | ✗ | ✗ | ✓ §5 L78 |
| `templates/agent-dispatch-audit-with-context-prompt-template.md` | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| `templates/agent-dispatch-audit-no-context-prompt-template.md` | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |

`document-standards.md` is N/A for these behaviors: it is a structural
reference for document schemas only.

## 4. Critical Gaps

### 4.1 worktree write guard is undocumented in every AI-developer doc

The PreToolUse hook `scripts/hooks/check-worktree-write-guard.sh` and its
Python backend `src/scistudio/qa/governance/worktree_write_guard.py` block
AI Edit/Write/MultiEdit/NotebookEdit calls when the current branch is
`main`/`master`/`HEAD`, when no committed gate record matches the current
branch, when the write target is outside `scope.include`, or when it is
inside `scope.exclude`. The hook is provisioned automatically by
`agent_provisioning/templates/hook_worktree_write_guard.py` for new
worktrees, but no AI-developer doc names the hook by name. Agents discover
the hook only when an edit is rejected, which produces a poor first
experience and turns a hard gate into a discovery cost.

### 4.2 Wrapper mandate only routes through gated-workflow.md §3.7

`scripts/scistudio_pr_create.py` is the required PR-creation entry point
for AI-authored PRs per ADR-042 Addendum 5. Routing to it lives only in
`gated-workflow.md` §3.7. Agents that enter through `bug-fix.md`,
`new-feature.md`, a persona file, or a dispatch template never see the
wrapper requirement and reach for `gh pr create` instead. That choice does
not fail the open-PR step, but it produces extra CI fix-and-push cycles.
The wrapper deserves a dedicated row in the `rules.md` §5 command table
and a one-line mention in each persona and dispatch template.

### 4.3 Persona docs have no Addendum 5 routing

All five personas mention `gated-workflow.md` and `rules.md §5` in their
`Where Your Rules Are` section, but none explicitly call out:

- the receipt runner that captures persona-specific evidence (test runner
  output for `test_engineer`, lint/format/audit for `implementer`,
  frontmatter lint / full audit for `adr_author`, receipt completeness as
  an audit check for `audit_reviewer`, post-integration receipt validation
  for `manager`);
- the wrapper mandate;
- the worktree write guard;
- the narrowed `admin-approved:core-change` semantics for the
  `audit_reviewer` and `manager` who review override-label use.

Without persona-specific anchors, the routing is purely transitive and the
persona file fails to make Addendum 5 actionable for the role.

## 5. Remediation In This PR

Per ADR-042 §3.5 (no new policy in runtime/skill/index files; pointers
only), this PR adds short routing pointers without duplicating policy:

- `AGENTS.md` §3.7: name the wrapper and the worktree write guard and link
  to `gated-workflow.md`.
- `docs/ai-developer/rules.md` §5: add a PR-creation row for the wrapper;
  add a worktree write guard pointer.
- `docs/ai-developer/specific_rules/gated-workflow.md` §3.4: name the
  worktree write guard hook so implementers know which Edit/Write calls
  the hook gates.
- `docs/ai-developer/specific_rules/agent-dispatch.md` §6: name the hook
  and confirm new worktrees are provisioned with it.
- 5 persona docs: add one or two `Where Your Rules Are` lines each that
  link Addendum 5 receipt + wrapper to the role.
- 5 specific_rules (`bug-fix.md`, `new-feature.md`, `hotfix.md`,
  `docs-change.md`, `test-engineering.md`): add a single-line routing
  pointer back to `gated-workflow.md` §3.6-§3.7 for receipt + wrapper.
- 4 dispatch templates: the prompt template gains an explicit wrapper
  reference, the checklist template gains a Verification Evidence row for
  the receipt, and the two audit templates list `gate_receipt validate`
  in `## Checks`.

`document-standards.md` is left unchanged because it carries no routing
content. The three runtime indexes (`.agents`/`.claude`/`.codex`
`rules/rules.md`) are left unchanged because they correctly transitively
route through `docs/ai-developer/rules.md` §5; that table is the source of
truth they delegate to.

## 6. Acceptance

The PR is acceptable when every cell of the matrix in §3 that this PR
targets becomes `✓` or `△` with a pointer, and no cell regresses. The
`gated-workflow.md` text remains the single normative source for the
behaviors; all other edits are pointers, not policy.

## 7. Out Of Scope

- Editing `document-standards.md`.
- Rewriting any behavior policy.
- Modifying the wrapper, hook, receipt, or gate-record CLI.
- Touching `src/scistudio/qa/governance/` or `scripts/scistudio_pr_create.py`.
- Resolving the worktree-aware behavior of the write guard hook when
  Claude Code session cwd diverges from the active worktree; the current
  observation is that Claude Code propagates the Bash subprocess cwd to
  hook payloads, so the hook sees the worktree branch correctly. A
  separate issue can track formal worktree-awareness if needed.
