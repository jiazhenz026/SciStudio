---
title: "ADR-055 Spec 2-3 Agent Dispatch Checklist"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 55
related_specs:
  - adr-055-agent-context-workspace
  - adr-055-local-background-runtime
language_source: en
---

# ADR-055 Spec 2-3 Agent Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: "After the design discussion, start a manager worktree and
  implement ADR-055 Spec 2 and Spec 3." Each PR updates its own spec to the
  owner decisions recorded on 2026-09-10 in its issue.
- Task kind: `feature` (implementation tracks); `manager` (this checklist)
- Manager persona: `manager`
- Issue: `#2282` (manager); implementation `#2279` (Spec 2), `#2280` (Spec 3);
  related out-of-scope fix `#2281` (worker orphan cleanup, owner-separated)
- Gate record: `.workflow/records/2282-track-adr-055-spec2-3.json`
- Branch/worktree plan: manager umbrella `track/adr-055-spec2-3` at
  `.worktrees/track-adr-055-spec2-3`; agent branches
  `feat/2279-agent-context-workspace` (stacked on
  `feat/2271-webmcp-bridge`, `--base-ref` recorded per #2143; rebased onto
  `main` before its PR opens, after PR #2275 merges — owner option B) and
  `feat/2280-local-background-runtime` (base `origin/main`)
- Protected branch: `main`
- Umbrella branch: `track/adr-055-spec2-3`
- Umbrella PR: `#2283`
- Umbrella PR title: `[DO NOT MERGE] ADR-055 Spec 2-3 dispatch`
- Final PR target: `main` (manager assigns both spec PRs as final PRs to the
  protected branch; the Spec 2 PR opens only once its base is `main`, so
  `ci.yml` runs on it)
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context:
    `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context:
    `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`
- Filled prompts: `docs/planning/adr-055-spec2-3-dispatch-prompts.md`

## 2. Scope

- In scope:
  - Spec 2 (`docs/specs/adr-055-agent-context-workspace.md`) as amended by the
    #2279 owner decisions: `get_agent_context`; inspect tools (absolute paths,
    OS-user read scope, bounded streaming reads); author tools (project-confined,
    server-side hook blacklist for `workflows/*.yaml` and `data/`); hook parity
    via tool results (list_blocks-before-block-write per backend lifetime,
    concrete port type warning, scistudio CLI denial in `run_command`,
    `run_workflow` poll hint); managed `run_command` (asyncio, ProcessRegistry,
    bounded output, request-vs-job cancellation, in-memory status); spec text
    updates, including moving transfer into the Spec 4 spec text
  - Spec 3 (`docs/specs/adr-055-local-background-runtime.md`) as amended by the
    #2280 owner decisions: mode picker on every launch with "don't ask again";
    headless external-AI mode with tray (menu: open connection window, copy
    address, status, open in desktop mode, stop and quit) and connection window;
    backend stops with Electron (POSIX watchdog kept; Windows verified, backstop
    added only if needed); mode-aware `second-instance`; OTA inclusion; shell
    file lists kept in parity; spec text updates
- Out of scope:
  - Transfer implementation (upload picker, download endpoint): Spec 4
    (`adr-055-lab-deployment`)
  - Worker/grandchild orphan cleanup on backend stop: #2281
  - Hub OAuth / lab deployment: Spec 4
  - AI-host presentation (deferred by owner)
  - Spec 0/1 code except the minimal, gate-amended touch points named in the
    Spec 2 prompt (PRs #2274/#2275 own those files)
  - `docs/ai-developer/**` (governance surface) including the release runbook
- Protected paths: none expected; any `src/scistudio/core/**` need is a stop
  condition
- Deferred work: transfer -> Spec 4 spec text (owner decision, moved in the
  Spec 2 PR); worker orphans -> #2281

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

- [x] Dedicated manager branch and worktree created. ->
      `track/adr-055-spec2-3` at `.worktrees/track-adr-055-spec2-3`
- [x] Existing issue linked, or new issue created only if none exists. ->
      #2279, #2280, #2281, #2282 (no open issue tracked the work; #2263 closed)
- [x] Gate record started. -> `.workflow/records/2282-track-adr-055-spec2-3.json`
- [x] Scope include/exclude recorded in the gate record.
- [x] Umbrella branch created. -> `track/adr-055-spec2-3`
- [x] Umbrella PR opened. -> #2283 (via `scripts/scistudio_pr_create.py`, pre-flight clean)
- [x] Umbrella PR title includes `[DO NOT MERGE]`.
- [x] Protected branch and umbrella PR number recorded in this checklist. -> main / #2283
- [x] No `pip install -e .` environment pollution found. -> gate CLI runs via
      `PYTHONPATH=src`, no editable install
- [x] Dispatch checklist copied from the template and committed.
- [x] Dispatch prompts created from the correct prompt template and linked
      below. -> `docs/planning/adr-055-spec2-3-dispatch-prompts.md` (A1, A2;
      audit prompts appended before audit dispatch)
- [x] Sentrux baseline recorded, or N/A reason recorded. -> N/A: Sentrux MCP
      not available in this runtime; guard evidence is recorded by
      `gate_record check` where applicable.

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `N/A`
- Owner authorization source: `N/A`
- Reason: `N/A`

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scistudio.qa.governance.gate_record check --mode pre-commit` | `N/A` | `[ ]` | `<pending>` |
| Commit message | `python -m scistudio.qa.governance.gate_record check --mode commit-msg` | `N/A` | `[ ]` | `<pending>` |
| Pre-push | `python -m scistudio.qa.governance.gate_record check --mode pre-push` | `N/A` | `[ ]` | `<pending>` |
| Pre-PR reconcile | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file <body-file>` | `N/A` | `[ ]` | `<pending>` |

## 5.1 Docs Impact Check

- Wrapper/hook/gate-record/receipt/CI/runtime behavior changed: `no`
- AI docs checked:
  `docs/ai-developer/rules.md`,
  `docs/ai-developer/specific_rules/gated-workflow.md`,
  `docs/ai-developer/specific_rules/agent-dispatch.md`,
  `docs/ai-developer/templates/*dispatch*.md`
- Updated docs or N/A rationale: `N/A — no AI-workflow behavior changes`

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| `A1` | `implementer` | `N/A` | `docs/planning/adr-055-spec2-3-dispatch-prompts.md` (A1) | Spec 2 agent context, workspace, execution tools | `feat/2279-agent-context-workspace` | `.worktrees/feat-2279-agent-context-workspace` | prompt A1 "Scope" | `frontend/**`, `desktop/**`, `docs/ai-developer/**`, transfer, #2281 | `#2279` (branch pushed `b1693f913`; PR after #2275 merges) | `[x]` |
| `AU3` | `audit_reviewer` | `with-context` | `docs/planning/adr-055-spec2-3-dispatch-prompts.md` (AU3) | Audit the Spec 2 branch | `audit/2279-spec2-with-context` | `.worktrees/audit-2279-spec2-wc` | `docs/audit/2026-09-11-adr-055-spec2-with-context.md` | implementation code, checklist | `#2279` | `[~]` |
| `AU4` | `audit_reviewer` | `no-context` | `docs/planning/adr-055-spec2-3-dispatch-prompts.md` (AU4) | Independent audit of the Spec 2 surfaces | `audit/2279-spec2-no-context` | `.worktrees/audit-2279-spec2-nc` | `docs/audit/2026-09-11-adr-055-spec2-no-context.md` | implementation code, checklist, issue/PR/commit context | N/A (no-context) | `[~]` |
| `A2` | `implementer` | `N/A` | `docs/planning/adr-055-spec2-3-dispatch-prompts.md` (A2) | Spec 3 local startup modes and background runtime | `feat/2280-local-background-runtime` | `.worktrees/feat-2280-local-background-runtime` | prompt A2 "Scope" | `frontend/**`, `src/scistudio/**` (except conditional Windows backstop), `docs/ai-developer/**`, #2281 | `#2280` / PR #2284 | `[x]` |
| `A3` | `implementer` | `N/A` | `docs/planning/adr-055-spec2-3-dispatch-prompts.md` (A3) | Owner-directed addition to PR #2275: local socket `tools/call` rejects external-audience tools | `feat/2271-webmcp-bridge` | `.worktrees/feat-2271-webmcp-bridge` | `src/scistudio/ai/agent/mcp/server.py` (local `tools/call` only), `tests/ai/test_mcp_fastmcp.py`, `docs/specs/adr-055-webmcp-bridge.md` (FR-004 text) | everything else, esp. Spec 0 files, Spec 2 files | `#2271` / PR #2275 | `[~]` |
| `AU1` | `audit_reviewer` | `with-context` | `docs/planning/adr-055-spec2-3-dispatch-prompts.md` (AU1) | Audit PR #2284 (Spec 3) | `audit/2280-spec3-with-context` | `.worktrees/audit-2280-spec3-wc` | `docs/audit/2026-09-10-adr-055-spec3-with-context.md` | implementation code, checklist | `#2280` / PR #2284 | `[~]` |
| `AU2` | `audit_reviewer` | `no-context` | `docs/planning/adr-055-spec2-3-dispatch-prompts.md` (AU2) | Independent audit of the Spec 3 surfaces | `audit/2280-spec3-no-context` | `.worktrees/audit-2280-spec3-nc` | `docs/audit/2026-09-10-adr-055-spec3-no-context.md` | implementation code, checklist, issue/PR/commit context | N/A (no-context) | `[~]` |

## 7. Track: Spec 2 — Agent Context, Workspace, Execution

### 7.1 Track Scope

- Owner: `A1 (implementer)`
- In scope: spec `adr-055-agent-context-workspace` as amended by #2279
  decisions 1-6
- Out of scope: transfer (Spec 4), frontend, desktop, #2281
- Required docs: spec text updated to the decisions; Spec 4 spec gains the
  transfer requirements removed from Spec 2
- Required tests: `tests/ai/test_mcp_agent_context.py`,
  `tests/ai/test_mcp_workspace_tools.py`, `tests/ai/test_mcp_execution_tools.py`,
  `tests/api/test_projects.py` (write-helper parity), hook-parity cases

### 7.2 Dispatch

- [x] Prompt file created or dispatch prompt recorded. -> `docs/planning/adr-055-spec2-3-dispatch-prompts.md` (A1)
- [x] Correct prompt template selected. -> work template (non-audit)
- [x] Audit mode recorded when persona is `audit_reviewer`. -> N/A
- [x] Agent branch/worktree assigned (stacked on `feat/2271-webmcp-bridge`,
      `--base-ref` recorded).
- [x] Write set and out-of-scope paths included in prompt.
- [x] TODO rule included in prompt.
- [x] Required checks included in prompt.

### 7.3 Implementation

- [x] Shared write helper extracted; editor route parity -> `b1693f913` `src/scistudio/api/runtime/_file_writes.py` (`ApiRuntime.project_files`), editor PUT route delegates; tools reach it via `MCPContext.project_files` (no ai->api import; 13 import contracts kept)
- [x] `get_agent_context` -> `b1693f913` `tools_qa.py`, `tests/ai/test_mcp_agent_context.py`
- [x] Inspect + author tools with hook blacklist and parity results -> `b1693f913` `tools_workspace.py` (incl. `move_path`), `tests/ai/test_mcp_workspace_tools.py`; scaffold_block bridge check via a context variable set in `webmcp.py` dispatch
- [x] `run_command` + managed job tools -> `b1693f913` `tools_execution.py` (+ `list_commands`), registers in `app.state.registry` (shutdown `terminate_all` test passes), `tests/ai/test_mcp_execution_tools.py`
- [x] Spec 2 + Spec 4 spec text updated -> Spec 2 rewritten to #2279 decisions; Spec 4 gains US6, FR-012..FR-015, TransferRecord, T-007, SC-006 (lab-only)
- [!] Tests -> CORRECTED 2026-09-11 (AU3 P2-4, manager-verified): the A1 ledger's `observed_diff` has base = head = `e817f9b82`, `changed_files` 0, empty-string fingerprint, so the checks below ran against an EMPTY diff (before the commit) and are not evidence; must be re-run on the committed diff, and again after the rebase onto main. Original claim: Tier-1 `gate_record check --base origin/feat/2271-webmcp-bridge` exit 0 (arch, hygiene, deferral, format, full_audit, import contracts, lint, full xdist suite, type check) + pre-PR check exit 0; one real-pip test skips locally (uv venv has no pip) with stated reason, a pip-free `PIP_TARGET` import test runs everywhere

### 7.4 Audit

- [x] Audit agent assigned, or manager audit completed. -> AU3 (with-context), AU4 (no-context)
- [x] Audit report file path assigned. -> `docs/audit/2026-09-11-adr-055-spec2-with-context.md`, `docs/audit/2026-09-11-adr-055-spec2-no-context.md`
- [~] Audit report committed. -> AU3 `0517a0afb` + ledger `755ffc39c` on `audit/2279-spec2-with-context`; AU4 pending
- [~] Audit report merged into final PR evidence path. -> A1-fix1 cherry-picks the AU3 commits onto `feat/2279-agent-context-workspace`
- [~] Findings recorded. -> AU3 (with-context): **block**. P1-1: `delete_path`/`move_path` act on a symlink/junction's resolved target — deleting a junction deleted its target directory with files (reproduced through the bridge on Windows). P1-2: Windows `cancel_command` (and shutdown) miss descendants whose parent already exited — grandchild survives, job stays `running` (breaks SC-004). P2-1: `get_file_info`/`read_file`/`patch_file` advance the cached file version, so the watcher suppresses the FILE_CHANGED for external edits. P2-2: a finished command stays `running` while a background child holds its pipes (3.11 and 3.13). P2-3: refusals/conflicts return `isError: false` — owner decision. P2-4: A1 gate evidence covered an empty diff (see 7.3 correction). P2-5: no tests for links, exited-parent orphans, pipe-holding children, read-then-watcher, real HTTP abort. 10 P3s. Confirmed: #2279 decisions 1-6, blacklist held against case/separator/`./`/`..`/trailing dot+space/ADS/8.3/junction tricks, bridge marker does not leak, 13 import contracts kept, real-pip test runs in CI. AU4 pending
- [~] Fix round A1-fix1 dispatched (prompt in dispatch-prompts file); AU3 P2-3 held for the owner decision; AU4 findings to be appended
- [x] AU4 (no-context) committed: report `6c8130d22` + ledger `9ffd04034` on `audit/2279-spec2-no-context`. **block**. P1-1: a command whose descendant holds stdout/stderr never finishes (`process.wait()` waits for pipe EOF), cancel targets the reaped leader (Windows: psutil cannot walk; POSIX: `getpgid` fails before `killpg`), and `terminate_all` drops the stale handle — the grandchild survives cancel and shutdown (reproduced on Windows; supersedes AU3 P2-2). P2: link-following delete/move (= AU3 P1-1); read hides external edits (= AU3 P2-1); `search_files` cap counts matches not visited files and the walk is uncancellable (25,000 non-matching files scanned, reported `truncated=False`); test gaps. P3: FastMCP logs exception text with paths (pre-existing on base); external-audience tools callable by name over the local socket (visibility-only filter, Spec 1 `server.py`); author tools block the event loop (spec §4.1 says threads); `read_file` reads before taking the state version; `status="ok"` for non-zero exit / ineffective cancel; parent dirs created before conflict checks; shared job table with no concurrency limit
- [~] A1-fix1 addendum sent: cherry-pick the AU4 commits; fix AU4 P1-1, P2-3, P3-3/4/6; P3-1/2/7 left with rationale for manager tracking; AU4 P3-5 held with AU3 P2-3 (owner `isError` decision)
- [x] Owner decision (2026-09-11) on AU3 P2-3 + AU4 P3-5: refusals, write conflicts, non-zero command exits, and ineffective cancels return `isError: true` with the structured reason kept (tool result with the error flag, not a raised exception). Sent to A1
- [x] Owner decision (2026-09-11) on AU4 P3-2: external-audience tools must be rejected when called by name over the local socket transport (not only hidden from its catalogue), landed on `feat/2271-webmcp-bridge` (PR #2275) before it merges. Dispatched as A3 (see dispatch matrix); A1 merges the updated base
- [ ] P1 findings fixed before integration.
- [ ] P2/P3 findings fixed or tracked with owner-approved rationale.

### 7.5 Integration

- [ ] Agent output reviewed by manager.
- [ ] Scope compliance verified.
- [ ] Conflicts resolved intentionally.
- [x] Dependency: PR #2274 (Spec 0) merged by the owner 2026-09-11 at `b8627c3fb`; verified landed (0 commits of `feat/2270` outside main, `base-path.ts` on main, #2270 CLOSED). A3 asked to move the #2275 ledger base to main and merge origin/main (picks up #2277 fastmcp `<5`) before #2275 merges
- [ ] Rebased onto `main` after PR #2275 merged; PR opened against `main`.
- [ ] Track merged or integrated.

## 8. Track: Spec 3 — Local Startup Modes And Background Runtime

### 8.1 Track Scope

- Owner: `A2 (implementer)`
- In scope: spec `adr-055-local-background-runtime` as amended by #2280
  decisions 1-5
- Out of scope: `runtime-port.js` discovery changes (dropped by owner),
  instance adoption, worker cleanup (#2281), frontend, lab deployment
- Required docs: spec text updated to the decisions
- Required tests: `desktop/test/background-mode.test.js`,
  `desktop/test/bootstrap.test.js` and `tests/scripts/test_ota_publish.py`
  (shell file list parity), `desktop/test/menu.test.js`

### 8.2 Dispatch

- [x] Prompt file created or dispatch prompt recorded. -> `docs/planning/adr-055-spec2-3-dispatch-prompts.md` (A2)
- [x] Correct prompt template selected. -> work template (non-audit)
- [x] Audit mode recorded when persona is `audit_reviewer`. -> N/A
- [x] Agent branch/worktree assigned.
- [x] Write set and out-of-scope paths included in prompt.
- [x] TODO rule included in prompt.
- [x] Required checks included in prompt.

### 8.3 Implementation

- [x] Mode picker (every launch, "don't ask again", changeable later) -> PR #2284 `desktop/splash.html`, `desktop/menu.js` (File › Startup Mode)
- [x] Headless mode, tray, connection window, stop/restart -> PR #2284 `desktop/main.js`, `desktop/connection.html`, `desktop/connection-preload.js`, `desktop/assets/tray*`
- [x] Mode-aware `second-instance` and `window-all-closed` -> PR #2284 `desktop/background-mode.js` (pure logic)
- [x] OTA inclusion and mode-honoring relaunch -> PR #2284 shared stop-then-relaunch helper, `--scistudio-launch-mode`
- [x] Windows backend-lifetime verification (backstop only if needed) -> A2 Node-level repro: Node 24.14.0 x3 and Electron 42.2.0-as-node x2, `taskkill /F` on the parent kills the non-detached backend child every run; no backstop; grandchild survives every run (#2281)
- [x] Shell file lists (`build.files`, `SHELL_FILES`) in parity -> PR #2284 `tests/scripts/test_ota_publish.py` parity + shipped-require/asset check (43/43)
- [x] Spec 3 spec text updated -> PR #2284 `docs/specs/adr-055-local-background-runtime.md` (FR-009 withdrawn, FR-012 tray, FR-013 known-good vouching)
- [x] Tests -> desktop `npm test` 193/193; CI 16/16 green at `5c0ddefac`
- [x] Manager review: known-good vouching in external-AI mode requires connection-window bridge ready AND service running (`maybeVouchForShellInBackground`, `main.js:1792`); readiness alone never records — rule of `shell-known-good.test.js` holds semantically, not only textually

### 8.4 Audit

- [x] Audit agent assigned, or manager audit completed. -> AU1 (with-context), AU2 (no-context)
- [x] Audit report file path assigned. -> `docs/audit/2026-09-10-adr-055-spec3-with-context.md`, `docs/audit/2026-09-10-adr-055-spec3-no-context.md`
- [x] Audit report committed. -> AU2 `caf5865e5` on `audit/2280-spec3-no-context`; AU1 `b4312fdb0` + ledger `c67327a56` on `audit/2280-spec3-with-context`
- [~] Audit report merged into final PR evidence path. -> A2-fix1 cherry-picks all four audit commits onto `feat/2280-local-background-runtime` (Spec 0/1 round pattern)
- [~] AU1 (with-context) findings: pass-with-fixes, P2 x5 — (1) quitting at the launch-mode picker leaves the loader crash-loop marker set, so a working patched shell is refused on every later launch (new; not exercised by the owner's build-0 dev run); (2) = AU2 P2-2 SIGKILL escalation dead (also Codex 3985756076); (3) = AU2 P2-1 resident app with no backend (also Codex 3985756074) — conflicts with FR-008, owner decision needed; (4) main.js orchestration has no behavioural tests — 5 of 10 mutations survive the committed suite; (5) CHANGELOG missing (owner already decided to add). 12 P3s. Confirmed owner decisions 1-5, Windows lifetime (3/3 Node, 2/2 Electron-as-node), connection-window security, shell lists complete today (tests only partly enforce). Correction to 8.3: the vouching invariant holds in code, but tests check only that the names appear
- [~] Fix round A2-fix1 dispatched (prompt in dispatch-prompts file); P2-3 held for the owner decision
- [x] A2-fix1 delivered: audit commits cherry-picked (`e9a8e255d`, `e5ddaee03`, `263620130`, `f9a839824`), fix `8a80d4ea6`, ledger `a4525c224`/`5465bcc79`; CI 16/16 at `5465bcc79`. All P2s fixed; 19-scenario orchestration suite (`desktop/test/main-orchestration.test.js` + `desktop/test/harness/**`) catches mutations M3-M10; desktop `npm test` 221/221; CHANGELOG entry added. P3s not fixed (rationale in A2 report): AU1 P3-8 switched desktop session relaunches without a main window (needs owner confirmation), AU1 P3-10 `127.0.0.1` vs ADR `localhost` (spec explains), AU1 P3-12 user-guide page (outside write set; needs a tracked follow-up), AU2 P3-7 external-AI vouching proves only the connection window (informational), AU2 P3-6 spec status stays Draft until the three-platform installed-build checks
- [x] Manager review of A2-fix1: `stopRuntime` escalates on `isChildRunning` (`exitCode`/`signalCode` null) instead of `child.killed`; the boot marker is released only in `before-quit`, before `stopRuntime`, when `pickerRendered && !shellFault` (`releasesBootMarkerOnQuit`); CI 16/16 confirmed
- [x] Owner decision on P2-3 (2026-09-11): **quit** — in external-AI mode, when no window is open and the service stops, crashes or fails, the app quits (re-evaluated on every service state change); with a window open, the connection window keeps showing stopped/crashed with Restart. FR-008 text narrowed accordingly. Sent to A2
- [~] Findings recorded. -> AU2 (no-context): pass-with-fixes, P1 0 / P2 2 / P3 7. P2-1: external-AI app stays resident with no windows when the service stops or crashes after the last window closed (`windowAllClosedAction` evaluated only on `window-all-closed`, `main.js:2251`) — new in this branch. P2-2: `stopRuntime` SIGKILL escalation is dead (`if (!child.killed)` after SIGTERM, `main.js:1544-1545`; Node sets `killed` once the signal is sent) — pre-existing on main, now load-bearing for Stop and OTA relaunch. Both manager-verified. P3: restart unresponsive up to 30 s after a startup crash; `stopRuntimeAndWait` does not wait when a stop is in flight; Stop and Quit lacks the attached-desktop confirmation; lifecycle tests are source-regex and `windowAllClosedAction` ignores `platform`; macOS Dock/Finder reopen may bypass `second-instance`; `docs/specs/desktop-shell-ota-hot-update.md` §6 shell list stale and spec frontmatter `feature_branch`/`tests` inaccurate; external-AI known-good covers only the connection window. AU1 pending
- [ ] P1 findings fixed before integration.
- [ ] P2/P3 findings fixed or tracked with owner-approved rationale.

### 8.5 Integration

- [ ] Agent output reviewed by manager.
- [ ] Scope compliance verified.
- [ ] Conflicts resolved intentionally.
- [ ] Track merged or integrated.

## 9. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Gate ledger check (local) | per-branch `gate_record check` | `[ ]` | `<pending>` |
| Targeted tests | per-track test files (sections 7.1, 8.1) | `[ ]` | `<pending>` |
| Pre-push gate check | n/a — pre-push hook is the allow shim; pre-pr is the hard local gate per ADR-042 Addendum 6 | `[ ]` | `<pending>` |
| Gate ledger check (pre-PR) | `gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `[ ]` | `<pending>` |
| Gate finalize (pre-PR) | `gate_record finalize --closes "#2279"` / `"#2280"` / `"#2282"` | `[ ]` | `<pending>` |
| Wrapper preflight | `python scripts/scistudio_pr_create.py` | `[ ]` | `<pending>` |
| CI | GitHub Actions | `[ ]` | `<pending>` |
| Spec 3 live launch evidence | Windows dev/installed launch by manager; macOS/Linux installed-build runs by owner | `[~]` | Windows: manager launched `feat/2280-local-background-runtime` @ `5c0ddefac` as a dev app (vite 127.0.0.1:5181, backend port 8210, worktree `src` on PYTHONPATH, venv interpreter); owner verified the launch-mode flow live on 2026-09-11 — "验证没问题". macOS/Linux installed builds: pending (owner) |

## 10. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| 2026-09-10 | manager | Owner decisions amend both specs (Spec 2: transfer moved to Spec 4, OS-user read scope, hook blacklist + parity via results, backend-lifetime list_blocks tracking; Spec 3: mode picker every launch, tray, backend stops with Electron) | Recorded in #2279/#2280; each PR updates its own spec text | N/A |
| 2026-09-10 | A1 | Needs `src/scistudio/api/app.py` (outside write set): the production `MCPContext` is `_RuntimeAdapter` inside the lifespan, and `app.state.registry` (the registry `terminate_all` runs on at shutdown) is created there, distinct from `ApiRuntime.process_registry` (LocalRunner's). Verified by manager at `e817f9b82` (`app.py:63/121/207`, `api/runtime/__init__.py:365`) | Manager approved: add `process_registry` and `project_files` members to `_RuntimeAdapter` only, gate-amended first, matching optional `MCPContext` members, no other app.py edits; `run_command` registers in `app.state.registry` | #2281 corrected (comment): workers live in `ApiRuntime.process_registry`, which `terminate_all` does not cover |
| 2026-09-10 | A1 | Needs `tests/ai/test_mcp_fastmcp.py` (outside write set): `test_fastmcp_lists_36_tools` pins the exact `mcp.list_tools()` name set, which includes external-tagged tools, so every new Spec 2 tool breaks it; the socket-transport count in `tests/integration/test_phase2_mcp_end_to_end.py` stays 36 (external tools filtered) | Manager approved: update the expected set only, gate-amended first | N/A |
| 2026-09-11 | A1 | Two more exact registry-count assertions break with the 14 new external tools (50 total): `tests/ai/test_finish_ai_block_skeleton.py::test_registry_now_has_36_tools`, `tests/contracts/test_runtime_import_contract.py::test_mcp_server_exposes_36_tools` | Manager approved: count/name-set update and rename to `*_50_tools` only, gate-amended first; xdist concurrency-test failure must be classified with evidence (own defect vs pre-existing flake on the stacked base) | N/A |
| 2026-09-11 | A1 | xdist failure classified: pre-existing `tests/ai/test_mcp_tools_disk_integration.py::test_concurrent_write_workflow_serialises` (one-off Windows atomic-replace race in `write_workflow` containment; not in the diff); `pytest -n auto tests/ai` 5/5 green on the base and 5/5 on the branch; matches closed-not-planned #2244 | Recorded; reopening #2244 left to the owner | Owner decision on #2244 pending |
| 2026-09-11 | A1 | Spec-silent choices in `b1693f913`, recorded in the spec: refusals (blacklist, list_blocks-first, CLI denial, conflict) returned as `status` + refusal code/message/alternative tool rather than exceptions (bridge withholds exception text); `scaffold_block` gains two optional result fields; bridge marker is a context variable in `_context.py`; port-type warning runs the provisioned hook template's scanner via the provisioning loader (template unmodified); Windows `run_command` uses `asyncio.create_subprocess_shell` (CreateProcess quoting), POSIX `/bin/sh -c`; command env = desktop Python terminal env + `SCISTUDIO_PROJECT_DIR` + `PYTHONIOENCODING=utf-8` (user value respected), strips `SCISTUDIO_ENGINE_IPC_TOKEN`; extra `list_commands` tool; rename/move merged as `move_path`; CLI denial = hook pattern per shell segment + Windows paths/`.exe` + `python -m scistudio` | Audits AU3/AU4 assess them | N/A |
| 2026-09-10 | A2 | Resolved spec-silent points in PR #2284 and wrote them into the spec: second launch passes only an explicit mode flag or remembered choice; desktop→external-AI switches in place on the same backend; last window closed in external-AI mode quits only once the service is stopped/crashed/failed; relaunch stops and waits up to 8 s then restarts in the running mode without the picker; external-AI known-good vouching; picker runs before the mandatory-update check; address is the bound `127.0.0.1:<port>`; stop with a desktop window attached asks for confirmation; CHANGELOG recorded N/A (outside write set). Five-scenario fake-Electron harness left uncommitted | Recorded for owner review; audits AU1/AU2 assess the choices and whether the harness scenarios need committed tests | Owner decided 2026-09-11: the new launch mode needs a CHANGELOG entry — bundled into A2's audit-fix round (`CHANGELOG.md` added to its write set, gate-amended first) |

## 11. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux
      evidence when needed, commit, and PR evidence.
- [ ] PR closes every issue fixed by the dispatch.
- [ ] CI passed.
- [ ] Checklist final state matches PR and gate record.
