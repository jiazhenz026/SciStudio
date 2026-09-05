"""How a session tool reaches the session service, and nothing more.

ADR-054 spec 5, FR-019 to FR-024 (issue #2254).

FR-024 is the rule this module exists to keep: **every session tool goes through
the session API, and none of them reaches the kernel, the notebook file, or the
queue.** The seven tools therefore hold exactly two references — a
:class:`~scistudio.explore.session.SessionService` and the
:class:`~scistudio.explore.session.ExploreSession` it hands back — and every
other thing they do is a method call on one of those. This module is where both
references come from, so the rule has one place to be checked rather than seven.

**Which service, and why the identity of it is the whole point.** Under the
topology the desktop app runs, these tools execute *inside* the backend process
that already holds the person's session: ``scistudio mcp-bridge`` proxies the
agent's stdio into the running GUI's in-process MCP server. A service built here
in that process would be a *second*
:class:`~scistudio.explore.session.SessionService` over the same notebook files
— two ``NotebookStore`` documents over one file, and a cell the agent appends
reaching the person only when their own session next reloads, which is the
opposite of what FR-024 promises. So the service comes from the runtime context:
:meth:`~scistudio.ai.agent.mcp._context.MCPContext.get_session_service`, which
``_RuntimeAdapter`` in ``scistudio.api.app`` answers out of the registry
``scistudio.api.routes.explore`` serves its own routes from. The crossing is
that way round because the AI layer must not import the API layer — the
import-linter contract "AI must not depend on api" forbids the edge with no
carve-out — so the API layer, which may import neither this package's
``__init__`` nor its Protocol, pushes the service down through the structural
context both sides already agree on.

**When there is genuinely no live service.** A standalone ``scistudio
mcp-bridge`` with no backend behind it has no session service to share, and a
tool still has to be able to open a notebook. This module then builds one of its
own over the open project — a *detached* service, built once per project and
cached, and never quietly: :func:`resolve_session_service` reports the origin to
any caller that asks, and the first detached build for a project logs a WARNING
naming the consequence. An agent working through a detached service is working
on its own copy of the notebook, and that is a fact about its answers.

Nothing here is a shortcut past the API. ``reload_if_changed`` is a session
method; ``open_notebook`` is a service method; the packaging seam the tools use
is the same pair of module functions ``api/routes/explore.py`` calls, with the
session's own marks, bindings and observations passed in — which is how
``scistudio.explore.packaging`` is designed to be called and why it never
reaches into a session to find them.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from scistudio.ai.agent.mcp._context import _resolve_project_root, get_context

if TYPE_CHECKING:  # pragma: no cover - typing only
    from scistudio.explore.session import ExploreSession, SessionService

logger = logging.getLogger(__name__)

__all__ = [
    "ORIGIN_DETACHED",
    "ORIGIN_RUNTIME",
    "SESSION_SERVICE_ACCESSORS",
    "ServiceOrigin",
    "SessionToolError",
    "reset_fallback_services",
    "resolve_session_service",
    "session_for",
    "session_service",
]

#: The names this module asks the context for, in order. ``get_session_service``
#: is the member ``MCPContext`` declares and ``_RuntimeAdapter`` implements;
#: ``session_service`` is accepted as a plain attribute so a runtime that holds
#: the service rather than looking it up satisfies the same contract.
SESSION_SERVICE_ACCESSORS: tuple[str, ...] = ("get_session_service", "session_service")

#: The service is the runtime's own — the same object the HTTP routes act on, so
#: a cell this agent appends is a cell the person sees.
ORIGIN_RUNTIME = "runtime"

#: The service is this process's own, built over the open project because the
#: runtime carried none. Correct for a standalone bridge, and a warning sign
#: anywhere else: nothing else is looking at the notebook through it.
ORIGIN_DETACHED = "detached"

#: Resolved project dir -> the detached service this process built for it. Keyed
#: by path, and cached, so that repeated tool calls in one process share one
#: service rather than opening a new notebook store per call.
_fallback_services: dict[str, Any] = {}
_fallback_lock = threading.Lock()

#: The project dirs a detached build has already been logged for, so the WARNING
#: names the condition once instead of once per tool call.
_warned_detached: set[str] = set()


@dataclass(frozen=True)
class ServiceOrigin:
    """Where the service a tool is about to act through came from, and why.

    Returned beside the service by :func:`resolve_session_service` so that the
    detached case is observable rather than silent. ``detail`` is written to be
    read by a person diagnosing a session that "did not update", and names the
    condition, not the code path.
    """

    origin: str
    project_dir: str | None
    detail: str

    @property
    def is_detached(self) -> bool:
        """``True`` when nothing else is looking at the notebook through this service."""
        return self.origin == ORIGIN_DETACHED


class SessionToolError(RuntimeError):
    """A session tool cannot act, and the message says what to do instead.

    A ``RuntimeError`` because that is what the MCP tool layer already surfaces
    to the agent as a tool error — the same class
    :func:`scistudio.ai.agent.mcp._context._resolve_project_root` and
    :class:`scistudio.ai.agent.mcp._focus.NoExploreSessionError` raise for the
    same purpose. Used for the two conditions a tool cannot answer around: no
    project is open, and the named notebook is not there.
    """


def reset_fallback_services() -> None:
    """Drop every cached detached service. For tests, and for a project switch.

    Shutting the services down is deliberately **not** done here: a service this
    module built may still own live kernels, and a helper called to clear a
    cache must not terminate a person's processes as a side effect. A project
    switch retires them through the API's own registry.

    The record of which projects have already been warned about is cleared with
    them, so a service rebuilt after a switch is announced again.
    """
    with _fallback_lock:
        _fallback_services.clear()
        _warned_detached.clear()


def session_service() -> SessionService:
    """Return the session service the tools act through.

    The runtime's own service when it has one — which is the case that matters,
    because it is the person's — and otherwise a detached service over the open
    project. :func:`resolve_session_service` is the same call with the origin
    attached, for a caller that needs to know which of the two it got.

    Raises:
        SessionToolError: No project is open, so there is no ``explore/``
            directory to hold a session.
    """
    service, _origin = resolve_session_service()
    return service


def resolve_session_service() -> tuple[SessionService, ServiceOrigin]:
    """Return the session service **and** where it came from.

    The runtime context is asked first, by each of
    :data:`SESSION_SERVICE_ACCESSORS` in turn. A context that answers with a
    service hands back :data:`ORIGIN_RUNTIME` and that service — the same object
    the HTTP routes act on, which is the whole point of asking.

    A context that has no such member, answers ``None``, or raises falls through
    to a detached service over the open project (:data:`ORIGIN_DETACHED`). The
    first detached build for a project logs a WARNING naming what it means; the
    origin record says the same thing to a caller that would rather read it than
    grep a log.

    Raises:
        SessionToolError: No project is open, so there is nothing to build a
            detached service over either.
    """
    ctx = get_context()
    reason = "the runtime carries no session service accessor"
    for attribute in SESSION_SERVICE_ACCESSORS:
        candidate = getattr(ctx, attribute, None)
        if candidate is None:
            continue
        try:
            service = candidate() if callable(candidate) else candidate
        except Exception:  # a runtime that has the name but cannot serve it
            logger.warning("session tools: the runtime's %s could not be used", attribute, exc_info=True)
            reason = f"the runtime's {attribute} raised"
            continue
        if service is None:
            reason = f"the runtime's {attribute} reports no live service"
            continue
        # Duck-typed on purpose: what the accessor hands back is whatever the
        # runtime holds, and the tools call only the session API's own members
        # on it.
        origin = ServiceOrigin(
            origin=ORIGIN_RUNTIME,
            project_dir=_project_dir_of(ctx),
            detail=f"the running backend's session service, via the context's {attribute}",
        )
        return cast("SessionService", service), origin
    return _detached_service(reason)


def _project_dir_of(ctx: Any) -> str | None:
    """The context's project dir as a string, or ``None`` when it has none."""
    root = getattr(ctx, "project_dir", None)
    return str(root) if root is not None else None


