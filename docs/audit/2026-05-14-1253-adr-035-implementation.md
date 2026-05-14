# Audit Report — ADR-035 Implementation (Phase 2.5)

**Date:** 2026-05-14 12:53
**Tracking branch:** `track/adr-035/ai-block-pty`
**Diff under review:** `origin/main`...`origin/track/adr-035/ai-block-pty`
**PRs in scope:** #856 (Skeleton), #862 (I35a backend), #861 (I35b engine+MCP), #866 (I35c frontend)
**Verdict:** **NEEDS-FIX** (4 × P1, 1 × P2, 1 × drift)

---

## 1. Local CI results (worktree)

| Check | Result | Notes |
|---|---|---|
| `pytest tests/blocks/ai tests/engine/test_pty_control* tests/api/test_ai_pty_engine_spawn.py tests/ai/test_finish_ai_block*` | **111 passed, 14 xfailed, 0 failed** | ADR-035-specific tests all green |
| `pytest tests/blocks/ai tests/engine tests/api` (broad scope) | **548 passed, 6 skipped, 8 xfailed, 2 failed** | The 2 failures are `tests/api/test_projects.py` Windows tempdir locking — pre-existing, file untouched by ADR-035 (verified via `git diff origin/main -- tests/api/test_projects.py` = empty). Not an audit finding. |
| `ruff format --check .` | PASS | 466 files already formatted |
| `ruff check .` | PASS | All checks passed |
| `npx vitest run` | **153 passed, 13 skipped, 0 failed** | All 18 frontend test files green |
| `npx tsc --noEmit` | PASS | No TS errors |
| `npm run build` | PASS | 2043 modules, 15.91s |

Environment notes: env-level h5py installation is broken (circular `_errors` import) and `pytest-timeout` plugin not installed. Worked around with `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 -p pytest_cov -p pytest_asyncio --no-cov`. These are pre-existing env issues unrelated to ADR-035; no `--timeout=60` enforced because the plugin isn't installed.

## 2. Checklist drift findings

**D1 (drift, severity: process):** `docs/planning/adr-035-036-checklist.md` Phase 2C section (lines 46–51) shows all six rows still as `[ ]` not started, but PR #866 (Phase 2C frontend) is merged into the tracking branch and the artifacts exist in the diff:

- L46 `TerminalTabs.tsx handles block_pty_opened` → implemented in `frontend/src/components/AIChat/blockPtyHandlers.ts::handleBlockPtyOpened`
- L47 `TerminalTab.tsx 🤖 prefix + status badge` → `TerminalTab.tsx::AiBlockStatusBadge` (lines 45–105)
- L48 `Mark done button` → `TerminalTab.tsx::MarkDoneButton` (lines 121–144)
- L49 `Tab close while running → confirmation modal → emit cancel` → `TerminalTabs.tsx::ConfirmDialog` (lines 30–67) + `pendingClose` flow (lines 251–280)
- L50 `Tab survives DONE/ERROR` → render path always mounts `TerminalView` regardless of `blockStatus`
- L51 `Vitest tests for new tab-source path; status badge variants` → `__tests__/TerminalTab.test.tsx` (15 tests) + `TerminalTabs.test.tsx` (19 tests)

The "Audit & Fix (skeleton)" rows (54–55) are also unticked despite PR #858 (`docs/audit/2026-05-14-adr-035-skeleton.md`) existing.

**Recommendation:** the F35-impl agent (or fix follow-up) must tick rows 46–51 and 54 with the artifact pointers above.

## 3. Codex review reconciliation

