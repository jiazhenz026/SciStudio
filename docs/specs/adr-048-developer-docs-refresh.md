---
spec_id: adr-048-developer-docs-refresh
title: "ADR-048 Package And Block Developer Documentation Rewrite Specification"
status: Planned
feature_branch: codex/adr-048-previewers-plot-jobs
created: 2026-06-10
input: "Owner-approved ADR-048 scope: the package and block developer docs are stale after recent package/block work and must be deleted and rewritten around current contracts, recent ADRs, previewers, and plot jobs."
owners:
  - "@jiazhenz026"
related_adrs:
  - 48
related_specs:
  - adr-048-preview-system
  - adr-048-ai-plot-tools
scope:
  in:
    - Delete and rewrite the active block and package developer documentation that teaches package layout, block contracts, custom types, previewers, plot jobs, tests, and publishing.
    - Audit all recent ADRs before rewriting so every new feature and changed authoring pattern is represented.
    - Align docs, examples, AI skills, and scaffolding templates because they all function as author guidance.
    - Add ADR-048 author guidance for package previewers, project previewers, and preview-side plot jobs.
    - Refresh imaging package docs when package-owned Image and Label previewers land.
    - Update AI-facing docs for `scistudio-write-plot` and current MCP preview/plot behavior.
  out:
    - Editing historical ADRs or legacy specs as governing sources.
    - Broad user documentation unrelated to blocks, packages, previewers, plot jobs, skills, or preview APIs.
    - LCMS/SRS package README rewrites unless those packages gain ADR-048 previewers.
    - Governance docs under `docs/ai-developer/**` unless separately approved with governance-touch scope.
    - Generated docs or generated facts by hand.
