"""Kernel lifecycle against a real ipykernel process (ADR-054 T-002).

Spec ``adr-054-explore-session`` §4.4 says these tests run against a real
kernel "because a mocked kernel would pass a test that a real interrupt
fails", and it is right: the interrupt test in this module is the one that
found ipykernel refusing ``interrupt_request`` on Windows. Every test here
that touches a kernel spawns a real process, and nothing in this file
substitutes a double for one.

The module carries the ``serial`` marker: real processes and threads must run
outside the xdist batch (#1867, #1896). Every handle a test creates is
registered with the ``kernels`` fixture, which stops it and kills anything
that survived, on the failure path as well as the success path.
"""

from __future__ import annotations

import ast
import contextlib
import sys
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import psutil
import pytest

# ipykernel and jupyter_client are core dependencies (FR-059, task T-001), but
# a checkout that predates T-001 has neither. Skipping the module honestly is
# the only correct behaviour: there is no way to prove an interrupt without a
# process to interrupt.
pytest.importorskip(
    "jupyter_client",
    reason="jupyter_client is not importable; ADR-054 T-001 adds it to pyproject.toml",
)
pytest.importorskip(
    "ipykernel",
    reason="ipykernel is not importable; ADR-054 T-001 adds it to pyproject.toml",
)

from scistudio.explore.kernel import (  # must follow the dependency guards above
    ExecutionResult,
    KernelDiedError,
    KernelError,
    KernelHandle,
    KernelLaunchError,
    KernelNotRunningError,
    KernelOutput,
    KernelTimeoutError,
    _as_output,
    default_interrupt_mode,
    validate_interrupt_mode,
)

pytestmark = pytest.mark.serial

#: Generous enough that a loaded CI machine does not flake, short enough that
#: the per-test 60s wall-clock kill is never the thing that fails.
_EXEC_TIMEOUT = 30.0

#: How long a test waits for a kernel-side marker file to appear before giving
#: up on the cell having started.
_MARKER_TIMEOUT = 30.0


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def kernels() -> Iterator[Callable[..., KernelHandle]]:
    """Hand out kernel handles and guarantee every process they started is gone.

    Cleanup runs whether the test passed or failed, records each pid *before*
    stopping so a handle that has already forgotten its process is still
    reaped, and kills anything that outlives a polite shutdown.
    """
    made: list[KernelHandle] = []

    def make(**kwargs: object) -> KernelHandle:
        handle = KernelHandle(**kwargs)  # type: ignore[arg-type]
        made.append(handle)
        return handle

    try:
        yield make
    finally:
        for handle in made:
            pid = handle.pid
            # Cleanup must not mask a test failure.
            with contextlib.suppress(Exception):
                handle.stop()
            if pid is not None:
                _kill_if_alive(pid)


def _process_gone(pid: int, timeout: float = 10.0) -> bool:
    """Whether ``pid`` is no longer a running process.

    A killed process can linger as a zombie on POSIX and a pid can be reused,
    so this waits briefly and treats "not running" and "does not exist" alike.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not psutil.pid_exists(pid):
            return True
        try:
            if not psutil.Process(pid).is_running():
                return True
        except psutil.Error:
            return True
        time.sleep(0.05)
    return False


def _kill_if_alive(pid: int) -> None:
    """Kill ``pid`` if it somehow outlived the handle that owned it."""
    try:
        process = psutil.Process(pid)
        process.kill()
        process.wait(timeout=10)
    except psutil.Error:
        return


def _started_kernel(kernels: Callable[..., KernelHandle], **kwargs: object) -> KernelHandle:
    """A handle whose kernel is up and answering."""
    handle = kernels(**kwargs)
    handle.start()
    return handle


def _spin_after_marker(marker: Path) -> str:
    """Kernel-side code that announces itself and then hangs forever.

    The marker is what makes the interrupt test honest: the test does not
    interrupt after an arbitrary sleep and hope the cell had started, it waits
    until the kernel has proved it is inside the loop.
    """
    return (
        "import pathlib\n"
        f"pathlib.Path({str(marker.as_posix())!r}).write_text('running', encoding='utf-8')\n"
        "while True:\n"
        "    pass\n"
    )


def _wait_for_marker(marker: Path, timeout: float = _MARKER_TIMEOUT) -> None:
    """Block until the kernel has written ``marker``, or fail the test."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if marker.exists():
            return
        time.sleep(0.02)
    pytest.fail(f"The kernel never reached the loop: {marker} was not written within {timeout}s")


def _interpreter_pid(handle: KernelHandle) -> int:
    """The pid of the process actually running the person's code.

    Not always ``handle.pid``: on Windows a virtual environment's
    ``python.exe`` can be a redirector that runs the real interpreter as a
    child, so the process ``jupyter_client`` launched is a four-megabyte stub.
    Asking the kernel who it is settles it.
    """
    result = handle.execute("import os; print(os.getpid())", timeout=_EXEC_TIMEOUT)
    assert result.status == "ok"
    return int(_text_of(result).strip())


