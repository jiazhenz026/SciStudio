"""Tests for interactive imaging AppBlocks using fake external tools.

Issue #680: per-plugin output classification heuristics
(``_collect_outputs`` / ``_guess_output_port``) were removed in favour of
the generic extension-based binner on ``AppBlock``. These tests now assert
that output files are wrapped as :class:`Artifact` instances and routed
into the user-declared output ports (or the fallback ``image`` port when
no ports are declared).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from scieasy_blocks_imaging.interactive.fiji_block import FijiBlock
from scieasy_blocks_imaging.interactive.napari_block import NapariBlock
from scieasy_blocks_imaging.types import Image

from scieasy.blocks.base.config import BlockConfig
from scieasy.blocks.base.state import BlockState
from scieasy.core.types.artifact import Artifact
from scieasy.core.types.collection import Collection


def _make_image(arr: np.ndarray, axes: list[str] | None = None) -> Image:
    image = Image(axes=axes or ["y", "x"], shape=arr.shape, dtype=arr.dtype)
    image._data = arr  # type: ignore[attr-defined]
    return image


def _make_running(block: object) -> object:
    block.transition(BlockState.READY)  # type: ignore[attr-defined]
    block.transition(BlockState.RUNNING)  # type: ignore[attr-defined]
    return block


def _write_fake_tool(tmp_path: Path, body: str) -> Path:
    script = tmp_path / "fake_tool.py"
    script.write_text(body, encoding="utf-8")
    return script


def test_fiji_block_routes_image_outputs(tmp_path: Path) -> None:
    # FijiBlock (no macro) now passes staged TIFF paths as trailing args (#420).
    # The fake tool receives the TIFF path as sys.argv[-1] and copies it to outputs/.
    script = _write_fake_tool(
        tmp_path,
        """
from pathlib import Path
import shutil
import sys

