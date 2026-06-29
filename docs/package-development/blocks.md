# Writing your blocks

Blocks are where your package does its work. The mechanics are the same as a
project-local block (see the user guide for the base classes and `process_item`
/ `run`); this page covers what is **different in a package**: naming, the type-
anchored ports, multiple outputs, registration, and the rule that blocks are not
an author-facing import surface.

We use the spectroscopy package's `BaselineCorrection` block as the example.

## Pick a base class

The same five base classes apply (`Block`, `ProcessBlock`, `IOBlock`,
`AppBlock`, `CodeBlock`). In a typed domain package, most blocks are
`ProcessBlock`s — they transform one item to one item over a batch — and the
loaders/savers are `IOBlock`s. Spectroscopy's 26 blocks are exactly that split:
preprocessing, feature extraction, and fitting are `ProcessBlock`s; the
load/save blocks are `IOBlock`s.

## Anchor ports on your types

A package block's ports name **your** types, which is what makes the canvas able
to type-check connections into and out of your package:

```python
class BaselineCorrection(ProcessBlock):
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="spectra", accepted_types=[Spectrum], is_collection=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="corrected", accepted_types=[Spectrum], is_collection=True),
        OutputPort(name="baseline", accepted_types=[Spectrum], is_collection=True),
        OutputPort(name="fit_diagnostics", accepted_types=[DataFrame]),
    ]
```

Two things to notice:

- **Multiple, well-named outputs.** A block is not limited to one output. Here
  the corrected spectra, the estimated baselines, and a diagnostics table are
  three separate ports, each a meaningful thing a downstream block or preview can
  use. Prefer several honest outputs over one overloaded one.
- **Mixed types out.** Two ports carry your `Spectrum`; one carries a core
  `DataFrame`. Reuse core types directly when they fit — don't wrap a plain
  table in a bespoke type.

## Package-block identity

Package blocks carry a few extra `ClassVar`s beyond `name`/`description` so the
palette can group and version them:

```python
class BaselineCorrection(ProcessBlock):
    type_name: ClassVar[str] = "spectroscopy.baseline_correction"  # stable id
    name: ClassVar[str] = "Baseline Correction"
    description: ClassVar[str] = "Estimate baselines, subtract them, report diagnostics."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "preprocessing"
```

`type_name` is the stable, namespaced identifier the engine and saved workflows
use — keep it constant across releases even if `name` (the display label)
changes. `subcategory` groups the block in the palette.

You may also set the optional display hints `ui_color` (a CSS hex string) and
`ui_icon` (a [Lucide](https://lucide.dev/icons/) icon name) to give your block
its own node color and glyph instead of the category default; an unknown icon
name silently falls back to the category icon. These are `provisional`. Use them
to make a package's blocks visually recognizable on the canvas.

## Parameters

`config_schema` is JSON Schema, rendered as the parameter panel and read with
`config.get(...)`. Package blocks tend to expose real algorithmic choices:

```python
config_schema: ClassVar[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "method": {"type": "string",
                   "enum": ["polynomial", "asls", "arpls", "airpls"],
                   "default": "polynomial", "title": "Baseline method"},
        "poly_order": {"type": "number", "default": 3, "minimum": 0},
        "max_iter": {"type": "number", "default": 50, "minimum": 1},
    },
    "required": ["method"],
}
```

Use `title`, `enum`, `minimum`/`maximum`, and `default` so the generated panel is
usable without the user reading your code.

## The body

For a `ProcessBlock`, override `process_item(self, item, config, state=None)`;
the base class loops over the batch and auto-flushes each result. Read the
incoming `Spectrum` with the inherited accessors, never with package internals:

```python
def process_item(self, item: Spectrum, config, state=None) -> Spectrum:
    s = item.to_pandas()                      # ergonomic read-out
    corrected = subtract_baseline(s, method=config.get("method", "polynomial"))
    return Spectrum.from_arrays(corrected.index.values, corrected.values,
                                meta=item.meta)   # your domain constructor
```

When you need shared setup across the whole batch (loading a model once, opening
a resource), override `setup()` and return state; it is passed to every
`process_item` call as `state`.

## Blocks are not an author-facing import surface

By default a package's block classes are exposed to **core** for registration
but are **not** part of the reuse surface — other authors interoperate with your
blocks by wiring the **types** on their ports, not by importing the block class.
A block carries engine lifecycle; importing and instantiating it in author code
is not the supported path.

If logic is worth sharing between blocks, put it in a **public helper or on a
type**, not in an imported block. You *may* publish a block class for
programmatic reuse, but only as an explicit, `@stable`-marked opt-in.

## Mark stability and register

Public blocks carry the stability decorators against your package's version
line, and you return them from the blocks entry point:

```python
from scistudio.blocks.process import ProcessBlock
# blocks/__init__.py aggregates them:
BLOCKS = [BaselineCorrection, ExtractIntensity, LoadSpectrum, ...]

# package __init__.py:
def get_blocks() -> list[type]:
    return list(BLOCKS)

def get_block_package() -> tuple[PackageInfo, list[type]]:
    return get_package_info(), get_blocks()
```

`PackageInfo` (from `scistudio.blocks.base`) carries your package name, version,
and update channel. See [publishing.md](publishing.md) for wiring it up.

## Next

[previewers.md](previewers.md) — show your types in the inspector.
