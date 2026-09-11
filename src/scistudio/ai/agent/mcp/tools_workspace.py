"""External-audience workspace tools."""
# Maintainer context (kept outside generated API documentation):
# External-audience workspace tools (ADR-055 Spec 2 §5.2, #2279).
#
# An external AI agent driving SciStudio through the WebMCP bridge has no
# filesystem of its own beside the backend. These tools give it one, under the
# owner decisions recorded on issue #2279:
#
# * **Inspect** (read-tagged) — ``list_directory``, ``get_file_info``,
#   ``search_files``, ``read_file``. They accept absolute paths and read anything
#   the backend's OS user can read; a project-relative path resolves against the
#   active project. Reads are bounded *while streaming* — a file is never
#   materialized to produce a slice of it — and every truncation is reported with
#   the file's total size.
# * **Author** (write-tagged) — ``write_file``, ``create_directory``,
#   ``patch_file``, ``move_path`` (rename or move), ``delete_path``. They are
#   confined to the active project and go through the editor's shared write path
#   (``MCPContext.project_files``: atomic write, ``file.changed`` to the UI,
#   block reload), never a bare write. A server-side blacklist mirrors the
#   provisioned local hooks: any mutation whose source or target is
#   ``workflows/*.yaml|*.yml`` or anything under ``data/`` is refused with a
#   pointer to the tool that owns that surface.
#
# Hook parity lives in the results: an author write to ``blocks/*.py`` is refused
# until ``list_blocks`` has run once in this backend lifetime, and a successful
# one carries non-blocking warnings for generic port types (the provisioned
# ``enforce_concrete_port_types`` scan, reused rather than re-implemented).
#
# Every tool carries the ``audience:external`` tag, so local agents — which have
# native file tools — never see them. Policy refusals and conflicts come back as
# results (``status`` + ``refusal``) because the bridge withholds exception text
# from external hosts; unexpected failures still raise.
#
# Logging records the tool name and outcome only — never paths, contents, or
# arguments (FR-012).
# Development references: #2279, ADR-055, FR-012, Spec 2.

from __future__ import annotations

import asyncio
import base64
import codecs
import contextlib
import fnmatch
import functools
import json
import logging
import os
import queue
import re
import stat as stat_module
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import IO, Annotated, Any, Literal

from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.middleware.middleware import CallNext
from fastmcp.tools.base import ToolResult
from mcp.types import CallToolRequestParams, CallToolResult
from pydantic import BaseModel, Field

from scistudio.ai.agent.mcp._context import ProjectFileWriter, get_context, get_project_files
from scistudio.ai.agent.mcp.server import AUDIENCE_EXTERNAL_TAG, mcp
from scistudio.ai.agent.mcp.tools_workflow.read import list_blocks_called

logger = logging.getLogger(__name__)

READ_DEFAULT_LIMIT_BYTES = 256 * 1024
"""Default byte window ``read_file`` returns."""

READ_MAX_LIMIT_BYTES = 1024 * 1024
"""Largest window one ``read_file`` call may request; larger limits are clamped."""

_READ_CHUNK_BYTES = 64 * 1024
_BINARY_SNIFF_BYTES = 8192

WRITE_CONTENT_CAP_BYTES = 10 * 1024 * 1024
"""Largest content an author tool accepts — the editor cap."""
# Development references: ADR-036.

LIST_DEFAULT_ENTRIES = 200
LIST_MAX_ENTRIES = 1000
_LIST_SCAN_CEILING = 100_000

SEARCH_DEFAULT_RESULTS = 50
SEARCH_MAX_RESULTS = 200
_SEARCH_MAX_ENTRIES = 20_000
"""Directory entries (files and directories, matching or not) one search may visit."""

_SEARCH_TIME_BUDGET_SECONDS = 20.0
"""Wall-clock budget for one search walk (a slow or huge root such as ``/`` or a network share)."""
_SEARCH_FILE_BYTES_CAP = 2 * 1024 * 1024
_SEARCH_MAX_LINE_BYTES = 64 * 1024
_REGEX_REPLY_POLL_SECONDS = 0.05
"""How often a search waiting on its regular-expression process checks the deadline and stop flag."""
_SEARCH_SNIPPET_CHARS = 200
_SEARCH_HITS_PER_FILE = 20
_SEARCH_SKIP_DIRS = frozenset({".git", "node_modules", "__pycache__"})

_TREE_POLICY_FILE_LIMIT = 2000
"""Most files a directory move/delete is checked for; mirrors the shared write path's limit."""

_AFFECTED_PATHS_CAP = 50

_READ_TAGS = {"category:workspace", "read", AUDIENCE_EXTERNAL_TAG}
_WRITE_TAGS = {"category:workspace", "write", AUDIENCE_EXTERNAL_TAG}

# The provisioned enforce_list_blocks_before_block_write hook's block-file pattern.
_BLOCK_FILE_RE = re.compile(r"(?:^|/)blocks/[^/]+\.py$", re.IGNORECASE)

_WORKFLOW_YAML_MESSAGE = (
    "workflows/*.yaml is managed by write_workflow (schema-validated) and update_block_config "
    "(preserves comments); edit_workflow applies targeted edits. Direct file writes bypass "
    "validation, so the workspace tools refuse them."
)
_DATA_DIR_MESSAGE = (
    "The project's data/ directory is protected: the agent must not directly create, edit, move, "
    "or delete files under data/. Produce or change data by running workflow blocks "
    "(run_workflow). Reading data/ and editing files outside data/ is fine."
)
_LIST_BLOCKS_MESSAGE = (
    "Authoring a custom block requires calling list_blocks first to confirm no existing block "
    "matches your I/O contract. Call list_blocks now, then retry. (Tracked once per backend "
    "lifetime; a backend restart resets it.)"
)

# Tests patch this to count the bytes a read pulls from disk.
_open_binary: Callable[[Path], Any] = functools.partial(open, mode="rb")


# ---------------------------------------------------------------------------
# Result models.
# ---------------------------------------------------------------------------


class ToolRefusal(BaseModel):
    """Why a tool call was refused or conflicted, and what to do instead.

    The structured refusal model. ``scistudio.api.seam.ToolRefusal`` is the
    exception an edition raises inside a tool to return one of these.
    """

    code: str = Field(description="Machine-readable reason, e.g. 'protected_data_dir' or 'stale_version'.")
    message: str = Field(description="Explanation the agent can act on.")
    use_instead: list[str] = Field(default_factory=list, description="Tools that own the refused operation.")


class WorkspaceResult(BaseModel):
    """Fields every workspace tool result carries."""

    status: str = Field(
        default="ok",
        description="'ok', 'refused' (a rule stopped the call; nothing changed), or 'conflict' (see refusal).",
    )
    refusal: ToolRefusal | None = Field(default=None, description="Set when status is not 'ok'.")


class DirectoryEntry(BaseModel):
    """One entry of ``list_directory``."""

    name: str
    path: str = Field(description="Project-relative POSIX path inside the project, else absolute.")
    type: str = Field(description="'file', 'directory', 'symlink', or 'other'.")
    size_bytes: int | None = None
    modified_at: float | None = Field(default=None, description="POSIX mtime.")


class ListDirectoryResult(WorkspaceResult):
    """Result envelope for ``list_directory``."""

    path: str = ""
    entries: list[DirectoryEntry] = Field(default_factory=list)
    total_entries: int = Field(default=0, description="Entries in the directory (see total_is_lower_bound).")
    total_is_lower_bound: bool = Field(default=False, description="True when counting stopped at the scan ceiling.")
    truncated: bool = Field(default=False, description="True when entries holds fewer than total_entries.")


