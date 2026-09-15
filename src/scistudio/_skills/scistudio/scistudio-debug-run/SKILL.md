---
name: scistudio-debug-run
description: |
  Use when a workflow run has failed, is stuck, or produced unexpected
  output, and you need to diagnose the cause. Covers run-status
  inspection, block-log retrieval, tracing a bad input upstream, common error
  signatures, and finishing an AI Agent block with finish_ai_block. NOT
  for designing new workflows (use scistudio-build-workflow).
---

# scistudio-debug-run

## 1. What debugging a run means

A run executes one workflow file block by block and records each block's state,
logs, outputs, and lineage. Debugging a run means finding, from those records,
which block went wrong and why, fixing the cause, and only then running again. A
run can go wrong in three ways:

- **It failed.** A block raised an error; the run state is `failed`.
- **It is stuck.** A block is `paused` waiting for someone: the agent of an AI
  Agent block, the user's decision in an interactive block, or an external
  application.
- **It produced wrong output.** Every block succeeded, but a result is not what
  the user expected. The cause is often upstream of the block where it shows.

The failing block is not always the faulty one: a block can fail because an
upstream block produced malformed data.

## 2. Steps to debug a run

1. **Read the run status.** Call `get_run_status(run_id)` and read every field:
   the run `state`, `progress.block_states`, and every entry in `errors`.
2. **Find the first block that went wrong.** Scan `progress.block_states` for the
   first block that is `error`, `paused`, or `skipped`, and match it to its
   `BlockErrorEntry` in `errors`.
3. **Read its logs.** Call `get_block_logs(run_id, block_id)` and read both
   streams. Find the bottom-most line of any traceback.
4. **Check its inputs.** Read the workflow's edges with `get_workflow` to find
   the upstream ports feeding the block, call `get_block_output` for each in the
   same run, then `inspect_data` and `preview_data`, to confirm each input has the
   type and content the block expects.
5. **Walk upstream when an input is wrong.** Follow the edge back to the block
   that produced it, and repeat steps 3 and 4 for that block in the same run
   until you reach the first block whose inputs are right and whose output is
   wrong.
6. **Explain and fix.** Tell the user the cause, quoting the log line verbatim,
   and the fix. Change the workflow with `edit_workflow` or `update_block_config`,
   or the block file with `scistudio-write-block`, then validate and run again.

## 3. Anti-patterns

- Re-running a failed workflow without changing anything.
- Reading only the run `state` and stopping before the block logs.
- Explaining a failure without quoting the log; paraphrasing a traceback.
- Blaming the block that failed without checking whether its input was wrong.
- Calling `cancel_run` on a running or paused workflow without the user's
  confirmation.
- Querying `.scistudio/lineage.db` or reading run folders directly instead of
  using the MCP tools.
- Treating a `paused` block as hung: it is waiting for someone.

## 4. Defaults, tool sequence, and failure handling

**Run status.** `get_run_status` returns `GetRunStatusResult` with `run_id`,
`state` (`queued`, `running`, `succeeded`, `failed`, `cancelled`, or `unknown`),
`progress.block_states` (block id to state: `idle`, `ready`, `running`, `paused`,
`done`, `error`, `cancelled`, or `skipped`), and `errors`, a list of
`BlockErrorEntry(block_id, error, summary)`. `summary` is a one-line digest;
`error` is the full traceback. A `skipped` block did not run because a required
upstream input was missing; look at the block before it.

**Block logs.** `get_block_logs(run_id, block_id)` returns `stdout`, `stderr`,
and `source`, each stream cut to its last 16 KiB. With `source` set to
`codeblock_exchange` (a Code Block), the script's output comes as a real
stdout/stderr split. With `run_log` (every other block), everything the block
wrote is in `stderr` and `stdout` is empty.

**Common error signatures.**

| Log shows | Likely cause | Next step |
|---|---|---|
| `FileNotFoundError: ... 'data/...'` | A `path` in the config names a file that does not exist | Find the file with `list_directory` or `search_files`; fix the path with `update_block_config` |
| `KeyError: '<name>'` inside `run` | The block reads an input port that is not wired, or a config key that is not set | `get_block_schema`; check the workflow's edges and the node's config |
| `pydantic.ValidationError` | The node's config does not match the block's schema | `get_block_schema`; fix with `update_block_config` |
| `ImportError` / `ModuleNotFoundError` | The block file imports a missing package, or the registry is stale | Check the imports in `blocks/<name>.py`; `reload_blocks` |
| `MemoryError` | An input is too large to load at once | `inspect_data` for its size; process it in chunks inside the block (`iter_chunks`) or use a smaller input |
| A type error naming two data types | The block received a different type than it expects | `inspect_data` on the input; check the edge in the workflow |

