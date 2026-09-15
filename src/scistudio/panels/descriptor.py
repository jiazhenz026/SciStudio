"""Panel descriptor validation; discovering a page never imports its Python."""

from __future__ import annotations

import json
import re
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from scistudio.previewers.models import OwnerKind, PreviewerSpec
from scistudio.stability import internal, provisional

#: The panel descriptor ``api_version`` the host serves. A descriptor must declare
#: the same major version, as ``MAJOR.MINOR``.
PANEL_API_VERSION = "1.0"
#: The SDK major this host serves; a panel loads the SDK from ``sdk/<major>/``.
PANEL_API_MAJOR = PANEL_API_VERSION.split(".")[0]
_ID = re.compile(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*\Z")
_VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
#: The contexts a panel may declare, in the order the reference lists them.
PANEL_CONTEXTS = ("preview", "interactive", "miniapp")
#: The largest ``panel.json`` the host reads.
DESCRIPTOR_MAX_BYTES = 65536
# Core-reserved type names that are not TypeRegistry entries: the catch-all
# sentinels (``DataObject``/``Collection``) and the synthetic catalog record
# types the built-in previewers serve (``PlotArtifact``; see
# ``previewers.fallbacks.core_previewer_specs``). Only CORE-owned panels may
# claim these; user panels must claim registered types.
_CORE_SENTINEL_TYPES = ("DataObject", "Collection", "PlotArtifact")


# TODO(#2288): owner_kind uses OwnerKind from the deprecated previewer models root.
#   Out of scope per #2426; the enum needs a non-deprecated home before 0.3.6.
#   Followup: https://github.com/jiazhenz026/SciStudio/issues/2288
@provisional(since="0.3.5")
@dataclass(frozen=True)
class PanelDescriptor:
    """A validated ``panel.json`` descriptor and the folder it came from.

    ``id``, ``api_version``, ``contexts``, ``types``, ``priority``, ``name``,
    ``description``, ``version``, and ``entry`` are the descriptor's fields after
    validation. ``root`` is the resolved panel folder, ``owner_kind`` and
    ``owner_name`` record the tier and owner it was discovered under, and
    ``has_python`` is true when a ``panel.py`` sits beside the descriptor. The
    local ``root`` path never leaves the backend.
    """

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

    @internal()
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


@provisional(since="0.3.5")
def parse_descriptor(
    directory: Path, *, owner_kind: OwnerKind, owner_name: str, registered_types: Collection[str]
) -> tuple[PanelDescriptor, list[str]]:
    """Validate the panel folder ``directory`` and return its descriptor.

    ``registered_types`` is the set of data type names the panel may claim; a
    claim outside it is refused. Returns the :class:`PanelDescriptor` and a list
    of non-fatal notes, such as unknown keys that were ignored. Raises
    ``ValueError`` with a diagnostic when the descriptor is invalid: the ``id``
    does not equal the folder name, the ``api_version`` major is not served, the
    contexts or types are malformed, or ``entry`` does not name an HTML file
    inside the folder.
    """
    # Development references: FR-002/003 and MiniApp FR-001/002.
    from scistudio.panels.files import resolve_panel_file

    directory = Path(directory)
    try:
        path = resolve_panel_file(directory, "panel.json")
        if path.stat().st_size > DESCRIPTOR_MAX_BYTES:
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
    if not isinstance(version, str) or not _VERSION.fullmatch(version) or version.split(".")[0] != PANEL_API_MAJOR:
        raise ValueError("FR-003: unsupported api_version; host serves major 1 (MAJOR.MINOR)")
    contexts = data.get("contexts")
    if (
        not isinstance(contexts, list)
        or not contexts
        or any(c not in PANEL_CONTEXTS for c in contexts)
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
        if claim in _CORE_SENTINEL_TYPES:
            if owner_kind is not OwnerKind.CORE:
                raise ValueError("FR-002: sentinel types are reserved for core panels")
            continue
        name = claim[11:-1] if claim.startswith("Collection[") and claim.endswith("]") else claim
        if name not in registered_types or name in _CORE_SENTINEL_TYPES:
            raise ValueError(f"FR-002: unregistered panel type {claim!r}")
    if type(data.get("priority", 0)) is not int:
        raise ValueError("FR-002: priority must be an integer")
    for key in ("name", "description", "version", "entry"):
        if key in data and not isinstance(data[key], str):
            raise ValueError(f"FR-002: {key} must be a string")
    entry = data.get("entry", "index.html")
    if resolve_panel_file(directory, entry).suffix.lower() != ".html":
        raise ValueError("FR-003: entry must name a confined HTML file")
    entry = PurePosixPath(entry).as_posix()
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


@internal()
@dataclass(frozen=True)
class DescriptorField:
    """One ``panel.json`` key: its JSON type, whether it is required, and its rule.

    The generated panel descriptor reference renders this table, and
    :func:`parse_descriptor` derives its set of known keys from it, so a key
    cannot be accepted without also being documented.
    """

    key: str
    json_type: str
    required: bool
    default: str
    rule: str


DESCRIPTOR_FIELDS: tuple[DescriptorField, ...] = (
    DescriptorField(
        "id",
        "string",
        True,
        "",
        "Lowercase dotted segments, each starting with a letter (`[a-z][a-z0-9_]*`). Must equal the panel "
        "directory's name. Ids starting with `core.` are reserved for panels shipped with SciStudio.",
    ),
    DescriptorField(
        "api_version",
        "string",
        True,
        "",
        "`MAJOR.MINOR` with no leading zeros. The major must be the one this host "
        f"serves (`{PANEL_API_MAJOR}`); the panel loads the SDK from `sdk/{PANEL_API_MAJOR}/`.",
    ),
    DescriptorField(
        "contexts",
        "array of string",
        True,
        "",
        "Non-empty list of distinct values from " + ", ".join(f"`{c}`" for c in PANEL_CONTEXTS) + ".",
    ),
    DescriptorField(
        "types",
        "array of string",
        False,
        "`[]`",
        "Distinct registered type names; `Collection[<Type>]` claims a collection of that type. Required "
        "(non-empty) when `contexts` includes `preview`; exactly one type when it includes `miniapp`. The "
        "names " + ", ".join(f"`{t}`" for t in _CORE_SENTINEL_TYPES) + " are reserved for built-in panels.",
    ),
    DescriptorField(
        "priority",
        "integer",
        False,
        "`0`",
        "Orders panels that claim the same type at the same tier; the higher value is chosen. Booleans are refused.",
    ),
    DescriptorField("name", "string", False, "the `id`", "Human-readable name for the panel."),
    DescriptorField("description", "string", False, '`""`', "Human-readable description of what the panel shows."),
    DescriptorField("version", "string", False, '`""`', "The panel's own version label; not interpreted by the host."),
    DescriptorField(
        "entry",
        "string",
        False,
        "`index.html`",
        "Path of the page to load, relative to the panel directory. Must stay inside the directory and name "
        "an `.html` file.",
    ),
)
_KEYS = frozenset(field.key for field in DESCRIPTOR_FIELDS)

#: Rules about the panel directory as a whole, rendered with the field table.
DESCRIPTOR_FILE_RULES: tuple[str, ...] = (
    f"`panel.json` must be a JSON object no larger than {DESCRIPTOR_MAX_BYTES // 1024} KiB.",
    "Unknown keys are ignored and reported as a validation note.",
    "A `panel.py` beside `panel.json` is started only for the `miniapp` context; in any other context it is "
    "reported as a note and never run.",
    "Discovering a panel never imports or executes its Python.",
)


__all__ = ["PANEL_API_VERSION", "PanelDescriptor"]
