"""Four-source discovery, and what happens when a tutorial is not usable.

``docs/specs/adr-053-learning-center.md`` FR-016 … FR-024, and spec §4.4's
Discovery row. All four sources are found, the entry-point group is read, a
duplicate id within one source is rejected naming both paths (FR-023), a
malformed manifest does not empty its group (FR-022), and a tutorial whose
requirements are unmet is still listed (FR-024).

The no-import guarantee (FR-018) has its own file, because it is asserted with
an import hook rather than with an assertion about a return value.
"""

from __future__ import annotations

import importlib.metadata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from scistudio.core.dropins import tutorial_scan_dirs, user_tutorials_dir
from scistudio.tutorials import discovery
from scistudio.tutorials.discovery import (
    DiscoveryEnvironment,
    TutorialState,
    build_catalogue,
    discover_tutorials,
)
from scistudio.tutorials.progress import ProgressStore
from scistudio.tutorials.projects import TutorialKey

from .conftest import write_tutorial

# ---------------------------------------------------------------------------
# Stand-ins for installed metadata
# ---------------------------------------------------------------------------


@dataclass
class _Distribution:
    """A distribution that can answer for its own files, as a real one does."""

    root: Path
    name: str

    @property
    def files(self) -> list[importlib.metadata.PackagePath]:
        return []

    def locate_file(self, path: Any) -> Path:
        return self.root / str(path)


@dataclass
class _EntryPoint:
    """An entry point carrying the four attributes the shared helper reads."""

    name: str
    value: str
    group: str
    dist: Any = None
    loads: list[str] = field(default_factory=list)

    @property
    def module(self) -> str:
        return self.value.split(":", 1)[0]

    def load(self) -> Any:  # pragma: no cover - reaching this is the bug FR-018 forbids
        self.loads.append(self.name)
        raise AssertionError("listing the catalogue must not load an entry point (FR-018)")


def _entry_points_returning(*entry_points: _EntryPoint) -> Any:
    def _entry_points(*_args: object, **kwargs: object) -> tuple[_EntryPoint, ...]:
        group = kwargs.get("group")
        return tuple(item for item in entry_points if item.group == group)

    return _entry_points


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``Path.home()`` at an isolated directory."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    return fake_home


@pytest.fixture
def core_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the core source at a scratch directory.

    Redirected rather than exercised in place so these tests describe discovery
    rather than whichever tutorials core happens to ship this week.
    """
    directory = tmp_path / "core-tutorials"
    directory.mkdir()
    monkeypatch.setattr(discovery, "core_tutorials_dir", lambda: directory)
    return directory


@pytest.fixture
def no_packages(monkeypatch: pytest.MonkeyPatch) -> None:
    """No package declares the tutorial group, unless a test says otherwise."""
    monkeypatch.setattr(importlib.metadata, "entry_points", _entry_points_returning())


@pytest.fixture
def environment() -> DiscoveryEnvironment:
    """A stated environment: one package installed, no agent, git present."""
    return DiscoveryEnvironment(
        scistudio_version="0.3.1",
        installed_distributions=frozenset({"scistudio-blocks-imaging"}),
        agent_available=False,
        git_available=True,
    )


def _manifest(tutorial_id: str, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "manifest_version": 1,
        "id": tutorial_id,
        "title": tutorial_id.replace("-", " ").title(),
        "summary": f"The {tutorial_id} tutorial.",
        "steps": [{"id": "one", "say": "Do the thing."}],
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# FR-016, FR-017 — the four sources
# ---------------------------------------------------------------------------


def test_all_four_sources_are_discovered(
    tmp_path: Path,
    home: Path,
    core_dir: Path,
    environment: DiscoveryEnvironment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-016/FR-017: core, a package entry point, the user tier, and the project tier."""
    write_tutorial(core_dir / "welcome", _manifest("welcome"))

    package_root = tmp_path / "site-packages" / "demo_pkg" / "tutorials"
    write_tutorial(package_root / "intro", _manifest("intro"))
    monkeypatch.setattr(
        importlib.metadata,
        "entry_points",
        _entry_points_returning(
            _EntryPoint(
                name="tutorials",
                value="demo_pkg.tutorials",
                group="scistudio.tutorials",
                dist=_Distribution(root=tmp_path / "site-packages", name="scistudio-blocks-demo"),
            )
        ),
    )

    write_tutorial(user_tutorials_dir() / "mine", _manifest("mine"))
    project = tmp_path / "project"
    write_tutorial(project / "tutorials" / "local", _manifest("local"))

    result = discover_tutorials(project_dir=project, environment=environment)

    assert [(str(source.kind), source.id) for source in result.sources] == [
        ("core", ""),
        ("package", "scistudio-blocks-demo"),
        ("user", "user"),
        ("project", "project"),
    ]
    assert {tutorial.id for tutorial in result.tutorials} == {"welcome", "intro", "mine", "local"}


