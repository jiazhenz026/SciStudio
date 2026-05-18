"""Tests for ``scieasy.qa.governance.monotonic_check`` (TC-1E.3).

Every detector is exercised against a real on-disk git history (built in
a ``tmp_path`` via ``subprocess.run("git ...")``) plus a final
end-to-end roundtrip through the public ``check_monotonic`` entry-point.
The 14-axis enum mapping (:data:`MONOTONIC_AXIS_DIRECTIONS`) is also
asserted to match the §3.4.1 table.
"""

from __future__ import annotations

import io
import json
import subprocess
from collections.abc import Iterator
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from scieasy.qa.governance.monotonic_check import (
    MONOTONIC_AXIS_DIRECTIONS,
    check_monotonic,
    main,
)

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


@pytest.fixture()
def two_ref_repo(tmp_path: Path) -> Iterator[tuple[Path, str, str]]:
    """Repo with two commits — yields (repo_root, base_sha, head_sha)."""
    _git_init(tmp_path)
    # base file
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\n\n[tool.pytest.ini_options]\n'
        'addopts = "--cov-fail-under=70"\ntimeout = 60\n\n'
        '[tool.ruff.lint]\nselect = ["E", "F", "I"]\nignore = []\n\n'
        "[tool.mypy]\nstrict = true\ndisallow_untyped_defs = true\n",
        encoding="utf-8",
    )
    base = _commit(tmp_path, "base")
    yield tmp_path, base, base


# --------------------------------------------------------------------------- #
# Axis-direction table                                                        #
# --------------------------------------------------------------------------- #


def test_monotonic_axis_directions_has_14_entries() -> None:
    """ADR-043 §3.4.1 lists 14 axes; the mapping must cover all of them."""
    assert len(MONOTONIC_AXIS_DIRECTIONS) == 14


@pytest.mark.parametrize("direction", sorted(set(MONOTONIC_AXIS_DIRECTIONS.values())))
def test_monotonic_axis_direction_values_are_canonical(direction: str) -> None:
    assert direction in {
        "increase-is-stricter",
        "decrease-is-stricter",
        "add-is-stricter",
        "remove-is-stricter",
    }


# --------------------------------------------------------------------------- #
# Coverage / pytest-timeout detectors                                         #
# --------------------------------------------------------------------------- #


def test_no_change_returns_zero_loosenings(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\naddopts = "--cov-fail-under=70"\ntimeout = 60\n',
        encoding="utf-8",
    )
    base = _commit(tmp_path, "base")
    (tmp_path / "README.md").write_text("touched\n", encoding="utf-8")
    head = _commit(tmp_path, "no-rule-change")
    result = check_monotonic(base, head, repo_root=tmp_path)
    assert result.loosened == []
    assert result.overall_blocking is False


def test_lowered_coverage_threshold_blocks(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\naddopts = "--cov-fail-under=80"\n',
        encoding="utf-8",
    )
    base = _commit(tmp_path, "base")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\naddopts = "--cov-fail-under=70"\n',
        encoding="utf-8",
    )
    head = _commit(tmp_path, "lower coverage")
    result = check_monotonic(base, head, repo_root=tmp_path)
    axes = {ax.axis for ax in result.loosened}
    assert "coverage-threshold" in axes
    assert result.overall_blocking is True


def test_raised_coverage_threshold_passes(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\naddopts = "--cov-fail-under=70"\n',
        encoding="utf-8",
    )
    base = _commit(tmp_path, "base")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\naddopts = "--cov-fail-under=80"\n',
        encoding="utf-8",
    )
    head = _commit(tmp_path, "raise coverage")
    result = check_monotonic(base, head, repo_root=tmp_path)
    assert all(ax.axis != "coverage-threshold" for ax in result.loosened)


