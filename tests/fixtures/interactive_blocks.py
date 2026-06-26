"""ADR-051 test fixture: a minimal interactive data-processing block.

Importable by the worker subprocess (dotted path
``tests.fixtures.interactive_blocks.SelectOptionBlock``) so the two-phase
runtime can be exercised end-to-end without any storage-backend plumbing: the
block takes no DataObject inputs and returns a plain JSON-safe value, so its
prompt and compute phases serialize cleanly through the real worker.
"""

from __future__ import annotations

import os
from typing import Any, ClassVar

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.interactive import (
    INTERACTIVE_RESPONSE_KEY,
    InteractiveMixin,
    InteractivePrompt,
    PanelManifest,
)
from scistudio.blocks.base.ports import OutputPort
from scistudio.blocks.base.state import ExecutionMode
from scistudio.blocks.process.process_block import ProcessBlock


class SelectOptionBlock(InteractiveMixin, ProcessBlock):
    """Interactive block that pauses, shows options, and returns the chosen one.

    prepare_prompt builds a panel payload listing ``config["options"]``; the
    compute phase reads ``interactive_response["choice"]`` and emits it on the
    plain ``selected`` output port. No DataObject inputs/outputs are involved so
    the real worker subprocess can run both phases without a storage backend.
    """

    name: ClassVar[str] = "SelectOption"
    description: ClassVar[str] = "Test interactive block: select one option."
    algorithm: ClassVar[str] = "select_option"
    subcategory: ClassVar[str] = "testing"

    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.INTERACTIVE
    interactive_panel: ClassVar[PanelManifest] = PanelManifest(
        panel_id="test.interactive.select_option",
        version="1",
    )
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="selected", accepted_types=[], is_collection=False),
    ]

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        # ``DAGScheduler._instantiate_block`` assigns ``.id`` after construction.
        self.id = ""

    def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> InteractivePrompt:
        options = config.get("options", [0, 1, 2])
        # ADR-051 SC-001: record the pid running prepare_prompt so an e2e test
        # can prove directly that the prompt phase executed in a worker
        # subprocess (a different pid from the engine/test process).
        return InteractivePrompt(panel_payload={"options": list(options), "prompt_pid": os.getpid()})

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:  # type: ignore[override]
        response = config.get(INTERACTIVE_RESPONSE_KEY, {}) or {}
        return {"selected": response.get("choice")}
