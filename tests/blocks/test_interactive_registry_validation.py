"""ADR-051 FR-002: scan-time validation binding the capability to INTERACTIVE mode.

The registry rejects, at scan time, a block that declares one half of the
capability without the other, an INTERACTIVE block missing ``prepare_prompt``,
or one missing a valid panel manifest; an INTERACTIVE block with the mixin,
``prepare_prompt``, and a valid manifest passes. SC-002: 100% of the malformed
matrix is rejected at scan time.
"""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.interactive import InteractiveMixin, InteractivePrompt, PanelManifest
from scistudio.blocks.base.state import ExecutionMode
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.blocks.registry import BlockRegistry
from scistudio.blocks.registry._capability import _validate_interactive_capability


def _validate(cls: type) -> None:
    # Exercise both the module-level helper and the registry static delegator.
    _validate_interactive_capability(cls)
    BlockRegistry._validate_interactive_capability(cls)


class _GoodInteractive(InteractiveMixin, ProcessBlock):
    name: ClassVar[str] = "GoodInteractive"
    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.INTERACTIVE
    interactive_panel: ClassVar[PanelManifest] = PanelManifest(panel_id="test.good")

    def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> InteractivePrompt:
        return InteractivePrompt(panel_payload={})


class _InteractiveNoMixin(ProcessBlock):
    name: ClassVar[str] = "InteractiveNoMixin"
    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.INTERACTIVE


class _MixinNotInteractive(InteractiveMixin, ProcessBlock):
    name: ClassVar[str] = "MixinNotInteractive"
    interactive_panel: ClassVar[PanelManifest] = PanelManifest(panel_id="test.x")

    def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> InteractivePrompt:
        return InteractivePrompt(panel_payload={})


class _InteractiveNoPanel(InteractiveMixin, ProcessBlock):
    name: ClassVar[str] = "InteractiveNoPanel"
    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.INTERACTIVE

    def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> InteractivePrompt:
        return InteractivePrompt(panel_payload={})


class _InteractiveEmptyPanelId(InteractiveMixin, ProcessBlock):
    name: ClassVar[str] = "InteractiveEmptyPanelId"
    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.INTERACTIVE
    interactive_panel: ClassVar[PanelManifest] = PanelManifest(panel_id="")

    def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> InteractivePrompt:
        return InteractivePrompt(panel_payload={})


class _InteractiveNoPrepare(InteractiveMixin, ProcessBlock):
    name: ClassVar[str] = "InteractiveNoPrepare"
    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.INTERACTIVE
    interactive_panel: ClassVar[PanelManifest] = PanelManifest(panel_id="test.x")
    # Does NOT override prepare_prompt -> the mixin's NotImplementedError default.


class _PlainAuto(ProcessBlock):
    name: ClassVar[str] = "PlainAuto"


# (cls, should_be_rejected, reason)
_MATRIX = [
    (_GoodInteractive, False, "valid interactive block"),
    (_InteractiveNoMixin, True, "INTERACTIVE without InteractiveMixin"),
    (_MixinNotInteractive, True, "InteractiveMixin without INTERACTIVE mode"),
    (_InteractiveNoPanel, True, "INTERACTIVE without a panel manifest"),
    (_InteractiveEmptyPanelId, True, "panel manifest with empty panel_id"),
    (_InteractiveNoPrepare, True, "INTERACTIVE without overriding prepare_prompt"),
    (_PlainAuto, False, "plain AUTO block (no-op)"),
]


@pytest.mark.parametrize("cls,rejected,reason", _MATRIX, ids=[m[2] for m in _MATRIX])
def test_scan_time_validation_matrix(cls: type, rejected: bool, reason: str) -> None:
    if rejected:
        with pytest.raises(ValueError):
            _validate(cls)
    else:
        _validate(cls)  # must not raise


def test_builtin_interactive_blocks_pass_real_scan() -> None:
    """The migrated DataRouter / PairEditor survive a real registry scan (FR-014)."""
    registry = BlockRegistry()
    registry.scan()
    assert registry.get_spec("Data Router") is not None
    assert registry.get_spec("Pair Editor") is not None
