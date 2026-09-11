"""The shared project-file write path: atomic write, change event, registry reload."""
# Maintainer context (kept outside generated API documentation):
# The shared project-file write path: atomic write, change event, registry reload.
#
# ADR-036 §3.2/§3.5 and ADR-045 define what a first-party write to a project file
# does: the bytes land atomically, the FS watcher is told the change is ours, the
# file's state version advances, a ``file.changed`` event reaches every connected
# UI, and a clean save under a drop-in tier (``blocks/``, ``types/``) rebuilds the
# registries. That sequence used to live inside the editor's
# ``PUT /api/projects/{id}/file`` handler, which meant a second writer could only
# reach it by re-implementing it — the WebMCP prototype's bare ``write_text`` fork
# that left the open UI stale.
#
# ADR-055 Spec 2 FR-005 (#2279) extracts it here so the editor route and the
# external-audience MCP author tools run the same code:
#
# * :func:`write_project_file` is the write the route calls.
# * :func:`delete_project_path` and :func:`move_project_path` are the structural
#   operations the author tools add, built from the same event and reload pieces.
# * :class:`ProjectFileService` is the same path bound to the runtime, exposed to
#   MCP tools as ``MCPContext.project_files``. The ``ai`` layer may not import
#   ``api`` (import-linter "AI must not depend on api"), so the service confines
#   every target to the active project itself and returns plain dicts.
#
# The optional expected ``state_version`` (#2279 owner decision 5) turns a write
# based on a stale read into an explicit :class:`FileWriteConflictError` instead of a
# silent overwrite. The editor route passes it only when its request carries one,
# so its observable behavior is unchanged.
# Development references: #2279, ADR-036, ADR-045, ADR-055, FR-005, Spec 2.

from __future__ import annotations

import asyncio
import contextlib
import errno
import logging
import os
import shutil
import stat
import tempfile
import weakref
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scistudio.api.file_contracts import FILE_CHANGED_EVENT_TYPE, FILE_ENTITY_CLASS
from scistudio.core.dropins import BLOCKS_DIR_NAME, TYPES_DIR_NAME
from scistudio.engine.events import EngineEvent

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from scistudio.api.runtime import ApiRuntime

logger = logging.getLogger(__name__)

BLOCKS_RELOADED_EVENT_TYPE: str = "blocks.reloaded"
"""WS event the palette listens on after a registry-invalidating save."""
# Development references: ADR-036.

DIRECTORY_OPERATION_FILE_LIMIT: int = 2000
"""Most files one directory delete or move may touch.

Each moved or deleted file emits its own ``file.changed`` event, so the bound
keeps one tool call from flooding every connected UI. Larger reorganizations
belong to ``run_command``.
"""

AGENT_SOURCE: str = "agent"
"""Change source recorded for writes made through the MCP author tools."""
# Development references: ADR-045.


class FileWriteConflictError(Exception):
    """The file is not in the state the caller based its write on.

    ``condition`` names the reason: ``stale_version`` (changed since the
    caller's read), ``missing_file``, ``already_exists``, ``missing_parent``,
    ``is_directory``, ``directory_not_empty``, or ``too_many_entries``.
    """

    def __init__(
        self,
        condition: str,
        message: str,
        *,
        entity_id: str,
        expected_version: int | None = None,
        current_version: int | None = None,
    ) -> None:
        super().__init__(message)
        self.condition = condition
        self.message = message
        self.entity_id = entity_id
        self.expected_version = expected_version
        self.current_version = current_version

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": "file_write_conflict",
            "condition": self.condition,
            "message": self.message,
            "entity_id": self.entity_id,
            "expected_state_version": self.expected_version,
            "current_state_version": self.current_version,
        }


class ProjectFileWriteError(Exception):
    """The disk operation itself failed; the message is the route's 500 detail."""


@dataclass(frozen=True)
class FileChange:
    """One emitted ``file.changed`` event and the file state it describes."""

    entity_id: str
    kind: str
    version: int
    payload: dict[str, Any]
    mtime: float | None = None
    size: int | None = None
    registry_refreshed: bool = False


# ---------------------------------------------------------------------------
# Path classification.
# ---------------------------------------------------------------------------


def project_relative_entity_id(project_root: Path, target: Path) -> str:
    """Return the file entity id for a sandboxed project file."""
    # Development references: ADR-045.
    try:
        relative = target.relative_to(project_root)
    except ValueError:
        relative = Path(os.path.relpath(target, project_root))
    return str(relative).replace("\\", "/")


def project_dropin_dir(project_root: Path | None, target: Path) -> str | None:
    """Return the drop-in tier child dir ``target`` sits in, else ``None``.

    ``<project>/types`` is a drop-in tier exactly as
    ``<project>/blocks`` is (:mod:`scistudio.core.dropins`), so a save under it
    invalidates the registries the same way. Uses ``Path.relative_to`` to avoid
    string-prefix gotchas on Windows.
    """
    # Development references: ADR-053, FR-062.
    if project_root is None or target.suffix.lower() != ".py":
        return None
    try:
        rel = target.relative_to(project_root)
    except ValueError:
        return None
    parts = rel.parts
    if len(parts) >= 2 and parts[0] in (BLOCKS_DIR_NAME, TYPES_DIR_NAME):
        return parts[0]
    return None


