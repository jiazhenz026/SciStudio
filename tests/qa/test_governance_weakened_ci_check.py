"""Tests for ``scieasy.qa.governance.weakened_ci_check`` (TC-1E.5).

Every weakening pattern is exercised against a real on-disk git history
(built in a ``tmp_path`` via ``subprocess.run("git ...")``). The
:class:`scieasy.qa.schemas.governance.WeakeningKind` enum is also
asserted to match the §6.4 14-row table.
"""

from __future__ import annotations

import io
import json
import subprocess
from collections.abc import Iterator
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from scieasy.qa.governance.weakened_ci_check import (
    main,
    verify_no_weakening,
)
from scieasy.qa.schemas.governance import WeakeningKind

# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)
    return out.stdout


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


def _delete(repo: Path, rel: str) -> None:
    (repo / rel).unlink()


@pytest.fixture
def repo(tmp_path: Path) -> Iterator[Path]:
    _git_init(tmp_path)
    # Seed a baseline commit on main with the canonical configs in place.
    _write(
        tmp_path,
        "pyproject.toml",
        """[tool.pytest.ini_options]
addopts = "--cov-fail-under=85"
timeout = 60

[tool.ruff.lint]
select = ["E", "F", "I"]
ignore = []

[tool.mypy]
strict = true
disallow_untyped_defs = true
""",
    )
    _write(
        tmp_path,
        ".pre-commit-config.yaml",
        """repos:
  - repo: local
    hooks:
      - id: ruff
        name: ruff
      - id: black
        name: black
""",
    )
    _write(
        tmp_path,
        ".github/workflows/ci.yml",
        """name: ci
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
  lint:
    runs-on: ubuntu-latest
""",
    )
    _write(
        tmp_path,
        ".governance-paths.yaml",
        """version: 1
governance_paths:
  - "docs/adr/**"
honeypot_canaries:
  - path: "AGENTS.md"
    marker_pattern: "# CANARY-DO-NOT-MODIFY: BASE"
  - path: "CLAUDE.md"
    marker_pattern: "# CANARY-DO-NOT-MODIFY: BASE2"
exclusions:
  - "tests/fixtures/**"
""",
    )
    _write(
        tmp_path,
        "docs/skills/required.yaml",
        """skills:
  - simplify
  - update-config
""",
    )
    _write(
        tmp_path, "tests/test_existing.py", "def test_alpha():\n    assert True\n\ndef test_beta():\n    assert True\n"
    )
    _commit(tmp_path, "init baseline")
    # Branch off main so subsequent commits land on a feature branch
    # and `main..HEAD` (CLI default) sees them.
    subprocess.run(["git", "checkout", "-q", "-b", "feature"], cwd=tmp_path, check=True)
    yield tmp_path


def _diff_to_findings(repo: Path) -> list:
    return verify_no_weakening("main", "HEAD", repo_root=repo)


# --------------------------------------------------------------------------- #
# Enum table coherence                                                        #
# --------------------------------------------------------------------------- #


def test_weakening_kind_enum_has_14_values():
    assert len(list(WeakeningKind)) == 14


# --------------------------------------------------------------------------- #
# Pattern 1 — deleted-test-file                                               #
# --------------------------------------------------------------------------- #


def test_deleted_test_file_blocks(repo: Path):
    _delete(repo, "tests/test_existing.py")
    _commit(repo, "delete test")
    findings = _diff_to_findings(repo)
    kinds = {f.kind for f in findings}
    assert WeakeningKind.DELETED_TEST_FILE in kinds


def test_deleted_non_test_file_ignored(repo: Path):
    _write(repo, "docs/random.md", "x")
    _commit(repo, "add doc")
    _delete(repo, "docs/random.md")
    _commit(repo, "delete doc")
    findings = _diff_to_findings(repo)
    assert WeakeningKind.DELETED_TEST_FILE not in {f.kind for f in findings}


# --------------------------------------------------------------------------- #
# Pattern 2 — removed-test-function                                           #
# --------------------------------------------------------------------------- #


def test_removed_test_function_blocks(repo: Path):
    _write(repo, "tests/test_existing.py", "def test_alpha():\n    assert True\n")
    _commit(repo, "drop test_beta")
    findings = _diff_to_findings(repo)
    removed = [f for f in findings if f.kind == WeakeningKind.REMOVED_TEST_FUNCTION]
    assert removed
    assert any("test_beta" in f.before_value for f in removed)


