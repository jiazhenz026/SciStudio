"""Tests for ``scistudio.qa.audit.semantic_dup``.

The wrapper subprocesses ``scripts/semantic_dup_scan.py`` for higher-
fidelity local full-audit runs (ADR-042 Addendum 2 §3 two-tier model
policy). These tests cover the three branches of the wrapper without
ever invoking the actual embedding subprocess (which would be ~30-90s
and pull fastembed weights):

- script-missing fallback (repo without the scanner)
- subprocess-failure fallback (script exits non-zero)
- happy path (script writes JSON payload that the wrapper parses into
  the AuditReport summary)
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scistudio.qa.audit import semantic_dup
from scistudio.qa.schemas.report import AuditStatus


def test_script_missing_returns_advisory_pass(tmp_path: Path) -> None:
    report = semantic_dup.check_semantic_dup(tmp_path)

    assert report.tool == "semantic_dup"
    assert report.status == AuditStatus.PASS
    assert report.summary["included"] is False
    assert report.summary["reason"] == "script-missing"
    assert [f.rule_id for f in report.findings] == ["semantic-dup.script-missing"]


def test_subprocess_failure_returns_advisory_pass_with_warning(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "semantic_dup_scan.py").write_text("# stub", encoding="utf-8")

    def _fail(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=2, stdout="", stderr="boom")

    monkeypatch.setattr(semantic_dup.subprocess, "run", _fail)

    report = semantic_dup.check_semantic_dup(tmp_path)

    assert report.status == AuditStatus.PASS  # advisory — never blocks parent
    assert report.summary["included"] is True
    assert report.summary["subprocess_exit"] == 2
    assert [f.rule_id for f in report.findings] == ["semantic-dup.subprocess-failed"]


def test_happy_path_parses_metrics_into_summary(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "semantic_dup_scan.py").write_text("# stub", encoding="utf-8")

    def _success(cmd, **kwargs):
        json_out_idx = cmd.index("--json-out") + 1
        Path(cmd[json_out_idx]).parent.mkdir(parents=True, exist_ok=True)
        Path(cmd[json_out_idx]).write_text(
            json.dumps(
                {
                    "metrics": {
                        "functions_scanned": 1253,
                        "clusters": 60,
                        "duplicate_loc": 3474,
                        "total_loc": 34636,
                        "duplicate_pct": 10.03,
                        "max_cluster_size": 9,
                    }
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(semantic_dup.subprocess, "run", _success)

    report = semantic_dup.check_semantic_dup(tmp_path, model="BAAI/bge-base-en-v1.5")

    assert report.status == AuditStatus.PASS
    assert report.findings == []
    assert report.summary["included"] is True
    assert report.summary["model"] == "BAAI/bge-base-en-v1.5"
    assert report.summary["clusters"] == 60
    assert report.summary["duplicate_pct"] == 10.03
    assert report.summary["max_cluster_size"] == 9


def test_default_model_is_bge_base() -> None:
    # The CI ratchet uses BGE-small (faster); local full-audit invocation
    # opts up to BGE-base for higher-fidelity cluster detection.
    assert semantic_dup.DEFAULT_AUDIT_MODEL == "BAAI/bge-base-en-v1.5"
