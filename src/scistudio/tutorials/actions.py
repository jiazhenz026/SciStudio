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
from typing import Any, Protocol, TypeVar, cast, runtime_checkable

from scistudio.stability import provisional

__all__ = [
    "AI_BLOCK_TERMINAL_SURFACE",
    "AI_CHAT_TERMINAL_SURFACE",
    "EXECUTED_PROJECT_PATHS",
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
    "executed_project_path_hit",
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
"""The AI Chat terminal — the conversation the reader is having."""

AI_BLOCK_TERMINAL_SURFACE = "ai_block_terminal"
"""The terminal an AI Block runs in.

A separate surface rather than a second tab on the same one, because they are
separate places: the chat is a conversation the reader is having, and this is a
block in their workflow doing its work. Keeping them apart is what lets both be
open at once — the runtime holds one scripted session *per surface* — so a
block's terminal opening does not end the conversation that asked for it.
"""

REPLAY_SURFACES: frozenset[str] = frozenset({AI_CHAT_TERMINAL_SURFACE, AI_BLOCK_TERMINAL_SURFACE})
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


EXECUTED_PROJECT_PATHS: frozenset[str] = frozenset(
    {
        # -- Imported or executed as code by the registries --------------------
        "blocks",  # drop-in scan imports every *.py; also joins sys.path
        "types",  # drop-in scan imports every *.py; <project>/types joins sys.path
        "previewers",  # sys.path insert, then every *.py is exec_module'd
        "panels",  # a panel.json may name a Python provider that is imported,
        # and every document under it is served into a frame the product mounts
        "plots",  # plots/<id>/plot.yaml names a render script that is executed
        # -- Configuration the product itself acts on to execute something -----
        "workflows",  # a workflow YAML names a code block's script_path and cwd
        "tutorials",  # a tutorial manifest is config this runtime acts on
        # -- Agent surfaces, live because the PTY spawns with cwd = project ----
        ".claude",  # settings.json registers hooks; hooks/*.py run on tool calls
        ".codex",  # config.toml carries an MCP command and hook command lines
        ".agents",  # skills/*/SKILL.md, provisioned and read as agent instructions
        ".qoder",  # settings.json in Claude's format, read by both Qoder channels
        ".kimi-code",  # mcp.json is merge-preserving, so a planted server survives
        ".scistudio",  # mcp.json spawns a command; previewers.json steers resolution
        ".git",  # commits run with cwd=project and no --no-verify, so hooks fire
        # -- Root files, same reasoning, matched as a first segment ------------
        ".mcp.json",  # fallback MCP discovery for Claude, Qoder, and Kimi
        "CLAUDE.md",  # auto-loaded verbatim as agent instructions
        "AGENTS.md",  # auto-loaded verbatim as agent instructions
    }
)
"""Project paths the product imports, executes, or reads to configure execution.

FR-020a names ``blocks/``, ``types/``, ``previewers/`` and ``plots/`` as a
floor — "at minimum" — not as the whole answer, and the first four alone are
not enough to make SC-012 true. ``create_project`` provisions an agent tree
into **every** project including tutorial ones
(``api/runtime/_projects.py`` calls ``install_project_agent_assets``), and the
AI PTY spawns with ``cwd`` set to the project root, so every provider's
project-scope discovery is live. A tutorial that could write ``.claude/hooks/``
would be shipping code that runs on the next tool call, before any human reads
it.

Two rules decided the membership, and both matter:

* **Configuration that steers execution counts.** ``.claude/settings.json`` and
  ``.codex/config.toml`` execute nothing themselves; they decide what does.
  Admitting them because "it is only JSON" would leave the same hole open
  through a different door.
* **The match is on the path, never on the extension.** Forbidding ``*.py``
  under ``.claude/hooks/`` while allowing ``*.sh`` would be the same bug with
  an extra step. Membership is tested against the first segment of a
  destination, so everything beneath a listed entry is covered.

Deliberately *not* here: ``user-guide/`` and ``docs/``, which the provisioner
also writes and the agent can read through its search tools. Those influence
what an agent is told, not what the product imports or runs, and FR-020a is
about executable code. That is a real question, but a broader one than this
requirement, and quietly folding it in here would misrepresent what this set
means.

**Adding a provisioned directory to a project means adding it here.** If
``create_project`` or ``agent_provisioning`` grows a new target, this list is
the thing that has to grow with it, or a project-level tutorial can write into
it. User-level and project-level tutorials are rejected for naming any of
these; see :func:`scistudio.tutorials.manifest.validate_tier_rules`, which owns
the tier grading because it owns
:class:`~scistudio.tutorials.manifest.TutorialSourceKind`.
"""

_EXECUTED_BY_FOLDED_NAME: Mapping[str, str] = {entry.casefold(): entry for entry in EXECUTED_PROJECT_PATHS}


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


def executed_project_path_hit(relative: str) -> str | None:
    """Return the :data:`EXECUTED_PROJECT_PATHS` entry ``relative`` lands under, if any.

    Comparison is case-insensitive and ignores the trailing dots and spaces
    Windows strips from a path component. Both matter: on a case-insensitive
    filesystem ``Blocks/evil.py`` and ``blocks./evil.py`` reach the same
    imported directory as ``blocks/evil.py``, so an exact match would be a
    check that the filesystem does not agree with.
    """
    head = destination_head(relative).rstrip(". ").casefold()
    return _EXECUTED_BY_FOLDED_NAME.get(head) if head else None


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


@provisional(since="0.3.4")
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


@provisional(since="0.3.4")
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


FileAction = WriteAction | CopyAction
"""The two actions that put files on disk -- the ones a replay segment may bind."""


@provisional(since="0.3.4")
@dataclass(frozen=True)
class RunAction:
    """Start a real workflow run from a step (FR-061d).

    The tutorial runtime could already *observe* runs -- ``run_succeeded`` and
    ``run_failed`` judge steps on them -- but not start one, so every run in
    every level was a button the reader had to press. That is right when
    pressing Run is the lesson and wrong when it is stage machinery: core
    tutorial 3's subject is an agent that runs things itself, and a scripted
    reply saying so while nothing ran would leave the reader reading logs that
    do not exist.

    Deliberately fire-and-forget. The port returns as soon as the run is
    queued, exactly as ``run_workflow`` does over MCP, and the step's own
    ``done_when`` is what waits for the outcome -- which is the mechanism a
    reader-pressed Run already went through, so nothing new judges it.
    """

    workflow: str
    """Tutorial-project-relative path of the workflow YAML to run."""

    kind: str = field(default="run", init=False)


@dataclass(frozen=True)
class ReplaySegment:
    """One ordered piece of a replay, with the actions bound to it (FR-061b)."""

    id: str
    source: str
    """Tutorial-directory-relative path of the segment's scripted bytes."""
    do: tuple[SegmentAction, ...] = ()
    """The actions bound to this segment.

    Write and copy actions MUST land before the segment's bytes are delivered
    (FR-061b, as revised by #2083 for a paced surface). A ``run`` bound here
    starts after every one of them has landed and settled -- a reply that
    writes a block and then runs a workflow that uses it cannot be allowed to
    race its own registry re-scan.
    """


@provisional(since="0.3.4")
@dataclass(frozen=True)
class ReplayAction:
    """Replay scripted material into one named surface (FR-061, FR-061a, FR-061b).

    How a tutorial shows a conversation that would otherwise need a live model:
    the material is scripted, and the surface renders it as though it had just
    arrived. A segment may bind to the file actions that must land first, so
    text claiming a file was written cannot be read before the file exists.
    """

    surface: str
    """The surface to replay into; one of :data:`REPLAY_SURFACES`."""
    segments: tuple[ReplaySegment, ...]
    """The scripted material, delivered in order."""
    #: FR-061 / #2089 — append to the surface's open replay tab rather than
    #: close-then-open. The conversation-pacing form: a step (or a trigger, in
    #: which case the reader's press is what asks for more) continues the
    #: scripted session already on screen instead of tearing its transcript
    #: down. A tab that has gone -- closed, or its socket dropped -- is not an
    #: authoring error: the runtime opens a fresh one and plays into that
    #: (#2083), because the alternative strands the reader for the rest of the
    #: level.
    continue_tab: bool = False

    kind: str = field(default="replay", init=False)


SegmentAction = FileAction | RunAction
"""What a replay segment may bind: the file actions, plus starting a run."""

Action = WriteAction | CopyAction | ReplayAction | RunAction
"""Every action a step may declare (FR-057)."""


RunPort = Callable[[str], None]
"""How the runtime starts a workflow: given a project-relative path, queue a run.

Fire-and-forget by contract. The product's own Run button and the agent's
``run_workflow`` MCP tool both return as soon as the run is queued, and a
tutorial that blocked here would freeze the step's press while the workflow
executed. What the run *does* is judged where every other run is judged: the
step's ``done_when``.
"""


def describe_action(action: Action) -> str:
    """Return a short human phrase naming the action, used in error messages."""
    if isinstance(action, ReplayAction):
        return f"replay action into {action.surface!r}"
    if isinstance(action, RunAction):
        return f"run action on {action.workflow!r}"
    return f"{action.kind} action {action.source!r} -> {action.destination!r}"


# ---------------------------------------------------------------------------
# Parsing (validation time)
# ---------------------------------------------------------------------------

_ACTION_KINDS = ("write", "copy", "replay", "run")
_FILE_ACTION_KINDS = ("write", "copy")
_SEGMENT_ACTION_KINDS = ("write", "copy", "run")


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


def _require_declaration(
    raw: Any,
    *,
    field_name: str,
    keys: tuple[str, ...],
    also_accepts: tuple[str, ...] = (),
) -> Mapping[str, Any]:
    """Return ``raw`` as a mapping declaring ``keys``, rejecting any key outside them.

    The three things this module parses out of a manifest — a file action, a
    replay, a replay segment — each open with the same two rejections: a body
    that is not a mapping, and a key the format does not define. Both messages
    have to name the declaration's own field path for FR-013's errors to point
    at the right place, so the caller passes that path in rather than three
    parsers separately agreeing on how to build it.

    ``keys`` are the ones the "expected a mapping with ..." message names.
    ``also_accepts`` are accepted without being named, which is a segment's
    optional ``do``.
    """
    if not isinstance(raw, Mapping):
        raise ActionValidationError(f"{field_name}: expected a mapping with {' and '.join(repr(key) for key in keys)}")
    unknown = set(raw) - set(keys) - set(also_accepts)
    if unknown:
        raise ActionValidationError(f"{field_name}: unknown key(s) {', '.join(sorted(unknown))}")
    return raw


def _require_text(body: Mapping[str, Any], key: str, *, field_name: str) -> str:
    """Return ``body[key]`` as a non-empty string, or reject it naming the key."""
    value = body.get(key)
    if not isinstance(value, str) or not value:
        raise ActionValidationError(f"{field_name}.{key}: expected a non-empty string")
    return value


def _parse_file_action(kind: str, body: Any, *, field_name: str) -> FileAction:
    field = f"{field_name}.{kind}"
    declared = _require_declaration(body, field_name=field, keys=("source", "destination"))
    for key in ("source", "destination"):
        # Distinguished from _require_text on purpose: a write whose 'source' is
        # missing and one whose 'source' is a number are different mistakes, and
        # an empty string is left to validate_relative_path so the reason a path
        # is unusable is always given by the path validator.
        if key not in declared:
            raise ActionValidationError(f"{field}: missing required key {key!r}")
        if not isinstance(declared[key], str):
            raise ActionValidationError(f"{field}.{key}: expected a string")
    source = str(declared["source"])
    destination = str(declared["destination"])
    validate_relative_path(source, field_name=f"{field}.source")
    validate_relative_path(destination, field_name=f"{field}.destination")
    if kind == "write":
        return WriteAction(source=source, destination=destination)
    return CopyAction(source=source, destination=destination)


def _parse_run(body: Any, *, field_name: str) -> RunAction:
    field = f"{field_name}.run"
    declared = _require_declaration(body, field_name=field, keys=("workflow",))
    workflow = _require_text(declared, "workflow", field_name=field)
    validate_relative_path(workflow, field_name=f"{field}.workflow")
    return RunAction(workflow=workflow)


def _parse_replay(body: Any, *, field_name: str) -> ReplayAction:
    field = f"{field_name}.replay"
    declared = _require_declaration(
        body, field_name=field, keys=("surface", "segments"), also_accepts=("continue_tab",)
    )
    continue_tab = declared.get("continue_tab", False)
    if not isinstance(continue_tab, bool):
        raise ActionValidationError(f"{field}.continue_tab: expected true or false, got {continue_tab!r}")
    surface = _require_text(declared, "surface", field_name=field)
    if surface not in REPLAY_SURFACES:
        raise ActionValidationError(
            f"{field}.surface: {surface!r} is not a replay surface; "
            f"the closed set is {', '.join(sorted(REPLAY_SURFACES))}"
        )
    raw_segments = declared.get("segments")
    if not isinstance(raw_segments, Sequence) or isinstance(raw_segments, str) or not raw_segments:
        raise ActionValidationError(f"{field}.segments: expected a non-empty list")
    seen: set[str] = set()
    segments = tuple(
        _parse_segment(raw_segment, field_name=f"{field}.segments[{index}]", seen=seen)
        for index, raw_segment in enumerate(raw_segments)
    )
    return ReplayAction(surface=surface, segments=segments, continue_tab=continue_tab)


def _parse_segment(raw: Any, *, field_name: str, seen: set[str]) -> ReplaySegment:
    declared = _require_declaration(raw, field_name=field_name, keys=("id", "source"), also_accepts=("do",))
    segment_id = _require_text(declared, "id", field_name=field_name)
    if segment_id in seen:
        raise ActionValidationError(f"{field_name}.id: duplicate segment id {segment_id!r}")
    seen.add(segment_id)
    source = _require_text(declared, "source", field_name=field_name)
    validate_relative_path(source, field_name=f"{field_name}.source")
    bound = parse_segment_actions(declared.get("do") or (), field_name=f"{field_name}.do")
    return ReplaySegment(id=segment_id, source=source, do=bound)


def _parse_one_action(raw: Any, *, field_name: str, allowed: Sequence[str]) -> Action:
    """Parse one declared action, restricted to the ``allowed`` kinds."""
    kind, body = _single_key(raw, field_name=field_name, allowed=allowed)
    if kind == "replay":
        return _parse_replay(body, field_name=field_name)
    if kind == "run":
        return _parse_run(body, field_name=field_name)
    return _parse_file_action(kind, body, field_name=field_name)


def parse_action(raw: Any, *, field_name: str) -> Action:
    """Parse one declared action, rejecting anything the format does not allow."""
    return _parse_one_action(raw, field_name=field_name, allowed=_ACTION_KINDS)


def _parse_action_list(raw: Any, *, field_name: str, allowed: Sequence[str], expected: str) -> tuple[Action, ...]:
    """Parse an ordered ``do`` list restricted to the ``allowed`` action kinds.

    A step's ``do`` and a replay segment's ``do`` are the same walk over the
    same declarations; they differ in which kinds are legal there and therefore
    in what the message says a non-list should have been. Both are that walk
    with those two arguments, so a change to how a ``do`` list is read cannot
    reach one of them and miss the other.
    """
    if raw is None:
        return ()
    if not isinstance(raw, Sequence) or isinstance(raw, str):
        raise ActionValidationError(f"{field_name}: expected {expected}")
    return tuple(
        _parse_one_action(item, field_name=f"{field_name}[{index}]", allowed=allowed) for index, item in enumerate(raw)
    )


def parse_actions(raw: Any, *, field_name: str) -> tuple[Action, ...]:
    """Parse an ordered ``do`` list. Order is preserved; it is execution order."""
    return _parse_action_list(raw, field_name=field_name, allowed=_ACTION_KINDS, expected="a list of actions")


def parse_file_actions(raw: Any, *, field_name: str) -> tuple[FileAction, ...]:
    """Parse a ``do`` list restricted to write and copy.

    Narrowed rather than checked again: ``_FILE_ACTION_KINDS`` excludes
    ``replay``, so :func:`_parse_action_list` can only have built write and copy
    actions here.
    """
    parsed = _parse_action_list(
        raw,
        field_name=field_name,
        allowed=_FILE_ACTION_KINDS,
        expected="a list of write or copy actions",
    )
    return cast("tuple[FileAction, ...]", parsed)


def parse_segment_actions(raw: Any, *, field_name: str) -> tuple[SegmentAction, ...]:
    """Parse a replay segment's ``do`` list: write, copy, or run.

    A segment may not nest a replay -- a scripted reply that opens another
    scripted reply is not a thing the format means -- but it may start a run,
    which is how a transcript that says "running it now" comes to be telling
    the truth (FR-061d).
    """
    parsed = _parse_action_list(
        raw,
        field_name=field_name,
        allowed=_SEGMENT_ACTION_KINDS,
        expected="a list of write, copy or run actions",
    )
    return cast("tuple[SegmentAction, ...]", parsed)


def iter_file_actions(actions: Iterable[Action]) -> Iterable[FileAction]:
    """Yield every write and copy an action list performs, including inside replays.

    The tier rules (FR-020a) and the containment checks need every destination a
    tutorial can reach, and a replay reaches destinations through its segments.
    """
    for action in actions:
        if isinstance(action, RunAction):
            # No source and no destination: nothing for a tier rule or a
            # containment check to judge.
            continue
        if isinstance(action, ReplayAction):
            for segment in action.segments:
                for bound in segment.do:
                    if not isinstance(bound, RunAction):
                        yield bound
        else:
            yield action


def iter_asset_sources(action: Action) -> Iterable[tuple[str, str]]:
    """Yield ``(suffix, source)`` for every asset one action reads.

    ``suffix`` names the sub-field within the action, so a caller that knows
    where the action was declared can build the full field name FR-013's error
    messages need.
    """
    if isinstance(action, RunAction):
        return
    if isinstance(action, ReplayAction):
        for segment in action.segments:
            yield (f"replay.segments[{segment.id}].source", segment.source)
            for bound in segment.do:
                if isinstance(bound, RunAction):
                    continue
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


def _execute_file_action(action: FileAction, *, context: ActionContext, step_id: str) -> Path:
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
    return destination


def execute_replay(
    action: ReplayAction,
    *,
    context: ActionContext,
    step_id: str,
    delivery: ReplayDelivery,
    defer: list[SegmentAction] | None = None,
) -> tuple[Path, ...]:
    """Run a replay: deliver each segment's bytes and land its bound actions.

    FR-061b is the ordering rule here: a scripted agent that claims to have
    written a block is matched by the block existing at the moment the claim
    becomes readable. Which moment that is depends on how the surface plays the
    bytes, and that is what ``defer`` is for.

    Without ``defer``, the bytes are readable as soon as they are delivered, so
    the segment's actions run first — the original ordering, and still the
    right one for any surface that renders a transcript at once.

    With ``defer``, the surface reveals the transcript over time (#2083: the
    scripted agent window types it at a speaking pace). "The moment the claim
    becomes readable" is then the end of the reply, not the start of it, and
    running the actions here would put the block on the canvas ten seconds
    before the agent finishes saying it wrote one — which reads as the tutorial
    knowing the future. So the actions are collected into ``defer`` instead and
    the caller runs them when the surface reports it has finished playing.

    Deferral is per *replay*, not per segment: the caller learns that the
    terminal has gone quiet, not which segment quietened it. For a
    single-segment replay — every replay these tutorials declare — the two are
    the same thing. A multi-segment replay lands all of its writes at the end
    of the last segment rather than each before its own.

    Returns the project paths the segments wrote, for the same reason
    :func:`execute_actions` does — which is nothing at all when deferring,
    because nothing has been written yet.
    """
    if delivery.surface != action.surface:
        raise ActionExecutionError(
            step_id=step_id,
            action=action,
            reason=f"delivery is bound to {delivery.surface!r} but the action names {action.surface!r}",
        )
    written: list[Path] = []
    for segment in action.segments:
        if defer is None:
            for bound in segment.do:
                if isinstance(bound, RunAction):
                    # Started by `perform_step_entry`, after the settle -- see
                    # `start_runs`. Running it here would beat the files this
                    # very loop is still writing.
                    continue
                written.append(_execute_file_action(bound, context=context, step_id=step_id))
        else:
            defer.extend(segment.do)
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
    return tuple(written)


def execute_action(
    action: Action,
    *,
    context: ActionContext,
    step_id: str,
    delivery: ReplayDelivery | None = None,
    defer: list[SegmentAction] | None = None,
) -> tuple[Path, ...]:
    """Run one action and return the project paths it wrote.

    A :class:`RunAction` is not run here and writes nothing; see
    :func:`start_runs` for why starting one is a separate pass.

    Raises :class:`ActionExecutionError` on any failure (FR-060).
    """
    if isinstance(action, RunAction):
        return ()
    if isinstance(action, ReplayAction):
        if delivery is None:
            raise ActionExecutionError(
                step_id=step_id,
                action=action,
                reason="no replay delivery was supplied for the declared surface",
            )
        return execute_replay(action, context=context, step_id=step_id, delivery=delivery, defer=defer)
    return (_execute_file_action(action, context=context, step_id=step_id),)


def _declared_runs(actions: Iterable[Action], *, include_bound: bool) -> Iterable[RunAction]:
    """The run actions *actions* declares, optionally descending into replays.

    ``include_bound`` is the caller saying whether it deferred. A step-entry
    replay runs its bound actions immediately, so its runs have to be found
    here or they never start at all. A deferred one has already handed the same
    actions to the defer list, and finding them here too would start the run at
    press time -- before the reply has finished saying it is starting one, which
    is the whole point of deferring.
    """
    for action in actions:
        if isinstance(action, RunAction):
            yield action
        elif include_bound and isinstance(action, ReplayAction):
            for segment in action.segments:
                for bound in segment.do:
                    if isinstance(bound, RunAction):
                        yield bound


def start_runs(
    actions: Iterable[Action],
    *,
    step_id: str,
    run: RunPort | None,
    include_bound: bool = True,
) -> tuple[str, ...]:
    """Start every :class:`RunAction` in *actions*, and return what was started.

    A separate pass rather than a branch inside :func:`execute_actions`, so
    that the ordering FR-061d requires is a property of the call sequence
    instead of something an author has to get right by where they put the
    action in their ``do`` list. A run always comes last: the workflow it
    executes may have been written by an action beside it, and the blocks that
    workflow needs may have been written there too, so it cannot start until
    those files have landed *and* the product has taken them in.

    Raises:
        ActionExecutionError: A run was declared with no runner wired into the
            runtime. Silence would be worse than an error here -- the step's
            ``done_when`` waits on a run that will never happen, and the reader
            is left pressing a button that does nothing.
    """
    started: list[str] = []
    for action in _declared_runs(actions, include_bound=include_bound):
        if run is None:
            raise ActionExecutionError(
                step_id=step_id,
                action=action,
                reason="no workflow runner is wired into the tutorial runtime",
            )
        try:
            run(action.workflow)
        except ActionExecutionError:
            raise
        except Exception as exc:
            raise ActionExecutionError(
                step_id=step_id,
                action=action,
                reason=f"the workflow could not be started: {type(exc).__name__}: {exc}",
            ) from exc
        started.append(action.workflow)
    return tuple(started)


def execute_actions(
    actions: Sequence[Action],
    *,
    context: ActionContext,
    step_id: str,
    delivery: ReplayDelivery | None = None,
    defer: list[SegmentAction] | None = None,
) -> tuple[Path, ...]:
    """Run an ordered action list. Declaration order is execution order.

    Returns every project path written, in the order it was written, so a
    caller can react to what landed without re-deriving it from the manifest.

    ``defer`` reaches :func:`execute_replay` and nothing else; see its
    docstring for what a replay does with it. A step's own ``write`` and
    ``copy`` actions are not claims anybody is in the middle of reading, so
    they run here exactly as they always have.

    ``run`` actions are skipped -- :func:`start_runs` is the pass that starts
    them, after this one and after the caller has settled what it wrote.
    """
    written: list[Path] = []
    for action in actions:
        written.extend(execute_action(action, context=context, step_id=step_id, delivery=delivery, defer=defer))
    return tuple(written)


_Reveal = TypeVar("_Reveal")


def perform_step_entry(
    actions: Sequence[Action],
    *,
    context: ActionContext,
    step_id: str,
    reveal: Callable[[], _Reveal],
    delivery: ReplayDelivery | None = None,
    settle: Callable[[Sequence[Path]], None] | None = None,
    defer: list[SegmentAction] | None = None,
    run: RunPort | None = None,
) -> _Reveal:
    """Run a step's entry actions, let the product take them in, then reveal (FR-059).

    The only way to get at ``reveal()``'s result is through this call, so the
    ordering FR-059 requires is a property of the API rather than something a
    caller has to remember. If any action fails the exception propagates and
    ``reveal`` is never called, so the step's text cannot be read after a
    failed entry (FR-060).

    ``settle`` is the third position in that ordering, and exists because
    writing a file is not the same as the product having noticed it. A step
    that says "we have written this block for you — find it in the palette"
    reads as broken while the file sits on disk unscanned, which satisfies
    FR-059's letter and misses what it is for. The hook is called with the
    paths just written, before ``reveal``, so whatever the product has to do to
    take them in has happened by the time the step's text can be read. It is
    given no way to change the reveal, and a caller that supplies none gets the
    plain write-then-reveal ordering.

    ``defer`` is passed to :func:`execute_actions` for a replay to collect its
    bound actions into. Whatever lands there has not run and has not settled,
    so a caller that defers owns running it — and settling it — later (#2083).

    ``run`` is the port a ``run`` action reaches. It is called after the settle
    and never before, so a workflow started here sees every file this step
    wrote and a product that has already noticed them.
    """
    written = execute_actions(actions, context=context, step_id=step_id, delivery=delivery, defer=defer)
    if settle is not None and written:
        settle(written)
    # Fourth in the ordering, and after the settle for the reason FR-061d
    # gives: a run started before the registries have re-scanned would execute
    # against a palette that does not yet contain the block the step just
    # wrote for it.
    start_runs(actions, step_id=step_id, run=run, include_bound=defer is None)
    return reveal()
