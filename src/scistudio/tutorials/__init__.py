"""The Learning Center tutorial runtime.

ADR-053 Learning Center spec (``docs/specs/adr-053-learning-center.md``).

A tutorial is a directory on disk holding a ``tutorial.yaml`` manifest and an
``assets/`` tree. Completion is judged on the backend against product truth
using a core-owned vocabulary, re-evaluated from the engine event bus rather
than by polling. Any step may write files into the tutorial project.

Module boundaries (checklist §6.1.2) — no module in this package imports
``scistudio.api``; the API route layer injects what the runtime needs, which
keeps ``api -> tutorials`` a one-way edge and keeps the package testable
without a FastAPI app.

* :mod:`~scistudio.tutorials.manifest` — manifest model, published schema,
  validation, tier rules. Imports ``conditions`` and ``actions``.
* :mod:`~scistudio.tutorials.conditions` — the completion vocabulary, its
  parser and evaluator, and the FR-050 event map. Imports neither sibling.
* :mod:`~scistudio.tutorials.actions` — step actions, path containment, and
  replay sequencing. Imports neither sibling.

* :mod:`~scistudio.tutorials.discovery` — the four sources, the catalogue, and
  the requirement checks. Imports ``manifest``, ``progress``, ``projects``.
* :mod:`~scistudio.tutorials.driver` — the driver protocol, core's
  ``ManifestDriver``, and package driver loading.
* :mod:`~scistudio.tutorials.session` — lifecycle, persistence, event
  subscription, and the one-at-a-time rule.
* :mod:`~scistudio.tutorials.projects` — tutorial project creation, marking,
  deletion, and the scoped library.
* :mod:`~scistudio.tutorials.progress` — progress storage, grouping, and the
  milestone unlock.
"""

from __future__ import annotations

from scistudio.tutorials.actions import (
    REPLAY_SURFACES,
    Action,
    ActionContext,
    ActionExecutionError,
    ActionValidationError,
    CopyAction,
    ReplayAction,
    ReplayDelivery,
    ReplaySegment,
    WriteAction,
    perform_step_entry,
)
from scistudio.tutorials.conditions import (
    EVENT_TERM_MAP,
    UI_EVENT_NAMES,
    VOCABULARY,
    Condition,
    ConditionValidationError,
    ExternalEventNames,
    ProductState,
    RunSummary,
    build_event_term_map,
    evaluate,
    parse_condition,
)
from scistudio.tutorials.discovery import (
    Catalogue,
    CatalogueEntry,
    CatalogueGroup,
    DiscoveredTutorial,
    DiscoveryEnvironment,
    DiscoveryResult,
    TutorialSource,
    TutorialState,
    build_catalogue,
    core_tutorials_dir,
    discover_tutorials,
)
from scistudio.tutorials.driver import (
    DriverContext,
    DriverContractError,
    DriverError,
    DriverLoadError,
    ManifestDriver,
    StepView,
    TutorialDriver,
    load_driver,
)
from scistudio.tutorials.manifest import (
    HIGHLIGHT_TARGETS,
    ROUTE_TARGETS,
    ManifestValidationError,
    TutorialBootstrap,
    TutorialManifest,
    TutorialManifestError,
    TutorialRequirements,
    TutorialSourceKind,
    TutorialStep,
    UnsupportedManifestVersionError,
    load_manifest,
    parse_manifest,
)
from scistudio.tutorials.progress import (
    CatalogueTotals,
    ProgressGroup,
    ProgressStore,
    work_import_milestone,
)
from scistudio.tutorials.projects import (
    TutorialKey,
    TutorialProjectPlan,
    clear_preview,
    clear_tutorial_data,
    delete_tutorial_project,
    find_tutorial_project,
    is_tutorial_entry,
    plan_tutorial_project,
    restart_preview,
    tutorial_key_of,
    tutorial_project_exists,
    tutorial_project_path,
)
from scistudio.tutorials.session import (
    AnotherSessionActiveError,
    NoActiveSessionError,
    ProjectProvisioner,
    ReplayHandle,
    ReplayView,
    SessionInvalidatedError,
    SessionRecord,
    SessionStatus,
    SessionStore,
    SessionView,
    TutorialRuntime,
    TutorialSessionError,
    TutorialUnavailableError,
)

__all__ = [
    "EVENT_TERM_MAP",
    "HIGHLIGHT_TARGETS",
    "REPLAY_SURFACES",
    "ROUTE_TARGETS",
    "UI_EVENT_NAMES",
    "VOCABULARY",
    "Action",
    "ActionContext",
    "ActionExecutionError",
    "ActionValidationError",
    "AnotherSessionActiveError",
    "Catalogue",
    "CatalogueEntry",
    "CatalogueGroup",
    "CatalogueTotals",
    "Condition",
    "ConditionValidationError",
    "CopyAction",
    "DiscoveredTutorial",
    "DiscoveryEnvironment",
    "DiscoveryResult",
    "DriverContext",
    "DriverContractError",
    "DriverError",
    "DriverLoadError",
    "ExternalEventNames",
    "ManifestDriver",
    "ManifestValidationError",
    "NoActiveSessionError",
    "ProductState",
    "ProgressGroup",
    "ProgressStore",
    "ProjectProvisioner",
    "ReplayAction",
    "ReplayDelivery",
    "ReplayHandle",
    "ReplaySegment",
    "ReplayView",
    "RunSummary",
    "SessionInvalidatedError",
    "SessionRecord",
    "SessionStatus",
    "SessionStore",
    "SessionView",
    "StepView",
    "TutorialBootstrap",
    "TutorialDriver",
    "TutorialKey",
    "TutorialManifest",
    "TutorialManifestError",
    "TutorialProjectPlan",
    "TutorialRequirements",
    "TutorialRuntime",
    "TutorialSessionError",
    "TutorialSource",
    "TutorialSourceKind",
    "TutorialState",
    "TutorialStep",
    "TutorialUnavailableError",
    "UnsupportedManifestVersionError",
    "WriteAction",
    "build_catalogue",
    "build_event_term_map",
    "clear_preview",
    "clear_tutorial_data",
    "core_tutorials_dir",
    "delete_tutorial_project",
    "discover_tutorials",
    "evaluate",
    "find_tutorial_project",
    "is_tutorial_entry",
    "load_driver",
    "load_manifest",
    "parse_condition",
    "parse_manifest",
    "perform_step_entry",
    "plan_tutorial_project",
    "restart_preview",
    "tutorial_key_of",
    "tutorial_project_exists",
    "tutorial_project_path",
    "work_import_milestone",
]
