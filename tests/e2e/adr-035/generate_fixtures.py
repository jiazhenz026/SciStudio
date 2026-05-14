"""Generate fixtures for ADR-035 AI Block e2e test.

Writes 4 random-noise TIFFs and the ground-truth metadata.csv into the
target directory passed as the only positional argument (defaults to the
script's parent dir).

Ground truth shape (per user e2e spec, 2026-05-14):
    image_id   group   FOV
    A_01       A       01
    A_02       A       02
    B_01       B       01
    C_01       C       01

The AI Block under test will read manifest.json, parse each filename,
write a CSV at the path it chose, and signal completion via
mcp__scieasy__finish_ai_block. We then compare its output to
expected_metadata.csv byte-for-byte (after column/row sort to be
order-insensitive).

Random seed is fixed so the TIFF bytes are reproducible across runs.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import tifffile

FILENAMES = ["A_01.tiff", "A_02.tiff", "B_01.tiff", "C_01.tiff"]
RNG_SEED = 20260514
IMAGE_SHAPE = (256, 256)
DTYPE = np.uint16


def _parse_name(name: str) -> tuple[str, str, str]:
    """`A_01.tiff` -> (`A_01`, `A`, `01`)."""
    stem = Path(name).stem
    group, fov = stem.split("_")
    return stem, group, fov


def write_fixtures(target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(RNG_SEED)

    rows: list[dict[str, str]] = []
    for name in FILENAMES:
        arr = rng.integers(0, 2**16, size=IMAGE_SHAPE, dtype=DTYPE)
        tifffile.imwrite(target_dir / name, arr)
        image_id, group, fov = _parse_name(name)
        rows.append({"image_id": image_id, "group": group, "FOV": fov})

    df = pd.DataFrame(rows, columns=["image_id", "group", "FOV"])
    df.to_csv(target_dir / "expected_metadata.csv", index=False)
    print(f"wrote {len(FILENAMES)} TIFFs + expected_metadata.csv to {target_dir}")


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent
    write_fixtures(out)
