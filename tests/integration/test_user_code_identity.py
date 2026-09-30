"""A user type is one class in every process that runs user code (ADR-056; spec NEW-016).

Covers User Story 1 end to end, across processes, without the resident panel
restart (FR-013), which lands with the reset entry point:

- one class per user type across a block, the type registry, a block worker
  and a panel process;
- the #2480 ``SimpleSaver`` failure ("SaveAnnData expected AnnData, got
  AnnData") does not occur;
- a block imports a helper file and another block file beside it;
- an object of a user type pickled in the backend unpickles in a worker.
"""

from __future__ import annotations

import base64
import json
import pickle
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.registry import BlockRegistry
from scistudio.core.dropins import register_block_scan_dirs, register_type_scan_dirs
from scistudio.core.types.registry import TypeRegistry
from scistudio.core.user_code import build_user_import_path, install_user_import_path

pytestmark = pytest.mark.serial

TYPES_SOURCE = """\
from scistudio.core.types.base import DataObject


class AnnData(DataObject):
    \"\"\"An annotated matrix (the #2480 type).\"\"\"
"""

HELPER_SOURCE = """\
def label(value):
    return f"helper:{value}"
"""

SAVER_SOURCE = """\
from pathlib import Path
from typing import Any

from scistudio.blocks.io.simple_io import SimpleSaver
from scverse_omics import AnnData


class SaveAnnData(SimpleSaver):
    name = "Save AnnData"
    input_type = AnnData
    format_id = "anndata_marker"
    extensions = (".annmarker",)

    def save_file(self, obj: AnnData, path: Path, config: dict[str, Any]) -> None:
        path.write_text(type(obj).__module__, encoding="utf-8")
"""

PROBE_SOURCE = """\
import base64
import json
import pickle
from pathlib import Path
from typing import Any, ClassVar

from omics_helpers import label
from save_anndata import SaveAnnData
from scistudio.blocks.base.block import Block
from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.base.ports import InputPort, OutputPort
from scverse_omics import AnnData


class IdentityProbe(Block):
    type_name: ClassVar[str] = "test.identity_probe"
    name: ClassVar[str] = "Identity Probe"
    base_category: ClassVar[str] = "process"
    input_ports: ClassVar = [InputPort(name="data", accepted_types=[AnnData], required=False)]
    output_ports: ClassVar = [OutputPort(name="out", accepted_types=[AnnData])]

    def run(self, inputs: dict[str, Any], config: BlockConfig) -> dict[str, Any]:
        from scistudio.core.types.serialization import _get_type_registry

        registered = _get_type_registry().load_class("AnnData")
        unpickled = pickle.loads(base64.b64decode(config.get("pickled")))
        target = Path(config.get("save_to"))
        SaveAnnData(config={}).save(registered(), BlockConfig(params={"path": str(target)}))
        report = {
            "registry_is_block_type": registered is AnnData,
            "port_is_registry_type": self.input_ports[0].accepted_types[0] is registered,
            "saver_is_registry_type": SaveAnnData.input_type is registered,
            "unpickled_is_instance": isinstance(unpickled, registered),
            "module": AnnData.__module__,
            "helper": label("x"),
            "saved": target.read_text(encoding="utf-8"),
        }
        return {"out": json.dumps(report)}
"""

PANEL_PY = """\
from panel_helper import VALUE
from scverse_omics import AnnData


def setup(data):
    pass


def probe():
    from scistudio.core.types.serialization import _get_type_registry

    registered = _get_type_registry().load_class("AnnData")
    return {"same": registered is AnnData, "module": AnnData.__module__, "helper": VALUE}
"""


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture()
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    project = tmp_path / "project"
    _write(project / "types" / "scverse_omics.py", TYPES_SOURCE)
    _write(project / "blocks" / "omics_helpers.py", HELPER_SOURCE)
    _write(project / "blocks" / "save_anndata.py", SAVER_SOURCE)
    _write(project / "blocks" / "identity_probe.py", PROBE_SOURCE)
    monkeypatch.setenv("SCISTUDIO_PROJECT_DIR", str(project))
    return project


def _registries(project: Path) -> tuple[TypeRegistry, BlockRegistry]:
    install_user_import_path(build_user_import_path(project))
    types = TypeRegistry()
    register_type_scan_dirs(types, project)
    types.scan_all()
    blocks = BlockRegistry()
    register_block_scan_dirs(blocks, project)
    blocks.scan()
    return types, blocks


def test_one_class_across_the_type_registry_and_every_block(project: Path) -> None:
    types, blocks = _registries(project)

    anndata = types.load_class("AnnData")
    probe = blocks.instantiate("Identity Probe")
    saver = blocks.instantiate("Save AnnData")

    assert anndata.__module__ == "scverse_omics"
    assert probe.input_ports[0].accepted_types[0] is anndata
    assert type(saver).input_type is anndata
    assert blocks.find_saver_capability(anndata, ".annmarker").data_type is anndata
    assert blocks.dropin_failures() == []


