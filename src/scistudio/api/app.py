"""FastAPI app factory, lifespan, CORS, and realtime endpoints."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from scistudio.api.mcp_lifecycle import stop_project_mcp_server
from scistudio.api.routes import (
    ai,
    ai_pty,
    blocks,
    data,
    diagnostics,
    explore,
    filesystem,
    lint,
    packages,
    panels,
    plots,
    projects,
    runs,
    tutorials,
    types,
    user_docs,
    user_library,
    work_import,
    workflows,
)
from scistudio.api.routes import (
    git as git_routes,
)
from scistudio.api.routes import workflow_watcher as workflow_watcher_module
from scistudio.api.runtime import ApiRuntime
from scistudio.api.spa import SPAStaticFiles
from scistudio.api.sse import sse_handler
from scistudio.api.ws import websocket_handler
from scistudio.engine.runners.process_handle import ProcessRegistry


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create and tear down the shared API runtime.

    T-ECA-205: also starts the in-process MCP server (Phase 2 of the
    ADR-033 embedded coding agent cascade). The server listens on a
    project-local socket (POSIX) or TCP loopback port (Windows); the
    ``scistudio mcp-bridge`` subprocess proxies CC stdin/stdout into it.
    Server start is best-effort — if it fails, we log ERROR but let
    FastAPI come up so the rest of the app is usable.
    """
    runtime = ApiRuntime()
    app.state.runtime = runtime
    app.state.registry = ProcessRegistry()

    # ---- ADR-035 §3.10 IPC token ----
    # Audit P1-B (Codex #861-1): the engine must export
    # ``SCISTUDIO_ENGINE_IPC_TOKEN`` BEFORE any AI Block worker is spawned so
    # the worker subprocess inherits it via os.environ and can authenticate
    # internal IPC calls. Without this, every
    # ``POST /api/ai/pty/internal/*`` call returns 401 and the entire AI
    # Block path is dead-on-arrival.
    from scistudio.api.routes.ai_pty import _ensure_ipc_token

    _ensure_ipc_token()

    # ---- ADR-034 Phase 2: workflow filesystem watcher ----
    # Watches the active project's ``workflows/`` directory and republishes
    # YAML mtime/create/delete events as ``workflow.changed`` engine events.
    # The existing ``/ws`` outbound loop forwards that event type, so the
    # browser canvas auto-refetches whenever claude / codex / an external
    # editor mutates a workflow on disk.
    watcher = workflow_watcher_module.WorkflowWatcher(runtime.event_bus)
    workflow_watcher_module.set_active_watcher(watcher)
    app.state.workflow_watcher = watcher
    if runtime.active_project is not None:
        try:
            loop = asyncio.get_running_loop()
            watcher.start_for_project(Path(runtime.active_project.path), loop)
        except Exception:
            import logging

            logging.getLogger(__name__).warning("workflow_watcher: initial start failed", exc_info=True)

    # ---- ADR-039 §3.8: git-state watcher ----
    # NOTE: D39-3.2 (#968) collapsed the previously-separate
    # ``core.versioning.watcher.GitChangeWatcher`` (asyncio-poll) into
    # ``workflow_watcher._GitHeadHandler`` (watchdog Observer) above. The
    # unified watcher attaches a second schedule to the project's
    # ``.git/`` directory inside ``WorkflowWatcher.start_for_project`` and
    # emits ``git.head_changed`` with the canonical ``commit_sha`` field
    # the frontend reads (see ``frontend/src/hooks/useWebSocket.ts``).
    # Project switch already restarts the watcher via
    # ``routes/projects.py::_restart_workflow_watcher``, so a separate
    # git-watcher lifecycle hook is no longer required.

    # ---- Phase 2: MCP context lifecycle ----
    #
    # The actual MCP server binds after a project is opened, through
    # ``api.mcp_lifecycle.ensure_project_mcp_server``. Binding here before
    # an active project exists would force every desktop instance to share
    # the same home-scoped fallback socket, which is not safe across stale
    # packaged backend processes.
    try:
        from scistudio.ai.agent.mcp import _context as _mcp_context

        # ApiRuntime structurally satisfies the MCPContext Protocol once
        # we expose ``project_dir`` as a property — wrap it in a small
        # adapter rather than touching ApiRuntime itself (the AI layer
        # cannot import from ``api/`` and ``api/`` should not know about
        # the MCP Protocol shape).
        class _RuntimeAdapter:
            def __init__(self, rt: ApiRuntime) -> None:
                self._rt = rt

            @property
            def block_registry(self) -> object:
                return self._rt.block_registry

            @property
            def type_registry(self) -> object:
                return self._rt.type_registry

            @property
            def project_dir(self) -> Path | None:
                return Path(self._rt.active_project.path) if self._rt.active_project else None

            @property
            def active_workflow_id(self) -> str | None:
                # ADR-040 Addendum 5 / #1488: surface the runtime field
                # to MCP tools through the protocol member. Defensive
                # getattr so an older ApiRuntime build without the
                # field still satisfies the Protocol (returns None).
                return getattr(self._rt, "active_workflow_id", None)

            @property
            def workspace_focus(self) -> dict[str, Any] | None:
                # ADR-054 spec 5 FR-003 (#2254): the same channel, widened. The
                # adapter forwards the runtime's focus record exactly as it
                # forwards the workflow id above — and it has to be forwarded
                # here rather than picked up by attribute fallthrough, because
                # this adapter declares every member it exposes.
                #
                # The mapping crosses as a mapping: the MCP side parses it into
                # its ``WorkspaceFocus`` record, so ``api.runtime`` never has to
                # import the MCP package (which would pull FastMCP and every
                # tool module into it).
                return getattr(self._rt, "workspace_focus", None)

            def get_session_service(self) -> object | None:
                # ADR-054 spec 5 FR-024 (#2254), closing follow-up F-B3-1. The
                # seven session MCP tools must act on the *person's* explore
                # session, and under the topology the desktop app runs they
                # execute inside this very process: ``scistudio mcp-bridge``
                # proxies the agent's stdio into this app's in-process MCP
                # server. Without this forward the tools found no service on
                # the context and stood a second ``SessionService`` up beside
                # the one the routes hold — two ``NotebookStore`` documents
                # over one file, and an appended cell that reached the person
                # only when their own session happened to reload.
                #
                # The registry is ``api.routes.explore``'s, not the runtime's,
                # so the forward goes through that module's narrow accessor
                # (``live_session_service``) rather than duplicating the
                # lookup. ``None`` means no project is open, which the tool
                # side answers with its own refusal.
                #
                # It has to be declared here rather than picked up by
                # attribute fallthrough, because this adapter exposes only the
                # members it names — and the crossing has to be this way round,
                # because ``ai`` may not import ``api`` and ``api`` may import
                # neither the MCP package's ``__init__`` (every tool module and
                # FastMCP) nor its Protocol.
                return explore.live_session_service(self._rt)

            @property
            def workflow_runs(self) -> object:
                return self._rt.workflow_runs

            @property
            def event_bus(self) -> object:
                # Exposed so MCP tools can subscribe to engine events
                # (e.g. capture BLOCK_ERROR tracebacks for ``get_run_status``).
                return self._rt.event_bus

            def start_workflow(self, workflow_id: str) -> object:
                return self._rt.start_workflow(workflow_id)

            def register_plot_artifact(
                self,
                artifact_path: str | Path,
                *,
                cache_key: str | None = None,
                workflow_id: str | None = None,
                node_id: str | None = None,
                output_port: str | None = None,
                plot_id: str | None = None,
            ) -> object:
                return self._rt.register_plot_artifact(
                    artifact_path,
                    cache_key=cache_key,
                    workflow_id=workflow_id,
                    node_id=node_id,
                    output_port=output_port,
                    plot_id=plot_id,
                )

        _mcp_context.set_context(_RuntimeAdapter(runtime))  # type: ignore[arg-type]
        app.state.mcp_server = None
    except Exception:
        import logging

        logging.getLogger(__name__).error("MCP context failed to initialize", exc_info=True)
        app.state.mcp_server = None

    try:
        yield
    finally:
        # Stop the FS watcher first so its observer thread does not race
        # against the rest of the teardown.
        try:
            watcher.stop()
        except Exception:
            import logging

            logging.getLogger(__name__).warning("workflow_watcher: stop raised", exc_info=True)
        workflow_watcher_module.set_active_watcher(None)
        # D39-3.2 (#968): the standalone git_watcher was deleted — its
        # ``.git/`` surface is now covered by the unified workflow_watcher
        # observer above. No separate teardown required.
        pending_run_tasks = []
        for run in runtime.workflow_runs.values():
            if not run.task.done():
                run.task.cancel()
                pending_run_tasks.append(run.task)
        if pending_run_tasks:
            await asyncio.gather(*pending_run_tasks, return_exceptions=True)
        # ADR-054 spec 3 (#2240): close every explore session and stop its
        # kernel. The session services are module state in
        # ``api.routes.explore`` rather than runtime state, so nothing else in
        # this teardown reaches them — without this call an ipykernel process
        # per open notebook outlives the backend it was started by.
        from scistudio.api.routes.explore import shutdown_session_services

        shutdown_session_services()
        app.state.registry.terminate_all(grace_period_sec=5.0)
        await stop_project_mcp_server(app, runtime)
        # Clear the global context so a subsequent app instance starts clean.
        try:
            from scistudio.ai.agent.mcp import _context as _mcp_context

            _mcp_context.set_context(None)
        except Exception:
            pass
        # ADR-039: drop the per-project MetadataStore reference so its
        # sqlite handle is gc-eligible. We cannot call ``close()`` directly
        # because sqlite3.Connection is thread-affine (opened in the
        # FastAPI worker thread; this runs in the lifespan event-loop
        # thread). Setting the module global to None + forcing a gc pass
        # releases the connection on Windows ~99% of the time, which is
        # sufficient for test cleanup.
        try:
            from scistudio.core.metadata_store import set_metadata_store

            set_metadata_store(None)
            import gc

            gc.collect()
        except Exception:
            pass


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    # #1741: install console + persistent JSON-line file logging. Idempotent, so
    # it is safe whether the CLI already configured logging (``scistudio gui``)
    # or this is standalone API usage (``uvicorn scistudio.api.app:create_app``).
    from scistudio.utils.logging import configure_logging

    log_level = os.environ.get("SCISTUDIO_LOG_LEVEL", "INFO").upper()
    configure_logging(log_level)

    # #1742: the FastAPI app version derives from the single source of truth.
    from scistudio.version import get_version

    app = FastAPI(title="SciStudio API", version=get_version().pep440, lifespan=lifespan)
    cors_origins_raw = os.getenv("SCISTUDIO_CORS_ORIGINS", "").strip()
    if cors_origins_raw == "*":
        origins: list[str] = ["*"]
    elif cors_origins_raw:
        origins = [o.strip() for o in cors_origins_raw.split(",")]
    else:
        origins = [
            "http://localhost:5173",
            "http://localhost:8000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:8000",
        ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ADR-054 spec 1 FR-021 (#2229): the merged panel asset route answers the
    # opaque origin a sandboxed panel presents, and no other route does. The
    # global CORS middleware above cannot express that — with
    # `SCISTUDIO_CORS_ORIGINS=*` it answers every origin including `null`, and
    # even the default satisfies the invariant only by the accident of `null`
    # not being in the list. Added after CORS so it sits outside it and sees the
    # headers CORS has set (Starlette runs middleware in reverse add order).
    from scistudio.api._opaque_origin_middleware import OpaqueOriginGuardMiddleware
    from scistudio.panels.descriptor import PANEL_ASSET_ROUTE_PREFIX

    app.add_middleware(OpaqueOriginGuardMiddleware, asset_route_prefix=PANEL_ASSET_ROUTE_PREFIX)

    # #1741: request/exception logging with correlation ids. Added after CORS so
    # it sits OUTERMOST (Starlette runs middleware in reverse add order), seeing
    # every request and any exception that escapes the routes.
    from scistudio.api._logging_middleware import RequestLoggingMiddleware

    app.add_middleware(RequestLoggingMiddleware)

    app.include_router(workflows.router)
    app.include_router(blocks.router)
    # ADR-053 §7 — the registered data type listing and the data-type template.
    # Registered beside the block router rather than under it: FR-027 makes the
    # Data types tab independent of the block listing, and a router nested in
    # ``/api/blocks`` would contradict that in the URL if not in the code.
    app.include_router(types.router)
    app.include_router(data.router)
    # ADR-048 SPEC 1: routed panel session API (additive to data.router).
    app.include_router(data.previews_router)
    # ADR-054 spec 1 D-020: the panel API surface — the one merged asset route
    # (FR-021), the catalogue and rebuild and per-capability choice FR-023 moved
    # here from ``/api/previews``, and the editing endpoints (FR-024 to FR-029).
    app.include_router(panels.router)
    # ADR-048 SPEC 2 / #1606: plot-job run + preview-wiring endpoint. Runs a
    # plot job and registers the produced artifact so the frontend can open a
    # routed plot_artifact preview session (producer -> PlotPanel link).
    app.include_router(plots.router)
    app.include_router(tutorials.router)
    app.include_router(packages.router)
    # filesystem router must be registered BEFORE projects router because
    # the projects router uses {project_id:path} which would greedily
    # match /api/projects/{id}/tree as a project-id lookup.
    app.include_router(filesystem.router)
    app.include_router(projects.router)
    # ADR-053 §4 — the user-wide library write path. Registered beside the
    # project file endpoints it inverts (FR-007) rather than under them: its
    # target lives outside every project root, so it cannot hang off
    # ``/api/projects/{project_id}``.
    app.include_router(user_library.router)
    app.include_router(ai.router)
    app.include_router(ai_pty.router)
    # ADR-036 §3.3 — server-side ruff lint endpoint for the embedded editor.
    app.include_router(lint.router)
    # ADR-038 §5.2 — ``runs`` router (lineage REST surface, D38-2.4a).
    app.include_router(runs.router)
    # ADR-054 spec 3 §FR-056 (#2240) — the Explore Session API.
    #
    # This line has to stay HERE, with the other ``include_router`` calls and
    # above the ``SPAStaticFiles`` mount at the bottom of this function. That
    # mount is registered at ``/`` and matches every path, ``/api/explore/...``
    # included, answering it with the SPA's own 404; a router appended after it
    # is registered where nothing can reach it. The mount only exists when a
    # built frontend is present, so moving this line down breaks the running
    # desktop app while a checkout with no ``frontend/dist`` still looks fine —
    # which is why ``tests/api/test_explore_mount.py`` asserts the position in
    # the route table rather than only asserting that a request succeeds.
    app.include_router(explore.router)
    # ADR-039 §3.5 — git endpoints (commit / log / diff / restore / branch
    # ops / merge / cherry-pick). D39-2.2b made these live. ADR-039 Addendum 1
    # (#1352) removed the stash CRUD surface (#1353).
    app.include_router(git_routes.router)
    # #1741/#1742: diagnostics — /api/version, /api/client-logs, /api/diagnostics/bundle.
    app.include_router(diagnostics.router)
    # ADR-053 §4 — Bring In My Work session spawn (POST /api/work-import/sessions).
    app.include_router(work_import.router)
    # #2157: the shipped user documentation, read in the Learning Center.
    app.include_router(user_docs.router)

    @app.get("/api/logs/stream")
    async def logs_stream(request: Request) -> object:
        return await sse_handler(request)

    @app.get("/version")
    async def version() -> object:
        # #1742: convenience top-level alias of /api/version for bug reports.
        from scistudio.version import get_version

        return get_version().as_dict()

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket) -> None:
        runtime = app.state.runtime
        await websocket_handler(websocket, runtime.event_bus)

    # SPA static files. Must be registered AFTER all /api/* and /ws routes.
    # Resolution depends on the run mode (see ``_resolve_spa_static_dir``):
    #   - Bundled desktop app (``SCISTUDIO_BUNDLED=1``): ONLY the embedded
    #     ``scistudio/api/static/`` is served, so the UI never depends on where
    #     the ``.app`` sits (#1747).
    #   - Editable/dev install: ``<repo-root>/frontend/dist/`` (latest
    #     ``npm run build``) is preferred, falling back to the packaged copy.
    # If neither is present, ``GET /`` redirects to the API docs so users
    # still land on something useful.
    static_dir = _resolve_spa_static_dir()
    if static_dir is not None:
        app.mount("/", SPAStaticFiles(directory=str(static_dir), html=True), name="spa")
    else:

        @app.get("/", include_in_schema=False)
        async def root() -> RedirectResponse:
            return RedirectResponse(url="/docs")

    return app


def _resolve_spa_static_dir() -> Path | None:
    """Locate the built SPA assets.

    A bundled/packaged desktop app (``SCISTUDIO_BUNDLED=1``) MUST serve only its
    own embedded ``scistudio/api/static/`` — never the dev walk-up below.
    Otherwise the served frontend would depend on where the ``.app`` physically
    sits: inside a source checkout the walk-up finds a stray ``frontend/dist``
    and serves that; in ``/Applications`` it falls back to the packaged copy.
    Same bundle, different UI (#1747).

    For editable installs (development), ``frontend/dist/`` is preferred because
    it reflects the latest ``npm run build``. The packaged copy at
    ``src/scistudio/api/static/`` is the fallback.

    Returns the first directory that contains an ``index.html``, or ``None`` if
    no built SPA is available.
    """
    packaged = Path(__file__).parent / "static"

    # Bundled desktop app: only ever serve the embedded SPA so the UI is
    # environment-independent (does not depend on the .app's filesystem
    # location). #1747.
    if os.environ.get("SCISTUDIO_BUNDLED") == "1":
        return packaged if (packaged / "index.html").is_file() else None

    # 1. Prefer frontend/dist/ (fresh dev build).
    #    Walk up from ``src/scistudio/api/app.py`` to the repo root.
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "frontend" / "dist"
        if (candidate / "index.html").is_file():
            # #406: Warn when frontend/src is newer than the build.
            src_dir = parent / "frontend" / "src"
            if src_dir.exists():
                try:
                    src_mtime = max(
                        (f.stat().st_mtime for f in src_dir.rglob("*") if f.is_file()),
                        default=0.0,
                    )
                    dist_mtime = (candidate / "index.html").stat().st_mtime
                    if src_mtime > dist_mtime:
                        import logging

                        logging.getLogger(__name__).warning(
                            "frontend/dist may be stale (frontend/src has newer files than "
                            "dist/index.html). Run 'cd frontend && npm run build' to rebuild."
                        )
                except Exception:
                    pass
            return candidate
        if (parent / "pyproject.toml").is_file():
            # Reached the repo root without finding frontend/dist/
            break

    # 2. Fall back to packaged static/ (wheel installs).
    if (packaged / "index.html").is_file():
        return packaged

    return None
