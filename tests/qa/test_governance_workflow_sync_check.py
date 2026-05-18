"""Tests for ``scieasy.qa.governance.workflow_sync_check`` (TC-1E.6 part B).

Covers:

- Workflow file missing branch.
- Shadow ``paths:`` hand-list rejection.
- Shadow ``paths-ignore:`` hand-list rejection.
- Missing path_filter / workflow_sync_check steps.
- Real shipping workflow passes (no findings).
- CLI exit codes (0 on green, 1 on findings).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from scieasy.qa.governance.workflow_sync_check import (
    _WORKFLOW_REL,
    main,
    verify,
)

# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #


_CLEAN_WORKFLOW = """\
name: governance-modification-check
on:
  pull_request: {}

jobs:
  recursive-self-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: pf
        run: python -m scieasy.qa.governance.path_filter --paths-yaml .governance-paths.yaml --base x --head y --output z
      - name: ws
        run: python -m scieasy.qa.governance.workflow_sync_check
"""


_SHADOW_PATHS_WORKFLOW = """\
name: governance-modification-check
on:
  pull_request:
    paths:
      - "docs/adr/**"
      - "CLAUDE.md"

jobs:
  recursive-self-check:
    runs-on: ubuntu-latest
    steps:
      - name: pf
        run: python -m scieasy.qa.governance.path_filter
      - name: ws
        run: python -m scieasy.qa.governance.workflow_sync_check
"""


_SHADOW_PATHS_IGNORE_WORKFLOW = """\
name: governance-modification-check
on:
  pull_request:
    paths-ignore:
      - "docs/notes/**"

jobs:
  recursive-self-check:
    runs-on: ubuntu-latest
    steps:
      - name: pf
        run: python -m scieasy.qa.governance.path_filter
      - name: ws
        run: python -m scieasy.qa.governance.workflow_sync_check
"""


_MISSING_PATH_FILTER_WORKFLOW = """\
name: governance-modification-check
on:
  pull_request: {}

jobs:
  recursive-self-check:
    runs-on: ubuntu-latest
    steps:
      - name: ws
        run: python -m scieasy.qa.governance.workflow_sync_check
"""


_MISSING_WORKFLOW_SYNC_WORKFLOW = """\
name: governance-modification-check
on:
  pull_request: {}

jobs:
  recursive-self-check:
    runs-on: ubuntu-latest
    steps:
      - name: pf
        run: python -m scieasy.qa.governance.path_filter
"""


def _stage(tmp_path: Path, body: str | None) -> Path:
    """Create a fake repo root with the workflow file (or omit it)."""
    if body is not None:
        target = tmp_path / _WORKFLOW_REL
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    return tmp_path


@pytest.fixture
def clean_repo(tmp_path: Path) -> Iterator[Path]:
    yield _stage(tmp_path, _CLEAN_WORKFLOW)


# --------------------------------------------------------------------------- #
# Verify                                                                      #
# --------------------------------------------------------------------------- #


def test_clean_workflow_yields_no_findings(clean_repo: Path):
    assert verify(clean_repo) == []


def test_missing_workflow_returns_workflow_missing_finding(tmp_path: Path):
    findings = verify(tmp_path)
    assert len(findings) == 1
    assert findings[0].kind == "workflow-missing"
    assert findings[0].file == _WORKFLOW_REL


def test_shadow_paths_hand_list_detected(tmp_path: Path):
    repo = _stage(tmp_path, _SHADOW_PATHS_WORKFLOW)
    findings = verify(repo)
    kinds = {f.kind for f in findings}
    assert "shadow-paths-filter" in kinds


def test_shadow_paths_ignore_detected(tmp_path: Path):
    repo = _stage(tmp_path, _SHADOW_PATHS_IGNORE_WORKFLOW)
    findings = verify(repo)
    assert "shadow-paths-ignore-filter" in {f.kind for f in findings}


def test_missing_path_filter_step_detected(tmp_path: Path):
    repo = _stage(tmp_path, _MISSING_PATH_FILTER_WORKFLOW)
    findings = verify(repo)
    assert "missing-path-filter-step" in {f.kind for f in findings}


def test_missing_workflow_sync_step_detected(tmp_path: Path):
    repo = _stage(tmp_path, _MISSING_WORKFLOW_SYNC_WORKFLOW)
    findings = verify(repo)
    assert "missing-workflow-sync-step" in {f.kind for f in findings}


def test_shadow_filter_finding_carries_line_number(tmp_path: Path):
    repo = _stage(tmp_path, _SHADOW_PATHS_WORKFLOW)
    findings = verify(repo)
    [shadow] = [f for f in findings if f.kind == "shadow-paths-filter"]
    assert shadow.line is not None
    assert shadow.line > 0


def test_real_repo_workflow_is_clean():
    """Sanity guard: the ACTUAL governance-modification.yml in this
    repo must pass workflow_sync_check. Failing here means the
    workflow we just shipped has reintroduced a shadow hand-list.
    """
    repo_root = Path(__file__).resolve().parents[2]
    if not (repo_root / _WORKFLOW_REL).is_file():
        pytest.skip("governance-modification.yml not yet present")
    findings = verify(repo_root)
    assert findings == [], findings


# --------------------------------------------------------------------------- #
# CLI                                                                         #
# --------------------------------------------------------------------------- #


def test_cli_exit_0_on_clean_workflow(clean_repo: Path):
    rc = main(["--repo-root", str(clean_repo)])
    assert rc == 0


def test_cli_exit_1_on_shadow_paths(tmp_path: Path):
    repo = _stage(tmp_path, _SHADOW_PATHS_WORKFLOW)
    rc = main(["--repo-root", str(repo)])
    assert rc == 1


def test_cli_exit_1_on_missing_workflow(tmp_path: Path):
    rc = main(["--repo-root", str(tmp_path)])
    assert rc == 1


# --------------------------------------------------------------------------- #
# YAML structural walk — #1179                                                #
# --------------------------------------------------------------------------- #

# A workflow where the required invocation appears ONLY inside a YAML comment;
# there is no actual step calling the module.
_COMMENT_ONLY_PATH_FILTER_WORKFLOW = """\
name: governance-modification-check
on:
  pull_request: {}