class FileInfoResult(WorkspaceResult):
    """Result envelope for ``get_file_info``."""

    path: str = ""
    absolute_path: str = ""
    exists: bool = False
    type: str | None = None
    size_bytes: int | None = None
    modified_at: float | None = None
    readable: bool = False
    within_project: bool = False
    state_version: int | None = Field(
        default=None,
        description="Current state version for a project file; pass it as expected_state_version to author tools.",
    )
    looks_binary: bool | None = None
    writable_by_author_tools: bool = False
    author_tools_note: str | None = Field(default=None, description="Why author tools would refuse this path.")


class SearchHit(BaseModel):
    """One match from ``search_files``."""

    path: str
    line: int | None = Field(default=None, description="1-based line of a content match; None for name-only search.")
    snippet: str | None = None


class SearchFilesResult(WorkspaceResult):
    """Result envelope for ``search_files``."""

    root: str = ""
    hits: list[SearchHit] = Field(default_factory=list)
    files_scanned: int = Field(default=0, description="Files whose name matched and were examined.")
    entries_visited: int = Field(default=0, description="Directory entries the walk visited, matching or not.")
    truncated: bool = Field(default=False, description="True when a result, file, or size bound stopped the search.")
    notes: list[str] = Field(default_factory=list, description="Which bounds applied and what was skipped.")


class ReadFileResult(WorkspaceResult):
    """Result envelope for ``read_file``."""

    path: str = ""
    absolute_path: str = ""
    encoding: str = "utf-8"
    content: str = ""
    offset: int = Field(default=0, description="Byte offset the returned content starts at.")
    bytes_returned: int = Field(default=0, description="Bytes of the file the content covers.")
    limit_applied: int = Field(default=0, description="Byte window actually used (requests above the max are clamped).")
    truncated: bool = Field(default=False, description="True when the file continues past the returned window.")
    next_offset: int | None = Field(default=None, description="Offset to pass to continue reading, when truncated.")
    total_size_bytes: int | None = Field(default=None, description="Size of the whole file (None for special files).")
    state_version: int | None = Field(default=None, description="Current state version for a project file.")


class AuthorResult(WorkspaceResult):
    """Result envelope for the author tools."""

    path: str = ""
    kind: str | None = Field(default=None, description="'created', 'modified', 'deleted', or 'moved'.")
    state_version: int | None = Field(default=None, description="The file's state version after the write.")
    size_bytes: int | None = None
    replacements: int | None = Field(default=None, description="patch_file: occurrences replaced.")
    affected_paths: list[str] = Field(
        default_factory=list,
        description="'<kind>:<project-relative path>' for each file-change event emitted to the UI.",
    )
    affected_truncated: bool = False
    registry_refreshed: bool = Field(
        default=False,
        description="True when the change rebuilt the block/type registries (a lint-clean drop-in save).",
    )
    warnings: list[str] = Field(default_factory=list, description="Non-blocking advisories (e.g. generic port types).")
    expected_state_version: int | None = None
    current_state_version: int | None = None
    next_step: str = Field(
        default=(
            "Re-read with read_file to verify. Pass the returned state_version as expected_state_version "
            "on the next write to the same file so a concurrent change is detected."
        ),
    )


# ---------------------------------------------------------------------------
# Failure outcomes carry the MCP error flag (owner decision 2026-09-11, #2279).
#
# Refusals, write conflicts, a command that exited non-zero, and a cancel that
# did not stop the command are failures: the host must see ``isError: true``.
# They stay tool RESULTS (not exceptions), so the structured reason — status,
# refusal code, message, alternatives — survives the bridge, which withholds
# exception text. The tools keep returning their result models; one
# call-tool middleware sets the flag at the MCP boundary for the tools that
# registered a failure rule.
# ---------------------------------------------------------------------------


class FlaggedToolResult(ToolResult):
    """A tool result carrying the MCP error flag, with its structured content intact."""

    is_error: bool = False

    def to_mcp_result(self) -> CallToolResult:  # type: ignore[override]
        """Native MCP transports receive ``isError`` alongside the structured content.

        Built from the wire (alias) keys, which validate on every supported mcp
        release: mcp 1.x names the fields ``structuredContent`` / ``isError``,
        mcp 2.x names them ``structured_content`` / ``is_error`` with those
        camelCase aliases (fastmcp 3.x and 4.x respectively).
        """
        data: dict[str, Any] = {
            "content": self.content,
            "structuredContent": self.structured_content,
            "isError": self.is_error,
        }
        if self.meta is not None:
            data["_meta"] = self.meta
        return CallToolResult.model_validate(data)


def status_is_failure(structured: dict[str, Any]) -> bool:
    """The default failure rule: a refusal or a conflict."""
    return structured.get("status") in {"refused", "conflict"}


_FAILURE_RULES: dict[str, Callable[[dict[str, Any]], bool]] = {}


def register_failure_outcome(tool_name: str, rule: Callable[[dict[str, Any]], bool] = status_is_failure) -> None:
    """Mark *tool_name*'s results as failures (``isError: true``) whenever *rule* says so."""
    _FAILURE_RULES[tool_name] = rule


def flag_failure(result: ToolResult, tool_name: str) -> ToolResult:
    """Return *result* flagged as an error when its tool's failure rule matches its structured content."""
    rule = _FAILURE_RULES.get(tool_name)
    structured = result.structured_content
    if rule is None or not isinstance(structured, dict) or not rule(structured):
        return result
    flagged = FlaggedToolResult(content=result.content, structured_content=structured, meta=result.meta)
    flagged.is_error = True
    return flagged


class _FailureOutcomeMiddleware(Middleware):
    """Sets ``isError`` on failure outcomes of the tools that registered a rule."""

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        result = await call_next(context)
        return flag_failure(result, context.message.name)


mcp.add_middleware(_FailureOutcomeMiddleware())


# ---------------------------------------------------------------------------
# Refusals and path resolution.
# ---------------------------------------------------------------------------


class _RefusedError(Exception):
    """Internal: a policy refusal the tool turns into a result."""

    def __init__(self, code: str, message: str, use_instead: list[str] | None = None, *, status: str = "refused"):
        super().__init__(message)
        self.status = status
        self.refusal = ToolRefusal(code=code, message=message, use_instead=list(use_instead or []))


def list_blocks_refusal() -> ToolRefusal:
    """The server-side ``enforce_list_blocks_before_block_write`` refusal."""
    return ToolRefusal(code="list_blocks_required", message=_LIST_BLOCKS_MESSAGE, use_instead=["list_blocks"])


def _log_outcome(tool: str, status: str, refusal: ToolRefusal | None = None) -> None:
    logger.info("workspace tool=%s outcome=%s code=%s", tool, status, refusal.code if refusal else "-")


def _project_root() -> Path | None:
    root = get_context().project_dir
    return Path(os.path.realpath(root)) if root is not None else None


def _within(root: Path, target: Path) -> bool:
    try:
        return os.path.commonpath([str(root), str(target)]) == str(root)
    except ValueError:  # different drives on Windows
        return False


def _relative_posix(root: Path, target: Path) -> str:
    rel = os.path.relpath(target, root).replace("\\", "/")
    return "." if rel in ("", ".") else rel


def _display_path(target: Path, root: Path | None) -> str:
    if root is not None and _within(root, target):
        return _relative_posix(root, target)
    return str(target)


def _resolve_inspect_path(path: str) -> tuple[Path, Path | None]:
    """Absolute paths as given; relative paths against the active project."""
    root = _project_root()
    raw = Path(os.path.expanduser((path or ".").strip() or "."))
    if not raw.is_absolute():
        if root is None:
            raise _RefusedError(
                "no_active_project",
                "Relative paths resolve against the active project, and no project is open. "
                "Pass an absolute path, or open a project first.",
                ["get_agent_context"],
            )
        raw = root / raw
    return Path(os.path.realpath(raw)), root


