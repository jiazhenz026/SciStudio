# Audit: ADR-054 Panels (no-context)

- Date: 2026-09-11
- Persona: `audit_reviewer`, **no-context** mode
- Branch / worktree: `audit/2285-adr054-no-context` @
  `C:/Users/jiazh/workspace/SciStudio/.worktrees/audit-2285-adr054-nc`
- Base commit audited: `de4010850b39d7817c3abff41581f3da969f431d`
- Document under audit: `docs/adr/ADR-054.md` (status `Proposed`,
  `phase: planning`)
- Judged against: ADR-017, ADR-038, ADR-041, ADR-043, ADR-048, ADR-049,
  ADR-051, ADR-051 Addendum 1, ADR-052, ADR-053, ADR-055,
  `docs/specs/adr-048-preview-system.md`,
  `docs/specs/adr-051-interactive-blocks.md`,
  `docs/architecture/ARCHITECTURE.md`, `docs/package-development/previewers.md`,
  the code under `src/scistudio/previewers/**`, `src/scistudio/blocks/**`,
  `src/scistudio/api/**`, `src/scistudio/engine/scheduler/**`, the frontend
  preview and interactive hosts, `desktop/`, and read-only clones of
  `scistudio-blocks-imaging` (`71594a33`), `scistudio-blocks-spectroscopy`
  (`8d178e9a`), and `scistudio-package-lcms` (`a7ab21dc`).

## 1. Change Summary

This report is the only file this change adds. It contains a no-context audit
of ADR-054, which proposes replacing ADR-048's frontend previewer modules and
ADR-051's interactive windows with **panels**: sandboxed HTML pages that talk
only to their host, receive a context (`preview` or `interactive`), and read
data through the core bounded read layer.

Line numbers such as `L248` refer to `docs/adr/ADR-054.md` at the audited
commit. Where a location is written `file:line`, the file is in this repository
unless it is prefixed with a package clone name.

**Recommendation: pass-with-fixes.** The direction is internally coherent, and
the frontmatter validates (`frontmatter_lint`: pass, 0 findings). But five
high-severity findings concern the ADR's central claims:

- the isolation boundary is described more strongly than the chosen sandbox
  provides (H1);
- the Lab-deployment claim that underpins rejecting a separate panel origin is
  unsupported and likely false as written (H2);
- a whole class of existing previewers has no migration path (H3);
- `panel.json` cannot express the routing ladder the ADR says carries over
  unchanged (H4);
- the three-operation model omits child routing, which two of the nine
  built-ins depend on (H5).

All five are fixable by revising the text. H2 may reopen the §4 alternatives
analysis. There are no block-level findings: nothing here breaks current code,
because ADR-054 is documentation-only.

Counts: 0 block, 5 high, 11 medium, 9 low, 5 info.

`gate_record check --mode pre-pr` is **N/A** for this dispatch. Per the
dispatch, no gate ledger is created here, and this report travels into the
ADR's own PR, whose ledger covers it. Sentrux: N/A (documentation-only audit).

## 2. Findings

Each finding is labelled as one of two kinds:

- **Contradiction / false claim**: the document says something the cited
  source contradicts.
- **Design weakness / open question**: the document is incomplete or
  ambiguous.

### 2.1 High

#### H1 — The isolation boundary is overstated: a sandboxed panel can reach the network and can send requests to the backend (contradiction / false claim)

