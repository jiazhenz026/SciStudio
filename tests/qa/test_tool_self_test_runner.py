from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))
for module_name in list(sys.modules):
    if module_name == "scieasy" or module_name.startswith("scieasy."):
        del sys.modules[module_name]

from scieasy.qa.tracker.tool_self_test_runner import TOOL_SELF_TEST_ARTIFACTS, run_self_test  # noqa: E402


def test_self_test_artifact_missing_produces_finding(tmp_path: Path) -> None:
    findings = run_self_test("frontmatter_lint", tmp_path)

    assert len(findings) == 1
    assert findings[0].rule_id == "tool-self-test.missing-artifact"


def test_self_test_artifact_valid_json_passes(tmp_path: Path) -> None:
    relative_path = TOOL_SELF_TEST_ARTIFACTS["frontmatter_lint"]
    artifact = tmp_path / relative_path
    artifact.parent.mkdir(parents=True)
    artifact.write_text('{"tool": "frontmatter_lint", "target": "ADR-042"}', encoding="utf-8")

    assert run_self_test("frontmatter_lint", tmp_path) == []


def test_self_test_cli_missing_artifact_has_clear_output(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/audit/tool_self_test_runner.py"),
            "frontmatter_lint",
            "--repo-root",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 1
    assert "missing mandatory ADR-042 self-test artifact" in result.stdout
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr
