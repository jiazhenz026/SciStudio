"""Short-cut base classes for simple, single-file loaders and savers.

:class:`SimpleLoader` and :class:`SimpleSaver` cover the most common IO block:
one file in, one object out (or the reverse). Instead of declaring full
:class:`~scistudio.blocks.io.FormatCapability` records by hand, set a few class
attributes (the data type, a format name, and the file extensions) and implement
one method; the base synthesizes a single conservative capability for you.
"""

from __future__ import annotations

from abc import abstractmethod
from pathlib import Path
from typing import Any, ClassVar

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.io.capabilities import (
    FormatCapability,
    MetadataFidelity,
    SimpleIODeclarationError,
    normalize_extensions,
)
from scistudio.blocks.io.io_block import IOBlock
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio.stability import stable


def _require_path(config: BlockConfig, *, base_name: str) -> Path:
    raw_path = config.get("path")
    if raw_path is None or (isinstance(raw_path, str) and not raw_path.strip()):
        raise ValueError(f"{base_name} requires a non-empty 'path' in config.params.")
    if isinstance(raw_path, (list, tuple, dict, set)):
        raise ValueError(f"{base_name} requires a single path string or PathLike in config.params.")
    try:
        return Path(raw_path)
    except TypeError as exc:
        raise ValueError(f"{base_name} requires a single path string or PathLike in config.params.") from exc


def _simple_capability_id(cls: type[IOBlock], direction: str, format_id: str) -> str:
    module = cls.__module__.replace(".__main__", "")
    return f"{module}.{cls.__name__}.{direction}.{format_id}".lower()


def _simple_label(format_id: str) -> str:
    return format_id.replace("_", " ").replace("-", " ").upper()


def _required_data_type(cls: type[IOBlock], attr_name: str) -> type[DataObject]:
    value = getattr(cls, attr_name, None)
    if not isinstance(value, type) or not issubclass(value, DataObject):
        raise SimpleIODeclarationError(f"{cls.__name__}.{attr_name} must be a DataObject subclass.")
    return value


def _required_format_id(cls: type[IOBlock]) -> str:
    value = getattr(cls, "format_id", None)
    if not isinstance(value, str) or not value.strip():
        raise SimpleIODeclarationError(f"{cls.__name__}.format_id must be a non-empty string.")
    return value.strip().lower()


def _required_extensions(cls: type[IOBlock]) -> tuple[str, ...]:
    value = getattr(cls, "extensions", None)
    if value is None:
        raise SimpleIODeclarationError(f"{cls.__name__}.extensions must declare at least one extension.")
    return normalize_extensions(value)


@stable(since="0.3.1")
class SimpleLoader(IOBlock):
    """Base class for a loader that reads one file into one data object.

    Subclass this for the common case of "load this file format into this data
    type". Set the class attributes :attr:`output_type`, :attr:`format_id`, and
    :attr:`extensions`, then implement :meth:`load_file`. The base wires up the
    rest: it declares one :class:`~scistudio.blocks.io.FormatCapability` from
    those attributes, reads the ``path`` from config, and calls your
    :meth:`load_file`. This is an input-only block; :meth:`save` always raises.

    Example:
        >>> class LoadJsonText(SimpleLoader):
        ...     output_type = Text
        ...     format_id = "json"
        ...     extensions = (".json",)
        ...     def load_file(self, path, config):
        ...         return Text(content=path.read_text(encoding="utf-8"), format="json")
    """

    direction: ClassVar[str] = "input"
    """Fixed to ``"input"`` — a SimpleLoader is always a loader."""
    output_type: ClassVar[type[DataObject]]
    """The :class:`DataObject` subclass :meth:`load_file` returns. Required."""
    extensions: ClassVar[list[str] | tuple[str, ...]]
    """File extensions this loader handles (e.g. ``(".json",)``). Required."""
    format_id: ClassVar[str]
    """Short stable format name for the synthesized capability (e.g. ``"json"``).

    Required."""
    metadata_fidelity: ClassVar[MetadataFidelity] = MetadataFidelity(level="pixel_only")
    """How much metadata the synthesized capability preserves. Defaults to
    values-only; override for richer fidelity."""

    @classmethod
    @stable(since="0.3.1")
    def get_format_capabilities(cls) -> tuple[FormatCapability, ...]:
        """Return the single capability synthesized from this loader's attributes.

        Uses :attr:`format_capabilities` when a subclass sets it explicitly;
        otherwise builds one load
        :class:`~scistudio.blocks.io.FormatCapability` from :attr:`output_type`,
        :attr:`format_id`, :attr:`extensions`, and :attr:`metadata_fidelity`.

        Returns:
            A one-element tuple holding the synthesized (or explicitly declared)
            capability.

        Raises:
            SimpleIODeclarationError: if a required attribute is missing.
        """
        if cls.format_capabilities:
            return super().get_format_capabilities()
        output_type = _required_data_type(cls, "output_type")
        format_id = _required_format_id(cls)
        return (
            FormatCapability(
                id=_simple_capability_id(cls, "load", format_id),
                direction="load",
                data_type=output_type,
                format_id=format_id,
                extensions=_required_extensions(cls),
                label=_simple_label(format_id),
                block_type=cls.__name__,
                handler="load_file",
                metadata_fidelity=cls.metadata_fidelity,
                is_synthesized=True,
            ),
        )

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        """Read the configured ``path`` and return the loaded object.

        Resolves the single ``path`` from ``config`` and delegates to
        :meth:`load_file`. You normally do not override this.

        Args:
            config: The block configuration; must carry a single ``path``.
            output_dir: Unused by the simple loader (kept for the base signature).

        Returns:
            The object produced by :meth:`load_file`.
        """
        return self.load_file(_require_path(config, base_name=type(self).__name__), dict(config.params))

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        """Always raises — a SimpleLoader cannot save.

        Raises:
            TypeError: always; use a :class:`SimpleSaver` to write files.
        """
        raise TypeError(f"{type(self).__name__} is a loader and does not implement save().")

    @abstractmethod
    @stable(since="0.3.1")
    def load_file(self, path: Path, config: dict[str, Any]) -> DataObject:
        """Read one object from *path*. Implement this in your loader.

        Args:
            path: The file to read.
            config: The block's config params as a plain dict.

        Returns:
            The loaded :class:`DataObject` (an instance of :attr:`output_type`).
        """
        ...


