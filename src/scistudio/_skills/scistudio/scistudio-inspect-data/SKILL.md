---
name: scistudio-inspect-data
description: |
  Use when the user wants to look at intermediate or output data —
  preview a slice of an image, peek at the first rows of a DataFrame,
  check the shape/dtype of an array, or trace where a data ref came
  from. NOT for debugging failed runs (use scistudio-debug-run).
---

# scistudio-inspect-data

SciStudio data flows as references (`StorageReference`), not in-memory
payloads. This is the reference-only contract: blocks emit
refs, edges carry refs, and the runtime materialises data inside a
block's `run()` only when the block itself asks. As an agent you
inspect refs without materialising them — `inspect_data` returns
shape / dtype / axes / storage backend, `preview_data` returns a
thumbnail or first-N-rows view, `get_lineage` walks the producing-block
graph backwards.

This skill teaches when to reach for each tool, how to interpret the
results faithfully, and when to materialise (rarely — only via a
block's `run()`, never inside an agent turn).

## 1. Reference-only contract

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

## 3. `preview_data(ref, fmt)`

Returns a small, bounded view of the ref. The signature is
`preview_data(ref, fmt)`: `ref` is the StorageReference wire dict and `fmt`
is an advisory preferred format (`table` / `png_base64` / `chart` / `text` /
`artifact`). Dispatch is **type-driven** — the tool inspects the ref's
`type_chain` and picks the right view regardless of `fmt`:

- DataFrame → first ~100 rows (Arrow slice).
- Array / Image → a PNG thumbnail clamped to 256×256 (chunked read; no OOM).
- Series / Spectrum → first ~200 entries.
- Text → first ~4096 chars.
- Artifact → size and, for small images, a base64 data URI under the 8 MiB cap.

There are no `max_rows` / `max_dim` arguments — bounds are fixed by the tool to
keep previews cheap. The preview is for the user's eye. Do NOT report a preview
as the actual data — it is downsampled or truncated.

For a richer interactive view (slice slider, LUT, custom panels) the GUI's
preview panel routes through the previewer system; as an agent you use
`preview_data` for a quick bounded look. To draw a figure from a block output,
use the `scistudio-write-plot` skill (preview-only plot jobs).

## 4. `get_lineage(ref)`

Returns the producing chain (transitive ancestors of the ref): which
block produced it, on which run, from which input refs. Useful for
"where did this come from?" questions.

`get_lineage` returns the recorded lineage; the answers are
authoritative. Do not guess at provenance.

## 5. `get_block_output(run_id, block_id, port)`

Fetches a ref by addressing the producing block. Use when the user
asks about the output of a specific block in a specific run.

The tool returns a `GetBlockOutputResult` envelope:

- `ref`: the StorageReference wire dict to pass to `inspect_data` or
  `preview_data`.
- `type`: `{type_chain: [...], type_name: "..."}` extracted from the ref
  metadata when available.
- `produced_at`: the recorded production timestamp, or an empty string when
  that timestamp is unavailable.

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
`bool`, axes `YX`, backed by Zarr at `data/processed/mask.zarr`."

If you don't yet know a value, call `inspect_data` before reporting.

## 8. Worked example

User: "What's in the output of the threshold step?"

```
# Step 1: address the ref
mask_output = get_block_output(run_id="r-abc123", block_id="thr", port="mask")
# -> {ref: {...}, type: {type_chain: ["DataObject", "Mask"], type_name: "Mask"},
#     produced_at: ""}

# Step 2: shape/type
inspect_data(ref=mask_output.ref)
# → {type: "Mask", shape: [512, 512], dtype: "bool", axes: "YX",
#    backend: "zarr", size_bytes: 262144}

# Step 3: thumbnail (for the user to see)
preview_data(ref=mask_output.ref, fmt="png_base64")
# → {fmt: "png_base64", payload: {...}, truncated: true}  # clamped to 256×256

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
