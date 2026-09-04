"""The Explore Session's notebook store — the ``.ipynb`` on disk.

A session *is* a notebook file (``docs/specs/adr-054-explore-session.md``
FR-001). Everything else in the subsystem — the kernel, the queue, the marks,
the dependency analysis, packaging — reads that file and writes back to it,
which makes this module's only real job **losing nothing**.

Three things live in a session notebook that an incautious reader/writer
destroys:

* **Cell outputs.** The notebook on disk keeps them (FR-027) so a kernel death
  loses nothing the person typed or saw.
* **The dependency analysis' per-cell record**, stored under the
  :data:`ANALYSIS_METADATA_KEY` key of a cell's metadata
  (``docs/specs/adr-054-notebook-dependency-analysis.md`` FR-031). Every write
  of the notebook must preserve it (FR-032).
* **Everything this module has never heard of.** A notebook that has been
  through JupyterLab, nbstripout, a git merge, or another SciStudio version
  carries keys — at the notebook level, on cells, in cell metadata, inside
  outputs — that this store does not model. FR-033 of the analysis spec makes
  that explicit for the ``scistudio`` namespace, and the same rule holds for
  the rest of the document.

The store therefore keeps the **parsed JSON document itself** as the source of
truth rather than projecting it onto a typed model and projecting it back.
:class:`NotebookDocument` is a thin, typed *view* over that mapping;
:class:`NotebookCell` is a view over one cell's mapping. Reads are typed;
writes go through a small set of named mutators so there is exactly one place
that touches the file's shape. A key nothing asked about is carried through
untouched, because nothing ever copies it out and back.

Serialisation matches what Jupyter writes — ``indent=1``, no ASCII escaping, a
trailing newline, UTF-8 bytes with ``\\n`` line endings on every platform — so
a notebook read and written unchanged is byte-identical and a git diff of a
session shows only what the session did.

No notebook library is a dependency here. ``nbformat`` would pull in
``jsonschema`` and would normalise the document on load, which is precisely the
behaviour this module exists to avoid; the standard library's ``json`` handles
the format (analysis spec FR-034).

**Output stripping** (FR-032, FR-028) produces a *separate* document with
outputs and execution counts cleared, leaving the on-disk file alone, for the
commit written to the session's ref off the execution path.

**External-change reload** (FR-005): a :class:`NotebookStore` remembers a
digest of the exact bytes it last read or wrote, so a write it performed is
never mistaken for somebody else's edit (assumption A-012), and an edit made
in JupyterLab, by a git checkout, or by hand is detected and reloaded.

Example:
    >>> store = NotebookStore(project / "explore" / "session.ipynb")
    >>> document = store.read()
    >>> document.set_cell_enabled(document.cells[0].cell_id, enabled=False)
    >>> store.write(document)
    >>> store.has_external_change()  # our own write is not an external edit
    False
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import uuid
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import Any

from scistudio.stability import provisional
from scistudio.utils.atomic_io import atomic_write_bytes

__all__ = [
    "ANALYSIS_METADATA_KEY",
    "ENABLED_METADATA_KEY",
    "NBFORMAT_MAJOR",
    "NBFORMAT_MINOR",
    "NotebookCell",
    "NotebookDocument",
    "NotebookStore",
    "NotebookStoreError",
    "new_code_cell",
    "new_markdown_cell",
    "new_notebook",
    "read_notebook",
    "strip_outputs",
    "write_notebook",
]

#: Cell- and notebook-metadata key SciStudio namespaces everything under.
#:
#: The dependency analysis stores its per-cell record here (analysis spec
#: FR-031) and preserves keys it does not recognise (FR-033), which is what
#: lets the notebook store keep the enabled flag alongside it. Namespacing
#: keeps SciStudio out of the way of Jupyter's own cell metadata and of any
#: other tool that touches the same file.
ANALYSIS_METADATA_KEY = "scistudio"

#: Key of the enabled flag inside :data:`ANALYSIS_METADATA_KEY`.
#:
#: The flag is owned by the notebook and written only here; the dependency
#: analysis reads it and never writes it (analysis spec FR-014, A-005). A cell
#: with no flag is enabled — a notebook authored anywhere else runs whole.
ENABLED_METADATA_KEY = "enabled"

#: nbformat version :func:`new_notebook` writes. 4.5 is the version that gave
#: cells a stable ``id``, which the session's marks and the analysis' records
#: are both keyed by.
NBFORMAT_MAJOR = 4
NBFORMAT_MINOR = 5

#: Length of a generated cell id. Matches what JupyterLab writes; the nbformat
#: 4.5 schema allows 1 to 64 characters of ``[a-zA-Z0-9-_]``.
_CELL_ID_LENGTH = 8

#: The one cell type that carries ``outputs`` and ``execution_count``, used
#: when generating a cell. Stripping does not read this: it clears the two keys
#: only where they already exist, so a markdown or raw cell never grows them
#: and a cell type this module has never heard of is handled by the file rather
#: than by a list here.
_EXECUTABLE_CELL_TYPE = "code"


@provisional(since="0.3.4")
class NotebookStoreError(ValueError):
    """A file is not a notebook this store can read.

    Raised for content that is not JSON, that is not a JSON object, or that
    has no ``cells`` array of objects. A *missing* file is not this error:
    :meth:`NotebookStore.read` lets :class:`FileNotFoundError` through, so a
    caller can tell "no session here" from "this session's file is damaged".
    """


def _digest(payload: bytes) -> str:
    """Return the content digest used to recognise the store's own writes."""
    return hashlib.blake2b(payload, digest_size=16).hexdigest()


