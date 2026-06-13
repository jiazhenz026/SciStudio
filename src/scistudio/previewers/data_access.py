"""Bounded data-access helpers for previewers (ADR-048 FR-009 / FR-010).

:class:`PreviewDataAccess` is the *only* surface a previewer provider may use
to read payload bytes. Every method enforces a row / byte / item / tile /
dimension budget so a preview of a multi-GB Zarr/TIFF/Parquet never
materializes the whole object (FR-010, SC-004).

The implementation reuses the proven streaming logic from two
previewer-owned helper modules (ADR-048 / #1598 — these were moved down out of
``scistudio.api.runtime`` so the previewer subsystem no longer imports up into
the API layer):

* table paging + LRU cache from ``scistudio.previewers._table_cache`` (the
  monkeypatchable ``_get_preview_table`` / ``_read_preview_table_from_disk``);
* raster slab loading + PNG data-URI encoding from
  ``scistudio.previewers._raster``.

Array access here is bounded directly against the storage handle: a Zarr
array is indexed with explicit slices (``arr[plane_index, y0:y1, x0:x1]``)
rather than ``arr[...]`` so only the requested plane/tile is read into RAM.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scistudio.core.storage.ref import StorageReference

# Default budgets. ``max_rows`` mirrors the legacy ``MAX_TABLE_PAGE_SIZE``
# (200); ``max_bytes`` mirrors the MCP 8 MiB cap (FR-027); ``max_dim`` /
# ``max_tile`` mirror the legacy 256-pixel thumbnail bound.
DEFAULT_MAX_ROWS = 200
DEFAULT_MAX_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_ITEMS = 100
DEFAULT_MAX_TILE = 256
DEFAULT_MAX_DIM = 256
DEFAULT_TEXT_CHARS = 5000
DEFAULT_SERIES_POINTS = 256


@dataclass(frozen=True)
class DataFramePage:
    """Bounded page of a tabular payload."""

    columns: list[str]
    rows: list[dict[str, Any]]
    total_rows: int
    page: int
    page_size: int
    total_pages: int
    sort_by: str | None
    sort_dir: str | None
    truncated: bool


@dataclass(frozen=True)
class SliceAxis:
    """One non-displayed (sliced) axis of an N-D array.

    Carries everything the frontend needs to render a per-axis index picker:
    the axis position, a display name, its full size, and the currently
    selected index along it.
    """

    axis: int
    name: str
    size: int
    index: int


@dataclass(frozen=True)
class ArrayPlane:
    """A bounded 2-D plane sliced out of an N-D array, plus axis metadata.

    ``matrix`` holds the actual (downsampled) numeric values of the displayed
    plane — the previewer renders these as a numeric heatmap table, not a
    lossy grayscale image. ``vmin`` / ``vmax`` are the finite min/max of the
    displayed plane so the frontend can build a value-scale legend and a
    diverging/sequential colormap that does NOT clip signed data.

    ``slice_axes`` lists every non-displayed axis with its current selected
    index so an N-D array is fully navigable (one index picker per extra
    axis), not just a single face. The legacy single ``slice_axis_*`` /
    ``slice_index`` fields are kept (they mirror the first entry of
    ``slice_axes``) for backward-compatible callers and the array-tile path.
    """

    shape: list[int]
    axes: list[str]
    dtype: str
    slice_axis_name: str | None
    slice_axis_size: int | None
    slice_index: int | None
    slice_axes: list[SliceAxis]
    # Non-finite cells (NaN / +-inf) are encoded as ``None`` (JSON ``null``) so
    # the envelope stays JSON-safe; the frontend renders them as empty /
    # transparent cells.
    matrix: list[list[float | None]]
    vmin: float | None
    vmax: float | None
    truncated: bool
    ndim: int


@dataclass(frozen=True)
class ArrayTile:
    """A bounded rectangular tile read out of a 2-D plane."""

    y0: int
    x0: int
    height: int
    width: int
    matrix: list[list[float]]


@dataclass(frozen=True)
class SeriesPoints:
    """A bounded (decimated) set of (x, y) chart points."""

    points: list[dict[str, float]]
    total: int
    truncated: bool


@dataclass(frozen=True)
class TextChunk:
    """A bounded chunk of text plus a truncation marker."""

    content: str
    truncated: bool
    total_bytes: int
    language: str


@dataclass(frozen=True)
class ArtifactInfo:
    """Bounded metadata about an opaque artifact (no full read)."""

    path: str
    mime_type: str
    size_bytes: int
    data_uri: str | None = None


@dataclass(frozen=True)
class CompositeSlots:
    """Slot inventory of a CompositeData target (no eager child render)."""

    slots: dict[str, str]


@dataclass(frozen=True)
class CollectionSample:
    """Bounded sample of a collection's items."""

    count: int
    item_type: str | None
    items: list[dict[str, Any]]
    sampled: bool


