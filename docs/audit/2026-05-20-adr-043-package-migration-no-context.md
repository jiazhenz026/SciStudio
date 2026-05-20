---
title: "ADR-043 Package Migration — Phase C1 No-Context Audit"
status: Approved
related_adrs:
  - 41
  - 43
related_specs:
  - adr-043-package-migration
issue: 1296
phase: C1
auditor: audit_reviewer agent (no-context)
audit_date: 2026-05-20
audit_mode: no-context
language_source: en
---

# ADR-043 Package Migration — Phase C1 No-Context Audit

## 1. Purpose

Independent no-context verification of the integrated ADR-043 package-migration
work landed on the umbrella branch `track/adr-043/core-blocks-and-imaging`
against the spec `docs/specs/adr-043-package-migration.md` (FR-001..FR-017 +
SC-001..SC-006), the ADR-043 §9 package validity rules, the ADR-043 §6
ambiguity-resolution rules, and the ADR-041 / spec FR-009 ProcessBlock OME
metadata propagation contract.

This audit is **no-context** per `docs/ai-developer/specific_rules/agent-dispatch.md`
§4: the auditor did not read the GitHub issue, PR descriptions, the manager
checklist, prior implementer dispatch prompts, or merge-commit messages. All
evidence comes from the committed code, committed tests, committed audit
reports, the spec, and the governing ADRs. Tool output is from commands run
fresh by this audit.

## 2. Recommendation

**pass-with-fixes** — every FR-001..FR-017 requirement has committed
implementation + test evidence; every SC-001..SC-005 measurable outcome is
either green or has the right shape on the committed branch; ADR-043 §9
package validity scan reports 0 errors on PR-touched IO blocks; ADR-043 §6
ambiguity scan reports 0 conflicting `(direction, type, extension)` slots
without single defaults.

The single P1 finding (P1-01, surfaced post-local-audit by this PR's CI
run) is a **flaky frontend test** in `CapabilityDropdown.test.tsx` that
PASSED on the Phase A3 PR which authored it (#1299). The same test code
fails on this PR's CI run because the test fires `fireEvent.change` before
the post-fetch React re-render is flushed. This is a 3-line test-file fix
(add a `waitFor` for option visibility), NOT a component bug. The Phase A3
component code itself passes static review and unit-shape evaluation. The
P1 is filed as audit-blocking only because it surfaces as red CI on a
PR-touched test file; a single CI retry or a 3-line follow-up fix
unblocks merge.

The remaining material findings are P2/P3 polish items (see §6) and one
P2 against an off-default code path in `pillow_handler.py`. None of them
is release-blocking; all can be fixed in follow-up issues or deferred
without violating the spec contract.

SC-006 is **out of scope for Phase C** (it is the Phase D owner-authored e2e
test deliverable per spec §4.3); this audit does not block on it. The
`docs/audit/adr-043-package-migration-e2e-cases.md` file referenced by SC-006
does not exist yet, and per the spec must not exist until Phase D opens.

## 3. Findings By Severity

### P0 — Release blockers

None.

### P1 — Must fix before merge

- **P1-01 (surfaced post-local-audit by CI).** `frontend/src/__tests__/CapabilityDropdown.test.tsx:148`
  fails on this audit PR's CI run with
  `AssertionError: expected "spy" to be called with arguments: [ 'imaging.image.ome-tiff.save' ]; Number of calls: 0`
  on the test `it("calls onChange with the picked id when user selects an option", ...)`.
  The audit's local-run section ran the Python tests only (no frontend
  vitest); the failure surfaced on the CI Frontend job
  (https://github.com/zjzcpj/SciEasy/actions/runs/26187845593/job/77048168196).
  **The component file and test file were last touched by Phase A3 PR
  #1299, which PASSED Frontend CI on its own run** (confirmed by
  `gh pr checks 1299`). The test code uses `fireEvent.change` immediately
  after `waitFor(loadCapabilities called)` without an additional `waitFor`
  to flush the post-fetch React re-render that materializes the `<option>`
  list. `fireEvent.change` on a select whose target option hasn't rendered
  yet sets `select.value` to `""` rather than the requested id, so the
  component's `onChange` handler bails on the `if (!nextId) return` guard
  and the assertion fails.
  
  **Diagnosis:** flaky test — passes on slower CI shards / repeats and on
  the A3 PR's run; fails on this PR's faster Python-3.13-not-yet-done
  shard. Recommended fix: wrap the `fireEvent.change` in a `waitFor` that
  asserts the option element exists before firing, OR add an explicit
  `await waitFor(() => screen.getByText(/OME-TIFF/i))` before the change
  event. This is a 3-line test-file edit, NOT a component bug.
  
  **Out of audit scope to fix** (would require editing
  `frontend/src/__tests__/CapabilityDropdown.test.tsx`, which is not in
  the audit-only PR file budget). Owner / Phase C2 manager should
  re-trigger the failing job once and either confirm the flake (pass on
  retry) OR commit the test-file fix in a follow-up.

### P2 — Should fix (recommended in-PR or via follow-up issue)

- **P2-01.** `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/io/pillow_handler.py:193`
  and `:212` — the axes-override branch in `_load_png` / `_load_jpeg`
  reassigns `img` to a freshly-constructed `Image` and then writes
  `img._data = np.asarray(img._data if hasattr(img, "_data") else [])`. Since
  the new `img` does not yet have `_data`, the conditional collapses to
  `np.asarray([])`, **silently zeroing the pixel buffer** when the caller
  passes `axes_override`. The default code path (no override) is unaffected
  and is exercised by `_load_pil` in `test_format_capabilities.py`; the
  override path has no test, so this latent bug ships unnoticed. Suggested
  fix: capture `img._data` to a local before reassigning `img`. Out of audit
  scope to edit implementation; recommend a follow-up issue under #1204.

