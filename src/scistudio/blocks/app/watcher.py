"""Polling file watcher that detects an external app's output files.

:class:`FileWatcher` watches a directory and reports files that appear or change
after it starts. :class:`AppBlock` uses it to know when an external program has
finished writing its results. It polls on a timer, which is slower than an
OS file-event backend but works the same way on every platform and adds no
extra runtime dependency.
"""

from __future__ import annotations

import fnmatch
import time
from pathlib import Path
from typing import Any

from scistudio.stability import provisional

# Output detection is polling-based, which keeps the watcher free of any
# extra runtime dependency.


@provisional(since="0.3.1")
class ProcessExitedWithoutOutputError(RuntimeError):
    """The external app quit before writing any output files.

    Raised by :meth:`FileWatcher.wait_for_output` when the watched process ends
    while no expected output has appeared. :class:`AppBlock` treats this as the
    step being cancelled rather than failing.
    """

    pass


@provisional(since="0.3.1")
class FileWatcher:
    """Watch a directory for new or changed files matching glob patterns.

    :class:`AppBlock` uses this to tell when an external application has finished
    writing its results. After :meth:`start` takes a snapshot of the directory,
    :meth:`wait_for_output` blocks until files that appear or change settle
    (their modification time stops moving), then returns them. If a process
    handle is supplied and that process exits before producing any output, it
    raises :class:`ProcessExitedWithoutOutputError`.

    A process handle is any object whose liveness can be probed: a plain
    :class:`subprocess.Popen` (alive while ``poll()`` returns ``None``) or any
    object exposing an ``is_alive()`` method.

    Example:
        >>> from pathlib import Path
        >>> watcher = FileWatcher(Path("/tmp/outputs"), patterns=["*.csv"])
        >>> watcher.start()
        >>> files = watcher.wait_for_output()  # blocks until *.csv files settle
        >>> watcher.stop()
    """

    @provisional(since="0.3.1")
    def __init__(
        self,
        directory: Path,
        patterns: list[str],
        timeout: int | None = None,
        poll_interval: float = 0.5,
        process_handle: Any | None = None,
        stability_period: float = 2.0,
        done_marker: str | None = None,
    ) -> None:
        """Configure a watcher (it does not start watching until :meth:`start`).

        Args:
            directory: Directory to watch for output files.
            patterns: Glob patterns a file must match to count as output.
            timeout: Seconds to wait before raising :class:`TimeoutError`;
                ``None`` waits indefinitely.
            poll_interval: Seconds between directory scans.
            process_handle: Optional handle to the external process; when it
                reports the process has exited with no output, watching stops
                with :class:`ProcessExitedWithoutOutputError`.
            stability_period: Seconds a file's modification time must stay
                unchanged before it is treated as finished.
            done_marker: Optional glob; when a matching file appears, all other
                new files are returned at once (the marker itself excluded).
        """
        self.directory: Path = directory
        """Directory being watched for output files."""
        self.patterns: list[str] = patterns
        """Glob patterns a file must match to be reported as output."""
        self.timeout: int | None = timeout
        """Seconds to wait for output before timing out; ``None`` waits forever."""
        self.poll_interval: float = poll_interval
        """Seconds between successive scans of the watched directory."""
        self._process_handle: Any | None = process_handle
        self._stability_period: float = stability_period
        self._done_marker: str | None = done_marker
        self._baseline: dict[Path, float] = {}
        self._running: bool = False

    @provisional(since="0.3.1")
    def start(self) -> None:
        """Begin watching the directory for changes.

        Takes a snapshot of existing files so that only *new* or *modified*
        files are detected by :meth:`wait_for_output`.
        """
        self.directory.mkdir(parents=True, exist_ok=True)
        self._baseline = self._snapshot()
        self._running = True

    @provisional(since="0.3.1")
    def wait_for_output(self) -> list[Path]:
        """Block until output files are detected and return their paths.

        A new file must keep the same modification time for at least
        ``stability_period`` seconds before it is returned, so a file still
        being written is not picked up half-finished. If a ``done_marker`` glob
        is set and a matching file appears, all other new files are returned at
        once (the marker itself excluded).

        Returns:
            Sorted paths of the detected output files.

        Raises:
            RuntimeError: If called before :meth:`start`.
            ProcessExitedWithoutOutputError: If the watched process exits without
                producing any output.
            TimeoutError: If ``timeout`` seconds elapse with no matching files.
        """
        if not self._running:
            raise RuntimeError("FileWatcher has not been started.")

        deadline = None
        if self.timeout is not None:
            deadline = time.monotonic() + self.timeout

        # Track candidate files and when their mtime last changed.
        candidates: dict[Path, float] = {}  # path -> last known mtime
        stable_since: dict[Path, float] = {}  # path -> monotonic time when mtime stopped changing

        while self._running:
            current = self._snapshot()
            new_files = self._diff(current)

            # Check done marker — if present, return immediately.
            if self._done_marker and new_files:
                done_files = [f for f in new_files if fnmatch.fnmatch(f.name, self._done_marker)]
                if done_files:
                    return sorted(f for f in new_files if f not in done_files)

            # Update candidate tracking.
            for f in new_files:
                mtime = current[f]
                if f not in candidates or candidates[f] != mtime:
                    candidates[f] = mtime
                    stable_since[f] = time.monotonic()
                # If mtime unchanged, stable_since stays as-is.

            # Check if any candidates are stable.
            now = time.monotonic()
            fully_stable = sorted(
                f for f in candidates if f in stable_since and (now - stable_since[f]) >= self._stability_period
            )
            if fully_stable:
                return fully_stable

            # Check process liveness.
            if self._process_handle is not None and not self._handle_is_alive() and not new_files:
                # Give one last chance — return any candidates even if not fully stable.
                if candidates:
                    return sorted(candidates.keys())
                pid = getattr(self._process_handle, "pid", "unknown")
                raise ProcessExitedWithoutOutputError(f"External process (pid={pid}) exited without producing output")

            if deadline is not None and time.monotonic() >= deadline:
                # Return any candidates even if not fully stable on timeout.
                if candidates:
                    return sorted(candidates.keys())
                raise TimeoutError(
                    f"FileWatcher timed out after {self.timeout}s waiting for "
                    f"files matching {self.patterns} in {self.directory}"
                )
            time.sleep(self.poll_interval)

        return []

    @provisional(since="0.3.1")
    def stop(self) -> None:
        """Stop watching and release resources."""
        self._running = False

    def _handle_is_alive(self) -> bool:
        """Return whether the watched process is still running.

        Accepts either a plain :class:`subprocess.Popen` (alive while
        ``poll()`` returns ``None``) or a wrapper exposing ``is_alive()``
        (ADR-052 §7.1). With no handle, liveness is unknown and treated as
        alive so the watcher relies on its timeout instead.
        """
        handle = self._process_handle
        if handle is None:
            return True
        is_alive = getattr(handle, "is_alive", None)
        if callable(is_alive):
            return bool(is_alive())
        poll = getattr(handle, "poll", None)
        if callable(poll):
            return poll() is None
        return True

    def _snapshot(self) -> dict[Path, float]:
        """Return a mapping of matched file paths to their mtime."""
        result: dict[Path, float] = {}
        if not self.directory.exists():
            return result
        for child in self.directory.iterdir():
            if child.is_file() and self._matches(child.name):
                result[child] = child.stat().st_mtime
        return result

    def _diff(self, current: dict[Path, float]) -> list[Path]:
        """Return files that are new or modified since the baseline."""
        new_files: list[Path] = []
        for path, mtime in current.items():
            if path not in self._baseline or mtime > self._baseline[path]:
                new_files.append(path)
        return sorted(new_files)

    def _matches(self, filename: str) -> bool:
        """Check if *filename* matches any of the watched patterns."""
        return any(fnmatch.fnmatch(filename, pat) for pat in self.patterns)
