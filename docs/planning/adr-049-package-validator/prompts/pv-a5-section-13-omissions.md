[DISPATCH-TEMPLATE-V1: test_engineer]

## Task Identity

- Repository: SciStudio
- Owner request: derive ADR-049 package validator contracts from code-first evidence.
- Task kind: manager
- Persona: test_engineer
- Issue: pending / owner-directed local investigation
- Protected branch: main
- Agent label: PV-A5
- Gate record:
  `.workflow/records/design-package-validator-contract-survey-design-package-validator-contract-survey.json`
- Checklist: `docs/planning/adr-049-package-validator-checklist.md`

## Required Rules

Read and follow:

- `AGENTS.md`
- `docs/ai-developer/rules.md`
- `docs/ai-developer/specific_rules/test-engineering.md`
- `docs/ai-developer/personas/test-engineer.md`

## Scope

You own only:

- `docs/planning/adr-049-package-validator/contracts/pv-a5-section-13-omissions.json`

You must not touch:

- Production code under `src/scistudio/**`
- Other agents' contract tables
- `docs/planning/adr-049-package-validator-checklist.md`
- `scripts/audit/check_package_contract_tables.py`

## Work To Do

1. Run the mechanical inventory:
   `python scripts/audit/check_package_contract_tables.py --dump-inventory --sections 13,99 --output .workflow/local/adr049-inventory-a5.json`
2. Also run a broad inventory without filter:
   `python scripts/audit/check_package_contract_tables.py --dump-inventory --output .workflow/local/adr049-inventory-all.json`
3. Use the inventory as the starting point. Cover every section-13
   `required: true` item with at least one contract row.
   The checker treats uncovered required inventory items as errors.
4. Investigate implementation first, ADRs second. ADRs may be stale.
5. Write the JSON contract table for:
   - `13_cross_surface_registry_consistency`
   - `99_omitted_or_discovered_contracts`
6. Extra duty: search for package-facing contracts omitted by sections 1-13.
   Check entry point groups, public registries, API serialization, package
   tests, scaffold templates, docs, and generated facts. Add omissions under
   both `contracts` section `99_omitted_or_discovered_contracts` and the
   top-level `omissions` array when warranted.

## Machine Format

Use schema version `adr049.package_contract_table.v1`.
Every contract row must satisfy
`docs/planning/adr-049-package-validator/contracts/contract-table.schema.json`.

## Required Check

After writing your table, run:

`python scripts/audit/check_package_contract_tables.py --sections 13,99`

Report changed file paths, checker result, omitted contracts found, and any ADR
drift warnings.
