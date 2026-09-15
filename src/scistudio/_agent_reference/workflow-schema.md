# Workflow YAML schema

A workflow is a DAG of typed blocks under `workflows/*.yaml`. The runtime is the
source of truth; it validates structure and types before running. Write through
the `write_workflow` MCP tool (not direct file edits), then `validate_workflow`.

## Shape

```yaml
workflow:                            # REQUIRED top-level key
  id: my-pipeline                    # slug, unique per project
  version: "1.0.0"                   # semver
  description: One-line summary.     # optional, recommended
  nodes:
    - id: load                       # unique node id
      block_type: load_data          # registered name (from list_blocks)
      config:                        # validated against the block's config_schema
        core_type: DataFrame
        path: data/raw/in.csv
    - id: thr
      block_type: imaging.threshold
      config: {method: otsu}
  edges:
    - source: "load:data"            # "<node_id>:<port_name>" — single colon
      target: "thr:image"
  metadata: {}                       # optional free-form
```

| Level | Keys |
|---|---|
| `workflow` | `id` (req), `version` (req), `description`, `nodes` (req), `edges` (req; `[]` ok for single block), `metadata` |
| node | `id` (req), `block_type` (req; must be registered), `config` (req; may be `{}`) |
| edge | `source` (req), `target` (req) — each `"node_id:port_name"`, **single colon**, two strings only |

## Rules

- **File name MUST equal the `id`.** Always write to `workflows/{id}.yaml`.
  `write_workflow` rejects a mismatch (e.g. file `foo_bar.yaml` holding
  `id: foo-bar`). Pick one convention for the id and let the file follow it — do
  not use snake_case for the file and kebab-case for the id. Renaming or moving
  a workflow with `move_path` rewrites its `id` to the new file name.
- **A run is identified by its file, not by `id`.** `run_workflow(path)` runs
  exactly the file at `path`. A file under `workflows/` runs as its file name
  (`workflows/main.yaml` → `main`); any other workflow file runs under its
  project path written with `@` separators (`subworkflows/qc.yaml` →
  `@subworkflows@qc.yaml`). That value is the `run_id` to poll, the `workflow_id`
  on run events and lineage, and the `data/zarr/<id>/` output folder.
- **Edge shape is two strings.** Not the canvas 4-field `{source, source_port,
  target, target_port}` form. Separator is a single colon (`load:data`), not
  `.`/`/`/`-`.
- **Never guess port names or block_type.** Call `get_block_schema(block_type)`
  and copy exact `input_ports[].name` / `output_ports[].name`; `block_type` is
  namespaced (`imaging.threshold`, `load_data`) — `list_blocks` returns the
  canonical name.
- **Config must satisfy `config_schema`** (required fields present); paths are
  project-relative (no `../` escape).
- **DAG only** (no cycles); edges must be **type-compatible** (`list_types` for the
  hierarchy).
- **Prefer core `Load`/`Save`** (`load_data` / `save_data`) with a `core_type` —
  it covers package types (`Spectrum`, `Image`, …) via the `core_type` enum. Use a
  package-specific IO block only when no `core_type` fits.
- **File format is a `capability_id`.** `get_block_schema` lists the format
  capabilities a core Load/Save node or a Code/App Block port can pick
  (`format_capabilities`); `get_block_config` reports the one a node or port will
  use and whether the choice is ambiguous. Leave `capability_id` unset when the
  path extension decides it; set it (node config for Load/Save, the port entry
  for Code/App Block ports) when several formats match. `update_block_config`
  refuses an id that does not fit the direction, data type, and extension.
- Fan-out = multiple edges with the same `source`; no "tee" block needed.

## Canonical tool sequence

```
list_blocks
get_block_schema(block_type)   # per candidate: exact ports + config_schema
list_types                     # when wiring unfamiliar types
write_workflow(path, content)  # pre-validates; read next_step
validate_workflow(path)        # edges, type-compat, DAG; read every error
run_workflow(path)             # -> run_id
get_run_status(run_id)         # poll until succeeded/failed/cancelled
```

On `validate_workflow` failure: read every error; for a port/type error call
`get_block_schema`/`list_types` before retrying; fix all in one rewrite; retry ≤3,
then ask the user. Never `run_workflow` an unvalidated YAML. See
[block-contract.md](block-contract.md) for the blocks; the built-in blocks are
catalogued in the user guide (`../../user-guide/built-in-blocks.md`).