governs:
  modules: []
  contracts: []
  entry_points: []
  files:
    - docs/adr/ADR-048.md
    - docs/specs/adr-048-developer-docs-refresh.md
    - docs/block-development/**
    - packages/scistudio-blocks-imaging/README.md
    - packages/scistudio-blocks-*/README.md
    - src/scistudio/_skills/scistudio/SKILL.md
    - src/scistudio/_skills/scistudio/scistudio-write-block/SKILL.md
    - src/scistudio/_skills/scistudio/scistudio-inspect-data/SKILL.md
    - docs/cli-integration.md
    - src/scistudio/cli/templates/block_package/**
    - src/scistudio/blocks/_templates/block_base_template.py
tests:
  - tests/cli/test_new_block_package.py
  - tests/api/test_blocks_template.py
  - tests/blocks/test_registry_package_layout.py
  - tests/integration/test_block_sdk_e2e.py
  - tests/packaging/test_wheel_skills.py
  - tests/agent_provisioning/test_skills.py
  - tests/cli/test_install.py
  - tests/docs/test_block_development_docs.py
acceptance_source: adr
language_source: en
---

# ADR-048 Package And Block Developer Documentation Rewrite Specification

## 1. Change Summary

ADR-048 introduces a new author-facing extension surface: package and
project-local previewers, previewer routing, preview-side plot jobs, and AI plot
authoring tools. At the same time, several existing block/package docs and
templates have drifted from current implementation contracts. This spec defines
the documentation rewrite that must ship with the ADR-048 implementation.

This is a deliberate delete-and-rewrite of the active package and block
developer documentation. The target is the documentation that active package
authors, block authors, and AI assistants use to build SciStudio extensions.
The rewrite must align four surfaces:

1. human-facing docs under `docs/block-development/**`;
2. package READMEs that document shipped package behavior;
3. AI-facing skills under `src/scistudio/_skills/scistudio/**`;
4. scaffolding templates that act as executable documentation.

Historical ADRs and legacy specs remain historical records. They must not be
deleted or treated as the governing ADR-048 design.

The rewrite must start from a recent-ADR impact review, not from the old
developer docs. The implementation must inspect ADR-036 through ADR-048,
including ADR-042 and ADR-046 addenda, and extract every package/block authoring
feature, contract change, and changed recommended writing pattern that belongs
in the new docs.

## 2. User Scenarios & Testing

### User Story 1 - A package author learns the current package contract (Priority: P1)

As a package author, I need one current path that teaches blocks, types,
previewers, entry points, tests, and publishing without stale API names.

Independent Test: Generate a new block package from the current scaffold and
compare the docs against the generated entry points, ports, package info, and
tests.

Acceptance Scenarios:

1. Given the package publishing guide, when an author follows it, then the docs
   teach `scistudio.blocks`, `scistudio.types`, and `scistudio.previewers` as
   separate extension entry points.
2. Given current `OutputPort` code, when the docs and templates mention output
   ports, then they do not use a nonexistent `produced_type` field.
3. Given the package scaffold, when tests inspect the generated package, then
   docs examples match the scaffolded callable shape.

### User Story 2 - A block author uses concrete types by default (Priority: P1)

As a block author, I need docs and templates to steer me toward concrete
accepted types so preview routing, canvas behavior, and package validity remain
useful.

Independent Test: Run template tests and doc examples; verify default examples
use concrete `DataObject` subclasses or explicitly justify generic ports.

Acceptance Scenarios:

1. Given the block contract guide, when it explains `accepted_types`, then it
   states that empty accepted types are valid but generic and should be used
   deliberately.
2. Given quickstart examples, when they define ports, then they use concrete
   types unless the example is specifically about generic utilities.
3. Given the block authoring skill, when it guides an AI assistant, then it
   warns that generic ports weaken preview routing and canvas semantics.

### User Story 3 - A previewer author understands package and project previewers (Priority: P1)

As a package or project author, I need docs that explain how to add a full
interactive previewer without moving domain UI into core.

Independent Test: Add a small fixture previewer following the docs; verify it
registers through the same path the implementation tests use.

Acceptance Scenarios:

1. Given the previewer docs, when a package author reads them, then they learn
   how `PreviewerSpec`, backend provider, frontend manifest, and
   `scistudio.previewers` fit together.
2. Given a project author reads the same page, then they learn project-local
   override order and default previewer declarations.
3. Given an imaging package README, when rich Image/Label previewers ship, then
   it states that imaging owns image-domain preview UI while core owns only
   generic array fallback.

### User Story 4 - A user or agent learns plot jobs separately from blocks (Priority: P1)

As a user or AI assistant, I need plot-job docs to make clear that plots are
preview-side artifacts, not workflow blocks.

Independent Test: Review the plot guide and `scistudio-write-plot` skill; verify
both require target discovery and validation and both warn against editing the
workflow DAG for plot authoring.

Acceptance Scenarios:

1. Given the plot docs, when they explain target selection, then they point to
   stable workflow path, node ID, and output port rather than block labels.
2. Given the plot docs, when they show Python and R templates, then both use the
   ADR-048 `render(collection, context)` model.
3. Given the AI skill, when it describes completion criteria, then it requires
   `validate_plot` and `run_plot_job` before declaring the plot ready.

### User Story 5 - Stale docs are deleted and rewritten (Priority: P2)

As a maintainer, I need the active developer docs to be rebuilt from current
contracts and recent ADRs, not patched paragraph by paragraph from stale pages.

Independent Test: Search rewritten docs for known stale patterns such as
`produced_type=`, label-only plot binding, hardcoded image preview in core, and
old `preview_data` argument examples.

Acceptance Scenarios:

1. Given an active package/block developer doc under `docs/block-development/`,
   when the rewrite lands, then the old page content has been deleted and
   replaced by current guidance or the page has been intentionally removed.
2. Given historical ADR/spec files, when the docs rewrite lands, then they remain
   intact unless a separate owner-approved supersession note is scoped.
3. Given generated docs or generated facts, when the docs rewrite lands, then they
   are regenerated by tooling or left untouched with a tracked reason.

### User Story 6 - Recent ADRs drive the rewrite (Priority: P2)

As a maintainer, I need the rewritten docs to include every recent package,
block, workflow-authoring, and extension-authoring change, not only ADR-048.

Independent Test: Build a recent-ADR impact matrix from ADR-036 through ADR-048,
including addenda, and verify every author-facing item is either represented in
the rewritten docs or explicitly marked as non-author-facing.

Acceptance Scenarios:

1. Given ADR-041 defines CodeBlock v2 script-as-AppBlock behavior, when the
   docs are rewritten, then CodeBlock authoring guidance reflects that model.
2. Given ADR-043 defines IO format capabilities, when package docs are
   rewritten, then loader/saver package guidance uses capability declarations
   instead of legacy extension-only patterns.
3. Given ADR-044, ADR-045, ADR-046, ADR-047, and ADR-048 change workflow,
   registry, scheduler, and previewer semantics, when the docs are rewritten,
   then the relevant new authoring patterns are included or explicitly
   classified as not package/block developer-facing.

### Edge Cases

- A doc page is long-form and does not fit short-form document limits.
- A package README describes behavior that will not exist until a later
  implementation slice.
- Existing examples rely on legacy package entry-point names that still work but
  should not be the primary pattern.
- AI skill docs and human docs disagree on generic port guidance.
- A template test passes while the prose example is stale.
- A link points to a historical spec that could be mistaken as current.
- R plot support is documented even when CI may skip real R execution.
- A recent ADR is proposed rather than accepted but is still the governing
  design for a planned implementation slice.

## 3. Requirements

### Functional Requirements

- FR-001: The rewrite must declare `docs/adr/ADR-048.md` and its three companion
  specs as the governing design for previewers and plot jobs.
- FR-002: The rewrite must not use legacy old ADR-048 material or historical
  preview-provider specs as governing sources.
- FR-003: Active package and block developer docs under
  `docs/block-development/**` must be deleted and rewritten from current
  contracts and recent ADRs. The implementation must not patch stale pages in
  place as the primary strategy.
- FR-004: `docs/block-development/quickstart.md` must be rewritten around the
  current package scaffold and concrete port examples.
- FR-005: `docs/block-development/block-contract.md` must align with current
  `Block`, `InputPort`, `OutputPort`, dynamic port, `ProcessBlock`, `IOBlock`,
  and config-schema contracts.
- FR-006: Block contract docs and examples must not mention
  `OutputPort.produced_type` as a valid field.
- FR-007: Block docs must explain that empty `accepted_types` is runtime-valid
  but should be used deliberately because concrete types support routing,
  preview, and canvas behavior.
- FR-008: `docs/block-development/publishing.md` must teach current package
  layout, `PackageInfo`, package entry points, and wheel packaging expectations.
- FR-009: Package publishing docs must distinguish `scistudio.blocks`,
  `scistudio.types`, and `scistudio.previewers`.
- FR-010: `docs/block-development/custom-types.md` must explain that semantic
  data types register through `scistudio.types`, while display behavior
  registers through `scistudio.previewers`.
- FR-011: `docs/block-development/testing.md` must include package registry
  tests, previewer registration tests, template tests, skill packaging tests
  where applicable, and plot validation/run checks where applicable.
- FR-012: The rewrite must add a previewer-and-plot author guide
  under `docs/block-development/`.
- FR-013: The previewer guide must cover `PreviewerSpec`, `PreviewDataAccess`,
  backend providers, frontend manifests, same-origin asset loading, routing
  precedence, package previewers, project previewers, project defaults, and
  ambiguity behavior.
- FR-014: The plot guide must cover `plots/<plot_id>/plot.yaml`, Python and R
  templates, stable target binding, preview cache outputs, supported plot
  formats, validation, run behavior, and export/save semantics.
- FR-015: The docs must state that plot jobs are preview-side artifacts and do
  not become workflow blocks, DAG nodes, lineage outputs, or downstream
  collections.
- FR-016: `docs/block-development/examples/**` must be deleted and regenerated
  from current scaffolds or intentionally removed. Retained legacy examples must
  be outside the active tutorial path and clearly marked as legacy.
- FR-017: `src/scistudio/cli/templates/block_package/**` must be corrected
  where template output contradicts current contracts.
- FR-018: `src/scistudio/blocks/_templates/block_base_template.py` must be
  reviewed so generated block examples align with concrete-port guidance or
  clearly mark generic ports as deliberate.
- FR-019: `packages/scistudio-blocks-imaging/README.md` must document
  package-owned Image and Label previewers once the implementation lands.
- FR-020: LCMS/SRS package READMEs must remain out of scope unless those
  packages gain ADR-048 previewer behavior.
- FR-021: `src/scistudio/_skills/scistudio/scistudio-inspect-data/SKILL.md`
  must be updated for current preview inspection behavior and must not teach
  stale `preview_data` signatures.
- FR-022: `src/scistudio/_skills/scistudio/scistudio-write-block/SKILL.md` must
  be updated only where ADR-048 changes block author obligations or links to
  previewer/plot docs.
- FR-023: `src/scistudio/_skills/scistudio/scistudio-write-plot/SKILL.md` must
  be added by the plot tools implementation and covered by this docs rewrite.
- FR-024: `docs/cli-integration.md` must list the new plot skill and plot MCP
  tools after they are implemented.
- FR-025: Docs must avoid presenting compatibility adapters as preferred new
  APIs when ADR-048 defines a replacement contract.
- FR-026: Every new or changed doc link to ADR-048 specs, skills, package
  READMEs, and templates must be validated by available docs checks or a
  documented manual check.
- FR-027: Generated docs or generated facts must not be hand-edited.
- FR-028: Any deferred docs page or obsolete example retained temporarily must
  carry a tracked TODO or follow-up issue reference, not a chat-only deferral.
- FR-029: Before rewriting docs, the implementation must create a recent-ADR
  impact matrix covering ADR-036 through ADR-048 and addenda in that range.
- FR-030: The ADR impact matrix must classify each item as `include in
  package/block docs`, `include in AI skill/docs`, `implementation-only`, or
  `not developer-facing`.
- FR-031: Rewritten docs must include all matrix items classified as package,
  block, previewer, plot, IO, workflow-authoring, CodeBlock, package registry,
  package distribution, or AI authoring guidance.

### Documentation Inventory

Primary docs to delete and rewrite:

| Path | Required action |
|---|---|
| `docs/block-development/quickstart.md` | Delete old content and rewrite around current scaffold and concrete ports. |
| `docs/block-development/block-contract.md` | Delete old content and rewrite contract details against current code. |
| `docs/block-development/publishing.md` | Delete old content and rewrite package entry point and previewer publishing guidance. |
| `docs/block-development/custom-types.md` | Delete old content and rewrite type vs previewer boundary. |
| `docs/block-development/testing.md` | Delete old content and rewrite previewer, plot, template, and packaging checks. |
| `docs/block-development/data-types.md` | Delete old content and rewrite current data-object and preview implications. |
| `docs/block-development/collection-guide.md` | Delete old content and rewrite current collection and preview implications. |
| `docs/block-development/memory-safety.md` | Delete old content and rewrite bounded-access and large-data guidance. |
| `docs/block-development/architecture-for-block-devs.md` | Delete old content and rewrite extension architecture overview. |
| `docs/block-development/previewers-and-plots.md` | Create new ADR-048 author guide. |

Recent ADR review required before rewrite:

| ADR | Required review focus |
|---|---|
| ADR-036 | Project-file editor behavior that affects source files, scripts, and local extension editing. |
| ADR-037 | Desktop packaging, plugin distribution, first-run dependency management, and package install expectations. |
| ADR-038 | Run lineage and recipe-vs-storage language that affects how docs explain outputs and persisted artifacts. |
| ADR-039 | Git-backed project source control expectations for project-local code and generated files. |
| ADR-040 | Production agent reliability where it affects AI-facing authoring docs and skill behavior. |
| ADR-041 | CodeBlock v2 script-as-AppBlock model and current CodeBlock authoring patterns. |
| ADR-042 and addenda 1-6 | Gate ledger, docs/test evidence, agent workflow, and governance wording that affects AI-authored package/block docs. |
| ADR-043 | IO format capability registry, SimpleLoader/SimpleSaver, metadata fidelity, and package IO guidance. |
| ADR-044 | SubWorkflowBlock authoring-only semantics and inline flattening at load. |
| ADR-045 | Workflow and file state version-vector contract where docs mention project files or live state. |
| ADR-046 and addendum 1 | DAGScheduler decomposition and subprocess-wrapper class-binding rules where block execution docs mention scheduler/runtime internals. |
| ADR-047 | BlockRegistry decomposition and legacy IO finder removal; package registry docs must match the new registry posture. |
| ADR-048 | Previewer registration, project/package previewers, preview-side plot jobs, and plot MCP skill/tooling. |

Examples and templates:

| Path | Required action |
|---|---|
| `docs/block-development/examples/multi-block-package/**` | Regenerate or mark legacy; align entry-point callable. |
| `docs/block-development/examples/simple-transform/**` | Refresh port/type examples. |
| `docs/block-development/examples/custom-io-loader/**` | Refresh package and test guidance. |
| `src/scistudio/cli/templates/block_package/**` | Correct stale executable docs such as invalid output port fields. |
| `src/scistudio/blocks/_templates/block_base_template.py` | Align generic port guidance. |

AI and package docs:

| Path | Required action |
|---|---|
| `src/scistudio/_skills/scistudio/SKILL.md` | Add plot skill/tool catalog references. |
| `src/scistudio/_skills/scistudio/scistudio-write-block/SKILL.md` | Narrow cross-reference updates. |
| `src/scistudio/_skills/scistudio/scistudio-inspect-data/SKILL.md` | Refresh preview inspection examples. |
| `src/scistudio/_skills/scistudio/scistudio-write-plot/SKILL.md` | Add new plot authoring skill. |
| `docs/cli-integration.md` | Update skill/tool inventory. |
| `packages/scistudio-blocks-imaging/README.md` | Document package-owned image previewers. |

### Authoritative Sources

- `src/scistudio/blocks/base/block.py` for `Block` behavior.
- `src/scistudio/blocks/base/ports.py` for `Port`, `InputPort`, and
  `OutputPort`.
- `src/scistudio/blocks/base/package_info.py` for `PackageInfo`.
- `src/scistudio/blocks/registry/_scan.py` for block package discovery.
- `src/scistudio/core/types/registry.py` for type package discovery.
- ADR-048 and `adr-048-preview-system` for previewer contracts.
- `adr-048-ai-plot-tools` for plot tool and plot runtime contracts.
- Current scaffolding templates and their tests for executable examples.
- Current AI skills and provisioning tests for agent-facing author guidance.

## 4. Implementation Plan

### 4.1 Technical Approach

Treat this as a replacement pass over active authoring docs. For each page,
compare current prose against the implementation source of truth before editing.
Prefer rewriting stale pages over patching isolated paragraphs when the old
structure teaches the wrong model.

Docs must be synchronized with implementation slices:

- previewer docs land with the preview system implementation;
- plot docs and `scistudio-write-plot` land with the AI plot tools
  implementation;
- imaging README previewer content lands when imaging previewer registration
  lands;
- template docs land with template fixes.

### 4.2 Affected Files

Documentation:

- `docs/block-development/quickstart.md`
- `docs/block-development/block-contract.md`
- `docs/block-development/publishing.md`
- `docs/block-development/custom-types.md`
- `docs/block-development/testing.md`
- `docs/block-development/data-types.md`
- `docs/block-development/collection-guide.md`
- `docs/block-development/memory-safety.md`
- `docs/block-development/architecture-for-block-devs.md`
- `docs/block-development/previewers-and-plots.md`
- `docs/block-development/examples/**`
- `packages/scistudio-blocks-imaging/README.md`
- `docs/cli-integration.md`

Executable documentation:

- `src/scistudio/cli/templates/block_package/**`
- `src/scistudio/blocks/_templates/block_base_template.py`
- `src/scistudio/_skills/scistudio/SKILL.md`
- `src/scistudio/_skills/scistudio/scistudio-write-block/SKILL.md`
- `src/scistudio/_skills/scistudio/scistudio-inspect-data/SKILL.md`
- `src/scistudio/_skills/scistudio/scistudio-write-plot/SKILL.md`

Tests:

- `tests/cli/test_new_block_package.py`
- `tests/api/test_blocks_template.py`
- `tests/blocks/test_registry_package_layout.py`
- `tests/integration/test_block_sdk_e2e.py`
- `tests/packaging/test_wheel_skills.py`
- `tests/agent_provisioning/test_skills.py`
- `tests/cli/test_install.py`
- docs link/frontmatter/audit checks used by the gate workflow.

### 4.3 Implementation Sequence

1. Create the recent-ADR impact matrix for ADR-036 through ADR-048, including
   addenda in that range.
2. Classify each ADR-derived item as package/block docs, AI skill/docs,
   implementation-only, or not developer-facing.
3. Delete and rewrite active `docs/block-development/**` pages from current
   contracts and the ADR impact matrix.
4. Fix scaffold templates that are objectively inconsistent with current code.
5. Regenerate active examples from current scaffolds or remove them.
6. Add the previewers-and-plots guide once preview and plot schemas are stable.
7. Update AI skills and CLI integration docs for plot tools.
8. Update imaging package README when package previewers are implemented.
9. Run docs, template, package registry, skill packaging, and provisioning
   tests.

### 4.4 Verification Plan

Docs checks:

- frontmatter lint for new/changed spec and docs files where required;
- markdown link validation for every new ADR/spec/skill/package link;
- generated facts check where applicable;
- search checks for known stale phrases such as `produced_type=`, label-only
  plot binding examples, and old preview-data argument examples.
- recent-ADR impact matrix review proving ADR-036 through ADR-048 author-facing
  items are represented or explicitly classified out.

Template and code-linked checks:

- package scaffold tests prove generated ports and entry points are valid;
- registry package-layout tests prove docs match accepted entry-point patterns;
- block SDK e2e tests prove author examples remain executable;
- skill packaging and provisioning tests prove AI docs are shipped.

Manual review:

- follow the quickstart from a clean project;
- follow package publishing docs to identify the correct entry points;
- spot-check the rewritten docs against the recent-ADR impact matrix;
- follow previewer docs to identify where backend provider and frontend
  manifest code belongs;
- follow plot docs to scaffold, validate, and run a Python plot;
- read the imaging README as a package user and confirm image preview ownership
  is clear.

### 4.5 Risks And Rollback

Risk: Docs describe implementation details before they land.

Mitigation: Sequence docs with implementation slices and mark planned behavior
only in specs, not in user-facing guides. Rollback by keeping planned behavior
inside this spec until code lands.

Risk: Rewriting examples breaks users relying on old snippets.

Mitigation: Prefer current scaffold-compatible examples. If a legacy pattern is
still supported but not preferred, say so explicitly and provide the current
preferred pattern first.

Risk: Skills and human docs drift again.

Mitigation: Add tests or search checks for core snippets and stale phrases, and
keep AI skills linked to the same docs they summarize.

## 5. Success Criteria

### Measurable Outcomes

- SC-001: Block/package docs no longer contain invalid `OutputPort.produced_type`
  guidance.
- SC-002: Quickstart and examples use concrete port types by default.
- SC-003: Publishing docs teach `scistudio.blocks`, `scistudio.types`, and
  `scistudio.previewers` as distinct entry points.
- SC-004: A previewers-and-plots author guide exists and covers package
  previewers, project previewers, plot manifests, Python/R templates, and
  preview-only semantics.
- SC-005: `scistudio-write-plot` is documented in the base skill, installed
  skills, and CLI integration docs.
- SC-006: Imaging package README documents package-owned Image/Label previewers
  after the implementation lands.
- SC-007: Template, package registry, skill packaging, provisioning, and docs
  checks pass.
- SC-008: Historical ADRs and specs remain intact unless separately approved.
- SC-009: Any deferred docs rewrite item has a tracked issue or TODO reference.
- SC-010: The rewrite includes a recent-ADR impact matrix for ADR-036 through
  ADR-048 and addenda in that range.
- SC-011: Every matrix item classified as package/block or AI authoring guidance
  is represented in rewritten docs, skills, templates, or package README
  updates.

## 6. Assumptions

- `docs/block-development/**` remains the canonical home for block and package
  author docs unless a separate docs architecture decision moves it.
- The primary package entry-point pattern should follow the current scaffold and
  tests, even if the registry still accepts legacy callable shapes.
- AI skills are part of developer documentation because agents use them as
  operational authoring guides.
- LCMS and SRS docs do not need ADR-048 previewer updates until those packages
  register previewers.
- The exact text of user-facing docs should wait for the implementing PRs when
  schemas or tool signatures are still changing.
