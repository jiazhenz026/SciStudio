"""Ergonomic local IOBlock bases for ADR-043."""

from __future__ import annotations

from abc import abstractmethod
from pathlib import Path
from typing import Any, ClassVar

from scieasy.blocks.base.config import BlockConfig
from scieasy.blocks.io.capabilities import (
    FormatCapability,
    MetadataFidelity,
    SimpleIODeclarationError,
    normalize_extensions,
)
from scieasy.blocks.io.io_block import IOBlock
from scieasy.core.types.base import DataObject
from scieasy.core.types.collection import Collection


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


class SimpleLoader(IOBlock):
    """Small local loader base that synthesizes one conservative capability."""

    direction: ClassVar[str] = "input"
    output_type: ClassVar[type[DataObject]]
    extensions: ClassVar[list[str] | tuple[str, ...]]
    format_id: ClassVar[str]
    metadata_fidelity: ClassVar[MetadataFidelity] = MetadataFidelity(level="pixel_only")

    @classmethod
    def get_format_capabilities(cls) -> tuple[FormatCapability, ...]:
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
        return self.load_file(_require_path(config, base_name=type(self).__name__), dict(config.params))

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
        raise TypeError(f"{type(self).__name__} is a loader and does not implement save().")

    @abstractmethod
    def load_file(self, path: Path, config: dict[str, Any]) -> DataObject:
        """Load one object from *path*."""
        ...


class SimpleSaver(IOBlock):
    """Small local saver base that synthesizes one conservative capability."""

    direction: ClassVar[str] = "output"
    input_type: ClassVar[type[DataObject]]
    extensions: ClassVar[list[str] | tuple[str, ...]]
    format_id: ClassVar[str]
    metadata_fidelity: ClassVar[MetadataFidelity] = MetadataFidelity(level="pixel_only")

    @classmethod
    def get_format_capabilities(cls) -> tuple[FormatCapability, ...]:
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
        raise TypeError(f"{type(self).__name__} is a saver and does not implement load().")

    def save(self, obj: DataObject | Collection, config: BlockConfig) -> None:
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
    def save_file(self, obj: DataObject, path: Path, config: dict[str, Any]) -> None:
        """Save one object to *path*."""
        ...
