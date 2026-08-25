"""Going back: a cursor over the trail, not an undo (#2138).

``docs/specs/adr-053-learning-center.md`` FR-054a and FR-054b.

The two things that make this more than "decrement the index" are what these
tests hold. A step's entry actions write files into the tutorial project, so
arriving at a step a second time must not enter it a second time. And a step
the reader already finished must still read as finished when they come back to
it, or a condition that has since stopped holding strands them in the past
behind a dark Continue.

The fixtures are ``test_session_lifecycle``'s. This is the same runtime with
the same injected ports, asked a different question.
"""

from __future__ import annotations

import importlib.metadata
from pathlib import Path
from typing import Any

import pytest

from scistudio.tutorials import discovery
from scistudio.tutorials.discovery import DiscoveryEnvironment
from scistudio.tutorials.projects import TutorialKey
from scistudio.tutorials.session import SessionRecord, SessionStatus, TutorialRuntime
from scistudio.workflow.definition import NodeDef, WorkflowDefinition

from .conftest import StubProductState, write_tutorial
from .test_session_lifecycle import _Provisioner, _runtime

# ---------------------------------------------------------------------------
# The same ports ``test_session_lifecycle`` injects, stood up again here
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
def packages(monkeypatch: pytest.MonkeyPatch) -> None:
    """No package tutorials, so discovery imports nothing."""
    monkeypatch.setattr(importlib.metadata, "entry_points", lambda *a, **k: ())


@pytest.fixture
def product() -> StubProductState:
    return StubProductState()


@pytest.fixture
def runtime(
    home: Path,
    product: StubProductState,
    packages: None,
) -> TutorialRuntime:
    return _runtime(
        home,
        product,
        _Provisioner(),
        DiscoveryEnvironment(
            scistudio_version="0.3.1",
            installed_distributions=frozenset(),
            agent_available=True,
            git_available=True,
        ),
    )


_LOAD_NODE = {"node_exists": {"block_type": "LoadCSV"}}


def _three_steps(core_dir: Path, **step_two: Any) -> Path:
    """A tutorial the reader can walk: read, act, read."""
    two: dict[str, Any] = {"id": "two", "say": "Drag a Load block."}
    two.update(step_two)
    return write_tutorial(
        core_dir / "walk",
        {
            "manifest_version": 1,
            "id": "walk",
            "title": "Walk",
            "summary": "A tutorial with somewhere to walk back from.",
            "steps": [
                {"id": "one", "say": "First."},
                two,
                {"id": "three", "say": "Third."},
            ],
        },
    )


def _with_load(product: StubProductState) -> None:
    product.workflow_definition = WorkflowDefinition(
        id="wf", nodes=[NodeDef(id="load-1", block_type="LoadCSV", config={})], edges=[]
    )


def _step_id(view: Any) -> str | None:
    return None if view.step is None else view.step.id


# ---------------------------------------------------------------------------
# The trail
# ---------------------------------------------------------------------------


def test_the_session_records_every_step_it_enters(runtime: TutorialRuntime, core_dir: Path) -> None:
    _three_steps(core_dir)
    runtime.start(TutorialKey.core("walk"))
    runtime.continue_active()

    record = runtime.session_store.read().active
    assert record is not None
    assert record.visited_step_ids == ("one", "two")


def test_the_first_step_has_nowhere_to_go_back_to(runtime: TutorialRuntime, core_dir: Path) -> None:
    _three_steps(core_dir)

    view = runtime.start(TutorialKey.core("walk"))

    assert _step_id(view) == "one"
    assert view.can_go_back is False


def test_back_reports_where_it_can_go_once_there_is_a_trail(runtime: TutorialRuntime, core_dir: Path) -> None:
    _three_steps(core_dir)
    runtime.start(TutorialKey.core("walk"))

    view = runtime.continue_active()

    assert _step_id(view) == "two"
    assert view.can_go_back is True


def test_a_record_written_before_the_trail_existed_reads_as_no_way_back() -> None:
    """FR-037's forward compatibility, from the other direction.

    A session persisted by an earlier build has no ``visited_step_ids``. It must
    load — losing a session costs the reader their place — and it must report
    honestly that it does not know where they came from.
    """
    record = SessionRecord.from_json(
        {
            "source_kind": "core",
            "source_id": "",
            "tutorial_id": "walk",
            "title": "Walk",
            "step_id": "two",
            "status": "active",
        }
    )

    assert record is not None
    assert record.visited_step_ids == ()
    assert record.can_go_back is False


# ---------------------------------------------------------------------------
# Going back, and coming forward again
# ---------------------------------------------------------------------------


def test_back_returns_to_the_previous_step(runtime: TutorialRuntime, core_dir: Path) -> None:
    _three_steps(core_dir)
    runtime.start(TutorialKey.core("walk"))
    runtime.continue_active()

    view = runtime.back_active()

    assert _step_id(view) == "one"
    assert view.can_go_back is False


