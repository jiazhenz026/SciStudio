# A2 Audit Core Prompt

Use the SciStudio implementer persona.

Task: implement contract discovery, governance coverage, forbidden production
reference checks, and baseline reconciliation for
`docs/specs/adr-042-change-contract-gate.md`.
Issue: close `#1619` in your PR body.

Branch/worktree:
- Create or use branch `feat/change-contract-gate-audit-core`.
- Use dedicated worktree `C:\Users\jiazh\Desktop\workspace\sci-wt\ccg-audit-core`.
- Base from umbrella branch `track/change-contract-gate-implementation`.

Ownership:
- You own `src/scistudio/qa/audit/change_contracts.py`.
- You own `docs/audit/baselines/change-contract-baseline.json`.
- You own audit-core tests, preferably `tests/qa/test_change_contract_audit.py`.

Out of scope:
- Do not own schema models except by importing A1's public schema module.
- Do not wire `full_audit` or `gate_record/checks.py`.
- Do not own reachability helper internals if A3 has created them.

Requirements:
- Load contracts linked from ADR/spec frontmatter and structured N/A declarations.
- Validate that contract surfaces are covered by parent `governs` or
  `planned_governs`.
- Check forbidden production references separately from docs, tests, generated,
  and allowed scopes.
- Implement stable finding identities and `no_new_violations` baseline
  reconciliation.
- Touched baseline findings must require resolution or renewed issue-backed
  justification.
- Use existing `AuditReport`, `Finding`, and severity conventions.
- Use tracked TODO format only: `TODO(#NNN): ...`.

Verification:
- Run targeted audit-core tests.
- Run the checker against fixtures with one missing contract, one valid N/A,
  one outside-governance surface, one forbidden production reference, and one
  baseline grandfathered finding.
- Final response must list changed files, test commands, and any blockers.
