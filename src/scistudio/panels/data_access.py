"""The bounded reader behind the panel data operations.

:class:`PreviewDataAccess` reads a preview target's stored data for the panel
routes and the panel contexts. Table-page, text, collection, and raster reads
honour the row / byte / item / tile limits of the session; the numeric window
reads (``panel_*``) return exact dtype-preserving values a page at a time.

Array reads are bounded directly against the storage handle: a Zarr array is
indexed with explicit slices (``arr[plane_index, y0:y1, x0:x1]``) rather than
``arr[...]`` so only the requested plane or tile is read into memory.
"""
# Maintainer context (kept outside generated API documentation):
# Relocated from the removed ``scistudio.previewers.data_access`` root (#2493,
# ADR-054 §8). The legacy provider reads (downsampled planes, whole-series
# points, inline artifact data URIs, the grayscale PNG encoder) went with the
# Python previewers; the panel reads stayed.
# Development references: ADR-052, ADR-054, #2460, #2493.

from __future__ import annotations

import base64
import datetime
import decimal
import math
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scistudio.core.storage.ref import StorageReference
from scistudio.stability import internal, provisional


def _json_safe_value(value: Any) -> Any:
    """Return one table cell in a form strict JSON can carry.

    A stored table holds values JSON has no literal for: ``NaN`` and ``±inf``,
    timestamps, dates, times, decimals, and raw bytes. Emitting them unchanged
    made the whole page fail to serialise, so a single missing measurement or a
    timestamp column took the preview down with it.

    Non-finite numbers use the same sentinel strings the array reads use
    (``"NaN"`` / ``"Infinity"`` / ``"-Infinity"``), so a missing measurement is
    shown as what it is rather than erased to an empty cell. Temporal and
    decimal values become their ISO / decimal text, and bytes become base64 —
    each readable, and none of them silently dropped.
    """
    # Development references: #1886 item E.
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Infinity" if value > 0 else "-Infinity"
        return value
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, datetime.timedelta):
        return str(value)
    if isinstance(value, decimal.Decimal):
        return "NaN" if value.is_nan() else str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return base64.b64encode(bytes(value)).decode("ascii")
    if isinstance(value, dict):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe_value(item) for item in value]
    return str(value)


if TYPE_CHECKING:
    from scistudio.panels._reads.arrays import NumericRead

# Default budgets. ``max_bytes`` is the 20 MiB per-request/per-tile transport
# budget (#1886 item G).
DEFAULT_MAX_ROWS = 200
DEFAULT_MAX_BYTES = 20 * 1024 * 1024
DEFAULT_MAX_ITEMS = 100
DEFAULT_MAX_TILE = 256
DEFAULT_MAX_DIM = 256
DEFAULT_TEXT_CHARS = 5000


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
    matrix: list[list[float | str]]
    """The tile's numeric values, row-major. Non-finite cells are conveyed as the
    sentinel strings ``"NaN"`` / ``"Infinity"`` / ``"-Infinity"`` so the payload
    stays strict JSON."""


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
    """Language/format hint derived from the file extension."""
    encoding: str = "utf-8"
    """Encoding used for the decoded byte window."""
    offset: int = 0
    """Inclusive byte offset of this window."""
    next_offset: int | None = None
    """Next byte offset, or None at end of file."""


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
    next_cursor: str | None = None
    """Cursor for the next page; None when every item has been reached."""
    page: int | None = None
    """1-based page index when read with ``page``/``page_size`` (dataframe-style
    paging); ``None`` for a legacy cursor read or a partial sample."""
    page_size: int | None = None
    """Items per page actually used (capped at the item budget) when read with
    ``page``/``page_size``; ``None`` otherwise."""
    total_pages: int | None = None
    """Total number of pages at this page size (at least 1) when read with
    ``page``/``page_size``; ``None`` otherwise. With ``count`` as the total item
    count, every item is reachable by requesting each page 1..``total_pages``."""


