"""CompletionWatcher — multi-signal completion detection for AI Block (skeleton).

ADR-035 §3.5 defines three completion paths, all supported simultaneously
(first-wins). This module wraps the polling logic that races them.

| Signal | Trigger |
|---|---|
| (a) MCP tool   | Agent calls ``mcp__scieasy__finish_ai_block(outputs={...})``. The MCP tool writes ``signals/finish_ai_block.json`` under the run dir. |
| (b) FileWatcher| All declared ``expected_path`` files exist and have been size-stable for 2s. |
| (c) User button| User clicks "Mark done" in the AI Block tab header → engine writes ``signals/mark_done.json``. |

Path (a) is the only one with explicit per-port output naming. Paths (b)
and (c) read from the per-port ``expected_path`` only.

Skeleton invariants (per skeleton-agent.md):
    * Every method body raises ``NotImplementedError``.
    * Each is preceded by a docstring + structured implementation plan.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class CompletionSource(Enum):
    """Which of the three paths fired (ADR-035 §3.5)."""

    MCP_FINISH_TOOL = "mcp_finish_tool"
    """Agent called ``mcp__scieasy__finish_ai_block``."""

    FILE_WATCHER = "file_watcher"
    """All ``expected_path`` files exist + size-stable for 2s."""

    USER_MARK_DONE = "user_mark_done"
    """User clicked "Mark done" in the tab header."""


@dataclass(frozen=True)
class CompletionEvent:
    """One completion signal.

    Attributes
    ----------
    source
        Which path fired.
    outputs
        Resolved per-port output paths. For ``MCP_FINISH_TOOL`` this is
        the dict the agent passed; for ``FILE_WATCHER`` and
        ``USER_MARK_DONE`` it is built from each port's ``expected_path``.
    detail
        Source-specific metadata (e.g., timestamp, agent-supplied notes).
    """

    source: CompletionSource
    outputs: dict[str, Path]
    detail: dict[str, Any]


class CompletionWatcher:
    """Race the three completion paths defined in ADR-035 §3.5.

    Implementation plan (per ADR-035 §3.5):
        * Constructor takes the run dir, the list of declared output ports
          with their ``expected_path`` values, and the project dir for
          resolving relative paths.
        * :meth:`wait()`: polling loop. Each iteration checks (a) → (b) → (c)
          in priority order. First match returns a :class:`CompletionEvent`.
          Honors ``timeout_sec`` — raises ``TimeoutError`` when exceeded.
        * Internally reuses :class:`scieasy.blocks.app.watcher.FileWatcher`
          for path (b) — do NOT reinvent the size-stability logic.

    References:
        ADR-035 §3.5 (table of three signals + precedence),
        src/scieasy/blocks/app/watcher.py (FileWatcher to reuse)
    """

    def __init__(
        self,
        run_dir: Any,  # forward ref to RunDir
        output_specs: dict[str, dict[str, Any]],
        project_dir: Path,
        poll_interval: float = 0.25,
        stability_period: float = 2.0,
    ) -> None:
        """Initialize the watcher.

        Parameters
        ----------
        run_dir
            :class:`scieasy.blocks.ai.run_dir.RunDir` instance — used to
            locate the MCP signal file and the user-mark-done signal file.
        output_specs
            ``{port_name: {"expected_path": str, "expected_type": str, ...}}``
            from the manifest. The watcher uses ``expected_path`` only.
        project_dir
            Used to resolve relative ``expected_path`` values (per ADR-035
            §3.3 "Relative paths resolve against the project directory").
        poll_interval
            Seconds between polls. Default tight (250 ms) since AI Block
            runs are user-visible and latency matters at signal time.
        stability_period
            Seconds an output file must be size-stable before path (b)
            counts (per ADR-035 §3.5 row 2).

        Implementation plan:
            1. Resolve each output's ``expected_path`` against ``project_dir``.
            2. Construct an internal :class:`FileWatcher` from the resolved
               paths' parent directories with appropriate glob patterns.
            3. Store all the above on ``self`` for :meth:`wait` to consume.

        Test plan:
            * test_init_resolves_relative_paths_against_project_dir
            * test_init_handles_absolute_expected_paths

        References: ADR-035 §3.3, §3.5
        """
        raise NotImplementedError("see comment block above")

    def wait(self, timeout_sec: float | None = None) -> CompletionEvent:
        """Poll until one of the three signals fires.

        Returns the first :class:`CompletionEvent` to fire. Priority order on
        a single tick: (a) MCP signal file > (b) FileWatcher all-files-stable
        > (c) user mark-done file. (Order matters only when multiple signals
        race within one poll interval.)

        Implementation plan (per ADR-035 §3.5):
            1. Compute deadline from ``timeout_sec`` (if supplied).
            2. Loop with ``poll_interval`` sleep:
               a. If ``run_dir.mcp_signal_path()`` exists → load JSON,
                  build :class:`CompletionEvent` with ``source=MCP_FINISH_TOOL``
                  and ``outputs`` from the agent's payload, return.
               b. Else if internal :class:`FileWatcher` reports all
                  expected paths satisfied → build event with
                  ``source=FILE_WATCHER`` and ``outputs`` from
                  ``expected_path`` values, return.
               c. Else if ``run_dir.mark_done_signal_path()`` exists →
                  build event with ``source=USER_MARK_DONE``, return.
               d. Else if deadline passed → ``TimeoutError``.
               e. Else sleep ``poll_interval``, continue.

        Edge cases:
            * MCP signal file is malformed JSON → log error, raise
              ``ValueError`` (caller transitions block to ERROR with
              detail referencing the bad signal file — preserved for
              post-mortem per ADR-035 §3.6).
            * MCP signal references an output port not declared in
              ``output_specs`` → log warning, ignore that key (extra
              outputs do not fail completion; missing outputs surface
              at validation stage in :meth:`AIBlock.run`).
            * ``output_specs`` is empty (no declared output ports) →
              path (b) trivially satisfies on first tick → effectively
              becomes wait-for-MCP-or-mark-done. Document this.
            * ``timeout_sec=None`` → wait forever (blocks until
              user closes tab; AIBlock.run() should always supply a
              timeout from ``config["timeout_sec"]``).

        Test plan:
            * test_wait_mcp_signal_returns_first
            * test_wait_file_watcher_returns_when_all_paths_stable
            * test_wait_user_mark_done_returns
            * test_wait_priority_mcp_beats_file_watcher_on_same_tick
            * test_wait_timeout_raises_TimeoutError
            * test_wait_malformed_mcp_signal_raises_ValueError
            * test_wait_extra_output_in_mcp_signal_logs_and_ignores

        References: ADR-035 §3.5
        """
        raise NotImplementedError("see comment block above")

    def cancel(self) -> None:
        """Cancel an in-flight :meth:`wait` from another thread.

        Implementation plan:
            Set an internal cancel flag; the next poll iteration checks
            it and raises ``CancelledError``. Used when the engine
            receives a workflow-cancel and needs to break the wait so
            the worker can transition to CANCELLED.

        Test plan:
            * test_cancel_breaks_wait

        References: ADR-035 §3.9 "* → CANCELLED"
        """
        raise NotImplementedError("see comment block above")
