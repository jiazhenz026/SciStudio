"""SubWorkflowBlock — runs an entire workflow as a single block."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort

if TYPE_CHECKING:
    from scistudio.core.types.collection import Collection
from scistudio.core.types.base import DataObject

logger = logging.getLogger(__name__)


class SubWorkflowBlock(Block):
    """Block that encapsulates a full workflow as a single composable unit.

    *workflow_ref* points to the nested workflow definition (YAML path or ID).
    *input_mapping* translates parent port names to child workflow input names.
    *output_mapping* translates child workflow output names to parent port names.

    The engine layer injects ``_scheduler_factory`` at startup so that child
    workflows can use the real DAG scheduler without blocks/ importing engine/.
    When no factory is injected, execution falls back to the sequential stub.

    .. note::

        Full async DAG scheduling requires the engine's event loop (Phase 5.2b
        worker.py).  The ``_run_with_scheduler`` method currently delegates to
        ``_sequential_execute`` as a placeholder until the worker integration
        is complete.

    TODO: #890 — wire ``_run_with_scheduler`` into a real async DAG run
    via the engine's scheduler factory so SubWorkflowBlock stops falling
    back to in-process sequential execution.
    """

    workflow_ref: ClassVar[str] = ""
    input_mapping: ClassVar[dict[str, str]] = {}
    output_mapping: ClassVar[dict[str, str]] = {}

    # Engine injects this at startup (avoids import-linter violation:
    # blocks cannot import engine).
    _scheduler_factory: ClassVar[Any] = None

    # Engine injects this at startup for nested subprocess cleanup (ADR-017/019).
    # Called in run()'s finally block so grandchild processes are terminated
    # even when the parent SubWorkflowBlock errors or is cancelled.
    _cleanup_callback: ClassVar[Any] = None

    name: ClassVar[str] = "Sub-Workflow"
    description: ClassVar[str] = "Encapsulate a full workflow as a single block"

    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "workflow_path": {
                "type": "string",
                "title": "Workflow YAML path",
                "ui_widget": "file_browser",
                "ui_priority": 0,
            },
        },
        "required": ["workflow_path"],
    }

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="data", accepted_types=[DataObject], required=False, description="Input to child workflow"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="result", accepted_types=[DataObject], description="Output from child workflow"),
    ]

    def run(self, inputs: dict[str, Collection], config: BlockConfig) -> dict[str, Collection]:
        """Execute the referenced sub-workflow.

        1. Load child workflow definition from *workflow_ref* or config.
        2. Map parent inputs to child inputs via *input_mapping*.
        3. Use real scheduler if ``_scheduler_factory`` is set, else fallback
           to :func:`_sequential_execute`.
        4. Map child outputs to parent outputs via *output_mapping*.

        .. note::

            ADR-017 requires child block execution to use subprocess isolation.
            This is enforced by the engine's LocalRunner, not by the block itself.
        """
        try:
            child_blocks = config.get("child_blocks") or []
            in_map = config.get("input_mapping") or self.input_mapping or {}
            out_map = config.get("output_mapping") or self.output_mapping or {}

            # Map parent inputs to child namespace.
            child_inputs: dict[str, Any] = {}
            for parent_key, child_key in in_map.items():
                if parent_key in inputs:
                    child_inputs[child_key] = inputs[parent_key]

            # Also pass through any unmapped inputs.
            for key, value in inputs.items():
                if key not in in_map:
                    child_inputs[key] = value

            # Use real scheduler if available, else fallback to sequential.
            if self._scheduler_factory is not None:
                child_outputs = self._run_with_scheduler(child_inputs, config)
            else:
                child_outputs = _sequential_execute(child_blocks, child_inputs)

            # Map child outputs to parent outputs.
            results: dict[str, Any] = {}
            for child_key, parent_key in out_map.items():
                if child_key in child_outputs:
                    results[parent_key] = child_outputs[child_key]

            # Also pass through any unmapped outputs.
            for key, value in child_outputs.items():
                if key not in out_map:
                    results[key] = value

            return results
        finally:
            # ADR-017/019: Clean up grandchild subprocesses.
            # Access via __class__ to avoid Python's descriptor protocol turning
            # the stored callable into a bound method (which would inject self
            # as the first argument).
            cb = type(self).__dict__.get("_cleanup_callback")
            if cb is not None:
                try:
                    cb()
                except Exception:
                    logger.warning(
                        "Cleanup callback failed for %s",
                        type(self).__name__,
                        exc_info=True,
                    )

    def _run_with_scheduler(self, child_inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        """Execute child workflow using injected scheduler factory.

        The engine layer sets ``_scheduler_factory`` at startup, avoiding
        the import-linter constraint (blocks cannot import engine).

        For now, delegates to ``_sequential_execute`` as the real async
        scheduler integration requires the engine's event loop (Phase 5.2b
        worker.py).  The worker recognises ``SubWorkflowBlock`` and creates
        a child scheduler.
        """
        child_blocks = config.get("child_blocks") or []
        return _sequential_execute(child_blocks, child_inputs)


def _sequential_execute(
    blocks: list[Block],
    inputs: dict[str, Any],
) -> dict[str, Any]:
    """Execute *blocks* in order, threading outputs as inputs to the next.

    Collections (ADR-020) flow through the shared namespace unchanged —
    child blocks receive them as-is without unwrapping.

    This is a fallback executor.  The real DAG scheduler is injected via
    ``SubWorkflowBlock._scheduler_factory`` by the engine layer.
    """
    namespace = dict(inputs)

    for block in blocks:
        block_inputs: dict[str, Any] = {}
        # ADR-028 Addendum 1 D5: read effective input ports so dynamic
        # child blocks resolve their config-driven port set per instance.
        for port in block.get_effective_input_ports():
            if port.name in namespace:
                block_inputs[port.name] = namespace[port.name]
            elif not port.required and port.default is not None:
                block_inputs[port.name] = port.default

        outputs = block.run(block_inputs, block.config)
        outputs = block.postprocess(outputs)
        namespace.update(outputs)

    return namespace
