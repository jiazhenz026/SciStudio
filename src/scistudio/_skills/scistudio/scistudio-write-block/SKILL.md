---
name: scistudio-write-block
description: |
  Use when the user needs a new block: a Python class in `blocks/<name>.py`
  with typed ports, a config schema, and run logic (process, IO, app, code, or
  interactive). Call list_blocks first and reuse a block that already fits.
  Not for adding an existing block to a workflow (scistudio-build-workflow) or
  changing a node's config (update_block_config).
---

# scistudio-write-block

## 1. What a block is

A block is one typed step of a workflow: a Python class with named input and
output ports, a `config_schema` for its parameters, and a `run` that turns input
collections into output collections. Every port carries a `Collection`. A block
in `blocks/<name>.py` belongs to this project; moved to My Library, it is
available in every project.

A block can take several shapes. None is preferred; pick the one that fits, and
reach for a richer one only when it genuinely helps the user:

- **Process block** — computes outputs from inputs (`ProcessBlock`, or `Block` for
  full control of `run`).
- **IO block** — reads or writes a file format (`SimpleLoader`, `SimpleSaver`).
  Workflows never use it as a node: core `load_data` / `save_data` route to it.
- **App block** — hands the step to a desktop application (`AppBlock`). To run a
  project script, add the built-in Code Block to the workflow and configure it;
  do not write a block for it.
- **Interactive block** — pauses the run so the user makes a data-dependent
  decision in a window, then computes outputs from that decision.

## 2. Steps to write a block

1. **Check for reuse.** Call `list_blocks`; if a block's ports and config already
   match, use it and stop. Build new only when nothing fits, and say why in the
   new block's docstring.
2. **Choose types and shape.** Call `list_types` and give every input and output
   port the most fitting registered type (`Image` over `Array`, `DataFrame` over
   `DataObject`). Using `DataObject` as a port type is forbidden. Decide the shape
   (§1).
3. **Scaffold.** Call `scaffold_block(name=..., category=..., input_ports=...,
   output_ports=..., description=...)` and read every entry in `warnings`.
4. **Write the logic.** Study a similar real block with `list_block_examples` and
   `read_block_source`, then fill in `run` or `process_item` in `blocks/<name>.py`.
   Fill every `EDIT THIS` section and replace every `Describe ...` placeholder the
   scaffold left.
5. **Make it usable.** Label everything the user sees (see the table below), and
   give the block a look of its own if you like (see below).
6. **For an interactive block,** follow "Use interactive blocks" below.
7. **Load and test.** Call `reload_blocks`, confirm the block appears in
   `list_blocks`, then `run_block_tests type_name="<registered name>"` and read the
   output verbatim.
8. **Use it.** Add the block to a workflow with `scistudio-build-workflow` (an IO
   block through core `load_data` / `save_data`), run it, and confirm its outputs
   before telling the user it works.

### Make it usable — label everything the user sees

The user drives your block from the GUI, where the only thing they see is the
text you put on these fields. Fill all of them with short, clear, human language
— a non-programmer must be able to tell ports and parameters apart (three ports
all typed `Image` with no names/descriptions are unusable):

| Where users see it | Field(s) to write |
|---|---|
| Palette + node header | block `name` (a real label, not `MyBlock`) and one-line `description` |
| Each input/output port | a distinct `name` **and** a `description` (what flows here, e.g. "raw image" vs "binary mask" vs "overlay") |
| Each parameter panel field | the `config_schema` property's `title` (the label) **and** `description` (what it does / units / when to change it) |
| In the code | short, plain comments explaining the *why*, not the obvious |

Distinct names + a one-line description per port and per parameter is the bar.
A value the user may reasonably want to change usually belongs in `config_schema`
(with a `title`/`description` and a sane `default`) rather than buried as an
unreachable constant — though a hard-coded value is fine when it is intrinsic or
a convenient default. Read each parameter in `run` with `config.get("<name>")`.

**Give it a look (optional).** If you like, choose an icon and color that make the
block easy to recognise on the canvas: `ui_icon` takes a Lucide icon name that
fits what the block does (an unknown name falls back to the category icon), and
`ui_color` takes a CSS hex color. Leaving both unset uses the category default.

