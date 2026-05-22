"""Private helpers shared by ``SaveData`` and its dispatch functions.

This module is **package-private** per ADR-028 Addendum 1 §C9
("private functions, not helper classes"): every public symbol is
prefixed with an underscore and the module name itself starts with an
underscore. External callers must import :class:`SaveData` from
:mod:`scistudio.blocks.io.savers`; importing helpers directly is
unsupported and the names may change without notice.

The functions here were extracted from
:mod:`scistudio.blocks.io.savers.save_data` in issue #1459 (Phase 2
of the backend god-file refactor umbrella #1427). They keep the
``_save_*`` dispatch functions and the :class:`SaveData` class in the
sibling ``save_data`` module short enough to fit under the 750-LOC
god-file threshold while preserving the exact behavior of every
public entry point.

Symmetric to :mod:`scistudio.blocks.io.loaders._helpers` on the load
side.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.array import Array
from scistudio.core.types.artifact import Artifact
from scistudio.core.types.base import DataObject
from scistudio.core.types.collection import Collection
from scistudio.core.types.composite import CompositeData
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.series import Series
from scistudio.core.types.text import Text

# Tag the logger with the public module path so log records remain
# attributable to ``SaveData`` regardless of which sub-module emits them.
logger = logging.getLogger("scistudio.blocks.io.savers.save_data")


# ADR-028 Addendum 1 §C5: hardcoded six core types. The keys are the
# string enum values exposed in ``config_schema['properties']['core_type']
# ['enum']``; the values are the concrete :class:`DataObject` subclasses
# used by :meth:`SaveData.get_effective_input_ports` to update the
# accepted-types of the ``data`` input port.
_CORE_TYPE_MAP: dict[str, type[DataObject]] = {
    "Array": Array,
    "DataFrame": DataFrame,
    "Series": Series,
    "Text": Text,
    "Artifact": Artifact,
    "CompositeData": CompositeData,
}


# Pickle file extensions that require explicit ``allow_pickle=True``
# opt-in. Treated case-insensitively.
_PICKLE_EXTENSIONS: frozenset[str] = frozenset({".pkl", ".pickle"})


def _require_path(config: BlockConfig) -> Path:
    """Return the configured ``path`` as a :class:`Path` or raise.

    Centralised so each ``_save_*`` function can fail loudly with the
    same message instead of duplicating the validation.
    """
    raw = config.get("path")
    if raw is None or raw == "":
        raise ValueError("SaveData requires a non-empty 'path' in config.params.")
    path = Path(str(raw))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _check_pickle_gate(path: Path, config: BlockConfig) -> bool:
    """Return ``True`` if *path* is a pickle file.

    Raises :class:`ValueError` if the file extension is ``.pkl`` /
    ``.pickle`` and ``allow_pickle`` is not explicitly ``True``. When
    pickle is enabled, an explicit security warning is logged at
    ``WARNING`` level so the user can audit the workflow run.
    """
    if path.suffix.lower() not in _PICKLE_EXTENSIONS:
        return False
    if not bool(config.get("allow_pickle", False)):
        raise ValueError(
            f"Refusing to write pickle file {path.name!r}: pickle is opt-in for "
            "security reasons. Set 'allow_pickle': True in the block config to "
            "enable pickle writes."
        )
    logger.warning(
        "SaveData: writing pickle file %r — pickle files can execute arbitrary "
        "code on load and should only be used with trusted data.",
        str(path),
    )
    return True


def _unwrap_for_save(
    obj: DataObject | Collection,
    target_cls: type[DataObject],
) -> DataObject:
    """Unwrap a single-item :class:`Collection` or return the bare object.

    Per spec §j, mixed-type Collections (where some item is not a
    ``target_cls`` instance) raise :class:`ValueError`. A Collection
    of all-``target_cls`` items with exactly one element is unwrapped
    transparently. A Collection of length > 1 also raises because the
    save dispatch functions write a single file at the configured path.
    """
    if isinstance(obj, Collection):
        items = list(obj)
        if not items:
            raise ValueError("SaveData received an empty Collection; nothing to save.")
        if len(items) > 1:
            raise ValueError(
                f"SaveData received a Collection of {len(items)} items; "
                "core SaveData writes one file at the configured path. "
                "Iterate over the Collection upstream and call SaveData per item."
            )
        only = items[0]
        if not isinstance(only, target_cls):
            raise ValueError(
                f"SaveData(core_type={target_cls.__name__}) received a "
                f"Collection item of type {type(only).__name__}; mixed-type "
                "Collections are out-of-scope per ADR-028 Addendum 1 §C9."
            )
        return only
    if not isinstance(obj, target_cls):
        raise ValueError(
            f"SaveData(core_type={target_cls.__name__}) received an instance of "
            f"{type(obj).__name__}; the input must be a {target_cls.__name__} "
            "instance (or a single-item Collection thereof)."
        )
    return obj


def _resolve_core_type_name(obj: DataObject) -> str | None:
    """Map a :class:`DataObject` instance to its core-type enum name.

    Returns ``None`` if *obj* is not an instance of any of the six
    supported core types. Order matters here: more specific types
    (``Array``, ``CompositeData``) come before the base ``DataObject``
    fallback.
    """
    for type_name, cls in _CORE_TYPE_MAP.items():
        if isinstance(obj, cls):
            return type_name
    return None


def _slot_path_for(
    type_name: str,
    slots_dir: Path,
    slot_name: str,
) -> tuple[str, Path]:
    """Return ``(filename, full_path)`` for a CompositeData slot file.

    The default extension per type mirrors the most common round-trip
    format used by tests: ``.csv`` for DataFrame / Series, ``.npy``
    for Array, ``.txt`` for Text, ``.bin`` for Artifact, ``.json`` for
    nested CompositeData.
    """
    default_ext = {
        "Array": ".npy",
        "DataFrame": ".csv",
        "Series": ".csv",
        "Text": ".txt",
        "Artifact": ".bin",
        "CompositeData": ".json",
    }[type_name]
    filename = f"{slot_name}{default_ext}"
    return filename, slots_dir / filename


def _dataframe_to_arrow_table(obj: DataFrame) -> Any:
    """Coerce a :class:`DataFrame` into a :class:`pyarrow.Table`.

    ADR-031 D6: always routes through ``get_in_memory_data()`` ->
    ``to_memory()`` -> storage backend read. The former ``_arrow_table``
    backdoor is removed.
    """
    import pyarrow as pa

    raw = obj.get_in_memory_data()
    if isinstance(raw, pa.Table):
        return raw
    if isinstance(raw, dict):
        return pa.table(raw)
    if isinstance(raw, list):
        return pa.Table.from_pylist(raw)
    raise ValueError(
        f"Cannot convert DataFrame in-memory data of type {type(raw).__name__} "
        "to a pyarrow.Table; expected pa.Table, dict, or list of records."
    )


__all__ = [
    "_CORE_TYPE_MAP",
    "_PICKLE_EXTENSIONS",
    "_check_pickle_gate",
    "_dataframe_to_arrow_table",
    "_require_path",
    "_resolve_core_type_name",
    "_slot_path_for",
    "_unwrap_for_save",
]
