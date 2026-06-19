"""Tests for desktop local package installation."""

from __future__ import annotations

import json
import os
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from scistudio.blocks.registry import BlockRegistry
from scistudio.desktop import package_installer
from scistudio.desktop import paths as desktop_paths
from scistudio.desktop.package_installer import PackageInstallError, install_local_package


def _package_init(block_name: str, package_name: str, version: str = "0.1.0") -> str:
    return (
        "from typing import Any\n"
        "\n"
        "from scistudio.blocks.base.block import Block\n"
        "from scistudio.blocks.base.config import BlockConfig\n"
        "from scistudio.blocks.base.package_info import PackageInfo\n"
        "\n"
        f"class {block_name}(Block):\n"
        f'    name = "{block_name}"\n'
        "    input_ports = []\n"
        "    output_ports = []\n"
        '    config_schema = {"type": "object", "properties": {}}\n'
        "\n"
        "    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:\n"
        "        return {}\n"
        "\n"
        "def get_block_package():\n"
        f'    return PackageInfo(name="{package_name}", version="{version}"), [{block_name}]\n'
    )


def _write_source_package(
    root: Path,
    *,
    dist_name: str,
    module_name: str,
    block_name: str,
    package_name: str,
    version: str = "0.1.0",
    dependencies: tuple[str, ...] = (),
) -> Path:
    package_root = root / dist_name
    module_dir = package_root / "src" / module_name
    module_dir.mkdir(parents=True)
    deps = "".join(f'    "{dependency}",\n' for dependency in dependencies)
    dependency_block = f"dependencies = [\n{deps}]\n" if dependencies else ""
    (package_root / "pyproject.toml").write_text(
        f'[project]\nname = "{dist_name}"\nversion = "{version}"\n{dependency_block}',
        encoding="utf-8",
    )
    (module_dir / "__init__.py").write_text(
        _package_init(block_name, package_name, version),
        encoding="utf-8",
    )
    return package_root


def test_install_source_directory_registers_blocks(tmp_path: Path) -> None:
    source_root = _write_source_package(
        tmp_path / "source",
        dist_name="scistudio-blocks-localprobe",
        module_name="scistudio_blocks_localprobe",
        block_name="LocalProbeBlock",
        package_name="Local Probe",
        version="0.3.0",
    )
    install_root = tmp_path / "installed"

    result = install_local_package(source_root, install_root=install_root)

    assert result.package_name == "scistudio-blocks-localprobe"
    assert result.version == "0.3.0"
    assert result.modules == ("scistudio_blocks_localprobe",)
    assert result.install_path == install_root / "scistudio-blocks-localprobe-0.3.0"
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["source_path"] == str(source_root.resolve())

    registry = BlockRegistry()
    registry.add_package_src_dir(install_root)
    registry.scan()
    spec = registry.get_spec("LocalProbeBlock")
    assert spec is not None
    assert spec.source == "package_src"
    assert spec.module_path == "scistudio_blocks_localprobe"
    assert spec.package_name == "Local Probe"
    assert str(result.install_path / "src") not in sys.path


def test_install_wheel_registers_flat_module_layout(tmp_path: Path) -> None:
    wheel_path = tmp_path / "scistudio_blocks_wheelprobe-0.2.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel_path, "w") as archive:
        archive.writestr(
            "scistudio_blocks_wheelprobe/__init__.py",
            _package_init("WheelProbeBlock", "Wheel Probe", "0.2.0"),
        )
        archive.writestr(
            "scistudio_blocks_wheelprobe-0.2.0.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: scistudio-blocks-wheelprobe\nVersion: 0.2.0\n",
        )

    install_root = tmp_path / "installed"
    result = install_local_package(wheel_path, install_root=install_root)

    assert result.package_name == "scistudio-blocks-wheelprobe"
    assert result.version == "0.2.0"
    assert (result.install_path / "scistudio_blocks_wheelprobe" / "__init__.py").is_file()

    registry = BlockRegistry()
    registry.add_package_src_dir(install_root)
    registry.scan()
    spec = registry.get_spec("WheelProbeBlock")
    assert spec is not None
    assert spec.source == "package_src"
    assert spec.module_path == "scistudio_blocks_wheelprobe"
    assert spec.package_name == "Wheel Probe"


