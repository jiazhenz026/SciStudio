"""Category (f) MCP tool — promotion into the personal tool library (1 tool).

ADR-053 ``docs/specs/adr-053-personal-tool-library.md`` §4 FR-011 and §6.2 E3.
Promotion is reachable from five entry points and this is the agent's: without
it the agent cannot act on the promotion opportunities ADR-053 §3 expects it to
offer — for instance right after it authors a block the user runs successfully.

Promotion **copies** (FR-017). The originating project keeps working exactly as
before; the copy is what becomes reusable across projects.

**FR-019 is one condition, not a list of cases.** Promotion is offered when
the block's *resolved origin tier* is ``project`` and refused for every other
value in the vocabulary — ``builtin``, ``package``, ``user``, and the FR-002
``custom`` fallback. That is literally the condition E1, E2 and E5 apply
(``isPromotableOrigin(origin) => origin === "project"`` in
``frontend/src/components/promotion/promotable.ts``), because both sides now
read the same resolver.

They did not always. This tool used to ask two narrower questions of its own —
"is there a file path" and "is the file's parent the library root" — because
:func:`~scistudio.core.origins.resolve_origin` lived in ``scistudio.api`` and
the "AI must not depend on api" import-linter contract put it out of reach. The
result was the divergence FR-003 exists to prevent: a block whose file resolved
under neither tier root (a symlinked drop-in escaping the project, a differing
Windows drive) was **hidden by the three frontend entry points and accepted
here**. The resolver moved to :mod:`scistudio.core.origins`, which both layers
may import, and this tool now calls
:func:`~scistudio.core.origins.map_block_origin` — the same function
``GET /api/blocks/`` calls to fill the ``origin`` field the frontend condition
reads. See ``docs/audit/2026-08-07-adr-053-spec1-track-b.md`` (P2-2).

The remaining refusal is FR-008/FR-018's: an existing destination file is
reported rather than overwritten, and overwriting requires ``overwrite=True``.
``new_name`` is the save-as-new-name half of the same prompt.

Layering: this module sits in the AI layer, which must not import
``scistudio.api``, so it reaches the user library through
:mod:`scistudio.core.dropins` — the same single answer to "where does the user
tier live" the HTTP endpoint uses (FR-058) — and it never spells out
``~/.scistudio`` itself.
"""

from __future__ import annotations

import logging
import os
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, Field

from scistudio.ai.agent.mcp._context import _safe_under, get_context
from scistudio.ai.agent.mcp._reload import broadcast_blocks_reloaded, refresh_context_registries
from scistudio.ai.agent.mcp.server import mcp
from scistudio.core.dropins import user_blocks_dir
from scistudio.core.origins import PROJECT_ORIGIN, map_block_origin

logger = logging.getLogger(__name__)

_ALLOWED_SUFFIX = ".py"

#: Suffix of the temp file :func:`_atomic_write` goes through — deliberately
#: not ``.py``, since the temp file shares the scanned destination directory.
_WRITE_TEMP_SUFFIX = ".tmp"

#: FR-019, per resolved origin tier: why this block is not promotable. Keyed by
#: every non-``project`` value :data:`~scistudio.core.origins.BLOCK_SURFACE`
#: can return, so a new tier cannot be added without this table noticing —
#: ``_refusal_for`` raises rather than guessing when a key is missing.
_REFUSAL_BY_ORIGIN = {
    "builtin": (
        "is a built-in block, so it already lives in a library and cannot be promoted. "
        "Only blocks in the current project's blocks/ directory are promotable."
    ),
    "package": (
        "comes from an installed plugin package, so it already lives in a library and "
        "cannot be promoted. Only blocks in the current project's blocks/ directory are "
        "promotable."
    ),
    "user": (
        "is already in the user library. Nothing to promote — tell the user it is available in every project already."
    ),
    "custom": (
        "is a drop-in whose source file resolves outside both the current project's "
        "blocks/ directory and the user library, so there is no project copy to promote. "
        "This is what the palette shows as an unresolvable custom block; ask the user to "
        "move the file into the project before promoting it."
    ),
}


