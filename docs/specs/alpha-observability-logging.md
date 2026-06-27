---
spec_id: alpha-observability-logging
title: "Alpha Closed-Beta Observability: Persistent Layered Logging"
status: Planned
feature_branch: guided/live-round5-20260621
created: 2026-06-21
input: "Issue #1741 — alpha closed-beta needs persistent, layered, fine-grained logs so a tester-reported bug can be reproduced offline. Owner-directed guided session 2026-06-21; bundled with versioning (#1742) into one PR per owner direction."
owners:
  - "@jiazhenz026"
related_adrs: []
related_specs:
  - alpha-version-management
scope:
  in:
    - Unified logging base that writes human-readable logs to disk with rotation and 7-day retention, in addition to the existing human-readable stderr stream.
    - Correlation-id propagation (X-Request-ID) across frontend -> backend -> log records.
    - Backend API request/exception middleware and a boundary @log_call decorator for fine-grained DEBUG with no broad function rewrites.
    - Per-run diagnostic log file aggregating engine events, worker output, and tracebacks.
    - Frontend logger abstraction, React ErrorBoundary, global error handlers, user-action INFO logging, and reflux of frontend logs to the backend.
    - Desktop log rotation, renderer-process console capture, and main-process crash handlers.
    - A diagnostic bundle export (backend zip endpoint + a small frontend button) for bug reports.
    - WebSocket logs persisted to disk (already use stdlib logging; covered by the file handler).
  out:
    - Third-party log shipping / error tracking (Sentry, Datadog, etc.).
    - Recording raw scientific data contents in logs (metadata only).
    - Log search UI or server-side log aggregation beyond per-run files.
    - Distributed tracing spans beyond a single correlation id.
governs:
  modules:
    - scistudio.utils.log_setup
    - scistudio.engine.run_logging
  contracts:
    - scistudio.utils.logging.configure_logging
  entry_points: []
  files:
    - docs/specs/alpha-observability-logging.md
    - src/scistudio/utils/logging.py
    - src/scistudio/utils/log_setup.py
    - src/scistudio/api/app.py
    - src/scistudio/api/_logging_middleware.py
    - src/scistudio/api/routes/diagnostics.py
    - src/scistudio/engine/run_logging.py
    - src/scistudio/cli/main.py
    - frontend/src/lib/logger.ts
    - frontend/src/components/ErrorBoundary.tsx
    - frontend/src/main.tsx
    - frontend/src/lib/api/core.ts
    - desktop/main.js
    - desktop/preload.js
  excludes: []
tests:
  - tests/utils/test_log_setup.py
  - tests/api/test_logging_middleware.py
  - tests/api/test_diagnostics_routes.py
  - tests/engine/test_run_logging.py
acceptance_source: issue
language_source: en
---

# Alpha Closed-Beta Observability: Persistent Layered Logging

## 1. Change Summary

