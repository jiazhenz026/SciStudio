# Unified QA Governance and Documentation System

Draft consolidation for ADR-042, ADR-043, and ADR-044.

This draft is a human-readable replacement structure for the ADR-042/043/044
cascade. It keeps the decisions and requirements from the three accepted ADRs,
but reorganizes them into:

1. A short decision summary.
2. Numbered normative requirements.
3. Supporting rationale.
4. Detailed specification appendices.

If accepted as a formal ADR, this document should supersede ADR-042, ADR-043,
and ADR-044, and those ADRs should become historical source records.

## Summary

SciEasy needs a single quality-governance system that keeps code, ADRs,
specifications, documentation, ownership metadata, agent instructions, and CI
policy synchronized.

The system has four jobs:

1. Define what counts as truth when code, documentation, ADRs, and generated
   facts disagree.
2. Detect and classify drift before it reaches protected branches.
3. Prevent the rules themselves from being silently weakened.
4. Keep human-facing docs, agent-facing docs, and production-agent docs short,
   generated where appropriate, and auditable.

The core decision is to replace prompt-only discipline with versioned schemas,
auditable reports, governed ownership, branch protection, and reviewable
exceptions.

This ADR does not define an implementation phase plan. The plan is intentionally
owned separately so the project owner can sequence the work without rewriting
the architecture.

## Normative Requirements

Requirement IDs are stable for this consolidation draft. If the formal ADR
number changes, keep these IDs unchanged unless a requirement is intentionally
merged, split, or withdrawn.

