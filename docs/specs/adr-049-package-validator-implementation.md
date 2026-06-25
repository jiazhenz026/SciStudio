---
spec_id: adr-049-package-validator-implementation
title: "ADR-049 Package Validator Implementation Specification"
status: Planned
feature_branch: design/package-validator-contract-survey
created: 2026-06-14
input: "Owner request: define an executable implementation plan for the ADR-049 package validator that validates package contracts during development and before production registration."
owners:
  - "@jiazhenz026"
related_adrs:
  - 49
related_specs: []
scope:
  in:
    - Runtime package validator models, report schema, validation profiles, and candidate package inventory.
    - Development CLI and test helper entry points for source trees, wheels, and installed distributions.
    - Production install-time validation before live type, block, previewer, IO capability, runner, or API-facing registry mutation.
    - Contract applicability selection from ADR-049 contract table rows.
    - Dry-run registries for candidate types, blocks, previewers, format capabilities, runner declarations, and registry-derived API payloads.
    - Structured validation report output for CLI, desktop, logs, and CI.
    - Package fixture tests that prove invalid packages are rejected and valid packages are registered atomically.
  out:
    - Shipping a third-party package marketplace.
    - Defining remote plugin sandboxing beyond the local isolation process required for validation.
    - Partial production registration or quarantine UI beyond a structured reject report.
    - Migrating every existing package contract warning to a production blocker in the first implementation PR.
    - Rewriting tolerant startup scans that are not package-install validation paths.
