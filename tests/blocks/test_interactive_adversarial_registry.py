"""ADR-051 adversarial registry validation + manifest/API-surface suite.

NO-IMPLEMENTATION-CONTEXT design driven by the contract:

* FR-002 / SC-002 — a malformed interactive declaration is rejected at registry
  SCAN time (not at runtime). Verified two ways: a REAL Tier-1 drop-in scan
  (the malformed blocks must not register; the good one must), and a precise
  unit call into the scan-time validator for the exact error wording.
* §4.2 / FR-007 — ``execution_mode`` and the serialized ``panel_manifest`` are
  surfaced on block metadata (the registry ``BlockSpec``). Since #2493 the
  manifest names the panel only; the legacy module fields and the package panel
  asset route are gone.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from scistudio.blocks.base.interactive import (
    InteractiveMixin,
    InteractivePrompt,
    PanelManifest,
)
from scistudio.blocks.base.state import ExecutionMode
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.blocks.registry import BlockRegistry
from scistudio.blocks.registry._spec import _spec_from_class
from tests.fixtures.interactive_blocks import EmitNumbersBlock, SelectOptionBlock
from tests.fixtures.interactive_blocks import registered_test_panels as registered_test_panels

# ===========================================================================
# F. Real Tier-1 drop-in scan — malformed interactive blocks rejected at scan.
# ===========================================================================

_GOOD_DROPIN = """
from scistudio.blocks.base.interactive import InteractiveMixin, InteractivePrompt, PanelManifest
from scistudio.blocks.base.state import ExecutionMode
from scistudio.blocks.process.process_block import ProcessBlock


class GoodPanelDropin(InteractiveMixin, ProcessBlock):
    name = "GoodPanelDropin"
    execution_mode = ExecutionMode.INTERACTIVE
    interactive_panel = PanelManifest(panel_id="dropin.good")

    def prepare_prompt(self, inputs, config):
        return InteractivePrompt(panel_payload={"ok": True})

    def run(self, inputs, config):
        return {}
"""

_BAD_MODE_NO_MIXIN = """
from scistudio.blocks.base.state import ExecutionMode
from scistudio.blocks.process.process_block import ProcessBlock


class BadModeNoMixin(ProcessBlock):
    name = "BadModeNoMixin"
    execution_mode = ExecutionMode.INTERACTIVE

    def run(self, inputs, config):
        return {}
"""

_BAD_MIXIN_NO_MODE = """
from scistudio.blocks.base.interactive import InteractiveMixin, InteractivePrompt, PanelManifest
from scistudio.blocks.process.process_block import ProcessBlock


class BadMixinNoMode(InteractiveMixin, ProcessBlock):
    name = "BadMixinNoMode"
    interactive_panel = PanelManifest(panel_id="dropin.badmode")

    def prepare_prompt(self, inputs, config):
        return InteractivePrompt(panel_payload={"ok": True})

    def run(self, inputs, config):
        return {}
"""

_BAD_MISSING_PROMPT = """
from scistudio.blocks.base.interactive import InteractiveMixin, PanelManifest
from scistudio.blocks.base.state import ExecutionMode
from scistudio.blocks.process.process_block import ProcessBlock


class BadMissingPrompt(InteractiveMixin, ProcessBlock):
    name = "BadMissingPrompt"
    execution_mode = ExecutionMode.INTERACTIVE
    interactive_panel = PanelManifest(panel_id="dropin.badprompt")

    def run(self, inputs, config):
        return {}
"""

_BAD_NO_MANIFEST = """
from scistudio.blocks.base.interactive import InteractiveMixin, InteractivePrompt
from scistudio.blocks.base.state import ExecutionMode
from scistudio.blocks.process.process_block import ProcessBlock


class BadNoManifest(InteractiveMixin, ProcessBlock):
    name = "BadNoManifest"
    execution_mode = ExecutionMode.INTERACTIVE

    def prepare_prompt(self, inputs, config):
        return InteractivePrompt(panel_payload={"ok": True})

    def run(self, inputs, config):
        return {}
"""

_BAD_EMPTY_PANEL_ID = """
from scistudio.blocks.base.interactive import InteractiveMixin, InteractivePrompt, PanelManifest
from scistudio.blocks.base.state import ExecutionMode
from scistudio.blocks.process.process_block import ProcessBlock


class BadEmptyPanelId(InteractiveMixin, ProcessBlock):
    name = "BadEmptyPanelId"
    execution_mode = ExecutionMode.INTERACTIVE
    interactive_panel = PanelManifest(panel_id="")

    def prepare_prompt(self, inputs, config):
        return InteractivePrompt(panel_payload={"ok": True})

    def run(self, inputs, config):
        return {}
