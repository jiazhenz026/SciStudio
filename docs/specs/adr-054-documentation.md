---
spec_id: adr-054-documentation
title: "ADR-054 Documentation Revision — The Architecture Document, The Developer Guides, And The Generated Reference"
status: Draft
feature_branch: docs/adr-054-documentation-spec
created: 2026-09-02
input: "Owner-directed live session (guided): author the documentation-revision spec for ADR-054. The architecture document needs revising and is reviewed section by section by the owner, so documentation is a spec of its own rather than a tail on each feature spec. List every document ADR-054 makes inaccurate, state what each must say afterwards, and sequence the revision behind the specs whose behaviour it describes."
owners:
  - "@jiazhenz026"
related_adrs:
  - 40
  - 42
  - 48
  - 51
  - 52
  - 53
  - 54
related_specs:
  - adr-048-developer-docs-refresh
  - adr-054-panel-contract
  - adr-054-notebook-dependency-analysis
  - adr-054-explore-session
  - adr-054-explore-frontend
  - adr-054-agent-enablement
scope:
  in:
    - The owner-controlled architecture document, revised section by section under the owner's review, with the CI approval label and the drift audit both satisfied.
    - The project tree, which declares a 1:1 correspondence with the architecture document.
    - The seven `docs/package-development/` guides, which teach the previewer contract and its ES-module panel form.
    - The generated API reference and the `mkdocs.yml` navigation that lists its module pages.
    - "`CHANGELOG.md` and the single `README.md` reference."
    - Documentation invariants in `tests/docs/` that fail when a guide teaches a form ADR-054 retired.
    - Sequencing the whole revision into tranches that follow the specs whose behaviour they describe.
  out:
    - The agent-facing teaching surface — the skill bundle and `src/scistudio/_agent_reference/**` — which belongs to the agent-enablement spec.
    - The ADR-048 and ADR-051 addenda, which carry the contract change and its governance transfer and belong to the panel-contract spec.
    - Any historical record — `docs/audit/**`, `docs/planning/**`, `docs/ai-developer/e2e/**`, and the ADRs and implemented specs themselves — which is preserved as written.
    - Deciding which architecture-document sections change; that is the owner's, taken document by document.
    - Product behaviour of any kind. This spec changes documents only.
