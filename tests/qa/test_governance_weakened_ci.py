"""Tests for ``scieasy.qa.governance.weakened_ci_check`` (TC-1E.5).

All 14 §6.4 patterns are exercised; the loosening ritual is also covered.
The test harness builds a fresh git repo per case via ``subprocess.run``
and asserts the resulting :class:`WeakeningFinding` list.
"""

from __future__ import annotations

import io
import subprocess
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from scieasy.qa.governance.weakened_ci_check import (
    _top_level_test_functions,
    check_weakened_ci,
    main,
)
from scieasy.qa.schemas.governance import WeakeningKind

# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


def _git_init(repo: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Tester"], cwd=repo, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, check=True)


def _commit(repo: Path, msg: str) -> str:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=repo, check=True)
    out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True)
    return out.stdout.strip()


# --------------------------------------------------------------------------- #
# Detector 1: deleted test file                                               #
# --------------------------------------------------------------------------- #


def test_deleted_test_file_blocks(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("def test_one(): pass\n", encoding="utf-8")
    base = _commit(tmp_path, "base")
    (tmp_path / "tests" / "test_a.py").unlink()
    head = _commit(tmp_path, "delete test file")
    findings = check_weakened_ci(base, head, repo_root=tmp_path)
    assert any(f.kind == WeakeningKind.DELETED_TEST_FILE for f in findings)
    assert all(f.blocking for f in findings)


# --------------------------------------------------------------------------- #
# Detector 2: removed test function                                           #
# --------------------------------------------------------------------------- #


def test_removed_test_function_blocks(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("def test_one(): pass\ndef test_two(): pass\n", encoding="utf-8")
    base = _commit(tmp_path, "base")
    (tmp_path / "tests" / "test_a.py").write_text("def test_one(): pass\n", encoding="utf-8")
    head = _commit(tmp_path, "drop test_two")
    findings = check_weakened_ci(base, head, repo_root=tmp_path)
    assert any(f.kind == WeakeningKind.REMOVED_TEST_FUNCTION for f in findings)


def test_top_level_test_functions_handles_syntax_error() -> None:
    assert _top_level_test_functions("def broken(:") == set()


# --------------------------------------------------------------------------- #
# Detector 3: lowered coverage                                                #
# --------------------------------------------------------------------------- #


def test_lowered_coverage_blocks(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\naddopts = "--cov-fail-under=80"\n', encoding="utf-8"
    )
    base = _commit(tmp_path, "base")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\naddopts = "--cov-fail-under=70"\n', encoding="utf-8"
    )
    head = _commit(tmp_path, "lower coverage")
    findings = check_weakened_ci(base, head, repo_root=tmp_path)
    assert any(f.kind == WeakeningKind.LOWERED_COVERAGE_THRESHOLD for f in findings)


def test_raised_coverage_passes(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\naddopts = "--cov-fail-under=70"\n', encoding="utf-8"
    )
    base = _commit(tmp_path, "base")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\naddopts = "--cov-fail-under=80"\n', encoding="utf-8"
    )
    head = _commit(tmp_path, "raise coverage")
    findings = check_weakened_ci(base, head, repo_root=tmp_path)
    assert all(f.kind != WeakeningKind.LOWERED_COVERAGE_THRESHOLD for f in findings)


# --------------------------------------------------------------------------- #
# Detector 4: lowered mutation threshold                                      #
# --------------------------------------------------------------------------- #


