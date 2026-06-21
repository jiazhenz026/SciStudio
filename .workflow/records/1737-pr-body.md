## Summary

Pre-alpha automated test suite for **data IO** and **builtin block**
behavior (owner-directed `guided` session). This PR carries the
**self-contained automated tests**; the curated sample data, golden
answers, generation scripts, and the owner-facing manual checklist live
in the separate test project (`~/Desktop/scistudio-tests`,
`alpha-test-suite/`).

Closes #1737.

## What's in this PR (tests only)

- `tests/blocks/io/test_io_coverage_matrix.py` — core IO load+save
  matrix for Array/DataFrame/Series/Text/CompositeData over every
  `load_ext × save_ext`, plus 10-item collection round-trips and N-D
  Array coverage. **232 pass / 30 xfail** (xfail = engine findings).
  Runs in CI (core deps only, scoped `LoadData`/`SaveData` registry).
- `packages/scistudio-blocks-imaging/tests/test_io_coverage_image.py` —
  Image format matrix (tif/png/jpg/zarr) + collection. **42 pass.**
- `packages/scistudio-blocks-spectroscopy/tests/test_io_coverage_spectroscopy.py`
  — Spectrum + SpectralDataset matrix + collection. **69 pass.**
- `tests/blocks/code/test_alpha_codeblock_python.py` /
  `test_alpha_codeblock_r.py` — real file-exchange CodeBlock runs
  (Python `out=in*2+1`; R adds `scaled=value*10`, `requires Rscript`).

> Package tests (`packages/*/tests`) are not collected by the repo's
> `testpaths = ["tests"]`, so they run locally / for the owner, not in
> the main CI job. They need `tifffile`, `ome-types`, `scikit-image`,
> `imageio` in the env.

## Findings surfaced while building the suite

Documented in the test project's `alpha-test-suite/FINDINGS.md`; covered
by `xfail` here so they stay visible without failing CI:

| ID | What |
|---|---|
| FIND-A | `CompositeData` `.json` saver writes slot key `file`, loader reads `path` → core composite save/load broken |
| FIND-B | `DataFrame`/`Series` pickle saves the Arrow Table; loader expects the wrapped object |
| FIND-C | Full-registry extension ambiguity (`.zarr`→Image, `.json`→SpectralDataset, ambiguous `.csv`) |
| FIND-D | `Array` `.zarr` reload restores data but drops `shape`/`axes` metadata |
| FIND-E | `Render Movie` uses `tifffile` `fps=` kwarg removed in 2026 |
| FIND-F | Python CodeBlock backend injects no `SCISTUDIO_*_DIR` env; scripts can't locate exchange dirs (R/shell do) |

These are **test findings, not fixes** — this PR does not touch engine
code. Follow-up issues can be filed per finding.

## Out of scope (per owner)

LCMS + SRS packages (future refactor), vendor binaries
(.czi/.lif/.nd2/.oib/.oir/.raw/.d/.mzml), legacy `.xls`, ProcessBlock +
AIBlock manual cases, Subworkflow.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
