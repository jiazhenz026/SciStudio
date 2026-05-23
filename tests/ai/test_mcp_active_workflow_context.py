"""Tests for the ``get_active_workflow_context`` MCP tool.

ADR-040 Addendum 5 / #1488. The tool returns the workflow id the GUI
editor currently has open, with a best-effort name resolved from the
workflow YAML's ``metadata.title`` / ``metadata.name`` when available.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from scistudio.ai.agent.mcp import _context
from scistudio.ai.agent.mcp.tools_workflow.read import get_active_workflow_context
from scistudio.blocks.registry import BlockRegistry
from scistudio.core.types.registry import TypeRegistry


@dataclass
class _StubContext:
    """Minimal MCPContext stub carrying the new ``active_workflow_id`` field."""

    block_registry: BlockRegistry = field(default_factory=BlockRegistry)
    type_registry: TypeRegistry = field(default_factory=TypeRegistry)
    active_workflow_id: str | None = None
    _project_dir: Path | None = None

    @property
    def project_dir(self) -> Path | None:
        return self._project_dir


@contextlib.contextmanager
def _install_context(ctx: _StubContext):
    _context.set_context(ctx)  # type: ignore[arg-type]
    try:
        yield
    finally:
        _context.set_context(None)


def test_returns_none_envelope_when_no_active_workflow(tmp_path: Path) -> None:
    """No project, no workflow → both fields None, no exception."""
    ctx = _StubContext(active_workflow_id=None, _project_dir=tmp_path)
    with _install_context(ctx):
        result = asyncio.run(get_active_workflow_context())
    assert result.workflow_id is None
    assert result.workflow_name is None


def test_returns_id_with_id_as_name_when_workflow_yaml_missing(tmp_path: Path) -> None:
    """Active id set, workflow YAML missing → fall back to id as name."""
    (tmp_path / "workflows").mkdir()
    ctx = _StubContext(active_workflow_id="ghost-workflow", _project_dir=tmp_path)
    with _install_context(ctx):
        result = asyncio.run(get_active_workflow_context())
    assert result.workflow_id == "ghost-workflow"
    assert result.workflow_name == "ghost-workflow"


def test_resolves_workflow_name_from_metadata_title(tmp_path: Path) -> None:
    """When the YAML carries ``metadata.title``, return it as workflow_name."""
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "calibration.yaml").write_text(
        "id: calibration\nmetadata:\n  title: Microplastic Calibration\nnodes: []\nedges: []\n",
        encoding="utf-8",
    )
    ctx = _StubContext(active_workflow_id="calibration", _project_dir=tmp_path)
    with _install_context(ctx):
        result = asyncio.run(get_active_workflow_context())
    assert result.workflow_id == "calibration"
    assert result.workflow_name == "Microplastic Calibration"


def test_falls_back_to_metadata_name(tmp_path: Path) -> None:
    """``metadata.name`` is honoured when ``metadata.title`` is absent."""
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "calibration.yaml").write_text(
        "id: calibration\nmetadata:\n  name: cal-display-name\nnodes: []\nedges: []\n",
        encoding="utf-8",
    )
    ctx = _StubContext(active_workflow_id="calibration", _project_dir=tmp_path)
    with _install_context(ctx):
        result = asyncio.run(get_active_workflow_context())
    assert result.workflow_name == "cal-display-name"


def test_malformed_yaml_does_not_raise(tmp_path: Path) -> None:
    """A corrupt workflow YAML must NOT bubble up — id still returned."""
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "bad.yaml").write_text("this is: : : not valid yaml\n", encoding="utf-8")
    ctx = _StubContext(active_workflow_id="bad", _project_dir=tmp_path)
    with _install_context(ctx):
        result = asyncio.run(get_active_workflow_context())
    assert result.workflow_id == "bad"
    # Name falls back to the id when YAML parsing fails.
    assert result.workflow_name == "bad"


@pytest.mark.parametrize("blank", ["", None])
def test_blank_or_none_id_returns_none_envelope(tmp_path: Path, blank: str | None) -> None:
    """Empty string id is treated the same as None."""
    ctx = _StubContext(active_workflow_id=blank, _project_dir=tmp_path)
    with _install_context(ctx):
        result = asyncio.run(get_active_workflow_context())
    assert result.workflow_id is None
    assert result.workflow_name is None
