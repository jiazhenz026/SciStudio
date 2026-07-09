"""ADR-043 Phase D E2E-001 OME propagation verification.

In-process Load → SRS Calibrate → Axis Projection (max along lambda)
chain. Dumps ``image.meta.ome`` (canonical OME) plus ``meta.physical_size_x``
/ ``meta.wavenumbers_cm1`` at each step.

This is the SC-005-adjacent direct-evidence script — the indirect evidence
that the umbrella's first 5 blocks all completed Done in the Chrome run is
necessary but not sufficient. This script proves the OME fields are still
populated (not silently dropped) at each step.

Run from the hotfix worktree:
    PYTHONPATH=src python scripts/verify_ome_propagation_e2e001.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

FIXTURE = Path(r"C:/Users/<user>/Desktop/workspace/scistudio-e2e-microplastic/data/raw/50nm_2800-3200-40.tif")

WAVENUMBERS = [2800.0 + i * (3200.0 - 2800.0) / 39 for i in range(40)]


def _ome_summary(image: Any, label: str) -> dict[str, Any]:
    meta = getattr(image, "meta", None)
    if meta is None:
        return {"label": label, "meta": None}
    out: dict[str, Any] = {
        "label": label,
        "axes": getattr(image, "axes", None),
        "shape": getattr(image, "shape", None),
        "meta.physical_size_x": getattr(meta, "physical_size_x", "MISSING"),
        "meta.physical_size_y": getattr(meta, "physical_size_y", "MISSING"),
        "meta.physical_size_z": getattr(meta, "physical_size_z", "MISSING"),
        "meta.source_file": getattr(meta, "source_file", "MISSING"),
        "meta.wavenumbers_cm1.len": (
            len(meta.wavenumbers_cm1) if getattr(meta, "wavenumbers_cm1", None) is not None else None
        ),
    }
    ome = getattr(meta, "ome", None)
    if ome is None:
        out["meta.ome"] = None
    else:
        try:
            ome_dict: dict[str, Any] = {
                "type": type(ome).__name__,
                "image_count": len(getattr(ome, "images", []) or []),
            }
            if getattr(ome, "images", None):
                first = ome.images[0]
                pixels = getattr(first, "pixels", None)
                if pixels is not None:
                    ome_dict["pixels.physical_size_x"] = getattr(pixels, "physical_size_x", "MISSING")
                    ome_dict["pixels.physical_size_y"] = getattr(pixels, "physical_size_y", "MISSING")
                    ome_dict["pixels.size_x"] = getattr(pixels, "size_x", "MISSING")
                    ome_dict["pixels.size_y"] = getattr(pixels, "size_y", "MISSING")
                    ome_dict["pixels.size_c"] = getattr(pixels, "size_c", "MISSING")
                    ome_dict["pixels.channels.len"] = len(getattr(pixels, "channels", []) or [])
            out["meta.ome"] = ome_dict
        except Exception as exc:
            out["meta.ome"] = f"INSPECT_FAILED: {exc!r}"
    return out


def main() -> int:
    print(f"loading: {FIXTURE}")
    if not FIXTURE.exists():
        print(f"FIXTURE MISSING: {FIXTURE}", file=sys.stderr)
        return 2

    from scistudio_blocks_imaging.io.load_image import LoadImage
    from scistudio_blocks_imaging.projection.projection import AxisProjection
    from scistudio_blocks_srs.preprocess.srs_calibrate import SRSCalibrate

    from scistudio.core.types.dataframe import DataFrame  # noqa: F401  ensure init

    BlockConfig = dict  # noqa: N806 — ad-hoc alias for the test script

    # Step 1: LoadImage
    loader = LoadImage()
    load_config = BlockConfig(
        {
            "path": str(FIXTURE),
            "axes": "lambda,y,x",
        }
    )
    loaded = loader.load(load_config)
    # Collection may expose items via attribute or be directly iterable.
    items = getattr(loaded, "items", None)
    if items is None:
        items = list(loaded)
    img0 = items[0]
    print(json.dumps(_ome_summary(img0, "step1.LoadImage"), default=str, indent=2))

    # Step 2: SRSCalibrate
    calib = SRSCalibrate()
    calib_config = BlockConfig(
        {
            "scale": 50000.0,
            "offset": 1.0,
            "bit_depth": 4096,
            "voltage_range": 10.0,
            "wavenumbers_cm1": WAVENUMBERS,
        }
    )
    calib_result = calib.run({"image": loaded}, calib_config)
    srs_collection = calib_result.get("srs_image") or calib_result.get("image")
    assert srs_collection is not None, f"calibrate returned: {list(calib_result.keys())}"
    srs_items = getattr(srs_collection, "items", None) or list(srs_collection)
    srs0 = srs_items[0]
    print(json.dumps(_ome_summary(srs0, "step2.SRSCalibrate"), default=str, indent=2))

    # Step 3: AxisProjection (max along lambda)
    proj = AxisProjection()
    proj_config = BlockConfig({"axis": "lambda", "method": "max"})
    proj_result = proj.run({"image": srs_collection}, proj_config)
    proj_collection = proj_result.get("projected") or proj_result.get("image")
    assert proj_collection is not None, f"projection returned: {list(proj_result.keys())}"
    proj_items = getattr(proj_collection, "items", None) or list(proj_collection)
    proj0 = proj_items[0]
    print(json.dumps(_ome_summary(proj0, "step3.AxisProjection"), default=str, indent=2))

    # Pass/fail summary
    print("\n=== OME PROPAGATION SUMMARY ===")
    failures: list[str] = []
    for label, img in [
        ("LoadImage", img0),
        ("SRSCalibrate", srs0),
        ("AxisProjection", proj0),
    ]:
        meta = getattr(img, "meta", None)
        ome = getattr(meta, "ome", None) if meta else None
        if ome is None:
            failures.append(f"{label}: meta.ome is None")
        else:
            ic = len(getattr(ome, "images", []) or [])
            if ic == 0:
                failures.append(f"{label}: meta.ome.images is empty")
        if meta is None:
            failures.append(f"{label}: meta is None")
    if failures:
        print("FAIL")
        for f in failures:
            print(" -", f)
        return 1
    print("PASS — OME propagated through LoadImage → SRSCalibrate → AxisProjection")
    return 0


if __name__ == "__main__":
    sys.exit(main())
