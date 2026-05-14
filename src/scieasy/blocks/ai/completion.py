"""CompletionWatcher — multi-signal completion detection for AI Block (ADR-035 §3.5).

Three completion paths, all supported simultaneously (first-wins):

| Signal | Trigger |
|---|---|
| (a) MCP tool   | Agent calls ``mcp__scieasy__finish_ai_block(outputs={...})``. The MCP tool writes ``signals/finish_ai_block.json`` under the run dir. |
| (b) FileWatcher| All declared ``expected_path`` files exist and have been size-stable for 2s. |
| (c) User button| User clicks "Mark done" in the AI Block tab header → engine writes ``signals/mark_done.json``. |

Path (a) is the only one with explicit per-port output naming. Paths (b)
and (c) read from the per-port ``expected_path`` only.
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
    from scieasy.blocks.ai.run_dir import RunDir

logger = logging.getLogger(__name__)


class WatcherCancelledError(RuntimeError):
    """Raised by :meth:`CompletionWatcher.wait` after :meth:`cancel` is called.

    Distinct from ``asyncio.CancelledError`` so synchronous callers can
    catch it without importing asyncio. Caller (``AIBlock.run``)
    translates this into a ``BlockState.CANCELLED`` transition.
    """


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

    Attributes:
        source: Which path fired.
        outputs: Resolved per-port output paths. For ``MCP_FINISH_TOOL``
            this is the dict the agent passed; for ``FILE_WATCHER`` and
            ``USER_MARK_DONE`` it is built from each port's ``expected_path``.
        detail: Source-specific metadata (timestamp, agent-supplied notes, etc.).
    """

    source: CompletionSource
    outputs: dict[str, Path]
    detail: dict[str, Any]


class CompletionWatcher:
    """Race the three completion paths defined in ADR-035 §3.5.

    Polling-loop implementation. Each iteration checks (a) → (b) → (c) in
    priority order. First match returns a :class:`CompletionEvent`.
    Honors ``timeout_sec`` — raises ``TimeoutError`` when exceeded.

    Internally tracks per-file size-stability for path (b) without
    instantiating ``scieasy.blocks.app.watcher.FileWatcher``: that
    watcher waits on a single directory + glob pattern, but AI Block's
    expected_paths can live in arbitrary directories. We replicate the
    stability heuristic (size unchanged for ``stability_period`` seconds)
    here. The interface remains compatible with ADR-035 §3.5.
    """

    def __init__(
        self,
        run_dir: RunDir,
        output_specs: dict[str, dict[str, Any]],
        project_dir: Path,
        poll_interval: float = 0.25,
        stability_period: float = 2.0,
    ) -> None:
        """Initialize the watcher.

        Args:
            run_dir: :class:`RunDir` instance — used to locate the MCP
                signal file and the user-mark-done signal file.
            output_specs: ``{port_name: {"expected_path": str, ...}}`` from
                the manifest. The watcher uses ``expected_path`` only.
            project_dir: Used to resolve relative ``expected_path`` values
                (per ADR-035 §3.3 "Relative paths resolve against the
                project directory").
            poll_interval: Seconds between polls. Default 250 ms — AI Block
                runs are user-visible; latency at signal time matters.
            stability_period: Seconds an output file must be size-stable
                before path (b) counts (per ADR-035 §3.5 row 2).
        """
        self.run_dir = run_dir
        self.project_dir = Path(project_dir)
        self.poll_interval = poll_interval
        self.stability_period = stability_period

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
        """Poll until one of the three signals fires.

        Returns the first :class:`CompletionEvent` to fire. Priority order
        on a single tick: (a) MCP > (b) FileWatcher > (c) user mark-done.
        (Order matters only when multiple signals race within one tick.)

        Raises:
            TimeoutError: deadline exceeded.
            ValueError: malformed JSON in MCP signal file (caller transitions
                block to ERROR; the bad signal file is preserved).
            asyncio.CancelledError: ``cancel()`` called from another thread.
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
                try:
                    payload = json.loads(mcp_path.read_text(encoding="utf-8"))
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

        Sets an internal cancel flag; the next poll iteration raises
        ``CancelledError``.
        """
        self._cancel_event.set()
