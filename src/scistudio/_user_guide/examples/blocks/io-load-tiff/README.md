# IOBlock example — a custom TIFF loader

`LoadTiffImage` ([load_tiff_image.py](load_tiff_image.py)) teaches the Load block to read a plain
`.tif` micrograph into this project's `Image` type. Loaders and savers are how
data gets **in and out** of a workflow — here, in.

## The simple helpers

You almost never subclass `IOBlock` directly. Use the two helper bases from
`scistudio.blocks.io`:

- **`SimpleLoader`** — reads a file → a `DataObject`. You implement
  `load_file(self, path, config)`.
- **`SimpleSaver`** — writes a `DataObject` → a file. You implement
  `save_file(self, obj, path, config)`.

A loader needs three class attributes plus the one method:

```python
class LoadTiffImage(SimpleLoader):
    output_type = Image                 # the type you produce
    format_id   = "tiff"                # a short stable id for this format
    extensions  = (".tif", ".tiff")     # the file extensions you claim

    def load_file(self, path, config) -> Image:
        ...
```

That is all SciStudio needs to register your loader, route matching files to
it, and show it in the palette. The file path the user picks arrives as
`path` — read it from there.

## What to notice

- **A narrow contract, kept.** The reader below handles exactly one TIFF
  flavor — single-page, uncompressed, 8-bit grayscale — and *refuses
  everything else by name*. A loader that guesses is a loader that corrupts
  data silently; the imaging package pattern is one narrow capability per
  format variant.
- **The source travels.** The loader records `FrameworkMeta(source=...)` on
  the value. Everything downstream that names the data — preview cards, save
  dialogs — reads it.
- **Depends on the Image type.** `from image import Image` resolves because a
  project's `types/` folder is on the import path. Copy
  [types/image/](../types/image/) into your project first; with both files in
  place, a Load node pointed at a `.tif` produces an `Image`.

## Beyond the basics

`SimpleLoader`/`SimpleSaver` synthesise a conservative *format capability*
for you (which type, which direction, which extensions). When you need finer
control — several formats in one block, declaring exactly which metadata
survives the round-trip — declare `format_capabilities` and a
`MetadataFidelity` explicitly, or subclass `IOBlock` and override `load()` /
`save()`. See `scistudio.blocks.io` in the API reference (`FormatCapability`,
`MetadataFidelity`).

## Try it

Put [types/image/](../types/image/) in `types/` and this block in `blocks/`,
reload blocks, then drop a Load node on the canvas and point it at a `.tif`.
