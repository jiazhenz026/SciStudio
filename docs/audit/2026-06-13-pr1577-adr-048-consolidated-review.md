# PR #1577 ADR-048 Consolidated Implementation Review

**Date:** 2026-06-13
**PR:** #1577 — `[DO NOT MERGE] ADR-048: complete preview system + AI plot tools + developer docs (SPEC 1+2+3 consolidated)`
**Branch:** `track/adr-048-spec1-preview-system`
**Reviewer:** Claude Opus 4.6 (audit persona)
**Scope:** Full implementation quality audit against ADR-048 and companion specs

## Executive Summary

PR #1577 consolidates all ADR-048 work across three specs (preview system,
AI plot tools, developer docs) and ten issues into one reviewable surface.
The audit examined backend wiring, frontend wiring, plot tool completeness,
docs rewrite quality, legacy code removal, test coverage, and open issue
status.

**Overall verdict: CONDITIONAL PASS — one critical gap, two moderate findings,
and several minor observations.**

The implementation is feature-complete against all three specs. The critical
gap is a missing entry point declaration that blocks package previewer
discovery in pip-installed deployments.

## Findings

### CRITICAL

#### C-1: Missing `scistudio.previewers` entry point in main pyproject.toml

**Location:** `pyproject.toml` between lines 115 (`scistudio.types`) and 117
(`scistudio.runners`).

**Problem:** The imaging package correctly declares
`[project.entry-points."scistudio.previewers"]` in its own `pyproject.toml`,
and the `PreviewerRegistry` correctly calls
`importlib.metadata.entry_points(group="scistudio.previewers")` to discover
package previewers. However, the main SciStudio `pyproject.toml` never
declares this entry point group. In production pip installs, package
previewers will not be discovered.

**Workaround:** Monorepo dev mode works because the registry has an explicit
`_scan_monorepo_packages()` fallback that walks `packages/scistudio-blocks-*`
directories. Tests pass because they use monorepo discovery or explicit
registration.

**Required fix:** Add the entry point group section to pyproject.toml:

```toml
[project.entry-points."scistudio.previewers"]
# Core previewers are loaded unconditionally; this group exists for
# installed packages to register through scistudio.previewers.
```

**Impact:** Without this fix, any pip-installed SciStudio deployment with
the imaging package installed separately will silently fall back to core
array viewers for Image/Label data, defeating the purpose of SPEC 1.

---

### MODERATE

#### M-1: Issue #1579 implemented but not in PR closing list

**Problem:** Issue #1579 ("make frontend_manifest a first-class
session-envelope field") is fully implemented in this PR:

- `PreviewSessionManager` auto-injects the resolved spec's
  `frontend_manifest` onto the envelope.
- `PreviewEnvelopeModel` has a first-class `frontend_manifest` field.
- `PreviewHost.tsx` reads from `envelope.frontend_manifest` with fallback to
  `envelope.metadata.frontend_manifest`.
- `tests/previewers/test_preview_session_manifest.py` covers auto-inject,
  provider-wins precedence, and null-manifest.
- A gate record exists at
  `.workflow/records/1579-issue-1579-frontend-manifest.json`.

The PR body and commit history confirm this work (the HEAD commit message
references "#1579"), but the PR body's "Closes" list does not include
`Closes #1579`.

**Required fix:** Add `Closes #1579` to the PR description.

#### M-2: Spec test file renamed without spec update

**Problem:** The preview system spec (`docs/specs/adr-048-preview-system.md`)
lists `tests/previewers/test_preview_sampling.py` in the `tests:` frontmatter
(line 57). The actual file on the branch is named
`tests/previewers/test_preview_data_access.py`. The content covers the same
FR-009/FR-010 bounded data-access requirements — this is a naming mismatch,
not a coverage gap.

**Required fix:** Update the spec frontmatter to reference the actual filename.

---

### MINOR / OBSERVATIONS

#### O-1: No ADR-048-specific e2e scenario file

No file under `docs/ai-developer/e2e/` covers the ADR-048 preview or plot
flow. Given issues #1623 (PlotPreviewPanel mounting) and #1626 (save-to-project
flow) are intentionally deferred, this is likely intentional. However, a basic
e2e scenario (upload data → create preview session → paginate → run plot →
view plot artifact) would strengthen confidence before merge.

#### O-2: Additional test files beyond spec listing

The PR includes several test files not listed in any spec's `tests:`
frontmatter but that provide valuable coverage:

- `tests/previewers/test_preview_security.py` (SVG sanitization, TIFF bounded-read)
- `tests/previewers/test_preview_session_manifest.py` (#1579 manifest stamping)
- `tests/previewers/test_table_cache_surface.py` (#1598 layer fix)
- `tests/previewers/test_fallback_array.py` (core array fallback)
- `tests/previewers/test_preview_registry.py` (registry CRUD)

These are bonus coverage, not gaps. Consider adding them to the spec
`tests:` list for traceability.

#### O-3: Related open issues correctly NOT in closing list

The following open issues are related to ADR-048 but correctly remain open
as intentional follow-ups:

| Issue | Title | Assessment |
|-------|-------|------------|
| #1623 | Mount PlotPreviewPanel in app shell | UX placement, deferred |
| #1626 | Explicit save-to-project flow for preview plot artifacts | saveArtifact host method stubs, deferred |
| #1578 | DRY core fallback provider envelope-building | Quality cleanup, deferred |

---

## SPEC 1 — Preview System: Detailed Audit

### Backend

| Component | Status | Evidence |
|-----------|--------|----------|
| PreviewerRegistry (core/package/project discovery) | PASS | `registry.py`: core, entry-point, monorepo, project-local loading |
| PreviewRouter (9-level ADR-048 §3 precedence) | PASS | `router.py`: exact type, parent fallback, collection, ambiguity |
| PreviewSession (lifecycle: create/read/patch/resource) | PASS | `session.py`: thread-safe LRU store, error wrapping |
| PreviewDataAccess (7 bounded helpers) | PASS | `data_access.py`: dataframe_page, array_plane, series_points, text_chunk, artifact_metadata, composite_slots, collection_sample |
| Core fallback previewers (8 + error fallback) | PASS | `fallbacks.py`: DataFrame, Array, Series, Text, Artifact, Composite, Collection, Plot, base fallback |
| API routes (POST/GET/PATCH sessions, resources, assets) | PASS | `routes/data.py`: all 5 routes implemented |
| Legacy `GET /api/data/{ref}/preview` deleted | PASS | No compat adapter; comment documents #1604 removal |
| SVG sanitization (FR-019) | PASS | Regex script/event/href stripping in fallbacks + iframe sandbox in frontend |
| Imaging package migration | PASS | `scistudio-blocks-imaging`: Image/Label previewers, entry point, frontend assets |
| API schemas | PASS | `schemas.py`: PreviewTargetModel, PreviewEnvelopeModel, session CRUD models |
| **pyproject.toml entry point** | **FAIL** | **See C-1** |

### Frontend

| Component | Status | Evidence |
|-----------|--------|----------|
| PreviewHost (session creation, fallback, ESM loading) | PASS | `PreviewHost.tsx`: 478 LOC, full lifecycle |
| Core fallback viewers (9 kinds) | PASS | `coreViewers.tsx`: 880 LOC, all viewers |
| ArrayViewer (scalar/1D/2D/ND modes) | PASS | PyCharm-style heatmap, axis selectors, diverging colormap |
| PlotViewer (PNG/JPEG/SVG/PDF) | PASS | SVG sandboxed iframe, PDF iframe, image tag |
| Dynamic previewer loading | PASS | `dynamicPreviewer.ts`: same-origin validation, ESM import |
| Previewer host API (constrained) | PASS | `previewerHostApi.ts`: no workflow mutation exposed |
| Legacy code removed | PASS | PreviewRenderer, ImageViewer, luts, OMEMetadataPanel deleted |
| API surface (session methods) | PASS | `data.ts`: create/get/patch session, resources, plot run |
| Types (PreviewTarget, Envelope, etc.) | PASS | `api.ts`: 176 additions, 9 EnvelopeKind values |
| Store (session-based cache) | PASS | `previewSlice.ts`: composite cache key per FR-021 |
| Tests | PASS | PreviewHost.test.tsx (14), coreViewers.test.tsx (13), DataPreview.test.tsx (5) |

---

## SPEC 2 — AI Plot Tools: Detailed Audit

| Component | Status | Evidence |
|-----------|--------|----------|
| 6 MCP tools implemented | PASS | tools_plot/: list_plot_targets, scaffold_plot, list_plot_examples, read_plot_source, validate_plot, run_plot_job |
| Tool registration (FastMCP side-effect) | PASS | `mcp/__init__.py` imports tools_plot |
| Models (PlotTarget, PlotManifest, PlotRunResult) | PASS | `models.py`: strict schemas with extra=forbid |
| Target discovery (stable target_id) | PASS | `targets.py`: deterministic ID from workflow_path + node_id + port |
| Scaffold (Python/R templates) | PASS | `scaffold.py`: render(collection, context) contract |
| Validation (manifest, path, target, entrypoint) | PASS | `validation.py`: path traversal rejection, runner checks |
| Runtime (subprocess execution, cache writes) | PASS | `runtime.py`: CodeBlock runner reuse, confined working dir |
| Harness (Python/R context helpers) | PASS | `_harness.py`: context.plt, to_dataframe, save_figure |
| Path safety (project root confinement) | PASS | Plot ID regex, relative_to checks, _safe_seg sanitization |
| Plot-artifact preview wiring (#1606) | PASS | register_plot_artifact → POST /api/plots/run → catalog → PlotPreviewer |
| Frontend integration (runPlotJob, plotTargetFromRunResponse) | PASS | `data.ts`: run + target builder |
| System prompt (plot category) | PASS | `system_prompt.py`: category "plot" |
| Skill (scistudio-write-plot) | PASS | `SKILL.md`: 156 LOC, target discovery workflow |
| Provisioning (skills.py, _orchestrate.py) | PASS | Updated skill list + expected count |
| Examples (matplotlib, seaborn, ggplot2) | PASS | `examples.py`: curated catalog |

---

## SPEC 3 — Developer Docs: Detailed Audit

| Component | Status | Evidence |
|-----------|--------|----------|
| 9 docs rewritten (block-development/*) | PASS | All substantially rewritten, not touch-ups |
| New previewers-and-plots.md guide | PASS | 504 LOC: PreviewerSpec, providers, manifests, routing, plots |
| ADR impact matrix (ADR-036..048) | PASS | `docs/planning/adr-048-impact-matrix.md` |
| Stale content eliminated | PASS | No produced_type=, no label-only binding, no old preview_data args |
| Imaging README updated | PASS | Package-owned previewers documented |
| Skills refreshed (inspect-data, write-block, write-plot) | PASS | All three updated or created |
| Examples updated | PASS | multi-block-package, simple-transform, custom-io-loader |
| Guardrail tests | PASS | `test_block_development_docs.py`: 17 tests, stale phrase + link checks |

---

## Legacy Code Scan

| Target | Status | Notes |
|--------|--------|-------|
| `getDataPreview` (frontend) | CLEAN | Removed; comment documents #1604 |
| `DataPreviewResponse` (backend) | CLEAN | Removed; comment documents #1604 |
| `_envelope_to_legacy_preview` | CLEAN | Removed; comment documents deletion |
| `_preview_query_for_record` | CLEAN | Removed; not found |
| ImageViewer.tsx | CLEAN | Deleted from core; ported to imaging package |
| PreviewRenderer.tsx | CLEAN | Deleted |
| luts.ts | CLEAN | Deleted from core; ported to imaging package viewer.js |
| useSlicePreview.ts, useOmeMetadata.ts | CLEAN | Deleted |
| OMEMetadataPanel.tsx | CLEAN | Deleted |
| `preview.kind` dispatch | CLEAN | Replaced by EnvelopeKind routing |

---

## Test Coverage Summary

**153 test points across 19+ files.**

| Category | Files | Test Count | Status |
|----------|-------|------------|--------|
| Previewer subsystem (routing, registry, data access, security, session, fallback, cache) | 7 | ~52 | PASS |
| API integration (previewers, plot wiring, data) | 3 | ~27 | PASS |
| Packaging + provisioning (wheel skills, skill install) | 2 | ~14 | PASS |
| Docs guardrails | 1 | 17 | PASS |
| Frontend (PreviewHost, coreViewers, DataPreview, plotPreview, api-surface) | 5 | ~43 | PASS |
| Imaging package | 1 | ~10 | PASS |

---

## Open Issues Status

All 10 claimed closing issues (#1574, #1575, #1576, #1592, #1593, #1594,
#1598, #1603, #1604, #1606) are confirmed OPEN and waiting for this PR.

Issue #1579 is implemented but not in the closing list (see M-1).

Issues #1623, #1626, #1578 are correctly open as intentional follow-ups.

---

## Action Items Before Merge

| Priority | Item | Fix |
|----------|------|-----|
| **CRITICAL** | C-1: Missing pyproject.toml entry point | Add `[project.entry-points."scistudio.previewers"]` section |
| Moderate | M-1: Issue #1579 not in closing list | Add `Closes #1579` to PR body |
| Moderate | M-2: Spec test filename mismatch | Update spec frontmatter: `test_preview_sampling.py` → `test_preview_data_access.py` |
| Low | O-1: No e2e scenario | Consider adding before or after merge |
| Low | O-2: Extra tests not in spec listing | Consider adding to spec `tests:` frontmatter |
