"""Tutorial projects and the tutorial-scoped library.

``docs/specs/adr-053-learning-center.md`` FR-062 to FR-073. A tutorial
declaring ``bootstrap`` gets a project of its own, created under one parent
directory, marked so it never reaches a project-listing surface, deleted and
recreated when the tutorial is restarted, and deleted along with the scoped
library when the user clears tutorial data.

**This module decides; it does not act on the runtime.** Creating a project is
:meth:`scistudio.api.runtime.ApiRuntime.create_project`'s job — it scaffolds the
directory tree, writes ``project.yaml``, initialises git, provisions agent
assets, and records the known-projects entry that FR-063 requires. What is
tutorial-specific is *where* the project goes, *what it is called*, *which
identity it carries*, and *what is deleted when*. Those are here, expressed as
plans and paths the API layer applies, because ``scistudio.tutorials`` may not
import ``scistudio.api`` (checklist §6.1.2) and because the same answers are
needed by the session, the restart confirmation, and the clear confirmation,
which are three different callers.

**Identity is the pair of source and tutorial id** (FR-019), so
:class:`TutorialKey` carries both and the marker on the known-projects entry
carries both. Two packages may ship a tutorial called ``intro`` and both must be
able to have a project on disk at the same time, which is why the directory name
encodes the source as well (:func:`tutorial_project_dir_name`).

**Containment is by location.** Every tutorial project is a direct child of
:func:`scistudio.core.dropins.tutorial_parent_dir`, and the scoped library is
the one other child. That is what lets :func:`clear_preview` name what clearing
deletes without consulting the known-projects registry, what lets
:func:`scistudio.core.dropins.library_root_for_project` route a tutorial
project's drop-in scans to the teaching library instead of the user's own
(FR-070, FR-071), and what makes "leave user projects untouched" (FR-073) true
by construction rather than by a filter that could be got wrong.
"""

from __future__ import annotations

import os
import shutil
import stat
from collections.abc import Callable, Iterable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from scistudio.core.dropins import (
    BLOCKS_DIR_NAME,
    TYPES_DIR_NAME,
    is_tutorial_location,
    tutorial_library_dir,
    tutorial_parent_dir,
)
from scistudio.stability import provisional

__all__ = [
    "SOURCE_KINDS",
    "RemoveTree",
    "SupportsTutorialMarker",
    "TutorialKey",
    "TutorialProjectPlan",
    "clear_preview",
    "clear_tutorial_data",
    "delete_tutorial_project",
    "ensure_scoped_library",
    "ensure_tutorial_parent",
    "find_tutorial_project",
    "is_tutorial_entry",
    "is_tutorial_location",
    "plan_tutorial_project",
    "restart_preview",
    "scoped_library_dirs",
    "tutorial_entries",
    "tutorial_key_of",
    "tutorial_project_dir_name",
    "tutorial_project_exists",
    "tutorial_project_path",
]

#: The four discovery sources a tutorial can come from (FR-016).
SOURCE_KINDS = frozenset({"core", "package", "user", "project"})

#: Separator between the components of a non-core tutorial project directory
#: name. A dot, because :func:`_slug` emits only ``[a-z0-9-]``, so no slug can
#: contain one — which is what makes :func:`tutorial_project_dir_name` injective.
_COMPONENT_SEPARATOR = "."

#: How a directory tree is removed. Injected so the API layer can pass its own
#: Windows-hardened remover; see :func:`_remove_tree` for the default.
RemoveTree = Callable[[Path], None]