"""

_MALFORMED: dict[str, str] = {
    "BadModeNoMixin": _BAD_MODE_NO_MIXIN,
    "BadMixinNoMode": _BAD_MIXIN_NO_MODE,
    "BadMissingPrompt": _BAD_MISSING_PROMPT,
    "BadNoManifest": _BAD_NO_MANIFEST,
    "BadEmptyPanelId": _BAD_EMPTY_PANEL_ID,
}


def test_real_scan_rejects_malformed_and_accepts_good(tmp_path: Path) -> None:
    """FR-002 / SC-002: a real Tier-1 scan registers the good block and drops every malformed one."""
    scan_dir = tmp_path / "dropins"
    scan_dir.mkdir()
    (scan_dir / "good_panel.py").write_text(_GOOD_DROPIN, encoding="utf-8")
    for idx, (name, source) in enumerate(_MALFORMED.items()):
        (scan_dir / f"bad_{idx}_{name.lower()}.py").write_text(source, encoding="utf-8")

    registry = BlockRegistry()
    registry.add_scan_dir(scan_dir)
    registry._scan_tier1()

    assert registry.get_spec("GoodPanelDropin") is not None, "valid interactive drop-in was not registered"
    for name in _MALFORMED:
        assert registry.get_spec(name) is None, f"malformed interactive block {name} was registered (FR-002 violated)"


# Precise scan-time validator wording for each malformed shape (FR-002).
# These in-test classes are never instantiated or worker-imported.


class _ModeNoMixin(ProcessBlock):
    execution_mode = ExecutionMode.INTERACTIVE

    def run(self, inputs: dict[str, Any], config: Any) -> dict[str, Any]:  # type: ignore[override]
        return {}


class _MixinNoMode(InteractiveMixin, ProcessBlock):
    interactive_panel = PanelManifest(panel_id="x.mixin_no_mode")

    def prepare_prompt(self, inputs: dict[str, Any], config: Any) -> InteractivePrompt:
        return InteractivePrompt(panel_payload={})

    def run(self, inputs: dict[str, Any], config: Any) -> dict[str, Any]:  # type: ignore[override]
        return {}


class _MissingPrompt(InteractiveMixin, ProcessBlock):
    execution_mode = ExecutionMode.INTERACTIVE
    interactive_panel = PanelManifest(panel_id="x.missing_prompt")

    def run(self, inputs: dict[str, Any], config: Any) -> dict[str, Any]:  # type: ignore[override]
        return {}


class _NoManifest(InteractiveMixin, ProcessBlock):
    execution_mode = ExecutionMode.INTERACTIVE

    def prepare_prompt(self, inputs: dict[str, Any], config: Any) -> InteractivePrompt:
        return InteractivePrompt(panel_payload={})

    def run(self, inputs: dict[str, Any], config: Any) -> dict[str, Any]:  # type: ignore[override]
        return {}


class _EmptyPanelId(InteractiveMixin, ProcessBlock):
    execution_mode = ExecutionMode.INTERACTIVE
    interactive_panel = PanelManifest(panel_id="")

    def prepare_prompt(self, inputs: dict[str, Any], config: Any) -> InteractivePrompt:
        return InteractivePrompt(panel_payload={})

    def run(self, inputs: dict[str, Any], config: Any) -> dict[str, Any]:  # type: ignore[override]
        return {}


@pytest.mark.parametrize(
    ("cls", "fragment"),
    [
        (_ModeNoMixin, "requires inheriting InteractiveMixin"),
        (_MixinNoMode, "requires execution_mode=INTERACTIVE"),
        (_MissingPrompt, "must implement prepare_prompt"),
        (_NoManifest, "must declare a valid interactive_panel"),
        (_EmptyPanelId, "must declare a valid interactive_panel"),
    ],
)
def test_validator_raises_clear_error(cls: type, fragment: str) -> None:
    """FR-002: the scan-time validator raises a clear, specific error for each shape."""
    with pytest.raises(ValueError, match=fragment):
        BlockRegistry._validate_interactive_capability(cls)


def test_good_interactive_block_passes_validator() -> None:
    """FR-002: a correctly-declared interactive block passes the validator untouched."""
    BlockRegistry._validate_interactive_capability(SelectOptionBlock)  # must not raise


def test_non_interactive_block_passes_validator() -> None:
    """FR-002: a plain AUTO block is a no-op for the interactive validator."""
    BlockRegistry._validate_interactive_capability(EmitNumbersBlock)  # must not raise


# ===========================================================================
# I. Manifest / API surface — execution_mode + panel_manifest on metadata.
# ===========================================================================


def test_interactive_block_spec_surfaces_mode_and_manifest() -> None:
    """FR-007 / §4.2: BlockSpec carries execution_mode + serialized panel_manifest."""
    spec = _spec_from_class(SelectOptionBlock)
    assert spec.execution_mode == "interactive"
    assert isinstance(spec.panel_manifest, dict)
    assert spec.panel_manifest["panel_id"] == "test.interactive.select_option"
    # #2493: the manifest names the panel and nothing else about loading it.
    assert set(spec.panel_manifest) <= {"panel_id", "api_version", "response_schema"}


def test_non_interactive_block_spec_has_no_manifest() -> None:
    """A plain block reports execution_mode=auto and no panel manifest."""
    spec = _spec_from_class(EmitNumbersBlock)
    assert spec.execution_mode == "auto"
    assert spec.panel_manifest is None


def test_the_legacy_module_fields_are_gone_from_the_manifest() -> None:
    """#2493: ``module_url``, ``export_name``, ``css``, ``version`` and ``asset_root`` were removed."""
    import dataclasses

    fields = {field.name for field in dataclasses.fields(PanelManifest)}
    assert fields == {"panel_id", "api_version", "response_schema"}
    with pytest.raises(TypeError):
        PanelManifest(panel_id="pkg.interactive.demo", module_url="/api/blocks/panels/x/index.js")  # type: ignore[call-arg]
