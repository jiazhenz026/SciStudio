"""Generic panel operations dispatched only after context reference authorization."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from scistudio.panels.contexts import READ_POINTS, PanelContext, PanelContexts, read_access
from scistudio.panels.targets import PanelError, child_targets, plot_variant_target
from scistudio.stability import internal


@internal()
@dataclass(frozen=True)
class ReadOperation:
    """One ``read(op, params)`` operation: the parameters it accepts and what it answers.

    :func:`read_context` checks a read's parameters against ``params``, and the
    generated panel SDK reference renders this table, so an operation cannot
    accept a parameter the reference does not list. ``params`` is ``None`` for
    an operation that ignores its parameters.
    """

    op: str
    params: tuple[str, ...] | None
    target: str
    result: str


#: Every read operation, in the order the reference lists them. Every
#: operation also accepts ``format``: ``"json"`` (the default) or ``"binary"``
#: for the numeric array and series reads.
READ_OPERATIONS: dict[str, ReadOperation] = {
    operation.op: operation
    for operation in (
        ReadOperation(
            "metadata",
            None,
            "any target",
            "`{type_chain, metadata, shape, dtype}` recorded for the target.",
        ),
        ReadOperation(
            "composite.slots",
            (),
            "a composite",
            "`{slots: [{name, type_name, ref}], complete}`; each slot `ref` can be read or opened.",
        ),
        ReadOperation(
            "collection.items",
            ("cursor", "limit"),
            "a collection",
            "One bounded page `{items: [{ref, type_name, kind, display_name}], truncated, complete, ...}`; "
            "pass the returned cursor to continue.",
        ),
        ReadOperation(
            "table.page",
            ("page", "page_size", "sort_by", "sort_dir"),
            "a data object with a table",
            "`{columns, rows, total, total_rows, page, page_size, total_pages, sort: {by, direction}, complete}`. "
            "Paging is navigation over complete data.",
        ),
        ReadOperation(
            "table.xy",
            ("x_column", "y_column", "max_points"),
            "a data object with a table",
            f"`{{x, y, ...}}` for two columns; `max_points` is clamped to 1..{READ_POINTS}.",
        ),
        ReadOperation(
            "array.plane",
            ("slice_index", "axis_indices"),
            "an array",
            "A numeric read of the selected plane: `values` plus geometry such as `shape`, `dtype`, `axes`, "
            "`slice_axes`, `vmin`, `vmax`.",
        ),
        ReadOperation(
            "array.tile",
            ("slice_index", "axis_indices", "y0", "x0", "height", "width"),
            "an array",
            "A numeric read of one bounded window `{values, y0, x0, ...}` of the selected plane.",
        ),
        ReadOperation(
            "series.points",
            ("max_points",),
            "a series",
            f"`{{index, values, nonfinite_positions, source_indices, ...}}`; `max_points` is clamped to "
            f"1..{READ_POINTS}.",
        ),
        ReadOperation(
            "text.chunk",
            ("offset", "length"),
            "a text object",
            "`{text, content, offset, next_offset, total_bytes, encoding, truncated, complete}`; "
            "continue from `next_offset`.",
        ),
        ReadOperation(
            "artifact.info",
            (),
            "an artifact",
            "`{name, path, mime_type, size}`, plus `formats` for a plot.",
        ),
        ReadOperation(
            "artifact.file",
            ("variant",),
            "an artifact",
            "`artifact.info` plus a `url` the page can load; `variant` selects one of a plot's `formats`.",
        ),
    )
}


def read_context(store: PanelContexts, context: PanelContext, ref: str, op: str, params: dict[str, Any]) -> Any:
    """Return bounded JSON or a NumericRead; callers transport off the event loop."""
    target = store.authorize(context, ref)
    access = read_access()
    storage = target.storage
    options = dict(params)
    options.pop("format", None)
    if op == "metadata":
        return {
            "type_chain": list(target.target.type_chain),
            "metadata": target.metadata,
            "shape": target.metadata.get("shape", (storage.metadata or {}).get("shape") if storage else None),
            "dtype": target.metadata.get("dtype", (storage.metadata or {}).get("dtype") if storage else None),
        }
    if op in ("composite.slots", "collection.items"):
        _only(options, op)
        return child_targets(store.runtime, target, access, **options)
    if storage is None:
        raise PanelError(400, "unsupported", "This read requires an individual data object")
    if op == "table.page":
        _only(options, op)
        result = asdict(access.dataframe_page(storage, **options))
        return {
            **result,
            "total": result["total_rows"],
            "sort": {"by": result["sort_by"], "direction": result["sort_dir"]},
            "sampled": False,
            # A page is not a truncation. Every row of the table is reachable by
            # paging, so the read reports the table as complete however many
            # pages it takes — flagging a paged table as truncated is exactly the
            # misleading status #1886 Part 1 forbids, and it disagreed with the
            # session metadata for the same table, which has always said False.
            "truncated": False,
            "complete": True,
        }
    if op == "table.xy":
        _only(options, op)
        options["max_points"] = min(READ_POINTS, max(1, int(options.get("max_points", READ_POINTS))))
        result = access.panel_table_xy(storage, **options).to_json()
        pairs = result.pop("values")
        return {**result, "x": [row[0] for row in pairs], "y": [row[1] for row in pairs]}
    if op in ("array.plane", "array.tile"):
        _only(options, op)
        if "axis_indices" in options:
            options["axis_indices"] = {int(k): int(v) for k, v in options["axis_indices"].items()}
        reader = access.panel_array_tile if op == "array.tile" else access.panel_array_plane
        return reader(storage, **options)
    if op == "series.points":
        _only(options, op)
        return access.panel_series_points(
            storage, target.metadata, max_points=min(READ_POINTS, max(1, int(options.get("max_points", READ_POINTS))))
        )
    if op == "text.chunk":
        _only(options, op)
        chunk = asdict(access.text_chunk(storage, **options))
        return {**chunk, "text": chunk["content"], "sampled": False, "complete": not chunk["truncated"]}
    if op in ("artifact.info", "artifact.file"):
        _only(options, op)
        import mimetypes

        from scistudio.previewers._plot_formats import available_formats

        primary = access.artifact_file(storage)
        # A plot is rendered once per allowed format, and the reader picks between
        # them in the Save menu. ``variant`` names which of those files to grant;
        # without it the primary is served, which is what every other artifact has.
        granted = target
        path = primary
        variant = options.get("variant")
        if variant:
            granted = plot_variant_target(target, str(variant))
            sibling = granted.storage
            if sibling is None:  # pragma: no cover - always constructed with storage
                raise PanelError(400, "unsupported", "This target has no artifact file")
            path = access.artifact_file(sibling)
        info = {
            "name": path.name,
            # The viewer this read serves identifies an artifact by its storage
            # path, not by its bare file name: two run outputs are routinely
            # called ``figure.png``, and only the path tells them apart.
            "path": str(path),
            "mime_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            "size": path.stat().st_size,
        }
        if "PlotArtifact" in target.target.type_chain:
            # Reported off the primary, so the menu is the same set whichever
            # format is currently being shown.
            info["formats"] = available_formats(primary)
        if op == "artifact.file":
            token, grant_id = store.grant_artifact(context, granted)
            info["url"] = f"/api/panels/t/{token}/artifact/{grant_id}"
        return info
    raise PanelError(400, "unsupported", f"Unsupported panel read operation: {op}")


def _only(options: dict[str, Any], op: str) -> None:
    unexpected = options.keys() - set(READ_OPERATIONS[op].params or ())
    if unexpected:
        raise PanelError(422, "invalid_request", f"Unsupported read parameters: {', '.join(sorted(unexpected))}")
