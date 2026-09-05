from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scistudio.qa.audit.facts import load_facts

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_generate_facts(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/audit/generate_facts.py", *args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


# Serial: this spawns ``scripts/audit/generate_facts.py`` as a subprocess that
# walks the whole repository. Under ``-n auto`` the worker hosting it dies
# (``node down: Not properly terminated``) and takes unrelated tests with it —
# the class ``pyproject.toml`` marks serial (#1867, #1896). Do not remove the
# mark; it passes in isolation either way, so a green local run is not evidence
# that the parallel phase can host it.
@pytest.mark.serial
def test_generate_facts_write_and_check_round_trip(tmp_path: Path) -> None:
    facts_path = tmp_path / "generated.yaml"

    write_result = _run_generate_facts(
        "--write",
        "--facts-path",
        str(facts_path),
        "--source-sha",
        "test-sha",
        "--generated-at",
        "2026-05-19T00:00:00+00:00",
    )

    assert write_result.returncode == 0, write_result.stderr
    registry = load_facts(facts_path)
    assert registry.source_sha == "test-sha"
    assert registry.find(kind="symbol")

    check_result = _run_generate_facts(
        "--check",
        "--facts-path",
        str(facts_path),
        "--source-sha",
        "test-sha",
        "--generated-at",
        "2026-05-19T00:00:00+00:00",
    )

    assert check_result.returncode == 0, check_result.stderr


def test_generate_facts_check_reports_stale_file(tmp_path: Path) -> None:
    facts_path = tmp_path / "generated.yaml"

    write_result = _run_generate_facts(
        "--write",
        "--facts-path",
        str(facts_path),
        "--source-sha",
        "stale-sha",
        "--generated-at",
        "2026-05-19T00:00:00+00:00",
    )
    assert write_result.returncode == 0, write_result.stderr

    result = _run_generate_facts(
        "--check",
        "--facts-path",
        str(facts_path),
        "--source-sha",
        "test-sha",
        "--generated-at",
        "2026-05-19T00:00:00+00:00",
    )

    assert result.returncode == 1
    assert "generated facts registry is stale" in result.stderr
