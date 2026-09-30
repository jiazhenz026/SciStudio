"""ADR-053 §5 (FR-012 through FR-016) — a drop-in block can import a drop-in type.

Spec §2.5 recorded the verified defect: ``{project}/types/spectrum.py`` defines
``SpectrumData``, ``{project}/blocks/uses_spectrum.py`` does
``from spectrum import SpectrumData``, and the block raises
``ModuleNotFoundError`` during the scan and then silently disappears from the
palette. Nothing but a server-side warning was left behind.

These tests pin the five obligations that end that:

* **FR-012** — the §2.5 reproduction registers.
* **FR-013** — a real worker subprocess runs the block, not just the parent
  registry, so the block cannot resolve at palette time and fail at run time.
* **FR-014** — a project type shadows a user-library type of the same file name.
* **FR-015** — a refused drop-in reaches ``GET /api/blocks/``.
* **FR-016** (spec §13 OQ-1, resolved as reject-with-error) — a type file whose
  stem collides with an importable top-level module is rejected: registration is
  refused, and the module it collides with still resolves to the installed
  package **in every process**, the worker subprocess included.

The FR-016 section carries two findings from the Track A audit (#2022). The
rejection used to be announced by the block scan and enforced nowhere else: the
type still registered in the ``TypeRegistry`` and still loaded, and the worker
— which never runs the block scan — got the drop-in file. Both are pinned
below against the surfaces that failed, a real ``TypeRegistry`` and a real
worker subprocess.

ADR-056 rewrote the mechanism under these scenarios (spec CHANGE-042): user
files are imported by their own module names from a user import path appended
to ``sys.path``, and the name check (FR-008) refuses a colliding file before
anything is imported. The refusing ``sys.meta_path`` finder, its warrants and
the ``sys.path`` windows are gone, so the scenarios that pinned them now pin
the plain-import answer: the installed module resolves because it comes first
on ``sys.path``, and a refusal lasts exactly as long as the file does.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scistudio.api.deps import get_block_registry
from scistudio.api.routes.blocks import router as blocks_router
from scistudio.blocks.registry import BlockRegistry
from scistudio.core.dropins import (
    block_scan_dirs,
    register_block_scan_dirs,
    register_type_scan_dirs,
    type_scan_dirs,
)
from scistudio.core.types.registry import TypeRegistry
from scistudio.core.user_code import build_user_import_path, check_user_import_path, install_user_import_path
from scistudio.desktop.paths import prepended_sys_paths
from scistudio.engine.runners.local import _worker_env
from scistudio.engine.runners.process_handle import build_worker_payload

#: ``error_type`` of a name-check refusal for a standard-library or installed
#: stem (ADR-056 FR-008).
COLLISION = "UserModuleNameCollision"

# ---------------------------------------------------------------------------
# Drop-in sources
# ---------------------------------------------------------------------------

SPECTRUM_TYPE = '''\
from scistudio.core.types.base import DataObject


class SpectrumData(DataObject):
    """Drop-in spectrum type from the ADR-053 §2.5 reproduction."""
'''

USES_SPECTRUM_BLOCK = """\
from typing import Any, ClassVar

from spectrum import SpectrumData

from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort


class UsesSpectrum(Block):
    type_name: ClassVar[str] = "test.uses_spectrum"
    name: ClassVar[str] = "uses_spectrum"
    base_category: ClassVar[str] = "process"
    subcategory: ClassVar[str] = "test"
    input_ports: ClassVar = [InputPort(name="data", accepted_types=[SpectrumData], required=False)]
    output_ports: ClassVar = [OutputPort(name="data", accepted_types=[SpectrumData])]

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        return {"data": SpectrumData.__name__}
"""

#: A block whose registered name reports which tier its type import resolved to.
TIER_PROBE_BLOCK = """\
from typing import Any, ClassVar

from shared_type import TIER

from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig


class TierProbe(Block):
    type_name: ClassVar[str] = "test.tier_probe"
    name: ClassVar[str] = "tier_probe_" + TIER
    base_category: ClassVar[str] = "process"
    subcategory: ClassVar[str] = "test"
    input_ports: ClassVar = []
    output_ports: ClassVar = []

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        return {}
"""

#: A block whose registered name reports whether ``sample_dep`` resolved to the
#: installed module or to the colliding drop-in type file (FR-016).
COLLISION_PROBE_BLOCK = """\
from typing import Any, ClassVar

import sample_dep

from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig


class CollisionProbe(Block):
    type_name: ClassVar[str] = "test.collision_probe"
    name: ClassVar[str] = "collision_probe_" + getattr(sample_dep, "ORIGIN", "shadowed")
    base_category: ClassVar[str] = "process"
    subcategory: ClassVar[str] = "test"
    input_ports: ClassVar = []
    output_ports: ClassVar = []

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        return {}
"""


#: A block that reports at *run* time — inside the worker — which ``sample_dep``
#: its import resolved to. The name is fixed, so registration cannot stand in
#: for execution the way ``CollisionProbe``'s class-name trick does.
WORKER_COLLISION_BLOCK = """\
from typing import Any, ClassVar

from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import OutputPort
from scistudio.core.types.base import DataObject


class WorkerCollisionProbe(Block):
    type_name: ClassVar[str] = "test.worker_collision_probe"
    name: ClassVar[str] = "worker_collision_probe"
    base_category: ClassVar[str] = "process"
    subcategory: ClassVar[str] = "test"
    input_ports: ClassVar = []
    output_ports: ClassVar = [OutputPort(name="origin", accepted_types=[DataObject])]

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        import sample_dep

        return {"origin": getattr(sample_dep, "ORIGIN", "SHADOWED-BY-TYPE-FILE")}
"""

#: A drop-in type file that also declares a ``DataObject``, so the FR-016
#: refusal has something to refuse rather than only something to report.
SHADOWED_TYPE = '''\
from scistudio.core.types.base import DataObject


class ShadowedType(DataObject):
    """Declared in a file whose name collides with an installed module."""
'''


#: A block whose registered name is the one thing that varies, so two bodies of
#: identical length can declare two different blocks — the shape a same-second,
#: same-size edit takes.
_NAMED_PROBE_BLOCK = """\
from typing import Any, ClassVar