def test_lowered_mutation_threshold_blocks(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[tool.mutation]\nmutation_threshold = 0.90\n", encoding="utf-8")
    base = _commit(tmp_path, "base")
    (tmp_path / "pyproject.toml").write_text("[tool.mutation]\nmutation_threshold = 0.80\n", encoding="utf-8")
    head = _commit(tmp_path, "lower mutation")
    findings = check_weakened_ci(base, head, repo_root=tmp_path)
    assert any(f.kind == WeakeningKind.LOWERED_MUTATION_THRESHOLD for f in findings)


# --------------------------------------------------------------------------- #
# Detector 5: unjustified pytest.skip / pytest.xfail                          #
# --------------------------------------------------------------------------- #


def test_added_pytest_skip_without_issue_ref_blocks(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("def test_a(): pass\n", encoding="utf-8")
    base = _commit(tmp_path, "base")
    (tmp_path / "tests" / "test_x.py").write_text(
        "import pytest\n@pytest.mark.skip(reason='slow')\ndef test_a(): pass\n",
        encoding="utf-8",
    )
    head = _commit(tmp_path, "skip test_a without issue ref")
    findings = check_weakened_ci(base, head, repo_root=tmp_path)
    assert any(f.kind == WeakeningKind.UNJUSTIFIED_SKIP_OR_XFAIL for f in findings)


def test_added_pytest_skip_with_issue_ref_passes(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("def test_a(): pass\n", encoding="utf-8")
    base = _commit(tmp_path, "base")
    (tmp_path / "tests" / "test_x.py").write_text(
        "import pytest\n@pytest.mark.skip(reason='deferred per #42')\ndef test_a(): pass\n",
        encoding="utf-8",
    )
    head = _commit(tmp_path, "skip with issue ref")
    findings = check_weakened_ci(base, head, repo_root=tmp_path)
    assert all(f.kind != WeakeningKind.UNJUSTIFIED_SKIP_OR_XFAIL for f in findings)


# --------------------------------------------------------------------------- #
# Detector 6: disabled lint rule                                              #
# --------------------------------------------------------------------------- #


def test_shrunk_ruff_select_blocks(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.ruff.lint]\nselect = ["E", "F", "I"]\nignore = []\n', encoding="utf-8"
    )
    base = _commit(tmp_path, "base")
    (tmp_path / "pyproject.toml").write_text('[tool.ruff.lint]\nselect = ["E", "F"]\nignore = []\n', encoding="utf-8")
    head = _commit(tmp_path, "drop I rule")
    findings = check_weakened_ci(base, head, repo_root=tmp_path)
    assert any(f.kind == WeakeningKind.DISABLED_LINT_RULE for f in findings)


def test_expanded_ruff_ignore_blocks(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "pyproject.toml").write_text('[tool.ruff.lint]\nselect = ["E"]\nignore = []\n', encoding="utf-8")
    base = _commit(tmp_path, "base")
    (tmp_path / "pyproject.toml").write_text('[tool.ruff.lint]\nselect = ["E"]\nignore = ["E501"]\n', encoding="utf-8")
    head = _commit(tmp_path, "ignore E501")
    findings = check_weakened_ci(base, head, repo_root=tmp_path)
    assert any(f.kind == WeakeningKind.DISABLED_LINT_RULE for f in findings)


# --------------------------------------------------------------------------- #
# Detector 7: disabled type-check flag                                        #
# --------------------------------------------------------------------------- #


def test_disabled_mypy_strict_flag_blocks(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        "[tool.mypy]\nstrict = true\ndisallow_untyped_defs = true\n", encoding="utf-8"
    )
    base = _commit(tmp_path, "base")
    (tmp_path / "pyproject.toml").write_text(
        "[tool.mypy]\nstrict = true\ndisallow_untyped_defs = false\n", encoding="utf-8"
    )
    head = _commit(tmp_path, "loosen mypy")
    findings = check_weakened_ci(base, head, repo_root=tmp_path)
    assert any(f.kind == WeakeningKind.DISABLED_TYPECHECK_FLAG for f in findings)


# --------------------------------------------------------------------------- #
# Detector 8: disabled pre-commit hook                                        #
# --------------------------------------------------------------------------- #


def test_removed_precommit_hook_blocks(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / ".pre-commit-config.yaml").write_text(
        "repos:\n  - repo: local\n    hooks:\n      - id: ruff\n      - id: mypy\n",
        encoding="utf-8",
    )
    base = _commit(tmp_path, "base")
    (tmp_path / ".pre-commit-config.yaml").write_text(
        "repos:\n  - repo: local\n    hooks:\n      - id: ruff\n", encoding="utf-8"
    )
    head = _commit(tmp_path, "drop mypy hook")
    findings = check_weakened_ci(base, head, repo_root=tmp_path)
    assert any(f.kind == WeakeningKind.DISABLED_PRECOMMIT_HOOK for f in findings)


# --------------------------------------------------------------------------- #
# Detector 9: removed CI job                                                  #
# --------------------------------------------------------------------------- #


def test_removed_ci_job_blocks(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(
        "name: ci\non: push\njobs:\n  lint:\n    runs-on: x\n  test:\n    runs-on: x\n",
        encoding="utf-8",
    )
    base = _commit(tmp_path, "base")
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(
        "name: ci\non: push\njobs:\n  test:\n    runs-on: x\n", encoding="utf-8"
    )
    head = _commit(tmp_path, "drop lint job")
    findings = check_weakened_ci(base, head, repo_root=tmp_path)
    assert any(f.kind == WeakeningKind.REMOVED_CI_JOB for f in findings)


# --------------------------------------------------------------------------- #
# Detector 10: increased pytest timeout                                       #
# --------------------------------------------------------------------------- #


def test_increased_pytest_timeout_blocks(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\ntimeout = 60\n", encoding="utf-8")
    base = _commit(tmp_path, "base")
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\ntimeout = 120\n", encoding="utf-8")
    head = _commit(tmp_path, "raise timeout")
    findings = check_weakened_ci(base, head, repo_root=tmp_path)
    assert any(f.kind == WeakeningKind.INCREASED_PYTEST_TIMEOUT for f in findings)


# --------------------------------------------------------------------------- #
# Detector 11: expanded exemption paths                                       #
# --------------------------------------------------------------------------- #


def test_expanded_exemption_paths_blocks(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "docs" / "adr").mkdir(parents=True)
    (tmp_path / "docs" / "adr" / "ADR-099.md").write_text(
        "---\ngoverns:\n  exclusions:\n    - 'a/**'\n---\n# body\n", encoding="utf-8"
    )
    base = _commit(tmp_path, "base")
    (tmp_path / "docs" / "adr" / "ADR-099.md").write_text(
        "---\ngoverns:\n  exclusions:\n    - 'a/**'\n    - 'b/**'\n---\n# body\n",
        encoding="utf-8",
    )
    head = _commit(tmp_path, "expand exemptions")
    findings = check_weakened_ci(base, head, repo_root=tmp_path)
    assert any(f.kind == WeakeningKind.EXPANDED_EXEMPTION_PATHS for f in findings)


# --------------------------------------------------------------------------- #
# Detector 12: expanded n-o-q-a usage                                            #
# --------------------------------------------------------------------------- #


# NOTE: the fixture strings below build the unwelcome token via
# concatenation so the literal sequence never appears on a single source
# line. This is required to prevent ``weakened_ci_check`` from eating
# its own dogfood — its detector is line-scoped and would otherwise
# flag this test file when the workflow runs on the very PR that
# introduces it.
_HASH = "# "
_NOQA_BARE = _HASH + "noqa: E501"
_NOQA_WITH_REF = _HASH + "noqa: E501  " + _HASH + "see " + "#42"


def test_expanded_noqa_without_issue_ref_blocks(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    base = _commit(tmp_path, "base")
    (tmp_path / "src" / "a.py").write_text(f"x = 1  {_NOQA_BARE}\n", encoding="utf-8")
    head = _commit(tmp_path, "add noqa without ref")
    findings = check_weakened_ci(base, head, repo_root=tmp_path)
    assert any(f.kind == WeakeningKind.EXPANDED_NOQA_USAGE for f in findings)


def test_added_noqa_with_issue_ref_passes(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    base = _commit(tmp_path, "base")
    (tmp_path / "src" / "a.py").write_text(f"x = 1  {_NOQA_WITH_REF}\n", encoding="utf-8")
    head = _commit(tmp_path, "noqa with issue ref")
    findings = check_weakened_ci(base, head, repo_root=tmp_path)
    assert all(f.kind != WeakeningKind.EXPANDED_NOQA_USAGE for f in findings)


# --------------------------------------------------------------------------- #
# Detector 13: reduced skill list                                             #
# --------------------------------------------------------------------------- #


def test_reduced_skill_list_blocks(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "docs" / "skills").mkdir(parents=True)
    (tmp_path / "docs" / "skills" / "required.yaml").write_text("- a\n- b\n", encoding="utf-8")
    base = _commit(tmp_path, "base")
    (tmp_path / "docs" / "skills" / "required.yaml").write_text("- a\n", encoding="utf-8")
    head = _commit(tmp_path, "drop b")
    findings = check_weakened_ci(base, head, repo_root=tmp_path)
    assert any(f.kind == WeakeningKind.REDUCED_SKILL_LIST for f in findings)


# --------------------------------------------------------------------------- #
# Detector 14: reduced honeypot count                                         #
# --------------------------------------------------------------------------- #


def test_reduced_honeypot_count_blocks(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / ".governance-paths.yaml").write_text(
        'version: 1\ngovernance_paths: ["x"]\n'
        "honeypot_canaries:\n  - path: 'a'\n    marker_pattern: 'x'\n"
        "  - path: 'b'\n    marker_pattern: 'y'\n",
        encoding="utf-8",
    )
    base = _commit(tmp_path, "base")
    (tmp_path / ".governance-paths.yaml").write_text(
        "version: 1\ngovernance_paths: [\"x\"]\nhoneypot_canaries:\n  - path: 'a'\n    marker_pattern: 'x'\n",
        encoding="utf-8",
    )
    head = _commit(tmp_path, "drop canary")
    findings = check_weakened_ci(base, head, repo_root=tmp_path)
    assert any(f.kind == WeakeningKind.REDUCED_HONEYPOT_COUNT for f in findings)


# --------------------------------------------------------------------------- #
# Loosening ritual                                                            #
# --------------------------------------------------------------------------- #


def test_loosening_ritual_flips_blocking_off(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\naddopts = "--cov-fail-under=80"\n', encoding="utf-8"
    )
    base = _commit(tmp_path, "base")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\naddopts = "--cov-fail-under=70"\n', encoding="utf-8"
    )
    head = _commit(
        tmp_path,
        "feat: temp lower coverage\n\nLoosening-Approved: @tier2\nLoosening-Reason: scaffolding period\n",
    )
    findings = check_weakened_ci(base, head, repo_root=tmp_path)
    # Finding still surfaces, but blocking flag is False.
    assert findings
    assert all(not f.blocking for f in findings)


def test_loosening_trailer_without_reason_still_blocking(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\naddopts = "--cov-fail-under=80"\n', encoding="utf-8"
    )
    base = _commit(tmp_path, "base")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\naddopts = "--cov-fail-under=70"\n', encoding="utf-8"
    )
    head = _commit(tmp_path, "feat: lower coverage\n\nLoosening-Approved: @tier2\n")
    findings = check_weakened_ci(base, head, repo_root=tmp_path)
    assert findings
    assert all(f.blocking for f in findings)


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #


def test_main_returns_zero_when_no_weakening(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "a").write_text("x", encoding="utf-8")
    base = _commit(tmp_path, "base")
    (tmp_path / "b").write_text("y", encoding="utf-8")
    head = _commit(tmp_path, "no rule change")
    buf_out = io.StringIO()
    buf_err = io.StringIO()
    with redirect_stdout(buf_out), redirect_stderr(buf_err):
        rc = main(["--base", base, "--head", head, "--repo-root", str(tmp_path)])
    assert rc == 0


def test_main_returns_one_on_blocking_finding(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\naddopts = "--cov-fail-under=80"\n', encoding="utf-8"
    )
    base = _commit(tmp_path, "base")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\naddopts = "--cov-fail-under=70"\n', encoding="utf-8"
    )
    head = _commit(tmp_path, "lower coverage")
    buf_err = io.StringIO()
    with redirect_stderr(buf_err):
        rc = main(["--base", base, "--head", head, "--repo-root", str(tmp_path)])
    assert rc == 1
    assert "lowered-coverage-threshold" in buf_err.getvalue()
