"""Tests for the ADR-042 Addendum 6 shared evaluator (spec §10.3/§10.4).

Covers: git-observed diff over agent declarations, tier derivation + observed-
diff escalation, obligation inference, claimed-but-unverified docs/test
reconciliation, sanitization, single-sentrux classifier, and guards-run-once.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scistudio.qa.governance.gate_record import checks, evaluator, io, surfaces, workflow
from scistudio.qa.governance.gate_record.io import SanitizationError
from scistudio.qa.governance.gate_record.ledger import (
    CheckEvent,
    DeclaredScope,
    DocsEvent,
    GateLedger,
    IssueRef,
    PullRequestEvidence,
    RequiredObligations,
    TestEvent,
)
from scistudio.qa.schemas.report import AuditReport, AuditStatus


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """A throwaway git repo with one committed baseline and one new change."""

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "test")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


def _ledger(**overrides: object) -> GateLedger:
    base: dict[str, object] = {
        "record_id": "1509-core",
        "runtime": "claude-code",
        "task_kind": "bugfix",
        "persona": "implementer",
        "branch": "track/x",
        "owner_directive": "fix it",
    }
    base.update(overrides)
    return GateLedger.model_validate(base)


def _add_change(repo: Path, rel: str, content: str = "x\n") -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _git(repo, "add", rel)
    _git(repo, "commit", "-q", "-m", f"add {rel}")


# ---------------------------------------------------------------------------
# Ledger discovery and post-PR finalize behavior.
# ---------------------------------------------------------------------------


def test_discover_ledger_can_include_finalized_for_ci(tmp_path: Path) -> None:
    records_dir = tmp_path / ".workflow" / "records"
    records_dir.mkdir(parents=True)
    record_path = records_dir / "1568-finalized-ledger-ci.json"
    ledger = _ledger(branch="track/x")
    ledger.pull_request = PullRequestEvidence(url="https://github.com/zjzcpj/SciStudio/pull/1568", number=1568)
    io.write_ledger(record_path, ledger, repo_root=tmp_path)

    default_discovery = io.discover_ledger(tmp_path, branch="track/x")
    assert not default_discovery.found
    assert default_discovery.candidates == []

    ci_discovery = io.discover_ledger(tmp_path, branch="track/x", include_finalized=True)
    assert ci_discovery.found
    assert ci_discovery.path == record_path


def test_ci_mode_check_resolves_finalized_ledger(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _git(git_repo, "checkout", "-q", "-b", "track/x")
    records_dir = git_repo / ".workflow" / "records"
    records_dir.mkdir(parents=True)
    record_path = records_dir / "1568-finalized-ledger-ci.json"
    ledger = _ledger(branch="track/x")
    ledger.pull_request = PullRequestEvidence(url="https://github.com/zjzcpj/SciStudio/pull/1568", number=1568)
    io.write_ledger(record_path, ledger, repo_root=git_repo)

    def _fake_reconcile(**kwargs: object) -> evaluator.ReconcileResult:
        resolved = kwargs["ledger"]
        assert isinstance(resolved, GateLedger)
        assert resolved.pull_request is not None
        return evaluator.ReconcileResult(
            report=AuditReport(tool="gate_record", status=AuditStatus.PASS, source_sha="test"),
            strictness_tier=2,
            required_obligations=RequiredObligations(),
        )

    monkeypatch.setattr(workflow.evaluator, "reconcile", _fake_reconcile)
    args = SimpleNamespace(
        record=None,
        mode="ci",
        owner_directive=[],
        include=[],
        exclude=[],
        issue=[],
        docs_updated=[],
        docs_na=[],
        test_path=[],
        test_na=[],
        check=[],
        check_na=[],
        admin_label=[],
        skip_execution=True,
        only=[],
        pr_body_file=None,
        pr_context_file=None,
        head="HEAD",
        base="HEAD",
    )

    assert workflow.run_check(git_repo, args) == workflow.EXIT_OK
    output = capsys.readouterr().out
    assert "no gate ledger found" not in output
    assert "reconciliation passed" in output


# ---------------------------------------------------------------------------
# Observed diff over declarations.
# ---------------------------------------------------------------------------


def test_observed_diff_comes_from_git_not_declarations(git_repo: Path) -> None:
    # Declare a scope the agent claims, but commit a DIFFERENT file.
    _add_change(git_repo, "src/scistudio/x.py")
    ledger = _ledger(declared_scope=DeclaredScope(include=["src/scistudio/y.py"]))
    result = evaluator.reconcile(
        ledger=ledger,
        repo_root=git_repo,
        base="HEAD~1",
        head="HEAD",
        mode="local",
        run_checks=False,
    )
    assert ledger.observed_diff is not None
    assert "src/scistudio/x.py" in ledger.observed_diff.changed_files
    # The observed file is out of the declared scope -> scope finding.
    assert any(f.rule_id == "scope.out-of-scope" for f in result.report.findings)


# ---------------------------------------------------------------------------
# Tier derivation + escalation (§7.6).
# ---------------------------------------------------------------------------


def test_baseline_tier_from_task_kind() -> None:
    empty: dict[str, list[str]] = {name: [] for name in evaluator._SURFACE_CLASSIFIERS}
    assert evaluator.derive_tier("feature", empty) == 1
    assert evaluator.derive_tier("bugfix", empty) == 2
    assert evaluator.derive_tier("docs", empty) == 3


def test_observed_diff_escalates_to_tier_1_never_lowers() -> None:
    grouped: dict[str, list[str]] = {name: [] for name in evaluator._SURFACE_CLASSIFIERS}
    grouped["protected_core"] = ["src/scistudio/core/foo.py"]
    # A docs task (baseline tier 3) that touches protected core escalates to 1.
    assert evaluator.derive_tier("docs", grouped) == 1


def test_governance_touch_escalates_tier(git_repo: Path) -> None:
    _add_change(git_repo, "src/scistudio/qa/governance/foo.py")
    ledger = _ledger(task_kind="maintenance")
    result = evaluator.reconcile(
        ledger=ledger, repo_root=git_repo, base="HEAD~1", head="HEAD", mode="local", run_checks=False
    )
    assert result.strictness_tier == 1


# ---------------------------------------------------------------------------
# Claimed-but-unverified docs/test reconciliation (§3.3.4).
# ---------------------------------------------------------------------------


def test_claimed_docs_path_not_in_diff_is_unverified(git_repo: Path) -> None:
    _add_change(git_repo, "src/scistudio/x.py")
    ledger = _ledger(declared_scope=DeclaredScope(include=["src/scistudio/x.py"]))
    ledger.docs_events.append(DocsEvent(kind="path", path="docs/not-changed.md"))
    result = evaluator.reconcile(
        ledger=ledger, repo_root=git_repo, base="HEAD~1", head="HEAD", mode="local", run_checks=False
    )
    assert any(f.rule_id == "docs.claimed-but-unverified" for f in result.report.findings)


def test_claimed_test_path_not_in_diff_is_unverified(git_repo: Path) -> None:
    _add_change(git_repo, "src/scistudio/x.py")
    ledger = _ledger(declared_scope=DeclaredScope(include=["src/scistudio/x.py"]))
    ledger.test_events.append(TestEvent(kind="path", path="tests/test_not_changed.py"))
    result = evaluator.reconcile(
        ledger=ledger, repo_root=git_repo, base="HEAD~1", head="HEAD", mode="local", run_checks=False
    )
    assert any(f.rule_id == "tests.claimed-but-unverified" for f in result.report.findings)


def test_verified_test_path_satisfies_obligation(git_repo: Path) -> None:
    # Implementation + an actually-changed test path -> no test obligation gap.
    repo = git_repo
    (repo / "src/scistudio").mkdir(parents=True, exist_ok=True)
    (repo / "src/scistudio/x.py").write_text("y\n", encoding="utf-8")
    (repo / "tests").mkdir(parents=True, exist_ok=True)
    (repo / "tests/test_x.py").write_text("def test_x():\n    assert True\n", encoding="utf-8")
    _git(repo, "add", "src/scistudio/x.py", "tests/test_x.py")
    _git(repo, "commit", "-q", "-m", "impl+test")
    ledger = _ledger(
        task_kind="bugfix",
        declared_scope=DeclaredScope(include=["src/scistudio/**", "tests/**"]),
    )
    ledger.test_events.append(TestEvent(kind="path", path="tests/test_x.py"))
    ledger.docs_events.append(
        DocsEvent.model_validate({"kind": "na", "class": "implementation", "rationale": "internal"})
    )
    result = evaluator.reconcile(
        ledger=ledger, repo_root=repo, base="HEAD~1", head="HEAD", mode="local", run_checks=False
    )
    assert "tests.changed_test_required" not in result.unsatisfied


# ---------------------------------------------------------------------------
# Obligation inference (§3.3.5).
# ---------------------------------------------------------------------------


def test_implementation_change_requires_test_evidence(git_repo: Path) -> None:
    _add_change(git_repo, "src/scistudio/x.py")
    ledger = _ledger(task_kind="bugfix", declared_scope=DeclaredScope(include=["src/scistudio/**"]))
    result = evaluator.reconcile(
        ledger=ledger, repo_root=git_repo, base="HEAD~1", head="HEAD", mode="local", run_checks=False
    )
    assert "tests.changed_test_required" in result.unsatisfied
    assert "changed_test_required" in result.required_obligations.tests


def test_docs_task_does_not_require_test_evidence(git_repo: Path) -> None:
    _add_change(git_repo, "docs/guide.md")
    ledger = _ledger(task_kind="docs", persona="adr_author", declared_scope=DeclaredScope(include=["docs/**"]))
    ledger.docs_events.append(DocsEvent(kind="path", path="docs/guide.md"))
    result = evaluator.reconcile(
        ledger=ledger, repo_root=git_repo, base="HEAD~1", head="HEAD", mode="local", run_checks=False
    )
    assert "tests.changed_test_required" not in result.unsatisfied


# ---------------------------------------------------------------------------
# Single sentrux classifier (§4.1) and guards-run-once.
# ---------------------------------------------------------------------------


def test_sentrux_classifier_includes_tests() -> None:
    # The §4.1 resolution: tests/** ARE sentrux-applicable (CI-inclusive).
    assert surfaces.sentrux_applies("tests/qa/test_x.py")
    assert surfaces.sentrux_applies("src/scistudio/x.py")
    assert not surfaces.sentrux_applies("docs/guide.md")
    assert not surfaces.sentrux_applies(".workflow/records/1-x.json")


def test_guards_run_exactly_once(git_repo: Path) -> None:
    _add_change(git_repo, "src/scistudio/x.py")
    ledger = _ledger(declared_scope=DeclaredScope(include=["src/scistudio/**"]))
    result = evaluator.reconcile(
        ledger=ledger, repo_root=git_repo, base="HEAD~1", head="HEAD", mode="local", run_checks=False
    )
    guard_names = [e.guard for e in result.guard_events]
    assert len(guard_names) == len(set(guard_names))
    assert set(guard_names) == set(evaluator.GUARD_REGISTRY.keys())


def test_blocking_guard_emits_repair_hint(git_repo: Path) -> None:
    # Defect 2 regression (#1509): a blocking guard finding must carry an
    # actionable repair hint, not a bare ``- guard.<name>`` line, so the
    # one-pass-guidance bar holds for the whole guard class.
    _add_change(git_repo, "src/scistudio/core/foo.py")
    ledger = _ledger(task_kind="bugfix", declared_scope=DeclaredScope(include=["src/scistudio/**"]))
    result = evaluator.reconcile(
        ledger=ledger, repo_root=git_repo, base="HEAD~1", head="HEAD", mode="ci", run_checks=False
    )
    assert "guard.core_change_guard" in result.unsatisfied
    guard_hints = [h for h in result.repair_hints if h.startswith("- guard.core_change_guard")]
    assert guard_hints, result.repair_hints
    hint = guard_hints[0]
    # The hint surfaces the guard's own message AND a concrete per-guard action.
    assert "Fix:" in hint
    assert "admin-approved:core-change" in hint
    # And the affected protected-core path is named.
    assert "src/scistudio/core/foo.py" in hint


def test_guard_repair_hint_uses_finding_message_when_no_action_mapped() -> None:
    # The helper falls back to the finding's own message/remediation; the
    # ``- guard.<name>`` header is always present.
    from scistudio.qa.schemas.report import AuditReport, AuditStatus, Finding, Severity

    report = AuditReport(
        tool="some_guard",
        status=AuditStatus.FAIL,
        source_sha="x",
        findings=[Finding(rule_id="some_guard.x", severity=Severity.ERROR, message="thing is broken", file="a.py")],
    )
    hint = evaluator._guard_repair_hint("some_guard", report)
    assert hint.startswith("- guard.some_guard")
    assert "thing is broken" in hint
    assert "Affected: a.py" in hint


# ---------------------------------------------------------------------------
# ci-mode obligation scope (§7.5): workflow-gate validates GOVERNANCE, not the
# ci.yml quality matrix. Defect 2 regression (#1509).
# ---------------------------------------------------------------------------


def _ci_ready_repo(repo: Path) -> None:
    """Stage a governance change WITH docs + tests landed in the same diff."""

    (repo / "src/scistudio/qa/governance").mkdir(parents=True, exist_ok=True)
    (repo / "src/scistudio/qa/governance/foo.py").write_text("y = 1\n", encoding="utf-8")
    (repo / "docs/specs").mkdir(parents=True, exist_ok=True)
    (repo / "docs/specs/x.md").write_text("# spec\n", encoding="utf-8")
    (repo / "tests/qa").mkdir(parents=True, exist_ok=True)
    (repo / "tests/qa/test_foo.py").write_text("def test_foo():\n    assert True\n", encoding="utf-8")
    _git(repo, "add", "src/scistudio/qa/governance/foo.py", "docs/specs/x.md", "tests/qa/test_foo.py")
    _git(repo, "commit", "-q", "-m", "gov change + docs + tests")


def test_ci_mode_passes_without_quality_check_events(git_repo: Path) -> None:
    # (d) ci mode must NOT fail solely because the ci.yml quality matrix has no
    # ledger check_events: those run as separate authoritative ci.yml jobs.
    _ci_ready_repo(git_repo)
    ledger = _ledger(task_kind="feature", issues=[IssueRef(number=1509)], governance_touch=True)
    result = evaluator.reconcile(
        ledger=ledger,
        repo_root=git_repo,
        base="HEAD~1",
        head="HEAD",
        mode="ci",
        pr_body="Closes #1509",
        run_checks=True,
    )
    # No quality-check obligations remain; docs+tests satisfied from the diff.
    # (The synthetic tmp repo has no persona pointers / src import, so unrelated
    # parity/persona gaps may remain; this test asserts only the §7.5 scope.)
    assert not any(item.startswith("checks.") for item in result.unsatisfied), result.unsatisfied
    assert "docs.docs_required_or_na" not in result.unsatisfied
    assert "tests.changed_test_required" not in result.unsatisfied
    assert "guard.docs_landing" not in result.unsatisfied
    assert "issue.required" not in result.unsatisfied
    assert "guard.issue_link" not in result.unsatisfied


def test_ci_mode_quality_checks_dropped_from_obligations(git_repo: Path) -> None:
    # The ci.yml quality matrix is never listed as a required ci-mode check.
    _ci_ready_repo(git_repo)

    ledger = _ledger(task_kind="feature", issues=[IssueRef(number=1509)], governance_touch=True)
    result = evaluator.reconcile(
        ledger=ledger, repo_root=git_repo, base="HEAD~1", head="HEAD", mode="ci", pr_body="Closes #1509"
    )
    assert not (set(result.required_obligations.checks) & evaluator._CI_OWNED_QUALITY_CHECKS)


def test_ci_mode_still_fails_without_issue_linkage(git_repo: Path) -> None:
    # (c) ci mode still enforces issue linkage even with the quality matrix off.
    _ci_ready_repo(git_repo)
    ledger = _ledger(task_kind="feature", governance_touch=True)  # no issues
    result = evaluator.reconcile(
        ledger=ledger, repo_root=git_repo, base="HEAD~1", head="HEAD", mode="ci", pr_body="some body"
    )
    assert "issue.required" in result.unsatisfied


def test_ci_mode_still_fails_missing_closing_keyword(git_repo: Path) -> None:
    # (c) ci mode still enforces the PR-body closing keyword via issue_link guard.
    _ci_ready_repo(git_repo)

    ledger = _ledger(task_kind="feature", issues=[IssueRef(number=1509)], governance_touch=True)
    result = evaluator.reconcile(
        ledger=ledger,
        repo_root=git_repo,
        base="HEAD~1",
        head="HEAD",
        mode="ci",
        pr_body="No closing keyword here.",
    )
    assert "guard.issue_link" in result.unsatisfied


def test_ci_mode_still_fails_out_of_scope_change(git_repo: Path) -> None:
    # (c) ci mode still enforces scope reconciliation against the observed diff.
    _add_change(git_repo, "src/scistudio/x.py")

    ledger = _ledger(
        task_kind="feature",
        issues=[IssueRef(number=1509)],
        declared_scope=DeclaredScope(include=["src/scistudio/y.py"]),
    )
    result = evaluator.reconcile(
        ledger=ledger, repo_root=git_repo, base="HEAD~1", head="HEAD", mode="ci", pr_body="Closes #1509"
    )
    assert any(f.rule_id == "scope.out-of-scope" for f in result.report.findings)
    assert not result.passed


def test_ci_mode_still_fails_governance_guard_violation(git_repo: Path) -> None:
    # (c) ci mode still enforces governance guards: an unauthorized governance
    # change (no governance_touch, no bypass) still blocks via mod_guard.
    _add_change(git_repo, "docs/ai-developer/rules.md")

    ledger = _ledger(
        task_kind="feature",
        issues=[IssueRef(number=1509)],
        governance_touch=False,
        declared_scope=DeclaredScope(include=["docs/**"]),
    )
    result = evaluator.reconcile(
        ledger=ledger, repo_root=git_repo, base="HEAD~1", head="HEAD", mode="ci", pr_body="Closes #1509"
    )
    assert "guard.mod_guard" in result.unsatisfied


def test_local_mode_still_requires_quality_checks(git_repo: Path) -> None:
    # Keep local behavior intact: local mode still selects the ci.yml quality
    # matrix as the CI-equivalent preflight (not dropped like ci mode).
    _ci_ready_repo(git_repo)

    ledger = _ledger(task_kind="feature", issues=[IssueRef(number=1509)], governance_touch=True)
    result = evaluator.reconcile(
        ledger=ledger,
        repo_root=git_repo,
        base="HEAD~1",
        head="HEAD",
        mode="local",
        run_checks=False,
    )
    # Quality checks remain in the required obligation set for local preflight.
    assert set(result.required_obligations.checks) & evaluator._CI_OWNED_QUALITY_CHECKS


# ---------------------------------------------------------------------------
# Reconcile event + mode equivalence.
# ---------------------------------------------------------------------------


def test_reconcile_event_is_appended(git_repo: Path) -> None:
    _add_change(git_repo, "src/scistudio/x.py")
    ledger = _ledger(declared_scope=DeclaredScope(include=["src/scistudio/**"]))
    evaluator.reconcile(ledger=ledger, repo_root=git_repo, base="HEAD~1", head="HEAD", mode="local", run_checks=False)
    evaluator.reconcile(ledger=ledger, repo_root=git_repo, base="HEAD~1", head="HEAD", mode="ci", run_checks=False)
    assert len(ledger.reconcile_events) == 2
    assert ledger.reconcile_events[0].mode == "local"
    assert ledger.reconcile_events[1].mode == "ci"


def test_local_and_ci_use_same_tier_for_same_diff(git_repo: Path) -> None:
    _add_change(git_repo, "src/scistudio/qa/governance/foo.py")
    ledger_local = _ledger(task_kind="maintenance")
    ledger_ci = _ledger(task_kind="maintenance")
    local = evaluator.reconcile(
        ledger=ledger_local, repo_root=git_repo, base="HEAD~1", head="HEAD", mode="local", run_checks=False
    )
    ci = evaluator.reconcile(
        ledger=ledger_ci, repo_root=git_repo, base="HEAD~1", head="HEAD", mode="ci", run_checks=False
    )
    assert local.strictness_tier == ci.strictness_tier


# ---------------------------------------------------------------------------
# Sanitization (§8).
# ---------------------------------------------------------------------------


def test_sanitizer_rejects_absolute_path_in_committed_event(tmp_path: Path) -> None:
    ledger = _ledger()
    ledger.check_events.append(
        CheckEvent(
            name="lint",
            command="ruff check .",
            covered_surface="python",
            status="fail",
            exit_code=1,
            summary=r"error in C:\Users\someone\repo\file.py",
        )
    )
    with pytest.raises(SanitizationError):
        io.write_ledger(tmp_path / "ledger.json", ledger)


def test_sanitizer_rejects_raw_log_ref_outside_local(tmp_path: Path) -> None:
    ledger = _ledger()
    ledger.check_events.append(
        CheckEvent(
            name="lint",
            command="ruff check .",
            covered_surface="python",
            status="fail",
            exit_code=1,
            raw_log_ref="src/leaked.log",
        )
    )
    with pytest.raises(SanitizationError):
        io.write_ledger(tmp_path / "ledger.json", ledger)


def test_sanitizer_allows_repo_relative_event(tmp_path: Path) -> None:
    ledger = _ledger()
    ledger.check_events.append(
        CheckEvent(
            name="lint",
            command="ruff check .",
            covered_surface="python",
            status="pass",
            exit_code=0,
            summary="clean",
            raw_log_ref=".workflow/local/logs/lint.log",
        )
    )
    # Should not raise.
    io.write_ledger(tmp_path / "ledger.json", ledger)


# ---------------------------------------------------------------------------
# Fix A: parity-gap classification — an env-parity cause is NOT a code failure.
# ---------------------------------------------------------------------------


def test_detect_parity_cause_classifies_missing_module() -> None:
    from scistudio.qa.governance.gate_record import checks

    out = "ImportError while importing test module\nE   ModuleNotFoundError: No module named 'pandas'\nerrors during collection"
    detail = checks.detect_parity_cause(out)
    assert detail is not None
    assert "pandas" in detail


def test_detect_parity_cause_ignores_genuine_assertion_failure() -> None:
    from scistudio.qa.governance.gate_record import checks

    out = "def test_x():\n>       assert 1 == 2\nE       assert 1 == 2\n1 failed in 0.01s"
    assert checks.detect_parity_cause(out) is None


def test_detect_parity_cause_ignores_missing_optional_module_in_skip_summary() -> None:
    from scistudio.qa.governance.gate_record import checks

    out = "\n".join(
        [
            "================================== FAILURES ===================================",
            "FAILED tests/example.py::test_real_failure - AssertionError: boom",
            "E   ValueError: Command executable not found: 'echo'. Ensure it is on PATH",
            "=========================== short test summary info ===========================",
            "SKIPPED [1] tests/plugins/test_phase11_skeleton.py: could not import 'skimage': No module named 'skimage'",
        ]
    )
    assert checks.detect_parity_cause(out) is None


def test_parity_gap_check_event_reports_distinctly_not_as_code_failure(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scistudio.qa.governance.gate_record import checks

    _add_change(git_repo, "src/scistudio/x.py")
    ledger = _ledger(
        declared_scope=DeclaredScope(include=["src/scistudio/**"]),
        issues=[IssueRef(number=1509, url="https://github.com/o/r/issues/1509")],
    )

    # Simulate a check whose nonzero exit is caused by a missing dependency CI
    # has (env-parity cause), NOT a code/assertion failure.
    def _fake_run_check(repo_root: Path, name: str, **_kw: object) -> CheckEvent:
        return CheckEvent(
            name=name,
            command="pytest -n auto",
            covered_surface="python",
            exit_code=2,
            status="fail",
            summary="parity gap: missing module: setuptools",
            parity_gap=True,
            parity_detail="missing module: setuptools",
        )

    monkeypatch.setattr(checks, "run_check", _fake_run_check)
    result = evaluator.reconcile(
        ledger=ledger, repo_root=git_repo, base="HEAD~1", head="HEAD", mode="pre-pr", run_checks=True
    )
    # Classified as a parity gap, fail closed for PR readiness, and NOT a
    # checks.<name> code failure.
    assert any("local environment is not CI-equivalent" in gap for gap in result.parity_gaps)
    assert any(item.startswith("parity.") for item in result.unsatisfied)
    assert not any(item.startswith("checks.") for item in result.unsatisfied)


def test_genuine_check_failure_still_reads_as_code_failure(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scistudio.qa.governance.gate_record import checks

    _add_change(git_repo, "src/scistudio/x.py")
    ledger = _ledger(
        declared_scope=DeclaredScope(include=["src/scistudio/**"]),
        issues=[IssueRef(number=1509, url="https://github.com/o/r/issues/1509")],
    )

    def _fake_run_check(repo_root: Path, name: str, **_kw: object) -> CheckEvent:
        return CheckEvent(
            name=name, command="ruff check .", covered_surface="python", exit_code=1, status="fail", summary="exit 1"
        )

    monkeypatch.setattr(checks, "run_check", _fake_run_check)
    result = evaluator.reconcile(
        ledger=ledger, repo_root=git_repo, base="HEAD~1", head="HEAD", mode="local", run_checks=True
    )
    # A genuine failure stays a code failure, not a parity gap.
    assert any(item.startswith("checks.") for item in result.unsatisfied)
    assert not result.parity_gaps


# ---------------------------------------------------------------------------
# Fix B: --check-na for a ci.yml-owned check has no force.
# ---------------------------------------------------------------------------


def test_check_na_for_ci_owned_check_warns_and_does_not_waive(git_repo: Path) -> None:
    from scistudio.qa.governance.gate_record.ledger import CheckNa

    _add_change(git_repo, "src/scistudio/x.py")
    ledger = _ledger(
        declared_scope=DeclaredScope(include=["src/scistudio/**"]),
        issues=[IssueRef(number=1509, url="https://github.com/o/r/issues/1509")],
    )
    ledger.check_na.append(CheckNa(name="python_tests", rationale="no time"))
    result = evaluator.reconcile(
        ledger=ledger, repo_root=git_repo, base="HEAD~1", head="HEAD", mode="local", run_checks=False
    )
    # Loud warning emitted; the N/A has no force for the ci.yml-owned check.
    assert any("python_tests" in w and "NO force" in w for w in result.warnings)


def test_check_na_for_non_ci_owned_check_still_waives(git_repo: Path) -> None:
    from scistudio.qa.governance.gate_record.ledger import CheckNa

    _add_change(git_repo, "src/scistudio/x.py")
    ledger = _ledger(
        declared_scope=DeclaredScope(include=["src/scistudio/**"]),
        issues=[IssueRef(number=1509, url="https://github.com/o/r/issues/1509")],
    )
    # A task-specific (non-ci-owned) check name is waivable without a warning.
    ledger.check_na.append(CheckNa(name="my_custom_task_check", rationale="not relevant here"))
    result = evaluator.reconcile(
        ledger=ledger, repo_root=git_repo, base="HEAD~1", head="HEAD", mode="local", run_checks=False
    )
    assert not any("my_custom_task_check" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# Codex P1 #3: a REQUIRED check that comes back "skipped" must fail closed for
# PR readiness (not be silently passed). Not double-counted with a parity gap.
# ---------------------------------------------------------------------------


def test_required_skipped_check_is_unsatisfied_in_pr_readiness(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scistudio.qa.governance.gate_record import checks

    _add_change(git_repo, "src/scistudio/x.py")
    ledger = _ledger(
        declared_scope=DeclaredScope(include=["src/scistudio/**"]),
        issues=[IssueRef(number=1509, url="https://github.com/o/r/issues/1509")],
    )

    # The tool is genuinely unavailable -> run_check returns status="skipped"
    # (NOT a parity-gap fail, NOT an explicit --check-na).
    def _fake_run_check(repo_root: Path, name: str, **_kw: object) -> CheckEvent:
        return CheckEvent(
            name=name,
            command="ruff check .",
            covered_surface="python",
            exit_code=None,
            status="skipped",
            summary="tool unavailable: ruff",
        )

    monkeypatch.setattr(checks, "run_check", _fake_run_check)
    result = evaluator.reconcile(
        ledger=ledger, repo_root=git_repo, base="HEAD~1", head="HEAD", mode="pre-pr", run_checks=True
    )
    # The skipped required check is unsatisfied (fail closed), with a repair hint,
    # and is NOT recorded as a parity gap (no double counting).
    assert any(item.startswith("checks.") for item in result.unsatisfied), result.unsatisfied
    assert any("SKIPPED" in h for h in result.repair_hints)
    assert not result.parity_gaps


def test_required_skipped_check_does_not_block_local_wip(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scistudio.qa.governance.gate_record import checks

    _add_change(git_repo, "src/scistudio/x.py")
    ledger = _ledger(
        declared_scope=DeclaredScope(include=["src/scistudio/**"]),
        issues=[IssueRef(number=1509, url="https://github.com/o/r/issues/1509")],
    )

    def _fake_run_check(repo_root: Path, name: str, **_kw: object) -> CheckEvent:
        return CheckEvent(
            name=name,
            command="ruff check .",
            covered_surface="python",
            exit_code=None,
            status="skipped",
            summary="tool unavailable: ruff",
        )

    monkeypatch.setattr(checks, "run_check", _fake_run_check)
    # A non-PR-readiness local invocation records the event but does not block on
    # the skipped check (§3.4): no checks.<name> obligation is added.
    result = evaluator.reconcile(
        ledger=ledger, repo_root=git_repo, base="HEAD~1", head="HEAD", mode="local", run_checks=True
    )
    assert not any(item.startswith("checks.") for item in result.unsatisfied), result.unsatisfied


def test_required_skipped_check_waived_by_na(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scistudio.qa.governance.gate_record import checks
    from scistudio.qa.governance.gate_record.ledger import CheckNa

    _add_change(git_repo, "src/scistudio/x.py")
    ledger = _ledger(
        declared_scope=DeclaredScope(include=["src/scistudio/**"]),
        issues=[IssueRef(number=1509, url="https://github.com/o/r/issues/1509")],
    )
    # A non-ci-owned check with an explicit N/A is removed from ``to_run`` before
    # execution, so a skip there is never even produced -> no unsatisfied entry.
    ledger.check_na.append(CheckNa(name="my_custom_task_check", rationale="not relevant"))

    def _fake_run_check(repo_root: Path, name: str, **_kw: object) -> CheckEvent:
        # Should not be called for the N/A check; guard the test anyway.
        return CheckEvent(
            name=name, command="x", covered_surface="python", exit_code=None, status="skipped", summary="unavailable"
        )

    monkeypatch.setattr(checks, "run_check", _fake_run_check)
    result = evaluator.reconcile(
        ledger=ledger, repo_root=git_repo, base="HEAD~1", head="HEAD", mode="pre-pr", run_checks=True
    )
    assert "checks.my_custom_task_check" not in result.unsatisfied


def test_frontend_check_runs_in_frontend_working_directory(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], Path]] = []

    def _fake_run(
        argv: list[str],
        *,
        cwd: Path,
        env: dict[str, str] | None,
        capture_output: bool,
        text: bool,
        encoding: str,
        errors: str,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        calls.append((argv, cwd))
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(checks.parity, "resolve_venv_executable", lambda _repo, _tool: None)
    monkeypatch.setattr(checks.shutil, "which", lambda tool: tool if tool == "npm" else None)
    monkeypatch.setattr(checks.subprocess, "run", _fake_run)

    event = checks.run_check(
        git_repo,
        "frontend",
        changed_files=["frontend/src/App.tsx"],
        diff_fingerprint=None,
    )

    assert event.status == "pass"
    assert event.command == "(cd frontend && npm run lint)"
    assert calls == [(["npm", "run", "lint"], git_repo / "frontend")]


# ---------------------------------------------------------------------------
# Codex P1 #2: a maintainer-applied admin label in the CI PR context must reach
# the core/human/merge guards as provenance-carrying observed labels. Wired via
# reconcile(pr_context=...) -> GuardInputs.observed_admin_labels + pr_context.
# ---------------------------------------------------------------------------


def test_core_change_authorized_by_admin_provenance_label_in_ci(git_repo: Path) -> None:
    # A protected-core change is BLOCKED in ci with no label/context...
    _add_change(git_repo, "src/scistudio/core/foo.py")
    ledger = _ledger(task_kind="bugfix", declared_scope=DeclaredScope(include=["src/scistudio/**"]))
    blocked = evaluator.reconcile(
        ledger=ledger, repo_root=git_repo, base="HEAD~1", head="HEAD", mode="ci", run_checks=False
    )
    assert "guard.core_change_guard" in blocked.unsatisfied

    # ...and AUTHORIZED when the CI PR context carries an admin-applied
    # admin-approved:core-change label (provenance verified in the workflow).
    ledger_ok = _ledger(task_kind="bugfix", declared_scope=DeclaredScope(include=["src/scistudio/**"]))
    authorized = evaluator.reconcile(
        ledger=ledger_ok,
        repo_root=git_repo,
        base="HEAD~1",
        head="HEAD",
        mode="ci",
        run_checks=False,
        pr_context={
            "labels": [{"name": "admin-approved:core-change", "actor": "owner", "permission": "admin"}],
        },
    )
    assert "guard.core_change_guard" not in authorized.unsatisfied


def test_core_change_label_by_non_admin_actor_does_not_authorize(git_repo: Path) -> None:
    _add_change(git_repo, "src/scistudio/core/foo.py")
    ledger = _ledger(task_kind="bugfix", declared_scope=DeclaredScope(include=["src/scistudio/**"]))
    result = evaluator.reconcile(
        ledger=ledger,
        repo_root=git_repo,
        base="HEAD~1",
        head="HEAD",
        mode="ci",
        run_checks=False,
        pr_context={
            "labels": [{"name": "admin-approved:core-change", "actor": "drive-by", "permission": "read"}],
        },
    )
    # A non-admin actor's label carries insufficient provenance -> still blocks.
    assert "guard.core_change_guard" in result.unsatisfied


def test_human_bypass_authorized_by_admin_provenance_label_in_ci(git_repo: Path) -> None:
    # An AI-runtime PR with human-authored only is blocked; adding an
    # admin-applied admin-approved:bypass label clears human_bypass_guard.
    _add_change(git_repo, "src/scistudio/x.py")
    blocked_ledger = _ledger(runtime="claude-code", declared_scope=DeclaredScope(include=["src/scistudio/**"]))
    blocked = evaluator.reconcile(
        ledger=blocked_ledger,
        repo_root=git_repo,
        base="HEAD~1",
        head="HEAD",
        mode="ci",
        run_checks=False,
        pr_context={"labels": [{"name": "human-authored", "actor": "owner", "permission": "admin"}]},
    )
    assert "guard.human_bypass_guard" in blocked.unsatisfied

    ok_ledger = _ledger(runtime="claude-code", declared_scope=DeclaredScope(include=["src/scistudio/**"]))
    authorized = evaluator.reconcile(
        ledger=ok_ledger,
        repo_root=git_repo,
        base="HEAD~1",
        head="HEAD",
        mode="ci",
        run_checks=False,
        pr_context={
            "labels": [
                {"name": "human-authored", "actor": "owner", "permission": "admin"},
                {"name": "admin-approved:bypass", "actor": "owner", "permission": "admin"},
            ]
        },
    )
    assert "guard.human_bypass_guard" not in authorized.unsatisfied


def test_human_bypass_label_by_non_admin_actor_does_not_authorize(git_repo: Path) -> None:
    _add_change(git_repo, "src/scistudio/x.py")
    ledger = _ledger(runtime="claude-code", declared_scope=DeclaredScope(include=["src/scistudio/**"]))
    result = evaluator.reconcile(
        ledger=ledger,
        repo_root=git_repo,
        base="HEAD~1",
        head="HEAD",
        mode="ci",
        run_checks=False,
        pr_context={"labels": [{"name": "admin-approved:bypass", "actor": "drive-by", "permission": "read"}]},
    )
    # An override label without admin provenance is unauthorized -> blocks.
    assert "guard.human_bypass_guard" in result.unsatisfied


def test_pr_merge_authorized_by_admin_provenance_label_in_ci(git_repo: Path) -> None:
    # AI merge automation is blocked without an authorized merge label...
    _add_change(git_repo, "src/scistudio/x.py")
    blocked_ledger = _ledger(declared_scope=DeclaredScope(include=["src/scistudio/**"]))
    blocked = evaluator.reconcile(
        ledger=blocked_ledger,
        repo_root=git_repo,
        base="HEAD~1",
        head="HEAD",
        mode="ci",
        run_checks=False,
        pr_context={"merge_intent": "merge", "is_ai_actor": True, "labels": []},
    )
    assert "guard.pr_merge_guard" in blocked.unsatisfied

    # ...and authorized with an admin-applied admin-approved:merge label.
    ok_ledger = _ledger(declared_scope=DeclaredScope(include=["src/scistudio/**"]))
    authorized = evaluator.reconcile(
        ledger=ok_ledger,
        repo_root=git_repo,
        base="HEAD~1",
        head="HEAD",
        mode="ci",
        run_checks=False,
        pr_context={
            "merge_intent": "merge",
            "is_ai_actor": True,
            "labels": [{"name": "admin-approved:merge", "actor": "owner", "permission": "maintain"}],
        },
    )
    assert "guard.pr_merge_guard" not in authorized.unsatisfied


def test_observed_labels_from_context_carry_provenance() -> None:
    # Unit-level: the evaluator helper turns CI context labels into
    # provenance-carrying AdminLabels and merges them with the ledger set.
    from scistudio.qa.governance.gate_record.ledger import AdminLabel

    context = {
        "labels": [
            {"name": "admin-approved:core-change", "actor": "owner", "permission": "admin"},
            {"name": "no-name-entry"},  # kept (has name)
            {"bad": "entry"},  # dropped (no name)
        ]
    }
    built = evaluator._observed_labels_from_context(context)
    by_name = {label.name: label for label in built}
    assert by_name["admin-approved:core-change"].actor_permission == "admin"
    assert by_name["admin-approved:core-change"].applied_by == "owner"

    # Merge: a context label of the same name overrides the ledger entry's
    # (missing) provenance; ledger-only names are kept.
    merged = evaluator._merge_observed_labels(
        [AdminLabel(name="admin-approved:core-change"), AdminLabel(name="ledger-only")],
        built,
    )
    merged_by_name = {label.name: label for label in merged}
    assert merged_by_name["admin-approved:core-change"].actor_permission == "admin"
    assert "ledger-only" in merged_by_name


def test_no_pr_context_leaves_outcome_unchanged(git_repo: Path) -> None:
    # A PR with no labels/context behaves exactly as before: a clean
    # non-protected-core change has no core/human/merge guard block.
    _add_change(git_repo, "src/scistudio/x.py")
    ledger = _ledger(
        declared_scope=DeclaredScope(include=["src/scistudio/**"]),
        issues=[IssueRef(number=1509, url="https://github.com/o/r/issues/1509")],
    )
    result = evaluator.reconcile(
        ledger=ledger,
        repo_root=git_repo,
        base="HEAD~1",
        head="HEAD",
        mode="ci",
        run_checks=False,
        pr_body="Closes #1509",
    )
    assert "guard.core_change_guard" not in result.unsatisfied
    assert "guard.human_bypass_guard" not in result.unsatisfied
    assert "guard.pr_merge_guard" not in result.unsatisfied
