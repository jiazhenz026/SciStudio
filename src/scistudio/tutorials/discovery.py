"""Four-source tutorial discovery, and the catalogue the Learning Center lists.

ADR-053 Learning Center spec, FR-016 … FR-024 and FR-029a
(``docs/specs/adr-053-learning-center.md``).

Four sources, and no fifth (FR-016): a directory inside the core distribution,
packages through the ``scistudio.tutorials`` entry-point group, the user
directory ``~/.scistudio/tutorials``, and the open project's ``tutorials/``.
The two local tiers are resolved through
:func:`scistudio.core.dropins.tutorial_scan_dirs`, which is the same tier
definition blocks and types use, so package install, package uninstall, branch
switch, and the working-tree rewrites that refresh the registries reach the
tutorial catalogue by the path they already travel rather than a fourth one
(FR-031).

**Listing imports nothing (FR-018).** Titles, summaries, covers, order, and
requirements come from manifests alone. A package tutorial's directory is
resolved from distribution metadata by
:func:`scistudio.core.entry_points.resolve_entry_point_directory`, which never
calls ``EntryPoint.load()``, ``importlib.import_module``, or
``importlib.util.find_spec``. This module contains no other way to reach a
package's files. The guarantee is asserted with a ``sys.meta_path`` hook in
``tests/tutorials/test_discovery_no_import.py`` rather than by reading the
source, because the failure it guards against is a refactor reintroducing an
import, not a particular spelling.

**Nothing that goes wrong empties a group (FR-022).** Every manifest is read
inside its own attempt. A file that fails schema validation, a file written for
a newer core, a directory whose id collides with a sibling's, and a package
whose entry point cannot be resolved each cost exactly their own entry. The
three failures owe the user *different* sentences, which is why they are three
paths rather than one ``except``:

* a malformed manifest raises :class:`ManifestValidationError` and is listed
  with its validation message — this tutorial is broken;
* a manifest declaring a ``manifest_version`` this core does not read raises
  :class:`UnsupportedManifestVersionError` and is listed naming the version it
  needs (FR-007a) — this tutorial needs a newer SciStudio;
* an unmet ``requires`` is not a failure at all: the tutorial is listed, marked
  unavailable, and says which requirement is unmet (FR-024), because a user
  cannot decide whether to install a package whose teaching material is
  invisible until after installing it.

**Identity is the pair (source, id) (FR-019).** Two packages may both ship
``intro``. Two tutorials in *one* source may not: a duplicate id makes
:class:`~scistudio.tutorials.projects.TutorialKey` ambiguous, so both entries
are listed as unavailable naming both directories (FR-023) rather than one of
them silently winning.

This module may not import :mod:`scistudio.tutorials.session` or
``scistudio.api`` (checklist §6.1.2). Everything it cannot read for itself —
the installed distribution set, whether an agent provider is available, whether
git is available — goes through :class:`DiscoveryEnvironment`, which may be
handed the answers or probe for them lazily on first use. Lazily, because none
of the three is free and a tutorial that declares no ``requires`` asks none of
them: listing a catalogue of such tutorials costs a directory walk and nothing
else.
"""

from __future__ import annotations

import importlib.metadata
import logging
import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from scistudio.core.dropins import (
    project_tutorials_dir,
    tutorial_scan_dirs,
    user_tutorials_dir,
)
from scistudio.core.entry_points import (
    STAGE_REGISTER,
    TUTORIALS_ENTRY_POINT_GROUP,
    DiagnosticSink,
    EntryPointDiagnostic,
    entry_point_name,
    enumerate_group,
    prepared_plugin_import_roots,
    resolve_entry_point_directory,
)
from scistudio.tutorials.manifest import (
    TUTORIAL_MANIFEST_FILENAME,
    ManifestValidationError,
    TutorialManifest,
    TutorialSourceKind,
    UnsupportedManifestVersionError,
    load_manifest,
)
from scistudio.tutorials.progress import CatalogueTotals, ProgressStore
from scistudio.tutorials.projects import TutorialKey, tutorial_project_exists, tutorial_project_path

logger = logging.getLogger(__name__)

