"""Typed storage-reference errors for missing or unreadable backend data."""

from __future__ import annotations

from typing import Any

from scistudio.core.storage.ref import StorageReference


class StorageReferenceInvalidError(RuntimeError):
    """A storage reference could not be resolved by its backend.

    Raised when the data a :class:`StorageReference` points at cannot be read —
    for example the file is corrupt, unreadable, or in an unexpected format.
    Use :meth:`to_payload` to turn it into a structured, JSON-compatible error
    for the API/UI layer. :class:`StorageMissingError` is the more specific
    subclass for the "data is simply not there" case.
    """

    error_kind = "storage_reference_invalid"
    """Short machine-readable tag identifying this error category in payloads."""

    def __init__(
        self,
        ref: StorageReference,
        *,
        reason: str,
        operation: str,
        detail: str | None = None,
    ) -> None:
        """Build the error.

        Args:
            ref: The storage reference that failed to resolve.
            reason: Short machine-readable reason (e.g. ``"corrupt_or_unreadable"``).
            operation: The backend operation underway when it failed (e.g.
                ``"read"``, ``"slice"``).
            detail: Optional human-readable detail, often the underlying
                exception text.
        """
        self.ref = ref
        """The storage reference that failed to resolve."""
        self.reason = reason
        """Short machine-readable reason the reference is invalid."""
        self.operation = operation
        """Name of the backend operation underway when the failure occurred."""
        self.detail = detail
        """Optional human-readable detail (often the underlying error text), or ``None``."""
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
        """Return a JSON-compatible structured description of this error.

        Args:
            block_id: Optional id of the block whose port referenced the data.
            port_name: Optional name of the input/output port involved.
            upstream_block: Optional id of the block that produced the data.

        Returns:
            A dict with ``error_kind``, a human-readable ``message``, the
            ``reason`` / ``operation``, the ``ref`` fields, and whichever
            optional context fields were supplied. Safe to serialise to JSON.
        """
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
    """The data a storage reference points at is missing.

    A specialisation of :class:`StorageReferenceInvalidError` for the case where
    the file or object simply does not exist (e.g. it was deleted or never
    written). The ``reason`` is fixed to ``"missing"``.
    """

    error_kind = "storage_missing"
    """Short machine-readable tag identifying this error category in payloads."""

    def __init__(
        self,
        ref: StorageReference,
        *,
        operation: str,
        detail: str | None = None,
    ) -> None:
        """Build the error.

        Args:
            ref: The storage reference whose data is missing.
            operation: The backend operation underway when the data was found
                missing (e.g. ``"read"``, ``"slice"``).
            detail: Optional human-readable detail, often the underlying
                exception text.
        """
        super().__init__(
            ref,
            reason="missing",
            operation=operation,
            detail=detail,
        )