def _new_cell_id() -> str:
    return uuid.uuid4().hex[:_CELL_ID_LENGTH]


def _join_source(source: object) -> str:
    """Return a cell's ``source`` as text, whatever form the file used."""
    if isinstance(source, str):
        return source
    if isinstance(source, list):
        return "".join(line for line in source if isinstance(line, str))
    return ""


def _split_source(text: str) -> list[str]:
    """Split *text* into the line list Jupyter writes for ``source``.

    ``splitlines(keepends=True)`` is what ``nbformat`` uses, so a notebook
    written here and one written by Jupyter agree line for line. Joining the
    result reproduces *text* exactly, so the split is lossless whatever the
    text contains.
    """
    return text.splitlines(keepends=True)


def _store_source(text: str, previous: object) -> str | list[str]:
    """Encode *text* in the same form *previous* used.

    A file that stored one cell's source as a plain string keeps storing it as
    a plain string, so editing a cell does not rewrite the shape of a document
    somebody else's tool produced.
    """
    if isinstance(previous, str):
        return text
    return _split_source(text)


@provisional(since="0.3.4")
class NotebookCell:
    """One cell of a notebook, as a typed view over its JSON mapping.

    A cell is *not* copied out of the document. The accessors here read the
    live mapping, and the read-only views they hand back
    (:attr:`metadata`, :attr:`outputs`, :attr:`raw`) exist so that a caller
    cannot rebind a key behind the store's back — every write goes through
    :class:`NotebookDocument`. Nothing here drops a key: a field this class
    does not model is still in the mapping and still gets written.

    Args:
        raw: The cell's mapping, as parsed from the ``.ipynb``. Held by
            reference, not copied.
    """

    __slots__ = ("_raw",)

    def __init__(self, raw: dict[str, Any]) -> None:
        self._raw = raw

    @property
    def raw(self) -> Mapping[str, Any]:
        """Read-only view of the cell's whole mapping, unrecognised keys included."""
        return MappingProxyType(self._raw)

    @property
    def cell_id(self) -> str | None:
        """The cell's ``id``, or ``None`` for a notebook older than nbformat 4.5.

        Marks and analysis records are keyed by this, which is why FR-005
        keeps marks "by cell id where the id survives" — a notebook without
        ids has nothing to key them by.
        """
        value = self._raw.get("id")
        return value if isinstance(value, str) else None

    @property
    def cell_type(self) -> str:
        """``"code"``, ``"markdown"``, ``"raw"``, or whatever the file said."""
        value = self._raw.get("cell_type")
        return value if isinstance(value, str) else ""

    @property
    def source(self) -> str:
        """The cell's source as one string, joined from the file's line list."""
        return _join_source(self._raw.get("source"))

    @property
    def metadata(self) -> Mapping[str, Any]:
        """Read-only view of the cell's metadata, unrecognised keys included."""
        metadata = self._raw.get("metadata")
        return MappingProxyType(metadata if isinstance(metadata, dict) else {})

    @property
    def scistudio_metadata(self) -> Mapping[str, Any]:
        """Read-only view of the cell's ``scistudio`` metadata namespace.

        Empty when the cell has never been analysed and has never had its
        enabled flag toggled.
        """
        namespace = self.metadata.get(ANALYSIS_METADATA_KEY)
        return MappingProxyType(namespace if isinstance(namespace, dict) else {})

    @property
    def enabled(self) -> bool:
        """Whether the dependency analysis builds the graph over this cell.

        A cell with no recorded flag is enabled (analysis spec FR-014).
        """
        value = self.scistudio_metadata.get(ENABLED_METADATA_KEY, True)
        return bool(value)

    @property
    def outputs(self) -> Sequence[Mapping[str, Any]]:
        """Read-only views of the cell's outputs; empty for a non-code cell."""
        outputs = self._raw.get("outputs")
        if not isinstance(outputs, list):
            return ()
        return tuple(MappingProxyType(item) for item in outputs if isinstance(item, dict))

    @property
    def execution_count(self) -> int | None:
        """The cell's execution count, or ``None`` when it has not run."""
        value = self._raw.get("execution_count")
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, NotebookCell):
            return NotImplemented
        return self._raw == other._raw

    # Python sets ``__hash__`` to None for a class that defines ``__eq__``; a
    # document is mutable, so it is deliberately unhashable.

    def __repr__(self) -> str:
        return f"NotebookCell(id={self.cell_id!r}, cell_type={self.cell_type!r})"


