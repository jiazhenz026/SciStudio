"""Re-evaluation is caused by events, requests, and step entry — never by a timer.

``docs/specs/adr-053-learning-center.md`` FR-050, FR-051, FR-053, and spec
§4.4's Events row: each mapped event re-evaluates its terms, no timer or poll
exists, and explicit evaluation satisfies a ``file_exists`` condition on a
non-allowlisted extension.

The parametrisation is generated from
:func:`~scistudio.tutorials.conditions.build_event_term_map` rather than from a
list written here, so a term added to the FR-050 table without a working
re-evaluation path fails rather than going untested.
"""

from __future__ import annotations

import ast
import importlib.metadata
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from scistudio.engine.events import (
    BLOCK_DONE,
    BLOCK_ERROR,
    GIT_HEAD_CHANGED,
    INTERACTIVE_COMPLETE,
    WORKFLOW_CHANGED,
    WORKFLOW_COMPLETED,
)
from scistudio.tutorials import discovery
from scistudio.tutorials.conditions import ExternalEventNames, RunSummary, build_event_term_map
from scistudio.tutorials.discovery import DiscoveryEnvironment
from scistudio.tutorials.progress import ProgressStore
from scistudio.tutorials.projects import TutorialKey
from scistudio.tutorials.session import SessionStore, TutorialRuntime
from scistudio.workflow.definition import EdgeDef, NodeDef, WorkflowDefinition

from .conftest import StubProductState, write_tutorial

#: The two event names the API layer owns, spelled here because the *test* may
#: name them; ``scistudio.tutorials`` may not, which ``test_conditions.py``
#: asserts against the package source.
EXTERNAL = ExternalEventNames(blocks_reloaded="blocks.reloaded", file_changed="file.changed")

_TUTORIALS_PACKAGE = Path(__file__).resolve().parents[2] / "src" / "scistudio" / "tutorials"


# ---------------------------------------------------------------------------
# One condition per vocabulary term, with the state change that makes it true
# ---------------------------------------------------------------------------


def _workflow(*, config: str = "data/raw/cells.csv") -> WorkflowDefinition:
    return WorkflowDefinition(
        id="wf",
        nodes=[
            NodeDef(id="load-1", block_type="LoadCSV", config={"path": config}),
            NodeDef(id="save-1", block_type="SaveCSV", config={}),
        ],
        edges=[EdgeDef(source="load-1:table", target="save-1:table")],
    )


def _set_workflow(state: StubProductState) -> None:
    state.workflow_definition = _workflow()


#: ``term -> (done_when, the change that makes it true)``.
_TERMS: dict[str, tuple[dict[str, Any], Callable[[StubProductState], None]]] = {
    "node_exists": ({"node_exists": {"block_type": "LoadCSV"}}, _set_workflow),
    "edge_exists": (
        {"edge_exists": {"source_block_type": "LoadCSV", "target_block_type": "SaveCSV"}},
        _set_workflow,
    ),
    "config_equals": (
        {"config_equals": {"block_type": "LoadCSV", "key": "path", "value": "data/raw/cells.csv"}},
        _set_workflow,
    ),
    # The browser-picked absolute path config_equals cannot judge: the same
    # event has to reach config_matches, or the step needs an explicit request.
    "config_matches": (
        {"config_matches": {"block_type": "LoadCSV", "key": "path", "pattern": "data/raw/cells.csv"}},
        lambda state: setattr(
            state,
            "workflow_definition",
            _workflow(config="/Users/someone/SciStudio Tutorials/welcome/data/raw/cells.csv"),
        ),
    ),
    "run_succeeded": (
        {"run_succeeded": {}},
        lambda state: setattr(state, "runs", (RunSummary(run_id="r-1", workflow_id="wf", succeeded=True),)),
    ),
    # The latest run exists and did not complete — the positive fact a step that
    # breaks something on purpose waits for.
    "run_failed": (
        {"run_failed": {}},
        lambda state: setattr(state, "runs", (RunSummary(run_id="r-2", workflow_id="wf", succeeded=False),)),
    ),
    "port_has_output": (
        {"port_has_output": {"node_id": "load-1", "port": "table"}},
        lambda state: setattr(state, "ports_with_output", frozenset({("load-1", "table")})),
    ),
    "block_registered": (
        {"block_registered": {"block_type": "Threshold"}},
        lambda state: setattr(state, "block_types", frozenset({"Threshold"})),
    ),
    "type_registered": (
        {"type_registered": {"type_name": "CellTable"}},
        lambda state: setattr(state, "data_types", frozenset({"CellTable"})),
    ),
    "previewer_registered": (
        {"previewer_registered": {"type_name": "CellTable"}},
        lambda state: setattr(state, "previewer_types", frozenset({"CellTable"})),
    ),
    "library_contains": (
        {"library_contains": {"kind": "type", "name": "CellTable"}},
        lambda state: setattr(state, "library", frozenset({("type", "CellTable")})),
    ),
    "git_branch_exists": (
        {"git_branch_exists": {"branch": "experiment"}},
        lambda state: setattr(state, "branches", frozenset({"experiment"})),
    ),
    "git_current_branch": (
        {"git_current_branch": {"branch": "experiment"}},
        lambda state: setattr(state, "current_branch", "experiment"),
    ),
    "file_exists": (
        {"file_exists": {"path": "data/processed/out.csv"}},
        lambda state: _write_project_file(state, "data/processed/out.csv"),
    ),
    "interaction_completed": (
        {"interaction_completed": {"node_id": "ai-1"}},
        lambda state: setattr(state, "interactions", frozenset({"ai-1"})),
    ),
    # Creating a plot writes plots/<id>/plot.yaml and a render script into the
    # watched project, so the watcher event is what says one appeared.
    "plot_exists": (
        {"plot_exists": {"plot_id": "normalized_activity"}},
        lambda state: setattr(state, "plots", (("normalized_activity", "norm-1", "normalized"),)),
    ),
}


