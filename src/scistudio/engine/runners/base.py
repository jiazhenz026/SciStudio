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

    async def check_status(self, run_id: str) -> Any:
        """Query the current status of a previously started run.

        Parameters
        ----------
        run_id:
            Opaque identifier returned when the run was initiated.

        Returns
        -------
        Any
            Runner-specific status descriptor.
        """
        ...

    async def cancel(self, run_id: str) -> None:
        """Request cancellation of a running execution.

        Parameters
        ----------
        run_id:
            Opaque identifier of the run to cancel.
        """
        ...
