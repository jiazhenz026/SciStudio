# ADR-048 Developer Docs Scope Impact Report

## Summary

ADR-048 makes the existing package and block developer documentation incomplete in two ways. First, the current docs predate the ADR-048 previewer model: previewer registration, project-local previewers, plot templates, package-owned domain previewers, previewer routing, and preview-side plot jobs are not documented for authors. Second, several package/block authoring examples have drifted from current contracts and scaffold tests, especially around package entry points, concrete port typing, and template-generated ports.

SPEC 3 should treat this as a focused documentation replacement and refresh, not a broad rewrite of all architecture history. The highest-risk scope is `docs/block-development/**`, package READMEs under `packages/scistudio-blocks-*`, AI skill docs under `src/scistudio/_skills/scistudio/**`, and package/block scaffolding templates that serve as executable author documentation. Historical ADRs and old specs should not be deleted or used as the governing design.

## Current Docs Inventory

- `docs/block-development/quickstart.md`: five-minute author path, save location, IO, tests, and data access. It does not mention previewer or plot authoring.
- `docs/block-development/block-contract.md`: primary block contract reference. It documents `Block`, classvars, ports, `run`, `ProcessBlock`, `IOBlock`, dynamic ports, config schema, and `AppBlock`.
- `docs/block-development/publishing.md`: package distribution and entry-point guidance. It currently shows `scistudio.blocks` and `scistudio.types`, but not `scistudio.previewers`.
- `docs/block-development/testing.md`: block validation and package testing guidance.
- `docs/block-development/custom-types.md`: custom data type registration through `scistudio.types`.
- `docs/block-development/data-types.md`, `collection-guide.md`, `memory-safety.md`, and `architecture-for-block-devs.md`: background for data objects, collections, streaming, and block execution.
- `docs/block-development/examples/**`: example packages used as author reference. The multi-block package example still presents `get_block_package` as the package entry-point callable.
- `packages/scistudio-blocks-imaging/README.md`: package-level author/user notes for imaging types, blocks, and IO capabilities. It does not describe package-owned image previewers.
- `packages/scistudio-blocks-lcms/README.md` and `packages/scistudio-blocks-srs/README.md`: package-level docs for domain blocks and types. These are likely secondary for ADR-048 unless domain previewers are added there.
- `src/scistudio/_skills/scistudio/scistudio-write-block/SKILL.md`: current AI-facing block authoring instructions. It already warns that generic ports harm preview and canvas behavior.
- `src/scistudio/_skills/scistudio/scistudio-inspect-data/SKILL.md`: current data inspection skill. Its `preview_data(ref, max_rows?, max_dim?)` examples are stale relative to the implemented MCP signature and ADR-048's future plot-tool direction.
- `docs/cli-integration.md`: user-facing AI CLI and skill integration document. It currently describes five task skills and will drift when ADR-048 adds `scistudio-write-plot` and plot MCP tools.
- `docs/specs/data-preview-3d-viewer.md`: historical data preview spec. Its frontmatter marks it as legacy; it should be treated as historical context, not the governing ADR-048 preview design.
- `docs/specs/adr-043-package-migration.md`: includes imaging package preview-panel behavior from ADR-043. It is relevant because ADR-048 moves rich image preview behavior into package-owned domain previewers.

## Staleness Findings

