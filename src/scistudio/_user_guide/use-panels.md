# Panels: the three ways SciStudio shows data

A **panel** is a small web page that shows your data and, where the situation
allows, lets you act on it. SciStudio panels are available in three forms:

| Form | Moment | What it does |
|---|---|---|
| **Preview panel** | Looking at data | Shows one data object or collection, read-only |
| **Interactive panel** | A workflow step needs your decision | Hands one decision back to a waiting workflow |
| **MiniApp** | Exploring data before the next step is known | Runs as an app on a block output, with its own Python |

## Preview panels — looking at data

- Click any port on the canvas and its preview opens in the preview column,
  read-only. Bounded reads keep even very large data instant.
- **All Previewers**, above the preview area, lists the panels available for a
  data type.

## Interactive panels — deciding a step

- When a run pauses at an interactive block (such as the built-in ones: the **Data Router**, the **Pair
  Editor**), a dialog opens with the view the block prepared.
- Make your choice; the workflow resumes and the decision is recorded in run
  history.

## MiniApps — exploring before you know the next step

- Open on the output of a completed block and keep computing while you work,
  thanks to their own Python process.
- When the exploration settles, convert a MiniApp into an interactive block so
  the step joins the workflow. See [miniapps.md](miniapps.md).

## What's next

- [miniapps.md](miniapps.md) — create, reuse, and convert a MiniApp
- [using-the-gui.md](using-the-gui.md#previewing-data) — where previews appear in the window
- [custom-types.md](custom-types.md) — give your own data type a dedicated panel
