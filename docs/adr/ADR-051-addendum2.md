---
adr: 51
addendum: 2
title: "The Block's Window Becomes A Panel — A Shared Contract, A Frame, And Host Chrome"
status: Proposed
date_created: 2026-09-03
date_accepted: null
date_superseded: null

supersedes: []
superseded_by: null
related: [48, 53, 54]
closes_issues: []
tracking_issue: 2229

is_code_implementation: false
governs:
  modules: []
  contracts: []
  entry_points: []
  files:
    # This addendum records a contract change and hands the surfaces it names
    # to ADR-054 and docs/specs/adr-054-panel-contract.md (Section 7). It
    # claims no code surface of its own, because claiming one would contradict
    # the transfer it exists to record.
    - docs/adr/ADR-051-addendum2.md
  excludes: []

tests: []
agent_editable: false
assisted_by:
  - "Claude:claude-opus-5"

phase: planning
tags:
  - adr-051
  - adr-054
  - panels
  - interactive-blocks
  - block-contract
  - frontend-runtime
  - governance
owner: "@jiazhenz026"
co_authors:
  - "@claude"
language_source: en
translations: []
---

# ADR-051 Addendum 2: The Block's Window Becomes A Panel — A Shared Contract, A Frame, And Host Chrome

## 1. Decision Summary

ADR-051 §4 gave an interactive block its own window, on the argument that only
the block knows what view makes its data actionable. That argument stands and
this addendum does not touch it. What changes is the machinery underneath: the
window is now a **panel** under the single contract of ADR-054 §3, mounted the
same way, versioned by the same constant, served by the same route, and failing
the same way as every other panel in SciStudio.

Four consequences follow, and each is a real change rather than a rename. The
manifest that describes the window moves out of the block layer into the core
layer, for a layering reason rather than a tidiness one (Section 2). A block
that names a panel must name a *producing* one, and that is checked when the
block is discovered rather than when it first pauses (Section 3). The window
is now a self-contained document in a sandboxed frame, so it can no longer
reach into the application — which is why Confirm and Cancel stop being the
panel's and become the host's chrome around it (Section 4 and Section 5). And,
deliberately, there is no compatibility shim on this side of the change
(Section 6).

The pause itself is untouched. ADR-051 §3's guarantee — that a workflow stopped
for a human holds no block code resident, keeps the isolation ADR-017
guarantees, and stays cancellable throughout — is the reason ADR-051 exists,
and ADR-054 §2 keeps its shape exactly. The prompt phase, the reference-carried
intermediate channel, the two subprocess runs, the `PAUSED` state, and the
recording of the decision in `block_config_resolved` are all as they were.
Addendum 1's interaction memory is likewise unaffected; it stores a decision,
not a window.

The panel contract is delivered by `docs/specs/adr-054-panel-contract.md`. This
addendum states what that spec requires of ADR-051's surfaces and does not
restate its implementation.

### 1.1 Problems Addressed

| Problem | Risk | Response | Detailed section |
|---|---|---|---|
| The `PanelManifest` sits in the block layer, but the panel subsystem and the API layer above it both need it | The pressure to avoid an upward import produces a second manifest type in the block layer — the exact duplication the unification exists to remove | Move the shared contract into the core layer, where `core/origins.py` already put a type whose consumers span layers | Section 2 |
| A block can name a panel that cannot hand a value back, and nothing notices until a scientist has run half a workflow and hit the pause | A workflow fails at the worst possible moment, on a defect that was visible at load time | Require the producing capability on a block-declared panel and check it when the block is discovered | Section 3 |
| ADR-051's window and ADR-048's previewer are loaded, versioned, served, and failed by two separate mechanisms | Two loaders, two version constants, two asset routes and two failure behaviours drift apart | One loader, one constant, one route, one failure behaviour; the block's naming of its panel is a parameter, not a second implementation | Section 4 |
| A panel in a sandboxed frame cannot own a Confirm button, because its only outbound path is the emission of code | Either the frame boundary is weakened for one button, or confirming an interaction breaks | The host renders Confirm and Cancel as chrome and commits the panel's most recent emission | Section 5 |
| The frame boundary also removes reach the interactive surface was relying on, including a shipped tutorial's highlight target | A migration that silently breaks a tutorial a user is following | Move what the frame cannot carry to the host, explicitly, rather than deferring it | Section 5 |
| An asymmetric compatibility posture looks like an omission unless it is written down | Someone later "fixes" it by adding a shim nobody needed | Record that the interactive-panel module form gets no shim, and why | Section 6 |
| ADR-051's panel-side surfaces would otherwise stay governed by an ADR that no longer describes them | Governed claims describing a contract nobody implements | Transfer them to ADR-054 and its panel-contract spec; keep the pause | Section 7 |