def _write_project_file(state: StubProductState, relative: str) -> None:
    assert state.project_dir is not None
    target = state.project_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("done\n", encoding="utf-8")


def _event_term_pairs() -> list[tuple[str, str]]:
    """Every (event, term) pair FR-050 declares, taken from the map itself."""
    pairs: list[tuple[str, str]] = []
    for event, terms in build_event_term_map(EXTERNAL).items():
        pairs.extend((event, term) for term in sorted(terms))
    return pairs


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


@pytest.fixture(autouse=True)
def no_packages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(importlib.metadata, "entry_points", lambda **_kwargs: ())


@pytest.fixture
def product(tmp_path: Path) -> StubProductState:
    project = tmp_path / "project"
    project.mkdir()
    return StubProductState(project_dir=project)


@pytest.fixture
def runtime(home: Path, product: StubProductState) -> TutorialRuntime:
    return TutorialRuntime(
        product_state=lambda: product,
        external_events=EXTERNAL,
        environment=DiscoveryEnvironment(
            scistudio_version="0.3.1",
            installed_distributions=frozenset(),
            agent_available=True,
            git_available=True,
        ),
        progress=ProgressStore(home / ".scistudio"),
        sessions=SessionStore(home / ".scistudio"),
    )


def _judged_by(core_dir: Path, done_when: dict[str, Any], tutorial_id: str = "judged") -> None:
    write_tutorial(
        core_dir / tutorial_id,
        {
            "manifest_version": 1,
            "id": tutorial_id,
            "title": tutorial_id.title(),
            "summary": "One step, judged by one condition.",
            "steps": [
                {"id": "judged", "say": "Do the thing.", "done_when": done_when},
                {"id": "after", "say": "Read this."},
            ],
        },
    )


# ---------------------------------------------------------------------------
# FR-050 — each mapped event re-evaluates its terms
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("event", "term"), _event_term_pairs())
def test_each_mapped_event_reevaluates_its_terms(
    event: str,
    term: str,
    runtime: TutorialRuntime,
    core_dir: Path,
    product: StubProductState,
) -> None:
    """FR-050: an observed event re-judges every term it maps to, and no other.

    The event moves the *judgment*, not the session (FR-054a): the step is
    reported satisfied and stays on screen until the reader continues.
    """
    done_when, make_true = _TERMS[term]
    _judged_by(core_dir, done_when)
    started = runtime.start(TutorialKey.core("judged"))
    assert started.step is not None and started.step.id == "judged"
    assert started.step.satisfied is False

    make_true(product)
    view = runtime.handle_event(event)

    assert view is not None, f"{event} did not re-evaluate {term}"
    assert "judged" in view.satisfied_step_ids
    assert view.step is not None and view.step.id == "judged"
    assert view.step.satisfied is True, f"{event} did not report {term} as satisfied"


