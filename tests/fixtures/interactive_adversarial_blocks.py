"""ADR-051 adversarial fixtures: interactive blocks built to attack the contract.

These blocks are deliberately hostile / boundary-seeking. They are importable by
the worker subprocess (dotted path
``tests.fixtures.interactive_adversarial_blocks.<Class>``) so the real two-phase
runtime can be driven against them end-to-end with no storage backend: inputs and
outputs are plain JSON-able values.

Each block targets a specific contract edge from ADR-051 §2 "Edge Cases" and
FR-004 / FR-010 / FR-012:

* :class:`EchoPanelBlock` — echoes a configurable ``panel_payload`` so the real
  prompt worker can be fed unicode/control/nested/large/empty/engine-colliding
  payloads. Tolerates an optional many-item input so FR-005 (one pause for the
  whole collection) can be observed.
* :class:`ListPanelBlock` / :class:`NonePromptBlock` — ``prepare_prompt`` returns
  a non-dict / ``None`` so the worker must reject it (FR-004).
* :class:`NanPanelBlock` — ``prepare_prompt`` injects ``NaN`` / ``Infinity`` into
  the payload, which the worker must reject with ``allow_nan=False`` (FR-004).
* :class:`CrashingPromptBlock` / :class:`CrashingComputeBlock` — raise inside the
  worker so the failure is isolated as a block error (ADR-051 §2 / §3).
* :class:`ScratchPromptBlock` — persists a real intermediate scratch file and
  carries it across the pause by reference, so intermediate threading (FR-010)
  and scratch release (FR-012) can be observed on disk.
* :class:`PidRecordingBlock` — records the pid of both phases so a test can prove
  each phase ran in its own worker subprocess (SC-001).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, ClassVar

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.interactive import (
    INTERACTIVE_RESPONSE_KEY,
    InteractiveMixin,
    InteractivePrompt,
    PanelManifest,
    load_intermediate,
)
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.base.state import ExecutionMode
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.storage.ref import StorageReference


class EchoPanelBlock(InteractiveMixin, ProcessBlock):
    """Interactive block that echoes a configurable JSON ``panel_payload``.

    ``prepare_prompt`` returns ``config["panel"]`` (a JSON-safe dict the test
    chooses) augmented with the count of items it saw on its optional ``items``
    input, so a test can prove the interaction spans the whole collection with a
    single pause (FR-005). The compute phase returns the user's ``choice``.
    """

    name: ClassVar[str] = "EchoPanel"
    description: ClassVar[str] = "Adversarial interactive block: echo a configurable panel payload."
    algorithm: ClassVar[str] = "echo_panel"
    subcategory: ClassVar[str] = "testing"

    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.INTERACTIVE
    interactive_panel: ClassVar[PanelManifest] = PanelManifest(
        panel_id="test.interactive.echo_panel",
        version="1",
    )
    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="items", accepted_types=[], is_collection=False, required=False),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="selected", accepted_types=[], is_collection=False),
    ]

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.id = ""

    def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> InteractivePrompt:
        items = inputs.get("items")
        n_items = len(items) if isinstance(items, (list, tuple)) else 0
        panel = dict(config.get("panel", {}) or {})
        panel["n_items"] = n_items
        panel["prompt_pid"] = os.getpid()
        return InteractivePrompt(panel_payload=panel)

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:  # type: ignore[override]
        response = config.get(INTERACTIVE_RESPONSE_KEY, {}) or {}
        return {"selected": response.get("choice")}


class ListPanelBlock(InteractiveMixin, ProcessBlock):
    """``prepare_prompt`` returns a list-typed ``panel_payload`` (not a dict).

    FR-004 requires the panel payload to be a JSON object; the worker must reject
    a non-dict payload rather than pass it through.
    """

    name: ClassVar[str] = "ListPanel"
    description: ClassVar[str] = "Adversarial interactive block: non-dict panel payload."
    algorithm: ClassVar[str] = "list_panel"
    subcategory: ClassVar[str] = "testing"

    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.INTERACTIVE
    interactive_panel: ClassVar[PanelManifest] = PanelManifest(panel_id="test.interactive.list_panel", version="1")
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="selected", accepted_types=[], is_collection=False),
    ]

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.id = ""

    def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> InteractivePrompt:
        # panel_payload is annotated dict[str, Any] but nothing enforces it at
        # construction; the worker is the JSON-safety boundary.
        return InteractivePrompt(panel_payload=["not", "a", "dict"])  # type: ignore[arg-type]

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:  # type: ignore[override]
        return {"selected": None}


class NonePromptBlock(InteractiveMixin, ProcessBlock):
    """``prepare_prompt`` returns ``None`` — coerce_prompt must reject it (FR-004)."""

    name: ClassVar[str] = "NonePrompt"
    description: ClassVar[str] = "Adversarial interactive block: prepare_prompt returns None."
    algorithm: ClassVar[str] = "none_prompt"
    subcategory: ClassVar[str] = "testing"

    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.INTERACTIVE
    interactive_panel: ClassVar[PanelManifest] = PanelManifest(panel_id="test.interactive.none_prompt", version="1")
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="selected", accepted_types=[], is_collection=False),
    ]

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.id = ""

    def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> InteractivePrompt:
        return None  # type: ignore[return-value]

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:  # type: ignore[override]
        return {"selected": None}


class NanPanelBlock(InteractiveMixin, ProcessBlock):
    """``prepare_prompt`` injects a non-finite float into the payload (FR-004).

    ``config["mode"]`` selects ``nan`` / ``inf`` / ``neginf``. These cannot
    travel through the JSON config, so they are generated inside the worker.
    """

    name: ClassVar[str] = "NanPanel"
    description: ClassVar[str] = "Adversarial interactive block: NaN/Infinity in panel payload."
    algorithm: ClassVar[str] = "nan_panel"
    subcategory: ClassVar[str] = "testing"

    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.INTERACTIVE
    interactive_panel: ClassVar[PanelManifest] = PanelManifest(panel_id="test.interactive.nan_panel", version="1")
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="selected", accepted_types=[], is_collection=False),
    ]

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.id = ""

    def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> InteractivePrompt:
        mode = config.get("mode", "nan")
        value = {"nan": float("nan"), "inf": float("inf"), "neginf": float("-inf")}.get(mode, float("nan"))
        return InteractivePrompt(panel_payload={"value": value})

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:  # type: ignore[override]
        return {"selected": None}


class CrashingPromptBlock(InteractiveMixin, ProcessBlock):
    """``prepare_prompt`` raises in the worker; the failure must stay isolated."""

    name: ClassVar[str] = "CrashingPrompt"
    description: ClassVar[str] = "Adversarial interactive block: prepare_prompt raises."
    algorithm: ClassVar[str] = "crashing_prompt"
    subcategory: ClassVar[str] = "testing"

    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.INTERACTIVE
    interactive_panel: ClassVar[PanelManifest] = PanelManifest(panel_id="test.interactive.crashing_prompt", version="1")
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="selected", accepted_types=[], is_collection=False),
    ]

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.id = ""

    def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> InteractivePrompt:
        raise RuntimeError("adversarial prepare_prompt crash")

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:  # type: ignore[override]
        return {"selected": None}


class CrashingComputeBlock(InteractiveMixin, ProcessBlock):
    """``prepare_prompt`` succeeds; ``run`` raises in the compute worker."""

    name: ClassVar[str] = "CrashingCompute"
    description: ClassVar[str] = "Adversarial interactive block: run raises in compute phase."
    algorithm: ClassVar[str] = "crashing_compute"
    subcategory: ClassVar[str] = "testing"

    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.INTERACTIVE
    interactive_panel: ClassVar[PanelManifest] = PanelManifest(
        panel_id="test.interactive.crashing_compute", version="1"
    )
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="selected", accepted_types=[], is_collection=False),
    ]

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.id = ""

    def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> InteractivePrompt:
        return InteractivePrompt(panel_payload={"ready": True})

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:  # type: ignore[override]
        raise RuntimeError("adversarial compute crash")


class ScratchPromptBlock(InteractiveMixin, ProcessBlock):
    """Persists a real intermediate scratch file and carries it across the pause.

    ``prepare_prompt`` writes ``config["scratch_path"]`` and returns a
    :class:`StorageReference` to it (intermediate channel, FR-010). The compute
    phase loads that reference and echoes its content, proving the reference was
    threaded engine-side. The engine releases the scratch after the run or on
    cancellation (FR-012); the test inspects the path on disk.
    """

    name: ClassVar[str] = "ScratchPrompt"
    description: ClassVar[str] = "Adversarial interactive block: persists intermediate scratch by reference."
    algorithm: ClassVar[str] = "scratch_prompt"
    subcategory: ClassVar[str] = "testing"

    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.INTERACTIVE
    interactive_panel: ClassVar[PanelManifest] = PanelManifest(panel_id="test.interactive.scratch_prompt", version="1")
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="selected", accepted_types=[], is_collection=False),
        OutputPort(name="scratch_content", accepted_types=[], is_collection=False),
    ]

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.id = ""

    def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> InteractivePrompt:
        scratch_path = str(config.get("scratch_path", ""))
        Path(scratch_path).write_text("SCRATCH-PAYLOAD", encoding="utf-8")
        ref = StorageReference(backend="file", path=scratch_path, format=None, metadata={"role": "intermediate"})
        return InteractivePrompt(panel_payload={"ok": True}, intermediate=(ref,))

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:  # type: ignore[override]
        refs = load_intermediate(config)
        content = ""
        if refs:
            ref_path = Path(refs[0].path)
            if ref_path.is_file():
                content = ref_path.read_text(encoding="utf-8")
        response = config.get(INTERACTIVE_RESPONSE_KEY, {}) or {}
        return {"selected": response.get("choice"), "scratch_content": content}


class PidRecordingBlock(InteractiveMixin, ProcessBlock):
    """Records the worker pid of each phase so a test can prove subprocess isolation.

    ``prepare_prompt`` stamps its pid into the panel payload; ``run`` returns its
    own pid. SC-001: neither pid should equal the engine pid, and the two should
    differ (a fresh subprocess per phase).
    """

    name: ClassVar[str] = "PidRecording"
    description: ClassVar[str] = "Adversarial interactive block: record prompt + compute pids."
    algorithm: ClassVar[str] = "pid_recording"
    subcategory: ClassVar[str] = "testing"

    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.INTERACTIVE
    interactive_panel: ClassVar[PanelManifest] = PanelManifest(panel_id="test.interactive.pid_recording", version="1")
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="selected", accepted_types=[], is_collection=False),
        OutputPort(name="compute_pid", accepted_types=[], is_collection=False),
    ]

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.id = ""

    def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> InteractivePrompt:
        return InteractivePrompt(panel_payload={"prompt_pid": os.getpid()})

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:  # type: ignore[override]
        response = config.get(INTERACTIVE_RESPONSE_KEY, {}) or {}
        return {"selected": response.get("choice"), "compute_pid": os.getpid()}
