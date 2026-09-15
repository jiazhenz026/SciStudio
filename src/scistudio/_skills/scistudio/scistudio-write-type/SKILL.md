---
name: scistudio-write-type
description: |
  Use when the user's data needs its own data type: a Python class in
  `types/<name>.py` that subclasses a core type (Array, Series, DataFrame, Text,
  Artifact, CompositeData) to name the data, require its axes or slots, and
  carry typed metadata, together with the IO block that reads it. Call list_types
  first and reuse a type that already fits. Not for writing the block that uses the type (scistudio-write-block).
---

# scistudio-write-type

## 1. What a data type is

A data type is the kind of thing blocks pass to each other. SciStudio ships six
general types (`Array`, `Series`, `DataFrame`, `Text`, `Artifact`,
`CompositeData`), and a project makes its own by subclassing the one that holds
its data. A custom type inherits storage, reading, and large-data access from its
base; it adds a name, the rules that make the data valid (required axes or
slots), and typed metadata that travels with the data.

A type is complete only when data of that type can be read: every new type comes
with an IO block that loads it from a file, so core `load_data` can bring it into
a workflow. A type with no way to load it is unusable.

Declaring a type lets ports require it, so a mis-wired canvas is caught before a
run; gives it a name and color in the Data types tab; and lets a preview panel or
MiniApp target it. Write one when the user's data has structure or metadata the
general types do not capture. When a general type or an installed package type
already fits, use it.

## 2. Steps to write a data type

1. **Check for reuse.** Call `list_types`. When a registered type (core or from a
   package) already describes the data, use it and stop.
2. **Pick the base.** Choose the core type whose shape matches the data (§4), or
   subclass an existing type when the new one is a narrower kind of it.
3. **Write the class.** Create `types/<name>.py` with one class per type; the
   class name is the registered type name. Give it a one-line docstring, which the
   Data types tab shows.
4. **Add the rules.** For an `Array`, require axes with `required_axes`,
   `allowed_axes`, and `canonical_order`; for a `CompositeData`, map each slot to
   its type in `expected_slots`.
5. **Add metadata, if any.** Write a frozen Pydantic model and point `Meta` at it.
6. **Write its IO block (required).** With `scistudio-write-block`, write a
   `SimpleLoader` in `blocks/<name>.py` whose `output_type` is the new type, with
   the file format it reads (`format_id`, `extensions`). Add a `SimpleSaver` too
   when the user will write this type to files.
7. **Register and check.** Call `reload_blocks`, confirm the type in `list_types`
   under the intended parent, and confirm `get_block_schema("load_data")` offers the
   type in its `core_type` choices and lists the loader under `format_capabilities`. Then load a real file through core `load_data` and
   check the result with `inspect_data`.
8. **Use it.** Declare the type on block ports with `scistudio-write-block`.

## 3. Anti-patterns

- **A type with no IO block that reads it.** Every new type needs a loader, so
  `load_data` can bring its data into a workflow.
- Writing a new type when a core or installed package type already fits.
- Subclassing `DataObject` directly instead of one of the six core types.
- Naming a class like a registered type (`Array`, `Image`, a package type): the
  existing type keeps the name and the file's class is skipped.
- Naming the file after an installed Python package (`json.py`, `numpy.py`); the
  `types/` folder is on the import path, so such a file is refused.
- Redefining `to_memory`, `to_pandas`, `to_numpy`, `sel`, or `with_meta`, which the
  base already provides.
- Mutable metadata, or metadata fields that do not survive a JSON round trip.
- Metadata fields without defaults, so an instance cannot be created without them.
- Declaring a type and never checking that it registered with `list_types`.

## 4. Defaults, tool sequence, and failure handling

**Which base to subclass.**

| The data is | Subclass |
|---|---|
| N-dimensional numeric data (image, volume, stack) | `Array` |
| A 1-D indexed signal (spectrum, chromatogram, time series) | `Series` |
| A table | `DataFrame` |
| Plain text, Markdown, or JSON | `Text` |
| An opaque file (PDF, report, binary) | `Artifact` |
| A named bundle of the above | `CompositeData` |

**Where it goes.** `<project>/types/` holds types for this project, and
`~/.scistudio/types/` holds the user's types for every project. One file may
declare several types.

**Array axes.** `required_axes` lists axes every instance must have,
`allowed_axes` limits which axes it may have, and `canonical_order` fixes their
order. Use the axis names `t`, `z`, `c` (discrete channel), `lambda` (continuous
spectral), `y`, and `x`. An instance missing a required axis is rejected when it is
constructed.