def test_a_block_imports_a_helper_and_another_block_file(project: Path) -> None:
    _types, blocks = _registries(project)
    specs = {spec.class_name: spec for spec in blocks.all_specs().values() if spec.source == "tier1"}

    # ``identity_probe.py`` imports ``SaveAnnData`` from ``save_anndata.py``:
    # both register, and ``SaveAnnData`` only once, from its own file.
    assert set(specs) == {"IdentityProbe", "SaveAnnData"}
    assert specs["SaveAnnData"].module_path == "save_anndata"
    assert specs["IdentityProbe"].module_path == "identity_probe"


def test_simple_saver_accepts_the_registered_type_in_process(project: Path, tmp_path: Path) -> None:
    # #2480: "SaveAnnData expected AnnData, got AnnData".
    types, blocks = _registries(project)
    saver = blocks.instantiate("Save AnnData")
    target = tmp_path / "out.annmarker"

    saver.save(types.load_class("AnnData")(), BlockConfig(params={"path": str(target)}))

    assert target.read_text(encoding="utf-8") == "scverse_omics"


def test_worker_resolves_the_same_class_and_unpickles_a_backend_object(project: Path, tmp_path: Path) -> None:
    from scistudio.engine.runners.local import _worker_env
    from scistudio.engine.runners.process_handle import build_worker_payload

    types, blocks = _registries(project)
    spec = blocks.get_spec("Identity Probe")
    pickled = base64.b64encode(pickle.dumps(types.load_class("AnnData")())).decode("ascii")
    payload = build_worker_payload(
        block_class=f"{spec.module_path}.{spec.class_name}",
        inputs_refs={},
        config={"pickled": pickled, "save_to": str(tmp_path / "worker.annmarker")},
        output_dir=str(tmp_path / "out"),
    )
    assert b"block_file_path" not in payload and b"runtime_import_roots" not in payload

    env = _worker_env(worker_cwd=None, project_dir=str(project))
    proc = subprocess.run(
        [sys.executable, "-m", "scistudio.engine.runners.worker"],
        input=payload,
        capture_output=True,
        timeout=120,
        env=env,
    )

    stdout = proc.stdout.decode("utf-8", errors="replace")
    stderr = proc.stderr.decode("utf-8", errors="replace")
    assert proc.returncode == 0, f"worker exited {proc.returncode}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
    result = json.loads(stdout)
    assert "error" not in result, result.get("error")
    report = json.loads(result["outputs"]["out"])
    assert report == {
        "registry_is_block_type": True,
        "port_is_registry_type": True,
        "saver_is_registry_type": True,
        "unpickled_is_instance": True,
        "module": "scverse_omics",
        "helper": "helper:x",
        "saved": "scverse_omics",
    }


def test_panel_process_resolves_the_same_class(project: Path) -> None:
    from scistudio.engine.runners.process_handle import ProcessRegistry
    from scistudio.panels import process as process_mod

    panel_dir = project / "panels" / "lab.omics"
    _write(panel_dir / "panel.py", PANEL_PY)
    _write(panel_dir / "panel_helper.py", "VALUE = 'beside-panel'\n")
    process = process_mod.start_panel_process(
        context_id="pc-identity",
        panel_dir=panel_dir,
        project_dir=project,
        registry=ProcessRegistry(),
        setup_payload=None,
    )
    try:
        deadline = time.time() + 30
        while time.time() < deadline and process.state == process_mod.STARTING:
            time.sleep(0.05)
        assert process.state == process_mod.RUNNING, process.log_tail()
        result: dict[str, Any] = process.call("probe", {}).header["result"]
    finally:
        process.stop()
    assert result == {"same": True, "module": "scverse_omics", "helper": "beside-panel"}


def test_worker_environment_carries_the_user_import_path(project: Path) -> None:
    from scistudio.core.user_code import USER_IMPORT_PATH_ENV_VAR, parse_user_import_path
    from scistudio.engine.runners.local import _worker_env

    install_user_import_path(build_user_import_path(project))
    env = _worker_env(worker_cwd=None, project_dir=str(project))

    assert env is not None
    assert parse_user_import_path(env[USER_IMPORT_PATH_ENV_VAR]) == build_user_import_path(project)


def test_plot_harness_imports_the_render_script_and_its_neighbours_by_name(project: Path, tmp_path: Path) -> None:
    """The plot folder is the entry folder: a render script imports a helper beside it and a project type."""
    import os

    from scistudio.core.user_code import user_import_path_env
    from scistudio.plot._harness import PYTHON_HARNESS

    plot_dir = project / "plots" / "omics.plot"
    script = _write(
        plot_dir / "render.py",
        "from plot_helper import VALUE\nfrom scverse_omics import AnnData\n\n\n"
        "def render(collection):\n    return VALUE + ':' + AnnData.__module__\n",
    )
    _write(plot_dir / "plot_helper.py", "VALUE = 'beside-script'\n")
    work = tmp_path / "work"
    _write(work / "_plot_harness.py", PYTHON_HARNESS)
    env = {**os.environ, **user_import_path_env(build_user_import_path(project, entry_folder=plot_dir))}

    code = "import sys, _plot_harness as h; print(h._load_render(sys.argv[1], 'render')(None))"
    proc = subprocess.run(
        [sys.executable, "-c", code, str(script)],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip().splitlines()[-1] == "beside-script:scverse_omics"
