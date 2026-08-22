"""Core tutorial 4 — the declared-fake AI session — held to its own claims.

``test_core_tutorials.py`` already applies the format-level conformance every
shipped tutorial gets. This file checks what only tutorial 4 promises
(#2083, scenarios doc 关卡 4):

* the beat order and each beat's judged condition survive edits;
* the science is real: the shipped QC block against the shipped plate table
  keeps 44 of 48 samples at 3 sigma and 40 at 2 — the exact numbers the
  transcript quotes — and the planted mistake fails with the exact visible
  ``KeyError`` the debug beat reads out of the logs;
* the transcript cannot drift from the data, because every quoted number is
  asserted against a fresh computation;
* the tutorial-only AI Block is a *real* ``AIBlock`` subclass whose category
  is inferred from the class hierarchy — the property the scenarios doc calls
  out as unfakeable — and its canned run produces a typed table covering
  every column the undocumented files ship;
* the conversation pacing is the continue-tab form: one tab opened by the
  first reply, every later reply appended to it (FR-061b, #2089).
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

from scistudio.blocks.base import BlockConfig
from scistudio.tutorials.actions import ReplayAction, WriteAction, iter_file_actions
from scistudio.tutorials.manifest import TutorialManifest, TutorialSourceKind, load_manifest

TUTORIAL_DIR = Path(__file__).resolve().parents[2] / "src" / "scistudio" / "tutorials" / "core" / "what-ai-can-do"
ASSETS = TUTORIAL_DIR / "assets"

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


@pytest.fixture(scope="module")
def manifest() -> TutorialManifest:
    return load_manifest(TUTORIAL_DIR, source_kind=TutorialSourceKind.CORE)


def _load_block_module(filename: str) -> ModuleType:
    """Import a shipped block asset under a drop-in-style module name.

    The synthetic ``_scistudio_dropin_`` prefix is what the real project scan
    uses, and it is what lets ``_spec_from_class`` stamp the SciStudio version
    instead of failing to resolve a distribution for an ad-hoc module.
    """
    path = ASSETS / "code" / filename
    name = f"_scistudio_dropin_test_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _frame(df: Any, tmp_path: Path, name: str) -> Any:
    """A storage-backed DataFrame, the shape ``to_memory`` requires."""
    import pyarrow as pa

    from scistudio.core.types import DataFrame

    obj = DataFrame(data=pa.Table.from_pandas(df, preserve_index=False))
    obj.save(tmp_path / name)
    return obj


def _plate(tmp_path: Path) -> Any:
    import pandas as pd

    return _frame(pd.read_csv(ASSETS / "data" / "plate_measurements.csv"), tmp_path, "plate.arrow")


def _live_step(view: Any) -> Any:
    """The view's step, asserted present — ``SessionView.step`` is optional."""
    assert view is not None and view.step is not None
    return view.step


def _segment_text(name: str) -> str:
    raw = (ASSETS / "replay" / f"{name}.txt").read_bytes().decode("utf-8")
    return _ANSI.sub("", raw).replace("\r\n", "\n")


# ---------------------------------------------------------------------------
# The beat map
# ---------------------------------------------------------------------------


def test_the_beat_map_is_the_designed_one(manifest: TutorialManifest) -> None:
    """Beat -> step -> condition, as dispatched. A reorder or a swapped judge fails here."""
    expected = [
        ("welcome", None),
        ("ask-what-scistudio-is", {"file_exists"}),
        ("ask-what-it-can-see", {"file_exists"}),
        ("ask-for-a-qc-block", {"block_registered"}),
        ("watch-it-assemble", {"node_exists", "edge_exists"}),
        ("run-and-hit-the-wall", {"run_failed"}),
        ("let-it-debug", {"file_exists"}),
        ("run-it-again", {"run_succeeded"}),
        ("look-for-yourself", {"file_exists", "ui_event"}),
        ("tighten-the-threshold", {"file_exists", "config_equals"}),
        ("run-at-two-sigma", {"run_succeeded"}),
        ("plot-the-cut", {"plot_rendered"}),
        ("one-more-trick", {"node_exists", "run_succeeded"}),
        ("where-the-real-agents-live", None),
    ]
    actual = [(step.id, set(step.done_when.terms()) if step.done_when is not None else None) for step in manifest.steps]
    assert actual == expected


