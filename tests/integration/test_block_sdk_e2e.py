"""End-to-end integration tests for Block SDK (issue #218).

Verifies the full Block SDK flow: package metadata, registry discovery,
type registry entry-points, and Tier 1 drop-in block scanning with
instantiation and execution.

T-TRK-004 / ADR-028 §D2: the legacy ``AdapterRegistry`` priority
enforcement test suites were removed alongside the deleted adapter
layer.
"""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scieasy.blocks.base.block import Block
from scieasy.blocks.base.config import BlockConfig
from scieasy.blocks.base.package_info import PackageInfo
from scieasy.blocks.registry import BlockRegistry
from scieasy.core.types.base import DataObject
from scieasy.core.types.registry import TypeRegistry

# ---------------------------------------------------------------------------
# Helpers: mock Block subclass and mock entry-point factories
# ---------------------------------------------------------------------------


def _make_block_class(name: str = "MockBlock", algorithm: str = "mock") -> type:
    """Create a minimal concrete Block subclass for testing."""
    cls = type(
        name,
        (Block,),
        {
            "name": name,
            "description": f"Mock block: {name}",
            "version": "1.0.0",
            "algorithm": algorithm,
            "input_ports": [],
            "output_ports": [],
            "config_schema": {"type": "object", "properties": {}},
            "run": lambda self, inputs, config: {},
        },
    )
    return cls


def _make_entry_point(name: str, load_return: object) -> MagicMock:
    """Create a mock entry-point whose .load() returns *load_return*."""
    ep = MagicMock()
    ep.name = name
    ep.value = f"mock_module:{name}"
    ep.load.return_value = load_return
    return ep


def _make_eps_mock(group_map: dict[str, list[MagicMock]]) -> MagicMock:
    """Create a mock for importlib.metadata.entry_points().

    Supports both .select(group=...) and .get(group, []) patterns.
    """
    mock = MagicMock()

    def select(group: str = "") -> list[MagicMock]:
        return group_map.get(group, [])

    mock.select = select
    mock.get = lambda group, default=None: group_map.get(group, default or [])
    return mock


# ===========================================================================
# Test Suite 1: Registry roundtrip — entry-point -> PackageInfo -> BlockSpec
# ===========================================================================


