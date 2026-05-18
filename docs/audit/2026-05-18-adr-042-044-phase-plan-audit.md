# ADR-042 to ADR-044 Phase Plan and Implementation Organization Audit

Date: 2026-05-18
Mode: doc review
Scope: `docs/adr/ADR-042.md`, `docs/adr/ADR-043.md`, `docs/adr/ADR-044.md`
Audit focus: reachability of the implementation plan, phase organization, ADR-level contradictions, unrealistic sequencing, and missing ADR-level decisions.

## Review Lens

This audit does not treat "not implemented yet" as a defect. ADR-042 through
ADR-044 are drafts, and an ADR is allowed to name future modules, tools, and
files.

The review flags problems only when the plan itself is unreachable, internally
contradictory, or underspecified at ADR granularity. In other words, this is
not asking ADR-042/043/044 to become implementation specs; it is asking them to
define a coherent implementation strategy that later specs and tasks can
execute.

## Executive Summary

ADR-042 through ADR-044 should remain Draft until their phase plan is
reorganized. The main design direction is coherent: machine-enforced QA,
governance hardening, and a real documentation layer. The current
implementation plan, however, is not reachable as written.

Highest-impact issues:

- Phase 0 has three competing definitions once ADR-043 and ADR-044 are added.
- Phase 1 expands from "QA scaffold in about two weeks" into a multi-subsystem
  platform build without a revised critical path.
- Phase 2 turns every report-only tool into a hard gate before Phase 3 cleanup
  can merge, creating a red-CI deadlock under normal branch protection.
- ADR-044 creates stub documentation in Phase 1, flips doc checks in Phase 2,
  and only fills the real content in Phase 3.
- The addenda repeatedly say "the addendum wins" instead of amending concrete
  sections and publishing a single consolidated phase contract.
- The ADRs conflate planned artifacts with currently enforceable `governs`
  closure, which makes self-validation ambiguous.

Recommended disposition: block promotion beyond Draft until P0/P1 items are
resolved or explicitly rescheduled.

## Current Repo Reality Used As Context

The following context matters for phase reachability, not as criticism of a
draft ADR:

- `src/scieasy/qa/` does not exist.
- `docs/contributing/`, `docs/user/`, `docs/prod-agent/`, `docs/doc-guide/`,
  and `docs/zh-CN/` do not exist.
- `MAINTAINERS`, `docs/identity/humans.yml`, `.governance-paths.yaml`, and
  `docs/facts/generated.yaml` do not exist.
- Current `.workflow/schema.json` has the existing six-stage gate only.
- Current `AGENTS.md` and `CLAUDE.md` are 778 lines each, not the planned
  sub-200-line root plus subtree hierarchy.
- Current `.github/CODEOWNERS` is a short hand-authored file, not generated
  from `.governance-paths.yaml`.

These gaps are acceptable for Draft ADRs. They become problems only where the
phase plan assumes the gaps are already closed or closes them in an impossible
order.

## P0 Findings

### P0.1 The cascade has no single authoritative Phase 0

Evidence:

- ADR-042 says Phase 0 deliverables are ADR-042, umbrella issue, SpecKit
  specs, feature-freeze announcement, and pre-implementation contradiction
  audit (`ADR-042.md:2749-2763`).
- ADR-043 adds Phase 0 deliverables: ADR-043 accepted alongside ADR-042,
  `.governance-paths.yaml`, and generated CODEOWNERS (`ADR-043.md:1408-1417`).
- ADR-044 adds Phase 0 acceptance of ADR-044 alongside ADR-042/043
  (`ADR-044.md:1004-1008`).
- ADR-043 and ADR-044 both state that addenda win over the main ADR where
  they collide (`ADR-043.md:144-146`, `ADR-044.md:186-193`).

Impact:

There is no one place a future implementer can read to know when Phase 0 is
complete. ADR-042's "Phase 0 ends when" condition is no longer sufficient, but
the addenda do not replace it with a consolidated condition.

ADR-level fix:

Add a consolidated "ADR-042 cascade phase contract" section, either in ADR-042
or in a short coordinating addendum. It should define Phase 0 once for the
entire ADR-042/043/044 bundle and list the minimum exit criteria:

- ADR-042, ADR-043, and ADR-044 reviewed together.
- One umbrella tracking issue populated in all three frontmatters.
- One accepted phase plan for the whole cascade.
- Explicit decision on whether `.governance-paths.yaml` and CODEOWNERS are
  Phase 0 artifacts or Phase 1 artifacts.

