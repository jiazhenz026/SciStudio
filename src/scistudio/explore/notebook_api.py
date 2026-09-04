"""The three notebook helpers, in a session and in a packaged run (T-004).

``scistudio.input``, ``scistudio.output``, and ``scistudio.load`` are the only
SciStudio-specific lines an explore notebook contains, and the whole point of
them is that **the same lines work in both places a notebook runs**
(``docs/specs/adr-054-explore-session.md`` FR-010, FR-011; §4.1 "Two modes for
three helpers"). A person explores in a session, packages the notebook, and the
block that comes out runs the notebook they wrote — not a rewritten copy of it.

Two modes, one contract::

    signal = scistudio.load(scistudio.input("signal"))
    peaks = find_peaks(signal)
    scistudio.output(peaks=peaks)

* **Session mode.** ``input("signal")`` returns the reference of the bound
  run's port artefact, ``load`` resolves that reference through the storage
  layer, and ``output`` registers the name as a declared output and writes
  nothing — the session is exploration, and packaging is the thing that turns a
  declaration into a port.
* **Packaged mode.** The notebook is a Code Block's script, so the helpers
  speak to the exchange folders that Code Block already passes data through:
  ``input("signal")`` returns the materialised input file for that port,
  ``load`` reads it back through the existing IO adapters, and ``output``
  writes each object into its output folder through the same adapters.

The launcher picks the mode with :data:`MODE_ENV_VAR`; nothing in the notebook
selects it and nothing in the notebook can tell which one it got, which is what
makes the two runs comparable. There is no default: a helper called with no
mode set raises :class:`NotebookModeError` rather than guessing, because
guessing wrong would silently write a person's results into the wrong place.

**Import discipline.** This module is imported *inside a kernel*, where the
cost of importing the storage stack is paid by the first cell a person runs.
Every ``scistudio.core`` and ``scistudio.blocks`` import is therefore made
inside the function that needs it: importing this module costs the standard
library, and the explore subsystem's layer rule
(``tests/architecture/test_layer_deps.py``) stays satisfied without a rule
change.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal

from scistudio.stability import provisional

if TYPE_CHECKING:  # pragma: no cover - imported for annotations only
    from scistudio.core.storage.ref import StorageReference
    from scistudio.core.types.base import DataObject

__all__ = [
    "ARTEFACT_REFERENCE_SCHEME",
    "EXCHANGE_DIR_ENV_VAR",
    "INPUTS_DIR_ENV_VAR",
    "MODE_ENV_VAR",
    "OUTPUTS_DIR_ENV_VAR",
    "PACKAGED_MODE",
    "SESSION_MODE",
    "DeclaredOutput",
    "NotebookLoadError",
    "NotebookMode",
    "NotebookModeError",
    "NotebookPortError",
    "SessionBinding",
    "bind_session",
    "clear_declared_outputs",
    "clear_session",
    "current_mode",
    "declared_outputs",
    "decode_artefact_reference",
    "encode_artefact_reference",
    "input",
    "is_artefact_reference",
    "load",
    "output",
    "session_binding",
    "wrap_native",
]


NotebookMode = Literal["session", "packaged"]
"""Which of the two places a notebook is running in.

A ``Literal`` alias cannot carry a runtime stability marker; it is part of this
module's public surface alongside the decorated symbols below.
"""

SESSION_MODE: Final[NotebookMode] = "session"
"""The notebook is a cell in a live explore session."""

PACKAGED_MODE: Final[NotebookMode] = "packaged"
"""The notebook is the script of a packaged Code Block."""

MODE_ENV_VAR: Final[str] = "SCISTUDIO_NOTEBOOK_MODE"
"""The environment variable the launcher sets to pick the mode (FR-010).

The session service sets it to ``"session"`` on the kernel it launches; the
packaged Code Block's run sets it to ``"packaged"``. Any other value, or none,
is an error rather than a default.
"""

EXCHANGE_DIR_ENV_VAR: Final[str] = "SCISTUDIO_EXCHANGE_DIR"
"""Packaged mode: the Code Block's per-run exchange folder.