def _text_of(result: ExecutionResult) -> str:
    """Everything the request wrote to stdout, concatenated."""
    return "".join(o.text or "" for o in result.outputs if o.output_type == "stream" and o.name == "stdout")


def _value_of(result: ExecutionResult) -> str | None:
    """The ``text/plain`` rendering of the request's result value, if any."""
    for output in result.outputs:
        if output.output_type == "execute_result":
            value = output.data.get("text/plain")
            return None if value is None else str(value)
    return None


# ---------------------------------------------------------------------------
# Launch (FR-007)
# ---------------------------------------------------------------------------


def test_start_launches_a_real_ipykernel_process(kernels: Callable[..., KernelHandle]) -> None:
    """The handle owns a live process running ipykernel, and reports it."""
    handle = _started_kernel(kernels)

    assert handle.state == "idle"
    assert handle.is_alive()
    pid = handle.pid
    assert pid is not None

    process = psutil.Process(pid)
    assert process.is_running()
    assert "ipykernel_launcher" in " ".join(process.cmdline())

    status = handle.status()
    assert status.pid == pid
    assert status.state == "idle"
    assert status.started_at is not None
    assert status.python_executable == handle.python_executable


def test_the_kernel_runs_the_interpreter_it_was_given(kernels: Callable[..., KernelHandle]) -> None:
    """FR-007: the kernel is launched from the interpreter SciStudio names.

    In a packaged desktop build that interpreter is the bundled one; the
    property under test is that the handle launches the executable it was
    handed and not whatever ``jupyter`` happens to be on the machine.
    """
    handle = _started_kernel(kernels, python_executable=sys.executable)

    result = handle.execute("import sys; print(sys.executable)", timeout=_EXEC_TIMEOUT)

    assert result.status == "ok"
    assert Path(_text_of(result).strip()) == Path(sys.executable)


def test_start_refuses_an_interpreter_that_does_not_exist(kernels: Callable[..., KernelHandle]) -> None:
    """A bad interpreter fails at start with an error naming it, not later."""
    handle = kernels(python_executable=str(Path(sys.executable).parent / "definitely-not-python.exe"))

    with pytest.raises(KernelLaunchError) as excinfo:
        handle.start()

    assert "definitely-not-python" in str(excinfo.value)
    assert handle.state == "dead"
    assert handle.pid is None


def test_working_directory_and_environment_reach_the_kernel(
    kernels: Callable[..., KernelHandle], tmp_path: Path
) -> None:
    """The kernel starts where it was told, with the variables it was given.

    FR-010 selects the notebook helpers' mode with an environment variable the
    launcher sets, so the environment actually arriving in the kernel process
    is a contract the bridge is built on.
    """
    workdir = tmp_path / "session-workdir"
    workdir.mkdir()
    handle = _started_kernel(kernels, working_directory=workdir, env={"SCISTUDIO_TEST_MODE": "session"})

    result = handle.execute(
        "import os; print(os.getcwd()); print(os.environ.get('SCISTUDIO_TEST_MODE'))",
        timeout=_EXEC_TIMEOUT,
    )

    lines = _text_of(result).splitlines()
    assert Path(lines[0]).resolve() == workdir.resolve()
    assert lines[1] == "session"


def test_starting_a_running_kernel_is_refused(kernels: Callable[..., KernelHandle]) -> None:
    """A second start would orphan the first process, so it is an error."""
    handle = _started_kernel(kernels)
    pid = handle.pid

    with pytest.raises(RuntimeError):
        handle.start()

    assert handle.pid == pid


def test_the_handle_is_a_context_manager(kernels: Callable[..., KernelHandle]) -> None:
    """Entering starts the kernel; leaving stops it, even on an exception."""
    handle = kernels()
    seen: list[int] = []
    with pytest.raises(ZeroDivisionError), handle:
        assert handle.is_alive()
        assert handle.pid is not None
        seen.append(handle.pid)
        raise ZeroDivisionError

    assert handle.state == "dead"
    assert _process_gone(seen[0])


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def test_a_cell_runs_and_returns_its_output_and_its_value(kernels: Callable[..., KernelHandle]) -> None:
    """The verification of T-002: a cell runs and its outputs come back."""
    handle = _started_kernel(kernels)

    printed = handle.execute("print('hello from the kernel')", timeout=_EXEC_TIMEOUT)
    assert printed.status == "ok"
    assert printed.error is None
    assert _text_of(printed) == "hello from the kernel\n"
    assert printed.execution_count == 1

    valued = handle.execute("6 * 7", timeout=_EXEC_TIMEOUT)
    assert valued.status == "ok"
    assert _value_of(valued) == "42"
    assert valued.execution_count == 2