- No current package/block developer doc explains ADR-048 previewer concepts from `docs/adr/ADR-048.md`: `PreviewHost`, `PreviewRouter`, `PreviewerRegistry`, `PreviewerSpec`, previewer resolution order, `PreviewDataAccess`, preview-side plot jobs, or the `scistudio.previewers` entry point.
- `docs/block-development/publishing.md` documents package entry points for blocks and types, but not previewers. It also presents `get_block_package` as the main published package callable, while the current CLI package scaffold and tests use `get_blocks() -> tuple[PackageInfo, list[type]]`.
- The block contract docs correctly state that empty `accepted_types` accepts any `DataObject`, but do not explain the current authoring rule that reusable blocks should prefer concrete data types. The wheel skill and provisioning hook treat empty or root `DataObject` ports as generic and risky because preview routing and canvas behavior depend on concrete type signals.
- `src/scistudio/cli/templates/block_package/blocks.py.tpl` appears stale as executable documentation: it emits `OutputPort(..., produced_type=None)`, but `OutputPort` has no `produced_type` field in `src/scistudio/blocks/base/ports.py`.
- `src/scistudio/blocks/_templates/block_base_template.py` still scaffolds empty accepted-type lists. That is valid at runtime but should be reconciled with author guidance and hooks that require explicit justification for generic ports.
- `src/scistudio/_skills/scistudio/scistudio-inspect-data/SKILL.md` documents old preview-data arguments and examples. The implemented MCP tool accepts `fmt` values, while ADR-048 will introduce explicit plot-target and plot-job tools.
- `docs/cli-integration.md`, `tests/packaging/test_wheel_skills.py`, `tests/agent_provisioning/test_skills.py`, and `src/scistudio/agent_provisioning/skills.py` currently enumerate five task skills. ADR-048 requires adding and packaging `scistudio-write-plot`.
- `docs/specs/data-preview-3d-viewer.md` describes the old hardcoded preview endpoint and frontend behavior. It should not be deleted as part of SPEC 3 unless the project has a separate historical-spec cleanup policy, but new docs must supersede it clearly.
- `packages/scistudio-blocks-imaging/README.md` describes imaging types, blocks, and IO capabilities but not the ADR-048 expectation that rich Image/Label viewing should be package-owned rather than hardcoded in core.

## Proposed Delete/Rewrite Scope

- Rewrite or replace `docs/block-development/publishing.md` as the main package-author guide. It should cover `scistudio.blocks`, `scistudio.types`, and `scistudio.previewers`, current scaffold conventions, `PackageInfo`, package layout, and when package-owned previewers are expected.
- Rewrite `docs/block-development/block-contract.md` enough to align block authoring with current contracts: `Port.accepted_types`, no `OutputPort.produced_type`, concrete-type guidance, dynamic ports, `ProcessBlock`, `IOBlock`, and how block output types affect preview routing.
- Refresh `docs/block-development/quickstart.md` so the first author path uses the current package scaffold and shows concrete ports. It should avoid teaching generic ports as the default.
- Refresh `docs/block-development/testing.md` to include previewer registration tests, package entry-point tests, plot-template validation, and wheel skill packaging checks where applicable.
- Refresh `docs/block-development/custom-types.md` to explain the boundary between custom data types and previewers: types register with `scistudio.types`; display behavior registers with `scistudio.previewers`.
- Replace or regenerate `docs/block-development/examples/multi-block-package/**` from the current scaffold, or mark it as legacy if retained. Its entry-point callable should not conflict with the canonical scaffold guidance.
- Review `docs/block-development/examples/simple-transform/**` and `docs/block-development/examples/custom-io-loader/**` for concrete port types, package entry-point shape, and any stale `OutputPort` fields.
- Add a new author-facing page or section for ADR-048 previewers and plot jobs under `docs/block-development/`, unless the spec chooses a new package-author docs location. Suggested title: `docs/block-development/previewers-and-plots.md`.
- Update `packages/scistudio-blocks-imaging/README.md` when the imaging package gains package-owned domain previewer registration. LCMS/SRS package READMEs should remain out of scope unless ADR-048 adds previewers there.
- Update `src/scistudio/_skills/scistudio/scistudio-write-block/SKILL.md` only where ADR-048 changes author obligations. It is already a strong source for concrete port-type guidance.
- Replace stale preview examples in `src/scistudio/_skills/scistudio/scistudio-inspect-data/SKILL.md` and add `src/scistudio/_skills/scistudio/scistudio-write-plot/SKILL.md`.
- Update `docs/cli-integration.md` for the added plot skill and tools.
- Do not delete or rewrite historical ADRs or historical specs as part of SPEC 3. If needed, add narrow supersession notes elsewhere rather than changing old ADR-048 or old preview-provider material.

