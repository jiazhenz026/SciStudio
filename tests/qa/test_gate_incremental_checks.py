"""Tests for diff-scoped local gate checks (spec gate-local-incremental-checks).

The contract under test: local `gate_record check` narrows each check to the
observed diff, while `ci.yml` keeps proving the full surface. The properties
that must never break are (a) the local gate never runs the whole Python test
suite: inputs it cannot map to tests are deferred to CI, never widened (#2386),
and (b) diff-scoped evidence never satisfies a CI-mirror obligation.
"""

from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path
from typing import Literal

import pytest

from scistudio.qa.governance.gate_record import checks, evaluator, io
from scistudio.qa.governance.gate_record.checks import (
    CHECK_CATALOG,
    diff_scoped_command,
    event_is_valid_for,
    select_python_tests,
    select_test_targets,
)
from scistudio.qa.governance.gate_record.evaluator import EvaluatorMode
from scistudio.qa.governance.gate_record.ledger import CheckEvent

REPO_ROOT = Path(__file__).resolve().parents[2]


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


@pytest.fixture
def mirror_repo(tmp_path: Path) -> Path:
    """A repo whose tests/ tree mirrors src/scistudio/ the way the real one does."""

    repo = tmp_path / "repo"
    (repo / "tests/qa").mkdir(parents=True)
    (repo / "tests/core").mkdir(parents=True)
    # Real files, not just directories: narrowing drops paths that no longer
    # exist, so a fixture of empty directories would never exercise that rule.
    for rel in (
        "src/scistudio/version.py",
        "src/scistudio/qa/a.py",
        "src/scistudio/qa/x.py",
        "src/scistudio/qa/governance/x.py",
        "src/scistudio/qa/governance/gate_record/checks.py",
        "tests/test_version.py",
        "tests/qa/test_gate_record.py",
        "tests/qa/test_a.py",
        "tests/core/conftest.py",
    ):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text("x = 1\n", encoding="utf-8")
    _git(repo, "init", "-q")
    return repo


# ---------------------------------------------------------------------------
# select_test_targets: resolve when provable, defer to CI when not (FR-003, #2386).
# ---------------------------------------------------------------------------


def test_source_module_maps_to_the_longest_existing_mirrored_test_dir(mirror_repo: Path) -> None:
    targets = select_test_targets(mirror_repo, ["src/scistudio/qa/governance/gate_record/checks.py"])

    # tests/qa/governance does not exist and no test_checks.py mirrors it; tests/qa does.
    assert targets == ("tests/qa",)


def test_top_level_module_maps_to_its_mirrored_test_file(mirror_repo: Path) -> None:
    assert select_test_targets(mirror_repo, ["src/scistudio/version.py"]) == ("tests/test_version.py",)


def test_changed_test_file_selects_itself(mirror_repo: Path) -> None:
    assert select_test_targets(mirror_repo, ["tests/qa/test_gate_record.py"]) == ("tests/qa/test_gate_record.py",)


def test_changed_conftest_selects_its_whole_directory(mirror_repo: Path) -> None:
    assert select_test_targets(mirror_repo, ["tests/core/conftest.py"]) == ("tests/core",)


@pytest.mark.parametrize(
    "changed",
    [
        pytest.param("pyproject.toml", id="pytest-and-coverage-config"),
        pytest.param("tests/conftest.py", id="root-conftest"),
        pytest.param(".github/workflows/ci.yml", id="ci-workflow"),
        pytest.param(".pre-commit-config.yaml", id="pre-commit-config"),
    ],
)
def test_global_input_is_deferred_to_ci_without_widening(mirror_repo: Path, changed: str) -> None:
    """A global input can change any test; CI's full suite owns it, the rest still narrows."""

    selection = select_python_tests(mirror_repo, [changed, "src/scistudio/qa/x.py"])

    assert selection.targets == ("tests/qa",)
    assert selection.coverage_deferred_to_ci
    assert f"global test input: {changed}" in (selection.deferred_reason() or "")


