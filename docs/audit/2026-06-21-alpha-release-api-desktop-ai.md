---
title: "Alpha Release Audit 20260621 - API, Desktop, AI"
status: Draft
owners:
  - "@jiazhenz026"
related_adrs:
  - 14
  - 35
  - 40
  - 42
issue: 1733
umbrella_pr: 1734
audit_agent: A3-api-desktop-ai
audit_persona: audit_reviewer
recommendation: pass-with-must-fix
language_source: en
---

# Alpha Release Audit 20260621 - API, Desktop, AI

Audit target: `track/alpha-release-audit-20260621` at `410e1253`.

## Findings

### P0 - Alpha Release Block

None found in the scoped API, desktop, AI orchestration, and runtime bridge surfaces.

### P1 - Must Fix Or Explicitly Risk Accept

#### A3-P1-1 - AI Block tab cancel is implemented as "mark done", not cancellation

The AI Block manual-review cancel path does not preserve user intent. ADR-035 says a user closing the tab transitions the block to `CANCELLED` and terminates the process tree: `docs/adr/ADR-035.md:155-167` and `docs/adr/ADR-035.md:291-304`. The current WebSocket handler instead maps `block_user_cancel` to the same `mark_done.json` signal used by the "Mark done" button: `src/scistudio/api/ws.py:306-330`. The comment explicitly says this treats a running-tab close as user-initiated completion while full cancellation is deferred.

That signal is consumed as `CompletionSource.USER_MARK_DONE`, returning the declared output paths: `src/scistudio/blocks/ai/completion.py:237-249`. `AIBlock.run()` then validates those outputs and notifies the engine with `event="completed"`: `src/scistudio/blocks/ai/ai_block.py:365-380`. The code path that produces a true cancelled block state is the watcher cancellation path: `src/scistudio/blocks/ai/completion.py:147-149`, `src/scistudio/blocks/ai/completion.py:261-267`, and `src/scistudio/blocks/ai/ai_block.py:352-359`; the WebSocket cancel frame does not trigger it. The regression test pins the current behavior by asserting `block_user_cancel` writes `mark_done.json`: `tests/api/test_ai_pty_audit_fixes.py:233-263`.

Impact: an alpha tester can attempt to cancel a manual-review AI block and instead drive the workflow toward validation and possible `DONE` if the expected outputs exist. If validation fails, the terminal state is `ERROR`, not the requested `CANCELLED`. This violates the alpha entry bar that manual review and AI orchestration cannot silently bypass user intent or runtime state: `docs/audit/2026-06-21-alpha-release-criteria.md:49-57`.

Required remediation: make `block_user_cancel` a real runtime cancellation, for example by translating the tab id/block run id into the scheduler cancellation path. There is already a helper whose docstring says it exists for translating `block_user_cancel` to `CANCEL_BLOCK_REQUEST`: `src/scistudio/api/routes/ai_pty/engine.py:46-52`. Add a regression test that a user cancel produces `BlockState.CANCELLED`, not `mark_done.json` completion.

#### A3-P1-2 - The governing AI Block contract is not alpha-current

ADR-035 is still marked `status: Proposed` with `date_accepted: null`: `docs/adr/ADR-035.md:1-7`. Its body says implementation is pending and should be promoted when the implementation issue ships: `docs/adr/ADR-035.md:65-70`. At the same time, the codebase has shipped an AI Block PTY implementation: `src/scistudio/blocks/ai/ai_block.py:1-9`, a FastAPI AI PTY bridge, and passing scoped AI PTY/MCP tests.

The ADR also presents current-seeming guarantees and risks that need alpha-grade acceptance: all three completion paths are described as supported (`docs/adr/ADR-035.md:247-257`), bypass mode is documented as full filesystem reach without SciStudio confinement (`docs/adr/ADR-035.md:271-279`), and the risk section says this must be surfaced prominently to users (`docs/adr/ADR-035.md:408-412`). Later sections still describe PoC/core implementation as future work: `docs/adr/ADR-035.md:416-432`.

Impact: release review cannot use the governing doc as reliable alpha evidence for manual review, cancellation, permission, and no-sandbox behavior. The release criteria require known limitations to be documented with severity/follow-up ownership and core contracts to either reject invalid input or document allowed instability: `docs/audit/2026-06-21-alpha-release-criteria.md:49-57`.

