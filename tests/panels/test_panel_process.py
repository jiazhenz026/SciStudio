"""T-002 (ADR-054 MiniApp FR-006..FR-015): the resident panel subprocess.

Startup, calls, binary results, author errors, timeouts, crash, restart, stop, a
panel.py that spawns a child, and stdout going to the log while the call
protocol is unaffected. A faulty panel.py must never take the app down. POSIX is
exercised in full; the process-group assertions are guarded off Windows.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

from scistudio.engine.runners.process_handle import ProcessRegistry
from scistudio.panels import process as process_mod
from scistudio.panels.process import (
    CRASHED,
    RUNNING,
    START_FAILED,
    UNRESPONSIVE,
    PanelCallError,
    start_panel_process,
)

pytestmark = pytest.mark.serial


def _panel(tmp_path: Path, body: str) -> Path:
    directory = tmp_path / "m.app"
    directory.mkdir()
    (directory / "panel.json").write_text(
        '{"id":"m.app","api_version":"1.0","contexts":["miniapp"],"types":["Text"]}', encoding="utf-8"
    )
    (directory / "index.html").write_text("<p>app</p>", encoding="utf-8")
    (directory / "panel.py").write_text(body, encoding="utf-8")
    return directory


def _launch(tmp_path: Path, body: str, *, setup_payload=None):
    panel_dir = _panel(tmp_path, body)
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    registry = ProcessRegistry()
    process = start_panel_process(
        context_id="c" + "0" * 31,
        panel_dir=panel_dir,
        project_dir=project_dir,
        registry=registry,
        setup_payload=setup_payload,
    )
    return process, registry, project_dir


def _gone(pid: int) -> bool:
    """True once *pid* is no longer a live process.

    A killed grandchild is reparented to PID 1, and a container init that does
    not reap promptly leaves it a zombie, which ``psutil.pid_exists`` still
    reports. A zombie runs nothing, so it counts as gone — the same rule
    ``_posix_group_members`` applies when deciding what is still alive.
    """
    import psutil

    try:
        return psutil.Process(pid).status() == psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return True


def _await_state(process, *states, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.state in states:
            return process.state
        time.sleep(0.02)
    return process.state


def test_setup_runs_once_and_json_calls_return(tmp_path: Path) -> None:
    body = (
        "count = {'setup': 0}\n"
        "def setup(data):\n    count['setup'] += 1\n"
        "def add(a, b):\n    return a + b\n"
        "def setup_calls():\n    return count['setup']\n"
    )
    process, _registry, _ = _launch(tmp_path, body)
    try:
        assert _await_state(process, RUNNING) == RUNNING
        assert process.call("add", {"a": 2, "b": 3}).header["result"] == 5
        assert process.call("setup_calls", {}).header["result"] == 1
        assert process.call("add", {"a": 1, "b": 1}).header["result"] == 2
        assert process.call("setup_calls", {}).header["result"] == 1
    finally:
        process.stop()


def test_numpy_array_result_is_binary_with_dtype_and_shape(tmp_path: Path) -> None:
    body = (
        "import numpy as np\n"
        "def setup(data):\n    pass\n"
        "def grid():\n    return np.arange(6, dtype='float64').reshape(2, 3)\n"
    )
    process, _, _ = _launch(tmp_path, body)
    try:
        assert _await_state(process, RUNNING) == RUNNING
        job = process.call("grid", {})
        assert job.header["binary"] is True
        assert job.header["shape"] == [2, 3]
        assert job.header["dtype"] == "<f8"
        assert len(job.payload) == 48
    finally:
        process.stop()


def test_author_exception_returns_error_and_process_survives(tmp_path: Path) -> None:
    body = "def setup(data):\n    pass\ndef boom():\n    raise ValueError('nope')\ndef ping():\n    return 'pong'\n"
    process, _, _ = _launch(tmp_path, body)
    try:
        assert _await_state(process, RUNNING) == RUNNING
        job = process.call("boom", {})
        assert job.header["type"] == "error"
        assert job.header["error"]["type"] == "ValueError"
        assert "nope" in job.header["error"]["message"]
        # The process keeps running (FR-011).
        assert process.call("ping", {}).header["result"] == "pong"
        assert process.state == RUNNING
    finally:
        process.stop()


def test_unknown_function_is_an_error(tmp_path: Path) -> None:
    process, _, _ = _launch(tmp_path, "def setup(data):\n    pass\n")
    try:
        assert _await_state(process, RUNNING) == RUNNING
        job = process.call("missing", {})
        assert job.header["type"] == "error"
        assert job.header["error"]["type"] == "UnknownFunction"
    finally:
        process.stop()


def test_imported_name_is_not_callable(tmp_path: Path) -> None:
    body = "import math\ndef setup(data):\n    pass\ndef mine():\n    return 1\n"
    process, _, _ = _launch(tmp_path, body)
    try:
        assert _await_state(process, RUNNING) == RUNNING
        # ``sqrt`` is imported into the module but defined elsewhere: not callable.
        assert process.call("sqrt", {"x": 4}).header["type"] == "error"
        assert process.call("mine", {}).header["result"] == 1
    finally:
        process.stop()


def test_call_timeout_marks_unresponsive_then_busy(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SCISTUDIO_PANEL_CALL_TIMEOUT", "0.5")
    body = "import time\ndef setup(data):\n    pass\ndef hang():\n    time.sleep(30)\n"
    process, _, _ = _launch(tmp_path, body)
    try:
        assert _await_state(process, RUNNING) == RUNNING
        with pytest.raises(PanelCallError) as first:
            process.call("hang", {})
        assert first.value.code == "timeout"
        assert process.state == UNRESPONSIVE
        with pytest.raises(PanelCallError) as second:
            process.call("hang", {})
        assert second.value.code == "busy"
    finally:
        process.stop()


def test_result_over_budget_is_too_large(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SCISTUDIO_PANEL_MAX_RESULT_BYTES", "1024")
    body = "def setup(data):\n    pass\ndef big():\n    return 'x' * 5000\n"
    process, _, _ = _launch(tmp_path, body)
    try:
        assert _await_state(process, RUNNING) == RUNNING
        with pytest.raises(PanelCallError) as exc:
            process.call("big", {})
        assert exc.value.code == "too_large"
    finally:
        process.stop()


def test_crash_reports_process_exited_and_log_tail(tmp_path: Path) -> None:
    body = "import os\ndef setup(data):\n    pass\ndef die():\n    os._exit(7)\n"
    process, _, _ = _launch(tmp_path, body)
    try:
        assert _await_state(process, RUNNING) == RUNNING
        with pytest.raises(PanelCallError) as exc:
            process.call("die", {})
        assert exc.value.code == "process_exited"
        assert _await_state(process, CRASHED) == CRASHED
        status = process.status()
        assert status["state"] == CRASHED
        assert "log_tail" in status
    finally:
        process.stop()


def test_startup_timeout_reports_start_failed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SCISTUDIO_PANEL_STARTUP_TIMEOUT", "0.5")
    body = "import time\ndef setup(data):\n    time.sleep(30)\n"
    process, _, _ = _launch(tmp_path, body)
    try:
        assert _await_state(process, START_FAILED) == START_FAILED
        with pytest.raises(PanelCallError) as exc:
            process.call("anything", {})
        assert exc.value.code == "start_failed"
    finally:
        process.stop()


def test_import_error_in_setup_reports_start_failed(tmp_path: Path) -> None:
    body = "import a_package_that_is_not_installed_xyz\ndef setup(data):\n    pass\n"
    process, _, _ = _launch(tmp_path, body)
    try:
        assert _await_state(process, START_FAILED) == START_FAILED
        assert process.status()["state"] == START_FAILED
    finally:
        process.stop()


def test_stdout_print_goes_to_log_not_the_channel(tmp_path: Path) -> None:
    body = (
        "def setup(data):\n    print('hello from setup')\n"
        "def echo(text):\n    print('printing ' + text)\n    return text\n"
    )
    process, _, _ = _launch(tmp_path, body)
    try:
        assert _await_state(process, RUNNING) == RUNNING
        assert process.call("echo", {"text": "abc"}).header["result"] == "abc"
        time.sleep(0.1)
        log = process.log_path.read_text(encoding="utf-8")
        assert "hello from setup" in log
        assert "printing abc" in log
    finally:
        process.stop()


def test_stop_ends_the_process_tree(tmp_path: Path) -> None:
    process, registry, _ = _launch(tmp_path, "def setup(data):\n    pass\n")
    assert _await_state(process, RUNNING) == RUNNING
    pid = process._popen.pid
    process.stop()
    deadline = time.time() + 10
    import psutil

    while time.time() < deadline and psutil.pid_exists(pid):
        time.sleep(0.05)
    assert not psutil.pid_exists(pid)
    assert registry.get_handle(process_mod.REGISTRY_NAMESPACE, f"context-{process.context_id}") is None


@pytest.mark.skipif(sys.platform == "win32", reason="process-group child cleanup asserted on POSIX")
def test_child_process_is_killed_on_stop(tmp_path: Path) -> None:
    body = (
        "import subprocess, sys, os\n"
        "child = {}\n"
        "def setup(data):\n"
        "    p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'])\n"
        "    child['pid'] = p.pid\n"
        "def child_pid():\n    return child['pid']\n"
    )
    process, _, _ = _launch(tmp_path, body)
    try:
        assert _await_state(process, RUNNING) == RUNNING
        child_pid = process.call("child_pid", {}).header["result"]
    finally:
        process.stop()
    deadline = time.time() + 10
    while time.time() < deadline and not _gone(child_pid):
        time.sleep(0.05)
    assert _gone(child_pid)


def test_a_class_defined_in_panel_py_is_not_callable(tmp_path: Path) -> None:
    # FR-007 names functions. A class defined in panel.py is callable and
    # carries the module's __module__, but it is not part of the call surface.
    body = (
        "class Widget:\n"
        "    def __init__(self, *args, **kwargs):\n        pass\n"
        "def setup(data):\n    pass\n"
        "def mine():\n    return 1\n"
    )
    process, _, _ = _launch(tmp_path, body)
    try:
        assert _await_state(process, RUNNING) == RUNNING
        job = process.call("Widget", {})
        assert job.header["type"] == "error"
        assert job.header["error"]["type"] == "UnknownFunction"
        assert process.call("mine", {}).header["result"] == 1
    finally:
        process.stop()


@pytest.mark.skipif(sys.platform == "win32", reason="child memory accounting asserted on POSIX")
def test_resident_memory_counts_the_children_the_panel_started(tmp_path: Path) -> None:
    # FR-015 shows the MiniApp's resident memory, and US7 has a panel.py that
    # starts a child process: the root process alone under-reports what the
    # MiniApp holds.
    body = (
        "import subprocess, sys\n"
        "child = {}\n"
        "def setup(data):\n"
        "    p = subprocess.Popen([sys.executable, '-c',"
        ' \'import time; block = bytearray(96 * 1024 * 1024); block[::4096] = b"x" * len(block[::4096]);'
        " time.sleep(300)'])\n"
        "    child['pid'] = p.pid\n"
        "def child_pid():\n    return child['pid']\n"
    )
    process, _, _ = _launch(tmp_path, body)
    try:
        assert _await_state(process, RUNNING) == RUNNING
        child_pid = process.call("child_pid", {}).header["result"]
        import psutil

        root = psutil.Process(process._popen.pid)
        child = psutil.Process(child_pid)
        # The child touches its pages lazily; wait for them to be resident.
        deadline = time.time() + 30
        while time.time() < deadline and child.memory_info().rss < 32 * 1024 * 1024:
            time.sleep(0.1)
        child_rss = child.memory_info().rss
        assert child_rss >= 32 * 1024 * 1024
        total = process.resident_memory()
        assert total is not None
        # The figure covers the root AND the child; the root alone cannot reach
        # this even allowing for the drift between the three readings.
        assert total >= root.memory_info().rss + child_rss // 2
        assert process.status()["resident_memory"] == pytest.approx(total, rel=0.5)
    finally:
        process.stop()


def test_a_response_for_another_call_is_refused(tmp_path: Path, monkeypatch) -> None:
    # The pipe is strictly serial, so a response whose id is not the call being
    # awaited means the channel desynchronised. Delivering those bytes to the
    # waiting caller would answer one question with another's answer, so the
    # call fails and the process is ended instead.
    real = process_mod.recv_frame

    def mangled(stream, **kwargs):
        header, payload = real(stream, **kwargs)
        if header.get("type") in ("result", "error"):
            header = dict(header, id=-1)
        return header, payload

    process, _, _ = _launch(tmp_path, "def setup(data):\n    pass\ndef ping():\n    return 'pong'\n")
    try:
        assert _await_state(process, RUNNING) == RUNNING
        monkeypatch.setattr(process_mod, "recv_frame", mangled)
        with pytest.raises(PanelCallError) as exc:
            process.call("ping", {})
        assert exc.value.code == "process_exited"
        assert _await_state(process, CRASHED) == CRASHED
    finally:
        monkeypatch.setattr(process_mod, "recv_frame", real)
        process.stop()


def test_the_child_exits_when_the_backend_pipe_closes(tmp_path: Path) -> None:
    # FR-009: the subprocess must exit when the pipe from the backend closes, so
    # it cannot outlive a backend that died. Nothing signals or kills it here —
    # the request pipe is simply closed, as it would be if the backend vanished.
    process, _, _ = _launch(tmp_path, "def setup(data):\n    pass\ndef ping():\n    return 'pong'\n")
    try:
        assert _await_state(process, RUNNING) == RUNNING
        process._request.close()
        # A zombie still answers pid_exists, so wait on the child itself: it
        # must exit on its own, with nothing signalling or killing it.
        assert process._popen.wait(timeout=15) is not None
    finally:
        process.stop()


def test_shutdown_terminate_all_ends_the_panel_tree(tmp_path: Path) -> None:
    # FR-008/SC-004: the handle lives in the application registry whose
    # terminate_all runs at shutdown, and it owns a live process for as long as
    # anything the panel started is alive, so shutdown reaches the whole tree.
    body = (
        "import subprocess, sys\n"
        "child = {}\n"
        "def setup(data):\n"
        "    p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(300)'])\n"
        "    child['pid'] = p.pid\n"
        "def child_pid():\n    return child['pid']\n"
    )
    process, registry, _ = _launch(tmp_path, body)
    assert _await_state(process, RUNNING) == RUNNING
    child_pid = process.call("child_pid", {}).header["result"]
    handle = registry.get_handle(process_mod.REGISTRY_NAMESPACE, f"context-{process.context_id}")
    assert handle is not None and handle.owns_live_process()
    registry.terminate_all(grace_period_sec=1.0)
    deadline = time.time() + 10
    while time.time() < deadline and (not _gone(child_pid) or process._popen.poll() is None):
        time.sleep(0.05)
    assert process._popen.poll() is not None
    assert _gone(child_pid)
    process.stop()


def test_a_json_result_larger_than_the_frame_header_cap_is_delivered(tmp_path: Path) -> None:
    # A JSON result travels as the frame's raw tail: the header is capped at
    # MAX_HEADER_BYTES, while a result may use the whole (larger) result budget.
    from scistudio.panels.protocol import MAX_HEADER_BYTES

    size = MAX_HEADER_BYTES * 2
    body = f"def setup(data):\n    pass\ndef big():\n    return 'x' * {size}\ndef ping():\n    return 'pong'\n"
    process, _, _ = _launch(tmp_path, body)
    try:
        assert _await_state(process, RUNNING) == RUNNING
        job = process.call("big", {})
        assert job.header["result"] == "x" * size
        assert job.payload == b""
        assert process.call("ping", {}).header["result"] == "pong"
        assert process.state == RUNNING
    finally:
        process.stop()


def test_an_author_exception_with_a_huge_message_does_not_end_the_process(tmp_path: Path) -> None:
    from scistudio.panels.protocol import MAX_HEADER_BYTES

    size = MAX_HEADER_BYTES * 2
    body = (
        f"def setup(data):\n    pass\ndef boom():\n    raise ValueError('y' * {size})\ndef ping():\n    return 'pong'\n"
    )
    process, _, _ = _launch(tmp_path, body)
    try:
        assert _await_state(process, RUNNING) == RUNNING
        job = process.call("boom", {})
        assert job.header["type"] == "error"
        assert job.header["error"]["type"] == "ValueError"
        assert job.header["error"]["message"].endswith("[truncated]")
        assert process.call("ping", {}).header["result"] == "pong"
    finally:
        process.stop()


def test_an_exit_between_calls_is_reported_without_a_call(tmp_path: Path) -> None:
    # FR-015: a panel.py that exits while no call is queued is reported as
    # crashed, with its log tail, and leaves the registry, without the page
    # having to attempt a call first.
    body = (
        "import os, sys, threading\n"
        "def setup(data):\n    pass\n"
        "def die_later():\n"
        "    def _go():\n"
        "        sys.stderr.write('panel going away\\n'); sys.stderr.flush(); os._exit(3)\n"
        "    threading.Timer(0.3, _go).start()\n"
        "    return 'scheduled'\n"
    )
    process, registry, _ = _launch(tmp_path, body)
    try:
        assert _await_state(process, RUNNING) == RUNNING
        assert process.call("die_later", {}).header["result"] == "scheduled"
        deadline = time.time() + 10
        status = process.status()
        while time.time() < deadline and status["state"] != CRASHED:
            time.sleep(0.05)
            status = process.status()
        assert status["state"] == CRASHED
        assert status["exit_code"] == 3
        assert "panel going away" in status["log_tail"]
        deadline = time.time() + 10
        key = f"context-{process.context_id}"
        while time.time() < deadline and registry.get_handle(process_mod.REGISTRY_NAMESPACE, key) is not None:
            time.sleep(0.05)
        assert registry.get_handle(process_mod.REGISTRY_NAMESPACE, key) is None
        with pytest.raises(PanelCallError) as exc:
            process.call("die_later", {})
        assert exc.value.code == "process_exited"
    finally:
        process.stop()


class _FakeWindowsOps:
    """Records the Windows containment steps without touching real Win32 APIs."""

    def __init__(self, *, job: object = "job", assign: bool = True, resume: bool = True) -> None:
        self.job, self.assign, self.resume = job, assign, resume
        self.calls: list[tuple[str, object]] = []

    def create_process_group(self, popen_kwargs):
        popen_kwargs["creationflags"] = popen_kwargs.get("creationflags", 0) | 0x200
        return popen_kwargs

    def create_job_object(self):
        self.calls.append(("create_job_object", None))
        return self.job

    def assign_to_job(self, job, pid):
        self.calls.append(("assign_to_job", pid))
        return self.assign

    def resume_process(self, pid):
        self.calls.append(("resume_process", pid))
        return self.resume

    def close_job_object(self, job):
        self.calls.append(("close_job_object", job))


class _FakePopen:
    def __init__(self, args, **kwargs) -> None:
        self.args, self.kwargs = args, kwargs
        self.pid = 4242
        self.stdin = self.stdout = None
        self.killed = False
        _FakePopen.last = self

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout=None):
        return 1

    def poll(self):
        return None


def _windows_launch(tmp_path: Path, monkeypatch, ops: _FakeWindowsOps):
    monkeypatch.setattr(process_mod.sys, "platform", "win32")
    monkeypatch.setattr(process_mod, "get_platform_ops", lambda: ops)
    monkeypatch.setattr(process_mod.subprocess, "Popen", _FakePopen)
    monkeypatch.setattr(process_mod.PanelProcess, "start", lambda self: None)
    _FakePopen.last = None
    panel_dir = _panel(tmp_path, "def setup(data):\n    pass\n")
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    registry = ProcessRegistry()
    kwargs = dict(
        context_id="w" + "0" * 31,
        panel_dir=panel_dir,
        project_dir=project_dir,
        registry=registry,
        setup_payload=None,
    )
    return registry, kwargs


def test_windows_panel_is_launched_suspended_and_resumed_only_once_contained(tmp_path: Path, monkeypatch) -> None:
    ops = _FakeWindowsOps()
    registry, kwargs = _windows_launch(tmp_path, monkeypatch, ops)
    process = start_panel_process(**kwargs)
    popen = _FakePopen.last
    assert popen.kwargs["creationflags"] & process_mod._CREATE_SUSPENDED
    assert popen.kwargs["creationflags"] & 0x200  # the process-group flag is kept
    assert [name for name, _ in ops.calls] == ["create_job_object", "assign_to_job", "resume_process"]
    assert process.handle.job_object == "job"
    assert registry.get_handle(process_mod.REGISTRY_NAMESPACE, f"context-{process.context_id}") is not None


@pytest.mark.parametrize(
    ("ops_kwargs", "expected"),
    [
        ({"assign": False}, ["create_job_object", "assign_to_job", "close_job_object"]),
        ({"resume": False}, ["create_job_object", "assign_to_job", "resume_process", "close_job_object"]),
    ],
)
def test_windows_panel_that_cannot_be_contained_never_runs(tmp_path: Path, monkeypatch, ops_kwargs, expected) -> None:
    from scistudio.panels.targets import PanelError

    ops = _FakeWindowsOps(**ops_kwargs)
    registry, kwargs = _windows_launch(tmp_path, monkeypatch, ops)
    with pytest.raises(PanelError) as exc:
        start_panel_process(**kwargs)
    assert exc.value.code == "containment_unavailable"
    assert [name for name, _ in ops.calls] == expected
    assert _FakePopen.last.killed
    assert registry.get_handle(process_mod.REGISTRY_NAMESPACE, f"context-{kwargs['context_id']}") is None


def test_windows_panel_is_not_started_without_a_job_object(tmp_path: Path, monkeypatch) -> None:
    from scistudio.panels.targets import PanelError

    ops = _FakeWindowsOps(job=None)
    registry, kwargs = _windows_launch(tmp_path, monkeypatch, ops)
    with pytest.raises(PanelError) as exc:
        start_panel_process(**kwargs)
    assert exc.value.code == "containment_unavailable"
    assert _FakePopen.last is None
    assert registry.get_handle(process_mod.REGISTRY_NAMESPACE, f"context-{kwargs['context_id']}") is None