@provisional(since="0.3.4")
def new_code_cell(source: str = "", *, cell_id: str | None = None) -> dict[str, Any]:
    """Build a code cell mapping in the shape nbformat 4.5 writes.

    Args:
        source: The cell's source text.
        cell_id: Cell id to use; a fresh random one when omitted.

    Returns:
        A plain mapping ready for :func:`new_notebook` or
        :meth:`NotebookDocument.append_cell`. Keys are in the order Jupyter
        writes them, so a notebook built here diffs cleanly against one
        JupyterLab saved.
    """
    return {
        "cell_type": _EXECUTABLE_CELL_TYPE,
        "execution_count": None,
        "id": cell_id or _new_cell_id(),
        "metadata": {},
        "outputs": [],
        "source": _split_source(source),
    }


@provisional(since="0.3.4")
def new_markdown_cell(source: str = "", *, cell_id: str | None = None) -> dict[str, Any]:
    """Build a markdown cell mapping in the shape nbformat 4.5 writes.

    Args:
        source: The cell's markdown text.
        cell_id: Cell id to use; a fresh random one when omitted.

    Returns:
        A plain mapping ready for :func:`new_notebook` or
        :meth:`NotebookDocument.append_cell`.
    """
    return {
        "cell_type": "markdown",
        "id": cell_id or _new_cell_id(),
        "metadata": {},
        "source": _split_source(source),
    }


@provisional(since="0.3.4")
def new_notebook(
    cells: Iterable[Mapping[str, Any]] = (),
    *,
    metadata: Mapping[str, Any] | None = None,
) -> NotebookDocument:
    """Build an empty nbformat 4.5 notebook holding *cells*.

    Used when a session is created and its first cell is generated (FR-004).

    Args:
        cells: Cell mappings, e.g. from :func:`new_code_cell`. Deep-copied, so
            the caller keeps no handle into the document.
        metadata: Notebook-level metadata. Deep-copied.

    Returns:
        A :class:`NotebookDocument` that has never been written anywhere.
    """
    return NotebookDocument(
        {
            "cells": [copy.deepcopy(dict(cell)) for cell in cells],
            "metadata": copy.deepcopy(dict(metadata)) if metadata else {},
            "nbformat": NBFORMAT_MAJOR,
            "nbformat_minor": NBFORMAT_MINOR,
        }
    )


