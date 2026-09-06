---
title: "ADR-055 Spec 0-1 Dispatch Prompts"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 55
related_specs:
  - adr-055-prefix-independence
  - adr-055-webmcp-bridge
language_source: en
---

# ADR-055 Spec 0-1 Dispatch Prompts

Filled from `docs/ai-developer/templates/agent-dispatch-prompt-template.md`.
Checklist: `docs/planning/adr-055-spec0-1-checklist.md`.

---

## A1 — Spec 0: Prefix Independence

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-055 Spec 0 (prefix independence) as a final PR to main.
- Task kind: feature
- Persona: implementer
- Issue: #2270
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2270
- Umbrella PR: #2273 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-055-spec0-1
- Agent branch: feat/2270-prefix-independence (base: origin/main)
- Agent worktree: .worktrees/feat-2270-prefix-independence
- Gate record: .workflow/records/2270-feat-2270-prefix-independence.json (init creates it)
- Checklist: docs/planning/adr-055-spec0-1-checklist.md (on umbrella branch; manager maintains it — you do NOT edit it)

## Required Rules

Read and follow:

- The GitHub issue #2270 and the spec `docs/specs/adr-055-prefix-independence.md` (the spec is the requirements contract; follow its FR-001..FR-009, implementation sequence §4.3, and verification plan §4.4).
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/new-feature.md
- docs/ai-developer/personas/implementer.md

## Environment Notes (Windows, Git Bash)

- Python: run everything as `PYTHONPATH=src /c/Users/jiazh/workspace/SciStudio/.venv/Scripts/python -m ...` from your worktree. NEVER `pip install -e .`.
- Gate runtime id for ledger init: `agents:kimi-k2`.
- Frontend: `cd frontend && npm ci` inside your worktree before running frontend tests/checks (node_modules is not shared into worktrees).
- `scistudio-web-demo` (at `.scratch-design/webmcp-recovery/scistudio-web-demo` and anywhere else) is a READ-ONLY reference. Never modify, commit, or push to it. Spec 0 does not need it at all.

## Scope

You own only (spec §4.2 affected files):

