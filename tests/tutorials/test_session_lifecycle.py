"""The session: one at a time, restart-proof, and contained when it fails.

``docs/specs/adr-053-learning-center.md`` FR-036, FR-037, FR-043, FR-044,
FR-054, FR-059, FR-060, FR-066, FR-069, FR-090, and spec §4.4's Session row.
Most of the spec's Edge Cases list lands here: a package uninstalled
mid-session, a tutorial project deleted outside the product, a condition
satisfied while the Learning Center is closed, and a frontend that disconnects.

Nothing in this file constructs a FastAPI app. The session reaches product
truth, project creation, and byte delivery through injected ports, which is
what keeps ``api -> tutorials`` a one-way edge (checklist §6.1.2).
"""

from __future__ import annotations

import importlib.metadata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from scistudio.tutorials import discovery
from scistudio.tutorials.actions import ActionExecutionError
from scistudio.tutorials.conditions import ExternalEventNames
from scistudio.tutorials.discovery import DiscoveryEnvironment
from scistudio.tutorials.progress import ProgressStore
from scistudio.tutorials.projects import TutorialKey, TutorialProjectPlan, tutorial_project_path
from scistudio.tutorials.session import (
    AnotherSessionActiveError,
    SessionInvalidatedError,
    SessionStatus,
    SessionStore,
    TutorialRuntime,
    TutorialUnavailableError,
)
from scistudio.workflow.definition import NodeDef, WorkflowDefinition

from .conftest import StubProductState, write_tutorial

_LOAD_NODE = {"node_exists": {"block_type": "LoadCSV"}}


# ---------------------------------------------------------------------------
# Ports the API layer owns, stood in for here
# ---------------------------------------------------------------------------


class _Provisioner:
    """Creates a directory that :func:`tutorial_project_exists` recognises.

    A real provisioner also writes the known-projects entry and the FR-064
    marker; none of that is this file's subject, and a ``project.yaml`` is what
    "the project is still there" means to every other part of the product.
    """

    def __init__(self) -> None:
        self.created: list[Path] = []
        self.deleted: list[Path] = []

    def create(self, plan: TutorialProjectPlan) -> Path:
        plan.path.mkdir(parents=True, exist_ok=True)
        (plan.path / "project.yaml").write_text(f"name: {plan.name}\n", encoding="utf-8")
        self.created.append(plan.path)
        return plan.path

    def delete(self, key: TutorialKey, path: Path) -> None:
        self.deleted.append(path)
        if path.is_dir():
            import shutil

            shutil.rmtree(path)


@dataclass
class _BreakableWorkflowState(StubProductState):
    """Product state whose workflow is read from disk, as the real one is.

    The workflow holds a ``LoadCSV`` node until a marker file appears, which is
    how a *step's own action* can change the answer its condition gives — the
    thing a purely in-memory stub cannot express and the thing the entry
    ordering turns on.
    """

    broken_marker: Path | None = None

    def workflow(self) -> WorkflowDefinition | None:
        self.reads.append("workflow")
        if self.broken_marker is not None and self.broken_marker.exists():
            return WorkflowDefinition(id="wf", nodes=[], edges=[])
        return WorkflowDefinition(id="wf", nodes=[NodeDef(id="load-1", block_type="LoadCSV", config={})], edges=[])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    return fake_home


@pytest.fixture
def core_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "core-tutorials"
    directory.mkdir()
    monkeypatch.setattr(discovery, "core_tutorials_dir", lambda: directory)
    return directory


