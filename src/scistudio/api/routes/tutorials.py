"""Learning Center endpoints: the catalogue, the session, progress, and clearing.

ADR-053 Learning Center spec (``docs/specs/adr-053-learning-center.md``),
checklist §6.1.6. FR-003 removed the previous contents of this module — a single
``POST /api/tutorials/run-first-workflow/bootstrap`` that scaffolded one
hardcoded project — rather than keeping it as an alias, so that route now 404s.

This layer owns no tutorial behaviour. :class:`~scistudio.tutorials.session.TutorialRuntime`
decides what is listed, what is running, which step it is on, and when a step is
satisfied; everything here either renders one of its return values as JSON or
supplies one of the four ports it is constructed with. That split is what keeps
``api -> tutorials`` a one-way edge: the tutorial package may not import
``scistudio.api`` (checklist §6.1.2), so product state, the two API-layer event
names, project creation and deletion, and replay byte delivery all arrive from
here.

The four ports, and where each one's truth lives
------------------------------------------------

* :class:`_ApiProductState` satisfies :class:`~scistudio.tutorials.conditions.ProductState`.
  Every method is a pure read of something the product already knows (FR-046,
  FR-055) — the workflow definition, the three registries, the plot manifests,
  the lineage store, git, and the tutorial-scoped library. Three terms have no
  pre-existing store, so this module keeps one: see :class:`_RecordedSignals`.
* :data:`_EXTERNAL_EVENTS` carries the two FR-050 event names declared under
  ``scistudio.api``, as the constants rather than as literals (checklist §6.1.5).
* :class:`_RuntimeProvisioner` creates the tutorial project through
  ``ApiRuntime.create_project`` so it lands in the known-projects registry with
  its marker (FR-063, FR-064), and deletes it with ``_rmtree_force``.
* :func:`~scistudio.api.routes.ai_pty.replay.open_replay_tab` supplies the
  scripted byte source, delivered through the product's real PTY path (FR-061a).

Re-evaluation is event-driven, never polled (FR-051). The runtime subscribes to
exactly the event types it maps and re-judges the active step when one arrives,
which advances and persists the session; the frontend sees the result on its
next read of ``/sessions/active``.
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from scistudio.api.deps import get_runtime
from scistudio.api.file_contracts import FILE_CHANGED_EVENT_TYPE
from scistudio.api.routes.ai_pty.replay import open_replay_tab
from scistudio.api.runtime import ApiRuntime
from scistudio.api.runtime._helpers import _rmtree_force
from scistudio.api.ws import BLOCKS_RELOADED
from scistudio.core.dropins import BLOCKS_DIR_NAME, TYPES_DIR_NAME, tutorial_library_dir
from scistudio.engine.events import INTERACTIVE_COMPLETE, EngineEvent
from scistudio.tutorials.conditions import UI_EVENT_NAMES, ExternalEventNames, ProductState, RunSummary
from scistudio.tutorials.discovery import Catalogue, CatalogueEntry, CatalogueGroup, DiscoveredTutorial
from scistudio.tutorials.manifest import ASSETS_DIR_NAME
from scistudio.tutorials.projects import (
    TutorialKey,
    TutorialProjectPlan,
    delete_tutorial_project,
    ensure_scoped_library,
    ensure_tutorial_parent,
    find_tutorial_project,
)
from scistudio.tutorials.session import (
    AnotherSessionActiveError,
    NoActiveSessionError,
    SessionView,
    TutorialRuntime,
    TutorialSessionError,
    TutorialUnavailableError,
)
from scistudio.workflow.definition import WorkflowDefinition

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tutorials", tags=["tutorials"])
RuntimeDep = Annotated[ApiRuntime, Depends(get_runtime)]

#: The two FR-050 event names that live under ``scistudio.api``.
#:
#: ``scistudio.engine.events`` is frozen by the ADR-035/036 hard-scope rules, so
#: these two were declared at the API and watcher layer instead, and
#: ``scistudio.tutorials`` may not import that layer. FR-050 requires the
#: subscription to use the declared constants, so they are imported and passed —
#: never spelled as literals, here or there.
#:
#: ``scistudio.api.ws`` is the copy this uses. ``api/routes/projects.py`` also
#: declares ``BLOCKS_RELOADED_EVENT_TYPE`` with the same value; ``ws.py`` is
#: chosen because it is the module ``conditions.py`` names as authoritative and
#: the one whose ``_OUTBOUND_EVENTS`` set actually carries the event to clients.
_EXTERNAL_EVENTS = ExternalEventNames(blocks_reloaded=BLOCKS_RELOADED, file_changed=FILE_CHANGED_EVENT_TYPE)

#: Attribute on the ``ApiRuntime`` holding this app's tutorial wiring.
_WIRING_ATTR = "_scistudio_tutorial_wiring"

_T = TypeVar("_T")

#: How many recent runs a ``run_succeeded`` or ``port_has_output`` term reads.
#:
#: Both terms ask whether something *ever* succeeded, which over a long project
#: history is an unbounded question and is asked on every ``block_done``. The
#: bound keeps the cost flat; a tutorial step judges the run the user just
#: performed, which is always within it.
_RUN_HISTORY_LIMIT = 25

#: The reserved asset subdirectory holding a tutorial's reading pages (FR-006).
_PAGES_DIR_NAME = "pages"


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class StartSessionRequest(BaseModel):
    """Which tutorial to start, and whether to start it over."""

    source_kind: str = Field(description="Where the tutorial came from: core, package, user, or project.")
    source_id: str = Field(default="", description="Empty for core, the distribution name for a package.")
    tutorial_id: str = Field(description="The tutorial's id within its source.")
    restart: bool = Field(
        default=False,
        description="Start over, deleting the tutorial's project and its recorded position first.",
    )

    def key(self) -> TutorialKey:
        return TutorialKey(
            source_kind=self.source_kind,
            source_id=self.source_id,
            tutorial_id=self.tutorial_id,
        )


class UiEventRequest(BaseModel):
    """A named interface event the user just caused."""

    name: str = Field(description="The event name. One of a closed set the product declares.")


class ClearDataRequest(BaseModel):
    """Confirmation for deleting every tutorial project and the tutorial library."""

    confirm: bool = Field(default=False, description="Must be true; the deletion is not reversible.")


# ---------------------------------------------------------------------------
# Responses (checklist §6.1.6)
# ---------------------------------------------------------------------------


class StepResponse(BaseModel):
    """The step a tutorial is currently on."""

    id: str
    index: int
    total: int
    say: str | None = None
    highlight: str | None = None
    route_to: str | None = None
    awaiting_continue: bool = False


class ReplayResponse(BaseModel):
    """The scripted playback currently attached to a terminal tab, if any."""

    surface: str
    tab_id: str


class SessionResponse(BaseModel):
    """One tutorial session: where it is, what it says, and how it ended."""

    source_kind: str
    source_id: str
    tutorial_id: str
    title: str
    project_id: str | None = None
    project_path: str | None = None
    step: StepResponse | None = None
    satisfied_step_ids: list[str] = Field(default_factory=list)
    status: str
    error: str | None = None
    replay: ReplayResponse | None = None


class CatalogueEntryResponse(BaseModel):
    """One tutorial as the Learning Center lists it."""

    source_kind: str
    source_id: str
    id: str
    title: str
    summary: str
    cover_url: str | None = None
    order: int | None = None
    state: str
    unavailable_reason: str | None = None
    project_directory: str | None = None
    reading: bool = False


class CatalogueGroupResponse(BaseModel):
    """One source's tutorials, with that source's own counts."""

    source_kind: str
    source_id: str
    label: str
    completed: int
    total: int
    tutorials: list[CatalogueEntryResponse] = Field(default_factory=list)


class CatalogueResponse(BaseModel):
    """Everything the Learning Center shows when it opens."""

    groups: list[CatalogueGroupResponse] = Field(default_factory=list)
    active: SessionResponse | None = None
    diagnostics: list[str] = Field(default_factory=list)


class ProgressGroupResponse(BaseModel):
    """One source's completion counts. No total across sources is reported."""

    source_kind: str
    source_id: str
    label: str
    completed: int
    total: int


