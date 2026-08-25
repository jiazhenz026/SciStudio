"""The driver interface, core's manifest driver, and package driver loading.

ADR-053 Learning Center spec, FR-038 … FR-042 and FR-021/FR-044
(``docs/specs/adr-053-learning-center.md``).

One runtime, two drivers. The runtime knows nothing about YAML: it asks a
driver four questions, which are exactly FR-038's four (view of the current
step, satisfied given current product state, actions to perform on entering a
step, and whether the tutorial has ended). Core ships :class:`ManifestDriver`,
which answers them by reading a ``tutorial.yaml``, and is the driver for every
core, user-level, and project-level tutorial (FR-039). A package may ship a
class implementing the same interface and keep full control of its tutorial's
logic (FR-040).

**The runtime cannot tell which one it is talking to (FR-040).** No response
field reveals the driver, because there is no field for it to reveal: what a
driver returns is normalized into :class:`StepView` before anything else sees
it, and :class:`StepView` is exactly FR-011's fields. That is FR-041 enforced
structurally rather than by convention — :meth:`StepView.of` reads the seven
names it knows and constructs a fresh :class:`StepView`, so a driver returning
a subclass with extra attributes, or a mapping with extra keys, has those
dropped at the boundary instead of leaking into an API response. A driver
therefore cannot introduce a rendering primitive, supply a frontend asset, or
address a surface the manifest format cannot address. Core owns what a step
looks like.

**Cursor position lives in the session, not the driver.** A driver is asked
about the step a :class:`DriverContext` names rather than about "its" current
step, which is what makes FR-037's survival across a backend restart possible
without every package driver having to persist anything: the session persists
the step id and hands it back. It is also why :meth:`TutorialDriver.advance`
called with ``step_id=None`` returns the *first* step — the step after nothing
is the beginning — so the same method covers starting, advancing, and FR-038's
"whether the tutorial has ended", which is ``advance`` returning ``None``.

**A package driver is imported only when the user starts that tutorial**
(FR-021). :func:`load_driver` is the only import site in this package, it is
reached from the session's start path and from nowhere in discovery, and an
import failure is raised as :class:`DriverLoadError` naming the tutorial, which
the session turns into a session-ending error contained to that tutorial
(FR-044).

**A package driver may call the core evaluator** (FR-042):
:func:`scistudio.tutorials.conditions.evaluate` and
:func:`~scistudio.tutorials.conditions.parse_condition` are public, so a driver
implements only the conditions the vocabulary does not cover.

This module may not import :mod:`scistudio.tutorials.session` or
``scistudio.api`` (checklist §6.1.2).
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from typing_extensions import Protocol, runtime_checkable

from scistudio.stability import provisional
from scistudio.tutorials.actions import Action
from scistudio.tutorials.conditions import Condition, ProductState, evaluate
from scistudio.tutorials.manifest import SAY_MOODS, TutorialManifest, TutorialStep, split_say_mood
from scistudio.tutorials.projects import TutorialKey

logger = logging.getLogger(__name__)

__all__ = [
    "STEP_VIEW_FIELDS",
    "DeclaresConditions",
    "DeclaresTriggerActions",
    "DriverContext",
    "DriverContractError",
    "DriverError",
    "DriverLoadError",
    "GuardedDriver",
    "ManifestDriver",
    "StepView",
    "TutorialDriver",
    "guarded",
    "load_driver",
]


class DriverError(RuntimeError):
    """Base for every driver failure the session must contain (FR-044)."""


class DriverLoadError(DriverError):
    """A package driver could not be imported or constructed (FR-021, FR-044).

    Names the tutorial and the underlying exception, because the session's
    error message is the only place a user can learn that a package's tutorial
    is broken rather than absent.
    """

    def __init__(self, key: TutorialKey, reference: str, cause: BaseException) -> None:
        self.key = key
        self.reference = reference
        super().__init__(
            f"tutorial '{key.tutorial_id}' from {key.source_kind} '{key.source_id or 'core'}' "
            f"declares driver '{reference}', which could not be loaded: "
            f"{type(cause).__name__}: {cause}"
        )


class DriverContractError(DriverError):
    """A driver returned something the step view cannot carry (FR-041).

    Raised at the boundary rather than tolerated, because the alternative to
    rejecting an unusable step view is rendering a step with no text and no
    explanation.
    """


# ---------------------------------------------------------------------------
# The step view (FR-011, FR-041)
# ---------------------------------------------------------------------------

#: The fields a step view carries, and the only ones (FR-011, FR-041).
#:
#: ``say``, ``highlight``, ``route_to``, ``prefill``, and the continue flag are
#: the manifest format's whole rendering vocabulary; ``id``, ``index``, and ``total`` are
#: position, which the frontend needs to show progress through a tutorial and
#: which no driver may misreport into a different shape.
STEP_VIEW_FIELDS: tuple[str, ...] = (
    "id",
    "index",
    "total",
    "title",
    "say",
    "say_moods",
    "highlights",
    "route_to",
    "prefill",
    "pages",
    "trigger",
    "compacts",
    "auto_advance",
    "awaiting_continue",
)


@provisional(since="0.3.4")
@dataclass(frozen=True)
class StepView:
    """What one step looks like, for every driver alike (FR-040, FR-041).

    The closed set of fields a driver may influence, and the return type of
    :meth:`TutorialDriver.step_view`. A driver may return this class, any object
    carrying these attributes, or a mapping of them; :meth:`of` reduces all
    three to a plain ``StepView`` and drops anything else, which is what makes a
    package driver and core's :class:`ManifestDriver` indistinguishable to
    everything downstream.

    Only :attr:`id`, :attr:`index` and :attr:`total` are required. The rest
    describe what the step shows and what it is waiting for:

    * :attr:`title`, :attr:`say` — the step's heading and body text.
    * :attr:`highlight` — the product surface to point at; the manifest's
      ``HIGHLIGHT_TARGETS`` names what can be addressed.
    * :attr:`route_to` — the surface to open before the step is readable.
    * :attr:`prefill` — values to seed into a form or editor.
    * :attr:`awaiting_continue` — the step ends on the reader acknowledging it
      rather than on a condition.

    :attr:`satisfied` is **not** a driver's field. A driver reports what a step
    *is*; whether it currently holds is the runtime's answer, attached after
    the driver's view has been reduced.
    """

    id: str
    index: int
    total: int
    title: str | None = None
    #: FR-011 — what the step says, as the ordered beats it is delivered in.
    #: A driver may return one bare line; the boundary widens it to a
    #: single-beat tuple, so drivers predating beats need no change.
    say: tuple[str, ...] = ()
    #: FR-011f (#2136) — one expression per beat, in the same order.
    #:
    #: Usually not written: the boundary reads it off each beat's own prefix,
    #: so a driver that returns lines the way a manifest does gets it for free.
    #: A driver computing its lines may declare it instead, and then it wins.
    say_moods: tuple[str, ...] = ()
    #: FR-089e (#2136) — what each beat points at, one entry per beat.
    #:
    #: A driver that returns the older singular ``highlight`` is understood to
    #: mean the same one for every beat, which is what it did mean.
    highlights: tuple[Mapping[str, Any] | None, ...] = ()
    route_to: str | None = None
    prefill: tuple[Mapping[str, Any], ...] = ()
    #: FR-011 — the reading pages this step presents, in order, served by the
    #: existing pages route. Names only: the content stays on disk and the
    #: core-owned reading surface fetches each page as the reader turns to it.
    pages: tuple[str, ...] = ()
    #: FR-011 / #2061 — the step's user-triggered action, as ``{"label": ...}``.
    #:
    #: The label alone crosses this boundary: what pressing the button *does*
    #: is the runtime's to execute through the trigger endpoint, so a driver
    #: cannot smuggle an action kind or a rendering primitive through the
    #: field, which is what keeps FR-041's closure closed while the set widens
    #: by this one field.
    trigger: Mapping[str, Any] | None = None
    #: FR-011e (#2136) — deliver this step as a chat line rather than a scene.
    #: FR-011e (#2136) — which form each beat is delivered in, one per beat.
    #:
    #: A driver that returns the older singular ``compact`` is understood to
    #: mean the same form for every beat, which is what it did mean.
    compacts: tuple[bool, ...] = ()
    #: FR-054c (#2136) — this step moves on by itself once its condition holds.
    #:
    #: A shape, not content: it picks between two ways of leaving a step that
    #: the runtime already supports, and can say nothing a driver could not
    #: already say by declaring no condition at all. FR-041's closure is about
    #: keeping a driver out of content and out of surfaces, and this is neither.
    auto_advance: bool = False
    awaiting_continue: bool = False
    #: Whether this step's condition currently holds (FR-054d).
    #:
    #: Not a driver's field and not read by :meth:`of`: a driver reports what a
    #: step *is*, and this is the runtime's answer about the world the step is
    #: being judged against. The session attaches it after reducing the driver's
    #: view, which is what keeps :data:`STEP_VIEW_FIELDS` the closed set a
    #: driver may influence.
    satisfied: bool = False

    @classmethod
    def of(cls, raw: Any) -> StepView:
        """Return *raw* as a plain :class:`StepView`, dropping anything else.

        The FR-041 boundary. Accepts an object with the attributes or a mapping
        with the keys, reads exactly :data:`STEP_VIEW_FIELDS`, and constructs a
        new instance — so a driver returning a richer object cannot smuggle a
        field through the runtime into an API response, and a subclass adding
        one is reduced to its base at the same point.
        """
        if isinstance(raw, StepView) and type(raw) is StepView:
            return raw
        read = raw.get if isinstance(raw, Mapping) else (lambda name, default=None: getattr(raw, name, default))
        try:
            step_id = read("id")
            index = read("index")
            total = read("total")
        except Exception as exc:  # pragma: no cover - a mapping-like that raises
            raise DriverContractError(f"a step view could not be read: {type(exc).__name__}: {exc}") from exc
        if not isinstance(step_id, str) or not step_id:
            raise DriverContractError(f"a step view must carry a non-empty string id, got {step_id!r}")
        if not isinstance(index, int) or not isinstance(total, int):
            raise DriverContractError(f"step {step_id!r}: index and total must be integers")
        say, say_moods = _optional_say(read("say"), step_id=step_id)
        return cls(
            id=step_id,
            index=index,
            total=total,
            title=_optional_text(read("title"), step_id=step_id, name="title"),
            say=say,
            say_moods=_optional_say_moods(read("say_moods"), step_id=step_id, beats=len(say), parsed=say_moods),
            highlights=_optional_highlights(read("highlights"), read("highlight"), step_id=step_id, beats=len(say)),
            route_to=_optional_text(read("route_to"), step_id=step_id, name="route_to"),
            prefill=_optional_prefill(read("prefill"), step_id=step_id),
            pages=_optional_pages(read("pages"), step_id=step_id),
            trigger=_optional_trigger(read("trigger"), step_id=step_id),
            compacts=_optional_compacts(read("compacts"), read("compact"), step_id=step_id, beats=len(say)),
            auto_advance=bool(read("auto_advance")),
            awaiting_continue=bool(read("awaiting_continue")),
        )


def _optional_text(value: Any, *, step_id: str, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise DriverContractError(f"step {step_id!r}: {name} must be text or absent, got {type(value).__name__}")
    return value


def _optional_trigger(value: Any, *, step_id: str) -> Mapping[str, Any] | None:
    """Reduce a driver's ``trigger`` to its wire shape — the label — or refuse it.

    Accepts a bare label, an object carrying one (a
    :class:`~scistudio.tutorials.manifest.TutorialTrigger`), or the wire
    mapping itself. Whatever arrives, only ``{"label": ...}`` leaves: the
    actions behind the button are asked for separately through the optional
    ``trigger_actions`` capability, never through the view (FR-041).
    """
    if value is None:
        return None
    label = getattr(value, "label", None)
    if isinstance(value, str):
        label = value
    elif isinstance(value, Mapping):
        label = value.get("label")
    if not isinstance(label, str) or not label:
        raise DriverContractError(f"step {step_id!r}: a trigger must carry a non-empty string label")
    return {"label": label}


def _optional_say(value: Any, *, step_id: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Reduce a driver's ``say`` to its ordered beats and their expressions.

    A bare string is one beat. That is not only the manifest's short form: it is
    what every driver written before beats existed returns, and this boundary
    accepting it is what lets those drivers keep working untouched. Only the
    plural shape leaves.

    The expression is split off here rather than in the manifest parser alone,
    so a package driver writes a beat the same way a manifest author does
    (FR-011f). A driver that already supplies ``say_moods`` itself is not
    overruled — see :meth:`StepView.of`.
    """
    if value is None:
        return (), ()
    if isinstance(value, str):
        value = [value] if value else []
    elif isinstance(value, bytes) or not isinstance(value, Sequence):
        raise DriverContractError(
            f"step {step_id!r}: say must be text, a sequence of lines, or absent, got {type(value).__name__}"
        )
    beats: list[str] = []
    moods: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise DriverContractError(f"step {step_id!r}: each say beat must be a non-empty line")
        mood, line = split_say_mood(item)
        if not line:
            raise DriverContractError(
                f"step {step_id!r}: a say beat is a line, not only the expression to deliver it with"
            )
        beats.append(line)
        moods.append(mood)
    return tuple(beats), tuple(moods)


