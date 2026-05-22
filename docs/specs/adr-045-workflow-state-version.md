---
spec_id: adr-045-workflow-state-version
title: "ADR-045 Workflow And File State Version-Vector Implementation Specification"
status: Planned
feature_branch: track/adr-045/version-vector
created: 2026-05-22
input: "Owner directive to land ADR-045 by eliminating workflow/file state races across autosave, lineage restore, agent writes, external editor writes, and multi-session edits."
owners:
  - "@jiazhenz026"
related_adrs:
  - 45
related_specs: []
scope:
  in:
    - Server-authoritative per-entity version tracking for workflow YAML and editable file tabs.
    - Source-tagged workflow.changed and file.changed events from write sites.
    - Watcher fallback behavior for external writes after first-party write sites emit semantic events.
    - Frontend baseVersion, pendingVersion, and source_id reconciliation for workflow canvas and file tabs.
    - Conflict detection and minimum user choices for dirty local state versus newer remote state.
    - Regression coverage for autosave, lineage restore, agent write, external editor, and multi-session races.
  out:
    - Real-time collaborative editing, OT, or CRDT.
    - Global cross-workflow ordering.
    - Git ref versioning beyond existing SHA-based git.head_changed events.
    - Lineage run mutation semantics.
    - Project tree bulk invalidation redesign.
governs:
  modules:
    - scistudio.api.routes.workflow_watcher
    - scistudio.api.routes.workflows
    - scistudio.api.routes.projects
    - scistudio.api.routes.git
    - scistudio.api.runtime
    - scistudio.engine.events
  contracts:
    - scistudio.engine.events.EngineEvent
  entry_points: []
  files:
    - docs/adr/ADR-045.md
    - docs/specs/adr-045-workflow-state-version.md
    - docs/architecture/ARCHITECTURE.md
    - src/scistudio/api/routes/workflow_watcher.py
    - src/scistudio/api/routes/workflows.py
    - src/scistudio/api/routes/projects.py
    - src/scistudio/api/routes/git.py
    - src/scistudio/api/runtime.py
    - src/scistudio/engine/events.py
    - frontend/src/hooks/useWebSocket.ts
    - frontend/src/store/tabSlice.ts
    - frontend/src/store/types.ts
    - frontend/src/store/workflowSlice.ts
    - frontend/src/lib/api.ts
tests:
  - tests/api/test_workflow_version_vector.py
  - tests/api/test_file_version_vector.py
  - tests/api/test_workflow_changed_event_schema.py
  - tests/api/routes/test_workflow_watcher_fallback.py
  - frontend/src/hooks/__tests__/useWebSocket.versionVector.test.ts
  - frontend/src/store/__tests__/workflowSlice.versionVector.test.ts
  - frontend/src/store/__tests__/tabSlice.versionVector.test.ts
  - tests/integration/test_race_autosave.py
  - tests/integration/test_race_lineage_restore.py
  - tests/integration/test_race_agent_write.py
  - tests/integration/test_race_external_editor.py
  - tests/integration/test_race_multi_session.py
acceptance_source: adr
language_source: en
---

# Spec: ADR-045 Workflow And File State Version-Vector Implementation

## 1. Change Summary

This spec turns ADR-045 into an implementation plan. The implementation adds a
single server-authoritative version contract for two mutable entity classes:
workflow YAML and editable file tabs. Every first-party write site assigns the
next version, writes the entity, then emits a source-tagged WebSocket event.
The filesystem watcher remains only as a fallback for external writers that do
not go through SciStudio write sites.

The frontend records the last clean server version and the in-flight local
write identity per entity. Incoming events are reconciled by version and
source_id instead of timing windows. During the staged rollout, watcher
self-write suppression remains but is limited to exact originating write
signatures such as path, mtime, size, and delete kind.

The implementation is intentionally split so backend write-site events, file
tab versioning, frontend reconciliation, and integration audit can proceed in
parallel without overlapping write sets.

## 2. User Scenarios & Testing

### User Story 1 - Autosave Echoes Do Not Revert Newer Local Edits

As a workflow editor, I need a WebSocket echo from my own save to confirm the
saved version without overwriting changes I made after the save request left
the browser.

Independent test: simulate local mutation, save with source_id, second local
mutation, then workflow.changed echo for the first save. The second mutation
must remain in local state and baseVersion must advance only when the echo
matches the in-flight source_id.

### User Story 2 - Git Restore Emits Semantic Workflow Updates

As a user restoring a workflow through git, I need the canvas to refresh from
the restored content without briefly treating the workflow as deleted during an
atomic replacement or checkout sequence.

