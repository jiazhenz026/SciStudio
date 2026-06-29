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
refresh the registry). Reusable across projects: ship a package with the
`scistudio.blocks` / `scistudio.types` / `scistudio.previewers` entry points.

## Before authoring (rules)

1. Call `list_blocks` and **reuse** if a block's I/O contract matches.
2. Call `list_types`; pick concrete port types.
3. After `scaffold_block`, read every `warnings[]`. After writing, `reload_blocks`
   then `run_block_tests`.
