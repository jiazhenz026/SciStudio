"""Guard GitHub Actions ``if:`` expressions against unavailable contexts (#2096).

GitHub only exposes a subset of expression contexts to each workflow key. An
``if:`` that reads a context it is not given is not a soft failure: GitHub
rejects the *entire workflow file* with ``Unrecognized named-value`` and the run
never starts, so a workflow that used to build stops building.

Two traps matter here, both hit while wiring macOS signing in #2096:

* ``secrets`` is unavailable in **any** ``if:`` — job-level or step-level.
  Map secret *presence* to a ``jobs.<id>.env`` flag (where ``secrets`` is
  available) and test that flag instead.
* ``env`` is unavailable in a **job-level** ``if:`` — it is only offered to
  step-level ones. So the fix above cannot simply be hoisted to the job.

Nothing else in this repository validates workflow files: there is no
actionlint hook and no CI job that parses them, and a ``workflow_dispatch``-only
workflow is never exercised by a pull request. These tests are the guard.

Reference: GitHub Actions "Contexts / Context availability".
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"

# Matches a `secrets.NAME` / `env.NAME` read inside an expression.
_SECRETS_READ = re.compile(r"\bsecrets\s*\.", re.IGNORECASE)
_ENV_READ = re.compile(r"\benv\s*\.", re.IGNORECASE)


def _workflow_files() -> list[Path]:
    return sorted(WORKFLOW_DIR.glob("*.yml")) + sorted(WORKFLOW_DIR.glob("*.yaml"))


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _jobs(doc: dict) -> dict:
    jobs = doc.get("jobs")
    return jobs if isinstance(jobs, dict) else {}


def _conditions(doc: dict) -> list[tuple[str, str, bool]]:
    """Every ``if:`` in the document as (location, expression, is_job_level)."""
    found: list[tuple[str, str, bool]] = []
    for job_id, job in _jobs(doc).items():
        if not isinstance(job, dict):
            continue
        if "if" in job:
            found.append((f"jobs.{job_id}.if", str(job["if"]), True))
        steps = job.get("steps")
        if not isinstance(steps, list):
            continue
        for index, step in enumerate(steps):
            if not isinstance(step, dict) or "if" not in step:
                continue
            name = step.get("name") or f"#{index}"
            found.append((f"jobs.{job_id}.steps[{name}].if", str(step["if"]), False))
    return found


def test_workflow_directory_is_discoverable() -> None:
    # A silent glob miss would make every test below vacuously pass.
    assert _workflow_files(), f"no workflow files found under {WORKFLOW_DIR}"


@pytest.mark.parametrize("path", _workflow_files(), ids=lambda p: p.name)
def test_no_secrets_context_in_any_if(path: Path) -> None:
    """``secrets`` in an ``if:`` makes GitHub reject the whole workflow."""
    offenders = [
        f"{location}: {expression}"
        for location, expression, _ in _conditions(_load(path))
        if _SECRETS_READ.search(expression)
    ]
    assert not offenders, (
        f"{path.name}: the `secrets` context is not available in `if:` conditions, and "
        "GitHub rejects the entire workflow with \"Unrecognized named-value: 'secrets'\" "
        "rather than skipping the step. Map the secret to a `jobs.<id>.env` flag and "
        "condition on `env.<FLAG> == 'true'` instead.\n  " + "\n  ".join(offenders)
    )


@pytest.mark.parametrize("path", _workflow_files(), ids=lambda p: p.name)
def test_no_env_context_in_a_job_level_if(path: Path) -> None:
    """``env`` reaches a step-level ``if:`` but never a job-level one."""
    offenders = [
        f"{location}: {expression}"
        for location, expression, is_job_level in _conditions(_load(path))
        if is_job_level and _ENV_READ.search(expression)
    ]
    assert not offenders, (
        f"{path.name}: the `env` context is not available in a job-level `if:` (only in a "
        "step-level one), so this is the same rejected-workflow failure. Use `needs`, "
        "`github`, `vars`, or `inputs` at the job level.\n  " + "\n  ".join(offenders)
    )


# --------------------------------------------------------------------------- #
# Retired runner images (#2165)
# --------------------------------------------------------------------------- #
# GitHub keeps only the latest two versions of each OS image. A workflow pinned
# to a retired label does not degrade to a newer one -- the job never gets a
# runner and fails with nothing to go on. The macOS Intel leg was written
# against `macos-13` and that image was retired before the PR landed, so the
# feature would have shipped dead.
#
# This is the same blind spot as the `if:` guards above: `workflow_dispatch`
# build workflows are never exercised by a pull request, so nothing else in the
# repository would notice.
RETIRED_RUNNER_LABELS = frozenset(
    {
        "macos-10.15",
        "macos-11",
        "macos-11-arm64",
        "macos-12",
        "macos-12-large",
        "macos-12-xlarge",
        "macos-13",
        "macos-13-large",
        "macos-13-xlarge",
        "ubuntu-18.04",
        "ubuntu-20.04",
        "windows-2016",
        "windows-2019",
    }
)


def _runs_on_labels(doc: dict) -> list[tuple[str, str]]:
    """Every literal runner label in the document as (location, label).

    Expressions such as ``${{ matrix.runner }}`` are skipped here and covered by
    the matrix walk below, which sees the values they resolve to.
    """
    found: list[tuple[str, str]] = []

    def collect(location: str, value: object) -> None:
        if isinstance(value, str):
            if "${{" not in value:
                found.append((location, value))
        elif isinstance(value, list):
            for item in value:
                collect(location, item)

    for job_id, job in _jobs(doc).items():
        if not isinstance(job, dict):
            continue
        collect(f"jobs.{job_id}.runs-on", job.get("runs-on"))
        matrix = (job.get("strategy") or {}).get("matrix") if isinstance(job.get("strategy"), dict) else None
        if not isinstance(matrix, dict):
            continue
        for key, value in matrix.items():
            if key == "include" and isinstance(value, list):
                for entry in value:
                    if isinstance(entry, dict):
                        for entry_key, entry_value in entry.items():
                            collect(f"jobs.{job_id}.strategy.matrix.include[].{entry_key}", entry_value)
            else:
                collect(f"jobs.{job_id}.strategy.matrix.{key}", value)
    return found


@pytest.mark.parametrize("path", _workflow_files(), ids=lambda p: p.name)
def test_no_retired_runner_images(path: Path) -> None:
    offenders = [
        f"{location}: {label}" for location, label in _runs_on_labels(_load(path)) if label in RETIRED_RUNNER_LABELS
    ]
    assert not offenders, (
        f"{path.name}: these runner labels have been retired by GitHub. A job asking for "
        "one is never scheduled and fails without a useful message, rather than falling "
        "back to a supported image. Move to a current label (for macOS Intel, "
        "`macos-15-intel`).\n  " + "\n  ".join(offenders)
    )
