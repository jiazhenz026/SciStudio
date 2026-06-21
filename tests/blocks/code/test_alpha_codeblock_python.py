"""Alpha Task-2 Case 4: Python CodeBlock end-to-end (load Array -> script -> save).

Runs a real Python CodeBlock through file exchange: an Array input is
materialised to ``inputs/values/*.npy``; the script computes
``out = in*2 + 1`` and writes ``outputs/scaled/*.npy``; the runtime
reconstructs the output Array. Verifies the transform round-trips.

The script discovers the exchange dirs via ``SCISTUDIO_*_DIR`` env vars
when present and otherwise globs the newest exchange dir under cwd
(workaround for FIND-F: the Python backend injects no exchange env).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

from scistudio.blocks.base.config import BlockConfig
from scistudio.blocks.code.code_block import CodeBlock
from scistudio.blocks.registry import BlockRegistry
from scistudio.core.types.array import Array
from scistudio.core.types.collection import Collection

SCRIPT = '''\
import os
from pathlib import Path
import numpy as np


def _exchange(kind):
    env = os.environ.get(f"SCISTUDIO_{kind.upper()}_DIR")
    if env:
        return Path(env)
    cands = sorted(Path("exchange").glob(f"*/*/{kind}"), key=lambda p: p.stat().st_mtime)
    if not cands:
        raise SystemExit(f"no {kind} dir")
    return cands[-1]


inputs, outputs = _exchange("inputs"), _exchange("outputs")
out_dir = outputs / "scaled"
out_dir.mkdir(parents=True, exist_ok=True)
for src in sorted((inputs / "values").glob("*.npy")):
    arr = np.load(src)
    np.save(out_dir / f"{src.stem}.npy", arr.astype("float64") * 2.0 + 1.0)
'''


@pytest.fixture
def _registry() -> BlockRegistry:
    reg = BlockRegistry()
    reg.scan(include_monorepo=False)
    return reg


def test_python_codeblock_scales_array(tmp_path: Path, _registry: BlockRegistry) -> None:
    project = tmp_path
    (project / "scripts").mkdir()
    (project / "scripts" / "process_array.py").write_text(SCRIPT, encoding="utf-8")

    data = np.arange(12, dtype=np.float64).reshape(3, 4)
    src = Array(axes=["y", "x"], shape=data.shape, dtype="float64", data=data)

    block = CodeBlock(config={"params": {
        "project_dir": str(project),
        "script_path": "scripts/process_array.py",
        "interpreter_mode": "existing",
        "interpreter_path": sys.executable,
        "exchange_root": "exchange",
        "block_id": "alpha-py", "run_id": "run-1",
        "inputs": [{"name": "values", "direction": "input", "data_type": "Array", "extension": ".npy"}],
        "outputs": [{"name": "scaled", "direction": "output", "data_type": "Array", "extension": ".npy"}],
        "registry": _registry,
    }})

    outputs = block.run({"values": Collection([src])}, block.config)

    result = outputs["scaled"][0]
    assert isinstance(result, Array)
    np.testing.assert_allclose(np.asarray(result.to_memory()), data * 2.0 + 1.0)
