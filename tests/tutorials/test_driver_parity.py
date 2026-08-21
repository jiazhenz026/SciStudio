"""A package driver and a manifest tutorial are indistinguishable to the runtime.

``docs/specs/adr-053-learning-center.md`` FR-021, FR-038 … FR-042, FR-044, and
spec §4.4's Driver-parity row: a fixture package driver and a manifest tutorial
produce API responses distinguishable only by content (FR-040), and a driver
cannot return fields outside the step view (FR-041).

The two tutorials in this file are written to be *the same tutorial twice* —
same steps, same text, same condition — with one expressed as ``steps`` and the
other as a ``driver``. That is what makes the parity assertion mean something:
if the responses differ at all after the identity fields are set aside, the
difference came from the driver, which is exactly what FR-040 forbids.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import pytest

from scistudio.tutorials import discovery
from scistudio.tutorials.conditions import ExternalEventNames, ProductState, evaluate, parse_condition
from scistudio.tutorials.discovery import DiscoveryEnvironment
from scistudio.tutorials.driver import (
    DriverContext,
    DriverContractError,
    ManifestDriver,
    StepView,
    guarded,
    load_driver,
)
from scistudio.tutorials.progress import ProgressStore
from scistudio.tutorials.projects import TutorialKey
from scistudio.tutorials.session import SessionStatus, SessionStore, SessionView, TutorialRuntime

from .conftest import StubProductState, write_tutorial

_MODULE = "tests.tutorials.test_driver_parity"

#: The one tutorial, as data. Both drivers below answer from this.
_STEPS: tuple[dict[str, Any], ...] = (
    {"id": "drag-load", "say": "Drag a Load block onto the canvas.", "highlight": "block_palette"},
    {"id": "read", "say": "That is a workflow.", "route_to": "canvas"},
)

_DONE_WHEN = {"node_exists": {"block_type": "LoadCSV"}}


# ---------------------------------------------------------------------------
# The fixture package drivers
# ---------------------------------------------------------------------------


class ParityDriver:
    """A package driver answering exactly what the manifest driver answers.

    It calls the core evaluator for its first step's condition (FR-042), which
    is the affordance that lets a package author implement only the conditions
    the vocabulary does not cover rather than reimplementing the vocabulary.
    """

    def __init__(self, manifest: Any) -> None:
        self.manifest = manifest
        self.condition = parse_condition(_DONE_WHEN)
        self.evaluated = 0

    # ``Any`` rather than ``dict``: the driver protocol accepts any of the
    # StepView shapes, and LeakyDriver narrows the return to a subclass.
    def step_view(self, context: DriverContext) -> Any:
        index = self._index(context.step_id)
        step = _STEPS[index]
        return {
            "id": step["id"],
            "index": index,
            "total": len(_STEPS),
            "say": step.get("say"),
            "highlight": step.get("highlight"),
            "route_to": step.get("route_to"),
            "awaiting_continue": index == 1,
            # FR-041: a driver may not introduce a rendering primitive. This
            # key is here on purpose and must never reach a response.
            "custom_widget": "a thing the manifest format cannot express",
        }

    def is_satisfied(self, context: DriverContext, product: ProductState) -> bool:
        if context.step_id != _STEPS[0]["id"]:
            return False
        self.evaluated += 1
        return evaluate(self.condition, product)

    def entry_actions(self, context: DriverContext) -> tuple[Any, ...]:
        return ()

    def steps_outline(self, context: DriverContext) -> tuple[dict[str, Any], ...]:
        # The optional outline capability: a package driver that answers it
        # produces the same session-level outline the manifest driver does,
        # which is what keeps FR-040's parity available to it.
        return tuple(
            {"index": index, "id": step["id"], "say": step.get("say"), "pages": ()} for index, step in enumerate(_STEPS)
        )

    def advance(self, context: DriverContext) -> str | None:
        if context.step_id is None:
            return str(_STEPS[0]["id"])
        position = self._index(context.step_id) + 1
        return str(_STEPS[position]["id"]) if position < len(_STEPS) else None

    @staticmethod
    def _index(step_id: str | None) -> int:
        for index, step in enumerate(_STEPS):
            if step["id"] == step_id:
                return index
        raise LookupError(step_id)


@dataclass(frozen=True)
class _RicherStepView(StepView):
    """A step view a driver enriched. FR-041 says the extra field is not a view."""

    banner_image: str = "banner.png"


class LeakyDriver(ParityDriver):
    """Returns a :class:`StepView` *subclass* rather than a mapping."""

    def step_view(self, context: DriverContext) -> _RicherStepView:
        index = self._index(context.step_id)
        return _RicherStepView(id=str(_STEPS[index]["id"]), index=index, total=len(_STEPS))


class RaisingDriver(ParityDriver):
    """Raises where a driver most plausibly would: while judging state."""

    def is_satisfied(self, context: DriverContext, product: ProductState) -> bool:
        raise ZeroDivisionError("the package driver miscounted")


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
def no_packages(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib.metadata

    monkeypatch.setattr(importlib.metadata, "entry_points", lambda **_kwargs: ())


@pytest.fixture
def product() -> StubProductState:
    """No workflow yet, so the first step's condition is false on entry."""
    return StubProductState()


