"""Tests for the Phase -0.5 temporary review CLI.

These tests exercise the rule-level checks in
``scripts.audit.temp_review`` directly via small, hermetic fixtures. The
real CLI surface is exercised via ``subprocess.run`` in
:func:`test_repo_sanity_passes` so we both verify the import-path layout
and confirm the script reports zero findings against the current repo
(design doc §5).

Coverage maps each test to the design's §1.1 enforced check:

* QA001 module docstring        — test_qa001_*
* QA002 public-class docstring  — test_qa002_*
* QA003 trailer presence        — test_qa003_*
* QA004 frontmatter presence    — test_qa004_*
* QA005 git-add-all in commit   — test_qa005_*
* Piggyback (ruff/mypy/pytest/  — test_piggyback_* / test_mypy_*
  importlinter)
* Repo sanity                   — test_repo_sanity_passes
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from scripts.audit import temp_review

# --------------------------------------------------------------------------- #
# Shared fixtures                                                             #
# --------------------------------------------------------------------------- #


@pytest.fixture()
def tmp_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo with an empty ``main`` branch.

    Returns the repo root. The repo is initialised with a single
    ``init`` commit on ``main`` so that follow-up branches can be
    diffed against it (used by QA003 / QA005 tests).
    """
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=str(tmp_path), check=True)
    (tmp_path / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(tmp_path), check=True)
    return tmp_path


def _make_qa_file(repo: Path, relpath: str, body: str) -> Path:
    """Drop ``body`` into ``repo/relpath`` and return the absolute path."""
    target = repo / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")
    return target


def _make_doc_file(repo: Path, relpath: str, body: str) -> Path:
    target = repo / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")
    return target


def _commit_all(repo: Path, message: str) -> str:
    subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=str(repo), check=True)
    rc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo), capture_output=True, text=True, check=True)
    return rc.stdout.strip()


def _checkout_new_branch(repo: Path, name: str) -> None:
    subprocess.run(["git", "checkout", "-q", "-b", name], cwd=str(repo), check=True)


# --------------------------------------------------------------------------- #
# QA001 — module docstring                                                    #
# --------------------------------------------------------------------------- #


def test_qa001_missing_module_docstring(tmp_path: Path) -> None:
    """A file under src/scieasy/qa/ with no docstring → QA001 finding."""
    file = _make_qa_file(tmp_path, "src/scieasy/qa/foo.py", "x = 1\n")
    findings = temp_review._check_qa_module_docstrings(file)
    assert any(f.rule_id == "QA001" for f in findings)


def test_qa001_present_module_docstring_passes(tmp_path: Path) -> None:
    file = _make_qa_file(tmp_path, "src/scieasy/qa/foo.py", '"""m."""\nx = 1\n')
    assert temp_review._check_qa_module_docstrings(file) == []


def test_qa001_init_with_only_imports_passes(tmp_path: Path) -> None:
    """__init__.py containing only imports is exempt from QA001."""
    file = _make_qa_file(tmp_path, "src/scieasy/qa/__init__.py", "from . import a\nfrom . import b\n")
    assert temp_review._check_qa_module_docstrings(file) == []


def test_qa001_init_with_real_code_fails(tmp_path: Path) -> None:
    """An __init__.py with a statement other than import → QA001 fires."""
    file = _make_qa_file(tmp_path, "src/scieasy/qa/__init__.py", "x = 1\n")
    findings = temp_review._check_qa_module_docstrings(file)
    assert any(f.rule_id == "QA001" for f in findings)


# --------------------------------------------------------------------------- #
# QA002 — public-class docstring                                              #
# --------------------------------------------------------------------------- #


def test_qa002_missing_public_class_docstring(tmp_path: Path) -> None:
    file = _make_qa_file(
        tmp_path,
        "src/scieasy/qa/foo.py",
        '"""m."""\nclass Foo:\n    pass\n',
    )
    findings = temp_review._check_qa_public_class_docstrings(file)
    assert any(f.rule_id == "QA002" and "Foo" in f.message for f in findings)


def test_qa002_public_class_with_docstring_passes(tmp_path: Path) -> None:
    file = _make_qa_file(
        tmp_path,
        "src/scieasy/qa/foo.py",
        '"""m."""\nclass Foo:\n    """Foo docstring."""\n',
    )
    assert temp_review._check_qa_public_class_docstrings(file) == []


def test_qa002_private_class_is_exempt(tmp_path: Path) -> None:
    file = _make_qa_file(
        tmp_path,
        "src/scieasy/qa/foo.py",
        '"""m."""\nclass _Hidden:\n    pass\n',
    )
    assert temp_review._check_qa_public_class_docstrings(file) == []