Required remediation: before alpha, update or add an accepted ADR addendum/known-limitations entry that describes the actual shipped AI Block/manual-review behavior, explicitly records no-confinement/bypass risk acceptance, and removes or resolves the stale "implementation pending" language. This should happen alongside the cancel-path fix or an explicit owner risk acceptance.

### P2 - Good To Fix Before Broader Alpha Testing

#### A3-P2-1 - Active workflow context can surface orphan or stale workflow ids to the AI agent

`POST /api/ai/active-context` directly sets whatever non-empty workflow id the caller sends: `src/scistudio/api/routes/ai.py:52-66`. `ApiRuntime.set_active_workflow_id()` normalizes empty strings but does not validate that a project is open or that the workflow exists: `src/scistudio/api/runtime/_projects.py:489-499`. If no project is active, persistence is skipped while the in-memory id remains set: `src/scistudio/api/runtime/_projects.py:465-474`.

The MCP tool then returns that id as editor context, even when name resolution fails: `src/scistudio/ai/agent/mcp/tools_workflow/read.py:301-350`. The test suite explicitly pins the no-project case by posting `"orphan"` and expecting `runtime.active_workflow_id == "orphan"`: `tests/api/test_ai_active_context.py:58-66`.

Impact: backend/runtime remains authoritative when the agent later calls `get_workflow`, but the "current workflow" hint can misdirect the AI agent in no-project or stale-tab cases. That is a small but real backend-truth semantics leak.

Suggested remediation: reject active-context updates when no project is open, validate the id against project workflows, or return an explicit `exists/project_open` flag so the MCP agent can distinguish a reliable current workflow from a stale hint. Update the existing tests to pin the chosen contract.

#### A3-P2-2 - MCP-triggered workflow runs depend on launch-path environment for AI Block PTY callbacks

REST workflow execution binds `SCISTUDIO_ENGINE_API_URL` from the request before starting a run: `src/scistudio/api/routes/workflows.py:103-105`, `src/scistudio/api/routes/workflows.py:480-499`, and `src/scistudio/api/routes/workflows.py:586-593`. There is a regression test for this REST path: `tests/api/test_projects.py:87-103`.

The MCP `run_workflow` tool starts the runtime directly and does not bind the callback URL itself: `src/scistudio/ai/agent/mcp/tools_workflow/write.py:190-220`. AI Block PTY allocation raises if `SCISTUDIO_ENGINE_API_URL` is missing: `src/scistudio/engine/pty_control.py:199-205`; completion notification only logs/skips when the URL is missing: `src/scistudio/engine/pty_control.py:302-311`. The CLI `serve` and `gui` paths mitigate this by setting the URL before launching Uvicorn: `src/scistudio/cli/main.py:352-362` and `src/scistudio/cli/main.py:418-425`. FastAPI lifespan sets only the IPC token, not the API URL: `src/scistudio/api/app.py:51-64`.

Impact: the normal alpha desktop/CLI paths look covered, but direct app-factory/Uvicorn launches or test harnesses that expose MCP without going through `scistudio serve`, `scistudio gui`, or REST execute can fail AI Block tab allocation. This is not a P1 because the intended alpha launch path sets the variable, but it is a runtime-facing boundary worth hardening or documenting.

Suggested remediation: set or validate the callback URL at app startup where possible, or have MCP `run_workflow` fail fast with a clear diagnostic when the runtime contains AI Blocks and the callback URL is absent. Add a test for MCP-triggered AI Block execution under the supported launch path.

### P3 - Improvements

#### A3-P3-1 - Frontend runtime bridge tests pass but emit noisy active-context warnings

The bridge intentionally treats active workflow sync as best-effort and logs failures: `frontend/src/store/index.ts:145-159`. The targeted Vitest command passed, but repeatedly logged:

```text
[ai-context] active workflow sync failed TypeError: Failed to parse URL from /api/ai/active-context
```

Impact: this does not block alpha, but it makes runtime bridge test output noisy and can hide real bridge regressions.

Suggested remediation: mock `postActiveWorkflowContext` in the relevant jsdom tests or configure the API base URL so expected best-effort failures are not logged as warnings during passing tests.

## Positive Evidence