def test_increased_pytest_timeout_blocks(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\ntimeout = 60\n", encoding="utf-8")
    base = _commit(tmp_path, "base")
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\ntimeout = 120\n", encoding="utf-8")
    head = _commit(tmp_path, "raise timeout")
    result = check_monotonic(base, head, repo_root=tmp_path)
    assert any(ax.axis == "pytest-timeout" for ax in result.loosened)


def test_lowered_pytest_timeout_passes(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\ntimeout = 60\n", encoding="utf-8")
    base = _commit(tmp_path, "base")
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\ntimeout = 30\n", encoding="utf-8")
    head = _commit(tmp_path, "tighten timeout")
    result = check_monotonic(base, head, repo_root=tmp_path)
    assert all(ax.axis != "pytest-timeout" for ax in result.loosened)


# --------------------------------------------------------------------------- #
# Honeypot canary count                                                       #
# --------------------------------------------------------------------------- #


def test_dropped_honeypot_canary_blocks(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / ".governance-paths.yaml").write_text(
        'version: 1\ngovernance_paths: ["x"]\n'
        'honeypot_canaries:\n  - path: "a"\n    marker_pattern: "x"\n'
        '  - path: "b"\n    marker_pattern: "y"\n',
        encoding="utf-8",
    )
    base = _commit(tmp_path, "base")
    (tmp_path / ".governance-paths.yaml").write_text(
        'version: 1\ngovernance_paths: ["x"]\nhoneypot_canaries:\n  - path: "a"\n    marker_pattern: "x"\n',
        encoding="utf-8",
    )
    head = _commit(tmp_path, "drop canary")
    result = check_monotonic(base, head, repo_root=tmp_path)
    assert any(ax.axis == "honeypot-canary-count" for ax in result.loosened)


def test_added_honeypot_canary_passes(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / ".governance-paths.yaml").write_text(
        'version: 1\ngovernance_paths: ["x"]\nhoneypot_canaries:\n  - path: "a"\n    marker_pattern: "x"\n',
        encoding="utf-8",
    )
    base = _commit(tmp_path, "base")
    (tmp_path / ".governance-paths.yaml").write_text(
        'version: 1\ngovernance_paths: ["x"]\n'
        'honeypot_canaries:\n  - path: "a"\n    marker_pattern: "x"\n'
        '  - path: "b"\n    marker_pattern: "y"\n',
        encoding="utf-8",
    )
    head = _commit(tmp_path, "add canary")
    result = check_monotonic(base, head, repo_root=tmp_path)
    assert all(ax.axis != "honeypot-canary-count" for ax in result.loosened)


# --------------------------------------------------------------------------- #
# Skill list / pre-commit hooks / ruff / mypy / CI gates / governance paths   #
# --------------------------------------------------------------------------- #


def test_removed_skill_list_entry_blocks(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "docs" / "skills").mkdir(parents=True)
    (tmp_path / "docs" / "skills" / "required.yaml").write_text("- a\n- b\n- c\n", encoding="utf-8")
    base = _commit(tmp_path, "base")
    (tmp_path / "docs" / "skills" / "required.yaml").write_text("- a\n- b\n", encoding="utf-8")
    head = _commit(tmp_path, "drop c")
    result = check_monotonic(base, head, repo_root=tmp_path)
    assert any(ax.axis == "required-skill-list" for ax in result.loosened)


def test_removed_precommit_hook_blocks(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / ".pre-commit-config.yaml").write_text(
        "repos:\n  - repo: local\n    hooks:\n      - id: ruff\n      - id: mypy\n",
        encoding="utf-8",
    )
    base = _commit(tmp_path, "base")
    (tmp_path / ".pre-commit-config.yaml").write_text(
        "repos:\n  - repo: local\n    hooks:\n      - id: ruff\n",
        encoding="utf-8",
    )
    head = _commit(tmp_path, "drop mypy hook")
    result = check_monotonic(base, head, repo_root=tmp_path)
    axes = {ax.axis for ax in result.loosened}
    assert "pre-commit-hooks" in axes


def test_removed_ruff_select_blocks(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.ruff.lint]\nselect = ["E", "F", "I"]\nignore = []\n',
        encoding="utf-8",
    )
    base = _commit(tmp_path, "base")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.ruff.lint]\nselect = ["E", "F"]\nignore = []\n',
        encoding="utf-8",
    )
    head = _commit(tmp_path, "drop I")
    result = check_monotonic(base, head, repo_root=tmp_path)
    assert any(ax.axis == "ruff-rule-selection" for ax in result.loosened)


def test_added_ruff_ignore_blocks(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.ruff.lint]\nselect = ["E", "F"]\nignore = []\n',
        encoding="utf-8",
    )
    base = _commit(tmp_path, "base")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.ruff.lint]\nselect = ["E", "F"]\nignore = ["E501"]\n',
        encoding="utf-8",
    )
    head = _commit(tmp_path, "ignore E501")
    result = check_monotonic(base, head, repo_root=tmp_path)
    assert any(ax.axis == "ruff-rule-selection" and "E501" in ax.after_value for ax in result.loosened)


