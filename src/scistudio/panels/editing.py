"""Reading a panel, writing it back, copy-on-write, and revert (FR-024 to FR-029).

ADR-054 spec 1 T-010. Editing a panel introduces **no new mechanism**: writing
a copy into the project and letting the FR-019 tier ordering shadow the
original is what the tiers already do. What is new is the surface, and it is
here rather than in the route so the route stays an HTTP adapter over
behaviour that can be tested without one.

Four operations, and the rule each one follows:

* :func:`read_panel_source` — read any resolved panel, whichever tier it came
  from (FR-024).
* :func:`save_panel_source` — write back to **the tier the panel was resolved
  from** (FR-025). Nobody is asked where to save.
* the same function, for a core or package panel — copy the directory into the
  open project under the same id and write there, never into the core or
  package location (FR-026, FR-027). Keeping the id is the whole mechanism: the
  ordering then makes the copy take effect.
* :func:`revert_panel_override` — delete the shadowing copy, restoring whatever
  it shadowed (FR-029).

**Every write is confined, and the confinement is not the asset route's.** This
is a filesystem write driven by an HTTP request, which is the surface this
repository has already been bitten on three times (#2038, #2037, #2039 — all
unvalidated path joins or inconsistent overwrite semantics). So: the panel id
must be a single safe path segment; the destination directory must resolve
inside the project's or the user library's panels root; the file written must
be one the asset route would agree to serve; and a symlink is never followed,
written through, or copied. A path that escapes is refused, not clamped.
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from scistudio.core.panels import (
    PANEL_DECLARATION_FILENAME,
    PanelDeclarationError,
    PanelTier,
    manifest_from_declaration,
)
from scistudio.panels.assets import is_allowed_asset_suffix, is_safe_panel_id
from scistudio.panels.discovery import DiscoveredPanel, PanelDiscovery
from scistudio.stability import internal
from scistudio.utils.atomic_io import atomic_write_bytes

logger = logging.getLogger(__name__)

__all__ = [
    "EDITABLE_TIERS",
    "PanelEditError",
    "PanelNotEditableError",
    "PanelOverrideNotFoundError",
    "PanelRevert",
    "PanelSaved",
    "PanelSource",
    "confined_panel_directory",
    "read_panel_source",
    "revert_panel_override",
    "save_panel_source",
]

#: The tiers a panel can be written back to in place (FR-025). Core and package
#: panels are read-only; editing one copies it into the project (FR-026).
EDITABLE_TIERS: frozenset[PanelTier] = frozenset({PanelTier.PROJECT, PanelTier.USER})

#: The bound on a saved document. The asset route refuses to serve an oversized
#: one (``MAX_PANEL_ASSET_BYTES``), so accepting a larger write would only store
#: a panel that can never load.
MAX_PANEL_SOURCE_BYTES = 16 * 1024 * 1024


class PanelEditError(Exception):
    """A panel edit cannot be carried out. Carries the readable reason."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class PanelNotEditableError(PanelEditError):
    """There is no writable destination for this edit.

    Raised when a core or package panel would have to be copied into a project
    and no project is open. FR-026 names the open project as the destination, so
    there is no second answer to fall back to; telling the person that is better
    than depositing their edit somewhere they did not ask for.
    """


class PanelOverrideNotFoundError(PanelEditError):
    """There is nothing to revert to.

    FR-029 reverts by deleting the *shadowing* copy. A panel that shadows
    nothing has no original behind it, so deleting its directory would not be a
    revert — it would be a delete, which is a different request nobody made.
    """


@internal()
@dataclass(frozen=True)
class PanelSource:
    """One panel's editable source, and where it came from."""

    panel_id: str
    tier: PanelTier
    directory: Path
    entry: str
    source: str
    """The entry document's text."""
    declaration: str
    """The ``panel.json`` text, so an editor can show both halves of a panel."""
    editable: bool
    """Whether a save writes in place. ``False`` means a save copies into the
    project first (FR-026) — the person is not asked either way."""
    shadows: PanelTier | None
    """The tier of the panel this one shadows, or ``None``. What tells a caller
    whether a revert has anything to restore."""


@internal()
@dataclass(frozen=True)
class PanelSaved:
    """The outcome of a save."""

    panel_id: str
    tier: PanelTier
    directory: Path
    copied: bool
    """``True`` when the save created a project copy of a read-only panel."""


@internal()
@dataclass(frozen=True)
class PanelRevert:
    """The outcome of a revert."""

    panel_id: str
    removed_tier: PanelTier
    removed_directory: Path
    restored_tier: PanelTier