def _detached_service(reason: str) -> tuple[SessionService, ServiceOrigin]:
    """Build (or reuse) this process's own service over the open project."""
    try:
        project_dir = _resolve_project_root(get_context()).resolve()
    except RuntimeError as exc:
        raise SessionToolError(
            "No project is open, so there is no explore session to work in. Open a project first; "
            "get_project_info says which one is open."
        ) from exc
    key = str(project_dir)
    origin = ServiceOrigin(
        origin=ORIGIN_DETACHED,
        project_dir=key,
        detail=(
            f"a session service this process built over {key}, because {reason}. "
            "Nothing else is reading the notebook through it, so a cell appended here reaches an open "
            "SciStudio window only when that window reloads the file."
        ),
    )
    with _fallback_lock:
        service = _fallback_services.get(key)
        if service is None:
            service = _build_service(project_dir)
            _fallback_services[key] = service
        announce = key not in _warned_detached
        if announce:
            _warned_detached.add(key)
    if announce:
        logger.warning("session tools: %s", origin.detail)
    return cast("SessionService", service), origin


def _build_service(project_dir: Path) -> SessionService:
    """Construct a session service over *project_dir*.

    The git engine and the lineage store are both best-effort, and both matter
    for a reason worth stating rather than inferring:

    * Without a **git engine** the session writes no history, and a notebook
      with no explore commit has no ``notebook_commit`` — which is the block's
      version, so ``package_notebook`` refuses for that reason alone (FR-041).
    * Without a **lineage store** the service has no way to resolve a block's
      output ports, so ``open_explore_session`` can open a session over a file
      but not over a block's outputs, and says so in its refusal.

    The lineage store is taken from the process-global the API publishes when it
    opens a project (:func:`scistudio.core.metadata_store._active_lineage_store`,
    which ``api/runtime/_projects.py`` sets alongside its own field). Reading it
    rather than opening a second SQLite connection to the same file is what
    keeps this from being a second writer to the project's lineage database.
    """
    from scistudio.explore.session import SessionService as _SessionService

    git_engine = None
    try:
        from scistudio.core.versioning.git_engine import GitEngine

        candidate = GitEngine(project_dir)
        if candidate.is_repository(project_dir):
            git_engine = candidate
    except Exception:  # a missing git binary must not stop a session opening
        logger.warning(
            "session tools: no git engine for %s; sessions will write no history and cannot be packaged",
            project_dir,
            exc_info=True,
        )

    lineage_store = None
    try:
        from scistudio.core.metadata_store import _active_lineage_store

        lineage_store = _active_lineage_store()
    except Exception:  # pragma: no cover - the shim is best-effort on both sides
        logger.debug("session tools: no active lineage store to resolve block outputs with", exc_info=True)

    return _SessionService(project_dir, git_engine=git_engine, lineage_store=lineage_store)


