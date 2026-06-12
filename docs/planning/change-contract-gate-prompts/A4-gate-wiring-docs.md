# A4 Gate Wiring And Docs Prompt

Use the SciStudio implementer persona.

Task: wire the change contract checker into full audit, gate-record routing, and
authoring documentation.
Issue: close `#1621` in your PR body.

Branch/worktree:
- Create or use branch `feat/change-contract-gate-wiring`.
- Use dedicated worktree `C:\Users\jiazh\Desktop\workspace\sci-wt\ccg-wiring`.
- Base from umbrella branch `track/change-contract-gate-implementation`.

Ownership:
- You own `src/scistudio/qa/audit/full_audit.py`.
- You own `src/scistudio/qa/governance/gate_record/checks.py`.
- You own `docs/ai-developer/specific_rules/document-standards.md`.
- You own integration tests for full audit and gate selection.

Out of scope:
- Do not implement schema internals.
- Do not implement contract scan internals beyond importing A2's checker.
- Do not edit unrelated governance rules or weaken existing checks.

Requirements:
- Add `change_contracts` as a full audit child report.
- Add a selectable gate check for change contracts.
- Select the check for ADR/spec, architecture, governance, and broad refactor
  diffs as required by the spec.
- Document authoring rules: when a contract is required, when structured N/A is
  allowed, how contracts relate to `governs`, and how baselines/waivers work.
- Because this touches `docs/ai-developer/**` and gate code, declare
  `governance_touch=true` and request `admin-approved:core-change` in your
  gate ledger.
- Use tracked TODO format only: `TODO(#NNN): ...`.

Verification:
- Run targeted full audit integration tests.
- Run targeted gate-record check selection tests.
- Run frontmatter/documentation lint if changed docs require it.
- Final response must list changed files, test commands, and any blockers.
