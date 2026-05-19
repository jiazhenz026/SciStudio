"""Tests for ADR-042 targeted mutation runner wrappers."""

from __future__ import annotations

import json
from pathlib import Path

from scieasy.qa.test_quality.mutation_runner import run_targeted


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_mutation_runner_not_applicable_without_targets(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "core.py", "VALUE = 1\n")
    report = run_targeted(["pkg/core.py"], repo_root=tmp_path, config_path=tmp_path / "mutation.json")
    assert report.status == "not-applicable"
    assert report.killed == 0
    assert report.survived == 0


def test_mutation_runner_records_failure_when_score_below_threshold(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "core.py", ("MUTATION_SURVIVORS: 9\ndef add(a, b):\n    return a + b\n"))
    config = {
        "targets": [
            {
                "module": "pkg/core.py",
                "threshold": 0.8,
            }
        ]
    }
    config_path = tmp_path / "mutation.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    report = run_targeted(["pkg/core.py"], repo_root=tmp_path, config_path=config_path)
    assert report.status == "failed"
    assert report.score < report.threshold
    assert report.audit_report.status == "failed"


def test_mutation_runner_passes_when_above_threshold(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "core.py", ("MUTATION_SURVIVORS: 1\ndef add(a, b):\n    return a + b\n"))
    config = {
        "targets": [
            {
                "module": "pkg/core.py",
                "threshold": 0.8,
            }
        ]
    }
    config_path = tmp_path / "mutation.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    report = run_targeted(["pkg/core.py"], repo_root=tmp_path, config_path=config_path)
    assert report.status == "passed"
    assert report.score >= report.threshold
