"""One answer to "how does a ``scistudio.*`` entry-point group get read?".

ADR-053 / ``docs/specs/adr-053-learning-center.md`` §3 "Entry-point symmetry"
(FR-025 to FR-035). Three registries read entry points and, before this module,
no two of them agreed:

============================  =====================  ======================  =====================
Concern                       ``scistudio.blocks``   ``scistudio.types``     ``scistudio.previewers``
============================  =====================  ======================  =====================
Enumeration failure           caught, empty group    **propagated**          caught, empty group
Load failure                  logged                 logged                  logged + diagnostic
Payload shape                 class or callable      callable -> sequence    callable -> sequence
``sys.path`` preparation      no                     no                      yes
============================  =====================  ======================  =====================

Adding a fourth group to three that disagree would make the disagreement the
convention, so this module states the contract once and all four groups use it.
Each registry keeps its own *registration* logic — what a block spec is, what a
``Meta`` must declare, which previewer id wins a duplicate — and keeps none of
its own enumeration, error containment, or diagnostic reporting (FR-025).

**The live group set (FR-034).** :data:`LIVE_ENTRY_POINT_GROUPS` is the one
place the set of live groups is written down. A fifth group is added by editing
this tuple, which is also what makes
``tests/packages/test_entry_point_symmetry.py`` cover it: that test parametrises
over this tuple rather than naming groups, so a group added without meeting the
contract below fails rather than diverging quietly.

**Error containment (FR-026, FR-027).** :func:`enumerate_group` never raises:
a failure to enumerate is logged, recorded as a diagnostic, and reported as an
empty group. :func:`load_entry_point` and :func:`resolve_payload` contain a
failure to the single entry point that caused it; the rest of the group still
loads. The group that used to propagate — ``scistudio.types`` — is the reason
this is stated as a rule rather than left to each registry: an enumeration
failure there reached the caller, which for a registry scan means the whole
process's type catalogue, not one plugin's contribution.

**Diagnostics (FR-028).** Every failure is recorded as an
:class:`EntryPointDiagnostic` in the caller-supplied sink as well as logged.
Logging alone is not enough: the observable outcome of a silent failure is a
package that installed successfully and contributed nothing, which a user
cannot tell apart from a package that had nothing to contribute. Each registry
turns the diagnostics into the ``diagnostics`` surface it exposes.

**The payload contract (FR-029).** A group that contributes objects declares a
*callable returning the contributed objects*. That is the single contract.

``scistudio.blocks`` additionally accepts a **bare class** — an entry point
whose value names a ``Block`` subclass directly rather than a factory. That
form is already published and installed packages depend on it, so it is kept as
a compatibility affordance, recorded here once rather than reproduced as a
per-registry convention, and passed as ``allow_bare_class=True`` by the block
registry alone. It MUST NOT be extended to any group added later: a new group
has no published users to keep working, so accepting two shapes there would buy
nothing and cost the contract.

**The metadata-only exemption (FR-029a).** ``scistudio.tutorials`` is exempt
from the callable contract and declares a *metadata-only* payload instead: the
entry point's value resolves to a directory of tutorial directories, and
:func:`resolve_entry_point_directory` resolves it from distribution metadata
without importing anything.

The exemption is required rather than convenient, and it is recorded beside
FR-029 rather than in the tutorial code so it reads as a second contract rather
than as one group ignoring the first. The callable contract is implemented by
importing the entry point's target; FR-018 forbids importing a package module
while listing the tutorial catalogue, because listing happens whenever the
Learning Center opens and must not execute package code. A tutorial group
satisfying both at once is impossible, so the payload rule is the one thing
that gives way. Everything else — enumeration, error containment (FR-026,
FR-027), diagnostics (FR-028), and import-root preparation (FR-030) — applies
to ``scistudio.tutorials`` unchanged.

**Import roots (FR-030).** :func:`prepared_plugin_import_roots` activates the
user-installed plugin import roots for the duration of a scan. This used to be
done by the previewer registry alone, which made the same installed package
resolve for previewers and fail for blocks: the plugin's ``site-packages``
carries its ``dist-info``, so with the roots off ``sys.path`` the canonical
entry-point path finds nothing (#1752). If the preparation is needed for one
group it is needed for all of them, so it is applied here rather than per
registry.

**The one permitted asymmetry (FR-032).** The previewer registry also scans the
``scistudio.blocks`` and ``scistudio.types`` groups for a conventional
``get_previewers()`` when a package declares no ``scistudio.previewers`` group.
That fallback stays where it lives, in
:mod:`scistudio.previewers.registry`, with its reason recorded there: it
compensates for installed metadata that predates the previewer group, which is
a history rather than a design. It is not a pattern to copy and is not extended
to ``scistudio.tutorials``.

This module lives under ``core/`` for the reasons ``core/dropins.py`` does: it
is imported by the block, type, and previewer registries and must sit where all
three reach it without a cycle, and the import-linter contract forbidding
``scistudio.core`` from importing ``blocks``/``engine``/``api``/``ai``/
``workflow`` is satisfied because it needs none of them. It deliberately knows
nothing about ``PackageInfo``, ``BlockSpec``, ``TypeSpec``, or
``PreviewerSpec``: interpreting a payload into registrations is each registry's
own job.
"""

