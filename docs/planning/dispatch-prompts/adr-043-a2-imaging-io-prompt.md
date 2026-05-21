[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Migrate scistudio-blocks-imaging IO blocks to ADR-043 explicit `FormatCapability`; add PNG/JPEG (Pillow) and Bio-Formats microscopy (`.czi`/`.nd2`/`.lif`/`.oir`/`.oib`) load-only handlers under an `imaging[bioformats]` optional install extra; add `ome: ome_types.model.OME | None` typed field to `Image.Meta` and `Label.Meta`.
- Task kind: feature
- Persona: implementer
- Parent tracking issue: #1204
- Umbrella sub-issue: #1296
- Umbrella PR: #1297 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-043/core-blocks-and-imaging
- Agent branch: feat/issue-1296/adr043-a2-imaging-io
- Agent worktree: `.claude/worktrees/adr-043-a2-imaging/` (provided by manager)
- Manager checklist: `docs/planning/adr-043-package-migration-checklist.md` (edit ONLY rows in §6 marked "A2" and §8 Track A2)
- Spec: `docs/specs/adr-043-package-migration.md` (your work is Phase A2 / FR-004..FR-008, FR-017)

## Required Rules

Read and follow:

- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/new-feature.md
- docs/ai-developer/personas/implementer.md
- The spec at `docs/specs/adr-043-package-migration.md` — your authoritative scope is Phase A2 in §4.3 and FR-004..FR-008, FR-017 in §3.
- `cellprofiler/python-bioformats` and `ome-types` package docs (you may web-fetch if needed — do not blindly copy upstream code).

## Scope

You own only:

- `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/types.py` (add `ome` field to `Image.Meta` and `Label.Meta` only — do not touch other type classes' Meta unless required for inheritance)
- `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/io/load_image.py`
- `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/io/save_image.py`
- `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/io/pillow_handler.py` (create)
- `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/io/bioformats_handler.py` (create)
- `packages/scistudio-blocks-imaging/pyproject.toml` (add `[bioformats]` extras + `ome-types` required dep)
- `packages/scistudio-blocks-imaging/tests/test_format_capabilities.py` (create)
- `packages/scistudio-blocks-imaging/tests/test_image_meta_ome.py` (create)
- `packages/scistudio-blocks-imaging/tests/test_bioformats_handler.py` (create, gated by extras availability)
- `CHANGELOG.md` (Unreleased entry only)
- Your own gate record at `.workflow/records/1296-a2-imaging-io.json`
- Your own checklist rows.

You must not touch:

- Any ProcessBlock under `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/{math,morphology,preprocess,projection,registration,segmentation,measurement}/` — that's Phase B1 (separate agent, after A2 merges). Image.Meta.ome field addition is your job; teaching ProcessBlocks to propagate it is B1's job.
- `src/scistudio/blocks/io/loaders/load_data.py`, `src/scistudio/blocks/io/savers/save_data.py` — A1 agent.
- `packages/scistudio-blocks-srs/**`, `packages/scistudio-blocks-lcms/**` — B2 / out of scope.
- `frontend/src/**` — A3 agent.
- `src/scistudio/blocks/io/io_block.py`, `capabilities.py`, `simple_io.py`, `registry.py`, `materialisation.py` — already migrated.
- `src/scistudio/engine/**`, `src/scistudio/workflow/validator.py` — out of scope.
- Other agents' branches/worktrees.

If you need an out-of-scope path, stop and report back.

## Coordination

- A1 (core IO) and A3 (frontend) are running in parallel; independent file sets.
- B1 (imaging ProcessBlock propagation) depends on your A2 merge — do not preemptively touch ProcessBlocks.
- MUST work only on your assigned branch and worktree.
- MUST NOT use `pip install -e .`. For Bio-Formats handler testing, lazy-import the dependency; tests must be skippable when extras are not installed (use `pytest.importorskip("bioformats")`).
- Open your PR targeting `track/adr-043/core-blocks-and-imaging`.

## TODO And Deferral Rule

Deferred work uses `TODO(#NNN): <reason>. Out of scope per <ref>. Followup: <link>.`

Known deferred items:

- OME-Zarr v0.4 first-class file-format support — out of scope per spec scope.out. If user requests, open new sub-issue under #1204.
- Bio-Formats save support — out of scope (python-bioformats is load-only by library design).
- Per-format pydantic schemas for CZI/ND2/LIF/OIR — replaced by unified `ome_types.model.OME` carrier per spec FR-006.

## Work To Do (matches spec §4.3 Phase A2, T-010..T-018)

1. **T-010:** Add `ome-types>=0.5,<0.6` to `packages/scistudio-blocks-imaging/pyproject.toml` `[project] dependencies` (required, not optional).

2. **T-011:** Add `[project.optional-dependencies] bioformats = ["python-bioformats>=4.0", "javabridge>=1.0"]` to imaging pyproject.toml. Mirror the existing `[cellpose]` extras pattern.

3. **T-012:** Add `ome: OME | None = None` field to `Image.Meta` (in `types.py`). Add `ome: OME | None = None` field to `Label.Meta` (currently inherits BaseModel directly, NOT Image.Meta — add field explicitly). Verify `SRSImage.Meta` automatically inherits the new field via `class Meta(Image.Meta)` chain (no SRS changes needed for ome itself; that's confirmed by inspection — but include a unit test that asserts `SRSImage.Meta` accepts `ome=<OME>`).

4. **T-013:** Create `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/io/pillow_handler.py` with `_load_png`, `_load_jpeg`, `_save_png`, `_save_jpeg` functions. Map PIL's EXIF / text chunks / ICC profile to `Image.Meta.ome` minimally (at minimum populate `physical_size_x/y` from EXIF DPI when present).

5. **T-014:** Create `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/io/bioformats_handler.py` with lazy-import + clear missing-extras error. Implement load-only handlers for `.czi`, `.nd2`, `.lif`, `.oir`, `.oib`. Use `bioformats.OMEXML` (or `bioformats.get_omexml_metadata`) + `ome_types.from_xml(...)` to populate `Image.Meta.ome`. The pixel data goes into the `Image` via existing storage_ref / persist_array machinery (consult ADR-031 for the persist contract — DO NOT bypass storage).

6. **T-015:** Declare `LoadImage.format_capabilities` per spec FR-004 covering:
   - `imaging.image.tiff.load` (handler: tifffile, extensions `.tif`/`.tiff`, OME-TIFF detected inside the handler)
   - `imaging.image.zarr.load` (handler: zarr, vanilla zarr)
   - `imaging.image.png.load` (handler: pillow_handler._load_png)
   - `imaging.image.jpeg.load` (handler: pillow_handler._load_jpeg, extensions `.jpg`/`.jpeg`)
   - `imaging.image.czi.load`, `imaging.image.nd2.load`, `imaging.image.lif.load`, `imaging.image.oir.load`, `imaging.image.oib.load` (handler: bioformats_handler.*)
   - All `metadata_fidelity=MetadataFidelity(level="format_specific", format_metadata_reads=("ome",), typed_meta_reads=("pixel_size","z_spacing","channels","axes"))`.

7. **T-016:** Declare `SaveImage.format_capabilities` per spec FR-005 — writable formats ONLY (`imaging.image.tiff.save`, `imaging.image.zarr.save`, `imaging.image.png.save`, `imaging.image.jpeg.save`). Bio-Formats family MUST NOT appear. `typed_meta_writes=("pixel_size","channels")` for PNG/JPEG (EXIF-mappable only); TIFF/zarr can declare more.

8. **T-017:** Add tests:
   - `test_format_capabilities.py` — capability count, IDs, defaults, fidelity, ambiguity, registry round-trip.
   - `test_image_meta_ome.py` — Image.Meta.ome round-trip, Label.Meta.ome round-trip, SRSImage.Meta inherits ome, `with_meta(ome=...)` works.
   - `test_bioformats_handler.py` — gated by `pytest.importorskip("bioformats")`. For each Bio-Formats subset member with a fixture, assert returned `Image.Meta.ome.images[0].pixels.physical_size_x is not None` (or document fixture-missing as `pytest.skip`). Always-pass test: missing-extras failure mode — mock import failure and assert the error message names `imaging[bioformats]`.

9. **T-018:** CHANGELOG entry `[#1296]` under `## [Unreleased]` → `### Added`.

## Required Tests And Checks

- `pytest packages/scistudio-blocks-imaging/tests/test_format_capabilities.py packages/scistudio-blocks-imaging/tests/test_image_meta_ome.py packages/scistudio-blocks-imaging/tests/test_bioformats_handler.py --timeout=60`
- `pytest packages/scistudio-blocks-imaging/tests/` (broader) — ensure no regression on existing imaging tests.
- `ruff check packages/scistudio-blocks-imaging/`
- `ruff format --check packages/scistudio-blocks-imaging/`
- `python -m scistudio.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json` — record path. Pre-existing repo debt is owner-acknowledged; if your changes add NEW findings, fix them.
- Sentrux: record skipped with rationale if CLI/MCP unavailable.

## Gate Record Stages You Must Execute

Same pattern as A1 agent (see A1 prompt). Your slug is `a2-imaging-io`. Your record path is `.workflow/records/1296-a2-imaging-io.json`.

## Output Required

Same shape as A1: changed paths, tests/checks results, checklist rows, PR URL, gate record path, Codex auto-review reconciliation evidence.

## Stop Conditions

Same as A1, with addition:

- If you cannot install `python-bioformats` locally for testing the bioformats handler, document that the bioformats tests are pytest.importorskip-gated and skip locally; DO NOT mock the load path itself.
- If `ome-types>=0.5` does not install on your environment, stop and report — this is a hard dependency per FR-017.

## Codex Auto-Review Reconciliation

After your PR opens and CI runs, read every Codex auto-review comment and explicitly accept, defer, or reject each one on the record before reporting done. Cap at one round per ADR-042 norms.