def test_the_namespace_persists_between_requests(kernels: Callable[..., KernelHandle]) -> None:
    """One kernel, one namespace: this is what makes a session a session."""
    handle = _started_kernel(kernels)

    handle.execute("total = 41", timeout=_EXEC_TIMEOUT)
    result = handle.execute("total + 1", timeout=_EXEC_TIMEOUT)

    assert _value_of(result) == "42"


def test_an_exception_is_a_result_not_a_raise(kernels: Callable[..., KernelHandle]) -> None:
    """A cell that raises produces an error result the session can render."""
    handle = _started_kernel(kernels)

    result = handle.execute("1 / 0", timeout=_EXEC_TIMEOUT)

    assert result.status == "error"
    assert result.error is not None
    assert result.error.ename == "ZeroDivisionError"
    assert "division by zero" in result.error.evalue
    assert result.error.traceback
    assert not result.interrupted
    error_outputs = [o for o in result.outputs if o.output_type == "error"]
    assert len(error_outputs) == 1
    assert error_outputs[0].error is not None
    assert error_outputs[0].error.ename == "ZeroDivisionError"

    # The kernel is unharmed.
    assert handle.execute("1 + 1", timeout=_EXEC_TIMEOUT).status == "ok"


def test_stderr_is_captured_separately_from_stdout(kernels: Callable[..., KernelHandle]) -> None:
    """A notebook renders the two streams differently, so they stay apart."""
    handle = _started_kernel(kernels)

    result = handle.execute(
        "import sys; sys.stdout.write('out'); sys.stdout.flush(); sys.stderr.write('err'); sys.stderr.flush()",
        timeout=_EXEC_TIMEOUT,
    )

    streams = {(o.name, o.text) for o in result.outputs if o.output_type == "stream"}
    assert ("stdout", "out") in streams
    assert ("stderr", "err") in streams


def test_a_silent_request_leaves_no_trace_but_still_delivers_stdout(
    kernels: Callable[..., KernelHandle],
) -> None:
    """The bridge's call must not look like a cell (FR-009).

    ``silent=True`` suppresses ``execute_input`` and ``execute_result`` and
    does not advance the execution counter, which is what stops a bridge call
    from appearing in the notebook. Stdout survives, which is the channel a
    bridge call has to answer on — asserted here because S3-B1 builds on it.
    """
    handle = _started_kernel(kernels)
    handle.execute("first = 1", timeout=_EXEC_TIMEOUT)
    before = handle.execute("first", timeout=_EXEC_TIMEOUT).execution_count
    assert before == 2

    silent = handle.execute_silent("print('bridge payload'); 'a value that must not come back'", timeout=_EXEC_TIMEOUT)

    assert silent.status == "ok"
    assert _text_of(silent) == "bridge payload\n"
    assert _value_of(silent) is None, "silent requests must not publish execute_result"
    assert silent.execution_count == before, "a silent request must not advance the execution counter"

    after = handle.execute("first", timeout=_EXEC_TIMEOUT)
    assert after.execution_count == before + 1, "the next real cell takes the very next counter value"


def test_a_silent_request_sees_the_namespace_the_cells_built(kernels: Callable[..., KernelHandle]) -> None:
    """The bridge reads the same namespace the person's cells write to."""
    handle = _started_kernel(kernels)
    handle.execute("sample = [1, 2, 3]", timeout=_EXEC_TIMEOUT)

    silent = handle.execute_silent("print(len(sample))", timeout=_EXEC_TIMEOUT)

    assert _text_of(silent) == "3\n"


def test_a_timeout_does_not_cancel_the_cell_and_the_interrupt_still_works(
    kernels: Callable[..., KernelHandle], tmp_path: Path
) -> None:
    """A timeout is a caller giving up waiting, not a cancel.

    The documented escape from a timed-out request is the interrupt, so the
    handle has to stay usable after one.
    """
    handle = _started_kernel(kernels)
    marker = tmp_path / "spinning"

    with pytest.raises(KernelTimeoutError):
        handle.execute(_spin_after_marker(marker), timeout=1.0)

    _wait_for_marker(marker)
    assert handle.is_alive(), "a timeout must not kill the kernel"

    handle.interrupt()
    recovered = handle.execute("'still here'", timeout=_EXEC_TIMEOUT)
    assert recovered.status == "ok"
    assert _value_of(recovered) == "'still here'"


# ---------------------------------------------------------------------------
# The interrupt (FR-013, SC-005, ADR-054 §6.3)
# ---------------------------------------------------------------------------