@provisional(since="0.3.1")
class PreviewDataAccess:
    """The bounded reader behind the panel data operations.

    The panel runtime builds one from the session or context budgets. It never
    exposes raw storage paths to a panel: the routes put only the JSON-safe
    contents of its typed results on the wire. Methods named ``*_page`` /
    ``*_chunk`` / ``*_tile`` are bounded by the budgets; the ``panel_*`` window
    reads return exact values a page at a time.
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
        from scistudio.panels._reads.table_cache import _get_preview_table

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
        rows = [{key: _json_safe_value(value) for key, value in row.items()} for row in page_table.to_pylist()]
        return DataFramePage(
            columns=columns,
            rows=rows,
            total_rows=total_rows,
            page=effective_page,
            page_size=effective_page_size,
            total_pages=total_pages,
            sort_by=effective_sort_by,
            sort_dir=effective_sort_dir if effective_sort_by else None,
        )

    # -- Array --------------------------------------------------------------

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
        selected by ``slice_index`` along the auto-detected slider axis.

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
        result = self.panel_array_tile(
            ref,
            slice_index=slice_index,
            y0=y0,
            x0=x0,
            height=height,
            width=width,
        )
        meta = result.metadata
        return ArrayTile(
            y0=meta["y0"], x0=meta["x0"], height=meta["height"], width=meta["width"], matrix=result.to_json()["values"]
        )

    @internal()
    def panel_array_plane(
        self,
        ref: StorageReference,
        *,
        slice_index: int = 0,
        axis_indices: dict[int, int] | None = None,
    ) -> NumericRead:
        """Read a bounded dtype-preserving plane for the panel transport."""
        from scistudio.panels._reads.arrays import read_plane

        return read_plane(self, ref, slice_index, axis_indices)

    @internal()
    def panel_array_tile(
        self,
        ref: StorageReference,
        *,
        slice_index: int = 0,
        axis_indices: dict[int, int] | None = None,
        y0: int = 0,
        x0: int = 0,
        height: int | None = None,
        width: int | None = None,
    ) -> NumericRead:
        """Read a tile directly from storage without materializing its plane."""
        from scistudio.panels._reads.arrays import read_tile

        return read_tile(
            self, ref, slice_index=slice_index, axis_indices=axis_indices, y0=y0, x0=x0, height=height, width=width
        )

    @internal()
    def panel_series_points(
        self,
        ref: StorageReference,
        metadata: dict[str, Any],
        *,
        offset: int = 0,
        limit: int,
    ) -> NumericRead:
        """Return the exact x/y float64 rows of one source window of a Series.

        Row ``i`` is source row ``offset + i``; a non-finite or missing value is
        returned in place as NaN, never dropped. Continue from ``next_offset``.
        """
        from scistudio.panels._reads.arrays import numeric_read
        from scistudio.panels._reads.series import read_xy_window

        path = Path(ref.path)
        if ref.backend == "zarr" or path.suffix.lower() == ".zarr" or path.is_dir():
            raise ValueError("Series preview expects Arrow/Parquet storage; got Zarr/directory storage")
        meta = metadata if isinstance(metadata, dict) else {}
        index_name, value_name = meta.get("index_name"), meta.get("value_name")
        both = isinstance(index_name, str) and isinstance(value_name, str)
        window = read_xy_window(
            path,
            meta,
            x_column=index_name if both else None,
            y_column=value_name if both else None,
            offset=offset,
            limit=limit,
        )
        values = window.pop("values")
        for key in ("columns", "x_column", "y_column"):
            window.pop(key)
        return numeric_read(values, {**window, "columns": ["x", "y"]}, self.max_bytes)

    @internal()
    def panel_table_xy(
        self,
        ref: StorageReference,
        *,
        x_column: str | None = None,
        y_column: str | None = None,
        offset: int = 0,
        limit: int,
    ) -> NumericRead:
        """Return the exact x/y rows of one source window of two table columns."""
        import pyarrow.parquet as pq

        from scistudio.panels._reads.arrays import numeric_read
        from scistudio.panels._reads.series import read_xy_window

        path = Path(ref.path)
        if ref.backend == "zarr" or path.suffix.lower() == ".zarr" or path.is_dir():
            raise ValueError("Table x/y preview expects Arrow/Parquet storage; got Zarr/directory storage")
        if len(pq.ParquetFile(path).schema_arrow.names) < 2:
            raise ValueError("Table x/y preview requires at least two columns")
        window = read_xy_window(path, {}, x_column=x_column, y_column=y_column, offset=offset, limit=limit)
        values = window.pop("values")
        return numeric_read(values, window, self.max_bytes)

    # -- Text ---------------------------------------------------------------

    @provisional(since="0.3.1")
    def text_chunk(self, ref: StorageReference, *, offset: int = 0, length: int | None = None) -> TextChunk:
        """Return a bounded chunk of text plus a truncation marker.

        Use this to preview a text file. It reads at most ``text_chars`` bytes
        from the start of the file (decoded leniently) so a huge log never loads
        in full.

        Args:
            ref: Storage reference for the text file.
            offset: Inclusive byte offset; use the returned next_offset to page.
            length: Requested byte count, capped at the text and byte budgets.
                The window carries a partial trailing UTF-8 character forward.

        Returns:
            A :class:`TextChunk` with the leading content and a truncation flag.
        """
        from scistudio.panels._reads.chunks import text_window

        path = Path(ref.path)
        budget = min(self.text_chars, self.max_bytes, self.text_chars if length is None else length)
        content, next_offset, total_bytes = text_window(path, offset=offset, length=budget)
        return TextChunk(
            content=content,
            truncated=next_offset is not None,
            total_bytes=total_bytes,
            language=path.suffix.lstrip(".") or "text",
            encoding="utf-8",
            offset=offset,
            next_offset=next_offset,
        )

    # -- Composite ----------------------------------------------------------

    @staticmethod
    def _slot_type_name(value: Any) -> str:
        """Return the type name a recorded composite slot holds.

        A slot is recorded either as a bare type name or as the wire-format
        envelope the serializer writes — ``{backend, path, format, metadata}``,
        whose ``metadata.type_chain`` runs general to specific. Stringifying that
        envelope is what put a whole JSON mapping on screen as the slot's "type"
        and left it matching no previewer, so read the chain instead.
        """
        if not isinstance(value, dict):
            return str(value)
        meta = value.get("metadata")
        chain = meta.get("type_chain") if isinstance(meta, dict) else None
        if isinstance(chain, (list, tuple)) and chain:
            return str(chain[-1])
        for key in ("type_name", "type"):
            name = value.get(key)
            if isinstance(name, str) and name:
                return name
        return ""

    @provisional(since="0.3.1")
    def composite_slots(self, metadata: dict[str, Any]) -> CompositeSlots:
        """Return a composite's slot inventory without rendering any child.

        Args:
            metadata: Recorded composite metadata; its ``slots`` mapping is read.

        Returns:
            A :class:`CompositeSlots` mapping slot name to its type name.
        """
        slots_raw = metadata.get("slots", {}) if isinstance(metadata, dict) else {}
        if not isinstance(slots_raw, dict):
            return CompositeSlots(slots={})
        return CompositeSlots(slots={str(name): self._slot_type_name(value) for name, value in slots_raw.items()})

    @provisional(since="0.3.1")
    def composite_slot_ref(self, ref: StorageReference, slot_name: str) -> StorageReference | None:
        """Resolve the storage reference for one slot of a composite target.

        The runtime owns the composite on-disk layout. This returns a slot's
        recorded reference so a single slot can be read through the bounded
        readers (:meth:`dataframe_page`, :meth:`text_chunk`, ...) without
        constructing a storage reference or knowing the storage layout.

        Args:
            ref: Storage reference for the composite.
            slot_name: Name of the slot to resolve.

        Returns:
            The slot's :class:`StorageReference`, or ``None`` when the slot
            cannot be resolved (no manifest or no such slot), so the caller can
            degrade gracefully.
        """
        from scistudio.core.storage.composite_store import CompositeStore

        return CompositeStore().slot_ref(ref, slot_name)

    @provisional(since="0.3.5")
    def artifact_file(self, ref: StorageReference) -> Path:
        """Resolve an existing artifact for the host's streaming file response.

        The host must authorize the storage reference before calling this and
        issue a context-bound token URL; this server path is never a panel URL.
        No inline limit applies, and no payload is loaded into memory.
        """
        path = Path(ref.path).resolve(strict=True)
        if not path.is_file():
            raise ValueError("Artifact storage must name a regular file")
        return path

    # -- Collection ---------------------------------------------------------

    @provisional(since="0.3.1")
    def collection_sample(
        self,
        *,
        count: int,
        item_type: str | None,
        items: list[dict[str, Any]],
        cursor: str | None = None,
        limit: int | None = None,
        page: int | None = None,
        page_size: int | None = None,
    ) -> CollectionSample:
        """Return a bounded page of a collection's item references.

        Two paging styles are supported and every item is reachable by either:

        * ``page`` / ``page_size`` — dataframe-style paging (mirrors
          :meth:`dataframe_page`). Any page ``1..total_pages`` can be requested
          directly, and the result carries ``page`` / ``page_size`` /
          ``total_pages`` alongside ``count`` (the total item count). This is the
          faithful reading contract: nothing is silently capped — page through to
          reach every item.
        * ``cursor`` / ``limit`` — sequential cursor paging. ``next_cursor`` walks
          forward until it is ``None``.

        With no paging argument, the first ``max_items`` items are surfaced as a
        legacy bounded sample.

        Args:
            count: Total number of items in the collection.
            item_type: Type name shared by the items, when known.
            items: The already-registered item descriptors (each a
                ``{data_ref, type_name, ...}`` mapping).
            cursor: Opaque cursor from a previous page of this inventory.
            limit: Requested cursor page size, capped at max_items.
            page: 1-based page number (dataframe-style); clamped to range.
            page_size: Items per page (dataframe-style); capped at max_items.

        Returns:
            A :class:`CollectionSample` holding the bounded page. Page/cursor
            paging both require the full registered inventory; a legacy partial
            sample (no paging argument) stays valid.

        Raises:
            ValueError: If paging is requested without the full inventory, if
                both a cursor and page are given, or if a paging bound is not
                positive.
        """
        from scistudio.panels._reads.chunks import collection_offset, next_collection_cursor

        paged = page is not None or page_size is not None
        cursored = cursor is not None or limit is not None
        if (paged or cursored) and (count < 0 or len(items) != count):
            raise ValueError("Paginated collection count must match the registered item inventory")
        if paged and cursored:
            raise ValueError("Use either page/page_size or a cursor, not both")
        if limit is not None and limit < 1:
            raise ValueError("Collection limit must be positive")
        if page is not None and page < 1:
            raise ValueError("Collection page must be positive")
        if page_size is not None and page_size < 1:
            raise ValueError("Collection page_size must be positive")

        if paged:
            effective_page_size = min(page_size if page_size is not None else self.max_items, self.max_items)
            total_pages = max(1, (int(count) + effective_page_size - 1) // effective_page_size)
            effective_page = max(1, min(page if page is not None else 1, total_pages))
            offset = (effective_page - 1) * effective_page_size
            bounded = list(items[offset : offset + effective_page_size])
            return CollectionSample(
                count=int(count),
                item_type=item_type,
                items=bounded,
                sampled=count > len(bounded),
                next_cursor=next_collection_cursor(offset + len(bounded), count),
                page=effective_page,
                page_size=effective_page_size,
                total_pages=total_pages,
            )

        offset = collection_offset(cursor, count)
        budget = self.max_items if limit is None else min(limit, self.max_items)
        bounded = list(items[offset : offset + budget])
        return CollectionSample(
            count=int(count),
            item_type=item_type,
            items=bounded,
            sampled=count > len(bounded),
            next_cursor=(next_collection_cursor(offset + len(bounded), count) if count == len(items) else None),
        )

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

    def _axes_from_ref(self, ref: StorageReference, full_shape: list[int]) -> list[str]:
        axes_raw = ref.metadata.get("axes") if ref.metadata else None
        if isinstance(axes_raw, list):
            return [str(a) for a in axes_raw]
        return []


__all__ = [
    "ArrayTile",
    "CollectionSample",
    "CompositeSlots",
    "DataFramePage",
    "PreviewDataAccess",
    "TextChunk",
]