def _blacklist_refusal(rel_posix: str) -> _RefusedError | None:
    """The server-side mirror of the protect_data_dir / protect_workflow_yaml hooks."""
    parts = [part for part in rel_posix.split("/") if part not in ("", ".")]
    if not parts:
        return None
    first = parts[0].casefold()
    if first == "data":
        return _RefusedError("protected_data_dir", _DATA_DIR_MESSAGE, ["run_workflow"])
    if first == "workflows" and len(parts) >= 2 and parts[-1].casefold().endswith((".yaml", ".yml")):
        return _RefusedError(
            "protected_workflow_yaml",
            _WORKFLOW_YAML_MESSAGE,
            ["write_workflow", "update_block_config", "edit_workflow"],
        )
    return None


def _resolve_author_path(
    path: str, *, follow_final: bool = True, project_root: Path | None = None
) -> tuple[Path, Path, str]:
    """Resolve an author-tool path: project-confined, blacklist-checked.

    Returns ``(mutated_path, project_root, project_relative_posix)`` for the path
    the operation will actually change. A write (``follow_final=True``) changes
    the file a link points to, so the fully resolved path is confined and
    checked. A delete or move (``follow_final=False``) changes the link itself
    (lstat semantics): only the parent directories are resolved and the link's
    own location is confined and checked — it never follows a link to delete or
    move what it points to. The lexical path is checked
    against the blacklist as well.

    ``project_root`` defaults to the active project; the seam's
    ``check_author_path`` passes an edition's project root explicitly.
    """
    # Maintainer context:
    # Returns ``(mutated_path, project_root, project_relative_posix)`` for the path
    # the operation will actually change. A write (``follow_final=True``) changes
    # the file a link points to, so the fully resolved path is confined and
    # checked. A delete or move (``follow_final=False``) changes the link itself
    # (lstat semantics): only the parent directories are resolved and the link's
    # own location is confined and checked — it never follows a link to delete or
    # move what it points to (audit AU3 P1-1). The lexical path is checked
    # against the blacklist as well. The explicit project_root is for the
    # identity seam's check_author_path (#2328).
    # Development references: #2279, #2328.
    root = _project_root() if project_root is None else Path(os.path.realpath(project_root))
    if root is None:
        raise _RefusedError(
            "no_active_project",
            "Author tools write inside the active project, and no project is open. Open a project first.",
        )
    raw = Path(os.path.expanduser((path or "").strip()))
    lexical = Path(os.path.normpath(raw if raw.is_absolute() else root / raw))
    if follow_final:
        mutated = Path(os.path.realpath(lexical))
    else:
        head, tail = os.path.split(lexical)
        mutated = Path(os.path.join(os.path.realpath(head), tail)) if tail else Path(os.path.realpath(lexical))
    if not _within(root, mutated):
        raise _RefusedError(
            "outside_project",
            "Author tools only change files inside the active project. Inspect tools can read other "
            "paths; use run_command for changes elsewhere.",
            ["run_command"],
        )
    rel = _relative_posix(root, mutated)
    for candidate in (rel, _relative_posix(root, lexical) if _within(root, lexical) else None):
        if candidate is None:
            continue
        refusal = _blacklist_refusal(candidate)
        if refusal is not None:
            raise refusal
    return mutated, root, rel


def _require_block_list(rel_posix: str) -> None:
    if _BLOCK_FILE_RE.search(rel_posix) and not list_blocks_called():
        refusal = list_blocks_refusal()
        raise _RefusedError(refusal.code, refusal.message, refusal.use_instead)


def _require_project_files() -> ProjectFileWriter:
    files = get_project_files(get_context())
    if files is None:
        raise _RefusedError(
            "write_path_unavailable",
            "This SciStudio context has no shared write path (for example the standalone MCP bridge). "
            "Author tools only write through the backend so the open UI stays in sync.",
        )
    return files


_FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_LINK_REPARSE_TAGS = frozenset({0xA0000003, 0xA000000C})  # junction, symlink


def _is_link(path: Path) -> bool:
    """A symlink or Windows junction, judged without following it (mirrors the shared write path)."""
    try:
        info = os.lstat(path)
    except OSError:
        return False
    if stat_module.S_ISLNK(info.st_mode):
        return True
    attributes = getattr(info, "st_file_attributes", 0)
    return bool(attributes & _FILE_ATTRIBUTE_REPARSE_POINT) and getattr(info, "st_reparse_tag", 0) in _LINK_REPARSE_TAGS


def _tree_files(directory: Path) -> list[Path]:
    """Every entry a tree operation touches; a link inside the tree is one entry, never descended."""
    found: list[Path] = []
    pending = [directory]
    while pending:
        with os.scandir(pending.pop()) as entries:
            for entry in entries:
                path = Path(entry.path)
                if not _is_link(path) and entry.is_dir(follow_symlinks=False):
                    pending.append(path)
                    continue
                found.append(path)
                if len(found) > _TREE_POLICY_FILE_LIMIT:
                    raise _RefusedError(
                        "too_many_entries",
                        f"The directory holds more than {_TREE_POLICY_FILE_LIMIT} files; one author-tool call touches "
                        "at most that many. Use run_command for bulk reorganization.",
                        ["run_command"],
                    )
    return found


def _check_tree(root: Path, directory: Path, destination: Path | None = None) -> None:
    """Apply the blacklist (and block rule for moves) to every file a tree operation touches."""
    for path in _tree_files(directory):
        refusal = _blacklist_refusal(_relative_posix(root, path))
        if refusal is not None:
            raise refusal
        if destination is not None:
            moved_rel = _relative_posix(root, destination / path.relative_to(directory))
            refusal = _blacklist_refusal(moved_rel)
            if refusal is not None:
                raise refusal
            _require_block_list(moved_rel)


# ---------------------------------------------------------------------------
# Hook parity: generic port types (enforce_concrete_port_types).
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def _port_type_scanner() -> tuple[Callable[..., Any], Callable[..., Any]] | None:
    """Load the scanner from the provisioned hook template itself.

    Reuse, not a copy: the template is read through the same loader
    provisioning uses and executed in a private namespace (its ``main`` stays
    behind the ``__main__`` guard), so the server-side warning can never drift
    from what the local hook reports.
    """
    try:
        from scistudio.agent_provisioning.hooks import _load_template

        source = _load_template("hook_enforce_concrete_port_types.py")
        namespace: dict[str, Any] = {"__name__": "scistudio_provisioned_hook_enforce_concrete_port_types"}
        exec(compile(source, "hook_enforce_concrete_port_types.py", "exec"), namespace)
        return namespace["_scan_for_generic_ports"], namespace["_format_message"]
    except Exception:
        logger.warning("port-type check unavailable: the provisioned hook template did not load", exc_info=True)
        return None


def port_type_warnings(rel_posix: str, content: str) -> list[str]:
    """Non-blocking warnings for generic ``InputPort``/``OutputPort`` types in a block file."""
    if not _BLOCK_FILE_RE.search(rel_posix):
        return []
    scanner = _port_type_scanner()
    if scanner is None:
        return []
    scan, format_message = scanner
    return [format_message(Path(rel_posix), lineno, port, reason) for lineno, port, reason in scan(content)]


# ---------------------------------------------------------------------------
# Bounded reads.
# ---------------------------------------------------------------------------


def _read_window(target: Path, offset: int, limit: int) -> tuple[bytes, int | None, bool]:
    """Read at most *limit* bytes from *offset*; return ``(data, total_size, more)``.

    Bounded while streaming: bytes land in a buffer sized to the window, in
    chunks, and a one-byte probe decides whether the file continues — the
    rest of the file is never read.
    """
    with _open_binary(target) as handle:
        info = os.fstat(handle.fileno())
        total = info.st_size if stat_module.S_ISREG(info.st_mode) else None
        if offset:
            handle.seek(offset)
        size = limit if total is None else max(0, min(limit, total - offset))
        buffer = bytearray(size)
        view = memoryview(buffer)
        filled = 0
        while filled < size:
            got = handle.readinto(view[filled : min(size, filled + _READ_CHUNK_BYTES)])
            if not got:
                break
            filled += got
        more = bool(handle.read(1)) if filled == size else False
    return bytes(buffer[:filled]), total, more


