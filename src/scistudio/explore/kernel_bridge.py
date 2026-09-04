"""The bridge the service injects into a kernel, and the driver that calls it (T-003, T-010, T-011).

A panel bound to a notebook variable needs a window of a live object, and that
object exists only inside the kernel process. The marks need a fingerprint of
every top-level name before and after each run, and those names live there too.
Both are answered by a *bridge*: a small module the session service injects at
kernel start, called over the kernel's own execute channel with the output
suppressed, so a bridge call never appears as a cell
(``docs/specs/adr-054-explore-session.md`` FR-009, §4.1 "The bridge, and why
panels read through the kernel").

This module is both halves of that arrangement, because they are two views of
one protocol and keeping them together is what stops them drifting:

* **In the kernel.** :func:`_dispatch` is the entry point a bridge call runs.
  It answers namespace fingerprints, the bindings list, the process's memory, a
  variable window, the session's declared outputs, an environment snapshot, and
  a block call.
* **In the service.** :class:`KernelBridge` wraps a
  :class:`~scistudio.explore.kernel.KernelHandle` and turns each of those into a
  method.

**The block call is answered here and performed next door.** Spec §4.2's table
puts FR-049 and FR-050 in this module, and it is right that the bridge is where
a block call is *answered*: this is the protocol boundary, and a caller outside
the kernel has no other way in. The adapter's body lives in
:mod:`scistudio.explore.block_call` all the same, because putting it here would
make one module the kernel protocol, the fingerprint plumbing, the window
renderer, the helpers' backend, *and* a block runner, which is the opposite of
the narrow modules AGENTS.md §3.5 asks for. Delegation satisfies both readings
and it is deliberate — please do not "fix" the split. What lives here is the
wiring: resolving each declared input to a variable in this kernel's namespace,
binding the outputs back into it, and rendering the call's lineage facts into
something that survives the frame.

Installing the bridge also binds :data:`BLOCKS_NAME` — ``blocks`` — in the
kernel's user namespace, which is what makes ``blocks.run("some.block", ...)``
a line a cell can run at all (FR-049). Spec §4.1 makes the bridge the thing the
service injects at kernel start, so the session decides *when* a kernel starts
and the bridge decides *what is in it*. The name is not a notebook variable and
is left out of the fingerprints, the bindings list, and the window offer —
until a cell rebinds it, at which point it is one; see :func:`_is_hidden`.

**Why the answer travels on stdout.** ``execute_silent`` suppresses
``execute_input``, ``execute_result``, the history, and the execution counter —
which is exactly what "must not appear as a cell" means, and which also means
the *value* of the call is not delivered. So the bridge prints its answer, as
base64 of JSON between two sentinels, and the driver reads it out of the
request's stream output. Base64 makes the payload pure ASCII, so no console
encoding, no newline in a person's data, and no split stream message can
corrupt it.

**Windows use the previewer that already exists.** A window request wraps the
native object into its SciStudio type by construction from data
(:func:`~scistudio.explore.notebook_api.wrap_native`), persists it where the
preview data access can read it, and runs the *existing* preview provider for
that type through :meth:`PreviewSessionManager.render_target`. A table window in
a session is therefore produced by the same code that produces it in the
workflow preview — there is no second renderer to keep in step. Persisting is
done without touching the object the person's name is bound to: ``save()`` would
set ``storage_ref`` on it, and the scratch file it pointed at is deleted when
the window is done, which would leave their variable holding a dangling
reference.

**Import discipline.** Every ``scistudio.core``, ``scistudio.blocks``, and
``scistudio.previewers`` import is made inside the function that needs it, so
importing this module in a kernel costs the standard library and the analysis,
and the explore subsystem's layer rule holds without a rule change.
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from scistudio.explore.dependency_analysis import BLOCK_CALL_PATHS
from scistudio.explore.fingerprint import Fingerprint, fingerprint
from scistudio.stability import provisional

if TYPE_CHECKING:  # pragma: no cover - imported for annotations only
    from scistudio.explore.kernel import KernelHandle

__all__ = [
    "BLOCKS_NAME",
    "BRIDGE_PROTOCOL_VERSION",
    "INSTALL_PROBE",
    "Binding",
    "BridgeError",
    "BridgeProtocolError",
    "KernelBridge",
    "NotebookBlocks",
    "bindings",
    "block_call_adapter",
    "cell_installs_packages",
    "drain_block_calls",
    "environment_snapshot",
    "fingerprints",
    "memory_bytes",
    "record_block_call_lineage",
    "scistudio_type_name",
    "session_kernel_env",
    "set_block_call_adapter",
    "variable_window",
]

BRIDGE_PROTOCOL_VERSION: Final[int] = 1
"""Bumped when the request or response shape changes.

Every response carries it, and :class:`KernelBridge` refuses a reply from a
different version rather than reading fields that may have moved. The kernel is
launched from the same installation as the service, so a mismatch means
something is wrong rather than something is old.
"""

#: The sentinels the answer is wrapped in. They are deliberately unlikely to
#: occur in a person's own output and are matched as a pair, so text a cell
#: printed earlier in the same request cannot be mistaken for a reply.
_FRAME_START: Final[str] = "<<<scistudio-bridge:"
_FRAME_END: Final[str] = ":scistudio-bridge>>>"
_FRAME_PATTERN: Final[re.Pattern[str]] = re.compile(
    re.escape(_FRAME_START) + r"([A-Za-z0-9+/=]*)" + re.escape(_FRAME_END)
)

INSTALL_PROBE: Final[str] = "install"
"""The action the service sends at kernel start to install the bridge (FR-009)."""

BLOCKS_NAME: Final[str] = BLOCK_CALL_PATHS[0][0]
"""The name a cell calls a block through: ``blocks``, as in ``blocks.run(...)``.

