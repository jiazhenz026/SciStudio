# ADR-043 Implementation Checklist

> Mandatory tracking doc for the ADR-043 implementation cascade.
> Every agent edits only the rows it owns. Drift = protocol violation.

## Conventions

- `[ ]` not started
- `[~]` in progress
- `[x]` done
- `[!]` blocked
- Each checked row MUST append `-> <PR-or-commit-or-test-link>`.

## Grounding

- ADR: `docs/adr/ADR-043.md`
- Spec: `docs/specs/adr-043-io-format-capability-registry.md`
- Manager issue: #1207
- Package migration fallout tracker: #1204
- Tracking branch: `track/adr-043/capability-registry`

## Track A - Core Capability Model (Owner: A43-core, issue #1209)

### Implementation

- [x] Add `FormatCapability`, `MetadataFidelity`, direction/fidelity literals, typed validation errors, and normalization helpers. [ADR-043 sections 8, 11] -> commit `4110f6b4`
- [x] Add `SimpleLoader` and `SimpleSaver` ergonomic bases with conservative `pixel_only` synthesis. [ADR-043 section 4] -> commit `4110f6b4`
- [x] Extend `IOBlock.get_format_capabilities()` and legacy `supported_extensions` migration synthesis without final package-compliance claims. [ADR-043 sections 9, 13] -> commit `4110f6b4`
- [x] Export public simple/capability APIs from `scieasy.blocks.io`. -> commit `4110f6b4`
- [x] Add tests for valid/invalid capabilities, metadata fidelity, simple IO synthesis, and compatibility synthesis. -> local tests `pytest -q --timeout=60 --no-cov tests/blocks/io/test_format_capabilities.py tests/blocks/io/test_simple_io.py`

## Track B - Registry Lookup (Owner: A43-registry, issue #1210)

### Implementation

- [x] Add capability storage to `BlockSpec` or an adjacent registry-owned index. [ADR-043 section 11.4] -> commit `d97d5771`
- [x] Add `list_format_capabilities`, `find_loader_capability`, and `find_saver_capability`. -> commit `d97d5771`
- [x] Implement deterministic lookup order: explicit ID, unique match, default, most-specific type, ambiguity error. [ADR-043 section 6] -> commit `d97d5771`
- [x] Validate handler existence, extension normalization, package-qualified IDs, default conflicts, roundtrip groups, and typed meta fields where feasible. [ADR-043 section 9] -> commit `d97d5771`
- [x] Preserve legacy `find_loader` / `find_saver` migration behavior where tests require it, but route semantics through capabilities. -> commit `d97d5771`
- [x] Add registry tests for unique/default/explicit/missing/ambiguous cases. -> local tests `pytest -q --timeout=60 --no-cov tests/blocks/test_block_registry_capabilities.py tests/blocks/test_registry.py`

## Track C - Boundary Runtime Validation (Owner: A43-boundary, issue #1211)

### Implementation

- [x] Add `capability_id` parameters to `materialise_to_file` and `reconstruct_from_file` and dispatch through registry capability lookup. [ADR-043 section 11.5] -> local tests `pytest -q --timeout=60 --no-cov tests/engine/test_materialisation_capabilities.py`
- [x] Preserve intentional Artifact fallback behavior only where the target type is Artifact-compatible. -> local test `test_reconstruct_artifact_fallback_only_for_artifact_compatible_type`
- [x] Thread `capability_id` through `FileExchangeBridge.prepare()` manifest entries and AppBlock output reconstruction. -> local tests `tests/blocks/app/test_app_block_capabilities.py`
- [x] Validate AppBlock and CodeBlock boundary ports before execution when type + extension is declared. [ADR-043 sections 7, 10] -> local tests `tests/workflow/test_io_boundary_validation.py`
- [x] Add runtime, AppBlock, and workflow validator tests for missing, unique, ambiguous, and explicit capability IDs. -> local tests `pytest -q --timeout=60 --no-cov tests/engine/test_materialisation_capabilities.py tests/blocks/app/test_app_block_capabilities.py tests/workflow/test_io_boundary_validation.py`

## Track D - API And Frontend Capability Selection (Owner: A43-ui, issue #1212)

### Implementation

