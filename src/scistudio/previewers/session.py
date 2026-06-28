"""PreviewSessionManager — create/read/patch sessions + provider invocation.

Ties the registry, router, and bounded data access together (ADR-048 FR-007):

* :meth:`create_session` routes a :class:`PreviewTarget` to a spec, builds an
  in-memory :class:`PreviewSession`, and renders the first envelope.
* :meth:`read_session` re-renders the current envelope for a session.
* :meth:`patch_session` merges new query state (slice/page/sort/slot/item) and
  re-renders.
* :meth:`read_resource` performs a bounded follow-up resource read for a
  session (e.g. an array tile or a child preview).
* :meth:`render_target` renders a one-shot envelope WITHOUT a session for
  routed child-resource previews and direct provider tests.

Provider calls are wrapped defensively: a routing/typed error becomes an error
envelope; an unexpected provider exception becomes a
:class:`PreviewErrorCode.PROVIDER_EXCEPTION` envelope rather than crashing the
API (FR-028/FR-029). Sessions never mutate workflow/data/lineage state.
"""

from __future__ import annotations

import base64
import json
import logging
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar, cast
from urllib.parse import unquote_to_bytes
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
    PreviewResourceProvider,
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
_PLOT_EXPORT_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".pdf": "application/pdf",
}
ChildContextResolver = Callable[[PreviewTarget, dict[str, Any]], tuple[PreviewTarget, dict[str, Any]]]
ProviderT = TypeVar("ProviderT", bound=Callable[..., Any])


