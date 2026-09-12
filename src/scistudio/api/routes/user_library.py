"""The write path into the user library."""
# Maintainer context (kept outside generated API documentation):
# The write path into the user library (ADR-053 §4).
#
# The destination is ``~/.scistudio/`` for an ordinary project and the
# tutorial-scoped library for a tutorial project. Which one is not decided here:
# :func:`scistudio.core.dropins.library_root_for_project` is the single answer to
# "which library does this project see", and both the block and type registries
# already scan through it, so the write resolving through it too is what makes
# the save and the scan agree (Learning Center FR-070, FR-071).
#
# ``docs/specs/adr-053-personal-tool-library.md`` §2.3: before this router the
# only file-write endpoint in the product was
# ``PUT /api/projects/{project_id}/file``, which rejects any path resolving
# outside the project root. The user library sits outside every project root by
# construction, so reaching ``~/.scistudio/blocks/`` or ``~/.scistudio/types/``
# required a file manager, and nothing in the product could put a file there.
#
# This is the second door, and §14 calls it "the highest-risk surface in the
# spec". Its constraint is the **inverse** of the project endpoint's rather than
# a relaxation of it (FR-007): the resolved target must be inside the relevant
# user library root, and ``PUT /api/projects/{project_id}/file`` is untouched
# (FR-009).
#
# Four rules make that constraint hold, and each one closes a case the others do
# not:
#
# 1. **The caller names the tier.** ``target`` is a
#    ``Literal["blocks", "types", "previewers"]`` and the roots come from
#    :mod:`scistudio.core.dropins`, so the destination is never inferred from
#    file content (FR-006) and this module never spells out ``~/.scistudio``
#    itself (FR-058).
# 2. **The caller supplies a filename, not a path.** Anything carrying a
#    separator, a drive, a ``..`` segment, or an absolute or drive-relative form
#    is refused before it touches the filesystem. ``C:blocks.py`` is a Windows
#    drive-relative path whose ``Path.name`` is ``blocks.py``, so the drive test
#    is separate from the basename test rather than implied by it. The basename
#    test asks both path flavours, so the rule does not change meaning when the
#    same library is used from the other operating system. Control characters, a
#    leading dot, a Windows reserved device stem, and any extension but an exact
#    ``.py`` are refused for the same reason: each of them produces a file that
#    either is not what the user asked for or cannot be found and removed
#    through the product.
# 3. **Containment is decided on resolved real paths.** ``os.path.realpath``
#    collapses symlinks first and ``os.path.commonpath`` compares canonical
#    forms — the CodeQL ``py/path-injection`` sanitiser the project endpoint
#    already uses. A symlink in the library pointing at ``/etc/passwd`` resolves
#    to ``/etc/passwd`` and fails the comparison; a path on another Windows drive
#    makes ``commonpath`` raise, which is treated as an escape. String prefixes
#    are never compared.
# 4. **The file lands directly in the root.** After resolution the target's
#    parent must be the root itself, so a nested subdirectory — including one
#    reached through a symlinked subdirectory that stays inside the root — is
#    refused, and the extension must be ``.py``.
#
# Error shapes match the project endpoint so one frontend error path serves both:
# 400 for an empty name, 403 for traversal and escape, 415 for a non-``.py``
# extension, 404 when a read finds nothing. The one addition is **409 for a
# collision** (FR-008): an existing file is reported to the caller rather than
# silently overwritten, and overwriting requires ``overwrite: true``. That
# refusal is decided by the filesystem at the moment of the write and not by the
# probe that precedes it — see :func:`write_user_library_file` for why the
# distinction is load-bearing once two processes share ``~/.scistudio``.
#
# After a successful write the registries are rebuilt through
# ``ApiRuntime.refresh_all_registries()`` (FR-010/FR-062) so the new block or
# type is discoverable without a restart — the caller names the *event*, not the
# registry set.
# Development references: ADR-053, FR-006, FR-007, FR-008, FR-009, FR-010, FR-058, FR-062, FR-070, FR-071,
# docs/specs/adr-053-personal-tool-library.md.

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from contextlib import suppress
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from scistudio.api.deps import get_runtime
from scistudio.api.routes.projects import (
    ADR036_FILE_SIZE_CAP_BYTES,
    BLOCKS_RELOADED_EVENT_TYPE,
    _resolve_project_file,
)
from scistudio.api.runtime import ApiRuntime
from scistudio.api.schemas import (
    MoveSourceRef,
    UserLibraryDirectoryRequest,
    UserLibraryDirectoryResponse,
    UserLibraryFileResponse,
    UserLibraryTarget,
    UserLibraryWriteRequest,
    UserLibraryWriteResponse,
)
from scistudio.core.dropins import (
    BLOCKS_DIR_NAME,
    PREVIEWERS_DIR_NAME,
    TYPES_DIR_NAME,
    library_root_for_project,
)
from scistudio.engine.events import EngineEvent
from scistudio.panels.descriptor import _ID as _PANEL_ID_RE
from scistudio.panels.miniapp_create import PANELS_DIR_NAME

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/user-library", tags=["user-library"])
RuntimeDep = Annotated[ApiRuntime, Depends(get_runtime)]