## 2. The Manifest Moves To The Core Layer

`PanelManifest` is declared today in `scistudio.blocks.base.interactive`, which
is where an interactive block declares its `interactive_panel`. Under the
unified contract the same type is read by the panel subsystem, which serves and
validates manifests and sits above the block layer, and by the API layer, which
routes them and sits above that. It therefore moves to `scistudio.core.panels`,
together with the capability declaration and the single API version constant,
and `scistudio.blocks.base.interactive` imports it from there (FR-001).

The reason is a layering constraint and not a preference, and it is worth
writing the reason rather than only the fact. SciStudio has answered this exact
question once already: `core/origins.py` records that it sits in
`scistudio.core` because its consumers span layers and no layer above `core`
may be imported by the others, which is also why the tier roots live in
`core/dropins.py` rather than inside the block or type registries. The panel
contract takes the same placement for the same reason, leaving the panel
subsystem to own the registry, the routing ladder, the asset route, and the
host.

ADR-054 §9.2 names the failure that follows from getting this wrong, and it has
a specific shape: a shared type left inside the panel subsystem forces the
block layer to import upward; the pressure to relieve that produces a second
manifest type inside the block layer; and the duplication the whole change
exists to remove reappears — arrived at through a layering constraint rather
than through carelessness. The architecture layer test is where this is
enforced, and its enumeration of subsystems moves with the change.

## 3. A Block-Declared Panel Must Be A Producing Panel

A panel declares one of two capabilities, and the declaration is static, read
from the panel's declaration file, and resolved before the panel loads; there
is no runtime negotiation by which a mounted panel acquires a capability it did
not declare. An interactive block exists to take a decision from a person, so
the panel it names must be able to hand a value back: a block-declared panel
MUST declare the producing capability (FR-050).

Where that is checked matters more than that it is checked. It happens when the
block is discovered, with a diagnostic naming the block and the panel, and not
when the block first pauses. ADR-051 §2 already established the principle for
the interaction capability itself — the registry refuses at load time a block
that claims the interactive execution mode without the capability, or that
omits the window it promises to open — and this is the same principle applied
to the window's own declaration. A pause is reached after a scientist has run
the front of a workflow on real data; it is the worst moment to discover a
declaration error that was legible at load time.

The reverse direction is not symmetric and does not need to be. A producing
panel is also mountable for display (FR-006), so a block author who writes a
region picker for their block gets, at no extra cost, a panel that can be
routed by data type and rendered read-only from the canvas.

## 4. One Mounting Mechanism For Every Panel

The window a block opens is now mounted exactly as any other panel: one
self-contained HTML document in a frame carrying `sandbox="allow-scripts"` and
nothing else, reached only through message passing, with a per-mount token on
every message in both directions and a check that the message came from the
frame the host mounted (FR-002, FR-007, FR-008). The host completes a handshake
before treating the panel as mounted, and a panel that does not answer within a
bounded wait is treated as a load failure rather than left blank (FR-009).

How the block's panel is *found* does not change. It is named by the block —
`InteractiveMixin.interactive_panel` is a manifest declared on the class — so it
is discovered exactly as its block is and inherits the block tiers, including
the user library (FR-017). ADR-054 §9.1 is precise about which differences are
legitimate: how a panel is addressed, and which outbound path the host grants
it. Both are parameters of one implementation. Everything else was duplicated
for no reason and stops being duplicated: `dynamicPreviewer.ts` and
`panelModuleLoader.ts` become one loader, the two API version constants become
one, the previewer asset route and the block panel asset route become one
merged route with one path-confinement check and one suffix allowlist, and the
two different behaviours when a module failed to load become one — the host
renders its own error surface naming the panel and the failure, and mounts the
fallback panel the backend named, so the data stays visible (FR-014, FR-015,
FR-021).