class PreviewSessionManager:
    """In-memory, thread-safe preview session store + provider dispatcher."""

    def __init__(
        self,
        registry: PreviewerRegistry,
        *,
        max_sessions: int = _DEFAULT_MAX_SESSIONS,
        data_access_factory: Callable[[PreviewLimits], PreviewDataAccess] | None = None,
        child_context_resolver: ChildContextResolver | None = None,
    ) -> None:
        self._registry = registry
        self._router = PreviewRouter(registry)
        self._sessions: OrderedDict[str, PreviewSession] = OrderedDict()
        self._lock = threading.RLock()
        self._max_sessions = max(1, int(max_sessions))
        self._data_access_factory = data_access_factory or self._default_data_access
        self._child_context_resolver = child_context_resolver

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

        session_id = f"pv-{uuid4().hex}"
        session = PreviewSession(
            session_id=session_id,
            previewer_id=spec.previewer_id,
            target=target,
            created_at=_now_iso(),
            query=query,
            cache_key=self._cache_key(spec, target, query, session_id=session_id),
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
                session_id=session_id,
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
        merged.update(_public_resource_params(params or {}))
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
            child_query = merged
            if self._child_context_resolver is not None:
                child_target, child_query = self._child_context_resolver(child_target, child_query)
            return self.create_session(child_target, child_query).to_dict()

        if resource_id == "export":
            return self._export_plot_resource(session, merged)

        spec = self._require_spec(session.previewer_id)
        resource_provider = self._resolve_resource_provider(spec)
        if resource_provider is not None:
            request = PreviewRequest(
                target=session.target,
                spec=spec,
                query=merged,
                data_access=access,
                limits=session.limits,
                session_id=session.session_id,
                storage=_storage_ref_from_query(merged, session.target.ref),
                record_metadata=_record_metadata_from_query(merged),
            )
            try:
                return resource_provider(request, resource_id, _public_resource_params(params or {}))
            except ProviderError:
                raise
            except Exception as exc:
                logger.debug("preview resource provider failed for %s", resource_id, exc_info=True)
                raise ProviderError(
                    f"resource provider for {session.previewer_id!r} failed: {exc}",
                    detail={"resource_id": resource_id, "previewer_id": session.previewer_id},
                ) from exc

        raise ProviderError(
            f"unknown resource id {resource_id!r} for session {session_id}",
            detail={"resource_id": resource_id},
        )

    def save_resource(
        self,
        session_id: str,
        resource_id: str,
        destination_path: Path,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Save a bounded resource payload to a user-selected destination."""
        data = self.read_resource(session_id, resource_id, params)
        payload, mime_type = _payload_from_data_uri(data)
        if len(payload) > self._get_session(session_id).limits.max_bytes:
            raise ProviderError(
                "preview resource exceeds save byte budget",
                detail={"resource_id": resource_id, "size_bytes": len(payload)},
            )
        if not destination_path.parent.is_dir():
            raise ProviderError(
                "save destination parent directory does not exist",
                detail={"resource_id": resource_id, "path": str(destination_path)},
            )
        destination_path.write_bytes(payload)
        return {
            "path": str(destination_path),
            "filename": destination_path.name,
            "size_bytes": len(payload),
            "mime_type": str(data.get("mime_type") or mime_type or ""),
        }

    def get_session(self, session_id: str) -> PreviewSession:
        """Return the session record (no re-render)."""
        return self._get_session(session_id)

    # -- one-shot rendering -------------------------------------------------

    def render_target(self, target: PreviewTarget, query: dict[str, Any] | None = None) -> PreviewEnvelope:
        """Render a one-shot envelope without creating a session."""
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
            storage=_storage_ref_from_query(query, target.ref),
            record_metadata=_record_metadata_from_query(query),
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
        # Stamp the resolved spec's frontend manifest onto the envelope so the
        # frontend host reads it first-class (#1579). Precedence: a
        # provider-set manifest wins; providers that set none inherit the spec
        # default. Core fallbacks have no spec manifest, so this is a no-op.
        if envelope.frontend_manifest is None and spec.frontend_manifest is not None:
            envelope = replace(envelope, frontend_manifest=spec.frontend_manifest)
        return envelope.with_session(session_id)

    def _resolve_provider(self, spec: PreviewerSpec) -> PreviewProvider | None:
        return _provider_from_decl(spec.backend_provider)

    def _resolve_resource_provider(self, spec: PreviewerSpec) -> PreviewResourceProvider | None:
        return _provider_from_decl(spec.resource_provider)

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
    def _cache_key(
        spec: PreviewerSpec,
        target: PreviewTarget,
        query: dict[str, Any],
        *,
        session_id: str | None = None,
    ) -> str:
        relevant = {k: v for k, v in query.items() if not k.startswith("_") and v is not None}
        version = ""
        storage = query.get("_storage")
        if isinstance(storage, dict):
            md = storage.get("metadata")
            if isinstance(md, dict):
                version = str(md.get("data_version", ""))
        parts = [
            f"previewer={spec.previewer_id}",
            f"kind={target.kind.value}",
            f"ref={target.ref}",
        ]
        if session_id:
            parts.append(f"session={session_id}")
        if version:
            parts.append(f"version={version}")
        parts.extend(f"{k}={_stable_cache_value(relevant[k])}" for k in sorted(relevant))
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
            # #1837: prefer the minimal flat params emitted by
            # ``_collection_item_params`` (``ref`` + ``type_name``). Fall back
            # to the legacy full ``item`` descriptor for any resource params
            # captured before that change.
            ref = str(params.get("ref") or "")
            type_name = str(params.get("type_name") or "")
            if not ref:
                item = params.get("item")
                if isinstance(item, dict):
                    ref = str(item.get("data_ref") or item.get("ref") or "")
                    type_name = type_name or str(item.get("type_name") or "")
            if not ref:
                return None
            type_name = type_name or str(parent.collection_item_type or "")
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

    def _export_plot_resource(self, session: PreviewSession, params: dict[str, Any]) -> dict[str, Any]:
        from scistudio.previewers.helpers import sanitize_svg
        from scistudio.previewers.models import TargetKind

        if session.target.kind is not TargetKind.PLOT_ARTIFACT and session.previewer_id != "core.plot.basic":
            raise ProviderError(
                f"resource 'export' is not available for previewer {session.previewer_id!r}",
                detail={"resource_id": "export", "previewer_id": session.previewer_id},
            )

        ref = _storage_ref_from_query(params, session.target.ref)
        path = Path(ref.path)
        suffix = path.suffix.lower()
        mime = _PLOT_EXPORT_MIME.get(suffix)
        if mime is None:
            raise ProviderError(
                f"unsupported plot export format: {suffix or '<none>'}",
                detail={"resource_id": "export", "format": suffix.lstrip(".")},
            )
        if not path.is_file():
            raise ProviderError(
                f"plot export source is unavailable: {path.name or session.target.ref}",
                detail={"resource_id": "export"},
            )

        actual_format = suffix.lstrip(".")
        requested_format = str(params.get("format") or actual_format).lower().lstrip(".")
        accepted_formats = {actual_format}
        if actual_format in {"jpg", "jpeg"}:
            accepted_formats.update({"jpg", "jpeg"})
        if requested_format not in accepted_formats:
            raise ProviderError(
                f"plot export format {requested_format!r} does not match artifact format {actual_format!r}",
                detail={"resource_id": "export", "format": requested_format},
            )

        if suffix == ".svg":
            raw_text = path.read_text(encoding="utf-8", errors="replace")
            sanitized, removed = sanitize_svg(raw_text)
            payload = sanitized.encode("utf-8")
            if len(payload) > session.limits.max_bytes:
                raise ProviderError(
                    "plot export exceeds preview byte budget",
                    detail={"resource_id": "export", "size_bytes": len(payload), "max_bytes": session.limits.max_bytes},
                )
            return {
                "format": "svg",
                "mime_type": mime,
                "filename": path.name,
                "size_bytes": len(payload),
                "data_uri": _data_uri(mime, payload),
                "sanitized": removed,
            }

        size = path.stat().st_size
        if size > session.limits.max_bytes:
            raise ProviderError(
                "plot export exceeds preview byte budget",
                detail={"resource_id": "export", "size_bytes": size, "max_bytes": session.limits.max_bytes},
            )
        payload = path.read_bytes()
        return {
            "format": "jpeg" if actual_format == "jpg" else actual_format,
            "mime_type": mime,
            "filename": path.name,
            "size_bytes": len(payload),
            "data_uri": _data_uri(mime, payload),
        }


def _provider_from_decl(provider: ProviderT | str | None) -> ProviderT | None:
    if provider is None:
        return None
    if callable(provider):
        return provider
    if isinstance(provider, str):
        return cast(ProviderT | None, _import_callable(provider))
    return None


def _import_callable(dotted: str) -> Callable[..., Any] | None:
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


def _record_metadata_from_query(query: dict[str, Any]) -> dict[str, Any]:
    """Extract the recorded data-record metadata carried on the query (ADR-052 §8.5)."""
    md = query.get("_record_metadata")
    return dict(md) if isinstance(md, dict) else {}


def _public_resource_params(params: dict[str, Any]) -> dict[str, Any]:
    """Return resource params without private session-enrichment keys."""
    return {str(key): value for key, value in params.items() if not str(key).startswith("_")}


def _stable_cache_value(value: Any) -> str:
    if isinstance(value, dict):
        parts = [
            f"{json.dumps(str(key), separators=(',', ':'))}:{_stable_cache_value(value[key])}"
            for key in sorted(value, key=lambda item: str(item))
            if value[key] is not None
        ]
        return "{" + ",".join(parts) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_stable_cache_value(item) for item in value) + "]"
    return json.dumps(value, separators=(",", ":"), default=str)


def _data_uri(mime_type: str, payload: bytes) -> str:
    return f"data:{mime_type};base64,{base64.b64encode(payload).decode('ascii')}"


def _payload_from_data_uri(data: dict[str, Any]) -> tuple[bytes, str | None]:
    data_uri = data.get("data_uri") or data.get("src")
    if not isinstance(data_uri, str) or not data_uri.startswith("data:"):
        raise ProviderError("preview resource is not a saveable data URI", detail={"resource": data})
    header, sep, payload = data_uri.partition(",")
    if sep == "":
        raise ProviderError("preview resource data URI is malformed", detail={"header": header})
    mime_type = header[5:].split(";", 1)[0] or None
    if ";base64" in header.lower():
        try:
            return base64.b64decode(payload.encode("ascii"), validate=True), mime_type
        except Exception as exc:
            raise ProviderError("preview resource data URI payload is invalid", detail={"header": header}) from exc
    return unquote_to_bytes(payload), mime_type


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