**Metadata.** Define a Pydantic model with `model_config = ConfigDict(frozen=True)`,
give every field a default and a JSON-safe type, and set
`Meta: ClassVar[type[BaseModel] | None] = MyMeta` on the class. Instances take
`meta=MyMeta(...)`, and `with_meta(**changes)` returns an updated copy.

**Appearance (optional).** `ui_color` (a CSS hex color) and `ui_ring_color` color
the type's tile and every port that carries it; leaving them unset picks a stable
color.

**Tool sequence.**

```
list_types                          # reuse check
# write types/<name>.py
# write blocks/<name>.py with a SimpleLoader (and SimpleSaver if needed)
reload_blocks                       # rescans block and type registries
list_types                          # confirm the type under its parent
get_block_schema("load_data")       # the type in core_type, the loader in format_capabilities
# load a real file through load_data, then inspect_data
```

**When something fails.** A type missing from `list_types` after `reload_blocks`
failed to import, collided with a registered name, or sits in a file whose name
shadows a Python package; read the reload result, then rename or fix it. When a
block rejects a value of the type, check the axes against `required_axes` and the
metadata against the `Meta` model.

## 5. Contracts and routing

**Contracts (MUST follow).**

- Core types, their constructors and methods:
  `user-guide/api-reference/scistudio.core.types.md`.
- Metadata helpers: `user-guide/api-reference/scistudio.core.meta.md`.
- Tool names and arguments: the live MCP tool schemas.

**Agent reference.**

- Reading, constructing, and streaming values: `.scistudio/agent-reference/data-types.md`.
- Types from installed packages: `.scistudio/agent-reference/package-discovery.md`.

**User guide.**

- Making a data type, as the user sees it: `user-guide/custom-types.md`.

**Related skills.**

- `scistudio-write-block`: the IO block that reads the type, and blocks whose ports
  use it.
- `scistudio-write-panel`: a preview panel for the type.
- `scistudio-write-plot`: a composite type that combines two outputs for a plot.

## 6. Examples

These come from the core tutorial "What is a type", where they are tested.

**The type** (`types/image.py`): an `Array` that must carry `y` and `x`.

```python
from __future__ import annotations

from typing import ClassVar

from scistudio.core.types import Array


class Image(Array):
    """A 2-D microscope image: a ``y`` axis, an ``x`` axis, one value per pixel."""

    # Every Image must carry the two spatial axes; constructing one without them raises.
    required_axes: ClassVar[frozenset[str]] = frozenset({"y", "x"})
```

**Its loader** (`blocks/load_tiff_image.py`): a `SimpleLoader` that reads a plain
TIFF into an `Image`. The type file's module name (`image`) is importable because
`types/` is on the import path. It records the source file in `framework`, so
previews and saves can name the image.

