"""Preview sessions: bounded, guarded query state behind every preview envelope."""
# Maintainer context (kept outside generated API documentation):
# ADR-048 FR-007/FR-009 and ADR-054 §2. A preview session remembers what one
# preview shows (its routed candidate, target and query) so the host can page,
# slice, open a child and export without resending the target. Two renderers
# keep sessions: panels (this module's :class:`PreviewSessions`, whose envelope
# is a ``kind: panel`` handle the host mounts a panel context on) and the
# deprecated Python previewers (``scistudio.previewers.session``). Both share
# :class:`SessionStore`, which owns what does not depend on the renderer: the
# LRU bound, the backend-owned guard and authority of a panel-opened child,
# array tiles, plot export and composite/collection child routing. Child
# routing goes back through the caller's router, so a child of a legacy preview
# can open in a panel and the reverse.
# Development references: #1837, #1918, #2465, ADR-048, ADR-054.

from __future__ import annotations

import base64
import json
import logging
import threading
from collections import OrderedDict
from collections.abc import Callable, Iterable
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote_to_bytes
from uuid import uuid4

from scistudio.previewers._plot_formats import EXPORT_FORMAT_ORDER, canonical_format, sibling_for
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
    PreviewSession,
    PreviewTarget,
    ProviderError,
    TargetKind,
    UnknownPreviewerError,
)
from scistudio.stability import internal

logger = logging.getLogger(__name__)

#: Bound on the in-memory session store so a long GUI session does not leak.
DEFAULT_MAX_SESSIONS = 512

_PLOT_EXPORT_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
    ".pdf": "application/pdf",
}
_PLOT_EXPORT_FORMATS = frozenset(EXPORT_FORMAT_ORDER)

#: ``(target, query) -> (target, query)``: applies runtime catalog truth to a child.
ChildContextResolver = Callable[[PreviewTarget, dict[str, Any]], tuple[PreviewTarget, dict[str, Any]]]
#: ``(target, query) -> envelope``: opens a child session through the full router.
ChildSessionFactory = Callable[[PreviewTarget, dict[str, Any]], PreviewEnvelope]


