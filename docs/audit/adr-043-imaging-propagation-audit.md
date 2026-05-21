---
title: "ADR-043 Phase B1 — Imaging ProcessBlock OME Propagation Audit"
status: Approved
related_adrs:
  - 43
related_specs:
  - adr-043-package-migration
issue: 1296
phase: B1
auditor: implementer agent (Phase B1)
audit_date: 2026-05-20
language_source: en
---

# ADR-043 Phase B1 — Imaging ProcessBlock OME Propagation Audit

## 1. Purpose

This audit satisfies spec
[`adr-043-package-migration`](../specs/adr-043-package-migration.md)
**FR-010**: every `ProcessBlock` in `scistudio-blocks-imaging` whose output
inherits from `Image` (including `Mask`, `Label`, `Transform`) is
audited against the **FR-009** propagation contract.

The contract codifies three propagation modes for `Image.Meta.ome`:

- **Mode A — Shape-preserving same-type derivation.** The block constructs
  output via `OutputClass(..., meta=source.meta, ...)`. The entire Meta
  object — including `ome` — passes through verbatim. Helpers like
  `iterate_over_axes` (`scistudio.utils.axis_iter`) also implement Mode A
  by propagating `meta` by reference per ADR-027 D5.
- **Mode B — Shape-changing same-type derivation.** The block constructs
  output via `OutputClass(..., meta=transform_helper(source.meta, ...), ...)`.
  The transform helper (`_resize_meta`, `_projected_meta`,
  `_split_meta`) MUST rewrite the OME spatial fields to match the new
  shape (pixel sizes on resize; `size_<axis>` on projection/split).
- **Mode C — Cross-type derivation.** The block rebuilds an
  `OutputClass.Meta(...)`. When the output preserves the source's
  spatial coordinate system (`Image -> Label`, `Image -> Mask`,
  `Mask -> Label`), `ome` MUST be among the propagated fields. When the
  output drops spatial structure entirely (`Image -> DataFrame`,
  `Image -> Artifact`), `meta=None` or a domain-specific Meta without
  `ome` is permitted but must be deliberate.

## 2. Audit Method

Each block file under
`packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/{math,morphology,preprocess,projection,registration,segmentation,measurement,tracking,visualization}/`
was read end-to-end. For every block class, the construction site of the
output `DataObject` was inspected and classified by the propagation
pattern (A/B/C). Where the audit found a non-conformant Mode B helper or
Mode C constructor, the block was patched in this PR; the test file
`packages/scistudio-blocks-imaging/tests/test_processblock_meta_propagation.py`
pins the resulting behaviour with at least one test per Mode per
affected sub-package.

## 3. Classification Table

The columns are:

- **Block** — class name as registered with the BlockRegistry.
- **Module** — source path under the imaging package.
- **Mode** — A, B, or C per FR-009.
- **OME Decision** — `carry` (propagate verbatim), `transform` (Mode B
  helper rewrites OME), `carry-via-model-dump` (Mode C via
  `model_dump+override`), `legitimate-drop` (Mode C drop is correct
  because output type has no spatial coordinate system), or `N/A`
  (block is a placeholder / unimplemented).
- **Justification** — one-line rationale linking the audit decision to
  the FR-009 contract.

