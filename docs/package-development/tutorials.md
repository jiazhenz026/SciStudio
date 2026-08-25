# Shipping a tutorial

A package can teach its own blocks. Ship one or more **tutorials** and they
appear in the user's Learning Center alongside the ones core ships, grouped
under your package's name.

A tutorial is not a document. Each one bootstraps a real project with real data,
and a step is complete when the backend can see it happened — a node exists, a
run succeeded, a type registered, a file landed. A reader who finishes your
tutorial is holding a working project, not a page they scrolled past.

## Two paths, and you probably want the first

| You write | When | Needs Python? |
|---|---|---|
| A `tutorial.yaml` manifest | The steps are a fixed sequence, each judged by something the core vocabulary can express | No |
| A **driver** class | The logic depends on what the reader did, or a step is judged by something the vocabulary has no term for | Yes |

Start with a manifest. Reach for a driver only when a manifest genuinely cannot
say what you mean — and even then, a driver can still defer most of its steps to
the manifest's vocabulary.

## The manifest path

### Directory layout

A tutorial is a directory holding a `tutorial.yaml` and an `assets/` tree. Put
them under one parent directory in your package:

```
src/scistudio_blocks_spectroscopy/
├── __init__.py
├── tutorials/
│   ├── __init__.py
│   ├── baseline-correction/
│   │   ├── tutorial.yaml
│   │   └── assets/
│   │       ├── data/example_spectrum.csv
│   │       └── code/custom_baseline.py
│   └── peak-fitting/
│       ├── tutorial.yaml
│       └── assets/
└── ...
```

### Declare the entry point

The `scistudio.tutorials` group names the **parent** package, and core scans its
directory for tutorial subdirectories:

```toml
[project.entry-points."scistudio.tutorials"]
scistudio_blocks_spectroscopy = "scistudio_blocks_spectroscopy.tutorials"
```

Core resolves this to a directory from your distribution's metadata and **never
imports it** to list the catalogue. Opening the Learning Center reads manifests
and nothing else, so a package with a broken tutorial breaks that one entry
rather than the catalogue.

Ship the directory as package data, since the tree is deliberately not
importable:

```toml
[tool.setuptools.package-data]
scistudio_blocks_spectroscopy = ["tutorials/**/*"]
```

### Write the manifest

`manifest_version`, `id`, `title`, and `summary` are required; everything else is
optional. The published schema is
`scistudio/tutorials/schema/tutorial.schema.json` — the contract, and the thing
to validate against.

```yaml
manifest_version: 1
id: baseline-correction
title: Correcting a baseline
summary: >-
  Load a spectrum, correct its baseline, and see the difference on a plot.
order: 1

requires:
  scistudio: ">=0.3.4"
  packages: ["scistudio-blocks-spectroscopy"]
  agent: false

bootstrap:
  project_name: Baseline correction
  do:
    - copy:
        source: assets/data
        destination: data/raw

steps:
  - id: add-the-loader
    title: Load the spectrum
    route_to: canvas
    say: Drag a Spectrum Loader onto the canvas and point it at the raw file.
    done_when:
      node_exists:
        block_type: SpectrumLoader

  - id: correct-it
    title: Correct the baseline
    say: Add a BaselineCorrection block and connect the loader to it.
    done_when:
      all:
        - node_exists:
            block_type: BaselineCorrection
        - edge_exists:
            source_block_type: SpectrumLoader
            target_block_type: BaselineCorrection

  - id: run-it
    title: Run it
    say: Press Run. The corrected spectrum lands on the output port.
    done_when:
      run_succeeded: {}
```

`requires` is what makes an entry honest: a tutorial whose requirements are unmet
is listed as unavailable, saying which requirement is missing, rather than
failing once the reader is inside it.

### Conditions

`done_when` takes one vocabulary term, or an `all` / `any` of them. The terms are
core-owned and the single declaration of them is
`scistudio.tutorials.VOCABULARY`; the schema deliberately does not restate the
names. They cover nodes and edges, node configuration, runs and ports, registered
blocks/types/previewers, plots, files, git branches, library contents, and
frontend interactions.

Steps may write files into the project at any point, not only at bootstrap, and
the files are on disk before the step's text is readable — a step that says "we
wrote this block for you" cannot be read before the block exists.

