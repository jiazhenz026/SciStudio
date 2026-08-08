"""The write path into the user-wide library, ``~/.scistudio/`` (ADR-053 §4).

``docs/specs/adr-053-personal-tool-library.md`` §2.3: before this router the
only file-write endpoint in the product was
``PUT /api/projects/{project_id}/file``, which rejects any path resolving
outside the project root. The user library sits outside every project root by
construction, so reaching ``~/.scistudio/blocks/`` or ``~/.scistudio/types/``
required a file manager, and nothing in the product could put a file there.

This is the second door, and §14 calls it "the highest-risk surface in the
spec". Its constraint is the **inverse** of the project endpoint's rather than
a relaxation of it (FR-007): the resolved target must be inside the relevant
user library root, and ``PUT /api/projects/{project_id}/file`` is untouched
(FR-009).

Four rules make that constraint hold, and each one closes a case the others do
not:

1. **The caller names the tier.** ``target`` is a ``Literal["blocks", "types"]``
   and the roots come from :mod:`scistudio.core.dropins`, so the destination is
   never inferred from file content (FR-006) and this module never spells out
   ``~/.scistudio`` itself (FR-058).
2. **The caller supplies a filename, not a path.** Anything carrying a
   separator, a drive, a ``..`` segment, or an absolute or drive-relative form
   is refused before it touches the filesystem. ``C:blocks.py`` is a Windows
   drive-relative path whose ``Path.name`` is ``blocks.py``, so the drive test
   is separate from the basename test rather than implied by it. The basename
   test asks both path flavours, so the rule does not change meaning when the
   same library is used from the other operating system. Control characters, a
   leading dot, a Windows reserved device stem, and any extension but an exact
   ``.py`` are refused for the same reason: each of them produces a file that
   either is not what the user asked for or cannot be found and removed
   through the product.
3. **Containment is decided on resolved real paths.** ``os.path.realpath``
   collapses symlinks first and ``os.path.commonpath`` compares canonical
   forms — the CodeQL ``py/path-injection`` sanitiser the project endpoint
   already uses. A symlink in the library pointing at ``/etc/passwd`` resolves
   to ``/etc/passwd`` and fails the comparison; a path on another Windows drive
   makes ``commonpath`` raise, which is treated as an escape. String prefixes
   are never compared.
4. **The file lands directly in the root.** After resolution the target's
   parent must be the root itself, so a nested subdirectory — including one
   reached through a symlinked subdirectory that stays inside the root — is
   refused, and the extension must be ``.py``.

Error shapes match the project endpoint so one frontend error path serves both:
400 for an empty name, 403 for traversal and escape, 415 for a non-``.py``
extension, 404 when a read finds nothing. The one addition is **409 for a
collision** (FR-008): an existing file is reported to the caller rather than
silently overwritten, and overwriting requires ``overwrite: true``. That
refusal is decided by the filesystem at the moment of the write and not by the
probe that precedes it — see :func:`write_user_library_file` for why the
distinction is load-bearing once two processes share ``~/.scistudio``.

After a successful write the registries are rebuilt through
``ApiRuntime.refresh_all_registries()`` (FR-010/FR-062) so the new block or
type is discoverable without a restart — the caller names the *event*, not the
registry set.
"""

from __future__ import annotations

import logging
import os
import tempfile
from contextlib import suppress
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from scistudio.api.deps import get_runtime
from scistudio.api.routes.projects import ADR036_FILE_SIZE_CAP_BYTES
from scistudio.api.runtime import ApiRuntime
from scistudio.api.schemas import (
    UserLibraryFileResponse,
    UserLibraryTarget,
    UserLibraryWriteRequest,
    UserLibraryWriteResponse,
)
from scistudio.core.dropins import user_blocks_dir, user_types_dir

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/user-library", tags=["user-library"])
RuntimeDep = Annotated[ApiRuntime, Depends(get_runtime)]

#: FR-006: the caller's ``target`` value to the ``core.dropins`` accessor for
#: that tier. The mapping is the whole of the target selection — no other code
#: in this module decides where a file goes.
_TARGET_ROOTS = {
    "blocks": user_blocks_dir,
    "types": user_types_dir,
}

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
    """The one FR-008 refusal sentence, for both writers that can raise it.

    The pre-write probe and the exclusive create answer the same question at
    two moments, and the caller must not be able to tell which one fired: a
    collision the filesystem caught is the same fact as a collision the probe
    caught, and two wordings would make the FR-018 prompt read differently
    depending on a race the user cannot see.
    """
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
    happened to catch the same inputs
    (``docs/audit/2026-08-07-adr-053-spec1-write-path.md`` P2-5).
    """
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


def _resolve_user_library_file(target: UserLibraryTarget, filename: str) -> tuple[Path, Path]:
    """Return ``(root, target_path)`` for a validated user-library write.

    Rules 3 and 4 of the module docstring: real paths are compared, and the
    file must land directly in the root. The root is created if missing so a
    first-ever promotion works on a machine that has never had a user library,
    and so ``realpath`` resolves a real directory rather than a phantom.
    """
    root_factory = _TARGET_ROOTS.get(target)
    if root_factory is None:  # pragma: no cover - FastAPI validates the Literal
        raise _reject(422, f"Unknown user library target: {target!r}")
    name = _validate_filename(filename)

    declared_root = root_factory()
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
    filename: str = "",
) -> UserLibraryFileResponse:
    """Read one file from the user library, or 404 when it is absent.

    ADR-053 FR-031: the existence probe the new-file and promotion flows run
    before writing. It mirrors ``GET /api/projects/{project_id}/file`` exactly —
    200 means "exists, do not overwrite", 404 means "safe to create" — so the
    frontend probe helper is the same shape for both destinations.
    """
    _root, resolved = _resolve_user_library_file(target, filename)
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
    """Write one file into the user-wide library (ADR-053 FR-006 to FR-010).

    An existing target is a 409 unless ``overwrite`` is set (FR-008); the write
    itself is atomic (temp file in the destination directory plus a single
    rename-shaped step) so a failure never leaves a half-written block where the
    registry will find it.

    **The refusal is decided by the filesystem, not by the probe above it.**
    ``existed`` answers the question early enough to give a good error, but it
    cannot be the thing FR-008 rests on: FR-065 put the API process and the
    standalone MCP bridge on the same ``~/.scistudio``, so a second writer can
    create the target between that call and this one and ``os.replace`` would
    destroy it without a word — the silent overwrite FR-008 exists to forbid,
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
    """
    _root, resolved = _resolve_user_library_file(target, filename)

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

    refreshed = _refresh_registries(runtime)

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
    )


def _refresh_registries(runtime: ApiRuntime) -> bool:
    """Rebuild every registry the write invalidated (FR-010 / FR-062).

    ``refresh_all_registries`` is the one entry point a caller naming this
    *event* uses; refreshing a single registry here would reintroduce exactly
    the drift FR-062 removed. A failure is reported to the caller rather than
    raised: the file is already on disk, so failing the request would be a lie.
    """
    try:
        runtime.refresh_all_registries()
    except Exception:
        logger.exception("user library write: refresh_all_registries() raised")
        return False
    return True
