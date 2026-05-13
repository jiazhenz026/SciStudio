"""Tests for #789 — auto-generated MCP inputSchema from handler signatures."""

from __future__ import annotations

from typing import Literal

from scieasy.ai.agent.mcp._schema import (
    infer_tool_schema,
    validate_call_arguments,
)

# ---------------------------------------------------------------------------
# infer_tool_schema
# ---------------------------------------------------------------------------


def test_required_vs_optional_parameters() -> None:
    def example(a: str, b: int = 5) -> None:
        """Doc.

        Parameters
        ----------
        a
            The required one.
        b
            The optional one.
        """

    schema = infer_tool_schema(example)
    assert schema["type"] == "object"
    assert set(schema["required"]) == {"a"}
    assert schema["properties"]["a"]["type"] == "string"
    assert schema["properties"]["b"]["type"] == "integer"
    assert schema["properties"]["b"].get("default") == 5


def test_optional_type_becomes_nullable() -> None:
    def example(x: str | None = None) -> None:
        pass

    schema = infer_tool_schema(example)
    typ = schema["properties"]["x"]["type"]
    assert "null" in typ
    assert "string" in typ


def test_literal_emits_enum() -> None:
    def example(mode: Literal["a", "b", "c"]) -> None:
        pass

    schema = infer_tool_schema(example)
    prop = schema["properties"]["mode"]
    assert prop["type"] == "string"
    assert prop["enum"] == ["a", "b", "c"]


def test_list_and_dict_types() -> None:
    def example(xs: list[int], meta: dict[str, str]) -> None:
        pass

    schema = infer_tool_schema(example)
    assert schema["properties"]["xs"]["type"] == "array"
    assert schema["properties"]["xs"]["items"]["type"] == "integer"
    assert schema["properties"]["meta"]["type"] == "object"


def test_numpy_docstring_parameters_become_descriptions() -> None:
    def example(path: str) -> None:
        """Top line.

        Parameters
        ----------
        path
            Path to the file.

        Returns
        -------
        None
        """

    schema = infer_tool_schema(example)
    assert schema["properties"]["path"].get("description") == "Path to the file."


def test_real_tool_write_workflow_has_path_and_yaml_required() -> None:
    from scieasy.ai.agent.mcp.tools_workflow import write_workflow

    schema = infer_tool_schema(write_workflow)
    assert "path" in schema["properties"]
    assert "yaml" in schema["properties"]
    assert set(schema["required"]) == {"path", "yaml"}


def test_real_tool_preview_data_has_expected_fields() -> None:
    from scieasy.ai.agent.mcp.tools_inspection import preview_data

    schema = infer_tool_schema(preview_data)
    assert "ref" in schema["properties"]


# ---------------------------------------------------------------------------
# validate_call_arguments
# ---------------------------------------------------------------------------


def test_validate_passes_correct_args() -> None:
    schema = {
        "type": "object",
        "properties": {"a": {"type": "string"}, "b": {"type": "integer"}},
        "required": ["a"],
        "additionalProperties": False,
    }
    assert validate_call_arguments(schema, {"a": "x", "b": 1}) is None


def test_validate_rejects_missing_required() -> None:
    schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }
    err = validate_call_arguments(schema, {})
    assert err is not None
    assert "path" in err


def test_validate_rejects_unknown_keys_when_strict() -> None:
    schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
        "additionalProperties": False,
    }
    err = validate_call_arguments(schema, {"path": "p", "name": "extra"})
    assert err is not None
    assert "name" in err


def test_validate_rejects_wrong_primitive_type() -> None:
    schema = {
        "type": "object",
        "properties": {"n": {"type": "integer"}},
        "required": ["n"],
    }
    err = validate_call_arguments(schema, {"n": "not-an-int"})
    assert err is not None
    assert "n" in err
