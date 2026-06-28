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
    """Storage backend for plain files: text and opaque binary artifacts.

    Reads and writes single files on disk. The router selects this backend for
    text and artifact types, so you rarely construct it directly. Writes are
    atomic (write to a temp file, then rename) so a crash or cancellation cannot
    leave a half-written file.

    Example:
        >>> import os, tempfile
        >>> backend = FilesystemBackend()
        >>> path = os.path.join(tempfile.mkdtemp(), "note.txt")
        >>> ref = backend.write("hello", StorageReference(backend="filesystem", path=path, format="text"))
        >>> backend.read(ref)
        'hello'
    """

    def read(self, ref: StorageReference) -> Any:
        """Read the file at *ref* as text or bytes.

        Text formats (``ref.format`` is one of ``plain``/``markdown``/``json``/
        ``text``/``csv`` or starts with ``text``) are decoded as UTF-8;
        anything else is returned as raw bytes.

        Args:
            ref: Pointer to the stored file.

        Returns:
            The file contents as a ``str`` (text formats) or ``bytes``.

        Raises:
            StorageMissingError: When the file does not exist.
            StorageReferenceInvalidError: When the bytes cannot be decoded as
                the declared text format.
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
        """Write *data* to the file at *ref* atomically.

        Writes to a temporary file in the same directory and renames it into
        place (``os.replace`` is atomic on POSIX and Windows), so a partial
        write is never observed.

        Args:
            data: A ``str`` (encoded as UTF-8) or ``bytes`` to write.
            ref: Pointer describing where to write the file.

        Returns:
            An updated :class:`StorageReference` whose metadata records the
            written file size.

        Raises:
            TypeError: When *data* is neither ``str`` nor ``bytes``.
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
        """Write in-memory text/bytes data to a new file at *path*.

        Args:
            data: A ``str`` or ``bytes`` to write.
            path: Target filesystem path.

        Returns:
            A :class:`StorageReference` pointing at the new file.
        """
        ref = StorageReference(backend="filesystem", path=path)
        return self.write(data, ref)

    def slice(self, ref: StorageReference, *args: Any) -> Any:
        """Read a byte range from the file at *ref*.

        Args:
            ref: Pointer to the stored file.
            *args: Exactly two values, ``(offset, length)`` in bytes.

        Returns:
            The requested ``bytes`` slice.

        Raises:
            ValueError: When *args* is not exactly ``(offset, length)``.
            StorageMissingError: When the file does not exist.
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
        """Yield the file at *ref* as fixed-size byte chunks.

        Args:
            ref: Pointer to the stored file.
            chunk_size: Number of bytes per yielded chunk.

        Yields:
            A ``bytes`` chunk for each read, until end of file.

        Raises:
            StorageMissingError: When the file does not exist.
        """
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
        """Return filesystem metadata for *ref*.

        Args:
            ref: Pointer to the stored file.

        Returns:
            A dict with ``size`` (bytes), ``mtime`` (modification time),
            ``name``, and ``suffix``.

        Raises:
            StorageMissingError: When the file does not exist.
        """
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
