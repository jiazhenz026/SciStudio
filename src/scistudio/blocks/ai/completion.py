"""CompletionWatcher — detect when an AI Block's agent has finished.

An AI Block run can finish in three ways, all watched at once (whichever
happens first wins):

1. The agent calls the ``mcp__scistudio__finish_ai_block`` tool, naming the
   output files it produced (the tool writes ``signals/finish_ai_block.json``
   under the run directory).
2. Every declared output file exists and has held a steady size for a couple
   of seconds.
3. The user clicks "Mark done" in the AI Block tab (which writes
   ``signals/mark_done.json``).

Only the first path names outputs per port explicitly; the other two read
each port's configured expected path.
"""

from __future__ import annotations

import contextlib
import json
import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scistudio.blocks.ai.run_dir import RunDir

logger = logging.getLogger(__name__)


class WatcherCancelledError(RuntimeError):
    """Raised by :meth:`CompletionWatcher.wait` after :meth:`cancel` is called.

    A dedicated exception (rather than ``asyncio.CancelledError``) so
    synchronous callers can catch it without importing asyncio. The AI Block
    translates it into a cancelled run.
    """


class CompletionSource(Enum):
    """Which of the three completion paths finished an AI Block run."""

    MCP_FINISH_TOOL = "mcp_finish_tool"
    """The agent called the ``mcp__scistudio__finish_ai_block`` tool."""

    FILE_WATCHER = "file_watcher"
    """Every declared output file exists and held a steady size briefly."""

    USER_MARK_DONE = "user_mark_done"
    """The user clicked "Mark done" in the tab header."""


@dataclass(frozen=True)
class CompletionEvent:
    """A single completion signal from an AI Block run.

    Records which path finished the run and where the outputs landed.
    """

    source: CompletionSource
    """Which of the three completion paths fired."""

    outputs: dict[str, Path]
    """Resolved output file path per port name. For the agent's ``finish`` tool
    this is what the agent reported; for the file-watcher and "Mark done" paths
    it is built from each port's configured expected path."""

    detail: dict[str, Any]
    """Extra metadata about the signal (timestamp, agent-supplied notes, etc.)."""