Read out of the analysis's own
:data:`~scistudio.explore.dependency_analysis.BLOCK_CALL_PATHS` rather than
spelled a second time here. The analysis matches that dotted path to decide a
cell contains a block call, and this module binds the name it resolves to. A
constant written in two places is one that ends up saying two different things,
and this particular disagreement would be silent — the graph recording calls to
a name nothing binds.
"""

#: Names the interactive shell puts in the user namespace itself. None of them
#: is a notebook variable, so none of them is fingerprinted, listed as a
#: binding, or offered as a window. ``_``, ``__`` and ``___`` are IPython's
#: output history; ``_i*`` and ``_oh`` and friends are its input history.
_SHELL_NAMES: Final[frozenset[str]] = frozenset(
    {
        "In",
        "Out",
        "exit",
        "quit",
        "get_ipython",
        "open",
        "_",
        "__",
        "___",
        "_i",
        "_ii",
        "_iii",
        "_dh",
        "_ih",
        "_oh",
        "_sh",
        "_exit_code",
    }
)

#: IPython's numbered history entries: ``_1``, ``_i1``, ``_12``.
_HISTORY_PATTERN: Final[re.Pattern[str]] = re.compile(r"^_i?\d+$")

#: Characters one binding's summary may occupy. See :func:`_summarise`.
_SUMMARY_LIMIT: Final[int] = 80


# ---------------------------------------------------------------------------
# Errors and result types
# ---------------------------------------------------------------------------


@provisional(since="0.3.4")
class BridgeError(RuntimeError):
    """Raised when a bridge call failed inside the kernel.

    The message carries the kernel-side exception's type and text, because the
    call itself left no cell and no traceback a person could look at.
    """


@provisional(since="0.3.4")
class BridgeProtocolError(BridgeError):
    """Raised when a bridge call produced no readable answer.

    Either the reply frame was missing — which is what a kernel that could not
    import ``scistudio`` looks like — or it announced a protocol version this
    driver does not speak.
    """


@provisional(since="0.3.4")
@dataclass(frozen=True)
class Binding:
    """One top-level name in the kernel namespace, with its type (FR-009)."""

    name: str
    """The name as it is bound in the namespace."""

    type_name: str
    """The **SciStudio** type of the object, or :attr:`native_type_name` when it has none.

    FR-038 types a packaged port by "the SciStudio type of the object bound to
    that name at packaging", and this is where that answer comes from: the
    bridge is the only side that holds the object, so it is the only side that
    can wrap it (:func:`scistudio_type_name`). A value no rule covers — an
    ``int``, a dictionary, a person's own class — keeps its native name here,
    because a name that packaging cannot resolve is better than a guess that
    fails later at the exchange layer.
    """

    native_type_name: str
    """``type(value).__name__``, kept whole for the bindings panel.

    ``x = "hello"`` is a ``str`` to the person reading their namespace and a
    ``Text`` to packaging, and both readings are true. This field is the
    person's one.
    """

    type_module: str
    """The module the *native* type came from, so ``DataFrame`` says which one it is."""

    summary: str
    """A short, bounded description — a length, a shape, or the native type name."""


# ---------------------------------------------------------------------------
# The kernel side
# ---------------------------------------------------------------------------


@provisional(since="0.3.4")
def fingerprints(namespace: Mapping[str, Any]) -> dict[str, Fingerprint]:
    """Fingerprint every top-level name in *namespace* (FR-009, FR-021).

    Uses :func:`scistudio.explore.fingerprint.fingerprint` — the function of the
    dependency-analysis spec — so the observation the session compares is the
    one that spec defines. Names the interactive shell injected are skipped.

    A name whose value cannot be fingerprinted at all (a ``__getattr__`` that
    raises, a proxy that dies when it is read) comes back with
    ``observable=False`` and an empty digest rather than failing the whole
    call: ``observable=False`` already means "equality proves nothing about
    this name", which is exactly the truth about it.

    Args:
        namespace: The kernel's user namespace.

    Returns:
        One :class:`~scistudio.explore.fingerprint.Fingerprint` per visible name.
    """
    result: dict[str, Fingerprint] = {}
    for name, value in list(namespace.items()):
        if _is_hidden(name, value):
            continue
        try:
            result[name] = fingerprint(value)
        except Exception:  # a value that cannot even be read is not observable
            result[name] = Fingerprint(digest="", observable=False, type_name=_safe_type_name(value))
    return result


@provisional(since="0.3.4")
def scistudio_type_name(value: object) -> str | None:
    """The name of the SciStudio type *value* would be wrapped into, or ``None`` (FR-009, FR-038).

    Packaging types every port by "the SciStudio type of the object bound to
    that name at packaging" (FR-038), and only this side of the bridge holds
    the object. Answering with ``type(value).__name__`` instead would hand
    packaging a *native* name — ``str``, ``ndarray`` — that resolves against
    nothing, and the person would be told their port "is bound to nothing in
    the kernel" when what is missing is the translation.

    The rules are :func:`~scistudio.explore.notebook_api.wrap_native`'s, and
    this answers *which* type without building one: a bindings list is drawn on
    every namespace change, and ``wrap_native`` on a pandas frame converts it to
    an Arrow table, which is a copy of the person's data per redraw. The two
    are pinned to each other by a test rather than left to drift.

    Args:
        value: The live object.

    Returns:
        The SciStudio type name, or ``None`` when no rule covers *value* — an
        ``int``, a dictionary, a person's own class. ``None`` is the honest
        answer: a port of that type cannot be materialised, and saying so at
        packaging beats failing at the exchange layer.
    """
    from pathlib import Path

    from scistudio.core.types.base import DataObject

    if isinstance(value, DataObject):
        return type(value).__name__
    if isinstance(value, str):
        return "Text"
    if isinstance(value, Path):
        return "Artifact"

    # pandas, pyarrow and numpy are consulted only when they are already
    # imported: an object cannot be a DataFrame if pandas was never imported,
    # so this is a ``sys.modules`` lookup rather than an import cost paid on
    # every redraw of the bindings list. The discipline is ``wrap_native``'s.
    pandas = sys.modules.get("pandas")
    if pandas is not None:
        if isinstance(value, pandas.DataFrame):
            return "DataFrame"
        if isinstance(value, pandas.Series):
            return "Series"
    arrow = sys.modules.get("pyarrow")
    if arrow is not None and isinstance(value, arrow.Table):
        return "DataFrame"
    numpy = sys.modules.get("numpy")
    if numpy is not None and isinstance(value, numpy.ndarray):
        return "Array"
    return None


def _safe_scistudio_type_name(value: object) -> str | None:
    """:func:`scistudio_type_name`, without trusting the object to survive an ``isinstance``.

    A metaclass with a hostile ``__instancecheck__`` is a value in somebody's
    namespace, not a reason for the whole bindings list to fail.
    """
    try:
        return scistudio_type_name(value)
    except Exception:  # pragma: no cover - a value that will not answer isinstance
        return None


@provisional(since="0.3.4")
def bindings(namespace: Mapping[str, Any]) -> list[Binding]:
    """List the top-level bindings with their type names (FR-009).

    Each binding carries both readings of "type": the SciStudio type packaging
    needs (FR-038) and the native one the person sees in their own namespace.
    See :class:`Binding` and :func:`scistudio_type_name`.

    Args:
        namespace: The kernel's user namespace.

    Returns:
        One :class:`Binding` per visible name, sorted by name so a panel
        re-rendering the list does not see it reorder.
    """
    listed: list[Binding] = []
    for name, value in list(namespace.items()):
        if _is_hidden(name, value):
            continue
        value_type = type(value)
        native = _safe_type_name(value)
        listed.append(
            Binding(
                name=name,
                type_name=_safe_scistudio_type_name(value) or native,
                native_type_name=native,
                type_module=getattr(value_type, "__module__", "") or "",
                summary=_summarise(value),
            )
        )
    return sorted(listed, key=lambda binding: binding.name)


@provisional(since="0.3.4")
def memory_bytes() -> int | None:
    """Resident memory of this kernel process, read from inside it (FR-009).

    FR-009 lists memory among the things the bridge answers. Note that the
    kernel *list* of FR-016 does not read it this way:
    :meth:`~scistudio.explore.kernel.KernelHandle.memory_bytes` reads the
    process from outside with ``psutil`` precisely so the list can answer while
    every kernel in it is stuck in a long cell, which a bridge call cannot do
    (ADR-054 §6.3, the shallow freeze). This one exists for a caller that wants
    the figure the kernel itself sees.

    Returns:
        Resident set size in bytes, or ``None`` when it cannot be read.
    """
    try:
        import psutil
    except ImportError:
        return None
    try:
        return int(psutil.Process().memory_info().rss)
    except Exception:
        return None


@provisional(since="0.3.4")
def environment_snapshot() -> dict[str, Any]:
    """Capture this kernel's environment as a snapshot dict (FR-012, FR-034).

    Captured *inside* the kernel deliberately: the kernel is a separate
    interpreter from the service, ``%pip`` installs into the kernel's
    environment, and a freeze taken in the service would describe the wrong
    one. The reference the session records comes from
    :meth:`~scistudio.core.lineage.environment.EnvironmentSnapshot.reference`,
    and the snapshot is stored once per distinct environment by
    :class:`~scistudio.core.lineage.environment.EnvironmentSnapshotStore`.

    Returns:
        The snapshot as :meth:`EnvironmentSnapshot.to_dict` renders it.
    """
    from scistudio.core.lineage.environment import EnvironmentSnapshot

    return EnvironmentSnapshot.capture(executable=sys.executable).to_dict()


@provisional(since="0.3.4")
def variable_window(
    namespace: Mapping[str, Any],
    name: str,
    *,
    query: Mapping[str, Any] | None = None,
    project_dir: str | None = None,
) -> dict[str, Any]:
    """Render a windowed read of one named variable (FR-009, T-010).

    Wraps the live object into its SciStudio type by construction from data and
    runs the existing preview provider for that type, so this is the same code
    that renders the same object in the workflow preview.

    Args:
        namespace: The kernel's user namespace.
        name: The variable to window.
        query: Preview query state — page, page size, sort, slice index — as
            the preview session manager understands it.
        project_dir: The project whose project-tier previewers should be
            consulted, so a project's own previewer wins here as it does
            everywhere else.

    Returns:
        The preview envelope as a JSON-safe dict.

    Raises:
        KeyError: *name* is not bound in the namespace.
    """
    import tempfile
    from pathlib import Path

    from scistudio.previewers import get_preview_service

    if name not in namespace or _is_hidden(name, namespace[name]):
        msg = f"{name!r} is not a variable in this kernel."
        raise KeyError(msg)

    from scistudio.explore.notebook_api import wrap_native

    data_object = wrap_native(namespace[name])
    service = get_preview_service(project_dir=Path(project_dir) if project_dir else None)
    target_kind = _target_kind(data_object)

    existing = getattr(data_object, "storage_ref", None)
    if existing is not None:
        return _render(service, data_object, existing, target_kind, query)
    with tempfile.TemporaryDirectory(prefix="scistudio-window-") as staging:
        destination = Path(staging) / (name + _staging_suffix(data_object))
        storage_ref = _persist_without_mutating(data_object, destination)
        return _render(service, data_object, storage_ref, target_kind, query)


def _render(
    service: Any,
    data_object: Any,
    storage_ref: Any,
    target_kind: Any,
    query: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Run the routed preview provider over *storage_ref* and return its envelope."""
    from scistudio.previewers.models import PreviewTarget

    chain = _type_chain(type(data_object))
    target = PreviewTarget(
        kind=target_kind,
        ref=storage_ref.path,
        recorded_type=chain[-1] if chain else "DataObject",
        type_chain=chain,
    )
    request_query: dict[str, Any] = dict(query or {})
    request_query["_storage"] = {
        "backend": storage_ref.backend,
        "path": storage_ref.path,
        "format": storage_ref.format,
        "metadata": storage_ref.metadata,
    }
    envelope = service.sessions.render_target(target, request_query)
    return dict(envelope.to_dict())


