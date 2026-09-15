"""#2362 — a run's captured tracebacks belong to that run.

``_run_block_errors`` is a module-global keyed by ``(workflow_id, block_id)``
and was never cleared, while ``get_run_status`` returns ``raw_errors`` whatever
the run's state. A traceback therefore outlived the run that produced it: the
agent asked about a ``succeeded`` run and was handed the failure it had just
fixed, and after a project switch it was handed a failure from a project with a
workflow of the same name — absolute paths and all.

The capture now resets on ``workflow_started``, which both run entry points
(``execute`` and ``execute_from``) emit before dispatching any block.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from scistudio.ai.agent.mcp import _context
from scistudio.ai.agent.mcp.tools_workflow import _errors


class _EventBus:
    """Minimal subscribe/emit bus matching the engine's surface."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Any]] = {}

    def subscribe(self, event_type: str, handler: Any) -> None:
        self._subscribers.setdefault(event_type, []).append(handler)

    async def emit(self, event: Any) -> None:
        for handler in self._subscribers.get(event.event_type, []):
            await handler(event)


class _Event:
    def __init__(self, event_type: str, block_id: str | None, data: dict[str, Any]) -> None:
        self.event_type = event_type
        self.block_id = block_id
        self.data = data


class _Ctx:
    def __init__(self, event_bus: _EventBus) -> None:
        self.event_bus = event_bus


@pytest.fixture(autouse=True)
def _isolated_capture() -> Any:
    _errors._run_block_errors.clear()
    _errors._error_subscriber_installed = False
    yield
    _errors._run_block_errors.clear()
    _errors._error_subscriber_installed = False
    _context.set_context(None)


def _install() -> _EventBus:
    bus = _EventBus()
    _context.set_context(_Ctx(bus))
    _errors._ensure_error_subscriber()
    return bus


def _fail(bus: _EventBus, workflow_id: str, block_id: str, message: str) -> None:
    asyncio.run(
        bus.emit(
            _Event(
                "block_error",
                block_id,
                {"workflow_id": workflow_id, "error": message, "error_summary": message},
            )
        )
    )


def _start(bus: _EventBus, workflow_id: str) -> None:
    asyncio.run(bus.emit(_Event("workflow_started", None, {"workflow_id": workflow_id})))


def test_a_new_run_discards_the_previous_runs_tracebacks() -> None:
    bus = _install()
    _fail(bus, "main", "load_1", "ValueError: the bug the agent just fixed")
    assert _errors._collect_run_errors("main")

    _start(bus, "main")

    assert _errors._collect_run_errors("main") == []


def test_a_run_of_another_workflow_leaves_this_ones_errors_alone() -> None:
    bus = _install()
    _fail(bus, "main", "load_1", "ValueError: boom")

    _start(bus, "other")

    assert len(_errors._collect_run_errors("main")) == 1


def test_a_same_named_workflow_in_the_next_project_starts_clean() -> None:
    """Every project's default workflow is ``main``; the key carries no project."""
    bus = _install()
    _fail(bus, "main", "load_1", "ValueError: from the previous project")

    # The user switches project and runs its own `main`.
    _start(bus, "main")
    _fail(bus, "main", "load_1", "TypeError: from this project")

    errors = _errors._collect_run_errors("main")
    assert len(errors) == 1
    assert "this project" in errors[0]["error"]


def test_errors_still_survive_until_the_next_run() -> None:
    """The capture exists so the agent can self-debug; it must not be eager."""
    bus = _install()
    _fail(bus, "main", "load_1", "ValueError: boom")
    _fail(bus, "main", "save_1", "OSError: also boom")

    collected = {record["block_id"] for record in _errors._collect_run_errors("main")}
    assert collected == {"load_1", "save_1"}


def test_forget_workflow_errors_is_scoped_to_one_workflow() -> None:
    _errors._run_block_errors[("main", "a")] = {"error": "x", "summary": None}
    _errors._run_block_errors[("other", "a")] = {"error": "y", "summary": None}

    _errors.forget_workflow_errors("main")

    assert list(_errors._run_block_errors) == [("other", "a")]
