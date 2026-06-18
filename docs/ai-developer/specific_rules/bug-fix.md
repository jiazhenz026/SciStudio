---
title: "AI Bug Fix Specific Rules"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
language_source: en
---

# AI Bug Fix Specific Rules

## 1. Purpose

- Use these rules for AI-authored bug fixes and audit-finding fixes.

- MUST also run `docs/ai-developer/specific_rules/gated-workflow.md`.

## 2. Bug Start Rules

- MUST confirm the bug, expected behavior, and affected user or subsystem.

- MUST link or create the bug issue before coding.

- MUST reproduce the bug or explain why reproduction is not possible.

- MUST identify the smallest architecture-correct fix.

- MUST decide if the fix needs an ADR.
  Use an ADR when the fix requires a design decision.

- MUST decide if the fix needs a spec update.
  Use a spec update when the fix changes a contract or expected behavior.

## 3. Fix Scope Rules

- MUST keep one bug or tightly related bug cluster per branch, worktree, issue,
  and PR.

- MUST NOT fix unrelated bugs in the same PR.
  Open a new issue for newly discovered bugs.

- MUST NOT change public behavior silently.
  Update the governing docs/spec/ADR when behavior changes.

- MUST NOT weaken tests, CI, validation, or governance to make the bug pass.

- MUST label planned behavior as planned.
  Do not claim the bug is fixed until the fix is implemented and verified.

## 4. Test Rules

- MUST add or update a regression test for the bug.

- MUST include a negative test when the bug is a validation, contract, or
  boundary failure.

- MUST run the targeted test that proves the bug is fixed.

- MUST run `gate_record check` to run the tier-selected CI-equivalent checks
  required for the observed diff. Do not run ruff, mypy, pytest, or full audit
  separately; `check` derives and runs the full set.

## 5. Deferral Rules

- MUST fix the approved bug completely.
  Do not leave hidden V1, MVP, or "later" bug debt.

- If part of the fix must be deferred, it MUST have a tracked TODO.

- If the deferred work is actually a separate bug, open or link a separate
  issue.

## 6. Route

Use these rules with:

- `docs/ai-developer/rules.md`
- `docs/ai-developer/specific_rules/gated-workflow.md`
- `docs/ai-developer/personas/implementer.md`
- `docs/ai-developer/personas/audit-reviewer.md` when the bug comes from audit
  findings
- `docs/ai-developer/personas/adr-author.md` when the fix requires ADR/spec
  text

The `scripts/scistudio_pr_create.py` wrapper is mandatory for every bug-fix PR.
`gate_record check --mode pre-pr` and pre-PR `finalize` replace the old
`gate_receipt` tooling; see
`docs/ai-developer/specific_rules/gated-workflow.md` §3.6 and §3.7.

`bugfix` is a Tier 2 task. The full task-kind CLI argument profile is in
ADR-042 Addendum 6 §7.7.4.
