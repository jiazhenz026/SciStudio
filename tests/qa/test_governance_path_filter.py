"""Tests for ``scieasy.qa.governance.path_filter`` (TC-1E.6 §3.5 audit-fix C2)."""

from __future__ import annotations

import io
import subprocess
from contextlib import redirect_stderr
from pathlib import Path

import pytest

from scieasy.qa.governance.path_filter import filter as path_filter_fn
from scieasy.qa.governance.path_filter import main


def _git_init(repo: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, check=True)


def _commit(repo: Path, msg: str) -> str:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=repo, check=True)
    out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True)
    return out.stdout.strip()


def _seed_paths_yaml(repo: Path) -> Path:
    p = repo / ".governance-paths.yaml"
    p.write_text(
        'version: 1\ngovernance_paths:\n  - "docs/adr/**"\n  - "CLAUDE.md"\nhoneypot_canaries: []\n',
        encoding="utf-8",
    )
    return p


# --------------------------------------------------------------------------- #
# filter() function                                                           #
# --------------------------------------------------------------------------- #


def test_returns_true_when_governance_path_touched(tmp_path: Path) -> None:
    _git_init(tmp_path)
    p = _seed_paths_yaml(tmp_path)
    (tmp_path / "docs" / "adr").mkdir(parents=True)
    (tmp_path / "docs" / "adr" / "ADR-099.md").write_text("# old\n", encoding="utf-8")
    base = _commit(tmp_path, "base")
    (tmp_path / "docs" / "adr" / "ADR-099.md").write_text("# new\n", encoding="utf-8")
    head = _commit(tmp_path, "edit ADR")
    out = tmp_path / "github_output.txt"
    touched = path_filter_fn(p, base, head, out, repo_root=tmp_path)
    assert touched is True
    assert "touched=true" in out.read_text(encoding="utf-8")


def test_returns_false_when_no_governance_path_touched(tmp_path: Path) -> None:
    _git_init(tmp_path)
    p = _seed_paths_yaml(tmp_path)
    (tmp_path / "src.txt").write_text("hello\n", encoding="utf-8")
    base = _commit(tmp_path, "base")
    (tmp_path / "src.txt").write_text("hello world\n", encoding="utf-8")
    head = _commit(tmp_path, "edit non-governance")
    out = tmp_path / "github_output.txt"
    touched = path_filter_fn(p, base, head, out, repo_root=tmp_path)
    assert touched is False
    assert "touched=false" in out.read_text(encoding="utf-8")


def test_appends_to_output_file_preserving_existing_lines(tmp_path: Path) -> None:
    """GitHub Actions accumulates step outputs in $GITHUB_OUTPUT — never overwrite."""
    _git_init(tmp_path)
    p = _seed_paths_yaml(tmp_path)
    (tmp_path / "x").write_text("1", encoding="utf-8")
    base = _commit(tmp_path, "base")
    (tmp_path / "x").write_text("2", encoding="utf-8")
    head = _commit(tmp_path, "head")
    out = tmp_path / "github_output.txt"
    out.write_text("previous_step_output=42\n", encoding="utf-8")
    path_filter_fn(p, base, head, out, repo_root=tmp_path)
    body = out.read_text(encoding="utf-8")
    assert "previous_step_output=42" in body
    assert "touched=" in body


def test_creates_output_parent_directory(tmp_path: Path) -> None:
    _git_init(tmp_path)
    p = _seed_paths_yaml(tmp_path)
    (tmp_path / "x").write_text("1", encoding="utf-8")
    base = _commit(tmp_path, "base")
    (tmp_path / "x").write_text("2", encoding="utf-8")
    head = _commit(tmp_path, "head")
    out = tmp_path / "subdir" / "github_output.txt"
    path_filter_fn(p, base, head, out, repo_root=tmp_path)
    assert out.is_file()


def test_returns_false_when_governance_yaml_missing(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "x").write_text("1", encoding="utf-8")
    base = _commit(tmp_path, "base")
    (tmp_path / "x").write_text("2", encoding="utf-8")
    head = _commit(tmp_path, "head")
    out = tmp_path / "github_output.txt"
    # No .governance-paths.yaml at all → no globs → touched=False.
    fake_yaml = tmp_path / "absent.yaml"
    fake_yaml.write_text("", encoding="utf-8")
    touched = path_filter_fn(fake_yaml, base, head, out, repo_root=tmp_path)
    assert touched is False