from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig


class NamedProbe(Block):
    type_name: ClassVar[str] = "test.named_probe"
    name: ClassVar[str] = "{name}"
    base_category: ClassVar[str] = "process"
    subcategory: ClassVar[str] = "test"
    input_ports: ClassVar = []
    output_ports: ClassVar = []

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        return {{}}
"""


def _named_probe_block(name: str) -> str:
    return _NAMED_PROBE_BLOCK.format(name=name)


def _shared_type(tier: str) -> str:
    return (
        "from scistudio.core.types.base import DataObject\n"
        "\n"
        f'TIER = "{tier}"\n'
        "\n"
        "\n"
        "class SharedType(DataObject):\n"
        f'    """Drop-in type present in the {tier} tier."""\n'
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


#: Top-level names a drop-in type import binds in ``sys.modules``. They are the
#: file stems, so they would leak into unrelated tests in the same session.
_DROPIN_MODULE_NAMES = ("spectrum", "shared_type", "sample_dep", "_sample_dep")


@pytest.fixture(autouse=True)
def _drop_dropin_modules() -> Iterator[None]:
    yield
    for name in _DROPIN_MODULE_NAMES:
        sys.modules.pop(name, None)


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``Path.home()`` at an isolated user library for the user tier."""
    fake_home = tmp_path / "home"
    (fake_home / ".scistudio" / "types").mkdir(parents=True)
    (fake_home / ".scistudio" / "blocks").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    return fake_home


@pytest.fixture
def project(tmp_path: Path) -> Path:
    project_dir = tmp_path / "proj"
    (project_dir / "blocks").mkdir(parents=True)
    (project_dir / "types").mkdir(parents=True)
    return project_dir


def _scanned_registry(project_dir: Path) -> BlockRegistry:
    """Scan the way :func:`refresh_block_registry` does (ADR-053 FR-057).

    The backend installs the project's user import path first (ADR-056).
    """
    install_user_import_path(build_user_import_path(project_dir))
    registry = BlockRegistry()
    register_block_scan_dirs(registry, project_dir)
    registry.scan()
    return registry


# ---------------------------------------------------------------------------
# FR-012 — the §2.5 reproduction registers
# ---------------------------------------------------------------------------


class TestDropInBlockImportsDropInType:
    def test_spec_2_5_reproduction_now_registers(self, home: Path, project: Path) -> None:
        """``from spectrum import SpectrumData`` resolves ``<project>/types``."""
        (project / "types" / "spectrum.py").write_text(SPECTRUM_TYPE, encoding="utf-8")
        (project / "blocks" / "uses_spectrum.py").write_text(USES_SPECTRUM_BLOCK, encoding="utf-8")

        registry = _scanned_registry(project)

        spec = registry.get_spec("uses_spectrum")
        assert spec is not None, "FR-012: the §2.5 drop-in block must register"
        assert spec.source == "tier1"
        assert registry.dropin_failures() == []

    def test_declared_port_types_are_the_dropin_class(self, home: Path, project: Path) -> None:
        """The port carries the real drop-in class, not a fallback."""
        (project / "types" / "spectrum.py").write_text(SPECTRUM_TYPE, encoding="utf-8")
        (project / "blocks" / "uses_spectrum.py").write_text(USES_SPECTRUM_BLOCK, encoding="utf-8")

        spec = _scanned_registry(project).get_spec("uses_spectrum")

        assert spec is not None
        assert [accepted.__name__ for accepted in spec.input_ports[0].accepted_types] == ["SpectrumData"]
        assert [accepted.__name__ for accepted in spec.output_ports[0].accepted_types] == ["SpectrumData"]

    def test_user_library_block_resolves_without_a_project(self, home: Path) -> None:
        """FR-060: the user tier resolves its own types with no project open."""
        user_library = home / ".scistudio"
        (user_library / "types" / "spectrum.py").write_text(SPECTRUM_TYPE, encoding="utf-8")
        (user_library / "blocks" / "uses_spectrum.py").write_text(USES_SPECTRUM_BLOCK, encoding="utf-8")

        registry = BlockRegistry()
        register_block_scan_dirs(registry, None)
        registry.scan()

        assert registry.get_spec("uses_spectrum") is not None


# ---------------------------------------------------------------------------
# FR-013 — worker parity
# ---------------------------------------------------------------------------


class TestWorkerParity:
    def test_spec_names_the_block_by_its_own_module_and_one_type_class(self, home: Path, project: Path) -> None:
        """ADR-056: the spec's module is the file stem; the port type is the registry's class."""
        (project / "types" / "spectrum.py").write_text(SPECTRUM_TYPE, encoding="utf-8")
        (project / "blocks" / "uses_spectrum.py").write_text(USES_SPECTRUM_BLOCK, encoding="utf-8")

        spec = _scanned_registry(project).get_spec("uses_spectrum")
        types = TypeRegistry()
        register_type_scan_dirs(types, project)
        types.scan_all()

        assert spec is not None
        assert spec.module_path == "uses_spectrum"
        assert not hasattr(spec, "runtime_import_roots") and not hasattr(spec, "file_path")
        assert spec.input_ports[0].accepted_types[0] is types.load_class("SpectrumData")

    def test_the_user_import_path_puts_the_project_tier_first(self, home: Path, project: Path) -> None:
        """FR-014 / ADR-056 FR-001: project types and blocks, then the library's."""
        library = home / ".scistudio"
        assert build_user_import_path(project) == (
            (project / "types").resolve(),
            (project / "blocks").resolve(),
            (library / "types").resolve(),
            (library / "blocks").resolve(),
        )

    def test_dropin_block_runs_in_a_fresh_worker(self, home: Path, project: Path) -> None:
        """FR-013: registering is not enough — the worker must run the block.

        Spawns a real ``python -m scistudio.engine.runners.worker``, which
        imports the block by module name through the user import path it
        receives in its environment. Without it the worker reproduces the
        original ``ModuleNotFoundError: No module named 'spectrum'``.
        """
        (project / "types" / "spectrum.py").write_text(SPECTRUM_TYPE, encoding="utf-8")
        (project / "blocks" / "uses_spectrum.py").write_text(USES_SPECTRUM_BLOCK, encoding="utf-8")

        spec = _scanned_registry(project).get_spec("uses_spectrum")
        assert spec is not None

        payload = build_worker_payload(
            block_class=f"{spec.module_path}.{spec.class_name}",
            inputs_refs={},
            config={},
            output_dir=None,
        )
        proc = subprocess.run(
            [sys.executable, "-m", "scistudio.engine.runners.worker"],
            input=payload,
            capture_output=True,
            timeout=120,
            env=_worker_env(worker_cwd=None, project_dir=str(project)),
        )

        stdout = proc.stdout.decode("utf-8", errors="replace")
        stderr = proc.stderr.decode("utf-8", errors="replace")
        assert proc.returncode == 0, f"Worker exited {proc.returncode}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
        result = json.loads(stdout)
        assert "error" not in result, f"Worker reported error: {result.get('error')}"
        assert result.get("outputs", {}).get("data") == "SpectrumData"


