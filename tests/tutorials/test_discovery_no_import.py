"""Listing the catalogue imports no package module.

``docs/specs/adr-053-learning-center.md`` FR-018, and spec §4.4's No-import row.
This is the requirement the whole of FR-029a exists to make satisfiable: the
callable entry-point payload contract is implemented by importing the target,
and the Learning Center lists its catalogue every time it opens, so a tutorial
group meeting both was impossible and the payload rule is the one that gave way.

Asserted with a ``sys.meta_path`` hook rather than by reading the source.
``EntryPoint.load``, ``importlib.import_module``, and
``importlib.util.find_spec`` all consult the meta path — ``find_spec`` imports
the target's *parent* packages in order to ask them, so it is no safer than the
other two — which means any of the three creeping back in fails this file
rather than passing a source inspection that was written against today's
spelling.

The tutorial under the hook **declares a driver**, which is the case that
matters: a driver-declaring package tutorial is the one whose logic lives in
code, and listing it must still read nothing but its manifest. Its driver is
imported later, when the user starts it (FR-021), which
``test_driver_parity.py`` covers.
"""

from __future__ import annotations

import importlib.metadata
import sys
from dataclasses import dataclass, field
from importlib.abc import MetaPathFinder
from pathlib import Path
from typing import Any

import pytest

from scistudio.core.dropins import user_tutorials_dir
from scistudio.tutorials import discovery
from scistudio.tutorials.discovery import DiscoveryEnvironment, discover_tutorials
from scistudio.tutorials.progress import ProgressStore
from scistudio.tutorials.projects import TutorialKey

from .conftest import write_tutorial

_GUARDED = "scistudio_tutorials_notimported_pkg"


class _ImportTripwire(MetaPathFinder):
    """Fail loudly the moment anything tries to import the guarded package."""

    def __init__(self, guarded: str) -> None:
        self.guarded = guarded
        self.attempts: list[str] = []

    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> None:
        if fullname == self.guarded or fullname.startswith(f"{self.guarded}."):
            self.attempts.append(fullname)
            raise AssertionError(f"listing the catalogue must not import '{fullname}' (FR-018)")
        return None


@dataclass
class _Distribution:
    root: Path
    name: str

    @property
    def files(self) -> list[importlib.metadata.PackagePath]:
        return []

    def locate_file(self, path: Any) -> Path:
        return self.root / str(path)


@dataclass
class _EntryPoint:
    name: str
    value: str
    group: str
    dist: Any
    loads: list[str] = field(default_factory=list)

    @property
    def module(self) -> str:
        return self.value.split(":", 1)[0]

    def load(self) -> Any:
        self.loads.append(self.name)
        raise AssertionError("listing the catalogue must not call EntryPoint.load() (FR-018/FR-029a)")


@pytest.fixture
def tripwire() -> Any:
    """Install the import hook for the duration of one test."""
    hook = _ImportTripwire(_GUARDED)
    sys.meta_path.insert(0, hook)
    try:
        yield hook
    finally:
        if hook in sys.meta_path:
            sys.meta_path.remove(hook)


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    return fake_home


@pytest.fixture
def core_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    directory = tmp_path / "core-tutorials"
    directory.mkdir()
    monkeypatch.setattr(discovery, "core_tutorials_dir", lambda: directory)
    return directory


@pytest.fixture
def driver_declaring_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _EntryPoint:
    """A package whose tutorial declares a driver, installed as metadata only."""
    root = tmp_path / "site-packages"
    write_tutorial(
        root / _GUARDED / "tutorials" / "guided",
        {
            "manifest_version": 1,
            "id": "guided",
            "title": "A package tutorial with its own driver",
            "summary": "Its logic is code; its listing is still only its manifest.",
            "cover": "cover.png",
            "order": 3,
            "requires": {"packages": ["scistudio-blocks-guided"]},
            "driver": f"{_GUARDED}.driver:GuidedDriver",
        },
        files={"cover.png": "not really a png"},
    )
    entry_point = _EntryPoint(
        name="tutorials",
        value=f"{_GUARDED}.tutorials",
        group="scistudio.tutorials",
        dist=_Distribution(root=root, name="scistudio-blocks-guided"),
    )

    def _entry_points(*_args: object, **kwargs: object) -> tuple[_EntryPoint, ...]:
        return (entry_point,) if kwargs.get("group") == "scistudio.tutorials" else ()

    monkeypatch.setattr(importlib.metadata, "entry_points", _entry_points)
    return entry_point


@pytest.fixture
def environment() -> DiscoveryEnvironment:
    """Stated rather than probed, so the test measures discovery and nothing else."""
    return DiscoveryEnvironment(
        scistudio_version="0.3.1",
        installed_distributions=frozenset({"scistudio-blocks-guided"}),
        agent_available=True,
        git_available=True,
    )


def test_listing_a_driver_declaring_package_tutorial_imports_nothing(
    tripwire: _ImportTripwire,
    home: Path,
    core_dir: Path,
    driver_declaring_package: _EntryPoint,
    environment: DiscoveryEnvironment,
) -> None:
    """FR-018: title, summary, cover, order, and requirements come from the manifest.

    Every one of those five is read back here, because "imported nothing" is
    only interesting if the listing was complete: a discovery pass that skipped
    the package would also import nothing.
    """
    result = discover_tutorials(environment=environment)

    tutorial = result.find(
        TutorialKey(source_kind="package", source_id="scistudio-blocks-guided", tutorial_id="guided")
    )
    assert tutorial is not None
    assert tutorial.title == "A package tutorial with its own driver"
    assert tutorial.summary == "Its logic is code; its listing is still only its manifest."
    assert tutorial.cover == "cover.png"
    assert tutorial.order == 3
    assert tutorial.is_startable

    assert tripwire.attempts == []
    assert driver_declaring_package.loads == [], "resolution must not call EntryPoint.load()"
    assert _GUARDED not in sys.modules
    assert not any(name.startswith(f"{_GUARDED}.") for name in sys.modules)


def test_building_the_whole_catalogue_imports_nothing(
    tripwire: _ImportTripwire,
    tmp_path: Path,
    home: Path,
    core_dir: Path,
    driver_declaring_package: _EntryPoint,
    environment: DiscoveryEnvironment,
) -> None:
    """The guarantee holds for the operation the Learning Center actually performs.

    Discovery is one half; grouping it with progress and rendering the entries
    is the other, and both run on every open. A cover resolved, an order sorted,
    or a state computed by touching package code would be just as much a
    violation as an ``EntryPoint.load()``.
    """
    write_tutorial(
        core_dir / "welcome",
        {
            "manifest_version": 1,
            "id": "welcome",
            "title": "Welcome",
            "summary": "The core tutorial.",
            "steps": [{"id": "one", "say": "Hello."}],
        },
    )
    write_tutorial(
        user_tutorials_dir() / "mine",
        {
            "manifest_version": 1,
            "id": "mine",
            "title": "Mine",
            "summary": "A user tutorial.",
            "steps": [{"id": "one", "say": "Hello."}],
        },
    )

    catalogue = discovery.build_catalogue(
        discover_tutorials(environment=environment),
        progress=ProgressStore(home / ".scistudio"),
    )

    assert [group.source_kind for group in catalogue.groups] == ["core", "package", "user"]
    assert tripwire.attempts == []
    assert _GUARDED not in sys.modules
