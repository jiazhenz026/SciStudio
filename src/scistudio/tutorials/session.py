"""The tutorial session: one at a time, owned by the backend, restart-proof.

ADR-053 Learning Center spec, FR-036, FR-037, FR-043, FR-044 and
FR-050 … FR-054 (``docs/specs/adr-053-learning-center.md``).

The backend owns which tutorial is running, which project it runs in, which
step it is on, and which steps are satisfied (FR-036), and it writes all of
that under ``~/.scistudio/`` so a backend restart resumes rather than restarts
(FR-037). Exactly one session is active at a time; starting a second requires
leaving the first, and leaving preserves it (FR-043, FR-090).

No polling (FR-051)
-------------------

This module creates no thread, no timer, and no ``asyncio`` loop. Every
re-evaluation has a cause: entry into a step, an observed event that
:func:`~scistudio.tutorials.conditions.build_event_term_map` maps to one of the
step's terms (FR-050), or an explicit request (FR-053). The event names come
from the declared constants — the six in ``scistudio.engine.events`` directly,
and the two that live under ``scistudio.api`` through
:class:`~scistudio.tutorials.conditions.ExternalEventNames`, which the route
layer constructs and injects because this package may not import that layer
(checklist §6.1.2, §6.1.5). No event name is spelled as a literal here.

Step entry: actions, then judgement, then text
----------------------------------------------

The order is ``do`` → evaluate ``done_when`` → reveal the step (FR-056, FR-059,
FR-054). The spec fixes each half separately and never states the order between
them, and it is load-bearing: one designed scenario has a step whose own ``do``
*breaks* the workflow so the user recovers it from History (FR-058). Its
``done_when`` is true of the pre-break state, so evaluating before the actions
ran would satisfy the step instantly and skip the whole lesson with no error.
:func:`~scistudio.tutorials.actions.perform_step_entry` gives the outer half of
the ordering — nothing can read the step until the actions have landed — and
the evaluation is performed inside its ``reveal`` callback, which puts it after
the actions and before the text.

What ends a session
-------------------

A driver exception ends it with an error naming the tutorial and the exception,
does not mark the tutorial complete, and does not prevent another tutorial from
starting (FR-044). An action failure does the same naming the step and the
action (FR-060). A package uninstalled mid-session ends it and says so, leaving
the tutorial project on disk. A tutorial project deleted outside the product
invalidates the session on the next interaction and the tutorial is offered
from the start (FR-069). None of these is a poll: each is noticed at the next
interaction, which is the only moment at which it could matter.

An ended session is *kept* as the active record with status ``complete`` or
``error`` rather than erased, so the frontend that asks for the active session
is told what happened. Only a session whose status is ``active`` blocks
starting another one, which is what makes FR-044's "does not prevent other
tutorials from starting" true without a second concept.

This module may not import ``scistudio.api`` (checklist §6.1.2). Everything it
needs from that layer — product state, the two external event names, project
creation and deletion, and replay byte delivery — is injected.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from scistudio.core.dropins import user_library_dir
from scistudio.tutorials.actions import (
    Action,
    ActionContext,
    ActionExecutionError,
    ReplayAction,
    ReplaySegment,
    execute_actions,
    perform_step_entry,
)
from scistudio.tutorials.conditions import (
    ExternalEventNames,
    ProductState,
    build_event_term_map,
)
from scistudio.tutorials.discovery import (
    Catalogue,
    CatalogueGroup,
    DiscoveryEnvironment,
    DiscoveryResult,
    build_catalogue,
    discover_tutorials,
)
from scistudio.tutorials.driver import (
    DriverContext,
    DriverError,
    GuardedDriver,
    StepView,
    load_driver,
)
from scistudio.tutorials.manifest import TutorialManifest
from scistudio.tutorials.progress import ProgressStore
from scistudio.tutorials.projects import (
    TutorialKey,
    TutorialProjectPlan,
    clear_preview,
    clear_tutorial_data,
    delete_tutorial_project,
    plan_tutorial_project,
    tutorial_project_exists,
    tutorial_project_path,
)

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    """The session's one clock: timezone-aware UTC, ISO-8601 — comparable with
    the lineage store's run timestamps, which ``since_step_entry`` compares it
    against (#2066)."""
    return datetime.now(tz=UTC).isoformat()


__all__ = [
    "SESSION_FILENAME",
    "AnotherSessionActiveError",
    "NoActiveSessionError",
    "ProjectProvisioner",
    "ReplayHandle",
    "ReplayView",
    "SessionInvalidatedError",
    "SessionRecord",
    "SessionState",
    "SessionStatus",
    "SessionStore",
    "SessionView",
    "TutorialRuntime",
    "TutorialSessionError",
    "TutorialUnavailableError",
]

#: The session file, beside the progress file under ``~/.scistudio/`` (FR-037).
SESSION_FILENAME = "tutorial-session.json"

_SCHEMA_VERSION = 1


class TutorialSessionError(RuntimeError):
    """Base for every session-lifecycle refusal the route layer maps to a status."""


class NoActiveSessionError(TutorialSessionError):
    """There is no active session to act on."""


class SessionInvalidatedError(NoActiveSessionError):
    """The active session's tutorial project is gone from disk (FR-069).

    A subclass of :class:`NoActiveSessionError` because that is what it now is —
    the record has been dropped and the tutorial is offered from the start — but
    a distinct type because the user is owed the reason rather than a bare
    "nothing is running".
    """

    def __init__(self, key: TutorialKey, path: Path) -> None:
        self.key = key
        self.path = path
        super().__init__(
            f"the tutorial project for '{key.tutorial_id}' is no longer at {path}; "
            "the session has been discarded and the tutorial can be started again"
        )


class AnotherSessionActiveError(TutorialSessionError):
    """One tutorial runs at a time (FR-043); the active one must be left first."""

    def __init__(self, active: TutorialKey, title: str) -> None:
        self.active = active
        self.title = title
        super().__init__(
            f"'{title}' is already running; one tutorial runs at a time, so leave it before starting another"
        )


class TutorialUnavailableError(TutorialSessionError):
    """The tutorial cannot be started, and says why (FR-024, FR-007a)."""

    def __init__(self, key: TutorialKey, reason: str) -> None:
        self.key = key
        self.reason = reason
        super().__init__(f"tutorial '{key.tutorial_id}' cannot be started: {reason}")


class SessionStatus(StrEnum):
    """The status the HTTP contract reports (checklist §6.1.6)."""

    ACTIVE = "active"
    COMPLETE = "complete"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Injected ports — everything that lives in the API layer
# ---------------------------------------------------------------------------


@runtime_checkable
class ProjectProvisioner(Protocol):
    """Creates and deletes tutorial projects on the session's behalf.

    A tutorial project must be recorded in the known-projects registry
    (FR-063) and carry the tutorial marker (FR-064), which only the API runtime
    can do. The session decides *when* a project is created or destroyed and
    hands over a :class:`~scistudio.tutorials.projects.TutorialProjectPlan`
    naming exactly where and under what name, so the two halves of FR-062 and
    FR-066 stay on one side of the boundary each.
    """

    def create(self, plan: TutorialProjectPlan) -> Path:
        """Create the planned project and return its directory."""
        ...

    def delete(self, key: TutorialKey, path: Path) -> None:
        """Remove a tutorial project and its known-projects entry (FR-066)."""
        ...


@runtime_checkable
class ReplayHandle(Protocol):
    """A :class:`~scistudio.tutorials.actions.ReplayDelivery` that names its tab.

    Checklist §6.1.7's byte source, plus the tab id the frontend attaches to,
    which is the ``replay`` field of the session response and the only thing
    the session needs to know about a replay beyond driving it.
    """

    @property
    def surface(self) -> str: ...

    @property
    def tab_id(self) -> str: ...

    def deliver(self, segment: ReplaySegment, payload: bytes) -> None: ...

    def close(self) -> None: ...


def _no_provisioner(plan: TutorialProjectPlan) -> Path:
    raise TutorialSessionError(
        f"tutorial '{plan.key.tutorial_id}' declares a bootstrap and so needs a project, "
        "but no project provisioner was supplied to the runtime"
    )


class _RefusingProvisioner:
    """The default provisioner: refuses, with the reason.

    A tutorial that declares no ``bootstrap`` never reaches it (FR-009), so the
    runtime is usable without one; a tutorial that does gets a clear failure
    rather than a project the known-projects registry has never heard of, which
    would fail the path-containment checks several routes perform (FR-063).
    """

    def create(self, plan: TutorialProjectPlan) -> Path:
        return _no_provisioner(plan)

    def delete(self, key: TutorialKey, path: Path) -> None:
        delete_tutorial_project(path)


# ---------------------------------------------------------------------------
# Persistence (FR-037)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SessionRecord:
    """One tutorial's session, active or preserved for resumption (FR-090)."""

    key: TutorialKey
    title: str
    project_path: Path | None = None
    step_id: str | None = None
    step_entered_at: str | None = None
    """When ``step_id`` was entered (ISO-8601, UTC) — ``since_step_entry``'s anchor (#2066).

    Persisted beside the step id so the scoping survives a backend restart the
    way the position does (FR-037). A record written before the field existed
    reads back ``None``, and the run terms then apply no time filter."""
    satisfied_step_ids: tuple[str, ...] = ()
    status: SessionStatus = SessionStatus.ACTIVE
    error: str | None = None

    def satisfied(self, step_id: str) -> SessionRecord:
        """Return this record with *step_id* recorded as satisfied, once."""
        if step_id in self.satisfied_step_ids:
            return self
        return replace(self, satisfied_step_ids=(*self.satisfied_step_ids, step_id))

    def as_json(self) -> dict[str, Any]:
        return {
            "source_kind": self.key.source_kind,
            "source_id": self.key.source_id,
            "tutorial_id": self.key.tutorial_id,
            "title": self.title,
            "project_path": None if self.project_path is None else str(self.project_path),
            "step_id": self.step_id,
            "step_entered_at": self.step_entered_at,
            "satisfied_step_ids": list(self.satisfied_step_ids),
            "status": str(self.status),
            "error": self.error,
        }

    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> SessionRecord | None:
        """Return the record *raw* describes, or ``None`` when it is unreadable.

        Unreadable rather than raising, for the reason
        :class:`~scistudio.tutorials.progress.ProgressStore` treats a corrupt
        progress file as empty: the worst a dropped session costs is restarting
        a tutorial, while refusing to load would make the Learning Center
        unopenable.
        """
        try:
            key = TutorialKey(
                source_kind=str(raw["source_kind"]),
                source_id=str(raw.get("source_id") or ""),
                tutorial_id=str(raw["tutorial_id"]),
            )
            status = SessionStatus(str(raw.get("status") or SessionStatus.ACTIVE))
        except (KeyError, ValueError, TypeError):
            return None
        project = raw.get("project_path")
        satisfied = raw.get("satisfied_step_ids")
        step_id = raw.get("step_id")
        entered = raw.get("step_entered_at")
        return cls(
            key=key,
            title=str(raw.get("title") or key.tutorial_id),
            project_path=Path(str(project)) if project else None,
            step_id=str(step_id) if isinstance(step_id, str) and step_id else None,
            step_entered_at=str(entered) if isinstance(entered, str) and entered else None,
            satisfied_step_ids=tuple(str(item) for item in satisfied) if isinstance(satisfied, list) else (),
            status=status,
            error=str(raw["error"]) if raw.get("error") else None,
        )


def _key_from_json(raw: Any) -> TutorialKey | None:
    """Return the key *raw* describes, or ``None`` when it is not one."""
    if not isinstance(raw, Mapping):
        return None
    try:
        return TutorialKey(
            source_kind=str(raw["source_kind"]),
            source_id=str(raw.get("source_id") or ""),
            tutorial_id=str(raw["tutorial_id"]),
        )
    except (KeyError, ValueError, TypeError):
        return None


@dataclass(frozen=True)
class SessionState:
    """Every stored session, plus which one is active (FR-043)."""

    records: tuple[SessionRecord, ...] = ()
    active_key: TutorialKey | None = None

    def record(self, key: TutorialKey | None) -> SessionRecord | None:
        if key is None:
            return None
        for record in self.records:
            if record.key == key:
                return record
        return None

    @property
    def active(self) -> SessionRecord | None:
        return self.record(self.active_key)

    def started_keys(self) -> frozenset[TutorialKey]:
        """Keys whose session exists and has not finished — the catalogue's ``in_progress``."""
        return frozenset(record.key for record in self.records if record.status is SessionStatus.ACTIVE)

    def with_record(self, record: SessionRecord) -> SessionState:
        others = tuple(existing for existing in self.records if existing.key != record.key)
        return replace(self, records=(*others, record))

    def without(self, key: TutorialKey) -> SessionState:
        remaining = tuple(existing for existing in self.records if existing.key != key)
        active = None if self.active_key == key else self.active_key
        return SessionState(records=remaining, active_key=active)

    def with_active(self, key: TutorialKey | None) -> SessionState:
        return replace(self, active_key=key)


class SessionStore:
    """The ``~/.scistudio/`` session file, read and written per operation (FR-037).

    Re-read rather than cached, for :class:`ProgressStore`'s reason: the desktop
    shell and the API process can both be looking at it, and a cached copy would
    let one report a session the other has already ended.
    """

    def __init__(self, root: Path | None = None) -> None:
        self._root = root

    @property
    def root(self) -> Path:
        """The directory holding the session file, resolved per access."""
        return self._root or user_library_dir()

    @property
    def path(self) -> Path:
        return self.root / SESSION_FILENAME

    def read(self) -> SessionState:
        """Return the stored state, or an empty one when there is none."""
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return SessionState()
        except (OSError, ValueError):
            logger.warning(
                "Learning Center: unreadable session file %s; treating as no session", self.path, exc_info=True
            )
            return SessionState()
        if not isinstance(raw, dict):
            return SessionState()
        entries = raw.get("sessions")
        parsed: list[SessionRecord] = []
        if isinstance(entries, list):
            for item in entries:
                record = SessionRecord.from_json(item) if isinstance(item, Mapping) else None
                if record is not None:
                    parsed.append(record)
        state = SessionState(records=tuple(parsed), active_key=_key_from_json(raw.get("active")))
        # An active key naming a record that did not survive parsing is dropped
        # rather than kept dangling, so ``active`` and ``sessions`` cannot
        # disagree about what is running.
        return state if state.active is not None else state.with_active(None)

    def write(self, state: SessionState) -> None:
        """Persist *state*, creating ``~/.scistudio/`` if it is not there yet."""
        self.root.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "version": _SCHEMA_VERSION,
            "sessions": [record.as_json() for record in state.records],
            "active": None
            if state.active_key is None
            else {
                "source_kind": state.active_key.source_kind,
                "source_id": state.active_key.source_id,
                "tutorial_id": state.active_key.tutorial_id,
            },
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def clear(self) -> None:
        """Delete every stored session (part of clearing tutorial data, FR-088)."""
        self.path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# What the route layer renders
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReplayView:
    """The active replay, if one is playing (checklist §6.1.6 ``replay``)."""

    surface: str
    tab_id: str


@dataclass(frozen=True)
class SessionView:
    """One session as the HTTP contract reports it (checklist §6.1.6).

    Carries no field naming the driver, which is FR-040 stated as a shape: a
    manifest tutorial and a package tutorial produce the same type with the same
    fields, distinguishable only by their content.
    """

    source_kind: str
    source_id: str
    tutorial_id: str
    title: str
    project_path: Path | None
    step: StepView | None
    satisfied_step_ids: tuple[str, ...]
    status: SessionStatus
    error: str | None
    replay: ReplayView | None = None

    @property
    def key(self) -> TutorialKey:
        return TutorialKey(source_kind=self.source_kind, source_id=self.source_id, tutorial_id=self.tutorial_id)


# ---------------------------------------------------------------------------
# The runtime (FR-036)
# ---------------------------------------------------------------------------


class TutorialRuntime:
    """The backend's tutorial runtime: the catalogue, the session, the events.

    One object serves every endpoint in checklist §6.1.6, and holds no state of
    its own beyond the currently open replay handle — which cannot be persisted,
    because it is a live PTY-shaped byte source. Everything else is read from
    the session file and the progress file at the start of each call, so two
    processes holding a runtime cannot disagree about what is running.
    """

    def __init__(
        self,
        *,
        product_state: Callable[[], ProductState],
        external_events: ExternalEventNames,
        project_dir: Callable[[], Path | None] | None = None,
        provisioner: ProjectProvisioner | None = None,
        environment: DiscoveryEnvironment | None = None,
        progress: ProgressStore | None = None,
        sessions: SessionStore | None = None,
        open_replay: Callable[[str], ReplayHandle] | None = None,
        record_ui_event: Callable[[str, str | None], None] | None = None,
        forget_ui_events: Callable[[], None] | None = None,
        files_written: Callable[[Sequence[Path]], None] | None = None,
    ) -> None:
        """Wire the runtime to the API layer's implementations of its ports.

        Args:
            product_state: Returns the current :class:`ProductState` to judge
                conditions against. Called per evaluation rather than held, so
                a project switch is seen without re-wiring.
            external_events: The two FR-050 event names that live under
                ``scistudio.api`` (checklist §6.1.5).
            project_dir: The open project, for the project-level tutorial tier.
            provisioner: Creates and deletes tutorial projects (FR-062, FR-066).
            environment: What ``requires`` is judged against; the real
                environment by default.
            progress: The progress store; the real one by default.
            sessions: The session store; the real one by default.
            open_replay: Opens a byte source for a replay surface
                (checklist §6.1.7). A tutorial declaring no replay never needs
                one.
            record_ui_event: Records a frontend-reported user-interface event
                into product state before it is judged (FR-052), together with
                the optional target it acted on (#2063). The API layer owns
                that state, so recording is its job and this is the hook.
            forget_ui_events: Drops the recorded events on step entry, so a
                ``ui_event`` condition asks whether the reader did the thing
                *on this step*. A reported event is a moment, not a state: the
                third step asks the reader to click a block, and without this
                the tenth step — which asks them to click one again — was
                satisfied before they arrived, by the click they made seven
                steps earlier.
            files_written: Called with the project paths a bootstrap or a step
                just wrote, before the step's text becomes readable (FR-059).
                Writing a block file is not the same as the product having the
                block, and only the API layer knows which directories its
                registries scan — see :meth:`_settle`.
        """
        self._product_state = product_state
        self._external = external_events
        self._project_dir = project_dir or (lambda: None)
        self._provisioner: ProjectProvisioner = provisioner or _RefusingProvisioner()
        self._environment = environment
        self._progress = progress or ProgressStore()
        self._sessions = sessions or SessionStore()
        self._open_replay = open_replay
        self._record_ui_event = record_ui_event
        self._forget_ui_events = forget_ui_events
        self._files_written = files_written
        self._replay: ReplayHandle | None = None

    # -- discovery and the catalogue -------------------------------------

    @property
    def progress_store(self) -> ProgressStore:
        """The progress store, for the unlock and clear endpoints."""
        return self._progress

    @property
    def session_store(self) -> SessionStore:
        """The session store, for the clear endpoint."""
        return self._sessions

    def discover(self) -> DiscoveryResult:
        """Run one discovery pass over all four sources (FR-016).

        Imports no package module (FR-018) and holds no cache, so a package
        installed or uninstalled a moment ago is reflected without a refresh
        hook of its own — which is how tutorials join the refresh path of
        FR-031 rather than building a fourth one.
        """
        return discover_tutorials(project_dir=self._project_dir(), environment=self._environment)

    def catalogue(self) -> Catalogue:
        """Return the grouped catalogue, core first, no aggregate (FR-076, FR-084)."""
        return build_catalogue(
            self.discover(),
            progress=self._progress,
            in_progress=self._sessions.read().started_keys(),
        )

    def progress_groups(self) -> tuple[CatalogueGroup, ...]:
        """Return the per-source counts ``GET /progress`` reports (FR-076).

        The same groups the catalogue carries: a total is the number of
        tutorials a source currently ships, which only a discovery pass knows,
        so there is no cheaper answer to give and no second one to let drift.
        """
        return self.catalogue().groups

    # -- the single session (FR-043) -------------------------------------

    def active_session(self) -> SessionView | None:
        """Return the active session, or ``None``.

        Invalidates and discards a session whose tutorial project has been
        deleted outside the product (FR-069) rather than reporting a session
        that cannot be acted on.

        Judges the current step on the way out (FR-054a). Reporting the step
        without judging it would answer "not yet" to a step the user finished
        while the Learning Center was closed, and the continue control drawn
        from that answer would be dead with no way to tell why — the reader did
        the work and the product says they did not. Judging is a side-effect-free
        read (FR-055), so asking on every render is a question rather than an
        action.
        """
        try:
            _, record = self._active(self._sessions.read())
        except NoActiveSessionError:
            return None
        if record.status is not SessionStatus.ACTIVE:
            return self._view(record)
        if not self._is_live(record):
            # Dormant: the tutorial's project is not the open one, so nothing is
            # running right now. Answering with the session would put its step
            # card over the user's own project and let anything reading the
            # session — a step's `prefill`, for one — act on it there. The
            # record is untouched, and reopening the tutorial resumes it.
            return None
        try:
            state, record, driver, tutorial_dir = self._resolved()
        except NoActiveSessionError:
            return None
        except TutorialSessionError:
            # ``_resolved`` has already ended the session and recorded why;
            # reporting that is the whole point of asking.
            ended = self._sessions.read().active
            return None if ended is None else self._view(ended)
        return self._reevaluate(state, record, driver, tutorial_dir)

    def start(self, key: TutorialKey, *, restart: bool = False) -> SessionView:
        """Start, resume, or restart *key*'s tutorial (FR-043, FR-066, FR-087).

        Raises:
            AnotherSessionActiveError: Another tutorial is running (FR-043).
            TutorialUnavailableError: The tutorial is not installed, is
                unreadable, or its requirements are unmet (FR-024, FR-007a).
        """
        state = self._sessions.read()
        active = state.active
        if active is not None and active.status is SessionStatus.ACTIVE and active.key != key:
            raise AnotherSessionActiveError(active.key, active.title)

        tutorial = self.discover().find(key)
        if tutorial is None:
            raise TutorialUnavailableError(key, "no tutorial with that identity is installed")
        if tutorial.unavailable_reason is not None:
            raise TutorialUnavailableError(key, tutorial.unavailable_reason)
        manifest = tutorial.manifest
        if manifest is None:  # pragma: no cover - is_startable already covers this
            raise TutorialUnavailableError(key, "its manifest could not be read")

        existing = state.record(key)
        if existing is not None and not restart and existing.status is SessionStatus.ACTIVE:
            return self._resume(state, existing, tutorial.directory, manifest, key)

        state = self._discard(state, existing, key=key, restart=restart)
        project = self._provision(manifest, key)
        record = SessionRecord(key=key, title=manifest.title, project_path=project)
        state = state.with_record(record).with_active(key)
        self._sessions.write(state)

        try:
            driver = self._load(manifest, key)
        except DriverError as exc:
            # FR-021/FR-044: a package driver that will not import breaks its own
            # tutorial and nothing else, and the user is told which one.
            return self._view(self._fail(state, record, str(exc)))

        try:
            self._bootstrap(manifest, record, tutorial.directory)
        except ActionExecutionError as exc:
            return self._view(self._fail(state, record, str(exc)))

        return self._advance_from(
            state, record, driver, tutorial.directory, self._context(record, tutorial.directory, None)
        )

    def continue_active(self) -> SessionView:
        """Advance to the next step on the user's explicit continue (FR-012, FR-054a).

        The only thing that moves a session forward. Re-evaluates first so the
        decision is made against the world as it is right now rather than
        against whatever the last event left recorded, and refuses — by
        returning the current step unchanged — when the step is neither
        satisfied nor a reading step. That refusal is the same rule the frontend
        draws the disabled button from, held on the side that owns the judgment
        (spec §4.1), so a client that lets the button be pressed early cannot
        skip a step.
        """
        state, record, driver, tutorial_dir = self._resolved()
        view = self._reevaluate(state, record, driver, tutorial_dir)
        if view.status is not SessionStatus.ACTIVE or view.step is None:
            return view
        if not (view.step.satisfied or view.step.awaiting_continue):
            return view
        state = self._sessions.read()
        current = state.active
        if current is None or current.step_id is None:  # pragma: no cover - the view check covers this
            return view
        satisfied = current.satisfied(current.step_id)
        context = self._context(satisfied, tutorial_dir, current.step_id)
        return self._advance_from(state, satisfied, driver, tutorial_dir, context)

    def evaluate_active(self) -> SessionView:
        """Re-evaluate the active step on explicit request (FR-053).

        The path for state no mapped event reaches: ``file.changed`` is filtered
        to the ADR-036 extension allowlist, so a ``file_exists`` condition on a
        TIFF or a Zarr store is never event-driven.
        """
        state, record, driver, tutorial_dir = self._resolved()
        return self._reevaluate(state, record, driver, tutorial_dir)

    def report_ui_event(self, name: str, target: str | None = None) -> SessionView:
        """Record a frontend user-interface event and re-judge the step (FR-052).

        The only completion path originating in the frontend, and it still
        arrives as backend state: the injected recorder writes it into the
        product state object, and the evaluation that follows reads it there
        like every other term. ``target`` is the optional argument the event
        acted on (#2063) — the block type behind ``node_selected``, the plot id
        behind ``plot_rendered`` — recorded beside the name so a condition may
        wait for *that* element rather than any of its kind.
        """
        if self._record_ui_event is not None:
            self._record_ui_event(name, target)
        return self.evaluate_active()

    def leave_active(self) -> None:
        """Leave the active tutorial, preserving its session (FR-090).

        Terminates any scripted replay on the way out, on the same path ending a
        session uses (FR-061c): the byte source is a live tab, and a preserved
        session cannot preserve one.
        """
        state = self._sessions.read()
        self._close_replay()
        if state.active_key is None:
            return
        self._sessions.write(state.with_active(None))

    # -- events (FR-050, FR-051) -----------------------------------------

    def subscribed_event_types(self) -> tuple[str, ...]:
        """Return exactly the event types FR-050 maps, from the declared constants.

        The route layer subscribes to these and calls :meth:`handle_event`. It
        is the whole of the runtime's connection to the bus: there is no timer
        and no background task anywhere in this module (FR-051).
        """
        return tuple(build_event_term_map(self._external))

    def handle_event(self, event_type: str) -> SessionView | None:
        """Re-evaluate the active step if *event_type* can change its answer (FR-050).

        Returns ``None`` when nothing happened — an unmapped event, no active
        session, or a step none of the event's terms reach — so the caller can
        skip pushing an unchanged session to the frontend.

        A driver that can name its step's condition is only re-evaluated for
        events whose terms it uses; one that cannot is re-evaluated for every
        mapped event. Both produce the same responses, which is what FR-040
        constrains, and evaluation is side-effect free (FR-055), so the extra
        reads cost nothing observable.
        """
        terms = build_event_term_map(self._external).get(event_type)
        if not terms:
            return None
        try:
            state, record, driver, tutorial_dir = self._resolved()
        except NoActiveSessionError:
            return None
        except TutorialSessionError:
            return None
        if record.step_id is not None:
            condition = driver.condition(self._context(record, tutorial_dir, record.step_id))
            if condition is not None and not (condition.terms() & terms):
                return None
        return self._reevaluate(state, record, driver, tutorial_dir)

    # -- clearing (FR-073, FR-088) ---------------------------------------

    def clear_preview(self) -> tuple[Path, ...]:
        """Return the directories clearing tutorial data would delete (FR-088)."""
        return clear_preview()

    def clear_data(self) -> tuple[Path, ...]:
        """Delete tutorial projects, the scoped library, progress, and sessions.

        Returns the directories that were removed, so the confirmation the user
        agreed to and the report they get back name the same things.
        """
        self._close_replay()
        removed = clear_tutorial_data()
        self._progress.clear()
        self._sessions.clear()
        return removed

    # -- internals -------------------------------------------------------

    def _active(self, state: SessionState) -> tuple[SessionState, SessionRecord]:
        """Return the active record, invalidating it if its project is gone (FR-069)."""
        record = state.active
        if record is None:
            raise NoActiveSessionError("no tutorial session is active")
        if record.project_path is not None and not tutorial_project_exists(record.project_path):
            self._close_replay()
            self._sessions.write(state.without(record.key))
            raise SessionInvalidatedError(record.key, record.project_path)
        return state, record

    def _resolved(self) -> tuple[SessionState, SessionRecord, GuardedDriver, Path]:
        """Return the active session with its driver, ending it if its source is gone."""
        state, record = self._active(self._sessions.read())
        tutorial = self.discover().find(record.key)
        if tutorial is None or tutorial.manifest is None:
            # A package uninstalled mid-session: the session ends and reports
            # why, and the tutorial project stays on disk to be removed by
            # clearing like any other (spec §2 Edge Cases).
            ended = self._fail(
                state,
                record,
                f"'{record.title}' is no longer installed, so the session cannot continue; "
                f"its project remains at {record.project_path}",
            )
            raise TutorialUnavailableError(record.key, ended.error or "no longer installed")
        try:
            driver = self._load(tutorial.manifest, record.key)
        except DriverError as exc:
            self._fail(state, record, str(exc))
            raise TutorialUnavailableError(record.key, str(exc)) from exc
        return state, record, driver, tutorial.directory

    def _load(self, manifest: TutorialManifest, key: TutorialKey) -> GuardedDriver:
        return load_driver(manifest, key)

    def _provision(self, manifest: TutorialManifest, key: TutorialKey) -> Path | None:
        """Create the tutorial's project, if it declares a bootstrap (FR-009, FR-062)."""
        if not manifest.creates_project:
            return None
        return self._provisioner.create(plan_tutorial_project(key, manifest.title))

    def _bootstrap(self, manifest: TutorialManifest, record: SessionRecord, tutorial_dir: Path) -> None:
        """Run the ``bootstrap`` block's actions into the freshly created project.

        Before the first step is entered, because a bootstrap exists to put the
        project into the state the first step's text assumes — the same reason
        FR-059 orders a step's own actions before its text.
        """
        bootstrap = manifest.bootstrap
        if bootstrap is None or not bootstrap.do:
            return
        written = execute_actions(
            bootstrap.do,
            context=ActionContext(tutorial_dir=tutorial_dir, project_dir=record.project_path),
            step_id="bootstrap",
            delivery=self._delivery_for(bootstrap.do, step_id="bootstrap"),
        )
        self._settle(written)

    def _discard(
        self,
        state: SessionState,
        existing: SessionRecord | None,
        *,
        key: TutorialKey,
        restart: bool,
    ) -> SessionState:
        """Drop a finished or restarted session, deleting its project on restart (FR-066).

        The project is deleted on restart whether or not a session record
        survives, because the directory is a pure function of the identity
        (:func:`~scistudio.tutorials.projects.tutorial_project_path`) and a
        completed tutorial whose record was cleared would otherwise be restarted
        into its own leftovers.
        """
        self._close_replay()
        if restart:
            path = (existing.project_path if existing is not None else None) or tutorial_project_path(key)
            self._provisioner.delete(key, path)
        return state if existing is None else state.without(existing.key)

    def _resume(
        self,
        state: SessionState,
        record: SessionRecord,
        tutorial_dir: Path,
        manifest: Any,
        key: TutorialKey,
    ) -> SessionView:
        """Resume a preserved session, re-judging where it left off (FR-037, FR-090).

        Entry actions are not re-run: they already landed, and FR-058's designed
        scenario has a step whose action breaks the workflow, which running twice
        would break twice. The step is re-judged instead, which is what makes a
        condition satisfied while the Learning Center was closed — or while the
        backend was down — not lost.
        """
        driver = self._load(manifest, key)
        state = state.with_active(key)
        self._sessions.write(state)
        return self._reevaluate(state, record, driver, tutorial_dir)

    def _is_live(self, record: SessionRecord) -> bool:
        """Is this session's own project the one the product has open?

        A session is bound to the project it created (FR-062). Everything that
        judges a step reads *the open project* — the workflow being edited, the
        registries, the run history, the files on disk — because that is where
        product truth lives and there is no way to read another project's live
        state. So while some other project is open, the tutorial is not merely
        invisible: its conditions would be judged against the user's own work.
        A user who happens to keep ``blocks/normalize_fluorescence.py`` in their
        project would find tutorial steps completing themselves in it.

        A session whose project is closed is dormant, not over. The record and
        its progress survive, and reopening the tutorial puts the reader back on
        the same step in the same project, which is what SC-007 already
        promises.

        A tutorial with no ``bootstrap`` has no project of its own and is never
        gated: a reading tutorial belongs to no project, so there is nothing for
        it to disagree with.
        """
        if record.project_path is None:
            return True
        open_dir = self._project_dir()
        if open_dir is None:
            return False
        try:
            return record.project_path.resolve() == open_dir.resolve()
        except OSError:
            # An unreadable path is not a match; judging is never the safe
            # answer to a question that could not be asked (FR-055's spirit).
            return False

    def _context(self, record: SessionRecord, tutorial_dir: Path, step_id: str | None) -> DriverContext:
        # The entry time belongs to the step the session is *on*: asking about
        # any other step gets no anchor, because the session never recorded one
        # for it (#2066).
        entered = record.step_entered_at if step_id is not None and step_id == record.step_id else None
        return DriverContext(
            key=record.key,
            tutorial_dir=tutorial_dir,
            project_dir=record.project_path,
            step_id=step_id,
            satisfied_step_ids=record.satisfied_step_ids,
            step_entered_at=entered,
        )

    def _reevaluate(
        self,
        state: SessionState,
        record: SessionRecord,
        driver: GuardedDriver,
        tutorial_dir: Path,
    ) -> SessionView:
        """Judge the current step and report it, without moving (FR-053, FR-054a).

        Judging and advancing are separate concerns as of FR-054a: this answers
        "is this step's condition met" and records that on the step view, and
        only :meth:`continue_active` moves the session. Every caller — the
        explicit re-check, a mapped engine event, a reported UI event — lands
        here, so none of them can move the user out from under a step they are
        still reading.
        """
        if record.status is not SessionStatus.ACTIVE or record.step_id is None:
            return self._view(record)
        context = self._context(record, tutorial_dir, record.step_id)
        if not self._is_live(record):
            # Report the step, judge nothing. See :meth:`_is_live`: the product
            # state available right now describes a different project, and an
            # answer read out of it would be about the user's own work.
            return self._view(record, step=self._step_of(record, driver, tutorial_dir, satisfied=False))
        try:
            satisfied = driver.is_satisfied(context, self._product_state())
        except Exception as exc:
            return self._view(self._fail(state, record, self._driver_failure(record, exc)))
        if satisfied:
            record = record.satisfied(record.step_id)
        self._sessions.write(state.with_record(record).with_active(record.key))
        return self._view(record, step=self._step_of(record, driver, tutorial_dir, satisfied=satisfied))

    def _advance_from(
        self,
        state: SessionState,
        record: SessionRecord,
        driver: GuardedDriver,
        tutorial_dir: Path,
        context: DriverContext,
    ) -> SessionView:
        """Enter the step after *context* and stop there (FR-054a).

        One step per call, never a walk. Advancing is the user's action as of
        FR-054a, so entering two steps because the first one's condition already
        held would skip past text they never saw — which is exactly the failure
        the old auto-advance loop produced when a step's own entry action left
        its condition true.

        The step's entry is ``do`` → evaluate → reveal: the actions run to
        completion first (FR-056, FR-059), the condition is judged afterwards so
        the Continue button's state reflects the world the actions left behind
        (FR-054 against FR-058), and the step view is produced last, which is
        why the evaluation lives inside
        :func:`~scistudio.tutorials.actions.perform_step_entry`'s ``reveal``
        rather than around the call.
        """
        try:
            next_id = driver.advance(context)
            if next_id is None:
                return self._view(self._complete(state, record))
            # The entry stamp is written before the step's own actions run, so
            # a run those actions cause counts as "since entry" (#2066).
            record = replace(record, step_id=next_id, step_entered_at=_now_iso())
            context = self._context(record, tutorial_dir, next_id)
            satisfied = self._enter(record, driver, context, tutorial_dir)
            if satisfied:
                record = record.satisfied(next_id)
            self._sessions.write(state.with_record(record).with_active(record.key))
            return self._view(record, step=self._step_of(record, driver, tutorial_dir, satisfied=satisfied))
        except ActionExecutionError as exc:
            # FR-060: name the step and the action, and do not advance.
            return self._view(self._fail(state, record, str(exc)))
        except Exception as exc:
            return self._view(self._fail(state, record, self._driver_failure(record, exc)))

    def _enter(
        self,
        record: SessionRecord,
        driver: GuardedDriver,
        context: DriverContext,
        tutorial_dir: Path,
    ) -> bool:
        """Run a step's entry and return whether it is satisfied on arrival.

        The ordering the manager ruled on and the spec leaves open: the actions
        land, then the condition is judged, then the step becomes readable.
        """
        step_id = context.step_id or ""
        # A ui_event belongs to the step that asked for it. See
        # ``forget_ui_events`` in :meth:`__init__`.
        if self._forget_ui_events is not None:
            self._forget_ui_events()
        actions = driver.entry_actions(context)
        action_context = ActionContext(tutorial_dir=tutorial_dir, project_dir=record.project_path)
        delivery = self._delivery_for(actions, step_id=step_id)
        product = self._product_state()

        def _judge_then_reveal() -> bool:
            satisfied = driver.is_satisfied(context, product)
            driver.step_view(context)
            return satisfied

        return perform_step_entry(
            actions,
            context=action_context,
            step_id=step_id,
            reveal=_judge_then_reveal,
            delivery=delivery,
            settle=self._settle,
        )

    def _settle(self, written: Sequence[Path]) -> None:
        """Let the product take in what a step just wrote, before its text is read.

        A step that writes ``blocks/normalize_fluorescence.py`` and then says
        "find Normalize Fluorescence in the palette" is unfollowable until the
        block registry has re-scanned: the file is there and the block is not.
        The API layer owns the registries and is the only side that knows which
        directories they scan, so it decides what a written path means; this is
        the hook it is handed. A runtime wired without one writes files and
        nothing else, which is what every test that does not care about the
        registries gets.
        """
        if self._files_written is None or not written:
            return
        self._files_written(tuple(written))

    def _delivery_for(self, actions: Iterable[Action], *, step_id: str) -> ReplayHandle | None:
        """Open a byte source when a step replays, and only then (checklist §6.1.7)."""
        replay = next((action for action in actions if isinstance(action, ReplayAction)), None)
        if replay is None:
            return None
        if self._open_replay is None:
            raise ActionExecutionError(
                step_id=step_id,
                action=replay,
                reason="no replay byte source is wired into the tutorial runtime",
            )
        self._close_replay()
        self._replay = self._open_replay(replay.surface)
        return self._replay

    def _close_replay(self) -> None:
        """Terminate a scripted session, leaving no replay object behind (FR-061c)."""
        handle, self._replay = self._replay, None
        if handle is None:
            return
        try:
            handle.close()
        except Exception:  # pragma: no cover - closing must not mask the real outcome
            logger.warning("Learning Center: failed to close a replay session", exc_info=True)

    def _complete(self, state: SessionState, record: SessionRecord) -> SessionRecord:
        """End a session that reached the end of its tutorial (FR-079)."""
        self._close_replay()
        finished = replace(record, status=SessionStatus.COMPLETE, step_id=None, error=None)
        self._progress.mark_completed(record.key)
        self._sessions.write(state.with_record(finished).with_active(finished.key))
        return finished

    def _fail(self, state: SessionState, record: SessionRecord, message: str) -> SessionRecord:
        """End a session with an error, without marking the tutorial complete (FR-044)."""
        self._close_replay()
        failed = replace(record, status=SessionStatus.ERROR, error=message)
        self._sessions.write(state.with_record(failed).with_active(failed.key))
        return failed

    @staticmethod
    def _driver_failure(record: SessionRecord, exc: BaseException) -> str:
        """FR-044's message: the tutorial and the exception, both named."""
        return f"'{record.title}' stopped: {type(exc).__name__}: {exc}"

    def _step_of(
        self,
        record: SessionRecord,
        driver: GuardedDriver,
        tutorial_dir: Path,
        *,
        satisfied: bool = False,
    ) -> StepView | None:
        """Return the current step's view, or ``None`` when the session is not on one.

        ``satisfied`` is supplied by the caller that just judged the step rather
        than re-derived here, for the reason FR-055 gives: judging is a read of
        the whole product, and rendering a response is not a place to run one
        again. It is attached after the driver has produced the view because it
        is not a driver's to report — it is the runtime's answer about the
        driver's condition, and FR-041 keeps the driver's field set closed.
        """
        if record.status is not SessionStatus.ACTIVE or record.step_id is None:
            return None
        view = driver.step_view(self._context(record, tutorial_dir, record.step_id))
        return replace(view, satisfied=satisfied)

    def _view(self, record: SessionRecord, *, step: StepView | None = None) -> SessionView:
        """Render a record. The step view is supplied by whoever holds the driver.

        Passed in rather than fetched, so rendering a response never re-runs
        discovery and never re-imports a package driver (FR-021): the caller
        already has both.
        """
        replay = (
            ReplayView(surface=self._replay.surface, tab_id=self._replay.tab_id) if self._replay is not None else None
        )
        return SessionView(
            source_kind=record.key.source_kind,
            source_id=record.key.source_id,
            tutorial_id=record.key.tutorial_id,
            title=record.title,
            project_path=record.project_path,
            step=step,
            satisfied_step_ids=record.satisfied_step_ids,
            status=record.status,
            error=record.error,
            replay=replay,
        )
