---
name: scistudio-build-workflow
description: |
  Use when the user wants to design a new workflow, choose block types,
  wire edges between blocks, or convert a verbal pipeline description into
  a valid workflow YAML. NOT for debugging existing runs (use
  scistudio-debug-run) or for writing custom blocks (use scistudio-write-block).
---

# scistudio-build-workflow

## 1. What a workflow is

A workflow is a graph of typed blocks saved as `workflows/<id>.yaml`. It holds
the steps of an analysis that are settled, so they can be rerun on new data,
reused, and traced back through lineage. The runtime validates structure and
types before a run, and the GUI canvas shows and edits the same file.

Build a workflow when the user knows the steps. When the next step is still
unclear and the user wants to try things on a result, offer a MiniApp first
(`scistudio-write-miniapp`), then build the settled step into the workflow.

## 2. Steps to build a workflow

1. **Understand the analysis.** Confirm the input data, the steps, and the
   outputs the user wants. Ask only about the science.
2. **Find the blocks.** Call `list_blocks`, then `get_block_schema` for each
   candidate to read its exact ports and config. If no block fits a step, write
   one with `scistudio-write-block`.
3. **Check the types.** Where blocks with unfamiliar types meet, call
   `list_types` to confirm each edge connects compatible types.
4. **Write the workflow.** Create it with `write_workflow` at
   `workflows/<id>.yaml`; change an existing one with `edit_workflow` or
   `update_block_config`.
5. **Validate.** Call `validate_workflow` and fix every error before running.
6. **Run and confirm.** Call `run_workflow`, poll `get_run_status` until a
   terminal state, then check the outputs with `get_block_output` and
   `inspect_data` / `preview_data`.
7. **Report.** Tell the user what the workflow does, where its outputs are, and
   which parameters they can tune in each block's config.

## 3. Anti-patterns

- Guessing port names or block types instead of reading `get_block_schema`.
- Putting a block's display name in `block_type`; use its `type_name`.
- Using the canvas four-field edge shape; workflow edges are two strings,
  `"node_id:port_name"`.
- Putting a package IO block or a self-written IO block in a workflow as its own
  node; every read and write goes through core `load_data` / `save_data`.
- Re-emitting a whole existing workflow through `write_workflow` for a small
  change; it drops the user's block config and comments.
- Running an unvalidated workflow, or declaring done while a run is `running`.
- Re-running a failed workflow without diagnosing the failure first.
- Editing `workflows/*.yaml` with file tools instead of the workflow tools.

## 4. Defaults, tool sequence, and failure handling

**Always load and save with the core blocks.** Every read uses `load_data` and
every write uses `save_data`, configured with `core_type` (the data type) and the
format: the file extension of the path, or `capability_id` to pick one registered
format capability explicitly. `get_block_schema` lists the capabilities a block can
pick under `format_capabilities`; `get_block_config` reports the one a node will
use and whether the choice is ambiguous. Leave `capability_id` unset when the
extension decides it, and set it when several formats match;
`update_block_config` refuses an id that does not fit the direction, data type, and
extension. Both blocks use a port named `data`. Never put a
package IO block or a self-written IO block in the workflow as its own node.

The core blocks route to whichever registered capability handles the type and
format, including package readers and writers and IO blocks written in this
project. When no capability covers a format the user needs, write an IO block for
it with `scistudio-write-block`, reload, and then read or write through core
`load_data` / `save_data`, which runs that block's code.

**Tool sequence.**

```
list_blocks
get_block_schema(block_type)          # each candidate block
list_types                            # only for unfamiliar type pairs
write_workflow(path, content)         # create; edit_workflow / update_block_config to change
validate_workflow(path)
run_workflow(path)                    # returns run_id
get_run_status(run_id)                # poll until terminal
get_block_output(run_id, block_id, port)
inspect_data(ref) / preview_data(ref, fmt)
```

Every write-class result carries `next_step`; read it and follow it.
`write_workflow` refuses a file name whose stem differs from the workflow `id`,
so always write `workflows/{id}.yaml`; a mismatched pair collides with the file
that id names on save and import. `run_workflow(path)` runs exactly the file at
`path`.

**Changing an existing workflow.** `write_workflow` replaces the whole file, so
use it only to create a workflow. To change part of one, call `get_workflow` and
copy the exact text to replace, then call
`edit_workflow(workflow_path, edits=[{old_string, new_string}])`: each
`old_string` must match exactly once, or set `replace_all` to replace every
occurrence. To change only one block's parameters, use
`update_block_config(workflow_path, block_id, params)`. Validate after either.

**When validation fails.** `validate_workflow` returns
`ValidateWorkflowResult(valid: bool, errors: list[str])`. On `valid=False`, read
every error, check `get_block_schema` for port errors and `list_types` for type
errors, fix them all in one edit, and validate again. After three failed rounds,
stop and explain the blocker to the user.