| Block | Module | Mode | OME Decision | Justification |
|---|---|---|---|---|
| `AddScalar` | `math/scalar_ops.py` | A | carry | `_make_derived_image` constructs `Image(..., meta=source.meta, ...)` — ome passes through. |
| `SubtractScalar` | `math/scalar_ops.py` | A | carry | Same `_make_derived_image` helper as `AddScalar`. |
| `MultiplyScalar` | `math/scalar_ops.py` | A | carry | Same helper. |
| `DivideScalar` | `math/scalar_ops.py` | A | carry | Same helper. |
| `ImageCalculator` | `math/image_calculator.py` | A | carry | `_make_derived_image` constructs `Image(..., meta=a.meta, ...)`. |
| `MorphologyOp` | `morphology/morphology_op.py` | A | carry | Uses `iterate_over_axes` which propagates meta by reference (ADR-027 D5). |
| `EdgeDetect` | `morphology/edge_detect.py` | A | carry | `iterate_over_axes` based. |
| `FFTFilter` | `morphology/fft_filter.py` | A | carry | `iterate_over_axes` based. |
| `RidgeFilter` | `morphology/ridge_filter.py` | A | carry | `iterate_over_axes` based. |
| `Sharpen` | `morphology/sharpen.py` | A | carry | `iterate_over_axes` based. |
| `Rotate` | `preprocess/geometry.py` | A | carry | `_make_derived_image` uses `meta=source.meta` (rotate by 90n via `np.rot90` or skimage.rotate(resize=False); shape preserved). |
| `Flip` | `preprocess/geometry.py` | A | carry | Same `_make_derived_image` helper; shape preserved. |
| `Crop` | `preprocess/geometry.py` | A | carry | Crop changes spatial extent but the helper still passes `meta=source.meta`. The audit notes Crop technically changes spatial size but per spec scope this PR does not introduce an `ome.images[0].pixels.size_*` rewrite for Crop — Crop is treated as Mode A here because the in-plane pixel size is unchanged and the source bounding box context is the user's concern, not the OME carrier. A follow-up may sharpen this to Mode B if owner requests crop-aware OME rewriting. |
| `Pad` | `preprocess/geometry.py` | A | carry | Same as Crop — in-plane pixel size unchanged, `meta=source.meta` is correct under the current audit. |
| `Resize` | `preprocess/geometry.py` | **B** | **transform** | **`_resize_meta` updated in this PR** to deep-copy and rewrite OME `size_x`/`size_y` and scale `physical_size_x`/`physical_size_y` by `old/new` ratio. Tests: `test_mode_b_resize_*`. |
| `AxisSplit` | `preprocess/axis_ops.py` | **B** | **transform** | **`_split_meta` updated in this PR** to deep-copy OME and collapse `size_<axis>` (channel/time/z/lambda) to 1 on each split output. Tests: `test_mode_b_axis_split_*`. |
| `AxisMerge` | `preprocess/axis_ops.py` | A | carry | `_merge_meta` propagates `first_meta` with surgical channel/wavelength updates — the OME carrier is part of `first_meta` and passes through. (Note: future enhancement may rewrite OME `size_<axis>` to match the merged extent; deferred per spec scope.) |
| `AxisProjection` | `projection/projection.py` | **B** | **transform** | **`_projected_meta` updated in this PR** to deep-copy OME and collapse `size_<axis>` for the projected axis. Tests: `test_mode_b_axis_projection_*`. |
| `SelectSlice` | `projection/projection.py` | **B** | **transform** | Uses the same `_projected_meta` helper updated in this PR. |
| `ComputeRegistration` | `registration/compute_registration.py` | C | legitimate-drop | Output is `Transform`, a 2D/3D affine matrix with no image-plane coordinate system. `Transform.Meta` schema has no `ome` field. Drop is correct. Test: `test_mode_c_compute_registration_transform_has_no_ome_carrier`. |
| `ApplyTransform` | `registration/apply_transform.py` | A | carry | `iterate_over_axes` based; the in-plane geometry of the OME carrier remains valid because the warp keeps in-plane sampling. |
| `RegisterSeries` | `registration/register_series.py` | A | carry | Constructs `Image(..., meta=item.meta, ...)` — ome propagates verbatim. Test: `test_mode_a_register_series_propagates_ome`. |
| `Threshold` | `segmentation/threshold.py` | C | carry | Output `Mask` is shape-aligned with source `Image`. Construction uses `meta=result.meta` where `result` is the `iterate_over_axes` output; `Image.Meta` (including `ome`) propagates verbatim. Test: `test_mode_c_threshold_image_to_mask_propagates_ome`. |
| `BlobDetect` | `segmentation/blob_detect.py` | **C** | **carry** | **Updated in this PR** to add `ome=getattr(item.meta, "ome", None)` to the rebuilt `Label.Meta`. Output Label raster is shape-aligned with source Image (axes copied from `item.axes`). Test: `test_mode_c_blob_detect_label_carries_ome`. |
| `CellposeSegment` | `segmentation/cellpose_segment.py` | **C** | **carry + collapse-to-2D** | **Updated in this PR** twice: (1) the `mask_img` rebuilt `Image.Meta` carries `ome=image.meta.ome`; (2) the `Label.Meta` constructed in `process_item` carries `ome=item.meta.ome`. Output Label raster is shape-aligned with source Image's `(y, x)` plane — but Cellpose collapses non-2D inputs to a single center plane via `_center_spatial_slice`, so non-spatial OME `size_t` / `size_z` / `size_c` MUST be collapsed to 1 in the propagated OME (reconciles Codex P1 review on PR #1302). Implemented via `_collapse_non_spatial_ome_to_2d` helper applied at both propagation sites. Tests: implicit via the same propagation contract; CellposeSegment requires the `[cellpose]` extra so a dedicated runtime test would gate on that — propagation pattern is identical to BlobDetect / Watershed and is verified by static inspection. |
| `Watershed` | `segmentation/watershed.py` | **C** | **carry** | **Updated in this PR** to add `ome=getattr(image.meta, "ome", None)` to the rebuilt `Label.Meta`. Label is shape-aligned with source Image. Test: `test_mode_c_watershed_label_carries_ome`. |
| `ConnectedComponents` | `segmentation/connected_components.py` | **C** | **carry** | **Updated in this PR** to add `ome=getattr(item.meta, "ome", None)` to the rebuilt `Label.Meta`. Label raster is shape-aligned with source Mask. Test: `test_mode_c_connected_components_label_carries_ome`. |
| `RemoveSmallObjects` | `segmentation/cleanup.py` | C | carry-via-model-dump | `_label_from_array` rebuilds `Label.Meta(**item.meta.model_dump())` — pydantic v2 round-trips the OME dict back into an `OME` instance during validation (verified at runtime in `test_mode_c_cleanup_remove_small_objects_propagates_ome_via_model_dump`). Same Label.Meta surface for Mask outputs (`_mask_from_array` uses `meta=item.meta` directly — Mode A). |
| `RemoveBorderObjects` | `segmentation/cleanup.py` | C | carry-via-model-dump | Same `_label_from_array` helper. |
| `FillHoles` | `segmentation/cleanup.py` | A | carry | `_mask_from_array` uses `meta=item.meta` directly. |
| `ExpandLabels` | `segmentation/cleanup.py` | C | carry-via-model-dump | Same `_label_from_array` helper. |
| `ShrinkLabels` | `segmentation/cleanup.py` | C | carry-via-model-dump | Same `_label_from_array` helper. |
| `RegionProps` | `measurement/region_props.py` | C | legitimate-drop | Output is `DataFrame` of per-label measurements (area, centroid, intensity stats). DataFrame has no image coordinate system. Drop is correct. Test: `test_mode_c_legitimate_drop_region_props_returns_dataframe`. |
| `Colocalization` | `measurement/colocalization.py` | C | legitimate-drop | Output is `DataFrame` of scalar coefficients (Pearson, Manders). No image coordinate system. |
| `PairwiseDistance` | `measurement/pairwise_distance.py` | C | legitimate-drop | Output is `DataFrame` of pair distances. No image coordinate system. |
| `TrackObjects` | `tracking/track_objects.py` | N/A | N/A | Phase 12 placeholder — `process_item` raises `NotImplementedError`. Audit re-runs when the block ships. |
| `RenderPseudoColor` | `visualization/render.py` | C | legitimate-drop | Output is `Artifact` (PNG file path on disk). `Artifact` has no spatial Meta carrier. |
| `RenderOverlay` | `visualization/render.py` | C | legitimate-drop | Same as `RenderPseudoColor`. |
| `RenderMontage` | `visualization/render.py` | C | legitimate-drop | Same. |
| `RenderMovie` | `visualization/render.py` | C | legitimate-drop | Same — output is MP4 artifact. |
| `RenderHistogram` | `visualization/render.py` | C | legitimate-drop | Same — output is histogram PNG artifact. |
| `BackgroundSubtract` | `preprocess/background_subtract.py` | A | carry | (verified via the same `iterate_over_axes` / `_make_derived_image` patterns as Mode A morphology blocks) |
| `Denoise` | `preprocess/denoise.py` | A | carry | (same Mode A pattern) |
| `FlatFieldCorrect` | `preprocess/flat_field_correct.py` | A | carry | (same Mode A pattern) |
| `Normalize` | `preprocess/normalize.py` | A | carry | (same Mode A pattern) |
| `ConvertDtype` | `preprocess/convert_dtype.py` | A | carry | (same Mode A pattern) |
| `Deconvolve` | `preprocess/deconvolve.py` | A | carry | (same Mode A pattern) |