#: The extension each storage backend's files are read back by. The preview
#: data access decides a table's format from the *path's suffix*
#: (``scistudio.previewers._table_cache``), so a staged file written without
#: one is read as CSV whatever it holds, and the window comes back as a parse
#: error. Naming the staged file after the backend that wrote it is what makes
#: a window of a live object identical to a window of a stored one.
_BACKEND_SUFFIX: Final[Mapping[str, str]] = {"arrow": ".parquet", "zarr": ".zarr"}


def _staging_suffix(data_object: Any) -> str:
    """The extension a staged copy of *data_object* must carry."""
    from scistudio.core.storage.backend_router import get_router

    backend_name, _backend = get_router().resolve(type(data_object))
    if backend_name in _BACKEND_SUFFIX:
        return _BACKEND_SUFFIX[backend_name]
    # A filesystem-backed object (Text, Artifact) is read by its own extension,
    # so keep the one it already has and fall back to none.
    file_path = getattr(data_object, "file_path", None)
    return "".join(getattr(file_path, "suffixes", []) or [])


def _persist_without_mutating(data_object: Any, destination: Any) -> Any:
    """Write *data_object*'s data to *destination* without touching the object.

    :meth:`~scistudio.core.types.base.DataObject.save` records the reference it
    wrote on the object. Here that would be wrong twice over: the object is the
    one the person's variable is bound to, and the file is a scratch one this
    call deletes, so their variable would be left pointing at a path that no
    longer exists. This does the same three steps and keeps the reference to
    itself.
    """
    from scistudio.core.storage.backend_router import get_router
    from scistudio.core.storage.ref import StorageReference

    backend_name, backend = get_router().resolve(type(data_object))
    data = data_object.get_in_memory_data()
    return backend.write(data, StorageReference(backend=backend_name, path=str(destination)))


def _target_kind(data_object: Any) -> Any:
    """Which preview target kind covers *data_object*."""
    from scistudio.core.types.artifact import Artifact
    from scistudio.core.types.collection import Collection
    from scistudio.previewers.models import TargetKind

    if isinstance(data_object, Collection):
        return TargetKind.COLLECTION_REF
    if isinstance(data_object, Artifact):
        return TargetKind.ARTIFACT
    return TargetKind.DATA_REF


def _type_chain(data_type: type) -> tuple[str, ...]:
    """The recorded type chain, general to specific, that the router walks."""
    from scistudio.core.types.base import DataObject

    chain = [base.__name__ for base in data_type.__mro__ if issubclass(base, DataObject)]
    return tuple(reversed(chain))


@provisional(since="0.3.4")
def cell_installs_packages(source: str) -> bool:
    """Whether *source* installs something into the kernel's environment (FR-012).

    FR-012 names three spellings — ``%pip``, ``!pip``, and ``%conda`` — and this
    matches those three at the start of a line, ignoring indentation. It is a
    text check on purpose: an install line is a magic or a shell escape, so it
    is not valid Python and never reaches the AST the analysis parses.

    Args:
        source: A cell's source.

    Returns:
        ``True`` when the cell contains an install line, so the session should
        re-snapshot the environment after it runs.

    Example:
        >>> cell_installs_packages("import numpy as np\\n%pip install scikit-image")
        True
        >>> cell_installs_packages("df = pipeline(df)  # %pip is only a comment here")
        False
    """
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        for marker in ("%pip", "!pip", "%conda"):
            if stripped == marker or stripped.startswith(marker + " "):
                return True
    return False


@provisional(since="0.3.4")
def session_kernel_env(mode: str = "session") -> dict[str, str]:
    """The environment variables a kernel launched for a session needs (FR-010).

    The session service passes this to
    :class:`~scistudio.explore.kernel.KernelHandle`'s ``env``. It is one
    function rather than a literal at the call site so that the mode variable
    is set in one place and the helpers' contract cannot drift from the
    launcher's.

    Args:
        mode: The notebook mode to select. Defaults to session mode.

    Returns:
        The environment delta to launch with.
    """
    from scistudio.explore.notebook_api import MODE_ENV_VAR

    return {MODE_ENV_VAR: mode}


