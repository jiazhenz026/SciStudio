"""Surface 1 (#2196): the scan says why it refused a block instead of dropping it.

Before this, a block the scan refused simply stopped appearing in the palette
and in ``list_blocks``. The refusal was in a server log and, for a whole
drop-in file, in ``dropin_failures()`` — neither of which the authoring agent
reads. These tests cover the per-block record that replaces the silence, at
every tier that can refuse one, plus the panel half of the interactive contract
that is the reason the record was needed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import pytest

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.interactive import InteractiveMixin, InteractivePrompt, PanelManifest
from scistudio.blocks.base.state import ExecutionMode
from scistudio.blocks.process.process_block import ProcessBlock
from scistudio.blocks.registry import BlockContractError, BlockRegistry
from scistudio.blocks.registry._capability import _validate_interactive_capability

GOOD_PANEL = """
export default {
  apiVersion: "1",
  mount(container, host) {
    container.onclick = () => host.confirm({});
    container.oncontextmenu = () => host.cancel();
    return { unmount() {} };
  },
};
"""


def _panel_root(tmp_path: Path, body: str = GOOD_PANEL) -> str:
    root = tmp_path / "panel_assets"
    root.mkdir(exist_ok=True)
    (root / "panel.mjs").write_text(body, encoding="utf-8")
    return str(root)


def _interactive_class(block_name: str, manifest: PanelManifest) -> type:
    """Build an otherwise-valid interactive block carrying *manifest*."""
    declared_name = block_name

    class _Block(InteractiveMixin, ProcessBlock):
        name: ClassVar[str] = declared_name
        execution_mode: ClassVar[ExecutionMode] = ExecutionMode.INTERACTIVE
        interactive_panel: ClassVar[PanelManifest] = manifest

        def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> InteractivePrompt:
            return InteractivePrompt(panel_payload={})

    _Block.__name__ = block_name
    return _Block


# ---------------------------------------------------------------------------
# The panel half of the scan-time contract.
# ---------------------------------------------------------------------------


def test_valid_package_panel_passes_the_scan_validator(tmp_path: Path) -> None:
    cls = _interactive_class(
        "GoodPanelBlock",
        PanelManifest(
            panel_id="pkg.good",
            module_url="/api/blocks/panels/pkg.good/panel.mjs",
            asset_root=_panel_root(tmp_path),
        ),
    )

    _validate_interactive_capability(cls)  # must not raise


def test_panel_module_missing_from_disk_is_refused(tmp_path: Path) -> None:
    """`import_failed`: the 404 that used to reach the user as a broken modal."""
    cls = _interactive_class(
        "MissingModuleBlock",
        PanelManifest(
            panel_id="pkg.missing",
            module_url="/api/blocks/panels/pkg.missing/nope.mjs",
            asset_root=_panel_root(tmp_path),
        ),
    )

    with pytest.raises(BlockContractError) as excinfo:
        _validate_interactive_capability(cls)

    assert excinfo.value.block == "MissingModuleBlock"
    assert any("import_failed" in reason or "not on disk" in reason for reason in excinfo.value.reasons)
    assert excinfo.value.fix


def test_block_contract_error_is_still_a_value_error(tmp_path: Path) -> None:
    """Every other scan-time class-shape refusal is a ``ValueError``; so is this one."""
    cls = _interactive_class(
        "RemotePanelBlock",
        PanelManifest(panel_id="pkg.remote", module_url="https://cdn.example.com/panel.mjs"),
    )

    with pytest.raises(ValueError):
        _validate_interactive_capability(cls)


def test_panel_advisories_never_refuse_a_block(tmp_path: Path) -> None:
    """A panel with no confirm control is a real problem, but not a scan-time one."""
    cls = _interactive_class(
        "AdvisoryOnlyBlock",
        PanelManifest(
            panel_id="pkg.advisory",
            module_url="/api/blocks/panels/pkg.advisory/panel.mjs",
            asset_root=_panel_root(tmp_path, 'export default { apiVersion: "1", mount(c, h) { return {}; } };'),
        ),
    )

    _validate_interactive_capability(cls)  # advisories are logged, never raised


def test_builtin_core_panels_still_scan_clean() -> None:
    """DataRouter / PairEditor carry no ``module_url`` by design and must not regress."""
    registry = BlockRegistry()
    registry.scan()

    assert registry.get_spec("Data Router") is not None
    assert registry.get_spec("Pair Editor") is not None
    # Scoped to the built-ins: a developer machine may carry a stale third-party
    # plugin whose own rejection is not this test's business.
    assert not [r for r in registry.rejections() if r.block in {"DataRouter", "PairEditor"}]


# ---------------------------------------------------------------------------
# The rejection record itself, from a real Tier-1 drop-in scan.
# ---------------------------------------------------------------------------

_DROPIN_TEMPLATE = """
from typing import Any, ClassVar

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.interactive import InteractiveMixin, InteractivePrompt, PanelManifest
from scistudio.blocks.base.state import ExecutionMode
from scistudio.blocks.process.process_block import ProcessBlock


