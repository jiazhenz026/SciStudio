"""The interactive scaffold emits a pair that works as generated (#2197).

An interactive block is two files, and the two ways an AI-authored one reached
users broken were both in the second file: a panel module the host could not
load, and a panel with no way out of the paused run. These tests hold the
generated pair to the parts of the contract those failures violated —

- the block registers (so ``prepare_prompt``, ``execution_mode``, and the
  ``PanelManifest`` really do satisfy ADR-051 FR-002, not just look like it);
- the manifest's ``module_url`` is the route the backend actually serves, and it
  points at where the panel was actually written;
- the panel module is a **default** export carrying ``apiVersion`` and a
  ``mount`` that returns ``{ unmount }`` — the three shapes whose absence the
  panel host reports as ``export_missing`` / ``api_version_mismatch`` /
  ``not_a_panel_module``;
- confirm and cancel are both wired.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from scistudio.ai.agent.mcp.panel_scaffold import (
    PANEL_MODULE_FILENAME,
    InteractiveScaffold,
    scaffold_interactive_block,
)
from scistudio.blocks.base.state import ExecutionMode
from scistudio.blocks.registry import BlockRegistry


@pytest.fixture
def scaffold(tmp_path: Path) -> InteractiveScaffold:
    """One scaffolded pair with default ports, in an empty project."""
    return scaffold_interactive_block(tmp_path, "pick_baseline")


# --- what gets written -----------------------------------------------------


def test_scaffold_writes_both_halves(tmp_path: Path, scaffold: InteractiveScaffold) -> None:
    assert scaffold.block_path == tmp_path / "blocks" / "pick_baseline.py"
    assert scaffold.panel_path == tmp_path / "blocks" / "pick_baseline_panel" / PANEL_MODULE_FILENAME
    assert scaffold.block_path.is_file()
    assert scaffold.panel_path.is_file()
    assert scaffold.class_name == "PickBaseline"


def test_manifest_points_at_where_the_panel_was_written(scaffold: InteractiveScaffold) -> None:
    """``asset_root`` and ``module_url`` must agree with the file on disk."""
    assert scaffold.asset_root == scaffold.panel_path.parent
    assert scaffold.panel_id == "project.pick_baseline"
    assert scaffold.module_url == f"/api/blocks/panels/{scaffold.panel_id}/{PANEL_MODULE_FILENAME}"
    block_text = scaffold.block_path.read_text(encoding="utf-8")
    assert f'module_url="{scaffold.module_url}"' in block_text
    assert f'panel_id="{scaffold.panel_id}"' in block_text
    assert f'/ "{scaffold.asset_root.name}"' in block_text


def test_module_url_is_the_route_the_backend_serves(scaffold: InteractiveScaffold) -> None:
    """Guard against the ``import_failed`` class: a URL no route answers.

    Compared against the live route table rather than a copied string, so the
    scaffold breaks loudly if the panel asset route ever moves.
    """
    from scistudio.api.routes.blocks import router

    served = {route.path for route in router.routes if "panels" in getattr(route, "path", "")}
    assert "/api/blocks/panels/{panel_id}/{asset_path:path}" in served
    prefix = f"/api/blocks/panels/{scaffold.panel_id}/"
    assert scaffold.module_url.startswith(prefix)
    assert scaffold.module_url[len(prefix) :] == PANEL_MODULE_FILENAME


# --- the block half --------------------------------------------------------


def test_generated_block_registers(tmp_path: Path, scaffold: InteractiveScaffold) -> None:
    """The registry accepts it with no edits — the real ADR-051 FR-002 check."""
    logging.disable(logging.CRITICAL)  # the drop-in scanner warns per file by design
    try:
        registry = BlockRegistry()
        registry.add_scan_dir(scaffold.block_path.parent)
        registry.scan()
    finally:
        logging.disable(logging.NOTSET)

    assert registry.dropin_failures() == []
    spec = registry.all_specs()["Pick Baseline"]
    assert spec.execution_mode == ExecutionMode.INTERACTIVE.value
    manifest = spec.panel_manifest
    assert manifest is not None
    assert manifest["panel_id"] == scaffold.panel_id
    assert manifest["module_url"] == scaffold.module_url
    # ``export_name`` defaults to "default"; the panel module must match it.
    assert manifest["export_name"] == "default"
    assert Path(spec.panel_asset_root) == scaffold.asset_root


def test_generated_block_declares_the_ports_it_was_asked_for(tmp_path: Path) -> None:
    result = scaffold_interactive_block(
        tmp_path,
        "sort_traces",
        input_ports={"traces": {"type": "Array", "description": "the raw traces"}},
        output_ports={"kept": {"type": "Array"}},
    )
    text = result.block_path.read_text(encoding="utf-8")
    assert 'InputPort(name="traces", accepted_types=[Array], description="the raw traces")' in text
    assert 'OutputPort(name="kept", accepted_types=[Array])' in text
    assert "from scistudio.core.types import Array, Collection" in text
    # The stub body wires the first input through to the first output, so the
    # block runs end to end before the author has touched it.
    assert 'return {"kept": inputs["traces"]}' in text


def test_package_port_type_falls_back_and_says_so(tmp_path: Path) -> None:
    """A type no canonical root exports would break the import, so it degrades.

    Degrading silently would be worse than the bug, so the fallback is named in
    a warning the authoring agent is required to read.
    """
    result = scaffold_interactive_block(tmp_path, "review", input_ports={"labels": {"type": "Image"}})
    assert "accepted_types=[DataObject]" in result.block_path.read_text(encoding="utf-8")
    assert any("Image" in warning and "DataObject" in warning for warning in result.warnings)


# --- the panel half --------------------------------------------------------


def test_panel_module_is_a_default_export(scaffold: InteractiveScaffold) -> None:
    """``export_name`` defaults to "default"; a named-only export is export_missing."""
    text = scaffold.panel_path.read_text(encoding="utf-8")
    assert "export default {" in text
    assert "export const" not in text


def test_panel_module_declares_api_version_and_mount(scaffold: InteractiveScaffold) -> None:
    text = scaffold.panel_path.read_text(encoding="utf-8")
    assert 'const API_VERSION = "1";' in text
    assert "apiVersion: API_VERSION," in text
    assert "mount(container, host) {" in text
    # mount must hand back an unmount handle or the host cannot tear it down.
    assert "unmount() {" in text
    assert "return {" in text


def test_panel_module_wires_confirm_and_cancel(scaffold: InteractiveScaffold) -> None:
    """The defect that reached users: a panel with no reachable way out."""
    text = scaffold.panel_path.read_text(encoding="utf-8")
    assert "host.confirm(" in text
    assert "host.cancel()" in text
    assert '"Continue",' in text
    assert '"Cancel",' in text


def test_scaffold_warns_that_both_controls_must_stay(scaffold: InteractiveScaffold) -> None:
    joined = " ".join(scaffold.warnings).lower()
    assert "confirm" in joined and "cancel" in joined


# --- refusals --------------------------------------------------------------


def test_refuses_to_overwrite_an_existing_block(tmp_path: Path) -> None:
    blocks = tmp_path / "blocks"
    blocks.mkdir()
    (blocks / "dup.py").write_text("# already here\n", encoding="utf-8")
    with pytest.raises(FileExistsError):
        scaffold_interactive_block(tmp_path, "dup")
    # Nothing half-written: a block that registers and then fails to open is
    # exactly the state this scaffold exists to prevent.
    assert not (blocks / "dup_panel").exists()


def test_refuses_to_overwrite_an_existing_panel_directory(tmp_path: Path) -> None:
    (tmp_path / "blocks" / "dup_panel").mkdir(parents=True)
    with pytest.raises(FileExistsError):
        scaffold_interactive_block(tmp_path, "dup")
    assert not (tmp_path / "blocks" / "dup.py").exists()


@pytest.mark.parametrize("name", ["Pick", "1pick", "pick-baseline", ""])
def test_rejects_a_name_that_is_not_snake_case(tmp_path: Path, name: str) -> None:
    with pytest.raises(ValueError):
        scaffold_interactive_block(tmp_path, name)


def test_rejects_the_reserved_core_panel_namespace(tmp_path: Path) -> None:
    """``core.*`` resolves from the frontend's built-in registry, not an asset_root."""
    with pytest.raises(ValueError):
        scaffold_interactive_block(tmp_path, "pick", panel_namespace="core")
