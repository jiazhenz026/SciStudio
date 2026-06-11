---
name: scistudio-build-workflow
description: |
  Use when the user wants to design a new workflow, choose block types,
  wire edges between blocks, or convert a verbal pipeline description into
  a valid workflow YAML. NOT for debugging existing runs (use
  scistudio-debug-run) or for writing custom blocks (use scistudio-write-block).
---

# scistudio-build-workflow

You are designing a SciStudio workflow — a DAG of typed blocks expressed
as a YAML file under `workflows/`. The runtime is the source of truth;
the GUI canvas is an editor and viewer. Workflows are validated
structurally and type-wise before they run, so a well-formed YAML is
the contract you have to satisfy on the first try if you want a smooth
user experience. This skill teaches the YAML schema verbatim, the
canonical tool-call sequence, and the pitfalls that account for most
validation failures.

## 1. Canonical workflow YAML shape

```yaml
workflow:                            # REQUIRED top-level key
  id: my-pipeline                    # slug, unique within the project
  version: "1.0.0"                   # semver string
  description: One-line summary.     # optional but recommended for the GUI
  nodes:                             # list of block instances
    - id: load                       # node id (referenced by edges; must be unique)
      block_type: imaging.load_image # registered block name from list_blocks
      config:                        # passes the block's config_schema
        path: data/raw/beads.tif
    - id: thr
      block_type: imaging.threshold
      config:
        method: otsu
    - id: save
      block_type: imaging.save_image
      config:
        path: data/derived/mask.tif
        format: tiff
  edges:                             # connections between node ports
    - source: "load:images"          # MUST be "<node_id>:<port_name>" — colon, not dot
      target: "thr:image"
    - source: "thr:mask"
      target: "save:images"
  metadata: {}                       # optional free-form dict
```

**Top-level keys**

| Key | Type | Required | Notes |
|---|---|---|---|
| `workflow.id` | string | yes | Slug; unique per project; used as run output prefix |
| `workflow.version` | string | yes | Semver; runtime checks compatibility |
| `workflow.description` | string | no | Shown in GUI; recommended |
| `workflow.nodes` | list[node] | yes | Block instances |
| `workflow.edges` | list[edge] | yes | Empty list `[]` is legal for a single-block workflow |
| `workflow.metadata` | dict | no | Free-form; reserved for tool-specific extensions |

**Node shape**

| Key | Type | Required | Notes |
|---|---|---|---|
| `id` | string | yes | Unique within the workflow |
| `block_type` | string | yes | Must match a registered block (call `list_blocks`) |
| `config` | dict | yes (may be `{}`) | Validated against the block's `config_schema` |

**Edge shape** — two strings only:

| Key | Type | Required | Notes |
|---|---|---|---|
| `source` | string | yes | `"<node_id>:<port_name>"` — single colon |
| `target` | string | yes | `"<node_id>:<port_name>"` — single colon |

## 2. Common authoring pitfalls

These ten failure modes account for most rejections from
`validate_workflow` / `write_workflow`. Read them before drafting any
YAML.

1. **Wrong edge shape — the 4-field form.** The frontend canvas API
   (`POST /api/blocks/validate-connection`) uses `{source, source_port,
   target, target_port}`. Workflow YAML edges are TWO strings:
   `source` and `target`, each containing `node_id:port_name`. Using
   the canvas shape causes a `pydantic.ValidationError` listing
   missing `source: str` field.
2. **Wrong port separator.** `"load.images"`, `"load/images"`,
   `"load-images"` all fail. The character is a single colon.
3. **Hallucinated port names.** Agents guess `"image"` when the block
   exposes `"images"` (plural) or vice versa. Cure: call
   `get_block_schema(block_type)` and copy the exact
   `input_ports[].name` / `output_ports[].name` strings. Never type
   from memory.