def is_under_project_blocks_dir(project_root: Path | None, target: Path) -> bool:
    """True when ``target`` is a ``.py`` file inside ``<project>/blocks``."""
    return project_dropin_dir(project_root, target) == BLOCKS_DIR_NAME


def confine_to_project(project_root: Path, target: Path, *, follow_final: bool = True) -> Path:
    """Resolve *target* and reject it when it escapes *project_root*.

    The same sanitiser as the editor route (CodeQL ``py/path-injection``): the
    resolved candidate is the root itself or starts with the root plus a
    separator, so a sibling such as ``<root>-other`` is an escape, and so is a
    different drive on Windows.

    With ``follow_final=False`` only the parent directories are resolved, so a
    *target* that is itself a symlink or junction names the link, not what it
    points to. Delete and move act on the path they are given (lstat
    semantics), so they confine that path.
    """
    # Maintainer context:
    # With ``follow_final=False`` only the parent directories are resolved, so a
    # *target* that is itself a symlink or junction names the link, not what it
    # points to. Delete and move act on the path they are given (lstat
    # semantics), so they confine that path (audit AU3 P1-1).
    # Development references: #2279.
    root = os.path.realpath(project_root)
    joined = os.path.normpath(os.path.join(root, target))
    if follow_final:
        candidate = os.path.realpath(joined)
    else:
        head, tail = os.path.split(joined)
        # normpath is a no-op here; it keeps the value a normalization result for the guard below.
        candidate = os.path.normpath(os.path.join(os.path.realpath(head), tail)) if tail else os.path.realpath(joined)
    if candidate == root:
        return Path(root)
    # A single startswith guard on the normalized path, the form CodeQL's
    # py/path-injection query recognizes; nothing below touches an unchecked value.
    prefix = root if root.endswith(os.sep) else root + os.sep
    if not candidate.startswith(prefix):
        raise PermissionError("Path escapes project root")
    return Path(candidate)


# ---------------------------------------------------------------------------
# State versions.
# ---------------------------------------------------------------------------


def _disk_mtime_ns(path: Path) -> int:
    try:
        return int(path.stat().st_mtime_ns)
    except OSError:
        return 0


def observed_entity_version(runtime: ApiRuntime, entity_id: str, target: Path) -> int:
    """Return the file's state version as a write would see it, without advancing it.

    Compare-only. Advancing the version here
    would also record the new disk mtime as already seen, and the watcher emits
    ``file.changed`` only when the disk is newer than the last known disk version
    so it would drop the external edit as a delayed echo and the
    open UI would never learn of it. Only a real write through the shared path
    advances a version. An external edit the watcher has not delivered yet (disk
    mtime newer than the cached disk version) is projected as the version the
    watcher will assign when it does: current + 1. A conflict check therefore
    still sees it, and a write based on the projected version lines up with it.
    """
    # Maintainer context:
    # Compare-only (audits AU3 P2-1 / AU4 P2-2). Advancing the version here
    #    would also record the new disk mtime as already seen, and the watcher emits
    #    ``file.changed`` only when the disk is newer than the last known disk version
    # so it would drop the external edit as a delayed echo and the
    #    open UI would never learn of it. Only a real write through the shared path
    #    advances a version. An external edit the watcher has not delivered yet (disk
    #    mtime newer than the cached disk version) is projected as the version the
    #    watcher will assign when it does: current + 1. A conflict check therefore
    #    still sees it, and a write based on the projected version lines up with it.
    # Development references: #2279, ADR-045.
    current = runtime.current_entity_version(FILE_ENTITY_CLASS, entity_id, path=target)
    cached_disk = runtime.current_entity_disk_version(FILE_ENTITY_CLASS, entity_id, path=target)
    disk = _disk_mtime_ns(target)
    return current + 1 if disk and disk > cached_disk else current


def absorb_unobserved_disk_edit(runtime: ApiRuntime, entity_id: str, target: Path) -> None:
    """Advance the version past an external edit the watcher has not delivered -- writes only.

    A write supersedes that pending edit (its own ``file.changed`` follows), and
    advancing first keeps the written version one past the version the writer's
    conflict check was based on. Reads never call this (see
    :func:`observed_entity_version`).
    """
    runtime.current_entity_version(FILE_ENTITY_CLASS, entity_id, path=target)  # seeds a first observation
    cached_disk = runtime.current_entity_disk_version(FILE_ENTITY_CLASS, entity_id, path=target)
    disk = _disk_mtime_ns(target)
    if disk and disk > cached_disk:
        runtime.bump_entity_version(FILE_ENTITY_CLASS, entity_id, path=target)