from __future__ import annotations

import importlib.metadata
import logging
from collections.abc import Iterator, MutableSequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scistudio.desktop.paths import installed_package_import_roots, prepended_sys_paths

logger = logging.getLogger(__name__)

BLOCKS_ENTRY_POINT_GROUP = "scistudio.blocks"
TYPES_ENTRY_POINT_GROUP = "scistudio.types"
PREVIEWERS_ENTRY_POINT_GROUP = "scistudio.previewers"
TUTORIALS_ENTRY_POINT_GROUP = "scistudio.tutorials"

#: Every live ``scistudio.*`` entry-point group (FR-034).
#:
#: The single place the set is written down. ``scistudio.adapters`` and
#: ``scistudio.runners`` were removed and are not members; see ``pyproject.toml``
#: for each removal note.
#:
#: TODO(#2059): ``docs/architecture/ARCHITECTURE.md`` §12.4 still lists the
#:   removed ``scistudio.runners`` group and does not list ``scistudio.tutorials``,
#:   so a package author reading it is told to use a group that does not exist.
#:   Out of scope per ADR-053 Learning Center dispatch: that document is gated by
#:   ``architecture_doc_guard`` and needs owner approval this session did not have.
#:   Followup: https://github.com/jiazhenz026/SciStudio/issues/2059
LIVE_ENTRY_POINT_GROUPS: tuple[str, ...] = (
    BLOCKS_ENTRY_POINT_GROUP,
    TYPES_ENTRY_POINT_GROUP,
    PREVIEWERS_ENTRY_POINT_GROUP,
    TUTORIALS_ENTRY_POINT_GROUP,
)

#: Groups whose entry point value may name a class directly (FR-029).
#:
#: One member, and it stays one member. See the module docstring for why the
#: bare-class form is kept for ``scistudio.blocks`` and why it is not extended.
BARE_CLASS_GROUPS: frozenset[str] = frozenset({BLOCKS_ENTRY_POINT_GROUP})

#: Groups exempt from the callable payload contract (FR-029a).
#:
#: Resolved through :func:`resolve_entry_point_directory` from distribution
#: metadata, never by importing the value's module.
METADATA_ONLY_GROUPS: frozenset[str] = frozenset({TUTORIALS_ENTRY_POINT_GROUP})

STAGE_ENUMERATE = "enumerate"
STAGE_LOAD = "load"
STAGE_INVOKE = "invoke"
STAGE_REGISTER = "register"


@dataclass(frozen=True)
class EntryPointDiagnostic:
    """One thing that went wrong while reading an entry-point group (FR-028).

    Attributes:
        group: The ``scistudio.*`` group being read.
        entry_point: The entry point's name, or ``""`` when the failure is
            enumeration of the group itself and no single entry point is at
            fault.
        stage: One of :data:`STAGE_ENUMERATE`, :data:`STAGE_LOAD`,
            :data:`STAGE_INVOKE`, :data:`STAGE_REGISTER`.
        message: A short human-readable cause.
    """

    group: str
    entry_point: str
    stage: str
    message: str

    def __str__(self) -> str:
        """Render as the one-line string the registries' surfaces carry.

        The registries expose ``list[str]`` because the previewer registry
        already did and other code reads that shape; this keeps all three
        equally surfaceable without changing it.
        """
        if self.entry_point:
            return f"{self.group}: entry point '{self.entry_point}' {self.stage} failed: {self.message}"
        return f"{self.group}: {self.stage} failed: {self.message}"


DiagnosticSink = MutableSequence[EntryPointDiagnostic]


def _record(
    diagnostics: DiagnosticSink | None,
    group: str,
    entry_point: str,
    stage: str,
    message: str,
) -> None:
    if diagnostics is None:
        return
    diagnostics.append(EntryPointDiagnostic(group=group, entry_point=entry_point, stage=stage, message=message))


def _describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__


def entry_point_name(ep: Any) -> str:
    """Return an entry point's name, tolerating stand-ins without one."""
    name = getattr(ep, "name", "")
    return name if isinstance(name, str) else ""