The two core interactive panels — the data router's and the pair editor's
windows — are rewritten as panel directories on disk under the panel subsystem,
keeping the ids they already carry, and are served through the same route as
every other tier. Their blocks' Python is unchanged. Because they are
directories rather than compiled-in components, they can be shadowed from the
user library or a project and copied by copying a directory, on the same terms
as any other panel (FR-033, FR-037).

One thing this change does not yet do: the modal that hosts an interactive
block's window survives, with its built-in panel registry replaced by tier
resolution. ADR-054 §4.2 retires the modal in favour of the Explore tab, and
that is a later step in ADR-054 §10.1's migration order, not this one.

## 5. What Replaces Confirm And Cancel, And What Else The Frame Cannot Carry

A producing panel's only outbound path is the emission of code (FR-012). It
holds no Python object, it cannot reach the application, and the meaning of
what it emits is settled by where it is mounted rather than by the loading
machinery. A panel with exactly one outbound message type does not own a
Confirm button.

So the host owns it. Confirm and Cancel are rendered by the host as chrome
around the frame, in the same place the host already renders the panel's title
bar and binds the escape key. Confirm commits the panel's most recent emission;
with no emission yet, Confirm is disabled. Cancel is ADR-051's cancel path
unchanged — the interaction is refused, the engine releases whatever
intermediate work the prompt phase left behind, and no computing run starts.

Why that is safe rests on one property, and the property is the reason it is
stated here rather than left implicit. Every producing panel re-emits its whole
decision on every change, so the newest emission is always the current
decision; the host never has to reconcile a sequence of partial edits, and
"commit the latest emission" is exactly "commit what the person is looking at".
This is a contract on the panel, not an accident of the built-in ones, and each
producing document carries it as a comment so that a person forking the panel
does not quietly break it.

The same boundary removes other reach, and the honest accounting is worth
making. What it buys is containment and clean reloads: a runaway loop, a leaked
global handler, or a thrown exception stays inside the panel that caused it
(ADR-054 §3.2), and saving an edited panel tears the frame down and builds a
new one with no cached module left behind (ADR-054 §3.5). What it costs is
every capability that depended on the panel being part of the application.

Two of those costs are settled here rather than deferred. A **download** is
host chrome: the frame is not granted `allow-downloads`, so a panel that wants
to export or save asks the host through a named message and the host performs
it. And the **tutorial surface** the collection panel used to carry moves to
the host. The shipped `what-is-a-type` tutorial depends on a UI event and a
highlight target that a frame at an opaque origin can carry neither of; the
host therefore fires that event when it services a panel's request to open a
collection item, and carries the highlight target on its own chrome around the
frame. This is not deferrable and a tracked TODO would not be an acceptable
answer for it: it is a shipped tutorial, and the migration must not break it.

## 6. No Shim On This Side, Deliberately

ADR-048's addendum 1 records a compatibility shim that keeps a previewer
written against the retired ES-module form loading, and states the condition
under which that shim is removed. No equivalent shim exists for the
interactive-panel module form, and the asymmetry is a decision rather than an
oversight.

The reason is that the two forms have different populations. Previewers are
published by packages outside this repository — `scistudio-blocks-imaging`
among them — and by user libraries and projects nobody here can enumerate. The
interactive-panel module form has no such population: its only consumers are
inside this repository, and the single asset carrying a hard-coded panel module
URL is a tutorial asset updated as part of this change. A shim for a form with
no external consumer would be a second implementation kept alive to serve
nobody, which is precisely what ADR-054 §9.4 warns against.

If a package outside this repository is later found to ship an interactive
block whose window is written against the retired form, the answer is to
migrate it, not to add the shim retroactively; a block ships with its window,
so the two move together in one release.

## 7. The Governance Transfer

ADR-054 §10.1 requires this addendum, and ADR-054's own front matter defers to
it: the interactive-block panel surfaces are governed by ADR-051 today, and
governance moves with the addenda rather than being claimed by ADR-054
directly. This section records the move for ADR-051's half.

Moving to ADR-054 and `docs/specs/adr-054-panel-contract.md`:

