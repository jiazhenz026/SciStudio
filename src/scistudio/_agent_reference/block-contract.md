# Block contract

A block is a class with class-level metadata, typed ports, a `config_schema`, and
a body. Imports come from canonical roots ([public-api.md](public-api.md)).

## Choose the base class

| Base (`scistudio.blocks.*`) | Override | Use when |
|---|---|---|
| `base.Block` | `run()` | general work; you handle the whole batch |
| `process.ProcessBlock` | `process_item()` | one item → one item, item count unchanged |
| `io.IOBlock` / `io.SimpleLoader` / `io.SimpleSaver` | `load()`/`save()` or `load_file()`/`save_file()` | read/write files |
| `app.AppBlock` | (class vars only) | hand off to an external GUI/CLI app |
| `code.CodeBlock` | (config only) | run a project-local script |

`AIBlock` / `SubWorkflowBlock` are **not** author extension points
([public-api.md](public-api.md)). `base_category` is **inferred** from the parent
class — never set it as a ClassVar (silently ignored).

## Interactive blocks (optional)

Interaction is a **capability**, not a separate base class. Any category can
pause mid-run, open a window onto its real input data, take a data-dependent
decision from the user, and compute outputs from it. Use it when a value can
only be judged by looking at the specific data; it is one option, not a default.
Mix in `InteractiveMixin`, set
`execution_mode = ExecutionMode.INTERACTIVE`, declare an `interactive_panel`,
and override `prepare_prompt`. Import all four from `scistudio.blocks.base`
(`InteractiveMixin`, `ExecutionMode`, `PanelManifest`, `InteractivePrompt`).

- `prepare_prompt(self, inputs, config) -> dict | InteractivePrompt` — runs
  first, in its own worker, with the block's full input collections. Reduce the
  real data to a small, **plain-JSON** view the window renders (a downsampled
  trace, a summary table, a list of choices); the runtime rejects a non-JSON
  payload. A bare dict is shorthand for `InteractivePrompt(panel_payload=...)`.
- `run` / `process_item` — runs after the user confirms; reads the panel's JSON
  decision from `config.get("interactive_response", {})` and computes outputs.

Two panel options:

- **Reuse a built-in panel** when the interaction is routing or pairing — no
  frontend code: `PanelManifest(panel_id="core.interactive.data_router")` (drag
  items from N inputs to M outputs) or `"core.interactive.pair_editor"` (reorder
  items to fix pairing across collections).
- **Write your own panel** for anything data-specific (pick a baseline region on
  a trace, click a peak, set a threshold against a preview). A panel is a
  **directory holding a `panel.json` declaration and one self-contained
  `index.html`** — markup, styles and script in one file, no build step. It
  lives in a panel tier, not beside the block:

  ```python
  interactive_panel = PanelManifest(panel_id="myproj.pick_baseline")
  ```

  The id is the panel directory's name, and that is the whole declaration a
  block makes: a block-declared panel is **producing** by default, because it
  exists to take a decision back.

  Do not hand-write the directory. Call
  `scaffold_panel(panel_id=..., target_types=[], capability="producing")` —
  `target_types` is empty because a block-declared panel is addressed by the
  block, not by the type of the data. It writes `panel.json`, a working
  `index.html`, and a `harness.html` you open in a browser to watch the panel
  render and see what it emits. Then `reload_panels` registers it.

  The panel is mounted in a sandboxed frame and speaks one `postMessage`
  contract: it receives `init` (carrying what `prepare_prompt` returned as the
  target), answers `ready`, and commits the user's decision with `emit`. For a
  block pause the emission is *run* in a bare namespace holding only
  `scistudio.output`, and the single `scistudio.output(...)` call's keyword
  arguments become `config["interactive_response"]`:

  ```python
  selection = {"start": 402.0, "end": 431.5}
  scistudio.output(baseline=selection)
  ```

  The whole contract — the declaration fields, both message directions, the
  tiers, and what an emission may contain — is in
  [panel-contract.md](panel-contract.md). Read it before writing the document.

The registry rejects an interactive block that declares the mixin without the
mode (or vice versa), omits `prepare_prompt`, or has no valid `interactive_panel`.

## Hand off to an app (AppBlock) or a script (CodeBlock)

