"""Artifact retention — keep the last successful run, reclaim the rest (#1983).

Every block output is persisted as a full-size artifact under
``data/zarr/<workflow_id>/<block_id>/``, and until #1983 nothing ever removed
one. A real project accumulated 16 GB of zarr from 634 MB of source images:
16 runs of the same pipeline at ~0.69 GB each, with one node holding 102
persisted arrays for a workflow that reads 6 input files.

The retention rule is deliberately simple, per owner directive:

    For each workflow, keep the artifacts produced by its most recent
    **successful** run. Reclaim everything else.

Two consequences follow from that wording and are intentional:

* "most recent **successful**" — a run that fails partway does not make the
  previous good run's artifacts reclaimable. Reclaiming on any run would leave
  a failed session with nothing on disk.
* "**produced by**" — a partial re-run (``runs.execute_from_block_id``)
  produces only its downstream nodes, so the upstream artifacts it inherited
  from an earlier run are reclaimed. That workflow then needs a full re-run.
  The owner chose this over inherited-input protection because the resulting
  behaviour is easier to predict.

Storage layout is unchanged: artifacts stay under
``data/zarr/<workflow_id>/<block_id>/``.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from scistudio.core.lineage.store import LineageStore, artifact_size_bytes

logger = logging.getLogger(__name__)

# Artifact roots swept by retention, relative to the project root. Each holds
# ``<workflow_id>/<block_id>/<artifact>`` and mirrors the directories
# ``_derive_output_dir`` and ``persist_table`` write into.
ARTIFACT_ROOTS = ("data/zarr", "data/parquet")

# Suffixes that mark a top-level artifact entry. The sweep never descends into
# one: a zarr store is a directory full of chunk files, and those chunks are
# not independently reclaimable.
ARTIFACT_SUFFIXES = (".zarr", ".parquet")


@dataclass(frozen=True)
class ReclaimCandidate:
    """One artifact the plan would remove."""

    path: Path
    """Absolute path to the artifact file or store directory."""
    size_bytes: int
    """Measured on-disk size, recursive for directory-backed stores."""
    workflow_id: str
    """The workflow directory the artifact sits under."""
    block_id: str
    """The block directory the artifact sits under."""


@dataclass(frozen=True)
class RetentionPlan:
    """What retention would keep and what it would reclaim.

    A plan is inert. :func:`apply_retention` is what deletes anything.
    """

    retained_runs: dict[str, str] = field(default_factory=dict)
    """``workflow_id`` → the run id whose artifacts are kept."""
    live_paths: frozenset[str] = frozenset()
    """Storage paths protected by the retained runs."""
    candidates: tuple[ReclaimCandidate, ...] = ()
    """Artifacts that would be removed, newest-first ordering not guaranteed."""
    protected_workflows: dict[str, str] = field(default_factory=dict)
    """``workflow_id`` → why its directory was skipped entirely."""
    blocked_reason: str | None = None
    """Non-``None`` when the whole plan refuses to run; ``candidates`` is empty."""

    @property
    def total_bytes(self) -> int:
        """Total bytes the plan would reclaim."""
        return sum(c.size_bytes for c in self.candidates)

    @property
    def is_blocked(self) -> bool:
        """Whether a safety guard refused to produce a sweep."""
        return self.blocked_reason is not None


def _iter_artifact_entries(root: Path) -> list[tuple[str, str, Path]]:
    """Yield ``(workflow_id, block_id, path)`` for each artifact under *root*.

    Only the ``<workflow_id>/<block_id>/<artifact>`` shape is recognised, which
    is what the runtime writes. Anything else in the tree is left alone.
    """
    entries: list[tuple[str, str, Path]] = []
    if not root.is_dir():
        return entries
    for workflow_dir in sorted(root.iterdir()):
        if not workflow_dir.is_dir():
            continue
        for block_dir in sorted(workflow_dir.iterdir()):
            if not block_dir.is_dir():
                continue
            for entry in sorted(block_dir.iterdir()):
                if entry.name.endswith(ARTIFACT_SUFFIXES):
                    entries.append((workflow_dir.name, block_dir.name, entry))
    return entries


def plan_retention(store: LineageStore, project_root: str | Path) -> RetentionPlan:
    """Compute which artifacts to keep and which to reclaim.

    Runs :meth:`LineageStore.backfill_storage_fields` first so a project
    recorded before the ``_extract_storage_fields`` fix still has a usable
    artifact mapping (the paths were always present in ``wire_payload``).

    Safety guards, each of which yields a blocked or partially-protected plan
    rather than an aggressive sweep:

    * A run still executing blocks the whole plan — its outputs are not yet
      recorded and would read as unreferenced.
    * An empty ``runs`` table blocks the whole plan — a fresh or reset lineage
      database must not be read as "nothing is live".
    * A workflow whose retained run recorded **no** artifact paths protects
      that workflow's directory entirely. That pattern means lineage recording
      failed for the run, and sweeping on it would delete every artifact the
      workflow has.

    Args:
        store: The project's lineage store.
        project_root: Project directory holding ``data/zarr``.

    Returns:
        The computed :class:`RetentionPlan`.
    """
    root = Path(project_root)

    in_progress = store.runs_in_progress()
    if in_progress:
        return RetentionPlan(
            blocked_reason=(
                f"{len(in_progress)} run(s) still executing; retention will not sweep while a workflow is running."
            )
        )

    if store.count("runs") == 0:
        return RetentionPlan(
            blocked_reason="lineage database records no runs; refusing to treat every artifact as reclaimable."
        )

    repaired = store.backfill_storage_fields()
    if repaired:
        logger.info("retention: recovered storage_path for %d lineage rows (#1983)", repaired)

    retained_runs = store.latest_successful_run_per_workflow()
    live_paths = store.artifact_paths_produced_by(retained_runs.values())
    # Compare resolved paths: lineage records absolute paths captured at write
    # time, while the sweep walks the project root it was handed.
    live_resolved = {str(Path(p).resolve()) for p in live_paths}

    # Group live paths by the workflow directory they sit in
    # (``.../<workflow_id>/<block_id>/<artifact>``) so the "retained run
    # recorded nothing" guard can be evaluated per workflow.
    per_workflow_live: dict[str, set[str]] = {wf: set() for wf in retained_runs}
    for path in live_resolved:
        parts = Path(path).parts
        if len(parts) >= 3:
            per_workflow_live.setdefault(parts[-3], set()).add(path)

    protected: dict[str, str] = {}
    candidates: list[ReclaimCandidate] = []
    for artifact_root in ARTIFACT_ROOTS:
        for workflow_id, block_id, entry in _iter_artifact_entries(root / artifact_root):
            if workflow_id not in retained_runs:
                protected.setdefault(
                    workflow_id,
                    "no successful run recorded; artifacts kept until one exists",
                )
                continue
            if not per_workflow_live.get(workflow_id):
                protected.setdefault(
                    workflow_id,
                    f"retained run {retained_runs[workflow_id][:8]} recorded no artifact paths; "
                    "keeping everything rather than sweeping on incomplete lineage",
                )
                continue
            if str(entry.resolve()) in live_resolved:
                continue
            candidates.append(
                ReclaimCandidate(
                    path=entry,
                    size_bytes=artifact_size_bytes(str(entry)) or 0,
                    workflow_id=workflow_id,
                    block_id=block_id,
                )
            )

    # A workflow protected by the guards above must not contribute candidates,
    # even if some of its entries were scanned before the guard tripped.
    if protected:
        candidates = [c for c in candidates if c.workflow_id not in protected]

    return RetentionPlan(
        retained_runs=retained_runs,
        live_paths=frozenset(live_resolved),
        candidates=tuple(candidates),
        protected_workflows=protected,
    )


def apply_retention(plan: RetentionPlan) -> tuple[int, int]:
    """Delete the artifacts in *plan*, returning ``(removed, freed_bytes)``.

    A blocked plan removes nothing. Individual failures are logged and skipped
    so one unreadable store cannot abort the sweep.

    Args:
        plan: A plan from :func:`plan_retention`.

    Returns:
        The number of artifacts removed and the bytes freed.
    """
    if plan.is_blocked:
        return 0, 0

    removed = 0
    freed = 0
    for candidate in plan.candidates:
        try:
            if candidate.path.is_dir():
                shutil.rmtree(candidate.path)
            else:
                candidate.path.unlink()
        except OSError:
            logger.warning("retention: could not remove %s", candidate.path, exc_info=True)
            continue
        removed += 1
        freed += candidate.size_bytes
    return removed, freed