# ---------------------------------------------------------------------------
# Calling a block from outside the kernel (FR-049, FR-051)
# ---------------------------------------------------------------------------

#: The adapter this kernel's block calls go through. Built on first use with a
#: freshly scanned registry, which is correct but slow; a session that already
#: holds a scanned registry, or a test that holds a hand-made one, installs it
#: with :func:`set_block_call_adapter`. It is process state because a kernel
#: serves one session (FR-001), which is the same reason the notebook helpers
#: keep their binding in a module global.
_ADAPTER: Any = None


@provisional(since="0.3.4")
def set_block_call_adapter(adapter: Any) -> None:
    """Install the :class:`~scistudio.explore.block_call.BlockCallAdapter` to use.

    Called *inside the kernel* — a registry and an interaction channel are
    objects and cannot cross the bridge frame, so the adapter has to be built
    on this side. Passing ``None`` drops the installed adapter and the next
    call builds a default one.

    An adapter installed this way must be built with
    ``on_call=record_block_call_lineage`` if its calls are to reach the
    session's lineage (FR-051). The default adapter :func:`block_call_adapter`
    builds carries the hook; one handed in here carries whatever its builder
    gave it, and this deliberately does not reach into it to attach one — an
    adapter is somebody else's object.

    Args:
        adapter: The adapter to use, or ``None`` to reset.
    """
    global _ADAPTER
    _ADAPTER = adapter


@provisional(since="0.3.4")
def block_call_adapter(session_id: str | None = None) -> Any:
    """The installed adapter, building a default one on first use.

    The default adapter is built with
    :func:`record_block_call_lineage` as its ``on_call`` hook, so every call it
    makes — a cell's ``blocks.run(...)`` included — buffers its lineage for the
    service to drain and write (FR-051).

    Args:
        session_id: Carried into the lineage of every call this default adapter
            makes (FR-051). Ignored when an adapter is already installed, whose
            own session id stands.

    The default carries **no interaction channel**, so an interactive block
    called through it is refused rather than silently run unattended.

    TODO(#2250): pass an ``interaction=`` channel here once one exists, so
      FR-050's "opens its panel through the session service" is met rather than
      refused. Nothing in ``src/`` implements
      :class:`~scistudio.explore.block_call.InteractionChannel` today.
      Out of scope per the #2240 audit fix pass: it needs a stdin-channel
      transport, an FR-057 event type, and an FR-056 route. The protocol's own
      marker explains why each is more than a call site.
      Followup: https://github.com/jiazhenz026/SciStudio/issues/2250

    Returns:
        The :class:`~scistudio.explore.block_call.BlockCallAdapter`.
    """
    global _ADAPTER
    if _ADAPTER is None:
        from scistudio.explore.block_call import BlockCallAdapter

        _ADAPTER = BlockCallAdapter(session_id=session_id, on_call=record_block_call_lineage)
    return _ADAPTER


@provisional(since="0.3.4")
class NotebookBlocks:
    """The ``blocks`` name a cell calls (FR-049).

    Bound into the kernel's user namespace at bridge install, so that::

        peaks = blocks.run("imaging.find_peaks", img=img, sigma=2.0)

    is a line a cell can actually run. The name is the one the dependency
    analysis matches — :data:`BLOCKS_NAME` is read out of
    :data:`~scistudio.explore.dependency_analysis.BLOCK_CALL_PATHS` rather than
    written twice — so what the graph records as a block call and what the
    kernel resolves cannot drift apart.

    It holds no adapter of its own and resolves one per call. That is what
    keeps kernel start cheap: a default
    :class:`~scistudio.explore.block_call.BlockCallAdapter` scans the whole
    block registry, and paying for that at install would put it in front of the
    person's first cell. It also means a session that installs its own adapter
    with :func:`set_block_call_adapter` — with its registry already scanned and
    its interaction channel attached, which is what an interactive block called
    from a cell needs (FR-050) — takes effect for calls made after it, without
    rebinding anything in the namespace.
    """

    __slots__ = ()

    @provisional(since="0.3.4")
    def run(self, identifier: str, /, **kwargs: Any) -> Any:
        """Run a block and return its result as a native object (FR-049).

        Args:
            identifier: The block's display name or stable type name.
            **kwargs: The block's inputs and configuration, mixed; the adapter
                splits them by the block's own declared port names.

        Returns:
            The single output port's native value, or a mapping of port name to
            native value when the block declares a number of outputs other than
            one.

        Raises:
            BlockCallError: Any of the adapter's failures — block not found, a
                port violated, the block raised, an interactive call cancelled,
                or an interactive block with no channel to open a panel on.
        """
        return block_call_adapter().call(identifier, **kwargs)

    def __repr__(self) -> str:
        """Describe the name rather than the object, since a cell may print it."""
        return "<scistudio blocks: call blocks.run('<block identifier>', ...)>"


#: The object bound into the namespace, held so that :func:`_is_hidden` can ask
#: whether the ``blocks`` name still refers to *ours*. ``None`` until an install
#: has run in this process.
_INJECTED_BLOCKS: NotebookBlocks | None = None


@provisional(since="0.3.4")
def notebook_blocks() -> NotebookBlocks:
    """The process's :class:`NotebookBlocks`, created on first use (FR-049).

    One object per process, shared by the bare ``blocks`` name a session kernel
    is given and by ``scistudio.blocks``, which is how a notebook reaches the
    same surface in **both** modes: the bare name is bound by the bridge and so
    exists only in a session, while the attribute goes through the top-level
    package and therefore exists in a packaged nbconvert run too.

    That difference is the whole reason the attribute spelling is the one the
    generated first cell binds. The dependency analysis reads *source*: a cell
    writing ``blocks.run(...)`` against a name nothing above it binds is an
    unresolved read, and packaging refuses a notebook that has one (FR-039) —
    so FR-049's affordance and FR-039's refusal would be mutually exclusive.
    Binding ``blocks = scistudio.blocks`` in the first cell resolves the read
    *and* carries the name into the packaged copy, because packaging's backward
    slice keeps the cell that binds it.
    """
    global _INJECTED_BLOCKS
    if _INJECTED_BLOCKS is None:
        _INJECTED_BLOCKS = NotebookBlocks()
    return _INJECTED_BLOCKS


def _inject_blocks(namespace: dict[str, Any]) -> str:
    """Bind :data:`BLOCKS_NAME` in *namespace* and return the name bound."""
    namespace[BLOCKS_NAME] = notebook_blocks()
    return BLOCKS_NAME


def _block_call(namespace: dict[str, Any], payload: Mapping[str, Any]) -> dict[str, Any]:
    """Run a block in this kernel on a caller's behalf (FR-049, FR-051).

    The values never cross the frame in either direction, which is the whole
    shape of this action: inputs are named by the kernel variable that holds
    them, outputs are bound back into the kernel by name, and what comes back
    is a description. A cell that wants the value itself calls
    ``blocks.run(...)`` and gets the object, which is
    :meth:`BlockCallAdapter.call`'s job, not this one's.

    Args:
        namespace: The kernel's user namespace.
        payload: ``identifier``, plus ``inputs`` mapping each port to the name
            of the variable holding its value, ``config``, ``session_id``, and
            ``bind`` — either one name for a single-output block or a mapping
            of port name to variable name.

    Returns:
        The names bound, the output type names, and the call's lineage facts.

    Raises:
        KeyError: An input names a variable this kernel does not have.
        ValueError: ``bind`` is a single name and the block has more than one
            output port, so which one it meant is not knowable.
    """
    identifier = str(payload["identifier"])
    inputs = {
        str(port): _named_value(namespace, str(variable)) for port, variable in (payload.get("inputs") or {}).items()
    }
    adapter = block_call_adapter(payload.get("session_id"))
    result = adapter.call_detailed(identifier, inputs=inputs, config=dict(payload.get("config") or {}))
    return {
        "identifier": identifier,
        "bound": _bind_outputs(namespace, result.outputs, payload.get("bind")),
        "outputs": {port: _safe_type_name(value) for port, value in result.outputs.items()},
        "lineage": _lineage_payload(result.lineage),
    }


