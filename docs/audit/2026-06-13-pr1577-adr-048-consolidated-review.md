# PR #1577 ADR-048 Consolidated Implementation Review

**Date:** 2026-06-13 (revised)
**PR:** #1577 — `[DO NOT MERGE] ADR-048: complete preview system + AI plot tools + developer docs (SPEC 1+2+3 consolidated)`
**Branch:** `track/adr-048-spec1-preview-system` (HEAD `669ddcf3`)
**Reviewer:** Claude Opus 4.6 (audit persona)
**Scope:** Full implementation quality audit against ADR-048 and companion specs

## Executive Summary

PR #1577 consolidates all ADR-048 work across three specs (preview system,
AI plot tools, developer docs) and ten issues into one reviewable surface.

**Overall verdict: FAIL — two P1 blockers and two P2 blockers must be resolved
before merge.**

The backend preview subsystem (registry, router, session, data access, API
routes) is structurally complete. However, the plot feature has no UI entry
point (users cannot trigger or see plots), a legacy MCP tool still bypasses
the new preview subsystem entirely, there is no final-state e2e evidence for
any viewer type, and multiple cross-document claims contradict each other.

## Findings

### P1 — CRITICAL BLOCKERS

#### P1-1: Plot feature has no UI entry point — users cannot trigger or see plots

**Location:** `frontend/src/lib/api/data.ts` defines `runPlotJob()` and
`plotTargetFromRunResponse()`. No `.tsx` component calls either function.

**Evidence:**
- `git grep -n "runPlotJob" 669ddcf3 -- "*.tsx"` returns only a comment at
  `PreviewHost.tsx:285`: `// api.runPlotJob -> plotTargetFromRunResponse -> PreviewHost); the`
- `git grep -n "plotTargetFromRunResponse" 669ddcf3 -- "*.tsx"` returns zero
  results.
- Issue #1623 references a `PlotPreviewPanel` component that does not exist
  in the codebase: `git grep -rn "PlotPreviewPanel" 669ddcf3` returns only
  the issue body reference, no source file.

**Impact:** The full plot pipeline (6 MCP tools → backend runtime → artifact
registration → catalog) works, but produces output that no UI component ever
renders. The API surface is dead code from a user perspective. SPEC 2 §FR-002
requires "plot result surfaced in preview host" — this is not met.

**Required fix:** Either implement `PlotPreviewPanel` (or equivalent) that
calls `runPlotJob`/`plotTargetFromRunResponse` and feeds the result into
`PreviewHost`, or explicitly defer the UI integration as a blocking follow-up
and remove #1606 from the PR closing list.

---

#### P1-2: MCP `preview_data` tool still live — bypasses new preview subsystem

**Location:** `src/scistudio/ai/agent/mcp/tools_inspection/read.py:169–229`

**Evidence:**
- The tool is decorated with `@mcp.tool()` and fully functional.
- It reads data directly via `Path(sref.path)` with type-based dispatch
  (DataFrame, Array, Series, Text, Artifact) — completely bypassing
  `PreviewerRegistry`, `PreviewRouter`, `PreviewSession`, and
  `PreviewDataAccess`.