| ID | Requirement | Verification |
|---|---|---|
| QA-GOV-R001 | The workflow graph, ADR/spec frontmatter, MAINTAINERS data, audit reports, generated facts, docs, and agent instructions are governed artifacts. | `frontmatter_lint`, `closure`, `doc_drift`, CI branch protection |
| QA-GOV-R002 | Merge-time enforcement must be agent-equal: human and AI-authored changes are subject to the same protected-branch checks. | Branch protection, CI required checks |
| QA-GOV-R003 | During cleanup, code may be treated as transitional truth for documented drift classes; after the truth-shift, arbitration is based on accepted artifact status and explicit amendment records. | `doc_drift`, amendment lint, post-truth-shift revalidation |
| QA-GOV-R004 | The project uses a zero-tolerance posture for new governed violations. Existing violations may be managed by ratchet baselines, but new regressions in governed files fail CI. | Ratchet wrapper, baseline files, Checks API conclusions |
| QA-GOV-R005 | QA tools are self-governing: they must have schemas, tests, self-test artifacts, and audit coverage. | `tool_self_test_runner`, mutation checks, audit reports |
| QA-GOV-R006 | ADRs and specs must use typed frontmatter with status, governed modules/contracts/files, tests, ownership, translations, and amendment metadata. | `ADRFrontmatter`, `SpecFrontmatter`, `frontmatter_lint` |
| QA-GOV-R007 | ADR lifecycle changes, supersession, and amendments must be explicit and machine-readable; implicit "newer text wins" behavior is forbidden. | Amendment records, supersession lint |
| QA-GOV-R008 | `governs.modules`, `governs.contracts`, `governs.files`, and `governs.excludes` define the audit surface for each ADR/spec. | Closure audit |
| QA-GOV-R009 | MAINTAINERS must provide bidirectional ownership coverage from source paths to accountable owners and from owners back to governed paths. | `closure.check_bidirectional` |
| QA-GOV-R010 | Generated fact registries must replace hardcoded cross-document facts where values are expected to change. | `fact_drift`, generated facts freshness check |
| QA-GOV-R011 | Drift findings must be classified as a, b, c1, c2, c3, or d using the ADR-defined algorithm and strict signature matching for public contracts. | `doc_drift.classify_repo` |
| QA-GOV-R012 | Audit reports must use a stable schema, be stored under `docs/audit/reports/<sha>/`, and expose latest/archive views. | `AuditReport`, report storage checks |
| QA-GOV-R013 | Every governed implementation surface must close the loop: ADR/spec -> implementation -> tests -> owner -> audit report. | Full audit |
| QA-GOV-R014 | Root `AGENTS.md` is the canonical always-loaded policy file; runtime-specific files are pointers; subtree `AGENTS.md` files may only narrow rules. | `agents-md-lint`, instruction-load audit |
| QA-GOV-R015 | Procedural work belongs in skills or workflow docs, not duplicated inside always-loaded instruction files. | Skill pointer sync, AGENTS lint |
| QA-GOV-R016 | Commits made by agents must carry `Assisted-by:` trailers in the canonical format. | `trailer_lint`, `committer.py` |
| QA-GOV-R017 | Governance commits may require additional trailers such as `Fixes:`, `Loosening-Approved:`, `Loosening-Reason:`, `Governance-Modification-Approved-By:`, `Errata-Only:`, and `Backfill-Test:`. | Trailer lint and governance PR checks |
| QA-GOV-R018 | Real-behavior-proof evidence is required for user-visible, workflow, API, frontend, block, engine, and runtime changes. | PR template, RBP section validation |
| QA-GOV-R019 | A docs-agent may repair only allowlisted documentation paths and must fail closed when edits would cross governance boundaries. | docs-agent workflow and allowlist tests |
| QA-GOV-R020 | `committer.py` is the mandatory assisted commit path for agents and records commit metadata in append-only audit logs. | Pre-commit, commit-log audit |
| QA-GOV-R021 | Required skills must be installed or available across supported runtimes, and CI must verify the skill manifest. | Required-skill installer and verification |
| QA-GOV-R022 | Workflow v2 has seven explicit stages and must support local validation, stage guidance, and controlled auto-advance. | `.workflow/schema-v2.yaml`, gate tests |
| QA-GOV-R023 | Codemods that implement ADR-governed migrations must use structured parsing, include ADR metadata, and ship with tests. | Codemod lint, codemod tests |
| QA-GOV-R024 | The tool stack spans pre-commit, CI, docs build, audit, security, typing, tests, mutation, and frontend checks; fast local hooks and slower CI checks are separated. | Tool inventory and CI topology checks |
| QA-GOV-R025 | English is the source language for governed docs; translations must track source freshness and be regenerated when English sources change. | Translation metadata and workflow |
| QA-GOV-R026 | Docs build uses Sphinx/MyST plus strict cross-reference enforcement; examples and generated pages must be checked in CI. | `sphinx-build -W --keep-going`, examples tests |
| QA-GOV-R027 | Human developer exemptions are explicit, tiered, audited, and narrower than protected-branch bypass. | Identity registry, override audit |
| QA-GOV-R028 | Exemptions must be scoped, tracked, and machine-readable; blanket untracked suppressions are forbidden. | Exemption lint |
| QA-GOV-R029 | The ADR cascade must self-validate before implementation, continuously during implementation, and after any truth-shift. | Contradiction audit, continuous audit, revalidation artifact |
| QA-GOV-R030 | Implementation monitoring must track every ADR section, required artifact, verification check, owner, and status. | Implementation tracker |
| QA-GOV-R031 | Phase or milestone transitions must be blocked unless all required artifacts and verification checks for the transition exist. | Phase gate validator |
| QA-GOV-R032 | Each QA tool must have a self-test proving it detects at least one known-positive and one known-negative case. | Tool self-test report |
| QA-GOV-R033 | ADR-to-implementation and implementation-to-ADR drift must be checked bidirectionally, including tracker entries. | ADR implementation check |
| QA-GOV-R034 | Governance paths must be listed in `.governance-paths.yaml` and mirrored into CODEOWNERS. | Governance path lint and CODEOWNERS generation |
| QA-GOV-R035 | Modifying governance paths requires a governance-modification workflow unless the change qualifies as errata-only. | `governance_mod_guard`, workflow check |
| QA-GOV-R036 | Governance rules may be strengthened normally but may not be loosened without explicit approval, reason, and audit trail. | Monotonic check |
| QA-GOV-R037 | Governance tooling must validate itself recursively so rule files, workflows, and path filters cannot drift apart. | Recursive self-validation checks |
| QA-GOV-R038 | Governance change logs and protected audit logs are append-only. Tampering or missing entries must fail audit. | Append-only log checks |
| QA-GOV-R039 | Honeypot canaries must exist for critical governance weakening patterns and must fail if removed or bypassed. | Honeypot check |
| QA-GOV-R040 | ADR self-modification is allowed only through the defined errata/addendum path and cannot silently change enforcement semantics. | ADR self-modification lint |
| QA-GOV-R041 | Tests must assert behavior, not merely import modules, assert constants, or duplicate implementation logic. | Test-quality AST lint |
| QA-GOV-R042 | New tests for governed behavior must be linked to the behavior they prove; backfilled tests require explicit trailers or tracker entries. | Test-first check, PR template |
| QA-GOV-R043 | QA tooling must meet mutation score targets: default at least 0.75, QA-critical surfaces at least 0.90. | Mutation runner |
| QA-GOV-R044 | The `test-author` skill exists to improve tests without weakening source or governance rules. | Skill availability and test-quality audit |
| QA-GOV-R045 | Agent instruction carriers are separated into hooks, path rules, skills, and always-loaded files; each rule belongs in the narrowest effective carrier. | AGENTS lint and skill sync |
| QA-GOV-R046 | Every governed `AGENTS.md` file must include required sections for data classification, assessment rubric, and path boundaries where applicable. | Classification lint |
| QA-GOV-R047 | Data classification categories and handling rules must be explicit for public code, secrets, generated code, fixtures, internal assets, user data, and append-only logs. | Data-classification lint |
| QA-GOV-R048 | Assessment rubrics must list completion criteria, verification commands, and stricter subtree rules where they apply. | Rubric lint |
| QA-GOV-R049 | Three-tier path boundaries must be explicit: free edit, ask first, and never edit. | Path-boundary lint |
| QA-GOV-R050 | CI workflows may not be weakened, narrowed, skipped, or made optional without governance approval. | Weakened-CI check |
| QA-GOV-R051 | Documentation is organized into four sibling categories: contributor docs, user docs, production-agent docs, and doc-guide docs. | Docs structure lint |
| QA-GOV-R052 | The four first-go documents are contributor onboarding, user quickstart, production-agent README, and doc-guide how-to-write-a-doc. | Docs structure lint |
| QA-GOV-R053 | Human-authored docs must obey the document-length discipline unless a typed exception is present. | `doc_length_lint` |
| QA-GOV-R054 | Documentation frontmatter must use typed schemas for workflow docs, user docs, production-agent docs, and doc-guide docs. | Docs schema lint |
| QA-GOV-R055 | Contributor, user, production-agent, and doc-guide directory structures are governed and must match the ADR layout. | Docs structure lint |
| QA-GOV-R056 | Production-agent documentation is intentionally minimal and focused on what is written into user projects. | Prod-agent doc lint |
| QA-GOV-R057 | Doc-guide docs must describe how docs are authored, generated, owned, and reviewed, and must apply their own rules. | Doc-guide lint |
| QA-GOV-R058 | The docs build stack uses Sphinx ecosystem tools including MyST, autoapi/autodoc support, click/OpenAPI support, gallery/design helpers, copybutton, issues, and the PyData theme. | Docs build |
| QA-GOV-R059 | Custom docs directives and generators must produce block, runner, AI-block, CLI, OpenAPI, schema, entry point, and `llms.txt` references. | Generator tests |
| QA-GOV-R060 | Skills are pointers to canonical workflow/reference docs; long duplicated skill bodies are forbidden. | `skill_pointer_sync` |
| QA-GOV-R061 | ADR-042 consistency rules extend to all four documentation categories and to skill-to-doc closure. | Closure audit |
| QA-GOV-R062 | Docs-specific pre-commit hooks and `docs-build.yml` must be integrated into the aggregate check path. | CI workflow checks |
| QA-GOV-R063 | Meta-compliance items M1 through M19 are normative and must be represented as machine-checkable verification items where feasible. | Meta-compliance audit |
| QA-GOV-R064 | The implementation plan is not part of this ADR body; it is a separate owner-authored plan that must map work items back to these requirement IDs. | Plan review |