def entry_point_module(ep: Any) -> str:
    """Return the module an entry point's value names, without importing it.

    ``module:attr``, ``module``, and ``module:attr [extra]`` all yield
    ``module``. Used by :func:`resolve_entry_point_directory` and by registries
    that attribute a registration to the distribution that declared it.
    """
    module = getattr(ep, "module", None)
    if isinstance(module, str) and module:
        return module
    value = getattr(ep, "value", None)
    if not isinstance(value, str):
        return ""
    return value.split(":", 1)[0].split("[", 1)[0].strip()


def enumerate_group(
    group: str,
    *,
    diagnostics: DiagnosticSink | None = None,
) -> tuple[importlib.metadata.EntryPoint, ...]:
    """Return every entry point declared for *group* (FR-026).

    Never raises. A failure to read installed metadata is logged, recorded as a
    diagnostic, and reported as an empty group, because one unreadable
    ``dist-info`` must not take down a registry scan.

    The result is re-selected through ``.select(group=...)`` when the object
    returned exposes it. Passing ``group=`` already narrows the real
    ``importlib.metadata`` result, so the extra select is a no-op there; it
    matters for the mapping-shaped and stand-in results that callers inject,
    which is the shape the block registry's own compatibility shim used to
    handle privately.
    """
    try:
        raw: Any = importlib.metadata.entry_points(group=group)
        selected = raw.select(group=group) if hasattr(raw, "select") else raw
        return tuple(selected)
    except Exception as exc:
        logger.warning("Failed to enumerate '%s' entry points", group, exc_info=True)
        _record(diagnostics, group, "", STAGE_ENUMERATE, _describe(exc))
        return ()


def load_entry_point(
    ep: Any,
    group: str,
    *,
    diagnostics: DiagnosticSink | None = None,
) -> object | None:
    """Load one entry point, containing its failure to itself (FR-027).

    Returns the loaded object, or ``None`` when loading failed — in which case
    a diagnostic has been recorded and the caller should move to the next entry
    point rather than reporting the failure again.

    Not valid for :data:`METADATA_ONLY_GROUPS`: loading imports the value's
    module, which FR-018 forbids while listing the tutorial catalogue. Use
    :func:`resolve_entry_point_directory` for those groups.
    """
    name = entry_point_name(ep)
    try:
        loaded: object = ep.load()
        return loaded
    except Exception as exc:
        logger.warning("Failed to load entry_point '%s' from group '%s'", name, group, exc_info=True)
        _record(diagnostics, group, name, STAGE_LOAD, _describe(exc))
        return None


def resolve_payload(
    loaded: object,
    *,
    group: str,
    entry_point: str,
    allow_bare_class: bool,
    diagnostics: DiagnosticSink | None = None,
) -> object | None:
    """Turn a loaded entry point into the objects it contributes (FR-029).

    The contract is one callable returning the contributed objects, so *loaded*
    is invoked and its return value handed back untouched. What that value is
    allowed to contain — a list of block classes, a ``(PackageInfo, list)``
    pair, a list of previewer specs — is each registry's own business and is
    deliberately not decided here.

    ``allow_bare_class=True`` accepts a class as the payload itself instead of
    invoking it. Classes are callable, so a bare class would otherwise be
    instantiated, which is neither what the publisher meant nor free of side
    effects. Only ``scistudio.blocks`` passes it; the module docstring records
    why, and why it is not extended.

    Returns ``None`` when no payload could be resolved, having recorded a
    diagnostic. ``None`` returned by the callable itself is treated the same
    way: a group member that contributes nothing at all is a fault worth
    surfacing, not a quiet success.
    """
    if allow_bare_class and isinstance(loaded, type):
        return loaded

    if not callable(loaded):
        message = f"expected a callable payload, got {type(loaded).__name__}"
        logger.warning(
            "Failed to process entry_point '%s' from group '%s': %s",
            entry_point,
            group,
            message,
        )
        _record(diagnostics, group, entry_point, STAGE_INVOKE, message)
        return None

    try:
        payload: object = loaded()
    except Exception as exc:
        logger.warning(
            "Failed to process entry_point '%s' from group '%s'",
            entry_point,
            group,
            exc_info=True,
        )
        _record(diagnostics, group, entry_point, STAGE_INVOKE, _describe(exc))
        return None

    if payload is None:
        message = "callable returned None"
        logger.warning(
            "Failed to process entry_point '%s' from group '%s': %s",
            entry_point,
            group,
            message,
        )
        _record(diagnostics, group, entry_point, STAGE_INVOKE, message)
        return None

    return payload


