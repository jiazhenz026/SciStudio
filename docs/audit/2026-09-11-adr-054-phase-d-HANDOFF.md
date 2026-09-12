---
title: "ADR-054 Phase D — state at handoff"
status: Draft
owners:
  - "@jiazhenz026"
related_adrs:
  - 54
related_specs:
  - adr-054-miniapp
language_source: en
---

# ADR-054 Phase D — state at handoff

Written at the owner's instruction to stop work and persist the audit results.
Nothing here is a claim that the feature works. It does not.

## 1. What the owner saw, and what the audits say about it

Two things were tried by hand and neither worked:

1. **The canvas context menu is covered by the block hover card.** The menu
   renders, the hover detail popover is `fixed z-50` and portalled to
   `document.body`, the menu is `fixed z-50` inside the canvas — the card wins
   and the entries cannot be read or clicked.
2. **Convert to interactive block produces no PTY / no visible agent session.**
   The adversarial frontend verifier found the same defect independently and
   states it as P2: *"FR-025 is not met: the agent session spawned by MiniApp
   create (and by Convert) is never registered or shown, so the user never sees
   the agent writing the MiniApp."*

A third was observed in the screenshot: the example MiniApp's process reports
**"Failed to start — exit 0"** with an empty log in the running app, while the
same panel starts and reaches `running` when driven directly from a script. That
discrepancy was not diagnosed before work stopped.

## 2. Audit verdicts

Five of six audit agents returned. **All four adversarial verifiers returned
`holds: false`** — every one of the four success criteria they were asked to
break, broke.

| Audit | Verdict | Findings |
|---|---|---|
| With-context review (`2026-09-11-adr-054-phase-d-with-context.md`) | pass-with-fixes | 11 (1×P1) |
| Adversarial: frontend integration | **holds: false** | 7 (2×P1) |
| Adversarial: process lifetime (SC-004) | **holds: false** | 7 (3×P1) |
| Adversarial: API responsiveness (SC-005) | **holds: false** | 5 (3×P1) |
| Adversarial: read-only contexts (SC-003) | **holds: false** | 3 (0×P1) |
| Independent no-context review | **failed to run** | — |

The no-context reviewer stalled on all six attempts (no progress for 180 s each)
and produced nothing. **The one audit that was forbidden to read the issue, the
checklist, the PR and the commit messages — the one that could not inherit this
session's assumptions — is the one there is no result from.** Anyone picking
this up should run it before trusting the other five.

Raw output: `2026-09-11-adr-054-phase-d-audit-raw.json` (all five results,
verbatim) and `2026-09-11-adr-054-phase-d-adversarial-verification.json` (the
four verifiers alone).

### The P1s

**Frontend**
- Every WebSocket reconnect kills and respawns each open MiniApp's `panel.py`
  twice and wipes its page state; the frontend never sends the `client_id` the
  backend added specifically to prevent that.
- FR-035's canvas block context menu was dead code — `ProjectWorkspace` passed
  none of the three MiniApp props. *(Wired during integration; the hover-card
  occlusion above is what remains.)*

**Process lifetime (SC-004)**
- When the panel root process exits on its own (crash, `os._exit`, segfault),
  `_on_exit` deregisters the registry handle **without terminating the process
  group**, and the later `stop()` skips termination because the root is already
  gone — so children survive.
- A child that leaves the panel's process group survives every termination
  path, **including full backend shutdown**.
- Windows: `assign_to_job`'s return value is discarded at launch, and
  `live_members()` then believes the empty Job Object over a demonstrably live
  root, so `owns_live_process()` returns `False` and shutdown drops the handle.

**API responsiveness (SC-005)**
- `stop_process()` calls `PanelProcess.stop()` while holding the store RLock, so
  the tab's Stop button on a hung MiniApp **freezes the whole API** for the
  teardown grace plus the kill window.
- `close_all()`'s `_join_stopping` is not off the lock as its docstring claims;
  via `on_event` it runs the join directly on the API event loop.
- Panel requests queued on the store lock during a `close_all` join **exhaust
  the anyio threadpool and starve sync routes**.
- Shutdown with wedged MiniApps open measured **5.22 s** on the event loop.

## 3. Where the code is

- **Integration branch**: `feat/2354-miniapp-phase-d` @ worktree
  `.worktrees/adr054-phase-d`, stacked on `feat/2294-panels-phase-b` (PR #2367).
  122 files, +14162 / −397 against the Phase B head.
- **Umbrella**: `track/adr-054-phase-d`, PR #2368 `[DO NOT MERGE]`.
- **Agent branches** (merged into the integration branch, kept for provenance):
  `feat/2354-miniapp-{backend-core,backend-routes,agent-surface,fe-tab,fe-sidebar,fe-entries,fe-realtime}`.
- **Audit branches**: `audit/2354-phase-d-context`, `audit/2354-phase-d-nocontext`.
- **Checklist**: `docs/planning/adr-054-phase-d-checklist.md`.
- **Gate ledger**: `.workflow/records/2354-feat-2354-miniapp-phase-d.json` —
  carries no check, test, docs, guard, commit or PR evidence. It is **not**
  PR-ready.

## 4. Test state

- Frontend: 233 files / 2600 tests pass; typecheck and lint clean.
- Backend: the `hello`-frame regression in five ws race/contract tests was found
  and fixed. Two failures remained unresolved at handoff:
  `tests/ai/test_mcp_socket_permissions.py::test_taken_over_temp_fallback_moves_to_a_unique_private_directory`
  and `tests/qa/test_audit_docstrings.py::test_actual_package_docstrings_are_clean`
  (the latter is FR-number text inside docstrings in `routes/panels.py` and
  elsewhere; the rule wants behaviour in the docstring and maintainer references
  in ordinary `#` comments). `tests/scripts/test_ota_publish.py` fails to
  collect — pre-existing, unrelated.
- The serial phase was never run to completion on this tree.

**The green suites did not catch any of the P1s above.** Four separate surfaces
compiled, passed their tests, and did nothing: the agent tool catalogue, the
toolbar entry, the ws client id, and the canvas context menu. Three were found
by reading, one by the owner.

## 5. Untouched on purpose

- `docs/architecture/ARCHITECTURE.md` — owner-controlled. Its MCP tool catalogue
  is stale (says 35; the live surface is 50 registered / 36 local) and Phase D
  makes it staler.
- `docs/ai-developer/e2e/` — governance surface; the spec's e2e scenario
  (§4.4) was never written.

## 6. Copy awaiting owner review

- `what-is-a-type` → `save-the-previewer`, second line: *"In **All Previewers**,
  find **Image** and choose **All projects**."*
- Four new tips in `tipPool.ts`.
- The MiniApp template page in `src/scistudio/panels/template/index.html`.

## 7. Running processes at handoff

A desktop dev instance was started from this worktree
(`npm --prefix desktop run dev`, `SCISTUDIO_DESKTOP_PYTHON` pointed at the
bundled 3.12). An example MiniApp was written into
`/Users/jiazhenz/adr054-tests/panels/lab.array_explorer/` — it is **test
scaffolding in the owner's project, not part of this branch**, and should be
deleted or moved if unwanted.
