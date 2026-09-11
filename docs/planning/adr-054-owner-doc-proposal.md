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

Reviewed patches under #2293, approved by the owner and applied to the four
listed ADR/spec files. The diff below consolidates the approved patch and the owner
clarification preserving refusal of core-id overrides.
They retain ADR
Proposed/spec Draft status, the null acceptance date and all D-only planned
paths. The reviewed A2 chain now supplies the existing
`frontend/src/panels/**` implementation for this surface movement. The
MiniApp spec owns shared existing surfaces without claiming its D behavior.
Artifact transport wording matches the reviewed A2 host materialization
and SDK blob disposal implementation; no PDF browser parity is claimed.

The bootstrap patch matches A1 `acdb1376` and A2 `45e52e05` source.
The agreed wire field is `ContextResponse.bootstrap_proof`; the proof remains
backend-owned. No extra operation is added to the canonical SDK channel.

## 2. Proposed ADR And Spec Patch

```diff
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
@@ -211,7 +211,7 @@
 | The Lab deployment authenticates every request, and a sandboxed page's requests carry no login | Panel files fail to load behind JupyterHub | Load panel files through short-lived, read-only, per-mount tokens issued with the panel's context | Section 4 |
 | An interactive block can name a window that was never written to return a decision | The block pauses with no error explaining why | Each panel declares its contexts; a mismatch is refused when the block is discovered and again when the panel is opened | Section 3 |
 | Customizing a preview can mean writing a Python provider, a JavaScript module, and manifest wiring | Customization is out of reach for most users and awkward for the agent | A preview panel is one HTML page plus a short `panel.json`, with no Python of its own | Section 3, Section 5 |
-| The built-in viewers are compiled into the frontend | The view a scientist uses all day cannot be adjusted without a release | Built-in viewers and windows are rewritten as core-tier panels that a user or project can shadow | Section 6 |
+| The built-in viewers are compiled into the frontend | The view a scientist uses all day cannot be adjusted without a release | Built-in viewers and windows are rewritten as core-tier panels; a customized copy uses a new non-core id | Section 6 |
 | Custom pages need plotting, table, and 3-D libraries, and some users work offline | Pages break without network access, or every page copies its own libraries | SciStudio ships a local, versioned library set; custom panels may also use an allowlist of public CDNs | Section 6 |
 | Installed packages, user projects, and a core tutorial depend on both existing previewer forms | Removing them at once breaks real packages, user work, and teaching material | Keep both forms, deprecated, through 0.5.x and remove them in 0.6 | Section 8 |
 | A notebook view that edits and syncs a kernel variable may follow | A panel model built only for today's two contexts would need a redesign | Contexts are the extension point; sync is reserved | Section 9 |
@@ -353,7 +353,7 @@
 capability and execution mode disagree, and the ADR-049 package validator reports
 the mismatch before a package ships. Project-tier panels become known only when a
 project opens, after blocks are discovered, and a user or project panel may
-shadow any panel by id, so the host checks again when it opens a panel: a
+shadow a non-core panel by id, so the host checks again when it opens a panel: a
 shadowing panel that lacks the context it is opened in is refused with an error
 naming both panels. A block's declaration keeps its current form — a
 `PanelManifest` naming a `panel_id` with an empty `module_url`, the form the
@@ -378,9 +378,13 @@
 `allow-same-origin`. The browser gives the page an opaque origin of its own. The
 page can run its script, but it cannot read the application's document, storage,
 or cookies, and it cannot make an authenticated call to the backend or read a
-backend response. It exchanges messages with its host over a channel the host
-hands it when it opens, so neither another panel nor another page can speak to it
-as the host.
+backend response. A trusted bootstrap prepended before the panel's markup binds
+initialization to that entry document using a per-context proof and private
+bootstrap channel. The host transfers input and the canonical message port
+through that retained document channel, not the frame's current window; a
+navigation before initialization cannot redirect the input to another document.
+All panel operations then use the canonical channel, so neither another panel
+nor another page can speak to it as the host.

 The sandbox alone does not stop a page from sending requests, so three further
 controls close the direct paths to the backend. The panel's HTML is served with a
@@ -560,7 +564,11 @@
 built-in interactive windows, `DataRouterModal` and `PairEditorModal`. They are
 served by the same route, mounted in the same sandbox, and given the same
 operations as every other panel. They have no privilege a package panel lacks,
-and a user or project panel with the same id shadows one. The collection and
+while `core.*` ids remain reserved for the core tier. A customized preview copy
+uses a new non-core id and the same concrete type, selected through the routing
+ladder or the per-type user choice; it does not override the core id. A block
+using a customized interactive window names that new panel id explicitly.
+Same-id tier shadowing applies only to non-core ids. The collection and
 composite panels use `open` to show an item or slot in its own panel, as the
 compiled viewers do today. When a panel cannot be loaded, the host shows the
 failure and offers the core panel for the type; it does not fall back silently.
@@ -908,9 +916,10 @@
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
@@ -180,6 +180,30 @@
 — `mount(container, host)` modules and Python-only previewers — keep working,
 deprecated, through 0.5.x.

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
+Owner clarification preserves the existing refusal to override core ids:
+FR-002's `core.*` reservation remains strict for non-core tiers. A customized
+core preview uses a new non-core id and the same concrete type, selected through
+the routing ladder or per-type user choice. Same-id shadowing applies only to
+non-core ids; this does not expand the implementation's override behavior.
+
 ## 2. User Scenarios & Testing

 ### User Story 1 - A custom preview panel renders for its type (Priority: P1)
@@ -382,19 +406,24 @@

 ### User Story 9 - A user adjusts a built-in panel by copying it (Priority: P3)

-A user copies `core.dataframe.basic` into `<project>/panels/` and edits it.
-
-**Why this priority**: Built-ins become adjustable (ADR-054 §6) through tier
-resolution alone.
-
-**Independent Test**: Copy a core panel directory into a project, change its
-page, reload, and assert the project copy is resolved.
+A user copies `core.dataframe.basic` into `<project>/panels/lab.dataframe/`,
+changes its descriptor id to `lab.dataframe`, retains the `DataFrame` type claim,
+and edits its page.
+
+**Why this priority**: Built-ins become adjustable (ADR-054 §6) through a
+separately named panel and the existing type-routing or user-choice mechanism.
+
+**Independent Test**: Copy a core panel directory into a project under a new
+non-core id, change its page, reload, and assert the project copy resolves for
+the declared type while the original core id remains available.

 **Acceptance Scenarios**:

-1. **Given** a project panel with the id of a core panel, **When** a matching type
-   is previewed, **Then** the project panel is mounted and the Previewers list
-   shows the core panel as shadowed.
+1. **Given** a project panel with a new non-core id and the concrete type of a
+   core panel, **When** that type is previewed and resolves to the project panel,
+   **Then** the project panel is mounted and the core panel keeps its own id.
+2. **Given** a project panel that retains a `core.*` id, **When** discovery runs,
+   **Then** the descriptor is refused by FR-002.

 ### User Story 10 - The agent writes a working panel (Priority: P3)

@@ -437,7 +466,8 @@
 - A plot artifact is a PDF: the browser's built-in PDF viewer does not run inside
   a sandboxed frame, so `core.plot.basic` uses the local PDF renderer.
 - An artifact is larger than the inline limit: the panel reads it through
-  `artifact.file`, a token-scoped file URL.
+  `artifact.file`: the host consumes a distinct context-target artifact grant and
+  transfers bounded bytes to the SDK; the frame uses a local blob URL.
 - The panel relies on `localStorage`, `alert`, or pop-ups: unavailable at an
   opaque origin without `allow-modals` or `allow-popups`; the SDK documents this
   and offers view state (FR-018) instead of storage.
@@ -489,7 +519,8 @@
   ids.
 - **FR-007**: Panel ids and legacy previewer ids MUST share one namespace. At the
   same tier a panel shadows a legacy previewer with the same id and the legacy
-  previewer is reported as shadowed; across tiers the higher tier wins as today.
+  previewer is reported as shadowed; across tiers the higher tier wins for
+  non-core ids. FR-002 continues to refuse `core.*` descriptors outside core.
 - **FR-008**: When no candidate matches, routing MUST return `core.base.fallback`.

 **Phase A — contexts and reads**
@@ -521,7 +552,7 @@
   | `series.points` | decimated index and values, with the decimation method |
   | `text.chunk` | text, encoding, offset, next offset |
   | `artifact.info` | name, MIME type, size |
-  | `artifact.file` | a token-scoped URL for the artifact's bytes, including plot-job outputs in the preview cache |
+  | `artifact.file` | backend: a distinct context-target grant URL, including preview-cache plot artifacts; SDK: artifact metadata, an `ArrayBuffer` in `data`, and a frame-local blob URL in `url` |
   | `composite.slots` | slot names, types, and child references |
   | `collection.items` | a page of item references with types, and the next cursor |

@@ -543,9 +574,18 @@
 - **FR-015**: The host MUST mount every panel in an `iframe` whose `sandbox`
   attribute is exactly `allow-scripts`, whose `referrerpolicy` is `no-referrer`,
   and whose `src` is the panel's token-scoped entry URL.
-- **FR-016**: On the frame's first load the host MUST create a `MessageChannel`,
-  transfer one port to the frame in a single `init` message addressed to that
-  frame's window, and exchange every further message over that port. Messages
+- **FR-016**: Context creation MUST return an unpredictable 256-bit
+  `bootstrap_proof`, stable across renewal. The backend MUST prepend trusted
+  bootstrap code before all panel entry markup. That code creates a private
+  bootstrap `MessageChannel` and sends `{v: 1, id: "bootstrap", type: "bootstrap",
+  proof}` with exactly one port to the parent. The host MUST accept at most one
+  bootstrap from the intended iframe with the matching context proof. After the
+  first load and a valid bootstrap, the host creates the canonical
+  `MessageChannel` and transfers its `init` and one canonical port through the
+  retained bootstrap port, never through the iframe's current `contentWindow`.
+  The bootstrap forwards initialization once in its original document; a
+  replacement document cannot receive it. All subsequent operations use only
+  the canonical port. Messages
   have the form `{v: <api major>, id, type, payload}`. Panel-to-host types:
   `ready`, `read`, `writeBack`, `open`, `save`, `viewState`, `resize`,
   `reportError`. Host-to-panel types: `init` (context kind, operations and
@@ -603,20 +643,38 @@
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
   `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.ttf`, `.otf`, and `.wasm` to today's
   set. No other API route may send permissive CORS headers.
+  The static mount token MUST NOT authorize artifact data. The backend's
+  `artifact.file` result uses a separate grant bound to one context-authorized
+  target; the host validates the local grant route and consumes it with no
+  redirects, enforcing a 100 MiB limit against declared size and streamed bytes.
+  Body consumption has its own 30-second deadline after response headers.
+  It transfers the bytes over the context's MessageChannel. The SDK creates a
+  frame-local blob URL, revokes the previous artifact URL on replacement and all
+  remaining URLs on disposal. Context close aborts host transfers and revokes
+  backend grants. The frame does not fetch the grant URL; `connect-src 'none'`
+  remains unchanged. This transfer contract does not establish Phase B PDF.js
+  rendering or companion-asset parity (#2294).
 - **FR-028**: Panel HTML responses MUST carry a Content-Security-Policy with
   `connect-src 'none'`; `script-src`, `style-src`, and `font-src` limited to the
   token-scoped path, `'unsafe-inline'`, and the CDN allowlist hosts; and
   `img-src` limited to the token-scoped path, `data:`, and `blob:`.
 - **FR-029**: The host MUST dispose a panel frame, and close its context, when the
-  frame loads any document other than its panel entry.
+  frame loads any document other than its panel entry. The first load event is
+  not proof of entry identity: without FR-016's valid document-bound bootstrap,
+  the host MUST withhold input and initialization. The existing ten-second
+  readiness deadline includes a missing entry handshake. A navigation before
+  initialization destroys the original document's bootstrap port, so the new
+  document receives no input; subsequent frame loads dispose the mount.
 - **FR-030**: The backend MUST refuse `POST`, `PUT`, `PATCH`, and `DELETE`
   requests whose `Origin` header is `null`, on every route.
 - **FR-031**: The backend MUST refuse to start when `SCISTUDIO_CORS_ORIGINS`
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
```

## 3. Architecture And Follow-ups

No architecture patch is needed for this slice: A3 already added the panels
package to the placement inventory. The full architecture narrative and author
guides stay tracked in Phase C (#2295); the manager may propose that text with
its final integrated evidence. No nonexistent ADR-049 addendum is introduced.

Owner clarification preserves strict `core.*` reservation. Same-id shadowing
applies to non-core ids only; customized core previews use a new id with a
concrete type claim or explicit per-type choice. No implementation expansion.

TODO(#2294): Complete core viewer and interactive-window migrations in Phase B.
Follow-up: https://github.com/jiazhenz026/SciStudio/issues/2294.

TODO(#2295): Land full author guides, migration material and architecture prose
in Phase C. Follow-up: https://github.com/jiazhenz026/SciStudio/issues/2295.

TODO(#2354): Implement MiniApps/All Previewers navigation, process/call runtime,
creation, promotion and conversion in Phase D. Follow-up:
https://github.com/jiazhenz026/SciStudio/issues/2354.
