"""Integration tests for Workflow v2 shadow-mode (TC-1H.1).

Verifies:

1. v1 behaviour is unchanged when ``--schema-version`` is omitted (the
   ADR-042 §19 invariant: shadow mode is purely additive).
2. v2 shadow mode logs validator results to
   ``<task_id>.v2.jsonl`` without affecting the v1 state file.
3. v1 advance succeeds even if v2 shadow validators all fail
   (shadow is non-blocking per ADR-042 §19 Phase 1).
4. The schema-v2.yaml ``version:`` field is checked for compatibility.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GATE_PY = REPO_ROOT / ".workflow" / "gate.py"


@pytest.fixture
def gate_mod(monkeypatch):
    """Import ``.workflow/gate.py`` as a module ``gate``.

    Uses ``syspath_prepend`` so cleanup happens automatically. Also
    purges any cached import so each test gets a fresh module object.
    """
    monkeypatch.syspath_prepend(str(REPO_ROOT / ".workflow"))
    sys.modules.pop("gate", None)
    import gate as gate_mod  # type: ignore[import-not-found]

    yield gate_mod
    sys.modules.pop("gate", None)


@pytest.fixture
def fresh_task(tmp_path):
    """Spin up an isolated workflow directory under ``tmp_path``.

    Copies the gate script + both schemas so the tests do not pollute
    the real ``.workflow/active/`` directory.
    """
    workflow_dir = tmp_path / ".workflow"
    workflow_dir.mkdir()
    (workflow_dir / "active").mkdir()

    shutil.copy(REPO_ROOT / ".workflow" / "schema.json", workflow_dir / "schema.json")
    shutil.copy(
        REPO_ROOT / ".workflow" / "schema-v2.yaml",
        workflow_dir / "schema-v2.yaml",
    )
    shutil.copy(REPO_ROOT / ".workflow" / "gate.py", workflow_dir / "gate.py")

    return tmp_path


def _start_workflow(repo: Path, title: str) -> str:
    """Start a workflow and return the new task_id."""
    result = subprocess.run(
        [sys.executable, str(repo / ".workflow" / "gate.py"), "start", title],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    for line in result.stdout.splitlines():
        if "Task ID:" in line:
            return line.split("Task ID:", 1)[1].strip()
    raise AssertionError(f"could not parse task_id from {result.stdout!r}")


# ─── Schema v2 loader ───────────────────────────────────────────────────────


class TestSchemaV2Loader:
    def test_load_schema_v2_succeeds(self, gate_mod):
        schema = gate_mod.load_schema_v2()
        assert schema["version"].startswith("2.")
        assert len(schema["stages"]) == 7

    def test_load_schema_v2_rejects_wrong_version(self, gate_mod, tmp_path, monkeypatch):
        bad = tmp_path / "schema-v2.yaml"
        bad.write_text("version: '1.0.0'\nstages: []\n", encoding="utf-8")
        monkeypatch.setattr(gate_mod, "SCHEMA_V2_PATH", bad)
        with pytest.raises(SystemExit):
            gate_mod.load_schema_v2()

    def test_load_schema_v2_rejects_missing_stages(self, gate_mod, tmp_path, monkeypatch):
        bad = tmp_path / "schema-v2.yaml"
        bad.write_text("version: '2.0.0'\nfoo: bar\n", encoding="utf-8")
        monkeypatch.setattr(gate_mod, "SCHEMA_V2_PATH", bad)
        with pytest.raises(SystemExit):
            gate_mod.load_schema_v2()

    def test_load_schema_v2_missing_file(self, gate_mod, tmp_path, monkeypatch):
        monkeypatch.setattr(gate_mod, "SCHEMA_V2_PATH", tmp_path / "does-not-exist.yaml")
        with pytest.raises(SystemExit):
            gate_mod.load_schema_v2()


# ─── Shadow event logging ──────────────────────────────────────────────────


class TestShadowEventLogging:
    def test_append_shadow_event(self, gate_mod, tmp_path, monkeypatch):
        monkeypatch.setattr(gate_mod, "ACTIVE_DIR", tmp_path)
        gate_mod.append_shadow_event("test-task", {"event": "v2_smoke", "stage": "create_issue"})
        log = tmp_path / "test-task.v2.jsonl"
        assert log.exists()
        lines = log.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        obj = json.loads(lines[0])
        assert obj["event"] == "v2_smoke"

    def test_shadow_log_is_append_only(self, gate_mod, tmp_path, monkeypatch):
        monkeypatch.setattr(gate_mod, "ACTIVE_DIR", tmp_path)
        for i in range(3):
            gate_mod.append_shadow_event("task", {"event": "n", "i": i})
        lines = (tmp_path / "task.v2.jsonl").read_text(encoding="utf-8").strip().splitlines()
        assert [json.loads(line)["i"] for line in lines] == [0, 1, 2]

    def test_shadow_log_path(self, gate_mod, tmp_path, monkeypatch):
        monkeypatch.setattr(gate_mod, "ACTIVE_DIR", tmp_path)
        path = gate_mod.shadow_log_path("my-task")
        assert path == tmp_path / "my-task.v2.jsonl"


# ─── Shadow runner ─────────────────────────────────────────────────────────


class TestRunV2ValidatorsShadow:
    def test_no_v2_mapping_returns_empty(self, gate_mod, tmp_path, monkeypatch):
        monkeypatch.setattr(gate_mod, "ACTIVE_DIR", tmp_path)
        results = gate_mod.run_v2_validators_shadow(task_id="t", v1_stage_id="unknown_v1_stage", artifacts={})
        assert results == []

    def test_v1_create_issue_runs_v2_create_issue(self, gate_mod, tmp_path, monkeypatch):
        monkeypatch.setattr(gate_mod, "ACTIVE_DIR", tmp_path)
        results = gate_mod.run_v2_validators_shadow(
            task_id="t",
            v1_stage_id="create_issue",
            artifacts={
                "issue_number": 1145,
                "issue_url": "https://github.com/zjzcpj/SciEasy/issues/1145",
            },
        )
        assert len(results) == 1
        assert results[0]["v2_stage"] == "create_issue"
        assert results[0]["validator_id"] == "create_issue.shape"
        assert results[0]["status"] == "pass"

    def test_v1_create_branch_runs_v2_branch_name(self, gate_mod, tmp_path, monkeypatch):
        monkeypatch.setattr(gate_mod, "ACTIVE_DIR", tmp_path)
        results = gate_mod.run_v2_validators_shadow(
            task_id="t",
            v1_stage_id="create_branch",
            artifacts={"branch_name": "feat/issue-1145/adr-042/workflow-v2-shadow"},
            branch="feat/issue-1145/adr-042/workflow-v2-shadow",
        )
        assert results[0]["status"] == "pass"

    def test_v1_write_change_plan_runs_v2_change_plan(self, gate_mod, tmp_path, monkeypatch):
        monkeypatch.setattr(gate_mod, "ACTIVE_DIR", tmp_path)
        results = gate_mod.run_v2_validators_shadow(
            task_id="t",
            v1_stage_id="write_change_plan",
            artifacts={
                "change_plan_comment_url": "https://github.com/x/y/issues/1#issuecomment-1",
                "files_to_modify": ["a.py"],
            },
        )
        assert len(results) == 1
        assert results[0]["v2_stage"] == "change_plan"
        assert results[0]["status"] == "pass"

    def test_v1_update_docs_runs_v2_complete_artifacts_skip(self, gate_mod, tmp_path, monkeypatch):
        monkeypatch.setattr(gate_mod, "ACTIVE_DIR", tmp_path)
        results = gate_mod.run_v2_validators_shadow(
            task_id="t",
            v1_stage_id="update_docs",
            artifacts={"docs_updated": ["docs/foo.md"]},
        )
        assert len(results) == 1
        assert results[0]["status"] == "skip"

    def test_v1_submit_pr_runs_v2_submit_reconcile(self, gate_mod, tmp_path, monkeypatch):
        monkeypatch.setattr(gate_mod, "ACTIVE_DIR", tmp_path)
        results = gate_mod.run_v2_validators_shadow(
            task_id="t",
            v1_stage_id="submit_pr",
            artifacts={
                "pr_number": 999,
                "pr_url": "https://github.com/zjzcpj/SciEasy/pull/999",
            },
        )
        assert results[0]["status"] == "pass"

    def test_shadow_writes_jsonl_log(self, gate_mod, tmp_path, monkeypatch):
        monkeypatch.setattr(gate_mod, "ACTIVE_DIR", tmp_path)
        gate_mod.run_v2_validators_shadow(
            task_id="logme",
            v1_stage_id="create_issue",
            artifacts={
                "issue_number": 1,
                "issue_url": "https://github.com/x/y/issues/1",
            },
        )
        log = tmp_path / "logme.v2.jsonl"
        assert log.exists()
        event = json.loads(log.read_text(encoding="utf-8").strip())
        assert event["event"] == "v2_shadow_run"
        assert event["v1_stage"] == "create_issue"
        assert event["v2_stages"] == ["create_issue"]
        assert len(event["results"]) == 1


# ─── v1 behaviour unchanged (the defining ADR-042 §19 Phase 1 invariant) ───


class TestV1BehaviourUnchanged:
    def test_v1_advance_writes_no_shadow_log(self, fresh_task):
        repo = fresh_task
        task_id = _start_workflow(repo, "v1 default test")
        result = subprocess.run(
            [
                sys.executable,
                str(repo / ".workflow" / "gate.py"),
                "advance",
                task_id,
                "create_issue",
                "--data",
                json.dumps(
                    {
                        "issue_number": 42,
                        "issue_url": "https://github.com/x/y/issues/42",
                    }
                ),
            ],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        shadow_log = repo / ".workflow" / "active" / f"{task_id}.v2.jsonl"
        assert not shadow_log.exists(), f"v1 default mode must not create shadow log; found {shadow_log}"

    def test_v2_flag_creates_shadow_log(self, fresh_task):
        repo = fresh_task
        task_id = _start_workflow(repo, "v2 shadow test")
        result = subprocess.run(
            [
                sys.executable,
                str(repo / ".workflow" / "gate.py"),
                "--schema-version",
                "v2",
                "advance",
                task_id,
                "create_issue",
                "--data",
                json.dumps(
                    {
                        "issue_number": 42,
                        "issue_url": "https://github.com/x/y/issues/42",
                    }
                ),
            ],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        shadow_log = repo / ".workflow" / "active" / f"{task_id}.v2.jsonl"
        assert shadow_log.exists(), "v2 mode must create shadow log"
        events = [json.loads(line) for line in shadow_log.read_text().strip().splitlines()]
        assert any(e["event"] == "v2_shadow_run" for e in events)

    def test_v2_validator_failures_do_not_block_v1(self, fresh_task):
        """If v2 validators all FAIL, v1 advance still succeeds."""
        repo = fresh_task
        task_id = _start_workflow(repo, "v2 fail test")
        # Pass a deliberately bad URL — v2 create_issue.shape will fail,
        # but v1's schema.json validation only requires issue_number +
        # issue_url present (which they are), so v1 advance succeeds.
        result = subprocess.run(
            [
                sys.executable,
                str(repo / ".workflow" / "gate.py"),
                "--schema-version",
                "v2",
                "advance",
                task_id,
                "create_issue",
                "--data",
                json.dumps(
                    {
                        "issue_number": 1,
                        "issue_url": "not-a-github-url",
                    }
                ),
            ],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, f"v1 advance must succeed despite v2 failure. stderr: {result.stderr}"
        assert "[v2-shadow]" in result.stdout
        assert "FAILED" in result.stdout
