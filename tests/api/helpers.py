"""Helpers for API integration tests."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from scistudio.api.runtime import ApiRuntime, WorkflowRun
from scistudio.blocks.base.state import BlockState

_T = TypeVar("_T")

# #2186: these are failure-detection bounds, not performance assertions.
#
# Every helper below polls every 50 ms and returns the instant its condition
# holds, so a generous budget costs nothing when things work -- it only changes
# how long a genuine hang takes to report. A tight one buys nothing, and makes
# "the machine is busy" indistinguishable from "the code is broken". That is
# what these were doing: at 5 s and 10 s, seven to nine API tests failed under a
# full-suite parallel run on a 32-core Windows box while passing in CI and
# passing alone. Raising the workflow budget to 60 s took that from seven
# failures to one.
#
# The ceiling is pytest-timeout's per-test kill -- `timeout = 60` in
# pyproject.toml, the ADR-040 preflight that hard-kills Windows
# subprocess/asyncio hangs. A budget at or above 60 s can never elapse: the test
# is killed first and reports a thread dump instead of a clean assertion. These
# therefore sit under it with room for setup and teardown, rather than raising
# the ceiling and weakening that kill for every test in the suite.
WORKFLOW_TIMEOUT = 45.0
"""Budget for a whole workflow run to reach a terminal state."""

STEP_TIMEOUT = 30.0
"""Budget for one condition or one block state transition."""


def wait_for_condition(
    predicate: Callable[[], _T | None],
    *,
    timeout: float = STEP_TIMEOUT,
    interval: float = 0.05,
) -> _T:
    """Poll until *predicate* returns a truthy value, then return it."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(interval)
    raise AssertionError("Timed out waiting for condition.")


def wait_for_workflow_completion(
    runtime: ApiRuntime,
    workflow_id: str,
    *,
    timeout: float = WORKFLOW_TIMEOUT,
) -> WorkflowRun:
    """Wait until a workflow run finishes and surface task exceptions."""

    def _run_done() -> WorkflowRun | None:
        run = runtime.workflow_runs.get(workflow_id)
        if run is None or not run.task.done():
            return None
        return run

    run = wait_for_condition(_run_done, timeout=timeout)
    exc = run.task.exception()
    if exc is not None:
        raise exc
    return run


def wait_for_block_state(
    runtime: ApiRuntime,
    workflow_id: str,
    block_id: str,
    expected_state: str | BlockState,
    *,
    timeout: float = STEP_TIMEOUT,
) -> dict[str, BlockState]:
    """Wait until a specific block reaches *expected_state*."""
    target = BlockState(expected_state) if isinstance(expected_state, str) else expected_state

    def _state_match() -> dict[str, BlockState] | None:
        run = runtime.workflow_runs.get(workflow_id)
        if run is None:
            return None
        states = run.scheduler.block_states()
        if states.get(block_id) == target:
            return states
        return None

    return wait_for_condition(_state_match, timeout=timeout)


def build_linear_workflow(
    project_path: Path,
    *,
    workflow_id: str,
    middle_sleep_seconds: float = 0.0,
    final_sleep_seconds: float = 0.0,
) -> dict[str, Any]:
    """Create a three-node workflow payload backed by a real CSV file."""
    csv_path = project_path / "data" / "raw" / f"{workflow_id}.csv"
    csv_path.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
    return {
        "id": workflow_id,
        "version": "1.0.0",
        "description": f"workflow {workflow_id}",
        "nodes": [
            {
                "id": "load",
                "block_type": "io_block",
                "config": {"params": {"path": str(csv_path)}},
                "layout": {"x": 20.0, "y": 40.0},
            },
            {
                "id": "transform",
                "block_type": "process_block",
                "config": {"params": {"sleep_seconds": middle_sleep_seconds, "label": "middle"}},
                "layout": {"x": 240.0, "y": 40.0},
            },
            {
                "id": "final",
                "block_type": "process_block",
                "config": {"params": {"sleep_seconds": final_sleep_seconds, "label": "final"}},
                "layout": {"x": 460.0, "y": 40.0},
            },
        ],
        "edges": [
            {"source": "load:data", "target": "transform:input"},
            {"source": "transform:output", "target": "final:input"},
        ],
        "metadata": {"kind": "linear"},
    }