class PreviewDataAccess:
    """Narrow, budget-enforcing read surface for preview providers.

    The class never exposes raw storage paths to frontend code; providers
    receive typed bounded results and place only JSON-safe payloads into
    their envelopes.
    """

    def __init__(
        self,
        *,
        max_rows: int = DEFAULT_MAX_ROWS,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_items: int = DEFAULT_MAX_ITEMS,
        max_tile: int = DEFAULT_MAX_TILE,
        max_dim: int = DEFAULT_MAX_DIM,
        text_chars: int = DEFAULT_TEXT_CHARS,
        series_points: int = DEFAULT_SERIES_POINTS,
    ) -> None:
        self.max_rows = max(1, int(max_rows))
        self.max_bytes = max(1, int(max_bytes))
        self.max_items = max(1, int(max_items))
        self.max_tile = max(1, int(max_tile))
        self.max_dim = max(1, int(max_dim))
        self.text_chars = max(1, int(text_chars))
        self.max_series_points = max(1, int(series_points))

    # -- DataFrame ----------------------------------------------------------

    def dataframe_page(
        self,
        ref: StorageReference,
        *,
        page: int = 1,
        page_size: int = 50,
        sort_by: str | None = None,
        sort_dir: str = "asc",
    ) -> DataFramePage:
        """Return one bounded, optionally sorted page of a CSV/parquet table.

        Reuses the LRU-cached ``_get_preview_table`` from the API runtime so
        repeated pagination/sort is O(slice) and the monkeypatchable disk
        reader contract stays intact (``tests/api/test_runtime_import_surface``).
        ``page_size`` is capped at ``max_rows``.
        """
        from scistudio.previewers._table_cache import _get_preview_table

        path = Path(ref.path)
        effective_page_size = max(1, min(int(page_size), self.max_rows))

        base = _get_preview_table(path, sort_by=None, sort_dir="asc")
        columns = list(base.column_names)
        total_rows = int(base.num_rows)

        effective_sort_dir = sort_dir if sort_dir in {"asc", "desc"} else "asc"
        effective_sort_by: str | None = None
        if sort_by and sort_by in columns:
            try:
                table = _get_preview_table(path, sort_by=sort_by, sort_dir=effective_sort_dir)
                effective_sort_by = sort_by
            except Exception:
                table = base
        else:
            table = base

        total_pages = max(1, (total_rows + effective_page_size - 1) // effective_page_size)
        effective_page = max(1, min(int(page), total_pages))
        offset = (effective_page - 1) * effective_page_size
        page_table = table.slice(offset, effective_page_size)
        rows = page_table.to_pylist()
        return DataFramePage(
            columns=columns,
            rows=rows,
            total_rows=total_rows,
            page=effective_page,
            page_size=effective_page_size,
            total_pages=total_pages,
            sort_by=effective_sort_by,
            sort_dir=effective_sort_dir if effective_sort_by else None,
            truncated=total_rows > effective_page_size,
        )

    # -- Array --------------------------------------------------------------

    def array_plane(
        self,
        ref: StorageReference,
        *,
        slice_index: int = 0,
        axis_indices: dict[int, int] | None = None,
    ) -> ArrayPlane:
        """Return shape/axes metadata + one bounded, downsampled 2-D plane.

        The returned ``matrix`` is the actual numeric data of the displayed
        plane (downsampled to ``max_dim`` per side); ``vmin`` / ``vmax`` are
        its finite min/max so the previewer can render a numeric heatmap table
        with a value-scale legend that does not clip signed data.

        Every non-displayed axis is independently navigable: ``axis_indices``
        maps an axis position to the selected index along it (PyCharm-style
        per-axis pickers). ``slice_index`` is the legacy single-axis control
        and is applied to the first extra axis when ``axis_indices`` omits it.
        ``slice_axes`` echoes the clamped selection per extra axis.

        For Zarr the array handle is sliced with explicit indices so only the
        requested plane is read — never the full N-D payload (FR-010 / SC-004).
        For TIFF the first page is read via the existing helper (a single IFD,
        already bounded for typical previews).
        """
        import numpy as np

        handle, full_shape, dtype = self._open_array_handle(ref)
        axes = self._axes_from_ref(ref, full_shape)
        ndim = len(full_shape)

        if ndim <= 2:
            y_idx, x_idx = (0, 1) if ndim == 2 else (0, 0)
        elif axes and "y" in axes and "x" in axes:
            y_idx = axes.index("y")
            x_idx = axes.index("x")
        else:
            y_idx, x_idx = ndim - 2, ndim - 1

        extra_dims = [i for i in range(ndim) if i not in (y_idx, x_idx)]
        requested = dict(axis_indices or {})
        # The legacy single ``slice_index`` control drives the first extra axis
        # unless an explicit per-axis index was supplied for it.
        if extra_dims and extra_dims[0] not in requested:
            requested[extra_dims[0]] = int(slice_index)

        # Clamp every extra-axis index into range and build the per-axis
        # selector that drives the bounded read.
        selected: dict[int, int] = {}
        slice_axes: list[SliceAxis] = []
        for axis in extra_dims:
            size = int(full_shape[axis])
            raw = int(requested.get(axis, 0))
            idx = max(0, min(raw, size - 1)) if size > 0 else 0
            selected[axis] = idx
            name = axes[axis] if axes and axis < len(axes) else f"axis {axis}"
            slice_axes.append(SliceAxis(axis=axis, name=name, size=size, index=idx))

        # Legacy single-axis fields mirror the first extra axis.
        first = slice_axes[0] if slice_axes else None
        slice_axis_name = first.name if first is not None else None
        slice_axis_size = first.size if first is not None else None
        legacy_slice_index = first.index if first is not None else None

        plane = self._read_bounded_plane(
            handle,
            full_shape=full_shape,
            y_idx=y_idx,
            x_idx=x_idx,
            axis_indices=selected,
        )
        # Transpose if y appears after x so the rendered plane matches axes.
        if axes and "y" in axes and "x" in axes and axes.index("y") > axes.index("x"):
            plane = plane.T

        plane = np.asarray(plane)
        vmin, vmax = self._finite_extent(plane)
        matrix = self._downsample(plane)
        truncated = max(int(plane.shape[0]), int(plane.shape[1])) > self.max_dim if plane.ndim >= 2 else False
        return ArrayPlane(
            shape=[int(d) for d in full_shape],
            axes=axes,
            dtype=dtype,
            slice_axis_name=slice_axis_name,
            slice_axis_size=int(slice_axis_size) if slice_axis_size is not None else None,
            slice_index=legacy_slice_index,
            slice_axes=slice_axes,
            matrix=matrix,
            vmin=vmin,
            vmax=vmax,
            truncated=truncated,
            ndim=ndim,
        )

    def array_tile(
        self,
        ref: StorageReference,
        *,
        slice_index: int = 0,
        y0: int = 0,
        x0: int = 0,
        height: int | None = None,
        width: int | None = None,
    ) -> ArrayTile:
        """Read one bounded rectangular tile from a 2-D plane (FR-010).

        Tile dimensions are capped at ``max_tile``. The plane is selected by
        ``slice_index`` along the auto-detected slider axis, like
        :meth:`array_plane`.
        """
        import numpy as np

        handle, full_shape, _dtype = self._open_array_handle(ref)
        axes = self._axes_from_ref(ref, full_shape)
        ndim = len(full_shape)
        if ndim <= 2:
            y_idx, x_idx = (0, 1) if ndim == 2 else (0, 0)
        elif axes and "y" in axes and "x" in axes:
            y_idx, x_idx = axes.index("y"), axes.index("x")
        else:
            y_idx, x_idx = ndim - 2, ndim - 1
        extra_dims = [i for i in range(ndim) if i not in (y_idx, x_idx)]
        slice_axis_idx = extra_dims[0] if extra_dims else None
        tile_axis_indices = {slice_axis_idx: int(slice_index)} if slice_axis_idx is not None else {}

        plane = self._read_bounded_plane(
            handle,
            full_shape=full_shape,
            y_idx=y_idx,
            x_idx=x_idx,
            axis_indices=tile_axis_indices,
            no_downsample=True,
        )
        plane = np.asarray(plane)
        ph, pw = (int(plane.shape[0]), int(plane.shape[1])) if plane.ndim >= 2 else (int(plane.shape[0]), 1)
        eff_h = min(self.max_tile, ph - y0 if height is None else min(int(height), self.max_tile, ph - y0))
        eff_w = min(self.max_tile, pw - x0 if width is None else min(int(width), self.max_tile, pw - x0))
        eff_h = max(0, eff_h)
        eff_w = max(0, eff_w)
        tile = plane[y0 : y0 + eff_h, x0 : x0 + eff_w] if plane.ndim >= 2 else plane[y0 : y0 + eff_h]
        return ArrayTile(
            y0=int(y0),
            x0=int(x0),
            height=int(eff_h),
            width=int(eff_w),
            matrix=np.asarray(tile, dtype=float).tolist(),
        )

    # -- Series -------------------------------------------------------------

    def series_points(self, ref: StorageReference, metadata: dict[str, Any]) -> SeriesPoints:
        """Return decimated chart points for a Series (FR-015).

        Prefers ``metadata['values']`` (cheap in-memory preview written by the
        worker). Falls back to a bounded parquet read of the first column.
        Values are decimated to ``series_points`` so a million-point series
        never serializes in full.
        """
        values: list[Any] = []
        if isinstance(metadata, dict):
            raw = metadata.get("values")
            if isinstance(raw, list):
                values = raw

        if not values:
            path = Path(ref.path)
            if path.exists() and path.suffix.lower() == ".parquet":
                import pyarrow.parquet as pq

                pf = pq.ParquetFile(path)
                collected: list[Any] = []
                for batch in pf.iter_batches(batch_size=self.max_series_points, columns=[pf.schema_arrow.names[0]]):
                    collected.extend(batch.column(0).to_pylist())
                    if len(collected) >= self.max_series_points:
                        break
                values = collected

        total = len(values)
        if total > self.max_series_points:
            step = max(1, total // self.max_series_points)
            sampled = values[::step][: self.max_series_points]
            points = [{"x": float(i * step), "y": float(v)} for i, v in enumerate(sampled)]
            return SeriesPoints(points=points, total=total, truncated=True)
        points = [{"x": float(i), "y": float(v)} for i, v in enumerate(values)]
        return SeriesPoints(points=points, total=total, truncated=False)

    # -- Text ---------------------------------------------------------------

    def text_chunk(self, ref: StorageReference) -> TextChunk:
        """Return a bounded text chunk + truncation marker (FR-016).

        Reads at most ``text_chars`` *bytes* (decoded leniently) so a huge log
        file never loads in full.
        """
        path = Path(ref.path)
        suffix = path.suffix.lower()
        total_bytes = path.stat().st_size if path.exists() else 0
        with path.open("rb") as fh:
            raw = fh.read(self.text_chars)
        content = raw.decode("utf-8", errors="replace")
        return TextChunk(
            content=content,
            truncated=total_bytes > self.text_chars,
            total_bytes=total_bytes,
            language=suffix.lstrip(".") or "text",
        )

    # -- Artifact -----------------------------------------------------------

    def artifact_metadata(self, ref: StorageReference, *, mime_type: str | None = None) -> ArtifactInfo:
        """Return bounded artifact metadata; inline a small image as a data URI.

        Only files at or under ``max_bytes`` get an inline ``data_uri`` for
        directly-displayable image formats; everything else returns metadata
        only.
        """
        path = Path(ref.path)
        size = path.stat().st_size if path.exists() and path.is_file() else 0
        resolved_mime = mime_type or self._guess_mime(path)
        data_uri: str | None = None
        if (
            path.is_file()
            and size <= self.max_bytes
            and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".svg", ".pdf"}
        ):
            data_uri = f"data:{resolved_mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"
        return ArtifactInfo(path=ref.path, mime_type=resolved_mime, size_bytes=size, data_uri=data_uri)

    # -- Composite ----------------------------------------------------------

    def composite_slots(self, metadata: dict[str, Any]) -> CompositeSlots:
        """Return the slot inventory without rendering any child (FR-017)."""
        slots_raw = metadata.get("slots", {}) if isinstance(metadata, dict) else {}
        slots = {str(k): str(v) for k, v in slots_raw.items()} if isinstance(slots_raw, dict) else {}
        return CompositeSlots(slots=slots)

    def composite_raster_slot(self, ref: StorageReference, slot_name: str = "raster") -> ArrayPlane | None:
        """Bounded read of a composite raster slot subdirectory, if present.

        Used by the compatibility adapter to keep returning a raster image for
        composites that have a raster slot (legacy behavior).
        """
        slot_path = Path(ref.path) / slot_name
        if not slot_path.exists():
            return None
        slot_ref = StorageReference(backend="zarr", path=str(slot_path))
        try:
            return self.array_plane(slot_ref, slice_index=0)
        except Exception:
            return None

    # -- Collection ---------------------------------------------------------

    def collection_sample(
        self,
        *,
        count: int,
        item_type: str | None,
        items: list[dict[str, Any]],
    ) -> CollectionSample:
        """Return a bounded sample of a collection's item refs (FR-009).

        ``items`` is the already-registered item descriptor list (each a
        ``{data_ref, type_name, ...}`` dict from ``register_output_payload``).
        Only the first ``max_items`` are surfaced; iteration is bounded.
        """
        bounded = list(items[: self.max_items])
        return CollectionSample(
            count=int(count),
            item_type=item_type,
            items=bounded,
            sampled=count > len(bounded),
        )

    # -- PNG helper (re-export so providers do not import private modules) --

    def png_data_uri(self, matrix: list[list[float | None]]) -> str:
        """Encode a 2-D matrix as a grayscale PNG data URI (legacy-compat only).

        Non-finite cells (encoded as ``None``) are coerced to ``0`` since the
        legacy grayscale encoder only consumes finite floats; this path feeds
        the REST compatibility adapter, not the new numeric viewer.
        """
        from scistudio.previewers._raster import _image_data_uri_from_matrix

        finite = [[(v if isinstance(v, (int, float)) else 0.0) for v in row] for row in matrix]
        return _image_data_uri_from_matrix(finite)

    # -- internals ----------------------------------------------------------

    def _open_array_handle(self, ref: StorageReference) -> tuple[Any, list[int], str]:
        """Open a raster handle WITHOUT reading the full payload.

        Returns ``(handle, full_shape, dtype)`` where ``handle`` is sliceable
        with numpy-style indexing. For Zarr the handle is the lazy array; for
        TIFF the page array is read (single IFD). This is the boundary that
        makes large-array previews bounded.
        """
        path = Path(ref.path)
        suffix = path.suffix.lower()

        if suffix in {".tif", ".tiff"}:
            import tifffile

            # FR-010/SC-004: read ONLY the first IFD page via ``key=0`` — never
            # the whole multi-page stack that ``tifffile.imread(path)`` would
            # materialize. Single-page and volumetric single-page TIFFs are
            # unaffected (key=0 IS that page); genuine multi-page stacks are
            # bounded to the first page. (Plain ``imread`` is kept — it is the
            # call CI fixtures already exercise — just scoped to one page.)
            arr = tifffile.imread(str(path), key=0)
            return arr, [int(d) for d in arr.shape], str(getattr(arr, "dtype", "unknown"))

        if suffix == ".zarr" or path.is_dir():
            import numpy as np
            import zarr

            node: Any = zarr.open(str(path), mode="r")
            handle: Any
            if isinstance(node, zarr.Array):
                handle = node
            elif "data" in node:
                handle = node["data"]
            else:
                raise ValueError(f"Zarr store at {path} has no top-level array or 'data' dataset")
            shape_attr = getattr(handle, "shape", None)
            if shape_attr is None:
                # Lazy handle without a shape attribute (e.g. a test double or
                # an exotic store). Materialize once via ``[...]`` so we still
                # produce a preview; real Zarr arrays always expose ``.shape``
                # and take the bounded path above.
                materialized = np.asarray(handle[...])
                return materialized, [int(d) for d in materialized.shape], str(materialized.dtype)
            shape = [int(d) for d in shape_attr]
            return handle, shape, str(getattr(handle, "dtype", "unknown"))

        raise ValueError(f"Unsupported raster preview format for {path}")

    def _read_bounded_plane(
        self,
        handle: Any,
        *,
        full_shape: list[int],
        y_idx: int,
        x_idx: int,
        axis_indices: dict[int, int] | None = None,
        no_downsample: bool = False,
    ) -> Any:
        """Slice a bounded 2-D plane out of *handle* using explicit indices.

        ``axis_indices`` maps each non-(y, x) axis position to the selected
        index along it. Only the requested plane is materialized — for a Zarr
        handle this is a single chunked read, never ``handle[...]``.
        """
        import numpy as np

        ndim = len(full_shape)
        picks = axis_indices or {}
        selector: list[Any] = [slice(None)] * ndim
        # Collapse every non-(y,x) dim to its selected index (default 0) so the
        # read stays 2-D and touches exactly one plane.
        for i in range(ndim):
            if i in (y_idx, x_idx):
                continue
            size = full_shape[i]
            raw = int(picks.get(i, 0))
            selector[i] = max(0, min(raw, size - 1)) if size > 0 else 0

        plane = handle[tuple(selector)] if ndim > 0 else handle
        plane = np.asarray(plane)
        while plane.ndim > 2:
            plane = plane[0]
        return plane

    @staticmethod
    def _finite_extent(plane: Any) -> tuple[float | None, float | None]:
        """Return the (min, max) of the finite entries of *plane*.

        NaN/inf are ignored so a diverging colormap legend stays meaningful;
        an all-NaN / empty plane yields ``(None, None)``.
        """
        import numpy as np

        arr = np.asarray(plane, dtype=float)
        if arr.size == 0:
            return None, None
        finite = arr[np.isfinite(arr)]
        if finite.size == 0:
            return None, None
        return float(finite.min()), float(finite.max())

    def _downsample(self, matrix: Any) -> list[list[float | None]]:
        import numpy as np

        from scistudio.previewers._raster import _downsample_matrix

        arr = np.asarray(matrix)
        if arr.ndim < 2:
            arr = arr.reshape(1, -1) if arr.ndim == 1 else arr.reshape(1, 1)
        result = _downsample_matrix(arr, max_dim=self.max_dim)
        return self._json_safe_matrix(result)

    @staticmethod
    def _json_safe_matrix(rows: list[list[float]]) -> list[list[float | None]]:
        """Replace non-finite cells (NaN / +-inf) with ``None`` (JSON ``null``).

        The numeric matrix is the primary preview payload and must serialize as
        strict JSON; ``NaN`` / ``Infinity`` are not valid JSON, so masked
        scientific arrays would otherwise break the session response. The
        frontend renders ``null`` cells as empty/transparent.
        """
        import math

        return [[(v if isinstance(v, (int, float)) and math.isfinite(v) else None) for v in row] for row in rows]

    def _axes_from_ref(self, ref: StorageReference, full_shape: list[int]) -> list[str]:
        axes_raw = ref.metadata.get("axes") if ref.metadata else None
        if isinstance(axes_raw, list):
            return [str(a) for a in axes_raw]
        return []

    @staticmethod
    def _guess_mime(path: Path) -> str:
        suffix = path.suffix.lower()
        mapping = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".svg": "image/svg+xml",
            ".pdf": "application/pdf",
            ".tif": "image/tiff",
            ".tiff": "image/tiff",
            ".zarr": "application/zarr",
        }
        return mapping.get(suffix, suffix.lstrip(".") or "application/octet-stream")


__all__ = [
    "DEFAULT_MAX_BYTES",
    "DEFAULT_MAX_DIM",
    "DEFAULT_MAX_ITEMS",
    "DEFAULT_MAX_ROWS",
    "DEFAULT_MAX_TILE",
    "ArrayPlane",
    "ArrayTile",
    "ArtifactInfo",
    "CollectionSample",
    "CompositeSlots",
    "DataFramePage",
    "PreviewDataAccess",
    "SeriesPoints",
    "SliceAxis",
    "TextChunk",
]
