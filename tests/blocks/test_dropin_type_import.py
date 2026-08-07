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
  stem collides with an importable top-level module is rejected, and the module
  it collides with still imports.
"""

from __future__ import annotations

import json
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
from scistudio.core.dropins import register_block_scan_dirs
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
_DROPIN_MODULE_NAMES = ("spectrum", "shared_type", "sample_dep")


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
        """An importable top-level ``sample_dep`` module outside the type dirs."""
        site = tmp_path / "site"
        site.mkdir()
        (site / "sample_dep.py").write_text('ORIGIN = "installed"\n', encoding="utf-8")
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

    def test_underscore_prefixed_type_files_are_ignored(self, home: Path, project: Path, installed_dep: Path) -> None:
        """Private files are not importable by name, so they cannot collide."""
        (project / "types" / "_sample_dep.py").write_text(SPECTRUM_TYPE, encoding="utf-8")

        assert _scanned_registry(project).dropin_failures() == []