From issue #1741. SciStudio is entering an alpha closed-beta. Today the only
on-disk observability log is the Electron `scistudio-desktop.log` (desktop only,
single file, no rotation, no renderer/frontend coverage). Backend, engine, and
event-bus logs go to **stderr only** (`configure_logging` installs no file
handler —落盘 was explicitly deferred in #827). Frontend errors are invisible:
no ErrorBoundary, no global handler, no reporting, no persistence. The FastAPI
app has no request/exception logging and no correlation id.

This spec defines a **layered, persistent, fine-grained** logging system so that
when a beta tester reports a bug, a developer can reproduce/diagnose it offline
from logs alone. The four layers — engine/engine-events, backend API, frontend,
desktop — are recorded at the same granularity (every call → DEBUG, every user
action → INFO), via **boundary instrumentation** (a `@log_call` decorator, an API
middleware, an `apiFetch` wrapper) rather than broad per-function rewrites. Logs
persist as human-readable files with rotation and 7-day retention; the console keeps
its human-readable stream. A diagnostic bundle export lets a tester ship logs +
environment + recent run with one click.

## 2. User Scenarios & Testing

### User Story 1 - Reproduce a backend/engine bug from disk logs (Priority: P1)

A tester runs a workflow that errors. A developer, later and elsewhere, opens the
persisted logs and sees the request that started the run, the per-run diagnostic
log with every block lifecycle event, worker output, and the full traceback.

**Why this priority**: This is the core promise of the feature — without
persisted backend/engine logs there is nothing to diagnose.

**Independent Test**: Run a failing workflow headless (`scistudio run`), then
confirm a human-readable process log and a `run-<id>.log` exist under the log dir and
contain the BLOCK_ERROR event and traceback.

**Acceptance Scenarios**:
1. **Given** logging is configured, **When** any backend process starts, **Then**
   a human-readable log file is created under the resolved log directory and receives
   records in addition to the human-readable stderr stream.
2. **Given** a workflow run, **When** the run executes, **Then** a per-run
   diagnostic file `run-<run_id>.log` captures engine events, worker stdout/stderr,
   and any traceback, and is closed when the run ends.
3. **Given** a request to the API, **When** it is handled, **Then** an INFO record
   logs method/path/status/duration with a correlation id, and an uncaught
   exception logs an ERROR record with traceback under the same correlation id.

### User Story 2 - See a frontend bug a tester could not describe (Priority: P1)

A tester's UI throws (render error or unhandled rejection). The error is caught,
shown as a recoverable UI state, logged, and refluxed to the backend so it lands
on disk under a correlation id the developer can tie to backend activity.

**Why this priority**: Frontend observability is currently zero; this is the
single biggest blind spot for a desktop beta.

**Independent Test**: Throw inside a component; confirm the ErrorBoundary renders
a fallback, `logger.error` fires, and a `POST /api/client-logs` persists the
record on the backend.

**Acceptance Scenarios**:
1. **Given** a React render error, **When** it propagates, **Then** the
   ErrorBoundary renders a fallback instead of a blank screen and logs the error.
2. **Given** an unhandled promise rejection or `window.onerror`, **When** it
   fires, **Then** the global handler logs it and refluxes it to the backend.
3. **Given** any frontend log at/above the reflux threshold, **When** emitted,
   **Then** it is batched to `POST /api/client-logs` and persisted on disk.

### User Story 3 - One-click diagnostic bundle (Priority: P2)

A tester clicks "Export logs"; the app produces a single zip with recent logs,
environment info, and the most recent run log, ready to attach to a report.

**Why this priority**: Dramatically lowers the cost of a useful bug report, but
the raw logs (US1/US2) are the prerequisite.

**Independent Test**: Call the bundle endpoint; confirm a zip is returned
containing log files and an environment manifest.

**Acceptance Scenarios**:
1. **Given** persisted logs exist, **When** the bundle endpoint is called,
   **Then** a zip stream is returned with logs + environment + recent run log.
2. **Given** the desktop/web UI, **When** the user clicks the export button,
   **Then** the bundle downloads.

### Edge Cases

- Log directory not writable → logging must degrade to stderr-only, never crash
  the process (mirror the desktop `safeWrite` best-effort contract).
- Backend unreachable when the frontend tries to reflux → frontend keeps an
  in-memory ring buffer that the export button can still dump.
- Very large payloads / scientific data → sanitized to metadata via the existing
  `_sanitize_value` (path/type/size/hash), never raw contents.
- DEBUG volume → default level INFO; DEBUG opt-in via `SCISTUDIO_LOG_LEVEL=DEBUG`
  and auto-elevated inside a per-run diagnostic file.

## 3. Requirements

### Functional Requirements

- **FR-001**: `configure_logging` MUST install, in addition to the existing
  human-readable stderr handler, rotating human-readable `.log` file handlers
  written to a resolved log directory — a combined `scistudio-<pid>.log` plus one
  file per layer (`api-`/`engine-`/`frontend-<pid>.log`) — idempotently and
  without crashing if the directory is unwritable. On-disk logs are
  human-readable only (no JSON files).
- **FR-002**: The log directory MUST resolve as: explicit arg → `SCISTUDIO_LOG_DIR`
  → desktop `logs_dir()` when bundled → `<project>/.scistudio/logs/` when a project
  is known → `logs_dir()` fallback.
- **FR-003**: On startup the system MUST prune log files older than 7 days from the
  log directory (best-effort).
- **FR-004**: A `@log_call` decorator MUST emit DEBUG on enter (sanitized args) and
  on exit (duration), and ERROR with traceback on exception, for both sync and
  async callables, and MUST be safe to apply at layer boundaries.
- **FR-005**: A correlation id MUST be stored in a contextvar, accepted/emitted as
  the `X-Request-ID` header, and included in every human-readable record when present.
- **FR-006**: The API MUST add middleware that assigns/propagates a correlation id,
  logs each request (method, path, status, duration) at INFO, and logs uncaught
  exceptions at ERROR with traceback (returning a 500 JSON body).
- **FR-007**: `POST /api/client-logs` MUST accept a batch of frontend log records
  and persist them through the backend logger (logger name `scistudio.frontend`).
- **FR-008**: Each workflow run MUST produce a per-run diagnostic log file
  `run-<run_id>.log` capturing engine events, worker output, and tracebacks for the
  duration of the run, removed cleanly when the run ends.
- **FR-009**: The frontend MUST provide a `logger` with debug/info/warn/error that
  writes to the console and batches records at/above a threshold to the backend,
  and MUST keep a bounded in-memory ring buffer for export.
- **FR-010**: The frontend MUST install a React ErrorBoundary and global
  `window.onerror` / `onunhandledrejection` handlers that log and reflux errors.
- **FR-011**: `apiFetch` MUST attach the correlation id header and emit DEBUG for
  request/response/error, providing user-action INFO at the API boundary.
- **FR-012**: The desktop main process MUST rotate its log file, capture
  renderer-process `console-message`, and handle `uncaughtException`,
  `unhandledRejection`, and `render-process-gone`, persisting all to disk under the
  Electron `logs` path (aligned with Python `logs_dir()`).
- **FR-013**: A backend endpoint MUST return a diagnostic bundle (zip) containing
  recent log files, an environment manifest, and the most recent run log; a small
  frontend button MUST trigger its download.
- **FR-014**: WebSocket and uvicorn logs MUST be routed through stdlib logging so
  the file handler persists them (no separate sink).
- **FR-015**: Logs MUST record metadata only (path/type/size/hash) for scientific
  payloads and MUST support redaction of configured sensitive config fields.

### Key Entities

- **LogRecord (on disk)**: a human-readable line `ts LEVEL logger message [req=…
  run=…]` (no JSON files on disk), written to a combined `scistudio-<pid>.log`
  and a per-layer file (`api-`/`engine-`/`frontend-<pid>.log`).
- **ClientLogBatch**: `{records: [{level, message, ts, url?, context?}], ...}` posted
  by the frontend to be bundled as a human-readable `frontend-logs.log`.
- **DiagnosticBundle**: zip of `logs/*.log` (combined + per-layer) +
  `environment.json` + `frontend-logs.log` + `runs/run-*.log`.

## 4. Implementation Plan

### 4.1 Technical Approach

A new `scistudio.utils.log_setup` module owns the file sink, directory resolution,
retention pruning, the correlation-id contextvar + logging filter, and the
`@log_call` decorator. `scistudio.utils.logging.configure_logging` is upgraded to
compose the existing stderr handler with the new human-readable file handler (reusing
`_JsonLineFormatter` and `_sanitize_value`). The API gains middleware
(`_logging_middleware.py`) and a `diagnostics` router (`/api/client-logs`,
`/version`, `/api/diagnostics/bundle`). A `scistudio.engine.run_logging` module
attaches/detaches a per-run file handler scoped by a `run_id` contextvar/filter.
CLI `serve`/`gui`/`run` and `create_app` call `configure_logging` (replacing bare
`basicConfig`) and pass uvicorn a `log_config` that routes uvicorn loggers through
stdlib logging. The frontend adds `lib/logger.ts`, `components/ErrorBoundary.tsx`,
global handlers in `main.tsx`, and correlation/debug in `lib/api/core.ts`, plus an
export button. Desktop `main.js` gains rotation, renderer capture, and crash
handlers.

### 4.2 Affected Files

| File | Action | Rationale |
|---|---|---|
| `src/scistudio/utils/log_setup.py` | create | File sink, dir resolution, retention, correlation id, `@log_call` |
| `src/scistudio/utils/logging.py` | modify | Compose stderr + file handlers in `configure_logging` |
| `src/scistudio/api/_logging_middleware.py` | create | Request/exception logging + correlation id |
| `src/scistudio/api/routes/diagnostics.py` | create | `/api/client-logs`, `/version`, `/api/diagnostics/bundle` |
| `src/scistudio/api/app.py` | modify | Wire middleware + diagnostics router |
| `src/scistudio/engine/run_logging.py` | create | Per-run diagnostic file handler |
| `src/scistudio/cli/main.py` | modify | Use `configure_logging`; uvicorn `log_config`; `--version` |
| `frontend/src/lib/logger.ts` | create | Frontend logger + ring buffer + reflux |
| `frontend/src/components/ErrorBoundary.tsx` | create | React error boundary |
| `frontend/src/main.tsx` | modify | Mount ErrorBoundary + global handlers |
| `frontend/src/lib/api/core.ts` | modify | Correlation id header + DEBUG boundary |
| `desktop/main.js` | modify | Rotation + renderer capture + crash handlers |
| `desktop/preload.js` | modify | Bridge renderer console if needed |

### 4.3 Implementation Sequence

1. Unified base (`log_setup.py` + `logging.py`) + tests.
2. Backend middleware + diagnostics router + `app.py` wiring + CLI entrypoints.
3. Engine per-run diagnostic log.
4. Frontend logger + ErrorBoundary + global handlers + `apiFetch` + export button.
5. Desktop rotation + renderer capture + crash handlers.
6. Diagnostic bundle endpoint + frontend button.

### 4.4 Verification Plan

- Unit tests: file handler creation, dir resolution, retention pruning,
  `@log_call` sync/async, correlation filter.
- API tests: middleware logs + correlation header; `/api/client-logs` persists;
  bundle endpoint returns a zip.
- Engine test: per-run file created and contains BLOCK_ERROR + traceback.
- `gate_record check --mode pre-pr` (Tier 1 expected; touches protected core).
- Manual: `scistudio run` on a failing workflow → inspect logs.

### 4.5 Risks And Rollback

- **Protected-core edits** (`engine/`, `utils/`): require `admin-approved:core-change`
  (owner pre-authorized). Risk: CI label provenance — recorded in ledger.
- **Log volume**: mitigated by default INFO level and rotation/retention.
- **Performance**: boundary-only instrumentation avoids hot-path overhead; sanitize
  before formatting.
- **Rollback**: the feature is additive; `configure_logging` retains stderr-only
  behavior if the file sink fails, so reverting is low-risk.

## 5. Success Criteria

### Measurable Outcomes

- **SC-001**: After any backend entrypoint starts, a human-readable log file exists in
  the resolved log directory and grows as the process logs.
- **SC-002**: A failing `scistudio run` produces a `run-<id>.log` containing the
  BLOCK_ERROR event and a full traceback.
- **SC-003**: A thrown frontend error results in a persisted record on the backend
  via `POST /api/client-logs`, correlated by `X-Request-ID` where applicable.
- **SC-004**: The diagnostic bundle endpoint returns a zip containing at least the
  current process log and an environment manifest.
- **SC-005**: Log files older than 7 days are pruned on startup.

## 6. Assumptions

- Owner-approved single combined PR with versioning (#1742) (source: owner).
- Boundary instrumentation satisfies the "every call DEBUG" intent without
  rewriting repository functions (source: owner).
- Default runtime level is INFO with DEBUG opt-in (source: owner-confirmed).
- No third-party telemetry; backend self-hosted reflux only (source: owner).