| Surface | Where it goes |
|---|---|
| The `PanelManifest` contract, declared today in `scistudio.blocks.base.interactive` | Governed by the panel-contract spec, which carries it while it sits in the block layer and carries `scistudio.core.panels.PanelManifest` and `PanelCapability` once Section 2's move lands. |
| `scistudio.blocks.base.interactive` and `src/scistudio/blocks/base/interactive.py`, for the panel half only — the manifest declaration and the import that replaces it | Governed by the panel-contract spec. The interaction capability in the same module stays with ADR-051; see below. |
| The block panel asset route in `scistudio.api.routes.blocks` | Folded into the merged panel asset route, governed by the panel-contract spec (FR-021, FR-022). |
| The frontend panel module loader and the dynamic panel component under `frontend/src/App.parts/InteractiveModals.parts/`, and the built-in panel registry in `frontend/src/App.parts/InteractiveModals.tsx` | Replaced by the single loader and frame host in `frontend/src/panels/**` and by tier resolution (FR-007 to FR-015, FR-037), governed by the panel-contract spec. |
| The two core interactive windows, `frontend/src/components/DataRouterModal.tsx` and `frontend/src/components/PairEditorModal.tsx` | Become panel documents under the panel subsystem's built-in tier (FR-033), governed by the panel-contract spec. |

Staying with ADR-051 and `docs/specs/adr-051-interactive-blocks.md`:

| Surface | Why it stays |
|---|---|
| `ExecutionMode`, `InteractiveMixin`, `InteractivePrompt`, `prepare_prompt`, and the registry check binding the capability to the interactive execution mode | The interaction capability is ADR-051's subject. Only the window's description moves. |
| The two-phase subprocess runtime — `scistudio.engine.scheduler`, `scistudio.engine.runners`, the `PAUSED` state, cancellation, and the reference-carried intermediate channel | ADR-054 §2 keeps ADR-051 §3's shape exactly; nothing here changes. |
| `scistudio.engine.events` and `scistudio.api.ws`, which carry the prompt and the decision | The transport of the interaction, not the rendering of it. |
| `scistudio.blocks.process.builtins.data_router` and `.pair_editor` | Their Python behaviour is unchanged; only the documents their windows render through move. |
| Interaction memory — the contract recorded in ADR-051 addendum 1 | It remembers a decision, and a decision is independent of the window that produced it. |
| `docs/architecture/ARCHITECTURE.md` | Owner-controlled and outside this change's scope. |

<!-- TODO(#2211): the package-development and user documentation describing the
     ADR-051 interactive-panel authoring form is revised separately.
     Out of scope per docs/specs/adr-054-panel-contract.md scope.out.
     Followup: issue #2211. -->

## 8. Verification

The properties this addendum asserts are verified by the panel-contract spec's
own coverage. The architecture layer test must show the panel contract in the
core layer with no upward import from the block layer. A block declaring a
displaying-only panel must be refused at discovery with a diagnostic naming the
block. A displaying panel must be granted no outbound message type, verified
from the host's side rather than from the declaration. The load-failure paths —
a malformed document, a version mismatch, an unanswered handshake — must each
leave the data visible. And the shipped `what-is-a-type` tutorial's tests must
still pass unchanged, which is the check that Section 5's move of the tutorial
surface to the host actually happened.

ADR-051's own verification is unchanged and must stay green: both phases run in
subprocesses, the computing run depends on nothing left in memory, intermediate
work crosses the pause only by reference, and cancellation releases that work
and starts no computing run.

## 9. Consequences

An interactive block author writes their window in the most widely documented
UI form there is, can open it in a browser with stub data to see whether it
works, and gets a panel that is also routable by data type for read-only
display. A package can now ship an interactive block whose window loads through
the same contract as everything else, which is what ADR-051 §4 promised and
left to a later mechanism.

The cost is that the window loses every reach into the application it might
have had, and two of those losses had to be answered rather than accepted:
Confirm and Cancel become host chrome, and the tutorial surface moves to the
host. A third is accepted openly — a panel renders only inside SciStudio, which
the frame boundary makes unavoidable.

The asymmetry in Section 6 is the part most likely to be misread later. It is
recorded so that the absence of a shim reads as a decision about who consumes
the retired form, and not as work someone forgot to do.