- **Where:**
  - §1.1 row 2 (L145): "a sandboxed frame that can reach nothing but its host".
  - §4 L248-252: "it cannot call the backend API. The only thing it can do is
    exchange messages with the host".
  - §4 L257-258: "the operations the host provides are the only reach the
    panel has".
  - §12 L475-477 (verification: "a page's direct attempt to call the backend
    fails").
  - §13 L492-493: "a faulty page can no longer reach the application".
- **What is wrong:**
  - `sandbox="allow-scripts"` without `allow-same-origin` gives the page an
    opaque origin. It does not restrict network access. The page can still
    `fetch()`, load images and scripts, and send beacons to any host.
  - §6 (L378-381) explicitly lets custom panels load scripts from a public CDN,
    so the ADR itself depends on the frame reaching the network. That
    contradicts §1.1 and §4 inside the same document.
  - A panel that is handed data through `read` can therefore send it anywhere.
- **Backend reachability, evidence from the code:**
  - The opaque origin only stops the page *reading* API responses, and only
    while the CORS allowlist excludes `null`. The default list is at
    `src/scistudio/api/app.py:250-255`.
  - With `SCISTUDIO_CORS_ORIGINS="*"` (`src/scistudio/api/app.py:245-246`,
    tested in `tests/api/test_app.py:143-144`), every API response becomes
    readable by any sandboxed panel.
  - A CORS-simple request is sent and executed even when its response cannot
    be read: no preflight, `mode: "no-cors"`, no body or a `text/plain` body.
    Two state-changing routes take no request body at all:
    - `POST /api/blocks/reload` (`src/scistudio/api/routes/blocks.py:312-313`);
    - `POST /api/previews/reload` (`src/scistudio/api/routes/data.py:506-507`).
    Local mode has no authentication.
  - The §12 check as worded ("attempt to call the backend fails") would pass
    against response-unreadability alone and miss request execution.
  - ADR-055 §7 (ADR-055 L295-297) already says "loopback deployment does not
    justify arbitrary cross-origin calls".
- **Suggested fix:**
  - State the boundary precisely: the SciStudio API is reachable only through
    the host for reads.
  - Add a Content-Security-Policy that the asset route serves on the panel
    document (for example `connect-src 'none'`, with `script-src` limited to
    the local library route plus an explicit CDN host allowlist).
  - Require the backend to refuse state-changing requests whose `Origin` is
    `null`, or to require a non-simple header or token.
  - Forbid `*` and `null` in `SCISTUDIO_CORS_ORIGINS` while panels are enabled.
  - Reword §12 to "a page cannot read or change backend state directly".
  - Reconcile §1.1 and §4 with §6's CDN permission.

#### H2 — Lab deployment: opaque-origin subresource requests carry no Hub credentials, so "no deployment needs a second address" is unsupported (design weakness)

- **Where:**
  - §4 L277-282 ("panels behave identically ... behind JupyterHub's path-based
    routing in the Lab deployment of ADR-055 §8. No deployment needs a second
    address").
  - §4 L288-291 and §14 L516-518: a separate origin is rejected because the
    backend "would need a scoped-token authorization layer".
  - §6 L375-376: the library set is served "at fixed URLs that carry their
    version".
- **What is weak:**
  - ADR-055 §8 (ADR-055 L310-313) requires Hub authentication on "the UI,
    APIs, WebSocket connections, WebMCP bridge, and transfer endpoints". It
    also requires verifying "API/asset/WebSocket URLs" under the proxy
    (ADR-055 L334-338).
  - Inside a document with an opaque origin, module scripts and `fetch()`
    requests use CORS mode with credentials mode `same-origin`. No URL is
    same-origin with an opaque origin, so the Hub session cookie is not
    attached.
  - The panel's own `<script type="module">`, its fetches, and its library
    loads from the asset route would therefore reach the Hub proxy
    unauthenticated.
  - Classic no-cors subresources are also at risk under SameSite rules, because
    the initiator is opaque.
  - ADR-054 notes only the CORS side (§4 L302-305), not credentials.
  - Separately, root-relative "fixed URLs" for the library set do not carry the
    per-user Hub prefix. ADR-055 §9.2 (ADR-055 L383) records exactly this
    defect ("root-relative fetch URLs do not encode Hub service prefixes").
- **Why it matters:** The plausible fixes each have a cost the ADR does not
  weigh:
  - the host fetches assets and injects them via `srcdoc` or `blob:` URLs,
    which changes the loading model;
  - per-mount capability tokens in asset URLs reintroduce the scoped-token
    layer the ADR cited to reject a separate origin;
  - exempting the asset route from Hub auth conflicts with ADR-055 §8.
- **Suggested fix:** Decide the asset-loading and authentication mechanism in
  the ADR. Re-weigh the separate-origin alternative against it. Add a Lab row
  to §12: a panel with module scripts and library imports loads through the
  Hub proxy under a user prefix.

#### H3 — Python-provider previewers rendered by core viewers have no migration path; §6 and §8 conflict (contradiction / design weakness)

- **Where:**
  - §6 L367-368: "The frontend keeps no mapping from a preview kind to a
    compiled component".
  - §8 L406-414: the compatibility path covers only "an ES module that
    exports `mount(container, host)`".
  - §2 L170: the preview context receives "a reference to one typed data
    object".
- **What is wrong:**
  - A third existing previewer form is neither kept nor retired. It is a
    Python provider with no frontend module, whose `PreviewEnvelope` is drawn
    by a compiled core viewer chosen by `EnvelopeKind`.
  - Evidence (the core tutorial):
    - The tutorial writes `previewers/image_preview.py` into user projects
      (`src/scistudio/tutorials/core/what-is-a-type/tutorial.yaml:362-366`) and
      promotes it to the user library (`tutorial.yaml:722-730`).
    - That file declares no `frontend_manifest` and returns
      `EnvelopeKind.PLOT` with a PNG `src`
      (`.../assets/code/image_preview.py:195-257`).
    - `frontend_manifest` is optional on `PreviewerSpec`
      (`src/scistudio/previewers/models.py:370`).
  - Evidence (the packages):
    - The imaging package's documented fallback design depends on this path:
      its envelope uses `kind=ARRAY` "so a failed packaged-JS load degrades to
      the core Array viewer" (`scistudio-blocks-imaging/.../previewers/providers.py:24-28`).
  - Consequence:
    - Once the built-ins become panels that read typed objects rather than
      render envelopes, these previewers have nothing to render them. They
      break at the built-in rewrite, not at the 0.6 removal. §8's promise that
      the old contract "keeps working ... through the 0.5 line" does not hold
      for them.
    - ADR-048 §8 (ADR-048 L399-400) requires previewer load failures to
      "degrade to diagnostics or a core fallback". ADR-054 does not say what a
      panel load failure falls back to.
- **Suggested fix:**
  - Either keep an envelope-rendering path in the core panels until 0.6 and
    say which panel renders which `EnvelopeKind`, or sequence the built-in
    rewrite after the removal.
  - Add Python-only previewers to §8's inventory, deprecation warning, and
    §13's migration cost.
  - Specify panel load-failure fallback: the next ladder candidate, or the
    core panel.

#### H4 — `panel.json` cannot express the routing ladder the ADR says carries over "as they are" (contradiction / false claim)

- **Where:**
  - §3 L227-230: "`types` is exactly the information the previewer routing
    ladder needs, so there is no separate previewer declaration".
  - §7 L401-402: "ADR-048's routing ladder, its ambiguity rule, ... carry over
    to panels as they are".
  - The manifest as specified has only `id`, `contexts`, and `types` (L202,
    L211-215).
- **Evidence:**
  - The ladder routes on more than the type:
    - `supports_collection`: exact `Collection[T]` and exact `T` are separate
      rungs (ADR-048 §3, ADR-048 L171-176). The router filters every bucket on
      it (`src/scistudio/previewers/router.py:220-227`). It deliberately never
      hands a collection to a single-item previewer (`router.py:91-96`,
      `router.py:177-179`).
    - `priority` decides within a tier (ADR-048 L184-186;
      `router.py:260-264`).
    - Sentinel target types `Collection` and `DataObject` implement the core
      catch-alls (`router.py:238-241`). The base fallback also relies on
      `priority=-100` (`src/scistudio/previewers/fallbacks.py:670`).
  - Real packages depend on priority:
    - imaging and spectroscopy use `priority=100`
      (`scistudio-blocks-imaging/.../previewers/__init__.py:103,114`;
      `scistudio-blocks-spectroscopy/.../previewers/__init__.py:63,75`);
    - the package guide teaches it (`docs/package-development/previewers.md:105-106`).
  - ADR-049 §3.5 checks that "priority and collection support are
    deterministic" (ADR-049 L257).
- **Consequences:**
  - No panel can claim `Collection[T]`.
  - Every same-tier pair of panels on a type becomes a hard ambiguity error.
  - The core fallback rungs cannot be expressed.
- **Suggested fix:** Add collection support and priority to `panel.json`, or
  state that they are dropped and what replaces them. Also say how the
  `Collection` and `DataObject` fallbacks are declared.

#### H5 — The three operations cannot express child routing, which the composite and collection built-ins depend on (design weakness)

- **Where:**
  - §2 L155-157: "a panel never needs more than three operations".
  - §2 L170: the preview context is "a reference to one typed data object".
  - §6 L359-364: all nine built-ins become panels with the same three
    operations.
- **Evidence:**
  - `core.composite.basic` and `core.collection.basic` declare `child_routing`
    (`src/scistudio/previewers/fallbacks.py:645,654`).
  - Their viewers open a slot or item as its own preview
    (`frontend/src/components/DataPreview.parts/coreViewers.tsx:705-742,748-809`;
    the host callback is at `coreViewers.tsx:847-848`).
  - ARCHITECTURE.md §9.6 describes them as "Slot list where each slot exposes
    its own previewable value" and "Entry list where each item opens its own
    preview" (ARCHITECTURE.md L1763-1764).
  - ADR-048 §6 gives `CompositePreviewer` "child preview routing"
    (ADR-048 L331).
  - Reading a slot's values is not the same as routing it. An `Image` slot
    should open in the imaging panel the ladder picks. That needs a host
    operation ("open child target") or nested panel frames, and neither is in
    the model.
  - The preview context for a `Collection` target (which ADR-048 routes
    explicitly) is not "one typed data object", and ADR-054 does not define
    it.
- **Suggested fix:** Add a host-mediated "open target" housekeeping operation,
  or define nested panel mounting. Define what the preview context hands a
  collection panel: item references, count, and a paging cursor.

### 2.2 Medium

#### M1 — "ADR-048 §7 already defines those reads and `PreviewDataAccess` implements them" is overstated (false claim)

- **Where:**
  - §5 L314-318: "pages of a table, planes and tiles of an array, decimated
    series, chunks of text, the slots of composite data, and the items of a
    collection".
  - §4 L268-270: binary data "transferred as `ArrayBuffer`".
- **Evidence** (all in `src/scistudio/previewers/data_access.py`):
  - **Series are not decimated or bounded.** `series_points` "Return[s] the
    complete set of chart points" and reads the whole Parquet file, always
    reporting `truncated=False` (`data_access.py:620-696`). ADR-048 §7 requires
    decimation "such as min/max bins or LTTB" (ADR-048 L378).
  - **Text has only a head chunk.** `text_chunk(ref)` takes no offset and reads
    the first `text_chars` bytes (`data_access.py:710-734`).
  - **Collections expose only the first `max_items` (100) items**, with no
    cursor (`data_access.py:835-862`). ADR-048 L382 asks for "bounded
    iteration".
  - **Artifacts have no bounded byte read.** Only metadata is returned, plus an
    inline data URI for PNG, JPEG, SVG, or PDF files at or under `max_bytes`
    (8 MiB) (`data_access.py:739-767`). A larger artifact cannot be read at all.
  - **Tiles are JSON float lists, not binary**
    (`np.asarray(tile, dtype=float).tolist()`, `data_access.py:614`).
- **No generic read route exists.** Reads reach the frontend only through
  provider envelopes and `GET /api/previews/sessions/{id}/resources/{resource_id}`,
  which are dispatched to provider code (`src/scistudio/api/routes/data.py:694-750`).
  With no providers (§5), a new generic read API must be built, and it becomes
  the SDK's public read contract.
- **Suggested fix:** List the read-layer extensions the decision requires
  (series decimation, text paging, collection cursor, artifact byte ranges, a
  binary transport, a generic read route) and put them in `planned_governs`
  (see M9).

#### M2 — Allowing CDN scripts reverses decisions in ADR-048, its spec, and ADR-049 without saying so (contradiction)

- **Where:**
  - §6 L378-384: custom panels "may also reference a public CDN".
  - §1 L132-133: ADR-054 "replaces [ADR-048's] frontend module contract".
  - §1 L136-137: "ADR-049 gains the panel checks".
- **Evidence:**
  - ADR-048 §4: "Remote CDN imports and arbitrary external URLs are not part of
    the contract" (ADR-048 L210-212).
  - ADR-048 §8: "frontend modules must load only from validated same-origin
    manifests" (ADR-048 L398).
  - ADR-048 §13 rejected "Load previewer JavaScript from arbitrary URLs — Too
    hard to audit" (ADR-048 L516).
  - The ADR-048 spec puts "Loading remote third-party JavaScript from arbitrary
    URLs" out of scope (`docs/specs/adr-048-preview-system.md:32`) and makes
    same-origin loading FR-022 (spec L304-305).
  - ADR-049 §3.5 requires same-origin manifest URLs and says "remote frontend
    assets ... are rejected" (ADR-049 L258, L261). Contract PV-12-001 is
    blocking (ADR-049 L401).
  - The code enforces this (`src/scistudio/previewers/assets.py:32,63-66`).
  - ADR-051 §8 relies on "ADR-048's validated same-origin serving"
    (ADR-051 L341-343).
- **What is missing:** ADR-054 neither names the reversal nor answers
  ADR-048's auditability objection. "Gains the panel checks" also hides the
  removal of a blocking ADR-049 check.
- **Suggested fix:**
  - State the reversal explicitly.
  - Answer the auditability objection, for example with a CDN host allowlist,
    subresource-integrity hashes, or the CSP in H1.
  - Specify which ADR-049 rows change.
  - Add "same-origin only" to §14 as a considered alternative.

#### M3 — "The block's inputs by reference" conflicts with the ADR-051 sections ADR-054 says it keeps unchanged (contradiction)

- **Where:**
  - §2 L171: the interactive context is given "the block's inputs by
    reference".
  - §7 L393-397: "ADR-051 §3 is unchanged ... while the block is paused the
    panel reads only through the core read layer".
  - §1 L134: ADR-054 "keeps ADR-051's interaction capability".
- **Evidence:**
  - ADR-051 §2 (kept): the view is "sized for a window rather than for the full
    dataset ... Reducing the data to something a person can look at is part of
    the block's job, because only the block knows which reduction is
    meaningful" (ADR-051 L168-173). `InteractivePrompt.panel_payload` says the
    same (`src/scistudio/blocks/base/interactive.py:166-172`).
  - ADR-051 §3 (declared unchanged): "the view goes to the browser, the
    references stay between the engine and the block — so heavy data is never
    pushed through the browser" (ADR-051 L226-230).
  - The spec's FR-010 says intermediate references "MUST NOT be sent to the
    browser" (`docs/specs/adr-051-interactive-blocks.md:234-236`). ADR-054 does
    not say whether "inputs by reference" excludes
    `InteractivePrompt.intermediate`.
- **The runtime cannot deliver input references today.** `INTERACTIVE_PROMPT`
  carries only `panel_manifest`, `panel_payload`, and `input_signature`
  (`src/scistudio/engine/scheduler/_dispatch.py:546-556`). The frontend prompt
  type has no references (`frontend/src/store/types.ts:278-297`). The
  scheduler event and the frontend type must change, yet the ADR calls
  ADR-051 §3 unchanged and does not govern the scheduler.
- **Suggested fix:** Either declare the ADR-051 amendment (§2's reduction
  responsibility, §3's browser rule, the prompt event payload) or drop "inputs
  by reference" from the interactive context. In either case:
  - exclude intermediate references explicitly;
  - say which references a panel may read.

#### M4 — The discovery-time `contexts` check is defeated by shadowing, and the hang is only partly removed (design weakness)

- **Where:**
  - §3 L218-234: a block naming a panel without `interactive` "is refused when
    the block is discovered"; this "turns that silent hang into a load-time
    error".
  - §6 L366-367: "a user or project panel with the same id shadows one".
- **What is weak:**
  - Project-tier panels become known only when a project opens, as previewer
    drop-ins do today (`src/scistudio/previewers/project.py:81-106`). That is
    after blocks are discovered.
  - A user or project panel that reuses an interactive panel's id with only
    `contexts: ["preview"]` passes the discovery check, and the block then
    opens it.
  - A panel that declares `interactive` but never writes back still leaves the
    block paused until Cancel (the host-drawn Cancel is at
    `frontend/src/App.parts/InteractiveModals.parts/DynamicPanel.tsx:14-24,230-233`).
    The claim in L223 is narrower than stated.
  - With `PanelManifest` retired (§13 L507-509), the type of
    `InteractiveMixin.interactive_panel` is unspecified. Today it is
    `ClassVar[PanelManifest]` (`interactive.py:208`), and the registry
    validates it (`src/scistudio/blocks/registry/_capability.py:285-330`).
- **Suggested fix:**
  - Re-check `contexts` at resolution or open time as well as at discovery.
  - Say whether shadowing applies to interactive panels.
  - Define the new `interactive_panel` declaration.

#### M5 — "A page that renders itself into a stall stays inside a frame" depends on process isolation that the sandbox does not guarantee (false claim / unverified)

- **Where:**
  - §4 L259-262.
  - §1.1 row 2 (L145), whose risk is "freeze the application".
- **What is weak:**
  - An infinite loop in a frame freezes the host page when the browser runs
    the frame in the host's renderer process.
  - Running a sandboxed opaque-origin frame out-of-process is a
    browser-specific site-isolation policy, not a property of the `sandbox`
    attribute.
  - The desktop pins Electron 42.2.0 (`desktop/package.json:28`), and ADR-055
    deployments use whatever browser the scientist has (ADR-055 §2). No
    evidence is given.
- **Suggested fix:** Verify out-of-process placement of sandboxed frames on the
  supported Electron and browsers and cite it, or narrow the claim to thrown
  exceptions and leaked handlers. Add a §12 row for the stall case.

#### M6 — Save and export are a write channel outside "the whole permission model" (contradiction / design weakness)

- **Where:**
  - §2 L174-178: the context table "is the whole permission model", and
    preview has "no write back".
  - §4 L273-275: housekeeping includes "asking the host to save a file through
    its native dialog".
- **Evidence:**
  - Today, save writes a server-generated, session-scoped provider resource to
    a user-chosen absolute path (`src/scistudio/api/routes/data.py:752-782`;
    `frontend/src/components/DataPreview.parts/previewerHostApi.ts:170-176`).
  - ADR-048 §5 also allows export to a "project artifact location"
    (ADR-048 L316-317).
- **Why it matters:**
  - Panels have no provider (§5), so a save must carry bytes the panel made,
    for example a canvas-rendered PNG.
  - That is a new backend write path, available in every context including
    preview.
- **Suggested fix:**
  - List save and export as a context-provided operation in the §2 table.
  - State their limits: user dialog required, size cap, and whether a project
    path is a permitted target.

#### M7 — What a panel may `read` in each context, and how host messages are authenticated, are unspecified (security gap)

- **Where:**
  - §2 L165-166 ("The thing that opened it ... decides what the panel is
    given").
  - §4 L264-275.
- **What is weak:**
  - The ADR never says the host restricts `read` to the target(s) the context
    references.
  - Today, reads are session-scoped to one resolved target: ADR-049 PV-10-003,
    "Preview resource reads remain session-scoped and bounded"
    (ADR-049 L396).
  - Without that rule, a preview panel could read any data reference it can
    name, and an interactive panel could read any reference, not only the
    block's inputs.
  - Every panel's origin is `null`. The host must therefore authenticate
    messages by `event.source` or by a transferred `MessageChannel` port.
  - Panels mounted at the same time (a preview panel next to an interactive
    modal) can `postMessage` each other and impersonate the host to a
    naive SDK.
- **Suggested fix:**
  - State the read-scoping rule per context as part of the permission model.
  - Require channel-bound messaging in the specification requirements.

#### M8 — SDK and `panel.json` versioning and stability are not decided (open question)

- **Where:**
  - §4 L277-278 ("The message schema, the exact shape of each read, and the
    library the SDK ships as are specification detail").
  - §13 L508-509 (`panel.json` and the SDK become "the new author-facing
    surface under ADR-052").
- **What is weak:**
  - Today both contracts carry an `api_version` that the host checks before
    mounting (`PANEL_API_VERSION`, `interactive.py:46-53`;
    `FrontendManifest.api_version`, `models.py:290`;
    `previewerHostApi.ts:224-233`). `panel.json` as specified has none.
  - ADR-052 §5 records stability with Python decorators
    (ADR-052 L399-415). That mechanism does not apply to a JSON schema or a
    JavaScript SDK, and the ADR picks no tier for them.
  - How a panel built for SDK v1 is detected and refused, or served a
    compatible SDK, is a decision rather than detail. The ADR already calls
    the library set's versioned URLs "a contract" (L384-385).
- **Suggested fix:**
  - Add an API or SDK version to `panel.json`.
  - State the stability tier and how ADR-052's policy applies to non-Python
    surfaces.
  - State whether the SDK is injected by the host or loaded by the panel from
    the library set.

#### M9 — `governs`, `planned_governs`, and §11 Affected Artifacts are incomplete (frontmatter / scope)

- **Missing from `governs.files`** (all exist; each must change under the
  decision):
  - `src/scistudio/engine/scheduler/_dispatch.py` and
    `frontend/src/store/types.ts`: prompt references (M3).
  - `src/scistudio/blocks/process/builtins/data_router.py:74` and
    `pair_editor.py:75`: their `PanelManifest(panel_id="core.interactive.*")`
    declarations change when the modals become panels.
  - `src/scistudio/previewers/project.py`, `src/scistudio/previewers/choices.py`
    (cited in §3 L242-243), and `src/scistudio/core/dropins.py`: tier scanning
    for `<tier root>/panels/`.
  - `frontend/src/lib/interactiveMemory.ts` (governed by ADR-051 Addendum 1)
    and `frontend/src/components/DataPreview.tsx`.
  - The ADR-049 validator and contract tables (§3 L233-234 says the validator
    reports the mismatch).
  - The "What Is A Type" tutorial under
    `src/scistudio/tutorials/core/what-is-a-type/**` (§8 L413-414, §11
    L467-468).
  - Agent-facing material that teaches the old contract:
    `src/scistudio/_agent_reference/block-contract.md:42-53` and
    `src/scistudio/_skills/scistudio/scistudio-write-block/SKILL.md:67`.
- **ARCHITECTURE.md is missing from §11.** Its §9.6 (L1742-1780), §12.2.3
  (L2152-2161: "each spec binds a target type to a frontend renderer"), and
  §5.3.1 (L813: the prompt "carrying the block's panel manifest") describe the
  contracts being replaced. It is owner-controlled (`docs/ai-developer/rules.md`
  L113-115), so the ADR should say that an update is proposed.
- **`planned_governs` is empty** although the ADR introduces new surfaces:
  - the `panel.json` schema;
  - the panel SDK;
  - the generic read API (M1);
  - the versioned local library route;
  - `<tier root>/panels/` discovery.
  The document standard reserves `planned_governs` for exactly these
  (`docs/ai-developer/specific_rules/document-standards.md:74-82`).
  `frontmatter_lint` passes because it does not check completeness.
- **Suggested fix:** Add these paths to `governs` or `planned_governs`, and add
  ARCHITECTURE.md to §11.

#### M10 — The built-in plot panel: plot artifacts are outside the canonical zone, and PDF display needs a renderer inside the sandbox (false claim / design weakness)

- **Where:**
  - §5 L309-310: "Everything a panel can be asked to show already lives inside
    SciStudio's canonical zone".
  - §6 L359-364: `core.plot.basic` becomes a panel.
- **Evidence:**
  - `core.plot.basic` targets `PlotArtifact`
    (`src/scistudio/previewers/fallbacks.py:657-664`). Its session is
    special-cased (`src/scistudio/previewers/session.py:601`).
  - Plot-job outputs live in the preview cache
    `.scistudio/previews/.../current.*`. That cache is display-only and "not a
    scientific result" (ADR-048 §5 L307-317, §8 L403-404), so it is not a typed
    object in the canonical zone.
  - PDF plots are currently shown by the browser's built-in PDF viewer in a
    nested frame (`frontend/src/components/DataPreview.parts/PlotViewer.tsx:182-186`).
  - Sandboxed documents always carry the sandboxed-plugins restriction; no
    `allow-*` token lifts it. Chromium's built-in PDF viewer is not expected to
    render inside a sandboxed frame. Verify on Electron 42 either way.
- **Why it matters:** A PDF renderer (for example pdf.js) would have to be in
  the local library set. ADR-048 §6 requires PDF and SVG support
  (ADR-048 L363-366).
- **Suggested fix:** Correct the §5 claim, say how plot artifacts are read, and
  name the PDF path.

#### M11 — The performance claims are unsupported (design weakness)

- **Where:**
  - §5 L320-327 (reading values "is usually better than today's
    arrangement").
  - §13 L503-505 (round trips kept small by "windowed reads and transferred
    buffers").
- **Evidence:**
  - Current budgets are `max_tile=256`, `max_dim=256`, `max_rows=200`,
    `max_items=100` (`src/scistudio/previewers/models.py:617-625`).
  - Tiles are JSON float lists (M1).
  - Showing a 2048×2048 plane at native resolution takes 64 tile reads per
    slice change. Each read costs an HTTP call, a JSON decode, and a
    `postMessage`, where today one 256-pixel PNG is sent.
  - Series reads are unbounded (M1).
  - The current path already computes the full-plane display extent
    server-side before downsampling (`data_access.py:528-529`). A panel keeps
    that only if the read shape exposes it.
- **Suggested fix:** State target budgets and the binary transport as
  decisions. Revisit `PreviewLimits` for panel reads, or soften the claim.

### 2.3 Low

- **L1 — The tutorial is misdescribed (false claim).**
  - §8 L413-414 says "What Is A Type" teaches readers to write "both a
    previewer and a panel module in this form" (the `mount(container, host)`
    ES module).
  - Only the review panel uses that form
    (`.../assets/panels/review_labels/panel.mjs:171-175`).
  - The previewer it writes is a Python drop-in with no frontend module
    (`image_preview.py:241-257`). This also feeds H3.
- **L2 — §1.1 row 4 overstates what a previewer requires.**
  - L147 says a previewer means "a Python provider, a JavaScript module, and
    manifest wiring".
  - `frontend_manifest` is optional (`models.py:370`), and the tutorial ships
    a Python-only previewer.
- **L3 — The porting cost is understated.**
  - §5 L332-335 describes the spectroscopy provider as paging, filtering,
    grouping, and integrity checks.
  - It also renders export figures server-side with matplotlib to PNG, SVG,
    and PDF and sanitizes the SVG
    (`scistudio-blocks-spectroscopy/.../previewers/providers.py:399-446`).
  - Porting "to JavaScript" (§13 L497-499) includes publication-format export
    in the browser. That needs a library the set must include.
- **L4 — The asset allowlist change is understated.**
  - §4 L304-305 says the allowlist "gains `.html`".
  - A panel folder holds "images, styles, scripts" (§3 L203-204), and the
    allowlist has no `.png`, `.jpg`, `.gif`, `.webp`, `.wasm`, or `.ttf`
    (`src/scistudio/previewers/assets.py:33`).
- **L5 — Deferred work is anchored on the issue this ADR closes.**
  - The frontmatter declares `closes_issues: [2285]`.
  - §8 L420, §9 L434-435, §10 L447, and §12 L472-473 all say the removal, the
    deferrals, and the implementation are "tracked from #2285".
  - If the ADR's merge closes #2285, the 0.6 removal and the out-of-scope
    items rest on a closed issue. AGENTS.md §3.6 requires visible tracking.
    ADR-051 uses the same pattern, but these deferrals are long-lived.
- **L6 — §9 overstates panel stability.**
  - §9 L428-429 says "neither needs a panel to change".
  - Under §3's `contexts` rule, an existing panel must add the new context
    value, and handle what that context provides, before an edit or notebook
    context can open it.
- **L7 — The project-tier trust rationale expires.**
  - §2 L183-187 justifies equal trust for project panels by pointing to
    project Python previewer drop-ins that already run in the backend
    (`src/scistudio/previewers/project.py:156-172`;
    `src/scistudio/previewers/session.py:462-475`).
  - Those drop-ins are the provider mechanism §5 and §8 retire.
  - After 0.6 the argument no longer holds, while project panels (possibly
    from a shared project, with CDN scripts per H1) remain.
- **L8 — Some `related` ADRs are never cited.**
  - `related` lists ADR-017 and ADR-038, but the body never cites either
    (grep count 0).
  - The `block_config_resolved` sentence at L189-193 is ADR-038's field and
    should cite it.
- **L9 — The frame costs listed in §4 L298-305 are incomplete.**
  - Missing: no `localStorage`, `IndexedDB`, or cookies (panels cannot keep
    view preferences); no `alert` or `confirm` without `allow-modals`; no form
    submission or popups.
  - Escape and other host shortcuts will not close the full-screen
    interactive modal while the frame has focus (the modals are
    `fixed inset-0`: `DataRouterModal.tsx:103`, `PairEditorModal.tsx:127`,
    `DynamicPanel.tsx:178`).

### 2.4 Info

- **I1 — Version.** §8 L419 says "the current version is 0.3.4";
  `pyproject.toml:3` is `0.3.4a0`.
- **I2 — #1703 is unverifiable.** The claim that the imaging decoder was
  "moved out of core by the hotfix for #1703" (§5 L337) is not referenced in
  any committed source or in the three clones (grep). It cannot be verified
  from permitted evidence.
- **I3 — The non-Zarr claim holds for the imaging loader.** "No code path
  found produces the non-Zarr image references it serves" (§5 L338-339) is
  consistent with the imaging `LoadImage`, which streams TIFF into Zarr and
  references Zarr stores
  (`scistudio-blocks-imaging/.../io/load_image.py:154-163,237-247`). It is not
  exhaustively verifiable: AppBlock or CodeBlock output reconstruction and
  other packages are not covered.
- **I4 — Previewer module count.** "The imaging and spectroscopy packages
  each ship two previewers with their own frontend module" (§8 L411-412):
  each package's two previewers share one `viewer.js`
  (`scistudio-blocks-imaging/.../previewers/__init__.py:8`;
  `scistudio-blocks-spectroscopy/.../previewers/__init__.py:8`).
- **I5 — `gate_record check --mode pre-pr`:** N/A per the dispatch (no ledger;
  the ADR's PR ledger covers this report). Sentrux: N/A.

## 3. Checked And Found Correct

- **All governed paths and tests exist.** Every `governs.files` path and every
  `tests` path in the frontmatter exists. The four `governs.contracts` import
  (`PreviewerSpec`, `FrontendManifest`, `PanelManifest`, `InteractiveMixin`).
  The `scistudio.previewers` entry-point group is real (ADR-052 L302-307;
  `registry.py:195-200`).
- **The frontmatter validates.**
  `python -m scistudio.qa.audit.frontmatter_lint --format json docs/adr/ADR-054.md`
  returns `status: pass`, 0 findings. The body has `## 1. Decision Summary` and
  `### 1.1 Problems Addressed` with all four required columns, and every
  `Detailed section` points to an existing later section.
- **The nine core previewer ids in §6 match.** They are registered in
  `src/scistudio/previewers/fallbacks.py:600-673`.
- **The two built-in interactive windows are compiled components.**
  `DataRouterModal` and `PairEditorModal` resolve through a compiled
  `PANEL_REGISTRY` (`frontend/src/App.parts/InteractiveModals.tsx:39-70`).
  Package panels use a separate `import()` loader.
- **Both current loaders import modules into the application page.**
  `dynamicPreviewer.ts:82` and `panelModuleLoader.ts:107` each have their own
  host API and asset route (`data.py:785`, `blocks.py:494`), as §1 and §8 say.
- **The previewer host API offers no workflow-mutation method** beyond
  export and save (`previewerHostApi.ts:110-183`), as §4 says.
- **The desktop windows are sandboxed.** They run with `contextIsolation: true`
  and `sandbox: true` (`desktop/main.js:1334-1336,1439-1441`).
- **The asset allowlist lacks `.html` today** (`assets.py:33`).
- **The per-type user choice exists.** It is layered project over user
  (`choices.py:106-116`) and short-circuits above the ladder
  (`router.py:82-89`).
- **Project and user previewer drop-ins are imported into the backend
  process** (`project.py:156-172`, `session.py:462-475`), as §2 says.
- **ADR-051's biconditional capability and execution-mode check exists** and
  refuses a mismatch at scan time (`_capability.py:285-330`).
- **Interactive decisions are recorded in lineage** through
  `block_config_resolved`, with intermediate references stripped
  (`engine/scheduler/_lineage.py:254-261`; ADR-051 spec FR-011).
- **The contract symbols are provisional.** `FrontendManifest`,
  `PreviewerSpec`, `PanelManifest`, and `InteractiveMixin` are all
  `@provisional(since="0.3.1")` (`models.py:258,322`;
  `interactive.py:76,183`). ADR-052 §5 lets provisional symbols change in a
  minor release with a changelog entry (ADR-052 L421-435).
- **`PreviewLimits.max_dim` is 256** (`models.py:625`). The imaging provider
  downsamples to it (`providers.py:180-188,346`). `applyLUTToImage` remaps a
  PNG in the imaging `viewer.js` (`viewer.js:95,412`).
- **The spectroscopy provider matches its description.** It reads through
  `PreviewDataAccess` and states "NO scientific processing"
  (`providers.py:22-23,233,489,644`).
- **The imaging provider decodes TIFF and Pillow formats itself**
  (`providers.py:19-22,124-150`).
- **"About 1,570 lines" is accurate.** The two `providers.py` files total
  487 + 1,086 = 1,573 lines.
- **LCMS ships four interactive panels.** There are four
  `ExecutionMode.INTERACTIVE` blocks with `PanelManifest` and four panel
  modules. The imaging package's Fiji and napari blocks are `EXTERNAL`
  AppBlocks, not panels.
- **The canonical-zone citation is accurate** (ARCHITECTURE.md §4.3.2,
  L419-473). "Types do not own file formats" is in ADR-043 §1 (ADR-043 L90-91).
- **The ADR-055 citations are accurate.** ADR-055 §2 puts the Lab user's
  browser on their own computer, and §8 describes JupyterHub path routing.
- **The ADR-051 Addendum 1 interaction memory is unaffected** by the text as
  written. The generic modal wrapper persists the decision
  (`InteractiveModals.tsx:93-110`).

## 4. Method And Context Boundary

I read `AGENTS.md`, `docs/ai-developer/rules.md`,
`docs/ai-developer/personas/audit-reviewer.md`, and
`docs/ai-developer/specific_rules/document-standards.md`. Then I read the ADRs,
specs, architecture sections, code, and package clones listed at the top of
this report.

I did **not** read:

- issue #2285 or PR #2286;
- any commit message (no `git log` with messages, no `git show`, no
  `git blame`);
- anything under `.workflow/records/2285*` or `.workflow/local/`;
- any scratchpad file other than the three package clones;
- any memory file, chat summary, or manager summary.

Commands run:

- `python -m scistudio.qa.audit.frontmatter_lint --format json docs/adr/ADR-054.md`
  (pass);
- a Python import check of the four governed contracts (OK);
- `wc -l` over the package provider and frontend files;
- `grep` searches cited inline.

Browser-behaviour statements are marked as needing verification on the
supported Electron build. Those are the process isolation in M5 and the PDF
viewer in M10.

## 5. Recommendation

**Pass-with-fixes.** Required before merge: H1-H5.

- H1 and H4 correct statements the evidence contradicts.
- H3 and H5 close gaps in the migration plan and the operation model.
- H2 needs a decided asset-authentication mechanism, and may reopen the §4
  alternatives.

M1-M11 should be fixed in the same revision, or recorded as explicit
specification requirements with tracked follow-ups. The low and info items
are editorial.
