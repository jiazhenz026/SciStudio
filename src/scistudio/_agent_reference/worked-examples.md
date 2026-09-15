# Worked examples

Complete, runnable examples for every authoring surface, shipped with the
in-app user guide. Each one is real code — the verbatim source of a built-in
block or panel, a tested tutorial block, or a tested agent-skill example — not
a toy sketch.

All paths below are relative to the project's `user-guide/examples/`
(that is `../../user-guide/examples/` from this page). Every example folder
carries a `README.md` walking through it.

## Blocks

| Example | Base class | What it is |
|---|---|---|
| `blocks/app-fiji/` | `AppBlock` | Open an image in Fiji/ImageJ for interactive editing and collect the saved results |
| `blocks/process-segment-cells/` | `ProcessBlock` | Per-item transform: segment a micrograph into a labeled cell map |
| `blocks/io-load-tiff/` | `IOBlock` (`SimpleLoader`) | A custom loader that teaches the Load block to read `.tif` into the project's `Image` type |
| `blocks/interactive-data-router/` | **Interactive block** (`InteractiveMixin` + `ProcessBlock`) | The built-in Data Router: pauses the run, the user drags items from N inputs to M outputs |

## Types

| Example | Base class | What it is |
|---|---|---|
| `types/image/` | `Array` | A 2-D micrograph type: required `y`/`x` axes, inherited storage |
| `types/anndata/` | `CompositeData` | An AnnData-style bundle: `expected_slots` over `X`/`obs`/`var` |

## Panels

| Example | Context | What it is |
|---|---|---|
| `panels/core.array.basic/` | preview | The built-in Array preview panel: bounded plane/tile reads, slice controls, view persistence (verbatim built-in source) |
| `panels/core.interactive.data_router/` | interactive | The built-in panel behind the Data Router block: renders the prepared view, submits one decision with `writeBack` |
| `panels/lab.array_explorer/` | MiniApp | A standalone MiniApp: a slider threshold with the full-array statistic computed in `panel.py` |

## Plots

| Example | What it is |
|---|---|
| `plots/cell-size-histogram/` | A complete plot: `plot.yaml` manifest plus `render.py`, pooling one column across every table in a batch |

## Workflows

| Example | What it is |
|---|---|
| `workflows/load-and-segment.yaml` | A two-node workflow YAML: a Load node pointed at custom-type files, wired into a process block |

The block, type, loader, and workflow examples interlock: the workflow reads
as-is once the `Image` type, the TIFF loader, and the segmentation block
exist in the project.

## Rule

An example answers "what does the finished artifact look like?". It does not
replace the contract pages in this reference or the `user-guide/api-reference/`
signatures — read the contract, then check your work with the skill's tool
sequence.
