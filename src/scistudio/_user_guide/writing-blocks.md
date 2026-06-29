# Writing a block

A block is one step in a workflow — it takes typed inputs, does some work, and
hands typed outputs to the next block. This page walks you through writing one
from scratch and running it. We build a `ProcessBlock` that scales every image in
a batch by a number you set in the GUI. By the end you will know the four things
every block needs: a **name**, **ports**, **parameters**, and a **body**.

> New to SciStudio? Read the overall [getting-started.md](getting-started.md)
> first; this page is the block-authoring deep dive. You usually do not start from
> a blank file — the *New custom block* action and the in-app AI assistant both
> scaffold a block for you (see [ai-assistant.md](ai-assistant.md)).

## 1. The shape of a block

A block is a Python class. Here is the whole thing; we explain each part below.

```python
from typing import Any, ClassVar

from scistudio.blocks.process import ProcessBlock
from scistudio.blocks.base import BlockConfig, InputPort, OutputPort
from scistudio.core.types import Array


class ScaleImage(ProcessBlock):
    """Multiply every pixel of each image by a gain factor."""

    # 1. Identity — shown in the palette and on the canvas node.
    name: ClassVar[str] = "Scale Image"
    description: ClassVar[str] = "Multiply each image by a gain factor."

    # 2. Ports — typed connection points.
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="input", accepted_types=[Array], description="Image to scale"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="output", accepted_types=[Array], description="Scaled image"),
    ]

    # 3. Parameters — a JSON Schema that renders the GUI panel.
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "gain": {"type": "number", "default": 1.0, "title": "Gain"},
        },
    }

    # 4. Body — runs once per item in the batch.
    def process_item(self, item: Array, config: BlockConfig, state: Any = None) -> Array:
        gain = config.get("gain", 1.0)
        pixels = item.to_memory()                  # numpy ndarray
        return Array(axes=list(item.axes), data=pixels * gain)
```

That is a complete, working block.

## 2. Identity

```python
name: ClassVar[str] = "Scale Image"
description: ClassVar[str] = "Multiply each image by a gain factor."
```

`name` is what users see in the block palette and on the node header.
`description` shows up as help text. Everything is a `ClassVar` — a class-level
attribute, not something you set in `__init__`.

### Give your block its own look (optional)

By default your block's node takes the color and icon of its category. You can
override either with two more class attributes:

```python
ui_color: ClassVar[str | None] = "#ff5733"   # any CSS hex color
ui_icon: ClassVar[str | None] = "Microscope"  # a Lucide icon name
```

- **`ui_color`** is a CSS hex string. The canvas derives the matching text and
  border shades from it, so you only pick one color.
- **`ui_icon`** is the **name** of a [Lucide](https://lucide.dev/icons/) icon
  (the icon set SciStudio bundles), e.g. `"Microscope"`, `"FlaskConical"`,
  `"Waves"`. An unknown name simply falls back to the category icon — it never
  errors and never shows a broken glyph, so you can try a name and see.

Leave both unset (`None`) and the block looks exactly as it would by category
default. These hints are *provisional* — handy and safe to use, but the exact
color-derivation and icon resolution may still be refined.

## 3. Ports

```python
input_ports = [InputPort(name="input", accepted_types=[Array], ...)]
output_ports = [OutputPort(name="output", accepted_types=[Array], ...)]
```

Ports are the plugs other blocks connect to. `accepted_types` controls what may
connect: always name a **concrete type** (`Array`, `DataFrame`, `Series`,
`Text`, `Artifact`, or a package type like `Image` or `Spectrum`) so the canvas
can type-check the wire and pick the right preview. Avoid `accepted_types=[]`
("accept anything") unless you truly mean it.

`InputPort` and `OutputPort` come from `scistudio.blocks.base`. See that module
in the API reference for the optional keywords (`required=False`, `default=`,
`description=`).

## 4. Parameters

```python
config_schema = {"type": "object", "properties": {
    "gain": {"type": "number", "default": 1.0, "title": "Gain"},
}}
```

`config_schema` is plain [JSON Schema](https://json-schema.org/). SciStudio
turns it into the parameter panel users see when they click your block. Read the
values back in the body with `config.get(name, default)`.

## 5. The body

```python
def process_item(self, item, config, state=None):
    gain = config.get("gain", 1.0)
    pixels = item.to_memory()              # the real value
    return Array(axes=list(item.axes), data=pixels * gain)
```

We chose `ProcessBlock` because every image is transformed independently and the
number of images does not change. `ProcessBlock` loops over the incoming batch
for you and calls `process_item` **once per item**, so you only write the
single-item logic. (For full control over the whole batch — filtering, merging,
splitting — subclass `Block` and write `run()` instead; see
[the process example](examples/process-scale-array/) and the API reference.)

Two things every body does:

- **Read the value** with `item.to_memory()`. What you get back depends on the
  type (see the table below).
- **Build the result** with the type's keyword constructor and `data=`.

### Reading and building each type

| Type | `item.to_memory()` returns | Read pandas/numpy directly | Build one with |
|---|---|---|---|
| `Array` | numpy `ndarray` | `item.to_numpy()` | `Array(axes=[...], data=arr)` |
| `DataFrame` | `pyarrow.Table` | `item.to_pandas()` / `item.to_numpy()` | `DataFrame(data=table)` |
| `Series` | `pyarrow.Table` | `item.to_pandas()` / `item.to_numpy()` | `Series(index_name=..., value_name=..., data=table)` |
| `Text` | `str` | — | `Text(content="...")` |
| `Artifact` | `bytes` (file contents; the path is `item.file_path`) | — | `Artifact(file_path=Path(...))` |

`to_pandas()` and `to_numpy()` are the **ergonomic accessors**: tables are
stored as Arrow (the fast, cross-language form), but most people think in pandas
or numpy, so these read straight out to what you know. They are read-only
conveniences — you still build a table back with `data=` and an Arrow table
(`pyarrow.Table.from_pandas(df)`).

## 6. Where the file goes

Save the class as a `.py` file under `blocks/` in your project (the *New custom
block* action does this for you). SciStudio discovers it automatically and it
appears in the palette. There is one class per concept; you can put several
blocks in one file if they are related.

## 7. Run it

Drop the block on the canvas, wire an image source into its `input` port, set
**Gain** in the parameter panel, and run the workflow. The output port now
carries the scaled images, ready for the next block or a preview.

## 8. Testing (optional but recommended)

A block is a normal Python class, so you can test it without the GUI: build a
`Collection` of inputs, call `run(...)`, and check the outputs.

```python
import numpy as np
from scistudio.core.types import Array, Collection
from scistudio.blocks.base import BlockConfig


def test_scale_doubles():
    img = Array(axes=["y", "x"], data=np.ones((2, 2)))
    block = ScaleImage()
    out = block.run({"input": Collection([img], item_type=Array)},
                    BlockConfig(params={"gain": 2.0}))
    assert (out["output"].open_one().to_memory() == 2.0).all()
```

`Collection` is the batch container every port carries — an ordered group of
same-type items. A single value is a `Collection` of length 1. See `Collection`
in the API reference for the helper methods (`open()`, `open_one()`, iteration).

## Next

- A different kind of block? Copy the matching [example](examples/).
- The built-in types do not fit your data? See [custom-types.md](custom-types.md).
- The exact signature of anything here? Open the **API reference**.
