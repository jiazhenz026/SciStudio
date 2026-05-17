---
name: scieasy-inspect-data
description: |
  Use when the user wants to look at intermediate or output data —
  preview a slice of an image, peek at the first rows of a DataFrame,
  check the shape/dtype of an array, or trace where a data ref came
  from. NOT for debugging failed runs (use scieasy-debug-run).
---

# scieasy-inspect-data

SciEasy data flows as references (`StorageReference`), not in-memory
payloads. This is the ADR-031 reference-only contract: blocks emit
refs, edges carry refs, and the runtime materialises data inside a
block's `run()` only when the block itself asks. As an agent you
inspect refs without materialising them — `inspect_data` returns
shape / dtype / axes / storage backend, `preview_data` returns a
thumbnail or first-N-rows view, `get_lineage` walks the producing-block
graph backwards.

This skill teaches when to reach for each tool, how to interpret the
results faithfully, and when to materialise (rarely — only via a
block's `run()`, never inside an agent turn).

## 1. Reference-only contract (ADR-031)

Data never flows through the agent's memory. The agent sees refs
(opaque IDs like `rf-001`); MCP tools operate on refs. There is no
agent-level "load this 50 GB image and look at it" — you ask the
runtime for a preview, and the runtime returns a thumbnail.

Implications:

- You cannot `cat` a ref via `Bash`.
- You cannot copy ref bytes into a variable.
- You can ask MCP tools about a ref: its shape, type, backend,
  ancestors, a thumbnail.

## 2. `inspect_data(ref)`

Returns shape, dtype, axes, storage backend, size in bytes, and the
data type (e.g. `Image`, `Mask`, `DataFrame`). Call this first when
you don't know what a ref is.

Use the returned fields verbatim when reporting to the user. Do not
fabricate.

## 3. `preview_data(ref, max_rows?, max_dim?)`

Returns a thumbnail / first-N rows / first-N chars view of the ref:

- For arrays: a downsampled thumbnail; pass `max_dim` to bound the
  largest axis (e.g. `max_dim=128`).
- For DataFrames: first N rows; pass `max_rows` (default ~10).
- For text: first N characters.

The preview is for the user's eye. Do NOT report a preview as the
actual data — it is downsampled or truncated.

## 4. `get_lineage(ref)`

Returns the producing chain (transitive ancestors of the ref): which
block produced it, on which run, from which input refs. Useful for
"where did this come from?" questions.

`get_lineage` returns the ADR-038-recorded lineage; the answers are
authoritative. Do not guess at provenance.

## 5. `get_block_output(run_id, node_id, port_name)`

Fetches a ref by addressing the producing block. Use when the user
asks about the output of a specific node in a specific run.

If the block emits a Collection, `get_block_output` returns the
Collection wrapper; call `inspect_data` on it to see the per-item
shape, or iterate via the wrapper's items.

## 6. `list_data`

Enumerates data assets under the project's `data/` directory. Use
this when the user asks "what data is in this project?" or before
designing a workflow that consumes a specific file.

## 7. Citing real data

When reporting results to the user, cite the `inspect_data` return
values verbatim. Never fabricate shapes, dtypes, or axes from memory.

Example phrasing: "The output mask is shape `(512, 512)`, dtype
`bool`, axes `YX`, backed by Zarr at `data/derived/mask.zarr`."

If you don't yet know a value, call `inspect_data` before reporting.

## 8. Worked example

User: "What's in the output of the threshold step?"

```
# Step 1: address the ref
get_block_output(run_id="r-abc123", node_id="thr", port_name="mask")
# → ref "rf-099"

# Step 2: shape/type
inspect_data(ref="rf-099")
# → {type: "Mask", shape: [512, 512], dtype: "bool", axes: "YX",
#    backend: "zarr", size_bytes: 262144}

# Step 3: thumbnail (for the user to see)
preview_data(ref="rf-099", max_dim=128)
# → {format: "png", bytes: "<base64-thumbnail>"}

# Step 4: report
# "The threshold step's `mask` output is a 512×512 bool Mask (YX,
# ~262 KB on Zarr). Thumbnail displayed above."
```

## 9. When to walk lineage

User asks "where did this number come from?" or "what produced this
output?":

```
get_lineage(ref="rf-099")
# → [{producer_run: r-abc123, producer_block: thr, producer_port: mask,
#     inputs: [{port: image, ref: rf-001}]},
#    {producer_run: r-abc123, producer_block: load, producer_port: images,
#     inputs: []}]
```

Report the chain back to the user. Each entry is a producing block in
the original run.

## Mandatory rules

- Never claim to have "seen" data without inspecting it via these
  tools.
- Use `preview_data` for thumbnails / first-rows; never load full
  arrays into the agent turn.
- Cite shape / dtype / axes from `inspect_data` results, not from
  memory.
- Never fabricate provenance — call `get_lineage` and cite the
  returned chain.

## Anti-patterns

- Fabricating shapes / dtypes ("it should be 512×512" — call
  `inspect_data` instead).
- Materialising a ref into memory via `Bash` and `cat`.
- Reporting a `preview_data` thumbnail as if it were the actual
  full-resolution data.
- Guessing at lineage instead of calling `get_lineage`.
