"""Panel descriptor validation; discovering a page never imports its Python."""

from __future__ import annotations

import json
import re
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scistudio.previewers.models import OwnerKind, PreviewerSpec
from scistudio.stability import internal

PANEL_API_VERSION = "1.0"
_ID = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*\Z")
_VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
_KEYS = {"id", "api_version", "contexts", "types", "priority", "name", "description", "version", "entry"}


@internal()
@dataclass(frozen=True)
class PanelDescriptor:
    """Validated manifest of an HTML panel; paths are backend-only."""

    id: str
    api_version: str
    contexts: tuple[str, ...]
    types: tuple[str, ...]
    root: Path
    owner_kind: OwnerKind
    owner_name: str
    priority: int = 0
    name: str = ""
    description: str = ""
    version: str = ""
    entry: str = "index.html"
    has_python: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return the public catalog descriptor without local paths."""
        return {
            key: getattr(self, key)
            for key in ("id", "api_version", "priority", "name", "description", "version", "entry", "has_python")
        } | {"contexts": list(self.contexts), "types": list(self.types)}

    def candidates(self) -> list[PreviewerSpec]:
        """Adapt each claimed preview type into the existing routing ladder."""
        if "preview" not in self.contexts:
            return []
        result = []
        for claim in self.types:
            collection = claim.startswith("Collection[") or claim == "Collection"
            type_name = claim[11:-1] if claim.startswith("Collection[") else claim
            result.append(
                PreviewerSpec(
                    previewer_id=self.id,
                    owner_kind=self.owner_kind,
                    owner_name=self.owner_name,
                    target_type=type_name,
                    supports_collection=collection,
                    priority=self.priority,
                    api_version=self.api_version,
                    panel=self.to_dict(),
                )
            )
        return result


def parse_descriptor(
    directory: Path, *, owner_kind: OwnerKind, owner_name: str, registered_types: Collection[str]
) -> tuple[PanelDescriptor, list[str]]:
    """Validate a panel descriptor or raise a diagnostic ValueError."""
    # Development references: FR-002/003 and MiniApp FR-001/002.
    from scistudio.panels.files import resolve_panel_file

    directory = Path(directory)
    try:
        path = resolve_panel_file(directory, "panel.json")
        if path.stat().st_size > 65536:
            raise ValueError("descriptor exceeds 64 KiB")
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"FR-003 {directory}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("FR-002: panel.json must be an object")
    panel_id = data.get("id")
    if not isinstance(panel_id, str) or not _ID.fullmatch(panel_id) or panel_id != directory.name:
        raise ValueError("FR-002: id must be lowercase dotted segments and equal the directory name")
    if panel_id.startswith("core.") and owner_kind is not OwnerKind.CORE:
        raise ValueError("FR-002: core. ids are reserved for core panels")
    version = data.get("api_version")
    if not isinstance(version, str) or not _VERSION.fullmatch(version) or version.split(".")[0] != "1":
        raise ValueError("FR-003: unsupported api_version; host serves major 1 (MAJOR.MINOR)")
    contexts = data.get("contexts")
    if (
        not isinstance(contexts, list)
        or not contexts
        or any(c not in ("preview", "interactive", "miniapp") for c in contexts)
        or len(set(contexts)) != len(contexts)
    ):
        raise ValueError("FR-002: contexts must be a nonempty distinct list of preview/interactive/miniapp")
    types = data.get("types", [])
    if not isinstance(types, list) or any(not isinstance(t, str) for t in types) or len(set(types)) != len(types):
        raise ValueError("FR-002: types must be a list of distinct registered type names")
    if "preview" in contexts and not types:
        raise ValueError("FR-002: preview requires types")
    if "miniapp" in contexts and len(types) != 1:
        raise ValueError("MiniApp FR-001: miniapp requires exactly one type")
    for claim in types:
        if claim in ("DataObject", "Collection"):
            if owner_kind is not OwnerKind.CORE:
                raise ValueError("FR-002: sentinel types are reserved for core panels")
            continue
        name = claim[11:-1] if claim.startswith("Collection[") and claim.endswith("]") else claim
        if name not in registered_types or name in ("DataObject", "Collection"):
            raise ValueError(f"FR-002: unregistered panel type {claim!r}")
    if type(data.get("priority", 0)) is not int:
        raise ValueError("FR-002: priority must be an integer")
    for key in ("name", "description", "version", "entry"):
        if key in data and not isinstance(data[key], str):
            raise ValueError(f"FR-002: {key} must be a string")
    entry = data.get("entry", "index.html")
    if resolve_panel_file(directory, entry).suffix.lower() != ".html":
        raise ValueError("FR-003: entry must name a confined HTML file")
    notes = [f"FR-003: unknown key {key!r} ignored" for key in sorted(data.keys() - _KEYS)]
    has_python = (directory / "panel.py").is_file()
    if has_python and "miniapp" not in contexts:
        notes.append("MiniApp FR-002: panel.py present but no context provides call; Python is never started")
    return PanelDescriptor(
        id=panel_id,
        api_version=version,
        contexts=tuple(contexts),
        types=tuple(types),
        root=directory.resolve(),
        owner_kind=owner_kind,
        owner_name=owner_name,
        priority=data.get("priority", 0),
        name=data.get("name", panel_id),
        description=data.get("description", ""),
        version=data.get("version", ""),
        entry=entry,
        has_python=has_python,
    ), notes


__all__ = ["PANEL_API_VERSION", "PanelDescriptor"]
