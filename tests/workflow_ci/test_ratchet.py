"""Tests for ``ci.ratchet`` (TC-1G.1).

Covers the pure-function ratchet decision logic plus the CLI surface.
The Checks API HTTP transport is intentionally not covered here because
it is deferred to Phase 2 (CI flip) per ADR-042 §4.3.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
from ci.baselines import BASELINE_SCHEMA_VERSION, write_baseline
from ci.ratchet import (
    RatchetDecision,
    compute_ratchet_decision,
    emit_checks_api_payload,
    main,
)


def _baseline(total: int, per_file: dict[str, int] | None = None) -> dict[str, object]:
    return {
        "tool": "ruff",
        "total_findings": total,
        "per_file": dict(per_file or {}),
        "phase_1_end_sha": None,
        "schema_version": BASELINE_SCHEMA_VERSION,
    }


def test_clean_run_emits_success() -> None:
    decision = compute_ratchet_decision(
        tool="ruff",
        current_total=0,
        current_per_file={},
        previous_baseline=_baseline(0),
    )
    assert decision.conclusion == "success"
    assert decision.delta == 0
    assert decision.new_file_regressions == ()
    assert "0 findings" in decision.message


def test_monotonic_decrease_emits_neutral() -> None:
    decision = compute_ratchet_decision(
        tool="ruff",
        current_total=4,
        current_per_file={"src/a.py": 4},
        previous_baseline=_baseline(10, {"src/a.py": 10}),
    )
    assert decision.conclusion == "neutral"
    assert decision.delta == -6


def test_equal_count_no_new_file_emits_neutral() -> None:
    decision = compute_ratchet_decision(
        tool="ruff",
        current_total=5,
        current_per_file={"src/a.py": 5},
        previous_baseline=_baseline(5, {"src/a.py": 5}),
    )
    assert decision.conclusion == "neutral"
    assert decision.delta == 0


def test_count_increase_emits_failure() -> None:
    decision = compute_ratchet_decision(
        tool="ruff",
        current_total=12,
        current_per_file={"src/a.py": 12},
        previous_baseline=_baseline(10, {"src/a.py": 10}),
    )
    assert decision.conclusion == "failure"
    assert decision.delta == 2
    assert "increased" in decision.message


def test_new_file_regression_emits_failure() -> None:
    decision = compute_ratchet_decision(
        tool="ruff",
        current_total=10,
        current_per_file={"src/a.py": 7, "src/new.py": 3},
        previous_baseline=_baseline(10, {"src/a.py": 10}),
    )
    assert decision.conclusion == "failure"
    assert decision.new_file_regressions == ("src/new.py",)
    assert "previously-clean" in decision.message


def test_new_file_regression_sorted() -> None:
    decision = compute_ratchet_decision(
        tool="ruff",
        current_total=8,
        current_per_file={"src/z.py": 2, "src/a.py": 4, "src/m.py": 2},
        previous_baseline=_baseline(8, {"src/a.py": 8}),
    )
    assert decision.conclusion == "failure"
    assert decision.new_file_regressions == ("src/m.py", "src/z.py")


def test_no_per_file_skips_regression_detection() -> None:
    decision = compute_ratchet_decision(
        tool="ruff",
        current_total=5,
        current_per_file=None,
        previous_baseline=_baseline(10),
    )
    assert decision.conclusion == "neutral"
    assert decision.new_file_regressions == ()


def test_negative_current_total_raises() -> None:
    with pytest.raises(ValueError, match="current_total must be >= 0"):
        compute_ratchet_decision(
            tool="ruff",
            current_total=-1,
            current_per_file=None,
            previous_baseline=_baseline(0),
        )


def test_emit_checks_api_payload_neutral() -> None:
    decision = RatchetDecision(
        tool="ruff",
        conclusion="neutral",
        previous_total=10,
        current_total=8,
        delta=-2,
        new_file_regressions=(),
        message="ruff: 10 -> 8.",
    )
    payload = emit_checks_api_payload(decision)
    assert payload["status"] == "completed"
    assert payload["conclusion"] == "neutral"
    assert payload["output"]["title"] == "ruff: 10 -> 8."
    assert "previous_total" in payload["output"]["summary"]
    assert "**neutral**" in payload["output"]["summary"]


def test_emit_checks_api_payload_failure_lists_regressions() -> None:
    decision = RatchetDecision(
        tool="ruff",
        conclusion="failure",
        previous_total=8,
        current_total=10,
        delta=2,
        new_file_regressions=("src/new.py",),
        message="ruff regressed",
    )
    payload = emit_checks_api_payload(decision)
    assert payload["conclusion"] == "failure"
    summary = payload["output"]["summary"]
    assert "New-file regressions" in summary
    assert "src/new.py" in summary


def test_ratchet_decision_is_frozen() -> None:
    decision = compute_ratchet_decision(
        tool="ruff",
        current_total=0,
        current_per_file={},
        previous_baseline=_baseline(0),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.tool = "mypy"  # type: ignore[misc]


def _write_current(tmp_path: Path, *, total: int, per_file: dict[str, int] | None = None) -> Path:
    payload: dict[str, object] = {"total": total}
    if per_file is not None:
        payload["per_file"] = per_file
    p = tmp_path / "current.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def test_main_neutral_exits_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_baseline("ruff", total_findings=10, per_file={}, base_dir=tmp_path)
    current = _write_current(tmp_path, total=5)
    rc = main(
        [
            "--tool",
            "ruff",
            "--current",
            str(current),
            "--baselines-dir",
            str(tmp_path),
        ],
    )
    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["conclusion"] == "neutral"
    assert parsed["previous_total"] == 10
    assert parsed["current_total"] == 5


def test_main_failure_exits_one(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_baseline("ruff", total_findings=5, per_file={}, base_dir=tmp_path)
    current = _write_current(tmp_path, total=12)
    rc = main(
        [
            "--tool",
            "ruff",
            "--current",
            str(current),
            "--baselines-dir",
            str(tmp_path),
        ],
    )
    assert rc == 1
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["conclusion"] == "failure"


def test_main_emit_payload_flag(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_baseline("ruff", total_findings=5, per_file={}, base_dir=tmp_path)
    current = _write_current(tmp_path, total=5)
    rc = main(
        [
            "--tool",
            "ruff",
            "--current",
            str(current),
            "--baselines-dir",
            str(tmp_path),
            "--emit-payload",
        ],
    )
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "completed"
    assert out["conclusion"] == "neutral"


def test_main_missing_total_in_current_raises(tmp_path: Path) -> None:
    write_baseline("ruff", total_findings=0, per_file={}, base_dir=tmp_path)
    current = tmp_path / "current.json"
    current.write_text(json.dumps({"per_file": {}}), encoding="utf-8")
    with pytest.raises(SystemExit, match="missing 'total'"):
        main(
            [
                "--tool",
                "ruff",
                "--current",
                str(current),
                "--baselines-dir",
                str(tmp_path),
            ],
        )


def test_main_with_per_file_detects_new_file_regression(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_baseline(
        "ruff",
        total_findings=5,
        per_file={"src/a.py": 5},
        base_dir=tmp_path,
    )
    current = _write_current(
        tmp_path,
        total=5,
        per_file={"src/a.py": 3, "src/new.py": 2},
    )
    rc = main(
        [
            "--tool",
            "ruff",
            "--current",
            str(current),
            "--baselines-dir",
            str(tmp_path),
        ],
    )
    assert rc == 1
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["conclusion"] == "failure"
    assert parsed["new_file_regressions"] == ["src/new.py"]
