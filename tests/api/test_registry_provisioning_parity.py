"""Drop-in provisioning parity across the four registration points.

ADR-053 / ``docs/specs/adr-053-personal-tool-library.md`` §10.3, FR-057 to
FR-061. §2.6 recorded the same semantic — "which drop-in directories does this
process see?" — written out four times with no two copies agreeing. These tests
pin the consolidated behaviour so it cannot drift apart again:

* the API runtime (``scistudio.api.runtime._projects``),
* the agent runtime (``scistudio.ai.agent.mcp.runtime``),
* worker-side type reconstruction (``scistudio.core.types.serialization``),
* IO dispatch (``scistudio.blocks.io._unified_dispatch``)

must resolve identical drop-in directories and identical import roots for a
given project context (FR-057, FR-058); the user tier must be discovered with
no project open and the project tier must not be (FR-060); the agent runtime
must register type directories at all (FR-059); and the two registries' scan
orders and duplicate policies must stay as recorded (FR-061).
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from typing import Any

import pytest

from scistudio.core import dropins

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _RecordingRegistry:
    """Stand-in registry that records ``add_scan_dir`` and skips real scanning.

    Satisfies both the :class:`~scistudio.blocks.registry.BlockRegistry` and
    the :class:`~scistudio.core.types.registry.TypeRegistry` surfaces the four
    registration points touch, so each site can be observed without paying for
    entry-point discovery or executing drop-in modules.
    """

    def __init__(self) -> None:
        self.scan_dirs: list[Path] = []
        self.scanned: list[str] = []

    def add_scan_dir(self, directory: str | Path) -> None:
        self.scan_dirs.append(Path(directory))

    # BlockRegistry surface
    def scan(self) -> None:
        self.scanned.append("scan")

    # TypeRegistry surface
    def scan_all(self) -> None:
        self.scanned.append("scan_all")

    def scan_builtins(self) -> None:
        self.scanned.append("scan_builtins")

    def _scan_entrypoint_types(self) -> None:
        self.scanned.append("entry_point")

    def _scan_package_src_dirs(self) -> None:
        self.scanned.append("package_src")

    def _scan_filesystem_dirs(self) -> None:
        self.scanned.append("dropin")


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``Path.home()`` at an isolated directory for the user tier."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    return fake_home


@pytest.fixture
def project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "proj"
    (project_dir / "blocks").mkdir(parents=True)
    (project_dir / "types").mkdir(parents=True)
    return project_dir


@pytest.fixture
def recorders(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[_RecordingRegistry]]:
    """Replace both registry classes everywhere the four sites import them."""
    made: dict[str, list[_RecordingRegistry]] = {"block": [], "type": []}

    def _make_block() -> _RecordingRegistry:
        registry = _RecordingRegistry()
        made["block"].append(registry)
        return registry

    def _make_type() -> _RecordingRegistry:
        registry = _RecordingRegistry()
        made["type"].append(registry)
        return registry

    # The API runtime binds both names at module import; the agent runtime,
    # worker reconstruction, and IO dispatch import them lazily inside the
    # function body, so the source modules are patched too.
    monkeypatch.setattr("scistudio.blocks.registry.BlockRegistry", _make_block)
    monkeypatch.setattr("scistudio.core.types.registry.TypeRegistry", _make_type)
    monkeypatch.setattr("scistudio.api.runtime._projects.BlockRegistry", _make_block)
    monkeypatch.setattr("scistudio.api.runtime._projects.TypeRegistry", _make_type)
    return made


def _api_runtime_stub(project_dir: Path | None) -> Any:
    """Minimal ``ApiRuntime`` surface for the two refresh free functions."""
    active = None if project_dir is None else types.SimpleNamespace(path=str(project_dir))
    return types.SimpleNamespace(active_project=active, block_registry=None, type_registry=None)


def _api_block_dirs(project_dir: Path | None) -> list[Path]:
    from scistudio.api.runtime import _projects

    runtime = _api_runtime_stub(project_dir)
    _projects.refresh_block_registry(runtime)
    return list(runtime.block_registry.scan_dirs)


def _api_type_dirs(project_dir: Path | None) -> list[Path]:
    from scistudio.api.runtime import _projects

    runtime = _api_runtime_stub(project_dir)
    _projects.refresh_type_registry(runtime)
    return list(runtime.type_registry.scan_dirs)


def _recorded_dirs(registry: Any) -> list[Path]:
    """Read back what a :class:`_RecordingRegistry` was asked to scan."""
    return list(registry.scan_dirs)


def _agent_block_dirs(project_dir: Path | None) -> list[Path]:
    from scistudio.ai.agent.mcp import runtime as agent_runtime

    return _recorded_dirs(agent_runtime._build_block_registry(project_dir))


def _agent_type_dirs(project_dir: Path | None) -> list[Path]:
    from scistudio.ai.agent.mcp import runtime as agent_runtime

    return _recorded_dirs(agent_runtime._build_type_registry(project_dir))


def _worker_type_dirs(project_dir: Path | None, monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    from scistudio.core.types import serialization

    monkeypatch.setattr(serialization, "_registry_instance", None)
    _set_project_env(project_dir, monkeypatch)
    return _recorded_dirs(serialization._get_type_registry())


def _dispatch_block_dirs(project_dir: Path | None, monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    from scistudio.blocks.io import _unified_dispatch

    _set_project_env(project_dir, monkeypatch)
    return _recorded_dirs(_unified_dispatch.runtime_block_registry())


def _dispatch_type_dirs(project_dir: Path | None, monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    from scistudio.blocks.io import _unified_dispatch

    _set_project_env(project_dir, monkeypatch)
    return _recorded_dirs(_unified_dispatch.runtime_type_registry())


def _set_project_env(project_dir: Path | None, monkeypatch: pytest.MonkeyPatch) -> None:
    if project_dir is None:
        monkeypatch.delenv(dropins.PROJECT_DIR_ENV_VAR, raising=False)
    else:
        monkeypatch.setenv(dropins.PROJECT_DIR_ENV_VAR, str(project_dir))


# ---------------------------------------------------------------------------
# FR-057 / FR-058 — one answer per tier, shared by every registration point
# ---------------------------------------------------------------------------


def test_block_scan_dirs_agree_across_registration_points(
    home: Path,
    project: Path,
    recorders: dict[str, list[_RecordingRegistry]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The three block-registering sites resolve the same directories (FR-057).

    Worker-side reconstruction registers no block directory at all (§2.6), so
    it is absent here by design.
    """
    expected = [project / "blocks", home / ".scistudio" / "blocks"]

    assert list(dropins.block_scan_dirs(project)) == expected
    assert _api_block_dirs(project) == expected
    assert _agent_block_dirs(project) == expected
    assert _dispatch_block_dirs(project, monkeypatch) == expected


