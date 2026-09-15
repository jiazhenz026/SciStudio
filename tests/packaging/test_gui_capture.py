"""Run the desktop screenshot boundary regressions in the Python gate surface."""

import subprocess
from pathlib import Path

import pytest


def test_desktop_capture_boundary() -> None:
    root = Path(__file__).resolve().parents[2]
    subprocess.run(["node", "--test", "desktop/test/gui-capture.test.js"], cwd=root, check=True, timeout=30)


@pytest.mark.serial
def test_native_canvas_webgl_screenshot_after_control_change(tmp_path, monkeypatch) -> None:
    """Opt-in native compositor smoke; CI without a desktop keeps the unit gate."""
    import json
    import os

    from scistudio.panels.gui_debug import decode_screenshot

    binary = os.environ.get("SCISTUDIO_ELECTRON_BINARY")
    if not binary:
        pytest.skip("Native desktop smoke requires SCISTUDIO_ELECTRON_BINARY; platform evidence tracked by #2354")
    root = Path(__file__).resolve().parents[2]
    monkeypatch.delenv("ELECTRON_RUN_AS_NODE", raising=False)
    environment = {**os.environ, "SCISTUDIO_GUI_SMOKE_OUTPUT": str(tmp_path)}
    result = subprocess.run(
        [binary, "desktop/test/harness/gui-capture-smoke.js"],
        cwd=root,
        env=environment,
        text=True,
        capture_output=True,
        timeout=25,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    before = decode_screenshot(json.loads((tmp_path / "0.json").read_text()))
    after = decode_screenshot(json.loads((tmp_path / "1.json").read_text()))
    assert before[1:] == after[1:]
    assert before[0] != after[0], "Range input must change the captured iframe canvas and WebGL pixels"
    evidence = root / ".workflow/local/gui-smoke"
    evidence.mkdir(exist_ok=True, parents=True)
    (evidence / "before.png").write_bytes(before[0])
    (evidence / "after.png").write_bytes(after[0])