def test_unreferenced_test_asset_is_deferred(mirror_repo: Path) -> None:
    """A fixture no test names, in a directory with no tests, selects nothing."""

    selection = select_python_tests(mirror_repo, ["tests/fixtures/sample.tiff"])

    assert selection.targets == ()
    assert "unreferenced test asset: tests/fixtures/sample.tiff" in (selection.deferred_reason() or "")


def test_test_asset_selects_the_tests_that_reference_it(mirror_repo: Path) -> None:
    """#2386 regression shape: a regenerated snapshot selects its readers, not the suite."""

    (mirror_repo / "tests/contracts").mkdir(parents=True)
    (mirror_repo / "tests/contracts/openapi.json").write_text("{}\n", encoding="utf-8")
    (mirror_repo / "tests/contracts/snapshot_helper.py").write_text('SNAP = "openapi.json"\n', encoding="utf-8")
    (mirror_repo / "tests/contracts/test_other_contract.py").write_text("def test_o(): ...\n", encoding="utf-8")
    (mirror_repo / "tests/qa/test_reads_snapshot.py").write_text(
        'PATH = "tests/contracts/openapi.json"\n', encoding="utf-8"
    )

    selection = select_python_tests(mirror_repo, ["tests/contracts/openapi.json"])

    assert selection.targets == ("tests/contracts/test_other_contract.py", "tests/qa/test_reads_snapshot.py")
    assert not selection.coverage_deferred_to_ci


def test_source_module_with_no_mirrored_test_location_is_deferred(mirror_repo: Path) -> None:
    selection = select_python_tests(mirror_repo, ["src/scistudio/nosuchpkg/thing.py"])

    assert selection.targets == ()
    assert selection.coverage_deferred_to_ci


def test_source_module_selects_tests_that_import_it(mirror_repo: Path) -> None:
    (mirror_repo / "src/scistudio/nosuchpkg").mkdir(parents=True)
    (mirror_repo / "src/scistudio/nosuchpkg/thing.py").write_text("x = 1\n", encoding="utf-8")
    (mirror_repo / "tests/qa/test_uses_thing.py").write_text(
        "from scistudio.nosuchpkg import thing\n", encoding="utf-8"
    )

    assert select_test_targets(mirror_repo, ["src/scistudio/nosuchpkg/thing.py"]) == ("tests/qa/test_uses_thing.py",)


def test_mirrored_test_file_is_preferred_over_the_mirrored_directory(mirror_repo: Path) -> None:
    (mirror_repo / "tests/qa/test_x.py").write_text("def test_x(): ...\n", encoding="utf-8")

    assert select_test_targets(mirror_repo, ["src/scistudio/qa/x.py"]) == ("tests/qa/test_x.py",)


def test_script_selects_its_mirrored_and_referencing_tests(mirror_repo: Path) -> None:
    (mirror_repo / "scripts").mkdir()
    (mirror_repo / "scripts/deferral_scan.py").write_text("x = 1\n", encoding="utf-8")
    (mirror_repo / "tests/scripts").mkdir()
    (mirror_repo / "tests/scripts/test_deferral_scan.py").write_text("def test_d(): ...\n", encoding="utf-8")
    (mirror_repo / "tests/qa/test_mentions_script.py").write_text('S = "scripts/deferral_scan.py"\n', encoding="utf-8")

    assert select_test_targets(mirror_repo, ["scripts/deferral_scan.py"]) == (
        "tests/qa/test_mentions_script.py",
        "tests/scripts/test_deferral_scan.py",
    )


def test_python_outside_the_package_with_no_referencing_test_is_deferred(mirror_repo: Path) -> None:
    selection = select_python_tests(mirror_repo, ["packages/pkg/thing.py"])

    assert selection.targets == ()
    assert "no test references: packages/pkg/thing.py" in (selection.deferred_reason() or "")


def test_docs_only_diff_selects_nothing_and_defers_rather_than_widening(mirror_repo: Path) -> None:
    """Selecting zero tests must never read as 'the suite passed', nor run the suite."""

    selection = select_python_tests(mirror_repo, ["docs/specs/x.md"])

    assert selection.targets == ()
    assert selection.coverage_deferred_to_ci
    assert selection.deferred_reason() == "no test target derivable from the diff"


