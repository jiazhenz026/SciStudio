# ADR-040 Phase 2b — Skill-design Investigation Deliverable

> Authored 2026-05-16 by `AC40-skill` (skill-design investigation agent).
> Read-only investigation feeding Phase 2c (I40b) skill content authoring.
> Companion to [ADR-040](../adr/ADR-040.md) §3.4 / §3.5 and [code-scope manifest](./adr-040-code-scope.md).
> Issue: [#1051](https://github.com/zjzcpj/SciEasy/issues/1051). Umbrella: [#1011](https://github.com/zjzcpj/SciEasy/issues/1011).
> Source state inspected: `track/adr-040` HEAD (commit `a697803`) for the S40a skeleton + WIP at `.claude/worktrees/i40a-impl/` (uncommitted, read-only) for I40a direction.

## How to use this document

- **Phase 2c (I40b) skill content authoring** consumes this whole file plus ADR-040 §3.4. No further upstream research should be required.
- The 9 top-level sections are the dispatch contract from the Phase 2b prompt; do not delete or renumber.
- Worked examples (§1.3, §2.6, §5.x) are **drop-in copy** for the matching skill bodies — they have been written against the real Block ABC / port API verified on `track/adr-040` and should compile/validate without rework. Where the live API differs from the existing repo-root `skills/scieasy/SKILL.md` worked example, this document is the canonical source.
- External-harness comparisons in §4 are explicitly tagged **verified** (sourced from the live docs cited in ADR-040 §10 or directly inspected) or **from training, unverified** so the Phase 2c agent can choose how heavily to lean on each recommendation.

---

## 0. Timing context — I40a still in flight

The S40a skeleton landed on `track/adr-040/fastmcp` (PR #1030, merged into `track/adr-040`) but the I40a impl PR is mid-flight in the user's worktree at `.claude/worktrees/i40a-impl/`. As of this writing, the WIP shows:

- `src/scieasy/ai/agent/mcp/server.py` — `MCPServer` lifecycle wrapper now wraps a real `fastmcp.FastMCP` instance (verified). Module-scope `mcp = FastMCP(name="scieasy-mcp", version="0.1.0")`. Transport (POSIX UDS / Windows TCP loopback) is preserved verbatim from the ADR-033-era hand-rolled server so the bridge subprocess (`scieasy mcp-bridge`) keeps working.
- `src/scieasy/ai/agent/system_prompt.py` — `_load_skill_md` prefers `importlib.resources` for the relocated `scieasy._skills.scieasy.SKILL.md` but **retains the walk-up fallback** to `<repo>/skills/scieasy/SKILL.md` because S40b's relocation has not been wired into this branch yet (per the file's own docstring comment marked `TODO(#1012)`). `_render_project_context` (closes #825) is shaped per ADR §3.3 but the live impl status varies — Phase 2c should verify once I40a lands.
- Each `tools_*.py` file: tool bodies are being filled in (compare `track/adr-040` HEAD `NotImplementedError` bodies → WIP partial-real bodies). The 26 `@mcp.tool` decorators with Pydantic return-model shapes are stable; what changes is the body.
- `_render_tool_catalog` placeholder state — the S40a skeleton produces a hand-rolled fallback string when FastMCP enumeration is unavailable; I40a switches it to live `await mcp.list_tools()`. Phase 2c skills should be robust to BOTH return styles (the body content describes the tools, not the catalog rendering itself).

**Recommendation for Phase 2c**: author the skill content against the **finalized tool shape described in §3 of this document** (which is authoritative per ADR-040 §3.1/§3.2/§3.2a), not against whichever transient state I40a happens to be in when the dispatch happens. After I40a fully lands and merges, schedule a **5-minute polish pass** to tighten any `next_step:` strings or `warnings:` wording the skills quote — but defer this to a small follow-up issue if the wording drift is minor.

---

## 1. SciEasy workflow development patterns

Source of truth inspected: `src/scieasy/workflow/`, the existing repo-root `skills/scieasy/SKILL.md` ("Workflow YAML — exact schema" section), `tests/integration/`, and `docs/specs/`. The YAML schema is enforced by `validate_workflow` (`src/scieasy/ai/agent/mcp/tools_workflow.py:306` on `track/adr-040`) and by `write_workflow` pre-write (lines 347+).

### 1.1 Canonical workflow YAML shape

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

**Top-level keys**:

| Key | Type | Required | Notes |
|---|---|---|---|
| `workflow.id` | string | yes | Slug; unique per project; used as run output prefix |
| `workflow.version` | string | yes | Semver; runtime checks compatibility |
| `workflow.description` | string | no | Shown in GUI; recommended |
| `workflow.nodes` | list[node] | yes | Block instances |
| `workflow.edges` | list[edge] | yes | Empty list `[]` is legal for a single-block workflow |
| `workflow.metadata` | dict | no | Free-form; reserved for tool-specific extensions |

**Node shape**:

| Key | Type | Required | Notes |
|---|---|---|---|
| `id` | string | yes | Unique within the workflow |
| `block_type` | string | yes | Must match a registered block (call `list_blocks`) |
| `config` | dict | yes (may be `{}`) | Validated against the block's `config_schema` |

**Edge shape**:

Two strings only:

| Key | Type | Required | Notes |
|---|---|---|---|
| `source` | string | yes | `"<node_id>:<port_name>"` — single colon |
| `target` | string | yes | `"<node_id>:<port_name>"` — single colon |

### 1.2 Common authoring pitfalls

Observed from `tests/integration/test_*.py` failure modes and live agent traces:

1. **Wrong edge shape — the 4-field form.** The frontend canvas API (`POST /api/blocks/validate-connection`) uses `{source, source_port, target, target_port}`. Agents who have seen that surface frequently copy it into workflow YAML; `write_workflow` rejects with a `pydantic.ValidationError` listing the missing `source: str` field.
2. **Wrong port separator.** `"load.images"`, `"load/images"`, `"load-images"` all fail. The character is a single colon.
3. **Hallucinated port names.** Agents guess `"image"` when the block exposes `"images"` (plural) or vice versa. Cure: `get_block_schema(block_type)` returns the exact `input_ports[].name` / `output_ports[].name`. Cite those names; do not type from memory.
4. **Wrong `block_type` casing or missing namespace.** Block types are namespaced (`imaging.threshold`, not `threshold`; `lcms.peak_pick`, not `peakpick`). `list_blocks` returns the canonical name.
5. **Missing required config field.** Each block's `config_schema` has a `required` list. `write_workflow` validates and rejects with the specific JSON-Schema error.
6. **Path escape.** `path: ../foo.tif` in a config is rejected at runtime — `MCPContext._safe_under` (in `src/scieasy/ai/agent/mcp/_context.py:112`) refuses paths outside the project root. Use project-relative paths.
7. **Circular edges (DAG violation).** The runtime rejects cycles at validation time. Agents accidentally create them by re-targeting an edge to an upstream node; `validate_workflow` reports the cycle.
8. **Type-incompatible edges.** Connecting `output_ports.dataframe: DataFrame` to `input_ports.image: Image` fails edge-time type checking. `get_block_schema` exposes the types; `list_types` exposes the hierarchy. Use both when wiring an unfamiliar pair of blocks.
9. **Missing `workflow:` top-level key.** A common slip: writing `id: ...` at the file root instead of nesting under `workflow:`. Schema validation rejects.
10. **`metadata` confused with `config`.** `metadata` is workflow-level free-form. Block config goes under each node's `config`.

### 1.3 Three worked examples

**Example A — simple linear (load → threshold → save):**

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

**Example B — parallel fan-out (load → [denoise, threshold] → composite):**

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

Note `load:images` appears as the source of two edges — fan-out is just multiple edges with the same `source`. The runtime handles ref-counting; the agent does not need a "tee" block.

**Example C — AI block in a pipeline (interactive segmentation step):**

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

Distinguishing feature: the `ai.assisted_segmenter` block is an `AIBlock` (ADR-035). When the runtime hits it the engine spawns the embedded agent (claude-code or codex) inside a PTY tab in the GUI. The agent uses the **same** MCP tool surface this document describes — it sees the AI block's run-dir, can call `mcp__scieasy__finish_ai_block` to terminate cleanly with output refs, and pauses the workflow until either a successful `finish_ai_block` call or a timeout. See §8 for the `finish_ai_block` placement decision.

### 1.4 Recommended tool-call sequence

For any new workflow, the canonical sequence is:

```
list_blocks                           # discover what blocks exist
get_block_schema(b)  ×3-5             # for each candidate, get exact port names + types + config_schema
list_types                            # only if connecting unfamiliar types
write_workflow(path, content)         # writes YAML, pre-validates against schema
validate_workflow(path)               # second pass: edges, type compat, DAG
run_workflow(path)                    # returns run_id
get_run_status(run_id)                # poll until terminal
get_block_output(run_id, node_id, port_name)   # fetch refs from interesting blocks
inspect_data(ref)                     # shape, dtype, axes
preview_data(ref)                     # thumbnail / first rows
```

**What to do when `validate_workflow` fails.** The result envelope shape (per S40a Pydantic models in `tools_workflow.py`) is `{ok: bool, errors: list[ValidationError], next_step: str}`. The skill must teach: read every error, do **not** assume only the first one matters, fix every issue in one re-write, re-call `validate_workflow`. If errors mention a port name, call `get_block_schema(block_type)` for the relevant block before retrying — never guess. Repeat ≤3 times; if still failing on the 3rd attempt, stop and ask the user.

**What to do when `run_workflow` succeeds but a block fails.** Status will be `{state: "failed", block_states: {node_id: "failed", ...}, error: "..."}`. Call `get_block_logs(run_id, node_id)` for the failed node. Read stdout/stderr. Common failures: missing input file (config path), out-of-memory on a too-large input, a plugin import error from a stale `reload_blocks`.

---

## 2. SciEasy block development patterns

Source of truth inspected on `track/adr-040`:

- `src/scieasy/blocks/base/block.py` — Block ABC. `Block.run(self, inputs, config) -> dict[str, Any]` is abstract. State machine `BlockState.IDLE → READY → RUNNING → DONE|PAUSED|ERROR|CANCELLED`.
- `src/scieasy/blocks/base/ports.py` — `Port` / `InputPort` / `OutputPort` dataclasses (kw_only). Fields: `name: str`, `accepted_types: list[type]`, `required: bool = True`, `description: str = ""`. The Port API is **inheritance-aware**: `port_accepts_type(port, data_type)` walks the type hierarchy.
- `src/scieasy/blocks/base/config.py` — `BlockConfig` (Pydantic BaseModel), accepts arbitrary keys, validated against `config_schema` at construct.
- `src/scieasy/blocks/process/process_block.py` — `ProcessBlock` adds `process_item(item, config, state)` for per-item iteration over Collections (ADR-020 transparency).
- `tests/integration/test_block_sdk_e2e.py` — canonical block-authoring contract test.
- ADR-025 (entry points): plugins register via `[project.entry-points."scieasy.blocks"]` in `pyproject.toml`. Project-local `blocks/*.py` are auto-discovered without entry points.
- ADR-030: `config_schema` is **MRO-merged** across the inheritance chain (subclass schemas extend parent schemas; the registry computes the effective schema at scan time).

### 2.1 The Block ABC contract

```python
class Block(ABC):
    # Class-level metadata (ClassVars):
    name: ClassVar[str] = "Unnamed Block"            # human-readable
    description: ClassVar[str] = ""                  # one-line
    version: ClassVar[str] = "0.1.0"                 # semver
    subcategory: ClassVar[str] = ""                  # palette grouping (#588)
    # base_category is INFERRED from the class hierarchy (io / process / code / app / ai / subworkflow)
    # — do NOT set it as a ClassVar.

    input_ports: ClassVar[list[InputPort]] = []
    output_ports: ClassVar[list[OutputPort]] = []
    config_schema: ClassVar[dict[str, Any]] = {"type": "object", "properties": {}}

    @abstractmethod
    def run(self, inputs: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        """Subclasses MUST override. Return {output_port_name: data_obj_or_ref}."""
```

**Critical**: agents must NOT set `base_category` as a ClassVar. It is inferred from which abstract base the class extends (`ProcessBlock`, `IOBlock`, `CodeBlock`, `AppBlock`, `AIBlock`, `SubWorkflowBlock`). Setting it as a ClassVar is a contract violation that the registry scan ignores; the skill should teach the right pattern (subclass the right parent), not the wrong one (set a ClassVar).

**Note on the existing repo-root `skills/scieasy/SKILL.md` example**: the "Writing a custom block" worked example currently uses an older `BlockSpec` / `PortSpec` dataclass pattern that no longer exists in the codebase (`src/scieasy/blocks/base/spec.py` does not exist on `track/adr-040`; ports use `InputPort` / `OutputPort` instances directly in the `input_ports` ClassVar list). **Phase 2c MUST refresh this example** to match the live API verified in §2.6 below. This is part of the §3.4 split work and is one of the most concrete reasons the existing skill is overdue for restructure.

### 2.2 The `_spec_from_class` mechanism + strict version checking

The block registry (in `src/scieasy/core/blocks/registry.py`, frozen contract — out of scope for Phase 2b) scans installed plugins and project-local `blocks/` for `Block` subclasses and computes a `BlockSpec` for each. The spec is derived from class metadata (name, version, ports, config_schema). Version mismatches (e.g. two plugins registering `imaging.threshold` at different `version` strings) cause the registry to refuse loading. The skill must teach: bump `version` on every meaningful contract change; do not silently re-use a version across incompatible bodies.

### 2.3 Plugin entry-point pattern (ADR-025)

For shipping a block as a pip-installable plugin:

```toml
# pyproject.toml of the plugin package
[project.entry-points."scieasy.blocks"]
mypkg = "mypkg"

[project.entry-points."scieasy.types"]
mypkg = "mypkg.types"
```

The skill should teach: for **most user blocks**, drop a `*.py` into the project's `blocks/` directory — it is auto-discovered on `reload_blocks`. Use entry points only when shipping a reusable plugin across multiple projects.

### 2.4 `config_schema` MRO merge (ADR-030)

If `MyBlock(ProcessBlock)` declares a `config_schema` and `ProcessBlock` itself declares one, the effective schema is **merged** (subclass adds to parent; subclass wins on duplicate keys). The skill should teach this so agents do not duplicate parent fields and do not assume their subclass schema is the full schema.

### 2.5 Port-type narrowness rule (ADR-040 §3.2a)

This is the **single most important rule** the `scieasy-write-block` skill must enforce.

**The rule**: pick the **most specific applicable** `DataObject` subclass for every port. Use the abstract `DataObject` root **only** when the block legitimately accepts any type (e.g. `SubWorkflowBlock` inputs, generic `save_data` / `load_data` blocks).

**Why it matters**: preview rendering, edge-time type checking, lineage-graph navigation, and AI-suggestion features all dispatch on port types. A `DataObject`-typed output port means "anything to anything" — the preview pane can't render it, the canvas can't validate connections, the AI block can't propose downstream candidates.

**Two enforcement layers complementing the skill**:

1. **MCP soft validation (§3.2a)**: `scaffold_block` returns a `warnings: list[str]` field. If the agent supplied `DataObject` for any port, the warning fires.
2. **PostToolUse hook (§3.6)**: `enforce_concrete_port_types.py` AST-parses the written file after Edit/Write/scaffold_block and re-flags the same issues — catches the case where the agent bypasses `scaffold_block` entirely.

The skill (Layer 1 / L2 in the defense-in-depth) preempts both by teaching the rule before the agent writes.

**The remediation when the agent needs a new type**: declare a new `DataObject` subclass in the plugin's `scieasy.types` entry point. Do NOT silently widen to `DataObject`.

### 2.6 Worked example — thresholding block from scratch

Drop-in for `scieasy-write-block` skill body. Written against the live Block ABC and verified against the `imaging.normalize` block in `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/preprocess/normalize.py`.

```python
# blocks/threshold_simple.py — project-local custom block.
"""Simple Otsu / manual threshold block (worked example for skill teaching)."""
from __future__ import annotations

from typing import Any, ClassVar

import numpy as np

from scieasy.blocks.base.config import BlockConfig
from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy_blocks_imaging.types import Image, Mask


class ThresholdSimple(ProcessBlock):
    """Otsu or manual thresholding to produce a binary mask."""

    # --- registry metadata ----------------------------------------------
    type_name: ClassVar[str] = "imaging.threshold_simple"
    name: ClassVar[str] = "Threshold (simple)"
    description: ClassVar[str] = "Otsu or manual threshold → binary mask."
    version: ClassVar[str] = "0.1.0"
    subcategory: ClassVar[str] = "segmentation"
    algorithm: ClassVar[str] = "threshold_simple"

    # --- ports (CONCRETE types — Image, Mask — never DataObject) --------
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="image", accepted_types=[Image], required=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="mask", accepted_types=[Mask]),
    ]

    # --- config_schema (JSON-Schema; MRO-merged with parent) ------------
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "enum": ["otsu", "manual"],
                "default": "otsu",
            },
            "threshold_value": {
                "type": "number",
                "description": "Required when method == 'manual'.",
            },
        },
        "required": ["method"],
    }

    def process_item(self, item: Image, config: BlockConfig, state: Any = None) -> Mask:
        """Threshold one Image → one Mask. ProcessBlock handles Collection iteration."""
        arr = item.to_memory()  # numpy ndarray
        method = config["method"]
        if method == "otsu":
            from skimage.filters import threshold_otsu
            t = float(threshold_otsu(arr))
        elif method == "manual":
            if "threshold_value" not in config:
                raise ValueError("method='manual' requires config.threshold_value.")
            t = float(config["threshold_value"])
        else:
            raise ValueError(f"Unknown method {method!r}.")
        return Mask(data=(arr > t).astype(bool), axes=item.axes)
```

Then the agent's tool sequence:

```
mcp__scieasy__list_blocks                              # confirm imaging.threshold_simple is NOT already registered
mcp__scieasy__list_types                               # confirm Image, Mask types exist in the registry
mcp__scieasy__scaffold_block(
    name="threshold_simple",
    category="process",
    input_ports={"image": {"type": "Image", "required": true}},
    output_ports={"mask": {"type": "Mask"}}
)                                                      # writes blocks/threshold_simple.py; warnings: []
# agent edits the scaffolded file to fill in process_item body
mcp__scieasy__reload_blocks                            # re-scans the registry
mcp__scieasy__list_blocks                              # confirm imaging.threshold_simple appears
mcp__scieasy__run_block_tests block_path=blocks/threshold_simple.py
```

**E2E (g) acceptance criterion**: an agent operating from this worked example alone (no prior context) should be able to author and register a working thresholding block end to end. The example is intentionally complete enough that the agent can copy it, edit method names, swap the algorithm, and produce a working block.

### 2.7 Common block-authoring pitfalls

1. **`DataObject` port types** — covered in §2.5. Most common drift.
2. **Setting `base_category` as a ClassVar** — silently ignored by the registry; agent thinks they declared the category but the registry infers it from the parent class.
3. **Forgetting `version` bump** — registry collision on `reload_blocks`.
4. **`run()` returning a non-dict** — `Block.run` MUST return `dict[str, Any]` keyed by output port name. Returning a list, tuple, or scalar fails downstream type-resolution.
5. **In-memory data loading without need** — `item.to_memory()` materialises the whole array; for streaming use `item.iter_chunks()`. The skill should mention this but not over-emphasize (most agent-authored blocks are simple per-item transforms; in-memory is fine for <1GB).
6. **Reusing a block when authoring (#875 violation)** — covered in §5.2.

---

## 3. Finalized MCP tool shape (per `track/adr-040` HEAD + I40a WIP direction)

### 3.1 The 26 tools

Verified count: `len(TOOL_REGISTRY) == 26` (asserted in `tests/ai/test_system_prompt.py:28` and `tests/ai/test_finish_ai_block_skeleton.py:30`). Breakdown reconciles with `docs/planning/adr-040-code-scope.md` §1.2.

| # | Tool name | Module | Class | I40a body state | Result model | `next_step` field | `warnings` field |
|---|---|---|---|---|---|---|---|
| 1 | `list_blocks` | `tools_workflow.py` | read | partial | `ListBlocksResult` | n/a | n/a |
| 2 | `get_block_schema` | `tools_workflow.py` | read | partial | `BlockSchemaResult` | n/a | n/a |
| 3 | `list_types` | `tools_workflow.py` | read | partial | `ListTypesResult` | n/a | n/a |
| 4 | `get_workflow` | `tools_workflow.py` | read | partial | `GetWorkflowResult` | n/a | n/a |
| 5 | `validate_workflow` | `tools_workflow.py` | read | partial | `ValidateWorkflowResult` | n/a | n/a |
| 6 | `write_workflow` | `tools_workflow.py` | write | partial | `WriteWorkflowResult` | yes | n/a |
| 7 | `run_workflow` | `tools_workflow.py` | write | partial | `RunWorkflowResult` | yes | n/a |
| 8 | `cancel_run` | `tools_workflow.py` | write | partial | `CancelRunResult` | yes | n/a |
| 9 | `get_run_status` | `tools_workflow.py` | read | partial | `RunStatusResult` | n/a | n/a |
| 10 | `finish_ai_block` | `tools_workflow.py` | write | partial | `FinishAIBlockResult` | yes | n/a |
| 11 | `read_block_source` | `tools_authoring.py` | read | partial | `ReadBlockSourceResult` | n/a | n/a |
| 12 | `list_block_examples` | `tools_authoring.py` | read | partial | `ListBlockExamplesResult` | n/a | n/a |
| 13 | `scaffold_block` | `tools_authoring.py` | write | partial | `ScaffoldBlockResult` | yes | **yes** (§3.2a) |
| 14 | `reload_blocks` | `tools_authoring.py` | write | partial | `ReloadBlocksResult` | yes | n/a |
| 15 | `run_block_tests` | `tools_authoring.py` | write | partial | `RunBlockTestsResult` | yes | n/a |
| 16 | `get_block_output` | `tools_inspection.py` | read | partial | `GetBlockOutputResult` | n/a | n/a |
| 17 | `inspect_data` | `tools_inspection.py` | read | partial | `InspectDataResult` | n/a | n/a |
| 18 | `preview_data` | `tools_inspection.py` | read | partial | `PreviewDataResult` | n/a | n/a |
| 19 | `get_lineage` | `tools_inspection.py` | read | partial | `GetLineageResult` | n/a | n/a |
| 20 | `get_block_config` | `tools_inspection.py` | read | partial | `GetBlockConfigResult` | n/a | n/a |
| 21 | `update_block_config` | `tools_inspection.py` | write | partial | `UpdateBlockConfigResult` | yes | n/a |
| 22 | `get_block_logs` | `tools_inspection.py` | read | partial | `GetBlockLogsResult` | n/a | n/a |
| 23 | `search_docs` | `tools_qa.py` | read | partial | `SearchDocsResult` | n/a | n/a |
| 24 | `get_doc` | `tools_qa.py` | read | partial | `GetDocResult` | n/a | n/a |
| 25 | `list_data` | `tools_qa.py` | read | partial | `ListDataResult` | n/a | n/a |
| 26 | `get_project_info` | `tools_qa.py` | read | partial | `GetProjectInfoResult` | n/a | n/a |

(All `partial`: S40a skeleton bodies raise `NotImplementedError` with `# TODO(#1012)` blocks. I40a WIP is filling in the bodies. Phase 2c skill content can rely on the documented function signatures + return-model shapes — those are stable per ADR-040 §3.1.)

### 3.2 Pydantic envelope conventions

Per ADR-040 §3.1 + §3.2:

- **Read-class tools** return a Pydantic `BaseModel` carrying the read result. No `next_step` field.
- **Write-class tools** carry a `next_step: str` field pointing at the canonical follow-up tool. E.g. `WriteWorkflowResult.next_step = "Call mcp__scieasy__validate_workflow with the same path before run_workflow."` The skill body should reference `next_step` so agents form the habit of reading it.
- **`scaffold_block`** uniquely carries `warnings: list[str]` (§3.2a). The skill must teach: after every `scaffold_block` call, **read every warning** before proceeding.

### 3.3 Per-tool description style

Per ADR-040 §3.2, every tool docstring follows:

```
<imperative one-liner>.

Use when <positive trigger>.
Do NOT use to <negative anti-pattern>.

Args:
    ...

Returns:
    <ResultModel>: ...
```

The skills should mirror this voice in their own content so the agent gets a consistent register across the prompt + tool-descriptions surface.

### 3.4 `_render_tool_catalog` placeholder note

The S40a base SKILL.md has `<!-- tool_catalog:begin/end -->` markers; `_render_tool_catalog` was a placeholder in S40a (returned a hand-rolled fallback string from a hard-coded inventory). I40a WIP is replacing it with a live `await mcp.list_tools()` rendering. **Phase 2c implication**: the body content of each task skill describes tools by **name and behavior**, not by quoting the catalog rendering. This keeps the skills robust to either rendering style.

---

## 4. External harness prior art — comparison + recommendations

Below, all entries marked "**verified**" were inspected against the documentation cited in ADR-040 §10 (Anthropic Skills, OpenAI Skills, AGENTS.md) or directly inspected. Entries marked "**from training, unverified**" should be treated as best-effort recall and re-checked by Phase 2c if the recommendation is load-bearing.

### 4.1 Comparison table

| Harness | Skill / tool-context shape | Frontmatter format | Progressive disclosure | Notable |
|---|---|---|---|---|
| **Anthropic Skills SDK** (verified — code.claude.com/docs/en/skills) | One directory per skill, `SKILL.md` body, optional `resources/` siblings. Skill chosen by Claude based on `description` frontmatter matching user turn. | YAML frontmatter at the top of `SKILL.md`: `name` (slug), `description` (the trigger spec — Claude reads this to decide invocation). | Two-level: (1) top-level `description` is always in context; (2) body is loaded when Claude invokes the skill. | The `name` + `description` MUST appear together. Description must describe BOTH what the skill does AND when to use it. |
| **OpenAI Codex Skills** (verified — developers.openai.com/codex/skills) | Same as Anthropic Skills SDK in shape (`SKILL.md` + frontmatter). Designed for cross-portability. | Identical YAML frontmatter convention. | Same two-level model. | Recently shipped (mid-2026); designed for parity with Anthropic. |
| **AGENTS.md convention** (verified — developers.openai.com/codex/guides/agents-md) | Single root file `AGENTS.md`; identity + non-negotiable rules + index of skills. NOT a skill in itself; complementary to skills. | No frontmatter — plain markdown. | Always in context (loaded at session start). | Designed as the universal counterpart to `CLAUDE.md`. ADR-040 §3.5 follows this exactly. |
| **n8n** (from training, unverified) | UI-driven workflow node catalog with embedded AI-agent nodes (LangChain). Each node has a schema + parameter UI. AI-agent context is per-node config, not a skill. | n/a (UI; no markdown skill convention). | n/a. | The "AI Agent" node accepts a system prompt as a parameter — no separation between identity rules and tool teaching. Single-blob prompt is the inverse of the split this ADR proposes; observation: n8n users report drift on long blocks of tool instructions, mirroring SciEasy's #832/#825 motivation. |
| **Langflow / LangChain LangGraph** (from training, unverified) | Tool context is per-agent system message + per-tool docstrings. No formal "skill" abstraction; tools are first-class with structured `description` fields. | n/a. | Tools are auto-rendered in the system prompt at agent construction; no dynamic disclosure within a session. | Strong precedent for treating tool docstrings as the primary teaching surface. SciEasy's ADR-040 §3.2 (rewriting tool descriptions + `next_step`) follows this exact pattern. |
| **Dify** (from training, unverified) | Workflow + AI block hybrid. Tools are "plugins" with schema + manifest. | YAML manifest per plugin. | Plugins listed in the agent's context at session start. | Closest analog to SciEasy's "MCP tools as blocks" mental model. No equivalent of skill split — single global system prompt. |
| **Goose** (Block.xyz, from training, unverified) | Skills called "extensions"; each extension has tool definitions + system-prompt fragments. | TOML extension manifest. | Extensions selected by user at session config time (not per-turn). | Stronger isolation than Anthropic Skills (each extension is a separate process). Less dynamic. |
| **Continue.dev** (from training, unverified) | `.continuerc` config + per-context-provider system messages. No skill split. | YAML config. | Static at session start. | Optimized for IDE inline-edit context; not directly comparable. |
| **Cursor** (from training, unverified) | `.cursorrules` (file-level system prompt) + per-repository instructions. No skill split. | Plain markdown. | Static at session start. | Closest analog to SciEasy's `<project>/CLAUDE.md` provisioning (§3.5). Single-file simplicity is the strength; no dynamic disclosure is the limit. |

### 4.2 Five-to-seven adoption recommendations for SciEasy

1. **Adopt Anthropic Skills SDK frontmatter convention verbatim** (`name: <slug>` + `description: <trigger spec>`). This is ADR-040 §3.4 already; the recommendation is to keep the description **trigger-focused** — describe the user-turn shape that should invoke the skill, NOT the skill content. Example template provided in §5 of this document for each of the 5 task skills.
2. **Keep the base `SKILL.md` thin** (~50 LOC) per ADR §3.4. Verified pattern: thin index + identity + when-to-use-each-skill. Avoid duplicating content across base + task skills — base is the discoverable entry, task skills are the canonical teaching surface.
3. **Adopt the AGENTS.md convention literally** for `<project>/AGENTS.md` (§3.5). Codex reads it by name; the content is identical to `<project>/CLAUDE.md`. Two files, one template.
4. **Mirror LangChain's tool-docstring discipline**: ADR-040 §3.2's tool-description rewrite is already aligned. The recommendation is to keep skill content **complementary** to tool docstrings, not duplicative. A skill teaches the **sequence**; a tool docstring teaches the **shape**. Cross-reference rather than copy.
5. **Adopt Cursor's project-file simplicity for `<project>/CLAUDE.md`** — ~50 lines, identity + rules + index. Resist the temptation to put tool-teaching content there; that belongs in the skills.
6. **NOT adopted: Goose's separate-process extension isolation.** MCP already provides the isolation (process boundary between MCP server and agent). Adding skill-level isolation would be over-engineering.
7. **NOT adopted: n8n / Dify's single-blob prompt.** The whole motivation for ADR-040 §3.4 is to escape this. Phase 2c agents should be specifically warned not to "merge" task skill content "for convenience".

---

## 5. Recommended SKILL content per task skill

For each of the 5 task skills, this section provides:

- Frontmatter (drop-in `description` text)
- 3-5 sentence body opening
- Required sections with 1-line descriptions
- Mandatory rules
- Worked example outline
- Recommended tool-call sequence
- Anti-patterns to call out

### 5.1 `scieasy-build-workflow`

**Frontmatter `description`:**
> Use when the user wants to design a new workflow, choose block types, wire edges between blocks, or convert a verbal pipeline description into a valid workflow YAML. NOT for debugging existing runs (use `scieasy-debug-run`) or for writing custom blocks (use `scieasy-write-block`).

**Body opening (drop-in):**
> You are designing a SciEasy workflow — a DAG of typed blocks expressed as a YAML file under `workflows/`. The runtime is the source of truth; the GUI canvas is an editor and viewer. Workflows are validated structurally and type-wise before they run, so a well-formed YAML is the contract you have to satisfy on the first try if you want a smooth user experience. This skill teaches the YAML schema verbatim, the canonical tool-call sequence, and the pitfalls that account for most validation failures.

**Required sections:**
1. **YAML schema teaching** — drop in §1.1 verbatim.
2. **Common pitfalls** — drop in §1.2 verbatim (10 items).
3. **Three worked examples** — drop in §1.3 verbatim (linear / fan-out / AI block).
4. **Canonical tool-call sequence** — drop in §1.4 verbatim.
5. **When validation fails / when run fails** — drop in §1.4's last two paragraphs.

**Mandatory rules:**
- Always call `list_blocks` + `get_block_schema` for each block before writing.
- Always call `validate_workflow` after `write_workflow`. NEVER call `run_workflow` on an unvalidated YAML.
- Edge port format is `"node_id:port_name"` (single colon, two strings only — NOT the canvas 4-field shape).
- Always poll `get_run_status` until terminal (`succeeded` / `failed` / `cancelled`). Do not declare "done" before terminal.

**Worked example outline:** Three examples from §1.3.

**Recommended tool-call sequence:**
```
list_blocks → get_block_schema (×N) → list_types (if unfamiliar) →
write_workflow → validate_workflow → run_workflow → get_run_status (poll) →
get_block_output → inspect_data / preview_data
```

**Anti-patterns to call out:**
- Using the 4-field edge shape (canvas API confusion).
- Skipping `validate_workflow` ("looks fine to me").
- Polling `get_run_status` once and declaring done on `running`.
- Hallucinating port names instead of calling `get_block_schema`.

### 5.2 `scieasy-write-block`

**Frontmatter `description`:**
> Use when the user wants to author a new custom block — a Python class subclassing `Block` (or `ProcessBlock` / `IOBlock` / etc.) with typed input/output ports and a `config_schema`. ALWAYS check if an existing block satisfies the contract first (call `list_blocks`). NOT for editing an existing block's config (use `update_block_config`) or for writing a workflow (use `scieasy-build-workflow`).

**Body opening (drop-in):**
> Before writing a new block, you MUST call `mcp__scieasy__list_blocks` and REUSE an existing block if its I/O contract matches. Build a new block only when no existing block satisfies the input-port + output-port shape — and document the reason in the new block's docstring. This is the project-wide block-reuse rule (#875). The rest of this skill covers what to do once you have established a new block is genuinely necessary: the Block ABC contract, port-type selection, config-schema design, the scaffold→edit→reload cycle, and a worked example.

**Required sections:**
1. **Block-reuse rule (#875) — MANDATORY first step** — see body opening + an "anti-pattern: silent new-block" callout.
2. **Block ABC contract** — drop in §2.1 verbatim. Include the warning about `base_category` being inferred, not set.
3. **Port-type selection rule (ADR-040 §3.2a)** — drop in §2.5 verbatim including the soft-validation + hook context.
4. **`config_schema` design** — drop in §2.4 (MRO merge note).
5. **Plugin entry-point pattern (ADR-025)** — drop in §2.3 (briefly).
6. **Worked example: thresholding block from scratch** — drop in §2.6 verbatim.
7. **Tool-call sequence for authoring** — included at end of §2.6.
8. **Common pitfalls** — drop in §2.7 verbatim.

**Mandatory rules:**
- Call `mcp__scieasy__list_blocks` FIRST. Reuse if contract matches.
- Call `mcp__scieasy__list_types` before selecting port types. Pick the most specific applicable type. `DataObject` is reserved for `SubWorkflowBlock` + generic `AppBlock` patterns — `scaffold_block` will warn if you use it.
- Do NOT set `base_category` as a ClassVar — it is inferred from the parent class.
- Always `reload_blocks` after writing; verify with `list_blocks`.
- Always `run_block_tests` before declaring the block done.
- After every `scaffold_block` call, READ every entry in `warnings: list[str]`. Do not proceed if there are unaddressed warnings.

**Worked example outline:** `imaging.threshold_simple` from §2.6 — complete, copy-pastable.

**Recommended tool-call sequence:**
```
list_blocks                            # check existing first
list_types                             # pick port types
scaffold_block (name, category, input_ports, output_ports)
# READ warnings, address any DataObject-typed ports
# Edit blocks/<name>.py to fill in run() / process_item()
reload_blocks
list_blocks                            # confirm registration
run_block_tests block_path=...
```

**Anti-patterns to call out:**
- Writing a new block without checking `list_blocks` first (#875 violation).
- Setting `expected_type` to `DataObject` for any non-generic block (§3.2a soft warning).
- Setting `base_category` as a ClassVar (silently ignored).
- Forgetting to bump `version` on a contract change (registry collision).
- `run()` returning a list/tuple/scalar (must return `dict[str, Any]` keyed by output port name).
- Skipping `reload_blocks` after writing (block does not appear in `list_blocks`).

### 5.3 `scieasy-debug-run`

**Frontmatter `description`:**
> Use when a workflow run has failed, is stuck, or produced unexpected output, and you need to diagnose the cause. Covers run-status inspection, block-log retrieval, lineage navigation, and common error signatures. NOT for designing new workflows (use `scieasy-build-workflow`).

**Body opening (drop-in):**
> A SciEasy run has terminated in `failed` or `cancelled` state, or you suspect a block is producing wrong output. This skill teaches the canonical diagnostic sequence — start at the run-status envelope, drill into per-block logs, follow lineage backwards to find the upstream cause, and inspect intermediate data refs without materialising them into memory. Most run failures fall into ~6 recurring categories; the "Common error signatures" section maps each to the next tool call.

**Required sections:**
1. **The canonical diagnostic sequence** — get_run_status → identify failed block(s) → get_block_logs → get_lineage → inspect_data / preview_data.
2. **`get_run_status` envelope shape** — `{state, block_states, started_at, finished_at, error}`. Read every field.
3. **`get_block_logs` patterns** — stdout vs stderr; how to recognize plugin import errors, OOM, missing inputs.
4. **`get_lineage` for cascading failures** — if block B failed, was its upstream block A's output malformed? `get_lineage(B's input ref)` shows the producer.
5. **Common error signatures** — table mapping error string → root cause → next tool call. Cover at least: `FileNotFoundError` (config path wrong), `MemoryError` (input too large; recommend chunking), `KeyError` in `inputs[...]` (edge wiring wrong), `ValidationError` (config_schema mismatch), `ImportError` (stale `reload_blocks`), `subprocess.TimeoutExpired` (AI block timed out).
6. **lineage.db query patterns (ADR-038)** — note that `get_lineage` is the public surface; do not query the SQLite directly.
7. **When to give up and ask the user** — after 3 diagnostic round-trips with no progress, surface the situation rather than guessing.

**Mandatory rules:**
- Always read the FULL `get_run_status` envelope, not just `state`.
- For any failed block, ALWAYS call `get_block_logs` before guessing the cause.
- Do NOT speculate — cite log lines verbatim when explaining the failure.
- Do NOT call `cancel_run` on a `running` workflow without user confirmation.

**Worked example outline:** A workflow that fails because `imaging.threshold` is fed a `DataFrame` (edge wiring wrong). Sequence: `get_run_status` → see `failed, block: thr, error: type mismatch` → `get_block_logs(run_id, "thr")` → see traceback → conclude wrong upstream edge → recommend fix.

**Recommended tool-call sequence:**
```
get_run_status(run_id)                 # full envelope
get_block_logs(run_id, failed_node)    # stdout/stderr
inspect_data(upstream_ref)             # confirm input type
get_lineage(failed_input_ref)          # walk backwards
# Form hypothesis; propose fix to user
```

**Anti-patterns to call out:**
- Cancelling a still-running workflow without checking with the user.
- Speculating about the cause without reading logs.
- Calling `inspect_data` on a 50GB array (use `preview_data` — it returns a thumbnail).
- Re-running the workflow without changing anything ("maybe it'll work this time").

### 5.4 `scieasy-inspect-data`

**Frontmatter `description`:**
> Use when the user wants to look at intermediate or output data — preview a slice of an image, peek at the first rows of a DataFrame, check the shape/dtype of an array, or trace where a data ref came from. NOT for debugging failed runs (use `scieasy-debug-run`).

**Body opening (drop-in):**
> SciEasy data flows as references (`StorageReference`), not in-memory payloads — this is the ADR-031 reference-only contract. You inspect refs without materialising them: `inspect_data` returns shape/dtype/axes/storage backend, `preview_data` returns a thumbnail or first-N-rows preview, `get_lineage` walks the producing-block graph backwards. This skill teaches when to reach for each, how to interpret the results faithfully, and when to materialise (rarely — only via `to_memory()` inside a block's `run()`, never inside an agent turn).

**Required sections:**
1. **Reference-only contract (ADR-031)** — data never flows through the agent's memory. The agent sees refs (opaque IDs); MCP tools operate on refs.
2. **`inspect_data(ref)`** — shape, dtype, axes, storage backend, size in bytes. Use first when you don't know what a ref is.
3. **`preview_data(ref, max_rows?, max_dim?)`** — thumbnail bytes / first-N rows / first chars. Optional max_rows for DataFrames, max_dim for arrays.
4. **`get_lineage(ref)`** — transitive ancestors; useful for "where did this come from?"
5. **`get_block_output(run_id, node_id, port_name)`** — fetch a ref by addressing the producing block.
6. **`list_data`** — enumerate data assets under `data/`.
7. **Citing real data** — when reporting results, cite the inspect_data return values verbatim. Never fabricate.

**Mandatory rules:**
- Never claim to have "seen" data without inspecting it via these tools.
- Use `preview_data` for thumbnails / first-rows; never load full arrays.
- Cite shape / dtype / axes from `inspect_data` results, not from memory.

**Worked example outline:** User asks "what's in the output of the threshold step?" Sequence: `get_block_output(run_id, "thr", "mask")` → `inspect_data(ref)` → report `shape=(512,512), dtype=bool, axes=YX, ~262 KB` → `preview_data(ref, max_dim=128)` → display thumbnail → summarize.

**Recommended tool-call sequence:**
```
list_data                              # if exploring
get_block_output(run_id, node, port)   # if from a run
inspect_data(ref)                      # always first
preview_data(ref, max_rows?, max_dim?) # for the user's eye
get_lineage(ref)                       # if "where did this come from"
```

**Anti-patterns to call out:**
- Fabricating shapes / dtypes ("it should be 512×512" — call `inspect_data` instead).
- Materialising a ref into memory via `Bash` and `cat`.
- Reporting a `preview_data` thumbnail as the actual data.

### 5.5 `scieasy-project-qa`

**Frontmatter `description`:**
> Use when the user asks about the project itself — what blocks are installed, where docs live, what files are in `data/`, project name/metadata, recent workflows. NOT for designing or debugging workflows.

**Body opening (drop-in):**
> Use this skill when the user asks meta-questions about the SciEasy project workspace: which plugins are installed, where the docs are, what's been recently modified, what files live in `data/`. These are surfaces beyond the workflow/run scope — they map to four read-only tools that pull from the file system, the block registry, and the docs index. This skill teaches what each tool returns and how to combine them for common questions.

**Required sections:**
1. **`search_docs(query)`** — free-text search over `docs/`.
2. **`get_doc(path)`** — full document text.
3. **`list_data`** — enumerate data assets under `data/`.
4. **`get_project_info`** — project name, root, installed plugins, recently-modified workflows.
5. **Combining tools** — for "what's this project about?" call `get_project_info` first, then `search_docs("overview")` or `get_doc("README.md")`.

**Mandatory rules:**
- Never invent project details — cite `get_project_info` returns verbatim.
- For doc-lookup questions, prefer `search_docs` over guessing paths.

**Worked example outline:** User: "What blocks does this project have access to?" → `get_project_info` → list `installed_plugins` → `list_blocks` (cross-reference to scieasy-build-workflow if user wants to use them).

**Recommended tool-call sequence:**
```
get_project_info                       # overview
search_docs(query)                     # for doc-text questions
get_doc(path)                          # full doc
list_data                              # for "what data do we have"
```

**Anti-patterns to call out:**
- Inventing plugin names instead of reading `get_project_info`.
- Reading random files via `Read` when `get_doc` would resolve canonically.

---

## 6. Recommended `<project>/CLAUDE.md` + `<project>/AGENTS.md` template

Per ADR-040 §3.5, both files share identical content. Below is the verbatim ~50-line draft body. The template lives at `src/scieasy/agent_provisioning/templates/project_claude_md.md` (Provisioning track owns the file; Phase 2c skill agent's job is to validate this content matches the skill index it ships).

```markdown
# SciEasy project — agent guide

You are an embedded agent inside a SciEasy project workspace. The user
is a researcher building scientific data workflows. The SciEasy GUI is
already running on http://localhost:8000; do NOT start a second backend.

## Identity & non-negotiable rules

- Use `mcp__scieasy__*` tools for anything touching blocks, workflows,
  runs, or data. Do NOT use the `scieasy` CLI via Bash — it bypasses
  live GUI updates and ADR-038 lineage tracking. Hooks will block such
  calls with exit code 2.
- Do NOT directly Edit/Write `workflows/*.yaml`. Use
  `mcp__scieasy__write_workflow` / `update_block_config` so the runtime
  sees changes via the validated path. Hooks block direct edits.
- BEFORE writing a new block, list existing blocks via
  `mcp__scieasy__list_blocks` and reuse one if its I/O contract
  matches. Build new only when nothing fits.
- BEFORE selecting port types for a new block, call
  `mcp__scieasy__list_types`. Pick the most specific applicable type;
  `DataObject` is reserved for generic blocks only.
- Working directory (`cwd`) is the project root. Use relative paths
  (`data/raw/x.tif`, `workflows/foo.yaml`) — MCP tools resolve them
  against the project and validate against escapes.
- All workflow YAML changes are git-tracked (ADR-039). The user sees
  your diffs and can revert.

## Skills available

Invoke the relevant skill before deep work in that area:

- `scieasy-build-workflow` — design a new workflow (YAML schema, validation, run lifecycle).
- `scieasy-write-block` — author a custom block (Block ABC, port types, scaffold→edit→reload).
- `scieasy-debug-run` — diagnose a failed run (run status, logs, lineage).
- `scieasy-inspect-data` — explore data references (inspect/preview/lineage).
- `scieasy-project-qa` — answer project-structure / docs / data questions.

The skill body is the canonical teaching surface. This file is the
identity + non-negotiable-rules index. If a rule here conflicts with a
skill body, ask the user — do not silently pick one.

## What this file is NOT

This file is intentionally short. Detailed contract teaching (YAML
schemas, block-authoring patterns, error-signature catalogs) lives in
the skills — load the relevant one and follow its guidance.
```

**Line count**: 50 lines including blank lines and headings. Per ADR §3.5 budget.

**Content provenance**: every non-negotiable rule is sourced from one of `list_blocks` / `list_types` / `write_workflow` / `update_block_config` enforcement layers, the ADR-038 lineage contract, or the ADR-039 git-auto-init contract. No new rules invented — this file is the index, not the spec.

---

## 7. Identified gaps — MCP shape vs skill compensation

Where the finalized MCP tool surface lacks affordance the skill teaching must fill in:

| # | Gap in MCP shape | Skill compensation |
|---|---|---|
| 1 | `scaffold_block` warnings are advisory; nothing in the tool surface forces the agent to **read** them | `scieasy-write-block` mandatory rule: "After every `scaffold_block` call, READ every entry in `warnings: list[str]`. Do not proceed if there are unaddressed warnings." |
| 2 | `list_types` output may be long; agent could miss the type they want | `scieasy-write-block` worked example demonstrates `list_types` → identify `Image, Mask` → use both. Skill teaches scanning by partial-name match. |
| 3 | `validate_workflow` errors are pydantic JSON; agents tend to fix only the first error | `scieasy-build-workflow` mandatory rule: "Read every error, fix all in one re-write." |
| 4 | `get_run_status` returns `error: str | None` at the run level but per-block details require `get_block_logs` | `scieasy-debug-run` canonical diagnostic sequence: status → identify failed block → logs. Skill teaches not to stop at status. |
| 5 | `get_block_output` requires the agent to know the `port_name`; if they forget the schema, they will guess | `scieasy-debug-run` cross-references `get_block_schema` for port-name lookup. |
| 6 | No tool surfaces "which workflows exist in this project" — `list_data` is data-only | `scieasy-project-qa` teaches: `get_project_info` includes `recently_modified_workflows`; for full enumeration use the Read tool on `workflows/*.yaml` (acceptable since it's read-only). |
| 7 | `update_block_config` accepts a JSON patch; agents may not know the YAML preservation behavior | `scieasy-debug-run` (and `scieasy-build-workflow`) note: `update_block_config` preserves comments + ordering — preferred over re-writing the whole YAML for parameter tweaks. |
| 8 | `finish_ai_block` is only meaningful when the agent is **inside** an AI block PTY; the same tool surface is exposed outside | `scieasy-write-block` and `scieasy-debug-run` note: only call `finish_ai_block` when the run context indicates an AI block (the environment variable `SCIEASY_AI_BLOCK_RUN_DIR` is set per ADR-035 §3.5). Outside an AI block, the call fails fast. |
| 9 | `run_block_tests` runs pytest against a single block file — if the test fails, the agent gets a pytest exit summary, not a structured failure | `scieasy-write-block` teaches: on `run_block_tests` failure, read the pytest output verbatim; do not retry without changes. |
| 10 | No tool exposes the **block category** taxonomy directly; only `list_blocks` (which returns per-block categories) | `scieasy-write-block` includes a brief taxonomy list (`io / process / code / app / ai / subworkflow`) so the agent knows what `category` argument to pass to `scaffold_block`. |

---

## 8. Manager pre-decisions captured

### 8.1 `finish_ai_block` placement

**Background**: per the code-scope manifest §1.2, `finish_ai_block` is registered in the `workflow` category (it's a write-class workflow tool that terminates the current AI Block's run with output refs per ADR-035 §3.5 path (a)). But its operational context is fundamentally **inside an AI Block PTY** — an agent in a normal "user-launched terminal tab" never calls it.

**Three placement options**:

A. Cover briefly in `scieasy-build-workflow` (since it's `workflow`-category).
B. Cover fully in `scieasy-write-block` (most relevant when authoring AI Block subclasses).
C. Cover fully in `scieasy-debug-run` (most relevant to unsticking AI block sessions).

**Recommendation: hybrid (A + C).**

- `scieasy-build-workflow` mentions `finish_ai_block` in passing inside the §1.3 "Example C — AI block in a pipeline" annotation: "the agent uses `mcp__scieasy__finish_ai_block` to terminate cleanly with output refs". One sentence; cross-reference to `scieasy-debug-run` for the full operational surface.
- `scieasy-debug-run` gets the full coverage in a dedicated subsection "Working inside an AI block PTY": when the env var `SCIEASY_AI_BLOCK_RUN_DIR` is set, the agent is inside an AI block; the canonical termination is via `finish_ai_block(run_id, output_refs)`; calling it without that env set fails fast.
- **NOT** in `scieasy-write-block`. The block author writes the AIBlock subclass; the agent calling `finish_ai_block` is the **embedded** agent that AIBlock spawns, not the author of the AIBlock class itself.

This placement matches user reality: workflow-authors see `finish_ai_block` mentioned once when wiring an AI block in; agents that actually need to call it find the full teaching where they're already looking (debug-run, which is where stuck-AI-block sessions tend to land).

### 8.2 The repo-root `skills/scieasy/SKILL.md` worked-example refresh

**Decision**: Phase 2c MUST refresh the "Writing a custom block" worked example to match the live Block ABC API (per §2 of this document). The current example uses an obsolete `BlockSpec` / `PortSpec` shape that no longer exists in the codebase. This is part of `scieasy-write-block` content authoring; not a separate task.

### 8.3 Tool catalog rendering

**Decision**: skill bodies describe tools by **name and behavior**, not by quoting the `_render_tool_catalog` output. This makes skills robust to either S40a's hard-coded fallback rendering OR I40a's `list_tools()`-driven rendering OR any future restructure of how the catalog is composed.

---

## 9. Phase 2c dispatch readiness checklist

Phase 2c (I40b) can dispatch with this deliverable + ADR-040 §3.4 alone. No further upstream research needed.

- [x] All 26 MCP tools enumerated with category, class (read/write), Pydantic result-model name, and `next_step` / `warnings` field presence (§3.1).
- [x] Block ABC contract documented against the live API (§2).
- [x] Workflow YAML schema documented verbatim (§1.1) including the edge-format pitfall (§1.2 #1).
- [x] Three worked workflow examples (linear / fan-out / AI block, §1.3) — drop-in for `scieasy-build-workflow`.
- [x] One worked block example (thresholding, §2.6) — drop-in for `scieasy-write-block`, complete enough for e2e (g) acceptance.
- [x] Port-type narrowness rule (ADR §3.2a) documented + skill compensation specified (§2.5 + §7 row 1).
- [x] Block-reuse rule (#875) — placement in `scieasy-write-block` confirmed; body opening provided (§5.2).
- [x] External harness comparison + 7 adoption recommendations (§4).
- [x] Per-skill recommended body content for all 5 task skills with frontmatter `description`, opening, sections, rules, anti-patterns, worked examples (§5.1-§5.5).
- [x] `<project>/CLAUDE.md` + `<project>/AGENTS.md` draft body (~50 LOC) provided verbatim (§6).
- [x] Identified gap-to-skill-compensation mappings (§7, 10 entries).
- [x] Manager pre-decisions captured: `finish_ai_block` placement (§8.1), worked-example refresh (§8.2), tool-catalog rendering decoupling (§8.3).
- [x] Timing-context flag for I40a-WIP staleness with recommended polish-pass approach (§0).

### Phase 2c dispatch instructions (recap)

The Phase 2c (I40b) agent should:

1. Read this document end-to-end + ADR-040 §3.4 / §3.5.
2. Create 6 files under `src/scieasy/_skills/scieasy/` (or whichever path I40a + S40b have settled on by then — verify before writing):
   - `SKILL.md` (thin base, ~50 LOC, frontmatter `name: scieasy`, body lists 5 task skills + project_context marker block).
   - `scieasy-build-workflow/SKILL.md` (§5.1 content).
   - `scieasy-write-block/SKILL.md` (§5.2 content).
   - `scieasy-debug-run/SKILL.md` (§5.3 content).
   - `scieasy-inspect-data/SKILL.md` (§5.4 content).
   - `scieasy-project-qa/SKILL.md` (§5.5 content).
3. Update `src/scieasy/agent_provisioning/templates/project_claude_md.md` (or wherever the Provisioning track has placed it) to match §6 body verbatim.
4. Drop the legacy `skills/scieasy/SKILL.md` (or compatibility-symlink per ADR §3.4 backward-compat note).
5. Update test fixtures that reference the monolithic skill (per `tests/ai/test_system_prompt.py`).
6. Verify: `python -c "import importlib.resources; print((importlib.resources.files('scieasy') / '_skills' / 'scieasy' / 'SKILL.md').read_text('utf-8')[:100])"` returns the new base content (post-S40b relocation landing).

### Risks / open items for Phase 2c

- **R1**: If I40a does NOT fully land before Phase 2c starts, the tool-catalog rendering in the base SKILL.md may still be the S40a fallback string. Phase 2c content (per §5) describes tools by name, not by quoting the catalog — so this is robust, BUT the base SKILL.md `<!-- tool_catalog:begin/end -->` markers must be preserved exactly so I40a / future polish can splice into them.
- **R2**: ADR-040 §3.5 says "the prompt is still frozen-at-spawn" — Phase 2c skill content must not assume per-turn dynamic rendering. Examples in this doc respect that constraint.
- **R3**: Test changes touching the existing `test_system_prompt.py` (which asserts `tool_catalog` splice idempotence) may collide with concurrent edits if I40a is still in flight. Phase 2c should rebase on the latest `track/adr-040` HEAD right before opening its PR.
- **R4**: The §3.10 out-of-scope items in ADR-040 (BlockRegistry runtime validation, Layer 7 ACL) are NOT in this Phase 2b deliverable — they remain tracked at issues #1015 / #1016 for the future ADR-041.

---

*End of AC40-skill Phase 2b deliverable. Phase 2c agent: dispatch with this document + ADR-040 §3.4 + §3.5 as your full upstream context. No further research required.*
