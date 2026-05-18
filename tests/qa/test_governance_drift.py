from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "scripts/audit/governance_drift.py"
spec = importlib.util.spec_from_file_location("governance_drift", MODULE_PATH)
assert spec and spec.loader
governance_drift = importlib.util.module_from_spec(spec)
spec.loader.exec_module(governance_drift)


def test_governance_drift_detects_coverage_threshold_mismatch(tmp_path: Path) -> None:
    adr = tmp_path / "docs/adr/ADR-042.md"
    pyproject = tmp_path / "pyproject.toml"
    adr.parent.mkdir(parents=True)
    adr.write_text("CI command: pytest --cov --cov-fail-under=90\n", encoding="utf-8")
    pyproject.write_text(
        """
[tool.pytest.ini_options]
addopts = "--cov=scieasy --cov-fail-under=70"

[tool.coverage.report]
fail_under = 70
""".strip(),
        encoding="utf-8",
    )

    findings = governance_drift.check(tmp_path)

    assert [finding.rule_id for finding in findings] == ["governance-drift.coverage-threshold-mismatch"]


def test_governance_drift_allows_matching_coverage_threshold(tmp_path: Path) -> None:
    adr = tmp_path / "docs/adr/ADR-042.md"
    pyproject = tmp_path / "pyproject.toml"
    adr.parent.mkdir(parents=True)
    adr.write_text("CI command: pytest --cov --cov-fail-under=90\n", encoding="utf-8")
    pyproject.write_text(
        """
[tool.pytest.ini_options]
addopts = "--cov=scieasy --cov-fail-under=90"

[tool.coverage.report]
fail_under = 90
""".strip(),
        encoding="utf-8",
    )

    assert governance_drift.check(tmp_path) == []
