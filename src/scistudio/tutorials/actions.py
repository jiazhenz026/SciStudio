"""Step actions — what entering a tutorial step *does* before it says anything.

ADR-053 Learning Center spec, FR-056 … FR-061c
(``docs/specs/adr-053-learning-center.md``).

Three things live here and nothing else:

* the **action model and its parser** — ``write``, ``copy``, ``replay``;
* **path containment** — FR-014's "an asset path resolves inside the tutorial
  directory" and FR-015's "a write destination resolves inside the tutorial
  project", both enforced *at validation* so a bad tutorial fails while it is
  being listed rather than while it is writing files into a user's project;
* **execution**, including the replay segment ordering FR-061b requires.

This module imports nothing else from :mod:`scistudio.tutorials`, which is what
lets :mod:`scistudio.tutorials.manifest` import it. It never imports
``scistudio.api``: the API layer injects the replay delivery it owns
(checklist §6.1.2, §6.1.7).

Ordering is a property of the API, not a convention (FR-059)
--------------------------------------------------------------

A step that says "we have written this block for you" must not be readable
before the block exists. :func:`perform_step_entry` is therefore the only way
to obtain a step's display payload: it runs the step's actions first and calls
the caller's ``reveal`` callback afterwards. A driver that wants the step text
has to go through the actions to get it.

Overwriting is deliberate
-------------------------

A write action whose destination the user has already edited overwrites it
(spec §2 Edge Cases). Tutorial projects are disposable and the designed
scenarios depend on the tutorial controlling their contents; the step text says
when it writes.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Protocol, TypeVar, runtime_checkable

__all__ = [
    "AI_CHAT_TERMINAL_SURFACE",
    "EXECUTED_PROJECT_DIRS",
    "REPLAY_SURFACES",
    "Action",
    "ActionContext",
    "ActionExecutionError",
    "ActionValidationError",
    "CopyAction",
    "FileAction",
    "ReplayAction",
    "ReplayDelivery",
    "ReplaySegment",
    "WriteAction",
    "describe_action",
    "destination_head",
    "execute_action",
    "execute_actions",
    "execute_replay",
    "iter_asset_sources",
    "iter_file_actions",
    "parse_action",
    "parse_actions",
    "parse_file_actions",
    "perform_step_entry",
    "resolve_contained_path",
    "validate_relative_path",
]


# ---------------------------------------------------------------------------
# The closed replay surface set (FR-061a)
# ---------------------------------------------------------------------------

AI_CHAT_TERMINAL_SURFACE = "ai_chat_terminal"
"""The AI Chat terminal — the only surface a replay may name."""

REPLAY_SURFACES: frozenset[str] = frozenset({AI_CHAT_TERMINAL_SURFACE})
"""FR-061a: the closed, core-owned set of surfaces a replay action may name.

This is the *single* declaration. The published manifest schema deliberately
does not restate it (``tutorial.schema.json`` types ``surface`` as a plain
string and points here), because a second copy is a second thing to keep in
step. A manifest naming a surface outside this set is rejected by
:func:`parse_action` at validation.

Byte delivery does not live here — the PTY injection that feeds the AI Chat
terminal is a separate slice (checklist §6.1.7). This module defines the
sequence and the :class:`ReplayDelivery` interface that slice drives.
"""


EXECUTED_PROJECT_DIRS: frozenset[str] = frozenset({"blocks", "types", "previewers", "plots"})
"""Tutorial-project directories the product imports or executes from (FR-020a).

