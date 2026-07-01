"""Disk-state integration tests for MCP path-handling tools (issue #790).

Restored from module-skip as part of #1539: the S40a skeleton has been
replaced by a fully implemented FastMCP async server (ADR-040 §3.1,
I40a Phase 2a). The original sync invocation pattern is rewritten here to
use ``asyncio.run()`` directly against the async-decorated callables.

The unit tests in ``test_mcp_tools_workflow.py`` and
``test_mcp_tools_inspection.py`` exercise tool happy/error paths but
implicitly run with the backend CWD pointing at the same ``tmp_path``
that is also the project root, so the historical CWD-relative
resolution bug never showed up. These tests pin the project root
explicitly and put the backend CWD somewhere else, so a regression in
:func:`_resolve_project_path` would surface as a wrong-location write.

Cross-platform notes (macOS):

* ``tmp_path`` on macOS lands under ``/private/var/folders/...`` but
  raw string-compare against ``/var/folders/...`` would treat them as
  different paths. All assertions therefore call :meth:`Path.resolve`
  on **both** sides of equality. ``os.path.realpath`` is what the
  helpers use internally; this keeps the test mirror-image.
* macOS HFS+/APFS are case-insensitive by default but case-preserving.
  ``Path.resolve`` preserves the canonical case, so equality is
  well-defined.
"""

from __future__ import annotations

import asyncio
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from scistudio.ai.agent.mcp import _context, tools_inspection, tools_workflow
from scistudio.blocks.registry import BlockRegistry
from scistudio.core.types.registry import TypeRegistry


def _run(coro):
    """Run a coroutine synchronously (mirrors test_mcp_fastmcp.py helper)."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Test scaffolding.
# ---------------------------------------------------------------------------


@dataclass
class _StubRuntime:
    """Minimal MCPContext stub with a pinned project_dir."""

    block_registry: BlockRegistry = field(default_factory=BlockRegistry)
    type_registry: TypeRegistry = field(default_factory=TypeRegistry)
    workflow_runs: dict[str, Any] = field(default_factory=dict)
    _project_dir: Path | None = None

    @property
    def project_dir(self) -> Path | None:
        return self._project_dir

    def start_workflow(self, workflow_id: str) -> dict[str, Any]:
        # Stub: record the call and return a queued envelope.
        self.workflow_runs[workflow_id] = object()
        return {"workflow_id": workflow_id, "status": "started"}


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """Project workspace root; resolved up-front for macOS symlink safety."""
    root = (tmp_path / "scistudio_project").resolve()
    root.mkdir()
    return root


@pytest.fixture
def other_cwd(tmp_path: Path) -> Path:
    """A *different* directory we'll force the backend CWD into."""
    other = (tmp_path / "elsewhere").resolve()
    other.mkdir()
    return other


@pytest.fixture
def ctx_with_project(project_root: Path, monkeypatch: pytest.MonkeyPatch) -> _StubRuntime:
    """Install a runtime stub whose project_dir is *project_root*."""
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
      block_type: load_data
      config:
        params:
          backend: csv
  edges: []