| PR | Codex finding | File:line | Severity (Codex) | Verified in current code? | Verdict |
|---|---|---|---|---|---|
| #856 | (no inline suggestions; meta-comment only) | — | — | — | **N/A** |
| #862 | Propagate Claude bootstrap failures (`_write_system_prompt_tempfile` / `_ensure_mcp_config`) | `src/scieasy/blocks/ai/ai_block.py:412-424` | P1 | YES — `except Exception: logger.exception(...)` swallows error and proceeds with degraded argv (no `--append-system-prompt`/`--mcp-config`). Worker can no longer call `finish_ai_block`. | **ACCEPTED — P1 (must fix)** |
| #861 | IPC token never initialised | `src/scieasy/api/routes/ai_pty.py:552-572` | P1 | YES — `_ensure_ipc_token()` is defined but never called from anywhere (verified via repo grep: only `os.environ.get(...)` reads). When `SCIEASY_ENGINE_IPC_TOKEN` env var is absent, `_check_ipc_token()` always 401s every internal request. **Engine→worker IPC is dead-on-arrival.** | **ACCEPTED — P1 (must fix)** |
| #861 | Reuse existing PTY instead of spawning again for same `tab_id` | `src/scieasy/api/routes/ai_pty.py:118-132` vs `:498-499` | P1 | YES — `pty_endpoint` (the user-visible WS at `/api/ai/pty/{tab_id}`) calls `_spawn(...)` unconditionally at line 119 and overwrites `_active_ptys[tab_id]` at line 132, even if the tab was pre-spawned by `open_engine_initiated_tab` (line 490, 499). The engine-initiated PTY is orphaned (along with `_engine_initial_stdin` and `_engine_block_run_id` metadata) and a fresh agent process replaces it. **Block-to-tab correlation broken at runtime.** | **ACCEPTED — P1 (must fix)** |
| #866 | `block_pty_closed`: parse outcome from `event` field, not `status`/`result` | `frontend/src/hooks/useWebSocket.ts:204-218` vs `src/scieasy/api/routes/ai_pty.py:654-660` | P1 | YES — backend writes `{type, block_run_id, tab_id, event: "completed"|"cancelled_by_user_close"|"error", detail}` (line 654-660) at the **top level**. Frontend reads `payload.data.status` and `payload.data.result` (lines 215-216). Neither field exists. `mapCloseResult(undefined)` falls through to default `"error"`. **Successful and user-cancelled runs render as red ✗.** | **ACCEPTED — P1 (must fix)** |
| #866 | `permission_mode` read from wrong nesting level | `frontend/src/hooks/useWebSocket.ts:181-185` vs `src/scieasy/api/routes/ai_pty.py:507` | P2 | YES — backend emits `permission_mode` at the top level of the message (line 507). Frontend reads `src.permission_mode` from `payload.data` (line 181). Fallback "safe" is always taken. AI Block tabs in bypass mode show `dangerous=false` in store, breaking reconnect/UI cues. | **ACCEPTED — P2 (should fix; cheap one-line shape patch)** |
| #866 | `block_user_marked_done` WS frame unsupported by inbound handler | `frontend/src/components/AIChat/TerminalTab.tsx:128-132` + `TerminalTabs.tsx:267-272` vs `src/scieasy/api/ws.py:113-146` | P1 | YES — inbound handler accepts `cancel_block`, `cancel_workflow`, `interactive_complete` only (lines 113-144). `block_user_marked_done` (TerminalTab.tsx:129) and `block_user_cancel` (TerminalTabs.tsx:268) both fall to the `else: logger.warning("Unknown WebSocket message type")` branch. **Mark-done button is a no-op; close-while-running cancellation never reaches engine.** | **ACCEPTED — P1 (must fix)** |

**Summary:** 4 × P1 + 1 × P2 verified-still-present from Codex. Per memory `audit_p1_override`: deferring any of these P1s would be invalid — they each render a documented user-facing feature non-functional, and there is no infrastructure-level reason they can't be fixed in-PR.

## 4. Chrome smoke test results

