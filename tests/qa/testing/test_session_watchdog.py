"""Keep the #2371 session watchdog from killing healthy CI runs (#2373)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PROBE = """
import os
import sys
from unittest.mock import patch

import pytest

with patch("faulthandler.dump_traceback_later") as timer:
    result = pytest.main([
        "-c", os.devnull, "--noconftest", "-p", "tests.conftest",
        "--collect-only", "-q", sys.argv[1],
    ])
    assert result == 0, result
    for call in timer.call_args_list:
        exits = call.kwargs.get("exit", call.args[3] if len(call.args) > 3 else False)
        assert not exits, f"Session watchdog must not kill a healthy suite: {call}"
"""


@pytest.mark.parametrize("worker", [None, "gw0"], ids=["controller", "worker"])
def test_session_setup_does_not_arm_process_killing_timer(tmp_path: Path, worker: str | None) -> None:
    """Exercise the real conftest hooks without arming or waiting for a timer.

    A fresh process avoids reapplying conftest's registry/entry-point patches
    in the outer suite. Intercept the timer before pytest loads the conftest,
    retaining calls after unconfigure cancels it. Per-test timeout plugins are
    deliberately excluded: this assertion concerns session-wide timers only.
    """
    probe = tmp_path / "test_probe.py"
    probe.write_text("def test_probe():\n    pass\n", encoding="utf-8")
    env = os.environ.copy()
    for key in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTEST_XDIST_WORKER", "SCISTUDIO_TEST_HANG_DUMP_SECONDS"):
        env.pop(key, None)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["CI"] = "true"
    env["PYTHONPATH"] = os.pathsep.join((str(_REPO_ROOT / "src"), str(_REPO_ROOT)))
    if worker is not None:
        env["PYTEST_XDIST_WORKER"] = worker
    result = subprocess.run(
        [sys.executable, "-c", _PROBE, str(probe)],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