Set by :func:`scistudio.blocks.code.codeblock_exchange_env`, together with the
two below. The exchange folder holds ``manifest.json``, which names each port's
folder, declared type, and file extension.
"""

INPUTS_DIR_ENV_VAR: Final[str] = "SCISTUDIO_INPUTS_DIR"
"""Packaged mode: the folder holding one subfolder per input port."""

OUTPUTS_DIR_ENV_VAR: Final[str] = "SCISTUDIO_OUTPUTS_DIR"
"""Packaged mode: the folder holding one subfolder per output port."""

ARTEFACT_REFERENCE_SCHEME: Final[str] = "scistudio+artefact"
"""URI scheme of the reference :func:`input` returns in session mode."""


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


@provisional(since="0.3.4")
class NotebookModeError(RuntimeError):
    """Raised when a helper is called outside a session and outside a package.

    The helpers exist to move data across a boundary — a session's bound run,
    or a Code Block's exchange folders — and outside both there is no boundary
    to move it across. This is what a person sees when they import
    ``scistudio`` in a plain Python shell and call ``scistudio.input``.
    """


@provisional(since="0.3.4")
class NotebookPortError(LookupError):
    """Raised when a port name is not one this notebook run has.

    The message names the port asked for and the ports that exist, because the
    usual cause is a typo or a notebook run against the wrong binding.
    """


@provisional(since="0.3.4")
class NotebookLoadError(RuntimeError):
    """Raised when :func:`load` cannot turn its argument into a data object."""


# ---------------------------------------------------------------------------
# Session-mode state, installed by the bridge at kernel start
# ---------------------------------------------------------------------------


@provisional(since="0.3.4")
@dataclass(frozen=True)
class SessionBinding:
    """What the session told the kernel about the run it was opened over.

    The session service builds one of these when it starts a kernel and hands
    it to the kernel-side bridge, which installs it here (FR-003, FR-010). It
    is the whole of session mode's state: a mapping of port name to the
    reference of that port's artefact, plus the project the session belongs to.
    """

    inputs: Mapping[str, str] = field(default_factory=dict)
    """Port name to artefact reference, as :func:`encode_artefact_reference` builds them."""

    project_dir: str | None = None
    """The project root, for the previewer tiers a variable window resolves."""

    run_id: str | None = None
    """The run whose outputs the session was opened over, when it was opened over one."""


@provisional(since="0.3.4")
@dataclass(frozen=True)
class DeclaredOutput:
    """One name a cell declared with ``scistudio.output`` in session mode.

    Packaging turns these into the block's output ports (FR-038). The value is
    kept as the cell passed it so that the declaration records what was
    declared even if the name is rebound afterwards; it is a reference to an
    object the namespace already holds, so it costs no extra memory.
    """

    name: str
    """The keyword the cell used, which becomes the port name."""

    value: Any
    """The object that was declared."""

    type_name: str
    """``type(value).__name__``, recorded at declaration time."""


_SESSION: SessionBinding | None = None
_DECLARED: dict[str, DeclaredOutput] = {}
#: Packaged mode only: which port each path :func:`input` handed out came from,
#: so :func:`load` knows the declared type without the notebook naming it.
_PACKAGED_PORT_BY_PATH: dict[str, dict[str, Any]] = {}
#: Lazily created by :func:`_scratch_dir` when there is no exchange folder to
#: stage into. Held for the life of the process, because the objects staged in
#: it are read for as long as the notebook holds them; its finalizer removes it.
_PROCESS_SCRATCH: Any = None


@provisional(since="0.3.4")
def bind_session(binding: SessionBinding) -> None:
    """Install *binding* as this kernel's session state (FR-010).

    Called by the kernel-side bridge at kernel start, not by a notebook. It
    replaces any previous binding, because a kernel serves one session and a
    restart re-installs.

    Args:
        binding: The session's inputs and project.
    """
    global _SESSION
    _SESSION = binding


@provisional(since="0.3.4")
def clear_session() -> None:
    """Forget the session binding and every declared output.

    A restart resets the namespace, so it must reset the declarations that were
    made in it (FR-023 resets marks for the same reason).
    """
    global _SESSION
    _SESSION = None
    _DECLARED.clear()
    _PACKAGED_PORT_BY_PATH.clear()


@provisional(since="0.3.4")
def session_binding() -> SessionBinding | None:
    """The installed session binding, or ``None`` outside session mode."""
    return _SESSION


@provisional(since="0.3.4")
def declared_outputs() -> tuple[DeclaredOutput, ...]:
    """Every name declared with :func:`output`, in declaration order.

    A name declared twice appears once, carrying the later declaration and in
    the later declaration's position: "the later declaration in written order
    wins" (spec §2, Edge Cases).
    """
    return tuple(_DECLARED.values())


@provisional(since="0.3.4")
def clear_declared_outputs() -> None:
    """Drop every declaration without touching the session binding."""
    _DECLARED.clear()


# ---------------------------------------------------------------------------
# Mode
# ---------------------------------------------------------------------------


@provisional(since="0.3.4")
def current_mode() -> NotebookMode:
    """Return the mode the launcher selected (FR-010).

    Returns:
        ``"session"`` or ``"packaged"``.

    Raises:
        NotebookModeError: :data:`MODE_ENV_VAR` is unset or holds anything
            else. There is deliberately no default: the two modes write a
            person's results to different places, so a wrong guess is worse
            than a refusal.
    """
    raw = os.environ.get(MODE_ENV_VAR, "").strip().lower()
    if raw == SESSION_MODE:
        return SESSION_MODE
    if raw == PACKAGED_MODE:
        return PACKAGED_MODE
    if not raw:
        msg = (
            f"scistudio's notebook helpers need {MODE_ENV_VAR} to be set to "
            f"{SESSION_MODE!r} or {PACKAGED_MODE!r}. They run inside an explore session's kernel "
            "or inside a packaged notebook block's run, and the launcher sets the variable in "
            "both; outside those there is no run to read inputs from or write outputs to."
        )
        raise NotebookModeError(msg)
    msg = f"{MODE_ENV_VAR}={raw!r} is not a notebook mode; expected {SESSION_MODE!r} or {PACKAGED_MODE!r}."
    raise NotebookModeError(msg)


# ---------------------------------------------------------------------------
# Artefact references (session mode)
# ---------------------------------------------------------------------------


@provisional(since="0.3.4")
def encode_artefact_reference(
    *,
    type_name: str,
    backend: str,
    path: str,
    format: str | None = None,
) -> str:
    """Build the reference session-mode :func:`input` hands to :func:`load`.

    The session service calls this when it binds a run's output ports to a new
    session. The reference is a URI rather than an opaque token so that a
    person who prints it in a cell sees where their data is, and so that a
    reference recorded in lineage can be read a year later without the object
    that produced it.

    Args:
        type_name: The SciStudio type recorded for the artefact, e.g. ``"DataFrame"``.
        backend: The storage backend the artefact lives in.
        path: The artefact's path within that backend.
        format: The backend's format hint, when it has one.

    Returns:
        A ``scistudio+artefact:`` URI.

    Example:
        >>> ref = encode_artefact_reference(type_name="Text", backend="filesystem", path="a/b.txt")
        >>> decode_artefact_reference(ref)[0]
        'Text'
    """
    query = {"type": type_name, "backend": backend, "path": path}
    if format is not None:
        query["format"] = format
    return f"{ARTEFACT_REFERENCE_SCHEME}:?{urllib.parse.urlencode(query)}"


@provisional(since="0.3.4")
def is_artefact_reference(value: object) -> bool:
    """Whether *value* is a string :func:`decode_artefact_reference` can read."""
    return isinstance(value, str) and value.startswith(f"{ARTEFACT_REFERENCE_SCHEME}:")


@provisional(since="0.3.4")
def decode_artefact_reference(reference: str) -> tuple[str, StorageReference]:
    """Split a reference into its recorded type name and its storage pointer.

    Args:
        reference: A URI built by :func:`encode_artefact_reference`.

    Returns:
        The recorded type name and the :class:`~scistudio.core.storage.ref.StorageReference`.

    Raises:
        ValueError: *reference* is not an artefact reference, or is missing the
            backend or path it needs to point at anything.
    """
    from scistudio.core.storage.ref import StorageReference

    if not is_artefact_reference(reference):
        msg = f"Not an artefact reference: {reference!r} (expected a {ARTEFACT_REFERENCE_SCHEME}: URI)."
        raise ValueError(msg)
    _scheme, _, remainder = reference.partition(":")
    query = urllib.parse.parse_qs(remainder.lstrip("?"), keep_blank_values=False)
    backend = _single(query, "backend")
    path = _single(query, "path")
    if not backend or not path:
        msg = f"Artefact reference {reference!r} carries no {'backend' if not backend else 'path'}."
        raise ValueError(msg)
    return _single(query, "type") or "DataObject", StorageReference(
        backend=backend,
        path=path,
        format=_single(query, "format"),
    )


def _single(query: Mapping[str, list[str]], key: str) -> str | None:
    """The one value recorded for *key*, or ``None``."""
    values = query.get(key) or []
    return values[0] if values else None


# ---------------------------------------------------------------------------
# The three helpers
# ---------------------------------------------------------------------------


@provisional(since="0.3.4")
def input(name: str) -> str | Path:
    """Return this run's value for the input port *name* (FR-010, FR-011).

    In session mode the return is the reference of the bound run's port
    artefact; in packaged mode it is the materialised input file for that port.
    Both are arguments :func:`load` accepts, which is what lets the notebook
    line ``x = scistudio.load(scistudio.input("x"))`` stand unchanged in both.

    Args:
        name: The port name, as the notebook declares it.

    Returns:
        A reference string (session mode) or a :class:`~pathlib.Path`
        (packaged mode).

    Raises:
        NotebookModeError: No mode is set. See :func:`current_mode`.
        NotebookPortError: This run has no input port called *name*, or the
            port's folder holds no file (packaged mode).
    """
    if current_mode() == SESSION_MODE:
        binding = _require_session()
        try:
            return binding.inputs[name]
        except KeyError:
            available = ", ".join(sorted(binding.inputs)) or "none"
            msg = f"This session has no input named {name!r}. Bound inputs: {available}."
            raise NotebookPortError(msg) from None
    return _packaged_input(name)


@provisional(since="0.3.4")
def load(source: object) -> DataObject:
    """Resolve *source* to a :class:`~scistudio.core.types.base.DataObject`.

    Accepts what :func:`input` returns in either mode, a path to a file the
    person names themselves (which is how a session opened over a file loads
    it, FR-004), and a data object, which it returns unchanged so that
    ``load(load(x))`` is harmless.

    **The object comes back storage-backed in both modes**, which is what makes
    the line after the load portable. ``to_memory``, ``slice``, and
    ``iter_chunks`` all read through
    :attr:`~scistudio.core.types.base.DataObject.storage_ref`, so a mode that
    returned an object without one would give a notebook that works while a
    person explores and fails once it is packaged — the single failure this
    whole two-mode design exists to prevent. A session load already resolves a
    reference, so it is backed by construction; a packaged load reads a file
    the exchange materialised, so it is written once into the run's own scratch
    folder. That write is a deliberate cost: the file has already been read
    into memory to build the object, and paying one more pass over it is worth
    a notebook that means the same thing in both places.

    Args:
        source: An artefact reference, a file path, or a data object.

    Returns:
        The loaded object.

    Raises:
        NotebookLoadError: *source* is not something this can resolve, or the
            file it names does not exist.
    """
    from scistudio.core.types.base import DataObject

    if isinstance(source, DataObject):
        return source
    if is_artefact_reference(source):
        return _load_reference(str(source))
    if isinstance(source, (str, Path)):
        return _load_path(Path(source))
    msg = (
        f"scistudio.load cannot resolve {type(source).__name__}. Pass what scistudio.input returned, "
        "a path to a file, or a data object."
    )
    raise NotebookLoadError(msg)


@provisional(since="0.3.4")
def output(**names: Any) -> None:
    """Declare each keyword as one of this notebook's outputs (FR-010, FR-011).

    In session mode this registers the names and writes nothing: the session is
    exploration and packaging is what turns a declaration into a port. In
    packaged mode the same call writes each object into its output folder
    through the same adapters a Code Block already uses, which is why the line
    the person wrote while exploring is the line the block runs.

    Args:
        **names: Port name to the object to declare.

    Raises:
        NotebookModeError: No mode is set. See :func:`current_mode`.
        NotebookPortError: Packaged mode, and either the declared name is not
            one of the block's output ports or the run has no exchange manifest
            to say what file format the port carries.
    """
    mode = current_mode()
    for name, value in names.items():
        if mode == SESSION_MODE:
            # "The later declaration in written order wins" (spec §2, Edge
            # Cases): drop the earlier entry so the winner also takes the
            # later position rather than inheriting the first one's.
            _DECLARED.pop(name, None)
            _DECLARED[name] = DeclaredOutput(name=name, value=value, type_name=type(value).__name__)
        else:
            _packaged_output(name, value)


# ---------------------------------------------------------------------------
# Wrapping a native object into its SciStudio type
# ---------------------------------------------------------------------------


@provisional(since="0.3.4")
def wrap_native(obj: object) -> DataObject:
    """Wrap a plain Python object into its SciStudio type by construction from data.

    This is the "by construction from data" of FR-009 and the way
    :func:`output` accepts a bare frame rather than demanding the person build
    a typed object first. A :class:`~scistudio.core.types.base.DataObject` is
    returned unchanged.

    The mapping is the one the IO loaders already use: a pandas or Arrow table
    is a :class:`~scistudio.core.types.dataframe.DataFrame`, a pandas Series is
    a single-column :class:`~scistudio.core.types.series.Series`, a NumPy array
    is an :class:`~scistudio.core.types.array.Array` with generated axis names,
    text is :class:`~scistudio.core.types.text.Text`, and an existing file is
    an :class:`~scistudio.core.types.artifact.Artifact`.

    Args:
        obj: The object to wrap.

    Returns:
        The wrapped object.

    Raises:
        TypeError: No rule covers this type. The message names it, because the
            answer is either to declare a SciStudio type for it or to convert
            it in the cell, and a silent pickle would be neither.
    """
    from scistudio.core.types.artifact import Artifact
    from scistudio.core.types.base import DataObject
    from scistudio.core.types.text import Text

    if isinstance(obj, DataObject):
        return obj
    if isinstance(obj, str):
        return Text(content=obj)
    if isinstance(obj, Path):
        return Artifact(file_path=obj)

    # numpy and pandas are consulted only when they are already imported: an
    # object cannot be a DataFrame if pandas was never imported, so this is a
    # ``sys.modules`` lookup rather than an import cost paid by every caller
    # (the discipline :mod:`scistudio.explore.fingerprint` uses).
    pandas = sys.modules.get("pandas")
    if pandas is not None:
        wrapped = _wrap_pandas(obj, pandas)
        if wrapped is not None:
            return wrapped
    arrow = sys.modules.get("pyarrow")
    if arrow is not None and isinstance(obj, arrow.Table):
        return _dataframe_from_table(obj)
    numpy = sys.modules.get("numpy")
    if numpy is not None and isinstance(obj, numpy.ndarray):
        from scistudio.core.types.array import Array

        return Array(
            axes=[f"axis_{index}" for index in range(obj.ndim)],
            shape=tuple(int(size) for size in obj.shape),
            dtype=str(obj.dtype),
            data=obj,
        )
    msg = (
        f"scistudio has no data type for {type(obj).__name__}. Wrap it yourself "
        "(for example DataFrame(data=table) or Artifact(file_path=path)) and pass that."
    )
    raise TypeError(msg)


def _wrap_pandas(obj: object, pandas: Any) -> DataObject | None:
    """Wrap a pandas frame or series, or return ``None`` when *obj* is neither."""
    import pyarrow

    from scistudio.core.types.series import Series

    if isinstance(obj, pandas.DataFrame):
        return _dataframe_from_table(pyarrow.Table.from_pandas(obj, preserve_index=False))
    if isinstance(obj, pandas.Series):
        # The repository's convention for a Series payload is a single-column
        # Arrow table (see ``scistudio.blocks.io.loaders.load_data``).
        name = obj.name if obj.name is not None else "value"
        table = pyarrow.table({str(name): pyarrow.array(obj.to_numpy())})
        return Series(
            index_name=obj.index.name,
            value_name=str(name),
            length=len(obj),
            data=table,
        )
    return None


def _dataframe_from_table(table: Any) -> DataObject:
    """Build a :class:`DataFrame` around an Arrow table."""
    from scistudio.core.types.dataframe import DataFrame

    return DataFrame(
        columns=list(table.column_names),
        row_count=int(table.num_rows),
        data=table,
    )


# ---------------------------------------------------------------------------
# Session mode internals
# ---------------------------------------------------------------------------


def _require_session() -> SessionBinding:
    """The installed binding, or an error explaining that none was installed."""
    if _SESSION is None:
        msg = (
            f"{MODE_ENV_VAR}={SESSION_MODE!r} but no session binding is installed in this kernel. "
            "The session service installs one through the kernel bridge at kernel start; a kernel "
            "started outside a session has no run to read inputs from."
        )
        raise NotebookModeError(msg)
    return _SESSION


def _load_reference(reference: str) -> DataObject:
    """Resolve an artefact reference through the storage layer (FR-010)."""
    from scistudio.core.types.base import DataObject

    type_name, storage_ref = decode_artefact_reference(reference)
    data_type = _resolve_type(type_name)
    try:
        return data_type(storage_ref=storage_ref)  # type: ignore[call-arg]
    except TypeError:
        # A type whose constructor needs more than the shared slots (Array
        # needs axes) cannot be built from a reference alone. A plain
        # DataObject still reads the same bytes through the same backend, and
        # saying so is better than failing the person's first cell.
        return DataObject(storage_ref=storage_ref)


def _resolve_type(type_name: str) -> type[DataObject]:
    """Resolve a recorded type name to its class, falling back to the base."""
    from scistudio.core.types.base import DataObject
    from scistudio.core.types.registry import TypeRegistry

    registry = TypeRegistry()
    registry.scan_builtins()
    try:
        resolved = registry.load_class(type_name)
    except Exception:  # an unregistered or unimportable plugin type
        return DataObject
    return resolved if isinstance(resolved, type) and issubclass(resolved, DataObject) else DataObject


# ---------------------------------------------------------------------------
# Packaged mode internals
# ---------------------------------------------------------------------------


def _packaged_input(name: str) -> Path:
    """The materialised input file for port *name* (FR-011)."""
    from scistudio.blocks.code.exchange import safe_exchange_name

    record = _manifest_port("input", name)
    if record is not None:
        folder = Path(str(record["folder"]))
    else:
        _refuse_undeclared_port("input", name)
        folder = _required_dir(INPUTS_DIR_ENV_VAR) / safe_exchange_name(name, fallback="port")
    if not folder.is_dir():
        inputs_dir = _required_dir(INPUTS_DIR_ENV_VAR)
        siblings = sorted(child.name for child in inputs_dir.iterdir()) if inputs_dir.is_dir() else []
        msg = (
            f"This block has no input named {name!r}: {folder} does not exist. "
            f"Input folders: {', '.join(siblings) or 'none'}."
        )
        raise NotebookPortError(msg)
    files = sorted(path for path in folder.iterdir() if path.is_file())
    if not files:
        msg = f"The input folder for port {name!r} ({folder}) is empty; nothing was materialised for it."
        raise NotebookPortError(msg)
    if len(files) > 1:
        # FR-011 says "the materialised input file", singular. Handing back one
        # of several silently would make the notebook's result depend on a
        # filename sort, which is exactly the kind of thing nobody debugs.
        listed = ", ".join(path.name for path in files)
        msg = (
            f"The input folder for port {name!r} ({folder}) holds {len(files)} files ({listed}); "
            "scistudio.input returns one file per port. Read the folder directly for a multi-file port."
        )
        raise NotebookPortError(msg)
    chosen = files[0]
    if record is not None:
        _PACKAGED_PORT_BY_PATH[str(chosen.resolve())] = record
    return chosen


def _packaged_output(name: str, value: object) -> None:
    """Write *value* into port *name*'s output folder through the IO adapters.

    Unlike :func:`_packaged_input`, this needs the run's manifest and says so
    when it is missing. Reading an input only needs the file; writing an output
    needs the port's declared file format, and the manifest is the only thing
    that carries it — a type such as ``DataFrame`` has six registered savers and
    the block registry refuses to pick between them, which is the right refusal
    to inherit rather than to paper over with a guess.
    """
    record = _manifest_port("output", name)
    if record is None:
        _refuse_undeclared_port("output", name)  # raises when a manifest exists at all
        msg = (
            f"Cannot write the output {name!r}: this run has no exchange manifest, so the port's "
            f"declared file format is unknown. The Code Block runtime writes "
            f"{EXCHANGE_DIR_ENV_VAR}/manifest.json before it launches the script."
        )
        raise NotebookPortError(msg)

    folder = Path(str(record["folder"]))
    extension = str(record.get("format_hint") or "") or None
    capability_id = record.get("capability_id")
    folder.mkdir(parents=True, exist_ok=True)

    from scistudio.blocks.io.materialisation import materialise_to_file

    materialise_to_file(
        wrap_native(value),
        folder,
        extension,
        filename_stem=name,
        capability_id=str(capability_id) if capability_id else None,
    )


def _load_path(path: Path) -> DataObject:
    """Read a file back into a data object through the existing IO adapters."""
    from scistudio.blocks.io.materialisation import reconstruct_from_file

    if not path.exists():
        msg = f"scistudio.load: no such file: {path}."
        raise NotebookLoadError(msg)
    record = _PACKAGED_PORT_BY_PATH.get(str(path.resolve()))
    target_type = _resolve_type(str(record["object_type"])) if record else _type_for_extension(path)
    extension = str(record.get("format_hint") or "") if record else ""
    try:
        loaded = reconstruct_from_file(path, target_type, extension or None)
    except LookupError as exc:
        msg = (
            f"scistudio.load could not read {path.name} as {target_type.__name__}: {exc} "
            "Register a loader for that type and extension, or load the file yourself in the cell."
        )
        raise NotebookLoadError(msg) from exc
    return _storage_backed(loaded, path.stem)


def _storage_backed(loaded: DataObject, stem: str) -> DataObject:
    """Give *loaded* a storage reference if the loader did not (see :func:`load`).

    A loader reached through ``reconstruct_from_file`` hands back an object
    carrying its data in memory and no
    :attr:`~scistudio.core.types.base.DataObject.storage_ref`, and every
    documented reader on a data object —  ``to_memory``, ``slice``,
    ``iter_chunks`` — reads through that reference. Writing the data once into
    the run's scratch folder is what makes the cell *after* the load identical
    in both modes.
    """
    if loaded.storage_ref is not None:
        return loaded
    destination = _scratch_dir() / stem
    try:
        loaded.save(str(destination))
    except Exception as exc:
        msg = (
            f"scistudio.load read {stem} but could not stage it for reading: {exc} "
            "The object is loaded but its data is not readable through to_memory()."
        )
        raise NotebookLoadError(msg) from exc
    return loaded


def _scratch_dir() -> Path:
    """A directory this run may write staging copies into.

    Prefers the Code Block's own ``tmp`` folder, which the runtime creates and
    owns for exactly this, so a packaged run leaves nothing behind anywhere
    else. Outside a packaged run (a session opened over a file) it falls back
    to one scratch directory per process, cleaned when the process exits.
    """
    exchange_dir = os.environ.get(EXCHANGE_DIR_ENV_VAR, "").strip()
    if exchange_dir:
        scratch = Path(exchange_dir) / "tmp" / "scistudio-load"
        scratch.mkdir(parents=True, exist_ok=True)
        return scratch
    global _PROCESS_SCRATCH
    if _PROCESS_SCRATCH is None:
        import tempfile

        _PROCESS_SCRATCH = tempfile.TemporaryDirectory(prefix="scistudio-notebook-load-")
    return Path(_PROCESS_SCRATCH.name)


def _type_for_extension(path: Path) -> type[DataObject]:
    """Guess the type of a file the notebook named itself.

    A path a person typed carries no declared type, so the answer comes from
    the loaders that are registered for its extension. When nothing is
    registered the answer is :class:`~scistudio.core.types.artifact.Artifact`,
    which is the fallback :func:`reconstruct_from_file` already documents and
    which keeps a load of an opaque file working.
    """
    from scistudio.blocks.registry import BlockRegistry
    from scistudio.core.types.artifact import Artifact

    suffixes = [suffix.lower() for suffix in path.suffixes]
    if not suffixes:
        return Artifact
    registry = BlockRegistry()
    registry.scan()
    for start in range(len(suffixes)):
        extension = "".join(suffixes[start:])
        capabilities = registry.list_format_capabilities(direction="load", extension=extension)
        if capabilities:
            return capabilities[0].data_type
    return Artifact


def _manifest_port(direction: str, name: str) -> dict[str, Any] | None:
    """The manifest record for one port, or ``None`` when there is no manifest.

    The Code Block writes ``manifest.json`` before it launches the script, so
    in a real packaged run this is present and authoritative about the port's
    folder, declared type, and extension. Everything below tolerates its
    absence so a notebook run by hand against hand-made exchange folders still
    works.
    """
    exchange_dir = os.environ.get(EXCHANGE_DIR_ENV_VAR, "").strip()
    if not exchange_dir:
        return None
    manifest_path = Path(exchange_dir) / "manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        ports = manifest["ports"]
    except (OSError, ValueError, KeyError):
        return None
    record = ports.get(f"{direction}:{name}")
    return record if isinstance(record, dict) else None


def _refuse_undeclared_port(direction: str, name: str) -> None:
    """Refuse a port the run's manifest does not declare.

    Reached only when :func:`_manifest_port` found no record. If there is a
    manifest, it is authoritative and the name is simply not a port of this
    block, so guessing a folder for it would write a person's result somewhere
    nothing collects it from. If there is no manifest at all — a notebook run
    by hand against hand-made exchange folders — there is nothing to contradict
    and the caller falls back to the folder named after the port.
    """
    declared = _manifest_port_names(direction)
    if declared is None:
        return
    listed = ", ".join(sorted(declared)) or "none"
    msg = f"This block has no {direction} port named {name!r}. Declared {direction} ports: {listed}."
    raise NotebookPortError(msg)


def _manifest_port_names(direction: str) -> set[str] | None:
    """Every port name the manifest declares for *direction*, or ``None`` with no manifest."""
    exchange_dir = os.environ.get(EXCHANGE_DIR_ENV_VAR, "").strip()
    if not exchange_dir:
        return None
    manifest_path = Path(exchange_dir) / "manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        ports = json.loads(manifest_path.read_text(encoding="utf-8"))["ports"]
    except (OSError, ValueError, KeyError):
        return None
    prefix = f"{direction}:"
    return {key[len(prefix) :] for key in ports if key.startswith(prefix)}


def _required_dir(variable: str) -> Path:
    """The directory *variable* names, or an error saying who sets it."""
    raw = os.environ.get(variable, "").strip()
    if not raw:
        msg = (
            f"{MODE_ENV_VAR}={PACKAGED_MODE!r} but {variable} is not set. The Code Block runtime sets "
            "the exchange variables for every script it launches; a notebook run in packaged mode "
            "outside that runtime has no exchange folders to read or write."
        )
        raise NotebookModeError(msg)
    return Path(raw)
