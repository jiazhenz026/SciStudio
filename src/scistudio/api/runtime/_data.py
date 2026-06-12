"""Data catalog + preview method implementations.

ADR-048 SPEC 1: ``preview_data`` now routes through the
:mod:`scistudio.previewers` subsystem (registry -> router -> selected provider
-> :class:`PreviewEnvelope`) and adapts the canonical envelope back to the
LEGACY REST ``preview`` dict shapes so existing callers and tests keep working
(FR-007/FR-008). The legacy payload shapes (table/text/image/chart/composite/
artifact) are produced verbatim by :func:`_envelope_to_legacy_preview`.

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
    EnvelopeKind,
    PreviewEnvelope,
    PreviewService,
    PreviewSource,
    PreviewTarget,
    TargetKind,
    build_preview_service,
)
from scistudio.previewers._raster import (
    _downsample_matrix,
    _image_data_uri_from_matrix,
    _load_preview_matrix,
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


def _preview_query_for_record(
    record: DataRecord,
    *,
    slice_index: int,
    page: int,
    page_size: int,
    sort_by: str | None,
    sort_dir: str,
) -> dict[str, Any]:
    """Build the provider query, injecting the resolved storage ref + metadata.

    Providers read only through ``PreviewDataAccess`` and never touch the
    catalog, so the runtime hands them the resolved ``StorageReference`` data
    under the ``_storage`` / ``_record_metadata`` private query keys.
    """
    ref = record.ref
    return {
        "slice_index": slice_index,
        "page": page,
        "page_size": page_size,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "_storage": {
            "backend": ref.backend,
            "path": ref.path,
            "format": ref.format,
            "metadata": ref.metadata,
        },
        "_record_metadata": dict(record.metadata) if isinstance(record.metadata, dict) else {},
    }


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


def preview_data(
    self: ApiRuntime,
    data_ref: str,
    slice_index: int = 0,
    page: int = 1,
    page_size: int = 50,
    sort_by: str | None = None,
    sort_dir: str = "asc",
) -> dict[str, Any]:
    """Return a lightweight preview for a stored data object.

    ADR-048 SPEC 1: routes through the previewer subsystem (router -> selected
    provider -> :class:`PreviewEnvelope`) and adapts the envelope back to the
    LEGACY REST ``preview`` dict shape via :func:`_envelope_to_legacy_preview`
    so existing frontend callers and tests keep working during migration.

    Parameters
    ----------
    data_ref:
        Catalog identifier returned by ``register_data_ref``.
    slice_index:
        Index into the slider axis (3D viewer, #899). Clamped to
        ``[0, slice_axis_size - 1]``. Ignored for 2D arrays / non-image
        previews.
    page, page_size, sort_by, sort_dir:
        DataFrame paging + sort. Page is 1-based and clamped server-side;
        ``page_size`` is capped at ``MAX_TABLE_PAGE_SIZE``. ``sort_by`` is
        ignored when the column is missing. Non-table previews ignore
        these.
    """
    record = self.get_data_record(data_ref)
    resolved_cls = self._resolve_record_class(record)

    target = self._build_preview_target(record, resolved_cls)
    query = _preview_query_for_record(
        record,
        slice_index=slice_index,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    service = self.get_preview_service()
    envelope = service.sessions.render_target(target, query)
    return _envelope_to_legacy_preview(envelope, record, suffix=Path(record.ref.path).suffix.lower())


def _envelope_to_legacy_preview(
    envelope: PreviewEnvelope,
    record: DataRecord,
    *,
    suffix: str,
) -> dict[str, Any]:
    """Adapt a canonical :class:`PreviewEnvelope` to the legacy REST preview dict.

    The legacy ``preview.kind`` shapes are preserved EXACTLY (FR-008):
    ``table`` / ``text`` / ``image`` / ``chart`` / ``composite`` / ``artifact``.
    """
    payload = envelope.payload
    kind = envelope.kind

    if kind is EnvelopeKind.DATAFRAME:
        return {
            "kind": "table",
            "columns": payload.get("columns", []),
            "rows": payload.get("rows", []),
            "total_rows": payload.get("total_rows", 0),
            "row_count": payload.get("total_rows", 0),  # backward-compat alias
            "page": payload.get("page", 1),
            "page_size": payload.get("page_size", 50),
            "total_pages": payload.get("total_pages", 1),
            "sort_by": payload.get("sort_by"),
            "sort_dir": payload.get("sort_dir"),
        }

    if kind is EnvelopeKind.TEXT:
        return {
            "kind": "text",
            "content": payload.get("content", ""),
            "language": payload.get("language", "text"),
        }

    if kind is EnvelopeKind.ARRAY:
        return {
            "kind": "image",
            "shape": payload.get("shape", []),
            "axes": payload.get("axes", []),
            "slice_axis_name": payload.get("slice_axis_name"),
            "slice_axis_size": payload.get("slice_axis_size"),
            "slice_index": payload.get("slice_index"),
            "thumbnail": payload.get("thumbnail", []),
            "src": payload.get("src", ""),
        }

    if kind is EnvelopeKind.SERIES:
        return {"kind": "chart", "points": payload.get("points", [])}

    if kind is EnvelopeKind.COMPOSITE:
        # Legacy compat: a composite with a raster slot returns an image; the
        # envelope's composite payload otherwise lists slots.
        raster = _composite_raster_legacy(record)
        if raster is not None:
            return raster
        return {"kind": "composite", "slots": payload.get("slots", {})}

    if kind is EnvelopeKind.PLOT:
        # Plot artifacts surface through the compat route as artifacts with the
        # plot mime type so older frontend code can still download them.
        return {
            "kind": "artifact",
            "path": payload.get("path", record.ref.path),
            "mime_type": payload.get("mime_type", "application/octet-stream"),
        }

    # ARTIFACT, ERROR, COLLECTION, and any future kind degrade to the legacy
    # artifact shape so the one-shot route never crashes (FR-008 edge cases).
    mime = payload.get("mime_type") or (suffix.lstrip(".") or "application/octet-stream")
    return {
        "kind": "artifact",
        "path": payload.get("path", record.ref.path),
        "mime_type": mime,
    }


def _composite_raster_legacy(record: DataRecord) -> dict[str, Any] | None:
    """Legacy composite raster-slot rendering, preserved bit-for-bit.

    The compat REST contract returns a raster ``image`` payload when a
    composite has a ``raster`` slot directory on disk. This mirrors the
    pre-ADR-048 behavior exactly so ``tests/api/test_data`` stays green.
    """
    composite_path = Path(record.ref.path)
    for slot_name in ("raster",):
        slot_path = composite_path / slot_name
        if slot_path.exists():
            try:
                slot_ref = StorageReference(backend="zarr", path=str(slot_path))
                raster_matrix = _load_preview_matrix(slot_ref)
                while getattr(raster_matrix, "ndim", 0) > 2:
                    raster_matrix = raster_matrix[0]
                full_shape = list(raster_matrix.shape)
                thumbnail = _downsample_matrix(raster_matrix)
                return {
                    "kind": "image",
                    "shape": full_shape,
                    "thumbnail": thumbnail,
                    "src": _image_data_uri_from_matrix(thumbnail),
                }
            except Exception:
                logger.debug("Failed to read raster slot '%s' for composite preview", slot_name, exc_info=True)
    return None