#: FR-006: the caller's ``target`` value to the tier's child directory name.
#: The mapping is the whole of the target selection — no other code in this
#: module decides which tier a file goes to, and none of it decides which
#: library root that tier hangs off (:func:`_library_root`).
_TARGET_DIR_NAMES = {
    "blocks": BLOCKS_DIR_NAME,
    "types": TYPES_DIR_NAME,
    # Learning Center FR-070 / #2086: the previewer tier promotes through the
    # same door, and the same library-root swap, as blocks and types.
    "previewers": PREVIEWERS_DIR_NAME,
    # ADR-054 MiniApp FR-039: the panel tier. Reached only by the directory
    # route below — ``_validate_filename`` refuses everything a panel is made
    # of, which is why a panel could not be promoted through the file route.
    "panels": PANELS_DIR_NAME,
}

#: FR-039: the only target that names a directory rather than a file. Kept as a
#: set so a second directory tier is one entry, not a second code path.
_DIRECTORY_TARGETS = frozenset({"panels"})

#: Files never carried into the library: compiled bytecode a scan would import
#: in preference to the source, and the temp files a write leaves behind.
_SKIP_DIR_NAMES = frozenset({"__pycache__", ".git", ".hg", ".svn"})

#: Only Python sources belong in a drop-in tier; both registries scan for
#: ``.py`` files and nothing else there is loadable.
_ALLOWED_SUFFIX = ".py"

#: Suffix of the temp file the atomic write goes through. Deliberately **not**
#: ``.py``: the temp file lives in the destination directory so the landing
#: step stays atomic, and that directory is globbed for ``*.py`` and executed on
#: every scan. A ``.py`` temp file is therefore a drop-in that a concurrent
#: palette refresh can import half-written, and one left behind by a failed
#: write is caller-controlled code the user cannot see in the palette or delete
#: through the product (``docs/audit/2026-08-07-adr-053-spec1-write-path.md``
#: P2-2). Neither ``os.replace`` nor ``os.link`` cares about the source
#: extension.
_WRITE_TEMP_SUFFIX = ".tmp"

#: Windows device names, which Win32 may resolve ahead of a real file of the
#: same stem. Refused on every platform so a library written on POSIX does not
#: become unusable — or worse, a device write — when synced to Windows.
_RESERVED_DEVICE_STEMS = frozenset(
    {"CON", "PRN", "AUX", "NUL"} | {f"COM{digit}" for digit in "0123456789"} | {f"LPT{digit}" for digit in "0123456789"}
)


def _reject(status_code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=detail)


def _collision(resolved: Path, target: UserLibraryTarget) -> HTTPException:
    """The one refusal sentence, for both writers that can raise it.

    The pre-write probe and the exclusive create answer the same question at
    two moments, and the caller must not be able to tell which one fired: a
    collision the filesystem caught is the same fact as a collision the probe
    caught, and two wordings would make the prompt read differently
    depending on a race the user cannot see.
    """
    # Development references: FR-008, FR-018.
    return _reject(
        409,
        (
            f"{resolved.name} already exists in the user library {target} directory. "
            "Retry with overwrite=true to replace it, or choose another name."
        ),
    )


