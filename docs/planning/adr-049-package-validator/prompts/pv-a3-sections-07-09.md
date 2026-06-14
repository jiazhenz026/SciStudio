[DISPATCH-TEMPLATE-V1: test_engineer]

## Task Identity

- Repository: SciStudio
- Owner request: derive ADR-049 package validator contracts from code-first evidence.
- Task kind: manager
- Persona: test_engineer
- Issue: pending / owner-directed local investigation
- Protected branch: main
- Agent label: PV-A3
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

- `docs/planning/adr-049-package-validator/contracts/pv-a3-sections-07-09.json`

You must not touch:

- Production code under `src/scistudio/**`
- Other agents' contract tables
- `docs/planning/adr-049-package-validator-checklist.md`
- `scripts/audit/check_package_contract_tables.py`

## Work To Do

1. Run the mechanical inventory:
   `python scripts/audit/check_package_contract_tables.py --dump-inventory --sections 7,8,9 --output .workflow/local/adr049-inventory-a3.json`
2. Use the inventory as the starting point. Cover every `required: true`
   item with at least one contract row and inspect the non-required data
   boundary, AppBlock/CodeBlock, and previewer items for omissions. The
   checker treats uncovered required inventory items as errors.
3. Investigate implementation first, ADRs second. ADRs may be stale.
4. Write the JSON contract table for:
   - `07_data_transport_runtime_boundary`
   - `08_app_code_block_boundaries`
   - `09_previewer_contracts`
5. Include current implementation behavior for strict errors versus diagnostics.

## Machine Format

Use schema version `adr049.package_contract_table.v1`.
Every contract row must satisfy
`docs/planning/adr-049-package-validator/contracts/contract-table.schema.json`.

## Required Check

After writing your table, run:

`python scripts/audit/check_package_contract_tables.py --sections 7,8,9`

Report changed file paths, checker result, and any ADR drift warnings.
