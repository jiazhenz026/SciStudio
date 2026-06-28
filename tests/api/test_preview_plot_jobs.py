"""Preview-cache + isolation tests for ADR-048 SPEC 2 plot jobs (FR-025..FR-031, SC-005, SC-010).

Verifies:
  * ``run_plot_job`` writes ``current.*`` + ``current.json`` at the FR-026 cache
    layout and that rerun overwrites them;
  * a failed rerun records the failure state in ``current.json``;
  * a plot run does NOT mutate workflow YAML, scheduler state, lineage, or any
    downstream collection (FR-025);
  * the produced SVG artifact is consumable by the core ``PlotPreviewer``
    (``core.plot.basic``) — SC-010.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine, Generator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

import pytest

from scistudio.ai.agent.mcp import _context
from scistudio.ai.agent.mcp.tools_plot import run_plot_job, scaffold_plot
from scistudio.plot.runtime import _flatten_to_refs, preview_cache_dir
from scistudio.plot.targets import discover_targets

pytest.importorskip("pandas")
pytest.importorskip("matplotlib")

_T = TypeVar("_T")


# ---------------------------------------------------------------------------
# Stub runtime (mirrors test_mcp_tools_plot).
# ---------------------------------------------------------------------------


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


class _Measurements:  # pragma: no cover
    pass


def _run(coro: Coroutine[Any, Any, _T]) -> _T:
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _teardown_ctx() -> Generator[None, None, None]:
    yield
    _context.set_context(None)


@pytest.fixture
def setup(tmp_path: Path) -> tuple[Path, _StubRuntime, Path]:
    project = tmp_path / "proj"
    (project / "workflows").mkdir(parents=True)
    wf = project / "workflows" / "main.yaml"
    wf.write_text(
        "workflow:\n  id: main\n  version: 1.0.0\n  nodes:\n"
        "  - id: node_a\n    block_type: demo.segment\n    config:\n      label: Seg\n"
        "  edges: []\n",
        encoding="utf-8",
    )
    csv = tmp_path / "measurements.csv"
    csv.write_text("x,y\n" + "\n".join(f"{i},{i * 2}" for i in range(20)), encoding="utf-8")
    registry = _StubBlockRegistry(
        {"demo.segment": _StubSpec(output_ports=[_StubPort(name="measurements", accepted_types=[_Measurements])])}
    )
    runs = {
        "run_1": _StubRun(
            {
                "node_a": {
                    "measurements": {
                        "backend": "filesystem",
                        "path": str(csv),
                        "format": "csv",
                        "metadata": {"type_chain": ["DataFrame"]},
                    }
                }
            }
        )
    }
    runtime = _StubRuntime(_project_dir=project, block_registry=registry, workflow_runs=runs)
    _context.set_context(runtime)
    tid = discover_targets(runtime)[0].target_id
    _run(scaffold_plot(plot_id="p1", target_id=tid, language="python"))
    (project / "plots" / "p1" / "render.py").write_text(
        (
            "def render(collection):\n"
            "    import matplotlib.pyplot as plt\n"
            "    df = collection.items.open_one()\n"
            "    fig, ax = plt.subplots()\n"
            "    ax.scatter(df['x'], df['y'], s=4)\n"
            "    return fig\n"
        ),
        encoding="utf-8",
    )
    return project, runtime, wf


# ---------------------------------------------------------------------------
# Cache layout + metadata (FR-026, FR-028, FR-027).
# ---------------------------------------------------------------------------


def test_writes_current_svg_and_json_at_fr026_layout(setup: tuple[Path, _StubRuntime, Path]) -> None:
    project, _runtime, _wf = setup
    res = _run(run_plot_job(plot_id="p1"))
    assert res.status == "succeeded", res.errors

    cache_dir = preview_cache_dir(project, "main", "node_a", "measurements", "p1")
    assert (cache_dir / "current.svg").is_file()
    assert (cache_dir / "current.json").is_file()
    # The FR-026 path layout is exactly previews/<wf>/<node>/<port>/<plot>/.
    rel = cache_dir.relative_to(project / ".scistudio" / "previews").as_posix()
    assert rel == "main/node_a/measurements/p1"

    record = json.loads((cache_dir / "current.json").read_text(encoding="utf-8"))
    assert record["plot_id"] == "p1"
    assert record["status"] == "succeeded"
    assert record["runner"] == "python"
    assert record["target"]["node_id"] == "node_a"
    assert record["target"]["output_port"] == "measurements"
    assert record["script_hash"]
    assert record["run_id"] == "run_1"
    assert any(o["filename"] == "current.svg" for o in record["outputs"])
    assert record["cache_key"] == res.cache_key


def test_rerun_overwrites_current(setup: tuple[Path, _StubRuntime, Path]) -> None:
    _project, _runtime, _wf = setup
    first = _run(run_plot_job(plot_id="p1"))
    svg = Path(first.artifact_paths[0])
    assert first.metadata_path is not None
    first_created = json.loads(Path(first.metadata_path).read_text(encoding="utf-8"))["created"]
    second = _run(run_plot_job(plot_id="p1"))
    assert Path(second.artifact_paths[0]) == svg
    assert second.metadata_path is not None
    second_created = json.loads(Path(second.metadata_path).read_text(encoding="utf-8"))["created"]
    assert second_created >= first_created


def test_failed_rerun_records_failure(setup: tuple[Path, _StubRuntime, Path]) -> None:
    project, _runtime, _wf = setup
    ok = _run(run_plot_job(plot_id="p1"))
    assert ok.status == "succeeded"
    previous_svg = Path(ok.artifact_paths[0])
    assert previous_svg.is_file()
    (project / "plots" / "p1" / "render.py").write_text(
        "def render(collection):\n    raise ValueError('boom')\n", encoding="utf-8"
    )
    bad = _run(run_plot_job(plot_id="p1"))
    assert bad.status == "failed"
    assert bad.metadata_path is not None
    record = json.loads(Path(bad.metadata_path).read_text(encoding="utf-8"))
    assert record["status"] == "failed"
    assert record["error"]
    assert not previous_svg.exists()


# ---------------------------------------------------------------------------
# Isolation: no DAG / scheduler / lineage / downstream mutation (FR-025, SC-005).
# ---------------------------------------------------------------------------


def test_plot_run_does_not_mutate_workflow_or_scheduler_or_lineage(
    setup: tuple[Path, _StubRuntime, Path],
) -> None:
    project, runtime, wf = setup
    wf_before = wf.read_text(encoding="utf-8")
    # Snapshot scheduler outputs (the only live run state).
    sched = runtime.workflow_runs["run_1"].scheduler
    outputs_before = json.dumps(sched._block_outputs, sort_keys=True, default=str)
    run_ids_before = set(runtime.workflow_runs.keys())

    res = _run(run_plot_job(plot_id="p1"))
    assert res.status == "succeeded", res.errors

    # 1. Workflow YAML untouched.
    assert wf.read_text(encoding="utf-8") == wf_before
    # 2. No new scheduler node / output mutation.
    assert json.dumps(sched._block_outputs, sort_keys=True, default=str) == outputs_before
    # 3. No new run registered.
    assert set(runtime.workflow_runs.keys()) == run_ids_before
    # 4. No lineage DB created by the plot run.
    assert not (project / ".scistudio" / "lineage.db").exists()
    # 5. No downstream collection / data dir created beyond the preview cache.
    scistudio_children = {p.name for p in (project / ".scistudio").iterdir()}
    assert scistudio_children == {"previews"}, scistudio_children


# ---------------------------------------------------------------------------
# SC-010: artifact consumable by core.plot.basic PlotPreviewer.
# ---------------------------------------------------------------------------


def test_artifact_consumable_by_plot_previewer(setup: tuple[Path, _StubRuntime, Path]) -> None:
    _project, _runtime, _wf = setup
    res = _run(run_plot_job(plot_id="p1"))
    assert res.status == "succeeded", res.errors
    svg_path = res.artifact_paths[0]

    from scistudio.previewers.data_access import PreviewDataAccess
    from scistudio.previewers.fallbacks import plot_previewer
    from scistudio.previewers.models import (
        EnvelopeKind,
        OwnerKind,
        PreviewerSpec,
        PreviewLimits,
        PreviewRequest,
        PreviewTarget,
        TargetKind,
    )

    spec = PreviewerSpec(
        previewer_id="core.plot.basic",
        owner_kind=OwnerKind.CORE,
        owner_name="scistudio",
        target_type="PlotArtifact",
        backend_provider=plot_previewer,
    )
    target = PreviewTarget(kind=TargetKind.PLOT_ARTIFACT, ref=svg_path, recorded_type="PlotArtifact")
    request = PreviewRequest(
        target=target,
        spec=spec,
        query={"_storage": {"backend": "filesystem", "path": svg_path, "format": "svg"}},
        data_access=PreviewDataAccess(),
        limits=PreviewLimits(),
    )
    envelope = plot_previewer(request)
    assert envelope.kind == EnvelopeKind.PLOT, envelope
    assert envelope.payload.get("format") == "svg"
    # SVG path goes through the sanitizer and is embedded inline.
    assert "svg" in envelope.payload
    assert envelope.payload.get("sandboxed") is True


# ---------------------------------------------------------------------------
# FR-016: the plot script must receive the ACTUAL selected block-output
# collection — regression guard for the canonical Collection wire-form
# {"_collection": True, "items": [...], "item_type": "..."} produced by the
# worker/scheduler/checkpoint layers (not a bespoke "_collection_items" key).
# ---------------------------------------------------------------------------


def test_flatten_to_refs_reads_canonical_collection_wire_form() -> None:
    # The shape the engine actually emits in scheduler._block_outputs[node][port].
    wire = {
        "_collection": True,
        "item_type": "DataFrame",
        "items": [
            {
                "backend": "filesystem",
                "path": "/data/a.parquet",
                "format": "parquet",
                "metadata": {"type_chain": ["DataFrame"], "framework": {"object_id": "obj-a"}},
            },
            {
                "backend": "filesystem",
                "path": "/data/b.parquet",
                "format": "parquet",
                "metadata": {"type_chain": ["DataFrame"], "framework": {"object_id": "obj-b"}},
            },
        ],
    }
    refs, collection_ids = _flatten_to_refs(wire)
    # Both items resolved (NOT an empty collection).
    assert [r["path"] for r in refs] == ["/data/a.parquet", "/data/b.parquet"]
    assert collection_ids == ["obj-a", "obj-b"]


def test_flatten_to_refs_single_ref_and_legacy_alias() -> None:
    single = {"backend": "filesystem", "path": "/data/x.csv", "format": "csv"}
    refs, _ = _flatten_to_refs(single)
    assert [r["path"] for r in refs] == ["/data/x.csv"]
    legacy = {"_collection_items": [{"backend": "filesystem", "path": "/data/y.csv"}]}
    refs2, _ = _flatten_to_refs(legacy)
    assert [r["path"] for r in refs2] == ["/data/y.csv"]
