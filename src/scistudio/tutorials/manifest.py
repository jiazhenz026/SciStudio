"""The tutorial manifest — its model, its published schema, and its validation.

ADR-053 Learning Center spec, FR-005 … FR-015, FR-020, FR-020a
(``docs/specs/adr-053-learning-center.md``).

A tutorial is a **directory containing a ``tutorial.yaml``**, and that manifest
is the only file required for the tutorial to be listed (FR-005). Assets live
under ``assets/`` with the reserved subdirectories ``data/``, ``code/``,
``panels/``, ``replay/``, ``workflows/`` and ``pages/`` (FR-006).

Two failures that look alike and are not
----------------------------------------

:class:`ManifestValidationError` says *this manifest is wrong*.
:class:`UnsupportedManifestVersionError` says *this manifest was written for a
newer core*. FR-007a is explicit that the second is not a malformed manifest:
it is listed as unavailable naming the version it requires, on the same path as
an unmet requirement (FR-024). The two owe the user different messages, so they
are different types and discovery can tell them apart without parsing strings.

Why there is no tutorial-kind field
-----------------------------------

The presence of ``bootstrap`` is what decides whether a tutorial gets a project
(FR-009). The spec rejects a second classification because the step actions
already declare what each step does, and a ``kind`` could contradict them.

The Learning Center nevertheless has to list reading tutorials apart from
hands-on ones, and does it without such a field: :attr:`TutorialManifest.is_reading_only`
reads the answer off the steps' own ``done_when``. Anyone arriving here to add
``kind: reading`` should look at that property first — a derived answer cannot
disagree with the steps, and a declared one can.

Containment is checked while listing, not while writing
-------------------------------------------------------

Asset paths resolve inside the tutorial directory (FR-014) and write
destinations inside the tutorial project (FR-015), and both are rejected *at
validation* — "so a bad tutorial fails while being listed rather than while
writing files into a user's project". The primitives live in
:mod:`scistudio.tutorials.actions`; this module applies them.

Tier grading (FR-020, FR-020a)
------------------------------

``driver`` is accepted only for ``core`` and ``package``. Rejecting the field
alone would not make a tier incapable of carrying executable code, so the
grading also rejects, for ``user`` and ``project``: an asset under
``assets/code/``, ``assets/panels/`` or ``assets/replay/``; a ``replay``
action; and a write or copy destination resolving under a directory the product
imports, executes, or reads as configuration for something it executes
(:data:`~scistudio.tutorials.actions.EXECUTED_PROJECT_PATHS`).
Without all three, a project-level tutorial could drop a ``.py`` into
``blocks/`` through an ordinary write action and have it imported on the next
registry refresh. FR-020a records why this is deliberately a *different*
tradeoff from drop-in blocks, where ``{project}/blocks/*.py`` is executed with
sandboxing deferred to #1531: tutorial code is reached earlier and far more
often, because merely listing the catalogue touches it.

Boundaries
----------

This module imports :mod:`scistudio.tutorials.conditions` and
:mod:`scistudio.tutorials.actions` and nothing else from the package —
``manifest -> conditions`` is the one direction the boundary allows, never the
reverse (checklist §6.1.2). It never imports ``scistudio.api``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml

from scistudio.tutorials.actions import (
    EXECUTED_PROJECT_PATHS,
    Action,
    ActionValidationError,
    CopyAction,
    ReplayAction,
    executed_project_path_hit,
    iter_asset_sources,
    iter_file_actions,
    parse_actions,
    resolve_contained_path,
)
from scistudio.tutorials.conditions import (
    READING_TERMS,
    Condition,
    ConditionValidationError,
    parse_condition,
)

__all__ = [
    "ASSETS_DIR_NAME",
    "EXECUTABLE_ASSET_DIRS",
    "HIGHLIGHT_TARGETS",
    "PREFILL_TARGETS",
    "RESERVED_ASSET_DIRS",
    "ROUTE_TARGETS",
    "SCHEMA_PATH",
    "SUPPORTED_MANIFEST_VERSIONS",
    "TUTORIAL_MANIFEST_FILENAME",
    "ManifestValidationError",
    "TutorialBootstrap",
    "TutorialManifest",
    "TutorialManifestError",
    "TutorialRequirements",
    "TutorialSourceKind",
    "TutorialStep",
    "UnsupportedManifestVersionError",
    "load_manifest",
    "load_schema",
    "parse_manifest",
    "validate_against_schema",
    "validate_asset_containment",
    "validate_step_pages",
    "validate_tier_assets",
    "validate_tier_rules",
]


TUTORIAL_MANIFEST_FILENAME = "tutorial.yaml"
"""FR-005: the one file a tutorial directory must contain."""

ASSETS_DIR_NAME = "assets"

RESERVED_ASSET_DIRS: tuple[str, ...] = ("data", "code", "panels", "replay", "workflows", "pages")
"""FR-006: data files, block/type/previewer/plot sources, built panel bundles,
scripted replay material, workflow YAML written into the project, and reading
content."""

EXECUTABLE_ASSET_DIRS: frozenset[str] = frozenset({"code", "panels", "replay", "workflows"})
"""The reserved asset directories whose contents the product imports, executes,
plays back, or reads as configuration for something it executes. A user-level
or project-level tutorial may not carry any of them (FR-020a).

