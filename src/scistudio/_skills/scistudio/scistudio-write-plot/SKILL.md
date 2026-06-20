---
name: scistudio-write-plot
description: |
  Use when the user wants a QUICK PREVIEW PLOT: a matplotlib, seaborn, base R,
  or ggplot2 figure drawn from a block OUTPUT collection and shown in the
  preview panel (e.g. "scatter the measurements from my segment-cells node",
  "show me a histogram of that output"). A plot job lives in
  ``<project>/plots/<plot_id>/`` and renders a display-only artifact.

  NOT for authoring a reusable processing BLOCK: that is scistudio-write-block
  (a Python class under ``blocks/<name>.py`` that becomes a workflow node).
  NOT for adding a node to a workflow YAML: that is scistudio-build-workflow.
  A plot job NEVER becomes a workflow DAG node, NEVER edits workflow YAML, and
  NEVER produces downstream data or lineage.
---

# scistudio-write-plot

A **plot job** is a preview-only figure. You bind it to one block **output
port**, write a `render(collection)` script, run it, and the resulting PNG /
JPEG / SVG / PDF appears in the preview panel through the core `PlotPreviewer`.
It is **not** a workflow block and **not** a DAG node.

The single most important rule: **never bind a plot by a human block label.**
Block labels repeat and drift. Always discover a stable `target_id` with
`list_plot_targets` first, and let the scaffold record workflow path + node id
+ output port.

## 1. The call sequence

```
mcp__scistudio__list_plot_targets
# Pick the target whose node_id + output_port is the data you want to plot.
# Repeated blocks with identical labels still get DISTINCT target_ids.

mcp__scistudio__list_plot_examples(language="python", library="matplotlib")
# Optional: grab a starting render() body for matplotlib / seaborn / ggplot2.

mcp__scistudio__scaffold_plot(
    plot_id="cell_scatter",
    target_id="tgt_...",          # from list_plot_targets; NOT a label
    language="python"             # or "r"
)
# Creates plots/cell_scatter/plot.yaml + render.py (or render.R).
# READ the next_step + warnings in the result envelope.

# Edit plots/cell_scatter/render.py to draw your figure.

mcp__scistudio__validate_plot(plot_id="cell_scatter")
# Catches broken targets, schema errors, path traversal, bad output formats,
# missing or wrong render(collection) entrypoint. R runner unavailability is a
# WARNING, not an error.

mcp__scistudio__run_plot_job(plot_id="cell_scatter")
# Renders preview-side, writes current.* + current.json to the preview cache.
# Re-running OVERWRITES current.*; it never appends a workflow node.
```

## 2. plot.yaml: the manifest

Strict, versioned. Binding identity is `target.node_id` + `target.output_port`;
`display_label` is metadata only.

```yaml
schema_version: 1
id: cell_scatter
title: Cell Scatter
target:
  workflow_path: workflows/main.yaml
  workflow_id: main
  node_id: node_8f3a2c          # the binding key; never a label
  output_port: measurements
  display_label: Segment Cells / measurements
script:
  language: python              # or r
  path: render.py               # render.R for R
  entrypoint: render            # must be "render"
outputs:
  preferred_format: svg
  allowed_formats: [svg, pdf, png, jpeg]
runtime:
  timeout_seconds: 30
limits:
  max_input_bytes: 67108864
  max_output_bytes: 10485760    # 10 MiB
  max_files: 8
```

## 3. The render contract

**Python** - `render(collection)`:

```python
def render(collection):
    import matplotlib.pyplot as plt

    df = collection.items.open_one()
    fig, ax = plt.subplots()
    ax.scatter(df["x"], df["y"], s=6)
    return fig
```

**R** - `render <- function(collection)`:

```r
render <- function(collection) {
  df <- collection$items$open_one()
  ggplot2::ggplot(df, ggplot2::aes(x = x, y = y)) +
    ggplot2::geom_point()
}
```

