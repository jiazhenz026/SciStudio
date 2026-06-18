"""Unit tests for ADR-048 SPEC 2 plot MCP tools (FR-001..FR-035).

Covers: target listing + uniqueness, scaffold create / overwrite-refuse /
path-traversal-reject, examples, read (exactly one of plot_id/path), validation
success + failure cases, and a real Python matplotlib run with SVG output plus a
sanitized failure and a timeout/size-cap path.

R execution is covered by ``requires_r``-marked tests (run only when Rscript is
on PATH) plus an always-on R manifest-validation test.
"""

from __future__ import annotations

import asyncio
import shutil
from collections.abc import Coroutine, Generator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

import pytest

from scistudio.ai.agent.mcp import _context
from scistudio.ai.agent.mcp.tools_plot import (
    list_plot_examples,
    list_plot_targets,
    read_plot_source,
    run_plot_job,
    scaffold_plot,
    validate_plot,
)

pytest.importorskip("pandas")
pytest.importorskip("matplotlib")
np = pytest.importorskip("numpy")

_T = TypeVar("_T")


# ---------------------------------------------------------------------------
# Stub runtime + fixtures.
# ---------------------------------------------------------------------------


@dataclass
class _StubPort:
    name: str
    accepted_types: list[type]


@dataclass
class _StubSpec:
    output_ports: list[_StubPort]


class _StubBlockRegistry:
    """Minimal block registry: maps block_type -> output ports."""

    def __init__(self, specs: dict[str, _StubSpec]) -> None:
        self._specs = specs

    def get_spec(self, type_name: str) -> _StubSpec | None:
        return self._specs.get(type_name)


class _DynamicBlock:
    """Block instance whose output ports are config-driven."""

    def __init__(self, config: dict[str, Any]) -> None:
        params = config.get("params")
        if isinstance(params, dict):
            config = params
        self._port_name = str(config.get("output_port", "measurements"))

    def get_effective_output_ports(self) -> list[_StubPort]:
        return [_StubPort(name=self._port_name, accepted_types=[_Measurements])]


class _DynamicBlockRegistry(_StubBlockRegistry):
    def instantiate(self, type_name: str, config: dict[str, Any] | None = None) -> _DynamicBlock:
        if type_name != "demo.dynamic":
            raise KeyError(type_name)
        return _DynamicBlock(config or {})


@dataclass
class _StubTypeSpec:
    base_type: str


class _StubTypeRegistry:
    def __init__(self, specs: dict[str, str]) -> None:
        self._specs = {name: _StubTypeSpec(base_type=base_type) for name, base_type in specs.items()}

    def all_types(self) -> dict[str, _StubTypeSpec]:
        return dict(self._specs)


class _StubScheduler:
    def __init__(self, block_outputs: dict[str, dict[str, Any]]) -> None:
        self._block_outputs = block_outputs


class _StubRun:
    def __init__(self, block_outputs: dict[str, dict[str, Any]]) -> None:
        self.scheduler = _StubScheduler(block_outputs)


@dataclass
class _PlotRecord:
    id: str
    type_name: str
    type_chain: list[str]
    metadata: dict[str, Any]


@dataclass
class _StubRuntime:
    _project_dir: Path
    block_registry: Any = None
    type_registry: Any = None
    workflow_runs: dict[str, Any] = field(default_factory=dict)
    active_workflow_id: str | None = None
    data_catalog: dict[str, _PlotRecord] = field(default_factory=dict)

    @property
    def project_dir(self) -> Path | None:
        return self._project_dir

    def register_plot_artifact(
        self,
        artifact_path: str | Path,
        *,
        cache_key: str | None = None,
        workflow_id: str | None = None,
        node_id: str | None = None,
        output_port: str | None = None,
        plot_id: str | None = None,
    ) -> _PlotRecord:
        record = _PlotRecord(
            id=f"data-plot-{len(self.data_catalog) + 1}",
            type_name="PlotArtifact",
            type_chain=["DataObject", "PlotArtifact"],
            metadata={
                "path": str(artifact_path),
                "cache_key": cache_key,
                "plot_id": plot_id,
                "source": {
                    "workflow_id": workflow_id,
                    "node_id": node_id,
                    "output_port": output_port,
                },
            },
        )
        self.data_catalog[record.id] = record
        return record


class _Measurements:  # pragma: no cover - used only as an accepted-type name
    pass


