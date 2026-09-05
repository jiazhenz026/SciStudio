# Packaged-notebook example — from a session to a block

[find_peaks.ipynb](find_peaks.ipynb) is an exploration notebook, and
[block.py](block.py) is the block declaration packaging wrote from it. Together
they are what a step looks like when **nobody knew the computation before
looking at the data**.

## When to choose this shape

Reach for a packaged notebook when neither you nor the user can yet say what the
step does. The threshold in `find_peaks.ipynb` is `median * 1.5` — a number
nobody could have written before seeing the readings. Guessing at a Python block
would have produced a file nobody could check; the notebook let the user watch
each cell before any of it became a block.

Once the computation *is* understood, write the block directly
([process-scale-array/](../process-scale-array/) is the shape for that). A
packaged notebook is not a better default; it is the answer to not knowing yet.

## The three helpers

They are the only SciStudio-specific lines the notebook contains, and the same
lines work in both places the notebook runs — that is the entire design:

| Helper | In the session | In the packaged block |
|---|---|---|
| `scistudio.input(name)` | the reference of the bound run's port artefact | the materialised input file for that port |
| `scistudio.load(source)` | resolves the reference through storage | reads the exchange file back |
| `scistudio.output(**names)` | registers the names; writes nothing | writes each object into its output folder |

The notebook cannot tell which mode it got, and nothing in it selects one. A
helper called with no mode set raises rather than guessing, because guessing
wrong writes a person's results into the wrong place.

## Cell conventions that matter

- **Read inputs through the port.** `scistudio.load(scistudio.input("readings"))`,
  not a hard-coded path. A path works while you watch and fails once packaged.
- **Rebind; do not mutate in place.** `df = df.dropna(...)` gives the dependency
  analysis an edge to see. `df.dropna(inplace=True)` changes the object with
  nothing to show for it, and a cell below goes stale without being marked.
- **Declare outputs in code.** `scistudio.output(peaks=peaks)` is what becomes an
  output port. A notebook that declares nothing cannot be packaged.
- **Native objects in, typed objects out.** Cells hold ordinary pandas and numpy
  values; `load` hands you a SciStudio object (call `.to_pandas()` for the
  familiar form) and `output` wraps a native object into its SciStudio type by
  construction at the boundary. See
  `.scistudio/agent-reference/data-types.md`.
- **Call a block when one already does the job**, rather than reimplementing it
  in a cell.

## What packaging writes

`block.py` above is generated, not hand-written. Notice:

- **It is a Code Block.** Packaging does not invent a new kind of node — a Code
  Block already runs a notebook through `nbconvert` with exchange folders for its
  ports, so that is what a packaged notebook is.
- **The ports come from the notebook.** Inputs are its `scistudio.input`
  declarations, outputs its `scistudio.output` declarations, each typed from the
  object bound at packaging time.
- **`slice_cells` is the backward slice** of the declared outputs, in written
  order. The run executes exactly those cells; the notebook on disk stays whole,
  so reopening it shows the user the notebook they wrote.
- **`version` is the notebook commit**, so the block's own version tracks the
  notebook rather than the distribution.
- **`on_new_input = "replay"`** runs the packaged cells on new data without
  pausing. Set to `"ask"`, the block pauses on new input and the user confirms a
  notebook commit in the Explore tab before the compute phase runs.

**Do not edit `block.py`.** Edit the notebook beside it and package again;
packaging replaces both files in place.

## Packaging refuses, and says why

A slice that would not reproduce what the user saw must not become a block.
Packaging refuses — naming the cells — when the slice contains a never-run,
stale, or out-of-order cell, when it has an unresolved read, when it calls an
interactive block, or when the notebook declares no output at all. Run the
packaging check before packaging and read the report; "packaging failed" with no
cell names is not something anyone can act on.

## Try it

Open a session over the block output or file you want to work from, write the
cells, run the packaging check, then package. The block appears in the palette
with the ports the notebook declared.