def _optional_say_moods(value: Any, *, step_id: str, beats: int, parsed: tuple[str, ...]) -> tuple[str, ...]:
    """Take a driver's own ``say_moods`` when it declares them, or the parsed ones.

    A driver computing its lines has nowhere convenient to put a prefix, so the
    field is writable directly. Declaring it replaces the prefixes entirely
    rather than merging with them, because a half-applied override is the one
    outcome nobody could reason about.
    """
    if value is None:
        return parsed
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise DriverContractError(
            f"step {step_id!r}: say_moods must be a sequence of expression names or absent, got {type(value).__name__}"
        )
    moods = list(value)
    if len(moods) != beats:
        raise DriverContractError(
            f"step {step_id!r}: say_moods has {len(moods)} entries for {beats} beat(s); "
            "one expression per beat, in the same order"
        )
    for mood in moods:
        if mood not in SAY_MOODS:
            raise DriverContractError(f"step {step_id!r}: {mood!r} is not an expression; one of {', '.join(SAY_MOODS)}")
    return tuple(str(mood) for mood in moods)


def _optional_pages(value: Any, *, step_id: str) -> tuple[str, ...]:
    """Reduce a driver's ``pages`` to a tuple of page names, or refuse it.

    Names, not content: the reading surface fetches each page from the pages
    route, so what crosses this boundary is only which pages and in what
    order — which is why a driver cannot smuggle rendered content through the
    field (FR-041).
    """
    if value is None:
        return ()
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise DriverContractError(f"step {step_id!r}: pages must be a sequence or absent, got {type(value).__name__}")
    pages: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise DriverContractError(f"step {step_id!r}: each pages entry must be a non-empty string name")
        pages.append(item)
    return tuple(pages)


