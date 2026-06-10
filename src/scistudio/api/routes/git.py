"""Git REST API endpoints (ADR-039 §3.5)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from scistudio.core.versioning.git_binary import BundledGitMissing
from scistudio.core.versioning.git_engine import GitEngine, GitError
from scistudio.engine.events import WORKFLOW_CHANGED, EngineEvent

logger = logging.getLogger(__name__)
_WORKFLOW_ENTITY_CLASS = "workflow"

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


def _capture_pre_op_ref(engine: GitEngine) -> str | None:
    """Capture the HEAD SHA before a tree-mutating git op (ADR-045 §5.1 #5).

    ADR-045 §5.1 row #5 retires the SHA-256 hash-snapshot diff: each git
    endpoint is a **write site** that already knows the semantic, so the set
    of affected workflows is derived from git itself rather than by hashing
    every YAML pre/post-op. Callers capture the pre-op HEAD here, run the git
    operation, then call :func:`_emit_workflow_diff`, which asks git which
    ``workflows/*.yaml`` paths changed.

    Returns ``None`` when HEAD cannot be resolved (e.g. an unborn branch with
    no commits yet); :func:`_emit_workflow_diff` falls back to a working-tree
    diff in that case.
    """
    try:
        state = engine.head_state()
    except GitError:
        return None
    return state.commit_sha or None


def _changed_workflow_paths(engine: GitEngine, project_dir: Path, before_ref: str | None) -> dict[str, str]:
    """Return ``{posix_relative_path: kind}`` for workflow YAMLs git says changed.

    ADR-045 §5.1 #5: replaces the hash-snapshot diff. Affected workflows are
    discovered with ``git diff --name-status`` over two surfaces, unioned:

    * **committed**: ``<before_ref>..HEAD`` — captures branch switch, merge,
      cherry-pick, merge-complete (operations that move HEAD).
    * **working tree**: ``HEAD`` vs the working tree — captures ``restore``
      (which overlays historical content without committing) and any residual
      uncommitted rewrite.

    Only paths under ``workflows/`` with a YAML suffix drive the canvas, so
    everything else is filtered out. ``kind`` is normalised to the
    ``created`` / ``deleted`` / ``modified`` vocabulary the watcher and the
    frontend handler at ``useWebSocket.ts`` already share.
    """
    diffs: list[str] = []
    after_ref = _capture_pre_op_ref(engine)  # current (post-op) HEAD SHA
    if before_ref and after_ref and before_ref != after_ref:
        try:
            diffs.append(engine._run(["diff", "--name-status", f"{before_ref}..{after_ref}"]).stdout or "")
        except GitError:
            logger.debug("git endpoint: committed-range diff failed", exc_info=True)
    # Working-tree changes vs HEAD (restore / uncommitted rewrites).
    try:
        diffs.append(engine._run(["diff", "--name-status", "HEAD"]).stdout or "")
    except GitError:
        logger.debug("git endpoint: working-tree diff failed", exc_info=True)

    changed: dict[str, str] = {}

    # Untracked workflow YAMLs are not reported by ``git diff`` but a git op can
    # leave a new-on-disk workflow the canvas must learn about; surface them as
    # ``created`` (matches the retired hash-snapshot's filesystem scan).
    try:
        untracked = engine._run(["ls-files", "--others", "--exclude-standard"]).stdout or ""
        for line in untracked.splitlines():
            rel = line.strip()
            if rel.startswith("workflows/") and Path(rel).suffix.lower() in {".yaml", ".yml"}:
                changed[rel] = "created"
    except GitError:
        logger.debug("git endpoint: untracked listing failed", exc_info=True)

    for block in diffs:
        for line in block.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            status = parts[0]
            # Renames/copies report two paths (R100 old new); take the dest.
            rel = parts[-1]
            if not rel.startswith("workflows/") or Path(rel).suffix.lower() not in {".yaml", ".yml"}:
                continue
            code = status[0]
            if code == "A" or code == "R" or code == "C":
                kind = "created"
            elif code == "D":
                kind = "deleted"
            else:
                kind = "modified"
            # A path appearing in both surfaces: prefer a concrete create/delete
            # over a generic modify; otherwise keep the first seen.
            existing = changed.get(rel)
            if existing is None or (existing == "modified" and kind != "modified"):
                changed[rel] = kind
    return changed


async def _emit_workflow_diff(
    runtime: Any,
    project_dir: Path,
    engine: GitEngine,
    before_ref: str | None,
    *,
    source: str,
    source_id: str | None = None,
) -> None:
    """Emit ``workflow.changed`` once per workflow YAML the git op rewrote.

    ADR-045 §5.1 #5 (retire the hash-snapshot diff): callers capture the
    pre-op HEAD via :func:`_capture_pre_op_ref`, run the git operation, then
    call this helper. It asks git which ``workflows/*.yaml`` paths changed
    (see :func:`_changed_workflow_paths`), classifies each as ``created`` /
    ``deleted`` / ``modified`` (the same schema the watcher uses so the
    frontend handler at ``useWebSocket.ts`` treats backend-driven and
    watcher-driven events identically), and emits one event per change.

    ``workflow_id`` is derived from the file stem so the frontend's
    "is this the active tab's workflow?" check (`state.workflowId ===
    changedId`) keeps the same identity rules as a canvas save.

    Best-effort: any emit failure is logged but never raised — the git op
    has already committed to disk and rolling it back would be worse than
    a stale-canvas-until-next-refresh fallback. The watcher is still
    running as insurance.
    """
    changed = _changed_workflow_paths(engine, project_dir, before_ref)

    for relative in sorted(changed.keys()):
        kind = changed[relative]
        workflow_id = Path(relative).stem
        workflow_path = project_dir / relative
        version = runtime.bump_workflow_version(workflow_id)
        runtime.mark_workflow_first_party_write(workflow_id, version, path=workflow_path, kind=kind)
        if workflow_path.exists():
            try:
                from scistudio.api.routes.workflow_watcher import mark_self_write

                mark_self_write(workflow_path)
            except Exception:
                logger.debug("git endpoint: mark_self_write failed for %s", workflow_path, exc_info=True)
        payload = runtime.versioned_change_payload(
            entity_class=_WORKFLOW_ENTITY_CLASS,
            entity_id=workflow_id,
            version=version,
            source=source,
            source_id=source_id,
            kind=kind,
            workflow_id=workflow_id,
            path=relative,
            changed_by="git",
        )
        try:
            await runtime.event_bus.emit(
                EngineEvent(
                    event_type=WORKFLOW_CHANGED,
                    data=payload,
                )
            )
        except Exception:
            logger.exception(
                "git endpoint: failed to emit workflow.changed for %s (%s)",
                relative,
                kind,
            )


def _auto_commit_if_dirty(engine: GitEngine, message: str) -> str | None:
    """Auto-commit a dirty working tree with ``prefix="auto"``.

    ADR-039 Addendum 1 §11.3 (#1354): the dirty-tree branch-switch and
    restore paths used to call ``git stash``. They now auto-commit
    instead so the user's prior state is one ``git checkout HEAD^``
    away in History rather than buried in a stash drawer the user is
    not expected to know about.

    Returns the new HEAD SHA on success, ``None`` if the tree was
    clean (no commit needed). Catches the engine's "nothing to commit"
    error as a no-op — this is the race-window where ``status()`` saw
    dirty but the staged diff was empty by the time ``commit()`` ran
    (typically: untracked-only files plus a gitignore-filtered subset).
    """
    if not engine.status()["dirty"]:
        return None
    try:
        return engine.commit(message, prefix="auto")
    except GitError as exc:
        stderr_lower = (exc.stderr or "").lower()
        if "nothing to commit" in stderr_lower or "no local changes" in stderr_lower:
            return None
        raise


def _iso_ts_now() -> str:
    """Return the current UTC time as an ISO-8601 string (no microseconds)."""
    return datetime.now(UTC).replace(microsecond=0).isoformat()


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
        # Codex P2 reconcile on PR #979: invalid merge target is a
        # client/input error, not a server failure.
        or "not something we can merge" in msg
    ):
        return HTTPException(404, detail)
    if (
        "nothing to commit" in msg
        or "no local changes" in msg
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
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return commit history. ADR-039 §3.5 line 218.

    Hotfix #1009: default to ``None`` (unbounded) rather than 500.
    The frontend GitGraph uses row virtualisation (#1004), so a deep
    history only costs lane-assignment time, not DOM nodes. The 500
    cap silently truncated dev repos (e.g. SciStudio's own ~570-commit
    history shown as "starts at fix572"). Clients that want a hard
    cap can still pass ``?limit=N`` explicitly.
    """
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
async def restore(request: Request, body: RestoreRequest) -> dict[str, Any]:
    """Soft-restore files from a prior commit. ADR-039 §3.5 line 220, §3.6.

    ADR-039 Addendum 1 (#1354): when the working tree is dirty, auto-
    commit the dirty content first with ``prefix="auto"`` and
    ``message="pre-restore @ <iso-ts> (target=<short_sha>)"`` so the
    user's prior state is recoverable via a normal ``git checkout
    HEAD^``. The response carries ``auto_commit_sha`` (string when an
    auto-commit landed, otherwise ``null``); the frontend
    ``RestoreWorkflowButton`` surfaces a "committed as <sha>" hint
    when it is non-null.
    """
    engine = _engine_for_request(request)
    runtime = request.app.state.runtime
    project_dir = Path(runtime.active_project.path)
    before_ref = _capture_pre_op_ref(engine)
    # Codex P2 on PR #1378: validate the restore target BEFORE creating
    # the auto-commit. Pre-fix, an invalid commit_sha (typo, dropped
    # ref, etc.) would mutate history with an `auto: pre-restore` commit
    # *and* return an error — non-atomic, confusing extra commits on
    # failed requests. Resolving the target first means the auto-commit
    # only lands when the subsequent restore can actually proceed.
    try:
        engine._run(["rev-parse", "--verify", f"{body.commit_sha}^{{commit}}"])
    except GitError as exc:
        raise _git_error_to_http(exc) from exc
    try:
        # ADR-039 Addendum 1 (#1354): auto-commit dirty tree BEFORE the
        # checkout overlays the historical content. This protects the
        # user's unsaved edits as a recoverable commit on the current
        # branch — much friendlier than the previous stash-and-pray.
        auto_sha = _auto_commit_if_dirty(
            engine,
            f"pre-restore @ {_iso_ts_now()} (target={body.commit_sha[:7]})",
        )
        engine.restore(body.commit_sha, files=body.files)
    except GitError as exc:
        raise _git_error_to_http(exc) from exc
    # Hotfix #988 / ADR-045 §5.1 #5: emit per-file workflow.changed so the
    # canvas reloads, deriving the affected set from git rather than a hash diff.
    await _emit_workflow_diff(runtime, project_dir, engine, before_ref, source="gitRestore", source_id=body.commit_sha)
    return {"status": "ok", "auto_commit_sha": auto_sha}


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
async def branch_switch(request: Request, body: BranchSwitchRequest) -> dict[str, Any]:
    """Switch to an existing branch.

    ADR-039 Addendum 1 (#1354): when the working tree is dirty, auto-
    commit the dirty content first with ``prefix="auto"`` and
    ``message="pre-switch @ <iso-ts> (from=<old>, to=<new>)"`` so the
    raw "your local changes would be overwritten" error is replaced by
    a safe, recoverable commit. The response carries
    ``auto_commit_sha`` (string when an auto-commit landed, otherwise
    ``null``); the frontend ``BranchPicker`` surfaces a transient
    toast when it is non-null.

    Phase 3.5 integration audit P2-2: after the branch switch lands,
    refresh the in-process block registry so per-project custom blocks
    that ship under ``<project>/blocks/`` (per ADR-039 §3.5b "blocks
    alongside git") pick up the new on-disk source. Without this call,
    the registry continues to serve the previous branch's block bodies
    until the next ``open_project`` or process restart.

    Best-effort: a refresh failure must not roll back the branch switch
    (the branch is already committed in the working tree); we log and
    proceed.
    """
    engine = _engine_for_request(request)
    runtime = request.app.state.runtime
    project_dir = Path(runtime.active_project.path)
    before_ref = _capture_pre_op_ref(engine)
    old_branch = engine.current_branch() or "(detached)"
    # Codex P1 on PR #1378: validate the target branch exists BEFORE
    # creating the auto-commit. Pre-fix, a stale/invalid branch name
    # (deleted outside this client, typo, etc.) would mutate history
    # with an `auto: pre-switch` commit on the OLD branch *and* return
    # an error from the subsequent checkout — non-atomic, user-visible
    # extra commits on failed requests. Resolving the target first
    # means the auto-commit only lands when the checkout can actually
    # proceed.
    known_branches = {b["name"] for b in engine.branches()}
    if body.branch_name not in known_branches:
        raise HTTPException(
            status_code=404,
            detail=f"Branch '{body.branch_name}' does not exist.",
        )
    try:
        # ADR-039 Addendum 1 (#1354): auto-commit dirty tree BEFORE the
        # checkout so the user does not see a raw git "your local
        # changes would be overwritten" error. The auto commit lands on
        # ``old_branch`` and is recoverable via History.
        auto_sha = _auto_commit_if_dirty(
            engine,
            f"pre-switch @ {_iso_ts_now()} (from={old_branch}, to={body.branch_name})",
        )
        engine.branch_switch(body.branch_name)
    except GitError as exc:
        raise _git_error_to_http(exc) from exc
    # ADR-039 §3.5b — refresh project-scoped block registry after the
    # working tree changes.
    try:
        runtime.refresh_block_registry()
    except Exception:
        logger.warning(
            "branch_switch: refresh_block_registry failed (non-fatal)",
            exc_info=True,
        )
    # Hotfix #988 / ADR-045 §5.1 #5: emit per-file workflow.changed so the
    # canvas reloads each workflow YAML the branch switch rewrote. The affected
    # set is derived from git (committed-range + working-tree diff) rather than
    # a pre/post hash snapshot, and this can't rely on the filesystem watcher
    # alone (bulk rewrites coalesce inside a single debounce slice).
    await _emit_workflow_diff(
        runtime, project_dir, engine, before_ref, source="gitRestore", source_id=body.branch_name
    )
    return {
        "status": "ok",
        "current_branch": body.branch_name,
        "auto_commit_sha": auto_sha,
    }


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
    """Delete a local branch.

    ADR-039 Addendum 1 §11.4 row #1356 — silent auto-tag safety net.
    The safety net is **two-phase**:

    1. Compute orphan candidates and lineage-reference intersection
       (read-only — does not mutate the repository).
    2. Run ``git branch -d|-D``. If this raises (current-branch
       check, unmerged + non-force, race with concurrent delete),
       propagate the error and do NOT mutate refs.
    3. Only if the delete succeeded, write ``refs/scistudio/lineage/
       <sha>`` per intersection-set SHA.

    This ordering means a failed request leaves the repository in
    its original state — pins are never created without a successful
    delete (Codex P2 on PR #1381). The window between delete success
    and pin writes is microseconds; ``git gc`` does not run mid-call,
    and the reflog keeps the formerly-branch SHA reachable until our
    pin lands.

    Per owner decision 2026-05-21 this is intentionally silent: no
    warn / confirm dialog, no response payload change.

    TODO(#1380): cleanup mechanism for accumulated
    refs/scistudio/lineage/* refs.
      Out of scope per ADR-039 Addendum 1 §11.4 row #1356.
      Followup: https://github.com/zjzcpj/SciStudio/issues/1380
    """
    engine = _engine_for_request(request)
    runtime = request.app.state.runtime
    lineage_store = getattr(runtime, "lineage_store", None)

    # Phase 1: read-only orphan-candidate intersection. We compute
    # this BEFORE the delete because afterwards the orphan SHAs are
    # only reachable via the reflog, which our pin needs to capture
    # before the reflog default 90-day window expires.
    referenced_orphans: set[str] = set()
    if lineage_store is not None:
        orphan_candidates = engine.commits_reachable_only_from(name)
        if orphan_candidates:
            referenced_orphans = lineage_store.workflow_git_commits_in(list(orphan_candidates))

    try:
        # Phase 2: actual delete. Raises on current-branch / unmerged-
        # without-force / unknown-branch. Pins are NOT created on
        # failure path.
        engine.branch_delete(name, force=force)
    except GitError as exc:
        raise _git_error_to_http(exc) from exc

    # Phase 3: pin the lineage-referenced orphan SHAs now that the
    # delete succeeded. ``engine.tag`` is idempotent (update-ref
    # overwrite-by-default) so partial failure here can be re-driven
    # safely; we still log unexpected tag failures rather than
    # surfacing them to the client because the delete already
    # committed.
    for sha in referenced_orphans:
        try:
            engine.tag(f"refs/scistudio/lineage/{sha}", sha)
        except GitError:
            logger.exception(
                "branch_delete: failed to pin orphan SHA %s under refs/scistudio/lineage/",
                sha,
            )

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
    runtime = request.app.state.runtime
    project_dir = Path(runtime.active_project.path)
    before_ref = _capture_pre_op_ref(engine)
    try:
        result = engine.merge(body.source_branch)
    except GitError as exc:
        raise _git_error_to_http(exc) from exc
    # Hotfix #988 / ADR-045 §5.1 #5: FF / clean merges rewrite workflow YAMLs;
    # emit per-file workflow.changed even when conflicted_files is non-empty so
    # the user sees both the conflict UI AND the canvas reflecting the
    # pre-conflict half of the merge that did apply.
    await _emit_workflow_diff(
        runtime, project_dir, engine, before_ref, source="gitRestore", source_id=body.source_branch
    )
    return result


@router.post("/cherry-pick")
async def cherry_pick(request: Request, body: CherryPickRequest) -> dict[str, Any]:
    """Cherry-pick a commit onto current branch."""
    engine = _engine_for_request(request)
    runtime = request.app.state.runtime
    project_dir = Path(runtime.active_project.path)
    before_ref = _capture_pre_op_ref(engine)
    try:
        result = engine.cherry_pick(body.commit_sha)
    except GitError as exc:
        raise _git_error_to_http(exc) from exc
    await _emit_workflow_diff(
        runtime, project_dir, engine, before_ref, source="gitRestore", source_id=body.commit_sha
    )
    return result


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
    runtime = request.app.state.runtime
    project_dir = Path(runtime.active_project.path)
    before_ref = _capture_pre_op_ref(engine)
    try:
        sha = engine.merge_complete()
    except GitError as exc:
        raise _git_error_to_http(exc) from exc
    # Merge-complete is the final write in a conflict-resolution flow:
    # the staged conflict resolutions become the working tree. Emit so
    # the canvas reflects the resolved YAML.
    await _emit_workflow_diff(runtime, project_dir, engine, before_ref, source="gitRestore", source_id=sha)
    return {"status": "ok", "commit_sha": sha}


@router.post("/merge/abort")
async def merge_abort(request: Request) -> dict[str, str]:
    """Abort an in-progress merge or cherry-pick."""
    engine = _engine_for_request(request)
    runtime = request.app.state.runtime
    project_dir = Path(runtime.active_project.path)
    before_ref = _capture_pre_op_ref(engine)
    try:
        engine.merge_abort()
    except GitError as exc:
        raise _git_error_to_http(exc) from exc
    # Abort rewinds the working tree to the pre-merge state — workflow
    # YAML files revert too.
    await _emit_workflow_diff(
        runtime, project_dir, engine, before_ref, source="gitRestore", source_id="merge-abort"
    )
    return {"status": "ok"}