def plugin_import_roots() -> tuple[Path, ...]:
    """Return the user-installed plugin import roots (FR-030).

    Never raises: a discovery scan must still run when the desktop package
    directories cannot be read.
    """
    try:
        return tuple(installed_package_import_roots())
    except Exception:  # pragma: no cover - defensive; never fail discovery
        logger.debug("Failed to resolve installed plugin import roots", exc_info=True)
        return ()


@contextmanager
def prepared_plugin_import_roots() -> Iterator[None]:
    """Activate the plugin import roots for the duration of a scan (FR-030).

    Wrap every entry-point scan in this, not only the previewer one. A plugin's
    ``site-packages`` carries the ``dist-info`` that makes its entry points
    visible at all, so a group scanned without the roots active reports the
    package as absent rather than as broken.
    """
    with prepended_sys_paths(plugin_import_roots()):
        yield


def resolve_entry_point_directory(
    ep: Any,
    *,
    diagnostics: DiagnosticSink | None = None,
) -> Path | None:
    """Resolve an entry point's value to a directory, without importing it.

    FR-029a. The metadata-only payload: the value names a package whose
    directory holds the contributed content, and the directory is found through
    the declaring distribution's own metadata — ``EntryPoint.dist`` plus
    ``Distribution.locate_file`` and ``Distribution.files``.

    This function must not call ``EntryPoint.load()``,
    ``importlib.import_module``, or ``importlib.util.find_spec``. The first two
    import the target; ``find_spec`` imports the target's *parent* packages in
    order to ask them, so it is no safer. FR-018 forbids importing a package
    module while listing the tutorial catalogue, which happens every time the
    Learning Center opens.

    Returns ``None``, with a diagnostic recorded, when the value cannot be
    resolved from metadata alone.
    """
    group = getattr(ep, "group", "") or TUTORIALS_ENTRY_POINT_GROUP
    name = entry_point_name(ep)
    module = entry_point_module(ep)

    if not module:
        _record(diagnostics, group, name, STAGE_LOAD, "entry point declares no module value")
        return None

    dist = getattr(ep, "dist", None)
    if dist is None:
        _record(
            diagnostics,
            group,
            name,
            STAGE_LOAD,
            f"no distribution metadata for '{module}'; cannot resolve a directory without importing",
        )
        return None

    parts = tuple(module.split("."))
    try:
        directory = _locate_module_directory(dist, parts)
    except Exception as exc:
        _record(diagnostics, group, name, STAGE_LOAD, _describe(exc))
        return None

    if directory is None:
        _record(
            diagnostics,
            group,
            name,
            STAGE_LOAD,
            f"'{module}' is not a directory in the files of distribution '{_distribution_name(dist)}'",
        )
        return None
    return directory


def _locate_module_directory(dist: Any, parts: tuple[str, ...]) -> Path | None:
    """Return the on-disk directory for the dotted *parts* inside *dist*."""
    direct = dist.locate_file("/".join(parts))
    if direct is not None:
        candidate = Path(str(direct))
        if candidate.is_dir():
            return candidate

    files = getattr(dist, "files", None) or ()
    depth = len(parts)
    for recorded in files:
        recorded_parts = tuple(recorded.parts)
        if len(recorded_parts) <= depth or recorded_parts[:depth] != parts:
            continue
        located = dist.locate_file(recorded)
        if located is None:
            continue
        # ``recorded`` sits ``len(recorded_parts) - depth`` levels below the
        # module directory, so walking up that many parents lands on it.
        candidate = Path(str(located)).parents[len(recorded_parts) - depth - 1]
        if candidate.is_dir():
            return candidate
    return None


def _distribution_name(dist: Any) -> str:
    name = getattr(dist, "name", None)
    if isinstance(name, str) and name:
        return name
    metadata: Any = getattr(dist, "metadata", None)
    value = metadata.get("Name") if metadata is not None and hasattr(metadata, "get") else None
    return value if isinstance(value, str) else "<unknown>"


__all__ = [
    "BARE_CLASS_GROUPS",
    "BLOCKS_ENTRY_POINT_GROUP",
    "LIVE_ENTRY_POINT_GROUPS",
    "METADATA_ONLY_GROUPS",
    "PREVIEWERS_ENTRY_POINT_GROUP",
    "STAGE_ENUMERATE",
    "STAGE_INVOKE",
    "STAGE_LOAD",
    "STAGE_REGISTER",
    "TUTORIALS_ENTRY_POINT_GROUP",
    "TYPES_ENTRY_POINT_GROUP",
    "DiagnosticSink",
    "EntryPointDiagnostic",
    "entry_point_module",
    "entry_point_name",
    "enumerate_group",
    "load_entry_point",
    "plugin_import_roots",
    "prepared_plugin_import_roots",
    "resolve_entry_point_directory",
    "resolve_payload",
]