def test_the_break_and_the_fix_are_scoped_to_their_own_steps(manifest: TutorialManifest) -> None:
    """The run terms carry ``since_step_entry`` (#2066), so an old run cannot satisfy them."""
    for step_id in ("run-and-hit-the-wall", "run-it-again", "run-at-two-sigma"):
        step = manifest.step_by_id(step_id)
        assert step is not None and step.done_when is not None

        def _walk(condition: Any) -> list[dict[str, Any]]:
            if condition.is_combinator:
                return [arg for operand in condition.operands for arg in _walk(operand)]
            return [dict(condition.args)] if condition.term in ("run_failed", "run_succeeded") else []

        run_args = _walk(step.done_when)
        assert run_args, f"{step_id} judges no run term"
        assert all(args.get("since_step_entry") is True for args in run_args), (
            f"{step_id}'s run condition must be scoped to runs started on this step"
        )


def test_the_conversation_continues_one_tab(manifest: TutorialManifest) -> None:
    """First reply opens the tab; every later reply appends to it (#2089)."""
    replays: list[ReplayAction] = []
    for step in manifest.steps:
        if step.trigger is None:
            continue
        for action in step.trigger.do:
            if isinstance(action, ReplayAction):
                replays.append(action)
    assert len(replays) == 9
    assert all(action.surface == "ai_chat_terminal" for action in replays)
    assert replays[0].continue_tab is False, "the first reply opens the tab"
    assert all(action.continue_tab for action in replays[1:]), "every later reply continues it"
    assert all(len(action.segments) == 1 for action in replays), "one press, one reply"


def test_every_file_exists_judge_is_written_by_its_own_trigger(manifest: TutorialManifest) -> None:
    """FR-061b honesty: the press writes exactly the file the step waits on."""
    for step in manifest.steps:
        if step.done_when is None or step.trigger is None:
            continue

        def _paths(condition: Any) -> list[str]:
            if condition.is_combinator:
                return [path for operand in condition.operands for path in _paths(operand)]
            return [condition.args["path"]] if condition.term == "file_exists" else []

        waited_on = _paths(step.done_when)
        written = {action.destination for action in iter_file_actions(step.trigger.do)}
        for path in waited_on:
            assert path in written, f"step {step.id!r} waits on {path!r} but its trigger does not write it"


# ---------------------------------------------------------------------------
# The science, computed fresh
# ---------------------------------------------------------------------------


def test_the_broken_block_fails_with_the_visible_keyerror(tmp_path: Path) -> None:
    """The planted mistake is a KeyError naming the wrong column — the loggable kind."""
    module = _load_block_module("qc_outlier_filter_broken.py")
    block = module.QcOutlierFilterBlock()
    with pytest.raises(KeyError, match="fluorescence"):
        block.process_item(_plate(tmp_path), BlockConfig(params={"sigma_threshold": 3}))


def test_the_fix_is_exactly_one_constant(manifest: TutorialManifest) -> None:
    """The broken and fixed sources differ in METRIC_COLUMN and nothing else."""
    broken = (ASSETS / "code" / "qc_outlier_filter_broken.py").read_text(encoding="utf-8")
    fixed = (ASSETS / "code" / "qc_outlier_filter.py").read_text(encoding="utf-8")
    assert broken != fixed
    assert broken.replace('METRIC_COLUMN = "fluorescence"', 'METRIC_COLUMN = "fluorescence_au"') == fixed


