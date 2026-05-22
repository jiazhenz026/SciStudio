"""Typed storage-reference errors for missing or unreadable backend data."""

from __future__ import annotations

from typing import Any

from scistudio.core.storage.ref import StorageReference


class StorageReferenceInvalidError(RuntimeError):
    """Raised when a storage reference cannot be resolved by its backend."""

    error_kind = "storage_reference_invalid"

    def __init__(
        self,
        ref: StorageReference,
        *,
        reason: str,
        operation: str,
        detail: str | None = None,
    ) -> None:
        self.ref = ref
        self.reason = reason
        self.operation = operation
        self.detail = detail
        message = f"Storage reference is invalid during {operation}: {ref.backend}:{ref.path} ({reason})"
        if detail:
            message = f"{message}: {detail}"
        super().__init__(message)

    def to_payload(
        self,
        *,
        block_id: str | None = None,
        port_name: str | None = None,
        upstream_block: str | None = None,
    ) -> dict[str, Any]:
        """Return a JSON-compatible structured error payload."""
        payload: dict[str, Any] = {
            "error_kind": self.error_kind,
            "message": self._contextual_message(block_id=block_id, port_name=port_name),
            "reason": self.reason,
            "operation": self.operation,
            "ref": {
                "backend": self.ref.backend,
                "path": self.ref.path,
                "format": self.ref.format,
                "metadata": self.ref.metadata,
            },
        }
        if block_id is not None:
            payload["block_id"] = block_id
        if port_name is not None:
            payload["port_name"] = port_name
        if upstream_block is not None:
            payload["upstream_block"] = upstream_block
        if self.detail is not None:
            payload["detail"] = self.detail
        return payload

    def _contextual_message(self, *, block_id: str | None, port_name: str | None) -> str:
        target = f"{self.ref.backend}:{self.ref.path}"
        if block_id and port_name:
            return f"Input '{port_name}' of block '{block_id}' references unavailable storage data: {target}."
        if port_name:
            return f"Input '{port_name}' references unavailable storage data: {target}."
        if block_id:
            return f"Block '{block_id}' references unavailable storage data: {target}."
        return f"Storage reference points to unavailable data: {target}."


class StorageMissingError(StorageReferenceInvalidError):
    """Raised when referenced backend data is missing."""

    error_kind = "storage_missing"

    def __init__(
        self,
        ref: StorageReference,
        *,
        operation: str,
        detail: str | None = None,
    ) -> None:
        super().__init__(
            ref,
            reason="missing",
            operation=operation,
            detail=detail,
        )
