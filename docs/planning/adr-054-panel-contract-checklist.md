---
title: "ADR-054 Panel Contract Agent Dispatch Checklist"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 48
  - 51
  - 54
language_source: en
---

# ADR-054 Panel Contract Agent Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: `Own the whole implementation of ADR-054 spec 1 (the panel
  contract), dispatch agents including a no-context audit and an adversarial
  no-context test engineer that proves previewer behaviour survives the
  migration, and deliver one PR.`
- Task kind: `manager`
- Manager persona: `manager`
- Issue: `#2229`
- Gate record: `.workflow/records/2229-track-adr-054-spec1-panel-contract.json`
- Branch/worktree plan: manager on `track/adr-054-spec1-panel-contract` in
  `.worktrees/mgr-2229-panel-contract`; every dispatched agent branches from the
  track branch into its own worktree and pushes its branch for manager
  integration.
- Protected branch: `main`
- Umbrella branch: `track/adr-054-spec1-panel-contract`
- Umbrella PR: `#2230`
- Umbrella PR title: `[DO NOT MERGE] ADR-054 spec 1: the unified panel contract`
- Final PR target: `main`
- Governing spec: `docs/specs/adr-054-panel-contract.md`
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context:
    `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context:
    `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`

## 2. Scope

- In scope: everything in the spec's `scope.in` and `governs.files`, delivered
  through its section 4.3 sequence T-001 to T-016.
  - `src/scistudio/core/panels.py`, `src/scistudio/panels/**`
    (renamed from `src/scistudio/previewers/**`)
  - `src/scistudio/api/routes/panels.py`, `routes/data.py`, `routes/blocks.py`,
    `api/schemas.py`
  - `src/scistudio/blocks/base/interactive.py`, `src/scistudio/core/dropins.py`,
    `src/scistudio/core/entry_points.py`
  - `frontend/src/panels/**` and the previewer/panel surfaces it replaces
  - `tests/panels/**` (renamed from `tests/previewers/**`), the panel tests
    under `tests/api/**`, `tests/architecture/test_layer_deps.py`,
    `tests/adr052_contract/**`
  - `docs/adr/ADR-048-addendum*.md`, `docs/adr/ADR-051-addendum2.md`
  - `docs/planning/adr-054-panel-contract-checklist.md`, `docs/audit/**`
- Out of scope (spec `scope.out` and `governs.excludes`):
  - The explore session, the kernel, the notebook, the dependency analysis.
  - `src/scistudio/_skills/**`, `src/scistudio/_agent_reference/**`.
  - `docs/architecture/**`, `docs/package-development/**`, `docs/user/**`
    (human documentation revision is `#2211`).
  - `src/scistudio/plot/runtime.py`; plot rendering, the preview cache, plot
    artifact registration.
  - Giving a plot panel the producing capability (`#2212`).
- Protected paths: `docs/architecture/ARCHITECTURE.md` is owner-controlled and
  is not edited by this dispatch. `#2059` and `#2211` own the architecture and
  user-documentation follow-through.
- Deferred work:
  - `TODO(#2212)` the plot panel's producing capability.
  - `TODO(#2211)` human documentation revision for the panel vocabulary.

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

- [x] Dedicated manager branch and worktree created.
      -> `track/adr-054-spec1-panel-contract`,
      `.worktrees/mgr-2229-panel-contract`
- [x] Existing issue linked, or new issue created only if none exists.
      -> `#2213` is the closed spec-authoring issue and `#2209` tracks the ADR
      as a whole and states each stage lands against its own issue, so `#2229`
      was created for this stage.
- [x] Gate record started.
      -> `.workflow/records/2229-track-adr-054-spec1-panel-contract.json`
- [x] Scope include/exclude recorded in the gate record.
- [x] Umbrella branch created.
- [x] Umbrella PR opened. -> `#2230`
- [x] Umbrella PR title includes `[DO NOT MERGE]`.
- [x] Protected branch and umbrella PR number recorded in this checklist.
- [x] No `pip install -e .` environment pollution found.
      -> no agent is permitted to run it; every prompt restates the prohibition.
- [x] Dispatch checklist copied from the template and committed.
- [x] Dispatch prompts created from the correct prompt template and linked
      below.
- [x] Sentrux baseline recorded, or N/A reason recorded.
      -> N/A: Sentrux is not installed in this environment (no `sentrux` on PATH,
      no Python package; only `.sentrux/rules.toml` is present). Recorded for
      every agent in the prompt file rather than per agent.

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `N/A`
- Owner authorization source: `N/A`
- Reason: `No bypass was requested or used.`

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scistudio.qa.governance.gate_record check --mode pre-commit` | `N/A` | `[ ]` | `no commit hook installed since #2150` |
| Commit message | `python -m scistudio.qa.governance.gate_record check --mode commit-msg` | `N/A` | `[ ]` | `subject check runs at pre-pr/ci since #2150` |
| Pre-push | `python -m scistudio.qa.governance.gate_record check --mode pre-push` | `N/A` | `[ ]` | `installed hook is a fast allow shim` |
| Pre-PR reconcile | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `N/A` | `[ ]` | `pending` |

## 5.1 Docs Impact Check

- Wrapper/hook/gate-record/receipt/CI/runtime behavior changed: `no`
- AI docs checked:
  `docs/ai-developer/rules.md`,
  `docs/ai-developer/specific_rules/gated-workflow.md`,
  `docs/ai-developer/specific_rules/agent-dispatch.md`,
  `docs/ai-developer/templates/*dispatch*.md`
- Updated docs or N/A rationale: `N/A - this dispatch changes the panel
  subsystem, not the gate CLI, the PR wrapper, the hooks, CI, or any AI runtime
  behaviour, so no AI developer workflow doc changes are required.`

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| `W1-rename` | `implementer` | `N/A` | `adr-054-panel-contract-prompts.md#w1-rename` | T-001 and FR-051 | `refactor/2229-panel-rename` | `.worktrees/w1-panel-rename` | the whole tree, mechanical rename only | any behaviour change | `#2229` | `[x]` |
| `W2-core` | `implementer` | `N/A` | `adr-054-panel-contract-prompts.md#w2-core` | T-002, T-003, T-013, T-015, T-016 | `feat/2229-panel-core-contract` | `.worktrees/w2-panel-core` | `src/scistudio/core/panels.py`, `src/scistudio/panels/**`, `src/scistudio/core/dropins.py`, `src/scistudio/core/entry_points.py`, `src/scistudio/blocks/base/interactive.py`, `tests/panels/**`, `tests/architecture/**`, `tests/adr052_contract/**` | frontend, API routes | `#2229` | `[~]` re-dispatched |
| `W2-host` | `implementer` | `N/A` | `adr-054-panel-contract-prompts.md#w2-host` | T-005, T-006 | `feat/2229-panel-frame-host` | `.worktrees/w2-panel-host` | `frontend/src/panels/**` | backend, the existing previewer frontend | `#2229` | `[x]` `c4cf38715` |
| `W3-api` | `implementer` | `N/A` | `adr-054-panel-contract-prompts.md#w3-api` | T-004, T-008 backend half, T-010 | `feat/2229-panel-api` | `.worktrees/w3-panel-api` | `src/scistudio/api/routes/panels.py`, `routes/data.py`, `routes/blocks.py`, `api/schemas.py`, `tests/api/**` | frontend, panel discovery internals | `#2229` | `[ ]` |
| `W3-fe` | `implementer` | `N/A` | `adr-054-panel-contract-prompts.md#w3-fe` | T-007, T-008 frontend half, T-011 | `feat/2229-panel-frontend` | `.worktrees/w3-panel-frontend` | the panel surfaces under `frontend/src/**` | backend | `#2229` | `[ ]` |
| `W4-builtin` | `implementer` | `N/A` | `adr-054-panel-contract-prompts.md#w4-builtin` | T-009 | `feat/2229-builtin-panels` | `.worktrees/w4-builtin-panels` | the built-in panel directories and their tests | the Python providers, the host | `#2229` | `[x]` merged |
| `W4-compat` | `implementer` | `N/A` | `adr-054-panel-contract-prompts.md#w4-compat` | T-012, T-014 | `feat/2229-panel-compat-shim` | `.worktrees/w4-panel-compat` | the shim module, `docs/adr/ADR-048-addendum*.md`, `docs/adr/ADR-051-addendum2.md`, the shim tests | everything else | `#2229` | `[~]` T-014 dispatched on `docs/2229-panel-addenda`; T-012 waits on T-007 |
| `W5-test` | `test_engineer` | `N/A` | `adr-054-panel-contract-prompts.md#w5-test` | adversarial migration-regression suite | `test/2229-panel-migration-regression` | `.worktrees/w5-panel-tests` | tests, fixtures, e2e evidence only | all production code | `#2229` | `[ ]` |
| `W5-audit-nc` | `audit_reviewer` | `no-context` | `adr-054-panel-contract-prompts.md#w5-audit-nc` | independent conformance audit | `audit/2229-panel-no-context` | `.worktrees/w5-audit-no-context` | `docs/audit/2026-09-02-panel-contract-no-context.md` | all implementation files | `#2229` | `[ ]` |
| `W5-audit-wc` | `audit_reviewer` | `with-context` | `adr-054-panel-contract-prompts.md#w5-audit-wc` | spec conformance audit | `audit/2229-panel-with-context` | `.worktrees/w5-audit-with-context` | `docs/audit/2026-09-02-panel-contract-with-context.md` | all implementation files | `#2229` | `[ ]` |
| `W4-emission` | `implementer` | `N/A` | `adr-054-panel-contract-prompts.md#w4-emission` | the owner-directed scope expansion: the interactive-block context settles a produced value, and a paused block's prompt carries a mountable descriptor | `feat/2229-panel-emission-consumer` | `.worktrees/w4-panel-integrate` | `blocks/base/interactive.py`, `engine/scheduler/_dispatch.py`, `App.parts/InteractiveModals*`, their tests | the panel subsystem, the API routes, the built-in documents | `#2229` | `[x]` merged |
| `W4-tutorial` | `implementer` | `N/A` | `adr-054-panel-contract-prompts.md#w4-tutorial` | migrate the tutorial `review_labels` panel off the retired module form | `feat/2229-tutorial-panel-migration` | `.worktrees/w4-tutorial-panel` | `tutorials/core/what-is-a-type/assets/**`, `tests/tutorials/test_core_tutorial_what_is_a_type.py`, `tutorialReviewPanel.test.ts` | every other tutorial, all production panel code | `#2229` | `[x]` merged |
| `W6-security` | `implementer` | `N/A` | `adr-054-panel-contract-prompts.md#w6-security` | fix the no-context audit's P1 and security findings | `fix/2229-panel-audit-p1` | `.worktrees/w6-security-fix` | `panels/providers.py`, `blocks/base/interactive.py`, `api/routes/panels.py`, `api/app.py`, their tests | the built-in documents, the alias package | `#2229` | `[~]` |
| `W6-compat` | `implementer` | `N/A` | `adr-054-panel-contract-prompts.md#w6-compat` | fix the unmigrated author surface the adversarial test engineer proved broken | `fix/2229-unmigrated-author-surface` | `.worktrees/w6-compat-fix` | `previewers/**`, `panels/models.py`, `panels/choices.py`, `tests/panels/**` | the security agent's files, the editing agent's files | `#2229` | `[~]` |
| `W6-editing` | `implementer` | `N/A` | `adr-054-panel-contract-prompts.md#w6-editing` | fix the with-context audit's two P1s: the discarded save, and T-010's missing host half | `fix/2229-panel-editing-host` | `.worktrees/w6-editing-fix` | `panels/compat.py`, `frontend/src/panels/PanelErrorSurface.tsx`, the panel editing surface, their tests | the other two fix agents' files | `#2229` | `[~]` |

For `test_engineer` rows, the write set should default to tests, fixtures,
validation scripts, e2e scenarios, audit evidence, and explicitly assigned
QA/governance tooling. Production code paths require a recorded scope
amendment.

## 7. Track: The Panel Contract

### 7.1 Track Scope

- Owner: `manager`
- In scope: the sixteen tasks of `docs/specs/adr-054-panel-contract.md`
  section 4.3.
- Out of scope: everything listed in section 2 above.
- Required docs:
  - `docs/adr/ADR-048-addendum*.md` (the contract change, the governance
    transfer, and the shim's removal condition, FR-044)
  - `docs/adr/ADR-051-addendum2.md` (the panel-side half of the same change)
  - this checklist
  - the audit reports under `docs/audit/`
- Required tests: the spec's `tests:` list, in particular
  `tests/panels/test_panel_contract.py`,
  `tests/panels/test_panel_capability_gate.py`,
  `tests/panels/test_panel_tiers.py`,
  `tests/panels/test_panel_editing.py`,
  `tests/panels/test_panel_asset_route.py`,
  `tests/panels/test_builtin_panels.py`,
  `tests/panels/test_compat_shim.py`,
  `tests/panels/test_panel_registration.py`,
  `tests/panels/test_panel_resolution.py`.

### 7.2 Dispatch

- [ ] Prompt file created or dispatch prompt recorded.
- [ ] Correct prompt template selected.
- [ ] Audit mode recorded when persona is `audit_reviewer`.
- [ ] Agent branch/worktree assigned.
- [ ] Write set and out-of-scope paths included in prompt.
- [ ] TODO rule included in prompt.
- [ ] Required checks included in prompt.

### 7.3 Implementation

| Task | Title | Agent | Status | Artifact |
|---|---|---|---|---|
| T-001 | Rename the subsystem and its vocabulary | `W1-rename` | `[x]` | branch `refactor/2229-panel-rename`; gate ledger `.workflow/records/2229-refactor-2229-panel-rename.json`; `pytest tests/panels tests/api/test_panels.py tests/api/test_panel_discovery.py tests/api/test_panel_choice_routes.py tests/api/test_interactive_panels.py tests/architecture tests/adr052_contract tests/blocks` 2312 tests, 40 pre-existing `openpyxl` env failures (baseline 2304/41); `npm test` 1884 tests; `lint-imports` 13 kept 0 broken |
| T-002 | Move the contract into the core layer | `W2-core` | `[x]` | `feat/2229-panel-core-contract`; `src/scistudio/core/panels.py`; one `PANEL_API_VERSION` in the tree, pinned by an AST walk over `src/**/*.py` |
| T-003 | The on-disk panel form and four-tier discovery | `W2-core` | `[x]` | `feat/2229-panel-core-contract`; `discovery.py`; `tests/panels/test_panel_tiers.py` |
| T-004 | Merge the asset route | `W3-api` | `[x]` | `feat/2229-panel-api`; one confinement check across four tier roots; traversal, encoded traversal, symlink, oversized and traversal-shaped-id cases per root |
| T-005 | The frame host and the message contract | `W2-host` | `[x]` | `c4cf38715`; `frontend/src/panels/{panelMessages,panelFrame,panelDescriptor,PanelHost,PanelErrorSurface}`; 112 tests in `vitest run src/panels` |
| T-006 | The capability gate in the host | `W2-host` | `[x]` | `c4cf38715`; `frontend/src/panels/panelCapability.ts` + `panelCapability.test.ts`; SC-007 asserted from the host's side |
| T-007 | One loader; delete the retired modules | `W3-fe` | `[x]` | `feat/2229-panel-frontend`; both loaders, both host APIs, coreViewers, PlotViewer and TableViewer deleted; zero frontend version literals (manager-verified post-merge) |
| T-008 | The backend names the fallback; delete the dispatch | `W3-api`, `W3-fe` | `[x]` | envelope carries `panel` and `fallback_panel` as full descriptors; `CoreFallbackRenderer` deleted |
| T-009 | Rewrite the eleven built-in panels | `W4-builtin` | `[x]` | `feat/2229-builtin-panels` merged; 11 panel directories under `src/scistudio/panels/builtin/`; `tests/panels/test_builtin_panels.py` 225 tests; all eleven proven to answer the handshake and render inside real headless Chromium under `sandbox="allow-scripts"`; wheel verified to ship all 22 files |
| T-010 | Read, write, copy-on-write, revert | `W3-api`, `W6-editing` | `[~]` | Backend on `feat/2229-panel-api`; write path confined and tested against a forged manifest discovery would have rejected. **The manager marked this done on backend evidence alone**: D-020 named `W3-fe` as the consumer, but `W3-fe`'s task list was T-007/T-008fe/T-011, so nobody owned the host half and FR-024/025/028/029 were unreachable from the interface. Found by the with-context audit; being built on `fix/2229-panel-editing-host` |
| T-011 | Hot reload and the optional state hook | `W3-fe` | `[x]` | `feat/2229-panel-frontend` + the `.html` allowlist entry from `W3-api`, without which a panel document's change emitted no event at all |
| T-012 | The compatibility shim | `W4-compat` | `[x]` | `feat/2229-panel-compat-shim`; wrapped on the backend so no second frontend mount path exists; SC-009 proven from the host's side with a real `emit` from the frame's own window |
| T-013 | Layer enumeration and frozen symbol inventory | `W2-core` | `[x]` | `feat/2229-panel-core-contract`; moved symbols keep provisional/0.3.1, new ones are provisional/0.3.4 with the derivation stated |
| T-014 | The ADR-048 and ADR-051 addenda | `W4-compat` | `[x]` | `docs/2229-panel-addenda` merged; removal condition stated in three inspectable clauses |
| T-015 | Entry-point group, directory registration, provider | `W2-core` | `[x]` | `feat/2229-panel-core-contract`; `tests/panels/test_panel_registration.py`. **The provider resolution shipped with a P1 path escape**, found by the no-context audit and fixed on `fix/2229-panel-audit-p1` |
| T-016 | Capability-aware resolution and the user choice | `W2-core` | `[x]` | `feat/2229-panel-core-contract`; `tests/panels/test_panel_resolution.py`. The choice ladder shipped implemented twice; deduplicated on `fix/2229-unmigrated-author-surface` |

### 7.4 Audit

- [ ] Audit agent assigned, or manager audit completed.
- [ ] Audit report file path assigned.
- [ ] Audit report committed.
- [ ] Audit report merged into final PR evidence path.
- [ ] Findings recorded.
- [ ] P1 findings fixed before integration.
- [ ] P2/P3 findings fixed or tracked with owner-approved rationale.

### 7.5 Integration

- [ ] Agent output reviewed by manager.
- [ ] Scope compliance verified.
- [ ] Conflicts resolved intentionally.
- [ ] Track merged or integrated.

## 8. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Baseline before the migration | `pytest tests/previewers tests/api/test_previewers.py tests/api/test_previewer_discovery.py tests/api/test_interactive_panels.py tests/architecture tests/adr052_contract -q --no-cov -p no:randomly` | `[x]` | exit 0 on `cae11210c`, the track branch's base |
| Gate ledger check (local) | `python -m scistudio.qa.governance.gate_record check --mode local --base origin/main --head HEAD` | `[ ]` | |
| Targeted tests | `pytest tests/panels tests/api tests/architecture tests/adr052_contract` and `npm test` in `frontend/` | `[ ]` | |
| Gate ledger check (pre-PR) | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `[ ]` | |
| Gate finalize (pre-PR) | `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#2229"` | `[ ]` | |
| Wrapper preflight | `python scripts/scistudio_pr_create.py --dry-run --title "<title>" --body "<body>"` | `[ ]` | |