## Authoritative Sources

- Current block base contract: `src/scistudio/blocks/base/block.py` defines `Block`, class variables, effective ports, validation, `run`, packing helpers, and auto-flush behavior.
- Current port contract: `src/scistudio/blocks/base/ports.py` defines `Port`, `InputPort`, `OutputPort`, and the behavior that empty `accepted_types` accepts any type.
- Current package metadata contract: `src/scistudio/blocks/base/package_info.py` defines `PackageInfo`.
- Current block package discovery contract: `src/scistudio/blocks/registry/_scan.py` accepts `scistudio.blocks` entry points that return either `(PackageInfo, list[type[Block]])` or `list[type[Block]]`, and also accepts legacy direct block classes.
- Current scaffold contract: `src/scistudio/cli/templates/block_package/**` and `tests/cli/test_new_block_package.py`. These are the best sources for the intended package scaffold, even though `blocks.py.tpl` needs correction.
- Current block authoring enforcement: `src/scistudio/_skills/scistudio/scistudio-write-block/SKILL.md`, `src/scistudio/agent_provisioning/templates/hook_enforce_concrete_port_types.py`, and `tests/agent_provisioning/test_hooks.py`.
- Current block registry and package tests: `tests/blocks/test_registry.py`, `tests/blocks/test_registry_package_layout.py`, `tests/integration/test_block_sdk_e2e.py`, and `tests/api/test_blocks_template.py`.
- Current hardcoded preview implementation: `src/scistudio/api/runtime/_data.py`, `frontend/src/components/DataPreview.parts/PreviewRenderer.tsx`, and `tests/api/test_data.py`. These are authoritative for current behavior only; ADR-048 supersedes them for the target design.
- Governing target design for ADR-048: `docs/adr/ADR-048.md`. In particular, the spec should document previewer resolution order, `PreviewerSpec`, bounded `PreviewDataAccess`, preview-side plot jobs, core fallback previewers, package/project previewers, and plot MCP tools from the current ADR.
- Future ADR-048 implementation sources should become authoritative once added: `src/scistudio/previewers/**`, previewer registry tests, preview plot-job tests, frontend manifest tests, MCP plot-tool tests, and package-owned imaging previewer tests.

## Test/Check Impact

- Documentation refresh should pass the normal docs-change gate path: frontmatter lint, full audit, docs closure/drift checks, and generated-facts checks where applicable.
- If new or moved docs land under short-form governed paths such as `docs/user/**`, `docs/contributing/**`, `docs/prod-agent/**`, or `docs/doc-guide/**`, they must satisfy the document-standard line and word limits or be split. `docs/block-development/**` is not currently listed in that short-form set, but SPEC 3 should state whether it is exempt or newly governed.
- Any facts generated from docs or code should be validated with the generated-facts check rather than hand-edited.
- Wheel skill packaging tests must be updated for `scistudio-write-plot`: `tests/packaging/test_wheel_skills.py`, `tests/agent_provisioning/test_skills.py`, and `src/scistudio/agent_provisioning/skills.py`.
- AI/MCP tests should be updated for ADR-048 plot tools and skill prompts. Likely impacted files include `tests/ai/test_mcp_fastmcp.py`, `tests/ai/test_system_prompt.py`, and MCP inspection/plot-tool tests added by ADR-048.
- Template tests should assert that package scaffolds use valid `InputPort`/`OutputPort` fields and do not teach `produced_type` on `OutputPort`.
- Block/package docs should be checked against scaffold output to prevent future drift between docs and `src/scistudio/cli/templates/block_package/**`.
- ADR-048 previewer tests should validate registry loading from package entry points, project-local previewer discovery, fallback resolution, ambiguity errors, sampling/truncation metadata, same-origin frontend manifests, and package-owned imaging previewer registration.
- Plot-job tests should validate `plots/<plot_id>/plot.yaml`, Python and R render templates, target selection, cache-path behavior, and that plot jobs are preview-side artifacts rather than workflow DAG nodes.
- Markdown links should be validated by whatever link or audit check is wired into the docs gate. SPEC 3 should require link validation for every newly referenced ADR-048 file, package README, skill, and template path.

