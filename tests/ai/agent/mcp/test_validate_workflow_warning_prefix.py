"""#1988 — an advisory diagnostic must not tell the agent a workflow is invalid.

``validate_workflow`` returns one list in which a leading ``Warning:`` marks an
advisory, the convention the API layer already applies. The MCP tool computed
``valid=not errors``, so any advisory reported ``valid=False`` — telling the
agent to fix a workflow that run start would dispatch. That became reachable
when #1988 widened the unregistered-block-type report to nodes with no edges.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from scistudio.ai.agent.mcp import _context, tools_workflow
from scistudio.blocks.registry import BlockRegistry
from scistudio.core.types.registry import TypeRegistry


@dataclass
class _StubRuntime:
    """The slice of the MCP context these two tools actually read."""

    block_registry: BlockRegistry = field(default_factory=BlockRegistry)
    type_registry: TypeRegistry = field(default_factory=TypeRegistry)
    workflow_runs: dict[str, Any] = field(default_factory=dict)
    active_workflow_id: str | None = None
    _project_dir: Path | None = None

    @property
    def project_dir(self) -> Path | None:
        return self._project_dir


@pytest.fixture
def ctx(tmp_path: Path) -> Iterator[_StubRuntime]:
    runtime = _StubRuntime(_project_dir=tmp_path)
    runtime.block_registry.scan()
    runtime.type_registry.scan_builtins()
    _context.set_context(runtime)
    yield runtime
    _context.set_context(None)


def _run(coro: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.new_event_loop().run_until_complete(coro)


_UNRESOLVED_ONLY = """
workflow:
  name: unresolved-only
  nodes:
    - id: orphan
      block_type: srs_baseline_block
  edges: []
"""

_WITH_A_HARD_ERROR = """
workflow:
  name: duplicate-ids
  nodes:
    - id: dup
      block_type: srs_baseline_block
    - id: dup
      block_type: srs_baseline_block
  edges: []
"""


def test_an_unresolved_node_reports_valid_with_the_warning_returned(ctx: _StubRuntime) -> None:
    result = _run(tools_workflow.validate_workflow(_UNRESOLVED_ONLY))

    assert result.valid is True, result.errors
    assert any("srs_baseline_block" in d for d in result.errors)
    assert all(d.startswith("Warning:") for d in result.errors), result.errors


def test_a_hard_error_still_reports_invalid(ctx: _StubRuntime) -> None:
    result = _run(tools_workflow.validate_workflow(_WITH_A_HARD_ERROR))

    assert result.valid is False
    assert any("Duplicate node id" in d for d in result.errors), result.errors