### Use interactive blocks

An interactive block pauses the workflow at its step, shows the user a window
built from the step's data, takes one decision, and computes its outputs from
that decision. Use it when a value can only be judged by looking at the specific
data — which items go where, where a threshold falls, which region to keep. The
decision is recorded with the run, so the step stays reproducible. For example, when the user wants to manually pick the peak when doing spectral peak picking, or when the user wants to edit segmentation labels manually after cell segmentation, it's time to use interactive blocks.

The block runs in two phases, each in its own process:

1. **Prepare the view.** `prepare_prompt(inputs, config)` turns the real inputs
   into the plain-JSON view the window needs for the decision (the candidate
   items, the table to choose from, the values of the trace). It carries real
   values, never a downsampled or sampled stand-in; the window receives only this
   view.
2. **Compute from the decision.** After the user confirms, `run` (or
   `process_item`) reads the decision from `config["interactive_response"]` and
   computes the declared outputs.

To declare one, mix in `InteractiveMixin`, set
`execution_mode = ExecutionMode.INTERACTIVE`, set
`interactive_panel = PanelManifest(panel_id="...")`, and implement
`prepare_prompt`; import all four from `scistudio.blocks.base`.

For the window, reuse a built-in panel when the decision is routing or pairing:
`core.interactive.data_router` (drag items from inputs to outputs) or
`core.interactive.pair_editor` (reorder items to fix pairing). For any other
decision, write a custom interactive panel in `panels/<panel_id>/` with
`scistudio-write-panel`, and point `panel_id` at it.

To turn a MiniApp into an interactive block, keep the MiniApp and create a
separate block and panel: build the view in `prepare_prompt`, let the panel write
back one decision, and compute reproducible outputs in `run` from that decision
and the config. The block cannot rely on the MiniApp's Python process.

## 3. Anti-patterns

- Writing a new block without calling `list_blocks` first.
- **Using `DataObject` (or an empty type list) as an input or output port type.**
  This is forbidden in every user-facing block; always use the most fitting
  registered type.
- Calling `to_memory()`, `to_numpy()`, or `to_pandas()` on GB-scale data; read it
  by region or in chunks and write large arrays with `persist_array` (see
  `block-contract.md`).
- Importing from a deep module path (`...base.ports`) or an underscore module
  (`_support`); import only from the canonical public roots.
- Subclassing `AIBlock`, `CodeBlock`, or `SubWorkflowBlock`, which are runtime base
  classes; for an AI step the user adds the built-in AI Agent block.
- Setting `base_category` in a block. Writing `base_category = "process"` has no
  effect: the category comes only from the class the block inherits.
- `run` returning anything but `dict[str, Collection]` keyed by output port name.
- Unlabelled ports and parameters, or a value the user will want to change buried
  as a constant in code.
- Skipping `reload_blocks` or `run_block_tests`.
- Placing a written IO block in a workflow as its own node instead of reading or
  writing through core `load_data` / `save_data`.
- An interactive block that declares `InteractiveMixin` without
  `execution_mode = ExecutionMode.INTERACTIVE` (or the reverse), or omits
  `prepare_prompt` or `interactive_panel`; the registry rejects it at scan time.

## 4. Defaults, tool sequence, and failure handling

**Imports.** `from scistudio.blocks.base import Block, BlockConfig, InputPort,
OutputPort`, `from scistudio.blocks.process import ProcessBlock`,
`from scistudio.core.types import Array, DataFrame, ...`.

**Scaffold categories.** `block` → `Block`, `process` → `ProcessBlock`, `io` →
`SimpleLoader` (`SimpleSaver` when only input ports are given), `app` →
`AppBlock`. `code` scaffolds a `ProcessBlock` with a warning; `ai` and
`subworkflow` are refused, because those steps are built-in blocks configured as
workflow nodes.