### P0.2 Phase 1 is oversubscribed and no longer credible at the stated scale

Evidence:

- ADR-042 describes Phase 1 as "Tooling scaffold (report-only)" in about two
  weeks (`ADR-042.md:2765-2787`).
- ADR-043 adds implementation tracker tooling, phase gate validator,
  governance hard-block tooling, test-quality tooling, hook/path-rule
  migration, required AGENTS sections, and `InstructionsLoaded` audit
  (`ADR-043.md:1418-1423`).
- ADR-044 adds doc frontmatter schemas, doc lint tools, workflow/skill sync
  tools, Sphinx config, custom directives, all generators, and skeletons for
  roughly forty docs (`ADR-044.md:1009`).
- ADR-042 itself already acknowledges about 20 tools, about 15 custom scripts,
  and about 5 CI workflows as a negative consequence (`ADR-042.md:2993-3000`).

Impact:

After ADR-043 and ADR-044, Phase 1 is not a scaffold phase. It is a large
platform build across schemas, audit engines, CI, docs infrastructure,
agent-instruction hierarchy, governance policy, mutation testing, translation,
and Sphinx generation. The phase still has the original duration and exit
wording, so the plan underestimates both work and dependency risk.

ADR-level fix:

Split Phase 1 into an ordered implementation ladder. For example:

- Phase 1A: schemas and phase-aware frontmatter model.
- Phase 1B: passive audit report generation.
- Phase 1C: ownership/identity bootstrap.
- Phase 1D: docs build skeleton and generator proof-of-concept.
- Phase 1E: governance checks in report-only mode.
- Phase 1F: test-quality tooling in report-only mode.

The ADR does not need task-level detail, but it must expose the critical path
and make clear which pieces can run in parallel.

### P0.3 Phase 2 creates a red-CI deadlock before Phase 3 can clean up

Evidence:

- ADR-042 rejects baselines and says CI is red from Phase 2 until Phase 3
  cleanup completes (`ADR-042.md:366-371`, `ADR-042.md:423-438`).
- Phase 2 toggles every tool from report-only to fail-on-error
  (`ADR-042.md:2796-2801`).
- Phase 3 is when existing violations are resolved and "full audit returns 0
  errors" (`ADR-042.md:2801-2817`).
- ADR-042 also requires branch protection through a required check
  (`ADR-042.md:2299-2305`).

Impact:

If all checks are hard-blocking in Phase 2 and the repository has known
repo-wide violations, then ordinary Phase 3 cleanup PRs cannot merge because
CI remains red for violations they have not yet fixed. The plan says "CI is
red" as if that is merely uncomfortable, but under branch protection it is a
merge deadlock.

ADR-level fix:

Pick one of these strategies explicitly:

- Scope Phase 2 hard gates to "no new violations in changed files" while
  repo-wide violations remain report-only.
- Use cleanup-track labels with tool-owned allowlists that expire per subtrack.
- Merge all cleanup through one protected stabilization branch with a dedicated
  rule set, then flip gates only after the branch is clean.
- Keep zero-tolerance as the end state, not the Phase 2 merge policy.

The ADR can still reject permanent baselines, but it needs a mergeable cleanup
path.

### P0.4 ADR-044 flips documentation gates before the real documents exist

Evidence:

- ADR-044 Phase 1 creates directory skeletons with stub/placeholder content
  for every listed file (`ADR-044.md:1009`).
- ADR-044 Phase 2 flips all doc-side checks to fail-on-error
  (`ADR-044.md:1011`).
- ADR-044 Phase 3 fills all stub workflow, user, prod-agent, and doc-guide
  content (`ADR-044.md:1012`).
- ADR-044 also requires workflow-doc to skill-pointer closure and user-doc
  coverage closure (`ADR-044.md:917-928`).

Impact:

The plan creates placeholders, makes doc checks blocking, and only then writes
the content those checks are meant to validate. That is another deadlock unless
the checks ignore placeholder docs, but the ADR does not define such a staging
rule.

ADR-level fix:

Move either the gate flip or the content fill:

- Option A: Phase 1 creates only schemas and one exemplar doc per category;
  Phase 3 writes the full doc set; Phase 4 flips doc closure hard gates.
- Option B: Phase 1 creates full minimum viable content, not placeholders;
  Phase 2 can then hard-gate docs.

