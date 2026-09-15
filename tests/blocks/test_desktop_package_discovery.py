"""Tests for ADR-037 desktop hard-installed source package discovery."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

from scistudio.blocks.registry import BlockRegistry
from scistudio.desktop import paths as desktop_paths


def _write_source_package(
    packages_dir: Path,
    *,
    dist_name: str,
    module_name: str,
    block_name: str,
    package_name: str,
) -> Path:
    package_root = packages_dir / dist_name
    module_dir = package_root / "src" / module_name
    module_dir.mkdir(parents=True)
    (package_root / "pyproject.toml").write_text(
        f'[project]\nname = "{dist_name}"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (module_dir / "__init__.py").write_text(
        "from typing import Any\n"
        "\n"
        "from scistudio.blocks.base.config import BlockConfig\n"
        "from scistudio.blocks.base.package_info import PackageInfo\n"
        "from scistudio.blocks.base.block import Block\n"
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
        f'    return PackageInfo(name="{package_name}", version="0.1.0"), [{block_name}]\n',
        encoding="utf-8",
    )
    return package_root / "src"


def test_scan_discovers_env_package_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    packages_dir = tmp_path / "env-packages"
    src_dir = _write_source_package(
        packages_dir,
        dist_name="scistudio-blocks-envprobe",
        module_name="scistudio_blocks_envprobe",
        block_name="EnvProbeBlock",
        package_name="Env Probe",
    )
    monkeypatch.setenv("SCISTUDIO_PLUGIN_PACKAGE_DIRS", str(packages_dir))

    registry = BlockRegistry()
    registry.scan()

    spec = registry.get_spec("EnvProbeBlock")
    assert spec is not None
    assert spec.source == "package_src"
    assert spec.module_path == "scistudio_blocks_envprobe"
    assert spec.package_name == "Env Probe"
    assert registry.packages()["Env Probe"].version == "0.1.0"
    assert str(src_dir) not in sys.path


def test_scan_discovers_desktop_resource_packages(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    resources_dir = tmp_path / "resources"
    packages_dir = resources_dir / "packages"
    _write_source_package(
        packages_dir,
        dist_name="scistudio-blocks-resourceprobe",
        module_name="scistudio_blocks_resourceprobe",
        block_name="ResourceProbeBlock",
        package_name="Resource Probe",
    )
    monkeypatch.setenv("SCISTUDIO_DESKTOP_RESOURCES", str(resources_dir))

    registry = BlockRegistry()
    registry.scan()

    spec = registry.get_spec("ResourceProbeBlock")
    assert spec is not None
    assert spec.source == "package_src"
    assert spec.package_name == "Resource Probe"


def test_add_package_src_dir_accepts_resolved_src_directory(tmp_path: Path) -> None:
    packages_dir = tmp_path / "manual-packages"
    src_dir = _write_source_package(
        packages_dir,
        dist_name="scistudio-blocks-manualprobe",
        module_name="scistudio_blocks_manualprobe",
        block_name="ManualProbeBlock",
        package_name="Manual Probe",
    )

    registry = BlockRegistry()
    registry.add_package_src_dir(src_dir)
    registry.scan()

    spec = registry.get_spec("ManualProbeBlock")
    assert spec is not None
    assert spec.source == "package_src"
    assert spec.package_name == "Manual Probe"


def test_add_package_src_dir_accepts_flat_installed_package(tmp_path: Path) -> None:
    packages_dir = tmp_path / "installed-packages"
    package_root = packages_dir / "scistudio-blocks-flatprobe-0.1.0"
    module_dir = package_root / "scistudio_blocks_flatprobe"
    module_dir.mkdir(parents=True)
    (module_dir / "__init__.py").write_text(
        "from typing import Any\n"
        "\n"
        "from scistudio.blocks.base.config import BlockConfig\n"
        "from scistudio.blocks.base.package_info import PackageInfo\n"
        "from scistudio.blocks.base.block import Block\n"
        "\n"
        "class FlatProbeBlock(Block):\n"
        '    name = "FlatProbeBlock"\n'
        "    input_ports = []\n"
        "    output_ports = []\n"
        '    config_schema = {"type": "object", "properties": {}}\n'
        "\n"
        "    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:\n"
        "        return {}\n"
        "\n"
        "def get_block_package():\n"
        '    return PackageInfo(name="Flat Probe", version="0.1.0"), [FlatProbeBlock]\n',
        encoding="utf-8",
    )

    registry = BlockRegistry()
    registry.add_package_src_dir(packages_dir)
    registry.scan()

    spec = registry.get_spec("FlatProbeBlock")
    assert spec is not None
    assert spec.source == "package_src"
    assert spec.module_path == "scistudio_blocks_flatprobe"
    assert spec.package_name == "Flat Probe"


def test_scan_imports_source_package_with_per_package_runtime_dependencies(tmp_path: Path) -> None:
    packages_dir = tmp_path / "installed-packages"
    package_root = packages_dir / "scistudio-blocks-runtimeprobe-0.1.0"
    module_dir = package_root / "src" / "scistudio_blocks_runtimeprobe"
    runtime_dir = package_root / "site-packages"
    module_dir.mkdir(parents=True)
    runtime_dir.mkdir(parents=True)
    (runtime_dir / "runtime_dep.py").write_text("VALUE = 'runtime-ok'\n", encoding="utf-8")
    (package_root / "pyproject.toml").write_text(
        '[project]\nname = "scistudio-blocks-runtimeprobe"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (module_dir / "__init__.py").write_text(
        "from typing import Any\n"
        "\n"
        "import runtime_dep\n"
        "from scistudio.blocks.base.config import BlockConfig\n"
        "from scistudio.blocks.base.package_info import PackageInfo\n"
        "from scistudio.blocks.base.block import Block\n"
        "\n"
        "class RuntimeProbeBlock(Block):\n"
        '    name = "RuntimeProbeBlock"\n'
        "    description = runtime_dep.VALUE\n"
        "    input_ports = []\n"
        "    output_ports = []\n"
        '    config_schema = {"type": "object", "properties": {}}\n'
        "\n"
        "    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:\n"
        "        return {}\n"
        "\n"
        "def get_block_package():\n"
        '    return PackageInfo(name="Runtime Probe", version="0.1.0"), [RuntimeProbeBlock]\n',
        encoding="utf-8",
    )

    registry = BlockRegistry()
    registry.add_package_src_dir(packages_dir)
    registry.scan()

    spec = registry.get_spec("RuntimeProbeBlock")
    assert spec is not None
    assert spec.description == "runtime-ok"
    assert spec.source == "package_src"
    assert str(module_dir.parent.resolve()) in spec.runtime_import_roots
    assert str(runtime_dir.resolve()) in spec.runtime_import_roots
    assert str(module_dir.parent) not in sys.path
    assert str(runtime_dir) not in sys.path


def test_scan_source_package_includes_shared_user_site_in_runtime_import_roots(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """#1772: installed plugin blocks must surface shared user-site deps
    (installed via the in-app Python terminal) to the worker, after the
    package's own roots so per-package deps keep precedence."""
    monkeypatch.setattr(desktop_paths, "_platformdirs_dir", lambda kind: tmp_path / kind)
    shared_site = desktop_paths.user_python_site_dir()
    shared_site.mkdir(parents=True)

    packages_dir = tmp_path / "installed-packages"
    src_dir = _write_source_package(
        packages_dir,
        dist_name="scistudio-blocks-sharedprobe",
        module_name="scistudio_blocks_sharedprobe",
        block_name="SharedProbeBlock",
        package_name="Shared Probe",
    )

    registry = BlockRegistry()
    registry.add_package_src_dir(packages_dir)
    registry.scan()

    spec = registry.get_spec("SharedProbeBlock")
    assert spec is not None
    roots = spec.runtime_import_roots
    assert str(shared_site.resolve()) in roots
    assert str(src_dir.resolve()) in roots
    # Per-package roots are ordered before the shared site.
    assert roots.index(str(src_dir.resolve())) < roots.index(str(shared_site.resolve()))
    # Shared site is not leaked into the parent interpreter's sys.path.
    assert str(shared_site) not in sys.path