Structural problems (a cycle, a required input with no connection, incompatible
edge types, an unknown port) are reported by `validate_workflow` before a run
starts; fix them with `scistudio-build-workflow`. When the log matches no row,
report the bottom-most call site of the traceback verbatim. Do not guess.

**A stuck run.** Find the `paused` block and what it waits for:

- **AI Agent block:** its agent tab in the GUI is still working. The block has
  no time limit; it waits until the agent calls `finish_ai_block` or the user
  cancels the run.
- **Interactive block:** its window is waiting for the user's decision. Ask the
  user to open it and confirm.
- **App block:** the external application is still open. Ask the user to finish
  there.

**Inside an AI Agent block.** When `SCISTUDIO_AI_BLOCK_RUN_DIR` is set in your
environment, you are the agent of an AI Agent block, and the run waits for you.
Write every declared output, then call `finish_ai_block(outputs={port_name:
path})` exactly once, with a path for each declared output port. The runtime then
validates the files against the ports and resumes the run. Error codes:
`not_in_ai_block_context` (called outside an AI Agent block), `invalid_outputs`
(`outputs` is not a mapping of port names to paths), `already_finished` (it was
already called for this run), and `io_error` (the signal could not be written).
If you cannot produce an output, do not call it; tell the user.

**Tool sequence.**

```
get_run_status(run_id)
get_block_logs(run_id, block_id)          # the first block in error
get_workflow(path)                        # edges into that block
get_block_output(run_id, upstream_id, port)
inspect_data(ref) / preview_data(ref, fmt)
```

## 5. Contracts and routing

**Contracts (MUST follow).**

- Tool names, arguments, and result fields: the live MCP tool schemas.
- Workflow YAML shape: `user-guide/api-reference/workflow-yaml.md`.

**Agent reference.**

- Block rules, including what `run` must return:
  `.scistudio/agent-reference/block-contract.md`.
- Reading data values inside a block: `.scistudio/agent-reference/data-types.md`.

**Related skills.**

- `scistudio-build-workflow`: fixing edges, config, or structure, then validating
  and running again.
- `scistudio-write-block`: fixing the code of a project block.
- `scistudio-inspect-data`: looking at intermediate outputs in detail, or tracing
  where an earlier result came from with lineage.
- `scistudio-use-gui`: checking a paused block's window or agent tab.

## 6. Examples

**"My normalize workflow failed."**

```
get_run_status(run_id="<run_id>")
# state="failed"; block_states: load="done", norm="error"
# errors=[BlockErrorEntry(block_id="norm", summary="...", error="<traceback>")]

get_block_logs(run_id="<run_id>", block_id="norm")
# stderr ends with: KeyError: 'gene_id'

out = get_block_output(run_id="<run_id>", block_id="load", port="data")
preview_data(ref=out.ref, fmt="table")
# the table's first column is "GeneID", not "gene_id"
```

Report: the `norm` block looks up a column named `gene_id`, but the loaded table
names it `GeneID` (quote the `KeyError` line). Offer to set the block's column
parameter with `update_block_config`, or to rename the column upstream, then
validate and run again.

**"The run has been going for an hour."**

```
get_run_status(run_id="<run_id>")
# state="running"; block_states: summarise="paused"
```

The `summarise` node is an AI Agent block waiting for its agent. Tell the user
its agent tab is still open in the GUI and has not finished; ask whether to
check that tab or cancel the run.

## 7. Available tools

The live MCP tool list is the source of truth; these are the tools this task
uses.

| Tool | What it does | When to use it |
|---|---|---|
| `get_run_status` | Returns a run's state, per-block states, and errors. | First, for every failed, stuck, or suspicious run. |
| `get_block_logs` | Returns a block's captured output. | For every block in `error`, before explaining the cause. |
| `get_block_output` | Resolves a block port's output from a run. | To get the inputs of a failing block. |
| `inspect_data` / `preview_data` | Return metadata or a bounded preview of stored data. | To check whether an input is what the block expects. |
| `get_block_schema` | Returns one block's ports and config schema. | To compare the node's wiring and config with the block. |
| `get_workflow` | Loads a workflow file. | To find the edges into a block and the config that ran. |
| `edit_workflow` / `update_block_config` | Change a workflow or one node's config. | To apply the fix. |
| `validate_workflow` / `run_workflow` | Check and start a workflow. | After the fix. |
| `cancel_run` | Cancels an in-flight run. | Only when the user confirms. |
| `finish_ai_block` | Ends the AI Agent block you are running in. | Once, after writing every declared output. |