def _discard(tmp_path: str) -> None:
    """Remove the write's temp file, swallowing everything removal can raise.

    Anything that escapes leaves a file behind in a directory the registry
    scans, which is the outcome :data:`_WRITE_TEMP_SUFFIX` exists to prevent.
    """
    with suppress(OSError):
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _is_reserved_device_name(name: str) -> bool:
    """Return whether *name*'s stem is a Windows reserved device name.

    Win32 resolves ``NUL.py`` to the ``NUL`` device on some builds and to an
    ordinary file on others, so the same request either writes to a device or
    fails late inside ``os.replace`` depending on the host. Refusing the whole
    family up front is cheaper than either outcome.
    """
    return name.split(".", 1)[0].upper() in _RESERVED_DEVICE_STEMS


def _validate_filename(filename: str) -> str:
    """Return *filename* if it is a bare ``.py`` basename, else raise.

    Rule 2 of the module docstring. Every rejection here happens before any
    filesystem access, so a hostile value never reaches ``realpath``.

    The basename test asks **both** path flavours, not the host's. A file
    written on Linux is read on Windows and vice versa, so ``sub\\evil.py`` has
    to be refused on POSIX even though POSIX treats the backslash as an
    ordinary character — otherwise the same library is a bare filename on one
    machine and a nested path on another. Asking
    :class:`~pathlib.PureWindowsPath` as well is also what makes this rule
    reachable rather than implied by an earlier separator check that only
    happened to catch the same inputs.
    """
    # Development references: adr-053-spec1-write-path.
    name = filename.strip()
    if not name:
        raise _reject(400, "filename query parameter is required")
    # A control character is never a legitimate filename, and an embedded NUL
    # in particular survives every path test here and then makes ``os.replace``
    # raise ``ValueError`` deep in the write, past the ``OSError`` cleanup
    # handler — an unhandled 500 that leaks the temp file (P2-2).
    if any(character < " " or character == "\x7f" for character in name):
        raise _reject(403, "Control characters are not allowed in a filename")
    drive, _ = os.path.splitdrive(name)
    if drive or os.path.isabs(name) or name.startswith(("/", "\\")):
        raise _reject(403, "Absolute and drive-relative paths are not allowed")
    if name in (".", ".."):
        raise _reject(403, "Path traversal is not allowed")
    if PurePosixPath(name).name != name or PureWindowsPath(name).name != name:
        raise _reject(403, "The user library accepts a bare filename, not a path")
    # A leading dot makes a live drop-in that most file listings hide, so the
    # user cannot find it to delete it and the palette cannot explain it.
    if name.startswith("."):
        raise _reject(403, "A user library filename cannot start with a dot")
    if _is_reserved_device_name(name):
        raise _reject(403, f"{name} is a reserved device name on Windows and cannot be used")
    # Exact ``.py``, not a case-insensitive match. ``SHOUT.PY`` is a live
    # drop-in on Windows (whose ``glob`` is case-insensitive) and dead on
    # POSIX, and the standalone bridge's change detector never sees it, so the
    # product refuses to create one rather than creating a file that means two
    # different things on two machines (P3-2).
    if not name.endswith(_ALLOWED_SUFFIX) or name == _ALLOWED_SUFFIX:
        raise _reject(415, f"Only {_ALLOWED_SUFFIX} files belong in the user library")
    return name


def _active_project_dir(runtime: ApiRuntime) -> Path | None:
    """Return the open project's directory, or ``None`` when none is open.

    The only input :func:`_library_root` needs, and the only reason both
    endpoints take a runtime.
    """
    active = getattr(runtime, "active_project", None)
    path = getattr(active, "path", None)
    return Path(path) if path else None


def _library_root(target: UserLibraryTarget, project_dir: Path | None) -> Path:
    """Return the library directory *target* names for *project_dir*'s context.

    Learning Center. This is the **same** answer the two
    registries scan: :func:`scistudio.core.dropins.library_root_for_project` is
    the single decision of which library root a project sees, and both drop-in
    scan-directory lists end with exactly ``<that root>/<tier name>``. Deciding
    it once is the whole point — the read side already resolved through it while
    this write path bound ``user_blocks_dir`` / ``user_types_dir`` directly, so
    a reader who saved a block to My Library from inside a tutorial deposited a
    teaching file into their real ``~/.scistudio`` library, where it was scanned
    into every project they opened afterwards and survived clearing tutorial
    data. It also made ``library_contains`` unsatisfiable: the save went to one
    library and the scan looked in the other.

    A real project is unaffected — ``library_root_for_project`` answers
    ``user_library_dir()`` for every path outside the tutorial parent.
    """
    # Development references: ADR-053, FR-070, FR-071.
    dir_name = _TARGET_DIR_NAMES.get(target)
    if dir_name is None:  # pragma: no cover - FastAPI validates the Literal
        raise _reject(422, f"Unknown user library target: {target!r}")
    return library_root_for_project(project_dir) / dir_name