Independent test: run the restore/write path and assert workflow.changed emits
source `gitRestore`, a monotonic version, and no delete-clears-canvas path.

### User Story 3 - Agent Writes Surface As Remote Changes

As a user editing a workflow while an agent writes the same workflow, I need the
browser to detect that a remote source moved the server version and prompt
instead of silently replacing my unsaved canvas edits.

Independent test: dispatch an agent/source write while local pendingVersion is
greater than baseVersion. The client must enter conflict state and preserve
local content.

### User Story 4 - File Tabs Detect External Changes

As a user editing a Python, JSON, Markdown, or YAML file tab, I need the same
remote-change detection that workflow canvas gets.

Independent test: open a file tab, mark it dirty, emit file.changed with a
higher version from source `external`, and assert the tab records conflict
state without clearing local edits.

### User Story 5 - Multiple Sessions Converge Through Versioned Events

As a user with two browser sessions, I need clean sessions to refresh when a
newer version arrives and dirty sessions to prompt.

Independent test: session A writes version N+1, session B receives the event.
If B is clean, it fetches and adopts N+1. If B is dirty, it records a conflict.

## 3. Requirements

### Functional Requirements

- FR-001: The backend MUST maintain a monotonic integer version per
  `(entity_class, entity_id)` for workflow and file entities.
- FR-002: Backend GET responses for workflow and editable file content MUST
  return the current ADR-045 state version alongside existing content and mtime
  data. Workflow responses MUST expose that counter as `state_version` and MUST
  preserve `version` as the workflow YAML/schema semver string. Editable file
  responses MUST also expose the counter as `state_version` and MUST NOT add or
  repurpose a file-response `version` field.
- FR-003: Backend write responses MUST return the new ADR-045 state version and
  echo the client-provided source_id when present. Workflow write responses MUST
  expose that counter as `state_version` and MUST NOT repurpose the workflow
  YAML/schema `version` field. Editable file write responses MUST expose the
  counter as `state_version`; `file.changed` events continue to carry the event
  counter as `version`.
- FR-004: Every first-party workflow write site MUST emit workflow.changed
  after the disk write completes.
- FR-005: Every first-party editable file write site MUST emit file.changed
  after the disk write completes.
- FR-006: workflow.changed and file.changed events MUST include entity_class,
  entity_id, version, source, source_id, kind, and timestamp.
- FR-007: Watcher fallback MUST emit source `external` only for governed paths
  not already covered by a first-party write-site event.
- FR-008: Frontend workflow state MUST track baseVersion, pendingVersion, and
  pendingSourceId for the opened workflow.
- FR-009: Frontend file tabs MUST track baseVersion, pendingVersion, and
  pendingSourceId for editable file tabs.
- FR-010: The frontend MUST drop stale events whose version is not newer than
  the clean baseline.
- FR-011: The frontend MUST treat matching source_id/version events as
  confirmations of its own write, not as remote overwrites.
- FR-012: The frontend MUST refresh clean entities on newer remote events.
- FR-013: The frontend MUST preserve dirty local entities and surface conflict
  state on newer remote events.
- FR-014: Git ref change events remain SHA-versioned and MUST NOT be moved onto
  the workflow/file version counter.
- FR-015: Existing path normalization remains in the watcher; transient-delete
  and self-write heuristics may be deleted only after all relevant write sites
  emit versioned events.

### Non-Functional Requirements

- NFR-001: Version assignment must be deterministic and atomic from the API
  caller's perspective: the returned state version is the version broadcast in
  the event.
- NFR-002: Missing version fields from older events must fail safely through
  legacy behavior until all event sources are migrated.
- NFR-003: Event payload additions must remain backward-compatible for clients
  that ignore unknown fields.
- NFR-004: Conflict handling must never silently discard dirty local state.
- NFR-005: Tests must be deterministic and must not depend on filesystem mtime
  granularity or arbitrary sleep timing.

## 4. Implementation Plan

### 4.1 Technical Approach

Add version state to `ApiRuntime` and expose narrow helpers for workflow and
file write paths. Write routes pass source/source_id through these helpers and
emit versioned events after successful writes. The watcher consults the same
runtime state to suppress only exact first-party echoes and to classify
external writes.

Frontend API types carry `state_version`/`source_id` for workflow and editable
file responses. The changed-event payload keeps the shared event `version`
field. The workflow and tab stores record clean and pending versions.
`useWebSocket` becomes a dispatcher that applies ADR-045's four-branch
reconcile algorithm to workflow and file events.