- [x] Expose serializable format capability metadata on block summary/schema without adding palette blocks. [ADR-043 section 3] -> commit `0b9b2f91`
- [x] Update frontend API types for format capabilities and metadata fidelity. -> commit `0b9b2f91`
- [x] Render capability-backed format choices in IO block config surfaces and persist selected `capability_id`. -> commit `0b9b2f91`
- [x] Surface ambiguity and metadata-loss states as backend-derived warnings, not frontend runtime truth. -> commit `0b9b2f91`
- [x] Add backend schema tests and frontend unit tests for capability list rendering and persisted selection. -> local tests `pytest -q --timeout=60 --no-cov tests/api/test_blocks.py`; `npx vitest run src/components/BottomPanel.test.tsx src/components/nodes/BlockNode.test.tsx`

## Track E - Package Capability Pilot (Owner: A43-packages, issue #1213)

### Implementation

- [x] Add explicit imaging `LoadImage` / `SaveImage` TIFF/Zarr capabilities with stable IDs and fidelity declarations. -> `pytest -q --timeout=60 --no-cov packages/scieasy-blocks-imaging/tests/test_format_capabilities.py`
- [x] Add minimal LCMS table/raw IO capability declarations where low-risk and mark one-way formats explicitly. -> `pytest -q --timeout=60 --no-cov packages/scieasy-blocks-lcms/tests/test_io/test_format_capabilities.py`
- [x] Add package tests proving explicit declarations are used instead of compatibility synthesis for pilot IOBlocks. -> focused capability tests passed, 5 tests
- [x] Update package docs for capability IDs and metadata fidelity. -> package README updates
- [x] Mark full package hard-validation migration deferrals with `TODO(#1204)` where code knowingly remains legacy. -> package README TODO markers

## Track F - Fact Audit And Fix (Owner: Manager/fix agent, issue #1214)

### Audit

- [x] Run `python scripts/audit/generate_facts.py --check`. -> local PASS after commit `ac875b87`
- [x] Run `python -m scieasy.qa.audit.full_audit --format json`. -> local FAIL only on pre-existing legacy frontmatter / global closure baseline
- [x] Classify failures as ADR-043-related vs pre-existing baseline. -> local classifier found `implementation_related_count: 0`
- [x] Fix every ADR-043-related fail in a scoped branch/PR. -> commit `ac875b87`
- [x] Post audit summary and fixes on #1207. -> https://github.com/zjzcpj/SciEasy/issues/1207#issuecomment-4492978957

## Track G - Architecture And Developer Docs (Owner: A43-docs, issue #1215)

### Implementation

- [x] Update `docs/architecture/ARCHITECTURE.md` for capability ownership, canonical-zone type/format separation, boundary validation, and metadata fidelity. -> local check `ruff format --check docs`
- [x] Update `docs/block-development/**` for `SimpleLoader`, `SimpleSaver`, explicit `FormatCapability` records, aggregate IOBlocks, and capability IDs. -> local check `ruff format --check docs`
- [x] Bring edited architecture and block-development docs into ADR-042 compliance, including the currently non-compliant `docs/architecture/ARCHITECTURE.md`. -> local check `frontmatter_lint ADR-042/ADR-043/specs: 0 errors`
- [x] Document that compatibility synthesis is migration scaffolding only, and link full package hard-validation migration to #1204. -> #1204
- [x] Add or update cross-links among ADR-043, the implementation spec, block-development docs, and package docs. -> `docs/block-development/block-contract.md`
- [x] Fix all ADR-043-related doc/fact audit failures found after implementation. -> local `full_audit` classification: 0 ADR-043-related findings remain; remaining failures are pre-existing legacy frontmatter / global closure baseline

## Codex Auto-Review Audit (Manager investigation, issue #1207)

> Source PRs: #1216, #1218, #1219, #1221, #1230, #1232, #1220.
> This section records automated Codex review findings discovered after
> integration. The accepted implementation findings were fixed in #1241.