@internal()
class SessionStore:
    """Thread-safe LRU of preview sessions plus the renderer-independent resources."""

    def __init__(
        self,
        *,
        max_sessions: int = DEFAULT_MAX_SESSIONS,
        data_access_factory: Callable[[PreviewLimits], PreviewDataAccess] | None = None,
        child_context_resolver: ChildContextResolver | None = None,
        child_session: ChildSessionFactory | None = None,
    ) -> None:
        self._sessions: OrderedDict[str, PreviewSession] = OrderedDict()
        self._session_guards: dict[str, Callable[[], None]] = {}
        self._session_authorities: dict[str, Any] = {}
        self._lock = threading.RLock()
        self._max_sessions = max(1, int(max_sessions))
        self._data_access_factory = data_access_factory or default_data_access
        self._child_context_resolver = child_context_resolver
        self._child_session = child_session

    # -- lifecycle ----------------------------------------------------------

    def owns(self, session_id: str) -> bool:
        """Whether *session_id* is held by this store (no guard is run)."""
        with self._lock:
            return session_id in self._sessions

    def set_child_session(self, factory: ChildSessionFactory | None) -> None:
        """Route composite/collection children through *factory*."""
        self._child_session = factory

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()
            self._session_guards.clear()
            self._session_authorities.clear()

    def discard(self, previewer_ids: Iterable[str]) -> list[str]:
        """Drop every session routed to one of *previewer_ids*; return their ids."""
        wanted = set(previewer_ids)
        with self._lock:
            gone = [sid for sid, session in self._sessions.items() if session.previewer_id in wanted]
            for session_id in gone:
                self._forget_locked(session_id)
        return gone

    def get_session(self, session_id: str) -> PreviewSession:
        """Return the session record (no re-render)."""
        return self._get_session(session_id)

    def frozen_session(self, session_id: str) -> PreviewSession:
        """Snapshot server-owned target/query state for a panel context."""
        with self._lock:
            return deepcopy(self._get_session(session_id))

    def session_authority(self, session_id: str) -> Any:
        """Return validated internal authority for an independently opened child."""
        with self._lock:
            self._get_session(session_id)
            return self._session_authorities.get(session_id)

    def _store(
        self,
        spec: PreviewerSpec,
        target: PreviewTarget,
        query: dict[str, Any],
        *,
        guard: Callable[[], None] | None,
        authority: Any,
    ) -> PreviewSession:
        session_id = f"pv-{uuid4().hex}"
        session = PreviewSession(
            session_id=session_id,
            previewer_id=spec.previewer_id,
            target=target,
            created_at=datetime.now(UTC).isoformat(),
            query=query,
            cache_key=cache_key(spec.previewer_id, target, query, session_id=session_id),
            limits=PreviewLimits(),
        )
        with self._lock:
            self._sessions[session_id] = session
            if guard is not None:
                self._session_guards[session_id] = guard
                self._session_authorities[session_id] = authority
            while len(self._sessions) > self._max_sessions:
                oldest, _ = self._sessions.popitem(last=False)
                self._session_guards.pop(oldest, None)
                self._session_authorities.pop(oldest, None)
        return session

    def _merge_query(self, session_id: str, query_patch: dict[str, Any]) -> PreviewSession:
        with self._lock:
            session = self._get_session(session_id)
            if session_id in self._session_guards and any(key.startswith("_") for key in query_patch):
                raise ValueError("Private preview query fields are backend-owned")
            session.query.update(query_patch)
            session.cache_key = cache_key(session.previewer_id, session.target, session.query, session_id=session_id)
            self._sessions.move_to_end(session_id)
            return session

    def _forget_locked(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        self._session_guards.pop(session_id, None)
        self._session_authorities.pop(session_id, None)

    def _get_session(self, session_id: str) -> PreviewSession:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise UnknownPreviewerError(
                    f"Unknown preview session: {session_id}",
                    detail={"session_id": session_id},
                )
            guard = self._session_guards.get(session_id)
            if guard is not None:
                try:
                    guard()
                except Exception as exc:
                    self._forget_locked(session_id)
                    raise UnknownPreviewerError("Preview source is no longer available") from exc
            self._sessions.move_to_end(session_id)
            return session

    # -- resources ----------------------------------------------------------

    def read_resource(self, session_id: str, resource_id: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Perform a bounded follow-up resource read for a session.

        ``tile`` reads an array tile, ``slot:<name>`` / ``item:<idx>`` open a
        child preview through the router, ``export`` returns a rendered plot
        format. Anything else is the renderer's own resource.
        """
        session = self._get_session(session_id)
        merged: dict[str, Any] = dict(session.query)
        merged.update(public_resource_params(params or {}))
        access = self._data_access_factory(session.limits)
        if resource_id == "tile":
            ref = storage_ref_from_query(merged, session.target.ref)
            tile = access.array_tile(
                ref,
                slice_index=int(merged.get("slice_index", 0) or 0),
                y0=int(merged.get("y0", 0) or 0),
                x0=int(merged.get("x0", 0) or 0),
                height=merged.get("height"),
                width=merged.get("width"),
            )
            return {"y0": tile.y0, "x0": tile.x0, "height": tile.height, "width": tile.width, "matrix": tile.matrix}
        if resource_id.startswith(("slot:", "item:")):
            child_target = child_target_from_resource(session.target, resource_id, merged)
            if child_target is None:
                raise ProviderError(
                    f"resource {resource_id!r} could not resolve a child target",
                    detail={"resource_id": resource_id},
                )
            child_query = merged
            if self._child_context_resolver is not None:
                child_target, child_query = self._child_context_resolver(child_target, child_query)
            return self._open_child(child_target, child_query).to_dict()
        if resource_id == "export":
            return export_plot_resource(session, merged)
        return self._renderer_resource(session, resource_id, merged, access, params or {})

    def save_resource(
        self,
        session_id: str,
        resource_id: str,
        destination_path: Path,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Save a bounded resource payload to a user-selected destination."""
        data = self.read_resource(session_id, resource_id, params)
        payload, mime_type = payload_from_data_uri(data)
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

    def _open_child(self, target: PreviewTarget, query: dict[str, Any]) -> PreviewEnvelope:
        if self._child_session is None:
            raise ProviderError("child previews are not routable here", detail={"ref": target.ref})
        return self._child_session(target, query)

    def _renderer_resource(
        self,
        session: PreviewSession,
        resource_id: str,
        merged: dict[str, Any],
        access: PreviewDataAccess,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        raise ProviderError(
            f"unknown resource id {resource_id!r} for session {session.session_id}",
            detail={"resource_id": resource_id},
        )


@internal()
class PreviewSessions(SessionStore):
    """Sessions routed to a panel; the envelope is the handle a panel context mounts on."""

    def create_session(
        self,
        spec: PreviewerSpec,
        target: PreviewTarget,
        query: dict[str, Any] | None = None,
        *,
        guard: Callable[[], None] | None = None,
        authority: Any = None,
    ) -> PreviewEnvelope:
        """Record a session for a panel candidate and return its envelope."""
        session = self._store(spec, target, dict(query or {}), guard=guard, authority=authority)
        return panel_envelope(spec.previewer_id, spec.api_version, session.target, session.session_id)

    def read_session(self, session_id: str, api_version: Callable[[str], str | None]) -> PreviewEnvelope:
        """Return the envelope for *session_id*; *api_version* looks up its panel."""
        session = self._get_session(session_id)
        return self._envelope(session, api_version)

    def patch_session(
        self, session_id: str, query_patch: dict[str, Any], api_version: Callable[[str], str | None]
    ) -> PreviewEnvelope:
        """Merge *query_patch* into the session query and return its envelope."""
        return self._envelope(self._merge_query(session_id, query_patch), api_version)

    @staticmethod
    def _envelope(session: PreviewSession, api_version: Callable[[str], str | None]) -> PreviewEnvelope:
        version = api_version(session.previewer_id)
        if version is None:
            raise UnknownPreviewerError(
                f"Unknown previewer: {session.previewer_id}",
                detail={"previewer_id": session.previewer_id},
            )
        return panel_envelope(session.previewer_id, version, session.target, session.session_id)


def panel_envelope(panel_id: str, api_version: str, target: PreviewTarget, session_id: str | None) -> PreviewEnvelope:
    """The ``kind: panel`` envelope: which panel to mount, never any data."""
    return PreviewEnvelope(
        previewer_id=panel_id,
        target=target,
        kind=EnvelopeKind.PANEL,
        panel={"id": panel_id, "api_version": api_version},
        session_id=session_id,
    )


def error_envelope(
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


def routing_error_envelope(target: PreviewTarget, exc: PreviewError) -> PreviewEnvelope:
    return error_envelope(target, exc.code, exc.message, previewer_id="", detail=exc.detail)


def default_data_access(limits: PreviewLimits) -> PreviewDataAccess:
    return PreviewDataAccess(
        max_rows=limits.max_rows,
        max_bytes=limits.max_bytes,
        max_items=limits.max_items,
        max_tile=limits.max_tile,
        max_dim=limits.max_dim,
    )


def cache_key(previewer_id: str, target: PreviewTarget, query: dict[str, Any], *, session_id: str | None = None) -> str:
    relevant = {k: v for k, v in query.items() if not k.startswith("_") and v is not None}
    version = ""
    storage = query.get("_storage")
    if isinstance(storage, dict):
        md = storage.get("metadata")
        if isinstance(md, dict):
            version = str(md.get("data_version", ""))
    parts = [f"previewer={previewer_id}", f"kind={target.kind.value}", f"ref={target.ref}"]
    if session_id:
        parts.append(f"session={session_id}")
    if version:
        parts.append(f"version={version}")
    parts.extend(f"{k}={_stable_cache_value(relevant[k])}" for k in sorted(relevant))
    return "|".join(parts)


def child_target_from_resource(parent: PreviewTarget, resource_id: str, params: dict[str, Any]) -> PreviewTarget | None:
    if resource_id.startswith("item:"):
        # #1837: prefer the minimal flat params (``ref`` + ``type_name``); fall
        # back to a full ``item`` descriptor captured before that change.
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
        return PreviewTarget(
            kind=TargetKind.DATA_REF,
            ref=f"{parent.ref}#{params.get('slot', '')}",
            recorded_type=slot_type,
            type_chain=(slot_type,) if slot_type else (),
            source=parent.source,
        )
    return None


def sibling_for_format(primary: Path, fmt: str) -> Path:
    """The sibling artifact file for *fmt* next to *primary* (#1918)."""
    found = sibling_for(primary, fmt)
    return found if found is not None else primary.parent / f"{primary.stem}.{canonical_format(fmt)}"


def export_plot_resource(session: PreviewSession, params: dict[str, Any]) -> dict[str, Any]:
    from scistudio.previewers.helpers import sanitize_svg

    if session.target.kind is not TargetKind.PLOT_ARTIFACT and session.previewer_id != "core.plot.basic":
        raise ProviderError(
            f"resource 'export' is not available for previewer {session.previewer_id!r}",
            detail={"resource_id": "export", "previewer_id": session.previewer_id},
        )
    ref = storage_ref_from_query(params, session.target.ref)
    primary = Path(ref.path)
    primary_suffix = primary.suffix.lower()
    if _PLOT_EXPORT_MIME.get(primary_suffix) is None:
        raise ProviderError(
            f"unsupported plot export format: {primary_suffix or '<none>'}",
            detail={"resource_id": "export", "format": primary_suffix.lstrip(".")},
        )
    # #1918: the plot run renders one sibling per allowed format next to the
    # primary; return the one the user chose, or refuse cleanly.
    primary_format = canonical_format(primary_suffix)
    requested_format = str(params.get("format") or primary_format).lower().lstrip(".")
    requested_format = canonical_format("." + requested_format)
    if requested_format not in _PLOT_EXPORT_FORMATS:
        raise ProviderError(
            f"unsupported plot export format: {requested_format or '<none>'}",
            detail={"resource_id": "export", "format": requested_format},
        )
    path = sibling_for_format(primary, requested_format)
    if not path.is_file():
        available = sorted(
            canonical_format(p.suffix)
            for p in primary.parent.glob(f"{primary.stem}.*")
            if canonical_format(p.suffix) in _PLOT_EXPORT_FORMATS
        )
        raise ProviderError(
            f"plot format {requested_format!r} was not rendered for this plot; "
            f"available formats: {', '.join(available) or '<none>'}",
            detail={"resource_id": "export", "format": requested_format, "available_formats": available},
        )
    mime = _PLOT_EXPORT_MIME[path.suffix.lower()]
    if path.suffix.lower() == ".svg":
        sanitized, removed = sanitize_svg(path.read_text(encoding="utf-8", errors="replace"))
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
            "data_uri": data_uri(mime, payload),
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
        "format": requested_format,
        "mime_type": mime,
        "filename": path.name,
        "size_bytes": len(payload),
        "data_uri": data_uri(mime, payload),
    }


def storage_ref_from_query(query: dict[str, Any], fallback_ref: str) -> Any:
    from scistudio.core.storage.ref import StorageReference

    storage = query.get("_storage") or {}
    return StorageReference(
        backend=str(storage.get("backend", "filesystem")),
        path=str(storage.get("path", fallback_ref)),
        format=storage.get("format"),
        metadata=storage.get("metadata"),
    )


def record_metadata_from_query(query: dict[str, Any]) -> dict[str, Any]:
    """Extract the recorded data-record metadata carried on the query."""
    md = query.get("_record_metadata")
    return dict(md) if isinstance(md, dict) else {}


def public_resource_params(params: dict[str, Any]) -> dict[str, Any]:
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


def data_uri(mime_type: str, payload: bytes) -> str:
    return f"data:{mime_type};base64,{base64.b64encode(payload).decode('ascii')}"


def payload_from_data_uri(data: dict[str, Any]) -> tuple[bytes, str | None]:
    raw = data.get("data_uri") or data.get("src")
    if not isinstance(raw, str) or not raw.startswith("data:"):
        raise ProviderError("preview resource is not a saveable data URI", detail={"resource": data})
    header, sep, payload = raw.partition(",")
    if sep == "":
        raise ProviderError("preview resource data URI is malformed", detail={"header": header})
    mime_type = header[5:].split(";", 1)[0] or None
    if ";base64" in header.lower():
        try:
            return base64.b64decode(payload.encode("ascii"), validate=True), mime_type
        except Exception as exc:
            raise ProviderError("preview resource data URI payload is invalid", detail={"header": header}) from exc
    return unquote_to_bytes(payload), mime_type


__all__ = ["DEFAULT_MAX_SESSIONS", "PreviewSessions", "SessionStore"]
