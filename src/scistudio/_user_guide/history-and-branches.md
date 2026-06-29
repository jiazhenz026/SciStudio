# Run history and branches

Science is iterative: you run a pipeline, change something, run it again, compare.
SciStudio keeps two tools for that in the bottom panel — **Run history**, which
remembers every run so you can go back to one, and **Branches**, which lets you
keep several variants of a pipeline side by side.

## Run history

Every time you run a workflow, SciStudio records it. The **Run history** tab
(bottom panel) lists your past runs, newest first. Each entry shows its status
(completed / failed / cancelled / running), when it ran, the workflow, how long
it took, and how many blocks it had.

### Looking inside a run

Click a run to open its detail. You see every block that executed, and expanding
a block shows:

- the **exact parameters** it ran with (resolved, including defaults),
- its **inputs and outputs** (which data objects, of which types),
- any **error** if it failed.

So a run is a complete, inspectable record of *what happened* — not just the
result, but the settings and data that produced it.

### Going back to a previous run

This is the point of keeping history: you can return to any past run.

- **Restore workflow.** Restores the workflow to exactly how it was when that run
  executed — the graph and every block's parameters. Use it when a later change
  made things worse and you want to get back to a version that worked.
- **Re-run.** Creates a fresh run from a past run's recorded workflow and
  parameters. Before it does, SciStudio checks whether anything has drifted — an
  input file that changed on disk, or a different package version in your
  environment — and warns you, so you know whether the re-run will reproduce the
  original result. The new run is linked to the one it came from.

Note what is and is not restored: the **workflow and its parameters** are
restored from the record; your **input data files** are whatever is on disk now
(SciStudio checks them and warns if they changed, but does not roll them back).

### Export methods

From a run you can **Export methods** — a ready-to-read Markdown description of
the workflow and the parameters it used, to copy or download. It is meant for
writing up what you did (a methods section, a lab note) without retyping it.

## Branches

A run records the past. A **branch** lets you keep more than one *present*.

The common situation: you have a pipeline, and you want to try it **two ways** —
two batches of data, two sets of processing parameters, or the same blocks in a
slightly different order — and switch between them easily without losing either.
That is exactly what branches are for. (If you have used git, these are git
branches; you do not need to know git to use them.)

### How it works

The **Branches** control lives in the **Git** tab of the bottom panel, showing
your current branch.

- **Create a branch.** From the branch menu, *Create branch…*, give it a name
  (e.g. `batch-2` or `stronger-smoothing`). It branches from where you are now
  and switches you onto it. Changes you make now — different parameters, a
  reordered pipeline — live on this branch.
- **Switch branches.** Pick another branch from the menu to switch to it; the
  canvas reloads to that branch's version of the workflows. If you have unsaved
  changes when you switch, SciStudio **saves them for you automatically** (and
  tells you, so you can recover them) — you never lose work by switching.
- **Compare and combine.** When a variant works out, you can **merge** a branch
  into your current one; the menu has *Merge into current*.

### What a branch covers

A branch tracks the things that define your pipeline: the **workflow files**,
your **custom blocks**, and your **project notes**. It does **not** touch your
**past runs** (those are kept permanently in run history, independent of
branches) or your **input data files**. So switching branches changes *the
pipeline*, while your run history and your data stay put.

### A worked example

You ran a pipeline on **batch 1** and it looks good. Batch 2 needs a higher
smoothing setting and an extra normalization block.

1. Create a branch `batch-2` and switch to it.
2. On `batch-2`, raise the smoothing parameter and add the normalization block.
3. Run it. Now `main` has the batch-1 pipeline and `batch-2` has the batch-2
   pipeline; switch between them anytime to compare or re-run either.
4. If batch-2's changes turn out to be the better default, *merge into current*
   to bring them back to `main`.

## Next

- [using-the-gui.md](using-the-gui.md) — building and running the workflows you
  are versioning here
- [ai-assistant.md](ai-assistant.md) — the assistant can set up and tune these
  variants for you
