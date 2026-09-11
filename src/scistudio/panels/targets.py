"""Freeze backend catalog targets and reachable children, never browser metadata."""

from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from scistudio.core.meta._display_name import resolve_display_name
from scistudio.core.storage.ref import StorageReference
from scistudio.previewers.models import PreviewTarget, TargetKind


class PanelError(Exception):
    """Stable context operation failure."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def project_identity(runtime: Any) -> tuple[Any, ...]:
    project = runtime.active_project
    return (id(project), getattr(project, "id", None), str(getattr(project, "path", "")), id(runtime.data_catalog))


def collection_store(runtime: Any) -> OrderedDict[str, dict[str, Any]]:
    identity = project_identity(runtime)
    if getattr(runtime, "_panel_collection_project", None) != identity:
        runtime._panel_collections = OrderedDict()
        runtime._panel_collection_project = identity
    return cast(OrderedDict[str, dict[str, Any]], runtime._panel_collections)


def register_collection(runtime: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """Retain collection output identity for the runtime catalog/project lifetime."""
    ref = "collection-" + uuid4().hex
    result = {**payload, "collection_ref": ref}
    store = collection_store(runtime)
    store[ref] = deepcopy(result)
    return result


def file_stamp(path: str) -> tuple[Any, ...]:
    p = Path(path)
    try:
        info = p.stat()
        return (str(p.resolve()), info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    except OSError as exc:
        raise PanelError(409, "stale_context", "The panel's data is no longer available") from exc


@dataclass
class FrozenTarget:
    target: PreviewTarget
    storage: StorageReference | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    collection: dict[str, Any] | None = None
    record: Any = None
    stamp: tuple[Any, ...] | None = None
    catalog_ref: str | None = None
    children: dict[str, FrozenTarget] = field(default_factory=dict)
    parent: FrozenTarget | None = None

    def validate(self, runtime: Any) -> None:
        if self.parent is not None:
            self.parent.validate(runtime)
        if self.catalog_ref:
            try:
                record = runtime.get_data_record(self.catalog_ref)
            except KeyError as exc:
                raise PanelError(409, "stale_context", "The panel's catalog reference was removed") from exc
            if record is not self.record or record.ref != self.storage or record.metadata != self.metadata:
                raise PanelError(409, "stale_context", "The panel's catalog reference changed")
        if self.storage is not None and file_stamp(self.storage.path) != self.stamp:
            raise PanelError(409, "stale_context", "The panel's stored data changed")


def type_chain(runtime: Any, type_name: str) -> tuple[str, ...]:
    """Follow recorded registry ancestry without importing a type implementation."""
    chain = [type_name]
    registry = getattr(runtime, "type_registry", None)
    while registry is not None and len(chain) < 32:
        try:
            spec = registry.resolve(chain[-1])
        except Exception:
            break
        parent = getattr(spec, "base_type", "")
        if not parent or parent in chain:
            break
        chain.append(parent)
    return tuple(reversed(chain))


def freeze_target(runtime: Any, ref: str) -> FrozenTarget:
    collection = collection_store(runtime).get(ref)
    if collection is not None:
        item_type = str(collection.get("item_type") or "")
        return FrozenTarget(
            target=PreviewTarget(
                kind=TargetKind.COLLECTION_REF,
                ref=ref,
                recorded_type=item_type,
                type_chain=type_chain(runtime, item_type),
                collection_item_type=item_type,
            ),
            collection=deepcopy(collection),
        )
    try:
        record = runtime.get_data_record(ref)
    except KeyError as exc:
        raise PanelError(403, "unauthorized_ref", "A panel target must be a backend catalog reference") from exc
    target = runtime.resolve_session_target(PreviewTarget(kind=TargetKind.DATA_REF, ref=ref))
    return FrozenTarget(
        target=target,
        storage=deepcopy(record.ref),
        metadata=deepcopy(record.metadata),
        record=record,
        stamp=file_stamp(record.ref.path),
        catalog_ref=ref,
    )


def child_targets(
    runtime: Any, parent: FrozenTarget, access: Any, *, cursor: str | None = None, limit: int | None = None
) -> dict[str, Any]:
    """Enumerate one bounded page; child authority comes only from frozen storage."""
    if parent.collection is not None:
        data = parent.collection
        from dataclasses import asdict

        page = asdict(
            access.collection_sample(
                count=data["count"], item_type=data.get("item_type"), items=data["items"], cursor=cursor, limit=limit
            )
        )
        items = []
        for raw in page["items"]:
            ref = raw.get("data_ref") or raw.get("collection_ref")
            if not ref:
                continue
            child = parent.children.get(ref)
            if child is None:
                child = freeze_target(runtime, ref)
                child.parent = parent
                parent.children[ref] = child
            # Stamp the backend-resolved display name from the child's frozen
            # (authoritative, non-browser) metadata so the collection grid shows
            # the real source filename instead of a truncated ref (regression:
            # the legacy membership path carried this; the frozen path dropped it).
            items.append(
                {
                    "ref": ref,
                    "type_name": child.target.recorded_type,
                    "kind": child.target.kind.value,
                    "display_name": resolve_display_name(child.metadata, fallback=""),
                }
            )
        return {**page, "items": items, "truncated": page["sampled"], "complete": not page["sampled"]}
    if parent.storage is None:
        raise PanelError(400, "unsupported", "This target has no composite slots")
    slots = access.composite_slots(parent.metadata).slots
    if len(slots) > access.max_items:
        raise PanelError(413, "read_budget", "Composite slot inventory exceeds panel item budget")
    result = []
    for name, type_name in slots.items():
        storage = access.composite_slot_ref(parent.storage, name)
        if storage is None:
            continue
        # Composite manifests may contain paths. Re-check their confinement.
        if not Path(storage.path).resolve().is_relative_to(Path(parent.storage.path).resolve()):
            raise PanelError(403, "unauthorized_ref", "Composite child escapes its parent")
        ref = f"{parent.target.ref}#{name}"
        if ref not in parent.children:
            md = deepcopy(storage.metadata or {})
            parent.children[ref] = FrozenTarget(
                target=PreviewTarget(
                    kind=TargetKind.DATA_REF,
                    ref=ref,
                    recorded_type=type_name,
                    type_chain=tuple(md.get("type_chain") or type_chain(runtime, type_name)),
                ),
                storage=storage,
                metadata=md,
                stamp=file_stamp(storage.path),
                parent=parent,
            )
        result.append({"name": name, "type_name": type_name, "ref": ref})
    return {"slots": result, "sampled": False, "truncated": False, "complete": True}