## Supporting Detail

### 1. Why

The project accumulated four kinds of drift:

1. Code and ADRs disagreed about public behavior.
2. Documentation repeated facts that later changed.
3. Governance rules lived in prompts and were easy to miss or weaken.
4. Agent-facing instructions, human-facing docs, and production-agent docs
   duplicated workflow procedures.

Prompt instructions helped, but they were not enough. They could remind an
agent what to do, but they could not prove that a PR preserved ownership,
truth arbitration, translation freshness, test quality, or governance
invariants.

The project therefore needs a governance system where the source of truth is
typed, checked, reported, reviewed, and protected by CI.

### 2. Why This Design Is Reasonable

This design treats governance as a normal software subsystem:

- Schemas define what valid metadata looks like.
- Audit tools classify violations and emit stable reports.
- CI protects branch state.
- Append-only logs and trailers preserve accountability.
- Documentation is generated where the source is machine-readable.
- Human judgment remains available through explicit, audited exceptions.

The result is stricter than prompt discipline but less brittle than trying to
freeze every file forever. Existing debt can be managed through baselines and
cleanup plans, while new regressions remain blocked.

### 3. Principles

The system follows these principles:

1. Governed artifacts are code-adjacent infrastructure, not informal prose.
2. Humans and agents use the same protected-branch gate.
3. Every meaningful rule has a verification path.
4. Generated facts replace duplicated facts.
5. Exceptions are explicit, scoped, and auditable.
6. Instruction files stay small; procedures live in skills or docs.
7. Documentation categories are siblings, not nested afterthoughts.
8. The implementation plan is replaceable; the requirements are stable.