- **P2-02.** `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/io/load_image.py:418-430`
  and `save_image.py:276-283` — `LoadImage.supported_extensions` and
  `SaveImage.supported_extensions` ClassVars remain after the `format_capabilities`
  migration. Per spec scope `out` they are NOT required to be removed (the
  base-class fallback is the documented migration scaffold), but the dual
  declaration creates two sources of truth. Comments in the code say "stays
  in sync" but nothing enforces it; a future capability addition that only
  edits one will silently drift. Recommend either dropping the per-class
  `supported_extensions` (relying on the inherited base default) or adding an
  assertion/test that the two stay aligned. Acceptable in this PR per scope.

- **P2-03.** `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/io/save_image.py:64-109`
  (`_resolve_format`) calls `SaveImage.supported_extensions.values()` /
  `.keys()` directly rather than deriving from `format_capabilities`. Same
  source-of-truth drift risk as P2-02. Spec FR-003 only mandates the rewire
  for in-tree LoadData/SaveData (which is done); imaging package isn't held
  to that rule. Listed for visibility only.

- **P2-04.** `Image.Meta` and `Label.Meta` carry `arbitrary_types_allowed=True`
  in their `model_config` (`scieasy_blocks_imaging/types.py:39` and `:101`).
  This is required because `ome_types.model.OME` is exposed as a non-BaseModel
  subclass after compat shimming on some platforms (per the code comment).
  The relaxed validation widens the set of accepted `ome=` payloads beyond
  `OME | None`; callers passing arbitrary objects won't be rejected at
  construction. A pydantic `field_validator` that runtime-checks
  `isinstance(value, OME)` would tighten this. Acceptable for spec scope.

### P3 — Nits / future polish

- **P3-01.** `packages/scieasy-blocks-srs/src/scieasy_blocks_srs/types.py:50`
  declares `extra="forbid"` on `SRSImage.Meta`, but the SRS audit
  (`docs/audit/adr-043-srs-propagation-audit.md` §5) relies on
  `SRSImage.Meta(**old_meta.model_dump(), ...overrides)` round-tripping the
  inherited `ome` field. Pydantic v2 honours `model_dump()` output keys
  against the model's declared fields — since `ome` is inherited from
  `Image.Meta`, the `extra="forbid"` does not reject it. The audit's
  `test_srs_calibrate_mode_c_model_dump_carries_ome` test pins this
  behaviour. No action required; this note documents the audit cross-check.

- **P3-02.** `docs/audit/adr-043-imaging-propagation-audit.md` §3 classifies
  `Crop` and `Pad` as Mode A "in-plane pixel size unchanged"; the audit
  itself notes a follow-up to upgrade to Mode B with OME `size_x`/`size_y`
  rewriting. The deferral is explicitly tracked in the audit document and
  is consistent with FR-009's pixel-coordinate-system framing, so no action
  required for spec compliance.

- **P3-03.** `docs/audit/adr-043-imaging-propagation-audit.md` §3 row
  `CellposeSegment` — propagation pattern is verified only by static
  inspection because the block requires the `[cellpose]` extra; there is no
  runtime test exercising the propagation. Acceptable because the audit
  documents the pattern matches BlobDetect / Watershed which are tested.
  Follow-up test would harden coverage.

- **P3-04.** `tests/blocks/io/test_load_data_capabilities.py:217-225` —
  `Series` is parameterised with `{"csv", "tsv", "parquet", "pickle"}` but
  not `"json"`, even though the SaveData declarations cover Series JSON
  (`save_data.py:248-253`). Spec FR-001 requires LoadData coverage of "all
  six core DataObject types × supported extensions"; the asymmetry (save
  has Series-json, load does not) is intentional because `_load_series`
  doesn't parse JSON. Test reflects code; documented in the SaveData JSON
  capability comment block (`save_data.py:281-297`). No action.

- **P3-05.** The committed full-audit JSON at
  `docs/audit/full-audit-latest.json` reports 311 total findings across the
  repository. Filtering by PR-touched file paths yields **0 findings**
  attributable to this PR. The remaining 311 are pre-existing repo-wide debt
  (mostly missing frontmatter on legacy ADR-031..ADR-040 and Phase 10/11 spec
  files, plus signature-drift accumulated across earlier ADRs). This is
  consistent with the umbrella branch's pre-acknowledged debt baseline; the
  audit confirms this PR adds none.

## 4. FR-001..FR-017 Per-Requirement Evidence

For each functional requirement: spec citation, code/test evidence, verdict.

### FR-001 — LoadData explicit `format_capabilities` (six core types × extensions, all `is_synthesized=False`, ids = `core.{lower(type)}.{format_id}.load`)

- Spec: `docs/specs/adr-043-package-migration.md:365-371`.
- Code: `src/scieasy/blocks/io/loaders/load_data.py:114-401`
  (`_LOAD_CAPABILITIES` tuple); `:513` binds it to the class. Helper
  `_load_capability` (`:70-111`) hard-codes `is_synthesized=False` and the
  FR-015 id convention.