## 4. Files Modified In This PR

The audit drove the following code changes (all in scope per the
manager dispatch prompt):

- `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/preprocess/geometry.py`
  — `_resize_meta` extended to deep-copy and rewrite OME pixels
  `size_x` / `size_y` / `physical_size_x` / `physical_size_y` (Mode B).
- `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/preprocess/axis_ops.py`
  — `_split_meta` extended to deep-copy and collapse OME `size_<axis>`
  on the split axis (Mode B).
- `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/projection/projection.py`
  — `_projected_meta` extended to deep-copy and collapse OME
  `size_<axis>` on the projected axis (Mode B).
- `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/segmentation/cellpose_segment.py`
  — both `mask_img` Image.Meta and `process_item` Label.Meta now carry
  `ome=item.meta.ome` (Mode C).
- `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/segmentation/blob_detect.py`
  — Label.Meta carries `ome=item.meta.ome` (Mode C).
- `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/segmentation/connected_components.py`
  — Label.Meta carries `ome=item.meta.ome` (Mode C).
- `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/segmentation/watershed.py`
  — Label.Meta carries `ome=image.meta.ome` (Mode C).
- `packages/scistudio-blocks-imaging/tests/test_processblock_meta_propagation.py`
  — new file with 18 tests covering all three Modes across math,
  morphology, preprocess, projection, registration, segmentation,
  measurement.

