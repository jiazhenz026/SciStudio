"""Smoke-test ``NoopBlock`` — relocated from the deleted production module.

Per Phase 11 master plan §2.5 sub-1a and ``docs/specs/phase11-implementation-standards.md``
T-TRK-003, this block was previously shipped as
``src/scistudio/blocks/process/builtins/transform.py::TransformBlock``. It is
not a placeholder — it is the smoke-test fixture used by the API/frontend
and execution-engine tests, just miscategorised. The body is preserved
verbatim (identity pass-through with optional sleep) so the existing
smoke tests continue to rely on identity-in == identity-out semantics.

Class name and ``type_name`` are updated:

* ``TransformBlock`` → ``NoopBlock``
* ``type_name = "process_block"`` → ``type_name = "noop"``

The block is no longer auto-registered as a core builtin. Tests that
need it under the legacy ``"process_block"`` registry alias rely on the
test-only registration hook in :mod:`tests.conftest`.
"""

from __future__ import annotations

import time
from typing import Any, ClassVar

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.core.types.base import DataObject


class NoopBlock(ProcessBlock):
    """A minimal pass-through Process block with optional delay.

    Used by the test suite as a generic, side-effect-free Process block.
    Identity-in == identity-out is a load-bearing invariant for the smoke
    tests; do **not** add transformation logic here.
    """

    type_name: ClassVar[str] = "noop"
    name: ClassVar[str] = "Process Block"
    description: ClassVar[str] = "A simple transform block for execution and frontend smoke tests."
    algorithm: ClassVar[str] = "transform"

    input_ports: ClassVar[list[InputPort]] = [
        InputPort(name="input", accepted_types=[DataObject], description="Primary input"),
    ]
    output_ports: ClassVar[list[OutputPort]] = [
        OutputPort(name="output", accepted_types=[DataObject], description="Primary output"),
    ]
    config_schema: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "sleep_seconds": {"type": "number", "default": 0, "title": "Sleep Seconds", "ui_priority": 1},
            "label": {"type": "string", "default": "", "title": "Label", "ui_priority": 2},
        },
    }

    def process_item(self, item: Any, config: BlockConfig, state: Any = None) -> Any:
        """Return the item unchanged after an optional sleep.

        ADR-027 D7: accepts ``state`` (unused by this passthrough block)
        for signature parity with the new ProcessBlock lifecycle contract.
        """
        del state  # unused — this passthrough block has no setup state
        sleep_seconds = float(config.get("sleep_seconds", 0) or 0)
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
        return item
