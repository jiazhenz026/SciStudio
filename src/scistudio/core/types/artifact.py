"""Artifact — opaque file DataObject (PDF, binary, image, report).

ADR-027 D2: this module is core-only. No domain subclasses of
:class:`Artifact` exist in core; any future file-format specialisations
(e.g. ``PdfArtifact``, ``HtmlReport``) should live in a plugin package.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Self

from scistudio.core.types.base import DataObject
from scistudio.stability import provisional, stable


@stable(since="0.3.1")
class Artifact(DataObject):
    """Opaque file artifact (PDF, binary blob, rendered report, etc.).

    Attributes:
        file_path: Local filesystem path to the artifact, if available.
        mime_type: MIME type of the artifact (e.g. ``"application/pdf"``).
        description: Human-readable description.
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
        """Construct an Artifact with optional file/MIME/description.

        Standard :class:`DataObject` slots (``framework``, ``meta``,
        ``user``, ``storage_ref``) are passed through ``**kwargs`` to
        :meth:`DataObject.__init__`.
        """
        super().__init__(**kwargs)
        self.file_path = file_path
        self.mime_type = mime_type
        self.description = description

    def get_in_memory_data(self) -> Any:
        """Return file bytes for persistence."""
        if self.file_path is not None and self.file_path.exists():
            return self.file_path.read_bytes()
        return super().get_in_memory_data()

    # -- with_meta override (T-005's base only handles standard slots) ----

    @stable(since="0.3.1")
    def with_meta(self, **changes: Any) -> Self:
        """Return a new Artifact with the ``meta`` slot updated.

        Overrides :meth:`DataObject.with_meta` to propagate the
        Artifact-specific constructor arguments (``file_path``,
        ``mime_type``, ``description``). The base implementation only
        propagates the four standard DataObject slots (``framework``,
        ``meta``, ``user``, ``storage_ref``); without this override the
        call would lose the Artifact-specific attributes on the
        returned instance.

        Raises:
            ValueError: if ``self.meta is None`` (no typed Meta to
                update). Only Artifact subclasses that declare a
                ``Meta`` ClassVar can use :meth:`with_meta`.
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
        """Return ``Artifact``-specific kwargs for worker reconstruction.

        Extracts ``file_path`` / ``mime_type`` / ``description`` from
        the wire-format metadata sidecar. ``file_path`` is stored as a
        string on the wire (``pathlib.Path`` is not JSON-native) and
        rebuilt into a :class:`pathlib.Path` here; ``None`` round-trips
        unchanged. ``description`` defaults to the empty string to
        mirror :meth:`Artifact.__init__`.

        See ADR-027 Addendum 1 §2 ("D11' companion") for the full
        contract.
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
        """Return ``Artifact``-specific fields for the metadata sidecar.

        Symmetric counterpart of :meth:`reconstruct_extra_kwargs`.
        :attr:`Artifact.file_path` is converted to a string (or
        ``None``) so the payload is JSON-clean.

        The parameter is typed as :class:`DataObject` to respect the
        Liskov substitution principle with the base classmethod; at
        runtime the caller only ever passes an instance of ``cls``.
        """
        assert isinstance(obj, Artifact), f"Expected Artifact, got {type(obj).__name__}"
        return {
            "file_path": str(obj.file_path) if obj.file_path is not None else None,
            "mime_type": obj.mime_type,
            "description": obj.description,
        }
