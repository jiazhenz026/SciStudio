"""Tests for ``scieasy.qa.governance.path_filter`` (TC-1E.6 part A).

Covers:

- Glob matching (literal, ``*``, ``**``, leading-dot files, nested).
- Empty / missing / malformed YAML registry.
- GITHUB_OUTPUT writer: ``touched=true|false`` line + matched heredoc.
- Public ``filter()`` entrypoint return value.
- CLI exit code + missing-paths-yaml branch.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from scieasy.qa.governance.path_filter import (
    _GitDiffError,
    _matches,
    _matches_any,
    main,
)
from scieasy.qa.governance.path_filter import (
    filter as path_filter_fn,
)

# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout


def _git_init(repo: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, check=True)


def _commit(repo: Path, msg: str) -> str:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=repo, check=True)
    return _git(repo, "rev-parse", "HEAD").strip()


def _write(repo: Path, rel: str, content: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Iterator[Path]:
    _git_init(tmp_path)
    _write(
        tmp_path,
        ".governance-paths.yaml",
        """version: 1
governance_paths:
  - "docs/adr/**"
  - "CLAUDE.md"
  - "**/AGENTS.md"
  - ".github/workflows/**"
  - "src/scieasy/qa/**"
""",
    )
    _write(tmp_path, "README.md", "hello\n")
    _commit(tmp_path, "init")
    subprocess.run(["git", "checkout", "-q", "-b", "feature"], cwd=tmp_path, check=True)
    yield tmp_path


# --------------------------------------------------------------------------- #
# Pure matcher tests                                                          #
# --------------------------------------------------------------------------- #


class TestMatches:
    def test_literal_match(self):
        assert _matches("CLAUDE.md", "CLAUDE.md")

    def test_literal_mismatch(self):
        assert not _matches("README.md", "CLAUDE.md")

    def test_double_star_subtree(self):
        assert _matches("docs/adr/ADR-042.md", "docs/adr/**")

    def test_double_star_nested_subtree(self):
        assert _matches("docs/adr/_template/x.md", "docs/adr/**")

    def test_double_star_leading(self):
        assert _matches("src/foo/AGENTS.md", "**/AGENTS.md")

    def test_double_star_root_match(self):
        # **/AGENTS.md should match AGENTS.md at root too (zero-component case).
        assert _matches("AGENTS.md", "**/AGENTS.md")

    def test_star_glob_one_component(self):
        assert _matches("scripts/foo.py", "scripts/*.py")

    def test_star_glob_does_not_cross_slash(self):
        assert not _matches("scripts/sub/foo.py", "scripts/*.py")

    def test_dot_file(self):
        assert _matches(".github/workflows/ci.yml", ".github/workflows/**")


class TestMatchesAny:
    def test_matches_any_hits_first(self):
        globs = ["docs/**", "src/**"]
        assert _matches_any("docs/adr/x.md", globs)

    def test_matches_any_no_hit(self):
        globs = ["docs/**", "src/**"]
        assert not _matches_any("README.md", globs)


# --------------------------------------------------------------------------- #
# filter() entrypoint                                                         #
# --------------------------------------------------------------------------- #


def test_filter_returns_true_when_governance_path_touched(repo: Path, tmp_path: Path):
    _write(repo, "docs/adr/ADR-999.md", "x")
    _commit(repo, "add adr")
    output = tmp_path / "gh.out"
    touched = path_filter_fn(
        repo / ".governance-paths.yaml",
        base="main",
        head="HEAD",
        output=output,
        repo_root=repo,
    )
    assert touched is True
    body = output.read_text(encoding="utf-8")
    assert "touched=true" in body
    assert "docs/adr/ADR-999.md" in body


def test_filter_returns_false_when_no_governance_path_touched(repo: Path, tmp_path: Path):
    _write(repo, "README.md", "hi\n")
    _commit(repo, "edit readme")
    output = tmp_path / "gh.out"
    touched = path_filter_fn(
        repo / ".governance-paths.yaml",
        base="main",
        head="HEAD",
        output=output,
        repo_root=repo,
    )
    assert touched is False
    assert output.read_text(encoding="utf-8").strip() == "touched=false"


def test_filter_with_empty_governance_list(repo: Path, tmp_path: Path):
    _write(repo, ".governance-paths.yaml", "version: 1\ngovernance_paths: []\n")
    _commit(repo, "drain registry")
    output = tmp_path / "gh.out"
    touched = path_filter_fn(
        repo / ".governance-paths.yaml",
        base="main",
        head="HEAD",
        output=output,
        repo_root=repo,
    )
    assert touched is False


def test_filter_with_malformed_yaml(repo: Path, tmp_path: Path):
    _write(repo, ".governance-paths.yaml", "::: not valid yaml :::")
    _commit(repo, "break yaml")
    output = tmp_path / "gh.out"
    touched = path_filter_fn(
        repo / ".governance-paths.yaml",
        base="main",
        head="HEAD",
        output=output,
        repo_root=repo,
    )
    assert touched is False


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #


def test_cli_writes_touched_true(repo: Path, tmp_path: Path):
    _write(repo, "docs/adr/ADR-998.md", "x")
    _commit(repo, "add adr")
    output = tmp_path / "gh.out"
    rc = main(
        [
            "--paths-yaml",
            str(repo / ".governance-paths.yaml"),
            "--base",
            "main",
            "--head",
            "HEAD",
            "--output",
            str(output),
            "--repo-root",
            str(repo),
        ]
    )
    assert rc == 0
    assert "touched=true" in output.read_text(encoding="utf-8")


def test_cli_writes_touched_false_when_paths_yaml_missing(tmp_path: Path):
    output = tmp_path / "gh.out"
    rc = main(
        [
            "--paths-yaml",
            str(tmp_path / "nope.yaml"),
            "--base",
            "main",
            "--head",
            "HEAD",
            "--output",
            str(output),
            "--repo-root",
            str(tmp_path),
        ]
    )
    assert rc == 0
    assert "touched=false" in output.read_text(encoding="utf-8")


def test_cli_default_paths_yaml_relative_to_repo(repo: Path, tmp_path: Path):
    _write(repo, "src/scieasy/qa/foo.py", "x = 1\n")
    _commit(repo, "edit qa")
    output = tmp_path / "gh.out"
    rc = main(
        [
            "--base",
            "main",
            "--head",
            "HEAD",
            "--output",
            str(output),
            "--repo-root",
            str(repo),
        ]
    )
    assert rc == 0
    assert "touched=true" in output.read_text(encoding="utf-8")


def test_emit_falls_back_to_stdout_on_oserror(repo: Path, capsys, monkeypatch):
    """When the GITHUB_OUTPUT path is unwritable, _emit falls back to stdout."""
    from scieasy.qa.governance import path_filter as pf

    # The function uses `output.open("a", ...)`; we can replace Path.open
    # with a lambda that raises OSError when the path looks like our
    # fake output path.
    real_open = Path.open

    def fake_open(self, *args, **kwargs):
        if str(self).endswith("blocked.out"):
            raise OSError("simulated")
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fake_open)

    _write(repo, "docs/adr/ADR-X.md", "x")
    _commit(repo, "add adr")
    output = Path("blocked.out")  # relative, will trip the monkeypatch
    pf.filter(
        repo / ".governance-paths.yaml",
        base="main",
        head="HEAD",
        output=output,
        repo_root=repo,
    )
    captured = capsys.readouterr()
    assert "touched=true" in captured.out


def test_diff_helper_raises_on_git_failure(tmp_path: Path, monkeypatch):
    """_git_diff_names raises _GitDiffError when the subprocess returns non-zero.

    #1178: fail-closed semantics — callers that want ``touched=true`` on
    error catch this exception.
    """
    from scieasy.qa.governance import path_filter as pf

    class _FakeResult:
        returncode = 1
        stdout = ""
        stderr = "fatal: not a repo"

    def fake_run(*a, **kw):
        return _FakeResult()

    monkeypatch.setattr(pf.subprocess, "run", fake_run)
    with pytest.raises(_GitDiffError):
        pf._git_diff_names(tmp_path, "a", "b")


def test_diff_helper_raises_when_git_missing(tmp_path: Path, monkeypatch):
    """_git_diff_names raises _GitDiffError when git is not installed.

    #1178: fail-closed semantics.
    """
    from scieasy.qa.governance import path_filter as pf

    def fake_run(*a, **kw):
        raise FileNotFoundError("no git")

    monkeypatch.setattr(pf.subprocess, "run", fake_run)
    with pytest.raises(_GitDiffError):
        pf._git_diff_names(tmp_path, "a", "b")


def test_filter_fail_closed_when_git_not_found(repo: Path, tmp_path: Path, monkeypatch):
    """filter() returns True and writes touched=true when git is unavailable (#1178).

    Without fail-closed semantics a FileNotFoundError would silently skip all
    downstream governance checks because filter() would write ``touched=false``.
    """
    from scieasy.qa.governance import path_filter as pf

    def fake_run(*a, **kw):
        raise FileNotFoundError("no git")

    monkeypatch.setattr(pf.subprocess, "run", fake_run)
    output = tmp_path / "gh.out"
    touched = pf.filter(
        repo / ".governance-paths.yaml",
        base="main",
        head="HEAD",
        output=output,
        repo_root=repo,
    )
    assert touched is True
    body = output.read_text(encoding="utf-8")
    assert "touched=true" in body
    assert "path_filter_error=" in body


def test_filter_fail_closed_on_nonzero_git_exit(repo: Path, tmp_path: Path, monkeypatch):
    """filter() returns True and writes touched=true when git diff exits non-zero (#1178)."""
    from scieasy.qa.governance import path_filter as pf

    class _FakeResult:
        returncode = 1
        stdout = ""
        stderr = "fatal: bad revision"

    def fake_run(*a, **kw):
        return _FakeResult()

    monkeypatch.setattr(pf.subprocess, "run", fake_run)
    output = tmp_path / "gh.out"
    touched = pf.filter(
        repo / ".governance-paths.yaml",
        base="main",
        head="HEAD",
        output=output,
        repo_root=repo,
    )
    assert touched is True
    body = output.read_text(encoding="utf-8")
    assert "touched=true" in body
    assert "path_filter_error=" in body


def test_filter_uses_three_dot_diff(repo: Path, tmp_path: Path):
    """filter() must use 'git diff base...head' (three dots) not 'base..head'.

    Three-dot diff computes changes from the merge-base of base and head,
    so commits on base that are not in head's ancestry are excluded (#1180).

    We verify the three-dot command is used by capturing the git subprocess args.
    """
    import unittest.mock as mock

    from scieasy.qa.governance import path_filter as pf

    captured_args: list[list[str]] = []
    real_run = pf.subprocess.run

    def spy_run(args, **kw):
        captured_args.append(list(args))
        return real_run(args, **kw)

    with mock.patch("scieasy.qa.governance.path_filter.subprocess.run", side_effect=spy_run):
        output = tmp_path / "gh.out"
        pf.filter(
            repo / ".governance-paths.yaml",
            base="main",
            head="HEAD",
            output=output,
            repo_root=repo,
        )

    diff_calls = [a for a in captured_args if "diff" in a]
    assert diff_calls, "Expected at least one git diff call"
    for args in diff_calls:
        # Each diff call must use three-dot form
        range_args = [a for a in args if ".." in a]
        for ra in range_args:
            assert "..." in ra, f"Expected three-dot diff but got: {ra}"


def test_three_dot_diff_no_false_positive_for_base_only_commits(tmp_path: Path):
    """Regression: base-only commits must NOT trigger governance findings.

    This test builds a diverged history:
    - main: init → extra-commit (modifying README.md only)
    - feature (branched from init): commits touching ONLY non-governance files

    With two-dot diff, extra-commit would be in the diff; with three-dot
    diff it is excluded.  The feature branch must produce ``touched=false``.
    """
    # Initialise repo
    _git_init(tmp_path)
    _write(
        tmp_path,
        ".governance-paths.yaml",
        "version: 1\ngovernance_paths:\n  - 'docs/adr/**'\n  - 'CLAUDE.md'\n",
    )
    _write(tmp_path, "README.md", "initial\n")
    _commit(tmp_path, "init")

    # Create feature branch at this point (feature diverges here)
    subprocess.run(["git", "checkout", "-q", "-b", "feature"], cwd=tmp_path, check=True)
    _write(tmp_path, "src/app.py", "x = 1\n")
    feature_head = _commit(tmp_path, "add app.py (non-governance)")

    # Back to main, add a commit that touches ONLY README.md (non-governance)
    subprocess.run(["git", "checkout", "-q", "main"], cwd=tmp_path, check=True)
    _write(tmp_path, "README.md", "updated by main\n")
    _commit(tmp_path, "main-only: update README (non-governance)")

    # Run filter from feature's perspective: base=main, head=feature_head.
    # Three-dot diff: only changes between merge-base and feature_head.
    # The main-only commit is NOT in feature's ancestry → excluded → touched=false.
    output = tmp_path / "gh.out"
    touched = path_filter_fn(
        tmp_path / ".governance-paths.yaml",
        base="main",
        head=feature_head,
        output=output,
        repo_root=tmp_path,
    )
    assert touched is False, (
        "Three-dot diff should exclude base-only commits; got touched=True which means two-dot diff is being used"
    )