``workflows`` is here for the reason :data:`~scistudio.tutorials.actions.EXECUTED_PROJECT_PATHS`
lists the project directory of the same name (#2063): a workflow YAML names a
code block's ``script_path`` and ``cwd``, so it is configuration the product
acts on to execute, graded executable-adjacent rather than as data."""

SUPPORTED_MANIFEST_VERSIONS: frozenset[int] = frozenset({1})
"""FR-007a. A manifest declaring a version outside this set is unavailable, not
malformed."""

SCHEMA_PATH = Path(__file__).resolve().parent / "schema" / "tutorial.schema.json"
"""FR-013: the published schema package authors write against."""


ROUTE_TARGETS: frozenset[str] = frozenset(
    {
        "ai_chat",
        "terminal",
        "config",
        "logs",
        "plots",
        "history",
        "git",
        "canvas",
        "block_palette",
    }
)
"""The closed set of destinations a step's ``route_to`` may name (FR-011).

The first seven mirror the product's real bottom-panel tabs; ``canvas`` and
``block_palette`` are the two surfaces outside that strip a step can send a
user to.

**Manifests name the tab the way the product names it to the user, not the way
the code spells it.** Two of the seven differ from their internal keys: the
``BottomTab`` union in ``frontend/src/types/ui.ts`` is
``ai | terminal | config | logs | plots | lineage | git``, and
``frontend/src/components/BottomPanel.parts/TabBar.tsx`` labels ``ai`` as
"AI Chat" and ``lineage`` as "History" — the latter an owner-requested UI
rename that deliberately left every internal key alone. A tutorial manifest is
authored content that a person reads and writes, so it says ``ai_chat`` and
``history``. The frontend owns the ``ai_chat -> ai`` and ``history -> lineage``
mapping.

That mismatch is recorded here because it will otherwise read as a bug: the
next person to compare this set against ``BottomTab`` will find two names that
do not appear there, and this paragraph is the answer.
"""


@dataclass(frozen=True)
class HighlightSpec:
    """One accepted ``highlight`` target and the arguments that address it."""

    name: str
    points_at: str
    required: tuple[str, ...] = ()


HIGHLIGHT_SPECS: tuple[HighlightSpec, ...] = (
    # Surfaces. A whole panel is the right size only when the step is about the
    # panel itself; pointing at one of these to mean "the Load block, which is
    # somewhere in here" is the failure the entity targets below exist to fix.
    HighlightSpec(name="block_palette", points_at="the block palette as a whole"),
    HighlightSpec(name="canvas", points_at="the workflow canvas as a whole"),
    HighlightSpec(name="data_preview", points_at="the data preview surface"),
    HighlightSpec(name="config_panel", points_at="the selected block's settings panel"),
    # Singleton controls. Exactly one of each exists on screen, so a name is
    # already an address.
    HighlightSpec(name="run_button", points_at="the toolbar's Run button"),
    HighlightSpec(name="new_menu_button", points_at="the toolbar's New menu"),
    HighlightSpec(name="plots_new_button", points_at="the Plots tab's new-plot button"),
    HighlightSpec(name="history_restore_button", points_at="the Restore button on a run in History"),
    # Entities. These take an argument because the element they address is one
    # of many of its kind, and which one is the whole content of the guidance.
    HighlightSpec(name="palette_block", points_at="one block's entry in the palette", required=("block_type",)),
    HighlightSpec(name="node", points_at="one node on the canvas", required=("block_type",)),
    HighlightSpec(name="plot_card", points_at="one plot's card in the Plots tab", required=("plot_id",)),
)
"""The closed set of interface elements a step's ``highlight`` may name (FR-011).

Deliberately small, and deliberately not a guess at a general vocabulary for
the product's interface. Every member is something core tutorial 1 actually
needs: drag one named block out of the palette, configure one named node, press
Run, create a plot, restore from History.

**Why some targets take arguments.** A highlight is only useful if the reader
can tell what to act on, and half of core tutorial 1's steps are about *one*
element among many of its kind — the Load entry in a palette listing thirty
blocks, the Normalize node among four on the canvas. A target that can only
name the containing panel points at the haystack. The entity targets take the
argument that picks the needle, and the frontend annotates each candidate
element with both the target name and that argument's value.

The set grows by core change rather than by a manifest author inventing a name.
A highlight only does anything once the frontend annotates the element it
names, so a new member without a matching frontend annotation is a step whose
guidance is silently dropped — which is exactly the failure this closure exists
to stop.
"""


@dataclass(frozen=True)
class PrefillSpec:
    """One accepted ``prefill`` target and the values it seeds."""

    name: str
    seeds: str
    required: tuple[str, ...] = ()


PREFILL_SPECS: tuple[PrefillSpec, ...] = (
    PrefillSpec(
        name="new_custom_block",
        seeds="the New custom block dialog",
        required=("filename",),
    ),
    PrefillSpec(
        name="new_plot",
        seeds="the new-plot dialog",
        required=("name",),
    ),
    PrefillSpec(
        name="block_config",
        seeds="one field of a block's settings, for the named block type",
        required=("block_type", "key", "value"),
    ),
)
"""The closed set of dialogs a step's ``prefill`` may seed (FR-011b).

``prefill`` says what a dialog the reader is about to open should already be
holding when it opens. A step that asks for a block named
``normalize_fluorescence`` and then presents a dialog offering ``my_block``
makes the reader retype something the tutorial already decided; the step and
the dialog were saying different things, and only one of them was the product.

The mechanism is general — a step carries any number of prefills, each naming a
target and the values that seed it — while the vocabulary is closed and
core-owned, for the same reason :data:`HIGHLIGHT_SPECS` is: a prefill only does
anything once the frontend seeds the dialog it names, so a member without a
matching frontend consumer is a manifest line that silently does nothing. The
set grows by core change as tutorials need it, never by an author inventing a
name.

A prefill is a *default*, not a decision. Whatever it seeds stays editable, and
a reader who types something else is not fighting the tutorial: the step's
``done_when`` still judges the world rather than the dialog.

``block_config`` seeds a settings field rather than a dialog, and is therefore
the one target that touches the workflow. It fills a field the reader has left
empty, and never overwrites a value they have typed. A step using it must judge
something the *reader* did — the folder they browsed to, the block they wired —
and not the field it seeded, or the step judges the tutorial's own work.
"""

PREFILL_TARGETS: frozenset[str] = frozenset(spec.name for spec in PREFILL_SPECS)
"""The accepted ``prefill`` target names, derived from :data:`PREFILL_SPECS`."""

_PREFILL_SPECS_BY_NAME: Mapping[str, PrefillSpec] = MappingProxyType({spec.name: spec for spec in PREFILL_SPECS})


@dataclass(frozen=True)
class Prefill:
    """One dialog a step seeds, and the values it seeds it with (FR-011b)."""

    target: str
    args: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))

    def as_json(self) -> dict[str, Any]:
        """The wire shape: the target name and its arguments, flat."""
        return {"target": self.target, "args": dict(self.args)}


HIGHLIGHT_TARGETS: frozenset[str] = frozenset(spec.name for spec in HIGHLIGHT_SPECS)
"""The accepted ``highlight`` target names, derived from :data:`HIGHLIGHT_SPECS`.

Kept as a name so the frontend parity test has one thing to compare against.
"""

_HIGHLIGHT_SPECS_BY_NAME: Mapping[str, HighlightSpec] = MappingProxyType({spec.name: spec for spec in HIGHLIGHT_SPECS})


@dataclass(frozen=True)
class Highlight:
    """What a step points at, and which one of it (FR-011).

    ``args`` is empty for the surface and singleton targets, whose name is
    already an address. It carries the entity targets' required argument —
    ``block_type`` for ``palette_block`` and ``node``, ``plot_id`` for
    ``plot_card`` — which is what lets the frontend pick one element out of a
    list of like elements rather than lighting up their container.
    """

    target: str
    args: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))

    def as_json(self) -> dict[str, Any]:
        """The wire shape: the target name and its arguments, flat."""
        return {"target": self.target, "args": dict(self.args)}


class TutorialSourceKind(StrEnum):
    """Where a tutorial came from. Declared here because it is a validation input.

    Discovery imports it from this module rather than the other way round: the
    tier decides which manifests are legal (FR-020, FR-020a), so the tier has to
    be knowable before discovery exists.
    """

    CORE = "core"
    PACKAGE = "package"
    USER = "user"
    PROJECT = "project"

    @property
    def allows_executable_content(self) -> bool:
        """True for ``core`` and ``package`` — the tiers that may ship code.

        A package author has a signed, distributed artifact that passes the
        ADR-049 validator. A user-level or project-level manifest is written by
        hand or by an agent, so the format makes it structurally incapable of
        carrying executable code rather than relying on a review that never
        happens.
        """
        return self in (TutorialSourceKind.CORE, TutorialSourceKind.PACKAGE)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class TutorialManifestError(Exception):
    """Base for every manifest failure. Always names the file (FR-013)."""

    def __init__(self, message: str, *, path: Path) -> None:
        self.path = path
        super().__init__(message)


class ManifestValidationError(TutorialManifestError):
    """The manifest is wrong: names the file, the field, and the reason (FR-013)."""

    def __init__(self, *, path: Path, field_name: str, reason: str) -> None:
        self.field_name = field_name
        self.reason = reason
        super().__init__(f"{path}: {field_name or '<manifest>'}: {reason}", path=path)


class UnsupportedManifestVersionError(TutorialManifestError):
    """The manifest was written for a core this one is not (FR-007a).

    Not a subclass of :class:`ManifestValidationError`, and deliberately so: a
    manifest this core cannot read is listed as unavailable naming the version
    it requires, on the same path as an unmet requirement (FR-024), while a
    malformed one is listed with its validation message. Discovery has to tell
    them apart to say the right thing.
    """

    def __init__(self, *, path: Path, declared_version: int, supported_versions: frozenset[int]) -> None:
        self.declared_version = declared_version
        self.supported_versions = tuple(sorted(supported_versions))
        super().__init__(
            f"{path}: manifest_version {declared_version} requires a newer SciStudio; "
            f"this one reads manifest_version {', '.join(str(version) for version in self.supported_versions)}",
            path=path,
        )


# ---------------------------------------------------------------------------
# The model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TutorialRequirements:
    """FR-008's ``requires`` block, parsed but not evaluated.

    Discovery evaluates it, not this module: a tutorial whose requirements are
    unmet is still listed (FR-024), because a user cannot decide whether to
    install a package whose teaching material is invisible until after
    installing it.
    """

    scistudio: str | None = None
    agent: bool = False
    packages: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        return self.scistudio is None and not self.agent and not self.packages


@dataclass(frozen=True)
class TutorialBootstrap:
    """FR-009's ``bootstrap`` block. Its presence is what grants a project."""

    project_name: str | None = None
    do: tuple[Action, ...] = ()


@dataclass(frozen=True)
class TutorialStep:
    """One step of a manifest-driven tutorial (FR-011)."""

    id: str
    #: FR-011c — the short heading the step card shows.
    #:
    #: Without it every step of a tutorial is headed by the tutorial's own name,
    #: which is the one thing the reader already knows and which says nothing
    #: about where they are. Optional: a tutorial that does not title its steps
    #: falls back to its own title, which is what every existing manifest gets.
    title: str | None = None
    say: str | None = None
    highlight: Highlight | None = None
    route_to: str | None = None
    prefill: tuple[Prefill, ...] = ()
    do: tuple[Action, ...] = ()
    done_when: Condition | None = None
    #: FR-011 — the reading pages this step presents, named as files under
    #: ``assets/pages/`` the way a ``page_reached`` condition names them: with
    #: or without the extension, ``intro`` for ``assets/pages/intro.md``.
    #: Validated to exist at load (:func:`validate_step_pages`), because a
    #: reading step whose page is missing fails the reader mid-read otherwise —
    #: the same argument FR-014 makes about asset paths.
    pages: tuple[str, ...] = ()

    @property
    def awaiting_continue(self) -> bool:
        """FR-012: a step with no ``done_when`` advances on an explicit user continue.

        Exposed as state rather than inferred by each caller so the driver and
        the API can both say "awaiting continue" without re-deriving it — the
        session response carries this field verbatim (checklist §6.1.6).
        """
        return self.done_when is None


@dataclass(frozen=True)
class TutorialManifest:
    """A parsed, validated ``tutorial.yaml``."""

    manifest_version: int
    id: str
    title: str
    summary: str
    source_kind: TutorialSourceKind
    directory: Path
    path: Path
    cover: str | None = None
    order: int | None = None
    requires: TutorialRequirements = field(default_factory=TutorialRequirements)
    bootstrap: TutorialBootstrap | None = None
    steps: tuple[TutorialStep, ...] = ()
    driver: str | None = None

    @property
    def creates_project(self) -> bool:
        """FR-009: a tutorial declaring ``bootstrap`` gets a project; one omitting it does not."""
        return self.bootstrap is not None

    @property
    def is_driver_driven(self) -> bool:
        """FR-010: exactly one of ``steps`` and ``driver`` is set."""
        return self.driver is not None

    @property
    def is_reading_only(self) -> bool:
        """Whether this tutorial only ever asks the reader to read on.

        True when every step either waits on an explicit continue or waits on a
        term from :data:`~scistudio.tutorials.conditions.READING_TERMS`. A step
        that judges any product fact — a registered block, a succeeded run, a
        file on disk — makes the tutorial hands-on, however much prose it also
        carries.

        Derived rather than declared, for the reason "Why there is no
        tutorial-kind field" gives above: a manifest saying it is a reading
        tutorial could contradict its own steps, and this cannot. A
        driver-driven tutorial answers False because its steps are the driver's
        to produce and are not on disk to inspect.
        """
        if self.is_driver_driven or not self.steps:
            return False
        return all(step.done_when is None or step.done_when.terms() <= READING_TERMS for step in self.steps)

    @property
    def assets_dir(self) -> Path:
        return self.directory / ASSETS_DIR_NAME

    def step_by_id(self, step_id: str) -> TutorialStep | None:
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def resolve_asset(self, relative: str) -> Path:
        """Resolve a tutorial-directory-relative asset path, rejecting escapes (FR-014)."""
        return resolve_contained_path(self.directory, relative, field_name="asset")


# ---------------------------------------------------------------------------
# Schema validation (FR-013)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def load_schema() -> Mapping[str, Any]:
    """Return the published manifest schema.

    ``jsonschema`` is not a dependency of this project, so :func:`_check_node`
    below implements the keyword subset this document uses rather than pulling
    in a library for one file. The schema document remains the contract: it is
    what package authors write against, and it is the thing validation reads —
    not a description of validation written twice.
    """
    with SCHEMA_PATH.open(encoding="utf-8") as handle:
        loaded: Mapping[str, Any] = json.load(handle)
    return loaded


_TYPE_CHECKS: Mapping[str, Any] = {
    "object": lambda value: isinstance(value, Mapping),
    "array": lambda value: isinstance(value, Sequence) and not isinstance(value, (str, bytes)),
    "string": lambda value: isinstance(value, str),
    "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
    "number": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool),
    "boolean": lambda value: isinstance(value, bool),
    "null": lambda value: value is None,
}


