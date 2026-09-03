"""A person's chosen panel, per type and per capability (#2049, ADR-054 FR-049).

ADR-048 FR-003 fixes one precedence ladder — project, then user, then package,
then core — and that ladder answers "which panel is best" without ever
asking the person looking at the data. When several panels can render a
type, the person may prefer one the ladder does not pick: a package's tailored
spectrum plot over a project-local experiment, or the plain core table over
either.

This module stores that preference. It is deliberately *not* the FR-005
project-default mechanism, which stays exactly as specified: a tie-breaker
between same-tier panels of equal priority, declared by whoever authored
the project. That is an author's declaration about a project; this is a
person's choice about their own view. Keeping them in separate files keeps the
two from being mistaken for each other, and keeps FR-005's semantics untouched.

**Two layers, project over user.** A choice recorded against the open project
wins over the same person's global choice, mirroring the tier model blocks,
types, and panels already follow. The user layer lives under the library
root :func:`scistudio.core.dropins.library_root_for_project` resolves, so a
tutorial project's choices land in the tutorial-scoped library rather than
following the user into every real project afterwards (ADR-053 FR-070/FR-071).

**Keyed on the exact type name.** A choice made for ``Spectrum`` applies to
``Spectrum`` and not to a type that merely descends from it. The narrower rule
is the predictable one: a choice silently governing subtypes the person never
looked at is harder to explain than one that simply does not apply yet.

**And keyed on the required capability** (ADR-054 spec 1 FR-049). The panel a
person prefers for *looking at* a frame and the one they prefer for *producing*
from it are different preferences about different situations, and one slot for
both would make choosing a display default silently disable production from that
type. The file therefore carries one map per capability.

**What an existing file does on first read.** The file this module used to write
is ``previewer-choices.json`` in the version-1 shape, one flat
``{type: panel id}`` map. It is read as the **displaying** layer, entire:
every choice recorded before this spec was made from the preview surface, which
*is* the displaying resolution, and no producing request existed when the file
was written. Nothing is dropped and nothing is guessed. The old file is not
rewritten or deleted on read; the next write lands in ``panel-choices.json``
carrying those entries with it, so a person's setting survives the rename even
if they never look at the file again.

**When both files exist the panel-named one wins, entire.** Not merged: merging
two declarations of the same thing produces a state neither file describes, and
"which file am I editing" then has no answer. The legacy file is left on disk
untouched, so reverting to an older build finds it exactly as it was.

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
from scistudio.core.panels import PanelCapability
from scistudio.stability import internal
from scistudio.utils.atomic_io import atomic_write_text

logger = logging.getLogger(__name__)

__all__ = [
    "CHOICES_FILENAME",
    "LEGACY_CHOICES_FILENAME",
    "clear_choice",
    "load_choice_layers",
    "load_choices",
    "project_choices_path",
    "read_choice_layer",
    "read_choice_layers",
    "user_choices_path",
    "write_choice",
]

#: One file per concern under the library root, as ``projects.json`` and
#: ``tutorial-progress.json`` already are. Carried over under the panel naming
#: by ADR-054 spec 1 (FR-038, FR-046).
CHOICES_FILENAME = "panel-choices.json"

#: The name this file had before the rename. Still read, never written, and
#: never deleted (FR-020): a project on disk predates the build reading it.
LEGACY_CHOICES_FILENAME = "previewer-choices.json"

#: Schema version of the written file. Version 1 was one flat ``{type: id}``
#: map; version 2 is one such map per capability. Readers ignore what they do
#: not know, so this exists to make the migration legible rather than to gate
#: reads — a version-1 body is recognised by its *shape*, not by this number,
#: because a file that lost its version key must still be read correctly.
_SCHEMA_VERSION = 2


def _empty_layers() -> dict[str, dict[str, str]]:
    return {capability.value: {} for capability in PanelCapability}


@internal()
def user_choices_path(project_dir: str | Path | None) -> Path:
    """Return the user-layer choices file for *project_dir*'s library root."""
    return library_root_for_project(project_dir) / CHOICES_FILENAME


@internal()
def project_choices_path(project_dir: str | Path) -> Path:
    """Return the project-layer choices file, under ``<project>/.scistudio``."""
    return Path(project_dir) / USER_LIBRARY_DIR_NAME / CHOICES_FILENAME


def _entries(raw: object) -> dict[str, str]:
    """Return the string pairs in *raw*, skipping anything else."""
    if not isinstance(raw, dict):
        return {}
    return {
        key: value for key, value in raw.items() if isinstance(key, str) and isinstance(value, str) and key and value
    }


