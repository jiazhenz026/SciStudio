"""Surface-preservation + per-sub-module behavior tests for ``tools_inspection``.

Issue: #1431 (umbrella #1427) — pure structural decomposition of
``scistudio.ai.agent.mcp.tools_inspection`` from a single 809 LOC file
into a sub-package. The legacy import surface MUST be preserved.

Layered alongside the broader behavior tests in
``tests/ai/test_mcp_tools_inspection.py`` (kept intact). The job here
is narrower: prove every public/internal name reachable before the
refactor stays reachable, AND exercise one trivial behavior assertion
per new sub-module.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from scistudio.ai.agent.mcp import _context, tools_inspection

# ---------------------------------------------------------------------------
# Stub MCPContext.
# ---------------------------------------------------------------------------


@dataclass
class _StubRuntime:
    workflow_runs: dict[str, Any] = field(default_factory=dict)
    _project_dir: Path | None = None

    @property
    def project_dir(self) -> Path | None:
        return self._project_dir


@pytest.fixture
def ctx(tmp_path: Path):
    runtime = _StubRuntime(_project_dir=tmp_path)
    _context.set_context(runtime)
    yield runtime
    _context.set_context(None)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Surface preservation
# ---------------------------------------------------------------------------

_EXPECTED_TOOL_NAMES = (
    "get_block_output",
    "inspect_data",
    "preview_data",
    "get_lineage",
    "get_block_config",
    "update_block_config",
    "get_block_logs",
)

_EXPECTED_MODEL_NAMES = (
    "TypeChainInfo",
    "GetBlockOutputResult",
    "InspectDataResult",
    "PreviewDataResult",
    "LineageNode",
    "LineageEdge",
    "GetLineageResult",
    "GetBlockConfigResult",
    "UpdateBlockConfigResult",
    "GetBlockLogsResult",
)

_EXPECTED_INTERNAL_NAMES = (
    "_LOCK_TIMEOUT_SECONDS",
    "_MAX_PREVIEW_BYTES",
    "_THUMBNAIL_MAX_DIM",
    "_DATAFRAME_PREVIEW_ROWS",
    "_SERIES_PREVIEW_POINTS",
    "_TEXT_PREVIEW_CHARS",
    "_BLOCK_LOG_TRUNCATE_BYTES",
    "_ref_from_dict",
    "_grayscale_png",
    "_preview_dataframe",
    "_preview_array",
    "_preview_series",
    "_preview_text",
    "_preview_artifact",
)


def test_package_exposes_every_legacy_tool_name() -> None:
    """All 7 ``@mcp.tool`` functions remain attribute-addressable on the package."""
    for name in _EXPECTED_TOOL_NAMES:
        assert hasattr(tools_inspection, name), f"missing tool {name!r} after refactor"
        assert callable(getattr(tools_inspection, name)), f"{name!r} is not callable"


def test_package_exposes_every_legacy_pydantic_model() -> None:
    """Every Pydantic envelope from the pre-refactor file is still importable."""
    for name in _EXPECTED_MODEL_NAMES:
        assert hasattr(tools_inspection, name), f"missing model {name!r} after refactor"


def test_package_exposes_internal_helpers_for_test_monkeypatch_compatibility() -> None:
    """Internal names used by external tests must be re-exported.

    ``tests/ai/test_mcp_fastmcp.py`` imports
    ``tools_inspection._preview_dataframe`` and reads
    ``tools_inspection._DATAFRAME_PREVIEW_ROWS``;
    ``tests/ai/test_mcp_tools_inspection.py`` monkeypatches
    ``tools_inspection._MAX_PREVIEW_BYTES``. Losing any of these
    bindings during decomposition would be a silent surface break.
    """
    for name in _EXPECTED_INTERNAL_NAMES:
        assert hasattr(tools_inspection, name), f"missing internal {name!r} after refactor"


def test_dunder_all_lists_every_expected_name() -> None:
    """``__all__`` is the canonical export list — it must be complete."""
    all_names = set(getattr(tools_inspection, "__all__", ()))
    expected = set(_EXPECTED_TOOL_NAMES) | set(_EXPECTED_MODEL_NAMES) | set(_EXPECTED_INTERNAL_NAMES)
    missing = expected - all_names
    assert not missing, f"__all__ is missing names: {sorted(missing)}"


def test_submodules_are_importable() -> None:
    """Every new sub-module is importable through its dotted path."""
    from scistudio.ai.agent.mcp.tools_inspection import (  # noqa: F401
        _helpers,
        _models,
        _preview,
        read,
        write,
    )

    assert read.preview_data is tools_inspection.preview_data
    assert write.update_block_config is tools_inspection.update_block_config


def test_no_legacy_single_file_module_path() -> None:
    """The pre-refactor flat module must no longer exist as a .py file."""
    import scistudio.ai.agent.mcp as mcp_pkg

    mcp_dir = Path(mcp_pkg.__file__).parent
    assert not (mcp_dir / "tools_inspection.py").exists(), "legacy single-file module still present"
    assert (mcp_dir / "tools_inspection").is_dir(), "sub-package directory missing"
    assert (mcp_dir / "tools_inspection" / "__init__.py").is_file(), "package __init__ missing"


# ---------------------------------------------------------------------------
# Per-sub-module behavior (one assertion per sub-module)
# ---------------------------------------------------------------------------


def test_helpers_submodule_ref_from_dict_normalises_fields() -> None:
    """_helpers.py: ``_ref_from_dict`` builds a StorageReference with defaults."""
    sref = tools_inspection._ref_from_dict({"backend": "filesystem", "path": "/tmp/x"})
    assert sref.backend == "filesystem"
    assert sref.path == "/tmp/x"
    # Default backend when missing.
    sref2 = tools_inspection._ref_from_dict({"path": "/tmp/y"})
    assert sref2.backend == "filesystem"


def test_models_submodule_update_block_config_carries_next_step() -> None:
    """_models.py: write-class envelopes carry ``next_step`` per ADR-040 §3.2."""
    result = tools_inspection.UpdateBlockConfigResult(
        block_id="b1",
        diff_summary="0 bytes (was 0)",
        bytes_written=0,
        workflow_path="/tmp/wf.yaml",
    )
    assert result.next_step
    assert "validate_workflow" in result.next_step


def test_preview_submodule_text_returns_text_envelope(tmp_path: Path) -> None:
    """_preview.py: ``_preview_text`` returns ``{fmt:'text', payload:{content:...}}``."""
    target = tmp_path / "note.txt"
    target.write_text("hello world", encoding="utf-8")
    out = tools_inspection._preview_text(target)
    assert out["fmt"] == "text"
    assert out["payload"]["content"] == "hello world"
    assert out["truncated"] is False


def test_read_submodule_get_block_output_raises_on_unknown_run(ctx: _StubRuntime) -> None:
    """read.py: ``get_block_output`` raises KeyError when the run id is unknown."""
    with pytest.raises(KeyError):
        _run(tools_inspection.get_block_output("missing-run", "b1", "out"))


def test_write_submodule_update_block_config_raises_on_missing_file(ctx: _StubRuntime, tmp_path: Path) -> None:
    """write.py: ``update_block_config`` raises FileNotFoundError on missing workflow."""
    with pytest.raises(FileNotFoundError):
        _run(tools_inspection.update_block_config(str(tmp_path / "missing.yaml"), "b1", {}))


def test_max_preview_bytes_monkeypatch_propagates_through_helpers(
    ctx: _StubRuntime, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Critical surface contract: monkeypatching the cap propagates into the
    preview helpers (which live in ``_preview``).

    Pre-refactor, the cap lived in the same module as the helpers and a
    straight ``monkeypatch.setattr(tools_inspection, ...)`` worked. After the
    decomposition the helpers look up the cap on the ``_helpers`` leaf at call
    time (round-4 no-cycles: reading it from the package would re-introduce a
    ``_preview -> tools_inspection`` child -> parent cycle edge). This test
    pins that contract.
    """
    # Use a tiny PNG so the preview path itself succeeds while we verify the
    # cap-lookup goes through the ``_helpers`` leaf binding.
    monkeypatch.setattr(tools_inspection._helpers, "_MAX_PREVIEW_BYTES", 4)

    from scistudio.ai.agent.mcp.tools_inspection._preview import _max_preview_bytes

    assert _max_preview_bytes() == 4