4. **Wrong `block_type` casing or missing namespace.** Block types
   are namespaced (`imaging.threshold`, not `threshold`;
   `lcms.peak_pick`, not `peakpick`). `list_blocks` returns the
   canonical name.
5. **Missing required config field.** Each block's `config_schema`
   has a `required` list. `write_workflow` validates and rejects with
   the specific JSON-Schema error.
6. **Path escape.** `path: ../foo.tif` in a config is rejected at
   runtime — MCP context refuses paths outside the project root. Use
   project-relative paths.
7. **Circular edges (DAG violation).** The runtime rejects cycles at
   validation time. Most often introduced by re-targeting an edge to
   an upstream node; `validate_workflow` reports the cycle.
8. **Type-incompatible edges.** Connecting an `output_port` of type
   `DataFrame` to an `input_port` of type `Image` fails edge-time type
   checking. `get_block_schema` exposes the types; `list_types`
   exposes the hierarchy. Use both when wiring an unfamiliar pair of
   blocks.
9. **Missing `workflow:` top-level key.** A common slip: writing
   `id: ...` at the file root instead of nesting under `workflow:`.
   Schema validation rejects.
10. **`metadata` confused with `config`.** `metadata` is
    workflow-level free-form. Block config goes under each node's
    `config`.

## 3. Three worked examples

### Example A — simple linear (load → threshold → save)

```yaml
workflow:
  id: otsu-mask
  version: "1.0.0"
  description: Load a TIFF, Otsu-threshold, save the binary mask.
  nodes:
    - id: load
      block_type: imaging.load_image
      config:
        path: data/raw/beads.tif
    - id: thr
      block_type: imaging.threshold
      config:
        method: otsu
    - id: save
      block_type: imaging.save_image
      config:
        path: data/derived/beads_mask.tif
        format: tiff
  edges:
    - source: "load:images"
      target: "thr:image"
    - source: "thr:mask"
      target: "save:images"
```

### Example B — parallel fan-out (load → [denoise, threshold] → composite)

```yaml
workflow:
  id: fanout-compare
  version: "1.0.0"
  description: Side-by-side denoised vs raw thresholded mask.
  nodes:
    - id: load
      block_type: imaging.load_image
      config:
        path: data/raw/sample.tif
    - id: denoise
      block_type: imaging.denoise
      config:
        method: gaussian
        sigma: 1.0
    - id: thr_raw
      block_type: imaging.threshold
      config: {method: otsu}
    - id: thr_denoised
      block_type: imaging.threshold
      config: {method: otsu}
    - id: composite
      block_type: imaging.compare_masks
      config:
        labels: [raw, denoised]
  edges:
    - source: "load:images"
      target: "thr_raw:image"
    - source: "load:images"
      target: "denoise:image"
    - source: "denoise:image"
      target: "thr_denoised:image"
    - source: "thr_raw:mask"
      target: "composite:mask_a"
    - source: "thr_denoised:mask"
      target: "composite:mask_b"
```

Note `load:images` appears as the source of two edges — fan-out is
just multiple edges with the same `source`. The runtime handles
ref-counting; you do not need a "tee" block.

### Example C — AI block in a pipeline

```yaml
workflow:
  id: ai-assisted-segment
  version: "1.0.0"
  description: AI block paused for manual segmentation review before downstream stats.
  nodes:
    - id: load
      block_type: imaging.load_image
      config:
        path: data/raw/microplastics.tif
    - id: pre
      block_type: imaging.normalize
      config: {method: percentile, low_pct: 1.0, high_pct: 99.0}
    - id: seg
      block_type: ai.assisted_segmenter   # ADR-035 AIBlock subclass
      config:
        provider: claude-code             # or "codex"
        initial_prompt: "Segment each microplastic particle."
        timeout_sec: 600
    - id: stats
      block_type: imaging.intensity_stats
      config:
        output_path: data/derived/microplastics_stats.csv
  edges:
    - source: "load:images"
      target: "pre:image"
    - source: "pre:image"
      target: "seg:image"
    - source: "seg:mask"
      target: "stats:mask"
    - source: "pre:image"
      target: "stats:image"
```