| Substep | Status | Reason |
|---|---|---|
| GUI reachable | PASS — `http://127.0.0.1:8000/` returns HTTP 200 | But running engine is from `main` (commit `a1f6a81`), not `track/adr-035/ai-block-pty`. ADR-035 routes return `405 Method Not Allowed` (not registered). |
| Build workflow → AIBlock → run | **SKIPPED** | Live engine doesn't have ADR-035 routes. Switching the running engine to this branch would require killing the user's running session (out of audit scope). |
| `block_pty_opened` event → tab auto-opens | **SKIPPED** | Same. Additionally, given the four confirmed P1 backend wiring bugs (IPC token uninitialised → 401 on every internal request, double-spawn on WS connect, status field mismatch, mark-done frame unhandled), the smoke test would deterministically fail at the first IPC call. Static review proves the path is non-functional end-to-end. |
| Status badge transitions | **SKIPPED** | Same. |
| Mark-done button when PAUSED | **SKIPPED** | Confirmed unwired (P1 #866-3). |
| Tab survives DONE | **SKIPPED** | Code-path looks correct (TerminalView always mounts when state==="running" regardless of `blockStatus`), but cannot exercise without a green PAUSED→DONE transition. |

**Smoke recommendation:** rerun smoke after the four P1 fixes land; do not merge to main without a successful Chrome smoke. Per memory `mandatory_chrome_smoke_test` and `phase_audit_smoke_test`, the dispatcher should treat the smoke-skip as a P1-equivalent gate.

## 5. P1 findings (must-fix before tracking → main)

**P1-A (Codex #862-1):** Bootstrap failures swallowed in `AIBlock._build_provider_argv`.
- File: `src/scieasy/blocks/ai/ai_block.py:412-424`
- Fix: re-raise after logging, or add explicit `raise RuntimeError("AI Block bootstrap failed: ...")` so `run()` enters ERROR state instead of spawning a degraded `claude` that hangs.
- Test: add an injection that makes `_write_system_prompt_tempfile` raise; assert `AIBlock.run()` transitions to ERROR with actionable message rather than silent argv degradation.

**P1-B (Codex #861-1):** IPC token never initialised in production engine startup.
- File: `src/scieasy/api/routes/ai_pty.py:552-565`
- Fix: call `_ensure_ipc_token()` at FastAPI app startup (e.g. in the engine bootstrapper that mounts `ai_pty.router`) so the env var is set before any worker subprocess inherits it. Pure helper-not-invoked bug.
- Test: integration test that spawns a worker, calls `/internal/request-tab` from it, asserts 200 not 401.

**P1-C (Codex #861-2):** Existing `pty_endpoint` overwrites engine-pre-spawned PTY on WS connect.
- File: `src/scieasy/api/routes/ai_pty.py:117-132` (the join-WS path) and `:498-499` (the engine-initiated registration)
- Fix: in `pty_endpoint`, if `tab_id in _active_ptys` and the existing entry has `_engine_block_run_id`, JOIN that PTY (re-use it) instead of calling `_spawn(...)` again. Also flush any `_engine_initial_stdin` to the PTY on first WS connect.
- Test: integration test — call `open_engine_initiated_tab(...)` to register `tab_id=X`, then connect to `/api/ai/pty/X`, assert `_spawn` is NOT called a second time and the WS reads forwarded stdout from the original PTY.

**P1-D (Codex #866-1):** `block_pty_closed` shape mismatch — frontend reads non-existent fields.
- Files: `frontend/src/hooks/useWebSocket.ts:204-218` and (less invasively) `src/scieasy/api/routes/ai_pty.py:654-660`
- Fix (preferred — cheap, one-side-only): update `useWebSocket.ts` to read `payload.event` (or `(payload as any).event`) at the top level, with map: `completed → "done"`, `cancelled_by_user_close → "cancelled"`, `error → "error"`. Pass through to `handleBlockPtyClosed`.
- Alternatively (backend side): add `status` field to message dict mirroring the `event` value with the FE-friendly label.
- Test: vitest — feed a `block_pty_closed` frame with `event: "completed"` and `tab_id, block_run_id` at top level; assert `updateAiBlockStatus(tabId, "done")` is called (currently calls with "error").

**P1-E (Codex #866-3):** `block_user_marked_done` and `block_user_cancel` WS frames are silently dropped.
- Files: `src/scieasy/api/ws.py:113-146` (add inbound branches) plus event-bus wiring to engine that translates these into `mark_done.json` write (path c, ADR-035 §3.5) and a cancellation request respectively.
- Fix: add two new `elif msg_type == "block_user_marked_done":` and `elif msg_type == "block_user_cancel":` branches that emit appropriate `EngineEvent`s. The engine-side handler then calls into `pty_control.notify_block_pty_event` or writes the signal file.
- Test: integration — open WS, send `{"type": "block_user_marked_done", "block_run_id": "...", "tab_id": "..."}`, assert `mark_done.json` appears in the run_dir within 1s.

## 6. P2 findings (should-fix; defer only with strong reason)

**P2-A (Codex #866-2):** `permission_mode` field nesting mismatch.
- File: `frontend/src/hooks/useWebSocket.ts:181-185` vs `src/scieasy/api/routes/ai_pty.py:507`
- Fix: read `(payload as any).permission_mode` from top level (mirror the `tab_id` / `block_run_id` resilience pattern already used in lines 209-212).
- Test: vitest — feed frame with `permission_mode: "bypass"` at top level; assert resulting tab has `permissionMode === "dangerous"`.
- **Should be fixed in the same fix-pass as P1-D** since they share the same WS handler and shape mismatch lineage. Deferring would leave `dangerous` mode silently degraded to `safe` on engine-initiated tabs.

## 7. P3 findings (nice-to-have)

None identified beyond what Codex flagged.

Optional polish observations (not findings):
- `blockPtyHandlers.ts` defensively accepts both `block_name` and `title` for `block_pty_opened`. The backend (line 505) emits `title`, but the dispatch contract per docstring says `block_name`. Harmless but the contract should be tightened in a follow-up doc PR so future authors don't have to read both sides.
- `_provider_from_argv` (ai_pty.py:531-539) defaults to `claude-code` for unknown argv — fine for v1, but a P3 hardening would be to log a warning when argv[0] doesn't match a known family.

## 8. Recommendation

**NEEDS-FIX.** Open one fix-PR (`fix/adr-035-impl-audit-p1`) onto `track/adr-035/ai-block-pty` addressing P1-A through P1-E plus P2-A in a single pass (they cluster in three files: `ai_block.py`, `ai_pty.py`, `useWebSocket.ts`/`ws.py`). After fixes land, re-run live Chrome smoke against this branch (start engine from `track/adr-035/ai-block-pty` on a free port, drive the LoadImage → AIBlock → SaveData workflow per the e2e checklist) **before** the umbrella `[DO NOT MERGE]` PR #852 can transition to MERGE-READY.

Drift item D1 (Phase 2C checklist rows untrackchecked) is process-only and should be ticked by the dispatcher when consolidating the audit findings.

---

**Counts:** P1 = 5, P2 = 1, P3 = 0, Drift = 1 (process)
**Audit author:** A35-impl (audit-impl-035 branch, worktree `agent-a708d8a2ff3a4d651`)
