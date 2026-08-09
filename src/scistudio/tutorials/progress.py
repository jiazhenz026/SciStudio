"""Tutorial progress, its grouping, and the one unlock it drives.

``docs/specs/adr-053-learning-center.md`` FR-074 to FR-081.

**Progress is a backend file** (FR-074). Browser storage was rejected for three
reasons the spec records: the backend has to read progress to decide the unlock
and write it when a package is uninstalled, browser storage does not survive
clearing browsing data, and the desktop and web surfaces would keep two copies
that disagree.

**A group's counts are a question about the catalogue, not about this file**
(FR-076, FR-077). What is stored is the set of completed ``(source, id)`` pairs
and nothing else; the totals come from whoever lists the catalogue and are
supplied to :meth:`ProgressStore.groups` per call. That is what makes FR-077
fall out rather than needing code: a source that ships a seventh tutorial widens
its own total, the completed set is unchanged, and the group goes back to
incomplete — which is the intended reading, because there is new material. It
also means a stored completion for a tutorial the source no longer ships stops
being counted instead of pushing ``completed`` above ``total``.

**Exactly one product behaviour is driven by progress** (FR-079), and it is
driven by the core group alone (FR-080): completing one named core tutorial
presents the work-import offer, once. Package progress is display only. And no
capability is gated on any of it (FR-081) — the work-import toolbar entry is
permanently available; the unlock decides only when the product *volunteers* it,
which is why this module exposes a "pending offer" flag and not a permission.

**Which tutorial that is, is configuration** (FR-079, spec assumption A-005):
the scenarios spec decides, and may change its mind. See
:func:`work_import_milestone` for the three places the value can come from.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scistudio.core.dropins import user_library_dir

from .projects import TutorialKey

__all__ = [
    "CONFIG_FILENAME",
    "DEFAULT_WORK_IMPORT_MILESTONE",
    "PROGRESS_FILENAME",
    "WORK_IMPORT_MILESTONE_ENV_VAR",
    "CatalogueTotals",
    "ProgressGroup",
    "ProgressStore",
    "work_import_milestone",
]

logger = logging.getLogger(__name__)

#: Progress file, under ``~/.scistudio/`` (FR-074).
PROGRESS_FILENAME = "tutorial-progress.json"

#: Learning Center settings file, in the same directory.
CONFIG_FILENAME = "learning-center.json"

#: Overrides the configured milestone for one process. Named for the behaviour
#: it selects rather than for this module, because it is a product setting.
WORK_IMPORT_MILESTONE_ENV_VAR = "SCISTUDIO_WORK_IMPORT_MILESTONE"

# TODO(#2057): the work-import milestone ships unset until the Learning Center
#   scenarios spec names the AI tutorial that carries it.
#   Out of scope per ADR-053 Learning Center spec assumption A-005, which
#   assigns that choice to the scenarios spec and requires FR-079's trigger to
#   be configuration precisely so the scenarios spec can make it and revise
#   it.
#   Followup: https://github.com/jiazhenz026/SciStudio/issues/2057
#: Milestone shipped with the product; see the note above and
#: :func:`work_import_milestone`.
DEFAULT_WORK_IMPORT_MILESTONE: str | None = None

_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class CatalogueTotals:
    """One source's contribution to the catalogue, as progress sees it.

    Ids rather than a count, because :meth:`ProgressStore.groups` counts the
    intersection with what has been completed. A count alone cannot tell a
    completion of a tutorial the source still ships from one it has withdrawn,
    and the difference decides whether a group reads as complete.
    """

    source_kind: str
    source_id: str
    tutorial_ids: frozenset[str]


@dataclass(frozen=True)
class ProgressGroup:
    """One source's progress, as reported (FR-076).

    No aggregate across groups exists anywhere in this module, because FR-076
    forbids reporting one: a percentage over a catalogue packages can grow does
    not denote a fixed point in the user's experience.
    """

    source_kind: str
    source_id: str
    completed: int
    total: int


def _config_value(name: str, root: Path | None = None) -> Any:
    """Return *name* from the Learning Center settings file, or ``None``."""
    path = (root or user_library_dir()) / CONFIG_FILENAME
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return raw.get(name) if isinstance(raw, dict) else None


def work_import_milestone(root: Path | None = None) -> str | None:
    """Return the core tutorial id whose completion offers work import (FR-079).

    Resolved from three sources, first hit winning:
    :data:`WORK_IMPORT_MILESTONE_ENV_VAR`, then ``work_import_milestone`` in
    ``~/.scistudio/`` :data:`CONFIG_FILENAME`, then
    :data:`DEFAULT_WORK_IMPORT_MILESTONE`. FR-079 requires the trigger to be
    configuration rather than a constant, and spec assumption A-005 gives the
    reason: the scenarios spec decides which tutorial this is and may revise that
    choice, so it must be changeable without touching the unlock's logic.

    A **core tutorial id** rather than a full :class:`TutorialKey`, because
    FR-080 restricts product behaviour to the core group. Making the milestone
    structurally incapable of naming a package tutorial is stronger than
    checking that it does not.

    ``None`` means no milestone is configured, and the offer is then never
    volunteered — the toolbar entry remains available regardless (FR-081), so an
    unconfigured milestone withholds a prompt rather than a capability.
    """
    from_env = os.environ.get(WORK_IMPORT_MILESTONE_ENV_VAR, "").strip()
    if from_env:
        return from_env
    configured = _config_value("work_import_milestone", root)
    if isinstance(configured, str) and configured.strip():
        return configured.strip()
    return DEFAULT_WORK_IMPORT_MILESTONE


class ProgressStore:
    """The ``~/.scistudio/`` progress file, read and written per operation.

    Re-read on every access rather than cached, for the same reason
    :meth:`scistudio.api.runtime.ApiRuntime.list_projects` re-reads the
    known-projects file: the desktop shell, the API process, and a package
    uninstall can all touch it, and a cached copy would let one of them report
    progress another has already changed. The file holds a handful of short
    strings, so the read costs nothing worth keeping.
    """

    def __init__(self, root: Path | None = None) -> None:
        self._root = root

    @property
    def root(self) -> Path:
        """Return the directory holding the progress file (FR-074).

        Resolved per access rather than at construction so a store built before
        the home directory is known — or in a test that redirects it — reads the
        current answer.
        """
        return self._root or user_library_dir()

    @property
    def path(self) -> Path:
        """Return the progress file's path."""
        return self.root / PROGRESS_FILENAME

    # -- storage ---------------------------------------------------------

    def _read(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            # A corrupt progress file must not break the Learning Center: the
            # worst it can cost is a repeated tutorial, while refusing to load
            # would make the catalogue unopenable. The file is rewritten by the
            # next completion.
            logger.warning("Learning Center: unreadable progress file %s; treating as empty", self.path, exc_info=True)
            return {}
        return raw if isinstance(raw, dict) else {}

    def _write(self, payload: Mapping[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"version": _SCHEMA_VERSION, **payload}, indent=2), encoding="utf-8")

    @staticmethod
    def _records(raw: Mapping[str, Any]) -> list[dict[str, Any]]:
        completed = raw.get("completed")
        if not isinstance(completed, list):
            return []
        return [record for record in completed if isinstance(record, dict) and record.get("tutorial_id")]

    @staticmethod
    def _key_of(record: Mapping[str, Any]) -> TutorialKey | None:
        kind = record.get("source_kind")
        tutorial_id = record.get("tutorial_id")
        if not isinstance(kind, str) or not isinstance(tutorial_id, str):
            return None
        source_id = record.get("source_id")
        try:
            return TutorialKey(
                source_kind=kind,
                source_id=source_id if isinstance(source_id, str) else "",
                tutorial_id=tutorial_id,
            )
        except ValueError:
            return None

    # -- completion (FR-075) ---------------------------------------------

    def completed_keys(self) -> frozenset[TutorialKey]:
        """Return every recorded completion, keyed by source and id (FR-075)."""
        keys = (self._key_of(record) for record in self._records(self._read()))
        return frozenset(key for key in keys if key is not None)

    def is_completed(self, key: TutorialKey) -> bool:
        """Return whether *key* has been completed."""
        return key in self.completed_keys()

    def mark_completed(self, key: TutorialKey, *, completed_at: str | None = None) -> bool:
        """Record *key* as complete; return whether this was the first time.

        The return value is what FR-079's "once" is decided on by the caller
        that ends a session: a re-completion of the milestone tutorial after a
        restart must not present the offer a second time, and the dismissal flag
        alone would not distinguish "already offered" from "never offered".
        """
        raw = self._read()
        records = self._records(raw)
        if any(self._key_of(record) == key for record in records):
            return False
        records.append(
            {
                "source_kind": key.source_kind,
                "source_id": key.source_id,
                "tutorial_id": key.tutorial_id,
                **({"completed_at": completed_at} if completed_at else {}),
            }
        )
        self._write({**raw, "completed": records})
        return True

    # -- grouping (FR-076, FR-077) ---------------------------------------

    def groups(self, totals: Iterable[CatalogueTotals]) -> tuple[ProgressGroup, ...]:
        """Return one :class:`ProgressGroup` per entry of *totals* (FR-076).

        Input order is preserved, so the caller's ordering — core first, per
        FR-084 — survives. Completion is counted as the intersection of the
        recorded set with the ids the source currently ships, which is where
        FR-077 comes from: a widened total is reported as widened, uncompensated.
        """
        completed = self.completed_keys()
        by_group: dict[tuple[str, str], set[str]] = {}
        for key in completed:
            by_group.setdefault(key.group, set()).add(key.tutorial_id)
        return tuple(
            ProgressGroup(
                source_kind=entry.source_kind,
                source_id=entry.source_id,
                completed=len(by_group.get((entry.source_kind, entry.source_id), set()) & entry.tutorial_ids),
                total=len(entry.tutorial_ids),
            )
            for entry in totals
        )

    # -- removal (FR-078, and clearing) ----------------------------------

    def remove_group(self, source_kind: str, source_id: str) -> int:
        """Drop every completion for one source; return how many went.

        FR-078's mechanism. Deleting rather than retaining-and-hiding is what
        makes "reinstalling starts from zero" true: a retained record would make
        a reinstalled package look already-finished to a user who has never seen
        its tutorials, and no surface would explain why.
        """
        raw = self._read()
        records = self._records(raw)
        kept = [
            record
            for record in records
            if not (record.get("source_kind") == source_kind and (record.get("source_id") or "") == source_id)
        ]
        if len(kept) == len(records):
            return 0
        self._write({**raw, "completed": kept})
        return len(records) - len(kept)

    def remove_package_group(self, distribution: str) -> int:
        """Drop the progress group of an uninstalled package (FR-078).

        Called by whoever handles package uninstall; this module does not
        observe installs.
        """
        return self.remove_group("package", distribution)

    def clear(self) -> None:
        """Delete all recorded progress and the unlock's state (FR-088).

        The progress half of clearing tutorial data. The directories are
        :func:`scistudio.tutorials.projects.clear_tutorial_data`'s half.
        """
        self.path.unlink(missing_ok=True)

    # -- the one unlock (FR-079, FR-080, FR-081) -------------------------

    def work_import_offer_pending(self, root: Path | None = None) -> bool:
        """Return whether the work-import offer is owed to the user (FR-079).

        True only when a milestone is configured, that core tutorial has been
        completed, and the offer has not yet been presented. It gates nothing:
        the toolbar entry is available whatever this returns (FR-081), so a
        ``False`` here withholds a prompt and no capability.
        """
        milestone = work_import_milestone(root if root is not None else self._root)
        if not milestone:
            return False
        if self._read().get("work_import_offer_dismissed") is True:
            return False
        return self.is_completed(TutorialKey.core(milestone))

    def dismiss_work_import_offer(self) -> None:
        """Record that the offer has been presented, so it does not return.

        FR-079's "once", and User Story 5's skip path: the user is told the
        toolbar entry stays available and is not asked again.
        """
        raw = self._read()
        self._write({**raw, "completed": self._records(raw), "work_import_offer_dismissed": True})