def _optional_compacts(plural: Any, singular: Any, *, step_id: str, beats: int) -> tuple[bool, ...]:
    """Reduce a driver's compact declaration to one flag per beat (FR-011e).

    Empty counts as unsaid rather than as a length mismatch, for the reason
    :func:`_optional_highlights` gives: `StepView`'s own default is an empty
    tuple, so a driver that never touched the field arrives here with one.
    """
    slots = max(1, beats)
    if plural is None or (isinstance(plural, Sequence) and len(plural) == 0):
        return (bool(singular),) * slots
    if isinstance(plural, str | bytes | Mapping) or not isinstance(plural, Sequence):
        return (bool(plural),) * slots
    entries = list(plural)
    if len(entries) != slots:
        raise DriverContractError(
            f"step {step_id!r}: compacts has {len(entries)} entries for {slots} beat(s); "
            "one per beat, in the same order"
        )
    return tuple(bool(entry) for entry in entries)


def _optional_highlights(
    plural: Any, singular: Any, *, step_id: str, beats: int
) -> tuple[Mapping[str, Any] | None, ...]:
    """Reduce a driver's highlights to one entry per beat (FR-089e).

    Two spellings accepted, because two are already in use. A driver written
    before highlights were per beat returns ``highlight``, one for the whole
    step, and every beat of that step shares it — which is exactly what it
    meant. A driver that wants a different one per beat returns ``highlights``,
    a sequence read beside ``say``. Declaring both takes the plural, since a
    driver that bothered to say it per beat meant it.
    """
    slots = max(1, beats)
    # Empty counts as unsaid, not as a length mismatch: `StepView`'s own default
    # is an empty tuple, so every driver that constructs one without touching
    # this field arrives here with `()` and means "I did not say".
    if plural is None or (isinstance(plural, Sequence) and len(plural) == 0):
        return (_optional_highlight(singular, step_id=step_id),) * slots
    if isinstance(plural, str | bytes | Mapping) or not isinstance(plural, Sequence):
        raise DriverContractError(
            f"step {step_id!r}: highlights must be a sequence with one entry per beat, got {type(plural).__name__}"
        )
    entries = list(plural)
    if len(entries) != slots:
        raise DriverContractError(
            f"step {step_id!r}: highlights has {len(entries)} entries for {slots} beat(s); "
            "one per beat, in the same order"
        )
    return tuple(_optional_highlight(entry, step_id=step_id) for entry in entries)