# ---------------------------------------------------------------------------
# FR-014 — project types shadow user types
# ---------------------------------------------------------------------------


class TestProjectTierShadowsUserTier:
    def test_project_type_wins_over_user_type_of_the_same_name(self, home: Path, project: Path) -> None:
        (project / "types" / "shared_type.py").write_text(_shared_type("project"), encoding="utf-8")
        (home / ".scistudio" / "types" / "shared_type.py").write_text(_shared_type("user"), encoding="utf-8")
        (project / "blocks" / "tier_probe.py").write_text(TIER_PROBE_BLOCK, encoding="utf-8")

        registry = _scanned_registry(project)

        assert registry.get_spec("tier_probe_project") is not None
        assert registry.get_spec("tier_probe_user") is None

    def test_user_type_is_used_when_the_project_has_none(self, home: Path, project: Path) -> None:
        (home / ".scistudio" / "types" / "shared_type.py").write_text(_shared_type("user"), encoding="utf-8")
        (project / "blocks" / "tier_probe.py").write_text(TIER_PROBE_BLOCK, encoding="utf-8")

        registry = _scanned_registry(project)

        assert registry.get_spec("tier_probe_user") is not None


# ---------------------------------------------------------------------------
# FR-015 — a refused drop-in reaches the user
# ---------------------------------------------------------------------------


def _palette_client(registry: BlockRegistry) -> TestClient:
    app = FastAPI()
    app.include_router(blocks_router)
    app.dependency_overrides[get_block_registry] = lambda: registry
    return TestClient(app)


