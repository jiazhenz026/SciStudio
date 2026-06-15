---
title: "Fix Readiness Audit: PR1665 Package Validator Audit Blockers"
date: 2026-06-15
auditor: "Codex manager"
pr: 1665
status: pass-with-review
related_issue: 1664
governed_by:
  - ADR-049
---

# Fix Readiness Audit: PR1665 Package Validator Audit Blockers

## Verdict

Pass with review.

This follow-up verifies the fix branch for the PR1665 no-context audit blockers.
The branch keeps the package validator focused on ADR-049 while closing the
false-pass and production-registration safety gaps raised by the audit.

## Finding Closure

### P1-1 Production validation imported candidate code in the live process

Fixed. `validate_for_registration(...)` now makes the production accept/reject
decision from a subprocess report and returns a lazy plan. The caller process
does not import the candidate while the plan decision is being made. The
regression test `test_production_plan_does_not_import_candidate_before_commit`
asserts that the valid fixture package is not present in `sys.modules` after
plan creation.

### P1-2 Wheel/sdist/archive inputs could be accepted as metadata-only packages

Fixed. Archive inventory now extracts wheels/source distributions, reads package
metadata, and preserves SciStudio entry points for validation. Unsupported or
malformed archive metadata produces a structured failure report. Regression
coverage includes wheel entry-point validation in
`test_wheel_entry_points_are_validated_instead_of_treated_as_metadata_only`
and wheel inventory parsing in `test_wheel_inventory_reads_distribution_entry_points`.

### P1-3 Applicable contract rows could be reported as `pass` without execution

Fixed. The engine tracks executed contract IDs and reports applicable but
unexecuted rows as `skipped` with evidence instead of `pass`. The regression
test `test_applicable_unexecuted_contract_rows_are_not_reported_as_pass`
asserts this behavior.

### P2-1 Unknown `scistudio.*` entry-point groups were silently ignored

Fixed. Inventory preserves unknown SciStudio entry-point groups, and validation
turns them into structured `PV-02-002` findings. Regression coverage:
`test_source_inventory_keeps_unknown_scistudio_entry_point_groups` and
`test_unknown_scistudio_entry_point_group_is_a_structured_failure`.

### P2-2 Existing-package conflicts were not checked before `accept`

Fixed for caller-provided live registries. `validate_for_registration(...)`
accepts existing block/type/previewer/runner registries and rejects conflicting
candidate capability, type, previewer, or runner IDs before commit. Regression
coverage: `test_production_registration_rejects_existing_capability_conflict_before_commit`.

### P2-3 Source-tree import isolation leaked `sys.modules`

Fixed. `candidate_import_context(...)` snapshots module state and removes
modules imported from candidate source paths when the context exits. Regression
coverage: `test_candidate_import_context_removes_source_modules`.

### P2-4 Dry-run type registries included built-ins and committed all dry-run types

Fixed. `DryRunBuilder` tracks candidate rows separately from built-ins. Report
summaries and `commit_to(...)` now use candidate blocks, types, previewers,
format capabilities, and runners only. Cross-surface block-port checks still
permit types imported from declared dependency packages; SRS is covered in the
existing-package sweep below to guard against false rejects.

### P2-5 Inventory failures escaped as exceptions

Fixed. Public validation catches inventory and contract-loading failures and
returns a structured `PackageValidationReport` with a blocking `PV-01-001`
finding. Regression coverage: `test_bad_source_metadata_returns_structured_report`.

### P2-6 Profile/severity policy was disconnected from contract-row behavior

Fixed. Findings now carry `profile_behavior` from the ADR-049 contract row, and
profile behavior can upgrade severity for production blockers without
downgrading structurally impossible package errors.

### P3-1 `PackageInfo` validation was too narrow

Fixed. The validator now checks non-empty `name`/`version`, string
`description`/`author`, and emits a warning when `PackageInfo.name` differs from
the package distribution name.

### P3-2 Tests missed the false-pass cases

Fixed. The package validator suite now includes regressions for wheel parsing,
unknown entry-point groups, source-module cleanup, structured inventory failure,
lazy production plans, existing registry conflicts, and applicable-unexecuted
contract result classification. It also covers the distinction between
candidate-local DataObject types that must be returned from `scistudio.types`
and declared-dependency DataObject types that candidate block ports may
reference.

### Gate environment compatibility

Fixed. The gate wrapper's isolated FastAPI dependency set exposes included
routers as wrapper entries in `app.routes`, while the ambient environment
eagerly expands them. The runtime route contract now recursively collects
effective paths, preserving the same required-route assertions across both
environments.

## Verification

Targeted package validator verification:

```powershell
$env:PYTHONPATH='src'
python -m pytest --no-cov `
  tests/packages/test_package_validator.py `
  tests/packages/test_package_validator_reports.py `
  tests/packages/test_package_validator_inventory.py `
  tests/packages/test_package_validator_production_registration.py `
  tests/packages/test_package_validator_cli.py -q
```

Result: `38 passed`.

Existing package production-profile sweep:

| Candidate | Status | Decision | Findings |
|---|---|---|---:|
| `.` (`scistudio`) | `pass` | `accept` | 0 |
| `packages/scistudio-blocks-imaging` | `pass` | `accept` | 0 |
| `packages/scistudio-blocks-lcms` | `pass` | `accept` | 0 |
| `packages/scistudio-blocks-srs` | `pass` | `accept` | 0 |
| `tests/packages/fixtures/package_validator/valid_package` | `pass` | `accept` | 0 |

ADR-049 contract table checker remains at the expected baseline:
`summary: 0 error(s), 9 warning(s)`.

Additional gate-risk checks:

- `python -m pytest --no-cov tests/packages/test_package_validator.py tests/packages/test_package_validator_reports.py tests/packages/test_package_validator_inventory.py tests/packages/test_package_validator_production_registration.py tests/packages/test_package_validator_cli.py tests/contracts/test_runtime_import_contract.py -q` -> `56 passed`.
- `.workflow\local\venv\Scripts\python.exe -m pytest --no-cov tests/contracts/test_runtime_import_contract.py -q` -> `19 passed`.
- `python scripts/semantic_dup_scan.py --check docs/audit/baselines/semantic-dup-baseline.json` -> all ratchets within limits.
- Full local pytest with source package entry-point overlay and
  `PYTEST_ADDOPTS=-m "not requires_imaging"` -> `4506 passed, 62 skipped,
  8 xfailed`.