Do not make placeholder content subject to production-grade closure checks
without a phase-aware exception.

### P0.5 "Addendum wins" is an unsafe ADR organization rule

Evidence:

- ADR-043 says it is not a supersession, but where it collides with ADR-042,
  the addendum wins (`ADR-043.md:144-146`).
- ADR-044 repeats the same pattern for ADR-042/043 (`ADR-044.md:186-193`).
- ADR-042 positions itself as the canonical template and rule source
  (`ADR-042.md:196-201`, `ADR-042.md:2950-2959`).

Impact:

This makes the authoritative plan depend on recency rather than explicit
section amendments. It is especially risky because the addenda modify phase
organization, governance semantics, docs scope, and meta-compliance. A reader
cannot tell whether ADR-042 section 26 remains binding without manually
merging three documents.

ADR-level fix:

Replace "the addendum wins" with a bounded amendment model:

- Each addendum lists exact ADR-042 sections it amends.
- Each amended section says whether it is extended, replaced, or constrained.
- A consolidated implementation-plan table is generated or maintained as the
  operational source of truth.

## P1 Findings

### P1.1 Planned artifacts are mixed with currently enforceable `governs`

Evidence:

- ADR-042/043/044 frontmatter declares `is_code_implementation: true` and
  large `governs` and `tests` lists (`ADR-042.md:15-120`,
  `ADR-043.md:15-98`, `ADR-044.md:15-108`).
- ADR-042 says `governs.contracts` must resolve to real symbols as a
  meta-recursion requirement, while Phase 1 creates many of those symbols
  (`ADR-042.md:442-452`).
- The bootstrap exemption covers hardcoded facts, non-importable contracts,
  and examples, but not missing files or missing tests (`ADR-042.md:266-285`).

Impact:

The ADRs use `governs` both as "future implementation surface" and "enforced
ownership closure." That makes self-validation ambiguous before Phase 1 and
dangerous after Phase 1 if planned files are still absent.

ADR-level fix:

Introduce an ADR-level distinction between planned and enforced scope:

- `governs`: artifacts already under governance and subject to closure.
- `planned_governs` or `implementation_surface`: artifacts this ADR intends to
  create in named phases.
- Tracker entries determine when planned artifacts graduate into `governs`.

This is an ADR-level modeling decision, not a schema-detail request.

### P1.2 Workflow v2 migration is not sequenced through the existing gate

Evidence:

- ADR-042 defines Workflow v2 as seven stages and says Phase 1 ships v2 while
  Phase 2 deprecates v1 entirely (`ADR-042.md:1943-2090`).
- The current repository gate uses six stages in `.workflow/schema.json`.
- The repository instructions still require the current six-stage workflow for
  every change.

Impact:

The project must use Workflow v1 to implement Workflow v2. The ADR does not
explain compatibility for active workflow state, branch policy during the gate
migration, or whether v1 and v2 coexist during Phase 1.

ADR-level fix:

Add a migration decision:

- v1 remains authoritative until the v2 PR is merged.
- v2 initially runs in shadow/report-only mode against v1 events.
- active v1 sessions either complete under v1 or are migrated by a one-time
  state converter.
- v1 is deprecated only after a clean shadow run.

### P1.3 Phase 1.5 is a decision point without a decision owner or outcomes

Evidence:

- ADR-042 Phase 1.5 says to halt and discuss baseline findings, and if there
  are more than 5,000 critical errors, revisit zero tolerance
  (`ADR-042.md:2790-2794`).

Impact:

Phase 1.5 is the only explicit opportunity to change the enforcement strategy,
but it does not define who decides, what alternatives are allowed, how a change
is recorded, or how the phase resumes. A future agent cannot execute "halt and
discuss" as a governed phase.

ADR-level fix:

Define Phase 1.5 as an ADR decision checkpoint:

- required artifact: baseline audit report;
- required reviewer: project owner or Tier-2 maintainer;
- allowed outcomes: proceed, split phases, adopt temporary changed-file-only
  gating, or publish an addendum;
- explicit rule: any change to zero-tolerance policy requires an addendum.

### P1.4 Feature freeze is not defined tightly enough for a multi-week cleanup

Evidence:

- ADR-042 Phase 0 announces feature freeze (`ADR-042.md:2758-2760`).
- Phase 3 is a 4-8 week cleanup sprint with no feature work
  (`ADR-042.md:2801-2817`).

