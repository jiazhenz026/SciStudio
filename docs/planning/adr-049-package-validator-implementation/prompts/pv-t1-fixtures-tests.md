[DISPATCH-TEMPLATE-V1: test_engineer]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-049 package validator runtime from PR #1662.
- Task kind: feature
- Persona: test_engineer
- Issue: #1664
- Issue URL: https://github.com/zjzcpj/SciStudio/issues/1664
- Umbrella PR: pending `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-049-package-validator-implementation
- Agent branch: feat/1664-pv-fixtures-tests
- Agent worktree: C:\Users\jiazh\Desktop\workspace\sci-wt\package-validator-fixtures-tests
- Gate record: .workflow/records/1664-track-adr-049-package-validator-implementation.json
- Checklist: docs/planning/adr-049-package-validator-implementation-checklist.md

## Required Rules

Read and follow:

- The GitHub issue #1664 and all owner instructions in it.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/test-engineering.md
- docs/ai-developer/personas/test-engineer.md
- docs/adr/ADR-049.md
- docs/specs/adr-049-package-validator-implementation.md
- docs/planning/adr-049-package-validator/contracts/*.json

## Scope

You own only:

- tests/packages/fixtures/package_validator/**
- tests/packages/test_package_validator.py
- tests/packages/test_package_validator_reports.py
- tests/packages/test_package_validator_cli.py
- tests/packages/test_package_validator_production_registration.py
- your checklist rows for PV-T1

You must not touch:

- src/scistudio/**
- pyproject.toml
- docs/block-development/**
- docs/ai-developer/**
- docs/audit/**
- CHANGELOG.md

If you need production-code changes, stop and report back with the failing test or fixture evidence.

## Coordination

- You are not alone in this codebase.
- MUST work only on your assigned branch.
- MUST work only in your assigned worktree.
- MUST NOT use `pip install -e .`.
- Do not revert or overwrite other agents' work.
- Do not broaden scope.
- MUST target your PR to `track/adr-049-package-validator-implementation`.
- MUST NOT target your PR to `main`.
- MUST NOT merge any PR unless the owner explicitly authorizes it.
- Edit only your checklist rows.

## TODO And Deferral Rule

Deferred work must be tracked in the repo.
Use `TODO(#NNN): <reason>` and cite an issue, ADR, spec, or follow-up ticket.
Do not leave hidden V1, MVP, or later work.

Known deferred items:

- None for the test matrix. If a required fixture cannot be implemented without production code, report it instead of skipping silently.

## Work To Do

1. Design fixture packages for one valid package and at least five invalid packages covering invalid block, invalid type Meta, invalid previewer payload or manifest, invalid IO capability, conflicting capability ID, unknown cross-surface target type, and no-entry-point package.
2. Add executable tests mapped to ADR-049 requirements and spec success criteria SC-001 through SC-007.
3. Keep tests focused on public validation APIs that PV-F1/PV-E1/PV-C1 are expected to implement.
4. Mark expected failures only if the implementation branch is not ready yet; remove xfail before PR readiness or report the blocker.

## Required Tests And Checks

- `$env:PYTHONPATH='src'; python -m pytest tests/packages --timeout=60`
- `python scripts/audit/check_package_contract_tables.py`
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr --base origin/design/package-validator-contract-survey --pr-body-file .workflow/local/pr-body.md`
- Sentrux: N/A unless gate_record selects it.

## Output Required

Before reporting done, provide:

- Changed fixture/test paths.
- Tests/checks run and results.
- Checklist rows updated.
- PR number or commit.
- Any product-code blocker with exact failing test.

## Stop Conditions

Stop and report back if:

- You need to edit production code.
- The task conflicts with AGENTS.md, ADR, spec, or gate record.
- Tests require hidden assumptions not present in ADR/spec.
