---
title: "ADR-043 Package Migration Agent Dispatch Checklist"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 41
  - 43
language_source: en
---

# ADR-043 Package Migration Agent Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: Coordinate ADR-043 migration across in-tree LoadData/SaveData,
  imaging package (adding PNG/JPEG/Bio-Formats and `Image.Meta.ome`), SRS package
  ProcessBlock propagation, frontend UI, ending with owner-authored e2e tests.
- Task kind: `manager`
- Manager persona: `manager`
- Issue: `#1296`
- Parent tracking issue: `#1204`
- Gate record: `.workflow/records/1296-adr-043-package-migration-manager.json`
- Branch/worktree plan:
  - Manager worktree: `.claude/worktrees/adr-043-umbrella` on
    `track/adr-043/core-blocks-and-imaging`.
  - Each dispatched agent owns its own worktree under
    `.claude/worktrees/adr-043-<phase>-<surface>/` on a sub-branch off the
    umbrella branch.
- Protected branch: `main`
- Umbrella branch: `track/adr-043/core-blocks-and-imaging`
- Umbrella PR: `#1297` — https://github.com/zjzcpj/SciEasy/pull/1297
- Umbrella PR title: `[DO NOT MERGE] track(#1296): ADR-043 in-tree + imaging + SRS migration umbrella`
- Final PR target: `main`
- Spec doc: `docs/specs/adr-043-package-migration.md`
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context:
    `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context:
    `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`

## 2. Scope

- In scope (matches spec scope.in):
  - In-tree `LoadData` / `SaveData` migration to explicit `FormatCapability`;
    delete legacy `supported_extensions`.
  - imaging `LoadImage` / `SaveImage` explicit `FormatCapability` + PNG/JPEG
    (Pillow) + Bio-Formats (CZI/ND2/LIF/OIR/OIB) load-only handlers.
  - `Image.Meta` + `Label.Meta` gain typed `ome: ome_types.model.OME | None`.
  - `imaging[bioformats]` optional install extra (cellpose pattern).
  - ProcessBlock OME metadata propagation contract (Modes A/B/C) + imaging +
    SRS audit/fix.
  - Frontend: capability dropdown, OME browser, lossy-save warning.
  - Owner-authored Phase D end-to-end test cases before final merge.
- Out of scope (matches spec scope.out):
  - LCMS package migration (separate sub-issue under #1204).
  - OME-Zarr v0.4 first-class support.
  - Adding `LoadSRSImage` IO block.
  - Bio-Formats save support (library is load-only).
  - Engine / registry / validator / materialisation changes (already migrated).
- Protected paths:
  - `src/scieasy/blocks/io/io_block.py` — base class; `supported_extensions`
    ClassVar stays for unmigrated third-party packages.
  - `src/scieasy/blocks/registry.py` — already capability-aware; no manager-
    track edits expected.
  - `src/scieasy/engine/**`, `src/scieasy/blocks/io/materialisation.py`,
    `src/scieasy/workflow/validator.py` — out-of-scope (engine already
    migrated).
- Deferred work:
  - LCMS migration: covered by parent #1204 follow-up.
  - OME-Zarr support: follow-up issue if requested.
  - `LoadSRSImage` block: follow-up issue if requested.

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

- [x] Dedicated manager branch and worktree created
      (`.claude/worktrees/adr-043-umbrella` on
      `track/adr-043/core-blocks-and-imaging`).
- [x] Existing parent issue #1204 linked; new sub-issue #1296 created.
- [x] Gate record started
      (`.workflow/records/1296-adr-043-package-migration-manager.json`).
- [x] Scope include/exclude recorded in the gate record.
- [x] Umbrella branch created.
- [x] Umbrella PR opened (#1297).
- [x] Umbrella PR title includes `[DO NOT MERGE]`.
- [x] Protected branch and umbrella PR number recorded in this checklist.
- [x] No `pip install -e .` environment pollution found (manager worktree only
      runs gate-record CLI).
- [x] Dispatch checklist copied from the template and committed (this file).
- [x] Dispatch prompts created from the correct prompt template and linked
      below:
      - A1: `docs/planning/dispatch-prompts/adr-043-a1-core-io-prompt.md`
      - A2: `docs/planning/dispatch-prompts/adr-043-a2-imaging-io-prompt.md`
      - A3: `docs/planning/dispatch-prompts/adr-043-a3-frontend-prompt.md`
- [x] Sentrux baseline recorded: N/A. Manager-track umbrella PR carries only docs/planning/gate-record/CHANGELOG scaffolding; Sentrux CLI unavailable locally; per-phase sub-PRs (A1/A2/A3/B1/B2) each own their Sentrux evidence at implementation surface.

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `admin-approved:ai-override`
- Owner authorization source: chat, 2026-05-20, manager session approving
  umbrella PR creation past Sentrux + full-audit gates after owner confirmed
  audit/CI gates are not yet enforced and the manager-track umbrella has no
  Python / governance code / architecture-relevant changes (4 additive
  scaffolding files only).
- Reason: (a) Sentrux CLI not installed locally; per-phase sub-PRs carry their
  own Sentrux evidence at their implementation surfaces. (b) Full-audit
  reports pre-existing repository debt unrelated to this PR (ADR-031 missing
  frontmatter, adr-042-consistency-tools.md signature drift, architecture-doc
  AnnData/SpatialData refs) that the owner is repairing in parallel.

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scieasy.qa.governance.gate_record pre-commit --staged` | `N/A` (no hook installed in this worktree) | `[x]` | manager-track files staged cleanly; no pre-commit hook in `.git/hooks/` |
| Commit message | `python -m scieasy.qa.governance.gate_record commit-msg <commit-msg-file>` | `N/A` | `[x]` | Trailers present: `Gate-Record: ...`, `Task-Kind: manager`, `Issue: #1296`, `Assisted-by: claude-code:claude-opus-4-7` |
| Pre-push | `python -m scieasy.qa.governance.gate_record pre-push` | `admin-approved:ai-override` | `[x]` | First push allowed; subsequent force-push allowed with `--force-with-lease` after gate record finalize (commit_and_submit_pr stage). Sentrux + full-audit gate failures classified as pre-existing repo debt + Sentrux CLI unavailable. |
| PR-create (gh) | `gh pr create --label admin-approved:ai-override ...` | `admin-approved:ai-override` | `[x]` | PR #1297 created with override label; label provenance via chat authorization recorded above. |

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| A1 | implementer | N/A | `docs/planning/dispatch-prompts/adr-043-a1-core-io-prompt.md` | Core IO LoadData/SaveData migration (FR-001..003) | `feat/issue-1296/adr043-a1-core-io` | `.claude/worktrees/adr-043-a1-core-io/` | `src/scieasy/blocks/io/loaders/load_data.py`, `src/scieasy/blocks/io/savers/save_data.py`, `tests/blocks/io/test_load_data_capabilities.py`, `tests/blocks/io/test_save_data_capabilities.py`, `CHANGELOG.md`, plus in-scope cleanup of `tests/blocks/io/test_load_data.py` + `tests/blocks/io/test_save_data.py` (legacy ClassVar tests rewritten to capability-derived contract) and `tests/blocks/app/test_appblock_bin_outputs.py` capability_id strings (direct FR-003 consequences) | imaging, srs, frontend, engine, registry, materialisation, IOBlock base | PR #1300 | `[~]` (implementation complete; pending merge) |
| A2 | implementer | N/A | `docs/planning/dispatch-prompts/adr-043-a2-imaging-io-prompt.md` | imaging IO migration + Image.Meta.ome + Bio-Formats extras (FR-004..008, FR-017) | `feat/issue-1296/adr043-a2-imaging-io` (merged + deleted) | `.claude/worktrees/adr-043-a2-imaging/` (removed) | (see PR #1298 diff) | core IO, srs, frontend, ProcessBlock propagation, engine | PR #1298 merged 2026-05-20 | `[x]` |
| A3 | implementer | N/A | `docs/planning/dispatch-prompts/adr-043-a3-frontend-prompt.md` | Frontend UI: capability dropdown + OME browser + lossy-save warning (FR-012..014) | `feat/issue-1296/adr043-a3-frontend` | `.claude/worktrees/adr-043-a3-frontend/` | `frontend/src/components/PortEditor/CapabilityDropdown.tsx` (new), `frontend/src/components/OutputPreview/OMEMetadataPanel.tsx` (new), `frontend/src/components/WorkflowEditor/LossySaveWarning.tsx` (new), `frontend/src/api/capabilities.ts` (new), `frontend/src/__tests__/CapabilityDropdown.test.tsx` (new), `frontend/src/__tests__/OMEMetadataPanel.test.tsx` (new), `frontend/src/__tests__/LossySaveWarning.test.tsx` (new), `frontend/src/__tests__/adr043-a3-smoke.test.tsx` (new — JSDOM smoke harness), `frontend/e2e/adr043-a3-smoke.md` (new — manual in-app browser checklist), `frontend/src/components/PortEditorTable.tsx` (modified — per-row CapabilityDropdown wiring + `capability_id` PortRow field), `frontend/src/components/DataPreview.tsx` (modified — OME metadata button + panel toggle), `frontend/src/components/WorkflowCanvas.tsx` (modified — derive `upstreamOmeFields` from `blockOutputs`), `frontend/src/components/nodes/BlockNode.tsx` (modified — LossySaveWarning in save-IO footer), `frontend/src/types/ui.ts` (modified — `upstreamOmeFields?: string[]` on `BlockNodeData`), `frontend/src/App.tsx` (modified — pass `blockOutputs` to `WorkflowCanvas`), `CHANGELOG.md` | backend code, ProcessBlock propagation | PR #1299 | `[~]` (implementation complete; pending merge) |
| B1 | implementer | N/A | `docs/planning/dispatch-prompts/adr-043-b1-imaging-propagation-prompt.md` | imaging ProcessBlock propagation audit + fix (FR-009/010); A2 prerequisite merged | `feat/issue-1296/adr043-b1-imaging-propagation` | `.claude/worktrees/adr-043-b1-imaging-propagation/` | `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/preprocess/geometry.py`, `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/preprocess/axis_ops.py`, `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/projection/projection.py`, `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/segmentation/*.py`, `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/math/*.py`, `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/morphology/*.py`, `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/registration/*.py`, `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/measurement/*.py`, `packages/scieasy-blocks-imaging/tests/test_processblock_meta_propagation.py`, `docs/audit/adr-043-imaging-propagation-audit.md`, `CHANGELOG.md` | imaging IO, types.py, core IO, srs, frontend, engine | PR #1302 open (targets umbrella) | `[~]` (implementation complete; pending merge) |
| B2 | implementer | N/A | `docs/planning/dispatch-prompts/adr-043-b2-srs-propagation-prompt.md` | SRS ProcessBlock propagation audit + fix (FR-009/011); A2 prerequisite merged | `feat/issue-1296/adr043-b2-srs-propagation` | `.claude/worktrees/adr-043-b2-srs-propagation/` | `packages/scieasy-blocks-srs/src/scieasy_blocks_srs/preprocess/srs_baseline.py`, `packages/scieasy-blocks-srs/src/scieasy_blocks_srs/preprocess/srs_spectral_denoise.py`, `packages/scieasy-blocks-srs/src/scieasy_blocks_srs/preprocess/srs_calibrate.py`, `packages/scieasy-blocks-srs/src/scieasy_blocks_srs/component_analysis/srs_kmeans.py`, `packages/scieasy-blocks-srs/src/scieasy_blocks_srs/component_analysis/srs_pca.py`, `packages/scieasy-blocks-srs/src/scieasy_blocks_srs/component_analysis/srs_unmix.py`, `packages/scieasy-blocks-srs/tests/test_processblock_meta_propagation.py`, `docs/audit/adr-043-srs-propagation-audit.md`, `CHANGELOG.md` | imaging, core IO, frontend, engine | impl complete; PR pending | `[~]` |
| C1 | audit_reviewer | no-context | pending | No-context final audit (FR-001..017, SC-001..005); commit audit report | `track/adr-043/core-blocks-and-imaging/c1-audit` | `.claude/worktrees/adr-043-c1-audit/` | `docs/audit/adr-043-package-migration-final-audit-<sha>.md` | code changes; audit is read-only | TBD | `[ ]` |
| D2 | implementer | N/A | pending after Phase D1 | Execute owner-authored e2e cases (SC-006) | `track/adr-043/core-blocks-and-imaging/d2-e2e` | `.claude/worktrees/adr-043-d2-e2e/` | `docs/audit/adr-043-package-migration-e2e-cases.md`, e2e test files as defined by owner cases | code changes outside what e2e cases require | TBD | `[ ]` |

## 7. Track: Phase A1 — In-tree Core IO Migration

### 7.1 Track Scope

- Owner: implementer agent (TBD)
- In scope:
  - Declare explicit `LoadData.format_capabilities` + `SaveData.format_capabilities`.
  - Delete `supported_extensions` ClassVars from both classes.
  - Rewire `_resolve_format` / `_resolve_save_format` and error messages.
  - Add capability tests.
- Out of scope:
  - `IOBlock` base class `supported_extensions` (stays).
  - Engine / registry / materialisation / validator code.
  - imaging / SRS / frontend.
- Required docs:
  - CHANGELOG entry.
- Required tests:
  - `tests/blocks/io/test_load_data_capabilities.py` (new).
  - `tests/blocks/io/test_save_data_capabilities.py` (new).

### 7.2 Dispatch

- [x] Prompt file created or dispatch prompt recorded. -> `docs/planning/dispatch-prompts/adr-043-a1-core-io-prompt.md`
- [x] Correct prompt template selected (`agent-dispatch-prompt-template.md`). -> dispatch prompt header `[DISPATCH-TEMPLATE-V1: implementer]`
- [x] Agent branch/worktree assigned. -> `feat/issue-1296/adr043-a1-core-io` on `.claude/worktrees/adr-043-a1-core-io/`
- [x] Write set and out-of-scope paths included in prompt. -> dispatch prompt §Scope
- [x] TODO rule included in prompt. -> dispatch prompt §"TODO And Deferral Rule"
- [x] Required checks included in prompt. -> dispatch prompt §"Required Tests And Checks"

### 7.3 Implementation

- [x] `LoadData.format_capabilities` declared (FR-001) -> `src/scieasy/blocks/io/loaders/load_data.py` (`_LOAD_CAPABILITIES`, 30 records covering Array/DataFrame/Series/Text/Artifact/CompositeData per ADR-043 FR-015 convention; Artifact records include both MIME-mapped and opaque-loader variants for the legacy supported-extension union)
- [x] `SaveData.format_capabilities` declared (FR-002) -> `src/scieasy/blocks/io/savers/save_data.py` (`_SAVE_CAPABILITIES`, 31 records mirroring LoadData with `direction='save'` plus the legacy Series-json save-only branch; Artifact records mirror LoadData's opaque-saver set)
- [x] `supported_extensions` ClassVars deleted; helpers rewired (FR-003) -> `_resolve_format`, `_resolve_save_format`, per-class `_detect_format` overrides now derive from `_LOAD_EXTENSION_MAP` / `_SAVE_EXTENSION_MAP`; user-facing error messages re-sourced via `_supported_load_extensions()` / `_supported_save_extensions()`
- [x] Test files added (FR-016) -> `tests/blocks/io/test_load_data_capabilities.py` (47 tests) and `tests/blocks/io/test_save_data_capabilities.py` (50 tests); existing `tests/blocks/io/test_load_data.py` + `tests/blocks/io/test_save_data.py` ClassVar test classes rewritten to assert the capability-derived contract; `tests/blocks/app/test_appblock_bin_outputs.py` capability_id strings updated to the new `core.dataframe.csv.load` form (direct consequence of FR-003 deleting the synthesis fallback). Local pytest pass: 270 IO tests + 11 AppBlock binner tests green; remaining 15 fails are imaging/lcms `ModuleNotFoundError` (worktree-environment-only, not introduced by A1).
- [x] CHANGELOG entry added -> CHANGELOG.md `[#1296]` entry under `## [Unreleased]` → `### Added`.

### 7.4 Audit

- [x] Codex auto-review consumed; P1/P2 reconciled with explicit decision per finding. -> One P1 finding ("Add `.json` to Text save capability extensions" at `src/scieasy/blocks/io/savers/save_data.py:277`, inline review id `3276517969`): **ACCEPTED**, fixed by adding a separate `core.text.json.save` capability (format_id="json", extensions=[".json"]) so `find_saver_capability(Text, '.json')` resolves instead of raising MissingCapabilityError. Reply posted as inline review id `3276633852`. Subsequent CI run (workflow_dispatch 26185256572 on commit `180a82d9`) is green on all 7 jobs (Type Check / Test 3.13 / Test 3.11 / Frontend / Import Contracts / Lint & Format / Architecture Tests).

### 7.5 Integration

- [ ] Agent output reviewed by manager. -> Awaiting manager review of PR #1300.
- [ ] Scope compliance verified. -> Self-attested: writes confined to A1 scope plus the direct-FR-003-consequence test updates documented in §7.3 and Drift Log row 1.
- [ ] Track merged into umbrella branch. -> Pending manager merge.

## 8. Track: Phase A2 — Imaging IO + Image.Meta.ome + Bio-Formats

### 8.1 Track Scope

- Owner: implementer agent (TBD)
- In scope:
  - `LoadImage.format_capabilities` + `SaveImage.format_capabilities` declarations.
  - Add `ome: OME | None` field to `Image.Meta` and `Label.Meta`.
  - Add `pillow_handler.py` for PNG/JPEG load+save.
  - Add `bioformats_handler.py` for CZI/ND2/LIF/OIR/OIB lazy-import load-only.
  - Add `bioformats` optional extras + `ome-types` required dep in pyproject.toml.
- Out of scope:
  - Core IO blocks.
  - ProcessBlock propagation audit (covered in B1).
  - SRS package.
  - Frontend.
- Required docs:
  - CHANGELOG entry.
- Required tests:
  - `test_format_capabilities.py` (new).
  - `test_image_meta_ome.py` (new).
  - `test_bioformats_handler.py` (new, gated by extras availability).

### 8.2 Dispatch

- [x] Prompt file created. (`docs/planning/dispatch-prompts/adr-043-a2-imaging-io-prompt.md`)
- [x] Correct prompt template selected.
- [x] Agent branch/worktree assigned. (`feat/issue-1296/adr043-a2-imaging-io` on `.claude/worktrees/adr-043-a2-imaging`)
- [x] Write set, out-of-scope paths, TODO rule, required checks included.

### 8.3 Implementation

- [x] `Image.Meta.ome` field added (FR-006) -> pending commit (this PR)
- [x] `Label.Meta.ome` field added (FR-007) -> pending commit (this PR)
- [x] `LoadImage.format_capabilities` declared (FR-004) -> pending commit (this PR; 9 capabilities incl. PNG/JPEG/Bio-Formats family)
- [x] `SaveImage.format_capabilities` declared (FR-005) -> pending commit (this PR; 4 writable capabilities; Bio-Formats family deliberately absent)
- [x] `pillow_handler.py` created -> pending commit (this PR)
- [x] `bioformats_handler.py` created with lazy-import + clear missing-extras error (FR-008) -> pending commit (this PR)
- [x] `pyproject.toml` updated with `bioformats` extras + `ome-types` required dep (FR-008, FR-017) -> pending commit (this PR)
- [x] Capability + ome tests added (FR-016) -> pending commit (test_format_capabilities.py + test_image_meta_ome.py + test_bioformats_handler.py)
- [x] CHANGELOG entry added -> pending commit (this PR)

### 8.4 Audit

- [ ] Codex auto-review consumed; P1/P2 reconciled.

### 8.5 Integration

- [ ] Agent output reviewed by manager.
- [ ] Scope compliance verified.
- [ ] Track merged into umbrella branch (gate for B1/B2 dispatch).

## 9. Track: Phase A3 — Frontend UI

### 9.1 Track Scope

- Owner: implementer agent (TBD)
- In scope:
  - `CapabilityDropdown.tsx` + integration into port editor.
  - `OMEMetadataPanel.tsx` + integration into output preview.
  - `LossySaveWarning.tsx` + integration into workflow editor.
  - Capability listing API client updates.
- Out of scope:
  - Backend code.
  - ProcessBlock propagation.
- Required docs:
  - CHANGELOG entry.
- Required tests:
  - Per-component unit tests under `frontend/src/__tests__/`.
  - **Mandatory Chrome smoke test** before reporting done.

### 9.2 Dispatch

- [x] Prompt file created — `docs/planning/dispatch-prompts/adr-043-a3-frontend-prompt.md`.
- [x] Mandatory Chrome smoke test included in prompt — T-024 step + JSDOM-smoke fallback documented in `frontend/e2e/adr043-a3-smoke.md` (Chrome MCP / Playwright not provisioned in this repo per the dispatch prompt stop-condition; surfaced as a known gap in the report-back).
- [x] Correct prompt template selected — `docs/ai-developer/templates/agent-dispatch-prompt-template.md` (DISPATCH-TEMPLATE-V1: implementer).

### 9.3 Implementation

- [x] `CapabilityDropdown.tsx` (FR-012) -> commit sha pending push
- [x] `OMEMetadataPanel.tsx` (FR-013) -> commit sha pending push
- [x] `LossySaveWarning.tsx` (FR-014) -> commit sha pending push
- [x] API client `capabilities.ts` created (`listCapabilities`, `aggregateCapabilities`, `getOMEMetadata`, `extractOMEFromMetadata`, `lossyOmeFields`) -> commit sha pending push
- [x] Unit tests added — `CapabilityDropdown.test.tsx` (6 tests), `OMEMetadataPanel.test.tsx` (13 tests), `LossySaveWarning.test.tsx` (11 tests) -> commit sha pending push
- [x] Smoke test scripted + executed — JSDOM harness at `frontend/src/__tests__/adr043-a3-smoke.test.tsx` (6 tests, all pass) + manual checklist at `frontend/e2e/adr043-a3-smoke.md`; Chrome MCP/Playwright unavailable in this repo, so JSDOM is the committed evidence and the manual checklist is for the owner to run after umbrella merge.
- [x] CHANGELOG entry added -> commit sha pending push

### 9.4 Audit

- [x] Codex auto-review consumed; P1/P2 reconciled — both findings fixed in commit bd899d0f and pinned by 6 new tests in `frontend/src/__tests__/capabilities.test.ts`. P1 (extension normalisation mismatch) addressed by `normalizeBackendExtension`; P2 (strict type equality) addressed by `ancestorTypeNames` + `typeHierarchy` forwarding through `CapabilityDropdown` and `PortEditorTable`. CI green after fix; no follow-up Codex round within the 5-min window per the saved discipline rule.

### 9.5 Integration

- [ ] Agent output reviewed by manager — pending.
- [ ] Track merged into umbrella branch — pending.

## 10. Track: Phase B1 — imaging ProcessBlock Propagation Audit + Fix

### 10.1 Track Scope

- Owner: implementer agent (TBD)
- Depends on: Phase A2 merged.
- In scope:
  - Audit every Image-domain ProcessBlock in imaging package; classify Mode A/B/C.
  - Update Mode B helpers (`_resize_meta`, `_projected_meta`, `_split_meta`) to
    handle ome field transformations.
  - Update Mode C blocks to carry ome when output preserves spatial coordinate
    system.
  - Add propagation tests.
  - Commit audit report.

### 10.2 Dispatch

- [x] Prompt file created. (`docs/planning/dispatch-prompts/adr-043-b1-imaging-propagation-prompt.md`)
- [x] Spec FR-009/010 contract clearly cited in prompt.

### 10.3 Implementation

- [x] All Image-domain ProcessBlocks classified A/B/C -> `docs/audit/adr-043-imaging-propagation-audit.md` §3 classification table (~40 rows covering math, morphology, preprocess, projection, registration, segmentation, measurement, tracking, visualization)
- [x] Mode B helpers updated for ome (FR-009) -> commit 9e1e60c6 (`_resize_meta` in `preprocess/geometry.py`, `_projected_meta` in `projection/projection.py`, `_split_meta` in `preprocess/axis_ops.py` — each deep-copies OME and rewrites pixel sizes / `size_<axis>`)
- [x] Mode C blocks updated to carry ome (FR-009/010) -> commit 9e1e60c6 (`segmentation/cellpose_segment.py` mask_img + Label.Meta both carry ome; `segmentation/blob_detect.py`, `connected_components.py`, `watershed.py` Label.Meta carries ome)
- [x] `test_processblock_meta_propagation.py` added (FR-010, FR-016) -> commit 9e1e60c6 (18 tests, all passing — Mode A x4, Mode B x7, Mode C x7 including legitimate-drop pins for RegionProps DataFrame + ComputeRegistration Transform)
- [x] `docs/audit/adr-043-imaging-propagation-audit.md` committed -> commit 9e1e60c6
- [x] CHANGELOG entry added -> commit 9e1e60c6

### 10.4 Audit

- [ ] Codex auto-review consumed; P1/P2 reconciled. (Pending — capped at one round, 5-min from CI green per ADR-042 norms.)

### 10.5 Integration

- [ ] Track merged into umbrella branch. (PR #1302 open, awaiting CI + Codex auto-review + manager review.)

## 11. Track: Phase B2 — SRS ProcessBlock Propagation Audit + Fix

### 11.1 Track Scope

- Owner: implementer agent (TBD)
- Depends on: Phase A2 merged.
- In scope:
  - Audit every block in scieasy-blocks-srs (preprocess, component_analysis,
    spectral_extraction); classify A/B/C.
  - Confirm Mode A blocks (`srs_baseline.py`, `srs_spectral_denoise.py`).
  - Fix `srs_kmeans.py` (Label output: add ome).
  - Confirm `srs_calibrate.py` Mode C via `model_dump+override`.
  - Document deliberate ome drop in `srs_pca.py` / `srs_unmix.py`.
  - Add propagation tests.
  - Commit audit report.

### 11.2 Dispatch

- [x] Prompt file created. (`docs/planning/dispatch-prompts/adr-043-b2-srs-propagation-prompt.md`)
- [x] Spec FR-009/011 contract clearly cited in prompt.

### 11.3 Implementation

- [x] All SRS ProcessBlocks classified A/B/C -> `docs/audit/adr-043-srs-propagation-audit.md` §3 (pending commit, this PR)
- [x] `srs_kmeans.py` Label output carries ome (FR-009/011) -> pending commit (this PR)
- [x] `srs_pca.py` / `srs_unmix.py` deliberate-drop documented -> pending commit (this PR)
- [x] `test_processblock_meta_propagation.py` added (FR-011, FR-016) -> pending commit (this PR)
- [x] `docs/audit/adr-043-srs-propagation-audit.md` committed -> pending commit (this PR)
- [x] CHANGELOG entry added -> pending commit (this PR)

### 11.4 Audit

- [ ] Codex auto-review consumed; P1/P2 reconciled.

### 11.5 Integration

- [ ] Track merged into umbrella branch.

## 12. Track: Phase C1 — No-Context Audit

### 12.1 Track Scope

- Owner: audit_reviewer agent (no-context mode)
- Audit mode: `no-context` (per agent-dispatch.md §4).
- Depends on: All of A + B merged into umbrella.
- In scope:
  - Verify FR-001..FR-017 acceptance independently from this checklist and the
    spec (uses repository docs, code, tests, and tool output only).
  - Run ADR-043 §9 package validity scan.
  - Run capability-synthesis check (is_synthesized=False on migrated blocks).
  - Commit audit report.
- Out of scope:
  - Code changes (audit is read-only).

### 12.2 Dispatch

- [ ] Prompt file created from
      `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`.
- [ ] No-context mode confirmed (no issue, checklist, PR, or manager summary
      context shared).

### 12.3 Audit

- [ ] Audit report committed at
      `docs/audit/adr-043-package-migration-final-audit-<sha>.md`.
- [ ] Findings recorded.
- [ ] P1 findings fixed before integration.
- [ ] P2/P3 findings fixed or tracked with owner-approved rationale.

### 12.4 Integration

- [ ] Audit report merged into umbrella PR evidence path.

## 13. Track: Phase C2 — Integration Verification (Manager)

### 13.1 Track Scope

- Owner: manager.
- Depends on: C1 audit committed.
- In scope:
  - Golden-path workflow: CZI → resize → save TIFF; verify ome.physical_size_x.
  - Chrome smoke verifying capability dropdown + OME panel + lossy-save warning.
  - CI green on umbrella PR.
  - All sub-PRs merged into umbrella.

### 13.2 Verification

- [ ] Golden-path test executed -> evidence path
- [ ] Chrome smoke executed -> evidence path
- [ ] CI green on umbrella PR -> CI URL
- [ ] All sub-PRs merged -> sub-PR URLs

## 14. Track: Phase D — Owner-Authored E2E

### 14.1 Track Scope

- Owner: jiazhenz026 authors test cases; manager coordinates execution.
- Depends on: Phase C2 complete.
- Gate: ALL owner-authored cases MUST pass before final merge (SC-006).

### 14.2 D1 — Owner test-case authoring

- [ ] Manager notifies owner that A + B + C are green.
- [ ] Owner provides e2e test case set covering real-world workflows, cross-package
      interactions, UI flows, regression scenarios, edge cases.
- [ ] Owner provides expected behavior per case.
- [ ] Test cases committed at `docs/audit/adr-043-package-migration-e2e-cases.md`.

### 14.3 D2 — Execute owner cases

- [ ] Translate owner cases into runnable scenarios.
- [ ] Execute each case against integrated umbrella.
- [ ] Record pass/fail per case in the audit doc.
- [ ] For each failure: open targeted bug-fix issue, dispatch fix, re-run.

### 14.4 D3 — E2E gate

- [ ] All owner cases pass (SC-006).
- [ ] Umbrella PR marked ready for owner final review.

## 15. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Ruff | `ruff check .` | `[ ]` | pending |
| Format | `ruff format --check .` | `[ ]` | pending |
| Tests (manager track) | `pytest tests/ --timeout=60` (umbrella scope = spec/checklist/gate-record only; no test deltas in manager track) | `[ ]` | N/A — manager track has no test files; per-phase tracks own their own tests |
| Full audit | `python -m scieasy.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json` | `[ ]` | pending |
| Sentrux | scan + check-rules per ADR-042 Addendum 1 §2 | `[ ]` | pending |
| ADR-043 §9 package validity | `python -m scieasy.qa.audit.full_audit` (filter for adr043 findings) | `[ ]` | pending |

## 16. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| `<YYYY-MM-DD>` | `<agent>` | `<what drifted>` | `<manager action>` | `<issue/TODO/N/A>` |
| 2026-05-20 | A2 implementer | Scope amendment: touched `tests/blocks/test_imaging_plugin_fixes.py` outside original write set to update stale `supported_extensions` assertions broken by FR-003. | Accepted via gate-record amend (recorded in A2's gate record `.workflow/records/1296-a2-imaging-io.json`). Mechanical migration cost — defensible. | N/A |
| 2026-05-20 | A2 implementer | Added root `pyproject.toml [dev]` extras with `ome-types>=0.5,<0.6` to keep `tests/plugins/test_phase11_skeleton.py` passing in CI. Outside original write set. | Accepted via gate-record amend — necessary follow-on of FR-017 (ome-types is now a required dep of imaging). Defensible. | N/A |
| 2026-05-20 | A3 implementer | **Chrome MCP / Playwright not provisioned in repo.** A3 substituted with JSDOM smoke harness (6 tests against real DOM via testing-library) + manual in-app checklist at `frontend/e2e/adr043-a3-smoke.md` for owner to run against `vite preview`. | Surface as KNOWN GAP for Phase D — owner's e2e cases can pick up live-click coverage. Manager flags this so future UI dispatches can request Chrome MCP setup separately. | Phase D follow-up |
| 2026-05-20 | A1 implementer | A1 dispatch write-set named only `load_data.py`/`save_data.py`/`test_load_data_capabilities.py`/`test_save_data_capabilities.py`/`CHANGELOG.md`/checklist row, but FR-003 (delete `supported_extensions` ClassVar) inherently breaks legacy ClassVar assertions in `tests/blocks/io/test_load_data.py`/`tests/blocks/io/test_save_data.py` (`TestSupportedExtensionsClassVar`) and the hard-coded synthesized capability_id in `tests/blocks/app/test_appblock_bin_outputs.py`. | Rewrote the broken legacy test classes to assert the capability-derived contract; updated the hard-coded capability_id string to the new `core.dataframe.csv.load` form. Logged the scope amendment via `python -m scieasy.qa.governance.gate_record amend` and re-included the three test files. Manager (in PR #1300 review) is the final adjudicator. | N/A; direct mechanical consequence of FR-003 per AGENTS.md §3.1. |
| 2026-05-20 | A1 implementer | First CI run on PR #1300 failed with 200 `CapabilityRegistrationError: Conflicting default IO format capabilities for (save, DataFrame, .csv): 'core.dataframe.csv.save' on SaveData and 'scieasy-blocks-lcms.table.csv.save' on SaveTable.` The legacy synthesized capability used `data_type=DataObject` (never collided with concrete-type package capabilities); my explicit per-concrete-type declarations exposed this latent cross-package default-slot collision. | Re-declared every core LoadData/SaveData FormatCapability with `is_default=False`. Updated `test_no_capability_claims_default` (renamed from `_is_default`) and the alternate-wins test (renamed `_default_alternate_wins_over_non_default_core`) to assert the new ownership semantics. | N/A; documented in code/test docstrings. |
| 2026-05-20 | A1 implementer | Codex auto-review P1 on PR #1300: my Text save capability omitted `.json` but `_save_text` writes JSON happily, causing a registry/runtime contract mismatch (`find_saver_capability(Text, '.json')` raised MissingCapabilityError). | Added a separate `core.text.json.save` capability (format_id="json") so Text+`.json` resolves at lookup. LoadData's Text capability still excludes `.json` because `_load_text` doesn't parse JSON (mirrors `core.series.json` save-only legacy branch). | N/A; documented inline in `_SAVE_CAPABILITIES` and `test_every_save_pairs_with_a_load_via_roundtrip_group.save_only_legacy`. |

## 17. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux
      evidence when needed, commit, and PR evidence.
- [ ] Phase C1 no-context audit report committed.
- [ ] Phase D owner-authored e2e cases authored, executed, and all pass.
- [ ] PR closes #1296 with closing keyword.
- [ ] CI passed.
- [ ] Checklist final state matches PR and gate record.
