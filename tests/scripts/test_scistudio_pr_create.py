"""Tests for ``scripts/scistudio_pr_create.py``.

Covers the four pure-function pieces (``extract_body``,
``find_gate_record``, ``filter_findings``) plus a smoke for ``main()``
using ``--dry-run`` so the test never invokes ``gh pr create`` or hits
the real network.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "scistudio_pr_create.py"


@pytest.fixture(scope="module")
def wrapper():
    """Load ``scripts/scistudio_pr_create.py`` as a module for testing."""
    spec = importlib.util.spec_from_file_location("scistudio_pr_create", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["scistudio_pr_create"] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# extract_body
# ---------------------------------------------------------------------------


class TestExtractBody:
    def test_body_space_separated(self, wrapper) -> None:
        assert wrapper.extract_body(["--title", "X", "--body", "hello"]) == "hello"

    def test_body_equals_separated(self, wrapper) -> None:
        assert wrapper.extract_body(["--title", "X", "--body=hello"]) == "hello"

    def test_body_file_space_separated(self, wrapper, tmp_path: Path) -> None:
        f = tmp_path / "body.md"
        f.write_text("from file\n", encoding="utf-8")
        assert wrapper.extract_body(["--body-file", str(f)]) == "from file\n"

    def test_body_file_equals_separated(self, wrapper, tmp_path: Path) -> None:
        f = tmp_path / "body.md"
        f.write_text("via equals\n", encoding="utf-8")
        assert wrapper.extract_body([f"--body-file={f}"]) == "via equals\n"

    def test_missing_returns_empty(self, wrapper) -> None:
        assert wrapper.extract_body(["--title", "X", "--draft"]) == ""

    def test_body_with_special_chars(self, wrapper) -> None:
        body = "Closes #1334\nCloses #560\n\n```python\nprint('hi')\n```"
        assert wrapper.extract_body(["--body", body]) == body


# ---------------------------------------------------------------------------
# find_gate_record
# ---------------------------------------------------------------------------


def _write_record(records_dir: Path, name: str, branch: str, *, task_kind: str = "feature") -> Path:
    records_dir.mkdir(parents=True, exist_ok=True)
    p = records_dir / f"{name}.json"
    p.write_text(
        json.dumps({"branch": branch, "task_kind": task_kind, "issues": []}),
        encoding="utf-8",
    )
    return p


class TestFindGateRecord:
    def test_unique_match(self, wrapper, tmp_path: Path) -> None:
        records_dir = tmp_path / ".workflow" / "records"
        p = _write_record(records_dir, "1360-x", "feat/issue-1360/x")
        assert wrapper.find_gate_record(tmp_path, "feat/issue-1360/x") == p

    def test_no_match_raises(self, wrapper, tmp_path: Path) -> None:
        records_dir = tmp_path / ".workflow" / "records"
        _write_record(records_dir, "1360-x", "feat/issue-1360/x")
        with pytest.raises(SystemExit, match="no gate record"):
            wrapper.find_gate_record(tmp_path, "feat/issue-9999/other")

    def test_no_records_dir_raises(self, wrapper, tmp_path: Path) -> None:
        with pytest.raises(SystemExit, match=r"no \.workflow/records/ directory"):
            wrapper.find_gate_record(tmp_path, "any-branch")

    def test_multi_match_prefers_manager(self, wrapper, tmp_path: Path) -> None:
        # Umbrella PR pattern from #1340: sub-records ride along with the
        # manager record; prefer the manager one.
        records_dir = tmp_path / ".workflow" / "records"
        _write_record(records_dir, "sub1", "umbrella/x", task_kind="feature")
        _write_record(records_dir, "sub2", "umbrella/x", task_kind="bugfix")
        manager = _write_record(records_dir, "manager", "umbrella/x", task_kind="manager")
        assert wrapper.find_gate_record(tmp_path, "umbrella/x") == manager

    def test_multi_match_no_manager_raises(self, wrapper, tmp_path: Path) -> None:
        records_dir = tmp_path / ".workflow" / "records"
        _write_record(records_dir, "a", "branch", task_kind="feature")
        _write_record(records_dir, "b", "branch", task_kind="bugfix")
        with pytest.raises(SystemExit, match="multiple gate records"):
            wrapper.find_gate_record(tmp_path, "branch")

    def test_malformed_record_is_skipped(self, wrapper, tmp_path: Path) -> None:
        records_dir = tmp_path / ".workflow" / "records"
        records_dir.mkdir(parents=True)
        (records_dir / "bad.json").write_text("not json{", encoding="utf-8")
        good = _write_record(records_dir, "good", "feat/x")
        assert wrapper.find_gate_record(tmp_path, "feat/x") == good


# ---------------------------------------------------------------------------
# filter_findings
# ---------------------------------------------------------------------------


def _finding(rule_id: str, severity: str = "error", message: str = "") -> dict[str, Any]:
    return {"rule_id": rule_id, "severity": severity, "message": message}


class TestFilterFindings:
    def test_all_filtered(self, wrapper) -> None:
        report = {
            "findings": [
                _finding("core_change_guard.missing-admin-approval"),
                _finding("pr_merge_guard.missing-admin-merge-approval"),
                _finding("human_bypass_guard.missing-bypass-label"),
            ]
        }
        remaining, filtered = wrapper.filter_findings(report)
        assert remaining == []
        assert filtered == 3

    def test_none_filtered(self, wrapper) -> None:
        report = {
            "findings": [
                _finding("issue_link.invalid-record"),
                _finding("docs_landing.missing-changelog"),
                _finding("sentrux.free_tier.missing-rules-checked"),
            ]
        }
        remaining, filtered = wrapper.filter_findings(report)
        assert len(remaining) == 3
        assert filtered == 0

    def test_mixed(self, wrapper) -> None:
        report = {
            "findings": [
                _finding("core_change_guard.missing-admin-approval"),  # filtered
                _finding("issue_link.missing"),  # kept
                _finding("human_bypass_guard.ai-evidence-needs-admin-override"),  # filtered
                _finding("docs_landing.missing-checklist"),  # kept
            ]
        }
        remaining, filtered = wrapper.filter_findings(report)
        assert {f["rule_id"] for f in remaining} == {
            "issue_link.missing",
            "docs_landing.missing-checklist",
        }
        assert filtered == 2

    def test_empty_findings(self, wrapper) -> None:
        assert wrapper.filter_findings({"findings": []}) == ([], 0)

    def test_missing_findings_key(self, wrapper) -> None:
        # gate_record ci returns no 'findings' on full pass — must not crash.
        assert wrapper.filter_findings({"status": "pass"}) == ([], 0)

    def test_finding_without_rule_id_kept(self, wrapper) -> None:
        # Defensive: a finding with no rule_id can't be filtered safely; keep it.
        report = {"findings": [{"severity": "error", "message": "weird"}]}
        remaining, filtered = wrapper.filter_findings(report)
        assert len(remaining) == 1
        assert filtered == 0

    def test_stage_not_done_commit_and_submit_pr_filtered(self, wrapper) -> None:
        # Caught during PR #1360 dogfood: ``commit_and_submit_pr`` stage is
        # only set by ``gate_record finalize`` which itself requires the PR
        # URL — structurally impossible to pass pre-PR.
        report = {
            "findings": [
                _finding(
                    "gate-record.stage.not-done",
                    message="gate stage must be done before PR readiness: commit_and_submit_pr",
                )
            ]
        }
        remaining, filtered = wrapper.filter_findings(report)
        assert remaining == []
        assert filtered == 1

    def test_stage_not_done_other_stages_kept(self, wrapper) -> None:
        # A ``stage.not-done`` for any other stage (e.g. ``implement``)
        # IS the author's responsibility to fix pre-push; must NOT be filtered.
        report = {
            "findings": [
                _finding(
                    "gate-record.stage.not-done",
                    message="gate stage must be done before PR readiness: implement",
                )
            ]
        }
        remaining, filtered = wrapper.filter_findings(report)
        assert len(remaining) == 1
        assert filtered == 0


# ---------------------------------------------------------------------------
# main — smoke via --dry-run + SCISTUDIO_SKIP_PREFLIGHT
# ---------------------------------------------------------------------------


class TestMainSmoke:
    def test_help_prints_and_exits_zero(self, wrapper, capsys) -> None:
        rc = wrapper.main(["--help"])
        assert rc == 0
        captured = capsys.readouterr()
        assert (
            "scistudio_pr_create" in captured.out.lower()
            or "preflight" in captured.out.lower()
            or "pre-flight" in captured.out.lower()
        )

    def test_dry_run_with_skip_preflight(self, wrapper, monkeypatch, capsys) -> None:
        monkeypatch.setenv("SCISTUDIO_SKIP_PREFLIGHT", "1")
        rc = wrapper.main(["--dry-run", "--title", "X", "--body", "Y"])
        assert rc == 0
        err = capsys.readouterr().err
        assert "SKIPPED" in err
        assert "DRY RUN" in err


# ---------------------------------------------------------------------------
# extract_base + resolve_base_ref (#1382)
# ---------------------------------------------------------------------------


class TestExtractBase:
    def test_missing_returns_none(self, wrapper) -> None:
        assert wrapper.extract_base(["--title", "X", "--body", "Y"]) is None

    def test_space_separated(self, wrapper) -> None:
        assert wrapper.extract_base(["--base", "main", "--title", "X"]) == "main"

    def test_equals_separated(self, wrapper) -> None:
        assert wrapper.extract_base(["--title", "X", "--base=main"]) == "main"

    def test_umbrella_branch(self, wrapper) -> None:
        assert wrapper.extract_base(["--base", "umbrella/2026-05-21-bug-sweep"]) == "umbrella/2026-05-21-bug-sweep"

    def test_branch_with_dots_and_slashes(self, wrapper) -> None:
        assert wrapper.extract_base(["--base=release/v1.0"]) == "release/v1.0"

    def test_token_substring_does_not_match(self, wrapper) -> None:
        # --base-file or --basemain must not falsely match.
        assert wrapper.extract_base(["--basefoo", "main"]) is None

    def test_returns_first_when_passed_twice(self, wrapper) -> None:
        # gh pr create's own semantics: first occurrence wins. Mirror that.
        assert wrapper.extract_base(["--base", "main", "--base", "release"]) == "main"


class TestResolveBaseRef:
    def test_none_defaults_to_origin_main(self, wrapper) -> None:
        assert wrapper.resolve_base_ref(None) == "origin/main"

    def test_plain_branch_prefixed_with_origin(self, wrapper) -> None:
        assert wrapper.resolve_base_ref("main") == "origin/main"

    def test_umbrella_branch_prefixed(self, wrapper) -> None:
        assert wrapper.resolve_base_ref("umbrella/2026-05-21-bug-sweep") == "origin/umbrella/2026-05-21-bug-sweep"

    def test_already_origin_qualified_kept_verbatim(self, wrapper) -> None:
        # Caller-provided ``origin/main`` must not become ``origin/origin/main``.
        assert wrapper.resolve_base_ref("origin/main") == "origin/main"
        assert wrapper.resolve_base_ref("origin/release/v1") == "origin/release/v1"

    def test_refs_qualified_kept_verbatim(self, wrapper) -> None:
        # Power users may pass a fully-qualified ref; respect that.
        assert wrapper.resolve_base_ref("refs/heads/main") == "refs/heads/main"
        assert wrapper.resolve_base_ref("refs/remotes/upstream/main") == "refs/remotes/upstream/main"

    def test_content_agnostic_no_umbrella_semantics(self, wrapper) -> None:
        # The function must work identically regardless of whether the branch
        # name looks umbrella-shaped. No special branches.
        assert wrapper.resolve_base_ref("feature/foo") == "origin/feature/foo"
        assert wrapper.resolve_base_ref("hotfix/bar") == "origin/hotfix/bar"
        assert wrapper.resolve_base_ref("track/baz") == "origin/track/baz"


class TestMainBaseWiring:
    """Ensure ``main()`` actually threads the resolved base into ``gate_record ci``."""

    def test_base_threaded_into_run_gate_record_ci(self, wrapper, monkeypatch, tmp_path: Path) -> None:
        # Set up a minimal repo-like layout so find_gate_record + body extraction
        # succeed, then intercept run_gate_record_ci to capture the resolved base.
        records_dir = tmp_path / ".workflow" / "records"
        _write_record(records_dir, "issue-x", "fix/issue-x/wrapper-detect")

        # git rev-parse stubs
        def _fake_check_output(cmd, *args, **kwargs):
            if cmd[:2] == ["git", "rev-parse"] and "--show-toplevel" in cmd:
                return str(tmp_path) + "\n"
            if cmd[:2] == ["git", "rev-parse"] and "--abbrev-ref" in cmd:
                return "fix/issue-x/wrapper-detect\n"
            raise AssertionError(f"unexpected check_output call: {cmd}")

        monkeypatch.setattr(wrapper.subprocess, "check_output", _fake_check_output)

        captured: dict[str, Any] = {}

        def _fake_run_gate_record_ci(repo_root, record, body, *, base="origin/main", head="HEAD"):
            captured["base"] = base
            captured["head"] = head
            return {"findings": []}

        monkeypatch.setattr(wrapper, "run_gate_record_ci", _fake_run_gate_record_ci)

        # Avoid actually invoking gh pr create.
        def _fake_subprocess_call(cmd):
            captured["gh_argv"] = cmd
            return 0

        monkeypatch.setattr(wrapper.subprocess, "call", _fake_subprocess_call)

        # --base umbrella/foo → resolve to origin/umbrella/foo
        rc = wrapper.main(["--base", "umbrella/2026-05-21-bug-sweep", "--title", "X", "--body", "Closes #1382"])
        assert rc == 0
        assert captured["base"] == "origin/umbrella/2026-05-21-bug-sweep"

    def test_default_base_origin_main_when_flag_absent(self, wrapper, monkeypatch, tmp_path: Path) -> None:
        records_dir = tmp_path / ".workflow" / "records"
        _write_record(records_dir, "issue-x", "fix/issue-x/wrapper-detect")

        def _fake_check_output(cmd, *args, **kwargs):
            if cmd[:2] == ["git", "rev-parse"] and "--show-toplevel" in cmd:
                return str(tmp_path) + "\n"
            if cmd[:2] == ["git", "rev-parse"] and "--abbrev-ref" in cmd:
                return "fix/issue-x/wrapper-detect\n"
            raise AssertionError(f"unexpected check_output call: {cmd}")

        monkeypatch.setattr(wrapper.subprocess, "check_output", _fake_check_output)

        captured: dict[str, Any] = {}

        def _fake_run_gate_record_ci(repo_root, record, body, *, base="origin/main", head="HEAD"):
            captured["base"] = base
            return {"findings": []}

        monkeypatch.setattr(wrapper, "run_gate_record_ci", _fake_run_gate_record_ci)
        monkeypatch.setattr(wrapper.subprocess, "call", lambda cmd: 0)

        rc = wrapper.main(["--title", "X", "--body", "Closes #1382"])
        assert rc == 0
        assert captured["base"] == "origin/main"
