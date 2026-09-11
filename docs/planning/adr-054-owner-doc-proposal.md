---
title: "ADR-054 Phase A Protected Document Proposal"
status: Draft
owners: ["@jiazhenz026"]
related_adrs: [49, 52, 54, 55]
related_specs: [adr-054-panels, adr-054-miniapp]
language_source: en
---

# ADR-054 Phase A Protected Document Proposal

## 1. Change Summary

Exact proposed patches for manager/owner review under #2293. These patches are
text only: the owner-controlled files have not been edited. They retain ADR
Proposed/spec Draft status, the null acceptance date and all D-only planned
paths. Frontend surface movement is conditional on integrating A2's existing
`frontend/src/panels/**` implementation before applying the proposal. The
MiniApp spec owns shared existing surfaces without claiming its D behavior.
Artifact transport wording is conditional on integrating A2 host materialization
and SDK blob disposal, then verifying its checks; no PDF browser parity is claimed.

## 2. Proposed ADR And Spec Patch

```diff
--- a/docs/adr/ADR-054.md
+++ b/docs/adr/ADR-054.md
@@ -15,6 +15,8 @@
 is_code_implementation: true
 governs:
   modules:
+    - scistudio.panels
+    - scistudio.api.routes.panels
     - scistudio.previewers
     - scistudio.blocks.base.interactive
     - scistudio.core.dropins
@@ -25,8 +27,12 @@
     - scistudio.blocks.base.interactive.PanelManifest
     - scistudio.blocks.base.interactive.InteractiveMixin
   entry_points:
+    - scistudio.panels
     - scistudio.previewers
   files:
+    - src/scistudio/panels/**
+    - src/scistudio/api/routes/panels.py
+    - frontend/src/panels/**
     - docs/adr/ADR-054.md
     - docs/architecture/ARCHITECTURE.md
     - src/scistudio/previewers/models.py
@@ -84,16 +90,10 @@
     - docs/user/reference/**
     - docs/user/llms.txt
 planned_governs:
-  modules:
-    - scistudio.panels
-    - scistudio.api.routes.panels
+  modules: []
   contracts: []
-  entry_points:
-    - scistudio.panels
+  entry_points: []
   files:
-    - src/scistudio/panels/**
-    - src/scistudio/api/routes/panels.py
-    - frontend/src/panels/**
     - frontend/src/miniapps/**
     - src/scistudio/ai/agent/mcp/tools_panels.py
     - src/scistudio/_skills/scistudio/scistudio-write-miniapp/SKILL.md
@@ -908,9 +908,10 @@
 `src/scistudio/api/routes/data.py` and `src/scistudio/api/routes/blocks.py`, the
 interactive declaration and its registry check, the ADR-049 contract tables, the
 frontend host, loaders, built-in viewers, and modals, and the agent-facing
-material and tutorial that teach the old forms. The new surfaces — the
+material and tutorial that teach the old forms. The Phase A surfaces — the
 `scistudio.panels` package, its routes, the frontend panel host, and the
-`scistudio.panels` entry point — are listed in `planned_governs`. MiniApps add to
+`scistudio.panels` entry-point discovery — now exist and are listed in `governs`.
+This records implementation surface ownership, not completion of all phases. MiniApps add to
 both lists: the process registry, the realtime event channel, the user-library
 route, skill provisioning, the workspace layout, tab types, activity bar,
 Previewers list, New menu, canvas, tips, and promotion flow they change are in
--- a/docs/specs/adr-054-panels.md
+++ b/docs/specs/adr-054-panels.md
@@ -39,6 +39,8 @@
     - "Any change to the ADR-051 runtime, its `interactive_prompt` event, interaction memory, or the embedded agent's MCP preview tools (`src/scistudio/ai/agent/mcp/tools_inspection/_preview.py`, which read data independently of the preview service)."
 governs:
   modules:
+    - scistudio.panels
+    - scistudio.api.routes.panels
     - scistudio.previewers
     - scistudio.blocks.base.interactive
     - scistudio.blocks.registry
@@ -53,8 +55,12 @@
     - scistudio.blocks.base.interactive.PanelManifest
     - scistudio.blocks.base.interactive.InteractiveMixin
   entry_points:
+    - scistudio.panels
     - scistudio.previewers
   files:
+    - src/scistudio/panels/**
+    - src/scistudio/api/routes/panels.py
+    - frontend/src/panels/**
     - docs/specs/adr-054-panels.md
     - docs/specs/adr-048-preview-system.md
     - docs/specs/adr-051-interactive-blocks.md
@@ -105,16 +111,10 @@
     - docs/user/reference/**
     - docs/user/llms.txt
 planned_governs:
-  modules:
-    - scistudio.panels
-    - scistudio.api.routes.panels
+  modules: []
   contracts: []
-  entry_points:
-    - scistudio.panels
+  entry_points: []
   files:
-    - src/scistudio/panels/**
-    - src/scistudio/api/routes/panels.py
-    - frontend/src/panels/**
     - src/scistudio/_skills/scistudio/scistudio-write-panel/SKILL.md
     - docs/package-development/panels.md
   excludes: []
@@ -179,6 +179,28 @@
 ambiguity rule, and per-type user choice carry over. Both legacy previewer forms
 — `mount(container, host)` modules and Python-only previewers — keep working,
 deprecated, through 0.5.x.
+
+### Phase A Owner Decisions (2026-09-11)
+
+Phase A preserves the existing Previewers sidebar entry and includes panel
+candidates in that catalog. Phase D (#2354) performs the MiniApps/All Previewers
+transition. SDK sample mode (FR-046) belongs to A; it does not require an
+intermediate Panels tab, card sample-opening flow, or directory promotion.
+
+The existing ADR-055 identity and prefix seams apply now: verify the default and
+replacement fake guards at root and proxy-prefixed mounts. Fake-guard evidence
+is not real JupyterHub verification.
+
+TODO(#2294): Replace the temporary compiled windows for
+`core.interactive.data_router` and `core.interactive.pair_editor` with core-tier
+HTML panels in Phase B; remove their explicit compatibility exceptions then.
+Out of scope per the Phase A/B split; follow-up:
+https://github.com/jiazhenz026/SciStudio/issues/2294.
+Other missing ids and context mismatches remain errors.
+
+FR-002's strict `core.*` reservation and ADR-054's same-id core customization
+remain an owner-contract question under #2293; this amendment does not choose a
+new rule or claim that same-id non-core overrides work.
 
 ## 2. User Scenarios & Testing
 
@@ -603,9 +625,11 @@
   `/api/panels/t/{token}/sdk/{major}/scistudio-panel.js`, and
   `/api/panels/t/{token}/lib/{name}@{version}/{path}`, built from the configured
   base path (adr-055-prefix-independence), with the path confinement of
-  `scistudio.previewers.assets.resolve_asset`. The session middleware MUST accept a
-  valid token in place of the session cookie on these paths only; this is the
-  documented exception recorded in `docs/specs/adr-055-enterprise-support.md`.
+  `scistudio.previewers.assets.resolve_asset`. The installed ADR-055 identity
+  guard MUST delegate the literal `/api/panels/t/` subtree through
+  `register_self_authenticating_prefix`; these routes validate their own token
+  without a session cookie. Catalog, context, read, renewal and close operations
+  remain behind the installed guard. No Lab-specific middleware is added.
 - **FR-027**: Token-scoped responses MUST allow cross-origin reads
   (`Access-Control-Allow-Origin: *`, no credentials) and carry
   `Referrer-Policy: no-referrer`; their file-type allowlist MUST add `.html`,
--- a/docs/specs/adr-054-miniapp.md
+++ b/docs/specs/adr-054-miniapp.md
@@ -44,10 +44,14 @@
     - "Mechanical conversion of a MiniApp into a block (ADR-054 §11.5)."
     - "Directory promotion through the agent's `promote_to_user_library` tool, and ADR-053's canvas promotion entry on the new block context menu (tracked in #2288)."
 governs:
-  modules: []
+  modules:
+    - scistudio.panels
   contracts: []
   entry_points: []
   files:
+    - src/scistudio/panels/**
+    - src/scistudio/api/routes/panels.py
+    - frontend/src/panels/**
     - docs/specs/adr-054-miniapp.md
     - src/scistudio/engine/runners/process_handle.py
     - src/scistudio/api/ws.py
@@ -73,16 +77,12 @@
     - src/scistudio/ai/agent/mcp/__init__.py
   excludes: []
 planned_governs:
-  modules:
-    - scistudio.panels
+  modules: []
   contracts: []
   entry_points: []
   files:
-    - src/scistudio/panels/**
-    - src/scistudio/api/routes/panels.py
     - src/scistudio/ai/agent/mcp/tools_panels.py
     - src/scistudio/_skills/scistudio/scistudio-write-miniapp/SKILL.md
-    - frontend/src/panels/**
     - frontend/src/miniapps/**
   excludes: []
 tests:
--- a/docs/specs/adr-054-panels.md
+++ b/docs/specs/adr-054-panels.md
@@ -437,7 +437,8 @@
 - A plot artifact is a PDF: the browser's built-in PDF viewer does not run inside
   a sandboxed frame, so `core.plot.basic` uses the local PDF renderer.
 - An artifact is larger than the inline limit: the panel reads it through
-  `artifact.file`, a token-scoped file URL.
+  `artifact.file`: the host consumes a distinct context-target artifact grant and
+  transfers bounded bytes to the SDK; the frame uses a local blob URL.
 - The panel relies on `localStorage`, `alert`, or pop-ups: unavailable at an
   opaque origin without `allow-modals` or `allow-popups`; the SDK documents this
   and offers view state (FR-018) instead of storage.
@@ -521,7 +522,7 @@
   | `series.points` | decimated index and values, with the decimation method |
   | `text.chunk` | text, encoding, offset, next offset |
   | `artifact.info` | name, MIME type, size |
-  | `artifact.file` | a token-scoped URL for the artifact's bytes, including plot-job outputs in the preview cache |
+  | `artifact.file` | backend: a distinct context-target grant URL, including preview-cache plot artifacts; SDK: artifact metadata, an `ArrayBuffer` in `data`, and a frame-local blob URL in `url` |
   | `composite.slots` | slot names, types, and child references |
   | `collection.items` | a page of item references with types, and the next cursor |
 
@@ -611,6 +612,16 @@
   `Referrer-Policy: no-referrer`; their file-type allowlist MUST add `.html`,
   `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.ttf`, `.otf`, and `.wasm` to today's
   set. No other API route may send permissive CORS headers.
+  The static mount token MUST NOT authorize artifact data. The backend's
+  `artifact.file` result uses a separate grant bound to one context-authorized
+  target; the host validates the local grant route and consumes it with no
+  redirects, enforcing a 100 MiB limit against declared size and streamed bytes.
+  It transfers the bytes over the context's MessageChannel. The SDK creates a
+  frame-local blob URL, revokes the previous artifact URL on replacement and all
+  remaining URLs on disposal. Context close aborts host transfers and revokes
+  backend grants. The frame does not fetch the grant URL; `connect-src 'none'`
+  remains unchanged. This transfer contract does not establish Phase B PDF.js
+  rendering or companion-asset parity (#2294).
 - **FR-028**: Panel HTML responses MUST carry a Content-Security-Policy with
   `connect-src 'none'`; `script-src`, `style-src`, and `font-src` limited to the
   token-scoped path, `'unsafe-inline'`, and the CDN allowlist hosts; and
--- a/docs/adr/ADR-049.md
+++ b/docs/adr/ADR-049.md
@@ -391,6 +391,11 @@
 | PV-09-004 | 09 previewer contracts | PreviewRouter selection is deterministic and ambiguous matches are strict errors | implemented | block | block | aligned | pv-a3-sections-07-09 |
 | PV-09-005 | 09 previewer contracts | Core and imaging package PreviewerSpec declarations establish fallback and package ownership | implemented | info | info | aligned | pv-a3-sections-07-09 |
 | PV-09-006 | 09 previewer contracts | Session rendering stamps manifests and turns provider failures into error envelopes | implemented | error | error | aligned | pv-a3-sections-07-09 |
+| PV-09-007 | 09 previewer contracts | Panel descriptor schema and version are validated without running panel Python | partial | error | block | aligned | pv-a3-sections-07-09 |
+| PV-09-008 | 09 previewer contracts | Panel discovery validates four tiers and contains package failures | partial | error | block | aligned | pv-a3-sections-07-09 |
+| PV-09-009 | 09 previewer contracts | Panel and legacy candidates share preview routing | partial | error | block | aligned | pv-a3-sections-07-09 |
+| PV-09-010 | 09 previewer contracts | Interactive declarations resolve compatible panels at discovery and open | partial | error | block | aligned | pv-a3-sections-07-09 |
+| PV-09-011 | 09 previewer contracts | Panel SDK communicates over one context-bound channel | partial | error | block | aligned | pv-a3-sections-07-09 |
 | PV-10-001 | 10 preview provider behavior | Preview providers use the bounded data-access surface | implemented | error | block | aligned | pv-a4-sections-10-12 |
 | PV-10-002 | 10 preview provider behavior | Preview session invocation converts routine provider failure to typed envelopes | implemented | error | block | aligned | pv-a4-sections-10-12 |
 | PV-10-003 | 10 preview provider behavior | Preview resource reads remain session-scoped and bounded | implemented | error | block | aligned | pv-a4-sections-10-12 |
@@ -402,6 +407,9 @@
 | PV-12-002 | 12 security isolation | Preview asset serving is manifest-validated and path-confined | implemented | error | block | aligned | pv-a4-sections-10-12 |
 | PV-12-003 | 12 security isolation | Plot SVG display and export are sanitized and bounded | implemented | error | block | aligned | pv-a4-sections-10-12 |
 | PV-12-004 | 12 security isolation | Subprocess isolation exists for plot rendering; broader plugin validation isolation is unresolved | partial | warning | error | adr_planned | pv-a4-sections-10-12 |
+| PV-12-005 | 12 security isolation | Panel static token serving confines files and preserves the identity seam | partial | error | block | aligned | pv-a4-sections-10-12 |
+| PV-12-006 | 12 security isolation | Panel external references and opaque-origin isolation are checked | partial | error | block | aligned | pv-a4-sections-10-12 |
+| PV-12-007 | 12 security isolation | Panel read and decision authority belongs to the backend context | partial | error | block | aligned | pv-a4-sections-10-12 |
 | PV-13-001 | 13 cross-surface registry consistency | Block registry descriptors preserve package identity | partial | error | block | aligned | pv-a5-section-13-omissions |
 | PV-13-002 | 13 cross-surface registry consistency | Block entry-point scans are tolerant runtime discovery, not install validation | partial | error | block | aligned | pv-a5-section-13-omissions |
 | PV-13-003 | 13 cross-surface registry consistency | Type registry discovery must reconcile package types with blocks and previewers | partial | error | block | aligned | pv-a5-section-13-omissions |
@@ -410,6 +418,13 @@
 | PV-99-002 | 99 omitted or discovered contracts | Scaffold-generated package fixtures are a package contract | implemented | warning | skip | aligned | pv-a5-section-13-omissions |
 | PV-99-003 | 99 omitted or discovered contracts | Generated public symbol facts are an API/package compatibility contract | implemented | info | skip | adr_missing | pv-a5-section-13-omissions |
 | PV-99-004 | 99 omitted or discovered contracts | Registry-derived API serialization is a package-facing contract | partial | error | block | adr_missing | pv-a5-section-13-omissions |
+
+The Phase A panel rows distinguish runtime enforcement from ADR-049 candidate
+validation: `partial` records implemented discovery/host/context checks whose
+independent development and production package-validation enforcement is not
+established by this evidence table. Table-anchor validation is not an install-time
+validator run. Panel Python symbols named as evidence remain internal under
+ADR-052; the author-facing panel surface is `panel.json` and the browser SDK.
 
 ### 5.1 Section Coverage
 
```

## 3. Architecture And Follow-ups

No architecture patch is needed for this slice: A3 already added the panels
package to the placement inventory. The full architecture narrative and author
guides stay tracked in Phase C (#2295); the manager may propose that text with
its final integrated evidence. No nonexistent ADR-049 addendum is introduced.

TODO(#2293): Resolve the owner question about FR-002 core-id reservation before
claiming same-id customization of core panels. Follow-up:
https://github.com/jiazhenz026/SciStudio/issues/2293.

TODO(#2294): Complete core viewer and interactive-window migrations in Phase B.
Follow-up: https://github.com/jiazhenz026/SciStudio/issues/2294.

TODO(#2295): Land full author guides, migration material and architecture prose
in Phase C. Follow-up: https://github.com/jiazhenz026/SciStudio/issues/2295.

TODO(#2354): Implement MiniApps/All Previewers navigation, process/call runtime,
creation, promotion and conversion in Phase D. Follow-up:
https://github.com/jiazhenz026/SciStudio/issues/2354.
