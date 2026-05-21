"""Platform abstraction for process group management.

ADR-019: PlatformOps protocol + PosixOps + WindowsOps implementations.
Isolates all OS-specific process management behind a single protocol.
ADR-017: Job Object support for nested SubWorkflowBlock subprocess cleanup.
"""

from __future__ import annotations

import contextlib
import logging
import subprocess
import sys
import time
from collections.abc import Callable
from typing import Any, Protocol, cast, runtime_checkable

from scistudio.engine.runners.exit_info import ProcessExitInfo

logger = logging.getLogger(__name__)


@runtime_checkable
class PlatformOps(Protocol):
    """Protocol for cross-platform process management.

    | Operation             | Linux / macOS                      | Windows                                  |
    |-----------------------|------------------------------------|------------------------------------------|
    | Process group creation| start_new_session=True             | CREATE_NEW_PROCESS_GROUP                 |
    | Graceful termination  | os.killpg(pgid, SIGTERM) + grace   | psutil terminate + grace + kill          |
    | Forced termination    | os.killpg(pgid, SIGKILL)           | psutil kill (recursive)                  |
    | Process tree kill     | os.killpg()                        | psutil children(recursive) + kill        |
    | Alive check           | os.kill(pid, 0)                    | psutil.pid_exists()                      |
    | Zombie cleanup        | os.waitpid(pid, WNOHANG)           | Not applicable                           |
    """

    def create_process_group(self, popen_kwargs: dict[str, Any]) -> dict[str, Any]:
        """Add platform-specific args to Popen kwargs for process group creation."""
        ...

    def terminate_tree(self, pid: int, grace_sec: float) -> ProcessExitInfo:
        """Graceful termination of process tree. Returns ProcessExitInfo."""
        ...

    def kill_tree(self, pid: int) -> ProcessExitInfo:
        """Immediate forced termination of process tree. Returns ProcessExitInfo."""
        ...

    def is_alive(self, pid: int) -> bool:
        """Non-blocking alive check."""
        ...

    def get_exit_info(self, pid: int) -> ProcessExitInfo | None:
        """Return ProcessExitInfo if exited, None if still alive."""
        ...

    def create_job_object(self) -> Any:
        """Create a platform-specific job object for nested process cleanup."""
        ...

    def assign_to_job(self, job_handle: Any, pid: int) -> bool:
        """Assign a process to a job object. Returns True on success."""
        ...


