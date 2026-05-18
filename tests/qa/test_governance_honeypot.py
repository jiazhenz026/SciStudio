"""Tests for ``scieasy.qa.governance.honeypot`` (TC-1E.4).

Marker-presence mode only — SHA-pinned verification is TC-1B.7 deliverable
and is TODO-marked in the implementation.
"""

from __future__ import annotations

import io
import subprocess
from collections.abc import Iterator
from contextlib import redirect_stderr
from pathlib import Path

import pytest

from scieasy.qa.governance.honeypot import check_honeypot, main

# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


def _seed(repo: Path, *, body: str | None = None, registry: str | None = None) -> Path:
    """Lay down a target file + a .governance-paths.yaml that registers it."""
    target = repo / ".governance-paths.yaml"
    target.write_text(
        registry
        or (
            "version: 1\n"
            'governance_paths: ["x"]\n'
            "honeypot_canaries:\n"
            '  - path: "canary.yaml"\n'
            '    marker_pattern: "# CANARY-DO-NOT-MODIFY: TRIPWIRE-RULE"\n'
        ),
        encoding="utf-8",
    )
    canary = repo / "canary.yaml"
    canary.write_text(
        body if body is not None else "# CANARY-DO-NOT-MODIFY: TRIPWIRE-RULE\nkey: value\n",
        encoding="utf-8",
    )
    return target


@pytest.fixture()
def repo(tmp_path: Path) -> Iterator[Path]:
    """Repo with init + a registered canary; default body keeps the marker."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=tmp_path, check=True)
    _seed(tmp_path)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=tmp_path, check=True)
    yield tmp_path


# --------------------------------------------------------------------------- #
# Marker presence                                                             #
# --------------------------------------------------------------------------- #


def test_intact_canary_yields_no_violations(repo: Path) -> None:
    violations = check_honeypot(repo / ".governance-paths.yaml", repo_root=repo)
    assert violations == []


def test_modified_marker_trips(repo: Path) -> None:
    (repo / "canary.yaml").write_text("# innocent comment\n", encoding="utf-8")
    violations = check_honeypot(repo / ".governance-paths.yaml", repo_root=repo)
    assert len(violations) == 1
    v = violations[0]
    assert v.rule_path == "canary.yaml"
    assert v.action_taken == "block-pr"


def test_missing_canary_file_trips(repo: Path) -> None:
    (repo / "canary.yaml").unlink()
    violations = check_honeypot(repo / ".governance-paths.yaml", repo_root=repo)
    assert len(violations) == 1


def test_action_taken_is_configurable(repo: Path) -> None:
    (repo / "canary.yaml").write_text("# tampered\n", encoding="utf-8")
    for action in ("auto-revert", "notify-only", "block-pr"):
        v = check_honeypot(repo / ".governance-paths.yaml", repo_root=repo, action=action)
        assert len(v) == 1
        assert v[0].action_taken == action


def test_invalid_action_rejected(repo: Path) -> None:
    with pytest.raises(ValueError):
        check_honeypot(repo / ".governance-paths.yaml", repo_root=repo, action="bogus")


def test_multiple_canaries(repo: Path) -> None:
    _seed(
        repo,
        registry=(
            "version: 1\n"
            'governance_paths: ["x"]\n'
            "honeypot_canaries:\n"
            '  - path: "canary.yaml"\n    marker_pattern: "MARKER-A"\n'
            '  - path: "other.yaml"\n    marker_pattern: "MARKER-B"\n'
        ),
        body="MARKER-A line\n",
    )
    (repo / "other.yaml").write_text("MARKER-B line\n", encoding="utf-8")
    assert check_honeypot(repo / ".governance-paths.yaml", repo_root=repo) == []
    # Tamper with one.
    (repo / "other.yaml").write_text("no marker here\n", encoding="utf-8")
    out = check_honeypot(repo / ".governance-paths.yaml", repo_root=repo)
    assert len(out) == 1
    assert out[0].rule_path == "other.yaml"


def test_skips_malformed_entries(repo: Path) -> None:
    _seed(
        repo,
        registry=(
            "version: 1\n"
            'governance_paths: ["x"]\n'
            "honeypot_canaries:\n"
            "  - 'this is not a dict'\n"
            "  - {path: '', marker_pattern: ''}\n"  # blank entries skipped
            '  - {path: "canary.yaml", marker_pattern: "MARKER"}\n'
        ),
        body="MARKER kept\n",
    )
    assert check_honeypot(repo / ".governance-paths.yaml", repo_root=repo) == []


def test_handles_missing_paths_yaml(tmp_path: Path) -> None:
    assert check_honeypot(tmp_path / "absent.yaml", repo_root=tmp_path) == []


def test_handles_invalid_yaml(tmp_path: Path) -> None:
    p = tmp_path / ".governance-paths.yaml"
    p.write_text(": bad", encoding="utf-8")
    assert check_honeypot(p, repo_root=tmp_path) == []


def test_records_last_commit_author_and_sha(repo: Path) -> None:
    (repo / "canary.yaml").write_text("# trip\n", encoding="utf-8")
    violations = check_honeypot(repo / ".governance-paths.yaml", repo_root=repo)
    assert len(violations) == 1
    assert violations[0].violating_author  # populated from git log
    assert len(violations[0].violating_commit_sha) >= 7  # SHA-like


def test_records_empty_strings_when_git_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Force ``git`` subprocesses to fail and verify graceful degradation."""
    _seed(tmp_path, body="no marker")
    import scieasy.qa.governance.honeypot as mod

    def _boom(*_a, **_kw):
        raise FileNotFoundError("git not found")

    monkeypatch.setattr(mod.subprocess, "run", _boom)
    violations = check_honeypot(tmp_path / ".governance-paths.yaml", repo_root=tmp_path)
    assert len(violations) == 1
    assert violations[0].violating_commit_sha == ""
    assert violations[0].violating_author == ""


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #


def test_main_returns_zero_when_intact(repo: Path) -> None:
    rc = main(["--paths-yaml", ".governance-paths.yaml", "--repo-root", str(repo)])
    assert rc == 0


def test_main_returns_one_when_tripped(repo: Path) -> None:
    (repo / "canary.yaml").write_text("tampered\n", encoding="utf-8")
    buf = io.StringIO()
    with redirect_stderr(buf):
        rc = main(
            [
                "--paths-yaml",
                ".governance-paths.yaml",
                "--repo-root",
                str(repo),
                "--check-all",
            ]
        )
    assert rc == 1
    assert "canary.yaml" in buf.getvalue()


def test_main_returns_two_when_paths_yaml_missing(tmp_path: Path) -> None:
    buf = io.StringIO()
    with redirect_stderr(buf):
        rc = main(
            [
                "--paths-yaml",
                "no-such.yaml",
                "--repo-root",
                str(tmp_path),
            ]
        )
    assert rc == 2
    assert "paths-yaml-missing" in buf.getvalue()


def test_main_accepts_absolute_paths_yaml(repo: Path) -> None:
    abs_path = (repo / ".governance-paths.yaml").resolve()
    rc = main(["--paths-yaml", str(abs_path), "--repo-root", str(repo)])
    assert rc == 0


def test_main_action_choice_passed_through(repo: Path) -> None:
    (repo / "canary.yaml").write_text("tampered\n", encoding="utf-8")
    buf = io.StringIO()
    with redirect_stderr(buf):
        rc = main(
            [
                "--paths-yaml",
                ".governance-paths.yaml",
                "--repo-root",
                str(repo),
                "--action",
                "notify-only",
            ]
        )
    assert rc == 1
    assert '"action_taken":"notify-only"' in buf.getvalue()