class TestRegistryEntryPointRoundtrip:
    """Verify _scan_tier2() processes mock entry-points into correct registry state."""

    def test_package_info_propagates_to_block_spec(self) -> None:
        """(PackageInfo, [Block]) return sets package_name on every BlockSpec."""
        info = PackageInfo(
            name="SRS Imaging Toolkit",
            description="SRS spectral imaging blocks",
            author="Wang Lab",
            version="2.0.0",
        )
        block_a = _make_block_class("SRSPreprocess")
        block_b = _make_block_class("SRSClassify")

        def factory():
            return info, [block_a, block_b]

        ep = _make_entry_point("srs-imaging", factory)
        mock_eps = _make_eps_mock({"scieasy.blocks": [ep]})

        reg = BlockRegistry()
        with patch("importlib.metadata.entry_points", return_value=mock_eps):
            reg._scan_tier2()

        # Both blocks should carry the package name.
        spec_a = reg.get_spec("SRSPreprocess")
        spec_b = reg.get_spec("SRSClassify")
        assert spec_a is not None
        assert spec_b is not None
        assert spec_a.package_name == "SRS Imaging Toolkit"
        assert spec_b.package_name == "SRS Imaging Toolkit"
        assert spec_a.source == "entry_point"
        assert spec_b.source == "entry_point"

    def test_package_info_stored_in_packages_dict(self) -> None:
        """PackageInfo returned by entry-point is accessible via packages()."""
        info = PackageInfo(name="Genomics Suite", author="Broad Institute", version="3.1.0")
        block_cls = _make_block_class("GenomicsAlign")

        def factory():
            return info, [block_cls]

        ep = _make_entry_point("genomics", factory)
        mock_eps = _make_eps_mock({"scieasy.blocks": [ep]})

        reg = BlockRegistry()
        with patch("importlib.metadata.entry_points", return_value=mock_eps):
            reg._scan_tier2()

        pkgs = reg.packages()
        assert "Genomics Suite" in pkgs
        assert pkgs["Genomics Suite"].author == "Broad Institute"
        assert pkgs["Genomics Suite"].version == "3.1.0"

    def test_specs_by_package_groups_correctly(self) -> None:
        """specs_by_package() groups blocks by their package_name."""
        info = PackageInfo(name="Pkg-A")
        cls_1 = _make_block_class("Block1")
        cls_2 = _make_block_class("Block2")

        def factory_a():
            return info, [cls_1, cls_2]

        cls_3 = _make_block_class("Block3")

        def factory_b():
            return [cls_3]  # No PackageInfo -- uses ep.name

        ep_a = _make_entry_point("pkg-a", factory_a)
        ep_b = _make_entry_point("standalone", factory_b)
        mock_eps = _make_eps_mock({"scieasy.blocks": [ep_a, ep_b]})

        reg = BlockRegistry()
        with patch("importlib.metadata.entry_points", return_value=mock_eps):
            reg._scan_tier2()

        grouped = reg.specs_by_package()
        assert "Pkg-A" in grouped
        assert len(grouped["Pkg-A"]) == 2
        assert {s.name for s in grouped["Pkg-A"]} == {"Block1", "Block2"}

        assert "standalone" in grouped
        assert len(grouped["standalone"]) == 1
        assert grouped["standalone"][0].name == "Block3"

    def test_plain_list_return_uses_ep_name_as_package(self) -> None:
        """Entry-point returning a plain list assigns ep.name to package_name."""
        cls = _make_block_class("SimpleBlock")

        def factory():
            return [cls]

        ep = _make_entry_point("simple-package", factory)
        mock_eps = _make_eps_mock({"scieasy.blocks": [ep]})

        reg = BlockRegistry()
        with patch("importlib.metadata.entry_points", return_value=mock_eps):
            reg._scan_tier2()

        spec = reg.get_spec("SimpleBlock")
        assert spec is not None
        assert spec.package_name == "simple-package"
        # No PackageInfo stored for plain list returns.
        assert len(reg.packages()) == 0

    def test_multiple_entry_points_coexist(self) -> None:
        """Multiple entry-points populate distinct package groups."""
        info_x = PackageInfo(name="PkgX")
        info_y = PackageInfo(name="PkgY")
        cls_x = _make_block_class("BlockX")
        cls_y = _make_block_class("BlockY")

        ep_x = _make_entry_point("x", lambda: (info_x, [cls_x]))
        ep_y = _make_entry_point("y", lambda: (info_y, [cls_y]))
        mock_eps = _make_eps_mock({"scieasy.blocks": [ep_x, ep_y]})

        reg = BlockRegistry()
        with patch("importlib.metadata.entry_points", return_value=mock_eps):
            reg._scan_tier2()

        assert reg.get_spec("BlockX") is not None
        assert reg.get_spec("BlockY") is not None
        assert reg.get_spec("BlockX").package_name == "PkgX"
        assert reg.get_spec("BlockY").package_name == "PkgY"

        pkgs = reg.packages()
        assert "PkgX" in pkgs
        assert "PkgY" in pkgs


# ===========================================================================
# Test Suite 2: Tier 1 scaffold -> scan -> instantiate -> run
# ===========================================================================


