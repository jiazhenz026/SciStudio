---
title: "AI New Feature Specific Rules"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
language_source: en
---

# AI New Feature Specific Rules

## 1. Purpose

- Use these rules for AI-authored new features, new subsystems, and meaningful
  behavior additions.

- MUST also run `docs/ai-developer/specific_rules/gated-workflow.md`.

## 2. Feature Start Rules

- MUST confirm the owner request and the expected feature outcome.

- MUST link or create the tracking issue before coding.

- MUST decide if SpecKit is required.
  Use SpecKit for new subsystems or significant design choices.

- MUST decide if a spec is required.
  Specs are required for changed contracts or behavior.

- MUST decide if an ADR is required.
  ADRs are required for architectural or hard-to-reverse decisions.

- MUST record these decisions in the gate record.
  Use a clear N/A reason when SpecKit, spec, or ADR is not needed.

## 3. Feature Scope Rules

- MUST keep one feature task per branch, worktree, issue, and PR.

- MUST NOT hide unrelated refactors, CI cleanup, or bug fixes inside a feature
  PR.

- MUST define affected modules, expected docs, and expected tests before
  coding.

- MUST add or update unit tests for the new feature.

- MUST deliver a complete feature for the approved scope.
  MUST NOT leave hidden V1, MVP, or "later" technical debt.
  If work must be deferred, it MUST have a tracked TODO.

- MUST treat any scope split as explicit.
  The issue, spec, ADR, or gate record must say what is out of scope.

- MUST NOT change core contracts, runtime semantics, storage behavior, or
  plugin contracts without the required spec or ADR.

## 4. Route

Use these rules with:

- `docs/ai-developer/rules.md`
- `docs/ai-developer/specific_rules/gated-workflow.md`
- `docs/ai-developer/personas/implementer.md`
- `docs/ai-developer/personas/adr-author.md` when the feature includes
  spec or ADR writing

ADR-042 Addendum 5 receipt and the `scripts/scistudio_pr_create.py` wrapper
are mandatory for every feature PR; see
`docs/ai-developer/specific_rules/gated-workflow.md` §3.6 and §3.7.