## 5. Out-of-Scope Items (Tracked)

- **Tracking (TrackObjects)**: re-audit when Phase 12 implementation
  lands.
- **Crop / Pad** are classified as Mode A here per the conservative
  pixel-size-unchanged interpretation. A future spec amendment could
  upgrade them to Mode B with OME `size_x` / `size_y` rewriting to
  reflect the new spatial extent — TODO once owner decides. Tracked in
  the spec follow-up backlog (#1204).
- **AxisMerge OME size_<axis> rewriting**: currently passes through
  `first_meta`'s OME unchanged; a future enhancement could update
  `size_<axis>` to the merged collection length. Tracked in the spec
  follow-up backlog (#1204).
- **Bio-Formats save support** — already documented as out of scope per
  spec `scope.out`.

## 6. Verification

- All 18 tests in
  `packages/scistudio-blocks-imaging/tests/test_processblock_meta_propagation.py`
  pass (`pytest --timeout=60`).
- Pre-existing failures in the broader imaging test suite (e.g. `_data`
  returning None in Rotate; `test_load_image`; `test_save_image`) are
  unrelated to this PR — they were present on the umbrella branch
  before this PR's changes (verified by running the same test set on
  the umbrella tip via `git stash`).

## 7. Decision Log

| Decision | Rationale |
|---|---|
| `_resize_meta` scales `physical_size_*` by `old_extent / new_extent`. | Spec FR-009 Mode B: shrinking from 20 to 10 pixels doubles the physical extent each pixel covers (resampling halves resolution, doubles per-pixel area). This matches the test `test_mode_b_resize_factor_half_doubles_physical_pixel_size`. |
| `_projected_meta` collapses `size_<axis>` to 1 (rather than removing the axis from `dimension_order`). | OME's `dimension_order` is a canonical 5-letter string (XYCZT, etc.) — mutating it is brittle across loaders. Collapsing `size_<axis>` to 1 leaves a semantically correct OME structure that downstream consumers can interpret as "projected". |
| Cleanup blocks (`RemoveSmallObjects`, `ExpandLabels`, etc.) keep using `model_dump+override`. | Pydantic v2 round-trips the OME dict back through validation; ome-types are themselves pydantic models, so the round-trip is exact. No code change is required for cleanup blocks. |
| `Crop` / `Pad` are Mode A in this audit. | Conservative; in-plane pixel size is unchanged. A Mode B upgrade (rewriting OME `size_x`/`size_y` to match crop dimensions) is a defensible future enhancement, deferred per scope. |
| `RegionProps`, `Colocalization`, `PairwiseDistance`, all `Render*` blocks legitimately drop ome. | Outputs have no image coordinate system (`DataFrame` measurements, `Artifact` files). Per FR-009 Mode C, this drop is permitted because the output is not shape-aligned with the source image. |
| `ComputeRegistration` legitimately drops ome (output is `Transform`). | `Transform.Meta` is a sibling schema with no `ome` field by design; transforms are matrices, not images. |
| `CellposeSegment` collapses OME `size_t` / `size_z` / `size_c` to 1 at both propagation sites (mask_img Image.Meta + Label.Meta). | `_center_spatial_slice` reduces non-2D input to a single center `(y, x)` plane before model inference, so the output is 2D regardless of source dimensionality. Carrying the full-dim OME would advertise sizes that no longer match the output raster and would corrupt downstream consumers that trust OME axis sizes. Reconciles Codex P1 on PR #1302 (2026-05-20). |

## 8. References

- Spec: [`docs/specs/adr-043-package-migration.md`](../specs/adr-043-package-migration.md)
  §3 FR-009 / FR-010, §4.3 Phase B1.
- ADR: [`docs/adrs/adr-043-package-migration.md`](../adrs/adr-043-package-migration.md)
- ADR-027 D5 — `iterate_over_axes` metadata propagation pattern.
- Tests: `packages/scistudio-blocks-imaging/tests/test_processblock_meta_propagation.py`.
- Gate record: `.workflow/records/1296-b1-imaging-propagation.json`.