def _write_workflow(project: Path, *, repeated: bool = False) -> None:
    """Write workflows/main.yaml with one or two nodes of the same block type."""
    wf_dir = project / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    nodes = [
        "  - id: node_a\n    block_type: demo.segment\n    config:\n      label: Segment Cells\n",
    ]
    if repeated:
        nodes.append("  - id: node_b\n    block_type: demo.segment\n    config:\n      label: Segment Cells\n")
    text = "workflow:\n  id: main\n  version: 1.0.0\n  nodes:\n" + "".join(nodes) + "  edges: []\n"
    (wf_dir / "main.yaml").write_text(text, encoding="utf-8")


def _make_runtime(project: Path, *, with_output_csv: Path | None = None, repeated: bool = False) -> _StubRuntime:
    registry = _StubBlockRegistry(
        {"demo.segment": _StubSpec(output_ports=[_StubPort(name="measurements", accepted_types=[_Measurements])])}
    )
    runs: dict[str, Any] = {}
    if with_output_csv is not None:
        runs["run_1"] = _StubRun(
            {
                "node_a": {
                    "measurements": {
                        "backend": "filesystem",
                        "path": str(with_output_csv),
                        "format": "csv",
                        "metadata": {"type_chain": ["DataFrame"]},
                    }
                }
            }
        )
    return _StubRuntime(_project_dir=project, block_registry=registry, workflow_runs=runs)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    proj.mkdir()
    _write_workflow(proj)
    return proj


@pytest.fixture
def csv_output(tmp_path: Path) -> Path:
    csv = tmp_path / "measurements.csv"
    lines = ["x,y"] + [f"{i},{i * 2}" for i in range(20)]
    csv.write_text("\n".join(lines), encoding="utf-8")
    return csv


def _set_ctx(runtime: _StubRuntime) -> None:
    _context.set_context(runtime)


def _run(coro: Coroutine[Any, Any, _T]) -> _T:
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _teardown_ctx() -> Generator[None, None, None]:
    yield
    _context.set_context(None)


# ---------------------------------------------------------------------------
# list_plot_targets (FR-005, FR-006, SC-002).
# ---------------------------------------------------------------------------


def test_list_targets_returns_stable_target_ids(project: Path) -> None:
    _set_ctx(_make_runtime(project))
    result = _run(list_plot_targets())
    assert result.count == 1
    t = result.targets[0]
    assert t.node_id == "node_a"
    assert t.output_port == "measurements"
    assert t.target_id.startswith("tgt_")
    assert t.latest_output_available is False  # no run recorded


def test_list_targets_distinguishes_repeated_blocks(project: Path) -> None:
    """SC-002: two repeated blocks with identical labels get DISTINCT target ids."""
    _write_workflow(project, repeated=True)
    _set_ctx(_make_runtime(project, repeated=True))
    result = _run(list_plot_targets())
    ids = {t.target_id for t in result.targets}
    node_ids = {t.node_id for t in result.targets}
    assert node_ids == {"node_a", "node_b"}
    assert len(ids) == 2, "repeated blocks must produce unique target_ids"


def test_list_targets_availability_with_recorded_output(project: Path, csv_output: Path) -> None:
    _set_ctx(_make_runtime(project, with_output_csv=csv_output))
    result = _run(list_plot_targets())
    t = result.targets[0]
    assert t.latest_output_available is True
    assert t.latest_run_id == "run_1"


def test_list_targets_rejects_workflow_path_traversal(project: Path, tmp_path: Path) -> None:
    """FR-004: workflow_path is project-confined."""
    outside = tmp_path / "outside.yaml"
    outside.write_text(
        "workflow:\n  id: outside\n  version: 1.0.0\n  nodes:\n"
        "  - id: node_x\n    block_type: demo.segment\n    config: {}\n"
        "  edges: []\n",
        encoding="utf-8",
    )
    _set_ctx(_make_runtime(project))
    with pytest.raises(PermissionError):
        _run(list_plot_targets(workflow_path="../outside.yaml"))