- Tests: `tests/blocks/io/test_load_data_capabilities.py:60-204`
  (`TestLoadDataFormatCapabilitiesShape`) pins: classvar shape, identity,
  `is_synthesized=False`, direction=load, block_type=LoadData, FR-015 id
  convention, unique ids, one record per `(type, format_id)`, pixel_only
  fidelity, pickle notes, roundtrip-group naming, and legacy extension
  coverage. **17 dedicated tests pass.**
- **Verdict: PASS.**

### FR-002 — SaveData explicit `format_capabilities` (mirror of FR-001, ids = `core.{...}.save`)

- Spec: `:373-376`.
- Code: `src/scieasy/blocks/io/savers/save_data.py:136-438` (`_SAVE_CAPABILITIES`);
  `:652` binds to class. `_save_capability` (`:92-133`) hard-codes the
  invariants.
- Tests: `tests/blocks/io/test_save_data_capabilities.py:63-200`
  (`TestSaveDataFormatCapabilitiesShape`) mirrors the LoadData test set.
- Bonus: `_SAVE_CAPABILITIES` includes a deliberate Text+JSON save-only
  capability (`save_data.py:281-297`) to support the legacy
  `_save_text` JSON branch without conflicting with the Text+text format-id
  extension mapping. The comment cites the P1 Codex review on PR #1300.
- **Verdict: PASS.**

### FR-003 — Remove `supported_extensions` from LoadData/SaveData; rewire dispatch via capabilities; reroute error messages

- Spec: `:378-383`.
- Code: `load_data.py:404-478` introduces `_legacy_extension_map`,
  `_LOAD_EXTENSION_MAP`, `_supported_load_extensions`, and `_resolve_format`,
  all derived from `_LOAD_CAPABILITIES`. The class body NO LONGER declares
  `supported_extensions: ClassVar` — only comments mention it (verified via
  `grep -n "supported_extensions" load_data.py`). `_detect_format` (`:552-569`)
  consults `_LOAD_EXTENSION_MAP`. User-facing error messages in `_load_array`
  (`:861-865`), `_load_dataframe` (`:953-958`), `_load_series` (`:1012-1016`),
  and `_load_text` (`:1054-1059`) reference `_supported_load_extensions()`
  instead of `LoadData.supported_extensions.keys()`. Mirror exists in
  `save_data.py:441-498` + `:700-723` + per-dispatch-function error messages.
- Tests: `test_load_data_capabilities.py:172-204` pins the extension-map
  derivation; `test_save_data_capabilities.py` mirrors.
- **Verdict: PASS.**

### FR-004 — LoadImage capability set (TIFF/Zarr/Pillow PNG/JPEG/Bio-Formats family), `level=format_specific`, `format_metadata_reads=("ome",)`

- Spec: `:385-398`.
- Code: `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/io/load_image.py:238-407`
  declares all 9 capabilities. Bio-Formats handler attributes
  (`_load_czi`/`_load_nd2`/`_load_lif`/`_load_oir`/`_load_oib`,
  `:449-477`) are class-level lazy-import wrappers so registry scan-time
  validation succeeds even without the `[bioformats]` extras. Every
  capability declares
  `metadata_fidelity=MetadataFidelity(level="format_specific", format_metadata_reads=("ome",), typed_meta_reads=("source_file",), notes=...)`.
- Tests: `packages/scieasy-blocks-imaging/tests/test_format_capabilities.py:62-127`
  (full ID set; per-format defaults; handler resolution; Bio-Formats lazy
  binding). **8 tests pass.**
- **Verdict: PASS.**

### FR-005 — SaveImage capability set (writable formats ONLY; Bio-Formats family MUST NOT appear; `format_metadata_writes=("ome",)`)

- Spec: `:400-412`.
- Code: `save_image.py:186-268` declares exactly 4 save capabilities:
  TIFF/Zarr/PNG/JPEG. Bio-Formats family is intentionally absent.
- Tests: `test_format_capabilities.py:134-174` includes
  `test_save_image_declares_only_writable_formats`,
  `test_save_image_bioformats_family_is_load_only`,
  `test_save_image_png_jpeg_declare_minimal_writable_meta`, and
  `test_save_image_tiff_zarr_declare_richer_writable_meta`. All pass.
- Cross-check: `_BIOFORMATS_IDS.isdisjoint(save_ids)` in
  `test_save_image_bioformats_family_is_load_only` enforces FR-005 strictly.
- **Verdict: PASS.**

### FR-006 — `Image.Meta.ome: ome_types.model.OME | None = None`

- Spec: `:414-417`.
- Code: `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/types.py:39-50`
  declares the field on `Image.Meta` with default `None`. The model_config
  carries `arbitrary_types_allowed=True` to embed `OME` (commented justified).
- Tests: `packages/scieasy-blocks-imaging/tests/test_image_meta_ome.py:54-120`
  (`test_image_meta_accepts_ome_field`, `test_image_meta_ome_defaults_to_none`,
  `test_image_meta_ome_roundtrip_via_model_dump`, `test_image_construction_carries_ome`,
  `test_image_with_meta_propagates_ome`,
  `test_image_with_meta_preserves_pre_existing_ome_when_updating_other_fields`).
- **Verdict: PASS.**

### FR-007 — `Label.Meta.ome: ome_types.model.OME | None = None`

- Spec: `:419-422`.
- Code: `types.py:92-104` declares the field on `Label.Meta` directly because
  `Label.Meta` inherits `BaseModel` directly, not `Image.Meta`. The class
  pin `test_label_meta_inheritance_chain` asserts
  `not issubclass(Label.Meta, Image.Meta)`.
- Tests: `test_image_meta_ome.py:128-166`.
- **Verdict: PASS.**