@stable(since="0.3.1")
class SimpleSaver(IOBlock):
    """Base class for a saver that writes one data object to one file.

    Subclass this for the common case of "write this data type to this file
    format". Set the class attributes :attr:`input_type`, :attr:`format_id`, and
    :attr:`extensions`, then implement :meth:`save_file`. The base declares one
    :class:`~scistudio.blocks.io.FormatCapability`, checks the incoming object's
    type, resolves the ``path``, and calls your :meth:`save_file`. This is an
    output-only block; :meth:`load` always raises.

    Example:
        >>> class SaveJsonText(SimpleSaver):
        ...     input_type = Text
        ...     format_id = "json"
        ...     extensions = (".json",)
        ...     def save_file(self, obj, path, config):
        ...         path.write_text(obj.content, encoding="utf-8")
    """

    direction: ClassVar[str] = "output"
    """Fixed to ``"output"`` — a SimpleSaver is always a saver."""
    input_type: ClassVar[type[DataObject]]
    """The :class:`DataObject` subclass this saver accepts and writes. Required."""
    extensions: ClassVar[list[str] | tuple[str, ...]]
    """File extensions this saver handles (e.g. ``(".json",)``). Required."""
    format_id: ClassVar[str]
    """Short stable format name for the synthesized capability (e.g. ``"json"``).

    Required."""
    metadata_fidelity: ClassVar[MetadataFidelity] = MetadataFidelity(level="pixel_only")
    """How much metadata the synthesized capability preserves. Defaults to
    values-only; override for richer fidelity."""

    @classmethod
    @stable(since="0.3.1")
    def get_format_capabilities(cls) -> tuple[FormatCapability, ...]:
        """Return the single capability synthesized from this saver's attributes.

        Uses :attr:`format_capabilities` when a subclass sets it explicitly;
        otherwise builds one save
        :class:`~scistudio.blocks.io.FormatCapability` from :attr:`input_type`,
        :attr:`format_id`, :attr:`extensions`, and :attr:`metadata_fidelity`.

        Returns:
            A one-element tuple holding the synthesized (or explicitly declared)
            capability.

        Raises:
            SimpleIODeclarationError: if a required attribute is missing.
        """
        if cls.format_capabilities:
            return super().get_format_capabilities()
        input_type = _required_data_type(cls, "input_type")
        format_id = _required_format_id(cls)
        return (
            FormatCapability(
                id=_simple_capability_id(cls, "save", format_id),
                direction="save",
                data_type=input_type,
                format_id=format_id,
                extensions=_required_extensions(cls),
                label=_simple_label(format_id),
                block_type=cls.__name__,
                handler="save_file",
                metadata_fidelity=cls.metadata_fidelity,
                is_synthesized=True,
            ),
        )

    def load(self, config: BlockConfig, output_dir: str = "") -> DataObject | Collection:
        """Always raises — a SimpleSaver cannot load.

        Raises:
            TypeError: always; use a :class:`SimpleLoader` to read files.
        """
        raise TypeError(f"{type(self).__name__} is a saver and does not implement load().")

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        """Validate the incoming object and write it to the configured path.

        Accepts a single object or a one-item :class:`Collection`, checks it is
        an :attr:`input_type` instance, then delegates to :meth:`save_file`. You
        normally do not override this.

        Args:
            obj: The object (or single-item Collection) to write.
            config: The block configuration; must carry a single ``path``.

        Raises:
            ValueError: if a Collection without exactly one item is given.
            TypeError: if the object is not an :attr:`input_type` instance.
        """
        if isinstance(obj, Collection):
            if len(obj) != 1:
                raise ValueError(f"{type(self).__name__} requires exactly one object to save.")
            item = obj[0]
        else:
            item = obj
        if not isinstance(item, self.input_type):
            raise TypeError(f"{type(self).__name__} expected {self.input_type.__name__}, got {type(item).__name__}.")
        self.save_file(item, _require_path(config, base_name=type(self).__name__), dict(config.params))

    @abstractmethod
    @stable(since="0.3.1")
    def save_file(self, obj: DataObject, path: Path, config: dict[str, Any]) -> None:
        """Write one object to *path*. Implement this in your saver.

        Args:
            obj: The object to write (an instance of :attr:`input_type`).
            path: The destination file.
            config: The block's config params as a plain dict.
        """
        ...
