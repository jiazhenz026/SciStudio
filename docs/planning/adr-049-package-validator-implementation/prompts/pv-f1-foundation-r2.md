[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-049 package validator runtime from PR #1662.
- Task kind: feature
- Persona: implementer
- Issue: #1664
- Issue URL: https://github.com/zjzcpj/SciStudio/issues/1664
- Umbrella PR: #1665 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-049-package-validator-implementation
- Agent branch: feat/1664-pv-foundation-r2
- Agent worktree: C:\Users\jiazh\Desktop\workspace\sci-wt\package-validator-foundation-r2
- Gate record: create/update your own feature ledger under `.workflow/records/`
- Checklist: docs/planning/adr-049-package-validator-implementation-checklist.md
- Replacement note: prior PV-F1 was shut down after producing only an untracked
  ledger and no implementation changes. Do not use that worktree.

## Required Rules

Read and follow:

- The GitHub issue #1664 and all owner instructions in it.
- PR #1662 ADR/spec branch content.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/new-feature.md
- docs/ai-developer/personas/implementer.md
- docs/adr/ADR-049.md
- docs/specs/adr-049-package-validator-implementation.md
- docs/planning/adr-049-package-validator/contracts/*.json

## Scope

You own only:

- src/scistudio/packages/validation/__init__.py
- src/scistudio/packages/validation/models.py
- src/scistudio/packages/validation/contracts.py
- src/scistudio/packages/validation/inventory.py
- tests/packages/test_package_validator_reports.py
- foundation portions of tests/packages/test_package_validator.py
- tests/packages/fixtures/package_validator/** only as needed for
  inventory/model tests
- your checklist rows for PV-F1-R2

You must not touch:

- src/scistudio/packages/validation/engine.py
- src/scistudio/packages/validation/registration.py
- src/scistudio/cli/**
- src/scistudio/blocks/registry/**
- src/scistudio/core/types/registry.py
- src/scistudio/previewers/**
- docs/block-development/package-validator.md
- docs/ai-developer/**
- docs/audit/**
- pyproject.toml
- CHANGELOG.md

If you need an out-of-scope path, stop and report back. Do not edit it.

## Coordination

- You are not alone in this codebase.
- MUST work only on `feat/1664-pv-foundation-r2`.
- MUST work only in
  `C:\Users\jiazh\Desktop\workspace\sci-wt\package-validator-foundation-r2`.
- MUST NOT use `pip install -e .`.
- Do not revert or overwrite other agents' work.
- Do not broaden scope.
- MUST target any PR to `track/adr-049-package-validator-implementation`.
- MUST NOT target any PR to `main`.
- MUST NOT merge any PR unless the owner explicitly authorizes it.
- Edit only your checklist rows.
- Record every completed row with a PR, commit, test, report, or gate evidence.

## TODO And Deferral Rule

Deferred work must be tracked in the repo. Use
`TODO(#NNNN): <reason>` and cite an issue, ADR, spec, or follow-up ticket.
Do not leave hidden V1, MVP, or later work.

Known deferred items:

- Partial production registration/quarantine is out of scope per ADR-049
  section 10 and spec section 6.
- Moving contract tables out of docs/planning is out of scope per spec section 6.

## Work To Do

1. Create the public validation package skeleton and exports.
2. Implement `PackageValidationProfile`, candidate/inventory/result/finding/report
   models, status derivation, registration decision derivation, and JSON
   serialization compatible with ADR-049.
3. Implement ADR-049 contract table loading, schema-version checks, duplicate ID
   detection, profile/applicability normalization, and missing applicability
   failures.
4. Implement candidate package inventory for source tree paths, installed
   distribution names, wheel/sdist paths where practical, no-entry-point
   packages, and entry-point metadata without live registry mutation.
5. Add focused report/contract/inventory tests and fixtures.

## Required Tests And Checks

- `python scripts/audit/check_package_contract_tables.py`
- `$env:PYTHONPATH='src'; python -m pytest tests/packages/test_package_validator_reports.py tests/packages/test_package_validator.py --timeout=60`
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr --base origin/design/package-validator-contract-survey --pr-body-file .workflow/local/pr-body.md`
- `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#1664"` before PR creation
- `python scripts/scistudio_pr_create.py --base track/adr-049-package-validator-implementation` if opening an agent PR
- Sentrux: N/A unless gate_record selects it.

## Output Required

Before reporting done, provide:

- Changed file paths.
- Tests/checks run and results.
- Checklist rows updated.
- PR number or commit.
- Any blocker or scope issue.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file.
- The task conflicts with AGENTS.md, ADR, spec, or gate record.
- CI or local checks fail for unclear reasons.
- Another agent's work blocks yours.
- You cannot add/update required tests.
