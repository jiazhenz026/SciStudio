# Spec: Data Preview Panel — Source Filename + 3D Viewer (v1)

**Status**: implemented (PR for #898 + #899, 2026-05-15)
**Related**: ARCHITECTURE.md §4.1 (Array axes), §9.7 (Data Preview Panel), ADR-027 D1 (named axes), ADR-031 (reference-only data contract), ADR-032 (MetadataStore)

---

## 1. Purpose

The right-column **Data Preview** panel in SciEasy Studio renders block outputs as type-specific previews. Two long-standing UX gaps surfaced live in the microplastic-calibration project (2026-05-15):

1. **Pill labels were uninformative.** Each output rendered as a truncated UUID (`data-873de`) regardless of whether the underlying DataObject carried a real source filename. For LoadImage outputs this is the user's primary mental key.
2. **3-D arrays rendered as nonsensical 2-D strips.** The reducer in `runtime.py::preview_data` blindly peeled leading axes via `while ndim > 2: matrix = matrix[0]`. For `(y, x, c)` RGB plots this produced a `(x, c)` strip (e.g. `(1285, 3)` displayed as a 1285×3 grayscale image). The same shape category covered z-stacks `(y, x, z)`, time series `(y, x, t)`, and hyperspectral cubes `(lambda, y, x)`.

v1 fixes both with a minimum-viable design that does **not** preclude richer follow-ups.

## 2. Non-goals (deferred to v2)

- **RGB composite mode.** Single-channel grayscale per slider position is v1; Fiji-style channel-merge with per-channel colors is v2.
- **Multi-slider for ndim > 3.** v1 renders one slider on the first non-(y, x) axis; further extra dims peel `[0]`. ndim>3 multi-slider is v2.
- **Click-pixel-on-lambda-image → spectrum chart.** Lambda renders the same as other axes in v1.
- **True zarr partial reads** via `Array.sel()`. v1 keeps the existing full-array load in `_load_preview_matrix`; partial reads are an optimization that only matters once a real large-array slowness is reported.
- **Block-level Methods export.** Tracked separately under the lineage / methods scope.

## 3. Backend contract

`GET /api/data/{ref}/preview?slice=<int>` returns:

```jsonc
{
  "ref": "data-xxxxx",
  "type_name": "Image",
  "preview": {
    "kind": "image",
    "shape": [40, 320, 320],          // ORIGINAL full shape, ndim preserved
    "axes": ["lambda", "y", "x"],     // may be [] when block didn't set axes
    "slice_axis_name": "lambda",      // null when ndim == 2
    "slice_axis_size": 40,            // null when ndim == 2
    "slice_index": 12,                // server-clamped index actually rendered, null when ndim == 2
    "src": "data:image/png;base64,...",
    "thumbnail": [[...]]
  }
}
```

`slice` query param semantics:
- Default `0`.
- Out-of-range values are **clamped** to `[0, slice_axis_size - 1]`; never `400`.
- Ignored for non-image previews and for ndim == 2 images.

## 4. Backend (y, x) plane detection

In `runtime.py::preview_data` image branch:

```
ndim = matrix.ndim
if axes and "y" in axes and "x" in axes:
    y_idx, x_idx = axes.index("y"), axes.index("x")
else:
    # numpy convention fallback
    y_idx, x_idx = ndim - 2, ndim - 1
```

The first dimension index NOT in `(y_idx, x_idx)` becomes the slider axis. Further extra dims peel `[0]` (ndim>3 fallback documented in §2).

**Why prefer axes over convention.** ADR-027 D1 makes every `Array` instance carry `axes: list[str]`. Plugin types (Image, FluorImage, SRSImage, etc.) declare `required_axes`. For correctly-axed objects the detection is exact. For axes-less custom blocks the numpy convention (`last two dims = (y, x)`) handles 95% of cases — z-stacks `(z, y, x)`, time series `(t, y, x)`, and hyperspectral `(lambda, y, x)` all give the right slider axis.

**Failure mode.** Custom blocks that store data in non-conventional order (`(y, x, c)` RGB plots being the canonical example we hit live) lose the friendly axis label without proper axes (slider labeled `axis 2` instead of `c`) but the slicer still picks the correct plane because `axes=["y","x","c"]` IS set by the block. Encourage user-authored custom blocks to set `axes`; document in block-development guide.

## 5. Frontend contract

`DataPreview.tsx` derives pill labels client-side from `blockOutputs[block_id]` payload (which already carries `metadata.framework.source` per ADR-032 wire format — no backend change for #898).

`extractRefEntries(payload) → Array<{ref, displayName}>` resolution order:

1. `basename(metadata.framework.source)` (LoadImage and IO loaders)
2. `basename(metadata.meta.source_file)` (typed `Image.Meta.source_file`)
3. `basename(metadata.meta.file_path)` (Artifact)
4. Fallback: `ref.slice(0, 10)` (today's behavior, no regression)

Pill button `title` is set to the full ref so power users can still see it.

## 6. Slider UX

`ImageViewer` renders a horizontal `<input type="range">` slider when `slice_axis_size > 1`. Label:

- `lambda (40)` when `axes` declared the axis
- `axis 0 (40)` when axes empty
- Position: `[N+1]/[total]` (1-indexed for human reading)

**Debounce**: 200 ms. The slider's `value` is driven by parent `currentSliceByRef[activeRef]` state — it updates instantly on drag. The fetch is deferred 200 ms; if user keeps dragging, the timer resets. Cache hits skip the timer entirely (instant image swap on cached slices).

**State preservation across slice changes** — critical. Zoom / pan / LUT / min-max display range are component-local `useState` in `ImageViewer` and must survive prop changes. Achieved by ensuring `ImageViewer` is NEVER unmounted during a slice transition:

- When the requested slice is not yet cached, `DataPreview` falls back to ANY cached preview for the same ref (slice 0 or the most recently-loaded slice), keeping `ImageViewer` mounted.
- The slider's `value` prop is driven from parent state (not from `preview.slice_index`), so dragging never snaps back to a stale backend-rendered index while a new fetch is in flight.

This is verified live: zoom 156% + viridis LUT survive a slider drag from position 0 to 12.

## 7. Slice cache

Local to `DataPreview.tsx`:

- `sliceCacheRef: useRef<Map<sliceKey, DataPreviewResponse>>` where `sliceKey = ${ref}#${index}`.
- `sliceFetchingRef: useRef<Set<sliceKey>>` prevents duplicate in-flight fetches.
- `sliceCacheVersion` (counter `useState`) bumps on each cache write to trigger memo re-evaluation.
- Slice 0 reads from the existing store-level `previewCache` (no migration needed); slice ≥ 1 reads from the local map.

Cache lifetime is the component instance. Closing the project or switching to a workflow that has no outputs unmounts the component and clears the local cache. Re-opening triggers fresh fetches. Acceptable for v1; a global store-level slice cache is a v2 optimization.

## 8. Test coverage

### Backend (`tests/api/test_data.py`)

- `test_preview_data_2d_image_has_no_slider_fields` — ndim=2 → `slice_axis_*` all `None`.
- `test_preview_data_3d_yxc_image_renders_slider_for_c_axis` — `(8, 12, 3)` `axes=["y","x","c"]` → slider 'c' size 3; `?slice=2` returns different `src` than `?slice=0`.
- `test_preview_data_3d_zyx_image_picks_z_as_slider` — `(5, 4, 6)` `axes=["z","y","x"]` → slider 'z' size 5.
- `test_preview_data_3d_no_axes_uses_axis0_fallback` — `(7, 9, 11)` no axes → slider 'axis 0' size 7.
- `test_preview_data_clamps_out_of_range_slice_query` — `?slice=999` clamps to 2; `?slice=-5` clamps to 0; both 200.

### Frontend (`frontend/src/components/DataPreview.test.tsx`)

- `pill label shows source filename when framework.source is set (#898)` — also covers meta.source_file fallback and truncated-ref fallback for empty source.
- `renders slice slider when slice_axis_size > 1 (#899)` — checks max, value, label format.
- `does NOT render slice slider for ndim=2 image (#899)` — `queryByTestId` returns null.

### Live (Chrome MCP, microplastic-calibration project)

- `srs_calibrate` Done → 3-D `(40, 320, 320)` `axes=["lambda","y","x"]` → slider visible labeled `lambda (40)`, badge `40 × 320 × 320 | 100%`, drag 0→20 changes rendered `src`.
- `max_project` Done → 2-D `(320, 320)` `axes=["y","x"]` → no slider, badge `320 × 320 | 100%`.
- State preservation: zoom 156% + viridis LUT survive slider drag from position 0 to 12.

## 9. Risks accepted in v1

- **`axes` empty on custom user blocks** → slider labeled `axis 0`. Fix path: educate block authors to set `axes` (block-development docs already cover this).
- **Backend always loads full array** → for a 100-slice z-stack with large per-slice extent, dragging across all positions issues 100 full loads. Acceptable for v1; optimize via `Array.sel()` zarr partial reads if a real complaint surfaces.
- **Local slice cache lost on component unmount** → re-clicking a different output pill within the same panel preserves the cache, but closing the project / re-opening the workflow forces refetches. Acceptable.

## 10. v2 follow-up issues (to be filed after v1 merge)

- RGB composite mode (channel merge with per-channel colors)
- Multi-slider for ndim > 3
- Click-pixel-on-lambda-image → spectrum chart
- True zarr partial reads via `Array.sel()` in `_load_preview_matrix`
- Store-level slice cache (cross-component, persists across selection)