def test_interrupt_ends_a_hung_cell_and_the_session_survives(
    kernels: Callable[..., KernelHandle], tmp_path: Path
) -> None:
    """SC-005, and the reason this whole module runs a real process.

    The cell is a bare ``while True: pass`` — no sleep, no I/O, no yield point
    of its own — which is the case a mocked kernel cannot represent and the
    case that fails when the interrupt does not reach the process. The test
    waits for the kernel to prove it is inside the loop before interrupting,
    so a pass cannot come from interrupting a cell that had not started.
    """
    handle = _started_kernel(kernels)
    handle.execute("survivor = 'alive'", timeout=_EXEC_TIMEOUT)
    pid = handle.pid
    marker = tmp_path / "hung-cell-started"

    def interrupt_once_the_loop_is_running() -> None:
        _wait_for_marker(marker)
        handle.interrupt()

    interrupter = threading.Thread(target=interrupt_once_the_loop_is_running, daemon=True)
    interrupter.start()
    started = time.monotonic()
    result = handle.execute(_spin_after_marker(marker), timeout=_EXEC_TIMEOUT)
    elapsed = time.monotonic() - started
    interrupter.join(timeout=5)

    assert result.status == "error"
    assert result.error is not None
    assert result.error.ename == "KeyboardInterrupt"
    assert result.interrupted
    assert elapsed < _EXEC_TIMEOUT, "the cell must end because it was interrupted, not because we gave up"

    # The session survives: same process, same namespace, still executing.
    assert handle.pid == pid
    assert handle.state == "idle"
    survivor = handle.execute("survivor", timeout=_EXEC_TIMEOUT)
    assert _value_of(survivor) == "'alive'"


def test_interrupting_an_idle_kernel_is_harmless(kernels: Callable[..., KernelHandle]) -> None:
    """The person can press stop when nothing is running."""
    handle = _started_kernel(kernels)

    handle.interrupt()

    assert handle.execute("1 + 1", timeout=_EXEC_TIMEOUT).status == "ok"


def test_interrupting_without_a_kernel_is_refused(kernels: Callable[..., KernelHandle]) -> None:
    """An interrupt that cannot reach a kernel says so instead of pretending."""
    handle = kernels()

    with pytest.raises(KernelNotRunningError):
        handle.interrupt()


def test_the_default_interrupt_mode_is_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    """``signal`` is the mode the interrupt test above proves."""
    monkeypatch.delenv("SCISTUDIO_EXPLORE_INTERRUPT_MODE", raising=False)

    assert default_interrupt_mode() == "signal"


@pytest.mark.skipif(sys.platform != "win32", reason="the refusal exists because of ipykernel's Windows behaviour")
def test_message_interrupts_are_refused_on_windows(kernels: Callable[..., KernelHandle]) -> None:
    """ipykernel cannot serve ``interrupt_request`` on Windows, so we refuse it.

    ipykernel's handler logs "Interrupt message not supported on Windows" and
    replies ``ok`` while the cell keeps running. Accepting the mode would ship
    exactly the #1790 failure ADR-054 §6.3 names: a stop control that does not
    stop. The refusal is at construction, so it cannot surface as a dead
    button during someone's session.
    """
    with pytest.raises(ValueError, match="Windows"):
        validate_interrupt_mode("message")

    with pytest.raises(ValueError, match="Windows"):
        kernels(interrupt_mode="message")