## The driver path

Implement `TutorialDriver` when the manifest cannot express the tutorial's logic.
Name the class from the manifest:

```yaml
manifest_version: 1
id: adaptive-fitting
title: Fitting until it converges
summary: A tutorial whose next step depends on how the fit went.
driver: scistudio_blocks_spectroscopy.tutorials.adaptive:FittingDriver
```

!!! note "Driver is a core/package-tier field"
    `driver` is accepted only from core and package tutorials. A user-level or
    project-level manifest declaring it is rejected, naming the field and the
    tier restriction.

### The four questions

The protocol is four methods and stays four. Everything comes from the canonical
root:

```python
from scistudio.tutorials import (
    Condition, DriverContext, ProductState, StepView, WriteAction, evaluate,
)


class FittingDriver:
    def __init__(self, manifest, key):
        self._steps = list(manifest.steps)

    def step_view(self, context: DriverContext) -> StepView:
        step = self._step(context.step_id)
        return StepView(
            id=step.id,
            index=self._steps.index(step),
            total=len(self._steps),
            title=step.title,
            say=step.say,
        )

    def is_satisfied(self, context: DriverContext, product: ProductState) -> bool:
        step = self._step(context.step_id)
        if step.id == "converged":
            return self._residual_below_threshold(product)   # no term for this
        return step.done_when is None or evaluate(step.done_when, product)

    def entry_actions(self, context: DriverContext) -> tuple[WriteAction, ...]:
        return self._step(context.step_id).actions

    def advance(self, context: DriverContext) -> str | None:
        if context.step_id is None:
            return self._steps[0].id            # "the step after nothing"
        nxt = self._steps.index(self._step(context.step_id)) + 1
        return self._steps[nxt].id if nxt < len(self._steps) else None
```

Note `is_satisfied`: the driver implements the one condition the vocabulary
cannot express and hands every other step to `evaluate`. That is the intended
shape — a driver is an escape hatch for the hard step, not a reason to reimplement
the easy ones.

### What a driver does not do

Three constraints, each of which removes work rather than adding it:

- **Core owns rendering.** Whatever `step_view` returns is reduced to a plain
  `StepView` at the boundary; extra attributes and extra mapping keys are
  dropped. A driver cannot introduce a display primitive, ship a frontend asset,
  or address a surface the manifest format cannot address — and correspondingly
  never has to describe one. This is also what makes a package driver and a
  manifest tutorial indistinguishable to everything downstream.
- **The session holds the cursor.** A driver is asked about the step its
  `DriverContext` names, not about "its" current step. It persists nothing and
  survives a backend restart with no state of its own.
- **The context is not the session.** A driver reads position and location and
  cannot advance, end, or start a session.

### Optional: declaring conditions

Implement `DeclaresConditions` as well and the session can skip re-evaluating a
step on events that could not affect it. It changes how often `is_satisfied` is
called, never what the reader sees.

```python
def condition(self, context: DriverContext) -> Condition | None:
    step = self._step(context.step_id)
    return step.done_when          # None for a step the vocabulary cannot express
```

### Failure is contained

Your driver is imported only when a reader starts that tutorial. An import
failure ends that one session, naming the tutorial, and leaves every other
tutorial listed and startable.

## Stability

`scistudio.tutorials` is a canonical public root; its `__all__` is this authoring
surface and nothing else. Everything else in the package stays importable by deep
path and carries no promise — do not build against it.

The surface is `provisional` as of `0.3.4`: the condition vocabulary and the
action set are still settling, so they may change in a minor release with a
changelog note. Pin `scistudio` accordingly.

The manifest format versions itself separately through `manifest_version`. A
manifest declaring a version newer than the installed core is reported as needing
a newer SciStudio rather than as malformed.

## Where to look next

| For | See |
|---|---|
| Every public symbol, with signatures and tiers | the `scistudio.tutorials` page of the API reference |
| The manifest contract | `scistudio/tutorials/schema/tutorial.schema.json` |
| A complete worked manifest | core's `welcome-to-scistudio` tutorial in the SciStudio repository |
| Entry points, packaging, versioning | [publishing.md](publishing.md) |