governs:
  modules:
    - scistudio.blocks.registry
    - scistudio.blocks.io.capabilities
    - scistudio.core.types.registry
    - scistudio.previewers
  contracts:
    - scistudio.blocks.base.package_info.PackageInfo
    - scistudio.blocks.registry.BlockRegistry
    - scistudio.blocks.io.capabilities.FormatCapability
    - scistudio.core.types.registry.TypeRegistry
    - scistudio.previewers.registry.PreviewerRegistry
    - scistudio.previewers.models.PreviewerSpec
  entry_points:
    - scistudio.blocks
    - scistudio.types
    - scistudio.previewers
    - scistudio.runners
  files:
    - docs/adr/ADR-049.md
    - docs/specs/adr-049-package-validator-implementation.md
    - docs/planning/adr-049-package-validator/contracts/**
    - scripts/audit/check_package_contract_tables.py
    - pyproject.toml
planned_governs:
  modules:
    - scistudio.packages.validation
    - scistudio.cli.package_validator
  contracts:
    - scistudio.packages.validation.PackageValidationProfile
    - scistudio.packages.validation.CandidatePackage
    - scistudio.packages.validation.PackageInventory
    - scistudio.packages.validation.ContractApplicability
    - scistudio.packages.validation.PackageValidationFinding
    - scistudio.packages.validation.PackageValidationReport
    - scistudio.packages.validation.validate_package
    - scistudio.packages.validation.validate_installed_package
  entry_points: []
  files:
    - src/scistudio/packages/validation/**
    - src/scistudio/cli/package_validator.py
    - tests/packages/test_package_validator.py
    - tests/packages/test_package_validator_reports.py
    - tests/packages/fixtures/package_validator/**
tests:
  - tests/packages/test_package_validator.py
  - tests/packages/test_package_validator_reports.py
  - tests/packages/test_package_validator_cli.py
  - tests/packages/test_package_validator_production_registration.py
acceptance_source: adr
language_source: en
---

# ADR-049 Package Validator Implementation Specification

## 1. Change Summary

This spec turns ADR-049 into an executable implementation plan. The package
validator must validate SciStudio extension packages during development and
before production registration. It must use ADR-049 contract tables as the
machine-readable contract inventory, derive the candidate package's declared
surfaces, apply only relevant contract rows, and return a structured validation
report.

The implementation has two profiles:

- development validation for package authors, CI, scaffolds, and local test
  helpers;
- production validation for install, enable, upgrade, reload, and startup
  package-registration paths.

The production validator must be stricter than current tolerant registry scans:
invalid packages are not registered into live registries when blocking findings
exist.

## 2. User Scenarios & Testing

### User Story 1 - Package Author Validates Before Release (Priority: P1)

As a package author, I can run a validator against a source tree, wheel, or
installed distribution and receive all contract findings in one report.

Why this priority: invalid packages should be caught before they enter a user
environment.

Independent Test: run the validator CLI against valid and invalid fixture
packages and assert deterministic JSON report statuses and findings.

Acceptance Scenarios:

- Given a fixture package with an invalid block, when development validation
  runs, then the report includes the block contract ID, source symbol, severity,
  and repair hint.
- Given a fixture package with only blocks and types, when validation runs, then
  previewer contracts are reported as `not_applicable`, not failures.
- Given a valid package, when development validation runs, then the final status
  is `pass` or `pass_with_warnings` according to ADR-049 severity policy.

### User Story 2 - Production Rejects Invalid Packages (Priority: P1)

As SciStudio runtime, I can validate a package before registration and reject it
without mutating live registries when blocking findings exist.

Why this priority: production registration must not allow a bad extension to
partially poison block, type, previewer, IO capability, or runner registries.

Independent Test: run production validation through a fake installer or package
registration harness and assert live registries are unchanged on failure.

Acceptance Scenarios:

- Given a package with an invalid previewer registry payload, when production
  install validation runs, then registration is rejected and no previewer is
  added to the live registry.
- Given a package whose block ports reference an unknown type, when production
  validation runs, then cross-surface consistency fails and no block is
  registered.
- Given a valid package, when production validation runs, then dry-run registry
  rows are committed atomically to live registries.

### User Story 3 - Agent And CI Drift Checks Stay Mechanical (Priority: P2)

As a maintainer using AI agents, I can check that contract rows, ADR text, and
code evidence stay aligned mechanically.

Why this priority: ADR-049 is only useful if contract drift and omitted surfaces
are visible before implementation or release.

Independent Test: run `scripts/audit/check_package_contract_tables.py` and
assert code evidence mismatches fail while ADR drift remains warning-level.

Acceptance Scenarios:

- Given a contract row whose code evidence no longer matches, when the checker
  runs, then it exits with an error.
- Given a contract row whose code evidence passes but ADR evidence is stale,
  when the checker runs, then it emits a warning.
- Given a contract row without applicability metadata, when the checker runs,
  then it fails the table shape check.

### Edge Cases

- A package declares no SciStudio entry points: report package metadata checks
  and mark extension-surface rows `not_applicable`.
- A package import raises before inventory completes: report `blocker` and do
  not attempt live registration.
- A package depends on optional extras that are unavailable: development may
  report `skipped` only when the optional dependency is declared; production
  must reject if the missing dependency is required for a declared surface.
- Two packages declare conflicting capability IDs: production validation must
  reject the candidate package before live mutation.
- A previewer has frontend assets but no provider: frontend manifest contracts
  apply; provider contracts are `not_applicable`.

## 3. Requirements

### Functional Requirements

- FR-001: The validator MUST accept candidate inputs as source tree path, wheel,
  source distribution, installed distribution name, or installer-provided
  distribution object.
- FR-002: The validator MUST build a `PackageInventory` from distribution
  metadata, entry points, manifests, and package-owned modules.
- FR-003: The validator MUST classify each ADR-049 contract row as `pass`,
  `fail`, `warning`, `skipped`, or `not_applicable`.
- FR-004: The validator MUST use contract row `applicability` metadata to decide
  whether a row applies to the candidate package.
- FR-005: The validator MUST load candidate entry points in an isolated
  validation context before touching live registries.
- FR-006: The validator MUST build dry-run registries for candidate types,
  blocks, previewers, format capabilities, runners, and registry-derived API
  payloads.
- FR-007: The validator MUST validate cross-surface consistency after all
  candidate surfaces are loaded into dry-run registries.
- FR-008: The development profile MUST return all findings in one report and
  include repair hints where possible.
- FR-009: The production profile MUST reject registration when a row with
  production behavior `block` or `error` fails.
- FR-010: Production validation MUST commit rows into live registries only after
  blocking findings are absent.
- FR-011: Production validation MUST leave live registries unchanged when
  validation fails.
- FR-012: The validator MUST emit `PackageValidationReport` JSON compatible with
  ADR-049's report envelope.
- FR-013: The CLI MUST support JSON output and a nonzero exit code when the
  selected profile fails.
- FR-014: The test helper MUST let package tests assert report status,
  findings, and contract IDs without depending on CLI output text.
- FR-015: The implementation MUST keep tolerant startup discovery separate from
  install-facing production validation unless the startup path is registering a
  candidate package.

### Key Entities

| Entity | Description | Required attributes |
|---|---|---|
| `PackageValidationProfile` | Validation profile enum | `development`, `production` |
| `CandidatePackage` | Caller-supplied candidate package identity | source kind, path or distribution name, version, root path, installer context |
| `PackageInventory` | Mechanical package surface inventory | metadata, entry points, declared surfaces, symbols, manifests, examples |
| `ContractApplicability` | Runtime applicability model for one contract row | candidate surfaces, trigger, `not_applicable` result |
| `ContractResult` | Per-contract execution result | contract ID, result, surface, symbol, severity, evidence |
| `PackageValidationFinding` | Human and machine-readable problem | contract ID, severity, surface, source path, symbol, message, repair hint |
| `PackageValidationReport` | Validator output envelope | schema version, package identity, profile, status, decision, inventory, results, findings |
| `DryRunRegistrySet` | Non-live registries used during validation | type, block, previewer, IO capability, runner, API serialization summaries |

## 4. Implementation Plan

### 4.1 Technical Approach

Create `src/scistudio/packages/validation/` as the package validator module. The
module owns candidate discovery, contract table loading, applicability
selection, dry-run registry construction, report generation, and production
registration decisions. Existing registries remain the source of truth for
their domain-specific checks; the validator orchestrates them in isolation and
normalizes failures into `PackageValidationFinding` records.

The validator must not import candidate package code into live registries before
validation succeeds. The first implementation may use an in-process isolated
context for development and a subprocess boundary for production validation.
Production registration receives either a passing report plus dry-run registry
rows or a reject report. It must not receive partially registered live state.

Contract rows are loaded from
`docs/planning/adr-049-package-validator/contracts/*.json` until they graduate
to a runtime package-contract manifest location. Runtime rules must preserve the
same contract IDs so reports are traceable to ADR-049.

### 4.2 Affected Files

| File or glob | Action | Rationale |
|---|---|---|
| `src/scistudio/packages/validation/models.py` | create | Pydantic or dataclass models for candidate, inventory, result, finding, report, profile |
| `src/scistudio/packages/validation/contracts.py` | create | Load ADR-049 contract tables and expose applicability metadata |
| `src/scistudio/packages/validation/inventory.py` | create | Build candidate package inventory from metadata, entry points, manifests, and modules |
| `src/scistudio/packages/validation/engine.py` | create | Execute contract rows, dry-run registries, and cross-surface checks |
| `src/scistudio/packages/validation/registration.py` | create | Atomic production registration handoff and reject behavior |
| `src/scistudio/packages/validation/__init__.py` | create | Public validator API exports |
| `src/scistudio/cli/package_validator.py` | create | CLI wrapper for development and production-style validation |
| `src/scistudio/blocks/registry/**` | modify | Add dry-run or clone support only where existing APIs cannot validate without live mutation |
| `src/scistudio/core/types/registry.py` | modify | Add dry-run support if current registration cannot be isolated by composition |
| `src/scistudio/previewers/**` | modify | Add dry-run support and normalized provider validation hooks |
| `pyproject.toml` | modify | Add CLI script or module entry, if needed |
| `tests/packages/fixtures/package_validator/**` | create | Valid and invalid package fixtures |
| `tests/packages/test_package_validator.py` | create | Core validation engine tests |
| `tests/packages/test_package_validator_reports.py` | create | Report schema and result classification tests |
| `tests/packages/test_package_validator_cli.py` | create | CLI behavior and exit-code tests |
| `tests/packages/test_package_validator_production_registration.py` | create | Atomic production registration tests |
| `docs/block-development/package-validator.md` | create | Author-facing package validation usage docs after runtime exists |

### 4.3 Implementation Sequence

| Task | Depends on | Work | Verification |
|---|---|---|---|
| T-001 | none | Add validation models and report JSON serialization | Unit tests for model round-trip and status derivation |
| T-002 | T-001 | Add contract table loader and applicability normalization | Fixture contract table tests, missing applicability fails |
| T-003 | T-001 | Add candidate package source parsing and inventory builder | Source tree, wheel, installed dist, and no-entry-point fixtures |
| T-004 | T-002, T-003 | Implement per-surface validation dispatch and `not_applicable` classification | Contract result matrix tests |
| T-005 | T-004 | Build dry-run type, block, previewer, IO capability, and runner registries | Valid package fixture registers in dry-run only |
| T-006 | T-005 | Add cross-surface consistency checks | Unknown type, conflicting capability, invalid previewer target fixtures |
| T-007 | T-006 | Add production registration handoff with atomic commit or reject | Live registry unchanged on failure |
| T-008 | T-004 | Add CLI and test helper API | CLI JSON output and exit-code tests |
| T-009 | T-008 | Add author-facing docs and sample command output | Docs link and frontmatter checks |
| T-010 | T-009 | Wire package install/enable/reload call sites to production validator | Integration tests around installer or registration harness |

### 4.4 Verification Plan

- Run `python scripts/audit/check_package_contract_tables.py` before and after
  implementation to keep ADR-049 contract rows aligned.
- Add unit tests for `PackageValidationReport` schema, result classification,
  and status derivation.
- Add fixture package tests for invalid block, invalid type `Meta`, invalid
  previewer payload, invalid frontend manifest, conflicting capability ID, and
  unknown cross-surface target type.
- Add production registration tests proving live registries remain unchanged on
  reject and update atomically on pass.
- Add CLI tests for source tree, installed distribution, JSON output, and exit
  codes.
- Run gate-selected repository checks through `gate_record check`.

### 4.5 Risks And Rollback

- Registry APIs may not currently support cheap dry-run cloning. Mitigation:
  compose temporary registry instances first; only add clone APIs where tests
  prove composition is insufficient.
- Candidate imports may run package code. Mitigation: production validation must
  use an isolation boundary before live mutation.
- Contract tables currently live under `docs/planning`. Mitigation: first
  implementation may load them there; a later cleanup can move generated
  runtime manifests if needed while preserving contract IDs.
- Existing packages may fail stricter production rules. Mitigation: development
  profile reports warnings first; production blocker adoption can be staged by
  contract row profile.
- Rollback is to disable production registration enforcement while keeping the
  CLI/report validator available for development checks.

## 5. Success Criteria

### Measurable Outcomes

- SC-001: A valid fixture package passes development and production validation
  with no blocking findings.
- SC-002: At least five invalid fixture packages fail with the expected contract
  IDs and source symbols.
- SC-003: Previewer contracts are `not_applicable` for a package that declares
  only blocks and types.
- SC-004: Production validation rejects an invalid package and leaves live
  registries unchanged in tests.
- SC-005: The CLI returns JSON output and exits nonzero for a failing production
  profile run.
- SC-006: `PackageValidationReport` JSON includes package identity, profile,
  status, registration decision, inventory, contract results, findings, and
  dry-run registry summaries.
- SC-007: `scripts/audit/check_package_contract_tables.py` still reports zero
  errors for the ADR-049 contract tables.

## 6. Assumptions

- The first implementation can use the ADR-049 planning contract tables as the
  runtime contract source until a generated runtime manifest is introduced.
- The production validator can begin with local process isolation and does not
  need remote sandboxing in the first implementation.
- Existing tolerant discovery paths remain valid for startup resilience when
  they are not making an install-time registration decision.
- Package registration call sites can pass a candidate distribution or source
  descriptor to the validator before live registry mutation.
- Partial registration remains out of scope until a later ADR defines
  quarantine semantics.