def test_added_test_function_not_a_weakening(repo: Path):
    _write(
        repo,
        "tests/test_existing.py",
        "def test_alpha():\n    assert True\n\ndef test_beta():\n    assert True\n\ndef test_gamma():\n    assert True\n",
    )
    _commit(repo, "add test")
    findings = _diff_to_findings(repo)
    assert WeakeningKind.REMOVED_TEST_FUNCTION not in {f.kind for f in findings}


# --------------------------------------------------------------------------- #
# Pattern 3 — lowered-coverage-threshold                                      #
# --------------------------------------------------------------------------- #


def test_lowered_coverage_threshold_blocks(repo: Path):
    pp = (repo / "pyproject.toml").read_text(encoding="utf-8")
    (repo / "pyproject.toml").write_text(pp.replace("--cov-fail-under=85", "--cov-fail-under=70"), encoding="utf-8")
    _commit(repo, "lower coverage")
    findings = _diff_to_findings(repo)
    assert WeakeningKind.LOWERED_COVERAGE_THRESHOLD in {f.kind for f in findings}


def test_raised_coverage_threshold_not_blocking(repo: Path):
    pp = (repo / "pyproject.toml").read_text(encoding="utf-8")
    (repo / "pyproject.toml").write_text(pp.replace("--cov-fail-under=85", "--cov-fail-under=90"), encoding="utf-8")
    _commit(repo, "raise coverage")
    findings = _diff_to_findings(repo)
    assert WeakeningKind.LOWERED_COVERAGE_THRESHOLD not in {f.kind for f in findings}


# --------------------------------------------------------------------------- #
# Pattern 4 — lowered-mutation-threshold                                      #
# --------------------------------------------------------------------------- #


def test_lowered_mutation_threshold_blocks(repo: Path):
    # Add the mutmut config to main first so the diff sees a lowering,
    # not a freshly-added key.
    subprocess.run(["git", "checkout", "-q", "main"], cwd=repo, check=True)
    pp = (repo / "pyproject.toml").read_text(encoding="utf-8")
    (repo / "pyproject.toml").write_text(pp + "\n[tool.mutmut]\nminimum-score = 90\n", encoding="utf-8")
    _commit(repo, "set mutation 90")
    subprocess.run(["git", "checkout", "-q", "feature"], cwd=repo, check=True)
    subprocess.run(["git", "merge", "-q", "--no-edit", "main"], cwd=repo, check=True)
    # Now lower the threshold on the feature branch.
    pp2 = (repo / "pyproject.toml").read_text(encoding="utf-8")
    (repo / "pyproject.toml").write_text(pp2.replace("minimum-score = 90", "minimum-score = 60"), encoding="utf-8")
    _commit(repo, "lower mutation")
    findings = verify_no_weakening("main", "HEAD", repo_root=repo)
    assert WeakeningKind.LOWERED_MUTATION_THRESHOLD in {f.kind for f in findings}


# --------------------------------------------------------------------------- #
# Pattern 5 — unjustified-skip-or-xfail                                       #
# --------------------------------------------------------------------------- #


def test_unjustified_skip_blocks(repo: Path):
    _write(
        repo,
        "tests/test_existing.py",
        "import pytest\n\n@pytest.mark.skip\ndef test_alpha():\n    assert True\n\ndef test_beta():\n    assert True\n",
    )
    _commit(repo, "skip test_alpha")
    findings = _diff_to_findings(repo)
    assert WeakeningKind.UNJUSTIFIED_SKIP_OR_XFAIL in {f.kind for f in findings}


def test_skip_with_issue_ref_allowed(repo: Path):
    _write(
        repo,
        "tests/test_existing.py",
        'import pytest\n\n@pytest.mark.skip(reason="see #1234")\ndef test_alpha():\n    assert True\n\ndef test_beta():\n    assert True\n',
    )
    _commit(repo, "skip with issue")
    findings = _diff_to_findings(repo)
    assert WeakeningKind.UNJUSTIFIED_SKIP_OR_XFAIL not in {f.kind for f in findings}


