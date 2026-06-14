# Spectroscopy Package Audit - Codex-Labeled Implementation

Date: 2026-06-14

Target: PR #1663, branch `codex/spectroscopy-package-20260614`,
head `ebf0f3ba5a443c5b9e5812f4a6cb0ec29d82e17f`

Spec: `docs/specs/spectroscopy-package.md` (`001-spectroscopy-package`)

Checker evidence: PR #1665 merged into a throwaway worktree with
`git merge --no-commit --no-ff origin/track/adr-049-package-validator-implementation`.
The merge had no conflicts.

## Verdict

Pass with fixes required. The implementation has the correct public package
shape, exact block roster, passing package tests, green CI, and passes the
ADR-049 package validator. It does not fully satisfy the spectroscopy spec's
previewer and IO-format fidelity contracts.

## Findings

### P1 - Previewer implementation is too shallow for the accepted previewer contract

The spec requires exact `Spectrum` and `SpectralDataset` previewers with real
interactive plotting, bounded reads, honest sampling/truncation metadata, data
table/filter/group controls, linked selection, diagnostics, and export/save
resources (FR-017..FR-030, SC-004..SC-006).

Evidence:

- `packages/scistudio-blocks-spectroscopy/src/scistudio_blocks_spectroscopy/previewers/__init__.py:21`
  builds a static `Spectrum` payload with metadata and labels only; it does
  not read target data or produce visible points/resources.
- `packages/scistudio-blocks-spectroscopy/src/scistudio_blocks_spectroscopy/previewers/__init__.py:42`
  builds a static `SpectralDataset` slot inventory; it does not read index or
  spectra slots, paginate rows, compute diagnostics, or expose grouped plot
  data.
- The previewer specs have no `frontend_manifest` or package frontend asset.
- `packages/scistudio-blocks-spectroscopy/tests/test_previewer_registration.py`
  verifies registration, routing, and static envelope shape only.

Impact: core registration is present, but the user-visible previewer behavior
required by the spec is mostly unimplemented.

### P1 - SPC and vendor/instrument capabilities are semantically misleading

The implementation declares ADR-043 capabilities for SPC and vendor/native
instrument formats, but several handlers route those formats through generic
text or pseudo-dataset paths instead of implementing the declared format or
failing honestly.

Evidence:

- `blocks/utilities.py:812` maps `_load_spc()` to `_load_vendor_text()`.
- `blocks/utilities.py:815..831` route Thermo OMNIC, Bruker OPUS, HORIBA,
  Renishaw, Andor, and Princeton loaders through the same text reader.
- `blocks/utilities.py:932` saves `.spc` by calling `_save_delimited_text()`.
- `blocks/utilities.py:1017..1039` route SPC and multi-spectrum vendor dataset
  loaders through `_load_pseudo_dataset()`.
- `blocks/utilities.py:1130` saves dataset `.spc` by writing a merged CSV-like
  table.

Impact: the capability matrix reports typed metadata fidelity and round-trip
groups for formats whose handlers are not format-correct. This is worse than a
tracked `NotImplementedError` because workflows may accept files as if the
format support is real.

### P2 - Test suite is broad but shallower than the claimed user stories

Local package tests pass, and the suite includes useful contract matrices.
However, the suite is materially smaller and less behavioral than the competing
implementation:

- 17 test files, 111 test functions, 199 collected tests.
- No real preview `PreviewDataAccess` tests for point reads, dataset slot reads,
  export resources, or diagnostics.
- Format tests mostly assert declared capabilities and handler existence; they
  do not catch the SPC/vendor text fallback issue above.

## Positive Evidence

- Public surface is correctly scoped: two types (`Spectrum`, `SpectralDataset`)
  and exactly the 26 accepted blocks.
- Package entry points exist for `scistudio.blocks`, `scistudio.types`, and
  `scistudio.previewers`.
- Accepted method enums and block output port names are covered by contract
  tests, including `FitPeak.parameters` and no `fit_diagnostics` output.
- Package imports do not require `scistudio_blocks_srs`.
- Local package tests passed:

```powershell
$env:PYTHONPATH = "src"
python -m pytest packages/scistudio-blocks-spectroscopy/tests -q --no-cov --timeout=60
```

Result: exit 0; 199 tests collected.

- PR #1663 CI was green at review time across lint, type check, architecture
  tests, full audit, Python tests, import contracts, frontend, wheel smoke,
  workflow gate, CodeQL, and deferral scan.

## Recommendation

Do not merge PR #1663 as the winning implementation without fixes. Required
fixes are:

1. Implement real preview providers and frontend asset registration, or reduce
   previewer claims until they match implemented behavior.
2. Replace fake SPC/vendor handlers with real format implementations or explicit
   tracked `NotImplementedError` boundaries, and ensure the capability
   `metadata_fidelity` values match tested behavior.
