"""Data catalog + preview method implementations.

Issue #1430 / umbrella #1427: behavior unchanged.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pyarrow.parquet as pq

from scistudio.core.storage.ref import StorageReference
from scistudio.core.types.array import Array
from scistudio.core.types.artifact import Artifact
from scistudio.core.types.composite import CompositeData
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.series import Series
from scistudio.core.types.text import Text

from ._preview_cache import MAX_TABLE_PAGE_SIZE, _get_preview_table
from ._preview_image import (
    _downsample_matrix,
    _image_data_uri_from_matrix,
    _infer_type_name_from_ref,
    _load_preview_matrix,
)

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
    ref = record.ref
    path = Path(ref.path)
    suffix = path.suffix.lower()

    resolved_cls = self._resolve_record_class(record)

    # ------------------------------------------------------------------
    # DataFrame / tabular
    # ------------------------------------------------------------------
    is_dataframe = record.type_name == DataFrame.__name__ or (
        resolved_cls is not None and issubclass(resolved_cls, DataFrame)
    )
    if is_dataframe or suffix in {".csv", ".parquet"}:
        effective_page_size = max(1, min(int(page_size), MAX_TABLE_PAGE_SIZE))

        base = _get_preview_table(path, sort_by=None, sort_dir="asc")
        columns = list(base.column_names)
        total_rows = base.num_rows

        effective_sort_dir = sort_dir if sort_dir in {"asc", "desc"} else "asc"
        effective_sort_by: str | None = None
        if sort_by and sort_by in columns:
            try:
                table = _get_preview_table(path, sort_by=sort_by, sort_dir=effective_sort_dir)
                effective_sort_by = sort_by
            except Exception:
                logger.debug("Sort failed on column %s; returning unsorted", sort_by, exc_info=True)
                table = base
        else:
            table = base

        total_pages = max(1, (total_rows + effective_page_size - 1) // effective_page_size)
        effective_page = max(1, min(int(page), total_pages))
        offset = (effective_page - 1) * effective_page_size
        page_table = table.slice(offset, effective_page_size)
        rows = page_table.to_pylist()
        return {
            "kind": "table",
            "columns": columns,
            "rows": rows,
            "total_rows": total_rows,
            "row_count": total_rows,  # backward-compat alias
            "page": effective_page,
            "page_size": effective_page_size,
            "total_pages": total_pages,
            "sort_by": effective_sort_by,
            "sort_dir": effective_sort_dir if effective_sort_by else None,
        }

    # ------------------------------------------------------------------
    # Text / artifact (text-based formats only)
    # ------------------------------------------------------------------
    is_text = record.type_name in {Text.__name__, Artifact.__name__} or (
        resolved_cls is not None and (issubclass(resolved_cls, Text) or issubclass(resolved_cls, Artifact))
    )
    if is_text and suffix in {
        ".txt",
        ".json",
        ".yaml",
        ".yml",
        ".md",
    }:
        text = path.read_text(encoding="utf-8", errors="replace")
        return {
            "kind": "text",
            "content": text[:5000],
            "language": suffix.lstrip(".") or "text",
        }

    # ------------------------------------------------------------------
    # Array / image (raster data)
    # ------------------------------------------------------------------
    is_array = record.type_name == Array.__name__ or (resolved_cls is not None and issubclass(resolved_cls, Array))
    if is_array or suffix in {".tif", ".tiff", ".zarr"}:
        try:
            matrix = _load_preview_matrix(ref)
            full_shape = list(matrix.shape)
            axes_raw = ref.metadata.get("axes") if ref.metadata else None
            axes: list[str] = [str(a) for a in axes_raw] if isinstance(axes_raw, list) else []
            ndim = matrix.ndim
            if axes and "y" in axes and "x" in axes:
                y_idx = axes.index("y")
                x_idx = axes.index("x")
            else:
                y_idx = max(0, ndim - 2)
                x_idx = max(0, ndim - 1)
            extra_dims = [i for i in range(ndim) if i not in (y_idx, x_idx)]
            slice_axis_idx: int | None = extra_dims[0] if extra_dims else None
            slice_axis_size: int | None = full_shape[slice_axis_idx] if slice_axis_idx is not None else None
            slice_axis_name: str | None
            if slice_axis_idx is None:
                slice_axis_name = None
            elif axes and slice_axis_idx < len(axes):
                slice_axis_name = axes[slice_axis_idx]
            else:
                slice_axis_name = f"axis {slice_axis_idx}"
            clamped_slice: int | None
            if slice_axis_size is not None and slice_axis_size > 0:
                clamped_slice = max(0, min(int(slice_index), slice_axis_size - 1))
            else:
                clamped_slice = None
            slab = matrix
            if slice_axis_idx is not None and clamped_slice is not None:
                sel: list[Any] = [slice(None)] * slab.ndim
                sel[slice_axis_idx] = clamped_slice
                slab = slab[tuple(sel)]
            while getattr(slab, "ndim", 0) > 2:
                slab = slab[0]
            if axes and "y" in axes and "x" in axes and axes.index("y") > axes.index("x"):
                slab = slab.T
            thumbnail = _downsample_matrix(slab)
            return {
                "kind": "image",
                "shape": full_shape,
                "axes": axes,
                "slice_axis_name": slice_axis_name,
                "slice_axis_size": slice_axis_size,
                "slice_index": clamped_slice,
                "thumbnail": thumbnail,
                "src": _image_data_uri_from_matrix(thumbnail),
            }
        except Exception:
            logger.debug("Failed to read raster preview for %s", ref.path, exc_info=True)
        return {
            "kind": "artifact",
            "path": ref.path,
            "mime_type": "image/tiff" if suffix in {".tif", ".tiff"} else "application/zarr",
        }

    # ------------------------------------------------------------------
    # Series / spectral (chart preview)
    # ------------------------------------------------------------------
    is_series = record.type_name == Series.__name__ or (resolved_cls is not None and issubclass(resolved_cls, Series))
    if is_series:
        values = record.metadata.get("values", [])
        return {
            "kind": "chart",
            "points": [{"x": index, "y": value} for index, value in enumerate(values[:256])],
        }

    # ------------------------------------------------------------------
    # CompositeData
    # ------------------------------------------------------------------
    is_composite = record.type_name == CompositeData.__name__ or (
        resolved_cls is not None and issubclass(resolved_cls, CompositeData)
    )
    if is_composite:
        composite_path = Path(ref.path)
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
        return {
            "kind": "composite",
            "slots": record.metadata.get("slots", {}),
        }

    return {
        "kind": "artifact",
        "path": ref.path,
        "mime_type": path.suffix.lower().lstrip(".") or "application/octet-stream",
    }
