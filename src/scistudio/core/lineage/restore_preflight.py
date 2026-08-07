"""Advisory checks run before a git restore (ADR-038 §3.6, Addendum 1 §11.3).

ADR-038 §3.6 specified two checks in executable pseudocode — inputs unchanged,
environment not drifted — and bound them to the Re-run affordance. Neither was
ever implemented: the client returned a hardcoded empty-warnings object and the
backend route was never written, so the dialog reported "no drift detected"
whatever the environment had done.

Addendum 1 (#2033) withdraws Re-run and moves both checks onto Restore, which
is where they matter more: git restores the project tree, and nothing else.
SciStudio's own version, installed packages, and the Python environment all
live outside the project repository, so a restore cannot roll them back. When a
user restores because something "worked yesterday and fails today", the second
possible cause is that the environment moved rather than the code — and this is
the one place equipped to say so.

Both checks are **advisory**. Nothing here blocks a restore; the caller renders
the warnings and the user decides.
"""

from __future__ import annotations

import contextlib
import json
import logging
import platform as platform_mod
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scistudio.core.lineage.store import LineageStore

logger = logging.getLogger(__name__)

__all__ = ["evaluate_restore_target"]


def _recorded_environment(run: dict[str, Any]) -> dict[str, Any]:
    """Return a run's ``environment_snapshot`` as a dict.

    The column is TEXT holding JSON. Rows written before the snapshot existed,
    or by a degraded path, can hold NULL or malformed content; treat any of
    those as "nothing recorded" rather than raising, since a preflight failing
    hard would block a restore the user is entitled to make.
    """
    raw = run.get("environment_snapshot")
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        logger.debug("restore preflight: unparseable environment_snapshot", exc_info=True)
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _input_warnings(store: LineageStore, run_id: str) -> list[dict[str, str]]:
    """ADR-038 §3.6 Check 1 — boundary inputs unchanged since the run.

    Compares each workflow-boundary input against the size and mtime recorded
    when the run consumed it. Per §7.3 the mtime comparison is deliberately a
    warning and not an error: filesystem mtime resolution is OS-dependent and a
    copied file legitimately carries a new mtime.

    A path that cannot be stat-ed (permissions, a disconnected network share)
    is reported as unreadable rather than silently skipped — the user should
    know the check could not cover it.
    """
    warnings: list[dict[str, str]] = []
    for obj in store.workflow_boundary_inputs(run_id):
        raw_path = obj.get("storage_path")
        if not raw_path:
            continue
        path = Path(str(raw_path))
        try:
            if not path.exists():
                warnings.append({"path": str(path), "reason": "no longer exists"})
                continue
            stat = path.stat()
        except OSError as exc:
            warnings.append({"path": str(path), "reason": f"could not be read ({exc.strerror or exc})"})
            continue

        recorded_size = obj.get("size_bytes")
        if recorded_size is not None and stat.st_size != recorded_size:
            warnings.append(
                {
                    "path": str(path),
                    "reason": f"size changed: {recorded_size} → {stat.st_size} bytes",
                }
            )
            continue

        recorded_mtime = obj.get("mtime_at_write")
        if recorded_mtime and _mtime_is_newer(stat.st_mtime, str(recorded_mtime)):
            warnings.append({"path": str(path), "reason": f"modified after the run (recorded {recorded_mtime})"})
    return warnings


def _mtime_is_newer(current_epoch: float, recorded_iso: str) -> bool:
    """Return True when *current_epoch* postdates the recorded ISO stamp.

    Returns ``False`` on an unparseable stamp: an unreadable record is not
    evidence that the file changed, and a false "modified" warning on every
    input would train users to ignore the panel.
    """
    from datetime import UTC, datetime

    try:
        recorded = datetime.fromisoformat(recorded_iso)
    except ValueError:
        logger.debug("restore preflight: unparseable mtime_at_write %r", recorded_iso)
        return False
    if recorded.tzinfo is None:
        recorded = recorded.replace(tzinfo=UTC)
    return datetime.fromtimestamp(current_epoch, tz=UTC) > recorded