def test_scan_does_not_leak_package_dependencies_to_global_pythonpath(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    packages_dir = tmp_path / "installed-packages"
    package_root = packages_dir / "scistudio-blocks-envisolation-0.1.0"
    module_dir = package_root / "src" / "scistudio_blocks_envisolation"
    runtime_dir = package_root / "site-packages"
    module_dir.mkdir(parents=True)
    runtime_dir.mkdir(parents=True)
    (runtime_dir / "runtime_dep.py").write_text("VALUE = 'runtime-ok'\n", encoding="utf-8")
    (package_root / "pyproject.toml").write_text(
        '[project]\nname = "scistudio-blocks-envisolation"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (module_dir / "__init__.py").write_text(
        "from typing import Any\n"
        "\n"
        "import runtime_dep\n"
        "from scistudio.blocks.base.config import BlockConfig\n"
        "from scistudio.blocks.base.package_info import PackageInfo\n"
        "from scistudio.blocks.base.block import Block\n"
        "\n"
        "class EnvIsolationBlock(Block):\n"
        '    name = "EnvIsolationBlock"\n'
        "    description = runtime_dep.VALUE\n"
        "    input_ports = []\n"
        "    output_ports = []\n"
        '    config_schema = {"type": "object", "properties": {}}\n'
        "\n"
        "    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:\n"
        "        return {}\n"
        "\n"
        "def get_block_package():\n"
        '    return PackageInfo(name="Env Isolation", version="0.1.0"), [EnvIsolationBlock]\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("PYTHONPATH", "/core-only")

    registry = BlockRegistry()
    registry.add_package_src_dir(packages_dir)
    registry.scan()

    spec = registry.get_spec("EnvIsolationBlock")
    assert spec is not None
    assert spec.description == "runtime-ok"
    assert str(runtime_dir.resolve()) in spec.runtime_import_roots
    assert os.environ["PYTHONPATH"] == "/core-only"


def test_tier1_dropin_imports_shared_user_python_dependency(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(desktop_paths, "_platformdirs_dir", lambda kind: tmp_path / kind)
    runtime_dir = desktop_paths.user_python_site_dir()
    runtime_dir.mkdir(parents=True)
    (runtime_dir / "user_dep.py").write_text("VALUE = 'user-dep-ok'\n", encoding="utf-8")

    scan_dir = tmp_path / "blocks"
    scan_dir.mkdir()
    (scan_dir / "user_dep_block.py").write_text(
        "from typing import Any\n"
        "\n"
        "import user_dep\n"
        "from scistudio.blocks.base.config import BlockConfig\n"
        "from scistudio.blocks.base.block import Block\n"
        "\n"
        "class UserDepProbeBlock(Block):\n"
        '    name = "UserDepProbeBlock"\n'
        "    description = user_dep.VALUE\n"
        "    input_ports = []\n"
        "    output_ports = []\n"
        '    config_schema = {"type": "object", "properties": {}}\n'
        "\n"
        "    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:\n"
        "        return {}\n",
        encoding="utf-8",
    )

    registry = BlockRegistry()
    registry.add_scan_dir(scan_dir)
    registry.scan()

    spec = registry.get_spec("UserDepProbeBlock")
    assert spec is not None
    assert spec.description == "user-dep-ok"
    assert str(runtime_dir) not in sys.path


def test_scan_reloads_reinstalled_package_from_same_source_path(tmp_path: Path) -> None:
    packages_dir = tmp_path / "installed-packages"
    dist_name = "scistudio-blocks-reloadprobe-0.1.0"
    module_name = "scistudio_blocks_reloadprobe"
    package_root = packages_dir / dist_name

    _write_source_package(
        packages_dir,
        dist_name=dist_name,
        module_name=module_name,
        block_name="ReloadProbeBlockV1",
        package_name="Reload Probe",
    )
    registry = BlockRegistry()
    registry.add_package_src_dir(packages_dir)
    registry.scan()
    assert registry.get_spec("ReloadProbeBlockV1") is not None
    assert registry.get_spec("ReloadProbeBlockV2") is None

    shutil.rmtree(package_root)
    _write_source_package(
        packages_dir,
        dist_name=dist_name,
        module_name=module_name,
        block_name="ReloadProbeBlockV2",
        package_name="Reload Probe",
    )
    registry = BlockRegistry()
    registry.add_package_src_dir(packages_dir)
    registry.scan()

    assert registry.get_spec("ReloadProbeBlockV1") is None
    assert registry.get_spec("ReloadProbeBlockV2") is not None


def test_hot_reload_picks_up_edited_source_package(tmp_path: Path) -> None:
    """#1791: hot_reload() re-scans Tier 3 and re-imports the edited package.

    Before the fix, hot_reload() re-scanned Tier 1 only, so an in-place edit
    to a packaged ``scistudio_blocks_*`` plugin stayed invisible until the
    process restarted.
    """
    packages_dir = tmp_path / "installed-packages"
    dist_name = "scistudio-blocks-hotreloadedit"
    module_name = "scistudio_blocks_hotreloadedit"
    _write_source_package(
        packages_dir,
        dist_name=dist_name,
        module_name=module_name,
        block_name="HotReloadEditBlockV1",
        package_name="Hot Reload Edit",
    )
    registry = BlockRegistry()
    registry.add_package_src_dir(packages_dir)
    registry.scan()
    assert registry.get_spec("HotReloadEditBlockV1") is not None

    # Edit the installed package in place: V1 renamed to V2. The extra
    # comment line changes the file size so a stale .pyc cannot survive.
    init_file = packages_dir / dist_name / "src" / module_name / "__init__.py"
    init_file.write_text(
        init_file.read_text(encoding="utf-8").replace("V1", "V2") + "# edited\n",
        encoding="utf-8",
    )

    registry.hot_reload()

    assert registry.get_spec("HotReloadEditBlockV1") is None
    spec = registry.get_spec("HotReloadEditBlockV2")
    assert spec is not None
    assert spec.source == "package_src"
    assert "Hot Reload Edit" in registry.packages()


def test_hot_reload_drops_removed_source_package(tmp_path: Path) -> None:
    """#1791: hot_reload() removes a Tier 3 package that was deleted on disk."""
    packages_dir = tmp_path / "installed-packages"
    dist_name = "scistudio-blocks-hotreloadgone"
    _write_source_package(
        packages_dir,
        dist_name=dist_name,
        module_name="scistudio_blocks_hotreloadgone",
        block_name="HotReloadGoneBlock",
        package_name="Hot Reload Gone",
    )
    registry = BlockRegistry()
    registry.add_package_src_dir(packages_dir)
    registry.scan()
    assert registry.get_spec("HotReloadGoneBlock") is not None
    assert "Hot Reload Gone" in registry.packages()

    shutil.rmtree(packages_dir / dist_name)

    registry.hot_reload()

    assert registry.get_spec("HotReloadGoneBlock") is None
    assert "Hot Reload Gone" not in registry.packages()


def test_hot_reload_runs_same_second_same_size_edit_not_cached_bytecode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """#1791 / PR #2185 review: a same-length edit inside one mtime second re-imports.

    CPython accepts a cached ``.pyc`` whose recorded source mtime (whole
    seconds) and size both match, so evicting ``sys.modules`` alone would
    re-register the previous class. The edit below keeps the byte length and
    restores the original mtime, which is exactly that key.
    """
    import importlib.util

    monkeypatch.setattr(sys, "dont_write_bytecode", False)
    packages_dir = tmp_path / "installed-packages"
    dist_name = "scistudio-blocks-samesecond"
    module_name = "scistudio_blocks_samesecond"
    _write_source_package(
        packages_dir,
        dist_name=dist_name,
        module_name=module_name,
        block_name="SameSecondBlockV1",
        package_name="Same Second",
    )
    registry = BlockRegistry()
    registry.add_package_src_dir(packages_dir)
    registry.scan()
    assert registry.get_spec("SameSecondBlockV1") is not None

    init_file = packages_dir / dist_name / "src" / module_name / "__init__.py"
    assert Path(importlib.util.cache_from_source(str(init_file))).exists()
    before = init_file.stat()
    edited = init_file.read_text(encoding="utf-8").replace("V1", "V2")
    assert len(edited.encode("utf-8")) == before.st_size
    init_file.write_text(edited, encoding="utf-8")
    os.utime(init_file, ns=(before.st_atime_ns, before.st_mtime_ns))

    registry.hot_reload()

    assert registry.get_spec("SameSecondBlockV1") is None
    assert registry.get_spec("SameSecondBlockV2") is not None


def test_hot_reload_keeps_nested_type_module_identity(tmp_path: Path) -> None:
    """#1791 / PR #2185 review: ``plugin.types.*`` descendants survive eviction.

    Type classes must keep their identity across a block-package refresh, so a
    types *package* (``plugin.types.image``) is exempt along with ``plugin.types``.
    """
    packages_dir = tmp_path / "installed-packages"
    dist_name = "scistudio-blocks-nestedtypes"
    module_name = "scistudio_blocks_nestedtypes"
    _write_source_package(
        packages_dir,
        dist_name=dist_name,
        module_name=module_name,
        block_name="NestedTypesBlock",
        package_name="Nested Types",
    )
    module_dir = packages_dir / dist_name / "src" / module_name
    (module_dir / "types").mkdir()
    (module_dir / "types" / "__init__.py").write_text("", encoding="utf-8")
    (module_dir / "types" / "image.py").write_text("class NestedImage:\n    pass\n", encoding="utf-8")
    init_file = module_dir / "__init__.py"
    init_file.write_text(
        f"from {module_name}.types.image import NestedImage  # noqa: F401\n" + init_file.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    registry = BlockRegistry()
    registry.add_package_src_dir(packages_dir)
    registry.scan()
    original = sys.modules[f"{module_name}.types.image"].NestedImage

    registry.hot_reload()

    assert registry.get_spec("NestedTypesBlock") is not None
    assert sys.modules[f"{module_name}.types.image"].NestedImage is original
    assert sys.modules[f"{module_name}.types"] is not None


def test_is_type_module_covers_types_descendants() -> None:
    from scistudio.blocks.registry._scan import _is_type_module

    assert _is_type_module("plugin.types")
    assert _is_type_module("plugin.types.image")
    assert _is_type_module("plugin.sub.types.image")
    assert not _is_type_module("plugin")
    assert not _is_type_module("plugin.typesetting")
    assert not _is_type_module("types")