### 4. Alternatives Considered

#### Keep ADR-042/043/044 Separate

Rejected for the long-term document shape. The three ADRs are one governance
system: truth and drift, governance hardening, test quality, agent
instructions, and documentation architecture depend on each other. Keeping them
separate made the accepted requirements harder to read and encouraged scattered
addendum logic.

The old ADRs should remain as historical sources, but the active design should
be one integrated ADR.

#### Use Prompt-Only Enforcement

Rejected. Prompt-only rules are useful reminders but cannot guarantee merge-time
correctness, detect drift, or protect governance files from weakening.

#### Use Manual Review Only

Rejected. Manual review remains necessary for design judgment, but it cannot
scale to every frontmatter field, docs mirror, ownership closure, trailer,
mutation threshold, or generated fact.

#### Make All Checks Hard-Fail Immediately

Rejected as an implementation strategy. The design keeps a zero-tolerance goal
for new regressions, but large existing debt may require report-only mode,
baselines, and owner-approved phase gates.

#### Put All Workflow Instructions in AGENTS.md

Rejected. Always-loaded files must stay short and policy-focused. Detailed
procedures belong in skills or workflow docs so they can be versioned, tested,
and reused by multiple runtimes.

### 5. Costs

This design adds real overhead:

- More schemas and audit tools must be maintained.
- Governance changes require more explicit approval.
- Some PRs will need more metadata than before.
- The docs system must distinguish authored, generated, translated, and
  production-agent-facing content.
- CI becomes more complex because local fast checks and full repository checks
  have different latency budgets.

The tradeoff is intentional: SciEasy relies on many agents, docs, plugins,
workflow contracts, and runtime surfaces. The cost of invisible drift is higher
than the cost of explicit governance.

## Appendix A: Legacy ADR Mapping

| Legacy source | Consolidated area | Requirement IDs |
|---|---|---|
| ADR-042 sections 1-4 | Scope, drift problem, principles, truth posture | QA-GOV-R001 through QA-GOV-R005 |
| ADR-042 sections 5-7.5 | Frontmatter, MAINTAINERS, audit reports, facts registry | QA-GOV-R006 through QA-GOV-R012 |
| ADR-042 sections 8-11 | Truth arbitration, drift classification, fact substitution, ownership closure | QA-GOV-R003, QA-GOV-R010, QA-GOV-R011, QA-GOV-R013 |
| ADR-042 sections 12-18 | AGENTS hierarchy, trailers, RBP, docs-agent, committer, skills, personas | QA-GOV-R014 through QA-GOV-R021, QA-GOV-R045 |
| ADR-042 sections 19-24 | Workflow v2, codemods, tool stack, language policy, docs build, audit reports | QA-GOV-R022 through QA-GOV-R026 |
| ADR-042 sections 25-28 | Human exemptions, carve-outs, amendments, self-compliance | QA-GOV-R027 through QA-GOV-R029, QA-GOV-R063 |
| ADR-043 section 2 | Implementation tracker, phase gate, tool self-tests | QA-GOV-R030 through QA-GOV-R033 |
| ADR-043 section 3 | Governance hard blocks | QA-GOV-R034 through QA-GOV-R040 |
| ADR-043 section 4 | Test quality enforcement | QA-GOV-R041 through QA-GOV-R044 |
| ADR-043 sections 5-6 | Instruction layering, data classification, rubrics, path boundaries, weakened CI | QA-GOV-R045 through QA-GOV-R050 |
| ADR-044 sections 1-5 | Documentation model, entry points, length discipline, docs schemas | QA-GOV-R051 through QA-GOV-R054 |
| ADR-044 sections 6-13 | Docs directories, production-agent docs, doc-guide, Sphinx, generators, skill pointers, docs CI | QA-GOV-R055 through QA-GOV-R062 |
| ADR-044 section 15 | Meta-compliance M16-M19 | QA-GOV-R063 |