def _resolve_ref(ref: str, root: Mapping[str, Any]) -> Mapping[str, Any]:
    node: Any = root
    for part in ref.lstrip("#/").split("/"):
        node = node[part]
    resolved: Mapping[str, Any] = node
    return resolved


def _fail(path: Path, field_name: str, reason: str) -> ManifestValidationError:
    return ManifestValidationError(path=path, field_name=field_name, reason=reason)


def _check_type(value: Any, node: Mapping[str, Any], field_name: str, path: Path) -> None:
    declared = node.get("type")
    if declared is None:
        return
    names = [declared] if isinstance(declared, str) else list(declared)
    if not any(_TYPE_CHECKS[name](value) for name in names):
        raise _fail(path, field_name, f"expected {' or '.join(names)}, got {type(value).__name__}")


def _check_scalar(value: Any, node: Mapping[str, Any], field_name: str, path: Path) -> None:
    if "enum" in node and value not in node["enum"]:
        raise _fail(path, field_name, f"expected one of {', '.join(str(item) for item in node['enum'])}")
    if isinstance(value, str):
        if len(value) < int(node.get("minLength", 0)):
            raise _fail(path, field_name, f"must be at least {node['minLength']} character(s)")
        pattern = node.get("pattern")
        if pattern is not None and not re.match(pattern, value):
            raise _fail(path, field_name, f"does not match {pattern}")
    is_plain_int = isinstance(value, int) and not isinstance(value, bool)
    if is_plain_int and "minimum" in node and value < int(node["minimum"]):
        raise _fail(path, field_name, f"must be >= {node['minimum']}")


