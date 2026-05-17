---
name: scieasy-debug-run
description: |
  Use when a workflow run has failed, is stuck, or produced unexpected
  output, and you need to diagnose the cause. Covers run-status
  inspection, block-log retrieval, lineage navigation, common error
  signatures, and the finish_ai_block contract for AI block PTYs. NOT
  for designing new workflows (use scieasy-build-workflow).
---

# scieasy-debug-run

A SciEasy run has terminated in `failed` or `cancelled` state, or you
suspect a block is producing wrong output. This skill teaches the
canonical diagnostic sequence — start at the run-status envelope,
drill into per-block logs, follow lineage backwards to find the
upstream cause, and inspect intermediate data refs without
materialising them into memory. Most run failures fall into ~6
recurring categories; §5 maps each to the next tool call.

## 1. The canonical diagnostic sequence

```
get_run_status(run_id)                 # full envelope
get_block_logs(run_id, failed_node)    # stdout/stderr for the failed block
inspect_data(upstream_ref)             # confirm input type/shape
get_lineage(failed_input_ref)          # walk backwards to producing block
# Form hypothesis; propose fix to user; do NOT silently retry.
```

Never skip any step. The status envelope alone often understates the
failure; the logs surface the real Python traceback; lineage shows
upstream contamination.

## 2. `get_run_status` envelope shape

```
GetRunStatusResult(
  run_id: str,
  state: "queued" | "running" | "succeeded" | "failed" | "cancelled" | "unknown",
  progress: {"block_states": {block_id: STATE_NAME, ...}},
  errors: [BlockErrorEntry(block_id, error, summary), ...]
)
```

Read every field. The per-block state map lives at
`progress.block_states` (not at the top level); captured block-level
errors with full Python tracebacks live in the top-level `errors`
list. The `summary` field (when present) is a one-line digest; the
`error` field is the full traceback. Start by scanning
`progress.block_states` for the first non-`succeeded` entry, then
locate its matching `BlockErrorEntry` in `errors`.

## 3. `get_block_logs` patterns

`get_block_logs(run_id, node_id)` returns `{stdout: str, stderr: str}`.
Read both. Common signatures:

- **`Traceback (most recent call last):`** — Python exception. Find
  the bottom-most line; that names the exception and the offending
  call.
- **`FileNotFoundError: [Errno 2] No such file or directory: '...'`**
  — block's `config.path` points to a file that does not exist. Check
  the config; verify the file exists under the project root.
- **`MemoryError`** — input too large to materialise. Recommend
  chunking (`iter_chunks()` inside the block) or a smaller input.
- **`KeyError: 'X'` inside `run(self, inputs, config)`** — the block
  expected an input port `X` that was not wired. Check the workflow
  YAML edges.
- **`pydantic.ValidationError`** in block config — `config_schema`
  mismatch. Check the workflow YAML's node `config` against the
  block's schema (`get_block_schema`).
- **`ImportError`** — stale `reload_blocks` or a missing dependency
  in the block's Python file.
- **`subprocess.TimeoutExpired`** — AI block timed out;
  `config.timeout_sec` was too low for the prompt's actual runtime.

When citing a log line to the user, copy the line verbatim. Do not
paraphrase tracebacks.

## 4. `get_lineage` for cascading failures

If block `B` failed because its input was malformed, the upstream
block `A` was the real cause. `get_lineage(input_ref)` returns the
ancestor chain:

```
get_block_output(run_id, failed_node, failed_input_port)
# Returns the input ref. If it's a list of refs (collection), pick one.
get_lineage(ref)
# Returns ancestors: [{producer_block: A, producer_port: out, ...}, ...]
```

Cross-reference with `get_block_logs(run_id, A)`. The actual fault
might be in A even though B is the one that failed.

## 5. Common error signatures

| Error string | Root cause | Next tool call |
|---|---|---|
| `FileNotFoundError: 'data/...'` | Config path wrong / file missing | `list_data` then fix config |
| `MemoryError` | Input too large | Recommend chunking; `inspect_data(ref)` to confirm size |
| `KeyError: '<port>'` in `run` | Edge not wired to required input | `get_block_schema`; fix workflow YAML |
| `pydantic.ValidationError` | Config doesn't match schema | `get_block_schema`; fix workflow YAML config |
| `ImportError: ...` | Stale registry / missing dep | `reload_blocks`; check `blocks/*.py` imports |
| `subprocess.TimeoutExpired` | AI block ran longer than `timeout_sec` | Increase `timeout_sec` or simplify prompt |
| `Type mismatch: expected X got Y` | Wrong edge type | `list_types`; rewire workflow |
| `Cycle detected in DAG` | Edge points to ancestor | Re-draw the YAML DAG |