def test_an_event_mapping_to_none_of_the_steps_terms_does_nothing(
    runtime: TutorialRuntime, core_dir: Path, product: StubProductState
) -> None:
    """A mapped event whose terms the step does not use is not a re-evaluation.

    The saving is not the point; the shape is. Re-evaluation is caused, and an
    event that cannot change the answer is not a cause.
    """
    _judged_by(core_dir, {"git_branch_exists": {"branch": "experiment"}})
    runtime.start(TutorialKey.core("judged"))
    product.branches = frozenset({"experiment"})

    assert runtime.handle_event(WORKFLOW_CHANGED) is None
    assert runtime.handle_event(GIT_HEAD_CHANGED) is not None


def test_an_unmapped_event_is_ignored(runtime: TutorialRuntime, core_dir: Path) -> None:
    """Only the FR-050 table drives re-evaluation; the bus carries much more."""
    _judged_by(core_dir, {"node_exists": {"block_type": "LoadCSV"}})
    runtime.start(TutorialKey.core("judged"))

    assert runtime.handle_event("workflow_started") is None
    assert runtime.handle_event("interactive_prompt") is None


def test_the_subscription_is_exactly_the_declared_event_set(runtime: TutorialRuntime) -> None:
    """FR-050: the runtime subscribes using the constants, not string literals.

    The six engine events are asserted by identity with
    ``scistudio.engine.events``, so renaming one there without moving the map
    fails the import rather than silently unsubscribing the runtime.
    """
    subscribed = set(runtime.subscribed_event_types())

    assert {
        WORKFLOW_CHANGED,
        WORKFLOW_COMPLETED,
        BLOCK_DONE,
        BLOCK_ERROR,
        GIT_HEAD_CHANGED,
        INTERACTIVE_COMPLETE,
    } <= subscribed
    assert subscribed == set(build_event_term_map(EXTERNAL))
    assert {EXTERNAL.blocks_reloaded, EXTERNAL.file_changed} <= subscribed


def test_the_two_api_layer_event_names_travel_through_the_injection(
    home: Path, product: StubProductState, core_dir: Path
) -> None:
    """Renaming an API-layer event moves the subscription with it (checklist §6.1.5)."""
    renamed = ExternalEventNames(blocks_reloaded="x.reloaded", file_changed="x.changed")
    runtime = TutorialRuntime(
        product_state=lambda: product,
        external_events=renamed,
        environment=DiscoveryEnvironment(
            scistudio_version="0.3.1",
            installed_distributions=frozenset(),
            agent_available=True,
            git_available=True,
        ),
        progress=ProgressStore(home / ".scistudio"),
        sessions=SessionStore(home / ".scistudio"),
    )
    _judged_by(core_dir, {"block_registered": {"block_type": "Threshold"}})
    runtime.start(TutorialKey.core("judged"))
    product.block_types = frozenset({"Threshold"})

    assert "x.reloaded" in runtime.subscribed_event_types()
    assert runtime.handle_event("blocks.reloaded") is None
    assert runtime.handle_event("x.reloaded") is not None


# ---------------------------------------------------------------------------
# FR-053 — the explicit request covers what no event reaches
# ---------------------------------------------------------------------------


def test_explicit_evaluation_satisfies_a_file_condition_no_event_reaches(
    runtime: TutorialRuntime, core_dir: Path, product: StubProductState
) -> None:
    """FR-053: ``file.changed`` is filtered to ``ADR036_FILE_ALLOWLIST``.

    A ``file_exists`` condition on a TIFF or a Zarr store is therefore never
    event-driven, which is why the explicit request exists as a requirement
    rather than as a convenience. The condition is judged against the
    filesystem either way; what differs is what causes the judgement.
    """
    _judged_by(core_dir, {"file_exists": {"path": "data/raw/cells.tiff"}})
    runtime.start(TutorialKey.core("judged"))
    _write_project_file(product, "data/raw/cells.tiff")

    from scistudio.api.file_contracts import ADR036_FILE_ALLOWLIST

    assert ".tiff" not in ADR036_FILE_ALLOWLIST, "the premise of FR-053 changed"

    view = runtime.evaluate_active()

    assert "judged" in view.satisfied_step_ids
    assert view.step is not None and view.step.id == "judged"
    assert view.step.satisfied is True


