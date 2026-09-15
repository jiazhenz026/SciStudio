# The SciStudio window

This page is a map of the SciStudio window: what each region is for and where
to find things. For hands-on teaching — building a workflow step by step — use
the tutorials in the **Learning Center** ([learning-center.md](learning-center.md))
instead; this page tells you what the regions of the window are.

## The layout

The desktop window has five regions, each described below: the **toolbar**
along the top, the **left rail** with its **sidebar**, the **stage** in the
center (with the bottom **tab bar** beneath it), and the **preview column** on
the right.

In the **AI browser layout** (when SciStudio runs for an external AI app), the
same regions rearrange: the icon rail and sidebar move to the **right** side of
the window, and the preview column disappears — the **Preview** card inside the
sidebar plays its role instead.

## The toolbar

The bar along the top of the window:

| Control | What it does |
|---|---|
| Project menu | The open project; switch between recent projects here. |
| **New** | Creates a new project item: workflow, custom block, data type, MiniApp, note, plot, or package. |
| **Import** | Bring an existing workflow or file into the project. |
| **Save** | Save the current workflow or file. |
| **Run** | Run the workflow on the canvas; shows **Running** while it executes. |
| **Bring in my work** | Import a Jupyter notebook or past analysis and have the AI turn it into a workflow. |
| **Packages** | Install and update block packages. |
| **Learning Center** | Tutorials, tips, and the user guide's Reading tab. |
| Layout toggle | Switch between the desktop and AI browser layouts. |

## The left rail and the sidebar

The narrow **icon rail** at the far left never resizes and stays visible even
when the sidebar is collapsed — clicking an icon selects what the **sidebar**
next to it shows. You can drag the icons (or press Alt+ArrowUp / Alt+ArrowDown
on a focused icon) to reorder them; the order is remembered on this computer.

| Rail icon | The sidebar shows |
|---|---|
| **Blocks** | The block palette — every block you can drag onto the canvas, with search and category chips. |
| **Workflows** | The project's workflow files; the one on the canvas is highlighted. |
| **MiniApps** | Your MiniApps — interactive data explorers you can open on a block's output or create with the AI assistant (see [miniapps.md](miniapps.md)). |
| **Data types** | The type catalogue — the data types known to this project and their fields. |
| **Data** | The project's data folders (raw, processed, zarr, parquet, artifacts, exchange); double-clicking a file opens a preview tab. |
| **Project** | The whole project as a file tree. |

The sidebar is resizable and collapsible; collapse it when you want the canvas
full width.

## The stage: tabs, canvas, and MiniApps

The center of the window is the **stage**:

- The **tab bar** above it holds one tab per open workflow (plus file tabs for
  code and previews), so you can keep several workflows open side by side.
- The **canvas** shows the active workflow as a graph of blocks and wires.
  Selecting a block shows its settings in the Config tab of the bottom panel.
- **MiniApps** run in their own layer over the stage: an open MiniApp keeps
  running (its Python included) until you close its tab, whether or not it is
  the one on screen.

## The bottom tab bar

The panel along the bottom of the stage holds tabs for the workflow-wide
surfaces. It is resizable, collapsible to just its tab strip, and can be
pinned so it stays open.

| Tab | What it shows |
|---|---|
| **AI Chat** | The embedded assistant (desktop layout; hidden in the AI browser layout, where the AI app's conversation plays this role). |
| **Config** | The selected block's parameters and settings. |
| **Logs** | The run log; the tab badge counts unread entries while you work elsewhere. |
| **Terminal** | A terminal session inside the project. |
| **Plots** | The project's plot cards. |
| **History** | Run history — what ran, with which parameters, and restore points. |
| **Git** | Branches, commits, and merges for the project's version control. |

## The preview column

The narrow column on the right exists only in the desktop layout.

### Previewing data

Click any port on the canvas — input or output, before or after a run — and its
**preview** opens here. The preview reads only a **bounded sample** of the
object, never the whole thing, so even a very large dataset previews instantly.
What you see depends on the data's type: a table renders as a scrollable table,
an image as an image viewer, a spectrum as a line plot, and a package type uses
the view its package ships. To make your own quick figures instead, see
[writing-plots.md](writing-plots.md); for interactive exploration, see
[miniapps.md](miniapps.md).

## Where to go next

- [learning-center.md](learning-center.md) — guided tutorials and the in-app reading tab
- [getting-started.md](getting-started.md) — the five-minute tour
- [miniapps.md](miniapps.md) — interactive data exploration
- [built-in-blocks.md](built-in-blocks.md) — every block that ships with SciStudio
- [history-and-branches.md](history-and-branches.md) — run history and git branches in depth