class TestFailureSurfacing:
    def test_failed_import_is_recorded_on_the_registry(self, home: Path, project: Path) -> None:
        (project / "blocks" / "uses_spectrum.py").write_text(USES_SPECTRUM_BLOCK, encoding="utf-8")

        registry = _scanned_registry(project)

        assert registry.get_spec("uses_spectrum") is None
        failures = registry.dropin_failures()
        assert len(failures) == 1
        assert failures[0].file_path == str(project / "blocks" / "uses_spectrum.py")
        assert failures[0].error_type == "ModuleNotFoundError"
        assert "spectrum" in failures[0].message

    def test_failure_reaches_the_block_listing_endpoint(self, home: Path, project: Path) -> None:
        """FR-015: the palette already fetches this response, so failures ride it."""
        (project / "blocks" / "uses_spectrum.py").write_text(USES_SPECTRUM_BLOCK, encoding="utf-8")

        registry = _scanned_registry(project)
        payload = _palette_client(registry).get("/api/blocks/").json()

        reported = payload["dropin_failures"]
        assert len(reported) == 1
        assert reported[0]["file_path"] == str(project / "blocks" / "uses_spectrum.py")
        assert reported[0]["error_type"] == "ModuleNotFoundError"
        assert "spectrum" in reported[0]["message"]

    def test_healthy_scan_reports_no_failures(self, home: Path, project: Path) -> None:
        (project / "types" / "spectrum.py").write_text(SPECTRUM_TYPE, encoding="utf-8")
        (project / "blocks" / "uses_spectrum.py").write_text(USES_SPECTRUM_BLOCK, encoding="utf-8")

        payload = _palette_client(_scanned_registry(project)).get("/api/blocks/").json()

        assert payload["dropin_failures"] == []

    def test_one_failure_does_not_stop_the_rest_of_the_scan(self, home: Path, project: Path) -> None:
        """#1531 hardening stays intact: skip-don't-crash, and keep scanning."""
        (project / "types" / "spectrum.py").write_text(SPECTRUM_TYPE, encoding="utf-8")
        (project / "blocks" / "uses_spectrum.py").write_text(USES_SPECTRUM_BLOCK, encoding="utf-8")
        (project / "blocks" / "hostile.py").write_text("raise RuntimeError('hostile')\n", encoding="utf-8")

        registry = _scanned_registry(project)

        assert registry.get_spec("uses_spectrum") is not None
        assert [failure.error_type for failure in registry.dropin_failures()] == ["RuntimeError"]

    def test_rescan_rebuilds_rather_than_appends(self, home: Path, project: Path) -> None:
        (project / "blocks" / "uses_spectrum.py").write_text(USES_SPECTRUM_BLOCK, encoding="utf-8")

        registry = _scanned_registry(project)
        assert len(registry.dropin_failures()) == 1
        registry.hot_reload()

        assert len(registry.dropin_failures()) == 1

    def test_hot_reload_runs_an_edit_made_inside_one_second_at_the_same_size(self, home: Path, project: Path) -> None:
        """FR-062's other half, on the block side (Codex P1 on PR #2035).

        CPython accepts a cached ``.pyc`` when the source's mtime in whole
        seconds and its size both match. A block edited within one second to
        the same length satisfies both, so the reload re-executes the previous
        class body and the palette keeps offering a block that no longer exists
        on disk. Verified against the type registry first and reproduced here
        against a real ``BlockRegistry``.
        """
        path = project / "blocks" / "renamed_probe.py"
        path.write_text(_named_probe_block("alpha_probe"), encoding="utf-8")

        registry = _scanned_registry(project)
        assert registry.get_spec("alpha_probe") is not None

        before = path.stat()
        path.write_text(_named_probe_block("betaa_probe"), encoding="utf-8")
        assert path.stat().st_size == before.st_size, "precondition: the edit keeps the file size"
        os.utime(path, (before.st_atime, before.st_mtime))

        registry.hot_reload()

        # Only the *new* definition is asserted. ``hot_reload`` drops a tier-1
        # entry when its file is gone and not when a name inside a surviving
        # file changes, so ``alpha_probe`` lingering is that separate, unrelated
        # behaviour — the question here is whether the edited body ran at all.
        assert registry.get_spec("betaa_probe") is not None, "the reload ran a stale .pyc"

    # -- AUDIT-SEC P2-1: a drop-in that exits is a failure, not the end --------

    @pytest.mark.parametrize(
        ("body", "error_type"),
        [
            ("import sys\n\nsys.exit(1)\n", "SystemExit"),
            ("raise SystemExit('argparse would do this')\n", "SystemExit"),
            ("raise GeneratorExit\n", "GeneratorExit"),
        ],
    )
    def test_a_dropin_that_raises_outside_exception_is_recorded_not_fatal(
        self, home: Path, project: Path, body: str, error_type: str
    ) -> None:
        """``except Exception`` did not cover ``SystemExit``, and it must.

        The accident is ordinary: a script turned into a block keeps its
        ``sys.exit(main())`` or its ``argparse`` error path. Under the narrower
        handler that file killed the palette refresh on every startup, recorded
        no ``DropinFailure``, and left no in-product way to find it — the
        palette that would have shown the error is what died
        (``docs/audit/2026-08-07-adr-053-spec1-write-path.md`` P2-1).
        """
        (project / "types" / "spectrum.py").write_text(SPECTRUM_TYPE, encoding="utf-8")
        (project / "blocks" / "uses_spectrum.py").write_text(USES_SPECTRUM_BLOCK, encoding="utf-8")
        (project / "blocks" / "aa_exits.py").write_text(body, encoding="utf-8")

        registry = _scanned_registry(project)

        assert [failure.error_type for failure in registry.dropin_failures()] == [error_type]
        assert registry.get_spec("uses_spectrum") is not None, "the healthy neighbour must still register"

    def test_a_type_dropin_that_exits_does_not_take_the_type_scan_down(self, home: Path, project: Path) -> None:
        """The same rule in the other registry's drop-in pass."""
        (project / "types" / "aa_exits.py").write_text("import sys\n\nsys.exit(1)\n", encoding="utf-8")
        (project / "types" / "spectrum.py").write_text(SPECTRUM_TYPE, encoding="utf-8")

        registry = TypeRegistry()
        register_type_scan_dirs(registry, project)
        registry.scan_all()

        assert "SpectrumData" in registry.all_types(), "the healthy neighbour must still register"


# ---------------------------------------------------------------------------
# FR-016 / §13 OQ-1 — reject a type file that shadows an installed module
# ---------------------------------------------------------------------------