## 9. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| `2026-09-02` | `manager` | none yet | dispatch opened | `N/A` |
| `2026-09-02` | `manager` | the rename's blast radius reaches the generated API reference under `src/scistudio/_user_guide/api-reference/**`, which my first prompt excluded | amended `W1-rename`'s scope: regenerate with `scripts/docs/build_reference.py`, never hand-edit; gate record amended | `N/A` |
| `2026-09-02` | `manager` | the rename's blast radius reaches the import-linter contracts in `pyproject.toml` that CI's Import Contracts job runs | amended `W1-rename`'s scope to include `pyproject.toml`; asked it to confirm `lint-imports` passes | `N/A` |
| `2026-09-02` | `manager` | `scripts/audit/check_package_contract_tables.py` maps the renamed symbols into `docs/package-development/**`, which the spec excludes | verified nothing in CI, `src/scistudio/qa/`, or `tests/` invokes that script, so it cannot fail the build; `W1-rename` told to report staleness rather than fix it | follow-up issue if `W1-rename` reports staleness |
| `2026-09-02` | `W2-host` | `full_audit` raises an error-severity finding as soon as a `planned_governs.files` entry starts to exist; `W2-host` correctly refused to edit `docs/specs/**` to fix it | recorded as manager decision D-014: the manager migrates all four `planned_governs` entries to `governs` once at integration, when they all resolve; no agent edits the spec | `N/A` |
| `2026-09-02` | `W2-host` | the message contract needed three additions D-011 did not name: `init.restored_state`, a nullable `error.request_id`, and `accepted_api_version` + `read_limits` on the descriptor | accepted and recorded as D-016; the backend agents conform to them | `N/A` |
| `2026-09-02` | `W2-host` | Sentrux is unavailable in this environment (not on PATH, not installed, only `.sentrux/rules.toml` present) | recorded once in the prompt file for every agent in this dispatch rather than rediscovered per agent | `N/A` |
| `2026-09-02` | `W2-host` | agents left their own checklist rows blank to avoid a four-way merge conflict on this file | accepted; the manager owns every checklist row and fills them from agent reports | `N/A` |
| `2026-09-03` | `W1-rename` | the rename moved every previewer symbol out from under governance claims in ADR-049, ADR-052, ADR-053 and the ADR-049 implementation spec: 28 error-severity `full_audit` findings against a baseline of zero; `W1-rename` correctly refused to edit out-of-scope governance documents | manager retargeted every claim at the renamed symbol, migrated this spec's own `governs` block, and moved the three resolving `planned_governs` entries into `governs`; `full_audit` back to zero error findings at `23e6f6ff3`; gate record amended with `--governance-touch true` | `N/A` |
| `2026-09-03` | `W1-rename` | `guard.core_change_guard` fails: the rename touches protected-core paths (`blocks/base/interactive.py`, `blocks/registry/__init__.py`, `blocks/registry/_scan.py`, `core/dropins.py`, `core/entry_points.py`) | those paths are in the spec's own `governs.files`, so the change is authorised by the approved spec but still needs the label; the manager requests `admin-approved:core-change` from the owner before the final PR | owner label on the final PR |
| `2026-09-03` | `W1-rename` | `docs/user/reference/*.md` is generated by the same script as the in-package API reference and still names `scistudio.previewers.*`; it is under `docs/user/**`, which the spec excludes | left as reported; it still builds because the alias modules resolve, and `full_audit` raises nothing against it | `#2211` |
| `2026-09-03` | `W1-rename` | `scripts/audit/check_package_contract_tables.py` is now stale against the renamed symbols | confirmed again that nothing in CI, `src/scistudio/qa/`, or `tests/` invokes it, so it cannot fail the build; left unedited per the spec's `docs/package-development/**` exclusion | follow-up issue at integration |
| `2026-09-03` | `manager` | `W2-core` and `W4-builtin` both died to a network error (ENOTFOUND) mid-task, losing everything they had not committed: `W2-core` lost all of it, `W4-builtin` lost all but one file | re-dispatched both from a clean branch point, carrying forward the one artifact that survived (the agreed `panel.json` shape) so it is not re-derived, and added a standing instruction to commit and push after each task rather than holding one final commit | `N/A` |
| `2026-09-03` | `W4-builtin` | the message contract had no name for five operations the panels need (query patch, plot export, open child resource, download, editor handoff), so the agent expressed all five as `read` with an `action` key | refused and replaced by D-017: `read`, `resource` and `host_action` are named types, because an export is not a read and five meanings in one type is the illegible single mechanism ADR-054 section 9 forbids; `W3-fe` implements it, `W4-builtin` updates the documents | `N/A` |
| `2026-09-03` | `W4-builtin` | the two producing panels have no Confirm button, because `emit` is their only outbound path; today's `DataRouterModal` and `PairEditorModal` have one | resolved as D-018: Confirm and Cancel are host chrome, as the title bar and ESC already are; Confirm commits the newest `emit` | `N/A` |
| `2026-09-03` | `W4-builtin` | the collection panel loses `data-tutorial-target="preview_item"` and the `preview_item_opened` UI event to the frame boundary; the agent marked it `TODO(#2229)` | **rejected as a deferral.** Verified the shipped `what-is-a-type` tutorial depends on both in five places and `tests/tutorials/test_core_tutorial_what_is_a_type.py` asserts them; a shipped tutorial must not break. Resolved as D-019: the host fires the event when it services a `resource` message and carries the target on its own chrome; `W3-fe` implements it | `N/A` |
| `2026-09-03` | `W4-builtin` | `pyproject.toml` package-data needed one pattern so the panel directories ship in the wheel; `guard.mod_guard` fired and the agent declared `governance_touch: true` | accepted: the dispatch instructed the packaging change, the wheel was built and all 22 files verified present, and the gate's `wheel_release_smoke` passed | owner review at PR |
| `2026-09-03` | `W4-builtin` | the browser-driven proof harness is not committed: it needed a new path and a playwright dependency outside the agent's one-test-file scope, so the committed tests are static and structural only | accepted for this branch; the adversarial no-context test engineer in wave 5 is the right owner for reproducible browser evidence | `W5-test` |
| `2026-09-03` | `W4-builtin` | one unidentified `python_tests` failure in the first gate run, clean on re-run, not in `tests/panels`; the gate does not persist the failing node id | logged as a suspected known flake; the manager re-runs the full suite at integration and will identify it if it recurs | `N/A` |
| `2026-09-03` | `W4-builtin` | D-017 sent the eleven documents back for a second pass; the agent verified both new guards actually bite by injecting an `action` key and an off-contract message type and confirming exactly two failures | accepted and merged; `tests/panels` is at 422 tests | `N/A` |
| `2026-09-03` | `W4-builtin` | `resource_result.resource` is not read by either panel that sends `resource` - the composite uses only the fact of the answer, the collection ignores it - so the host is free to make it thin | recorded for `W3-fe`: decide what `resource_result` carries; nothing in the documents constrains it | `W3-fe` |
| `2026-09-03` | `W4-builtin` | `host_action_result.ok === false` is treated by the documents as a failure whose `detail` becomes the message; a host that wants to signal a *declined* action differently has no way to say so | recorded for `W3-fe`: either adopt the documents' reading or propose a third state and the documents follow | `W3-fe` |
| `2026-09-03` | `W4-builtin` | while testing that the guards bite, the agent left one document in a mixed state after uneven `git checkout --` reverts | self-caught: it reverted all eight documents to the last commit and re-ran the patch scripts from scratch, each asserting on every replacement; the committed diff is from the clean re-apply. Manager confirmed the merged tree's guard tests are present and passing | `N/A` |
| `2026-09-03` | `manager` | my own scope-expansion commit `b85e7001e` put an unquoted `2026-09-03:` inside a plain YAML scalar, so the spec's frontmatter stopped parsing entirely and every frontmatter-driven audit on it went blind rather than failing loudly | found by `W4-compat`, which noticed the *expected* `planned_governs` finding had vanished rather than appeared. Quoted the note; `full_audit` back to pass with zero error findings, and the last `planned_governs` entry migrated now that `api/routes/panels.py` exists | `N/A` |
| `2026-09-03` | `W4-compat` | the tutorial `review_labels` panel cannot be migrated yet: three assertions in `test_core_tutorial_what_is_a_type.py` pin the retired `.mjs` form, and a block-declared panel directory is not reachable through the merged asset route until the paused-block descriptor lands | agent correctly stopped rather than forcing it. Manager correction: my instruction that the tutorial test pass *unchanged* was right for D-019's behaviour and wrong for those three assertions, which pin an asset form the spec's section 4.2 explicitly retires. Sequenced after the emission-consumer branch | `N/A` |
| `2026-09-03` | `manager` | the tutorial tier-guard hole fixed in `448c64c42` was not logged here when it was fixed | logged now: `<project>/panels` was outside `EXECUTED_PROJECT_PATHS` and `_SCANNED_PROJECT_DIRS`, so a user- or project-level tutorial could write a `panels/` directory the product frames and whose `panel.json` names an imported Python provider. Omission found by the with-context audit | `N/A` |
| `2026-09-03` | `manager` | `W1-rename` added `tests/panels/test_previewers_alias.py`, which D-002 forbade; the manager authorised it in the dispatch but never recorded that D-002 had been bent | logged now. D-002's rule held for every other file; the exception was deliberate and is the one test proving the D-001 aliases resolve | `N/A` |
| `2026-09-03` | `manager` | two agents ran with full gate ledgers and merge commits but no dispatch-matrix row: `feat/2229-panel-emission-consumer` and `feat/2229-tutorial-panel-migration` | rows added to section 6 above. Found by the with-context audit, not by the manager | `N/A` |
| `2026-09-03` | `manager` | this log described the tutorial test change as three assertions; the real diff is +168/-50 across five assertion sites | corrected: `W4-tutorial` rewrote five sites, two of which it identified itself as members of the same category, and reported both | `N/A` |
| `2026-09-03` | `W5-audit-nc` | **P1**: `panels/providers.py` resolved a declaration's `provider` with `root.joinpath(*name.split(...))`, which an absolute segment escapes, then exec_module'd the result. Fires at project open, registry reload, every choice write and every panel save | manager reproduced the escape independently; dispatched `W6-security`. The test named for the property only checked that two bare same-named modules do not cross | `N/A` |
| `2026-09-03` | `W5-test` | **P1**: `capabilities` to `features` shipped with no keyword alias, so an unmigrated package's `get_previewers()` fails to register silently; and `target_types` inserted as the fifth field makes positional construction mis-bind with no error | dispatched `W6-compat` with the engineer's five red tests as its specification | `N/A` |
| `2026-09-03` | `W5-audit-wc` | **P1**: `OwnerKind is PanelTier`, so a shimmed user- or project-tier previewer is treated as editable in place and its save is written into the disposable shim root - success reported, edit discarded on the next rebuild | dispatched `W6-editing` | `N/A` |
| `2026-09-03` | `W5-audit-wc` | every `TODO(#2211)` this change introduces cites a **closed** issue; #2211 is the spec-authoring issue, not the follow-through | `W6-editing` opens a real issue and repoints the three live sites | `N/A` |
| `2026-09-03` | `W5-audit-wc` | D-002 and D-017 constrain shipped behaviour but live only in `docs/planning/**`, which the spec's own `governs.excludes` excludes; 191 `D-0NN` citations across 51 source files point there | manager moves the behaviour-constraining decisions into the governed spec | `N/A` |
| `2026-09-03` | `W4-compat` | `POST /api/panels/{id}/copy` would copy a shim-generated directory into a project, freezing a wrapped previewer as a permanent snapshot | degrades gracefully and carries the `adr048-compat-shim` feature tag; `is_compat_panel()` exists if a refusal is wanted. Left for the audit to judge rather than fixed outside the agent's scope | audit finding candidate |

## 10. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux
      evidence when needed, commit, and PR evidence.
- [ ] PR closes every issue fixed by the dispatch.
- [ ] CI passed.
- [ ] Checklist final state matches PR and gate record.