def _decode_window(data: bytes, *, at_start: bool, more: bool) -> tuple[str, int, int] | None:
    """Decode a UTF-8 window; return ``(text, skipped_leading, consumed)`` or ``None`` if binary.

    A window may start or end inside a multi-byte character. Leading
    continuation bytes are skipped (and reported through the offset); an
    incomplete trailing sequence is held back so ``next_offset`` resumes on a
    character boundary.
    """
    if b"\x00" in data[:_BINARY_SNIFF_BYTES]:
        return None
    skip = 0
    if not at_start:
        while skip < min(3, len(data)) and (data[skip] & 0xC0) == 0x80:
            skip += 1
    body = data[skip:]
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    try:
        text = decoder.decode(body, final=not more)
    except UnicodeDecodeError:
        return None
    pending = len(decoder.getstate()[0])
    return text, skip, len(body) - pending


def _looks_binary(target: Path) -> bool | None:
    try:
        with _open_binary(target) as handle:
            sample = handle.read(_BINARY_SNIFF_BYTES)
    except OSError:
        return None
    if b"\x00" in sample:
        return True
    try:
        codecs.getincrementaldecoder("utf-8")("strict").decode(sample, final=False)
    except UnicodeDecodeError:
        return True
    return False


def _entry_type(path: Path) -> str:
    if path.is_symlink():
        return "symlink"
    if path.is_dir():
        return "directory"
    if path.is_file():
        return "file"
    return "other"


# ---------------------------------------------------------------------------
# Inspect tools.
# ---------------------------------------------------------------------------


def _list_directory_sync(target: Path, root: Path | None, max_entries: int) -> ListDirectoryResult:
    if not target.exists():
        raise _RefusedError("not_found", "The directory does not exist.")
    if not target.is_dir():
        raise _RefusedError("not_a_directory", "The path is a file, not a directory.", ["get_file_info", "read_file"])
    scanned: list[os.DirEntry[str]] = []
    lower_bound = False
    with os.scandir(target) as iterator:
        for entry in iterator:
            scanned.append(entry)
            if len(scanned) >= _LIST_SCAN_CEILING:
                lower_bound = True
                break

    def _is_dir(entry: os.DirEntry[str]) -> bool:
        try:
            return entry.is_dir()
        except OSError:
            return False

    scanned.sort(key=lambda entry: (not _is_dir(entry), entry.name.casefold()))
    entries: list[DirectoryEntry] = []
    for entry in scanned[:max_entries]:
        path = Path(entry.path)
        size: int | None = None
        mtime: float | None = None
        try:
            info = entry.stat()
            size = info.st_size if not _is_dir(entry) else None
            mtime = info.st_mtime
        except OSError:
            pass
        entries.append(
            DirectoryEntry(
                name=entry.name,
                path=_display_path(path, root),
                type="symlink" if entry.is_symlink() else ("directory" if _is_dir(entry) else "file"),
                size_bytes=size,
                modified_at=mtime,
            )
        )
    return ListDirectoryResult(
        path=_display_path(target, root),
        entries=entries,
        total_entries=len(scanned),
        total_is_lower_bound=lower_bound,
        truncated=len(entries) < len(scanned) or lower_bound,
    )


@mcp.tool(name="list_directory", tags=_READ_TAGS)
async def list_directory(
    path: Annotated[
        str,
        Field(
            description="Directory to list: project-relative, or absolute (any directory the backend user can read)."
        ),
    ] = ".",
    max_entries: Annotated[int, Field(description=f"Entries to return (1-{LIST_MAX_ENTRIES}).")] = LIST_DEFAULT_ENTRIES,
) -> ListDirectoryResult:
    """List a directory beside the SciStudio backend: names, types, sizes, mtimes.

    Directories come first, then files, by name. Relative paths resolve
    against the active project; absolute paths may point anywhere the backend's
    OS user can read (for example a shared dataset directory, used in place).
    ``truncated`` and ``total_entries`` say when the listing was cut.
    """
    try:
        target, root = _resolve_inspect_path(path)
        bounded = max(1, min(int(max_entries), LIST_MAX_ENTRIES))
        result = await asyncio.to_thread(_list_directory_sync, target, root, bounded)
    except _RefusedError as refused:
        result = ListDirectoryResult(status=refused.status, refusal=refused.refusal, path=path)
    except PermissionError:
        result = ListDirectoryResult(
            status="refused",
            refusal=ToolRefusal(code="permission_denied", message="The backend user cannot read this directory."),
            path=path,
        )
    _log_outcome("list_directory", result.status, result.refusal)
    return result


def _author_note(target: Path, root: Path | None) -> str | None:
    if root is None:
        return "No project is open; author tools need one."
    if not _within(root, target):
        return "Outside the active project; author tools only change files inside it."
    refusal = _blacklist_refusal(_relative_posix(root, target))
    return refusal.refusal.message if refusal is not None else None


def _file_info_sync(target: Path, root: Path | None, files: ProjectFileWriter | None) -> FileInfoResult:
    exists = target.exists()
    within = root is not None and _within(root, target)
    note = _author_note(target, root)
    result = FileInfoResult(
        path=_display_path(target, root),
        absolute_path=str(target),
        exists=exists,
        within_project=within,
        writable_by_author_tools=note is None,
        author_tools_note=note,
    )
    if not exists:
        return result
    info = target.stat()
    result.type = _entry_type(target)
    result.modified_at = info.st_mtime
    result.readable = os.access(target, os.R_OK)
    if target.is_file():
        result.size_bytes = info.st_size
        result.looks_binary = _looks_binary(target) if result.readable else None
        if within and files is not None:
            result.state_version = files.state_version(target)
    return result


@mcp.tool(name="get_file_info", tags=_READ_TAGS)
async def get_file_info(
    path: Annotated[str, Field(description="File or directory: project-relative, or absolute.")],
) -> FileInfoResult:
    """Return metadata for one path: existence, type, size, mtime, readability.

    For a project file it also returns ``state_version`` — pass it as
    ``expected_state_version`` to an author tool so a concurrent change is
    reported as a conflict instead of being overwritten — and whether the
    author tools may change it (``writable_by_author_tools`` / ``author_tools_note``).
    """
    try:
        target, root = _resolve_inspect_path(path)
        files = get_project_files(get_context())
        result = await asyncio.to_thread(_file_info_sync, target, root, files)
    except _RefusedError as refused:
        result = FileInfoResult(status=refused.status, refusal=refused.refusal, path=path)
    except PermissionError:
        result = FileInfoResult(
            status="refused",
            refusal=ToolRefusal(code="permission_denied", message="The backend user cannot inspect this path."),
            path=path,
        )
    _log_outcome("get_file_info", result.status, result.refusal)
    return result


def _iter_lines(path: Path) -> Iterator[tuple[int, str]] | None:
    """Yield ``(line_no, text)`` for at most the per-file byte cap; ``None`` for binary files."""
    handle = _open_binary(path)
    try:
        head = handle.read(_BINARY_SNIFF_BYTES)
        if b"\x00" in head:
            handle.close()
            return None
        handle.seek(0)
    except OSError:
        handle.close()
        return None

    def _lines() -> Iterator[tuple[int, str]]:
        consumed = 0
        line_no = 0
        try:
            while consumed < _SEARCH_FILE_BYTES_CAP:
                raw = handle.readline(_SEARCH_MAX_LINE_BYTES)
                if not raw:
                    return
                consumed += len(raw)
                line_no += 1
                yield line_no, raw.decode("utf-8", errors="replace")
        finally:
            handle.close()

    return _lines()


