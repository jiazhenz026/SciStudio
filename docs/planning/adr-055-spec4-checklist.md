---
title: "ADR-055 Spec 4 Agent Dispatch Checklist"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 55
  - 52
related_specs:
  - adr-055-enterprise-support
  - adr-055-identity-seam
language_source: en
---

# ADR-055 Spec 4 Agent Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request (2026-09-11): act as manager for implementing ADR-055 Spec 4.
  That is the open-source `adr-055-enterprise-support` spec and its enterprise
  counterpart. Finish by pushing PRs in both repositories.
- Task kind: `manager` (this checklist); `feature` (implementation tracks)
- Manager persona: `manager`
- Issue: `#2321` (manager); implementation `#2322` (O1), `#2308` (O2)
- Gate record: `.workflow/records/2321-track-adr-055-spec4.json`
- Branch/worktree plan:
  - manager umbrella `track/adr-055-spec4` at `.worktrees/track-adr-055-spec4`;
  - agent branches `feat/2322-enterprise-ui` at `.worktrees/feat-2322-enterprise-ui`
    and `feat/2308-webmcp-adapter` at `.worktrees/feat-2308-webmcp-adapter`,
    both based on `origin/main`.
- Protected branch: `main`
- Umbrella branch: `track/adr-055-spec4`
- Umbrella PR: `#2323`
- Umbrella PR title: `[DO NOT MERGE] ADR-055 Spec 4 dispatch`
- Final PR target: `main`. Each track opens its own final PR to `main`, as the
  Spec 2-3 dispatch did.
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context:
    `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context:
    `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`
- Filled prompts: `docs/planning/adr-055-spec4-dispatch-prompts.md`
- Enterprise-side tracks are dispatched and tracked in the private enterprise
  repository. This public checklist records only the open-source tracks, and
  the enterprise tracks' dependencies on them.

## 2. Scope

- In scope:
  - **O1 (#2322):** `docs/specs/adr-055-enterprise-support.md` T-002 and T-003.
    - Additive capability extensions in `scistudio.api.seam`:
      `ai_chat_disabled`, a `transfer` object, a dynamic `update`, and an
      optional `identity.logout_url`.
    - Capability-gated UI: identity chrome with a POST Logout, the update
      notice, the transfer controls, and hiding the AI Chat surface.
    - Backend refusal of agent-kind PTY providers when `ai_chat_disabled` is
      set.
    - Spec amendments for the dynamic `update` shape.
    - Scope additions (manager, 2026-09-11):
      - register `/api/ai/pty/internal/` as self-authenticating, after
        verifying the IPC token on every route there;
      - #2328, seam project access for editions: `active_project_root`,
        `ToolRefusal`, `check_author_path`, `write_project_file`,
        `add_upload_listener`.
  - **O2 (#2308):** the stdio MCP adapter over `/api/webmcp/*` and the per-user
    loopback token file (FR-008 to FR-011), with the adapter's spec details.
    - Scope addition (manager, 2026-09-11): #2333, owner-only permissions on
      the local MCP socket whatever the umask, and a private fallback
      directory (`ai/agent/mcp/server.py`, `runtime.py`).
- Out of scope:
  - Enterprise backend routes, guard, deployment, and runbook (private
    repository).
  - Panel prefix registration (#2288; ADR-054 is paused).
  - The external-AI user-guide page (#2290).
  - OTA publishing. PyPI `0.3.4a32` is already published (#2317 records the
    numbering constraint).
- Protected paths: any `src/scistudio/core/**` need is a stop condition.
- Deferred work: N/A at dispatch. Agents record any deferral as
  `TODO(#NNN)`.

## 3. Conventions

- `[ ]` not started
- `[~]` in progress
- `[x]` done
- `[!]` blocked
- Every completed row MUST include an artifact:
  PR link, commit, test command, report path, or gate-record entry.
- Chat messages are not checklist evidence.
- Agents edit only their own rows.
- Scope changes require gate-record amendment before work continues.

## 4. Manager Preflight

- [x] Dedicated manager branch and worktree created -> `track/adr-055-spec4`, `.worktrees/track-adr-055-spec4`
- [x] Existing issue linked, or new issue created only if none exists -> `#2321` (new manager issue), `#2322` (new), `#2308` (existing)
- [x] Gate record started -> `.workflow/records/2321-track-adr-055-spec4.json`
- [x] Scope include/exclude recorded in the gate record -> `init --include` for this checklist and the prompts file
- [x] Umbrella branch created -> `track/adr-055-spec4`
- [x] Umbrella PR opened -> #2323
- [x] Umbrella PR title includes `[DO NOT MERGE]` -> "[DO NOT MERGE] ADR-055 Spec 4 dispatch"
- [x] Protected branch and umbrella PR number recorded in this checklist -> main, #2323
- [x] No `pip install -e .` environment pollution found -> the shared `.venv` is untouched; agents are told not to install.
- [x] Dispatch checklist copied from the template and committed -> this file.
- [x] Dispatch prompts created from the correct prompt template and linked below -> `docs/planning/adr-055-spec4-dispatch-prompts.md`
- [x] Sentrux baseline recorded, or N/A reason recorded -> N/A: Sentrux MCP is not available in this runtime; guard evidence is recorded by `gate_record check`.

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `N/A`
- Owner authorization source: `N/A`
- Reason: `N/A`

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scistudio.qa.governance.gate_record check --mode pre-commit` | `N/A` | `[ ]` | |
| Commit message | `python -m scistudio.qa.governance.gate_record check --mode commit-msg` | `N/A` | `[ ]` | |
| Pre-push | `python -m scistudio.qa.governance.gate_record check --mode pre-push` | `N/A` | `[ ]` | |
| Pre-PR reconcile | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `N/A` | `[ ]` | |

## 5.1 Docs Impact Check

- Wrapper/hook/gate-record/receipt/CI/runtime behavior changed: `no`
- AI docs checked:
  `docs/ai-developer/rules.md`,
  `docs/ai-developer/specific_rules/gated-workflow.md`,
  `docs/ai-developer/specific_rules/agent-dispatch.md`,
  `docs/ai-developer/templates/*dispatch*.md`
- Updated docs or N/A rationale: N/A. This dispatch changes product code and
  specs only. `docs/ai-developer/**` is out of scope.

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| `A1` | `implementer` | `N/A` | prompts §A1 | O1: capability extensions and enterprise UI, plus #2328 and the `ai_pty` internal prefix | `feat/2322-enterprise-ui` | `.worktrees/feat-2322-enterprise-ui` | see prompts §A1 | `webmcp.py`, `cli/**`, enterprise code | `#2322`, `#2328`, PR #2336 | `[~]` Fix round head 07c474836. It covers the P1 fix (strictly-below prefix matching plus the reserved tab id), the restart race and `confirm_active_runs`, upload staging semantics, URL and path hardening, the shared resolver, and the ratchet fix (commits 5ad2720e8, 7e116e7df, c063860ea). Both audit branches are merged. AU1 passed its re-verification and AU2 passed with fixes. Final round, head dd51834ba: re-verification reports merged (93c3a05ab), plus the CHANGELOG refused-areas line (9f2273842). CI is being watched. After it, the PR is ready for owner merge, pending owner approval of the #2337 deferrals. |
| `A2` | `implementer` | `N/A` | prompts §A2 | O2: stdio MCP adapter and loopback token file, plus #2333 | `feat/2308-webmcp-adapter` | `.worktrees/feat-2308-webmcp-adapter` | see prompts §A2 | `seam.py`, `spa.py`, `app.py`, `ai_pty/**`, `frontend/**` | `#2308`, `#2333`, PR #2329 | `[~]` PR open. CI is green at f130ee558. Commits: 3db69c431, d1438dc14, fcf894175, 4cf18fff0, 5756b4e4e. Audits are running. |
| `AU3b` | `audit_reviewer` | `with-context` | template filled at dispatch (2026-09-11) | audit O2, PR #2329 | `audit/2308-with-context` | `.worktrees/audit-2308-with-context` | `docs/audit/2026-09-11-adr-055-spec4-o2-with-context.md` | product code | PR #2329 | `[~]` |
| `AU4b` | `audit_reviewer` | `no-context` | template filled at dispatch (2026-09-11) | audit the adapter, the token file and the MCP socket surfaces | `audit/2308-no-context` | `.worktrees/audit-2308-no-context` | `docs/audit/2026-09-11-adr-055-spec4-o2-no-context.md` | product code | none (no-context) | `[~]` |
| `AU1` | `audit_reviewer` | `with-context` | template filled at dispatch (2026-09-11) | audit O1, PR #2336 | `audit/2322-with-context` | `.worktrees/audit-2322-with-context` | `docs/audit/2026-09-11-adr-055-spec4-o1-with-context.md` | product code | PR #2336 | `[~]` |
| `AU2` | `audit_reviewer` | `no-context` | template filled at dispatch (2026-09-11) | audit the seam, capabilities, enterprise UI and ai_pty surfaces | `audit/2322-no-context` | `.worktrees/audit-2322-no-context` | `docs/audit/2026-09-11-adr-055-spec4-o1-no-context.md` | product code | none (no-context) | `[~]` |
| `AU3` | `audit_reviewer` | `with-context` | assigned after the A2 PR | audit O2 | read-only | own worktree | `docs/audit/2026-09-*-adr-055-spec4-o2-with-context.md` | product code | A2 PR | `[ ]` |
| `AU4` | `audit_reviewer` | `no-context` | assigned after the A2 PR | audit O2 | read-only | own worktree | `docs/audit/2026-09-*-adr-055-spec4-o2-no-context.md` | product code | A2 PR | `[ ]` |
| `A3` | `implementer` | `N/A` | prompts §A3 | O3: remove the GUI-disconnect auto-cancel without regressing #1500 | `fix/2327-run-lifetime` | `.worktrees/fix-2327-run-lifetime` | see prompts §A3 | `seam.py`, `spa.py`, `ai_pty/**`, `webmcp.py`, `cli/**`, `frontend/**` | `#2327`, PR #2334 | `[~]` PR open, CI running |
| `AU5` | `audit_reviewer` | `with-context` | template filled at dispatch (2026-09-11) | audit O3, PR #2334 | `audit/2327-with-context` | `.worktrees/audit-2327-with-context` | `docs/audit/2026-09-11-adr-055-spec4-o3-with-context.md` | product code | PR #2334 | `[~]` |
| `AU6` | `audit_reviewer` | `no-context` | template filled at dispatch (2026-09-11) | audit O3 run lifetime | `audit/2327-no-context` | `.worktrees/audit-2327-no-context` | `docs/audit/2026-09-11-adr-055-spec4-o3-no-context.md` | product code | none (no-context) | `[~]` |
| `A4` | `implementer` | `N/A` | written at dispatch | O4: Package Manager for editions via a seam capability (owner option C) | `feat/2331-edition-package-manager` | `.worktrees/feat-2331-edition-package-manager` | `routes/packages.py`, seam capability, frontend Package Manager gate | everything else | `#2331` | `[ ]` queued after #2322 merges |
| `A5` | `implementer` | `N/A` | written at dispatch | O5: ABI-keyed user site and automatic background reinstall (owner option C) | `feat/2332-user-site-abi-repair` | `.worktrees/feat-2332-user-site-abi-repair` | `desktop/paths.py`, `desktop/package_installer.py`, the startup repair in `api/runtime/__init__.py`, the frontend notice | everything else | `#2332` | `[ ]` queued after #2322 and #2327 merge |

## 7. Track: O1 — Capability Extensions And Enterprise UI (#2322)

### 7.1 Track Scope

- Owner: `A1`
- In scope: see §2, O1. The shared capability contract is in #2321.
- Out of scope: `src/scistudio/api/routes/webmcp.py`, `src/scistudio/cli/**`,
  and anything enterprise.
- Required docs:
  - `docs/specs/adr-055-enterprise-support.md` (dynamic `update`);
  - `docs/specs/adr-055-identity-seam.md` (FR-014 to FR-016);
  - `CHANGELOG.md`;
  - the public-surface reference.
- Required tests:
  - `tests/api/test_enterprise_capabilities.py`;
  - `tests/api/test_ai_pty_capability.py`;
  - `tests/api/test_identity_seam.py` (extended);
  - `frontend/src/lib/capabilities.test.ts`;
  - `frontend/src/components/Enterprise/*.test.tsx`.

### 7.2 Dispatch

- [ ] Prompt file created or dispatch prompt recorded.
- [ ] Correct prompt template selected.
- [ ] Audit mode recorded when persona is `audit_reviewer`.
- [ ] Agent branch/worktree assigned.
- [ ] Write set and out-of-scope paths included in prompt.
- [ ] TODO rule included in prompt.
- [ ] Required checks included in prompt.

### 7.3 Implementation

- [ ] Seam capability extensions and page injection -> `<commit>`
- [ ] Frontend capability accessor and enterprise components -> `<commit>`
- [ ] Agent-kind PTY refusal when `ai_chat_disabled` -> `<commit>`
- [ ] Tests at the root mount and under `/user/alice/scistudio` -> `<test command>`
- [ ] Spec, CHANGELOG, and public-surface updates -> `<commit>`

### 7.4 Audit

- [x] Audit agents assigned -> AU1 (with-context), AU2 (no-context).
- [x] Audit report file paths assigned -> `docs/audit/2026-09-11-adr-055-spec4-o1-{with,no}-context.md`
- [x] Audit reports committed -> AU1 aef739e2e plus re-verification 6f3b9db1e; AU2 4688128ac.
- [x] Audit reports merged into the final PR evidence path -> A1 merged both audit branches (f12f21e57, da3e2fae1). The AU1 re-verification commit is still to be merged.
- [x] Findings recorded -> drift log. Both audits blocked on the terminal-bypass P1.
- [x] P1 findings fixed before integration -> 7e116e7df: the seam exempts only paths strictly below a prefix, and the terminal refuses the reserved tab id. AU1 re-verification at 07c474836 **passes**, and CI is 17/17 green at 07c474836. The AU2 re-audit at 07c474836 recommends **pass-with-fixes** (9ecb0b28d):
  - The Windows stream-suffix gap in the built-in author tools predates this PR and is tracked as a new issue.
  - A CHANGELOG line naming the refused areas: A1's final round.
  - The availability install hint is tracked in #2337.
  - The general route-collision check is tracked in #2338.

  A1's final round merges both re-verification commits and the CHANGELOG line.
- [ ] P2/P3 findings fixed or tracked with owner-approved rationale. Fixed: the ratchet, the restart race, upload semantics, URL and path hardening. Deferred to #2337: P2-3 (tutorial replay hidden) and P2-4 ("Bring in my work" returns 500), plus N-1 (availability grading). **These deferrals need owner approval**, batched with the merge request.

### 7.5 Integration

- [ ] Agent output reviewed by manager.
- [ ] Scope compliance verified.
- [ ] Conflicts resolved intentionally.
- [ ] Track merged or integrated.

## 8. Track: O2 — Stdio MCP Adapter (#2308)

### 8.1 Track Scope

- Owner: `A2`
- In scope: see §2, O2.
- Out of scope:
  - `src/scistudio/api/seam.py`, `src/scistudio/api/spa.py`,
    `src/scistudio/api/app.py`, `src/scistudio/api/routes/ai_pty/**`,
    `frontend/**`;
  - the local socket audience rule (#2275).
- Required docs:
  - `docs/specs/adr-055-enterprise-support.md` (adapter details);
  - `CHANGELOG.md`;
  - CLI help.
- Required tests:
  - `tests/cli/test_webmcp_adapter.py`;
  - `tests/api/test_webmcp.py` (token file).

### 8.2 Dispatch

- [ ] Prompt file created or dispatch prompt recorded.
- [ ] Correct prompt template selected.
- [ ] Agent branch/worktree assigned.
- [ ] Write set and out-of-scope paths included in prompt.
- [ ] TODO rule included in prompt.
- [ ] Required checks included in prompt.

### 8.3 Implementation

- [ ] Loopback token file (owner-only, per launch, removed on shutdown, not written with a replacement guard) -> `<commit>`
- [ ] Adapter: `tools/list` and `tools/call` forwarding, stale-context handling, bearer credential, bounded logging -> `<commit>`
- [ ] Config snippet command -> `<commit>`
- [ ] Tests -> `<test command>`
- [ ] Spec and CHANGELOG -> `<commit>`

### 8.4 Audit

- [ ] Audit agents assigned (AU3 with-context, AU4 no-context).
- [ ] Audit reports committed and merged into the final PR evidence path.
- [ ] P1 findings fixed before integration; P2/P3 fixed or tracked.

### 8.5 Integration

- [ ] Agent output reviewed by manager.
- [ ] Scope compliance verified.
- [ ] Track merged or integrated.

## 9. Track: O3 — Run Lifetime Without The GUI-Disconnect Cancel (#2327)

### 9.1 Track Scope

- Owner: `A3`
- In scope:
  - Remove the last-`/ws`-disconnect auto-cancel from `src/scistudio/api/ws.py`.
  - Keep #1500's guarantee that no run's lineage stays `running`. Terminal
    state must be reached on graceful shutdown, on the next startup after a
    kill or crash, and when a worker dies.
- Owner decision (2026-09-11, #2327): option 1, with the no-regression
  constraint.
- Out of scope: the seam, the frontend, the adapter, and `ai_pty`.
  `src/scistudio/core/**` is a stop condition: report the exact change and the
  manager asks the owner for `admin-approved:core-change`.
- Required tests: a GUI disconnect no longer cancels runs; shutdown mid-run
  leaves a terminal lineage state; a simulated crash is reconciled at the next
  startup; the #1500 scenario is reproduced as a regression test.

### 9.2 Dispatch

- [x] Prompt recorded -> prompts §A3
- [x] Agent branch/worktree assigned -> `fix/2327-run-lifetime`
- [x] Write set, out of scope, TODO rule, and checks included in prompt.

### 9.3 Implementation

- [ ] Auto-cancel removed -> `<commit>`
- [ ] Shutdown and startup terminal-state guarantees -> `<commit>`
- [ ] Regression tests -> `<test command>`

### 9.4 Audit and Integration

- [x] PR opened -> #2334. It uses the existing lineage APIs and states, per-run owner markers, reconciliation when the store opens, and a bounded shutdown finalize. No core or schema change.
- [~] Audits dispatched on their own -> AU5 (with-context), AU6 (no-context). Each report is committed on its audit branch, and the manager merges it into `fix/2327-run-lifetime`.
- [x] AU6 (no-context) -> **block**. The report is `docs/audit/2026-09-11-adr-055-spec4-o3-no-context.md` on `audit/2327-no-context` (d50ef37b).
  - P1: reopening a project with a run live closes its lineage store, so the terminal write is lost and the next open reconciles a completed run to `failed`.
  - P2: desktop quit force-kills and skips graceful shutdown.
  - P2: the run lifetime rules have no governing doc.
  - Several P3s.
- [x] AU5 (with-context) -> **block**. The report is `docs/audit/2026-09-11-adr-055-spec4-o3-with-context.md` on `audit/2327-with-context` (2f2f7ea05).
  - It confirms P1-1 and adds that a mid-run project switch also strands the row.
  - P2-1: cross-host owners count as alive forever, because hostnames are unstable.
  - P2-2: `run-owners/` is missing from `ARCHITECTURE.md` §11.2.
  - P3s: an unreadable marker is treated as a dead owner, and there is a sweep race, a double finalize, and ledger nits.
  - CI is 17/17 green.
- [x] Manager decision on the project switch, following the owner's #2327 rule: the previous project's live runs continue, and their store stays open until they finish.
- [x] P1 findings fixed; P2/P3 fixed or tracked. A3's fix round, with both audit branches merged in, runs from commit 6ee4b109a (first round) to 0ac9045cb (fixes); head 4d02f0423. It covers:
  - the reopen and switch fix, where the store stays open until live runs finish;
  - the desktop graceful stop: SIGTERM on POSIX, stdin EOF on Windows, force-kill at 15 s;
  - machine-ID ownership with a 24 h cross-machine warning;
  - Spec 3 FR-015/FR-016 and §4.6;
  - the P3s, plus symlink-safe MCP pointer writes.
- [~] Re-verification: AU5 re-verifies with context. AU6 re-audited without context at 4d02f0423 (97724be1) and says **still block**:
  - P1-1 fixed. The earlier P2s and P3s are fixed or documented.
  - New N1 (P1): the Windows stdin stop watcher makes child processes that inherit stdin, such as git, hang. Project create and open freeze and the event loop stalls.
  - New N2 (P2): uvicorn has no graceful timeout, and SSE and `/ws` keep it waiting, so the lifespan never runs before the force-kill.
  - New P3s: N3 (deleting the project mid-run resurrects it) and N5 (the stdin pipe is used on every platform).
  - All are routed to A3 in the same round as the main merge.
- [ ] Owner approvals pending, batched with the merge request:
  - `ARCHITECTURE.md` §11.2 rows for `run-owners/` and `mcp.sock.path` need `admin-approved:architecture-doc`;
  - #2344 (core `finalize_run` guard) needs `admin-approved:core-change`.
- [ ] Track merged.

## 10. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Gate ledger check (pre-PR) | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `[ ]` | |
| Gate finalize (pre-PR) | `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#2321"` | `[ ]` | |
| Track CI | per-track PR checks | `[ ]` | |

## 11. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| 2026-09-11 | manager | The umbrella issue #2321 and the issue map comment carry enterprise route names and track details in a public repository. | Reported to owner; enterprise prompts are kept in the private repository. | owner decision pending |
| 2026-09-11 | manager | Owner chose to trim the public issues (option b). | Issue-map comment deleted; #2321 body reduced to open-source content; enterprise details moved to the private tracker. GitHub keeps body edit history. | done |
| 2026-09-11 | manager | The enterprise guard track found that `/api/ai/pty/internal/*` worker callbacks are refused by any replacement guard. No other internal callback routes exist. | Added to A1's scope (inside `ai_pty/**`): verify the IPC token on every internal route, then register the prefix as self-authenticating. | #2322 |
| 2026-09-11 | manager | The enterprise guard track found that `ws.py` cancels every active run 2 s after the last `/ws` disconnect, which conflicts with ADR-055 external-AI mode and editions. | Opened #2327. Owner chose option 1 with the #1500 no-regression constraint. New track O3 (A3). | #2327 |
| 2026-09-11 | manager | An edition's transfer track stopped: the seam offers no public project root, tool-result error, author-blacklist check, shared write path, or upload event, and only internals reach them. | Opened #2328 and folded it into A1's scope, because it is the same seam module. The edition proceeds behind an adapter bound to the planned names. | #2328 |
| 2026-09-11 | manager | The edition's consumer fixed the #2328 signatures: `ToolRefusal(code, message, alternatives)`, `add_upload_listener` callback `(path, size, status)` returning an unsubscribe, and a new `"started"` status. | Sent to A1 as binding signatures. | #2328 |
| 2026-09-11 | manager | An edition security review found the open-source local MCP socket is protected only by file permissions, and its `/tmp` fallback name is predictable. | Opened #2333 and folded it into A2's scope (MCP transport files, no other owner). | #2333 |
| 2026-09-11 | A1 | Three items outside its write set. With `ai_chat_disabled`, "Bring in my work" fails with a 500 after writing a session brief. Tutorial replays are hidden with the AI Chat tab. A mypy error sits at `tests/api/test_identity_seam.py:171` on an untouched line. | Opened #2337 for the first two. The mypy item goes to the audits and CI. | #2337 |
| 2026-09-11 | A1 | `transfer=True` now raises `TypeError`, a provisional break per ADR-052, recorded in CHANGELOG "Changed". `ToolRefusal`'s `alternatives` is `use_instead` on the wire. `write_project_file` is async. | Recorded for the edition integration step. | N/A |
| 2026-09-11 | manager | PR #2336's "Deferral discipline ratchet" failed on 4 false positives: "placeholder" meaning the download template's `{path}` marker in `seam.py`. | A1 rewords them to "`{path}` marker" (renaming `_PATH_PLACEHOLDER` to `_PATH_MARKER`), with no tracked-TODO noise. | N/A |
| 2026-09-11 | AU1 | Audit of PR #2336 -> **block**. The report is `docs/audit/2026-09-11-adr-055-spec4-o1-with-context.md` on `audit/2322-with-context` (aef739e2e).<br>P1: the bare `/api/ai/pty/internal` path is exempt from the guard and collides with the terminal WebSocket `/api/ai/pty/{tab_id}`, which gives an unauthenticated shell under a replacement guard.<br>P2s: the restart-confirm race (also a Codex P1), the CHANGELOG replay claim, "Bring in my work" (#2337), the upload `started` semantics and project drift (also a Codex P2), and CI red on the ratchet.<br>P3s: `..`/BOM segments in capability URLs, the `public-api.md` row, and CodeQL alert 286. | A1 fixes all of them in one round. The P1 gets two fixes: an `ai_pty` tab-id refusal, and the seam matching only strictly below a prefix. | #2322, #2328 |
| 2026-09-11 | AU2 | No-context audit of PR #2336 -> **block**. The report is `docs/audit/2026-09-11-adr-055-spec4-o1-no-context.md` on `audit/2322-no-context` (4688128ac).<br>It confirms the P1 (the bare internal prefix opens a terminal without authentication).<br>New P2s: a Windows `::$DATA` suffix bypasses the author blacklist, and `check_author_path` expands `~` while `write_project_file` does not.<br>New P3s: NUL bytes, the undocumented `changed_by`, `/api/ai/status` probing agents when AI chat is disabled, the unescaped base-path bootstrap, and non-ASCII whitespace. | Forwarded to A1 with a scope amendment for the AI status route. | #2322, #2328 |
| 2026-09-11 | AU3b | With-context audit of PR #2329 -> **block**. The report is `docs/audit/2026-09-11-adr-055-spec4-o2-with-context.md` on `audit/2308-with-context` (002cac1bf).<br>P1: queued parallel mutations are redirected to the new project after a stale-context swap.<br>P2s: the loopback token can reach a proxy or a LAN URL taken from the token file; the ADR-055 §4 amendment is missing; `mcp-bridge` trusts the `mcp.sock.path` pointer without an ownership check.<br>P3s: hang on stdin EOF, IPv6 URL formatting, an unenforced startup timeout, token-file PID reuse and same-port collisions, and bearer tokens sent over plain http. Codex has 4 unanswered comments. | A2 fix round. Scope amendments authorized by the manager: `docs/adr/ADR-055.md` (§4 only) and `src/scistudio/cli/mcp_bridge.py` (pointer validation only). | #2308, #2333 |
| 2026-09-11 | A3 | Out-of-scope findings from the #2334 fix round:<br>- `finalize_run` has no terminal-status guard (core);<br>- a run that continues across a project switch can't resolve its own project's block types (registry refresh);<br>- `workflow_runs` is keyed by workflow ID only;<br>- the gate ledger's `verified_in_diff`/`body_closes_issues` are never assigned;<br>- #2335 is fixed by 0ac9045cb;<br>- the `ARCHITECTURE.md` §11.2 rows are drafted but need an owner label. | Filed #2344 (core, needs `admin-approved:core-change`), #2345 (registry per project) and #2346 (ledger fields). Commented on #1517 about the new exposure, and on #2335 that it will close when #2334 merges. The `ARCHITECTURE.md` rows wait for owner approval. | #2344, #2345, #2346, #1517, #2335 |
| 2026-09-11 | manager | Main moved: #2343 (fix #2330) rewrote API docstrings to remove development references and added a blocking `docstrings` check to `full_audit`. PRs #2334, #2336 and #2329 became CONFLICTING, so the main CI stopped running on them; #2334 showed only 4 checks. The overlaps are `app.py` (#2334 and #2336); `ai_pty/**`, `data.py`, `ai.py`, `tools_workspace.py` and the reference pages (#2336); and MCP `runtime.py`/`server.py` (#2329). | A1, A2 and A3 each merge `origin/main`, resolve conflicts keeping main's cleaned docstrings, move development refs from their own docstrings into comments, regenerate the reference pages, and pass `full_audit` including `docstrings`. Merge order: #2336 first; then #2334 and #2329 each do one more small main merge. | #2330, #2343 |
| 2026-09-11 | AU4b | No-context audit of PR #2329 -> **block**. The report is `docs/audit/2026-09-11-adr-055-spec4-o2-no-context.md` on `audit/2308-no-context` (27dcd7d3c).<br>It confirms the P1.<br>New P2s: a second backend on the same port deletes the live backend's token file; the socket pointer is written through a planted symlink (`_projects._publish_mcp_port`).<br>New P3s: an echoed `--base-url` value, `print-config` consistency, a malformed token file blocking discovery, a fallback-dir takeover, the chmod window, and docs drift. The unauthenticated TCP transport on Windows has no tracking. | A2: token-file lifecycle and the P3s. A3: the symlink-safe pointer write in `_projects.py` (its file) and `ARCHITECTURE.md` `mcp.sock.path`. The Windows TCP transport is filed as a new issue. | #2308, #2333 |
| 2026-09-11 | manager | An edition's security review made the backend enforce the active-runs warning on restart (409 unless `{"confirm_active_runs": true}`). | Added to the #2321 contract (comment) and to A1's current #2336 round in `UpdateNotice.tsx`: send the field after the warning is accepted, and re-confirm on a 409. | #2322 |
| 2026-09-11 | A2 | #2308 asks for an ADR-055 §4 amendment (the second consumer of the bridge), but `docs/adr` was outside A2's write set. The gate records docs N/A. | Queued for A2's post-audit fix round as a scope amendment to `docs/adr/ADR-055.md` (§4 only). | #2308 |
| 2026-09-11 | manager | The edition security review (E1) produced two open-source follow-ups. One is seam hardening: freeze the self-authenticating registry after startup, and refuse plain `serve` under a Hub spawn env. The other is that internal loopback callbacks fail when the backend serves TLS with client certs (`internal_ssl`). | Filed #2338 and #2339, both queued after #2336 merges. Until #2339 ships, the edition runbook warns that AI chat plus `internal_ssl` is unsupported. | #2338, #2339 |
| 2026-09-11 | manager | The AU6 audit of #2334 found desktop quit force-kills the backend, so graceful run shutdown never runs on desktop. | Scope amendment for A3, authorized by the manager: `desktop/main.js` (the stop sequence only) and `desktop/test/**`. The new sequence is a graceful request, a bounded wait of at least 12 s, then a force kill, keeping the ADR-055 Spec 3 guarantees. | #2327 |

## 12. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, commit,
      and PR evidence.
- [ ] PR closes every issue fixed by the dispatch.
- [ ] CI passed.
- [ ] Checklist final state matches PR and gate record.
