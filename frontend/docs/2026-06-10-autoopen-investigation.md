# Investigation: prod YAML auto-open intermittently fails after agent `write_workflow` (#1322)

Date: 2026-06-10
Author: F1 frontend implementer (AI-assisted)
Status: root-cause hypotheses + low-risk defensive logging applied; no
behaviour change. Recommendation: keep #1322 open as INVESTIGATE until the
next prod recurrence produces the new diagnostic logs.

## Symptom

In a production build, when an AI agent creates a new workflow YAML via the
MCP `write_workflow` tool, the GUI does **not** auto-open it as a canvas
tab. The dev environment works. The 2026-05-21 hotfix session confirmed the
backend emits the correct WS frame
(`workflow.changed kind="created" workflow_id=...`) but could not reproduce
the missing auto-open, and the owner then reported behaviour was normal.

## Current code path (post #1413/#1414 refactor)

The issue references `frontend/src/hooks/useWebSocket.ts:78-98`, but that
auto-open block was extracted in #1413/#1414. It now lives in
`frontend/src/hooks/useWebSocket.parts/handleWorkflowChanged.ts`:

1. WS `onmessage` -> `dispatchWorkflowEvent` -> `handleWorkflowChanged`.
2. `handleWorkflowChanged` always calls `bumpProjectTreeRefresh()`, then
   `parseWorkflowChangedPayload`. If no `changedId` can be derived it
   returns.
3. `isUnopenedCreatedWorkflow(ctx)` gates the auto-open. It requires
   **`ctx.kind === "created"`** AND no existing workflow tab with
   `workflowId === changedId`.
4. If so, `autoOpenCreatedWorkflow(changedId)` does
   `api.getWorkflow(changedId)` then `openTab(fresh, changedId)`.

There is a second, independent auto-open path on `workflow_started`
(`handleLifecycle.ts::handleWorkflowStartedAutoOpen`) used when an agent
*runs* a workflow. That path is NOT triggered by a plain `write_workflow`
(no run), so a pure create relies entirely on the `kind === "created"`
gate.

## Backend emit path (for context; not modified — out of scope)

`src/scistudio/api/routes/workflow_watcher.py::_WorkflowFileHandler.on_any_event`
maps watchdog events to the wire `kind`:

- `FileCreatedEvent` -> `"created"`
- `FileModifiedEvent` -> `"modified"`
- `FileMovedEvent` (tmp -> final, the atomic `os.replace` case) ->
  forced to `"created"` (line ~160).

It then applies, in order: first-party-write suppression, transient-delete
suppression, **self-write `(path, mtime, size)` suppression**, and a
**200 ms per-path debounce**. `src/scistudio/api/ws.py::serialise_event`
puts `workflow_id` at the top level from `event.data["workflow_id"]`, which
the frontend reads first — so the `changedId` derivation is sound.

## Root-cause hypotheses (ranked)

### H1 (most likely) — `kind` is not reliably `"created"` for a new file

The auto-open is strictly gated on `kind === "created"`. The wire `kind`
depends on which watchdog event the OS delivers *first* and on the
suppression/debounce pipeline:

- An atomic write is `tmp` write -> `os.replace(tmp, final)`. On some
  platforms the **create** of the final name is delivered as a
  `FileModifiedEvent` (or the create is coalesced), yielding
  `kind="modified"`.
- The 200 ms debounce collapses a create+modify burst to a single event;
  if the create is the one that loses (e.g. it was self-write/transient
  suppressed) the surviving event can be `modified`.
- Watchdog event coalescence on Windows (issue hypothesis #2) can present
  a single `modified` for an atomic create.

When the surviving frame is `kind="modified"`, `isUnopenedCreatedWorkflow`
returns false. Because the new workflow is also not the *current* canvas
workflow, `handleWorkflowChanged` then returns without opening anything —
**silent no-op**, exactly matching the symptom. This is platform/timing
dependent, which explains the intermittency and the dev-vs-prod split.

### H2 — `getWorkflow` races the not-yet-flushed file

`autoOpenCreatedWorkflow` fetches via `api.getWorkflow(changedId)`
immediately. If the WS frame is observed before the YAML is fully visible
to the API process (rare, but possible with the debounce/replace timing),
the GET can 404/throw and the `.catch` swallows it — again a silent
no-op. The dev environment's faster, single-process timing would hide
this.

### H3 — stale static bundle (issue hypothesis #1)

A pip-installed package shipping a static bundle from before the auto-open
fix would never auto-open. This is an install/packaging issue, not a code
bug, and is consistent with "dev works, prod doesn't". Cannot be confirmed
from the frontend source.

### H4 (ruled low) — dedupe-key mismatch in `openTab`

`openTab(fresh, changedId)` dedupes on `fresh.id || changedId`. If a YAML
omits `id` (the #796 case), `fresh.id` is `""` and the dedupe falls back to
`changedId`, while `isUnopenedCreatedWorkflow` checks `workflowId ===
changedId` and the created tab's `workflowId` resolves to `changedId` too.
These are consistent, so this is unlikely to be the cause — but the new
debug log records `fresh.id` so we can confirm if it ever diverges.

## Evidence

- WS frame correctness was confirmed live in the 2026-05-21 hotfix session
  (recorded on the issue).
- Code inspection shows the only create-time auto-open trigger is the
  `kind === "created"` gate; there is no `modified`/`created` fallback for
  an unopened workflow.
- The backend pipeline has multiple legitimate ways to emit `modified`
  instead of `created` for an atomic new-file write.

## What was changed in this PR

Low-risk, behaviour-preserving diagnostics only, in
`handleWorkflowChanged.ts::autoOpenCreatedWorkflow`:

- `console.debug` when the auto-open fetch starts, when the tab is opened
  (logging the fetched `fresh.id` for H4), and when `getWorkflow` fails
  (surfacing H2 instead of swallowing it silently).

No change to the auto-open gating was made. Broadening the gate to also
auto-open on `kind === "modified"` for an unopened workflow was considered
and **rejected**: it would auto-open a tab on every external save of any
workflow the user has never opened (tab spam), and it cannot distinguish a
brand-new file from an edit to an existing-but-unopened one without extra
backend signal.

## Recommendation / follow-up

1. Keep #1322 open as INVESTIGATE. The added debug logs make the next prod
   recurrence diagnosable per the issue's repro guidance (capture every
   `workflow.*` frame and check whether `openTab` fired).
2. If H1 is confirmed by a recurrence, the durable fix belongs on the
   **backend** watcher (out of scope for F1): guarantee a `created` kind
   for atomic new-file writes (e.g. track known workflow paths and emit
   `created` when a path is seen for the first time, regardless of the
   raw watchdog event class). File this as a backend bugfix referencing
   #1322 when confirmed.
3. If H3 is confirmed, it is a packaging/release task (ensure the prod
   wheel ships the rebuilt static bundle), not a code fix.

No new follow-up issue is filed yet because #1322 already tracks this
investigation and the durable fix (if any) is backend-side and gated on a
confirmed recurrence.
