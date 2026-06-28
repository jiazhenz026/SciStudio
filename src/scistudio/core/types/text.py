"""Text content (:class:`Text`).

The data type for textual results — plain text, Markdown, or JSON. Use it
for notes, generated reports, log output, or any string payload a block
produces. Format-specific text kinds belong in plugin packages.
"""

from __future__ import annotations

from typing import Any, Self

from scistudio.core.types.base import DataObject
from scistudio.stability import internal, provisional, stable


@stable(since="0.3.1")
class Text(DataObject):
    """Textual data: plain text, Markdown, or JSON.

    Use this for any string result — a note, a generated report, JSON output.
    The :attr:`format` label records which flavour the text is, and
    :attr:`encoding` records its character encoding.

    Example:
        >>> from scistudio.core.types import Text
        >>> note = Text(content="All samples passed QC.", format="markdown")
        >>> note.format
        'markdown'
    """

    @stable(since="0.3.1")
    def __init__(
        self,
        *,
        content: str | None = None,
        format: str = "plain",
        encoding: str = "utf-8",
        **kwargs: Any,
    ) -> None:
        """Construct a text object.

        Args:
            content: The text content, or ``None`` for a metadata-only text object (no content).
            format: Content flavour: ``"plain"`` (default), ``"markdown"``,
                or ``"json"``.
            encoding: Character encoding; defaults to UTF-8.
            **kwargs: The shared :class:`DataObject` slots (``framework``,
                ``meta``, ``user``, ``storage_ref``).
        """
        super().__init__(**kwargs)
        self.content = content
        """The text itself, or ``None`` when not yet loaded."""
        self.format = format
        """Content flavour: ``"plain"`` (default), ``"markdown"``, or ``"json"``."""
        self.encoding = encoding
        """Character encoding; defaults to UTF-8."""

    @internal()
    def get_in_memory_data(self) -> Any:
        """Return text content for persistence."""
        if self.content is not None:
            return self.content
        return super().get_in_memory_data()

    # -- with_meta override (T-005's base only handles standard slots) ----

    @stable(since="0.3.1")
    def with_meta(self, **changes: Any) -> Self:
        """Return a copy with some typed ``meta`` fields changed.

        Like :meth:`DataObject.with_meta`, but also carries the text-specific
        fields (:attr:`content`, :attr:`format`, :attr:`encoding`) onto the
        copy.

        Args:
            **changes: Field name / value pairs to update on the ``meta``
                model.

        Returns:
            A new text object of the same type with the updated metadata.

        Raises:
            ValueError: if this object has no typed ``meta`` (only subclasses
                that declare a :attr:`Meta` model can use this).
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
    @provisional(since="0.3.1")
    def reconstruct_extra_kwargs(cls, metadata: dict[str, Any]) -> dict[str, Any]:
        """Rebuild a text object's constructor arguments from saved metadata.

        Reads ``content`` / ``format`` / ``encoding`` back out of the
        metadata produced by :meth:`serialise_extra_metadata`. ``format``
        defaults to ``"plain"`` and ``encoding`` to ``"utf-8"`` to match the
        constructor. ``content`` is optional; a metadata-only text object
        (its content lives in storage) round-trips with ``content=None``.

        Args:
            metadata: The saved metadata dict for one text object.

        Returns:
            Keyword arguments to pass to ``cls(**kwargs)``.
        """
        return {
            "content": metadata.get("content"),
            "format": metadata.get("format", "plain"),
            "encoding": metadata.get("encoding", "utf-8"),
        }

    @classmethod
    @provisional(since="0.3.1")
    def serialise_extra_metadata(cls, obj: DataObject) -> dict[str, Any]:
        """Return a text object's own fields for the saved metadata.

        The counterpart of :meth:`reconstruct_extra_kwargs`. All three fields
        are already JSON primitives and need no conversion.

        Args:
            obj: The text object to serialise. Typed as :class:`DataObject`
                so it matches the base method's signature; the caller always
                passes a :class:`Text`.

        Returns:
            A JSON-serialisable dict of the text object's fields.
        """
        assert isinstance(obj, Text), f"Expected Text, got {type(obj).__name__}"
        return {
            "content": obj.content,
            "format": obj.format,
            "encoding": obj.encoding,
        }
