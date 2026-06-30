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

## Choose the block shape — climb the accessibility ladder

Your users drive blocks from the GUI; they are bench scientists, not your
analyst. **Never hard-code a decision that depends on looking at the user's
specific data.** The moment you catch yourself inspecting their data and baking
in a constant — which rows are background, where a peak sits, a cutoff that
"looks right" — stop and push that decision out to the user. A pipeline of
`ProcessBlock`s with baked-in constants is the default failure mode; the user
cannot change what you hid in code. Pick the lowest rung that fits:

| Rung | Shape | Reach for it when |
|---|---|---|
| ❌ | hard-coded constant in the body | never, for a value that depends on the data |
| 1 | **config parameter** (`config_schema` + `config.get`) | the user can set it without seeing the data (a default that is usually right, units they know) |
| 2 | **interactive, built-in panel** | the choice is routing items (`core.interactive.data_router`) or fixing pairing (`core.interactive.pair_editor`) — no frontend code |
| 3 | **interactive, custom panel** | the user must look at *their* data to decide — pick a baseline region on a trace, click a peak, set a threshold against a preview |
| 4 | **AppBlock / CodeBlock** | an external GUI/CLI tool or an existing script the user already trusts does the job |

Default to rung 1 — always cheap, always available. Climb to rung 3 when the
decision is inherently visual or data-dependent: that is the line between a
block that runs and one a scientist can actually use. (Example: an LCMS
"subtract background" should not guess which scans are background from the data
— it should open a panel and let the user mark the baseline region.) The
interactive / App / Code authoring details are in `block-contract.md`; a compact
interactive example is below.

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

## Worked example — interactive block (rung 3, custom panel)

When the decision needs the user's eyes on their own data, make the block
interactive instead of guessing. Mix in `InteractiveMixin`, set
`execution_mode = INTERACTIVE`, point `interactive_panel` at a panel file you
write beside the block, build a JSON view in `prepare_prompt`, and read the
user's choice in `run` from `config["interactive_response"]`. Full contract in
`block-contract.md`.

```python
# blocks/pick_baseline.py — interactive: the user marks the baseline region.
"""Subtract a baseline the user selects on the trace, instead of guessing it."""
from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from scistudio.blocks.base import (
    BlockConfig, ExecutionMode, InputPort, InteractiveMixin,
    InteractivePrompt, OutputPort, PanelManifest,
)
from scistudio.blocks.process import ProcessBlock
from scistudio.core.types import Array, Collection


class PickBaseline(InteractiveMixin, ProcessBlock):
    name: ClassVar[str] = "Pick Baseline"
    description: ClassVar[str] = "Mark a baseline region on the trace, then subtract it."
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="trace", accepted_types=[Array], required=True,
                  description="Signal to baseline-correct"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="corrected", accepted_types=[Array],
                   description="Trace with the selected baseline subtracted"),
    ]
    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.INTERACTIVE
    interactive_panel: ClassVar[PanelManifest] = PanelManifest(
        panel_id="myproj.pick_baseline",
        module_url="/api/blocks/panels/myproj.pick_baseline/index.js",
        asset_root=str(Path(__file__).parent / "pick_baseline"),  # dir holding index.js
        version="1",
    )

    def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> InteractivePrompt:
        # Reduce the REAL data to a small JSON view the window draws (downsample if large).
        first = next(iter(inputs["trace"]))  # Collection is iterable; one item per length-1 batch
        return InteractivePrompt(panel_payload={"y": first.to_memory().tolist()})

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Collection]:
        region = config.get("interactive_response", {}).get("region", [0, 0])

        def subtract(item: Array) -> Array:
            data = item.to_memory()
            lo, hi = int(region[0]), int(region[1])
            baseline = data[lo:hi].mean() if hi > lo else 0.0
            return Array(axes=list(item.axes), data=data - baseline)

        return {"corrected": self.map_items(subtract, inputs["trace"])}
```

```javascript
// blocks/pick_baseline/index.js — the window the block opens (plain ES module, no build step).
export default {
  apiVersion: "1",
  mount(container, host) {
    const y = host.panelPayload.y || [];           // what prepare_prompt returned
    // A real panel draws `y` and lets the user drag a span; kept minimal here.
    container.innerHTML =
      `<p>Baseline region for a ${y.length}-point trace:</p>` +
      `<input id="lo" type="number" placeholder="start index"> ` +
      `<input id="hi" type="number" placeholder="end index"> ` +
      `<button id="ok">Confirm</button> <button id="no">Cancel</button>`;
    const val = (id) => Number(container.querySelector(id).value);
    container.querySelector("#ok").onclick = () =>
      host.confirm({ region: [val("#lo"), val("#hi")] });  // -> config["interactive_response"]
    container.querySelector("#no").onclick = () => host.cancel();
    return { unmount() { container.innerHTML = ""; } };
  },
};
```

For a routing or pairing interaction, skip the custom panel and reuse a built-in
one (`PanelManifest(panel_id="core.interactive.data_router")` or
`"core.interactive.pair_editor"`) — no JS to write. For an external tool or an
existing script, use an `AppBlock` or `CodeBlock` instead (see `block-contract.md`).

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
- Never hard-code a data-dependent decision. Climb the shape ladder: config
  parameter, then interactive (built-in or custom panel), then App/Code.
- After `scaffold_block`, read every `warnings[]`. After writing, `reload_blocks`
  then `run_block_tests`; read the result `next_step`.

## Anti-patterns

- Authoring without `list_blocks` first.
- **Hard-coding a value read off the user's data** (background region, peak
  location, a cutoff that "looks right") instead of a config param or an
  interactive panel — the #1 reason agent-written blocks are unusable.
- Reflexively chaining `ProcessBlock`s when an interactive, App, or Code block
  would let the user steer the decision.
- Deep-path or `_support` imports; bare `DataObject` ports on a non-generic block.
- Subclassing `AIBlock`/`SubWorkflowBlock`, or setting `base_category`.
- `run()` returning a non-dict; skipping `reload_blocks` / `run_block_tests`.
- Interactive block missing its pair (`InteractiveMixin` without
  `execution_mode=INTERACTIVE`, or no `prepare_prompt` / `interactive_panel`) —
  the registry rejects it at scan time.
