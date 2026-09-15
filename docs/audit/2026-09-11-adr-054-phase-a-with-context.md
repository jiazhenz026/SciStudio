---
title: "ADR-054 Phase A Integration Audit With Context"
status: Draft
owners: ["@jiazhenz026"]
related_adrs: [54, 55]
related_specs: [adr-054-panels, adr-054-miniapp, adr-055-identity-seam, adr-055-prefix-independence]
language_source: en
---

# ADR-054 Phase A Integration Audit With Context

## 1. Change Summary

Recommendation: **block Phase A readiness until the three P2 integration findings
below are fixed and the final integrated candidate has browser and CI evidence**.
No P1 security finding was established in the inspected paths. This is a
with-context audit of production candidate `cabe4981` against `7b132175`, under
#2293 and coordination #2296. Approved normative documentation commits
`f67fb637` and `bd1a052e` were also consumed; they do not change production code.
The audit modifies only this report and its unique gate ledger. No implementation
fix, test change, PR creation, or merge was performed.

## 2. Findings

### P2-1: Panel drill-down cannot cross to a legacy or compiled core viewer

Locations: `frontend/src/panels/PanelPreview.tsx:84`,
`src/scistudio/panels/contexts.py:158`, and
`frontend/src/components/DataPreview.parts/PreviewHost.tsx:532`.