@provisional(since="0.3.4")
@dataclass(frozen=True)
class TutorialKey:
    """A tutorial's identity: its source and its id (FR-019, FR-075).

    ``source_id`` is ``""`` for core, the distribution name for a package, and
    ``"user"`` or ``"project"`` for the two local tiers — the same spelling the
    HTTP contract and the progress groups use, so one value travels from
    discovery through the project marker to the progress record without being
    re-encoded at each boundary.
    """

    source_kind: str
    source_id: str
    tutorial_id: str

    def __post_init__(self) -> None:
        if self.source_kind not in SOURCE_KINDS:
            raise ValueError(
                f"Unknown tutorial source kind {self.source_kind!r}; expected one of {sorted(SOURCE_KINDS)}"
            )
        if not self.tutorial_id:
            raise ValueError("A tutorial key needs a tutorial id")

    @classmethod
    def core(cls, tutorial_id: str) -> TutorialKey:
        """Return the key of a core tutorial, whose source id is empty."""
        return cls(source_kind="core", source_id="", tutorial_id=tutorial_id)

    @property
    def group(self) -> tuple[str, str]:
        """Return the progress group this tutorial belongs to (FR-076)."""
        return (self.source_kind, self.source_id)


@runtime_checkable
class SupportsTutorialMarker(Protocol):
    """Structural view of a known-projects entry carrying the FR-064 marker.

    :class:`scistudio.api.runtime.models.KnownProject` satisfies it. Declared
    structurally so this module stays free of any import of the API layer, the
    same device :class:`scistudio.core.dropins.SupportsScanDirs` uses.
    """

    path: str
    tutorial_source_kind: str | None
    tutorial_source_id: str | None
    tutorial_id: str | None


@dataclass(frozen=True)
class TutorialProjectPlan:
    """Everything the API layer needs to create one tutorial project.

    A plan rather than a call, because the caller that has to make the call is
    the one holding the ``ApiRuntime`` this module may not import. The same plan
    also answers the FR-067 confirmation, which needs the directory named before
    anything is created or deleted.
    """

    key: TutorialKey
    parent: Path
    dir_name: str
    path: Path
    name: str
    description: str


def _slug(value: str) -> str:
    """Return *value* reduced to ``[a-z0-9-]``, the directory-name alphabet."""
    return "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-")


def tutorial_project_dir_name(key: TutorialKey) -> str:
    """Return the directory name *key*'s project occupies under the parent.

    Core tutorials get their bare id, so the common case reads as the tutorial
    it is: ``~/SciStudio Tutorials/welcome-to-scistudio``. Every other source
    prefixes its kind and id, separated by :data:`_COMPONENT_SEPARATOR`.

    The scheme is injective, which FR-019 needs it to be: slugs contain no dot,
    so a core name (no dot) can never equal a non-core one (two dots), and two
    non-core names are equal only when all three components are. Two packages
    shipping ``intro`` therefore get two directories rather than one they fight
    over.
    """
    tutorial = _slug(key.tutorial_id) or "tutorial"
    if key.source_kind == "core":
        return tutorial
    source = _slug(key.source_id) or key.source_kind
    return f"{_slug(key.source_kind)}{_COMPONENT_SEPARATOR}{source}{_COMPONENT_SEPARATOR}{tutorial}"


def tutorial_project_path(key: TutorialKey) -> Path:
    """Return where *key*'s tutorial project lives (FR-062, FR-066).

    A pure function of the identity, which is what makes FR-066's "creates a new
    one at the same location" true without recording the previous location
    anywhere.
    """
    return tutorial_parent_dir() / tutorial_project_dir_name(key)


def plan_tutorial_project(key: TutorialKey, title: str) -> TutorialProjectPlan:
    """Return the plan for *key*'s project, displayed under *title*.

    The display name is the tutorial's own title, so the project reads as the
    tutorial in every surface that shows a project name, while the directory
    name stays identity-derived and stable across restarts.
    """
    parent = tutorial_parent_dir()
    dir_name = tutorial_project_dir_name(key)
    return TutorialProjectPlan(
        key=key,
        parent=parent,
        dir_name=dir_name,
        path=parent / dir_name,
        name=title or key.tutorial_id,
        description=(
            f"Learning Center workspace for the {title or key.tutorial_id!r} tutorial. "
            "It is removed when the tutorial is restarted and when tutorial data is cleared."
        ),
    )


# ---------------------------------------------------------------------------
# The known-projects marker (FR-063, FR-064, FR-065)
# ---------------------------------------------------------------------------