def test_install_source_directory_installs_runtime_dependencies_with_selected_python(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_root = _write_source_package(
        tmp_path / "source",
        dist_name="scistudio-blocks-depprobe",
        module_name="scistudio_blocks_depprobe",
        block_name="DependencyProbeBlock",
        package_name="Dependency Probe",
        dependencies=("scistudio>=0.2.1", "ome-types>=0.5,<0.6", "numpy>=1.24"),
    )
    calls: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> SimpleNamespace:
        calls.append(command)
        target_dir = Path(command[command.index("--target") + 1])
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "scistudio").mkdir(exist_ok=True)
        (target_dir / "scistudio-999.dist-info").mkdir(exist_ok=True)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(package_installer.subprocess, "run", fake_run)
    monkeypatch.setattr(
        package_installer,
        "_python_runtime_info",
        lambda python: package_installer._PythonRuntimeInfo(
            executable=str(Path(python)),
            version="3.11.9",
            cache_tag="cpython-311",
        ),
    )
    bundled_python = tmp_path / "bundled-python"

    result = install_local_package(
        source_root,
        install_root=tmp_path / "installed",
        install_dependencies=True,
        python_executable=bundled_python,
    )

    assert len(calls) == 2
    assert calls[0][:4] == [str(bundled_python), "-m", "pip", "install"]
    assert "--no-deps" in calls[0]
    assert str(source_root.resolve()) not in calls[0]
    dependency_command = calls[1]
    assert dependency_command[:4] == [str(bundled_python), "-m", "pip", "install"]
    assert "ome-types>=0.5,<0.6" in dependency_command
    assert "numpy>=1.24" in dependency_command
    assert all(not arg.startswith("scistudio>=") for arg in dependency_command)
    runtime_dir = result.install_path / desktop_paths.PACKAGE_SITE_DIR_NAME
    assert runtime_dir.is_dir()
    assert not (runtime_dir / "scistudio").exists()
    assert not (runtime_dir / "scistudio-999.dist-info").exists()
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["dependency_runtime"]["cache_tag"] == "cpython-311"
    assert "ome-types>=0.5,<0.6" in manifest["dependency_runtime"]["dependencies"]


def test_user_python_terminal_env_creates_user_wrappers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(desktop_paths, "_platformdirs_dir", lambda kind: tmp_path / kind)
    monkeypatch.setenv("PYTHONPATH", "/existing")

    env = desktop_paths.user_python_terminal_env(tmp_path / "bundled-python")

    site_dir = tmp_path / "data" / "plugins" / "python" / desktop_paths.PACKAGE_SITE_DIR_NAME
    bin_dir = tmp_path / "data" / "plugins" / "python" / ("Scripts" if sys.platform == "win32" else "bin")
    pip_wrapper = bin_dir / ("pip.cmd" if sys.platform == "win32" else "pip")

    assert site_dir.is_dir()
    assert pip_wrapper.is_file()
    assert env["PIP_TARGET"] == str(site_dir)
    assert env["SCISTUDIO_USER_PYTHON_SITE"] == str(site_dir)
    assert str(bin_dir) == env["PATH"].split(os.pathsep)[0]
    assert env["PYTHONPATH"].split(os.pathsep)[0] == str(site_dir.resolve())
    wrapper_text = pip_wrapper.read_text(encoding="utf-8")
    assert "-m pip" in wrapper_text
    assert str(site_dir) in wrapper_text


def test_install_archive_rejects_path_traversal(tmp_path: Path) -> None:
    archive_path = tmp_path / "bad-package.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../escape.py", "print('nope')\n")

    with pytest.raises(PackageInstallError, match="outside its install root"):
        install_local_package(archive_path, install_root=tmp_path / "installed")