A write or copy destination whose first path segment is one of these lands in
a directory the registry scan reaches. User-level and project-level tutorials
are rejected for naming one; see
:func:`scistudio.tutorials.manifest.validate_tier_rules`, which owns the tier
grading because it owns :class:`~scistudio.tutorials.manifest.TutorialSourceKind`.
"""


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ActionValidationError(ValueError):
    """An action was rejected while the manifest was being validated.

    Raised for a malformed action, an unknown action kind, a path escaping its
    base, or a replay naming a surface outside :data:`REPLAY_SURFACES`.
    :mod:`scistudio.tutorials.manifest` catches this and re-raises it as a
    ``ManifestValidationError`` naming the file, so discovery has one type to
    catch.
    """


class ActionExecutionError(RuntimeError):
    """An action failed while a step was being entered (FR-060).

    Carries the step id and the action so the session layer can end the session
    with an error naming both, rather than advancing silently.
    """

    def __init__(self, *, step_id: str, action: Action, reason: str) -> None:
        self.step_id = step_id
        self.action = action
        self.reason = reason
        super().__init__(f"tutorial step {step_id!r}: {describe_action(action)} failed: {reason}")


# ---------------------------------------------------------------------------
# Path containment (FR-014, FR-015)
# ---------------------------------------------------------------------------


def validate_relative_path(relative: str, *, field_name: str) -> PurePosixPath:
    """Return ``relative`` as a project/tutorial-relative POSIX path, or reject it.

    Rejected: an empty string, a backslash (a separator on Windows and a legal
    filename character elsewhere — allowing it would make containment mean two
    different things on two platforms), an absolute path, a Windows drive or
    drive-relative path, and any ``..`` segment.

    ``"."`` is accepted and means the base itself — a copy action landing a
    directory at the project root. It is not a loophole: the tier rules reject
    what such a copy would land in an executed directory
    (:func:`scistudio.tutorials.manifest.validate_tier_assets`), which is a
    better answer than forbidding the root and leaving the reason unstated.

    The check is lexical on purpose. FR-014 and FR-015 require rejection *at
    validation*, when the tutorial project may not exist yet, so it cannot
    depend on resolving anything on disk.
    """
    if not relative or not relative.strip():
        raise ActionValidationError(f"{field_name}: path must not be empty")
    if relative == ".":
        return PurePosixPath(".")
    if "\\" in relative:
        raise ActionValidationError(
            f"{field_name}: path {relative!r} must use '/' separators; '\\' is a separator on Windows "
            "and a filename character elsewhere"
        )
    if PurePosixPath(relative).is_absolute() or PureWindowsPath(relative).drive:
        raise ActionValidationError(f"{field_name}: path {relative!r} must be relative, not absolute")
    parts = PurePosixPath(relative).parts
    if any(part == ".." for part in parts):
        raise ActionValidationError(f"{field_name}: path {relative!r} must not escape its directory with '..'")
    if not parts:
        raise ActionValidationError(f"{field_name}: path must not be empty")
    return PurePosixPath(relative)


def destination_head(relative: str) -> str:
    """Return the first path segment of ``relative``, or ``""`` when there is none."""
    parts = PurePosixPath(relative).parts
    return parts[0] if parts else ""


def resolve_contained_path(base: Path, relative: str, *, field_name: str) -> Path:
    """Resolve ``relative`` under ``base`` and reject anything that escapes it.

    Used with the tutorial directory for asset sources (FR-014) and with the
    tutorial project for destinations (FR-015). When ``base`` exists the real
    paths are compared as well, so a symlink planted inside the base cannot
    carry a write outside it.
    """
    validate_relative_path(relative, field_name=field_name)
    base_norm = Path(os.path.normpath(str(base)))
    candidate = Path(os.path.normpath(str(base_norm / relative)))
    if candidate != base_norm and base_norm not in candidate.parents:
        raise ActionValidationError(f"{field_name}: path {relative!r} resolves outside {base_norm}")
    if base_norm.exists():
        real_base = os.path.realpath(base_norm)
        real_candidate = os.path.realpath(candidate)
        if real_candidate != real_base and not real_candidate.startswith(real_base + os.sep):
            raise ActionValidationError(
                f"{field_name}: path {relative!r} resolves outside {base_norm} through a symbolic link"
            )
    return candidate


# ---------------------------------------------------------------------------
# The action model (FR-057)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WriteAction:
    """Write one asset file into the tutorial project.

    Available at any step, not only at bootstrap (FR-058). An existing
    destination is overwritten (spec §2 Edge Cases).
    """

    source: str
    """Tutorial-directory-relative path of the asset to write."""
    destination: str
    """Tutorial-project-relative path to write it to."""

    kind: str = field(default="write", init=False)


@dataclass(frozen=True)
class CopyAction:
    """Copy one asset directory into the tutorial project.

    Existing files under the destination are overwritten, for the same reason
    :class:`WriteAction` overwrites.
    """

    source: str
    """Tutorial-directory-relative path of the asset directory to copy."""
    destination: str
    """Tutorial-project-relative directory to copy it into."""

    kind: str = field(default="copy", init=False)


@dataclass(frozen=True)
class ReplaySegment:
    """One ordered piece of a replay, with the actions bound to it (FR-061b)."""

    id: str
    source: str
    """Tutorial-directory-relative path of the segment's scripted bytes."""
    do: tuple[FileAction, ...] = ()
    """Write and copy actions that MUST land before this segment's bytes are delivered."""