- src/scistudio/api/app.py
- src/scistudio/api/spa.py
- src/scistudio/api/routes/workflows.py
- src/scistudio/cli/main.py
- frontend/src/lib/api/base-path.ts (create)
- frontend/src/lib/api/core.ts
- frontend/src/hooks/useWebSocket.ts
- frontend/src/components/AIChat/hooks/usePtyWebSocket.ts
- frontend/src/App.parts/InteractiveModals.parts/panelModuleLoader.ts
- frontend/src/components/DataPreview.parts/dynamicPreviewer.ts
- frontend/src/components/AIChat/SetupScreen.tsx
- frontend/src/components/CodeEditor.parts/useLintMarkers.ts
- frontend/src/components/LearningCenter.parts/ProviderIntro.tsx
- frontend/src/lib/logger.ts
- tests/api/test_root_path.py (create)
- frontend/src/lib/api/base-path.test.ts (create)
- .workflow/records/** (your own ledger), .workflow/local/** (never commit local/)

You must not touch:

- docs/ai-developer/** (governance surface)
- docs/adr/**, docs/specs/** (specs are inputs, not deliverables)
- .scratch-design/** (read-only demo reference)
- src/scistudio/api/routes/webmcp.py, frontend/src/webmcp/** (Spec 1 / agent A2)
- desktop/** (desktop path always uses the empty prefix)

If the FR-004 sweep finds additional root-relative call sites beyond the listed
files, `gate_record amend --reason ... --include <path>` BEFORE editing them.
If you need any other out-of-scope path, stop and report back.

## Coordination

- You are not alone in this codebase. Work only on your branch, only in your worktree.
- Do not revert or overwrite other agents' work.
- Your PR targets `main` directly (manager-assigned final PR).
- MUST NOT merge any PR.

## TODO And Deferral Rule

Deferred work must be tracked in the repo: `TODO(#NNN): <reason>` citing an
issue/ADR/spec. The owner directive for this task is NO deferrals: implement
the spec fully; if something is genuinely out of scope, stop and report instead
of deferring.

## Work To Do

Follow spec §4.3:

1. Backend `root_path` plumbing in create_app + SPA bootstrap injection in api/spa.py + CLI flags/env in cli/main.py (`--root-path` / `SCISTUDIO_ROOT_PATH`, host binding flags on serve and gui; defaults unchanged).
2. `frontend/src/lib/api/base-path.ts` single source of truth (`apiUrl`/`wsUrl`, single-point normalization, runtime global `window.__SCISTUDIO_BASE_PATH__` default `""`); route `apiFetch` through it; migrate the two WS hooks and the two same-origin validators.
3. Migrate the enumerated direct `fetch("/api/...")` call sites; run the root-relative literal sweep (SC-004: zero `"/api/` or `"/ws"` literals outside base-path.ts and tests); add the guard test.
4. Worker callback URL: `SCISTUDIO_ENGINE_API_URL` from configured external base (api/routes/workflows.py), not `request.base_url`.
5. Requests at the unprefixed root while a prefix is configured: pick one behavior (redirect or 404), document it in the test.
6. Docs: update user/CLI docs if a docs surface exists for serve flags; otherwise record `--docs-na` rationale in the ledger. Check whether `docs/ai-developer/*` need updates (they should not — record N/A).

## Required Tests And Checks

- tests/api/test_root_path.py: prefixed and unprefixed serving, SPA shell, representative API, WS handshake, redirect contract, worker callback URL derivation (spec §4.4).
- frontend/src/lib/api/base-path.test.ts: helper normalization + root-relative literal guard.
- Existing backend/frontend suites must pass unchanged under default empty prefix (SC-002).
- Gate flow (all from your worktree, `PYTHONPATH=src`, venv python above):
  1. `python -m scistudio.qa.governance.gate_record init --task-kind feature --persona implementer --runtime agents:kimi-k2 --branch feat/2270-prefix-independence --issue 2270 --owner-directive "<summary>" --include <each write-set path>`
  2. `gate_record plan` with docs/test declarations
  3. implement; `gate_record amend` before any scope addition
  4. `gate_record check --base origin/main --head HEAD` then `--mode pre-pr --pr-body-file .workflow/local/pr-body.md`
  5. `gate_record finalize --base origin/main --head HEAD --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#2270"`
  6. push; `python scripts/scistudio_pr_create.py --title "feat(#2270): ..." --body "..."` (body must contain `Closes #2270` and `Gate record: <path>`)
  7. `gate_record finalize --commit <sha> --pr <url> --pr-body-file .workflow/local/pr-body.md`; commit+push the ledger update
- Commits: Conventional Commits; trailers `Gate-Record:`, `Task-Kind: feature`, `Issue: #2270`, `Assisted-by: agents:kimi-k2`.
- Sentrux MCP is unavailable in this runtime; record that when asked.

## Output Required

- Changed file paths.
- Tests/checks run and results (commands + pass/fail).
- PR number/URL and gate record path.
- Any blocker or scope issue.

## Stop Conditions

Stop and report back if: you need an out-of-scope file; the task conflicts with AGENTS.md/ADR/spec/gate record; local checks fail for unclear reasons; you cannot add required tests.
```

---

## A2 — Spec 1: WebMCP Bridge

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-055 Spec 1 (WebMCP bridge) as a final PR to main, stacked on the Spec 0 branch.
- Task kind: feature
- Persona: implementer
- Issue: #2271
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2271
- Umbrella PR: #2273 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-055-spec0-1
- Agent branch: feat/2271-webmcp-bridge (STACKED on feat/2270-prefix-independence — record `--base-ref feat/2270-prefix-independence` in every gate command; never measure against origin/main)
- Agent worktree: .worktrees/feat-2271-webmcp-bridge
- Gate record: .workflow/records/2271-feat-2271-webmcp-bridge.json (init creates it)
- Checklist: docs/planning/adr-055-spec0-1-checklist.md (manager maintains it — you do NOT edit it)

## Required Rules

Read and follow:

- The GitHub issue #2271 and the spec `docs/specs/adr-055-webmcp-bridge.md` (FR-001..FR-011, sequence §4.3, verification §4.4).
- ADR-055 `docs/adr/ADR-055.md` sections 4 and 9.2 (robustness findings are requirements).
- AGENTS.md, docs/ai-developer/rules.md, docs/ai-developer/specific_rules/gated-workflow.md, docs/ai-developer/specific_rules/new-feature.md, docs/ai-developer/personas/implementer.md

## Environment Notes (Windows, Git Bash)

- Python: `PYTHONPATH=src /c/Users/jiazh/workspace/SciStudio/.venv/Scripts/python -m ...` from your worktree. NEVER `pip install -e .`.
- Gate runtime id: `agents:kimi-k2`.
- Frontend: `cd frontend && npm ci` inside your worktree first.
- The demo reference is READ-ONLY. Extract transplant sources with:
  `git -C /c/Users/jiazh/workspace/SciStudio/.scratch-design/webmcp-recovery/scistudio-web-demo show 952f697b:<path>`
  Key files at that commit: `src/scistudio/api/routes/webmcp.py` (146-line router), `frontend/src/webmcp/register.ts`, `frontend/src/webmcp/types.ts`, wiring in `frontend/src/main.tsx` and `src/scistudio/api/app.py`.
  NEVER modify, commit, or push to that repo (blocking hooks are installed; treat any write need as a stop condition).

## Scope

You own only (spec §4.2 affected files):

- src/scistudio/api/routes/webmcp.py (create)
- src/scistudio/ai/agent/mcp/server.py (promote _serialise_result to the shared documented adapter; audience-tag filtering in socket tools/list)
- src/scistudio/ai/agent/mcp/__init__.py (audience tag constant)
- src/scistudio/api/app.py (mount router /api/webmcp; wire bridge session middleware)
- src/scistudio/api/spa.py (extend bootstrap injection with the loopback session token — Spec 0's injection mechanism is on your base branch)
- frontend/src/webmcp/register.ts (create), frontend/src/webmcp/types.ts (create)
- frontend/src/main.tsx (fire-and-forget wiring)
- frontend/src/lib/api/core.ts (bridge fetches: token header + base path)
- tests/api/test_webmcp.py (create)
- tests/ai/test_mcp_fastmcp.py (modify: audience filtering tests)
- frontend/src/webmcp/register.test.ts (create)
- .workflow/records/** (your own ledger), .workflow/local/** (never commit)

You must not touch:

- docs/ai-developer/**, docs/adr/**, docs/specs/**
- .scratch-design/** (read-only demo)
- Spec 0's frontend base-path helper implementation (use it as-is from your base branch; if it is missing or broken, stop and report)
- Domain tools (get_agent_context, workspace, execution): NOT in this spec
- The local socket transport's wire protocol

## Coordination

- You are not alone; work only on your branch/worktree. Do not modify the Spec 0 branch; build on it read-only.
- Your PR targets `main` (manager-assigned final PR). The diff vs main includes Spec 0 commits until that PR merges; your ledger's `--base-ref feat/2270-prefix-independence` records your actual delta (per #2143).
- MUST NOT merge any PR.

## TODO And Deferral Rule

No deferrals (owner directive). Deferred work needs `TODO(#NNN)` citing an issue/ADR/spec; if something is genuinely out of scope, stop and report.

## Work To Do

Follow spec §4.3 (T-001..T-006): adapter promotion + router + mount; audience tag + both-side filtering; session middleware (one middleware, pluggable identity-backend interface, loopback token backend delivered via SPA bootstrap injection); catalogue context snapshot + stale-mutation rejection (FR-005); frontend registration module hardened per FR-009 (dual document/navigator probing, superseded-attempt abort, per-tool failure tolerance, retry path, no stale success); bounded logging (FR-007: tool name + outcome, NEVER full arguments); all frontend URLs via the Spec 0 base-path helpers (FR-008 — no root-relative literals).

## Required Tests And Checks

- tests/api/test_webmcp.py: catalogue parity vs `mcp.list_tools()`, unknown-tool 404, adapter mapping fixtures (structured, non-text, error flag, thrown exception), stale-project rejection, token required/accepted, log-scanning test (SC-005).
- tests/ai/test_mcp_fastmcp.py: audience filtering both directions.
- frontend/src/webmcp/register.test.ts: US3 matrix (missing/late capability, superseded attempts, partial failure, reconnect, no stale success).
- Gate flow: same command shape as any feature PR, but ALWAYS pass `--base-ref feat/2270-prefix-independence` (init/plan/amend) and `--base feat/2270-prefix-independence` (check/finalize --base). Ledger trailers: `Gate-Record:`, `Task-Kind: feature`, `Issue: #2271`, `Assisted-by: agents:kimi-k2`. PR via `python scripts/scistudio_pr_create.py`; body must contain `Closes #2271` and `Gate record: <path>`. Post-PR finalize + commit + push.
- Sentrux MCP unavailable in this runtime; record that when asked.

## Output Required

- Changed file paths; tests/checks run and results; PR number/URL and gate record path; blockers.

## Stop Conditions

Stop and report back if: out-of-scope file needed; conflict with AGENTS.md/ADR/spec/gate record; unclear check failures; Spec 0 base branch missing what the spec says it provides; you cannot add required tests.
```
