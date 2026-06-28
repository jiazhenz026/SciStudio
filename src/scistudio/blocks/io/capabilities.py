"""IO format capability declarations for ADR-043.

The classes in this module describe boundary conversions owned by IOBlock
classes. They intentionally model file formats as IO capabilities, not as
properties of DataObject types.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

from scistudio.core.types.base import DataObject
from scistudio.stability import stable

# Stability: stable type-aliases (ADR-052 §6.3). ``Literal`` special forms
# cannot carry a stability marker; tier is recorded in the ADR-052 contract.
CapabilityDirection = Literal["load", "save"]
MetadataFidelityLevel = Literal[
    "pixel_only",
    "typed_meta",
    "format_specific",
    "lossless",
]

VALID_CAPABILITY_DIRECTIONS: frozenset[str] = frozenset({"load", "save"})
VALID_METADATA_FIDELITY_LEVELS: frozenset[str] = frozenset({"pixel_only", "typed_meta", "format_specific", "lossless"})


@stable(since="0.3.1")
class CapabilityValidationError(ValueError):
    """Base class for invalid IO capability declarations.

    Public/stable (ADR-052 §6.3): authors may catch this (and its subclasses)
    for internal fallback when a capability declaration is rejected.
    """


@stable(since="0.3.1")
class InvalidExtensionError(CapabilityValidationError):
    """Raised when an extension cannot be normalized safely."""


@stable(since="0.3.1")
class InvalidMetadataFidelityError(CapabilityValidationError):
    """Raised when a metadata fidelity declaration is invalid."""


@stable(since="0.3.1")
class InvalidFormatCapabilityError(CapabilityValidationError):
    """Raised when a format capability declaration is internally invalid."""


@stable(since="0.3.1")
class SimpleIODeclarationError(CapabilityValidationError):
    """Raised when a SimpleLoader/SimpleSaver class omits required fields."""


def normalize_extension(extension: str) -> str:
    """Return a lowercase extension with a leading dot.

    Internal (ADR-052 §6.3): the framework normalizes extensions automatically
    via ``FormatCapability.__post_init__``; not part of the public surface.
    """

    if not isinstance(extension, str):
        raise InvalidExtensionError(f"Extension must be a string, got {type(extension).__name__}.")
    value = extension.strip().lower()
    if not value:
        raise InvalidExtensionError("Extension must not be empty.")
    if value == ".":
        raise InvalidExtensionError("Extension must contain characters after the leading dot.")
    if "/" in value or "\\" in value:
        raise InvalidExtensionError(f"Extension must not contain path separators: {extension!r}.")
    if not value.startswith("."):
        value = f".{value}"
    return value


def normalize_extensions(extensions: Iterable[str]) -> tuple[str, ...]:
    """Normalize an extension iterable into an ordered tuple without duplicates."""

    if isinstance(extensions, str):
        raise InvalidExtensionError("Extensions must be an iterable of strings, not a scalar string.")
    try:
        values = tuple(extensions)
    except TypeError as exc:
        raise InvalidExtensionError("Extensions must be an iterable of strings.") from exc
    normalized = tuple(dict.fromkeys(normalize_extension(ext) for ext in values))
    if not normalized:
        raise InvalidExtensionError("At least one extension is required.")
    return normalized


def _normalize_string_tuple(values: Iterable[str], *, field_name: str) -> tuple[str, ...]:
    if isinstance(values, str):
        raise InvalidMetadataFidelityError(f"{field_name} must be an iterable of strings, not a scalar string.")
    try:
        items = tuple(values)
    except TypeError as exc:
        raise InvalidMetadataFidelityError(f"{field_name} must be an iterable of strings.") from exc
    for item in items:
        if not isinstance(item, str) or not item.strip():
            raise InvalidMetadataFidelityError(f"{field_name} entries must be non-empty strings.")
    return tuple(dict.fromkeys(item.strip() for item in items))


def _meta_model_fields(data_type: type[DataObject]) -> frozenset[str]:
    meta_model = getattr(data_type, "Meta", None)
    if meta_model is None:
        return frozenset()
    if not isinstance(meta_model, type) or not issubclass(meta_model, BaseModel):
        raise InvalidMetadataFidelityError(
            f"{data_type.__name__}.Meta must be a pydantic BaseModel subclass when metadata fields are declared."
        )
    return frozenset(meta_model.model_fields.keys())


@stable(since="0.3.1")
@dataclass(frozen=True)
class MetadataFidelity:
    """Typed ``meta`` preservation contract for one IO boundary capability."""

    level: MetadataFidelityLevel = "pixel_only"
    typed_meta_reads: tuple[str, ...] = ()
    typed_meta_writes: tuple[str, ...] = ()
    format_metadata_reads: tuple[str, ...] = ()
    format_metadata_writes: tuple[str, ...] = ()
    notes: str | None = None

    def __post_init__(self) -> None:
        if self.level not in VALID_METADATA_FIDELITY_LEVELS:
            raise InvalidMetadataFidelityError(f"Unknown metadata fidelity level: {self.level!r}.")

        typed_reads = _normalize_string_tuple(self.typed_meta_reads, field_name="typed_meta_reads")
        typed_writes = _normalize_string_tuple(self.typed_meta_writes, field_name="typed_meta_writes")
        format_reads = _normalize_string_tuple(self.format_metadata_reads, field_name="format_metadata_reads")
        format_writes = _normalize_string_tuple(self.format_metadata_writes, field_name="format_metadata_writes")

        object.__setattr__(self, "typed_meta_reads", typed_reads)
        object.__setattr__(self, "typed_meta_writes", typed_writes)
        object.__setattr__(self, "format_metadata_reads", format_reads)
        object.__setattr__(self, "format_metadata_writes", format_writes)

        if self.level == "pixel_only" and (typed_reads or typed_writes or format_reads or format_writes):
            raise InvalidMetadataFidelityError("pixel_only fidelity must not declare preserved metadata fields.")
        if self.level == "typed_meta" and not (typed_reads or typed_writes):
            raise InvalidMetadataFidelityError(
                "typed_meta fidelity must declare typed_meta_reads or typed_meta_writes."
            )
        if self.level == "format_specific" and not (format_reads or format_writes):
            raise InvalidMetadataFidelityError(
                "format_specific fidelity must declare format_metadata_reads or format_metadata_writes."
            )

    @property
    @stable(since="0.3.1")
    def typed_meta_fields(self) -> tuple[str, ...]:
        """Return all declared typed ``meta`` fields without duplicates."""

        return tuple(dict.fromkeys((*self.typed_meta_reads, *self.typed_meta_writes)))

    @property
    @stable(since="0.3.1")
    def format_metadata_fields(self) -> tuple[str, ...]:
        """Return all declared format-specific metadata fields without duplicates."""

        return tuple(dict.fromkeys((*self.format_metadata_reads, *self.format_metadata_writes)))

    @stable(since="0.3.1")
    def validate_typed_meta_fields(self, data_type: type[DataObject]) -> None:
        """Validate declared typed ``meta`` fields against ``data_type.Meta``."""

        fields = self.typed_meta_fields
        if not fields:
            return
        available = _meta_model_fields(data_type)
        missing = tuple(field for field in fields if field not in available)
        if missing:
            raise InvalidMetadataFidelityError(
                f"{data_type.__name__}.Meta does not declare metadata fields: {', '.join(missing)}."
            )


@stable(since="0.3.1")
@dataclass(frozen=True)
class FormatCapability:
    """One external file-format conversion owned by an IOBlock class."""

    id: str
    direction: CapabilityDirection
    data_type: type[DataObject]
    format_id: str
    extensions: tuple[str, ...]
    label: str
    block_type: str
    handler: str
    is_default: bool = False
    priority: int = 0
    roundtrip_group: str | None = None
    metadata_fidelity: MetadataFidelity = field(default_factory=MetadataFidelity)
    is_synthesized: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise InvalidFormatCapabilityError("Capability id must be a non-empty string.")
        if self.direction not in VALID_CAPABILITY_DIRECTIONS:
            raise InvalidFormatCapabilityError(
                f"Capability direction must be 'load' or 'save', got {self.direction!r}."
            )
        if not isinstance(self.data_type, type) or not issubclass(self.data_type, DataObject):
            raise InvalidFormatCapabilityError("Capability data_type must be a DataObject subclass.")
        if not isinstance(self.format_id, str) or not self.format_id.strip():
            raise InvalidFormatCapabilityError("Capability format_id must be a non-empty string.")
        if not isinstance(self.label, str) or not self.label.strip():
            raise InvalidFormatCapabilityError("Capability label must be a non-empty string.")
        if not isinstance(self.block_type, str) or not self.block_type.strip():
            raise InvalidFormatCapabilityError("Capability block_type must be a non-empty string.")
        if not isinstance(self.handler, str) or not self.handler.strip():
            raise InvalidFormatCapabilityError("Capability handler must be a non-empty string.")
        if not isinstance(self.metadata_fidelity, MetadataFidelity):
            raise InvalidFormatCapabilityError("metadata_fidelity must be a MetadataFidelity instance.")

        object.__setattr__(self, "id", self.id.strip())
        object.__setattr__(self, "format_id", self.format_id.strip().lower())
        object.__setattr__(self, "extensions", normalize_extensions(self.extensions))
        object.__setattr__(self, "label", self.label.strip())
        object.__setattr__(self, "block_type", self.block_type.strip())
        object.__setattr__(self, "handler", self.handler.strip())
        if self.roundtrip_group is not None:
            group = self.roundtrip_group.strip()
            if not group:
                raise InvalidFormatCapabilityError("roundtrip_group must not be empty when provided.")
            object.__setattr__(self, "roundtrip_group", group)

        self.metadata_fidelity.validate_typed_meta_fields(self.data_type)
        if self.metadata_fidelity.level == "lossless" and self.roundtrip_group is None:
            raise InvalidFormatCapabilityError("lossless capabilities must declare roundtrip_group.")

    @property
    @stable(since="0.3.1")
    def migration_scaffold(self) -> bool:
        """Whether this capability was synthesized from legacy declarations."""

        return self.is_synthesized

    @property
    @stable(since="0.3.1")
    def normalized_extensions(self) -> tuple[str, ...]:
        """Return normalized extensions for downstream registry code."""

        return self.extensions
