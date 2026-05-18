"""Tests for ``ci.baselines``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ci import baselines
from ci.baselines import (
    BASELINE_SCHEMA_VERSION,
    BaselineError,
    baseline_path,
    read_baseline,
    write_baseline,
)


def test_baseline_path_default_dir() -> None:
    p = baseline_path("ruff")
    assert p == Path("docs/audit/baselines/ruff.json")


def test_baseline_path_custom_dir(tmp_path: Path) -> None:
    p = baseline_path("mypy", tmp_path)
    assert p == tmp_path / "mypy.json"


def test_read_missing_returns_zero_baseline(tmp_path: Path) -> None:
    data = read_baseline("ruff", tmp_path)
    assert data == {
        "tool": "ruff",
        "total_findings": 0,
        "per_file": {},
        "phase_1_end_sha": None,
        "schema_version": BASELINE_SCHEMA_VERSION,
    }


def test_write_and_read_round_trip(tmp_path: Path) -> None:
    write_baseline(
        "ruff",
        total_findings=5,
        per_file={"src/a.py": 2, "src/b.py": 3},
        phase_1_end_sha="abc1234",
        base_dir=tmp_path,
    )
    data = read_baseline("ruff", tmp_path)
    assert data["total_findings"] == 5
    assert data["per_file"] == {"src/a.py": 2, "src/b.py": 3}
    assert data["phase_1_end_sha"] == "abc1234"
    assert data["schema_version"] == BASELINE_SCHEMA_VERSION


def test_write_sorts_per_file_keys(tmp_path: Path) -> None:
    write_baseline(
        "ruff",
        total_findings=3,
        per_file={"src/z.py": 1, "src/a.py": 1, "src/m.py": 1},
        base_dir=tmp_path,
    )
    raw = (tmp_path / "ruff.json").read_text(encoding="utf-8")
    payload = json.loads(raw)
    assert list(payload["per_file"].keys()) == ["src/a.py", "src/m.py", "src/z.py"]


def test_write_negative_total_raises(tmp_path: Path) -> None:
    with pytest.raises(BaselineError, match="total_findings must be >= 0"):
        write_baseline("ruff", total_findings=-1, per_file={}, base_dir=tmp_path)


def test_write_negative_per_file_raises(tmp_path: Path) -> None:
    with pytest.raises(BaselineError, match="per_file counts must be >= 0"):
        write_baseline("ruff", total_findings=0, per_file={"src/a.py": -1}, base_dir=tmp_path)


def test_read_invalid_json_raises(tmp_path: Path) -> None:
    path = tmp_path / "ruff.json"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(BaselineError, match="not valid JSON"):
        read_baseline("ruff", tmp_path)


def test_read_missing_keys_raises(tmp_path: Path) -> None:
    path = tmp_path / "ruff.json"
    path.write_text(json.dumps({"tool": "ruff"}), encoding="utf-8")
    with pytest.raises(BaselineError, match="missing keys"):
        read_baseline("ruff", tmp_path)


def test_read_wrong_schema_version_raises(tmp_path: Path) -> None:
    path = tmp_path / "ruff.json"
    path.write_text(
        json.dumps(
            {
                "tool": "ruff",
                "total_findings": 0,
                "per_file": {},
                "schema_version": "9.9",
            },
        ),
        encoding="utf-8",
    )
    with pytest.raises(BaselineError, match="schema_version"):
        read_baseline("ruff", tmp_path)


def test_read_negative_total_raises(tmp_path: Path) -> None:
    path = tmp_path / "ruff.json"
    path.write_text(
        json.dumps(
            {
                "tool": "ruff",
                "total_findings": -1,
                "per_file": {},
                "schema_version": BASELINE_SCHEMA_VERSION,
            },
        ),
        encoding="utf-8",
    )
    with pytest.raises(BaselineError, match="non-negative int"):
        read_baseline("ruff", tmp_path)


def test_read_per_file_not_dict_raises(tmp_path: Path) -> None:
    path = tmp_path / "ruff.json"
    path.write_text(
        json.dumps(
            {
                "tool": "ruff",
                "total_findings": 0,
                "per_file": [],
                "schema_version": BASELINE_SCHEMA_VERSION,
            },
        ),
        encoding="utf-8",
    )
    with pytest.raises(BaselineError, match="per_file must be an object"):
        read_baseline("ruff", tmp_path)


def test_read_per_file_bad_value_raises(tmp_path: Path) -> None:
    path = tmp_path / "ruff.json"
    path.write_text(
        json.dumps(
            {
                "tool": "ruff",
                "total_findings": 0,
                "per_file": {"src/a.py": -3},
                "schema_version": BASELINE_SCHEMA_VERSION,
            },
        ),
        encoding="utf-8",
    )
    with pytest.raises(BaselineError, match=r"per_file\[.+\]"):
        read_baseline("ruff", tmp_path)


def test_seed_baselines_on_disk_are_valid() -> None:
    """Every seed file shipped under docs/audit/baselines/ must validate."""
    seed_dir = Path("docs/audit/baselines")
    if not seed_dir.exists():
        pytest.skip("seed baselines not present in this checkout")
    for path in seed_dir.glob("*.json"):
        data = read_baseline(path.stem, seed_dir)
        assert data["tool"] == path.stem
        assert data["total_findings"] == 0
        assert data["per_file"] == {}
        assert data["schema_version"] == BASELINE_SCHEMA_VERSION


def test_module_default_dir_constant() -> None:
    assert Path("docs/audit/baselines") == baselines.DEFAULT_BASELINES_DIR
