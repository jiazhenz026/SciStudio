# Documentation Governance

## 1. Decision Summary

Documentation is part of the product and part of the repository contract.
Skills should point to canonical docs and rule modules rather than duplicating
large policy blocks.

Documentation rules:

- Update specs when changing object models, block protocols, runtime behavior,
  storage behavior, API contracts, plugin contracts, major UI semantics, AI
  orchestration behavior, or external app integration.
- Update ADRs when making architectural, hard-to-reverse, cross-module, or
  long-term tradeoff decisions.
- Update `CHANGELOG.md` for meaningful behavior, governance, feature, bugfix,
  or capability changes.
- Keep hand-authored docs concise and structured.
- Prefer explicit not-applicable rationale over silent omission.

ADR and spec direction:

- New ADRs should follow ADR-042 frontmatter and section expectations where
  practical.
- New specs should remain compatible with the repository SpecKit workflow.

Skill pointer rule:

- Canonical skill source is `ai_developers/skills/`.
- Skills should be short operational entry points.
- Skills should link to `AGENTS.md` and `ai_developers/rules/`.
- Do not make runtime mirror skills more authoritative than the canonical
  source.
