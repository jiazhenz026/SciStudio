---
title: "ADR-055 Spec 2-3 Dispatch Prompts"
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

# ADR-055 Spec 2-3 Dispatch Prompts

Filled from `docs/ai-developer/templates/agent-dispatch-prompt-template.md`.
Checklist: `docs/planning/adr-055-spec2-3-checklist.md`.

---

## A1 — Spec 2: Agent Context, Workspace Access, And Managed Execution

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-055 Spec 2 (agent context, workspace tools, managed execution) as amended by the owner decisions in issue #2279, as a final PR to main.
- Task kind: feature
- Persona: implementer
- Issue: #2279
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2279
- Umbrella PR: see checklist `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-055-spec2-3
- Agent branch: feat/2279-agent-context-workspace — STACKED on feat/2271-webmcp-bridge (PR #2275, open). Record `--base-ref feat/2271-webmcp-bridge` at init; pass `--base origin/feat/2271-webmcp-bridge` to check/finalize. Never measure against origin/main while stacked.
- Agent worktree: C:/Users/jiazh/workspace/SciStudio/.worktrees/feat-2279-agent-context-workspace (already created at e817f9b82)
- Gate record: .workflow/records/2279-feat-2279-agent-context-workspace.json (init creates it)
- Checklist: docs/planning/adr-055-spec2-3-checklist.md (on the umbrella branch; the manager maintains it — you do NOT edit it)

## Required Rules

Read and follow:

- Issue #2279 — its "Owner decisions" section OVERRIDES the spec wherever they differ.
- The spec `docs/specs/adr-055-agent-context-workspace.md` (FR-001..FR-012, §4.3 sequence, §4.4 verification) and ADR-055 `docs/adr/ADR-055.md` §5 and §9.2 (the demo's robustness findings are requirements).
- AGENTS.md, docs/ai-developer/rules.md, docs/ai-developer/specific_rules/gated-workflow.md, docs/ai-developer/specific_rules/new-feature.md, docs/ai-developer/personas/implementer.md

## Environment Notes (Windows, Git Bash)

- Python: `PYTHONPATH=src /c/Users/jiazh/workspace/SciStudio/.venv/Scripts/python -m ...` from your worktree. NEVER `pip install -e .`.
- Put `cd /c/Users/jiazh/workspace/SciStudio/.worktrees/feat-2279-agent-context-workspace && ` in front of EVERY shell command that touches git or gate state, and run `git branch --show-current` before any `git add`/`commit`. The shell cwd does not reliably persist.
- `git add -A` before every commit (pre-commit's stash path breaks on Windows otherwise).
- Gate runtime id: `claude-code:claude-opus-5`.
- Other agents and the owner run processes on this machine. Never kill a process you did not start; attribute by CommandLine + parent + creation time before touching any process or port.
- The demo at `.scratch-design/webmcp-recovery/scistudio-web-demo` is a READ-ONLY reference (see `src/scistudio/api/routes/webmcp.py` there for its `write_file`/`read_file`/`run_bash`/`import_data`). Never modify, commit, or push to it.

## Architecture Constraints You Must Respect

- import-linter forbids `scistudio.ai` -> `scistudio.api` (pyproject.toml "AI must not depend on api"). MCP tools reach the runtime through the structural `MCPContext` Protocol in `src/scistudio/ai/agent/mcp/_context.py` (`get_context()`, `getattr(ctx, "event_bus", None)` pattern as in `_reload.py` / `tools_workflow/write.py`). The shared write helper extracted from `api/routes/projects.py` (atomic write + FILE_CHANGED emission + block reload) MUST be reachable from both the HTTP route and the tools WITHOUT an ai->api import and WITHOUT adding an import-linter exception: expose it through the context (extend the Protocol) and/or place pure logic in a layer both may import. If neither works, stop and report.
- New tools are ordinary `@mcp.tool` registrations tagged `audience:external` (constant `AUDIENCE_EXTERNAL_TAG` from Spec 1 in `ai/agent/mcp/server.py` / `__init__.py`), with `read`/`write` tags matching mutation (Spec 1's project binding derives `mutation` from these tags). No router-internal tools.
- `run_command` processes register in the app's `ProcessRegistry` (`app.state.registry`) so backend shutdown `terminate_all` covers them; spawn like `LocalRunner._spawn_worker` (`asyncio.create_subprocess_exec`, platform process-group creation). Never `subprocess.run` on the event loop.
- Logging: operation identifiers and outcomes only; never file contents, command bodies, or full arguments (FR-012).

## Scope

You own only:

- src/scistudio/ai/agent/mcp/tools_qa.py (get_agent_context)
- src/scistudio/ai/agent/mcp/tools_workspace.py (create: inspect + author tools)
- src/scistudio/ai/agent/mcp/tools_execution.py (create: run_command + managed job status/cancel tools)
- src/scistudio/ai/agent/mcp/__init__.py (register new modules)
- src/scistudio/ai/agent/mcp/_context.py (Protocol extension only)
- src/scistudio/ai/agent/mcp/tools_workflow/read.py (list_blocks records "called" for the backend lifetime)
- src/scistudio/ai/agent/mcp/tools_workflow/write.py (run_workflow: additive poll-status hint field only)
- src/scistudio/ai/agent/mcp/tools_authoring.py (scaffold_block: list_blocks-first check when invoked through the bridge)
- src/scistudio/api/routes/projects.py (use the extracted shared write helper; optional expected state_version; route behavior unchanged)
- src/scistudio/api/runtime/** — only what is needed to expose the shared write helper / ProcessRegistry to the MCP context (gate_record amend --include each file BEFORE editing)
- src/scistudio/engine/runners/process_handle.py (registry accessor, only if needed)
- tests/ai/test_mcp_agent_context.py (create), tests/ai/test_mcp_workspace_tools.py (create), tests/ai/test_mcp_execution_tools.py (create), tests/api/test_projects.py (modify), plus the existing test file covering run_workflow / scaffold_block if you change them (amend first)
- docs/specs/adr-055-agent-context-workspace.md (update to the #2279 decisions; move implemented files from planned_governs to governs)
- docs/specs/adr-055-lab-deployment.md (ADD the transfer requirements removed from Spec 2: user-picked upload reusing POST /api/data/upload, streaming download endpoint authenticated by the Spec 4 session cookie, inline caps, TransferRecord; lab-only)
- .workflow/records/** (your own ledger), .workflow/local/** (never commit)

Conditional (amend BEFORE editing, keep minimal, note in your report):

- src/scistudio/api/routes/webmcp.py — only if the bridge must mark "called through the bridge" for the scaffold_block check (e.g. a context variable set around dispatch). This file belongs to open PR #2275; keep the change to a few lines.
- docs/adr/ADR-055.md — frontmatter `governs`/`tests` lists only, and only if full_audit requires it.

You must not touch:

- frontend/**, desktop/**
- docs/ai-developer/** (governance surface)
- src/scistudio/api/routes/data.py, upload staging in src/scistudio/api/runtime/_workflows.py (transfer moved to Spec 4)
- src/scistudio/agent_provisioning/templates/** (provisioned standalone hook scripts; read them for the rules, do not modify them)
- src/scistudio/engine/runners/local.py and worker cleanup behavior (#2281)
- src/scistudio/core/** (protected)
- .scratch-design/**

If you need any other out-of-scope path, stop and report back.

## Coordination

- You are not alone in this codebase. Work only on your branch and worktree. Do not revert or overwrite other agents' work. Agent A2 (Spec 3) works in desktop/**; your write sets do not overlap.
- If origin/feat/2271-webmcp-bridge moves (review fixes on PR #2275), merge it into your branch (do not rebase published history) and continue.
- DO NOT open a PR. While your base is feat/2271-webmcp-bridge a PR would not run ci.yml. When implementation is complete, commit, push your branch (`git push -u origin feat/2279-agent-context-workspace`), and report. The manager schedules the rebase onto main and the PR after #2275 merges.
- MUST NOT merge any PR.

## TODO And Deferral Rule

Deferred work must be tracked in the repo: `TODO(#NNN): <reason>` citing an issue/ADR/spec/follow-up. Known deferred items: transfer -> Spec 4 spec text (you move it); worker orphan cleanup -> #2281. Do not leave any other hidden "later" work; if something is genuinely out of scope, stop and report.

## Work To Do

1. T-001: extract the shared write helper from api/routes/projects.py (atomic write, FILE_CHANGED emission, post-save block reload) per the architecture constraint above; route + helper parity tests; add the optional expected `state_version` conflict check (route default unchanged).
2. T-002: `get_agent_context` in tools_qa.py over the real provisioned assets (CLAUDE.md/AGENTS.md, `.scistudio/agent-reference/*`, skills under `.claude/skills` and `.agents/skills`, hooks under `.claude/hooks`, project `docs/`), each index entry naming its actual retrieval path (existing doc tools for `docs/`, workspace read for the rest); accurate diagnostics for missing asset classes; hook guidance states where hooks execute (never claims the host ran them) and that the server enforces the parity rules below; explicit absent-project response.
3. T-003: tools_workspace.py
   - Inspect (list / metadata / search / ranged read): absolute paths accepted, anything the backend OS user can read; project-relative paths resolve against the active project; reads bounded WHILE streaming with an accurate truncation marker carrying total size; binary detection with a declared refusal/fallback.
   - Author (create / write / patch / rename / move / delete): project-confined; server-side blacklist rejecting any mutation whose source or target is `workflows/*.yaml|*.yml` (point to write_workflow / update_block_config) or under `data/` (point to run_workflow); every write goes through the shared helper (UI sync + block reload); explicit conflict results.
   - Hook parity in results: (a) writing `blocks/*.py` returns an explanatory error result until `list_blocks` has been called at least once in this backend lifetime (state resets on restart; list_blocks marks it from any transport); the same check applies to `scaffold_block` when invoked through the bridge, without changing local-transport behavior; (b) after a write to `blocks/*.py`, scan InputPort/OutputPort constructors — generic `DataObject` or empty `accepted_types` adds a non-blocking warning to the write result (mirror `hook_enforce_concrete_port_types.py` logic; reuse rather than duplicate if you can do so without modifying the template).
4. T-004: tools_execution.py — `run_command`: explicit absent-project error; cwd = project; environment = bundled interpreter + existing user dependency locations + `SCISTUDIO_PROJECT_DIR` (follow the existing worker env construction / `desktop/paths.py` user-python helpers) so pip-install-then-import resolves the same runtime; bounded incremental output capture with truncation flags; managed job lifecycle: the originating request ending does not kill the job; separate status and cancel tools; process-tree cancellation; in-memory status (exit state, bounded output tail) cleared on restart. Reject commands invoking the `scistudio` CLI (same pattern as `hook_deny_scistudio_cli.py`) with a result naming the MCP alternatives.
5. T-005: run_workflow gains an additive hint telling the agent to poll get_run_status until terminal (no existing field changes).
6. T-006: spec text updates (Spec 2 amended to the decisions; Spec 4 gains transfer), bounded logging, audience tags verified in both catalogues.

## Required Tests And Checks

- Registry-level tests (no browser) for every new tool and every acceptance scenario that survives the #2279 decisions: bounded reads on fixtures >= 4x the cap (assert no full materialization), traversal/blacklist rejections (workflows yaml, data/, rename/move into or out of data/), conflict rejection, FILE_CHANGED emitted via the shared helper, get_agent_context real-path index + missing-asset diagnostics + absent-project response, list_blocks-first rule (incl. backend-lifetime scope and scaffold_block via bridge), port-type warning, scistudio CLI denial, run_workflow hint present, run_command: absent project, responsiveness (sibling request completes while a long command runs), process-tree cancellation with zero registry residue, request-abort does not kill the job, pip-install-then-import environment parity (use a tiny local wheel or a stdlib-only check if network is unavailable — never skip silently; if impossible, stop and report).
- Local non-ASCII and Windows path cases where relevant (this machine is Windows; CI is Ubuntu).
- Gate flow (all from your worktree, PYTHONPATH=src, venv python):
  1. `gate_record init --task-kind feature --persona implementer --runtime claude-code:claude-opus-5 --branch feat/2279-agent-context-workspace --base-ref feat/2271-webmcp-bridge --issue 2279 --owner-directive "<summary incl. #2279 decisions>" --include <each write-set path>`
  2. `gate_record plan` with docs/test declarations
  3. implement; `gate_record amend --reason ... --include <path>` BEFORE any scope addition
  4. `gate_record check --base origin/feat/2271-webmcp-bridge --head HEAD`, then `--mode pre-pr --pr-body-file .workflow/local/pr-body.md` (body must contain `Closes #2279` and `Gate record: <path>`)
  5. commit (Conventional Commits; trailers `Gate-Record:`, `Task-Kind: feature`, `Issue: #2279`, `Assisted-by: claude-code:claude-opus-5`), push the branch. Do NOT run pre-PR finalize and do NOT open a PR — the manager does that after the rebase onto main.
- Sentrux MCP is unavailable in this runtime; record that when asked.

## Output Required

- Changed file paths (and every gate amend you made, with reason).
- Tests/checks run and results (commands + pass/fail counts).
- Pushed branch head sha and gate record path.
- Where the shared write helper lives and how the tools reach it (layering).
- Any blocker, scope issue, or spec ambiguity you resolved (state the choice).

## Stop Conditions

Stop and report back if: you need an out-of-scope file; the task conflicts with AGENTS.md/ADR/spec/issue decisions/gate record; the layering constraint cannot be met; local checks fail for unclear reasons; you cannot add required tests.
```

---

## A2 — Spec 3: Local Startup Modes And The Background Runtime

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-055 Spec 3 (local startup modes and background runtime) as amended by the owner decisions in issue #2280, as a final PR to main.
- Task kind: feature
- Persona: implementer
- Issue: #2280
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2280
- Umbrella PR: see checklist `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-055-spec2-3
- Agent branch: feat/2280-local-background-runtime (base: origin/main)
- Agent worktree: C:/Users/jiazh/workspace/SciStudio/.worktrees/feat-2280-local-background-runtime (already created at f87c6ad40)
- Gate record: .workflow/records/2280-feat-2280-local-background-runtime.json (init creates it)
- Checklist: docs/planning/adr-055-spec2-3-checklist.md (manager maintains — you do NOT edit it)

## Required Rules

Read and follow:

- Issue #2280 — its "Owner decisions" section OVERRIDES the spec wherever they differ.
- The spec `docs/specs/adr-055-local-background-runtime.md` and ADR-055 `docs/adr/ADR-055.md` §7.
- docs/ai-developer/release-runbook.md (read only — shell OTA rules; if your change would require editing it, stop and report).
- AGENTS.md, docs/ai-developer/rules.md, docs/ai-developer/specific_rules/gated-workflow.md, docs/ai-developer/specific_rules/new-feature.md, docs/ai-developer/personas/implementer.md

## Environment Notes (Windows, Git Bash)

- Python: `PYTHONPATH=src /c/Users/jiazh/workspace/SciStudio/.venv/Scripts/python -m ...` from your worktree. NEVER `pip install -e .`.
- Put `cd /c/Users/jiazh/workspace/SciStudio/.worktrees/feat-2280-local-background-runtime && ` in front of EVERY shell command that touches git or gate state, and run `git branch --show-current` before any `git add`/`commit`.
- `git add -A` before every commit.
- Gate runtime id: `claude-code:claude-opus-5`.
- Desktop: `cd desktop && npm ci` in your worktree before `npm test` (`node --test test/*.test.js`).
- THE OWNER MAY BE USING A RUNNING SCISTUDIO DESKTOP APP ON THIS MACHINE. Do not launch the full Electron app, and never kill a process you did not start (attribute by CommandLine + parent + creation time first). The app holds a single-instance lock, so a launch could also collide with the owner's instance. If a live GUI check is needed, stop and report — the manager runs live launches.

## Owner Decisions (from #2280) — summary

1. Every launch, the splash offers "Desktop" / "External AI" with a "don't ask again" option; the remembered choice stays changeable later (menu and tray). Desktop gives today's flow unchanged.
2. Tray icon only in external-AI (headless) mode. Menu: open connection window, copy address, service status, open in desktop mode, stop and quit. macOS: template (monochrome) image; keep a strong reference to the Tray. Linux without a tray host: relaunch -> `second-instance` -> connection window.
3. Backend stops with Electron: keep the POSIX parent watchdog unchanged; DROP the spec's `--no-parent-watchdog` opt-out (FR-009), instance adoption/re-adoption, and `runtime-port.js` discovery changes. On Windows, VERIFY that Electron's non-detached backend child dies when the Electron process is force-killed (Node/libuv is believed to place non-detached children in a kill-on-close job object). Verify with a Node-level repro (a node script spawns a long-lived python child the way `desktop/main.js` does — no `detached` — then force-kill the node process with `taskkill /F /PID` and check the child) instead of launching the app. If the child survives, adding a Windows backstop (e.g. extending `src/scistudio/desktop/parent_watchdog.py` + its gating in `src/scistudio/cli/main.py` with a parent-alive + create-time identity check) is IN scope — amend first, add tests. Grandchild/worker cleanup is NOT (#2281).
4. One backend per machine; `second-instance` reveals the connection window, or attaches a desktop window to the running backend.
5. OTA stop-then-relaunch includes the background instance; the relaunch honors the mode choice.

## Scope

You own only:

- desktop/main.js (mode branch at startup; mode- and platform-aware `window-all-closed`; `second-instance` routing; OTA relaunch honoring mode)
- desktop/background-mode.js (create: pure mode/lifetime/routing decision logic + persisted mode preference, following the `runtime-port.js` pure-function precedent)
- desktop/menu.js (entries: switch mode / ask again at next launch, reopen connection window)
- desktop/splash.html (mode picker UI)
- desktop/preload.js (only if the new windows need IPC; or create a dedicated preload file)
- new connection-window HTML (and preload if separate) under desktop/
- desktop/assets/ new tray image files (derive from `desktop/assets/icon.png`; macOS `*Template.png` + `@2x`)
- desktop/package.json — `build.files` ONLY (every new shell file must be listed)
- scripts/ota_publish.py — `SHELL_FILES` ONLY (every new shell file must be listed; it must match `build.files` minus bootstrap.js/package.json)
- desktop/test/background-mode.test.js (create), desktop/test/bootstrap.test.js, desktop/test/menu.test.js, tests/scripts/test_ota_publish.py (list parity)
- docs/specs/adr-055-local-background-runtime.md (update to the #2280 decisions; move implemented files into governs)
- .workflow/records/** (own ledger), .workflow/local/** (never commit)

Conditional (only if the Windows verification in decision 3 fails; amend first):

- src/scistudio/desktop/parent_watchdog.py, src/scistudio/cli/main.py (gating only), tests/desktop/** or tests/cli/** for them

You must not touch:

- desktop/runtime-port.js, desktop/bootstrap.js, desktop/ota.js logic (read only)
- frontend/**, src/scistudio/** (except the conditional above), docs/ai-developer/** (incl. the release runbook)
- src/scistudio/engine/runners/** (worker cleanup is #2281)

If you need any other out-of-scope path, stop and report back.

## Shell OTA Constraint (critical)

The shell is hot-updated (#2097): `scripts/ota_publish.py` ships exactly `SHELL_FILES` inside a patch, and the installed asar ships `desktop/package.json` `build.files`. A new file that main.js `require`s but that is missing from either list crashes patched or installed launches. `tests/scripts/test_ota_publish.py` has a parity test between the two lists — extend it, keep it green, and add the new files to `desktop/test/bootstrap.test.js`'s baseline-shell assertion where appropriate. HTML files referencing assets by relative path must ship those assets too (see the `assets/icon.png` note in SHELL_FILES).

## Coordination

- You are not alone in this codebase. Work only on your branch and worktree. Agent A1 (Spec 2) works in src/scistudio/ai/** and api/**; your write sets do not overlap.
- Your PR targets `main` directly (manager-assigned final PR).
- MUST NOT merge any PR.

## TODO And Deferral Rule

Deferred work must be tracked in the repo: `TODO(#NNN): <reason>` citing an issue/ADR/spec/follow-up. Known deferred items: worker/grandchild cleanup -> #2281. macOS/Linux installed-build verification is a manager/owner e2e step, not a code deferral. No other hidden "later" work; stop and report instead.

## Work To Do

1. T-001: `background-mode.js` pure logic + unit tests: mode resolution (picker vs remembered), preference persistence shape, `window-all-closed` policy per mode/platform, `second-instance` routing (same-mode reveal vs attach desktop window), relaunch mode carry-over.
2. T-002: Windows backend-lifetime verification (decision 3); backstop only if it fails.
3. T-003: splash mode picker (every launch; "don't ask again"); menu entries to switch mode / re-enable the picker.
4. T-004: external-AI mode in main.js: existing `startRuntimeWithRollback` + readiness chain, no main window; tray + connection window (address shown only after readiness, copyable, status re-validated on focus, stop -> existing `stopRuntime` with visible stopped state, restart via the readiness chain, crash surfaced with restart action); "open in desktop mode" attaches a main window to the running backend.
5. T-005: OTA: the update chain stops the background instance before relaunch and the relaunch honors the mode.
6. T-006: shell file lists parity; spec text update; docs check (record docs N/A for any user-doc class not applicable).

## Required Tests And Checks

- `desktop` `npm test` (node --test) green including the new background-mode tests and updated bootstrap/menu tests.
- `tests/scripts/test_ota_publish.py` green with the list parity.
- Record the Windows verification method and result (script + observed outcome) in your report and in the PR body.
- Gate flow (from your worktree):
  1. `gate_record init --task-kind feature --persona implementer --runtime claude-code:claude-opus-5 --branch feat/2280-local-background-runtime --issue 2280 --owner-directive "<summary incl. #2280 decisions>" --include <each write-set path>`
  2. `gate_record plan` with docs/test declarations
  3. implement; `gate_record amend` before any scope addition
  4. `gate_record check --base origin/main --head HEAD`, then `--mode pre-pr --pr-body-file .workflow/local/pr-body.md` (body: `Closes #2280`, `Gate record: <path>`, Windows verification evidence, a "Live launch verification pending (manager/owner)" note)
  5. `gate_record finalize --base origin/main --head HEAD --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#2280"`
  6. push; `python scripts/scistudio_pr_create.py --title "feat(#2280): ..." --body "$(cat .workflow/local/pr-body.md)"`
  7. `gate_record finalize --commit <sha> --pr <url> --pr-body-file .workflow/local/pr-body.md` (use `--record <path>` if discovery stops after finalize); commit + push the ledger update
- Commits: Conventional Commits; trailers `Gate-Record:`, `Task-Kind: feature`, `Issue: #2280`, `Assisted-by: claude-code:claude-opus-5`.
- Sentrux MCP is unavailable in this runtime; record that when asked.

## Output Required

- Changed file paths (and gate amends with reasons).
- Tests/checks run and results.
- Windows verification method + result, and whether the backstop was needed.
- PR number/URL, head sha, gate record path, CI status.
- Any blocker, scope issue, or spec ambiguity you resolved (state the choice).

## Stop Conditions

Stop and report back if: you need an out-of-scope file; a live GUI launch is needed; the task conflicts with AGENTS.md/ADR/spec/issue decisions/gate record; local checks fail for unclear reasons; you cannot add required tests.
```

---

## AU1 — Audit PR #2284 (Spec 3), with-context

```markdown
[DISPATCH-TEMPLATE-V1: audit-with-context]

## Task Identity

- Repository: SciStudio (C:/Users/jiazh/workspace/SciStudio)
- Persona: audit_reviewer
- Audit mode: with-context
- Task kind: maintenance (your own gate ledger)
- Issue: #2280 (https://github.com/jiazhenz026/SciStudio/issues/2280)
- Owner request: Verify the ADR-055 Spec 3 implementation PR before merge.
- Umbrella PR: #2283 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-055-spec2-3
- Audit branch: audit/2280-spec3-with-context (base: origin/feat/2280-local-background-runtime) — ALREADY CREATED
- Audit worktree: C:/Users/jiazh/workspace/SciStudio/.worktrees/audit-2280-spec3-wc — ALREADY CREATED at 5c0ddefac
- Gate record: init your own (task_kind=maintenance, persona=audit_reviewer, runtime `claude-code:claude-opus-5`, branch audit/2280-spec3-with-context, --base-ref feat/2280-local-background-runtime, --issue 2280, --include docs/audit/2026-09-10-adr-055-spec3-with-context.md)
- Checklist: docs/planning/adr-055-spec2-3-checklist.md on origin/track/adr-055-spec2-3 (read it with `git show origin/track/adr-055-spec2-3:docs/planning/adr-055-spec2-3-checklist.md`; do NOT edit it)
- PR to audit: #2284 (feat/2280-local-background-runtime @ 5c0ddefac)
- Audit report path: docs/audit/2026-09-10-adr-055-spec3-with-context.md

## Required Reading

- Issue #2280 (its "Owner decisions" override the spec), spec `docs/specs/adr-055-local-background-runtime.md` (as rewritten by the PR), ADR-055 §7 and §11 (Local launch row), PR #2284 description + diff + CI (`gh pr view 2284`, `gh pr diff 2284`, `gh pr checks 2284`), the checklist (sections 8 and 10).
- docs/ai-developer/release-runbook.md (shell OTA rules).
- AGENTS.md, docs/ai-developer/rules.md, docs/ai-developer/specific_rules/agent-dispatch.md, docs/ai-developer/personas/audit-reviewer.md

## Audit Goal

Verify the claimed work against the issue decisions, spec, code, tests, gate evidence, and CI. Report findings first. Severity: P1 blocks merge or breaks contract; P2 should fix before completion; P3 improvement/follow-up.

Claims to verify (from the implementer's report):
- Owner decisions 1-5 of #2280 are all implemented: picker on every launch with "don't ask again" and a way to change it later; tray only in external-AI mode with the five menu items; backend stops with Electron (POSIX watchdog untouched, no opt-out flag, no adoption, runtime-port.js untouched); one backend per machine via second-instance; OTA relaunch includes the background instance and honors the mode.
- Windows lifetime claim: a non-detached child dies when its Node/Electron parent is `taskkill /F`-ed. Reproduce it yourself with your own small Node script (no Electron GUI).
- Shell OTA safety: every file main.js requires and every asset an HTML file references is in both `build.files` and `SHELL_FILES`; the parity test really enforces this.
- External-AI known-good vouching (`maybeVouchForShellInBackground`): cannot fire on readiness alone; cannot fire before the connection window's preload bridge is ready; a shell fault still blocks it.
- The implementer's spec-silent choices (checklist drift log row for A2): assess each for correctness and consistency with ADR-055 §7 and the owner decisions.
- Decision logic placement: is the mode/lifetime/routing logic in `background-mode.js` (unit-tested) rather than untested branches in `main.js` (+760 lines)? The implementer drove five launch scenarios through an UNCOMMITTED fake-Electron harness — determine which of those behaviors have no committed test coverage.
- Connection window security: sandbox, contextIsolation, the preload/IPC surface, what the renderer can make the main process do.
- CHANGELOG: the implementer recorded N/A; state whether repository practice for user-visible features calls for an entry (evidence from `git log -- CHANGELOG.md`).

Audit surfaces: the PR #2284 diff, ledger .workflow/records/2280-feat-2280-local-background-runtime.json.

Do not write feature code. Do NOT launch the SciStudio Electron app (the owner may be using one; it also holds a single-instance lock). Never kill a process you did not start. MUST write the audit report to the path above, commit it on your audit branch (trailers: Gate-Record, Task-Kind: maintenance, Issue: #2280, Assisted-by: claude-code:claude-opus-5, plus `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`), and push (`git push -u origin audit/2280-spec3-with-context`). Do NOT open a PR. The manager integrates the report into the PR evidence path.

## Checks

Run or verify (PYTHONPATH=src /c/Users/jiazh/workspace/SciStudio/.venv/Scripts/python for Python; from your worktree; `cd desktop && npm ci` before desktop tests):
- desktop `npm test`; `pytest tests/scripts/test_ota_publish.py`
- `gate_record check --mode local --base origin/feat/2280-local-background-runtime --head HEAD` after committing your report
- Sentrux: unavailable in this runtime — record N/A.
- Frontend/browser smoke: N/A (no frontend change); live Electron launch: reserved for the manager/owner.

## Output Required

Report path; commit sha containing the report; findings by severity; checklist/scope drift if any; missing tests/docs/gate evidence if any; CI status; recommendation: pass / pass-with-fixes / block.

## Stop Conditions

Stop and report if: you need to change implementation code; required evidence is unavailable; the audit scope conflicts with AGENTS.md/ADR/spec/gate record.
```

---

## AU2 — Independent audit of the Spec 3 surfaces, no-context

```markdown
[DISPATCH-TEMPLATE-V1: audit-no-context]

## Task Identity

- Repository: SciStudio (C:/Users/jiazh/workspace/SciStudio)
- Persona: audit_reviewer
- Audit mode: no-context
- Audit branch: audit/2280-spec3-no-context — ALREADY CREATED
- Audit worktree: C:/Users/jiazh/workspace/SciStudio/.worktrees/audit-2280-spec3-nc — ALREADY CREATED
- Allowed audit surfaces:
  - desktop/** (main.js, background-mode.js, menu.js, splash.html, connection.html, connection-preload.js, preload.js, bootstrap.js, ota.js, runtime-port.js, package.json, assets/, test/**)
  - scripts/ota_publish.py, tests/scripts/test_ota_publish.py
  - src/scistudio/desktop/parent_watchdog.py, src/scistudio/cli/main.py (the `gui` command)
  - docs/specs/adr-055-local-background-runtime.md, docs/adr/ADR-055.md, docs/ai-developer/release-runbook.md
- Audit report path: docs/audit/2026-09-10-adr-055-spec3-no-context.md

## Context Limits

You must not read or use:

- Any GitHub issue or PR (no `gh issue`, no `gh pr`).
- Anything under docs/planning/** (manager checklists, dispatch prompts).
- Commit messages: do not run `git log`, `git show <commit>` with messages, or `git blame`. Read changes with `git diff origin/main...HEAD` and by reading files.
- Gate ledgers under .workflow/records/ other than the one you create.
- Chat summaries or manager summaries of what changed.

You may read only repository docs, code, tests, committed generated facts or audit outputs, and output from commands you run yourself.

## Required Reading

- AGENTS.md, docs/ai-developer/rules.md, docs/ai-developer/personas/audit-reviewer.md
- Governing ADRs, specs, and docs discovered from the allowed surfaces.

## Audit Goal

Independently check whether docs, code, tests, and declared contracts agree. Do not assume what anyone intended to change.

Look for:

- Spec/ADR statements about launch modes, the tray, the connection window, stop/restart, second launch, window-close behavior per platform, OTA relaunch, and backend lifetime that the code does not implement, or code behavior the spec does not describe.
- Tests whose assertions are weaker than the behavior they claim to cover: source-text/regex assertions standing in for behavior, fakes that never reach a failure path, scenarios that are described but never exercised.
- Lifecycle defects: a second backend process, a backend that outlives the app, an app that stays invisibly resident, stop that leaves the UI lying about state, crash handling, relaunch races.
- Shell hot-update packaging: every module required by the shell and every asset referenced by its HTML is shipped by both the installer file list and the OTA shell file list.
- Connection window / preload security: sandbox, contextIsolation, the exposed IPC surface.
- For any suspected failure, reproduce it on origin/main (e.g. in a detached checkout under your scratch space) to decide whether it is new or pre-existing.

## Coordination

- Work only on your audit branch and worktree. MUST NOT use `pip install -e .`. MUST NOT merge any PR. MUST NOT edit implementation files or any checklist.
- Do NOT launch the SciStudio Electron app (someone may be using one on this machine; it holds a single-instance lock). Never kill a process you did not start. Node-level repro scripts are fine.
- MUST write the audit report to the path above, commit it on your audit branch (trailers: Gate-Record, Task-Kind: maintenance, Assisted-by: claude-code:claude-opus-5, plus `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`), and push (`git push -u origin audit/2280-spec3-no-context`). Do NOT open a PR.

## Checks

Run or verify (PYTHONPATH=src /c/Users/jiazh/workspace/SciStudio/.venv/Scripts/python for Python; `cd desktop && npm ci` before desktop tests):
- desktop `npm test`; `pytest tests/scripts/test_ota_publish.py`
- `gate_record init --task-kind maintenance --persona audit_reviewer --runtime claude-code:claude-opus-5 --branch audit/2280-spec3-no-context --base-ref feat/2280-local-background-runtime --include docs/audit/2026-09-10-adr-055-spec3-no-context.md --owner-directive "independent no-context audit of the desktop launch-mode surfaces"`, then after committing the report: `gate_record check --mode local --base origin/feat/2280-local-background-runtime --head HEAD` (record any issue-linkage gap as a known gap; do not look up issues)
- Sentrux: unavailable in this runtime — record N/A.

## Output Required

- Audit report path and the commit sha containing it.
- Findings ordered by severity (P1 blocks merge or breaks contract; P2 should fix; P3 follow-up), each with evidence from docs, code, tests, or tool output.
- No statement about anyone's intent unless it is visible in repository docs.
- Recommendation: pass, pass-with-fixes, or block.

## Stop Conditions

Stop and report back if: you are asked to read issue/checklist/PR context; the audit requires hidden context; you need to edit implementation code.
```

---

## A2-fix1 — Spec 3 audit fix round (sent to A2 via SendMessage)

```markdown
[DISPATCH-TEMPLATE-V1: fix]

Task identity, rules, environment notes, coordination and gate flow are unchanged from A2 (branch feat/2280-local-background-runtime, worktree .worktrees/feat-2280-local-background-runtime, issue #2280, PR #2284). This round fixes the two Spec 3 audits.

1. Integrate the audit evidence first: `git cherry-pick b4312fdb0 c67327a56 da013b31be caf5865e5` (AU1 with-context report + its ledger, AU2 no-context report + its ledger), same pattern as the Spec 0/1 round. Then read both reports in full:
   docs/audit/2026-09-10-adr-055-spec3-with-context.md, docs/audit/2026-09-10-adr-055-spec3-no-context.md.
2. Fix (each with a test that fails before the fix):
   - AU1 P2-1: quitting at the launch-mode picker (or closing the splash there) leaves the loader's crash-loop marker set, so a working patched shell is refused on every later launch. Invariant: a shell that rendered the picker and handled the user's choice or close is not a shell fault; a shell that fails before that still is. Prove it with the loader's own marker functions in desktop/ota.js (read-only; do not change ota.js or bootstrap.js).
   - AU1 P2-2 / AU2 P2-2 / Codex 3985756076: `stopRuntime` SIGKILL escalation never fires (`child.killed` is true once SIGTERM is sent). Escalate on actual liveness (exitCode/signalCode), and make every relaunch path wait for real backend exit. Pre-existing on main, in scope because Spec 3 depends on it.
   - AU1 P2-4: behavioural tests for the main.js orchestration. Commit the fake-Electron harness scenarios as tests, and make the five surviving mutations from AU1 fail them: vouching on readiness alone; setting the bridge-ready flag early; removing the connection-window IPC sender check; not awaiting backend exit before relaunch; external-AI mode creating the main window. Re-run those mutations and report that each is now caught.
   - AU1 P2-5: CHANGELOG entry for the new launch mode (owner decision 2026-09-11). `gate_record amend --include CHANGELOG.md` first; follow the file's existing format.
   - P3s from both reports: fix every one that fits this PR. That includes the ones the owner hit live: "Stop and Quit" with a desktop window attached quits without confirmation (the owner ran into this). It also includes: restart is unresponsive for up to 30 s after a startup crash; `stopRuntimeAndWait` does not wait when a stop is in flight; `windowAllClosedAction` ignores `platform`; macOS reopen through `activate` in external-AI mode; the picker has no timeout if the splash fails to load; test enforcement for relative requires in ota.js/background-mode.js and assets referenced from HTML; the stale shell list in `docs/specs/desktop-shell-ota-hot-update.md` §6 (amend it in); spec frontmatter `feature_branch`/`tests`. For any P3 you do not fix, give a one-line rationale; the manager tracks it with the owner.
   - HOLD: AU1 P2-3 / AU2 P2-1 / Codex 3985756074, what happens when the backend stops or dies after every window is closed. This waits on an owner decision; the manager will send it. Do not change that behavior until then.
3. After fixing, reply on PR #2284 to both Codex review comments (3985756074: "held for owner decision" until the manager sends it; 3985756076: the fix commit). Use `gh api repos/jiazhenz026/SciStudio/pulls/2284/comments/<id>/replies -f body=...`.
4. Gate: amend before every new file; `gate_record check --record <ledger> --mode pre-pr --base origin/main --head HEAD --pr-body-file .workflow/local/pr-body.md`; commit (trailers as before); push; post-PR finalize with `--record`; confirm CI green. Still no Electron GUI launch (the manager runs live checks) and never kill a process you did not start. Run long commands in the foreground with output redirected to a log; do not background them.
5. Report: fix commits, test/mutation results, P3s fixed vs not fixed (with rationale), CI status.
```

---

## A1-fix1 — Spec 2 audit fix round (sent to A1 via SendMessage)

```markdown
[DISPATCH-TEMPLATE-V1: fix]

Task identity, rules, environment notes, scope approvals and coordination are unchanged from A1 (branch feat/2279-agent-context-workspace stacked on feat/2271-webmcp-bridge, worktree .worktrees/feat-2279-agent-context-workspace, issue #2279). Still NO PR until the manager schedules the rebase onto main.

1. Integrate the audit evidence: `git cherry-pick 0517a0afb 755ffc39c` (AU3 with-context report + ledger). Read docs/audit/2026-09-11-adr-055-spec2-with-context.md in full. AU4 (no-context) is still running; the manager will send its findings as an addendum.
2. Fix, each with a test that fails before the fix (tests must run on CI's Ubuntu too — use symlinks there; junctions are Windows-only extras):
   - P1-1: `delete_path` / `move_path` act on the resolved target of a symlink/junction. They must act on the link itself (lstat semantics, never follow a link to delete or move its target), and the blacklist/confinement checks must evaluate the path actually mutated. Cover symlinks (POSIX) and junctions (Windows), file and directory links, links pointing inside `data/`/`workflows/` and outside the project.
   - P1-2: Windows `cancel_command` and backend shutdown miss descendants whose parent already exited. Make cancellation cover the whole job regardless of intermediate exits (the repo already has Windows Job Object support in src/scistudio/engine/runners/platform.py — prefer reusing it; amend any new file in first). Test: a command whose child spawns a long-lived grandchild and exits.
   - P2-1: inspect/patch paths (`get_file_info`, `read_file`, `patch_file` read step) must not advance the cached file version that suppresses FILE_CHANGED for external edits; only real writes through the shared helper may. Test the watcher emit condition after read-then-external-edit.
   - P2-2: a command whose process exited must be reported exited even while a background child holds the output pipes (bounded drain, then "exited, output may be incomplete" note). Test on the current interpreter.
   - P2-5: the missing tests above, plus a real HTTP request abort through the bridge that leaves the job running.
   - P3s: fix every one that fits (including: `get_agent_context` hook guidance overstating server enforcement; a block filename reaching INFO logs via the shared write path — FR-012; stale spec `feature_branch` / governed-file list). For any P3 not fixed, give a one-line rationale.
   - HOLD: AU3 P2-3 (refusals returned with `isError: false`) waits on an owner decision; the manager will send it.
3. Evidence (AU3 P2-4): your previous gate events covered an EMPTY diff (base = head = e817f9b82). Commit first, then run `gate_record check --base origin/feat/2271-webmcp-bridge --head HEAD` and the pre-PR check on the committed diff, and confirm the ledger's `observed_diff.changed_files` is non-zero and lists your files. Report the numbers.
4. Commit (trailers as before), push the branch, report: fix commits, test results, P3 fixed / not fixed with rationale, the evidence numbers from step 3. Run long commands in the foreground with output redirected to a log; do not background them.
```

---

## A3 — Owner-directed addition to PR #2275 (Spec 1): reject external-audience tools on the local socket

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: External-audience tools must not be callable over the local socket MCP transport (not only hidden from its catalogue); land it on PR #2275 before it merges (owner decision 2026-09-11, raised by the ADR-055 Spec 2 no-context audit P3-2).
- Task kind: feature (continuation of #2271)
- Persona: implementer
- Issue: #2271 (https://github.com/jiazhenz026/SciStudio/issues/2271)
- PR: #2275 (feat/2271-webmcp-bridge -> main, stacked on feat/2270-prefix-independence)
- Umbrella PR for this dispatch: #2283 `[DO NOT MERGE]` (track/adr-055-spec2-3)
- Agent branch: feat/2271-webmcp-bridge (existing)
- Agent worktree: C:/Users/jiazh/workspace/SciStudio/.worktrees/feat-2271-webmcp-bridge (existing, clean, at e817f9b82 = origin)
- Gate record: .workflow/records/2271-feat-2271-webmcp-bridge.json (already finalized; pass `--record <path>` to amend/check/finalize). Its base ref is feat/2270-prefix-independence; pass `--base origin/feat/2270-prefix-independence` to check/finalize.
- Checklist: docs/planning/adr-055-spec2-3-checklist.md on origin/track/adr-055-spec2-3 (manager maintains; do not edit)

## Required Rules

- AGENTS.md, docs/ai-developer/rules.md, docs/ai-developer/specific_rules/gated-workflow.md, docs/ai-developer/personas/implementer.md
- Spec `docs/specs/adr-055-webmcp-bridge.md` (FR-004, US6), `src/scistudio/ai/agent/mcp/server.py` (`AUDIENCE_EXTERNAL_TAG`, the socket handler's `tools/list` filter and `tools/call` dispatch around lines 368-401)

## Scope

You own only:
- src/scistudio/ai/agent/mcp/server.py — the local socket `tools/call` path only
- tests/ai/test_mcp_fastmcp.py — new test(s) for the rejection
- docs/specs/adr-055-webmcp-bridge.md — FR-004 / US6 text recording the owner decision
- your ledger (.workflow/records/2271-feat-2271-webmcp-bridge.json), .workflow/local/** (never commit)

You must not touch anything else (Spec 0 files, the WebMCP router, the frontend, any Spec 2 files, docs/ai-developer/**). If you need another file, stop and report.

## Work To Do

1. `gate_record amend --record <ledger> --reason "owner decision 2026-09-11: local socket rejects external-audience tools by name" --owner-directive "<that decision>"` before editing.
2. In the socket transport's `tools/call`, reject a tool carrying `AUDIENCE_EXTERNAL_TAG` with the same error shape the handler returns for an unknown tool, and a message saying the tool is available only through the WebMCP bridge. `mcp.call_tool` used directly (the bridge path) must be unaffected. Untagged tools keep working over the socket.
3. Tests: an external-tagged fixture tool is (a) absent from socket `tools/list` (existing) and (b) rejected by socket `tools/call`; an untagged tool still succeeds over the socket; the same external tool still dispatches through the bridge path.
4. Spec text: FR-004 / US6 say the local transport neither lists nor executes external-audience tools; record the owner decision and date.
5. `gate_record check --record <ledger> --mode pre-pr --base origin/feat/2270-prefix-independence --head HEAD --pr-body-file <PR #2275 body saved to .workflow/local/pr-body.md via gh pr view 2275 --json body>`; commit (Conventional Commit, trailers Gate-Record / Task-Kind: feature / Issue: #2271 / Assisted-by: claude-code:claude-opus-5 / Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>); push; post-PR finalize `--record <ledger> --commit <sha> --pr 2275 --pr-body-file .workflow/local/pr-body.md`; commit + push the ledger; confirm CI green on #2275.
6. Comment on PR #2275 summarizing the owner-directed addition (one short paragraph, link the commit).

## Coordination / Constraints

- You are not alone: A1 works on feat/2279-agent-context-workspace, which is stacked on your branch and will merge your change; do not touch that branch. Never kill a process you did not start. MUST NOT merge any PR. No deferrals. Run long commands in the foreground with output redirected to a log; do not background them.

## Output Required

Changed files, test results, commit shas, CI status on #2275, any blocker.

## Stop Conditions

Stop and report if you need an out-of-scope file, the ledger refuses the amend, or checks fail for unclear reasons.
```

---

## A1-fix2 — PR #2292 CI and Codex review fix round (sent to A1 via SendMessage)

```markdown
[DISPATCH-TEMPLATE-V1: fix]

Same identity/scope/coordination as A1. PR #2292 is open against main (stacked by content on #2275). Fix, each with a test where behavior changes:

1. Type Check: CI resolves fastmcp 4.0.3 / mcp 2.2.0 (main's `fastmcp<5`). `CallToolResult(structuredContent=..., isError=...)` at tools_workspace.py:278 is rejected by mcp 2.2. Make the error-result construction work on the versions CI installs (and keep working on fastmcp 3.x if the lower bound still allows it). Reproduce locally in a throwaway venv or with `uv pip install --target` in scratch space — never `pip install -e .`, never modify the shared .venv.
2. POSIX cancel / Codex P1 (tools_execution.py:353): cancellation must not reap the shell process asyncio owns (the supervisor then waits forever and the job stays `running`). Fix `test_http_request_abort_through_the_bridge_leaves_the_job_running` on 3.11.
3. Codex P1 (_file_writes.py:458): the expected-version check and the atomic replace must be one critical section — two writes carrying the same `expected_state_version` must not both succeed. Test with concurrent writers.
4. Codex P1 (tools_execution.py:786): on Windows, refuse the command (isError result, no process left running) when Job Object creation or assignment fails; consider a suspended start if feasible. Test the failure path with an injected failure.
5. Codex P2 (tools_workspace.py:919): check the search deadline / stop flag while scanning a file's contents; bound regex cost (e.g. per-file byte cap + timeout-aware iteration). Test with a slow/large file.
6. Test (3.11) collection errors in tests/architecture/test_packaging.py and tests/packaging/test_wheel_spa.py ("distutils already imported"): find the root cause on this branch (they pass on main and #2275). Likely an import-time side effect from a new module or test (e.g. something importing pip/setuptools/distutils in-process). Fix the cause; do not skip or reorder tests to hide it. Report the cause.
7. Deferral ratchet: reword the comment at tools_execution.py:256 (the word "later"), or cite a tracked issue if it is a real deferral.
8. CodeQL alerts #274-276 (py/path-injection, _file_writes.py:190/244/469): prefer a code fix that makes the containment check visible to CodeQL (resolve + verify containment before any filesystem call on that path). If a genuine false positive remains, stop and report — dismissal is the owner's decision.
9. Reply to each Codex comment on PR #2292 with the fix commit.

Gate: amend before new files; `gate_record check --record <ledger> --mode pre-pr --base origin/feat/2271-webmcp-bridge --head HEAD --pr-body-file .workflow/local/pr-body.md` on the COMMITTED diff; commit; push; post-PR finalize `--record ... --pr 2292`; commit + push; wait for CI. Expected remaining red: Verify Workflow Compliance until the owner applies `admin-approved:core-change`. Run long commands in the foreground with output redirected to a log. Report: fix commits, root cause of item 6, CodeQL outcome, CI state.
```

---

## A1b — Take over the interrupted A1-fix2 round and move PR #2292 onto main

```markdown
[DISPATCH-TEMPLATE-V1: fix]

## Task Identity

- Repository: SciStudio
- Owner request: finish the PR #2292 fix round (A1-fix2) and move the branch onto main now that PR #2275 has merged.
- Task kind: feature; Persona: implementer; Issue: #2279; PR: #2292 (-> main)
- Umbrella PR: #2283 `[DO NOT MERGE]`; Umbrella branch: track/adr-055-spec2-3
- Agent branch: feat/2279-agent-context-workspace (remote head f28dd2ffd)
- Agent worktree: C:/Users/jiazh/workspace/SciStudio/.worktrees/feat-2279-agent-context-workspace
- Gate record: .workflow/records/2279-feat-2279-agent-context-workspace.json (finalized; pass `--record <path>`; base-ref currently feat/2271-webmcp-bridge)
- Checklist: docs/planning/adr-055-spec2-3-checklist.md on origin/track/adr-055-spec2-3 (manager maintains; do not edit)

## Situation

The previous implementer (A1) was interrupted in the middle of A1-fix2 (section "A1-fix2" of docs/planning/adr-055-spec2-3-dispatch-prompts.md on origin/track/adr-055-spec2-3 — read it). Its worktree holds UNCOMMITTED, UNPUSHED edits to 8 files (+676/-207): docs/specs/adr-055-agent-context-workspace.md, tools_execution.py, tools_workspace.py, api/routes/projects.py, api/runtime/_file_writes.py, engine/runners/platform.py, tests/ai/test_mcp_execution_tools.py, tests/ai/test_mcp_workspace_tools.py. Treat them as a draft: read every hunk, map it to the A1-fix2 items, keep what is correct, fix or finish the rest. Do not discard them unread, and do not assume any item is done until its test proves it.

PR #2275 (Spec 1) merged into main at 84643e354; main is 26 commits ahead of the branch. The owner approved the engine/runners core change and applies `admin-approved:core-change` on #2292 (already recorded in the ledger).

## Required Rules

AGENTS.md; docs/ai-developer/rules.md; docs/ai-developer/specific_rules/gated-workflow.md; docs/ai-developer/personas/implementer.md; issue #2279 decisions and the later owner decisions in the checklist.

## Environment Notes (Windows, Git Bash)

- Prefix every git/gate command with `cd /c/Users/jiazh/workspace/SciStudio/.worktrees/feat-2279-agent-context-workspace && `; run `git branch --show-current` before add/commit; `git add -A` before every commit.
- Python: `PYTHONPATH=src /c/Users/jiazh/workspace/SciStudio/.venv/Scripts/python`. Never `pip install -e .`; never modify the shared .venv (use a scratch venv / `uv pip install --target` in your scratch space to reproduce fastmcp 4.0.3 / mcp 2.2.0).
- `git show <ref>:<path>` needs `MSYS_NO_PATHCONV=1`.
- Never kill a process you did not start. Run long commands in the foreground, output redirected to a log, long timeout; do not background them.

## Work To Do

1. Finish every A1-fix2 item (1-9), each with a test where behavior changes: mcp 2.2 `CallToolResult` construction; POSIX cancel not reaping the asyncio-owned shell; atomic expected-version check + replace; Windows Job Object failure refuses the command; search deadline inside a file scan; root cause of the 3.11 "distutils already imported" collection errors (fix the cause, no skip/reorder); deferral-ratchet wording; CodeQL #274-276 via a code fix (stop and report if a real false positive remains); Codex replies.
2. Commit the fixes on the committed diff with `gate_record check --record <ledger> --mode pre-pr --base origin/feat/2271-webmcp-bridge --head HEAD --pr-body-file .workflow/local/pr-body.md`.
3. Move onto main: `gate_record amend --record <ledger> --base-ref main --reason "#2275 merged into main at 84643e354; base moves from feat/2271-webmcp-bridge to main"`; `git merge origin/main` (merge, not rebase — the PR is open); resolve conflicts deliberately and report them.
4. Update `.workflow/local/pr-body.md`: drop the "depends on #2275" note (merged); keep Closes #2279, the gate record path, the core-change note, the final `🤖 Generated with [Claude Code](https://claude.com/claude-code)` line. Update the PR body on GitHub (`gh pr edit 2292 --body-file ...`).
5. `gate_record check --record <ledger> --mode pre-pr --base origin/main --head HEAD --pr-body-file .workflow/local/pr-body.md`; commit; push; post-PR finalize `--record <ledger> --commit <sha> --pr 2292 --pr-body-file .workflow/local/pr-body.md`; commit + push; wait for CI.
6. Expected remaining red only: Verify Workflow Compliance until the owner applies the label.

Commits: Conventional Commits; trailers Gate-Record / Task-Kind: feature / Issue: #2279 / Assisted-by: claude-code:claude-opus-5 / `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`. MUST NOT merge any PR.

## Output Required

Which draft hunks you kept / changed / dropped and why; fix commits; root cause of the collection errors; CodeQL outcome; merge commit and conflicts; final CI state on #2292.

## Stop Conditions

Out-of-scope file needed; CodeQL false positive that needs dismissal; unclear check failures; you cannot add a required test.
```

---

## AU3 — Audit the Spec 2 branch, with-context

```markdown
[DISPATCH-TEMPLATE-V1: audit-with-context]

## Task Identity

- Repository: SciStudio (C:/Users/jiazh/workspace/SciStudio)
- Persona: audit_reviewer
- Audit mode: with-context
- Task kind: maintenance (your own gate ledger)
- Issue: #2279 (https://github.com/jiazhenz026/SciStudio/issues/2279)
- Owner request: Verify the ADR-055 Spec 2 implementation before its PR opens.
- Umbrella PR: #2283 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-055-spec2-3
- Audit branch: audit/2279-spec2-with-context (base: origin/feat/2279-agent-context-workspace) — ALREADY CREATED
- Audit worktree: C:/Users/jiazh/workspace/SciStudio/.worktrees/audit-2279-spec2-wc — ALREADY CREATED at b1693f913
- Gate record: init your own (task_kind=maintenance, persona=audit_reviewer, runtime `claude-code:claude-opus-5`, branch audit/2279-spec2-with-context, --base-ref feat/2279-agent-context-workspace, --issue 2279, --include docs/audit/2026-09-11-adr-055-spec2-with-context.md)
- Checklist: docs/planning/adr-055-spec2-3-checklist.md on origin/track/adr-055-spec2-3 (`git fetch origin && git show origin/track/adr-055-spec2-3:docs/planning/adr-055-spec2-3-checklist.md`; do NOT edit it)
- Work to audit: branch feat/2279-agent-context-workspace @ b1693f913, STACKED on feat/2271-webmcp-bridge (PR #2275, open). No PR exists yet. Audit the Spec 2 delta only: `git diff origin/feat/2271-webmcp-bridge...origin/feat/2279-agent-context-workspace`.
- Audit report path: docs/audit/2026-09-11-adr-055-spec2-with-context.md

## Required Reading

- Issue #2279 (its "Owner decisions" override the spec), spec `docs/specs/adr-055-agent-context-workspace.md` (as rewritten by the branch), the Spec 4 additions in `docs/specs/adr-055-lab-deployment.md`, ADR-055 §5, §9.2 (robustness findings are requirements) and §11 (Workspace / Execution / Existing context rows), Spec 1 `docs/specs/adr-055-webmcp-bridge.md` (adapter contract FR-003, binding FR-005, logging FR-007), the checklist sections 7 and 10.
- AGENTS.md, docs/ai-developer/rules.md, docs/ai-developer/specific_rules/agent-dispatch.md, docs/ai-developer/personas/audit-reviewer.md

## Audit Goal

Verify the claimed work against the issue decisions, specs, code, tests, gate evidence. Report findings first. Severity: P1 blocks merge or breaks contract; P2 should fix before completion; P3 improvement/follow-up.

Claims to verify (from the implementer's report and the checklist drift log):
- Decisions 1-6 of #2279 implemented: no transfer tools in Spec 2 (moved to Spec 4 text); inspect tools read any OS-user-readable absolute path, bounded WHILE streaming; author tools project-confined with the `workflows/*.yaml|*.yml` and `data/` blacklist on source AND target; the four hook-parity behaviors (list_blocks-first per backend lifetime incl. scaffold_block via bridge only, port-type warning, CLI denial, run_workflow poll hint additive); optional expected `state_version` with the editor route unchanged; in-memory command status; `run_command` in `app.state.registry`.
- Blacklist robustness on Windows and POSIX: case variants (`Workflows/X.YAML`), backslash separators, `./`, `..` segments, symlinks/junctions resolving into `data/` or `workflows/`, rename/move into and out of protected areas.
- Refusals returned as `status` + refusal code instead of `isError`: assess against the Spec 1 adapter contract (FR-003) and ADR-055 §4 ("failure information" must be preserved) — would an external agent read a refusal as success?
- Shared write helper extraction: editor PUT route behavior unchanged (parity tests real, not tautological); FILE_CHANGED and block reload still fire for both callers; no ai->api import.
- `run_command`: event loop never blocked; bounded incremental capture; process-tree cancellation (Windows `create_subprocess_shell` — does cancellation kill the shell's children, not just cmd.exe?); request abort does not kill the job; `list_commands`/status/cancel semantics; env (IPC token stripped, user deps, `SCISTUDIO_PROJECT_DIR`); CLI denial bypasses you can find.
- Bridge marker context variable: cannot leak across concurrent requests or into local-transport calls.
- `get_agent_context`: every index path resolves; missing-asset diagnostics accurate; hook guidance honest.
- Logging: no file contents, command bodies, or full arguments anywhere in new code.
- Tests: find assertions weaker than what they claim (fixtures that never reach the failure path, stubs that bypass the real helper); the locally skipped real-pip test — is the skip justified and does CI run it?
- Scope: every file outside the dispatch write set is covered by a manager approval or the dispatch's conditional scope (checklist drift log).

Do not write feature code. Never kill a process you did not start. MUST write the audit report to the path above, commit it on your audit branch (trailers: Gate-Record, Task-Kind: maintenance, Issue: #2279, Assisted-by: claude-code:claude-opus-5, plus `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`), and push (`git push -u origin audit/2279-spec2-with-context`). Do NOT open a PR.

## Checks

Run or verify (PYTHONPATH=src /c/Users/jiazh/workspace/SciStudio/.venv/Scripts/python; from your worktree):
- `pytest tests/ai/test_mcp_agent_context.py tests/ai/test_mcp_workspace_tools.py tests/ai/test_mcp_execution_tools.py tests/api/test_projects.py tests/ai/test_mcp_fastmcp.py -q --no-cov` (plus targeted repros you write in your scratch space)
- `lint-imports` (or the gate's import_contracts check)
- `gate_record check --mode local --base origin/feat/2279-agent-context-workspace --head HEAD` after committing your report
- Sentrux: unavailable in this runtime — record N/A. Frontend/browser smoke: N/A (no frontend change).

## Output Required

Report path; commit sha containing the report; findings by severity; checklist/scope drift if any; missing tests/docs/gate evidence if any; recommendation: pass / pass-with-fixes / block.

## Stop Conditions

Stop and report if: you need to change implementation code; required evidence is unavailable; the audit scope conflicts with AGENTS.md/ADR/spec/gate record.
```

---

## AU4 — Independent audit of the Spec 2 surfaces, no-context

```markdown
[DISPATCH-TEMPLATE-V1: audit-no-context]

## Task Identity

- Repository: SciStudio (C:/Users/jiazh/workspace/SciStudio)
- Persona: audit_reviewer
- Audit mode: no-context
- Audit branch: audit/2279-spec2-no-context — ALREADY CREATED
- Audit worktree: C:/Users/jiazh/workspace/SciStudio/.worktrees/audit-2279-spec2-nc — ALREADY CREATED
- Allowed audit surfaces:
  - src/scistudio/ai/agent/mcp/** (especially tools_workspace.py, tools_execution.py, tools_qa.py, _context.py, tools_authoring.py, tools_workflow/**)
  - src/scistudio/api/runtime/_file_writes.py, src/scistudio/api/runtime/__init__.py, src/scistudio/api/routes/projects.py, src/scistudio/api/routes/webmcp.py, src/scistudio/api/app.py
  - src/scistudio/agent_provisioning/** (read only; the provisioned hooks define local agent rules)
  - tests/ai/**, tests/api/test_projects.py, tests/contracts/test_runtime_import_contract.py
  - docs/specs/adr-055-*.md, docs/adr/ADR-055.md, docs/adr/ADR-036.md, docs/adr/ADR-040.md
- Change surface for reading diffs: `git diff origin/feat/2271-webmcp-bridge...HEAD`
- Audit report path: docs/audit/2026-09-11-adr-055-spec2-no-context.md

## Context Limits

You must not read or use:

- Any GitHub issue or PR (no `gh issue`, no `gh pr`).
- Anything under docs/planning/** (manager checklists, dispatch prompts).
- Commit messages: do not run `git log`, `git show <commit>` with messages, or `git blame`. Read changes with the `git diff` above and by reading files.
- Gate ledgers under .workflow/records/ other than the one you create.
- Chat summaries or manager summaries of what changed.

You may read only repository docs, code, tests, committed generated facts or audit outputs, and output from commands you run yourself.

## Required Reading

- AGENTS.md, docs/ai-developer/rules.md, docs/ai-developer/personas/audit-reviewer.md
- Governing ADRs, specs, and docs discovered from the allowed surfaces.

## Audit Goal

Independently check whether docs, code, tests, and declared contracts agree. Do not assume what anyone intended to change.

Look for:

- Path handling defects: traversal, symlink/junction escapes, case and separator variants on Windows, writes landing outside the project, protected areas (`workflows/*.yaml`, `data/`) reachable by any mutation path including rename/move/delete.
- Resource bounds: any read, search, or command-output path that materializes more than its documented cap.
- Subprocess lifecycle: event-loop blocking, cancellation that leaves descendants alive (check Windows shell spawning specifically), jobs killed by a request ending, registry residue, which registry is terminated at shutdown.
- Error signalling: tool outcomes an external caller could misread as success.
- Concurrency: shared state (e.g. context variables, per-backend flags, command stores) that can leak between concurrent calls or transports.
- Tests whose assertions are weaker than the behavior they claim to cover: stubs that bypass the real code path, fixtures that never reach the failure branch, skips.
- Logging that records file contents, command bodies, or full arguments.
- Docs/spec statements the code does not implement, and code behavior the docs do not describe.
- For any suspected failure, reproduce it on the base (`origin/feat/2271-webmcp-bridge`, in a detached checkout under your scratch space) to decide whether it is new or pre-existing.

## Coordination

- Work only on your audit branch and worktree. MUST NOT use `pip install -e .`. MUST NOT merge any PR. MUST NOT edit implementation files or any checklist. Never kill a process you did not start.
- MUST write the audit report to the path above, commit it on your audit branch (trailers: Gate-Record, Task-Kind: maintenance, Assisted-by: claude-code:claude-opus-5, plus `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`), and push (`git push -u origin audit/2279-spec2-no-context`). Do NOT open a PR.

## Checks

Run or verify (PYTHONPATH=src /c/Users/jiazh/workspace/SciStudio/.venv/Scripts/python):
- the tests under the allowed test surfaces relevant to your findings (`-q --no-cov`)
- `gate_record init --task-kind maintenance --persona audit_reviewer --runtime claude-code:claude-opus-5 --branch audit/2279-spec2-no-context --base-ref feat/2279-agent-context-workspace --include docs/audit/2026-09-11-adr-055-spec2-no-context.md --owner-directive "independent no-context audit of the agent workspace and execution tool surfaces"`, then after committing the report: `gate_record check --mode local --base origin/feat/2279-agent-context-workspace --head HEAD` (record any issue-linkage gap as a known gap; do not look up issues)
- Sentrux: unavailable in this runtime — record N/A.

## Output Required

- Audit report path and the commit sha containing it.
- Findings ordered by severity (P1 blocks merge or breaks contract; P2 should fix; P3 follow-up), each with evidence from docs, code, tests, or tool output.
- No statement about anyone's intent unless it is visible in repository docs.
- Recommendation: pass, pass-with-fixes, or block.

## Stop Conditions

Stop and report back if: you are asked to read issue/checklist/PR context; the audit requires hidden context; you need to edit implementation code.
```
