# scistudio-blocks-imaging

Phase 11 imaging plugin for SciStudio.

The package ships 33 implemented imaging ticket deliverables covering 49
concrete block classes across IO, preprocess, morphology, segmentation,
measurement, registration, projection, math, visualization, and interactive
AppBlocks. The primary public types are `Image`, `Mask`, and `Label`;
registration also uses the internal helper type `Transform`.

Blocks:
- IO: `LoadImage`, `SaveImage`
- Preprocess: `Denoise`, `BackgroundSubtract`, `Normalize`, `FlatFieldCorrect`, `Rotate`, `Flip`, `Crop`, `Pad`, `Resize`, `ConvertDType`, `AxisSplit`, `AxisMerge`
- Morphology: `MorphologyOp`, `EdgeDetect`, `RidgeFilter`, `Sharpen`, `FFTFilter`
- Segmentation: `Threshold`, `Watershed`, `CellposeSegment`, `BlobDetect`, `ConnectedComponents`, `RemoveSmallObjects`, `RemoveBorderObjects`, `FillHoles`, `ExpandLabels`, `ShrinkLabels`
- Measurement: `RegionProps`, `PairwiseDistance`, `Colocalization`
- Registration: `ComputeRegistration`, `ApplyTransform`, `RegisterSeries`
- Projection: `AxisProjection`, `SelectSlice`
- Math: `AddScalar`, `SubtractScalar`, `MultiplyScalar`, `DivideScalar`, `ImageCalculator`
- Visualization: `RenderPseudoColor`, `RenderOverlay`, `RenderMontage`, `RenderMovie`, `RenderHistogram`
- Interactive: `FijiBlock`, `NapariBlock`

Phase 12 deferrals remain unchanged: `Deconvolve` and `TrackObjects`.

Entry points:
- `scistudio.blocks = scistudio_blocks_imaging:get_block_package`
- `scistudio.types = scistudio_blocks_imaging:get_types`
- `scistudio.previewers = scistudio_blocks_imaging.previewers:get_previewers`

## Package-owned Image/Label previewers (ADR-048 SPEC 1)

Per ADR-048 §4/§6, the rich image-domain preview behaviour lives in this
package, not in core. Core keeps only the generic numeric Array fallback
(`core.array.basic`); this package owns the `Image` and `Label` target types.

`scistudio_blocks_imaging.previewers:get_previewers()` returns two
`PreviewerSpec` declarations (`owner_kind=PACKAGE`):

| Previewer id | Target type | Envelope kind | Capabilities |
|---|---|---|---|
| `imaging.image.viewer` | `Image` | `array` | slice, lut, range, zoom, metadata, export |
| `imaging.label.viewer` | `Label` | `composite` | slots, raster, metadata, export |

Each spec ships a same-origin `FrontendManifest` whose `module_url` is
`/api/previews/assets/<previewer_id>/viewer.js`. The packaged viewer
(`previewers/assets/viewer.js`) is a self-contained, dependency-free vanilla
ES module implementing the host-module contract
(`export default { apiVersion, mount(container, host) }`). It ports the legacy
`ImageViewer.tsx` behaviour — 9-colormap LUT, display min/max range,
single-axis slice slider, zoom/pan, and an OME/channel metadata panel — and
reads all data through the constrained host API
(`host.envelope.payload`, `host.session.patchQuery`/`getResource`,
`host.exportArtifact`). No remote code, no workflow mutation.

The backend providers read bounded data via `request.data_access` (never
materialising a full array) and embed the wire `FrontendManifest`
(`metadata.extra["frontend_manifest"]`) so the frontend host can locate the
module. The `Image` envelope uses `kind=array` so a failed dynamic-module load
degrades cleanly to the core Array viewer (FR-026).

This package is the worked reference for the ADR-048 previewer model. The
author guide for registering package or project previewers (and preview-side
plot jobs) is `docs/block-development/previewers-and-plots.md`.

## ADR-043 IO format capabilities

The imaging IO pilot declares explicit `FormatCapability` records for the
published aggregate `LoadImage` and `SaveImage` blocks. These IDs are stable
workflow replay keys:

| Capability ID | Direction | Format | Extensions | Fidelity |
|---|---|---|---|---|
| `scistudio-blocks-imaging.image.tiff.load` | load | `tiff` | `.tif`, `.tiff` | `pixel_only` |
| `scistudio-blocks-imaging.image.tiff.save` | save | `tiff` | `.tif`, `.tiff` | `pixel_only` |
| `scistudio-blocks-imaging.image.zarr.load` | load | `zarr` | `.zarr` | `pixel_only` |
| `scistudio-blocks-imaging.image.zarr.save` | save | `zarr` | `.zarr` | `pixel_only` |

`pixel_only` is intentionally conservative here. The blocks preserve the image
payload and structural axes used to construct `Image`, but they do not promise
round-trip preservation of typed `Image.Meta` domain fields such as pixel size,
channels, objective, instrument, or acquisition date.

<!-- TODO(#1204): Complete published-package hard-validation migration beyond this ADR-043 pilot.
  Out of scope per ADR-043 §9 and issue #1213 pilot scope.
  Followup: https://github.com/zjzcpj/SciStudio/issues/1204.
-->