def test_selection_never_names_the_whole_tests_tree(mirror_repo: Path) -> None:
    """A deleted top-level test module must not select tests/ itself."""

    selection = select_python_tests(mirror_repo, ["tests/test_gone.py"])

    assert "tests" not in selection.targets
    assert selection.targets == ()
    assert selection.coverage_deferred_to_ci


# ---------------------------------------------------------------------------
# diff_scoped_command: what each strategy actually builds (FR-001, FR-005).
# ---------------------------------------------------------------------------


def test_lint_variant_names_the_changed_files_instead_of_the_repo(mirror_repo: Path) -> None:
    command = diff_scoped_command(
        CHECK_CATALOG["lint_format"],
        repo_root=mirror_repo,
        changed_files=["src/scistudio/qa/a.py", "docs/x.md"],
    )

    assert command == ("ruff", "check", "src/scistudio/qa/a.py")


def test_format_variant_rewrites_instead_of_checking(mirror_repo: Path) -> None:
    """Every recorded format_check failure was auto-fixable; locally we fix."""

    command = diff_scoped_command(
        CHECK_CATALOG["format_check"],
        repo_root=mirror_repo,
        changed_files=["src/scistudio/qa/a.py"],
    )

    assert command == ("ruff", "format", "src/scistudio/qa/a.py")
    assert "--check" not in command
    # CI keeps the failing form.
    assert "--check" in CHECK_CATALOG["format_check"].command


def test_type_variant_covers_only_source_files(mirror_repo: Path) -> None:
    command = diff_scoped_command(
        CHECK_CATALOG["type_check"],
        repo_root=mirror_repo,
        changed_files=["src/scistudio/qa/a.py", "tests/qa/test_a.py"],
    )

    assert command == ("mypy", "src/scistudio/qa/a.py", "--ignore-missing-imports")


def test_test_variant_disables_the_coverage_floor_and_names_targets(mirror_repo: Path) -> None:
    """Without --no-cov the repo-wide floor makes every subset run fail (FR-003)."""

    command = diff_scoped_command(
        CHECK_CATALOG["python_tests"],
        repo_root=mirror_repo,
        changed_files=["src/scistudio/qa/governance/x.py"],
    )

    assert command is not None
    assert "--no-cov" in command
    assert command[-1] == "tests/qa"


def test_unmappable_test_selection_never_falls_back_to_the_ci_mirror(mirror_repo: Path) -> None:
    command = diff_scoped_command(
        CHECK_CATALOG["python_tests"],
        repo_root=mirror_repo,
        changed_files=["pyproject.toml"],
    )

    assert command is not None
    assert command == (*CHECK_CATALOG["python_tests"].command, "--no-cov")


def test_checks_without_a_strategy_have_no_diff_scoped_form(mirror_repo: Path) -> None:
    for name in ("full_audit", "wheel_release_smoke", "architecture_tests", "deferral_discipline"):
        assert CHECK_CATALOG[name].local_scope == "none"
        assert (
            diff_scoped_command(
                CHECK_CATALOG[name],
                repo_root=mirror_repo,
                changed_files=["src/scistudio/qa/a.py"],
            )
            is None
        )


# ---------------------------------------------------------------------------
# Diff-scoped evidence never stands in for a CI-mirror obligation (FR-008).
# ---------------------------------------------------------------------------


def _event(scope: Literal["repo", "diff"], *, status: Literal["pass", "fail"] = "pass") -> CheckEvent:
    return CheckEvent(
        name="python_tests",
        command="pytest",
        covered_surface="python_tests",
        scope=scope,
        input_fingerprint="sha256:abc",
        exit_code=0 if status == "pass" else 1,
        status=status,
    )


def test_repo_scoped_evidence_satisfies_a_ci_mirror_obligation() -> None:
    assert event_is_valid_for(_event("repo"), input_fingerprint="sha256:abc", require_repo_scope=True)


def test_diff_scoped_evidence_never_satisfies_a_ci_mirror_obligation() -> None:
    event = _event("diff")

    # Valid as a local signal ...
    assert event_is_valid_for(event, input_fingerprint="sha256:abc")
    # ... but not as proof of the full surface.
    assert not event_is_valid_for(event, input_fingerprint="sha256:abc", require_repo_scope=True)