"""


# ---------------------------------------------------------------------------
# Case 1+2: relative path resolves against project_dir, not CWD.
# ---------------------------------------------------------------------------


def test_write_workflow_relative_path_resolves_against_project_dir(
    ctx_with_project: _StubRuntime,
    project_root: Path,
) -> None:
    """A relative path lands under project_dir, not under os.getcwd()."""
    result = _run(
        tools_workflow.write_workflow(
            path="workflows/main.yaml",
            yaml=_VALID_WF_YAML,
        )
    )

    expected = (project_root / "workflows" / "main.yaml").resolve()
    # The file is on disk at the resolved location.
    assert expected.is_file(), f"file not found at {expected}; got result {result}"
    assert expected.read_text(encoding="utf-8") == _VALID_WF_YAML
    # The response envelope returns the absolute resolved path, not the
    # user-supplied relative one. result is a WriteWorkflowResult Pydantic model.
    assert Path(result.path).resolve() == expected
    assert Path(result.path).is_absolute()


def test_write_workflow_ignores_backend_cwd(
    ctx_with_project: _StubRuntime,
    project_root: Path,
    other_cwd: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """File lands in project_dir even when backend CWD differs.

    This is the regression test for the original #790 symptom: the
    backend was running with a CWD other than the project root, the
    user-supplied path was relative, and the file ended up in the
    wrong place.
    """
    monkeypatch.chdir(other_cwd)
    assert Path.cwd().resolve() == other_cwd  # sanity

    result = _run(
        tools_workflow.write_workflow(
            path="workflows/cwd_test.yaml",
            yaml=_VALID_WF_YAML,
        )
    )

    expected = (project_root / "workflows" / "cwd_test.yaml").resolve()
    assert expected.is_file()
    # Crucially: the file is NOT at other_cwd/workflows/cwd_test.yaml.
    bogus = (other_cwd / "workflows" / "cwd_test.yaml").resolve()
    assert not bogus.exists(), f"file leaked to CWD at {bogus}"
    assert Path(result.path).resolve() == expected


# ---------------------------------------------------------------------------
# Case 3+4: traversal rejection.
# ---------------------------------------------------------------------------


def test_write_workflow_absolute_outside_project_raises_permission_error(
    ctx_with_project: _StubRuntime,
    tmp_path: Path,
) -> None:
    """An absolute path outside project_dir is rejected before any write."""
    # tmp_path is a parent of project_root, so a sibling of project_root
    # is guaranteed to be outside.
    outside = (tmp_path / "outside_target.yaml").resolve()
    with pytest.raises(PermissionError, match="resolves outside project root"):
        _run(tools_workflow.write_workflow(path=str(outside), yaml=_VALID_WF_YAML))
    assert not outside.exists(), "write should not have occurred"


def test_write_workflow_relative_traversal_escape_raises_permission_error(
    ctx_with_project: _StubRuntime,
    project_root: Path,
) -> None:
    """A ``../`` escape is normalised and rejected."""
    with pytest.raises(PermissionError, match="resolves outside project root"):
        _run(tools_workflow.write_workflow(path="../escape.yaml", yaml=_VALID_WF_YAML))
    bogus = (project_root.parent / "escape.yaml").resolve()
    assert not bogus.exists()


# ---------------------------------------------------------------------------
# Case 5: absolute under project_dir is accepted.
# ---------------------------------------------------------------------------


def test_write_workflow_absolute_under_project_dir_succeeds(
    ctx_with_project: _StubRuntime,
    project_root: Path,
) -> None:
    target = project_root / "workflows" / "abs.yaml"
    result = _run(tools_workflow.write_workflow(path=str(target), yaml=_VALID_WF_YAML))
    assert target.resolve().is_file()
    assert Path(result.path).resolve() == target.resolve()


# ---------------------------------------------------------------------------
# Case 6+7: round-trip through get_workflow / validate_workflow.
# ---------------------------------------------------------------------------


def test_write_then_get_round_trip(
    ctx_with_project: _StubRuntime,
    project_root: Path,
) -> None:
    _run(tools_workflow.write_workflow(path="workflows/roundtrip.yaml", yaml=_VALID_WF_YAML))
    data = _run(tools_workflow.get_workflow(path="workflows/roundtrip.yaml"))
    # data is a WorkflowDefinitionEnvelope Pydantic model.
    # The workflow id comes from the workflow dict inside the YAML.
    expected = (project_root / "workflows" / "roundtrip.yaml").resolve()
    assert Path(data.path).resolve() == expected


def test_write_then_validate_round_trip(
    ctx_with_project: _StubRuntime,
) -> None:
    _run(tools_workflow.write_workflow(path="workflows/validate.yaml", yaml=_VALID_WF_YAML))
    result = _run(tools_workflow.validate_workflow(yaml_or_path="workflows/validate.yaml"))
    # result is a ValidateWorkflowResult Pydantic model.
    assert result.valid is True
    assert result.errors == []


# ---------------------------------------------------------------------------
# Case 8: write_workflow then run_workflow finds the file.
# ---------------------------------------------------------------------------


def test_write_then_run_workflow_uses_resolved_stem(
    ctx_with_project: _StubRuntime,
    project_root: Path,
) -> None:
    _run(tools_workflow.write_workflow(path="workflows/run_me.yaml", yaml=_VALID_WF_YAML))
    result = _run(tools_workflow.run_workflow(path="workflows/run_me.yaml"))
    # result is a RunWorkflowResult Pydantic model.
    assert result.status in ("queued", "started")
    assert "run_me" in result.run_id
    assert "run_me" in ctx_with_project.workflow_runs


# ---------------------------------------------------------------------------
# Case 9: update_block_config preserves comments and changes parameter.
# ---------------------------------------------------------------------------


_COMMENTED_WF = """\
# Top-level comment preserved by ruamel
workflow:
  id: commented_wf
  # version comment preserved
  version: 1.0.0
  nodes:
    - id: b1
      block_type: load_data
      config:
        params:
          backend: csv
  edges: []
