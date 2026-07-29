from __future__ import annotations

from pathlib import Path

import pytest

from scistudio.blocks.code.code_block import CodeBlock
from scistudio.blocks.registry import BlockRegistry, _spec_from_class
from scistudio.workflow.definition import EdgeDef, NodeDef, WorkflowDefinition
from scistudio.workflow.validator import validate_workflow


class _CodeBlockValidationRegistry(BlockRegistry):
    def __init__(self) -> None:
        super().__init__()
        spec = _spec_from_class(CodeBlock, source="test")
        spec.module_path = CodeBlock.__module__
        spec.class_name = CodeBlock.__name__
        self._registry[spec.name] = spec
        self._aliases[spec.type_name] = spec.name

    def find_saver_capability(
        self,
        *,
        data_type: type,
        extension: str,
        capability_id: str | None = None,
    ) -> object:
        return object()

    def find_loader_capability(
        self,
        *,
        data_type: type,
        extension: str,
        capability_id: str | None = None,
    ) -> object:
        return object()


def _script(project_dir: Path, name: str = "script.py") -> None:
    path = project_dir / "scripts" / name
    path.parent.mkdir()
    path.write_text("print('ok')\n", encoding="utf-8")


def _node_config(project_dir: Path, script_path: str, **params: object) -> dict[str, object]:
    config: dict[str, object] = {
        "params": {
            "project_dir": str(project_dir),
            "script_path": script_path,
            "inputs": [
                {
                    "name": "prompt",
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
    }
    config["params"].update(params)  # type: ignore[union-attr]
    return config


def test_validate_workflow_accepts_valid_codeblock_v2_config(tmp_path: Path) -> None:
    _script(tmp_path)
    registry = _CodeBlockValidationRegistry()
    workflow = WorkflowDefinition(
        nodes=[NodeDef(id="code1", block_type="code_block", config=_node_config(tmp_path, "scripts/script.py"))],
    )

    errors = validate_workflow(workflow, registry=registry)

    assert errors == []


def test_validate_workflow_reports_node_scoped_codeblock_diagnostics(tmp_path: Path) -> None:
    _script(tmp_path, "script.zzz")
    registry = _CodeBlockValidationRegistry()
    workflow = WorkflowDefinition(
        nodes=[
            NodeDef(
                id="code1",
                block_type="code_block",
                config=_node_config(
                    tmp_path,
                    "scripts/script.zzz",
                    outputs=[{"name": "summary", "direction": "output", "data_type": "Image", "extension": ".txt"}],
                ),
            )
        ],
    )

    errors = validate_workflow(workflow, registry=registry)

    assert any("Node 'code1': CodeBlock script_path" in error and ".zzz" in error for error in errors)
    assert any("Node 'code1': CodeBlock port 'summary' data_type" in error for error in errors)


def test_draft_mode_skips_codeblock_config_diagnostics(tmp_path: Path) -> None:
    """bug#3: editor autosave (draft mode) must not surface CodeBlock config
    diagnostics for a not-yet-configured block. Strict mode (run start) still
    reports them so an incomplete graph cannot execute."""
    _script(tmp_path, "script.zzz")
    registry = _CodeBlockValidationRegistry()
    workflow = WorkflowDefinition(
        nodes=[
            NodeDef(
                id="code1",
                block_type="code_block",
                config=_node_config(
                    tmp_path,
                    "scripts/script.zzz",
                    outputs=[{"name": "summary", "direction": "output", "data_type": "Image", "extension": ".txt"}],
                ),
            )
        ],
    )

    strict = validate_workflow(workflow, registry=registry)
    draft = validate_workflow(workflow, registry=registry, mode="draft")

    assert any("CodeBlock script_path" in error for error in strict)
    assert not any("CodeBlock" in error for error in draft)


def test_validate_workflow_reports_legacy_inline_migration(tmp_path: Path) -> None:
    registry = _CodeBlockValidationRegistry()
    workflow = WorkflowDefinition(
        nodes=[
            NodeDef(
                id="legacy",
                block_type="code_block",
                config={"params": {"project_dir": str(tmp_path), "mode": "inline", "code": "result = 1"}},
            )
        ],
    )

    errors = validate_workflow(workflow, registry=registry)

    assert any("Node 'legacy': CodeBlock migration" in error for error in errors)
    assert any("Inline CodeBlock configs are not valid" in error for error in errors)


def test_validate_workflow_preserves_unknown_block_warning() -> None:
    workflow = WorkflowDefinition(
        nodes=[
            NodeDef(id="source", block_type="not_registered_source"),
            NodeDef(id="target", block_type="not_registered_target"),
        ],
        edges=[EdgeDef(source="source:out", target="target:in")],
    )

    errors = validate_workflow(workflow, registry=BlockRegistry())

    assert any("Warning: block type 'not_registered_source' not in registry" in error for error in errors)
    assert not any("CodeBlock" in error for error in errors)


def _persisted_node_config(script_path: str) -> dict[str, object]:
    """A node config in its persisted shape: no runtime-injected ``project_dir``.

    The scheduler injects ``project_dir`` at dispatch, so the graph the
    validator sees at run start never carries one (#1967).
    """

    return {
        "script_path": script_path,
        "inputs": [],
        "outputs": [],
    }


def test_validate_workflow_resolves_script_path_against_caller_project_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#1967: a project-relative ``script_path`` validates when the caller
    supplies the project root, even though the process working directory is
    somewhere else entirely (the app's ``Resources`` directory in the packaged
    desktop build)."""

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _script(project_dir)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    registry = _CodeBlockValidationRegistry()
    workflow = WorkflowDefinition(
        nodes=[
            NodeDef(
                id="code1",
                block_type="code_block",
                config=_persisted_node_config("scripts/script.py"),
            )
        ],
    )

    assert validate_workflow(workflow, registry=registry, project_dir=str(project_dir)) == []


def test_validate_workflow_script_path_falls_back_to_cwd_without_project_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without a caller-supplied project root the validator still falls back to
    the working directory — the documented last resort for callers with no
    project context, and the #1967 failure mode when the API forgot to pass one."""

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    _script(project_dir)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    registry = _CodeBlockValidationRegistry()
    workflow = WorkflowDefinition(
        nodes=[
            NodeDef(
                id="code1",
                block_type="code_block",
                config=_persisted_node_config("scripts/script.py"),
            )
        ],
    )

    errors = validate_workflow(workflow, registry=registry)

    assert any("CodeBlock script_path" in error for error in errors)


def test_validate_workflow_node_project_dir_outranks_caller_project_dir(tmp_path: Path) -> None:
    """Node-level ``project_dir`` still wins: a flattened subworkflow node may
    carry its own root that differs from the parent's."""

    node_project = tmp_path / "node-project"
    node_project.mkdir()
    _script(node_project)
    caller_project = tmp_path / "caller-project"
    caller_project.mkdir()

    registry = _CodeBlockValidationRegistry()
    workflow = WorkflowDefinition(
        nodes=[
            NodeDef(
                id="code1",
                block_type="code_block",
                config=_node_config(node_project, "scripts/script.py"),
            )
        ],
    )

    assert validate_workflow(workflow, registry=registry, project_dir=str(caller_project)) == []