@dataclass(frozen=True)
class ReplayAction:
    """Replay scripted material into one named surface (FR-061, FR-061a, FR-061b)."""

    surface: str
    segments: tuple[ReplaySegment, ...]

    kind: str = field(default="replay", init=False)


FileAction = WriteAction | CopyAction
"""The two actions that put files on disk — the ones a replay segment may bind."""

Action = WriteAction | CopyAction | ReplayAction
"""Every action a step may declare (FR-057)."""


def describe_action(action: Action) -> str:
    """Return a short human phrase naming the action, used in error messages."""
    if isinstance(action, ReplayAction):
        return f"replay action into {action.surface!r}"
    return f"{action.kind} action {action.source!r} -> {action.destination!r}"


# ---------------------------------------------------------------------------
# Parsing (validation time)
# ---------------------------------------------------------------------------

_ACTION_KINDS = ("write", "copy", "replay")
_FILE_ACTION_KINDS = ("write", "copy")


def _single_key(raw: Any, *, field_name: str, allowed: Sequence[str]) -> tuple[str, Any]:
    if not isinstance(raw, Mapping):
        raise ActionValidationError(f"{field_name}: an action must be a mapping, got {type(raw).__name__}")
    if len(raw) != 1:
        raise ActionValidationError(
            f"{field_name}: an action must declare exactly one of {', '.join(allowed)}; got {len(raw)} keys"
        )
    kind, body = next(iter(raw.items()))
    if kind not in allowed:
        raise ActionValidationError(f"{field_name}: unknown action {kind!r}; expected one of {', '.join(allowed)}")
    return str(kind), body


def _parse_file_action(kind: str, body: Any, *, field_name: str) -> FileAction:
    if not isinstance(body, Mapping):
        raise ActionValidationError(f"{field_name}.{kind}: expected a mapping with 'source' and 'destination'")
    unknown = set(body) - {"source", "destination"}
    if unknown:
        raise ActionValidationError(f"{field_name}.{kind}: unknown key(s) {', '.join(sorted(unknown))}")
    for key in ("source", "destination"):
        if key not in body:
            raise ActionValidationError(f"{field_name}.{kind}: missing required key {key!r}")
        if not isinstance(body[key], str):
            raise ActionValidationError(f"{field_name}.{kind}.{key}: expected a string")
    source = str(body["source"])
    destination = str(body["destination"])
    validate_relative_path(source, field_name=f"{field_name}.{kind}.source")
    validate_relative_path(destination, field_name=f"{field_name}.{kind}.destination")
    if kind == "write":
        return WriteAction(source=source, destination=destination)
    return CopyAction(source=source, destination=destination)


def _parse_replay(body: Any, *, field_name: str) -> ReplayAction:
    if not isinstance(body, Mapping):
        raise ActionValidationError(f"{field_name}.replay: expected a mapping with 'surface' and 'segments'")
    unknown = set(body) - {"surface", "segments"}
    if unknown:
        raise ActionValidationError(f"{field_name}.replay: unknown key(s) {', '.join(sorted(unknown))}")
    surface = body.get("surface")
    if not isinstance(surface, str) or not surface:
        raise ActionValidationError(f"{field_name}.replay.surface: expected a non-empty string")
    if surface not in REPLAY_SURFACES:
        raise ActionValidationError(
            f"{field_name}.replay.surface: {surface!r} is not a replay surface; "
            f"the closed set is {', '.join(sorted(REPLAY_SURFACES))}"
        )
    raw_segments = body.get("segments")
    if not isinstance(raw_segments, Sequence) or isinstance(raw_segments, str) or not raw_segments:
        raise ActionValidationError(f"{field_name}.replay.segments: expected a non-empty list")
    segments: list[ReplaySegment] = []
    seen: set[str] = set()
    for index, raw_segment in enumerate(raw_segments):
        segments.append(_parse_segment(raw_segment, field_name=f"{field_name}.replay.segments[{index}]", seen=seen))
    return ReplayAction(surface=surface, segments=tuple(segments))


