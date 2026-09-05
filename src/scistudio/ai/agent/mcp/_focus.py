"""The workspace focus, and the refusal every session tool makes without one.

ADR-054 spec 5, FR-001 to FR-005 (issue #2254).

ADR-040 Addendum 5 gave the agent one fact about the workspace: the id of the
workflow the GUI editor has open. The frontend posts it, the runtime keeps it
and mirrors it to ``<project>/.scistudio/active_workflow.json``, and the
``get_active_workflow_context`` tool reads it back. ADR-054 adds a second place
a person can be — an explore session over a notebook — and an agent that edits a
workflow while the person is in a notebook, or appends a cell while they are on
the canvas, is doing the wrong thing confidently.

So the channel is widened rather than duplicated. The same POST, the same file,
the same tool; what travels beside the workflow id is now a **record**:

* ``canvas`` — the person is on a workflow. Carries the workflow id, which is
  the id ADR-040 Addendum 5 already carried.
* ``explore`` — the person is in a session. Carries the session's notebook path
  (project-relative POSIX, as ``ExploreSession.relative_path`` addresses it),
  the run it is bound to, and the cell they are on.
* ``pause`` — the person is at an interactive pause. Carries the paused node and
  its run.

Every field is optional and every reader tolerates the record being absent,
because that absence is exactly today's behaviour: no focus reported reads as
:data:`MODE_CANVAS` over whatever workflow id is persisted (FR-003).

**The record crosses the layer boundary as a mapping, not as this class.** The
API layer persists the focus and hands it to the tools through the
:class:`~scistudio.ai.agent.mcp._context.MCPContext` Protocol, and ``api``
importing this module at module scope would drag the whole FastMCP tool graph
into ``scistudio.api.runtime`` — a package that today imports neither FastMCP
nor anything under ``ai`` (importing ``scistudio.ai.agent.mcp._focus`` executes
``scistudio/ai/agent/mcp/__init__.py``, which eagerly imports every tool module
so the ``@mcp.tool`` decorators run). The API therefore carries the focus as a
plain JSON-safe ``dict`` — the same shape it writes to disk — and
:meth:`WorkspaceFocus.from_mapping` is where it becomes a record, on this side
of the boundary. That also means the parse has to be tolerant, which it would
have to be anyway: the persistence file outlives the build that wrote it.

**Refusal is the enforcement.** :func:`resolve_session_path` is what the session
tools call before they act. A skill can tell the agent to check the mode first,
and it does; the refusal is what makes the rule hold when it forgets. The
message therefore has to let the agent recover in one step, which is why it
names the tool that opens a session and the arguments that tool takes rather
than merely reporting that the tool declined.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ._context import _safe_under, get_optional_context

if TYPE_CHECKING:
    from ._context import MCPContext

logger = logging.getLogger(__name__)


#: The person is on the canvas, editing a workflow. The mode a focus that has
#: never been reported reads as (FR-003), so it is also the safe default.
MODE_CANVAS = "canvas"
#: The person is in an explore session over a notebook.
MODE_EXPLORE = "explore"
#: The person is at an interactive pause on a node.
MODE_PAUSE = "pause"

#: Every mode the frontend may report. An unrecognised mode is read as "no focus
#: was reported" rather than rejected: a backend that refused to parse a newer
#: frontend's report would take the tool offline, and degrading to the
#: conservative canvas reading loses only the extra identifiers.
FOCUS_MODES: tuple[str, ...] = (MODE_CANVAS, MODE_EXPLORE, MODE_PAUSE)

#: The keys of the focus record, in the order they are written. This is the
#: on-the-wire and on-disk field list; :class:`WorkspaceFocus` is its in-process
#: form. Named so a test can assert the two have not drifted apart.
FOCUS_FIELDS: tuple[str, ...] = (
    "mode",
    "workflow_id",
    "session_path",
    "bound_run_id",
    "current_cell_id",
    "paused_node_id",
    "paused_run_id",
    "reported_at",
)


@dataclass(frozen=True, slots=True)
class WorkspaceFocus:
    """What the person is looking at, as the frontend last reported it.

    Immutable so that the runtime's record can be handed to a tool without the
    tool being able to edit the workspace's idea of itself. Mutate with
    :func:`dataclasses.replace`.

    Attributes
    ----------
    mode
        One of :data:`FOCUS_MODES`.
    workflow_id
        The workflow behind the canvas. Set for :data:`MODE_CANVAS`; it may also
        be carried in the other modes, because switching to an explore tab does
        not close the workflow the person came from.
    session_path
        Project-relative POSIX path of the focused session's notebook
        (:data:`MODE_EXPLORE`).
    bound_run_id
        The run the focused session is bound to, when it was opened over one.
    current_cell_id
        The cell the person's cursor is in, in the focused session.
    paused_node_id, paused_run_id
        The node that is paused and the run it is paused in
        (:data:`MODE_PAUSE`).
    reported_at
        ISO-8601 timestamp stamped by the backend when the report arrived,
        rather than sent by the browser — the browser's clock is not a fact this
        process can rely on.
    """

    mode: str = MODE_CANVAS
    workflow_id: str | None = None
    session_path: str | None = None
    bound_run_id: str | None = None
    current_cell_id: str | None = None
    paused_node_id: str | None = None
    paused_run_id: str | None = None
    reported_at: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return the JSON-safe mapping form — the shape the API persists."""
        return {name: getattr(self, name) for name in FOCUS_FIELDS}

    @classmethod
    def from_mapping(cls, raw: Any) -> WorkspaceFocus | None:
        """Parse a persisted or posted focus, or return ``None`` when unusable.

        Tolerant on purpose. The persistence file outlives the build that wrote
        it (the same argument ``_load_known_projects`` makes for the project
        registry), so an unknown key is ignored rather than fatal and a value of
        the wrong type is dropped rather than raising. A mapping that carries no
        recognisable mode is not a focus and returns ``None``, which every
        reader treats as "never reported" — today's behaviour (FR-003).

        Accepts a :class:`WorkspaceFocus` unchanged so callers do not have to
        care which form the context happens to be carrying.
        """
        if isinstance(raw, cls):
            return raw
        if not isinstance(raw, Mapping):
            return None
        mode = raw.get("mode")
        if not isinstance(mode, str) or mode not in FOCUS_MODES:
            if mode is not None:
                logger.debug("WorkspaceFocus: ignoring unrecognised mode %r", mode)
            return None
        return cls(
            mode=mode,
            workflow_id=_clean(raw.get("workflow_id")),
            session_path=_clean_path(raw.get("session_path")),
            bound_run_id=_clean(raw.get("bound_run_id")),
            current_cell_id=_clean(raw.get("current_cell_id")),
            paused_node_id=_clean(raw.get("paused_node_id")),
            paused_run_id=_clean(raw.get("paused_run_id")),
            reported_at=_clean(raw.get("reported_at")),
        )


