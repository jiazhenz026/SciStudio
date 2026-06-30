"""Two-phase pytest runner that isolates xdist-fragile tests (#1896).

Most of the suite runs under ``pytest -n auto`` (xdist) for speed. A small set
of tests drive a real PTY / subprocess / daemon thread and are marked ``serial``
(see ``[tool.pytest.ini_options].markers`` in ``pyproject.toml``); under
parallel load they can leak a thread or hang uninterruptibly and crash an xdist
worker (#1867, #1896). This runner runs the parallel bulk first
(``-n auto -m "not serial"``), then the serial tests in-process
(``-n 0 -m serial``), so the fragile tests never share a worker with the rest of
the suite.

It is the gate-side (``gate_record`` ``python_tests`` check) single-command
equivalent of the two ``pytest`` invocations the CI ``test`` job runs inline
(``.github/workflows/ci.yml``). The weakened-CI guard requires the literal
``pytest`` token in the workflow, so CI keeps explicit ``pytest`` lines while the
gate runs ``python -m scistudio.qa.testing.run_python_tests``; both express the
same two-phase policy.

Coverage: when coverage is active (no ``--no-cov`` in the forwarded args), the
parallel phase writes a fresh dataset with ``--cov-fail-under=0`` (a partial run
must not trip the floor) and the serial phase appends with ``--cov-append`` so
the configured ``fail_under`` is evaluated against the combined dataset — the
gate's coverage floor is preserved across the split. If no serial test is
selected, the floor is re-asserted with ``coverage report`` (which reads
``[tool.coverage.report].fail_under``).

Forwarded args (e.g. ``--timeout=60 --timeout-method=thread`` or ``--no-cov``)
apply to both phases.

Exit code: the first phase that fails (nonzero, other than pytest's
"no tests collected" code 5) is returned; otherwise 0.
"""

from __future__ import annotations

import subprocess
import sys

# pytest's exit code when a phase's marker expression selects nothing.
_NO_TESTS_COLLECTED = 5


def _run(cmd: list[str]) -> int:
    # Fixed argv, no shell — the only inputs are this module's own phase flags
    # plus the gate/CI-supplied pytest options.
    return subprocess.run(cmd).returncode


def main(argv: list[str] | None = None) -> int:
    """Run the suite in a parallel phase then a serial phase.

    ``argv`` defaults to ``sys.argv[1:]``; every forwarded arg is applied to both
    phases. Returns a process exit code suitable for ``SystemExit``.
    """
    forwarded = list(sys.argv[1:] if argv is None else argv)
    coverage_active = "--no-cov" not in forwarded
    pytest = [sys.executable, "-m", "pytest"]

    parallel = [*pytest, "-n", "auto", "-m", "not serial", *forwarded]
    serial = [*pytest, "-n", "0", "-m", "serial", *forwarded]
    if coverage_active:
        # Partial parallel run must not trip the floor; the serial phase appends
        # and the configured ``fail_under`` is enforced on the combined dataset.
        parallel += ["--cov-fail-under=0"]
        serial += ["--cov-append"]

    rc = _run(parallel)
    if rc not in (0, _NO_TESTS_COLLECTED):
        return rc

    rc = _run(serial)
    if rc == _NO_TESTS_COLLECTED:
        # No serial test selected: the parallel phase suppressed the floor, so
        # re-assert it against the dataset already written. ``coverage report``
        # reads ``[tool.coverage.report].fail_under``.
        if coverage_active:
            return _run([sys.executable, "-m", "coverage", "report"])
        return 0
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