def _optional_highlight(value: Any, *, step_id: str) -> Mapping[str, Any] | None:
    """Reduce a driver's ``highlight`` to the wire shape, or refuse it.

    Accepts the three forms a driver can reasonably produce: a bare target name,
    a :class:`~scistudio.tutorials.manifest.Highlight`, and the wire mapping
    itself. The bare name is accepted for the same reason the manifest format
    accepts it — a target whose name is already an address should not have to be
    written as a mapping — and a driver author writing Python has exactly the
    same claim on that shorthand as a manifest author writing YAML.

    The target has to be a non-empty string and the arguments a mapping of
    strings, because everything downstream — the API response, the frontend's
    element lookup — treats both as given, and a driver is the one place that
    shape is not already checked.
    """
    if value is None:
        return None
    as_json = getattr(value, "as_json", None)
    if callable(as_json):
        value = as_json()
    if isinstance(value, str):
        value = {"target": value, "args": {}}
    if not isinstance(value, Mapping):
        raise DriverContractError(
            f"step {step_id!r}: highlight must be a target name, a mapping, or absent, got {type(value).__name__}"
        )
    target = value.get("target")
    if not isinstance(target, str) or not target:
        raise DriverContractError(f"step {step_id!r}: a highlight must carry a non-empty string target")
    args = value.get("args") or {}
    if not isinstance(args, Mapping):
        raise DriverContractError(f"step {step_id!r}: highlight args must be a mapping, got {type(args).__name__}")
    return {"target": target, "args": {str(key): str(item) for key, item in args.items()}}


