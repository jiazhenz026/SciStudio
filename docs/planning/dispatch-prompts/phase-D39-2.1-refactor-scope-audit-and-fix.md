# [DISPATCH-TEMPLATE-V1: implement] Phase D39-2.1 — ADR-039 refactor-scope audit+fix

> This is a **combined audit + fix** agent. ADR-039's refactor surface is small
> enough that the same agent audits the current code, lists every site that
> needs to change, and applies the changes in a single PR — unlike the larger
> implementation phases which split skeleton + impl.

## Your task

ADR-039 mostly adds new feature surfaces (git engine, REST routes, frontend components), but it also **removes** a small set of pre-existing constructs:

1. `ApiRuntime.bump_revision` / `current_revision` — in-memory optimistic-concurrency counter that resets on server restart.
2. `If-Match` revision-header handling in `api/routes/workflows.py` — the HTTP enforcement path for the counter above.
3. Anywhere in the **frontend** that sets the `If-Match` header on workflow PUT/POST.
4. Any references to the revision-based ETag flow in tests, schemas, or docs.

It also adds **one small surface** to a pre-existing file:

5. Extend `api/routes/workflow_watcher.py` to also notice `.git/HEAD` changes and emit a `git.head_changed` engine event.
6. Subscribe to `git.head_changed` in `api/ws.py` and forward to clients.

Your job is to:

**Phase 2.1a (audit):** Audit `main` for every callsite of the four removal targets. ADR-039 §5.2 lists the obvious ones; you must find every additional callsite — frontend included (which the ADR §5.2 may have undercounted because of the Python-backend focus).

**Phase 2.1b (fix):** In the **same PR**, remove the four targets and add the two new surfaces (5, 6) per ADR-039 §3.8.

Read `docs/planning/agent-prompt-templates/00-common-boilerplate.md` first for the mandatory rules. The cascade context: ADR-038/039 implementation, plan file `~/.claude/plans/whimsical-soaring-pascal.md`, checklist `docs/planning/adr-038-039-checklist.md`, tracking branch `track/adr-039/git-versioning`.

## Owned files (your whitelist)

You may modify exactly these files:

- `src/scieasy/api/runtime.py` (remove `bump_revision`, `current_revision`, and any internal callers)
- `src/scieasy/api/routes/workflows.py` (remove `If-Match` header handling, remove the `revision` field from `WorkflowResponse` if no in-tree consumer remains — verify by grep)
- `src/scieasy/api/routes/workflow_watcher.py` (add `.git/HEAD` + `.git/refs/heads/*` mtime polling per ADR-039 §3.8; emit `git.head_changed` event with `{commit_sha, ref, kind}` payload)
- `src/scieasy/api/ws.py` (subscribe to `git.head_changed`, forward to all connected clients; per the common boilerplate, this is an authorized event-type addition since ADR-039 §3.8 explicitly mandates it)
- `src/scieasy/engine/events.py` (add `GIT_HEAD_CHANGED = "git.head_changed"` constant; this is the one authorized addition to the EventBus contract per the common boilerplate's "may NOT add new event types EXCEPT" clause)
- `frontend/src/lib/api.ts` (remove any `If-Match: ...` headers from workflow PUT calls)
- `frontend/src/hooks/useWebSocket.ts` (add a `git.head_changed` case stub that invalidates a placeholder `gitSlice` — actual gitSlice doesn't exist yet, that's D39-2.3a; leave a TODO)
- `frontend/src/store/workflowSlice.ts` (remove any `revision` field from workflow state if present)
- Any test file that directly tests bump_revision or If-Match (delete the test or rewrite for the new contract)
- `docs/planning/adr-038-039-checklist.md` — tick your row in the **D39-2.1** section with artifact link
- `CHANGELOG.md` — single `[Unreleased] > Changed` entry for this PR

## Out of scope (DO NOT TOUCH)

In addition to the common boilerplate's hard list:

- `src/scieasy/core/versioning/` — does not exist yet; D39-2.2a creates the skeleton
- `src/scieasy/api/routes/git.py` — does not exist yet; D39-2.2a creates the skeleton
- Any frontend `Git/` components — D39-2.3a creates the skeleton
- Any ADR file (cross-ref edits already done in Phase 0)
- ANY ADR-038 owned file (track/adr-038/ work is on a different tracking branch)

## Audit output

Before applying fixes, post a comment on your sub-issue listing every file × line that needs to change. This is the audit half. Then commit the actual fixes referencing that comment.

## Implementation requirements

1. Removing `bump_revision` / `current_revision`:
   - Delete the method bodies.
   - Delete any internal callers (likely in `save_workflow` and the workflow routes).
   - The previous behavior (in-memory counter for ETag) is replaced by **nothing** at v1 — the docs are clear that git is now the durable concurrency mechanism, and the existing `workflow_watcher` (extended to git events in this same PR) provides external-change detection. There is no ETag replacement to implement here.
2. Removing `If-Match` from `workflows.py`:
   - Drop the header parameter from PUT/POST handlers.
   - Drop the `412 Precondition Failed` branch.
   - `WorkflowResponse.revision` field: if no in-tree frontend consumer reads it (grep the frontend), drop it; otherwise, return `0` for one minor-version compat window with a TODO to remove. Document in the PR which case applied.
3. Removing frontend `If-Match`:
   - Grep `frontend/src/lib/api.ts` for the header; remove from request init objects.
   - Grep `frontend/src/store/workflowSlice.ts` for revision tracking; remove if dead.
4. Adding `.git/HEAD` watch:
   - Reuse the existing `workflow_watcher` polling loop pattern.
   - Watch `<project>/.git/HEAD` and `<project>/.git/refs/heads/*` mtimes (or use `watchdog` if it's already a dep — check `pyproject.toml`).
   - Emit `git.head_changed` event with payload `{commit_sha: <new HEAD SHA>, ref: "HEAD" | <branch ref>, kind: "head" | "refs"}`.
   - Add an integration test that simulates an external `git commit` and asserts the event fires.
5. WebSocket forwarding:
   - Subscribe to the new event in the `/ws` outbound loop; serialize to JSON and send as a `git.head_changed` frame.
   - Test: with a connected `/ws` client and an external commit simulated, the client receives the frame within 1s.

## Tests required

- `tests/api/test_workflow_watcher_git.py` (NEW): `.git/HEAD` change emits event; `.git/refs/heads/<branch>` change emits event; multiple changes within debounce window collapse.
- `tests/api/test_ws_git_events.py` (NEW): WS client receives `git.head_changed` frame.
- `tests/api/test_workflow_routes.py` (EXISTING): assert PUT no longer requires `If-Match`; assert 412 no longer emitted.
- All pytest invocations use `--timeout=60`.

## Definition of done

- All four removal targets fully gone from backend and frontend (grep confirms zero matches).
- New `git.head_changed` event flows from filesystem → engine → WebSocket → frontend hook (stub).
- pytest green; ruff/mypy clean; vitest green for frontend.
- PR opened against `track/adr-039/git-versioning`, body has `Closes #<sub-issue>`, all CI checks pass.
- Codex auto-review comments reconciled.
- Cascade checklist updated (D39-2.1 row ticked with PR link).
- CHANGELOG entry added.