def _clean(value: Any) -> str | None:
    """Return a non-empty trimmed string, or ``None`` for anything else."""
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed or None


def _clean_path(value: Any) -> str | None:
    """Return a notebook path in the project-relative POSIX form sessions use.

    ``ExploreSession.relative_path`` is the address of a session, and it is
    POSIX with no leading separator; ``SessionService.session_for`` looks a
    session up by exactly that string. A frontend running on Windows may hand
    back the same path with backslashes, and a leading ``./`` is a harmless
    thing for a caller to send. Both are normalised here so that the focus and
    the session registry agree on one spelling of the same notebook.

    This is the only place that knows the spelling, which is why the API layer
    persists what it was given and normalisation happens on read: a file written
    by an older build, or edited by hand, gets the same treatment as a fresh
    report.
    """
    cleaned = _clean(value)
    if cleaned is None:
        return None
    normalised = cleaned.replace("\\", "/")
    while normalised.startswith("./"):
        normalised = normalised[2:]
    normalised = normalised.lstrip("/")
    return normalised or None


def canvas_focus(workflow_id: str | None = None) -> WorkspaceFocus:
    """Return the focus a never-reported workspace reads as (FR-003)."""
    return WorkspaceFocus(mode=MODE_CANVAS, workflow_id=_clean(workflow_id))


def effective_focus(ctx: MCPContext | None = None) -> WorkspaceFocus:
    """Return the focus the tools should act on — never ``None``.

    FR-003: "a focus that has never been reported MUST read as mode canvas with
    the persisted workflow". That fallback lives here rather than in each
    reader, so the context tool and the session tools cannot disagree about what
    an unreported workspace means.

    Both reads are defensive ``getattr`` calls for the same reason
    ``get_active_workflow_context`` reads ``active_workflow_id`` defensively:
    third-party and test :class:`MCPContext` implementations predate these
    Protocol members, and a missing attribute must degrade to today's behaviour
    rather than take the tool offline.
    """
    if ctx is None:
        ctx = get_optional_context()
    if ctx is None:
        return canvas_focus()
    workflow_id = getattr(ctx, "active_workflow_id", None)
    focus = WorkspaceFocus.from_mapping(getattr(ctx, "workspace_focus", None))
    if focus is None:
        return canvas_focus(workflow_id)
    if focus.workflow_id is None and isinstance(workflow_id, str) and workflow_id:
        # The canvas's workflow is still the workflow the person came from when
        # they switched to a session, and the runtime keeps it independently of
        # the focus. Fill it in rather than reporting None beside a mode that
        # says nothing about it.
        return replace(focus, workflow_id=workflow_id)
    return focus


def focus_notebook_path(focus: WorkspaceFocus, project_dir: Path | None) -> Path | None:
    """Return the absolute notebook path a focus names, or ``None``.

    ``None`` means the focus does not name a resolvable notebook: it is not in
    explore mode, it carries no session path, no project is open, or the path
    escapes the project root. The traversal check is the same
    :func:`~scistudio.ai.agent.mcp._context._safe_under` every other
    agent-supplied path goes through — the focus arrives over HTTP, so it is
    caller input like any other.
    """
    if focus.mode != MODE_EXPLORE or not focus.session_path or project_dir is None:
        return None
    try:
        return _safe_under(project_dir, Path(focus.session_path))
    except (PermissionError, OSError, ValueError):
        logger.debug(
            "WorkspaceFocus: session path %r does not resolve under %s",
            focus.session_path,
            project_dir,
        )
        return None