def _named_value(namespace: dict[str, Any], variable: str) -> Any:
    """The value bound to *variable*, refusing a name the kernel does not have."""
    if variable not in namespace or _is_hidden(variable, namespace.get(variable)):
        msg = f"{variable!r} is not a variable in this kernel, so it cannot be an input to a block call."
        raise KeyError(msg)
    return namespace[variable]


def _bind_outputs(namespace: dict[str, Any], outputs: Mapping[str, Any], bind: Any) -> dict[str, str]:
    """Bind the call's outputs into the kernel namespace as *bind* asks.

    Returns the port-to-variable mapping actually bound, which is empty when
    the caller asked for nothing — a call made only for its lineage.
    """
    if bind is None:
        return {}
    if isinstance(bind, str):
        if len(outputs) != 1:
            msg = (
                f"bind={bind!r} names one variable but the block produced {len(outputs)} outputs "
                f"({', '.join(sorted(outputs)) or 'none'}); pass a mapping of port name to variable name."
            )
            raise ValueError(msg)
        port = next(iter(outputs))
        namespace[bind] = outputs[port]
        return {port: bind}
    bound: dict[str, str] = {}
    for port, variable in dict(bind).items():
        if str(port) not in outputs:
            msg = f"bind names the output port {port!r}, which this block does not produce."
            raise ValueError(msg)
        namespace[str(variable)] = outputs[str(port)]
        bound[str(port)] = str(variable)
    return bound


#: Lineage for the block calls this kernel has made since the service last
#: drained it (FR-051). Process state for the same reason the adapter is: a
#: kernel serves one session.
#:
#: A buffer rather than a direct write because the store is on the *other* side
#: of the kernel boundary. The adapter fires its ``on_call`` hook inside this
#: process, where there is no lineage store and no way to reach one; the
#: service drains this after every cell run and writes the rows.
_BLOCK_CALL_LINEAGE: list[dict[str, Any]] = []


@provisional(since="0.3.4")
def record_block_call_lineage(lineage: Any) -> None:
    """Buffer one block call's lineage for the service to drain (FR-051).

    This is the ``on_call`` hook :func:`block_call_adapter` installs, and it is
    the hook rather than a wrapper around either door on purpose. **The path a
    person actually uses is the inline one** — a cell writing
    ``blocks.run("imaging.find_peaks", img=img)`` — which never reaches
    :meth:`KernelBridge.block_call`; a drain that only covered the bridge's own
    action would satisfy FR-051 on paper and leave every real call unrecorded.
    The hook covers both doors, and it covers the call that *raised*: the
    adapter fires it from ``finish()`` before the exception propagates, so a
    block that failed still writes a record with ``termination="error"``, which
    is what FR-051 asks for and what a wrapper around a raising call could not
    give.

    Never raises. A lineage buffer that could break a cell would be a provenance
    feature that costs people their work.

    Args:
        lineage: The :class:`~scistudio.explore.block_call.BlockCallLineage` the
            adapter built for the call.
    """
    try:
        payload = _lineage_payload(lineage)
    except Exception:  # pragma: no cover - a lineage that will not render
        return
    if payload is not None:
        _BLOCK_CALL_LINEAGE.append(payload)
    _remember_declarable(lineage)


@provisional(since="0.3.4")
def drain_block_calls() -> list[dict[str, Any]]:
    """Take and clear the buffered block-call lineage (FR-051).

    Draining rather than reading, because every call must be written exactly
    once: the service records what comes back, and a second drain of the same
    call would be a second ``BlockExecutionRecord`` for one execution.

    Returns:
        One payload per call since the last drain, in the order the calls were
        made.
    """
    drained = list(_BLOCK_CALL_LINEAGE)
    _BLOCK_CALL_LINEAGE.clear()
    return drained


#: Identity map from a value a block call handed a cell back to the object it
#: came from: ``id(native) -> (getter, object_id, type_name)`` (FR-055).
#:
#: ``blocks.run(...)`` returns a **native** — a ``str``, an ``ndarray`` — so the
#: value a notebook goes on to name in ``scistudio.output`` carries no object
#: identity, while the row retention decides over is the ``DataObject`` the call
#: produced. This is the only place both are in hand.
#:
#: The entry is a *getter*, not the value, because this map must not be the
#: reason a person's memory does not come back. A cell that calls a block a
#: hundred times produces a hundred results, and holding each one would keep
#: every array alive for the life of the kernel even after the cell rebound the
#: name — in a tool that reports kernel memory per session, that is the wrong
#: kind of bug to introduce for a provenance hint. So the getter is a
#: :class:`weakref.ref` wherever the type supports one, which covers every large
#: object (arrays, frames, data objects), and a plain closure over the value for
#: the types that do not (``str``, ``int``, ``bytes``, ``tuple``) — exactly the
#: small immutables where holding on costs nothing.
#:
#: The reference also disambiguates the key: a dead object's ``id`` can be
#: reused by the next allocation, so a hit is confirmed with ``is`` and a
#: weakref that has expired is dropped rather than trusted.
_DECLARABLE_BY_ID: dict[int, tuple[Callable[[], Any], str, str]] = {}


def _remember_declarable(lineage: Any) -> None:
    """Record the natives one call's outputs unwrap to (FR-055). Never raises.

    Inputs are skipped: an object a cell *passed* to a block was not produced by
    the session and is not what FR-055 makes durable.
    """
    try:
        import weakref

        from scistudio.explore.block_call import native_of

        _prune_declarable()
        for edge in getattr(lineage, "edges", ()) or ():
            if getattr(edge, "direction", "") != "output":
                continue
            object_id = getattr(edge, "object_id", "")
            data_object = getattr(edge, "data_object", None)
            if not object_id or data_object is None:
                continue
            native = native_of(data_object)
            try:
                getter: Callable[[], Any] = weakref.ref(native)
            except TypeError:  # a small immutable; holding it costs nothing
                getter = _constant(native)
            _DECLARABLE_BY_ID[id(native)] = (getter, str(object_id), str(getattr(edge, "type_name", "") or ""))
    except Exception:  # pragma: no cover - a durability hint must never break a cell
        return


def _constant(value: Any) -> Callable[[], Any]:
    """A getter for a value that cannot be weakly referenced."""
    return lambda: value


def _prune_declarable() -> None:
    """Drop entries whose object is gone, so a stale ``id`` cannot be matched."""
    for key in [key for key, (getter, _, _) in _DECLARABLE_BY_ID.items() if getter() is None]:
        _DECLARABLE_BY_ID.pop(key, None)