The `ai.assisted_segmenter` block is an `AIBlock` (ADR-035). When the
runtime hits it, the engine spawns an embedded agent (claude-code or
codex) inside a PTY tab in the GUI. The embedded agent uses the same
MCP tool surface and terminates cleanly via
`mcp__scistudio__finish_ai_block(run_id, output_refs)`. See
`scistudio-debug-run` for the full `finish_ai_block` operational
contract.

## 4. Canonical tool-call sequence

For any new workflow, the canonical sequence is:

```
list_blocks                            # discover what blocks exist
get_block_schema(block_type)  ×3-5     # for each candidate, get exact ports + config_schema
list_types                             # only if connecting unfamiliar types
write_workflow(path, content)          # writes YAML, pre-validates against schema
validate_workflow(path)                # second pass: edges, type compat, DAG
run_workflow(path)                     # returns run_id
get_run_status(run_id)                 # poll until terminal
get_block_output(run_id, block_id, port)       # returns {ref, type, produced_at}
inspect_data(ref)                      # shape, dtype, axes
preview_data(ref, fmt)                 # thumbnail / first rows
```

Every write-class tool (`write_workflow`, `run_workflow`,
`cancel_run`, `update_block_config`, `finish_ai_block`) returns a
result envelope with a `next_step: str` field. Read it and follow.

## 5. When validation fails

`validate_workflow` returns `ValidateWorkflowResult(valid: bool, errors:
list[str])` — `valid=False` with a list of human-readable error strings.
(Note: this read-class tool does not carry a `next_step` field; the
canonical follow-up is documented here.) When `valid=False`:

1. Read **every** error, not just the first. They are independent.
2. If an error mentions a port name, call
   `get_block_schema(block_type)` for that block before retrying —
   never guess.
3. If an error mentions a type mismatch, call `list_types` to confirm
   the type hierarchy and find a valid bridge block if needed.
4. Fix all issues in **one** rewrite, then re-call `validate_workflow`.
5. Repeat at most three times. If still failing on the third attempt,
   stop and ask the user.

`write_workflow` itself is the write-class tool; its result envelope
carries `next_step` pointing at `validate_workflow`. Always follow it.

## 6. When a run fails

`get_run_status` returns
`GetRunStatusResult(run_id, state, progress={"block_states": {node_id: state, ...}}, errors=[BlockErrorEntry(block_id, error, summary), ...])`
when a block fails. The per-block state map is nested under
`progress.block_states` (NOT at the top level); per-block tracebacks
live in the top-level `errors` list (plural — multiple blocks may
fail). Terminal states are `succeeded` / `failed` / `cancelled`;
non-terminal states are `queued` / `running` / `unknown`. Pivot to
the **scistudio-debug-run** skill — it teaches the log-retrieval and
lineage-navigation steps. Do not re-run the workflow without
changing something; the failure mode will recur.

## Mandatory rules

- Always call `list_blocks` + `get_block_schema` for each block before
  writing a workflow.
- Always call `validate_workflow` after `write_workflow`. NEVER call
  `run_workflow` on an unvalidated YAML.
- Edge port format is `"node_id:port_name"` (single colon, two
  strings) — NOT the canvas 4-field shape.
- Always poll `get_run_status` until terminal (`succeeded` / `failed`
  / `cancelled`). Do not declare "done" before terminal.
- Read every `next_step` field on write-class result envelopes.

## Anti-patterns

- Using the 4-field edge shape from the canvas API.
- Skipping `validate_workflow` ("looks fine to me").
- Polling `get_run_status` once and declaring done on `running`.
- Hallucinating port names instead of calling `get_block_schema`.
- Re-running a failed workflow without diagnosing the failure first.
