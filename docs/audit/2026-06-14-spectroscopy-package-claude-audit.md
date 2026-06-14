# Spectroscopy Package Audit - Claude-Labeled Implementation

Date: 2026-06-14

Target: PR #1666, branch `claudecode/spectroscopy-package`,
head `3a9a145e40bffb144eed7647489aa5e4e8569549`

Spec: `docs/specs/spectroscopy-package.md` (`001-spectroscopy-package`)

Checker evidence: PR #1665 merged into a throwaway worktree with
`git merge --no-commit --no-ff origin/track/adr-049-package-validator-implementation`.
The merge had no conflicts.

## Verdict

Pass with minor gaps. This implementation is the stronger candidate: it has the
same correct package roster as PR #1663, deeper previewer implementation,
clearer IO boundaries, and a substantially broader test suite.

## Findings

### P2 - SPC and vendor/instrument binary handlers remain incomplete

The package declares the accepted ADR-043 capability matrix, including SPC and
vendor/native instrument formats. SPC and proprietary vendor formats are not
fully implemented; handlers raise `NotImplementedError` with tracked
`TODO(#1661)` comments.

Evidence:

- `blocks/io_handlers/spectrum_formats.py:395` and `:408` define SPC spectrum
  load/save as deferred.
- `blocks/io_handlers/spectrum_formats.py:429..469` mark single-spectrum
  vendor/native loaders as deferred.
- `blocks/io_handlers/dataset_formats.py:267` and `:280` define SPC dataset
  load/save as deferred.
- `blocks/io_handlers/dataset_formats.py:305..356` mark multi-spectrum
  vendor/native loaders as deferred.

Impact: this is an implementation completeness gap against FR-132..FR-143 and
SC-050..SC-052. It is less risky than silently parsing these formats as text,
because unsupported paths fail explicitly and cite the tracking issue.

### P2 - Local xlsx verification was skipped in the current environment

The local test run skipped six xlsx tests because `openpyxl` was not installed:

- `tests/e2e/test_e2e_io.py` x2
- `tests/test_io_dataset_smoke.py`
- `tests/test_io_spectrum_smoke.py`
- `tests/test_spectral_dataset_io.py`
- `tests/test_spectrum_io.py`

The package declares `openpyxl>=3.1` in `pyproject.toml`, so this is an
environment gap in the audit worktree rather than a missing package dependency.
It still means this local benchmark did not execute the xlsx behavior paths.

### P3 - Minor stale implementation comment

`blocks/utilities.py:13` still says executable bodies are skeleton stubs. The
file now contains real utility and IO dispatch behavior. This does not affect
runtime behavior, but it is stale documentation inside source.

## Positive Evidence

- Public surface is correctly scoped: two types (`Spectrum`, `SpectralDataset`)
  and exactly the 26 accepted blocks.
- Package entry points exist for `scistudio.blocks`, `scistudio.types`, and
  `scistudio.previewers`.
- Previewers are materially implemented:
  - `previewers/__init__.py:40` creates frontend manifests.
  - `previewers/__init__.py:64` and `:75` attach frontend manifests to both
    previewer specs.
  - `previewers/providers.py:143` implements the spectrum provider.
  - `previewers/providers.py:469` implements the dataset provider.
  - `previewers/assets/viewer.js` provides package-owned frontend behavior.
- IO code separates generic text/native JSON/xlsx/JCAMP handlers from deferred
  binary/vendor handlers under `blocks/io_handlers/`.
- Package imports do not require `scistudio_blocks_srs`.
- Local package tests passed with only the xlsx environment skips:

```powershell
$env:PYTHONPATH = "src"
python -m pytest packages/scistudio-blocks-spectroscopy/tests -q --no-cov --timeout=60 -rs
```

Result: `461 passed, 6 skipped in 2.30s`.

- PR #1666 CI was green at review time across lint, type check, architecture
  tests, full audit, Python tests, import contracts, frontend, wheel smoke,
  workflow gate, CodeQL, and deferral scan.

## Recommendation

Prefer PR #1666 as the base implementation. Before final release, either
implement SPC/vendor handlers with fixtures and optional dependencies or adjust
the capability/fidelity contract so those paths are explicitly unavailable
until follow-up work lands.