**When a run fails.** `get_run_status` returns `GetRunStatusResult` with
per-block states under `progress.block_states` and failures in `errors`, a list
of `BlockErrorEntry(block_id, error, summary)`. Terminal states are `succeeded`,
`failed`, and `cancelled`; keep polling while the state is `queued`, `running`,
or `unknown`. Load `scistudio-debug-run` to diagnose before changing
and re-running.

## 5. Contracts and routing

**Contracts (MUST follow).**

- Workflow YAML shape: `user-guide/api-reference/workflow-yaml.md`.
- A block's ports and config: `get_block_schema(block_type)`.
- Type hierarchy: `list_types`.
- Tool names and arguments: the live MCP tool schemas.
- AI Agent block providers: `get_block_schema("ai.agent")`, whose `provider`
  enum lists the providers that can run an AI block.

**Agent reference.**

- Blocks and types from installed packages:
  `.scistudio/agent-reference/package-discovery.md`.
- For more worked examples (a complete workflow YAML, block examples):
  `.scistudio/agent-reference/worked-examples.md`.

**Related skills.**

- `scistudio-write-block`: no registered block fits a step, or a format needs an
  IO block.
- `scistudio-debug-run`: a run failed or an AI Agent block did not finish.
- `scistudio-inspect-data`: checking what a run produced.
- `scistudio-write-miniapp`: the next step is unclear and the user wants to try
  things on a result.

## 6. Examples

Block types other than `load_data`, `save_data`, and `ai.agent` below are
placeholders; copy real `type_name`s and port names from `list_blocks` and
`get_block_schema`.

**Linear: load, process, save.**

```yaml
workflow:
  id: normalize-counts
  version: "1.0.0"
  description: Load a count table, normalize it, save the result.
  nodes:
    - id: load
      block_type: load_data
      config: {core_type: DataFrame, path: data/raw/counts.csv}
    - id: norm
      block_type: normalize_counts        # placeholder
      config: {method: cpm}
    - id: save
      block_type: save_data
      config: {core_type: DataFrame, path: data/processed/counts_cpm.csv}
  edges:
    - {source: "load:data", target: "norm:table"}
    - {source: "norm:table", target: "save:data"}
```

**Fan-out: one output feeds two steps.** Give the same `source` to two edges;
no tee block is needed.

```yaml
  edges:
    - {source: "load:data", target: "qc:table"}
    - {source: "load:data", target: "norm:table"}
```

**AI Agent block.** When the run reaches this node, the runtime opens an agent
tab in the GUI with the chosen provider. The agent uses the same MCP tools, writes
the declared outputs, and ends the step once with
`finish_ai_block(outputs={port_name: path})`; `scistudio-debug-run` covers what to
do when it does not finish.

```yaml
    - id: summarise
      block_type: ai.agent
      config:
        provider: claude-code
        user_prompt: Summarise each CSV into one row of statistics.
        output_ports:
          - {name: result, types: [DataFrame], expected_path: ./summary.csv}
```

## 7. Available tools

The live MCP tool list is the source of truth; these are the tools this task
uses.

| Tool | What it does | When to use it |
|---|---|---|
| `list_blocks` | Lists registered blocks with category, package, and a one-line I/O signature. | First, to find blocks for each step and to reuse before writing a new one. |
| `get_block_schema` | Returns one block's ports and config schema. | Before wiring or configuring any block; copy port names and config keys from it. |
| `list_types` | Returns the data-type hierarchy. | When an edge joins unfamiliar types. |
| `get_active_workflow_context` | Returns the workflow the user has open in the GUI. | When the user says "this workflow" without naming it. |
| `get_workflow` | Loads a workflow file. | Before editing an existing workflow, to copy exact text. |
| `write_workflow` | Writes a whole workflow file after schema validation. | Only to create a new workflow. |
| `edit_workflow` | Applies search/replace patches to an existing workflow. | For any partial change: add or remove nodes, rewire edges. |
| `get_block_config` / `update_block_config` | Reads or patches one block's config in a workflow. | To inspect or change a single block's parameters. |
| `validate_workflow` | Checks structure, edges, types, and the graph. | After every write or edit, before running. |
| `run_workflow` | Starts a run and returns its `run_id`. | Once the workflow validates. |
| `get_run_status` | Returns run and per-block state and errors. | Poll after starting a run until it is terminal. |
| `cancel_run` | Cancels an in-flight run. | When the user asks to stop, or a run must be restarted. |
| `get_block_output` | Resolves a block port's output from a run. | After a run, to find what a block produced. |
| `inspect_data` / `preview_data` | Return metadata or a bounded preview of stored data. | To confirm outputs look right before reporting. |
| `get_block_logs` | Returns a block's captured output. | When a block fails or behaves unexpectedly; then load `scistudio-debug-run`. |
