from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scistudio.qa.audit.facts import load_facts, write_facts

REPO_ROOT = Path(__file__).resolve().parents[2]

GENERATED_AT = "2026-05-19T00:00:00+00:00"
SOURCE_SHA = "test-sha"


def _run_generate_facts(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/audit/generate_facts.py", *args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.fixture(scope="module")
def written_facts(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A registry written once by the real CLI, shared by this module.

    ``--write`` walks the whole package with griffe, which is the dominant
    cost of this file. Both tests below need a CLI-written registry and
    neither depends on having written its own, so one ``--write`` run serves
    both (#2253: the parallel CI phase ran out its wall).
    """

    facts_path = tmp_path_factory.mktemp("facts") / "generated.yaml"
    result = _run_generate_facts(
        "--write",
        "--facts-path",
        str(facts_path),
        "--source-sha",
        SOURCE_SHA,
        "--generated-at",
        GENERATED_AT,
    )
    assert result.returncode == 0, result.stderr
    return facts_path


# Serial, and cheap. Two agents fixed this file for two different reasons and
# both fixes are kept: the module-scoped fixture above spawns the griffe walk
# once instead of twice (#2253, the cost), and this mark keeps that one walk out
# of the parallel phase (#1867, #1896, the crash — the worker hosting a
# repo-walking subprocess dies with "node down: Not properly terminated" and
# takes unrelated tests with it). Neither substitutes for the other, and a green
# local run is not evidence that ``-n auto`` can host this.
@pytest.mark.serial
def test_generate_facts_write_and_check_round_trip(written_facts: Path) -> None:
    registry = load_facts(written_facts)
    assert registry.source_sha == SOURCE_SHA
    assert registry.find(kind="symbol")

    check_result = _run_generate_facts(
        "--check",
        "--facts-path",
        str(written_facts),
        "--source-sha",
        SOURCE_SHA,
        "--generated-at",
        GENERATED_AT,
    )

    assert check_result.returncode == 0, check_result.stderr


@pytest.mark.serial
def test_generate_facts_check_reports_stale_file(written_facts: Path, tmp_path: Path) -> None:
    stale_path = tmp_path / "generated.yaml"
    stale = load_facts(written_facts).model_copy(update={"source_sha": "stale-sha"})
    write_facts(stale, stale_path)

    result = _run_generate_facts(
        "--check",
        "--facts-path",
        str(stale_path),
        "--source-sha",
        SOURCE_SHA,
        "--generated-at",
        GENERATED_AT,
    )

    assert result.returncode == 1
    assert "generated facts registry is stale" in result.stderr
