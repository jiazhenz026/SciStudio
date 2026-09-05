---
adr: 48
addendum: 1
title: "The Previewer Becomes A Panel — One Contract, And When The Old One Ends"
status: Proposed
date_created: 2026-09-03
date_accepted: null
date_superseded: null

supersedes: []
superseded_by: null
related: [51, 53, 54]
closes_issues: []
tracking_issue: 2229

is_code_implementation: false
governs:
  modules: []
  contracts: []
  entry_points: []
  files:
    # This addendum records a contract change and hands the surfaces it names
    # to ADR-054 and docs/specs/adr-054-panel-contract.md (Section 6). It
    # claims no code surface of its own, because claiming one would contradict
    # the transfer it exists to record.
    - docs/adr/ADR-048-addendum1.md
  excludes: []

tests: []
agent_editable: false
assisted_by:
  - "Claude:claude-opus-5"

phase: planning
tags:
  - adr-048
  - adr-054
  - panels
  - previewers
  - plugin-contracts
  - compatibility
  - governance
owner: "@jiazhenz026"
co_authors:
  - "@claude"
language_source: en
translations: []
---

# ADR-048 Addendum 1: The Previewer Becomes A Panel — One Contract, And When The Old One Ends

## 1. Decision Summary

ADR-048 gave SciStudio a previewer: a viewer chosen by the type of the data,
supplied by core, a package, the user library, or a project, described by a
manifest, and loaded into the running application as an ES module. ADR-051 gave
an interactive block a window: a viewer named by the block, described by a
manifest, and loaded into the running application as an ES module through a
second asset route. Two mechanisms were built for what turned out to be one
thing, and a package author who wanted the same spectrum view in both places
had to write it twice.

ADR-054 §3 replaces both with a single **panel** contract. A panel declares one
of two capabilities: *displaying*, which renders what it is given and has no
outbound path, and *producing*, which renders what it is given and can hand a
value back. A previewer is not a separate kind of component any more. It is the
degenerate case of a panel — one resolved by the type of the data, declaring
only the displaying capability — and the word *previewer* survives in the code
only as the name of that capability, in historical documents, and in the
compatibility surface this addendum bounds.

This addendum records three things ADR-048 owes the people who wrote against
it. What a package author must now do, concretely (Section 3). What keeps
working while they do it, and by what mechanism (Section 4). And when the
compatibility that keeps it working goes away (Section 5), because ADR-054 §9.4
is explicit that a shim with no removal condition is a second implementation
with a friendly name. Section 6 records which of ADR-048's governed surfaces
move to ADR-054 and `docs/specs/adr-054-panel-contract.md`, and which stay.

The panel contract is delivered by `docs/specs/adr-054-panel-contract.md`; this
addendum states the requirements it carries and does not restate its
implementation.

### 1.1 Problems Addressed

| Problem | Risk | Response | Detailed section |
|---|---|---|---|
| ADR-048 defined a previewer as its own kind of component, so the same view had to be written twice to serve a block's window as well as a data preview | Two loaders, two API version constants, two asset routes and two failure behaviours drift apart, and a package author pays for the duplication | One panel contract with two declared capabilities; a previewer is its displaying case | Section 2 |
| A package written against ADR-048's ES-module form cannot mount under the new one, and its author cannot migrate on the day the contract changes | A SciStudio release silently stops rendering a published package's data | The retired form keeps loading through a shim that grants it nothing new | Section 4 and Section 5 |
| An author who does migrate has no statement of what actually changed for them | Migration by guesswork, and support questions in place of a document | State the three changes — the authoring form, registration, and the vocabulary — concretely | Section 3 |
| A compatibility shim with no removal condition outlives the migration it was written for | The shim becomes a second implementation with a friendly name, permanently | Name the removal condition here, in the change that introduces the shim | Section 5 |
| ADR-048's previewer surfaces would otherwise stay governed by an ADR that no longer describes them | Governed claims that describe a contract nobody implements, and an audit that cannot tell | Transfer the panel surfaces to ADR-054 and its panel-contract spec; keep the rest | Section 6 |

## 2. Why One Contract Replaced Two

