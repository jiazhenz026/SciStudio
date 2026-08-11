"""Every ``scistudio.*`` entry-point group behaves the same way.

ADR-053 / ``docs/specs/adr-053-learning-center.md`` §3 "Entry-point symmetry",
FR-025 to FR-033. Three registries read entry points and, before the shared
helper, disagreed about all four of: whether an enumeration failure escapes,
whether a load failure is recorded anywhere a user can see, what payload shape
is accepted, and whether plugin import roots are prepared. Adding a fourth
group to that would have made the disagreement the convention.

**These tests are parametrised over**
:data:`scistudio.core.entry_points.LIVE_ENTRY_POINT_GROUPS`, never over a
hardcoded list of names. That is the point of the file (FR-033): a fifth group
is added by appending to that tuple, and a fifth group that does not meet the
contract fails here rather than diverging quietly.

``scistudio.tutorials`` has no registry yet — it is built on top of this
contract, not before it — so the group contract is exercised through the shared
helper. The registry-level half is
:func:`test_no_registry_propagates_an_enumeration_failure`, whose coverage map
is asserted to be exhaustive so the tutorial registry cannot join without being
added to it.
"""

from __future__ import annotations

import importlib.metadata
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from importlib.abc import MetaPathFinder
from pathlib import Path
from typing import Any

import pytest

from scistudio.core.entry_points import (
    BARE_CLASS_GROUPS,
    BLOCKS_ENTRY_POINT_GROUP,
    LIVE_ENTRY_POINT_GROUPS,
    METADATA_ONLY_GROUPS,
    PREVIEWERS_ENTRY_POINT_GROUP,
    STAGE_ENUMERATE,
    STAGE_INVOKE,
    STAGE_LOAD,
    TUTORIALS_ENTRY_POINT_GROUP,
    TYPES_ENTRY_POINT_GROUP,
    EntryPointDiagnostic,
    enumerate_group,
    load_entry_point,
    resolve_entry_point_directory,
    resolve_payload,
)

# ---------------------------------------------------------------------------
# Stand-ins
# ---------------------------------------------------------------------------


@dataclass
class _EntryPointStub:
    """An entry point the tests control, including its declaring distribution.

    ``importlib.metadata.EntryPoint`` only gains a ``dist`` through a private
    constructor, and every function under test reads the entry point through
    ``getattr``, so a stand-in carrying the same four attributes exercises the
    same contract without reaching into private API.
    """

    name: str
    value: str
    group: str
    dist: Any = None
    loader: Any = None
    load_error: BaseException | None = None
    loads: list[str] = field(default_factory=list)

    def load(self) -> Any:
        self.loads.append(self.name)
        if self.load_error is not None:
            raise self.load_error
        return self.loader


@dataclass
class _FakeDistribution:
    """A distribution whose files are known only through its metadata.

    ``locate_file`` answers for recorded files and, when *answer_directly* is
    set, for the module path itself. The two modes are both real: a
    ``PathDistribution`` resolves any relative path against its own parent,
    while a distribution backed by something other than a directory can only
    answer for paths it recorded.
    """

    root: Path
    name: str
    recorded: tuple[str, ...] = ()
    answer_directly: bool = True

    @property
    def files(self) -> list[importlib.metadata.PackagePath]:
        return [importlib.metadata.PackagePath(item) for item in self.recorded]

    def locate_file(self, path: Any) -> Path | None:
        text = str(path)
        if not self.answer_directly and text not in self.recorded:
            return None
        return self.root / text


class _ImportTripwire(MetaPathFinder):
    """Fail the test if anything tries to import the guarded module.

    ADR-053 FR-018 forbids importing a package module while listing the
    tutorial catalogue, and FR-029a exists because the callable payload
    contract cannot be satisfied without doing exactly that. Asserting it with
    an import hook rather than by reading the source is the difference between
    pinning the behaviour and pinning today's implementation: ``find_spec``,
    ``import_module``, and ``EntryPoint.load`` all come through here, so a
    later refactor that reintroduces any of them fails.
    """

    def __init__(self, guarded: str) -> None:
        self.guarded = guarded
        self.attempts: list[str] = []

    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> None:
        if fullname == self.guarded or fullname.startswith(f"{self.guarded}."):
            self.attempts.append(fullname)
            raise AssertionError(f"the tutorial group must not import '{fullname}' (FR-018/FR-029a)")
        return None