def _env_warnings(recorded_env: dict[str, Any]) -> list[dict[str, str]]:
    """ADR-038 §3.6 Check 2 — environment not drifted since the run.

    Two deliberate refinements over the §3.6 pseudocode:

    * The pseudocode calls ``EnvironmentSnapshot.capture(full=True)`` and reads
      ``key_packages`` off it. ``capture`` resolves a *fixed default* package
      list, so any package recorded outside that list would compare against
      ``None`` and be reported as removed. Here the recorded snapshot's own
      keys drive the lookup, so the comparison covers exactly what the run
      recorded. ``full=True`` is also avoided: it shells out to ``pip freeze``,
      which is seconds of latency for a value this check never reads.

    * Python itself is compared alongside the packages. ``environment_snapshot``
      records ``python_version`` and ``platform`` precisely because they affect
      reproducibility, and an interpreter upgrade is as capable of breaking a
      block as a dependency upgrade. Both are reported through the same
      ``{package, old, new}`` shape, so the wire contract is unchanged.

    A package that is no longer installed is reported with ``new`` set to
    ``"not installed"`` rather than an empty string, so the UI never renders a
    bare arrow pointing at nothing.
    """
    warnings: list[dict[str, str]] = []

    recorded_python = recorded_env.get("python_version")
    if recorded_python and _python_base(str(recorded_python)) != _python_base(sys.version):
        warnings.append(
            {
                "package": "Python",
                "old": _python_base(str(recorded_python)),
                "new": _python_base(sys.version),
            }
        )

    recorded_platform = recorded_env.get("platform")
    current_platform = platform_mod.platform()
    if recorded_platform and str(recorded_platform) != current_platform:
        warnings.append({"package": "Platform", "old": str(recorded_platform), "new": current_platform})

    recorded_packages = recorded_env.get("key_packages")
    if isinstance(recorded_packages, dict):
        for pkg, old_version in sorted(recorded_packages.items()):
            current_version: str | None = None
            with contextlib.suppress(PackageNotFoundError):
                current_version = version(pkg)
            if current_version != old_version:
                warnings.append(
                    {
                        "package": pkg,
                        "old": str(old_version),
                        "new": current_version or "not installed",
                    }
                )
    return warnings


def _python_base(version_string: str) -> str:
    """Return the ``X.Y.Z`` prefix of a ``sys.version``-style string.

    ``sys.version`` carries the build tag and compiler ("3.12.4 (main, Jun ...)
    [MSC v.1940 64 bit]"), which differs between two installs of the same
    interpreter version. Comparing the full string would warn on a reinstall
    that changed nothing the user cares about.
    """
    return version_string.strip().split()[0] if version_string.strip() else version_string


def evaluate_restore_target(store: LineageStore, commit_sha: str) -> dict[str, Any]:
    """Return the advisory preflight for restoring to *commit_sha*.

    Resolves the commit to the newest run recorded at it, then applies the two
    ADR-038 §3.6 checks against that run's record.

    Args:
        store: The active project's lineage store.
        commit_sha: Full SHA the user is about to restore to.

    Returns:
        A dict with ``commit_sha``, ``run_id``, ``run_started_at``,
        ``input_warnings`` (``{path, reason}``) and ``env_warnings``
        (``{package, old, new}``).

        ``run_id`` is ``None`` when no run references this commit — the normal
        case for a manual commit or an ``auto: pre-restore`` commit. Callers
        MUST render that as "no run recorded here, so nothing could be
        checked", never as a clean result: reporting "no drift detected" for a
        comparison that never happened is the exact defect Addendum 1 exists to
        remove.
    """
    run = store.latest_run_for_git_commit(commit_sha)
    if run is None:
        return {
            "commit_sha": commit_sha,
            "run_id": None,
            "run_started_at": None,
            "input_warnings": [],
            "env_warnings": [],
        }

    run_id = str(run.get("run_id") or "")
    return {
        "commit_sha": commit_sha,
        "run_id": run_id,
        "run_started_at": run.get("started_at"),
        "input_warnings": _input_warnings(store, run_id),
        "env_warnings": _env_warnings(_recorded_environment(run)),
    }
