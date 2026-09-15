---
adr: 52
addendum: 1
title: "The Panel Contract Is Public API With A Generated Reference"
status: Proposed
date_created: 2026-09-15
date_accepted: null
date_superseded: null

supersedes: []
superseded_by: null
related: [42, 52, 54]
closes_issues: [2430]
tracking_issue: 2430

is_code_implementation: true
governs:
  modules:
    - scistudio.panels.descriptor
    - scistudio.panels.reads
  contracts:
    - scistudio.panels.descriptor.DESCRIPTOR_FIELDS
    - scistudio.panels.descriptor.PANEL_API_VERSION
    - scistudio.panels.reads.READ_OPERATIONS
  entry_points: []
  files:
    - docs/adr/ADR-052-addendum1.md
    - scripts/docs/build_panel_reference.py
    - scripts/docs/build_reference.py
    - src/scistudio/panels/sdk/**
    - src/scistudio/_user_guide/api-reference/panels-sdk.md
    - src/scistudio/_user_guide/api-reference/panels-renderers.md
    - src/scistudio/_user_guide/api-reference/panel-descriptor.md
  excludes: []

tests:
  - tests/docs/test_panel_reference.py
  - tests/panels/test_panel_descriptor.py
  - tests/panels/test_panel_read_operations.py
agent_editable: false
assisted_by:
  - "claude-code:claude-opus-5"

phase: implementation
tags: [api, public-contract, stability, documentation, panels]
owner: "@jiazhenz026"
co_authors: ["@claude"]
language_source: en
translations: []
---

# ADR-052 Addendum 1: The Panel Contract Is Public API With A Generated Reference

## 1. Decision Summary

ADR-052 defines the public API as the symbols in each canonical Python root's
`__all__`, marks each with a stability decorator, and generates the reference
from that code (Section 7). ADR-054 then added a contract authors depend on that
is not Python at all: the panel SDK (`window.scistudio`), the shared panel
components and stylesheets, and the `panel.json` and `panel.sample.json` files.
ADR-054 §3 already says this contract is public at the `provisional` tier and is
versioned through `api_version` and a versioned SDK path, because ADR-052's
decorators cannot mark a JSON schema or a JavaScript file. It does not say how
that contract is declared, marked, or documented, so today it exists only as
hand-written prose that drifts from the code.

This addendum brings the panel contract into ADR-052's model:

- the panel contract's public surface is declared in the files that implement it;
- its stability is `provisional`, recorded once for the whole contract, with the
  panel API version beside it;
- it is versioned by `api_version` and the SDK major path `sdk/<major>/`;
- its reference is generated from source, like the Python reference, and a test
  fails when the committed pages differ from a fresh render.

### 1.1 Problems Addressed

| Problem | Detailed section |
|---|---|
| ADR-052 §2 and §7 cover Python roots only; the panel contract has no declared public surface. | Section 3 |
| ADR-052 §5's decorators cannot mark a JavaScript file or a JSON schema, so the contract's stability is not recorded anywhere a reader of the reference sees it. | Section 4 |
| The relation between `api_version`, the SDK path, and compatibility is stated in ADR-054 but not tied to ADR-052's versioning. | Section 5 |
| The panel contract is documented only by hand (skills, agent reference, user guide), which drifts from the code. | Section 6 |

## 2. Scope

In scope: the panel SDK script, the component modules it ships beside
(`panel-ui.js`, `renderers.js` and the `renderer-*.js` modules it re-exports),
the stylesheets `panel.css` and `renderers.css`, the `panel.json` descriptor, the
`panel.sample.json` file, the read operations `read` accepts, and the pinned
library set served beside the SDK.

Out of scope: the host-side bridge message schema (a specification detail of
ADR-054, not an author contract); the Python API of `scistudio.panels`, which is
an ordinary canonical root under ADR-052 §3; rewriting the skills, user guide, or
agent reference, which link to the generated pages instead of restating them.

## 3. Declaring The Public Surface

The panel contract's surface is declared where it is implemented, by rules the
generator enforces rather than by a separate list:

- **SDK.** Every member of `window.scistudio` carries a JSDoc block naming it
  (`@member`). The members the script assigns and the members documented must be
  the same set; a member added without documentation, or documented but removed,
  fails generation.
- **Components.** The public components are the exports of `panel-ui.js` and the
  names `renderers.js` re-exports. Each needs a JSDoc description and documents
  its props; a documented prop the component does not take, or a destructured
  prop left undocumented, fails generation. Other named exports of a
  `renderer-*.js` module are helpers and not public.
- **Descriptor.** `panel.json` keys are declared by
  `scistudio.panels.descriptor.DESCRIPTOR_FIELDS`, and the validator's set of
  known keys is derived from that table, so a key cannot be accepted without
  being documented.
- **Reads.** Read operations and their parameters are declared by
  `scistudio.panels.reads.READ_OPERATIONS`, which is also the parameter
  allowlist the read route enforces.
- **Sample file.** `panel.sample.json` keys are declared by the SDK's `@sample`
  block and must match the keys the SDK reads.

## 4. Stability

The whole panel contract is `provisional` (ADR-052 §5): usable, and changeable in
a minor release with a changelog entry. Since there is no decorator to put on a
JSON key or a JavaScript function, the tier is recorded once, in the generator,
and stamped on every generated page together with the panel API version and the
SDK path. Per-member tiers and `Since` values are not recorded; when a part of
the contract becomes `stable`, a later addendum decides how that finer marking is
expressed.

## 5. Versioning

- `panel.json`'s `api_version` is `MAJOR.MINOR`. The host serves one major; a
  panel whose major it does not serve is refused with a diagnostic
  (ADR-054 §3). `scistudio.panels.descriptor.PANEL_API_VERSION` is the version
  the host serves, and the generator checks that the SDK reports the same one.
- The SDK and components live under `sdk/<major>/`. An incompatible change to
  the SDK, the components, or the descriptor is a new major under a new path; a
  compatible addition raises the minor.
- The generated pages are single-version, stamped with the panel API version,
  under the same deferral of multi-version hosting as ADR-052 §7.

## 6. Generated Reference And Freshness

`scripts/docs/build_panel_reference.py` renders three self-contained pages into
the packaged API reference, next to the Python pages and linked from its index:

- `panels-sdk.md` — `window.scistudio`, the operations and services per context
  (read from `PanelContext.provides`), the read operations, the error codes, and
  the pinned libraries;
- `panels-renderers.md` — the stylesheets, their theme tokens, and every public
  component with its props and defaults (defaults are read from the component
  signatures);
- `panel-descriptor.md` — the `panel.json` keys and rules and the
  `panel.sample.json` shape.

`scripts/docs/build_reference.py` calls this generator and adds the index section,
so the documentation site and the reference provisioned into projects include
the panel pages. The pages are generated artifacts under ADR-042's rule: they
are regenerated, never hand-edited. `tests/docs/test_panel_reference.py` renders
the pages and fails when the committed copies differ, and it exercises each drift
guard of Section 3.

The generator is plain Python reading JSDoc blocks with a small parser; it adds
no JavaScript toolchain, so it runs wherever the Python tests run.

## 7. Verification And Tooling Impact

- `tests/docs/test_panel_reference.py`: freshness of the three pages, the index
  links, the stability and version stamp, the read operations matching the host
  bridge's allowlist, and one test per drift guard.
- `tests/panels/test_panel_descriptor.py`: every documented key is accepted
  without a note, and every documented required key is required.
- `tests/panels/test_panel_read_operations.py`: each operation accepts its
  documented parameters and refuses others.
- `tests/docs/test_reference_language.py` already scans every page under the
  packaged reference for internal development markers, so the new pages are
  held to the same rule.

## 8. Consequences

- Hand-written panel documentation (the panel and MiniApp skills, the agent
  reference on renderer components and the block contract) can link to the
  generated pages instead of restating signatures.
- Changing the SDK, a component's props, a descriptor key, or a read parameter
  now requires regenerating the reference in the same change, or the freshness
  test fails.
- JSDoc in the SDK and component files becomes contract text and is held to the
  same writing rules as Python docstrings in the reference.

## 9. Alternatives Considered

- **TypeScript declaration files with a documentation tool such as TypeDoc.**
  Rejected for now: it adds a Node toolchain to the Python documentation build
  and CI jobs, and the SDK is a dependency-free script whose members are
  assigned at runtime per context, which a declaration file would describe but
  not check against the script.
- **A JSON Schema file for `panel.json`.** Rejected as a second source of truth
  beside the validator; deriving the known keys from `DESCRIPTOR_FIELDS` keeps a
  single table.
- **Keep hand-written contract pages and review them.** Rejected: the drift this
  addendum addresses already happened in that model.
