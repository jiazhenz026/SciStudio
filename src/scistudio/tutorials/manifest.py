"""The tutorial manifest — its model, its published schema, and its validation.

ADR-053 Learning Center spec, FR-005 … FR-015, FR-020, FR-020a
(``docs/specs/adr-053-learning-center.md``).

A tutorial is a **directory containing a ``tutorial.yaml``**, and that manifest
is the only file required for the tutorial to be listed (FR-005). Assets live
under ``assets/`` with the reserved subdirectories ``data/``, ``code/``,
``panels/``, ``replay/`` and ``pages/`` (FR-006).

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
imports or executes (:data:`~scistudio.tutorials.actions.EXECUTED_PROJECT_DIRS`).
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
from typing import Any

import yaml

from scistudio.tutorials.actions import (
    EXECUTED_PROJECT_DIRS,
    Action,
    ActionValidationError,
    CopyAction,
    ReplayAction,
    destination_head,
    iter_asset_sources,
    iter_file_actions,
    parse_actions,
    resolve_contained_path,
)
from scistudio.tutorials.conditions import (
    Condition,
    ConditionValidationError,
    parse_condition,
)

__all__ = [
    "ASSETS_DIR_NAME",
    "EXECUTABLE_ASSET_DIRS",
    "RESERVED_ASSET_DIRS",
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
    "validate_tier_assets",
    "validate_tier_rules",
]


TUTORIAL_MANIFEST_FILENAME = "tutorial.yaml"
"""FR-005: the one file a tutorial directory must contain."""

ASSETS_DIR_NAME = "assets"

RESERVED_ASSET_DIRS: tuple[str, ...] = ("data", "code", "panels", "replay", "pages")
"""FR-006: data files, block/type/previewer/plot sources, built panel bundles,
scripted replay material, and reading content."""

EXECUTABLE_ASSET_DIRS: frozenset[str] = frozenset({"code", "panels", "replay"})
"""The reserved asset directories whose contents the product imports, executes,
or plays back. A user-level or project-level tutorial may not carry any of them
(FR-020a)."""

SUPPORTED_MANIFEST_VERSIONS: frozenset[int] = frozenset({1})
"""FR-007a. A manifest declaring a version outside this set is unavailable, not
malformed."""

SCHEMA_PATH = Path(__file__).resolve().parent / "schema" / "tutorial.schema.json"
"""FR-013: the published schema package authors write against."""


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
    say: str | None = None
    highlight: str | None = None
    route_to: str | None = None
    do: tuple[Action, ...] = ()
    done_when: Condition | None = None

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
        steps.append(
            TutorialStep(
                id=step_id,
                say=_optional_str(item.get("say")),
                highlight=_optional_str(item.get("highlight")),
                route_to=_optional_str(item.get("route_to")),
                do=_parse_actions_or_fail(item.get("do"), field_name=f"{field_name}.do", path=path),
                done_when=done_when,
            )
        )
    return tuple(steps)


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
    """
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


def validate_tier_rules(manifest: TutorialManifest) -> None:
    """Apply the tier rules judgeable from the declaration alone (FR-020, FR-020a).

    Rejects, for ``user`` and ``project``: a ``driver`` field, a ``replay``
    action, and a write or copy destination whose first segment names a
    directory the product imports or executes. Each rejection names the tier,
    the field, and the restriction.
    """
    tier = manifest.source_kind
    if manifest.driver is not None and not tier.allows_executable_content:
        raise ManifestValidationError(
            path=manifest.path,
            field_name="driver",
            reason=(
                f"a {tier.value}-level tutorial may not declare 'driver'; "
                "code-driven tutorials are accepted only from core and packages"
            ),
        )
    if tier.allows_executable_content:
        return
    for field_name, action in _all_actions(manifest):
        if isinstance(action, ReplayAction):
            raise ManifestValidationError(
                path=manifest.path,
                field_name=f"{field_name}.replay",
                reason=(
                    f"a {tier.value}-level tutorial may not declare a 'replay' action; "
                    "scripted replay material is accepted only from core and packages"
                ),
            )
        for file_action in iter_file_actions([action]):
            head = destination_head(file_action.destination)
            if head in EXECUTED_PROJECT_DIRS:
                raise ManifestValidationError(
                    path=manifest.path,
                    field_name=f"{field_name}.{file_action.kind}.destination",
                    reason=(
                        f"a {tier.value}-level tutorial may not write into {head!r}, "
                        "a project directory the product imports or executes; "
                        f"the restricted set is {', '.join(sorted(EXECUTED_PROJECT_DIRS))}"
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
    tier = manifest.source_kind
    if tier.allows_executable_content:
        return
    for name in sorted(EXECUTABLE_ASSET_DIRS):
        candidate = manifest.assets_dir / name
        if candidate.is_dir() and any(entry.is_file() for entry in candidate.rglob("*")):
            raise ManifestValidationError(
                path=manifest.path,
                field_name=f"{ASSETS_DIR_NAME}/{name}",
                reason=(
                    f"a {tier.value}-level tutorial may not carry assets under "
                    f"{ASSETS_DIR_NAME}/{name}/; the product imports, executes, or plays back "
                    f"the contents of {', '.join(sorted(EXECUTABLE_ASSET_DIRS))}"
                ),
            )
    for field_name, action in _all_actions(manifest):
        if isinstance(action, CopyAction):
            _reject_executed_landing(manifest, action, field_name=field_name)


def _reject_executed_landing(manifest: TutorialManifest, action: CopyAction, *, field_name: str) -> None:
    source = manifest.directory / action.source
    if not source.is_dir():
        return
    base = Path(action.destination)
    for entry in source.rglob("*"):
        if not entry.is_file():
            continue
        landing = base / entry.relative_to(source)
        head = destination_head(landing.as_posix())
        if head in EXECUTED_PROJECT_DIRS:
            raise ManifestValidationError(
                path=manifest.path,
                field_name=f"{field_name}.copy.source",
                reason=(
                    f"a {manifest.source_kind.value}-level tutorial may not copy "
                    f"{action.source!r} into {action.destination!r}: {landing.as_posix()!r} would land in "
                    f"{head!r}, a project directory the product imports or executes"
                ),
            )