class PromoteToUserLibraryResult(BaseModel):
    """Result envelope for ``promote_to_user_library``."""

    block_type: str = Field(description="The block type that was promoted.")
    source_path: str = Field(description="Absolute path of the file that was copied from.")
    path: str = Field(description="Absolute path of the new file in the user library.")
    filename: str = Field(description="Filename the block now has in the user library.")
    bytes_written: int = Field(description="Number of bytes written to the destination.")
    overwritten: bool = Field(description="True when an existing library file was replaced.")
    added: list[str] = Field(
        default_factory=list,
        description="Block type names that appeared after the post-promotion registry refresh.",
    )
    removed: list[str] = Field(
        default_factory=list,
        description="Block type names that disappeared after the post-promotion registry refresh.",
    )
    next_step: str = Field(
        default=(
            "The block is now in the user library and is discoverable without a restart. "
            "Call mcp__scistudio__list_blocks to confirm, and tell the user it is available "
            "in every project from now on. If the block imports a project-local custom type, "
            "that type is still project-local and the promoted block will fail to load "
            "elsewhere until it is promoted too."
        ),
        description="Suggested next MCP call and what to tell the user.",
    )


def _library_filename(name: str) -> str:
    """Return *name* if it is a bare ``.py`` basename, else raise ``ValueError``.

    Rejected before any filesystem access: a separator, a Windows drive (a
    drive-relative ``C:evil.py`` has a harmless-looking ``Path.name``), an
    absolute form, a ``..`` segment, a control character, a leading dot, or
    anything but an exact ``.py`` extension. The extension test is
    case-sensitive for the reason the HTTP endpoint's is: a ``.PY`` file is a
    live drop-in on Windows and dead on POSIX, so the product declines to
    create one.
    """
    candidate = name.strip()
    drive, _ = os.path.splitdrive(candidate)
    if (
        not candidate
        or drive
        or os.path.isabs(candidate)
        or "/" in candidate
        or "\\" in candidate
        or candidate in (".", "..")
        or candidate.startswith(".")
        or any(character < " " or character == "\x7f" for character in candidate)
        or Path(candidate).name != candidate
        or not candidate.endswith(_ALLOWED_SUFFIX)
        or candidate == _ALLOWED_SUFFIX
    ):
        raise ValueError(f"{name!r} is not a valid user library filename; pass a bare '<name>.py'")
    return candidate


def _refusal_for(origin: str) -> str:
    """Return the agent-facing reason a block with *origin* is not promotable.

    Raises ``KeyError`` for an origin the table does not cover, which is a
    programming error rather than a user-facing case: the table is keyed by
    :attr:`~scistudio.core.origins.OriginSurface.vocabulary` minus ``project``,
    and a new tier must arrive here deliberately rather than fall through to a
    vague message.
    """
    return _REFUSAL_BY_ORIGIN[origin]


