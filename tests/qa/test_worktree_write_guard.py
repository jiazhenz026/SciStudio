from __future__ import annotations

import json
from pathlib import Path

import pytest

from scistudio.qa.governance.worktree_write_guard import check_hook_payload, check_paths


def _record(path: Path, *, branch: str = "feat/guard") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "task_id": "1492-worktree-guard",
                "task_kind": "maintenance",
                "persona": "implementer",
                "branch": branch,
                "owner_directive": "test",
                "issues": [{"number": 1492, "url": "https://github.com/zjzcpj/SciStudio/issues/1492"}],
                "scope": {"include": ["src/allowed.py"], "exclude": ["src/blocked.py"]},
                "governance_touch": True,
                "stages": [
                    {"stage": "scope_and_issue", "status": "done"},
                    {"stage": "plan", "status": "done"},
                    {"stage": "implement", "status": "done"},
                    {"stage": "update_docs", "status": "done"},
                    {"stage": "test_and_checks", "status": "done"},
                    {"stage": "commit_and_submit_pr", "status": "pending"},
                ],
            }
        ),
        encoding="utf-8",
    )


def test_check_paths_blocks_main_branch(tmp_path: Path) -> None:
    record = tmp_path / ".workflow" / "records" / "1492.json"
    _record(record, branch="main")

    errors = check_paths(repo_root=tmp_path, gate_record=record, branch="main", target_paths=["src/allowed.py"])

    assert any("dedicated non-main branch" in error for error in errors)


def test_check_paths_blocks_outside_worktree_and_scope(tmp_path: Path) -> None:
    record = tmp_path / ".workflow" / "records" / "1492.json"
    _record(record)
    outside = tmp_path.parent / "outside.py"

    errors = check_paths(
        repo_root=tmp_path,
        gate_record=record,
        branch="feat/guard",
        target_paths=["src/other.py", str(outside)],
    )

    joined = "\n".join(errors)
    assert "outside gate scope include patterns" in joined
    assert "outside the assigned worktree" in joined


def test_check_hook_payload_extracts_write_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    record = tmp_path / ".workflow" / "records" / "1492.json"
    _record(record)

    def fake_repo_root(start: Path) -> Path:
        return tmp_path

    def fake_branch(root: Path) -> str:
        return "feat/guard"

    monkeypatch.setattr("scistudio.qa.governance.worktree_write_guard._repo_root", fake_repo_root)
    monkeypatch.setattr("scistudio.qa.governance.worktree_write_guard._branch", fake_branch)

    errors = check_hook_payload({"cwd": str(tmp_path), "tool_input": {"file_path": "src/blocked.py"}})

    assert any("inside gate scope exclude patterns" in error for error in errors)