- **AppBlock** (`scistudio.blocks.app`) — hand the step to a desktop GUI/CLI
  program. Set `app_command` (the executable) and declare output ports
  (optionally keyed by file extension); the block stages inputs to an exchange
  dir, launches the tool, and packs the result files it writes back into
  outputs. Override `prepare_launch(exchange_dir, output_dir, config)` only for
  tools that need a generated config file and a custom argv. Reach for it when a
  real tool (Fiji, a converter, an analysis GUI) already does the job better
  than code.
- **CodeBlock** (`scistudio.blocks.code`) — run a project-local script (Python,
  R, shell, MATLAB, notebook) as a step without rewriting it as a block. The
  user keeps their script; the block exchanges declared inputs/outputs through
  files located by `SCISTUDIO_*` env vars. Reach for it to wrap an existing
  analysis the user already trusts.

## Metadata (ClassVars)

```python
name: ClassVar[str]            # palette + node header
description: ClassVar[str]     # one line
version: ClassVar[str] = "0.1.0"
subcategory: ClassVar[str] = ""        # palette grouping
type_name: ClassVar[str] = "<ns>.<id>" # stable id for package blocks
ui_color: ClassVar[str | None] = None  # optional CSS hex
ui_icon: ClassVar[str | None] = None   # optional Lucide icon name
```

## Ports

```python
input_ports: ClassVar[list[InputPort]] = [
    InputPort(name="input", accepted_types=[Array], required=True, description="..."),
]
output_ports: ClassVar[list[OutputPort]] = [
    OutputPort(name="output", accepted_types=[Array]),
]
```

`accepted_types` MUST be the **most specific applicable** type, never `[]` or bare
`DataObject` for a non-generic block (preview, type-checking, and suggestions all
dispatch on it). Multiple, well-named outputs are encouraged. Call `list_types`
first.

## config_schema

JSON Schema rendering the parameter panel; read with `config.get(name, default)`.
Use `title`, `enum`, `default`, `minimum`/`maximum`. The registry **MRO-merges**
schemas across the inheritance chain — do not duplicate parent fields; bump
`version` on an incompatible change.

**Expose tunables here, never hard-code them.** Any value a user might reasonably
want to choose (a processing parameter, threshold, window, method) belongs in
`config_schema` with a `title`/`description` and a sane `default`, read via
`config.get(...)` — not as a buried constant in the body.

## User-facing labels

The GUI shows the user only the text on these fields — fill them all with short,
clear language so a non-programmer can tell ports and parameters apart:

- block `name` (a real label) + one-line `description`;
- each `InputPort`/`OutputPort` — a distinct `name` **and** a `description` of
  what flows there (not three unlabeled `Image` ports);
- each `config_schema` property — `title` (panel label) **and** `description`
  (what it does / units / when to change it);
- concise code comments explaining the *why*.

## Body

```python
# Block: whole batch
def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
    ...
    return {"output": self.map_items(fn, inputs["input"])}

# ProcessBlock: one item (base loops the batch; ~80% of blocks)
def process_item(self, item, config: BlockConfig, state=None):
    ...
    return new_item   # one DataObject
```

`run()` MUST return `dict[str, Collection]` keyed by output port name. Read with
`item.to_memory()` / `to_pandas()` / `to_numpy()`; build with the `data=`
constructor ([data-types.md](data-types.md)).

## Collection helpers (on `self`)

`map_items(fn, coll)` (low-memory), `parallel_map(fn, coll)`,
`pack(items, item_type=T)`, `unpack(coll)`, `unpack_single(coll)`. Every port
carries a `Collection`; a single value is length 1.

## Where it lives

Project-local: drop a `*.py` under `<project>/blocks/`; auto-discovered (reload to
refresh the registry). A panel the block opens is its own directory under
`<project>/panels/<panel_id>/`, not a file beside the block
([panel-contract.md](panel-contract.md)). Reusable across projects: ship a
package with the `scistudio.blocks` / `scistudio.types` / `scistudio.panels`
entry points.

## Before authoring (rules)

1. Call `list_blocks` and **reuse** if a block's I/O contract matches.
2. Call `list_types`; pick concrete port types.
3. After `scaffold_block`, read every `warnings[]`. After writing, `reload_blocks`
   then `run_block_tests`.