def _parse_segment(raw: Any, *, field_name: str, seen: set[str]) -> ReplaySegment:
    if not isinstance(raw, Mapping):
        raise ActionValidationError(f"{field_name}: expected a mapping with 'id' and 'source'")
    unknown = set(raw) - {"id", "source", "do"}
    if unknown:
        raise ActionValidationError(f"{field_name}: unknown key(s) {', '.join(sorted(unknown))}")
    segment_id = raw.get("id")
    if not isinstance(segment_id, str) or not segment_id:
        raise ActionValidationError(f"{field_name}.id: expected a non-empty string")
    if segment_id in seen:
        raise ActionValidationError(f"{field_name}.id: duplicate segment id {segment_id!r}")
    seen.add(segment_id)
    source = raw.get("source")
    if not isinstance(source, str) or not source:
        raise ActionValidationError(f"{field_name}.source: expected a non-empty string")
    validate_relative_path(source, field_name=f"{field_name}.source")
    bound = parse_file_actions(raw.get("do") or (), field_name=f"{field_name}.do")
    return ReplaySegment(id=segment_id, source=source, do=bound)


def parse_action(raw: Any, *, field_name: str) -> Action:
    """Parse one declared action, rejecting anything the format does not allow."""
    kind, body = _single_key(raw, field_name=field_name, allowed=_ACTION_KINDS)
    if kind == "replay":
        return _parse_replay(body, field_name=field_name)
    return _parse_file_action(kind, body, field_name=field_name)


def parse_actions(raw: Any, *, field_name: str) -> tuple[Action, ...]:
    """Parse an ordered ``do`` list. Order is preserved; it is execution order."""
    if raw is None:
        return ()
    if not isinstance(raw, Sequence) or isinstance(raw, str):
        raise ActionValidationError(f"{field_name}: expected a list of actions")
    return tuple(parse_action(item, field_name=f"{field_name}[{index}]") for index, item in enumerate(raw))


def parse_file_actions(raw: Any, *, field_name: str) -> tuple[FileAction, ...]:
    """Parse a ``do`` list restricted to write and copy — a replay segment's binding."""
    if raw is None:
        return ()
    if not isinstance(raw, Sequence) or isinstance(raw, str):
        raise ActionValidationError(f"{field_name}: expected a list of write or copy actions")
    parsed: list[FileAction] = []
    for index, item in enumerate(raw):
        item_field = f"{field_name}[{index}]"
        kind, body = _single_key(item, field_name=item_field, allowed=_FILE_ACTION_KINDS)
        parsed.append(_parse_file_action(kind, body, field_name=item_field))
    return tuple(parsed)


def iter_file_actions(actions: Iterable[Action]) -> Iterable[FileAction]:
    """Yield every write and copy an action list performs, including inside replays.

    The tier rules (FR-020a) and the containment checks need every destination a
    tutorial can reach, and a replay reaches destinations through its segments.
    """
    for action in actions:
        if isinstance(action, ReplayAction):
            for segment in action.segments:
                yield from segment.do
        else:
            yield action


def iter_asset_sources(action: Action) -> Iterable[tuple[str, str]]:
    """Yield ``(suffix, source)`` for every asset one action reads.

    ``suffix`` names the sub-field within the action, so a caller that knows
    where the action was declared can build the full field name FR-013's error
    messages need.
    """
    if isinstance(action, ReplayAction):
        for segment in action.segments:
            yield (f"replay.segments[{segment.id}].source", segment.source)
            for bound in segment.do:
                yield (f"replay.segments[{segment.id}].{bound.kind}.source", bound.source)
    else:
        yield (f"{action.kind}.source", action.source)


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ActionContext:
    """Everything an action needs to run: where assets come from and where they go."""

    tutorial_dir: Path
    project_dir: Path | None
    """``None`` for a tutorial that declares no ``bootstrap`` and so has no project (FR-009)."""


@runtime_checkable
class ReplayDelivery(Protocol):
    """The interface the replay byte-delivery slice implements (checklist §6.1.7).

    This module owns the *sequence*; it does not own the bytes. The API layer
    supplies an object satisfying this protocol, bound to one surface, and
    :func:`execute_replay` drives it. ``close`` exists so ending a session
    mid-replay leaves nothing behind (FR-061c).
    """

    @property
    def surface(self) -> str:
        """The surface this delivery writes to; must be in :data:`REPLAY_SURFACES`."""
        ...

    def deliver(self, segment: ReplaySegment, payload: bytes) -> None:
        """Deliver one segment's bytes. Called only after the segment's actions have landed."""
        ...

    def close(self) -> None:
        """Terminate the scripted session and release its resources (FR-061c)."""
        ...