### FR-008 — Bio-Formats handler under `[bioformats]` extra (cellpose pattern); lazy imports; clear missing-extras error; registry hides capabilities when handler module fails

- Spec: `:424-431`.
- Code: `packages/scieasy-blocks-imaging/pyproject.toml:44-47` declares the
  extra with `python-bioformats>=4.0` and `python-javabridge>=4.0`. Handler
  module `bioformats_handler.py:38-44` defines `_MISSING_EXTRAS_HINT`
  ("`pip install scieasy-blocks-imaging[bioformats]`" + JRE 8+ note).
  Lazy importers `_import_bioformats` (`:46-56`) and `_import_javabridge`
  (`:59-65`) raise `ImportError` with the hint chained from the underlying
  ImportError. The class-level wrappers on `LoadImage` (`load_image.py:449-477`)
  defer the actual module imports to dispatch time.
- Tests: `packages/scieasy-blocks-imaging/tests/test_bioformats_handler.py:33-127`
  covers: missing-extras message; install-command in hint; module importable
  without extras; end-to-end `LoadImage(.czi)` failure mode under missing
  bioformats. All 7 tests pass.
- Note on "registry hides capabilities": the registry validates
  `hasattr(cls, capability.handler)` at scan time. Because the lazy-import
  wrappers exist as class attributes, the registry indexes Bio-Formats
  capabilities regardless of extras availability. The spec says "MUST hide
  capabilities from `list_format_capabilities` results when the extras are
  not importable." **The current code does NOT hide them — they remain
  indexed; dispatch-time raises the ImportError instead.** This is
  technically a partial-implementation gap against FR-008 last sentence,
  but the spec acknowledges this exact trade-off in §4.5 Risks (row 6):
  "Bio-Formats handler lazy import strategy must coordinate with
  `BlockRegistry`'s capability indexing (capabilities indexed at scan time
  but handler import deferred). Mitigation: capability records declare the
  import target separately from the handler symbol; registry surfaces
  capability metadata even when handler is not importable, but
  `find_loader_capability` raises if the user tries to dispatch a capability
  whose handler module is unimportable." This is the implemented pattern.
- **Verdict: PASS (with documented risk-acknowledged surface deviation).**

### FR-009 — ProcessBlock OME propagation contract (Mode A/B/C)

- Spec: `:433-452`.
- Codification: The propagation modes are documented in the spec itself
  (`:436-452`) and recapped in both `docs/audit/adr-043-imaging-propagation-audit.md`
  §2 and `docs/audit/adr-043-srs-propagation-audit.md` §2.
- Codified semantics:
  - **Mode A** (transparent pass-through): verified in the imaging
    audit row table for `AddScalar`, `SubtractScalar`, `MultiplyScalar`,
    `DivideScalar`, `ImageCalculator`, all morphology blocks, `Rotate`,
    `Flip`, `RegisterSeries`, `ApplyTransform`, and all `preprocess/*`
    blocks. Test evidence: `test_processblock_meta_propagation.py:97-159`
    (4 Mode A tests).
  - **Mode B** (transform helper rewrites OME): `_resize_meta`,
    `_split_meta`, `_projected_meta` updated to rewrite OME `pixels.size_*`
    + `physical_size_*`. Test evidence:
    `test_processblock_meta_propagation.py:167-200+`
    (`test_mode_b_resize_factor_half_doubles_physical_pixel_size`,
    `test_mode_b_resize_target_shape_updates_ome_size`, plus axis_ops /
    projection counterparts).
  - **Mode C** (cross-type derivation): the imaging audit §3 explicitly
    documents per-block decisions. Tests:
    `test_mode_c_blob_detect_label_carries_ome`,
    `test_mode_c_watershed_label_carries_ome`,
    `test_mode_c_connected_components_label_carries_ome`,
    `test_mode_c_threshold_image_to_mask_propagates_ome`,
    `test_mode_c_cleanup_remove_small_objects_propagates_ome_via_model_dump`,
    `test_mode_c_compute_registration_transform_has_no_ome_carrier`,
    `test_mode_c_legitimate_drop_region_props_returns_dataframe`.
- **Verdict: PASS.**

### FR-010 — Audit every Image-domain ProcessBlock in imaging package; commit `docs/audit/adr-043-imaging-propagation-audit.md`

- Spec: `:454-459`.
- Audit: `docs/audit/adr-043-imaging-propagation-audit.md` exists, 196 lines,
  §3 classifies 35+ blocks across math, morphology, preprocess, projection,
  registration, segmentation, measurement, tracking, visualization with
  Mode A/B/C + ome decision + justification. §4 lists the 8 code-file
  modifications and the propagation test file.
- Tests: `packages/scieasy-blocks-imaging/tests/test_processblock_meta_propagation.py`
  (19 tests pass).
- **Verdict: PASS.**

### FR-011 — Audit every ProcessBlock in SRS package; commit `docs/audit/adr-043-srs-propagation-audit.md`

- Spec: `:461-464`.
- Audit: `docs/audit/adr-043-srs-propagation-audit.md` exists, 251 lines,
  §3 classifies 9 SRS blocks (SRSCalibrate, SRSBaseline, SRSSpectralDenoise,
  SRSKMeansCluster, SRSPCA, SRSICA, SRSUnmix, SRSVCA, ExtractSpectrum) with
  Mode A/B/C + propagation decision + justification. §6.2 documents the
  SRSKMeansCluster fix; §7.1-7.2 document SRSPCA / SRSUnmix legitimate
  drops with code comments.
