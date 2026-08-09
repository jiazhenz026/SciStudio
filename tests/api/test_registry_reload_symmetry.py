"""Reload symmetry — every invalidating event refreshes every registry.

ADR-053 ``docs/specs/adr-053-personal-tool-library.md`` §10.4 (FR-062 to FR-065),
issue #2021, plus issue #2009 for the previewer half.

``refresh_block_registry`` used to be called alone from five sites — the
branch-switch route and the four package install/update/rollback/delete routes —
while the type registry and the previewer registry were rebuilt only on project
switch and at startup. A package that shipped types or previewers, and a branch
that changed ``<project>/types/`` or ``<project>/previewers/``, produced no
error and no hint: the new items simply were not there until the user happened
to switch projects.

The tests below pin the five halves of the fix: the FR-062 audit result (no
route reaches an individual registry any more), the three ``hot_reload()``
invalidation events, FR-063 + #2009 at package install, FR-064 + #2009 at
branch switch, and the FR-065 entry point that a user library write calls.

The ``hot_reload()`` group is the #2022 audit finding. FR-062 is written in
terms of *events* that invalidate the registry, but the original audit
enumerated ``refresh_block_registry`` call sites, so three events that rebuild
the block registry a different way — the palette Reload button, the file-save
hook, and the MCP ``reload_blocks`` tool — were never evaluated against the
type registry. The most visible consequence was that saving a file under
``{project}/types/`` refreshed nothing at all: the save hook's gate named only
``blocks``. They are pinned here behaviourally — write a type, trigger the
event, resolve the type — because the original regression test asserted
coverage by grepping route sources for three literal method names and
structurally could not see ``registry.hot_reload()``.
"""

from __future__ import annotations

import importlib.metadata
import sys
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scistudio.api.routes import packages as package_routes
from scistudio.api.runtime import ApiRuntime
from scistudio.core.types.base import DataObject
from scistudio.desktop.package_installer import LocalPackageInstallResult
from scistudio.previewers.models import OwnerKind, PreviewerSpec

PROBE_MODULE = "scistudio_reload_probe"
PROBE_PREVIEWER_ID = "probe.package.viewer"
PROJECT_PREVIEWER_ID = "probe.project.viewer"

_PROJECT_TYPE_MODULE = '''
from scistudio.core.types.base import DataObject


class BranchOnlyType(DataObject):
    """Project-tier drop-in type that exists only on the feature branch."""
'''

_PROJECT_PREVIEWER_MODULE = f'''
from scistudio.previewers.models import OwnerKind, PreviewerSpec


def get_previewers():
    return [
        PreviewerSpec(
            previewer_id="{PROJECT_PREVIEWER_ID}",
            owner_kind=OwnerKind.PROJECT,
            owner_name="probe-project",
            target_type="BranchOnlyType",
        )
    ]
'''


class PackageProbeType(DataObject):
    """Stand-in for a ``DataObject`` shipped by an installed package."""


def _type_names(runtime: ApiRuntime) -> set[str]:
    return set(runtime.type_registry.all_types())


def _previewer_ids(runtime: ApiRuntime) -> set[str]:
    return {spec.previewer_id for spec in runtime.get_preview_service().registry.all_specs()}


def _install_package_entry_points(monkeypatch: pytest.MonkeyPatch) -> None:
    """Publish a fake installed package shipping one type and one previewer.

    Entry points are how a package ships both, so injecting them is the
    package tier as the registries actually see it. The injection happens
    after the fixtures' startup scan, which is what makes "discoverable
    without a project switch" a real assertion rather than a tautology.
    """
    module = types.ModuleType(PROBE_MODULE)
    module.get_types = lambda: [PackageProbeType]  # type: ignore[attr-defined]
    module.get_previewers = lambda: [  # type: ignore[attr-defined]
        PreviewerSpec(
            previewer_id=PROBE_PREVIEWER_ID,
            owner_kind=OwnerKind.PACKAGE,
            owner_name=PROBE_MODULE,
            target_type=PackageProbeType.__name__,
        )
    ]
    monkeypatch.setitem(sys.modules, PROBE_MODULE, module)

    injected = {
        group: (importlib.metadata.EntryPoint(name="probe", value=f"{PROBE_MODULE}:{attr}", group=group),)
        for group, attr in (("scistudio.types", "get_types"), ("scistudio.previewers", "get_previewers"))
    }
    real_entry_points = importlib.metadata.entry_points

    def _entry_points(*args: object, **kwargs: object) -> object:
        group = kwargs.get("group")
        if isinstance(group, str) and group in injected:
            return injected[group]
        return real_entry_points(*args, **kwargs)

    monkeypatch.setattr(importlib.metadata, "entry_points", _entry_points)