## Appendix B: Data Model Specifications

### B.1 ADR and Spec Frontmatter

ADR frontmatter includes:

- Numeric ADR identifier.
- Title.
- Status.
- Creation, acceptance, and supersession dates.
- Supersedes and superseded-by links.
- Related ADRs.
- Issues and tracking issue.
- `is_code_implementation`.
- `governs.modules`, `governs.contracts`, `governs.files`,
  `governs.entry_points`, and `governs.excludes`.
- Tests.
- `agent_editable`.
- Assisted-by metadata.
- Phase or implementation state.
- Tags.
- Owner and co-authors.
- Source language and translations.
- Amendment records.

Spec frontmatter follows the same governance model but is scoped to features,
contracts, and implementation plans rather than architectural decisions.

### B.2 Amendment Records

An amendment record includes:

- Target ADR and section or component.
- Amendment kind: extend, replace, clarify, deprecate, or withdraw.
- Summary.
- Optional replacement text or reference.
- Verification status.

Amendments are explicit records. Addenda do not silently override earlier ADRs.

### B.3 MAINTAINERS

MAINTAINERS entries include:

- Path globs.
- Owners and reviewers.
- Maintainer tier.
- Required approval conditions.
- Optional agent-editability rules.
- Optional escalation contacts.

Glob resolution must be deterministic. Parent/child overlaps are allowed only
when the narrower rule clearly wins.

### B.4 Audit Report

An audit report includes:

- Commit SHA.
- Tool runs.
- Findings.
- Drift class.
- Severity.
- Stable finding ID.
- Affected artifact.
- Source references.
- Verification command.
- Translation freshness status where applicable.
- Summary counts.

Reports are stored under `docs/audit/reports/<sha>/`, with latest and archive
views.

### B.5 Facts Registry

The facts registry includes generated, typed values for:

- Workflow stages.
- Tool inventory.
- ADR metadata.
- Maintainer ownership.
- Required skills.
- Documentation surfaces.

Hardcoded facts that are expected to change must be replaced with substitutions
after the registry is implemented.

### B.6 Implementation Tracker

Tracker entries include:

- ADR requirement or section ID.
- Required artifacts.
- Verification checks.
- Owner.
- Status.
- Evidence link.
- Last verified SHA.
- Notes.

Valid statuses include not started, in progress, implemented, verified,
deferred, blocked, superseded, and withdrawn. State transitions are constrained
by required artifacts and verification checks.

### B.7 Governance Paths

`.governance-paths.yaml` includes:

- Path pattern.
- Governance class.
- Agent editability.
- Required reviewers or owner tier.
- Whether weakening requires explicit approval.
- Whether the path is append-only.
- Whether CODEOWNERS should include it.

The registry is the source for workflow path filtering. Workflows must not keep
shadow hand-maintained path lists.

### B.8 Test Quality

Test-quality reports include:

- Test file.
- Covered source file or behavior.
- Anti-pattern findings.
- Mutation score.
- Whether the test was written before or after implementation.
- Backfill-test trailer where applicable.

### B.9 Documentation Frontmatter

Workflow, user, production-agent, and doc-guide docs each have typed
frontmatter. Common fields include:

- Title.
- Category.
- Audience.
- Owner.
- Source type: authored, generated, or translated.
- Source SHA for generated or translated files.
- Review cadence.
- Length exception where applicable.
- Related ADR/spec/source surfaces.

## Appendix C: Truth and Drift Rules

### C.1 Truth Arbitration

Before the truth-shift, code may be treated as transitional truth for
documented cleanup cases. After the truth-shift:

1. Accepted ADRs define intended architectural contracts.
2. Implemented code defines actual behavior.
3. Generated facts define volatile repo facts.
4. Amendment records define explicit changes to ADR text.
5. Audit reports identify and classify disagreements.

Conflicts between accepted ADRs must be surfaced as ADR conflicts, not silently
resolved by implementation choices.

### C.2 Drift Classes

Drift classes are:

- `a`: direct contradiction between governed sources.
- `b`: public contract mismatch, including strict signature mismatch.
- `c1`: stale factual reference where generated facts should apply.
- `c2`: doc/code mismatch where code is transitional truth during cleanup.
- `c3`: non-contractual explanatory drift.
- `d`: missing documentation, missing frontmatter, missing owner, or missing
  traceability.

