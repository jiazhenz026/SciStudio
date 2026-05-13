# Microplastics golden reference outputs

This directory holds the **reference numerical outputs** that the SciEasy
embedded coding agent's workflow run must reproduce within tolerance.

The files were captured by executing the source notebook end-to-end on
the dispatcher's machine. The agent under test does **not** read these
files — they are consumed only by the test (T-ECA-505), which compares
the agent-produced run outputs to each file via
[`tests/e2e/microplastics/_compare.py`](../_compare.py).

## Source

- Notebook: `C:\Users\jiazh\Box\Jiazhen Zhang\04 Data\microplastics\processed\scripts\sample.ipynb`
- Executor: `papermill` (deterministic re-run of the notebook on the
  unchanged TIFF inputs under
  `C:\Users\jiazh\Box\Jiazhen Zhang\04 Data\microplastics\processed\tiff`).
- Capture date: 2026-05-12.

To re-capture from a fresh ipynb run, use the throwaway helper at
`.workflow/aborted/build_golden.py` (not committed; lives in the dispatcher's
local `.workflow/aborted/` tree). The helper rounds float columns to
6 significant figures while leaving non-numeric columns byte-identical.

## File inventory

Each `*_spectra.csv` is produced by **cell 5** of the source notebook
(`process_image` invocations) and has the shape:

```
Raman_Shift, ROI1, ROI2, ROI3, ...
```

where `Raman_Shift` is the wavenumber axis (50 evenly spaced points
between 2800 and 3100 cm⁻¹) and each `ROI<k>` column is the lock-in
voltage (in µV) averaged over the masked pixels of the k-th
particle in that image.

| File | Source cell | Particles (ROIs) | Tolerance fields |
|------|-------------|------------------|------------------|
| `50nm_2800-3100-100_spectra.csv` | cell 5 — `process_image` | 33 | all float |
| `50nm_2800-3100-100_0001_spectra.csv` | cell 5 — `process_image` | 32 | all float |
| `200nm_2800-3100-100_spectra.csv` | cell 5 — `process_image` | 142 | all float |
| `200nm_2800-3100-100_0001_spectra.csv` | cell 5 — `process_image` | 12 | all float |
| `500nm_2800-3100-100_spectra.csv` | cell 5 — `process_image` | 35 | all float |
| `500nm_2800-3100-100_0002_spectra.csv` | cell 5 — `process_image` | 29 | all float |
| `1000nm_2800-3100-100_0003_spectra.csv` | cell 5 — `process_image` | 3 | all float |
| `1000nm_2800-3100-100_0004_spectra.csv` | cell 5 — `process_image` | 5 | all float |
| `summary_prism_xy.csv` | **cell 6** — Prism XY aggregation | (joined) | all float |

> Note: `200nm_2800-3100-100_0002` is *not* in the source TIFF directory.
> The `200nm_2800-3100-100` image excluded by cell 6's `DROP` set
> (`{"200nm_2800-3100-100-100"}`) is the verbatim Box-side file; we keep
> all images in the per-image golden CSVs so the agent's workflow can be
> compared independently of its filter decisions, then check that the
> agent's `summary_prism_xy.csv` applies the same drop rule.

## Comparator contract

All numerical comparisons go through `assert_numerically_equal` in
`../_compare.py`. The default tolerances are:

- `rtol = 1e-3` — 0.1 % relative
- `atol = 1e-6` — 1 µV-equivalent absolute floor (well below the lock-in
  noise floor in the source data)

### Per-field rationale

- **`Raman_Shift` column**: produced by `np.linspace(2800, 3100, 50)`. The
  agent should reproduce this exactly when it derives the axis from the
  same `RAMAN_START`/`RAMAN_STOP` constants, but the comparator uses
  tolerance to absorb harmless dtype differences (`float32` vs `float64`).
- **`ROI<k>` columns**: computed as `stack_uv[c, mask].mean()` for each
  channel `c`. The dominant uncertainty is the order of pixels iterated
  by `regionprops` — this is deterministic on the same scikit-image
  version, but `rtol=1e-3` gives the agent room to use any equivalent
  averaging (e.g. masked `np.mean` vs flat-indexed mean).
- **`summary_prism_xy.csv` header rows**: the first two rows are layout
  metadata (group labels + per-ROI column names). The comparator treats
  them as string columns and requires exact equality.
- **`summary_prism_xy.csv` data rows**: float-tolerance per the defaults.

### What's *not* in golden

- ROI `.zip` files. These contain binary ImageJ ROI polygons whose vertex
  order depends on `find_contours` internals; not robust enough to
  golden-check. T-ECA-505 should treat ROI zips as *opaque* artefacts
  (presence/absence + file count, not byte-equality).
- The pandas `summary` DataFrame printed by cell 5 (image-level stats:
  thresholds, particle counts). T-ECA-505 can re-derive these from the
  per-image CSV column counts if needed.

## Re-capture procedure

To regenerate the golden files (e.g., after a TIFF batch is added):

```powershell
# from repo root
pip install papermill nbformat ipykernel
papermill "<path-to-sample.ipynb>" .workflow/aborted/papermill_out/executed.ipynb
python .workflow/aborted/build_golden.py
```

Commit the resulting `golden/*.csv` files in a dedicated PR with the
re-capture notebook execution logs.
