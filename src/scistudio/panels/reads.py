"""Generic panel operations dispatched only after context reference authorization."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from scistudio.panels.contexts import READ_POINTS, PanelContext, PanelContexts, read_access
from scistudio.panels.targets import PanelError, child_targets


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
        allowed = {"cursor", "limit"} if op == "collection.items" else set()
        _only(options, allowed)
        return child_targets(store.runtime, target, access, **options)
    if storage is None:
        raise PanelError(400, "unsupported", "This read requires an individual data object")
    if op == "table.page":
        _only(options, {"page", "page_size", "sort_by", "sort_dir"})
        result = asdict(access.dataframe_page(storage, **options))
        return {
            **result,
            "total": result["total_rows"],
            "sort": {"by": result["sort_by"], "direction": result["sort_dir"]},
            "sampled": False,
            "truncated": result["total_rows"] > len(result["rows"]),
            "complete": result["total_rows"] <= len(result["rows"]),
        }
    if op == "table.xy":
        _only(options, {"x_column", "y_column", "max_points"})
        options["max_points"] = min(READ_POINTS, max(1, int(options.get("max_points", READ_POINTS))))
        result = access.panel_table_xy(storage, **options).to_json()
        pairs = result.pop("values")
        return {**result, "x": [row[0] for row in pairs], "y": [row[1] for row in pairs]}
    if op in ("array.plane", "array.tile"):
        _only(
            options,
            {"slice_index", "axis_indices"} | ({"y0", "x0", "height", "width"} if op == "array.tile" else set()),
        )
        if "axis_indices" in options:
            options["axis_indices"] = {int(k): int(v) for k, v in options["axis_indices"].items()}
        reader = access.panel_array_tile if op == "array.tile" else access.panel_array_plane
        return reader(storage, **options)
    if op == "series.points":
        _only(options, {"max_points"})
        return access.panel_series_points(
            storage, target.metadata, max_points=min(READ_POINTS, max(1, int(options.get("max_points", READ_POINTS))))
        )
    if op == "text.chunk":
        _only(options, {"offset", "length"})
        chunk = asdict(access.text_chunk(storage, **options))
        return {**chunk, "text": chunk["content"], "sampled": False, "complete": not chunk["truncated"]}
    if op in ("artifact.info", "artifact.file"):
        _only(options, set())
        path = access.artifact_file(storage)
        import mimetypes

        info = {
            "name": path.name,
            # The viewer this read serves identifies an artifact by its storage
            # path, not by its bare file name: two run outputs are routinely
            # called ``figure.png``, and only the path tells them apart.
            "path": str(path),
            "mime_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            "size": path.stat().st_size,
        }
        if op == "artifact.file":
            token, grant_id = store.grant_artifact(context, target)
            info["url"] = f"/api/panels/t/{token}/artifact/{grant_id}"
        return info
    raise PanelError(400, "unsupported", f"Unsupported panel read operation: {op}")


def _only(options: dict[str, Any], allowed: set[str]) -> None:
    unexpected = options.keys() - allowed
    if unexpected:
        raise PanelError(422, "invalid_request", f"Unsupported read parameters: {', '.join(sorted(unexpected))}")
