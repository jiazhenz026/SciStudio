"""Alpha Task-2 Case 4: Python CodeBlock end-to-end (load Array -> script -> save).

Runs a real Python CodeBlock through file exchange: an Array input is
materialised to ``inputs/values/*.npy``; the script computes
``out = in*2 + 1`` and writes ``outputs/scaled/*.npy``; the runtime
reconstructs the output Array. Verifies the transform round-trips.

The Python backend injects no ``SCISTUDIO_*_DIR`` env (FIND-F), so the
script reads those vars when present and otherwise globs the exchange
dir under cwd. This test pins them deterministically (via the runtime's
own layout helper) through ``environment_variables`` so it is immune to
``SCISTUDIO_*`` leaked into ``os.environ`` by sibling tests under
``pytest -n auto``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

from scistudio.blocks.code.code_block import CodeBlock
from scistudio.blocks.code.exchange import create_codeblock_exchange_layout
from scistudio.blocks.io.loaders.load_data import LoadData
from scistudio.blocks.io.savers.save_data import SaveData
from scistudio.blocks.registry import BlockRegistry, _spec_from_class
from scistudio.core.types.array import Array
from scistudio.core.types.collection import Collection

SCRIPT = """\
import os
from pathlib import Path
import numpy as np


def _exchange(kind):
    env = os.environ.get(f"SCISTUDIO_{kind.upper()}_DIR")
    if env:
        return Path(env)
    cands = sorted(Path("exchange").glob(f"*/*/{kind}"), key=lambda p: p.stat().st_mtime)
    if cands:
        return cands[-1]
    raise SystemExit(f"no {kind} dir")


inputs, outputs = _exchange("inputs"), _exchange("outputs")
out_dir = outputs / "scaled"
out_dir.mkdir(parents=True, exist_ok=True)
for src in sorted((inputs / "values").glob("*.npy")):
    arr = np.load(src)
    np.save(out_dir / f"{src.stem}.npy", arr.astype("float64") * 2.0 + 1.0)
"""


def test_python_codeblock_scales_array(tmp_path: Path) -> None:
    project = tmp_path
    (project / "scripts").mkdir()
    (project / "scripts" / "process_array.py").write_text(SCRIPT, encoding="utf-8")

    data = np.arange(12, dtype=np.float64).reshape(3, 4)
    src = Array(axes=["y", "x"], shape=data.shape, dtype="float64", data=data)

    # Minimal, hermetic registry (no plugin scan) so the test does not touch
    # the global type registry shared with the rest of the -n auto suite.
    registry = BlockRegistry()
    registry._register_spec(_spec_from_class(LoadData, source="alpha-suite"))
    registry._register_spec(_spec_from_class(SaveData, source="alpha-suite"))

    # Pin the exchange dirs the runtime will use so the script is leak-immune.
    layout = create_codeblock_exchange_layout(project / "exchange", block_id="alpha-py", run_id="run-1", create=False)

    block = CodeBlock(
        config={
            "params": {
                "project_dir": str(project),
                "script_path": "scripts/process_array.py",
                "interpreter_mode": "existing",
                "interpreter_path": sys.executable,
                "exchange_root": "exchange",
                "block_id": "alpha-py",
                "run_id": "run-1",
                "environment_variables": {
                    "SCISTUDIO_INPUTS_DIR": str(layout.inputs_dir),
                    "SCISTUDIO_OUTPUTS_DIR": str(layout.outputs_dir),
                },
                "inputs": [{"name": "values", "direction": "input", "data_type": "Array", "extension": ".npy"}],
                "outputs": [{"name": "scaled", "direction": "output", "data_type": "Array", "extension": ".npy"}],
                "registry": registry,
            }
        }
    )

    outputs = block.run({"values": Collection([src])}, block.config)

    result = outputs["scaled"][0]
    assert isinstance(result, Array)
    np.testing.assert_allclose(np.asarray(result.to_memory()), data * 2.0 + 1.0)
