from __future__ import annotations

from pathlib import Path
from typing import Any

from scistudio.blocks.code.validation import validate_codeblock_config
from scistudio.blocks.registry import BlockRegistry


class _CapabilityRegistry(BlockRegistry):
    def __init__(self, *, fail_capability_id: str | None = None) -> None:
        super().__init__()
        self.fail_capability_id = fail_capability_id

    def find_saver_capability(
        self,
        *,
        data_type: type,
        extension: str,
        capability_id: str | None = None,
    ) -> object:
        return self._lookup("saver", data_type, extension, capability_id)

    def find_loader_capability(
        self,
        *,
        data_type: type,
        extension: str,
        capability_id: str | None = None,
    ) -> object:
        return self._lookup("loader", data_type, extension, capability_id)

    def _lookup(
        self,
        direction: str,
        data_type: type,
        extension: str,
        capability_id: str | None,
    ) -> object:
        if capability_id == self.fail_capability_id:
            raise ValueError(f"unknown capability {capability_id!r}")
        return {
            "direction": direction,
            "data_type": data_type.__name__,
            "extension": extension,
            "capability_id": capability_id,
        }


def _script(project_dir: Path, name: str = "script.py") -> Path:
    path = project_dir / "scripts" / name
    path.parent.mkdir()
    path.write_text("print('ok')\n", encoding="utf-8")
    return path


def _config(script_path: str, **params: Any) -> dict[str, Any]:
    config: dict[str, Any] = {
        "script_path": script_path,
        "working_directory": ".",
        "exchange_root": "exchange",
        "inputs": [
            {
                "name": "image",
                "direction": "input",
                "data_type": "Text",
                "extension": ".txt",
                "capability_id": "core.text.txt.save",
            }
        ],
        "outputs": [
            {
                "name": "summary",
                "direction": "output",
                "data_type": "Text",
                "extension": ".txt",
                "capability_id": "core.text.txt.load",
            }
        ],
    }
    config.update(params)
    return config


def _messages(config: dict[str, Any], project_dir: Path, registry: BlockRegistry | None = None) -> list[str]:
    return [
        diagnostic.render()
        for diagnostic in validate_codeblock_config(
            config,
            project_dir=project_dir,
            registry=registry or _CapabilityRegistry(),
        )
    ]


def test_valid_codeblock_v2_config_has_no_diagnostics(tmp_path: Path) -> None:
    _script(tmp_path)

    assert _messages(_config("scripts/script.py"), tmp_path) == []


def test_rejects_script_path_outside_project(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.py"
    outside.write_text("print('outside')\n", encoding="utf-8")

    messages = _messages(_config(str(outside)), tmp_path)

    assert any("script_path" in message and "inside the project" in message for message in messages)


def test_rejects_working_directory_that_is_a_file(tmp_path: Path) -> None:
    _script(tmp_path)
    bad_workdir = tmp_path / "not-a-directory"
    bad_workdir.write_text("", encoding="utf-8")

    messages = _messages(_config("scripts/script.py", working_directory="not-a-directory"), tmp_path)

    assert any("working_directory" in message and "must be a directory" in message for message in messages)


def test_rejects_unsupported_script_extension_without_interpreter_check(tmp_path: Path) -> None:
    _script(tmp_path, "script.unknown")

    messages = _messages(_config("scripts/script.unknown"), tmp_path)

    assert any("unsupported script extension" in message and ".unknown" in message for message in messages)


def test_normalizes_backend_extensions_before_script_suffix_check(tmp_path: Path) -> None:
    _script(tmp_path, "script.R")

    messages = _messages(_config("scripts/script.R"), tmp_path)

    assert not any("unsupported script extension" in message for message in messages)


def test_rejects_legacy_language_mode() -> None:
    messages = _messages({"language": "python", "script_path": "scripts/script.py"}, Path.cwd())

    assert any("language" in message and "legacy CodeBlock runner fields" in message for message in messages)


def test_reports_legacy_inline_migration_message() -> None:
    messages = _messages({"mode": "inline", "code": "result = 1"}, Path.cwd())

    assert any("Inline CodeBlock configs are not valid" in message for message in messages)
    assert any("ProcessBlock/custom block" in message for message in messages)


def test_rejects_unknown_data_type(tmp_path: Path) -> None:
    _script(tmp_path)
    config = _config(
        "scripts/script.py",
        outputs=[{"name": "summary", "direction": "output", "data_type": "Image", "extension": ".txt"}],
    )

    messages = _messages(config, tmp_path)

    assert any("data_type" in message and "unknown data_type 'Image'" in message for message in messages)


def test_rejects_invalid_capability_id_syntax(tmp_path: Path) -> None:
    _script(tmp_path)
    config = _config(
        "scripts/script.py",
        inputs=[
            {
                "name": "image",
                "direction": "input",
                "data_type": "Text",
                "extension": ".txt",
                "capability_id": "bad id",
            }
        ],
    )

    messages = _messages(config, tmp_path)

    assert any("capability_id" in message and "bad id" in message for message in messages)


def test_reports_declared_capability_lookup_failure(tmp_path: Path) -> None:
    _script(tmp_path)
    registry = _CapabilityRegistry(fail_capability_id="missing.capability")
    config = _config(
        "scripts/script.py",
        outputs=[
            {
                "name": "summary",
                "direction": "output",
                "data_type": "Text",
                "extension": ".txt",
                "capability_id": "missing.capability",
            }
        ],
    )

    messages = _messages(config, tmp_path, registry=registry)

    assert any("capability lookup failed" in message and "missing.capability" in message for message in messages)


def test_rejects_port_exchange_folder_with_wrong_direction(tmp_path: Path) -> None:
    _script(tmp_path)
    config = _config(
        "scripts/script.py",
        inputs=[
            {
                "name": "image",
                "direction": "input",
                "data_type": "Text",
                "extension": ".txt",
                "exchange_folder": "outputs/image/",
            }
        ],
    )

    messages = _messages(config, tmp_path)

    assert any("exchange_folder" in message and "inputs/" in message for message in messages)