def test_pre_existing_events_without_a_scope_field_read_as_repo_scoped() -> None:
    """Ledgers written before the field existed recorded repository-wide runs."""

    event = CheckEvent.model_validate(
        {
            "name": "python_tests",
            "command": "pytest",
            "covered_surface": "python",
            "input_fingerprint": "sha256:abc",
            "exit_code": 0,
            "status": "pass",
        }
    )

    assert event.scope == "repo"
    assert event_is_valid_for(event, input_fingerprint="sha256:abc", require_repo_scope=True)


# ---------------------------------------------------------------------------
# Surface split: one check's edit no longer invalidates another's (FR-006).
# ---------------------------------------------------------------------------


def test_a_test_only_edit_does_not_invalidate_type_check_evidence() -> None:
    """mypy reads src/; a change under tests/ cannot alter its verdict."""

    changed = ["tests/qa/test_gate_record.py"]

    assert evaluator._check_input_paths("type_check", changed) == []
    assert evaluator._check_input_paths("python_tests", changed) == changed


def test_a_frontend_edit_does_not_invalidate_full_audit_evidence() -> None:
    """The audit reads no frontend or desktop file (FR-007)."""

    assert evaluator._check_input_paths("full_audit", ["frontend/src/App.tsx"]) == []
    assert evaluator._check_input_paths("full_audit", ["desktop/main.js"]) == []
    assert evaluator._check_input_paths("full_audit", ["docs/adr/ADR-042.md"]) == ["docs/adr/ADR-042.md"]


def test_a_non_python_edit_does_not_invalidate_the_deferral_ratchet() -> None:
    """scripts/deferral_scan.py rglobs *.py and reads nothing else (FR-007)."""

    assert evaluator._check_input_paths("deferral_discipline", ["docs/specs/x.md"]) == []
    assert evaluator._check_input_paths("deferral_discipline", ["src/scistudio/a.py"]) == ["src/scistudio/a.py"]


def test_python_check_surfaces_are_distinct() -> None:
    """Sharing one surface is what made a formatting edit invalidate the suite."""

    surfaces_by_check = {name: CHECK_CATALOG[name].covered_surface for name in CHECK_CATALOG}

    assert surfaces_by_check["lint_format"] == surfaces_by_check["format_check"]
    assert len({surfaces_by_check[n] for n in ("lint_format", "type_check", "python_tests", "import_contracts")}) == 4


# ---------------------------------------------------------------------------
# The floor stays where CI can enforce it (FR-004).
# ---------------------------------------------------------------------------


def test_the_repository_coverage_floor_is_not_relaxed() -> None:
    """Local runs opt out per-invocation; the configured floor must not move."""

    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    addopts = config["tool"]["pytest"]["ini_options"]["addopts"]

    assert "--cov-fail-under=70" in addopts
    assert config["tool"]["coverage"]["report"]["fail_under"] == 70
    # The CI-mirror command must never carry the local opt-out.
    assert "--no-cov" not in CHECK_CATALOG["python_tests"].command


def test_ci_still_runs_both_test_phases_over_the_whole_suite() -> None:
    ci = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert 'pytest -n auto -m "not serial"' in ci
    assert "pytest -n 0 -m serial" in ci


# ---------------------------------------------------------------------------
# Selection breadth is a tier concern; scope is a mode concern (FR-011).
# ---------------------------------------------------------------------------


def test_tier_1_selects_a_superset_of_tier_2() -> None:
    changed = ["src/scistudio/core/thing.py"]
    tier1 = set(checks.select_checks(tier=1, changed_files=changed).required)
    tier2 = set(checks.select_checks(tier=2, changed_files=changed).required)

    assert tier2 < tier1


def test_selection_is_scope_agnostic() -> None:
    """select_checks answers WHICH checks; the evaluator answers HOW BROADLY."""

    empty = checks.select_checks(tier=1, changed_files=[]).required
    broad = checks.select_checks(tier=1, changed_files=["src/scistudio/a.py"]).required

    assert set(empty) <= set(broad)


# ---------------------------------------------------------------------------
# End-to-end: a real run records which variant it used.
# ---------------------------------------------------------------------------