__all__ = [
    "CORE_SOURCE_LABEL",
    "CORE_TUTORIALS_DIR_NAME",
    "GIT_TERMS",
    "PROJECT_SOURCE_ID",
    "USER_SOURCE_ID",
    "Catalogue",
    "CatalogueEntry",
    "CatalogueGroup",
    "DiscoveredTutorial",
    "DiscoveryEnvironment",
    "DiscoveryResult",
    "TutorialSource",
    "TutorialState",
    "agent_provider_available",
    "build_catalogue",
    "core_tutorials_dir",
    "core_version",
    "discover_tutorials",
    "git_available",
    "installed_distribution_names",
    "normalize_distribution_name",
    "unmet_requirement",
]

#: The directory inside the core distribution holding the shipped tutorials.
#:
#: Scanned as a parent of tutorial directories, exactly like a package's
#: entry-point directory and the two local tiers, so a core tutorial is added by
#: adding a directory rather than by naming an id anywhere in this module.
#: ``pyproject.toml`` ships ``tutorials/core/**/*`` as package data because the
#: tree is deliberately not an importable package (FR-020a keeps tutorial
#: material off every import path).
CORE_TUTORIALS_DIR_NAME = "core"

#: The label the core group carries in the Learning Center (FR-084).
CORE_SOURCE_LABEL = "SciStudio"

#: ``source_id`` for the two local tiers, spelled as the HTTP contract spells
#: them (checklist §6.1.6) and as
#: :class:`~scistudio.tutorials.projects.TutorialKey` stores them, so one value
#: travels from discovery through the project marker to the progress record.
USER_SOURCE_ID = "user"
PROJECT_SOURCE_ID = "project"

_SOURCE_ORDER: Mapping[TutorialSourceKind, int] = {
    TutorialSourceKind.CORE: 0,
    TutorialSourceKind.PACKAGE: 1,
    TutorialSourceKind.USER: 2,
    TutorialSourceKind.PROJECT: 3,
}

#: The vocabulary terms that read git state.
#:
#: A tutorial using one of them is listed but not startable when no git binary
#: can be found, which is the degraded mode ADR-039 §3.4 already defines for
#: runs rather than a second one invented here.
GIT_TERMS: frozenset[str] = frozenset({"git_branch_exists", "git_current_branch"})


class TutorialState(StrEnum):
    """A catalogue entry's state (FR-085, checklist §6.1.6)."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    UNAVAILABLE = "unavailable"


def core_tutorials_dir() -> Path:
    """Return the directory the core distribution's tutorials live in (FR-016)."""
    return Path(__file__).resolve().parent / CORE_TUTORIALS_DIR_NAME


# ---------------------------------------------------------------------------
# The environment requirement evaluation reads (FR-008, FR-024)
# ---------------------------------------------------------------------------


def normalize_distribution_name(name: str) -> str:
    """Return *name* in the PEP 503 normalized form distributions compare in."""
    return re.sub(r"[-_.]+", "-", name).strip().lower()


def core_version() -> str:
    """Return the running core's version, for a ``requires.scistudio`` check."""
    from scistudio.version import __version__

    return __version__


def installed_distribution_names() -> frozenset[str]:
    """Return every installed distribution's normalized name.

    Read under :func:`prepared_plugin_import_roots` for the reason every
    entry-point scan is (FR-030): a desktop-installed plugin's ``site-packages``
    carries the ``dist-info`` that makes it visible at all, so a ``requires``
    check run without the roots active would report an installed package as
    missing and mark its own tutorials unavailable.

    Never raises: unreadable metadata costs a requirement check, not the
    catalogue.
    """
    names: set[str] = set()
    try:
        with prepared_plugin_import_roots():
            for dist in importlib.metadata.distributions():
                raw = _distribution_name(dist)
                if raw:
                    names.add(normalize_distribution_name(raw))
    except Exception:  # pragma: no cover - defensive; never fail discovery
        logger.debug("Learning Center: failed to enumerate installed distributions", exc_info=True)
    return frozenset(names)


def agent_provider_available() -> bool:
    """Return whether any AI agent provider resolves to an installed binary.

    ``requires.agent`` asks whether the tutorial's AI material can run at all,
    and the product's own answer to that is the provider registry's binary
    resolution — the same question the AI block asks before a run. Reached
    lazily and defensively so a discovery scan still completes when the agent
    layer is unavailable, in which case the answer is "no agent", which lists
    the tutorial rather than hiding it (FR-024).
    """
    try:
        from scistudio.ai.agent.providers_registry import agent_descriptors, resolve_binary

        return any(resolve_binary(descriptor) is not None for descriptor in agent_descriptors())
    except Exception:  # pragma: no cover - defensive; never fail discovery
        logger.debug("Learning Center: failed to probe agent provider availability", exc_info=True)
        return False


