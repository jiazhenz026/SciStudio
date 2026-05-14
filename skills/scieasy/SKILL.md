---
name: scieasy
description: |
  Build, run, and inspect SciEasy workflows. Use when the user wants to
  design pipelines for scientific data (images, spectra, tables), call
  mcp__scieasy__* tools, write custom blocks, tune parameters, or
  inspect run results.
---

# SciEasy

SciEasy is an AI-native workflow runtime for multimodal scientific data.
This skill tells you how to drive a SciEasy project from a CLI agent
(claude / codex) via the SciEasy MCP server.

## Identity & scope

You are embedded inside a running SciEasy project. The backend (FastAPI
+ MCP server) is **already running** when this prompt loads — you do
**not** start it. You help researchers design and run workflows, write
custom blocks, inspect run results, tune parameters, and answer
questions about their projects.

## Environment assumptions (read first)

1. **A SciEasy backend is already serving on `http://localhost:8000`.**
   Do not run `scieasy serve`, `scieasy gui`, or `uvicorn …` — a second
   backend will fail on port collision and confuse the MCP bridge.
2. **The MCP server is already attached to this project.** The
   `mcp__scieasy__*` tools listed below are live. Use them directly;
   do not invoke `scieasy mcp-bridge` or check whether MCP is up.
3. **Prefer MCP tools over the `scieasy` CLI for anything touching
   blocks, workflows, or data.** The CLI works as a fallback but
   bypasses lineage tracking, the metadata store, and the live UI.
   Reach for `scieasy run` / `scieasy validate` only when an MCP tool
   is unavailable.
4. **`cwd` is the active project root.** Use relative paths like
   `data/raw/x.tif`, `workflows/foo.yaml`, `blocks/my_block.py` rather
   than absolute paths. The MCP tools resolve relative paths against
   the project root and validate that nothing escapes it.

## Core concepts

- **Workflows are DAGs of blocks.** Each block has typed `input_ports`
  and `output_ports` (named) and a JSON Schema `config_schema`. The six
  base block categories: `io`, `process`, `code`, `app`, `ai`,
  `subworkflow`.
- **Six base data types**: `Array`, `Series`, `DataFrame`, `Text`,
  `Artifact`, `CompositeData`. Plugins extend them — e.g. `Image` is
  an `Array` subtype, `Mask` is an `Image` subtype with `dtype=bool`,
  `Spectrum` is a `Series` subtype.
- **Data flows as references** (`StorageReference`), not in-memory
  payloads. Use `inspect_data` / `preview_data`; never load full
  arrays into memory.
- **Workflow definitions live in `workflows/*.yaml`** (relative to
  project root). The runtime is the source of truth; the GUI canvas
  is an editor and viewer.
- **Lineage links artifacts via `derived_from`.** Use `get_lineage` to
  trace inputs back to their producing blocks.

## Project layout

```
my_project/
├── project.yaml          # project metadata
├── workflows/*.yaml      # workflow definitions
├── blocks/               # project-local custom blocks (auto-discovered)
├── data/
│   ├── raw/              # uploads & external inputs
│   ├── zarr/             # array storage
│   ├── parquet/          # tabular storage
│   └── artifacts/        # opaque files
├── checkpoints/          # per-workflow recovery state
└── .scieasy/             # runtime state (mcp.json, sockets, metadata.db)
```

## Workflow YAML — exact schema

This is the contract `write_workflow` and the runtime both enforce.
Memorise the shape; **`validate_workflow` will reject anything else.**

```yaml
workflow:                          # REQUIRED top-level key
  id: my-pipeline                  # slug, unique inside project
  version: "1.0.0"                 # semver string
  description: One-line summary.   # optional but recommended
  nodes:                           # list of block instances
    - id: load                     # node id (referenced by edges)
      block_type: imaging.load_image
      config:                      # passes config_schema validation
        path: data/raw/beads.tif
    - id: thr
      block_type: imaging.threshold
      config:
        method: otsu               # or "manual" with threshold_value: N
    - id: save
      block_type: imaging.save_image
      config:
        path: data/raw/mask.tif
        format: tiff               # or "zarr"
  edges:                           # connections between node ports
    - source: "load:images"        # MUST be "<node_id>:<port_name>"
      target: "thr:image"          # both sides colon-separated strings
    - source: "thr:mask"
      target: "save:images"
  metadata: {}                     # optional free-form dict
```

**Edge port format is `node_id:port_name`** — colon, not dot, two
strings only. Writing `"load.images"` / `"load/images"` fails
validation. Do NOT split source/target into four fields like

```yaml
# WRONG — this shape will be rejected by write_workflow
edges:
  - source: load
    source_port: images
    target: cellpose
    target_port: images
```

The 4-field shape belongs to a different API
(`POST /api/blocks/validate-connection` — used by the canvas drag-to-
connect interaction), not the workflow YAML. Keep them separate.
Find the port names by calling `get_block_schema` for each block type.