def test_run_check_records_the_variant_that_actually_ran(mirror_repo: Path) -> None:
    _git(mirror_repo, "config", "user.email", "t@example.com")
    _git(mirror_repo, "config", "user.name", "test")
    (mirror_repo / "src/scistudio/qa/a.py").write_text("x = 1\n", encoding="utf-8")
    _git(mirror_repo, "add", "-A")
    _git(mirror_repo, "commit", "-q", "-m", "add")

    event = checks.run_check(
        mirror_repo,
        "lint_format",
        changed_files=["src/scistudio/qa/a.py"],
        diff_fingerprint=io.diff_fingerprint(mirror_repo, "HEAD", "HEAD"),
        scope="diff",
    )

    if event.status == "skipped":
        pytest.skip("ruff is not resolvable in this environment")
    assert event.scope == "diff"
    assert event.command.endswith("src/scistudio/qa/a.py")


def test_run_check_falls_back_to_repo_scope_when_narrowing_is_impossible(mirror_repo: Path) -> None:
    """The event states the command that ran, not the one that was requested."""

    event = checks.run_check(
        mirror_repo,
        "lint_format",
        changed_files=["docs/only.md"],
        diff_fingerprint="sha256:x",
        scope="diff",
    )

    assert event.scope == "repo"
    assert event.command == "ruff check ."


# ---------------------------------------------------------------------------
# Corpus-wide checks are deferred to CI locally, and only those (FR-002).
# ---------------------------------------------------------------------------


def _required(mode: EvaluatorMode) -> set[str]:
    """What the given caller must prove, through the real narrowing function."""

    selection = checks.select_checks(tier=1, changed_files=["src/scistudio/core/thing.py"])
    return set(evaluator.required_for_mode(selection.required, mode=mode))


def test_no_check_is_deferred_out_of_the_local_gate() -> None:
    """Every remaining check narrows, or costs under 20s; none is CI-only.

    semantic_dup was the sole exception and was removed outright (#2120), so a
    local pre-PR run must now prove the same set the tier selected.
    """

    selection = checks.select_checks(tier=1, changed_files=["src/scistudio/core/thing.py"])

    assert _required("pre-pr") == set(selection.required)
    for name in ("architecture_tests", "full_audit", "deferral_discipline", "import_contracts"):
        assert name in _required("pre-pr"), f"{name} must stay local"


def test_semantic_dup_is_gone_from_every_selection_surface() -> None:
    assert "semantic_dup" not in CHECK_CATALOG
    assert "semantic_dup" not in checks.select_checks(tier=1, changed_files=[]).required
    assert "semantic_dup" not in evaluator._CI_OWNED_QUALITY_CHECKS
    assert "semantic_dup" not in evaluator._PRE_COMMIT_SKIP_CHECKS


# ---------------------------------------------------------------------------
# A deleted path is in the diff but must never reach a tool (FR-001, FR-003).
# ---------------------------------------------------------------------------


def test_deleted_python_files_are_not_handed_to_ruff_or_mypy(mirror_repo: Path) -> None:
    """`ruff format <removed-file>` is an execution error, not a finding."""

    (mirror_repo / "src/scistudio/qa/kept.py").write_text("x = 1\n", encoding="utf-8")
    changed = ["src/scistudio/qa/kept.py", "src/scistudio/qa/gone.py"]

    for name in ("lint_format", "format_check"):
        command = diff_scoped_command(CHECK_CATALOG[name], repo_root=mirror_repo, changed_files=changed)
        assert command is not None
        assert "src/scistudio/qa/gone.py" not in command
        assert "src/scistudio/qa/kept.py" in command

    typed = diff_scoped_command(CHECK_CATALOG["type_check"], repo_root=mirror_repo, changed_files=changed)
    assert typed == ("mypy", "src/scistudio/qa/kept.py", "--ignore-missing-imports")


def test_a_deletion_only_diff_falls_back_to_the_repository_command(mirror_repo: Path) -> None:
    """Nothing survives narrowing, so the whole-repo command is the right answer."""

    changed = ["src/scistudio/qa/gone.py", "tests/qa/test_gone.py"]

    for name in ("lint_format", "format_check", "type_check"):
        assert diff_scoped_command(CHECK_CATALOG[name], repo_root=mirror_repo, changed_files=changed) is None