Contract consistency is a release constraint for this rollout. ADR-045, this
spec, governed module/file lists, API response types, WebSocket event payloads,
runtime helpers, tests, and audit facts must describe the same contract. When
implementation proves a safer or narrower contract than the draft text, update
the ADR/spec in the same change instead of leaving documentation drift.

### 4.2 Affected Files

| File or glob | Action | Rationale |
|---|---|---|
| `src/scistudio/api/runtime.py` | modify | Own version map and write-site helper state. |
| `src/scistudio/api/routes/workflows.py` | modify | Return versions and emit versioned workflow events. |
| `src/scistudio/api/routes/projects.py` | modify | Return versions for file reads/saves and emit file.changed. |
| `src/scistudio/api/routes/git.py` | modify | Emit gitRestore workflow changes through write-site semantics. |
| `src/scistudio/api/routes/workflow_watcher.py` | modify | Demote watcher to fallback and simplify suppression. |
| `src/scistudio/engine/events.py` | modify | Carry version/source/entity fields where event objects are used. |
| `frontend/src/lib/api.ts` | modify | Type GET/PUT `state_version`/`source_id` fields and changed-event `version` fields. |
| `frontend/src/hooks/useWebSocket.ts` | modify | Apply version reconcile algorithm. |
| `frontend/src/store/workflowSlice.ts` | modify | Track workflow version state and conflict state. |
| `frontend/src/store/tabSlice.ts` | modify | Track file tab version state and conflict state. |
| `frontend/src/store/types.ts` | modify | Add shared version/conflict fields. |

### 4.3 Dispatch Tracks

| Track | Owner | Scope |
|---|---|---|
| A1 Backend workflow versioning | implementer | `ApiRuntime`, shared event payload fields, workflow routes, git restore, watcher fallback, backend workflow tests. |
| A2 Backend file versioning | implementer | project file GET/PUT routes, `file.changed`, reload-on-save coexistence, backend file tests. |
| A3 Frontend reconcile | implementer | API types, websocket handler, workflow slice, tab slice, conflict state, frontend tests. |
| A4 Audit | audit_reviewer | verify A1-A3 against ADR/spec, changed files, tests, and race matrix. |

### 4.4 Verification Plan

- Run backend API tests for workflow version responses, write-site event
  payloads, and watcher fallback behavior.
- Run backend API tests for editable file read/save version responses and
  file.changed event payloads.
- Run frontend store and websocket tests for stale event drop, self-write
  confirmation, clean remote refresh, and dirty conflict state.
- Run race-matrix tests for autosave, lineage restore, agent write, external
  editor, and multi-session scenarios.
- Run ADR-042 full audit and record output in `docs/audit/`.
- Run Sentrux evidence when available; otherwise record environment N/A in the
  gate record.

## 5. Acceptance Criteria

- AC-001: ADR-045 is Accepted and phase `implementation`; this spec is
  `Planned` before implementation agents start.
- AC-002: Full audit passes for the ADR/spec state transition before dispatch.
- AC-003: Backend workflow GET/write/event tests prove monotonic version and
  source_id propagation.
- AC-004: Backend file GET/write/event tests prove the same contract for file
  tabs.
- AC-005: Frontend websocket/store tests cover all four reconcile branches.
- AC-006: Watcher fallback no longer treats exact first-party write echoes as
  remote edits, and it still emits `source="external"` when the same path is
  modified again with a different file signature shortly afterward.
- AC-007: Dirty local workflow and file-tab state is never silently overwritten
  by newer remote events.
- AC-008: CI passes before final completion.

## 6. Risks And Rollback

The main risk is deleting watcher suppression before all write sites emit
versioned events. Mitigation: implementation tracks must keep existing
heuristics until targeted tests prove each write site has versioned emission.

The second risk is splitting workflow and file-tab work across agents while
sharing frontend API types. Mitigation: A2 and A3 have explicit write sets and
the manager sequences any shared `frontend/src/lib/api.ts` edits if needed.

Rollback is to keep the additive version fields ignored by the client and
restore the previous watcher/websocket behavior while retaining tests that
describe the still-open race.

## 7. Assumptions

- The implementation uses in-memory runtime version state for the first
  landing, as ADR-045 specifies.
- Version counters reset safely on server restart because clients refetch on
  reconnect or on newer event detection.
- `source_id` uniqueness is generated by the client for browser writes and by
  the backend or tool layer for non-browser writes.
- File-tab conflict UI may initially be state-only plus existing editor
  surfaces; richer diff UI can be a follow-up only if a tracked issue records
  the deferral.