**Large data.** Check the input's size with `inspect_data` before writing the
logic. When it may not fit in memory (GB-scale images, stacks, or tables), never
call `to_memory()`, `to_numpy()`, or `to_pandas()` on it: read an `Array` by region
with `sel(...)` or plane by plane with `iter_over(axis)`, read any type in pieces
with `slice(...)` or `iter_chunks(chunk_size)`, and stream a large output array with
`self.persist_array(iterator, shape, dtype)`, wrapping the returned reference as
`Array(axes=[...], shape=shape, dtype=dtype, storage_ref=ref)`. Process a batch with
`map_items`, which holds one item at a time.

**IO blocks.** Declare the formats the block reads or writes as format
capabilities. After `reload_blocks`, core `load_data` / `save_data` select it by
type and file extension or by its `capability_id`, and run its code.

**By default, no extra batch handling is needed.** When you write an IO
block, inherit SimpleLoader/SimpleSaver and handle the read or write as a
single-file operation; the core automatically fans in and fans out.

**Tool sequence.**

```
list_blocks                  # reuse check — stop if a match exists
list_types                   # concrete port types
scaffold_block(...)          # read every warnings[] entry
# edit blocks/<name>.py
reload_blocks
list_blocks                  # confirm it registered
run_block_tests type_name="<registered name>"
```

Every write-class result carries `next_step`; read it and follow it.

**When something fails.** A block missing from `list_blocks` after
`reload_blocks` failed to import or register: read the reload result and fix the
reported error. When `run_block_tests` fails, read the pytest output verbatim,
fix the cause, and rerun. When the block fails inside a workflow run, load
`scistudio-debug-run`.

## 5. Contracts and routing

**Contracts (MUST follow).**

- Every public class, port, and helper signature: `user-guide/api-reference/`
  (block base classes in `scistudio.blocks.base.md`, data types in
  `scistudio.core.types.md`).
- Allowed import roots: `user-guide/api-reference/index.md`.
- Tool names and arguments: the live MCP tool schemas.

**Agent reference.**

- The public/private import boundary: `.scistudio/agent-reference/public-api.md`.
- Block rules and interactive declarations:
  `.scistudio/agent-reference/block-contract.md`.
- Reading and constructing data values: `.scistudio/agent-reference/data-types.md`.
- Types from installed packages: `.scistudio/agent-reference/package-discovery.md`.
- For more worked examples (AppBlock, ProcessBlock, IOBlock, interactive):
  `.scistudio/agent-reference/worked-examples.md`.

**Related skills.**

- `scistudio-build-workflow`: adding the new block to a workflow and running it.
- `scistudio-write-type`: no registered type fits a port.
- `scistudio-write-panel`: the custom window of an interactive block.
- `scistudio-write-miniapp`: the user wants to explore a result freely, with no
  single decision to record.
- `scistudio-debug-run`: the block fails inside a workflow run.

## 6. Examples

Read real registered blocks instead of writing from memory: `list_block_examples`
lists curated examples per category (`io`, `process`, `code`, `app`, `ai`,
`subworkflow`), and `read_block_source` shows a block's source. The file written
by `scaffold_block` is itself a commented starting point.

## 7. Available tools

The live MCP tool list is the source of truth; these are the tools this task
uses.

| Tool | What it does | When to use it |
|---|---|---|
| `list_blocks` | Lists registered blocks with a one-line I/O signature. | First, to reuse an existing block; again after reload to confirm yours registered. |
| `get_block_schema` | Returns one block's ports and config schema. | To compare a candidate block's contract with what the user needs. |
| `list_types` | Returns the data-type hierarchy. | Before choosing port types. |
| `list_block_examples` | Lists curated example blocks for a category. | Before writing logic, to find a pattern to follow. |
| `read_block_source` | Returns the source of a registered block. | To study an example or an existing block you are extending. |
| `scaffold_block` | Writes a starter block module under `blocks/`. | To start a new block with the right base class and ports. |
| `reload_blocks` | Rescans the block and type registries. | After writing or editing a block file. |
| `run_block_tests` | Runs the block's tests with pytest. | After reload, before using the block in a workflow. |
| `validate_panel` | Checks a panel folder the way discovery does. | After writing an interactive block's custom panel. |
| `promote_to_user_library` | Moves a project block into My Library. | When the user wants the block in every project. |
