---
spec_id: adr-055-ai-host-presentation
feature_branch: guided/adr055-ai-layout
created: 2026-09-11
input: "Owner requests a permanent two-presentation UI and local browser review, with explicit URLs and directional sidebar adaptation."
title: "ADR-055 AI-host presentation"
status: Draft
owners:
  - "@jiazhenz026"
related_adrs:
  - 55
related_specs:
  - adr-055-local-background-runtime
  - adr-055-webmcp-bridge
scope:
  in:
    - URL-based presentation and toolbar switching
    - Sidebar placement, preview navigation, directional overlays and responsive controls
    - External-AI launch URL and preserved terminal lifecycle
  out:
    - Demo-specific hosting and tutorial behavior
    - Backend and plugin contracts
    - Release and PR submission before owner visual review
governs:
  modules: []
  contracts: []
  entry_points: []
  files:
    - frontend/src/lib/presentation.ts
    - frontend/src/components/PresentationToggle.tsx
    - frontend/src/App.parts/ProjectWorkspace.tsx
    - frontend/src/App.parts/usePresentationNavigation.ts
    - frontend/src/components/ActivityBar.tsx
    - frontend/src/components/palette/hoverPopover.ts
    - frontend/src/components/palette/DetailPopover.tsx
    - frontend/src/components/BottomPanel.tsx
    - frontend/src/components/Toolbar.tsx
    - desktop/background-mode.js
  excludes: []
planned_governs:
  modules: []
  contracts: []
  entry_points: []
  files: []
  excludes: []
tests:
  - frontend/src/lib/presentation.test.ts
  - frontend/src/components/PresentationToggle.test.tsx
  - frontend/src/components/BottomPanel.presentation.test.tsx
  - frontend/src/components/palette/__tests__/useHoverPopover.test.tsx
  - desktop/test/background-mode.test.js
acceptance_source: adr
language_source: en
---

# ADR-055 AI-host presentation

## 1. Change Summary

Owner-directed local review implementation from remote main, September 11, 2026.
The full workbench is shared by Electron and ordinary browsers. AI-host mode
uses the same canvas, editors, project operations, and preview contracts with a
right sidebar and no AI Chat entry. The demo supplies layout reference only.

## 2. User Scenarios And Requirements

- `?ui=ai` opens AI presentation. Missing, unknown, or `workbench` values open
  the full workbench. No user-agent sniffing or WebMCP capability detection
  changes this selection.
- In browsers, a toolbar button at the far right is available before and after opening a project. It uses a bidirectional switch icon. Switching
  updates the current URL in place, preserves other query parameters, hash,
  history state and service prefix, and survives reload through that URL.
- The external-AI launcher's copyable address includes `?ui=ai`. The desktop
  launch continues to use the default full workbench.
- The AI workspace places the library sidebar and icon rail on the right.
  A dedicated Preview card reuses DataPreview. Previewers retains its catalogue.
  The separate preview column exists only in the full workbench.
- Entering AI mode, selecting a node, or publishing a plot target reveals Preview.
  Switching to another card remains possible until the preview target changes.
- Config, Logs, Terminal, Plots, History, and Git remain available. The bottom
  tab strip scrolls horizontally when space is limited.
- Direct AI entry does not mount AI Chat. Switching away from a workbench with
  mounted chat sessions keeps those sessions mounted and hidden, so layout
  changes do not terminate a running PTY. A stale AI tab selection displays Config.
- Layout changes preserve the main canvas/editor mount and unsaved file state.
  Presentation is not persisted to shared localStorage or stored on the backend.
- Existing WebMCP registration remains independent of presentation. Selecting
  AI layout does not grant permissions or certify host capability.
- In AI presentation, the AI Agent block (`ai.agent`, implemented by AIBlock)
  carries a visible "Use Workbench" caption. Its palette/canvas hover details
  and selected-node Config explain that it starts a local agent in AI Chat,
  whose terminal, prompts and permission requests are hidden in AI layout.
  Users are directed to Workbench for this interaction; the current external
  AI host does not execute the block. This notice also covers imported and
  existing nodes, including while the schema is loading. It disappears in
  Workbench and Electron. See #2324.
  This is presentation guidance: nodes remain editable and backend execution
  is unchanged. A URL layout choice does not prove that PTY execution is absent.

## 3. Implementation Plan

Use a URL-backed external-store hook for presentation, a shared toolbar toggle,
and presentation-aware workspace composition. Keep stable workspace panel IDs
and reuse the existing PreviewHost/DataPreview and bottom panel components.
This local iteration is for owner visual review; release/PR readiness requires
normal gate reconciliation and CI after the owner settles the reviewed design.

## 4. Verification

Cover URL defaults, prefix/query/hash preservation, browser history, mode
subscriptions, separate Preview and Previewers, absent AI Chat initialization,
and preservation of existing terminal mounts. Inspect actual browser layouts
at narrow and wide viewports, exercise switching and resize handles, select a
node, open Previewers, and refresh an explicit AI URL. Verify the launch-address
helper includes AI presentation. Record local evidence separately from CI.
Verify the AI Block notice in the palette, shared hover details and existing-node
Config; switching presentation updates it, and other AI-category blocks are not
incorrectly labelled as using the local agent terminal.

## 5. Boundaries

Backend execution, project contracts, plugin registration, and WebMCP transport
are unchanged. Demo badges, tutorial placeholders, hosting, and temporary
implementations are not imported. This change does not claim verification of
any named AI host's WebMCP or authentication support.


## 6. Demo Adaptation Review

The reviewed demo is commit cf0fe7699a6ab4ed29d850c87b8040ae81fc3670.
Adopted product interactions: right sidebar, left-facing rail tooltips and
hover details, collision-aware popovers, wider usable sidebar, node/plot preview
reveal, and responsive toolbar/tab-strip access. Panels use real keyed child
ordering, so dragging and keyboard resizing agree with the visual order.
Popover placement prefers the side facing the stage and flips/clamps when the
viewport is too small; stale anchors close on scroll, resize, or layout change.

Demo removal of Import, Reload, Packages, Bring in my work, Terminal, AIBlock,
and AppBlock is excluded: these are capability/product changes, not layout.
The demo's file-browser restriction, Save picker changes, and multi-file handling
are separate file-operation behavior; existing file contracts remain in force.
Demo tutorial rewrites, starter notes, badges, container paths and hosting are
excluded. The Preview card is distinct from the retained Previewers catalogue.

Electron is identified by the existing preload bridge and always uses the full
workbench. It has no presentation switch and ignores `ui=ai`; programmatic
presentation changes are also ignored in the desktop shell.

During the owner-guided #2354 session, desktop first-open sidebar sizing was
corrected: a sidebar mounted collapsed opens at 280px, with a 240px readable
minimum, instead of expanding to the resizer's 10% fallback. AI presentation
retains its 28% preferred width and 180px minimum. Each presentation remembers
manual sizing separately during the workspace session; collapse/reopen restores
that size rather than the other presentation's width.