ADR-048 §4 and ADR-051 §4 arrived at the same mechanism independently, and by
the time both had shipped the machinery below the surface had diverged without
cause: two copies of the validate-load-mount sequence, two API version
constants, two asset whitelists, and two different things happening when a
module failed to load. Nothing about a previewer and a block's window is
different in the loading, versioning, serving, or failure behaviour. What
differs is how a panel is addressed — by the type of the data, or by name from
the block that opens it — and which outbound path the host grants it. ADR-054
§9.1 states the rule the unification follows: the panel is one implementation
whose differences are parameters, never a second copy of the mechanism.

The vocabulary had to move with it. ADR-054 §9.3 puts the reason plainly: code
that keeps *previewer*, *interactive panel*, and *explore panel* as three nouns
will keep three of everything else, because a reader with three names has no
signal that they are looking at one thing. So the concept is the panel, and
`previewer` names one of its two capabilities.

The gain a package author collects is that a view is written once. A region
picker for a spectrum renders that spectrum read-only when a person opens it
from the canvas, and produces a region when the same picker is mounted in a
producing position. The author never chose which situation it belonged to.

## 3. What A Package Author Must Now Do

Three things change for a package that ships previewers. None of them is a
rename that a search-and-replace settles.

**The authoring form.** An ADR-048 previewer is an ES module with a named
export, imported into the application's own React tree from a
backend-validated, same-origin URL. A panel is one self-contained HTML file —
markup, styles, and script in a single document — mounted in a sandboxed frame
and reachable only through message passing (FR-002, FR-007). The frame is
granted `allow-scripts` and nothing else, so it runs at an opaque origin; the
host addresses it by its window reference, every message in both directions
carries a per-mount token the host issued at mount, and the host additionally
checks that the message came from the frame it mounted (FR-008). The one thing
the document can fetch on its own is the read-only asset route, which answers it
as a cross-origin request (FR-021).

What the panel loses is any reach into the application: its document, its
storage, its API, its store, and its keyboard. What it gains is that its first
attempt can fail without consequence — a runaway loop, a leaked global handler,
or a thrown exception is contained in the panel that caused it — and that the
author can open the file in a browser with stub data and see whether it works.
ADR-054 §3.2 records why that property dominates the choice of form.

**Registration.** ADR-048 registration is a `get_previewers()` factory behind
the `scistudio.previewers` entry point, returning constructed `PreviewerSpec`
objects. A package now registers panels through the `scistudio.panels`
entry-point group, whose entry point resolves to one or more panel directories
inside the package (FR-045). A panel directory holds a declaration file and its
entry document; the declaration carries the panel's id, its display name, the
data types it targets, its declared capability, and the name of its entry
document, and one missing field is refused at discovery with a diagnostic
naming the directory and the field (FR-002, FR-003). No package constructs a
Python object to register a panel, which is what lets a person — or the agent
on their behalf — register one by writing files.

Python does not disappear; it stops being mandatory. A panel may name a Python
provider that windows data of its target types, and when it does not, the host
serves its windowed reads from the shared bounded data-access layer (FR-047).
A package type that layer cannot window still ships a provider, resolved from
the tier the panel was discovered in.

**The vocabulary.** `PreviewerSpec` is `PanelSpec`, `PreviewerRegistry` is
`PanelRegistry`, and `scistudio.previewers` is `scistudio.panels`. The change
an author is most likely to trip over is narrower: the free-form `capabilities`
tuple on a spec — the one carrying feature tags such as `table`, `sort`,
`slice`, and `lut` — is now `features` (FR-051). The word *capability* names
only the declared displaying or producing capability, and nothing else.

## 4. What Keeps Working, And How

A package author cannot migrate on the day the contract changes, and a release
of SciStudio that silently stops rendering a published package's data is not
shippable. Four things therefore keep working for the duration of the
migration, each by a named mechanism rather than by accident.

**The entry-point group and its factory.** `scistudio.previewers` and its
`get_previewers()` factory continue to be discovered (FR-045, FR-020). A
package that supplies that factory is found exactly as it was.