def git_available() -> bool:
    """Return whether a git binary can be located (ADR-039 §3.4 degraded mode)."""
    try:
        from scistudio.core.versioning.git_binary import GitBinary

        GitBinary.locate()
    except Exception:
        return False
    return True


@dataclass(frozen=True)
class DiscoveryEnvironment:
    """What a ``requires`` block is judged against (FR-008, FR-024).

    Every field may be *stated*, in which case that is the answer, or left
    ``None``, in which case it is probed on first use and remembered for the
    rest of this object's life. Stating it is how a test lists a catalogue
    against a named environment instead of against whatever is installed on the
    machine running it.

    The probes are lazy rather than eager because they are not free and are
    usually not needed. Enumerating installed distributions walks every
    ``dist-info`` on the path, resolving an agent searches the filesystem for
    provider binaries, and locating git runs ``git --version``. A tutorial
    declaring no ``requires`` and no git condition — which is most of them —
    asks none of those questions, so opening the Learning Center costs a
    directory walk and nothing else. A tutorial that does ask pays once per
    discovery pass rather than once per tutorial.
    """

    scistudio_version: str | None = None
    installed_distributions: frozenset[str] | None = None
    agent_available: bool | None = None
    git_available: bool | None = None
    _probed: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    def _answer(self, name: str, stated: Any, probe: Any) -> Any:
        if stated is not None:
            return stated
        if name not in self._probed:
            self._probed[name] = probe()
        return self._probed[name]

    def version(self) -> str:
        """The running core's version."""
        return str(self._answer("version", self.scistudio_version, core_version))

    def distributions(self) -> frozenset[str]:
        """Every installed distribution, by normalized name."""
        answer: frozenset[str] = self._answer(
            "distributions", self.installed_distributions, installed_distribution_names
        )
        return answer

    def has_agent(self) -> bool:
        """Whether an AI agent provider is available on this machine."""
        return bool(self._answer("agent", self.agent_available, agent_provider_available))

    def has_git(self) -> bool:
        """Whether a git binary can be located (ADR-039 §3.4)."""
        return bool(self._answer("git", self.git_available, git_available))

    def has_distribution(self, name: str) -> bool:
        """Return whether *name* is installed, comparing normalized names."""
        return normalize_distribution_name(name) in self.distributions()


def unmet_requirement(manifest: TutorialManifest, environment: DiscoveryEnvironment) -> str | None:
    """Return why *manifest* cannot be started, or ``None`` when it can.

    Three predicates, in the order a user can act on them: an installed package
    is one install away, a core upgrade is further, and an agent is a machine
    setup task. All three are evaluated — none is skipped as unknowable — and
    the git check that follows is not part of ``requires`` at all but of the
    conditions the tutorial declares, which is why it is last: a tutorial
    blocked on a missing package should say so rather than mentioning git.
    """
    requires = manifest.requires
    for name in requires.packages:
        if not environment.has_distribution(name):
            return f"needs the package '{name}', which is not installed"
    if requires.scistudio is not None:
        unmet = _unmet_version(requires.scistudio, environment.version())
        if unmet is not None:
            return unmet
    if requires.agent and not environment.has_agent():
        return "needs an AI agent, and no agent provider is available on this machine"
    if _uses_git_terms(manifest) and not environment.has_git():
        return "needs version control, and no git binary is available on this machine"
    return None


def _unmet_version(specifier: str, installed: str) -> str | None:
    """Return why *installed* fails *specifier*, or ``None``."""
    from packaging.specifiers import InvalidSpecifier, SpecifierSet
    from packaging.version import InvalidVersion, Version

    try:
        wanted = SpecifierSet(specifier)
    except InvalidSpecifier:
        return f"declares an unreadable SciStudio requirement '{specifier}'"
    try:
        current = Version(installed)
    except InvalidVersion:  # pragma: no cover - a dev tree with an odd version string
        return None
    # ``prereleases=True`` rather than the PEP 440 default. That default exists
    # for dependency resolution, where silently pulling an alpha into someone's
    # environment is the hazard. Here the question is the opposite one — is the
    # SciStudio the user is already running new enough — and refusing to answer
    # it "yes" for an alpha makes every release-candidate build report its own
    # tutorials as needing an upgrade. SciStudio ships pre-release versions as a
    # matter of course (this tree is 0.3.3a0), so the default would have made
    # ``requires.scistudio`` unusable rather than merely strict.
    if wanted.contains(current, prereleases=True):
        return None
    return f"needs SciStudio {specifier}, and this is {installed}"