```python
from __future__ import annotations

import struct
from pathlib import Path
from typing import Any, ClassVar

import numpy as np
from image import Image

from scistudio.blocks.base import OutputPort
from scistudio.blocks.io import SimpleLoader
from scistudio.core.meta.framework import FrameworkMeta

# The TIFF tags this reader needs, by their numbers in the TIFF 6.0 spec.
_WIDTH, _HEIGHT, _BITS, _COMPRESSION, _STRIP_OFFSETS, _SAMPLES, _STRIP_COUNTS = (
    256,
    257,
    258,
    259,
    273,
    277,
    279,
)

# TIFF field types this reader can decode: BYTE, SHORT, LONG.
_FIELD_FORMATS = {1: "B", 3: "H", 4: "I"}
_FIELD_SIZES = {1: 1, 3: 2, 4: 4}


def _read_baseline_tiff(path: Path) -> np.ndarray:
    """Read a single-page, uncompressed, 8-bit grayscale TIFF as a 2-D array.

    Refuses, by name, everything outside that contract rather than guessing.
    """
    data = path.read_bytes()
    if len(data) < 8 or data[:2] not in (b"II", b"MM"):
        raise ValueError(f"{path.name} is not a TIFF file (no II/MM byte-order mark).")
    order = "<" if data[:2] == b"II" else ">"
    magic, ifd_offset = struct.unpack_from(order + "HI", data, 2)
    if magic != 42:
        raise ValueError(f"{path.name} is not a classic TIFF file (magic {magic}, expected 42).")

    (entry_count,) = struct.unpack_from(order + "H", data, ifd_offset)
    tags: dict[int, tuple[int, ...]] = {}
    for index in range(entry_count):
        entry_offset = ifd_offset + 2 + 12 * index
        tag, field_type, count = struct.unpack_from(order + "HHI", data, entry_offset)
        item = _FIELD_FORMATS.get(field_type)
        if item is None:
            continue  # a field type (rationals, ASCII) nothing below asks for
        if _FIELD_SIZES[field_type] * count <= 4:
            values_at = entry_offset + 8
        else:
            (values_at,) = struct.unpack_from(order + "I", data, entry_offset + 8)
        tags[tag] = struct.unpack_from(order + item * count, data, values_at)
    (next_ifd,) = struct.unpack_from(order + "I", data, ifd_offset + 2 + 12 * entry_count)

    if next_ifd != 0:
        raise ValueError(f"{path.name} has more than one page; this loader reads a single 2-D plane.")
    if tags.get(_COMPRESSION, (1,))[0] != 1:
        raise ValueError(f"{path.name} is compressed; this loader reads uncompressed TIFF only.")
    if set(tags.get(_BITS, (1,))) != {8} or tags.get(_SAMPLES, (1,))[0] != 1:
        raise ValueError(f"{path.name} is not 8-bit single-channel grayscale.")

    width = int(tags[_WIDTH][0])
    height = int(tags[_HEIGHT][0])
    strips = b"".join(
        data[offset : offset + count] for offset, count in zip(tags[_STRIP_OFFSETS], tags[_STRIP_COUNTS], strict=True)
    )
    return np.frombuffer(strips, dtype=np.uint8).reshape(height, width)


class LoadTiffImage(SimpleLoader):
    """Read one TIFF micrograph from disk and hand it on as an ``Image``."""

    name: ClassVar[str] = "Load TIFF Image"
    type_name: ClassVar[str] = "load_tiff_image"
    description: ClassVar[str] = "Read a plain .tif/.tiff micrograph into this project's Image type."

    # The three attributes SimpleLoader turns into a load capability.
    output_type: ClassVar[type[Image]] = Image
    format_id: ClassVar[str] = "tiff"
    extensions: ClassVar[tuple[str, ...]] = (".tif", ".tiff")

    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="data", accepted_types=[Image], description="The loaded micrograph"),
    ]

    def load_file(self, path: Path, config: dict[str, Any]) -> Image:
        """Read *path* and wrap the pixels in an ``Image``, recording the source file."""
        return Image(
            axes=["y", "x"],
            data=_read_baseline_tiff(path),
            framework=FrameworkMeta(source=str(path)),
        )
```

After `reload_blocks`, `get_block_schema("load_data")` offers `Image` as a
`core_type`, and a Load node pointed at a `.tif` file produces an `Image`.

**Adding metadata to the type.** Give `Image` a frozen metadata model whose fields
all have defaults and are JSON-safe, and point `Meta` at it:

```python
from typing import ClassVar

from pydantic import BaseModel, ConfigDict
from scistudio.core.types import Array


class ImageMeta(BaseModel):
    """Acquisition details carried by every Image."""

    model_config = ConfigDict(frozen=True)

    pixel_size_um: float | None = None
    objective: str = ""


class Image(Array):
    """A 2-D microscope image: a ``y`` axis, an ``x`` axis, one value per pixel."""

    Meta: ClassVar[type[BaseModel] | None] = ImageMeta
    required_axes: ClassVar[frozenset[str]] = frozenset({"y", "x"})
```

The loader then passes it on construction,
`Image(axes=["y", "x"], data=pixels, meta=ImageMeta(pixel_size_um=0.65))`; a block
reads `image.meta.pixel_size_um` and changes it with
`image.with_meta(objective="40x")`, which returns a new object.

**A `CompositeData` type that bundles two tables.**

```python
from typing import ClassVar

from scistudio.core.types import CompositeData, DataFrame


class ClusteredEmbedding(CompositeData):
    """A cell embedding together with each cell's cluster label."""

    expected_slots: ClassVar[dict[str, type]] = {"embedding": DataFrame, "clusters": DataFrame}
```

## 7. Available tools

The live MCP tool list is the source of truth; these are the tools this task
uses.

| Tool | What it does | When to use it |
|---|---|---|
| `list_types` | Returns the data-type hierarchy. | First, to reuse a type; again after reload to confirm yours registered. |
| `reload_blocks` | Rescans the block and data-type registries. | After writing or editing a type or its IO block. |
| `get_block_schema` | Returns a block's ports, config, and format capabilities. | `get_block_schema("load_data")` to confirm the new type can be loaded. |
| `list_blocks` | Lists registered blocks with their I/O signature. | To see where an existing type is already used. |
| `inspect_data` | Returns a reference's type chain and metadata. | To check real data carries the type you expect. |