class CompletionWatcher:
    """Watch for the first of the three AI Block completion signals.

    Polls in a loop. Each tick checks, in priority order, the agent's
    ``finish`` tool, then the output files, then the user "Mark done" signal,
    and returns a :class:`CompletionEvent` for the first that fires. Honors an
    optional timeout, raising ``TimeoutError`` when it elapses.

    It tracks output-file size stability itself rather than reusing the app
    file watcher, because an AI Block's output files can live in any directory
    while that watcher follows a single directory and glob pattern.

    Example:
        >>> watcher = CompletionWatcher(run_dir, output_specs, project_dir)  # doctest: +SKIP
        >>> event = watcher.wait(timeout_sec=None)  # blocks until done  # doctest: +SKIP
        >>> event.source  # doctest: +SKIP
        <CompletionSource.FILE_WATCHER: 'file_watcher'>
    """

    def __init__(
        self,
        run_dir: RunDir,
        output_specs: dict[str, dict[str, Any]],
        project_dir: Path,
        poll_interval: float = 0.25,
        stability_period: float = 2.0,
    ) -> None:
        """Set up the watcher.

        Args:
            run_dir: :class:`RunDir` for this run — used to find the agent's
                ``finish`` signal file and the user "Mark done" file.
            output_specs: ``{port_name: {"expected_path": str, ...}}`` from the
                manifest. The watcher uses ``expected_path`` only.
            project_dir: Base directory used to resolve relative
                ``expected_path`` values.
            poll_interval: Seconds between polls. Default 250 ms — runs are
                user-visible, so latency at finish time matters.
            stability_period: Seconds an output file must hold a steady size
                before the file-watcher path counts it as done.
        """
        self.run_dir = run_dir
        """:class:`RunDir` for this run; the signal files live under it."""
        self.project_dir = Path(project_dir)
        """Base directory for resolving relative output paths."""
        self.poll_interval = poll_interval
        """Seconds between polls of the completion signals."""
        self.stability_period = stability_period
        """Seconds an output file must hold a steady size to count as done."""

        # Resolve each output's expected_path against project_dir up front.
        self._resolved: dict[str, Path] = {}
        for port_name, spec in output_specs.items():
            raw = spec.get("expected_path")
            if not raw:
                continue
            p = Path(raw)
            if not p.is_absolute():
                p = (self.project_dir / p).resolve()
            self._resolved[port_name] = p

        self._cancel_event = threading.Event()

    def wait(self, timeout_sec: float | None = None) -> CompletionEvent:
        """Poll until one of the three completion signals fires.

        On each tick the signals are checked in priority order — the agent's
        ``finish`` tool, then the output files, then user "Mark done" — which
        matters only when several fire within the same tick.

        Args:
            timeout_sec: Maximum seconds to wait, or ``None`` to wait
                indefinitely (the AI Block default).

        Returns:
            The first :class:`CompletionEvent` to fire.

        Raises:
            TimeoutError: ``timeout_sec`` elapsed before any signal fired.
            ValueError: the agent's ``finish`` signal file held malformed JSON;
                the bad file is left in place for inspection and the run is
                recorded as failed.
            WatcherCancelledError: :meth:`cancel` was called from another thread.
        """
        deadline = (time.monotonic() + timeout_sec) if timeout_sec is not None else None

        # Per-file size-stability tracking for path (b).
        last_size: dict[Path, int] = {}
        stable_since: dict[Path, float] = {}

        while True:
            if self._cancel_event.is_set():
                raise WatcherCancelledError("CompletionWatcher.wait was cancelled")

            # (a) MCP signal file
            mcp_path = self.run_dir.mcp_signal_path()
            if mcp_path.exists():
                # Issue #902: defend against the TOCTOU race where a
                # writer that opens the signal file with mode ``"w"``
                # truncates it to 0 bytes before writing JSON. If the
                # watcher polls inside that truncate window it reads
                # an empty string and ``json.loads("")`` raises
                # ``JSONDecodeError`` — which would otherwise surface
                # as a spurious ``ValueError("malformed MCP signal")``.
                # Tests/fixtures use atomic temp+replace (see
                # ``tests/blocks/ai/conftest.py::_atomic_write_signal``);
                # production agents historically also use atomic writes
                # (#962 / #909), but we cannot assume every MCP writer
                # is atomic. Treat empty / whitespace-only content as
                # "file mid-write" and retry on the next poll. Persistent
                # malformed JSON (non-empty but invalid) still raises.
                raw = mcp_path.read_text(encoding="utf-8")
                if not raw.strip():
                    # File created but content not yet flushed; let the
                    # next poll see the all-or-nothing post-replace state.
                    if deadline is not None and time.monotonic() >= deadline:
                        raise TimeoutError(
                            f"AIBlock completion: no signal within {timeout_sec}s "
                            f"(declared outputs: {list(self._resolved.keys())})."
                        )
                    time.sleep(self.poll_interval)
                    continue
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"AIBlock completion: malformed MCP signal at {mcp_path}: {exc}") from exc
                outputs_raw = payload.get("outputs", {}) if isinstance(payload, dict) else {}
                outputs: dict[str, Path] = {}
                for port_name, raw_path in outputs_raw.items():
                    if port_name not in self._resolved:
                        logger.warning(
                            "AIBlock MCP signal references undeclared port %r; ignoring.",
                            port_name,
                        )
                        continue
                    p = Path(str(raw_path))
                    if not p.is_absolute():
                        p = (self.project_dir / p).resolve()
                    outputs[port_name] = p
                # Ports the agent did NOT explicitly mention but DID declare:
                # fall back to the declared expected_path so validation can
                # check for them.
                for port_name, declared in self._resolved.items():
                    outputs.setdefault(port_name, declared)
                return CompletionEvent(
                    source=CompletionSource.MCP_FINISH_TOOL,
                    outputs=outputs,
                    detail={"raw_payload": payload},
                )

            # (b) FileWatcher path: all declared expected_path files exist
            # AND each one has been size-stable for stability_period seconds.
            if self._resolved:
                all_stable = True
                now = time.monotonic()
                for _port_name, p in self._resolved.items():
                    if not p.exists() or not p.is_file():
                        all_stable = False
                        # Reset tracking on disappearance.
                        last_size.pop(p, None)
                        stable_since.pop(p, None)
                        continue
                    try:
                        size = p.stat().st_size
                    except OSError:
                        all_stable = False
                        continue
                    if last_size.get(p) != size:
                        last_size[p] = size
                        stable_since[p] = now
                        all_stable = False
                    elif now - stable_since.get(p, now) < self.stability_period:
                        all_stable = False
                if all_stable:
                    return CompletionEvent(
                        source=CompletionSource.FILE_WATCHER,
                        outputs=dict(self._resolved),
                        detail={},
                    )

            # (c) User mark-done signal file
            mark_done = self.run_dir.mark_done_signal_path()
            if mark_done.exists():
                detail: dict[str, Any] = {}
                # Best-effort detail read; the existence of the file is
                # the signal — malformed JSON does not block completion.
                with contextlib.suppress(OSError, json.JSONDecodeError):
                    detail = json.loads(mark_done.read_text(encoding="utf-8"))
                return CompletionEvent(
                    source=CompletionSource.USER_MARK_DONE,
                    outputs=dict(self._resolved),
                    detail=detail if isinstance(detail, dict) else {},
                )

            # Deadline check
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError(
                    f"AIBlock completion: no signal within {timeout_sec}s "
                    f"(declared outputs: {list(self._resolved.keys())})."
                )

            # Tick.
            time.sleep(self.poll_interval)

    def cancel(self) -> None:
        """Cancel an in-flight :meth:`wait` from another thread.

        Sets an internal flag; the next poll in :meth:`wait` raises
        :class:`WatcherCancelledError`.
        """
        self._cancel_event.set()
