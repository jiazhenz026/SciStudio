"""CI-mode reconciliation tests for ADR-042 Addendum 6 (spec §3.4 / §10.4).

Rewritten from the legacy ``validate_gate_record`` / ``check_pr`` assertions to
ledger-reconcile assertions against the single shared evaluator in ``--mode ci``.
Covers: issue closure from the PR body, scope reconciliation against the observed
diff, test-evidence obligation, sentrux advisory (opt-in) semantics, guard
aggregation, and ``test_engineer_scope_guard`` invocation — all through one
``reconcile()`` call with ``run_checks=False`` (check execution is exercised in
the CLI smoke / evaluator tests; here we assert reconciliation logic).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from scistudio.qa.governance.gate_record import evaluator
from scistudio.qa.governance.gate_record.ledger import (
    DeclaredScope,
    DocsEvent,
    GateLedger,
    IssueRef,
    TestEvent,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "test")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


def _commit(repo: Path, rel: str, content: str = "x\n") -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _git(repo, "add", rel)
    _git(repo, "commit", "-q", "-m", f"add {rel}")


def _ledger(**overrides: object) -> GateLedger:
    base: dict[str, object] = {
        "record_id": "1267-core",
        "runtime": "claude-code",
        "task_kind": "feature",
        "persona": "implementer",
        "branch": "feat/issue-1267",
        "owner_directive": "Implement gate-record core.",
        "issues": [IssueRef(number=1267, url="https://github.com/o/r/issues/1267")],
    }
    base.update(overrides)
    return GateLedger.model_validate(base)


def _reconcile(ledger: GateLedger, repo: Path, *, pr_body: str | None = None, mode: str = "ci"):
    return evaluator.reconcile(
        ledger=ledger,
        repo_root=repo,
        base="HEAD~1",
        head="HEAD",
        mode=mode,  # type: ignore[arg-type]
        pr_body=pr_body,
        run_checks=False,
    )


# ---------------------------------------------------------------------------
# Issue closure from the PR body (issue_link guard, ci mode).
# ---------------------------------------------------------------------------


def test_ci_pr_body_must_close_every_gate_issue(git_repo: Path) -> None:
    _commit(git_repo, "src/scistudio/x.py")
    ledger = _ledger(declared_scope=DeclaredScope(include=["src/scistudio/**"]))
    refs = _reconcile(ledger, git_repo, pr_body="Refs #1267")
    assert "guard.issue_link" in refs.unsatisfied
    assert any(f.rule_id == "issue_link.missing-closing-keyword" for f in refs.report.findings)

    ledger_ok = _ledger(declared_scope=DeclaredScope(include=["src/scistudio/**", "tests/**"]))
    ledger_ok.docs_events.append(
        DocsEvent.model_validate({"kind": "na", "class": "implementation", "rationale": "internal"})
    )
    ledger_ok.test_events.append(TestEvent(kind="path", path="src/scistudio/x.py"))
    closes = _reconcile(ledger_ok, git_repo, pr_body="Closes #1267")
    assert "guard.issue_link" not in closes.unsatisfied


def test_ci_multiple_issues_must_all_close(git_repo: Path) -> None:
    _commit(git_repo, "src/scistudio/x.py")
    ledger = _ledger(
        declared_scope=DeclaredScope(include=["src/scistudio/**"]),
        issues=[
            IssueRef(number=1267, url="https://github.com/o/r/issues/1267"),
            IssueRef(number=1266, url="https://github.com/o/r/issues/1266"),
        ],
    )
    result = _reconcile(ledger, git_repo, pr_body="Closes #1267")
    # 1266 is not closed -> issue_link blocks.
    assert any(
        f.rule_id == "issue_link.missing-closing-keyword" and f.evidence.get("issue_number") == 1266
        for f in result.report.findings
    )


# ---------------------------------------------------------------------------
# Scope reconciliation against the observed diff.
# ---------------------------------------------------------------------------


def test_ci_scope_rejects_out_of_scope_and_excluded_files(git_repo: Path) -> None:
    _commit(git_repo, "src/scistudio/core/secret.py")
    ledger = _ledger(
        declared_scope=DeclaredScope(include=["src/scistudio/api/**"], exclude=["src/scistudio/core/**"]),
    )
    result = _reconcile(ledger, git_repo, pr_body="Closes #1267")
    assert any(f.rule_id == "scope.out-of-scope" for f in result.report.findings)


def test_ci_scope_expansion_via_directive_allows_file(git_repo: Path) -> None:
    from scistudio.qa.governance.gate_record.ledger import ScopeEvent

    _commit(git_repo, "src/scistudio/core/allowed.py")
    ledger = _ledger(declared_scope=DeclaredScope(include=["src/scistudio/api/**"]))
    # An owner-directed scope expansion (recorded as an append-only scope event).
    ledger.scope_events.append(ScopeEvent(action="add-include", pattern="src/scistudio/core/**", reason="owner"))
    result = _reconcile(ledger, git_repo, pr_body="Closes #1267")
    assert not any(f.rule_id == "scope.out-of-scope" for f in result.report.findings)


# ---------------------------------------------------------------------------
# Test-evidence obligation.
# ---------------------------------------------------------------------------


def test_ci_implementation_change_requires_changed_test(git_repo: Path) -> None:
    _commit(git_repo, "src/scistudio/qa/governance/x.py")
    ledger = _ledger(
        task_kind="bugfix",
        declared_scope=DeclaredScope(include=["src/scistudio/**"]),
    )
    ledger.docs_events.append(
        DocsEvent.model_validate({"kind": "na", "class": "implementation", "rationale": "internal"})
    )
    result = _reconcile(ledger, git_repo, pr_body="Closes #1267")
    assert "tests.changed_test_required" in result.unsatisfied


def test_ci_docs_task_without_implementation_does_not_require_tests(git_repo: Path) -> None:
    _commit(git_repo, "docs/contributing/guide.md")
    ledger = _ledger(
        task_kind="docs",
        persona="adr_author",
        declared_scope=DeclaredScope(include=["docs/**"]),
    )
    ledger.docs_events.append(DocsEvent(kind="path", path="docs/contributing/guide.md"))
    result = _reconcile(ledger, git_repo, pr_body="Closes #1267")
    assert "tests.changed_test_required" not in result.unsatisfied


# ---------------------------------------------------------------------------
# Sentrux advisory (opt-in) + recorded-failure block.
# ---------------------------------------------------------------------------


def test_ci_sentrux_missing_evidence_is_advisory_not_block(git_repo: Path) -> None:
    _commit(git_repo, "src/scistudio/x.py")
    ledger = _ledger(declared_scope=DeclaredScope(include=["src/scistudio/**"]))
    result = _reconcile(ledger, git_repo, pr_body="Closes #1267")
    # Missing sentrux evidence is advisory (INFO), never a hard block.
    assert "guard.sentrux_gate" not in result.unsatisfied


def test_ci_recorded_sentrux_failure_blocks(git_repo: Path) -> None:
    from scistudio.qa.governance.gate_record.ledger import CheckEvent

    _commit(git_repo, "src/scistudio/x.py")
    ledger = _ledger(declared_scope=DeclaredScope(include=["src/scistudio/**"]))
    ledger.check_events.append(
        CheckEvent(
            name="sentrux",
            command="sentrux check",
            covered_surface="sentrux",
            status="pass",
            exit_code=0,
            summary='{"mode": "free-tier", "status": "fail", "rules_checked": 5}',
        )
    )
    result = _reconcile(ledger, git_repo, pr_body="Closes #1267")
    assert "guard.sentrux_gate" in result.unsatisfied
    assert any(f.rule_id == "sentrux.free_tier.not-passing" for f in result.report.findings)


# ---------------------------------------------------------------------------
# Guard aggregation + test_engineer_scope_guard invocation.
# ---------------------------------------------------------------------------


def test_ci_aggregates_all_guards_each_once(git_repo: Path) -> None:
    _commit(git_repo, "src/scistudio/x.py")
    ledger = _ledger(declared_scope=DeclaredScope(include=["src/scistudio/**"]))
    result = _reconcile(ledger, git_repo, pr_body="Closes #1267")
    guard_names = [e.guard for e in result.guard_events]
    assert sorted(guard_names) == sorted(evaluator.GUARD_REGISTRY.keys())
    assert len(guard_names) == len(set(guard_names))


def test_ci_test_engineer_scope_guard_blocks_production_change(git_repo: Path) -> None:
    _commit(git_repo, "src/scistudio/core/x.py")
    ledger = _ledger(
        task_kind="bugfix",
        persona="test_engineer",
        declared_scope=DeclaredScope(include=["src/scistudio/**"]),
    )
    result = _reconcile(ledger, git_repo, pr_body="Closes #1267")
    assert "guard.test_engineer_scope_guard" in result.unsatisfied
    assert any(f.rule_id == "test_engineer_scope_guard.blocked-path" for f in result.report.findings)