Impact:

The ADR does not define whether bug fixes, CI fixes, doc audits, hotfixes,
ADR corrections, dependency updates, or security fixes are allowed during the
freeze. Because Phase 3 may last weeks, this is too vague for repo governance.

ADR-level fix:

Add a freeze policy at ADR level:

- allowed: hotfixes, CI unblockers, security fixes, and cleanup-track PRs;
- blocked: new user-visible features and new governance scope;
- exception path: issue label plus Tier-2 approval;
- interaction with hotfix mode and existing active branches.

### P1.5 Enforcement timing is inconsistent across tool families

Evidence:

- ADR-042 says every tool flips fail-on-error in Phase 2
  (`ADR-042.md:2796-2801`).
- ADR-043 says mutation testing is introduced in Phase 1 but enforced in
  Phase 3 (`ADR-043.md:761-779`, `ADR-043.md:971-989`).
- ADR-043 says weakened-CI is included in Phase 2
  (`ADR-043.md:1424-1425`).
- ADR-044 says all doc-side checks flip in Phase 2 (`ADR-044.md:1011`).

Impact:

The phase plan lacks a per-tool enforcement matrix. "All tools flip in Phase
2" conflicts with specific tools that are intentionally delayed to Phase 3 or
Phase 4.

ADR-level fix:

Add a compact table with one row per tool family:

- report-only phase;
- changed-files hard-gate phase;
- repo-wide hard-gate phase;
- permanent cron phase.

This is appropriate ADR granularity and would prevent future specs from
guessing.

### P1.6 Phase 4 truth shift is underspecified

Evidence:

- ADR-042 says Phase 4 removes transitional language, shifts to permanent
  status-based arbitration, attaches revalidation, and tags
  `phase-4-complete` (`ADR-042.md:2819-2830`).
- ADR-042 also says no tag may be created until revalidation passes and CI
  reverts early tags (`ADR-042.md:2828-2832`, `ADR-042.md:2931-2948`).

Impact:

Phase 4 is supposed to change the repository's source-of-truth model, but it
does not define who has authority to declare the shift, how concurrent ADRs are
handled, or what happens if only part of the cascade validates. The tag-policy
detail is lower-level than the missing decision: what constitutes acceptance of
the truth shift?

ADR-level fix:

Define Phase 4 as a governance decision:

- required inputs: 0-error full audit, tracker all verified, accepted addenda
  reconciled, generated templates committed;
- required approver: project owner/Tier-2 maintainer;
- allowed failure path: remain in transitional mode and publish addendum;
- output: one PR plus tag after merge.

### P1.7 Self-modification and errata rules conflict with the bootstrap model

Evidence:

- ADR-042 has a self-exemption window for its first PR
  (`ADR-042.md:2879-2884`).
- ADR-043 says ADR-042 and ADR-043 self-modifications still require full
  governance workflow, monotonic check, contradiction audit, Tier-2 approval,
  and governance log entry (`ADR-043.md:721-754`).

Impact:

The drafts do not say which rule applies while the ADR cascade itself is still
being corrected pre-acceptance. A typo-only or audit-driven correction to
ADR-042/043/044 could be interpreted as both exempt bootstrap work and a fully
governed self-modification.

ADR-level fix:

Add a "pre-acceptance errata" rule:

- before acceptance, corrections to the ADR cascade are governed by current
  repository gates and human review, not by unimplemented ADR-042 governance;
- after acceptance, ADR-043 self-modification rules apply.

### P1.8 ADR-044's user-doc coverage rule is too broad for the first hard gate

Evidence:

- ADR-044 extends drift class d to every public class/function/CLI command/HTTP
  endpoint/entry point missing from user docs (`ADR-044.md:906-928`).
- ADR-044 Phase 2 flips all doc-side checks before Phase 3 content fill
  (`ADR-044.md:1011-1012`).

Impact:

At ADR level, the problem is not that API reference coverage is bad. The
problem is that the phase plan gives no staged API classification boundary.
Without one, the first hard gate will reward generated symbol dumping and make
cleanup noisy.

ADR-level fix:

Stage the coverage rule:

- first hard gate: stable public classes, CLI commands, HTTP endpoints, block
  entry points, and plugin contracts;
- later gate: exported helper functions after `__all__` and public/private API
  policy are normalized.

### P1.9 Deferred items lack a tracking model despite the ADR's own rule

Evidence:

- ADR-043 lists known gaps tracked only as "Future addendum" or similar
  placeholders (`ADR-043.md:1519-1527`).
- ADR-044 defers multi-version docs, translations beyond zh-CN, interactive
  try-it, plot regression, and migration work without concrete tracking
  artifacts (`ADR-044.md:195-202`).
- All three ADR frontmatters have `tracking_issue: null`
  (`ADR-042.md:13`, `ADR-043.md:13`, `ADR-044.md:13`).

Impact:

The cascade is about traceability, but the implementation plan itself defers
work without a durable tracking mechanism. This is not a request for every
future feature to be specified; it is a request for the ADR-level tracking
contract to exist.

ADR-level fix:

Create one umbrella issue and use it in all three frontmatters. For deferred
items, require either:

- issue number;
- named future addendum with owner and trigger;
- explicit "not accepted as requirement" note.

## P2 Findings

### P2.1 The phase numbering language is inconsistent

Evidence:

- ADR-042 says the regime is delivered in "six phases" but lists Phase 0,
  Phase 1, Phase 1.5, Phase 2, Phase 3, Phase 4, and Phase 5
  (`ADR-042.md:357-364`).
- ADR-042 section 26 is titled "Phase 0-5 Timeline" while Phase 1.5 is a
  separate gate (`ADR-042.md:2749-2794`).

Impact:

Minor by itself, but it matters because ADR-043 introduces a phase gate
validator. A machine-readable phase model should not inherit ambiguous prose.

ADR-level fix:

Call this a "seven-step phased rollout" or make Phase 1.5 a checkpoint within
Phase 1 rather than a standalone phase.

### P2.2 ADR-level and spec-level detail are mixed unevenly

Evidence:

- The ADRs include detailed code sketches for pydantic classes, CI YAML, and
  Sphinx extensions while leaving phase decision points underdefined.
- Examples include the frontmatter schemas (`ADR-042.md:466-765`), governance
  schemas (`ADR-043.md:578-604`), and docs schemas (`ADR-044.md:339-515`).

Impact:

The documents are detailed in places where a later spec can decide exact field
shape, but too vague in places where the ADR must decide ownership, sequencing,
and enforcement timing.

ADR-level fix:

Move detailed schema/API sketches into follow-up specs or mark them
illustrative. Use ADR space to decide:

- which contracts exist;
- who owns them;
- when they become enforceable;
- what phase exits mean.

### P2.3 Phase ownership is spread across agents and tools without a clear accountable role

Evidence:

- ADR-042 assigns Phase 0 deliverables to `@claude + @jiazhenz026`,
  `@jiazhenz026`, and `$scieasy-adr-auditor` (`ADR-042.md:2751-2763`).
- ADR-043 and ADR-044 add many phase deliverables but do not assign owners in
  their phase adjustment tables (`ADR-043.md:1408-1429`,
  `ADR-044.md:1004-1014`).

Impact:

For a governance ADR, phase ownership is part of the decision. The current plan
names many mechanisms but does not say who can declare phase completion after
the addenda expand the scope.

ADR-level fix:

Add an accountable owner column to the consolidated phase table:

- responsible implementer;
- required reviewer/approver;
- verifying tool or report;
- fallback if verifier is not available.

## Required ADR-Level Corrections Before Promotion

1. Publish a consolidated phase plan for ADR-042/043/044 as one cascade.
2. Split the current Phase 1 into smaller, dependency-aware subphases.
3. Define a mergeable cleanup path between Phase 2 and Phase 3.
4. Separate planned artifacts from currently enforceable `governs` closure.
5. Replace "addendum wins" with explicit amendment records.
6. Add a per-tool enforcement matrix with report-only, changed-file hard gate,
   repo-wide hard gate, and cron phases.
7. Define Phase 1.5 and Phase 4 as real decision checkpoints with owners,
   artifacts, and allowed outcomes.
8. Add tracking artifacts for all accepted deferred work before promotion.

## Acceptance Recommendation

Do not promote ADR-042, ADR-043, or ADR-044 beyond Draft in their current
form. The decisions are directionally valuable, but the implementation plan is
not yet an executable governance roadmap.

The documents should be revised at ADR granularity first: fewer low-level code
sketches, one authoritative phase contract, clear enforcement timing, and a
mergeable cleanup strategy. After that, detailed specs can safely define the
schemas, CLI flags, CI YAML, and tool internals.