@pytest.fixture
def runtime(home: Path, product: StubProductState, no_packages: None) -> TutorialRuntime:
    return TutorialRuntime(
        product_state=lambda: product,
        external_events=ExternalEventNames(blocks_reloaded="blocks.reloaded", file_changed="file.changed"),
        environment=DiscoveryEnvironment(
            scistudio_version="0.3.1",
            installed_distributions=frozenset(),
            agent_available=False,
            git_available=True,
        ),
        progress=ProgressStore(home / ".scistudio"),
        sessions=SessionStore(home / ".scistudio"),
    )


def _write_manifest_tutorial(core_dir: Path) -> None:
    write_tutorial(
        core_dir / "by-manifest",
        {
            "manifest_version": 1,
            "id": "by-manifest",
            "title": "The tutorial",
            "summary": "Written as steps.",
            "steps": [dict(_STEPS[0], done_when=_DONE_WHEN), dict(_STEPS[1])],
        },
    )


def _write_driver_tutorial(core_dir: Path, driver: str = f"{_MODULE}:ParityDriver") -> None:
    write_tutorial(
        core_dir / "by-driver",
        {
            "manifest_version": 1,
            "id": "by-driver",
            "title": "The tutorial",
            "summary": "Written as a driver.",
            "driver": driver,
        },
    )


def _identity_free(view: SessionView) -> SessionView:
    """Return *view* with the fields that name *which* tutorial it is blanked.

    What remains is everything the driver influences. FR-040's claim is that
    this remainder is equal for the two, which is a stronger statement than
    "both responses have the same fields" — they are the same type, so that
    would be free.
    """
    return replace(view, tutorial_id="", source_id="", project_path=None)


# ---------------------------------------------------------------------------
# FR-040 — the runtime cannot tell them apart
# ---------------------------------------------------------------------------


def test_a_package_driver_and_a_manifest_tutorial_produce_the_same_response(
    runtime: TutorialRuntime, core_dir: Path, product: StubProductState
) -> None:
    """FR-040: no response field reveals which driver produced it."""
    _write_manifest_tutorial(core_dir)
    _write_driver_tutorial(core_dir)

    from_manifest = runtime.start(TutorialKey.core("by-manifest"))
    runtime.leave_active()
    from_driver = runtime.start(TutorialKey.core("by-driver"))

    assert _identity_free(from_manifest) == _identity_free(from_driver)
    assert from_manifest.step is not None
    assert from_manifest.step.id == "drag-load"


def test_both_drivers_advance_and_complete_identically(
    runtime: TutorialRuntime, core_dir: Path, product: StubProductState
) -> None:
    """The parity holds across the whole lifecycle, not only at the first step."""
    _write_manifest_tutorial(core_dir)
    _write_driver_tutorial(core_dir)

    def _run(key: TutorialKey) -> list[SessionView]:
        product.workflow_definition = None
        views = [runtime.start(key)]
        product.workflow_definition = _workflow_with_load()
        views.append(runtime.evaluate_active())
        views.append(runtime.continue_active())
        runtime.leave_active()
        return [_identity_free(view) for view in views]

    assert _run(TutorialKey.core("by-manifest")) == _run(TutorialKey.core("by-driver"))


def _workflow_with_load() -> Any:
    from scistudio.workflow.definition import NodeDef, WorkflowDefinition

    return WorkflowDefinition(id="wf", nodes=[NodeDef(id="load-1", block_type="LoadCSV", config={})], edges=[])


# ---------------------------------------------------------------------------
# FR-041 — the step view is closed
# ---------------------------------------------------------------------------


