# scieasy-blocks-imaging

Phase 11 imaging plugin for SciEasy.

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
- `scieasy.blocks = scieasy_blocks_imaging:get_block_package`
- `scieasy.types = scieasy_blocks_imaging:get_types`

## ADR-043 IO format capabilities

The imaging IO pilot declares explicit `FormatCapability` records for the
published aggregate `LoadImage` and `SaveImage` blocks. These IDs are stable
workflow replay keys:

| Capability ID | Direction | Format | Extensions | Fidelity |
|---|---|---|---|---|
| `scieasy-blocks-imaging.image.tiff.load` | load | `tiff` | `.tif`, `.tiff` | `pixel_only` |
| `scieasy-blocks-imaging.image.tiff.save` | save | `tiff` | `.tif`, `.tiff` | `pixel_only` |
| `scieasy-blocks-imaging.image.zarr.load` | load | `zarr` | `.zarr` | `pixel_only` |
| `scieasy-blocks-imaging.image.zarr.save` | save | `zarr` | `.zarr` | `pixel_only` |

`pixel_only` is intentionally conservative here. The blocks preserve the image
payload and structural axes used to construct `Image`, but they do not promise
round-trip preservation of typed `Image.Meta` domain fields such as pixel size,
channels, objective, instrument, or acquisition date.

<!-- TODO(#1204): Complete published-package hard-validation migration beyond this ADR-043 pilot.
  Out of scope per ADR-043 §9 and issue #1213 pilot scope.
  Followup: https://github.com/zjzcpj/SciEasy/issues/1204.
-->