The algorithm must prefer explicit machine-readable metadata over prose
heuristics where possible.

### C.3 Signature Matching

Public contract matching is strict for:

- Public functions and methods.
- Public classes.
- CLI commands.
- HTTP endpoints.
- Plugin contracts.
- Data-object contracts.
- Block contracts.

Signature drift is not downgraded merely because the prose still sounds close.

### C.4 Fact Substitution

Generated facts are used when a value is expected to change, such as workflow
stage count, tool inventory, required skill list, or ownership closure. Prose
may explain what the fact means, but the volatile value should come from the
registry.

## Appendix D: Governance Modification Rules

### D.1 Five Layers

Governance hardening has five layers:

1. Governance paths registry plus CODEOWNERS.
2. Local pre-commit governance modification guard.
3. Monotonic strengthening check.
4. Recursive self-validation.
5. Append-only audit log plus honeypot canaries.

### D.2 Loosening Protocol

Any governance loosening requires:

- Explicit owner or tiered approval.
- `Loosening-Approved:` trailer.
- `Loosening-Reason:` trailer.
- Governance change log entry.
- Passing recursive validation.

The absence of a check is not approval to weaken policy.

### D.3 Errata-Only Path

ADR self-edits may use an errata-only path only when they do not change
semantics, enforcement, ownership, or implementation obligations. Errata-only
commits require `Errata-Only:` trailer and remain auditable.

### D.4 Honeypot Canaries

Honeypot rules intentionally represent forbidden weakening patterns. Removing,
relaxing, or bypassing a canary is a finding unless the loosening protocol is
followed.

## Appendix E: Test Quality Rules

### E.1 Forbidden Test Patterns

Tests must not be accepted when they only:

- Import a module.
- Assert a constant copied from implementation.
- Assert that a mocked function was called without behavioral assertions.
- Mirror implementation logic instead of checking behavior.
- Exercise only the happy path for governance logic that has explicit failure
  modes.

### E.2 Test-First and Backfill

New governed behavior should have tests written before or alongside the
implementation. Backfilled tests are allowed for existing behavior but must be
marked with explicit evidence, tracker status, or `Backfill-Test:` trailer.

### E.3 Mutation Targets

Default mutation target is at least 0.75. QA-critical surfaces, especially
`src/scieasy/qa/**`, target at least 0.90. Temporary lower scores require
tracked exceptions.

### E.4 `test-author` Skill

The test-author skill may edit tests and fixtures. It must not weaken source
behavior, governance rules, or CI settings to make tests pass.

## Appendix F: Agent Instruction Architecture

### F.1 Carrier Types

Rules are carried by:

- Hooks, for automatic enforcement.
- Path-rule files, for scoped local policy.
- Skills, for procedures.
- Always-loaded files, for short canonical policy.

Each rule belongs in the narrowest carrier that can enforce or explain it.

### F.2 Root and Subtree Files

Root `AGENTS.md` is canonical. Runtime-specific files point to it. Subtree
`AGENTS.md` files narrow rules and must not duplicate the root.

### F.3 Required Sections

Governed instruction files include, where applicable:

- Identity or purpose.
- Data classification.
- Assessment rubric.
- Path boundaries.
- Hotfix or exception handling.
- Required verification commands.

### F.4 Instruction Load Audit

The instruction-load audit records which rule carriers were loaded in an agent
session. This is for debugging and accountability, not a substitute for CI.

## Appendix G: Documentation Architecture

### G.1 Categories

Documentation has four sibling categories:

1. `docs/contributing/`: contributor workflows.
2. `docs/user/`: end-user product documentation.
3. `docs/prod-agent/`: production-agent artifacts written into user projects.
4. `docs/doc-guide/`: documentation authoring rules.

They are siblings because they serve different audiences and should not bury
one audience under another.

### G.2 First-Go Documents

The four first-go documents are:

- `docs/contributing/onboarding.md`.
- `docs/user/quickstart.md`.
- `docs/prod-agent/README.md`.
- `docs/doc-guide/how-to-write-a-doc.md`.

### G.3 Length Discipline

Human-authored docs should be short enough to read and maintain. Long docs must
be split or carry a typed length exception explaining why the length is
necessary.

### G.4 Directory Requirements