def _require_project(context: ActionContext, action: Action, step_id: str) -> Path:
    if context.project_dir is None:
        raise ActionExecutionError(
            step_id=step_id,
            action=action,
            reason="the tutorial declares no bootstrap, so it has no project to write into",
        )
    return context.project_dir


def _execute_file_action(action: FileAction, *, context: ActionContext, step_id: str) -> None:
    project_dir = _require_project(context, action, step_id)
    try:
        source = resolve_contained_path(context.tutorial_dir, action.source, field_name="source")
        destination = resolve_contained_path(project_dir, action.destination, field_name="destination")
    except ActionValidationError as exc:
        raise ActionExecutionError(step_id=step_id, action=action, reason=str(exc)) from exc

    try:
        if isinstance(action, WriteAction):
            if not source.is_file():
                raise FileNotFoundError(f"asset {action.source!r} is not a file")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        else:
            if not source.is_dir():
                raise NotADirectoryError(f"asset {action.source!r} is not a directory")
            destination.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, destination, dirs_exist_ok=True)
    except OSError as exc:
        raise ActionExecutionError(step_id=step_id, action=action, reason=str(exc)) from exc


def execute_replay(
    action: ReplayAction,
    *,
    context: ActionContext,
    step_id: str,
    delivery: ReplayDelivery,
) -> None:
    """Run a replay: for each segment, land its actions, then deliver its bytes.

    FR-061b in one line. A scripted agent that claims to have written a block
    is matched by the block existing at the moment the claim becomes readable,
    which is why the segment's own actions run *before* its bytes and not
    merely before the next segment's.
    """
    if delivery.surface != action.surface:
        raise ActionExecutionError(
            step_id=step_id,
            action=action,
            reason=f"delivery is bound to {delivery.surface!r} but the action names {action.surface!r}",
        )
    for segment in action.segments:
        for bound in segment.do:
            _execute_file_action(bound, context=context, step_id=step_id)
        try:
            source = resolve_contained_path(context.tutorial_dir, segment.source, field_name="segment source")
            payload = source.read_bytes()
        except (ActionValidationError, OSError) as exc:
            raise ActionExecutionError(
                step_id=step_id,
                action=action,
                reason=f"segment {segment.id!r}: {exc}",
            ) from exc
        delivery.deliver(segment, payload)


def execute_action(
    action: Action,
    *,
    context: ActionContext,
    step_id: str,
    delivery: ReplayDelivery | None = None,
) -> None:
    """Run one action, raising :class:`ActionExecutionError` on any failure (FR-060)."""
    if isinstance(action, ReplayAction):
        if delivery is None:
            raise ActionExecutionError(
                step_id=step_id,
                action=action,
                reason="no replay delivery was supplied for the declared surface",
            )
        execute_replay(action, context=context, step_id=step_id, delivery=delivery)
        return
    _execute_file_action(action, context=context, step_id=step_id)


def execute_actions(
    actions: Sequence[Action],
    *,
    context: ActionContext,
    step_id: str,
    delivery: ReplayDelivery | None = None,
) -> None:
    """Run an ordered action list. Declaration order is execution order."""
    for action in actions:
        execute_action(action, context=context, step_id=step_id, delivery=delivery)


_Reveal = TypeVar("_Reveal")


def perform_step_entry(
    actions: Sequence[Action],
    *,
    context: ActionContext,
    step_id: str,
    reveal: Callable[[], _Reveal],
    delivery: ReplayDelivery | None = None,
) -> _Reveal:
    """Run a step's entry actions, then produce the step's display payload (FR-059).

    The only way to get at ``reveal()``'s result is through this call, so the
    ordering FR-059 requires is a property of the API rather than something a
    caller has to remember. If any action fails the exception propagates and
    ``reveal`` is never called, so the step's text cannot be read after a
    failed entry (FR-060).
    """
    execute_actions(actions, context=context, step_id=step_id, delivery=delivery)
    return reveal()