@pytest.fixture
def import_tripwire() -> Iterator[Any]:
    def _install(module_name: str) -> _ImportTripwire:
        tripwire = _ImportTripwire(module_name)
        sys.meta_path.insert(0, tripwire)
        installed.append(tripwire)
        return tripwire

    installed: list[_ImportTripwire] = []
    try:
        yield _install
    finally:
        for tripwire in installed:
            if tripwire in sys.meta_path:
                sys.meta_path.remove(tripwire)


def _exploding_entry_points(*_args: object, **_kwargs: object) -> object:
    raise RuntimeError("unreadable dist-info")


def _payload_for(group: str) -> Any:
    """A minimal valid payload for *group*'s contract."""
    if group in METADATA_ONLY_GROUPS:
        raise AssertionError(f"{group} declares a metadata-only payload, not a callable one")
    return lambda: []


# ---------------------------------------------------------------------------
# FR-026 — enumeration failure is contained identically for every group
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("group", LIVE_ENTRY_POINT_GROUPS)
def test_enumeration_failure_is_an_empty_group_not_an_exception(
    group: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-026: unreadable metadata yields an empty group, never a raise.

    ``scistudio.types`` used to call ``entry_points(group=...)`` bare, so this
    failure reached whoever asked the registry to scan — which is the whole
    process's type catalogue, lost to one bad ``dist-info``.
    """
    monkeypatch.setattr(importlib.metadata, "entry_points", _exploding_entry_points)
    diagnostics: list[EntryPointDiagnostic] = []

    assert enumerate_group(group, diagnostics=diagnostics) == ()

    assert [d.stage for d in diagnostics] == [STAGE_ENUMERATE]
    assert diagnostics[0].group == group
    assert diagnostics[0].entry_point == ""


@pytest.mark.parametrize("group", LIVE_ENTRY_POINT_GROUPS)
def test_enumeration_needs_no_diagnostic_sink_to_stay_contained(
    group: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Containment is not conditional on the caller wanting diagnostics."""
    monkeypatch.setattr(importlib.metadata, "entry_points", _exploding_entry_points)

    assert enumerate_group(group) == ()


# ---------------------------------------------------------------------------
# FR-027 / FR-028 — one entry point failing does not take the group with it
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("group", [g for g in LIVE_ENTRY_POINT_GROUPS if g not in METADATA_ONLY_GROUPS])
def test_one_failing_entry_point_leaves_the_rest_of_the_group(group: str) -> None:
    """FR-027 + FR-028: contained to itself, and recorded rather than silent."""
    broken = _EntryPointStub(
        name="broken",
        value="pkg_broken:contribute",
        group=group,
        load_error=ImportError("no module named pkg_broken"),
    )
    healthy = _EntryPointStub(
        name="healthy",
        value="pkg_healthy:contribute",
        group=group,
        loader=_payload_for(group),
    )
    diagnostics: list[EntryPointDiagnostic] = []

    results = [load_entry_point(ep, group, diagnostics=diagnostics) for ep in (broken, healthy)]

    assert results[0] is None
    assert results[1] is healthy.loader
    assert [(d.group, d.entry_point, d.stage) for d in diagnostics] == [(group, "broken", STAGE_LOAD)]


@pytest.mark.parametrize("group", [g for g in LIVE_ENTRY_POINT_GROUPS if g not in METADATA_ONLY_GROUPS])
def test_a_payload_that_raises_is_recorded_as_a_diagnostic(group: str) -> None:
    """FR-028: an installed package that contributed nothing says why."""

    def _explode() -> list[object]:
        raise RuntimeError("plugin is unhappy")

    diagnostics: list[EntryPointDiagnostic] = []

    payload = resolve_payload(
        _explode,
        group=group,
        entry_point="unhappy",
        allow_bare_class=group in BARE_CLASS_GROUPS,
        diagnostics=diagnostics,
    )

    assert payload is None
    assert [(d.group, d.entry_point, d.stage) for d in diagnostics] == [(group, "unhappy", STAGE_INVOKE)]
    assert "plugin is unhappy" in diagnostics[0].message


@pytest.mark.parametrize("group", LIVE_ENTRY_POINT_GROUPS)
def test_every_diagnostic_renders_with_its_group_and_stage(group: str) -> None:
    """The registries surface ``list[str]``, so the string has to carry the facts."""
    rendered = str(EntryPointDiagnostic(group=group, entry_point="probe", stage=STAGE_LOAD, message="boom"))

    assert group in rendered
    assert "probe" in rendered
    assert STAGE_LOAD in rendered
    assert "boom" in rendered


# ---------------------------------------------------------------------------
# FR-033 — refresh: no group caches its own answer
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("group", LIVE_ENTRY_POINT_GROUPS)
def test_a_second_enumeration_sees_a_newly_installed_package(
    group: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-031/FR-033: refresh means re-reading, for every group alike.

    Package install, uninstall, and branch switch all work by asking the
    registries to scan again. A group that memoised its first answer would
    report the pre-install world forever, which is the failure this pins.
    """
    installed: list[_EntryPointStub] = []

    def _entry_points(*_args: object, **kwargs: object) -> object:
        return tuple(ep for ep in installed if ep.group == kwargs.get("group"))

    monkeypatch.setattr(importlib.metadata, "entry_points", _entry_points)

    assert enumerate_group(group) == ()

    installed.append(_EntryPointStub(name="late", value="pkg_late:contribute", group=group))

    assert [ep.name for ep in enumerate_group(group)] == ["late"]


# ---------------------------------------------------------------------------
# FR-029 — one payload contract, and one documented affordance
# ---------------------------------------------------------------------------


def test_the_bare_class_affordance_belongs_to_the_block_group_alone() -> None:
    """FR-029: already-published compatibility, not a convention to spread.

    Asserted against the declared set rather than against behaviour alone so
    that adding a group to it is a deliberate edit that fails this test.
    """
    assert frozenset({BLOCKS_ENTRY_POINT_GROUP}) == BARE_CLASS_GROUPS


@pytest.mark.parametrize("group", [g for g in LIVE_ENTRY_POINT_GROUPS if g not in METADATA_ONLY_GROUPS])
def test_a_bare_class_is_returned_untouched_only_where_it_is_allowed(group: str) -> None:
    """The affordance is a real behavioural difference, not a label.

    Where it applies the class is the payload; where it does not, the class is
    treated as the callable the contract asks for and invoked — so a group that
    quietly started accepting bare classes would change this result.
    """
    instantiations: list[str] = []

    class _Contribution:
        def __init__(self) -> None:
            instantiations.append(group)

    allowed = group in BARE_CLASS_GROUPS
    payload = resolve_payload(
        _Contribution,
        group=group,
        entry_point="probe",
        allow_bare_class=allowed,
        diagnostics=[],
    )

    if allowed:
        assert payload is _Contribution
        assert instantiations == []
    else:
        assert isinstance(payload, _Contribution)
        assert instantiations == [group]


@pytest.mark.parametrize("group", [g for g in LIVE_ENTRY_POINT_GROUPS if g not in METADATA_ONLY_GROUPS])
def test_a_non_callable_payload_is_refused_with_a_diagnostic(group: str) -> None:
    """FR-029: the contract is a callable, and breaking it is reported."""
    diagnostics: list[EntryPointDiagnostic] = []

    payload = resolve_payload(
        "not a callable",
        group=group,
        entry_point="probe",
        allow_bare_class=group in BARE_CLASS_GROUPS,
        diagnostics=diagnostics,
    )

    assert payload is None
    assert [d.stage for d in diagnostics] == [STAGE_INVOKE]


@pytest.mark.parametrize("group", [g for g in LIVE_ENTRY_POINT_GROUPS if g not in METADATA_ONLY_GROUPS])
def test_a_bare_class_is_accepted_but_a_bare_list_is_refused(group: str) -> None:
    """The FR-029 affordance is a bare *class*, and only that.

    ``BlockRegistry._scan_tier2`` used to resolve its payload with
    ``result = loaded() if callable(loaded) else loaded``, which accepted any
    non-callable — so an entry point whose value resolved to a bare **list** of
    block classes worked, undocumented and unintended. It is refused now, and
    that decision is pinned here rather than left implicit.

    Nothing published depends on the list form: the in-repo fixture package
    declares callables for all three of its groups, and ADR-049's package
    validator already enforces the callable return shape (PV-02-003), so a real
    package shipping a bare list fails validation before it ever reaches a
    registry. The bare *class*, by contrast, is a published form that installed
    packages do depend on, which is why exactly one of these two survives.
    """

    class _Contribution:
        """A block-like class an entry point could name directly."""

    allowed = group in BARE_CLASS_GROUPS

    class_diagnostics: list[EntryPointDiagnostic] = []
    from_class = resolve_payload(
        _Contribution,
        group=group,
        entry_point="bare-class",
        allow_bare_class=allowed,
        diagnostics=class_diagnostics,
    )

    list_diagnostics: list[EntryPointDiagnostic] = []
    from_list = resolve_payload(
        [_Contribution],
        group=group,
        entry_point="bare-list",
        allow_bare_class=allowed,
        diagnostics=list_diagnostics,
    )

    if allowed:
        assert from_class is _Contribution, "the published bare-class form must keep working"
        assert class_diagnostics == []
    else:
        assert class_diagnostics == [] or from_class is not _Contribution

    assert from_list is None, "a bare list is not the contract and must not be accepted"
    assert [d.stage for d in list_diagnostics] == [STAGE_INVOKE]
    assert "list" in list_diagnostics[0].message


# ---------------------------------------------------------------------------
# FR-018 / FR-029a — the tutorial group resolves without importing
# ---------------------------------------------------------------------------


def _tutorial_package(tmp_path: Path, module: str) -> Path:
    directory = tmp_path / Path(*module.split("."))
    (directory / "first-workflow").mkdir(parents=True)
    (directory / "first-workflow" / "tutorial.yaml").write_text("id: first-workflow\n", encoding="utf-8")
    return directory


@pytest.mark.parametrize("group", sorted(METADATA_ONLY_GROUPS))
def test_the_metadata_only_group_resolves_a_directory_without_importing(
    group: str,
    tmp_path: Path,
    import_tripwire: Any,
) -> None:
    """FR-029a + FR-018: the value names a module, and it stays unimported.

    Asserted with a ``sys.meta_path`` hook rather than by reading the source:
    ``EntryPoint.load``, ``importlib.import_module``, and
    ``importlib.util.find_spec`` all consult the meta path, so any of the three
    creeping back in trips this.
    """
    module = "scistudio_tutorials_probe_pkg.tutorials"
    expected = _tutorial_package(tmp_path, module)
    tripwire = import_tripwire("scistudio_tutorials_probe_pkg")
    ep = _EntryPointStub(
        name="probe",
        value=module,
        group=group,
        dist=_FakeDistribution(root=tmp_path, name="scistudio-tutorials-probe"),
    )
    diagnostics: list[EntryPointDiagnostic] = []

    resolved = resolve_entry_point_directory(ep, diagnostics=diagnostics)

    assert resolved == expected
    assert diagnostics == []
    assert tripwire.attempts == []
    assert ep.loads == [], "resolution must not call EntryPoint.load()"
    assert "scistudio_tutorials_probe_pkg" not in sys.modules


@pytest.mark.parametrize("group", sorted(METADATA_ONLY_GROUPS))
def test_the_metadata_only_group_resolves_from_recorded_files_alone(
    group: str,
    tmp_path: Path,
    import_tripwire: Any,
) -> None:
    """A distribution that can only answer for the files it recorded still resolves."""
    module = "scistudio_tutorials_probe_files.tutorials"
    expected = _tutorial_package(tmp_path, module)
    tripwire = import_tripwire("scistudio_tutorials_probe_files")
    ep = _EntryPointStub(
        name="probe",
        value=module,
        group=group,
        dist=_FakeDistribution(
            root=tmp_path,
            name="scistudio-tutorials-probe-files",
            recorded=(f"{module.replace('.', '/')}/first-workflow/tutorial.yaml",),
            answer_directly=False,
        ),
    )

    assert resolve_entry_point_directory(ep) == expected
    assert tripwire.attempts == []


@pytest.mark.parametrize("group", sorted(METADATA_ONLY_GROUPS))
def test_an_unresolvable_metadata_only_entry_point_is_a_diagnostic(
    group: str,
    import_tripwire: Any,
) -> None:
    """FR-026/FR-028 apply unchanged: contained, and recorded rather than silent."""
    module = "scistudio_tutorials_probe_absent"
    tripwire = import_tripwire(module)
    ep = _EntryPointStub(name="probe", value=module, group=group, dist=None)
    diagnostics: list[EntryPointDiagnostic] = []

    assert resolve_entry_point_directory(ep, diagnostics=diagnostics) is None

    assert [(d.group, d.entry_point) for d in diagnostics] == [(group, "probe")]
    assert tripwire.attempts == []


def test_the_metadata_only_exemption_is_the_tutorial_group_alone() -> None:
    """FR-029a is an exemption with a reason, not a second general option.

    The reason is that the callable contract is implemented by importing the
    target and FR-018 forbids that while listing the catalogue. Nothing else
    has that conflict, so nothing else may join without a new argument.
    """
    assert frozenset({TUTORIALS_ENTRY_POINT_GROUP}) == METADATA_ONLY_GROUPS
    assert not (METADATA_ONLY_GROUPS & BARE_CLASS_GROUPS)


# ---------------------------------------------------------------------------
# FR-026 at the registry level — the regression that motivated the rule
# ---------------------------------------------------------------------------

#: Which scan reads which group.
#:
#: ``scistudio.tutorials`` is a row like the other three, and deliberately not
#: a *registry* row: the Learning Center catalogue is recomputed on every
#: listing and cached nowhere, so there is no registry object to rebuild and
#: nothing that can go stale (ADR-053 FR-031). What the three assertions below
#: check is the part that is common to all four — that a scan contains an
#: enumeration failure, records a load failure as a diagnostic, and stays quiet
#: when nothing is wrong — and that part does not depend on a group holding
#: state.
_REGISTRY_SCANS: dict[str, str] = {
    BLOCKS_ENTRY_POINT_GROUP: "blocks",
    TYPES_ENTRY_POINT_GROUP: "types",
    PREVIEWERS_ENTRY_POINT_GROUP: "previewers",
    TUTORIALS_ENTRY_POINT_GROUP: "tutorials",
}

_GROUPS_WITHOUT_A_REGISTRY = frozenset(LIVE_ENTRY_POINT_GROUPS) - set(_REGISTRY_SCANS)


def test_every_live_group_is_either_scanned_by_a_registry_or_tracked() -> None:
    """The coverage map above may not fall behind the live group set.

    Every live group now has a scan, so the tracked-exception set is empty and
    must stay empty: the map is how FR-026 coverage is claimed, and a group
    added to ``LIVE_ENTRY_POINT_GROUPS`` without a row here would otherwise be
    uncovered and unmentioned. A fifth group that genuinely cannot be scanned
    belongs in this assertion with its reason, not absent from it.
    """
    assert not _GROUPS_WITHOUT_A_REGISTRY, (
        "update _REGISTRY_SCANS when a group gains or loses a scan; "
        f"these are covered by nothing: {sorted(_GROUPS_WITHOUT_A_REGISTRY)}"
    )


def _scan_registry(kind: str) -> list[str]:
    """Run one group's entry-point pass and return its diagnostics."""
    if kind == "blocks":
        from scistudio.blocks.registry import BlockRegistry

        registry = BlockRegistry()
        registry._scan_tier2()
        return registry.diagnostics
    if kind == "types":
        from scistudio.core.types.registry import TypeRegistry

        type_registry = TypeRegistry()
        type_registry._scan_entrypoint_types()
        return type_registry.diagnostics
    if kind == "tutorials":
        return _scan_tutorials()
    from scistudio.previewers.registry import PreviewerRegistry

    previewer_registry = PreviewerRegistry()
    previewer_registry._scan_entry_points()
    return previewer_registry.diagnostics


def _scan_tutorials() -> list[str]:
    """Run the Learning Center catalogue scan and return its diagnostics.

    The environment is stated in full so the scan probes nothing. Left to
    itself, ``DiscoveryEnvironment`` would enumerate installed distributions,
    search for an agent binary, and run ``git --version`` — none of which is
    the entry-point path these assertions are about, and all of which would
    make a symmetry test depend on what happens to be installed on the machine
    running it.
    """
    from scistudio.tutorials.discovery import DiscoveryEnvironment, discover_tutorials

    result = discover_tutorials(
        environment=DiscoveryEnvironment(
            scistudio_version="0.0.0",
            installed_distributions=frozenset(),
            agent_available=False,
            git_available=False,
        )
    )
    return list(result.diagnostic_messages)


@pytest.mark.parametrize("group", sorted(_REGISTRY_SCANS))
def test_no_registry_propagates_an_enumeration_failure(
    group: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-026 where it actually bit: the scan itself.

    ``TypeRegistry._scan_entrypoint_types`` used to let this out. The other two
    absorbed it. All four absorb it now, and all four say so afterwards — the
    tutorial catalogue included, which is the point of writing the fourth group
    against a settled contract rather than retrofitting it onto one.
    """
    monkeypatch.setattr(importlib.metadata, "entry_points", _exploding_entry_points)

    diagnostics = _scan_registry(_REGISTRY_SCANS[group])

    assert any(group in diagnostic for diagnostic in diagnostics), (
        f"{group} enumeration failure left no diagnostic: {diagnostics}"
    )


@pytest.mark.parametrize("group", sorted(_REGISTRY_SCANS))
def test_every_registry_records_a_load_failure_as_a_diagnostic(
    group: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-028 at the registry level, in the one shape all three expose.

    Before this, only the previewer registry kept a diagnostic list, so a
    package whose ``scistudio.blocks`` or ``scistudio.types`` hook failed to
    import installed cleanly and contributed nothing, with no way for the user
    to tell that apart from a package that had nothing to contribute.
    """
    broken = _EntryPointStub(
        name="broken",
        value="pkg_broken:contribute",
        group=group,
        load_error=ImportError("no module named pkg_broken"),
    )

    def _entry_points(*_args: object, **kwargs: object) -> object:
        return (broken,) if kwargs.get("group") == group else ()

    monkeypatch.setattr(importlib.metadata, "entry_points", _entry_points)

    diagnostics = _scan_registry(_REGISTRY_SCANS[group])

    assert any("broken" in diagnostic for diagnostic in diagnostics), (
        f"{group} load failure left no diagnostic: {diagnostics}"
    )


@pytest.mark.parametrize("group", sorted(_REGISTRY_SCANS))
def test_a_clean_scan_leaves_no_diagnostics(group: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """The surface has to stay quiet when nothing is wrong to be worth reading."""

    def _entry_points(*_args: object, **_kwargs: object) -> object:
        return ()

    monkeypatch.setattr(importlib.metadata, "entry_points", _entry_points)

    assert _scan_registry(_REGISTRY_SCANS[group]) == []