def check_write_preconditions(
    runtime: ApiRuntime,
    *,
    entity_id: str,
    target: Path,
    expected_state_version: int | None = None,
    create_only: bool = False,
    require_existing: bool = False,
) -> tuple[bool, str]:
    """Raise :class:`FileWriteConflictError` unless the write may proceed.

    Returns ``(existed, kind)`` for the event payload. With every option at
    its default this never raises, which is how the editor route stays
    unchanged.
    """
    existed = target.exists()
    if create_only and existed:
        raise FileWriteConflictError(
            "already_exists",
            f"{entity_id} already exists; write with mode='overwrite' to replace it.",
            entity_id=entity_id,
        )
    if require_existing and not existed:
        raise FileWriteConflictError("missing_file", f"{entity_id} does not exist.", entity_id=entity_id)
    if expected_state_version is not None:
        if not existed and expected_state_version > 0:
            raise FileWriteConflictError(
                "missing_file",
                f"{entity_id} no longer exists; it was deleted after state version {expected_state_version}.",
                entity_id=entity_id,
                expected_version=expected_state_version,
                current_version=0,
            )
        current = observed_entity_version(runtime, entity_id, target)
        if current != expected_state_version:
            raise FileWriteConflictError(
                "stale_version",
                (
                    f"{entity_id} changed since state version {expected_state_version} "
                    f"(now {current}). Re-read it and base the write on the current content."
                ),
                entity_id=entity_id,
                expected_version=expected_state_version,
                current_version=current,
            )
    return existed, ("modified" if existed else "created")


# ---------------------------------------------------------------------------
# Serialization.
# ---------------------------------------------------------------------------

_PROJECT_LOCKS: weakref.WeakValueDictionary[tuple[int, str], asyncio.Lock] = weakref.WeakValueDictionary()


@contextlib.asynccontextmanager
async def project_mutation_lock(project_root: Path) -> AsyncIterator[None]:
    """Serialize the mutations of one project that go through the shared write path.

    The precondition check (expected ``state_version``, create-only, missing
    file), the disk change, and the version advance must form one critical
    section. Otherwise two writes based on the same version can both pass the
    check before either lands, and one silently overwrites the other (Codex
    review on). One lock per project, per event loop, also orders a file
    write against a delete or move of a directory that holds the file. The
    lint-gated registry rebuild after a drop-in save runs inside it, because it
    must see the file that was written.
    """
    # Development references: #2292.
    key = (id(asyncio.get_running_loop()), os.path.normcase(str(project_root)))
    lock = _PROJECT_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _PROJECT_LOCKS[key] = lock
    async with lock:
        yield


# ---------------------------------------------------------------------------
# The write sequence.
# ---------------------------------------------------------------------------


def _mark_watcher_self_write(target: Path) -> None:
    """Best-effort FS-watcher echo suppression."""
    # Development references: ADR-034.
    from scistudio.api.routes.workflow_watcher import mark_self_write

    try:
        mark_self_write(target)
    except Exception:
        # Failure just means the watcher echoes a modify event the frontend
        # then ignores via existing dedup.
        logger.debug("mark_self_write raised", exc_info=True)


