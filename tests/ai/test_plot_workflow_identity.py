"""#2362 — a plot resolves ITS OWN workflow's output, never a namesake's.

Two workflows may legitimately contain a node with the same name. The plot
layer bound by ``(node_id, output_port)`` and scanned every entry of
``ctx.workflow_runs``, so whichever workflow came last in dict-iteration order
answered — a plot bound to workflow A's ``load_one`` rendered workflow B's
``load_one`` output, and a ``.npy`` deliberately loaded as an ``Artifact``
opened in the array previewer because the ref it was handed came from the other
workflow's node of the same name.

These tests build exactly that collision: two workflows, each with a node named
``load_one``, producing DIFFERENT types, and assert that target discovery and
plot input resolution each stay inside their own workflow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml

from scistudio.plot.runtime import _resolve_input
from scistudio.plot.targets import discover_targets, workflow_run_keys
from scistudio.plot.validation import load_plot

SHARED_NODE_ID = "load_one"
PORT = "output"


# ---------------------------------------------------------------------------
# Stub runtime (mirrors the shape ``tests/ai/test_mcp_tools_plot.py`` uses).
# ---------------------------------------------------------------------------


class _Payload:  # pragma: no cover - only its name is read as an accepted type
    pass


@dataclass
class _StubPort:
    name: str
    accepted_types: list[type]


@dataclass
class _StubSpec:
    output_ports: list[_StubPort]


class _StubBlockRegistry:
    def __init__(self, specs: dict[str, _StubSpec]) -> None:
        self._specs = specs

    def get_spec(self, type_name: str) -> _StubSpec | None:
        return self._specs.get(type_name)


class _StubScheduler:
    def __init__(self, block_outputs: dict[str, dict[str, Any]]) -> None:
        self._block_outputs = block_outputs


class _StubRun:
    def __init__(self, block_outputs: dict[str, dict[str, Any]]) -> None:
        self.scheduler = _StubScheduler(block_outputs)


@dataclass
class _StubRuntime:
    _project_dir: Path
    block_registry: Any = None
    type_registry: Any = None
    workflow_runs: dict[str, Any] = field(default_factory=dict)
    active_workflow_id: str | None = None

    @property
    def project_dir(self) -> Path | None:
        return self._project_dir


# ---------------------------------------------------------------------------
# Fixtures: two workflows that both contain a node named ``load_one``.
# ---------------------------------------------------------------------------


def _write_workflow(project: Path, workflow_id: str) -> None:
    wf_dir = project / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    (wf_dir / f"{workflow_id}.yaml").write_text(
        "workflow:\n"
        f"  id: {workflow_id}\n"
        "  version: 1.0.0\n"
        "  nodes:\n"
        f"  - id: {SHARED_NODE_ID}\n"
        "    block_type: demo.load\n"
        "    config:\n"
        "      label: Load One\n"
        "  edges: []\n",
        encoding="utf-8",
    )


def _write_plot(project: Path, plot_id: str, workflow_id: str) -> None:
    plot_dir = project / "plots" / plot_id
    plot_dir.mkdir(parents=True, exist_ok=True)
    (plot_dir / "plot.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "id": plot_id,
                "target": {
                    "workflow_path": f"workflows/{workflow_id}.yaml",
                    "workflow_id": workflow_id,
                    "node_id": SHARED_NODE_ID,
                    "output_port": PORT,
                },
                "script": {"language": "python", "path": "render.py", "entrypoint": "render"},
            }
        ),
        encoding="utf-8",
    )
    (plot_dir / "render.py").write_text("def render(collection):\n    return []\n", encoding="utf-8")


def _ref(path: Path, *, type_name: str, fmt: str) -> dict[str, Any]:
    return {
        "backend": "filesystem",
        "path": str(path),
        "format": fmt,
        "metadata": {"type_chain": ["DataObject", type_name]},
    }


@pytest.fixture
def project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    proj.mkdir()
    # ``array_wf`` and ``artifact_wf`` each own a node called ``load_one``.
    _write_workflow(proj, "array_wf")
    _write_workflow(proj, "artifact_wf")
    _write_plot(proj, "array_plot", "array_wf")
    _write_plot(proj, "artifact_plot", "artifact_wf")
    return proj


@pytest.fixture
def array_path(tmp_path: Path) -> Path:
    path = tmp_path / "grid.npy"
    path.write_bytes(b"\x93NUMPY-stub")
    return path


@pytest.fixture
def artifact_path(tmp_path: Path) -> Path:
    path = tmp_path / "opaque.npy"
    path.write_bytes(b"\x93NUMPY-stub-artifact")
    return path


def _runtime(project: Path, array_path: Path, artifact_path: Path) -> _StubRuntime:
    """Both workflows have run; both recorded an output on ``load_one``.

    ``workflow_runs`` is keyed by workflow id — that is what
    ``ApiRuntime.start_workflow`` registers a run under. ``artifact_wf`` is
    inserted LAST so a scan that ignores the workflow lands on it, which is the
    exact shape of the reported bug.
    """
    registry = _StubBlockRegistry(
        {"demo.load": _StubSpec(output_ports=[_StubPort(name=PORT, accepted_types=[_Payload])])}
    )
    return _StubRuntime(
        _project_dir=project,
        block_registry=registry,
        workflow_runs={
            "array_wf": _StubRun({SHARED_NODE_ID: {PORT: _ref(array_path, type_name="Array", fmt="npy")}}),
            "artifact_wf": _StubRun({SHARED_NODE_ID: {PORT: _ref(artifact_path, type_name="Artifact", fmt="npy")}}),
        },
    )


# ---------------------------------------------------------------------------
# workflow_run_keys.
# ---------------------------------------------------------------------------


def test_workflow_run_keys_prefers_the_file_stem() -> None:
    """The run registry is keyed by the file's run identity."""
    assert workflow_run_keys("workflows/main.yaml", "main") == ("main",)
    assert workflow_run_keys("workflows/main.yaml", None) == ("main",)
    # #2394: a declared id that drifted from the file name is not a key — a
    # copy still declaring the original's id must not read the original's run.
    assert workflow_run_keys("workflows/on_disk.yaml", "declared") == ("on_disk",)
    assert workflow_run_keys("subworkflows/qc.yaml", "main") == ("@subworkflows@qc.yaml",)