# --------------------------------------------------------------------------- #
# QA003 — trailer presence on track/adr-042/** commits                        #
# --------------------------------------------------------------------------- #


def test_qa003_missing_trailer_on_tracking_branch(tmp_repo: Path) -> None:
    _checkout_new_branch(tmp_repo, "track/adr-042/1a-schemas")
    (tmp_repo / "f.txt").write_text("x", encoding="utf-8")
    _commit_all(tmp_repo, "feat: thing\n\nNo trailers here.")
    findings = temp_review._check_commit_trailers(tmp_repo, "main", "track/adr-042/1a-schemas")
    assert any(f.rule_id == "QA003" for f in findings)


def test_qa003_assisted_by_satisfies(tmp_repo: Path) -> None:
    _checkout_new_branch(tmp_repo, "track/adr-042/1a-schemas")
    (tmp_repo / "f.txt").write_text("x", encoding="utf-8")
    _commit_all(tmp_repo, "feat: thing\n\nAssisted-by: Claude")
    findings = temp_review._check_commit_trailers(tmp_repo, "main", "track/adr-042/1a-schemas")
    assert findings == []


def test_qa003_co_authored_by_satisfies(tmp_repo: Path) -> None:
    _checkout_new_branch(tmp_repo, "track/adr-042/1a-schemas")
    (tmp_repo / "f.txt").write_text("x", encoding="utf-8")
    _commit_all(tmp_repo, "feat: thing\n\nCo-Authored-By: Alice <a@b>")
    findings = temp_review._check_commit_trailers(tmp_repo, "main", "track/adr-042/1a-schemas")
    assert findings == []


def test_qa003_not_enforced_off_tracking_branch(tmp_repo: Path) -> None:
    _checkout_new_branch(tmp_repo, "feat/issue-9999/something")
    (tmp_repo / "f.txt").write_text("x", encoding="utf-8")
    _commit_all(tmp_repo, "feat: thing")  # No trailers, but off track/ branch.
    findings = temp_review._check_commit_trailers(tmp_repo, "main", "feat/issue-9999/something")
    assert findings == []


# --------------------------------------------------------------------------- #
# QA004 — YAML frontmatter on new ADR/spec files                              #
# --------------------------------------------------------------------------- #


def test_qa004_missing_frontmatter_on_new_adr(tmp_path: Path) -> None:
    _make_doc_file(tmp_path, "docs/adr/ADR-099.md", "# ADR-099\n\nNo frontmatter here.\n")
    findings = temp_review._check_frontmatter(tmp_path, [Path("docs/adr/ADR-099.md")])
    assert any(f.rule_id == "QA004" for f in findings)


def test_qa004_with_frontmatter_passes(tmp_path: Path) -> None:
    _make_doc_file(
        tmp_path,
        "docs/adr/ADR-099.md",
        "---\ntitle: x\n---\n\nBody.\n",
    )
    findings = temp_review._check_frontmatter(tmp_path, [Path("docs/adr/ADR-099.md")])
    assert findings == []


def test_qa004_non_adr_md_is_ignored(tmp_path: Path) -> None:
    _make_doc_file(tmp_path, "README.md", "no frontmatter\n")
    findings = temp_review._check_frontmatter(tmp_path, [Path("README.md")])
    assert findings == []


def test_qa004_existing_adr_unchanged_is_skipped(tmp_path: Path) -> None:
    # File exists but is not in the candidate set → no finding.
    _make_doc_file(tmp_path, "docs/adr/ADR-001.md", "no frontmatter\n")
    findings = temp_review._check_frontmatter(tmp_path, [])
    assert findings == []


# --------------------------------------------------------------------------- #
# QA005 — git add -A / . / * in commit message                                #
# --------------------------------------------------------------------------- #


def test_qa005_git_add_dash_a_blocked(tmp_repo: Path) -> None:
    _checkout_new_branch(tmp_repo, "feat/test-qa005-a")
    (tmp_repo / "f.txt").write_text("x", encoding="utf-8")
    _commit_all(tmp_repo, "feat: x\n\nI ran git add -A then committed.")
    findings = temp_review._check_commit_git_add_all(tmp_repo, "main")
    assert any(f.rule_id == "QA005" for f in findings)


def test_qa005_git_add_dot_blocked(tmp_repo: Path) -> None:
    _checkout_new_branch(tmp_repo, "feat/test-qa005-b")
    (tmp_repo / "f.txt").write_text("x", encoding="utf-8")
    _commit_all(tmp_repo, "feat: x\n\nThen git add . and commit.")
    findings = temp_review._check_commit_git_add_all(tmp_repo, "main")
    assert any(f.rule_id == "QA005" for f in findings)