@pytest.mark.parametrize(
    ("threshold", "kept", "flagged"),
    [
        (3, 44, {"S05", "S13", "S27", "S35"}),
        (2, 40, {"S05", "S10", "S13", "S22", "S27", "S31", "S35", "S42"}),
    ],
)
def test_the_qc_numbers_the_transcript_quotes(tmp_path: Path, threshold: int, kept: int, flagged: set[str]) -> None:
    """44 of 48 at 3 sigma, 40 at 2 — recomputed from the shipped data every run."""
    module = _load_block_module("qc_outlier_filter.py")
    block = module.QcOutlierFilterBlock()
    out = block.process_item(_plate(tmp_path), BlockConfig(params={"sigma_threshold": threshold}))
    table = out.get_in_memory_data().to_pandas()
    assert len(table) == 48, "the QC block flags; it never drops rows"
    assert int(table["qc_keep"].sum()) == kept
    assert set(table.loc[~table["qc_keep"], "sample_id"]) == flagged


def test_the_summary_block_reports_the_retained_count(tmp_path: Path) -> None:
    module = _load_block_module("qc_outlier_filter.py")
    summarize = _load_block_module("summarize_metrics.py").SummarizeMetricsBlock()
    annotated = module.QcOutlierFilterBlock().process_item(_plate(tmp_path), BlockConfig(params={"sigma_threshold": 3}))
    annotated.save(tmp_path / "annotated.arrow")
    summary = summarize.process_item(annotated, BlockConfig()).get_in_memory_data().to_pandas()
    fluor = summary[summary["metric"] == "fluorescence_au"].iloc[0]
    assert fluor["n_total"] == 48
    assert fluor["n_kept"] == 44
    # The qc_* bookkeeping columns are not metrics.
    assert not any(str(metric).startswith("qc_") for metric in summary["metric"])


def test_the_transcript_numbers_match_the_data() -> None:
    """The replies quote retained counts and z-scores; the data must agree.

    The counts themselves are pinned by the recomputation test above; this one
    pins the *transcript* to those counts, so editing either side alone fails.
    """
    inspect = _segment_text("06-inspect")
    assert "44 of 48" in inspect
    assert "+99.2" in inspect and "-13.7" in inspect

    threshold = _segment_text("07-threshold")
    assert "40 of 48" in threshold
    for quoted in ("S10 +2.1", "S22 +2.2", "S31 -2.1", "S42 +2.4"):
        assert quoted in threshold, f"the threshold reply no longer quotes {quoted!r}"

    debug = _segment_text("05-debug")
    assert "KeyError: 'fluorescence'" in debug
    assert "fluorescence_au" in debug

    again = None
    for step in load_manifest(TUTORIAL_DIR, source_kind=TutorialSourceKind.CORE).steps:
        if step.id == "run-it-again":
            again = step.say
    assert again is not None and "44 of" in again


def test_every_log_twin_matches_its_segment() -> None:
    """The clean project log is the segment's own text, escapes stripped."""
    log_dir = ASSETS / "replay" / "log"
    twins = sorted(log_dir.glob("*.txt"))
    assert [twin.name for twin in twins] == [
        "01-what-is-scistudio.txt",
        "02-list-blocks.txt",
        "05-debug.txt",
        "06-inspect.txt",
        "07-threshold.txt",
    ]
    for twin in twins:
        segment = _segment_text(twin.stem)
        assert segment.rstrip("\n") == twin.read_text(encoding="utf-8").rstrip("\n"), (
            f"{twin.name} drifted from its replay segment"
        )


# ---------------------------------------------------------------------------
# The tutorial-only AI Block
# ---------------------------------------------------------------------------


def test_the_tutorial_ai_block_is_a_real_aiblock(tmp_path: Path) -> None:
    """Inheritance is the unfakeable part: category comes from the class walk."""
    from scistudio.blocks.ai.ai_block import AIBlock
    from scistudio.blocks.registry._spec import _infer_category, _spec_from_class

    module = _load_block_module("tutorial_ai_agent.py")
    cls = module.TutorialAiAgentBlock
    assert issubclass(cls, AIBlock)
    assert _infer_category(cls) == "ai"

    spec = _spec_from_class(cls, source="custom")
    assert spec.type_name == "tutorial_ai_agent"
    assert spec.name == "AI Block (tutorial only)"
    assert spec.base_category == "ai"


