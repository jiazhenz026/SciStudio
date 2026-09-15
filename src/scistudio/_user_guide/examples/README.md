# Examples

Worked, runnable examples for every authoring surface, organized by what you
are making. Every example is real code — most of it is the verbatim source of a
built-in block, panel, or plot, or a tested tutorial block — not a toy sketch.

| Folder | What you are making |
|---|---|
| [blocks/](blocks/) | A workflow step — one example per block base class |
| [types/](types/) | A project data type |
| [panels/](panels/) | A preview panel, an interactive decision panel, a MiniApp |
| [plots/](plots/) | A preview-only figure bound to an output port |
| [workflows/](workflows/) | A workflow YAML file |

## Blocks

One example per block base class. Each folder has the block (a `.py` file) and
a short `README.md` that walks through it. Copy the block into your project's
`blocks/` and edit from there.

| Folder | Base class | What it shows |
|---|---|---|
| [blocks/app-fiji/](blocks/app-fiji/) | `AppBlock` | Hand an image to Fiji/ImageJ and read the result back |
| [blocks/process-segment-cells/](blocks/process-segment-cells/) | `ProcessBlock` | Per-item transform: segment a micrograph into a labeled cell map |
| [blocks/io-load-tiff/](blocks/io-load-tiff/) | `IOBlock` (`SimpleLoader`) | Teach the Load block to read `.tif` into a custom `Image` type |
| [blocks/interactive-data-router/](blocks/interactive-data-router/) | interactive `ProcessBlock` | Pause mid-run, let the user drag items from N inputs to M outputs |

The `process` and `io` examples build on the [Image type](types/image/): copy
that folder into your project's `types/` first (a project type under `types/`
is importable by name, which is why the blocks can do `from image import
Image`).

## Types

A data type is a Python class under your project's `types/`.

| Folder | Base class | What it shows |
|---|---|---|
| [types/image/](types/image/) | `Array` | A 2-D micrograph: required `y`/`x` axes, inherited storage |
| [types/anndata/](types/anndata/) | `CompositeData` | An AnnData-style bundle: expression matrix + `obs`/`var` tables |

## Panels

A panel is an HTML page SciStudio shows in a sandboxed iframe, reading data
only through the panel SDK. The two `core.*` folders are the **verbatim source
of the shipped built-in panels**, shown so you can read a real, working panel;
copy them into your project's `panels/` only as a starting point for your own
panel (change the `id` — `core.` ids are reserved for built-ins).

| Folder | Context | What it shows |
|---|---|---|
| [panels/core.array.basic/](panels/core.array.basic/) | preview | The built-in Array preview: bounded plane/tile reads, slice controls, view persistence |
| [panels/core.interactive.data_router/](panels/core.interactive.data_router/) | interactive | The panel behind the Data Router block: render the prepared view, `writeBack` one decision |
| [panels/lab.array_explorer/](panels/lab.array_explorer/) | MiniApp | A standalone explorer: slider threshold with the full-array statistic computed in `panel.py` |

## Plots

| Folder | What it shows |
|---|---|
| [plots/cell-size-histogram/](plots/cell-size-histogram/) | A `plot.yaml` + `render.py` pair: pool one column across every table in a batch into one histogram |

## Workflows

| File | What it shows |
|---|---|
| [workflows/load-and-segment.yaml](workflows/load-and-segment.yaml) | A two-node workflow YAML: a Load node pointed at custom-type files, wired into a process block |

## Conventions

Python examples import only from the **canonical public roots**
(`scistudio.blocks.base`, `scistudio.blocks.process`, `scistudio.blocks.io`,
`scistudio.blocks.app`, `scistudio.core.types`, `scistudio.core.meta`). For
the exact signature of any symbol, see the **API reference**.
