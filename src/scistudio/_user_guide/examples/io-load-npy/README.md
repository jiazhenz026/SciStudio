# IOBlock example — a custom `.npy` loader

`LoadNpy` ([block.py](block.py)) reads a NumPy `.npy` file into an `Array`.
Loaders and savers are how data gets **in and out** of a workflow.

## The simple helpers

You almost never subclass `IOBlock` directly. Use the two helper bases from
`scistudio.blocks.io`:

- **`SimpleLoader`** — reads a file → a `DataObject`. You implement
  `load_file(self, path, config)`.
- **`SimpleSaver`** — writes a `DataObject` → a file. You implement
  `save_file(self, obj, path, config)`.

A loader needs three class attributes plus the one method:

```python
class LoadNpy(SimpleLoader):
    output_type = Array              # the type you produce
    extensions  = (".npy",)          # the file extensions you claim
    format_id   = "numpy_npy"        # a short stable id for this format

    def load_file(self, path, config) -> Array:
        ...
```

That is all SciStudio needs to register your loader, route `.npy` files to it,
and show it in the palette. The file path the user picks arrives for you — read
it from `path`.

## A matching saver

The mirror image writes a file. For example, saving a `DataFrame` to CSV:

```python
import pyarrow.csv as pcsv
from scistudio.blocks.io import SimpleSaver
from scistudio.core.types import DataFrame

class SaveCsv(SimpleSaver):
    input_type = DataFrame
    extensions = (".csv",)
    format_id  = "csv"

    def save_file(self, obj: DataFrame, path, config) -> None:
        pcsv.write_csv(obj.to_memory(), str(path))   # to_memory() -> pyarrow.Table
```

## Beyond the basics

`SimpleLoader`/`SimpleSaver` synthesise a conservative *format capability* for
you (which type, which direction, which extensions). When you need finer control
— several formats in one block, declaring exactly which metadata survives the
round-trip — declare `format_capabilities` and a `MetadataFidelity` explicitly,
or subclass `IOBlock` and override `load()` / `save()`. See
`scistudio.blocks.io` in the API reference (`FormatCapability`,
`MetadataFidelity`).
