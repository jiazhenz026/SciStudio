"""Save-direction :class:`FormatCapability` declarations for ``SaveData``.

Per ADR-028 Addendum 1 §C9 ("private functions, not helper classes")
this module is package-private: every public symbol is prefixed with an
underscore and the module name itself starts with an underscore.

ADR-043 / spec ``adr-043-package-migration`` FR-002 / FR-003 require
:class:`SaveData` to expose explicit :class:`FormatCapability` records via
its ``format_capabilities`` ClassVar so the block registry can discover
the saver from a target ``data_type`` + extension query. This module
holds the capability tuple, the legacy ``extension -> format_id`` lookup
derived from it, and the format-resolution helper used by
:meth:`SaveData._detect_format`.

Extracted from :mod:`scistudio.blocks.io.savers.save_data` in issue #1459
(Phase 2 of the backend god-file refactor umbrella #1427). Symmetric to
:mod:`scistudio.blocks.io.loaders._capability` on the load side.
"""

from __future__ import annotations

from pathlib import Path

from scistudio.blocks.io.capabilities import FormatCapability, MetadataFidelity
from scistudio.core.types.array import Array
from scistudio.core.types.artifact import Artifact
from scistudio.core.types.base import DataObject
from scistudio.core.types.composite import CompositeData
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.series import Series
from scistudio.core.types.text import Text

_PICKLE_NOTE: str = "requires allow_pickle=True"


def _save_capability(
    *,
    data_type: type[DataObject],
    type_name: str,
    format_id: str,
    extensions: tuple[str, ...],
    label: str,
    handler: str,
    notes: str | None = None,
) -> FormatCapability:
    """Build a single save-direction :class:`FormatCapability` record.

    The capability id follows the spec FR-015 convention
    ``core.{lower(type)}.{format_id}.save`` and the roundtrip group
    mirrors the matching load capability so the registry can pair
    load+save handlers via :attr:`FormatCapability.roundtrip_group`.

    Core IO records are declared ``is_default=False`` so installed
    package-specific savers (e.g. the LCMS package's
    ``scistudio-blocks-lcms.table.csv.save`` for ``(DataFrame, .csv)``)
    keep ownership of the default slot for their specialised data types
    without triggering a registration-time conflict. When no package
    declares a default for a given ``(data_type, extension)`` slot, the
    registry returns the unique non-default core capability normally per
    :meth:`BlockRegistry.find_saver_capability`.
    """

    lower_type = type_name.lower()
    return FormatCapability(
        id=f"core.{lower_type}.{format_id}.save",
        direction="save",
        data_type=data_type,
        format_id=format_id,
        extensions=extensions,
        label=label,
        block_type="SaveData",
        handler=handler,
        is_default=False,
        roundtrip_group=f"core.{lower_type}.{format_id}",
        metadata_fidelity=MetadataFidelity(level="pixel_only", notes=notes),
        is_synthesized=False,
    )