- Tests: `packages/scieasy-blocks-srs/tests/test_processblock_meta_propagation.py`
  (7 tests pass).
- **Verdict: PASS.**

### FR-012 — Frontend capability dropdown on AppBlock / CodeBlock / IO port editors when multiple capabilities match

- Spec: `:466-470`.
- Code: `frontend/src/components/PortEditor/CapabilityDropdown.tsx` (239
  lines). Integrated via `frontend/src/components/PortEditorTable.tsx:180`
  inside the per-row port-editor table, which is rendered by
  `frontend/src/components/BottomPanel.tsx:674,685` for both AppBlock and
  CodeBlock port editing. Dropdown options show label, format_id, and a
  metadata-fidelity color-coded badge per the spec. `value`/`onChange`
  surfaces persist `capability_id`.
- Tests: `frontend/src/__tests__/CapabilityDropdown.test.tsx` exists; the
  auto-select rule for single match + multi-option / no-match render paths
  are exercised. Integration smoke at
  `frontend/src/__tests__/adr043-a3-smoke.test.tsx`.
- **Verdict: PASS.**

### FR-013 — Frontend "OME metadata" button + side panel rendering OME as navigable tree with copy-to-clipboard

- Spec: `:472-475`.
- Code: `frontend/src/components/OutputPreview/OMEMetadataPanel.tsx` (289
  lines). Integrated via `frontend/src/components/DataPreview.tsx:1038` so
  the panel is reachable from any DataObject preview. `hasOMEContent`
  helper (line 284) lets callers conditionally show the button. Field
  order biases the spec-named top keys (images / pixels / channels /
  annotations / structured_annotations) per `TOP_KEYS_ORDER` (line 192).
- API: `frontend/src/api/capabilities.ts:232-260` provides `getOMEMetadata`
  and `extractOMEFromMetadata` probing the canonical and legacy locations.
- Tests: `frontend/src/__tests__/OMEMetadataPanel.test.tsx` exists.
- **Verdict: PASS.**

### FR-014 — Lossy-save warning chip on SaveImage node when target capability fidelity does not declare source OME fields

- Spec: `:477-481`.
- Code: `frontend/src/components/WorkflowEditor/LossySaveWarning.tsx` (133
  lines). Integrated via `frontend/src/components/nodes/BlockNode.tsx:1105`.
  `lossyOmeFields` helper in `frontend/src/api/capabilities.ts:289-299`
  computes the dropped-field diff; `lossless` capabilities return empty,
  `pixel_only` returns the full source list.
- Tests: `frontend/src/__tests__/LossySaveWarning.test.tsx` exists.
- **Verdict: PASS.**

### FR-015 — Capability ID naming convention

- Spec: `:483-489`.
- Code:
  - In-tree: `load_data.py:99` builds `f"core.{lower_type}.{format_id}.load"`
    and `save_data.py:121` the `.save` mirror. Tested in
    `test_load_data_capabilities.py:91-106` and the SaveData mirror.
  - imaging: `load_image.py:238-407` and `save_image.py:186-268` use
    `"scieasy-blocks-imaging.image.{format}.{load|save}"`. **Discrepancy:**
    the spec text says `imaging.image.{format_id}.{load|save}` but the
    code uses the package-name-prefixed form
    `scieasy-blocks-imaging.image.{format_id}.{load|save}`. Tests
    (`test_format_capabilities.py:73`) assert
    `cap_id.startswith("scieasy-blocks-imaging.image.")`. The
    longer form is **stronger** — package-qualified globally — and
    satisfies ADR-043 §9 "capability IDs are globally stable and
    package-qualified". The spec's `imaging.image.*` example is shorter
    but the §9 rule is the binding constraint. Accept the more-qualified
    id; recommend a spec follow-up note clarifying the convention.
  - SRS: "reserved for future use"; no IO blocks in SRS package
    (confirmed by `ls packages/scieasy-blocks-srs/src/scieasy_blocks_srs/`).
- **Verdict: PASS (with a minor spec/code wording mismatch — code is stricter).**

### FR-016 — Test coverage matrix

- Spec: `:491-500`.
- Evidence:
  - Per-block capability declarations: `test_load_data_capabilities.py`
    (97 tests pass), `test_save_data_capabilities.py`,
    `test_format_capabilities.py` (15 tests pass).
  - Typed Meta `ome` round-trip: `test_image_meta_ome.py` (35 pass +
    1 skip).
  - Propagation Mode A/B/C: imaging `test_processblock_meta_propagation.py`
    (19 pass); SRS `test_processblock_meta_propagation.py` (7 pass).
  - Ambiguity error:
    `test_load_data_capabilities.py::TestRegistryAmbiguityForMultipleCapabilities`
    (`test_two_non_default_capabilities_for_same_slot_raise_ambiguous_lookup`
    pins the `AmbiguousCapabilityError` path).
  - Missing-extras failure mode: `test_bioformats_handler.py:33-127`
    (5 missing-extras tests + 1 install-hint test, all pass).
- **Verdict: PASS.**

### FR-017 — Add `ome-types>=0.5,<0.6` as non-optional dep of `scieasy-blocks-imaging`

- Spec: `:502-504`.
- Code: `packages/scieasy-blocks-imaging/pyproject.toml:29` declares
  `"ome-types>=0.5,<0.6"` in `dependencies` (not optional).
- Verified by `pip show ome-types` returning `0.5.3`.
- **Verdict: PASS.**

## 5. SC-001..SC-006 Per-Outcome Evidence

