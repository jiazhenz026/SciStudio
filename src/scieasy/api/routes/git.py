"""Git REST API endpoints (ADR-039 §3.5).

Backs the v1 feature set:

- commit, log, diff, restore
- branch list / switch / create / delete
- status
- merge, cherry-pick (with conflict-resolution finalization)
- stash list / save / apply / drop
- merge-stage-file / merge-complete / merge-abort

Endpoint shapes match ADR-039 §3.5 table verbatim. Frontend
``frontend/src/lib/api.ts`` will declare matching function signatures.

Skeleton phase (D39-2.2a)
-------------------------

All handlers raise ``NotImplementedError``. Each handler carries a
≥20-line comment block specifying:

- the underlying ``GitEngine`` method to invoke
- the request schema (path / body params)
- the response schema (keys + types)
- error envelopes (HTTP status code per failure mode)
- edge cases the impl agent must cover
- ADR references (section + line)

The impl agent (D39-2.2b) fills bodies without re-reading the ADR.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/git", tags=["git"])


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


class CommitRequest(BaseModel):
    """``POST /api/git/commit`` body. ADR §3.5 line 217."""

    message: str = Field(..., description="Commit message (subject + optional body)")
    author: str | None = Field(
        default=None,
        description='Optional "Name <email>" override (else git config defaults)',
    )
    files: list[str] | None = Field(
        default=None,
        description="Optional list of repo-relative paths to limit the commit to",
    )


class CommitResponse(BaseModel):
    commit_sha: str


class RestoreRequest(BaseModel):
    """``POST /api/git/restore`` body. ADR §3.5 line 220, §3.6."""

    commit_sha: str
    files: list[str] | None = Field(
        default=None,
        description="Optional path list; None / empty = whole worktree",
    )


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
# Helper: resolve the active project's GitEngine
# ---------------------------------------------------------------------------


def _engine_for_request(request: Request) -> Any:
    """Construct a GitEngine for the active project.

    Implementation note for D39-2.2b
    --------------------------------
    1. ``runtime = request.app.state.runtime``.
    2. If ``runtime.active_project is None``: raise
       ``HTTPException(status_code=409, detail="No active project")``.
    3. ``project_path = Path(runtime.active_project.path)``.
    4. Construct and return ``GitEngine(project_path)``.

    The engine instance is cheap (lazy binary resolution), so we
    construct one per request rather than caching — keeps the
    ``app.state`` surface small.
    """
    raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")


# ---------------------------------------------------------------------------
# Commit / log / diff / restore endpoints
# ---------------------------------------------------------------------------


@router.post("/commit", response_model=CommitResponse)
async def commit(request: Request, body: CommitRequest) -> CommitResponse:
    """Create a new commit.

    Purpose
    -------
    User-driven manual commit (no ``prefix``). The pre-run auto-commit
    path and the agent-commit path do NOT go through this endpoint —
    they call ``GitEngine.commit`` directly with the appropriate prefix.

    Request schema
    --------------
    Body — :class:`CommitRequest`:

    - ``message`` (required) — must be non-empty after strip.
    - ``author`` (optional) — overrides git config user identity.
    - ``files`` (optional) — restrict the commit to these paths.

    Response schema
    ---------------
    :class:`CommitResponse` — ``{"commit_sha": "<40-char hex>"}``.

    Error envelopes
    ---------------
    - 400 — empty message (ValueError from engine).
    - 409 — nothing to commit (GitError "nothing to commit").
    - 500 — unexpected GitError.

    Implementation steps (D39-2.2b)
    -------------------------------
    1. ``engine = _engine_for_request(request)``.
    2. ``sha = engine.commit(body.message, files=body.files, author=body.author, prefix=None)``.
    3. Return ``CommitResponse(commit_sha=sha)``.
    4. Catch ``ValueError`` → 400; catch GitError("nothing to commit")
       → 409; re-raise other GitError → 500.

    Edge cases
    ----------
    - User clicks Commit twice rapidly — second one fails with "nothing
      to commit" (409). Frontend handles gracefully (button disabled
      after first click).
    - Author missing — engine uses git config which was set by
      :meth:`init_repository` to the SciEasy default identity (OQ-1).

    Test plan
    ---------
    - ``test_commit_endpoint_round_trip`` — POST → 200 with sha; GET
      /api/git/log returns it.
    - ``test_commit_endpoint_empty_message_400``.
    - ``test_commit_endpoint_clean_tree_409``.

    ADR references
    --------------
    - §3.5 line 217.
    """
    raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")


@router.get("/log")
async def log(
    request: Request,
    branch: str | None = None,
    limit: int | None = 500,
) -> list[dict[str, Any]]:
    """Return commit history.

    Purpose
    -------
    Feeds the GitHistoryList and GitGraph views.

    Query params
    ------------
    - ``branch`` (optional) — branch name; default None = ``--all`` (the
      graph view wants the full DAG; HistoryList may pin to a specific
      branch when the filter is set).
    - ``limit`` (optional) — int; default 500. Caps response size for
      large repos. UI virtualizes beyond this.

    Response schema
    ---------------
    List of dicts (see :meth:`GitEngine.log` docstring for exact field
    keys).

    Error envelopes
    ---------------
    - 500 — GitError.

    Implementation steps (D39-2.2b)
    -------------------------------
    1. ``engine = _engine_for_request(request)``.
    2. ``return engine.log(branch=branch, limit=limit)``.

    Edge cases
    ----------
    - Empty repo → engine returns ``[]``; this endpoint returns ``[]``.
    - ``limit=0`` — treat as unlimited? No — return ``[]``. Document.
      The UI never sends 0.

    Test plan
    ---------
    - ``test_log_endpoint_returns_commits`` — 3 commits, GET → 3 items.
    - ``test_log_endpoint_respects_limit`` — limit=1, len(response)==1.

    ADR references
    --------------
    - §3.5 line 218.
    """
    raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")


@router.get("/diff")
async def diff(
    request: Request,
    from_: str = Query(..., alias="from"),
    to: str | None = "WORKING",
    file: str | None = None,
) -> dict[str, str]:
    """Return a unified diff string.

    Note: ``from`` is a Python keyword, so we use ``from_`` with an
    alias. The HTTP query param is literally ``?from=...``.

    Query params
    ------------
    - ``from`` (required) — source ref (SHA / branch / "HEAD").
    - ``to`` (optional, default ``"WORKING"``) — target ref. Special
      values: ``"WORKING"`` (working tree), ``"HEAD"``, or any SHA.
    - ``file`` (optional) — single path filter. UI calls per-file; if
      future need arises for multi-file, the param becomes
      ``files=a&files=b``.

    Response schema
    ---------------
    ``{"diff": "<unified-diff-text>"}`` — single key so we can extend
    later (e.g. with ``binary: true`` flag) without breaking clients.

    Error envelopes
    ---------------
    - 404 — ref not found (GitError matching "unknown revision").
    - 500 — other GitError.

    Implementation steps (D39-2.2b)
    -------------------------------
    1. Engine call:
          ``text = engine.diff(from_, to if to != "WORKING" else None,
                               files=[file] if file else None)``
    2. Return ``{"diff": text}``.

    Edge cases
    ----------
    - Binary file — diff text contains "Binary files X and Y differ".
      Frontend detects this and renders a placeholder.
    - Identical refs — empty diff text. Frontend renders "No changes".

    Test plan
    ---------
    - ``test_diff_endpoint_commit_to_commit``.
    - ``test_diff_endpoint_commit_to_working``.
    - ``test_diff_endpoint_404_on_bad_sha``.

    ADR references
    --------------
    - §3.5 line 219.
    """
    raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")


@router.post("/restore")
async def restore(request: Request, body: RestoreRequest) -> dict[str, str]:
    """Restore files from a prior commit (soft restore default).

    Request body
    ------------
    :class:`RestoreRequest`:
    - ``commit_sha`` (required).
    - ``files`` (optional; None/empty = whole worktree).

    Response schema
    ---------------
    ``{"status": "ok"}`` (or potentially
    ``{"status": "stashed", "stash_id": "stash@{0}"}`` if auto-stash
    fired — caller renders StashApplyDialog).

    Implementation steps (D39-2.2b)
    -------------------------------
    1. ``engine = _engine_for_request(request)``.
    2. Before restore, check ``engine.head_state().dirty`` — if dirty,
       engine.restore will auto-stash; capture the new stash_id by
       calling ``engine.stash_list()[0]["stash_id"]`` afterward and
       include in response.
    3. ``engine.restore(body.commit_sha, files=body.files)``.

    Error envelopes
    ---------------
    - 404 — bad commit SHA.
    - 500 — other GitError.

    Edge cases
    ----------
    - Dirty tree → auto-stash; response signals via ``status=stashed``.
    - Restore-to-current-state — no-op succeeds.

    Test plan
    ---------
    - ``test_restore_endpoint_soft_restore``.
    - ``test_restore_endpoint_auto_stash_on_dirty``.

    ADR references
    --------------
    - §3.5 line 220, §3.6 lines 349-355.
    """
    raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")


# ---------------------------------------------------------------------------
# Branch endpoints
# ---------------------------------------------------------------------------


@router.get("/branches")
async def branches(request: Request) -> list[dict[str, Any]]:
    """List all local branches.

    Response schema
    ---------------
    ``[{"name": "main", "head_sha": "...", "is_current": true}, ...]``

    Implementation
    --------------
    1. ``engine = _engine_for_request(request)``.
    2. ``return engine.branches()``.

    Test plan
    ---------
    - ``test_branches_endpoint`` — fresh init + commit → one branch
      "main", is_current=True.

    ADR references
    --------------
    - §3.5 line 221.
    """
    raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")


@router.post("/branch/switch")
async def branch_switch(request: Request, body: BranchSwitchRequest) -> dict[str, str]:
    """Switch to an existing branch.

    Request: :class:`BranchSwitchRequest` ``{"branch_name": "..."}``.
    Response: ``{"status": "ok", "current_branch": "<name>"}``.

    Error envelopes
    ---------------
    - 404 — branch doesn't exist.
    - 409 — working tree dirty (caller should stash first).

    Implementation steps (D39-2.2b)
    -------------------------------
    1. ``engine.branch_switch(body.branch_name)``.
    2. Return ``{"status": "ok", "current_branch": body.branch_name}``.

    Edge cases
    ----------
    - Switching to current branch — git is silent, returns success;
      we follow.

    Test plan
    ---------
    - ``test_branch_switch_changes_head``.
    - ``test_branch_switch_dirty_tree_409``.

    ADR references
    --------------
    - §3.5 line 221, §3.7.
    """
    raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")


@router.post("/branch/create")
async def branch_create(request: Request, body: BranchCreateRequest) -> dict[str, str]:
    """Create a new branch at HEAD or specified base SHA.

    Request: :class:`BranchCreateRequest` ``{"name": "...", "base_sha": "..."?}``.
    Response: ``{"status": "ok", "name": "<name>"}``.

    Error envelopes
    ---------------
    - 400 — invalid name (git check-ref-format fails).
    - 409 — name already exists.

    Implementation steps (D39-2.2b)
    -------------------------------
    1. ``engine.branch_create(body.name, base=body.base_sha)``.
    2. Return ``{"status": "ok", "name": body.name}``.

    Edge cases
    ----------
    - Base SHA doesn't exist — GitError → 404.

    Test plan
    ---------
    - ``test_branch_create_at_head``.
    - ``test_branch_create_at_sha``.
    - ``test_branch_create_duplicate_409``.

    ADR references
    --------------
    - §3.5 line 221, §3.7.
    """
    raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")


@router.delete("/branches/{name}")
async def branch_delete(request: Request, name: str, force: bool = False) -> dict[str, str]:
    """Delete a local branch.

    Path param: ``name``. Query param: ``force=true`` to allow deletion
    of unmerged branches.

    Response: ``{"status": "ok"}``.

    Error envelopes
    ---------------
    - 404 — branch doesn't exist.
    - 409 — currently checked out (cannot delete) OR unmerged without
      force.

    Implementation steps (D39-2.2b)
    -------------------------------
    1. ``engine.branch_delete(name, force=force)``.
    2. Return ``{"status": "ok"}``.

    Test plan
    ---------
    - ``test_branch_delete_merged``.
    - ``test_branch_delete_unmerged_409``.
    - ``test_branch_delete_unmerged_force_ok``.
    - ``test_branch_delete_current_branch_409``.

    ADR references
    --------------
    - §3.5 line 221, §3.7.
    """
    raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")


# ---------------------------------------------------------------------------
# Status endpoint
# ---------------------------------------------------------------------------


@router.get("/status")
async def status_endpoint(request: Request) -> dict[str, Any]:
    """Return working-tree status.

    Response schema
    ---------------
    ``{"dirty": bool, "modified": [str], "staged": [str],
       "untracked": [str], "conflicted": [str]}``

    (Endpoint named ``status_endpoint`` in Python to avoid clobbering
    the ``http.HTTPStatus`` import idiom; the route path is ``/status``.)

    Implementation steps (D39-2.2b)
    -------------------------------
    1. ``engine = _engine_for_request(request)``.
    2. ``return engine.status()``.

    Edge cases
    ----------
    - Non-repo project (degraded mode) — runtime should not register
      this endpoint as available; for safety, return
      ``{"dirty": False, "modified": [], ...}`` if engine raises.

    Test plan
    ---------
    - ``test_status_clean``.
    - ``test_status_dirty_modified``.

    ADR references
    --------------
    - §3.5 line 222.
    """
    raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")


# ---------------------------------------------------------------------------
# Merge / cherry-pick
# ---------------------------------------------------------------------------


@router.post("/merge")
async def merge(request: Request, body: MergeRequest) -> dict[str, Any]:
    """Merge a branch into current.

    Request: :class:`MergeRequest` ``{"source_branch": "..."}``.

    Response schema
    ---------------
    ``{"result": "fast-forward" | "clean" | "conflict",
       "conflicted_files": [str, ...]}``

    Error envelopes
    ---------------
    - 404 — source branch doesn't exist.
    - 409 — dirty working tree.
    - 200 with ``result: "conflict"`` — NOT an error envelope; the
      frontend MergeFlow.tsx orchestrator drives resolution from here.

    Implementation steps (D39-2.2b)
    -------------------------------
    1. ``engine = _engine_for_request(request)``.
    2. ``return engine.merge(body.source_branch)``.

    Edge cases
    ----------
    - Already up to date — return ``{"result": "fast-forward",
      "conflicted_files": []}``.
    - Octopus merge — out of scope; reject in body validation if a
      future client tries to send multiple sources.

    Test plan
    ---------
    - ``test_merge_endpoint_fast_forward``.
    - ``test_merge_endpoint_clean``.
    - ``test_merge_endpoint_conflict``.

    ADR references
    --------------
    - §3.5 line 223, §3.5a (full conflict flow).
    """
    raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")


@router.post("/cherry-pick")
async def cherry_pick(request: Request, body: CherryPickRequest) -> dict[str, Any]:
    """Cherry-pick a commit onto current branch.

    Request: :class:`CherryPickRequest` ``{"commit_sha": "..."}``.

    Response — same shape as ``/merge`` minus "fast-forward":
    ``{"result": "clean" | "conflict", "conflicted_files": [...]}``.

    Implementation steps (D39-2.2b)
    -------------------------------
    1. ``return engine.cherry_pick(body.commit_sha)``.

    Edge cases
    ----------
    - Commit already in history — engine returns ``{"result": "clean",
      "conflicted_files": []}`` (no-op success).

    Test plan
    ---------
    - ``test_cherry_pick_endpoint_clean``.
    - ``test_cherry_pick_endpoint_conflict``.

    ADR references
    --------------
    - §3.5 line 224, §3.7.
    """
    raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")


# ---------------------------------------------------------------------------
# Stash CRUD
# ---------------------------------------------------------------------------


@router.get("/stash")
async def stash_list(request: Request) -> list[dict[str, Any]]:
    """List stashed changes.

    Response schema
    ---------------
    ``[{"stash_id": "stash@{0}", "message": "...", "date": "<iso>"}, ...]``

    Implementation
    --------------
    ``return engine.stash_list()``.

    Test plan
    ---------
    - ``test_stash_list_empty``.
    - ``test_stash_list_after_save``.

    ADR references
    --------------
    - §3.5 line 225.
    """
    raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")


@router.post("/stash/save")
async def stash_save(request: Request, body: StashSaveRequest) -> dict[str, str]:
    """Save current changes to a new stash.

    Request: :class:`StashSaveRequest` ``{"message": "..."?}``.
    Response: ``{"stash_id": "stash@{0}"}``.

    Error envelope
    --------------
    - 409 — nothing to stash (clean tree).

    Implementation
    --------------
    ``stash_id = engine.stash_save(message=body.message)``
    ``return {"stash_id": stash_id}``.

    Test plan
    ---------
    - ``test_stash_save_dirty_creates_stash``.
    - ``test_stash_save_clean_409``.

    ADR references
    --------------
    - §3.5 line 225, §3.6 line 354.
    """
    raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")


@router.post("/stash/apply")
async def stash_apply(request: Request, body: StashApplyRequest) -> dict[str, str]:
    """Apply a stash entry (without dropping it).

    Request: ``{"stash_id": "stash@{0}"}``.
    Response: ``{"status": "ok"}`` (or
    ``{"status": "conflict"}`` if apply produces conflicts — caller
    handles via the standard resolution UI).

    Implementation steps (D39-2.2b)
    -------------------------------
    1. ``engine.stash_apply(body.stash_id)``.
    2. Post-apply check :meth:`GitEngine.status` — if conflicted is
       non-empty, return ``{"status": "conflict",
       "conflicted_files": status["conflicted"]}``.
    3. Else return ``{"status": "ok"}``.

    Test plan
    ---------
    - ``test_stash_apply_clean``.
    - ``test_stash_apply_conflict``.
    - ``test_stash_apply_nonexistent_404``.

    ADR references
    --------------
    - §3.5 line 225.
    """
    raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")


@router.delete("/stash/{stash_id:path}")
async def stash_drop(request: Request, stash_id: str) -> dict[str, str]:
    """Drop a stash entry.

    Note: path converter ``:path`` because ``stash@{0}`` contains ``{``
    and ``}`` which FastAPI's default converter does not accept.

    Response: ``{"status": "ok"}``.

    Implementation
    --------------
    ``engine.stash_drop(stash_id)``; return ok.

    Test plan
    ---------
    - ``test_stash_drop_removes_entry``.
    - ``test_stash_drop_nonexistent_404``.

    ADR references
    --------------
    - §3.5 line 225.
    """
    raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")


# ---------------------------------------------------------------------------
# Conflict-resolution finalization
# ---------------------------------------------------------------------------


@router.post("/merge/stage-file")
async def merge_stage_file(request: Request, body: MergeStageFileRequest) -> dict[str, str]:
    """Stage a file after the user resolved its conflict markers.

    Request: ``{"file": "<repo-relative-path>"}``.
    Response: ``{"status": "ok"}`` or
    ``{"status": "still_conflicted"}`` if engine detected unresolved
    markers.

    Implementation steps (D39-2.2b)
    -------------------------------
    1. ``engine.merge_stage_file(body.file)``.
    2. If engine raises GitError("file still has conflict markers"),
       catch and return ``{"status": "still_conflicted"}`` with 409.
    3. Else return ``{"status": "ok"}``.

    Test plan
    ---------
    - ``test_stage_file_resolved`` — write resolved content, stage,
      conflicted list empty after.
    - ``test_stage_file_still_has_markers_409``.

    ADR references
    --------------
    - §3.5a lines 270-272.
    """
    raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")


@router.post("/merge/complete")
async def merge_complete(request: Request) -> dict[str, str]:
    """Finalize merge after all conflicts staged.

    No request body.
    Response: ``{"status": "ok", "commit_sha": "<new-merge-commit-sha>"}``.

    Error envelopes
    ---------------
    - 409 — conflicted entries still present, or no merge in progress.

    Implementation steps (D39-2.2b)
    -------------------------------
    1. ``sha = engine.merge_complete()``.
    2. Return ``{"status": "ok", "commit_sha": sha}``.

    Test plan
    ---------
    - ``test_merge_complete_creates_merge_commit``.
    - ``test_merge_complete_with_conflicts_409``.

    ADR references
    --------------
    - §3.5a lines 273-276.
    """
    raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")


@router.post("/merge/abort")
async def merge_abort(request: Request) -> dict[str, str]:
    """Abort an in-progress merge or cherry-pick.

    No request body.
    Response: ``{"status": "ok"}``.

    Error envelope
    --------------
    - 409 — no merge / cherry-pick in progress.

    Implementation
    --------------
    ``engine.merge_abort()``; return ok.

    Test plan
    ---------
    - ``test_merge_abort_restores_state``.
    - ``test_merge_abort_no_op_409``.

    ADR references
    --------------
    - §3.5a lines 275-276.
    """
    raise NotImplementedError("D39-2.2a skeleton — body filled by D39-2.2b")


# ---------------------------------------------------------------------------
# Helper: surface 4xx/5xx envelope for GitError → HTTPException
# ---------------------------------------------------------------------------

# (Helper to be filled by D39-2.2b — translates GitError stderr patterns
# into the right HTTP status code. Suggested pattern:
#
#   def _git_error_to_http(err: GitError) -> HTTPException:
#       msg = err.stderr.lower()
#       if "unknown revision" in msg or "not a valid object" in msg:
#           return HTTPException(404, err.stderr)
#       if "nothing to commit" in msg or "no local changes" in msg:
#           return HTTPException(409, err.stderr)
#       if "would be overwritten" in msg or "your local changes" in msg:
#           return HTTPException(409, err.stderr)
#       return HTTPException(500, err.stderr)
#
# Used by every handler's except block. Centralizes the mapping so
# error envelopes stay consistent across endpoints.)