class ProgressResponse(BaseModel):
    """Completion counts, grouped by where the tutorials came from."""

    groups: list[ProgressGroupResponse] = Field(default_factory=list)


class ClearPreviewResponse(BaseModel):
    """The directories that clearing tutorial data would delete."""

    directories: list[str] = Field(default_factory=list)


class ClearDataResponse(BaseModel):
    """The directories that clearing tutorial data actually deleted."""

    deleted_directories: list[str] = Field(default_factory=list)


class UnlockResponse(BaseModel):
    """Whether the product owes the user the one progress-driven offer."""

    work_import_offer_pending: bool


# ---------------------------------------------------------------------------
# The three signals the product does not already record
# ---------------------------------------------------------------------------


class _RecordedSignals:
    """Truth for the three terms nothing else in the product stores.

    The other thirteen terms read something that exists anyway — a registry, the
    workflow file, the lineage database, git. These three do not, each for its
    own reason, and all three are still *backend* state by the time a condition
    reads them, which is what FR-046 requires:

    * ``ui_event`` is the one signal that originates in the frontend (FR-052).
      It exists precisely because enlarging a preview or opening a tab leaves no
      backend state behind, so the frontend reports it and this records it.
    * ``interaction_completed``: the ``interactive_complete`` event is consumed
      by the scheduler to resolve the block's waiting future and is then
      discarded, so nothing keeps the set of node ids that were submitted.
    * ``page_reached``: a page is reached by being served, and the route that
      serves it is the only thing that knows.

    Held for the life of the process rather than persisted. A restart loses
    them, which is the correct trade: re-reporting is a click, and persisting
    would make a stale marker outlive the tutorial project it referred to.
    """

    def __init__(self) -> None:
        self.ui_events: set[str] = set()
        self.interactions: set[str] = set()
        self.pages: set[str] = set()

    def record_ui_event(self, name: str) -> None:
        self.ui_events.add(name)

    def record_page(self, name: str) -> None:
        self.pages.add(name)

    def on_interactive_complete(self, event: EngineEvent) -> None:
        """Record the node whose interactive panel was just submitted."""
        if event.block_id:
            self.interactions.add(str(event.block_id))


# ---------------------------------------------------------------------------
# The product-state port (checklist §6.1.3, FR-046, FR-055)
# ---------------------------------------------------------------------------