def test_the_canned_run_covers_every_shipped_column(tmp_path: Path) -> None:
    """One typed row per (table, column), and no shipped column falls back to 'unknown'."""
    import pandas as pd

    from scistudio.core.types import Collection, DataFrame

    module = _load_block_module("tutorial_ai_agent.py")
    block = module.TutorialAiAgentBlock()

    files = sorted((ASSETS / "data" / "undocumented").glob("*.csv"))
    assert [path.name for path in files] == ["mmx_007.csv", "mmx_012.csv", "plate2_export.csv"]
    frames = [pd.read_csv(path) for path in files]
    items = [_frame(frame, tmp_path, f"{index}.arrow") for index, frame in enumerate(frames)]

    result = block.run({"data": Collection(items)}, BlockConfig(params={}))
    collection = result["result"]
    assert len(collection) == 1
    output = next(iter(collection))
    assert isinstance(output, DataFrame)

    table = output.get_in_memory_data().to_pandas()
    expected_rows = sum(len(frame.columns) for frame in frames)
    assert len(table) == expected_rows
    assert not table["inferred_meaning"].str.startswith("unknown").any(), (
        "a shipped column has no canned inference; the demo would answer 'unknown'"
    )
    # Observed facts are computed from the real files, not canned.
    t_row = table[(table["table"] == 1) & (table["column"] == "t")].iloc[0]
    assert t_row["observed_min"] == 0 and t_row["observed_max"] == 450


def test_the_canned_run_refuses_an_empty_input(tmp_path: Path) -> None:
    from scistudio.core.types import Collection, DataFrame

    module = _load_block_module("tutorial_ai_agent.py")
    with pytest.raises(ValueError, match="at least one input table"):
        module.TutorialAiAgentBlock().run({"data": Collection([], item_type=DataFrame)}, BlockConfig(params={}))


# ---------------------------------------------------------------------------
# The seeded workflows and the plot
# ---------------------------------------------------------------------------


def _workflow(name: str) -> Any:
    from scistudio.workflow.schema import WorkflowFileModel

    data = yaml.safe_load((ASSETS / "workflows" / name).read_text(encoding="utf-8"))
    return WorkflowFileModel.model_validate(data).workflow.to_definition()


def test_the_seeded_workflows_parse_and_stay_consistent(manifest: TutorialManifest) -> None:
    base = _workflow("main.yaml")
    extended = _workflow("main-with-metadata.yaml")

    assert [node.id for node in base.nodes] == ["load-plate", "qc-filter", "summarize", "save-summary"]
    assert [node.id for node in extended.nodes][:4] == [node.id for node in base.nodes]
    assert [node.id for node in extended.nodes][4:] == ["load-mystery", "ai-metadata"]

    def _threshold(definition: Any) -> float:
        node = next(node for node in definition.nodes if node.id == "qc-filter")
        return float(node.config["params"]["sigma_threshold"])

    # The base graph starts at the conservative 3; the extended rewrite must
    # carry the 2 the tighten-the-threshold step judged, or the agent's edit
    # would clobber the reader's own decision.
    assert _threshold(base) == 3
    assert _threshold(extended) == 2

    step = manifest.step_by_id("tighten-the-threshold")
    assert step is not None and step.done_when is not None

    def _config_value(condition: Any) -> Any:
        if condition.is_combinator:
            for operand in condition.operands:
                found = _config_value(operand)
                if found is not None:
                    return found
            return None
        return condition.args.get("value") if condition.term == "config_equals" else None

    assert _config_value(step.done_when) == _threshold(extended)


def test_the_seeded_workflows_reference_only_shipped_or_builtin_blocks() -> None:
    builtins = {
        "load_data",
        "save_data",
        "ai.agent",
        "subworkflow_block",
        "code_block",
        "app_block",
        "datarouter_block",
        "mergecollection_block",
        "paireditor_block",
    }
    shipped = {"qc_outlier_filter", "summarize_metrics", "tutorial_ai_agent"}
    for name in ("main.yaml", "main-with-metadata.yaml"):
        for node in _workflow(name).nodes:
            assert node.block_type in builtins | shipped, f"{name}: unknown block_type {node.block_type!r}"


