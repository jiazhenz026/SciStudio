"""The bounded reader a preview provider uses to read payload bytes.

:class:`PreviewDataAccess` is the only surface a previewer provider may use to
read a target's stored data. Every method keeps a budget: table-page, text,
collection, and raster reads honour the row / byte / item / tile / dimension
limits the preview promises, so a huge dataset never loads in full. The
series/curve helpers are the exception — they return the complete set of
plottable points so a line preview and any point export are true to the stored
data.

The runtime constructs one of these per request and injects it on
``request.data_access``; you call its methods and never instantiate it yourself.
The result types below are plain dataclasses with JSON-safe contents.

Array reads are bounded directly against the storage handle: a Zarr array is
indexed with explicit slices (``arr[plane_index, y0:y1, x0:x1]``) rather than
``arr[...]`` so only the requested plane or tile is read into memory.
"""

from __future__ import annotations

import base64
import math
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scistudio.core.storage.ref import StorageReference
from scistudio.stability import internal, provisional

# Default budgets (Internal, ADR-052 §8.2): runtime budget defaults, not an
# author contract — providers read the applied budgets through
# :class:`~scistudio.previewers.models.PreviewLimits` on ``request.limits``.
# These are excluded from ``__all__`` and the generated reference. ``max_rows``
# mirrors the legacy ``MAX_TABLE_PAGE_SIZE`` (200); ``max_bytes`` mirrors the MCP
# 8 MiB cap (FR-027); ``max_dim`` / ``max_tile`` mirror the legacy 256-pixel
# thumbnail bound.
DEFAULT_MAX_ROWS = 200
DEFAULT_MAX_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_ITEMS = 100
DEFAULT_MAX_TILE = 256
DEFAULT_MAX_DIM = 256
DEFAULT_TEXT_CHARS = 5000
DEFAULT_SERIES_POINTS = 256


@provisional(since="0.3.1")
@dataclass(frozen=True)
class DataFramePage:
    """One bounded page of a table, returned by :meth:`PreviewDataAccess.dataframe_page`.

    Holds a single page of rows plus the paging/sort state the frontend needs to
    render a pager. The page size is capped by the session row budget.
    """

    columns: list[str]
    """Column names in table order."""
    rows: list[dict[str, Any]]
    """The page's rows, each a column-name -> value mapping."""
    total_rows: int
    """Total rows in the whole table (not just this page)."""
    page: int
    """1-based index of this page after clamping to the valid range."""
    page_size: int
    """Number of rows per page actually used (capped at the row budget)."""
    total_pages: int
    """Total number of pages at this page size (at least 1)."""
    sort_by: str | None
    """Column the rows were sorted by, or ``None`` if unsorted."""
    sort_dir: str | None
    """Sort direction (``"asc"`` / ``"desc"``), or ``None`` if unsorted."""
    truncated: bool
    """True when the table has more rows than this page shows."""


@provisional(since="0.3.1")
@dataclass(frozen=True)
class SliceAxis:
    """One non-displayed (sliced) axis of an N-D array.

    For an array with more than two dimensions, every axis that is not the
    displayed Y or X axis becomes a slider the user can move. This carries what
    the frontend needs to render one such index picker.
    """

    axis: int
    """Position of this axis in the array's shape."""
    name: str
    """Display name of the axis (e.g. ``"z"``, ``"channel"``)."""
    size: int
    """Number of indices available along this axis."""
    index: int
    """Currently selected index along this axis."""