def _resolve_user_library_file(target: UserLibraryTarget, filename: str, project_dir: Path | None) -> tuple[Path, Path]:
    """Return ``(root, target_path)`` for a validated user-library write.

    Rules 3 and 4 of the module docstring: real paths are compared, and the
    file must land directly in the root. The root is created if missing so a
    first-ever promotion works on a machine that has never had a user library,
    and so ``realpath`` resolves a real directory rather than a phantom.

    *project_dir* selects the library (:func:`_library_root`); containment is
    then decided against whichever root that returned, so the sandbox is as
    tight for a tutorial save as for a real one.
    """
    if target in _DIRECTORY_TARGETS:
        # FR-039: a panel is a directory. Saying so here is what stops the file
        # route creating a stray ``.py`` in the panel tier root, which no scan
        # would ever load and no palette would ever show.
        raise _reject(400, f"The {target} tier holds directories; use POST /api/user-library/directory")
    declared_root = _library_root(target, project_dir)
    name = _validate_filename(filename)

    try:
        declared_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise _reject(500, f"Could not create user library directory: {exc}") from exc
    root = os.path.realpath(str(declared_root))

    candidate = os.path.realpath(os.path.join(root, name))
    # CodeQL py/path-injection canonical sanitiser: realpath + commonpath.
    try:
        if os.path.commonpath([root, candidate]) != root:
            raise _reject(403, "Path escapes the user library root")
    except ValueError as exc:
        # commonpath raises on different drives (Windows) — treat as an escape.
        raise _reject(403, "Path escapes the user library root") from exc

    resolved = Path(candidate)
    if str(resolved.parent) != root:
        raise _reject(403, "User library files must live directly in the target directory")
    return Path(root), resolved


@router.get("/file", response_model=UserLibraryFileResponse)
async def read_user_library_file(
    target: UserLibraryTarget,
    runtime: RuntimeDep,
    filename: str = "",
) -> UserLibraryFileResponse:
    """Read one file from the user library, or 404 when it is absent.

    the existence probe the new-file and promotion flows run
    before writing. It mirrors ``GET /api/projects/{project_id}/file`` exactly —
    200 means "exists, do not overwrite", 404 means "safe to create" — so the
    frontend probe helper is the same shape for both destinations.

    It takes the runtime for the same reason the write does: the probe has to
    look in the library the write will land in (:func:`_library_root`), or a
    tutorial save would be checked for collisions against the user's real
    library and reported against the wrong file.
    """
    # Development references: ADR-053, FR-031.
    _root, resolved = _resolve_user_library_file(target, filename, _active_project_dir(runtime))
    if not resolved.exists():
        raise _reject(404, "File not found")
    if resolved.is_dir():
        raise _reject(400, "Path is a directory, not a file")
    try:
        stat = resolved.stat()
        content = resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise _reject(415, f"File is not valid UTF-8: {exc}") from exc
    except OSError as exc:
        raise _reject(500, f"read failed: {exc}") from exc
    return UserLibraryFileResponse(
        target=target,
        filename=resolved.name,
        path=str(resolved),
        content=content,
        mtime=stat.st_mtime,
        size=stat.st_size,
    )