def atomic_write_bytes(runtime: ApiRuntime, *, target: Path, entity_id: str, kind: str, encoded: bytes) -> None:
    """Replace *target* with *encoded* atomically.

    Temp file in the destination's directory + ``os.replace`` — atomic on
    POSIX and Windows. Any failure before the rename leaves the destination
    untouched and removes the temp file. The temp file carries a fixed
    ``.tmp`` suffix so it is never itself a drop-in while it exists: the
    directory may be ``blocks/`` or ``types/``, which are globbed for ``*.py``
    and executed on every scan.

    The watcher is marked before the rename, so the call lands before the FS
    event fires, and again after it, so the ``(path, mtime, size)`` triple
    matches the file the watcher will see.
    """
    # Maintainer context:
    # Temp file in the destination's directory + ``os.replace`` — atomic on
    # POSIX and Windows. Any failure before the rename leaves the destination
    # untouched and removes the temp file. The temp file carries a fixed
    # ``.tmp`` suffix so it is never itself a drop-in while it exists: the
    # directory may be ``blocks/`` or ``types/``, which are globbed for ``*.py``
    # and executed on every scan (
    # P2-2).
    # Development references: adr-053-spec1-write-path.
    tmp_fd, tmp_path = tempfile.mkstemp(prefix=".__scistudio_write_", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(tmp_fd, "wb") as tmp_file:
            tmp_file.write(encoded)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        runtime.mark_entity_first_party_write(
            FILE_ENTITY_CLASS,
            entity_id,
            runtime.current_entity_version(FILE_ENTITY_CLASS, entity_id, path=target),
            path=target,
            kind=kind,
            pending=True,
        )
        _mark_watcher_self_write(target)
        os.replace(tmp_path, target)
        _mark_watcher_self_write(target)
    except Exception as exc:
        # Not ``except OSError``: a filename carrying an embedded NUL makes
        # ``os.replace`` raise ``ValueError``, which would otherwise leave the
        # temp file behind for good.
        try:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except OSError:
            pass
        raise ProjectFileWriteError(f"write failed: {exc}") from exc


async def emit_file_changed(
    runtime: ApiRuntime,
    *,
    entity_id: str,
    target: Path,
    project_id: str,
    source: str,
    source_id: str | None,
    kind: str,
    changed_by: str | None,
) -> dict[str, Any]:
    """Advance the file's version and broadcast the ``file.changed`` event."""
    # Development references: ADR-045.
    version = runtime.bump_entity_version(FILE_ENTITY_CLASS, entity_id, path=target)
    runtime.mark_entity_first_party_write(FILE_ENTITY_CLASS, entity_id, version, path=target, kind=kind)
    payload = runtime.versioned_change_payload(
        entity_class=FILE_ENTITY_CLASS,
        entity_id=entity_id,
        version=version,
        source=source,
        source_id=source_id,
        kind=kind,
        project_id=project_id,
        path=entity_id,
        changed_by=changed_by,
    )
    await runtime.event_bus.emit(EngineEvent(event_type=FILE_CHANGED_EVENT_TYPE, data=payload))
    return payload


def _lint_clean(content: str, filename: str) -> bool:
    """True when ruff reports nothing for *content* (missing ruff counts as clean)."""
    # Imported lazily to keep lint config out of module import time.
    from scistudio.api.routes.lint import lint_python_source

    try:
        lint_result = lint_python_source(content, filename=filename)
    except Exception:
        logger.debug("blocks-reload hook: lint raised, skipping reload", exc_info=True)
        return False
    if lint_result.diagnostics:
        # FR-012: counts only — the file name is an argument of the call.
        logger.info("blocks-reload hook: %d lint diagnostic(s); skipping reload", len(lint_result.diagnostics))
        return False
    # ruff missing / timeout returns an empty diagnostics list with a
    # non-empty ``note`` — "no errors observed", same as the editor.
    return True


async def refresh_registries_and_broadcast(runtime: ApiRuntime, *, reloaded: list[str], path: Path) -> bool:
    """Rebuild every registry and broadcast ``blocks.reloaded``; True on success.

    rebuild every registry the change invalidates, not just
    blocks. Exceptions are swallowed because the file operation itself already
    succeeded — losing the palette refresh is annoying, surfacing a 500 is worse.
    """
    # Development references: ADR-053, FR-062.
    before = set(runtime.block_registry.all_specs().keys())
    try:
        runtime.refresh_all_registries()
    except Exception:
        logger.exception("blocks-reload hook: refresh_all_registries() raised")
        return False
    after = set(runtime.block_registry.all_specs().keys())
    payload = {
        "added": sorted(after - before),
        "removed": sorted(before - after),
        "reloaded": reloaded,
        "path": str(path),
    }
    try:
        await runtime.event_bus.emit(EngineEvent(event_type=BLOCKS_RELOADED_EVENT_TYPE, data=payload))
    except Exception:
        logger.exception("blocks-reload hook: event_bus.emit raised")
    return True


async def maybe_reload_blocks_after_save(runtime: ApiRuntime, target: Path, content: str) -> bool:
    """If ``target`` is a lint-clean ``blocks/*.py`` or ``types/*.py``, reload.

    Lint failure keeps the registry stable — the file is saved
    but not loaded, so a broken module never poisons the palette. Returns
    whether the registries were rebuilt.
    """
    # Development references: ADR-036.
    active = runtime.active_project
    project_root = Path(active.path) if active is not None else None
    if project_dropin_dir(project_root, target) is None:
        return False
    # ruff runs as a subprocess; keep it off the event loop.
    if not await asyncio.to_thread(_lint_clean, content, target.name):
        return False
    # No per-spec staleness tracking exists, so the saved file's name is the
    # canonical reloaded target downstream consumers scope the toast to.
    return await refresh_registries_and_broadcast(runtime, reloaded=[target.name], path=target)


async def write_project_file(
    runtime: ApiRuntime,
    *,
    project_id: str,
    project_root: Path,
    target: Path,
    content: str | bytes,
    source: str,
    source_id: str | None,
    changed_by: str | None,
    expected_state_version: int | None = None,
    create_only: bool = False,
    require_existing: bool = False,
) -> FileChange:
    """Write *content* to the already-sandboxed *target* through the full path.

    Order matches the pre-extraction route exactly: preconditions, atomic
    write, lint-gated registry reload, stat, then the ``file.changed`` event,
    all under :func:`project_mutation_lock`, so two writes based on the same
    state version cannot both succeed.
    Raises :class:`FileWriteConflictError` for a refused precondition and
    :class:`ProjectFileWriteError` when the disk operation fails.

    *content* may be ``bytes`` (the seam's ``write_project_file`` passes
    bytes): it is written as given, and only UTF-8 text can trigger the
    lint-gated registry reload.
    """
    # Development references: #2328 (bytes through the shared write path).
    encoded = content if isinstance(content, bytes) else content.encode("utf-8")
    if isinstance(content, str):
        text: str | None = content
    else:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            text = None  # not text, so never a lint-clean drop-in module
    entity_id = project_relative_entity_id(project_root, target)
    async with project_mutation_lock(project_root):
        _, kind = check_write_preconditions(
            runtime,
            entity_id=entity_id,
            target=target,
            expected_state_version=expected_state_version,
            create_only=create_only,
            require_existing=require_existing,
        )
        absorb_unobserved_disk_edit(runtime, entity_id, target)
        # Disk work (write, fsync, replace) runs in a worker thread so the event loop stays free.
        await asyncio.to_thread(
            atomic_write_bytes, runtime, target=target, entity_id=entity_id, kind=kind, encoded=encoded
        )
        refreshed = await maybe_reload_blocks_after_save(runtime, target, text) if text is not None else False
        try:
            stat = target.stat()
        except OSError as exc:
            raise ProjectFileWriteError(f"post-write stat failed: {exc}") from exc
        payload = await emit_file_changed(
            runtime,
            entity_id=entity_id,
            target=target,
            project_id=project_id,
            source=source,
            source_id=source_id,
            kind=kind,
            changed_by=changed_by,
        )
    return FileChange(
        entity_id=entity_id,
        kind=str(payload["kind"]),
        version=int(payload["version"]),
        payload=payload,
        mtime=stat.st_mtime,
        size=stat.st_size,
        registry_refreshed=refreshed,
    )


# ---------------------------------------------------------------------------
# Structural operations (author tools only).
# ---------------------------------------------------------------------------


_FILE_ATTRIBUTE_REPARSE_POINT = 0x400
# IO_REPARSE_TAG_MOUNT_POINT (a junction) and IO_REPARSE_TAG_SYMLINK. Other
# reparse points (cloud-file placeholders, for example) are ordinary entries.
_LINK_REPARSE_TAGS = frozenset({0xA0000003, 0xA000000C})


def is_link(path: Path) -> bool:
    """True for a symlink or a Windows junction, judged without following it.

    ``os.path.islink`` misses junctions before Python 3.12, and a junction is
    the kind of link anyone can create on Windows without privilege.
    """
    try:
        info = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    attributes = getattr(info, "st_file_attributes", 0)
    return bool(attributes & _FILE_ATTRIBUTE_REPARSE_POINT) and getattr(info, "st_reparse_tag", 0) in _LINK_REPARSE_TAGS


def remove_link(path: Path) -> None:
    """Remove a symlink or junction itself; what it points to is untouched."""
    try:
        os.unlink(path)
    except (IsADirectoryError, PermissionError):
        # A Windows directory symlink or junction goes with rmdir, which removes
        # the reparse point, not the directory it names.
        os.rmdir(path)


def files_under(directory: Path, *, limit: int = DIRECTORY_OPERATION_FILE_LIMIT) -> list[Path]:
    """Every file below *directory*, refusing a tree larger than *limit*.

    A symlink or junction inside the tree counts as one entry and is never
    descended: a tree operation acts on the link, not on what it points to.
    """
    found: list[Path] = []
    pending = [directory]
    while pending:
        with os.scandir(pending.pop()) as entries:
            for entry in entries:
                path = Path(entry.path)
                if not is_link(path) and entry.is_dir(follow_symlinks=False):
                    pending.append(path)
                    continue
                found.append(path)
                if len(found) > limit:
                    raise FileWriteConflictError(
                        "too_many_entries",
                        (
                            f"{directory.name}/ holds more than {limit} files; one author-tool call "
                            "touches at most that many. Use run_command for bulk reorganization."
                        ),
                        entity_id=directory.name,
                    )
    return sorted(found)


def _has_entries(directory: Path) -> bool:
    with os.scandir(directory) as entries:
        return any(True for _ in entries)


def _remove_tree(directory: Path) -> None:
    """Delete *directory* bottom-up, removing links as links (never their targets)."""
    with os.scandir(directory) as entries:
        children = [(Path(entry.path), entry.is_dir(follow_symlinks=False)) for entry in entries]
    for path, is_directory in children:
        if is_link(path):
            remove_link(path)
        elif is_directory:
            _remove_tree(path)
        else:
            try:
                os.unlink(path)
            except PermissionError:
                # A read-only file on Windows.
                os.chmod(path, stat.S_IWRITE)
                os.unlink(path)
    os.rmdir(directory)


def _delete_on_disk(target: Path, *, link: bool) -> None:
    if link:
        remove_link(target)
    elif target.is_dir():
        _remove_tree(target)
    else:
        os.unlink(target)


def _move_on_disk(source_path: Path, destination: Path) -> None:
    """Rename *source_path*; a link is renamed as a link (``os.replace`` does not follow it)."""
    try:
        os.replace(source_path, destination)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        shutil.move(str(source_path), str(destination))


async def delete_project_path(
    runtime: ApiRuntime,
    *,
    project_id: str,
    project_root: Path,
    target: Path,
    recursive: bool,
    source: str,
    source_id: str | None,
    changed_by: str | None,
    expected_state_version: int | None = None,
) -> tuple[list[FileChange], bool]:
    """Delete a file, directory, or link and emit a ``deleted`` event per removed entry.

    A symlink or junction is removed as a link and what it points to is
    untouched (lstat semantics); a directory tree is
    removed without ever descending through a link inside it. Returns
    ``(changes, registry_refreshed)``. Deleting a drop-in ``.py`` rebuilds the
    registries without a lint gate — there is no longer a module that could
    poison them. The walk and the removal run in a worker thread.
    """
    # Maintainer context:
    # A symlink or junction is removed as a link and what it points to is
    # untouched (lstat semantics,  audit AU3 P1-1); a directory tree is
    # removed without ever descending through a link inside it. Returns
    # ``(changes, registry_refreshed)``. Deleting a drop-in ``.py`` rebuilds the
    # registries without a lint gate — there is no longer a module that could
    # poison them. The walk and the removal run in a worker thread.
    # Development references: #2279.
    entity_id = project_relative_entity_id(project_root, target)
    async with project_mutation_lock(project_root):
        if not os.path.lexists(target):
            raise FileWriteConflictError("missing_file", f"{entity_id} does not exist.", entity_id=entity_id)
        link = is_link(target)
        if not link and target.is_dir():
            files = await asyncio.to_thread(files_under, target)
            if not recursive and await asyncio.to_thread(_has_entries, target):
                raise FileWriteConflictError(
                    "directory_not_empty",
                    f"{entity_id}/ is not empty; pass recursive=true to delete it with its contents.",
                    entity_id=entity_id,
                )
        else:
            files = [target]
            if expected_state_version is not None and not link:
                check_write_preconditions(
                    runtime, entity_id=entity_id, target=target, expected_state_version=expected_state_version
                )
        # Seed each version while the entry still exists so the ``deleted`` event
        # advances it rather than starting from the "absent" baseline.
        file_ids = [(path, project_relative_entity_id(project_root, path)) for path in files]
        for path, file_id in file_ids:
            absorb_unobserved_disk_edit(runtime, file_id, path)
        try:
            await asyncio.to_thread(_delete_on_disk, target, link=link)
        except Exception as exc:
            raise ProjectFileWriteError(f"delete failed: {exc}") from exc

        changes: list[FileChange] = []
        for path, file_id in file_ids:
            payload = await emit_file_changed(
                runtime,
                entity_id=file_id,
                target=path,
                project_id=project_id,
                source=source,
                source_id=source_id,
                kind="deleted",
                changed_by=changed_by,
            )
            changes.append(
                FileChange(entity_id=file_id, kind="deleted", version=int(payload["version"]), payload=payload)
            )
        refreshed = False
        if any(project_dropin_dir(project_root, path) is not None for path in files):
            refreshed = await refresh_registries_and_broadcast(runtime, reloaded=[target.name], path=target)
    return changes, refreshed


async def move_project_path(
    runtime: ApiRuntime,
    *,
    project_id: str,
    project_root: Path,
    source_path: Path,
    destination: Path,
    source: str,
    source_id: str | None,
    changed_by: str | None,
    expected_state_version: int | None = None,
) -> tuple[list[FileChange], bool]:
    """Rename or move a file, directory, or link; never overwrites.

    A symlink or junction is moved as a link. Each
    moved entry emits ``deleted`` at its old entity id and ``created`` at the
    new one, so an open editor tab learns its file went away. A move that
    touches a drop-in ``.py`` rebuilds the registries, unless a moved-in module
    fails lint (keeps the registry stable in that case). Disk work
    and lint run in a worker thread.
    """
    # Maintainer context:
    # A symlink or junction is moved as a link (audit AU3 P1-1). Each
    # moved entry emits ``deleted`` at its old entity id and ``created`` at the
    # new one, so an open editor tab learns its file went away. A move that
    # touches a drop-in ``.py`` rebuilds the registries, unless a moved-in module
    # fails lint (keeps the registry stable in that case). Disk work
    # and lint run in a worker thread.
    # Development references: #2279, ADR-036.
    source_id_rel = project_relative_entity_id(project_root, source_path)
    dest_id_rel = project_relative_entity_id(project_root, destination)
    async with project_mutation_lock(project_root):
        if not os.path.lexists(source_path):
            raise FileWriteConflictError("missing_file", f"{source_id_rel} does not exist.", entity_id=source_id_rel)
        if os.path.lexists(destination):
            raise FileWriteConflictError(
                "already_exists",
                f"{dest_id_rel} already exists; moves never overwrite. Delete it first or pick another name.",
                entity_id=dest_id_rel,
            )
        if not destination.parent.is_dir():
            raise FileWriteConflictError(
                "missing_parent",
                f"The parent directory of {dest_id_rel} does not exist.",
                entity_id=dest_id_rel,
            )
        link = is_link(source_path)
        if not link and source_path.is_dir():
            pairs = [
                (path, destination / path.relative_to(source_path))
                for path in await asyncio.to_thread(files_under, source_path)
            ]
        else:
            if expected_state_version is not None and not link:
                check_write_preconditions(
                    runtime, entity_id=source_id_rel, target=source_path, expected_state_version=expected_state_version
                )
            pairs = [(source_path, destination)]
        for old, _new in pairs:
            absorb_unobserved_disk_edit(runtime, project_relative_entity_id(project_root, old), old)
        try:
            await asyncio.to_thread(_move_on_disk, source_path, destination)
        except Exception as exc:
            raise ProjectFileWriteError(f"move failed: {exc}") from exc

        changes: list[FileChange] = []
        for old, new in pairs:
            _mark_watcher_self_write(new)
            for path, kind in ((old, "deleted"), (new, "created")):
                file_id = project_relative_entity_id(project_root, path)
                payload = await emit_file_changed(
                    runtime,
                    entity_id=file_id,
                    target=path,
                    project_id=project_id,
                    source=source,
                    source_id=source_id,
                    kind=kind,
                    changed_by=changed_by,
                )
                changes.append(
                    FileChange(entity_id=file_id, kind=kind, version=int(payload["version"]), payload=payload)
                )

        refreshed = False
        touched = [
            path for old, new in pairs for path in (old, new) if project_dropin_dir(project_root, path) is not None
        ]
        if touched:
            moved_in = [
                new for _old, new in pairs if project_dropin_dir(project_root, new) is not None and not is_link(new)
            ]
            if await asyncio.to_thread(_all_lint_clean, moved_in):
                refreshed = await refresh_registries_and_broadcast(
                    runtime, reloaded=[destination.name], path=destination
                )
    return changes, refreshed


def _read_text_or_empty(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _all_lint_clean(paths: list[Path]) -> bool:
    return all(_lint_clean(_read_text_or_empty(path), path.name) for path in paths)


# ---------------------------------------------------------------------------
# The service the MCP author tools reach through ``MCPContext.project_files``.
# ---------------------------------------------------------------------------


def _change_summary(change: FileChange) -> dict[str, Any]:
    return {"entity_id": change.entity_id, "kind": change.kind, "state_version": change.version}


class ProjectFileService:
    """The shared write path bound to the live runtime.

    Every method takes absolute targets, re-confines them to the ACTIVE
    project's root (the author tools confine too; this is the second line),
    and returns a plain dict whose ``status`` is ``"ok"`` or ``"conflict"``.
    Disk failures raise :class:`ProjectFileWriteError`. Blacklist and
    hook-parity policy stays in the tools — this service is the editor's write
    semantics, nothing more. ``write_text`` writes through a link to the file it
    names; ``delete`` and ``move`` act on a link itself. Preconditions are checked
    before any parent directory is created, so a refused call leaves nothing new
    behind.
    """

    # Development references: ADR-055, FR-005, Spec 2.

    def __init__(self, runtime: ApiRuntime) -> None:
        self._runtime = runtime

    def _active(self) -> tuple[str, Path]:
        project = self._runtime.active_project
        if project is None:
            raise RuntimeError("No project is currently open. Open a project before writing project files.")
        return project.id, Path(os.path.realpath(project.path))

    def state_version(self, target: Path) -> int | None:
        """Current state version of a project file (compare-only), or ``None`` outside the project."""
        project = self._runtime.active_project
        if project is None:
            return None
        root = Path(os.path.realpath(project.path))
        try:
            confined = confine_to_project(root, target)
        except PermissionError:
            return None
        if confined.is_dir():
            return None
        return observed_entity_version(self._runtime, project_relative_entity_id(root, confined), confined)

    async def write_text(
        self,
        target: Path,
        content: str | bytes,
        *,
        expected_state_version: int | None = None,
        create_only: bool = False,
        require_existing: bool = False,
        create_parents: bool = False,
        changed_by: str = "mcp.workspace",
    ) -> dict[str, Any]:
        project_id, root = self._active()
        confined = confine_to_project(root, target)
        entity_id = project_relative_entity_id(root, confined)
        try:
            if confined.is_dir():
                raise FileWriteConflictError("is_directory", f"{entity_id} is a directory.", entity_id=entity_id)
            # Check first, create after: a refused write leaves no new directories behind.
            check_write_preconditions(
                self._runtime,
                entity_id=entity_id,
                target=confined,
                expected_state_version=expected_state_version,
                create_only=create_only,
                require_existing=require_existing,
            )
            if create_parents and not confined.parent.exists():
                await asyncio.to_thread(confined.parent.mkdir, parents=True, exist_ok=True)
            if not confined.parent.is_dir():
                raise FileWriteConflictError(
                    "missing_parent",
                    f"The parent directory of {entity_id} does not exist; pass create_parents=true.",
                    entity_id=entity_id,
                )
            change = await write_project_file(
                self._runtime,
                project_id=project_id,
                project_root=root,
                target=confined,
                content=content,
                source=AGENT_SOURCE,
                source_id=None,
                changed_by=changed_by,
                expected_state_version=expected_state_version,
                create_only=create_only,
                require_existing=require_existing,
            )
        except FileWriteConflictError as conflict:
            return {"status": "conflict", **conflict.to_dict()}
        return {
            "status": "ok",
            "entity_id": change.entity_id,
            "kind": change.kind,
            "state_version": change.version,
            "size_bytes": change.size,
            "registry_refreshed": change.registry_refreshed,
        }

    async def make_directory(
        self, target: Path, *, parents: bool = False, changed_by: str = "mcp.workspace"
    ) -> dict[str, Any]:
        """Create a directory without emitting a file-change event."""
        _, root = self._active()
        confined = confine_to_project(root, target, follow_final=False)
        entity_id = project_relative_entity_id(root, confined)
        if os.path.lexists(confined):
            conflict = FileWriteConflictError("already_exists", f"{entity_id} already exists.", entity_id=entity_id)
            return {"status": "conflict", **conflict.to_dict()}
        if not parents and not confined.parent.is_dir():
            conflict = FileWriteConflictError(
                "missing_parent",
                f"The parent directory of {entity_id} does not exist; pass parents=true.",
                entity_id=entity_id,
            )
            return {"status": "conflict", **conflict.to_dict()}
        try:
            await asyncio.to_thread(confined.mkdir, parents=parents, exist_ok=False)
        except OSError as exc:
            raise ProjectFileWriteError(f"mkdir failed: {exc}") from exc
        logger.info("project_files: mkdir outcome=ok changed_by=%s", changed_by)
        return {"status": "ok", "entity_id": entity_id, "kind": "created"}

    async def delete(
        self,
        target: Path,
        *,
        recursive: bool = False,
        expected_state_version: int | None = None,
        changed_by: str = "mcp.workspace",
    ) -> dict[str, Any]:
        project_id, root = self._active()
        confined = confine_to_project(root, target, follow_final=False)
        if confined == root:
            raise PermissionError("Refusing to delete the project root")
        try:
            changes, refreshed = await delete_project_path(
                self._runtime,
                project_id=project_id,
                project_root=root,
                target=confined,
                recursive=recursive,
                source=AGENT_SOURCE,
                source_id=None,
                changed_by=changed_by,
                expected_state_version=expected_state_version,
            )
        except FileWriteConflictError as conflict:
            return {"status": "conflict", **conflict.to_dict()}
        return {
            "status": "ok",
            "entity_id": project_relative_entity_id(root, confined),
            "changes": [_change_summary(change) for change in changes],
            "registry_refreshed": refreshed,
        }

    async def move(
        self,
        source_path: Path,
        destination: Path,
        *,
        create_parents: bool = False,
        expected_state_version: int | None = None,
        changed_by: str = "mcp.workspace",
    ) -> dict[str, Any]:
        project_id, root = self._active()
        confined_source = confine_to_project(root, source_path, follow_final=False)
        confined_destination = confine_to_project(root, destination, follow_final=False)
        if root in (confined_source, confined_destination):
            raise PermissionError("Refusing to move the project root")
        source_rel = project_relative_entity_id(root, confined_source)
        destination_rel = project_relative_entity_id(root, confined_destination)
        try:
            # Check first, create after: a refused move leaves no new directories behind.
            if not os.path.lexists(confined_source):
                raise FileWriteConflictError("missing_file", f"{source_rel} does not exist.", entity_id=source_rel)
            if os.path.lexists(confined_destination):
                raise FileWriteConflictError(
                    "already_exists",
                    f"{destination_rel} already exists; moves never overwrite. Delete it first or pick another name.",
                    entity_id=destination_rel,
                )
            if create_parents and not confined_destination.parent.exists():
                await asyncio.to_thread(confined_destination.parent.mkdir, parents=True, exist_ok=True)
            changes, refreshed = await move_project_path(
                self._runtime,
                project_id=project_id,
                project_root=root,
                source_path=confined_source,
                destination=confined_destination,
                source=AGENT_SOURCE,
                source_id=None,
                changed_by=changed_by,
                expected_state_version=expected_state_version,
            )
        except FileWriteConflictError as conflict:
            return {"status": "conflict", **conflict.to_dict()}
        return {
            "status": "ok",
            "entity_id": destination_rel,
            "changes": [_change_summary(change) for change in changes],
            "registry_refreshed": refreshed,
        }


__all__ = [
    "AGENT_SOURCE",
    "BLOCKS_RELOADED_EVENT_TYPE",
    "DIRECTORY_OPERATION_FILE_LIMIT",
    "FileChange",
    "FileWriteConflictError",
    "ProjectFileService",
    "ProjectFileWriteError",
    "absorb_unobserved_disk_edit",
    "atomic_write_bytes",
    "check_write_preconditions",
    "confine_to_project",
    "delete_project_path",
    "emit_file_changed",
    "files_under",
    "is_link",
    "is_under_project_blocks_dir",
    "maybe_reload_blocks_after_save",
    "move_project_path",
    "observed_entity_version",
    "project_dropin_dir",
    "project_mutation_lock",
    "project_relative_entity_id",
    "refresh_registries_and_broadcast",
    "remove_link",
    "write_project_file",
]