@provisional(since="0.3.1")
@dataclass(frozen=True)
class ArrayPlane:
    """A bounded 2-D plane sliced out of an N-D array, with axis metadata.

    ``matrix`` holds the actual (downsampled) numeric values of the displayed
    plane — the previewer renders these as a numeric heatmap table, not a lossy
    grayscale image. Every non-displayed axis is listed in ``slice_axes`` with
    its selected index, so an N-D array is fully navigable (one index picker per
    extra axis).
    """

    shape: list[int]
    """Full shape of the source array."""
    axes: list[str]
    """Axis names in shape order, when known (e.g. ``["z", "y", "x"]``)."""
    dtype: str
    """Data type name of the source array."""
    slice_axis_name: str | None
    """Name of the primary (first extra) slider axis; mirrors the first entry of
    ``slice_axes``. Kept for backward-compatible callers."""
    slice_axis_size: int | None
    """Size of the primary slider axis; mirrors the first entry of
    ``slice_axes``."""
    slice_index: int | None
    """Selected index along the primary slider axis; mirrors the first entry of
    ``slice_axes``."""
    slice_axes: list[SliceAxis]
    """Every non-displayed axis with its selected index, one entry per extra
    axis."""
    matrix: list[list[float | None]]
    """The displayed plane's downsampled values. Non-finite cells (NaN / +-inf)
    are ``None`` (JSON ``null``) so the payload stays valid JSON and the frontend
    renders them as empty/transparent cells."""
    vmin: float | None
    """Finite minimum of the displayed plane, for a value-scale legend; ``None``
    when the plane has no finite values. A diverging/sequential colormap built
    from ``vmin``/``vmax`` does not clip signed data."""
    vmax: float | None
    """Finite maximum of the displayed plane, for a value-scale legend; ``None``
    when the plane has no finite values."""
    truncated: bool
    """True when the plane was downsampled to fit the dimension budget."""
    ndim: int
    """Number of dimensions of the source array."""


@provisional(since="0.3.1")
@dataclass(frozen=True)
class ArrayTile:
    """A bounded rectangular tile read out of a 2-D array plane.

    Returned by :meth:`PreviewDataAccess.array_tile` so the frontend can fetch a
    zoomed-in region of a large plane without loading the whole plane.
    """

    y0: int
    """Top row offset of the tile within the plane."""
    x0: int
    """Left column offset of the tile within the plane."""
    height: int
    """Number of rows in the tile (capped at the tile budget)."""
    width: int
    """Number of columns in the tile (capped at the tile budget)."""
    matrix: list[list[float]]
    """The tile's numeric values, row-major."""


@provisional(since="0.3.1")
@dataclass(frozen=True)
class SeriesPoints:
    """The complete finite set of (x, y) chart points for a Series preview.

    Unlike the bounded readers, this returns every plottable point so a line
    preview and any point export match the stored data exactly.
    """

    points: list[dict[str, float]]
    """Finite chart points, each ``{"x": ..., "y": ...}``."""
    total: int
    """Total number of source values considered (including non-numeric ones)."""
    truncated: bool
    """Always ``False`` — the point set is complete (kept for shape parity)."""
    nonnumeric: int = 0
    """Count of values dropped because they were not finite numbers."""


@provisional(since="0.3.1")
@dataclass(frozen=True)
class TableXYPoints:
    """The complete finite set of (x, y) points from two table columns."""

    columns: list[str]
    """All column names available in the source table."""
    x_column: str
    """Column used for the x values."""
    y_column: str
    """Column used for the y values."""
    points: list[dict[str, float]]
    """Finite points, each ``{"x": ..., "y": ...}``."""
    total: int
    """Total rows in the source table."""
    truncated: bool
    """Always ``False`` — every finite point is returned."""
    nonnumeric: int
    """Count of rows dropped because either value was not a finite number."""


@provisional(since="0.3.1")
@dataclass(frozen=True)
class TextChunk:
    """A bounded chunk of text plus a truncation marker."""

    content: str
    """The decoded text read from the start of the file."""
    truncated: bool
    """True when the file is larger than the read budget."""
    total_bytes: int
    """Total size of the source file in bytes."""
    language: str
    """Language/format hint derived from the file extension (e.g. ``"py"``,
    ``"txt"``)."""


@provisional(since="0.3.1")
@dataclass(frozen=True)
class ArtifactInfo:
    """Bounded metadata about an opaque artifact, with no full read.

    Describes a file artifact by path, MIME type, and size. A small,
    directly-displayable image may also carry an inline ``data_uri``; larger
    files return metadata only.
    """

    path: str
    """Storage path of the artifact."""
    mime_type: str
    """MIME type of the artifact."""
    size_bytes: int
    """Artifact size in bytes."""
    data_uri: str | None = None
    """Inline ``data:`` URI for a small displayable image, else ``None``."""


@provisional(since="0.3.1")
@dataclass(frozen=True)
class CompositeSlots:
    """The slot inventory of a composite target, with no child rendered."""

    slots: dict[str, str]
    """Mapping of slot name to its recorded type name."""


