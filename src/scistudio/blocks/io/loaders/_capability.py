"""Load-direction :class:`FormatCapability` declarations for ``LoadData``.

Per ADR-028 Addendum 1 §C9 ("private functions, not helper classes")
this module is package-private: every public symbol is prefixed with an
underscore and the module name itself starts with an underscore.

ADR-043 / spec ``adr-043-package-migration`` FR-001 / FR-003 require
:class:`LoadData` to expose explicit :class:`FormatCapability` records via
its ``format_capabilities`` ClassVar so the block registry can discover
the loader from a target ``data_type`` + extension query. This module
holds the capability tuple, the legacy ``extension -> format_id`` lookup
derived from it, and the format-resolution helper used by
:meth:`LoadData._detect_format`.

Extracted from :mod:`scistudio.blocks.io.loaders.load_data` in issue
#1459 (Phase 2 of the backend god-file refactor umbrella #1427).
Symmetric to :mod:`scistudio.blocks.io.savers._capability` on the save
side.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from scistudio.blocks.io.capabilities import FormatCapability, MetadataFidelity
from scistudio.core.types.array import Array
from scistudio.core.types.artifact import Artifact
from scistudio.core.types.base import DataObject
from scistudio.core.types.composite import CompositeData
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.series import Series
from scistudio.core.types.text import Text

# Issue #1482: ``_resolve_format`` previously typed its ``block`` parameter
# as ``LoadData | None`` and imported ``LoadData`` under
# ``if TYPE_CHECKING:`` from :mod:`scistudio.blocks.io.loaders.load_data`.
# Sentrux's AST analysis counted that as a bidirectional edge and flagged
# the bare ``_capability ↔ load_data`` cycle even though the import never
# executed at runtime. Per ADR-028 Addendum 1 §C9 this sibling module
# must hold no helper classes (so a structural ``Protocol`` is also
# disallowed); the parameter is duck-typed as ``Any | None`` instead.
# The single call site (``LoadData._load_*``) always passes ``self`` or
# ``None``; the runtime contract is "an object with
# ``_detect_format(Path) -> str | None``".


_PICKLE_NOTE: str = "requires allow_pickle=True"


def _load_capability(
    *,
    data_type: type[DataObject],
    type_name: str,
    format_id: str,
    extensions: tuple[str, ...],
    label: str,
    handler: str,
    notes: str | None = None,
) -> FormatCapability:
    """Build a single load-direction :class:`FormatCapability` record.

    The capability id follows the spec FR-015 convention
    ``core.{lower(type)}.{format_id}.load`` and the roundtrip group
    mirrors the matching save capability so the registry can pair
    load+save handlers via :attr:`FormatCapability.roundtrip_group`.

    Core IO records are declared ``is_default=False`` so installed
    package-specific loaders (e.g. the LCMS package's
    ``scistudio-blocks-lcms.table.csv.load`` for ``(DataFrame, .csv)``)
    keep ownership of the default slot for their specialised data types
    without triggering a registration-time conflict. When no package
    declares a default for a given ``(data_type, extension)`` slot, the
    registry returns the unique non-default core capability normally per
    :meth:`BlockRegistry.find_loader_capability`.
    """

    lower_type = type_name.lower()
    return FormatCapability(
        id=f"core.{lower_type}.{format_id}.load",
        direction="load",
        data_type=data_type,
        format_id=format_id,
        extensions=extensions,
        label=label,
        block_type="LoadData",
        handler=handler,
        is_default=False,
        roundtrip_group=f"core.{lower_type}.{format_id}",
        metadata_fidelity=MetadataFidelity(level="pixel_only", notes=notes),
        is_synthesized=False,
    )


_LOAD_CAPABILITIES: tuple[FormatCapability, ...] = (
    # ----- Array -----------------------------------------------------------
    _load_capability(
        data_type=Array,
        type_name="Array",
        format_id="npy",
        extensions=(".npy",),
        label="NumPy NPY",
        handler="load",
    ),
    _load_capability(
        data_type=Array,
        type_name="Array",
        format_id="npz",
        extensions=(".npz",),
        label="NumPy NPZ",
        handler="load",
    ),
    _load_capability(
        data_type=Array,
        type_name="Array",
        format_id="zarr",
        extensions=(".zarr",),
        label="Zarr",
        handler="load",
    ),
    _load_capability(
        data_type=Array,
        type_name="Array",
        format_id="parquet",
        extensions=(".parquet", ".pq"),
        label="Parquet",
        handler="load",
    ),
    _load_capability(
        data_type=Array,
        type_name="Array",
        format_id="pickle",
        extensions=(".pkl", ".pickle"),
        label="Pickle",
        handler="load",
        notes=_PICKLE_NOTE,
    ),
    # ----- DataFrame -------------------------------------------------------
    _load_capability(
        data_type=DataFrame,
        type_name="DataFrame",
        format_id="csv",
        extensions=(".csv",),
        label="CSV",
        handler="load",
    ),
    _load_capability(
        data_type=DataFrame,
        type_name="DataFrame",
        format_id="tsv",
        extensions=(".tsv",),
        label="TSV",
        handler="load",
    ),
    _load_capability(
        data_type=DataFrame,
        type_name="DataFrame",
        format_id="parquet",
        extensions=(".parquet", ".pq"),
        label="Parquet",
        handler="load",
    ),
    _load_capability(
        data_type=DataFrame,
        type_name="DataFrame",
        format_id="json",
        extensions=(".json",),
        label="JSON",
        handler="load",
    ),
    _load_capability(
        data_type=DataFrame,
        type_name="DataFrame",
        format_id="xlsx",
        extensions=(".xlsx",),
        label="Excel",
        handler="load",
    ),
    _load_capability(
        data_type=DataFrame,
        type_name="DataFrame",
        format_id="pickle",
        extensions=(".pkl", ".pickle"),
        label="Pickle",
        handler="load",
        notes=_PICKLE_NOTE,
    ),
    # ----- Series ----------------------------------------------------------
    _load_capability(
        data_type=Series,
        type_name="Series",
        format_id="csv",
        extensions=(".csv",),
        label="CSV",
        handler="load",
    ),
    _load_capability(
        data_type=Series,
        type_name="Series",
        format_id="tsv",
        extensions=(".tsv",),
        label="TSV",
        handler="load",
    ),
    _load_capability(
        data_type=Series,
        type_name="Series",
        format_id="parquet",
        extensions=(".parquet", ".pq"),
        label="Parquet",
        handler="load",
    ),
    _load_capability(
        data_type=Series,
        type_name="Series",
        format_id="xlsx",
        extensions=(".xlsx",),
        label="Excel",
        handler="load",
    ),
    _load_capability(
        data_type=Series,
        type_name="Series",
        format_id="pickle",
        extensions=(".pkl", ".pickle"),
        label="Pickle",
        handler="load",
        notes=_PICKLE_NOTE,
    ),
    # ----- Text ------------------------------------------------------------
    # ``.markdown`` and ``.htm`` are accepted by ``_load_text`` (see
    # :data:`_TEXT_FORMAT_MAP`) and are added here to keep the Load <-> Save
    # capability map symmetric per ADR-043 FR-001 / FR-002 (#1110).
    _load_capability(
        data_type=Text,
        type_name="Text",
        format_id="text",
        extensions=(
            ".txt",
            ".log",
            ".md",
            ".markdown",
            ".html",
            ".htm",
            ".xml",
            ".yaml",
            ".yml",
            ".toml",
        ),
        label="Text",
        handler="load",
    ),
    # ----- Artifact (opaque catch-all loader) -----------------------------
    # ``_load_artifact`` accepts any extension at runtime — it copies bytes
    # to an :class:`Artifact` with MIME-guessed type. The capability
    # records below cover the canonical MIME-mapped extensions
    # (:data:`_MIME_GUESS`) AND every extension the typed core loaders
    # claim, so workflows that declare a wildcard port (AppBlock's
    # ``types=['DataObject']``, which the binner maps to Artifact) can
    # still resolve a loader for the legacy supported-extension union.
    # The runtime catch-all means unknown extensions also load via this
    # path; the records below are the discoverable / registry-visible
    # surface.
    _load_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="binary",
        extensions=(".bin", ".dat"),
        label="Binary",
        handler="load",
    ),
    _load_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="pdf",
        extensions=(".pdf",),
        label="PDF",
        handler="load",
    ),
    _load_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="png",
        extensions=(".png",),
        label="PNG",
        handler="load",
    ),
    _load_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="jpeg",
        extensions=(".jpg", ".jpeg"),
        label="JPEG",
        handler="load",
    ),
    _load_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="tiff",
        extensions=(".tif", ".tiff"),
        label="TIFF",
        handler="load",
    ),
    # Artifact-as-opaque-loader records for the typed-core-loader
    # extensions. These mirror the pre-ADR-043 synthesized
    # ``data_type=DataObject`` capability that the AppBlock wildcard-port
    # binner relied on. The typed loader (DataFrame+csv, Array+npy, …) is
    # preferred when the caller asks for the concrete type because
    # capability matching uses type specificity; the registry only
    # returns the Artifact-typed record when the caller passes
    # ``target_type=Artifact``.
    _load_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="csv",
        extensions=(".csv",),
        label="CSV (opaque)",
        handler="load",
    ),
    _load_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="tsv",
        extensions=(".tsv",),
        label="TSV (opaque)",
        handler="load",
    ),
    _load_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="json",
        extensions=(".json",),
        label="JSON (opaque)",
        handler="load",
    ),
    _load_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="parquet",
        extensions=(".parquet", ".pq"),
        label="Parquet (opaque)",
        handler="load",
    ),
    _load_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="npy",
        extensions=(".npy",),
        label="NumPy NPY (opaque)",
        handler="load",
    ),
    _load_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="npz",
        extensions=(".npz",),
        label="NumPy NPZ (opaque)",
        handler="load",
    ),
    _load_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="zarr",
        extensions=(".zarr",),
        label="Zarr (opaque)",
        handler="load",
    ),
    _load_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="text",
        extensions=(
            ".txt",
            ".log",
            ".md",
            ".markdown",
            ".html",
            ".htm",
            ".xml",
            ".yaml",
            ".yml",
            ".toml",
        ),
        label="Text (opaque)",
        handler="load",
    ),
    _load_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="pickle",
        extensions=(".pkl", ".pickle"),
        label="Pickle (opaque)",
        handler="load",
        notes=_PICKLE_NOTE,
    ),
    # ----- CompositeData ---------------------------------------------------
    _load_capability(
        data_type=CompositeData,
        type_name="CompositeData",
        format_id="json",
        extensions=(".json",),
        label="Composite manifest (JSON)",
        handler="load",
    ),
)


def _legacy_extension_map(
    capabilities: tuple[FormatCapability, ...],
) -> dict[str, str]:
    """Derive a legacy ``extension -> format_id`` mapping from capabilities.

    The pre-ADR-043 ``LoadData.supported_extensions`` ClassVar was a flat
    ``dict[str, str]`` used by :func:`_resolve_format` / :meth:`IOBlock._detect_format`
    for compound-suffix-first dispatch. The post-ADR-043 mapping is
    derived from the explicit ``format_capabilities`` so format dispatch
    keeps working at runtime without holding a duplicate ClassVar.

    Cross-type collisions (e.g. ``.parquet`` is declared on Array,
    DataFrame, and Series) are stable because every type that handles a
    given extension uses the same ``format_id`` (e.g. ``"parquet"`` for
    all three). The first capability to win the iteration is the
    authoritative mapping for that extension; any subsequent capability
    with the same extension+format_id is a no-op overwrite. Collisions
    with different ``format_id`` values would raise a
    :class:`RuntimeError` to surface the misconfiguration loudly rather
    than silently picking one.
    """

    mapping: dict[str, str] = {}
    for capability in capabilities:
        for extension in capability.extensions:
            normalized = extension.lower()
            existing = mapping.get(normalized)
            if existing is not None and existing != capability.format_id:
                raise RuntimeError(
                    f"LoadData format_capabilities declare conflicting format_id "
                    f"for extension {normalized!r}: {existing!r} vs {capability.format_id!r}"
                )
            mapping[normalized] = capability.format_id
    return mapping


_LOAD_EXTENSION_MAP: dict[str, str] = _legacy_extension_map(_LOAD_CAPABILITIES)


def _supported_load_extensions() -> tuple[str, ...]:
    """Return the sorted tuple of every extension declared by LoadData.

    Replaces the legacy ``sorted(LoadData.supported_extensions.keys())``
    call sites in user-facing error messages.
    """

    return tuple(sorted(_LOAD_EXTENSION_MAP.keys()))


def _resolve_format(path: Path, block: Any | None) -> str | None:
    """Resolve a path's format identifier from the LoadData capability map.

    Walks ``Path.suffixes`` longest-first to support compound suffixes,
    mirroring :meth:`IOBlock._detect_format`. The lookup is
    case-insensitive. If ``block`` is provided, the underlying
    :meth:`IOBlock._detect_format` path is honoured (it reads
    ``self.supported_extensions``, which on ``LoadData`` is now the
    capability-derived module-level mapping exposed as
    :attr:`LoadData.supported_extensions`).

    ADR-043 / spec FR-003: format dispatch is now derived from explicit
    ``format_capabilities`` rather than the deleted
    ``supported_extensions`` ClassVar.
    """

    if block is not None:
        # ``block`` is ``LoadData`` at the call site; type as ``Any`` so this
        # module doesn't import ``load_data`` (sentrux would flag the edge,
        # see issue #1482) and ADR-028 Add 1 §C9 forbids a Protocol here.
        # ``cast`` keeps mypy honest about the return contract.
        return cast("str | None", block._detect_format(path))
    if not _LOAD_EXTENSION_MAP:
        return None
    suffixes = [s.lower() for s in path.suffixes]
    for start in range(len(suffixes)):
        candidate = "".join(suffixes[start:])
        if candidate in _LOAD_EXTENSION_MAP:
            return _LOAD_EXTENSION_MAP[candidate]
    return None


__all__ = [
    "_LOAD_CAPABILITIES",
    "_LOAD_EXTENSION_MAP",
    "_PICKLE_NOTE",
    "_legacy_extension_map",
    "_load_capability",
    "_resolve_format",
    "_supported_load_extensions",
]
