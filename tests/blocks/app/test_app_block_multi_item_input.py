"""Regression tests for AppBlock multi-item input collection staging (#1874).

A multi-item input :class:`Collection` must reach
:meth:`FileExchangeBridge.prepare` *as a Collection* so each item is
materialised to its own file under ``inputs/<port>/`` and recorded as a
``collection`` manifest entry. Before #1874 ``AppBlock.run`` downcast a
multi-item collection to a bare ``list``, which fell through to the JSON
fallback and silently serialised the items as ``repr`` strings, staging no
files. Single-item collections survived because they were unpacked to a bare
``DataObject``; that ergonomic is preserved here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scistudio.blocks.app.app_block import AppBlock
from scistudio.blocks.app.bridge import FileExchangeBridge
from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.artifact import Artifact
from scistudio.core.types.collection import Collection
from scistudio.core.types.dataframe import DataFrame


def _make_artifacts(tmp_path: Path) -> list[Artifact]:
    """Two Artifacts wrapping real source files, mirroring the bug report."""
    a = tmp_path / "a.mzML"
    a.write_text("AAA", encoding="utf-8")
    b = tmp_path / "b.mzXML"
    b.write_text("BBB", encoding="utf-8")
    return [Artifact(file_path=a), Artifact(file_path=b)]


def _run_capturing_prepare(
    block: AppBlock,
    inputs: dict,
    config: BlockConfig,
    tmp_path: Path,
) -> dict:
    """Run ``block.run`` with the bridge/watcher mocked, return the dict that
    ``bridge.prepare`` received (its first positional argument)."""
    with (
        patch("scistudio.blocks.app.app_block.FileExchangeBridge") as mock_bridge_cls,
        patch("scistudio.blocks.app.app_block.subprocess"),
        patch(
            "scistudio.blocks.app.app_block.validate_app_command",
            return_value=["echo", "hello"],
        ),
    ):
        mock_bridge = MagicMock()
        mock_bridge_cls.return_value = mock_bridge
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 4242
        mock_bridge.launch.return_value = mock_proc
        mock_bridge.collect.return_value = {}

        with patch("scistudio.blocks.app.watcher.FileWatcher") as mock_watcher_cls:
            mock_watcher = MagicMock()
            mock_watcher_cls.return_value = mock_watcher
            fake_output = tmp_path / "result.csv"
            fake_output.write_text("a,b\n1,2\n", encoding="utf-8")
            mock_watcher.wait_for_output.return_value = [fake_output]

            block.run(inputs=inputs, config=config)

        return mock_bridge.prepare.call_args[0][0]


# ---------------------------------------------------------------------------
# Unpack layer: what AppBlock.run hands to bridge.prepare
# ---------------------------------------------------------------------------


class TestRunUnpacksToBridge:
    """``AppBlock.run`` must preserve the Collection for 0- and multi-item
    inputs and only unpack a length-one collection to a bare object."""

    def test_multi_item_collection_passed_through_unchanged(self, tmp_path: Path) -> None:
        """A 2-item collection reaches prepare as the same Collection (#1874)."""
        collection = Collection(_make_artifacts(tmp_path))
        config = BlockConfig(params={"app_command": "echo hello"})

        prepared = _run_capturing_prepare(AppBlock(), {"samples": collection}, config, tmp_path)

        assert prepared["samples"] is collection
        # The pre-#1874 bug downcast it to a bare list; guard against regression.
        assert not isinstance(prepared["samples"], list)

    def test_single_item_collection_unpacked_to_bare_object(self, tmp_path: Path) -> None:
        """A length-one collection is still unpacked to a bare DataObject."""
        items = _make_artifacts(tmp_path)[:1]
        collection = Collection(items)
        config = BlockConfig(params={"app_command": "echo hello"})

        prepared = _run_capturing_prepare(AppBlock(), {"samples": collection}, config, tmp_path)

        assert prepared["samples"] is items[0]
        assert isinstance(prepared["samples"], Artifact)

    def test_empty_collection_passed_through_as_collection(self, tmp_path: Path) -> None:
        """A 0-item collection reaches prepare as a Collection (not a bare [])."""
        empty = Collection([], item_type=Artifact)
        config = BlockConfig(params={"app_command": "echo hello"})

        prepared = _run_capturing_prepare(AppBlock(), {"samples": empty}, config, tmp_path)

        assert prepared["samples"] is empty
        assert isinstance(prepared["samples"], Collection)


# ---------------------------------------------------------------------------
# Staging: prepare materialises one file per item with a collection entry
# ---------------------------------------------------------------------------


class TestMultiItemStaging:
    """End-to-end of the bridge layer: a multi-item collection materialises one
    file per item and a ``collection`` manifest entry with absolute paths."""

    def test_multi_item_collection_materialises_one_file_per_item(self, tmp_path: Path) -> None:
        collection = Collection(_make_artifacts(tmp_path))
        exchange = tmp_path / "exchange"

        FileExchangeBridge().prepare({"samples": collection}, exchange, input_ports=None)

        manifest = json.loads((exchange / "manifest.json").read_text())
        entry = manifest["samples"]
        assert entry["type"] == "collection"
        assert entry["item_type"] == "Artifact"
        assert len(entry["items"]) == 2

        coll_dir = exchange / "inputs" / "samples"
        for i, item_entry in enumerate(entry["items"]):
            item_path = Path(item_entry["path"])
            assert item_path.is_absolute()
            assert item_path.is_file()
            assert item_path.parent == coll_dir
            assert item_path.stem == f"item_{i:04d}"

        # No JSON fallback file with repr strings was written for this port.
        assert not (exchange / "inputs" / "samples.json").exists()

    def test_single_item_collection_stages_one_bare_file(self, tmp_path: Path) -> None:
        """Single-item path is byte-identical: one bare file, single-object
        manifest entry (not a collection)."""
        block_inputs = {"samples": _make_artifacts(tmp_path)[0]}  # bare object, as run() unpacks
        exchange = tmp_path / "exchange"

        FileExchangeBridge().prepare(block_inputs, exchange, input_ports=None)

        manifest = json.loads((exchange / "manifest.json").read_text())
        entry = manifest["samples"]
        assert entry["type"] == "Artifact"
        assert "items" not in entry
        staged = Path(entry["path"])
        assert staged.is_file()
        assert staged.parent == exchange / "inputs"

    def test_empty_collection_yields_empty_collection_entry(self, tmp_path: Path) -> None:
        """A 0-item collection produces a safe, empty collection manifest entry
        (no repr, no JSON fallback)."""
        empty = Collection([], item_type=DataFrame)
        exchange = tmp_path / "exchange"

        FileExchangeBridge().prepare({"frames": empty}, exchange, input_ports=None)

        manifest = json.loads((exchange / "manifest.json").read_text())
        entry = manifest["frames"]
        assert entry["type"] == "collection"
        assert entry["item_type"] == "DataFrame"
        assert entry["items"] == []


# ---------------------------------------------------------------------------
# Boundaries: non-homogeneous input and the bare-DataObject-list guard
# ---------------------------------------------------------------------------


class TestInputBoundaries:
    def test_non_homogeneous_collection_rejected_at_construction(self, tmp_path: Path) -> None:
        """A non-homogeneous batch cannot even be built as a Collection, so it
        can never reach the bridge as one (Collection enforces homogeneity)."""
        artifact = _make_artifacts(tmp_path)[0]
        with pytest.raises(TypeError, match="homogeneous"):
            Collection([artifact, DataFrame(columns=["x"], row_count=0)])

    def test_prepare_raises_on_bare_dataobject_list(self, tmp_path: Path) -> None:
        """A bare list of DataObjects passed straight to prepare fails loudly
        instead of silently writing repr strings (#1874)."""
        arts = _make_artifacts(tmp_path)
        exchange = tmp_path / "exchange"

        with pytest.raises(TypeError, match="Collection"):
            FileExchangeBridge().prepare({"samples": arts}, exchange, input_ports=None)

        # Nothing was silently serialised for the port.
        assert not (exchange / "inputs" / "samples.json").exists()

    def test_prepare_still_jsons_plain_scalar_list(self, tmp_path: Path) -> None:
        """A plain list with no DataObjects keeps the documented JSON fallback."""
        exchange = tmp_path / "exchange"

        FileExchangeBridge().prepare({"tags": [1, 2, 3]}, exchange, input_ports=None)

        manifest = json.loads((exchange / "manifest.json").read_text())
        entry = manifest["tags"]
        assert entry["type"] == "json"
        assert json.loads(Path(entry["path"]).read_text()) == [1, 2, 3]


# ---------------------------------------------------------------------------
# End-to-end: multi-item inputs are consumable by a real external tool
# ---------------------------------------------------------------------------


_FAKE_APP = """\
import json, pathlib, sys
cwd = pathlib.Path.cwd()
manifest = json.loads((cwd / "manifest.json").read_text())
entry = manifest["samples"]
paths = [item["path"] for item in entry["items"]]
result = {
    "type": entry["type"],
    "count": len(paths),
    "all_absolute": all(pathlib.Path(p).is_absolute() for p in paths),
    "all_exist": all(pathlib.Path(p).is_file() for p in paths),
    "paths": paths,
}
out = cwd / "outputs"
out.mkdir(exist_ok=True)
(out / "staged.json").write_text(json.dumps(result), encoding="utf-8")
"""


class TestEndToEndExternalTool:
    def test_multi_item_inputs_reach_external_tool_via_manifest(self, tmp_path: Path) -> None:
        """Drive a real AppBlock.run with a fake tool that reads manifest.json and
        proves every input file is on disk at an absolute path it can open."""
        script = tmp_path / "fake_app.py"
        script.write_text(_FAKE_APP, encoding="utf-8")

        exchange = tmp_path / "exchange"  # explicit -> not a temp dir, survives cleanup
        config = BlockConfig(
            params={
                "app_command": [sys.executable, str(script)],
                "exchange_dir": str(exchange),
                "stability_period": 0.2,
            }
        )
        collection = Collection(_make_artifacts(tmp_path))

        result = AppBlock().run(inputs={"samples": collection}, config=config)

        # The block produced an output collection from the tool's result file.
        assert result
        staged = json.loads((exchange / "outputs" / "staged.json").read_text())
        assert staged["type"] == "collection"
        assert staged["count"] == 2
        assert staged["all_absolute"] is True
        assert staged["all_exist"] is True