def _check_object(value: Mapping[str, Any], node: Mapping[str, Any], field_name: str, path: Path, root: Any) -> None:
    for key in node.get("required", ()):
        if key not in value:
            raise _fail(path, field_name or "<manifest>", f"missing required field {key!r}")
    minimum = node.get("minProperties")
    maximum = node.get("maxProperties")
    if minimum is not None and len(value) < int(minimum):
        raise _fail(path, field_name, f"expected at least {minimum} key(s), got {len(value)}")
    if maximum is not None and len(value) > int(maximum):
        raise _fail(path, field_name, f"expected at most {maximum} key(s), got {len(value)}")
    properties: Mapping[str, Any] = node.get("properties", {})
    if node.get("additionalProperties") is False:
        unknown = set(value) - set(properties)
        if unknown:
            raise _fail(path, field_name or "<manifest>", f"unknown field(s): {', '.join(sorted(unknown))}")
    for key, sub_schema in properties.items():
        if key in value:
            child = f"{field_name}.{key}" if field_name else key
            _check_node(value[key], sub_schema, child, path, root)


def _check_array(value: Sequence[Any], node: Mapping[str, Any], field_name: str, path: Path, root: Any) -> None:
    if "minItems" in node and len(value) < int(node["minItems"]):
        raise _fail(path, field_name, f"expected at least {node['minItems']} item(s)")
    item_schema = node.get("items")
    if item_schema is None:
        return
    for index, item in enumerate(value):
        _check_node(item, item_schema, f"{field_name}[{index}]", path, root)


