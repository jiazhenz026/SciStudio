# Workflow YAML schema

## 1. Where to look

| You need | Read |
|---|---|
| Every key of a workflow file, the edge form, file name and run identity, and what validation checks | `user-guide/api-reference/workflow-yaml.md` (generated from the code) |
| How to build, edit, validate, and run a workflow | the `scistudio-build-workflow` skill |
| A block's exact ports, config, and format capabilities | `get_block_schema(block_type)` |
| The type hierarchy for wiring | `list_types` |
| Blocks and types from installed packages | [package-discovery.md](package-discovery.md) |

## 2. Rules

- **Change workflows only through the workflow tools.** Create with
  `write_workflow`, change with `edit_workflow` or `update_block_config`, and never
  edit `workflows/*.yaml` with file or shell tools. Re-emitting a whole existing
  file through `write_workflow` drops the user's config and comments.
- **Name the file after the `id`.** Write `workflows/<id>.yaml`; `write_workflow`
  refuses a file whose name and `id` differ. A run is identified by its file, and
  `run_workflow(path)` runs exactly that file.
- **Copy block types and port names from the schema.** Use the `type_name` from
  `list_blocks` as `block_type`, and port names from `get_block_schema`. A guessed
  name fails validation or wires the wrong port.
- **Write edges as two strings.** Each edge is `source: "node_id:port_name"` and
  `target: "node_id:port_name"`, with one colon. The canvas form with separate port
  fields is not a workflow edge.
- **Read and write data only with core `load_data` and `save_data`.** Configure
  `core_type` and the format (the path's extension, or `capability_id` when several
  formats match). Never put a package or self-written IO block in a workflow as a
  node.
- **Validate before every run.** Call `validate_workflow` after each change and fix
  every error, reading `Warning:` messages as advisory. Never start
  `run_workflow` on a workflow that has not validated.
- **Track a run by its own `run_id`.** `run_workflow` returns it; pass it to
  `get_run_status`, `get_block_output`, `get_block_logs`, and `cancel_run`, which act
  on that run only (a workflow id means that workflow's latest run). One workflow
  cannot run twice at once, while different workflows can.
- **Poll a run to a terminal state.** Keep calling `get_run_status` while the state
  is `queued`, `running`, or `unknown`. Only `succeeded`, `failed`, or `cancelled` is
  an outcome.
- **Keep GB-scale data out of memory.** `load_data` persists what it reads to Zarr
  or Parquet storage, and each block should read that storage by region or in chunks
  (see [block-contract.md](block-contract.md)). Inspect results with `inspect_data`
  and `preview_data`, which are bounded, and never read stored data files whole.