@pytest.mark.skipif(sys.platform != "win32", reason="the environment override is only clamped on Windows")
def test_the_environment_override_cannot_select_message_mode_on_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No environment variable can turn the interrupt into a no-op."""
    monkeypatch.setenv("SCISTUDIO_EXPLORE_INTERRUPT_MODE", "message")

    assert default_interrupt_mode() == "signal"


@pytest.mark.skipif(sys.platform == "win32", reason="message mode is only usable off Windows")
def test_message_mode_is_available_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """The control-channel mode stays reachable where ipykernel implements it."""
    assert validate_interrupt_mode("message") == "message"
    monkeypatch.setenv("SCISTUDIO_EXPLORE_INTERRUPT_MODE", "message")
    assert default_interrupt_mode() == "message"


def test_an_unknown_interrupt_mode_is_refused() -> None:
    """A typo must not silently become a mode that does nothing."""
    with pytest.raises(ValueError, match="Unknown interrupt mode"):
        validate_interrupt_mode("sigint")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Restart and stop (FR-013)
# ---------------------------------------------------------------------------


def test_restart_gives_a_new_process_and_an_empty_namespace(kernels: Callable[..., KernelHandle]) -> None:
    """Restart is what resets a session; the namespace must really be gone."""
    handle = _started_kernel(kernels)
    handle.execute("carried_over = 'should not survive'", timeout=_EXEC_TIMEOUT)
    original_pid = handle.pid
    assert original_pid is not None

    handle.restart()

    assert handle.state == "idle"
    assert handle.pid is not None
    assert handle.pid != original_pid
    assert _process_gone(original_pid)

    gone = handle.execute("carried_over", timeout=_EXEC_TIMEOUT)
    assert gone.status == "error"
    assert gone.error is not None
    assert gone.error.ename == "NameError"

    fresh = handle.execute("1 + 1", timeout=_EXEC_TIMEOUT)
    assert fresh.status == "ok"
    assert fresh.execution_count == 2, "a restarted kernel counts from the beginning"


def test_restart_recovers_a_kernel_that_died(kernels: Callable[..., KernelHandle]) -> None:
    """FR-015 offers a restart after a death, so restart must work on a corpse."""
    handle = _started_kernel(kernels)
    pid = handle.pid
    assert pid is not None
    psutil.Process(pid).kill()
    psutil.Process(pid).wait(timeout=10)
    assert handle.state == "dead"

    handle.restart()

    assert handle.state == "idle"
    assert handle.pid not in (None, pid)
    assert handle.execute("1 + 1", timeout=_EXEC_TIMEOUT).status == "ok"


def test_restart_before_start_is_refused(kernels: Callable[..., KernelHandle]) -> None:
    """There is nothing to restart, and saying so beats starting one silently."""
    handle = kernels()

    with pytest.raises(KernelNotRunningError):
        handle.restart()


def test_stop_terminates_the_process(kernels: Callable[..., KernelHandle]) -> None:
    """Stop leaves no process behind; a session's kernel is not a leak."""
    handle = _started_kernel(kernels)
    pid = handle.pid
    assert pid is not None
    interpreter_pid = _interpreter_pid(handle)

    handle.stop()

    assert handle.state == "dead"
    assert not handle.is_alive()
    assert handle.pid is None
    assert _process_gone(pid)
    assert _process_gone(interpreter_pid), "the interpreter must go too, not only the process that launched it"


def test_stop_terminates_a_kernel_stuck_in_a_hung_cell(kernels: Callable[..., KernelHandle], tmp_path: Path) -> None:
    """A kernel that cannot answer a shutdown request is still ended.

    Closing a session must not be defeated by the cell that made the person
    want to close it.
    """
    handle = _started_kernel(kernels, shutdown_timeout=15.0)
    marker = tmp_path / "hung-at-stop"
    with pytest.raises(KernelTimeoutError):
        handle.execute(_spin_after_marker(marker), timeout=1.0)
    _wait_for_marker(marker)
    pid = handle.pid
    assert pid is not None

    handle.stop()

    assert handle.state == "dead"
    assert _process_gone(pid)


def test_stop_is_idempotent(kernels: Callable[..., KernelHandle]) -> None:
    """Closing a session twice must not raise at the second close."""
    handle = _started_kernel(kernels)

    handle.stop()
    handle.stop()

    assert handle.state == "dead"


def test_executing_after_stop_is_refused(kernels: Callable[..., KernelHandle]) -> None:
    """A stopped handle says there is no kernel rather than hanging."""
    handle = _started_kernel(kernels)
    handle.stop()

    with pytest.raises(KernelNotRunningError):
        handle.execute("1 + 1", timeout=_EXEC_TIMEOUT)


# ---------------------------------------------------------------------------
# Death detection (FR-015)
# ---------------------------------------------------------------------------


def test_a_process_killed_from_outside_ends_the_running_cell(kernels: Callable[..., KernelHandle]) -> None:
    """FR-015: the caller gets an error, not a wait for a process that is gone.

    The cell would sleep for five minutes. The assertion that the caller
    returned in a small fraction of that is the whole point: a handle that
    merely waited for the reply would sit there until the test's wall-clock
    kill.
    """
    deaths: list[str] = []
    handle = _started_kernel(kernels, on_death=lambda: deaths.append("died"))
    pid = handle.pid
    assert pid is not None
    interpreter_pid = _interpreter_pid(handle)

    def kill_the_kernel() -> None:
        time.sleep(1.0)
        psutil.Process(pid).kill()

    killer = threading.Thread(target=kill_the_kernel, daemon=True)
    killer.start()
    started = time.monotonic()
    with pytest.raises(KernelDiedError):
        handle.execute("import time; time.sleep(300)", timeout=_EXEC_TIMEOUT)
    elapsed = time.monotonic() - started
    killer.join(timeout=5)

    assert elapsed < 15.0, "a dead kernel must end the request promptly, not wait it out"
    assert handle.state == "dead"
    assert not handle.is_alive()
    assert deaths == ["died"], "the owner is told exactly once that the kernel died"
    assert _process_gone(interpreter_pid), "killing the kernel must not orphan the interpreter behind it"


