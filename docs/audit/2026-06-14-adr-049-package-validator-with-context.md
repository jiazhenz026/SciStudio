# ADR-049 Package Validator With-Context Audit

Date: 2026-06-14

Scope: PR #1665 / issue #1664 implementation of ADR-049 package validator
runtime against ADR-049 and
`docs/specs/adr-049-package-validator-implementation.md`.

## Findings

### P1

None open.

During audit, the production registration helper was tightened to satisfy the
ADR-049 isolation and atomicity requirements:

- `validate_for_registration()` now runs the production report through a
  subprocess before any in-process commit preparation.
- `PackageRegistrationPlan.commit_to(...)` commits accepted dry-run rows into
  caller-owned registries only after validation passes.
- rejected reports return `False` from `commit_to(...)` without registry
  mutation;
- live-registry failure during commit rolls back already-written rows.

Regression coverage:
`tests/packages/test_package_validator_production_registration.py`.

### P2

None open.

### P3

None open.

## Evidence Reviewed

- ADR/spec:
  - `docs/adr/ADR-049.md`
  - `docs/specs/adr-049-package-validator-implementation.md`
- Runtime implementation:
  - `src/scistudio/packages/validation/models.py`
  - `src/scistudio/packages/validation/contracts.py`
  - `src/scistudio/packages/validation/inventory.py`
  - `src/scistudio/packages/validation/engine.py`
  - `src/scistudio/packages/validation/registration.py`
  - `src/scistudio/cli/package_validator.py`
  - `src/scistudio/cli/main.py`
- Tests and fixtures:
  - `tests/packages/**`
- Evidence docs:
  - `docs/block-development/package-validator.md`
  - `docs/audit/2026-06-14-adr-049-existing-package-sweep.md`
  - `docs/ai-developer/e2e/2026-06-14-adr-049-package-validator.md`
  - `docs/planning/adr-049-package-validator-implementation-checklist.md`

## Verification

Commands run locally from
`C:\Users\jiazh\Desktop\workspace\sci-wt\package-validator-impl`:

```powershell
$env:PYTHONPATH = "src"
$env:PYTEST_ADDOPTS = "--no-cov"
python -m pytest tests/packages --timeout=60
```

Result: `25 passed`.

```powershell
python scripts/audit/check_package_contract_tables.py
```

Result: `summary: 0 error(s), 9 warning(s)`. The nine warnings match the
ADR-049 known drift baseline.

```powershell
python -m ruff check src/scistudio/packages/validation src/scistudio/cli/package_validator.py tests/packages
python -m ruff format --check src/scistudio/packages/validation src/scistudio/cli/package_validator.py tests/packages
$env:PYTHONPATH = "src"
python -m mypy src/scistudio/packages/validation src/scistudio/cli/package_validator.py
```

Result: ruff clean; mypy clean.

```powershell
$env:PYTHONPATH = "src"
python -m scistudio.qa.audit.full_audit --repo-root . --format json --output .audit/full-audit.json
```

Result: pass after ADR/spec governed contract metadata was moved from
`planned_governs` to `governs` and pointed at actual definition symbols.

Existing package sweep:

- `scistudio`: pass / accept / 0 findings
- `scistudio-blocks-imaging`: pass / accept / 0 findings
- `scistudio-blocks-srs`: pass / accept / 0 findings
- `scistudio-blocks-lcms`: pass / accept / 0 findings

Detailed sweep evidence:
`docs/audit/2026-06-14-adr-049-existing-package-sweep.md`.

## Verdict

PASS. The implementation satisfies the ADR-049 package-validator module scope,
has focused fixture and production-registration coverage, preserves existing
package validity under the production profile, and carries durable e2e/sweep
evidence in the repository.
