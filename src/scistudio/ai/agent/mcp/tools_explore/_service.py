"""How a session tool reaches the session service, and nothing more.

ADR-054 spec 5, FR-019 to FR-024 (issue #2254).

FR-024 is the rule this module exists to keep: **every session tool goes through
the session API, and none of them reaches the kernel, the notebook file, or the
queue.** The seven tools therefore hold exactly two references — a
:class:`~scistudio.explore.session.SessionService` and the
:class:`~scistudio.explore.session.ExploreSession` it hands back — and every
other thing they do is a method call on one of those. This module is where both
references come from, so the rule has one place to be checked rather than seven.

**Where the service comes from, and the gap that is not this task's to close.**
The context Protocol
(:class:`scistudio.ai.agent.mcp._context.MCPContext`) carries the two registries,
the project dir, the active workflow id and the workspace focus — not a session
service. The FastAPI adapter that implements it in production
(``_RuntimeAdapter`` in ``src/scistudio/api/app.py``) forwards no session service
either, and the session service registry itself lives in
``scistudio.api.routes.explore``, which the AI layer must not import: the
import-linter contract "AI must not depend on api" forbids it, with no carve-out.

So this module asks the context first, by name, and falls back to a service of
its own over the open project when the context carries none. Under the attached
topology — the desktop app running, the bridge proxying the agent's stdio into
the GUI's in-process MCP server — the fallback is a *second* service over the
same notebooks as the person's, which is a real hazard and is registered as
**F-B3-1** in ``docs/planning/adr-054-assembly-followups.md``. Two mitigations
are in place until the adapter forwards its service: the fallback is cached per
project so a process never holds more than one, and :func:`session_for` reloads
a notebook that changed on disk (``ExploreSession.reload_if_changed``, the
session API's own answer to an outside edit) before any tool reads or writes it.

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
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from scistudio.ai.agent.mcp._context import _resolve_project_root, get_context

if TYPE_CHECKING:  # pragma: no cover - typing only
    from scistudio.explore.session import ExploreSession, SessionService

logger = logging.getLogger(__name__)

__all__ = [
    "SESSION_SERVICE_ACCESSORS",
    "SessionToolError",
    "reset_fallback_services",
    "session_for",
    "session_service",
]

#: The names this module asks the context for, in order, before building a
#: service of its own. Neither exists on the Protocol today; they are the hook
#: F-B3-1 closes with one forwarded property rather than a second registry.
SESSION_SERVICE_ACCESSORS: tuple[str, ...] = ("get_session_service", "session_service")

#: Resolved project dir -> the fallback service this process built for it. Keyed
#: by path, and cached, so that repeated tool calls in one process share one
#: service rather than opening a new notebook store per call.
_fallback_services: dict[str, Any] = {}
_fallback_lock = threading.Lock()


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
    """Drop every cached fallback service. For tests, and for a project switch.

    Shutting the services down is deliberately **not** done here: a service this
    module built may still own live kernels, and a helper called to clear a
    cache must not terminate a person's processes as a side effect. A project
    switch retires them through the API's own registry.
    """
    with _fallback_lock:
        _fallback_services.clear()


def session_service() -> SessionService:
    """Return the session service the tools act through.

    The context's own service when it carries one, and otherwise a service over
    the open project, built once per project and cached.

    Raises:
        SessionToolError: No project is open, so there is no ``explore/``
            directory to hold a session.
    """
    ctx = get_context()
    for attribute in SESSION_SERVICE_ACCESSORS:
        candidate = getattr(ctx, attribute, None)
        if candidate is None:
            continue
        try:
            service = candidate() if callable(candidate) else candidate
        except Exception:  # pragma: no cover - a runtime that has the name but cannot serve it
            logger.warning("session tools: the runtime's %s could not be used", attribute, exc_info=True)
            continue
        if service is not None:
            # Duck-typed on purpose: the accessor is not on the Protocol, so
            # what it hands back is whatever the runtime holds. The tools call
            # only the session API's own members on it.
            return cast("SessionService", service)
    return _fallback_service()


def _fallback_service() -> SessionService:
    """Build (or reuse) this process's own service over the open project."""
    try:
        project_dir = _resolve_project_root(get_context()).resolve()
    except RuntimeError as exc:
        raise SessionToolError(
            "No project is open, so there is no explore session to work in. Open a project first; "
            "get_project_info says which one is open."
        ) from exc
    key = str(project_dir)
    with _fallback_lock:
        service = _fallback_services.get(key)
        if service is None:
            service = _build_service(project_dir)
            _fallback_services[key] = service
        return service


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
