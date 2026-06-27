"""ADR-051 test fixtures: minimal interactive data-processing blocks.

Importable by the worker subprocess (dotted path
``tests.fixtures.interactive_blocks.<Class>``) so the two-phase runtime can be
exercised end-to-end without any storage-backend plumbing: the blocks take no
DataObject inputs and return plain JSON-safe values, so their prompt and compute
phases serialize cleanly through the real worker.

Alongside :class:`SelectOptionBlock` (the single-block fixture used by
``test_interactive_two_phase.py``) this module hosts the tiny companion blocks
the system-level smoke (``test_interactive_system_smoke.py``) wires into a
multi-block workflow:

* :class:`EmitNumbersBlock` / :class:`DoubleValueBlock` — non-interactive
  ProcessBlocks that pass plain JSON-able values, so an interactive block can be
  driven between/after them through the real scheduler with no storage backend.
* :class:`SelectFromInputBlock` — an interactive block whose panel view is built
  from its real upstream input (not just static config).
* :class:`NonJsonPanelBlock` — an interactive block whose ``prepare_prompt``
  returns a non-JSON ``panel_payload`` (ADR-051 FR-004), so the real prompt-phase
  worker must reject it as an isolated block error.
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
from scistudio.blocks.base.ports import InputPort, OutputPort
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


class EmitNumbersBlock(ProcessBlock):
    """Non-interactive companion block: emits a plain JSON list of numbers.

    Used as the upstream node in the multi-block interactive smoke so the
    interactive block downstream receives a real (JSON-able) input value without
    any storage-backend plumbing. ``config["numbers"]`` drives the output.
    """

    name: ClassVar[str] = "EmitNumbers"
    description: ClassVar[str] = "Test block: emit a fixed list of numbers."
    algorithm: ClassVar[str] = "emit_numbers"
    subcategory: ClassVar[str] = "testing"

    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="numbers", accepted_types=[], is_collection=False),
    ]

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.id = ""

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:  # type: ignore[override]
        return {"numbers": list(config.get("numbers", []) or [])}


class SelectFromInputBlock(InteractiveMixin, ProcessBlock):
    """Interactive block whose prompt view is built from its real input.

    ``prepare_prompt`` reads the upstream ``numbers`` value and offers it as
    selectable choices; the compute phase returns the item the user picked by
    index. No DataObject inputs/outputs are involved, so both phases serialize
    cleanly through the real worker subprocess. Records the prompt-phase pid so
    an e2e test can prove ``prepare_prompt`` ran in a worker subprocess.
    """

    name: ClassVar[str] = "SelectFromInput"
    description: ClassVar[str] = "Test interactive block: pick one of the input numbers."
    algorithm: ClassVar[str] = "select_from_input"
    subcategory: ClassVar[str] = "testing"

    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.INTERACTIVE
    interactive_panel: ClassVar[PanelManifest] = PanelManifest(
        panel_id="test.interactive.select_from_input",
        version="1",
    )
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="numbers", accepted_types=[], is_collection=False),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="selected", accepted_types=[], is_collection=False),
    ]

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.id = ""

    def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> InteractivePrompt:
        choices = list(inputs.get("numbers", []) or [])
        return InteractivePrompt(panel_payload={"choices": choices, "prompt_pid": os.getpid()})

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:  # type: ignore[override]
        response = config.get(INTERACTIVE_RESPONSE_KEY, {}) or {}
        choices = list(inputs.get("numbers", []) or [])
        index = int(response.get("index", 0))
        return {"selected": choices[index]}


class DoubleValueBlock(ProcessBlock):
    """Non-interactive companion block: doubles the scalar on its ``value`` port.

    Used as the downstream node in the multi-block interactive smoke to prove
    the interactive decision flows into a subsequent block's output.
    """

    name: ClassVar[str] = "DoubleValue"
    description: ClassVar[str] = "Test block: double the input value."
    algorithm: ClassVar[str] = "double_value"
    subcategory: ClassVar[str] = "testing"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="value", accepted_types=[], is_collection=False),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="doubled", accepted_types=[], is_collection=False),
    ]

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.id = ""

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:  # type: ignore[override]
        value = inputs.get("value", 0)
        return {"doubled": value * 2}


class NonJsonPanelBlock(InteractiveMixin, ProcessBlock):
    """Interactive block whose ``prepare_prompt`` returns a non-JSON panel payload.

    The panel payload nests a ``set`` (not JSON-serializable). ADR-051 FR-004
    requires the runtime to reject a non-JSON-safe ``panel_payload`` rather than
    pickle or truncate it, so the real prompt-phase worker must fail the block as
    an isolated block error instead of pausing.
    """

    name: ClassVar[str] = "NonJsonPanel"
    description: ClassVar[str] = "Test interactive block: emits a non-JSON panel payload."
    algorithm: ClassVar[str] = "non_json_panel"
    subcategory: ClassVar[str] = "testing"

    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.INTERACTIVE
    interactive_panel: ClassVar[PanelManifest] = PanelManifest(
        panel_id="test.interactive.non_json_panel",
        version="1",
    )
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="selected", accepted_types=[], is_collection=False),
    ]

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.id = ""

    def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> InteractivePrompt:
        # A set is not JSON-serializable; the worker prompt phase must reject it.
        return InteractivePrompt(panel_payload={"bad": {1, 2, 3}})

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:  # type: ignore[override]
        # Never reached: the prompt phase fails before any compute phase.
        return {"selected": None}