class TestTypeNameCollisionIsRejected:
    @pytest.fixture
    def installed_dep(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        """Importable top-level modules outside the type dirs.

        ``sample_dep`` stands in for an ordinary installed dependency and
        ``_sample_dep`` for a private one — the class the collision guard used
        to exempt (AUDIT-SEC P1-1). Both are needed because the two questions
        the guard answers about them are the same question.
        """
        site = tmp_path / "site"
        site.mkdir()
        (site / "sample_dep.py").write_text('ORIGIN = "installed"\n', encoding="utf-8")
        (site / "_sample_dep.py").write_text('ORIGIN = "installed"\n', encoding="utf-8")
        monkeypatch.syspath_prepend(str(site))
        return site

    def test_colliding_type_file_is_rejected_with_an_error(
        self, home: Path, project: Path, installed_dep: Path
    ) -> None:
        (project / "types" / "sample_dep.py").write_text(SPECTRUM_TYPE, encoding="utf-8")

        registry = _scanned_registry(project)

        failures = registry.dropin_failures()
        assert len(failures) == 1
        assert failures[0].file_path == str(project / "types" / "sample_dep.py")
        assert failures[0].error_type == COLLISION
        assert "sample_dep" in failures[0].message

    def test_the_real_module_still_imports_from_a_dropin_block(
        self, home: Path, project: Path, installed_dep: Path
    ) -> None:
        """Rejection is enforced, not merely announced: the installed module wins."""
        (project / "types" / "sample_dep.py").write_text(SPECTRUM_TYPE, encoding="utf-8")
        (project / "blocks" / "collision_probe.py").write_text(COLLISION_PROBE_BLOCK, encoding="utf-8")

        registry = _scanned_registry(project)

        assert registry.get_spec("collision_probe_installed") is not None
        assert registry.get_spec("collision_probe_shadowed") is None

    def test_rejection_reaches_the_block_listing_endpoint(self, home: Path, project: Path, installed_dep: Path) -> None:
        (project / "types" / "sample_dep.py").write_text(SPECTRUM_TYPE, encoding="utf-8")

        payload = _palette_client(_scanned_registry(project)).get("/api/blocks/").json()

        assert [entry["error_type"] for entry in payload["dropin_failures"]] == [COLLISION]

    def test_a_rejected_neighbour_does_not_block_a_valid_type(
        self, home: Path, project: Path, installed_dep: Path
    ) -> None:
        (project / "types" / "sample_dep.py").write_text(SPECTRUM_TYPE, encoding="utf-8")
        (project / "types" / "spectrum.py").write_text(SPECTRUM_TYPE, encoding="utf-8")
        (project / "blocks" / "uses_spectrum.py").write_text(USES_SPECTRUM_BLOCK, encoding="utf-8")

        registry = _scanned_registry(project)

        assert registry.get_spec("uses_spectrum") is not None
        assert [failure.error_type for failure in registry.dropin_failures()] == [COLLISION]

    def test_a_type_file_never_reports_itself_as_a_collision(self, home: Path, project: Path) -> None:
        """The lookup runs with the type dirs stripped, so ``spectrum.py`` is fine.

        Re-scanning is the case that catches a naive implementation: the first
        scan leaves ``sys.modules['spectrum']`` pointing at the type file, and a
        lookup that trusted it would reject the file on the second pass.
        """
        (project / "types" / "spectrum.py").write_text(SPECTRUM_TYPE, encoding="utf-8")
        (project / "blocks" / "uses_spectrum.py").write_text(USES_SPECTRUM_BLOCK, encoding="utf-8")

        registry = _scanned_registry(project)
        assert registry.dropin_failures() == []
        assert "spectrum" in sys.modules, "precondition: the drop-in import bound the stem"

        registry.hot_reload()

        assert registry.dropin_failures() == []
        assert registry.get_spec("uses_spectrum") is not None

    # -- AUDIT-SEC P1-1: a leading underscore is not an exemption -------------

    def test_an_underscore_prefixed_type_file_that_takes_a_taken_name_is_refused(
        self, home: Path, project: Path, installed_dep: Path
    ) -> None:
        """A ``_``-prefixed ``.py`` file on ``sys.path`` *is* importable by name.

        This test replaces one that asserted the opposite, on the stated
        premise that "private files are not importable by name, so they cannot
        collide". That premise is false, and it was the reason the exemption
        survived review. ``_`` is a convention meaning "do not register me",
        which the two registries honour for the *registration* question; the
        *collision* question is about which names the directory claims on the
        top-level module namespace, and the underscore does not change that
        answer. See ``docs/audit/2026-08-07-adr-053-spec1-write-path.md`` P1-1.
        """
        (project / "types" / "_sample_dep.py").write_text(SPECTRUM_TYPE, encoding="utf-8")

        failures = _scanned_registry(project).dropin_failures()

        assert [failure.error_type for failure in failures] == [COLLISION]
        assert failures[0].file_path == str(project / "types" / "_sample_dep.py")
        assert "_sample_dep" in failures[0].message

    def test_a_lazily_imported_private_stdlib_module_is_refused(self, home: Path, project: Path) -> None:
        """The concrete accident: ``types/_strptime.py``.

        No fixture stands in for the installed module here, because the point
        is that the exempted class was the standard library's own private
        modules — imported lazily, long after any scan, by ordinary calls
        (``datetime.strptime`` loads ``_strptime`` on first use). A guard that
        only looks at public names never sees them.
        """
        (project / "types" / "_strptime.py").write_text(SPECTRUM_TYPE, encoding="utf-8")

        failures = _scanned_registry(project).dropin_failures()

        assert [failure.error_type for failure in failures] == [COLLISION]
        assert "_strptime" in failures[0].message

    def test_an_underscore_prefixed_package_that_takes_a_taken_name_is_refused(
        self, home: Path, project: Path, installed_dep: Path
    ) -> None:
        """The package shape was exempted by the same bug and closed by the same rule."""
        package_dir = project / "types" / "_sample_dep"
        package_dir.mkdir()
        (package_dir / "__init__.py").write_text(SHADOWED_TYPE, encoding="utf-8")

        failures = _scanned_registry(project).dropin_failures()

        assert [failure.error_type for failure in failures] == [COLLISION]
        assert failures[0].file_path == str(package_dir)

    def test_a_private_helper_whose_name_is_free_is_not_refused(
        self, home: Path, project: Path, installed_dep: Path
    ) -> None:
        """The rule is "this name is already taken", not "this name is private".

        A user writing an ordinary private helper next to their types must not
        be refused — widening the guard to every importable name must not
        widen it to every underscore name.
        """
        (project / "types" / "_project_helpers.py").write_text(SPECTRUM_TYPE, encoding="utf-8")

        assert _scanned_registry(project).dropin_failures() == []

    def test_the_entries_that_name_no_top_level_module_are_not_reported(
        self, home: Path, project: Path, installed_dep: Path
    ) -> None:
        """``__init__.py`` and ``__pycache__`` stay out of the collision question.

        They are the only entries a directory on ``sys.path`` structurally does
        not make importable *by name*: ``__init__.py`` names the directory
        rather than a top-level module, and ``__pycache__`` holds compiled
        artefacts. Pinning them keeps the widened rule from drifting into
        "report everything in the directory".
        """
        (project / "types" / "__init__.py").write_text("", encoding="utf-8")
        cache_dir = project / "types" / "__pycache__"
        cache_dir.mkdir()
        (cache_dir / "__init__.py").write_text("", encoding="utf-8")

        assert _scanned_registry(project).dropin_failures() == []

    # -- #2022 P1-1: the guard must hold in the worker, not only the API ------

    def test_the_installed_module_wins_inside_a_fresh_worker(
        self, home: Path, project: Path, installed_dep: Path
    ) -> None:
        """FR-016 in the process that never runs the palette scan.

        The worker appends the user import path it receives after everything
        else on ``sys.path`` (ADR-056 FR-001), so the installed module wins
        there exactly as it does in the API process — the
        scan-time-versus-run-time divergence FR-013 exists to eliminate cannot
        arise. Registration is deliberately not the assertion: the block reports
        its answer from ``run()``.
        """
        (project / "types" / "sample_dep.py").write_text(SHADOWED_TYPE, encoding="utf-8")
        (project / "blocks" / "worker_collision_probe.py").write_text(WORKER_COLLISION_BLOCK, encoding="utf-8")

        spec = _scanned_registry(project).get_spec("worker_collision_probe")
        assert spec is not None

        payload = build_worker_payload(
            block_class=f"{spec.module_path}.{spec.class_name}",
            inputs_refs={},
            config={},
            output_dir=None,
        )
        env = _worker_env(worker_cwd=None, project_dir=str(project)) or dict(os.environ)
        # The installed module has to be importable in the subprocess for the
        # question to mean anything; the fixture only put it on this process's
        # sys.path.
        env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(installed_dep), env.get("PYTHONPATH", "")]))
        proc = subprocess.run(
            [sys.executable, "-m", "scistudio.engine.runners.worker"],
            input=payload,
            capture_output=True,
            timeout=120,
            env=env,
        )

        stdout = proc.stdout.decode("utf-8", errors="replace")
        stderr = proc.stderr.decode("utf-8", errors="replace")
        assert proc.returncode == 0, f"Worker exited {proc.returncode}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
        result = json.loads(stdout)
        assert "error" not in result, f"Worker reported error: {result.get('error')}"
        assert result.get("outputs", {}).get("origin") == "installed", (
            "FR-016: the worker must resolve the installed module, not the colliding type file"
        )

    # -- #2022 P1-2: refused means refused, not announced ---------------------

    def test_a_colliding_type_file_does_not_register_its_type(
        self, home: Path, project: Path, installed_dep: Path
    ) -> None:
        """Spec §13 OQ-1: registration is refused, not merely warned.

        Built the way ``ApiRuntime.refresh_type_registry`` builds it. Before
        #2022 the user was shown an error saying the file was rejected and had
        to be renamed while the type it declared stayed resolvable and loadable,
        and nothing in the product reconciled the two.
        """
        (project / "types" / "sample_dep.py").write_text(SHADOWED_TYPE, encoding="utf-8")

        registry = TypeRegistry()
        register_type_scan_dirs(registry, project)
        registry.scan_all()

        assert "ShadowedType" not in registry.all_types()
        with pytest.raises(KeyError):
            registry.resolve("ShadowedType")

    def test_the_refusal_is_still_reported_while_a_neighbour_registers(
        self, home: Path, project: Path, installed_dep: Path
    ) -> None:
        """Refusing registration must not cost the report, or the neighbours."""
        (project / "types" / "sample_dep.py").write_text(SHADOWED_TYPE, encoding="utf-8")
        (project / "types" / "spectrum.py").write_text(SPECTRUM_TYPE, encoding="utf-8")

        types = TypeRegistry()
        register_type_scan_dirs(types, project)
        types.scan_all()

        assert "SpectrumData" in types.all_types()
        assert [failure.error_type for failure in _scanned_registry(project).dropin_failures()] == [COLLISION]

    # -- #2022 P3-1: a package directory shadows just as effectively ----------

    def test_a_colliding_package_directory_is_rejected(self, home: Path, project: Path, installed_dep: Path) -> None:
        """``types/sample_dep/__init__.py`` is as importable as ``sample_dep.py``."""
        package_dir = project / "types" / "sample_dep"
        package_dir.mkdir()
        (package_dir / "__init__.py").write_text(SHADOWED_TYPE, encoding="utf-8")
        (project / "blocks" / "collision_probe.py").write_text(COLLISION_PROBE_BLOCK, encoding="utf-8")

        registry = _scanned_registry(project)

        failures = registry.dropin_failures()
        assert [failure.error_type for failure in failures] == [COLLISION]
        assert failures[0].file_path == str(package_dir)
        assert registry.get_spec("collision_probe_installed") is not None

    def test_a_plain_directory_is_not_reported_as_a_collision(
        self, home: Path, project: Path, installed_dep: Path
    ) -> None:
        """A namespace portion cannot displace an installed regular module.

        Python resolves a regular module or package found anywhere on
        ``sys.path`` ahead of every namespace portion, so reporting one would
        be a false refusal. Pins the reasoning the detector documents.
        """
        (project / "types" / "sample_dep").mkdir()
        (project / "blocks" / "collision_probe.py").write_text(COLLISION_PROBE_BLOCK, encoding="utf-8")

        registry = _scanned_registry(project)

        assert registry.dropin_failures() == []
        assert registry.get_spec("collision_probe_installed") is not None

    # -- #2022 P3-2: the check binds nothing ----------------------------------

    def test_the_name_check_imports_nothing(self, home: Path, project: Path, installed_dep: Path) -> None:
        """A ``numpy.py`` collision must not import numpy on every refresh.

        The old guard bound the shadowed module once per process to keep it
        winning; with user directories after the installed packages on
        ``sys.path`` there is nothing to bind (ADR-056 FR-008).
        """
        (project / "types" / "sample_dep.py").write_text(SHADOWED_TYPE, encoding="utf-8")

        registry = _scanned_registry(project)
        registry.hot_reload()

        assert "sample_dep" not in sys.modules
        assert [failure.error_type for failure in registry.dropin_failures()] == [COLLISION]

    # -- Codex P1 on PR #2035: a collision whose module raises -------------------

    #: An installed module with a perfectly good spec that raises on import —
    #: the shape a missing native dependency takes.
    _UNIMPORTABLE_DEP = 'raise ImportError("libsample.so: cannot open shared object file")\n'

    def test_a_collision_whose_module_raises_never_resolves_to_the_dropin(
        self, home: Path, project: Path, installed_dep: Path
    ) -> None:
        """FR-016 must not depend on the collided package importing cleanly.

        The installed module comes first on ``sys.path``, so ``import
        sample_dep`` finds it and fails with the module's own error; the drop-in
        file behind it is never reached. The name check still reports the file.
        """
        (installed_dep / "sample_dep.py").write_text(self._UNIMPORTABLE_DEP, encoding="utf-8")
        (project / "types" / "sample_dep.py").write_text(SHADOWED_TYPE, encoding="utf-8")
        install_user_import_path(build_user_import_path(project))

        refusals = check_user_import_path(type_scan_dirs(project), user_import_path=build_user_import_path(project))
        assert [refusal.stem for refusal in refusals] == ["sample_dep"]
        with pytest.raises(ImportError) as raised:
            importlib.import_module("sample_dep")

        assert "sample_dep" not in sys.modules
        assert "libsample.so" in str(raised.value), "the module's own failure is what the user sees"

    def test_the_collision_is_still_reported_on_a_second_pass(
        self, home: Path, project: Path, installed_dep: Path
    ) -> None:
        """A failed import must not make the next check answer "no module"."""
        (installed_dep / "sample_dep.py").write_text(self._UNIMPORTABLE_DEP, encoding="utf-8")
        (project / "types" / "sample_dep.py").write_text(SHADOWED_TYPE, encoding="utf-8")
        install_user_import_path(build_user_import_path(project))

        check_user_import_path(type_scan_dirs(project))
        with pytest.raises(ImportError):
            importlib.import_module("sample_dep")
        second = check_user_import_path(type_scan_dirs(project))

        assert [refusal.stem for refusal in second] == ["sample_dep"]

    def test_the_dropin_does_not_win_the_name_through_the_block_scan(
        self, home: Path, project: Path, installed_dep: Path
    ) -> None:
        """The product surface of the same defect: the palette scan's own path."""
        (installed_dep / "sample_dep.py").write_text(self._UNIMPORTABLE_DEP, encoding="utf-8")
        (project / "types" / "sample_dep.py").write_text(SHADOWED_TYPE, encoding="utf-8")
        (project / "blocks" / "collision_probe.py").write_text(COLLISION_PROBE_BLOCK, encoding="utf-8")

        registry = _scanned_registry(project)

        assert registry.get_spec("collision_probe_shadowed") is None
        assert COLLISION in {failure.error_type for failure in registry.dropin_failures()}

    # -- #2022: a refusal lasts exactly as long as the file ---------------------

    def test_removing_the_colliding_file_ends_the_refusal(self, home: Path, project: Path, installed_dep: Path) -> None:
        """The report asks the user to rename or remove the file; doing it must work.

        There is no process-wide refusal to release any more: the check reads
        the directory on every pass, so the next scan simply finds nothing, and
        the installed module was never displaced in the first place.
        """
        (project / "types" / "sample_dep.py").write_text(SHADOWED_TYPE, encoding="utf-8")
        registry = _scanned_registry(project)
        assert [failure.error_type for failure in registry.dropin_failures()] == [COLLISION]

        (project / "types" / "sample_dep.py").unlink()
        registry.hot_reload()

        assert registry.dropin_failures() == []
        assert importlib.import_module("sample_dep").ORIGIN == "installed"

    def test_a_file_still_present_is_still_refused_after_a_rescan(
        self, home: Path, project: Path, installed_dep: Path
    ) -> None:
        (project / "types" / "sample_dep.py").write_text(SHADOWED_TYPE, encoding="utf-8")
        registry = _scanned_registry(project)

        registry.hot_reload()

        assert [failure.error_type for failure in registry.dropin_failures()] == [COLLISION]

    def test_the_same_name_colliding_in_two_tiers_is_reported_for_both(
        self, home: Path, project: Path, installed_dep: Path
    ) -> None:
        """Both tiers are seen in one pass; cross-tier order does not hide a collision."""
        (home / ".scistudio" / "types" / "sample_dep.py").write_text(SHADOWED_TYPE, encoding="utf-8")
        (project / "types" / "sample_dep.py").write_text(SHADOWED_TYPE, encoding="utf-8")

        refusals = check_user_import_path(build_user_import_path(project))

        assert [refusal.path for refusal in refusals] == [
            (project / "types" / "sample_dep.py").resolve(),
            (home / ".scistudio" / "types" / "sample_dep.py").resolve(),
        ]

    def test_a_directory_that_cannot_be_listed_does_not_stop_the_scan(
        self, home: Path, project: Path, installed_dep: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (project / "types" / "spectrum.py").write_text(SPECTRUM_TYPE, encoding="utf-8")
        (project / "blocks" / "uses_spectrum.py").write_text(USES_SPECTRUM_BLOCK, encoding="utf-8")
        real_iterdir = Path.iterdir

        def _unreadable(self: Path) -> Iterator[Path]:
            if self.name == "types" and self.parent == home / ".scistudio":
                raise OSError("directory temporarily unreadable")
            return real_iterdir(self)

        monkeypatch.setattr(Path, "iterdir", _unreadable)
        registry = _scanned_registry(project)

        assert registry.get_spec("uses_spectrum") is not None


# ---------------------------------------------------------------------------
# FR-012 / FR-014 — the tier layout the user import path rests on (#2022 P3-3)
# ---------------------------------------------------------------------------


class TestUserImportPathTiers:
    """The user import path is the scan dirs of the same tiers, in FR-001 order.

    A registry is handed block and type directories separately; the path it
    ensures on ``sys.path`` must be the one the backend installs for the
    project, or cross-tier shadowing would depend on which registry ran first.
    """

    def test_the_path_is_the_type_and_block_dirs_of_the_same_tiers(self, home: Path, project: Path) -> None:
        (home / ".scistudio" / "types").mkdir(parents=True, exist_ok=True)
        expected = tuple(
            path.resolve()
            for pair in zip(type_scan_dirs(project), block_scan_dirs(project), strict=True)
            for path in pair
        )
        assert build_user_import_path(project) == expected

    def test_the_path_holds_with_no_project_open(self, home: Path) -> None:
        expected = tuple(
            path.resolve() for pair in zip(type_scan_dirs(None), block_scan_dirs(None), strict=True) for path in pair
        )
        assert build_user_import_path(None) == expected


# ---------------------------------------------------------------------------
# The two ``sys.path`` windows, under interleaving (AUDIT-SEC P3-1)
# ---------------------------------------------------------------------------


class TestSysPathWindowsAreNotSnapshots:
    """The installed-package window must undo its own edits, not restore a snapshot.

    ``prepended_sys_paths`` survives ADR-056 for installed-package loading only;
    user code no longer opens a window.

    A snapshot is wrong the moment two windows overlap, and both failure modes
    are real: the inner window's exit restores the outer window's ``sys.path``,
    so the inner user silently loses its roots mid-window, and the outer exit
    then restores a snapshot predating the inner one, leaking the inner roots
    for the rest of the process
    (``docs/audit/2026-08-07-adr-053-spec1-write-path.md`` P3-1).

    Driven as a deterministic A-enter / B-enter / A-exit / B-exit interleaving
    rather than with threads, because the defect is about ordering rather than
    about concurrency — the two scans run on one event loop today, which is
    exactly why this is latent rather than live.
    """

    def test_overlapping_prepend_windows_neither_lose_nor_leak(self, tmp_path: Path) -> None:
        root_a = tmp_path / "root_a"
        root_b = tmp_path / "root_b"
        root_a.mkdir()
        root_b.mkdir()
        baseline = list(sys.path)

        window_a = prepended_sys_paths([root_a])
        window_b = prepended_sys_paths([root_b])
        window_a.__enter__()
        try:
            window_b.__enter__()
            try:
                assert str(root_a) in sys.path
                assert str(root_b) in sys.path
            finally:
                window_a.__exit__(None, None, None)
            assert str(root_b) in sys.path, "B's root must survive A's exit, inside B's own window"
        finally:
            window_b.__exit__(None, None, None)

        assert str(root_a) not in sys.path, "A's root must not leak past both windows"
        assert str(root_b) not in sys.path
        assert sys.path == baseline

    def test_a_prepend_window_keeps_what_the_body_added(self, tmp_path: Path) -> None:
        """Restoring a snapshot also discarded anything the body itself added."""
        root = tmp_path / "root"
        root.mkdir()
        added = str(tmp_path / "added_by_the_body")

        with prepended_sys_paths([root]):
            sys.path.append(added)
        try:
            assert added in sys.path
            assert str(root) not in sys.path
        finally:
            sys.path.remove(added)


# ---------------------------------------------------------------------------
# What the collision report names as the origin (AUDIT-SEC P3-10)
# ---------------------------------------------------------------------------


def test_a_namespace_package_collision_does_not_report_itself_as_built_in(
    home: Path, project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``find_spec().origin`` is ``None`` for a namespace package too.

    Reporting the collision is right — a regular module does displace a
    namespace portion — but ``origin or "built-in"`` told the user a directory
    on disk was a built-in module, which sends them looking in the wrong place
    (``docs/audit/2026-08-07-adr-053-spec1-write-path.md`` P3-10).
    """
    site = tmp_path / "site"
    (site / "namespace_dep").mkdir(parents=True)
    monkeypatch.syspath_prepend(str(site))
    (project / "types" / "namespace_dep.py").write_text(SPECTRUM_TYPE, encoding="utf-8")

    try:
        failures = _scanned_registry(project).dropin_failures()

        assert [failure.error_type for failure in failures] == [COLLISION]
        assert "built-in" not in failures[0].message
        assert "namespace package" in failures[0].message
        assert str(site / "namespace_dep") in failures[0].message
    finally:
        sys.modules.pop("namespace_dep", None)


# ---------------------------------------------------------------------------
# Hot reload: a file that now fails, and a package-shaped type that changed
# ---------------------------------------------------------------------------


def test_hot_reload_drops_the_blocks_of_a_file_that_now_fails(project: Path, home: Path) -> None:
    """A block file edited into an import error no longer keeps its old spec."""
    (project / "types" / "spectrum.py").write_text(SPECTRUM_TYPE, encoding="utf-8")
    block_file = project / "blocks" / "uses_spectrum.py"
    block_file.write_text(USES_SPECTRUM_BLOCK, encoding="utf-8")
    registry = _scanned_registry(project)
    assert "test.uses_spectrum" in {spec.type_name for spec in registry.all_specs().values()}

    block_file.write_text("from a_sibling_that_is_not_there import helper\n" + USES_SPECTRUM_BLOCK, encoding="utf-8")
    stamp = block_file.stat().st_mtime + 5
    os.utime(block_file, (stamp, stamp))
    registry.hot_reload()

    assert "test.uses_spectrum" not in {spec.type_name for spec in registry.all_specs().values()}
    assert [Path(failure.file_path).name for failure in registry.dropin_failures()] == ["uses_spectrum.py"]


def test_a_package_shaped_type_is_imported_fresh_after_an_edit(project: Path, home: Path) -> None:
    """Every submodule of a ``types/<pkg>/`` drop-in is re-read, not only the package."""
    package = project / "types" / "omics_pkg"
    package.mkdir()
    (package / "__init__.py").write_text("from omics_pkg._types import BASE\n", encoding="utf-8")
    (package / "_types.py").write_text("BASE = 'Artifact'\n", encoding="utf-8")
    block_file = project / "blocks" / "base_probe.py"
    block_file.write_text(
        "from typing import ClassVar\n"
        "from omics_pkg import BASE\n"
        "from scistudio.blocks.base.block import Block\n"
        "class BaseProbe(Block):\n"
        "    type_name: ClassVar[str] = 'test.base_probe'\n"
        "    name: ClassVar[str] = 'base_probe_' + BASE\n"
        "    base_category: ClassVar[str] = 'process'\n"
        "    input_ports: ClassVar = []\n"
        "    output_ports: ClassVar = []\n"
        "    def run(self, inputs, config):\n"
        "        return {}\n",
        encoding="utf-8",
    )
    registry = _scanned_registry(project)
    assert "base_probe_Artifact" in registry.all_specs()

    try:
        (package / "_types.py").write_text("BASE = 'CompositeData'\n", encoding="utf-8")
        stamp = block_file.stat().st_mtime + 5
        for path in (package / "_types.py", block_file):
            os.utime(path, (stamp, stamp))
        registry.hot_reload()

        names = set(registry.all_specs())
        assert "base_probe_CompositeData" in names
    finally:
        for name in [name for name in sys.modules if name == "omics_pkg" or name.startswith("omics_pkg.")]:
            sys.modules.pop(name, None)