@dataclass
class _ApiProductState:
    """Reads product truth for the condition evaluator. Every method is a read.

    Rebuilt per evaluation rather than held, because ``project_dir`` and
    ``tutorial_library_dir`` are plain attributes on the protocol while the open
    project can change underneath: constructing them at read time is what keeps
    them from going stale without making the protocol's shape a lie.

    FR-055 is a property of this class as a whole. Nothing below creates a file,
    mutates a registry, opens a project, or triggers a run; the two methods that
    touch a database open it read-only through the existing store, and every
    failure path returns "no" rather than raising, because a condition that
    cannot be judged is not satisfied and must not end the session.
    """

    runtime: ApiRuntime
    recorded: _RecordedSignals
    project_dir: Path | None
    tutorial_library_dir: Path | None

    # -- the workflow ----------------------------------------------------

    def workflow(self) -> WorkflowDefinition | None:
        """The workflow the user is editing, or ``None`` when there is none.

        The GUI reports which workflow is open and the runtime persists it, so
        that is the first answer. A project whose active workflow was never
        reported falls back to its first workflow, which is the same answer
        ``project_response`` gives as ``current_workflow_id`` — a tutorial
        project has exactly one, ``main``, so the fallback is the normal path
        during a tutorial rather than an edge case.
        """
        if self.runtime.active_project is None:
            return None
        workflow_id = self.runtime.active_workflow_id
        if not workflow_id:
            available: list[str] = _read_or(self.runtime.list_project_workflows, [])
            if not available:
                return None
            workflow_id = available[0]
        try:
            return self.runtime.load_workflow(workflow_id)
        except (FileNotFoundError, OSError, ValueError):
            return None

    # -- the three registries --------------------------------------------

    def block_type_names(self) -> frozenset[str]:
        """Every name a block is registered under.

        The block registry is keyed by *display* name — "Load Data" — while a
        ``block_type`` argument is the stable type name a saved workflow stores,
        ``load_data``. Reading the keys alone would therefore make
        ``block_registered`` false for every correctly written condition, so
        this reports the type names.

        Both are reported, because ``BlockRegistry.get_spec`` accepts either and
        a tutorial author reading the palette will write what the palette shows.
        Matching the product's own resolution rule is what stops a step hanging
        on a name the product would have resolved.
        """
        specs: dict[str, Any] = _read_or(self.runtime.block_registry.all_specs, {})
        names = set(specs)
        names.update(str(spec.type_name) for spec in specs.values() if getattr(spec, "type_name", ""))
        return frozenset(names)

    def data_type_names(self) -> frozenset[str]:
        specs: dict[str, Any] = _read_or(self.runtime.type_registry.all_types, {})
        return frozenset(specs)

    def previewer_type_ids(self) -> frozenset[str]:
        """The data types that have a previewer registered for them.

        ``previewer_registered`` takes a ``type_name`` and judges "a previewer is
        registered for a given type" (FR-047), so this is the set of
        ``target_type`` values rather than of previewer ids. A previewer is
        interesting to a tutorial for the type it can display, and the id is an
        internal handle the user never sees.
        """
        specs: list[Any] = _read_or(lambda: self.runtime.get_preview_service().registry.all_specs(), [])
        return frozenset(str(spec.target_type) for spec in specs if getattr(spec, "target_type", None))

    # -- plots ------------------------------------------------------------

    def plot_bindings(self) -> tuple[tuple[str, str, str], ...]:
        """``(plot_id, node_id, output_port)`` for every plot in the project.

        Read from the plot manifests on disk, which is where a plot lives — the
        same enumeration ``GET /api/plots`` performs. A plot binds one-to-one to
        a node and an output port, so a manifest whose target names neither is
        skipped rather than reported with empty strings that could match a
        condition asking for a specific port.
        """
        project_dir = self.project_dir
        if project_dir is None:
            return ()
        from scistudio.plot.validation import load_plot

        bindings: list[tuple[str, str, str]] = []
        plots_dir = project_dir / "plots"
        if not plots_dir.is_dir():
            return ()
        for manifest_path in sorted(plots_dir.glob("*/plot.yaml")):
            plot_id = manifest_path.parent.name
            try:
                loaded = load_plot(self.runtime, plot_id=plot_id)
            except Exception:
                # One unreadable plot must not hide the others, for the reason
                # discovery gives about one malformed manifest (FR-022).
                logger.debug("Learning Center: plot %r could not be read", plot_id, exc_info=True)
                continue
            target = getattr(loaded.manifest, "target", None)
            node_id = getattr(target, "node_id", None)
            output_port = getattr(target, "output_port", None)
            if node_id and output_port:
                bindings.append((str(loaded.plot_id), str(node_id), str(output_port)))
        return tuple(bindings)

    # -- runs -------------------------------------------------------------

    def run_records(self) -> tuple[RunSummary, ...]:
        """The recent runs, projected into what a condition may ask about.

        The lineage store is the record of what ran, so it survives the restart
        FR-037 promises to resume across: a step satisfied by a successful run
        stays satisfied after the backend comes back.
        """
        store = self.runtime.lineage_store
        if store is None:
            return ()
        rows: list[dict[str, Any]] = _read_or(lambda: store.list_runs(limit=_RUN_HISTORY_LIMIT), [])
        summaries: list[RunSummary] = []
        for row in rows:
            run_id = str(row.get("run_id") or "")
            if not run_id:
                continue
            executions: list[dict[str, Any]] = _read_or(lambda rid=run_id: store.list_block_executions(rid), [])
            summaries.append(
                RunSummary(
                    run_id=run_id,
                    workflow_id=str(row.get("workflow_id") or ""),
                    succeeded=row.get("status") == "completed",
                    succeeded_node_ids=frozenset(
                        str(execution.get("block_id") or "")
                        for execution in executions
                        if execution.get("termination") == "completed" and execution.get("block_id")
                    ),
                )
            )
        return tuple(summaries)

    def port_has_output(self, node_id: str, port: str) -> bool:
        """Whether ``node_id``'s ``port`` holds data.

        Asked of both halves of the product's own answer, because they go stale
        in opposite directions. The scheduler's in-memory outputs are what the
        product itself consults to decide whether a plot target is ready, and
        they are current the instant a block finishes; the lineage store's
        input/output edges are written per block execution and survive a
        restart. A step waiting on an output must not regress because the
        backend was restarted, nor wait for a database write to land.
        """
        for run in list(self.runtime.workflow_runs.values()):
            scheduler = getattr(run, "scheduler", None)
            outputs = getattr(scheduler, "_block_outputs", None)
            if isinstance(outputs, dict):
                produced = outputs.get(node_id)
                if isinstance(produced, dict) and port in produced:
                    return True

        store = self.runtime.lineage_store
        if store is None:
            return False
        rows: list[dict[str, Any]] = _read_or(lambda: store.list_runs(limit=_RUN_HISTORY_LIMIT), [])
        for row in rows:
            run_id = str(row.get("run_id") or "")
            if not run_id:
                continue
            executions: list[dict[str, Any]] = _read_or(lambda rid=run_id: store.list_block_executions(rid), [])
            wanted = {
                str(execution.get("block_execution_id"))
                for execution in executions
                if execution.get("block_id") == node_id
            }
            if not wanted:
                continue
            edges: list[dict[str, Any]] = _read_or(lambda rid=run_id: store.list_block_io_with_objects(rid), [])
            for edge in edges:
                if (
                    edge.get("direction") == "output"
                    and edge.get("port_name") == port
                    and str(edge.get("block_execution_id")) in wanted
                ):
                    return True
        return False

    # -- git ---------------------------------------------------------------

    def git_branches(self) -> frozenset[str]:
        engine = self._git_engine()
        if engine is None:
            return frozenset()
        branches: list[dict[str, Any]] = _read_or(engine.branches, [])
        return frozenset(str(branch.get("name")) for branch in branches if branch.get("name"))

    def git_current_branch(self) -> str | None:
        engine = self._git_engine()
        if engine is None:
            return None
        current: str | None = _read_or(engine.current_branch, None)
        return current

    def _git_engine(self) -> Any:
        """A git engine for the open project, or ``None`` when there is no repo.

        Constructed per call rather than held: it is cheap, and a held one would
        point at the previous project after a switch. Every failure — no
        project, not a repository, no bundled git binary — is ``None``, so a git
        condition in a project without git is unsatisfied rather than fatal.
        """
        project_dir = self.project_dir
        if project_dir is None:
            return None
        from scistudio.core.versioning.git_engine import GitEngine

        try:
            engine = GitEngine(project_dir)
            return engine if engine.is_repository(project_dir) else None
        except Exception:
            logger.debug("Learning Center: no usable git engine for %s", project_dir, exc_info=True)
            return None

    # -- the tutorial-scoped library ---------------------------------------

    def library_entries(self) -> frozenset[tuple[str, str]]:
        """``(kind, name)`` for everything saved into the tutorial-scoped library.

        Read from the registries rather than from the filenames, so the name a
        condition matches is the name the product registered — the block type or
        the class name — rather than the stem of whatever file it was saved to.
        Membership is decided by the spec's source file sitting under the scoped
        library, which is the definition of the library holding it.

        Only ``block`` and ``type`` can appear. ``scoped_library_dirs`` creates
        exactly those two directories (FR-070) and the previewer registry does
        not scan the library at all, so a ``library_contains`` condition naming
        ``previewer`` cannot become true; the vocabulary accepts the kind, which
        makes that a gap in the library rather than in this method.
        TODO(#2057): give the tutorial-scoped library a ``previewers`` tier, or
            drop ``previewer`` from ``library_contains``' accepted kinds, so the
            vocabulary and the library agree.
            Followup: https://github.com/jiazhenz026/SciStudio/issues/2057
        """
        library = self.tutorial_library_dir
        if library is None:
            return frozenset()
        entries: set[tuple[str, str]] = set()
        blocks_dir = library / BLOCKS_DIR_NAME
        types_dir = library / TYPES_DIR_NAME
        block_specs: dict[str, Any] = _read_or(self.runtime.block_registry.all_specs, {})
        type_specs: dict[str, Any] = _read_or(self.runtime.type_registry.all_types, {})
        for name, spec in block_specs.items():
            if _is_under(getattr(spec, "file_path", None), blocks_dir):
                # Both names, for the reason ``block_type_names`` reports both.
                entries.add(("block", str(name)))
                if getattr(spec, "type_name", ""):
                    entries.add(("block", str(spec.type_name)))
        for name, spec in type_specs.items():
            if _is_under(getattr(spec, "file_path", None), types_dir):
                entries.add(("type", str(name)))
        return frozenset(entries)

    # -- the three recorded signals ----------------------------------------

    def interactions_completed(self) -> frozenset[str]:
        return frozenset(self.recorded.interactions)

    def pages_reached(self) -> frozenset[str]:
        return frozenset(self.recorded.pages)

    def ui_events(self) -> frozenset[str]:
        return frozenset(self.recorded.ui_events)


