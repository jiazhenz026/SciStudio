---
title: "AI Hotfix Specific Rules"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
language_source: en
---

# AI Hotfix Specific Rules

## 1. Purpose

- Hotfix is a user-guided live debugging session.

- Enter hotfix ONLY when the owner explicitly authorizes hotfix mode.

- You are authorized to bypass the gated workflow during the live hotfix
  session.

- Final commit and PR submission MUST use the standard gated workflow.

## 2. Entry Rules

- MUST NOT treat a normal bugfix as a hotfix.

- MUST create a dedicated `hotfix/<short-description>` branch and worktree.

- MUST read the relevant ADR or spec before editing code.

- MUST read `docs/architecture/ARCHITECTURE.md` and
  `docs/architecture/PROJECT_TREE.md` when the fix crosses subsystem
  boundaries.

- MUST quote the governing section you read before the first code edit.

## 3. Live Debug Rules

- MAY reproduce the bug interactively when the owner is guiding the session.

- MAY iterate code edits and live retests during the hotfix round.

- MUST NOT fix only the surface symptom.
  Find and fix the root cause for the approved scope.

- MUST keep the hotfix scope limited to the owner-authorized live-debug bug.
  Closely related means same root cause, same reproduction path, or same
  minimal fix surface.

- MUST NOT use hotfix mode for features, refactors, or architecture changes.

- MUST NOT weaken tests, CI, governance, Sentrux, or validation to make the
  hotfix pass.

## 4. Exit Rules

- MUST complete the gated workflow before final commit and PR submission.

- MUST add or update regression tests unless the owner explicitly scopes this
  as live-debug-only recovery.

- MUST update docs or record a clear N/A reason.

- MUST make the PR close every fixed issue.

- MUST wait for CI to pass before treating the hotfix as complete.

## 5. Deferral Rules

- MUST fix the approved hotfix scope completely.
  MUST NOT leave hidden "later" bug debt.

- If work must be deferred, it MUST have a tracked TODO.

- If a new unrelated bug is found, open or link a separate issue.

## 6. Route

Use these rules with:

- `docs/ai-developer/rules.md`
- `docs/ai-developer/specific_rules/gated-workflow.md` for the final-gate
  workflow that every hotfix exit must complete, including ADR-042 Addendum 5
  receipt under §3.6 and the `scripts/scistudio_pr_create.py` wrapper under
  §3.7
- `docs/ai-developer/specific_rules/bug-fix.md`
- `docs/ai-developer/personas/implementer.md`
- `docs/ai-developer/personas/audit-reviewer.md` when the hotfix comes from
  audit or CI findings