def test_a_driver_cannot_return_fields_outside_the_step_view(runtime: TutorialRuntime, core_dir: Path) -> None:
    """FR-041: the extra key the fixture driver returns never reaches a response.

    Enforced structurally: :meth:`StepView.of` constructs a fresh view from the
    names it knows, so there is no path by which an unknown key could survive,
    whatever a driver does.
    """
    _write_driver_tutorial(core_dir)

    view = runtime.start(TutorialKey.core("by-driver"))

    assert view.step is not None
    assert type(view.step) is StepView
    assert not hasattr(view.step, "custom_widget")
    assert set(vars(view.step)) == {
        "id",
        "index",
        "total",
        "title",
        "say",
        "highlight",
        "route_to",
        "prefill",
        "pages",
        "trigger",
        "awaiting_continue",
        # Not a driver's field: the runtime attaches it after reducing the
        # driver's view (FR-054a), which is why it survives this reduction
        # while `custom_widget` does not.
        "satisfied",
    }


def test_a_step_view_subclass_is_reduced_to_the_core_view(runtime: TutorialRuntime, core_dir: Path) -> None:
    """Subclassing is the other way to add a field, and it is closed too."""
    _write_driver_tutorial(core_dir, driver=f"{_MODULE}:LeakyDriver")

    view = runtime.start(TutorialKey.core("by-driver"))

    assert view.step is not None
    assert type(view.step) is StepView
    assert not hasattr(view.step, "banner_image")


def test_a_driver_returning_an_unusable_step_view_is_rejected() -> None:
    """A view with no id cannot be rendered, so it is a contract error, not a blank step."""
    with pytest.raises(DriverContractError):
        StepView.of({"index": 0, "total": 1})
    with pytest.raises(DriverContractError):
        StepView.of({"id": "one", "index": "first", "total": 1})
    with pytest.raises(DriverContractError):
        StepView.of({"id": "one", "index": 0, "total": 1, "say": ["not", "text"]})


def test_a_driver_cannot_introduce_an_action_kind(core_dir: Path) -> None:
    """FR-041 again, on the other half of the interface: entry actions are core's.

    A driver that could return an arbitrary object as an "action" would be able
    to address surfaces the manifest format cannot, which is the same escape the
    step view closes.
    """

    class _InventiveDriver(ParityDriver):
        def entry_actions(self, context: DriverContext) -> tuple[Any, ...]:
            return ({"launch": "a browser"},)

    driver = guarded(_InventiveDriver(manifest=None))
    context = DriverContext(key=TutorialKey.core("x"), tutorial_dir=core_dir, project_dir=None, step_id="drag-load")

    with pytest.raises(DriverContractError):
        driver.entry_actions(context)


def test_something_that_is_not_a_driver_is_refused_by_name() -> None:
    """A wrong object is named for what it is missing rather than failing later."""

    class _NotADriver:
        def step_view(self, context: DriverContext) -> None: ...

    with pytest.raises(DriverContractError) as caught:
        guarded(_NotADriver())

    assert "is_satisfied" in str(caught.value)


# ---------------------------------------------------------------------------
# FR-021, FR-042, FR-044 — importing, evaluating, failing
# ---------------------------------------------------------------------------


def test_a_package_driver_may_call_the_core_condition_evaluator(
    runtime: TutorialRuntime, core_dir: Path, product: StubProductState
) -> None:
    """FR-042: the vocabulary is available to a driver, so it implements only the rest."""
    _write_driver_tutorial(core_dir)

    runtime.start(TutorialKey.core("by-driver"))
    product.workflow_definition = _workflow_with_load()
    view = runtime.evaluate_active()

    assert view.step is not None
    assert view.step.id == "drag-load"
    assert view.step.satisfied is True, "the core evaluator judged the driver's condition true"
    assert "drag-load" in view.satisfied_step_ids
    assert runtime.continue_active().step is not None


def test_a_driver_that_will_not_import_breaks_only_its_own_tutorial(runtime: TutorialRuntime, core_dir: Path) -> None:
    """FR-021/FR-044: an import failure is contained, and another tutorial still starts."""
    _write_manifest_tutorial(core_dir)
    _write_driver_tutorial(core_dir, driver="scistudio_absent_package.driver:Nope")

    broken = runtime.start(TutorialKey.core("by-driver"))

    assert broken.status is SessionStatus.ERROR
    assert broken.error is not None
    assert "by-driver" in broken.error
    assert "ModuleNotFoundError" in broken.error

    working = runtime.start(TutorialKey.core("by-manifest"))
    assert working.status is SessionStatus.ACTIVE


