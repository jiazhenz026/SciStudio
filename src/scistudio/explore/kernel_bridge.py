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
  variable window, the session's declared outputs, and an environment snapshot.
* **In the service.** :class:`KernelBridge` wraps a
  :class:`~scistudio.explore.kernel.KernelHandle` and turns each of those into a
  method.

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
set ``storage_ref`` on it, and the temporary file it pointed at is deleted when
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
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from scistudio.explore.fingerprint import Fingerprint, fingerprint
from scistudio.stability import provisional

if TYPE_CHECKING:  # pragma: no cover - imported for annotations only
    from scistudio.explore.kernel import KernelHandle

__all__ = [
    "BRIDGE_PROTOCOL_VERSION",
    "INSTALL_PROBE",
    "Binding",
    "BridgeError",
    "BridgeProtocolError",
    "KernelBridge",
    "bindings",
    "cell_installs_packages",
    "environment_snapshot",
    "fingerprints",
    "memory_bytes",
    "session_kernel_env",
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
    """``type(value).__name__``."""

    type_module: str
    """The module the type came from, so ``DataFrame`` says which one it is."""

    summary: str
    """A short, bounded description — a length, a shape, or the type name."""


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
        if _is_hidden(name):
            continue
        try:
            result[name] = fingerprint(value)
        except Exception:  # a value that cannot even be read is not observable
            result[name] = Fingerprint(digest="", observable=False, type_name=_safe_type_name(value))
    return result


@provisional(since="0.3.4")
def bindings(namespace: Mapping[str, Any]) -> list[Binding]:
    """List the top-level bindings with their type names (FR-009).

    Args:
        namespace: The kernel's user namespace.

    Returns:
        One :class:`Binding` per visible name, sorted by name so a panel
        re-rendering the list does not see it reorder.
    """
    listed: list[Binding] = []
    for name, value in list(namespace.items()):
        if _is_hidden(name):
            continue
        value_type = type(value)
        listed.append(
            Binding(
                name=name,
                type_name=_safe_type_name(value),
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

    if name not in namespace or _is_hidden(name):
        msg = f"{name!r} is not a variable in this kernel."
        raise KeyError(msg)

    from scistudio.explore.notebook_api import wrap_native

    data_object = wrap_native(namespace[name])
    service = get_preview_service(project_dir=Path(project_dir) if project_dir else None)
    target_kind = _target_kind(data_object)

    existing = getattr(data_object, "storage_ref", None)
    if existing is not None:
        return _render(service, data_object, existing, target_kind, query)
    with tempfile.TemporaryDirectory(prefix="scistudio-window-") as temporary:
        destination = Path(temporary) / (name + _staging_suffix(data_object))
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
    one the person's variable is bound to, and the file is a temporary one this
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


def _is_hidden(name: str) -> bool:
    """Whether *name* is the interpreter's rather than the notebook's."""
    if name.startswith("__") and name.endswith("__"):
        return True
    if name in _SHELL_NAMES:
        return True
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
    """
    type_name = _safe_type_name(value)
    try:
        shape = getattr(value, "shape", None)
        if isinstance(shape, tuple) and all(isinstance(size, int) for size in shape):
            return f"{type_name}{tuple(shape)}"
        if isinstance(value, (str, bytes, list, tuple, dict, set, frozenset)):
            return f"{type_name} of {len(value)}"
        if isinstance(value, (bool, int, float)):
            return f"{type_name} {value}"
    except Exception:  # an object whose len or shape raises describes itself as its type
        return type_name
    return type_name


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
        return {"python": sys.executable, "pid": os.getpid()}
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
                "type_module": binding.type_module,
                "summary": binding.summary,
            }
            for binding in bindings(namespace)
        ]
    if action == "memory":
        return memory_bytes()
    if action == "environment":
        return environment_snapshot()
    if action == "declared_outputs":
        return [
            {"name": declared.name, "type_name": declared.type_name} for declared in notebook_api.declared_outputs()
        ]
    if action == "window":
        return variable_window(
            namespace,
            str(payload["name"]),
            query=payload.get("query"),
            project_dir=payload.get("project_dir"),
        )
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
        """The top-level bindings with their type names (FR-009)."""
        raw = self._call({"action": "bindings"})
        return tuple(
            Binding(
                name=str(entry["name"]),
                type_name=str(entry["type_name"]),
                type_module=str(entry["type_module"]),
                summary=str(entry["summary"]),
            )
            for entry in raw
        )

    def memory_bytes(self) -> int | None:
        """Resident memory the kernel reports for itself (FR-009).

        See :func:`memory_bytes` for why the kernel *list* does not use this.
        """
        raw = self._call({"action": "memory"})
        return int(raw) if raw is not None else None

    def declared_outputs(self) -> tuple[str, ...]:
        """The names cells have declared with ``scistudio.output`` (FR-010)."""
        raw = self._call({"action": "declared_outputs"})
        return tuple(str(entry["name"]) for entry in raw)

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
