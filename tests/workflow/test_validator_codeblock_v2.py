from __future__ import annotations

from pathlib import Path

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