def test_unjustified_xfail_blocks(repo: Path):
    _write(
        repo,
        "tests/test_existing.py",
        'import pytest\n\n@pytest.mark.xfail(reason="just because")\ndef test_alpha():\n    assert True\n\ndef test_beta():\n    assert True\n',
    )
    _commit(repo, "xfail")
    findings = _diff_to_findings(repo)
    assert WeakeningKind.UNJUSTIFIED_SKIP_OR_XFAIL in {f.kind for f in findings}


# --------------------------------------------------------------------------- #
# Pattern 6 — disabled-lint-rule                                              #
# --------------------------------------------------------------------------- #


def test_lint_select_shrink_blocks(repo: Path):
    pp = (repo / "pyproject.toml").read_text(encoding="utf-8")
    (repo / "pyproject.toml").write_text(
        pp.replace('select = ["E", "F", "I"]', 'select = ["E", "F"]'), encoding="utf-8"
    )
    _commit(repo, "drop ruff I")
    findings = _diff_to_findings(repo)
    assert WeakeningKind.DISABLED_LINT_RULE in {f.kind for f in findings}


def test_lint_ignore_grow_blocks(repo: Path):
    pp = (repo / "pyproject.toml").read_text(encoding="utf-8")
    (repo / "pyproject.toml").write_text(pp.replace("ignore = []", 'ignore = ["E501"]'), encoding="utf-8")
    _commit(repo, "add ruff ignore")
    findings = _diff_to_findings(repo)
    assert WeakeningKind.DISABLED_LINT_RULE in {f.kind for f in findings}


# --------------------------------------------------------------------------- #
# Pattern 7 — disabled-typecheck-flag                                         #
# --------------------------------------------------------------------------- #


def test_strict_flag_flip_blocks(repo: Path):
    pp = (repo / "pyproject.toml").read_text(encoding="utf-8")
    (repo / "pyproject.toml").write_text(pp.replace("strict = true", "strict = false"), encoding="utf-8")
    _commit(repo, "disable strict")
    findings = _diff_to_findings(repo)
    assert WeakeningKind.DISABLED_TYPECHECK_FLAG in {f.kind for f in findings}


# --------------------------------------------------------------------------- #
# Pattern 8 — disabled-precommit-hook                                         #
# --------------------------------------------------------------------------- #