def _check_node(value: Any, node: Mapping[str, Any], field_name: str, path: Path, root: Any) -> None:
    if "$ref" in node:
        node = _resolve_ref(str(node["$ref"]), root)
    _check_type(value, node, field_name, path)
    _check_scalar(value, node, field_name, path)
    if isinstance(value, Mapping):
        _check_object(value, node, field_name, path, root)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        _check_array(value, node, field_name, path, root)


def validate_against_schema(data: Any, *, path: Path) -> None:
    """Validate ``data`` against the published schema, naming file, field, and reason."""
    schema = load_schema()
    _check_node(data, schema, "", path, schema)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _parse_requires(raw: Any) -> TutorialRequirements:
    if not raw:
        return TutorialRequirements()
    packages = tuple(str(item) for item in raw.get("packages", ()))
    scistudio = raw.get("scistudio")
    return TutorialRequirements(
        scistudio=None if scistudio is None else str(scistudio),
        agent=bool(raw.get("agent", False)),
        packages=packages,
    )


def _parse_bootstrap(raw: Any, *, path: Path) -> TutorialBootstrap | None:
    if raw is None:
        return None
    project_name = raw.get("project_name")
    do = _parse_actions_or_fail(raw.get("do"), field_name="bootstrap.do", path=path)
    return TutorialBootstrap(
        project_name=None if project_name is None else str(project_name),
        do=do,
    )


def _parse_actions_or_fail(raw: Any, *, field_name: str, path: Path) -> tuple[Action, ...]:
    try:
        return parse_actions(raw, field_name=field_name)
    except ActionValidationError as exc:
        raise ManifestValidationError(path=path, field_name=field_name, reason=str(exc)) from exc


def _parse_steps(raw: Any, *, path: Path) -> tuple[TutorialStep, ...]:
    steps: list[TutorialStep] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        field_name = f"steps[{index}]"
        step_id = str(item["id"])
        if step_id in seen:
            raise ManifestValidationError(
                path=path,
                field_name=f"{field_name}.id",
                reason=f"duplicate step id {step_id!r}; step ids must be unique within a tutorial",
            )
        seen.add(step_id)
        done_when_raw = item.get("done_when")
        try:
            done_when = None if done_when_raw is None else parse_condition(done_when_raw, field_name="done_when")
        except ConditionValidationError as exc:
            raise ManifestValidationError(path=path, field_name=f"{field_name}.done_when", reason=str(exc)) from exc
        highlight = _parse_highlight(item.get("highlight"), field_name=f"{field_name}.highlight", path=path)
        route_to = _optional_str(item.get("route_to"))
        _check_closed_value(route_to, ROUTE_TARGETS, field_name=f"{field_name}.route_to", path=path)
        steps.append(
            TutorialStep(
                id=step_id,
                title=_optional_str(item.get("title")),
                say=_optional_str(item.get("say")),
                highlight=highlight,
                route_to=route_to,
                prefill=_parse_prefill(item.get("prefill"), field_name=f"{field_name}.prefill", path=path),
                do=_parse_actions_or_fail(item.get("do"), field_name=f"{field_name}.do", path=path),
                done_when=done_when,
                pages=_parse_pages(item.get("pages"), field_name=f"{field_name}.pages", path=path),
            )
        )
    return tuple(steps)


