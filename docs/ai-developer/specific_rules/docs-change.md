---
title: "AI Docs Change Specific Rules"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
language_source: en
---

# AI Docs Change Specific Rules

## 1. Purpose

- Use these rules for AI-authored documentation-only changes.

- MUST also run `docs/ai-developer/specific_rules/gated-workflow.md`.

## 2. Truth Rules

- MUST describe current implementation as current.
  MUST describe planned work as planned.

- MUST NOT claim a feature, command, API, check, or workflow exists unless it
  is implemented and verifiable.

- MUST NOT hide missing behavior behind vague words like "supports",
  "integrates", or "handles".

- MUST cite the governing ADR, spec, issue, or code path when the document
  states a contract.

## 3. Document Type Rules

- MUST follow the required structure for the document type being edited.

- MUST use `docs/ai-developer/specific_rules/document-standards.md` as the
  ADR-042 reference for ADR, spec, frontmatter, first-section, generated-doc,
  and location standards.

- MUST keep AI-only operating rules under `docs/ai-developer/**`.
  Do not place AI-only procedures in human contributor docs.

- MUST keep human-facing contributor docs human-facing.
  They may link to AI docs but must not duplicate AI-only rules.

- MUST keep generated docs generated.

## 4. Scope Rules

- MUST keep docs changes scoped to the approved issue and gate record.

- MUST NOT rewrite unrelated docs for style, tone, or cleanup.

- MUST NOT change architecture meaning as a wording cleanup.
  Use an ADR or spec update when meaning changes.

- MUST NOT move rules between `AGENTS.md`, ADRs, specs, and AI docs without
  owner-approved scope.

## 5. Check Rules

- MUST run the docs checks required by the gate plan.

- MUST run frontmatter lint when editing ADRs, specs, or governed docs.

- MUST run ADR-042 QA full audit when available.

- MUST record N/A reasons for tests when the change is truly docs-only.

- MUST wait for CI to pass before treating the docs change as complete.

## 6. Route

Use these rules with:

- `docs/ai-developer/rules.md`
- `docs/ai-developer/specific_rules/document-standards.md`
- `docs/ai-developer/specific_rules/gated-workflow.md`
- `docs/ai-developer/personas/adr-author.md` when editing ADRs or specs
- `docs/ai-developer/personas/audit-reviewer.md` when fixing audit findings

ADR-042 Addendum 5 receipt and the `scripts/scistudio_pr_create.py` wrapper
apply to every docs-change PR that touches `docs/adr/`, `docs/specs/`, or
`docs/ai-developer/`; see
`docs/ai-developer/specific_rules/gated-workflow.md` §3.6 and §3.7.