class TestTier1DropInEndToEnd:
    """Scaffold a temp block file, scan it, instantiate, run, verify output."""

    BLOCK_TEMPLATE = """\
from scieasy.blocks.process.process_block import ProcessBlock
from scieasy.blocks.base.config import BlockConfig
from scieasy.blocks.base.ports import InputPort, OutputPort
from scieasy.core.types.base import DataObject
from typing import Any


class {class_name}(ProcessBlock):
    name = "{display_name}"
    description = "{description}"
    version = "0.2.0"
    algorithm = "{algorithm}"
    input_ports = [InputPort(name="input", accepted_types=[DataObject])]
    output_ports = [OutputPort(name="output", accepted_types=[DataObject])]
    config_schema = {{"type": "object", "properties": {{"threshold": {{"type": "number"}}}}}}

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        return {{"output": "processed"}}
"""

    def _write_block_file(self, tmp_path: Path, class_name: str, display_name: str) -> Path:
        """Write a valid block .py file to tmp_path and return the file path."""
        content = self.BLOCK_TEMPLATE.format(
            class_name=class_name,
            display_name=display_name,
            description=f"Test block {display_name}",
            algorithm=class_name.lower(),
        )
        file_path = tmp_path / f"{class_name.lower()}.py"
        file_path.write_text(content, encoding="utf-8")
        return file_path

    def test_scaffold_file_is_valid_python(self, tmp_path: Path) -> None:
        """The generated block file is syntactically valid Python."""
        import ast

        file_path = self._write_block_file(tmp_path, "MyTestBlock", "My Test Block")
        source = file_path.read_text(encoding="utf-8")
        # Should parse without SyntaxError.
        tree = ast.parse(source)
        # Should contain exactly one class definition.
        class_defs = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        assert len(class_defs) == 1
        assert class_defs[0].name == "MyTestBlock"

    def test_scaffold_file_has_run_method(self, tmp_path: Path) -> None:
        """The generated block file contains a run() method."""
        import ast

        file_path = self._write_block_file(tmp_path, "RunCheckBlock", "Run Check")
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        class_def = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef))
        method_names = [n.name for n in ast.walk(class_def) if isinstance(n, ast.FunctionDef)]
        assert "run" in method_names

    def test_tier1_scan_discovers_scaffolded_block(self, tmp_path: Path) -> None:
        """A scaffolded block file is discovered by Tier 1 scan.

        ADR-038 §3.3: ``block_version`` is force-injected at registry
        scan time. Tier-1 drop-in modules have no PyPI distribution so
        they fall back to ``scieasy.__version__`` — the class-level
        ``version`` attribute on the scaffolded block is intentionally
        overridden to remove the historical ``"unknown"`` default and
        keep version provenance honest.
        """
        from scieasy import __version__ as scieasy_version

        self._write_block_file(tmp_path, "DiscoverBlock", "Discover Block")

        reg = BlockRegistry()
        reg.add_scan_dir(tmp_path)
        reg.scan()

        specs = reg.all_specs()
        assert "Discover Block" in specs
        spec = specs["Discover Block"]
        assert spec.source == "tier1"
        assert spec.base_category == "process"
        assert spec.version == scieasy_version

    def test_tier1_instantiate_and_run(self, tmp_path: Path) -> None:
        """A Tier 1 block can be instantiated and executed end-to-end."""
        self._write_block_file(tmp_path, "RunBlock", "Run Block")

        reg = BlockRegistry()
        reg.add_scan_dir(tmp_path)
        reg.scan()

        block = reg.instantiate("Run Block")
        assert block.name == "Run Block"

        # Execute the block.
        result = block.run({}, BlockConfig())
        assert result == {"output": "processed"}

    def test_tier1_block_has_correct_metadata(self, tmp_path: Path) -> None:
        """Tier 1 scan extracts description, ports, config_schema from the class."""
        self._write_block_file(tmp_path, "MetaBlock", "Meta Block")

        reg = BlockRegistry()
        reg.add_scan_dir(tmp_path)
        reg.scan()

        spec = reg.get_spec("Meta Block")
        assert spec is not None
        assert spec.description.startswith("Test block Meta Block")
        assert len(spec.input_ports) == 1
        assert len(spec.output_ports) == 1
        assert "threshold" in spec.config_schema.get("properties", {})

    def test_full_scan_includes_builtins_and_dropin(self, tmp_path: Path) -> None:
        """A full scan() discovers both built-in blocks and drop-in files."""
        self._write_block_file(tmp_path, "DropinBlock", "Dropin Block")

        reg = BlockRegistry()
        reg.add_scan_dir(tmp_path)
        reg.scan()

        specs = reg.all_specs()
        # Core builtins should be present (LoadData/SaveData/AIBlock/SubWorkflow).
        assert "Load" in specs
        assert "Save" in specs
        # Drop-in should also be present.
        assert "Dropin Block" in specs


# ===========================================================================
# Test Suite 3: TypeRegistry entry-point scanning
# T-TRK-004: the previous "Adapter priority enforcement" test suite was
# removed alongside the deleted ``AdapterRegistry`` layer (ADR-028 §D2).
# ===========================================================================


