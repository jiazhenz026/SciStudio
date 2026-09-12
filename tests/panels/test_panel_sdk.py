"""T-004 (ADR-054 MiniApp FR-016/FR-003): the SDK exposes ``call`` only in the
miniapp context, and ``read`` there too, while preview/interactive never gain
``call``. Driven through the SDK's own standalone sample path under node; the
full host-driven SDK behaviour is covered by the frontend PanelFrame tests.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SDK = _ROOT / "src" / "scistudio" / "panels" / "sdk" / "1" / "scistudio-panel.js"
_HARNESS = Path(__file__).with_name("_sdk_harness.js")
_NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(_NODE is None, reason="node is required to exercise the SDK")


def _capabilities(context: str) -> dict[str, str]:
    result = subprocess.run(
        [_NODE, str(_HARNESS), str(_SDK), context],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return json.loads(result.stdout)


def test_miniapp_context_exposes_call_and_read() -> None:
    caps = _capabilities("miniapp")
    assert caps["call"] == "function"
    assert caps["read"] == "function"
    assert caps["save"] == "function"
    assert caps["open"] == "undefined"
    assert caps["writeBack"] == "undefined"


def test_preview_context_never_exposes_call() -> None:
    caps = _capabilities("preview")
    assert caps["call"] == "undefined"
    assert caps["read"] == "function"
    assert caps["open"] == "function"


def test_interactive_context_never_exposes_call_or_read() -> None:
    caps = _capabilities("interactive")
    assert caps["call"] == "undefined"
    assert caps["read"] == "undefined"
    assert caps["writeBack"] == "function"


def test_sdk_source_gates_call_on_the_miniapp_context() -> None:
    # A source-level guard so the invariant survives even where node is absent:
    # the only ``api.call =`` assignment lives inside the miniapp branch.
    source = _SDK.read_text(encoding="utf-8")
    assert source.count("api.call = function") == 1
    guard = source.index('api.context === "miniapp" && operations.indexOf("call")')
    assignment = source.index("api.call = function")
    assert guard < assignment


_CALL_HARNESS = Path(__file__).with_name("_sdk_call_harness.js")


def _call(mode: str) -> dict:
    result = subprocess.run(
        [_NODE, str(_CALL_HARNESS), str(_SDK), mode],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return json.loads(result.stdout)


def test_call_forwards_the_function_name_and_arguments() -> None:
    assert _call("result")["sent"] == {"fn": "compute", "args": {"x": 1}}


def test_call_resolves_with_an_ordinary_result() -> None:
    outcome = _call("result")
    assert outcome["outcome"] == "resolved"
    assert outcome["value"] == {"total": 42}


def test_call_rejects_on_an_error_body() -> None:
    # FR-011: a raising panel.py function answers HTTP 200 with
    # {error: {type, message, traceback}} and the process stays alive. The page
    # asked a question with no answer, so its promise must reject.
    outcome = _call("error")
    assert outcome["outcome"] == "rejected"
    assert outcome["code"] == "ValueError"
    assert outcome["message"] == "nope"
    assert outcome["traceback"] == "Traceback..."


def test_a_result_that_merely_carries_an_error_field_still_resolves() -> None:
    outcome = _call("error-like")
    assert outcome["outcome"] == "resolved"
    assert outcome["value"]["rows"] == 3
