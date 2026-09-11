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