def _fake_local_install(monkeypatch: pytest.MonkeyPatch, install_path: Path) -> None:
    def _install(path: str, **_kwargs: object) -> LocalPackageInstallResult:
        return LocalPackageInstallResult(
            package_name="scistudio-blocks-probe",
            version="0.1.0",
            install_path=install_path,
            source_path=Path(path),
            modules=(PROBE_MODULE,),
            manifest_path=install_path / "scistudio-local-package.json",
            replaced=False,
        )

    monkeypatch.setattr(package_routes, "install_local_package", _install)


def _write_project_dropins(project_dir: Path) -> None:
    for child, name, body in (
        ("types", "branch_only_type.py", _PROJECT_TYPE_MODULE),
        ("previewers", "branch_only_previewer.py", _PROJECT_PREVIEWER_MODULE),
    ):
        target = project_dir / child
        target.mkdir(parents=True, exist_ok=True)
        (target / name).write_text(body, encoding="utf-8")


def _commit(client: TestClient, message: str) -> None:
    if client.get("/api/git/status").json()["dirty"]:
        assert client.post("/api/git/commit", json={"message": message}).status_code == 200


def _switch(client: TestClient, branch: str) -> None:
    response = client.post("/api/git/branch/switch", json={"branch_name": branch})
    assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# FR-062 — the audit result, pinned
# ---------------------------------------------------------------------------


def test_no_route_names_a_single_registry_refresh_method() -> None:
    """No route under ``api/routes`` names one refresh method (FR-062).

    A source-level rule, and only that: it stops a new route from writing
    ``runtime.refresh_block_registry()`` instead of the unified entry point,
    including in the user library write endpoint Track B adds next (#1996).

    It is deliberately *not* evidence that every invalidating event is
    covered — it cannot see ``registry.hot_reload()``, which is how three of
    them invalidated the registry until #2022. The event coverage is the
    behavioural tests below; this one guards the naming.
    """
    from scistudio.api import routes

    single_registry_calls = {"refresh_block_registry(", "refresh_type_registry(", "refresh_preview_service("}
    offenders = {
        path.name: sorted(call for call in single_registry_calls if call in path.read_text(encoding="utf-8"))
        for path in sorted(Path(routes.__file__).parent.glob("*.py"))
    }
    offenders = {name: calls for name, calls in offenders.items() if calls}
    assert not offenders, (
        f"api/routes must call runtime.refresh_all_registries() rather than one registry at a time: {offenders}"
    )


def test_refresh_all_registries_is_bound_on_the_runtime() -> None:
    """The FR-065 entry point exists on ``ApiRuntime`` and covers all three."""
    assert callable(ApiRuntime.refresh_all_registries)


# ---------------------------------------------------------------------------
# FR-062 — the three ``hot_reload()`` invalidation events (#2022)
# ---------------------------------------------------------------------------

_LATE_TYPE_MODULE = _PROJECT_TYPE_MODULE.replace("BranchOnlyType", "LateType")


def _write_project_type(project_dir: Path) -> None:
    """Write a project-tier type the startup scan cannot have seen."""
    types_dir = project_dir / "types"
    types_dir.mkdir(parents=True, exist_ok=True)
    (types_dir / "late_type.py").write_text(_LATE_TYPE_MODULE, encoding="utf-8")