class {class_name}(InteractiveMixin, ProcessBlock):
    name: ClassVar[str] = "{class_name}"
    execution_mode: ClassVar[ExecutionMode] = ExecutionMode.INTERACTIVE
    interactive_panel: ClassVar[PanelManifest] = PanelManifest(
        panel_id="pkg.{panel_id}",
        module_url="{module_url}",
        asset_root={asset_root!r},
    )

    def prepare_prompt(self, inputs: dict[str, Any], config: BlockConfig) -> InteractivePrompt:
        return InteractivePrompt(panel_payload={{}})
"""


def _scan_dropins(tmp_path: Path, files: dict[str, str]) -> BlockRegistry:
    blocks_dir = tmp_path / "blocks"
    blocks_dir.mkdir(exist_ok=True)
    for filename, body in files.items():
        (blocks_dir / filename).write_text(body, encoding="utf-8")
    registry = BlockRegistry()
    registry.add_scan_dir(blocks_dir)
    registry.scan()
    return registry


def test_a_refused_dropin_block_is_reported_with_reason_and_fix(tmp_path: Path) -> None:
    registry = _scan_dropins(
        tmp_path,
        {
            "broken_panel.py": _DROPIN_TEMPLATE.format(
                class_name="BrokenPanel",
                panel_id="broken",
                module_url="/api/blocks/panels/pkg.broken/nope.mjs",
                asset_root=_panel_root(tmp_path),
            )
        },
    )

    assert registry.get_spec("BrokenPanel") is None
    rejections = registry.rejections()
    assert [r.block for r in rejections] == ["BrokenPanel"]
    assert rejections[0].reasons
    assert rejections[0].fix
    assert rejections[0].source == "tier1"


def test_one_refused_block_no_longer_takes_the_rest_of_its_file(tmp_path: Path) -> None:
    """A refusal used to fall to the file-level handler and abandon the whole module."""
    good = _DROPIN_TEMPLATE.format(
        class_name="GoodInFile",
        panel_id="good",
        module_url="/api/blocks/panels/pkg.good/panel.mjs",
        asset_root=_panel_root(tmp_path),
    )
    bad = _DROPIN_TEMPLATE.format(
        class_name="BadInFile",
        panel_id="bad",
        module_url="/api/blocks/panels/pkg.bad/nope.mjs",
        asset_root=_panel_root(tmp_path),
    )
    # ``dir(module)`` is alphabetical, so BadInFile is validated first.
    registry = _scan_dropins(tmp_path, {"mixed.py": bad + good})

    assert registry.get_spec("GoodInFile") is not None
    assert [r.block for r in registry.rejections()] == ["BadInFile"]


def test_a_dropin_that_raises_on_import_is_reported_by_file(tmp_path: Path) -> None:
    """A module that never imports contributes no class name — the file stem stands in."""
    registry = _scan_dropins(tmp_path, {"explodes.py": "raise RuntimeError('boom')\n"})

    rejections = registry.rejections()
    assert [r.block for r in rejections] == ["explodes"]
    assert "boom" in rejections[0].reasons[0]
    # FR-015's file-level record is still written; the two surfaces coexist.
    assert [f.error_type for f in registry.dropin_failures()] == ["RuntimeError"]


def test_a_full_scan_starts_a_fresh_rejection_list(tmp_path: Path) -> None:
    registry = _scan_dropins(
        tmp_path,
        {
            "broken_panel.py": _DROPIN_TEMPLATE.format(
                class_name="BrokenPanel",
                panel_id="broken",
                module_url="/api/blocks/panels/pkg.broken/nope.mjs",
                asset_root=_panel_root(tmp_path),
            )
        },
    )
    assert len(registry.rejections()) == 1

    registry.scan()

    assert len(registry.rejections()) == 1  # rebuilt, not appended to


def test_hot_reload_replaces_only_the_dropin_rejections(tmp_path: Path) -> None:
    """``hot_reload`` rescans Tier 1 alone, so only Tier 1's findings are stale."""
    blocks_dir = tmp_path / "blocks"
    blocks_dir.mkdir()
    target = blocks_dir / "broken_panel.py"
    target.write_text(
        _DROPIN_TEMPLATE.format(
            class_name="BrokenPanel",
            panel_id="broken",
            module_url="/api/blocks/panels/pkg.broken/nope.mjs",
            asset_root=_panel_root(tmp_path),
        ),
        encoding="utf-8",
    )
    registry = BlockRegistry()
    registry.add_scan_dir(blocks_dir)
    registry.scan()
    assert len(registry.rejections()) == 1

    target.write_text(
        _DROPIN_TEMPLATE.format(
            class_name="BrokenPanel",
            panel_id="broken",
            module_url="/api/blocks/panels/pkg.broken/panel.mjs",
            asset_root=_panel_root(tmp_path),
        ),
        encoding="utf-8",
    )
    registry.hot_reload()

    assert registry.rejections() == []
    assert registry.get_spec("BrokenPanel") is not None