def test_the_plot_binds_the_qc_output(manifest: TutorialManifest) -> None:
    from scistudio.plot.models import PlotManifest

    data = yaml.safe_load((ASSETS / "code" / "qc_before_after" / "plot.yaml").read_text(encoding="utf-8"))
    plot = PlotManifest.model_validate(data)
    assert plot.id == "qc_before_after"
    assert plot.target.workflow_path == "workflows/main.yaml"
    assert plot.target.node_id == "qc-filter"
    assert plot.target.output_port == "annotated"

    # The step waits on this plot id; the two files sit in one trigger.
    step = manifest.step_by_id("plot-the-cut")
    assert step is not None and step.done_when is not None
    assert step.done_when.args["plot_id"] == plot.id
    assert step.trigger is not None
    written = {action.destination for action in iter_file_actions(step.trigger.do) if isinstance(action, WriteAction)}
    assert written == {"plots/qc_before_after/plot.yaml", "plots/qc_before_after/render.py"}


def test_the_render_draws_the_two_sigma_cut(tmp_path: Path) -> None:
    """The shipped render script against the shipped data: 40 of 48 in the title."""
    import matplotlib

    matplotlib.use("Agg")

    module = _load_block_module("qc_outlier_filter.py")
    annotated = (
        module.QcOutlierFilterBlock()
        .process_item(_plate(tmp_path), BlockConfig(params={"sigma_threshold": 2}))
        .get_in_memory_data()
        .to_pandas()
    )

    spec = importlib.util.spec_from_file_location("_t4_render", ASSETS / "code" / "qc_before_after" / "render.py")
    assert spec is not None and spec.loader is not None
    render_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(render_module)

    class _Items:
        def __init__(self, frame: Any) -> None:
            self._frame = frame

        def open_one(self) -> Any:
            return self._frame

    class _Collection:
        def __init__(self, frame: Any) -> None:
            self.items = _Items(frame)

    figure = render_module.render(_Collection(annotated))
    try:
        assert figure.axes[0].get_title() == "QC: 40 of 48 samples kept"
    finally:
        import matplotlib.pyplot as plt

        plt.close(figure)


# ---------------------------------------------------------------------------
# The whole session, walked through the real runtime
# ---------------------------------------------------------------------------


