"""A gate check that times out must not count as one that passed (#2253).

`gate_record` ran every check under a hardcoded `subprocess.run(timeout=600)`
and caught `TimeoutExpired` in the same `except (SubprocessError, OSError)` as a
check that could not be launched at all. Both were recorded as
`status="unknown"` / `"execution error: ..."`, and the evaluator's executing
path — the one `check` takes — treated anything that was not `fail` as
discharging its obligation. So on a machine where the Python suite takes longer
than ten minutes, `check --mode pre-pr` printed "reconciliation passed" on a
test run that never finished.

`finalize` never agreed: it reuses recorded evidence through
`checks.event_is_valid_for`, which has always required a `pass`, so it called
the identical event "missing or stale". Two commands, one ledger event, two
verdicts, and no terminating state for the prescribed workflow.

These tests hold the three halves of that: a timeout is its own recorded fact,
it leaves the obligation unsatisfied, and both commands say so. The budget is
configurable so the correct behaviour is survivable on a slow machine, and it
still defaults to the 600s that was hardcoded.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from scistudio.qa.governance.gate_record import checks, evaluator, io
from scistudio.qa.governance.gate_record.ledger import (
    CheckEvent,
    DeclaredScope,
    GateLedger,
    IssueRef,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """A throwaway git repo with one committed baseline and one Python change."""

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "test")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-q", "-m", "base")
    target = repo / "src" / "scistudio" / "x.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x = 1\n", encoding="utf-8")
    _git(repo, "add", "src/scistudio/x.py")
    _git(repo, "commit", "-q", "-m", "change")
    return repo


def _ledger() -> GateLedger:
    return GateLedger.model_validate(
        {
            "record_id": "2253-gate-timeout",
            "runtime": "claude-code",
            "task_kind": "bugfix",
            "persona": "implementer",
            "branch": "fix/2253-gate-timeout-not-satisfied",
            "owner_directive": "a timed-out check is not a passing check",
            "declared_scope": DeclaredScope(include=["src/scistudio/**"]),
            "issues": [IssueRef(number=2253, url="https://github.com/o/r/issues/2253")],
        }
    )


def _event_of_status(status: str, **overrides: Any) -> Any:
    """Build a fake ``run_check`` that returns one event of the given status.

    The stub echoes the ``input_fingerprint`` the evaluator computed, so the
    event it records is CURRENT for the observed diff. That matters: it removes
    staleness as an explanation, leaving ``status`` as the only thing the two
    reconciliation paths can be disagreeing about.
    """

    def _fake_run_check(_repo_root: Path, name: str, **kwargs: Any) -> CheckEvent:
        payload: dict[str, Any] = {
            "name": name,
            "command": "python -m scistudio.qa.testing.run_python_tests",
            "covered_surface": "python_tests",
            "scope": "repo",
            "input_fingerprint": kwargs.get("input_fingerprint"),
            "exit_code": None if status != "pass" else 0,
            "status": status,
            "summary": "timed out after 600s" if status == "timeout" else status,
        }
        payload.update(overrides)
        return CheckEvent.model_validate(payload)

    return _fake_run_check


def _check_names(unsatisfied: list[str]) -> list[str]:
    return [item for item in unsatisfied if item.startswith("checks.")]


# ---------------------------------------------------------------------------
# 1. A timeout is recorded as its own fact, distinguishable from a launch error.
# ---------------------------------------------------------------------------


def _run_check_with_subprocess(
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    raiser: Any,
) -> tuple[CheckEvent, dict[str, Any]]:
    """Run ``python_tests`` with ``subprocess.run`` replaced, capturing its kwargs."""

    seen: dict[str, Any] = {}

    def _fake_subprocess_run(argv: Any, **kwargs: Any) -> Any:
        seen.update(kwargs)
        seen["argv"] = argv
        raise raiser(kwargs.get("timeout"))

    monkeypatch.setattr(checks.subprocess, "run", _fake_subprocess_run)
    event = checks.run_check(
        repo_root,
        "python_tests",
        changed_files=["src/scistudio/x.py"],
        diff_fingerprint="deadbeef",
        input_fingerprint="deadbeef",
    )
    return event, seen


def test_a_timed_out_check_is_recorded_as_a_timeout_not_an_execution_error(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    event, _ = _run_check_with_subprocess(
        git_repo,
        monkeypatch,
        lambda budget: subprocess.TimeoutExpired(cmd="pytest", timeout=budget or 600),
    )

    assert event.status == "timeout"
    # The old wording. A timeout must never be reported as "we could not run it".
    assert "execution error" not in event.summary
    # The budget is in the summary so the reader knows which number to raise.
    assert "600" in event.summary
    assert checks.CHECK_TIMEOUT_ENV_VAR in event.summary
    assert event.exit_code is None


def test_a_check_that_cannot_be_launched_is_still_an_execution_error(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other branch keeps its own meaning; the two are told apart."""

    event, _ = _run_check_with_subprocess(
        git_repo,
        monkeypatch,
        lambda _budget: OSError("cannot spawn"),
    )

    assert event.status == "unknown"
    assert event.summary == "execution error: OSError"