- [ ] #1216 P2 `docs/adr/ADR-043.md`: Codex suggested changing `tracking_issue` from package fallout #1204 to manager issue #1207. Assessment: partially valid traceability concern, but not accepted as an implementation bug. ADR-043's locked frontmatter currently points at the long-lived package migration tracker #1204; #1207 is the cascade execution manager issue. Resolution: not changed; checklist and #1207 comment carry cascade traceability.
- [x] #1218 P1 `src/scieasy/blocks/io/capabilities.py`: reject scalar extension strings before normalizing. Assessment: valid. Final code treated `extensions="tif"` as an iterable of characters. Resolution: fixed in #1241; regression `test_normalize_extension_rejects_invalid_values`.
- [x] #1218 P2 `src/scieasy/blocks/io/capabilities.py`: reject scalar metadata-field strings in fidelity declarations. Assessment: valid. Final code treated `typed_meta_reads="pixel_size"` as per-character fields. Resolution: fixed in #1241; regression `test_metadata_field_lists_reject_scalar_strings`.
- [x] #1218 P2 `src/scieasy/blocks/io/simple_io.py`: validate `path` is a single path in SimpleLoader/SimpleSaver helpers. Assessment: valid. Final code coerced list values through `Path(str(raw_path))`. Resolution: fixed in #1241; regressions `test_simple_loader_rejects_multi_path_config` and `test_simple_saver_rejects_multi_path_config`.
- [x] #1219 P1 `docs/block-development/quickstart.md`: quickstart imported `SimpleLoader` before the core API existed in that standalone docs PR. Assessment: valid at the moment of PR #1219 review, but resolved by integration order once #1218 landed on the tracking branch. Resolution: fixed by integrated branch state.
- [x] #1221 P1 `src/scieasy/blocks/registry.py`: preserve legacy ordering when loader dtype is omitted. Assessment: valid. Final `find_loader(None, ext)` entered capability ranking via `find_loader_capability(dtype or DataObject, extension)` before legacy fallback, so it could select a non-first registered capability. Resolution: fixed in #1241; regression `test_legacy_find_loader_without_dtype_keeps_registration_order`.
- [x] #1221 P1 `src/scieasy/blocks/registry.py`: fall back when the resolved capability class fails to import. Assessment: valid. Final code resolved a single winning capability class and could return `None` instead of trying lower-ranked usable candidates. Resolution: fixed in #1241; regression `test_legacy_find_loader_falls_back_when_winning_capability_class_cannot_resolve`.
- [x] #1230 P2 `frontend/src/components/BottomPanel.tsx`: avoid persisting empty `capability_id` from the placeholder option. Assessment: valid. Final selector forwarded `event.target.value`; selecting the placeholder could persist `capability_id: ""`. Resolution: fixed in #1241; regression `BottomPanel clears ADR-043 capability selection as null when the placeholder is selected`.
- [x] #1232 P1 `src/scieasy/workflow/validator.py`: validate boundary outputs against the runtime-selected type. Assessment: valid. Final validator checked all configured output types, while AppBlock reconstruction uses the first accepted type; unions such as `Artifact | Text` could be rejected even when runtime would use Artifact fallback. Resolution: fixed in #1241; regression `test_appblock_output_validation_uses_first_runtime_selected_type`.
- [x] #1232 P2 `src/scieasy/blocks/app/app_block.py`: treat null `capability_id` as unset on AppBlock outputs. Assessment: valid. Final AppBlock output mapping used `str(entry.get("capability_id", "")).strip()`, so JSON null became `"None"`. Resolution: fixed in #1241; regression `test_appblock_output_binner_treats_null_capability_id_as_unset`.
- [x] #1220 package capability pilot: no Codex auto-review findings were posted. Resolution: no action required.

## Acceptance Criteria

- [x] Each sub-issue has an implementation PR targeting `track/adr-043/capability-registry`. -> PRs #1218, #1219, #1221, #1230, #1232, #1220
- [x] Every agent used an independent worktree and independent branch. -> manager verified PR branches/worktrees during merge
- [x] All implementation PRs pass local tests and GitHub CI. -> PR #1216 CI green after integration
- [x] Architecture and block-development docs are updated as part of this cascade. -> PR #1219
- [x] Fact audit has been run after implementation integration. -> local `generate_facts`, `full_audit`, and `lint-imports`
- [x] All ADR-043-related fact audit failures are fixed or explicitly escalated with evidence. -> commit `ac875b87`

## Drift Log

(empty until first violation)
