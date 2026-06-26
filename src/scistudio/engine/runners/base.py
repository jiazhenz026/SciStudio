"""BlockRunner protocol -- run, check_status, cancel."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class BlockRunner(Protocol):
    """Protocol that every block runner must satisfy.

    A runner is responsible for executing a single block invocation,
    reporting its status, and supporting cancellation.
    """

    # NOTE(ADR-017, ADR-018): run() currently returns dict[str, Any].
    # Future evolution: return RunHandle (dataclass with run_id,
    # process_handle, result: asyncio.Future) defined in engine/scheduler.py.
    async def run(
        self,
        block: Any,
        inputs: dict[str, Any],
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute *block* with the given *inputs* and *config*.

        Parameters
        ----------
        block:
            The block instance to run.
        inputs:
            Mapping of port names to input data references.
        config:
            Execution-time configuration for this invocation.

        Returns
        -------
        dict[str, Any]
            Mapping of output port names to result data references.
            In the future this may evolve to a RunHandle containing
            a process_handle and an asyncio.Future for the result.
        """
        ...

    async def run_prompt(
        self,
        block: Any,
        inputs: dict[str, Any],
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """Run an interactive block's prompt phase in an isolated subprocess (ADR-051).

        Spawns the worker with the ADR-051 ``phase="prompt"`` marker so it runs
        ``block.prepare_prompt`` (not ``run``) and exits. Returns a dict with
        ``panel_payload`` (the JSON-safe window view), ``intermediate`` (a list
        of serialized storage references the engine holds across the pause), and
        ``environment``. Called by the scheduler before pausing an interactive
        block; the compute phase reuses :meth:`run`.
        """
        ...

    async def check_status(self, workflow_id: str, block_id: str) -> Any:
        """Query the current status of a previously started run.

        Parameters
        ----------
        workflow_id:
            The workflow run that owns the block (#1517: handles are keyed by
            ``(workflow_id, block_id)`` so concurrent runs don't collide).
        block_id:
            Block identifier within that run.

        Returns
        -------
        Any
            Runner-specific status descriptor.
        """
        ...

    async def cancel(self, workflow_id: str, block_id: str) -> None:
        """Request cancellation of a running execution.

        Parameters
        ----------
        workflow_id:
            The workflow run that owns the block (#1517).
        block_id:
            Block identifier within that run.
        """
        ...
