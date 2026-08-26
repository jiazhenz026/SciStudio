"""@@BLOCK_LABEL@@ — an interactive block: it pauses the run and asks the user.

Interaction is a capability, not a base class: this is an ordinary block that
mixes in ``InteractiveMixin`` and declares ``execution_mode = INTERACTIVE``. The
run reaches it, ``prepare_prompt`` reduces the real inputs to a small JSON view,
the window beside this file (``@@PANEL_DIRNAME@@/@@PANEL_FILENAME@@``) shows that
view and takes the user's decision, and then ``run`` computes the outputs from
it.

Everything the registry and the panel host check is already filled in and
correct: both halves of the interactive declaration, a panel manifest whose
``module_url`` matches the route the backend actually serves, and a panel with
working confirm and cancel controls. Three things are yours, each marked TODO:

  1. ``prepare_prompt`` — reduce the inputs to the plain-JSON view the panel
     renders. Never send the raw data.
  2. the panel's content area — draw that view and collect the decision.
  3. ``run`` — read the decision and produce the outputs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from scistudio.blocks.base import (
    Block,
    BlockConfig,
    ExecutionMode,
    InputPort,
    InteractiveMixin,
    InteractivePrompt,
    OutputPort,
    PanelManifest,
)
@@TYPE_IMPORT_LINE@@


class @@CLASS_NAME@@(InteractiveMixin, Block):
    """@@BLOCK_LABEL@@: pause the run, show the data, and act on the answer."""

    name: ClassVar[str] = "@@BLOCK_LABEL@@"
    type_name: ClassVar[str] = "@@TYPE_NAME@@"
    # TODO(scaffold): one line, in the user's language — this is the palette text.
    description: ClassVar[str] = "Pause and let the user decide from the data."
    version: ClassVar[str] = "0.1.0"

    # Both halves, always. The registry rejects the block when only one of the
    # mixin and the mode is present (ADR-051 FR-002).
    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.INTERACTIVE

    # The window this block opens.
    #
    # ``asset_root`` is the on-disk directory beside this file that holds the
    # panel; it is a backend-only path and never reaches the browser.
    # ``module_url`` is always ``/api/blocks/panels/<panel_id>/<file>`` — that is
    # the route the backend serves panel assets on, and a URL of any other shape
    # fails to load with ``import_failed``.
    interactive_panel: ClassVar[PanelManifest] = PanelManifest(
        panel_id="@@PANEL_ID@@",
        module_url="@@MODULE_URL@@",
        version="1",
        asset_root=str(Path(__file__).resolve().parent / "@@PANEL_DIRNAME@@"),
    )

    input_ports: ClassVar[list[InputPort]] = [
@@INPUT_PORTS@@
    ]
    output_ports: ClassVar[list[OutputPort]] = [
@@OUTPUT_PORTS@@
    ]

    def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> InteractivePrompt:
        """Reduce the real inputs to the window-sized JSON view the panel renders.

        Runs first, in its own worker, with the block's full input collections.
        One prompt covers the whole batch: the run pauses once, not once per item.

        Args:
            inputs: The block's input collections, keyed by input-port name.
            config: The resolved block configuration.

        Returns:
            An :class:`InteractivePrompt` whose ``panel_payload`` is plain JSON.
            The runtime rejects a payload that is not JSON-safe.
        """
        items = self.unpack(inputs["@@PRIMARY_INPUT@@"])
        # TODO(scaffold): reduce the real data to something a person can look at
        # — a downsampled trace, a summary table, a list of choices — and send
        # that instead of this placeholder count. Never send the raw arrays.
        return InteractivePrompt(panel_payload={"item_count": len(items)})

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Compute the outputs from the decision the user made in the panel.

        Args:
            inputs: The block's input collections, keyed by input-port name.
            config: Carries ``interactive_response`` — the JSON the panel sent
                through ``host.confirm(...)`` — injected by the engine after the
                user confirms.

        Returns:
            One :class:`Collection` per output port name.
        """
        response = config.get("interactive_response", {}) or {}
        # TODO(scaffold): compute the real outputs from ``response``. This
        # passes the input through so the block runs end to end as scaffolded.
        _ = response
        return {"@@PRIMARY_OUTPUT@@": inputs["@@PRIMARY_INPUT@@"]}
