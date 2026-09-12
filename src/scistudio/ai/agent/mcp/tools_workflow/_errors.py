"""Run-level error capture for the ``tools_workflow`` sub-package."""
# Maintainer context (kept outside generated API documentation):
# Run-level error capture for the ``tools_workflow`` sub-package.
#
# The engine emits ``block_error`` events whose ``data["error"]`` is the full
# Python traceback. The MCP layer surfaces it so the embedded agent can
# self-debug without copy/paste from the GUI.
#
# Extracted from the original single-file ``tools_workflow.py`` (#1431,
# umbrella #1427). No behavior change.
# Development references: #1427, #1431.

from __future__ import annotations

import logging
from typing import Any

from scistudio.ai.agent.mcp._context import get_context

logger = logging.getLogger(__name__)

_run_block_errors: dict[tuple[str, str], dict[str, Any]] = {}
"""``{(workflow_id, block_id): {"error": traceback, "summary": one_line}}``.

Holds the CURRENT run's failures only. The key names a workflow, not a run, and
the map is module-global for the life of the process, so a traceback left here
after a run finished was handed back verbatim by the next ``get_run_status`` —
which returns ``raw_errors`` whatever the run's state. The agent then read a
``succeeded`` run alongside the failure it had just fixed and "debugged" an
error that no longer existed; after a project switch it read a failure from a
different project entirely, absolute paths and all. :func:`_ensure_error_subscriber`
now clears a workflow's entries when that workflow starts running, so what is
in here always belongs to the run being asked about.
"""

_error_subscriber_installed: bool = False


def forget_workflow_errors(workflow_id: str) -> None:
    """Drop every captured failure for ``workflow_id``.

    Called when that workflow starts running: the previous run's tracebacks are
    not evidence about the new one, and — because the key carries no project —
    they may not even be evidence about this project.
    """
    # Development references: #2362.
    for key in [key for key in _run_block_errors if key[0] == workflow_id]:
        del _run_block_errors[key]


def _ensure_error_subscriber() -> None:
    """Install BLOCK_ERROR / WORKFLOW_STARTED subscribers on the runtime's event_bus.

    Idempotent + best-effort: if the context doesn't expose ``event_bus``
    (e.g. an MCP standalone-mode runtime stub used by tests), this is a
    no-op and ``get_run_status`` will simply return an empty ``errors``
    list.

    The ``workflow_started`` half is what keeps the captured errors run-scoped
    rather than merely workflow-scoped: both run entry points
    (``execute`` and ``execute_from``) emit it before dispatching any block, so
    a workflow's previous tracebacks are discarded the moment it runs again.
    """
    global _error_subscriber_installed
    if _error_subscriber_installed:
        return
    try:
        ctx = get_context()
    except Exception:
        return
    event_bus = getattr(ctx, "event_bus", None)
    if event_bus is None or not hasattr(event_bus, "subscribe"):
        return

    async def _capture(event: Any) -> None:
        data = getattr(event, "data", None) or {}
        if not isinstance(data, dict):
            return
        workflow_id = data.get("workflow_id")
        block_id = getattr(event, "block_id", None)
        error = data.get("error")
        summary = data.get("error_summary")
        if not workflow_id or not block_id or error is None:
            return
        _run_block_errors[(str(workflow_id), str(block_id))] = {
            "error": str(error),
            "summary": str(summary) if summary else None,
        }

    async def _reset(event: Any) -> None:
        data = getattr(event, "data", None) or {}
        if not isinstance(data, dict):
            return
        workflow_id = data.get("workflow_id")
        if workflow_id:
            forget_workflow_errors(str(workflow_id))

    try:
        event_bus.subscribe("block_error", _capture)
        event_bus.subscribe("workflow_started", _reset)
        _error_subscriber_installed = True
        logger.info("MCP: installed block_error capture subscriber")
    except Exception:
        logger.warning("MCP: failed to install block_error capture", exc_info=True)


def _collect_run_errors(run_id: str) -> list[dict[str, Any]]:
    """Return the captured block errors for ``run_id`` (its workflow_id)."""
    return [
        {"block_id": block_id, "error": record["error"], "summary": record["summary"]}
        for (workflow_id, block_id), record in _run_block_errors.items()
        if workflow_id == run_id
    ]


__all__ = [
    "_collect_run_errors",
    "_ensure_error_subscriber",
    "_error_subscriber_installed",
    "_run_block_errors",
    "forget_workflow_errors",
]
