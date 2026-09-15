---
title: "ADR-054 Phase A Frontend Implementation Notes"
status: Draft
owners: ["@jiazhenz026"]
related_adrs: [54, 55]
related_specs: [adr-054-panels, adr-054-miniapp, adr-055-prefix-independence]
language_source: en
---

# ADR-054 Phase A Frontend Implementation Notes

This is the A2 implementation record for #2293, coordinated through #2296 and
umbrella PR #2353. Phase A retains the Previewers sidebar entry; Phase D #2354
owns the MiniApps/All Previewers transition and directory promotion.

## Host And Wire Contract

`PanelFrame` creates one backend context, opaque sandbox (`allow-scripts` only),
and canonical MessageChannel per mount. The entry response begins with a trusted
bootstrap before any original markup. The host accepts only its first hello from
the intended frame with the context's unpredictable `bootstrap_proof` and one
private document-bound port. On first load the host transfers canonical init and
its canonical channel through that bootstrap port, never to `contentWindow`
(which may already refer to another document). A pre-load navigation destroys
the old document's port; the new document receives no input. A missing valid
hello waits without authority until the 10 second deadline. Subsequent loads
close all ports and revoke the context. Context creation
that resolves after disposal immediately closes its orphaned context. A 10 second
ready deadline and reported exceptions show explicit remount, core-preview or
Cancel actions. Mounted contexts renew through guarded host requests every four
minutes, before the backend's ten minute token lifetime.

Every operation uses the existing `apiFetch` auth and prefix source. Its optional
response mode preserves the same transport for binary reads. Binary headers are
`X-Panel-Dtype`, `X-Panel-Shape` and `X-Panel-Metadata`; the body becomes a
transferred ArrayBuffer. Static tokens authorize only entry/SDK/library assets,
never catalog, read, renewal or deletion operations. The bridge rejects call and
sync, restricts operations by context kind, validates JSON decisions and view
state, and bounds concurrent operations to 64. Context references are authorized
by the backend, including child navigation through `parent_context_id`.

Interactive completion retains the existing `interactive_complete` WebSocket
message and adds `context_id` outside its unchanged decision data. A new-panel
confirmation retains its dialog and context until the workflow socket returns
`panel_accepted` with matching context, workflow and block identifiers. Only
then does the host persist opted-in interaction memory and close the dialog.
A matching `panel_error` or a 30 second acknowledgement timeout offers remount;
Cancel aborts pending acknowledgement. Legacy compiled/module decisions retain
their existing behavior. Interaction memory and Cancel remain in the host. The two compiled built-in
interactive windows remain until Phase B #2294; other empty-module manifests
resolve through backend panel contexts. Legacy module loads log deprecation once
per URL. Legacy removal is tracked in #2288.

The common preview host handles routed panel envelopes as well as legacy ones.
Maximize captures the independently frozen preview session, optional resolved
panel id and latest view state alongside the target, using the existing
`preview:<ref>` dedup and transient-tab rules. The host resumes that session;
it never assumes a composite-local `#slot` is a global catalog reference.
Child navigation uses guarded `POST /api/panels/contexts/{id}/open {ref}`:
the backend authorizes reachability and returns a canonical child envelope and
independent preview session. The same PreviewHost renders a panel, retained
legacy core viewer or legacy module. Parent frames and contexts stay mounted
until Back or root disposal, so Back restores the parent's live state. A child
session survives parent-context disposal for maximize. Core fallback is an explicit reroute through
`query.core_only`; it can select the retained legacy core envelope during A.

## Artifact Mediation

`artifact.file` resolves an independently authorized grant URL on the backend.
The host validates the exact same-origin, prefix-aware artifact route and fetches
it through `apiFetch` with redirects refused. A separate 100 MiB artifact budget
checks declared size, Content-Length and actual streamed bytes; over-budget
results fail explicitly. Both artifact and numeric bodies have independent
30 second deadlines after headers. Unmount interrupts even a pending stream
read; numeric bodies also enforce the 8 MiB transport budget. The host transfers the
bytes to the SDK, which preserves metadata, adds `data` and creates its own local
Blob `url`. Images use that URL; PDF.js consumes `data` directly. Replacement and
disposal revoke Blob URLs. The frame never needs fetch or broader CSP access.