def _walk_stop_reason(result: SearchFilesResult, stop: threading.Event | None, deadline: float) -> str | None:
    """Why the search walk must stop now, or ``None`` to go on."""
    if stop is not None and stop.is_set():
        return "The search was stopped because its request ended."
    if result.entries_visited >= _SEARCH_MAX_ENTRIES:
        return f"Stopped after visiting {_SEARCH_MAX_ENTRIES} directory entries; narrow the path or name_pattern."
    if time.monotonic() > deadline:
        return f"Stopped after the {_SEARCH_TIME_BUDGET_SECONDS:g} s search time budget; narrow the path."
    return None


def _scan_stop_reason(stop: threading.Event | None, deadline: float) -> str | None:
    """Why scanning a file's content must stop now (request ended, budget spent), or ``None``."""
    if stop is not None and stop.is_set():
        return "The search was stopped because its request ended."
    if time.monotonic() > deadline:
        return f"Stopped after the {_SEARCH_TIME_BUDGET_SECONDS:g} s search time budget; narrow the path."
    return None


_REGEX_UNAVAILABLE_MESSAGE = (
    "A regular-expression search runs in a separate Python process, so that it can be stopped when the time "
    "budget runs out or the request ends, and that process could not be started. Search for plain text "
    "instead (regex=false)."
)
_REGEX_FAILED_MESSAGE = (
    "The process evaluating the regular expression ended unexpectedly. Simplify the pattern or search for "
    "plain text instead (regex=false)."
)

# The child program: stdlib only, run with ``-I -S`` so nothing from the user's
# environment or site-packages loads. It reads one JSON header (pattern, flags,
# lifetime), then answers each request -- one file's lines and a hit limit --
# with the index and column of every matching line, up to the limit.
_REGEX_WORKER_SOURCE = r"""
import json
import re
import signal
import sys

stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
header = json.loads(stdin.readline())
if hasattr(signal, "alarm"):
    signal.alarm(header["lifetime"])  # POSIX backstop: SIGALRM ends this process even mid-match
pattern = re.compile(header["pattern"], header["flags"])
for raw in iter(stdin.readline, b""):
    request = json.loads(raw)
    hits = []
    for index, text in enumerate(request["lines"]):
        found = pattern.search(text)
        if found is not None:
            hits.append([index, found.start()])
            if len(hits) >= request["limit"]:
                break
    stdout.write(json.dumps({"hits": hits}).encode("ascii") + b"\n")
    stdout.flush()
"""


