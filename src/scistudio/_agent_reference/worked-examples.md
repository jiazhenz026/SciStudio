# Worked examples

Complete, runnable examples for every authoring surface, shipped with the
in-app user guide. Each one is real code — the verbatim source of a built-in
block or panel, a tested tutorial block, or a tested agent-skill example — not
a toy sketch. Read the matching contract page first; then copy the example
into the project and edit it.

All paths below are relative to the project's `user-guide/examples/`
(that is `../../user-guide/examples/` from this page). Every example folder
carries a `README.md` walking through it.

## Blocks — copy the `.py` into the project's `blocks/`

| Example | Base class | What it shows |
|---|---|---|
| `blocks/app-fiji/` | `AppBlock` | Hand an image to Fiji/ImageJ and read the result back |
| `blocks/process-segment-cells/` | `ProcessBlock` | Per-item transform: segment a micrograph into a labeled cell map |
| `blocks/io-load-tiff/` | `IOBlock` (`SimpleLoader`) | Teach the Load block to read `.tif` into a custom `Image` type |
| `blocks/interactive-data-router/` | interactive `ProcessBlock` | Pause mid-run; the user drags items from N inputs to M outputs |

The `process` and `io` examples build on the `Image` type from
`types/image/` — copy that into the project's `types/` first.

## Types — copy the `.py` into the project's `types/`

| Example | Base class | What it shows |
|---|---|---|
| `types/image/` | `Array` | A 2-D micrograph: required `y`/`x` axes, inherited storage |
| `types/anndata/` | `CompositeData` | An AnnData-style bundle: `expected_slots` over `X`/`obs`/`var` |

## Panels — copy the folder into the project's `panels/`

| Example | Context | What it shows |
|---|---|---|
| `panels/core.array.basic/` | preview | The built-in Array preview: bounded plane/tile reads, slice controls, view persistence (verbatim built-in source; change the `id` — `core.` is reserved) |
| `panels/core.interactive.data_router/` | interactive | The panel behind the Data Router block: render the prepared view, `writeBack` one decision |
| `panels/lab.array_explorer/` | MiniApp | A standalone explorer: slider threshold with the full-array statistic computed in `panel.py` |

## Plots — copy the folder into the project's `plots/`

| Example | What it shows |
|---|---|
| `plots/cell-size-histogram/` | A `plot.yaml` + `render.py` pair: pool one column across every table in a batch |

## Workflows — copy the YAML into the project's `workflows/`

| Example | What it shows |
|---|---|
| `workflows/load-and-segment.yaml` | A two-node workflow: a Load node pointed at custom-type files, wired into a process block |

The workflow example runs unchanged once the `types/image/`,
`blocks/io-load-tiff/`, and `blocks/process-segment-cells/` examples are in the
project — together they form one small pipeline.

## Rule

An example answers "what does the finished artifact look like?". It does not
replace the contract pages in this reference or the `user-guide/api-reference/`
signatures — read the contract, then copy the example, then check your work
with the skill's tool sequence.
