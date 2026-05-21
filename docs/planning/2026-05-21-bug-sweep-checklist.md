---
title: "2026-05-21 Bug Sweep Agent Dispatch Checklist"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs: []
language_source: en
---

# 2026-05-21 Bug Sweep Agent Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: `Triage and fix open bugs with medium-to-simple scope, fix LOC ≤150 (excluding tests). Root-cause fixes only.`
- Task kind: `manager`
- Manager persona: `manager`
- Issues (16 total, all bugfix scope ≤150 LOC):
  - Tier 1 surgical (5): #1110, #617, #1281, #1282, #1368
  - Tier 2 focused (4): #1109, #902, #1306, #1309
  - Audit-followup batch (7): #1343, #1365, #1366, #1367, #1369, #1370, #1371
- Owner-skipped: #1356 (owner fixing themselves)
- Gate record: `.workflow/records/manager-2026-05-21-bug-sweep.json`
- Branch/worktree plan:
  - Manager: `umbrella/2026-05-21-bug-sweep` @ `.claude/worktrees/manager-2026-05-21-bug-sweep`
  - Agents: `fix/issue-<n>/<slug>` @ `.claude/worktrees/agent-<wave>-<id>` per dispatch
- Protected branch: `main`
- Umbrella branch: `umbrella/2026-05-21-bug-sweep`
- Umbrella PR: `#1377` (https://github.com/zjzcpj/SciStudio/pull/1377)
- Umbrella PR title: `[DO NOT MERGE] umbrella(bug-sweep-2026-05-21): 16-issue Tier 1+2 + audit-followup batch`
- Final PR target: `main`
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context: `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context: `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`

## 2. Scope

- In scope:
  - Each agent's assigned write-set per Wave (see §6).
- Out of scope:
  - `#1356` lineage orphan tag — owner is fixing themselves
  - `#1336` / `#1337` circular import — architecture, requires ADR-author
  - `#841` Codex Windows 3.12 hang — platform diagnosis depth unknown
  - Any cross-cutting refactor not named in a Wave write-set
- Protected paths:
  - `src/scistudio/{core,engine,blocks,workflow,utils}/**` — admin-approved:core-change label required
  - `src/scistudio/qa/{governance,audit,schemas}/**` — admin-approved:core-change label required
  - `.github/workflows/**` — admin-approved:core-change
  - `.workflow/**` — admin-approved:core-change
  - `.pre-commit-config.yaml` — admin-approved:core-change
- Deferred work: `<TODO(#NNN) item or N/A>`

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
  → `umbrella/2026-05-21-bug-sweep` @ `.claude/worktrees/manager-2026-05-21-bug-sweep`
- [x] Existing issues linked (16 issues, all open).
- [ ] Gate record started.
- [ ] Scope include/exclude recorded in the gate record.
- [x] Umbrella branch created.
- [x] Umbrella PR opened. → #1377
- [x] Umbrella PR title includes `[DO NOT MERGE]`.
- [x] Protected branch and umbrella PR number recorded in this checklist.
- [x] No `pip install -e .` environment pollution found.
- [~] Dispatch checklist copied from the template and committed.
- [ ] Dispatch prompts created from the correct prompt template and linked below.
- [ ] Sentrux baseline recorded, or N/A reason recorded.

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `N/A` (no bypass authorized; standard gate enforcement)
- Owner authorization source: `N/A`
- Reason: `N/A`

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scistudio.qa.governance.gate_record pre-commit --staged` | `N/A` | `[ ]` | `<output or summary>` |
| Commit message | `python -m scistudio.qa.governance.gate_record commit-msg <commit-msg-file>` | `N/A` | `[ ]` | `<output or summary>` |
| Pre-push | `python -m scistudio.qa.governance.gate_record pre-push` | `N/A` | `[ ]` | `<output or summary>` |

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| W1 | implementer | N/A | inline | Tier 1 surgical batch | `fix/bug-sweep-2026-05-21/tier1-surgical` | `.claude/worktrees/agent-w1-tier1` | See §7.1 | See §7.1 | Closes #1110 #617 #1281 #1282 #1368 | `[ ]` |
| W2-A | implementer | N/A | inline | types path drop-in + worker | `fix/issue-1343-1365/types-registry` | `.claude/worktrees/agent-w2a-types` | See §7.2 | See §7.2 | Closes #1343 #1365 | `[ ]` |
| W2-B | implementer | N/A | inline | imaging TIFF OME + capability metadata | `fix/issue-1306-1371/imaging-ome-fidelity` | `.claude/worktrees/agent-w2b-imaging` | See §7.3 | See §7.3 | PR #1388, Closes #1306 #1371 | `[x]` |
| W3-A | implementer | N/A | inline | scheduler READY emit + interactive normalize | `fix/issue-1367-1370/scheduler-emit-normalize` | `.claude/worktrees/agent-w3a-scheduler` | See §7.4 | See §7.4 | Closes #1367 #1370 | `[ ]` |
| W3-B | implementer | N/A | inline | block registry + code backends | `fix/issue-1109-1309/registry-codebackends` | `.claude/worktrees/agent-w3b-registry` | See §7.5 | See §7.5 | Closes #1109 #1309 | `[ ]` |
| W4-A | implementer | N/A | inline | frontend port editor capability_id | `fix/issue-1366/port-capability-clear` | `.claude/worktrees/agent-w4a-porteditor` | See §7.6 | See §7.6 | Closes #1366 | `[ ]` |
| W4-B | implementer | N/A | inline | completion race + save-image dir picker | `fix/issue-902-1369/completion-saveimg` | `.claude/worktrees/agent-w4b-misc` | See §7.7 | See §7.7 | Closes #902 #1369 | `[ ]` |

## 7. Tracks

### 7.1 W1 — Tier 1 surgical batch (#1110 #617 #1281 #1282 #1368)

- Owner: W1 implementer
- In scope:
  - `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/io/save_data.py` (#1110) — verify exact package path
  - `src/scistudio/api/routes/filesystem.py` (#617) — escape apostrophes in PowerShell strings
  - `src/scistudio/blocks/code/exchange.py` (#1281) — key manifest records by `(direction, name)`
  - `src/scistudio/workflow/validator.py` (#1282) — narrow `_is_codeblock_spec` to concrete class
  - `tests/blocks/app/test_appblock_fiji_integration.py` (#1368) — remove calls to deleted `Block.transition`
- Out of scope:
  - All other source paths; no refactors; no docs unless directly tied to a fix
- Required docs: ADR/spec untouched; CHANGELOG entry for the batch under `[Unreleased]`
- Required tests:
  - Tests asserting full key set for `SaveData.supported_extensions`
  - Test that apostrophe in workflow name does not break PowerShell file dialog (mock subprocess.run + assert escaped form)
  - Test that input+output ports of same name preserve both records in exchange manifest
  - Test that non-CodeBlock spec with `base_category == 'code'` skips CodeBlock v2 validation
  - For #1368: confirm Fiji integration test path either passes or skips for env reasons (no AttributeError)

### 7.2 W2-A — Types path (#1343 + #1365)

- Owner: W2-A implementer
- In scope:
  - `src/scistudio/core/types/registry.py` — register drop-in `__module__` into `sys.modules` before storing TypeSpec
  - `src/scistudio/core/types/serialization.py` — refresh `_get_type_registry()` to consult project/user scan dirs (or expose a refresh-on-call path consistent with `ApiRuntime.refresh_type_registry()`)
  - `src/scistudio/engine/runners/worker.py::reconstruct_inputs` — call into refresh path before resolving
  - Tests for drop-in resolve through `TypeRegistry.load_class()` and through worker subprocess reconstruction
- Out of scope:
  - Removing or restructuring `_get_type_registry()`'s singleton contract — change behavior, not the API shape
  - Any unrelated registry, capability, or schema work
- Required docs: CHANGELOG entry only (no ADR/spec change for behavior-restoring bugfix)
- Required tests:
  - `tests/core/test_types_registry.py` — drop-in class registration round-trip via `TypeRegistry.load_class()`
  - `tests/engine/test_worker_reconstruction.py` (extend) — project-local drop-in type reconstructs in worker subprocess (not falls back to base `DataObject`)

### 7.3 W2-B — Imaging (#1306 + #1371)

- Owner: W2-B implementer
- In scope:
  - `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/io/load_image.py::_load_tiff` — read `tf.is_ome` + parse with `ome_types.from_xml`
  - `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/io/save_image.py` and `load_image.py` zarr/png/jpeg capability declarations — narrow `format_metadata_writes` / `format_metadata_reads` to actually-preserved subset
  - `frontend/src/api/capabilities.ts::lossyOmeFields()` — broaden matching to handle hierarchical OME field paths vs broad declarations
  - Tests for OME round-trip + capability matching
- Out of scope:
  - ImageJ TIFF metadata mapping to OME (separate enhancement per #1306 §Acceptance.3)
  - Anything outside the imaging package or `lossyOmeFields`
- Required docs: CHANGELOG entry
- Required tests:
  - Load fixture OME-TIFF → assert `image.meta.ome.images[0].pixels.physical_size_x`
  - Zarr round-trip → assert capability declaration matches behavior (`meta.ome is None` for zarr today; or implement zarr OME if narrow enough)
  - `lossyOmeFields()` unit test: flattened field `images.0.pixels.physical_size_x` correctly matched against broad declaration `ome`

#### W2-B status (2026-05-21)

- PR: [#1388](https://github.com/zjzcpj/SciStudio/pull/1388) — `MERGEABLE`, CI `Verify Workflow Compliance` pass.
- Final commit: `b7c505b8210987a1bd6d59c0b392f33797cc0c26` (Codex P1 reconciliation).
- Codex auto-review: 1 P1 (lossyOmeFields `images.<index>.` normalisation) addressed in b7c505b8 + reply on `pulls/comments/3284325380`.
- Implementation summary:
  - #1306 — `_load_tiff` already parsed OME-XML via `_ome_from_tiff` (PR #1304's P2-05 unblocker). This PR adds the externally-authored-OME-TIFF regression in `packages/scistudio-blocks-imaging/tests/test_load_image_ome.py` (3 cases: positive OME-TIFF, plain TIFF returns `meta.ome is None`, malformed OME-XML defensive fallback). No source change needed for #1306.
  - #1371 backend — zarr load/save capabilities drop to `level="pixel_only"` (zero OME or typed Meta survives); PNG/JPEG declarations narrow to hierarchical `("ome.pixels.physical_size_x", "ome.pixels.physical_size_y")` (the only fields Pillow's EXIF DPI round-trips); TIFF keeps the broad `"ome"` token (genuinely writes full OME-XML via `ome_types.to_xml` into ImageDescription).
  - #1371 frontend — `lossyOmeFields` now treats `"ome"` as a prefix covering every OME source path and strips `ome.` from hierarchical declarations before comparing source paths. Fixes false positives on broad declarations and false negatives once narrowed declarations land.
- Scope amendments:
  - 2026-05-21 — added `frontend/src/__tests__/adr043-a3-smoke.test.tsx` + `frontend/src/__tests__/LossySaveWarning.test.tsx` to gate record (`gate_record amend`) — both pre-existing tests pinned the old buggy `lossyOmeFields` exact-match semantics and needed updating to the new prefix-matching contract.
- Files touched:
  - `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/io/load_image.py` (zarr → pixel_only, png/jpeg → narrow paths)
  - `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/io/save_image.py` (zarr → pixel_only, png/jpeg → narrow paths, docstrings)
  - `frontend/src/api/capabilities.ts` (`lossyOmeFields` prefix matcher)
  - `packages/scistudio-blocks-imaging/tests/test_load_image_ome.py` (new, 3 cases)
  - `packages/scistudio-blocks-imaging/tests/test_save_image_capabilities.py` (new, 7 cases)
  - `packages/scistudio-blocks-imaging/tests/test_format_capabilities.py` (5 assertions updated to new fidelity)
  - `frontend/src/__tests__/LossySaveWarning.test.tsx` (5 new cases)
  - `frontend/src/__tests__/adr043-a3-smoke.test.tsx` (FR-014 smoke test updated)
  - `CHANGELOG.md`
  - `.workflow/records/1306-1371-imaging-ome-fidelity.json`
- Tests: pytest 35 pass / 0 fail (0.89s); vitest 444 pass / 13 skipped / 0 fail (4.85s, 43 files).
- Gate record: `.workflow/records/1306-1371-imaging-ome-fidelity.json`

### 7.4 W3-A — Scheduler (#1367 + #1370)

- Owner: W3-A implementer
- In scope:
  - `src/scistudio/engine/scheduler.py::resume`, `rerun_block`, `reset_block`, `_run_interactive` — emit `BLOCK_READY` on every IDLE→READY; normalize collection outputs in interactive path
  - Tests for resume/rerun/reset and interactive collection normalization
- Out of scope:
  - Any other scheduler behavior; lifecycle/state machine refactor
- Required docs: CHANGELOG entry; no ADR/spec change
- Required tests:
  - `tests/engine/test_scheduler.py` (extend): resume/rerun/reset each emit exactly one `BLOCK_READY`
  - `tests/engine/test_scheduler_interactive.py` (extend or create): bare `DataObject` and `list[DataObject]` on `is_collection=True` ports normalize via `_normalize_outputs()`

### 7.5 W3-B — Registry + Code backends (#1109 + #1309)

- Owner: W3-B implementer
- In scope:
  - `src/scistudio/blocks/registry.py::_ext_in_mapping` — implement compound→single suffix walk mirroring `IOBlock._detect_format`
  - `src/scistudio/blocks/code/backends/notebook.py` + `backends/python.py` — compute `script_cwd = context.config.resolve_working_directory(context.project_dir)` and pass to both subprocess and nbconvert
  - Tests for compound extension fallback + CodeBlock cwd
- Out of scope:
  - Loader/saver dispatch beyond `_ext_in_mapping`
  - CodeBlock exchange manifest (covered by #1281 in W1)
- Required docs: CHANGELOG entry
- Required tests:
  - `tests/blocks/test_registry.py`: `.ome.tif` falls back to block declaring only `.tif`
  - `tests/blocks/code/test_backends.py`: both backends pass `resolve_working_directory(project_dir)` as `cwd=`; subprocess sees `Path.cwd() == project_dir` when `working_directory: '.'`

### 7.6 W4-A — Frontend PortEditor capability_id (#1366)

- Owner: W4-A implementer
- In scope:
  - `frontend/src/components/PortEditorTable.tsx::handleTypeChange` + `handleExtensionChange` — clear `capability_id` (or recompute if still valid)
  - Frontend tests for both change handlers
- Out of scope:
  - Backend validation pathway
  - Other port editor functionality
- Required docs: CHANGELOG entry
- Required tests:
  - `frontend/src/components/__tests__/PortEditorTable.test.tsx` (extend or add): changing `types` clears stale `capability_id`; changing `extension` likewise; backend validation accepts the resulting workflow

### 7.7 W4-B — Completion race + Save Image dir picker (#902 + #1369)

- Owner: W4-B implementer
- In scope:
  - `src/scistudio/blocks/ai/completion.py::CompletionWatcher` — Option B: skip empty/whitespace-only reads, retry on next poll (production hardening per #902 §Fix options)
  - `tests/blocks/ai/conftest.py::StubAgent` — optionally also Option A atomic rename for fixture stability
  - `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/io/save_image.py` registry capability — flip `directory_browser` to file browser for single-image saves
  - `frontend/src/components/BottomPanel.tsx` native dialog mapping if needed
- Out of scope:
  - Multi-image save behavior (out of scope per #1369 — single-image only)
  - Other AI block lifecycle work
- Required docs: CHANGELOG entry
- Required tests:
  - `tests/blocks/ai/test_completion.py`: empty-file mid-write retried, not crash
  - `tests/blocks/test_save_image_capabilities.py`: single-image save advertises file-not-directory browse mode

## 8. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Ruff | `ruff check .` | `[ ]` | `<output path or summary>` |
| Format | `ruff format --check .` | `[ ]` | `<output path or summary>` |
| Tests | `pytest <changed-test-paths-per-wave>` | `[ ]` | `<output path or summary>` |
| Full audit | `python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json` | `[ ]` | `<output path>` |
| Sentrux | MCP `rescan`+`check_rules`+`health` or CLI `sentrux scan . && sentrux check .` | `[ ]` | `<evidence or N/A reason>` |

#### W2-B verification (PR #1388)

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Ruff | `ruff check .` | `[x]` | `All checks passed!` |
| Format | `ruff format --check .` | `[x]` | `652 files already formatted` |
| Pytest | `pytest packages/scistudio-blocks-imaging/tests/{test_load_image_ome,test_save_image_capabilities,test_format_capabilities}.py --timeout=60` | `[x]` | `35 passed in 0.89s` |
| Vitest | `npx vitest run` (frontend) | `[x]` | `448 passed, 13 skipped (43 files) in 5.51s` |
| Full audit | `python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json` | `[x]` | `status=pass, 0 findings, vulture child 6 informational` |
| Sentrux | MCP `scan` + `check_rules` | `[x]` | `pass, rules_checked=3/15, violation_count=0, quality_signal=4445, files=1110` |
| CI | `Verify Workflow Compliance` | `[x]` | https://github.com/zjzcpj/SciStudio/actions/runs/26252955593 (1m6s) |

## 9. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| (none yet) | — | — | — | — |

## 10. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux evidence when needed, commit, and PR evidence.
- [ ] PR closes every issue fixed by the dispatch.
- [ ] CI passed.
- [ ] Checklist final state matches PR and gate record.