def test_a_raising_driver_ends_the_session_naming_the_tutorial_and_the_exception(
    runtime: TutorialRuntime, core_dir: Path
) -> None:
    """FR-044: the session ends, the tutorial is not marked complete, others still start."""
    _write_manifest_tutorial(core_dir)
    _write_driver_tutorial(core_dir, driver=f"{_MODULE}:RaisingDriver")

    view = runtime.start(TutorialKey.core("by-driver"))

    assert view.status is SessionStatus.ERROR
    assert view.error is not None
    assert "The tutorial" in view.error
    assert "ZeroDivisionError" in view.error
    assert not runtime.progress_store.is_completed(TutorialKey.core("by-driver"))
    assert runtime.start(TutorialKey.core("by-manifest")).status is SessionStatus.ACTIVE


def test_the_manifest_driver_is_used_for_every_non_driver_tutorial(core_dir: Path) -> None:
    """FR-039: core, user, and project tutorials all get core's driver."""
    _write_manifest_tutorial(core_dir)
    from scistudio.tutorials.manifest import TutorialSourceKind, load_manifest

    manifest = load_manifest(core_dir / "by-manifest", source_kind=TutorialSourceKind.CORE)

    assert isinstance(load_driver(manifest, TutorialKey.core("by-manifest")).inner, ManifestDriver)


# ---------------------------------------------------------------------------
# The pages field crosses the FR-041 boundary as names, and only as names
# ---------------------------------------------------------------------------


def test_step_view_carries_pages_and_the_boundary_normalises_them() -> None:
    from scistudio.tutorials.driver import STEP_VIEW_FIELDS, DriverContractError, StepView

    assert "pages" in STEP_VIEW_FIELDS

    view = StepView.of({"id": "read", "index": 0, "total": 1, "pages": ["intro", "closing"]})
    assert view.pages == ("intro", "closing")

    # A driver returning something that is not a list of names is refused at
    # the boundary rather than rendered as a broken reading step.
    import pytest

    with pytest.raises(DriverContractError, match="pages"):
        StepView.of({"id": "read", "index": 0, "total": 1, "pages": "intro"})
    with pytest.raises(DriverContractError, match="pages"):
        StepView.of({"id": "read", "index": 0, "total": 1, "pages": [1]})


# ---------------------------------------------------------------------------
# The trigger crosses the FR-041 boundary as a label, and only as a label
# ---------------------------------------------------------------------------


def test_step_view_carries_the_trigger_label_and_nothing_behind_it() -> None:
    from scistudio.tutorials.driver import STEP_VIEW_FIELDS, DriverContractError, StepView

    assert "trigger" in STEP_VIEW_FIELDS

    view = StepView.of({"id": "s", "index": 0, "total": 1, "trigger": {"label": "Play", "do": ["smuggled"]}})
    assert view.trigger == {"label": "Play"}

    bare = StepView.of({"id": "s", "index": 0, "total": 1, "trigger": "Play"})
    assert bare.trigger == {"label": "Play"}

    import pytest

    with pytest.raises(DriverContractError, match="label"):
        StepView.of({"id": "s", "index": 0, "total": 1, "trigger": {"do": []}})


def test_a_driver_without_the_capability_answers_no_trigger_actions() -> None:
    from scistudio.tutorials.driver import GuardedDriver

    class _Bare:
        def step_view(self, context: object) -> dict[str, object]:
            return {"id": "s", "index": 0, "total": 1}

        def is_satisfied(self, context: object, product: object) -> bool:
            return False

        def entry_actions(self, context: object) -> tuple[()]:
            return ()

        def advance(self, context: object) -> None:
            return None

    assert GuardedDriver(_Bare()).trigger_actions(None) == ()  # type: ignore[arg-type]


def test_trigger_actions_are_normalised_like_entry_actions() -> None:
    """FR-041 cannot hold at one action door and not the other."""
    import pytest

    from scistudio.tutorials.driver import DriverContractError, GuardedDriver

    class _Leaky:
        def step_view(self, context: object) -> dict[str, object]:
            return {"id": "s", "index": 0, "total": 1}

        def is_satisfied(self, context: object, product: object) -> bool:
            return False

        def entry_actions(self, context: object) -> tuple[()]:
            return ()

        def advance(self, context: object) -> None:
            return None

        def trigger_actions(self, context: object) -> list[object]:
            return [{"write": {"source": "a", "destination": "b"}}]

    with pytest.raises(DriverContractError, match="core action objects"):
        GuardedDriver(_Leaky()).trigger_actions(None)  # type: ignore[arg-type]