`PanelPreview` implements `open(ref)` by creating another panel context. The
backend correctly uses the unified router, but then requires the selected id to
exist in `registry.panels`. A collection panel whose child has no custom panel
therefore fails with `404 unknown_panel` when the child routes to a compiled core
or legacy package previewer. This is the ordinary Phase A situation because core
panel migration is explicitly Phase B (#2294). It violates ADR-054 Section 2 and
panel FR-020/FR-039 while both renderers must coexist through 0.5.x.

Reproduction used the real `tests.panels.conftest.make_runtime` registry and
context service, replacing `lab.text`'s claims with `Collection[Text]`, registering
a two-item backend collection containing `data-a`, and opening that collection.
The child router selected `core.text.basic`. Creating the child with its parent's
`parent_context_id` returned:

```text
Parent: lab.text Child route: core.text.basic
Child create: 404 unknown_panel Panel 'core.text.basic' is not registered
```

The reverse direction also needs coverage: `PreviewHost` returns `PanelPreview`
before rendering its existing `childStack` Back button. A legacy parent that opens
a panel child consequently loses that parent navigation control by code inspection.
The existing `PanelPreview.test.tsx` mock returns panels for every child and cannot
exercise either mixed-renderer boundary.

Required correction: route authorized children through a host that can render
both envelope forms while retaining the same parent/child stack and backend
authority. Add panel-to-core, panel-to-legacy, and legacy-to-panel Back tests.

### P2-2: Maximizing a composite child loses its backend authorization

Locations: `frontend/src/panels/PanelPreview.tsx:42`,
`frontend/src/panels/types.ts:46`, `frontend/src/components/DataPreview.tsx:271`,
and `src/scistudio/panels/contexts.py:143`.

Composite children have synthetic references such as `parent#notes`, authorized
through the current parent context rather than registered in the runtime catalog.
`PanelSnapshot` retains only target, panel id, and view state, omitting the
authority needed to reopen that synthetic child. Maximize passes that snapshot
into a new root host. The new host first tries ordinary preview-session routing
without the child's resolved metadata, and a subsequent root context creation
cannot resolve the synthetic reference through `freeze_target`.

Reproduction wrote a real `CompositeStore` object with a filesystem text slot,
registered a `CompositeData` catalog parent, and used a panel claiming both
`CompositeData` and `Text`. Opening `parent#notes` with `parent_context_id` succeeded;
reopening the same ref with only the exact fields carried by `PanelSnapshot`
returned:

```text
Drilled child: kind=data_ref ref=parent#notes recorded_type=Text
Maximized child without parent authority:
403 unauthorized_ref A panel target must be a backend catalog reference
```

This breaks FR-039's frozen current target and latest view-state requirement.
Required correction: carry or clone a backend-authorized child identity into the
maximized mount, with an explicit lifecycle independent of closing its original
preview area. Do not solve this by trusting browser-supplied storage paths.
Test composite child maximize, its preserved panel/view state, and parent closure.

### P2-3: Interactive confirmation can revoke its context before delivery

Locations: `frontend/src/App.parts/InteractiveModals.tsx:84`,
`frontend/src/panels/PanelFrame.tsx:85`,
`src/scistudio/api/ws.py:307`, and
`src/scistudio/panels/contexts.py:298`.

Confirmation sends a WebSocket message and immediately clears the prompt. Clearing
it unmounts `PanelFrame`, whose cleanup independently issues HTTP DELETE for the
same context. WebSocket and HTTP requests have no cross-transport ordering
guarantee. If DELETE reaches the backend first, `claim_writeback` refuses the
otherwise valid pending-block decision because the context no longer exists.
The dialog is already dismissed and the new `panel_error` response has no frontend
handler, so the workflow remains paused without its decision UI. The frontend
may also have already saved that rejected answer as interaction memory.

Reproduction used the real `websocket_handler`, panel DELETE route, EventBus,
and existing `waiting` scheduler fixture. Delivering teardown DELETE before the
queued confirmation produced:

```text
Unmount close: 204
Delayed WS result: unknown_context
interactive_complete events: 0
```

This is a deterministic reproduction of an allowed transport ordering, not a
claim that every browser submission races. The current WS test covers completion
before teardown only. Required correction: establish acknowledged or ordered
completion before releasing its authority and dismissing the prompt; show a
recoverable error on rejection. Add a delayed-WS/fast-DELETE integration test and
ensure rejected decisions are not persisted as remembered answers. Preserve the
existing engine completion event contract (FR-022/FR-024).

## 3. Verification Evidence

The following checks ran against this audit tree with `PYTHONPATH=src` and the
existing isolated A3 environment; no editable installation was used.

| Check | Result and limits |
|---|---|
| `pytest tests/panels tests/api/test_panel_routes.py tests/api/test_panel_collection_authority.py tests/api/test_panel_interactive_ws.py tests/api/test_panel_security.py tests/previewers/test_panel_read_extensions.py --no-cov -q` | 88 tests passed. Covers descriptor/routing, token lifecycle, root/prefix default and fake guards, null-Origin refusal, assets, bounded reads and WS claims. It does not cover the three sequences above. |
| Standalone finding reproductions | All three produced the failures recorded above using repository runtime helpers and actual storage or HTTP/WS handlers. |
| Panel/API import smoke | `api.app`, `panels.contexts`, `panels.registry`, and `panels.validation` imported successfully. |
| `pytest tests/architecture/test_no_new_cycles.py tests/architecture/test_placement.py --no-cov -q` | 418 tests passed, including the existing import-cycle guard and package placement inventory. |
| Pinned library inventory | Independently recomputed SHA-256 for all 202 indexed files across the four shipped libraries; every shipped digest matched. Minified vendor source was not manually reviewed. |
| Browser / Electron | Not run by this audit. Frontend behavior conclusions identify code paths; the manager arranged independent live browser evidence. No Electron process containment or native-save success is claimed. |
| Frontend unit rerun | Not run in this audit tree because its local frontend dependency directory is absent. Existing test source was inspected; manager owns integrated frontend validation. |
| Sentrux | MCP unavailable. No Pro diagnostics claimed; repository CLI gate and architecture checks are recorded separately. |
| Report-only local gate | Tier 3 `commit_hygiene` and `full_audit` passed; local reconciliation passed. The unique audit ledger measures report changes against the consumed documentation landing, not the Phase A production diff. |

The targeted suite reports existing Starlette deprecation and duplicate diagnostics
OpenAPI operation-id warnings. Neither was treated as a new panel defect.

## 4. Contract And Scope Reconciliation

The audit read #2293, the manager checklist/enterprise matrix and dispatch,
ADR-054, both panel and MiniApp specs, ADR-055 identity/prefix contracts, slice
notes, common rules, audit persona, and gated workflow. Core ids remain reserved;
the approved documentation now consistently requires custom ids. The 30 MiB
added-file threshold has explicit owner authorization. Neither is an audit finding.

Production inspection confirms the new routes register only `/api/panels/t/`
with the identity seam, guard ordinary operations, and keep the generic reads in
synchronous FastAPI worker handlers. Asset and artifact tokens are distinct;
project/registry changes and stored-file replacement revoke contexts. The host
consumes artifact grants with redirect refusal, streamed byte limits, body
deadlines and aborts, then transfers bytes for SDK blob URLs. Entry bootstrap
precedes author markup and initialization uses the retained document channel.
Actual browser navigation containment remains the independent browser audit's
evidence obligation.

Read tests exercise direct bounded array slices and full-plane extrema; collection
tests exercise retained outputs beyond the prior eviction bound. The helper-level
passing evidence does not replace full UI traversal. Panels never dispatch Python
in preview/interactive. The two compiled interactive exceptions remain explicitly
tracked to #2294. No Phase B core migrations, Phase C full guides, or Phase D
MiniApps work was started by this audit; those phases remain paused.

The manager checklist's implementation/audit/integration rows were still pending
at inspection. The report supplies row evidence rather than modifying that shared
file. Known contract-table baseline external-package evidence is not reclassified
as a new Phase A defect. The approved documentation landing supersedes the earlier
planned-governs integration errors; final exact-candidate gate reconciliation
remains manager-owned.

## 5. CI And Readiness

`gh pr checks 2353` reported all 17 checks passing on open draft umbrella #2353;
its current remote head was `69abb6465891e092daebf9083ba926d1605316ff`. Those
checks validate the coordination PR, not implementation candidate `cabe4981`.
No final Phase A PR or implementation CI result was available to this audit.
Final pre-PR reconciliation, report integration, browser checks, issue-closing PR,
and successful implementation CI remain required under #2293/#2296.

The three findings were sent to the manager as soon as reproduced. They are
tracked here under #2293 and require implementation fixes before this audit can
recommend Phase A readiness. This report is an assessment of the named candidate,
not a claim about later fixes.
