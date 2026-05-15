"""Git REST API endpoints (ADR-039 §3.5)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from scieasy.core.versioning.git_binary import BundledGitMissing
from scieasy.core.versioning.git_engine import GitEngine, GitError

router = APIRouter(prefix="/api/git", tags=["git"])


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


class CommitRequest(BaseModel):
    message: str = Field(..., description="Commit message")
    author: str | None = Field(default=None)
    files: list[str] | None = Field(default=None)


class CommitResponse(BaseModel):
    commit_sha: str


class RestoreRequest(BaseModel):
    commit_sha: str
    files: list[str] | None = None


class BranchSwitchRequest(BaseModel):
    branch_name: str


class BranchCreateRequest(BaseModel):
    name: str
    base_sha: str | None = None


class MergeRequest(BaseModel):
    source_branch: str


class CherryPickRequest(BaseModel):
    commit_sha: str


class StashSaveRequest(BaseModel):
    message: str | None = None


class StashApplyRequest(BaseModel):
    stash_id: str


class MergeStageFileRequest(BaseModel):
    file: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _engine_for_request(request: Request) -> GitEngine:
    """Construct a GitEngine for the active project.

    Resolves the bundled git binary eagerly here (the engine's
    ``_git`` property is lazy) so a missing git surfaces as a
    structured ``503`` before any endpoint handler runs, rather than
    bubbling up as an uncaught 500 from the first subprocess call
    inside a handler. Codex P1 on PR #927.
    """
    runtime = request.app.state.runtime
    if runtime.active_project is None:
        raise HTTPException(status_code=409, detail="No active project")
    project_path = Path(runtime.active_project.path)
    try:
        engine = GitEngine(project_path)
        # Force lazy binary resolution so BundledGitMissing surfaces here.
        _ = engine._git
        return engine
    except BundledGitMissing as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _git_error_to_http(err: GitError) -> HTTPException:
    """Translate GitError stderr patterns into the right HTTP status code."""
    msg = (err.stderr or "").lower()
    detail = err.stderr or str(err)
    if (
        "unknown revision" in msg
        or "not a valid object" in msg
        or "bad revision" in msg
        or "did not match any" in msg
        or "no such branch" in msg
        or "not found" in msg
    ):
        return HTTPException(404, detail)
    if (
        "nothing to commit" in msg
        or "no local changes" in msg
        or "nothing to stash" in msg
        or "still has conflict markers" in msg
        or "would be overwritten" in msg
        or "your local changes" in msg
        or "cannot delete" in msg
        or "currently checked out" in msg
        or "no merge or cherry-pick" in msg
        or "cannot complete merge" in msg
    ):
        return HTTPException(409, detail)
    if "invalid" in msg or "is not a valid" in msg:
        return HTTPException(400, detail)
    return HTTPException(500, detail)


# ---------------------------------------------------------------------------
# Commit / log / diff / restore
# ---------------------------------------------------------------------------


@router.post("/commit", response_model=CommitResponse)
async def commit(request: Request, body: CommitRequest) -> CommitResponse:
    """Create a new commit. ADR-039 §3.5 line 217."""
    engine = _engine_for_request(request)
    try:
        sha = engine.commit(body.message, files=body.files, author=body.author, prefix=None)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except GitError as exc:
        raise _git_error_to_http(exc) from exc
    return CommitResponse(commit_sha=sha)


@router.get("/log")
async def log(
    request: Request,
    branch: str | None = None,
    limit: int | None = 500,
) -> list[dict[str, Any]]:
    """Return commit history. ADR-039 §3.5 line 218."""
    engine = _engine_for_request(request)
    try:
        return engine.log(branch=branch, limit=limit)
    except GitError as exc:
        raise _git_error_to_http(exc) from exc


@router.get("/diff")
async def diff(
    request: Request,
    from_: str = Query(..., alias="from"),
    to: str | None = "WORKING",
    file: str | None = None,
) -> dict[str, str]:
    """Return a unified diff string. ADR-039 §3.5 line 219."""
    engine = _engine_for_request(request)
    try:
        text = engine.diff(
            from_,
            to if to != "WORKING" else None,
            files=[file] if file else None,
        )
    except GitError as exc:
        raise _git_error_to_http(exc) from exc
    return {"diff": text}


@router.post("/restore")
async def restore(request: Request, body: RestoreRequest) -> dict[str, str]:
    """Soft-restore files from a prior commit. ADR-039 §3.5 line 220, §3.6."""
    engine = _engine_for_request(request)
    was_dirty = False
    try:
        was_dirty = engine.status()["dirty"]
        engine.restore(body.commit_sha, files=body.files)
    except GitError as exc:
        raise _git_error_to_http(exc) from exc
    if was_dirty:
        stashes = engine.stash_list()
        if stashes:
            return {"status": "stashed", "stash_id": stashes[0]["stash_id"]}
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Branch endpoints
# ---------------------------------------------------------------------------


@router.get("/branches")
async def branches(request: Request) -> list[dict[str, Any]]:
    """List all local branches. ADR-039 §3.5 line 221."""
    engine = _engine_for_request(request)
    try:
        return engine.branches()
    except GitError as exc:
        raise _git_error_to_http(exc) from exc


@router.post("/branch/switch")
async def branch_switch(request: Request, body: BranchSwitchRequest) -> dict[str, str]:
    """Switch to an existing branch."""
    engine = _engine_for_request(request)
    try:
        engine.branch_switch(body.branch_name)
    except GitError as exc:
        raise _git_error_to_http(exc) from exc
    return {"status": "ok", "current_branch": body.branch_name}


@router.post("/branch/create")
async def branch_create(request: Request, body: BranchCreateRequest) -> dict[str, str]:
    """Create a new branch at HEAD or specified base SHA."""
    engine = _engine_for_request(request)
    try:
        engine.branch_create(body.name, base=body.base_sha)
    except GitError as exc:
        raise _git_error_to_http(exc) from exc
    return {"status": "ok", "name": body.name}


@router.delete("/branches/{name}")
async def branch_delete(request: Request, name: str, force: bool = False) -> dict[str, str]:
    """Delete a local branch."""
    engine = _engine_for_request(request)
    try:
        engine.branch_delete(name, force=force)
    except GitError as exc:
        raise _git_error_to_http(exc) from exc
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Status endpoint
# ---------------------------------------------------------------------------


@router.get("/status")
async def status_endpoint(request: Request) -> dict[str, Any]:
    """Return working-tree status. ADR-039 §3.5 line 222."""
    engine = _engine_for_request(request)
    try:
        return engine.status()
    except GitError:
        return {
            "dirty": False,
            "modified": [],
            "staged": [],
            "untracked": [],
            "conflicted": [],
        }


# ---------------------------------------------------------------------------
# Merge / cherry-pick
# ---------------------------------------------------------------------------


@router.post("/merge")
async def merge(request: Request, body: MergeRequest) -> dict[str, Any]:
    """Merge a branch into current."""
    engine = _engine_for_request(request)
    try:
        return engine.merge(body.source_branch)
    except GitError as exc:
        raise _git_error_to_http(exc) from exc


@router.post("/cherry-pick")
async def cherry_pick(request: Request, body: CherryPickRequest) -> dict[str, Any]:
    """Cherry-pick a commit onto current branch."""
    engine = _engine_for_request(request)
    try:
        return engine.cherry_pick(body.commit_sha)
    except GitError as exc:
        raise _git_error_to_http(exc) from exc


# ---------------------------------------------------------------------------
# Stash CRUD
# ---------------------------------------------------------------------------


@router.get("/stash")
async def stash_list(request: Request) -> list[dict[str, Any]]:
    """List stashed changes."""
    engine = _engine_for_request(request)
    try:
        return engine.stash_list()
    except GitError as exc:
        raise _git_error_to_http(exc) from exc


@router.post("/stash/save")
async def stash_save(request: Request, body: StashSaveRequest) -> dict[str, str]:
    """Save current changes to a new stash."""
    engine = _engine_for_request(request)
    try:
        stash_id = engine.stash_save(message=body.message)
    except GitError as exc:
        raise _git_error_to_http(exc) from exc
    return {"stash_id": stash_id}


@router.post("/stash/apply")
async def stash_apply(request: Request, body: StashApplyRequest) -> dict[str, Any]:
    """Apply a stash entry (without dropping it)."""
    engine = _engine_for_request(request)
    try:
        engine.stash_apply(body.stash_id)
    except GitError as exc:
        raise _git_error_to_http(exc) from exc
    status = engine.status()
    if status["conflicted"]:
        return {"status": "conflict", "conflicted_files": status["conflicted"]}
    return {"status": "ok"}


@router.delete("/stash/{stash_id:path}")
async def stash_drop(request: Request, stash_id: str) -> dict[str, str]:
    """Drop a stash entry."""
    engine = _engine_for_request(request)
    try:
        engine.stash_drop(stash_id)
    except GitError as exc:
        raise _git_error_to_http(exc) from exc
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Conflict-resolution finalization
# ---------------------------------------------------------------------------


@router.post("/merge/stage-file")
async def merge_stage_file(request: Request, body: MergeStageFileRequest) -> dict[str, str]:
    """Stage a file after the user resolved its conflict markers."""
    engine = _engine_for_request(request)
    try:
        engine.merge_stage_file(body.file)
    except GitError as exc:
        if "conflict markers" in (exc.stderr or "").lower():
            raise HTTPException(409, exc.stderr) from exc
        raise _git_error_to_http(exc) from exc
    return {"status": "ok"}


@router.post("/merge/complete")
async def merge_complete(request: Request) -> dict[str, str]:
    """Finalize merge after all conflicts staged."""
    engine = _engine_for_request(request)
    try:
        sha = engine.merge_complete()
    except GitError as exc:
        raise _git_error_to_http(exc) from exc
    return {"status": "ok", "commit_sha": sha}


@router.post("/merge/abort")
async def merge_abort(request: Request) -> dict[str, str]:
    """Abort an in-progress merge or cherry-pick."""
    engine = _engine_for_request(request)
    try:
        engine.merge_abort()
    except GitError as exc:
        raise _git_error_to_http(exc) from exc
    return {"status": "ok"}