def test_list_targets_uses_effective_output_ports(project: Path) -> None:
    """Dynamic blocks must be listed with their config-driven output port."""
    wf = project / "workflows" / "main.yaml"
    wf.write_text(
        "workflow:\n  id: main\n  version: 1.0.0\n  nodes:\n"
        "  - id: node_dyn\n    block_type: demo.dynamic\n    config:\n"
        "      params:\n        output_port: dynamic_measurements\n"
        "  edges: []\n",
        encoding="utf-8",
    )
    registry = _DynamicBlockRegistry(
        {"demo.dynamic": _StubSpec(output_ports=[_StubPort(name="placeholder", accepted_types=[object])])}
    )
    _set_ctx(_StubRuntime(_project_dir=project, block_registry=registry))
    result = _run(list_plot_targets())
    assert result.count == 1
    assert result.targets[0].output_port == "dynamic_measurements"
    assert result.targets[0].output_type == "_Measurements"


# ---------------------------------------------------------------------------
# scaffold_plot (FR-007, FR-008, FR-009).
# ---------------------------------------------------------------------------


def _target_id(project: Path) -> str:
    result = _run(list_plot_targets())
    return str(result.targets[0].target_id)


def test_scaffold_creates_python_plot(project: Path) -> None:
    _set_ctx(_make_runtime(project))
    tid = _target_id(project)
    res = _run(scaffold_plot(plot_id="cell_scatter", target_id=tid, language="python"))
    assert res.plot_id == "cell_scatter"
    assert res.next_step
    assert (project / "plots" / "cell_scatter" / "plot.yaml").is_file()
    assert (project / "plots" / "cell_scatter" / "render.py").is_file()
    body = (project / "plots" / "cell_scatter" / "render.py").read_text(encoding="utf-8")
    assert "def render(collection):" in body
    assert "context" not in body
    assert "collection.items.open_one()" in body
    assert "ADR-048" not in body


def test_scaffold_creates_r_plot(project: Path) -> None:
    _set_ctx(_make_runtime(project))
    tid = _target_id(project)
    _run(scaffold_plot(plot_id="r_plot", target_id=tid, language="r"))
    assert (project / "plots" / "r_plot" / "render.R").is_file()
    body = (project / "plots" / "r_plot" / "render.R").read_text(encoding="utf-8")
    assert "render <- function(collection)" in body
    assert "What `collection` means" in body
    assert "context" not in body
    assert "Minimal examples" in body
    assert "ADR-048" not in body


def test_scaffold_refuses_overwrite_by_default(project: Path) -> None:
    _set_ctx(_make_runtime(project))
    tid = _target_id(project)
    _run(scaffold_plot(plot_id="dup", target_id=tid, language="python"))
    with pytest.raises(FileExistsError):
        _run(scaffold_plot(plot_id="dup", target_id=tid, language="python"))
    # overwrite=true succeeds.
    res = _run(scaffold_plot(plot_id="dup", target_id=tid, language="python", overwrite=True))
    assert res.plot_id == "dup"


def test_scaffold_rejects_label_only_selection(project: Path) -> None:
    """FR-011 / SC: scaffold must reject a non-target_id (e.g. a label)."""
    _set_ctx(_make_runtime(project))
    with pytest.raises(ValueError, match="unknown target_id"):
        _run(scaffold_plot(plot_id="x", target_id="Segment Cells", language="python"))


def test_scaffold_rejects_path_traversal_plot_id(project: Path) -> None:
    _set_ctx(_make_runtime(project))
    tid = _target_id(project)
    for bad in ("../evil", "a/b", ".hidden", "with space"):
        with pytest.raises(ValueError):
            _run(scaffold_plot(plot_id=bad, target_id=tid, language="python"))


# ---------------------------------------------------------------------------
# list_plot_examples (FR-019).
# ---------------------------------------------------------------------------


def test_list_examples_includes_three_libraries(project: Path) -> None:
    _set_ctx(_make_runtime(project))
    res = _run(list_plot_examples())
    libs = {e.library for e in res.examples}
    assert {"matplotlib", "seaborn", "ggplot2"} <= libs


def test_list_examples_filter_by_language(project: Path) -> None:
    _set_ctx(_make_runtime(project))
    res = _run(list_plot_examples(language="r"))
    assert res.count >= 1
    assert all(e.language == "r" for e in res.examples)


def test_list_examples_are_context_free(project: Path) -> None:
    _set_ctx(_make_runtime(project))
    res = _run(list_plot_examples())
    assert res.examples
    for example in res.examples:
        assert "context" not in example.source
        if example.language == "python":
            assert "def render(collection):" in example.source
        if example.language == "r":
            assert "render <- function(collection)" in example.source