_SAVE_CAPABILITIES: tuple[FormatCapability, ...] = (
    # ----- Array -----------------------------------------------------------
    _save_capability(
        data_type=Array,
        type_name="Array",
        format_id="npy",
        extensions=(".npy",),
        label="NumPy NPY",
        handler="save",
    ),
    _save_capability(
        data_type=Array,
        type_name="Array",
        format_id="npz",
        extensions=(".npz",),
        label="NumPy NPZ",
        handler="save",
    ),
    _save_capability(
        data_type=Array,
        type_name="Array",
        format_id="zarr",
        extensions=(".zarr",),
        label="Zarr",
        handler="save",
    ),
    _save_capability(
        data_type=Array,
        type_name="Array",
        format_id="parquet",
        extensions=(".parquet", ".pq"),
        label="Parquet",
        handler="save",
    ),
    _save_capability(
        data_type=Array,
        type_name="Array",
        format_id="pickle",
        extensions=(".pkl", ".pickle"),
        label="Pickle",
        handler="save",
        notes=_PICKLE_NOTE,
    ),
    # ----- DataFrame -------------------------------------------------------
    _save_capability(
        data_type=DataFrame,
        type_name="DataFrame",
        format_id="csv",
        extensions=(".csv",),
        label="CSV",
        handler="save",
    ),
    _save_capability(
        data_type=DataFrame,
        type_name="DataFrame",
        format_id="tsv",
        extensions=(".tsv",),
        label="TSV",
        handler="save",
    ),
    _save_capability(
        data_type=DataFrame,
        type_name="DataFrame",
        format_id="parquet",
        extensions=(".parquet", ".pq"),
        label="Parquet",
        handler="save",
    ),
    _save_capability(
        data_type=DataFrame,
        type_name="DataFrame",
        format_id="json",
        extensions=(".json",),
        label="JSON",
        handler="save",
    ),
    _save_capability(
        data_type=DataFrame,
        type_name="DataFrame",
        format_id="pickle",
        extensions=(".pkl", ".pickle"),
        label="Pickle",
        handler="save",
        notes=_PICKLE_NOTE,
    ),
    # ----- Series ----------------------------------------------------------
    _save_capability(
        data_type=Series,
        type_name="Series",
        format_id="csv",
        extensions=(".csv",),
        label="CSV",
        handler="save",
    ),
    _save_capability(
        data_type=Series,
        type_name="Series",
        format_id="tsv",
        extensions=(".tsv",),
        label="TSV",
        handler="save",
    ),
    _save_capability(
        data_type=Series,
        type_name="Series",
        format_id="parquet",
        extensions=(".parquet", ".pq"),
        label="Parquet",
        handler="save",
    ),
    _save_capability(
        data_type=Series,
        type_name="Series",
        format_id="json",
        extensions=(".json",),
        label="JSON",
        handler="save",
    ),
    _save_capability(
        data_type=Series,
        type_name="Series",
        format_id="pickle",
        extensions=(".pkl", ".pickle"),
        label="Pickle",
        handler="save",
        notes=_PICKLE_NOTE,
    ),
    # ----- Text ------------------------------------------------------------
    # ``.markdown`` and ``.htm`` are accepted by ``_save_text`` (see the
    # Text-specific superset in that function) but were missing from the
    # registry-visible capability declaration, so ``find_saver_capability``
    # could not discover SaveData for those extensions (#1110).
    _save_capability(
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
        handler="save",
    ),
    # Text + .json is a legacy save-only extension: ``_save_text`` writes
    # JSON files happily (just dumps ``obj.content``) but LoadData's Text
    # capability intentionally excludes ``.json`` because ``_load_text``
    # does not parse JSON. Declared as a separate capability record with
    # ``format_id="json"`` so ``find_saver_capability(Text, '.json')``
    # resolves to a Text saver without conflicting with the Text +
    # ``.json`` -> ``"text"`` mapping at the extension-map layer. Mirrors
    # the Series + json save-only legacy branch and the P1 Codex-review
    # finding on PR #1300.
    _save_capability(
        data_type=Text,
        type_name="Text",
        format_id="json",
        extensions=(".json",),
        label="Text as JSON",
        handler="save",
    ),
    # ----- Artifact (opaque catch-all saver) ------------------------------
    # ``_save_artifact`` accepts any extension at runtime — it copies bytes
    # to the configured path. The capability records below cover the
    # canonical MIME-mapped extensions AND every extension the typed core
    # savers claim, so the AppBlock wildcard-port flow (which the binner
    # maps to Artifact) can resolve a saver for the legacy
    # supported-extension union without falling through to the
    # registry's polymorphic fallback. Mirror of the corresponding
    # ``Artifact``-as-opaque-loader records on the ``LoadData`` side.
    _save_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="binary",
        extensions=(".bin", ".dat"),
        label="Binary",
        handler="save",
    ),
    _save_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="pdf",
        extensions=(".pdf",),
        label="PDF",
        handler="save",
    ),
    _save_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="png",
        extensions=(".png",),
        label="PNG",
        handler="save",
    ),
    _save_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="jpeg",
        extensions=(".jpg", ".jpeg"),
        label="JPEG",
        handler="save",
    ),
    _save_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="tiff",
        extensions=(".tif", ".tiff"),
        label="TIFF",
        handler="save",
    ),
    _save_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="csv",
        extensions=(".csv",),
        label="CSV (opaque)",
        handler="save",
    ),
    _save_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="tsv",
        extensions=(".tsv",),
        label="TSV (opaque)",
        handler="save",
    ),
    _save_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="json",
        extensions=(".json",),
        label="JSON (opaque)",
        handler="save",
    ),
    _save_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="parquet",
        extensions=(".parquet", ".pq"),
        label="Parquet (opaque)",
        handler="save",
    ),
    _save_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="npy",
        extensions=(".npy",),
        label="NumPy NPY (opaque)",
        handler="save",
    ),
    _save_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="npz",
        extensions=(".npz",),
        label="NumPy NPZ (opaque)",
        handler="save",
    ),
    _save_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="zarr",
        extensions=(".zarr",),
        label="Zarr (opaque)",
        handler="save",
    ),
    _save_capability(
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
        handler="save",
    ),
    _save_capability(
        data_type=Artifact,
        type_name="Artifact",
        format_id="pickle",
        extensions=(".pkl", ".pickle"),
        label="Pickle (opaque)",
        handler="save",
        notes=_PICKLE_NOTE,
    ),
    # ----- CompositeData ---------------------------------------------------
    _save_capability(
        data_type=CompositeData,
        type_name="CompositeData",
        format_id="json",
        extensions=(".json",),
        label="Composite manifest (JSON)",
        handler="save",
    ),
)


