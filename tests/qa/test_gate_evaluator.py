"""Tests for the ADR-042 Addendum 6 shared evaluator (spec §10.3/§10.4).

Covers: git-observed diff over agent declarations, tier derivation + observed-
diff escalation, obligation inference, claimed-but-unverified docs/test
reconciliation, sanitization, single-sentrux classifier, and guards-run-once.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scistudio.qa.governance.gate_record import evaluator, io, surfaces
from scistudio.qa.governance.gate_record.io import SanitizationError
from scistudio.qa.governance.gate_record.ledger import (
    CheckEvent,
    DeclaredScope,
    DocsEvent,
    GateLedger,
    TestEvent,
)


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
