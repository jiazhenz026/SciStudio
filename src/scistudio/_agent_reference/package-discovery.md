# Package discovery

## 1. Where to look

| You need | Read |
|---|---|
| Which blocks exist, and which package each comes from | `list_blocks` |
| Which data types exist, and where each is defined | `list_types` (each type's `module_path`) |
| A package block's exact ports, config, and format capabilities | `get_block_schema(block_type)` |
| Which panels and MiniApps a package ships | `list_panels` |
| A package's own docs, when it ships them | `.scistudio/agent-reference/package-index.md`, then `.scistudio/agent-reference/packages/<package>/` |
| Reading and building values of a package type | [data-types.md](data-types.md) |
| Using package types in a block | [block-contract.md](block-contract.md) |

## 2. Rules

- **Discover through the tools.** Take block, type, and panel names from
  `list_blocks`, `list_types`, and `list_panels`. Never type a package name from
  memory or read a package's source to find it.
- **Only what is installed exists.** A package that is not in `list_blocks` is not
  installed in this environment. Tell the user and let them install it from the
  Package Manager; do not install packages yourself.
- **Import from the package top level.** Write `from scistudio_blocks_<name> import
  SomeType`. Never import from a deep module path or an underscore module such as
  `_support`.
- **Use a package type like a core type.** A package type subclasses a core type, so
  it already has `to_memory()`, `to_numpy()`, `sel()`, and `with_meta()`. Build it
  with its constructor or a classmethod on the type, never with a package helper.
- **Read and write package data through core `load_data` and `save_data`.** Package
  readers and writers register format capabilities that the core blocks route to.
  Never put a package IO block in a workflow as its own node.
- **Reuse package blocks and types first.** When a package block or type already
  fits the task, use it. Write a new block with `scistudio-write-block`, or a new
  type with `scistudio-write-type`, only when nothing registered fits.
- **Read the package's docs when it ships them.** `package-index.md` lists the
  installed packages that bundle docs, with links to their pages. A package missing
  from it ships no docs; rely on the tools' output for it.
