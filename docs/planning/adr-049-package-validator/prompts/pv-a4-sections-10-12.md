[DISPATCH-TEMPLATE-V1: test_engineer]

## Task Identity

- Repository: SciStudio
- Owner request: derive ADR-049 package validator contracts from code-first evidence.
- Task kind: manager
- Persona: test_engineer
- Issue: pending / owner-directed local investigation
- Protected branch: main
- Agent label: PV-A4
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

- `docs/planning/adr-049-package-validator/contracts/pv-a4-sections-10-12.json`

You must not touch:

- Production code under `src/scistudio/**`
- Other agents' contract tables
- `docs/planning/adr-049-package-validator-checklist.md`
- `scripts/audit/check_package_contract_tables.py`

## Work To Do

1. Run the mechanical inventory:
   `python scripts/audit/check_package_contract_tables.py --dump-inventory --sections 10,11,12 --output .workflow/local/adr049-inventory-a4.json`
2. Use the inventory as the starting point. Cover every `required: true`
   item with at least one contract row and inspect related code/tests for
   omissions. The checker treats uncovered required inventory items as errors.
3. Investigate implementation first, ADRs second. ADRs may be stale.
4. Write the JSON contract table for:
   - `10_preview_provider_behavior`
   - `11_plot_jobs`
   - `12_security_isolation`
5. Pay special attention to routine provider failures, bounded access,
   plot-job preview-only semantics, same-origin assets, path confinement, and
   subprocess/plugin isolation boundaries.

## Machine Format

Use schema version `adr049.package_contract_table.v1`.
Every contract row must satisfy
`docs/planning/adr-049-package-validator/contracts/contract-table.schema.json`.

## Required Check

After writing your table, run:

`python scripts/audit/check_package_contract_tables.py --sections 10,11,12`

Report changed file paths, checker result, and any ADR drift warnings.