def test_the_local_tiers_are_exactly_the_shared_tier_definition(
    tmp_path: Path,
    home: Path,
    core_dir: Path,
    no_packages: None,
    environment: DiscoveryEnvironment,
) -> None:
    """FR-031: tutorials join ``dropins``' tier answer rather than writing a fourth.

    Asserted against :func:`~scistudio.core.dropins.tutorial_scan_dirs` rather
    than against two hardcoded paths, so a change to the tier definition is a
    change to what discovery scans and cannot silently be only one of the two.
    """
    project = tmp_path / "project"
    write_tutorial(user_tutorials_dir() / "mine", _manifest("mine"))
    write_tutorial(project / "tutorials" / "local", _manifest("local"))

    result = discover_tutorials(project_dir=project, environment=environment)

    local = {source.directory for source in result.sources if str(source.kind) in {"user", "project"}}
    assert local == set(tutorial_scan_dirs(project))


def test_two_packages_may_ship_the_same_id(
    tmp_path: Path,
    home: Path,
    core_dir: Path,
    environment: DiscoveryEnvironment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-019: identity is the pair (source, id), so ``intro`` is not taken."""
    for package in ("alpha", "beta"):
        write_tutorial(tmp_path / package / f"{package}_pkg" / "tutorials" / "intro", _manifest("intro"))
    monkeypatch.setattr(
        importlib.metadata,
        "entry_points",
        _entry_points_returning(
            *(
                _EntryPoint(
                    name="tutorials",
                    value=f"{package}_pkg.tutorials",
                    group="scistudio.tutorials",
                    dist=_Distribution(root=tmp_path / package, name=f"scistudio-blocks-{package}"),
                )
                for package in ("alpha", "beta")
            )
        ),
    )

    result = discover_tutorials(environment=environment)

    keys = {tutorial.key for tutorial in result.tutorials}
    assert keys == {
        TutorialKey(source_kind="package", source_id="scistudio-blocks-alpha", tutorial_id="intro"),
        TutorialKey(source_kind="package", source_id="scistudio-blocks-beta", tutorial_id="intro"),
    }
    assert all(tutorial.is_startable for tutorial in result.tutorials)


def test_a_package_that_contributed_nothing_is_a_diagnostic(
    tmp_path: Path,
    home: Path,
    core_dir: Path,
    environment: DiscoveryEnvironment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-028: an install that contributed nothing is distinguishable from silence.

    The observable failure this guards against is a package that installed
    successfully and produced no tutorials, which a user cannot tell apart from
    a package that ships none.
    """
    (tmp_path / "site-packages" / "empty_pkg" / "tutorials").mkdir(parents=True)
    monkeypatch.setattr(
        importlib.metadata,
        "entry_points",
        _entry_points_returning(
            _EntryPoint(
                name="tutorials",
                value="empty_pkg.tutorials",
                group="scistudio.tutorials",
                dist=_Distribution(root=tmp_path / "site-packages", name="scistudio-blocks-empty"),
            )
        ),
    )

    result = discover_tutorials(environment=environment)

    assert result.sources == ()
    assert any("holds no tutorial directory" in message for message in result.diagnostic_messages)


# ---------------------------------------------------------------------------
# FR-022, FR-023 — nothing empties a group
# ---------------------------------------------------------------------------


def test_a_malformed_manifest_does_not_empty_its_own_source(
    home: Path, core_dir: Path, no_packages: None, environment: DiscoveryEnvironment
) -> None:
    """FR-022: one bad file costs one entry, including against its own siblings."""
    write_tutorial(core_dir / "good", _manifest("good"))
    broken = core_dir / "broken"
    broken.mkdir(parents=True)
    (broken / "tutorial.yaml").write_text("manifest_version: 1\ntitle: no id\n", encoding="utf-8")
    write_tutorial(core_dir / "also-good", _manifest("also-good"))

    result = discover_tutorials(environment=environment)

    startable = {tutorial.id for tutorial in result.tutorials if tutorial.is_startable}
    assert startable == {"good", "also-good"}
    listed = result.find(TutorialKey.core("broken"))
    assert listed is not None
    assert listed.unavailable_reason is not None


def test_a_future_manifest_version_says_so_rather_than_saying_broken(
    home: Path, core_dir: Path, no_packages: None, environment: DiscoveryEnvironment
) -> None:
    """FR-007a: "needs a newer SciStudio" and "is malformed" are different sentences.

    Both are listed as unavailable, and both leave their siblings alone; what
    separates them is what the user is told, which is the whole reason
    ``manifest_version`` exists.
    """
    write_tutorial(core_dir / "good", _manifest("good"))
    write_tutorial(core_dir / "future", _manifest("future", manifest_version=99))

    result = discover_tutorials(environment=environment)

    future = result.find(TutorialKey.core("future"))
    assert future is not None
    assert future.unavailable_reason is not None
    assert "manifest_version 99 requires a newer SciStudio" in future.unavailable_reason
    assert result.find(TutorialKey.core("good")) is not None
    assert (result.find(TutorialKey.core("good")) or future).is_startable


def test_a_duplicate_id_within_one_source_is_rejected_naming_both_paths(
    home: Path, core_dir: Path, no_packages: None, environment: DiscoveryEnvironment
) -> None:
    """FR-023: neither wins, because identity is what a duplicate destroys.

    Picking one would make which tutorial the user gets depend on directory
    iteration order, and would silently discard the other's session key,
    progress record, and project path — all three of which are derived from the
    pair (source, id).
    """
    first = write_tutorial(core_dir / "first", _manifest("clash"))
    second = write_tutorial(core_dir / "second", _manifest("clash"))
    write_tutorial(core_dir / "unaffected", _manifest("unaffected"))

    result = discover_tutorials(environment=environment)

    clashing = [tutorial for tutorial in result.tutorials if tutorial.id == "clash"]
    assert len(clashing) == 2
    for tutorial in clashing:
        assert not tutorial.is_startable
        assert tutorial.unavailable_reason is not None
        assert str(first) in tutorial.unavailable_reason
        assert str(second) in tutorial.unavailable_reason
    unaffected = result.find(TutorialKey.core("unaffected"))
    assert unaffected is not None and unaffected.is_startable


# ---------------------------------------------------------------------------
# FR-024 — unmet requirements are listed, not hidden
# ---------------------------------------------------------------------------


def test_a_tutorial_needing_an_uninstalled_package_is_still_listed(
    home: Path, core_dir: Path, no_packages: None, environment: DiscoveryEnvironment
) -> None:
    """FR-024: discoverability is the point of the catalogue.

    A user cannot decide whether to install a package whose teaching material
    is invisible until after installing it.
    """
    write_tutorial(
        core_dir / "spectra",
        _manifest("spectra", requires={"packages": ["scistudio-blocks-spectroscopy"]}),
    )

    tutorial = discover_tutorials(environment=environment).find(TutorialKey.core("spectra"))

    assert tutorial is not None
    assert tutorial.title == "Spectra"
    assert not tutorial.is_startable
    assert tutorial.unavailable_reason == ("needs the package 'scistudio-blocks-spectroscopy', which is not installed")


def test_an_installed_package_requirement_is_met(
    home: Path, core_dir: Path, no_packages: None, environment: DiscoveryEnvironment
) -> None:
    """The same predicate, satisfied — and matched on the normalized name."""
    write_tutorial(
        core_dir / "imaging",
        _manifest("imaging", requires={"packages": ["SciStudio_Blocks.Imaging"]}),
    )

    tutorial = discover_tutorials(environment=environment).find(TutorialKey.core("imaging"))

    assert tutorial is not None and tutorial.is_startable


@pytest.mark.parametrize(
    ("specifier", "startable"),
    [(">=0.3.0", True), (">=9.0", False), ("<0.1", False)],
)
def test_the_core_version_requirement_is_evaluated(
    specifier: str,
    startable: bool,
    home: Path,
    core_dir: Path,
    no_packages: None,
    environment: DiscoveryEnvironment,
) -> None:
    """FR-008: ``requires.scistudio`` is a version specifier against the running core."""
    write_tutorial(core_dir / "versioned", _manifest("versioned", requires={"scistudio": specifier}))

    tutorial = discover_tutorials(environment=environment).find(TutorialKey.core("versioned"))

    assert tutorial is not None
    assert tutorial.is_startable is startable


def test_an_agent_requirement_is_evaluated_against_the_environment(
    home: Path, core_dir: Path, no_packages: None, environment: DiscoveryEnvironment
) -> None:
    """FR-008: ``requires.agent`` asks whether the tutorial's AI material can run."""
    write_tutorial(core_dir / "ai", _manifest("ai", requires={"agent": True}))

    without = discover_tutorials(environment=environment).find(TutorialKey.core("ai"))
    assert without is not None and not without.is_startable
    assert without.unavailable_reason is not None and "agent" in without.unavailable_reason

    with_agent = discover_tutorials(
        environment=DiscoveryEnvironment(
            scistudio_version=environment.scistudio_version,
            installed_distributions=environment.installed_distributions,
            agent_available=True,
            git_available=True,
        )
    ).find(TutorialKey.core("ai"))
    assert with_agent is not None and with_agent.is_startable


def test_git_state_conditions_are_listed_but_not_startable_without_git(
    home: Path, core_dir: Path, no_packages: None
) -> None:
    """Spec §2 Edge Cases: git unavailable is ADR-039 §3.4's degraded mode, not a hidden entry."""
    write_tutorial(
        core_dir / "branching",
        _manifest(
            "branching",
            steps=[{"id": "branch", "say": "Make a branch.", "done_when": {"git_branch_exists": {"name": "wip"}}}],
        ),
    )
    write_tutorial(core_dir / "plain", _manifest("plain"))

    without_git = DiscoveryEnvironment(
        scistudio_version="0.3.1",
        installed_distributions=frozenset(),
        agent_available=False,
        git_available=False,
    )
    result = discover_tutorials(environment=without_git)

    branching = result.find(TutorialKey.core("branching"))
    assert branching is not None
    assert not branching.is_startable
    assert branching.unavailable_reason is not None and "git" in branching.unavailable_reason
    plain = result.find(TutorialKey.core("plain"))
    assert plain is not None and plain.is_startable


# ---------------------------------------------------------------------------
# The catalogue (FR-076, FR-084, FR-085)
# ---------------------------------------------------------------------------


def test_the_catalogue_groups_by_source_with_core_first_and_no_aggregate(
    tmp_path: Path,
    home: Path,
    core_dir: Path,
    environment: DiscoveryEnvironment,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-084 and FR-076: core leads, every group counts itself, nothing counts all."""
    write_tutorial(core_dir / "first", _manifest("first", order=1))
    write_tutorial(core_dir / "second", _manifest("second", order=2))
    write_tutorial(tmp_path / "sp" / "demo_pkg" / "tutorials" / "intro", _manifest("intro"))
    monkeypatch.setattr(
        importlib.metadata,
        "entry_points",
        _entry_points_returning(
            _EntryPoint(
                name="tutorials",
                value="demo_pkg.tutorials",
                group="scistudio.tutorials",
                dist=_Distribution(root=tmp_path / "sp", name="scistudio-blocks-demo"),
            )
        ),
    )
    store = ProgressStore(home / ".scistudio")
    store.mark_completed(TutorialKey.core("first"))

    catalogue = build_catalogue(discover_tutorials(environment=environment), progress=store)

    assert [group.source_kind for group in catalogue.groups] == ["core", "package"]
    assert (catalogue.groups[0].completed, catalogue.groups[0].total) == (1, 2)
    assert (catalogue.groups[1].completed, catalogue.groups[1].total) == (0, 1)
    assert not hasattr(catalogue, "completed"), "FR-076 forbids an aggregate across groups"


def test_entries_are_ordered_by_declared_order_then_title(
    home: Path, core_dir: Path, no_packages: None, environment: DiscoveryEnvironment
) -> None:
    """FR-007: ``order`` positions an entry within its group; unordered entries follow."""
    write_tutorial(core_dir / "b", _manifest("b", order=2))
    write_tutorial(core_dir / "a", _manifest("a", order=1))
    write_tutorial(core_dir / "z", _manifest("z"))

    catalogue = build_catalogue(
        discover_tutorials(environment=environment), progress=ProgressStore(home / ".scistudio")
    )

    assert [entry.id for entry in catalogue.groups[0].tutorials] == ["a", "b", "z"]


def test_every_entry_state_is_reported(
    home: Path, core_dir: Path, no_packages: None, environment: DiscoveryEnvironment
) -> None:
    """FR-085: not started, in progress, complete, or unavailable with the reason."""
    for tutorial_id in ("fresh", "running", "done"):
        write_tutorial(core_dir / tutorial_id, _manifest(tutorial_id))
    write_tutorial(core_dir / "blocked", _manifest("blocked", requires={"packages": ["absent-package"]}))
    store = ProgressStore(home / ".scistudio")
    store.mark_completed(TutorialKey.core("done"))

    catalogue = build_catalogue(
        discover_tutorials(environment=environment),
        progress=store,
        in_progress=[TutorialKey.core("running")],
    )

    states = {entry.id: entry.state for entry in catalogue.groups[0].tutorials}
    assert states == {
        "fresh": TutorialState.NOT_STARTED,
        "running": TutorialState.IN_PROGRESS,
        "done": TutorialState.COMPLETE,
        "blocked": TutorialState.UNAVAILABLE,
    }
    blocked = catalogue.entry(TutorialKey.core("blocked"))
    assert blocked is not None and blocked.unavailable_reason is not None


def test_listing_probes_the_machine_only_for_what_a_manifest_asks(
    home: Path, core_dir: Path, no_packages: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The environment's probes are lazy, because none of them is free.

    Enumerating installed distributions walks every ``dist-info``, resolving an
    agent searches the filesystem, and locating git runs a subprocess. A
    catalogue of tutorials that declare no ``requires`` and no git condition
    must ask none of that — otherwise opening the Learning Center, and every
    mapped event that re-runs discovery, would pay for all three.
    """
    probed: list[str] = []

    def _record_distributions() -> frozenset[str]:
        probed.append("distributions")
        return frozenset()

    def _record_agent() -> bool:
        probed.append("agent")
        return False

    def _record_git() -> bool:
        probed.append("git")
        return False

    monkeypatch.setattr(discovery, "installed_distribution_names", _record_distributions)
    monkeypatch.setattr(discovery, "agent_provider_available", _record_agent)
    monkeypatch.setattr(discovery, "git_available", _record_git)
    write_tutorial(core_dir / "plain", _manifest("plain"))
    write_tutorial(core_dir / "needs-package", _manifest("needs-package", requires={"packages": ["absent"]}))

    result = discover_tutorials()

    assert probed == ["distributions"], "only the question a manifest actually asked was probed"
    plain = result.find(TutorialKey.core("plain"))
    assert plain is not None and plain.is_startable
    blocked = result.find(TutorialKey.core("needs-package"))
    assert blocked is not None and not blocked.is_startable


# ---------------------------------------------------------------------------
# requires.tutorials — a track's levels gate on their predecessors (#2088)
# ---------------------------------------------------------------------------


def _gated_pair(core: Path) -> None:
    """Two core tutorials: ``level-two`` requires ``level-one`` completed."""
    write_tutorial(
        core / "level-one",
        {
            "manifest_version": 1,
            "id": "level-one",
            "title": "Level One",
            "summary": "The first level.",
            "steps": [{"id": "one", "say": "Start here."}],
        },
    )
    write_tutorial(
        core / "level-two",
        {
            "manifest_version": 1,
            "id": "level-two",
            "title": "Level Two",
            "summary": "The second level.",
            "requires": {"tutorials": ["level-one"]},
            "steps": [{"id": "one", "say": "Carry on."}],
        },
    )


def test_an_uncompleted_prerequisite_lists_the_tutorial_unavailable_naming_it(
    core_dir: Path,
) -> None:
    from scistudio.tutorials.discovery import DiscoveryEnvironment, discover_tutorials
    from scistudio.tutorials.projects import TutorialKey

    _gated_pair(core_dir)
    environment = DiscoveryEnvironment(completed_tutorials=frozenset())
    result = discover_tutorials(environment=environment)

    gated = result.find(TutorialKey.core("level-two"))
    assert gated is not None
    assert gated.is_startable is False
    assert gated.unavailable_reason is not None
    assert "level-one" in gated.unavailable_reason
    # FR-024: unmet requirements never hide a tutorial.
    ungated = result.find(TutorialKey.core("level-one"))
    assert ungated is not None and ungated.is_startable is True


def test_a_completed_prerequisite_makes_the_tutorial_startable(core_dir: Path) -> None:
    from scistudio.tutorials.discovery import DiscoveryEnvironment, discover_tutorials
    from scistudio.tutorials.projects import TutorialKey

    _gated_pair(core_dir)
    environment = DiscoveryEnvironment(completed_tutorials=frozenset({TutorialKey.core("level-one")}))
    result = discover_tutorials(environment=environment)

    gated = result.find(TutorialKey.core("level-two"))
    assert gated is not None and gated.is_startable is True


def test_the_prerequisite_is_judged_within_its_own_source(core_dir: Path) -> None:
    """Same-source ids only: a completion under another source must not unlock it."""
    from scistudio.tutorials.discovery import DiscoveryEnvironment, discover_tutorials
    from scistudio.tutorials.projects import TutorialKey

    _gated_pair(core_dir)
    foreign = TutorialKey(source_kind="package", source_id="some-pack", tutorial_id="level-one")
    environment = DiscoveryEnvironment(completed_tutorials=frozenset({foreign}))
    result = discover_tutorials(environment=environment)

    gated = result.find(TutorialKey.core("level-two"))
    assert gated is not None and gated.is_startable is False


def test_the_catalogue_surfaces_the_prerequisite_gate(
    core_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The FR-024 pattern end to end: unavailable with the reason, then unlocked.

    Driven through the runtime rather than through discovery alone, because the
    runtime is what states its own progress store's completions (#2088) — the
    seam a wrong wiring would break while every direct-discovery test passed.
    """
    from scistudio.tutorials.conditions import ExternalEventNames
    from scistudio.tutorials.discovery import TutorialState
    from scistudio.tutorials.progress import ProgressStore
    from scistudio.tutorials.projects import TutorialKey
    from scistudio.tutorials.session import SessionStore, TutorialRuntime

    from .conftest import StubProductState

    _gated_pair(core_dir)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    progress = ProgressStore(home / ".scistudio")
    runtime = TutorialRuntime(
        product_state=StubProductState,
        external_events=ExternalEventNames(blocks_reloaded="blocks.reloaded", file_changed="file.changed"),
        progress=progress,
        sessions=SessionStore(home / ".scistudio"),
    )

    entry = runtime.catalogue().entry(TutorialKey.core("level-two"))
    assert entry is not None
    assert entry.state is TutorialState.UNAVAILABLE
    assert entry.unavailable_reason is not None and "level-one" in entry.unavailable_reason

    progress.mark_completed(TutorialKey.core("level-one"))
    unlocked = runtime.catalogue().entry(TutorialKey.core("level-two"))
    assert unlocked is not None
    assert unlocked.state is TutorialState.NOT_STARTED
    assert unlocked.unavailable_reason is None


def test_requires_tutorials_round_trips_through_the_manifest(tmp_path: Path) -> None:
    from scistudio.tutorials.manifest import TutorialSourceKind, load_manifest

    directory = write_tutorial(
        tmp_path / "gated",
        {
            "manifest_version": 1,
            "id": "gated",
            "title": "Gated",
            "summary": "Requires a sibling.",
            "requires": {"tutorials": ["level-one"]},
            "steps": [{"id": "one", "say": "One."}],
        },
    )
    manifest = load_manifest(directory, source_kind=TutorialSourceKind.CORE)
    assert manifest.requires.tutorials == ("level-one",)
    assert manifest.requires.is_empty is False
