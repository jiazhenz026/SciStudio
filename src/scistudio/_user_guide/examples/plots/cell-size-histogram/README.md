# Plot example — a cell-size histogram

A complete plot — the two files a plot is, in the two-file layout the Plots
tab expects: [plot.yaml](plot.yaml) (the manifest: what port it binds to, how
it renders) and [render.py](render.py) (the script: `render(collection)` → a
matplotlib figure). Copy the folder into your project's `plots/` directory and
relink the target in the GUI, or scaffold a fresh plot with the
`scaffold_plot` tool and compare.

## What to notice

- **Binding is by node id and port, never by label.** The `target` block names
  the workflow file, the `node_id`, and the `output_port`; two nodes with the
  same display label stay distinct.
- **The script imports nothing from SciStudio.** Everything arrives through
  `collection`: `collection.items.open()` reads every table in the batch,
  `open_one()` the first. (A package type opens as its core base type — an
  `Image` opens as a NumPy array.)
- **`render(collection)` — exactly that signature.** Returning `None` is an
  error; return a figure, a path to an image you wrote in the working
  directory, or a list of either.
- **A plot is preview-only.** It never becomes a workflow node and never feeds
  another step; the rendered files are a cache the next run overwrites. A
  figure that must be kept is a block output (an `Artifact`), not a plot.

The script pools one column across every table in the batch into a single
histogram — the smallest realistic `render`. For the full contract (house
style, figure sizes, the R/ggplot2 form), see the `writing-plots.md` page of
this guide.