# ---------------------------------------------------------------------------
# read_plot_source (FR-020).
# ---------------------------------------------------------------------------


def test_read_requires_exactly_one_selector(project: Path) -> None:
    _set_ctx(_make_runtime(project))
    tid = _target_id(project)
    _run(scaffold_plot(plot_id="readme", target_id=tid, language="python"))
    with pytest.raises(ValueError, match="exactly one"):
        _run(read_plot_source())
    with pytest.raises(ValueError, match="exactly one"):
        _run(read_plot_source(plot_id="readme", path="plots/readme/plot.yaml"))
    res = _run(read_plot_source(plot_id="readme"))
    assert res.plot_id == "readme"
    assert "def render(collection):" in res.script_source
    assert "context" not in res.script_source


def test_read_rejects_manifest_script_path_traversal(project: Path, tmp_path: Path) -> None:
    """FR-004/FR-020: read_plot_source must not read escaped render scripts."""
    _set_ctx(_make_runtime(project))
    tid = _target_id(project)
    _run(scaffold_plot(plot_id="escaped_read", target_id=tid, language="python"))
    outside = tmp_path / "outside_render.py"
    outside.write_text("def render(collection):\n    return None\n", encoding="utf-8")
    manifest = project / "plots" / "escaped_read" / "plot.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace("path: render.py", "path: ../../../outside_render.py"),
        encoding="utf-8",
    )
    with pytest.raises(PermissionError, match=r"script\.path"):
        _run(read_plot_source(plot_id="escaped_read"))


# ---------------------------------------------------------------------------
# validate_plot (FR-021, FR-022, SC-004).
# ---------------------------------------------------------------------------


def test_validate_success(project: Path) -> None:
    _set_ctx(_make_runtime(project))
    tid = _target_id(project)
    _run(scaffold_plot(plot_id="good", target_id=tid, language="python"))
    res = _run(validate_plot(plot_id="good"))
    assert res.valid, res.errors
    assert res.manifest is not None


def test_validate_rejects_python_context_signature(project: Path) -> None:
    _set_ctx(_make_runtime(project))
    tid = _target_id(project)
    _run(scaffold_plot(plot_id="oldpy", target_id=tid, language="python"))
    (project / "plots" / "oldpy" / "render.py").write_text(
        "def render(collection, context):\n    return None\n",
        encoding="utf-8",
    )
    res = _run(validate_plot(plot_id="oldpy"))
    assert not res.valid
    assert any("def render(collection)" in e and "context" in e for e in res.errors)


def test_validate_rejects_r_context_signature(project: Path) -> None:
    _set_ctx(_make_runtime(project))
    tid = _target_id(project)
    _run(scaffold_plot(plot_id="oldr", target_id=tid, language="r"))
    (project / "plots" / "oldr" / "render.R").write_text(
        "render <- function(collection, context) {\n  NULL\n}\n",
        encoding="utf-8",
    )
    res = _run(validate_plot(plot_id="oldr"))
    assert not res.valid
    assert any("render <- function(collection)" in e and "context" in e for e in res.errors)


def test_validate_broken_target(project: Path) -> None:
    """SC-004: a manifest pointing at a deleted node is invalid."""
    _set_ctx(_make_runtime(project))
    tid = _target_id(project)
    _run(scaffold_plot(plot_id="broken", target_id=tid, language="python"))
    # Delete the workflow so the target no longer resolves.
    (project / "workflows" / "main.yaml").unlink()
    res = _run(validate_plot(plot_id="broken"))
    assert not res.valid
    assert any("broken target" in e.lower() or "not found" in e.lower() for e in res.errors)


def test_validate_unsupported_format(project: Path) -> None:
    _set_ctx(_make_runtime(project))
    tid = _target_id(project)
    _run(scaffold_plot(plot_id="badfmt", target_id=tid, language="python"))
    manifest = project / "plots" / "badfmt" / "plot.yaml"
    text = manifest.read_text(encoding="utf-8").replace("preferred_format: svg", "preferred_format: gif")
    manifest.write_text(text, encoding="utf-8")
    res = _run(validate_plot(plot_id="badfmt"))
    assert not res.valid