def test_repair_installed_package_dependencies_reinstalls_mismatched_abi(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_root = _write_source_package(
        tmp_path / "source",
        dist_name="scistudio-blocks-repairprobe",
        module_name="scistudio_blocks_repairprobe",
        block_name="RepairProbeBlock",
        package_name="Repair Probe",
        dependencies=("numpy>=1.24",),
    )
    install_root = tmp_path / "installed"
    install_path = install_root / "scistudio-blocks-repairprobe-0.1.0"
    site_dir = install_path / desktop_paths.PACKAGE_SITE_DIR_NAME
    site_dir.mkdir(parents=True)
    (site_dir / "native.cpython-312-darwin.so").write_bytes(b"")
    manifest = {
        "format": "source-directory",
        "installed_at": "2026-06-19T00:00:00+00:00",
        "modules": ["scistudio_blocks_repairprobe"],
        "package_name": "scistudio-blocks-repairprobe",
        "source_path": str(source_root),
        "version": "0.1.0",
        "dependency_runtime": {
            "cache_tag": "cpython-312",
            "dependencies": ["numpy>=1.24"],
            "python_executable": "/old/python",
            "python_version": "3.12.7",
        },
    }
    (install_path / "scistudio-local-package.json").write_text(json.dumps(manifest), encoding="utf-8")
    calls: list[tuple[Path, dict[str, object]]] = []

    def fake_install(source: str | Path, **kwargs: object) -> package_installer.LocalPackageInstallResult:
        calls.append((Path(source), kwargs))
        return package_installer.LocalPackageInstallResult(
            package_name="scistudio-blocks-repairprobe",
            version="0.1.0",
            install_path=install_path,
            source_path=Path(source),
            modules=("scistudio_blocks_repairprobe",),
            manifest_path=install_path / "scistudio-local-package.json",
            replaced=True,
        )

    monkeypatch.setattr(
        package_installer,
        "_python_runtime_info",
        lambda python: package_installer._PythonRuntimeInfo(
            executable=str(Path(python)),
            version="3.11.9",
            cache_tag="cpython-311",
        ),
    )
    monkeypatch.setattr(package_installer, "install_local_package", fake_install)

    results = package_installer.repair_installed_package_dependencies(
        install_root=install_root,
        python_executable=tmp_path / "python",
    )

    assert len(results) == 1
    assert results[0].repaired is True
    assert results[0].reason == "compiled dependency targets cpython-312-darwin"
    assert calls == [
        (
            source_root,
            {
                "install_root": install_root,
                "install_dependencies": True,
                "python_executable": str(tmp_path / "python"),
            },
        )
    ]


def test_repair_installed_package_dependencies_skips_current_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_root = _write_source_package(
        tmp_path / "source",
        dist_name="scistudio-blocks-currentprobe",
        module_name="scistudio_blocks_currentprobe",
        block_name="CurrentProbeBlock",
        package_name="Current Probe",
        dependencies=("numpy>=1.24",),
    )
    install_root = tmp_path / "installed"
    install_path = install_root / "scistudio-blocks-currentprobe-0.1.0"
    site_dir = install_path / desktop_paths.PACKAGE_SITE_DIR_NAME
    site_dir.mkdir(parents=True)
    (site_dir / "native.cpython-311-darwin.so").write_bytes(b"")
    manifest = {
        "format": "source-directory",
        "installed_at": "2026-06-19T00:00:00+00:00",
        "modules": ["scistudio_blocks_currentprobe"],
        "package_name": "scistudio-blocks-currentprobe",
        "source_path": str(source_root),
        "version": "0.1.0",
        "dependency_runtime": {
            "cache_tag": "cpython-311",
            "dependencies": ["numpy>=1.24"],
            "python_executable": str(tmp_path / "python"),
            "python_version": "3.11.9",
        },
    }
    (install_path / "scistudio-local-package.json").write_text(json.dumps(manifest), encoding="utf-8")

    monkeypatch.setattr(
        package_installer,
        "_python_runtime_info",
        lambda python: package_installer._PythonRuntimeInfo(
            executable=str(Path(python)),
            version="3.11.9",
            cache_tag="cpython-311",
        ),
    )

    results = package_installer.repair_installed_package_dependencies(
        install_root=install_root,
        python_executable=tmp_path / "python",
    )

    assert results == []
