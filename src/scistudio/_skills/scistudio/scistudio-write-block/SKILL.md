---
name: scistudio-write-block
description: |
  Use when the user wants to author a NEW BLOCK FILE — Python source
  code (a class subclassing Block / ProcessBlock / IOBlock / AppBlock /
  CodeBlock with typed ports and a config_schema) that goes in
  ``<project>/blocks/<name>.py``. ALWAYS check if an existing block
  satisfies the contract first (call list_blocks first and reuse a match).

  NOT for ADDING AN EXISTING BLOCK TYPE AS A NODE in a workflow YAML —
  that's scistudio-build-workflow ("add an imaging.threshold node to my
  workflow"). NOT for editing an existing block's config
  (update_block_config). NOT for writing the workflow YAML itself
  (scistudio-build-workflow).
---

# scistudio-write-block

Author a project-local custom block. This skill is the **task flow**; the block
**contract** lives in the provisioned reference docs — read them, do not guess:

- **`.scistudio/agent-reference/block-contract.md`** — base classes, ports,
  `config_schema`, `run` vs `process_item`, Collection helpers.
- **`.scistudio/agent-reference/public-api.md`** — canonical import roots and the
  rules below. Import from roots only.
- **`.scistudio/agent-reference/data-types.md`** — reading/constructing values.
- **`.scistudio/agent-reference/package-discovery.md`** — using package types.
- **`user-guide/api-reference/`** — exact signatures of every public symbol.

## Non-negotiables (full detail in the reference docs)

1. **Reuse first.** Call `mcp__scistudio__list_blocks` BEFORE authoring and
   reuse any block whose I/O contract matches. A PostToolUse hook blocks
   `blocks/*.py` writes if `list_blocks` was not called this session. Build new
   only when nothing fits; justify it in the new block's docstring.
2. **Canonical imports only.** `from scistudio.blocks.base import Block,
   BlockConfig, InputPort, OutputPort`, `from scistudio.blocks.process import
   ProcessBlock`, `from scistudio.core.types import Array, DataFrame, ...`. Never a
   deep module path (`...base.ports`) or an underscore module
   (`_support`) — see `public-api.md`.
3. **Concrete port types.** Pick the most specific applicable
   type; never bare `DataObject` / `[]` for a non-generic block. Call
   `mcp__scistudio__list_types` first. `scaffold_block` warns and a PostToolUse
   hook stderr-warns on `DataObject` ports — read every warning.
4. **`run()` returns `dict[str, Collection]`** keyed by output port name.
5. **Not author surfaces:** do not subclass `AIBlock` / `SubWorkflowBlock` (they
   are runtime base classes; for AI-in-workflow the user adds the built-in **AI
   Agent** block and configures it). Do not set `base_category` (it is inferred).

## Tool-call sequence

```
mcp__scistudio__list_blocks                    # reuse check — STOP if a match exists
mcp__scistudio__list_types                     # pick concrete port types
mcp__scistudio__scaffold_block(name=..., category="process|io|app|code",
    input_ports={...}, output_ports={...})     # READ every warnings[] entry
# edit blocks/<name>.py — fill the body per block-contract.md
mcp__scistudio__reload_blocks                  # re-scan the registry
mcp__scistudio__list_blocks                    # confirm it appears
mcp__scistudio__run_block_tests type_name="<registered name>"   # read pytest output verbatim
```

`category` → parent: `process`→ProcessBlock, `io`→IOBlock, `app`→AppBlock,
`code`→CodeBlock. Every write-class tool returns a `next_step` — read and follow.

## Worked example

A minimal `ProcessBlock` (one item → one item). Adapt names/algorithm; for IO,
App, and Code blocks see `block-contract.md`.

```python
# blocks/scale_image.py — project-local custom block.
"""Scale every image in the batch by a gain factor."""
from __future__ import annotations

from typing import Any, ClassVar

from scistudio.blocks.base import BlockConfig, InputPort, OutputPort
from scistudio.blocks.process import ProcessBlock
from scistudio.core.types import Array


class ScaleImage(ProcessBlock):
    name: ClassVar[str] = "Scale Image"
    description: ClassVar[str] = "Multiply each image by a gain factor."
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="input", accepted_types=[Array], required=True),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="output", accepted_types=[Array]),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {"gain": {"type": "number", "default": 1.0}},
    }

    def process_item(self, item: Array, config: BlockConfig, state: Any = None) -> Array:
        return Array(axes=list(item.axes), data=item.to_memory() * config.get("gain", 1.0))
```

A package type is imported from the package top level
(`from scistudio_blocks_spectroscopy import Spectrum`), never a deep path — see
`package-discovery.md`.

## Make it usable — label everything the user sees

The user drives your block from the GUI, where the only thing they see is the
text you put on these fields. Fill all of them with short, clear, human language
— a non-programmer must be able to tell ports and parameters apart (three ports
all typed `Image` with no names/descriptions are unusable):

| Where users see it | Field(s) to write |
|---|---|
| Palette + node header | block `name` (a real label, not `MyBlock`) and one-line `description` |
| Each input/output port | a distinct `name` **and** a `description` (what flows here, e.g. "raw image" vs "binary mask" vs "overlay") |
| Each parameter panel field | the `config_schema` property's `title` (the label) **and** `description` (what it does / units / when to change it) |
| In the code | short, plain comments explaining the *why*, not the obvious |

```python
input_ports = [
    InputPort(name="image",   accepted_types=[Image], description="Image to segment"),
    InputPort(name="markers", accepted_types=[Image], description="Seed markers for watershed"),
]
config_schema = {"type": "object", "properties": {
    "sigma": {"type": "number", "default": 1.0,
              "title": "Smoothing (sigma)", "description": "Gaussian blur before thresholding; 0 disables."},
}}
```

Keep it terse but specific. Distinct names + a one-line description per port and
per parameter is the bar.

**Expose tunables as config, never hard-code them.** Any value a user might
reasonably want to choose — a processing parameter, threshold, window size,
method choice — goes in `config_schema` (with a `title`/`description` and a sane
`default`) and is read in the body with `config.get(...)`. Do not bury a tunable
constant in the code where the user cannot reach it; if they might want to change
it, surface it.

## Mandatory rules

- `list_blocks` FIRST; reuse on a contract match.
- `list_types` before choosing port types; concrete types only.
- Canonical-root imports only (`public-api.md`); no deep paths / `_support`.
- Do not subclass `AIBlock` / `SubWorkflowBlock`; do not set `base_category`.
- After `scaffold_block`, read every `warnings[]`. After writing, `reload_blocks`
  then `run_block_tests`; read the result `next_step`.

## Anti-patterns

- Authoring without `list_blocks` first.
- Deep-path or `_support` imports; bare `DataObject` ports on a non-generic block.
- Subclassing `AIBlock`/`SubWorkflowBlock`, or setting `base_category`.
- `run()` returning a non-dict; skipping `reload_blocks` / `run_block_tests`.
