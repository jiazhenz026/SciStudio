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
driver returns is normalised into :class:`StepView` before anything else sees
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
from typing import Any, Protocol, runtime_checkable

from scistudio.tutorials.actions import Action
from scistudio.tutorials.conditions import Condition, ProductState, evaluate
from scistudio.tutorials.manifest import TutorialManifest, TutorialStep
from scistudio.tutorials.projects import TutorialKey

logger = logging.getLogger(__name__)

__all__ = [
    "STEP_VIEW_FIELDS",
    "DeclaresConditions",
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
#: ``say``, ``highlight``, ``route_to``, and the continue flag are the manifest
#: format's whole rendering vocabulary; ``id``, ``index``, and ``total`` are
#: position, which the frontend needs to show progress through a tutorial and
#: which no driver may misreport into a different shape.
STEP_VIEW_FIELDS: tuple[str, ...] = (
    "id",
    "index",
    "total",
    "say",
    "highlight",
    "route_to",
    "awaiting_continue",
)


@dataclass(frozen=True)
class StepView:
    """What one step looks like, for every driver alike (FR-040, FR-041)."""

    id: str
    index: int
    total: int
    say: str | None = None
    highlight: str | None = None
    route_to: str | None = None
    awaiting_continue: bool = False

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
        return cls(
            id=step_id,
            index=index,
            total=total,
            say=_optional_text(read("say"), step_id=step_id, name="say"),
            highlight=_optional_text(read("highlight"), step_id=step_id, name="highlight"),
            route_to=_optional_text(read("route_to"), step_id=step_id, name="route_to"),
            awaiting_continue=bool(read("awaiting_continue")),
        )


def _optional_text(value: Any, *, step_id: str, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise DriverContractError(f"step {step_id!r}: {name} must be text or absent, got {type(value).__name__}")
    return value


# ---------------------------------------------------------------------------
# The interface (FR-038)
# ---------------------------------------------------------------------------


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


@runtime_checkable
class TutorialDriver(Protocol):
    """FR-038's four questions, and no fifth."""

    def step_view(self, context: DriverContext) -> Any:
        """Return the view of ``context.step_id``.

        The return value is normalised through :meth:`StepView.of`, so it may
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
            say=step.say,
            highlight=step.highlight,
            route_to=step.route_to,
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
        return evaluate(step.done_when, product)

    def entry_actions(self, context: DriverContext) -> tuple[Action, ...]:
        """Return the step's declared ``do`` list, in declaration order (FR-056)."""
        return self._step(context).do

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
    """Normalises every answer a driver gives, whichever driver it is.

    The session talks only to this, so the parity FR-040 requires is a property
    of one wrapper rather than of every driver's good behaviour. It normalises
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
        raw = self._inner.entry_actions(context)
        if raw is None:
            return ()
        if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
            raise DriverContractError(f"entry_actions must return a sequence of actions, got {type(raw).__name__}")
        actions: list[Action] = []
        for item in raw:
            if not isinstance(item, Action):
                raise DriverContractError(
                    "entry_actions may only return core action objects, got "
                    f"{type(item).__name__}; a driver cannot introduce an action kind (FR-041)"
                )
            actions.append(item)
        return tuple(actions)

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


def guarded(driver: Any) -> GuardedDriver:
    """Wrap *driver* so its answers are normalised to the core contract.

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