class PosixOps:
    """Linux/macOS implementation using OS-level process group APIs.

    Uses:
        - start_new_session=True for process group
        - os.killpg(pgid, signal.SIGTERM) for graceful
        - os.killpg(pgid, signal.SIGKILL) for forced
        - os.kill(pid, 0) for alive check (raises OSError if dead)
        - os.waitpid(pid, os.WNOHANG) for zombie cleanup
    """

    def create_process_group(self, popen_kwargs: dict[str, Any]) -> dict[str, Any]:
        """Add ``start_new_session=True`` so the child gets its own process group."""
        popen_kwargs["start_new_session"] = True
        return popen_kwargs

    def terminate_tree(self, pid: int, grace_sec: float) -> ProcessExitInfo:
        """Send SIGTERM to the process group, wait *grace_sec*, then SIGKILL."""
        import os
        import signal

        getpgid = cast(Callable[[int], int], os.getpgid)  # type: ignore[attr-defined]
        killpg = cast(Callable[[int, int], None], os.killpg)  # type: ignore[attr-defined]
        sigkill = cast(int, signal.SIGKILL)  # type: ignore[attr-defined]

        try:
            pgid = getpgid(pid)
        except ProcessLookupError:
            return ProcessExitInfo(
                exit_code=None,
                signal_number=None,
                was_killed_by_framework=True,
                platform_detail="process already dead before terminate",
            )

        # Phase 1: SIGTERM
        try:
            killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            return ProcessExitInfo(
                exit_code=None,
                signal_number=signal.SIGTERM,
                was_killed_by_framework=True,
                platform_detail="process died during SIGTERM",
            )

        # Wait for graceful exit
        deadline = time.monotonic() + grace_sec
        while time.monotonic() < deadline:
            if not self.is_alive(pid):
                info = self.get_exit_info(pid)
                if info is not None:
                    info.was_killed_by_framework = True
                    return info
                return ProcessExitInfo(
                    exit_code=None,
                    signal_number=signal.SIGTERM,
                    was_killed_by_framework=True,
                    platform_detail="terminated by SIGTERM",
                )
            time.sleep(0.05)

        # Phase 2: SIGKILL if still alive
        with contextlib.suppress(ProcessLookupError):
            killpg(pgid, sigkill)

        return ProcessExitInfo(
            exit_code=None,
            signal_number=sigkill,
            was_killed_by_framework=True,
            platform_detail="killed by SIGKILL after grace period",
        )

    def kill_tree(self, pid: int) -> ProcessExitInfo:
        """Immediately SIGKILL the entire process group."""
        import os
        import signal

        getpgid = cast(Callable[[int], int], os.getpgid)  # type: ignore[attr-defined]
        killpg = cast(Callable[[int, int], None], os.killpg)  # type: ignore[attr-defined]
        sigkill = cast(int, signal.SIGKILL)  # type: ignore[attr-defined]

        try:
            pgid = getpgid(pid)
            killpg(pgid, sigkill)
        except ProcessLookupError:
            pass

        return ProcessExitInfo(
            exit_code=None,
            signal_number=sigkill,
            was_killed_by_framework=True,
            platform_detail="killed by SIGKILL",
        )

    def is_alive(self, pid: int) -> bool:
        """Check if process is alive using ``os.kill(pid, 0)``.

        Guard (#495): ``pid <= 0`` is never valid for a single-process
        alive check.  In particular ``os.kill(-1, 0)`` signals **all**
        user processes and always succeeds, giving a false-positive.
        ``pid == 0`` targets the caller's own process group.  Both are
        rejected early.
        """
        if pid <= 0:
            return False

        import os

        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            # Process exists but we lack permission — still alive
            return True
        return True

    def get_exit_info(self, pid: int) -> ProcessExitInfo | None:
        """Retrieve exit status via ``os.waitpid(pid, WNOHANG)``.

        Returns ProcessExitInfo if the process has exited, None if still alive.
        """
        import os
        import signal as signal_mod

        waitpid = cast(Callable[[int, int], tuple[int, int]], os.waitpid)  # type: ignore[attr-defined]
        wnohang = cast(int, os.WNOHANG)  # type: ignore[attr-defined]
        wifexited = cast(Callable[[int], bool], os.WIFEXITED)  # type: ignore[attr-defined]
        wexitstatus = cast(Callable[[int], int], os.WEXITSTATUS)  # type: ignore[attr-defined]
        wifsignaled = cast(Callable[[int], bool], os.WIFSIGNALED)  # type: ignore[attr-defined]
        wtermsig = cast(Callable[[int], int], os.WTERMSIG)  # type: ignore[attr-defined]

        try:
            wpid, status = waitpid(pid, wnohang)
        except ChildProcessError:
            # Not our child or already reaped
            if not self.is_alive(pid):
                return ProcessExitInfo(
                    exit_code=None,
                    platform_detail="process exited but not our child",
                )
            return None

        if wpid == 0:
            # Still running
            return None

        if wifexited(status):
            return ProcessExitInfo(
                exit_code=wexitstatus(status),
                platform_detail="exited normally",
            )
        if wifsignaled(status):
            sig = wtermsig(status)
            return ProcessExitInfo(
                exit_code=None,
                signal_number=sig,
                platform_detail=f"killed by signal {signal_mod.Signals(sig).name}",
            )

        return ProcessExitInfo(
            exit_code=None,
            platform_detail=f"unknown exit status {status}",
        )

    def create_job_object(self) -> Any:
        """No-op on POSIX -- process groups handle nested cleanup."""
        return None

    def assign_to_job(self, job_handle: Any, pid: int) -> bool:
        """No-op on POSIX."""
        return False