def focus_is_stale(focus: WorkspaceFocus, project_dir: Path | None) -> bool:
    """Return whether an explore focus names a notebook that is no longer there.

    FR-004. Only an explore focus can be stale: a canvas focus over a deleted
    workflow is the existing tool's business, and a pause focus names a run
    rather than a file. A focus with no session path is not stale, it is
    incomplete, and the refusal covers it.

    A focus reported while no project is open cannot be checked, and is reported
    stale rather than live: the tools' contract is that a non-stale explore
    focus can be acted on, and one whose project has been closed cannot.
    """
    if focus.mode != MODE_EXPLORE or not focus.session_path:
        return False
    resolved = focus_notebook_path(focus, project_dir)
    if resolved is None:
        return True
    try:
        return not resolved.is_file()
    except OSError:
        return True


# ---------------------------------------------------------------------------
# FR-005 — the refusal every session tool makes
# ---------------------------------------------------------------------------

#: How to get a session, in the words the agent needs to act on. Appended to
#: every refusal so the agent can recover in one call rather than asking the
#: person what to do. Kept as a constant because the two refusal paths (no
#: session at all, and a stale one) must not drift into offering different
#: recoveries for the same problem.
OPEN_SESSION_HINT = (
    "Open one with the `open_explore_session` tool — pass source='block_outputs' with "
    "block_id set to the block whose outputs you want to explore, or source='file' with "
    "path set to a file in the project's data tree — and then retry. To act on a "
    "session the person is not looking at, pass its notebook path as `session_path` "
    "instead. Call `get_active_workflow_context` first if you need to know where the "
    "person actually is."
)


class NoExploreSessionError(RuntimeError):
    """Raised by :func:`resolve_session_path` when no session can be acted on.

    A ``RuntimeError`` subclass because that is what the MCP tool layer already
    surfaces to the agent as a tool error (``_resolve_project_root`` raises the
    same way for "no project is open"). A caller that would rather answer with a
    structured envelope can catch this and read ``str(exc)``; the message is
    written to be shown to the agent verbatim.
    """


def refusal_message(*, stale_path: str | None = None) -> str:
    """Return the message a session tool refuses with (FR-004, FR-005).

    Two shapes, one recovery. Without *stale_path* the workspace simply has no
    session focused; with it, the focus named a notebook that has since been
    deleted or moved, and saying so is the difference between the agent retrying
    the same call and the agent opening a new session.
    """
    if stale_path:
        return (
            f"No explore session is active: the workspace focus names the notebook "
            f"'{stale_path}', which no longer exists, so the focus is stale. "
            f"{OPEN_SESSION_HINT}"
        )
    return f"No explore session is active. {OPEN_SESSION_HINT}"


def resolve_session_path(
    session_path: str | None = None,
    *,
    ctx: MCPContext | None = None,
) -> str:
    """Return the notebook path a session tool must act on, or refuse.

    FR-005: every session tool acts on the focused session by default, accepts
    an explicit session path instead, and refuses when neither is available.
    This is that rule, in one place, so that seven tools cannot implement it
    seven ways.

    Parameters
    ----------
    session_path
        The notebook path the agent named explicitly, if it named one. An
        explicit path wins over the focus — including over a *stale* focus,
        which is the whole point of FR-005's escape hatch: it is how the agent
        works in a session the person is not looking at. It is normalised to the
        project-relative POSIX form ``SessionService.session_for`` looks a
        session up by, but its existence is not checked here; the session API
        owns that answer and raises its own error for a notebook it does not
        know.
    ctx
        The MCP context to read the focus from. Defaults to the installed one.

    Returns
    -------
    str
        A project-relative POSIX notebook path.

    Raises
    ------
    NoExploreSessionError
        When no explicit path was given and the focus is not a live explore
        session — because the person is on the canvas or at a pause, because no
        focus has ever been reported, or because the focused notebook is gone
        (FR-004). The message names the way to open a session.
    """
    explicit = _clean_path(session_path)
    if explicit is not None:
        return explicit
    if ctx is None:
        ctx = get_optional_context()
    focus = effective_focus(ctx)
    if focus.mode != MODE_EXPLORE or not focus.session_path:
        raise NoExploreSessionError(refusal_message())
    project_dir = getattr(ctx, "project_dir", None) if ctx is not None else None
    if focus_is_stale(focus, project_dir):
        raise NoExploreSessionError(refusal_message(stale_path=focus.session_path))
    return focus.session_path


__all__ = [
    "FOCUS_FIELDS",
    "FOCUS_MODES",
    "MODE_CANVAS",
    "MODE_EXPLORE",
    "MODE_PAUSE",
    "OPEN_SESSION_HINT",
    "NoExploreSessionError",
    "WorkspaceFocus",
    "canvas_focus",
    "effective_focus",
    "focus_is_stale",
    "focus_notebook_path",
    "refusal_message",
    "resolve_session_path",
]