- Issue #1594 and the PR description claim "no compatibility adapter —
  legacy preview path deleted." The `GET /api/data/{ref}/preview` HTTP
  endpoint was indeed deleted (#1604), but this MCP tool is a parallel
  legacy path that was overlooked.
- AI agents using `preview_data` get raw file reads instead of the governed,
  session-based, bounded-data preview that ADR-048 specifies.

**Impact:** The "no compat" claim is incorrect. Any MCP client (including
SciStudio's own AI orchestrator) that calls `preview_data` silently uses
the old path, defeating preview routing, session lifecycle, security
sanitization (FR-019), and bounded data access (FR-009/FR-010).

**Required fix:** Either migrate `preview_data` to use the new preview
session API internally, or remove it and direct MCP clients to the preview
session endpoints.

---

### P2 — HIGH PRIORITY

#### P2-1: No final-state per-viewer live e2e evidence

**Problem:** There is no end-to-end test evidence proving that each viewer
type (DataFrame, Array, Series, Text, Artifact, Composite, Collection,
Plot, Error) works in the current final state of the branch.

**Evidence:**
- The June 11 smoke test (`docs/audit/2026-06-11-adr-048-smoke-tests.md`)
  explicitly states: *"the live preview panel currently fetches the legacy
  `GET /api/data/{ref}/preview` for core types"* — it tested against the
  old code path, before #1604 deleted the legacy endpoint.
- No subsequent smoke test was recorded after #1604 merged.
- No `docs/ai-developer/e2e/` scenario file covers the ADR-048 preview
  flow.

**Impact:** We have unit tests and integration tests for individual
components, but no evidence that the assembled system actually works for
any viewer type in its current state. Given that #1604 deleted the legacy
endpoint that the smoke test relied on, we cannot assume correctness.

**Required fix:** Run a live e2e session for at least DataFrame, Array,
Plot, and Artifact viewer types against the current branch HEAD, and
record the results.

---

#### P2-2: Contradictory claims across issues, CHANGELOG, spec, and code

**Problem:** Multiple documents make claims that contradict each other or
the actual code state.

**Evidence:**

1. **Issue #1623 references non-existent component:** The issue body
   describes mounting `PlotPreviewPanel` in the app shell, but no such
   component exists in the codebase. The issue is open and listed as a
   follow-up, yet #1606 (plot-artifact preview wiring, in the PR closing
   list) depends on this UI component to be user-visible.

2. **CHANGELOG says #1623 is blocked by #1592, but #1592 is fixed:**
   If #1592 (preview routing for plot artifacts) is resolved in this PR,
   the stated blocker for #1623 no longer applies, yet #1623 remains open
   without updated rationale.

3. **Spec has mixed compat/no-compat language:** The preview system spec
   (`docs/specs/adr-048-preview-system.md`) contains ~20 references to
   "compatibility" with varying guidance — some paragraphs describe a
   compatibility adapter pattern, others state "no compat shim." The
   final decision (no compat, per #1594) is not cleanly reflected
   throughout the document.

4. **#1594 "no compat" claim vs. live `preview_data` tool:** The PR
   claims all legacy preview paths are removed, but `preview_data` MCP
   tool (P1-2 above) is a fully functional legacy path.

**Impact:** Reviewers and future maintainers cannot trust the documented
state. Cross-referencing issues, spec, CHANGELOG, and code produces
contradictions at every level.

**Required fix:** Reconcile all claims: update #1623 blocker rationale,
clean up spec compat language to reflect the final #1594 decision,
clarify #1606's dependency on UI integration.

---

### MODERATE

#### M-1: Missing `scistudio.previewers` entry point in main pyproject.toml

**Location:** `pyproject.toml` between lines 115 (`scistudio.types`) and
117 (`scistudio.runners`).

**Problem:** The imaging package declares
`[project.entry-points."scistudio.previewers"]` and `PreviewerRegistry`
calls `importlib.metadata.entry_points(group="scistudio.previewers")`,
but the main `pyproject.toml` never declares this group. Package
previewers will not be discovered in pip-installed deployments.

**Workaround:** Monorepo dev mode works via `_scan_monorepo_packages()`
fallback.

**Required fix:** Add the entry point group section to `pyproject.toml`.

#### M-2: Issue #1579 implemented but not in PR closing list

**Problem:** #1579 ("make frontend_manifest a first-class session-envelope
field") is fully implemented, tested, and has a gate record, but is not
in the PR's `Closes` list.

**Required fix:** Add `Closes #1579` to the PR description.

#### M-3: Spec test file renamed without spec update

**Problem:** The preview system spec lists `test_preview_sampling.py` in
its `tests:` frontmatter. The actual file is named
`test_preview_data_access.py`.

**Required fix:** Update spec frontmatter to reference the actual filename.

---

### MINOR / OBSERVATIONS

#### O-1: Additional test files beyond spec listing

The PR includes several test files not listed in any spec's `tests:`
frontmatter (security, manifest, cache, fallback, registry). These are
bonus coverage — consider adding to spec for traceability.

#### O-2: Related open issues correctly NOT in closing list

| Issue | Title | Assessment |
|-------|-------|------------|
| #1623 | Mount PlotPreviewPanel in app shell | UX, deferred — but see P1-1 and P2-2 |
| #1626 | Explicit save-to-project flow | Deferred |
| #1578 | DRY core fallback provider | Quality cleanup, deferred |

---

## Action Items Before Merge

| Priority | ID | Item | Fix |
|----------|----|------|-----|
| **P1** | P1-1 | Plot feature has no UI entry point | Implement PlotPreviewPanel or defer #1606 |
| **P1** | P1-2 | MCP `preview_data` bypasses new subsystem | Migrate or remove `preview_data` tool |
| **P2** | P2-1 | No final-state e2e evidence | Run live e2e for each viewer type on current HEAD |
| **P2** | P2-2 | Contradictory cross-document claims | Reconcile issues, spec, CHANGELOG, code |
| Moderate | M-1 | Missing pyproject.toml entry point | Add `scistudio.previewers` entry point group |
| Moderate | M-2 | #1579 not in closing list | Add `Closes #1579` to PR body |
| Moderate | M-3 | Spec test filename mismatch | Update spec frontmatter |
