---
title: "PR #1577 ADR-048 Final Implementation Review"
audit_date: 2026-06-13
auditor: "audit_reviewer (Codex)"
issue: 1635
reviewed_pr: 1577
reviewed_head: 669ddcf3d75952db153bb84a9daaffdd5b09f742
review_branch: review-target/pr1577
report_branch: audit/pr1577-adr048-final-review
governing_adr: docs/adr/ADR-048.md
governing_specs:
  - docs/specs/adr-048-preview-system.md
  - docs/specs/adr-048-ai-plot-tools.md
  - docs/specs/adr-048-developer-docs-refresh.md
recommendation: block-merge
language_source: en
---

# PR #1577 ADR-048 Final Implementation Review

## Verdict

**Block merge. Do not remove `[DO NOT MERGE]` yet.**

PR #1577 has real progress: the live `DataPreview` surface now mounts
`PreviewHost`, the legacy one-shot REST preview route is deleted, collection
routing no longer falls through to item previewers, core fallback viewers exist,
the REST plot run route can register a produced plot artifact into the catalog,
and CI is green.

The implementation is still not complete against the owner request, ADR-048, and
SPEC 2's "AI plot tools show the result in the preview panel" contract. The
highest-risk gap is that the path real AI agents are instructed to use
(`mcp__scistudio__run_plot_job`) still returns only preview-cache artifacts and a
cache key; the catalog registration that creates a `plot_artifact` preview target
exists only behind the new REST route. There is also no production UI affordance
that calls that REST route. The result is a partially wired plot path that is
well-tested in isolation but still not user-reachable or agent-reachable as
claimed.

## Blocking Findings

### P1-1: AI plot output is still not wired from the actual MCP tool path to the preview panel

**Requirement:** ADR-048 and SPEC 2 require preview-side plot jobs to display
artifacts through the core `PlotPreviewer` in the selected preview panel. SPEC 2
states the user story as "show it in the preview panel" and FR-031/SC-010 require
successful plot artifacts to be consumable by `PlotPreviewer`.

**What PR #1577 implements:** the REST path is wired:

- `src/scistudio/api/routes/plots.py:49-120` defines `POST /api/plots/run`,
  calls `run_plot_job`, and, on success, calls
  `runtime.register_plot_artifact(...)` before returning `data_ref`.
- `src/scistudio/api/runtime/_data.py:71-134` registers the artifact as a
  catalog `DataRecord` with `plot_artifact` metadata.
- `frontend/src/lib/api/data.ts:42-50` builds a `plot_artifact` target from the
  REST response.
- `tests/api/test_plot_preview_wiring.py` proves
  `POST /api/plots/run -> register_plot_artifact -> POST /api/previews/sessions
  -> core.plot.basic`.

**What remains unwired:** the actual AI-facing tool path does not use that REST
registration path:

- `src/scistudio/ai/agent/mcp/tools_plot/tools.py:244-272` exposes
  `run_plot_job` and returns `_runtime.run_plot_job(...)` directly.
- `src/scistudio/ai/agent/mcp/tools_plot/models.py:278-297` defines
  `PlotRunResult` with `artifact_paths`, `metadata_path`, and `cache_key`, but no
  `data_ref` or `PreviewTarget`.
- `src/scistudio/ai/agent/mcp/tools_plot/runtime.py:220-337` writes
  `.scistudio/previews/.../current.*` and `current.json`; it does not call
  `ApiRuntime.register_plot_artifact`.
- `src/scistudio/_skills/scistudio/scistudio-write-plot/SKILL.md:21-22` and
  `tools_plot/models.py:297` still tell agents that success shows the artifact
  through `PlotPreviewer`, but the MCP result cannot open a routed preview
  session by itself.
- Production frontend search found no non-test caller of
  `dataApi.runPlotJob` or `plotTargetFromRunResponse` outside
  `frontend/src/lib/api/data.ts`.
- No `frontend/src/components/DataPreview.parts/PlotPreviewPanel.tsx` exists in
  the PR head.

**Claim audit:** this is the same "dead-wire" class the PR claims to have fixed.
The merged sub-PR #1631 says the GUI can open a routed plot preview and defers
only pane placement, but it also says the deferral is gated on #1592
(`PreviewHost` not mounted). In PR #1577, `fix(#1592)` later mounts
`PreviewHost` in `frontend/src/components/DataPreview.tsx:137`, so the quoted
deferral rationale is stale. Issue #1623 also claims an exported, tested
`PlotPreviewPanel`, but that file is absent.

**Impact:** an agent following the shipped `scistudio-write-plot` skill runs the
MCP tool, receives a cache artifact, and has no catalog `data_ref` or production
UI hook to open the `PlotPreviewer`. The REST path is useful infrastructure, but
it does not satisfy the user-facing/AI-facing contract by itself.