def test_removed_precommit_hook_blocks(repo: Path):
    pp = (repo / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    (repo / ".pre-commit-config.yaml").write_text(
        pp.replace("      - id: black\n        name: black\n", ""), encoding="utf-8"
    )
    _commit(repo, "remove black hook")
    findings = _diff_to_findings(repo)
    assert WeakeningKind.DISABLED_PRECOMMIT_HOOK in {f.kind for f in findings}


# --------------------------------------------------------------------------- #
# Pattern 9 — removed-ci-job                                                  #
# --------------------------------------------------------------------------- #


def test_removed_ci_job_blocks(repo: Path):
    wf = (repo / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    (repo / ".github/workflows/ci.yml").write_text(
        wf.replace("  lint:\n    runs-on: ubuntu-latest\n", ""), encoding="utf-8"
    )
    _commit(repo, "drop lint job")
    findings = _diff_to_findings(repo)
    assert WeakeningKind.REMOVED_CI_JOB in {f.kind for f in findings}


# --------------------------------------------------------------------------- #
# Pattern 10 — increased-pytest-timeout                                       #
# --------------------------------------------------------------------------- #


def test_increased_pytest_timeout_blocks(repo: Path):
    pp = (repo / "pyproject.toml").read_text(encoding="utf-8")
    (repo / "pyproject.toml").write_text(pp.replace("timeout = 60", "timeout = 300"), encoding="utf-8")
    _commit(repo, "raise timeout")
    findings = _diff_to_findings(repo)
    assert WeakeningKind.INCREASED_PYTEST_TIMEOUT in {f.kind for f in findings}


# --------------------------------------------------------------------------- #
# Pattern 11 — expanded-exemption-paths                                       #
# --------------------------------------------------------------------------- #


def test_expanded_exemption_paths_blocks(repo: Path):
    gp = (repo / ".governance-paths.yaml").read_text(encoding="utf-8")
    (repo / ".governance-paths.yaml").write_text(
        gp.replace('  - "tests/fixtures/**"\n', '  - "tests/fixtures/**"\n  - "src/legacy/**"\n'),
        encoding="utf-8",
    )
    _commit(repo, "grow exclusions")
    findings = _diff_to_findings(repo)
    assert WeakeningKind.EXPANDED_EXEMPTION_PATHS in {f.kind for f in findings}


# --------------------------------------------------------------------------- #
# Pattern 12 — expanded-noqa-usage                                            #
# --------------------------------------------------------------------------- #


def test_added_noqa_without_issue_ref_blocks(repo: Path):
    _write(repo, "src/example.py", "x = 1\n")
    _commit(repo, "add module")
    _write(repo, "src/example.py", "x = 1  # noqa: E501\n")
    _commit(repo, "add noqa")
    findings = _diff_to_findings(repo)
    assert WeakeningKind.EXPANDED_NOQA_USAGE in {f.kind for f in findings}


def test_added_noqa_with_issue_ref_allowed(repo: Path):
    _write(repo, "src/example.py", "x = 1\n")
    _commit(repo, "add module")
    _write(repo, "src/example.py", "x = 1  # noqa: E501 - tracked in #4242\n")
    _commit(repo, "add noqa with ref")
    findings = _diff_to_findings(repo)
    assert WeakeningKind.EXPANDED_NOQA_USAGE not in {f.kind for f in findings}


# --------------------------------------------------------------------------- #
# Pattern 13 — reduced-skill-list                                             #
# --------------------------------------------------------------------------- #


def test_reduced_skill_list_blocks(repo: Path):
    (repo / "docs/skills/required.yaml").write_text("skills:\n  - simplify\n", encoding="utf-8")
    _commit(repo, "drop update-config")
    findings = _diff_to_findings(repo)
    assert WeakeningKind.REDUCED_SKILL_LIST in {f.kind for f in findings}


# --------------------------------------------------------------------------- #
# Pattern 14 — reduced-honeypot-count                                         #
# --------------------------------------------------------------------------- #


def test_reduced_honeypot_count_blocks(repo: Path):
    gp = (repo / ".governance-paths.yaml").read_text(encoding="utf-8")
    (repo / ".governance-paths.yaml").write_text(
        gp.replace(
            '  - path: "CLAUDE.md"\n    marker_pattern: "# CANARY-DO-NOT-MODIFY: BASE2"\n',
            "",
        ),
        encoding="utf-8",
    )
    _commit(repo, "drop honeypot canary")
    findings = _diff_to_findings(repo)
    assert WeakeningKind.REDUCED_HONEYPOT_COUNT in {f.kind for f in findings}


# --------------------------------------------------------------------------- #
# Approval ritual                                                             #
# --------------------------------------------------------------------------- #


def test_loosening_approved_trailer_marks_findings_non_blocking(repo: Path):
    pp = (repo / "pyproject.toml").read_text(encoding="utf-8")
    (repo / "pyproject.toml").write_text(pp.replace("--cov-fail-under=85", "--cov-fail-under=70"), encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "commit",
            "-q",
            "-m",
            "lower coverage\n\nLoosening-Approved: @jiazhenz026\nLoosening-Reason: migrating to mutmut\n",
        ],
        cwd=repo,
        check=True,
    )
    findings = _diff_to_findings(repo)
    cov_findings = [f for f in findings if f.kind == WeakeningKind.LOWERED_COVERAGE_THRESHOLD]
    assert cov_findings
    assert all(f.has_loosening_approval is True for f in cov_findings)
    assert all(f.blocking is False for f in cov_findings)


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #


def test_cli_exit_0_when_no_weakening(repo: Path):
    # No diff at all.
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["--base", "main", "--head", "HEAD", "--repo-root", str(repo)])
    assert rc == 0


def test_cli_exit_1_on_blocking_weakening(repo: Path):
    pp = (repo / "pyproject.toml").read_text(encoding="utf-8")
    (repo / "pyproject.toml").write_text(pp.replace("--cov-fail-under=85", "--cov-fail-under=70"), encoding="utf-8")
    _commit(repo, "lower coverage")
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["--base", "main", "--head", "HEAD", "--repo-root", str(repo)])
    assert rc == 1
    payload = json.loads(buf.getvalue())
    assert payload["blocking"] is True
    assert any(f["kind"] == "lowered-coverage-threshold" for f in payload["findings"])