@router.put("/file", response_model=UserLibraryWriteResponse)
async def write_user_library_file(
    body: UserLibraryWriteRequest,
    runtime: RuntimeDep,
    target: UserLibraryTarget,
    filename: str = "",
) -> UserLibraryWriteResponse:
    """Write one file into the user-wide library.

    An existing target is a 409 unless ``overwrite`` is set; the write
    itself is atomic (temp file in the destination directory plus a single
    rename-shaped step) so a failure never leaves a half-written block where the
    registry will find it.

    **The refusal is decided by the filesystem, not by the probe above it.**
    ``existed`` answers the question early enough to give a good error, but it
    cannot be the only notification: the API process and the
    standalone MCP bridge on the same ``~/.scistudio``, so a second writer can
    create the target between that call and this one and ``os.replace`` would
    destroy it without a word — the silent overwrite exists to forbid,
    reachable because of this spec's own work. The non-overwrite path therefore
    lands the file with ``os.link``, which fails with ``FileExistsError`` when
    the name is taken and is the same 409 either way. ``os.link`` rather than an
    ``O_EXCL`` create because the destination name must never exist in a state
    other than fully written: the temp file is complete and fsynced before the
    name appears at all, so a palette refresh cannot catch it empty. An
    ``overwrite=true`` request has consented to replacing whatever is there, so
    it keeps ``os.replace``.

    The temp file has to live in the destination directory for both steps to be
    atomic, and that directory is globbed for ``*.py`` and executed on every
    scan — so it is written with :data:`_WRITE_TEMP_SUFFIX` instead. Atomicity
    of the destination *name* is not enough on its own: a ``.py`` temp file is a
    second name in the same scanned directory, and a palette refresh concurrent
    with a save could import it half-written. ``os.link`` keeps that second name
    after a successful write, so it is removed on both paths, and cleanup
    catches every exception rather than only ``OSError`` because anything that
    escapes it leaves that file behind.

    Which library the file lands in is decided by the open project
    (:func:`_library_root`): a tutorial project writes to the tutorial-scoped
    library and every other project to ``~/.scistudio``.
    """
    # Development references: ADR-053, FR-006, FR-008, FR-010, FR-065, FR-070, FR-071.
    _root, resolved = _resolve_user_library_file(target, filename, _active_project_dir(runtime))

    encoded = body.content.encode("utf-8")
    if len(encoded) > ADR036_FILE_SIZE_CAP_BYTES:
        raise _reject(
            413,
            f"Content size {len(encoded)} exceeds editor cap {ADR036_FILE_SIZE_CAP_BYTES} bytes",
        )

    if resolved.is_dir():
        raise _reject(400, "Path is a directory, not a file")
    existed = resolved.exists()
    if existed and not body.overwrite:
        raise _collision(resolved, target)

    # ``resolved`` passed realpath + commonpath containment above.
    # lgtm[py/path-injection]
    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix=".__scistudio_write_",
        suffix=_WRITE_TEMP_SUFFIX,
        dir=str(resolved.parent),
    )
    try:
        with os.fdopen(tmp_fd, "wb") as tmp_file:
            tmp_file.write(encoded)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        if body.overwrite:
            os.replace(tmp_path, resolved)
        else:
            os.link(tmp_path, resolved)
    except FileExistsError as exc:
        _discard(tmp_path)
        raise _collision(resolved, target) from exc
    except Exception as exc:
        # Not ``except OSError``: the cleanup has to cover everything the write
        # can raise, because whatever escapes it leaves a file behind in a
        # directory the scan reads.
        _discard(tmp_path)
        raise _reject(500, f"write failed: {exc}") from exc
    if not body.overwrite:
        # ``os.link`` leaves the source name behind; ``os.replace`` consumes it.
        _discard(tmp_path)

    # FR-017 — the library copy exists, so the original may go. Ordered this way
    # deliberately: a removal that ran first and a write that then failed would
    # destroy the user's only copy, and no error message makes that acceptable.
    moved_from, move_error = _consume_source(runtime, body.move_from, resolved)

    # After the removal, not before: the project file is gone from the tier the
    # registry scans, so a refresh that ran first would leave the promoted item
    # registered twice — once from each tier — which is the state FR-017 exists
    # to avoid.
    refreshed = _refresh_registries(runtime)
    if refreshed:
        await _announce_reload(runtime, resolved)

    try:
        stat = resolved.stat()
    except OSError as exc:
        raise _reject(500, f"post-write stat failed: {exc}") from exc

    return UserLibraryWriteResponse(
        target=target,
        filename=resolved.name,
        path=str(resolved),
        mtime=stat.st_mtime,
        size=stat.st_size,
        kind="modified" if existed else "created",
        registries_refreshed=refreshed,
        moved_from=moved_from,
        move_error=move_error,
    )


