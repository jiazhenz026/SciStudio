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
    import psutil

    deadline = time.time() + 10
    while time.time() < deadline and psutil.pid_exists(child_pid):
        time.sleep(0.05)
    assert not psutil.pid_exists(child_pid)