**Required fix before merge:** make one canonical plot-display path real and
tested end-to-end. Either the MCP `run_plot_job` path must register/return a
routable preview target, or the production UI must call `POST /api/plots/run`,
call `plotTargetFromRunResponse`, and mount/open `PreviewHost`. The shipped skill
and `next_step` text must match the actual path. Add an automated integration
test that starts from the public AI/tool or UI entry point, not just the REST
helper.

### P1-2: The no-compatibility sweep claimed for #1594 is incomplete

Issue #1594 explicitly reversed ADR-048's compatibility-adapter posture for this
pre-alpha repo and listed the MCP inspection compatibility adapter as in scope:
the retained "8 MiB-cap compatibility adapter" in `tools_inspection` should be
re-evaluated, dropped, or migrated to the canonical contract.

PR #1577 correctly deletes the old REST preview compatibility surface:

- `api.getDataPreview`, `GET /api/data/{ref}/preview`,
  `ApiRuntime.preview_data`, `_envelope_to_legacy_preview`,
  `_preview_query_for_record`, and `DataPreviewResponse` are absent from live
  product code.

However, a live compatibility path remains:

- `src/scistudio/ai/agent/mcp/tools_inspection/read.py:170` still exposes
  `preview_data`.
- `src/scistudio/ai/agent/mcp/tools_inspection/_preview.py:4-9` says the preview
  implementation was "preserved verbatim from the pre-FastMCP impl" with "No
  behavior change."
- `tests/ai/test_mcp_tools_inspection.py:111-182` still tests that tool directly,
  including the bounded TIFF compatibility behavior.
- `docs/specs/adr-048-preview-system.md:312-313` still permits explicitly
  retaining a compatibility adapter for this MCP path, while #1594 and the owner
  request say no legacy compatibility layers should keep running.

**Impact:** the PR body closes #1594, but #1594's MCP-inspection item is still
live and still documented as compatibility code. This is not the deleted REST
route; it is a separate legacy surface that remains callable by agents.

**Required fix before merge:** either migrate MCP `preview_data` to the canonical
ADR-048 preview/session/data-access contract and delete the compatibility text,
or explicitly record an owner-approved ADR/spec amendment saying this MCP tool is
not part of the #1594 no-compat sweep. Without that decision, closing #1594 is
not accurate.

## Non-Blocking But Merge-Relevant Findings

### P2-1: No current canonical e2e evidence covers every viewer at PR #1577 head

The user request explicitly asks that e2e can run successfully for every viewer.
I found automated unit/integration coverage for many viewers, but no committed
canonical live e2e scenario for the final PR head:

- `docs/ai-developer/e2e/` contains only `README.md` and `template.md`; there is
  no filled ADR-048/PR1577 e2e session file.
- `frontend/e2e/specs/system-flows.spec.ts` is an ADR-043/general workflow spec,
  not ADR-048 per-viewer coverage.
- `frontend/e2e/support/systemMocks.ts:204` still mocks
  `/api/data/obj-1/preview`, the deleted legacy preview endpoint.
- `docs/audit/2026-06-11-adr-048-smoke-tests.md` is useful historical browser
  smoke evidence, but it predates the final #1604/#1592 cutover. It explicitly
  notes at lines 49-51 that the live preview panel was still fetching the legacy
  `GET /api/data/{ref}/preview` path for core types, and it only screenshots a
  subset of the viewer types.

The component and API tests are valuable, but they do not prove a live user can
exercise DataFrame, Array, Series, Text, Artifact, CompositeData, Collection,
package Image/Label, and Plot through the running app at the final PR head.

### P2-2: Several shipped claims and docs are stale or self-contradictory

The implementation relies on documentation and issue text that now disagree with
the code:

- `CHANGELOG.md:22` and PR #1631 say `PreviewHost` is not mounted in production,
  but PR #1577 later mounts it at `DataPreview.tsx:137`.
- Issue #1623 says #1606 added `PlotPreviewPanel` and
  `GET/POST /api/previews/plots[/session]`; neither exists in PR #1577.
- `frontend/src/lib/api/data.ts:36-40` still says the plot builder is deferred
  partly because `PreviewHost` is not mounted, which is stale after #1592.
- `docs/specs/adr-048-preview-system.md` still contains compatibility language
  that conflicts with the no-compat migration: examples include lines 17, 196,
  418-419, 444, 560, and 608, even though FR-007/FR-008 now say the legacy route
  was removed.

This matters because SciStudio agents use these docs and issue bodies as runtime
instructions. Stale "done" and "deferred" claims are exactly how dead-wired paths
escape review.

## Verified Working Areas

- **Live preview mount:** `frontend/src/components/DataPreview.tsx:137` mounts
  `PreviewHost` for the active output. `DataPreview.test.tsx:73-90` covers the
  routed session call.
- **Legacy REST preview route removed:** live code no longer defines
  `GET /api/data/{ref}/preview`, `ApiRuntime.preview_data`,
  `_envelope_to_legacy_preview`, `DataPreviewResponse`, or frontend
  `getDataPreview`. Remaining matches are comments/tests/spec text plus the MCP
  inspection tool called out above.