def _read_or(read: Callable[..., _T], default: _T) -> _T:
    """Perform one product-state read, returning *default* if it fails.

    Judging a step must never be what takes the session down: a condition that
    cannot be evaluated is simply not satisfied yet, and the user retries by
    doing the thing the step asked for. The alternative — letting a locked
    SQLite file or a half-written registry raise — would end the tutorial with
    an error naming the tutorial rather than the fault.
    """
    try:
        return read()
    except Exception:
        logger.debug("Learning Center: a product-state read failed", exc_info=True)
        return default


def _is_under(candidate: str | Path | None, parent: Path) -> bool:
    """Whether *candidate* is a path inside *parent*."""
    if not candidate:
        return False
    try:
        return Path(candidate).resolve().is_relative_to(parent.resolve())
    except (OSError, ValueError):
        return False


# ---------------------------------------------------------------------------
# The project provisioner (FR-062 … FR-066)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _RuntimeProvisioner:
    """Creates and deletes tutorial projects on the session's behalf.

    The session decides *when*, and hands over a plan naming where and under
    what name; only this side can call ``create_project``, which is what puts
    the project in the known-projects registry with its marker (FR-063,
    FR-064) — several routes resolve a project's real path through that
    registry, so an unregistered tutorial project could not be operated at all.
    """

    runtime: ApiRuntime

    def create(self, plan: TutorialProjectPlan) -> Path:
        """Create the planned project and return its directory.

        The scoped library is created alongside it (FR-070) rather than on first
        write, because the save-to-library step a scenario teaches has to land
        somewhere and a step that fails on a missing directory teaches the wrong
        lesson.
        """
        ensure_tutorial_parent()
        ensure_scoped_library()
        project = self.runtime.create_project(
            plan.name,
            plan.description,
            str(plan.parent),
            dir_name=plan.dir_name,
            tutorial_source_kind=plan.key.source_kind,
            tutorial_source_id=plan.key.source_id,
            tutorial_id=plan.key.tutorial_id,
        )
        return Path(project.path)

    def delete(self, key: TutorialKey, path: Path) -> None:
        """Remove the project directory and its known-projects entry (FR-066).

        A registered project is removed through ``delete_project``, which does
        both halves and one more thing neither half can: it closes the lineage
        database first. A tutorial project is the active project while its
        tutorial runs, so its SQLite file is open, and removing the directory
        underneath an open handle is what fails on Windows.

        A project with no entry — the tutorial was never started, or its entry
        was already pruned — is a directory and nothing else, so it is removed
        directly. ``_rmtree_force`` is passed in explicitly there because
        ``scistudio.tutorials`` may not import this package: its own default is
        a chmod pass plus ``shutil.rmtree``, while this helper also retries
        around the file watcher and any handle that is still closing.
        """
        entry = find_tutorial_project(self.runtime.list_projects(), key)
        entry_id = getattr(entry, "id", None) if entry is not None else None
        if entry_id is not None:
            try:
                self.runtime.delete_project(str(entry_id))
                return
            except (OSError, ValueError, FileNotFoundError):
                # Fall through to the directory removal below: a registry entry
                # that cannot be deleted must not leave the directory behind,
                # because the next start would restart into its own leftovers.
                logger.warning("Learning Center: could not delete tutorial project %s", entry_id, exc_info=True)
        delete_tutorial_project(path, remove_tree=_rmtree_force)


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _TutorialWiring:
    """This app's tutorial runtime and the signal store behind its product state.

    The two are kept together because two different routes need them: the
    session endpoints drive the runtime, and the page endpoint records into the
    signals. Reaching the second through the first would mean opening up the
    runtime's private port, so both are held here instead.
    """

    tutorials: TutorialRuntime
    recorded: _RecordedSignals