def _optional_prefill(value: Any, *, step_id: str) -> tuple[Mapping[str, Any], ...]:
    """Reduce a driver's ``prefill`` to the wire shape, or refuse it.

    A sequence, because a step may seed more than one dialog. Each member is
    reduced the way a highlight is — a :class:`~scistudio.tutorials.manifest.Prefill`
    or the wire mapping itself — minus the bare-name shorthand, which a prefill
    has no use for: a target with no values to seed would seed nothing.
    """
    if value is None:
        return ()
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise DriverContractError(f"step {step_id!r}: prefill must be a sequence or absent, got {type(value).__name__}")
    reduced: list[Mapping[str, Any]] = []
    for item in value:
        as_json = getattr(item, "as_json", None)
        if callable(as_json):
            item = as_json()
        if not isinstance(item, Mapping):
            raise DriverContractError(f"step {step_id!r}: each prefill must be a mapping, got {type(item).__name__}")
        target = item.get("target")
        if not isinstance(target, str) or not target:
            raise DriverContractError(f"step {step_id!r}: a prefill must carry a non-empty string target")
        args = item.get("args") or {}
        if not isinstance(args, Mapping):
            raise DriverContractError(f"step {step_id!r}: prefill args must be a mapping, got {type(args).__name__}")
        reduced.append({"target": target, "args": {str(key): str(entry) for key, entry in args.items()}})
    return tuple(reduced)


# ---------------------------------------------------------------------------
# The interface (FR-038)
# ---------------------------------------------------------------------------


@provisional(since="0.3.4")
@dataclass(frozen=True)
class DriverContext:
    """Everything a driver is told about the session asking the question.

    Deliberately not the session object: a driver reads position and location
    and nothing else, so it cannot advance the session, end it, or start
    another one. That is what keeps FR-043's one-session rule and FR-044's
    containment properties of the runtime rather than of every driver.
    """

    key: TutorialKey
    tutorial_dir: Path
    project_dir: Path | None
    step_id: str | None
    """The step being asked about. ``None`` means "before the first step"."""
    satisfied_step_ids: tuple[str, ...] = ()
    step_entered_at: str | None = None
    """ISO-8601 time the current step was entered, when the session knows it.

    FR-046's session-supplied evaluation context (#2066): the two run terms
    read it for ``since_step_entry`` scoping. It rides on the context rather
    than on product state because it describes the reader's position in the
    tutorial, which only the session knows — and it survives a backend restart
    the way the step id does, by being persisted in the session record."""


@provisional(since="0.3.4")
@runtime_checkable
class TutorialDriver(Protocol):
    """What a package implements to own its tutorial's logic (FR-038, FR-040).

    Most tutorials need none of this. A ``tutorial.yaml`` written against the
    published schema is run by core's :class:`ManifestDriver`, and that is the
    path to prefer. Implement this protocol only when the tutorial's logic
    cannot be expressed as a manifest — a step judged by a condition the
    vocabulary has no term for, or a sequence that depends on what the reader
    did earlier.

    The protocol is four methods and stays four: the runtime asks what the
    current step looks like, whether it is satisfied, what to do on entering it,
    and which step comes next. There is no fifth question and no hook to add
    one.

    Name the class from the manifest, and it is imported only when a reader
    starts that tutorial (FR-021); an import failure ends that one session and
    leaves every other tutorial listed and startable (FR-044).

    Three properties are worth knowing before writing one, because each removes
    work rather than adding it:

    * **Core owns rendering.** Whatever :meth:`step_view` returns is normalized
      through :meth:`StepView.of` at the boundary, so extra attributes and extra
      mapping keys are dropped rather than reaching a response (FR-041). A
      driver cannot introduce a display primitive or ship a frontend asset, and
      correspondingly never has to describe one.
    * **The session holds the cursor.** A driver is asked about the step a
      :class:`DriverContext` names, not about "its" current step, so it persists
      nothing and survives a backend restart without any state of its own
      (FR-037).
    * **The core evaluator is available.** :func:`~scistudio.tutorials.conditions.evaluate`
      and :func:`~scistudio.tutorials.conditions.parse_condition` are public, so
      :meth:`is_satisfied` can defer every term the vocabulary already covers
      and implement only the remainder (FR-042).

    A driver that answers most steps from its manifest and one step itself::

        from scistudio.tutorials import (
            Condition, DriverContext, ProductState, StepView, evaluate,
        )

        class MyDriver:
            def __init__(self, manifest, key):
                self._steps = list(manifest.steps)

            def step_view(self, context: DriverContext) -> StepView:
                step = self._step(context.step_id)
                index = self._steps.index(step)
                return StepView(
                    id=step.id, index=index, total=len(self._steps),
                    title=step.title, say=step.say,
                )

            def is_satisfied(self, context: DriverContext, product: ProductState) -> bool:
                step = self._step(context.step_id)
                if step.id == "calibration-converged":
                    return self._converged(product)   # no vocabulary term for this
                return step.done_when is None or evaluate(step.done_when, product)

            def entry_actions(self, context: DriverContext):
                return self._step(context.step_id).actions

            def advance(self, context: DriverContext) -> str | None:
                if context.step_id is None:
                    return self._steps[0].id
                nxt = self._steps.index(self._step(context.step_id)) + 1
                return self._steps[nxt].id if nxt < len(self._steps) else None

    Optionally also implement :class:`DeclaresConditions`, which lets the
    session skip re-evaluating a step on events that cannot affect it. It
    changes how often :meth:`is_satisfied` is called and never what the reader
    sees.
    """

    def step_view(self, context: DriverContext) -> Any:
        """Return the view of ``context.step_id``.

        The return value is normalized through :meth:`StepView.of`, so it may
        be a :class:`StepView`, any object carrying its attributes, or a
        mapping — and may carry nothing else (FR-041).
        """
        ...

    def is_satisfied(self, context: DriverContext, product: ProductState) -> bool:
        """Return whether ``context.step_id`` is satisfied by current product state.

        A package driver may answer by calling
        :func:`scistudio.tutorials.conditions.evaluate` for the conditions the
        core vocabulary covers and implementing only the rest (FR-042).
        """
        ...

    def entry_actions(self, context: DriverContext) -> Sequence[Action]:
        """Return the actions to perform on entering ``context.step_id`` (FR-056)."""
        ...

    def advance(self, context: DriverContext) -> str | None:
        """Return the id of the step to enter after ``context.step_id``.

        ``None`` means the tutorial has ended, which is FR-038's fourth
        question. Called with ``context.step_id is None`` to obtain the first
        step, so a tutorial with no steps ends the moment it starts rather than
        needing a separate emptiness check.
        """
        ...