def _parse_prefill(raw: Any, *, field_name: str, path: Path) -> tuple[Prefill, ...]:
    """Parse ``prefill``: a list of single-key mappings naming a dialog.

    The shape ``do`` already uses, for the same reason it uses it — a step may
    seed more than one dialog — rather than ``highlight``'s bare-or-single-key
    form, which exists because a step points at exactly one thing.
    """
    if raw is None:
        return ()
    if not isinstance(raw, Sequence) or isinstance(raw, str | bytes):
        raise ManifestValidationError(
            path=path,
            field_name=field_name,
            reason=f"prefill must be a list of single-key mappings, got {type(raw).__name__}",
        )

    prefills: list[Prefill] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        item_field = f"{field_name}[{index}]"
        if not isinstance(item, Mapping) or len(item) != 1:
            raise ManifestValidationError(
                path=path,
                field_name=item_field,
                reason="each prefill names exactly one target, as a single-key mapping",
            )
        ((target_raw, args_raw),) = item.items()
        target = str(target_raw)
        spec = _PREFILL_SPECS_BY_NAME.get(target)
        if spec is None:
            raise ManifestValidationError(
                path=path,
                field_name=item_field,
                reason=f"{target!r} is not accepted; the accepted values are {', '.join(sorted(PREFILL_TARGETS))}",
            )
        if target in seen:
            raise ManifestValidationError(
                path=path,
                field_name=item_field,
                reason=f"{target!r} is prefilled twice in one step; a dialog opens holding one set of values",
            )
        seen.add(target)
        if not isinstance(args_raw, Mapping):
            raise ManifestValidationError(
                path=path,
                field_name=f"{item_field}.{target}",
                reason=f"a prefill target's values must be a mapping, got {type(args_raw).__name__}",
            )
        args = {str(key): str(value) for key, value in args_raw.items()}
        missing = [name for name in spec.required if not args.get(name)]
        if missing:
            raise ManifestValidationError(
                path=path,
                field_name=f"{item_field}.{target}",
                reason=f"{target!r} seeds {spec.seeds} and needs {', '.join(missing)}",
            )
        unexpected = sorted(set(args) - set(spec.required))
        if unexpected:
            raise ManifestValidationError(
                path=path,
                field_name=f"{item_field}.{target}",
                reason=(
                    f"{target!r} takes {', '.join(spec.required) or 'no values'}; "
                    f"got unexpected {', '.join(unexpected)}"
                ),
            )
        prefills.append(Prefill(target=target, args=MappingProxyType(args)))
    return tuple(prefills)


def _parse_pages(raw: Any, *, field_name: str, path: Path) -> tuple[str, ...]:
    """Parse a step's ``pages``: an ordered list of page names.

    Names only here — whether each names a real file under ``assets/pages/``
    is :func:`validate_step_pages`'s question, asked once the directory is on
    disk, on the same two-phase arrangement asset containment uses.
    """
    if raw is None:
        return ()
    if not isinstance(raw, Sequence) or isinstance(raw, str | bytes):
        raise ManifestValidationError(
            path=path,
            field_name=field_name,
            reason=f"pages must be a list of page names, got {type(raw).__name__}",
        )
    pages: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, str) or not item:
            raise ManifestValidationError(
                path=path,
                field_name=f"{field_name}[{index}]",
                reason="a page is named by a non-empty string",
            )
        if item in seen:
            raise ManifestValidationError(
                path=path,
                field_name=f"{field_name}[{index}]",
                reason=f"page {item!r} is listed twice in one step",
            )
        seen.add(item)
        pages.append(item)
    return tuple(pages)


def _parse_highlight(raw: Any, *, field_name: str, path: Path) -> Highlight | None:
    """Parse ``highlight`` in either of its two written forms.

    A bare string for the targets whose name is already an address
    (``highlight: run_button``), and a single-key mapping for the ones that need
    to say *which* (``highlight: {palette_block: {block_type: load_data}}``).

    The mapping form is the shape ``done_when`` already uses for conditions, on
    purpose: a tutorial author who has written one ``done_when`` has learned the
    only nested syntax this format has, and a second spelling for the same idea
    would be a second thing to get wrong.
    """
    if raw is None:
        return None

    args_raw: Any = {}
    if isinstance(raw, str):
        target = raw
    elif isinstance(raw, Mapping):
        if len(raw) != 1:
            raise ManifestValidationError(
                path=path,
                field_name=field_name,
                reason=(
                    f"a highlight names exactly one target, got {len(raw)} "
                    f"({', '.join(sorted(str(key) for key in raw))})"
                ),
            )
        ((target_raw, args_raw),) = raw.items()
        target = str(target_raw)
        if args_raw is None:
            args_raw = {}
        if not isinstance(args_raw, Mapping):
            raise ManifestValidationError(
                path=path,
                field_name=f"{field_name}.{target}",
                reason=f"a highlight target's arguments must be a mapping, got {type(args_raw).__name__}",
            )
    else:
        raise ManifestValidationError(
            path=path,
            field_name=field_name,
            reason=f"a highlight must be a target name or a single-key mapping, got {type(raw).__name__}",
        )

    spec = _HIGHLIGHT_SPECS_BY_NAME.get(target)
    if spec is None:
        raise ManifestValidationError(
            path=path,
            field_name=field_name,
            reason=f"{target!r} is not accepted; the accepted values are {', '.join(sorted(HIGHLIGHT_TARGETS))}",
        )

    args = {str(key): str(value) for key, value in args_raw.items()}
    missing = [name for name in spec.required if not args.get(name)]
    if missing:
        raise ManifestValidationError(
            path=path,
            field_name=f"{field_name}.{target}",
            reason=(f"{target!r} points at {spec.points_at} and needs {', '.join(missing)} to say which one"),
        )
    unexpected = sorted(set(args) - set(spec.required))
    if unexpected:
        raise ManifestValidationError(
            path=path,
            field_name=f"{field_name}.{target}",
            reason=(
                f"{target!r} takes {', '.join(spec.required) or 'no arguments'}; got unexpected {', '.join(unexpected)}"
            ),
        )
    return Highlight(target=target, args=MappingProxyType(args))


def _check_closed_value(value: str | None, accepted: frozenset[str], *, field_name: str, path: Path) -> None:
    """Reject a step field naming something outside its core-owned set.

    Same argument FR-049 makes for the condition vocabulary, applied to the two
    step fields that address the interface: a free-form name is a typo that
    fails the *user* — the highlight never appears, the route never happens, and
    nothing says why — rather than failing the author while the tutorial is
    being listed.
    """
    if value is not None and value not in accepted:
        raise ManifestValidationError(
            path=path,
            field_name=field_name,
            reason=f"{value!r} is not accepted; the accepted values are {', '.join(sorted(accepted))}",
        )


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _reject_unsupported_version(declared_version: int, *, path: Path) -> None:
    """FR-007a: 'written for a newer core' is a different answer from 'malformed'."""
    if declared_version not in SUPPORTED_MANIFEST_VERSIONS:
        raise UnsupportedManifestVersionError(
            path=path,
            declared_version=declared_version,
            supported_versions=SUPPORTED_MANIFEST_VERSIONS,
        )


