"""The Learning Center tutorial runtime.

ADR-053 Learning Center spec (``docs/specs/adr-053-learning-center.md``).

A tutorial is a directory on disk holding a ``tutorial.yaml`` manifest and an
``assets/`` tree. Completion is judged on the backend against product truth
using a core-owned vocabulary, re-evaluated from the engine event bus rather
than by polling. Any step may write files into the tutorial project.

**This module is a canonical public root (ADR-052 §3).** Its ``__all__`` is the
tutorial *authoring* surface — what a package needs to ship a tutorial of its
own — and nothing else. Every other name in this package remains importable by
its deep path and carries no promise.

Two authoring paths, and only the second one is Python:

* **A manifest.** Ship a directory holding a ``tutorial.yaml`` written against
  the published schema (``scistudio/tutorials/schema/tutorial.schema.json``) and
  register its parent under the ``scistudio.tutorials`` entry-point group. Core's
  :class:`~scistudio.tutorials.driver.ManifestDriver` runs it. No import, no
  code, and the format versions itself through ``manifest_version``.
* **A driver.** Ship a class satisfying :class:`~scistudio.tutorials.driver.TutorialDriver`
  and name it from the manifest, which buys full control of the tutorial's logic
  (FR-040). This is the path that needs the symbols below.

What a driver may *not* do is as much of the contract as what it may. A driver
answers four questions and supplies no rendering: whatever it returns is
normalised through :meth:`~scistudio.tutorials.driver.StepView.of` at the
boundary, so it cannot introduce a display primitive, ship a frontend asset, or
address a surface the manifest format cannot address. Core owns what a step
looks like (FR-041). A driver is also handed a
:class:`~scistudio.tutorials.driver.DriverContext` rather than the session, so
it can read position and location but cannot advance, end, or start a session.

The whole surface is ``provisional`` at ``0.3.4``: the condition vocabulary and
the action set are still settling under open design work, so they may change in
a minor release with a changelog note.

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
    Action,
    CopyAction,
    ReplayAction,
    WriteAction,
)
from scistudio.tutorials.conditions import (
    VOCABULARY,
    Condition,
    ConditionValidationError,
    ProductState,
    RunSummary,
    evaluate,
    parse_condition,
)
from scistudio.tutorials.driver import (
    DeclaresConditions,
    DriverContext,
    StepView,
    TutorialDriver,
)
from scistudio.tutorials.projects import TutorialKey

__all__ = [
    "VOCABULARY",
    "Action",
    "Condition",
    "ConditionValidationError",
    "CopyAction",
    "DeclaresConditions",
    "DriverContext",
    "ProductState",
    "ReplayAction",
    "RunSummary",
    "StepView",
    "TutorialDriver",
    "TutorialKey",
    "WriteAction",
    "evaluate",
    "parse_condition",
]
