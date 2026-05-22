[DISPATCH-TEMPLATE-V1: audit-with-context]

## Task Identity

- Repository: SciStudio
- Persona: audit_reviewer
- Audit mode: with-context
- Issue: #1401
- Issue URL: https://github.com/zjzcpj/SciStudio/issues/1401
- Owner request: Audit the ADR-045 implementation outputs for workflow/file version-vector race fixes before manager integration.
- Umbrella PR: pending - manager must replace this line with the `[DO NOT MERGE]` PR number before dispatch.
- Protected branch: main
- Umbrella branch: track/adr-045/version-vector
- Audit branch: audit/issue-1401/adr-045-version-vector
- Audit worktree: `.claude/worktrees/adr-045-a4-audit/`
- Gate record: `.workflow/records/1401-a4-audit.json`
- Checklist: `docs/planning/adr-045-version-vector-checklist.md`
- PRs or commits to audit: pending A1/A2/A3 PR URLs - manager must replace before dispatch.
- Audit report path: `docs/audit/adr-045-implementation-audit.md`

## Required Reading

Read and follow:

- GitHub issue #1401 and all owner instructions in it.
- The manager checklist.
- A1/A2/A3 PR descriptions, changed files, CI, gate records, and checklist rows.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/personas/audit-reviewer.md
- docs/adr/ADR-045.md
- docs/specs/adr-045-workflow-state-version.md

## Contract Consistency Requirement

Treat contract consistency as a merge gate, not a documentation nicety. ADR-045,
the spec, governed files/contracts, backend response models, WebSocket payloads,
frontend API/store types, tests, gate records, and audit facts must all describe
the same behavior. If code is better than docs, require a docs update; if docs
are stronger than code, classify the gap as a finding.

## Audit Goal

Verify the claimed A1/A2/A3 work against ADR-045, the spec, tests, gate evidence, and CI. Findings first, ordered by severity:

- P1: blocks merge or breaks ADR/spec contract.
- P2: should fix before completion.
- P3: improvement or tracked follow-up.

## Scope

Audit these claims:

- Backend workflow GET/write/event paths use a server-authoritative monotonic version and source/source_id contract.
- Git restore/write-site events are semantic workflow.changed events and no longer rely on transient delete behavior.
- Watcher fallback handles external workflow changes without treating first-party writes as remote deletes.
- Backend file GET/PUT emits `file.changed` with version/source/source_id and preserves reload-on-save semantics.
- Frontend workflow and file state track clean baseline, pending write identity, stale event drop, self-write confirmation, clean remote refresh, and dirty conflict state.
- Tests cover autosave echo, lineage/git restore, agent/remote write, external editor, and multi-session race shapes or explicitly justified reduced unit coverage.

Audit these files or surfaces:

- `docs/adr/ADR-045.md`
- `docs/specs/adr-045-workflow-state-version.md`
- `src/scistudio/api/runtime.py`
- `src/scistudio/api/routes/workflows.py`
- `src/scistudio/api/routes/git.py`
- `src/scistudio/api/routes/workflow_watcher.py`
- `src/scistudio/api/routes/projects.py`
- `src/scistudio/engine/events.py`
- `frontend/src/lib/api.ts`
- `frontend/src/hooks/useWebSocket.ts`
- `frontend/src/store/workflowSlice.ts`
- `frontend/src/store/tabSlice.ts`
- `frontend/src/store/types.ts`
- `tests/api/test_workflow_version_vector.py`
- `tests/api/test_file_version_vector.py`
- `tests/api/test_workflow_changed_event_schema.py`
- `tests/api/routes/test_workflow_watcher_fallback.py`
- `frontend/src/hooks/__tests__/useWebSocket.versionVector.test.ts`
- `frontend/src/store/__tests__/workflowSlice.versionVector.test.ts`
- `frontend/src/store/__tests__/tabSlice.versionVector.test.ts`
- A1/A2/A3 gate records and audit outputs.

Do not write feature code. Only write:

- `docs/audit/adr-045-implementation-audit.md`
- `.workflow/records/1401-a4-audit.json`
- A4 rows in `docs/planning/adr-045-version-vector-checklist.md`

## Coordination

- MUST work only on branch `audit/issue-1401/adr-045-version-vector`.
- MUST work only in worktree `.claude/worktrees/adr-045-a4-audit/`.
- MUST NOT use `pip install -e .`; use `PYTHONPATH=src`.
- MUST NOT merge any PR.
- MUST NOT fix implementation code unless the manager changes your role to fix agent.
- Edit only A4 checklist audit rows.

## Checks

Run or verify:

- `PYTHONPATH=src python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/adr-045-a4-full-audit.json`
- A1/A2 backend pytest commands from their prompts, or an equivalent narrowed set justified in the report.
- A3 frontend vitest/build commands from its prompt.
- Sentrux pass evidence if available; otherwise record an explicit skipped rationale.
- Frontend/browser smoke if A3 added visible conflict UI; otherwise record N/A.

## Output Required

- Audit report path.
- Commit or PR containing the audit report.
- Findings ordered by severity.
- Checklist drift, if any.
- Scope drift, if any.
- Missing tests/docs/gate evidence, if any.
- CI status.
- Recommendation: pass, pass-with-fixes, or block.

## Stop Conditions

Stop and report back if:

- The umbrella PR line or A1/A2/A3 PR list still says `pending` when you are dispatched.
- You need to change implementation code.
- Required evidence is unavailable.
- The audit scope conflicts with AGENTS.md, ADR, spec, or gate record.