tiff_path = Path(sys.argv[-1])
output_dir = tiff_path.parent.parent / "outputs"
output_dir.mkdir(exist_ok=True)
shutil.copyfile(tiff_path, output_dir / "image_reviewed.tif")
""".strip(),
    )
    block = _make_running(FijiBlock())
    image = _make_image(np.arange(16, dtype=np.uint8).reshape(4, 4))

    result = block.run(
        {"image": Collection(items=[image], item_type=Image)},
        BlockConfig(params={"app_command": [sys.executable, str(script)], "watch_timeout": 5}),
    )

    assert "image" in result
    assert result["image"].length == 1
    assert isinstance(result["image"][0], Artifact)
    assert result["image"][0].file_path is not None


def test_fiji_block_passes_staged_tiff_paths_to_fiji_when_no_macro(tmp_path: Path) -> None:
    """FijiBlock must pass the staged TIFF file paths (not exchange_dir) to Fiji (#420).

    The fake tool receives the staged TIFF as sys.argv[-1] (the last arg), opens it,
    and copies it to outputs/. This proves the file path was passed, not the directory.
    """
    script = _write_fake_tool(
        tmp_path,
        """
from pathlib import Path
import shutil
import sys

# When no macro is set, FijiBlock passes individual TIFF paths as trailing args.
# The last arg is the staged TIFF file (not the exchange dir root).
tiff_path = Path(sys.argv[-1])
assert tiff_path.suffix == ".tif", f"Expected .tif, got {tiff_path}"
assert tiff_path.is_file(), f"File not found: {tiff_path}"

output_dir = tiff_path.parent.parent / "outputs"
output_dir.mkdir(exist_ok=True)
shutil.copyfile(tiff_path, output_dir / "image_from_fiji.tif")
""".strip(),
    )
    block = _make_running(FijiBlock())
    image = _make_image(np.arange(16, dtype=np.uint8).reshape(4, 4))

    result = block.run(
        {"image": Collection(items=[image], item_type=Image)},
        BlockConfig(params={"app_command": [sys.executable, str(script)], "watch_timeout": 5}),
    )

    assert "image" in result
    assert result["image"].length == 1


def test_fiji_block_passes_multiple_staged_tiff_paths_when_multiple_images(tmp_path: Path) -> None:
    """When multiple images are input, all staged TIFF paths are passed to Fiji (#420)."""
    script = _write_fake_tool(
        tmp_path,
        """
from pathlib import Path
import shutil
import sys

# All staged TIFFs are passed as trailing args.
tiff_paths = [Path(arg) for arg in sys.argv[1:] if arg.endswith(".tif")]
assert len(tiff_paths) == 2, f"Expected 2 TIFFs, got {len(tiff_paths)}: {sys.argv[1:]}"

output_dir = tiff_paths[0].parent.parent / "outputs"
output_dir.mkdir(exist_ok=True)
shutil.copyfile(tiff_paths[0], output_dir / "image_0.tif")
shutil.copyfile(tiff_paths[1], output_dir / "image_1.tif")
""".strip(),
    )
    block = _make_running(FijiBlock())
    images = [
        _make_image(np.arange(16, dtype=np.uint8).reshape(4, 4)),
        _make_image(np.arange(16, 32, dtype=np.uint8).reshape(4, 4)),
    ]

    result = block.run(
        {"image": Collection(items=images, item_type=Image)},
        BlockConfig(params={"app_command": [sys.executable, str(script)], "watch_timeout": 5}),
    )

    assert "image" in result
    assert result["image"].length == 2


def test_fiji_block_passes_exchange_dir_when_macro_is_set(tmp_path: Path) -> None:
    """When a macro_path is set, FijiBlock passes exchange_dir (headless mode), not file paths (#420).

    In macro mode, the script reads inputs from the exchange directory itself.
    The old behavior of passing exchange_dir as the last arg must be preserved.
    """
    macro_file = tmp_path / "macro.ijm"
    macro_file.write_text("// fake Fiji macro", encoding="utf-8")

    script = _write_fake_tool(
        tmp_path,
        """
from pathlib import Path
import shutil
import sys

# In macro mode the last arg after the macro path is the exchange dir root.
# sys.argv = [script, "--headless", "-macro", macro_path, exchange_dir]
exchange = Path(sys.argv[-1])
assert exchange.is_dir(), f"Expected exchange dir, got: {exchange}"

source = next((exchange / "inputs").glob("*.tif"))
target = exchange / "outputs" / "image_macro_out.tif"
target.parent.mkdir(exist_ok=True)
shutil.copyfile(source, target)
""".strip(),
    )
    block = _make_running(FijiBlock())
    image = _make_image(np.arange(16, dtype=np.uint8).reshape(4, 4))

    result = block.run(
        {"image": Collection(items=[image], item_type=Image)},
        BlockConfig(
            params={
                "app_command": [sys.executable, str(script)],
                "macro_path": str(macro_file),
                "watch_timeout": 5,
            }
        ),
    )

    assert "image" in result
    assert result["image"].length == 1


def test_napari_block_routes_image_outputs(tmp_path: Path) -> None:
    script = _write_fake_tool(
        tmp_path,
        """
from pathlib import Path
import shutil
import sys

# NapariBlock passes the staged TIFF path as the trailing arg
# (consistent with FijiBlock #420).
tiff_path = Path(sys.argv[-1])
output_dir = tiff_path.parent.parent / "outputs"
output_dir.mkdir(exist_ok=True)
shutil.copyfile(tiff_path, output_dir / "image_layer.tif")
""".strip(),
    )
    block = _make_running(NapariBlock())
    image = _make_image(np.arange(25, dtype=np.uint8).reshape(5, 5))

    result = block.run(
        {"image": Collection(items=[image], item_type=Image)},
        BlockConfig(params={"app_command": [sys.executable, str(script)], "watch_timeout": 5}),
    )

    assert "image" in result
    assert result["image"].length == 1
    assert isinstance(result["image"][0], Artifact)
    assert result["image"][0].file_path is not None


def test_fiji_block_routes_outputs_into_user_declared_ports_by_extension(tmp_path: Path) -> None:
    """Issue #680: when the user declares output_ports with extensions, the
    binner routes saved files into those ports — bypassing the legacy
    fallback path. Verify FijiBlock end-to-end with a user-defined port set.
    """
    script = _write_fake_tool(
        tmp_path,
        """
from pathlib import Path
import shutil
import sys

# Save a .tif AND a .csv to outputs/.
tiff_path = Path(sys.argv[-1])
out = tiff_path.parent.parent / "outputs"
out.mkdir(exist_ok=True)
shutil.copyfile(tiff_path, out / "result.tif")
(out / "summary.csv").write_text("col\\n1\\n", encoding="utf-8")
""".strip(),
    )
    block = _make_running(FijiBlock())
    image = _make_image(np.arange(16, dtype=np.uint8).reshape(4, 4))

    result = block.run(
        {"image": Collection(items=[image], item_type=Image)},
        BlockConfig(
            params={
                "app_command": [sys.executable, str(script)],
                "watch_timeout": 5,
                "output_patterns": ["*.tif", "*.csv"],
                "output_ports": [
                    {"name": "images", "types": ["DataObject"], "extension": "tif"},
                    {"name": "tables", "types": ["DataObject"], "extension": "csv"},
                ],
            }
        ),
    )

    assert set(result.keys()) == {"images", "tables"}
    assert result["images"].length == 1
    assert result["tables"].length == 1
    assert isinstance(result["images"][0], Artifact)
    assert result["images"][0].file_path is not None
    assert result["images"][0].file_path.suffix.lower() == ".tif"
    assert result["tables"][0].file_path.suffix.lower() == ".csv"
