"""Records that describe which file formats an IO block can read or write.

A "capability" pairs a data type with one external file format (for example,
"this block can save a DataFrame as CSV") plus a note on how faithfully metadata
survives the round trip. File-format support lives here, on the IO block that
performs the conversion, rather than on the data type itself: the same DataFrame
can be saved by several different blocks to several different formats.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel

from scistudio.core.types.base import DataObject
from scistudio.stability import stable

# ``Literal`` special forms cannot carry a stability marker; the stable tier for
# these aliases is recorded in the public-API contract docs.
CapabilityDirection = Literal["load", "save"]
"""Direction of a capability: ``"load"`` reads a file, ``"save"`` writes one."""
MetadataFidelityLevel = Literal[
    "pixel_only",
    "typed_meta",
    "format_specific",
    "lossless",
]
"""How much metadata a capability preserves, from least to most.

``"pixel_only"`` keeps only the raw values; ``"typed_meta"`` also preserves the
data object's typed ``meta`` fields; ``"format_specific"`` additionally keeps
format-native metadata; ``"lossless"`` guarantees a faithful round trip and must
name a ``roundtrip_group``.
"""

VALID_CAPABILITY_DIRECTIONS: frozenset[str] = frozenset({"load", "save"})
VALID_METADATA_FIDELITY_LEVELS: frozenset[str] = frozenset({"pixel_only", "typed_meta", "format_specific", "lossless"})


@stable(since="0.3.1")
class CapabilityValidationError(ValueError):
    """Base error for an invalid IO format-capability declaration.

    Raised when a block declares a :class:`FormatCapability`,
    :class:`MetadataFidelity`, or a :class:`~scistudio.blocks.io.SimpleLoader` /
    :class:`~scistudio.blocks.io.SimpleSaver` whose fields do not make sense.
    Catch this (or one of its more specific subclasses below) when you want to
    detect and recover from a bad declaration yourself instead of letting it
    propagate.
    """


@stable(since="0.3.1")
class InvalidExtensionError(CapabilityValidationError):
    """Raised when a file extension cannot be turned into a safe ``.ext`` form.

    Triggered by, for example, an empty string, a bare ``"."``, or a value that
    contains a path separator such as ``"/"`` or ``"\\"``.
    """


@stable(since="0.3.1")
class InvalidMetadataFidelityError(CapabilityValidationError):
    """Raised when a :class:`MetadataFidelity` declaration is inconsistent.

    For example: an unknown fidelity level, a ``"pixel_only"`` level that still
    lists preserved fields, or a typed-metadata field that the data type's
    ``Meta`` model does not declare.
    """


@stable(since="0.3.1")
class InvalidFormatCapabilityError(CapabilityValidationError):
    """Raised when a :class:`FormatCapability` record is internally inconsistent.

    For example: a blank id or label, a direction other than ``"load"`` /
    ``"save"``, a ``data_type`` that is not a :class:`DataObject` subclass, or a
    ``"lossless"`` capability that names no ``roundtrip_group``.
    """


@stable(since="0.3.1")
class SimpleIODeclarationError(CapabilityValidationError):
    """Raised when a :class:`~scistudio.blocks.io.SimpleLoader` or
    :class:`~scistudio.blocks.io.SimpleSaver` subclass omits a required field.

    These ergonomic bases require the subclass to set ``format_id``,
    ``extensions``, and the ``output_type`` (loader) or ``input_type`` (saver).
    The error names the field that is missing or has the wrong type.
    """


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
    """How much of a file's metadata one IO capability preserves.

    Attach this to a :class:`FormatCapability` to record what survives a read or
    write: just the raw values, the data object's typed ``meta`` fields, extra
    format-native metadata, or a fully lossless round trip. On construction the
    declared fields are checked for consistency (for example, a ``"pixel_only"``
    capability may not also list preserved fields).

    Example:
        >>> MetadataFidelity(level="pixel_only")  # keep only the values
        >>> MetadataFidelity(
        ...     level="typed_meta",
        ...     typed_meta_writes=("exposure_time",),
        ... )
    """

    level: MetadataFidelityLevel = "pixel_only"
    """Overall preservation level; see :data:`MetadataFidelityLevel`."""
    typed_meta_reads: tuple[str, ...] = ()
    """Typed ``meta`` field names this capability fills in when *reading* a file."""
    typed_meta_writes: tuple[str, ...] = ()
    """Typed ``meta`` field names this capability persists when *writing* a file."""
    format_metadata_reads: tuple[str, ...] = ()
    """Format-native metadata keys recovered when *reading* (``format_specific``)."""
    format_metadata_writes: tuple[str, ...] = ()
    """Format-native metadata keys preserved when *writing* (``format_specific``)."""
    notes: str | None = None
    """Optional free-text note describing fidelity caveats for this capability."""

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
        """All typed ``meta`` field names this capability touches, de-duplicated.

        Returns:
            The union of :attr:`typed_meta_reads` and :attr:`typed_meta_writes`,
            in first-seen order with duplicates removed.
        """

        return tuple(dict.fromkeys((*self.typed_meta_reads, *self.typed_meta_writes)))

    @property
    @stable(since="0.3.1")
    def format_metadata_fields(self) -> tuple[str, ...]:
        """All format-native metadata keys this capability touches, de-duplicated.

        Returns:
            The union of :attr:`format_metadata_reads` and
            :attr:`format_metadata_writes`, in first-seen order without
            duplicates.
        """

        return tuple(dict.fromkeys((*self.format_metadata_reads, *self.format_metadata_writes)))

    @stable(since="0.3.1")
    def validate_typed_meta_fields(self, data_type: type[DataObject]) -> None:
        """Check that every declared typed ``meta`` field exists on the data type.

        Pass the :class:`DataObject` subclass the capability applies to. The
        check does nothing when no typed fields are declared.

        Args:
            data_type: Data type whose ``Meta`` model must declare the fields
                named in :attr:`typed_meta_reads` / :attr:`typed_meta_writes`.

        Raises:
            InvalidMetadataFidelityError: if any declared field is missing from
                ``data_type.Meta``.
        """

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
    """One file-format conversion an IO block can perform.

    Records that a specific block can read (or write) one data type as one file
    format — for example, "save a :class:`DataFrame` as a ``.csv`` file". A block
    lists its capabilities in its ``format_capabilities`` so the runtime can pick
    the right block for a given file extension and so the format appears in the
    UI. Every field is validated and normalized on construction (extensions are
    lowercased with a leading dot, ids and labels are trimmed).

    Example:
        >>> FormatCapability(
        ...     id="mypkg.MyCsvSaver.save.csv",
        ...     direction="save",
        ...     data_type=DataObject,
        ...     format_id="csv",
        ...     extensions=(".csv",),
        ...     label="CSV",
        ...     block_type="MyCsvSaver",
        ...     handler="save_file",
        ... )
    """

    id: str
    """Stable, unique identifier for this capability (e.g. ``"mypkg.Saver.save.csv"``)."""
    direction: CapabilityDirection
    """Whether this capability loads (reads) or saves (writes) the file."""
    data_type: type[DataObject]
    """The :class:`DataObject` subclass this capability reads into or writes from."""
    format_id: str
    """Short stable format name, lowercased (e.g. ``"csv"``, ``"ome_tiff"``)."""
    extensions: tuple[str, ...]
    """File extensions this format uses, normalized to lowercase with a leading dot."""
    label: str
    """Human-readable name shown in the UI (e.g. ``"CSV"``, ``"OME-TIFF"``)."""
    block_type: str
    """Class name of the IO block that owns this capability."""
    handler: str
    """Name of the block method that performs the conversion (e.g. ``"save_file"``)."""
    is_default: bool = False
    """Whether this is the preferred capability when several match one extension."""
    priority: int = 0
    """Tie-breaker when several capabilities match; higher wins."""
    roundtrip_group: str | None = None
    """Tag pairing a load capability with its matching save capability.

    Required for ``"lossless"`` fidelity so the framework knows the read and
    write sides form a faithful round trip.
    """
    metadata_fidelity: MetadataFidelity = field(default_factory=MetadataFidelity)
    """How much metadata this conversion preserves; see :class:`MetadataFidelity`."""
    is_synthesized: bool = False
    """``True`` when this record was generated from a legacy declaration rather
    than written by hand. See :attr:`migration_scaffold`."""

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
        """Whether this capability was generated from a legacy declaration.

        Returns:
            ``True`` when the record was synthesized automatically (so tools can
            tell it apart from a final, hand-authored declaration); otherwise
            ``False``. Mirrors :attr:`is_synthesized`.
        """

        return self.is_synthesized

    @property
    @stable(since="0.3.1")
    def normalized_extensions(self) -> tuple[str, ...]:
        """The capability's file extensions, already lowercased with leading dots.

        Returns:
            The same value as :attr:`extensions`; exposed under this name for
            registry code that asks for the normalized form explicitly.
        """

        return self.extensions
