"""PreviewSessionManager — create/read/patch sessions + provider invocation.

Ties the registry, router, and bounded data access together (ADR-048 FR-007):

* :meth:`create_session` routes a :class:`PreviewTarget` to a spec, builds an
  in-memory :class:`PreviewSession`, and renders the first envelope.
* :meth:`read_session` re-renders the current envelope for a session.
* :meth:`patch_session` merges new query state (slice/page/sort/slot/item) and
  re-renders.
* :meth:`read_resource` performs a bounded follow-up resource read for a
  session (e.g. an array tile or a child preview).
* :meth:`render_target` renders a one-shot envelope WITHOUT a session — used by
  the legacy REST compatibility adapter.

Provider calls are wrapped defensively: a routing/typed error becomes an error
envelope; an unexpected provider exception becomes a
:class:`PreviewErrorCode.PROVIDER_EXCEPTION` envelope rather than crashing the
API (FR-028/FR-029). Sessions never mutate workflow/data/lineage state.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from scistudio.previewers.data_access import PreviewDataAccess
from scistudio.previewers.models import (
    EnvelopeKind,
    PreviewEnvelope,
    PreviewError,
    PreviewErrorCode,
    PreviewErrorInfo,
    PreviewerSpec,
    PreviewLimits,
    PreviewMetadata,
    PreviewProvider,
    PreviewRequest,
    PreviewSession,
    PreviewTarget,
    ProviderError,
    UnknownPreviewerError,
)
from scistudio.previewers.registry import PreviewerRegistry
from scistudio.previewers.router import PreviewRouter

logger = logging.getLogger(__name__)

# Bound the in-memory session store so a long GUI session does not leak
# (mirrors the ApiRuntime bounded registries, #1551).
_DEFAULT_MAX_SESSIONS = 512


class PreviewSessionManager:
    """In-memory, thread-safe preview session store + provider dispatcher."""

    def __init__(
        self,
        registry: PreviewerRegistry,
        *,
        max_sessions: int = _DEFAULT_MAX_SESSIONS,
        data_access_factory: Callable[[PreviewLimits], PreviewDataAccess] | None = None,
    ) -> None:
        self._registry = registry
        self._router = PreviewRouter(registry)
        self._sessions: OrderedDict[str, PreviewSession] = OrderedDict()
        self._lock = threading.RLock()
        self._max_sessions = max(1, int(max_sessions))
        self._data_access_factory = data_access_factory or self._default_data_access

    @property
    def router(self) -> PreviewRouter:
        return self._router

    @property
    def registry(self) -> PreviewerRegistry:
        return self._registry

    # -- session lifecycle --------------------------------------------------

    def create_session(self, target: PreviewTarget, query: dict[str, Any] | None = None) -> PreviewEnvelope:
        """Route *target*, create a session, and return the first envelope.

        A routing failure returns an error envelope (no session is created).
        """
        query = dict(query or {})
        try:
            spec = self._router.resolve(target)
        except PreviewError as exc:
            return self._error_envelope(target, exc.code, exc.message, previewer_id="", detail=exc.detail)

        session = PreviewSession(
            session_id=f"pv-{uuid4().hex}",
            previewer_id=spec.previewer_id,
            target=target,
            created_at=_now_iso(),
            query=query,
            cache_key=self._cache_key(spec, target, query),
            limits=PreviewLimits(),
        )
        with self._lock:
            self._sessions[session.session_id] = session
            self._trim_locked()

        envelope = self._render(spec, session.target, session.query, session.limits, session.session_id)
        return envelope

    def read_session(self, session_id: str) -> PreviewEnvelope:
        """Re-render the current envelope for *session_id*.

        Raises :class:`UnknownPreviewerError` (code ``unknown_previewer``) when
        the session id is unknown — the route maps this to a stable 404.
        """
        session = self._get_session(session_id)
        spec = self._require_spec(session.previewer_id)
        return self._render(spec, session.target, session.query, session.limits, session.session_id)

    def patch_session(self, session_id: str, query_patch: dict[str, Any]) -> PreviewEnvelope:
        """Merge *query_patch* into the session query state and re-render."""
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise UnknownPreviewerError(
                    f"Unknown preview session: {session_id}",
                    detail={"session_id": session_id},
                )
            session.query.update(query_patch)
            session.cache_key = self._cache_key(
                self._registry.get(session.previewer_id) or _missing_spec(session.previewer_id),
                session.target,
                session.query,
            )
            self._sessions.move_to_end(session_id)
            target = session.target
            limits = session.limits
            query = dict(session.query)
            previewer_id = session.previewer_id

        spec = self._require_spec(previewer_id)
        return self._render(spec, target, query, limits, session_id)

    def read_resource(self, session_id: str, resource_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Perform a bounded follow-up resource read for a session (FR-009).

        Supports the two resource families the core fallbacks emit:

        * ``tile`` — a bounded array tile read.
        * ``slot:<name>`` / ``item:<idx>`` — child routing for composite slots
          and collection items (returns a freshly-created child envelope).

        Returns a JSON-safe dict. Raises :class:`UnknownPreviewerError` for an
        unknown session and :class:`ProviderError` for an unknown resource.
        """
        session = self._get_session(session_id)
        merged: dict[str, Any] = dict(session.query)
        merged.update(params or {})
        access = self._data_access_factory(session.limits)

        if resource_id == "tile":
            ref = _storage_ref_from_query(merged, session.target.ref)
            tile = access.array_tile(
                ref,
                slice_index=int(merged.get("slice_index", 0) or 0),
                y0=int(merged.get("y0", 0) or 0),
                x0=int(merged.get("x0", 0) or 0),
                height=merged.get("height"),
                width=merged.get("width"),
            )
            return {
                "y0": tile.y0,
                "x0": tile.x0,
                "height": tile.height,
                "width": tile.width,
                "matrix": tile.matrix,
            }

        if resource_id.startswith(("slot:", "item:")):
            # Child routing: build a child target and render it as a one-shot
            # envelope using the same precedence rules (FR US4 scenario 3).
            child_target = self._child_target_from_resource(session.target, resource_id, merged)
            if child_target is None:
                raise ProviderError(
                    f"resource {resource_id!r} could not resolve a child target",
                    detail={"resource_id": resource_id},
                )
            return self.render_target(child_target, merged).to_dict()

        raise ProviderError(
            f"unknown resource id {resource_id!r} for session {session_id}",
            detail={"resource_id": resource_id},
        )

    def get_session(self, session_id: str) -> PreviewSession:
        """Return the session record (no re-render)."""
        return self._get_session(session_id)

    # -- one-shot (compatibility) ------------------------------------------

    def render_target(self, target: PreviewTarget, query: dict[str, Any] | None = None) -> PreviewEnvelope:
        """Render a one-shot envelope without creating a session (compat adapter)."""
        query = dict(query or {})
        try:
            spec = self._router.resolve(target)
        except PreviewError as exc:
            return self._error_envelope(target, exc.code, exc.message, previewer_id="", detail=exc.detail)
        return self._render(spec, target, query, PreviewLimits(), session_id=None)

    # -- internals ----------------------------------------------------------

    def _render(
        self,
        spec: PreviewerSpec,
        target: PreviewTarget,
        query: dict[str, Any],
        limits: PreviewLimits,
        session_id: str | None,
    ) -> PreviewEnvelope:
        provider = self._resolve_provider(spec)
        if provider is None:
            return self._error_envelope(
                target,
                PreviewErrorCode.MISSING_BUNDLE,
                f"previewer {spec.previewer_id!r} has no backend provider",
                previewer_id=spec.previewer_id,
            ).with_session(session_id)

        request = PreviewRequest(
            target=target,
            spec=spec,
            query=query,
            data_access=self._data_access_factory(limits),
            limits=limits,
            session_id=session_id,
        )
        try:
            envelope = provider(request)
        except PreviewError as exc:
            envelope = self._error_envelope(
                target, exc.code, exc.message, previewer_id=spec.previewer_id, detail=exc.detail
            )
        except Exception as exc:
            logger.warning("preview provider %s raised", spec.previewer_id, exc_info=True)
            envelope = self._error_envelope(
                target,
                PreviewErrorCode.PROVIDER_EXCEPTION,
                f"provider {spec.previewer_id!r} raised: {exc}",
                previewer_id=spec.previewer_id,
            )
        return envelope.with_session(session_id)

    def _resolve_provider(self, spec: PreviewerSpec) -> PreviewProvider | None:
        provider = spec.backend_provider
        if provider is None:
            return None
        if callable(provider):
            return provider
        if isinstance(provider, str):
            return _import_provider(provider)
        return None

    def _error_envelope(
        self,
        target: PreviewTarget,
        code: PreviewErrorCode,
        message: str,
        *,
        previewer_id: str,
        detail: dict[str, Any] | None = None,
    ) -> PreviewEnvelope:
        return PreviewEnvelope(
            previewer_id=previewer_id,
            target=target,
            kind=EnvelopeKind.ERROR,
            metadata=PreviewMetadata(complete=False, failed=True),
            error=PreviewErrorInfo(code=code, message=message, detail=detail or {}),
        )

    def _get_session(self, session_id: str) -> PreviewSession:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise UnknownPreviewerError(
                    f"Unknown preview session: {session_id}",
                    detail={"session_id": session_id},
                )
            self._sessions.move_to_end(session_id)
            return session

    def _require_spec(self, previewer_id: str) -> PreviewerSpec:
        spec = self._registry.get(previewer_id)
        if spec is None:
            raise UnknownPreviewerError(
                f"Unknown previewer: {previewer_id}",
                detail={"previewer_id": previewer_id},
            )
        return spec

    def _trim_locked(self) -> None:
        while len(self._sessions) > self._max_sessions:
            self._sessions.popitem(last=False)

    @staticmethod
    def _cache_key(spec: PreviewerSpec, target: PreviewTarget, query: dict[str, Any]) -> str:
        relevant = {
            k: v
            for k, v in query.items()
            if not k.startswith("_")
            and k in {"slice_index", "page", "page_size", "sort_by", "sort_dir", "slot", "item"}
        }
        version = ""
        storage = query.get("_storage")
        if isinstance(storage, dict):
            md = storage.get("metadata")
            if isinstance(md, dict):
                version = str(md.get("data_version", ""))
        parts = [spec.previewer_id, target.ref, version]
        parts.extend(f"{k}={relevant[k]}" for k in sorted(relevant))
        return "|".join(parts)

    @staticmethod
    def _default_data_access(limits: PreviewLimits) -> PreviewDataAccess:
        return PreviewDataAccess(
            max_rows=limits.max_rows,
            max_bytes=limits.max_bytes,
            max_items=limits.max_items,
            max_tile=limits.max_tile,
            max_dim=limits.max_dim,
        )

    def _child_target_from_resource(
        self,
        parent: PreviewTarget,
        resource_id: str,
        params: dict[str, Any],
    ) -> PreviewTarget | None:
        from scistudio.previewers.models import TargetKind

        if resource_id.startswith("item:"):
            item = params.get("item")
            if not isinstance(item, dict):
                return None
            ref = str(item.get("data_ref") or item.get("ref") or "")
            type_name = str(item.get("type_name") or parent.collection_item_type or "")
            if not ref:
                return None
            return PreviewTarget(
                kind=TargetKind.DATA_REF,
                ref=ref,
                recorded_type=type_name,
                type_chain=(type_name,) if type_name else (),
                source=parent.source,
            )
        if resource_id.startswith("slot:"):
            slot_type = str(params.get("slot_type") or "")
            slot_ref = f"{parent.ref}#{params.get('slot', '')}"
            return PreviewTarget(
                kind=TargetKind.DATA_REF,
                ref=slot_ref,
                recorded_type=slot_type,
                type_chain=(slot_type,) if slot_type else (),
                source=parent.source,
            )
        return None