def test_disabled_mypy_strict_flag_blocks(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        "[tool.mypy]\nstrict = true\ndisallow_untyped_defs = true\n",
        encoding="utf-8",
    )
    base = _commit(tmp_path, "base")
    (tmp_path / "pyproject.toml").write_text(
        "[tool.mypy]\nstrict = true\ndisallow_untyped_defs = false\n",
        encoding="utf-8",
    )
    head = _commit(tmp_path, "loosen mypy")
    result = check_monotonic(base, head, repo_root=tmp_path)
    assert any(ax.axis == "mypy-strictness-flags" for ax in result.loosened)


def test_removed_ci_job_blocks(tmp_path: Path) -> None:
    _git_init(tmp_path)
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(
        "name: ci\non: push\njobs:\n  lint:\n    runs-on: ubuntu-latest\n"
        "  type:\n    runs-on: ubuntu-latest\n  test:\n    runs-on: ubuntu-latest\n",
        encoding="utf-8",
    )
    base = _commit(tmp_path, "base")
    (workflows / "ci.yml").write_text(
        "name: ci\non: push\njobs:\n  lint:\n    runs-on: ubuntu-latest\n  test:\n    runs-on: ubuntu-latest\n",
        encoding="utf-8",
    )
    head = _commit(tmp_path, "drop type job")
    result = check_monotonic(base, head, repo_root=tmp_path)
    assert any(ax.axis == "required-ci-gates" for ax in result.loosened)


def test_shrunk_governance_paths_blocks(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / ".governance-paths.yaml").write_text(
        'version: 1\ngovernance_paths:\n  - "docs/adr/**"\n  - "CLAUDE.md"\n  - "AGENTS.md"\nhoneypot_canaries: []\n',
        encoding="utf-8",
    )
    base = _commit(tmp_path, "base")
    (tmp_path / ".governance-paths.yaml").write_text(
        'version: 1\ngovernance_paths:\n  - "docs/adr/**"\n  - "CLAUDE.md"\nhoneypot_canaries: []\n',
        encoding="utf-8",
    )
    head = _commit(tmp_path, "drop AGENTS.md from registry")
    result = check_monotonic(base, head, repo_root=tmp_path)
    assert any(ax.axis == "agent-editable-false-paths" for ax in result.loosened)


# --------------------------------------------------------------------------- #
# Loosening trailer / blocking semantics                                      #
# --------------------------------------------------------------------------- #


def test_loosening_with_trailer_and_reason_is_non_blocking(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\naddopts = "--cov-fail-under=80"\n',
        encoding="utf-8",
    )
    base = _commit(tmp_path, "base")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\naddopts = "--cov-fail-under=70"\n',
        encoding="utf-8",
    )
    head = _commit(
        tmp_path,
        "feat: temporarily lower coverage\n\n"
        "Loosening-Approved: @tier2\n"
        "Loosening-Reason: Phase 1A scaffolding period\n",
    )
    result = check_monotonic(base, head, repo_root=tmp_path)
    assert result.has_loosening_approved_trailer is True
    assert result.approver_handle == "@tier2"
    assert result.overall_blocking is False


def test_loosening_with_trailer_but_no_reason_still_blocks(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\naddopts = "--cov-fail-under=80"\n',
        encoding="utf-8",
    )
    base = _commit(tmp_path, "base")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\naddopts = "--cov-fail-under=70"\n',
        encoding="utf-8",
    )
    head = _commit(tmp_path, "feat: lower coverage\n\nLoosening-Approved: @tier2\n")
    result = check_monotonic(base, head, repo_root=tmp_path)
    assert result.overall_blocking is True


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #


def test_main_emits_json_and_returns_zero_on_clean(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "x").write_text("1", encoding="utf-8")
    base = _commit(tmp_path, "base")
    (tmp_path / "y").write_text("2", encoding="utf-8")
    head = _commit(tmp_path, "head")
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["--base", base, "--head", head, "--repo-root", str(tmp_path)])
    assert rc == 0
    payload = json.loads(buf.getvalue())
    assert payload["overall_blocking"] is False


def test_main_returns_one_on_blocking_loosening(tmp_path: Path) -> None:
    _git_init(tmp_path)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\naddopts = "--cov-fail-under=80"\n',
        encoding="utf-8",
    )
    base = _commit(tmp_path, "base")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\naddopts = "--cov-fail-under=70"\n',
        encoding="utf-8",
    )
    head = _commit(tmp_path, "lower")
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["--base", base, "--head", head, "--repo-root", str(tmp_path)])
    assert rc == 1
    payload = json.loads(buf.getvalue())
    assert payload["overall_blocking"] is True
    assert payload["loosened"]
