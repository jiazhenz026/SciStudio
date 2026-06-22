"""CodeBlock engine findings (see the alpha test-suite FINDINGS registry).

FIND-F: the Python CodeBlock backend injected no ``SCISTUDIO_*_DIR`` env
vars (the R/Quarto backends do via their exchange wrappers), so a script
had no supported way to locate its exchange inputs/outputs. Fixed under
#1740: the Python backend now injects the same exchange env via the shared
``codeblock_exchange_env`` helper. The test runs a CodeBlock with NO
``environment_variables`` (probing the backend's native behaviour) and
asserts the subprocess sees ``SCISTUDIO_INPUTS_DIR``; it is retained as a
regression guard.
"""

from __future__ import annotations

import sys
from pathlib import Path

from scistudio.blocks.code.code_block import CodeBlock
from scistudio.blocks.io.loaders.load_data import LoadData
from scistudio.blocks.io.savers.save_data import SaveData
from scistudio.blocks.registry import BlockRegistry, _spec_from_class

# Stdlib only: writes the inherited SCISTUDIO_INPUTS_DIR to a cwd-relative
# file (cwd is the project dir), so it needs neither numpy nor the env to
# locate its output.
PROBE = (
    "import os\n"
    "from pathlib import Path\n"
    "Path('env_probe.txt').write_text(os.environ.get('SCISTUDIO_INPUTS_DIR', 'MISSING'))\n"
)


def test_find_f_python_backend_injects_exchange_env(tmp_path: Path) -> None:
    project = tmp_path
    (project / "scripts").mkdir()
    (project / "scripts" / "probe.py").write_text(PROBE, encoding="utf-8")

    reg = BlockRegistry()
    reg._register_spec(_spec_from_class(LoadData, source="alpha-findings"))
    reg._register_spec(_spec_from_class(SaveData, source="alpha-findings"))

    block = CodeBlock(
        config={
            "params": {
                "project_dir": str(project),
                "script_path": "scripts/probe.py",
                "interpreter_mode": "existing",
                "interpreter_path": sys.executable,
                "exchange_root": "exchange",
                "block_id": "find-f",
                "run_id": "run-1",
                # Deliberately NO environment_variables: probe the backend itself.
                "inputs": [],
                "outputs": [],
                "registry": reg,
            }
        }
    )
    block.run({}, block.config)

    probe = (project / "env_probe.txt").read_text(encoding="utf-8")
    assert probe != "MISSING", "Python backend should inject SCISTUDIO_INPUTS_DIR"