def _uses_git_terms(manifest: TutorialManifest) -> bool:
    """Return whether any declared condition reads git state.

    Answerable for a manifest-driven tutorial and not for a driver-driven one,
    whose conditions live in code this must not import while listing (FR-018).
    A driver-driven tutorial therefore stays startable with git absent and
    fails, if it fails, inside its own session — which is contained to it
    (FR-044) rather than being a reason to import a package to list a
    catalogue.
    """
    return any(step.done_when is not None and (step.done_when.terms() & GIT_TERMS) for step in manifest.steps)


# ---------------------------------------------------------------------------
# Sources and the tutorials found in them
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TutorialSource:
    """Where a tutorial came from, and how its group is labelled (FR-084)."""

    kind: TutorialSourceKind
    id: str
    label: str
    directory: Path

    @property
    def sort_key(self) -> tuple[int, str]:
        """Core first, then packages by name, then the two local tiers (FR-084)."""
        return (_SOURCE_ORDER[self.kind], self.id)


@dataclass(frozen=True)
class DiscoveredTutorial:
    """One tutorial found on disk, listed whether or not it can be started.

    ``manifest`` is ``None`` only when the manifest could not be read at all,
    in which case ``unavailable_reason`` carries the message that says so. Every
    other field is filled from the manifest, because FR-018 forbids any other
    source for them.
    """

    source: TutorialSource
    id: str
    title: str
    summary: str
    directory: Path
    manifest: TutorialManifest | None = None
    cover: str | None = None
    order: int | None = None
    unavailable_reason: str | None = None

    @property
    def key(self) -> TutorialKey:
        """Return this tutorial's identity, the pair (source, id) (FR-019)."""
        return TutorialKey(source_kind=str(self.source.kind), source_id=self.source.id, tutorial_id=self.id)

    @property
    def is_startable(self) -> bool:
        """Return whether a session may be started for this tutorial."""
        return self.unavailable_reason is None and self.manifest is not None

    @property
    def entry_sort_key(self) -> tuple[int, int, str, str]:
        """Order within a group: declared ``order`` first, then title (FR-007)."""
        return (0 if self.order is not None else 1, self.order or 0, self.title.lower(), self.id)


@dataclass(frozen=True)
class DiscoveryResult:
    """Everything one discovery pass found, before progress is applied."""

    tutorials: tuple[DiscoveredTutorial, ...] = ()
    sources: tuple[TutorialSource, ...] = ()
    diagnostics: tuple[EntryPointDiagnostic, ...] = ()

    @property
    def diagnostic_messages(self) -> tuple[str, ...]:
        """The diagnostics as the one-line strings every registry surface carries (FR-028)."""
        return tuple(str(diagnostic) for diagnostic in self.diagnostics)

    def find(self, key: TutorialKey) -> DiscoveredTutorial | None:
        """Return the tutorial *key* names, or ``None`` when nothing ships it."""
        for tutorial in self.tutorials:
            if tutorial.key == key:
                return tutorial
        return None

    def in_source(self, source: TutorialSource) -> tuple[DiscoveredTutorial, ...]:
        """Return *source*'s tutorials in display order."""
        found = [tutorial for tutorial in self.tutorials if tutorial.source == source]
        return tuple(sorted(found, key=lambda tutorial: tutorial.entry_sort_key))

    def totals(self) -> tuple[CatalogueTotals, ...]:
        """Return each source's contribution, for :meth:`ProgressStore.groups` (FR-076)."""
        return tuple(
            CatalogueTotals(
                source_kind=str(source.kind),
                source_id=source.id,
                tutorial_ids=frozenset(tutorial.id for tutorial in self.in_source(source)),
            )
            for source in self.sources
        )


# ---------------------------------------------------------------------------
# The scan (FR-016 … FR-023)
# ---------------------------------------------------------------------------


