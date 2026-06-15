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
- Agent branch: feat/1664-pv-cli-docs-evidence
- Agent worktree: C:\Users\jiazh\Desktop\workspace\sci-wt\package-validator-cli-docs
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
- docs/ai-developer/skills/scistudio-e2e-test/SKILL.md for scenario shape only; the manager will run final live e2e.
- docs/adr/ADR-049.md
- docs/specs/adr-049-package-validator-implementation.md

## Scope

You own only:

- src/scistudio/cli/package_validator.py
- src/scistudio/cli/main.py
- pyproject.toml if a script entry is needed
- tests/packages/test_package_validator_cli.py
- docs/block-development/package-validator.md
- docs/ai-developer/e2e/2026-06-14-adr-049-package-validator.md
- docs/audit/2026-06-14-adr-049-existing-package-sweep.md
- CHANGELOG.md
- your checklist rows for PV-C1

You must not touch:

- src/scistudio/packages/validation/engine.py
- src/scistudio/packages/validation/registration.py
- src/scistudio/packages/validation/models.py unless adapting imports after manager integration
- src/scistudio/blocks/registry/**
- src/scistudio/core/types/registry.py
- src/scistudio/previewers/**

If you need an out-of-scope path, stop and report back.
Do not edit it.

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

- None for CLI/docs/evidence. If a package cannot be scanned because of a missing optional dependency, the audit evidence must record the package, profile, and validator status rather than hiding it.

## Work To Do

1. Add the package validator CLI wrapper with JSON output, profile selection, and nonzero exit code on failed selected profile.
2. Register the CLI through the existing Typer app or a script entry, following current CLI patterns.
3. Add CLI tests.
4. Add author-facing docs with command examples and report semantics.
5. Prepare the e2e scenario file. The manager will execute the final live run and fill Section 7.
6. After integration, run the package validator against every existing SciStudio package in this repository and save an audit evidence report.

## Required Tests And Checks

- `$env:PYTHONPATH='src'; python -m pytest tests/packages/test_package_validator_cli.py --timeout=60`
- `python scripts/audit/check_package_contract_tables.py`
- final package sweep command over core, imaging, SRS, LCMS, and repository package fixtures
- e2e scenario: docs/ai-developer/e2e/2026-06-14-adr-049-package-validator.md
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr --base origin/track/adr-049-package-validator-implementation --pr-body-file .workflow/local/pr-body.md`
- Sentrux: N/A unless gate_record selects it.

## Output Required

Before reporting done, provide:

- Changed file paths.
- Tests/checks run and results.
- Checklist rows updated.
- PR number or commit.
- Existing package sweep status and evidence path.
- Any blocker or scope issue.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file.
- E2E scenario would mutate a shared resource.
- Existing package sweep exposes a product bug requiring engine changes.