@provisional(since="0.3.4")
class NotebookDocument:
    """An ``.ipynb`` in memory, held as the JSON mapping the file parsed to.

    The mapping *is* the document. Reads are typed views over it and writes
    are named mutators on it, so a key this class has never heard of — at the
    notebook level, on a cell, inside cell metadata, inside an output — is
    carried from read to write untouched. That is what FR-032 and FR-033 ask
    for and what makes a round trip byte-stable.

    Args:
        raw: The parsed notebook mapping. Held by reference, not copied; use
            :meth:`copy` for an independent document.

    Raises:
        NotebookStoreError: *raw* is not a mapping with a ``cells`` array of
            mappings.

    Example:
        >>> document = new_notebook([new_code_cell("import numpy")])
        >>> document.cells[0].source
        'import numpy'
    """

    __slots__ = ("_raw",)

    def __init__(self, raw: dict[str, Any]) -> None:
        _validate_document(raw)
        self._raw = raw

    # ---- construction and serialisation ---------------------------------

    @classmethod
    def from_json(cls, text: str, *, source: str = "<notebook>") -> NotebookDocument:
        """Parse *text* as a notebook.

        Args:
            text: The ``.ipynb`` file's decoded content.
            source: Name used in the error message; usually a path.

        Raises:
            NotebookStoreError: *text* is not JSON, or not a notebook.
        """
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise NotebookStoreError(f"{source} is not valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise NotebookStoreError(f"{source} is not a notebook: top level is {type(parsed).__name__}, not an object")
        try:
            return cls(parsed)
        except NotebookStoreError as exc:
            raise NotebookStoreError(f"{source} is not a notebook: {exc}") from exc

    def to_json(self) -> str:
        """Serialise the document the way Jupyter does.

        ``indent=1``, no ASCII escaping, and a trailing newline — the exact
        recipe ``nbformat`` uses — and key order is whatever the document
        carries, which for a file Jupyter wrote is already sorted. A document
        read and written back unchanged therefore comes out byte-identical.
        """
        return json.dumps(self._raw, indent=1, ensure_ascii=False) + "\n"

    def to_bytes(self) -> bytes:
        """Serialise to the bytes written to disk: UTF-8 with ``\\n`` endings.

        Encoding here rather than letting text-mode IO do it keeps Windows
        from translating every newline to ``\\r\\n``, which would make the
        same notebook two different files on two platforms.
        """
        return self.to_json().encode("utf-8")

    def copy(self) -> NotebookDocument:
        """Return an independent deep copy of this document."""
        return NotebookDocument(copy.deepcopy(self._raw))

    # ---- reads ----------------------------------------------------------

    @property
    def raw(self) -> Mapping[str, Any]:
        """Read-only view of the whole notebook mapping."""
        return MappingProxyType(self._raw)

    @property
    def cells(self) -> tuple[NotebookCell, ...]:
        """The notebook's cells, in written order."""
        return tuple(NotebookCell(cell) for cell in self._cell_list)

    @property
    def metadata(self) -> Mapping[str, Any]:
        """Read-only view of notebook-level metadata (kernelspec, language, ...)."""
        metadata = self._raw.get("metadata")
        return MappingProxyType(metadata if isinstance(metadata, dict) else {})

    @property
    def scistudio_metadata(self) -> Mapping[str, Any]:
        """Read-only view of the notebook's ``scistudio`` metadata namespace.

        Where the session id of FR-001 and the analysis version of the
        analysis spec's FR-031 live.
        """
        namespace = self.metadata.get(ANALYSIS_METADATA_KEY)
        return MappingProxyType(namespace if isinstance(namespace, dict) else {})

    @property
    def nbformat_version(self) -> tuple[int, int]:
        """The document's ``(nbformat, nbformat_minor)``, defaulting to ``(4, 0)``."""
        major = self._raw.get("nbformat")
        minor = self._raw.get("nbformat_minor")
        return (
            major if isinstance(major, int) and not isinstance(major, bool) else NBFORMAT_MAJOR,
            minor if isinstance(minor, int) and not isinstance(minor, bool) else 0,
        )

    def index_of(self, cell_id: str) -> int | None:
        """Return the position of the cell with *cell_id*, or ``None``."""
        for index, cell in enumerate(self._cell_list):
            if cell.get("id") == cell_id:
                return index
        return None

    def cell(self, cell_id: str) -> NotebookCell:
        """Return the cell with *cell_id*.

        Raises:
            KeyError: No cell carries that id.
        """
        return NotebookCell(self._cell_list[self._require_index(cell_id)])

    # ---- writes ---------------------------------------------------------

    def set_notebook_metadata(self, key: str, value: Any) -> None:
        """Set one notebook-level metadata *key*, leaving every other key alone."""
        self._notebook_metadata()[key] = value

    def set_scistudio_metadata(self, key: str, value: Any) -> None:
        """Set one key inside the notebook's ``scistudio`` metadata namespace.

        Used for the ref-safe session id of FR-001. Sibling keys are untouched.
        """
        self._namespace(self._notebook_metadata())[key] = value

    def set_cell_source(self, cell_id: str, source: str) -> None:
        """Replace one cell's source, persisting an edit received through the API (FR-005).

        The stored form follows the form the file already used, so a document
        whose cells hold plain strings keeps holding plain strings.

        Raises:
            KeyError: No cell carries that id.
        """
        cell = self._cell_list[self._require_index(cell_id)]
        cell["source"] = _store_source(source, cell.get("source"))

    def set_cell_enabled(self, cell_id: str, *, enabled: bool) -> None:
        """Write a cell's enabled flag (FR-033).

        The flag is the notebook's to own; the analysis only reads it. It is
        written into the ``scistudio`` namespace beside the analysis record,
        and neither disturbs the other.

        Raises:
            KeyError: No cell carries that id.
        """
        cell = self._cell_list[self._require_index(cell_id)]
        self._namespace(self._cell_metadata(cell))[ENABLED_METADATA_KEY] = bool(enabled)

    def set_cell_outputs(
        self,
        cell_id: str,
        outputs: Iterable[Mapping[str, Any]],
        *,
        execution_count: int | None = None,
    ) -> None:
        """Write what a run produced into one code cell (FR-027).

        The counterpart of :meth:`without_outputs`: that one clears outputs for
        the commit, this one records them so the file on disk keeps them and a
        notebook reopened here — or in JupyterLab — shows what ran.

        *outputs* replaces whatever the cell held; each item is deep-copied, so
        the caller keeps no handle into the document. The items are nbformat
        output mappings (``output_type`` plus that type's own fields), which is
        the shape :class:`~scistudio.explore.kernel.KernelOutput` already
        carries.

        Args:
            cell_id: The cell that ran.
            outputs: The nbformat output mappings, in arrival order.
            execution_count: The kernel's counter for this execution, or
                ``None`` to record none.

        Raises:
            KeyError: No cell carries that id.
            NotebookStoreError: The cell is not a code cell. Only a code cell
                may carry ``outputs``; writing them onto a markdown cell would
                produce a notebook nbformat rejects.
        """
        cell = self._cell_list[self._require_index(cell_id)]
        if cell.get("cell_type") != _EXECUTABLE_CELL_TYPE:
            raise NotebookStoreError(f"Cell {cell_id!r} is not a code cell, so it cannot carry outputs")
        cell["outputs"] = [copy.deepcopy(dict(output)) for output in outputs]
        cell["execution_count"] = execution_count

    def set_analysis_record(self, cell_id: str, record: Mapping[str, Any]) -> None:
        """Merge the dependency analysis' record into a cell's ``scistudio`` metadata.

        The record's keys are written over; every other key in the namespace —
        the enabled flag, another tool's data — is left where it is. Values
        are deep-copied so the caller keeps no handle into the document.

        Raises:
            KeyError: No cell carries that id.
        """
        cell = self._cell_list[self._require_index(cell_id)]
        namespace = self._namespace(self._cell_metadata(cell))
        for key, value in record.items():
            namespace[key] = copy.deepcopy(value)

    def append_cell(self, cell: Mapping[str, Any]) -> NotebookCell:
        """Append a cell mapping (deep-copied) and return the view over it."""
        return self.insert_cell(len(self._cell_list), cell)

    def insert_cell(self, index: int, cell: Mapping[str, Any]) -> NotebookCell:
        """Insert a cell mapping (deep-copied) at *index* and return the view over it."""
        stored = copy.deepcopy(dict(cell))
        self._cell_list.insert(index, stored)
        return NotebookCell(stored)

    def insert_cell_after(self, cell_id: str, cell: Mapping[str, Any]) -> NotebookCell:
        """Insert a cell directly after the cell with *cell_id* (FR-018).

        Raises:
            KeyError: No cell carries that id.
        """
        return self.insert_cell(self._require_index(cell_id) + 1, cell)

    def remove_cell(self, cell_id: str) -> None:
        """Delete the cell with *cell_id*.

        Raises:
            KeyError: No cell carries that id.
        """
        del self._cell_list[self._require_index(cell_id)]

    def without_outputs(self) -> NotebookDocument:
        """Return a copy with cell outputs and execution counts cleared (FR-032).

        This document is untouched — the on-disk file keeps its outputs
        (FR-027) while the committed form does not (FR-028). Only cells that
        already carry ``outputs`` / ``execution_count`` are changed, so a
        markdown cell does not grow keys nbformat does not allow it, and
        nothing else in the document is disturbed: cell metadata, the analysis
        record, the enabled flag, and every unrecognised key survive, because
        packaging and the commit reader need them.
        """
        stripped = copy.deepcopy(self._raw)
        for cell in stripped["cells"]:
            if not isinstance(cell, dict):  # pragma: no cover - _validate_document rejects these
                continue
            if "outputs" in cell:
                cell["outputs"] = []
            if "execution_count" in cell:
                cell["execution_count"] = None
        return NotebookDocument(stripped)

    # ---- internals ------------------------------------------------------

    @property
    def _cell_list(self) -> list[Any]:
        cells = self._raw["cells"]
        if not isinstance(cells, list):  # pragma: no cover - _validate_document guarantees this
            raise NotebookStoreError("'cells' is no longer an array")
        return cells

    def _require_index(self, cell_id: str) -> int:
        index = self.index_of(cell_id)
        if index is None:
            raise KeyError(f"No cell with id {cell_id!r} in this notebook")
        return index

    def _notebook_metadata(self) -> dict[str, Any]:
        metadata = self._raw.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            self._raw["metadata"] = metadata
        return metadata

    @staticmethod
    def _cell_metadata(cell: dict[str, Any]) -> dict[str, Any]:
        metadata = cell.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            cell["metadata"] = metadata
        return metadata

    @staticmethod
    def _namespace(metadata: dict[str, Any]) -> dict[str, Any]:
        namespace = metadata.get(ANALYSIS_METADATA_KEY)
        if not isinstance(namespace, dict):
            namespace = {}
            metadata[ANALYSIS_METADATA_KEY] = namespace
        return namespace

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, NotebookDocument):
            return NotImplemented
        return self._raw == other._raw

    def __repr__(self) -> str:
        return f"NotebookDocument(cells={len(self._cell_list)})"