def test_a_timed_out_check_keeps_whatever_it_printed_before_the_kill(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The partial transcript is the only clue a timed-out check leaves."""

    def _raiser(budget: float | None) -> subprocess.TimeoutExpired:
        return subprocess.TimeoutExpired(
            cmd="pytest",
            timeout=budget or 600,
            output="collected 9312 items\n",
            stderr="",
        )

    event, _ = _run_check_with_subprocess(git_repo, monkeypatch, _raiser)

    assert event.raw_log_ref is not None
    body = (git_repo / event.raw_log_ref).read_text(encoding="utf-8")
    assert "TIMED OUT" in body
    assert "collected 9312 items" in body


# ---------------------------------------------------------------------------
# 2. The budget is configurable and defaults to the 600s that was hardcoded.
# ---------------------------------------------------------------------------


def test_the_check_timeout_defaults_to_the_previously_hardcoded_600s(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(checks.CHECK_TIMEOUT_ENV_VAR, raising=False)

    assert checks.resolve_check_timeout() == 600.0
    assert checks.DEFAULT_CHECK_TIMEOUT_SECONDS == 600.0

    _, seen = _run_check_with_subprocess(
        git_repo,
        monkeypatch,
        lambda budget: subprocess.TimeoutExpired(cmd="pytest", timeout=budget or 600),
    )
    assert seen["timeout"] == 600.0


def test_the_check_timeout_is_honoured_when_set(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(checks.CHECK_TIMEOUT_ENV_VAR, "1800")

    assert checks.resolve_check_timeout() == 1800.0

    event, seen = _run_check_with_subprocess(
        git_repo,
        monkeypatch,
        lambda budget: subprocess.TimeoutExpired(cmd="pytest", timeout=budget or 0),
    )
    assert seen["timeout"] == 1800.0
    assert "1800" in event.summary


@pytest.mark.parametrize("raw", ["", "   ", "abc", "0", "-5", "nan", "inf"])
def test_an_unusable_timeout_value_falls_back_to_the_default(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    """A typo must neither remove the wall nor silently install an unintended one."""

    monkeypatch.setenv(checks.CHECK_TIMEOUT_ENV_VAR, raw)
    assert checks.resolve_check_timeout() == checks.DEFAULT_CHECK_TIMEOUT_SECONDS


# ---------------------------------------------------------------------------
# 3. A timed-out check leaves its obligation UNSATISFIED.
#    This is the test that fails without the fix: before it, the evaluator's
#    executing path fell through every status that was not "fail".
# ---------------------------------------------------------------------------


def test_a_timed_out_check_is_unsatisfied_in_pr_readiness(git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(checks, "run_check", _event_of_status("timeout"))

    result = evaluator.reconcile(
        ledger=_ledger(),
        repo_root=git_repo,
        base="HEAD~1",
        head="HEAD",
        mode="pre-pr",
        run_checks=True,
    )

    assert _check_names(result.unsatisfied), (
        "a check that timed out discharged its obligation; a run that never "
        f"finished is not a run that passed. unsatisfied={result.unsatisfied}"
    )
    assert any("TIMED OUT" in hint for hint in result.repair_hints)
    # The hint names the knob, because the honest fix for a slow machine is to
    # raise the budget rather than to stop believing the check.
    assert any(checks.CHECK_TIMEOUT_ENV_VAR in hint for hint in result.repair_hints)
    # A timeout is not an environment-parity gap; it must not be double-counted.
    assert not result.parity_gaps


def test_an_unrunnable_check_is_also_unsatisfied_in_pr_readiness(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``unknown`` was the original hole and closes with the same predicate."""

    monkeypatch.setattr(checks, "run_check", _event_of_status("unknown", summary="execution error: OSError"))

    result = evaluator.reconcile(
        ledger=_ledger(),
        repo_root=git_repo,
        base="HEAD~1",
        head="HEAD",
        mode="pre-pr",
        run_checks=True,
    )

    assert _check_names(result.unsatisfied), result.unsatisfied
    assert any("could NOT BE EXECUTED" in hint for hint in result.repair_hints)


def test_a_timed_out_check_does_not_block_a_local_wip_invocation(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail closed is a PR-readiness posture, as it already is for ``skipped``."""

    monkeypatch.setattr(checks, "run_check", _event_of_status("timeout"))

    result = evaluator.reconcile(
        ledger=_ledger(),
        repo_root=git_repo,
        base="HEAD~1",
        head="HEAD",
        mode="local",
        run_checks=True,
    )

    assert not _check_names(result.unsatisfied), result.unsatisfied


# ---------------------------------------------------------------------------
# 4. `check` and `finalize` reach the same verdict on the same event.
# ---------------------------------------------------------------------------


def _check_then_finalize(git_repo: Path, ledger: GateLedger) -> tuple[list[str], list[str]]:
    """Reconcile the way ``check`` does, then the way ``finalize`` does.

    ``check`` runs the checks (``run_checks=True``) and reads the event it just
    produced. ``finalize`` runs none (``run_checks=False``) and reads the same
    event back off the ledger. The two verdicts are what used to disagree.
    """

    check_result = evaluator.reconcile(
        ledger=ledger,
        repo_root=git_repo,
        base="HEAD~1",
        head="HEAD",
        mode="pre-pr",
        run_checks=True,
    )
    finalize_result = evaluator.reconcile(
        ledger=ledger,
        repo_root=git_repo,
        base="HEAD~1",
        head="HEAD",
        mode="pre-pr",
        run_checks=False,
    )
    return _check_names(check_result.unsatisfied), _check_names(finalize_result.unsatisfied)


def test_check_and_finalize_agree_that_a_timed_out_check_is_unsatisfied(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(checks, "run_check", _event_of_status("timeout"))
    ledger = _ledger()

    from_check, from_finalize = _check_then_finalize(git_repo, ledger)

    assert from_check == from_finalize, (
        "check and finalize disagree on the same ledger event: "
        f"check={from_check}, finalize={from_finalize}. This is the state that "
        "gave the workflow no terminating state on a slow machine."
    )
    assert from_check, "both agreed, but they agreed on the wrong answer"
    assert any(event.status == "timeout" for event in ledger.check_events)


def test_check_and_finalize_agree_that_a_passing_check_is_satisfied(
    git_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Positive control: the fix strengthens the unknown path and nothing else.

    A check that genuinely passed still discharges its obligation on both
    paths, which is what makes "no check became easier OR harder to satisfy
    when it actually ran" a claim with a test behind it rather than an
    assertion.
    """

    monkeypatch.setattr(checks, "run_check", _event_of_status("pass", summary="clean"))
    ledger = _ledger()

    from_check, from_finalize = _check_then_finalize(git_repo, ledger)

    assert from_check == [] == from_finalize, (from_check, from_finalize)


def test_the_two_paths_share_one_predicate(git_repo: Path) -> None:
    """The structural guarantee, not just the observed agreement.

    The two reconciliation paths drifted because each carried its own idea of
    what counted. They now both ask ``event_discharges_obligation``, so a new
    status cannot silently discharge an obligation on one path only.
    """

    fingerprint = io.diff_fingerprint(git_repo, "HEAD~1", "HEAD")
    for status in ("pass", "fail", "skipped", "unknown", "timeout"):
        event = CheckEvent.model_validate(
            {
                "name": "python_tests",
                "command": "python -m scistudio.qa.testing.run_python_tests",
                "covered_surface": "python_tests",
                "input_fingerprint": fingerprint,
                "exit_code": 0 if status == "pass" else None,
                "status": status,
            }
        )
        discharges = checks.event_discharges_obligation(event)
        reusable = checks.event_is_valid_for(event, input_fingerprint=fingerprint)
        assert discharges == reusable, status
        assert discharges is (status == "pass"), status
