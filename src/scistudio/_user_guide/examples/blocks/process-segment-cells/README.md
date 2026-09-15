# ProcessBlock example — segment a micrograph

`SegmentCellsBlock` ([block.py](block.py)) turns a microscope image into a
**labeled cell map**: threshold the foreground, fill holes, flood-fill each
connected patch its own integer label, drop the sensor noise. It is the
simplest and most common kind of block: a **per-item transform**.

## Why `ProcessBlock`

`ProcessBlock` is for blocks where:

- every item is transformed **independently**, and
- the number of items does **not** change (no filtering, merging, or splitting).

You write only `process_item(self, item, config, state=None)` — the base class
loops over the incoming batch (`Collection`) and calls it once per item, packing
the results back into a `Collection` for the output port. About 80% of blocks
need nothing more than this.

## What to notice

- **Reading the image.** `item.to_memory()` hands you the pixel grid as a NumPy
  array. (`to_numpy()` and the typed accessors are there too; see the
  `Array` page in the API reference.)
- **Parameters.** `config_schema` is JSON Schema; read values with
  `config.get("threshold", 70)`. Every parameter the user sees carries a
  `title` and a `description` — those strings are the parameter panel.
- **Provenance travels.** The output keeps `framework=item.framework`, so the
  result is still named after the slide it came from in previews and saves.
- **The `c` axis.** The block returns the micrograph and its label map as two
  channels of one `Image` (`c=0`/`c=1`) so a preview can draw the labels over
  the cells — an `Array` subclass may name a `c` axis for exactly this.

This block is also honest about being imperfect: both the `threshold` and the
`adaptive` method run for real, and neither is right everywhere. That is what
segmentation is like — the example is the science, not a toy.

## Depends on the Image type

The block imports `from image import Image`. Copy
[types/image/](../types/image/) into your project's `types/` first — the
`types/` folder is on the import path, so the block resolves the project type
by its module name. Together with
[io-load-tiff/](../io-load-tiff/) and
[workflows/load-and-segment.yaml](../workflows/load-and-segment.yaml) these
examples form one small pipeline: load `.tif` → segment.

## When you need the whole batch instead

`ProcessBlock` hides the batch from you. If your block must **filter**, **merge**,
**split**, or otherwise change the item count, subclass `Block` and write
`run()`, which receives and returns whole `Collection`s — see the
[interactive Data Router](../interactive-data-router/) for a block that does.

## Try it

Wire an `Image` source into `image`, run, and the `labels` port carries one
two-channel `Image` per input.
