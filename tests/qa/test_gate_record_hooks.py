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
        assert "scistudio.qa.governance.gate_record" in text
        assert ".workflow/gate.py" not in text
        assert ".workflow/active" not in text


def test_pre_commit_config_exposes_gate_record_hooks() -> None:
    config = yaml.safe_load(_text(".pre-commit-config.yaml"))
    local_repo = next(repo for repo in config["repos"] if repo["repo"] == "local")
    hooks = {hook["id"]: hook for hook in local_repo["hooks"]}

    assert hooks["scistudio-gate-record-pre-commit"]["entry"] == (
        "python scripts/hooks/run_python_module.py scistudio.qa.governance.gate_record pre-commit --staged"
    )
    assert hooks["scistudio-gate-record-commit-msg"]["entry"] == (
        "python scripts/hooks/run_python_module.py scistudio.qa.governance.gate_record commit-msg"
    )
    assert hooks["scistudio-gate-record-commit-msg"]["stages"] == ["commit-msg"]


def test_pre_commit_config_uses_src_layout_launcher_for_local_python_hooks() -> None:
    config = yaml.safe_load(_text(".pre-commit-config.yaml"))
    local_repo = next(repo for repo in config["repos"] if repo["repo"] == "local")

    for hook in local_repo["hooks"]:
        assert hook["entry"].startswith("python scripts/hooks/run_python_module.py ")


def test_git_pre_commit_wrapper_uses_src_layout_launcher() -> None:
    hook = _text(".workflow/hooks/pre-commit")

    assert 'scripts" / "hooks" / "run_python_module.py' in hook
    assert "scistudio.qa.governance.gate_record" in hook


def test_legacy_gate_py_removed() -> None:
    assert not (REPO_ROOT / ".workflow" / "gate.py").exists()


def test_legacy_active_workflow_state_removed() -> None:
    assert not (REPO_ROOT / ".workflow" / "active").exists()


def test_pre_commit_does_not_branch_match_hotfix() -> None:
    assert "hotfix/" not in _text(".workflow/hooks/pre-commit")
    assert "hotfix/" not in _text(".pre-commit-config.yaml")
    assert "feat|fix|refactor|hotfix" not in _text("scripts/hooks/check-gate-before-push.sh")
    assert "feat|fix|refactor|hotfix|track" not in _text("scripts/hooks/check-gate-before-pr.sh")


def test_local_push_and_pr_hooks_accept_adr042_override_labels() -> None:
    push_hook = _text("scripts/hooks/check-gate-before-push.sh")
    pr_hook = _text("scripts/hooks/check-gate-before-pr.sh")

    for hook in (push_hook, pr_hook):
        assert "human-authored" in hook
        assert "admin-approved:ai-override" in hook
        assert "admin-approved:core-change" in hook
        assert "admin-approved:merge" in hook
        assert "SCISTUDIO_GATE_BYPASS_LABELS" in hook
        assert "ADR-042 local gate bypassed by broad override label" in hook

    assert "--label" in pr_hook
    assert 'gh", "pr", "view"' in push_hook


def test_workflow_orchestrates_adr042_governance_guards() -> None:
    workflow = _text(".github/workflows/workflow-gate.yml")

    assert "human_bypass_guard.check" in workflow
    assert "core_change_guard.check" in workflow
    assert "pr_merge_guard.check" in workflow
    assert "collaborators/{actor}/permission" in workflow
    assert "human-authored PR skips ADR-042 workflow-gate enforcement" in workflow
    assert "protected_globs=mod_guard.PROTECTED_PATTERNS" in workflow
    assert "allow_governance_change=not mod_approval_report.blocks_merge" in workflow
    assert "allow_governance_change=not core_report.blocks_merge" not in workflow
    assert "pulls/{pr_number}/reviews" in workflow
