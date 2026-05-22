[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-045 frontend reconciliation so versioned workflow.changed and file.changed events never silently overwrite dirty local state.
- Task kind: bugfix
- Persona: implementer
- Issue: #1401
- Issue URL: https://github.com/zjzcpj/SciStudio/issues/1401
- Umbrella PR: pending - manager must replace this line with the `[DO NOT MERGE]` PR number before dispatch.
- Protected branch: main
- Umbrella branch: track/adr-045/version-vector
- Agent branch: feat/issue-1401/adr-045-frontend-reconcile
- Agent worktree: `.claude/worktrees/adr-045-a3-frontend-reconcile/` (provided by manager)
- Gate record: `.workflow/records/1401-a3-frontend-reconcile.json`
- Checklist: `docs/planning/adr-045-version-vector-checklist.md`
- Governing ADR/spec: `docs/adr/ADR-045.md`, `docs/specs/adr-045-workflow-state-version.md`

## Required Rules

Read and follow:

- GitHub issue #1401 and all owner instructions in it.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/bug-fix.md
- docs/ai-developer/personas/implementer.md
- ADR-045 and `docs/specs/adr-045-workflow-state-version.md`

## Contract Consistency Requirement

ADR-045, the spec, frontend API types, WebSocket event handling, store fields,
legacy fallback behavior, and frontend tests must describe one contract. If
the backend contract lands narrower or safer than the current draft, reconcile
the frontend types/tests and update governing docs or stop for manager scope
approval. Do not leave code/docs/test drift for full_audit to discover later.

## Scope

You own only:

- `frontend/src/lib/api.ts`
- `frontend/src/hooks/useWebSocket.ts`
- `frontend/src/store/workflowSlice.ts`
- `frontend/src/store/tabSlice.ts`
- `frontend/src/store/types.ts`
- Frontend tests:
  - `frontend/src/hooks/__tests__/useWebSocket.versionVector.test.ts` (create or update)
  - `frontend/src/store/__tests__/workflowSlice.versionVector.test.ts` (create or update)
  - `frontend/src/store/__tests__/tabSlice.versionVector.test.ts` (create or update)
  - Existing `frontend/src/store/__tests__/tabState.test.ts` only for compatibility.
- Minimal UI components only if required to expose ADR-045 conflict choices; if you need new visible UI outside these files, stop and ask manager to update scope first.
- Your own gate record and only A3 rows in `docs/planning/adr-045-version-vector-checklist.md`.

You must not touch:

- `src/scistudio/**` backend files - A1/A2 own backend contracts.
- `frontend/package-lock.json` unless a real dependency change is approved. Do not add dependencies for this task.
- ADR/spec/checklist rows not assigned to A3, except your own evidence rows.

If you need an out-of-scope path, stop and report back. Do not edit it.

## Coordination

- MUST work only on branch `feat/issue-1401/adr-045-frontend-reconcile`.
- MUST work only in worktree `.claude/worktrees/adr-045-a3-frontend-reconcile/`.
- MUST NOT use `pip install -e .`.
- Do not run `npm run dev` as a background service. Prefer `npm test` and `npm run build`; use browser smoke only with a manager-approved local server.
- Do not revert or overwrite other agents' work.
- Target your PR to `track/adr-045/version-vector`, not `main`.
- PR body must include `Closes #1401` or the manager-assigned open sub-issue.
- Do not merge any PR.
- Edit only A3 checklist rows and include command/report evidence.

## TODO And Deferral Rule

Deferred work must be tracked in the repo:

```ts
// TODO(#1401): <what is deferred and why>.
// Out of scope per ADR-045 / adr-045-workflow-state-version.
// Followup: <issue URL or tracking reference>.
```

Known out-of-scope items:

- Real-time collaboration, OT, CRDT, and global cross-workflow ordering are out of scope per ADR-045.
- Rich graph-level diff UI may be deferred only if the minimum conflict choices are implemented and a tracked TODO/follow-up is present.
- Do not remove existing autosave debounce; ADR-045 keeps it as UX behavior.

## Work To Do

1. Extend frontend API types and calls so workflow/file GET and PUT paths carry `version` and optional `source_id` from backend contracts.
2. Add workflow version state: `baseVersion`, `pendingVersion`, `pendingSourceId`, and conflict state for the active workflow/captured workflow tabs.
3. Add file tab version state replacing the conflict-detection role of `contentLoadedAt` without breaking persisted/re-hydrated tabs.
4. Implement ADR-045's four-branch reconcile algorithm in WebSocket handling for `workflow.changed` and `file.changed`:
   - drop stale events;
   - confirm matching source_id/version echoes;
   - refresh clean remote changes;
   - preserve dirty local content and surface conflict state on newer remote events.
5. Keep legacy behavior safe for events without version fields until A1/A2 are fully deployed.
6. Add deterministic vitest coverage for autosave echo, clean remote refresh, dirty workflow conflict, dirty file conflict, and legacy event fallback.

## Required Tests And Checks

- From `frontend/`: `npm test -- src/hooks/__tests__/useWebSocket.versionVector.test.ts src/store/__tests__/workflowSlice.versionVector.test.ts src/store/__tests__/tabSlice.versionVector.test.ts src/store/__tests__/tabState.test.ts`
- From `frontend/`: `npm run build`
- If visible conflict UI is added, run a live browser smoke against the relevant local target and record the result in the gate record.
- From repo root: `PYTHONPATH=src python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/adr-045-a3-full-audit.json`
- Sentrux pass evidence if available; otherwise record a gate-record skipped rationale.

## Gate Record Stages You Must Execute

Use `python -m scistudio.qa.governance.gate_record` with `.workflow/records/1401-a3-frontend-reconcile.json`.

1. `start --task-kind bugfix --issue 1401 --slug a3-frontend-reconcile --branch feat/issue-1401/adr-045-frontend-reconcile --owner-directive "ADR-045 A3 frontend version reconcile and conflict state" --record-path .workflow/records/1401-a3-frontend-reconcile.json`
2. `plan` with every planned file and required check.
3. `docs` with docs updated or a clear N/A if the governing spec is already sufficient.
4. `check` once per completed command.
5. `sentrux` pass or skipped rationale.
6. After commit and PR: `finalize` with commit SHA, PR URL/number, and body-closes evidence.

## Output Required

- Changed file paths.
- Tests/checks run and results.
- Checklist rows updated.
- PR number and URL targeting `track/adr-045/version-vector`.
- Gate record path and final stage status.
- Any blocker or scope issue.

## Stop Conditions

Stop and report back if:

- The umbrella PR line still says `pending` when you are dispatched.
- Backend event/response contracts from A1/A2 are not available on the tracking branch.
- You need an out-of-scope file.
- You cannot add deterministic frontend tests for the four reconcile branches.
- CI/local checks fail for reasons you cannot diagnose within reasonable effort.

## Codex Auto-Review Reconciliation

After your PR opens and CI runs, read every Codex auto-review comment and explicitly accept, defer with a tracked issue/TODO, or reject each one on the record before reporting done.
