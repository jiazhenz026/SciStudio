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

- [ ] Add `capability_id` parameters to `materialise_to_file` and `reconstruct_from_file` and dispatch through registry capability lookup. [ADR-043 section 11.5]
- [ ] Preserve intentional Artifact fallback behavior only where the target type is Artifact-compatible.
- [ ] Thread `capability_id` through `FileExchangeBridge.prepare()` manifest entries and AppBlock output reconstruction.
- [ ] Validate AppBlock and CodeBlock boundary ports before execution when type + extension is declared. [ADR-043 sections 7, 10]
- [ ] Add runtime, AppBlock, and workflow validator tests for missing, unique, ambiguous, and explicit capability IDs.

## Track D - API And Frontend Capability Selection (Owner: A43-ui, issue #1212)

### Implementation

- [x] Expose serializable format capability metadata on block summary/schema without adding palette blocks. [ADR-043 section 3] -> commit `0b9b2f91`
- [x] Update frontend API types for format capabilities and metadata fidelity. -> commit `0b9b2f91`
- [x] Render capability-backed format choices in IO block config surfaces and persist selected `capability_id`. -> commit `0b9b2f91`
- [x] Surface ambiguity and metadata-loss states as backend-derived warnings, not frontend runtime truth. -> commit `0b9b2f91`
- [x] Add backend schema tests and frontend unit tests for capability list rendering and persisted selection. -> local tests `pytest -q --timeout=60 --no-cov tests/api/test_blocks.py`; `npx vitest run src/components/BottomPanel.test.tsx src/components/nodes/BlockNode.test.tsx`

## Track E - Package Capability Pilot (Owner: A43-packages, issue #1213)

### Implementation

- [ ] Add explicit imaging `LoadImage` / `SaveImage` TIFF/Zarr capabilities with stable IDs and fidelity declarations.
- [ ] Add minimal LCMS table/raw IO capability declarations where low-risk and mark one-way formats explicitly.
- [ ] Add package tests proving explicit declarations are used instead of compatibility synthesis for pilot IOBlocks.
- [ ] Update package docs for capability IDs and metadata fidelity.
- [ ] Mark full package hard-validation migration deferrals with `TODO(#1204)` where code knowingly remains legacy.

## Track F - Fact Audit And Fix (Owner: Manager/fix agent, issue #1214)

### Audit

- [ ] Run `python scripts/audit/generate_facts.py --check`.
- [ ] Run `python -m scieasy.qa.audit.full_audit --format json`.
- [ ] Classify failures as ADR-043-related vs pre-existing baseline.
- [ ] Fix every ADR-043-related fail in a scoped branch/PR.
- [ ] Post audit summary and fixes on #1207.

## Track G - Architecture And Developer Docs (Owner: A43-docs, issue #1215)

### Implementation

- [x] Update `docs/architecture/ARCHITECTURE.md` for capability ownership, canonical-zone type/format separation, boundary validation, and metadata fidelity. -> local check `ruff format --check docs`
- [x] Update `docs/block-development/**` for `SimpleLoader`, `SimpleSaver`, explicit `FormatCapability` records, aggregate IOBlocks, and capability IDs. -> local check `ruff format --check docs`
- [x] Bring edited architecture and block-development docs into ADR-042 compliance, including the currently non-compliant `docs/architecture/ARCHITECTURE.md`. -> local check `frontmatter_lint ADR-042/ADR-043/specs: 0 errors`
- [x] Document that compatibility synthesis is migration scaffolding only, and link full package hard-validation migration to #1204. -> #1204
- [x] Add or update cross-links among ADR-043, the implementation spec, block-development docs, and package docs. -> `docs/block-development/block-contract.md`
- [x] Fix all ADR-043-related doc/fact audit failures found after implementation. -> local check `full_audit`: only pre-existing `facts.generated-stale` baseline

## Acceptance Criteria

- [ ] Each sub-issue has an implementation PR targeting `track/adr-043/capability-registry`.
- [ ] Every agent used an independent worktree and independent branch.
- [ ] All implementation PRs pass local tests and GitHub CI.
- [ ] Architecture and block-development docs are updated as part of this cascade.
- [ ] Fact audit has been run after implementation integration.
- [ ] All ADR-043-related fact audit failures are fixed or explicitly escalated with evidence.

## Drift Log

(empty until first violation)