def test_a_death_is_noticed_without_executing_anything(kernels: Callable[..., KernelHandle]) -> None:
    """The kernel list of FR-016 must show a dead kernel as dead.

    Reading state polls the process, so a session that is not executing still
    learns the kernel is gone.
    """
    deaths: list[str] = []
    handle = _started_kernel(kernels, on_death=lambda: deaths.append("died"))
    pid = handle.pid
    assert pid is not None
    psutil.Process(pid).kill()
    psutil.Process(pid).wait(timeout=10)

    assert handle.state == "dead"
    assert handle.status().state == "dead"
    assert deaths == ["died"]


def test_a_death_notice_fires_once_however_often_it_is_observed(
    kernels: Callable[..., KernelHandle],
) -> None:
    """A session must not be told its kernel died on every poll."""
    deaths: list[str] = []
    handle = _started_kernel(kernels, on_death=lambda: deaths.append("died"))
    pid = handle.pid
    assert pid is not None
    psutil.Process(pid).kill()
    psutil.Process(pid).wait(timeout=10)

    for _ in range(5):
        assert handle.state == "dead"
    with pytest.raises(KernelDiedError):
        handle.execute("1 + 1", timeout=_EXEC_TIMEOUT)

    assert deaths == ["died"]


class _StubProvisioner:
    """Just enough of a ``jupyter_client`` provisioner to carry a pid."""

    def __init__(self, pid: int | None) -> None:
        self.pid = pid


class _StubManager:
    """A ``jupyter_client`` manager whose ``is_alive()`` answer is dictated.

    The one thing in this file that substitutes a double for a real kernel,
    and deliberately: the bug these tests guard is that the handle *believed*
    this object. ``is_alive()`` is ``Popen.poll() is None`` underneath, and on
    POSIX that answers ``None`` for a process that is already dead — when the
    poll cannot take ``_waitpid_lock`` because another thread is polling, and
    while a killed child is still an unreaped zombie. Neither can be staged
    with a real process on Windows, and a death-detection guarantee that only
    holds on one platform is how this reached CI in the first place.
    """

    def __init__(self, *, alive: bool, pid: int | None = 4242) -> None:
        self.provisioner = _StubProvisioner(pid)
        self._alive = alive
        self.polls = 0

    def is_alive(self) -> bool:
        self.polls += 1
        return self._alive


class _StubPsutilProcess:
    """A ``psutil.Process`` replacement whose reading of one pid is dictated.

    Stands in for the class rather than an instance, so ``psutil.Process(pid)``
    inside the handle returns it. A dead process has no memory to report, which
    is why :meth:`memory_info` refuses: :meth:`KernelHandle.status` reads the
    memory as well as the state.
    """

    def __init__(self, status: str) -> None:
        self._status = status
        self.pid = -1

    def __call__(self, pid: int) -> _StubPsutilProcess:
        self.pid = pid
        return self

    def is_running(self) -> bool:
        return True

    def status(self) -> str:
        return self._status

    def children(self, recursive: bool = False) -> list[_StubPsutilProcess]:
        return []

    def memory_info(self) -> object:
        raise psutil.NoSuchProcess(self.pid)


def _idle_handle_over(manager: object, **kwargs: object) -> KernelHandle:
    """A handle that believes it has an idle kernel driven by ``manager``.

    Reaches into the handle's privates because the seam under test *is*
    private: the point is what :attr:`KernelHandle.state` does with a manager
    that lies, and there is no public way to install one.
    """
    handle = KernelHandle(**kwargs)  # type: ignore[arg-type]
    handle._manager = manager  # type: ignore[assignment]
    handle._state = "idle"
    return handle


def test_a_zombie_kernel_is_dead_even_while_jupyter_client_says_alive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-015: an unreaped corpse is a dead kernel, whatever the library says.

    This is the regression. ``jupyter_client`` reported a SIGKILLed kernel as
    alive, so ``state`` stayed ``"idle"``, ``needs_restart`` stayed false and
    the death callback never fired — the session went on offering a kernel
    that no longer existed.
    """
    deaths: list[str] = []
    manager = _StubManager(alive=True)
    handle = _idle_handle_over(manager, on_death=lambda: deaths.append("died"))
    monkeypatch.setattr(psutil, "Process", _StubPsutilProcess(psutil.STATUS_ZOMBIE))

    assert handle.state == "dead"
    assert handle.status().state == "dead"
    assert handle.is_alive() is False
    assert deaths == ["died"]
    assert manager.polls > 0, "the manager must still be polled, because its poll is what reaps the child"


def test_a_vanished_kernel_is_dead_even_while_jupyter_client_says_alive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same reading on Windows, which has no zombie state: the pid is gone."""

    def _no_such_process(pid: int) -> psutil.Process:
        raise psutil.NoSuchProcess(pid)

    deaths: list[str] = []
    handle = _idle_handle_over(_StubManager(alive=True), on_death=lambda: deaths.append("died"))
    monkeypatch.setattr(psutil, "Process", _no_such_process)

    assert handle.state == "dead"
    assert deaths == ["died"]