def test_palette_reload_button_refreshes_the_type_registry(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """``POST /api/blocks/reload`` is an invalidating event, so it refreshes all.

    A user who edits ``{project}/types/spectrum.py`` and presses Reload used to
    get a fresh block registry and a stale type registry.
    """
    _write_project_type(opened_project)
    assert "LateType" not in _type_names(runtime)

    assert client.post("/api/blocks/reload").status_code == 200

    assert "LateType" in _type_names(runtime)


def test_saving_a_project_type_file_refreshes_the_type_registry(
    client: TestClient,
    runtime: ApiRuntime,
    project_parent: Path,
) -> None:
    """Saving ``types/*.py`` through the editor makes the type resolvable.

    The save hook was gated on ``<project>/blocks``, so this path refreshed
    nothing at all — the same user-visible failure FR-063 argues for fixing,
    on a path the user hits far more often than package install.
    """
    created = client.post(
        "/api/projects/",
        json={"name": "TypeSave", "description": "", "path": str(project_parent)},
    )
    assert created.status_code == 200, created.text
    project_id = created.json()["id"]

    assert "LateType" not in _type_names(runtime)

    saved = client.put(
        f"/api/projects/{project_id}/file?path=types/late_type.py",
        json={"content": _LATE_TYPE_MODULE},
    )
    assert saved.status_code == 200, saved.text

    assert "LateType" in _type_names(runtime)
    assert runtime.type_registry.resolve("LateType").name == "LateType"


def test_mcp_reload_blocks_refreshes_the_type_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The agent's own reload keeps its type registry current too.

    This path matters more since FR-059: the agent now *has* a populated type
    registry, so it now has one that can go stale. The tool holds an
    ``MCPContext`` rather than an ``ApiRuntime``, so it refreshes both
    registries in place instead of calling ``refresh_all_registries()``.
    """
    import asyncio

    from scistudio.ai.agent.mcp import _context, tools_authoring
    from scistudio.ai.agent.mcp.runtime import make_mcp_runtime

    fake_home = tmp_path / "home"
    (fake_home / ".scistudio").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))

    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    ctx = make_mcp_runtime(project_dir)
    _context.set_context(ctx)
    try:
        assert "LateType" not in ctx.type_registry.all_types()

        _write_project_type(project_dir)
        asyncio.run(tools_authoring.reload_blocks())

        assert "LateType" in ctx.type_registry.all_types()
    finally:
        _context.set_context(None)


# ---------------------------------------------------------------------------
# FR-063 + #2009 — package install
# ---------------------------------------------------------------------------


def test_package_install_refreshes_type_and_previewer_registries(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Installing a package makes its types and previewers usable at once.

    FR-063 for the type half and #2009 for the previewer half: before the fix
    the install route rebuilt only the block registry, so both stayed
    undiscovered until the next project switch.
    """
    monkeypatch.setenv("SCISTUDIO_BUNDLED", "1")
    _fake_local_install(monkeypatch, tmp_path / "installed" / "probe-0.1.0")
    _install_package_entry_points(monkeypatch)

    assert PackageProbeType.__name__ not in _type_names(runtime)
    assert PROBE_PREVIEWER_ID not in _previewer_ids(runtime)

    response = client.post("/api/packages/local", json={"path": str(tmp_path / "probe.whl")})
    assert response.status_code == 200, response.text

    assert PackageProbeType.__name__ in _type_names(runtime)
    assert PROBE_PREVIEWER_ID in _previewer_ids(runtime)


@pytest.mark.parametrize(
    ("method", "url", "manager_attr"),
    [
        ("post", "/api/packages/probe/update", "update_package"),
        ("post", "/api/packages/probe/rollback", "rollback_package"),
        ("delete", "/api/packages/probe", "delete_package"),
    ],
)
def test_package_lifecycle_routes_refresh_every_registry(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    url: str,
    manager_attr: str,
) -> None:
    """Update, rollback, and uninstall re-discover types and previewers too.

    All three move package code on disk exactly as an install does, so all
    three are FR-063 sites; uninstall is named in the FR explicitly.
    """
    from scistudio.desktop import package_manager

    monkeypatch.setenv("SCISTUDIO_BUNDLED", "1")
    monkeypatch.setattr(
        package_manager,
        manager_attr,
        lambda name, **_kwargs: package_manager.PackageActionResult(
            package_name=name, version="1.0.0", action="probe", previous_version="0.9.0"
        ),
    )
    _install_package_entry_points(monkeypatch)

    assert PackageProbeType.__name__ not in _type_names(runtime)
    assert PROBE_PREVIEWER_ID not in _previewer_ids(runtime)

    assert getattr(client, method)(url).status_code == 200

    assert PackageProbeType.__name__ in _type_names(runtime)
    assert PROBE_PREVIEWER_ID in _previewer_ids(runtime)


# ---------------------------------------------------------------------------
# FR-064 + #2009 — branch switch
# ---------------------------------------------------------------------------


def test_branch_switch_refreshes_project_types_and_previewers(
    client: TestClient,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """A branch that changes ``types/`` or ``previewers/`` is picked up.

    FR-064 and #2009: a branch rewrites those directories exactly as it
    rewrites ``blocks/``, and until now only the blocks half was rebuilt.
    """
    _commit(client, "drain")
    assert client.post("/api/git/branch/create", json={"name": "feature"}).status_code == 200
    _switch(client, "feature")
    _write_project_dropins(opened_project)
    _commit(client, "add project type and previewer")

    _switch(client, "main")
    assert "BranchOnlyType" not in _type_names(runtime)
    assert PROJECT_PREVIEWER_ID not in _previewer_ids(runtime)

    _switch(client, "feature")
    assert "BranchOnlyType" in _type_names(runtime)
    assert PROJECT_PREVIEWER_ID in _previewer_ids(runtime)


# ---------------------------------------------------------------------------
# FR-065 — the entry point a user library write calls
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# ADR-053 (Learning Center) FR-031 — the refresh path reaches every live group
# ---------------------------------------------------------------------------

#: Which registry a live entry-point group is refreshed through.
#:
#: The tests above are written per registry kind, in paired assertions; this
#: map is the same claim stated once against the live group set, so a group
#: added to :data:`~scistudio.core.entry_points.LIVE_ENTRY_POINT_GROUPS`
#: cannot quietly sit outside the refresh path.
#:
#: TODO(#2057): ``scistudio.tutorials`` has no discovery surface on this branch
#:   — the Learning Center runtime is built on top of the entry-point contract
#:   rather than before it — so it has no row here yet. The tutorials agent
#:   must add tutorial discovery to ``ApiRuntime.refresh_all_registries`` and
#:   list it below, so package install, package uninstall, and branch switch
#:   reach the tutorial catalogue like every other group (ADR-053 FR-031).
#:   Followup: https://github.com/jiazhenz026/SciStudio/issues/2057
_GROUP_REFRESH_SITES: dict[str, str] = {
    "scistudio.blocks": "block_registry",
    "scistudio.types": "type_registry",
    "scistudio.previewers": "preview_service",
}


def test_the_refresh_map_covers_every_live_entry_point_group() -> None:
    """FR-031: exactly one group is still outside the refresh path, and it is tracked.

    This fails the moment tutorial discovery lands, which is the intent: the
    map is how refresh coverage is claimed, so a new group must either join it
    or be argued about, never be forgotten.
    """
    from scistudio.core.entry_points import LIVE_ENTRY_POINT_GROUPS, TUTORIALS_ENTRY_POINT_GROUP

    uncovered = frozenset(LIVE_ENTRY_POINT_GROUPS) - set(_GROUP_REFRESH_SITES)

    assert uncovered == frozenset({TUTORIALS_ENTRY_POINT_GROUP}), (
        "update _GROUP_REFRESH_SITES and the TODO(#2057) above when a group joins or leaves the refresh path"
    )


@pytest.mark.parametrize("group", sorted(_GROUP_REFRESH_SITES))
def test_refresh_all_registries_rebuilds_the_registry_behind_every_group(
    group: str,
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """Every mapped group's registry is a different object after a refresh.

    The behavioural tests above pin the user-visible half — a type or previewer
    that was not there before the event is there afterwards. This pins the
    structural half for every group at once, so a registry that
    ``refresh_all_registries`` stopped rebuilding is caught even when no test
    happens to ship a package for that group.
    """
    attribute = _GROUP_REFRESH_SITES[group]
    before = getattr(runtime, attribute) if attribute != "preview_service" else runtime.get_preview_service()

    runtime.refresh_all_registries()

    after = getattr(runtime, attribute) if attribute != "preview_service" else runtime.get_preview_service()
    assert after is not before, f"{group} was not rebuilt by refresh_all_registries()"


def test_refresh_all_registries_picks_up_a_user_library_write(
    runtime: ApiRuntime,
    opened_project: Path,
) -> None:
    """A type written into the user library is visible without a restart.

    FR-065's in-process half: whichever request handler performs the write
    (the Track B endpoint, #1996) calls this one entry point and the palette
    reads a rebuilt registry. The cross-process half — a standalone
    ``scistudio mcp-bridge`` holding its own registries — needs an
    invalidation channel that does not exist yet.
    """
    user_types = Path.home() / ".scistudio" / "types"
    user_types.mkdir(parents=True, exist_ok=True)
    (user_types / "promoted_type.py").write_text(
        _PROJECT_TYPE_MODULE.replace("BranchOnlyType", "PromotedType"), encoding="utf-8"
    )

    assert "PromotedType" not in _type_names(runtime)
    runtime.refresh_all_registries()
    assert "PromotedType" in _type_names(runtime)