def _read_body(path: Path) -> dict[str, dict[str, str]] | None:
    """Return the layers in the file at *path*, or ``None`` when there is none."""
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Ignoring unreadable panel choices at %s", path.name, exc_info=True)
        return _empty_layers()
    if not isinstance(payload, dict):
        logger.warning("Ignoring panel choices at %s: expected an object", path.name)
        return _empty_layers()

    raw = payload.get("choices")
    if not isinstance(raw, dict):
        return _empty_layers()

    layers = _empty_layers()
    known = set(layers)
    if known & set(raw):
        # Version 2: one map per capability. Keys outside the capability set are
        # skipped rather than merged, the same way an unknown top-level key is.
        for capability, entries in raw.items():
            if capability in known:
                layers[capability] = _entries(entries)
        return layers

    # Version 1: one flat map, and every entry in it was recorded from the
    # preview surface, which is the displaying resolution. Reading it as the
    # displaying layer loses nothing and guesses nothing.
    layers[PanelCapability.DISPLAYING.value] = _entries(raw)
    return layers


@internal()
def read_choice_layers(path: Path) -> dict[str, dict[str, str]]:
    """Return ``{capability: {type_name: panel_id}}`` for the layer at *path*.

    Reads *path* when it exists, and otherwise the legacy
    ``previewer-choices.json`` beside it. Never raises: anything unreadable,
    unparseable, or shaped wrongly is logged once and read as an empty layer,
    and individual entries that are not a string pair are skipped so one bad key
    cannot cost the rest.
    """
    body = _read_body(path)
    if body is not None:
        return body
    legacy = path.parent / LEGACY_CHOICES_FILENAME
    if legacy != path:
        body = _read_body(legacy)
    return body if body is not None else _empty_layers()


@internal()
def read_choice_layer(
    path: Path,
    capability: PanelCapability | str = PanelCapability.DISPLAYING,
) -> dict[str, str]:
    """Return ``{type_name: panel_id}`` for one capability at *path*.

    The default is displaying, because that is the request every caller written
    before ADR-054 was making.
    """
    key = capability.value if isinstance(capability, PanelCapability) else str(capability)
    return read_choice_layers(path).get(key, {})


@internal()
def load_choices(
    project_dir: str | Path | None,
    capability: PanelCapability | str = PanelCapability.DISPLAYING,
) -> dict[str, str]:
    """Return the effective choices for *project_dir* and *capability*.

    One capability's slice of :func:`load_choice_layers`, and deliberately not a
    second implementation of the same precedence rule. It used to merge the two
    layers itself, which made the ladder true twice in one module: the tests
    naming project-over-user all reached this function while the runtime went
    through :func:`load_choice_layers`, so breaking the rule where the runtime
    reads it left every test that names the rule green (#2229). Delegating
    leaves one place where project beats user, and the tests that were pointed
    at this function now bite the code the runtime runs. It costs no extra read:
    :func:`read_choice_layer` already loaded every capability's layer to return
    one of them.
    """
    key = capability.value if isinstance(capability, PanelCapability) else str(capability)
    return load_choice_layers(project_dir).get(key, {})


@internal()
def load_choice_layers(project_dir: str | Path | None) -> dict[str, dict[str, str]]:
    """Return every capability's effective choices for *project_dir*.

    The one place the choice ladder is applied: the user layer loads
    unconditionally — it is defined by the person, not by which project happens
    to be open — and the project layer, when there is a project, overrides it
    per type within each capability.

    What :meth:`scistudio.panels.registry.PanelRegistry.set_panel_choices` is
    given, so that one read covers both capabilities rather than one read each.
    """
    layers = read_choice_layers(user_choices_path(project_dir))
    if project_dir is not None:
        project_layers = read_choice_layers(project_choices_path(project_dir))
        for capability, entries in project_layers.items():
            layers.setdefault(capability, {}).update(entries)
    return layers


def _write_layers(path: Path, layers: dict[str, dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = {
        capability.value: dict(sorted(layers.get(capability.value, {}).items())) for capability in PanelCapability
    }
    payload = {"version": _SCHEMA_VERSION, "choices": ordered}
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


@internal()
def write_choice(
    path: Path,
    target_type: str,
    previewer_id: str,
    capability: PanelCapability | str = PanelCapability.DISPLAYING,
) -> dict[str, str]:
    """Record *target_type* -> *previewer_id* for *capability* at *path*.

    Returns the capability's layer as written. Reads the existing layers first —
    including the legacy file when the panel-named one does not yet exist — so a
    concurrent edit to another type, another capability, or a preference the
    person set before the rename is carried across rather than overwritten. That
    read is what makes the migration lossless: the first write to
    ``panel-choices.json`` takes the old file's entries with it.
    """
    key = capability.value if isinstance(capability, PanelCapability) else str(capability)
    layers = read_choice_layers(path)
    layers.setdefault(key, {})[target_type] = previewer_id
    _write_layers(path, layers)
    return layers[key]


@internal()
def clear_choice(
    path: Path,
    target_type: str,
    capability: PanelCapability | str = PanelCapability.DISPLAYING,
) -> dict[str, str]:
    """Remove *target_type* from *capability*'s layer at *path*, if present.

    Returns the layer as written. Clearing a type that was never chosen is not
    an error: the caller's intent — "no choice for this type here" — already
    holds, and reporting a failure would push the caller into checking first.
    """
    key = capability.value if isinstance(capability, PanelCapability) else str(capability)
    layers = read_choice_layers(path)
    layers.setdefault(key, {}).pop(target_type, None)
    _write_layers(path, layers)
    return layers[key]