#: Project subdirectories whose contents the registries scan (ADR-036 drop-ins).
#:
#: Named from ``scistudio.core.dropins`` rather than spelled here, so a tier
#: that gains a directory does not need this list edited to keep working.
_SCANNED_PROJECT_DIRS: frozenset[str] = frozenset({BLOCKS_DIR_NAME, TYPES_DIR_NAME})


def _wrote_into_a_scanned_dir(written: Sequence[Path], *, project_dir: Path | None) -> bool:
    """Whether any written path lands in a directory the registries scan.

    Asked so that copying a CSV into ``data/raw`` does not re-scan every
    registry. The test is on the path's position under the project rather than
    on its suffix: a ``.py`` file under ``data/`` is not a block, and a block is
    a block because of where it sits.
    """
    if project_dir is None:
        return False
    for path in written:
        try:
            relative = path.resolve().relative_to(project_dir.resolve())
        except (OSError, ValueError):
            continue
        if relative.parts and relative.parts[0] in _SCANNED_PROJECT_DIRS:
            return True
    return False


def _build_wiring(runtime: ApiRuntime) -> _TutorialWiring:
    """Construct the tutorial runtime with this app's five ports filled in."""
    recorded = _RecordedSignals()
    # Holds the in-flight broadcast tasks. Without a strong reference the loop
    # keeps only a weak one and may collect a task mid-await, dropping the
    # frame that tells open palettes to refetch.
    broadcasts: set[asyncio.Task[None]] = set()

    def product_state() -> ProductState:
        return _ApiProductState(
            runtime=runtime,
            recorded=recorded,
            project_dir=runtime.project_dir,
            tutorial_library_dir=tutorial_library_dir(),
        )

    def files_written(written: Sequence[Path]) -> None:
        """Re-scan the registries when a step writes a block or a type (FR-059).

        A step that writes ``blocks/normalize_fluorescence.py`` and then says
        "find Normalize Fluorescence in the palette" is unfollowable until this
        runs: the file is on disk and the block is not in the registry. FR-059
        orders actions before the step's text so that a step claiming something
        exists is true when read, and for a block "exists" means the product
        has it, not that a file does.

        ``refresh_all_registries`` rather than a block-only re-scan, for the
        reason ``POST /api/blocks/reload`` gives: a step may write a type
        alongside its block, and a fresh block registry beside a stale type
        registry is its own bug.

        The broadcast that follows is what makes open palettes redraw. It is
        scheduled rather than awaited because this is called from a synchronous
        step-entry path; the *registry* is already correct before the step's
        text is revealed, and the frame only tells clients to refetch. A
        runtime with no event bus or no loop — every test, and any headless
        run — simply skips it.
        """
        if not _wrote_into_a_scanned_dir(written, project_dir=runtime.project_dir):
            return
        runtime.refresh_all_registries()

        event_bus = getattr(runtime, "event_bus", None)
        if event_bus is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        specs: dict[str, Any] = _read_or(runtime.block_registry.all_specs, {})
        event = EngineEvent(
            event_type=BLOCKS_RELOADED,
            data={"added": [], "removed": [], "reloaded": sorted(specs), "source": "tutorial"},
        )
        task = loop.create_task(_emit_quietly(event_bus, event))
        broadcasts.add(task)
        task.add_done_callback(broadcasts.discard)

    tutorials = TutorialRuntime(
        product_state=product_state,
        external_events=_EXTERNAL_EVENTS,
        project_dir=lambda: runtime.project_dir,
        provisioner=_RuntimeProvisioner(runtime=runtime),
        open_replay=open_replay_tab,
        record_ui_event=recorded.record_ui_event,
        files_written=files_written,
    )
    _subscribe(runtime, tutorials, recorded)
    return _TutorialWiring(tutorials=tutorials, recorded=recorded)


async def _emit_quietly(event_bus: Any, event: EngineEvent) -> None:
    """Emit *event*, logging rather than raising: a failed broadcast is not a failed step."""
    try:
        await event_bus.emit(event)
    except Exception:
        logger.exception("tutorial step: blocks.reloaded broadcast failed")


def _subscribe(runtime: ApiRuntime, tutorials: TutorialRuntime, recorded: _RecordedSignals) -> None:
    """Re-judge the active step whenever a mapped event is observed (FR-050).

    The whole of the runtime's connection to the bus. There is no timer and no
    background task (FR-051): each subscription fires only when the product
    does something, and an event whose terms the current step does not use
    returns without reading anything.

    Re-evaluation persists the session, so the effect is visible on the next
    read of ``/sessions/active``. Nothing is pushed to the frontend, because no
    frame type exists for it: the frontend re-reads the session on reconnect and
    can ask for an evaluation explicitly (FR-053).
    """

    def _on_event(event: EngineEvent) -> None:
        try:
            tutorials.handle_event(event.event_type)
        except Exception:
            # A failure here must not break the event that carried it: this
            # subscriber is a bystander on every one of these events.
            logger.debug("Learning Center: re-evaluation after %s failed", event.event_type, exc_info=True)

    # The recorder goes first, and the order is load-bearing rather than
    # incidental. ``interactive_complete`` is both the event that records an
    # interaction and one of the events that re-judges the step, and the bus
    # calls subscribers in registration order. Re-judging first would read the
    # set as it was before the interaction, so a step waiting on that very
    # interaction would not advance until something else happened to re-evaluate
    # it — the kind of stuck step that never says why.
    runtime.event_bus.subscribe(INTERACTIVE_COMPLETE, recorded.on_interactive_complete)
    for event_type in tutorials.subscribed_event_types():
        runtime.event_bus.subscribe(event_type, _on_event)