def test_fails_closed_when_git_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Codex P1 fix: when git is missing the filter must fail-closed
    (``touched=true``) so the workflow's downstream governance checks
    still run instead of being silently skipped."""
    p = _seed_paths_yaml(tmp_path)

    import scieasy.qa.governance.path_filter as mod

    def _boom(*_a, **_kw):
        raise FileNotFoundError("simulated missing git")

    monkeypatch.setattr(mod.subprocess, "run", _boom)
    out = tmp_path / "github_output.txt"
    touched = path_filter_fn(p, "BASE", "HEAD", out, repo_root=tmp_path)
    assert touched is True
    body = out.read_text(encoding="utf-8")
    assert "touched=true" in body
    assert "path_filter_error=" in body  # error reason logged


def test_fails_closed_when_git_returns_nonzero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Codex P1 fix: a non-zero git exit (e.g. unavailable base SHA in
    the checkout) must fail-closed."""
    p = _seed_paths_yaml(tmp_path)
    import scieasy.qa.governance.path_filter as mod

    class _Out:
        returncode = 128
        stdout = ""
        stderr = "fatal: bad revision 'BASE..HEAD'"

    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _Out())
    out = tmp_path / "github_output.txt"
    touched = path_filter_fn(p, "BASE", "HEAD", out, repo_root=tmp_path)
    assert touched is True
    assert "touched=true" in out.read_text(encoding="utf-8")


def test_honours_caller_provided_paths_yaml(tmp_path: Path) -> None:
    """Codex P2 fix: the caller-provided ``paths_yaml`` must be the
    source of governance globs — NOT a hard-coded
    ``repo_root/.governance-paths.yaml`` lookup."""
    # Put a *different* registry at the caller-provided location and a
    # broader (would-match) one at the repo-root default location.
    caller_yaml = tmp_path / "custom" / "my-paths.yaml"
    caller_yaml.parent.mkdir(parents=True)
    caller_yaml.write_text(
        'version: 1\ngovernance_paths:\n  - "ONLY_THIS.md"\nhoneypot_canaries: []\n',
        encoding="utf-8",
    )
    # Default location declares the broader registry — if the impl reads
    # this by mistake, the test will see a false touched=true.
    (tmp_path / ".governance-paths.yaml").write_text(
        'version: 1\ngovernance_paths:\n  - "**"\nhoneypot_canaries: []\n',
        encoding="utf-8",
    )
    _git_init(tmp_path)
    (tmp_path / "x.txt").write_text("v1\n", encoding="utf-8")
    base = _commit(tmp_path, "base")
    (tmp_path / "x.txt").write_text("v2\n", encoding="utf-8")
    head = _commit(tmp_path, "head")

    out = tmp_path / "github_output.txt"
    touched = path_filter_fn(caller_yaml, base, head, out, repo_root=tmp_path)
    # ``x.txt`` does NOT match ``ONLY_THIS.md``; if the impl were reading
    # ``.governance-paths.yaml`` it would match the broader ``**``.
    assert touched is False


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #


def test_main_returns_zero_on_no_touch(tmp_path: Path) -> None:
    _git_init(tmp_path)
    _seed_paths_yaml(tmp_path)
    (tmp_path / "a").write_text("1", encoding="utf-8")
    base = _commit(tmp_path, "base")
    (tmp_path / "a").write_text("2", encoding="utf-8")
    head = _commit(tmp_path, "head")
    out = tmp_path / "github_output.txt"
    rc = main(
        [
            "--paths-yaml",
            ".governance-paths.yaml",
            "--base",
            base,
            "--head",
            head,
            "--output",
            str(out),
            "--repo-root",
            str(tmp_path),
        ]
    )
    assert rc == 0
    assert "touched=false" in out.read_text(encoding="utf-8")


def test_main_returns_zero_on_governance_touch(tmp_path: Path) -> None:
    _git_init(tmp_path)
    _seed_paths_yaml(tmp_path)
    (tmp_path / "CLAUDE.md").write_text("v1\n", encoding="utf-8")
    base = _commit(tmp_path, "base")
    (tmp_path / "CLAUDE.md").write_text("v2\n", encoding="utf-8")
    head = _commit(tmp_path, "head")
    out = tmp_path / "github_output.txt"
    rc = main(
        [
            "--paths-yaml",
            ".governance-paths.yaml",
            "--base",
            base,
            "--head",
            head,
            "--output",
            str(out),
            "--repo-root",
            str(tmp_path),
        ]
    )
    assert rc == 0  # touched is not an error — workflow consumes the flag.
    assert "touched=true" in out.read_text(encoding="utf-8")


def test_main_returns_two_when_paths_yaml_missing(tmp_path: Path) -> None:
    buf = io.StringIO()
    with redirect_stderr(buf):
        rc = main(
            [
                "--paths-yaml",
                "no-such.yaml",
                "--base",
                "main",
                "--head",
                "HEAD",
                "--output",
                str(tmp_path / "out.txt"),
                "--repo-root",
                str(tmp_path),
            ]
        )
    assert rc == 2
    assert "paths-yaml-missing" in buf.getvalue()


def test_main_accepts_absolute_paths_yaml(tmp_path: Path) -> None:
    _git_init(tmp_path)
    abs_yaml = _seed_paths_yaml(tmp_path)
    (tmp_path / "x").write_text("1", encoding="utf-8")
    base = _commit(tmp_path, "base")
    (tmp_path / "x").write_text("2", encoding="utf-8")
    head = _commit(tmp_path, "head")
    rc = main(
        [
            "--paths-yaml",
            str(abs_yaml.resolve()),
            "--base",
            base,
            "--head",
            head,
            "--output",
            str(tmp_path / "out.txt"),
            "--repo-root",
            str(tmp_path),
        ]
    )
    assert rc == 0