def discover_tutorials(
    *,
    project_dir: str | Path | None = None,
    environment: DiscoveryEnvironment | None = None,
    diagnostics: DiagnosticSink | None = None,
) -> DiscoveryResult:
    """Scan all four sources and return everything found (FR-016).

    Imports no package module (FR-018). Never raises: the failure of one
    manifest, one directory, or one entry point costs that entry alone
    (FR-022).
    """
    env = environment or DiscoveryEnvironment()
    sink: list[EntryPointDiagnostic] = []
    found: list[DiscoveredTutorial] = []
    sources: list[TutorialSource] = []

    for source in _sources(project_dir=project_dir, diagnostics=sink):
        entries = _scan_source(source, env)
        if not entries:
            continue
        sources.append(source)
        found.extend(entries)

    if diagnostics is not None:
        # The caller's sink is extended rather than replaced, so a route
        # collecting diagnostics from several scans keeps all of them.
        diagnostics.extend(sink)

    return DiscoveryResult(
        tutorials=tuple(found),
        sources=tuple(sorted(sources, key=lambda source: source.sort_key)),
        diagnostics=tuple(sink),
    )


def _sources(*, project_dir: str | Path | None, diagnostics: DiagnosticSink) -> Iterator[TutorialSource]:
    """Yield every source to scan, core first (FR-016, FR-084)."""
    yield TutorialSource(
        kind=TutorialSourceKind.CORE,
        id="",
        label=CORE_SOURCE_LABEL,
        directory=core_tutorials_dir(),
    )
    yield from _package_sources(diagnostics=diagnostics)

    # The two local tiers come from the one tier definition blocks and types
    # use (FR-031), rather than from a second answer written here.
    scan_dirs = set(tutorial_scan_dirs(project_dir))
    user_dir = user_tutorials_dir()
    if user_dir in scan_dirs:
        yield TutorialSource(
            kind=TutorialSourceKind.USER,
            id=USER_SOURCE_ID,
            label="My tutorials",
            directory=user_dir,
        )
    if project_dir is not None:
        project_tier = project_tutorials_dir(project_dir)
        if project_tier in scan_dirs:
            yield TutorialSource(
                kind=TutorialSourceKind.PROJECT,
                id=PROJECT_SOURCE_ID,
                label="This project",
                directory=project_tier,
            )


def _package_sources(*, diagnostics: DiagnosticSink) -> Iterator[TutorialSource]:
    """Yield one source per resolvable ``scistudio.tutorials`` entry point (FR-017).

    Enumeration, error containment, diagnostics, and import-root preparation all
    come from the shared helper (FR-025 … FR-030). The one thing that differs
    from the other three groups is the payload: FR-029a's metadata-only
    resolution, which reaches a directory without importing the module its value
    names (FR-018).
    """
    with prepared_plugin_import_roots():
        entry_points = enumerate_group(TUTORIALS_ENTRY_POINT_GROUP, diagnostics=diagnostics)
        for entry_point in entry_points:
            directory = resolve_entry_point_directory(entry_point, diagnostics=diagnostics)
            if directory is None:
                continue
            name = _distribution_name(getattr(entry_point, "dist", None)) or entry_point_name(entry_point)
            if not _holds_a_tutorial(directory):
                # FR-028: a package that installed and contributed nothing must
                # be distinguishable from one that had nothing to contribute.
                diagnostics.append(
                    EntryPointDiagnostic(
                        group=TUTORIALS_ENTRY_POINT_GROUP,
                        entry_point=entry_point_name(entry_point),
                        stage=STAGE_REGISTER,
                        message=f"'{directory}' holds no tutorial directory",
                    )
                )
                continue
            yield TutorialSource(
                kind=TutorialSourceKind.PACKAGE,
                id=normalize_distribution_name(name),
                label=name,
                directory=directory,
            )


def _holds_a_tutorial(directory: Path) -> bool:
    """Return whether *directory* is a parent of at least one tutorial directory."""
    return any(True for _ in _tutorial_directories(directory))


def _tutorial_directories(parent: Path) -> Iterator[Path]:
    """Yield every subdirectory of *parent* holding a manifest, in name order.

    A missing parent is not an error: three of the four sources are optional
    directories that exist only once something is put in them.
    """
    try:
        children = sorted(parent.iterdir())
    except OSError:
        return
    for child in children:
        try:
            if (child / TUTORIAL_MANIFEST_FILENAME).is_file():
                yield child
        except OSError:  # pragma: no cover - unreadable child; skip it
            continue