def session_for(session_path: str) -> ExploreSession:
    """Return the session over *session_path*, opening it if it is not open yet.

    ``SessionService.open_notebook`` is the session API's own idempotent lookup:
    "open a session on an existing notebook, or return the open one". A notebook
    has at most one session per service, so a path the person already has open
    comes back as *their* session rather than a second one over the same file.

    A notebook that is no longer there is refused by ``open_notebook`` itself,
    which is the refusal below: the store reads the file to answer.

    An open session is then reloaded when the file changed underneath it
    (:meth:`~scistudio.explore.session.ExploreSession.reload_if_changed`), so a
    tool never reads a document another writer has moved on from. That call is
    best-effort — a notebook deleted between the two steps, or a file the store
    no longer recognises, is left to the tool's own call to raise more
    specifically than "could not reload" would.

    Args:
        session_path: Project-relative POSIX path, as
            :func:`scistudio.ai.agent.mcp._focus.resolve_session_path` returns it.

    Raises:
        SessionToolError: No project is open, or there is no notebook there.
    """
    service = session_service()
    try:
        session = service.open_notebook(session_path)
    except FileNotFoundError as exc:
        raise SessionToolError(
            f"There is no notebook at {session_path!r} in this project, so there is no session to act on. "
            f"Open one with open_explore_session, or call get_active_workflow_context to see where the person is."
        ) from exc
    try:
        session.reload_if_changed()
    except Exception:  # the tool's own call will raise more specifically if this mattered
        logger.debug("session tools: %s could not be reloaded before use", session_path, exc_info=True)
    return session