def _import_provider(dotted: str) -> PreviewProvider | None:
    """Resolve a ``module:callable`` (or ``module.callable``) provider import path."""
    import importlib

    try:
        if ":" in dotted:
            mod_name, attr = dotted.split(":", 1)
        else:
            mod_name, attr = dotted.rsplit(".", 1)
        module = importlib.import_module(mod_name)
        provider = getattr(module, attr)
    except Exception:
        logger.warning("Failed to import previewer provider %r", dotted, exc_info=True)
        return None
    return provider if callable(provider) else None


def _storage_ref_from_query(query: dict[str, Any], fallback_ref: str) -> Any:
    from scistudio.core.storage.ref import StorageReference

    storage = query.get("_storage") or {}
    return StorageReference(
        backend=str(storage.get("backend", "filesystem")),
        path=str(storage.get("path", fallback_ref)),
        format=storage.get("format"),
        metadata=storage.get("metadata"),
    )


def _missing_spec(previewer_id: str) -> PreviewerSpec:
    from scistudio.previewers.models import OwnerKind

    return PreviewerSpec(
        previewer_id=previewer_id,
        owner_kind=OwnerKind.CORE,
        owner_name="scistudio",
        target_type="DataObject",
    )


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


__all__ = ["PreviewSessionManager"]
