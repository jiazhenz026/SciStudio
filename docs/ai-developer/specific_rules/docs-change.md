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

- MUST keep docs changes scoped to the approved issue and gate ledger.

- MUST NOT rewrite unrelated docs for style, tone, or cleanup.

- MUST NOT change architecture meaning as a wording cleanup.
  Use an ADR or spec update when meaning changes.

- MUST NOT move rules between `AGENTS.md`, ADRs, specs, and AI docs without
  owner-approved scope.

## 5. Check Rules

- MUST run `gate_record check` to run all docs checks required by the observed
  diff. `gate_record check` automatically includes frontmatter lint, full audit,
  docs/closure checks, and governance checks when the diff includes ADRs, specs,
  or `docs/ai-developer/**` files.

- MUST record N/A reasons for implementation tests when the change is truly
  docs-only: `amend --test-na "implementation:<reason>"`.

- MUST wait for CI to pass before treating the docs change as complete.

- Changes to `docs/ai-developer/**` are a governance surface per ADR-042
  Addendum 6 §7.8. Use `--governance-touch true` at `init` when editing AI
  developer rules, persona guides, specific rules, dispatch templates, or skills.
  These changes are evaluated with governance checks even when the task kind is
  `docs`.

## 6. Route

Use these rules with:

- `docs/ai-developer/rules.md`
- `docs/ai-developer/specific_rules/document-standards.md`
- `docs/ai-developer/specific_rules/gated-workflow.md`
- `docs/ai-developer/personas/adr-author.md` when editing ADRs or specs
- `docs/ai-developer/personas/audit-reviewer.md` when fixing audit findings

The `scripts/scistudio_pr_create.py` wrapper applies to every docs-change PR
that touches `docs/adr/`, `docs/specs/`, or `docs/ai-developer/`.
`gate_record check --mode pre-pr` and pre-PR `finalize` replace the old
`gate_receipt` tooling; see
`docs/ai-developer/specific_rules/gated-workflow.md` §3.6 and §3.7.

`docs` is a Tier 3 task. The full task-kind CLI argument profile is in
ADR-042 Addendum 6 §7.7.4.