def _scan_source(source: TutorialSource, environment: DiscoveryEnvironment) -> tuple[DiscoveredTutorial, ...]:
    """Return every tutorial in *source*, listed whether or not it works (FR-022)."""
    entries = [_read_tutorial(source, directory, environment) for directory in _tutorial_directories(source.directory)]
    return _reject_duplicate_ids(tuple(entries))


def _read_tutorial(
    source: TutorialSource,
    directory: Path,
    environment: DiscoveryEnvironment,
) -> DiscoveredTutorial:
    """Read one tutorial directory into a listable entry.

    The three outcomes FR-007a and FR-024 require to reach the user as different
    sentences are three branches here: written for a newer core, malformed, and
    requirements unmet.
    """
    try:
        manifest = load_manifest(directory, source_kind=source.kind)
    except UnsupportedManifestVersionError as exc:
        # FR-007a: "this needs a newer SciStudio", not "this is broken".
        return _unreadable(source, directory, reason=str(exc))
    except ManifestValidationError as exc:
        # FR-013 / FR-022: this one tutorial is broken; its siblings are not.
        return _unreadable(source, directory, reason=str(exc))
    except Exception as exc:  # pragma: no cover - defensive; never empty a group
        logger.warning("Learning Center: unreadable tutorial at %s", directory, exc_info=True)
        return _unreadable(source, directory, reason=f"{type(exc).__name__}: {exc}")

    return DiscoveredTutorial(
        source=source,
        id=manifest.id,
        title=manifest.title,
        summary=manifest.summary,
        directory=directory,
        manifest=manifest,
        cover=manifest.cover,
        order=manifest.order,
        unavailable_reason=unmet_requirement(manifest, environment),
    )


def _unreadable(source: TutorialSource, directory: Path, *, reason: str) -> DiscoveredTutorial:
    """Return the entry a tutorial whose manifest could not be read is listed as.

    Its id is the directory name, because the manifest that would have carried
    one is the thing that could not be read. That keeps the entry addressable —
    a user can be told which directory to fix — without inventing an identity
    the tutorial does not claim.
    """
    return DiscoveredTutorial(
        source=source,
        id=directory.name,
        title=directory.name,
        summary="",
        directory=directory,
        manifest=None,
        unavailable_reason=reason,
    )


def _reject_duplicate_ids(entries: tuple[DiscoveredTutorial, ...]) -> tuple[DiscoveredTutorial, ...]:
    """Mark every member of a colliding id group unavailable, naming both paths (FR-023).

    Both rather than the second: identity is the pair (source, id), so a
    collision makes *neither* addressable — the session key, the progress
    record, and the tutorial project path would all be ambiguous. Picking a
    winner would make which one the user gets depend on directory iteration
    order, and would silently discard the other.
    """
    by_id: dict[str, list[DiscoveredTutorial]] = {}
    for entry in entries:
        by_id.setdefault(entry.id, []).append(entry)

    resolved: list[DiscoveredTutorial] = []
    for entry in entries:
        colliding = by_id[entry.id]
        if len(colliding) == 1:
            resolved.append(entry)
            continue
        others = ", ".join(str(other.directory) for other in colliding if other is not entry)
        resolved.append(
            DiscoveredTutorial(
                source=entry.source,
                id=entry.id,
                title=entry.title,
                summary=entry.summary,
                directory=entry.directory,
                manifest=None,
                cover=entry.cover,
                order=entry.order,
                unavailable_reason=(
                    f"shares the id '{entry.id}' with {others}; ids are unique within one source, "
                    f"so neither {entry.directory} nor {others} can be started"
                ),
            )
        )
    return tuple(resolved)


def _distribution_name(dist: Any) -> str:
    """Return a distribution's declared name, or ``""``."""
    if dist is None:
        return ""
    name = getattr(dist, "name", None)
    if isinstance(name, str) and name:
        return name
    metadata: Any = getattr(dist, "metadata", None)
    value = metadata.get("Name") if metadata is not None and hasattr(metadata, "get") else None
    return value if isinstance(value, str) else ""


