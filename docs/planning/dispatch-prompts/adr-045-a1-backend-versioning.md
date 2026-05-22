[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-045 server-authoritative workflow versioning so workflow.changed events are semantic, source-tagged, and race-safe.
- Task kind: bugfix
- Persona: implementer
- Issue: #1401
- Issue URL: https://github.com/zjzcpj/SciStudio/issues/1401
- Umbrella PR: pending - manager must replace this line with the `[DO NOT MERGE]` PR number before dispatch.
- Protected branch: main
- Umbrella branch: track/adr-045/version-vector
- Agent branch: feat/issue-1401/adr-045-backend-versioning
- Agent worktree: `.claude/worktrees/adr-045-a1-backend-versioning/` (provided by manager)
- Gate record: `.workflow/records/1401-a1-backend-versioning.json`
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

ADR-045, the spec, governed files/contracts, backend response models,
`workflow.changed` payloads, runtime helper signatures, and tests must describe
one contract. If the implementation needs a safer or narrower shape than the
current draft, update the governing ADR/spec in your PR or stop for manager
scope approval. Do not leave code/docs/test drift for full_audit to discover
later.

## Scope

You own only:

- `src/scistudio/api/runtime.py`
- `src/scistudio/api/routes/workflows.py`
- `src/scistudio/api/routes/git.py`
- `src/scistudio/api/routes/workflow_watcher.py`
- `src/scistudio/engine/events.py`
- `tests/api/test_workflow_version_vector.py` (create or update)
- `tests/api/test_workflow_changed_event_schema.py` (create or update)
- `tests/api/routes/test_workflow_watcher_fallback.py` (create or update)
- Existing focused tests in `tests/api/test_workflows.py`, `tests/api/test_git_endpoints.py`, and `tests/api/test_workflow_watcher.py` only when needed for compatibility.
- Your own gate record and only A1 rows in `docs/planning/adr-045-version-vector-checklist.md`.

You must not touch:

- `src/scistudio/api/routes/projects.py` - A2 owns file route versioning.
- `frontend/src/**` - A3 owns all frontend reconciliation.
- `packages/**`, `src/scistudio/blocks/**`, `src/scistudio/workflow/**` unless a stop condition is approved by the manager.
- ADR/spec/checklist rows not assigned to A1, except your own evidence rows.

If you need an out-of-scope path, stop and report back. Do not edit it.

## Coordination

- MUST work only on branch `feat/issue-1401/adr-045-backend-versioning`.
- MUST work only in worktree `.claude/worktrees/adr-045-a1-backend-versioning/`.
- MUST NOT use `pip install -e .`; use `PYTHONPATH=src`.
- Do not revert or overwrite other agents' work.
- Target your PR to `track/adr-045/version-vector`, not `main`.
- PR body must include `Closes #1401` or the manager-assigned open sub-issue.
- Do not merge any PR.
- Edit only A1 checklist rows and include command/report evidence.

## TODO And Deferral Rule

Deferred work must be tracked in the repo:

```python
# TODO(#1401): <what is deferred and why>
#   Out of scope per ADR-045 / adr-045-workflow-state-version.
#   Followup: <issue URL or tracking reference>.
```

Known out-of-scope items:

- Real-time collaboration, OT, CRDT, and global cross-workflow ordering are out of scope per ADR-045.
- Do not delete watcher heuristics unless your tests prove every affected workflow write site emits a versioned semantic event.
- Git ref events stay SHA-versioned; do not move `git.head_changed` onto workflow/file counters.

## Work To Do

1. Add the backend version-state primitive in `ApiRuntime` for `(entity_class, entity_id)` with deterministic monotonic versions initialized safely from disk state where needed.
2. Extend workflow GET/write responses and workflow.changed event payloads with ADR-045 fields: `entity_class`, `entity_id`, `version`, `source`, `source_id`, `kind`, and `timestamp`.
3. Route workflow create/import/update and git restore/checkout write sites through the versioned emit contract after disk writes complete.
4. Keep watcher fallback behavior for external workflow writes and ensure first-party workflow writes are not double-emitted as remote deletes.
5. Preserve backwards-compatible event handling for clients that ignore unknown fields.
6. Add deterministic backend tests for monotonic workflow versions, source/source_id propagation, gitRestore source, stale watcher suppression, and external fallback.

## Required Tests And Checks

- `pytest tests/api/test_workflow_version_vector.py tests/api/test_workflow_changed_event_schema.py tests/api/routes/test_workflow_watcher_fallback.py tests/api/test_workflows.py tests/api/test_git_endpoints.py tests/api/test_workflow_watcher.py --timeout=60`
- `ruff check src/scistudio/api/runtime.py src/scistudio/api/routes/workflows.py src/scistudio/api/routes/git.py src/scistudio/api/routes/workflow_watcher.py src/scistudio/engine/events.py tests/api/test_workflow_version_vector.py tests/api/test_workflow_changed_event_schema.py tests/api/routes/test_workflow_watcher_fallback.py`
- `ruff format --check src/scistudio/api/runtime.py src/scistudio/api/routes/workflows.py src/scistudio/api/routes/git.py src/scistudio/api/routes/workflow_watcher.py src/scistudio/engine/events.py tests/api/test_workflow_version_vector.py tests/api/test_workflow_changed_event_schema.py tests/api/routes/test_workflow_watcher_fallback.py`
- `PYTHONPATH=src python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/adr-045-a1-full-audit.json`
- Sentrux pass evidence if available; otherwise record a gate-record skipped rationale.

## Gate Record Stages You Must Execute

Use `python -m scistudio.qa.governance.gate_record` with `.workflow/records/1401-a1-backend-versioning.json`.

1. `start --task-kind bugfix --issue 1401 --slug a1-backend-versioning --branch feat/issue-1401/adr-045-backend-versioning --owner-directive "ADR-045 A1 backend workflow versioning and watcher fallback" --record-path .workflow/records/1401-a1-backend-versioning.json`
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
- You need an out-of-scope file.
- You cannot preserve existing workflow.changed compatibility.
- CI/local checks fail for reasons you cannot diagnose within reasonable effort.
- Another agent's work blocks or conflicts with yours.

## Codex Auto-Review Reconciliation

After your PR opens and CI runs, read every Codex auto-review comment and explicitly accept, defer with a tracked issue/TODO, or reject each one on the record before reporting done.
