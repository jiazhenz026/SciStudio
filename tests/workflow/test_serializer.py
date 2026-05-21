"""Tests for workflow YAML serializer -- load_yaml / save_yaml round-trips and error handling."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from scistudio.workflow.definition import EdgeDef, NodeDef, WorkflowDefinition
from scistudio.workflow.serializer import load_yaml, save_yaml


class TestRoundTrip:
    """Round-trip serialization tests."""

    def test_round_trip_simple(self, tmp_path: Path) -> None:
        """Two nodes and one edge survive a save/load round-trip."""
        wf = WorkflowDefinition(
            id="test-wf",
            version="1.0.0",
            description="A simple workflow",
            nodes=[
                NodeDef(id="a", block_type="IOBlock", config={"direction": "input"}),
                NodeDef(id="b", block_type="ProcessBlock", config={"algorithm": "merge"}),
            ],
            edges=[EdgeDef(source="a:output_0", target="b:input_0")],
        )
        path = tmp_path / "wf.yaml"
        save_yaml(wf, path)
        loaded = load_yaml(path)

        assert loaded.id == wf.id
        assert loaded.version == wf.version
        assert loaded.description == wf.description
        assert len(loaded.nodes) == 2
        assert len(loaded.edges) == 1
        assert loaded.nodes[0].id == "a"
        assert loaded.nodes[0].block_type == "IOBlock"
        assert loaded.nodes[0].config == {"direction": "input"}
        assert loaded.nodes[1].id == "b"
        assert loaded.edges[0].source == "a:output_0"
        assert loaded.edges[0].target == "b:input_0"

    def test_round_trip_with_layout(self, tmp_path: Path) -> None:
        """Layout dict {x, y} is preserved through round-trip."""
        wf = WorkflowDefinition(
            id="layout-wf",
            nodes=[
                NodeDef(id="n1", block_type="IOBlock", layout={"x": 100.0, "y": 200.0}),
            ],
        )
        path = tmp_path / "wf.yaml"
        save_yaml(wf, path)
        loaded = load_yaml(path)

        assert loaded.nodes[0].layout == {"x": 100.0, "y": 200.0}

    def test_round_trip_without_layout(self, tmp_path: Path) -> None:
        """When layout is None, it stays None after round-trip."""
        wf = WorkflowDefinition(
            id="no-layout",
            nodes=[NodeDef(id="n1", block_type="IOBlock")],
        )
        path = tmp_path / "wf.yaml"
        save_yaml(wf, path)
        loaded = load_yaml(path)

        assert loaded.nodes[0].layout is None

    def test_round_trip_with_metadata(self, tmp_path: Path) -> None:
        """Workflow-level metadata dict is preserved through round-trip."""
        wf = WorkflowDefinition(
            id="meta-wf",
            metadata={"author": "test", "tags": ["bio", "ms"]},
        )
        path = tmp_path / "wf.yaml"
        save_yaml(wf, path)
        loaded = load_yaml(path)

        assert loaded.metadata == {"author": "test", "tags": ["bio", "ms"]}

    def test_empty_workflow_round_trip(self, tmp_path: Path) -> None:
        """An empty workflow (no nodes, no edges) round-trips correctly."""
        wf = WorkflowDefinition(id="empty")
        path = tmp_path / "wf.yaml"
        save_yaml(wf, path)
        loaded = load_yaml(path)

        assert loaded.id == "empty"
        assert loaded.nodes == []
        assert loaded.edges == []
        assert loaded.metadata == {}


class TestLoadErrors:
    """Error-handling tests for load_yaml."""

    def test_load_invalid_yaml_syntax(self, tmp_path: Path) -> None:
        """Malformed YAML raises yaml.YAMLError."""
        bad = tmp_path / "bad.yaml"
        bad.write_text("workflow:\n  nodes:\n    - id: [unterminated", encoding="utf-8")
        with pytest.raises(yaml.YAMLError):
            load_yaml(bad)

    def test_load_missing_file(self, tmp_path: Path) -> None:
        """Non-existent path raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_yaml(tmp_path / "does_not_exist.yaml")

    def test_load_invalid_schema(self, tmp_path: Path) -> None:
        """Valid YAML but wrong structure raises pydantic ValidationError."""
        bad = tmp_path / "bad_schema.yaml"
        bad.write_text("not_workflow:\n  key: value\n", encoding="utf-8")
        with pytest.raises(ValidationError):
            load_yaml(bad)

    def test_load_invalid_edge_format(self, tmp_path: Path) -> None:
        """Edge source missing colon separator raises ValidationError."""
        bad = tmp_path / "bad_edge.yaml"
        content = {
            "workflow": {
                "id": "test",
                "nodes": [
                    {"id": "a", "block_type": "IOBlock"},
                    {"id": "b", "block_type": "ProcessBlock"},
                ],
                "edges": [{"source": "no_colon", "target": "b:input_0"}],
            }
        }
        bad.write_text(yaml.safe_dump(content), encoding="utf-8")
        with pytest.raises(ValidationError, match="node_id:port_name"):
            load_yaml(bad)


class TestSaveCreatesParentDirs:
    """Regression tests for #467 — save_yaml must create parent dirs."""

    def test_save_creates_missing_parent_dirs(self, tmp_path: Path) -> None:
        """save_yaml creates intermediate directories that do not exist."""
        wf = WorkflowDefinition(id="nested-wf")
        nested = tmp_path / "a" / "b" / "c" / "wf.yaml"
        # Parent dirs do not exist yet
        assert not nested.parent.exists()
        save_yaml(wf, nested)
        assert nested.exists()
        loaded = load_yaml(nested)
        assert loaded.id == "nested-wf"

    def test_save_works_when_parent_already_exists(self, tmp_path: Path) -> None:
        """save_yaml still works when the parent directory already exists."""
        wf = WorkflowDefinition(id="existing-parent")
        path = tmp_path / "wf.yaml"
        save_yaml(wf, path)
        assert path.exists()


class TestSaveOutput:
    """Tests for the YAML output content."""

    def test_save_excludes_none_layout(self, tmp_path: Path) -> None:
        """When layout is None, the YAML output does not contain 'layout: null'."""
        wf = WorkflowDefinition(
            id="no-null",
            nodes=[NodeDef(id="n1", block_type="IOBlock")],
        )
        path = tmp_path / "wf.yaml"
        save_yaml(wf, path)
        text = path.read_text(encoding="utf-8")

        assert "layout" not in text
