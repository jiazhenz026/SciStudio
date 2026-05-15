"""Tests for BlockRegistry — Tier 1 scan, hot reload, Tier 2 entry_points."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scieasy.blocks.base.package_info import PackageInfo
from scieasy.blocks.base.state import BlockState
from scieasy.blocks.registry import BlockRegistry, BlockSpec


class TestBlockRegistryTier2:
    """Tier 2: entry_point discovery (always available from installed package)."""

    def test_scan_discovers_entry_points(self) -> None:
        reg = BlockRegistry()
        reg.scan()
        specs = reg.all_specs()
        # Should find at least the built-in blocks from pyproject.toml entry_points.
        assert len(specs) >= 3
        names = list(specs.keys())
        assert "Merge" in names
        assert "Split" in names
        assert "IOBlock" not in names

    def test_instantiate_by_name(self) -> None:
        reg = BlockRegistry()
        reg.scan()
        block = reg.instantiate("Merge")
        assert block.name == "Merge"
        assert block.state == BlockState.IDLE

    def test_instantiate_unknown_raises(self) -> None:
        reg = BlockRegistry()
        with pytest.raises(KeyError, match="not registered"):
            reg.instantiate("NonexistentBlock")


class TestBlockRegistryTier1:
    """Tier 1: drop-in directory scan."""

    def test_scan_discovers_dropin(self, tmp_path: Path) -> None:
        """A .py file with a Block subclass in a scan dir is discovered."""
        dropin = tmp_path / "my_block.py"
        dropin.write_text(
            "from scieasy.blocks.process.process_block import ProcessBlock\n"
            "from scieasy.blocks.base.config import BlockConfig\n"
            "from typing import Any\n"
            "\n"
            "class MyCustomBlock(ProcessBlock):\n"
            "    name = 'My Custom'\n"
            "    algorithm = 'custom'\n"
            "\n"
            "    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:\n"
            "        return {'out': 'hello'}\n"
        )

        reg = BlockRegistry()
        reg.add_scan_dir(tmp_path)
        reg.scan()

        specs = reg.all_specs()
        assert "My Custom" in specs
        assert specs["My Custom"].source == "tier1"
        assert specs["My Custom"].base_category == "process"

    def test_hot_reload_picks_up_new_file(self, tmp_path: Path) -> None:
        """hot_reload() discovers a file added after initial scan."""
        reg = BlockRegistry()
        reg.add_scan_dir(tmp_path)
        reg.scan()

        initial_count = len(reg.all_specs())

        # Add a new block file.
        new_block = tmp_path / "new_block.py"
        new_block.write_text(
            "from scieasy.blocks.process.process_block import ProcessBlock\n"
            "from scieasy.blocks.base.config import BlockConfig\n"
            "from typing import Any\n"
            "\n"
            "class NewBlock(ProcessBlock):\n"
            "    name = 'New Block'\n"
            "    algorithm = 'new'\n"
            "\n"
            "    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:\n"
            "        return {}\n"
        )

        reg.hot_reload()
        assert len(reg.all_specs()) > initial_count
        assert "New Block" in reg.all_specs()

    def test_hot_reload_removes_deleted_file(self, tmp_path: Path) -> None:
        """hot_reload() removes specs for deleted files."""
        dropin = tmp_path / "temp_block.py"
        dropin.write_text(
            "from scieasy.blocks.process.process_block import ProcessBlock\n"
            "from scieasy.blocks.base.config import BlockConfig\n"
            "from typing import Any\n"
            "\n"
            "class TempBlock(ProcessBlock):\n"
            "    name = 'Temp Block'\n"
            "    algorithm = 'temp'\n"
            "\n"
            "    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:\n"
            "        return {}\n"
        )

        reg = BlockRegistry()
        reg.add_scan_dir(tmp_path)
        reg.scan()
        assert "Temp Block" in reg.all_specs()

        # Delete the file and hot-reload.
        dropin.unlink()
        reg.hot_reload()
        assert "Temp Block" not in reg.all_specs()


class TestBlockRegistryLogging:
    """Tests for logged warnings on import/load failures (#169)."""

    def test_tier1_import_error_logged(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """A .py file with a syntax error should log a warning, not crash."""
        bad_file = tmp_path / "bad_block.py"
        bad_file.write_text("this is not valid python!!!")

        registry = BlockRegistry()
        registry.add_scan_dir(tmp_path)

        with caplog.at_level(logging.WARNING):
            registry.scan()

        assert "Failed to import block from" in caplog.text
        assert "bad_block" in caplog.text

    def test_tier1_import_error_does_not_prevent_other_blocks(self, tmp_path: Path) -> None:
        """A bad file should not prevent other valid blocks from loading."""
        bad = tmp_path / "bad.py"
        bad.write_text("raise ImportError('missing dep')")

        good = tmp_path / "good_block.py"
        good.write_text(
            "from scieasy.blocks.process.process_block import ProcessBlock\n"
            "from scieasy.blocks.base.config import BlockConfig\n"
            "from typing import Any\n"
            "\n"
            "class GoodBlock(ProcessBlock):\n"
            "    name = 'good_block'\n"
            "    algorithm = 'good'\n"
            "\n"
            "    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:\n"
            "        return {}\n"
        )

        registry = BlockRegistry()
        registry.add_scan_dir(tmp_path)
        registry.scan()

        assert "good_block" in registry.all_specs()


class TestInferCategory:
    """Tests for _infer_category helper."""

    def test_infer_category_ai_block(self) -> None:
        from scieasy.blocks.ai.ai_block import AIBlock
        from scieasy.blocks.registry import _infer_category

        assert _infer_category(AIBlock) == "ai"

        class MyAIBlock(AIBlock):
            pass

        assert _infer_category(MyAIBlock) == "ai"


class TestPackageInfo:
    """Tests for the PackageInfo dataclass (ADR-025 Phase 2.1)."""

    def test_creation_with_defaults(self) -> None:
        info = PackageInfo(name="Test Package")
        assert info.name == "Test Package"
        assert info.description == ""
        assert info.author == ""
        assert info.version == "0.1.0"

    def test_creation_with_all_fields(self) -> None:
        info = PackageInfo(
            name="SRS Imaging",
            description="Stimulated Raman Scattering toolkit",
            author="Dr. Wang Lab",
            version="1.2.3",
        )
        assert info.name == "SRS Imaging"
        assert info.description == "Stimulated Raman Scattering toolkit"
        assert info.author == "Dr. Wang Lab"
        assert info.version == "1.2.3"

    def test_frozen(self) -> None:
        info = PackageInfo(name="Frozen")
        with pytest.raises(AttributeError):
            info.name = "Changed"  # type: ignore[misc]

    def test_importable_from_base(self) -> None:
        from scieasy.blocks.base import PackageInfo as PackageInfoFromBase

        assert PackageInfoFromBase is PackageInfo


class TestBlockSpecPackageName:
    """Tests for the package_name field on BlockSpec (ADR-025 Phase 2.2)."""

    def test_default_package_name_is_empty(self) -> None:
        spec = BlockSpec(name="TestBlock")
        assert spec.package_name == ""

    def test_package_name_can_be_set(self) -> None:
        spec = BlockSpec(name="TestBlock", package_name="my-package")
        assert spec.package_name == "my-package"


class TestBlockRegistryPackages:
    """Tests for packages() and specs_by_package() (ADR-025 Phase 2.2)."""

    def test_packages_returns_dict(self) -> None:
        reg = BlockRegistry()
        result = reg.packages()
        assert isinstance(result, dict)
        # Empty before scan adds any external packages.
        assert len(result) == 0

    def test_packages_returns_copy(self) -> None:
        reg = BlockRegistry()
        p1 = reg.packages()
        p2 = reg.packages()
        assert p1 is not p2

    def test_specs_by_package_groups_correctly(self) -> None:
        reg = BlockRegistry()
        # Manually register some specs with different package_names.
        spec_a = BlockSpec(name="A", package_name="pkg1")
        spec_b = BlockSpec(name="B", package_name="pkg1")
        spec_c = BlockSpec(name="C", package_name="pkg2")
        spec_d = BlockSpec(name="D", package_name="")

        reg._register_spec(spec_a)
        reg._register_spec(spec_b)
        reg._register_spec(spec_c)
        reg._register_spec(spec_d)

        grouped = reg.specs_by_package()
        assert "pkg1" in grouped
        assert "pkg2" in grouped
        assert "" in grouped
        assert len(grouped["pkg1"]) == 2
        assert len(grouped["pkg2"]) == 1
        assert len(grouped[""]) == 1
        assert {s.name for s in grouped["pkg1"]} == {"A", "B"}

    def test_specs_by_package_builtins_have_empty_package(self) -> None:
        reg = BlockRegistry()
        reg.scan()
        grouped = reg.specs_by_package()
        # Built-in blocks should be under empty string or entry-point name.
        assert "" in grouped or any(grouped.values())


class TestScanTier2CallableProtocol:
    """Tests for _scan_tier2 callable protocol (ADR-025 Phase 2.2)."""

    def _make_mock_block_class(self, name: str = "MockBlock") -> type:
        """Create a minimal mock Block subclass for testing."""
        from scieasy.blocks.base.block import Block

        cls = type(
            name,
            (Block,),
            {
                "name": name,
                "description": f"Mock {name}",
                "version": "0.1.0",
                "input_ports": [],
                "output_ports": [],
                "config_schema": {"type": "object", "properties": {}},
                "run": lambda self, inputs, config: {},
            },
        )
        return cls

    def _make_mock_entry_point(self, name: str, load_return: object) -> MagicMock:
        """Create a mock entry-point that returns load_return on .load()."""
        ep = MagicMock()
        ep.name = name
        ep.value = f"mock_module:{name}"
        ep.load.return_value = load_return
        return ep

    def test_tuple_return_with_package_info(self) -> None:
        """Entry-point returning (PackageInfo, list) populates package_name."""
        info = PackageInfo(name="SRS Imaging", author="Dr. Wang")
        block_cls = self._make_mock_block_class("SRSBlock")

        def get_blocks():
            return info, [block_cls]

        ep = self._make_mock_entry_point("srs", get_blocks)

        mock_eps = MagicMock()
        mock_eps.select.return_value = [ep]

        reg = BlockRegistry()
        with patch("importlib.metadata.entry_points", return_value=mock_eps):
            reg._scan_tier2()

        # Verify block is registered with correct package_name.
        spec = reg.get_spec("SRSBlock")
        assert spec is not None
        assert spec.package_name == "SRS Imaging"
        assert spec.source == "entry_point"

        # Verify PackageInfo is stored.
        pkgs = reg.packages()
        assert "SRS Imaging" in pkgs
        assert pkgs["SRS Imaging"].author == "Dr. Wang"

    def test_abstract_block_entry_point_logs_precise_warning(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Abstract Block entry-points should not be reported as non-Block items."""
        from abc import ABC, abstractmethod

        from scieasy.blocks.base.block import Block

        abstract_block = type(
            "AbstractMockBlock",
            (Block, ABC),
            {
                "name": "Abstract Mock",
                "description": "abstract",
                "version": "0.1.0",
                "input_ports": [],
                "output_ports": [],
                "config_schema": {"type": "object", "properties": {}},
                "run": abstractmethod(lambda self, inputs, config: {}),
            },
        )
        ep = self._make_mock_entry_point("abstract_block", abstract_block)
        mock_eps = MagicMock()
        mock_eps.select.return_value = [ep]

        reg = BlockRegistry()
        with patch("importlib.metadata.entry_points", return_value=mock_eps), caplog.at_level(logging.WARNING):
            reg._scan_tier2()

        assert "contained abstract Block subclass" in caplog.text
        assert "contained non-Block item" not in caplog.text

    def test_plain_list_return_uses_ep_name(self) -> None:
        """Entry-point returning plain list uses ep.name as package_name."""
        block_cls = self._make_mock_block_class("GenomicsBlock")

        def get_blocks():
            return [block_cls]

        ep = self._make_mock_entry_point("genomics", get_blocks)

        mock_eps = MagicMock()
        mock_eps.select.return_value = [ep]

        reg = BlockRegistry()
        with patch("importlib.metadata.entry_points", return_value=mock_eps):
            reg._scan_tier2()

        spec = reg.get_spec("GenomicsBlock")
        assert spec is not None
        assert spec.package_name == "genomics"

        # No PackageInfo stored for plain list returns.
        assert len(reg.packages()) == 0

    def test_entry_point_load_failure_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Entry-point that fails to load logs warning and continues."""
        ep = MagicMock()
        ep.name = "bad_package"
        ep.load.side_effect = ImportError("module not found")

        mock_eps = MagicMock()
        mock_eps.select.return_value = [ep]

        reg = BlockRegistry()
        with (
            patch("importlib.metadata.entry_points", return_value=mock_eps),
            caplog.at_level(logging.WARNING),
        ):
            reg._scan_tier2()

        assert "Failed to load entry_point 'bad_package'" in caplog.text

    def test_entry_point_callable_failure_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Entry-point callable that raises logs warning and continues."""

        def bad_get_blocks():
            raise RuntimeError("something broke")

        ep = self._make_mock_entry_point("broken", bad_get_blocks)

        mock_eps = MagicMock()
        mock_eps.select.return_value = [ep]

        reg = BlockRegistry()
        with (
            patch("importlib.metadata.entry_points", return_value=mock_eps),
            caplog.at_level(logging.WARNING),
        ):
            reg._scan_tier2()

        assert "Failed to process entry_point 'broken'" in caplog.text

    def test_multiple_blocks_in_one_entry_point(self) -> None:
        """An entry-point can return multiple block classes."""
        info = PackageInfo(name="Multi-Block Package")
        cls_a = self._make_mock_block_class("AlphaBlock")
        cls_b = self._make_mock_block_class("BetaBlock")

        def get_blocks():
            return info, [cls_a, cls_b]

        ep = self._make_mock_entry_point("multi", get_blocks)

        mock_eps = MagicMock()
        mock_eps.select.return_value = [ep]

        reg = BlockRegistry()
        with patch("importlib.metadata.entry_points", return_value=mock_eps):
            reg._scan_tier2()

        assert reg.get_spec("AlphaBlock") is not None
        assert reg.get_spec("BetaBlock") is not None
        assert reg.get_spec("AlphaBlock").package_name == "Multi-Block Package"
        assert reg.get_spec("BetaBlock").package_name == "Multi-Block Package"

    def test_no_entry_points_does_not_crash(self) -> None:
        """_scan_tier2 works when no entry-points exist."""
        mock_eps = MagicMock()
        mock_eps.select.return_value = []

        reg = BlockRegistry()
        with patch("importlib.metadata.entry_points", return_value=mock_eps):
            reg._scan_tier2()

        assert len(reg.all_specs()) == 0
        assert len(reg.packages()) == 0


# ----------------------------------------------------------------------------
# Stage 10.1 Part 2 — skipped test stubs authored by Agent A.
#
# Agent B will remove the skip markers and implement these in Part 2.
# ----------------------------------------------------------------------------


class TestStage101CategoryAndSource:
    """Stage 10.1 — category ClassVar override, Custom default, source rename."""

    @pytest.mark.skip(reason="Agent B implements in Stage 10.1 Part 2")
    def test_explicit_category_classvar_wins(self, tmp_path: Path) -> None:
        """A Tier 1 block with ``category = "segmentation"`` keeps that value.

        The explicit ClassVar override must take precedence over the Custom
        default Agent B applies in ``_scan_tier1``. Drop-in blocks that
        declare a category are NOT reclassified as Custom.
        """

    @pytest.mark.skip(reason="Agent B implements in Stage 10.1 Part 2")
    def test_tier1_block_without_category_defaults_to_custom(self, tmp_path: Path) -> None:
        """A Tier 1 drop-in block with no category ClassVar gets "Custom".

        This verifies the default assignment in ``_scan_tier1`` — blocks
        from drop-in directories are palette-classified as Custom unless
        they explicitly declare otherwise.
        """

    @pytest.mark.skip(reason="Agent B implements in Stage 10.1 Part 2")
    def test_tier2_block_without_category_uses_hierarchy_inference(self) -> None:
        """An entry-point block without a ClassVar still uses hierarchy inference.

        Tier 2 (installed packages) must NOT be classified as Custom.
        A ProcessBlock subclass from an entry-point gets ``category == "process"``.
        """

    @pytest.mark.skip(reason="Agent B implements in Stage 10.1 Part 2")
    def test_spec_source_values_after_rename(self) -> None:
        """After the Stage 10.1 rename, source values are builtin/custom/package.

        - ``_scan_builtins`` -> ``spec.source == "builtin"``
        - ``_scan_tier1``    -> ``spec.source == "custom"``
        - ``_scan_tier2``    -> ``spec.source == "package"``
        """

    @pytest.mark.skip(reason="Agent B implements in Stage 10.1 Part 2")
    def test_hot_reload_still_recognizes_custom_source(self, tmp_path: Path) -> None:
        """``hot_reload`` prunes stale Tier 1 specs by matching new ``custom`` source.

        After Agent B updates the comparison in ``hot_reload`` to
        ``spec.source == "custom"``, deleted drop-in files are still pruned.
        """


# ----------------------------------------------------------------------------
# ADR-030 — config_schema MRO merge tests
# ----------------------------------------------------------------------------


class TestMergeConfigSchema:
    """ADR-030: _merge_config_schema() merges properties along the MRO."""

    def test_child_properties_override_parent(self) -> None:
        """When both parent and child declare the same field, child wins."""
        from typing import Any, ClassVar

        from scieasy.blocks.base.block import Block
        from scieasy.blocks.registry import _merge_config_schema

        class Parent(Block):
            config_schema: ClassVar[dict[str, Any]] = {
                "type": "object",
                "properties": {
                    "field_a": {"type": "string", "title": "Parent A"},
                },
                "required": ["field_a"],
            }

            def run(self, inputs, config):
                return {}

        class Child(Parent):
            config_schema: ClassVar[dict[str, Any]] = {
                "type": "object",
                "properties": {
                    "field_a": {"type": "string", "title": "Child A"},
                },
                "required": [],
            }

        merged = _merge_config_schema(Child)
        assert merged["properties"]["field_a"]["title"] == "Child A"
        assert "field_a" in merged["required"]

    def test_parent_fields_appear_when_not_overridden(self) -> None:
        """Fields declared only in parent appear in the merged schema."""
        from typing import Any, ClassVar

        from scieasy.blocks.base.block import Block
        from scieasy.blocks.registry import _merge_config_schema

        class Parent(Block):
            config_schema: ClassVar[dict[str, Any]] = {
                "type": "object",
                "properties": {
                    "parent_field": {"type": "string"},
                },
                "required": ["parent_field"],
            }

            def run(self, inputs, config):
                return {}

        class Child(Parent):
            config_schema: ClassVar[dict[str, Any]] = {
                "type": "object",
                "properties": {
                    "child_field": {"type": "number"},
                },
                "required": ["child_field"],
            }

        merged = _merge_config_schema(Child)
        assert "parent_field" in merged["properties"]
        assert "child_field" in merged["properties"]
        assert "parent_field" in merged["required"]
        assert "child_field" in merged["required"]

    def test_direction_aware_path_for_output_ioblock(self) -> None:
        """Output IOBlock subclass gets directory_browser + single-string path."""
        from typing import Any, ClassVar

        from scieasy.blocks.base.config import BlockConfig
        from scieasy.blocks.io.io_block import IOBlock
        from scieasy.blocks.registry import _merge_config_schema
        from scieasy.core.types.base import DataObject
        from scieasy.core.types.collection import Collection

        class MySaver(IOBlock):
            direction: ClassVar[str] = "output"

            config_schema: ClassVar[dict[str, Any]] = {
                "type": "object",
                "properties": {
                    "format": {"type": "string"},
                },
                "required": [],
            }

            def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
                raise NotImplementedError

            def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
                pass

        merged = _merge_config_schema(MySaver)
        path_prop = merged["properties"]["path"]
        assert path_prop["type"] == "string"
        assert path_prop["ui_widget"] == "directory_browser"
        assert "items" not in path_prop

    def test_input_ioblock_inherits_file_browser(self) -> None:
        """Input IOBlock subclass inherits file_browser + array path from base."""
        from typing import Any, ClassVar

        from scieasy.blocks.base.config import BlockConfig
        from scieasy.blocks.io.io_block import IOBlock
        from scieasy.blocks.registry import _merge_config_schema
        from scieasy.core.types.base import DataObject
        from scieasy.core.types.collection import Collection

        class MyLoader(IOBlock):
            direction: ClassVar[str] = "input"

            config_schema: ClassVar[dict[str, Any]] = {
                "type": "object",
                "properties": {
                    "format": {"type": "string"},
                },
                "required": [],
            }

            def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
                raise NotImplementedError

            def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
                raise NotImplementedError

        merged = _merge_config_schema(MyLoader)
        path_prop = merged["properties"]["path"]
        assert path_prop["type"] == ["string", "array"]
        assert path_prop["ui_widget"] == "file_browser"
        assert "items" in path_prop

    def test_appblock_subclass_inherits_output_dir(self) -> None:
        """AppBlock subclass inherits output_dir from the base class."""
        from typing import Any, ClassVar

        from scieasy.blocks.app.app_block import AppBlock
        from scieasy.blocks.registry import _merge_config_schema

        class MyApp(AppBlock):
            app_command: ClassVar[str] = "fiji"

            config_schema: ClassVar[dict[str, Any]] = {
                "type": "object",
                "properties": {
                    "custom_field": {"type": "string"},
                },
                "required": [],
            }

        merged = _merge_config_schema(MyApp)
        assert "output_dir" in merged["properties"]
        assert merged["properties"]["output_dir"]["ui_widget"] == "directory_browser"
        assert "custom_field" in merged["properties"]
        assert "app_command" in merged["properties"]
        # Issue #571: verify forced ordering
        assert merged["properties"]["app_command"]["ui_priority"] == 0
        assert merged["properties"]["app_command"]["ui_widget"] == "file_browser"
        assert merged["properties"]["app_command"]["title"] == "Executable Path"
        assert merged["properties"]["output_dir"]["ui_priority"] == 1

    def test_appblock_subclass_priority_enforcement(self) -> None:
        """AppBlock subclass fields with ui_priority < 2 are bumped to 2."""
        from typing import Any, ClassVar

        from scieasy.blocks.app.app_block import AppBlock
        from scieasy.blocks.registry import _merge_config_schema

        class MyApp(AppBlock):
            app_command: ClassVar[str] = "fiji"

            config_schema: ClassVar[dict[str, Any]] = {
                "type": "object",
                "properties": {
                    "sneaky_field": {"type": "string", "ui_priority": 0},
                    "normal_field": {"type": "string", "ui_priority": 5},
                },
                "required": [],
            }

        merged = _merge_config_schema(MyApp)
        # sneaky_field tried to claim priority 0 but must be bumped to 2
        assert merged["properties"]["sneaky_field"]["ui_priority"] == 2
        # normal_field already >= 2, should be untouched
        assert merged["properties"]["normal_field"]["ui_priority"] == 5
        # reserved fields keep their forced priorities
        assert merged["properties"]["app_command"]["ui_priority"] == 0
        assert merged["properties"]["output_dir"]["ui_priority"] == 1

    def test_subclass_path_override_wins(self) -> None:
        """When a leaf class explicitly declares path, its version wins."""
        from typing import Any, ClassVar

        from scieasy.blocks.base.config import BlockConfig
        from scieasy.blocks.io.io_block import IOBlock
        from scieasy.blocks.registry import _merge_config_schema
        from scieasy.core.types.base import DataObject
        from scieasy.core.types.collection import Collection

        class CustomLoader(IOBlock):
            direction: ClassVar[str] = "input"

            config_schema: ClassVar[dict[str, Any]] = {
                "type": "object",
                "properties": {
                    "path": {
                        "type": ["string", "array"],
                        "items": {"type": "string"},
                        "title": "Custom Path Title",
                        "ui_priority": 0,
                        "ui_widget": "file_browser",
                    },
                },
                "required": ["path"],
            }

            def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
                raise NotImplementedError

            def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
                raise NotImplementedError

        merged = _merge_config_schema(CustomLoader)
        assert merged["properties"]["path"]["title"] == "Custom Path Title"

    def test_output_block_with_own_path_not_overridden(self) -> None:
        """Output IOBlock that declares its own path keeps it as-is."""
        from typing import Any, ClassVar

        from scieasy.blocks.base.config import BlockConfig
        from scieasy.blocks.io.io_block import IOBlock
        from scieasy.blocks.registry import _merge_config_schema
        from scieasy.core.types.base import DataObject
        from scieasy.core.types.collection import Collection

        class CustomSaver(IOBlock):
            direction: ClassVar[str] = "output"

            config_schema: ClassVar[dict[str, Any]] = {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "title": "My Output Path",
                        "ui_widget": "file_browser",
                    },
                },
                "required": ["path"],
            }

            def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
                raise NotImplementedError

            def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
                pass

        merged = _merge_config_schema(CustomSaver)
        # Subclass explicitly declared path, so direction-aware override is skipped.
        assert merged["properties"]["path"]["ui_widget"] == "file_browser"
        assert merged["properties"]["path"]["title"] == "My Output Path"

    def test_required_deduplication(self) -> None:
        """Duplicate required fields across MRO are deduplicated."""
        from typing import Any, ClassVar

        from scieasy.blocks.base.block import Block
        from scieasy.blocks.registry import _merge_config_schema

        class Parent(Block):
            config_schema: ClassVar[dict[str, Any]] = {
                "type": "object",
                "properties": {"x": {"type": "string"}},
                "required": ["x"],
            }

            def run(self, inputs, config):
                return {}

        class Child(Parent):
            config_schema: ClassVar[dict[str, Any]] = {
                "type": "object",
                "properties": {"y": {"type": "string"}},
                "required": ["x", "y"],
            }

        merged = _merge_config_schema(Child)
        assert merged["required"].count("x") == 1
        assert merged["required"].count("y") == 1


class TestAppBlockSubclassConfigCleanup:
    """#572: FijiBlock and ElMAVENBlock must not redeclare AppBlock base fields."""

    def test_fiji_own_config_schema_has_no_watch_timeout(self) -> None:
        """FijiBlock's own config_schema must not include watch_timeout."""
        from scieasy_blocks_imaging.interactive.fiji_block import FijiBlock

        own_schema = FijiBlock.__dict__.get("config_schema", {})
        props = own_schema.get("properties", {})
        assert "watch_timeout" not in props, "watch_timeout should be removed from FijiBlock config_schema"

    def test_fiji_own_config_schema_has_no_app_command(self) -> None:
        """FijiBlock must not redeclare app_command in its own config_schema."""
        from scieasy_blocks_imaging.interactive.fiji_block import FijiBlock

        own_schema = FijiBlock.__dict__.get("config_schema", {})
        props = own_schema.get("properties", {})
        assert "app_command" not in props, "app_command should be inherited from AppBlock, not redeclared"

    def test_fiji_own_config_schema_has_no_output_patterns(self) -> None:
        """FijiBlock must not redeclare output_patterns in its own config_schema."""
        from scieasy_blocks_imaging.interactive.fiji_block import FijiBlock

        own_schema = FijiBlock.__dict__.get("config_schema", {})
        props = own_schema.get("properties", {})
        assert "output_patterns" not in props, "output_patterns should be inherited from AppBlock, not redeclared"

    def test_fiji_mro_merged_includes_app_command(self) -> None:
        """FijiBlock's MRO-merged config_schema includes app_command from AppBlock."""
        from scieasy_blocks_imaging.interactive.fiji_block import FijiBlock

        from scieasy.blocks.registry import _merge_config_schema

        merged = _merge_config_schema(FijiBlock)
        props = merged.get("properties", {})
        assert "app_command" in props, "app_command should be inherited via MRO merge from AppBlock"

    def test_fiji_mro_merged_includes_output_dir(self) -> None:
        """FijiBlock's MRO-merged config_schema includes output_dir from AppBlock."""
        from scieasy_blocks_imaging.interactive.fiji_block import FijiBlock

        from scieasy.blocks.registry import _merge_config_schema

        merged = _merge_config_schema(FijiBlock)
        props = merged.get("properties", {})
        assert "output_dir" in props, "output_dir should be inherited via MRO merge from AppBlock"

    def test_elmaven_own_config_schema_has_no_app_command(self) -> None:
        """ElMAVENBlock must not redeclare app_command in its own config_schema."""
        from scieasy_blocks_lcms.external.elmaven_block import ElMAVENBlock

        own_schema = ElMAVENBlock.__dict__.get("config_schema", {})
        props = own_schema.get("properties", {})
        assert "app_command" not in props, "app_command should be inherited from AppBlock, not redeclared"

    def test_elmaven_own_config_schema_has_no_output_patterns(self) -> None:
        """ElMAVENBlock must not redeclare output_patterns in its own config_schema."""
        from scieasy_blocks_lcms.external.elmaven_block import ElMAVENBlock

        own_schema = ElMAVENBlock.__dict__.get("config_schema", {})
        props = own_schema.get("properties", {})
        assert "output_patterns" not in props, "output_patterns should be inherited from AppBlock, not redeclared"

    def test_elmaven_mro_merged_includes_app_command(self) -> None:
        """ElMAVENBlock's MRO-merged config_schema includes app_command from AppBlock."""
        from scieasy_blocks_lcms.external.elmaven_block import ElMAVENBlock

        from scieasy.blocks.registry import _merge_config_schema

        merged = _merge_config_schema(ElMAVENBlock)
        props = merged.get("properties", {})
        assert "app_command" in props, "app_command should be inherited via MRO merge from AppBlock"


class TestVariadicPortsSpec:
    """ADR-029 D8: _spec_from_class() populates variadic_inputs/outputs on BlockSpec."""

    def test_static_block_spec_has_variadic_false(self) -> None:
        """Non-variadic block yields variadic_inputs=False, variadic_outputs=False."""
        from typing import Any, ClassVar

        from scieasy.blocks.base.block import Block
        from scieasy.blocks.base.config import BlockConfig
        from scieasy.blocks.registry import _spec_from_class

        class _StaticBlock(Block):
            name: ClassVar[str] = "StaticTestBlock"

            def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
                return {}

        spec = _spec_from_class(_StaticBlock)
        assert spec.variadic_inputs is False
        assert spec.variadic_outputs is False

    def test_variadic_block_spec_has_variadic_true(self) -> None:
        """Variadic block yields variadic_inputs=True, variadic_outputs=True."""
        from typing import Any, ClassVar

        from scieasy.blocks.base.block import Block
        from scieasy.blocks.base.config import BlockConfig
        from scieasy.blocks.registry import _spec_from_class

        class _VariadicBlock(Block):
            name: ClassVar[str] = "VariadicTestBlock"
            variadic_inputs: ClassVar[bool] = True
            variadic_outputs: ClassVar[bool] = True

            def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
                return {}

        spec = _spec_from_class(_VariadicBlock)
        assert spec.variadic_inputs is True
        assert spec.variadic_outputs is True

    def test_allowed_types_serialized_as_string_list(self) -> None:
        """allowed_input/output_types ClassVars are serialized to class name strings."""
        from typing import Any, ClassVar

        from scieasy.blocks.base.block import Block
        from scieasy.blocks.base.config import BlockConfig
        from scieasy.blocks.base.ports import InputPort, OutputPort
        from scieasy.blocks.registry import _spec_from_class
        from scieasy.core.types.array import Array
        from scieasy.core.types.dataframe import DataFrame

        class _TypedVariadicBlock(Block):
            name: ClassVar[str] = "TypedVariadicBlock"
            variadic_inputs: ClassVar[bool] = True
            variadic_outputs: ClassVar[bool] = True
            allowed_input_types: ClassVar[list[type]] = [Array, DataFrame]
            allowed_output_types: ClassVar[list[type]] = [Array]
            input_ports: ClassVar[list[InputPort]] = []
            output_ports: ClassVar[list[OutputPort]] = []

            def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
                return {}

        spec = _spec_from_class(_TypedVariadicBlock)
        assert spec.allowed_input_types == ["Array", "DataFrame"]
        assert spec.allowed_output_types == ["Array"]

    def test_empty_allowed_types_yields_empty_list(self) -> None:
        """Block with no allowed_types ClassVar yields empty allowed_input/output_types."""
        from typing import Any, ClassVar

        from scieasy.blocks.base.block import Block
        from scieasy.blocks.base.config import BlockConfig
        from scieasy.blocks.registry import _spec_from_class

        class _DefaultAllowedBlock(Block):
            name: ClassVar[str] = "DefaultAllowedBlock"
            variadic_inputs: ClassVar[bool] = True

            def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
                return {}

        spec = _spec_from_class(_DefaultAllowedBlock)
        assert spec.allowed_input_types == []
        assert spec.allowed_output_types == []


class TestPortCountLimitsSpec:
    """ADR-029 Addendum 1: _spec_from_class() populates min/max port count limits."""

    def test_default_limits_are_none(self) -> None:
        """Block without explicit limits yields None for all 4 fields."""
        from typing import Any, ClassVar

        from scieasy.blocks.base.block import Block
        from scieasy.blocks.base.config import BlockConfig
        from scieasy.blocks.registry import _spec_from_class

        class _NoLimitsBlock(Block):
            name: ClassVar[str] = "NoLimitsBlock"

            def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
                return {}

        spec = _spec_from_class(_NoLimitsBlock)
        assert spec.min_input_ports is None
        assert spec.max_input_ports is None
        assert spec.min_output_ports is None
        assert spec.max_output_ports is None

    def test_explicit_limits_captured(self) -> None:
        """Block with explicit min/max ClassVars yields correct spec values."""
        from typing import Any, ClassVar

        from scieasy.blocks.base.block import Block
        from scieasy.blocks.base.config import BlockConfig
        from scieasy.blocks.registry import _spec_from_class

        class _LimitedBlock(Block):
            name: ClassVar[str] = "LimitedBlock"
            variadic_inputs: ClassVar[bool] = True
            variadic_outputs: ClassVar[bool] = True
            min_input_ports: ClassVar[int | None] = 1
            max_input_ports: ClassVar[int | None] = 5
            min_output_ports: ClassVar[int | None] = 2
            max_output_ports: ClassVar[int | None] = 4

            def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
                return {}

        spec = _spec_from_class(_LimitedBlock)
        assert spec.min_input_ports == 1
        assert spec.max_input_ports == 5
        assert spec.min_output_ports == 2
        assert spec.max_output_ports == 4