def _validate_document(raw: object) -> None:
    """Reject anything that is not a notebook, before it becomes one."""
    if not isinstance(raw, dict):
        raise NotebookStoreError(f"top level is {type(raw).__name__}, not an object")
    cells = raw.get("cells")
    if cells is None:
        raise NotebookStoreError("no 'cells' array")
    if not isinstance(cells, list):
        raise NotebookStoreError(f"'cells' is {type(cells).__name__}, not an array")
    for index, cell in enumerate(cells):
        if not isinstance(cell, dict):
            raise NotebookStoreError(f"cell {index} is {type(cell).__name__}, not an object")


@provisional(since="0.3.4")
def read_notebook(path: str | os.PathLike[str]) -> NotebookDocument:
    """Read the notebook at *path*.

    Args:
        path: The ``.ipynb`` file.

    Raises:
        FileNotFoundError: There is no file at *path*.
        NotebookStoreError: The file is not a notebook.
    """
    resolved = Path(path)
    return NotebookDocument.from_json(resolved.read_bytes().decode("utf-8"), source=str(resolved))


@provisional(since="0.3.4")
def write_notebook(path: str | os.PathLike[str], document: NotebookDocument) -> Path:
    """Write *document* to *path* atomically, outputs and all (FR-027).

    The write is temp-file-then-rename, so a crash never leaves a truncated
    notebook and a watcher sees one event rather than a partial file.

    Returns:
        The destination path.
    """
    return atomic_write_bytes(path, document.to_bytes())


