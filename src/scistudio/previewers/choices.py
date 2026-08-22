"""A user's chosen previewer per type (#2049).

ADR-048 FR-003 fixes one precedence ladder — project, then user, then package,
then core — and that ladder answers "which previewer is best" without ever
asking the person looking at the data. When several previewers can render a
type, the person may prefer one the ladder does not pick: a package's tailored
spectrum plot over a project-local experiment, or the plain core table over
either.

This module stores that preference. It is deliberately *not* the FR-005
project-default mechanism, which stays exactly as specified: a tie-breaker
between same-tier previewers of equal priority, declared by whoever authored
the project. That is an author's declaration about a project; this is a
person's choice about their own view. Keeping them in separate files keeps the
two from being mistaken for each other, and keeps FR-005's semantics untouched.

**Two layers, project over user.** A choice recorded against the open project
wins over the same person's global choice, mirroring the tier model blocks,
types, and previewers already follow. The user layer lives under the library
root :func:`scistudio.core.dropins.library_root_for_project` resolves, so a
tutorial project's choices land in the tutorial-scoped library rather than
following the user into every real project afterwards (ADR-053 FR-070/FR-071).

**Keyed on the exact type name.** A choice made for ``Spectrum`` applies to
``Spectrum`` and not to a type that merely descends from it. The narrower rule
is the predictable one: a choice silently governing subtypes the person never
looked at is harder to explain than one that simply does not apply yet.

Every read is best-effort. A missing file, malformed JSON, an unknown key from
a newer build, or an entry of the wrong shape is skipped rather than raised —
the same forward-compatibility rule ``projects.json`` learned in #2073, and for
the same reason: this file outlives the build that wrote it, and losing a
preference must never be able to stop a preview from rendering.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from scistudio.core.dropins import USER_LIBRARY_DIR_NAME, library_root_for_project
from scistudio.stability import internal
from scistudio.utils.atomic_io import atomic_write_text

logger = logging.getLogger(__name__)

__all__ = [
    "CHOICES_FILENAME",
    "clear_choice",
    "load_choices",
    "project_choices_path",
    "read_choice_layer",
    "user_choices_path",
    "write_choice",
]

#: One file per concern under the library root, as ``projects.json`` and
#: ``tutorial-progress.json`` already are.
CHOICES_FILENAME = "previewer-choices.json"

#: Schema version of the written file. Readers ignore what they do not know, so
#: this exists to make a future migration legible rather than to gate reads.
_SCHEMA_VERSION = 1


@internal()
def user_choices_path(project_dir: str | Path | None) -> Path:
    """Return the user-layer choices file for *project_dir*'s library root."""
    return library_root_for_project(project_dir) / CHOICES_FILENAME


@internal()
def project_choices_path(project_dir: str | Path) -> Path:
    """Return the project-layer choices file, under ``<project>/.scistudio``."""
    return Path(project_dir) / USER_LIBRARY_DIR_NAME / CHOICES_FILENAME


@internal()
def read_choice_layer(path: Path) -> dict[str, str]:
    """Return ``{type_name: previewer_id}`` from *path*; never raises.

    A missing file is an empty layer. Anything unreadable, unparseable, or
    shaped wrongly is logged once and treated as empty, and individual entries
    that are not a string pair are skipped so one bad key cannot cost the rest.
    """
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Ignoring unreadable previewer choices at %s", path.name, exc_info=True)
        return {}
    if not isinstance(payload, dict):
        logger.warning("Ignoring previewer choices at %s: expected an object", path.name)
        return {}
    raw = payload.get("choices")
    if not isinstance(raw, dict):
        return {}
    return {
        key: value for key, value in raw.items() if isinstance(key, str) and isinstance(value, str) and key and value
    }


@internal()
def load_choices(project_dir: str | Path | None) -> dict[str, str]:
    """Return the effective choices for *project_dir*, project layer winning.

    The user layer loads unconditionally — it is defined by the person, not by
    which project happens to be open — and the project layer, when there is a
    project, overrides it per type.
    """
    effective = read_choice_layer(user_choices_path(project_dir))
    if project_dir is not None:
        effective.update(read_choice_layer(project_choices_path(project_dir)))
    return effective


def _write_layer(path: Path, choices: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": _SCHEMA_VERSION, "choices": dict(sorted(choices.items()))}
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


@internal()
def write_choice(path: Path, target_type: str, previewer_id: str) -> dict[str, str]:
    """Record *target_type* -> *previewer_id* in the layer at *path*.

    Returns the layer as written. Reads the existing layer first so a
    concurrent edit to another type is preserved rather than overwritten.
    """
    choices = read_choice_layer(path)
    choices[target_type] = previewer_id
    _write_layer(path, choices)
    return choices


@internal()
def clear_choice(path: Path, target_type: str) -> dict[str, str]:
    """Remove *target_type* from the layer at *path*, if present.

    Returns the layer as written. Clearing a type that was never chosen is not
    an error: the caller's intent — "no choice for this type here" — already
    holds, and reporting a failure would push the caller into checking first.
    """
    choices = read_choice_layer(path)
    choices.pop(target_type, None)
    _write_layer(path, choices)
    return choices
