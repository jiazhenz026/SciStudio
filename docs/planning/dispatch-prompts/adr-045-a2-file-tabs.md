[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-045 backend file-tab versioning so editable file saves and reads use the same versioned change contract as workflows.
- Task kind: bugfix
- Persona: implementer
- Issue: #1401
- Issue URL: https://github.com/zjzcpj/SciStudio/issues/1401
- Umbrella PR: pending - manager must replace this line with the `[DO NOT MERGE]` PR number before dispatch.
- Protected branch: main
- Umbrella branch: track/adr-045/version-vector
- Agent branch: feat/issue-1401/adr-045-file-tabs
- Agent worktree: `.claude/worktrees/adr-045-a2-file-tabs/` (provided by manager)
- Gate record: `.workflow/records/1401-a2-file-tabs.json`
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
`file.changed` payloads, runtime helper usage, and tests must describe one
contract. If the implementation needs a safer or narrower shape than the
current draft, update the governing ADR/spec in your PR or stop for manager
scope approval. Do not leave code/docs/test drift for full_audit to discover
later.

## Scope

You own only:

- `src/scistudio/api/routes/projects.py`
- Backend tests for file read/write versioning:
  - `tests/api/test_file_version_vector.py` (create or update)
  - `tests/api/test_projects.py` only for compatibility.
  - `tests/api/test_reload_on_save.py` only for reload-on-save coexistence.
- Your own gate record and only A2 rows in `docs/planning/adr-045-version-vector-checklist.md`.

You may read but must not edit:

- `src/scistudio/api/runtime.py`, `src/scistudio/engine/events.py`, and A1 code. If the A1 event/runtime helper you need is missing, stop and report the dependency instead of creating a conflicting local design.
- `frontend/src/**` - A3 owns frontend API/store/reconcile.
- `src/scistudio/api/routes/workflows.py`, `src/scistudio/api/routes/git.py`, `src/scistudio/api/routes/workflow_watcher.py` - A1 owns workflow versioning.
- ADR/spec/checklist rows not assigned to A2, except your own evidence rows.

If you need an out-of-scope path, stop and report back. Do not edit it.

## Coordination

- MUST work only on branch `feat/issue-1401/adr-045-file-tabs`.
- MUST work only in worktree `.claude/worktrees/adr-045-a2-file-tabs/`.
- MUST NOT use `pip install -e .`; use `PYTHONPATH=src`.
- Do not revert or overwrite other agents' work.
- Target your PR to `track/adr-045/version-vector`, not `main`.
- PR body must include `Closes #1401` or the manager-assigned open sub-issue.
- Do not merge any PR.
- Edit only A2 checklist rows and include command/report evidence.

## TODO And Deferral Rule

Deferred work must be tracked in the repo:

```python
# TODO(#1401): <what is deferred and why>
#   Out of scope per ADR-045 / adr-045-workflow-state-version.
#   Followup: <issue URL or tracking reference>.
```

Known out-of-scope items:

- Frontend file conflict UI is A3, not A2.
- Real-time collaboration, OT, CRDT, and global cross-workflow ordering are out of scope per ADR-045.
- Do not weaken block reload-on-save behavior while adding file.changed.

## Work To Do

1. Extend `GET /api/projects/{project_id}/file` response shape to include the current file entity version alongside existing `content`, `mtime`, `size`, and `encoding`.
2. Extend `PUT /api/projects/{project_id}/file` to accept optional `source_id`, return the new version, and emit `file.changed` after the atomic disk write completes.
3. Use the runtime/event helpers supplied by A1 for `(entity_class="file", entity_id=<project-relative path>)`.
4. Preserve ADR-036 reload-on-save behavior: clean `blocks/*.py` saves still emit `blocks.reloaded`, broken files still do not reload, and file.changed remains independent.
5. Add deterministic backend tests for file GET version, PUT version bump, source/source_id echo, `file.changed` payload fields, and reload-on-save coexistence.

## Required Tests And Checks

- `pytest tests/api/test_file_version_vector.py tests/api/test_projects.py tests/api/test_reload_on_save.py --timeout=60`
- `ruff check src/scistudio/api/routes/projects.py tests/api/test_file_version_vector.py tests/api/test_projects.py tests/api/test_reload_on_save.py`
- `ruff format --check src/scistudio/api/routes/projects.py tests/api/test_file_version_vector.py tests/api/test_projects.py tests/api/test_reload_on_save.py`
- `PYTHONPATH=src python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/adr-045-a2-full-audit.json`
- Sentrux pass evidence if available; otherwise record a gate-record skipped rationale.

## Gate Record Stages You Must Execute

Use `python -m scistudio.qa.governance.gate_record` with `.workflow/records/1401-a2-file-tabs.json`.

1. `start --task-kind bugfix --issue 1401 --slug a2-file-tabs --branch feat/issue-1401/adr-045-file-tabs --owner-directive "ADR-045 A2 backend file-tab versioning and file.changed events" --record-path .workflow/records/1401-a2-file-tabs.json`
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
- A1 runtime/event helpers are not available on the tracking branch.
- You need an out-of-scope file.
- You cannot preserve reload-on-save behavior.
- CI/local checks fail for reasons you cannot diagnose within reasonable effort.

## Codex Auto-Review Reconciliation

After your PR opens and CI runs, read every Codex auto-review comment and explicitly accept, defer with a tracked issue/TODO, or reject each one on the record before reporting done.