def _check_steps_xor_driver(data: Mapping[str, Any], *, path: Path) -> None:
    has_steps = "steps" in data
    has_driver = "driver" in data
    if has_steps and has_driver:
        raise ManifestValidationError(
            path=path,
            field_name="steps/driver",
            reason="a manifest declares exactly one of 'steps' and 'driver'; this one declares both",
        )
    if not has_steps and not has_driver:
        raise ManifestValidationError(
            path=path,
            field_name="steps/driver",
            reason="a manifest declares exactly one of 'steps' and 'driver'; this one declares neither",
        )


def parse_manifest(
    data: Any,
    *,
    directory: Path,
    source_kind: TutorialSourceKind,
    path: Path,
) -> TutorialManifest:
    """Validate and parse manifest data that has already been read from YAML.

    Applies, in order: the schema (FR-013), the supported-version check
    (FR-007a), the ``steps`` xor ``driver`` rule (FR-010), the step and action
    and condition parsers (FR-011, FR-049, FR-057), and the tier rules that can
    be judged from the declaration alone (FR-020, FR-020a). The tier rules that
    need the directory on disk are :func:`validate_tier_assets`, applied by
    :func:`load_manifest`.
    """
    if not isinstance(data, Mapping):
        raise ManifestValidationError(
            path=path,
            field_name="",
            reason=f"a manifest is a mapping, got {type(data).__name__}",
        )
    declared_version = data.get("manifest_version")
    if isinstance(declared_version, int) and not isinstance(declared_version, bool):
        _reject_unsupported_version(declared_version, path=path)
    validate_against_schema(data, path=path)
    _check_steps_xor_driver(data, path=path)

    cover = _optional_str(data.get("cover"))
    if cover is not None:
        try:
            resolve_contained_path(directory, cover, field_name="cover")
        except ActionValidationError as exc:
            raise ManifestValidationError(path=path, field_name="cover", reason=str(exc)) from exc

    order = data.get("order")
    manifest = TutorialManifest(
        manifest_version=int(data["manifest_version"]),
        id=str(data["id"]),
        title=str(data["title"]),
        summary=str(data["summary"]),
        source_kind=source_kind,
        directory=directory,
        path=path,
        cover=cover,
        order=None if order is None else int(order),
        requires=_parse_requires(data.get("requires")),
        bootstrap=_parse_bootstrap(data.get("bootstrap"), path=path),
        steps=_parse_steps(data.get("steps", ()), path=path),
        driver=_optional_str(data.get("driver")),
    )
    validate_tier_rules(manifest)
    return manifest


def load_manifest(directory: Path, *, source_kind: TutorialSourceKind) -> TutorialManifest:
    """Read, validate, and parse ``<directory>/tutorial.yaml``.

    FR-005: the manifest is the only file required. Everything else about the
    tutorial directory is optional, and a tutorial with no ``assets/`` tree is
    a legal tutorial.

    ``directory`` is the tutorial directory, not the manifest inside it. Being
    handed the manifest is a natural mistake, and joining the filename onto it
    produces ``.../tutorial.yaml/tutorial.yaml: cannot be read``, which reads
    like a missing file rather than like a wrong argument — so it is caught and
    named.
    """
    if directory.is_file():
        raise ManifestValidationError(
            path=directory,
            field_name="",
            reason=(
                f"is a file, but a tutorial is a directory containing {TUTORIAL_MANIFEST_FILENAME}; "
                f"pass {directory.parent} rather than the manifest inside it"
            ),
        )
    path = directory / TUTORIAL_MANIFEST_FILENAME
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ManifestValidationError(path=path, field_name="", reason=f"cannot be read: {exc}") from exc
    try:
        data = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise ManifestValidationError(path=path, field_name="", reason=f"is not valid YAML: {exc}") from exc
    manifest = parse_manifest(data, directory=directory, source_kind=source_kind, path=path)
    validate_asset_containment(manifest)
    validate_tier_assets(manifest)
    validate_step_pages(manifest)
    return manifest


# ---------------------------------------------------------------------------
# Containment and tier rules
# ---------------------------------------------------------------------------


def _all_actions(manifest: TutorialManifest) -> tuple[tuple[str, Action], ...]:
    collected: list[tuple[str, Action]] = []
    if manifest.bootstrap is not None:
        collected.extend(("bootstrap.do", action) for action in manifest.bootstrap.do)
    for index, step in enumerate(manifest.steps):
        collected.extend((f"steps[{index}].do", action) for action in step.do)
    return tuple(collected)


def validate_asset_containment(manifest: TutorialManifest) -> None:
    """Re-check every declared asset source against the real directory (FR-014).

    The parser already rejects ``..`` and absolute paths lexically. This pass
    runs once the directory is known and adds the symbolic-link check, so an
    asset path that points outside the tutorial through a link is rejected
    while the tutorial is being listed rather than while it is writing.
    """
    for field_name, action in _all_actions(manifest):
        for suffix, source in iter_asset_sources(action):
            full_field = f"{field_name}.{suffix}"
            try:
                resolve_contained_path(manifest.directory, source, field_name=full_field)
            except ActionValidationError as exc:
                raise ManifestValidationError(path=manifest.path, field_name=full_field, reason=str(exc)) from exc