**The retired import paths.** `scistudio.previewers` remains an importable
module that re-exports the renamed symbols under their old names, alongside
`scistudio.previewers.models`, `scistudio.previewers.data_access`, and
`scistudio.previewers.helpers`. The four modules contain imports and aliases
and no logic of their own. A package that imports `PreviewerSpec` from that
path — which every package supplying the factory above does — keeps resolving.

**The existing asset routes.** The two routes serving previewer bundles and
interactive-block panel modules today continue to serve their existing clients
while the merged route of FR-021 takes over (FR-022). An unmigrated package
fetches its module from the route it was built against.

**The on-disk drop-in directories.** `~/.scistudio/previewers/` in the user
library and `previewers/` in an open project keep being discovered, and so does
a project's default-previewer declaration in `.scistudio/previewers.json`,
carried over under the panel naming with its current behaviour (FR-046). These
are read from projects that already exist on disk, which is why their names
survive the rename rather than moving with it.

## 5. The Shim, And Its End

An ADR-048-form previewer keeps loading through a compatibility shim (FR-042).
The shim wraps the retired module form so that data a package previews still
appears; it is the reason a person who upgrades SciStudio with an older
`scistudio-blocks-imaging` installed still sees their images.

The shim grants nothing new. It hands a wrapped previewer neither variable
bindings nor an outbound path (FR-043): a package that has not migrated keeps
working, and obtains the producing capability and the session bindings by
moving to the contract, not by waiting. ADR-054 §9.4 names this as the one
thing the shim must not do, because a shim that accretes the new surface
becomes the second implementation permanently.

That leaves the question ADR-054 §9.4 refuses to defer, and FR-044 requires to
be answered here rather than by a later judgement call.

**The shim is removed when all three of these are true.**

First, `scistudio-blocks-imaging` — the one published package known to ship
previewers written against the retired form — has published a release in which
every panel it registers is a directory registered through the
`scistudio.panels` entry-point group, in the on-disk form the contract
requires, and that release is the package's latest.

Second, nothing inside this repository still reads the retired form:
`src/scistudio/previewers/` holds only the four alias modules and no logic; no
test mounts a panel through the shim except the one that proves the shim
behaves as FR-042 and FR-043 require; and no tutorial asset, package template,
or scaffold emits an ES-module previewer.

Third, one released version of SciStudio has carried both the panel contract
and the deprecation notice on the retired import path, so that a project or a
user library holding a previewer of its own — which no inventory in this
repository can enumerate — has had a release in which it was told.

The check belongs to the owner of the imaging-package migration, on the issue
that tracks it, and every clause is settled by looking rather than by judging:
at the imaging package's published entry-point declaration and the directories
that release ships, at the contents of `src/scistudio/previewers/` and of the
test tree, and at the release that carried the deprecation. When all three
hold, removal is a deletion and not a redesign: the shim, the four alias
modules, the `scistudio.previewers` entry-point group, the two retained asset
routes, and the retired drop-in directory names go together in one change.

What the third clause buys is a bounded exposure rather than a guarantee, and
that is worth saying rather than implying. After removal, an installation still
holding a previewer written against the retired form gets the ordinary
load-failure behaviour of the contract: the host renders its own error surface
naming the panel and the failure, and mounts the fallback panel the backend
named, so the data stays visible (FR-014). The shim shortens the window in
which anyone meets that; it was never the only thing standing between an
unmigrated previewer and a blank pane.

## 6. The Governance Transfer

ADR-054 §10.1 requires this addendum, and its own front matter defers to it:
the previewer and panel-loader surfaces are governed by ADR-048 and ADR-051
today, and governance moves with the addenda rather than being claimed by
ADR-054 directly. This section records the move for ADR-048's half.

Moving to ADR-054 and `docs/specs/adr-054-panel-contract.md`:

| Surface | Where it goes |
|---|---|
| The `scistudio.previewers` entry point, as an entry-point group | Governed by the panel-contract spec, which owns its retention (FR-045) and, through Section 5 above, its end. The live group is `scistudio.panels`. |
| The previewer subsystem itself — its registry, router, specs, and frontend manifest — renamed to `scistudio.panels`, together with the alias modules under `scistudio.previewers` | Governed as the `scistudio.panels` and `scistudio.previewers` modules and as the `PanelSpec`, `FrontendManifest`, and `PreviewEnvelope` contracts of the panel-contract spec. ADR-048 never claimed these paths as governed files; the spec now does. |
| The preview asset route in `scistudio.api.routes.data`, and the endpoints that list panels, rebuild the registry, and record the per-type choice | The merged asset route and the panel naming (FR-021, FR-023), governed by the panel-contract spec. |
| The frontend preview host, its dynamic module loader, its host API, and its dispatch from a response's kind to a viewer component — `frontend/src/components/DataPreview.parts/**` and `frontend/src/store/previewSlice.ts` | Replaced by `frontend/src/panels/**` (FR-007 to FR-015, FR-036), governed by the panel-contract spec. |
| The four-tier drop-in roots and entry-point wiring in `scistudio.core.dropins` and `scistudio.core.entry_points`, as they apply to panels | Governed by the panel-contract spec (FR-018, FR-045, FR-046). |

Staying with ADR-048 and its specs:

| Surface | Why it stays |
|---|---|
| The preview session API — `scistudio.api.routes.data.create_preview_session` and the session lifecycle around it | ADR-048 §2 defines it and the panel contract does not change it. What is mounted changes; how a session is created does not. |
| `scistudio.api.schemas.PreviewEnvelopeModel` and the routed session responses | Unchanged apart from the fallback-panel field FR-015 adds, which the panel-contract spec carries. |
| `PreviewDataAccess`, the bounded-read helpers, and the preview budget of ADR-048 §7 | The panel contract reuses this layer as the default source of a panel's windowed reads (FR-047); it does not redefine it. |
| The Python providers of the core fallback viewers of ADR-048 §6 | FR-033 leaves them unchanged. Only the document each renders through moves. |
| Preview-side plot jobs in their entirety — `plot.yaml`, the plot cache under `.scistudio/previews/`, the artifact semantics of `PlotPreviewer`, `scistudio.blocks.code`, the MCP plot tools, and the `scistudio-write-plot` skill | Out of scope of the panel contract. The plot panel moves across as a panel resolved by type declaring only the displaying capability; giving it the producing capability is deferred to a tracked issue. |
| `scistudio.api.runtime`, `frontend/src/components/DataPreview.tsx`, `frontend/src/store/types.ts`, `frontend/src/types/api.ts`, and `frontend/src/lib/api/data.ts` | Preview session plumbing and the preview tab shell, not the panel contract. |
| The developer-documentation inventory of `docs/specs/adr-048-developer-docs-refresh.md` | Human documentation revision is tracked separately. |

<!-- TODO(#2212): the plot panel's producing capability is deferred.
     Out of scope per ADR-054 §3.6 and docs/specs/adr-054-panel-contract.md
     scope.out. Followup: issue #2212. -->

<!-- TODO(#2211): the package-development and user documentation that describes
     the ADR-048 previewer authoring form is revised separately.
     Out of scope per docs/specs/adr-054-panel-contract.md scope.out.
     Followup: issue #2211. -->

## 7. Verification

The properties this addendum asserts are verified by the panel-contract spec's
own coverage rather than by anything added here. A previewer built against the
retired module form renders through the shim and is confirmed to receive
neither variable bindings nor an outbound path; a panel written against the
contract is confirmed to need no shim; a package registers a panel through the
entry-point group with a directory and no Python object; and the retained
entry-point group, alias modules, asset routes, and drop-in directories are
exercised as the migration path they are.

The removal condition of Section 5 is verified by reading it, which is what
FR-044 asks for. Its three clauses were written to be settled by inspection so
that the reading is not an argument.

## 8. Consequences

A package author writes one panel where they wrote two components, and writes
it in the most widely documented UI form there is. The cost of that is real and
is worth stating plainly: the panel can no longer reach into the application,
so anything it used to do by touching the host — opening a dialog, starting a
download, reading the store — is now either a message to the host or not
available at all. A panel also renders only inside SciStudio, which the frame
boundary makes unavoidable.

The compatibility surface is wider than a shim: an entry-point group, four
alias modules, two asset routes, and two drop-in directory names, all retained
at once. That is the price of not breaking a published package on an upgrade,
and Section 5 is what keeps the price temporary.