"""


def test_update_block_config_preserves_comments(
    ctx_with_project: _StubRuntime,
    project_root: Path,
) -> None:
    """ruamel preserves comments outside the keys being mutated.

    Inline comments attached to a specific value (e.g. ``backend: csv  #
    note``) are dropped when the parameter dict is replaced; that's a
    documented ruamel limitation of dict-replace, not something this
    fix is responsible for. We assert preservation of *structural*
    comments that sit above/around the mutation.
    """
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
    # Structural comments survive.
    assert "Top-level comment preserved by ruamel" in text
    assert "version comment preserved" in text
    # The parameter was updated.
    assert "parquet" in text
    assert "csv" not in text
    # Envelope echoes the resolved path — out is an UpdateBlockConfigResult model.
    assert Path(out.workflow_path).resolve() == target


# ---------------------------------------------------------------------------
# Case 10: every write tool returns an absolute path.
# ---------------------------------------------------------------------------


def test_write_tools_return_absolute_paths(
    ctx_with_project: _StubRuntime,
) -> None:
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


# ---------------------------------------------------------------------------
# Case 11: concurrent writes serialise via the file lock.
# ---------------------------------------------------------------------------


def test_concurrent_write_workflow_serialises(
    ctx_with_project: _StubRuntime,
    project_root: Path,
) -> None:
    """Two concurrent writes on the same path: filelock serialises both."""
    results: list[Any] = []
    errors: list[BaseException] = []

    def _worker(payload: str) -> None:
        try:
            r = _run(tools_workflow.write_workflow(path="workflows/concurrent.yaml", yaml=payload))
            results.append(r)
        except BaseException as exc:
            errors.append(exc)

    t1 = threading.Thread(target=_worker, args=(_VALID_WF_YAML,))
    t2 = threading.Thread(
        target=_worker,
        args=(_VALID_WF_YAML.replace("integration_test", "second"),),
    )
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors, f"unexpected errors: {errors}"
    assert len(results) == 2
    expected = (project_root / "workflows" / "concurrent.yaml").resolve()
    assert expected.is_file()
    # Whichever finished last won; both are valid YAML on disk.
    content = expected.read_text(encoding="utf-8")
    assert "workflow:" in content


# ---------------------------------------------------------------------------
# Case 12: tool invocation without an open project raises RuntimeError.
# ---------------------------------------------------------------------------


def test_write_workflow_without_open_project_raises_runtime_error(
    project_root: Path,  # unused, but creates the dir; keeps fixture shape uniform
) -> None:
    """Context with project_dir=None raises a clear RuntimeError, not a TypeError."""
    runtime = _StubRuntime(_project_dir=None)
    _context.set_context(runtime)
    try:
        with pytest.raises(RuntimeError, match="No project is currently open"):
            _run(tools_workflow.write_workflow(path="workflows/x.yaml", yaml=_VALID_WF_YAML))
    finally:
        _context.set_context(None)


# ---------------------------------------------------------------------------
# Extra: macOS symlink-realpath sanity (also passes on Linux/Windows; the
# implementation relies on Path.resolve which calls realpath).
# ---------------------------------------------------------------------------


def test_resolved_path_uses_realpath_not_string_compare(
    ctx_with_project: _StubRuntime,
    project_root: Path,
) -> None:
    """The result of _resolve_project_path is realpath-canonicalised.

    On macOS this matters because ``tmp_path`` is reached via
    ``/private/var/folders/...`` while a naive client could refer to
    it via ``/var/folders/...``. Both must resolve to the same Path.

    On all platforms, double slashes / current-dir markers in the
    relative segment must be normalised away.
    """
    # Path with redundant ./ and // separators in the relative portion.
    result = _run(
        tools_workflow.write_workflow(
            path="workflows/./subdir/../redundant.yaml",
            yaml=_VALID_WF_YAML,
        )
    )
    expected = (project_root / "workflows" / "redundant.yaml").resolve()
    assert Path(result.path).resolve() == expected
    assert expected.is_file()
    # ``..`` should NOT have escaped (still inside workflows/).
    assert os.path.commonpath([str(expected), str(project_root)]) == str(project_root)
