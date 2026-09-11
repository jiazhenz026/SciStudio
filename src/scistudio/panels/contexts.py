"""Backend-owned, project-bound panel contexts and revocable mount capabilities."""

from __future__ import annotations

import json
import secrets
import threading
import time
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from scistudio.panels.descriptor import PanelDescriptor
from scistudio.panels.targets import FrozenTarget, PanelError, child_targets, freeze_target, project_identity
from scistudio.previewers.data_access import PreviewDataAccess

TOKEN_TTL = 600
MAX_CONTEXTS = 128
READ_BYTES = 8 * 1024 * 1024
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
    view_state: Any = None
    root: FrozenTarget | None = None
    parent_context_id: str | None = None
    workflow_id: str | None = None
    block_id: str | None = None
    prompt: Any = None
    grants: dict[str, tuple[str, FrozenTarget]] = field(default_factory=dict)


class PanelContexts:
    """In-memory bounded authority; no panel Python is imported or executed."""

    def __init__(self, runtime: Any, *, clock: Any = time.time) -> None:
        self.runtime = runtime
        self.clock = clock
        self.contexts: OrderedDict[str, PanelContext] = OrderedDict()
        self.prompts: dict[tuple[str, str], dict[str, Any]] = {}
        self.lock = threading.RLock()
        self._project = project_identity(runtime)

    def _synchronize(self) -> None:
        identity = project_identity(self.runtime)
        if identity != self._project:
            self.close_all()
            self._project = identity
        for context in list(self.contexts.values()):
            if context.expires_at <= self.clock():
                self.close(context.context_id)

    def close_all(self) -> None:
        with self.lock:
            self.contexts.clear()
            self.prompts.clear()

    def on_event(self, event: Any) -> None:
        with self.lock:
            self._synchronize()
            data = event.data if isinstance(event.data, dict) else {}
            workflow_id = data.get("workflow_id")
            key = (workflow_id, event.block_id)
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

    def _waiting(self, workflow_id: str, block_id: str) -> dict[str, Any]:
        prompt = self.prompts.get((workflow_id, block_id))
        run = self.runtime.workflow_runs.get(workflow_id)
        scheduler = getattr(run, "scheduler", None)
        pending = getattr(scheduler, "_interactive_futures", {}).get(block_id)
        state = getattr(scheduler, "_block_states", {}).get(block_id)
        if prompt is None or pending is None or pending.done() or getattr(state, "value", state) != "paused":
            raise PanelError(409, "not_waiting", "The block is not waiting for an interactive decision")
        return prompt

    def create(self, payload: dict[str, Any]) -> PanelContext:
        with self.lock:
            self._synchronize()
            if self.runtime.active_project is None:
                raise PanelError(409, "no_project", "Open a project before opening a panel")
            kind = payload.get("kind")
            if kind not in ("preview", "interactive"):
                raise PanelError(400, "unsupported", "Only preview and interactive contexts are implemented in Phase A")
            service = self.runtime.get_preview_service()
            panel_id = payload.get("panel_id")
            root = None
            prompt = None
            parent_id = payload.get("parent_context_id")
            if kind == "preview":
                target = payload.get("target") or {}
                ref = target.get("ref", "")
                parent = self.get(parent_id) if parent_id else None
                if parent is not None:
                    root = self.authorize(parent, ref)
                    if root is parent.root:
                        raise PanelError(403, "unauthorized_ref", "open requires a child of the preview target")
                else:
                    root = freeze_target(self.runtime, ref)
                session_id = payload.get("preview_session_id")
                query = {}
                if session_id:
                    try:
                        session = service.sessions.frozen_session(session_id)
                    except Exception as exc:
                        raise PanelError(409, "stale_context", "The frozen preview session no longer exists") from exc
                    if session.target.ref != ref:
                        raise PanelError(403, "unauthorized_ref", "Preview session does not own this target")
                    if panel_id and session.previewer_id != panel_id:
                        raise PanelError(409, "stale_context", "Panel does not match the frozen preview session")
                    panel_id = session.previewer_id
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
            self.contexts.pop(context_id, None)
            for child in list(self.contexts.values()):
                if child.parent_context_id == context_id:
                    self.close(child.context_id)

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
        if context.kind != "preview" or context.root is None:
            raise PanelError(403, "unauthorized_ref", "Interactive contexts authorize no data references")
        root = context.root
        root.validate(self.runtime)
        if ref == root.target.ref:
            return root
        # A child may be requested before its inventory page was displayed.
        if root.collection:
            for raw in root.collection["items"]:
                if (raw.get("data_ref") or raw.get("collection_ref")) == ref and ref not in root.children:
                    root.children[ref] = freeze_target(self.runtime, ref)
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
                if manifest and not manifest.get("module_url") and manifest.get("panel_id") not in LEGACY_CORE_PANELS:
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
                raise PanelError(413, "read_budget", "Interactive response exceeds 8 MiB")
            self.close(context_id)


# TODO(#2294): Remove compiled core exceptions when Phase B migrates these windows.
#   Out of scope per ADR-054 Phase A/B split; generic missing ids still fail.
#   Followup: https://github.com/jiazhenz026/SciStudio/issues/2294
LEGACY_CORE_PANELS = frozenset({"core.interactive.data_router", "core.interactive.pair_editor"})


def get_panel_contexts(runtime: Any) -> PanelContexts:
    """Reuse one context store per API runtime, including its EventBus subscription."""
    store = getattr(runtime, "_panel_contexts", None)
    if store is None:
        store = PanelContexts(runtime)
        runtime._panel_contexts = store
        for event in PANEL_EVENTS:
            runtime.event_bus.subscribe(event, store.on_event)
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
