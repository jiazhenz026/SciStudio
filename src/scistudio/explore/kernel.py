"""One ipykernel process and the ``jupyter_client`` machinery that drives it.

This module is the whole of SciStudio's contact with a live Python kernel
(ADR-054 §5.3; spec ``adr-054-explore-session`` FR-007, FR-013 to FR-016).
:class:`KernelHandle` launches ipykernel from SciStudio's own interpreter,
runs code on it, interrupts a cell that will not end, restarts, stops, and
notices when the process dies. It knows nothing about notebooks, cells, or
marks: the session service owns those and holds one handle per session.

`jupyter_server` is deliberately absent. It exists to let a frontend talk to a
kernel directly, and every thing SciStudio adds around execution — admission,
marking, observation, recording, committing — has to sit between the person
and the kernel. So the service is the kernel's only client (FR-007).

**The interrupt.** ADR-054 §6.3 requires that a hung cell can actually be
ended, and calls it out because the product has previously shipped a stop
control that did not stop what the person believed it stopped (#1790).
`jupyter_client` decides how to interrupt from the *kernel spec's*
``interrupt_mode``, not from an argument to ``interrupt_kernel()``, and the
two modes are not equivalent:

* ``"signal"`` asks the provisioner to deliver ``SIGINT``. On POSIX that is a
  signal to the kernel's own process group, which ``jupyter_client``'s
  launcher gives it. On Windows there is no ``SIGINT`` to send, so the
  launcher creates a named Win32 event, hands its handle to the child through
  ``JPY_INTERRUPT_EVENT``, and ``LocalProvisioner.send_signal`` sets that
  event; ipykernel's parent poller waits on it and calls
  ``interrupt_main()``. The launcher creates the event on Windows
  unconditionally, whatever the mode says.
* ``"message"`` sends an ``interrupt_request`` on the kernel's control
  channel. ipykernel serves the control channel on a thread of its own, so on
  POSIX the request is read while the main thread is stuck in the person's
  loop and ipykernel signals its own process group.

**Only ``"signal"`` interrupts a hung cell on Windows.** ipykernel's control
handler ends at ``if os.name == "nt": self.log.error("Interrupt message not
supported on Windows")`` and returns — the request is accepted, an ``ok``
reply comes back, and the cell keeps running. Measured against ipykernel
7.3.0 and jupyter_client 8.10.0 on Windows 11: with ``"signal"`` a
``while True: pass`` cell ends within a tenth of a second of the interrupt
with ``KeyboardInterrupt`` and the kernel survives; with ``"message"`` the
same cell was still running twenty seconds later. That is precisely the #1790
failure — a stop control that does not stop — so :class:`KernelHandle`
**refuses** ``"message"`` on Windows rather than accepting a mode it knows to
be inert there.

SciStudio therefore builds its own in-memory kernel spec (it never reads an
installed kernelspec directory, so a user's Jupyter installation cannot change
what SciStudio launches) and defaults ``interrupt_mode`` to ``"signal"`` on
every platform: the one mode proven here, and the one ipykernel's own
kernelspec uses. :func:`default_interrupt_mode` is the single place that
decision lives, and ``tests/explore/test_kernel_session.py`` re-proves it
against a real process on whatever platform CI runs.

**Death.** A caller must never wait forever on a kernel that is already gone
(FR-015). :meth:`KernelHandle.execute` polls the process while it waits for
output, so a kernel killed from outside ends the running request with
:class:`KernelDiedError` rather than a hang, and the handle reports
``"dead"`` afterwards and can be restarted.

That poll asks two independent questions and believes the more pessimistic
answer, because ``jupyter_client``'s ``is_alive()`` is not trustworthy on its
own: it is ``waitpid(pid, WNOHANG)`` underneath, and Linux withholds a killed
multi-threaded process from ``wait`` while its sibling threads finish exiting,
even though ``/proc`` already calls it a zombie. Believing only the library
left a dead kernel reported as ``"idle"`` on CI (#2240). See
:meth:`KernelHandle._process_alive`.
"""

from __future__ import annotations

import logging
import os
import queue
import sys
import threading
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import psutil
from jupyter_client.kernelspec import KernelSpec, KernelSpecManager
from jupyter_client.manager import KernelManager

from scistudio.stability import provisional

__all__ = [
    "ExecutionResult",
    "InterruptMode",
    "KernelDiedError",
    "KernelError",
    "KernelHandle",
    "KernelLaunchError",
    "KernelNotRunningError",
    "KernelOutput",
    "KernelState",
    "KernelStatus",
    "KernelTimeoutError",
    "default_interrupt_mode",
    "validate_interrupt_mode",
]

_LOG = logging.getLogger(__name__)

#: How long to wait on a channel before checking whether the kernel is still
#: alive. Small enough that a killed kernel is noticed promptly, large enough
#: that an idle wait costs nothing measurable.
_POLL_INTERVAL_SECONDS = 0.1

