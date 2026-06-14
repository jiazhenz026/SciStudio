# ADR-049 Existing Package Validator Sweep

Date: 2026-06-14

Branch: `track/adr-049-package-validator-implementation`

Scope: run the ADR-049 package validator against every existing SciStudio
package in this repository after implementing `scistudio.packages.validation`.

## Commands

Targeted package tests:

```powershell
$env:PYTHONPATH = "src"
$env:PYTEST_ADDOPTS = "--no-cov"
python -m pytest tests/packages --timeout=60
```

Result: `25 passed`.

The targeted tests include subprocess-first production validation,
accepted-package `commit_to(...)`, rejected-package non-mutation, and rollback
when a live registry rejects one row during commit.

Existing package sweep:

```powershell
$env:PYTHONPATH = "src"
python -m scistudio.cli.package_validator . --profile production --json
python -m scistudio.cli.package_validator packages/scistudio-blocks-imaging --profile production --json
python -m scistudio.cli.package_validator packages/scistudio-blocks-srs --profile production --json
python -m scistudio.cli.package_validator packages/scistudio-blocks-lcms --profile production --json
```

## Results

| Package | Version | Exit | Status | Decision | Findings | Dry-run registries |
|---|---:|---:|---|---|---:|---|
| `scistudio` | `0.2.1` | 0 | `pass` | `accept` | 0 | blocks 14, types 7, previewers 0, format capabilities 62, runners 3 |
| `scistudio-blocks-imaging` | `0.1.0` | 0 | `pass` | `accept` | 0 | blocks 49, types 11, previewers 2, format capabilities 13 |
| `scistudio-blocks-srs` | `0.1.0.dev0` | 0 | `pass` | `accept` | 0 | blocks 9, types 8, previewers 0, format capabilities 0 |
| `scistudio-blocks-lcms` | `0.1.0.dev0` | 0 | `pass` | `accept` | 0 | blocks 9, types 11, previewers 0, format capabilities 16 |

## Notes

- The first sweep surfaced an SRS import failure for
  `scistudio_blocks_imaging`. SRS declares
  `scistudio-blocks-imaging>=0.1.0.dev0` in `project.dependencies`, so source
  tree validation now exposes declared monorepo sibling package `src` paths in
  the validation import context. Undeclared sibling packages remain hidden.
- The validator did not require any existing package to declare surfaces it does
  not expose. Missing previewer surfaces for SRS and LCMS are classified through
  contract applicability rather than as findings.
- No live application registry is mutated by the sweep; all counts above come
  from dry-run registries.

Verdict: PASS. Existing in-repository SciStudio packages validate successfully
under the production profile with zero findings.
