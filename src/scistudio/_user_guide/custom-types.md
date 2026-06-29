# Making your own data type

Most of the time the built-in types — `Array`, `DataFrame`, `Series`, `Text`,
`Artifact` — are enough. Reach for a **custom type** when your data has
structure or metadata the generic types do not capture, and you want the canvas
to treat it as its own thing: type-check connections, pick a tailored preview,
and carry domain metadata from block to block.

A custom type is a small subclass of a core type. You are not building a new
storage format — you inherit all of that — you are **naming** your data and
pinning the rules and metadata that go with it.

> This page covers a **simple, project-local** type. Designing the type system
> for a distributable package (multiple types, composites, previewers) is
> covered in the Package Development guide (`docs/package-development/types.md`).

## Pick a base type

Subclass the core type whose in-memory shape matches your data:

| Your data is… | Subclass |
|---|---|
| An N-dimensional array (image, volume, stack) | `Array` |
| A 1-D indexed signal (spectrum, chromatogram, time series) | `Series` |
| A table | `DataFrame` |
| A bundle of named sub-objects | `CompositeData` |

You inherit `to_memory()`, `to_pandas()`/`to_numpy()`, `sel()`, `with_meta()`,
and the `data=` constructor for free. **Do not** redefine `to_pandas` or
`to_numpy` — you already have them.

## Example: a microscope image type

Say you work with grayscale microscope images and you want to (a) guarantee
every instance is 2-D with `y` and `x` axes, and (b) carry the pixel size so
downstream blocks can compute real distances. Subclass `Array`:

```python
from typing import ClassVar

from pydantic import BaseModel, ConfigDict
from scistudio.core.types import Array


class MicroscopeImage(Array):
    """A 2-D grayscale microscope image with a known pixel size."""

    # Tighten the axis schema: every instance MUST be 2-D (y, x).
    required_axes: ClassVar[frozenset[str]] = frozenset({"y", "x"})
    allowed_axes: ClassVar[frozenset[str] | None] = frozenset({"y", "x"})
    canonical_order: ClassVar[tuple[str, ...]] = ("y", "x")

    # Typed, validated metadata that travels with the image.
    class Meta(BaseModel):
        model_config = ConfigDict(frozen=True)   # frozen so updates stay immutable
        pixel_size_um: float | None = None       # microns per pixel
        objective: str | None = None
```

Two things make this a real type and not just an `Array`:

- **The axis schema** (`required_axes` / `allowed_axes` / `canonical_order`)
  rejects anything that is not a 2-D `y, x` image at construction time, so a
  malformed image cannot flow into your workflow unnoticed.
- **The `Meta` model** is a frozen [Pydantic](https://docs.pydantic.dev/) model.
  Its fields are validated, and because it is frozen, `with_meta()` returns a
  new instance instead of mutating in place — which keeps lineage honest.

## Construct and read it

You build a custom type exactly like a core type — the keyword constructor with
`data=` — and you set metadata through the `Meta` model:

```python
import numpy as np

img = MicroscopeImage(
    axes=["y", "x"],
    data=np.zeros((512, 512), dtype="uint16"),
    meta=MicroscopeImage.Meta(pixel_size_um=0.65, objective="40x"),
)

pixels = img.to_memory()          # numpy ndarray, exactly like Array
size = img.meta.pixel_size_um     # 0.65
```

To update metadata, use `with_meta()` (inherited); it returns a new instance:

```python
img2 = img.with_meta(objective="63x")
```

## Use it on a port

Name your type on a port and blocks will only connect compatible wires:

```python
input_ports = [InputPort(name="image", accepted_types=[MicroscopeImage])]
```

Because `MicroscopeImage` is an `Array`, a port that accepts `Array` will also
accept your image — subtypes flow into supertype ports, not the other way
around.

## Where it goes

Put the class in a `.py` file under your project (next to the blocks that use
it). For a one-off project that is all you need. If you later want to **share**
the type — give it a dedicated previewer, publish it for others to install — see
the Package Development guide, which uses the real `Spectrum` type from the
spectroscopy package as its worked example.

## What you inherited (and must not re-create)

| Inherited from the core type | Do not write your own |
|---|---|
| `to_memory()` — the canonical in-memory form | — |
| `to_pandas()` / `to_numpy()` — ergonomic read-out | ✗ never redefine these |
| `with_meta(**changes)` — immutable metadata update | — |
| `sel(...)` / `slice(...)` / `iter_chunks(...)` — large-data reads | — |
| the `data=` keyword constructor | — |

See the core type in the **API reference** for the full list.