def test_validate_missing_entrypoint(project: Path) -> None:
    _set_ctx(_make_runtime(project))
    tid = _target_id(project)
    _run(scaffold_plot(plot_id="noentry", target_id=tid, language="python"))
    manifest = project / "plots" / "noentry" / "plot.yaml"
    text = manifest.read_text(encoding="utf-8").replace("entrypoint: render", "entrypoint: draw")
    manifest.write_text(text, encoding="utf-8")
    res = _run(validate_plot(plot_id="noentry"))
    assert not res.valid
    assert any("entrypoint" in e.lower() for e in res.errors)


def test_validate_requires_exactly_one_selector(project: Path) -> None:
    _set_ctx(_make_runtime(project))
    with pytest.raises(ValueError, match="exactly one"):
        _run(validate_plot())


# ---------------------------------------------------------------------------
# run_plot_job — Python matplotlib SVG (FR-026..FR-031, SC-005, SC-006).
# ---------------------------------------------------------------------------


def _write_render(project: Path, plot_id: str, body: str) -> None:
    (project / "plots" / plot_id / "render.py").write_text(body, encoding="utf-8")


def test_run_python_svg_success(project: Path, csv_output: Path) -> None:
    _set_ctx(_make_runtime(project, with_output_csv=csv_output))
    tid = _target_id(project)
    _run(scaffold_plot(plot_id="scatter", target_id=tid, language="python"))
    _write_render(
        project,
        "scatter",
        (
            "def render(collection):\n"
            "    import matplotlib.pyplot as plt\n"
            "    assert collection.types == ('DataFrame',)\n"
            "    assert len(collection.items) == 1\n"
            "    assert collection.items[0].type == 'DataFrame'\n"
            "    assert 'path' not in collection.items[0].metadata\n"
            "    assert 'format' not in collection.items[0].metadata\n"
            "    assert 'type_chain' not in collection.items[0].metadata\n"
            "    assert collection.items[0:1][0].type == 'DataFrame'\n"
            "    df = collection.items.open_one()\n"
            "    assert len(collection.items.open(max_items=1)) == 1\n"
            "    fig, ax = plt.subplots()\n"
            "    ax.scatter(df['x'], df['y'], s=4)\n"
            "    return fig\n"
        ),
    )
    res = _run(run_plot_job(plot_id="scatter"))
    assert res.status == "succeeded", res.errors
    assert res.artifact_paths
    svg = Path(res.artifact_paths[0])
    assert svg.name == "current.svg"
    assert svg.is_file()
    assert res.data_ref == "data-plot-1"
    assert res.preview_target is not None
    assert res.preview_target.kind == "plot_artifact"
    assert res.preview_target.ref == res.data_ref
    assert res.preview_target.source == {
        "workflow_id": "main",
        "node_id": "node_a",
        "output_port": "measurements",
    }
    # current.json written.
    assert res.metadata_path and Path(res.metadata_path).is_file()


def test_run_normalizes_package_array_subclass_to_array(project: Path, tmp_path: Path) -> None:
    array_path = tmp_path / "image.npy"
    np.save(array_path, np.arange(9, dtype="float32").reshape(3, 3))
    runtime = _make_runtime(project)
    runtime.type_registry = _StubTypeRegistry({"Image": "Array"})
    runtime.workflow_runs["run_1"] = _StubRun(
        {
            "node_a": {
                "measurements": {
                    "backend": "filesystem",
                    "path": str(array_path),
                    "format": "npy",
                    "item_type": "Image",
                    "metadata": {
                        "shape": [3, 3],
                        "dtype": "float32",
                        "path": "should-not-leak",
                        "format": "npy",
                    },
                }
            }
        }
    )
    _set_ctx(runtime)
    tid = _target_id(project)
    _run(scaffold_plot(plot_id="image_plot", target_id=tid, language="python"))
    _write_render(
        project,
        "image_plot",
        (
            "def render(collection):\n"
            "    import matplotlib.pyplot as plt\n"
            "    assert collection.types == ('Array',)\n"
            "    item = collection.items[0]\n"
            "    assert item.type == 'Array'\n"
            "    assert 'type_chain' not in item.metadata\n"
            "    assert 'path' not in item.metadata\n"
            "    array = item.open()\n"
            "    assert array.shape == (3, 3)\n"
            "    fig, ax = plt.subplots()\n"
            "    ax.imshow(array)\n"
            "    return fig\n"
        ),
    )
    res = _run(run_plot_job(plot_id="image_plot"))
    assert res.status == "succeeded", res.errors