- **Collection routing fixed:** `src/scistudio/previewers/router.py:65-123`
  prevents collection targets from resolving to single-item previewers before
  the core collection fallback. Regression tests live in
  `tests/previewers/test_preview_routing.py:134-168`.
- **Core fallback viewers present:** `fallbacks.py:535-600` registers
  `core.dataframe.basic`, `core.array.basic`, `core.series.basic`,
  `core.text.basic`, `core.artifact.basic`, `core.composite.basic`,
  `core.collection.basic`, `core.plot.basic`, and `core.base.fallback`.
  `coreViewers.tsx:111-879` dispatches DataFrame, Array, Series, Text,
  Artifact, Composite, Collection, and Plot viewer components.
- **#1598 dependency inversion fixed:** `tests/architecture/test_layer_deps.py`
  guards that `scistudio.previewers` must not import up into `scistudio.api`.
  Current `previewers` references to API are explanatory comments; helper code
  was moved down into `previewers/_table_cache.py` and `previewers/_raster.py`.
- **TableViewer session migration fixed:** `PreviewHost.test.tsx:391-455`
  verifies pagination/sort goes through `patchPreviewSession`, not the deleted
  legacy route.
- **REST plot preview wiring works:** `tests/api/test_plot_preview_wiring.py`
  proves the REST route can register a plot artifact and open it through
  `core.plot.basic`.
- **Developer-doc guardrails exist:** `tests/docs/test_block_development_docs.py`
  guards the ADR-048 docs/scaffold/skill surfaces against several stale patterns.

## Test Evidence Collected

Target PR head: `669ddcf3d75952db153bb84a9daaffdd5b09f742`.

Commands run locally in a dedicated review worktree:

- `PYTHONPATH=src python -m pytest tests/architecture/test_layer_deps.py
  tests/previewers tests/api/test_previewers.py
  tests/api/test_plot_preview_wiring.py tests/api/test_preview_plot_jobs.py
  tests/ai/test_mcp_tools_plot.py tests/ai/test_mcp_tools_inspection.py
  tests/docs/test_block_development_docs.py -q --no-cov` - passed; one R
  test skipped because `Rscript` is not on PATH.
- `PYTHONPATH='src;..\\..\\src' python -m pytest
  packages/scistudio-blocks-imaging/tests/test_previewer_registration.py -q
  --no-cov` - 14 passed.
- `cd frontend && npm ci` - installed locked dependencies; npm reported 9 audit
  vulnerabilities (3 moderate, 6 high), not analyzed as part of this ADR-048
  feature audit.
- `cd frontend && npm run test -- src/components/DataPreview.test.tsx
  src/components/DataPreview.parts/PreviewHost.test.tsx
  src/components/DataPreview.parts/coreViewers.test.tsx
  src/lib/api/__tests__/plotPreview.test.ts` - 4 files / 37 tests passed.

GitHub checks for PR #1577 were green at audit time: Analyze, Architecture
Tests, CodeQL, Deferral discipline, Frontend, Full Audit, Import Contracts, Lint
and Format, Semantic duplication ratchet, Python 3.11/3.13 tests, Type Check,
Verify Workflow Compliance, and Wheel Release Smoke all passed.

## Issue Cross-Check

- #1574, #1575, #1576: implemented in the consolidated PR, but final readiness
  depends on the P1 findings above.
- #1592: code appears fixed by the live `PreviewHost` mount, but old issue/PR
  text is still being used in later deferral claims.
- #1593: fixed by collection-aware router precedence and regression tests.
- #1594: not fully fixed because MCP inspection `preview_data` compatibility
  remains live unless the owner narrows the issue.
- #1598: fixed and guarded by a layer-dependency test.
- #1603: implemented; backend/frontend targeted tests pass.
- #1604: implemented for the REST/frontend table path; old route deleted.
- #1606: partially fixed. The REST/catalog path is real, but the actual AI MCP
  tool path and production UI affordance remain unwired.
- #1623: still open and should be treated as a real user-reachability blocker for
  plots, not only a cosmetic pane-placement issue.
- #1626: tracked save-to-project flow. This appears to be a legitimate follow-up
  if export/download remains available and owner accepts that save-to-project is
  outside the initial display contract.

## Recommended Exit Criteria For PR #1577

1. Make the plot path agent/user reachable from the public entry point, then add
   a test that starts from that public entry point and proves the `PlotPreviewer`
   opens.
2. Add a filled `docs/ai-developer/e2e/YYYY-MM-DD-adr048-pr1577-viewers.md`
   session, or an equivalent committed e2e artifact, covering every viewer type
   at the final PR head.
3. Resolve #1594 honestly: delete/migrate the MCP compatibility preview path or
   record a narrowed owner decision.
4. Clean stale PR/CHANGELOG/spec/issue claims so future agents are not routed by
   false evidence.

Until those are done, PR #1577 is not complete enough to merge.
