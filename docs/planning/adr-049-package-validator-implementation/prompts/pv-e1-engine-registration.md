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
- Agent branch: feat/1664-pv-engine-registration
- Agent worktree: C:\Users\jiazh\Desktop\workspace\sci-wt\package-validator-engine
- Gate record: .workflow/records/1664-track-adr-049-package-validator-implementation.json
- Checklist: docs/planning/adr-049-package-validator-implementation-checklist.md

## Required Rules

Read and follow:

- The GitHub issue #1664 and all owner instructions in it.
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

- src/scistudio/packages/validation/engine.py
- src/scistudio/packages/validation/registration.py
- engine/registration portions of tests/packages/test_package_validator.py
- tests/packages/test_package_validator_production_registration.py
- tests/packages/fixtures/package_validator/** only as needed for engine fixtures
- your checklist rows for PV-E1

You must not touch:

- src/scistudio/packages/validation/models.py
- src/scistudio/packages/validation/contracts.py
- src/scistudio/packages/validation/inventory.py unless the manager has merged PV-F1 and explicitly tells you to adapt to its API
- src/scistudio/cli/**
- pyproject.toml
- docs/block-development/**
- docs/ai-developer/**
- docs/audit/**
- CHANGELOG.md

Conditional paths requiring stop-and-report before editing:

- src/scistudio/blocks/registry/**
- src/scistudio/core/types/registry.py
- src/scistudio/previewers/**

Prefer temporary registry composition over modifying core registry APIs.

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

- Partial registration/quarantine UI is out of scope per ADR-049 section 10 and spec section 6.
- Remote sandboxing is out of scope; local process isolation is accepted by spec section 6.

## Work To Do

1. Implement per-surface validation dispatch over ADR-049 contract rows, including `not_applicable`.
2. Build dry-run registry summaries for candidate types, blocks, previewers, format capabilities, runners, and registry-derived API serialization without live mutation.
3. Add cross-surface consistency checks for unknown types, conflicting capability IDs, invalid previewer targets, and serializable descriptors.
4. Implement production registration handoff that rejects on blocking findings and leaves live registries unchanged on failure.
5. Own ADR-049 T-010 for production package-registration call sites: install,
   enable, upgrade, reload, and startup paths that make a package-registration
   decision must go through the production validation handoff before live
   mutation. Existing tolerant startup discovery that is not making an
   install-time registration decision remains out of scope per spec FR-015.
6. Add tests proving valid dry-run pass, invalid package reject, and atomic live commit behavior.

## Required Tests And Checks

- `$env:PYTHONPATH='src'; python -m pytest tests/packages/test_package_validator.py tests/packages/test_package_validator_production_registration.py --timeout=60`
- `python scripts/audit/check_package_contract_tables.py`
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr --base origin/track/adr-049-package-validator-implementation --pr-body-file .workflow/local/pr-body.md`
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
- You need to modify core registry APIs.
- Production validation would mutate live state on failure.
- You cannot add/update required tests.