def _declarable_for(value: Any) -> tuple[str, str] | None:
    """``(object_id, type_name)`` for *value*, when a block call produced it.

    Identity, not equality: two arrays with the same contents are two objects,
    and only the one a call actually produced has a row in the catalog.
    """
    found = _DECLARABLE_BY_ID.get(id(value))
    if found is None:
        return None
    getter, object_id, type_name = found
    return (object_id, type_name) if getter() is value else None


def _declared_output_payload(declared: Any) -> dict[str, Any]:
    """One ``scistudio.output`` declaration as the frame can carry it (FR-055).

    The name and the type were always here. ``object_id`` and ``data_object``
    are what make the declaration *durable* rather than merely recorded: FR-055
    says an object named in ``scistudio.output`` must be kept while everything
    else a session produced is a reclaim candidate, and the retention planner
    decides that over rows in ``data_objects``. Without the object's identity
    crossing the frame there is nothing to join the name to, which is why the
    durable set was empty at runtime however many declarations a notebook made.

    The envelope is built with the same :func:`_data_object_payload` a block
    call's edges use, so a declared object and an object a call produced are the
    same row in the catalog.

    Two ways the identity is found, because a notebook reaches an object by two
    routes. A cell holding a ``DataObject`` outright carries its identity on the
    object. A cell that wrote ``x = blocks.run(...)`` holds a **native** —
    ``blocks.run`` unwraps on the way out — and that value has no identity of
    its own, so it is looked up in :data:`_DECLARABLE_BY_ID`, which the lineage
    hook fills at the moment both forms are in hand. The second route is the one
    that matters: it is how the objects FR-055 exists to protect are produced.

    A declared value that is neither — a plain int a cell computed — carries no
    identity. That is not a gap: retention decides over rows in
    ``data_objects``, and a value that was never stored was never a reclaim
    candidate either.
    """
    payload: dict[str, Any] = {"name": declared.name, "type_name": declared.type_name}
    value = getattr(declared, "value", None)
    framework = getattr(value, "framework", None)
    object_id = getattr(framework, "object_id", None)
    if isinstance(object_id, str) and object_id:
        payload["object_id"] = object_id
        payload["data_object"] = _data_object_payload(value)
        return payload
    from_call = _declarable_for(value)
    if from_call is not None:
        payload["object_id"], payload["type_name"] = from_call
    return payload


def _data_object_payload(data_object: Any) -> dict[str, Any] | None:
    """Serialise one edge's data object into the envelope a lineage row stores.

    FR-051 records a call's inputs and outputs "as they are for a workflow
    run", and what a workflow run stores in ``data_objects.wire_payload`` is the
    reference-only envelope :func:`scistudio.core.types.serialization._serialise_one`
    writes. Using the same function is the point: an object a cell passed to a
    block and an object a workflow step passed to one are the same object in
    the catalog, reconstructable the same way.

    The object itself still cannot cross the frame — it lives in this process —
    but its envelope is exactly the reference the row wants, so this is not a
    lossy substitute for it.

    Returns:
        The envelope, or ``None`` for an object that cannot be serialised. A
        row with an empty payload still carries the object's identity and type,
        which is enough for the edge; refusing the whole call over one
        unserialisable port would lose more.
    """
    if data_object is None:
        return None
    try:
        from scistudio.core.types.serialization import _serialise_one

        return _serialise_one(data_object)
    except Exception:  # an object with no envelope is still an edge
        return None


def _lineage_payload(lineage: Any) -> dict[str, Any] | None:
    """Render :class:`BlockCallLineage` into something the frame can carry.

    Every field of a ``BlockExecutionRecord`` survives, and each edge carries
    its data object's *wire envelope* rather than the object: the object exists
    only in this process, but the envelope is precisely what a ``data_objects``
    row stores, so the service can build the same row a workflow run would
    (:func:`_data_object_payload`).
    """
    if lineage is None:
        return None
    return {
        "session_id": lineage.session_id,
        "block_identifier": lineage.block_identifier,
        "block_type": lineage.block_type,
        "block_version": lineage.block_version,
        "block_config_resolved": dict(lineage.block_config_resolved),
        "started_at": lineage.started_at,
        "finished_at": lineage.finished_at,
        "duration_ms": lineage.duration_ms,
        "termination": lineage.termination,
        "termination_detail": lineage.termination_detail,
        "interactive": lineage.interactive,
        "interactive_response": lineage.interactive_response,
        "edges": [
            {
                "direction": edge.direction,
                "port_name": edge.port_name,
                "object_id": edge.object_id,
                "position": edge.position,
                "type_name": edge.type_name,
                "data_object": _data_object_payload(edge.data_object),
            }
            for edge in lineage.edges
        ],
    }


#: Sentinel for :func:`_is_hidden`'s optional value, so that ``None`` — a
#: perfectly ordinary thing for a name to be bound to — is not mistaken for
#: "no value was passed".
_NO_VALUE: Final[object] = object()


def _is_hidden(name: str, value: object = _NO_VALUE) -> bool:
    """Whether *name* is the interpreter's or ours, rather than the notebook's.

    Three groups are hidden: dunders, the names the interactive shell injects,
    and its numbered history. All three are decided by the name alone.

    :data:`BLOCKS_NAME` is the fourth and is decided by the *value*, because a
    cell may rebind it. While ``blocks`` still holds the object the bridge
    injected it is not a notebook variable — the person did not put it there,
    so it is not fingerprinted, not listed as a binding, and not offered as a
    window. The moment a cell writes ``blocks = something``, their assignment
    wins: the namespace is theirs, Jupyter's semantics are that a cell binds
    what it binds, and the name now holds a value they created, so it stops
    being hidden and shows up like any other variable they made. The cost of
    that is their own — ``blocks.run`` no longer reaches a block — and it is
    the same cost as shadowing ``list`` or ``id``.

    Args:
        name: The name as it is bound in the namespace.
        value: What it is bound to. Omit it to ask about the name alone, which
            answers for the first three groups and never hides ``blocks``.

    Returns:
        Whether the name should be left out of what the session reports.
    """
    if name.startswith("__") and name.endswith("__"):
        return True
    if name in _SHELL_NAMES:
        return True
    if name == BLOCKS_NAME and value is not _NO_VALUE:
        return _INJECTED_BLOCKS is not None and value is _INJECTED_BLOCKS
    return bool(_HISTORY_PATTERN.match(name))


def _safe_type_name(value: object) -> str:
    """``type(value).__name__``, without trusting the object to answer."""
    try:
        return type(value).__name__
    except Exception:  # pragma: no cover - a type that will not name itself
        return "?"


def _summarise(value: object) -> str:
    """A short, bounded description of *value* for the bindings list.

    Never ``repr``: a binding list is drawn on every namespace change, and a
    ``repr`` can be a megabyte, can run arbitrary code, and can raise. Shape
    and length are what a person actually reads off that list anyway.

    Bounded at :data:`_SUMMARY_LIMIT` characters, because a number is not
    automatically short: ``value = 2 ** 100_000`` renders thirty thousand
    digits, and one such name would dominate the payload the whole list travels
    in.
    """
    type_name = _safe_type_name(value)
    try:
        shape = getattr(value, "shape", None)
        if isinstance(shape, tuple) and all(isinstance(size, int) for size in shape):
            return f"{type_name}{tuple(shape)}"[:_SUMMARY_LIMIT]
        if isinstance(value, (str, bytes, list, tuple, dict, set, frozenset)):
            return f"{type_name} of {len(value)}"[:_SUMMARY_LIMIT]
        if isinstance(value, (bool, int, float)):
            return f"{type_name} {value}"[:_SUMMARY_LIMIT]
    except Exception:  # an object whose len or shape raises describes itself as its type
        return type_name
    return type_name[:_SUMMARY_LIMIT]