def _wiring(runtime: ApiRuntime) -> _TutorialWiring:
    """Return this app's tutorial wiring, building it on first use.

    Cached on the ``ApiRuntime`` rather than in a module global, because the
    runtime is per-app and a global would let one test's session file and event
    subscriptions leak into the next. It has to outlive the request either way:
    an open replay is a live byte source and cannot be rebuilt from the session
    file, which is why the tutorial runtime holds it and why this must be the
    same object on the next call.

    Built lazily rather than at startup so a product that never opens the
    Learning Center pays nothing. Nothing is lost by waiting: everything except
    the replay handle is re-read from disk per call, and a step satisfied while
    no one was subscribed is judged on entry the next time it is read (FR-054).
    """
    existing = getattr(runtime, _WIRING_ATTR, None)
    if not isinstance(existing, _TutorialWiring):
        existing = _build_wiring(runtime)
        setattr(runtime, _WIRING_ATTR, existing)
    return existing


def _tutorials(runtime: ApiRuntime) -> TutorialRuntime:
    """Return this app's tutorial runtime."""
    return _wiring(runtime).tutorials


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _asset_url(source_kind: str, source_id: str, tutorial_id: str, suffix: str) -> str:
    """Build a tutorial asset URL, which may carry an empty ``source_id``.

    A core tutorial's ``source_id`` is the empty string, so the contract's path
    shape genuinely produces an empty middle segment. The URL is emitted here
    and consumed verbatim by the frontend, and a companion route matches that
    shape, so the two agree rather than the frontend having to know the rule.
    """
    return f"/api/tutorials/{source_kind}/{source_id}/{tutorial_id}/{suffix}"


def _entry_response(entry: CatalogueEntry) -> CatalogueEntryResponse:
    return CatalogueEntryResponse(
        source_kind=entry.source_kind,
        source_id=entry.source_id,
        id=entry.id,
        title=entry.title,
        summary=entry.summary,
        cover_url=(
            _asset_url(entry.source_kind, entry.source_id, entry.id, "cover") if entry.cover is not None else None
        ),
        order=entry.order,
        state=str(entry.state),
        unavailable_reason=entry.unavailable_reason,
        project_directory=None if entry.project_directory is None else str(entry.project_directory),
        reading=entry.reading,
    )


def _group_response(group: CatalogueGroup) -> CatalogueGroupResponse:
    return CatalogueGroupResponse(
        source_kind=group.source_kind,
        source_id=group.source_id,
        label=group.label,
        completed=group.completed,
        total=group.total,
        tutorials=[_entry_response(entry) for entry in group.tutorials],
    )


def _session_response(runtime: ApiRuntime, view: SessionView | None) -> SessionResponse | None:
    """Render a session, resolving the project id the tutorial layer cannot know.

    ``SessionView`` carries the project's path because the tutorial package
    decides where the project goes; the id is minted by ``create_project`` and
    lives in the known-projects registry, which that package may not reach. It
    is resolved here by the tutorial marker rather than by comparing paths, so a
    project whose directory was renamed still resolves to its own entry.
    """
    if view is None:
        return None
    project_id: str | None = None
    if view.project_path is not None:
        entry = find_tutorial_project(runtime.known_projects.values(), view.key)
        entry_id = getattr(entry, "id", None)
        project_id = None if entry_id is None else str(entry_id)
    step = (
        None
        if view.step is None
        else StepResponse(
            id=view.step.id,
            index=view.step.index,
            total=view.step.total,
            say=view.step.say,
            highlight=view.step.highlight,
            route_to=view.step.route_to,
            awaiting_continue=view.step.awaiting_continue,
        )
    )
    return SessionResponse(
        source_kind=view.source_kind,
        source_id=view.source_id,
        tutorial_id=view.tutorial_id,
        title=view.title,
        project_id=project_id,
        project_path=None if view.project_path is None else str(view.project_path),
        step=step,
        satisfied_step_ids=list(view.satisfied_step_ids),
        status=str(view.status),
        error=view.error,
        replay=None if view.replay is None else ReplayResponse(surface=view.replay.surface, tab_id=view.replay.tab_id),
    )


def _catalogue_response(runtime: ApiRuntime, catalogue: Catalogue, active: SessionView | None) -> CatalogueResponse:
    return CatalogueResponse(
        groups=[_group_response(group) for group in catalogue.groups],
        active=_session_response(runtime, active),
        diagnostics=list(catalogue.diagnostics),
    )


def _acting(action: Callable[[], _T]) -> _T:
    """Run *action*, mapping the session layer's refusals onto status codes.

    ``TutorialUnavailableError`` is 422 and never 409, even though both are
    refusals to act: 409 is the frontend's signal that another tutorial is
    running and is rendered as an offer to leave it, so reusing it for "this
    tutorial cannot start" would offer to leave a session that is not the
    problem.

    ``SessionInvalidatedError`` needs no branch of its own — it is a
    ``NoActiveSessionError``, which is now the truth, and its own message
    carries the reason the session went away.
    """
    try:
        return action()
    except AnotherSessionActiveError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except TutorialUnavailableError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except NoActiveSessionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TutorialSessionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _rendered(runtime: ApiRuntime, view: SessionView) -> SessionResponse:
    """Render a session the runtime just returned, which is never absent."""
    response = _session_response(runtime, view)
    if response is None:  # pragma: no cover - a returned view is never None
        raise HTTPException(status_code=500, detail="The tutorial session could not be rendered.")
    return response


def _find_tutorial(runtime: ApiRuntime, key: TutorialKey) -> DiscoveredTutorial:
    """Return the installed tutorial *key* names, or raise 404."""
    found = _tutorials(runtime).discover().find(key)
    if found is None or found.manifest is None:
        raise HTTPException(status_code=404, detail=f"No tutorial {key.tutorial_id!r} is installed for that source.")
    return found


