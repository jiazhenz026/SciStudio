[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciEasy
- Owner request: Implement the fix-in-PR items from the Phase C1 no-context audit report so the umbrella PR meets every spec success criterion before final merge into main. Specifically: P1-01 (flaky frontend test waitFor), P2-01 (pillow axes-override pixel-buffer zero bug), P2-05 (SaveImage TIFF OME-XML emission — unblocks SC-003), and P2-03 (SaveImage._resolve_format dual-source-of-truth).
- Task kind: bugfix
- Persona: implementer
- Parent tracking issue: #1204
- Umbrella sub-issue: #1296
- Umbrella PR: #1297 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-043/core-blocks-and-imaging (already includes A1/A2/A3/B1/B2 + C1 audit report)
- Agent branch: feat/issue-1296/adr043-c1-fixes
- Agent worktree: `/c/Users/jiazh/Desktop/workspace/SciEasy/.claude/worktrees/adr-043-c1-fixes` (manager pre-created)
- Audit report (your source-of-truth for findings): `docs/audit/2026-05-20-adr-043-package-migration-no-context.md`
- Manager checklist: `docs/planning/adr-043-package-migration-checklist.md` (edit ONLY rows in §6 marked "C1 fixes" if any; otherwise leave the checklist alone)
- Spec: `docs/specs/adr-043-package-migration.md` — §3 FR-001..FR-017, §5 SC-001..SC-006

## Required Rules

Read and follow:

- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/bug-fix.md
- docs/ai-developer/personas/implementer.md

Read for findings detail:

- `docs/audit/2026-05-20-adr-043-package-migration-no-context.md` §3 (P1) and §4 (P2), §10 (SC-003 evidence)
- `docs/specs/adr-043-package-migration.md` §3 FR-005, §5 SC-003

## Scope (in)

You own only these files for the fixes below:

- `frontend/src/__tests__/CapabilityDropdown.test.tsx` — P1-01 fix (waitFor around `fireEvent.change` at line ~148)
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/io/pillow_handler.py` — P2-01 fix (`_load_png` / `_load_jpeg` axes-override pixel-buffer zero bug at line ~193)
- `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/io/save_image.py` — P2-05 fix (`_write_tiff` OME-XML emission to ImageDescription tag) + P2-03 fix (`_resolve_format` to consult `format_capabilities` instead of `supported_extensions`)
- `packages/scieasy-blocks-imaging/tests/test_format_capabilities.py` — add regression test for SC-003 round-trip OME-XML preservation (load OME-TIFF → save OME-TIFF → reload → assert ome metadata equal)
- `packages/scieasy-blocks-imaging/tests/test_pillow_handler.py` (create if missing) or extend an existing imaging test — regression test for axes-override pixel buffer (P2-01)
- `CHANGELOG.md` — `[#1296]` `### Fixed` entry under `[Unreleased]`
- Your own gate record at `.workflow/records/1296-c1-fixes.json`

## Scope (out)

- All other files. P2-02 (dual sources of truth — supported_extensions still on imaging IO) is INTENTIONALLY DEFERRED — spec FR-003 only deletes supported_extensions from LoadData/SaveData (core), not imaging. P2-04 (arbitrary_types_allowed=True on Meta) is pydantic-required for the OME typed field; defer documentation.
- Spec amendments (FR-015 wording + FR-008 vs §4.5) are owner decisions; do NOT edit the spec.
- Implementation files outside the listed in-scope set.
- Other agents' branches/worktrees.
- The audit report itself (it is committed evidence; do not edit it).

If you need an out-of-scope path, stop and report back.

## Coordination

- This is the only agent dispatched for fix work; no parallel-conflict risk.
- Open your PR targeting umbrella `track/adr-043/core-blocks-and-imaging`, NOT main.
- MUST NOT use `pip install -e .`.

## TODO And Deferral Rule

Use `TODO(#NNN): <reason>. Followup: <link>.`

Known deferred items (audit's §12 recommendations not in your scope):

- P2-02 / P2-03 wider drift-detection test for supported_extensions vs format_capabilities consistency — write a small follow-up issue under #1296.
- Spec amendments (FR-015 wording + FR-008 vs §4.5) — surface to owner in your PR body; do NOT amend spec.

## Work To Do

1. **P1-01 (P1 — flaky CapabilityDropdown test):**
   - In `frontend/src/__tests__/CapabilityDropdown.test.tsx` around line 148, wrap the `fireEvent.change(...)` in an explicit `await waitFor(() => screen.getByText(/OME-TIFF/i))` (or equivalent option visibility check) BEFORE the change event, so the option list is mounted before React fires the synthetic change. Add a comment explaining why.

2. **P2-01 (P2 — pillow axes-override pixel buffer zero bug):**
   - In `pillow_handler.py` near line 193, when `axes_override` is provided, the current code returns a buffer of zeros instead of the loaded pixel data. Fix the bug so the override changes only the axes labels, not the underlying pixel buffer.
   - Add a regression test that loads a PNG with `axes_override=["y", "x"]` and asserts `image.to_memory()` returns non-zero pixel data matching the source.

3. **P2-05 (P2 — SaveImage TIFF OME-XML emission, unblocks SC-003):**
   - In `save_image.py:_write_tiff`, when `Image.Meta.ome` is non-None, serialize the OME object to XML via `ome_types.to_xml(image.meta.ome)` and pass it as the `description` kwarg (or via the `ImageDescription` tag) to `tifffile.imwrite(...)`. tifffile recognizes the OME-XML and writes it to tag 270 (`ImageDescription`).
   - Reciprocal verification: ensure `tifffile.imread` on the saved file can recover the OME-XML via the resulting TIFF's `ImageDescription` (load side already handled by tifffile's OME-XML detection inside the existing TIFF load capability).
   - Add the SC-003 integration regression test in `test_format_capabilities.py`:
     1. Construct an `Image` with `meta=Image.Meta(ome=<sample OME with physical_size_x>)`.
     2. SaveImage to `out.ome.tif` (or `out.tif`; tifffile auto-promotes when OME XML present).
     3. LoadImage from the saved file.
     4. Assert `loaded.meta.ome.images[0].pixels.physical_size_x` equals the source value.

4. **P2-03 (P2 — SaveImage._resolve_format walks supported_extensions instead of format_capabilities):**
   - In `save_image.py:_resolve_format` (~lines 64-109), replace the `SaveImage.supported_extensions.values()` walk with derivation from `cls.format_capabilities` (the canonical source under ADR-043). Mirror the pattern A1 used for the in-tree LoadData/SaveData rewrite (see `src/scieasy/blocks/io/savers/save_data.py` `_resolve_save_format`).
   - This eliminates the dual-source-of-truth drift risk noted by P2-03 of the audit.

5. **CHANGELOG entry:** `[#1296]` under `## [Unreleased]` → `### Fixed`. Describe the four fixes in one entry.

## Required Tests And Checks

- `pytest packages/scieasy-blocks-imaging/tests/test_format_capabilities.py --timeout=60` — new SC-003 regression test must pass.
- `pytest packages/scieasy-blocks-imaging/tests/ --timeout=60` — no NEW failures vs the umbrella baseline (39 pre-existing failures are owner-acknowledged debt).
- `npm test -- frontend/src/__tests__/CapabilityDropdown.test.tsx` (or `vitest run frontend/src/__tests__/CapabilityDropdown.test.tsx`) — flaky test now stable across 10 runs.
- `ruff check packages/scieasy-blocks-imaging/`
- `ruff format --check packages/scieasy-blocks-imaging/`
- `python -m scieasy.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json` — record evidence; pre-existing repo debt is owner-acknowledged.
- Sentrux: skipped with rationale if CLI unavailable.

## Gate Record Stages You Must Execute

`python -m scieasy.qa.governance.gate_record start --task-kind bugfix --issue 1296 --slug c1-fixes --branch feat/issue-1296/adr043-c1-fixes --owner-directive "Phase C1 audit follow-up fixes: P1-01 flaky test + P2-01 pillow axes-override + P2-05 SaveImage TIFF OME-XML emission (unblocks SC-003) + P2-03 SaveImage._resolve_format consistency" --include <each file> --record-path .workflow/records/1296-c1-fixes.json`

Then `plan`, `docs`, `check`, `sentrux`, `finalize` per usual.

## Output Required

- Final commit SHA(s) on your branch
- PR number + URL (target umbrella)
- Test results, especially the new SC-003 regression test (load OME → resize/process → save TIFF → reload → assert ome preserved)
- Confirm flaky test stable across 10 reruns
- Gate record path with all 6 stages done
- Codex auto-review reconciliation summary (cap 5 min wait after CI green)
- In your PR body: list the deferred items (P2-02 dual sources of truth, P2-04 arbitrary_types_allowed, spec amendment requests for FR-015 + FR-008) so the manager can act on them.

## Stop Conditions

- Out-of-scope file needed.
- The OME-XML write into TIFF cannot be implemented because `ome_types.to_xml` produces output `tifffile` cannot persist — STOP and report (alternative is weakening FR-005 capability fidelity advertisement, which is an owner decision).
- The SC-003 round-trip test cannot be made deterministic.
- Codex P1 fires on your PR — reconcile in one round.

## Codex Auto-Review Reconciliation

After CI green, wait up to 5 min for Codex auto-review; reconcile every P1/P2; cap at one round.
