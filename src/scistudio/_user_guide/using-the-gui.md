# Using the canvas: build, run, preview

This page covers the day-to-day of working in SciStudio: building a workflow on
the canvas, running it, and looking at the results. It is the deep version of
[getting-started.md](getting-started.md).

## Building a workflow

A workflow is a graph of **blocks** connected by **wires**. You build it by
dragging blocks from the palette and connecting their ports.

### The palette

The block palette lists everything you can use: the **built-in blocks** that ship
with SciStudio (see [built-in-blocks.md](built-in-blocks.md)), the blocks from any
**installed packages** (imaging, LC-MS, spectroscopy, …), and any **custom
blocks** you have written in this project's `blocks/` folder. Blocks are grouped
by category and subcategory. Drag one onto the canvas to add it as a node.

### Ports and wiring

Each block has typed **ports** — inputs on one side, outputs on the other. You
connect an output port to an input port by dragging a wire between them.

The key thing: **wires are type-checked.** A port declares which data types it
accepts, and the canvas only lets you connect compatible ports — you cannot wire
a table into a block that expects an image. A package type flows into a port that
accepts its parent type (a `Spectrum` into a `Series` port), but not the other
way around. This is what stops whole classes of mistake before you ever run.

Every wire carries a **Collection** — an ordered batch of same-type items — not
just a single value. Scientific work is batch work, so a port that looks like it
carries "an image" actually carries "a batch of images"; a single value is just a
batch of length one.

### Parameters

Select a block and the **parameter panel** shows its settings. These are defined
by the block and render automatically: a number field, a dropdown of choices, a
file picker, a text area. Set them here; they are saved with the workflow.

### Variadic ports and the port editor

Some blocks let you decide their ports yourself — the **Code Block**, **App
Block**, and **AI Agent** all do. These show a **port editor** in their panel
where you add named input and output ports and choose each port's type. Use it
when a script or app takes several inputs or produces several outputs.

### Sub-workflows and annotations

A **Sub-Workflow** block references another workflow file as a single node, so
you can build a big pipeline out of smaller reusable ones. **Annotation** notes
let you label regions of the canvas to keep a large workflow readable.

> You never have to edit the workflow file by hand. The canvas writes a
> validated workflow definition for you, and the [AI assistant](ai-assistant.md)
> can build or modify a whole pipeline from a description.

## Running a workflow

Run the workflow from the toolbar. As it executes:

- **Each node shows its status** on the canvas — waiting, running, done, failed,
  or cancelled.
- **The logs tab** (in the bottom panel) streams progress and any messages a
  block prints, so you can watch what is happening.
- **You can stop a run.** Cancelling stops the workflow; blocks that were already
  done keep their results.

### Interactive blocks

A few blocks **pause and ask you for input** mid-run rather than running straight
through. The **Data Router** lets you drag items from several inputs to several
outputs; the **Pair Editor** lets you reorder items so they line up correctly.
When one of these runs, it opens its panel and waits for you, then continues.

External-app blocks behave similarly: an **App Block** hands off to a program
like Fiji and waits for you to finish there; the **AI Agent** block spawns an
assistant in a terminal tab and waits for it to produce the declared outputs.

## Previewing data

Click any port — input or output, before or after a run — to open its
**preview**. This is how you actually look at your data.

The preview reads only a **bounded sample** of the object, never the whole thing,
so even a 100 GB image or a million-row table previews instantly and never
exhausts memory. What you see is tailored to the type:

- a **table** renders as a scrollable table,
- an **array/image** renders as an image viewer,
- a **series/spectrum** renders as a line plot,
- a **package type** uses the previewer its package ships (a spectrum viewer, an
  image viewer with channels, …).

If a type has no special previewer, SciStudio falls back to a sensible generic
view. Previews are read-only — they never change your data.

### Quick plots

When you want a figure that is not one of the built-in previews — a custom
matplotlib/seaborn/ggplot chart of an output port — write a **plot**. A plot is
preview-only (it is not a workflow block) and shows in the **plots** tab. See
[writing-plots.md](writing-plots.md).

## Next

- [built-in-blocks.md](built-in-blocks.md) — the blocks you build with
- [history-and-branches.md](history-and-branches.md) — re-run and branch your work
- [ai-assistant.md](ai-assistant.md) — have the assistant do it for you
