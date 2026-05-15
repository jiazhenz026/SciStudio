"""FastAPI app factory, lifespan, CORS, and realtime endpoints."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from scieasy.api.routes import (
    ai,
    ai_pty,
    blocks,
    data,
    filesystem,
    lint,
    projects,
    workflows,
)
from scieasy.api.routes import (
    git as git_routes,
)
from scieasy.api.routes import workflow_watcher as workflow_watcher_module
from scieasy.api.runtime import ApiRuntime
from scieasy.api.spa import SPAStaticFiles
from scieasy.api.sse import sse_handler
from scieasy.api.ws import websocket_handler
from scieasy.engine.runners.process_handle import ProcessRegistry


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create and tear down the shared API runtime.

    T-ECA-205: also starts the in-process MCP server (Phase 2 of the
    ADR-033 embedded coding agent cascade). The server listens on a
    project-local socket (POSIX) or TCP loopback port (Windows); the
    ``scieasy mcp-bridge`` subprocess proxies CC stdin/stdout into it.
    Server start is best-effort — if it fails, we log ERROR but let
    FastAPI come up so the rest of the app is usable.
    """
    runtime = ApiRuntime()
    app.state.runtime = runtime
    app.state.registry = ProcessRegistry()

    # ---- ADR-035 §3.10 IPC token ----
    # Audit P1-B (Codex #861-1): the engine must export
    # ``SCIEASY_ENGINE_IPC_TOKEN`` BEFORE any AI Block worker is spawned so
    # the worker subprocess inherits it via os.environ and can authenticate
    # internal IPC calls. Without this, every
    # ``POST /api/ai/pty/internal/*`` call returns 401 and the entire AI
    # Block path is dead-on-arrival.
    from scieasy.api.routes.ai_pty import _ensure_ipc_token

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

    # ---- Phase 2: MCP server lifecycle ----
    mcp_server: object | None = None
    try:
        from scieasy.ai.agent.mcp import _context as _mcp_context
        from scieasy.ai.agent.mcp.server import MCPServer

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
            def workflow_runs(self) -> object:
                return self._rt.workflow_runs

            @property
            def event_bus(self) -> object:
                # Exposed so MCP tools can subscribe to engine events
                # (e.g. capture BLOCK_ERROR tracebacks for ``get_run_status``).
                return self._rt.event_bus

            def start_workflow(self, workflow_id: str) -> object:
                return self._rt.start_workflow(workflow_id)

        _mcp_context.set_context(_RuntimeAdapter(runtime))  # type: ignore[arg-type]
        # Pick a per-process socket path. Without an active project we
        # fall back to a temp-dir sentinel so the server still starts
        # and can be inspected via tools/list.
        project_dir = Path(runtime.active_project.path) if runtime.active_project else Path.home() / ".scieasy"
        socket_path = project_dir / ".scieasy" / "mcp.sock"
        mcp_server = MCPServer(socket_path=socket_path, project_dir=project_dir)
        await mcp_server.start()  # type: ignore[attr-defined]
        app.state.mcp_server = mcp_server
        # ADR-034: publish the live MCP port into the active project's
        # .scieasy/ so the per-project mcp-bridge can find it on (re)open.
        runtime.set_mcp_port(mcp_server.port)
    except Exception:
        import logging

        logging.getLogger(__name__).error("MCP server failed to start", exc_info=True)
        mcp_server = None
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
        for run in runtime.workflow_runs.values():
            if not run.task.done():
                run.task.cancel()
        app.state.registry.terminate_all(grace_period_sec=5.0)
        if mcp_server is not None:
            try:
                await mcp_server.stop()  # type: ignore[attr-defined]
            except Exception:
                import logging

                logging.getLogger(__name__).warning("MCP server stop raised", exc_info=True)
        # Clear the global context so a subsequent app instance starts clean.
        try:
            from scieasy.ai.agent.mcp import _context as _mcp_context

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
            from scieasy.core.metadata_store import set_metadata_store

            set_metadata_store(None)
            import gc

            gc.collect()
        except Exception:
            pass


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    import logging

    # Ensure a SciEasy-specific handler exists so logger calls are not
    # silently discarded.  When invoked via ``scieasy gui`` the CLI already
    # configures logging with ``force=True``; this fallback only fires for
    # standalone API usage (e.g. ``uvicorn scieasy.api.app:create_app``).
    log_level = os.environ.get("SCIEASY_LOG_LEVEL", "INFO").upper()
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=getattr(logging, log_level, logging.INFO),
            format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
            datefmt="%H:%M:%S",
        )

    app = FastAPI(title="SciEasy API", version="0.1.0", lifespan=lifespan)
    cors_origins_raw = os.getenv("SCIEASY_CORS_ORIGINS", "").strip()
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

    app.include_router(workflows.router)
    app.include_router(blocks.router)
    app.include_router(data.router)
    # filesystem router must be registered BEFORE projects router because
    # the projects router uses {project_id:path} which would greedily
    # match /api/projects/{id}/tree as a project-id lookup.
    app.include_router(filesystem.router)
    app.include_router(projects.router)
    app.include_router(ai.router)
    app.include_router(ai_pty.router)
    # ADR-036 §3.3 — server-side ruff lint endpoint for the embedded editor.
    app.include_router(lint.router)
    # ADR-039 §3.5 — git endpoints (commit / log / diff / restore / branch
    # ops / merge / cherry-pick / stash). D39-2.2b made these live.
    app.include_router(git_routes.router)

    @app.get("/api/logs/stream")
    async def logs_stream(request: Request) -> object:
        return await sse_handler(request)

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket) -> None:
        runtime = app.state.runtime
        await websocket_handler(websocket, runtime.event_bus)

    # SPA static files. Must be registered AFTER all /api/* and /ws routes.
    # Two locations are checked, in order:
    #   1. Packaged assets at ``scieasy/api/static/`` — populated by the
    #      setuptools build hook from ``frontend/dist/`` when building wheels.
    #   2. Editable-install fallback at ``<repo-root>/frontend/dist/`` — so
    #      developers can ``pip install -e . && (cd frontend && npm run build)``
    #      and get the SPA without running the full wheel build.
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

    For editable installs (development), ``frontend/dist/`` is preferred
    because it reflects the latest ``npm run build``.  The packaged copy
    at ``src/scieasy/api/static/`` is only used as a fallback — it is
    written once during ``pip install`` and quickly becomes stale when
    the developer rebuilds the frontend.

    Returns the first directory that contains an ``index.html``, or
    ``None`` if no built SPA is available.
    """
    # 1. Prefer frontend/dist/ (fresh dev build).
    #    Walk up from ``src/scieasy/api/app.py`` to the repo root.
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
    packaged = Path(__file__).parent / "static"
    if (packaged / "index.html").is_file():
        return packaged

    return None
