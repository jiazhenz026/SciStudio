"""Advisory checks run before a git restore."""
# Maintainer context (kept outside generated API documentation):
# Advisory checks run before a git restore (ADR-038 §3.6, Addendum 1 §11.3).
#
# ADR-038 §3.6 specified two checks in executable pseudocode — inputs unchanged,
# environment not drifted — and bound them to the Re-run affordance. Neither was
# ever implemented: the client returned a hardcoded empty-warnings object and the
# backend route was never written, so the dialog reported "no drift detected"
# whatever the environment had done.
#
# Addendum 1 (#2033) withdraws Re-run and moves both checks onto Restore, which
# is where they matter more: git restores the project tree, and nothing else.
# SciStudio's own version, installed packages, and the Python environment all
# live outside the project repository, so a restore cannot roll them back. When a
# user restores because something "worked yesterday and fails today", the second
# possible cause is that the environment moved rather than the code — and this is
# the one place equipped to say so.
#
# Both checks are **advisory**. Nothing here blocks a restore; the caller renders
# the warnings and the user decides.
# Development references: #2033, ADR-038, Addendum 1.

from __future__ import annotations

import contextlib
import json
import logging
import platform as platform_mod
import sys
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scistudio.core.lineage.store import LineageStore

logger = logging.getLogger(__name__)

__all__ = ["RestoreRunMismatchError", "evaluate_restore_target"]


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
    """Check 1 — boundary inputs unchanged since the run.

    Compares each workflow-boundary input against the size and mtime recorded
    when the run consumed it.  the mtime comparison is deliberately a
    warning and not an error: filesystem mtime resolution is OS-dependent and a
    copied file legitimately carries a new mtime.

    A path that cannot be stat-ed (permissions, a disconnected network share)
    is reported as unreadable rather than silently skipped — the user should
    know the check could not cover it.
    """
    # Maintainer context:
    # Compares each workflow-boundary input against the size and mtime recorded
    # when the run consumed it. Per §7.3 the mtime comparison is deliberately a
    # warning and not an error: filesystem mtime resolution is OS-dependent and a
    # copied file legitimately carries a new mtime.
    # Development references: ADR-038.
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


def _parse_recorded_mtime(recorded: str) -> datetime | None:
    """Return *recorded* as an aware datetime, or ``None`` if unreadable.

    ``data_objects.mtime_at_write`` holds **two** formats and both are live.
    :meth:`LineageStore.upsert_data_object` fills a missing value with
    ``str(path.stat().st_mtime)`` — a bare epoch float like ``"1786092443.98"``
    and that is the only writer, so every row the recorder produces is in
    epoch form. The API's pseudocode assumes ISO, and the column's type is
    TEXT with no format stated on the field, so an ISO value from a caller that
    supplies its own is equally valid.

    Reading only ISO would make the mtime branch dead code against real lineage
    rows: ``fromisoformat`` rejects the epoch string, the comparison returns
    False, and an input modified after its run reaches the user as a clean
    result. That is the same class of defect this module exists to remove, so
    both forms are parsed here rather than migrating the writer — historical
    rows are already epoch and a writer change cannot reach them.
    """
    # Development references: ADR-038.
    text = recorded.strip()
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            return datetime.fromtimestamp(float(text), tz=UTC)
        except (ValueError, OSError, OverflowError):
            logger.debug("restore preflight: unparseable mtime_at_write %r", recorded)
            return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _mtime_is_newer(current_epoch: float, recorded: str) -> bool:
    """Return True when *current_epoch* postdates the recorded stamp.

    Returns ``False`` on an unreadable stamp: a record that cannot be parsed is
    not evidence that the file changed, and a false "modified" warning on every
    input would train users to ignore the panel.
    """
    recorded_dt = _parse_recorded_mtime(recorded)
    if recorded_dt is None:
        return False
    return datetime.fromtimestamp(current_epoch, tz=UTC) > recorded_dt