def _dispatch(namespace: dict[str, Any], request: str) -> None:
    """Run one bridge request and print its framed answer (FR-009).

    This is the function a bridge call executes, and the only kernel-side entry
    point :class:`KernelBridge` names. It is private because the *protocol* is
    private: a notebook calls the helpers, a panel calls the service, and
    nothing calls this except the driver below.

    It never raises. A failure is an answer with ``ok`` false, because a raised
    exception inside a silent request produces a traceback the person cannot
    see and leaves the driver with nothing to report.

    Args:
        namespace: The kernel's user namespace — ``globals()`` at the call
            site, which is what makes this see the person's variables.
        request: base64 of the request JSON.
    """
    try:
        payload = json.loads(base64.b64decode(request.encode("ascii")).decode("utf-8"))
        response = {"ok": True, "version": BRIDGE_PROTOCOL_VERSION, "result": _handle(namespace, payload)}
    except BaseException as exc:  # every failure must come back as an answer, not a traceback
        response = {
            "ok": False,
            "version": BRIDGE_PROTOCOL_VERSION,
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }
    encoded = base64.b64encode(json.dumps(response, default=str).encode("utf-8")).decode("ascii")
    # stdout is the reply channel: see this module's docstring on execute_silent.
    print(f"{_FRAME_START}{encoded}{_FRAME_END}")


def _handle(namespace: dict[str, Any], payload: Mapping[str, Any]) -> Any:
    """Run one decoded request and return its result."""
    from scistudio.explore import notebook_api

    action = payload.get("action")
    if action == INSTALL_PROBE:
        notebook_api.bind_session(
            notebook_api.SessionBinding(
                inputs=dict(payload.get("inputs") or {}),
                project_dir=payload.get("project_dir"),
                run_id=payload.get("run_id"),
            )
        )
        if payload.get("mode"):
            os.environ[notebook_api.MODE_ENV_VAR] = str(payload["mode"])
        # FR-049's cell-facing surface. Bound here rather than by the session
        # because spec §4.1 makes the bridge what the service injects at kernel
        # start: the session decides when a kernel starts, the bridge decides
        # what is in it.
        return {"python": sys.executable, "pid": os.getpid(), "blocks": _inject_blocks(namespace)}
    if action == "fingerprints":
        return {
            name: {"digest": value.digest, "observable": value.observable, "type_name": value.type_name}
            for name, value in fingerprints(namespace).items()
        }
    if action == "bindings":
        return [
            {
                "name": binding.name,
                "type_name": binding.type_name,
                "native_type_name": binding.native_type_name,
                "type_module": binding.type_module,
                "summary": binding.summary,
            }
            for binding in bindings(namespace)
        ]
    if action == "block_calls":
        return drain_block_calls()
    if action == "memory":
        return memory_bytes()
    if action == "environment":
        return environment_snapshot()
    if action == "declared_outputs":
        return [_declared_output_payload(declared) for declared in notebook_api.declared_outputs()]
    if action == "window":
        return variable_window(
            namespace,
            str(payload["name"]),
            query=payload.get("query"),
            project_dir=payload.get("project_dir"),
        )
    if action == "block_call":
        return _block_call(namespace, payload)
    msg = f"Unknown bridge action: {action!r}."
    raise ValueError(msg)


# ---------------------------------------------------------------------------
# The service side
# ---------------------------------------------------------------------------


