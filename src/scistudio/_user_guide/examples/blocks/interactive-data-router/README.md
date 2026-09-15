# Interactive block example — the Data Router

`DataRouter` ([data_router.py](data_router.py)) is SciStudio's built-in **Data Router**
block: the workflow runs until it reaches this block, **pauses**, opens a
drag-and-drop window, and waits. The user drags each input item onto the
output port it should leave by; the block resumes, routes the items exactly
as assigned, and the decision is part of the run's record. No code is written
for any specific routing — the same block merges, splits, or re-sorts items
across branches.

## The four declarations of an interactive block

An interactive block is declared completely or not at all — the registry
rejects a block that has only some of these (see the comments on the class
attributes in [data_router.py](data_router.py)):

| Declaration | What it does |
|---|---|
| `InteractiveMixin` | Adds the pause/resume contract to the block. |
| `execution_mode = ExecutionMode.INTERACTIVE` | The run pauses at this block until a decision arrives. |
| `interactive_panel = PanelManifest(panel_id=...)` | Names the panel the frontend opens while paused — here the built-in `core.interactive.data_router` panel ([panels example](../../panels/core.interactive.data_router/)). |
| `prepare_prompt(...)` | Builds the plain-JSON view the panel renders: here the input ports, every item with a human label, and the output ports. |

## The two halves of the run

1. **`prepare_prompt` runs before the pause**, in an isolated worker. It sees
   the full inputs and returns plain JSON only — no data objects, no
   references — describing what the user will decide over.
2. **`run` runs after the user confirms.** The panel's decision arrives as
   `config.get("interactive_response", {})`; here it is `assignments`, a
   mapping of output port name to item refs. The outputs follow from the
   inputs, the config, and that decision alone — nothing the user did in the
   window is needed beyond the JSON.

Notice also the **variadic ports**: `variadic_inputs`/`variadic_outputs` let
the user add as many ports as the routing needs (`min_input_ports`/
`min_output_ports` bound them), and `get_effective_output_ports()` reads the
ports the user actually configured.

## The paired panel

The window the user drags items in is
[panels/core.interactive.data_router/](../../panels/core.interactive.data_router/) —
the interactive-panel example. Read the two together: this file decides *what
the panel is offered* (`prepare_prompt`) and *what happens with the answer*
(`run`); the panel folder decides *how the decision looks and is submitted*.

## Try it

Add a Data Router node between two branches, run, and the run pauses on it.
Drag every item to an output, press **Confirm**, and each output port carries
the Collection you built.