class WindowsOps:
    """Windows implementation using psutil for process tree management.

    Uses:
        - CREATE_NEW_PROCESS_GROUP flag for Popen
        - psutil.Process(pid).children(recursive=True) for tree operations
        - psutil.Process.terminate() / kill() for termination
        - psutil.pid_exists() for alive check
    """

    def create_process_group(self, popen_kwargs: dict[str, Any]) -> dict[str, Any]:
        """Add ``CREATE_NEW_PROCESS_GROUP`` creation flag."""
        create_new_pg: int = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        popen_kwargs["creationflags"] = popen_kwargs.get("creationflags", 0) | create_new_pg
        return popen_kwargs

    def terminate_tree(self, pid: int, grace_sec: float) -> ProcessExitInfo:
        """Terminate process tree via psutil with grace period, then kill."""
        import psutil

        try:
            parent = psutil.Process(pid)
        except psutil.NoSuchProcess:
            return ProcessExitInfo(
                exit_code=None,
                was_killed_by_framework=True,
                platform_detail="process already dead before terminate",
            )

        # Collect the tree (children first, then parent)
        children = parent.children(recursive=True)
        procs = [*children, parent]

        # Phase 1: terminate all
        for proc in procs:
            try:
                proc.terminate()
            except psutil.NoSuchProcess:
                continue

        # Wait for graceful exit
        _, alive = psutil.wait_procs(procs, timeout=grace_sec)

        # Phase 2: kill survivors
        for proc in alive:
            try:
                proc.kill()
            except psutil.NoSuchProcess:
                continue

        # Get exit code from parent if possible
        exit_code = None
        with contextlib.suppress(psutil.NoSuchProcess, psutil.TimeoutExpired):
            exit_code = parent.wait(timeout=1)

        return ProcessExitInfo(
            exit_code=exit_code,
            was_killed_by_framework=True,
            platform_detail="terminated via psutil" + (" (killed after grace)" if alive else ""),
        )

    def kill_tree(self, pid: int) -> ProcessExitInfo:
        """Immediately kill entire process tree via psutil."""
        import psutil

        try:
            parent = psutil.Process(pid)
        except psutil.NoSuchProcess:
            return ProcessExitInfo(
                exit_code=None,
                was_killed_by_framework=True,
                platform_detail="process already dead before kill",
            )

        children = parent.children(recursive=True)
        for child in children:
            try:
                child.kill()
            except psutil.NoSuchProcess:
                continue

        with contextlib.suppress(psutil.NoSuchProcess):
            parent.kill()

        return ProcessExitInfo(
            exit_code=None,
            was_killed_by_framework=True,
            platform_detail="killed via psutil",
        )

    def is_alive(self, pid: int) -> bool:
        """Check if process exists using ``psutil.pid_exists()``."""
        import psutil

        return bool(psutil.pid_exists(pid))

    def get_exit_info(self, pid: int) -> ProcessExitInfo | None:
        """Check process status via psutil.

        Returns ProcessExitInfo if exited, None if still alive.
        """
        import psutil

        if psutil.pid_exists(pid):
            try:
                proc = psutil.Process(pid)
                status = proc.status()
                if status == psutil.STATUS_ZOMBIE:
                    return ProcessExitInfo(
                        exit_code=None,
                        platform_detail="zombie process",
                    )
                # Still alive
                return None
            except psutil.NoSuchProcess:
                pass

        return ProcessExitInfo(
            exit_code=None,
            platform_detail="process no longer exists",
        )

    def create_job_object(self) -> Any:  # pragma: no cover — Windows-only ctypes
        """Create a Windows Job Object with kill-on-close semantics.

        When the job handle is closed (or the parent process exits),
        all processes assigned to the job are terminated.  This ensures
        nested subprocess cleanup for SubWorkflowBlock.

        Returns the job handle, or None if creation fails.
        """
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

            # CreateJobObjectW(lpJobAttributes, lpName)
            job = kernel32.CreateJobObjectW(None, None)
            if not job:
                return None

            # Configure JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):  # noqa: N801
                _fields_ = [
                    ("PerProcessUserTimeLimit", ctypes.c_int64),
                    ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.POINTER(ctypes.c_ulong)),
                    ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD),
                ]

            class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):  # noqa: N801
                _fields_ = [
                    ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                    ("IoInfo", ctypes.c_byte * 48),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t),
                ]

            JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000  # noqa: N806
            JobObjectExtendedLimitInformation = 9  # noqa: N806

            info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

            kernel32.SetInformationJobObject(
                job,
                JobObjectExtendedLimitInformation,
                ctypes.byref(info),
                ctypes.sizeof(info),
            )
            return job
        except Exception:
            return None

    def assign_to_job(self, job_handle: Any, pid: int) -> bool:  # pragma: no cover — Windows-only ctypes
        """Assign a process to a Job Object.

        Returns True on success, False on failure.
        """
        if job_handle is None:
            return False
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            PROCESS_ALL_ACCESS = 0x1F0FFF  # noqa: N806
            proc_handle = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
            if not proc_handle:
                return False
            result = kernel32.AssignProcessToJobObject(job_handle, proc_handle)
            kernel32.CloseHandle(proc_handle)
            return bool(result)
        except Exception:
            return False


def get_platform_ops() -> PlatformOps:
    """Return the correct PlatformOps implementation for the current OS."""
    if sys.platform == "win32":
        return WindowsOps()
    return PosixOps()
