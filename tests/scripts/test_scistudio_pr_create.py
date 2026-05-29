# mypy: disable-error-code=no-untyped-def
"""Tests for the rewritten ``scripts/scistudio_pr_create.py`` (ADR-042 Addendum 6).

The wrapper is now a thin caller of the single shared evaluator: it extracts the
PR body/base from the ``gh pr create`` argv, verifies a current-branch gate
ledger exists via the SHARED ``io.discover_ledger`` (no private ``find_gate_record``),
then runs ``gate_record check --mode pre-pr --pr-body-file <body>`` once. There is
no caller-side finding filter (``filter_findings`` is deleted — pre-PR-impossible
findings are classified internally by the evaluator's pre-PR mode) and no separate
receipt-validate step. ``--dry-run`` and ``SCISTUDIO_SKIP_PREFLIGHT`` are preserved.
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


class TestResolveBaseRef:
    def test_none_defaults_to_origin_main(self, wrapper) -> None:
        assert wrapper.resolve_base_ref(None) == "origin/main"

    def test_plain_branch_prefixed_with_origin(self, wrapper) -> None:
        assert wrapper.resolve_base_ref("main") == "origin/main"

    def test_umbrella_branch_prefixed(self, wrapper) -> None:
        assert wrapper.resolve_base_ref("umbrella/2026-05-21-bug-sweep") == "origin/umbrella/2026-05-21-bug-sweep"

    def test_already_origin_qualified_kept_verbatim(self, wrapper) -> None:
        assert wrapper.resolve_base_ref("origin/main") == "origin/main"
        assert wrapper.resolve_base_ref("origin/release/v1") == "origin/release/v1"

    def test_refs_qualified_kept_verbatim(self, wrapper) -> None:
        assert wrapper.resolve_base_ref("refs/heads/main") == "refs/heads/main"

    def test_content_agnostic_no_umbrella_semantics(self, wrapper) -> None:
        assert wrapper.resolve_base_ref("feature/foo") == "origin/feature/foo"
        assert wrapper.resolve_base_ref("hotfix/bar") == "origin/hotfix/bar"


# ---------------------------------------------------------------------------
# Shared discovery: the wrapper does NOT reimplement ledger discovery.
# ---------------------------------------------------------------------------


def test_wrapper_has_no_private_discovery_or_filter(wrapper) -> None:
    # The legacy private helpers are deleted; the wrapper uses the shared
    # io.discover_ledger and the evaluator's pre-pr classification.
    assert not hasattr(wrapper, "find_gate_record")
    assert not hasattr(wrapper, "filter_findings")
    assert not hasattr(wrapper, "run_gate_record_ci")
    assert not hasattr(wrapper, "run_gate_receipt_validate")
    assert hasattr(wrapper, "run_pre_pr_check")


# ---------------------------------------------------------------------------
# main — smoke via --help / --dry-run + SCISTUDIO_SKIP_PREFLIGHT.
# ---------------------------------------------------------------------------


class TestMainSmoke:
    def test_help_prints_and_exits_zero(self, wrapper, capsys) -> None:
        rc = wrapper.main(["--help"])
        assert rc == 0
        out = capsys.readouterr().out.lower()
        assert "scistudio_pr_create" in out or "pre-flight" in out or "preflight" in out

    def test_dry_run_with_skip_preflight(self, wrapper, monkeypatch, capsys) -> None:
        monkeypatch.setenv("SCISTUDIO_SKIP_PREFLIGHT", "1")
        rc = wrapper.main(["--dry-run", "--title", "X", "--body", "Y"])
        assert rc == 0
        err = capsys.readouterr().err
        assert "SKIPPED" in err
        assert "DRY RUN" in err


# ---------------------------------------------------------------------------
# main wiring: discovery + body required + base threaded into run_pre_pr_check.
# ---------------------------------------------------------------------------


def _write_ledger(records_dir: Path, name: str, branch: str) -> Path:
    records_dir.mkdir(parents=True, exist_ok=True)
    p = records_dir / f"{name}.json"
    p.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "record_id": name,
                "runtime": "claude-code",
                "task_kind": "feature",
                "persona": "implementer",
                "branch": branch,
                "owner_directive": "d",
            }
        ),
        encoding="utf-8",
    )
    return p


class TestMainWiring:
    def _stub_git(self, wrapper, monkeypatch, repo: Path, branch: str) -> None:
        def _fake_check_output(cmd, *args, **kwargs):
            if cmd[:2] == ["git", "rev-parse"] and "--show-toplevel" in cmd:
                return str(repo) + "\n"
            if cmd[:2] == ["git", "rev-parse"] and "--abbrev-ref" in cmd:
                return branch + "\n"
            raise AssertionError(f"unexpected check_output call: {cmd}")

        monkeypatch.setattr(wrapper.subprocess, "check_output", _fake_check_output)

    def test_no_ledger_is_environment_error(self, wrapper, monkeypatch, tmp_path: Path) -> None:
        repo = tmp_path
        self._stub_git(wrapper, monkeypatch, repo, "feat/x")
        rc = wrapper.main(["--title", "X", "--body", "Closes #1"])
        # No current-branch ledger -> environment error (exit 2).
        assert rc == 2

    def test_missing_body_is_error(self, wrapper, monkeypatch, tmp_path: Path) -> None:
        repo = tmp_path
        _write_ledger(repo / ".workflow" / "records", "issue-x", "feat/x")
        self._stub_git(wrapper, monkeypatch, repo, "feat/x")
        rc = wrapper.main(["--title", "X"])
        assert rc == 1

    def test_base_threaded_into_pre_pr_check_and_gh_runs_on_clean(self, wrapper, monkeypatch, tmp_path: Path) -> None:
        repo = tmp_path
        _write_ledger(repo / ".workflow" / "records", "issue-x", "feat/x")
        self._stub_git(wrapper, monkeypatch, repo, "feat/x")

        captured: dict[str, Any] = {}

        def _fake_run_pre_pr_check(repo_root, body_file, *, base="origin/main"):
            captured["base"] = base
            return 0  # clean pre-flight

        def _fake_call(cmd):
            captured["gh"] = cmd
            return 0

        monkeypatch.setattr(wrapper, "run_pre_pr_check", _fake_run_pre_pr_check)
        monkeypatch.setattr(wrapper.subprocess, "call", _fake_call)

        rc = wrapper.main(["--base", "umbrella/2026-05-21-bug-sweep", "--title", "X", "--body", "Closes #1382"])
        assert rc == 0
        assert captured["base"] == "origin/umbrella/2026-05-21-bug-sweep"
        assert captured["gh"][:3] == ["gh", "pr", "create"]

    def test_default_base_origin_main_when_flag_absent(self, wrapper, monkeypatch, tmp_path: Path) -> None:
        repo = tmp_path
        _write_ledger(repo / ".workflow" / "records", "issue-x", "feat/x")
        self._stub_git(wrapper, monkeypatch, repo, "feat/x")

        captured: dict[str, Any] = {}

        def _fake_run_pre_pr_check(repo_root, body_file, *, base="origin/main"):
            captured["base"] = base
            return 0

        monkeypatch.setattr(wrapper, "run_pre_pr_check", _fake_run_pre_pr_check)
        monkeypatch.setattr(wrapper.subprocess, "call", lambda cmd: 0)

        rc = wrapper.main(["--title", "X", "--body", "Closes #1382"])
        assert rc == 0
        assert captured["base"] == "origin/main"

    def test_failed_pre_flight_blocks_gh(self, wrapper, monkeypatch, tmp_path: Path) -> None:
        repo = tmp_path
        _write_ledger(repo / ".workflow" / "records", "issue-x", "feat/x")
        self._stub_git(wrapper, monkeypatch, repo, "feat/x")
        monkeypatch.setattr(wrapper, "run_pre_pr_check", lambda *a, **k: 1)  # failed pre-flight
        called: dict[str, Any] = {}
        monkeypatch.setattr(wrapper.subprocess, "call", lambda cmd: called.setdefault("gh", cmd) or 0)
        rc = wrapper.main(["--title", "X", "--body", "Closes #1382"])
        assert rc == 1
        assert "gh" not in called  # gh pr create must not run on failed pre-flight.