#: Default seconds to wait for a freshly launched kernel to answer
#: ``kernel_info_request``.
_DEFAULT_STARTUP_TIMEOUT = 60.0

#: Default seconds to wait for a kernel to exit after a shutdown request.
_DEFAULT_SHUTDOWN_TIMEOUT = 10.0


# A Literal type alias cannot carry a runtime stability marker; it is part of
# this module's public surface alongside the decorated symbols below.
InterruptMode = Literal["message", "signal"]
"""How an interrupt reaches the kernel: an ``interrupt_request`` on the control
channel (``"message"``) or ``SIGINT`` to the process group (``"signal"``)."""

KernelState = Literal["not-started", "starting", "idle", "busy", "dead"]
"""Where a :class:`KernelHandle` is in its life.

``"not-started"`` before the first :meth:`KernelHandle.start`; ``"starting"``
while the process comes up; ``"idle"`` when it is ready and running nothing;
``"busy"`` while a request of ours is executing; ``"dead"`` once the process
has exited, whether we stopped it or something else killed it.
"""


@provisional(since="0.3.4")
class KernelLaunchError(RuntimeError):
    """Raised when the kernel process could not be started or never answered.

    Causes include an interpreter that cannot import ``ipykernel``, a process
    that exited during startup, and a kernel that came up but did not reply to
    ``kernel_info_request`` within the startup timeout.
    """


@provisional(since="0.3.4")
class KernelNotRunningError(RuntimeError):
    """Raised when an operation needs a live kernel and there is none.

    Either :meth:`KernelHandle.start` was never called, or the handle has been
    stopped. A handle whose kernel *died* raises :class:`KernelDiedError` from
    the request that noticed instead.
    """


@provisional(since="0.3.4")
class KernelDiedError(RuntimeError):
    """Raised when the kernel process is gone while a request was outstanding.

    This is FR-015's contract: the running cell ends with an error rather than
    the caller waiting on a process that will never answer. The handle reports
    ``"dead"`` afterwards and :meth:`KernelHandle.restart` brings up a fresh
    one.
    """


@provisional(since="0.3.4")
class KernelTimeoutError(TimeoutError):
    """Raised when a request did not finish inside the timeout it was given.

    The request is *still running* in the kernel — a timeout is not a cancel.
    Call :meth:`KernelHandle.interrupt` to end it.
    """


@provisional(since="0.3.4")
@dataclass(frozen=True)
class KernelError:
    """The exception a request raised inside the kernel."""

    ename: str
    """The exception class name, for example ``"KeyboardInterrupt"``."""

    evalue: str
    """The exception's string value."""

    traceback: tuple[str, ...] = ()
    """The formatted traceback lines, as the kernel rendered them."""


@provisional(since="0.3.4")
@dataclass(frozen=True)
class KernelOutput:
    """One output message a request produced.

    The field names follow the nbformat output shapes so a notebook store can
    write these straight into a cell.
    """

    output_type: Literal["stream", "execute_result", "display_data", "error"]
    """Which kind of output this is."""

    name: str | None = None
    """For a ``"stream"`` output, ``"stdout"`` or ``"stderr"``."""

    text: str | None = None
    """For a ``"stream"`` output, the text written."""

    data: Mapping[str, Any] = field(default_factory=dict)
    """For a result or a display, the MIME bundle."""

    metadata: Mapping[str, Any] = field(default_factory=dict)
    """For a result or a display, the accompanying metadata."""

    error: KernelError | None = None
    """For an ``"error"`` output, the exception that was raised."""


@provisional(since="0.3.4")
@dataclass(frozen=True)
class ExecutionResult:
    """What one execute request produced."""

    status: Literal["ok", "error", "abort"]
    """The reply status from the kernel.

    ``"abort"`` is a request the kernel dropped without running, which is what
    happens to anything queued behind a request that ended in an error.
    """

    outputs: tuple[KernelOutput, ...] = ()
    """Every output message the request published, in arrival order.

    Empty for a request run with ``silent=True`` that printed nothing.
    """

    execution_count: int | None = None
    """The kernel's execution counter as of this reply.

    A silent request does not advance the counter, so it reports whatever the
    last non-silent request left behind; comparing the count across a silent
    request is how a test proves the request left no trace. ``None`` when the
    reply carried no counter at all.
    """

    error: KernelError | None = None
    """The exception that ended the request, when ``status`` is ``"error"``."""

    @property
    def interrupted(self) -> bool:
        """Whether this request ended because it was interrupted.

        True exactly when the kernel raised ``KeyboardInterrupt``, which is how
        both interrupt modes surface at the caller.
        """
        return self.error is not None and self.error.ename == "KeyboardInterrupt"