@provisional(since="0.3.4")
class KernelBridge:
    """Drives the kernel-side bridge over one :class:`KernelHandle` (FR-009).

    One bridge per session, held beside the handle. Every call runs
    ``silent=True`` with history off, so nothing it does appears as a cell,
    advances the execution counter, or enters the kernel's history — which a
    test in ``tests/explore/test_kernel_bridge.py`` proves against a real
    kernel's message stream rather than against this docstring.

    Bridge calls queue behind a running cell, because the kernel executes one
    request at a time. That is the shallow freeze ADR-054 §6.3 accepts: a panel
    keeps its last window and the read completes when the cell does.

    Example::

        bridge = KernelBridge(handle)
        bridge.install(inputs={"signal": reference})
        before = bridge.fingerprints()
    """

    def __init__(self, handle: KernelHandle, *, timeout: float | None = None) -> None:
        """Wrap *handle*.

        Args:
            handle: The kernel to drive. The bridge never starts, stops, or
                restarts it — the session owns its life.
            timeout: Seconds to wait for a bridge call. ``None`` waits as long
                as the kernel takes, which is the honest default while a long
                cell is running ahead of us.
        """
        self._handle = handle
        self._timeout = timeout

    @property
    def handle(self) -> KernelHandle:
        """The kernel this bridge drives."""
        return self._handle

    def install(
        self,
        *,
        inputs: Mapping[str, str] | None = None,
        project_dir: str | None = None,
        run_id: str | None = None,
        mode: str | None = None,
    ) -> dict[str, Any]:
        """Inject the bridge and its session binding into the kernel (FR-009, FR-010).

        Called once at kernel start and again after a restart. It is also the
        first proof that the kernel can import SciStudio at all: a kernel
        launched from an interpreter that cannot answers with no frame, and
        this raises :class:`BridgeProtocolError` naming that.

        Args:
            inputs: Port name to artefact reference, for ``scistudio.input``.
            project_dir: The session's project, for the project-tier previewers.
            run_id: The run the session was opened over, when it was opened over one.
            mode: Set the notebook mode inside the kernel as well as through
                the launcher's environment. Pass it when the kernel was started
                without :func:`session_kernel_env`.

        Returns:
            The kernel's interpreter path and process id, which is what makes a
            successful install visible in a log.
        """
        payload: dict[str, Any] = {
            "action": INSTALL_PROBE,
            "inputs": dict(inputs or {}),
            "project_dir": project_dir,
            "run_id": run_id,
        }
        if mode is not None:
            payload["mode"] = mode
        return dict(self._call(payload))

    def fingerprints(self) -> dict[str, Fingerprint]:
        """Fingerprint every top-level name in the kernel (FR-009, FR-021)."""
        raw = self._call({"action": "fingerprints"})
        return {
            name: Fingerprint(
                digest=str(entry["digest"]),
                observable=bool(entry["observable"]),
                type_name=str(entry["type_name"]),
            )
            for name, entry in raw.items()
        }

    def bindings(self) -> tuple[Binding, ...]:
        """The top-level bindings with their SciStudio and native type names (FR-009).

        :attr:`Binding.type_name` is the SciStudio type, which is what
        packaging's ports are typed by (FR-038); the native name travels
        alongside it for the panel.
        """
        raw = self._call({"action": "bindings"})
        return tuple(
            Binding(
                name=str(entry["name"]),
                type_name=str(entry["type_name"]),
                native_type_name=str(entry["native_type_name"]),
                type_module=str(entry["type_module"]),
                summary=str(entry["summary"]),
            )
            for entry in raw
        )

    def block_calls(self) -> tuple[dict[str, Any], ...]:
        """Take the block calls this kernel has made since the last drain (FR-051).

        The session calls this after every cell run and writes each payload as a
        ``BlockExecutionRecord`` against itself. It **drains**: a payload comes
        back once, because a call is one execution and a second write of it
        would be a second row for it.

        Each edge carries its data object's wire envelope under
        ``data_object``, which is what a ``data_objects`` row stores, so the
        recorder can build the same row a workflow run would.

        Returns:
            One payload per call, in the order the calls were made. Empty when
            the cell called no block, which is the ordinary case.
        """
        raw = self._call({"action": "block_calls"})
        return tuple(dict(entry) for entry in raw or ())

    def memory_bytes(self) -> int | None:
        """Resident memory the kernel reports for itself (FR-009).

        See :func:`memory_bytes` for why the kernel *list* does not use this.
        """
        raw = self._call({"action": "memory"})
        return int(raw) if raw is not None else None

    def declared_outputs(self) -> tuple[dict[str, Any], ...]:
        """What cells have declared with ``scistudio.output`` (FR-010, FR-055).

        Each entry carries ``name`` and ``type_name``, and — when the declared
        value is a ``DataObject`` — ``object_id`` and the ``data_object``
        envelope a lineage row stores. The identity is the point: FR-055's
        durable set is decided over rows in ``data_objects``, so a declaration
        that crossed the frame as a bare name could not be joined to anything
        and the durable set was empty however many outputs a notebook declared.

        Returns:
            One mapping per declared name, in declaration order.
        """
        raw = self._call({"action": "declared_outputs"})
        return tuple(dict(entry) for entry in raw)

    def environment_snapshot(self) -> Any:
        """Capture the kernel's environment (FR-012, FR-034).

        Returns:
            An :class:`~scistudio.core.lineage.environment.EnvironmentSnapshot`
            describing the kernel's interpreter, not the service's. Store it
            with
            :class:`~scistudio.core.lineage.environment.EnvironmentSnapshotStore`
            and record its
            :meth:`~scistudio.core.lineage.environment.EnvironmentSnapshot.reference`.
        """
        from scistudio.core.lineage.environment import EnvironmentSnapshot

        return EnvironmentSnapshot.from_dict(dict(self._call({"action": "environment"})))

    def window(
        self,
        name: str,
        *,
        query: Mapping[str, Any] | None = None,
        project_dir: str | None = None,
    ) -> dict[str, Any]:
        """Render a windowed read of the variable *name* (FR-009, T-010).

        Args:
            name: The variable to window.
            query: Preview query state (page, page size, sort, slice index).
            project_dir: The project whose previewers should be consulted.

        Returns:
            The preview envelope as a JSON-safe dict, exactly as the same
            provider returns it for the same object in a workflow preview.

        Raises:
            BridgeError: The variable is not bound, or the previewer failed.
        """
        payload: dict[str, Any] = {"action": "window", "name": name}
        if query is not None:
            payload["query"] = dict(query)
        if project_dir is not None:
            payload["project_dir"] = project_dir
        return dict(self._call(payload))

    def block_call(
        self,
        identifier: str,
        *,
        inputs: Mapping[str, str] | None = None,
        config: Mapping[str, Any] | None = None,
        bind: str | Mapping[str, str] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Run a block inside the kernel and leave its results there (FR-049, FR-051).

        The body of the call is
        :class:`~scistudio.explore.block_call.BlockCallAdapter`'s; this is the
        way in from outside the kernel. Values never cross the frame: an input
        is named by the kernel variable holding it and an output is bound back
        into the kernel, so calling a block over a gigabyte array costs one
        JSON message either way.

        A cell that wants the object itself calls ``blocks.run(...)`` and gets
        it, which is the adapter's own surface and does not come through here.

        Args:
            identifier: The block's display name or stable type name.
            inputs: Port name to the name of the kernel variable holding its value.
            config: The block's configuration — JSON-safe values only, since
                this half does cross the frame.
            bind: Where to put the results: one variable name for a
                single-output block, or a mapping of port name to variable name.
                Omit it to run the block for its lineage alone.
            session_id: The explore session the call belongs to, carried into
                its lineage. Ignored once an adapter is installed in the kernel.

        Returns:
            The port-to-variable names bound, the output type names, and the
            call's lineage facts — every field of a ``BlockExecutionRecord``
            and its ``block_io`` edges except each edge's data object, which
            exists only in the kernel.

        Raises:
            BridgeError: The block was not found, a port was violated, the
                block raised, an interactive call was cancelled, or an input
                named a variable the kernel does not have.
        """
        payload: dict[str, Any] = {"action": "block_call", "identifier": identifier}
        if inputs is not None:
            payload["inputs"] = dict(inputs)
        if config is not None:
            payload["config"] = dict(config)
        if bind is not None:
            payload["bind"] = bind if isinstance(bind, str) else dict(bind)
        if session_id is not None:
            payload["session_id"] = session_id
        return dict(self._call(payload))

    # -- protocol -----------------------------------------------------------

    def _call(self, payload: Mapping[str, Any]) -> Any:
        """Run one bridge call and return its result.

        Raises:
            BridgeError: The call failed inside the kernel.
            BridgeProtocolError: No reply frame arrived, or it announced
                another protocol version.
        """
        result = self._handle.execute_silent(_bridge_call_source(payload), timeout=self._timeout)
        stdout = "".join(
            output.text or "" for output in result.outputs if output.output_type == "stream" and output.name == "stdout"
        )
        match = _FRAME_PATTERN.search(stdout)
        if match is None:
            raise BridgeProtocolError(_no_frame_message(result))
        response = json.loads(base64.b64decode(match.group(1)).decode("utf-8"))
        version = response.get("version")
        if version != BRIDGE_PROTOCOL_VERSION:
            msg = (
                f"The kernel's bridge speaks protocol version {version!r}; this service speaks "
                f"{BRIDGE_PROTOCOL_VERSION}. The kernel is running a different SciStudio than the service."
            )
            raise BridgeProtocolError(msg)
        if not response.get("ok"):
            error = response.get("error") or {}
            msg = f"{error.get('type', 'Error')} in the kernel bridge: {error.get('message', 'no message')}"
            raise BridgeError(msg)
        return response.get("result")


def _bridge_call_source(payload: Mapping[str, Any]) -> str:
    """The one line of code a bridge call runs in the kernel.

    It binds no name. ``__import__`` with a non-empty ``fromlist`` returns the
    submodule, so the whole call is a single expression statement and the
    kernel namespace is exactly as it was afterwards — which matters, because
    the next thing the session does with that namespace is fingerprint it.
    """
    encoded = base64.b64encode(json.dumps(dict(payload)).encode("utf-8")).decode("ascii")
    return f'__import__("scistudio.explore.kernel_bridge", fromlist=["_dispatch"])._dispatch(globals(), "{encoded}")'


def _no_frame_message(result: Any) -> str:
    """Explain a missing reply frame with whatever the kernel did say."""
    if result.error is not None:
        return (
            f"The kernel bridge did not answer: {result.error.ename}: {result.error.evalue}. "
            "The usual cause is a kernel whose interpreter cannot import scistudio."
        )
    printed = "".join(output.text or "" for output in result.outputs if output.output_type == "stream")
    tail = printed.strip()[-400:]
    return "The kernel bridge did not answer and raised nothing." + (f" It printed: {tail!r}" if tail else "")
