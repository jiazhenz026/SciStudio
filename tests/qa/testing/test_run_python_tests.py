"""Unit tests for the two-phase pytest runner (#1896).

``subprocess.run`` is stubbed so these tests assert the runner's phase
composition and exit-code logic without actually invoking pytest. Every call
names an explicit target: outside CI a target-less run is refused (#2386).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from scistudio.qa.testing import run_python_tests


class _FakeCompleted:
    def __init__(self, returncode: int) -> None:
        self.returncode = returncode


@pytest.fixture(autouse=True)
def _outside_ci(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CI", raising=False)


@pytest.fixture
def record_runs(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[list[list[str]], list[int]]]:
    """Record each ``subprocess.run`` argv; return rc from a scripted queue."""
    calls: list[list[str]] = []
    rcs: list[int] = []

    def _fake_run(cmd: list[str], *_a: object, **_k: object) -> _FakeCompleted:
        calls.append(list(cmd))
        return _FakeCompleted(rcs.pop(0) if rcs else 0)

    monkeypatch.setattr(run_python_tests.subprocess, "run", _fake_run)
    yield calls, rcs


def test_coverage_path_composes_two_phases(record_runs: tuple[list[list[str]], list[int]]) -> None:
    calls, rcs = record_runs
    rcs.extend([0, 0])

    rc = run_python_tests.main(["--timeout=60", "--timeout-method=thread", "tests/qa"])

    assert rc == 0
    assert len(calls) == 2
    parallel, serial = calls
    # Phase 1: parallel, deselect serial, suppress the floor on the partial run.
    assert parallel[1:3] == ["-m", "pytest"]
    assert "-n" in parallel and parallel[parallel.index("-n") + 1] == "auto"
    assert "not serial" in parallel
    assert "--cov-fail-under=0" in parallel
    assert "--timeout=60" in parallel
    # Phase 2: serial, in-process, append coverage so the combined floor holds.
    assert "-n" in serial and serial[serial.index("-n") + 1] == "0"
    assert "serial" in serial and "not serial" not in serial
    assert "--cov-append" in serial
    assert "--cov-fail-under=0" not in serial


def test_no_cov_path_omits_coverage_flags(record_runs: tuple[list[list[str]], list[int]]) -> None:
    calls, rcs = record_runs
    rcs.extend([0, 0])

    rc = run_python_tests.main(["--no-cov", "--timeout=60", "tests/qa"])

    assert rc == 0
    parallel, serial = calls
    assert "--cov-fail-under=0" not in parallel
    assert "--cov-append" not in serial
    assert "--no-cov" in parallel and "--no-cov" in serial


def test_parallel_failure_short_circuits(record_runs: tuple[list[list[str]], list[int]]) -> None:
    calls, rcs = record_runs
    rcs.extend([1])  # parallel phase fails

    rc = run_python_tests.main(["--no-cov", "tests/qa"])

    assert rc == 1
    assert len(calls) == 1  # serial phase never runs


def test_parallel_no_tests_collected_continues(record_runs: tuple[list[list[str]], list[int]]) -> None:
    calls, rcs = record_runs
    rcs.extend([5, 0])  # parallel collects nothing (exit 5), serial passes

    rc = run_python_tests.main(["--no-cov", "tests/qa"])

    assert rc == 0
    assert len(calls) == 2


def test_empty_serial_reasserts_coverage_floor(record_runs: tuple[list[list[str]], list[int]]) -> None:
    calls, rcs = record_runs
    rcs.extend([0, 5, 0])  # parallel passes, serial collects nothing, coverage report passes

    rc = run_python_tests.main(["--timeout=60", "tests/qa"])

    assert rc == 0
    assert len(calls) == 3
    assert calls[2][1:3] == ["-m", "coverage"]
    assert calls[2][3] == "report"


def test_empty_serial_without_coverage_returns_zero(record_runs: tuple[list[list[str]], list[int]]) -> None:
    calls, rcs = record_runs
    rcs.extend([0, 5])  # parallel passes, serial collects nothing, no coverage

    rc = run_python_tests.main(["--no-cov", "tests/qa"])

    assert rc == 0
    assert len(calls) == 2  # no coverage-report fallback when --no-cov


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param([], id="no-args"),
        pytest.param(["--timeout=60", "--timeout-method=thread"], id="options-only"),
        pytest.param(["--no-cov", "tests"], id="whole-tests-tree"),
        pytest.param(["--no-cov", "."], id="repo-root"),
    ],
)
def test_whole_suite_run_is_refused_outside_ci(
    record_runs: tuple[list[list[str]], list[int]], argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    """#2386: the full Python suite never runs locally; no pytest process starts."""
    calls, _rcs = record_runs

    rc = run_python_tests.main(argv)

    assert rc == 4
    assert calls == []
    assert "#2386" in capsys.readouterr().err


def test_target_less_run_is_allowed_in_ci(
    record_runs: tuple[list[list[str]], list[int]], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls, rcs = record_runs
    rcs.extend([0, 0])
    monkeypatch.setenv("CI", "true")

    assert run_python_tests.main(["--no-cov"]) == 0
    assert len(calls) == 2
