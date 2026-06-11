---
doc_type: planning
title: "ADR-048 Recent-ADR Documentation Impact Matrix (ADR-036 .. ADR-048)"
status: living
owner: "@jiazhenz026"
last_updated: 2026-06-10
governed_by:
  - ADR-048
related_specs:
  - adr-048-developer-docs-refresh
summary: "Recent-ADR impact review driving the ADR-048 SPEC 3 developer-docs rewrite. Classifies every ADR-036..ADR-048 author-facing item as package/block docs, AI skill/docs, implementation-only, or not developer-facing (FR-029/FR-030, SC-010/SC-011)."
---

# ADR-048 Recent-ADR Documentation Impact Matrix

This matrix satisfies FR-029 / FR-030 and SC-010 / SC-011 of
[`adr-048-developer-docs-refresh`](../specs/adr-048-developer-docs-refresh.md).
It is the input the SPEC 3 rewrite started from: the active block/package
developer docs were rebuilt against current contracts **and** against every
author-facing change introduced from ADR-036 through ADR-048 (including the
ADR-042 addenda 1-6 and the ADR-046 addendum 1), not just ADR-048 itself.

Each row classifies one ADR-derived item into exactly one of four buckets:

- **package/block docs** — belongs in `docs/block-development/**` (rewritten this PR).
- **AI skill/docs** — belongs in `src/scistudio/_skills/scistudio/**` or `docs/cli-integration.md`.
- **implementation-only** — a runtime/internal change with no author-facing surface.
- **not developer-facing** — desktop/packaging/governance/UX with no block-author surface.

Every item classified as **package/block docs** or **AI skill/docs** is mapped
to the page, skill, template, or README that now covers it (SC-011). Items in
the other two buckets are recorded here as deliberately classified out (SC-010).

## 1. Classification matrix

| ADR / addendum | Author-facing item | Classification | Where it lands |
|---|---|---|---|
| ADR-036 | Project-file editor: block `.py` files are project source the user edits/hot-reloads | package/block docs | `quickstart.md` (Tier-1 drop-in + reload), `architecture-for-block-devs.md` (`hot_reload` on save) |
| ADR-036 | `GET /api/blocks/template` new-block template content (basic kind) | package/block docs | `quickstart.md` (the template is the editor's starting point; mirrors `block_base_template.py`'s generic-port default, documented in prose) |
| ADR-037 | Desktop packaging, plugin distribution, first-run dependency management | not developer-facing | recorded out; block-author docs only note `pip install` Tier-2 distribution in `publishing.md` |
| ADR-037 D11 | Plugin distribution version stamped onto `BlockSpec.version` from `importlib.metadata.version(distribution_name)` | package/block docs | `architecture-for-block-devs.md` (`block_version` is framework-injected; missing `pyproject` version fails registration) |
| ADR-038 | Run lineage recorded externally; `key_dependencies` is palette metadata, not a reproducibility contract | package/block docs | `architecture-for-block-devs.md` (lineage recorded externally; `key_dependencies` is UX only), `block-contract.md` (optional ClassVars) |
| ADR-038 | `get_lineage` reads recorded lineage; never fabricate provenance | AI skill/docs | `scistudio-inspect-data/SKILL.md` |
| ADR-039 | Git-backed project source control; block `.py` files are git-tracked; branch switch reloads palette | package/block docs | `architecture-for-block-devs.md` ("Custom blocks alongside git") |
| ADR-040 | Production agent reliability; concrete-port-type rule (§3.2a); `DataObject` reserved for generic blocks | AI skill/docs + package/block docs | `scistudio-write-block/SKILL.md` (§3 enforcement), `block-contract.md` + `quickstart.md` (concrete-port-by-default prose) |
| ADR-040 §3.4/§3.9 | Packaged skill tree; cross-install to Claude + Codex; six task skills | AI skill/docs | `docs/cli-integration.md`, base `SKILL.md` index |
| ADR-041 | CodeBlock v2 — script-as-AppBlock model; arbitrary Python computation, no Collection iteration | package/block docs | `block-contract.md` (CodeBlock in the base hierarchy), `scistudio-write-block/SKILL.md` (`code` category row) |
| ADR-042 + addenda 1-6 | Gate ledger / docs+test evidence / agent workflow / governance | not developer-facing | recorded out; governance lives under `docs/ai-developer/**` (out of scope for SPEC 3). Block-author docs carry only the standard frontmatter `governed_by`. |
| ADR-043 | IO format capability registry; `FormatCapability`; `SimpleLoader`/`SimpleSaver`; metadata fidelity; capability ids as replay keys | package/block docs | `block-contract.md` ("IO Format Capabilities"), `publishing.md` ("Published IO Format Capabilities"), `quickstart.md` (Simple local IO) |
| ADR-044 | `SubWorkflowBlock` authoring-only semantics; inline flattening at load; generic `DataObject` ports are legitimately generic here | package/block docs | `block-contract.md` (base hierarchy + SubWorkflow note), `architecture-for-block-devs.md`, concrete-port prose (SubWorkflow is the named generic-port exception) |
| ADR-045 | Workflow / file-state version-vector contract | not developer-facing | recorded out; no block-author surface (project files / live state, not block contracts) |
| ADR-046 + addendum 1 | DAGScheduler decomposition; subprocess-wrapper class-binding rules | implementation-only | recorded out; `architecture-for-block-devs.md` keeps the author-facing "each block runs in a subprocess" model without scheduler internals |
| ADR-047 | `BlockRegistry` decomposition (private helpers, not helper classes); legacy IO finder removal; capability-aware lookup is canonical | package/block docs | `publishing.md` + `testing.md` (registry posture: entry-point callable protocol, capability lookup), `block-contract.md` (IO capabilities), `architecture-for-block-devs.md` |
| ADR-048 SPEC 1 | Previewer registration; `PreviewerSpec`, `PreviewDataAccess`, routing precedence; package + project previewers; project default + ambiguity; same-origin frontend manifests; `scistudio.previewers` entry point | package/block docs | `previewers-and-plots.md` (new), `publishing.md` + `custom-types.md` (three entry points; types vs previewers boundary), `packages/scistudio-blocks-imaging/README.md` (package-owned Image/Label previewers) |
| ADR-048 SPEC 1 | Core fallback previewers vs package-owned domain previewers (imaging owns `Image`/`Label`; core owns generic `Array` fallback) | package/block docs | `previewers-and-plots.md`, `data-types.md` (preview implications), imaging README |
| ADR-048 SPEC 2 | Preview-side plot jobs; `plots/<id>/plot.yaml`; Python/R `render(collection, context)`; stable target binding; preview cache; supported formats; validate/run; export/save; plots are NOT workflow blocks | package/block docs + AI skill/docs | `previewers-and-plots.md` (plot half), `scistudio-write-plot/SKILL.md` (landed SPEC 2; cross-linked), `docs/cli-integration.md` (6 plot tools) |
| ADR-048 SPEC 2 | `preview_data(ref, fmt)` MCP signature (no `max_rows`/`max_dim` args; type-driven dispatch) | AI skill/docs | `scistudio-inspect-data/SKILL.md` |