def _consume_source(
    runtime: ApiRuntime,
    ref: MoveSourceRef | None,
    written: Path,
) -> tuple[str | None, str | None]:
    """Remove the project file *ref* names, returning ``(removed_path, error)``.

    Promotion moves rather than copies, so the write above is
    only half of it: while the project keeps its own copy, the two tiers hold
    the same class name, and which one the process actually uses is decided by
    a registry duplicate policy the user cannot see. Removing the original is
    what makes "it is in My Library now" true rather than approximately true.

    Three properties this function is responsible for:

    * **The path is sandboxed by the same resolver the project file endpoints
      use.** ``_resolve_project_file`` applies the realpath + commonpath
      containment check, the ``..`` rejection, and the editor extension
      allowlist, so a caller cannot name a file outside the project root or one
      the editor would refuse to open. Reusing it rather than restating it is
      the point: a second containment check is a second thing to get wrong.
    * **A failure is reported, never raised.** The library copy is already on
      disk, so the promotion succeeded; failing the request would tell the
      caller nothing happened when something did. The outcome degrades to a
      copy — exactly the legacy behaviour — and the caller says so.
    * **It never removes the file it just wrote.** The library sits outside
      every project root, so containment already rules this out, but a
      same-path guard makes it true regardless of how the roots are configured.
    """
    # Development references: ADR-053, FR-017.
    if ref is None:
        return None, None
    try:
        _root, target = _resolve_project_file(runtime, ref.project_id, ref.path)
    except HTTPException as exc:
        return None, f"could not resolve {ref.path!r}: {exc.detail}"

    if os.path.realpath(target) == os.path.realpath(written):
        return None, "refusing to remove the file that was just written"
    if not target.exists():
        # Already gone — the move's goal, so not an error.
        return str(target), None
    try:
        target.unlink()
    except OSError as exc:
        return None, f"could not remove {ref.path!r}: {exc}"
    return str(target), None


async def _announce_reload(runtime: ApiRuntime, target: Path) -> None:
    """Tell open clients the registries were rebuilt.

    Refreshing is only half of it. Every other caller that rebuilds the
    registries — a save under ``blocks/`` or ``types/``, a branch switch, a
    tutorial step's write — follows it with this event, and the frontend hangs
    real behaviour off it: the block palette and the type and previewer
    catalogues re-read themselves, and the Learning Center re-judges the
    conditions that turn on what the registries hold.

    Promoting a block or a type to the user library did not send it. The
    registries were right and nothing on screen knew, so a tutorial step
    waiting on ``library_contains`` sat unsatisfied until the reader pressed
    "Check again" by hand — the product having done the thing and the product
    saying so had come apart.

    Best-effort, like the refresh above: the file is written and the library
    holds it, so a bus failure is logged rather than turned into a 500 on a
    request that succeeded.
    """
    # Development references: FR-062.
    event_bus = getattr(runtime, "event_bus", None)
    if event_bus is None:
        return
    try:
        await event_bus.emit(
            EngineEvent(
                event_type=BLOCKS_RELOADED_EVENT_TYPE,
                data={"added": [], "removed": [], "reloaded": [target.name], "path": str(target)},
            )
        )
    except Exception:
        logger.exception("user library write: event_bus.emit raised")


def _refresh_registries(runtime: ApiRuntime) -> bool:
    """Rebuild every registry the write invalidated.

    ``refresh_all_registries`` is the one entry point a caller naming this
    *event* uses; refreshing a single registry here would leave inconsistent cached definitions. A failure is reported to the caller rather than
    raised: the file is already on disk, so failing the request would be a lie.
    """
    # Development references: FR-010, FR-062.
    try:
        runtime.refresh_all_registries()
    except Exception:
        logger.exception("user library write: refresh_all_registries() raised")
        return False
    return True


