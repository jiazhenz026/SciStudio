"""Private helpers shared by ``LoadData`` and its dispatch functions.

This module is **package-private** per ADR-028 Addendum 1 §C9
("private functions, not helper classes"): every public symbol is
prefixed with an underscore and the module name itself starts with an
underscore. External callers must import :class:`LoadData` from
:mod:`scistudio.blocks.io.loaders`; importing helpers directly is
unsupported and the names may change without notice.

The functions here were extracted from
:mod:`scistudio.blocks.io.loaders.load_data` in issue #1459 (Phase 2 of
the backend god-file refactor umbrella #1427). They keep the
``_load_*`` dispatch functions and the :class:`LoadData` class in the
sibling ``load_data`` module short enough to fit under the 750-LOC
god-file threshold while preserving the exact behavior of every public
entry point.

Symmetric to :mod:`scistudio.blocks.io.savers._helpers` on the save
side.
"""

from __future__ import annotations

import logging
from pathlib import Path

from scistudio.blocks.base.config import BlockConfig
from scistudio.core.types.array import Array
from scistudio.core.types.artifact import Artifact
from scistudio.core.types.base import DataObject
from scistudio.core.types.composite import CompositeData
from scistudio.core.types.dataframe import DataFrame
from scistudio.core.types.series import Series
from scistudio.core.types.text import Text

# Tag the logger with the public module path so log records remain
# attributable to ``LoadData`` regardless of which sub-module emits them.
_LOGGER = logging.getLogger("scistudio.blocks.io.loaders.load_data")


# ADR-028 Addendum 1 §C5: hardcoded six core types. Used by
# :meth:`LoadData.get_effective_output_ports` to update the
# accepted-types of the ``data`` output port and by
# :meth:`LoadData.load` to dispatch to the matching ``_load_*`` function.
_CORE_TYPE_MAP: dict[str, type[DataObject]] = {
    "Array": Array,
    "DataFrame": DataFrame,
    "Series": Series,
    "Text": Text,
    "Artifact": Artifact,
    "CompositeData": CompositeData,
}


# Per-extension ``Text.format`` lookup used by :func:`_load_text` to
# stamp the constructed :class:`Text` instance with a stable format id.
_TEXT_FORMAT_MAP: dict[str, str] = {
    ".txt": "plain",
    ".log": "plain",
    ".md": "markdown",
    ".markdown": "markdown",
    ".html": "html",
    ".htm": "html",
    ".xml": "xml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
}


# MIME-type lookup used by :func:`_load_artifact` for canonical
# extensions. Anything not in this table falls through to
# ``application/octet-stream``.
_MIME_GUESS: dict[str, str] = {
    ".csv": "text/csv",
    ".json": "application/json",
    ".txt": "text/plain",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".pdf": "application/pdf",
    ".bin": "application/octet-stream",
    ".dat": "application/octet-stream",
}


def _resolve_path(config: BlockConfig) -> Path:
    """Pull the validated ``path`` field off ``config`` as a :class:`Path`.

    Raises ``ValueError`` if no path was supplied; the JSON schema also
    enforces this on the API side, but we double-check at runtime so the
    failure mode is identical regardless of the call site.
    """
    raw = config.get("path")
    if raw is None:
        raise ValueError("LoadData requires a 'path' config field")
    return Path(str(raw))


def _check_pickle_allowed(path: Path, config: BlockConfig) -> bool:
    """Return ``True`` if the path is a pickle file and pickle is allowed.

    Returns ``False`` for non-pickle paths (so the caller can fall through
    to its default branch). Raises ``ValueError`` when the path IS a
    pickle file but ``allow_pickle`` is not set, with an explicit security
    message. Logs a WARNING when ``allow_pickle=True`` is honoured.
    """
    suffix = path.suffix.lower()
    if suffix not in {".pkl", ".pickle"}:
        return False
    if not bool(config.get("allow_pickle", False)):
        raise ValueError(
            f"Refusing to load pickle file {path.name!r}: pickle deserialisation "
            f"can execute arbitrary code. Set allow_pickle=True on the LoadData "
            f"config if you trust the source."
        )
    _LOGGER.warning(
        "LoadData: loading pickle file %s with allow_pickle=True. "
        "Pickle files can execute arbitrary code; only load files from trusted sources.",
        path,
    )
    return True


__all__ = [
    "_CORE_TYPE_MAP",
    "_LOGGER",
    "_MIME_GUESS",
    "_TEXT_FORMAT_MAP",
    "_check_pickle_allowed",
    "_resolve_path",
]
