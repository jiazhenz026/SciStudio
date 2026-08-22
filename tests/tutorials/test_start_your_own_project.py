"""Core tutorial 6 — "Start your own project" (#2085, scenarios doc 关卡 6).

Two halves. The manifest half pins the shape the level was designed to — the
pretend-"your own" folder, the import trigger, results judged into
``data/processed``, a run scoped to its own step, and the export beat as an
honest continue — so a later edit that keeps the manifest valid but breaks the
design fails here with the design named. The generic conformance suite
(``test_core_tutorials.py``) already holds this tutorial to the schema, the
closed sets, and the asset checks by scanning the core directory; nothing from
it is repeated.

The session half walks the real shipped manifest end to end through the real
runtime against a real bootstrap project: bootstrap lands the pretend folder,
the trigger copies it into ``data/raw``, and every judged condition is driven
true the way the product would — canvas state, run records, files on disk, a
reported UI event — through the injected :class:`ProductState` port.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scistudio.tutorials import discovery
from scistudio.tutorials.actions import Action, CopyAction, WriteAction
from scistudio.tutorials.conditions import Condition, ExternalEventNames, RunSummary
from scistudio.tutorials.discovery import DiscoveryEnvironment
from scistudio.tutorials.manifest import (
    TutorialManifest,
    TutorialSourceKind,
    TutorialStep,
    load_manifest,
)
from scistudio.tutorials.progress import ProgressStore
from scistudio.tutorials.projects import TutorialKey, TutorialProjectPlan, tutorial_project_path
from scistudio.tutorials.session import SessionStatus, SessionStore, TutorialRuntime
from scistudio.workflow.definition import EdgeDef, NodeDef, WorkflowDefinition

from .conftest import StubProductState

TUTORIAL_ID = "start-your-own-project"
REAL_CORE_DIR = Path(__file__).resolve().parents[2] / "src" / "scistudio" / "tutorials" / "core"
TUTORIAL_DIR = REAL_CORE_DIR / TUTORIAL_ID


def _manifest() -> TutorialManifest:
    return load_manifest(TUTORIAL_DIR, source_kind=TutorialSourceKind.CORE)


def _actions_everywhere(manifest: TutorialManifest) -> list[Action]:
    """Every action the manifest declares — bootstrap, entry, *and* trigger.

    Deliberately wider than ``test_core_tutorials._actions``, which does not
    descend into ``step.trigger.do``: this level's central action is a
    trigger's, so the asset check here must reach it.
    """
    found: list[Action] = []
    if manifest.bootstrap is not None:
        found.extend(manifest.bootstrap.do)
    for step in manifest.steps:
        found.extend(step.do)
        if step.trigger is not None:
            found.extend(step.trigger.do)
    return found


def _leaves(condition: Condition) -> list[Condition]:
    if condition.is_combinator:
        return [leaf for operand in condition.operands for leaf in _leaves(operand)]
    return [condition]


def _step(manifest: TutorialManifest, step_id: str) -> TutorialStep:
    step = manifest.step_by_id(step_id)
    assert step is not None, f"the level no longer has a step {step_id!r}"
    return step


# ---------------------------------------------------------------------------
# The manifest half: the level's design, pinned
# ---------------------------------------------------------------------------


def test_the_level_is_hands_on_and_sits_last() -> None:
    manifest = _manifest()
    assert manifest.id == TUTORIAL_ID
    assert manifest.order == 6
    assert manifest.creates_project, "the level bootstraps the project the import happens in"
    assert not manifest.is_reading_only, "a level that walks a real import is not a reading tutorial"


def test_every_declared_asset_exists_including_the_triggers() -> None:
    """A missing asset breaks at the step that names it, minutes in.

    The scanning suite checks bootstrap and entry actions; the trigger's
    actions are checked only here.
    """
    manifest = _manifest()
    for action in _actions_everywhere(manifest):
        assert isinstance(action, (WriteAction, CopyAction)), f"unexpected action kind {action.kind!r}"
        resolved = manifest.resolve_asset(action.source)
        assert resolved.exists(), f"action source {action.source!r} does not exist at {resolved}"
        if isinstance(action, WriteAction):
            assert resolved.is_file()
        else:
            assert resolved.is_dir()


def test_the_pretend_folder_and_the_import_move_the_same_files() -> None:
    """The level's central trick, pinned.

    Bootstrap supplies the pretend-"your own" folder *inside* the tutorial
    project (a session goes dormant when the reader switches projects, so
    nothing may send them elsewhere), and the import trigger lands the same
    file set in ``data/raw`` — so what the reader watches happen is exactly
    the move the copy describes.
    """
    manifest = _manifest()
    assert manifest.bootstrap is not None
    (supply,) = manifest.bootstrap.do
    assert isinstance(supply, CopyAction)
    assert supply.destination == "incoming-example"

    import_step = _step(manifest, "import-your-files")
    assert import_step.trigger is not None, "the import is a do-it-with-me trigger, not narration"
    (move,) = import_step.trigger.do
    assert isinstance(move, CopyAction)
    assert move.destination == "data/raw"
    assert move.source == supply.source, "the trigger must move the files the bootstrap supplied"


def test_the_import_step_judges_the_copied_files_on_disk() -> None:
    import_step = _step(_manifest(), "import-your-files")
    assert import_step.done_when is not None
    leaves = _leaves(import_step.done_when)
    assert {leaf.term for leaf in leaves} == {"file_exists"}
    judged = {str(leaf.args["path"]) for leaf in leaves}
    assert judged == {"data/raw/growth_measurements.csv", "data/raw/notes.txt"}, (
        "the import judges the whole folder arriving, notes and all"
    )


def test_results_are_judged_into_data_processed() -> None:
    """Where results land is the level's second question, answered twice.

    The Save step judges the *reader's* move — the folder they browsed to —
    and the result step judges the file the run then left there.
    """
    manifest = _manifest()
    save_step = _step(manifest, "choose-where-results-land")
    assert save_step.done_when is not None
    (config,) = _leaves(save_step.done_when)
    assert config.term == "config_matches"
    assert config.args["block_type"] == "save_data"
    assert config.args["pattern"] == "data/processed"

    result_step = _step(manifest, "your-result-is-there")
    assert result_step.done_when is not None
    (landed,) = _leaves(result_step.done_when)
    assert landed.term == "file_exists"
    assert str(landed.args["path"]).startswith("data/processed/")


def test_the_run_step_only_accepts_a_run_started_on_it() -> None:
    run_step = _step(_manifest(), "run-it")
    assert run_step.done_when is not None
    (run,) = _leaves(run_step.done_when)
    assert run.term == "run_succeeded"
    assert run.args.get("since_step_entry") is True, (
        "a run finished earlier in the tutorial must not satisfy 'press Run' (#2066)"
    )


def test_the_export_beat_is_an_honest_continue() -> None:
    """No vocabulary term can see an export — the file lands outside the
    project, wherever the reader chose — so the step must not pretend to
    judge one."""
    export_step = _step(_manifest(), "export-or-lose-it")
    assert export_step.done_when is None
    assert export_step.say is not None and "cannot check" in export_step.say


def test_the_six_questions_each_have_a_step() -> None:
    """The owner's six questions, mapped to the steps that answer them.

    The map is the level's contract with its design (issue #2085); renaming a
    step is fine as long as the answer still exists and this map moves with
    it.
    """
    six_questions = {
        "where data goes in": ("the-four-buckets", "import-your-files"),
        "where results land": ("choose-where-results-land", "your-result-is-there"),
        "where the project's tools live": ("the-projects-own-tools",),
        "how data is exchanged with external software": ("the-exchange-folder",),
        "how a plot card exports a figure": ("export-or-lose-it",),
        "how data is saved": ("add-save", "choose-where-results-land"),
    }
    manifest = _manifest()
    step_ids = {step.id for step in manifest.steps}
    for question, answering_steps in six_questions.items():
        missing = set(answering_steps) - step_ids
        assert not missing, f"no step answers {question!r} any more: {sorted(missing)}"


# ---------------------------------------------------------------------------
# The session half: the shipped level, walked
# ---------------------------------------------------------------------------


class _Provisioner:
    """Creates a directory that counts as a project: a ``project.yaml``.

    The real provisioner also writes the known-projects entry, the FR-064
    marker, and the full scaffold; none of that is judged here — the level's
    own actions create every directory the walk touches.
    """

    def create(self, plan: TutorialProjectPlan) -> Path:
        plan.path.mkdir(parents=True, exist_ok=True)
        (plan.path / "project.yaml").write_text(f"name: {plan.name}\n", encoding="utf-8")
        return plan.path

    def delete(self, key: TutorialKey, path: Path) -> None:  # pragma: no cover - restart is not walked
        import shutil

        if path.is_dir():
            shutil.rmtree(path)


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    return fake_home


@pytest.fixture
def real_core_dir(monkeypatch: pytest.MonkeyPatch) -> Path:
    """Discovery over the *shipped* core tutorials, not a fixture copy.

    The point of the walk is that the manifest on disk — the one a reader
    gets — drives a session end to end.
    """
    monkeypatch.setattr(discovery, "core_tutorials_dir", lambda: REAL_CORE_DIR)
    return REAL_CORE_DIR


@pytest.fixture
def product() -> StubProductState:
    return StubProductState()


@pytest.fixture
def runtime(home: Path, real_core_dir: Path, product: StubProductState) -> TutorialRuntime:
    return TutorialRuntime(
        product_state=lambda: product,
        external_events=ExternalEventNames(blocks_reloaded="blocks.reloaded", file_changed="file.changed"),
        project_dir=lambda: product.project_dir,
        provisioner=_Provisioner(),
        environment=DiscoveryEnvironment(
            scistudio_version="0.3.1",
            installed_distributions=frozenset(),
            agent_available=False,
            git_available=True,
        ),
        progress=ProgressStore(home / ".scistudio"),
        sessions=SessionStore(home / ".scistudio"),
    )


def test_the_level_walks_end_to_end_against_a_real_bootstrap_project(
    runtime: TutorialRuntime, product: StubProductState
) -> None:
    """Every judged condition of the shipped manifest, driven true in order."""
    key = TutorialKey.core(TUTORIAL_ID)
    project = tutorial_project_path(key)
    product.project_dir = project

    view = runtime.start(key)

    # Bootstrap supplied the pretend-"your own" folder inside the project.
    assert view.status is SessionStatus.ACTIVE
    assert (project / "incoming-example" / "growth_measurements.csv").is_file()
    assert (project / "incoming-example" / "notes.txt").is_file()
    assert view.step is not None and view.step.id == "welcome"

    # Three reading steps open the level.
    view = runtime.continue_active()
    assert view.step is not None and view.step.id == "the-project-is-a-folder"
    view = runtime.continue_active()
    assert view.step is not None and view.step.id == "the-four-buckets"
    view = runtime.continue_active()

    # The import: nothing lands in data/raw until the reader presses the
    # button, and pressing it is what satisfies the step.
    assert view.step is not None and view.step.id == "import-your-files"
    assert view.step.trigger is not None
    assert view.step.trigger["label"] == "Copy my files into data/raw"
    assert not (project / "data" / "raw" / "growth_measurements.csv").exists()
    assert view.step.satisfied is False
    view = runtime.trigger_active()
    assert (project / "data" / "raw" / "growth_measurements.csv").is_file()
    assert (project / "data" / "raw" / "notes.txt").is_file()
    assert view.step is not None and view.step.satisfied is True
    view = runtime.continue_active()

    # Load: judged against the canvas, which the stub plays.
    assert view.step is not None and view.step.id == "load-your-file"
    assert view.step.satisfied is False
    nodes: list[NodeDef] = [NodeDef(id="load-1", block_type="load_data", config={})]
    edges: list[EdgeDef] = []

    def canvas() -> WorkflowDefinition:
        return WorkflowDefinition(id="wf", nodes=list(nodes), edges=list(edges))

    product.workflow_definition = canvas()
    view = runtime.evaluate_active()
    assert view.step is not None and view.step.satisfied is True
    view = runtime.continue_active()

    assert view.step is not None and view.step.id == "point-load-at-your-file"
    nodes[0] = NodeDef(id="load-1", block_type="load_data", config={"path": "data/raw/growth_measurements.csv"})
    product.workflow_definition = canvas()
    view = runtime.evaluate_active()
    assert view.step is not None and view.step.satisfied is True
    view = runtime.continue_active()

    # Entering the tools step wrote the block into the project's blocks/ —
    # before its text was readable (FR-059).
    assert view.step is not None and view.step.id == "the-projects-own-tools"
    assert (project / "blocks" / "summarize_growth.py").is_file()
    nodes.append(NodeDef(id="sum-1", block_type="summarize_growth", config={}))
    edges.append(EdgeDef(source="load-1:table", target="sum-1:table"))
    product.workflow_definition = canvas()
    view = runtime.evaluate_active()
    assert view.step is not None and view.step.satisfied is True
    view = runtime.continue_active()

    assert view.step is not None and view.step.id == "add-save"
    nodes.append(NodeDef(id="save-1", block_type="save_data", config={}))
    edges.append(EdgeDef(source="sum-1:summary", target="save-1:table"))
    product.workflow_definition = canvas()
    view = runtime.evaluate_active()
    assert view.step is not None and view.step.satisfied is True
    view = runtime.continue_active()

    assert view.step is not None and view.step.id == "choose-where-results-land"
    nodes[-1] = NodeDef(
        id="save-1",
        block_type="save_data",
        config={"path": "data/processed", "filename": "growth_summary.csv"},
    )
    product.workflow_definition = canvas()
    view = runtime.evaluate_active()
    assert view.step is not None and view.step.satisfied is True

    # A run recorded before the Run step is entered must not satisfy it.
    product.runs = (
        RunSummary(run_id="run-0", workflow_id="wf", succeeded=True, started_at="2000-01-01T00:00:00+00:00"),
    )
    view = runtime.continue_active()
    assert view.step is not None and view.step.id == "run-it"
    assert view.step.satisfied is False, "a stale run must not satisfy since_step_entry (#2066)"
    product.runs += (
        RunSummary(run_id="run-1", workflow_id="wf", succeeded=True, started_at="2999-01-01T00:00:00+00:00"),
    )
    view = runtime.evaluate_active()
    assert view.step is not None and view.step.satisfied is True
    view = runtime.continue_active()

    # The saved result: the walk plays the Save block's part, because the
    # step judges the file the reader's run leaves in data/processed.
    assert view.step is not None and view.step.id == "your-result-is-there"
    assert view.step.satisfied is False
    result = project / "data" / "processed" / "growth_summary.csv"
    result.parent.mkdir(parents=True, exist_ok=True)
    result.write_text("sample,fold_change\nculture_a,8.17\n", encoding="utf-8")
    view = runtime.evaluate_active()
    assert view.step is not None and view.step.satisfied is True
    view = runtime.continue_active()

    assert view.step is not None and view.step.id == "the-exchange-folder"
    assert view.step.awaiting_continue is True
    view = runtime.continue_active()

    assert view.step is not None and view.step.id == "make-a-plot"
    product.plots = (("growth_curves", "load-1", "table"),)
    view = runtime.evaluate_active()
    assert view.step is not None and view.step.satisfied is True
    view = runtime.continue_active()

    # Entering the render step wrote the plot script; the render itself is a
    # frontend fact, reported as the targeted ui_event the condition names.
    assert view.step is not None and view.step.id == "render-it"
    assert (project / "plots" / "growth_curves" / "render.py").is_file()
    product.targeted_events = frozenset({("plot_rendered", "growth_curves")})
    view = runtime.evaluate_active()
    assert view.step is not None and view.step.satisfied is True
    view = runtime.continue_active()

    # The export beat: nothing to judge, and the step says so.
    assert view.step is not None and view.step.id == "export-or-lose-it"
    assert view.step.awaiting_continue is True
    view = runtime.continue_active()

    assert view.step is not None and view.step.id == "your-own-project"
    view = runtime.continue_active()
    assert view.status is SessionStatus.COMPLETE
    assert runtime.progress_store.is_completed(key)
