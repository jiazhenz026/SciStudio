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

Discovery, the driver interface, the session, tutorial projects, and progress
land in sibling modules and extend the exports below.
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
from scistudio.tutorials.manifest import (
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

__all__ = [
    "EVENT_TERM_MAP",
    "REPLAY_SURFACES",
    "VOCABULARY",
    "Action",
    "ActionContext",
    "ActionExecutionError",
    "ActionValidationError",
    "Condition",
    "ConditionValidationError",
    "CopyAction",
    "ExternalEventNames",
    "ManifestValidationError",
    "ProductState",
    "ReplayAction",
    "ReplayDelivery",
    "ReplaySegment",
    "RunSummary",
    "TutorialBootstrap",
    "TutorialManifest",
    "TutorialManifestError",
    "TutorialRequirements",
    "TutorialSourceKind",
    "TutorialStep",
    "UnsupportedManifestVersionError",
    "WriteAction",
    "build_event_term_map",
    "evaluate",
    "load_manifest",
    "parse_condition",
    "parse_manifest",
    "perform_step_entry",
]
