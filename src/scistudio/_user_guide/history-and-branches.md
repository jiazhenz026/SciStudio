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

**Restore** puts your project back to how it was when that run executed. Use it
when a later change made things worse and you want to get back to a version that
worked. Then press Run.

Restore covers everything that makes up your pipeline: the workflow graph, every
block's parameters, your **custom blocks and scripts**, and your project notes.
That last part matters — if what broke was the code inside a block you wrote,
restoring the workflow alone would not have fixed it, so Restore brings the code
back too.

Before it does anything, SciStudio checks the version you picked against your
current setup and tells you what has moved since:

- an **input file** that changed size or was edited after that run,
- a **package version** — including SciStudio's own — that is different now.

These are warnings, not blockers; you decide whether to go ahead. If you picked
a version you saved yourself rather than one a run produced, there is no run
record to compare against, and SciStudio says so instead of pretending
everything matches.

Your current work is not lost. SciStudio commits it first, and tells you the
version it saved it as, so you can come back to it from History.

Two things Restore does **not** touch:

- **Your data files.** They are whatever is on disk now. SciStudio warns you if
  they changed, but does not roll them back.
- **Your software environment.** SciStudio itself, installed packages, and
  Python live outside your project folder. If a run stopped working because a
  package was updated, restoring the files will not fix it — which is exactly
  why the check above tells you when that is what happened.

The same **Restore** is available in the Git tab against any version in your
history, not only the ones a run produced. It behaves identically.

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
   pipeline; switch between them anytime to compare or run either.
4. If batch-2's changes turn out to be the better default, *merge into current*
   to bring them back to `main`.

## Next

- [using-the-gui.md](using-the-gui.md) — building and running the workflows you
  are versioning here
- [ai-assistant.md](ai-assistant.md) — the assistant can set up and tune these
  variants for you
