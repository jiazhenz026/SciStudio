"""The type a file extension is opened as, remembered per project (#2112).

Several registered types can load the same extension, and which one is right is
a fact about the data, not about the installation. A ``.tif`` in one project is
a plain microscopy ``Image``; in another it is the project's own ``SRSImage``.
The load capability table can list the candidates but cannot choose between
them, and picking by tier order would make the answer depend on which packages
happen to be installed rather than on what the file actually holds.

So the person chooses, once, and this module remembers the choice: extension ->
type name, for one project. Project-scoped on purpose — the collision that
makes the question worth asking usually comes from a project-local drop-in
type, and a global answer would carry one project's convention into every other
one. There is no user layer for the same reason.

Every read is best-effort. A missing file, malformed JSON, an unknown key from
a newer build, or an entry of the wrong shape is skipped rather than raised: a
lost preference must never be able to stop a file from opening, only to make
the picker ask again.

Sibling to :mod:`scistudio.previewers.choices` on purpose: both store a
person's preference about what they see, in one file each under the same
project library dir, and both are read by the data routes rather than by the
previewer machinery itself. Keeping them together keeps the two from drifting
into different conventions for the same kind of file.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from scistudio.core.dropins import USER_LIBRARY_DIR_NAME
from scistudio.stability import internal
from scistudio.utils.atomic_io import atomic_write_text

logger = logging.getLogger(__name__)

__all__ = [
    "OPEN_AS_FILENAME",
    "clear_open_as",
    "normalize_extension",
    "open_as_path",
    "read_open_as",
    "write_open_as",
]

#: One file per concern under the project library dir, as
#: ``previewer-choices.json`` already is.
OPEN_AS_FILENAME = "open-as-types.json"

#: Schema version of the written file. Readers ignore what they do not know, so
#: this exists to make a future migration legible rather than to gate reads.
_SCHEMA_VERSION = 1


@internal()
def normalize_extension(extension: str) -> str:
    """Return *extension* as a lowercase, dot-prefixed key (``.tif``).

    Callers hand this a suffix from a path, a format id off a storage ref, or
    a string typed into an API query, and those three spell the same extension
    three ways. Normalising at the door means the stored keys have one shape,
    so a choice recorded from a double-click is found again by a lookup that
    came from anywhere else.
    """
    text = extension.strip().lower().lstrip(".")
    return f".{text}" if text else ""


@internal()
def open_as_path(project_dir: str | Path) -> Path:
    """Return the open-as file for *project_dir*, under ``<project>/.scistudio``."""
    return Path(project_dir) / USER_LIBRARY_DIR_NAME / OPEN_AS_FILENAME


@internal()
def read_open_as(project_dir: str | Path) -> dict[str, str]:
    """Return ``{extension: type_name}`` for *project_dir*; never raises.

    A missing file is an empty map. Anything unreadable, unparseable, or shaped
    wrongly is logged once and treated as empty, and individual entries that
    are not a string pair are skipped so one bad key cannot cost the rest.
    """
    path = open_as_path(project_dir)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Ignoring unreadable open-as types at %s", path.name, exc_info=True)
        return {}
    if not isinstance(payload, dict):
        logger.warning("Ignoring open-as types at %s: expected an object", path.name)
        return {}
    raw = payload.get("open_as")
    if not isinstance(raw, dict):
        return {}
    return {
        normalize_extension(key): value
        for key, value in raw.items()
        if isinstance(key, str) and isinstance(value, str) and normalize_extension(key) and value
    }


def _write(project_dir: str | Path, entries: dict[str, str]) -> dict[str, str]:
    path = open_as_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": _SCHEMA_VERSION, "open_as": dict(sorted(entries.items()))}
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return entries


@internal()
def write_open_as(project_dir: str | Path, extension: str, type_name: str) -> dict[str, str]:
    """Record *extension* -> *type_name* for *project_dir*.

    Returns the map as written. Reads the existing file first so a concurrent
    edit to another extension is preserved rather than overwritten.
    """
    entries = read_open_as(project_dir)
    entries[normalize_extension(extension)] = type_name
    return _write(project_dir, entries)


@internal()
def clear_open_as(project_dir: str | Path, extension: str) -> dict[str, str]:
    """Forget the choice for *extension*, if there was one.

    Returns the map as written. Clearing an extension that was never chosen is
    not an error: the caller's intent — no remembered type for this extension —
    already holds, and reporting a failure would push the caller into checking
    first.
    """
    entries = read_open_as(project_dir)
    entries.pop(normalize_extension(extension), None)
    return _write(project_dir, entries)
