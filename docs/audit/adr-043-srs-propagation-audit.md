---
title: ADR-043 Phase B2 — SRS ProcessBlock OME-Metadata Propagation Audit
adr: ADR-043
spec: docs/specs/adr-043-package-migration.md
phase: B2
issue: 1296
branch: feat/issue-1296/adr043-b2-srs-propagation
author: implementer agent
date: 2026-05-20
status: committed
---

# ADR-043 Phase B2 — SRS ProcessBlock OME-Metadata Propagation Audit

## 1. Scope

This audit covers every `ProcessBlock` in `packages/scistudio-blocks-srs/` and
classifies its OME-metadata propagation behavior against the propagation
contract codified in
[`docs/specs/adr-043-package-migration.md`](../specs/adr-043-package-migration.md)
FR-009 (Modes A / B / C), as required by FR-011.

Phase A2 added `ome: OME | None = None` to `Image.Meta` and `Label.Meta` in the
imaging plugin. Because `SRSImage.Meta` inherits from `Image.Meta` via
`class Meta(Image.Meta)` in
[`packages/scistudio-blocks-srs/src/scistudio_blocks_srs/types.py`](../../packages/scistudio-blocks-srs/src/scistudio_blocks_srs/types.py#L47),
`SRSImage.Meta` automatically gained the `ome` field with no edit to `types.py`
required.

This Phase B2 work then audited each SRS ProcessBlock to confirm that the new
`ome` field flows through the SRS pipeline correctly per the propagation
contract.

## 2. Propagation Contract Recap (FR-009)

- **Mode A — shape-preserving same-type derivation.** Block constructs output
  with `OutputClass(..., meta=item.meta, ...)`. `ome` propagates transparently
  via whole-Meta pass-through. **No code change required.**

- **Mode B — shape-changing same-type derivation.** Block constructs output via
  a helper transform that rewrites `ome.images[0].pixels.*` to match the new
  geometry. **Not used in the SRS package** (no SRS block resizes / projects).

- **Mode C — cross-type derivation.** Block constructs the output Meta
  field-by-field. The block author chooses which fields to propagate. Per
  FR-009: **if the output preserves the source's spatial coordinate system,
  `ome` MUST be propagated; if the output drops spatial / spectral structure,
  `meta=None` (or a Meta without `ome`) is permitted.**

## 3. Per-Block Classification

| Block | File | Mode | Propagation site | Required action | Result |
|---|---|---|---|---|---|
| `SRSCalibrate` | [preprocess/srs_calibrate.py](../../packages/scistudio-blocks-srs/src/scistudio_blocks_srs/preprocess/srs_calibrate.py#L95) | Mode C (model_dump + override) | `SRSImage.Meta(**item.meta.model_dump(), …overrides)` | None — `model_dump()` already includes `ome` | verified by test |
| `SRSBaseline` | [preprocess/srs_baseline.py](../../packages/scistudio-blocks-srs/src/scistudio_blocks_srs/preprocess/srs_baseline.py#L93) | Mode A | `SRSImage(..., meta=item.meta, ...)` | None — transparent | verified by test |
| `SRSSpectralDenoise` | [preprocess/srs_spectral_denoise.py](../../packages/scistudio-blocks-srs/src/scistudio_blocks_srs/preprocess/srs_spectral_denoise.py#L96) | Mode A | `SRSImage(..., meta=item.meta, ...)` | None — transparent | verified by test |
| `SRSKMeansCluster` | [component_analysis/srs_kmeans.py](../../packages/scistudio-blocks-srs/src/scistudio_blocks_srs/component_analysis/srs_kmeans.py#L121) | Mode C (cross-type → `Label`) | `Label.Meta(source_file=…, n_objects=…, ome=…)` | **Add `ome=getattr(item.meta, "ome", None)` — DONE** | verified by test |
| `SRSPCA` | [component_analysis/srs_pca.py](../../packages/scistudio-blocks-srs/src/scistudio_blocks_srs/component_analysis/srs_pca.py#L144) | Mode C — legitimate drop | `Image(..., meta=None, ...)` for per-PC score maps | Document deliberate `meta=None` | comment added; verified by test |
| `SRSICA` | [component_analysis/srs_ica.py](../../packages/scistudio-blocks-srs/src/scistudio_blocks_srs/component_analysis/srs_ica.py#L107) | Mode C — legitimate drop (shares `_scores_to_image_collection`) | Reuses `SRSPCA._scores_to_image_collection` | Same rationale as `SRSPCA` (covered by shared helper) | comment in shared helper covers both |
| `SRSUnmix` | [component_analysis/srs_unmix.py](../../packages/scistudio-blocks-srs/src/scistudio_blocks_srs/component_analysis/srs_unmix.py#L206) | Mode C — legitimate drop | `Image(..., meta=None, ...)` for per-endmember abundance maps | Document deliberate `meta=None` | comment added |
| `SRSVCA` | [component_analysis/srs_vca.py](../../packages/scistudio-blocks-srs/src/scistudio_blocks_srs/component_analysis/srs_vca.py#L143) | Mode C — DataFrame output | `DataFrame(columns=…, row_count=…)` — no Meta object on DataFrame | None — output is tabular; no Meta to populate | n/a — DataFrame has no `ome` carrier |
| `ExtractSpectrum` | [spectral_extraction/extract_spectrum.py](../../packages/scistudio-blocks-srs/src/scistudio_blocks_srs/spectral_extraction/extract_spectrum.py#L118) | Mode C — DataFrame output | `DataFrame(columns=…, row_count=…)` — wide-format per-ROI spectra | None — output is tabular; no Meta to populate | n/a — DataFrame has no `ome` carrier |

## 4. Mode A — Verifications (No-Op Fixes)

### 4.1 `SRSBaseline`

[`packages/scistudio-blocks-srs/src/scistudio_blocks_srs/preprocess/srs_baseline.py:93`](../../packages/scistudio-blocks-srs/src/scistudio_blocks_srs/preprocess/srs_baseline.py#L93)
builds the output as:

```python
out = SRSImage(
    axes=list(item.axes),
    shape=out_data.shape,
    dtype=out_data.dtype,
    chunk_shape=item.chunk_shape,
    framework=item.framework.derive(),
    meta=item.meta,             # <-- Mode A transparent pass-through
    user=dict(item.user),
    storage_ref=None,
)
```

Since `item.meta` is passed through as-is, the new `ome` field on
`SRSImage.Meta` propagates automatically. No code change required.
Verified by `test_srs_baseline_mode_a_preserves_ome`.

### 4.2 `SRSSpectralDenoise`

[`packages/scistudio-blocks-srs/src/scistudio_blocks_srs/preprocess/srs_spectral_denoise.py:96`](../../packages/scistudio-blocks-srs/src/scistudio_blocks_srs/preprocess/srs_spectral_denoise.py#L96)
uses the same `meta=item.meta` pattern. Same conclusion as `SRSBaseline`.
Verified by `test_srs_spectral_denoise_mode_a_preserves_ome`.

## 5. Mode C — `model_dump` + override: `SRSCalibrate`

[`packages/scistudio-blocks-srs/src/scistudio_blocks_srs/preprocess/srs_calibrate.py:95`](../../packages/scistudio-blocks-srs/src/scistudio_blocks_srs/preprocess/srs_calibrate.py#L95)
rebuilds the SRSImage.Meta from the source's dumped Meta plus digitizer
overrides:

```python
old_meta = item.meta.model_dump() if item.meta is not None else {}
new_meta = SRSImage.Meta(
    **old_meta,
    wavenumbers_cm1=list(wavenumbers_cm1) if wavenumbers_cm1 is not None else None,
    digitizer_bit_depth=bit_depth,
    digitizer_voltage_range=voltage_range,
    digitizer_offset=offset,
    digitizer_scale=scale,
)
```

Pydantic v2 `model_dump()` returns every field on the source Meta — including
the new `ome` field — so the kwarg expansion carries it through transparently.
**No code change required**, but the contract is fragile against future
refactors; the test `test_srs_calibrate_mode_c_model_dump_carries_ome` pins
this behavior so a future refactor that switches to explicit field selection
will trigger an immediate failure.

## 6. Mode C Fix — `SRSKMeansCluster` (Image → Label, shape-preserving)

### 6.1 Before

The cluster-assignment `Label` output was constructed without the source's
OME metadata:

```python
label_obj = Label(
    slots={"raster": raster},
    framework=item.framework.derive(),
    meta=Label.Meta(
        source_file=getattr(item.meta, "source_file", None) if item.meta is not None else None,
        n_objects=n_clusters,
    ),
    user=dict(item.user),
)
```

### 6.2 After

K-means cluster assignments are shape-aligned with the source's `y/x` spatial
layout — every pixel in the source maps to exactly one cluster ID. Per FR-009
Mode C, **shape-preserving cross-type derivations MUST propagate `ome`**.

The fix at
[`packages/scistudio-blocks-srs/src/scistudio_blocks_srs/component_analysis/srs_kmeans.py:118-130`](../../packages/scistudio-blocks-srs/src/scistudio_blocks_srs/component_analysis/srs_kmeans.py#L118):

```python
# ADR-043 FR-009 Mode C — Image-domain → Label is a shape-preserving
# cross-type derivation (cluster assignments share the source's y/x
# spatial layout), so the source SRSImage's OME metadata MUST be
# propagated onto the Label output per spec FR-011.
label_obj = Label(
    slots={"raster": raster},
    framework=item.framework.derive(),
    meta=Label.Meta(
        source_file=getattr(item.meta, "source_file", None) if item.meta is not None else None,
        n_objects=n_clusters,
        ome=getattr(item.meta, "ome", None) if item.meta is not None else None,
    ),
    user=dict(item.user),
)
```

Defensive `getattr(..., "ome", None)` keeps the code working if `item.meta`
is `None` or carries a Meta variant without `ome` (e.g. a future plugin
subclass). Verified by `test_srs_kmeans_mode_c_label_carries_ome`,
`test_srs_kmeans_handles_none_meta_source`, and
`test_srs_kmeans_handles_meta_without_ome`.

## 7. Mode C Legitimate Drop — Documented `meta=None` Cases

### 7.1 `SRSPCA` per-PC score maps

[`packages/scistudio-blocks-srs/src/scistudio_blocks_srs/component_analysis/srs_pca.py:128-150`](../../packages/scistudio-blocks-srs/src/scistudio_blocks_srs/component_analysis/srs_pca.py#L128):
each output `Image` is a 2D `y/x` score map for one principal component. The
source spectral (`lambda`) axis is collapsed into a derived `pc_id` index — the
OME description (channel ordering, spectral wavelengths, pixel-axis
descriptions) **no longer corresponds** to the score-map content even though
`y/x` pixel dimensions match. Per FR-009 Mode C:

> When the output drops spatial structure entirely … `meta=None` or a
> domain-specific Meta without `ome` is permitted.

Reasoning: an OME structure that says "size_c=1, dimension_order=XYCZT,
channel=<spectrum-name>" applied to a PC-score map would be **actively
misleading** — downstream consumers would assume the map represents a single
physical channel rather than a derived projection. Dropping `meta` is the
correct behavior. A comment was added at
[`srs_pca.py:128-136`](../../packages/scistudio-blocks-srs/src/scistudio_blocks_srs/component_analysis/srs_pca.py#L128)
to make the deliberate intent explicit.

Note: `SRSICA` reuses the same `_scores_to_image_collection` helper, so the
identical reasoning and documentation apply to FastICA component maps.

Verified by `test_srs_pca_mode_c_legitimate_meta_drop`.

### 7.2 `SRSUnmix` per-endmember abundance maps

[`packages/scistudio-blocks-srs/src/scistudio_blocks_srs/component_analysis/srs_unmix.py:197-214`](../../packages/scistudio-blocks-srs/src/scistudio_blocks_srs/component_analysis/srs_unmix.py#L197):
each abundance map is a 2D `y/x` map of per-endmember abundance. Same
reasoning as `SRSPCA`: the spectral axis is replaced by an `endmember_id`
index; OME channel / spectral metadata does not apply. A comment was added at
[`srs_unmix.py:197-203`](../../packages/scistudio-blocks-srs/src/scistudio_blocks_srs/component_analysis/srs_unmix.py#L197)
to make the deliberate intent explicit.

### 7.3 `SRSVCA` and `ExtractSpectrum`

Both emit `DataFrame` outputs (endmember spectra; wide-format per-ROI spectra).
`DataFrame` is a tabular type with no `Meta.ome` carrier and no spatial
coordinate system. There is no propagation requirement to discuss for these
two blocks.

## 8. Tests

A new test module at
[`packages/scistudio-blocks-srs/tests/test_processblock_meta_propagation.py`](../../packages/scistudio-blocks-srs/tests/test_processblock_meta_propagation.py)
covers:

| Test | Mode | Assertion |
|---|---|---|
| `test_srs_baseline_mode_a_preserves_ome` | A | `out.meta.ome is ome` (identity) |
| `test_srs_spectral_denoise_mode_a_preserves_ome` | A | `out.meta.ome is ome` (identity) |
| `test_srs_calibrate_mode_c_model_dump_carries_ome` | C (model_dump) | `out.meta.ome.model_dump() == ome.model_dump()` |
| `test_srs_kmeans_mode_c_label_carries_ome` | C (fix) | `label.meta.ome is ome` |
| `test_srs_pca_mode_c_legitimate_meta_drop` | C (drop) | every PC map has `meta is None` |
| `test_srs_kmeans_handles_none_meta_source` | C edge | `meta=None` source → `label.meta.ome is None` |
| `test_srs_kmeans_handles_meta_without_ome` | C edge | source `ome=None` → `label.meta.ome is None` |

All 7 tests pass locally with
`PYTHONPATH="packages/scistudio-blocks-imaging/src;packages/scistudio-blocks-srs/src" pytest packages/scistudio-blocks-srs/tests/test_processblock_meta_propagation.py --timeout=60 --no-cov`.

## 9. Out of Scope

- `LoadSRSImage` / `SaveSRSImage` IO blocks — out of scope per spec scope.out;
  Phase B2 covers ProcessBlocks only.
- `types.py` — no edit required because `SRSImage.Meta` inherits `Image.Meta`
  via Python class inheritance.
- Imaging-package ProcessBlocks — covered by parallel Phase B1.
- Pre-existing `test_types.py::test_srsimage_required_axes` / `…missing_lambda_raises`
  failures (since commit `bb8a9cb4` loosened `required_axes` to drop `lambda`)
  are pre-existing test debt unrelated to this audit and were not introduced
  by Phase B2 changes.

## 10. References

- [docs/specs/adr-043-package-migration.md](../specs/adr-043-package-migration.md) FR-009, FR-011, T-040..T-046
- [docs/planning/adr-043-package-migration-checklist.md](../planning/adr-043-package-migration-checklist.md) §11 Track B2
- Parallel: [docs/audit/adr-043-imaging-propagation-audit.md](adr-043-imaging-propagation-audit.md) (Phase B1, in progress)
- Phase A2 PR: #1298 (merged)
- Umbrella PR: #1297
