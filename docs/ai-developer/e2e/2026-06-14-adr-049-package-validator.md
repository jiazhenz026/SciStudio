---
session_id: "2026-06-14-adr-049-package-validator"
title: "ADR-049 package validator runtime sweep"
created: "2026-06-14"
owner: "@jiazhenz026"
trigger:
  kind: "feature-sweep"
  ref: "PR #1665 / issue #1664 / ADR-049"
related_adrs:
  - 49
status: "passed"
language_source: en
---

# E2E Session - ADR-049 Package Validator Runtime Sweep

## 1. Goal And Out-Of-Scope

- **Goal**: Prove the ADR-049 validator can run end to end through its public
  CLI/API, reject invalid packages without live registry mutation, and accept
  every existing in-repository SciStudio package under the production profile.
- **Out of scope**: Browser GUI rendering, third-party marketplace install UI,
  remote sandboxing, and partial package quarantine UI.

## 2. Preconditions

- **Repo state**: `track/adr-049-package-validator-implementation` at or after
  `e3ca1a7b` with the ADR-049 validator candidate diff applied.
- **Working tree**: acceptable dirty paths are the ADR-049 implementation,
  tests, docs, gate ledger, audit report, e2e scenario, checklist, ADR/spec
  metadata, and changelog files for PR #1665.
- **Worktree to run from**:
  `C:\Users\jiazh\Desktop\workspace\sci-wt\package-validator-impl`
- **Backend port**: not used.
- **Frontend mode**: not used; this feature-sweep verifies CLI/API behavior.
- **Required services / env vars**: `PYTHONPATH=src`.
- **Required data / fixtures**:
  `tests/packages/fixtures/package_validator/**` and in-repo package source
  trees under `packages/scistudio-blocks-*`.
- **External accounts**: none.

## 3. Launch Plan

- **Backend start**:
  ```powershell
  # Not used. The package validator is a CLI/API runtime surface.
  ```
- **Frontend start** (only if Vite dev server is needed):
  ```powershell
  # Not used.
  ```
- **Readiness probe**:
  ```powershell
  $env:PYTHONPATH = "src"
  python -c "import scistudio.packages.validation as v; print(v.PackageValidationProfile.PRODUCTION.value)"
  ```
- **Cleanup commands** (will run at end of session, even on failure):
  ```powershell
  # No persistent server process is started.
  ```

## 4. Affordances Under Test

- Public API: `scistudio.packages.validation.validate_package`.
- Production helper:
  `scistudio.packages.validation.registration.validate_for_registration`.
- CLI module: `python -m scistudio.cli.package_validator`.
- Root CLI registration: `scistudio package-validator`.
- ADR-049 contract table loader and applicability model.
- Dry-run type, block, previewer, IO capability, runner, and API registry
  summary generation.
- Production accept/reject behavior for invalid and valid package candidates.

## 5. Steps

### Step 1 - Import Public Validator API

- **Action**: Run the readiness probe in Section 3.
- **Expected**: The command exits 0 and prints `production`.
- **Capture**: console output.
- **On failure**: halt.

### Step 2 - Run Targeted Package Validator Tests

- **Action**:
  ```powershell
  $env:PYTHONPATH = "src"
  $env:PYTEST_ADDOPTS = "--no-cov"
  python -m pytest tests/packages --timeout=60
  ```
- **Expected**: All package validator tests pass, including invalid fixtures,
  report schema checks, CLI exit-code checks, monorepo sibling dependency
  inventory, and production registration atomicity.
- **Capture**: console output.
- **On failure**: halt.

### Step 3 - Validate A Passing Fixture Through CLI JSON

- **Action**:
  ```powershell
  $env:PYTHONPATH = "src"
  python -m scistudio.cli.package_validator tests/packages/fixtures/package_validator/valid_package --profile production --json
  ```
- **Expected**: Exit code is 0, `status` is `pass`, `registration_decision` is
  `accept`, and dry-run registry counts include blocks, types, previewers, and
  format capabilities.