def test_the_whole_tutorial_walks_through_the_real_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every beat of the real manifest, driven end to end (#2083).

    The runtime, the session store, the progress store, the replay sequencing
    and the milestone unlock are all the real ones; only the product-state
    port and the byte sink are stood in, exactly as the API layer stands them
    in. The walk asserts the two properties the level exists for: one terminal
    tab carries the whole conversation in order, and finishing the tutorial —
    and nothing before finishing it — makes the work-import offer pending.
    """
    import ast as _ast
    import shutil
    from dataclasses import dataclass
    from datetime import UTC, datetime, timedelta

    from scistudio.tutorials import discovery
    from scistudio.tutorials.conditions import ExternalEventNames, RunSummary
    from scistudio.tutorials.discovery import DiscoveryEnvironment
    from scistudio.tutorials.progress import ProgressStore
    from scistudio.tutorials.projects import TutorialKey, TutorialProjectPlan
    from scistudio.tutorials.session import SessionStatus, SessionStore, TutorialRuntime
    from scistudio.workflow.schema import WorkflowFileModel

    from .conftest import StubProductState

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    monkeypatch.setattr(discovery, "core_tutorials_dir", lambda: TUTORIAL_DIR.parent)

    @dataclass
    class _ProjectBackedState(StubProductState):
        """Reads the workflow off the project file, the way the product does."""

        def workflow(self) -> Any:
            self.reads.append("workflow")
            if self.project_dir is None:
                return None
            path = Path(self.project_dir) / "workflows" / "main.yaml"
            if not path.is_file():
                return None
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            return WorkflowFileModel.model_validate(data).workflow.to_definition()

    class _Provisioner:
        def create(self, plan: TutorialProjectPlan) -> Path:
            plan.path.mkdir(parents=True, exist_ok=True)
            (plan.path / "project.yaml").write_text(f"name: {plan.name}\n", encoding="utf-8")
            return plan.path

        def delete(self, key: TutorialKey, path: Path) -> None:
            if path.is_dir():
                shutil.rmtree(path)

    class _Handle:
        """The byte sink, recording delivery order (FR-061b)."""

        def __init__(self, tab_id: str) -> None:
            self.surface = "ai_chat_terminal"
            self.tab_id = tab_id
            self.delivered: list[str] = []
            self.closed = False

        @property
        def is_open(self) -> bool:
            return not self.closed

        def deliver(self, segment: Any, payload: bytes) -> None:
            assert payload, "a segment delivered no bytes"
            self.delivered.append(segment.id)

        def close(self) -> None:
            self.closed = True

    product = _ProjectBackedState()
    handles: list[_Handle] = []

    def _open(surface: str) -> _Handle:
        handle = _Handle(f"tab-{len(handles) + 1}")
        handles.append(handle)
        return handle

    def _settle(written: Any) -> None:
        """The API layer's registry re-scan, reduced to what conditions read."""
        registered = set(product.block_types)
        for path in written:
            path = Path(path)
            if path.suffix == ".py" and path.parent.name == "blocks":
                tree = _ast.parse(path.read_text(encoding="utf-8"))
                for cls in (node for node in tree.body if isinstance(node, _ast.ClassDef)):
                    for node in cls.body:
                        if (
                            isinstance(node, _ast.AnnAssign)
                            and isinstance(node.target, _ast.Name)
                            and node.target.id == "type_name"
                            and isinstance(node.value, _ast.Constant)
                        ):
                            registered.add(str(node.value.value))
        product.block_types = frozenset(registered)

    def _record_event(name: str, target: str | None) -> None:
        product.events = product.events | {name}
        if target is not None:
            product.targeted_events = product.targeted_events | {(name, target)}

    def _forget_events() -> None:
        product.events = frozenset()
        product.targeted_events = frozenset()

    runtime = TutorialRuntime(
        product_state=lambda: product,
        external_events=ExternalEventNames(blocks_reloaded="blocks.reloaded", file_changed="file.changed"),
        project_dir=lambda: product.project_dir,
        provisioner=_Provisioner(),
        environment=DiscoveryEnvironment(scistudio_version="0.3.1", git_available=True),
        progress=ProgressStore(fake_home / ".scistudio"),
        sessions=SessionStore(fake_home / ".scistudio"),
        open_replay=_open,
        record_ui_event=_record_event,
        forget_ui_events=_forget_events,
        files_written=_settle,
    )

    def _run(succeeded: bool, *, nodes: frozenset[str] = frozenset()) -> None:
        """Prepend a run record started comfortably after the step was entered."""
        started = (datetime.now(UTC) + timedelta(seconds=5)).isoformat()
        record = RunSummary(
            run_id=f"r{len(product.runs) + 1}",
            workflow_id="main",
            succeeded=succeeded,
            succeeded_node_ids=nodes,
            started_at=started,
        )
        product.runs = (record, *product.runs)

    view = runtime.start(TutorialKey.core("what-ai-can-do"))
    assert view.step is not None and view.step.id == "welcome"
    project = Path(view.project_path or "")
    product.project_dir = project
    assert (project / "data" / "raw" / "plate_measurements.csv").is_file()
    assert (project / "data" / "raw" / "undocumented" / "mmx_007.csv").is_file()

    def _advance(expect: str) -> Any:
        moved = runtime.continue_active()
        assert moved.step is not None and moved.step.id == expect, (
            f"expected {expect!r}, on {moved.step.id if moved.step else None!r}"
        )
        return moved

    # welcome is a reading step.
    _advance("ask-what-scistudio-is")
    assert _live_step(runtime.trigger_active()).satisfied is True
    assert (project / "data" / "agent_log" / "01-what-is-scistudio.txt").is_file()

    _advance("ask-what-it-can-see")
    assert _live_step(runtime.trigger_active()).satisfied is True

    _advance("ask-for-a-qc-block")
    view = runtime.trigger_active()
    assert _live_step(view).satisfied is True, "settle registered the block before the press reported done"
    written = (project / "blocks" / "qc_outlier_filter.py").read_text(encoding="utf-8")
    assert 'METRIC_COLUMN = "fluorescence"' in written, "the planted mistake ships first"

    _advance("watch-it-assemble")
    view = runtime.trigger_active()
    assert _live_step(view).satisfied is True, "the seeded workflow satisfies the node and edge conditions"
    assert (project / "workflows" / "main.yaml").is_file()

    _advance("run-and-hit-the-wall")
    assert _live_step(runtime.active_session()).satisfied is False, "no run has started since entry (FR-054 + #2066)"
    _run(succeeded=False)
    assert _live_step(runtime.evaluate_active()).satisfied is True

    _advance("let-it-debug")
    view = runtime.trigger_active()
    assert _live_step(view).satisfied is True
    fixed = (project / "blocks" / "qc_outlier_filter.py").read_text(encoding="utf-8")
    assert 'METRIC_COLUMN = "fluorescence_au"' in fixed, "the agent's fix landed"

    _advance("run-it-again")
    _run(succeeded=True)
    assert _live_step(runtime.evaluate_active()).satisfied is True

    _advance("look-for-yourself")
    view = runtime.trigger_active()
    assert _live_step(view).satisfied is False, "the agent's own summary is not the reader's look"
    view = runtime.report_ui_event("node_selected", "qc_outlier_filter")
    assert _live_step(view).satisfied is True

    _advance("tighten-the-threshold")
    view = runtime.trigger_active()
    assert _live_step(view).satisfied is False, "the recommendation alone does not change the config"
    # The reader edits the QC node's settings; the editor persists to the file.
    workflow_path = project / "workflows" / "main.yaml"
    data = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    for node in data["workflow"]["nodes"]:
        if node["id"] == "qc-filter":
            node["config"]["params"]["sigma_threshold"] = 2
    workflow_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    assert _live_step(runtime.evaluate_active()).satisfied is True

    _advance("run-at-two-sigma")
    _run(succeeded=True)
    assert _live_step(runtime.evaluate_active()).satisfied is True

    _advance("plot-the-cut")
    view = runtime.trigger_active()
    assert (project / "plots" / "qc_before_after" / "plot.yaml").is_file()
    assert (project / "plots" / "qc_before_after" / "render.py").is_file()
    assert _live_step(view).satisfied is False, "the files exist; the figure does not yet"
    product.rendered = (("main", "qc-filter", "annotated", "qc_before_after"),)
    assert _live_step(runtime.evaluate_active()).satisfied is True

    _advance("one-more-trick")
    view = runtime.trigger_active()
    assert (project / "blocks" / "tutorial_ai_agent.py").is_file()
    assert _live_step(view).satisfied is False, "the node exists; its run has not happened"
    _run(succeeded=True, nodes=frozenset({"ai-metadata"}))
    assert _live_step(runtime.evaluate_active()).satisfied is True

    _advance("where-the-real-agents-live")
    assert runtime.progress_store.work_import_offer_pending() is False, "no offer before the finish"

    finished = runtime.continue_active()
    assert finished.status is SessionStatus.COMPLETE

    # The milestone fired through the shipped default — no configuration set.
    assert runtime.progress_store.work_import_offer_pending() is True

    # One tab carried the whole conversation, in script order (FR-061b, #2089).
    assert len(handles) == 1
    assert handles[0].delivered == [
        "what-is-scistudio",
        "list-blocks",
        "qc-block",
        "assemble",
        "debug",
        "inspect",
        "threshold",
        "plot",
        "ai-block",
    ]
    # Completion tore the scripted session down (FR-061c).
    assert handles[0].closed is True
