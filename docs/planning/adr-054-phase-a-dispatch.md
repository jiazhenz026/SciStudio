---
title: "ADR-054 Phase A Dispatch Prompts"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs: [54, 55]
language_source: en
---

# ADR-054 Phase A Dispatch Prompts

Filled from `docs/ai-developer/templates/agent-dispatch-prompt-template.md`.
Manager checklist and enterprise matrix are on `codex/2296-adr054-coordination`;
read them with `git show` if absent from the implementation branch.

## A1: Descriptor, discovery, routing, contexts, routes and interactive validation

[DISPATCH-TEMPLATE-V1: implementer]

### Task Identity

- Repository: SciStudio; owner request: implement ADR-054 Panels and MiniApps, with ADR-055 enterprise adaptation in A.
- Task kind: `feature`; persona: `implementer`; issue #2293, https://github.com/jiazhenz026/SciStudio/issues/2293.
- Umbrella PR: #2353 `[DO NOT MERGE]`; protected branch: `main`.
- Umbrella branch: `codex/2296-adr054-coordination`.
- Agent branch: `codex/2293-panel-backend`; worktree: `.worktrees/adr054-backend`.
- Gate record: `.workflow/records/2293-panel-backend.json` (create via CLI, slug `panel-backend`, base `origin/main`).
- Checklist: `docs/planning/adr-054-panels-checklist.md` on manager branch.

### Required Rules

Read AGENTS.md, common rules, gated-workflow, agent-dispatch, new-feature specific rule,
implementer persona and skill. Read issue #2293 but apply this session's newer owner
choice: A preserves sidebar entry; D performs MiniApps/All Previewers transition.
Read `docs/planning/adr-054-enterprise-contracts.md` from manager branch.

### Scope

You own only:

- `src/scistudio/panels/**` EXCEPT `sdk/**`, `lib/**`, and `security.py`.
- `src/scistudio/previewers/{models,registry,router,choices,project,session,assets}.py` and narrowly required helpers under `previewers/`, EXCEPT `data_access.py` and its new helper modules (A3).
- `src/scistudio/api/ws.py` only for new-panel context validation immediately before existing interactive-complete dispatch, and `tests/api/test_panel_interactive_ws.py` (manager amendment, 2026-09-11).
- `src/scistudio/api/routes/panels.py`, `src/scistudio/api/routes/data.py`, `src/scistudio/api/routes/blocks.py`, and panel-related API schemas.
- `src/scistudio/core/dropins.py` for tier roots only; record protected scope, do not claim the admin label is granted.
- `src/scistudio/blocks/base/interactive.py`, `src/scistudio/blocks/registry/_capability.py` and narrowly necessary block-registry discovery call sites.
- Panel validator modules and `scripts/audit/check_package_contract_tables.py` (do not weaken existing checks; request owner-controlled ADR changes separately).
- `pyproject.toml` only for panel asset packaging.
- `tests/panels/**` except security/read-extension tests A3 owns; `tests/api/test_panel_routes.py`, `test_panel_context_routes.py`, `test_panel_guard_contract.py`; affected previewer/block tests except `test_preview_data_access.py`.
- `docs/planning/adr-054-backend-notes.md` and your own gate ledger.

Everything outside your write set, other agents' gates/notes, governance and owner-controlled
ADRs/architecture is out of scope. Report a needed additional path BEFORE editing it.

### Coordination

You are not alone in this codebase. Work only in your assigned worktree and branch.
Do not overwrite others' work, install editable packages, change global environment, merge
PRs, or create a separate PR. Deliver focused commits with gate trailers for manager to
review and integrate into `codex/2293-panels-phase-a`; its final PR targets main and closes #2293.
Use `PYTHONPATH=src python` and isolated environments as needed. Manager owns checklist
updates; return row evidence in your report. Do not edit the shared manager worktree.
Send API coordination directly to sibling agents through collaboration tools and copy manager.
No nested agents unless manager explicitly assigns an independent subtask.

### TODO And Deferral Rule