# ---------------------------------------------------------------------------
# The catalogue (FR-076, FR-084, FR-085)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CatalogueEntry:
    """One row of the Learning Center, as checklist §6.1.6 renders it.

    ``cover`` is the manifest's declared filename rather than a URL: the route
    layer owns the URL space, and this package may not import it. The route
    resolves the file through
    :meth:`~scistudio.tutorials.manifest.TutorialManifest.resolve_asset`, which
    is what keeps the cover inside the tutorial directory (FR-014).
    """

    source_kind: str
    source_id: str
    id: str
    title: str
    summary: str
    cover: str | None
    order: int | None
    state: TutorialState
    unavailable_reason: str | None
    project_directory: Path | None
    directory: Path

    @property
    def key(self) -> TutorialKey:
        return TutorialKey(source_kind=self.source_kind, source_id=self.source_id, tutorial_id=self.id)


@dataclass(frozen=True)
class CatalogueGroup:
    """One source's group, with its own counts and no aggregate (FR-076)."""

    source_kind: str
    source_id: str
    label: str
    completed: int
    total: int
    tutorials: tuple[CatalogueEntry, ...]


@dataclass(frozen=True)
class Catalogue:
    """The whole listing: groups in display order, plus what went wrong (FR-028)."""

    groups: tuple[CatalogueGroup, ...] = ()
    diagnostics: tuple[str, ...] = ()

    def entry(self, key: TutorialKey) -> CatalogueEntry | None:
        """Return the row *key* names, or ``None``."""
        for group in self.groups:
            for entry in group.tutorials:
                if entry.key == key:
                    return entry
        return None


def build_catalogue(
    result: DiscoveryResult,
    *,
    progress: ProgressStore,
    in_progress: Iterable[TutorialKey] = (),
) -> Catalogue:
    """Turn a discovery pass into the grouped catalogue the Learning Center lists.

    Groups keep :meth:`DiscoveryResult.sources`' order — core first (FR-084) —
    and each carries only its own completed and total counts. No aggregate
    across groups is computed anywhere in this function, because FR-076 forbids
    reporting one and the cheapest way to keep that true is never to have the
    number.
    """
    completed = progress.completed_keys()
    started = frozenset(in_progress)
    groups = progress.groups(result.totals())
    by_group = {(group.source_kind, group.source_id): group for group in groups}

    rendered: list[CatalogueGroup] = []
    for source in result.sources:
        counts = by_group[(str(source.kind), source.id)]
        entries = tuple(_entry(tutorial, completed=completed, started=started) for tutorial in result.in_source(source))
        rendered.append(
            CatalogueGroup(
                source_kind=str(source.kind),
                source_id=source.id,
                label=source.label,
                completed=counts.completed,
                total=counts.total,
                tutorials=entries,
            )
        )
    return Catalogue(groups=tuple(rendered), diagnostics=result.diagnostic_messages)


def _entry(
    tutorial: DiscoveredTutorial,
    *,
    completed: frozenset[TutorialKey],
    started: frozenset[TutorialKey],
) -> CatalogueEntry:
    key = tutorial.key
    project = tutorial_project_path(key)
    return CatalogueEntry(
        source_kind=key.source_kind,
        source_id=key.source_id,
        id=tutorial.id,
        title=tutorial.title,
        summary=tutorial.summary,
        cover=tutorial.cover,
        order=tutorial.order,
        state=_state(tutorial, completed=completed, started=started),
        unavailable_reason=tutorial.unavailable_reason,
        project_directory=project if tutorial_project_exists(project) else None,
        directory=tutorial.directory,
    )


def _state(
    tutorial: DiscoveredTutorial,
    *,
    completed: frozenset[TutorialKey],
    started: frozenset[TutorialKey],
) -> TutorialState:
    """Return an entry's state (FR-085).

    Unavailability wins over everything, including completion: a tutorial whose
    package was uninstalled after it was finished cannot be reopened, and
    showing it as merely complete would offer a restart that cannot run. The
    recorded completion still counts toward its group, which is
    :meth:`ProgressStore.groups`' business rather than this function's.
    """
    if not tutorial.is_startable:
        return TutorialState.UNAVAILABLE
    key = tutorial.key
    if key in started:
        return TutorialState.IN_PROGRESS
    if key in completed:
        return TutorialState.COMPLETE
    return TutorialState.NOT_STARTED
