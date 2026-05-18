"""Unit tests for :mod:`scieasy.qa.test_quality.test_first_check` (TC-1F.2).

Subprocess boundaries (``gh api`` and ``git show``) are exercised via
monkey-patching the single :func:`_run_capture` seam — the verifier
itself remains pure, deterministic, and platform-portable.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import pytest

from scieasy.qa.schemas.report import Severity
from scieasy.qa.test_quality import test_first_check as tfc


def _stub_run_capture(
    pr_commits: list[dict[str, str]],
    files_per_sha: dict[str, list[str]],
):
    """Build a fake ``_run_capture`` that returns canned commits + diffs."""

    def fake(args: Sequence[str]) -> tuple[int, str, str]:
        if len(args) >= 2 and args[0] == "gh" and args[1] == "api":
            # Emit one JSON object per line (matches ``-q .[] | {...}``).
            out = "\n".join(json.dumps(c) for c in pr_commits)
            return 0, out, ""
        if len(args) >= 3 and args[0] == "git" and args[1] == "show":
            sha = args[-1]
            files = files_per_sha.get(sha, [])
            return 0, "\n".join(files) + ("\n" if files else ""), ""
        if len(args) >= 1 and args[0] == "git" and args[1] == "rev-parse":
            return 0, "/tmp/repo\n", ""
        return 2, "", "unhandled stub"

    return fake


def test_verify_ordering_silent_when_test_precedes_impl(monkeypatch: pytest.MonkeyPatch) -> None:
    """Compliant order: test commit first, impl commit second → no finding."""
    commits = [
        {"sha": "aaa1111", "message": "test: add failing test_normalize"},
        {"sha": "bbb2222", "message": "feat: implement normalize"},
    ]
    files = {
        "aaa1111": ["tests/test_normalize.py"],
        "bbb2222": ["src/scieasy/util/normalize.py"],
    }
    monkeypatch.setattr(tfc, "_run_capture", _stub_run_capture(commits, files))
    assert tfc.verify_ordering(42, "owner/repo") == []


def test_verify_ordering_fires_when_impl_precedes_test(monkeypatch: pytest.MonkeyPatch) -> None:
    """Order violation: impl committed before its paired test."""
    commits = [
        {"sha": "bbb2222", "message": "feat: implement normalize"},
        {"sha": "aaa1111", "message": "test: add test_normalize"},
    ]
    files = {
        "bbb2222": ["src/scieasy/util/normalize.py"],
        "aaa1111": ["tests/test_normalize.py"],
    }
    monkeypatch.setattr(tfc, "_run_capture", _stub_run_capture(commits, files))
    findings = tfc.verify_ordering(42, "owner/repo")
    assert len(findings) == 1
    assert findings[0].rule_id == "TQTF-impl-before-test"
    assert findings[0].severity is Severity.WARNING  # report-only default
    assert findings[0].symbol == "normalize"


def test_verify_ordering_enforce_upgrades_to_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """``enforce=True`` (tdd-required label gate) raises severity to error."""
    commits = [
        {"sha": "bbb2222", "message": "feat: implement normalize"},
        {"sha": "aaa1111", "message": "test: add test_normalize"},
    ]
    files = {
        "bbb2222": ["src/scieasy/util/normalize.py"],
        "aaa1111": ["tests/test_normalize.py"],
    }
    monkeypatch.setattr(tfc, "_run_capture", _stub_run_capture(commits, files))
    findings = tfc.verify_ordering(42, "owner/repo", enforce=True)
    assert findings[0].severity is Severity.ERROR


def test_verify_ordering_backfill_trailer_exempts_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``Backfill-Test:`` trailer on the test commit suppresses the finding."""
    commits = [
        {"sha": "bbb2222", "message": "feat: implement normalize"},
        {
            "sha": "aaa1111",
            "message": "test: backfill test_normalize\n\nBackfill-Test: yes",
        },
    ]
    files = {
        "bbb2222": ["src/scieasy/util/normalize.py"],
        "aaa1111": ["tests/test_normalize.py"],
    }
    monkeypatch.setattr(tfc, "_run_capture", _stub_run_capture(commits, files))
    assert tfc.verify_ordering(42, "owner/repo") == []


def test_verify_ordering_returns_empty_when_no_commits(monkeypatch: pytest.MonkeyPatch) -> None:
    """No PR commits (gh returned nothing) → no findings."""
    monkeypatch.setattr(tfc, "_run_capture", _stub_run_capture(pr_commits=[], files_per_sha={}))
    assert tfc.verify_ordering(42, "owner/repo") == []


def test_verify_ordering_returns_empty_when_no_pair_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests added without an impl pair (and vice-versa) are silently skipped."""
    commits = [
        {"sha": "aaa1111", "message": "test: add unrelated test"},
        {"sha": "bbb2222", "message": "feat: add unrelated impl"},
    ]
    files = {
        "aaa1111": ["tests/test_aaa.py"],
        "bbb2222": ["src/scieasy/util/bbb.py"],
    }
    monkeypatch.setattr(tfc, "_run_capture", _stub_run_capture(commits, files))
    assert tfc.verify_ordering(42, "owner/repo") == []


def test_verify_ordering_handles_gh_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Failed ``gh`` call → empty findings, no crash."""

    def fail(_args):
        return 2, "", "gh not found"

    monkeypatch.setattr(tfc, "_run_capture", fail)
    assert tfc.verify_ordering(42, "owner/repo") == []


