"""Text — plain text, markdown, or JSON content DataObject.

ADR-027 D2: this module is core-only. No domain subclasses of
:class:`Text` exist in core; any future text-format specialisations
(e.g. LaTeX, RTF) should live in a plugin package.
"""

from __future__ import annotations

from typing import Any, Self

from scistudio.core.types.base import DataObject


class Text(DataObject):
    """Textual data object (plain text, markdown, JSON, etc.).

    Attributes:
        content: The text content, if loaded.
        format: Content format identifier (e.g. ``"plain"``, ``"markdown"``,
            ``"json"``).
        encoding: Character encoding (default UTF-8).
    """

    def __init__(
        self,
        *,
        content: str | None = None,
        format: str = "plain",
        encoding: str = "utf-8",
        **kwargs: Any,
    ) -> None:
        """Construct a Text with optional content and format metadata.

        Standard :class:`DataObject` slots (``framework``, ``meta``,
        ``user``, ``storage_ref``) are passed through ``**kwargs`` to
        :meth:`DataObject.__init__`.
        """
        super().__init__(**kwargs)
        self.content = content
        self.format = format
        self.encoding = encoding

    def get_in_memory_data(self) -> Any:
        """Return text content for persistence."""
        if self.content is not None:
            return self.content
        return super().get_in_memory_data()

    # -- with_meta override (T-005's base only handles standard slots) ----

    def with_meta(self, **changes: Any) -> Self:
        """Return a new Text with the ``meta`` slot updated.

        Overrides :meth:`DataObject.with_meta` to propagate the
        Text-specific constructor arguments (``content``, ``format``,
        ``encoding``). The base implementation only propagates the four
        standard DataObject slots (``framework``, ``meta``, ``user``,
        ``storage_ref``); without this override the call would lose the
        Text-specific attributes on the returned instance.

        Raises:
            ValueError: if ``self.meta is None`` (no typed Meta to
                update). Only Text subclasses that declare a ``Meta``
                ClassVar can use :meth:`with_meta`.
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
            content=self.content,
            format=self.format,
            encoding=self.encoding,
            framework=new_framework,
            meta=new_meta,
            user=dict(self._user),
            storage_ref=self._storage_ref,
        )

    # -- worker subprocess reconstruction hooks (ADR-027 Addendum 1 §2) -----

    @classmethod
    def _reconstruct_extra_kwargs(cls, metadata: dict[str, Any]) -> dict[str, Any]:
        """Return ``Text``-specific kwargs for worker reconstruction.

        Extracts ``content`` / ``format`` / ``encoding`` from the
        wire-format metadata sidecar. ``format`` defaults to ``"plain"``
        and ``encoding`` to ``"utf-8"`` to mirror the constructor's
        defaults. ``content`` is optional; metadata-only ``Text``
        instances (content lives in the storage backend) round-trip
        with ``content=None``.

        See ADR-027 Addendum 1 §2 ("D11' companion") for the full
        contract.
        """
        return {
            "content": metadata.get("content"),
            "format": metadata.get("format", "plain"),
            "encoding": metadata.get("encoding", "utf-8"),
        }

    @classmethod
    def _serialise_extra_metadata(cls, obj: DataObject) -> dict[str, Any]:
        """Return ``Text``-specific fields for the metadata sidecar.

        Symmetric counterpart of :meth:`_reconstruct_extra_kwargs`. All
        three fields are already JSON-primitive (``str | None``) and
        need no conversion.

        The parameter is typed as :class:`DataObject` to respect the
        Liskov substitution principle with the base classmethod; at
        runtime the caller only ever passes an instance of ``cls``.
        """
        assert isinstance(obj, Text), f"Expected Text, got {type(obj).__name__}"
        return {
            "content": obj.content,
            "format": obj.format,
            "encoding": obj.encoding,
        }
