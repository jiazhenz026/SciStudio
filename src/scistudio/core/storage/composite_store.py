"""Directory-of-slots storage for CompositeData types."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from scistudio.core.storage.errors import StorageMissingError, StorageReferenceInvalidError
from scistudio.core.storage.ref import StorageReference
from scistudio.utils.atomic_io import atomic_replace_dir


class CompositeStore:
    """Storage backend for :class:`CompositeData`, persisting each slot on its own.

    A composite object groups several named "slots" (each a separate piece of
    data, possibly of different kinds). This backend stores each slot in its own
    sub-directory using the slot's own backend, and writes a ``manifest.json``
    recording the slot name to backend/path mapping. The router selects this
    backend for composite types, so you rarely construct it directly.

    Example:
        >>> import os, tempfile
        >>> store = CompositeStore()
        >>> path = os.path.join(tempfile.mkdtemp(), "obj")
        >>> ref = store.write({"notes": ("filesystem", "hello")}, StorageReference(backend="composite", path=path))
        >>> store.read(ref)["notes"]
        'hello'
    """

    _MANIFEST_NAME = "manifest.json"

    def _get_backend_for(self, backend_name: str) -> Any:
        """Return the appropriate backend instance for *backend_name*."""
        from scistudio.core.storage.arrow_backend import ArrowBackend
        from scistudio.core.storage.filesystem import FilesystemBackend
        from scistudio.core.storage.zarr_backend import ZarrBackend

        backends: dict[str, Any] = {
            "zarr": ZarrBackend(),
            "arrow": ArrowBackend(),
            "filesystem": FilesystemBackend(),
        }
        if backend_name not in backends:
            raise ValueError(f"Unknown backend: {backend_name}")
        return backends[backend_name]

    def read(self, ref: StorageReference) -> Any:
        """Read every slot of the composite directory at *ref*.

        Args:
            ref: Pointer to the composite directory.

        Returns:
            A dict mapping each ``slot_name`` to that slot's data, read with the
            slot's own backend.

        Raises:
            StorageMissingError: When the manifest is absent.
            StorageReferenceInvalidError: When the manifest is corrupt.
        """
        base = Path(ref.path)
        manifest_path = base / self._MANIFEST_NAME
        try:
            manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise StorageMissingError(ref, operation="read", detail=str(exc)) from exc
        except json.JSONDecodeError as exc:
            raise StorageReferenceInvalidError(
                ref,
                reason="corrupt_or_unreadable",
                operation="read",
                detail=str(exc),
            ) from exc

        result: dict[str, Any] = {}
        for slot_name, slot_info in manifest["slots"].items():
            backend = self._get_backend_for(slot_info["backend"])
            slot_ref = StorageReference(
                backend=slot_info["backend"],
                path=slot_info["path"],
                format=slot_info.get("format"),
            )
            result[slot_name] = backend.read(slot_ref)
        return result

    def slot_ref(self, ref: StorageReference, slot_name: str) -> StorageReference | None:
        """Resolve the :class:`StorageReference` for a single composite slot.

        A read-only manifest lookup that returns one slot's recorded
        ``backend`` / ``path`` / ``format`` — the same per-slot reference that
        :meth:`read` and :meth:`slice` reconstruct. This is the authoritative
        slot resolver, exposed so a bounded reader (e.g. a previewer) can read a
        single slot without reconstructing the on-disk layout itself.

        Args:
            ref: Pointer to the composite directory.
            slot_name: Name of the slot to resolve.

        Returns:
            The slot's :class:`StorageReference`, or ``None`` when the composite
            has no manifest or no such slot (the caller degrades gracefully).

        Raises:
            StorageReferenceInvalidError: When the manifest exists but is corrupt.
        """
        base = Path(ref.path)
        manifest_path = base / self._MANIFEST_NAME
        try:
            manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except json.JSONDecodeError as exc:
            raise StorageReferenceInvalidError(
                ref,
                reason="corrupt_or_unreadable",
                operation="slot_ref",
                detail=str(exc),
            ) from exc
        slots = manifest.get("slots")
        if not isinstance(slots, dict):
            return None
        slot_info = slots.get(slot_name)
        if not isinstance(slot_info, dict) or not isinstance(slot_info.get("path"), str):
            return None
        return StorageReference(
            backend=str(slot_info.get("backend", "filesystem")),
            path=slot_info["path"],
            format=slot_info.get("format"),
        )

    def write(self, data: Any, ref: StorageReference) -> StorageReference:
        """Write composite slots to a directory at *ref* atomically.

        All slots and the manifest are built in a staging sibling directory that
        is swapped into place at the end, so a crash or cancellation mid-write
        leaves the previous composite (or nothing) on disk rather than a
        half-written directory.

        Args:
            data: A dict mapping ``slot_name`` to ``(backend_name, slot_data)``.
                Each slot is written under its own sub-directory using the named
                backend.
            ref: Pointer describing where to write the composite directory.

        Returns:
            An updated :class:`StorageReference` whose metadata lists the slot
            names that were written.

        Raises:
            TypeError: When *data* is not a dict.
        """
        if not isinstance(data, dict):
            raise TypeError("CompositeStore.write expects a dict of {slot_name: (backend, data)}.")

        base = Path(ref.path)
        manifest_slots: dict[str, Any] = {}
        with atomic_replace_dir(base) as staging:
            for slot_name, (backend_name, slot_data) in data.items():
                backend = self._get_backend_for(backend_name)
                if backend_name == "zarr":
                    rel = Path(slot_name) / "data.zarr"
                    slot_format: str | None = None
                elif backend_name == "arrow":
                    rel = Path(slot_name) / "data.parquet"
                    slot_format = "parquet"
                elif isinstance(slot_data, str):
                    rel = Path(slot_name) / "data.txt"
                    slot_format = "plain"
                else:
                    rel = Path(slot_name) / "data.bin"
                    slot_format = "binary"
                staging_slot = staging / rel
                staging_slot.parent.mkdir(parents=True, exist_ok=True)

                # Write into the staging tree; the slot lands at ``base / rel``
                # after the atomic swap, so that is what the manifest records.
                slot_ref = StorageReference(backend=backend_name, path=str(staging_slot), format=slot_format)
                result_ref = backend.write(slot_data, slot_ref)
                manifest_slots[slot_name] = {
                    "backend": backend_name,
                    "path": str(base / rel),
                    "format": result_ref.format,
                }

            manifest = {"slots": manifest_slots}
            (staging / self._MANIFEST_NAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        metadata = dict(ref.metadata) if ref.metadata else {}
        metadata["slot_names"] = list(manifest_slots.keys())
        return StorageReference(
            backend="composite",
            path=ref.path,
            format="composite",
            metadata=metadata,
        )

    def write_from_memory(self, data: Any, path: str) -> StorageReference:
        """Write in-memory composite slot data to a new directory at *path*.

        Args:
            data: A dict mapping ``slot_name`` to ``(backend_name, slot_data)``.
            path: Target filesystem path for the composite directory.

        Returns:
            A :class:`StorageReference` pointing at the new directory.
        """
        ref = StorageReference(backend="composite", path=path)
        return self.write(data, ref)

    def slice(self, ref: StorageReference, *args: Any) -> Any:
        """Read a subset of slots from the composite at *ref*.

        Args:
            ref: Pointer to the composite directory.
            *args: Slot names to select. Empty selects all slots.

        Returns:
            A dict mapping each selected ``slot_name`` to its data. Unknown slot
            names are skipped.

        Raises:
            StorageMissingError: When the manifest is absent.
            StorageReferenceInvalidError: When the manifest is corrupt.
        """
        base = Path(ref.path)
        manifest_path = base / self._MANIFEST_NAME
        try:
            manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise StorageMissingError(ref, operation="slice", detail=str(exc)) from exc
        except json.JSONDecodeError as exc:
            raise StorageReferenceInvalidError(
                ref,
                reason="corrupt_or_unreadable",
                operation="slice",
                detail=str(exc),
            ) from exc

        requested = set(args) if args else set(manifest["slots"].keys())
        result: dict[str, Any] = {}
        for slot_name in requested:
            slot_info = manifest["slots"].get(slot_name)
            if slot_info is None:
                continue
            backend = self._get_backend_for(slot_info["backend"])
            slot_ref = StorageReference(
                backend=slot_info["backend"],
                path=slot_info["path"],
                format=slot_info.get("format"),
            )
            result[slot_name] = backend.read(slot_ref)
        return result

    def iter_chunks(self, ref: StorageReference, chunk_size: int) -> Iterator[Any]:
        """Yield the composite's slots one at a time.

        Args:
            ref: Pointer to the composite directory.
            chunk_size: Accepted for protocol compatibility; ignored, since one
                slot is yielded at a time.

        Yields:
            A ``(slot_name, data)`` pair for each slot in the manifest.

        Raises:
            StorageMissingError: When the manifest is absent.
            StorageReferenceInvalidError: When the manifest is corrupt.
        """
        base = Path(ref.path)
        manifest_path = base / self._MANIFEST_NAME
        try:
            manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise StorageMissingError(ref, operation="iter_chunks", detail=str(exc)) from exc
        except json.JSONDecodeError as exc:
            raise StorageReferenceInvalidError(
                ref,
                reason="corrupt_or_unreadable",
                operation="iter_chunks",
                detail=str(exc),
            ) from exc

        for slot_name, slot_info in manifest["slots"].items():
            backend = self._get_backend_for(slot_info["backend"])
            slot_ref = StorageReference(
                backend=slot_info["backend"],
                path=slot_info["path"],
                format=slot_info.get("format"),
            )
            yield slot_name, backend.read(slot_ref)

    def get_metadata(self, ref: StorageReference) -> dict[str, Any]:
        """Return metadata for the composite directory at *ref*.

        Args:
            ref: Pointer to the composite directory.

        Returns:
            A dict with ``slot_names`` (the list of slots) and ``slot_backends``
            (mapping each slot name to its backend name).

        Raises:
            StorageMissingError: When the manifest is absent.
            StorageReferenceInvalidError: When the manifest is corrupt.
        """
        base = Path(ref.path)
        manifest_path = base / self._MANIFEST_NAME
        try:
            manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise StorageMissingError(ref, operation="get_metadata", detail=str(exc)) from exc
        except json.JSONDecodeError as exc:
            raise StorageReferenceInvalidError(
                ref,
                reason="corrupt_or_unreadable",
                operation="get_metadata",
                detail=str(exc),
            ) from exc
        return {
            "slot_names": list(manifest["slots"].keys()),
            "slot_backends": {k: v["backend"] for k, v in manifest["slots"].items()},
        }