def _env_warnings(recorded_env: dict[str, Any]) -> list[dict[str, str]]:
    """Check 2 — environment not drifted since the run.

    The checks apply two additional rules:

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
    # Maintainer context:
    # Two deliberate refinements over the §3.6 pseudocode:
    # Development references: ADR-038.
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


class RestoreRunMismatchError(ValueError):
    """Raised when a supplied ``run_id`` was recorded at a different commit.

    A run from another commit describes a different project tree, so comparing
    the restore target against it would answer a question the user did not
    ask. The caller maps this to a client error instead of silently using it.
    """

    def __init__(self, run_id: str, run_commit: str | None, commit_sha: str) -> None:
        self.run_id = run_id
        self.run_commit = run_commit
        self.commit_sha = commit_sha
        recorded = run_commit or "no commit"
        super().__init__(f"run {run_id!r} was recorded at {recorded}, not at the restore target {commit_sha}")


def _run_entry(store: LineageStore, run: dict[str, Any]) -> dict[str, Any]:
    """Evaluate both checks for one run and return its per-workflow entry."""
    run_id = str(run.get("run_id") or "")
    return {
        "workflow_id": run.get("workflow_id"),
        "run_id": run_id,
        "run_started_at": run.get("started_at"),
        "input_warnings": _input_warnings(store, run_id),
        "env_warnings": _env_warnings(_recorded_environment(run)),
    }


def _merge_env_warnings(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge per-run environment warnings, collapsing identical drifts.

    The environment is shared by every workflow, so two runs that recorded
    the same package version report the same drift. Identical
    ``(package, old, new)`` triples are listed once, with every workflow and
    run that recorded them.
    """
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    for entry in entries:
        for warning in entry["env_warnings"]:
            key = (warning["package"], warning["old"], warning["new"])
            slot = merged.get(key)
            if slot is None:
                slot = {**warning, "workflow_ids": [], "run_ids": []}
                merged[key] = slot
            if entry["workflow_id"] not in slot["workflow_ids"]:
                slot["workflow_ids"].append(entry["workflow_id"])
            slot["run_ids"].append(entry["run_id"])
    return list(merged.values())


def evaluate_restore_target(
    store: LineageStore,
    commit_sha: str,
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Return the advisory preflight for restoring to *commit_sha*.

    A commit snapshots every workflow in the project, so the checks run
    against the newest recorded run of **each** workflow at the commit and the
    warnings are merged, each attributed to its workflow and run.

    Args:
        store: The active project's lineage store.
        commit_sha: Full SHA the user is about to restore to.
        run_id: The run the user selected, when the caller has one. Run history
            restores start from a specific run and MUST pass it; the Git tab
            restores an arbitrary commit and cannot.

            This is not a redundant hint. The pre-run auto-commit is skipped
            when the tree is already clean, so consecutive runs of an unedited
            workflow all anchor to the same SHA — and resolving by commit alone
            would then answer with the newest of them regardless of outcome.
            The selected run therefore replaces the newest run *of its own
            workflow*; the other workflows at the commit are still checked
            through their newest runs.

    Returns:
        A dict with ``commit_sha``, ``run_id``, ``run_started_at``,
        ``input_warnings`` (``{path, reason, workflow_id, run_id}``),
        ``env_warnings`` (``{package, old, new, workflow_ids, run_ids}``) and
        ``runs`` (one ``{workflow_id, run_id, run_started_at, input_warnings,
        env_warnings}`` entry per checked workflow: the selected run first when
        one was passed, the rest newest first).

        ``run_id``/``run_started_at`` name the anchoring run: the selected run
        when one was passed, otherwise the newest run at the commit.

        ``run_id`` is ``None`` (and ``runs`` empty) when no run could be
        resolved — the normal case for a manual commit or an
        ``auto: pre-restore`` commit. Callers MUST render that as "no run
        recorded here, so nothing could be checked", never as a clean result.

    Raises:
        RestoreRunMismatchError: ``run_id`` names a recorded run whose
            ``workflow_git_commit`` is not *commit_sha*.
    """
    # Development references: #2425, ADR-038, Addendum 1.
    selected = store.get_run(run_id) if run_id else None
    if selected is not None and selected.get("workflow_git_commit") != commit_sha:
        raise RestoreRunMismatchError(str(run_id), selected.get("workflow_git_commit"), commit_sha)
    # A named run that is gone (a retention sweep, a hand-edited db) falls back
    # to the commit, which is all the Git tab ever has.

    runs = store.latest_runs_per_workflow_for_git_commit(commit_sha)
    if selected is not None:
        runs = [selected] + [r for r in runs if r.get("workflow_id") != selected.get("workflow_id")]
    if not runs:
        return {
            "commit_sha": commit_sha,
            "run_id": None,
            "run_started_at": None,
            "input_warnings": [],
            "env_warnings": [],
            "runs": [],
        }

    entries = [_run_entry(store, run) for run in runs]
    anchor = entries[0]
    input_warnings = [
        {**warning, "workflow_id": entry["workflow_id"], "run_id": entry["run_id"]}
        for entry in entries
        for warning in entry["input_warnings"]
    ]
    return {
        "commit_sha": commit_sha,
        "run_id": anchor["run_id"],
        "run_started_at": anchor["run_started_at"],
        "input_warnings": input_warnings,
        "env_warnings": _merge_env_warnings(entries),
        "runs": entries,
    }