@provisional(since="0.3.4")
@runtime_checkable
class DeclaresTriggerActions(Protocol):
    """An optional capability: a driver whose steps can carry a trigger (#2061).

    Optional for the reason :class:`DeclaresConditions` is: FR-038 fixes the
    driver interface at four questions, and a driver whose steps never declare
    a trigger owes no fifth answer. A driver that *does* put a trigger label in
    its step view answers this with the actions pressing it performs; one that
    labels a trigger but cannot answer has declared a button that does nothing,
    and the runtime refuses the press rather than pretending it worked.
    """

    def trigger_actions(self, context: DriverContext) -> Sequence[Action]:
        """Return the actions behind ``context.step_id``'s trigger."""
        ...


@provisional(since="0.3.4")
@runtime_checkable
class DeclaresConditions(Protocol):
    """An optional capability: a driver that can name a step's condition.

    Not part of :class:`TutorialDriver`, because FR-038 fixes that interface at
    four members and a package driver must be able to implement conditions the
    vocabulary cannot express — which by definition have no
    :class:`~scistudio.tutorials.conditions.Condition` to return.

    A driver that *can* answer lets the session skip re-evaluating on an event
    that maps to none of the step's terms (FR-050). A driver that cannot is
    re-evaluated on every mapped event instead. The two produce identical
    responses, which is what FR-040 constrains; only the number of evaluations
    differs, and evaluation is side-effect free (FR-055).
    """

    def condition(self, context: DriverContext) -> Condition | None:
        """Return the condition ``context.step_id`` is judged by, if it has one."""
        ...