# ---------------------------------------------------------------------------
# Directory promotion (ADR-054 MiniApp FR-039)
# ---------------------------------------------------------------------------
#
# The file route above promotes one ``.py`` file. A panel is a directory — a
# manifest, a page, its assets, and optionally ``panel.py`` — so it needs a
# second door, and the four rules of the module docstring are restated for a
# tree rather than relaxed for it:
#
# 1. The caller names the tier (``target=panels``) and the directory name; the
#    name must be a panel id, which is the directory's own name by the
#    descriptor rule, so nothing here can address a path.
# 2. Both ends are confined on resolved real paths — under the project's
#    ``panels/`` tier on the way out, under the library's ``panels/`` tier on
#    the way in — and symlinks are neither followed nor copied, so a link
#    pointing out of the project cannot drag a file in or a removal out.
# 3. The project directory is the *open* project's, checked against the
#    runtime rather than trusted from the body. This route removes a directory
#    tree; a caller that could name any project could name any tree.
# 4. The landing is a rename of a fully-copied staging directory, so the
#    library never holds a half-panel that a scan could pick up.
#
# The ordering is ADR-053 FR-017's, for its reason: write the library copy,
# then remove the project copy, and degrade to a copy when the removal fails.
# A removal that ran first and a copy that then failed would destroy the
# user's only copy.


def _validate_directory_name(name: str) -> str:
    """Return *name* if it is a panel id, else raise.

    The descriptor rule is the whole check: a panel id is lowercase dotted
    segments and must equal its directory name, so an id that parses cannot
    contain a separator, a drive, a ``..`` segment, or a leading dot. Asking
    the descriptor's own pattern rather than restating it keeps the two from
    drifting into different ideas of what a panel is called.
    """
    # Development references: ADR-054 MiniApp, FR-039.
    candidate = name.strip()
    if not candidate:
        raise _reject(400, "name query parameter is required")
    if not _PANEL_ID_RE.fullmatch(candidate):
        raise _reject(403, "The user library accepts a panel id, not a path")
    return candidate


def _promotion_project_dir(runtime: ApiRuntime, declared: str) -> Path:
    """Resolve the body's ``project_dir`` against the open project, or refuse."""
    active = _active_project_dir(runtime)
    if active is None:
        raise _reject(400, "Open a project before promoting a directory to the user library")
    try:
        resolved = Path(declared).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise _reject(400, f"Invalid project_dir: {exc}") from exc
    if not resolved.is_dir():
        raise _reject(400, "project_dir is not a directory")
    if os.path.realpath(resolved) != os.path.realpath(active):
        raise _reject(403, "project_dir must be the open project")
    return resolved


def _resolve_promotion_source(project_dir: Path, target: UserLibraryTarget, name: str) -> Path:
    """Return the project-tier directory to promote, confined to that tier."""
    tier = os.path.realpath(str(project_dir / _TARGET_DIR_NAMES[target]))
    candidate = os.path.realpath(os.path.join(tier, name))
    try:
        if os.path.commonpath([tier, candidate]) != tier:
            raise _reject(403, "Path escapes the project tier directory")
    except ValueError as exc:
        raise _reject(403, "Path escapes the project tier directory") from exc
    source = Path(candidate)
    if str(source.parent) != tier:
        raise _reject(403, "A promoted directory must live directly in the project tier directory")
    if not source.is_dir():
        raise _reject(404, f"{name} is not a directory in this project's {target} directory")
    return source


def _resolve_library_directory(target: UserLibraryTarget, name: str, project_dir: Path) -> tuple[Path, Path]:
    """Return ``(library root, destination)``, both confined and real."""
    declared_root = _library_root(target, project_dir)
    try:
        declared_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise _reject(500, f"Could not create user library directory: {exc}") from exc
    root = os.path.realpath(str(declared_root))
    candidate = os.path.normpath(os.path.join(root, name))
    try:
        if os.path.commonpath([root, candidate]) != root:
            raise _reject(403, "Path escapes the user library root")
    except ValueError as exc:
        raise _reject(403, "Path escapes the user library root") from exc
    destination = Path(candidate)
    if str(destination.parent) != root:
        raise _reject(403, "User library directories must live directly in the target directory")
    return Path(root), destination


