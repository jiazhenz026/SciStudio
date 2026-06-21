---
name: scistudio-write-block
description: |
  Use when the user wants to author a NEW BLOCK FILE — Python source
  code (a class subclassing Block / ProcessBlock / IOBlock / AppBlock /
  AIBlock with typed ports and a config_schema) that goes in
  ``<project>/blocks/<name>.py``. ALWAYS check if an existing block
  satisfies the contract first (call list_blocks per #875).

  NOT for ADDING AN EXISTING BLOCK TYPE AS A NODE in a workflow YAML —
  that's scistudio-build-workflow ("add an imaging.threshold node to my
  workflow"). NOT for editing an existing block's config
  (update_block_config). NOT for writing the workflow YAML itself
  (scistudio-build-workflow). NOT for changing port types or
  config_schema on an existing block file via update_block_config
  (which only patches the workflow node's config dict, not the block
  source).
---

# scistudio-write-block

Before authoring a new block, you MUST call `mcp__scistudio__list_blocks`
and REUSE an existing one if its contract matches. Build a new block
ONLY when no existing block satisfies the I/O contract. This is the
project-wide block-reuse rule (#875); it is enforced by a PostToolUse
hook that blocks `blocks/*.py` writes if `list_blocks` was not called
earlier in the same session. The hook is a safety net — your job is
to obey the rule yourself.

The rest of this skill covers what to do once you have established a
new block is genuinely necessary: the Block ABC contract, port-type
selection (ADR-040 §3.2a), `config_schema` design, the
scaffold → edit → reload cycle, and a worked example.

## 1. Block-reuse rule (#875)

Run this sequence FIRST, every time the user asks for a new block:

```
mcp__scistudio__list_blocks
# Inspect the returned list. Match by input port types, output port
# types, and operational intent. If any block has the same I/O
# contract and similar intent, use it instead.
```

If you decide to build a new block anyway, document the reason in the
new block's docstring (e.g. "Existing imaging.threshold uses a fixed
Otsu method; this block adds method=manual with explicit threshold
value."). Reviewers will look for that justification.

## 2. The Block ABC contract

The base class lives in `scistudio.blocks.base.block`. Subclasses MUST
override `run()`. The class-level metadata is read by the registry at
scan time:

```python
from typing import Any, ClassVar
from abc import ABC, abstractmethod

class Block(ABC):
    # Class-level metadata (ClassVars):
    name: ClassVar[str] = "Unnamed Block"            # human-readable
    description: ClassVar[str] = ""                  # one-line
    version: ClassVar[str] = "0.1.0"                 # semver
    subcategory: ClassVar[str] = ""                  # palette grouping
    # base_category is INFERRED from the class hierarchy (io / process /
    # code / app / ai / subworkflow) — do NOT set it as a ClassVar.

    input_ports: ClassVar[list[InputPort]] = []
    output_ports: ClassVar[list[OutputPort]] = []
    config_schema: ClassVar[dict[str, Any]] = {"type": "object", "properties": {}}

    @abstractmethod
    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Subclasses MUST override. Return {output_port_name: Collection}."""
```

**Critical**: do NOT set `base_category` as a ClassVar. It is inferred
from which abstract base the class extends (`ProcessBlock`, `IOBlock`,
`CodeBlock`, `AppBlock`, `AIBlock`, `SubWorkflowBlock`). Setting it as
a ClassVar is silently ignored by the registry.

**ProcessBlock variant**: for blocks that operate per-item over a
`Collection`, subclass `scistudio.blocks.process.process_block.ProcessBlock`
and override `process_item(item, config, state)`. The base class
handles iteration and Collection transparency (ADR-020).

`run()` MUST return a `dict[str, Collection]` keyed by output port name.
Returning a list, tuple, or scalar fails downstream type resolution.

## 3. Port-type selection (ADR-040 §3.2a) — MANDATORY

This is the single most important rule the rest of this skill enforces.

**The rule**: pick the **most specific applicable** `DataObject` subclass
for every port. Use the abstract `DataObject` root ONLY when the block
legitimately accepts any type (e.g. `SubWorkflowBlock` inputs, generic
`save_data` / `load_data` blocks).

**Why it matters**: preview rendering, edge-time type checking,
lineage-graph navigation, and AI-suggestion features all dispatch on
port types. A `DataObject`-typed output port means "anything to
anything" — the preview pane can't render it, the canvas can't
validate connections, the AI block can't propose downstream
candidates.

**Workflow**:

1. Call `mcp__scistudio__list_types` to enumerate registered data types.
2. Pick the most specific applicable type. For an image block, prefer
   `Image`, `MultiChannelImage`, or `Mask` over `Array` or
   `DataObject`. For a tabular block, prefer `DataFrame` over
   `DataObject`.
3. If no registered type fits, declare a new `DataObject` subclass in
   your plugin's `scistudio.types` entry point. Do NOT silently widen
   to `DataObject`.

**Two enforcement layers complement this rule**:

- `mcp__scistudio__scaffold_block` returns a `warnings: list[str]`
  field. If you supplied `DataObject` for any port, a warning fires.
  **Read every warning** before proceeding.
- A PostToolUse hook (`enforce_concrete_port_types.py`) AST-parses
  written `blocks/*.py` files and stderr-warns on the same issues —
  this catches the case where you bypass `scaffold_block` and write
  the file directly.

## 4. `config_schema` design (ADR-030 MRO merge)

`config_schema` is JSON-Schema. The registry **MRO-merges** the schema
across the inheritance chain: a subclass's schema extends the parent's
(subclass wins on duplicate keys). Implications:

- Do not duplicate parent fields in your subclass `config_schema`.
- Your subclass schema is NOT the full effective schema; the registry
  computes the effective schema at scan time.
- Bump `version` whenever you make a backward-incompatible change to
  the schema — the registry refuses to load conflicting versions.

## 5. Plugin entry-point pattern (ADR-025)

For shipping a block as a pip-installable plugin:

```toml
# pyproject.toml of the plugin package
[project.entry-points."scistudio.blocks"]
mypkg = "mypkg:get_blocks"

[project.entry-points."scistudio.types"]
mypkg = "mypkg:get_types"
```

For **most user blocks**, drop a `*.py` file into the project's
`blocks/` directory — it is auto-discovered on `reload_blocks`. Use
entry points only when shipping a reusable plugin across multiple
projects.

A package has a third, separate entry point — `scistudio.previewers`
(ADR-048) — for *display* behaviour, distinct from `scistudio.blocks`
(logic) and `scistudio.types` (data types). Authoring a block does not
touch it. If the user wants a custom previewer for a type, or a quick
preview figure from a block output, that is a different task: a previewer
package or a preview-only plot job (see `scistudio-write-plot`). Block
authoring never creates workflow plots and never edits the preview system.
The human-facing guide is `docs/block-development/previewers-and-plots.md`.

## 6. Block category taxonomy

When you call `scaffold_block(category=...)`, pass one of:

| category | Parent class | Typical use |
|---|---|---|
| `io` | `IOBlock` | Read/write to disk or external store |
| `process` | `ProcessBlock` | Per-item transformation over a Collection |
| `code` | `CodeBlock` | Arbitrary Python computation, no Collection iteration |
| `app` | `AppBlock` | Spawn an external GUI / CLI tool, pause for user output |
| `ai` | `AIBlock` | Spawn an embedded agent in a PTY (ADR-035) |
| `subworkflow` | `SubWorkflowBlock` | Embed another workflow as a block |

## 7. Worked example — thresholding block from scratch

Drop-in starting point. Adapt the algorithm and class names to your
specific block.

```python
# blocks/threshold_simple.py — project-local custom block.
"""Simple Otsu / manual threshold block (worked example for skill teaching)."""
from __future__ import annotations

from typing import Any, ClassVar

import numpy as np

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio_blocks_imaging.types import Image, Mask


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
        method = config.get("method", "otsu")
        if method == "otsu":
            from skimage.filters import threshold_otsu
            t = float(threshold_otsu(arr))
        elif method == "manual":
            threshold_value = config.get("threshold_value")
            if threshold_value is None:
                raise ValueError("method='manual' requires config.threshold_value.")
            t = float(threshold_value)
        else:
            raise ValueError(f"Unknown method {method!r}.")
        return Mask(data=(arr > t).astype(bool), axes=item.axes)
```

## 8. Tool-call sequence for authoring

```
mcp__scistudio__list_blocks
# Confirm imaging.threshold_simple is NOT already registered.
# If a match exists, STOP and reuse.

mcp__scistudio__list_types
# Confirm Image, Mask, etc. exist in the registry. Pick the most
# specific applicable types.

mcp__scistudio__scaffold_block(
    name="threshold_simple",
    category="process",
    input_ports={"image": {"type": "Image", "required": true}},
    output_ports={"mask": {"type": "Mask"}}
)
# Read the result envelope. If `warnings: []` is non-empty, address
# every warning. DO NOT proceed with unaddressed warnings.

# Edit blocks/threshold_simple.py to fill in process_item body.

mcp__scistudio__reload_blocks
# Re-scan the registry so the new block is loadable.

mcp__scistudio__list_blocks
# Confirm imaging.threshold_simple now appears.

mcp__scistudio__run_block_tests type_name="imaging.threshold_simple"
# Targets tests/blocks/test_<type_name lowercased>.py. Read the pytest
# output verbatim. If a test fails, do not retry without changes —
# fix the issue first.
```

## 9. Common pitfalls

1. **`DataObject` port types** — see §3. Most common drift.
2. **Setting `base_category` as a ClassVar** — silently ignored by
   the registry; subclass the right parent instead.
3. **Forgetting `version` bump** — registry collision on
   `reload_blocks`.
4. **`run()` returning a non-dict** — `Block.run` MUST return
   `dict[str, Collection]` keyed by output port name.
5. **In-memory data loading without need** — `item.to_memory()`
   materialises the whole array; for streaming use `item.iter_chunks()`.
   For typical agent-authored blocks under ~1 GB, in-memory is fine.
6. **Reusing a block when authoring** — the #875 violation. Always
   `list_blocks` first.
7. **Skipping `reload_blocks` after writing** — the block won't
   appear in `list_blocks` until you reload.
8. **Skipping `run_block_tests`** — the registry may load a block
   that fails at first run; tests catch trivial bugs early.

## Mandatory rules

- Call `mcp__scistudio__list_blocks` FIRST. Reuse if any block's
  contract matches.
- Call `mcp__scistudio__list_types` before selecting port types. Pick
  the most specific applicable type. `DataObject` is reserved for
  `SubWorkflowBlock` and generic `AppBlock` patterns.
- Do NOT set `base_category` as a ClassVar — it is inferred from the
  parent class.
- Always `reload_blocks` after writing; verify with `list_blocks`.
- Always `run_block_tests` (with `type_name=<registered name>`) before
  declaring the block done.
- After every `scaffold_block` call, READ every entry in
  `warnings: list[str]`. Do not proceed with unaddressed warnings.

## Anti-patterns

- Writing a new block without checking `list_blocks` first (#875).
- Using `DataObject` as a port type for any non-generic block
  (ADR-040 §3.2a soft warning, hook stderr-warning).
- Setting `base_category` as a ClassVar (silently ignored).
- Forgetting to bump `version` on a contract change.
- `run()` returning a list/tuple/scalar (must return `dict[str, Collection]`).
- Skipping `reload_blocks` after writing (block does not appear).
