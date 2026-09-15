# Plot contract

## 1. Where to look

| You need | Read |
|---|---|
| How to find a target, scaffold, validate, run, and check a plot | the `scistudio-write-plot` skill |
| `plot.yaml` fields and the plot tools' arguments and results | the live MCP tool schemas (`scaffold_plot`, `validate_plot`, `run_plot_job`) |
| What the user sees and does with plots | `user-guide/writing-plots.md` |
| The data types a plot receives | [data-types.md](data-types.md) |

## 2. Rules

- **Define exactly `render(collection)`.** In R write `render <- function(collection)`.
  Any other signature, including `render(collection, context)`, is rejected.
- **Import nothing from `scistudio`.** The script receives everything through
  `collection`. Import only plotting and data libraries such as matplotlib,
  seaborn, pandas, numpy, or ggplot2.
- **Read data through `collection`.** Use `collection.types`, `collection.items`
  (`len`, iterate, index, slice), `items.open_one()`, `items.open(max_items=n)`, and
  per item `item.type`, `item.metadata`, and `item.open()`. `item.metadata` is
  read-only and has storage keys removed.
- **`open()` returns plain objects.** An `Array` opens as a NumPy array, a
  `DataFrame` as pandas, a `Series` as pandas (a `DataFrame` when it has two or more
  columns), `Text` as `str`, `Artifact` as `pathlib.Path`, and `CompositeData` as a
  dict of opened slots. Package types open as their core base type.
- **Return a figure, a path, or a list of them.** Return a matplotlib figure, a path
  to an image the script wrote inside its working directory, or a list or tuple of
  those; in R a ggplot object or a path. Returning `None` or anything else fails the
  run.
- **Bind by `target_id`, never by label.** Get the target from `list_plot_targets`
  and let `scaffold_plot` write `plot.yaml`. A plot never becomes a workflow node,
  never edits a workflow, and never produces data or lineage.
- **Plots read whole items under a size limit.** `open()` loads an item fully and
  refuses inputs above the limit (64 MiB per input by default, 512 MiB at most).
  For GB-scale data, open fewer items or add a block upstream that reduces the data,
  and plot that block's output.
- **Plot two outputs through one composite output.** A plot binds to one port. Combine
  outputs into a `CompositeData` type with `scistudio-write-type` and a merge block,
  then plot the merged output.
- **A figure that must be kept is a block output.** The plot's files are a preview
  cache that the next run overwrites. For a saved, reproducible figure, write a block
  that produces an `Artifact`.
- **Look at the figure before reporting.** Check it for overlapping legends or labels
  and cut-off or unreadable text. Fix the script and run again until it reads
  cleanly.