def test_a_reported_user_interface_event_satisfies_a_ui_event_condition(
    home: Path, core_dir: Path, product: StubProductState
) -> None:
    """FR-052: the one completion path originating in the frontend.

    It still arrives as backend state: the route layer records the name into
    the product state object and the evaluation reads it there, like every
    other term.
    """
    reported: list[str] = []

    def _record(name: str) -> None:
        reported.append(name)
        product.events = frozenset({*product.events, name})

    runtime = TutorialRuntime(
        product_state=lambda: product,
        external_events=EXTERNAL,
        environment=DiscoveryEnvironment(
            scistudio_version="0.3.1",
            installed_distributions=frozenset(),
            agent_available=True,
            git_available=True,
        ),
        progress=ProgressStore(home / ".scistudio"),
        sessions=SessionStore(home / ".scistudio"),
        record_ui_event=_record,
    )
    _judged_by(core_dir, {"ui_event": {"name": "preview_expanded"}})
    runtime.start(TutorialKey.core("judged"))

    view = runtime.report_ui_event("preview_expanded")

    assert reported == ["preview_expanded"]
    assert "judged" in view.satisfied_step_ids


def test_a_reported_event_belongs_to_the_step_that_asked_for_it(
    home: Path, core_dir: Path, product: StubProductState
) -> None:
    """Entering a step forgets the events reported under the previous one.

    The defect: core tutorial 1 asks the reader to click a block on its third
    step and again on its tenth. A reported event is a moment, not a state, and
    the recorded set lived for the whole session — so the tenth step was
    satisfied on arrival by the click they made seven steps earlier, and its
    Continue was live before they had done anything.
    """

    def _record(name: str) -> None:
        product.events = frozenset({*product.events, name})

    def _forget() -> None:
        product.events = frozenset()

    runtime = TutorialRuntime(
        product_state=lambda: product,
        external_events=EXTERNAL,
        environment=DiscoveryEnvironment(
            scistudio_version="0.3.1",
            installed_distributions=frozenset(),
            agent_available=True,
            git_available=True,
        ),
        progress=ProgressStore(home / ".scistudio"),
        sessions=SessionStore(home / ".scistudio"),
        record_ui_event=_record,
        forget_ui_events=_forget,
    )
    write_tutorial(
        core_dir / "twice",
        {
            "manifest_version": 1,
            "id": "twice",
            "title": "Twice",
            "summary": "Asks for the same interface event on two different steps.",
            "steps": [
                {"id": "click-once", "say": "Click it.", "done_when": {"ui_event": {"name": "node_selected"}}},
                {"id": "click-again", "say": "Click it again.", "done_when": {"ui_event": {"name": "node_selected"}}},
            ],
        },
    )
    runtime.start(TutorialKey.core("twice"))
    first = runtime.report_ui_event("node_selected")
    assert first.step is not None and first.step.satisfied is True

    second = runtime.continue_active()

    assert second.step is not None and second.step.id == "click-again"
    assert second.step.satisfied is False, "the earlier click must not satisfy this step"
    assert runtime.report_ui_event("node_selected").step.satisfied is True


# ---------------------------------------------------------------------------
# FR-051 — there is no timer
# ---------------------------------------------------------------------------


def test_a_whole_session_creates_no_thread(runtime: TutorialRuntime, core_dir: Path, product: StubProductState) -> None:
    """FR-051: nothing wakes on its own, measured across a full lifecycle."""
    _judged_by(core_dir, {"node_exists": {"block_type": "LoadCSV"}})
    before = threading.active_count()

    runtime.catalogue()
    runtime.start(TutorialKey.core("judged"))
    runtime.evaluate_active()
    _set_workflow(product)
    runtime.handle_event(WORKFLOW_CHANGED)
    runtime.continue_active()
    runtime.active_session()

    assert threading.active_count() == before, "the tutorial runtime started a background thread"


@pytest.mark.parametrize("module", sorted(_TUTORIALS_PACKAGE.rglob("*.py")), ids=lambda path: path.name)
def test_no_module_schedules_its_own_wakeup(module: Path) -> None:
    """FR-051 structurally: no scheduling machinery is imported anywhere here.

    Asserted against the import graph rather than against observed behaviour,
    because a poll that fires once a minute would pass a runtime assertion and
    still be the thing FR-051 forbids. Re-evaluation has three causes — a
    mapped event, an explicit request, and step entry — and none of them needs
    a clock.
    """
    forbidden = {"threading", "asyncio", "sched", "_thread", "concurrent.futures", "multiprocessing"}
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    offending = {name for name in imported if name in forbidden or name.split(".")[0] in forbidden}
    assert offending == set(), f"{module.name} imports {sorted(offending)}, which FR-051 forbids"


@pytest.mark.parametrize("module", sorted(_TUTORIALS_PACKAGE.rglob("*.py")), ids=lambda path: path.name)
def test_no_module_sleeps(module: Path) -> None:
    """The other spelling of a poll: a loop around ``time.sleep``."""
    source = module.read_text(encoding="utf-8")
    assert "time.sleep" not in source
    assert "sleep(" not in source
