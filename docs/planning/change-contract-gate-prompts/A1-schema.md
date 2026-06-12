# A1 Schema Prompt

Use the SciStudio implementer persona.

Task: implement the schema layer for `docs/specs/adr-042-change-contract-gate.md`.
Issue: close `#1618` in your PR body.

Branch/worktree:
- Create or use branch `feat/change-contract-gate-schema`.
- Use dedicated worktree `C:\Users\jiazh\Desktop\workspace\sci-wt\ccg-schema`.
- Base from umbrella branch `track/change-contract-gate-implementation`.

Ownership:
- You own `src/scistudio/qa/schemas/change_contracts.py`.
- You may update schema exports if existing local patterns require it.
- You own schema-focused tests, preferably `tests/qa/test_change_contract_schemas.py`.

Out of scope:
- Do not implement audit scanning logic.
- Do not wire `full_audit` or `gate_record`.
- Do not edit A2/A3/A4 files unless the manager amends scope.

Requirements:
- Model `ChangeContract`, `ChangeSurface`, baseline policy, waivers,
  required reachability, required canaries, and structured N/A declarations.
- Use the repo's existing Pydantic/schema conventions.
- Keep contract fields aligned with the spec and frontmatter relationship.
- Add tests for valid contracts, invalid enum values, retained surface required
  fields, waiver required fields, and structured N/A rationale.
- Use tracked TODO format only: `TODO(#NNN): ...`.

Verification:
- Run targeted schema tests.
- Run `python -m scistudio.qa.governance.gate_record check` for your ledger.
- Final response must list changed files, test commands, and any blockers.
