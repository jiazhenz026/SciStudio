"""Regression test for #883.

Worker subprocess instantiated blocks via ``block_cls()`` (no config)
which left ``self.config`` empty. Variadic-port blocks (ADR-029 D1)
read ``self.config["input_ports"]`` / ``self.config["output_ports"]``
from ``get_effective_*_ports()`` to compute per-instance ports — so
without the config, the block silently fell back to the static
class-level port list and any downstream watcher / validator looked
at the wrong file.

Worker now passes ``config=config``. This test pins that contract by
exercising it on a minimal variadic-output block.
"""

from __future__ import annotations

from typing import ClassVar

from scieasy.blocks.base.block import Block
from scieasy.blocks.base.ports import OutputPort
from scieasy.core.types.base import DataObject


class _VariadicOut(Block):
    """Tiny variadic-output block used only by the regression tests."""

    name: ClassVar[str] = "variadic_out_test"
    variadic_outputs: ClassVar[bool] = True
    output_ports: ClassVar[tuple[OutputPort, ...]] = (OutputPort(name="result", accepted_types=[DataObject]),)

    def run(self, **inputs: object) -> dict[str, object]:  # pragma: no cover
        return {}


def test_variadic_block_with_user_config_returns_user_ports() -> None:
    """The fix path: ``block_cls(config=config)`` exposes user ports."""
    config = {
        "output_ports": [
            {"name": "metadata", "types": ["DataFrame"]},
        ]
    }
    block = _VariadicOut(config=config)

    effective = block.get_effective_output_ports()
    names = [p.name for p in effective]

    assert names == ["metadata"], (
        f"Expected user-configured port 'metadata', got {names}. "
        "Worker must pass config to the block constructor (#883)."
    )


def test_variadic_block_without_config_falls_back_to_class_default() -> None:
    """The bug path (kept as a regression guard).

    Instantiating without config — what worker.py did before #883 — yields
    only the static class-level port. This is the exact wrong behavior
    the fix removes from the worker code path; the test pins it so a
    future regression in ``get_effective_output_ports`` is caught.
    """
    block = _VariadicOut()

    effective = block.get_effective_output_ports()
    names = [p.name for p in effective]

    assert names == ["result"], (
        f"Without config, variadic block must fall back to the class-level static port, got {names}."
    )