def tutorial_key_of(entry: SupportsTutorialMarker) -> TutorialKey | None:
    """Return the tutorial *entry* belongs to, or ``None`` for a user project.

    The marker is read as a whole: an entry is a tutorial project only when it
    carries a complete identity, so a half-written entry is treated as a user
    project. That is the safe direction — a user project wrongly marked would
    vanish from every listing surface (FR-065) with no way for the user to find
    it again, while a tutorial project wrongly unmarked is merely visible.
    """
    kind = entry.tutorial_source_kind
    tutorial_id = entry.tutorial_id
    if not kind or not tutorial_id or kind not in SOURCE_KINDS:
        return None
    return TutorialKey(source_kind=kind, source_id=entry.tutorial_source_id or "", tutorial_id=tutorial_id)


def is_tutorial_entry(entry: SupportsTutorialMarker) -> bool:
    """Return whether *entry* is a tutorial project (FR-064).

    The predicate the listing route filters on (FR-065).
    """
    return tutorial_key_of(entry) is not None


def tutorial_entries(entries: Iterable[SupportsTutorialMarker]) -> tuple[SupportsTutorialMarker, ...]:
    """Return only the tutorial projects among *entries*."""
    return tuple(entry for entry in entries if is_tutorial_entry(entry))


def find_tutorial_project(entries: Iterable[SupportsTutorialMarker], key: TutorialKey) -> SupportsTutorialMarker | None:
    """Return the known-projects entry for *key*, or ``None``.

    What FR-066 resolves against: restarting deletes *that tutorial's* previous
    project, and the registry is the record of which one that was.
    """
    for entry in entries:
        if tutorial_key_of(entry) == key:
            return entry
    return None


# ---------------------------------------------------------------------------
# Existence, creation of the shared directories
# ---------------------------------------------------------------------------


def tutorial_project_exists(path: str | Path) -> bool:
    """Return whether *path* is still a usable project directory (FR-069).

    A tutorial project the user deleted outside the product must invalidate its
    session on the next interaction and be offered from the start. The session
    asks this; ``project.yaml`` is the same evidence
    :meth:`scistudio.api.runtime.ApiRuntime.list_projects` prunes stale entries
    on, so the two agree about what "gone" means.
    """
    target = Path(path)
    return target.is_dir() and (target / "project.yaml").is_file()


def ensure_tutorial_parent() -> Path:
    """Create and return :func:`tutorial_parent_dir` (FR-062)."""
    parent = tutorial_parent_dir()
    parent.mkdir(parents=True, exist_ok=True)
    return parent


def scoped_library_dirs() -> tuple[Path, ...]:
    """Return the tutorial-scoped library's tier directories (FR-070)."""
    root = tutorial_library_dir()
    return (root / BLOCKS_DIR_NAME, root / TYPES_DIR_NAME)


def ensure_scoped_library() -> Path:
    """Create the tutorial-scoped library and return its root (FR-070).

    Created eagerly at bootstrap rather than on first write, because the
    save-to-library action the scenarios teach has to land somewhere and a
    tutorial step that fails on a missing directory teaches the wrong lesson.
    Both registries skip missing scan directories, so an empty library costs
    nothing until something is saved into it.
    """
    root = tutorial_library_dir()
    for directory in scoped_library_dirs():
        directory.mkdir(parents=True, exist_ok=True)
    return root


# ---------------------------------------------------------------------------
# Deletion (FR-066, FR-067, FR-073)
# ---------------------------------------------------------------------------