class TestTypeRegistryEntryPoints:
    """Verify TypeRegistry discovers external types from mock entry-points."""

    def _make_custom_type(self, name: str) -> type:
        """Create a DataObject subclass for testing."""
        return type(name, (DataObject,), {"__doc__": f"Custom type: {name}"})

    def test_scan_all_discovers_builtins(self) -> None:
        """scan_all() populates at least the core built-in types.

        ADR-027 D2: domain subclasses (``Image``, ``Spectrum``,
        ``PeakTable``, ...) live in plugin packages now and only appear
        in the registry once their owning plugin is installed. Core
        ``scan_builtins()`` only registers the seven base types.
        """
        reg = TypeRegistry()

        # Mock empty entry-points so _scan_entrypoint_types doesn't hit real packages.
        with patch("importlib.metadata.entry_points", return_value=[]):
            reg.scan_all()

        all_types = reg.all_types()
        assert "DataObject" in all_types
        assert "Array" in all_types
        assert "DataFrame" in all_types
        assert "Series" in all_types
        assert "Text" in all_types
        assert "Artifact" in all_types
        assert "CompositeData" in all_types
        # Image / Spectrum / PeakTable are plugin types and must NOT
        # appear in a core-only registry scan.
        assert "Image" not in all_types
        assert "Spectrum" not in all_types
        assert "PeakTable" not in all_types

    def test_entrypoint_type_appears_in_registry(self) -> None:
        """A custom type returned by an entry-point is registered."""
        custom_data_cls = self._make_custom_type("CustomData")

        def factory():
            return [custom_data_cls]

        ep = MagicMock()
        ep.name = "custom-types"
        ep.load.return_value = factory

        with patch("importlib.metadata.entry_points", return_value=[ep]):
            reg = TypeRegistry()
            reg.scan_builtins()
            reg._scan_entrypoint_types()

        assert "CustomData" in reg.all_types()
        spec = reg.resolve("CustomData")
        assert spec.class_name == "CustomData"
        assert spec.base_type == "DataObject"

    def test_entrypoint_multiple_types(self) -> None:
        """An entry-point can return multiple types at once."""
        type_a_cls = self._make_custom_type("TypeA")
        type_b_cls = self._make_custom_type("TypeB")

        def factory():
            return [type_a_cls, type_b_cls]

        ep = MagicMock()
        ep.name = "multi-types"
        ep.load.return_value = factory

        with patch("importlib.metadata.entry_points", return_value=[ep]):
            reg = TypeRegistry()
            reg.scan_builtins()
            reg._scan_entrypoint_types()

        assert "TypeA" in reg.all_types()
        assert "TypeB" in reg.all_types()

    def test_entrypoint_non_dataobject_skipped(self, caplog: pytest.LogCaptureFixture) -> None:
        """An entry-point returning non-DataObject types logs a warning."""

        class NotADataObject:
            pass

        def factory():
            return [NotADataObject]

        ep = MagicMock()
        ep.name = "bad-types"
        ep.load.return_value = factory

        with (
            patch("importlib.metadata.entry_points", return_value=[ep]),
            caplog.at_level(logging.WARNING),
        ):
            reg = TypeRegistry()
            reg._scan_entrypoint_types()

        assert "not a DataObject subclass" in caplog.text
        assert "NotADataObject" not in reg.all_types()

    def test_entrypoint_load_failure_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        """A failing entry-point .load() logs a warning and continues."""
        ep = MagicMock()
        ep.name = "broken-types"
        ep.load.side_effect = ImportError("no such module")

        with (
            patch("importlib.metadata.entry_points", return_value=[ep]),
            caplog.at_level(logging.WARNING),
        ):
            reg = TypeRegistry()
            reg._scan_entrypoint_types()

        assert "Failed to load entry-point 'broken-types'" in caplog.text

    def test_entrypoint_callable_failure_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        """An entry-point whose callable raises logs a warning and continues."""

        def bad_factory():
            raise RuntimeError("kaboom")

        ep = MagicMock()
        ep.name = "crashing-types"
        ep.load.return_value = bad_factory

        with (
            patch("importlib.metadata.entry_points", return_value=[ep]),
            caplog.at_level(logging.WARNING),
        ):
            reg = TypeRegistry()
            reg._scan_entrypoint_types()

        assert "callable raised an exception" in caplog.text

    def test_load_class_roundtrip(self) -> None:
        """A registered type can be loaded back into its original class."""
        reg = TypeRegistry()
        with patch("importlib.metadata.entry_points", return_value=[]):
            reg.scan_all()

        loaded_cls = reg.load_class("Array")
        from scieasy.core.types.array import Array

        assert loaded_cls is Array

    def test_is_instance_check(self) -> None:
        """is_instance() uses the loaded class for isinstance checking."""
        from scieasy.core.types.array import Array

        reg = TypeRegistry()
        with patch("importlib.metadata.entry_points", return_value=[]):
            reg.scan_all()

        # ADR-027 D2: core no longer ships ``Image``; exercise the
        # registry's inheritance-aware isinstance check against the
        # base ``Array`` type it does register.
        arr = Array(axes=["y", "x"], shape=(1, 1))
        assert reg.is_instance(arr, "Array")
        assert reg.is_instance(arr, "DataObject")
        assert not reg.is_instance(arr, "DataFrame")