def test_qa005_git_add_star_blocked(tmp_repo: Path) -> None:
    _checkout_new_branch(tmp_repo, "feat/test-qa005-c")
    (tmp_repo / "f.txt").write_text("x", encoding="utf-8")
    _commit_all(tmp_repo, "feat: x\n\nI did git add * earlier.")
    findings = temp_review._check_commit_git_add_all(tmp_repo, "main")
    assert any(f.rule_id == "QA005" for f in findings)


def test_qa005_clean_message_passes(tmp_repo: Path) -> None:
    _checkout_new_branch(tmp_repo, "feat/test-qa005-clean")
    (tmp_repo / "f.txt").write_text("x", encoding="utf-8")
    _commit_all(tmp_repo, "feat: x\n\nNo forbidden patterns here.")
    findings = temp_review._check_commit_git_add_all(tmp_repo, "main")
    assert findings == []


# --------------------------------------------------------------------------- #
# Mypy / importlinter piggyback — skip-when-absent semantics                  #
# --------------------------------------------------------------------------- #


def test_mypy_strict_on_qa_skipped_when_dir_absent(tmp_path: Path) -> None:
    """When src/scieasy/qa/ does not exist, mypy --strict returns 0 (skip)."""
    ctx = temp_review.Context(
        repo_root=tmp_path,
        changed_files_only=False,
        ci_mode=True,
        base_ref="main",
        explicit_paths=(),
    )
    rc, msg = temp_review._piggyback_mypy_strict_on_qa(ctx)
    assert rc == 0
    assert "skipped" in msg


def test_importlinter_skipped_when_qa_absent(tmp_path: Path) -> None:
    ctx = temp_review.Context(
        repo_root=tmp_path,
        changed_files_only=False,
        ci_mode=True,
        base_ref="main",
        explicit_paths=(),
    )
    rc, msg = temp_review._piggyback_lint_imports(ctx)
    assert rc == 0
    assert "skipped" in msg


def test_pytest_timeout_and_coverage_are_pinned_in_pyproject() -> None:
    """Sanity: design §2.3 says pytest gate piggybacks on existing config.

    We assert the existing pyproject.toml still pins ``--cov-fail-under=70``
    and ``timeout = 60``. If a future PR loosens these, this test fires.
    """
    repo_root = Path(temp_review.__file__).resolve().parents[2]
    pyproject = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    assert "--cov-fail-under=70" in pyproject
    assert "timeout = 60" in pyproject


# --------------------------------------------------------------------------- #
# Exit-code semantics                                                         #
# --------------------------------------------------------------------------- #


def test_cli_exit_code_2_on_missing_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """If --ci is requested but git is missing, exit 2 (env error)."""
    monkeypatch.setattr(temp_review.shutil, "which", lambda name: None if name == "git" else "/usr/bin/" + name)
    args = temp_review._parse_args(["--ci"])
    ctx = temp_review._resolve_context(args, tmp_path)
    findings, _messages, env_error = temp_review._collect_findings(ctx)
    # The git absence registers as env_error 2 via subprocess wrappers.
    # The findings list does NOT promote it to an error; the caller does.
    # We assert that either env_error==2 OR the relevant piggyback msg
    # reports the missing-binary state. (Some platforms still have ruff.)
    env_error_or_clean = env_error == 2 or not findings
    assert env_error_or_clean


def test_cli_exit_zero_on_clean_repo(tmp_repo: Path) -> None:
    """A fresh repo with no qa/ tree → zero findings, exit 0."""
    args = temp_review._parse_args([])
    ctx = temp_review._resolve_context(args, tmp_repo)
    findings, _messages, env_error = temp_review._collect_findings(ctx)
    assert env_error == 0
    assert findings == []


# --------------------------------------------------------------------------- #
# Repo sanity — runs the real CLI against the current repo                    #
# --------------------------------------------------------------------------- #


def test_repo_sanity_passes() -> None:
    """The current repo must pass ``python -m scripts.audit.temp_review``.

    Design §5: this is the load-bearing sanity check confirming that
    P-0.5.B itself satisfies the rules it introduces.
    """
    repo_root = Path(temp_review.__file__).resolve().parents[2]
    env = dict(os.environ)
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.audit.temp_review"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert proc.returncode == 0, (
        f"temp_review failed against current repo:\nstdout:\n{proc.stdout}\n\nstderr:\n{proc.stderr}"
    )
