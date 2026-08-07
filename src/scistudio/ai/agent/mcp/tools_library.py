"""Category (f) MCP tool — promotion into the personal tool library (1 tool).

ADR-053 ``docs/specs/adr-053-personal-tool-library.md`` §4 FR-011 and §6.2 E3.
Promotion is reachable from five entry points and this is the agent's: without
it the agent cannot act on the promotion opportunities ADR-053 §3 expects it to
offer — for instance right after it authors a block the user runs successfully.

Promotion **copies** (FR-017). The originating project keeps working exactly as
before; the copy is what becomes reusable across projects.

Three refusals, and each is a real case rather than defensiveness:

* A block with no source file is built-in or packaged. It already lives in a
  library, so promoting it is meaningless (FR-019).
* A block whose file already resolves inside ``~/.scistudio/blocks/`` is
  already at the destination. Copying it onto itself would raise a collision
  prompt about a file the user just promoted (FR-019 again).
* An existing destination file is reported rather than overwritten, and
  overwriting requires ``overwrite=True`` (FR-008/FR-018). ``new_name`` is the
  save-as-new-name half of the same prompt.

Layering: this module sits in the AI layer, which must not import
``scistudio.api`` (the import-linter contract "AI must not depend on api"), so
it reaches the user library through :mod:`scistudio.core.dropins` — the same
single answer to "where does the user tier live" the HTTP endpoint uses
(FR-058) — and it never spells out ``~/.scistudio`` itself.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, Field

from scistudio.ai.agent.mcp._context import _safe_under, get_context
from scistudio.ai.agent.mcp._reload import broadcast_blocks_reloaded, refresh_context_registries
from scistudio.ai.agent.mcp.server import mcp
from scistudio.core.dropins import user_blocks_dir

logger = logging.getLogger(__name__)

_ALLOWED_SUFFIX = ".py"


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
    absolute form, a ``..`` segment, or a non-Python extension.
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
        or Path(candidate).name != candidate
        or Path(candidate).suffix.lower() != _ALLOWED_SUFFIX
    ):
        raise ValueError(f"{name!r} is not a valid user library filename; pass a bare '<name>.py'")
    return candidate


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
      - Promote a built-in or packaged block; those already live in a library
        and the call is refused.
      - Move a block — this copies, and the project keeps its own file.
      - Write arbitrary files into the user's home directory; only a registered
        block's own source is copied, and only into the library blocks
        directory.

    Raises ``KeyError`` for an unregistered type, ``RuntimeError`` when the
    block has no promotable source file or is already in the library,
    ``FileExistsError`` on a collision without ``overwrite``, ``ValueError``
    for an invalid ``new_name``, and ``PermissionError`` if a name somehow
    resolves outside the library.
    """
    ctx = get_context()
    spec = ctx.block_registry.get_spec(block_type)
    if spec is None:
        raise KeyError(f"Block type '{block_type}' is not registered")

    raw_source = getattr(spec, "file_path", None)
    if not raw_source:
        raise RuntimeError(
            f"'{block_type}' is a built-in or packaged block, so it already lives in a library "
            "and cannot be promoted. Only drop-in blocks with a source file are promotable."
        )
    source = Path(os.path.realpath(str(raw_source)))
    if not source.is_file():
        raise FileNotFoundError(f"Block source file not found: {source}")

    library = user_blocks_dir()
    library.mkdir(parents=True, exist_ok=True)
    library_root = Path(os.path.realpath(str(library)))
    if source.parent == library_root:
        raise RuntimeError(
            f"'{block_type}' is already in the user library at {source}. "
            "Nothing to promote — tell the user it is available in every project already."
        )

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
    """
    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix=".__scistudio_promote_",
        suffix=_ALLOWED_SUFFIX,
        dir=str(destination.parent),
    )
    try:
        with os.fdopen(tmp_fd, "wb") as tmp_file:
            tmp_file.write(payload)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        os.replace(tmp_path, destination)
    except OSError:
        try:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except OSError:
            pass
        raise