**Figure size / aspect ratio.** Both languages default to **6.4×4.8 in (4:3)**.
To use a different size or ratio, set it from the render script:

- **Python**: pass `figsize` when you create the figure, e.g.
  `fig, ax = plt.subplots(figsize=(12, 5))` — the saved output uses it.
- **R**: call `figure_size(width, height)` (inches) at the **top level** of the
  script (outside `render`), e.g. `figure_size(12, 5)`. Top-level placement is
  required because base-graphics devices open before `render()` runs; it is
  honored by both base graphics and ggplot2.

Collection helpers are preview-only; there are **no** workflow-mutation APIs.

Python helpers:

- `collection.types`
- `collection.items`
- `len(collection.items)`
- `for item in collection.items`
- `collection.items[index]`
- `collection.items[start:stop]`
- `collection.items.open()`
- `collection.items.open(max_items=n)`
- `collection.items.open_one()`
- `item.type`
- `item.metadata`
- `item.open()`

R helpers:

- `collection$types`
- `collection$items`
- `length(collection$items)`
- `collection$items[[index]]`
- `collection$items$open()`
- `collection$items$open(max_items = n)`
- `collection$items$open_one()`
- `collection$items[[index]]$type`
- `collection$items[[index]]$metadata`
- `collection$items[[index]]$open()`

Core base conversions:

| Core base type | Python `open()` result | R `open()` result |
|---|---|---|
| `Array` | `numpy.ndarray` | `matrix` for 2-D data, `array` otherwise |
| `DataFrame` | `pandas.DataFrame` | `data.frame` |
| `Series` | `pandas.Series` | atomic vector |
| `Text` | `str` | character scalar |
| `Artifact` | `pathlib.Path` | character scalar path |
| `CompositeData` | `dict[str, native]` recursively | named list recursively |

Package subclasses are folded back to supported core base types before user
code sees them. For example, package `Image` and `Mask` subclasses of `Array`
appear as `Array`.

`open()` materializes data and has a memory guard. It is not lazy loading. For
large inputs, write an explicit storage-aware reader in the plot script.

seaborn works when the project environment provides it (`import seaborn`).
ggplot2 works when R + ggplot2 are installed.

## 4. Where the output goes

`run_plot_job` writes display-only artifacts to the preview cache:

```
.scistudio/previews/<workflow_id>/<node_id>/<output_port>/<plot_id>/
    current.svg        # or current.png / current.pdf / current.jpeg
    current.json       # run record: manifest, script hash, target, inputs,
                       # run id, runner, created time, outputs, status, error
```

Re-running overwrites `current.*` and `current.json`. The preview cache is
**not** a scientific result path; to keep a figure, export/save it explicitly.

## 5. Mandatory rules

- Call `list_plot_targets` FIRST and bind by `target_id`. Never bind a plot by
  a block label alone.
- A plot job is PREVIEW-ONLY. Do NOT edit `workflows/*.yaml`, do NOT add a
  workflow node, do NOT expect downstream data or lineage from a plot.
- `scaffold_plot` refuses to overwrite an existing plot unless
  `overwrite=true`. READ the `next_step` and `warnings` it returns.
- `validate_plot` before `run_plot_job`. Fix every error first.
- After `run_plot_job`, READ the `next_step` and check `status`
  (`succeeded` / `failed` / `timed_out` / `cancelled`).

## 6. Anti-patterns

- Binding a plot by block label instead of a discovered `target_id`.
- Writing old `render(collection, context)` scripts. There is no compatibility
  layer for the removed context API.
- Treating a plot job as a workflow block (use `scistudio-write-block`) or a
  workflow node (use `scistudio-build-workflow`).
- Editing `workflows/*.yaml` from a plot task; plots never touch the DAG.
- Saving an unsupported format (only svg / pdf / png / jpeg are accepted).
- Skipping `validate_plot` and running a plot bound to a deleted node/port.
- Expecting `current.*` to persist as a result; it is overwritten on re-run.