def test_type_scan_dirs_agree_across_registration_points(
    home: Path,
    project: Path,
    recorders: dict[str, list[_RecordingRegistry]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All four type-registering sites resolve the same directories (FR-057)."""
    expected = [project / "types", home / ".scistudio" / "types"]

    assert list(dropins.type_scan_dirs(project)) == expected
    assert _api_type_dirs(project) == expected
    assert _agent_type_dirs(project) == expected
    assert _worker_type_dirs(project, monkeypatch) == expected
    assert _dispatch_type_dirs(project, monkeypatch) == expected


def test_blocks_and_types_share_one_user_tier_definition(home: Path, project: Path) -> None:
    """FR-058: exactly one answer to "where does the user tier live"."""
    assert dropins.user_library_dir() == home / ".scistudio"
    assert dropins.user_blocks_dir() == dropins.user_library_dir() / "blocks"
    assert dropins.user_types_dir() == dropins.user_library_dir() / "types"
    assert dropins.project_blocks_dir(project) == project / "blocks"
    assert dropins.project_types_dir(project) == project / "types"


def test_dropin_import_roots_are_one_answer_for_every_site(
    home: Path,
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-057: no call site decides which roots go on ``sys.path``.

    The roots are the project types dir, the user types dir, and the shared
    user dependency site — in that order, so a project type shadows a
    user-library type of the same module name.
    """
    user_site = home / "user-site"
    monkeypatch.setattr(dropins, "user_python_import_roots", lambda: [user_site])

    assert list(dropins.dropin_import_roots(project)) == [
        project / "types",
        home / ".scistudio" / "types",
        user_site,
    ]
    # The type scan dirs are a prefix of the import roots: the same tier
    # definition drives discovery and import resolution.
    assert list(dropins.dropin_import_roots(project))[:2] == list(dropins.type_scan_dirs(project))


# ---------------------------------------------------------------------------
# FR-060 — the user tier does not depend on an active project
# ---------------------------------------------------------------------------


def test_user_tier_is_discovered_with_no_project_at_every_site(
    home: Path,
    recorders: dict[str, list[_RecordingRegistry]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-060: user tier present, project tier absent, at all four sites."""
    user_blocks = home / ".scistudio" / "blocks"
    user_types = home / ".scistudio" / "types"

    assert _api_block_dirs(None) == [user_blocks]
    assert _agent_block_dirs(None) == [user_blocks]
    assert _dispatch_block_dirs(None, monkeypatch) == [user_blocks]

    assert _api_type_dirs(None) == [user_types]
    assert _agent_type_dirs(None) == [user_types]
    assert _worker_type_dirs(None, monkeypatch) == [user_types]
    assert _dispatch_type_dirs(None, monkeypatch) == [user_types]


def test_project_tier_requires_a_project(home: Path) -> None:
    """FR-060: project-tier discovery still needs a project directory."""
    assert list(dropins.block_scan_dirs(None)) == [dropins.user_blocks_dir()]
    assert list(dropins.type_scan_dirs(None)) == [dropins.user_types_dir()]
    assert list(dropins.dropin_import_roots(None))[:1] == [dropins.user_types_dir()]


def test_project_dir_from_env_declares_the_project_context(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The two env-driven sites read one contract, including the blank case."""
    monkeypatch.setenv(dropins.PROJECT_DIR_ENV_VAR, str(project))
    assert dropins.project_dir_from_env() == project

    monkeypatch.setenv(dropins.PROJECT_DIR_ENV_VAR, "   ")
    assert dropins.project_dir_from_env() is None

    monkeypatch.delenv(dropins.PROJECT_DIR_ENV_VAR, raising=False)
    assert dropins.project_dir_from_env() is None


# ---------------------------------------------------------------------------
# FR-059 — the agent runtime sees drop-in types
# ---------------------------------------------------------------------------


def test_agent_runtime_registers_type_directories(
    home: Path,
    project: Path,
    recorders: dict[str, list[_RecordingRegistry]],
) -> None:
    """FR-059: ``make_mcp_runtime`` wires both type tiers, not zero of them."""
    from scistudio.ai.agent.mcp import runtime as agent_runtime

    mcp_runtime = agent_runtime.make_mcp_runtime(project)
    type_registry: Any = mcp_runtime.type_registry

    assert _recorded_dirs(type_registry) == [
        project / "types",
        home / ".scistudio" / "types",
    ]
    assert _recorded_dirs(mcp_runtime.block_registry) == [
        project / "blocks",
        home / ".scistudio" / "blocks",
    ]
    assert type_registry.scanned == ["scan_all"]


# ---------------------------------------------------------------------------
# FR-061 — the two scan orders and their duplicate policies
# ---------------------------------------------------------------------------


def test_type_registry_scan_order_is_unchanged() -> None:
    """FR-061: builtins -> entry-point -> package-src -> drop-in."""
    from scistudio.core.types.registry import TypeRegistry

    calls: list[str] = []

    class _Recording(TypeRegistry):
        def scan_builtins(self) -> None:
            calls.append("builtins")

        def _scan_entrypoint_types(self) -> None:
            calls.append("entry_point")

        def _scan_package_src_dirs(self) -> None:
            calls.append("package_src")

        def _scan_filesystem_dirs(self) -> None:
            calls.append("dropin")

    _Recording().scan_all()
    assert calls == ["builtins", "entry_point", "package_src", "dropin"]


def test_block_registry_scan_order_is_unchanged() -> None:
    """FR-061: builtins -> drop-in -> entry-point -> package-src."""
    from scistudio.blocks.registry import BlockRegistry

    calls: list[str] = []

    class _Recording(BlockRegistry):
        def _scan_builtins(self) -> None:
            calls.append("builtins")

        def _scan_tier1(self) -> None:
            calls.append("dropin")

        def _scan_tier2(self) -> None:
            calls.append("entry_point")

        def _scan_package_src_dirs(self) -> None:
            calls.append("package_src")

    _Recording().scan()
    assert calls == ["builtins", "dropin", "entry_point", "package_src"]


def test_dropin_type_cannot_shadow_a_core_type(tmp_path: Path) -> None:
    """FR-061: the type drop-in tier is skip-if-present, so core names win.

    Worker-side reconstruction resolves a serialised ``type_chain`` by name,
    so a drop-in shadowing ``Array`` would change what persisted artifacts
    deserialise to in one process and not another.
    """
    from scistudio.core.types.registry import TypeRegistry

    types_dir = tmp_path / "types"
    types_dir.mkdir()
    (types_dir / "shadow.py").write_text(
        "from scistudio.core.types.base import DataObject\n"
        "\n"
        "\n"
        "class Array(DataObject):\n"
        '    """Drop-in trying to shadow the core Array."""\n',
        encoding="utf-8",
    )

    registry = TypeRegistry()
    registry.add_scan_dir(types_dir)
    registry.scan_builtins()
    registry._scan_filesystem_dirs()

    assert registry.resolve("Array").module_path == "scistudio.core.types.array"


# ---------------------------------------------------------------------------
# ADR-053 (Learning Center) FR-030 / FR-031 — the entry-point half
#
# The drop-in half above answers "which directories does this process see?".
# The same question has a second half — "which import roots does an
# entry-point scan see?" — that was answered by the previewer registry alone.
# A package's ``site-packages`` carries the ``dist-info`` that makes its entry
# points visible at all, so a group scanned without those roots reports the
# package as absent. The observable consequence was a package that resolved
# for previewers and vanished for blocks (#1752).
# ---------------------------------------------------------------------------


def _entry_point_visible_only_with(sentinel: str, group: str, ep: Any) -> Any:
    """Metadata that appears only while *sentinel* is on ``sys.path``.

    Mirrors a packaged install: the plugin's ``dist-info`` is unreadable until
    its root is activated, so a scan that skips the activation finds nothing
    and reports no error.
    """

    def _entry_points(*_args: object, **kwargs: object) -> object:
        if kwargs.get("group") != group:
            return ()
        return (ep,) if sentinel in sys.path else ()

    return _entry_points


@pytest.mark.parametrize("kind", ["blocks", "types", "previewers"])
def test_every_entry_point_scan_activates_the_plugin_import_roots(
    kind: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-030: one answer to "which import roots does a scan run under".

    Written per site, like the drop-in assertions above, because that is what
    makes divergence visible: each scan is run against metadata that only
    exists while the plugin root is active, so a scan that forgot the
    activation returns an empty group rather than failing loudly.

    TODO(#2057): ``scistudio.tutorials`` has no registry on this branch, so its
      scan cannot be listed here yet. The tutorials agent must add its
      discovery pass to this parametrisation once
      ``scistudio.tutorials.discovery`` exists, per ADR-053 FR-030/FR-031.
      Followup: https://github.com/jiazhenz026/SciStudio/issues/2057
    """
    import importlib.metadata

    from scistudio.core import entry_points as shared

    sentinel = str(tmp_path)
    monkeypatch.setattr(shared, "installed_package_import_roots", lambda: [tmp_path])

    seen: list[str] = []

    class _Probe:
        """Records that the scan reached the point of reading the payload."""

        def __call__(self) -> list[object]:
            seen.append(kind)
            return []

    group, scan = {
        "blocks": (shared.BLOCKS_ENTRY_POINT_GROUP, lambda: _run_block_entry_point_scan()),
        "types": (shared.TYPES_ENTRY_POINT_GROUP, lambda: _run_type_entry_point_scan()),
        "previewers": (shared.PREVIEWERS_ENTRY_POINT_GROUP, lambda: _run_previewer_entry_point_scan()),
    }[kind]

    ep = types.SimpleNamespace(
        name="probe",
        value="pkg_probe:contribute",
        group=group,
        load=lambda: _Probe(),
    )
    monkeypatch.setattr(
        importlib.metadata,
        "entry_points",
        _entry_point_visible_only_with(sentinel, group, ep),
    )

    scan()

    assert seen == [kind], (
        f"the {kind} entry-point scan did not run with the plugin import roots active, "
        "so an installed package's metadata was invisible to it"
    )


def _run_block_entry_point_scan() -> None:
    from scistudio.blocks.registry import BlockRegistry

    BlockRegistry()._scan_tier2()


def _run_type_entry_point_scan() -> None:
    from scistudio.core.types.registry import TypeRegistry

    TypeRegistry()._scan_entrypoint_types()


def _run_previewer_entry_point_scan() -> None:
    from scistudio.previewers.registry import PreviewerRegistry

    PreviewerRegistry().load_packages()


def test_plugin_import_roots_are_one_answer_for_every_group() -> None:
    """FR-030: no registry keeps its own copy of the resolution.

    The drop-in half of this file makes the same claim about
    :func:`scistudio.core.dropins.dropin_import_roots`; this is the
    entry-point half, and the two are deliberately separate answers because
    they cover different directories.
    """
    from scistudio.core import entry_points as shared
    from scistudio.desktop.paths import installed_package_import_roots

    assert tuple(installed_package_import_roots()) == shared.plugin_import_roots()


def test_dropin_block_overrides_a_builtin_of_the_same_name() -> None:
    """FR-061: the block drop-in tier registers unconditionally.

    The opposite policy to types, and deliberately so: replacing a shipped
    block for one project is the point of a project-local block file. This is
    why the two scan orders are recorded as separate rather than unified.
    """
    from scistudio.blocks.registry import BlockRegistry, BlockSpec

    registry = BlockRegistry()
    registry._register_spec(BlockSpec(name="Load", class_name="BuiltinLoad", source="builtin"))
    registry._register_spec(BlockSpec(name="Load", class_name="DropInLoad", source="tier1"))

    spec = registry.get_spec("Load")
    assert spec is not None
    assert spec.class_name == "DropInLoad"
    assert spec.source == "tier1"