def test_back_at_the_start_returns_the_same_step_rather_than_failing(runtime: TutorialRuntime, core_dir: Path) -> None:
    """The same shape ``continue_active`` refuses in, for the same reason.

    The client's disabled control and the backend's answer are one rule, held
    on the side that owns the judgment (spec §4.1), so a client that offers the
    press anyway cannot walk off the front of the tutorial.
    """
    _three_steps(core_dir)
    runtime.start(TutorialKey.core("walk"))

    view = runtime.back_active()

    assert _step_id(view) == "one"
    assert view.status is SessionStatus.ACTIVE


def test_a_round_trip_does_not_enter_a_step_twice(
    runtime: TutorialRuntime, core_dir: Path, product: StubProductState
) -> None:
    """The reason back is a cursor and not a re-entry.

    Step two writes a file into the tutorial project on entry (FR-056). The file
    is deleted after that first entry, and walking away and back must not bring
    it back: nothing was entered, so nothing ran.
    """
    write_tutorial(
        core_dir / "walk",
        {
            "manifest_version": 1,
            "id": "walk",
            "title": "Walk",
            "summary": "A tutorial whose second step writes.",
            "bootstrap": {"project_name": "Walk"},
            "steps": [
                {"id": "one", "say": "First."},
                {
                    "id": "two",
                    "say": "Second.",
                    "do": [{"write": {"source": "assets/note.txt", "destination": "note.txt"}}],
                },
            ],
        },
        files={"assets/note.txt": "written on entry\n"},
    )
    view = runtime.start(TutorialKey.core("walk"))
    assert view.project_path is not None
    runtime.continue_active()

    written = view.project_path / "note.txt"
    assert written.is_file()
    written.unlink()

    runtime.back_active()
    forward = runtime.continue_active()

    assert _step_id(forward) == "two"
    assert not written.exists(), "the step was entered a second time"


def test_continuing_from_behind_walks_the_trail_before_asking_the_driver(
    runtime: TutorialRuntime, core_dir: Path
) -> None:
    _three_steps(core_dir)
    runtime.start(TutorialKey.core("walk"))
    runtime.continue_active()
    runtime.continue_active()
    runtime.back_active()
    runtime.back_active()

    assert _step_id(runtime.active_session()) == "one"
    assert _step_id(runtime.continue_active()) == "two"
    assert _step_id(runtime.continue_active()) == "three"


# ---------------------------------------------------------------------------
# What a revisited step reports
# ---------------------------------------------------------------------------


def test_a_step_the_reader_finished_stays_finished_when_they_come_back(
    runtime: TutorialRuntime, core_dir: Path, product: StubProductState
) -> None:
    """Otherwise going back is a trap.

    The reader satisfied step two by dragging a Load block on, moved on, and
    then deleted it — or the step's condition was scoped to the time it was
    entered (#2066), which a second entry stamp cannot reproduce. Judged live,
    the step they already cleared would tell them it is not done and offer them
    a dark Continue on the way out of it.
    """
    _three_steps(core_dir, done_when=_LOAD_NODE)
    runtime.start(TutorialKey.core("walk"))
    runtime.continue_active()
    _with_load(product)
    judged = runtime.evaluate_active()
    assert judged.step is not None and judged.step.satisfied is True
    runtime.continue_active()

    product.workflow_definition = WorkflowDefinition(id="wf", nodes=[], edges=[])
    view = runtime.back_active()

    assert _step_id(view) == "two"
    assert view.step is not None
    assert view.step.satisfied is True


def test_the_step_the_reader_is_actually_on_is_judged_live(
    runtime: TutorialRuntime, core_dir: Path, product: StubProductState
) -> None:
    """The other half of the same rule, and the one FR-054a rests on.

    Stickiness applies behind the reader, never at the furthest point they have
    reached. A step that reports satisfied because it once was would let them
    continue past work they have since undone.
    """
    _three_steps(core_dir, done_when=_LOAD_NODE)
    runtime.start(TutorialKey.core("walk"))
    runtime.continue_active()
    _with_load(product)
    judged = runtime.evaluate_active()
    assert judged.step is not None and judged.step.satisfied is True

    product.workflow_definition = WorkflowDefinition(id="wf", nodes=[], edges=[])
    view = runtime.evaluate_active()

    assert _step_id(view) == "two"
    assert view.step is not None
    assert view.step.satisfied is False


def test_a_revisited_step_says_so(runtime: TutorialRuntime, core_dir: Path) -> None:
    """The client needs to tell "you did this once" from "you just did it".

    A revisited step reports satisfied whatever its condition now says, so a
    surface that hides its pointer on a satisfied step would hide it on every
    step the reader walked back through — which is exactly when the pointer is
    the illustration rather than an instruction.
    """
    _three_steps(core_dir)
    runtime.start(TutorialKey.core("walk"))
    assert runtime.continue_active().revisiting is False

    back = runtime.back_active()

    assert _step_id(back) == "one"
    assert back.revisiting is True
    # And forward again, back to the live edge.
    assert runtime.continue_active().revisiting is False