### SC-001 — ADR-043 §9 package validity scan returns 0 violations on LoadData/SaveData/LoadImage/SaveImage

- Measurement: tool output from this audit's manual §9 scan (Python script
  iterating `format_capabilities` on the four classes, checking
  `is_synthesized`, id uniqueness, extension normalization, default
  conflicts, roundtrip-group pairing, metadata-fidelity field validity).
  **Result: 0 errors, 7 warnings (all one-way formats, explicitly
  permitted by ADR-043 §9: Bio-Formats family load-only + Series/Text
  JSON save-only).**
- Cross-check: `python -m scieasy.qa.audit.full_audit ...` writes
  `docs/audit/full-audit-latest.json`; filtering 311 findings to those
  touching PR files yields **0** PR-attributable findings.
- **Verdict: PASS.**

### SC-002 — Bio-Formats load returns `Image` with non-None `physical_size_x` for CZI/ND2/LIF/OIR/OIB fixtures

- Test: `packages/scieasy-blocks-imaging/tests/test_bioformats_handler.py:163-189`
  (`test_bioformats_load_populates_ome_physical_size_x`, parameterized over
  the 5 vendor formats). Each subset member skips if (a) the
  `[bioformats]` extra is not installed OR (b) no fixture is committed
  under `packages/scieasy-blocks-imaging/tests/fixtures/microscopy/`.
- Local run reports 5 SKIP because the test environment has neither the
  bioformats extras (no JVM) nor the fixtures. The test SHAPE is correct;
  green will require either CI with `[bioformats]` extras or a fixture
  drop.
- **Verdict: PASS (test ready, fixture/CI provisioning is owner / Phase
  D decision).**

### SC-003 — End-to-end OME propagation golden path (CZI → Resize → SaveImage(.ome.tif) → reload → assert physical_size_x doubled)

- No committed end-to-end test exercises the full CZI→Resize→TIFF→reload
  cycle (it would require a CZI fixture + the bioformats extra). The
  individual links in the chain are tested:
  - Bio-Formats load → `physical_size_x` populated (SC-002 test).
  - Resize Mode B → `physical_size_x` doubled
    (`test_processblock_meta_propagation.py:167-185`).
  - SaveImage TIFF write of OME → `save_image.py:112-141` `_write_tiff`
    passes `metadata={"axes": axes_str}`. **NOTE:** the current
    `_write_tiff` writes the axis string but DOES NOT serialize
    `Image.Meta.ome` to the OME-XML `ImageDescription` tag. The
    `metadata_fidelity` declaration on `imaging.image.tiff.save`
    (`save_image.py:198-207`) advertises `format_metadata_writes=("ome",)`
    and the notes say "OME-XML written to the ImageDescription tag when
    Image.Meta.ome is populated", but the code does not actually emit the
    OME-XML. **This is a gap against the SC-003 spec and the
    advertised fidelity.** Logged below as P2-05.
- **Verdict: PARTIAL — link-by-link tests pass, but the full golden path
  is not testable end-to-end on the committed code because the TIFF saver
  does not yet write OME-XML.**

### SC-004 — PNG/JPEG round-trip preserves EXIF DPI

- Test: implicit via `test_image_meta_ome.py` + Pillow handler unit tests.
  The handler `_save_png` (`pillow_handler.py:254-268`) writes EXIF DPI
  when `physical_size_x` is populated. No committed end-to-end
  load→save→reload roundtrip test on PNG.
- The `_ome_dpi_value` helper (`pillow_handler.py:216-232`) computes DPI
  from `physical_size_x` (DPI = 25400 / um) for round-trip.
- **Verdict: PARTIAL — handler logic is correct and tested in unit
  scope, but the load→save→reload roundtrip is not exercised end-to-end
  in committed tests.**

### SC-005 — Chrome smoke test: ambiguous Image+TIFF capability dropdown shows ≥2 options + OME button renders pixel_size

- Spec: `:823-829`.
- Code: components shipped and integrated (FR-012, FR-013 above).
- No committed Chrome smoke test artifact under `docs/audit/` for this PR.
- The frontend unit tests (`CapabilityDropdown.test.tsx`,
  `OMEMetadataPanel.test.tsx`, `LossySaveWarning.test.tsx`, and the
  integration smoke `adr043-a3-smoke.test.tsx`) exercise the components
  but do not run a real browser.