Use tracked `TODO(#NNN)` with ADR/spec/issue references for every deferred item. No hidden
MVP/V1/later behavior. Known future scope: B core migrations, C full guides, D MiniApps;
0.6 legacy removal and notebook/sync tracked #2288. Do not defer A requirements silently.

### Work To Do

1. Read full ADR-054 and both specs, then implement Phase A T-001/2/3/5/6/8/9. Keep routing as one candidate set with the existing ADR-048 ladder, preserve both legacy paths through 0.5.x, and add diagnostics. The current descriptor mentions miniapp; validate its descriptor shape but never open miniapp contexts or run Python in A. Report any ambiguity.
2. Coordinate wire/API shapes directly with A2 and read API additions with A3 before building their consumers. Publish a concrete example create request/response, catalog/preview discriminator, read JSON/binary headers, error shape, close and token renewal contract early. Avoid a parallel routing system.
3. Contexts must be backend-owned, project-bound, authorize target/reachable children, reject stale project/ref use, verify interactive waiting state and tie writeback to the matching waiting block. Preserve engine/interactive event contracts. Reuse frozen preview target/session resolution rather than trusting browser type/ref metadata.
4. Register ONLY `/api/panels/t/` with existing `register_self_authenticating_prefix`. Assets/SDK/libs are independently token-authenticated, scoped, expiring, revocable; operations remain guarded. No Lab middleware. Use root-path aware URLs. File confinement must reject traversal, symlink escapes, Python source, and cross-panel token use. Coordinate A3 app registration via an explicit exported installer/router.
5. Implement all generic read operations, bounded flags and binary response handling using A3's read extensions. Resolve artifact.file securely, including cached plot artifacts; its data-bearing token must remain bound to authorized context data, never arbitrary filesystem paths. Reads run off the event loop.
6. Cover root and `/user/alice/scistudio` mounts with default and fake replacement guards, token revocation, lookalike/sibling prefixes and refusal of using static tokens on read/create/delete routes. Coordinate globally applied null-Origin checks with A3.
7. Record implementation budgets, API shapes and traceability in backend notes. Test packaging includes SDK/library files supplied by A2. Report any required protected/public-surface/ADR frontmatter changes to manager; do not silently omit them.

### Required Tests And Checks

Add tests for behavior. Initialize/plan/amend the gate before editing. Use `gate_record check`
for tier-selected checks, narrowed to your delta. Include your implementation notes as docs
landing; do not claim generated docs, browser smoke, Sentrux Pro or CI you have not run.
Sentrux MCP unavailable here; CLI fallback is gate-selected when needed. Before final delivery,
run gate local checks and report failures with concrete logs under ignored `.workflow/local`.
Manager owns integrated `check --mode pre-pr`, `finalize`, gate-aware PR wrapper, post-PR
provenance and CI; no separate agent PR/finalize is required. A failure due solely to a sibling's
not-yet-integrated artifact must be recorded precisely, not bypassed with a stub.

### Output Required

Changed paths, focused commit IDs, tests/checks/results, your notes path, checklist evidence,
API decisions, unresolved blockers and scope requests. Keep working until the bounded assignment
is implemented and tested; do not stop at an analysis report.

### Stop Conditions

Report before editing outside scope, on an unresolved contract conflict, unclear gate failure,
missing essential test support, or an integration dependency. Do independent in-scope work
while waiting for clarification. Never weaken tests, policies or CI to make a check green.

## A2: SDK, local libraries, sandbox host, preview and interactive integration

[DISPATCH-TEMPLATE-V1: implementer]

### Task Identity

- Repository: SciStudio; owner request: implement ADR-054 Panels and MiniApps, with ADR-055 enterprise adaptation in A.
- Task kind: `feature`; persona: `implementer`; issue #2293, https://github.com/jiazhenz026/SciStudio/issues/2293.
- Umbrella PR: #2353 `[DO NOT MERGE]`; protected branch: `main`.
- Umbrella branch: `codex/2296-adr054-coordination`.
- Agent branch: `codex/2293-panel-frontend`; worktree: `.worktrees/adr054-frontend`.
- Gate record: `.workflow/records/2293-panel-frontend.json` (create via CLI, slug `panel-frontend`, base `origin/main`).
- Checklist: `docs/planning/adr-054-panels-checklist.md` on manager branch.