# ---------------------------------------------------------------------------
# Core's manifest driver (FR-039)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ManifestDriver:
    """The driver for every core, user-level, and project-level tutorial (FR-039).

    Holds the parsed manifest and nothing else. It has no cursor: every answer
    is a function of the manifest and the context it is handed, which is what
    lets a session resume after a backend restart by handing back a step id it
    read out of a file.
    """

    manifest: TutorialManifest

    def _step(self, context: DriverContext) -> TutorialStep:
        step = None if context.step_id is None else self.manifest.step_by_id(context.step_id)
        if step is None:
            raise DriverContractError(
                f"tutorial '{self.manifest.id}' has no step {context.step_id!r}; "
                "the session's recorded position no longer exists in the manifest"
            )
        return step

    def step_view(self, context: DriverContext) -> StepView:
        """Return FR-011's fields for the context's step."""
        step = self._step(context)
        return StepView(
            id=step.id,
            index=self._index(step.id),
            total=len(self.manifest.steps),
            title=step.title,
            say=step.say,
            say_moods=step.say_moods,
            highlights=tuple(None if highlight is None else highlight.as_json() for highlight in step.highlights),
            route_to=step.route_to,
            prefill=tuple(prefill.as_json() for prefill in step.prefill),
            pages=step.pages,
            trigger=None if step.trigger is None else {"label": step.trigger.label},
            compacts=step.compacts,
            auto_advance=step.auto_advance,
            awaiting_continue=step.awaiting_continue,
        )

    def is_satisfied(self, context: DriverContext, product: ProductState) -> bool:
        """Return whether the step's ``done_when`` holds (FR-046, FR-054).

        A step with no ``done_when`` is never satisfied by state: FR-012 says it
        advances on an explicit user continue, which is the session's business
        and not a condition this can fake.
        """
        step = self._step(context)
        if step.done_when is None:
            return False
        return evaluate(step.done_when, product, entered_at=context.step_entered_at)

    def entry_actions(self, context: DriverContext) -> tuple[Action, ...]:
        """Return the step's declared ``do`` list, in declaration order (FR-056)."""
        return self._step(context).do

    def trigger_actions(self, context: DriverContext) -> tuple[Action, ...]:
        """Return the actions behind the step's trigger, or nothing (#2061).

        The optional capability :class:`DeclaresTriggerActions` describes; the
        runtime asks through it when the reader presses the button the step
        view's ``trigger`` label named.
        """
        trigger = self._step(context).trigger
        return () if trigger is None else trigger.do

    def steps_outline(self, context: DriverContext) -> tuple[Mapping[str, Any], ...]:
        """Static metadata for every step, for the session's outline surface.

        The reading window shows the whole tutorial's card names up front, and
        the per-step view only ever describes the step the session is on. What
        crosses here is deliberately the inert subset — index, id, title, say,
        pages — never a condition, highlight, prefill, or action, so the
        outline cannot become a second step surface.
        """
        return tuple(
            {"index": index, "id": step.id, "title": step.title, "say": step.say, "pages": step.pages}
            for index, step in enumerate(self.manifest.steps)
        )

    def advance(self, context: DriverContext) -> str | None:
        """Return the next step's id, or ``None`` at the end of the manifest."""
        steps = self.manifest.steps
        if not steps:
            return None
        if context.step_id is None:
            return steps[0].id
        position = self._index(context.step_id)
        return steps[position + 1].id if position + 1 < len(steps) else None

    def condition(self, context: DriverContext) -> Condition | None:
        """Return the step's ``done_when``, letting the session filter events (FR-050)."""
        return self._step(context).done_when

    def _index(self, step_id: str) -> int:
        for index, step in enumerate(self.manifest.steps):
            if step.id == step_id:
                return index
        raise DriverContractError(f"tutorial '{self.manifest.id}' has no step {step_id!r}")


# ---------------------------------------------------------------------------
# The guard that makes both drivers indistinguishable (FR-040, FR-041)
# ---------------------------------------------------------------------------


class GuardedDriver:
    """Normalizes every answer a driver gives, whichever driver it is.

    The session talks only to this, so the parity FR-040 requires is a property
    of one wrapper rather than of every driver's good behavior. It normalizes
    and validates; it does not catch. A driver exception is the session's to
    turn into a session-ending error naming the tutorial (FR-044), and
    swallowing it here would make that impossible.
    """

    def __init__(self, inner: Any) -> None:
        missing = [
            name
            for name in ("step_view", "is_satisfied", "entry_actions", "advance")
            if not callable(getattr(inner, name, None))
        ]
        if missing:
            raise DriverContractError(
                f"{type(inner).__name__} is not a tutorial driver: it does not implement {', '.join(missing)}"
            )
        self._inner = inner

    @property
    def inner(self) -> Any:
        """The wrapped driver, for tests that need to name it. The runtime never asks."""
        return self._inner

    def step_view(self, context: DriverContext) -> StepView:
        return StepView.of(self._inner.step_view(context))

    def is_satisfied(self, context: DriverContext, product: ProductState) -> bool:
        return bool(self._inner.is_satisfied(context, product))

    def entry_actions(self, context: DriverContext) -> tuple[Action, ...]:
        return _normalised_actions(self._inner.entry_actions(context), method="entry_actions")

    def trigger_actions(self, context: DriverContext) -> tuple[Action, ...]:
        """The actions behind the current step's trigger, normalized (#2061).

        ``()`` when the wrapped driver lacks the optional capability, so the
        runtime can distinguish "no actions to run" from "no trigger declared"
        by the step view rather than by this answer.
        """
        declared = getattr(self._inner, "trigger_actions", None)
        if not callable(declared):
            return ()
        return _normalised_actions(declared(context), method="trigger_actions")

    def steps_outline(self, context: DriverContext) -> tuple[Mapping[str, Any], ...]:
        """The tutorial's static step outline, normalized; ``()`` without the capability.

        Reduced to exactly the inert fields — index, id, title, say, pages —
        the way :meth:`step_view` reduces a step, so a driver cannot widen the
        outline into a second step surface.
        """
        declared = getattr(self._inner, "steps_outline", None)
        if not callable(declared):
            return ()
        raw = declared(context)
        if raw is None:
            return ()
        if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
            raise DriverContractError(f"steps_outline must return a sequence, got {type(raw).__name__}")
        outline: list[Mapping[str, Any]] = []
        for index, item in enumerate(raw):
            if not isinstance(item, Mapping):
                raise DriverContractError(f"steps_outline[{index}] must be a mapping, got {type(item).__name__}")
            step_id = item.get("id")
            if not isinstance(step_id, str) or not step_id:
                raise DriverContractError(f"steps_outline[{index}] must carry a non-empty string id")
            outline.append(
                {
                    "index": int(item.get("index", index)),
                    "id": step_id,
                    "title": _optional_text(item.get("title"), step_id=step_id, name="title"),
                    # The reading window shows lines, not expressions: the
                    # outline is a table of contents, and nobody's face is in it.
                    "say": _optional_say(item.get("say"), step_id=step_id)[0],
                    "pages": _optional_pages(item.get("pages"), step_id=step_id),
                }
            )
        return tuple(outline)

    def advance(self, context: DriverContext) -> str | None:
        nxt = self._inner.advance(context)
        if nxt is None:
            return None
        if not isinstance(nxt, str) or not nxt:
            raise DriverContractError(f"advance must return a step id or None, got {nxt!r}")
        return nxt

    def condition(self, context: DriverContext) -> Condition | None:
        """Return the step's condition when the driver declares one, else ``None``."""
        declared = getattr(self._inner, "condition", None)
        if not callable(declared):
            return None
        found = declared(context)
        return found if isinstance(found, Condition) else None

    @property
    def declares_conditions(self) -> bool:
        """Whether the wrapped driver can name a step's condition (FR-050 filtering)."""
        return callable(getattr(self._inner, "condition", None))