Contributor docs include onboarding, first PR, configuring agents, workflow
recipes, testing, agent dispatch, policy, and references.

User docs include install, quickstart, workflow graph, blocks/contracts,
data objects, execution model, code runners, AI blocks, tutorials, reference,
plugin authoring, glossary, FAQ, production environment artifacts, and
`llms.txt`.

Production-agent docs have a minimal README focused on what is written into
user projects, known issues, upgrade flow, and extension points.

Doc-guide docs explain how to write docs, distinguish authored from generated
docs, and assign ownership/review.

## Appendix H: Docs Build and Generation

### H.1 Sphinx Stack

The docs build uses Sphinx/MyST and related ecosystem tools for API, CLI,
OpenAPI, gallery, design, copybutton, issue references, and theme support.

The canonical theme is PyData Sphinx Theme.

### H.2 Custom Directives

Required custom directives include:

- SciEasy block catalog.
- SciEasy runner catalog.
- SciEasy AI-block catalog.

### H.3 Generators

Required generators include:

- `llms_txt`.
- Entry point catalog.
- CLI reference.
- OpenAPI reference.
- Schema reference.

Generated pages must record their source and freshness metadata.

### H.4 Skill-as-Pointer

Skills that document procedures must point to canonical workflow or reference
docs. Long duplicated skill bodies are forbidden because they drift.

## Appendix I: CI and Tool Topology

### I.1 Local Checks

Local checks should be fast and focused:

- Formatting.
- Lightweight lint.
- Frontmatter validation for touched docs.
- Governance path guard for touched governance files.
- Trailer and commit metadata checks.

### I.2 CI Checks

CI owns slower or broader checks:

- Full audit.
- Docs build.
- Type checks.
- Test suite.
- Mutation runs where applicable.
- Security and dependency checks.
- Frontend checks.
- Translation freshness.
- Governance modification workflow.

### I.3 Ratchet Baselines

Baselines may allow existing debt to be reduced over time, but they must not
permit new violations in previously clean files or increases above baseline.
Baseline files are governance files and require protected update paths.

## Appendix J: Human Exemptions and Overrides

Humans may receive narrowly scoped exemptions because some governance choices
require human judgment. Exemptions are not protected-branch bypasses.

Human identity, maintainer tier, and override authority are defined in the
identity registry. Overrides are logged and periodically reviewed.

Trivial-change fast lanes are allowed only for changes that cannot affect
contracts, runtime behavior, governance policy, or generated artifacts.

## Appendix K: Exemptions

Path exemptions include generated code, frontend bundles, node modules, certain
skill data assets, templates, scripts outside audit-critical paths, and tests
where docstring coverage does not apply.

Inline exemptions require:

- Specific rule ID.
- Tracking issue.
- Narrow scope.

Blanket suppressions are forbidden.

## Appendix L: Meta-Compliance

Meta-compliance requirements M1 through M19 remain normative. They cover:

- ADR self-compliance.
- Frontmatter validity.
- Audit report generation.
- Tool inventory.
- Ownership closure.
- Translation freshness.
- Workflow validation.
- Governance hardening.
- Mutation and test-quality targets.
- AGENTS hierarchy and required sections.
- Documentation length, pointer skills, docs closure, and translation mirrors.

Each meta-compliance item should eventually map to one tracker entry and one
machine-checkable verification command where feasible.

## Appendix M: Implementation Plan Slot

This ADR intentionally does not prescribe phases, subtracks, owners, or
calendar estimates.

The implementation plan must be a separate owner-authored document that maps
work items to `QA-GOV-R###` requirements. A valid plan must include:

- Work item ID.
- Requirement IDs covered.
- Files expected to change.
- Owner.
- Verification command.
- Exit condition.
- Whether the work is report-only or enforced.
- Rollback path.

The plan may sequence work by dependency rather than by legacy ADR number.

## Appendix N: Supersession Procedure

If this draft becomes the accepted unified ADR:

1. Assign it a formal ADR number or make it the rewritten ADR-042.
2. Mark ADR-042, ADR-043, and ADR-044 as superseded by the unified ADR.
3. Preserve the old ADRs as historical records.
4. Move any remaining schema snippets or examples not copied here into
   implementation specs.
5. Update `related`, `supersedes`, `superseded_by`, and amendment metadata.
6. Regenerate zh-CN mirrors after the English source is accepted.
7. Re-run frontmatter, doc-drift, closure, docs-build, and translation checks.