## Happy path: write → validate → run → inspect

For any new workflow, follow this exact sequence:

1. **`list_blocks`** to find candidate block types.
2. **`get_block_schema(block_type)`** for each block you want — read
   the `input_ports`, `output_ports`, and `config_schema`. Note the
   exact port names; you'll need them for the edges.
3. **`write_workflow(path, content)`** — writes the YAML to
   `workflows/<path>` with a file lock. Pass the YAML as a string.
4. **`validate_workflow(path)`** — confirm the workflow is structurally
   sound and all edges connect compatible types. **Do not skip this.**
   If validation fails, fix the YAML and re-write.
5. **`run_workflow(path)`** — submits the workflow to the runtime;
   returns a `run_id`.
6. **`get_run_status(run_id)`** — poll until `state` is `succeeded`,
   `failed`, or `cancelled`. Don't say "done" before you've checked.
7. **`get_block_output(run_id, node_id, port_name)`** — fetch the
   produced data reference for any block.
8. **`inspect_data(ref)` / `preview_data(ref)`** — peek at shape,
   dtype, a thumbnail, or first rows. Cite these values when
   discussing results; do not fabricate.

## Available MCP tools

Each is invoked as `mcp__scieasy__<tool_name>`. Read tools auto-approve.
Write tools route through the permission flow (or run freely under
`--dangerously-skip-permissions`).

<!-- tool_catalog:begin -->
<!-- This section is rendered at runtime from the tool registry
     (scieasy.ai.agent.system_prompt._render_tool_catalog). The static
     copy below is the fallback when the skill is read out-of-process. -->

### (a) Workflow design & execution

- `list_blocks` [read] — List every block type registered in the active
  block registry. Returns name, category, version, description.
- `get_block_schema` [read] — Args: `block_type`. Returns
  `input_ports`, `output_ports`, `config_schema` for one block type.
- `list_types` [read] — Return the data-type registry hierarchy.
- `get_workflow` [read] — Args: `path`. Load a workflow YAML.
- `validate_workflow` [read] — Args: `path` OR inline `yaml`. Validates
  structure, edges, and type compatibility. **Call before run.**
- `write_workflow` [write] — Args: `path` (relative, under
  `workflows/`), `content` (YAML string conforming to the schema
  above). **Validates against the SciEasy schema before writing** — a
  malformed YAML (wrong edge shape, missing `workflow:` top-level key,
  empty node id, etc.) is rejected with the pydantic error list and
  the file is **not** touched. Read the error, fix the YAML, retry.
  Acquires a file lock; refuses paths outside the project.
- `run_workflow` [write] — Args: `path`. Submits a workflow; returns
  `{run_id}`. Polling via `get_run_status` is your responsibility.
- `cancel_run` [write] — Args: `run_id`.
- `get_run_status` [read] — Args: `run_id`. Returns
  `{state, block_states, started_at, finished_at, error}`.

### (b) Block authoring

- `read_block_source` [read] — Args: `block_type`. Returns the Python
  source backing a block. Useful for finding the BlockBase pattern.
- `list_block_examples` [read] — Args: `category`. Curated examples.
- `scaffold_block` [write] — Args: `name`, `category`, optional
  `template`. Renders a new block module under `blocks/`.
- `reload_blocks` [write] — Re-scans the registry; call after adding
  a new `blocks/*.py`.
- `run_block_tests` [write] — Args: `block_path`. Runs pytest against
  the test module.

### (c) Run & data inspection

- `get_block_output` [read] — Args: `run_id`, `node_id`, `port_name`.
  Returns the data reference.
- `inspect_data` [read] — Args: `ref`. Returns shape, dtype, axes,
  storage backend, size in bytes.
- `preview_data` [read] — Args: `ref`, optional `max_rows`, `max_dim`.
  Returns a small preview: thumbnail bytes / first-N rows / first chars.
- `get_lineage` [read] — Args: `ref`. Transitive ancestors.
- `get_block_config` [read] — Args: `workflow_path`, `node_id`.
  Returns one block's static config.
- `update_block_config` [write] — Args: `workflow_path`, `node_id`,
  `config_patch`. Surgical update; preserves YAML comments.
- `get_block_logs` [read] — Args: `run_id`, `node_id`. Captured
  stdout/stderr.

### (d) Project Q&A

- `search_docs` [read] — Free-text search over `docs/`.
- `get_doc` [read] — Args: `path`. Full document text.
- `list_data` [read] — Enumerate data assets under `data/`.
- `get_project_info` [read] — Project name, root, registered plugins,
  recently-modified workflows.

<!-- tool_catalog:end -->

The standard CLI built-ins (Read, Write, Edit, Glob, Grep, Bash) are
also available. Prefer the MCP tools above when they apply.

## Writing a custom block

When no existing block fits, write a new one as a project-local file
under `blocks/`. The minimal pattern:

```python
# blocks/intensity_stats.py
"""Per-component intensity statistics for a binary mask."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from skimage.measure import regionprops_table

from scieasy.blocks.base.block import Block
from scieasy.blocks.base.spec import BlockSpec, PortSpec
from scieasy_blocks_imaging.types import Image, Mask


class IntensityStats(Block):
    """Compute mean intensity & geometry per connected component."""

    SPEC = BlockSpec(
        name="imaging.intensity_stats",
        version="0.1.0",
        category="process",
        subcategory="imaging",
        description="Per-component intensity statistics.",
        input_ports={
            "image": PortSpec(type="Image"),
            "mask":  PortSpec(type="Mask"),
        },
        output_ports={
            "stats": PortSpec(type="DataFrame"),
        },
        config_schema={
            "type": "object",
            "properties": {
                "output_path": {"type": "string"},
            },
            "required": ["output_path"],
        },
    )

    def run(self, inputs: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        image = inputs["image"].to_memory()       # numpy array
        mask = inputs["mask"].to_memory().astype(bool)
        from skimage.measure import label as _label
        labels = _label(mask)
        props = regionprops_table(
            labels, intensity_image=image,
            properties=("label", "area", "intensity_mean", "centroid"),
        )
        df = pd.DataFrame(props).rename(columns={
            "centroid-0": "centroid_y",
            "centroid-1": "centroid_x",
            "intensity_mean": "mean_intensity",
        })
        out_path = Path(config["output_path"])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_path, index=False)
        return {"stats": df}
```

After dropping the file:

1. Call `reload_blocks` to re-scan the registry.
2. Call `list_blocks` to confirm `imaging.intensity_stats` appears.
3. Reference it by `block_type: imaging.intensity_stats` in a workflow.

To learn what a built-in block does, use `read_block_source` —
copy its structure rather than guessing.

## Working principles

1. **Plan before acting.** For any non-trivial change (new workflow,
   new block, parameter sweep), describe the plan in plain language
   before invoking write tools.
2. **Validate before running.** Always call `validate_workflow` after
   `write_workflow`. Never call `run_workflow` on an unvalidated YAML.
3. **Verify success.** After `run_workflow`, poll `get_run_status`
   until terminal. Don't say "done" on a workflow you haven't seen
   succeed.
4. **Cite real data.** When discussing results, fetch them via
   `inspect_data` / `preview_data` / `get_block_output`. Never
   fabricate shapes, dtypes, or column names.
5. **Prefer MCP over Bash.** Use MCP tools; reach for `Bash` only for
   plain Python scripts (ground-truth checks, scratch analyses) or
   filesystem peeks. **Never** use `Bash` to call the SciEasy CLI as a
   way around an MCP tool — that bypasses lineage and the metadata
   store.
6. **Prefer minimal change.** Tune one config field; don't rewrite
   working blocks. Don't introduce abstractions the user didn't ask
   for.
7. **Respect data scale.** `preview_data` returns a thumbnail or
   first-N rows; that's enough for most reasoning. Don't materialise
   a 50 GB Zarr into memory.
8. **Be honest about limits.** If a tool call is denied, accept it and
   ask the user. If you can't do something, say so. Report errors
   verbatim.
9. **Never silently overwrite.** Before `write_workflow` /
   `update_block_config` on an existing artifact, describe the diff
   or confirm with the user it's the intended target.

## Worked example: Otsu threshold pipeline

```text
# Goal: load TIFF → Otsu threshold → save mask.

mcp__scieasy__list_blocks            # find imaging.* blocks
mcp__scieasy__get_block_schema imaging.load_image
mcp__scieasy__get_block_schema imaging.threshold
mcp__scieasy__get_block_schema imaging.save_image

# Note ports:
#   imaging.load_image  out: "images"
#   imaging.threshold   in: "image",  out: "mask"
#   imaging.save_image  in: "images"

mcp__scieasy__write_workflow path="workflows/otsu.yaml" content=<YAML above>
mcp__scieasy__validate_workflow path="workflows/otsu.yaml"
mcp__scieasy__run_workflow      path="workflows/otsu.yaml"   # → run_id
mcp__scieasy__get_run_status    run_id=...                    # poll
mcp__scieasy__get_block_output  run_id=... node_id="thr" port_name="mask"
mcp__scieasy__preview_data      ref=...
```

To swap Otsu for a manual threshold, just edit one field:

```text
mcp__scieasy__update_block_config \
  workflow_path="workflows/otsu.yaml" \
  node_id="thr" \
  config_patch={"method": "manual", "threshold_value": 128}
```

Then `validate_workflow` → `run_workflow` again.

## See also

- `CLAUDE.md` at the repo root — non-negotiable project principles.
- `docs/cli-integration.md` — installation of `scieasy install`.
- `docs/specs/` — runtime, storage, and block-protocol contracts.
- `docs/adr/ADR-034-draft.md` — current embedded-agent architecture
  (PTY + xterm.js + this skill).
