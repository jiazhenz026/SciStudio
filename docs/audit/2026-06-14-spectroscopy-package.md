# Audit report — scistudio-blocks-spectroscopy umbrella (#1661)

Date: 2026-06-14
Integration branch: `claudecode/spectroscopy-package`
Gate ledger: `.workflow/records/1661-spectroscopy-package.json` (feature, manager, Tier-1)
Spec: `docs/specs/spectroscopy-package.md` (001-spectroscopy-package)

## Summary

**pass** — The package implements the full accepted spec (types, two previewers,
26 blocks across 8 groups, ADR-043 IO capability matrix) with a comprehensive
contract + e2e test suite. No `scistudio_blocks_srs` dependency. All local
verification green.

## What landed

Foundation (manager-authored): `Spectrum(Series)` + `SpectralDataset(CompositeData)`
types with typed `Meta`; the shared `_support` data-model helpers (build/read/
derive spectra, DataFrame plumbing, dataset frames, coercion, grid utils);
package wiring + entry points; previewer registration.

Implementation tracks (7 parallel sub-agents, each a dedicated branch merged into
the integration branch):

| Track | Branch | Scope |
| --- | --- | --- |
| pre | claudecode/spectro/pre | 7 preprocessing blocks |
| feat | claudecode/spectro/feat | 5 feature extraction + FitPeak |
| analysis | claudecode/spectro/analysis | 2 reference correction + library matching + unmixing |
| io-spectrum | claudecode/spectro/io-spectrum | LoadSpectrum/SaveSpectrum + spectrum format handlers |
| io-dataset | claudecode/spectro/io-dataset | LoadSpectralDataset/SaveSpectralDataset + dataset format handlers |
| util | claudecode/spectro/util | 5 conversion/transport blocks |
| prev | claudecode/spectro/prev | Spectrum + SpectralDataset previewer providers + viewer.js |

Test tracks (2 parallel test engineers):

| Track | Branch | Scope |
| --- | --- | --- |
| te-contract | claudecode/spectro/te-contract | 12 spec-named contract test files + 4 extended (SC-001..SC-055) + pyproject openpyxl dep |
| te-e2e | claudecode/spectro/te-e2e | tests/e2e/ pseudo-spectra generators + per-block load→block→save workflows + boundary cases + chained pipelines |

## Verification (integration branch)

- `ruff check` + `ruff format --check` on the whole package: clean.
- Package import: 26 blocks register; `get_types() == [Spectrum, SpectralDataset]`;
  `validate_block()` clean for all 26; **scipy not imported on package import**;
  **scistudio_blocks_srs not imported** (SC-007).
- Full test suite: **465 passed, 0 failed, 0 xfail** (foundation + per-track smoke
  + 168 contract + 136 e2e). Both test engineers independently found **no
  implementation bugs**.
- mypy (`--ignore-missing-imports`) clean on changed files.

## Spec compliance highlights

- Exactly the accepted block roster; no unaccepted calibration/clustering/
  PCA/reporting blocks (SC-047).
- Closed method enums per block (baseline polynomial/asls/arpls/airpls;
  smoothing 4; normalize max/minmax; align none/peak_fit/cross_correlation;
  FitPeak gaussian/lorentzian/voigt with `parameters` table, no `fit_diagnostics`
  port; unmixing 3 methods; matching 4 methods).
- ADR-043 capabilities with formal fields; `spectrum_json`/`manifest_json`
  lossless round-trips; vendor formats load-only; no `.zip` capability;
  capability ambiguity fails rather than using registration order.
- Reference correction grid-mismatch + divide-by-zero default errors; unmixing
  wide collision-free coefficient columns; feature tables flat & mergeable.

## Findings

- **P3 (optional):** feature blocks reject a `SpectralDataset` on the `spectra`
  port via `AttributeError` rather than a typed `ValueError`. Contract ("rejects
  directly") holds; a future isinstance guard would give a cleaner message.
- **Deferred (tracked, `# TODO(#1661)`):** SPC and vendor/instrument binary
  formats (`.spa`/`.spg`/`.opus`/`.wdf`/`.wip`/`.sif`/`.spe`/HORIBA LabSpec)
  raise informative `NotImplementedError` pending fixture data / optional SDKs.
  Their ADR-043 capabilities are declared per the accepted matrix; vendor
  formats are load-only.

## Process note

The local gate pre-commit/commit-msg hooks discover the ledger by exact branch
name and verify declared test paths against the committed diff
(`base...HEAD`). Sub-track branches therefore retarget the ledger `branch` field
via the sanctioned `gate_record amend --record --branch ...` (never
`--no-verify`); the integration branch keeps `branch=claudecode/spectroscopy-package`
and re-declares the per-track test surfaces. CI runs the authoritative
`gate_record check --mode ci`.
