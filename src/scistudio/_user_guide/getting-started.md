# Getting started with SciStudio

SciStudio is a workspace for building **workflows** over scientific data: you
wire together **blocks** — load, process, analyze, save — on a canvas, run them,
and inspect the results, with an AI assistant on hand the whole time. This page
takes you from an empty project to your first run.

> **Want the AI assistant?** Install a provider (Claude Code or Codex) first —
> see [Install a provider](ai-assistant.md#before-you-start-install-a-provider).

## 1. Create a project

Everything lives in a **project** — a folder that holds your workflows, your
custom blocks, your notes, and the record of every run. Create one from the
start screen (or open an existing one). Inside, you will find:

| Area | What it is |
|---|---|
| **Canvas** | The center, where you build workflows by placing and wiring blocks. |
| **Block palette** | The list of available blocks (built-in + any installed packages) you drag onto the canvas. |
| **Parameter panel** | Appears when you select a block; shows that block's settings. |
| **Bottom panel** | Tabbed: run **logs**, **plots**, **run history**, and **git** branches. |
| **Preview** | Shows the data on any port you click. |
| **AI chat** | The embedded assistant — ask it to build, fix, or explain things. |

If you are new to SciStudio, the start screen can also show **Run Your First
SciStudio Workflow**. It creates a real tutorial project with a small
fluorescence table, then walks you through creating a normalization custom
block, building and running the workflow, creating a plot card, and reviewing
run history. You can dismiss the prompt, hide it permanently, or restart the
tutorial later from the start screen when the prompt is available.

## 2. Build a small workflow

A workflow is a graph of blocks. Let's build the simplest useful one: **load a
file → transform it → save the result.**

1. **Add a Load block.** Drag **Load** from the palette onto the canvas. Select
   it; in the parameter panel pick the data type (e.g. `DataFrame`) and the file
   to read.
2. **Add a transform.** Drag in a processing block — a built-in one, a block
   from an installed package, or one you wrote yourself (see
   [writing-blocks.md](writing-blocks.md)). Wire **Load**'s output port to its
   input port. The canvas only lets you connect ports whose types are
   compatible, so you cannot wire a table into an image block by mistake.
3. **Add a Save block.** Drag in **Save**, wire the transform's output into it,
   and set where to write.

That three-block pipeline is a complete workflow. The full mechanics of the
canvas — palette, wiring, parameters, variadic ports — are in
[using-the-gui.md](using-the-gui.md).

## 3. Run it

Run the workflow. The bottom panel's **logs** tab streams progress; each node
shows its status on the canvas (running, done, failed). When it finishes, the
output files are written and every port is filled with data you can inspect.

If something fails, the logs and the node status tell you where; the AI
assistant can read the same logs and help you fix it.

## 4. Look at the data

Click any port — input or output — to open its **preview**. SciStudio shows a
bounded view of the data without loading the whole thing into memory, so even a
very large object previews instantly. Tables show as tables, images as images,
spectra as plots. See [previewing](using-the-gui.md#previewing-data) and, to make
your own quick figures, [writing-plots.md](writing-plots.md).

## 5. It is all recorded

Every run is saved. The **run history** remembers what you ran, with which
parameters, and lets you restore or re-run it later; **branches** let you keep
several variants of a pipeline side by side. See
[history-and-branches.md](history-and-branches.md).

## Where to go next

| You want to… | Read |
|---|---|
| Learn the canvas, running, and previews in depth | [using-the-gui.md](using-the-gui.md) |
| See every built-in block and what it does | [built-in-blocks.md](built-in-blocks.md) |
| Re-run past work; keep pipeline variants on branches | [history-and-branches.md](history-and-branches.md) |
| Get the AI assistant to do the work | [ai-assistant.md](ai-assistant.md) |
| Make a quick plot of a result | [writing-plots.md](writing-plots.md) |
| Write your own block | [writing-blocks.md](writing-blocks.md) |
| Make your own data type | [custom-types.md](custom-types.md) |

You rarely have to do any of this by hand — the [AI assistant](ai-assistant.md)
can build workflows, write blocks and plots, and tune parameters for you. These
pages are here for when you want to understand or do it yourself.
