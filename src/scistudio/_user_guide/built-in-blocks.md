# Built-in blocks

These blocks ship with SciStudio and are always in the palette, independent of any
installed package. They cover getting data in and out, running your own code or
external tools, and shaping batches. Each entry says what the block does, its
ports, and its main settings.

> Installed packages (imaging, LC-MS, spectroscopy, …) add many more blocks — the
> domain science. This page is only the core built-ins.

## Data in and out

### Load

Reads a file from disk into the workflow. You choose the **core type** to load it
as — `Array`, `DataFrame`, `Series`, `Text`, `Artifact`, or `CompositeData` — and
the output port takes that type, so the next block connects correctly.

- **Output:** `data` (the type you selected).
- **Settings:** the **type** to load, and the **path** to the file (or files).

### Save

Writes a data object to disk — the sink at the end of a pipeline.

- **Input:** `data` (the core type you select, matching what you wire in).
- **Settings:** the **type**, the output **path**, an optional **filename**, and
  **overwrite** on/off.

`Load` and `Save` are the bookends of most workflows. To support a file format
they do not cover, write a custom loader/saver — see
[examples/io-load-npy/](examples/io-load-npy/).

## Run your own code or tools

### Code Block

Runs a **project-local script** — Python, R, or Julia — as a workflow step,
exchanging typed data through files. You point it at a script in your project and
declare its input and output ports; SciStudio writes the inputs to files for the
script and reads its outputs back as typed data.

- **Ports:** you declare them (the port editor).
- **Settings:** the **script path**, the **interpreter**, and the declared
  inputs/outputs.

Use it to reuse code that already exists in another language. See the R example
in [examples/code-accucor-r/](examples/code-accucor-r/).

### App Block

Hands work to an **external GUI application** (Fiji, ImageJ, CellProfiler, …). It
writes your inputs to an exchange folder, launches the app, waits for the output
files, and reads them back.

- **Ports:** you declare them.
- **Settings:** the **executable** to launch, an optional output directory.

See [examples/app-fiji/](examples/app-fiji/).

### AI Agent

Runs an **AI step inside the workflow**: it spawns an assistant (claude-code or
codex) with a prompt and your inputs, and waits for it to produce the declared
outputs. Use it for judgement tasks that are hard to write as fixed code —
classifying, extracting, inferring.

- **Ports:** you declare them (each output names where the agent writes its
  result).
- **Settings:** the **user prompt**, the **provider**, and the **permission
  mode** (Ask / Bypass).

See [ai-assistant.md](ai-assistant.md) for a worked metadata-inference example.

## Compose and reuse

### Sub-Workflow

References **another workflow file** as a single node, so you can build large
pipelines out of smaller reusable ones. Its ports come from the inputs and
outputs the referenced workflow exposes.

- **Settings:** the **workflow file** to reference.

## Shape your batches

Every port carries a Collection (a batch). These blocks rearrange batches.

### Merge Collection

Concatenates several same-typed Collections into one — e.g. combine batches from
two `Load` blocks into a single stream.

- **Inputs:** 2–8 Collections of the same type.
- **Output:** the merged Collection.

### Data Router

An **interactive** block: when it runs, it opens a panel where you drag items
from several inputs to several outputs, deciding by hand where each item goes.
Use it to split or regroup a batch on a judgement you make at run time.

- **Ports:** you declare the inputs and outputs.

### Pair Editor

Another **interactive** block: it lets you **reorder** items within Collections so
that they line up correctly for index-based pairing (item 1 with item 1, etc.).
Use it when two batches need to be matched up but arrived in different orders.

- **Inputs/outputs:** 2–8, mirrored.

## Next

- [using-the-gui.md](using-the-gui.md) — placing and wiring these blocks
- [writing-blocks.md](writing-blocks.md) — when you need one that does not exist
  yet