def _legacy_save_extension_map(
    capabilities: tuple[FormatCapability, ...],
) -> dict[str, str]:
    """Derive a legacy ``extension -> format_id`` mapping from capabilities.

    Mirror of :func:`scistudio.blocks.io.loaders._capability._legacy_extension_map`.
    The same extension may appear on multiple types (e.g. ``.parquet`` on
    Array, DataFrame, Series) but the ``format_id`` is identical across
    types, so the dict is well-defined. Conflicting format_id values
    raise :class:`RuntimeError` to surface misconfiguration.
    """

    mapping: dict[str, str] = {}
    for capability in capabilities:
        for extension in capability.extensions:
            normalized = extension.lower()
            existing = mapping.get(normalized)
            if existing is not None and existing != capability.format_id:
                raise RuntimeError(
                    f"SaveData format_capabilities declare conflicting format_id "
                    f"for extension {normalized!r}: {existing!r} vs {capability.format_id!r}"
                )
            mapping[normalized] = capability.format_id
    return mapping


_SAVE_EXTENSION_MAP: dict[str, str] = _legacy_save_extension_map(_SAVE_CAPABILITIES)


def _supported_save_extensions() -> tuple[str, ...]:
    """Return the sorted tuple of every extension declared by SaveData.

    Replaces the legacy ``sorted(SaveData.supported_extensions.keys())``
    call sites in user-facing error messages.
    """

    return tuple(sorted(_SAVE_EXTENSION_MAP.keys()))


def _resolve_save_format(path: Path) -> str | None:
    """Resolve a path's format identifier from the SaveData capability map.

    ADR-043 / spec FR-003: format dispatch is now derived from explicit
    :attr:`SaveData.format_capabilities` rather than the deleted
    ``supported_extensions`` ClassVar. Compound-suffix-first,
    case-insensitive lookup matching :meth:`IOBlock._detect_format`
    semantics.
    """

    if not _SAVE_EXTENSION_MAP:
        return None
    suffixes = [s.lower() for s in path.suffixes]
    for start in range(len(suffixes)):
        candidate = "".join(suffixes[start:])
        if candidate in _SAVE_EXTENSION_MAP:
            return _SAVE_EXTENSION_MAP[candidate]
    return None


__all__ = [
    "_PICKLE_NOTE",
    "_SAVE_CAPABILITIES",
    "_SAVE_EXTENSION_MAP",
    "_legacy_save_extension_map",
    "_resolve_save_format",
    "_save_capability",
    "_supported_save_extensions",
]