def confined_panel_directory(root: Path | str, panel_id: str) -> Path:
    """Return ``root/panel_id``, refusing anything that escapes *root*.

    The one join the write path performs. The id must be a single safe path
    segment, and the resolved destination must still be inside the resolved
    root — so a symlinked panel directory pointing out of the project is
    refused by the same comparison that refuses ``..``.
    """
    if not is_safe_panel_id(panel_id):
        raise PanelEditError(f"panel id {panel_id!r} is not a usable directory name")
    resolved_root = Path(root).resolve()
    candidate = (resolved_root / panel_id).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise PanelEditError(f"panel directory for {panel_id!r} escapes {resolved_root}") from exc
    return candidate


def _confined_existing_directory(panel: DiscoveredPanel) -> Path:
    """Return *panel*'s own directory, confirmed to be inside its tier root."""
    root = Path(panel.root).resolve()
    directory = Path(panel.directory).resolve()
    try:
        directory.relative_to(root)
    except ValueError as exc:
        raise PanelEditError(f"panel {panel.panel_id!r} resolves outside its tier root {root}") from exc
    return directory


def _confined_file(directory: Path, name: str, *, panel_id: str) -> Path:
    """Return ``directory/name``, confined and suffix-checked.

    The suffix check is the asset route's own allowlist: a panel directory must
    not be able to hold a file the route would refuse to serve, because that is
    a panel a person can save and then never load.
    """
    if not name or "\x00" in name:
        raise PanelEditError(f"panel {panel_id!r} names an unusable file {name!r}")
    candidate = (directory / name).resolve()
    try:
        candidate.relative_to(directory.resolve())
    except ValueError as exc:
        raise PanelEditError(f"panel {panel_id!r} names a file outside its own directory: {name!r}") from exc
    if name != PANEL_DECLARATION_FILENAME and not is_allowed_asset_suffix(candidate):
        raise PanelEditError(
            f"panel {panel_id!r} entry {name!r} is not a file type the panel asset route serves",
        )
    return candidate


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PanelEditError(f"panel file {path.name} could not be read ({exc})") from exc


def _shadowed_tier(discovery: PanelDiscovery, panel_id: str) -> PanelTier | None:
    """Return the tier of the highest-ranked panel *panel_id* shadows."""
    candidates = [entry for entry in discovery.shadowed if entry.panel_id == panel_id]
    if not candidates:
        return None
    return min(candidates, key=lambda entry: entry.tier.shadow_rank).tier


@internal()
def read_panel_source(panel: DiscoveredPanel, discovery: PanelDiscovery) -> PanelSource:
    """Read *panel*'s entry document and declaration (FR-024).

    Whichever tier the panel came from: a core panel reads exactly the way a
    project panel does, which is the property that makes "open the panel and
    change it" one action rather than four.
    """
    directory = _confined_existing_directory(panel)
    entry = panel.manifest.entry
    entry_path = _confined_file(directory, entry, panel_id=panel.panel_id)
    declaration_path = directory / PANEL_DECLARATION_FILENAME
    return PanelSource(
        panel_id=panel.panel_id,
        tier=panel.tier,
        directory=directory,
        entry=entry,
        source=_read_text(entry_path),
        declaration=_read_text(declaration_path),
        editable=panel.tier in EDITABLE_TIERS,
        shadows=_shadowed_tier(discovery, panel.panel_id),
    )


def _copy_panel_directory(source: Path, destination: Path, *, panel_id: str) -> None:
    """Copy a read-only panel directory into a writable tier (FR-026).

    Symlinks are skipped rather than followed: a core or package panel is not
    expected to contain one, and following it would copy — and then serve —
    whatever it pointed at. Only regular files are copied, and every one of them
    is confined to the destination the same way a written file is.
    """
    source = source.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    for item in sorted(source.rglob("*")):
        if item.is_symlink():
            logger.warning("Skipping symlink %s while copying panel %s", item, panel_id)
            continue
        relative = item.relative_to(source)
        target = (destination / relative).resolve()
        try:
            target.relative_to(destination.resolve())
        except ValueError:
            logger.warning("Skipping %s while copying panel %s: it escapes the destination", item, panel_id)
            continue
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif item.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(item, target)