@pytest.fixture
def packages(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """A mutable list of entry points, so a package can be uninstalled mid-test."""
    installed: list[Any] = []

    def _entry_points(*_args: object, **kwargs: object) -> tuple[Any, ...]:
        return tuple(installed) if kwargs.get("group") == "scistudio.tutorials" else ()

    monkeypatch.setattr(importlib.metadata, "entry_points", _entry_points)
    return installed


@pytest.fixture
def product() -> StubProductState:
    return StubProductState()


@pytest.fixture
def provisioner() -> _Provisioner:
    return _Provisioner()


@pytest.fixture
def environment() -> DiscoveryEnvironment:
    return DiscoveryEnvironment(
        scistudio_version="0.3.1",
        installed_distributions=frozenset({"scistudio-blocks-demo"}),
        agent_available=True,
        git_available=True,
    )


def _runtime(
    home: Path,
    product: Any,
    provisioner: _Provisioner,
    environment: DiscoveryEnvironment,
) -> TutorialRuntime:
    """A fresh runtime over the same files, which is what a backend restart is."""
    return TutorialRuntime(
        product_state=lambda: product,
        external_events=ExternalEventNames(blocks_reloaded="blocks.reloaded", file_changed="file.changed"),
        # The open project, read the same way the app reads it: the API wires
        # both this port and the product state to `runtime.project_dir`, so a
        # harness that let them disagree would be modelling a state the product
        # cannot be in — and a session is only live in its own project.
        project_dir=lambda: product.project_dir,
        provisioner=provisioner,
        environment=environment,
        progress=ProgressStore(home / ".scistudio"),
        sessions=SessionStore(home / ".scistudio"),
    )


@pytest.fixture
def runtime(
    home: Path,
    product: StubProductState,
    provisioner: _Provisioner,
    environment: DiscoveryEnvironment,
    packages: list[Any],
) -> TutorialRuntime:
    return _runtime(home, product, provisioner, environment)


def _tutorial(core_dir: Path, tutorial_id: str, **overrides: Any) -> Path:
    payload: dict[str, Any] = {
        "manifest_version": 1,
        "id": tutorial_id,
        "title": tutorial_id.replace("-", " ").title(),
        "summary": "A tutorial.",
        "steps": [
            {"id": "one", "say": "Drag a Load block.", "done_when": _LOAD_NODE},
            {"id": "two", "say": "Read this and continue."},
        ],
    }
    payload.update(overrides)
    return write_tutorial(core_dir / tutorial_id, payload)


def _with_load(product: StubProductState) -> None:
    product.workflow_definition = WorkflowDefinition(
        id="wf", nodes=[NodeDef(id="load-1", block_type="LoadCSV", config={})], edges=[]
    )


# ---------------------------------------------------------------------------
# FR-043, FR-090 — one at a time, and leaving preserves
# ---------------------------------------------------------------------------


def test_exactly_one_session_is_active_at_a_time(runtime: TutorialRuntime, core_dir: Path) -> None:
    """FR-043: starting a second requires leaving the first."""
    _tutorial(core_dir, "first")
    _tutorial(core_dir, "second")

    runtime.start(TutorialKey.core("first"))

    with pytest.raises(AnotherSessionActiveError) as caught:
        runtime.start(TutorialKey.core("second"))
    assert "one tutorial runs at a time" in str(caught.value)


def test_leaving_preserves_the_session_and_frees_the_slot(runtime: TutorialRuntime, core_dir: Path) -> None:
    """FR-090: leaving is possible at any step and keeps the session for later."""
    _tutorial(core_dir, "first")
    _tutorial(core_dir, "second")
    runtime.start(TutorialKey.core("first"))
    runtime.continue_active()  # step one is unsatisfied; this is a no-op that proves position

    runtime.leave_active()

    assert runtime.active_session() is None
    assert runtime.start(TutorialKey.core("second")).status is SessionStatus.ACTIVE
    runtime.leave_active()
    resumed = runtime.start(TutorialKey.core("first"))
    assert resumed.step is not None and resumed.step.id == "one"


# ---------------------------------------------------------------------------
# FR-037 — the session survives a backend restart
# ---------------------------------------------------------------------------


def test_a_session_survives_a_backend_restart(
    home: Path,
    core_dir: Path,
    product: StubProductState,
    provisioner: _Provisioner,
    environment: DiscoveryEnvironment,
    packages: list[Any],
) -> None:
    """FR-037: position and satisfied steps are read back from ``~/.scistudio``."""
    _tutorial(core_dir, "welcome")
    first = _runtime(home, product, provisioner, environment)
    _with_load(product)
    started = first.start(TutorialKey.core("welcome"))
    assert started.step is not None and started.step.id == "one" and started.step.satisfied
    first.continue_active()

    second = _runtime(home, product, provisioner, environment)
    resumed = second.active_session()

    assert resumed is not None
    assert resumed.step is not None and resumed.step.id == "two"
    assert resumed.satisfied_step_ids == ("one",)


def test_a_condition_satisfied_while_the_learning_center_is_closed_is_not_lost(
    home: Path,
    core_dir: Path,
    product: StubProductState,
    provisioner: _Provisioner,
    environment: DiscoveryEnvironment,
    packages: list[Any],
) -> None:
    """Spec §2 Edge Cases: state lives on the backend, so nothing is missed.

    The mechanism is the point: the *backend* stays subscribed while the
    Learning Center is closed, so the event that satisfies the step is observed
    and recorded by something the user is not looking at. Reopening — modelled
    here as a second runtime reading the same files, which is also what a
    backend restart is — shows the step the user is really on rather than the
    one they last saw.
    """
    _tutorial(core_dir, "welcome")
    runtime = _runtime(home, product, provisioner, environment)
    started = runtime.start(TutorialKey.core("welcome"))
    assert started.step is not None and started.step.id == "one"

    # The Learning Center is closed. The bus is not.
    _with_load(product)
    runtime.handle_event("workflow.changed")

    reopened = _runtime(home, product, provisioner, environment).active_session()
    assert reopened is not None
    # FR-054a: the judgment was not lost — the step is reported satisfied and
    # waiting. What a closed Learning Center must not do is miss the event.
    assert reopened.step is not None and reopened.step.id == "one"
    assert reopened.step.satisfied is True
    assert reopened.satisfied_step_ids == ("one",)


def test_evaluation_continues_when_the_frontend_disconnects(
    runtime: TutorialRuntime, core_dir: Path, product: StubProductState
) -> None:
    """Spec §2 Edge Cases: the backend judges; the frontend only renders.

    Modelled as the thing a disconnect actually is: events keep arriving on the
    bus and nobody asks for a session view until later.
    """
    _tutorial(core_dir, "welcome")
    runtime.start(TutorialKey.core("welcome"))

    _with_load(product)
    pushed = runtime.handle_event("workflow.changed")

    assert pushed is not None and pushed.step is not None and pushed.step.id == "one"
    assert pushed.step.satisfied is True
    on_reconnect = runtime.active_session()
    assert on_reconnect is not None and on_reconnect.step is not None
    assert on_reconnect.step.id == "one"
    assert on_reconnect.step.satisfied is True


# ---------------------------------------------------------------------------
# FR-054 and the entry ordering
# ---------------------------------------------------------------------------


def test_a_condition_already_true_on_entry_satisfies_the_step_immediately(
    runtime: TutorialRuntime, core_dir: Path, product: StubProductState
) -> None:
    """FR-054: conditions are statements about state, not about having just acted.

    A user who dragged the Load block before the tutorial told them to must not
    be stuck being told to do something already done. Under FR-054a that shows
    up as the step arriving already satisfied — its Continue is live from the
    first frame — rather than as the session skipping past it.
    """
    _tutorial(core_dir, "welcome")
    _with_load(product)

    view = runtime.start(TutorialKey.core("welcome"))

    assert view.satisfied_step_ids == ("one",)
    assert view.step is not None and view.step.id == "one"
    assert view.step.satisfied is True

    assert runtime.continue_active().step is not None
    assert runtime.session_store.read().active is not None


def test_a_step_whose_own_action_falsifies_its_condition_does_not_auto_complete(
    home: Path,
    core_dir: Path,
    provisioner: _Provisioner,
    environment: DiscoveryEnvironment,
    packages: list[Any],
) -> None:
    """Entry order is ``do`` → evaluate → reveal, and it is load-bearing.

    FR-056/FR-059 fix that actions run on entry before the text; FR-054 fixes
    that an already-true condition satisfies on entry. The spec never states
    which of the two happens first, and one designed scenario turns on the
    answer: FR-058's step *breaks* the workflow so the user recovers it from
    History, and its ``done_when`` is true of the pre-break state. Evaluating
    before the action ran would satisfy the step instantly and skip the whole
    Restore lesson with no error anywhere.

    So the action lands first, and the step stays. The recovery — the marker
    going away — is what advances it, which is the lesson.
    """
    project = tutorial_project_path(TutorialKey.core("breaks-itself"))
    state = _BreakableWorkflowState(broken_marker=project / "workflows" / "broken.marker")
    # The tutorial's own project is the open one, as it is in the product once
    # the session has provisioned it. A session is judged only in its own
    # project, so leaving this unset would model a tutorial running while the
    # user is somewhere else — which is a dormant session, not this scenario.
    state.project_dir = project
    write_tutorial(
        core_dir / "breaks-itself",
        {
            "manifest_version": 1,
            "id": "breaks-itself",
            "title": "Breaks Itself",
            "summary": "The tutorial breaks the workflow so the user recovers it.",
            "bootstrap": {"project_name": "Breaks Itself"},
            "steps": [
                {
                    "id": "recover",
                    "say": "We just broke your workflow. Restore it from History.",
                    "do": [
                        {"write": {"source": "assets/data/broken.marker", "destination": "workflows/broken.marker"}}
                    ],
                    "done_when": _LOAD_NODE,
                }
            ],
        },
        files={"assets/data/broken.marker": "the tutorial broke it\n"},
    )
    runtime = _runtime(home, state, provisioner, environment)

    view = runtime.start(TutorialKey.core("breaks-itself"))

    assert (project / "workflows" / "broken.marker").is_file(), "the step's action must have run"
    assert view.status is SessionStatus.ACTIVE
    assert view.step is not None and view.step.id == "recover"
    assert view.satisfied_step_ids == (), "the step must not have satisfied itself against the pre-break state"

    (project / "workflows" / "broken.marker").unlink()  # the user restores from History
    recovered = runtime.evaluate_active()
    assert recovered.step is not None and recovered.step.satisfied is True
    assert runtime.continue_active().status is SessionStatus.COMPLETE


def test_a_steps_actions_land_before_its_text_is_readable(
    home: Path,
    core_dir: Path,
    provisioner: _Provisioner,
    environment: DiscoveryEnvironment,
    packages: list[Any],
    product: StubProductState,
) -> None:
    """FR-059: "we have written this block for you" must not be readable first."""
    project = tutorial_project_path(TutorialKey.core("writes"))
    write_tutorial(
        core_dir / "writes",
        {
            "manifest_version": 1,
            "id": "writes",
            "title": "Writes",
            "summary": "Writes a block, then says so.",
            "bootstrap": {"project_name": "Writes"},
            "steps": [
                {
                    "id": "written",
                    "say": "We have written the block for you.",
                    "do": [{"write": {"source": "assets/code/threshold.py", "destination": "blocks/threshold.py"}}],
                    "done_when": {"file_exists": {"path": "blocks/threshold.py"}},
                }
            ],
        },
        files={"assets/code/threshold.py": "# a block\n"},
    )
    product.project_dir = project
    runtime = _runtime(home, product, provisioner, environment)

    view = runtime.start(TutorialKey.core("writes"))

    assert (project / "blocks" / "threshold.py").is_file()
    # The action ran before the step was revealed, so the step arrives already
    # satisfied — and, under FR-054a, waits there for the reader.
    assert view.status is SessionStatus.ACTIVE
    assert view.step is not None and view.step.id == "written" and view.step.satisfied is True
    assert runtime.continue_active().status is SessionStatus.COMPLETE


def test_a_failed_action_ends_the_session_naming_the_step_and_the_action(
    home: Path,
    core_dir: Path,
    provisioner: _Provisioner,
    environment: DiscoveryEnvironment,
    packages: list[Any],
    product: StubProductState,
) -> None:
    """FR-060: an action failure ends the session and does not silently advance."""
    write_tutorial(
        core_dir / "missing-asset",
        {
            "manifest_version": 1,
            "id": "missing-asset",
            "title": "Missing Asset",
            "summary": "Declares an asset it does not ship.",
            "bootstrap": {"project_name": "Missing Asset"},
            "steps": [
                {
                    "id": "writes",
                    "say": "Written.",
                    "do": [{"write": {"source": "assets/data/absent.csv", "destination": "data/absent.csv"}}],
                },
                {"id": "next", "say": "Never reached."},
            ],
        },
    )
    runtime = _runtime(home, product, provisioner, environment)

    view = runtime.start(TutorialKey.core("missing-asset"))

    assert view.status is SessionStatus.ERROR
    assert view.error is not None
    assert "writes" in view.error and "absent.csv" in view.error
    assert view.satisfied_step_ids == ()
    assert not runtime.progress_store.is_completed(TutorialKey.core("missing-asset"))


# ---------------------------------------------------------------------------
# FR-012, FR-079 — continuing, and completing once
# ---------------------------------------------------------------------------


def test_a_reading_step_advances_on_an_explicit_continue(
    runtime: TutorialRuntime, core_dir: Path, product: StubProductState
) -> None:
    """FR-012: a step with no ``done_when`` waits for the user, then ends the tutorial."""
    _tutorial(core_dir, "welcome")
    _with_load(product)
    view = runtime.start(TutorialKey.core("welcome"))
    assert view.step is not None and view.step.id == "one" and view.step.satisfied
    reading = runtime.continue_active()
    assert reading.step is not None and reading.step.awaiting_continue

    finished = runtime.continue_active()

    assert finished.status is SessionStatus.COMPLETE
    assert finished.step is None
    assert runtime.progress_store.is_completed(TutorialKey.core("welcome"))


def test_completion_is_recorded_once(runtime: TutorialRuntime, core_dir: Path, product: StubProductState) -> None:
    """FR-079's "once": re-completing after a restart must not re-offer the milestone."""
    _tutorial(core_dir, "welcome")
    _with_load(product)
    runtime.start(TutorialKey.core("welcome"))
    runtime.continue_active()  # off the judged step
    runtime.continue_active()  # off the reading step, ending the tutorial

    assert runtime.progress_store.mark_completed(TutorialKey.core("welcome")) is False


# ---------------------------------------------------------------------------
# A session is live only in its own project
# ---------------------------------------------------------------------------


def test_a_session_is_dormant_while_another_project_is_open(
    runtime: TutorialRuntime, core_dir: Path, product: StubProductState
) -> None:
    """Closing the tutorial project stops the tutorial being the running one.

    Everything that judges a step reads the *open* project, so a session left
    running over the user's own project judges its conditions against their
    work: a project of theirs that happens to hold the file a step waits for
    would complete it. Reporting no session is what stops that, and what stops
    every surface reading the session — a step's ``prefill``, the step card —
    from acting inside a project the tutorial has nothing to do with.
    """
    _tutorial(core_dir, "welcome", bootstrap={"project_name": "Welcome"})
    _with_load(product)
    product.project_dir = tutorial_project_path(TutorialKey.core("welcome"))
    runtime.start(TutorialKey.core("welcome"))
    assert runtime.active_session() is not None

    product.project_dir = Path("/somewhere/else/the-users-own-project")

    assert runtime.active_session() is None


def test_a_dormant_session_is_preserved_and_resumes_in_its_own_project(
    runtime: TutorialRuntime, core_dir: Path, product: StubProductState
) -> None:
    """Dormant is not over: SC-007's resume is the same session, same step."""
    _tutorial(core_dir, "welcome", bootstrap={"project_name": "Welcome"})
    _with_load(product)
    project = tutorial_project_path(TutorialKey.core("welcome"))
    product.project_dir = project
    started = runtime.start(TutorialKey.core("welcome"))
    assert started.step is not None
    step_id = started.step.id

    product.project_dir = Path("/somewhere/else/the-users-own-project")
    assert runtime.active_session() is None

    product.project_dir = project
    resumed = runtime.active_session()

    assert resumed is not None
    assert resumed.step is not None and resumed.step.id == step_id
    assert resumed.status is SessionStatus.ACTIVE


def test_no_project_open_at_all_is_not_the_tutorials_project(
    runtime: TutorialRuntime, core_dir: Path, product: StubProductState
) -> None:
    """Closing without opening anything else is the same answer, for the same reason."""
    _tutorial(core_dir, "welcome", bootstrap={"project_name": "Welcome"})
    _with_load(product)
    product.project_dir = tutorial_project_path(TutorialKey.core("welcome"))
    runtime.start(TutorialKey.core("welcome"))

    product.project_dir = None

    assert runtime.active_session() is None


def test_a_step_is_not_judged_against_someone_elses_project(
    runtime: TutorialRuntime, core_dir: Path, product: StubProductState
) -> None:
    """The defect itself: product truth read elsewhere must not satisfy a step.

    ``evaluate_active`` is reachable from an engine event as well as from an
    explicit request, so the guard sits where judging happens rather than only
    where the session is reported.
    """
    _tutorial(core_dir, "welcome", bootstrap={"project_name": "Welcome"})
    product.project_dir = tutorial_project_path(TutorialKey.core("welcome"))
    runtime.start(TutorialKey.core("welcome"))

    # The user's own project happens to satisfy the tutorial's condition.
    product.project_dir = Path("/somewhere/else/the-users-own-project")
    _with_load(product)
    judged = runtime.evaluate_active()

    assert judged.step is not None and judged.step.satisfied is False
    assert judged.satisfied_step_ids == ()


def test_a_tutorial_with_no_project_of_its_own_is_never_gated(
    runtime: TutorialRuntime, core_dir: Path, product: StubProductState
) -> None:
    """A reading tutorial declares no ``bootstrap``, so it belongs to no project.

    Gating it on a project it does not have would make it unrunnable, which is
    the opposite of the defect being fixed.
    """
    _tutorial(core_dir, "reading")
    _with_load(product)
    product.project_dir = Path("/the/users/own/project")

    started = runtime.start(TutorialKey.core("reading"))

    assert started.step is not None
    assert runtime.active_session() is not None


# ---------------------------------------------------------------------------
# FR-066, FR-069 — the tutorial project
# ---------------------------------------------------------------------------


def test_restarting_deletes_the_previous_project_and_creates_it_again(
    home: Path,
    core_dir: Path,
    provisioner: _Provisioner,
    environment: DiscoveryEnvironment,
    packages: list[Any],
    product: StubProductState,
) -> None:
    """FR-066: the same location, a new project, and the user's edits gone."""
    _tutorial(core_dir, "welcome", bootstrap={"project_name": "Welcome"})
    runtime = _runtime(home, product, provisioner, environment)
    runtime.start(TutorialKey.core("welcome"))
    project = tutorial_project_path(TutorialKey.core("welcome"))
    (project / "scratch.txt").write_text("the user's own edit", encoding="utf-8")

    restarted = runtime.start(TutorialKey.core("welcome"), restart=True)

    assert provisioner.deleted == [project]
    assert restarted.project_path == project
    assert project.is_dir()
    assert not (project / "scratch.txt").exists()
    assert restarted.satisfied_step_ids == ()


def test_a_project_deleted_outside_the_product_invalidates_the_session(
    home: Path,
    core_dir: Path,
    provisioner: _Provisioner,
    environment: DiscoveryEnvironment,
    packages: list[Any],
    product: StubProductState,
) -> None:
    """FR-069: invalidated on the next interaction, and offered from the start."""
    import shutil

    _tutorial(core_dir, "welcome", bootstrap={"project_name": "Welcome"})
    runtime = _runtime(home, product, provisioner, environment)
    runtime.start(TutorialKey.core("welcome"))
    project = tutorial_project_path(TutorialKey.core("welcome"))

    shutil.rmtree(project)

    with pytest.raises(SessionInvalidatedError) as caught:
        runtime.evaluate_active()
    assert str(project) in str(caught.value)
    assert runtime.active_session() is None

    fresh = runtime.start(TutorialKey.core("welcome"))
    assert fresh.status is SessionStatus.ACTIVE
    assert fresh.satisfied_step_ids == ()
    assert fresh.step is not None and fresh.step.id == "one"


# ---------------------------------------------------------------------------
# A package uninstalled mid-session
# ---------------------------------------------------------------------------


def test_uninstalling_a_package_mid_session_ends_it_and_leaves_the_project(
    tmp_path: Path,
    home: Path,
    core_dir: Path,
    provisioner: _Provisioner,
    environment: DiscoveryEnvironment,
    packages: list[Any],
    product: StubProductState,
) -> None:
    """Spec §2 Edge Cases: the session ends and reports why; the project stays.

    The project is removed by clearing like any other, which is the whole
    reason it is left here rather than deleted: a user mid-tutorial has work in
    it, and losing that to an unrelated ``pip uninstall`` would be a surprise
    nothing warned about.
    """

    @dataclass
    class _Distribution:
        root: Path
        name: str

        @property
        def files(self) -> list[Any]:
            return []

        def locate_file(self, path: Any) -> Path:
            return self.root / str(path)

    @dataclass
    class _EntryPoint:
        name: str
        value: str
        group: str
        dist: Any

        @property
        def module(self) -> str:
            return self.value

    root = tmp_path / "site-packages"
    write_tutorial(
        root / "demo_pkg" / "tutorials" / "intro",
        {
            "manifest_version": 1,
            "id": "intro",
            "title": "Intro",
            "summary": "From a package.",
            "bootstrap": {"project_name": "Intro"},
            "steps": [{"id": "one", "say": "Drag a Load block.", "done_when": _LOAD_NODE}],
        },
    )
    packages.append(
        _EntryPoint(
            name="tutorials",
            value="demo_pkg.tutorials",
            group="scistudio.tutorials",
            dist=_Distribution(root=root, name="scistudio-blocks-demo"),
        )
    )
    key = TutorialKey(source_kind="package", source_id="scistudio-blocks-demo", tutorial_id="intro")
    runtime = _runtime(home, product, provisioner, environment)
    runtime.start(key)
    project = tutorial_project_path(key)
    assert project.is_dir()

    packages.clear()  # pip uninstall

    with pytest.raises(TutorialUnavailableError) as caught:
        runtime.evaluate_active()
    assert "no longer installed" in str(caught.value)
    assert project.is_dir(), "the tutorial project is left on disk"

    ended = runtime.active_session()
    assert ended is not None
    assert ended.status is SessionStatus.ERROR
    assert ended.error is not None and "no longer installed" in ended.error
    assert not runtime.progress_store.is_completed(key)


# ---------------------------------------------------------------------------
# Refusals the route layer maps to statuses
# ---------------------------------------------------------------------------


def test_an_unavailable_tutorial_cannot_be_started_and_says_why(runtime: TutorialRuntime, core_dir: Path) -> None:
    """FR-024: listed is not startable, and the refusal carries the same reason."""
    _tutorial(core_dir, "needs-a-package", requires={"packages": ["absent-package"]})

    with pytest.raises(TutorialUnavailableError) as caught:
        runtime.start(TutorialKey.core("needs-a-package"))

    assert "absent-package" in str(caught.value)


def test_acting_with_no_session_is_refused_rather_than_guessed(runtime: TutorialRuntime) -> None:
    """There is no implicit session; the route layer maps this to a status."""
    from scistudio.tutorials.session import NoActiveSessionError

    assert runtime.active_session() is None
    with pytest.raises(NoActiveSessionError):
        runtime.evaluate_active()
    with pytest.raises(NoActiveSessionError):
        runtime.continue_active()


def test_a_replay_step_without_a_byte_source_fails_as_an_action(
    home: Path,
    core_dir: Path,
    provisioner: _Provisioner,
    environment: DiscoveryEnvironment,
    packages: list[Any],
    product: StubProductState,
) -> None:
    """A replay with nowhere to play is a step failure, not a crash (FR-060).

    The byte source is the route layer's (checklist §6.1.7); a runtime wired
    without one still has to fail the way every other action failure fails.
    """
    write_tutorial(
        core_dir / "replays",
        {
            "manifest_version": 1,
            "id": "replays",
            "title": "Replays",
            "summary": "Plays a scripted agent session.",
            "bootstrap": {"project_name": "Replays"},
            "steps": [
                {
                    "id": "watch",
                    "say": "Watch the agent work.",
                    "do": [
                        {
                            "replay": {
                                "surface": "ai_chat_terminal",
                                "segments": [{"id": "s1", "source": "assets/replay/s1.txt"}],
                            }
                        }
                    ],
                }
            ],
        },
        files={"assets/replay/s1.txt": "hello\n"},
    )
    runtime = _runtime(home, product, provisioner, environment)

    view = runtime.start(TutorialKey.core("replays"))

    assert view.status is SessionStatus.ERROR
    assert view.error is not None and "replay" in view.error


def test_a_replay_step_drives_the_injected_byte_source(
    home: Path,
    core_dir: Path,
    provisioner: _Provisioner,
    environment: DiscoveryEnvironment,
    packages: list[Any],
    product: StubProductState,
) -> None:
    """The session opens one byte source, drives it, and closes it when it ends (FR-061c)."""
    delivered: list[tuple[str, bytes]] = []
    closed: list[str] = []

    class _Handle:
        surface = "ai_chat_terminal"
        tab_id = "tab-1"

        def deliver(self, segment: Any, payload: bytes) -> None:
            delivered.append((segment.id, payload))

        def close(self) -> None:
            closed.append(self.tab_id)

    write_tutorial(
        core_dir / "replays",
        {
            "manifest_version": 1,
            "id": "replays",
            "title": "Replays",
            "summary": "Plays a scripted agent session.",
            "bootstrap": {"project_name": "Replays"},
            "steps": [
                {
                    "id": "watch",
                    "say": "Watch the agent work.",
                    "do": [
                        {
                            "replay": {
                                "surface": "ai_chat_terminal",
                                "segments": [{"id": "s1", "source": "assets/replay/s1.txt"}],
                            }
                        }
                    ],
                }
            ],
        },
        files={"assets/replay/s1.txt": "hello\n"},
    )
    runtime = TutorialRuntime(
        product_state=lambda: product,
        external_events=ExternalEventNames(blocks_reloaded="blocks.reloaded", file_changed="file.changed"),
        provisioner=provisioner,
        environment=environment,
        progress=ProgressStore(home / ".scistudio"),
        sessions=SessionStore(home / ".scistudio"),
        open_replay=lambda surface: _Handle(),
    )

    view = runtime.start(TutorialKey.core("replays"))

    assert delivered == [("s1", b"hello\n")]
    assert view.replay is not None
    assert (view.replay.surface, view.replay.tab_id) == ("ai_chat_terminal", "tab-1")

    runtime.leave_active()
    assert closed == ["tab-1"]


def test_entering_a_step_anchors_since_step_entry_and_the_anchor_survives_restart(
    home: Path,
    core_dir: Path,
    environment: DiscoveryEnvironment,
    packages: list[Any],
    product: StubProductState,
    provisioner: _Provisioner,
) -> None:
    """#2066: the session stamps step entry and supplies it as evaluation context.

    A successful run from before the tutorial began must not satisfy a
    ``since_step_entry`` step (FR-054's already-true rule deliberately does not
    reach a since-scoped condition), the anchor must survive a backend restart
    the way the step id does (FR-037), and a run performed after entry must
    satisfy it.
    """
    from scistudio.tutorials.conditions import RunSummary

    _tutorial(
        core_dir,
        "press-run-here",
        steps=[
            {
                "id": "press-run",
                "say": "Press Run.",
                "done_when": {"run_succeeded": {"since_step_entry": True}},
            },
            {"id": "done", "say": "Done."},
        ],
    )
    product.runs = (
        RunSummary(run_id="r-old", workflow_id="wf", succeeded=True, started_at="2020-01-01T00:00:00+00:00"),
    )

    runtime = _runtime(home, product, provisioner, environment)
    started = runtime.start(TutorialKey.core("press-run-here"))
    assert started.step is not None and started.step.satisfied is False

    # A backend restart is a fresh runtime over the same files (FR-037).
    restarted = _runtime(home, product, provisioner, environment)
    view = restarted.evaluate_active()
    assert view.step is not None and view.step.satisfied is False

    from datetime import UTC, datetime

    product.runs = (
        RunSummary(run_id="r-new", workflow_id="wf", succeeded=True, started_at=datetime.now(tz=UTC).isoformat()),
        *product.runs,
    )
    view = restarted.evaluate_active()
    assert view.step is not None and view.step.satisfied is True


def test_the_default_provisioner_refuses_rather_than_making_an_unregistered_project(
    home: Path, core_dir: Path, environment: DiscoveryEnvironment, packages: list[Any], product: StubProductState
) -> None:
    """FR-063: a tutorial project the known-projects registry has never heard of is unusable.

    Several routes resolve a project's real path through that registry,
    including a path-containment check, so a directory created behind its back
    would fail them. Refusing names the gap; creating one would hide it.
    """
    _tutorial(core_dir, "welcome", bootstrap={"project_name": "Welcome"})
    runtime = TutorialRuntime(
        product_state=lambda: product,
        external_events=ExternalEventNames(blocks_reloaded="blocks.reloaded", file_changed="file.changed"),
        environment=environment,
        progress=ProgressStore(home / ".scistudio"),
        sessions=SessionStore(home / ".scistudio"),
    )

    with pytest.raises(Exception) as caught:
        runtime.start(TutorialKey.core("welcome"))

    assert "project provisioner" in str(caught.value)


def test_clearing_removes_progress_sessions_and_directories(
    runtime: TutorialRuntime, core_dir: Path, home: Path, product: StubProductState
) -> None:
    """FR-073/FR-088: clearing leaves no progress, no session, and no directories."""
    _tutorial(core_dir, "welcome", bootstrap={"project_name": "Welcome"})
    _with_load(product)
    # The tutorial's project is the open one; a session is live only there.
    product.project_dir = tutorial_project_path(TutorialKey.core("welcome"))
    runtime.start(TutorialKey.core("welcome"))
    runtime.continue_active()  # off the judged step
    runtime.continue_active()  # off the reading step, ending the tutorial
    assert runtime.progress_store.completed_keys()

    runtime.clear_data()

    assert runtime.progress_store.completed_keys() == frozenset()
    assert runtime.active_session() is None
    assert not tutorial_project_path(TutorialKey.core("welcome")).exists()


def test_an_action_failure_is_the_action_error_type(core_dir: Path) -> None:
    """The type the route layer sees is the one ``actions`` declares, not a new one."""
    assert issubclass(ActionExecutionError, RuntimeError)