@provisional(since="0.3.4")
@dataclass(frozen=True)
class KernelStatus:
    """A point-in-time reading of one kernel, for the list of FR-016."""

    state: KernelState
    """The handle's state at the moment the reading was taken."""

    pid: int | None
    """The kernel process id, or ``None`` when no process is running."""

    memory_bytes: int | None
    """Resident set size of the kernel process, or ``None`` when unreadable."""

    python_executable: str
    """The interpreter the kernel was launched from."""

    started_at: float | None
    """``time.time()`` when the current process was launched."""

    interrupt_mode: InterruptMode
    """How an interrupt reaches this kernel."""


@provisional(since="0.3.4")
def default_interrupt_mode() -> InterruptMode:
    """The interrupt mode SciStudio launches kernels with.

    ``"signal"`` on every platform. It is the only mode that reaches a hung
    cell on Windows (see this module's docstring), it is what ipykernel's own
    kernelspec uses, and one mode everywhere means the interrupt the tests
    prove is the interrupt users get.

    Set ``SCISTUDIO_EXPLORE_INTERRUPT_MODE=message`` to override, which exists
    for diagnosing an environment where signal delivery misbehaves; any other
    value is ignored and ``"signal"`` is used. The override is refused on
    Windows by :func:`validate_interrupt_mode`, because there it would produce
    an interrupt control that silently does nothing.
    """
    override = os.environ.get("SCISTUDIO_EXPLORE_INTERRUPT_MODE", "").strip().lower()
    if override == "message" and not _is_windows():
        return "message"
    return "signal"


@provisional(since="0.3.4")
def validate_interrupt_mode(mode: InterruptMode) -> InterruptMode:
    """Return ``mode``, or refuse it because it cannot interrupt on this platform.

    Args:
        mode: The mode a caller asked for.

    Returns:
        The same mode, when it works here.

    Raises:
        ValueError: ``mode`` is ``"message"`` on Windows, where ipykernel
            answers ``interrupt_request`` with a logged error and leaves the
            cell running. Accepting it would ship an interrupt control that
            does nothing, which is the failure ADR-054 §6.3 exists to prevent.
    """
    if mode == "message" and _is_windows():
        msg = (
            "interrupt_mode='message' cannot interrupt a kernel on Windows: ipykernel's "
            "interrupt_request handler logs 'Interrupt message not supported on Windows' "
            "and leaves the cell running. Use 'signal', which reaches the kernel through "
            "the JPY_INTERRUPT_EVENT the launcher creates."
        )
        raise ValueError(msg)
    if mode not in {"signal", "message"}:
        msg = f"Unknown interrupt mode {mode!r}; expected 'signal' or 'message'."
        raise ValueError(msg)
    return mode


def _is_windows() -> bool:
    """Whether this is the platform where ``"message"`` interrupts do nothing."""
    return sys.platform == "win32"