@internal()
def save_panel_source(
    panel: DiscoveredPanel,
    source: str,
    *,
    project_panels_root: Path | None,
    declaration: str | None = None,
) -> PanelSaved:
    """Save an edit to *panel* (FR-025, FR-026, FR-027).

    The destination is decided here and nowhere else, from the tier the panel
    resolved from:

    * project or user library — written back in place, with no second copy made;
    * core or package — copied into the open project under the same id, and the
      original is not written.

    Args:
        panel: The resolved panel being edited.
        source: The new entry-document text.
        project_panels_root: The open project's panels root, or ``None`` when no
            project is open. Only consulted for a read-only panel.
        declaration: An optional replacement ``panel.json``. It must parse and
            must keep the panel's id: FR-027 is what makes a copy take effect,
            so a save that renamed the panel would leave the original visible
            and the edit apparently lost.

    Raises:
        PanelNotEditableError: A read-only panel is being edited with no project
            open.
        PanelEditError: The declaration does not parse, changes the id, or the
            destination cannot be confined.
    """
    if len(source.encode("utf-8")) > MAX_PANEL_SOURCE_BYTES:
        raise PanelEditError(
            f"panel document is larger than the {MAX_PANEL_SOURCE_BYTES}-byte limit the asset route serves"
        )
    if declaration is not None:
        _validate_declaration(declaration, panel_id=panel.panel_id)

    copied = False
    if panel.tier in EDITABLE_TIERS:
        directory = _confined_existing_directory(panel)
        tier = panel.tier
    else:
        if project_panels_root is None:
            raise PanelNotEditableError(
                f"panel {panel.panel_id!r} belongs to the {panel.tier.value} tier and is read-only; "
                "editing it copies it into the open project, and no project is open"
            )
        directory = confined_panel_directory(project_panels_root, panel.panel_id)
        if not directory.exists():
            _copy_panel_directory(panel.directory, directory, panel_id=panel.panel_id)
            copied = True
        tier = PanelTier.PROJECT

    entry_path = _confined_file(directory, panel.manifest.entry, panel_id=panel.panel_id)
    entry_path.parent.mkdir(parents=True, exist_ok=True)
    # Bytes rather than text: a panel document is source, and the platform must
    # not rewrite its line endings on the way to disk. A person who saves a
    # document on Windows and reads it back on a colleague's machine has to see
    # what they wrote, not what the runtime's newline translation made of it.
    atomic_write_bytes(entry_path, source.encode("utf-8"))
    if declaration is not None:
        atomic_write_bytes(directory / PANEL_DECLARATION_FILENAME, declaration.encode("utf-8"))
    logger.info("Saved panel %s to the %s tier at %s (copied=%s)", panel.panel_id, tier.value, directory, copied)
    return PanelSaved(panel_id=panel.panel_id, tier=tier, directory=directory, copied=copied)


def _validate_declaration(declaration: str, *, panel_id: str) -> None:
    """Refuse a replacement ``panel.json`` that will not parse or renames the panel."""
    try:
        raw = json.loads(declaration)
    except ValueError as exc:
        raise PanelEditError(f"panel declaration is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise PanelEditError("panel declaration must be a JSON object")
    try:
        manifest = manifest_from_declaration(raw, directory=Path(panel_id))
    except PanelDeclarationError as exc:
        raise PanelEditError(exc.message) from exc
    if manifest.panel_id != panel_id:
        raise PanelEditError(
            f"a saved declaration must keep the panel id {panel_id!r}; it declares {manifest.panel_id!r}. "
            "The id is what makes a project copy shadow the panel it was copied from (FR-027)."
        )


@internal()
def revert_panel_override(panel: DiscoveredPanel, discovery: PanelDiscovery) -> PanelRevert:
    """Delete *panel*'s shadowing copy, restoring what it shadowed (FR-029).

    Refuses a panel that shadows nothing: without an original behind it, this is
    a delete rather than a revert, and FR-029 describes the second.

    Raises:
        PanelOverrideNotFoundError: The panel is not in an editable tier, or it
            shadows nothing.
        PanelEditError: The directory cannot be confined to its tier root.
    """
    if panel.tier not in EDITABLE_TIERS:
        raise PanelOverrideNotFoundError(
            f"panel {panel.panel_id!r} resolves from the {panel.tier.value} tier, which holds no override to revert"
        )
    restored = _shadowed_tier(discovery, panel.panel_id)
    if restored is None:
        raise PanelOverrideNotFoundError(
            f"panel {panel.panel_id!r} shadows nothing, so there is nothing to revert to. "
            "Deleting the only copy of a panel is a different request."
        )
    directory = _confined_existing_directory(panel)
    if Path(panel.directory).is_symlink():
        raise PanelEditError(f"panel {panel.panel_id!r} is a symlink; refusing to delete through it")
    shutil.rmtree(directory)
    logger.info("Reverted panel %s: removed %s, restoring the %s tier", panel.panel_id, directory, restored.value)
    return PanelRevert(
        panel_id=panel.panel_id,
        removed_tier=panel.tier,
        removed_directory=directory,
        restored_tier=restored,
    )