## 2. Items deliberately classified out (SC-010)

- **ADR-037 desktop packaging / first-run deps** — installer and bundling
  behavior; block authors only see standard `pip install` Tier-2 distribution.
- **ADR-042 + addenda 1-6 governance** — gate ledger, evidence, agent workflow.
  Governance docs are `docs/ai-developer/**`, a separate governance surface out
  of SPEC 3 scope. Block-author pages carry only `governed_by` frontmatter.
- **ADR-045 version-vector contract** — project-file / live-state consistency;
  no block-contract surface.
- **ADR-046 + addendum 1 scheduler/subprocess internals** — implementation-only.
  Author docs keep the stable "block runs in a subprocess" mental model and do
  not document `DAGScheduler` decomposition or class-binding rules.

## 3. Stale patterns removed by this rewrite (SC-001 / User Story 5)

- `OutputPort(..., produced_type=...)` — `OutputPort` has no `produced_type`
  field (`src/scistudio/blocks/base/ports.py`). The scaffold template
  (`blocks.py.tpl`) and all docs/examples now use `accepted_types=[...]`.
- Label-only plot binding — plot jobs bind by stable workflow path + node id +
  output port, never by a human block label.
- Hardcoded image preview in core — the rich image-domain previewer is
  package-owned (`scistudio-blocks-imaging`); core ships only the generic
  `Array` fallback.
- Old `preview_data(ref, max_rows?, max_dim?)` argument examples — the
  implemented MCP tool is `preview_data(ref, fmt)` with type-driven dispatch.

## 4. Primary entry-point pattern decision

The current scaffold and its tests (`tests/cli/test_new_block_package.py`,
`tests/api/test_blocks_template.py`) make `get_blocks() -> tuple[PackageInfo,
list[type]]` the **primary** published-package callable. The registry
(`src/scistudio/blocks/registry/_scan.py`) also accepts a plain
`list[type[Block]]`, a direct block class, and the monorepo-fallback name
`get_block_package()`. SPEC 3 docs teach `get_blocks()` returning the
`(PackageInfo, list[type])` tuple as the one primary pattern and note the
also-accepted shapes so existing packages keep working (FR-025: do not present
the also-accepted legacy shapes as the preferred new API).
