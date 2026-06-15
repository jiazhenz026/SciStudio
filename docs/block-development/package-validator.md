---
doc_type: block-development
title: "Package Validator"
status: living
owner: "@jiazhenz026"
last_updated: 2026-06-15
governed_by:
  - ADR-049
summary: "How package authors and install-time registration code use the ADR-049 package validator for development diagnostics and production accept/reject decisions."
---

# Package Validator

The ADR-049 package validator checks one SciStudio extension package at a time.
It loads the package's declared SciStudio entry points in a validation context,
builds dry-run registries, applies the ADR-049 contract table rows that are
relevant to the package's surfaces, and emits a structured
`PackageValidationReport`.

Use it before publishing a package and before production registration commits
rows into live registries.

## CLI

Validate a source tree:

```powershell
scistudio package-validator packages/scistudio-blocks-imaging --profile development --json
```

The module form is equivalent and is useful inside a source checkout:

```powershell
$env:PYTHONPATH = "src"
python -m scistudio.cli.package_validator packages/scistudio-blocks-imaging --profile production --json
```

The candidate argument may be a source tree, an installed distribution name, a
wheel, or a source distribution. Wheel and source-distribution inputs are
inspected for package metadata and SciStudio entry points before validation; a
bad archive is returned as a structured reject report instead of being accepted
as metadata-only input.

Profiles:

| Profile | Use | Failure behavior |
|---|---|---|
| `development` | Authoring, package CI, scaffold tests | Reports all findings in one run. |
| `production` | Install, enable, upgrade, reload, or startup registration checks | Exits nonzero and rejects registration when blocking findings exist. |

CLI exit codes are intentionally simple: `0` means the selected profile passed;
`1` means the report status is `fail`.

## Python API

```python
from scistudio.packages.validation import PackageValidationProfile, validate_package

report = validate_package(
    "packages/scistudio-blocks-imaging",
    profile=PackageValidationProfile.PRODUCTION,
)
assert report.registration_decision.value == "accept"
```

For install-facing code, use the production handoff helper:

```python
from scistudio.packages.validation.registration import validate_for_registration

plan = validate_for_registration("packages/scistudio-blocks-imaging")
if not plan.accepted:
    raise RuntimeError(plan.report.to_dict()["findings"])
plan.commit_to(block_registry=block_registry, type_registry=type_registry)
```

`validate_for_registration()` returns a plan/report boundary. Caller-owned
installer code commits live registry rows by calling `plan.commit_to(...)` only
after validation passes. The helper runs the production report in a subprocess
before returning an accepted plan; candidate package modules are not imported
into the caller's process while the production decision is being made. A reject
report returns `False` from `commit_to(...)` and leaves live registries
unchanged. If a live registry rejects one row during commit, previously written
rows from the same call are rolled back.

Installers may pass existing live registries to `validate_for_registration(...)`
so the report can reject candidate packages that conflict with installed type,
previewer, runner, or IO capability IDs before a commit is attempted:

```python
plan = validate_for_registration(
    "packages/scistudio-blocks-imaging",
    block_registry=block_registry,
    type_registry=type_registry,
    previewer_registry=previewer_registry,
)
```

## Report Shape

Every report uses schema version `adr049.package_validation_report.v1` and
contains:

- package identity: `name`, `version`, `source`;
- selected profile and final `status`;
- `registration_decision`: `accept` or `reject`;
- package inventory: entry points, declared surfaces, symbols, and capability
  IDs discovered during validation;
- one `contract_results` entry for every loaded ADR-049 contract row;
- repairable `findings`, each with a contract ID, severity, surface, message,
  symbol when known, and repair hint;
- dry-run registry counts for blocks, types, previewers, format capabilities,
  runners, and API payloads.

Absent surfaces are reported as `not_applicable`. For example, a package that
declares only blocks and types does not fail previewer contracts; those rows are
classified as not applicable. A row whose surface applies but whose runtime
validator did not execute is reported as `skipped` with evidence instead of
being reported as `pass`. Package authors should treat skipped applicable rows
as incomplete validation coverage, not as proof that the contract passed.

Unknown `scistudio.*` entry-point groups are structured findings. Misspelled or
future entry-point groups must not be silently ignored.

## Source Tree Dependencies

When validating packages inside the SciStudio monorepo, the validator exposes
only the candidate package and sibling `packages/*/src` directories that are
declared in the candidate package's `project.dependencies`. This keeps local
source-tree validation faithful to package metadata: a package may use a sibling
source tree only if it declares the dependency in `pyproject.toml`.

Block ports may reference DataObject types owned by declared dependency
packages. DataObject types defined inside the candidate package itself must be
returned by its `scistudio.types` entry point before candidate block ports or
previewers may target them.

## Contract Evidence

The validator loads contract rows from:

```text
docs/planning/adr-049-package-validator/contracts/*.json
```

Run the contract table checker when changing package-facing contracts:

```powershell
python scripts/audit/check_package_contract_tables.py
```

The expected ADR-049 baseline is zero errors. The current ADR drift warnings are
documented in ADR-049 and remain warnings until the governing ADRs are updated
or the implementation intentionally tightens those contracts.