def test_verify_ordering_skips_non_string_sha(monkeypatch: pytest.MonkeyPatch) -> None:
    """Malformed commit objects don't crash the verifier."""
    commits = [
        {"sha": 123, "message": "broken commit object"},
        {"sha": "aaa1111", "message": "test"},
    ]
    files = {"aaa1111": ["tests/test_normalize.py"]}
    monkeypatch.setattr(tfc, "_run_capture", _stub_run_capture(commits, files))
    # No pair → no findings, but importantly no exception.
    assert tfc.verify_ordering(42, "owner/repo") == []


def test_extract_test_stem_matches_nested_path() -> None:
    """``tests/qa/test_normalize.py`` → ``normalize``."""
    assert tfc._extract_test_stem("tests/qa/test_normalize.py") == "normalize"


def test_extract_test_stem_returns_none_for_non_test() -> None:
    """Non-test paths return None."""
    assert tfc._extract_test_stem("src/scieasy/util/normalize.py") is None
    assert tfc._extract_test_stem("README.md") is None


def test_extract_src_stem_matches_nested_path() -> None:
    """``src/scieasy/util/normalize.py`` → ``normalize``."""
    assert tfc._extract_src_stem("src/scieasy/util/normalize.py") == "normalize"


def test_has_backfill_trailer_recognises_canonical_form() -> None:
    """The trailer regex is case-insensitive and multi-line aware."""
    assert tfc._has_backfill_trailer("feat: x\n\nBackfill-Test: yes\n")
    assert tfc._has_backfill_trailer("feat: x\n\nbackfill-test: legacy code\n")
    assert not tfc._has_backfill_trailer("feat: x\n")
    assert not tfc._has_backfill_trailer(123)  # type: ignore[arg-type]


def test_run_capture_returns_env_error_when_binary_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_run_capture`` returns (2, "", msg) when the binary isn't on PATH."""
    monkeypatch.setattr(tfc.shutil, "which", lambda _: None)
    rc, out, err = tfc._run_capture(["nonexistent-binary", "arg"])
    assert rc == 2
    assert out == ""
    assert "nonexistent-binary" in err


def test_run_capture_returns_env_error_on_empty_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty argv is rejected without a subprocess call."""
    rc, _out, err = tfc._run_capture([])
    assert rc == 2
    assert "no command" in err


def test_fetch_pr_commits_skips_malformed_json_lines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A malformed ``gh`` response line is dropped, not propagated as a crash."""

    def fake(args):
        # First line is valid JSON, second is garbage, third is valid.
        return 0, '{"sha": "aaa1111", "message": "good"}\nnot-json\n{"sha":"bbb2222","message":"also good"}\n', ""

    monkeypatch.setattr(tfc, "_run_capture", fake)
    commits = tfc._fetch_pr_commits(1, "owner/repo")
    assert [c["sha"] for c in commits] == ["aaa1111", "bbb2222"]


def test_fetch_pr_commits_returns_empty_on_gh_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``gh`` non-zero exit → empty list, no crash."""
    monkeypatch.setattr(tfc, "_run_capture", lambda _a: (3, "", "auth required"))
    assert tfc._fetch_pr_commits(1, "owner/repo") == []


def test_files_added_in_commit_returns_empty_on_git_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``git show`` failure → empty file list."""
    monkeypatch.setattr(tfc, "_run_capture", lambda _a: (128, "", "bad object"))
    assert tfc._files_added_in_commit("deadbeef") == []


def test_build_test_impl_pairs_yields_one_entry_per_test_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex #1148 P1 fix — multiple test files for the same stem each get checked."""
    commits = [
        {"sha": "aaa1111", "message": "test: compliant first test"},
        {"sha": "bbb2222", "message": "feat: implement normalize"},
        {"sha": "ccc3333", "message": "test: later test for same stem"},
    ]
    files = {
        "aaa1111": ["tests/test_normalize.py"],
        "bbb2222": ["src/scieasy/util/normalize.py"],
        "ccc3333": ["tests/integration/test_normalize.py"],
    }
    monkeypatch.setattr(tfc, "_run_capture", _stub_run_capture(commits, files))
    findings = tfc.verify_ordering(42, "owner/repo")
    # The first test (aaa1111) precedes impl (bbb2222) — compliant.
    # The second test (ccc3333) comes AFTER impl — violation must be flagged.
    assert len(findings) == 1
    assert findings[0].file == "tests/integration/test_normalize.py"


def test_run_capture_invokes_subprocess_with_safe_kwargs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end ``_run_capture`` path: real subprocess.run gets a clean kwargs set."""
    monkeypatch.setattr(tfc.shutil, "which", lambda _: "/usr/bin/true")

    captured: dict[str, object] = {}

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        captured["args"] = args[0]
        captured["kwargs"] = kwargs

        class _Done:
            returncode = 0
            stdout = "out"
            stderr = "err"

        return _Done()

    monkeypatch.setattr(tfc.subprocess, "run", fake_run)
    rc, out, err = tfc._run_capture(["true", "x"])
    assert rc == 0
    assert out == "out"
    assert err == "err"
    assert captured["kwargs"]["encoding"] == "utf-8"
    assert captured["kwargs"]["errors"] == "replace"
    assert captured["kwargs"]["check"] is False
