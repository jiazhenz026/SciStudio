"""Resolve the run an MCP tool call names.

``run_workflow`` returns the run's id: the lineage ``runs.run_id``, the name of
its ``run-<run_id>.log`` and the ``run_id`` stamped on every event the run
emits. The run tools accept that id and act on that run only. A workflow id is
still accepted for compatibility and stands for the latest run of that
workflow the active project holds.
"""

# Development references: #2401, #2433.

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def find_run(runs: Any, identifier: str) -> tuple[str, Any] | None:
    """Return ``(workflow_id, run)`` for the run *identifier* names, or ``None``.

    *identifier* is a run id, or a workflow id meaning that workflow's latest
    run. A run id wins when both could match.
    """
    if not isinstance(runs, Mapping):
        return None
    for workflow_id, run in list(runs.items()):
        if getattr(run, "run_id", None) == identifier:
            return str(workflow_id), run
    run = runs.get(identifier)
    if run is None:
        return None
    return identifier, run


def require_run(runs: Any, identifier: str) -> tuple[str, Any]:
    """Like :func:`find_run`, raising ``KeyError`` for an unknown identifier."""
    found = find_run(runs, identifier)
    if found is None:
        raise KeyError(f"Unknown run: {identifier}")
    return found


def run_identity(run: Any, fallback: str) -> str:
    """The run id of *run*, or *fallback* for a run that carries none."""
    run_id = getattr(run, "run_id", None)
    return str(run_id) if run_id else fallback


__all__ = ["find_run", "require_run", "run_identity"]
