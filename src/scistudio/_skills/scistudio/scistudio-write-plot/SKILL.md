---
name: scistudio-write-plot
description: |
  Use when the user wants a quick figure of a block's output: a matplotlib,
  seaborn, or ggplot2 chart drawn from one output port and shown in the Plots
  tab (e.g. "scatter the measurements from my segment-cells node", "show me a
  histogram of that output"). A plot lives in `plots/<plot_id>/` and is
  preview-only. Not for a figure that must be a saved pipeline output (write a
  block that produces an `Artifact` with scistudio-write-block) or for exploring
  a result interactively (scistudio-write-miniapp).
---

# scistudio-write-plot

## 1. What a plot is

A plot is a small script that draws a figure from one output port of one
workflow node. It lives in `plots/<plot_id>/` as two files: `plot.yaml`, which
records the port the plot is bound to and how it renders, and a render script
(`render.py` or `render.R`) that defines `render(collection)`. The figure shows in
the Plots tab of the GUI.

A plot is only for looking. It never becomes a workflow node, never edits the
workflow, and never produces data or lineage for another step. Use it for a quick
look while the user works. When the figure must be a saved, reproducible output
of the pipeline, write a block that produces an `Artifact` instead
(`scistudio-write-block`). When the user wants to change settings and watch the
figure respond, offer a MiniApp (`scistudio-write-miniapp`).

`scaffold_plot` writes `plot.yaml` for you; you normally edit only the render
script. The plot binds to the node id and output port, never to the node's
display label, so two nodes with the same label stay distinct.

## 2. Steps to write a plot

1. **Find the target.** Call `list_plot_targets` and pick the target whose node
   and output port hold the data to plot. Check `latest_output_available`; when
   it is false, the workflow has to run before the plot can draw. When the figure
   needs data from two or more ports, first combine them into one output (see
   "When a figure needs several outputs" in §4).
2. **Pick a starting point (optional).** Call `list_plot_examples(language=...,
   library=...)` for a render body in matplotlib, seaborn, or ggplot2.
3. **Scaffold.** Call `scaffold_plot(plot_id=..., target_id=..., language=...)`
   with the `target_id` from step 1, and read its `warnings` and `next_step`.
4. **Write `render`.** Edit the render script: open the data from `collection`,
   draw the figure, and return it.
5. **Validate.** Call `validate_plot(plot_id=...)` and fix every error.
6. **Run.** Call `run_plot_job(plot_id=...)` and check `status`. On failure,
   read `errors` and `stderr`, fix the script, and run again.
7. **Look at the figure.** A plot that ran can still be unreadable. Look at the
   rendered image and fix every visual problem listed in "Check the figure"
   (§4), then run again.
8. **Report.** Tell the user the figure is in the Plots tab, and what it shows.

## 3. Anti-patterns

- Binding a plot by a node's display label instead of a `target_id` from
  `list_plot_targets`.
- Hand-writing `plot.yaml` instead of calling `scaffold_plot`.
- Writing `render(collection, context)`; the entrypoint takes only `collection`.
- Importing from SciStudio in the render script; `collection` is the whole
  interface.
- Returning `None` from `render`.
- Reading a second port's output from files inside `render` because a plot binds
  to one port; combine the outputs into a `CompositeData` type instead.
- Treating a plot as a workflow step: editing `workflows/*.yaml` from a plot task,
  or expecting a plot to feed another block or appear in lineage.
- Running a plot without `validate_plot`, or reporting success without checking
  `status`.
- Reporting a plot as done without looking at the rendered figure.
- Treating the rendered file as a kept result; the next run overwrites it.

## 4. Defaults, tool sequence, and failure handling

**What `collection` gives you.** Python: `collection.types`, `collection.items`
(`len`, iterate, index, slice), `collection.items.open_one()` for the first item,
`collection.items.open(max_items=n)` for a list of items, and per item `item.type`,
`item.metadata`, and `item.open()`. R uses the same names with `$`
(`collection$items$open_one()`, `collection$items[[i]]$open()`).

`open()` returns plain objects:

| Item type | Python | R |
|---|---|---|
| `Array` | `numpy.ndarray` | `matrix` (2-D) or `array` |
| `DataFrame` | `pandas.DataFrame` | `data.frame` |
| `Series` | `pandas.Series`; a `DataFrame` when stored with two or more columns (a spectrum's `lambda` and `intensity`) | vector |
| `Text` | `str` | character |
| `Artifact` | `pathlib.Path` | character path |
| `CompositeData` | `dict` of opened parts | named list |

Package types reach the script as their core base type; an `Image` opens as an
`Array`. `open()` loads the data into memory under a size limit (64 MiB per input
by default), so for a large input open fewer items or read only what the figure
needs.

**What `render` returns.** Python: a matplotlib figure, a path to an image the
script wrote in its working directory, or a list of either. R: a ggplot object, a
path, or a list of either; base graphics drawn inside `render` are captured
without a return value.

**Figure size and style.** Both languages default to 6.4 × 4.8 inches. Python
plots also get a house style before `render` runs: large text (20 pt labels,
18 pt ticks and legend, 24 pt titles) and constrained layout, so they stay
readable in the Plots tab. Keep the default size unless the figure needs more
room: many categories, several panels, or a legend outside the axes. Then enlarge
it in proportion; do not shrink it below the default. In Python, pass `figsize`
when creating the figure (`plt.subplots(figsize=(12, 5))`). In R, call
`figure_size(12, 5)` at the top level of the script, outside `render`.

**Check the figure.** After a successful run, look at the image. With the
figure visible in the Plots tab, call `screenshot_gui(target="workspace")`; you
can also open a PNG from `artifact_paths` if your host can view images. Check for:

- a legend covering data, or legends overlapping each other;
- axis labels or tick labels overlapping each other, or cut off at the edge;
- a title, colorbar, or annotation overlapping the plot area;
- text too small to read, or markers so dense that the data cannot be seen;
- missing axis labels or units.

Fix these in the script: move the legend (`loc="best"`, or outside the axes with
`bbox_to_anchor`), rotate or thin crowded tick labels, and enlarge `figsize` when
the text has no room; in ggplot2, adjust `theme()` and `figure_size`. Run again and look again.

**When a figure needs several outputs.** A plot binds to exactly one output port.
When the figure needs data from two ports (a UMAP embedding from one step and the
cluster labels from another), combine them first:

1. **Create a composite type.** Subclass `CompositeData` in `types/<name>.py`,
   set `expected_slots` to one named slot per output (for example
   `{"embedding": DataFrame, "clusters": DataFrame}`), and call `reload_blocks`.
2. **Create a merge block** with `scistudio-write-block`: one input port per
   output to combine and one output port of the new type. Its `run` puts each
   input into its slot.
3. **Add the block to the workflow** with `scistudio-build-workflow`, wire both
   outputs into it, and run the workflow.
4. **Plot the merge block's output.** In `render`, `open_one()` returns a dict
   keyed by slot name.

**Formats and limits.** A plot writes SVG, PDF, PNG, or JPEG. A run times out
after 30 seconds by default and may write up to 8 files and 10 MiB; the manifest
can tighten these, and the runtime caps them at 300 seconds, 32 files, and 64 MiB.

**Where the output goes.** `run_plot_job` writes `current.*` and `current.json` to
`.scistudio/previews/<workflow_id>/<node_id>/<output_port>/<plot_id>/`, replacing
the previous run's files. This cache is for display; to keep a figure, export it.

**Tool sequence.**

```
list_plot_targets
list_plot_examples(language, library)      # optional
scaffold_plot(plot_id, target_id, language)
# edit plots/<plot_id>/render.py or render.R
validate_plot(plot_id)
run_plot_job(plot_id)                      # check status
```

**When something fails.** `validate_plot` returns `valid`, `errors`, and
`warnings`; an unavailable R runtime is a warning, not an error. `run_plot_job`
returns `status` (`succeeded`, `failed`, `timed_out`, or `cancelled`) with `errors`,
`stdout`, and `stderr`. A target that no longer exists means its node was deleted
or recreated; the user can relink the plot from its card in the Plots tab, or you
can scaffold it again on the new target with `overwrite=true` and restore the
render script. A missing input means the bound workflow has not run;
run it with `scistudio-build-workflow`.

## 5. Contracts and routing

**Contracts (MUST follow).**

- `plot.yaml` fields, plot tool arguments, and results: the live MCP tool schemas.
- `CompositeData` and `expected_slots`:
  `user-guide/api-reference/scistudio.core.types.md`.

**Agent reference.**

- Render contract, `collection` surface, and return values:
  `.scistudio/agent-reference/plot-contract.md`.

**User guide.**

- Writing a plot, as the user sees it: `user-guide/writing-plots.md`.
- Making a data type: `user-guide/custom-types.md`.

**Related skills.**

- `scistudio-write-block`: the merge block for a composite plot, or a block that
  saves a figure as a pipeline output.
- `scistudio-build-workflow`: wiring a merge block, or running the workflow the
  plot is bound to.
- `scistudio-inspect-data`: checking the output's type and columns before writing
  `render`.
- `scistudio-write-miniapp`: the user wants to change settings and watch the
  figure respond.

## 6. Examples

**Python: scatter a table.**

```python
def render(collection):
    import matplotlib.pyplot as plt

    df = collection.items.open_one()
    fig, ax = plt.subplots()
    ax.scatter(df["area"], df["intensity"], s=6)
    ax.set_xlabel("area")
    ax.set_ylabel("intensity")
    return fig
```

**Python: overlay every spectrum in a batch.**

```python
def render(collection):
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    for item in collection.items:
        s = item.open()
        ax.plot(s.iloc[:, 0], s.iloc[:, 1])
    return fig
```

**Python: two outputs combined in a composite type.**

```python
def render(collection):
    import matplotlib.pyplot as plt

    parts = collection.items.open_one()      # {"embedding": ..., "clusters": ...}
    df = parts["embedding"].merge(parts["clusters"], on="cell")
    fig, ax = plt.subplots()
    for label, cells in df.groupby("cluster"):
        ax.scatter(cells["UMAP1"], cells["UMAP2"], s=4, label=label)
    ax.set_xlabel("UMAP1")
    ax.set_ylabel("UMAP2")
    ax.legend(title="cluster", loc="center left", bbox_to_anchor=(1, 0.5))
    return fig
```

**R: ggplot2.**

```r
render <- function(collection) {
  df <- collection$items$open_one()
  ggplot2::ggplot(df, ggplot2::aes(x = area, y = intensity)) +
    ggplot2::geom_point()
}
```

## 7. Available tools

The live MCP tool list is the source of truth; these are the tools this task
uses.

| Tool | What it does | When to use it |
|---|---|---|
| `list_plot_targets` | Lists the output ports a plot can bind to, with a stable `target_id`. | First, to choose the data to plot. |
| `list_plot_examples` | Lists starter render scripts by language and library. | When starting a render script. |
| `scaffold_plot` | Creates `plots/<plot_id>/` with `plot.yaml` and a render script. | To start a plot bound to a target. |
| `read_plot_source` | Returns a plot's manifest and render script. | Before changing an existing plot. |
| `validate_plot` | Checks the manifest, target, and render entrypoint. | After editing, before running. |
| `run_plot_job` | Renders the figure and writes it to the preview cache. | After validation, and after each change. |
| `get_block_output` / `inspect_data` | Resolve and describe the bound output. | When you need the data's type or columns before writing `render`. |
| `screenshot_gui` | Captures the SciStudio workspace as an image (local MCP only). | To look at the rendered figure for visual problems. |
| `open_gui` | Returns the address of the running GUI. | When the user wants to see the figure in the Plots tab. |