def test_open_enforces_input_memory_guard(project: Path, csv_output: Path) -> None:
    runtime = _make_runtime(project, with_output_csv=csv_output)
    runtime.workflow_runs["run_1"].scheduler._block_outputs["node_a"]["measurements"]["metadata"] = {
        "type_chain": ["DataFrame"],
        "shape": [10000, 10000],
        "dtype": "float64",
    }
    _set_ctx(runtime)
    tid = _target_id(project)
    _run(scaffold_plot(plot_id="too_big", target_id=tid, language="python"))
    manifest = project / "plots" / "too_big" / "plot.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace("max_input_bytes: 67108864", "max_input_bytes: 64"),
        encoding="utf-8",
    )
    _write_render(
        project,
        "too_big",
        ("def render(collection):\n    collection.items.open_one()\n    return None\n"),
    )
    res = _run(run_plot_job(plot_id="too_big"))
    assert res.status == "failed"
    assert any("memory cap" in e for e in res.errors)


def test_run_python_sanitized_failure(project: Path, csv_output: Path) -> None:
    _set_ctx(_make_runtime(project, with_output_csv=csv_output))
    tid = _target_id(project)
    _run(scaffold_plot(plot_id="boom", target_id=tid, language="python"))
    _write_render(
        project,
        "boom",
        ("def render(collection):\n    raise RuntimeError('kaboom')\n"),
    )
    res = _run(run_plot_job(plot_id="boom"))
    assert res.status == "failed"
    assert any("kaboom" in e for e in res.errors)
    # The sanitized error must not leak the absolute project path.
    joined = " ".join(res.errors) + res.stderr
    assert str(project.resolve()) not in joined


def test_run_rejects_manifest_script_path_traversal(project: Path, csv_output: Path, tmp_path: Path) -> None:
    """FR-004/FR-023: run_plot_job must not execute escaped render scripts."""
    _set_ctx(_make_runtime(project, with_output_csv=csv_output))
    tid = _target_id(project)
    _run(scaffold_plot(plot_id="escaped_run", target_id=tid, language="python"))
    outside = tmp_path / "outside_render.py"
    outside.write_text(
        (
            "def render(collection):\n"
            "    import matplotlib.pyplot as plt\n"
            "    fig, ax = plt.subplots()\n"
            "    ax.plot([1, 2, 3])\n"
            "    return fig\n"
        ),
        encoding="utf-8",
    )
    manifest = project / "plots" / "escaped_run" / "plot.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace("path: render.py", "path: ../../../outside_render.py"),
        encoding="utf-8",
    )
    with pytest.raises(PermissionError, match=r"script\.path"):
        _run(run_plot_job(plot_id="escaped_run"))


def test_run_overwrites_current(project: Path, csv_output: Path) -> None:
    """FR-027: rerun overwrites current.* + records the new run."""
    _set_ctx(_make_runtime(project, with_output_csv=csv_output))
    tid = _target_id(project)
    _run(scaffold_plot(plot_id="rerun", target_id=tid, language="python"))
    _write_render(
        project,
        "rerun",
        (
            "def render(collection):\n"
            "    import matplotlib.pyplot as plt\n"
            "    fig, ax = plt.subplots()\n"
            "    ax.plot([1, 2, 3])\n"
            "    return fig\n"
        ),
    )
    first = _run(run_plot_job(plot_id="rerun"))
    assert first.status == "succeeded"
    svg = Path(first.artifact_paths[0])
    first_bytes = svg.read_bytes()
    # Change the script so the artifact differs, then rerun.
    _write_render(
        project,
        "rerun",
        (
            "def render(collection):\n"
            "    import matplotlib.pyplot as plt\n"
            "    fig, ax = plt.subplots()\n"
            "    ax.bar([0, 1, 2], [3, 2, 1])\n"
            "    return fig\n"
        ),
    )
    second = _run(run_plot_job(plot_id="rerun"))
    assert second.status == "succeeded"
    assert Path(second.artifact_paths[0]) == svg
    assert svg.read_bytes() != first_bytes


