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
