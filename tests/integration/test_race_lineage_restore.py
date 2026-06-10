"""ADR-045 lineage/git restore race regression coverage.

ADR-045 §5.1 row #5 retired the SHA-256 hash-snapshot diff in ``git.py``: the
set of workflows a tree-mutating git op rewrote is now derived from git itself
(``git diff --name-status`` over the committed range + working tree) rather than
by hashing every YAML pre/post-op. These tests pin the new write-site emit:

* ``_changed_workflow_paths`` returns the right ``{path: kind}`` for a working-
  tree edit (the ``restore`` shape: historical content overlaid, uncommitted).
* ``_emit_workflow_diff`` emits one versioned ``workflow.changed`` per change.

Git commits in this sandbox fail at a signing server, so these tests build the
repo with commit signing explicitly disabled (read-only git paths that
``GitEngine`` uses for diffing do not sign and work unchanged).
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

import pytest

from scistudio.api.routes.git import _capture_pre_op_ref, _changed_workflow_paths, _emit_workflow_diff
from scistudio.api.runtime import ApiRuntime, KnownProject
from scistudio.core.versioning.git_engine import GitEngine
from scistudio.engine.events import WORKFLOW_CHANGED, EngineEvent


def _git(repo: Path, *args: str) -> None:
    """Run git in *repo* with signing disabled (sandbox-safe commits)."""
    subprocess.run(
        [
            "git",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "tag.gpgsign=false",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            *args,
        ],
        cwd=repo,
        check=True,
        capture_output=True,
    )


@pytest.fixture()
def git_project(tmp_path: Path) -> Path:
    """A real git repo with one committed workflow YAML (signing disabled)."""
    repo = tmp_path / "proj"
    (repo / "workflows").mkdir(parents=True)
    wf = repo / "workflows" / "lineage-restore-race.yaml"
    wf.write_text("id: w\nnodes: []\nedges: []\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "seed workflow")
    return repo


def test_changed_workflow_paths_detects_working_tree_edit(git_project: Path) -> None:
    """ADR-045 §5.1 #5: a working-tree YAML edit is detected via git diff.

    This is the ``restore`` shape — historical content overlaid into the
    working tree without a new commit. The old hash-snapshot is gone; git is
    the source of truth for which workflow changed.
    """
    engine = GitEngine(git_project)
    before_ref = _capture_pre_op_ref(engine)
    assert before_ref is not None

    wf = git_project / "workflows" / "lineage-restore-race.yaml"
    wf.write_text(wf.read_text(encoding="utf-8") + "metadata:\n  restored: true\n", encoding="utf-8")

    changed = _changed_workflow_paths(engine, git_project, before_ref)
    assert changed == {"workflows/lineage-restore-race.yaml": "modified"}


def test_changed_workflow_paths_detects_new_and_deleted(git_project: Path) -> None:
    """A created and a deleted workflow are classified correctly."""
    engine = GitEngine(git_project)
    before_ref = _capture_pre_op_ref(engine)

    (git_project / "workflows" / "fresh.yaml").write_text("id: fresh\n", encoding="utf-8")
    (git_project / "workflows" / "lineage-restore-race.yaml").unlink()

    changed = _changed_workflow_paths(engine, git_project, before_ref)
    assert changed.get("workflows/fresh.yaml") == "created"
    assert changed.get("workflows/lineage-restore-race.yaml") == "deleted"


def test_changed_workflow_paths_ignores_non_workflow_files(git_project: Path) -> None:
    """Edits outside ``workflows/`` (or non-YAML) never drive the canvas."""
    engine = GitEngine(git_project)
    before_ref = _capture_pre_op_ref(engine)

    (git_project / "README.md").write_text("hi\n", encoding="utf-8")
    (git_project / "workflows" / "notes.txt").write_text("note\n", encoding="utf-8")

    changed = _changed_workflow_paths(engine, git_project, before_ref)
    assert changed == {}


def test_git_restore_emits_semantic_modified_event_not_delete_clear(
    git_project: Path,
) -> None:
    """ADR-045 §5.1 #5: the write-site emit produces a single versioned
    ``modified`` event for the workflow git rewrote — never a delete/clear."""
    runtime = ApiRuntime()
    runtime.active_project = KnownProject(
        id="p1", name="proj", path=str(git_project), description=""
    )
    engine = GitEngine(git_project)
    before_ref = _capture_pre_op_ref(engine)

    # Seed the runtime's version state from disk so the bump is deterministic.
    runtime.reset_version_state_for_project(git_project)
    base_version = runtime.current_workflow_version("lineage-restore-race")

    wf = git_project / "workflows" / "lineage-restore-race.yaml"
    wf.write_text(wf.read_text(encoding="utf-8") + "metadata:\n  restored: true\n", encoding="utf-8")

    seen: list[EngineEvent] = []
    runtime.event_bus.subscribe(WORKFLOW_CHANGED, lambda event: seen.append(event))

    asyncio.run(
        _emit_workflow_diff(
            runtime,
            git_project,
            engine,
            before_ref,
            source="gitRestore",
            source_id="restore-commit-123",
        )
    )

    assert len(seen) == 1
    data = seen[0].data
    assert data["entity_class"] == "workflow"
    assert data["entity_id"] == "lineage-restore-race"
    assert data["workflow_id"] == "lineage-restore-race"
    assert data["source"] == "gitRestore"
    assert data["source_id"] == "restore-commit-123"
    assert data["kind"] == "modified"
    assert data["version"] == base_version + 1
    assert data["path"] == "workflows/lineage-restore-race.yaml"
