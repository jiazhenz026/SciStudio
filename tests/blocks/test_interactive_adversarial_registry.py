"""ADR-051 adversarial registry validation + manifest/API-surface suite.

NO-IMPLEMENTATION-CONTEXT design driven by the contract:

* FR-002 / SC-002 — a malformed interactive declaration is rejected at registry
  SCAN time (not at runtime). Verified two ways: a REAL Tier-1 drop-in scan
  (the malformed blocks must not register; the good one must), and a precise
  unit call into the scan-time validator for the exact error wording.
* §4.2 / FR-007 — ``execution_mode`` and the serialized ``panel_manifest`` are
  surfaced on block metadata (the registry ``BlockSpec``), with the server-only
  ``asset_root`` kept off the wire.
* §4.1 / FR-007 (ADR-048 reuse) — the package panel asset route is path-confined:
  it rejects ``../`` escape, disallowed suffixes, unknown panels, missing files,
  and remote URLs, and serves a confined asset.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
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
from scistudio.previewers.assets import resolve_asset
from scistudio.previewers.models import MissingBundleError
from tests.fixtures.interactive_blocks import EmitNumbersBlock, SelectOptionBlock

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
    interactive_panel = PanelManifest(panel_id="dropin.good", version="1")

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
    interactive_panel = PanelManifest(panel_id="dropin.badmode", version="1")

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
    interactive_panel = PanelManifest(panel_id="dropin.badprompt", version="1")

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
    interactive_panel = PanelManifest(panel_id="", version="1")

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
    # Core panel: bundled, so module_url is empty and there is no asset_root.
    assert spec.panel_manifest.get("module_url") == ""
    assert spec.panel_asset_root is None


def test_non_interactive_block_spec_has_no_manifest() -> None:
    """A plain block reports execution_mode=auto and no panel manifest."""
    spec = _spec_from_class(EmitNumbersBlock)
    assert spec.execution_mode == "auto"
    assert spec.panel_manifest is None
    assert spec.panel_asset_root is None


class _PackagePanelBlock(InteractiveMixin, ProcessBlock):
    """Package-style interactive block whose panel is wheel-served (has asset_root)."""

    name = "PackagePanelBlock"
    execution_mode = ExecutionMode.INTERACTIVE
    interactive_panel = PanelManifest(
        panel_id="pkg.interactive.demo",
        module_url="/api/blocks/panels/pkg.interactive.demo/index.js",
        asset_root="/server/only/secret/root",
        version="2",
    )

    def prepare_prompt(self, inputs: dict[str, Any], config: Any) -> InteractivePrompt:
        return InteractivePrompt(panel_payload={})

    def run(self, inputs: dict[str, Any], config: Any) -> dict[str, Any]:  # type: ignore[override]
        return {}


def test_package_panel_asset_root_kept_off_the_wire() -> None:
    """§4.2: asset_root is server-only — it must never appear in the serialized manifest."""
    spec = _spec_from_class(_PackagePanelBlock)
    assert spec.panel_manifest is not None
    assert "asset_root" not in spec.panel_manifest, "asset_root leaked onto the wire"
    assert spec.panel_manifest["module_url"].startswith("/api/")
    # The server-side confinement root is captured separately on the spec.
    assert spec.panel_asset_root == "/server/only/secret/root"


# ===========================================================================
# I. Package panel asset route — path confinement (ADR-048 reuse).
# ===========================================================================


def _manifest_for(root: Path) -> SimpleNamespace:
    # Mirrors what api/routes/blocks.serve_panel_asset hands to resolve_asset.
    return SimpleNamespace(asset_root=str(root), previewer_id="pkg.interactive.demo")


def test_panel_asset_route_serves_confined_asset(tmp_path: Path) -> None:
    """A valid, confined, allowed-suffix asset is served with the right media type."""
    root = tmp_path / "assets"
    root.mkdir()
    (root / "index.js").write_text("export default {}", encoding="utf-8")

    served = resolve_asset(_manifest_for(root), "index.js")  # type: ignore[arg-type]
    assert served.path == (root / "index.js").resolve()
    assert served.media_type == "text/javascript"


def test_panel_asset_route_rejects_parent_escape(tmp_path: Path) -> None:
    """``../`` traversal that escapes the confinement root is rejected."""
    root = tmp_path / "assets"
    root.mkdir()
    (tmp_path / "secret.js").write_text("stolen", encoding="utf-8")

    with pytest.raises(MissingBundleError):
        resolve_asset(_manifest_for(root), "../secret.js")  # type: ignore[arg-type]


def test_panel_asset_route_rejects_disallowed_suffix(tmp_path: Path) -> None:
    """A disallowed suffix (e.g. .exe) is rejected even if confined and present."""
    root = tmp_path / "assets"
    root.mkdir()
    (root / "payload.exe").write_text("MZ", encoding="utf-8")

    with pytest.raises(MissingBundleError):
        resolve_asset(_manifest_for(root), "payload.exe")  # type: ignore[arg-type]


def test_panel_asset_route_rejects_missing_file(tmp_path: Path) -> None:
    """A confined, allowed-suffix path that does not exist on disk is rejected."""
    root = tmp_path / "assets"
    root.mkdir()
    with pytest.raises(MissingBundleError):
        resolve_asset(_manifest_for(root), "does_not_exist.js")  # type: ignore[arg-type]


def test_panel_asset_route_rejects_remote_url(tmp_path: Path) -> None:
    """A remote (off-origin) URL must never be served."""
    root = tmp_path / "assets"
    root.mkdir()
    with pytest.raises(MissingBundleError):
        resolve_asset(_manifest_for(root), "https://evil.example/x.js")  # type: ignore[arg-type]


def test_panel_asset_route_rejects_when_no_asset_root() -> None:
    """A core panel (no asset_root) is not servable via the package asset route."""
    manifest = SimpleNamespace(asset_root=None, previewer_id="core.panel")
    with pytest.raises(MissingBundleError):
        resolve_asset(manifest, "index.js")  # type: ignore[arg-type]
