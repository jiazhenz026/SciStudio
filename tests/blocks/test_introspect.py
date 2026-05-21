"""Tests for introspect.py — script interface extraction and port auto-inference.

ADR-029 D7: introspect_script() now includes ``input_ports`` derived from the
``run()`` function's parameter annotations.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scistudio.blocks.code.introspect import (
    _annotation_to_type_name,
    _params_to_port_dicts,
    introspect_script,
)

# ---------------------------------------------------------------------------
# Helper: write a temporary Python script file for introspection tests.
# ---------------------------------------------------------------------------


def _write_script(tmp_path: Path, source: str) -> Path:
    """Write *source* to a temp .py file and return the path."""
    script = tmp_path / "test_script.py"
    script.write_text(source, encoding="utf-8")
    return script


# ---------------------------------------------------------------------------
# _annotation_to_type_name unit tests
# ---------------------------------------------------------------------------


class TestAnnotationToTypeName:
    """_annotation_to_type_name — map ast.dump annotation strings to type names."""

    def test_simple_name_annotation(self) -> None:
        assert _annotation_to_type_name("Name(id='Image')") == "Image"

    def test_dataframe_annotation(self) -> None:
        assert _annotation_to_type_name("Name(id='DataFrame')") == "DataFrame"

    def test_dataobject_annotation(self) -> None:
        assert _annotation_to_type_name("Name(id='DataObject')") == "DataObject"

    def test_none_annotation_falls_back(self) -> None:
        assert _annotation_to_type_name(None) == "DataObject"

    def test_subscript_annotation_falls_back(self) -> None:
        # e.g. Optional[Image] -> "Subscript(...)"
        assert _annotation_to_type_name("Subscript(value=Name(id='Optional'), ...)") == "DataObject"

    def test_attribute_annotation_falls_back(self) -> None:
        assert _annotation_to_type_name("Attribute(value=Name(id='scistudio'), attr='Image')") == "DataObject"

    def test_empty_string_falls_back(self) -> None:
        assert _annotation_to_type_name("") == "DataObject"

    def test_name_with_ctx(self) -> None:
        """ast.dump in Python 3.9+ includes ctx=Load() by default."""
        assert _annotation_to_type_name("Name(id='Array', ctx=Load())") == "Array"


# ---------------------------------------------------------------------------
# _params_to_port_dicts unit tests
# ---------------------------------------------------------------------------


class TestParamsToPortDicts:
    """_params_to_port_dicts — convert extracted params to port dict list."""

    def test_annotated_params(self) -> None:
        params = [
            {"name": "self", "annotation": None, "default": None},
            {"name": "image", "annotation": "Name(id='Image')", "default": None},
            {"name": "table", "annotation": "Name(id='DataFrame')", "default": None},
        ]
        ports = _params_to_port_dicts(params)
        assert len(ports) == 2
        assert ports[0] == {"name": "image", "types": ["Image"]}
        assert ports[1] == {"name": "table", "types": ["DataFrame"]}

    def test_unannotated_params_default_to_dataobject(self) -> None:
        params = [
            {"name": "x", "annotation": None, "default": None},
            {"name": "y", "annotation": None, "default": None},
        ]
        ports = _params_to_port_dicts(params)
        assert len(ports) == 2
        assert ports[0]["types"] == ["DataObject"]
        assert ports[1]["types"] == ["DataObject"]

    def test_self_skipped(self) -> None:
        params = [{"name": "self", "annotation": None, "default": None}]
        ports = _params_to_port_dicts(params)
        assert ports == []

    def test_config_skipped(self) -> None:
        params = [
            {"name": "data", "annotation": "Name(id='DataObject')", "default": None},
            {"name": "config", "annotation": None, "default": None},
        ]
        ports = _params_to_port_dicts(params)
        assert len(ports) == 1
        assert ports[0]["name"] == "data"

    def test_empty_params(self) -> None:
        assert _params_to_port_dicts([]) == []


# ---------------------------------------------------------------------------
# introspect_script integration tests
# ---------------------------------------------------------------------------


class TestIntrospectScriptInputPorts:
    """introspect_script() now includes input_ports derived from run() annotations."""

    def test_annotated_run_produces_input_ports(self, tmp_path: Path) -> None:
        script = _write_script(
            tmp_path,
            "def run(image, table):\n    return {}\n",
        )
        result = introspect_script(script)
        assert result["has_run"] is True
        assert result["input_ports"] == [
            {"name": "image", "types": ["DataObject"]},
            {"name": "table", "types": ["DataObject"]},
        ]

    def test_type_annotated_run_produces_typed_ports(self, tmp_path: Path) -> None:
        script = _write_script(
            tmp_path,
            "from __future__ import annotations\ndef run(image: Image, table: DataFrame):\n    return {}\n",
        )
        result = introspect_script(script)
        assert result["input_ports"] == [
            {"name": "image", "types": ["Image"]},
            {"name": "table", "types": ["DataFrame"]},
        ]

    def test_mixed_annotated_run(self, tmp_path: Path) -> None:
        script = _write_script(
            tmp_path,
            "def run(x: Array, y):\n    return {}\n",
        )
        result = introspect_script(script)
        assert result["input_ports"] == [
            {"name": "x", "types": ["Array"]},
            {"name": "y", "types": ["DataObject"]},
        ]

    def test_no_run_function_produces_empty_ports(self, tmp_path: Path) -> None:
        script = _write_script(tmp_path, "def configure():\n    return {}\n")
        result = introspect_script(script)
        assert result["has_run"] is False
        assert result["input_ports"] == []

    def test_run_with_self_and_config_skipped(self, tmp_path: Path) -> None:
        script = _write_script(
            tmp_path,
            "def run(self, data: DataObject, config):\n    return {}\n",
        )
        result = introspect_script(script)
        assert result["input_ports"] == [{"name": "data", "types": ["DataObject"]}]

    def test_introspect_result_has_input_ports_key(self, tmp_path: Path) -> None:
        """input_ports key must always be present even when run() is absent."""
        script = _write_script(tmp_path, "x = 1\n")
        result = introspect_script(script)
        assert "input_ports" in result

    def test_configure_schema_still_extracted(self, tmp_path: Path) -> None:
        """Existing configure() extraction still works alongside port inference."""
        script = _write_script(
            tmp_path,
            "def run(data: Array):\n    return {}\n\ndef configure():\n    return {'threshold': 0.5}\n",
        )
        result = introspect_script(script)
        assert result["has_configure"] is True
        assert result["configure_schema"] == {"threshold": 0.5}
        assert result["input_ports"] == [{"name": "data", "types": ["Array"]}]

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            introspect_script(tmp_path / "nonexistent.py")