def _asset_file(manifest: Any, relative: str, *, what: str) -> Path:
    """Resolve one tutorial asset, keeping it inside the tutorial directory.

    Resolution goes through the manifest rather than being built from the path
    parts, because that is what applies FR-014's containment check: a request
    naming ``../`` or an absolute path is refused there, and a symlink planted
    inside the tutorial cannot carry the read outside it. Building the path here
    instead would be how that check gets bypassed.
    """
    try:
        resolved: Path = manifest.resolve_asset(relative)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=f"The {what} is not a readable asset of this tutorial.") from exc
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail=f"This tutorial has no {what}.")
    return resolved


# ---------------------------------------------------------------------------
# The catalogue
# ---------------------------------------------------------------------------


@router.get("/catalogue", response_model=CatalogueResponse)
async def get_catalogue(runtime: RuntimeDep) -> CatalogueResponse:
    """List every installed tutorial, grouped by where it came from.

    Groups are ordered with the ones SciStudio ships first, and each carries its
    own completed and total counts; no count across groups is reported, because
    a total that grows when a package is installed would make a user's progress
    appear to go backwards. Anything that could not be read is reported in
    ``diagnostics`` rather than silently emptying its group.
    """
    tutorials = _tutorials(runtime)
    return _catalogue_response(runtime, tutorials.catalogue(), tutorials.active_session())


@router.get("/progress", response_model=ProgressResponse)
async def get_progress(runtime: RuntimeDep) -> ProgressResponse:
    """Report how many tutorials from each source have been completed."""
    groups = _tutorials(runtime).progress_groups()
    return ProgressResponse(
        groups=[
            ProgressGroupResponse(
                source_kind=group.source_kind,
                source_id=group.source_id,
                label=group.label,
                completed=group.completed,
                total=group.total,
            )
            for group in groups
        ]
    )


# ---------------------------------------------------------------------------
# The session
# ---------------------------------------------------------------------------


@router.get("/sessions/active", response_model=SessionResponse | None)
async def get_active_session(runtime: RuntimeDep) -> SessionResponse | None:
    """Return the tutorial currently running, or null when none is.

    A session whose tutorial project has been deleted from outside the product
    is discarded here rather than reported, so the tutorial can be started again
    from the beginning instead of resuming into a directory that is gone.
    """
    return _session_response(runtime, _tutorials(runtime).active_session())


@router.post("/sessions", response_model=SessionResponse)
async def start_session(body: StartSessionRequest, runtime: RuntimeDep) -> SessionResponse:
    """Start a tutorial, resume it where it was left, or start it over.

    One tutorial runs at a time: starting a second while one is active is
    refused with a conflict, and the running one must be left first. Asking for
    a restart deletes the tutorial's project and its recorded position before
    creating them again.
    """
    tutorials = _tutorials(runtime)
    return _rendered(runtime, _acting(lambda: tutorials.start(body.key(), restart=body.restart)))


@router.post("/sessions/active/evaluate", response_model=SessionResponse)
async def evaluate_active_session(runtime: RuntimeDep) -> SessionResponse:
    """Re-check whether the current step is finished.

    Most steps finish on their own, when the product reports the change that
    completes them. This is for the rest: creating a data file the editor does
    not watch, for instance, changes nothing the product announces, so the step
    is re-checked on request instead of on a timer.
    """
    tutorials = _tutorials(runtime)
    return _rendered(runtime, _acting(tutorials.evaluate_active))


@router.post("/sessions/active/ui-event", response_model=SessionResponse)
async def report_ui_event(body: UiEventRequest, runtime: RuntimeDep) -> SessionResponse:
    """Report an interface action the user took, and re-check the step.

    Some steps ask for something that leaves no trace behind — enlarging the
    preview panel, opening a block's source. The interface reports those here so
    a step waiting on one can finish. The set of names is closed; an unknown one
    is refused rather than recorded, because a name nothing will ever report
    would leave the step waiting with no way to tell why.
    """
    if body.name not in UI_EVENT_NAMES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{body.name!r} is not a reportable interface event; "
                f"expected one of {', '.join(sorted(UI_EVENT_NAMES))}."
            ),
        )
    tutorials = _tutorials(runtime)
    return _rendered(runtime, _acting(lambda: tutorials.report_ui_event(body.name)))


@router.post("/sessions/active/continue", response_model=SessionResponse)
async def continue_active_session(runtime: RuntimeDep) -> SessionResponse:
    """Move on from a step that is only asking to be read."""
    tutorials = _tutorials(runtime)
    return _rendered(runtime, _acting(tutorials.continue_active))


@router.post("/sessions/active/leave", status_code=204)
async def leave_active_session(runtime: RuntimeDep) -> Response:
    """Leave the running tutorial without losing its progress.

    The tutorial's project and the step it reached are preserved, so starting it
    again resumes rather than restarts. Any scripted playback still running is
    ended, because it is a live terminal session and cannot be put away.
    """
    _tutorials(runtime).leave_active()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Tutorial data
# ---------------------------------------------------------------------------


@router.get("/data/clear-preview", response_model=ClearPreviewResponse)
async def preview_clear_data(runtime: RuntimeDep) -> ClearPreviewResponse:
    """List the directories that clearing tutorial data would delete.

    The confirmation names the directories rather than describing them, so the
    user agrees to something specific. Projects of the user's own are never in
    this list.
    """
    return ClearPreviewResponse(directories=[str(path) for path in _tutorials(runtime).clear_preview()])


@router.post("/data/clear", response_model=ClearDataResponse)
async def clear_data(body: ClearDataRequest, runtime: RuntimeDep) -> ClearDataResponse:
    """Delete every tutorial project, the tutorial library, and all progress.

    Reports what was actually deleted rather than what the confirmation listed:
    the two can differ if something disappeared in between, and reporting the
    preview would claim a deletion that did not happen.
    """
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Clearing tutorial data must be confirmed.")
    tutorials = _tutorials(runtime)
    promised = tutorials.clear_preview()
    _delete_registered_tutorial_projects(runtime)
    tutorials.clear_data()
    # The registry's own pruning pass, which drops the entries whose directories
    # have just gone. Called rather than reached into, so this route owns no
    # copy of what "stale" means.
    runtime.list_projects()
    return ClearDataResponse(deleted_directories=[str(path) for path in promised if not path.exists()])