def test_the_death_of_a_zombie_kernel_is_reported_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Polling the kernel list must not tell the session its kernel died again."""
    deaths: list[str] = []
    handle = _idle_handle_over(_StubManager(alive=True), on_death=lambda: deaths.append("died"))
    monkeypatch.setattr(psutil, "Process", _StubPsutilProcess(psutil.STATUS_ZOMBIE))

    for _ in range(5):
        assert handle.state == "dead"

    assert deaths == ["died"]


def test_a_process_the_platform_will_not_read_leaves_the_verdict_to_the_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed reading must not kill a healthy kernel.

    ``psutil`` can refuse a process it can see — a hardened host, a sandbox,
    a container that hides ``/proc``. Treating "I cannot tell" as "dead"
    would retire every kernel in the project on such a machine, which is a
    worse failure than the one being fixed.
    """

    def _access_denied(pid: int) -> psutil.Process:
        raise psutil.AccessDenied(pid)

    deaths: list[str] = []
    handle = _idle_handle_over(_StubManager(alive=True), on_death=lambda: deaths.append("died"))
    monkeypatch.setattr(psutil, "Process", _access_denied)

    assert handle.state == "idle"
    assert handle.is_alive() is True
    assert deaths == []


def test_a_kernel_with_no_pid_yet_leaves_the_verdict_to_the_manager() -> None:
    """A provisioner that has not published a pid is not evidence of a death."""
    deaths: list[str] = []
    handle = _idle_handle_over(_StubManager(alive=True, pid=None), on_death=lambda: deaths.append("died"))

    assert handle.state == "idle"
    assert deaths == []


def test_the_manager_still_settles_a_death_the_pid_reading_missed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Either reading may condemn the kernel; the pid check only adds to the manager.

    A pid can be reused by an unrelated process between the death and the
    poll, and then the direct reading says "running" about something that is
    not the kernel at all.
    """
    deaths: list[str] = []
    handle = _idle_handle_over(_StubManager(alive=False), on_death=lambda: deaths.append("died"))
    monkeypatch.setattr(psutil, "Process", _StubPsutilProcess(psutil.STATUS_RUNNING))

    assert handle.state == "dead"
    assert deaths == ["died"]


def test_stopping_a_kernel_is_not_a_death(kernels: Callable[..., KernelHandle]) -> None:
    """Closing a session is not a failure, so the death notice must stay quiet."""
    deaths: list[str] = []
    handle = _started_kernel(kernels, on_death=lambda: deaths.append("died"))

    handle.stop()

    assert deaths == []


# ---------------------------------------------------------------------------
# Memory and the kernel list (FR-016)
# ---------------------------------------------------------------------------


def test_memory_is_reported_for_a_live_kernel(kernels: Callable[..., KernelHandle]) -> None:
    """FR-016 lists each kernel with its memory, so there must be a figure."""
    handle = _started_kernel(kernels)

    memory = handle.memory_bytes()

    assert memory is not None
    assert memory > 1_000_000, "a Python process holding an interpreter is not this small"
    assert handle.status().memory_bytes is not None


def test_memory_grows_when_the_kernel_holds_data(kernels: Callable[..., KernelHandle]) -> None:
    """The figure tracks the interpreter, rather than being a constant.

    This is the assertion that catches the Windows redirector: reading only
    the process ``jupyter_client`` launched reports the same few megabytes
    before and after a sixty-four-megabyte allocation, because that process is
    a launcher and the data is in its child.
    """
    handle = _started_kernel(kernels)
    before = handle.memory_bytes()
    assert before is not None

    result = handle.execute("payload = b'x' * (64 * 1024 * 1024)", timeout=_EXEC_TIMEOUT)
    assert result.status == "ok"

    after = handle.memory_bytes()
    assert after is not None
    assert after - before > 32 * 1024 * 1024


def test_memory_covers_the_process_that_runs_the_code(kernels: Callable[..., KernelHandle]) -> None:
    """Whatever process holds the namespace is inside the figure FR-016 shows."""
    handle = _started_kernel(kernels)
    interpreter_pid = _interpreter_pid(handle)

    reported = handle.memory_bytes()

    assert reported is not None
    assert reported >= psutil.Process(interpreter_pid).memory_info().rss


def test_memory_and_status_are_readable_while_the_kernel_is_busy(
    kernels: Callable[..., KernelHandle], tmp_path: Path
) -> None:
    """The kernel list must work during the shallow freeze of ADR-054 §6.3.

    A reading taken through the kernel would queue behind the running cell and
    the list would hang for as long as the cell ran. This reads the process
    from outside, so it answers while the kernel is stuck.
    """
    handle = _started_kernel(kernels)
    marker = tmp_path / "busy"
    results: list[ExecutionResult] = []

    def run_the_hung_cell() -> None:
        # The assertion after the join is what covers the outcome.
        with contextlib.suppress(Exception):
            results.append(handle.execute(_spin_after_marker(marker), timeout=_EXEC_TIMEOUT))

    runner = threading.Thread(target=run_the_hung_cell, daemon=True)
    runner.start()
    try:
        _wait_for_marker(marker)

        started = time.monotonic()
        status = handle.status()
        elapsed = time.monotonic() - started

        assert status.state == "busy"
        assert status.memory_bytes is not None
        assert status.pid == handle.pid
        assert elapsed < 5.0, "reading a busy kernel's memory must not wait for its cell"
    finally:
        handle.interrupt()
        runner.join(timeout=_EXEC_TIMEOUT)

    assert results and results[0].interrupted


def test_memory_is_none_once_the_kernel_is_gone(kernels: Callable[..., KernelHandle]) -> None:
    """A stopped kernel has no memory to report, and says so."""
    handle = _started_kernel(kernels)
    handle.stop()

    assert handle.memory_bytes() is None
    assert handle.status().memory_bytes is None


def test_every_handle_has_its_own_identifier(kernels: Callable[..., KernelHandle]) -> None:
    """The list of FR-016 needs to tell two kernels apart."""
    first = kernels()
    second = kernels()

    assert first.kernel_id != second.kernel_id
    assert kernels(kernel_id="fixed").kernel_id == "fixed"


# ---------------------------------------------------------------------------
# Message conversion — pure functions, no process needed
# ---------------------------------------------------------------------------


def test_stream_messages_become_stream_outputs() -> None:
    """The nbformat shape a notebook store writes straight into a cell."""
    output = _as_output({"msg_type": "stream", "content": {"name": "stderr", "text": "boom"}})

    assert output == KernelOutput(output_type="stream", name="stderr", text="boom")


def test_display_data_and_updates_both_become_display_outputs() -> None:
    """An updated display is still a display, not a lost message."""
    display = _as_output({"msg_type": "display_data", "content": {"data": {"text/plain": "a"}, "metadata": {"k": 1}}})
    updated = _as_output({"msg_type": "update_display_data", "content": {"data": {"text/plain": "b"}}})

    assert display is not None
    assert display.output_type == "display_data"
    assert display.data == {"text/plain": "a"}
    assert display.metadata == {"k": 1}
    assert updated is not None
    assert updated.output_type == "display_data"
    assert updated.data == {"text/plain": "b"}


def test_error_messages_carry_the_traceback() -> None:
    """A cell's rendered traceback is what the notebook shows."""
    output = _as_output(
        {"msg_type": "error", "content": {"ename": "ValueError", "evalue": "bad", "traceback": ["line 1", "line 2"]}}
    )

    assert output is not None
    assert output.error == KernelError(ename="ValueError", evalue="bad", traceback=("line 1", "line 2"))