### Required Rules

Read AGENTS.md, common rules, gated-workflow, agent-dispatch, new-feature specific rule,
implementer persona and skill. Read issue #2293 but apply this session's newer owner
choice: A preserves sidebar entry; D performs MiniApps/All Previewers transition.
Read `docs/planning/adr-054-enterprise-contracts.md` from manager branch.

### Scope

You own only:

- `frontend/src/panels/**` and panel integration in `frontend/src/components/DataPreview*`, `frontend/src/components/DataPreview.parts/**`, `frontend/src/App.parts/InteractiveModals*`, its parts, `frontend/src/App.parts/ProjectWorkspace.tsx`, `frontend/src/store/**`, `frontend/src/types/api.ts`, `frontend/src/lib/api/` for a new panels client and minimal exports, `frontend/src/components/PreviewerPalette*` for catalog display only.
- Minimal call-site wiring in `frontend/src/App.tsx` and related preview props when necessary; do not change unrelated layout semantics.
- `src/scistudio/panels/sdk/**`, `src/scistudio/panels/lib/**` including real pinned library assets, licenses and digest index.
- Tests adjacent to these frontend surfaces and SDK tests.
- `docs/planning/adr-054-frontend-notes.md` and your gate ledger.

Everything outside your write set, other agents' gates/notes, governance and owner-controlled
ADRs/architecture is out of scope. Report a needed additional path BEFORE editing it.

### Coordination

You are not alone in this codebase. Work only in your assigned worktree and branch.
Do not overwrite others' work, install editable packages, change global environment, merge
PRs, or create a separate PR. Deliver focused commits with gate trailers for manager to
review and integrate into `codex/2293-panels-phase-a`; its final PR targets main and closes #2293.
Use `PYTHONPATH=src python` and isolated environments as needed. Manager owns checklist
updates; return row evidence in your report. Do not edit the shared manager worktree.
Send API coordination directly to sibling agents through collaboration tools and copy manager.
No nested agents unless manager explicitly assigns an independent subtask.

### TODO And Deferral Rule

Use tracked `TODO(#NNN)` with ADR/spec/issue references for every deferred item. No hidden
MVP/V1/later behavior. Known future scope: B core migrations, C full guides, D MiniApps;
0.6 legacy removal and notebook/sync tracked #2288. Do not defer A requirements silently.

### Work To Do

1. Read ADR-054, panel spec T-010/11/12/13, FR-046 sample mode, and relevant ADR-055 prefix/presentation and enterprise contracts. Ask A1 for wire examples immediately; agree create/catalog/preview discriminator, read binary headers, error and renewal shapes before integration.
2. Implement a reusable PanelFrame, dependency-free SDK and channel bridge: sandbox exactly allow-scripts, no-referrer, one MessageChannel transfer to the intended frame, ready timeout, port-only responses, validation of operations and messages, explicit errors/remount/fallback, navigation teardown, close/revoke on unmount, viewState and theme tokens. Preview/interactive never define or perform call/sync.
3. Use the same host for preview and main-stage preview tabs; retain frozen target/id/view state on maximize, dedup/drop rule, drill-down child authorization and stack/back, Data-tree open and type-change resolution. Keep existing legacy modules and compiled viewers with deprecation warnings.
4. Integrate interactive panel IDs with the existing prompt, writeback/complete and cancel flow and memory toggle. Do not change the engine event contract or remove built-in modals (Phase B).
5. Owner decision: preserve the existing sidebar entry in A. Display panel candidates/diagnostics in the current Previewers list, but do NOT add an interim Panels tab, new icon, directory promotion, or MiniApp UI. D handles MiniApps/All Previewers.
6. Use apiFetch/apiUrl and the existing base-path source; no hardcoded server origin or missing/double prefix. Save panel-generated bytes only via explicit native user selection or browser download, enforce 100 MiB default limit, preserve enterprise/local path distinction. Respect AI presentation without requiring a right column. Avoid enterprise capability definitions, Toolbar/BottomPanel enterprise surfaces, and broad api/data.ts changes that overlap PR #2336.
7. Ship real pinned Plotly (existing frontend version), D3, three.js and PDF.js library assets with licenses and SHA-256 index per FR-032; retain policy documented. Inspect primary package metadata/documentation for versions/files, no placeholder library files. Coordinate static file/layout with A1 and packaging.
8. Add meaningful tests for port isolation, unsupported calls, disposal races, transfer buffers, ready/error/navigation handling, prefix requests, host flows, theme updates, save limits and SDK standalone panel.sample.json. Record usable frontend/browser smoke instructions for manager.