def _copy_tree_confined(source: Path, staging: Path) -> None:
    """Copy *source* into *staging*, file by file, confined to *source*.

    ``os.walk`` without ``followlinks`` and an explicit symlink skip, so a link
    inside the panel neither escapes the project on the way out nor lands in
    the library as a link into somewhere else. Bytecode and version-control
    directories are dropped: a ``__pycache__`` copied beside its source is
    imported in preference to it after an edit.
    """
    source_root = os.path.realpath(str(source))
    for current, dir_names, file_names in os.walk(source, followlinks=False):
        dir_names[:] = [
            d for d in dir_names if d not in _SKIP_DIR_NAMES and not os.path.islink(os.path.join(current, d))
        ]
        relative = os.path.relpath(current, source)
        target_dir = staging if relative == "." else staging / relative
        target_dir.mkdir(parents=True, exist_ok=True)
        for file_name in file_names:
            origin = os.path.join(current, file_name)
            if os.path.islink(origin):
                continue
            if os.path.commonpath([source_root, os.path.realpath(origin)]) != source_root:
                raise _reject(403, "A file in the directory resolves outside the project")
            if os.path.getsize(origin) > ADR036_FILE_SIZE_CAP_BYTES:
                raise _reject(413, f"{file_name} exceeds the {ADR036_FILE_SIZE_CAP_BYTES} byte file cap")
            shutil.copyfile(origin, target_dir / file_name)


def _land_directory(staging: Path, destination: Path, *, overwrite: bool, target: UserLibraryTarget) -> None:
    """Rename the staged copy into place, or refuse a collision."""
    if destination.is_symlink():
        # An overwrite would otherwise be asked to remove a link standing where
        # a panel should be, whose target is somewhere this route never checked.
        raise _reject(403, f"{destination.name} in the user library {target} directory is a symbolic link")
    if destination.exists():
        if not overwrite:
            raise HTTPException(
                409,
                detail={
                    "code": "exists",
                    "message": (
                        f"{destination.name} already exists in the user library {target} directory. "
                        "Retry with overwrite=true to replace it, or choose another name."
                    ),
                },
            )
        shutil.rmtree(destination)
    try:
        os.rename(staging, destination)
    except OSError as exc:
        # A concurrent writer created the name between the probe and here.
        raise HTTPException(
            409,
            detail={
                "code": "exists",
                "message": f"{destination.name} was created in the user library {target} directory by something else.",
            },
        ) from exc


def _consume_directory(source: Path, written: Path) -> tuple[bool, str | None]:
    """Remove the project copy, reporting rather than raising (ADR-053 FR-017).

    The library copy is already on disk, so the promotion succeeded; failing
    the request would tell the caller nothing happened when something did. The
    outcome degrades to a copy, and the caller says so. The same-path guard is
    belt and braces over the containment above: this must never remove what it
    just wrote.
    """
    if os.path.realpath(source) == os.path.realpath(written):
        return False, "refusing to remove the directory that was just written"
    try:
        shutil.rmtree(source)
    except OSError as exc:
        return False, f"could not remove {source.name!r} from the project: {exc}"
    return True, None


@router.post("/directory", response_model=UserLibraryDirectoryResponse)
async def promote_user_library_directory(
    body: UserLibraryDirectoryRequest,
    runtime: RuntimeDep,
    target: UserLibraryTarget,
    name: str = "",
) -> UserLibraryDirectoryResponse:
    """Move a project directory into the user library (ADR-054 MiniApp FR-039).

    The only directory tier today is ``panels``. Which library it lands in is
    decided by the open project, exactly as the file route decides it: a
    tutorial project promotes into the tutorial-scoped library, so the write
    and the scan agree.
    """
    # Development references: ADR-053, FR-017; ADR-054 MiniApp, FR-039.
    if target not in _DIRECTORY_TARGETS:
        raise _reject(400, f"The {target} tier holds files; use PUT /api/user-library/file")
    directory_name = _validate_directory_name(name)
    project_dir = _promotion_project_dir(runtime, body.project_dir)
    source = _resolve_promotion_source(project_dir, target, directory_name)
    root, destination = _resolve_library_directory(target, directory_name, project_dir)
    if os.path.realpath(source) == os.path.realpath(destination):
        raise _reject(403, "The project directory and the library directory are the same path")

    staging = Path(tempfile.mkdtemp(prefix=".__scistudio_promote_", dir=str(root)))
    try:
        _copy_tree_confined(source, staging)
        _land_directory(staging, destination, overwrite=body.overwrite, target=target)
    except HTTPException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise _reject(500, f"promotion failed: {exc}") from exc

    moved, move_error = _consume_directory(source, destination)
    refreshed = _refresh_registries(runtime)
    if refreshed:
        await _announce_reload(runtime, destination)
    return UserLibraryDirectoryResponse(
        target=target,
        name=directory_name,
        path=str(destination),
        moved=moved,
        move_error=move_error,
        registries_refreshed=refreshed,
    )