- Backend/runtime remains the primary workflow truth for core workflow writes and execution. ADR-014 explicitly keeps frontend state out of runtime truth: `docs/adr/ADR-014.md:55-64`. Workflow writes go through the API/runtime and emit backend `workflow.changed` events with runtime versions: `src/scistudio/api/routes/workflows.py:161-198` and `src/scistudio/api/routes/workflows.py:373-420`.
- Runtime start rejects concurrent live runs, validates workflows before scheduling, and stores live scheduler state in `runtime.workflow_runs`: `src/scistudio/api/runtime/_runs.py:240-248`, `src/scistudio/api/runtime/_runs.py:302-328`, and `src/scistudio/api/runtime/_runs.py:339-382`.
- Workflow pause/resume/cancel API routes delegate to scheduler state instead of frontend-only state: `src/scistudio/api/routes/workflows.py:502-549`.
- CLI/desktop state-sharing docs are consistent with backend truth: attached mode shares backend state, standalone mode persists to disk but does not share live in-memory run history: `docs/cli-integration.md:43-61` and `docs/cli-integration.md:163-172`.

## Commands Run

```text
git status --short --branch
```

Result: on `track/alpha-release-audit-20260621...origin/track/alpha-release-audit-20260621`; no pre-existing local changes observed before writing this report.

```text
git rev-parse --short HEAD
```

Result: `410e1253`.

```text
rg --files src/scistudio/api src/scistudio/desktop src/scistudio/ai
rg --files tests/api tests/desktop tests/ai tests/e2e
rg -n "manual|review|AIBlock|active-context|SCISTUDIO_ENGINE_API_URL|block_user_cancel|runtime truth|workflow.changed" ...
```

Result: used to inventory scoped API, desktop, AI, frontend bridge, tests, and governing docs.

```text
python -m pytest tests/api/test_ai_active_context.py \
  tests/api/test_runtime_workflow_validation_gate.py \
  tests/api/test_projects.py::test_execute_workflow_sets_engine_api_url_for_workers \
  tests/api/test_ai_pty_audit_fixes.py \
  tests/ai/test_mcp_tools_workflow.py \
  tests/ai/test_finish_ai_block.py -q
```

Result: invalid local-source evidence. It imported `scistudio` from `/opt/anaconda3/lib/python3.12/site-packages`, failed in `tests/api/test_ai_pty_audit_fixes.py` because the installed package did not expose `ai_pty._state`, and coverage failed at 26 percent. I did not use this as product evidence.

```text
PYTHONPATH=src python -m pytest --no-cov tests/api/test_ai_active_context.py \
  tests/api/test_runtime_workflow_validation_gate.py \
  tests/api/test_projects.py::test_execute_workflow_sets_engine_api_url_for_workers \
  tests/api/test_ai_pty_audit_fixes.py \
  tests/ai/test_mcp_tools_workflow.py \
  tests/ai/test_finish_ai_block.py -q
```

Result: `49 passed`.

```text
PYTHONPATH=src python -m pytest --no-cov tests/desktop/test_source_package_discovery.py \
  tests/desktop/test_package_installer.py \
  tests/api/test_packages.py -q
```

Result: `12 passed`.

```text
npm test -- src/hooks/useWebSocket.test.ts \
  src/hooks/__tests__/useWebSocket.versionVector.test.ts \
  src/components/AIChat/__tests__/TerminalTabs.test.tsx
```

Result from `frontend/`: `3 passed`, `46 passed`; repeated active-context URL warnings noted in A3-P3-1.

## Missing Evidence And Audit Limits

- I did not run full repository CI, the gate ledger workflow, a packaged desktop binary, or live GUI/e2e execution with a real Claude/Codex provider.
- I did not edit implementation files, checklist rows, or gate records.
- The first Python test attempt showed this worktree can accidentally import an installed SciStudio package unless `PYTHONPATH=src` is set. The corrected local-source commands above are the audit evidence.

## Recommendation

Recommendation: **pass-with-must-fix**.

No P0 was found in the scoped surfaces, and targeted local-source API/desktop/AI tests passed. Alpha should not proceed on this scope until A3-P1-1 is fixed or explicitly owner risk-accepted, and A3-P1-2 provides an alpha-current governing contract/known-limitation record. The P2 and P3 items are good-to-fix before broader internal testing.