def test_cli_exit_0_when_only_approved_loosening(repo: Path):
    pp = (repo / "pyproject.toml").read_text(encoding="utf-8")
    (repo / "pyproject.toml").write_text(pp.replace("--cov-fail-under=85", "--cov-fail-under=70"), encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "commit",
            "-q",
            "-m",
            "lower coverage\n\nLoosening-Approved: @jiazhenz026\n",
        ],
        cwd=repo,
        check=True,
    )
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["--base", "main", "--head", "HEAD", "--repo-root", str(repo)])
    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["blocking"] is False
    assert payload["findings"]


# --------------------------------------------------------------------------- #
# Edge cases + additional coverage                                            #
# --------------------------------------------------------------------------- #


def test_verify_no_weakening_returns_empty_on_clean_repo(repo: Path):
    findings = verify_no_weakening("main", "HEAD", repo_root=repo)
    assert findings == []


def test_syntax_error_in_test_file_does_not_crash(repo: Path):
    # Removing test_beta + introducing a syntax error in a follow-up commit
    # must not raise; the detector should treat unparseable files as
    # having no tests.
    _write(repo, "tests/test_existing.py", "def test_alpha(:\n    pass\n")
    _commit(repo, "introduce syntax error")
    findings = _diff_to_findings(repo)
    # Either we get a removed-test-function (test_beta dropped) or no
    # finding — both are acceptable; the key invariant is no exception.
    assert isinstance(findings, list)


def test_classbased_test_method_removal(repo: Path):
    _write(
        repo,
        "tests/test_existing.py",
        "class TestCase:\n    def test_a(self):\n        pass\n    def test_b(self):\n        pass\n",
    )
    _commit(repo, "switch to class style")
    # Now drop test_b
    _write(
        repo,
        "tests/test_existing.py",
        "class TestCase:\n    def test_a(self):\n        pass\n",
    )
    _commit(repo, "drop test_b")
    findings = verify_no_weakening("HEAD~1", "HEAD", repo_root=repo)
    removed = [f for f in findings if f.kind == WeakeningKind.REMOVED_TEST_FUNCTION]
    assert any("test_b" in f.before_value for f in removed)


def test_multiline_ruff_select_shrink(repo: Path):
    multi = """[tool.ruff.lint]
select = [
    "E",
    "F",
    "I",
    "B",
]
ignore = []
"""
    (repo / "pyproject.toml").write_text(multi, encoding="utf-8")
    _commit(repo, "multi-line ruff config")
    multi2 = """[tool.ruff.lint]
select = [
    "E",
    "F",
]
ignore = []
"""
    (repo / "pyproject.toml").write_text(multi2, encoding="utf-8")
    _commit(repo, "shrink multi-line select")
    findings = verify_no_weakening("HEAD~1", "HEAD", repo_root=repo)
    assert WeakeningKind.DISABLED_LINT_RULE in {f.kind for f in findings}


def test_async_test_function_removal(repo: Path):
    _write(
        repo,
        "tests/test_existing.py",
        "async def test_async_a():\n    pass\n\nasync def test_async_b():\n    pass\n",
    )
    _commit(repo, "switch to async tests")
    _write(repo, "tests/test_existing.py", "async def test_async_a():\n    pass\n")
    _commit(repo, "drop async b")
    findings = verify_no_weakening("HEAD~1", "HEAD", repo_root=repo)
    removed = [f for f in findings if f.kind == WeakeningKind.REMOVED_TEST_FUNCTION]
    assert any("test_async_b" in f.before_value for f in removed)


def test_typecheck_severity_downgrade(repo: Path):
    """pyright severity downgrade (\"error\" → \"warning\") flagged."""
    _write(
        repo,
        "pyrightconfig.json",
        '{\n  "reportGeneralTypeIssues": "error"\n}\n',
    )
    _commit(repo, "add pyright")
    _write(
        repo,
        "pyrightconfig.json",
        '{\n  "reportGeneralTypeIssues": "warning"\n}\n',
    )
    _commit(repo, "downgrade pyright")
    findings = verify_no_weakening("HEAD~1", "HEAD", repo_root=repo)
    assert WeakeningKind.DISABLED_TYPECHECK_FLAG in {f.kind for f in findings}


def test_workflow_file_deletion_treated_as_job_removal(repo: Path):
    _delete(repo, ".github/workflows/ci.yml")
    _commit(repo, "delete ci workflow")
    findings = _diff_to_findings(repo)
    removed_jobs = [f for f in findings if f.kind == WeakeningKind.REMOVED_CI_JOB]
    assert removed_jobs