@mcp.tool(name="promote_to_user_library", tags={"category:library", "write"})
async def promote_to_user_library(
    block_type: Annotated[
        str,
        Field(description="Registered block type name to copy into the user library (from list_blocks)."),
    ],
    new_name: Annotated[
        str | None,
        Field(
            description=(
                "Optional destination filename, e.g. 'normalize_v2.py'. Must be a bare "
                "'<name>.py'. Use this as the save-as-new-name answer when a promotion "
                "collided with an existing library file."
            ),
        ),
    ] = None,
    overwrite: Annotated[
        bool,
        Field(
            description=(
                "Replace an existing library file of the same name. Ask the user first — "
                "the default refuses and reports the collision so they can choose "
                "overwrite or a new name."
            ),
        ),
    ] = False,
) -> PromoteToUserLibraryResult:
    """Copy a project-local block into the user's personal library.

    Use when:
      - The user just ran a block you authored successfully and it is worth
        reusing in other projects — offer promotion at that moment.
      - The user asks to save, keep, or reuse a block across projects.

    Do NOT use to:
      - Promote anything whose resolved origin is not ``project``: a built-in
        or packaged block already lives in a library, one already in the user
        library has nowhere to go, and one whose file resolves under neither
        tier root has no project copy to promote. All four are refused, which
        is exactly what the palette, the canvas node and the editor toolbar do
        by hiding the action.
      - Move a block — this copies, and the project keeps its own file.
      - Write arbitrary files into the user's home directory; only a registered
        block's own source is copied, and only into the library blocks
        directory.

    Raises ``KeyError`` for an unregistered type, ``RuntimeError`` when the
    block's resolved origin is not ``project``,
    ``FileExistsError`` on a collision without ``overwrite``, ``ValueError``
    for an invalid ``new_name``, and ``PermissionError`` if a name somehow
    resolves outside the library.
    """
    ctx = get_context()
    spec = ctx.block_registry.get_spec(block_type)
    if spec is None:
        raise KeyError(f"Block type '{block_type}' is not registered")

    # FR-019 / FR-003: one condition, resolved by the function that fills the
    # ``origin`` field E1, E2 and E5 read. Anything but ``project`` is refused.
    origin = map_block_origin(spec, project_dir=ctx.project_dir)
    if origin != PROJECT_ORIGIN:
        raise RuntimeError(f"'{block_type}' {_refusal_for(origin)}")

    raw_source = getattr(spec, "file_path", None)
    source = Path(os.path.realpath(str(raw_source)))
    if not source.is_file():
        raise FileNotFoundError(f"Block source file not found: {source}")

    library = user_blocks_dir()
    library.mkdir(parents=True, exist_ok=True)
    library_root = Path(os.path.realpath(str(library)))

    filename = _library_filename(new_name or source.name)
    destination = _safe_under(library_root, Path(filename))
    if destination.parent != library_root:
        raise PermissionError(f"{filename!r} does not resolve directly inside the user library")

    overwritten = destination.exists()
    if overwritten and not overwrite:
        raise FileExistsError(
            f"{destination.name} already exists in the user library. Ask the user whether to "
            "overwrite it (retry with overwrite=True) or save under a different name "
            "(retry with new_name='<other>.py')."
        )

    payload = source.read_bytes()
    _atomic_write(destination, payload)

    added, removed = refresh_context_registries(ctx)
    await broadcast_blocks_reloaded(ctx, added=added, removed=removed, source="agent")
    logger.info("promote_to_user_library: %s -> %s (overwritten=%s)", source, destination, overwritten)

    return PromoteToUserLibraryResult(
        block_type=block_type,
        source_path=str(source),
        path=str(destination),
        filename=destination.name,
        bytes_written=len(payload),
        overwritten=overwritten,
        added=added,
        removed=removed,
    )


def _atomic_write(destination: Path, payload: bytes) -> None:
    """Write *payload* to *destination* through a temp file plus ``os.replace``.

    A partially written file in a drop-in directory is a block the next scan
    tries to import, so the destination must never be observable half-written.

    The temp file must share the destination's directory for ``os.replace`` to
    be atomic, and that directory is globbed for ``*.py`` and executed on every
    scan — hence :data:`_WRITE_TEMP_SUFFIX` rather than ``.py``, so the temp
    file is not itself a drop-in while it exists. Cleanup catches every
    exception rather than only ``OSError``, because whatever escapes it leaves
    that file behind permanently
    (``docs/audit/2026-08-07-adr-053-spec1-write-path.md`` P2-2).
    """
    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix=".__scistudio_promote_",
        suffix=_WRITE_TEMP_SUFFIX,
        dir=str(destination.parent),
    )
    try:
        with os.fdopen(tmp_fd, "wb") as tmp_file:
            tmp_file.write(payload)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        os.replace(tmp_path, destination)
    except Exception:
        with suppress(OSError):
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        raise