class _RegexWorker:
    """Matches one search's regular expression in a child process the search can kill.

    Python cannot interrupt a regular-expression match once it has started, and
    a backtracking pattern such as ``(a+)+$`` or ``.*.*.*x`` can run for hours
    on one line, so no in-process bound on the pattern or the line holds
    (Codex review on). The search thread therefore hands each file's
    lines to this stdlib-only child interpreter and, while it waits for the
    answer, keeps checking its deadline and stop flag; when either fires, it
    kills the child mid-match. If the backend dies first, the child dies with
    it: a kill-on-close Job Object on Windows, ``SIGALRM`` on POSIX.
    """

    # Development references: #2292.

    def __init__(self, pattern: re.Pattern[str]) -> None:
        self._header = {
            "pattern": pattern.pattern,
            "flags": pattern.flags,
            "lifetime": int(_SEARCH_TIME_BUDGET_SECONDS) + 10,
        }
        self._process: subprocess.Popen[bytes] | None = None
        self._job: Any = None
        self._replies: queue.Queue[bytes] = queue.Queue()

    def _start(self) -> None:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        try:
            process = subprocess.Popen(
                [sys.executable, "-I", "-S", "-c", _REGEX_WORKER_SOURCE],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
        except OSError as exc:
            raise _RefusedError("regex_unavailable", _REGEX_UNAVAILABLE_MESSAGE) from exc
        self._process = process
        if sys.platform == "win32":
            from scistudio.engine.runners.platform import get_platform_ops

            ops = get_platform_ops()
            job = ops.create_job_object()
            if job is not None and ops.assign_to_job(job, process.pid):
                self._job = job
            elif job is not None:
                ops.close_job_object(job)
        threading.Thread(
            target=self._pump_replies, args=(process.stdout,), name="search-regex-replies", daemon=True
        ).start()
        self._send(self._header)

    def _pump_replies(self, stdout: IO[bytes] | None) -> None:
        """Queue each reply line; an empty item means the child's output ended."""
        try:
            if stdout is not None:
                for raw in iter(stdout.readline, b""):
                    self._replies.put(raw)
        except (OSError, ValueError):
            pass
        finally:
            self._replies.put(b"")
            if stdout is not None:
                with contextlib.suppress(OSError):
                    stdout.close()

    def _send(self, message: dict[str, Any]) -> None:
        stdin = self._process.stdin if self._process is not None else None
        if stdin is None:
            raise _RefusedError("regex_failed", _REGEX_FAILED_MESSAGE)
        try:
            stdin.write(json.dumps(message).encode("ascii") + b"\n")
            stdin.flush()
        except OSError as exc:  # the child is gone
            self.close()
            raise _RefusedError("regex_failed", _REGEX_FAILED_MESSAGE) from exc

    def search(
        self, lines: list[str], limit: int, stop: threading.Event | None, deadline: float
    ) -> tuple[list[tuple[int, int]], str | None]:
        """Index and column of the first *limit* matching *lines*, plus why matching stopped early (or ``None``)."""
        if self._process is None:
            self._start()
        self._send({"lines": lines, "limit": limit})
        while True:
            try:
                raw = self._replies.get(timeout=_REGEX_REPLY_POLL_SECONDS)
            except queue.Empty:
                reason = _scan_stop_reason(stop, deadline)
                if reason is not None:
                    self.close()  # the only way to stop a match that has started
                    return [], reason
                continue
            if not raw:
                self.close()
                raise _RefusedError("regex_failed", _REGEX_FAILED_MESSAGE)
            return [(int(index), int(column)) for index, column in json.loads(raw)["hits"]], None

    def close(self) -> None:
        """Kill the child (idle or mid-match) and release its Job Object."""
        process, self._process = self._process, None
        if process is not None:
            with contextlib.suppress(OSError):
                process.kill()
            with contextlib.suppress(Exception):
                process.wait(timeout=5)
            if process.stdin is not None:
                with contextlib.suppress(OSError):
                    process.stdin.close()
        if self._job is not None:
            from scistudio.engine.runners.platform import get_platform_ops

            get_platform_ops().close_job_object(self._job)
            self._job = None


_FileScan = tuple[list[tuple[int, str, int]], int, "str | None"]
"""``(hits as (line_no, text, column), lines read, why the scan stopped early or None)``."""


def _scan_here(
    lines: Iterator[tuple[int, str]],
    matcher: Callable[[str], int],
    limit: int,
    stop: threading.Event | None,
    deadline: float,
) -> _FileScan:
    """Match plain text line by line in this thread, checking the deadline and stop flag per line."""
    hits: list[tuple[int, str, int]] = []
    lines_read = 0
    for line_no, text in lines:
        # Checked per line, not only between directory entries: one slow file
        # (a stalled network share) must not outlive the budget.
        reason = _scan_stop_reason(stop, deadline)
        if reason is not None:
            return hits, lines_read, reason
        lines_read = line_no
        column = matcher(text)
        if column >= 0:
            hits.append((line_no, text, column))
            if len(hits) >= limit:
                break
    return hits, lines_read, None


def _scan_in_worker(
    lines: Iterator[tuple[int, str]],
    worker: _RegexWorker,
    limit: int,
    stop: threading.Event | None,
    deadline: float,
) -> _FileScan:
    """Read one file's lines here (deadline and stop flag checked per line), match them in *worker*."""
    texts: list[str] = []
    for _line_no, text in lines:
        reason = _scan_stop_reason(stop, deadline)
        if reason is not None:
            return [], len(texts), reason
        texts.append(text)
    if not texts:
        return [], 0, None
    found, reason = worker.search(texts, limit, stop, deadline)
    # _iter_lines numbers lines from 1 without gaps, so a line's index is its number minus one.
    return [(index + 1, texts[index], column) for index, column in found], len(texts), reason


def _snippet(text: str, column: int) -> str:
    start = max(0, column - 60)
    return text[start : start + _SEARCH_SNIPPET_CHARS].rstrip("\r\n").replace("\n", " ")


def _walk_regular_files(
    root_dir: Path,
    result: SearchFilesResult,
    stop: threading.Event | None,
    stopped_by: list[str],
    deadline: float,
) -> Iterator[Path]:
    """Regular files below *root_dir*, within the entry and time budgets; never follows links.

    Every directory entry visited counts toward ``result.entries_visited``,
    matching or not, so a huge root such as ``/`` stays bounded. A set *stop* event ends the walk at the next entry; the reason a
    walk stopped early is appended to *stopped_by*.
    """
    # Maintainer context:
    # Every directory entry visited counts toward ``result.entries_visited``,
    # matching or not, so a huge root such as ``/`` stays bounded (audit
    # AU4 P2-3). A set *stop* event ends the walk at the next entry; the reason a
    # walk stopped early is appended to *stopped_by*.
    # Development references: #2279.
    if root_dir.is_file():
        result.entries_visited = 1
        yield root_dir
        return
    pending = [root_dir]
    while pending:
        try:
            with os.scandir(pending.pop()) as iterator:
                entries = sorted(iterator, key=lambda entry: entry.name)
        except OSError:
            continue
        subdirectories: list[Path] = []
        for entry in entries:
            reason = _walk_stop_reason(result, stop, deadline)
            if reason is not None:
                stopped_by.append(reason)
                return
            result.entries_visited += 1
            path = Path(entry.path)
            try:
                if _is_link(path):
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if entry.name not in _SEARCH_SKIP_DIRS:
                        subdirectories.append(path)
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue  # FIFOs, sockets, devices: never opened
            except OSError:
                continue
            yield path
        pending.extend(reversed(subdirectories))


def _search_sync(
    root_dir: Path,
    project_root: Path | None,
    name_pattern: str,
    content: str | None,
    use_regex: bool,
    case_sensitive: bool,
    max_results: int,
    stop: threading.Event | None = None,
) -> SearchFilesResult:
    if not root_dir.exists():
        raise _RefusedError("not_found", "The search root does not exist.")
    matcher: Callable[[str], int]
    worker: _RegexWorker | None = None
    if content is not None and use_regex:
        try:
            pattern = re.compile(content, 0 if case_sensitive else re.IGNORECASE)
        except re.error as exc:
            raise _RefusedError(
                "invalid_regex", f"The content pattern is not a valid regular expression: {exc}"
            ) from exc
        # Started on the first file that has lines to match; see _RegexWorker for why.
        worker = _RegexWorker(pattern)

    elif content is not None:
        needle = content if case_sensitive else content.casefold()

        def matcher(line: str) -> int:
            return (line if case_sensitive else line.casefold()).find(needle)

    name_glob = name_pattern if case_sensitive else name_pattern.casefold()
    result = SearchFilesResult(root=_display_path(root_dir, project_root))
    skipped_binary = 0
    capped_files = 0

    stopped_by: list[str] = []
    # One budget for the walk and the content scan together.
    deadline = time.monotonic() + _SEARCH_TIME_BUDGET_SECONDS
    try:
        for path in _walk_regular_files(root_dir, result, stop, stopped_by, deadline):
            name = path.name if case_sensitive else path.name.casefold()
            if not fnmatch.fnmatchcase(name, name_glob):
                continue
            result.files_scanned += 1
            display = _display_path(path, project_root)
            if content is None:
                result.hits.append(SearchHit(path=display))
            else:
                try:
                    lines = _iter_lines(path)
                except OSError:
                    continue
                if lines is None:
                    skipped_binary += 1
                    continue
                limit = min(_SEARCH_HITS_PER_FILE, max_results - len(result.hits))
                if worker is not None:
                    found, lines_read, reason = _scan_in_worker(lines, worker, limit, stop, deadline)
                else:
                    found, lines_read, reason = _scan_here(lines, matcher, limit, stop, deadline)
                result.hits.extend(
                    SearchHit(path=display, line=line_no, snippet=_snippet(text, column))
                    for line_no, text, column in found
                )
                if reason is not None:
                    stopped_by.append(reason)
                    break
                if lines_read and path.stat().st_size > _SEARCH_FILE_BYTES_CAP:
                    capped_files += 1
            if len(result.hits) >= max_results:
                result.truncated = True
                result.notes.append(f"Stopped at {max_results} results.")
                break
    finally:
        if worker is not None:
            worker.close()
    if stopped_by:
        result.truncated = True
        result.notes.extend(stopped_by)
    if skipped_binary:
        result.notes.append(f"Skipped {skipped_binary} binary file(s).")
    if capped_files:
        result.notes.append(
            f"{capped_files} file(s) larger than {_SEARCH_FILE_BYTES_CAP} bytes were searched only in their first "
            f"{_SEARCH_FILE_BYTES_CAP} bytes."
        )
        result.truncated = True
    return result


@mcp.tool(name="search_files", tags=_READ_TAGS)
async def search_files(
    path: Annotated[str, Field(description="Directory (or file) to search: project-relative, or absolute.")] = ".",
    name_pattern: Annotated[str, Field(description="Glob matched against file names, e.g. '*.py'.")] = "*",
    content: Annotated[
        str | None,
        Field(description="Text to find inside files. Omit to search by file name only."),
    ] = None,
    regex: Annotated[bool, Field(description="Treat content as a regular expression.")] = False,
    case_sensitive: Annotated[bool, Field(description="Match case exactly.")] = False,
    max_results: Annotated[
        int, Field(description=f"Hits to return (1-{SEARCH_MAX_RESULTS}).")
    ] = SEARCH_DEFAULT_RESULTS,
) -> SearchFilesResult:
    """Find files by name, and optionally by content, below a directory.

    Bounded: stops at ``max_results`` hits, after visiting 20000 directory
    entries (matching or not), or after 20 s, and reads at most the first 2 MiB
    of each file; binary and special files are skipped, links are not followed,
    and ``.git``, ``node_modules``, and ``__pycache__`` are not descended.
    The deadline and the request's end are checked between the lines of a
    file as well as between entries, and a regular expression is matched in a
    separate process that is stopped when either fires, so a pattern that
    backtracks badly cannot outlive the budget. ``truncated`` and ``notes``
    say which bound applied. Ending the request stops the search.
    """
    stop = threading.Event()
    try:
        root_dir, project_root = _resolve_inspect_path(path)
        bounded = max(1, min(int(max_results), SEARCH_MAX_RESULTS))
        result = await asyncio.to_thread(
            _search_sync, root_dir, project_root, name_pattern or "*", content, regex, case_sensitive, bounded, stop
        )
    except asyncio.CancelledError:
        # The worker thread cannot be cancelled; tell it to stop at its next entry.
        stop.set()
        raise
    except _RefusedError as refused:
        result = SearchFilesResult(status=refused.status, refusal=refused.refusal, root=path)
    _log_outcome("search_files", result.status, result.refusal)
    return result


def _read_file_sync(
    target: Path, root: Path | None, offset: int, limit: int, encoding: str, files: ProjectFileWriter | None
) -> ReadFileResult:
    if not target.exists():
        raise _RefusedError("not_found", "The file does not exist.")
    if target.is_dir():
        raise _RefusedError("is_directory", "The path is a directory.", ["list_directory"])
    if not stat_module.S_ISREG(target.stat().st_mode):
        # A FIFO without a writer would block this thread forever; devices and
        # sockets are not files to read.
        raise _RefusedError("special_file", "The path is not a regular file (a FIFO, socket, or device).")
    # The version is taken BEFORE the content: an edit landing in between then
    # makes a write based on this version conflict, instead of overwriting
    # content the agent never saw (#2279 audit AU4 P3-4).
    state_version = (
        files.state_version(target) if files is not None and root is not None and _within(root, target) else None
    )
    data, total, more = _read_window(target, offset, limit)
    result = ReadFileResult(
        path=_display_path(target, root),
        absolute_path=str(target),
        encoding=encoding,
        offset=offset,
        limit_applied=limit,
        total_size_bytes=total,
        state_version=state_version,
    )
    if encoding == "base64":
        result.content = base64.b64encode(data).decode("ascii")
        result.bytes_returned = len(data)
        result.truncated = more
        result.next_offset = offset + len(data) if more else None
        return result
    decoded = _decode_window(data, at_start=offset == 0, more=more)
    if decoded is None:
        raise _RefusedError(
            "binary_content",
            "The file is not UTF-8 text (it looks binary). Read a bounded raw slice with encoding='base64', "
            "or use get_file_info for its metadata.",
            ["read_file", "get_file_info"],
        )
    text, skipped, consumed = decoded
    result.offset = offset + skipped
    result.content = text
    result.bytes_returned = consumed
    held_back = len(data) - skipped - consumed
    result.truncated = more or held_back > 0
    result.next_offset = result.offset + consumed if result.truncated else None
    return result


@mcp.tool(name="read_file", tags=_READ_TAGS)
async def read_file(
    path: Annotated[str, Field(description="File to read: project-relative, or absolute.")],
    offset: Annotated[int, Field(description="Byte offset to start at (use next_offset to continue).")] = 0,
    limit: Annotated[
        int,
        Field(description=f"Bytes to read; default {READ_DEFAULT_LIMIT_BYTES}, at most {READ_MAX_LIMIT_BYTES}."),
    ] = READ_DEFAULT_LIMIT_BYTES,
    encoding: Annotated[
        Literal["utf-8", "base64"],
        Field(description="'utf-8' for text; 'base64' for a raw bounded slice of a binary file."),
    ] = "utf-8",
) -> ReadFileResult:
    """Read a bounded byte range of a file as UTF-8 text (or base64).

    The read stops at ``limit`` bytes while streaming — the rest of the file
    is never loaded. ``truncated``, ``next_offset``, and ``total_size_bytes``
    say whether more remains; continue with ``offset=next_offset``. A binary
    file is refused with code ``binary_content``; use ``encoding='base64'``
    for its raw bytes. Relative paths resolve against the active project;
    absolute paths may be anywhere the backend user can read.
    """
    try:
        target, root = _resolve_inspect_path(path)
        bounded_limit = max(1, min(int(limit), READ_MAX_LIMIT_BYTES))
        start = max(0, int(offset))
        files = get_project_files(get_context())
        result = await asyncio.to_thread(_read_file_sync, target, root, start, bounded_limit, encoding, files)
    except _RefusedError as refused:
        result = ReadFileResult(status=refused.status, refusal=refused.refusal, path=path)
    except PermissionError:
        result = ReadFileResult(
            status="refused",
            refusal=ToolRefusal(code="permission_denied", message="The backend user cannot read this file."),
            path=path,
        )
    _log_outcome("read_file", result.status, result.refusal)
    return result


# ---------------------------------------------------------------------------
# Author tools.
# ---------------------------------------------------------------------------


def _affected(changes: list[dict[str, Any]]) -> tuple[list[str], bool]:
    rendered = [f"{change['kind']}:{change['entity_id']}" for change in changes]
    return rendered[:_AFFECTED_PATHS_CAP], len(rendered) > _AFFECTED_PATHS_CAP


def _author_result(outcome: dict[str, Any], rel: str, **extra: Any) -> AuthorResult:
    """Map the shared write path's dict to a tool result."""
    if outcome.get("status") == "conflict":
        return AuthorResult(
            status="conflict",
            refusal=ToolRefusal(
                code=str(outcome.get("condition")),
                message=str(outcome.get("message")),
                use_instead=["get_file_info", "read_file"],
            ),
            path=rel,
            expected_state_version=outcome.get("expected_state_version"),
            current_state_version=outcome.get("current_state_version"),
        )
    affected, truncated = _affected(outcome.get("changes", []))
    if not affected and outcome.get("entity_id") and outcome.get("kind"):
        affected = [f"{outcome['kind']}:{outcome['entity_id']}"]
    return AuthorResult(
        path=str(outcome.get("entity_id", rel)),
        kind=outcome.get("kind"),
        state_version=outcome.get("state_version"),
        size_bytes=outcome.get("size_bytes"),
        affected_paths=affected,
        affected_truncated=truncated,
        registry_refreshed=bool(outcome.get("registry_refreshed", False)),
        **extra,
    )


def _check_content_size(content: str) -> None:
    size = len(content.encode("utf-8"))
    if size > WRITE_CONTENT_CAP_BYTES:
        raise _RefusedError(
            "content_too_large",
            f"Content is {size} bytes, over the {WRITE_CONTENT_CAP_BYTES}-byte author-tool cap. "
            "Produce large files with run_command or a workflow instead.",
            ["run_command", "run_workflow"],
        )


def _refused_result(tool: str, refused: _RefusedError, path: str) -> AuthorResult:
    result = AuthorResult(status=refused.status, refusal=refused.refusal, path=path)
    _log_outcome(tool, result.status, result.refusal)
    return result


@mcp.tool(name="write_file", tags=_WRITE_TAGS)
async def write_file(
    path: Annotated[str, Field(description="Project-relative (or absolute, inside the project) file path.")],
    content: Annotated[str, Field(description="Full UTF-8 text content of the file.")],
    mode: Annotated[
        Literal["overwrite", "create"],
        Field(description="'create' refuses if the file exists; 'overwrite' creates or replaces."),
    ] = "overwrite",
    expected_state_version: Annotated[
        int | None,
        Field(description="State version from get_file_info/read_file; a changed file is reported as a conflict."),
    ] = None,
    create_parents: Annotated[bool, Field(description="Create missing parent directories.")] = False,
) -> AuthorResult:
    """Create or replace a text file in the active project, with UI sync.

    The write goes through the editor's shared path: atomic replace, a
    ``file.changed`` event so the open UI updates, and a registry reload after
    a lint-clean save under ``blocks/`` or ``types/``. Refused: anything under
    ``data/`` (use run_workflow), ``workflows/*.yaml`` (use write_workflow /
    update_block_config), and a ``blocks/*.py`` write before list_blocks has
    been called. A block write returns non-blocking warnings for generic port
    types.
    """
    try:
        files = _require_project_files()
        target, _root, rel = _resolve_author_path(path)
        _require_block_list(rel)
        _check_content_size(content)
        outcome = await files.write_text(
            target,
            content,
            expected_state_version=expected_state_version,
            create_only=mode == "create",
            create_parents=create_parents,
            changed_by="mcp.write_file",
        )
    except _RefusedError as refused:
        return _refused_result("write_file", refused, path)
    warnings = port_type_warnings(rel, content) if outcome.get("status") == "ok" else []
    result = _author_result(outcome, rel, warnings=warnings)
    _log_outcome("write_file", result.status, result.refusal)
    return result


@mcp.tool(name="create_directory", tags=_WRITE_TAGS)
async def create_directory(
    path: Annotated[str, Field(description="Project-relative directory to create.")],
    parents: Annotated[bool, Field(description="Create missing parent directories too.")] = False,
) -> AuthorResult:
    """Create a directory in the active project (never under ``data/``)."""
    try:
        files = _require_project_files()
        target, _root, rel = _resolve_author_path(path)
        outcome = await files.make_directory(target, parents=parents, changed_by="mcp.create_directory")
    except _RefusedError as refused:
        return _refused_result("create_directory", refused, path)
    result = _author_result(outcome, rel)
    result.next_step = "Create files inside it with write_file."
    _log_outcome("create_directory", result.status, result.refusal)
    return result


def _read_for_patch(target: Path) -> str:
    size = target.stat().st_size
    if size > WRITE_CONTENT_CAP_BYTES:
        raise _RefusedError(
            "content_too_large",
            f"The file is {size} bytes, over the {WRITE_CONTENT_CAP_BYTES}-byte author-tool cap.",
            ["run_command"],
        )
    raw = target.read_bytes()
    try:
        # Decoded without newline translation so CRLF files keep their endings.
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _RefusedError("binary_content", "The file is not UTF-8 text and cannot be patched.") from exc


@mcp.tool(name="patch_file", tags=_WRITE_TAGS)
async def patch_file(
    path: Annotated[str, Field(description="Project-relative file to edit.")],
    old_text: Annotated[str, Field(description="Exact text to replace; must occur once unless replace_all.")],
    new_text: Annotated[str, Field(description="Replacement text.")],
    expected_state_version: Annotated[
        int | None,
        Field(description="State version the edit is based on; a changed file is reported as a conflict."),
    ] = None,
    replace_all: Annotated[bool, Field(description="Replace every occurrence of old_text.")] = False,
) -> AuthorResult:
    """Replace exact text in an existing project file, with UI sync.

    Same rules and write path as write_file. ``old_text`` must match exactly
    once (or pass ``replace_all``); a missing or ambiguous match is refused
    without writing. The edit is applied to the file as it is on disk, and
    written only if it has not changed in between.
    """
    try:
        files = _require_project_files()
        target, _root, rel = _resolve_author_path(path)
        _require_block_list(rel)
        if not target.is_file():
            raise _RefusedError("missing_file", "The file does not exist; create it with write_file.", ["write_file"])
        if not old_text:
            raise _RefusedError("invalid_patch", "old_text must not be empty.")
        base_version = expected_state_version if expected_state_version is not None else files.state_version(target)
        text = await asyncio.to_thread(_read_for_patch, target)
        occurrences = text.count(old_text)
        if occurrences == 0:
            raise _RefusedError("patch_target_not_found", "old_text does not occur in the file.", ["read_file"])
        if occurrences > 1 and not replace_all:
            raise _RefusedError(
                "patch_target_ambiguous",
                f"old_text occurs {occurrences} times; add surrounding context or pass replace_all=true.",
                ["read_file"],
            )
        updated = text.replace(old_text, new_text) if replace_all else text.replace(old_text, new_text, 1)
        _check_content_size(updated)
        outcome = await files.write_text(
            target,
            updated,
            expected_state_version=base_version,
            require_existing=True,
            changed_by="mcp.patch_file",
        )
    except _RefusedError as refused:
        return _refused_result("patch_file", refused, path)
    warnings = port_type_warnings(rel, updated) if outcome.get("status") == "ok" else []
    result = _author_result(outcome, rel, warnings=warnings, replacements=occurrences if replace_all else 1)
    _log_outcome("patch_file", result.status, result.refusal)
    return result


@mcp.tool(name="move_path", tags=_WRITE_TAGS)
async def move_path(
    path: Annotated[str, Field(description="Project-relative file or directory to rename or move.")],
    destination: Annotated[str, Field(description="Full new project-relative path (never overwritten).")],
    create_parents: Annotated[bool, Field(description="Create the destination's missing parent directories.")] = False,
    expected_state_version: Annotated[
        int | None,
        Field(description="For a file: the state version the move is based on."),
    ] = None,
) -> AuthorResult:
    """Rename or move a file or directory inside the active project, with UI sync.

    Never overwrites an existing destination. A symlink or junction is moved
    as a link, never what it points to. Each moved file emits a
    ``deleted`` event at its old path and ``created`` at its new one. Refused
    when the source or destination touches ``data/`` or ``workflows/*.yaml``
    (for a directory: any file inside it), or when a ``blocks/*.py`` would be
    created before list_blocks has been called.
    """
    try:
        files = _require_project_files()
        source, root, source_rel = _resolve_author_path(path, follow_final=False)
        target, _root, target_rel = _resolve_author_path(destination, follow_final=False)
        if root in (source, target):
            raise _RefusedError("project_root", "The project root itself cannot be moved.")
        if source.is_dir() and not _is_link(source):
            await asyncio.to_thread(_check_tree, root, source, target)
        else:
            _require_block_list(target_rel)
        outcome = await files.move(
            source,
            target,
            create_parents=create_parents,
            expected_state_version=expected_state_version,
            changed_by="mcp.move_path",
        )
    except _RefusedError as refused:
        return _refused_result("move_path", refused, path)
    warnings: list[str] = []
    if outcome.get("status") == "ok" and not _is_link(target) and target.is_file():
        try:
            warnings = port_type_warnings(target_rel, await asyncio.to_thread(_read_for_patch, target))
        except _RefusedError:
            warnings = []
    result = _author_result(outcome, source_rel, warnings=warnings)
    if result.status == "ok":
        result.kind = "moved"
    _log_outcome("move_path", result.status, result.refusal)
    return result


@mcp.tool(name="delete_path", tags=_WRITE_TAGS)
async def delete_path(
    path: Annotated[str, Field(description="Project-relative file or directory to delete.")],
    recursive: Annotated[bool, Field(description="Required to delete a non-empty directory.")] = False,
    expected_state_version: Annotated[
        int | None,
        Field(description="For a file: the state version the delete is based on."),
    ] = None,
) -> AuthorResult:
    """Delete a file or directory in the active project, with UI sync.

    A symlink or junction is removed as a link; what it points to is never
    touched. A ``deleted`` event is emitted for every removed file so an open
    editor tab learns its file is gone. Refused for anything under ``data/`` and for
    ``workflows/*.yaml`` (for a directory: any such file inside it). A
    non-empty directory needs ``recursive=true``.
    """
    try:
        files = _require_project_files()
        target, root, rel = _resolve_author_path(path, follow_final=False)
        if target == root:
            raise _RefusedError("project_root", "The project root itself cannot be deleted.")
        if target.is_dir() and not _is_link(target):
            await asyncio.to_thread(_check_tree, root, target)
        outcome = await files.delete(
            target,
            recursive=recursive,
            expected_state_version=expected_state_version,
            changed_by="mcp.delete_path",
        )
    except _RefusedError as refused:
        return _refused_result("delete_path", refused, path)
    result = _author_result(outcome, rel)
    if result.status == "ok":
        result.kind = "deleted"
        result.next_step = "Confirm with list_directory; the UI received a file-deleted event for each removed file."
    _log_outcome("delete_path", result.status, result.refusal)
    return result


# Refusals and conflicts of these tools are failures. scaffold_block refuses only
# through the WebMCP bridge; get_agent_context refuses when no project is open.
for _tool_name in (
    "list_directory",
    "get_file_info",
    "search_files",
    "read_file",
    "write_file",
    "create_directory",
    "patch_file",
    "move_path",
    "delete_path",
    "get_agent_context",
    "scaffold_block",
):
    register_failure_outcome(_tool_name)


__all__ = [
    "READ_DEFAULT_LIMIT_BYTES",
    "READ_MAX_LIMIT_BYTES",
    "WRITE_CONTENT_CAP_BYTES",
    "AuthorResult",
    "FileInfoResult",
    "ListDirectoryResult",
    "ReadFileResult",
    "SearchFilesResult",
    "ToolRefusal",
    "create_directory",
    "delete_path",
    "get_file_info",
    "list_blocks_refusal",
    "list_directory",
    "move_path",
    "patch_file",
    "port_type_warnings",
    "read_file",
    "search_files",
    "write_file",
]