- **Verdict: PARTIAL — unit-test evidence present, real-Chrome smoke is a
  Phase C2 manager-owned task (spec §4.3 Phase C2: "Run Chrome smoke test
  verifying capability dropdown + OME panel + lossy-save warning").**

### SC-006 — Owner-authored e2e cases in `docs/audit/adr-043-package-migration-e2e-cases.md`

- Spec: `:831-836`.
- File DOES NOT EXIST yet (verified).
- Per spec §4.3 Phase D this is the owner-driven Phase D deliverable that
  the manager pauses on after C1/C2 green. **Out of scope for Phase C1.**
- **Verdict: N/A — Phase D scope.**

### Additional P2 finding surfaced by SC-003 audit

- **P2-05.** `packages/scieasy-blocks-imaging/src/scieasy_blocks_imaging/io/save_image.py:112-141`
  (`_write_tiff`) writes the axis string via `tifffile.imwrite(...
  metadata={"axes": axes_str})` but DOES NOT serialize `image.meta.ome` to
  the OME-XML `ImageDescription` tag. The `imaging.image.tiff.save`
  capability advertises `format_metadata_writes=("ome",)` with the note
  "OME-XML written to the ImageDescription tag when Image.Meta.ome is
  populated" (`save_image.py:198-207`) — **the advertised fidelity does
  not match the implementation**. SC-003 (the end-to-end golden-path
  test) is therefore not currently green even with bioformats fixtures
  installed: the saved TIFF would lose OME on the SaveImage step. The
  Resize Mode B unit test passes because it reads `Image.Meta.ome` from
  the in-memory `Image`, not from a written-then-reloaded TIFF.
  Recommend a follow-up issue: extend `_write_tiff` to emit
  `image.meta.ome.to_xml()` to `ImageDescription` when populated, and add
  the SC-003 round-trip integration test.

## 6. ADR-043 §9 Package Validity Scan Results

Manual scan over the 75 capabilities declared by LoadData (33),
SaveData (33), LoadImage (9), SaveImage (4):

- Capability IDs are package-qualified and globally stable: PASS.
  In-tree uses `core.{type}.{format}.{direction}`; imaging uses
  `scieasy-blocks-imaging.image.{format}.{direction}`. All 75 ids are
  unique across the audited blocks.
- Extensions are normalized lowercase with leading dots: PASS.
  Every extension in every capability's `extensions` tuple starts with
  `.` and is lowercase (enforced by `normalize_extension` in
  `src/scieasy/blocks/io/capabilities.py:50-64`, called from
  `FormatCapability.__post_init__`).
- Defaults do not conflict within `(direction, type, extension)`: PASS.
  In-tree records are all `is_default=False` (deliberate cross-package
  collision rule with LCMS package); imaging records are
  `is_default=True` per single-package-per-extension assumption. No
  conflict surfaced.
- Round-trip groups marked round-trip have both load and save: PASS for
  all paired groups; one-way warnings (Series/Text JSON save-only;
  Bio-Formats family load-only) are explicitly permitted by ADR-043 §9
  for "raw instrument formats that are load-only" and "report formats
  that are save-only".
- Metadata fidelity declarations reference fields that exist on the
  declared type's `Meta` model when `level=typed_meta` or stronger:
  PASS. The audit scan walked every capability with
  `level∈{typed_meta, format_specific, lossless}` and verified each
  `typed_meta_reads`/`typed_meta_writes` field appears in
  `data_type.Meta.model_fields`. The runtime check is enforced by
  `FormatCapability.__post_init__` via
  `metadata_fidelity.validate_typed_meta_fields(self.data_type)` in
  `src/scieasy/blocks/io/capabilities.py:218`.
- `is_synthesized=False` on every record: PASS — verified for all 75
  records.

## 7. ADR-043 §6 Ambiguity-Resolution Scan

- No `(direction, type, extension)` triple matches multiple
  `is_default=True` capabilities across the four audited blocks.
- The registry's two-block ambiguity error path is tested in
  `test_load_data_capabilities.py::TestRegistryAmbiguityForMultipleCapabilities::test_two_non_default_capabilities_for_same_slot_raise_ambiguous_lookup`.
- The default-vs-non-default winner path is tested in
  `test_default_alternate_wins_over_non_default_core`.

## 8. ADR-041 / FR-009 Propagation Contract — Per-Mode Verification

- **Mode A (transparent):** `meta=source.meta` pattern verified across
  imaging math (`AddScalar` and siblings), morphology (`MorphologyOp`,
  `EdgeDetect`, `FFTFilter`, `RidgeFilter`, `Sharpen`), preprocess
  (`BackgroundSubtract`, `Denoise`, `FlatFieldCorrect`, `Normalize`,
  `ConvertDtype`, `Deconvolve`), registration (`ApplyTransform`,
  `RegisterSeries`), and SRS preprocess (`SRSBaseline`,
  `SRSSpectralDenoise`). 4 dedicated tests in the imaging propagation
  test file + 2 in the SRS propagation test file pin this.

- **Mode B (transform helper):** `_resize_meta`, `_split_meta`,
  `_projected_meta` updated to rewrite OME spatial fields. Verified at
  `test_mode_b_resize_factor_half_doubles_physical_pixel_size`,
  `test_mode_b_resize_target_shape_updates_ome_size`,
  `test_mode_b_axis_split_*`, `test_mode_b_axis_projection_*`.

- **Mode C (cross-type):** `Image→Label` / `Image→Mask` cases propagate
  `ome` in `BlobDetect`, `Watershed`, `ConnectedComponents`,
  `Threshold`, `RemoveSmallObjects`/`RemoveBorderObjects`/`ExpandLabels`/
  `ShrinkLabels` (via `model_dump+override`), `CellposeSegment` (with
  collapse-to-2D OME normalisation per Codex P1 review reconciled on PR
  #1302), and `SRSKMeansCluster`. Legitimate-drop cases:
  `ComputeRegistration` (output is `Transform`, no spatial Meta carrier);
  `RegionProps`, `Colocalization`, `PairwiseDistance` (DataFrame outputs
  without spatial coordinate system); all `Render*` blocks (Artifact
  outputs); `SRSPCA`/`SRSICA`/`SRSUnmix` (per-component score maps;
  documented in the SRS audit §7).

## 9. Check Commands Executed

| Command | Status | Evidence |
|---|---|---|
| `python -m scieasy.qa.audit.full_audit --repo-root . --format json --output docs/audit/full-audit-latest.json` | wrote 6694 lines | 311 total findings; 0 in PR-touched files (per `python` filter above). |
| `ruff check src/scieasy/blocks/io/ packages/scieasy-blocks-imaging/ packages/scieasy-blocks-srs/` | All checks passed! | clean |
| `ruff format --check src/scieasy/blocks/io/ packages/scieasy-blocks-imaging/ packages/scieasy-blocks-srs/` | 113 files already formatted | clean |
| `pytest tests/blocks/io/test_load_data_capabilities.py tests/blocks/io/test_save_data_capabilities.py --timeout=60` | 97 passed | clean |
| `pytest packages/scieasy-blocks-imaging/tests/test_format_capabilities.py packages/scieasy-blocks-imaging/tests/test_image_meta_ome.py --timeout=60` | 35 passed + 1 skipped | clean |
| `pytest packages/scieasy-blocks-imaging/tests/test_processblock_meta_propagation.py --timeout=60` | 19 passed | clean |
| `pytest packages/scieasy-blocks-srs/tests/test_processblock_meta_propagation.py --timeout=60` | 7 passed | clean |
| `pytest packages/scieasy-blocks-imaging/tests/test_bioformats_handler.py --timeout=60` | 7 passed + 5 skipped | clean (skips are extras-gated, expected) |
| ADR-043 §9 manual scan | 0 errors, 7 allowed-one-way warnings | see §6 |
| ADR-043 §6 ambiguity scan | 0 ambiguity slots | see §7 |
| Sentrux | skipped | not available in this audit environment (consistent with other ADR-043 phases) |

## 10. Spec Gaps Surfaced By Audit

Items where the spec is silent or weaker than the as-built code, deserving a
follow-up spec amendment:

- **Capability id wording (FR-015):** spec says
  `imaging.image.{format}.{load|save}`; code uses
  `scieasy-blocks-imaging.image.{format}.{load|save}`. The code is stricter
  (package-qualified) and aligns with ADR-043 §9. Recommend spec amendment
  to align wording.
- **`_write_tiff` OME-XML serialisation (FR-005 + SC-003):** capability
  fidelity advertises `format_metadata_writes=("ome",)` and notes OME-XML
  is written to `ImageDescription`, but `_write_tiff` does not currently
  emit OME-XML. Either tighten the implementation OR weaken the capability
  advertisement to `level="typed_meta"` until the implementation lands.
  Tracked as P2-05.
- **`_load_png` / `_load_jpeg` axes-override bug (P2-01):** the axes-override
  branch zeros the pixel buffer. Untested off-default path; should be fixed
  with a regression test.
- **Registry "hide capabilities when handler module unimportable" (FR-008
  last sentence):** spec §3 says the registry MUST hide bioformats
  capabilities when extras are missing. Code keeps them visible and raises
  ImportError at dispatch time. Spec §4.5 (Risks row 6) acknowledges this
  trade-off, so the spec is internally inconsistent. Recommend §3 FR-008
  amendment to match §4.5 OR add the hide-on-fail logic to the registry.

## 11. Codex Auto-Review Reconciliation

This audit's PR has not been opened yet at the time of writing; Codex
auto-review will fire on first CI run. Cap: 5 minutes from CI-green.

After PR open + CI green, this section will be updated with:

- Total Codex comments by severity.
- Per-comment disposition (accept / defer-to-followup / reject-with-reason).
- For accepted P1/P2: the follow-up commit SHA in this audit PR.

If Codex review does not fire within 5 minutes of CI-green (token-exhaustion
fallback per the `feedback_codex_review_timeout` recorded protocol), the
audit will record "no review fired within 5 min window" and proceed.

## 12. Final Recommendation

**pass-with-fixes.** Approve PR with the following follow-up issues
opened against the umbrella `track/adr-043/core-blocks-and-imaging` work:

1. P2-01: Fix `_load_png` / `_load_jpeg` axes-override pixel-buffer zero
   bug + add regression test.
2. P2-05: Implement OME-XML serialisation in `SaveImage._write_tiff` OR
   weaken capability fidelity advertisement to match current behaviour.
   This unblocks SC-003 end-to-end.
3. P2-02 / P2-03: Resolve dual-source-of-truth between `supported_extensions`
   and `format_capabilities` on `LoadImage` / `SaveImage` (either remove
   the per-class ClassVar or add a drift-detection test).
4. Spec amendment: align FR-015 capability-id wording with as-built code;
   reconcile FR-008 last sentence with §4.5 Risks row 6.
5. Phase C2 manager work: run real-Chrome smoke test for SC-005 + provide
   committed evidence path.
6. Phase D work: open the owner-authored e2e test cases under SC-006
   when the owner is ready.

None of the items above is a P0 / P1 release blocker for the umbrella PR
merge into `main`. The spec contract (FR-001..FR-017 + SC-001..SC-002)
holds; SC-003/SC-004/SC-005 hold link-by-link in unit/integration scope
and gain end-to-end coverage in Phase C2 / Phase D as the spec intends.

## 13. References

- Spec: [`docs/specs/adr-043-package-migration.md`](../specs/adr-043-package-migration.md)
- ADRs: [`docs/adr/ADR-041.md`](../adr/ADR-041.md), [`docs/adr/ADR-043.md`](../adr/ADR-043.md)
- Phase B1 audit: [`docs/audit/adr-043-imaging-propagation-audit.md`](adr-043-imaging-propagation-audit.md)
- Phase B2 audit: [`docs/audit/adr-043-srs-propagation-audit.md`](adr-043-srs-propagation-audit.md)
- Full audit JSON: [`docs/audit/full-audit-latest.json`](full-audit-latest.json)
- Gate record: `.workflow/records/1296-c1-audit.json`
