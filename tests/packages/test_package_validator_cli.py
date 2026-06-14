from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "package_validator"


def _run_cli(fixture: str, profile: str) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        "-m",
        "scistudio.cli.package_validator",
        str(FIXTURES / fixture),
        "--profile",
        profile,
        "--json",
    ]
    return subprocess.run(command, check=False, capture_output=True, text=True)


def _json_or_xfail(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    if "No module named scistudio.cli.package_validator" in result.stderr:
        pytest.xfail("ADR-049 package validator CLI is not present in this worktree yet.")
    try:
        return cast(dict[str, Any], json.loads(result.stdout))
    except json.JSONDecodeError as exc:
        raise AssertionError(f"CLI did not emit JSON: stdout={result.stdout!r} stderr={result.stderr!r}") from exc


def test_cli_emits_json_and_zero_exit_for_valid_development_package() -> None:
    result = _run_cli("valid_package", "development")
    payload = _json_or_xfail(result)

    assert result.returncode == 0
    assert payload["schema_version"] == "adr049.package_validation_report.v1"
    assert payload["package"]["name"] == "pv-valid-package"
    assert payload["status"] in {"pass", "pass_with_warnings"}


def test_cli_emits_json_and_nonzero_exit_for_failing_production_package() -> None:
    result = _run_cli("invalid_block_package", "production")
    payload = _json_or_xfail(result)

    assert result.returncode != 0
    assert payload["status"] == "fail"
    assert payload["registration_decision"] == "reject"
    assert any(item["contract_id"] == "PV-04-001" for item in payload["findings"])
