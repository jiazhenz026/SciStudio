# Block contract

## 1. Where to look

| You need | Read |
|---|---|
| How to write, load, test, and use a block | the `scistudio-write-block` skill |
| Signatures of `Block`, ports, `BlockConfig`, interactive declarations, collection helpers | `user-guide/api-reference/scistudio.blocks.base.md` |
| `ProcessBlock` and `process_item` | `user-guide/api-reference/scistudio.blocks.process.md` |
| IO blocks: `SimpleLoader`, `SimpleSaver`, `IOBlock`, format capabilities | `user-guide/api-reference/scistudio.blocks.io.md` |
| `AppBlock`: `app_command`, `prepare_launch` | `user-guide/api-reference/scistudio.blocks.app.md` |
| Data types and how to read or build values | `user-guide/api-reference/scistudio.core.types.md`, [data-types.md](data-types.md) |
| A data type no registered type covers | the `scistudio-write-type` skill |
| What may be imported | [public-api.md](public-api.md) |
| The window of an interactive block | the `scistudio-write-panel` skill |
| Blocks and types from installed packages | [package-discovery.md](package-discovery.md) |

## 2. Rules

- **Reuse before writing.** Call `list_blocks` and use a registered block whose
  ports and config already fit. Write a new block only when none does, and say
  why in its docstring.
- **Never use `DataObject` as a port type.** Every input and output port declares
  the most fitting registered type (for example `Image` over `Array`, `DataFrame`
  over `DataObject`); call `list_types` to choose it. `DataObject` or an empty
  type list breaks previews, type checks, and suggestions, and is not allowed on
  a user-facing block.
- **Inherit only the author base classes.** Use `Block`, `ProcessBlock`,
  `SimpleLoader`, `SimpleSaver`, `IOBlock`, or `AppBlock`. `AIBlock`, `CodeBlock`,
  and `SubWorkflowBlock` are runtime blocks the user adds and configures in a
  workflow.
- **The category comes from the base class.** Writing `base_category` in a block
  has no effect. Choose the base class for the category you want.
- **Return a dict of Collections.** `run` returns `dict[str, Collection]` keyed by
  output port name, and every port carries a `Collection` even for one value.
  `process_item` returns one data object.
- **By default, no extra batch handling is needed.** When you write an IO
  block, inherit SimpleLoader/SimpleSaver and handle the read or write as a
  single-file operation; the core automatically fans in and fans out.
- **Read and build data through the type.** Read values with `to_memory()`,
  `to_pandas()`, or `to_numpy()`, and build outputs with the type's `data=`
  constructor. Never reach into private storage attributes.
- **Never load GB-scale data whole.** Check the size with `inspect_data` first,
  and do not call `to_memory()`, `to_numpy()`, or `to_pandas()` on data that may not
  fit in memory. Read an `Array` by region with `sel(z=..., y=slice(...))` or plane
  by plane with `iter_over("z")`, and any type in pieces with `slice(...)` or
  `iter_chunks(chunk_size)`.
- **Write large arrays in chunks.** Stream an output array with
  `self.persist_array(iterator, shape, dtype)`, where the iterator yields
  `(index, chunk)` along the first axis, and wrap the returned reference as
  `Array(axes=[...], shape=shape, dtype=dtype, storage_ref=ref)`. `persist_table`
  writes one Arrow table at once, so reduce a large table chunk by chunk before
  writing it.
- **Prefer `map_items` for large batches.** It processes one item at a time and
  keeps memory low; `parallel_map` is faster for CPU-heavy work but holds several
  items in memory and needs a picklable function. Use `pack`, `unpack`,
  and `unpack_single` to move between Collections and items.
- **Put every tunable value in `config_schema`.** Give each property a `title`, a
  `description`, and a sensible `default`, and read it with `config.get(...)`.
  A value the user may want to change must not be a constant in the code.
- **`config_schema` merges along the inheritance chain.** A subclass inherits its
  parents' properties, and a property it redeclares replaces the parent's. Do not
  copy parent fields, and bump `version` when you change the schema incompatibly.
- **Label everything the user sees.** Give the block a real `name` and one-line
  `description`, and every port and parameter a distinct name and a description.
  Set `subcategory` to group the block in the palette, and `type_name` to give a
  package block a stable id.
- **Declare an interactive block completely.** Mix in `InteractiveMixin`, set
  `execution_mode = ExecutionMode.INTERACTIVE`, set `interactive_panel`, and
  implement `prepare_prompt`. The registry rejects a block that has only some of
  these.
- **`prepare_prompt` sends plain JSON of real values.** It runs in its own worker
  with the full inputs and builds the JSON view the decision needs, never a sampled
  or downsampled stand-in; the runtime rejects anything that is not plain JSON. A bare dict is shorthand for `InteractivePrompt(panel_payload=...)`,
  and heavy work to reuse after the pause goes in `intermediate`.
- **Compute outputs from the decision.** After the user confirms, `run` or
  `process_item` reads the decision with `config.get("interactive_response", {})`.
  The outputs must follow from the inputs, the config, and that decision alone.
- **Convert a MiniApp without depending on it.** Keep the MiniApp, and create a
  separate block and interactive panel whose results do not rely on the
  MiniApp's Python process. Declare the typed outputs the user asked for, run
  `validate_panel`, `reload_blocks`, and `run_block_tests`, and confirm a real
  pause, decision, and outputs before calling it done.
- **Reload and test after every edit.** Call `reload_blocks`, confirm the block in
  `list_blocks`, then `run_block_tests`. Read `scaffold_block` warnings and every
  write result's `next_step`.