### Required Tests And Checks

Add tests for behavior. Initialize/plan/amend the gate before editing. Use `gate_record check`
for tier-selected checks, narrowed to your delta. Include your implementation notes as docs
landing; do not claim generated docs, browser smoke, Sentrux Pro or CI you have not run.
Sentrux MCP unavailable here; CLI fallback is gate-selected when needed. Before final delivery,
run gate local checks and report failures with concrete logs under ignored `.workflow/local`.
Manager owns integrated `check --mode pre-pr`, `finalize`, gate-aware PR wrapper, post-PR
provenance and CI; no separate agent PR/finalize is required. A failure due solely to a sibling's
not-yet-integrated artifact must be recorded precisely, not bypassed with a stub.

### Output Required

Changed paths, focused commit IDs, tests/checks/results, your notes path, checklist evidence,
API decisions, unresolved blockers and scope requests. Keep working until the bounded assignment
is implemented and tested; do not stop at an analysis report.

### Stop Conditions

Report before editing outside scope, on an unresolved contract conflict, unclear gate failure,
missing essential test support, or an integration dependency. Do independent in-scope work
while waiting for clarification. Never weaken tests, policies or CI to make a check green.

## A3: Bounded read extensions and global security/app integration

[DISPATCH-TEMPLATE-V1: implementer]

### Task Identity

- Repository: SciStudio; owner request: implement ADR-054 Panels and MiniApps, with ADR-055 enterprise adaptation in A.
- Task kind: `feature`; persona: `implementer`; issue #2293, https://github.com/jiazhenz026/SciStudio/issues/2293.
- Umbrella PR: #2353 `[DO NOT MERGE]`; protected branch: `main`.
- Umbrella branch: `codex/2296-adr054-coordination`.
- Agent branch: `codex/2293-panel-security`; worktree: `.worktrees/adr054-security`.
- Gate record: `.workflow/records/2293-panel-security.json` (create via CLI, slug `panel-security`, base `origin/main`).
- Checklist: `docs/planning/adr-054-panels-checklist.md` on manager branch.

### Required Rules

Read AGENTS.md, common rules, gated-workflow, agent-dispatch, new-feature specific rule,
implementer persona and skill. Read issue #2293 but apply this session's newer owner
choice: A preserves sidebar entry; D performs MiniApps/All Previewers transition.
Read `docs/planning/adr-054-enterprise-contracts.md` from manager branch.

### Scope

You own only:

- `src/scistudio/previewers/data_access.py` and new narrowly scoped read helper modules beside it (tell A1 exact names first).
- `src/scistudio/panels/security.py` only under panels; A1 owns the rest of its Python.
- `src/scistudio/api/app.py` for panel router/lifecycle mounting and security middleware/startup CORS checks only.
- `tests/previewers/test_preview_data_access.py` and new `tests/previewers/test_panel_read_extensions.py`; `tests/api/test_panel_security.py` and relevant minimal `tests/api/test_app.py` additions.
- `CHANGELOG.md` for combined Phase A additions/hardening (coordinate input from A1/A2).
- `docs/planning/adr-054-security-notes.md` and your gate ledger.

Everything outside your write set, other agents' gates/notes, governance and owner-controlled
ADRs/architecture is out of scope. Report a needed additional path BEFORE editing it.

