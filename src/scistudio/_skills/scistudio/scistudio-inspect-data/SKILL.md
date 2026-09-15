---
name: scistudio-inspect-data
description: |
  Use when the user wants to look at intermediate or output data — preview a
  slice of an array, peek at the first rows of a table, check what a data
  reference holds, or trace where it came from. NOT for debugging failed runs
  (use scistudio-debug-run) or for building an interactive view (use
  scistudio-write-miniapp, or scistudio-write-panel for a reusable per-type view).
---

# scistudio-inspect-data

## 1. What data looks like in SciStudio

Data in a workflow travels as references (`StorageReference`), not as in-memory
payloads: blocks emit references, edges carry them, and data is loaded only
inside a block's `run`. Every port carries a `Collection`. As an agent you never
load data into your own turn; you ask the MCP tools about a reference — what it
is, a bounded preview of its contents, and the lineage that produced it.

The user sees the same data in the GUI's preview column, where preview panels
show the real values of each type. When the user wants to explore a result
repeatedly — move a threshold, compare settings — offer a MiniApp
(`scistudio-write-miniapp`) instead of a series of previews.

## 2. Steps to inspect data

1. **Find the reference.** For a block's result, call
   `get_block_output(run_id, block_id, port)`; for datasets stored by earlier
   runs, call `list_data`. Files the user added (such as `data/raw/counts.csv`)
   are not stored data; find them with `list_directory` or `search_files`.
2. **Learn what it is.** Call `inspect_data(ref)` for its type chain, backend,
   path, format, and size.
3. **Look at the contents.** Call `preview_data(ref, fmt)` for a bounded view.
4. **Trace its origin** when one of the cases in "When to use lineage" applies:
   call `get_lineage(ref)`.
5. **Report.** Quote the values the tools returned, say when a preview is
   truncated, and point the user to the preview column to see it themselves.

## 3. Anti-patterns

- Describing a shape, type, or value without having called the tools.
- Reading a stored reference's files through the shell to load the data.
- Presenting a truncated or downsampled preview as the full data.
- Guessing provenance instead of calling `get_lineage`.
- Claiming to have seen what the GUI shows without GUI evidence
  (`scistudio-use-gui` or `screenshot_gui`).

## 4. Defaults, tool sequence, and failure handling

**`get_block_output(run_id, block_id, port)`** returns a `GetBlockOutputResult`:
`ref` (the StorageReference wire dict to pass on), `type` (`type_chain` and
`type_name` when recorded), and `produced_at` (an ISO timestamp, or empty when
unrecorded). A block that emits a Collection returns the Collection reference;
inspect it to see its items.

**`preview_data(ref, fmt)`** dispatches on the reference's type chain; `fmt` is
only a preferred format (`table`, `png_base64`, `chart`, `text`, `artifact`).
Bounds are fixed by the tool: a table's first 100 rows, an array as a PNG
thumbnail clamped to 256×256, a series' first 200 entries, a text's first 4096
characters, and an artifact's size with inline image data only under the 8 MiB
cap. The result's `truncated` flag says whether content was omitted.

**When to use lineage.** Lineage records, for every workflow output, which block
produced it from which inputs, back to the source files. Call `get_lineage(ref)`
when:

- the user asks where a result, figure, or number came from;
- a value looks wrong, to find the upstream step and input that produced it
  before inspecting those;
- two outputs that should match differ, to see whether they came from different
  inputs or steps;
- you describe how a result was made (a methods summary, a report), so the
  description matches what actually ran instead of what the workflow file says
  now.

Lineage covers data produced by workflow runs. Files written by a MiniApp, a
command, or by hand have no lineage; say so instead of guessing. An empty result
with a `note` means the reference could not be resolved in the lineage store.

**Tool sequence.**

```
get_block_output(run_id, block_id, port)   # or list_data for stored datasets
inspect_data(ref)
preview_data(ref, fmt="table")             # choose fmt by type
get_lineage(ref)                           # see "When to use lineage"
```

**When something fails.** A missing path means the data was removed or the run's
outputs were not kept; check the run with `get_run_status` and rerun the workflow
if needed. When a block output is absent because the run failed, load
`scistudio-debug-run`.

## 5. Contracts and routing

**Contracts (MUST follow).**

- Data types and their access methods:
  `user-guide/api-reference/scistudio.core.types.md`.
- Tool result fields: the live MCP tool schemas.

**Agent reference.**

- How each data type is read and constructed:
  `.scistudio/agent-reference/data-types.md`.
- Types from installed packages: `.scistudio/agent-reference/package-discovery.md`.

**User guide.**

- How the GUI previews each type: `user-guide/using-the-gui.md`.

**Related skills.**

- `scistudio-debug-run`: an expected output is missing because a run failed.
- `scistudio-write-plot`: the user wants a figure of an output.
- `scistudio-write-miniapp`: the user wants to explore a result interactively.
- `scistudio-use-gui`: confirming what the GUI shows.

## 6. Examples

**"What's in the output of the normalize step?"**

```
out = get_block_output(run_id="<run_id>", block_id="norm", port="table")
inspect_data(ref=out.ref)
preview_data(ref=out.ref, fmt="table")
```

Report from the returned fields, for example: "The `table` output is a DataFrame
stored as Parquet (1.2 MB); the preview shows its first 100 rows."

**"Where did this come from?"** Call `get_lineage(ref=...)` and describe the
returned nodes (each data object with the block that produced it) and edges in
order from the source files to the result.

## 7. Available tools

The live MCP tool list is the source of truth; these are the tools this task
uses.

| Tool | What it does | When to use it |
|---|---|---|
| `get_block_output` | Resolves one block port's output from a run. | To get the reference behind a block's result. |
| `list_data` | Lists datasets stored by runs under `data/zarr/`, `data/parquet/`, and `data/artifacts/`. | When the user asks what results the project holds. |
| `inspect_data` | Returns a reference's metadata without loading it. | First, to learn what a reference is. |
| `preview_data` | Returns a bounded preview of stored data. | To look at contents. |
| `get_lineage` | Returns the lineage ancestors of a reference. | For provenance questions, unexpected values, differing outputs, and methods descriptions. |
| `get_run_status` | Returns a run's state and errors. | When an expected output is missing. |
| `open_gui` | Returns the address of the running GUI. | When the user wants to see the data in the preview column. |