class _FixedKernelSpecManager(KernelSpecManager):
    """A spec manager that serves one in-memory spec and reads no directory.

    ``KernelManager`` reaches for a kernel spec in two places we care about:
    the argv it launches, and the ``interrupt_mode`` it obeys. Handing it a
    spec we built means neither can be changed by whatever kernelspecs happen
    to be installed on the machine, which matters because a user's Jupyter
    installation is not ours to trust with what SciStudio launches.
    """

    def __init__(self, spec: KernelSpec, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._spec = spec

    def get_kernel_spec(self, kernel_name: str) -> KernelSpec:
        """Return the one spec this manager was built with, whatever is asked for."""
        return self._spec


@provisional(since="0.3.4")
class KernelHandle:
    """One ipykernel process and the client that drives it.

    The session service owns a handle per session and is the kernel's only
    client (FR-007). The handle is deliberately ignorant of notebooks: it
    launches, executes, interrupts, restarts, stops, reports memory, and
    reports death, and that is all.

    Threading: :meth:`execute` and :meth:`execute_silent` serialise on one
    lock, because ipykernel executes one request at a time anyway.
    :meth:`interrupt`, :meth:`is_alive`, :meth:`memory_bytes`, and
    :meth:`status` deliberately do **not** take that lock — the whole point of
    an interrupt is that it can be issued while a request is running, and the
    kernel list of FR-016 must be readable while every kernel in it is busy.

    Example::

        handle = KernelHandle()
        handle.start()
        try:
            result = handle.execute("x = 1 + 1")
            assert result.status == "ok"
        finally:
            handle.stop()
    """

    def __init__(
        self,
        *,
        python_executable: str | Path | None = None,
        working_directory: str | Path | None = None,
        env: Mapping[str, str] | None = None,
        interrupt_mode: InterruptMode | None = None,
        startup_timeout: float = _DEFAULT_STARTUP_TIMEOUT,
        shutdown_timeout: float = _DEFAULT_SHUTDOWN_TIMEOUT,
        on_death: Callable[[], None] | None = None,
        kernel_id: str | None = None,
    ) -> None:
        """Describe a kernel without starting it.

        Args:
            python_executable: The interpreter to launch ipykernel from.
                Defaults to ``sys.executable``, which in a packaged desktop
                build *is* SciStudio's bundled interpreter (FR-007) and in a
                source checkout is the environment the service runs in.
            working_directory: The kernel process's working directory.
                Defaults to the service's own.
            env: Environment variables added to the kernel's environment on top
                of the service's. The launcher's own connection variables always
                win.
            interrupt_mode: Override :func:`default_interrupt_mode`. Validated
                by :func:`validate_interrupt_mode`, which refuses a mode that
                cannot interrupt on this platform.
            startup_timeout: Seconds to wait for the kernel to answer
                ``kernel_info_request`` before giving up.
            shutdown_timeout: Seconds to wait for the process to exit after a
                shutdown request before killing it.
            on_death: Called once, with no arguments, the first time the handle
                observes that the process has died without being stopped by us.
                This is how the session learns to report the kernel dead and
                offer a restart (FR-015). Exceptions raised by the callback are
                logged and swallowed, because the caller that noticed the death
                has its own error to raise.
            kernel_id: A stable identifier for this handle. Generated when
                omitted.

        Raises:
            ValueError: ``interrupt_mode`` cannot interrupt a kernel on this
                platform. See :func:`validate_interrupt_mode`.
        """
        self.kernel_id = kernel_id or uuid.uuid4().hex
        """A stable identifier for this handle, for the kernel list of FR-016."""

        self._python_executable = str(python_executable) if python_executable is not None else sys.executable
        self._working_directory = Path(working_directory) if working_directory is not None else None
        self._extra_env = dict(env or {})
        self._interrupt_mode: InterruptMode = validate_interrupt_mode(interrupt_mode or default_interrupt_mode())
        self._startup_timeout = startup_timeout
        self._shutdown_timeout = shutdown_timeout
        self._on_death = on_death

        self._manager: KernelManager | None = None
        self._client: Any = None
        self._state: KernelState = "not-started"
        self._started_at: float | None = None
        self._stopping = False
        self._death_reported = False
        self._pending_msg_id: str | None = None

        self._exec_lock = threading.RLock()
        self._lifecycle_lock = threading.RLock()

    # ------------------------------------------------------------------
    # Reading the kernel
    # ------------------------------------------------------------------

    @property
    def state(self) -> KernelState:
        """The handle's state, refreshed against the process before answering.

        Reading this notices a kernel that was killed from outside, so a caller
        polling ``state`` learns about a death without having to execute
        anything.
        """
        if self._state in {"idle", "busy", "starting"} and not self._process_alive():
            self._mark_dead()
        return self._state

    @property
    def python_executable(self) -> str:
        """The interpreter this kernel is (or would be) launched from."""
        return self._python_executable

    @property
    def interrupt_mode(self) -> InterruptMode:
        """How an interrupt reaches this kernel."""
        return self._interrupt_mode

    @property
    def pid(self) -> int | None:
        """The kernel process id, or ``None`` when no process is running."""
        manager = self._manager
        if manager is None:
            return None
        provisioner = getattr(manager, "provisioner", None)
        pid = getattr(provisioner, "pid", None)
        return int(pid) if pid else None

    def is_alive(self) -> bool:
        """Whether the kernel process is running right now.

        Safe to call while a request is executing; it polls the process and
        does not touch the message channels.
        """
        return self.state in {"starting", "idle", "busy"}

    def memory_bytes(self) -> int | None:
        """Resident memory the kernel holds, or ``None`` if unreadable.

        Read from outside the process with ``psutil`` rather than through the
        kernel, deliberately: FR-016 must be able to list a kernel's memory
        while that kernel is stuck in a long cell, and anything asked of the
        kernel itself would queue behind the cell (the shallow freeze of
        ADR-054 §6.3).

        The figure covers the launched process **and its descendants**,
        because on Windows the launched process is often not the interpreter.
        A virtual environment's ``python.exe`` there can be a redirector that
        runs the real interpreter as a child and waits for it; reading only
        the process ``jupyter_client`` launched then reports about four
        megabytes for every kernel however much data it holds, which would
        make the kernel list of FR-016 useless for the thing it exists to
        show. Summing a tree can double-count pages two processes share, which
        for a redirector and its child is a few megabytes and is the honest
        error to prefer.
        """
        processes = self._process_tree()
        if not processes:
            return None
        total = 0
        counted = False
        for process in processes:
            try:
                total += int(process.memory_info().rss)
                counted = True
            except (psutil.Error, OSError):  # a child that exited mid-read
                continue
        return total if counted else None

    def _process_tree(self) -> list[psutil.Process]:
        """The launched process and everything it started, as far as we can see."""
        pid = self.pid
        if pid is None:
            return []
        try:
            root = psutil.Process(pid)
            return [root, *root.children(recursive=True)]
        except (psutil.Error, OSError):
            return []

    def status(self) -> KernelStatus:
        """A reading of this kernel for the list of FR-016."""
        return KernelStatus(
            state=self.state,
            pid=self.pid,
            memory_bytes=self.memory_bytes(),
            python_executable=self._python_executable,
            started_at=self._started_at,
            interrupt_mode=self._interrupt_mode,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Launch the kernel and wait until it answers.

        Raises:
            KernelLaunchError: The process could not be started, exited during
                startup, or did not answer within the startup timeout.
            RuntimeError: The handle already has a live kernel.
        """
        with self._lifecycle_lock:
            if self._state in {"starting", "idle", "busy"} and self._process_alive():
                msg = "Kernel is already running; stop it or restart it instead."
                raise RuntimeError(msg)
            self._launch()

    def restart(self) -> None:
        """Replace the kernel process with a fresh one.

        The namespace is gone afterwards, which is what makes the session's
        marks reset to never-run (FR-013); resetting the marks is the session's
        job, not the handle's. A handle whose kernel has died restarts the same
        way as one whose kernel is healthy.

        Raises:
            KernelLaunchError: The replacement kernel did not come up.
            KernelNotRunningError: The handle was never started, or was
                stopped. Start it instead.
        """
        with self._lifecycle_lock:
            if self._manager is None:
                msg = "Kernel has never been started; call start() instead of restart()."
                raise KernelNotRunningError(msg)
            self._teardown()
            self._launch()

    def stop(self) -> None:
        """Shut the kernel down and release the process.

        Asks for a clean shutdown first and kills the process if it has not
        exited within the shutdown timeout, so this always ends with no kernel
        process left behind. Calling it on a handle that is already stopped or
        already dead does nothing. Stopping is not a death: ``on_death`` is not
        called, because nothing went wrong.
        """
        with self._lifecycle_lock:
            if self._manager is None:
                self._state = "not-started" if self._started_at is None else "dead"
                return
            self._stopping = True
            try:
                self._teardown()
            finally:
                self._stopping = False
            self._manager = None
            self._state = "dead"

    def interrupt(self) -> None:
        """Interrupt whatever the kernel is running.

        This is the exit from the shallow freeze of ADR-054 §6.3 and it is
        expected to work on a cell that is spinning in pure Python with no
        yield point of its own. See this module's docstring for why the
        control-channel mode is the default. The running request ends with a
        ``KeyboardInterrupt`` the caller sees as
        :attr:`ExecutionResult.interrupted`; the kernel and the session
        survive.

        Deliberately does not take the execution lock — a caller can only
        interrupt from a different thread than the one that is waiting on the
        request.

        Raises:
            KernelNotRunningError: There is no kernel to interrupt.
        """
        manager = self._manager
        if manager is None or not self._process_alive():
            msg = "Cannot interrupt: no kernel is running."
            raise KernelNotRunningError(msg)
        manager.interrupt_kernel()

    def close(self) -> None:
        """Alias for :meth:`stop`, so a handle works as a context manager."""
        self.stop()

    def __enter__(self) -> KernelHandle:
        """Start the kernel if it is not running and return the handle."""
        if self._state in {"not-started", "dead"} or not self._process_alive():
            self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Stop the kernel, whatever happened in the block."""
        self.stop()

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute(
        self,
        code: str,
        *,
        timeout: float | None = None,
        silent: bool = False,
        store_history: bool = True,
        allow_stdin: bool = False,
    ) -> ExecutionResult:
        """Run ``code`` in the kernel and return what it produced.

        Args:
            code: The source to execute. Magics and shell escapes work; this
                is ipykernel's own execution and nothing is rewritten.
            timeout: Seconds to wait for the request to finish. ``None`` waits
                as long as the cell takes, which is the normal case — a cell
                may legitimately run for minutes and the exit is an interrupt,
                not a deadline.
            silent: Run without the request appearing as a cell. See
                :meth:`execute_silent`, which is the call the bridge makes.
            store_history: Whether the kernel records the code in its history
                and advances its execution counter.
            allow_stdin: Whether the kernel may ask for input. False, because
                the service has no terminal to answer with; a kernel that asks
                would otherwise hang the queue.

        Returns:
            The reply status, the outputs in arrival order, the execution
            count, and the error when one was raised. An exception inside the
            code is a *result* with ``status == "error"``, not a raised
            exception here — including an interrupt, which arrives as
            ``KeyboardInterrupt`` and sets
            :attr:`ExecutionResult.interrupted`.

        Raises:
            KernelNotRunningError: No kernel is running.
            KernelDiedError: The process died while the request was
                outstanding (FR-015).
            KernelTimeoutError: ``timeout`` elapsed. The request is still
                running; interrupt it.
        """
        with self._exec_lock:
            client = self._require_client()
            self._state = "busy"
            try:
                self._drain_abandoned(client, timeout=timeout)
                msg_id = client.execute(
                    code,
                    silent=silent,
                    store_history=store_history,
                    allow_stdin=allow_stdin,
                    stop_on_error=True,
                )
                self._pending_msg_id = msg_id
                result = self._collect(client, msg_id, timeout=timeout)
                self._pending_msg_id = None
                return result
            except KernelDiedError:
                self._pending_msg_id = None
                raise
            finally:
                if self._state == "busy":
                    self._state = "idle" if self._process_alive() else "dead"

    def execute_silent(self, code: str, *, timeout: float | None = None) -> ExecutionResult:
        """Run ``code`` without it appearing as a cell.

        This is the call the kernel-side bridge is driven with (FR-009): a
        fingerprint, a variable window, a bindings list, or a memory reading
        travels over the kernel's own execute channel and must leave no trace
        a notebook would render. ``silent=True`` means ipykernel publishes no
        ``execute_input``, publishes no ``execute_result``, does not advance
        the execution counter, and writes nothing to history.

        One consequence the bridge must design around: because
        ``execute_result`` is suppressed, the *value* of a silent request's
        last expression is not delivered. A bridge call that needs to return
        data should write it to stdout, which is still published and arrives in
        :attr:`ExecutionResult.outputs` as a ``"stream"`` output.

        Args:
            code: The bridge call to run.
            timeout: Seconds to wait, as for :meth:`execute`.

        Returns:
            The same :class:`ExecutionResult` as :meth:`execute`. Its
            ``execution_count`` is the counter the *previous* non-silent
            request left, because a silent request does not advance it.
        """
        return self.execute(code, timeout=timeout, silent=True, store_history=False)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _kernel_spec(self) -> KernelSpec:
        """Build the in-memory spec that decides argv and interrupt mode."""
        return KernelSpec(
            argv=[self._python_executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
            display_name="SciStudio Explore",
            language="python",
            interrupt_mode=self._interrupt_mode,
            env={},
            metadata={},
        )

    def _launch(self) -> None:
        """Start a kernel process and a client, and wait for the kernel to answer."""
        spec = self._kernel_spec()
        manager = KernelManager(
            kernel_name="scistudio-explore",
            kernel_spec_manager=_FixedKernelSpecManager(spec),
        )
        self._state = "starting"
        self._death_reported = False
        self._pending_msg_id = None

        env = dict(os.environ)
        env.update(self._extra_env)
        launch_kwargs: dict[str, Any] = {"env": env}
        if self._working_directory is not None:
            launch_kwargs["cwd"] = str(self._working_directory)

        try:
            manager.start_kernel(**launch_kwargs)
        except Exception as exc:  # re-raised as our own error below
            self._state = "dead"
            msg = f"Could not start an ipykernel from {self._python_executable}: {exc}"
            raise KernelLaunchError(msg) from exc

        self._manager = manager
        self._started_at = time.time()

        client = manager.client()
        client.start_channels()
        try:
            client.wait_for_ready(timeout=self._startup_timeout)
        except Exception as exc:  # RuntimeError/TimeoutError both mean the same thing here
            with _suppressed_cleanup_errors():
                client.stop_channels()
            with _suppressed_cleanup_errors():
                manager.shutdown_kernel(now=True)
            self._manager = None
            self._state = "dead"
            msg = (
                f"ipykernel started from {self._python_executable} but did not answer "
                f"within {self._startup_timeout}s: {exc}"
            )
            raise KernelLaunchError(msg) from exc

        self._client = client
        self._state = "idle"

    def _teardown(self) -> None:
        """Stop the channels and end the process. Never raises.

        ``shutdown_kernel(now=False)`` asks the kernel to exit and falls back
        to terminating it, which is what a kernel stuck in an uninterruptible
        loop needs. :func:`_wait_for_exit` is the backstop that guarantees the
        caller of :meth:`KernelHandle.stop` is not left with a live process.
        """
        client = self._client
        self._client = None
        self._pending_msg_id = None
        if client is not None:
            with _suppressed_cleanup_errors():
                client.stop_channels()

        manager = self._manager
        if manager is None:
            return
        # Capture the tree before the shutdown, because afterwards there is
        # nothing left to enumerate. On Windows the launched process can be a
        # redirector whose child is the real interpreter; a launcher that did
        # not take its child down with it would leave a kernel holding an
        # afternoon's data with no session to attribute it to.
        pids = [process.pid for process in self._process_tree()]
        with _suppressed_cleanup_errors():
            manager.shutdown_kernel(now=False)
        for pid in pids:
            _wait_for_exit(pid, timeout=self._shutdown_timeout)

    def _require_client(self) -> Any:
        """Return the live client, or explain why there is not one."""
        if self._manager is None or self._client is None:
            msg = "Kernel is not running; call start() first."
            raise KernelNotRunningError(msg)
        if not self._process_alive():
            self._mark_dead()
            msg = "Kernel process is gone."
            raise KernelDiedError(msg)
        return self._client

    def _process_alive(self) -> bool:
        """Poll the process without touching the message channels.

        Two independent readings, and the kernel is alive only if **both**
        agree that it is. Asking ``jupyter_client`` alone is not enough, and
        the failure is not hypothetical: it reported a ``SIGKILL``\\ ed kernel
        as healthy on Linux CI, so the session went on offering a kernel that
        no longer existed (#2240).

        ``KernelManager.is_alive()`` is ``Popen.poll() is None`` underneath,
        and ``Popen.poll()`` is ``waitpid(pid, WNOHANG)``. On Linux those two
        questions are not the same question. When a multi-threaded process is
        killed, its thread-group leader is marked a zombie — ``/proc`` reports
        state ``Z`` at once — but ``wait`` deliberately withholds it while any
        sibling thread is still exiting (the kernel's ``delay_group_leader``).
        ``waitpid`` answers "nothing to report", ``Popen.poll()`` returns
        ``None``, and ``jupyter_client`` reads that ``None`` as "still
        running". ipykernel runs half a dozen threads, so the window is real;
        it is short on an idle machine and wide on a loaded one, which is why
        this only ever failed in CI.

        (``Popen.poll()`` has a second way to answer ``None`` about a dead
        process: it takes ``_waitpid_lock`` non-blockingly and gives up when a
        concurrent poll holds it. The handle is polled from several threads by
        design — :meth:`state` for the kernel list of FR-016, and the
        ``_collect`` loop of a request in flight — so that overlap can happen
        too. It was not what #2240 caught, but the same reading rules it out.)

        Asking the operating system about the pid directly settles both,
        because a zombie *is* a dead kernel however the library reads it —
        the same insight the ``_process_gone`` test helper needed. The manager
        is still asked first, and its answer still counts: its poll is what
        reaps the child when the child is reapable, and it is the reading that
        survives a pid reused by an unrelated process.
        """
        manager = self._manager
        if manager is None:
            return False
        try:
            manager_alive = bool(manager.is_alive())
        except Exception:  # a manager that cannot answer is not alive
            manager_alive = False
        directly_alive = self._pid_alive()
        if directly_alive is None:  # the OS would not say; the manager is all we have
            return manager_alive
        return manager_alive and directly_alive

    def _pid_alive(self) -> bool | None:
        """Whether the kernel's pid is a live process, read straight from the OS.

        ``None`` means "cannot tell" — there is no pid yet, or the platform
        refused the reading — and leaves the verdict to the manager rather
        than declaring a healthy kernel dead on a failed lookup.

        A zombie counts as dead: on POSIX a killed child keeps its pid until
        something reaps it, and psutil reports it as both existing and
        running for as long as it sits there. Windows has no zombie state, so
        there the process is simply gone and :class:`psutil.NoSuchProcess`
        gives the same answer.
        """
        pid = self.pid
        if pid is None:
            return None
        try:
            process = psutil.Process(pid)
            if process.status() == psutil.STATUS_ZOMBIE:
                return False
            return bool(process.is_running())
        except psutil.NoSuchProcess:  # ZombieProcess is a subclass of this
            return False
        except (psutil.Error, OSError):
            return None

    def _mark_dead(self) -> None:
        """Record the death and tell the owner once."""
        self._state = "dead"
        if self._stopping or self._death_reported:
            return
        self._death_reported = True
        if self._on_death is None:
            return
        try:
            self._on_death()
        except Exception:  # the caller that noticed has its own error to raise
            _LOG.exception("Explore kernel death callback failed for kernel %s", self.kernel_id)

    def _drain_abandoned(self, client: Any, *, timeout: float | None) -> None:
        """Finish a request a previous timeout walked away from.

        A :class:`KernelTimeoutError` leaves the cell running, and ipykernel
        runs one request at a time: submitting the next one while the old one
        is still going would queue it behind the old one, and ipykernel aborts
        every queued request when the one ahead of it ends in an error — which
        is exactly how an interrupted cell ends. So the next caller waits for
        the abandoned request to finish, throwing its output away, and only
        then submits. If the abandoned request is still running when this
        caller's own timeout expires, the timeout is reported against this
        caller too, because the kernel genuinely is not free.
        """
        abandoned = self._pending_msg_id
        if abandoned is None:
            return
        _LOG.debug("Waiting for an abandoned explore request %s to finish", abandoned)
        self._collect(client, abandoned, timeout=timeout)
        self._pending_msg_id = None

    def _collect(self, client: Any, msg_id: str, *, timeout: float | None) -> ExecutionResult:
        """Gather one request's iopub output and its shell reply.

        The request is finished when both have arrived: the ``status: idle``
        broadcast that closes its iopub stream, and the ``execute_reply`` that
        carries its status and execution count. Waiting for only one of the two
        loses either the last outputs or the status.
        """
        deadline = None if timeout is None else time.monotonic() + timeout
        outputs: list[KernelOutput] = []
        reply: dict[str, Any] | None = None
        idle_seen = False

        while reply is None or not idle_seen:
            if reply is None:
                shell_msg = _try_get(client.get_shell_msg, _POLL_INTERVAL_SECONDS / 10)
                if shell_msg is not None and _parent_id(shell_msg) == msg_id:
                    reply = shell_msg

            iopub_msg = _try_get(client.get_iopub_msg, _POLL_INTERVAL_SECONDS)
            if iopub_msg is not None and _parent_id(iopub_msg) == msg_id:
                output = _as_output(iopub_msg)
                if output is not None:
                    outputs.append(output)
                elif _is_idle_status(iopub_msg):
                    idle_seen = True

            if not self._process_alive():
                self._mark_dead()
                msg = "Kernel process died while a request was running."
                raise KernelDiedError(msg)

            if deadline is not None and time.monotonic() >= deadline and (reply is None or not idle_seen):
                msg = f"Kernel request did not finish within {timeout}s; it is still running."
                raise KernelTimeoutError(msg)

        content = reply.get("content", {})
        status = _normalised_status(content.get("status"))
        error = None
        if status == "error":
            error = KernelError(
                ename=str(content.get("ename", "")),
                evalue=str(content.get("evalue", "")),
                traceback=tuple(str(line) for line in content.get("traceback", ())),
            )
        raw_count = content.get("execution_count")
        return ExecutionResult(
            status=status,
            outputs=tuple(outputs),
            execution_count=int(raw_count) if isinstance(raw_count, int) else None,
            error=error,
        )


class _suppressed_cleanup_errors:  # noqa: N801 - a context manager used as a statement, not a type
    """Swallow and log anything a teardown step raises.

    Cleanup runs on paths that already have an error to report, and a second
    failure while closing a socket must not replace the first one.
    """

    def __enter__(self) -> None:
        """Enter the block."""
        return None

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: object) -> bool:
        """Log and swallow whatever the block raised."""
        if exc is not None:
            _LOG.debug("Ignoring error while shutting an explore kernel down: %s", exc)
        return True


def _wait_for_exit(pid: int, *, timeout: float) -> None:
    """Wait for ``pid`` to disappear, killing it if it outstays the timeout."""
    try:
        process = psutil.Process(pid)
    except psutil.Error:
        return
    try:
        process.wait(timeout=timeout)
        return
    except psutil.TimeoutExpired:
        _LOG.warning("Explore kernel %s did not exit within %ss; killing it.", pid, timeout)
    except psutil.Error:
        return
    try:
        process.kill()
        process.wait(timeout=timeout)
    except psutil.Error:
        return


def _try_get(getter: Callable[..., dict[str, Any]], timeout: float) -> dict[str, Any] | None:
    """Read one message, returning ``None`` when the channel had nothing to give."""
    try:
        return getter(timeout=timeout)
    except queue.Empty:
        return None
    except Exception as exc:  # a closed channel reads as "nothing here"
        _LOG.debug("Explore kernel channel read failed: %s", exc)
        return None


def _normalised_status(raw: object) -> Literal["ok", "error", "abort"]:
    """Map a reply's status onto the three the message spec defines.

    ipykernel says ``"aborted"`` for a request it dropped because the one
    ahead of it failed, where the spec's name is ``"abort"``; anything else
    unrecognised is treated as a failure rather than quietly as success.
    """
    if raw in {"ok", "error", "abort"}:
        return raw  # type: ignore[return-value]
    if raw == "aborted":
        return "abort"
    return "error"


def _is_idle_status(message: Mapping[str, Any]) -> bool:
    """Whether this is the ``status: idle`` broadcast that closes a request."""
    if message.get("msg_type") != "status":
        return False
    content: Mapping[str, Any] = message.get("content") or {}
    return content.get("execution_state") == "idle"


def _parent_id(message: Mapping[str, Any]) -> str | None:
    """The ``msg_id`` of the request a message answers."""
    parent = message.get("parent_header") or {}
    value = parent.get("msg_id")
    return str(value) if value is not None else None


def _as_output(message: Mapping[str, Any]) -> KernelOutput | None:
    """Convert one iopub message into a :class:`KernelOutput`, or ``None``.

    ``None`` for every message that is not an output — ``status``,
    ``execute_input``, ``clear_output``, and anything a future kernel adds.
    """
    msg_type = message.get("msg_type")
    content: Mapping[str, Any] = message.get("content") or {}

    if msg_type == "stream":
        return KernelOutput(
            output_type="stream",
            name=str(content.get("name", "stdout")),
            text=str(content.get("text", "")),
        )
    if msg_type in {"execute_result", "display_data", "update_display_data"}:
        return KernelOutput(
            output_type="execute_result" if msg_type == "execute_result" else "display_data",
            data=dict(content.get("data") or {}),
            metadata=dict(content.get("metadata") or {}),
        )
    if msg_type == "error":
        return KernelOutput(
            output_type="error",
            error=KernelError(
                ename=str(content.get("ename", "")),
                evalue=str(content.get("evalue", "")),
                traceback=tuple(str(line) for line in _as_sequence(content.get("traceback"))),
            ),
        )
    return None


def _as_sequence(value: object) -> Sequence[object]:
    """Coerce a possibly-missing traceback into a sequence."""
    if isinstance(value, (list, tuple)):
        return value
    return ()
