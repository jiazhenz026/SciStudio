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
from scistudio.core import dropins as dropins_module
from scistudio.core.dropins import (
    block_scan_dirs,
    dropin_type_roots_for_block_dirs,
    register_block_scan_dirs,
    register_type_scan_dirs,
    type_scan_dirs,
)
from scistudio.core.types.registry import TypeRegistry
from scistudio.engine.runners.process_handle import build_worker_payload

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
    """Scan the way :func:`refresh_block_registry` does (ADR-053 FR-057)."""
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
    def test_spec_records_the_type_roots_for_the_worker(self, home: Path, project: Path) -> None:
        """The roots the parent used are stamped on the spec, project tier first."""
        (project / "types" / "spectrum.py").write_text(SPECTRUM_TYPE, encoding="utf-8")
        (project / "blocks" / "uses_spectrum.py").write_text(USES_SPECTRUM_BLOCK, encoding="utf-8")

        spec = _scanned_registry(project).get_spec("uses_spectrum")

        assert spec is not None
        roots = spec.runtime_import_roots
        assert roots[0] == str(project / "types"), "FR-014: the project tier must resolve first"
        assert str(home / ".scistudio" / "types") in roots

    def test_dropin_block_runs_in_a_fresh_worker(self, home: Path, project: Path) -> None:
        """FR-013: registering is not enough — the worker must run the block.

        Spawns a real ``python -m scistudio.engine.runners.worker``, which
        re-imports the drop-in file from disk in a fresh interpreter. Without
        the recorded roots the worker reproduces the original
        ``ModuleNotFoundError: No module named 'spectrum'``.
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
            block_file_path=spec.file_path,
            runtime_import_roots=spec.runtime_import_roots,
        )
        proc = subprocess.run(
            [sys.executable, "-m", "scistudio.engine.runners.worker"],
            input=payload,
            capture_output=True,
            timeout=120,
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
        assert failures[0].error_type == "DropinTypeNameCollision"
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

        assert [entry["error_type"] for entry in payload["dropin_failures"]] == ["DropinTypeNameCollision"]

    def test_a_rejected_neighbour_does_not_block_a_valid_type(
        self, home: Path, project: Path, installed_dep: Path
    ) -> None:
        (project / "types" / "sample_dep.py").write_text(SPECTRUM_TYPE, encoding="utf-8")
        (project / "types" / "spectrum.py").write_text(SPECTRUM_TYPE, encoding="utf-8")
        (project / "blocks" / "uses_spectrum.py").write_text(USES_SPECTRUM_BLOCK, encoding="utf-8")

        registry = _scanned_registry(project)

        assert registry.get_spec("uses_spectrum") is not None
        assert [failure.error_type for failure in registry.dropin_failures()] == ["DropinTypeNameCollision"]

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

        assert [failure.error_type for failure in failures] == ["DropinTypeNameCollision"]
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

        assert [failure.error_type for failure in failures] == ["DropinTypeNameCollision"]
        assert "_strptime" in failures[0].message

    def test_an_underscore_prefixed_package_that_takes_a_taken_name_is_refused(
        self, home: Path, project: Path, installed_dep: Path
    ) -> None:
        """The package shape was exempted by the same bug and closed by the same rule."""
        package_dir = project / "types" / "_sample_dep"
        package_dir.mkdir()
        (package_dir / "__init__.py").write_text(SHADOWED_TYPE, encoding="utf-8")

        failures = _scanned_registry(project).dropin_failures()

        assert [failure.error_type for failure in failures] == ["DropinTypeNameCollision"]
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

        The worker puts the stamped type roots on ``sys.path`` itself and
        reconstructs the block from its file, so a guard that lived only in
        ``_scan_tier1`` left the installed module winning in the API process and
        the type file winning here — the scan-time-versus-run-time divergence
        FR-013 exists to eliminate. Registration is deliberately not the
        assertion: the block reports its answer from ``run()``.
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
            block_file_path=spec.file_path,
            runtime_import_roots=spec.runtime_import_roots,
        )
        env = dict(os.environ)
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
        assert [failure.error_type for failure in _scanned_registry(project).dropin_failures()] == [
            "DropinTypeNameCollision"
        ]

    # -- #2022 P3-1: a package directory shadows just as effectively ----------

    def test_a_colliding_package_directory_is_rejected(self, home: Path, project: Path, installed_dep: Path) -> None:
        """``types/sample_dep/__init__.py`` is as importable as ``sample_dep.py``."""
        package_dir = project / "types" / "sample_dep"
        package_dir.mkdir()
        (package_dir / "__init__.py").write_text(SHADOWED_TYPE, encoding="utf-8")
        (project / "blocks" / "collision_probe.py").write_text(COLLISION_PROBE_BLOCK, encoding="utf-8")

        registry = _scanned_registry(project)

        failures = registry.dropin_failures()
        assert [failure.error_type for failure in failures] == ["DropinTypeNameCollision"]
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

    # -- #2022 P3-2: bind the shadowed module once, not once per scan ---------

    def test_the_shadowed_module_is_bound_once_per_process(
        self, home: Path, project: Path, installed_dep: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A ``numpy.py`` collision must not re-import numpy on every refresh."""
        (project / "types" / "sample_dep.py").write_text(SHADOWED_TYPE, encoding="utf-8")

        registry = _scanned_registry(project)
        assert sys.modules["sample_dep"].__file__ == str(installed_dep / "sample_dep.py")

        imported: list[str] = []
        real_import_module = importlib.import_module

        def _spy(name: str, package: str | None = None):  # type: ignore[no-untyped-def]
            imported.append(name)
            return real_import_module(name, package)

        monkeypatch.setattr(dropins_module.importlib, "import_module", _spy)
        registry.hot_reload()

        assert "sample_dep" not in imported
        assert [failure.error_type for failure in registry.dropin_failures()] == ["DropinTypeNameCollision"]


# ---------------------------------------------------------------------------
# FR-012 / FR-014 — the sibling-``types/`` inference the roots rest on (#2022 P3-3)
# ---------------------------------------------------------------------------


class TestTypeRootDerivation:
    """``dropin_type_roots_for_block_dirs`` assumes a tier layout. Pin it.

    The registry is handed block directories and never learns the project root,
    so it recovers the type roots as ``<block_dir>.parent / "types"``. That is
    correct only while every block scan dir is ``<tier-root>/blocks``. The
    assumption is load-bearing for FR-012 in all four processes and was stated
    only in a docstring; a future tier layout change should fail here rather
    than silently resolve nothing.
    """

    def test_block_dirs_round_trip_to_the_type_dirs_of_the_same_tiers(self, home: Path, project: Path) -> None:
        assert dropin_type_roots_for_block_dirs(block_scan_dirs(project)) == type_scan_dirs(project)

    def test_the_round_trip_holds_with_no_project_open(self, home: Path) -> None:
        assert dropin_type_roots_for_block_dirs(block_scan_dirs(None)) == type_scan_dirs(None)