## Open Questions

- Should `docs/block-development/**` remain a long-form developer-doc area, or should SPEC 3 split it into shorter governed pages under a new or existing standards-covered docs location?
- What canonical package entry-point function name should docs teach? The current scaffold uses `get_blocks() -> tuple[PackageInfo, list[type]]`, while existing packages and examples often use `get_block_package()`. The registry accepts both as callable entry-point targets, but author docs should choose one primary pattern.
- Should package-local previewer examples be added first for imaging only, or should LCMS/SRS also receive minimal previewer stubs to demonstrate domain package ownership?
- What exact project-local previewer layout should be documented? ADR-048 defines the concept and resolution order, but SPEC 3 should wait for or define the concrete directory schema.
- Should the old hardcoded preview endpoint docs receive an explicit supersession note, or is it enough for new ADR-048 author docs to avoid linking to historical preview specs?
- Should generic ports be allowed in generated templates with a comment, or should scaffolds require authors to choose a concrete `DataObject` subclass before tests pass?

## Recommended Spec Requirements

- SPEC 3 must declare the current `docs/adr/ADR-048.md` as the sole governing previewer and plot-job design for this doc refresh.
- SPEC 3 must inventory and refresh package/block authoring docs, examples, skills, and templates together because templates and AI skills function as executable author documentation.
- SPEC 3 must require a new previewer-and-plot author guide covering package previewer registration, project-local previewers, `PreviewerSpec`, resolution precedence, same-origin frontend manifests, bounded `PreviewDataAccess`, plot manifests, Python/R plot templates, cache outputs, and the distinction between preview artifacts and workflow outputs.
- SPEC 3 must require package-author docs to explain that `scistudio.previewers` is separate from `scistudio.blocks` and `scistudio.types`.
- SPEC 3 must require imaging package documentation to describe package-owned Image/Label previewers once implemented, with core fallback previewers documented as generic fallback behavior.
- SPEC 3 must require block docs and scaffolds to align on concrete port guidance and valid `Port`/`OutputPort` fields.
- SPEC 3 must define exact in-scope globs:
  - `docs/block-development/**`
  - `docs/block-development/examples/**`
  - `packages/scistudio-blocks-imaging/README.md`
  - `packages/scistudio-blocks-*/README.md` only when the package gains ADR-048 previewers
  - `src/scistudio/_skills/scistudio/scistudio-inspect-data/SKILL.md`
  - `src/scistudio/_skills/scistudio/scistudio-write-block/SKILL.md` for narrow cross-reference updates
  - `src/scistudio/_skills/scistudio/scistudio-write-plot/SKILL.md`
  - `docs/cli-integration.md`
  - `src/scistudio/cli/templates/block_package/**`
  - `src/scistudio/blocks/_templates/block_base_template.py`
  - ADR-048 previewer and plot tests introduced by the implementation
- SPEC 3 must define out-of-scope globs:
  - legacy old ADR-048 material and old preview-provider specs
  - historical ADR files except for explicit owner-approved supersession notes
  - `docs/specs/data-preview-3d-viewer.md` except for a narrow historical/supersession cross-reference if approved
  - unrelated user docs that do not mention blocks, packages, previewers, plot jobs, skills, or preview APIs
  - package READMEs for LCMS/SRS unless ADR-048 adds or changes previewers there
- SPEC 3 must require verification through docs audits, generated-doc/facts checks where applicable, wheel skill packaging tests, template tests, package registry tests, and ADR-048 previewer/plot-job tests.