def _normalised_actions(raw: Any, *, method: str) -> tuple[Action, ...]:
    """Reduce a driver's action list to core action objects, or refuse it.

    One reduction for both action-returning answers — entry and trigger — so
    FR-041's "a driver cannot introduce an action kind" cannot hold at one
    door and not the other.
    """
    if raw is None:
        return ()
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise DriverContractError(f"{method} must return a sequence of actions, got {type(raw).__name__}")
    actions: list[Action] = []
    for item in raw:
        if not isinstance(item, Action):
            raise DriverContractError(
                f"{method} may only return core action objects, got "
                f"{type(item).__name__}; a driver cannot introduce an action kind (FR-041)"
            )
        actions.append(item)
    return tuple(actions)


def guarded(driver: Any) -> GuardedDriver:
    """Wrap *driver* so its answers are normalized to the core contract.

    Every driver goes through this, core's included, so there is one code path
    and no way for a manifest tutorial and a package tutorial to diverge in what
    the runtime sees (FR-040).
    """
    return GuardedDriver(driver)


# ---------------------------------------------------------------------------
# Loading (FR-021, FR-039, FR-044)
# ---------------------------------------------------------------------------


def load_driver(manifest: TutorialManifest, key: TutorialKey) -> GuardedDriver:
    """Return the driver for *manifest*, importing a package's only if it has one.

    A manifest declaring ``steps`` gets :class:`ManifestDriver` and no import
    happens at all. A manifest declaring ``driver`` names a driver class, as
    the published schema describes it: either the dotted path
    ``package.module.DriverClass`` or the entry-point spelling
    ``package.module:DriverClass``. Both are accepted because the schema says
    "dotted path" while every other reference to a Python attribute in this
    repository uses the colon, and rejecting a manifest over which of the two
    its author chose would teach nothing. The named attribute is called with
    the manifest and must return an object implementing
    :class:`TutorialDriver`.

    This is the only place in :mod:`scistudio.tutorials` that imports a package
    module, and it is reached from the session's start path alone — never from
    discovery, which is what FR-018 and FR-021 together require. Any failure
    becomes a :class:`DriverLoadError` naming the tutorial, so a broken package
    tutorial breaks itself and nothing else (FR-044).
    """
    if not manifest.is_driver_driven:
        return guarded(ManifestDriver(manifest))

    reference = manifest.driver or ""
    if ":" in reference:
        module_name, _, attribute = reference.partition(":")
    else:
        module_name, _, attribute = reference.rpartition(".")
    try:
        if not module_name or not attribute:
            raise ValueError(f"'{reference}' does not name a module and an attribute")
        module = importlib.import_module(module_name)
        instance = getattr(module, attribute)(manifest)
        return guarded(instance)
    except Exception as exc:
        logger.warning("Learning Center: failed to load driver '%s'", reference, exc_info=True)
        raise DriverLoadError(key, reference, exc) from exc
