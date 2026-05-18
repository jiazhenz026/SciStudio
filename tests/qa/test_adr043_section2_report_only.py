from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "scripts/audit/adr043_section2_report_only.py"
spec = importlib.util.spec_from_file_location("adr043_section2_report_only", MODULE_PATH)
assert spec and spec.loader
adr043_report_only = importlib.util.module_from_spec(spec)
sys.modules["adr043_section2_report_only"] = adr043_report_only
spec.loader.exec_module(adr043_report_only)


def test_nonzero_tool_exit_is_report_only_finding(monkeypatch, tmp_path: Path) -> None:
    def fake_run(command: list[str], **kwargs: Any) -> SimpleNamespace:
        if command[0] == "git":
            return SimpleNamespace(returncode=0, stdout="local/adr043-report-only-wiring\n", stderr="")
        return SimpleNamespace(returncode=2, stdout="drift found", stderr="warning")

    monkeypatch.setattr(adr043_report_only.subprocess, "run", fake_run)

    report = adr043_report_only.build_report(tmp_path)

    assert report["report_only"] is True
    assert report["classification"] == "finding"
    assert {command["classification"] for command in report["commands"]} == {"finding"}
    assert {command["exit_code"] for command in report["commands"]} == {2}


def test_main_writes_report_and_returns_zero_for_findings(monkeypatch, tmp_path: Path) -> None:
    def fake_build_report(repo_root: Path) -> dict[str, object]:
        return {
            "repo_root": str(repo_root),
            "report_only": True,
            "classification": "finding",
            "commands": [
                {
                    "name": "stub",
                    "command": ["stub"],
                    "exit_code": 1,
                    "classification": "finding",
                    "report_only": True,
                    "hard_fail_later": "TODO(#1113): keep report-only until owner final CI pass.",
                    "stdout": "finding",
                    "stderr": "",
                    "manual_note": None,
                }
            ],
        }

    monkeypatch.setattr(adr043_report_only, "build_report", fake_build_report)
    output = tmp_path / "report.json"

    exit_code = adr043_report_only.main(["--repo-root", str(tmp_path), "--output", str(output)])

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["classification"] == "finding"
    assert payload["commands"][0]["exit_code"] == 1


def test_addendum_propagate_uses_help_only_probe() -> None:
    addendum_specs = [
        item for item in adr043_report_only.SECTION2_COMMANDS if item.name == "addendum_propagate_help_probe"
    ]

    assert len(addendum_specs) == 1
    assert addendum_specs[0].command[-1] == "--help"
    assert "writes tracker rows" in addendum_specs[0].manual_note
