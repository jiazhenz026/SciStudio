---
title: "ADR-054 Panels Dispatch Prompts"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 54
related_specs:
  - adr-054-panels
language_source: en
---

# ADR-054 Panels Dispatch Prompts

Filled from `docs/ai-developer/templates/agent-dispatch-prompt-template.md`.
Checklist: `docs/planning/adr-054-panels-checklist.md`.

---

## A1 — Phase A Backend

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-054 Phase A (panel mechanism and Panels tab) as one PR per phase; you own the backend half.
- Task kind: feature
- Persona: implementer
- Issue: #2293
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2293
- Umbrella PR: #2299 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-054-panels
- Phase integration branch: feat/2293-panels-phase-a (manager-owned; it carries the amended spec)
- Agent branch: feat/2293-a1-backend (cut from feat/2293-panels-phase-a; record `--base-ref feat/2293-panels-phase-a` in every gate command)
- Agent worktree: .worktrees/feat-2293-a1-backend
- Gate record: .workflow/records/2293-feat-2293-a1-backend.json (your init creates it)
- Checklist: docs/planning/adr-054-panels-checklist.md (on the umbrella branch; the manager maintains it — you do NOT edit it)

## Required Rules

Read and follow:

- The GitHub issue #2293 and all owner instructions in it.
- `docs/specs/adr-054-panels.md` as it stands on your branch — it is the requirements contract. Read §1.1 (owner amendments) first. `docs/adr/ADR-054.md` is the governing decision.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/new-feature.md
- docs/ai-developer/personas/implementer.md

## Environment Notes (Windows, Git Bash)

