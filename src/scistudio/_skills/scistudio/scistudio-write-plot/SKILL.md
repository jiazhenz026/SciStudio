---
name: scistudio-write-plot
description: |
  Use when the user wants a QUICK PREVIEW PLOT — a matplotlib, seaborn, or
  ggplot2 figure drawn from a block OUTPUT collection and shown in the
  preview panel (e.g. "scatter the measurements from my segment-cells node",
  "show me a histogram of that output"). A plot job lives in
  ``<project>/plots/<plot_id>/`` and renders a display-only artifact.

  NOT for authoring a reusable processing BLOCK — that is
  scistudio-write-block (a Python class under ``blocks/<name>.py`` that
  becomes a workflow node). NOT for adding a node to a workflow YAML — that
  is scistudio-build-workflow. A plot job NEVER becomes a workflow DAG node,
  NEVER edits workflow YAML, and NEVER produces downstream data or lineage.
---

# scistudio-write-plot

A **plot job** is a preview-only figure. You bind it to one block **output
port**, write a `render(collection, context)` script, run it, and the
resulting PNG / JPEG / SVG / PDF appears in the preview panel through the core
`PlotPreviewer`. It is **not** a workflow block and **not** a DAG node.

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
    target_id="tgt_...",          # from list_plot_targets — NOT a label
    language="python"             # or "r"
)
# Creates plots/cell_scatter/plot.yaml + render.py (or render.R).
# READ the next_step + warnings in the result envelope.

# Edit plots/cell_scatter/render.py to draw your figure.

mcp__scistudio__validate_plot(plot_id="cell_scatter")
# Catches broken targets, schema errors, path traversal, bad output formats,
# missing entrypoint. R runner unavailability is a WARNING, not an error.

mcp__scistudio__run_plot_job(plot_id="cell_scatter")
# Renders preview-side, writes current.* + current.json to the preview cache.
# Re-running OVERWRITES current.* — it never appends a workflow node.
```

## 2. plot.yaml — the manifest

Strict, versioned. Binding identity is `target.node_id` + `target.output_port`;
`display_label` is metadata only.

```yaml
schema_version: 1
id: cell_scatter
title: Cell Scatter
target:
  workflow_path: workflows/main.yaml
  workflow_id: main
  node_id: node_8f3a2c          # the binding key — never a label
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
  max_rows: 10000
  max_output_bytes: 10485760    # 10 MiB
  max_files: 8
```

## 3. The render contract

**Python** — `render(collection, context)`:

```python
def render(collection, context):
    df = context.to_dataframe(collection, max_rows=10000)
    fig, ax = context.plt.subplots()
    ax.scatter(df["x"], df["y"], s=6)
    return context.save_figure(fig, "figure.svg")
```

**R** — `render <- function(collection, context)`:

```r
render <- function(collection, context) {
  df <- context$to_dataframe(collection, max_rows = 10000)
  p <- ggplot2::ggplot(df, ggplot2::aes(x = x, y = y)) +
    ggplot2::geom_point()
  context$save_plot(p, "figure.pdf")
}
```

`context` helpers (preview-only — there are **no** workflow-mutation APIs):

- `context.to_dataframe(collection, max_rows=...)` — bounded DataFrame.
- `context.items(collection, max_items=...)` — bounded iteration over refs.
- `context.plt` — `matplotlib.pyplot` (Agg backend).
- `context.save_figure(fig, "figure.svg")` / `context.save_plot(...)` —
  save PNG / JPEG / SVG / PDF. SVG is sanitized before display.

seaborn works when the project environment provides it (`import seaborn`).
ggplot2 works when R + ggplot2 are installed.

## 4. Where the output goes

`run_plot_job` writes display-only artifacts to the preview cache:

```
.scistudio/previews/<workflow_id>/<node_id>/<output_port>/<plot_id>/
    current.svg        # (or current.png / current.pdf / current.jpeg)
    current.json       # run record: manifest, script hash, target, inputs,
                       # run id, runner, created time, outputs, status, error
```

Re-running overwrites `current.*` and `current.json`. The preview cache is
**not** a scientific result path — to keep a figure, export/save it explicitly.

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
- Treating a plot job as a workflow block (use `scistudio-write-block`) or a
  workflow node (use `scistudio-build-workflow`).
- Editing `workflows/*.yaml` from a plot task — plots never touch the DAG.
- Saving an unsupported format (only svg / pdf / png / jpeg are accepted).
- Skipping `validate_plot` and running a plot bound to a deleted node/port.
- Expecting `current.*` to persist as a result — it is overwritten on re-run.
