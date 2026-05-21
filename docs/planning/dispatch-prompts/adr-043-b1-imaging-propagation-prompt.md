[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Audit every Image-domain ProcessBlock in scistudio-blocks-imaging and update each one to propagate `Image.Meta.ome` per the ADR-043 propagation contract (Modes A/B/C); commit an audit report enumerating each block's mode classification and ome decision.
- Task kind: refactor
- Persona: implementer
- Parent tracking issue: #1204
- Umbrella sub-issue: #1296
- Umbrella PR: #1297 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-043/core-blocks-and-imaging (already includes Phase A2 merge providing `Image.Meta.ome` and `Label.Meta.ome` fields)
- Agent branch: feat/issue-1296/adr043-b1-imaging-propagation
- Agent worktree: `/c/Users/jiazh/Desktop/workspace/SciStudio/.claude/worktrees/adr-043-b1-imaging-propagation` (manager pre-created)
- Manager checklist: `docs/planning/adr-043-package-migration-checklist.md` (edit ONLY rows in §6 marked "B1" and §10 Track B1)
- Spec: `docs/specs/adr-043-package-migration.md` (your work is Phase B1 / FR-009, FR-010)

## Required Rules

Read and follow:

- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/bug-fix.md (refactor variant)
- docs/ai-developer/personas/implementer.md
- The spec at `docs/specs/adr-043-package-migration.md` — your authoritative scope is Phase B1 in §4.3 and FR-009, FR-010 in §3.

## Scope

You own only:

- `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/preprocess/geometry.py` (`_resize_meta` helper — Mode B; update to handle `ome` field axes/pixel_size adjustment)
- `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/preprocess/axis_ops.py` (`_split_meta` helper — Mode B; propagate ome to split outputs)
- `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/projection/projection.py` (`_projected_meta` helper — Mode B; rewrite ome dimensions on axis projection)
- `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/segmentation/*.py` (Mode C blocks — add `ome=source.meta.ome` to rebuilt Meta where output preserves spatial coordinate system, e.g. cellpose_segment.py L110 mask_img and L147 Label output)
- `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/math/*.py` (Mode A — verify `meta=source.meta` intact; no-op fix expected)
- `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/morphology/*.py` (Mode A — verify)
- `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/registration/*.py` (Mode A — verify)
- `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/measurement/*.py` (Mode C — outputs are DataFrames with no image coord; legitimately drop ome and document)
- `packages/scistudio-blocks-imaging/tests/test_processblock_meta_propagation.py` (create)
- `docs/audit/adr-043-imaging-propagation-audit.md` (create — committed audit report)
- `CHANGELOG.md` (Unreleased entry only)
- Your own gate record at `.workflow/records/1296-b1-imaging-propagation.json`
- Your own checklist rows.

You must not touch:

- IO blocks: `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/io/*.py` — already migrated by A2.
- `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/types.py` — A2's territory. The `ome` field is already there.
- `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/interactive/*.py` — AppBlocks, separate concern.
- `packages/scistudio-blocks-srs/**` — that is B2 agent's territory.
- `src/scistudio/**` — out of scope for this phase.
- `frontend/src/**` — A3 agent.
- Other agents' branches/worktrees.

If you need an out-of-scope path, stop and report back.

## Coordination

- Phase A2 already merged into umbrella, providing `Image.Meta.ome` and `Label.Meta.ome` typed fields.
- B2 (SRS propagation) is running in parallel on a different package; no file overlap.
- A1 (core IO) and A3 (frontend) may still be running on different file sets.
- MUST work only on your assigned branch and worktree.
- MUST NOT use `pip install -e .`.
- Open your PR targeting `track/adr-043/core-blocks-and-imaging` (umbrella), NOT main.

## TODO And Deferral Rule

Use `TODO(#NNN): <reason>. Out of scope per <ref>. Followup: <link>.`

Known deferred items:

- Bio-Formats save support (load-only library) — out of scope per spec scope.out.

## Work To Do (matches spec §4.3 Phase B1, T-030..T-034)

1. **T-030 (Audit):** Read every Image-domain ProcessBlock file under your scope. For each block class, classify it as:
   - **Mode A** (shape-preserving same-type): the block constructs output via `OutputClass(..., meta=source.meta, ...)`. Verify `meta=source.meta` propagation is intact — no-op fix expected.
   - **Mode B** (shape-changing same-type): the block constructs output via `OutputClass(..., meta=transform_helper(source.meta, ...), ...)`. Confirm the transform helper handles `ome` field — update helper if it does not.
   - **Mode C** (cross-type): the block constructs output via `OutputClass.Meta(field1=..., ...)`. If output preserves spatial coord system (e.g. Image→Label/Mask shape-aligned with input), `ome=source.meta.ome` MUST be in the rebuilt Meta. If output drops spatial structure entirely (e.g. Image→DataFrame for measurements), `meta=None` or domain-specific Meta without ome is permitted but MUST be documented.
   
   Record each block's classification + ome decision in `docs/audit/adr-043-imaging-propagation-audit.md` (table: block_name, module_path, mode, ome_decision, justification).

2. **T-031 (Mode B fixes):** Update `_resize_meta` in geometry.py, `_projected_meta` in projection.py, `_split_meta` in axis_ops.py. Each helper must:
   - If `source.meta.ome` is None, leave new_meta.ome = None.
   - If `source.meta.ome` is non-None, copy and transform the OME object to match the new shape/axes:
     - **resize:** scale `ome.images[0].pixels.physical_size_x/y` by inverse of resize factor (smaller pixels when resize-up, larger when resize-down).
     - **projection:** drop the projected axis from `ome.images[0].pixels.dimension_order` and zero out `size_<axis>` for the dropped axis; pixel sizes for remaining axes unchanged.
     - **split:** propagate ome verbatim to each split output (no spatial transformation on split-along-channel/time).
   - Use `ome.copy(deep=True)` or pydantic model_copy to avoid mutating source.

3. **T-032 (Mode C fixes):** Walk every segmentation/*.py block. For each block where the output is shape-aligned with input (cellpose_segment.py L110 mask_img, L147 Label output, blob_detect, watershed, connected_components, cleanup, threshold), add `ome=image.meta.ome if image.meta else None` to the rebuilt Meta. For measurement/*.py blocks (region_props, colocalization, pairwise_distance) where output is a DataFrame, document the deliberate drop.

4. **T-033 (Tests):** Create `packages/scistudio-blocks-imaging/tests/test_processblock_meta_propagation.py`. Cover:
   - At least one test per Mode (A/B/C) per affected sub-package.
   - Mode A: load Image with ome.physical_size_x=0.5; run ImageCalculator; assert output.meta.ome.images[0].pixels.physical_size_x == 0.5.
   - Mode B: load Image with ome.physical_size_x=0.5; Resize(factor=0.5); assert output.meta.ome.images[0].pixels.physical_size_x == 1.0.
   - Mode B (projection): load 3-channel Image; project along 'c'; assert output.meta.ome dimensions reflect 2-channel result.
   - Mode C (cellpose mask): load Image; CellposeSegment; assert mask_img.meta.ome == input.meta.ome.
   - Mode C (cellpose Label): assert label.meta.ome == input.meta.ome.
   - Mode C (region_props legitimately drops ome): assert output is DataFrame and has no ome field expected; this is documented behavior.

5. **T-034 (Audit doc):** Commit `docs/audit/adr-043-imaging-propagation-audit.md` with the full Mode A/B/C classification table + the rationale per Mode C decision.

6. **T-034.5:** CHANGELOG entry `[#1296]` under `## [Unreleased]` → `### Changed`.

## Required Tests And Checks

- `pytest packages/scistudio-blocks-imaging/tests/test_processblock_meta_propagation.py --timeout=60`
- `pytest packages/scistudio-blocks-imaging/tests/` (broader, ensure no regression on existing tests)
- `ruff check packages/scistudio-blocks-imaging/`
- `ruff format --check packages/scistudio-blocks-imaging/`
- `python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json` — pre-existing repo debt is owner-acknowledged; if your changes add NEW findings fix them.
- Sentrux: skipped with rationale if CLI unavailable.

## Gate Record Stages You Must Execute

`python -m scistudio.qa.governance.gate_record start --task-kind refactor --issue 1296 --slug b1-imaging-propagation --branch feat/issue-1296/adr043-b1-imaging-propagation --owner-directive "Phase B1: imaging ProcessBlock OME propagation audit + fix per spec FR-009/FR-010" --include <each file> --record-path .workflow/records/1296-b1-imaging-propagation.json`

Then `plan`, `docs`, `check` (×N), `sentrux`, `finalize` per usual A1/A2 pattern.

## Output Required

Same as A-phase agents: changed paths, tests/checks, checklist rows, PR URL, gate record path, audit doc path, Codex auto-review reconciliation (cap 5 min from CI green).

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file (especially: do NOT touch types.py or io/* — they are A2's territory).
- The propagation Mode for a block is ambiguous (e.g. a block both projects axes AND changes type — Mode B + C interleaved). Report the case in your audit report and ask for guidance.
- Adding ome propagation to a Mode B helper breaks an existing test in a way that suggests the helper was deliberately wrong before — report don't auto-fix.
- CI or local checks fail unexpectedly.

## Codex Auto-Review Reconciliation

After CI green, wait up to 5 min for Codex auto-review; reconcile every P1/P2; cap at one round.
