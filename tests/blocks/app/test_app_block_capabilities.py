from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar

from scieasy.blocks.app.app_block import AppBlock
from scieasy.blocks.app.bridge import FileExchangeBridge
from scieasy.blocks.base.config import BlockConfig
from scieasy.blocks.base.ports import InputPort
from scieasy.blocks.io.capabilities import FormatCapability
from scieasy.blocks.io.io_block import IOBlock
from scieasy.blocks.registry import BlockRegistry, _spec_from_class
from scieasy.core.types.base import DataObject
from scieasy.core.types.collection import Collection
from scieasy.core.types.text import Text


class _BridgeTextSaver(IOBlock):
    name: ClassVar[str] = "_BridgeTextSaver"
    type_name: ClassVar[str] = "test.bridge_text_saver"
    direction: ClassVar[str] = "output"
    input_ports: ClassVar[list[InputPort]] = [InputPort(name="data", accepted_types=[Text])]
    format_capabilities: ClassVar[tuple[FormatCapability, ...]] = (
        FormatCapability(
            id="tests.bridge.text.special.save",
            direction="save",
            data_type=Text,
            format_id="special-text",
            extensions=(".special",),
            label="Special text",
            block_type="_BridgeTextSaver",
            handler="_save_special",
        ),
    )

    def _save_special(self, obj: Text, path: Path, config: dict[str, object]) -> None:
        path.write_text(f"special:{obj.content or ''}", encoding="utf-8")

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        raise NotImplementedError

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        assert isinstance(obj, Text)
        assert config.get("capability_id") == "tests.bridge.text.special.save"
        self._save_special(obj, Path(str(config.get("path"))), dict(config.params))


def _registry(*classes: type) -> BlockRegistry:
    registry = BlockRegistry()
    for cls in classes:
        registry._register_spec(_spec_from_class(cls, source="test"))
    return registry


def test_appblock_output_binner_threads_capability_id(monkeypatch: Any, tmp_path: Path) -> None:
    output = tmp_path / "result.special"
    output.write_text("payload", encoding="utf-8")
    calls: list[dict[str, Any]] = []

    def _fake_reconstruct(path: Path, **kwargs: Any) -> Text:
        calls.append({"path": path, **kwargs})
        return Text(content="payload")

    monkeypatch.setattr("scieasy.blocks.io.materialisation.reconstruct_from_file", _fake_reconstruct)
    block = AppBlock(
        config={
            "params": {
                "output_ports": [
                    {
                        "name": "result",
                        "types": ["Text"],
                        "extension": "special",
                        "capability_id": "tests.bridge.text.special.load",
                    }
                ]
            }
        }
    )
    config = BlockConfig(
        params={
            "output_ports": [
                {
                    "name": "result",
                    "types": ["Text"],
                    "extension": "special",
                    "capability_id": "tests.bridge.text.special.load",
                }
            ]
        }
    )

    result = block._bin_outputs_by_extension([output], config)

    assert result["result"].length == 1
    assert calls == [
        {
            "path": output,
            "target_type": Text,
            "extension": ".special",
            "capability_id": "tests.bridge.text.special.load",
        }
    ]


def test_file_exchange_bridge_threads_input_capability_id_into_manifest(tmp_path: Path) -> None:
    registry = _registry(_BridgeTextSaver)
    bridge = FileExchangeBridge()

    bridge.prepare(
        {"sample": Text(content="payload")},
        tmp_path,
        input_ports=[
            {
                "name": "sample",
                "types": ["Text"],
                "extension": "special",
                "capability_id": "tests.bridge.text.special.save",
            }
        ],
        registry=registry,
    )

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    entry = manifest["sample"]
    assert entry["extension"] == ".special"
    assert entry["format"] == "special-text"
    assert entry["capability_id"] == "tests.bridge.text.special.save"
    assert Path(entry["path"]).read_text(encoding="utf-8") == "special:payload"