@pytest.mark.parametrize("msg_type", ["status", "execute_input", "clear_output", "comm_open"])
def test_non_output_messages_are_not_outputs(msg_type: str) -> None:
    """Only outputs become outputs; control traffic must not reach a cell."""
    assert _as_output({"msg_type": msg_type, "content": {}}) is None


def test_a_missing_traceback_is_tolerated() -> None:
    """A kernel that omits the traceback must not crash the collector."""
    output = _as_output({"msg_type": "error", "content": {"ename": "E", "evalue": "v"}})

    assert output is not None
    assert output.error is not None
    assert output.error.traceback == ()


def test_interrupted_is_true_only_for_a_keyboard_interrupt() -> None:
    """The flag the session reads to tell a stop apart from a failure."""
    interrupted = ExecutionResult(status="error", error=KernelError(ename="KeyboardInterrupt", evalue=""))
    failed = ExecutionResult(status="error", error=KernelError(ename="ValueError", evalue=""))
    fine = ExecutionResult(status="ok")

    assert interrupted.interrupted
    assert not failed.interrupted
    assert not fine.interrupted


def test_the_kernel_module_imports_no_jupyter_server() -> None:
    """FR-007: the session service is the kernel's only client.

    ``jupyter_server`` exists to let a frontend talk to a kernel directly,
    which would take admission, marking, observation, recording, and
    committing out of SciStudio's hands. The spec says it "is not used and
    must not be imported", so this reads the module's own imports rather than
    trusting a grep.
    """
    module_file = sys.modules["scistudio.explore.kernel"].__file__
    assert module_file is not None
    tree = ast.parse(Path(module_file).read_text(encoding="utf-8"))

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    assert not [name for name in imported if name.split(".")[0] == "jupyter_server"]
    assert "jupyter_client.manager" in imported, "the handle is built on jupyter_client, as FR-007 requires"
