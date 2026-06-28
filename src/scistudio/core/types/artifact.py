"""Opaque file artifacts (:class:`Artifact`).

The data type for a finished file that SciStudio passes along without
looking inside it — a PDF, a rendered report, an image file, or any binary
blob. Use it when the meaningful unit is "a file", not a table or an array.
File-format specialisations belong in plugin packages.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Self

from scistudio.core.types.base import DataObject
from scistudio.stability import internal, provisional, stable


@stable(since="0.3.1")
class Artifact(DataObject):
    """An opaque file: a PDF, a rendered report, an image, a binary blob.

    Use an :class:`Artifact` when the result of a step is a whole file that
    later steps should carry along or save rather than inspect. SciStudio
    does not parse its contents; it just tracks the file, its MIME type, and
    a human-readable description.

    Example:
        >>> from pathlib import Path
        >>> from scistudio.core.types import Artifact
        >>> report = Artifact(
        ...     file_path=Path("/tmp/report.pdf"),
        ...     mime_type="application/pdf",
        ...     description="QC report",
        ... )
        >>> report.mime_type
        'application/pdf'
    """

    @stable(since="0.3.1")
    def __init__(
        self,
        *,
        file_path: Path | None = None,
        mime_type: str | None = None,
        description: str = "",
        **kwargs: Any,
    ) -> None:
        """Construct an artifact pointing at a file.

        Args:
            file_path: Path to the file on the local filesystem, if any.
            mime_type: The file's MIME type, e.g. ``"application/pdf"``.
            description: Short human-readable description.
            **kwargs: The shared :class:`DataObject` slots (``framework``,
                ``meta``, ``user``, ``storage_ref``).
        """
        super().__init__(**kwargs)
        self.file_path = file_path
        """Path to the file on the local filesystem, or ``None``."""
        self.mime_type = mime_type
        """The file's MIME type (e.g. ``"application/pdf"``), or ``None``."""
        self.description = description
        """Short human-readable description (empty string by default)."""

    @internal()
    def get_in_memory_data(self) -> Any:
        """Return file bytes for persistence."""
        if self.file_path is not None and self.file_path.exists():
            return self.file_path.read_bytes()
        return super().get_in_memory_data()

    # -- with_meta override (T-005's base only handles standard slots) ----

    @stable(since="0.3.1")
    def with_meta(self, **changes: Any) -> Self:
        """Return a copy with some typed ``meta`` fields changed.

        Like :meth:`DataObject.with_meta`, but also carries the
        artifact-specific fields (:attr:`file_path`, :attr:`mime_type`,
        :attr:`description`) onto the copy.

        Args:
            **changes: Field name / value pairs to update on the ``meta``
                model.

        Returns:
            A new artifact of the same type with the updated metadata.

        Raises:
            ValueError: if this artifact has no typed ``meta`` (only
                subclasses that declare a :attr:`Meta` model can use this).
        """
        if self._meta is None:
            raise ValueError(
                f"{type(self).__name__}.with_meta() requires a typed `meta` slot. "
                f"This instance has meta=None. Subclass with a class-level `Meta` "
                f"Pydantic model and pass an instance via the constructor to use "
                f"with_meta()."
            )

        from scistudio.core.meta import with_meta_changes

        new_meta = with_meta_changes(self._meta, **changes)
        new_framework = self._framework.derive()

        return type(self)(
            file_path=self.file_path,
            mime_type=self.mime_type,
            description=self.description,
            framework=new_framework,
            meta=new_meta,
            user=dict(self._user),
            storage_ref=self._storage_ref,
        )

    # -- worker subprocess reconstruction hooks (ADR-027 Addendum 1 §2) -----

    @classmethod
    @provisional(since="0.3.1")
    def reconstruct_extra_kwargs(cls, metadata: dict[str, Any]) -> dict[str, Any]:
        """Rebuild an artifact's constructor arguments from saved metadata.

        Reads ``file_path`` / ``mime_type`` / ``description`` back out of the
        metadata produced by :meth:`serialise_extra_metadata`. The path
        travels as a string (JSON has no path type) and is rebuilt into a
        :class:`pathlib.Path`; ``None`` is left unchanged. ``description``
        defaults to the empty string, matching the constructor.

        Args:
            metadata: The saved metadata dict for one artifact.

        Returns:
            Keyword arguments to pass to ``cls(**kwargs)``.
        """
        file_path_raw = metadata.get("file_path")
        return {
            "file_path": Path(file_path_raw) if file_path_raw is not None else None,
            "mime_type": metadata.get("mime_type"),
            "description": metadata.get("description", ""),
        }

    @classmethod
    @provisional(since="0.3.1")
    def serialise_extra_metadata(cls, obj: DataObject) -> dict[str, Any]:
        """Return an artifact's own fields for the saved metadata.

        The counterpart of :meth:`reconstruct_extra_kwargs`.
        :attr:`file_path` becomes a string (or ``None``) so the result is
        plain JSON.

        Args:
            obj: The artifact to serialise. Typed as :class:`DataObject` so
                it matches the base method's signature; the caller always
                passes an :class:`Artifact`.

        Returns:
            A JSON-serialisable dict of the artifact's fields.
        """
        assert isinstance(obj, Artifact), f"Expected Artifact, got {type(obj).__name__}"
        return {
            "file_path": str(obj.file_path) if obj.file_path is not None else None,
            "mime_type": obj.mime_type,
            "description": obj.description,
        }
