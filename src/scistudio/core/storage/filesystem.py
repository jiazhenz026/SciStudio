"""Plain filesystem storage backend for Text and Artifact types."""

from __future__ import annotations

import contextlib
import os
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from scistudio.core.storage.errors import StorageMissingError, StorageReferenceInvalidError
from scistudio.core.storage.ref import StorageReference


def _wrap_filesystem_read_error(
    ref: StorageReference,
    operation: str,
    exc: Exception,
) -> StorageReferenceInvalidError:
    if isinstance(exc, FileNotFoundError):
        return StorageMissingError(ref, operation=operation, detail=str(exc))
    return StorageReferenceInvalidError(
        ref,
        reason="corrupt_or_unreadable",
        operation=operation,
        detail=str(exc),
    )


class FilesystemBackend:
    """Filesystem-based storage backend for text files and opaque artifacts."""

    def read(self, ref: StorageReference) -> Any:
        """Read a file from the filesystem at *ref*.

        For text formats (format starts with "text" or is "plain"/"markdown"/"json"),
        reads as UTF-8 string. Otherwise reads as bytes.
        """
        path = Path(ref.path)
        text_formats = {"plain", "markdown", "json", "text", "csv"}
        fmt = (ref.format or "").lower()
        try:
            if fmt in text_formats or fmt.startswith("text"):
                return path.read_text(encoding="utf-8")
            return path.read_bytes()
        except (FileNotFoundError, UnicodeDecodeError) as exc:
            raise _wrap_filesystem_read_error(ref, "read", exc) from exc

    def write(self, data: Any, ref: StorageReference) -> StorageReference:
        """Write *data* (str or bytes) to the filesystem at *ref* atomically.

        Uses write-to-temp-then-rename to prevent partial writes on crash or
        cancellation.  ``os.replace()`` is atomic on both POSIX and Windows
        (Python 3.3+).
        """
        path = Path(ref.path)
        path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(data, str):
            content_bytes = data.encode("utf-8")
        elif isinstance(data, bytes):
            content_bytes = data
        else:
            raise TypeError(f"FilesystemBackend.write expects str or bytes, got {type(data).__name__}")

        fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".tmp_")
        try:
            os.write(fd, content_bytes)
            os.close(fd)
            fd = -1  # Mark as closed
            os.replace(tmp_path, str(path))
        except BaseException:
            if fd >= 0:
                os.close(fd)
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise

        metadata = dict(ref.metadata) if ref.metadata else {}
        metadata["size"] = path.stat().st_size
        return StorageReference(
            backend="filesystem",
            path=ref.path,
            format=ref.format,
            metadata=metadata,
        )

    def write_from_memory(self, data: Any, path: str) -> StorageReference:
        """Write raw in-memory str/bytes data to the filesystem at *path*."""
        ref = StorageReference(backend="filesystem", path=path)
        return self.write(data, ref)

    def slice(self, ref: StorageReference, *args: Any) -> Any:
        """Return a byte-range slice from *ref*.

        Expects two positional args: (offset, length).
        """
        if len(args) != 2:
            raise ValueError("FilesystemBackend.slice expects (offset, length).")
        offset, length = int(args[0]), int(args[1])
        path = Path(ref.path)
        try:
            with path.open("rb") as f:
                f.seek(offset)
                return f.read(length)
        except FileNotFoundError as exc:
            raise StorageMissingError(ref, operation="slice", detail=str(exc)) from exc

    def iter_chunks(self, ref: StorageReference, chunk_size: int) -> Iterator[Any]:
        """Yield fixed-size byte chunks from *ref*."""
        path = Path(ref.path)
        try:
            with path.open("rb") as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
        except FileNotFoundError as exc:
            raise StorageMissingError(ref, operation="iter_chunks", detail=str(exc)) from exc

    def get_metadata(self, ref: StorageReference) -> dict[str, Any]:
        """Return filesystem metadata (size, mtime, etc.) for *ref*."""
        path = Path(ref.path)
        try:
            stat = path.stat()
        except FileNotFoundError as exc:
            raise StorageMissingError(ref, operation="get_metadata", detail=str(exc)) from exc
        return {
            "size": stat.st_size,
            "mtime": os.path.getmtime(ref.path),
            "name": path.name,
            "suffix": path.suffix,
        }