@provisional(since="0.3.1")
@dataclass(frozen=True)
class CollectionSample:
    """A bounded sample of a collection's items."""

    count: int
    """Total number of items in the collection."""
    item_type: str | None
    """Type name shared by the items, when known."""
    items: list[dict[str, Any]]
    """The sampled item descriptors (at most the item budget)."""
    sampled: bool
    """True when the collection has more items than the sample shows."""


@provisional(since="0.3.1")
class PreviewDataAccess:
    """The bounded reader a provider uses for every payload read.

    This is the only sanctioned way a previewer provider reads a target's stored
    bytes. The runtime builds it from the session budgets and injects it on
    ``request.data_access`` — you call its methods and never construct it. It
    never exposes raw storage paths to the frontend: you get typed result
    objects and put only their JSON-safe contents into your envelope. Methods
    named ``*_page`` / ``*_chunk`` / ``*_tile`` are bounded; methods returning
    chart points return the complete set.

    Example:
        >>> def render(request):
        ...     page = request.data_access.dataframe_page(request.storage, page=1)
        ...     return {"columns": page.columns, "rows": page.rows}
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
        """Maximum table rows returned in one page."""
        self.max_bytes = max(1, int(max_bytes))
        """Maximum payload size in bytes for a bounded read."""
        self.max_items = max(1, int(max_items))
        """Maximum collection items returned in one sample."""
        self.max_tile = max(1, int(max_tile))
        """Maximum tile width/height in pixels."""
        self.max_dim = max(1, int(max_dim))
        """Maximum displayed plane width/height after downsampling."""
        self.text_chars = max(1, int(text_chars))
        """Maximum number of bytes read from a text file."""
        # ``series_points`` is a legacy constructor argument. It is now only a
        # batch-size hint for complete curve reads, not a display cap.
        self.series_batch_size = max(1, int(series_points))
        """Row batch size used when streaming a complete series/curve read."""

    # -- DataFrame ----------------------------------------------------------

    @provisional(since="0.3.1")
    def dataframe_page(
        self,
        ref: StorageReference,
        *,
        page: int = 1,
        page_size: int = 50,
        sort_by: str | None = None,
        sort_dir: str = "asc",
    ) -> DataFramePage:
        """Return one bounded, optionally sorted page of a CSV/Parquet table.

        Use this to fill a paged table view. The table is cached after the first
        read, so paging and re-sorting stay cheap on repeat calls.

        Args:
            ref: Storage reference for the table file.
            page: 1-based page number; clamped to the valid range.
            page_size: Rows per page; capped at ``max_rows``.
            sort_by: Column to sort by; ignored if it is not a column.
            sort_dir: ``"asc"`` or ``"desc"``; anything else is treated as
                ``"asc"``.

        Returns:
            A :class:`DataFramePage` for the requested page.
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

    @provisional(since="0.3.1")
    def table_xy_points(
        self,
        ref: StorageReference,
        *,
        x_column: str | None = None,
        y_column: str | None = None,
    ) -> TableXYPoints:
        """Return all finite x/y points from two Parquet table columns.

        Use this to build a scatter or line chart from a table. When a column is
        not given (or not found), the first two columns are used.

        Args:
            ref: Storage reference for the Parquet table.
            x_column: Column for the x values; defaults to the first column.
            y_column: Column for the y values; defaults to the second column.

        Returns:
            A :class:`TableXYPoints` with every finite (x, y) pair.

        Raises:
            ValueError: If the storage is Zarr/directory storage, or the table
                has fewer than two columns.
        """
        path = Path(ref.path)
        if ref.backend == "zarr" or path.suffix.lower() == ".zarr" or path.is_dir():
            raise ValueError("Table x/y preview expects Arrow/Parquet storage; got Zarr/directory storage")

        import pyarrow.parquet as pq

        pf = pq.ParquetFile(path)
        columns = list(pf.schema_arrow.names)
        resolved_x = x_column if x_column in columns else (columns[0] if columns else None)
        resolved_y = y_column if y_column in columns else (columns[1] if len(columns) > 1 else None)
        if resolved_x is None or resolved_y is None:
            raise ValueError("Table x/y preview requires at least two columns")

        total = int(pf.metadata.num_rows)
        if total <= 0:
            return TableXYPoints(
                columns=columns,
                x_column=resolved_x,
                y_column=resolved_y,
                points=[],
                total=0,
                truncated=False,
                nonnumeric=0,
            )

        points: list[dict[str, float]] = []
        nonnumeric = 0
        batch_size = max(1, self.series_batch_size)
        for batch in pf.iter_batches(batch_size=batch_size, columns=[resolved_x, resolved_y]):
            xs = batch.column(0).to_pylist()
            ys = batch.column(1).to_pylist()
            for raw_x, raw_y in zip(xs, ys, strict=True):
                x_val = self._finite_number(raw_x)
                y_val = self._finite_number(raw_y)
                if x_val is not None and y_val is not None:
                    points.append({"x": x_val, "y": y_val})
                else:
                    nonnumeric += 1

        return TableXYPoints(
            columns=columns,
            x_column=resolved_x,
            y_column=resolved_y,
            points=points,
            total=total,
            truncated=False,
            nonnumeric=nonnumeric,
        )

    # -- Array --------------------------------------------------------------

    @provisional(since="0.3.1")
    def array_plane(
        self,
        ref: StorageReference,
        *,
        slice_index: int = 0,
        axis_indices: dict[int, int] | None = None,
    ) -> ArrayPlane:
        """Return array shape/axes metadata plus one bounded, downsampled 2-D plane.

        Use this to show a heatmap of one face of an array. The returned
        ``matrix`` is the actual numeric data of the displayed plane, downsampled
        to ``max_dim`` per side, with ``vmin`` / ``vmax`` for a value-scale
        legend. Every non-displayed axis is independently navigable.

        Args:
            ref: Storage reference for the array (Zarr or a directory store).
            slice_index: Index along the first extra axis; used when
                ``axis_indices`` does not set that axis.
            axis_indices: Optional mapping of axis position to the selected index
                along it, one entry per non-displayed axis.

        Returns:
            An :class:`ArrayPlane` for the selected plane.

        Raises:
            ValueError: If the storage format is not a supported array store.
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

    @provisional(since="0.3.1")
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
        """Read one bounded rectangular tile from a 2-D plane.

        Use this to fetch a zoomed-in region of a large plane. The plane is
        selected by ``slice_index`` along the auto-detected slider axis, like
        :meth:`array_plane`.

        Args:
            ref: Storage reference for the array.
            slice_index: Index along the slider axis to read the plane from.
            y0: Top row offset of the tile within the plane.
            x0: Left column offset of the tile within the plane.
            height: Tile height in rows; capped at ``max_tile``. ``None`` reads
                to the bottom edge (still capped).
            width: Tile width in columns; capped at ``max_tile``. ``None`` reads
                to the right edge (still capped).

        Returns:
            An :class:`ArrayTile` for the requested region.

        Raises:
            ValueError: If the storage format is not a supported array store.
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

    @provisional(since="0.3.1")
    def series_points(self, ref: StorageReference, metadata: dict[str, Any]) -> SeriesPoints:
        """Return the complete set of chart points for a Series.

        Use this to plot a 1-D series. It prefers in-memory values supplied on
        ``metadata['values']`` and otherwise reads the persisted Parquet file in
        full. If the table has both Series axis columns, both are used;
        otherwise the first value column is plotted against the row index.

        Args:
            ref: Storage reference for the Series payload.
            metadata: Recorded Series metadata; may carry ``values``,
                ``index_name``, and ``value_name``.

        Returns:
            A :class:`SeriesPoints` with every finite point.

        Raises:
            ValueError: If the storage is Zarr/directory storage.
        """
        path = Path(ref.path)
        if ref.backend == "zarr" or path.suffix.lower() == ".zarr" or path.is_dir():
            raise ValueError("Series preview expects Arrow/Parquet storage; got Zarr/directory storage")

        values: list[Any] = []
        if isinstance(metadata, dict):
            raw = metadata.get("values")
            if isinstance(raw, list):
                values = raw

        if values:
            return self._series_points_from_values(values)

        if path.exists() and path.suffix.lower() == ".parquet":
            import pyarrow.parquet as pq

            pf = pq.ParquetFile(path)
            columns = list(pf.schema_arrow.names)
            if not columns:
                return self._series_points_from_values([])

            index_name = metadata.get("index_name") if isinstance(metadata, dict) else None
            value_name = metadata.get("value_name") if isinstance(metadata, dict) else None
            if (
                isinstance(index_name, str)
                and isinstance(value_name, str)
                and index_name in columns
                and value_name in columns
            ):
                xy = self.table_xy_points(ref, x_column=index_name, y_column=value_name)
                return SeriesPoints(
                    points=xy.points,
                    total=xy.total,
                    truncated=False,
                    nonnumeric=xy.nonnumeric,
                )
            if len(columns) >= 2:
                xy = self.table_xy_points(ref, x_column=columns[0], y_column=columns[1])
                return SeriesPoints(points=xy.points, total=xy.total, truncated=False, nonnumeric=xy.nonnumeric)

            collected: list[Any] = []
            for batch in pf.iter_batches(batch_size=max(1, self.series_batch_size), columns=[columns[0]]):
                collected.extend(batch.column(0).to_pylist())
            return self._series_points_from_values(collected)

        return self._series_points_from_values([])

    def _series_points_from_values(self, values: list[Any]) -> SeriesPoints:
        """Build indexed y-values from in-memory/Parquet Series values."""
        points: list[dict[str, float]] = []
        nonnumeric = 0
        for i, value in enumerate(values):
            y_val = self._finite_number(value)
            if y_val is None:
                nonnumeric += 1
                continue
            points.append({"x": float(i), "y": y_val})
        return SeriesPoints(points=points, total=len(values), truncated=False, nonnumeric=nonnumeric)

    # -- Text ---------------------------------------------------------------

    @staticmethod
    def _finite_number(value: Any) -> float | None:
        """Return a finite float for numeric preview cells, else ``None``."""
        try:
            out = float(value)
        except (TypeError, ValueError):
            return None
        return out if math.isfinite(out) else None

    @provisional(since="0.3.1")
    def text_chunk(self, ref: StorageReference) -> TextChunk:
        """Return a bounded chunk of text plus a truncation marker.

        Use this to preview a text file. It reads at most ``text_chars`` bytes
        from the start of the file (decoded leniently) so a huge log never loads
        in full.

        Args:
            ref: Storage reference for the text file.

        Returns:
            A :class:`TextChunk` with the leading content and a truncation flag.
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

    @provisional(since="0.3.1")
    def artifact_metadata(self, ref: StorageReference, *, mime_type: str | None = None) -> ArtifactInfo:
        """Return bounded artifact metadata, inlining a small image as a data URI.

        Use this to describe an opaque file artifact without reading it in full.
        A directly-displayable image (PNG/JPEG/SVG/PDF) at or under ``max_bytes``
        also gets an inline ``data_uri``; everything else returns metadata only.

        Args:
            ref: Storage reference for the artifact file.
            mime_type: Explicit MIME type; if omitted it is guessed from the
                file extension, falling back to ``application/octet-stream``.

        Returns:
            An :class:`ArtifactInfo` describing the artifact.
        """
        path = Path(ref.path)
        size = path.stat().st_size if path.exists() and path.is_file() else 0
        # Extension -> MIME is non-load-bearing display metadata (ADR-052 §8.2),
        # so it comes from the stdlib ``mimetypes`` registry rather than a
        # hand-maintained map; an unknown suffix degrades to octet-stream.
        resolved_mime = mime_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        data_uri: str | None = None
        if (
            path.is_file()
            and size <= self.max_bytes
            and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".svg", ".pdf"}
        ):
            data_uri = f"data:{resolved_mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"
        return ArtifactInfo(path=ref.path, mime_type=resolved_mime, size_bytes=size, data_uri=data_uri)

    # -- Composite ----------------------------------------------------------

    @provisional(since="0.3.1")
    def composite_slots(self, metadata: dict[str, Any]) -> CompositeSlots:
        """Return a composite's slot inventory without rendering any child.

        Args:
            metadata: Recorded composite metadata; its ``slots`` mapping is read.

        Returns:
            A :class:`CompositeSlots` mapping slot name to its type name.
        """
        slots_raw = metadata.get("slots", {}) if isinstance(metadata, dict) else {}
        slots = {str(k): str(v) for k, v in slots_raw.items()} if isinstance(slots_raw, dict) else {}
        return CompositeSlots(slots=slots)

    @provisional(since="0.3.1")
    def composite_slot_ref(self, ref: StorageReference, slot_name: str) -> StorageReference | None:
        """Resolve the storage reference for one slot of a composite target.

        The runtime owns the composite on-disk layout. This returns a slot's
        recorded reference so a provider can read a single slot through the
        bounded readers (:meth:`dataframe_page`, :meth:`series_points`,
        :meth:`array_plane`, :meth:`text_chunk`, ...) without constructing a
        storage reference or knowing the storage layout.

        Args:
            ref: Storage reference for the composite.
            slot_name: Name of the slot to resolve.

        Returns:
            The slot's :class:`StorageReference`, or ``None`` when the slot
            cannot be resolved (no manifest or no such slot), so the provider can
            degrade gracefully.
        """
        from scistudio.core.storage.composite_store import CompositeStore

        return CompositeStore().slot_ref(ref, slot_name)

    @provisional(since="0.3.1")
    def composite_raster_slot(self, ref: StorageReference, slot_name: str = "raster") -> ArrayPlane | None:
        """Bounded read of a composite's raster slot subdirectory, if present.

        Returns a raster image for composites that carry a raster slot, used to
        keep the legacy raster preview working.

        Args:
            ref: Storage reference for the composite.
            slot_name: Name of the raster slot subdirectory.

        Returns:
            An :class:`ArrayPlane` for the raster slot, or ``None`` when the slot
            is absent or cannot be read.
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

    @provisional(since="0.3.1")
    def collection_sample(
        self,
        *,
        count: int,
        item_type: str | None,
        items: list[dict[str, Any]],
    ) -> CollectionSample:
        """Return a bounded sample of a collection's item references.

        Only the first ``max_items`` items are surfaced, so iterating a large
        collection stays bounded.

        Args:
            count: Total number of items in the collection.
            item_type: Type name shared by the items, when known.
            items: The already-registered item descriptors (each a
                ``{data_ref, type_name, ...}`` mapping).

        Returns:
            A :class:`CollectionSample` holding the bounded sample.
        """
        bounded = list(items[: self.max_items])
        return CollectionSample(
            count=int(count),
            item_type=item_type,
            items=bounded,
            sampled=count > len(bounded),
        )

    # -- PNG helper (Internal, legacy-compat) -------------------------------

    @internal()
    def png_data_uri(self, matrix: list[list[float | None]]) -> str:
        """Encode a 2-D matrix as a grayscale PNG data URI (legacy-compat only).

        Internal (ADR-052 §8.2): the legacy grayscale-PNG path used by the REST
        compatibility adapter. It is excluded from the author surface and the
        generated reference; new previewers return the numeric ``matrix`` from
        :meth:`array_plane` and let the frontend render the heatmap.

        Non-finite cells (encoded as ``None``) are coerced to ``0`` since the
        legacy grayscale encoder only consumes finite floats; this path feeds
        the REST compatibility adapter, not the new numeric viewer.
        """
        from scistudio.previewers._raster import _image_data_uri_from_matrix

        finite = [[(v if isinstance(v, (int, float)) else 0.0) for v in row] for row in matrix]
        return _image_data_uri_from_matrix(finite)

    # -- internals ----------------------------------------------------------

    def _open_array_handle(self, ref: StorageReference) -> tuple[Any, list[int], str]:
        """Open a core Array handle WITHOUT reading the full payload.

        Returns ``(handle, full_shape, dtype)`` where ``handle`` is sliceable
        with numpy-style indexing. For Zarr the handle is the lazy array. This
        is the boundary that makes large-array previews bounded while keeping
        package-owned image decoders out of core.
        """
        path = Path(ref.path)
        suffix = path.suffix.lower()

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

        raise ValueError(f"Unsupported core Array preview format for {path}")

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


# Public author surface for ``scistudio.previewers.data_access`` (ADR-052 §8.2):
# the injected reader plus its bounded-read result dataclasses, all provisional.
# The ``DEFAULT_MAX_*`` budget constants are Internal (read budgets via
# ``request.limits`` / :class:`~scistudio.previewers.models.PreviewLimits`) and
# the ``png_data_uri`` method is Internal — both excluded here.
__all__ = [
    "ArrayPlane",
    "ArrayTile",
    "ArtifactInfo",
    "CollectionSample",
    "CompositeSlots",
    "DataFramePage",
    "PreviewDataAccess",
    "SeriesPoints",
    "SliceAxis",
    "TableXYPoints",
    "TextChunk",
]
