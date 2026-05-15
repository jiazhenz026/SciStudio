"""Skeleton tests for ``scieasy.api.routes.git`` REST endpoints (ADR-039).

D39-2.2a contributes xfail stubs; D39-2.2b flips them to passing.

Each test exercises the happy path of one endpoint plus the most
important error envelope. Negative-path coverage (e.g. 404 on bad SHA)
is listed in each endpoint's docstring "Test plan" and should be added
during impl.
"""

from __future__ import annotations

import pytest

# Endpoint smoke tests use the FastAPI TestClient fixture from
# tests/api/conftest.py (created by D39-2.2b alongside these tests, or
# reusing the existing test_app fixture).


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_commit_endpoint_round_trip() -> None:
    """POST /api/git/commit → 200 with sha; GET /api/git/log returns it.

    Steps:
    1. Create test project + auto-init (via fixture).
    2. Modify a workflow file in the test project.
    3. POST /api/git/commit with body ``{"message": "test commit"}``.
    4. Assert 200; capture ``commit_sha``.
    5. GET /api/git/log; assert first entry's ``sha == commit_sha``.
    """
    raise NotImplementedError("D39-2.2b — see docstring")


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_commit_endpoint_clean_tree_409() -> None:
    """POST /api/git/commit on clean tree returns 409."""
    raise NotImplementedError("D39-2.2b — see docstring")


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_log_endpoint_returns_commits() -> None:
    """GET /api/git/log returns the seeded commits."""
    raise NotImplementedError("D39-2.2b — see docstring")


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_diff_endpoint_commit_to_working() -> None:
    """GET /api/git/diff?from=<sha>&to=WORKING returns unified diff."""
    raise NotImplementedError("D39-2.2b — see docstring")


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_restore_endpoint_soft_restore() -> None:
    """POST /api/git/restore restores file content; HEAD unchanged."""
    raise NotImplementedError("D39-2.2b — see docstring")


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_branches_endpoint_lists_default() -> None:
    """GET /api/git/branches returns [{"name": "main", is_current: true, ...}]."""
    raise NotImplementedError("D39-2.2b — see docstring")


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_branch_switch_endpoint_changes_head() -> None:
    """POST /api/git/branch/switch updates current branch."""
    raise NotImplementedError("D39-2.2b — see docstring")


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_branch_create_endpoint() -> None:
    """POST /api/git/branch/create makes a new branch at HEAD."""
    raise NotImplementedError("D39-2.2b — see docstring")


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_branch_delete_endpoint() -> None:
    """DELETE /api/git/branches/{name} removes the branch."""
    raise NotImplementedError("D39-2.2b — see docstring")


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_status_endpoint_reports_dirty() -> None:
    """GET /api/git/status reflects working-tree state."""
    raise NotImplementedError("D39-2.2b — see docstring")


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_merge_endpoint_fast_forward() -> None:
    """POST /api/git/merge returns result="fast-forward" when applicable."""
    raise NotImplementedError("D39-2.2b — see docstring")


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_merge_endpoint_conflict() -> None:
    """POST /api/git/merge returns result="conflict" + conflicted_files."""
    raise NotImplementedError("D39-2.2b — see docstring")


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_cherry_pick_endpoint_clean() -> None:
    """POST /api/git/cherry-pick produces clean result."""
    raise NotImplementedError("D39-2.2b — see docstring")


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_stash_save_endpoint() -> None:
    """POST /api/git/stash/save creates a new stash entry."""
    raise NotImplementedError("D39-2.2b — see docstring")


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_stash_list_endpoint() -> None:
    """GET /api/git/stash lists stashes."""
    raise NotImplementedError("D39-2.2b — see docstring")


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_stash_apply_endpoint() -> None:
    """POST /api/git/stash/apply re-applies stashed changes."""
    raise NotImplementedError("D39-2.2b — see docstring")


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_stash_drop_endpoint() -> None:
    """DELETE /api/git/stash/{stash_id} removes a stash entry."""
    raise NotImplementedError("D39-2.2b — see docstring")


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_merge_stage_file_endpoint() -> None:
    """POST /api/git/merge/stage-file marks a file resolved."""
    raise NotImplementedError("D39-2.2b — see docstring")


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_merge_complete_endpoint() -> None:
    """POST /api/git/merge/complete finalizes the merge commit."""
    raise NotImplementedError("D39-2.2b — see docstring")


@pytest.mark.xfail(reason="D39-2.2a skeleton — body filled by D39-2.2b", strict=True)
def test_merge_abort_endpoint() -> None:
    """POST /api/git/merge/abort restores pre-merge state."""
    raise NotImplementedError("D39-2.2b — see docstring")