def test_a_deleted_source_module_selects_its_package_tests(mirror_repo: Path) -> None:
    """Its tests moved or went with it; its package's mirrored tests still run."""

    assert select_test_targets(mirror_repo, ["src/scistudio/qa/gone.py"]) == ("tests/qa",)


def test_a_deleted_test_file_does_not_select_itself(mirror_repo: Path) -> None:
    (mirror_repo / "tests/qa/test_kept.py").write_text("def test_k(): ...\n", encoding="utf-8")

    targets = select_test_targets(mirror_repo, ["tests/qa/test_kept.py", "tests/qa/test_gone.py"])

    # The deletion selects its surviving sibling directory, never the removed path.
    assert "tests/qa/test_gone.py" not in targets
    assert targets == ("tests/qa", "tests/qa/test_kept.py")


# ---------------------------------------------------------------------------
# The local gate never runs the full Python test suite (#2386).
# ---------------------------------------------------------------------------


def _whole_suite(argv: list[str]) -> bool:
    """True when a python_tests argv names no explicit target or the whole tree."""

    try:
        checks.assert_bounded_python_test_argv(argv)
    except checks.FullPythonSuiteRefusedError:
        return True
    return False


def test_the_2379_openapi_snapshot_diff_selects_its_readers_not_the_suite() -> None:
    """Regression: #2379 widened to the full suite solely on tests/contracts/openapi.json."""

    selection = select_python_tests(REPO_ROOT, ["src/scistudio/api/models.py", "tests/contracts/openapi.json"])

    assert selection.targets
    assert "tests/contracts/test_openapi_snapshot.py" in selection.targets
    assert "tests" not in selection.targets
    assert not selection.coverage_deferred_to_ci


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param([], id="no-args"),
        pytest.param(["--timeout=60", "--timeout-method=thread"], id="options-only"),
        pytest.param(["--no-cov", "-m", "not serial"], id="marker-value-is-not-a-target"),
        pytest.param(["--no-cov", "tests"], id="whole-tests-tree"),
        pytest.param(["--no-cov", "tests/"], id="whole-tests-tree-slash"),
        pytest.param(["--no-cov", "."], id="repo-root"),
    ],
)
def test_guard_refuses_whole_suite_invocations_outside_ci(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> None:
    monkeypatch.delenv("CI", raising=False)

    assert _whole_suite(argv)


def test_guard_allows_explicit_targets_outside_ci(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CI", raising=False)

    assert not _whole_suite(["--no-cov", "tests/qa"])
    assert not _whole_suite(["--no-cov", "tests/qa/test_gate_record.py::test_x"])


def test_guard_does_not_constrain_ci(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CI", "true")

    assert not _whole_suite([])


def _fake_subprocess(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []

    def _run(argv: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(checks.subprocess, "run", _run)
    monkeypatch.setattr(checks.parity, "venv_path", lambda _repo: Path("/nonexistent-venv"))
    return calls


@pytest.mark.parametrize("scope", ["repo", "diff"])
@pytest.mark.parametrize(
    "changed",
    [
        pytest.param(["pyproject.toml"], id="global-input"),
        pytest.param(["docs/specs/x.md"], id="no-python"),
        pytest.param(["frontend/src/App.tsx"], id="frontend-only"),
        pytest.param(["tests/fixtures/sample.tiff"], id="unreferenced-asset"),
        pytest.param(["src/scistudio/nosuchpkg/thing.py"], id="unmapped-module"),
        pytest.param(["tests/test_gone.py"], id="deleted-top-level-test"),
    ],
)
def test_unmappable_python_tests_record_a_ci_deferral_without_running(
    mirror_repo: Path, monkeypatch: pytest.MonkeyPatch, scope: Literal["repo", "diff"], changed: list[str]
) -> None:
    """Requested scope does not matter outside CI: nothing runs, the event defers to CI."""

    monkeypatch.delenv("CI", raising=False)
    calls = _fake_subprocess(monkeypatch)

    event = checks.run_check(
        mirror_repo, "python_tests", changed_files=changed, diff_fingerprint="sha256:x", scope=scope
    )

    assert calls == []
    assert event.status == "pass"
    assert event.scope == "diff"
    assert event.exit_code is None
    assert event.coverage_deferred_to_ci
    assert event.deferred_reason
    assert "deferred to CI" in event.summary
    # The deferral is valid local evidence ...
    assert event_is_valid_for(event, input_fingerprint=event.input_fingerprint)
    # ... and never proof of the full surface.
    assert not event_is_valid_for(event, input_fingerprint=event.input_fingerprint, require_repo_scope=True)


@pytest.mark.parametrize("scope", ["repo", "diff"])
def test_python_tests_run_only_explicit_targets_outside_ci(
    mirror_repo: Path, monkeypatch: pytest.MonkeyPatch, scope: Literal["repo", "diff"]
) -> None:
    monkeypatch.delenv("CI", raising=False)
    calls = _fake_subprocess(monkeypatch)

    event = checks.run_check(
        mirror_repo,
        "python_tests",
        changed_files=["src/scistudio/qa/x.py", "pyproject.toml"],
        diff_fingerprint="sha256:x",
        scope=scope,
    )

    assert len(calls) == 1
    assert calls[0][-1] == "tests/qa"
    assert not _whole_suite(calls[0][1:])
    assert event.status == "pass"
    assert event.scope == "diff"
    assert event.coverage_deferred_to_ci
    assert "global test input: pyproject.toml" in (event.deferred_reason or "")


def test_run_check_refuses_a_target_less_python_test_command(
    mirror_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The chokepoint holds even if selection were bypassed."""

    monkeypatch.delenv("CI", raising=False)
    calls = _fake_subprocess(monkeypatch)
    monkeypatch.setattr(
        checks,
        "select_python_tests",
        lambda *_a, **_k: checks.PythonTestSelection(targets=("tests",), deferred=()),
    )

    with pytest.raises(checks.FullPythonSuiteRefusedError):
        checks.run_check(mirror_repo, "python_tests", changed_files=["x.py"], diff_fingerprint=None, scope="diff")
    assert calls == []


@pytest.mark.parametrize("mode", ["local", "pre-commit", "commit-msg", "pre-push", "pre-pr", "ci"])
@pytest.mark.parametrize("force_checks", [False, True])
def test_no_mode_or_flag_executes_python_tests_at_repository_scope_locally(
    mode: EvaluatorMode, force_checks: bool
) -> None:
    scope = evaluator.execution_scope_for("python_tests", mode=mode, force_checks=force_checks)

    if mode == "ci":
        # ci mode never even requires python_tests: ci.yml owns the full suite.
        assert "python_tests" not in _required("ci")
    else:
        assert scope == "diff"


def test_force_checks_still_widens_checks_other_than_python_tests() -> None:
    assert evaluator.execution_scope_for("lint_format", mode="pre-pr", force_checks=True) == "repo"
    assert evaluator.execution_scope_for("lint_format", mode="pre-pr", force_checks=False) == "diff"


def test_every_tier_and_diff_shape_yields_a_bounded_python_test_command(monkeypatch: pytest.MonkeyPatch) -> None:
    """Whatever the gate selects, the python_tests command it builds names targets or runs nothing."""

    monkeypatch.delenv("CI", raising=False)
    diffs = [
        [],
        ["docs/ai-developer/rules.md"],
        ["frontend/src/App.tsx"],
        ["pyproject.toml"],
        ["tests/conftest.py"],
        [".github/workflows/ci.yml"],
        ["tests/contracts/openapi.json"],
        ["src/scistudio/__init__.py"],
        ["scripts/scistudio_pr_create.py"],
        ["src/scistudio/qa/governance/gate_record/checks.py"],
    ]
    spec = CHECK_CATALOG["python_tests"]
    for changed in diffs:
        command = diff_scoped_command(spec, repo_root=REPO_ROOT, changed_files=changed)
        assert command is not None
        targets = command[len(spec.command) + 1 :]
        if targets:
            assert not _whole_suite(list(command[1:])), changed
