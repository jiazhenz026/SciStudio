"""Data catalog + routed-preview helper implementations.

ADR-048 SPEC 1 (no-compat, #1594/#1604): the catalog is previewed exclusively
through the routed previewer session API (``POST/GET/PATCH
/api/previews/sessions`` -> registry -> router -> selected provider ->
:class:`PreviewEnvelope`). The legacy one-shot ``GET /api/data/{ref}/preview``
REST adapter (``preview_data`` + ``_envelope_to_legacy_preview``) was deleted
under #1604; callers now use the session API. The runtime contributes only the
catalog-resolution helpers the session manager needs: :func:`enrich_preview_query`
(injects the resolved storage ref + record metadata under the private
``_storage`` / ``_record_metadata`` query keys) and :func:`resolve_session_target`
(rebuilds the authoritative target kind + type chain from the catalog record).

The data-catalog helpers (``register_data_ref``, ``register_output_payload``,
``get_data_record``, ``describe_ref``, ``_resolve_record_class``) are unchanged
from the pre-split implementation (issue #1430 / umbrella #1427).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pyarrow.parquet as pq

from scistudio.core.storage.ref import StorageReference
from scistudio.previewers import (
    PreviewService,
    PreviewSource,
    PreviewTarget,
    TargetKind,
    build_preview_service,
)

from ._preview_image import _infer_type_name_from_ref

if TYPE_CHECKING:
    from . import ApiRuntime, DataRecord

logger = logging.getLogger(__name__)


def register_data_ref(
    self: ApiRuntime,
    ref: StorageReference,
    *,
    type_name: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> DataRecord:
    from . import DataRecord

    resolved_type_name = type_name or _infer_type_name_from_ref(ref)
    ref_type_chain: list[str] = []
    if ref.metadata:
        tc = ref.metadata.get("type_chain")
        if isinstance(tc, list):
            ref_type_chain = [str(n) for n in tc]
    record = DataRecord(
        id=f"data-{uuid4().hex}",
        ref=ref,
        type_name=resolved_type_name,
        metadata=metadata or self.describe_ref(ref),
        type_chain=ref_type_chain,
    )
    self.data_catalog[record.id] = record
    return record


def register_output_payload(self: ApiRuntime, payload: Any) -> Any:
    if isinstance(payload, dict) and {"backend", "path"}.issubset(payload.keys()):
        ref = StorageReference(
            backend=str(payload["backend"]),
            path=str(payload["path"]),
            format=payload.get("format"),
            metadata=payload.get("metadata"),
        )
        explicit_type_name: str | None = None
        raw_meta = payload.get("metadata") or {}
        tc = raw_meta.get("type_chain") if isinstance(raw_meta, dict) else None
        if tc and isinstance(tc, list) and tc:
            explicit_type_name = str(tc[-1])
        record = self.register_data_ref(ref, type_name=explicit_type_name, metadata=self.describe_ref(ref))
        return {
            "data_ref": record.id,
            "type_name": record.type_name,
            "metadata": record.metadata,
        }
    if isinstance(payload, dict) and payload.get("_collection") is True:
        items = [self.register_output_payload(item) for item in payload.get("items", [])]
        return {
            "kind": "collection",
            "count": len(items),
            "item_type": payload.get("item_type"),
            "items": items,
        }
    if isinstance(payload, dict):
        return {key: self.register_output_payload(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [self.register_output_payload(item) for item in payload]
    return payload


def get_data_record(self: ApiRuntime, data_ref: str) -> DataRecord:
    if data_ref not in self.data_catalog:
        raise KeyError(f"Unknown data reference: {data_ref}")
    return self.data_catalog[data_ref]


def describe_ref(self: ApiRuntime, ref: StorageReference) -> dict[str, Any]:
    path = Path(ref.path)
    metadata: dict[str, Any] = {
        "backend": ref.backend,
        "path": ref.path,
        "format": ref.format,
        "exists": path.exists(),
    }
    if path.exists():
        metadata["size_bytes"] = path.stat().st_size
    if ref.metadata:
        metadata.update(ref.metadata)
    if path.suffix.lower() == ".parquet" and path.exists():
        try:
            table = pq.read_table(path)
            metadata["columns"] = table.column_names
            metadata["row_count"] = table.num_rows
        except Exception:
            logger.debug("Failed to read parquet metadata for %s", ref.path, exc_info=True)
    return metadata


def _resolve_record_class(self: ApiRuntime, record: DataRecord) -> type | None:
    """Resolve the DataObject class for *record* via TypeRegistry."""
    chain = record.type_chain or [record.type_name]
    try:
        return self.type_registry.resolve(chain)
    except Exception:
        return None


def get_preview_service(self: ApiRuntime) -> PreviewService:
    """Return (building on first use) this runtime's :class:`PreviewService`.

    ADR-048 SPEC 1: the runtime owns a per-process preview service loaded with
    core + package + project previewers. It is built lazily and rebuilt on
    project switch via :meth:`refresh_preview_service` so project-local
    previewers and defaults track the active project.
    """
    service = getattr(self, "_preview_service", None)
    if service is None:
        project_dir = Path(self.active_project.path) if self.active_project else None
        service = build_preview_service(project_dir=project_dir)
        self._preview_service = service  # type: ignore[attr-defined]
    return service


def refresh_preview_service(self: ApiRuntime) -> PreviewService:
    """Rebuild the runtime preview service for the active project (FR-002)."""
    project_dir = Path(self.active_project.path) if self.active_project else None
    service = build_preview_service(project_dir=project_dir)
    self._preview_service = service  # type: ignore[attr-defined]
    return service


def _target_kind_for_record(record: DataRecord, resolved_cls: type | None) -> TargetKind:
    """Classify a DataRecord into a previewer :class:`TargetKind`.

    Plot artifacts are detected by a ``plot_artifact`` metadata flag or a
    plot-style suffix; everything non-collection is a ``data_ref``.
    """
    suffix = Path(record.ref.path).suffix.lower()
    is_plot = bool(record.metadata.get("plot_artifact")) or (
        record.type_name == "PlotArtifact" and suffix in {".png", ".jpg", ".jpeg", ".svg", ".pdf"}
    )
    if is_plot:
        return TargetKind.PLOT_ARTIFACT
    return TargetKind.DATA_REF


def _build_preview_target(self: ApiRuntime, record: DataRecord, resolved_cls: type | None) -> PreviewTarget:
    """Build a normalized :class:`PreviewTarget` from a catalog record."""
    type_chain = tuple(record.type_chain) if record.type_chain else (record.type_name,)
    source = None
    src_meta = record.metadata.get("source") if isinstance(record.metadata, dict) else None
    if isinstance(src_meta, dict):
        source = PreviewSource(
            workflow_id=src_meta.get("workflow_id"),
            node_id=src_meta.get("node_id"),
            output_port=src_meta.get("output_port"),
        )
    return PreviewTarget(
        kind=_target_kind_for_record(record, resolved_cls),
        ref=record.id,
        recorded_type=record.type_name,
        type_chain=type_chain,
        source=source,
    )


def enrich_preview_query(self: ApiRuntime, ref: str, query: dict[str, Any]) -> dict[str, Any]:
    """Inject the resolved storage ref + record metadata into a session query.

    The routed session API receives a bare ``ref`` (catalog id). Providers read
    only through ``PreviewDataAccess`` and never touch the catalog, so the
    runtime resolves the ``StorageReference`` here and places it under the
    private ``_storage`` / ``_record_metadata`` query keys. Unknown refs (e.g. a
    collection-only target whose items carry their own storage) leave the query
    untouched so the provider can degrade to an error/collection envelope.
    """
    enriched = dict(query)
    try:
        record = self.get_data_record(ref)
    except KeyError:
        return enriched
    record_ref = record.ref
    enriched.setdefault(
        "_storage",
        {
            "backend": record_ref.backend,
            "path": record_ref.path,
            "format": record_ref.format,
            "metadata": record_ref.metadata,
        },
    )
    enriched.setdefault(
        "_record_metadata",
        dict(record.metadata) if isinstance(record.metadata, dict) else {},
    )
    return enriched


def resolve_session_target(self: ApiRuntime, target: PreviewTarget) -> PreviewTarget:
    """Rebuild a routed preview target from the catalog (ADR-048 / #1592).

    The routed session API (``POST /api/previews/sessions``) accepts a client
    target that may carry only ``{kind, ref}`` — the frontend ``PreviewHost``
    has no authoritative type chain. For a ref the runtime knows, the backend
    is the source of truth for the target's kind + type chain, so rebuild it
    from the catalog record (the same path :func:`preview_data` uses) to
    guarantee correct routing regardless of what the frontend supplied. Unknown
    refs (e.g. a collection-only target whose items carry their own storage) are
    returned unchanged so the provider can degrade.
    """
    try:
        record = self.get_data_record(target.ref)
    except KeyError:
        return target
    resolved_cls = self._resolve_record_class(record)
    return self._build_preview_target(record, resolved_cls)