jobs:
  recursive-self-check:
    runs-on: ubuntu-latest
    steps:
      - name: note
        # The next line is documentation ONLY — it mentions
        # scieasy.qa.governance.path_filter but does NOT invoke it.
        run: |
          echo "See scieasy.qa.governance.workflow_sync_check for details"
"""

# A workflow where path_filter invocation is in another job (not recursive-self-check).
_PATH_FILTER_WRONG_JOB_WORKFLOW = """\
name: governance-modification-check
on:
  pull_request: {}

jobs:
  other-job:
    runs-on: ubuntu-latest
    steps:
      - name: pf
        run: python -m scieasy.qa.governance.path_filter
      - name: ws
        run: python -m scieasy.qa.governance.workflow_sync_check
  recursive-self-check:
    runs-on: ubuntu-latest
    steps:
      - name: unrelated
        run: echo hello
"""


def test_yaml_comment_does_not_count_as_path_filter_step(tmp_path: Path):
    """A signature that appears only in a YAML comment must NOT pass the step check (#1179).

    The raw-text substring search (old implementation) would falsely pass here
    because ``scieasy.qa.governance.workflow_sync_check`` appears in the workflow
    text but not in an actual ``run:`` step.  The structural YAML walk must
    correctly flag this as ``missing-path-filter-step``.
    """
    repo = _stage(tmp_path, _COMMENT_ONLY_PATH_FILTER_WORKFLOW)
    findings = verify(repo)
    kinds = {f.kind for f in findings}
    # path_filter only appears as raw text (in the echo string), not as
    # an actual invocation. The step check must flag it as missing.
    assert "missing-path-filter-step" in kinds, f"Expected missing-path-filter-step in findings; got: {kinds}"


def test_path_filter_in_wrong_job_is_not_sufficient(tmp_path: Path):
    """An invocation in a job other than 'recursive-self-check' must not satisfy the check (#1179)."""
    repo = _stage(tmp_path, _PATH_FILTER_WRONG_JOB_WORKFLOW)
    findings = verify(repo)
    kinds = {f.kind for f in findings}
    # Neither path_filter nor workflow_sync_check runs inside recursive-self-check
    assert "missing-path-filter-step" in kinds, f"Expected missing-path-filter-step; got {kinds}"


def test_has_step_yaml_walk_ignores_yaml_comments():
    """Direct unit test for _has_step: YAML comment must not match (#1179)."""
    from scieasy.qa.governance.workflow_sync_check import _has_step

    workflow = """\
name: governance-modification-check
on:
  pull_request: {}
jobs:
  recursive-self-check:
    runs-on: ubuntu-latest
    steps:
      - name: note
        # scieasy.qa.governance.path_filter is mentioned here in a comment
        run: echo done
"""
    assert not _has_step(workflow, "scieasy.qa.governance.path_filter"), (
        "A YAML comment must not count as a matching step"
    )


def test_has_step_yaml_walk_matches_actual_run_line():
    """Direct unit test for _has_step: actual run: step must match."""
    from scieasy.qa.governance.workflow_sync_check import _has_step

    workflow = """\
name: governance-modification-check
on:
  pull_request: {}
jobs:
  recursive-self-check:
    runs-on: ubuntu-latest
    steps:
      - name: pf
        run: python -m scieasy.qa.governance.path_filter --paths-yaml x
"""
    assert _has_step(workflow, "scieasy.qa.governance.path_filter")