<!-- TODO(#2294): PDF.js default CMap/font/WASM factories use fetch and cannot
run under connect-src none. Phase B must provide factories or script-loaded
resources and verify full PDF parity; shipping assets alone is not that proof.
Out of scope for A per ADR-054 Phase B core.plot.basic migration.
Followup: https://github.com/jiazhenz026/SciStudio/issues/2294 -->

## Generated Bytes And Theme

Save accepts only text or bytes, defaults to a 100 MiB maximum, removes directory
components from the suggested filename, and downloads a host-created Blob to the
user's computer. It does not write a server project or interpret a remote path as
a local destination. Real Electron save-dialog behavior still needs smoke
verification on the integrated build; unit tests do not establish that behavior.

The host resolves `--ss-*` CSS values and light/dark mode and sends theme changes
over the private port. The SDK applies them on its page root. No right-column
assumption exists in PanelFrame, so main-stage tabs and AI presentation reuse it.

## SDK And Local Libraries

The dependency-free `sdk/1/scistudio-panel.js` exposes context-appropriate methods
after `await scistudio.ready()`. It receives only its first parent init on window,
then accepts replies exclusively on its transferred port. It rejects pending
promises on disposal. Direct standalone pages read adjacent `panel.sample.json`:

```json
{
  "context": "preview",
  "input": { "ref": "sample-image" },
  "reads": { "metadata": { "type_name": "Image", "complete": true } }
}
```

The reads map may also key a fixture by
`JSON.stringify({ref, op, params})` for query-specific values. Serve the folder
with a static HTTP server when the browser disallows file-URL fetches. Sample
mode never grants access to a SciStudio backend.

`lib/index.json` records package source, version, license, per-file shipped/upstream SHA-256 and
upstream tarball integrity. Vendoring verified tarball integrity before copying
assets from npm's primary registry. The repository hygiene hook normalizes text
whitespace/final newlines; the index retains upstream digests alongside the
normalized shipped digests. Binary assets remain byte-identical. Versions: Plotly 2.35.3 (the frontend lock),
D3 7.9.0, three.js 0.180.0 and PDF.js 5.4.149. Three's module and core bundles
ship together; PDF.js includes its matching worker, CMaps, standard fonts and
WASM companions. A superseded version remains served for at least one minor
release after its replacement ships. These are genuine upstream distributions;
no placeholder or reconstructed bundles are used.

## Verification And Integrated Smoke

Targeted frontend tests cover port isolation, unsupported operations, transferred
buffers, one-shot decisions, JSON validation, disposal races, exact sandbox,
wrong-window SDK init, navigation/error/remount, ready timeout, root/prefixed
requests, sample mode, theme changes and save limits. Gate results are recorded
in `.workflow/records/2293-panel-frontend.json`. The frontend gate at source
commit `46aa309b`, consuming the generated bootstrap schema, passes 208 test
files / 2296 tests, TypeScript, ESLint (zero errors) and the production build.
The independent A2 full local run passes architecture, commit hygiene, tracked
deferrals, Python formatting/lint/imports and types. Its Python suite records
7784 passes, 82 skips and eight expected failures; the one failing OpenAPI
snapshot comparison requires the A1 backend implementation in the integrated
branch. Full-audit findings are the planned-to-governs promotions owned by the
contract-docs slice. These local results do not establish integrated readiness.

Integrated smoke still required by manager: install a preview fixture and an
interactive fixture; open data in ordinary and AI presentation, change view state,
maximize, drill down and Back; verify interactive response/memory/cancel; navigate
the frame or throw and verify explicit recovery. In a real browser, verify both
a normal entry and an entry that calls `location.replace` before its first load:
the replacement document must receive neither input nor a canonical port. Use
the deployed proxy prefix;
load all local libraries offline; export bytes on browser and supported Electron
and observe an explicit user destination choice. Run the combined gate and CI.

## Vendored Asset Size Evidence

The original 1000 KiB added-file check was reproduced with an independent
temporary git directory/index anchored to origin/main. It refused Plotly
(4452 KiB) and the PDF worker (1015 KiB); the actual working HEAD/index were
unchanged. The same staged-addition reproduction passes with the subsequently
authorized 30720 KiB configuration. Owner subsequently authorized a global 30 MiB threshold, committed
by manager as 9ae3a0e2. Final integration must use that authorized configuration;
this branch does not alter hooks or exclude files.

## Audit Follow-up Verification

The child-session and acknowledgement regression tests cover panel/legacy
children, multiple Back levels, legacy-to-panel Back, independent composite-slot
maximize, delayed acknowledgement without premature DELETE or memory writes,
rejection/remount, identity mismatch, timeout and cancellation. At `72b38d91`
all these tests passed in two complete frontend runs. The runs exposed two
existing timing failures elsewhere: ESLint configuration loading exceeded its
unchanged 5 second deadline once, and OpenAsDialog's immediate preselection
assertion raced its existing selection effect once.

The OpenAsDialog component and test were byte-identical to origin/main
`7b132175`. Two unchanged-main baseline runs both passed its preselection test
and all 2255 tests; one complete pipeline passed and the other reported an
unhandled teardown import in PreviewHost.dynamic.test. Baseline gate evidence is
committed as `76e8f5d0` on `codex/2293-panel-baseline`. Per manager's #2293 audit
follow-up, the only stabilization waits for the same visible checked radio via
the existing `waitFor`; production behavior and timeout thresholds are unchanged.