governs:
  modules: []
  contracts: []
  entry_points: []
  files:
    - docs/specs/adr-054-documentation.md
    - docs/architecture/ARCHITECTURE.md
    - docs/architecture/PROJECT_TREE.md
    - docs/package-development/**
    - mkdocs.yml
    - tests/docs/test_block_development_docs.py
    - CHANGELOG.md
    - README.md
  excludes:
    - docs/user/reference/**
    - docs/user/llms.txt
    - docs/audit/**
    - docs/planning/**
    - docs/ai-developer/**
planned_governs:
  modules: []
  contracts: []
  entry_points: []
  files: []
  excludes: []
tests:
  - tests/docs/test_block_development_docs.py
  - tests/qa/test_architecture_drift.py
acceptance_source: adr
language_source: en
---

# ADR-054 Documentation Revision — The Architecture Document, The Developer Guides, And The Generated Reference

## 1. Change Summary

This spec comes from ADR-054 (Explore Sessions And One Contract For Interactive
Panels) and from an owner directive in a guided session: the architecture
document needs revising and is reviewed by the owner section by section, so
documentation is a spec of its own rather than a tail on each feature spec.

ADR-054 replaces the panel contract, adds the Explore Session as a notebook and
kernel over data that is packaged into a block when it is worth keeping, and
makes the Explore tab the one surface for every interaction. When its first spec
lands, documents that are accurate today begin describing a system that no
longer exists: the package-development guides teach package authors to write an
ES module against a previewer host API, the architecture document describes
previewers and interactive blocks as two systems and the interaction as a
modal, and the project tree carries neither the panel subsystem nor the explore
subsystem ADR-054 §9 introduces.

The change has three parts and one sequencing rule.

The **architecture document** is owner-controlled. `architecture_doc_guard`
(#2054) hard-fails an unapproved change in CI, and `architecture_drift.py`
audits the document's identifiers against generated repository facts. This spec
states how the revision is authorised and ordered, and supplies an inventory of
candidate sections for the owner's review; it does not propose what any section
should say.

The **package-development guides** teach the contract ADR-054 §3 replaces. Seven
files reference previewers, four substantively, and `previewers.md` is entirely
about the retired form.

The **generated reference** regenerates rather than being edited; the
`mkdocs.yml` navigation that lists its pages is hand-maintained and does not.

The sequencing rule is that the revision lands in **tranches behind the specs
whose behaviour they describe**. A single pass at the end would leave a window in
which a shipped contract and its documentation disagree, and would make the
drift audit unsatisfiable for any tranche describing modules not yet written.

This spec also adds the invariants that make the same rot fail a test next time.
`tests/docs/test_block_development_docs.py` already asserts that no guide teaches
`produced_type=`, an editable install, or a module-only entry point — each a
fossil of a migration that rotted once. The ES-module panel form joins them.

## 2. User Scenarios & Testing

### User Story 1 - A package author follows a guide that matches the shipped contract (Priority: P1)

As a package author, I open the package-development guides to add a previewer to
my package and find instructions for the contract that actually ships, so the
panel I write mounts instead of failing a version gate.

**Why this priority:** The panel-contract spec is the first ADR-054 spec to
merge. From that moment the guides teach a form the runtime refuses, and a
package author following them produces work that cannot load. Every other story
concerns accuracy; this one concerns a reader being actively misled into wasted
work.

**Independent Test:** Follow the panel guide end to end against a scratch
package, register the result, and confirm it loads in the product without
consulting the ADR or the source.

**Acceptance Scenarios:**

1. Given the panel guide after tranche A, when an author follows it to write a
   panel, then the document describes a self-contained HTML file, its capability
   declaration, and the tier directory it belongs in, and never an ES module
   mounted from a `module_url`.
2. Given an author who knows the previous vocabulary, when they search the guides
   for "previewer", then they find a statement that a displaying panel is what
   was previously called a previewer, rather than concluding the feature was
   removed.
3. Given `index.md`, `publishing.md`, `types.md`, and `architecture.md`, when a
   reader follows any link to the panel guide, then the link resolves and the
   target describes the current contract.
4. Given the three guides that define what a package is, when a reader compares
   them, then the entry-point declaration appears in one guide and the others
   link to it.

### User Story 2 - The owner revises the architecture document section by section (Priority: P1)

As the repository owner, I review the architecture document one section at a
time and decide what changes, so I authorise text I have read rather than a
change proposed on my behalf.

**Why this priority:** The document is owner-controlled and enforced as such.
The guard exists because PR #2036 carried a thirty-line addition through every
check green and was caught only by the owner reading the diff. A spec that
proposed architecture text would reproduce exactly the situation the guard was
added to prevent.

**Independent Test:** Open one architecture tranche and confirm it touches only
sections the owner approved for that tranche, carries the approval label, and
passes the drift audit with no exclusion added.

**Acceptance Scenarios:**

1. Given this spec, when the owner reads its architecture section, then they find
   an inventory of candidate sections and no proposed wording for any of them.
2. Given an architecture-document PR, when CI runs, then the PR carries
   `admin-approved:architecture-doc` applied by an authorised maintainer or an
   administrator approval, and the guard passes on that provenance rather than on
   any other route.
3. Given an architecture tranche, when the drift audit runs, then every
   `scistudio.*` name and `src/scistudio/...` path in the changed text resolves
   against generated facts, with no exclusion added to make it pass.
4. Given a tranche whose text would need to name a module that has not landed,
   when the tranche is authored, then that sentence is deferred to the later
   tranche rather than written with the name omitted.

### User Story 3 - A reader of the generated reference sees the surface that exists (Priority: P2)

As anyone reading the API reference, I see pages for the modules that exist and
navigation entries that resolve, so the reference is trustworthy without
cross-checking the source.

**Why this priority:** The reference is generated and its correctness follows
from regenerating it. The failure is real but narrow — a stale page or a dangling
nav entry — and `mkdocs build --strict` catches the dangling case already.

**Independent Test:** Regenerate the reference after a public-surface change and
build the docs site with `--strict`; both succeed with no hand edit to any file
under `docs/user/reference/`.

**Acceptance Scenarios:**

1. Given a public symbol that ADR-054 moves between modules, when the reference
   is regenerated, then the symbol appears on the new module's page with its
   stability tier, and no file under `docs/user/reference/` was edited by hand.
2. Given a tranche that changes the public surface, when the docs site builds
   with `--strict`, then the build succeeds and every navigation entry points at
   a page the generator emitted.

### User Story 4 - A future author cannot quietly reintroduce the retired form (Priority: P2)

As a maintainer reviewing a documentation change two releases from now, I have a
test that fails when a guide teaches the retired panel form, so the rot this
spec is repairing does not recur unnoticed.

**Why this priority:** It prevents recurrence rather than repairing the present
state, so it ranks below the stories that repair it. The existing test module
shows the cost of omitting it: three prior migrations each needed an assertion
added after the fact.

**Independent Test:** Add a sentence teaching the retired form to any
package-development guide on a scratch branch and confirm the suite fails.

**Acceptance Scenarios:**

1. Given tranche A has landed, when any file under `docs/package-development/`
   describes a module export mounted from an asset URL as the way to write a
   panel, then `tests/docs/test_block_development_docs.py` fails.
2. Given a guide naming an entry-point group that no longer exists, when the
   suite runs, then it fails and names the file.
3. Given the new assertions, when a maintainer looks for the documentation
   invariants, then all of them are in one test module.

### Edge Cases

- **A tranche is opened before the spec it follows has merged.** The drift audit
  catches this for the architecture document. Nothing catches it for the guides,
  where a guide describing an unshipped contract passes every check. FR-030 is a
  rule, and reviewers enforce it.
- **The approval label is unavailable when a tranche is ready.** The tranche
  waits. Splitting the architecture change out of the tranche to unblock the rest
  is permitted only when the remaining content is independently correct.
- **A guide is renamed and an external link breaks.** The docs site has no
  redirect mechanism today. Resolved by the owner's answer to the open question
  on filenames before tranche A.
- **The reference generator changes during this work.** FR-023 and FR-024 state
  intent; the mechanism follows whatever the generator becomes.
- **A section appears in the §3 inventory that the owner decides not to change.**
  It stays as written. The inventory is a search result.

## 3. Requirements

### Functional Requirements

**Scope boundaries.**

**FR-001.** The work MUST NOT revise any file under `docs/audit/`,
`docs/planning/`, or `docs/ai-developer/e2e/`, nor any ADR body or implemented
spec, on the grounds that ADR-054 makes its content historical. A contract change
is recorded in an addendum instead.

**FR-002.** The work MUST NOT modify `src/scistudio/_agent_reference/**` or
`src/scistudio/_skills/**`, and MUST NOT author the ADR-048 or ADR-051 addenda;
those belong to the agent-enablement and panel-contract specs respectively.

**The architecture document.**

**FR-003.** Every PR that modifies `docs/architecture/ARCHITECTURE.md` MUST carry
`admin-approved:architecture-doc` applied by an authorised maintainer, or an
administrator approval, and MUST NOT satisfy `architecture_doc_guard` by any
other route.

**FR-004.** Architecture-document changes MUST be concentrated into as few PRs as
the tranching in §4.3 allows, so the number of authorisations the owner is asked
for equals the number of tranches rather than the number of edits.

**FR-005.** The inventory in §4.1 MUST be presented as a search result for owner
review, and no entry in it MUST be treated as an agreed change.

**FR-006.** Each architecture-document PR MUST state which sections it touches and
MUST NOT touch a section outside the set the owner approved for that tranche.

**FR-007.** Each architecture tranche MUST land after the spec whose behaviour it
describes has merged, and the drift audit MUST pass on the tranche without any
exclusion added for a name that does not yet resolve.

**FR-008.** Where a tranche would otherwise name a module that has not landed, the
sentence MUST be deferred to the tranche that follows that module rather than
written with the name omitted.

**The project tree.**

**FR-009.** `docs/architecture/PROJECT_TREE.md` MUST gain an entry for every module
ADR-054 §9 introduces, in the tranche in which that module lands, carrying the
same one-responsibility annotation as the surrounding entries.

**FR-010.** The project tree MUST amend or remove the entries for the frontend
modules the unified loader replaces, in the tranche that replaces them.

**FR-011.** The project tree MUST NOT be revised ahead of the architecture-document
section it corresponds to, so its own 1:1 claim stays true at every commit.

**Package developer documentation.**

**FR-012.** `docs/package-development/previewers.md` MUST be replaced by a
panel-authoring guide covering the capability declaration, the self-contained
document form, the on-disk layout of ADR-054 §3.3, the four tiers and how each
registers a panel, how a panel is found in each of the three cases and how the
required capability filters the candidates, the statement whitelist for emitted
code, and how a person edits a panel (ADR-054 §3.5).

**FR-013.** The replacement MUST state that a displaying panel is what was
previously called a previewer.

**FR-014.** Every relative link into the replaced page from `index.md`,
`publishing.md`, `types.md`, and `architecture.md` MUST be updated in the same
change, and `test_relative_links_resolve` MUST pass.

**FR-015.** `architecture.md` and `publishing.md` MUST describe the package's
registration surface using the vocabulary ADR-054 §9.3 settles, and MUST NOT
present the display and produce capabilities as separate extension points.

**FR-016.** Entry-point examples MUST name the current group and MUST continue to
use callable factories, which
`test_entry_point_examples_use_callable_factories` already enforces.

**FR-017.** Asset-packaging guidance MUST describe the file types the unified
contract serves, which ADR-054 §10.1 adds to the asset whitelist.

**FR-018.** The entry-point declaration MUST appear in exactly one
package-development guide, with the others linking to it, since three
independent descriptions of one fact is how the present inconsistency arose.

**FR-019.** `blocks.md` MUST present the packaged notebook block as one of the
block shapes an author may choose, in the same neutral register the interactive,
App, and Code shapes are presented in today, MUST state the criterion ADR-054
§4.6 and §8.1 give for choosing it — the computation is not yet understood — and
MUST state that an Explore Session itself is not a block and that the
`on_new_input` setting of ADR-054 §4.7 applies to every block with an
interaction.

**FR-020.** `blocks.md` MUST NOT teach the panel document form and MUST link to the
panel guide.

**FR-021.** `types.md` MUST keep its statement that panels attach to types, in the
settled vocabulary.

**FR-022.** `tutorials.md`'s capability list MUST name the current surfaces.

**Generated reference and navigation.**

**FR-023.** Reference pages MUST be regenerated rather than hand-edited, and
`scripts/docs/build_reference.py` MUST remain the only writer of files under
`docs/user/reference/`.

**FR-024.** Where ADR-054 moves a public symbol between modules, the docstring and
`scistudio.stability` decorator MUST move with it, so the regenerated page is
correct without any edit to the page.

**FR-025.** `mkdocs.yml` navigation MUST gain an entry for each new public module
page and lose the entry for any page the generator no longer produces, in the
tranche that changes the surface.

**FR-026.** `mkdocs build --strict` MUST pass after each tranche.

**Release and entry documents.**

**FR-027.** `CHANGELOG.md` MUST carry an entry per tranche in user-facing terms,
and the entry for the panel-contract tranche MUST state that package-provided
panels require migration.

**FR-028.** The single `README.md` reference MUST be updated to the settled
vocabulary in the panel-contract tranche.

**Sequencing.**

**FR-029.** A public-surface change and its regenerated reference MUST land in the
same PR, never as a follow-up.

**FR-030.** A tranche MUST NOT be opened before the spec it follows has merged.

**Documentation invariants.**

**FR-031.** A test MUST fail when any file under `docs/package-development/`
teaches the retired panel module form — a module export mounted from a
`module_url` under the block-panel asset route — after tranche A has landed.

**FR-032.** A test MUST fail when a package-development guide names an entry-point
group that does not exist in the current contract.

**FR-033.** The new assertions MUST live in
`tests/docs/test_block_development_docs.py` rather than a new module.

**FR-034.** The invariants MUST scope to `docs/package-development/` and MUST NOT
assert over `docs/audit/`, `docs/planning/`, or `docs/ai-developer/e2e/`, whose
content is historical by FR-001.

**Checks.**

**FR-035.** Each tranche MUST pass `tests/docs/test_block_development_docs.py`,
`tests/qa/test_architecture_drift.py`, `mkdocs build --strict`, and the gate's
`full_audit` before it is opened, and MUST NOT add an exclusion to any of them to
make a tranche pass.

**The agent tool table.**

**FR-036.** The architecture document's table of agent tools MUST gain a row for
each tool the agent-enablement spec adds, in tranche C, because the document is
guarded and the agent-enablement spec's catalog test excludes it until this
tranche lands.

### Key Entities

Not applicable. This spec changes documents only and introduces no data entity,
persisted schema, or public data shape.

## 4. Implementation Plan

### 4.1 Technical Approach

The work is a document revision carried out in four tranches, each following the
merge of the ADR-054 spec whose behaviour it describes. Nothing here changes
product behaviour; the only executable artefacts are two test assertions.

**Ordering is imposed by mechanism, not preference.** `architecture_drift.py`
extracts dotted `scistudio.*` names, `src/scistudio/...` paths, and Python
callables from the architecture document's prose and fenced blocks and audits
them against generated repository facts. A section written ahead of the code it
describes names modules that do not resolve, and the audit reports drift. The
architecture revision therefore cannot lead the implementation, and the same
tranching is applied to the guides so that no document in the set is ahead of
another.

**The architecture document's scope is the owner's.** This spec supplies an
inventory of sections that reference the subject matter ADR-054 changes, so the
owner's review starts from a list rather than a whole document. The inventory is
a search result over the current text and asserts nothing about need.

| Section | Why it appears in the inventory |
|---|---|
| §3 Architecture Overview | Describes the subsystems, including preview |
| §4.6 Version Control | Branch usage and what is and is not git content, which ADR-054 §4.5 and §6.6 extend |
| §5 Layer 2: Block System | The interaction capability, which ADR-054 §4.2 routes through the Explore tab; the packaged notebook block and the `on_new_input` setting of §4.6 and §4.7 |
| §7 Layer 4: AI Agents | The skill bundle and the tool table, which the agent-enablement spec changes |
| §9 Layer 6: Frontend | The panel host, the tab model with the Explore tab, and the retired interactive modal |
| §11 Project Workspace Structure | Per-project and per-user drop-in directories, the `explore/` directory, and packaged blocks under `blocks/` |
| §12 Extensibility | Registration surfaces and tiers, including per-tier panel registration |
| §14 Dependencies List, §15 Technology Stack | A resident kernel adds `ipykernel` and `jupyter_client` as runtime dependencies |

**Invariants land before the prose they protect.** The FR-031 and FR-032
assertions are written with tranche A rather than after it, so the guides are
rewritten into a form something checks.

### 4.2 Affected Files

| File or glob | Action | Rationale |
|---|---|---|
| `docs/specs/adr-054-documentation.md` | create | This spec |
| `docs/architecture/ARCHITECTURE.md` | modify | Sections the owner approves per tranche (§4.1 inventory) |
| `docs/architecture/PROJECT_TREE.md` | modify | Its own header claims 1:1 correspondence with the architecture document (FR-009 to FR-011) |
| `docs/package-development/previewers.md` | delete | Replaced by the panel guide (FR-012) |
| `docs/package-development/panels.md` | create | The panel-authoring guide; filename subject to the open question in §6 |
| `docs/package-development/architecture.md` | modify | Registration surface, package directory, entry point (FR-015, FR-016) |
| `docs/package-development/publishing.md` | modify | Package definition, entry-point declaration, asset packaging (FR-015 to FR-018) |
| `docs/package-development/index.md` | modify | Package definition, entry-point table, navigation (FR-014, FR-018) |
| `docs/package-development/types.md` | modify | Vocabulary (FR-021) |
| `docs/package-development/blocks.md` | modify | The packaged notebook block shape (FR-019, FR-020) |
| `docs/package-development/tutorials.md` | modify | Capability list (FR-022) |
| `docs/user/reference/**` | generate | Regenerated by `scripts/docs/build_reference.py` (FR-023) |
| `mkdocs.yml` | modify | Navigation entries for module pages (FR-025) |
| `CHANGELOG.md` | modify | One entry per tranche (FR-027) |
| `README.md` | modify | Single vocabulary reference (FR-028) |
| `tests/docs/test_block_development_docs.py` | modify | FR-031 and FR-032 assertions |

### 4.3 Implementation Sequence

| Task | Title | Story | Files | Depends on | Verification |
|---|---|---|---|---|---|
| T-001 | Resolve the open questions in §6 that block tranche A | US1, US2 | — | — | Answers recorded in this spec |
| T-002 | Add the FR-031 and FR-032 assertions | US4 | `tests/docs/test_block_development_docs.py` | T-001 | Suite fails on a seeded violation and passes on the current tree |
| T-003 | Write the panel guide and delete the previewer guide | US1 | `docs/package-development/panels.md`, `previewers.md` | T-001, panel-contract spec merged | Link test passes; FR-031 assertion passes |
| T-004 | Update the four cross-referencing guides | US1 | `index.md`, `publishing.md`, `types.md`, `architecture.md` | T-003 | Link and entry-point tests pass |
| T-005 | Update README and CHANGELOG for tranche A | US1 | `README.md`, `CHANGELOG.md` | T-003 | Review |
| T-006 | Regenerate the reference and update navigation for tranche A | US3 | `docs/user/reference/**`, `mkdocs.yml` | panel-contract spec merged | `mkdocs build --strict` passes |
| T-007 | Revise the architecture sections the owner approves for panels | US2 | `ARCHITECTURE.md` | Owner approval, T-003 | Drift audit passes; PR carries the label |
| T-008 | Update the project tree for tranche A | US2 | `PROJECT_TREE.md` | T-007 | Review against the architecture diff |
| T-009 | Update `blocks.md` and `tutorials.md` for packaged notebook blocks and sessions | US1 | `blocks.md`, `tutorials.md` | explore-session spec merged | Link test passes |
| T-010 | Regenerate the reference and update navigation for tranche B | US3 | `docs/user/reference/**`, `mkdocs.yml` | explore-session spec merged | `mkdocs build --strict` passes |
| T-011 | Revise the architecture and project-tree sections the owner approves for sessions, packaging, and the Explore tab | US2 | `ARCHITECTURE.md`, `PROJECT_TREE.md` | Owner approval, T-009, explore-frontend spec merged | Drift audit passes; PR carries the label |
| T-012 | Update CHANGELOG for tranche B | US1 | `CHANGELOG.md` | T-009 | Review |
| T-013 | Revise the architecture section the owner approves for the agent layer, add the tool-table rows (FR-036), and CHANGELOG | US2 | `ARCHITECTURE.md`, `CHANGELOG.md` | Owner approval, agent-enablement spec merged | Drift audit passes; PR carries the label; the catalog test includes the document again |

Tranche A is T-002 through T-008, tranche B is T-009 through T-012, tranche C is
T-013. Reference regeneration is folded into the tranche that changes the surface
(FR-029) rather than being a tranche of its own.

### 4.4 Verification Plan

Every check this work can be verified by already exists and is wired.

`tests/docs/test_block_development_docs.py` covers frontmatter validity,
relative-link resolution, entry-point form, and the two assertions this spec
adds. `tests/qa/test_architecture_drift.py` covers the architecture document's
identifiers against generated facts. `mkdocs build --strict` covers navigation
entries against generated pages. The gate's `full_audit` covers doc drift and
closure across the repository, and `gate_record check` runs it.

Manual verification is limited to what a test cannot express: an author following
the panel guide end to end against a scratch package (US1 independent test), and
the owner's own reading of each architecture diff (US2).

No tranche adds an exclusion to any of these checks to pass (FR-035).

### 4.5 Risks And Rollback

**The architecture revision stalls behind approval.** Every tranche touching it
needs an authorisation the owner supplies. If tranches queue, the guides move and
the architecture document does not, producing the disagreement this spec exists
to prevent by way of process rather than neglect. FR-004 mitigates by minimising
the number of asks; it does not remove the dependency. Rollback is to land the
non-architecture content of the tranche and carry the architecture change into
the next one.

**A tranche lands ahead of its spec.** Caught for the architecture document by
the drift audit and by nothing for the guides, where a guide describing an
unshipped contract passes every check. FR-030 is a rule enforced at review.

**The invariants are written to pass rather than to hold.** An assertion matching
one exact phrase is satisfied by rewording. FR-031 matches the shape — a module
export mounted from an asset URL — rather than a sentence.

**Vocabulary drifts back.** Three guides currently define a package
independently, which is how the present inconsistency arose. FR-018 collapses
them to one definition with links; nothing enforces that afterwards.

**Rollback in general.** Every change in this spec is a document revert. The only
executable artefacts are two test assertions, which revert independently of the
prose they protect.

## 5. Success Criteria

### Measurable Outcomes

**SC-001.** After tranche A, zero files under `docs/package-development/` describe
a panel as a module export mounted from an asset URL, measured by the FR-031
assertion passing on the tree.

**SC-002.** After every tranche, every relative link in `docs/package-development/`
resolves, measured by `test_relative_links_resolve`.

**SC-003.** Every architecture-document tranche passes
`tests/qa/test_architecture_drift.py` with the same exclusion set the repository
carried before this work began.

**SC-004.** After every tranche, `mkdocs build --strict` exits zero.

**SC-005.** Every PR modifying `docs/architecture/ARCHITECTURE.md` carries
`admin-approved:architecture-doc` or an administrator approval, measured by the
`architecture_doc_guard` result in CI being a pass on that provenance.

**SC-006.** No tranche PR is opened before the merge of the spec it follows,
measured by comparing merge and open timestamps.

**SC-007.** The entry-point declaration appears in exactly one file under
`docs/package-development/`, measured by a count of its occurrences.

**SC-008.** No file under `docs/user/reference/` is modified by any commit in this
work other than by `scripts/docs/build_reference.py` output, measured by
inspecting each tranche's diff.

## 6. Assumptions

**A-001.** The panel-contract, dependency-analysis, explore-session,
explore-frontend, and agent-enablement specs land in the order ADR-054 §10.1
gives, and each merges before its documentation tranche opens. _Source: adr._

**A-002.** `architecture_doc_guard` and `architecture_drift.py` behave as read at
the time of writing: the guard hard-fails without the label, and the drift audit
resolves identifiers against generated facts. _Source: existing-system._

**A-003.** The generated reference remains generated by
`scripts/docs/build_reference.py`. If the generator changes during this work,
FR-023 and FR-024 describe the intent and the mechanism follows the generator.
_Source: existing-system._

**A-004.** No document in scope is translated. `README.zh-CN.md` carries no
reference to the affected vocabulary, so it is out of scope on that basis rather
than by policy. _Source: inferred._

**A-005.** The owner reviews the architecture document section by section and
decides the scope of each tranche, as directed in the originating session.
_Source: owner._

**A-006.** The three unverified items in the originating session —
`docs/specs/frontend-block-palette.md`'s relevance, the extent of
`_agent_reference/data-types.md`'s change, and the location of the `README.md`
reference — are resolved by T-001 before tranche A. The first would add a file to
§4.2; the second belongs to the agent-enablement spec either way.
_Source: spec._
