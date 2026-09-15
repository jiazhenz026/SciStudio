"""Backend-owned, project-bound panel contexts and revocable mount capabilities."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import secrets
import threading
import time
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, cast

from scistudio.panels.descriptor import PanelDescriptor
from scistudio.panels.targets import FrozenTarget, PanelError, child_targets, freeze_target, project_identity
from scistudio.previewers.data_access import PreviewDataAccess
from scistudio.previewers.models import PreviewEnvelope

logger = logging.getLogger(__name__)

TOKEN_TTL = 600
MAX_CONTEXTS = 128
READ_BYTES = 20 * 1024 * 1024
READ_ITEMS = 200
READ_ROWS = 200
READ_DIM = 512
READ_POINTS = 2000


def read_access() -> PreviewDataAccess:
    return PreviewDataAccess(
        max_rows=READ_ROWS,
        max_bytes=READ_BYTES,
        max_items=READ_ITEMS,
        max_tile=READ_DIM,
        max_dim=READ_DIM,
        text_chars=65536,
    )


def _running_loop() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


@dataclass
class PanelContext:
    context_id: str
    panel: PanelDescriptor
    kind: str
    project: tuple[Any, ...]
    preview_service: Any
    token: str
    expires_at: float
    input: Any
    bootstrap_proof: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    view_state: Any = None
    root: FrozenTarget | None = None
    parent_context_id: str | None = None
    workflow_id: str | None = None
    block_id: str | None = None
    prompt: Any = None
    grants: dict[str, tuple[str, FrozenTarget]] = field(default_factory=dict)
    # MiniApp (miniapp kind) fields: the resident process and what a Restart
    # needs to start a new one for the same context and target (FR-006/FR-014),
    # plus the realtime client the context is bound to (FR-013).
    port: str | None = None
    source: dict[str, Any] | None = None
    process: Any = None
    project_dir: Any = None
    setup_payload: Any = None
    import_roots: tuple[str, ...] = ()
    ws_client_id: str | None = None
    watcher: Any = None

    def provides(self) -> tuple[list[str], list[str]]:
        """The operations and services this context exposes to its page."""
        if self.kind == "miniapp":
            return (["read", "call"] if self.panel.has_python else ["read"]), ["save"]
        if self.kind == "preview":
            return ["read"], ["open", "save"]
        return ["writeBack"], ["save"]


class PanelContexts:
    """In-memory bounded authority; no panel Python is imported or executed."""

    def __init__(self, runtime: Any, *, clock: Any = time.time) -> None:
        self.runtime = runtime
        self.event_bus = runtime.event_bus
        self.clock = clock
        self.contexts: OrderedDict[str, PanelContext] = OrderedDict()
        self.prompts: dict[tuple[str, str], dict[str, Any]] = {}
        self.lock = threading.RLock()
        self._project = project_identity(runtime)
        # The loop a watchdog thread hands a panel.files_changed event to. The
        # store is first built from the panels lifespan, which runs on the API
        # event loop; a store built off it (a test, a synchronous host) keeps
        # None and the watcher dispatches the event itself.
        self._loop: asyncio.AbstractEventLoop | None = _running_loop()

    def _synchronize(self) -> None:
        identity = project_identity(self.runtime)
        if identity != self._project:
            self.close_all()
            self._project = identity
        for context in list(self.contexts.values()):
            if context.expires_at <= self.clock():
                self.close(context.context_id)

    def close_all(self) -> None:
        """Revoke all contexts immediately and stop their resources in the background."""
        with self.lock:
            for context in self.contexts.values():
                self._detach(context)
            self.contexts.clear()
            self.prompts.clear()

    @staticmethod
    def _detach(context: PanelContext) -> threading.Thread | None:
        """Take the process off *context* and end it on its own thread."""
        process = getattr(context, "process", None)
        context.process = None
        watcher = getattr(context, "watcher", None)
        context.watcher = None
        if process is None and watcher is None:
            return None

        def stop_resources() -> None:
            if watcher is not None:
                with contextlib.suppress(Exception):
                    watcher.stop()
            if process is not None:
                process.stop()

        thread = threading.Thread(target=stop_resources, name=f"panel-stop-{context.context_id}", daemon=True)
        thread.start()
        return thread

    @classmethod
    def _stop(cls, context: PanelContext) -> None:
        """End a context's process without waiting for it."""
        # End a context's process without waiting for it (FR-013, SC-005).
        #
        # ``PanelProcess.stop`` runs teardown, waits out the grace period and then
        # kills the tree — up to ten seconds for a ``panel.py`` that hangs in
        # ``teardown``. Every caller here holds the store lock, and one of them
        # (``_synchronize``) runs on the path of every panel request, so the wait
        # happens on its own thread. The process is detached from the context
        # first, so nothing can reach it again, and the tree is ended either way:
        # by ``stop`` itself, or by the application registry's ``terminate_all``
        # at shutdown.
        cls._detach(context)

    def on_event(self, event: Any) -> None:
        # The bus awaits this on the API event loop, so it is also the second
        # chance to learn the loop a watcher hands its event to when the store
        # was first built off the loop.
        self._loop = _running_loop() or self._loop
        with self.lock:
            self._synchronize()
            data = event.data if isinstance(event.data, dict) else {}
            workflow_id = data.get("workflow_id")
            if not isinstance(workflow_id, str):
                return
            key = (workflow_id, str(event.block_id or ""))
            if event.event_type == "interactive_prompt":
                self._close_waiting(key)
                self.prompts[key] = deepcopy(data)
                return
            if event.block_id:
                self._close_waiting(key)
                self.prompts.pop(key, None)
            elif workflow_id:
                for pending in list(self.prompts):
                    if pending[0] == workflow_id:
                        self._close_waiting(pending)
                        self.prompts.pop(pending, None)

    def _close_waiting(self, key: tuple[str, str]) -> None:
        for context in list(self.contexts.values()):
            if (context.workflow_id, context.block_id) == key:
                self.close(context.context_id)

    def _waiting(self, workflow_id: str | None, block_id: str | None) -> dict[str, Any]:
        if not workflow_id or not block_id:
            raise PanelError(422, "invalid_request", "workflow_id and block_id are required")
        prompt = self.prompts.get((workflow_id, block_id))
        run = self.runtime.workflow_runs.get(workflow_id)
        scheduler = getattr(run, "scheduler", None)
        pending = getattr(scheduler, "_interactive_futures", {}).get(block_id)
        state = getattr(scheduler, "_block_states", {}).get(block_id)
        if prompt is None or pending is None or pending.done() or getattr(state, "value", state) != "paused":
            raise PanelError(409, "not_waiting", "The block is not waiting for an interactive decision")
        return prompt

    def create(self, payload: dict[str, Any], *, process_registry: Any = None) -> PanelContext:
        with self.lock:
            self._synchronize()
            if self.runtime.active_project is None:
                raise PanelError(409, "no_project", "Open a project before opening a panel")
            kind = payload.get("kind")
            if kind not in ("preview", "interactive", "miniapp"):
                raise PanelError(400, "unsupported", "Panel context kind must be preview, interactive or miniapp")
            if kind == "miniapp":
                return self._create_miniapp(payload, process_registry=process_registry)
            service = self.runtime.get_preview_service()
            panel_id = payload.get("panel_id")
            root = None
            prompt = None
            parent_id = payload.get("parent_context_id")
            if kind == "preview":
                target = payload.get("target") or {}
                ref = target.get("ref", "")
                session_id = payload.get("preview_session_id")
                authority = None
                if session_id:
                    try:
                        session = service.sessions.frozen_session(session_id)
                        authority = service.sessions.session_authority(session_id)
                    except Exception as exc:
                        raise PanelError(409, "stale_context", "The frozen preview session no longer exists") from exc
                    if session.target.ref != ref:
                        raise PanelError(403, "unauthorized_ref", "Preview session does not own this target")
                    if panel_id and session.previewer_id != panel_id:
                        raise PanelError(409, "stale_context", "Panel does not match the frozen preview session")
                    panel_id = session.previewer_id
                parent = self.get(parent_id) if parent_id else None
                if parent is not None:
                    root = self.authorize(parent, ref)
                    if root is parent.root:
                        raise PanelError(403, "unauthorized_ref", "open requires a child of the preview target")
                elif isinstance(authority, FrozenTarget):
                    root = authority
                    root.validate(self.runtime)
                else:
                    root = freeze_target(self.runtime, ref)
                query = {}
                if panel_id:
                    query["panel_id"] = panel_id
                spec = service.sessions._select_spec(root.target, query)
                panel_id = spec.previewer_id
                input_value = self._input(root)
            else:
                workflow_id, block_id = payload.get("workflow_id"), payload.get("block_id")
                prompt = self._waiting(workflow_id, block_id)
                manifest = prompt.get("panel_manifest") or {}
                if manifest.get("panel_id") != panel_id or manifest.get("module_url"):
                    raise PanelError(403, "panel_mismatch", "Panel id does not match the waiting block's panel")
                input_value = deepcopy(prompt.get("panel_payload") or {})
            panel = service.registry.panels.get(panel_id) if service.registry.panels else None
            if panel is None:
                raise PanelError(404, "unknown_panel", f"Panel {panel_id!r} is not registered")
            if kind not in panel.contexts:
                raise PanelError(
                    409,
                    "context_mismatch",
                    f"Requested panel {panel_id!r} resolves to {panel.owner_kind.value} panel {panel.id!r}, which does not declare {kind}",
                )
            if len(self.contexts) >= MAX_CONTEXTS:
                raise PanelError(429, "context_limit", "Close a panel before opening another")
            context = PanelContext(
                context_id="pc-" + secrets.token_hex(16),
                panel=panel,
                kind=kind,
                project=self._project,
                preview_service=service,
                token=secrets.token_urlsafe(32),
                expires_at=self.clock() + TOKEN_TTL,
                input=input_value,
                view_state=payload.get("view_state"),
                root=root,
                parent_context_id=parent_id,
                workflow_id=payload.get("workflow_id"),
                block_id=payload.get("block_id"),
                prompt=prompt,
            )
            self.contexts[context.context_id] = context
            return context

    def _create_miniapp(self, payload: dict[str, Any], *, process_registry: Any) -> PanelContext:
        """Open a miniapp context on a block output and start its process."""
        from scistudio.panels.miniapp import build_setup_payload, miniapp_input, resolve_source
        from scistudio.panels.process import runtime_import_roots

        service = self.runtime.get_preview_service()
        panel_id = payload.get("panel_id")
        panel = service.registry.panels.get(panel_id) if service.registry.panels else None
        if panel is None:
            raise PanelError(404, "unknown_panel", f"Panel {panel_id!r} is not registered")
        if "miniapp" not in panel.contexts:
            raise PanelError(409, "context_mismatch", f"Panel {panel.id!r} does not declare miniapp")
        source = payload.get("source") or {}
        frozen = resolve_source(self.runtime, source, panel)
        if len(self.contexts) >= MAX_CONTEXTS:
            raise PanelError(429, "context_limit", "Close a panel before opening another")
        project_dir = getattr(self.runtime.active_project, "path", None)
        setup_payload = build_setup_payload(self.runtime, frozen)
        # FR-006: panel.py imports what a block worker imports, from the same
        # roots, so a MiniApp can use the project's drop-in types and the
        # packages the user installed through the app.
        import_roots = runtime_import_roots(project_dir)
        context = PanelContext(
            context_id="pc-" + secrets.token_hex(16),
            panel=panel,
            kind="miniapp",
            project=self._project,
            preview_service=service,
            token=secrets.token_urlsafe(32),
            expires_at=self.clock() + TOKEN_TTL,
            input=miniapp_input(frozen, panel),
            view_state=payload.get("view_state"),
            root=frozen,
            workflow_id=source.get("workflow_id"),
            block_id=source.get("block_id"),
            port=source.get("port"),
            source={k: source.get(k) for k in ("workflow_id", "block_id", "port")},
            project_dir=project_dir,
            setup_payload=setup_payload,
            import_roots=import_roots,
            ws_client_id=payload.get("ws_client_id"),
        )
        self.contexts[context.context_id] = context
        if panel.has_python:
            self._start_process(context, process_registry)
        self._start_watcher(context)
        return context

    def _start_watcher(self, context: PanelContext) -> None:
        """Watch the MiniApp's own directory while the context is open."""
        # Watch the MiniApp's own directory while the context is open (FR-022).
        from scistudio.panels.watcher import PanelDirectoryWatcher, watches

        if not watches(context.panel):
            return
        watcher = PanelDirectoryWatcher(
            panel_id=context.panel.id,
            directory=context.panel.root,
            event_bus=self.event_bus,
            loop=self._loop,
        )
        try:
            if watcher.start():
                context.watcher = watcher
        except Exception:
            # A MiniApp that cannot be watched still opens; it just does not
            # reload on its own.
            logger.warning("panel watcher: %s not watched", context.panel.id, exc_info=True)

    def _start_process(self, context: PanelContext, process_registry: Any) -> None:
        """Launch the resident subprocess for a miniapp context."""
        # Launch the resident subprocess for a miniapp context (FR-006).
        from scistudio.panels.process import start_panel_process

        if process_registry is None:
            raise PanelError(500, "no_registry", "The application process registry is unavailable")
        if context.project_dir is None:
            raise PanelError(409, "no_project", "Open a project before opening a MiniApp")
        context.process = start_panel_process(
            context_id=context.context_id,
            panel_dir=context.panel.root,
            project_dir=context.project_dir,
            registry=process_registry,
            setup_payload=context.setup_payload,
            import_roots=context.import_roots,
        )

    def restart(self, context_id: str, process_registry: Any = None) -> PanelContext:
        """Start a new process for the same context and target."""
        # Start a new process for the same context and target (FR-014).
        #
        # ``get`` re-validates the frozen target first, so a restart after
        # artifact retention reclaimed the run that produced it closes the context
        # and reports that the data is gone rather than starting a process on a
        # file that is not there — the tab then offers the picker. The target
        # itself is not re-resolved: FR-014 restarts "for the same context and
        # target", and re-resolving would silently move an open MiniApp onto a
        # later run's output.
        #
        # The setup payload is rebuilt from the revalidated target so the new
        # process reconstructs what the catalog says the target is now, and the
        # context's lease is renewed: a restart is the user working with this
        # MiniApp, and leaving ``expires_at`` untouched let a restart late in the
        # 600-second lease be closed by the next ``_synchronize`` moments later.
        from scistudio.panels.miniapp import build_setup_payload

        with self.lock:
            context = self.get(context_id)
            if context.kind != "miniapp":
                raise PanelError(400, "unsupported", "Only a MiniApp context has a process to restart")
            previous = context.process
            context.process = None
            context.expires_at = self.clock() + TOKEN_TTL
            if context.root is not None:
                context.setup_payload = build_setup_payload(self.runtime, context.root)
        if previous is not None:
            previous.stop()
        with self.lock:
            context = self.get(context_id)
            if context.panel.has_python and context.process is None:
                self._start_process(context, process_registry)
            return context

    def stop_process(self, context_id: str) -> PanelContext:
        """Stop the process but keep the context so the tab can Restart it."""
        with self.lock:
            context = self.get(context_id)
            if context.kind != "miniapp" or context.process is None:
                raise PanelError(400, "unsupported", "This context has no panel process to stop")
            process = context.process
        process.stop()
        return context

    def _input(self, root: FrozenTarget) -> dict[str, Any]:
        if root.collection is not None:
            return {
                "ref": root.target.ref,
                "kind": "collection_ref",
                **child_targets(self.runtime, root, read_access()),
            }
        return {**root.target.to_dict(), "metadata": deepcopy(root.metadata)}

    def get(self, context_id: str) -> PanelContext:
        with self.lock:
            self._synchronize()
            context = self.contexts.get(context_id)
            if context is None:
                raise PanelError(404, "unknown_context", "The panel context is unknown, closed or expired")
            try:
                if (
                    context.project != project_identity(self.runtime)
                    or context.preview_service is not self.runtime.get_preview_service()
                ):
                    raise PanelError(409, "stale_context", "The panel's project or registry changed")
                if context.root:
                    context.root.validate(self.runtime)
                if (
                    context.kind == "interactive"
                    and self._waiting(context.workflow_id, context.block_id) is not context.prompt
                ):
                    raise PanelError(409, "stale_context", "The waiting prompt changed")
            except PanelError:
                self.close(context_id)
                raise
            return context

    def close(self, context_id: str) -> None:
        with self.lock:
            context = self.contexts.pop(context_id, None)
            if context is not None:
                self._stop(context)
            for child in list(self.contexts.values()):
                if child.parent_context_id == context_id:
                    self.close(child.context_id)

    def close_for_client(self, ws_client_id: str) -> None:
        """Close every miniapp context bound to a gone realtime client."""
        # Close every miniapp context bound to a gone realtime client (FR-013).
        #
        # The 30-second disconnect debounce lives in the realtime layer
        # (``src/scistudio/api/ws.py``), as the cancellation of browser-owned runs
        # does; this call performs the close once that layer decides the client is
        # gone.
        with self.lock:
            for context in list(self.contexts.values()):
                if context.kind == "miniapp" and context.ws_client_id == ws_client_id:
                    self.close(context.context_id)

    def renew(self, context_id: str) -> PanelContext:
        with self.lock:
            context = self.get(context_id)
            context.expires_at = self.clock() + TOKEN_TTL
            return context

    def by_token(self, token: str) -> PanelContext:
        with self.lock:
            self._synchronize()
            for context in list(self.contexts.values()):
                if secrets.compare_digest(context.token, token):
                    return self.get(context.context_id)
            raise PanelError(403, "invalid_token", "Invalid or expired panel asset token")

    def authorize(self, context: PanelContext, ref: str) -> FrozenTarget:
        # A miniapp context authorizes reads on its target as a preview does; an
        # interactive context authorizes no data references.
        if context.kind not in ("preview", "miniapp") or context.root is None:
            raise PanelError(403, "unauthorized_ref", "This context authorizes no data references")
        root = context.root
        root.validate(self.runtime)
        if ref == root.target.ref:
            return root
        # A child may be requested before its inventory page was displayed.
        if root.collection:
            for raw in root.collection["items"]:
                if (raw.get("data_ref") or raw.get("collection_ref")) == ref and ref not in root.children:
                    root.children[ref] = freeze_target(self.runtime, ref)
                    root.children[ref].parent = root
                    break
        elif ref.startswith(root.target.ref + "#"):
            child_targets(self.runtime, root, read_access())
        stack = list(root.children.values())
        while stack:
            child = stack.pop()
            child.validate(self.runtime)
            if child.target.ref == ref:
                return child
            stack.extend(child.children.values())
        raise PanelError(403, "unauthorized_ref", "The context does not authorize this reference")

    def open_child(self, context_id: str, ref: str) -> PreviewEnvelope:
        """Route an authorized child through either existing preview renderer."""
        with self.lock:
            context = self.get(context_id)
            if context.kind != "preview":
                raise PanelError(403, "unsupported", "Only a preview context provides open")
            root = self.authorize(context, ref)
            if root is context.root:
                raise PanelError(403, "unauthorized_ref", "open requires a child of the preview target")
            service, project = context.preview_service, context.project
            query: dict[str, Any] = {"_record_metadata": deepcopy(root.metadata)}
            if root.storage is not None:
                query["_storage"] = {
                    "backend": root.storage.backend,
                    "path": root.storage.path,
                    "format": root.storage.format,
                    "metadata": deepcopy(root.storage.metadata),
                }
            if root.collection is not None:
                query.update(
                    _collection_items=deepcopy(root.collection["items"]),
                    _collection_count=root.collection["count"],
                    _collection_item_type=root.collection.get("item_type"),
                )

            def validate() -> None:
                if project_identity(self.runtime) != project or self.runtime.get_preview_service() is not service:
                    raise PanelError(409, "stale_context", "The child preview's project or registry changed")
                root.validate(self.runtime)

            return cast(
                PreviewEnvelope, service.sessions.create_session(root.target, query, guard=validate, authority=root)
            )

    def grant_artifact(self, context: PanelContext, target: FrozenTarget) -> tuple[str, str]:
        with self.lock:
            self.get(context.context_id)
            for grant_id, (token, frozen) in context.grants.items():
                if frozen is target:
                    return token, grant_id
            token, grant_id = secrets.token_urlsafe(32), secrets.token_hex(16)
            context.grants[grant_id] = (token, target)
            return token, grant_id

    def artifact(self, token: str, grant_id: str) -> FrozenTarget:
        with self.lock:
            self._synchronize()
            for context in list(self.contexts.values()):
                grant = context.grants.get(grant_id)
                if grant and secrets.compare_digest(grant[0], token):
                    self.get(context.context_id)
                    grant[1].validate(self.runtime)
                    return grant[1]
            raise PanelError(403, "invalid_token", "Invalid or revoked artifact grant")

    def claim_writeback(self, context_id: str | None, workflow_id: str, block_id: str, response: Any) -> None:
        """Claim once before the existing WS event emit, with unchanged event payload."""
        with self.lock:
            self._synchronize()
            prompt = self.prompts.get((workflow_id, block_id))
            manifest = (prompt or {}).get("panel_manifest") or {}
            if not context_id:
                if manifest and not manifest.get("module_url"):
                    raise PanelError(403, "missing_context", "Panel writeback requires its waiting context")
                return
            context = self.get(context_id)
            if context.kind != "interactive" or (context.workflow_id, context.block_id) != (workflow_id, block_id):
                raise PanelError(403, "panel_mismatch", "Context does not own this waiting block")
            try:
                encoded = json.dumps(response, allow_nan=False)
            except (TypeError, ValueError) as exc:
                raise PanelError(422, "invalid_response", "Interactive response must be JSON-safe") from exc
            if len(encoded.encode()) > READ_BYTES:
                raise PanelError(413, "read_budget", "Interactive response exceeds 20 MiB")
            self.close(context_id)


def get_panel_contexts(runtime: Any) -> PanelContexts:
    """Reuse one context store per API runtime, including its EventBus subscription."""
    store = getattr(runtime, "_panel_contexts", None)
    if store is None:
        store = PanelContexts(runtime)
        runtime._panel_contexts = store
        for event in PANEL_EVENTS:
            store.event_bus.subscribe(event, store.on_event)
    return store


PANEL_EVENTS = (
    "interactive_prompt",
    "interactive_complete",
    "cancel_block_request",
    "block_cancelled",
    "block_done",
    "block_error",
    "cancel_workflow_request",
    "workflow_completed",
)
