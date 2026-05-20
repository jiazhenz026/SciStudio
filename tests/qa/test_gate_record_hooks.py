from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def _text(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_hook_wrappers_use_gate_record_cli_and_not_legacy_gate() -> None:
    paths = [
        "scripts/hooks/check-gate-before-push.sh",
        "scripts/hooks/check-gate-before-pr.sh",
        ".workflow/hooks/pre-commit",
        ".pre-commit-config.yaml",
        ".github/workflows/workflow-gate.yml",
    ]

    for path in paths:
        text = _text(path)
        assert "scieasy.qa.governance.gate_record" in text
        assert ".workflow/gate.py" not in text
        assert ".workflow/active" not in text


def test_pre_commit_config_exposes_gate_record_hooks() -> None:
    config = yaml.safe_load(_text(".pre-commit-config.yaml"))
    local_repo = next(repo for repo in config["repos"] if repo["repo"] == "local")
    hooks = {hook["id"]: hook for hook in local_repo["hooks"]}

    assert hooks["scieasy-gate-record-pre-commit"]["entry"] == (
        "python -m scieasy.qa.governance.gate_record pre-commit --staged"
    )
    assert hooks["scieasy-gate-record-commit-msg"]["entry"] == (
        "python -m scieasy.qa.governance.gate_record commit-msg"
    )
    assert hooks["scieasy-gate-record-commit-msg"]["stages"] == ["commit-msg"]


def test_legacy_gate_py_removed() -> None:
    assert not (REPO_ROOT / ".workflow" / "gate.py").exists()


def test_pre_commit_does_not_branch_match_hotfix() -> None:
    assert "hotfix/" not in _text(".workflow/hooks/pre-commit")
    assert "hotfix/" not in _text(".pre-commit-config.yaml")
