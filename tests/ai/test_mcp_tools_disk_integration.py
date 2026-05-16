"""Disk-state integration tests for MCP path-handling tools (issue #790).

The unit tests in ``test_mcp_tools_workflow.py`` and
``test_mcp_tools_inspection.py`` implicitly run with the backend CWD
pointing at the same ``tmp_path`` as the project root, so the
historical CWD-relative resolution bug never showed up there. These
tests pin the project root explicitly and put the backend CWD
somewhere else.

Post-ADR-040 the MCP tools are FastMCP-decorated async coroutines; we
drive them via ``asyncio.run``.
"""

from __future__ import annotations

import asyncio
import os
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from scieasy.ai.agent.mcp import _context, tools_inspection, tools_workflow
from scieasy.blocks.registry import BlockRegistry
from scieasy.core.types.registry import TypeRegistry


def _run(coro):
    return asyncio.run(coro)


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
        self.workflow_runs[workflow_id] = object()
        return {"workflow_id": workflow_id, "status": "started"}


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    root = (tmp_path / "scieasy_project").resolve()
    root.mkdir()
    return root


@pytest.fixture
def other_cwd(tmp_path: Path) -> Path:
    other = (tmp_path / "elsewhere").resolve()
    other.mkdir()
    return other


@pytest.fixture
def ctx_with_project(project_root: Path) -> Iterator[_StubRuntime]:
    runtime = _StubRuntime(_project_dir=project_root)
    runtime.block_registry.scan()
    runtime.type_registry.scan_builtins()
    _context.set_context(runtime)
    yield runtime
    _context.set_context(None)


_VALID_WF_YAML = """\
workflow:
  id: integration_test
  version: 1.0.0
  nodes:
    - id: b1
      block_type: LoadData
      config:
        params:
          backend: csv
  edges: []
"""


# Case 1+2: relative path resolves against project_dir, not CWD.


def test_write_workflow_relative_path_resolves_against_project_dir(
    ctx_with_project: _StubRuntime,
    project_root: Path,
) -> None:
    result = _run(tools_workflow.write_workflow(path="workflows/main.yaml", yaml=_VALID_WF_YAML))

    expected = (project_root / "workflows" / "main.yaml").resolve()
    assert expected.is_file()
    assert expected.read_text(encoding="utf-8") == _VALID_WF_YAML
    assert Path(result.path).resolve() == expected
    assert Path(result.path).is_absolute()


def test_write_workflow_ignores_backend_cwd(
    ctx_with_project: _StubRuntime,
    project_root: Path,
    other_cwd: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(other_cwd)
    assert Path.cwd().resolve() == other_cwd

    result = _run(tools_workflow.write_workflow(path="workflows/cwd_test.yaml", yaml=_VALID_WF_YAML))

    expected = (project_root / "workflows" / "cwd_test.yaml").resolve()
    assert expected.is_file()
    bogus = (other_cwd / "workflows" / "cwd_test.yaml").resolve()
    assert not bogus.exists()
    assert Path(result.path).resolve() == expected


# Case 3+4: traversal rejection.


def test_write_workflow_absolute_outside_project_raises_permission_error(
    ctx_with_project: _StubRuntime,
    tmp_path: Path,
) -> None:
    outside = (tmp_path / "outside_target.yaml").resolve()
    with pytest.raises(PermissionError, match="resolves outside project root"):
        _run(tools_workflow.write_workflow(path=str(outside), yaml=_VALID_WF_YAML))
    assert not outside.exists()


def test_write_workflow_relative_traversal_escape_raises_permission_error(
    ctx_with_project: _StubRuntime,
    project_root: Path,
) -> None:
    with pytest.raises(PermissionError, match="resolves outside project root"):
        _run(tools_workflow.write_workflow(path="../escape.yaml", yaml=_VALID_WF_YAML))
    bogus = (project_root.parent / "escape.yaml").resolve()
    assert not bogus.exists()


# Case 5: absolute under project_dir is accepted.


def test_write_workflow_absolute_under_project_dir_succeeds(
    ctx_with_project: _StubRuntime,
    project_root: Path,
) -> None:
    target = project_root / "workflows" / "abs.yaml"
    result = _run(tools_workflow.write_workflow(path=str(target), yaml=_VALID_WF_YAML))
    assert target.resolve().is_file()
    assert Path(result.path).resolve() == target.resolve()


# Case 6+7: round-trip.


def test_write_then_get_round_trip(
    ctx_with_project: _StubRuntime,
    project_root: Path,
) -> None:
    _run(tools_workflow.write_workflow(path="workflows/roundtrip.yaml", yaml=_VALID_WF_YAML))
    data = _run(tools_workflow.get_workflow(path="workflows/roundtrip.yaml"))
    payload = data.model_dump()
    assert payload.get("id") == "integration_test"
    expected = (project_root / "workflows" / "roundtrip.yaml").resolve()
    assert Path(payload["path"]).resolve() == expected


def test_write_then_validate_round_trip(ctx_with_project: _StubRuntime) -> None:
    _run(tools_workflow.write_workflow(path="workflows/validate.yaml", yaml=_VALID_WF_YAML))
    result = _run(tools_workflow.validate_workflow(yaml_or_path="workflows/validate.yaml"))
    assert result.valid is True
    assert result.errors == []


# Case 8: write_workflow + run_workflow find the file.


def test_write_then_run_workflow_uses_resolved_stem(
    ctx_with_project: _StubRuntime,
    project_root: Path,
) -> None:
    _run(tools_workflow.write_workflow(path="workflows/run_me.yaml", yaml=_VALID_WF_YAML))
    result = _run(tools_workflow.run_workflow(path="workflows/run_me.yaml"))
    assert result.status == "queued"
    assert result.run_id == "run_me"
    assert "run_me" in ctx_with_project.workflow_runs


# Case 9: update_block_config preserves comments.


_COMMENTED_WF = """\
# Top-level comment preserved by ruamel
workflow:
  id: commented_wf
  # version comment preserved
  version: 1.0.0
  nodes:
    - id: b1
      block_type: LoadData
      config:
        params:
          backend: csv
  edges: []
"""


def test_update_block_config_preserves_comments(
    ctx_with_project: _StubRuntime,
    project_root: Path,
) -> None:
    _run(tools_workflow.write_workflow(path="workflows/commented.yaml", yaml=_COMMENTED_WF))
    out = _run(
        tools_inspection.update_block_config(
            workflow_path="workflows/commented.yaml",
            block_id="b1",
            params={"params": {"backend": "parquet"}},
        )
    )
    target = (project_root / "workflows" / "commented.yaml").resolve()
    text = target.read_text(encoding="utf-8")
    assert "Top-level comment preserved by ruamel" in text
    assert "version comment preserved" in text
    assert "parquet" in text
    assert Path(out.workflow_path).resolve() == target


# Case 10: every write tool returns an absolute path.


def test_write_tools_return_absolute_paths(ctx_with_project: _StubRuntime) -> None:
    w_out = _run(tools_workflow.write_workflow(path="workflows/abs1.yaml", yaml=_VALID_WF_YAML))
    assert Path(w_out.path).is_absolute()

    u_out = _run(
        tools_inspection.update_block_config(
            workflow_path="workflows/abs1.yaml",
            block_id="b1",
            params={"params": {"backend": "json"}},
        )
    )
    assert Path(u_out.workflow_path).is_absolute()

    g_out = _run(tools_workflow.get_workflow(path="workflows/abs1.yaml"))
    assert Path(g_out.path).is_absolute()


# Case 11: concurrent writes serialise via file lock.


def test_concurrent_write_workflow_serialises(
    ctx_with_project: _StubRuntime,
    project_root: Path,
) -> None:
    results: list[Any] = []
    errors: list[BaseException] = []

    def _worker(payload: str) -> None:
        try:
            r = _run(tools_workflow.write_workflow(path="workflows/concurrent.yaml", yaml=payload))
            results.append(r)
        except BaseException as exc:
            errors.append(exc)

    t1 = threading.Thread(target=_worker, args=(_VALID_WF_YAML,))
    t2 = threading.Thread(target=_worker, args=(_VALID_WF_YAML.replace("integration_test", "second"),))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors, f"unexpected errors: {errors}"
    assert len(results) == 2
    expected = (project_root / "workflows" / "concurrent.yaml").resolve()
    assert expected.is_file()
    content = expected.read_text(encoding="utf-8")
    assert "workflow:" in content


# Case 12: tool invocation without an open project raises RuntimeError.


def test_write_workflow_without_open_project_raises_runtime_error(project_root: Path) -> None:
    runtime = _StubRuntime(_project_dir=None)
    _context.set_context(runtime)
    try:
        with pytest.raises(RuntimeError, match="No project is currently open"):
            _run(tools_workflow.write_workflow(path="workflows/x.yaml", yaml=_VALID_WF_YAML))
    finally:
        _context.set_context(None)


def test_resolved_path_uses_realpath_not_string_compare(
    ctx_with_project: _StubRuntime,
    project_root: Path,
) -> None:
    result = _run(tools_workflow.write_workflow(path="workflows/./subdir/../redundant.yaml", yaml=_VALID_WF_YAML))
    expected = (project_root / "workflows" / "redundant.yaml").resolve()
    assert Path(result.path).resolve() == expected
    assert expected.is_file()
    assert os.path.commonpath([str(expected), str(project_root)]) == str(project_root)