_EXECUTED_PATH_REASON = "a project path the product imports, executes, or reads to configure something it executes"
"""Why a destination under :data:`~scistudio.tutorials.actions.EXECUTED_PROJECT_PATHS`
is refused. Named once because two of the tier rejections give it — one for a
destination that says the path and one for a copy that reaches it — and a reader
comparing the two messages is comparing this sentence."""


def _tier_rejection(manifest: TutorialManifest, *, field_name: str, may_not: str) -> ManifestValidationError:
    """Build a tier rejection, naming the tier the same way in every one.

    FR-020a is five separate restrictions — a ``driver`` field, a ``replay``
    action, a write into an executed project path, a copy landing in one, and a
    carried executable asset — and they are separate because they are judged at
    different times against different things. What they share is the sentence
    they open with: *a <tier>-level tutorial may not ...*. Composing it here is
    what keeps five messages agreeing on how they name the tier and the field,
    which is the part of them a reader compares when one fires.
    """
    return _fail(manifest.path, field_name, f"a {manifest.source_kind.value}-level tutorial may not {may_not}")


def validate_tier_rules(manifest: TutorialManifest) -> None:
    """Apply the tier rules judgeable from the declaration alone (FR-020, FR-020a).

    Rejects, for ``user`` and ``project``: a ``driver`` field, a ``replay``
    action, and a write or copy destination whose first segment names a
    directory the product imports or executes. Each rejection names the tier,
    the field, and the restriction.
    """
    if manifest.source_kind.allows_executable_content:
        # The driver check is inside the gate rather than before it: a core or
        # package tutorial may declare one, so there is nothing to reject.
        return
    if manifest.driver is not None:
        raise _tier_rejection(
            manifest,
            field_name="driver",
            may_not="declare 'driver'; code-driven tutorials are accepted only from core and packages",
        )
    for field_name, action in _all_actions(manifest):
        if isinstance(action, ReplayAction):
            raise _tier_rejection(
                manifest,
                field_name=f"{field_name}.replay",
                may_not="declare a 'replay' action; scripted replay material is accepted only from core and packages",
            )
        for file_action in iter_file_actions([action]):
            hit = executed_project_path_hit(file_action.destination)
            if hit is not None:
                raise _tier_rejection(
                    manifest,
                    field_name=f"{field_name}.{file_action.kind}.destination",
                    may_not=(
                        f"write into {hit!r}, {_EXECUTED_PATH_REASON}; the restricted set is "
                        f"{', '.join(sorted(EXECUTED_PROJECT_PATHS))}"
                    ),
                )


def validate_tier_assets(manifest: TutorialManifest) -> None:
    """Apply the tier rules that need the directory on disk (FR-020a).

    Two checks. A ``user``- or ``project``-level tutorial may not *carry* an
    asset under ``assets/code/``, ``assets/panels/`` or ``assets/replay/``. And
    a copy action whose source tree contains a path landing under an executed
    project directory is rejected as well, because copying a directory to the
    project root reaches ``blocks/`` just as directly as naming it.
    """
    if manifest.source_kind.allows_executable_content:
        return
    for name in sorted(EXECUTABLE_ASSET_DIRS):
        candidate = manifest.assets_dir / name
        if candidate.is_dir() and any(entry.is_file() for entry in candidate.rglob("*")):
            raise _tier_rejection(
                manifest,
                field_name=f"{ASSETS_DIR_NAME}/{name}",
                may_not=(
                    f"carry assets under {ASSETS_DIR_NAME}/{name}/; the product imports, executes, "
                    f"or plays back the contents of {', '.join(sorted(EXECUTABLE_ASSET_DIRS))}"
                ),
            )
    for field_name, action in _all_actions(manifest):
        if isinstance(action, CopyAction):
            _reject_executed_landing(manifest, action, field_name=field_name)


def validate_step_pages(manifest: TutorialManifest) -> None:
    """Every declared page names a file under ``assets/pages/`` (FR-011, FR-014).

    Checked at load rather than at read, for FR-014's reason: a reading step
    whose page is missing should fail the tutorial while it is being listed,
    not fail the reader on the page turn. A name is accepted with or without
    its extension — the same rule the pages route applies when serving one —
    and containment is enforced first, so ``../`` cannot reach outside the
    pages directory whichever spelling is used.
    """
    pages_dir = manifest.assets_dir / "pages"
    for index, step in enumerate(manifest.steps):
        for page in step.pages:
            field_name = f"steps[{index}].pages"
            try:
                direct = resolve_contained_path(pages_dir, page, field_name=field_name)
            except ActionValidationError as exc:
                raise ManifestValidationError(path=manifest.path, field_name=field_name, reason=str(exc)) from exc
            if direct.is_file():
                continue
            stem_matches = (
                [child for child in pages_dir.iterdir() if child.is_file() and child.stem == page]
                if pages_dir.is_dir()
                else []
            )
            if not stem_matches:
                raise ManifestValidationError(
                    path=manifest.path,
                    field_name=field_name,
                    reason=f"page {page!r} is not a file under {ASSETS_DIR_NAME}/pages/",
                )


def _reject_executed_landing(manifest: TutorialManifest, action: CopyAction, *, field_name: str) -> None:
    source = manifest.directory / action.source
    if not source.is_dir():
        return
    base = Path(action.destination)
    for entry in source.rglob("*"):
        if not entry.is_file():
            continue
        landing = base / entry.relative_to(source)
        hit = executed_project_path_hit(landing.as_posix())
        if hit is not None:
            raise _tier_rejection(
                manifest,
                field_name=f"{field_name}.copy.source",
                may_not=(
                    f"copy {action.source!r} into {action.destination!r}: "
                    f"{landing.as_posix()!r} would land in {hit!r}, {_EXECUTED_PATH_REASON}"
                ),
            )