# ===========================================================================
# Test Suite 4: Cross-cutting integration — full scan and resolve
# ===========================================================================


class TestFullIntegration:
    """Integration tests combining multiple subsystems."""

    def test_block_registry_full_scan_is_idempotent(self) -> None:
        """Calling scan() twice does not duplicate entries."""
        reg = BlockRegistry()
        reg.scan()
        count_1 = len(reg.all_specs())

        reg.scan()
        count_2 = len(reg.all_specs())

        assert count_1 == count_2

    def test_get_spec_by_type_name_alias(self) -> None:
        """Blocks can be resolved by their type_name alias."""
        reg = BlockRegistry()
        reg.scan()

        # Merge block has type_name "merge_block".
        spec_by_name = reg.get_spec("Merge")
        spec_by_type = reg.get_spec("merge_block")
        assert spec_by_name is not None
        assert spec_by_type is not None
        assert spec_by_name.name == spec_by_type.name

    def test_entry_point_bad_tuple_format_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        """Entry-point returning a tuple with wrong types logs a warning."""

        def bad_factory():
            return ("not_package_info", "not_a_list")

        ep = _make_entry_point("bad-tuple", bad_factory)
        mock_eps = _make_eps_mock({"scieasy.blocks": [ep]})

        reg = BlockRegistry()
        with (
            patch("importlib.metadata.entry_points", return_value=mock_eps),
            caplog.at_level(logging.WARNING),
        ):
            reg._scan_tier2()

        assert "unexpected tuple format" in caplog.text

    def test_entry_point_unsupported_return_type_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        """Entry-point returning an unsupported type logs a warning."""

        def bad_factory():
            return 42

        ep = _make_entry_point("bad-return", bad_factory)
        mock_eps = _make_eps_mock({"scieasy.blocks": [ep]})

        reg = BlockRegistry()
        with (
            patch("importlib.metadata.entry_points", return_value=mock_eps),
            caplog.at_level(logging.WARNING),
        ):
            reg._scan_tier2()

        assert "unsupported type" in caplog.text

    def test_tier1_and_tier2_coexist_in_registry(self, tmp_path: Path) -> None:
        """Tier 1 drop-in blocks and Tier 2 entry-point blocks coexist."""
        # Set up a Tier 1 drop-in block.
        dropin = tmp_path / "custom_dropin.py"
        dropin.write_text(
            "from scieasy.blocks.process.process_block import ProcessBlock\n"
            "from scieasy.blocks.base.config import BlockConfig\n"
            "from typing import Any\n"
            "\n"
            "class DropinInteg(ProcessBlock):\n"
            "    name = 'Dropin Integ'\n"
            "    algorithm = 'dropin'\n"
            "\n"
            "    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:\n"
            "        return {}\n",
            encoding="utf-8",
        )

        # Set up a Tier 2 entry-point block.
        info = PackageInfo(name="IntegPkg")
        cls = _make_block_class("Tier2Integ")

        ep = _make_entry_point("integ-ep", lambda: (info, [cls]))
        mock_eps = _make_eps_mock({"scieasy.blocks": [ep]})

        reg = BlockRegistry()
        reg.add_scan_dir(tmp_path)

        with patch("importlib.metadata.entry_points", return_value=mock_eps):
            reg.scan()

        specs = reg.all_specs()
        # Both tiers discovered.
        assert "Dropin Integ" in specs
        assert specs["Dropin Integ"].source == "tier1"
        assert "Tier2Integ" in specs
        assert specs["Tier2Integ"].source == "entry_point"
        assert specs["Tier2Integ"].package_name == "IntegPkg"

        # Built-ins also present (core builtins: Load, Save, AI, SubWorkflow).
        assert "Load" in specs
