"""Directory-of-slots storage for CompositeData types."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from scistudio.core.storage.errors import StorageMissingError, StorageReferenceInvalidError
from scistudio.core.storage.ref import StorageReference


class CompositeStore:
    """Storage backend for :class:`CompositeData`, persisting each slot independently.

    Each slot is stored in a sub-directory, and a manifest.json records the
    mapping of slot names to their backend types and paths.
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
        """Read a composite directory structure from *ref*.

        Returns a dict of ``{slot_name: data}`` by reading each slot
        according to the manifest.
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

    def write(self, data: Any, ref: StorageReference) -> StorageReference:
        """Write composite slots to a directory at *ref*.

        *data* must be a dict of ``{slot_name: (backend_name, slot_data)}``.
        Each slot is stored in a subdirectory using the appropriate backend.

        .. warning::
            Multi-slot writes are **not atomic**.  Slots are written
            sequentially; a crash or cancellation mid-way may leave some
            slots persisted and others missing.  The manifest is written
            last, so a missing manifest indicates an incomplete write.
            The checkpoint-resume strategy re-runs the producing block,
            which overwrites incomplete output (ADR-018).

        .. todo::
            Implement atomic composite write via write-to-temp-directory
            then rename (requires directory-level atomicity across all
            slot backends).
        """
        if not isinstance(data, dict):
            raise TypeError("CompositeStore.write expects a dict of {slot_name: (backend, data)}.")

        base = Path(ref.path)
        base.mkdir(parents=True, exist_ok=True)

        manifest_slots: dict[str, Any] = {}
        for slot_name, (backend_name, slot_data) in data.items():
            backend = self._get_backend_for(backend_name)
            if backend_name == "zarr":
                slot_path = str(base / slot_name / "data.zarr")
                slot_format = None
            elif backend_name == "arrow":
                slot_path = str(base / slot_name / "data.parquet")
                slot_format = "parquet"
            elif isinstance(slot_data, str):
                slot_path = str(base / slot_name / "data.txt")
                slot_format = "plain"
            else:
                slot_path = str(base / slot_name / "data.bin")
                slot_format = "binary"
            Path(slot_path).parent.mkdir(parents=True, exist_ok=True)

            slot_ref = StorageReference(backend=backend_name, path=slot_path, format=slot_format)
            result_ref = backend.write(slot_data, slot_ref)
            manifest_slots[slot_name] = {
                "backend": backend_name,
                "path": result_ref.path,
                "format": result_ref.format,
            }

        manifest = {"slots": manifest_slots}
        manifest_path = base / self._MANIFEST_NAME
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        metadata = dict(ref.metadata) if ref.metadata else {}
        metadata["slot_names"] = list(manifest_slots.keys())
        return StorageReference(
            backend="composite",
            path=ref.path,
            format="composite",
            metadata=metadata,
        )

    def write_from_memory(self, data: Any, path: str) -> StorageReference:
        """Write raw in-memory composite data to a directory at *path*."""
        ref = StorageReference(backend="composite", path=path)
        return self.write(data, ref)

    def slice(self, ref: StorageReference, *args: Any) -> Any:
        """Return a subset of slots from the composite at *ref*.

        *args* should be slot names to select.
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
        """Yield slots one at a time from the composite at *ref*."""
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
        """Return metadata for the composite directory at *ref*."""
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