If the error does not match any row, read the full traceback and
report the bottom-most call site to the user. Do not guess.

## 6. lineage.db (ADR-038) — use the MCP surface

ADR-038 lineage data lives in `.scieasy/lineage.db` (SQLite). Do NOT
query that file directly. The MCP tools are the public surface:

- `get_lineage(ref)` — ancestors of one ref
- `get_block_output(run_id, node_id, port_name)` — ref by address
- `get_run_status(run_id)` — top-level run envelope

These tools enforce schema versioning and access semantics. Direct
SQLite queries bypass those checks and may return stale or
mis-shaped rows.

## 7. Working inside an AI block PTY

When a workflow's `AIBlock` step is reached, the engine spawns an
embedded agent in a PTY tab and sets the environment variable
`SCIEASY_AI_BLOCK_RUN_DIR`. If that variable is set in your shell
environment, you are inside an AI block — the workflow is paused
waiting for you to finish.

**Canonical termination**: when the prompt's work is complete, call
`mcp__scieasy__finish_ai_block(run_id, output_refs)` where:

- `run_id` — the parent workflow's run id (read from
  `SCIEASY_AI_BLOCK_RUN_ID` or the environment).
- `output_refs` — a dict `{port_name: ref}` matching the AIBlock's
  declared `output_ports`.

The runtime validates the refs against the block's port types,
records the completion in lineage.db, and resumes the downstream
workflow.

**Failure modes**:

- `finish_ai_block` called outside an AI block (no `SCIEASY_AI_BLOCK_RUN_DIR`)
  — fails fast with a clear error.
- `finish_ai_block` called with output refs that don't match the
  declared port types — runtime rejects with a type-mismatch error;
  fix the upstream block or the port declaration.
- AI block timed out (`subprocess.TimeoutExpired` from §5) — the
  parent workflow already failed; you can no longer
  `finish_ai_block`. Surface to the user and let them re-run with a
  larger `timeout_sec`.

## 8. Worked example

User: "My segmentation workflow failed."

```
# Step 1: full envelope
get_run_status(run_id="r-abc123")
# → GetRunStatusResult(state="failed",
#     progress={"block_states": {"load": "succeeded", "thr": "failed"}},
#     errors=[BlockErrorEntry(block_id="thr",
#                             summary="Block 'thr' raised: type mismatch",
#                             error="<full traceback>")])

# Step 2: per-block logs
get_block_logs(run_id="r-abc123", node_id="thr")
# stderr → "TypeError: ThresholdSimple.process_item() expected
#           Image, got DataFrame"

# Step 3: confirm the upstream output type
get_block_output(run_id="r-abc123", node_id="load", port_name="images")
# → ref "rf-001"
inspect_data(ref="rf-001")
# → {type: "DataFrame", shape: ..., axes: ...}

# Diagnosis: the workflow YAML wired load's "tables" port (DataFrame)
# into thr's "image" port (Image). Should have wired "images" port.

# Report to user: cite the log line verbatim; recommend fixing the
# workflow YAML edge. Do NOT silently retry.
```

## Mandatory rules

- Always read the FULL `get_run_status` envelope, not just `state`.
- For any failed block, ALWAYS call `get_block_logs` before guessing
  the cause.
- Do NOT speculate — cite log lines verbatim when explaining the
  failure.
- Do NOT call `cancel_run` on a `running` workflow without user
  confirmation.
- Do NOT query `lineage.db` directly; use the MCP lineage tools.

## Anti-patterns

- Cancelling a still-running workflow without checking with the user.
- Speculating about the cause without reading logs.
- Calling `inspect_data` on a 50 GB array (use `preview_data` — it
  returns a thumbnail).
- Re-running the workflow without changing anything ("maybe it'll
  work this time").
- Stopping at `get_run_status` without drilling into per-block logs.
