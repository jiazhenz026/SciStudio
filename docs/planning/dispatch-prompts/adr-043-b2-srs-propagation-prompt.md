[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciEasy
- Owner request: Audit every ProcessBlock in scieasy-blocks-srs and update each one to propagate `Image.Meta.ome` per the ADR-043 propagation contract (Modes A/B/C); commit an audit report. SRSImage.Meta inherits Image.Meta so `ome` is already on it via A2's merge.
- Task kind: refactor
- Persona: implementer
- Parent tracking issue: #1204
- Umbrella sub-issue: #1296
- Umbrella PR: #1297 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-043/core-blocks-and-imaging (already includes Phase A2 merge)
- Agent branch: feat/issue-1296/adr043-b2-srs-propagation
- Agent worktree: `/c/Users/jiazh/Desktop/workspace/SciEasy/.claude/worktrees/adr-043-b2-srs-propagation` (manager pre-created)
- Manager checklist: `docs/planning/adr-043-package-migration-checklist.md` (edit ONLY rows in §6 marked "B2" and §11 Track B2)
- Spec: `docs/specs/adr-043-package-migration.md` (your work is Phase B2 / FR-009, FR-011)

## Required Rules

Read and follow:

- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/bug-fix.md (refactor variant)
- docs/ai-developer/personas/implementer.md
- The spec at `docs/specs/adr-043-package-migration.md` — Phase B2 in §4.3 and FR-009, FR-011 in §3.

## Scope

You own only:

- `packages/scieasy-blocks-srs/src/scieasy_blocks_srs/preprocess/*.py`
- `packages/scieasy-blocks-srs/src/scieasy_blocks_srs/component_analysis/*.py`
- `packages/scieasy-blocks-srs/src/scieasy_blocks_srs/spectral_extraction/*.py`
- `packages/scieasy-blocks-srs/tests/test_processblock_meta_propagation.py` (create)
- `docs/audit/adr-043-srs-propagation-audit.md` (create — committed audit report)
- `CHANGELOG.md` (Unreleased entry only)
- Your own gate record at `.workflow/records/1296-b2-srs-propagation.json`
- Your own checklist rows.

You must not touch:

- `packages/scieasy-blocks-srs/src/scieasy_blocks_srs/types.py` — SRSImage.Meta inherits Image.Meta so `ome` is already there via A2; no changes needed here (verify but don't edit).
- Any file in `packages/scieasy-blocks-imaging/**` — that is B1 agent's territory.
- `src/scieasy/**`, `frontend/src/**` — out of scope.
- Other agents' branches/worktrees.

If you need an out-of-scope path, stop and report back.

## Coordination

- Phase A2 merged into umbrella; `SRSImage.Meta` already has `ome` field via inheritance.
- B1 (imaging propagation) is running in parallel on a different package; no file overlap.
- A1, A3 may still be running on different file sets.
- Open your PR targeting `track/adr-043/core-blocks-and-imaging` (umbrella), NOT main.

## TODO And Deferral Rule

Use `TODO(#NNN): <reason>. Out of scope per <ref>. Followup: <link>.`

Known deferred items:

- Adding LoadSRSImage IO block — out of scope per spec scope.out.

## Work To Do (matches spec §4.3 Phase B2, T-040..T-046)

1. **T-040 (Audit):** Read every ProcessBlock file under your scope. For each block class, classify Mode A/B/C and record in `docs/audit/adr-043-srs-propagation-audit.md`.

2. **T-041 (Mode A verifications, no-op fixes expected):**
   - `preprocess/srs_baseline.py` — `meta=item.meta` line ~93 — verify intact.
   - `preprocess/srs_spectral_denoise.py` — `meta=item.meta` line ~96 — verify intact.
   - `spectral_extraction/extract_spectrum.py` — read upstream meta; output is DataFrame so deliberate drop OK (Mode C). Verify.

3. **T-042 (Mode C fix — Label output):** `component_analysis/srs_kmeans.py` line ~121 currently builds `Label.Meta(source_file=getattr(item.meta, "source_file", None) if item.meta is not None else None)` — Label output is shape-aligned with SRSImage input (cluster assignments share y/x layout), so add `ome=getattr(item.meta, "ome", None) if item.meta is not None else None` to the rebuilt Meta.

4. **T-043 (Mode C confirmation):** `preprocess/srs_calibrate.py` line ~95 uses `item.meta.model_dump()` + override. Because `model_dump()` preserves all fields not in the override (including the new `ome` field), this block is already correct — `new_meta = SRSImage.Meta(**old_meta, ...overrides)` will carry `ome` automatically. Add an explicit test asserting this.

5. **T-044 (Mode C legitimate drop documentation):** `component_analysis/srs_pca.py` line ~144 and `srs_unmix.py` line ~206 both set `meta=None` on outputs because PC scores and end-member abundance maps don't share the source's pixel coordinate system (dimensionality is reduced). Document this in the audit report as "Mode C legitimate drop — output is not spatially aligned with input". DO NOT add ome propagation for these.

6. **T-045 (Tests):** Create `packages/scieasy-blocks-srs/tests/test_processblock_meta_propagation.py`. Cover:
   - Mode A: SRSImage in with ome → SRSSpectralDenoise → ome present and equal.
   - Mode A: SRSImage in with ome → SRSBaseline → ome present and equal.
   - Mode C with model_dump: SRSImage in with ome → SRSCalibrate → ome present and equal (proves model_dump+override carries it).
   - Mode C fix: SRSImage in with ome → SRSKMeansCluster → Label output has matching ome.
   - Mode C legitimate drop: SRSImage in with ome → SRSPCA → output `meta is None` (deliberate, documented behavior).

7. **T-046 (Audit doc):** Commit `docs/audit/adr-043-srs-propagation-audit.md` with the full Mode A/B/C classification table + Mode C decisions justified.

8. **T-046.5:** CHANGELOG entry `[#1296]` under `## [Unreleased]` → `### Changed`.

## Required Tests And Checks

- `pytest packages/scieasy-blocks-srs/tests/test_processblock_meta_propagation.py --timeout=60`
- `pytest packages/scieasy-blocks-srs/tests/` (broader)
- `ruff check packages/scieasy-blocks-srs/`
- `ruff format --check packages/scieasy-blocks-srs/`
- `python -m scieasy.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json`
- Sentrux: skipped if unavailable with rationale.

## Gate Record Stages You Must Execute

`python -m scieasy.qa.governance.gate_record start --task-kind refactor --issue 1296 --slug b2-srs-propagation --branch feat/issue-1296/adr043-b2-srs-propagation --owner-directive "Phase B2: SRS ProcessBlock OME propagation audit + fix per spec FR-009/FR-011" --include <each file> --record-path .workflow/records/1296-b2-srs-propagation.json`

Then `plan`, `docs`, `check`, `sentrux`, `finalize` per usual.

## Output Required

Same as A-phase agents.

## Stop Conditions

- Out-of-scope file needed.
- A block's propagation Mode is ambiguous — report.
- Tests fail unexpectedly.

## Codex Auto-Review Reconciliation

After CI green, wait up to 5 min for Codex auto-review; reconcile P1/P2; cap at one round.