def _delete_registered_tutorial_projects(runtime: ApiRuntime) -> None:
    """Delete every marked tutorial project through the runtime (FR-063, FR-073).

    Done before the directories are cleared, and not by clearing them, because
    only this path closes the lineage database of whichever tutorial project is
    currently open. A project of the user's own is never in this list: the
    marker is what selects it, and only ``create_project`` writes one.
    """
    from scistudio.tutorials.projects import tutorial_entries

    for entry in tutorial_entries(runtime.list_projects()):
        entry_id = getattr(entry, "id", None)
        if entry_id is None:
            continue
        try:
            runtime.delete_project(str(entry_id))
        except (OSError, ValueError, FileNotFoundError):
            # Whatever survives here is still a directory under the tutorial
            # parent, so the clearing pass below removes it anyway; the entry is
            # dropped by the pruning pass. One stuck project must not stop the
            # user being rid of the rest.
            logger.warning("Learning Center: could not delete tutorial project %s", entry_id, exc_info=True)


@router.get("/unlock", response_model=UnlockResponse)
async def get_unlock(runtime: RuntimeDep) -> UnlockResponse:
    """Whether the user should be offered help bringing in their own work.

    True once, after the tutorial that earns the offer is finished and before
    the offer has been shown. It gates nothing: the toolbar entry is available
    whatever this reports.
    """
    store = _tutorials(runtime).progress_store
    return UnlockResponse(work_import_offer_pending=store.work_import_offer_pending())


@router.post("/unlock/dismiss", status_code=204)
async def dismiss_unlock(runtime: RuntimeDep) -> Response:
    """Record that the offer has been shown, so it is not made again."""
    _tutorials(runtime).progress_store.dismiss_work_import_offer()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Tutorial assets
#
# Two routes per asset. A core tutorial's ``source_id`` is the empty string, so
# its URL has an empty middle segment, which a single-parameter path cannot
# match. The pair keeps the contract's path shape working for both instead of
# giving core tutorials a different URL scheme that every consumer would have to
# know about.
# ---------------------------------------------------------------------------


def _cover(runtime: ApiRuntime, key: TutorialKey) -> FileResponse:
    manifest = _find_tutorial(runtime, key).manifest
    cover = getattr(manifest, "cover", None)
    if cover is None:
        raise HTTPException(status_code=404, detail="This tutorial has no cover image.")
    resolved = _asset_file(manifest, str(cover), what="cover image")
    media_type, _ = mimetypes.guess_type(resolved.name)
    return FileResponse(resolved, media_type=media_type or "application/octet-stream")


def _page(runtime: ApiRuntime, key: TutorialKey, name: str) -> FileResponse:
    """Serve one reading page, and record that the page has been reached.

    Serving *is* reaching: a ``page_reached`` condition asks whether a reading
    step got as far as a given page, and the request for that page is the only
    moment anything in the product knows. Recording it here is the same
    arrangement as a reported interface event — the API layer owns the state and
    the evaluator reads it back like any other backend fact (FR-046).

    A page is named without its extension, because that is the name a
    ``page_reached`` condition carries: ``page: intro`` for
    ``assets/pages/intro.md``. The extension is accepted too, and what gets
    recorded is the name without it either way, so the two spellings cannot
    satisfy different conditions.
    """
    manifest = _find_tutorial(runtime, key).manifest
    resolved = _asset_file(manifest, _page_asset(manifest, name), what=f"page {name!r}")
    _wiring(runtime).recorded.record_page(Path(name).stem)
    media_type, _ = mimetypes.guess_type(resolved.name)
    return FileResponse(resolved, media_type=media_type or "text/plain")


def _page_asset(manifest: Any, name: str) -> str:
    """Return the tutorial-relative path of the page called *name*.

    Containment is never left to this function. It resolves the pages directory
    through the manifest first, so a name that escapes is refused there, and it
    only ever returns a path built from a filename it read back out of that
    directory — never one assembled from the request.
    """
    pages = f"{ASSETS_DIR_NAME}/{_PAGES_DIR_NAME}"
    direct = f"{pages}/{name}"
    try:
        directory = manifest.resolve_asset(pages)
        if manifest.resolve_asset(direct).is_file():
            return direct
    except ValueError:
        # A name the containment check refuses. Hand back the path it refused so
        # the caller raises the same "no such page" it would for a real miss,
        # rather than this function deciding the status code.
        return direct
    if not directory.is_dir():
        return direct
    matches = sorted(child for child in directory.iterdir() if child.is_file() and child.stem == name)
    return f"{pages}/{matches[0].name}" if matches else direct


@router.get("/{source_kind}/{source_id}/{tutorial_id}/cover")
async def get_cover(source_kind: str, source_id: str, tutorial_id: str, runtime: RuntimeDep) -> FileResponse:
    """Return a tutorial's cover image."""
    return _cover(runtime, TutorialKey(source_kind=source_kind, source_id=source_id, tutorial_id=tutorial_id))


@router.get("/{source_kind}//{tutorial_id}/cover")
async def get_core_cover(source_kind: str, tutorial_id: str, runtime: RuntimeDep) -> FileResponse:
    """Return the cover image of a tutorial whose source has no name."""
    return _cover(runtime, TutorialKey(source_kind=source_kind, source_id="", tutorial_id=tutorial_id))


@router.get("/{source_kind}/{source_id}/{tutorial_id}/pages/{name}")
async def get_page(source_kind: str, source_id: str, tutorial_id: str, name: str, runtime: RuntimeDep) -> FileResponse:
    """Return one of a tutorial's reading pages."""
    return _page(runtime, TutorialKey(source_kind=source_kind, source_id=source_id, tutorial_id=tutorial_id), name)


@router.get("/{source_kind}//{tutorial_id}/pages/{name}")
async def get_core_page(source_kind: str, tutorial_id: str, name: str, runtime: RuntimeDep) -> FileResponse:
    """Return one reading page of a tutorial whose source has no name."""
    return _page(runtime, TutorialKey(source_kind=source_kind, source_id="", tutorial_id=tutorial_id), name)