# ---------------------------------------------------------------------------
# Plot input resolution (the reported symptom).
# ---------------------------------------------------------------------------


def test_plot_resolves_its_own_workflows_output(project: Path, array_path: Path, artifact_path: Path) -> None:
    """Each plot gets the ref its OWN workflow's ``load_one`` produced.

    Before #2362 both plots resolved to whichever run came last in
    ``workflow_runs``, so the array plot rendered the artifact workflow's file
    and the artifact plot's preview ref was an ``Array``.
    """
    ctx = _runtime(project, array_path, artifact_path)

    array_manifest = load_plot(ctx, plot_id="array_plot").manifest
    artifact_manifest = load_plot(ctx, plot_id="artifact_plot").manifest

    array_resolved = _resolve_input(ctx, array_manifest, None)
    artifact_resolved = _resolve_input(ctx, artifact_manifest, None)

    assert [r["path"] for r in array_resolved.refs] == [str(array_path)]
    assert array_resolved.run_id == "array_wf"

    assert [r["path"] for r in artifact_resolved.refs] == [str(artifact_path)]
    assert artifact_resolved.run_id == "artifact_wf"


def test_plot_resolution_ignores_insertion_order(project: Path, array_path: Path, artifact_path: Path) -> None:
    """The answer does not depend on which run happens to be registered last.

    The pre-fix loop had no ``break``, so the LAST match won and the result
    moved with dict-iteration order. Reversing the registry must change nothing.
    """
    ctx = _runtime(project, array_path, artifact_path)
    ctx.workflow_runs = dict(reversed(list(ctx.workflow_runs.items())))

    manifest = load_plot(ctx, plot_id="array_plot").manifest
    resolved = _resolve_input(ctx, manifest, None)

    assert [r["path"] for r in resolved.refs] == [str(array_path)]
    assert resolved.run_id == "array_wf"


def test_plot_refuses_an_explicit_run_id_from_another_workflow(
    project: Path, array_path: Path, artifact_path: Path
) -> None:
    """Naming a foreign run is the same cross-workflow read by another route.

    It resolves to no input rather than to the other workflow's data, so the
    plot reports "no recorded output" instead of silently rendering a stranger.
    """
    ctx = _runtime(project, array_path, artifact_path)
    manifest = load_plot(ctx, plot_id="array_plot").manifest

    assert _resolve_input(ctx, manifest, "artifact_wf").refs == []
    # Its own run id still works.
    assert [r["path"] for r in _resolve_input(ctx, manifest, "array_wf").refs] == [str(array_path)]


# ---------------------------------------------------------------------------
# Target discovery.
# ---------------------------------------------------------------------------


def test_target_discovery_reports_each_workflows_own_run(project: Path, array_path: Path, artifact_path: Path) -> None:
    """``latest_run_id`` names the workflow the target lives in."""
    ctx = _runtime(project, array_path, artifact_path)
    by_workflow = {t.workflow_id: t for t in discover_targets(ctx)}

    assert set(by_workflow) == {"array_wf", "artifact_wf"}
    for workflow_id, target in by_workflow.items():
        assert target.node_id == SHARED_NODE_ID
        assert target.latest_output_available is True
        assert target.latest_run_id == workflow_id


def test_target_availability_is_not_borrowed_from_another_workflow(project: Path, array_path: Path) -> None:
    """A workflow that never ran reports no output, even when a namesake ran.

    Before #2362 ``artifact_wf``'s untouched ``load_one`` was reported ready
    because ``array_wf``'s node of the same name had produced data.
    """
    registry = _StubBlockRegistry(
        {"demo.load": _StubSpec(output_ports=[_StubPort(name=PORT, accepted_types=[_Payload])])}
    )
    ctx = _StubRuntime(
        _project_dir=project,
        block_registry=registry,
        workflow_runs={
            "array_wf": _StubRun({SHARED_NODE_ID: {PORT: _ref(array_path, type_name="Array", fmt="npy")}}),
        },
    )
    by_workflow = {t.workflow_id: t for t in discover_targets(ctx)}

    assert by_workflow["array_wf"].latest_output_available is True
    assert by_workflow["array_wf"].latest_run_id == "array_wf"
    assert by_workflow["artifact_wf"].latest_output_available is False
    assert by_workflow["artifact_wf"].latest_run_id is None