@provisional(since="0.3.4")
def strip_outputs(document: NotebookDocument) -> NotebookDocument:
    """Return *document* with outputs cleared, leaving *document* alone (FR-032).

    The committed form of a session (FR-028) carries no outputs; the file on
    disk keeps them. This is the seam between the two, and it writes nothing
    anywhere.
    """
    return document.without_outputs()


@provisional(since="0.3.4")
class NotebookStore:
    """One session notebook on disk, and whether it changed underneath us.

    Reads and writes go through a store instance so that it can tell its own
    writes from somebody else's. It remembers a digest of the exact bytes it
    last read or wrote; :meth:`has_external_change` compares that against the
    file. A write the session performed therefore never triggers a reload
    (assumption A-012), while an edit from JupyterLab, a git checkout, or a
    text editor does (FR-005).

    Comparison is on content, not on ``mtime``: a file written twice inside
    one clock tick can carry the same timestamp — the Windows system clock
    updates roughly every 15 ms — so a stat-based check would miss exactly the
    edit that matters. Session notebooks are small and the check runs on a
    filesystem event, not in a loop.

    Content is also the right question rather than the file's identity: a git
    checkout that restores byte-identical content has changed nothing the
    session needs to reload.

    Args:
        path: The ``.ipynb`` this store owns. Nothing is read at construction.

    Example:
        >>> store = NotebookStore(path)
        >>> document = store.read()
        >>> store.write(document)
        >>> store.has_external_change()
        False
    """

    __slots__ = ("_path", "_seen")

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._path = Path(path)
        self._seen: str | None = None

    @property
    def path(self) -> Path:
        """The notebook file this store owns."""
        return self._path

    @property
    def last_seen_digest(self) -> str | None:
        """Digest of the bytes last read or written, or ``None`` before either."""
        return self._seen

    def exists(self) -> bool:
        """Whether the notebook file is present."""
        return self._path.is_file()

    def read(self) -> NotebookDocument:
        """Read the notebook and remember its bytes.

        Raises:
            FileNotFoundError: There is no file at :attr:`path`.
            NotebookStoreError: The file is not a notebook.
        """
        payload = self._path.read_bytes()
        document = NotebookDocument.from_json(payload.decode("utf-8"), source=str(self._path))
        self._seen = _digest(payload)
        return document

    def write(self, document: NotebookDocument) -> Path:
        """Write *document* atomically and remember the bytes written.

        The session writes before every run so a kernel death loses nothing
        typed (FR-027). Because the digest recorded is of the bytes this call
        produced, the write that follows is invisible to
        :meth:`has_external_change`.

        Returns:
            The destination path.
        """
        payload = document.to_bytes()
        destination = atomic_write_bytes(self._path, payload)
        self._seen = _digest(payload)
        return destination

    def has_external_change(self) -> bool:
        """Whether the file differs from what this store last read or wrote.

        ``True`` when the store has seen nothing yet and a file exists, when
        the content differs, or when a file the store had seen is now gone.
        ``False`` when the content matches — including after this store's own
        write, and including a rewrite that restored identical bytes.
        """
        try:
            payload = self._path.read_bytes()
        except FileNotFoundError:
            return self._seen is not None
        return _digest(payload) != self._seen

    def reload(self) -> NotebookDocument | None:
        """Re-read the notebook if it changed on disk from outside (FR-005).

        Returns:
            The reloaded document, or ``None`` when the file still holds the
            bytes this store last read or wrote. The caller keeps its marks by
            cell id across the reload and leaves the kernel namespace alone;
            both are the session's, not the store's.

        Raises:
            FileNotFoundError: The notebook has been deleted.
            NotebookStoreError: The file on disk is no longer a notebook — the
                store keeps its previous digest, so the next well-formed write
                still reads as a change.
        """
        payload = self._path.read_bytes()
        digest = _digest(payload)
        if digest == self._seen:
            return None
        document = NotebookDocument.from_json(payload.decode("utf-8"), source=str(self._path))
        self._seen = digest
        return document

    def __repr__(self) -> str:
        return f"NotebookStore({str(self._path)!r})"