- Python: run everything as `PYTHONPATH=./src /c/Users/jiazh/workspace/SciStudio/.venv/Scripts/python -m ...` from your worktree. NEVER `pip install -e .`.
- Put `cd <your absolute worktree path> && ` in front of every git or gate command; the shell's working directory does not persist between tool calls. Run `git branch --show-current` before any commit.
- Gate runtime id: `claude-code`.
- `git add -A` before every commit.
- Other agents run tests on this machine at the same time; a flaky failure in a file you did not touch is classified before it is blamed on your change (see known issues #2047, #2103, #2074, #2107).

## Scope

You own only:

- src/scistudio/panels/** except src/scistudio/panels/sdk/** (agent A2 owns the SDK)
- src/scistudio/api/routes/panels.py (create)
- src/scistudio/api/app.py
- src/scistudio/api/routes/data.py
- src/scistudio/api/routes/blocks.py
- src/scistudio/api/routes/user_library.py
- src/scistudio/core/dropins.py (protected core; the owner applies `admin-approved:core-change` on the final PR — record the label request in your ledger with `--admin-label admin-approved:core-change`)
- src/scistudio/previewers/**
- src/scistudio/blocks/base/interactive.py
- src/scistudio/blocks/registry/**
- scripts/audit/check_package_contract_tables.py
- docs/planning/adr-049-package-validator/contracts/**
- pyproject.toml (package data for `panels/lib`, `panels/sdk`, `panels/builtin`)
- CHANGELOG.md (the T-007 hardening entry)
- tests/panels/** (create), tests/api/**, tests/previewers/**, tests/blocks/**
- .workflow/records/2293-feat-2293-a1-backend.json, .workflow/local/** (never commit local/)

You must not touch:

- frontend/** (agent A2)
- src/scistudio/panels/sdk/** (agent A2)
- docs/adr/** — including ADR-049 and ADR-054, both `agent_editable: false`
- docs/specs/** (the manager owns the spec)
- docs/ai-developer/** (governance surface)
- src/scistudio/tutorials/** (owner decision: the tutorial stays unchanged)
- src/scistudio/panels/builtin/** content beyond an empty package marker (Phase B)
- src/scistudio/ai/agent/mcp/tools_inspection/_preview.py (spec: out of scope)

If you need an out-of-scope path, stop and report back. Do not edit it.

## Coordination

- You are not alone in this codebase. Agent A2 builds the frontend host, the SDK, and the Panels tab in parallel on `feat/2293-a2-frontend`, coding against the HTTP contracts you implement.
- **Contract first.** Your first commit MUST contain the request and response models (Pydantic) for: `POST /api/panels/contexts` (preview, interactive, and sample kinds) and `DELETE /api/panels/contexts/{id}`; `POST /api/panels/contexts/{id}/read` (JSON and binary forms); the panel entries added to `GET /api/previews/previewers` (FR-005, including contexts, types, priority, tier, owner, shadowing, sample presence, diagnostics, and the deprecation marker for legacy previewers); and the `panels` target of `/api/user-library` (FR-054). Commit it as soon as it is stable and tell the manager the commit SHA in your progress report. A2 reads it with `git show feat/2293-a1-backend:<path>`. After that commit, change a contract only by reporting to the manager first.
- MUST work only on your assigned branch and worktree. Do not revert or overwrite other agents' work.
- Do NOT open a PR. The manager reviews your branch and merges it into `feat/2293-panels-phase-a`.
- MUST NOT merge any PR.

## TODO And Deferral Rule

Deferred work must be tracked in the repo: `TODO(#NNN): <reason>` citing an issue, ADR, spec, or follow-up ticket. Do not leave hidden V1, MVP, or later work.

Known deferred items:

- FR-026: the ADR-055 Lab session middleware does not exist. Validate the token inside the token-scoped routes and mark the middleware integration point with `TODO(#2288)` (owner decision).
- FR-049: the "What Is A Type" tutorial is not migrated (#2288). Do not touch it.

## Work To Do

Follow spec §4.3, tasks T-001 to T-009 and T-020/T-021, plus the backend halves of FR-050 to FR-054:

1. T-001/T-002: `scistudio.panels` descriptor model and parser (FR-001 to FR-003), discovery at the four tiers including the `scistudio.panels` entry point and the tutorial library swap (FR-004), dot-directories skipped (FR-054), reload and project-switch triggers and the catalog listing (FR-005).
2. T-003: routing over panels and legacy `PreviewerSpec` records as one candidate set, the shared id namespace, choices accepting panel ids (FR-006 to FR-008). Reuse the ADR-048 router; do not reimplement the ladder.
3. T-004: `PreviewDataAccess` extensions (FR-014).
4. T-005: context service with tokens, the generic read route off the event loop, context authorization, and the `sample` kind of FR-053 (FR-009 to FR-013, FR-019 backend half, FR-025).
5. T-006: token-scoped file routes for panel assets, SDK (`src/scistudio/panels/sdk/<major>/scistudio-panel.js`, the file A2 writes), and the library set; CSP, CORS headers, and file-type allowlist (FR-026 to FR-028); the local library set in `src/scistudio/panels/lib/` with `index.json` (FR-032; Plotly at the exact version in `frontend/package-lock.json`, D3, three.js, PDF.js — record name, version, files, license, SHA-256); the CDN allowlist (FR-033).
6. T-007: refuse state-changing requests with `Origin: null` on every route (FR-030) and refuse to start with `*` or `null` in `SCISTUDIO_CORS_ORIGINS` (FR-031), with a CHANGELOG entry.
7. T-008: the interactive checks at discovery, reload, and open (FR-023) and the deprecation diagnostics for both legacy forms (FR-036, FR-037).
8. T-009: validator code and contract-table rows (FR-038). `check_package_contract_tables.py` requires every contract id to appear in `docs/adr/ADR-049.md`, which you may not edit: write the rows and code, and put the exact ADR-049 text you need into `.workflow/local/adr-049-proposed.md`, then report it to the manager. The manager brings the owner's decision back.
9. FR-054 backend: the `panels` target of `/api/user-library` with atomic directory staging, collision refusal, overwrite, and registry reload.

## Required Tests And Checks

- The spec frontmatter `tests` list for backend paths: `tests/panels/test_panel_descriptor.py`, `test_panel_registry.py`, `test_panel_routing.py`, `test_panel_contexts.py`, `test_panel_read.py`, `test_panel_tokens.py`, `tests/api/test_panel_routes.py`, `tests/api/test_panel_security.py`, `tests/api/test_app.py`, `tests/api/test_interactive_panels.py`, `tests/api/test_user_library_panels.py`, `tests/blocks/test_interactive_mixin.py`, `tests/previewers/test_preview_routing.py`, `tests/previewers/test_preview_data_access.py`.
- US5 prefix and token tests with the adr-055-prefix-independence harness (no session authentication; FR-026 TODO).
- Existing backend suites pass unchanged.
- Gate flow (from your worktree, `PYTHONPATH=./src`, venv python above):
  1. `gate_record init --task-kind feature --persona implementer --runtime claude-code --branch feat/2293-a1-backend --issue 2293 --base-ref feat/2293-panels-phase-a --owner-directive "<summary>" --include <each write-set path>`
  2. `gate_record plan` with docs, tests, and `--admin-label admin-approved:core-change`
  3. implement; `gate_record amend --reason ... --include <path>` before any scope addition
  4. `gate_record check --base feat/2293-panels-phase-a --head HEAD` until it passes. Do not run `finalize` and do not open a PR.
- Commits: Conventional Commits; trailers `Gate-Record: .workflow/records/2293-feat-2293-a1-backend.json`, `Task-Kind: feature`, `Issue: #2293`, `Assisted-by: claude-code:<model>`.
- Docs: the spec is the manager's; record `--docs-updated CHANGELOG.md` and `--docs-na` for any other class with a rationale.
- Sentrux MCP is unavailable in this runtime; record that when asked.

## Output Required

Before reporting done, provide:

- The contract commit SHA and the final branch SHA.
- Changed file paths.
- Tests and checks run, with results.
- The ADR-049 proposed text path, if T-009 reached it.
- Any blocker, contract change, or scope issue.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file.
- The task conflicts with AGENTS.md, ADR-054, the spec, or the gate record.
- A contract A2 depends on must change after your contract commit.
- Checks fail for unclear reasons.
- You cannot add or update required tests.
```

---

## A2 — Phase A Frontend, SDK, And Panels Tab

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-054 Phase A (panel mechanism and Panels tab) as one PR per phase; you own the frontend host, the SDK, and the Panels tab.
- Task kind: feature
- Persona: implementer
- Issue: #2293
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2293
- Umbrella PR: #2299 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-054-panels
- Phase integration branch: feat/2293-panels-phase-a (manager-owned; it carries the amended spec)
- Agent branch: feat/2293-a2-frontend (cut from feat/2293-panels-phase-a; record `--base-ref feat/2293-panels-phase-a` in every gate command)
- Agent worktree: .worktrees/feat-2293-a2-frontend
- Gate record: .workflow/records/2293-feat-2293-a2-frontend.json (your init creates it)
- Checklist: docs/planning/adr-054-panels-checklist.md (on the umbrella branch; the manager maintains it — you do NOT edit it)

## Required Rules

Read and follow:

- The GitHub issue #2293 and all owner instructions in it.
- `docs/specs/adr-054-panels.md` as it stands on your branch — it is the requirements contract. Read §1.1 (owner amendments) first. `docs/adr/ADR-054.md` is the governing decision.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/new-feature.md
- docs/ai-developer/personas/implementer.md

## Environment Notes (Windows, Git Bash)

- Python (gate CLI only): `PYTHONPATH=./src /c/Users/jiazh/workspace/SciStudio/.venv/Scripts/python -m ...` from your worktree. NEVER `pip install -e .`.
- Frontend: run `cd frontend && npm ci` inside your worktree first; `node_modules` is not shared between worktrees.
- Put `cd <your absolute worktree path> && ` in front of every git or gate command; the shell's working directory does not persist between tool calls. Run `git branch --show-current` before any commit.
- Gate runtime id: `claude-code`.
- `git add -A` before every commit.
- Do not start, stop, or restart any SciStudio dev app or backend process; the owner may be testing in one. The manager runs the live smoke test.

## Scope

You own only:

- frontend/src/panels/** (create): `PanelFrame`, the bridge, the per-context operations table
- src/scistudio/panels/sdk/** (create): the SDK at `src/scistudio/panels/sdk/1/scistudio-panel.js`, including sample mode, and its tests
- frontend/src/components/DataPreview.tsx, frontend/src/components/DataPreview.parts/**
- frontend/src/App.parts/InteractiveModals.tsx, frontend/src/App.parts/InteractiveModals.parts/**
- frontend/src/App.parts/ProjectWorkspace.tsx
- frontend/src/components/ActivityBar.tsx
- frontend/src/components/PreviewerPalette.tsx and frontend/src/components/PreviewerPalette.parts/** (you may rename them to PanelPalette; keep the tab's internal key `previewers` and the Learning Center target ids unchanged, FR-050)
- frontend/src/components/PanelPalette.tsx, frontend/src/components/PanelPalette.parts/** (create)
- frontend/src/components/promotion/**
- frontend/src/store/**
- frontend/src/types/api.ts, frontend/src/lib/api/**
- frontend tests next to the files above
- .workflow/records/2293-feat-2293-a2-frontend.json, .workflow/local/** (never commit local/)

You must not touch:

- src/** Python, tests/** Python, scripts/** (agent A1)
- src/scistudio/tutorials/** and frontend/src/components/LearningCenter.parts/** (owner decision: the tutorial stays unchanged)
- frontend/src/components/DataRouterModal.tsx, PairEditorModal.tsx, and the compiled core viewers' behaviour (Phase B)
- docs/** (the manager owns the spec; ADRs are `agent_editable: false`)
- desktop/**

If you need an out-of-scope path, stop and report back. Do not edit it.

## Coordination

- You are not alone in this codebase. Agent A1 builds the backend on `feat/2293-a1-backend` in parallel.
- **Contract source.** The HTTP contracts are FR-005, FR-009, FR-011, FR-012, FR-026, FR-053, and FR-054 of the spec. A1 commits the Pydantic request and response models first. All worktrees share one repository, so read them directly with `git log feat/2293-a1-backend` and `git show feat/2293-a1-backend:src/scistudio/panels/<file>`; no fetch is needed. Mirror them in `frontend/src/types/api.ts`. Until they exist, code against the spec and mock `apiFetch` in tests. Report any mismatch between the spec and A1's models to the manager instead of guessing.
- MUST work only on your assigned branch and worktree. Do not revert or overwrite other agents' work.
- Do NOT open a PR. The manager reviews your branch and merges it into `feat/2293-panels-phase-a`.
- MUST NOT merge any PR.

## TODO And Deferral Rule

Deferred work must be tracked in the repo: `TODO(#NNN): <reason>` citing an issue, ADR, spec, or follow-up ticket. Do not leave hidden V1, MVP, or later work.

Known deferred items:

- FR-049: the tutorial is not migrated (#2288). Its copy still says "Previewers tab"; that is the owner's decision.

## Work To Do

Follow spec §4.3, tasks T-010 to T-013 and T-020/T-021, plus the frontend halves of FR-050 to FR-054:

1. T-010: the SDK (FR-016, FR-017, FR-018, FR-034) as one dependency-free script, and sample mode (FR-046) both for a page opened directly and for the host's sample mount.
2. T-011: `PanelFrame` — frame attributes exactly `sandbox="allow-scripts"` and `referrerpolicy="no-referrer"` (FR-015), `MessageChannel` handoff in one `init` (FR-016), 10-second ready timeout and error card with remount (FR-035), navigation teardown (FR-029), disposal; the bridge and the per-context operations table (FR-019, FR-020, FR-021, FR-024).
3. T-012: preview mounting through one host component for the preview panel and the preview tab; `open` through the existing drill-down stack; maximize carrying the panel id and view state; Data-tree open and the type-change chip re-resolving; legacy loader and compiled viewers kept for legacy candidates (FR-036, FR-037, FR-039).
4. T-013: the interactive modal mounting panels resolved by id, `writeBack` mapped to `interactive_complete`, Cancel to `cancel_block`, the shadowing error with Cancel; `DynamicPanel` kept for `module_url` manifests (FR-022 to FR-024).
5. FR-050 to FR-054: the Panels tab (label, icon, cards with purpose lines, choice control only on preview cards and legacy previewer cards, stale-choices strip, reload, diagnostics), double-click opening a sample-mode preview tab, and Move to My Library on project-tier panel cards through the shared promotion machinery.

## Required Tests And Checks

- `frontend/src/panels/PanelFrame.test.tsx`, `frontend/src/panels/bridge.test.ts`, `frontend/src/components/DataPreview.parts/PreviewHost.test.tsx`, `frontend/src/components/PanelPalette.test.tsx`, modal tests, preview-tab tests, and SDK tests (including sample mode).
- Every existing frontend test keeps passing, or is updated with a stated reason when the tab rename changes what it asserts.
- Frontend lint, type check, and tests through `gate_record check`.
- Gate flow (from your worktree):
  1. `gate_record init --task-kind feature --persona implementer --runtime claude-code --branch feat/2293-a2-frontend --issue 2293 --base-ref feat/2293-panels-phase-a --owner-directive "<summary>" --include <each write-set path>`
  2. `gate_record plan` with docs and tests
  3. implement; `gate_record amend --reason ... --include <path>` before any scope addition
  4. `gate_record check --base feat/2293-panels-phase-a --head HEAD` until it passes. Do not run `finalize` and do not open a PR.
- Commits: Conventional Commits; trailers `Gate-Record: .workflow/records/2293-feat-2293-a2-frontend.json`, `Task-Kind: feature`, `Issue: #2293`, `Assisted-by: claude-code:<model>`.
- Docs: the spec is the manager's; record `--docs-na` with a rationale.
- Sentrux MCP is unavailable in this runtime; record that when asked.

## Output Required

Before reporting done, provide:

- The final branch SHA.
- Changed file paths.
- Tests and checks run, with results.
- Every place you had to assume a contract detail A1 had not committed yet.
- Any blocker or scope issue.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file.
- The task conflicts with AGENTS.md, ADR-054, the spec, or the gate record.
- A1's committed models contradict the spec.
- Checks fail for unclear reasons.
- You cannot add or update required tests.
```

---

## Manager Addenda Sent At Dispatch (2026-09-11)

Each agent received its prompt above with the relative worktree path replaced
by the absolute path under `C:/Users/jiazh/workspace/SciStudio/.worktrees/`,
followed by the addendum below, which overrides the prompt where they differ.

### A1 addendum

1. You run as a background agent and cannot send reports mid-run. The manager
   and A2 read your branch directly, so commit the contract models early and
   keep committing as you go; put everything you would have reported mid-run
   into your final report.
2. ADR-049 (T-009) does not stop the task. Finish everything else. The owner
   has not yet decided how ADR-049 gets the new contract ids, so a
   `check_package_contract_tables.py` / `full_audit` failure whose only cause
   is ADR-049 lacking the new contract ids is expected: do not work around it,
   do not edit ADR-049, and do not waive it; report it with the proposed text
   path. Every other check must pass.
3. Do not start, stop, or restart any SciStudio dev app, Electron window, or
   backend server process; the owner may be testing in one. Tests that spin up
   their own in-process app are fine.
4. Take the time the work needs. When the spec is ambiguous, choose the reading
   that follows ADR-054 and list the choice in the final report.

### A2 addendum

1. You run as a background agent and cannot send reports mid-run. Where A1's
   committed models contradict the spec, follow A1's models if they are a
   reasonable reading of the spec, otherwise follow the spec, and list every
   such case in the final report; the manager reconciles at integration.
2. Check `git log feat/2293-a1-backend` periodically (at least before writing
   `frontend/src/types/api.ts` and again before finishing) and align with the
   latest committed models.
3. The SDK's tests may live under `frontend/src/panels/` and import the SDK
   file by relative path, or next to the SDK; keep them runnable by the
   existing frontend test command so `gate_record check` exercises them.
4. Take the time the work needs. When the spec is ambiguous, choose the reading
   that follows ADR-054 and list the choice in the final report.

### A1 follow-up message (2026-09-11, after the owner's ADR-049 decision)

Sent to A1 while it was running. It replaces A1 addendum item 2 and the
ADR-049 part of Work To Do step 8.

1. Merge `feat/2293-panels-phase-a` (commit `92723cb94`, which adds
   `docs/adr/ADR-049-addendum1.md`) into `feat/2293-a1-backend`; the base ref is
   unchanged.
2. `tests/audit/**` joins A1's write set; amend the ledger before editing it.
3. Write `docs/planning/adr-049-package-validator/contracts/pv-a6-section-14-panels.json`
   with rows PV-14-001 to PV-14-008 exactly as the addendum's Section 2 table
   defines them (section `14_panel_contracts`, status `implemented`, alignment
   `aligned`), with code, test, and ADR evidence that exists.
4. Add `14_panel_contracts` to the schema's `section` enum.
5. Add a `notes` field to the PV-12-001 row scoping it to `FrontendManifest`
   modules.
6. Extend `check_adr_coverage` to search `docs/adr/ADR-049.md` plus every
   `docs/adr/ADR-049-addendum*.md`; an id named nowhere still fails.
7. Add `tests/audit/test_check_package_contract_tables.py` with tmp_path
   fixtures for both cases.
8. The expected checker result stays 0 errors and the nine warnings of ADR-049
   §4.1.
9. The proposed-text file is no longer needed; the contract-table check and
   full audit must pass once the addendum is merged.