def _remove_tree(target: Path) -> None:
    """Remove *target* recursively, defeating read-only files first.

    A tutorial project is a git repository (``create_project`` auto-inits one),
    and git writes its object files read-only, which plain
    :func:`shutil.rmtree` cannot remove on Windows. This is the same hazard
    ``scistudio.api.runtime._helpers._rmtree_force`` handles, and callers that
    hold that helper should pass it as *remove_tree*: it additionally retries
    around file watchers and SQLite WAL handles. It is not imported here because
    ``scistudio.tutorials`` may not import ``scistudio.api``; what is duplicated
    is the chmod pass alone, and a caller that wants the full treatment injects
    it rather than reimplementing it.
    """
    if not target.exists():
        return
    for root, dirs, files in os.walk(target):
        with suppress(OSError):
            os.chmod(root, stat.S_IRWXU)
        for name in dirs:
            with suppress(OSError):
                os.chmod(Path(root) / name, stat.S_IRWXU)
        for name in files:
            with suppress(OSError):
                os.chmod(Path(root) / name, stat.S_IWRITE | stat.S_IREAD)
    with suppress(OSError):
        os.chmod(target, stat.S_IRWXU)
    shutil.rmtree(target, ignore_errors=True)
    if target.exists():
        raise OSError(f"Could not remove {target}")


def _guarded_remove(target: Path, remove_tree: RemoveTree | None) -> bool:
    """Remove *target* after checking it is inside the tutorial parent.

    Every deleting entry point funnels through here. The check is not
    defence-in-depth against this module's own callers so much as the one place
    the FR-073 promise — user projects are untouched — is enforced: nothing
    outside :func:`scistudio.core.dropins.tutorial_parent_dir` can be removed by
    any function in this module, whatever it is handed.
    """
    if not is_tutorial_location(target):
        raise ValueError(f"Refusing to delete {target}: not inside {tutorial_parent_dir()}")
    if target.resolve() == tutorial_parent_dir().resolve():
        raise ValueError("Refusing to delete the tutorial parent directory itself")
    if not target.exists():
        return False
    (remove_tree or _remove_tree)(target)
    return True


def restart_preview(entries: Iterable[SupportsTutorialMarker], key: TutorialKey) -> Path | None:
    """Return the directory restarting *key* would delete, or ``None``.

    The data FR-067's confirmation needs, which is the directory itself: the
    label says "restart" while the effect is deleting a folder, and the user is
    entitled to see which one before agreeing. Read from the known-projects
    entry rather than recomputed from the identity, so what is named is what
    exists.
    """
    entry = find_tutorial_project(entries, key)
    if entry is None:
        return None
    path = Path(entry.path)
    return path if path.exists() else None


def delete_tutorial_project(path: str | Path, *, remove_tree: RemoveTree | None = None) -> bool:
    """Delete one tutorial project directory; return whether it existed.

    FR-066's first half. Removing the known-projects entry is the caller's, for
    the same reason creation is: the registry lives on the ``ApiRuntime``.
    """
    return _guarded_remove(Path(path), remove_tree)


def clear_preview() -> tuple[Path, ...]:
    """Return the directories clearing tutorial data would delete (FR-088).

    Every tutorial project plus the scoped library, in that order, and only the
    ones that exist — a confirmation listing directories that are not there
    would read as a threat the product cannot carry out. The listing is the
    tutorial parent's children rather than the marked known-projects entries,
    because a project whose entry was pruned (its ``project.yaml`` removed by
    hand, say) is still a directory the user asked to be rid of.
    """
    parent = tutorial_parent_dir()
    if not parent.is_dir():
        return ()
    library = tutorial_library_dir()
    projects = sorted(child for child in parent.iterdir() if child.is_dir() and child != library)
    return (*projects, *((library,) if library.is_dir() else ()))


def clear_tutorial_data(*, remove_tree: RemoveTree | None = None) -> tuple[Path, ...]:
    """Delete every tutorial project and the scoped library (FR-073).

    Returns what was actually deleted, which is what the response reports rather
    than the preview it was asked to confirm: the two can differ if something
    disappeared in between, and reporting the preview would claim a deletion
    that did not happen.

    The tutorial parent itself is left in place, empty. It is the product's
    directory rather than the user's, it is recreated on the next bootstrap
    anyway, and removing it would also remove anything the user had put beside a
    tutorial project without telling us.
    """
    deleted: list[Path] = []
    for target in clear_preview():
        if _guarded_remove(target, remove_tree):
            deleted.append(target)
    return tuple(deleted)