- **Capture**: response JSON.
- **On failure**: halt.

### Step 4 - Validate A Failing Fixture Through CLI JSON

- **Action**:
  ```powershell
  $env:PYTHONPATH = "src"
  python -m scistudio.cli.package_validator tests/packages/fixtures/package_validator/invalid_block_package --profile production --json
  ```
- **Expected**: Exit code is nonzero, `status` is `fail`,
  `registration_decision` is `reject`, and findings include `PV-04-001`.
- **Capture**: response JSON.
- **On failure**: halt.

### Step 5 - Run Existing Package Production Sweep

- **Action**: Run the production validator against `.`,
  `packages/scistudio-blocks-imaging`, `packages/scistudio-blocks-srs`, and
  `packages/scistudio-blocks-lcms`.
- **Expected**: Every package exits 0 with `status=pass`,
  `registration_decision=accept`, and zero findings.
- **Capture**: summarized JSON evidence in
  `docs/audit/2026-06-14-adr-049-existing-package-sweep.md`.
- **On failure**: halt.

### Step 6 - Run ADR-049 Contract Table Checker

- **Action**:
  ```powershell
  python scripts/audit/check_package_contract_tables.py
  ```
- **Expected**: The checker exits 0 with zero errors. The known ADR-049 drift
  baseline remains nine warnings.
- **Capture**: console output.
- **On failure**: halt.

## 6. Regression Sentinels

- **Console errors**: no Python tracebacks in any CLI command.
- **Network errors**: not applicable; no network server is started.
- **Native dialogs**: none.
- **Process health**: no persistent process remains after the sweep.
- **Registry mutation**: production rejection tests must leave live registries
  unchanged.
- **Package sweep**: no existing in-repository package may report findings under
  the production profile.

## 7. Results

### 7.1 Verdict

PASS. The ADR-049 validator ran end to end through its public API and CLI,
rejected invalid fixtures, preserved live registries on production rejection,
and accepted all existing in-repository SciStudio packages under the production
profile.

### 7.2 Per-Step Outcome

| Step | Outcome | Evidence | Notes |
|------|---------|----------|-------|
| 1 | PASS | `python -c "import scistudio.packages.validation as v; print(v.PackageValidationProfile.PRODUCTION.value)"` prints `production`. | Public API imports from the source checkout. |
| 2 | PASS | `$env:PYTHONPATH='src'; $env:PYTEST_ADDOPTS='--no-cov'; python -m pytest tests/packages --timeout=60` -> `25 passed`. | Covers fixtures, report envelope, CLI, subprocess-first production registration, atomic commit rollback, and monorepo dependency inventory. |
| 3 | PASS | Valid fixture CLI exits 0 with `status=pass`, `registration_decision=accept`, and dry-run blocks/types/previewers/capabilities. | JSON schema version is `adr049.package_validation_report.v1`. |
| 4 | PASS | Invalid block fixture CLI exits 1 with `status=fail`, `registration_decision=reject`, and finding `PV-04-001`. | Confirms CLI nonzero failure behavior. |
| 5 | PASS | `docs/audit/2026-06-14-adr-049-existing-package-sweep.md` records core, imaging, SRS, and LCMS all as `pass` / `accept` with zero findings. | SRS sibling dependency is resolved only because it is declared in `project.dependencies`. |
| 6 | PASS | `python scripts/audit/check_package_contract_tables.py` -> `summary: 0 error(s), 9 warning(s)`. | Warning IDs match the ADR-049 known drift baseline. |

### 7.3 Sentinel Hits

None.

### 7.4 Artifacts

- `tests/packages/**`
- `docs/audit/2026-06-14-adr-049-existing-package-sweep.md`
- `docs/block-development/package-validator.md`
- `docs/ai-developer/e2e/2026-06-14-adr-049-package-validator.md`

No Chrome screenshots were produced because the package validator has no
browser affordance in this implementation; the acceptance surface is the public
Python API and CLI.

### 7.5 Follow-Ups

None.