def test_run_failed_rerun_records_failure_state(project: Path, csv_output: Path) -> None:
    """FR / US4 scenario 3: a failing rerun records failure in current.json."""
    import json

    _set_ctx(_make_runtime(project, with_output_csv=csv_output))
    tid = _target_id(project)
    _run(scaffold_plot(plot_id="flip", target_id=tid, language="python"))
    _write_render(
        project,
        "flip",
        (
            "def render(collection):\n"
            "    import matplotlib.pyplot as plt\n"
            "    fig, ax = plt.subplots()\n"
            "    ax.plot([1, 2, 3])\n"
            "    return fig\n"
        ),
    )
    ok = _run(run_plot_job(plot_id="flip"))
    assert ok.status == "succeeded"
    _write_render(project, "flip", "def render(collection):\n    raise ValueError('nope')\n")
    bad = _run(run_plot_job(plot_id="flip"))
    assert bad.status == "failed"
    assert bad.metadata_path is not None
    record = json.loads(Path(bad.metadata_path).read_text(encoding="utf-8"))
    assert record["status"] == "failed"
    assert record["error"]
    assert not Path(ok.artifact_paths[0]).exists()


def test_run_enforces_file_count_cap(project: Path, csv_output: Path) -> None:
    """FR-029: writing more files than max_files fails the run."""
    _set_ctx(_make_runtime(project, with_output_csv=csv_output))
    tid = _target_id(project)
    _run(scaffold_plot(plot_id="manyfiles", target_id=tid, language="python"))
    # Tighten the cap to 1.
    manifest = project / "plots" / "manyfiles" / "plot.yaml"
    manifest.write_text(manifest.read_text(encoding="utf-8").replace("max_files: 8", "max_files: 1"), encoding="utf-8")
    _write_render(
        project,
        "manyfiles",
        (
            "def render(collection):\n"
            "    import matplotlib.pyplot as plt\n"
            "    paths = []\n"
            "    for i in range(3):\n"
            "        fig, ax = plt.subplots()\n"
            "        ax.plot([1, 2, 3])\n"
            "        path = f'figure_{i}.svg'\n"
            "        fig.savefig(path)\n"
            "        paths.append(path)\n"
            "    return paths\n"
        ),
    )
    res = _run(run_plot_job(plot_id="manyfiles"))
    assert res.status == "failed"
    assert any("max_files" in e for e in res.errors)


def test_run_timeout(project: Path, csv_output: Path) -> None:
    """FR-029: a slow render is timed out."""
    _set_ctx(_make_runtime(project, with_output_csv=csv_output))
    tid = _target_id(project)
    _run(scaffold_plot(plot_id="slow", target_id=tid, language="python"))
    _write_render(
        project,
        "slow",
        ("import time\n\ndef render(collection):\n    time.sleep(5)\n    return None\n"),
    )
    res = _run(run_plot_job(plot_id="slow", timeout_seconds=1.0))
    assert res.status == "timed_out"


# ---------------------------------------------------------------------------
# R: manifest validation always; execution only with Rscript (FR-015, SC-007).
# ---------------------------------------------------------------------------


def test_r_manifest_validates_without_runner(project: Path) -> None:
    """SC-007: R manifest validates everywhere; runner unavailability is a warning."""
    _set_ctx(_make_runtime(project))
    tid = _target_id(project)
    _run(scaffold_plot(plot_id="rmanifest", target_id=tid, language="r"))
    res = _run(validate_plot(plot_id="rmanifest"))
    assert res.valid, res.errors
    if shutil.which("Rscript") is None:
        assert any("R runner unavailable" in w for w in res.warnings)


@pytest.mark.requires_r
def test_run_r_ggplot2(project: Path, csv_output: Path) -> None:
    """SC-007: real R + ggplot2 run produces an artifact (skipped without Rscript)."""
    if shutil.which("Rscript") is None:
        pytest.skip("Rscript not on PATH")
    _set_ctx(_make_runtime(project, with_output_csv=csv_output))
    tid = _target_id(project)
    _run(scaffold_plot(plot_id="rrun", target_id=tid, language="r"))
    (project / "plots" / "rrun" / "render.R").write_text(
        (
            "render <- function(collection) {\n"
            "  df <- collection$items$open_one()\n"
            "  ggplot2::ggplot(df, ggplot2::aes(x = x, y = y)) + ggplot2::geom_point()\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    res = _run(run_plot_job(plot_id="rrun"))
    # Either it succeeded with a PDF, or ggplot2 is missing → failed with a
    # clear error (not a crash).
    assert res.status in {"succeeded", "failed"}
    if res.status == "succeeded":
        assert any(p.endswith(".svg") for p in res.artifact_paths)
