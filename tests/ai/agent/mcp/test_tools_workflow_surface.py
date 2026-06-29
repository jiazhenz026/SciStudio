"""Surface-preservation + per-sub-module behavior tests for ``tools_workflow``.

Issue: #1431 (umbrella #1427) — pure structural decomposition of
``scistudio.ai.agent.mcp.tools_workflow`` from a single 884 LOC file
into a sub-package. The legacy import surface MUST be preserved.

These tests are deliberately layered alongside the broader behavior
tests in ``tests/ai/test_mcp_tools_workflow.py`` (kept intact). Their
job is narrower: prove that every public/internal name reachable
before the refactor is still reachable after the refactor, AND
exercise one trivial behavior assertion per new sub-module so the
god-file-decomposition cannot silently lose a sub-module's content.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from scistudio.ai.agent.mcp import _context, tools_workflow
from scistudio.blocks.registry import BlockRegistry
from scistudio.core.types.registry import TypeRegistry

# ---------------------------------------------------------------------------
# Stub MCPContext (same shape used by the legacy test suite).
# ---------------------------------------------------------------------------


@dataclass
class _StubRuntime:
    block_registry: BlockRegistry = field(default_factory=BlockRegistry)
    type_registry: TypeRegistry = field(default_factory=TypeRegistry)
    workflow_runs: dict[str, Any] = field(default_factory=dict)
    _project_dir: Path | None = None

    @property
    def project_dir(self) -> Path | None:
        return self._project_dir

    def start_workflow(self, workflow_id: str) -> dict[str, Any]:
        return {"workflow_id": workflow_id, "status": "started"}


@pytest.fixture
def ctx(tmp_path: Path):
    runtime = _StubRuntime(_project_dir=tmp_path)
    runtime.block_registry.scan()
    runtime.type_registry.scan_builtins()
    _context.set_context(runtime)
    yield runtime
    _context.set_context(None)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Surface preservation
# ---------------------------------------------------------------------------

_EXPECTED_TOOL_NAMES = (
    "list_blocks",
    "get_block_schema",
    "list_types",
    "get_workflow",
    "validate_workflow",
    "write_workflow",
    "run_workflow",
    "cancel_run",
    "get_run_status",
    "finish_ai_block",
)

_EXPECTED_MODEL_NAMES = (
    "BlockSummary",
    "ListBlocksResult",
    "BlockSchemaResult",
    "TypeEntry",
    "ListTypesResult",
    "WorkflowDefinitionEnvelope",
    "ValidateWorkflowResult",
    "WriteWorkflowResult",
    "RunWorkflowResult",
    "CancelRunResult",
    "BlockErrorEntry",
    "GetRunStatusResult",
    "FinishAIBlockOK",
    "FinishAIBlockError",
)

_EXPECTED_INTERNAL_NAMES = (
    "_LOCK_TIMEOUT_SECONDS",
    "_atomic_write_text",
    "_diff_summary",
    "_port_to_dict",
    "_spec_to_dict",
    "_looks_like_inline_yaml",
    "_resolve_ai_block_run_dir",
    "_get_workflow_runtime",
    "_run_block_errors",
    "_ensure_error_subscriber",
    "_collect_run_errors",
    "_TOOL_MODULE_ID",
)


def test_package_exposes_every_legacy_tool_name() -> None:
    """All 10 ``@mcp.tool`` functions remain attribute-addressable on the package."""
    for name in _EXPECTED_TOOL_NAMES:
        assert hasattr(tools_workflow, name), f"missing tool {name!r} after refactor"
        assert callable(getattr(tools_workflow, name)), f"{name!r} is not callable"


def test_package_exposes_every_legacy_pydantic_model() -> None:
    """Every Pydantic envelope from the pre-refactor file is still importable."""
    for name in _EXPECTED_MODEL_NAMES:
        assert hasattr(tools_workflow, name), f"missing model {name!r} after refactor"


def test_package_exposes_internal_helpers_for_test_monkeypatch_compatibility() -> None:
    """Internal names used by external test monkeypatches must be re-exported.

    ``tests/ai/test_finish_ai_block.py`` monkeypatches
    ``tools_workflow._atomic_write_text``; ``tests/ai/test_mcp_fastmcp.py``
    imports ``tools_workflow.FinishAIBlockOK``. Losing any of these
    bindings during decomposition would be a silent surface break.
    """
    for name in _EXPECTED_INTERNAL_NAMES:
        assert hasattr(tools_workflow, name), f"missing internal {name!r} after refactor"


def test_dunder_all_lists_every_expected_name() -> None:
    """``__all__`` is the canonical export list — it must be complete."""
    all_names = set(getattr(tools_workflow, "__all__", ()))
    expected = set(_EXPECTED_TOOL_NAMES) | set(_EXPECTED_MODEL_NAMES) | set(_EXPECTED_INTERNAL_NAMES)
    missing = expected - all_names
    assert not missing, f"__all__ is missing names: {sorted(missing)}"


def test_submodules_are_importable() -> None:
    """Every new sub-module is importable through its dotted path.

    The sub-module ``finish_ai_block`` shares its name with the tool
    function ``finish_ai_block`` that the package re-exports — the
    re-export wins on the package namespace, so the sub-module must
    be resolved through ``importlib``.
    """
    import importlib

    from scistudio.ai.agent.mcp.tools_workflow import _errors, _helpers, _models, read, write  # noqa: F401

    fab_mod = importlib.import_module("scistudio.ai.agent.mcp.tools_workflow.finish_ai_block")
    assert fab_mod.finish_ai_block is tools_workflow.finish_ai_block
    assert read.list_blocks is tools_workflow.list_blocks
    assert write.write_workflow is tools_workflow.write_workflow


def test_no_legacy_single_file_module_path() -> None:
    """The pre-refactor flat module must no longer exist as a .py file."""
    import scistudio.ai.agent.mcp as mcp_pkg

    mcp_dir = Path(mcp_pkg.__file__).parent
    assert not (mcp_dir / "tools_workflow.py").exists(), "legacy single-file module still present"
    assert (mcp_dir / "tools_workflow").is_dir(), "sub-package directory missing"
    assert (mcp_dir / "tools_workflow" / "__init__.py").is_file(), "package __init__ missing"


# ---------------------------------------------------------------------------
# Per-sub-module behavior (one assertion per sub-module)
# ---------------------------------------------------------------------------


def test_read_submodule_list_blocks_returns_envelope(ctx: _StubRuntime) -> None:
    """read.py: ``list_blocks`` returns a ``ListBlocksResult`` of ``BlockSummary``."""
    result = _run(tools_workflow.list_blocks())
    assert isinstance(result, tools_workflow.ListBlocksResult)
    # Registry scan finds something; if empty in a stripped-down test env
    # we still validate the envelope contract on the result type.
    for entry in result.blocks:
        assert isinstance(entry, tools_workflow.BlockSummary)


def test_helpers_submodule_diff_summary_format() -> None:
    """_helpers.py: ``_diff_summary`` returns the expected compact string."""
    summary = tools_workflow._diff_summary("a\nb\nc\n", "a\nb\nc\nd\n")
    assert "+1/-0 lines" in summary
    assert "bytes" in summary


def test_models_submodule_write_workflow_result_next_step_present() -> None:
    """_models.py: write-class envelopes carry the ``next_step`` field per ADR-040 §3.2."""
    result = tools_workflow.WriteWorkflowResult(
        path="/tmp/x.yaml",
        bytes_written=10,
        diff_summary="+0/-0",
    )
    assert result.next_step  # non-empty default
    assert "validate_workflow" in result.next_step


def test_errors_submodule_collect_run_errors_empty_for_unknown_run() -> None:
    """_errors.py: ``_collect_run_errors`` is total — empty list for unknown runs."""
    out = tools_workflow._collect_run_errors("does-not-exist-run-id")
    assert out == []


def test_write_submodule_write_workflow_rejects_invalid_yaml(ctx: _StubRuntime, tmp_path: Path) -> None:
    """write.py: ``write_workflow`` raises ValueError on schema-invalid YAML."""
    ctx._project_dir = tmp_path
    bad = "workflow:\n  id: [unterminated"
    with pytest.raises(ValueError):
        _run(tools_workflow.write_workflow(str(tmp_path / "bad.yaml"), bad))


def test_finish_ai_block_submodule_returns_error_outside_ai_block_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """finish_ai_block.py: returns ``not_in_ai_block_context`` envelope when no run dir.

    Reset the AI block run dir env var so the call cannot accidentally
    succeed from leakage between tests.
    """
    monkeypatch.delenv("SCISTUDIO_AI_BLOCK_RUN_DIR", raising=False)
    _context.set_context(None)
    result = _run(tools_workflow.finish_ai_block({}))
    assert isinstance(result, tools_workflow.FinishAIBlockError)
    assert result.code == "not_in_ai_block_context"