### Coordination

You are not alone in this codebase. Work only in your assigned worktree and branch.
Do not overwrite others' work, install editable packages, change global environment, merge
PRs, or create a separate PR. Deliver focused commits with gate trailers for manager to
review and integrate into `codex/2293-panels-phase-a`; its final PR targets main and closes #2293.
Use `PYTHONPATH=src python` and isolated environments as needed. Manager owns checklist
updates; return row evidence in your report. Do not edit the shared manager worktree.
Send API coordination directly to sibling agents through collaboration tools and copy manager.
No nested agents unless manager explicitly assigns an independent subtask.

### TODO And Deferral Rule

Use tracked `TODO(#NNN)` with ADR/spec/issue references for every deferred item. No hidden
MVP/V1/later behavior. Known future scope: B core migrations, C full guides, D MiniApps;
0.6 legacy removal and notebook/sync tracked #2288. Do not defer A requirements silently.

### Work To Do

1. Read ADR-054 FR-014, FR-030/31 and read shapes/budgets, the identity seam/prefix/enterprise specs, plus existing data_access consumers. Implement bounded decimation, text offsets/next offsets, collection cursors, artifact access beyond inline size, little-endian numeric binary data. Preserve legacy default behavior and existing public signatures compatibly; new options must not silently truncate existing provider/export uses.
2. Send A1 exact proposed method signatures/result fields early. Use small helpers, avoid loading full large arrays/text/collections merely to select a bounded region. Respect source dtype/shape, nonfinite values, indexing and full-plane extrema requirements. Ensure JSON flags and binary metadata are consistent; add tests that prove storage is sliced and bounds are enforced.
3. Implement opaque-Origin refusal for every HTTP POST/PUT/PATCH/DELETE including edition routers, guarded routes and token routes. Preserve ordinary same-origin and no-Origin requests. Reject SCISTUDIO_CORS_ORIGINS entries `*` and `null` at startup with a useful error. Do not break self-auth static GET/OPTIONS modules and fonts. Coordinate middleware order and static headers with A1.
4. Integrate A1's explicit router/lifespan installer into create_app, ensuring cleanup and prefix handling. Preserve existing create_app guard/lifespan/capability API and no-argument default behavior apart from mandated CORS/null-Origin hardening. No new Lab/session middleware; no edits to seam.py. PR #2336 currently changes app lifespan and capability policy: keep edits narrow for manager hunk reconciliation.
5. Test both mount prefixes and fake replacement guard including custom edition routes, CORS headers and current API/identity seam regressions. Record exact checks and any dependency on A1 imports rather than adding placeholder stubs.
6. Add changelog entries for public-read additions and global security changes. Coordinate any generated reference or ADR-052 snapshot needs with manager; do not edit owner-controlled architecture/governance or weaken gate checks.

### Required Tests And Checks

Add tests for behavior. Initialize/plan/amend the gate before editing. Use `gate_record check`
for tier-selected checks, narrowed to your delta. Include your implementation notes as docs
landing; do not claim generated docs, browser smoke, Sentrux Pro or CI you have not run.
Sentrux MCP unavailable here; CLI fallback is gate-selected when needed. Before final delivery,
run gate local checks and report failures with concrete logs under ignored `.workflow/local`.
Manager owns integrated `check --mode pre-pr`, `finalize`, gate-aware PR wrapper, post-PR
provenance and CI; no separate agent PR/finalize is required. A failure due solely to a sibling's
not-yet-integrated artifact must be recorded precisely, not bypassed with a stub.

### Output Required

Changed paths, focused commit IDs, tests/checks/results, your notes path, checklist evidence,
API decisions, unresolved blockers and scope requests. Keep working until the bounded assignment
is implemented and tested; do not stop at an analysis report.

### Stop Conditions

Report before editing outside scope, on an unresolved contract conflict, unclear gate failure,
missing essential test support, or an integration dependency. Do independent in-scope work
while waiting for clarification. Never weaken tests, policies or CI to make a check green.
