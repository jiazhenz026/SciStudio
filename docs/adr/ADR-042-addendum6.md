---
adr: 42
addendum: 6
title: "Gate Record Ledger And Single-Source Governance Runtime"
status: Proposed
date_created: 2026-05-29
date_accepted: null
date_superseded: null

supersedes: []
superseded_by: null
related: [42]
closes_issues: []
tracking_issue: null

is_code_implementation: true
governs:
  modules:
    - scistudio.qa.governance
    - scistudio.qa.governance.gate_record
  contracts: []
  entry_points: []
  files:
    - docs/adr/ADR-042-addendum6.md
    - docs/specs/adr-042-gate-ledger-runtime.md
    - docs/ai-developer/rules.md
    - docs/ai-developer/specific_rules/gated-workflow.md
    - docs/ai-developer/specific_rules/guided-work.md
    - docs/ai-developer/personas/live-implementer.md
    - src/scistudio/qa/governance/**
    - tests/qa/**
    - .github/workflows/**
    - scripts/hooks/**
    - scripts/scistudio_pr_create.py
  excludes: []

tests:
  - tests/qa/test_gate_record.py
agent_editable: false
assisted_by:
  - "Codex:gpt-5"
  - "Claude:claude-opus-4-8"

phase: planning
tags: [qa, ci, ai-governance, workflow-gate, gate-record, single-source-of-truth]
owner: "@jiazhenz026"
co_authors: ["@codex", "@claude"]
language_source: en
translations: []
---

# ADR-042 Addendum 6: Gate Record Ledger And Single-Source Governance Runtime

## 1. Decision Summary

This addendum preserves the ADR-042 gate workflow as a hard standard and
replaces the implementation text for ADR-042 Section 7 where the existing
implementation has split authority across gate records, receipts, hooks,
guards, wrappers, and CI.

The retained text is repeated below so implementation work can use this
addendum as the effective Section 7 contract. Unchanged ideas remain unchanged:
AI governance is deterministic tooling, not prompt-only policy; AI agents
follow the same repository quality checks as humans plus additional harness
constraints; CI remains authoritative.

The changed implementation model is:

- `gate_record` becomes the single source of truth;
- receipt behavior is folded into the gate record as ledger events;
- local hooks, guard modules, PR wrapper checks, and CI use one shared
  evaluator;
- the ledger records both declared scope and observed git diff state;
- check evidence is incremental and reconciled by covered surface;
- task kinds receive explicit profiles while preserving hard gate standards;
- owner-guided live implementation is represented by a new `guided` task kind
  and the `live_implementer` persona;
- local and CI share one tool-version source and a CI-equivalent local
  environment so passing local checks predicts CI.

### 1.1 Problems Addressed

| Problem | Risk | ADR response | Detailed section |
|---|---|---|---|
| Gate record and receipt record overlapping evidence | Local evidence can disagree with committed evidence, and normal follow-up edits invalidate useful prior checks | Merge receipt behavior into gate record ledger events | Section 7.5 |
| Local hooks, guards, wrappers, and CI use different criteria | A branch can pass locally and fail CI for avoidable governance reasons | Require one shared evaluator for local and CI enforcement | Section 7.5 |
| Gate records rely too much on declared scope | The record can claim a scope that differs from the actual git diff | Record both owner declarations and observed changed files | Section 7.2 and Section 7.5 |
| Current evidence freshness is all-or-nothing | A later unrelated edit discards earlier valid checks | Validate check evidence by covered surface and input fingerprint | Section 7.5 |
| All task kinds inherit the same heavy process shape | Small, docs-only, maintenance, and owner-guided tasks spend unnecessary effort on workflow form | Define task-kind profiles while preserving hard gate standards | Section 7.6 and Section 7.7 |
| Owner-guided implementation does not fit existing task kinds | Hotfix is too narrow, feature is too planned, and explore sounds read-only | Add `guided` as an owner-directed live implementation task kind and `live_implementer` as its persona | Section 7.2 and Section 7.7 |
| Committed gate records may accidentally capture local-machine details | Absolute paths, stdout/stderr, usernames, temporary directories, or environment details can leak into the remote repository | Record behavior and sanitized facts in the ledger; keep detailed logs local-only | Section 7.5 |
| Local and CI run different tool versions and environments | A branch passes locally but fails CI on lint/type/test for avoidable version or environment reasons | Make CI the single source of truth for tool versions and require a CI-equivalent local environment | Section 7.10 |

## 2. Replacement Text For ADR-042 Section 7

This section is the proposed replacement text for ADR-042 Section 7. Text that
still applies is intentionally repeated instead of summarized.

### 7.1 Why

AI developers are useful but constrained by context limits, instruction
loading behavior, tool availability, and a tendency to overfit local prompts.
Repository governance must therefore be enforced by deterministic tools, not
only by instruction text.

AI-specific policy must also avoid treating AI agents as magical: AI agents
follow the same repository quality checks as humans, plus additional harness
constraints where their failure modes are different.

The gate implementation must not create a second quality system that competes
with CI. It must make the same quality obligations visible earlier and record
how the current candidate satisfies them.

### 7.2 AI Gate Workflow

AI work is not always a new code feature. The gate workflow therefore models a
reviewable task lifecycle, not a fixed "code implementation" pipeline.

Supported task kinds are:

| Kind | Examples | Notes |
|---|---|---|
| `hotfix` | Live-debugging and a batch of related bug fixes | May start from owner directive; formal issues must be linked or created before commit |
| `bugfix` | Fix one known issue | Prefer existing issue; create one only if none exists |
| `feature` | Implement new behavior | Usually requires spec and/or ADR links |
| `refactor` | Behavior-preserving code movement or cleanup | Must prove affected behavior stayed stable |
| `docs` | Write or update documentation | Still requires scope, checks, and issue linkage |
| `maintenance` | Cleanup, dependency/config hygiene, repository housekeeping | Must declare why it is safe and scoped |
| `manager` | Agent-manager coordination, checklist updates, merge preparation | May touch planning docs and reports without code changes |
| `guided` | Owner-directed live implementation session | May expand scope through recorded owner directives; final tier-selected check obligations remain mandatory |

Gate state is committed repository evidence stored under `.workflow/records/`.
It is no longer split between a committed gate record and local-only receipt
state. Local-only logs may exist as helper artifacts, but the gate record
ledger is the canonical state read by hooks, wrappers, guards, and CI.

The gate does not replace the repository's branch or PR rules. It protects the
AI-authored work boundary and records the evidence reviewers and CI need. The
branch, PR, reviewer, and remote CI requirements still apply after the commit
exists.

The AI gate has six required lifecycle concerns:

| Concern | Required record | Blocking rule |
|---|---|---|
| 1. Scope And Issue | Task kind, owner directive, branch, persona, declared scope when known, governance-touch flag, issue links | No issue linkage or branch/task identity means no PR readiness |
| 2. Plan | Planned files/checks/docs/tests when known, or task-kind profile explaining why scope is owner-guided or dynamic | Missing plan data blocks planned task kinds; `guided` records owner directives instead of pretending all scope was known up front |
| 3. Implement | Work happens within declared scope or recorded owner directives; actual changed files are observed from git | Observed diff outside the allowed owner/directive model fails reconciliation |
| 4. Update Docs | Required docs/spec/ADR/changelog/checklist updates are completed or explicitly marked not applicable with rationale | Missing required docs fail reconciliation |
| 5. Test And Checks | Required tests plus ADR-042 normative checks, tier-selected local/CI checks, and command evidence | Missing, stale, or failing required checks fail reconciliation |
| 6. Commit And Submit PR | Commit records gate ledger path, task kind, issue, AI assistance metadata, pre-PR candidate evidence, and later PR URL/issue closure provenance | Missing durable provenance or missing issue-closing keywords fails CI |

These concerns remain mandatory, but the gate record is an append-only ledger
rather than a single linear form that is only valid at the end of a fixed
sequence. Later work may add new directive, diff, check, docs, test, guard, or
reconcile events. The current candidate is valid when the shared evaluator can
reconcile the ledger against the current git diff and PR metadata.

The gate ledger schema is:

| Field or event | Meaning |
|---|---|
| `record_id` | Repository-visible gate record identifier |
| `session_id` | Local unique session identifier stored under `.git/scistudio/gates/`; identifies the live work session and is distinct from the committed `record_id` |
| `task_kind` | One of `hotfix`, `bugfix`, `feature`, `refactor`, `docs`, `maintenance`, `manager`, `guided` |
| `strictness_tier` | Tier derived from `task_kind` and escalated by observed diff per Section 7.6; Tier 1 is strictest and Tier 3 is lightest |
| `persona` | One of the allowed AI personas in Section 7.3 |
| `runtime` | AI runtime executing the task, for example Codex, Claude Code, Gemini, or a local CLI agent |
| `branch` | Branch the ledger applies to |
| `owner_directive` | Initial human instruction or issue that authorized the task |
| `directive_events` | Later owner instructions that redirect or expand work |
| `declared_scope.include` | Expected allowed path globs when known |
| `declared_scope.exclude` | Expected denied path globs when known |
| `observed_diff` | Changed files, git base/head, diff fingerprint, and file-surface classification derived from git |
| `governance_touch` | Whether governance files may be touched |
| `issues` | Existing or newly created GitHub issues to close or reference |
| `required_obligations` | Docs, tests, checks, and guards inferred by the shared evaluator |
| `check_events` | Recorded command/tool identity, exit code, timestamp, covered surface, input fingerprint, and sanitized result summary |
| `docs_events` | Docs/spec/ADR/changelog/checklist updates or N/A rationale |
| `test_events` | Changed test paths, runtime/e2e evidence, or N/A rationale |
| `guard_events` | Guard reports produced from shared evaluator inputs |
| `reconcile_events` | Local or CI reconciliation result for a specific candidate |
| `commit` | Commit SHA, trailers, and gate record path |
| `pull_request` | PR URL/number, body issue closure evidence, and final provenance |
| `requested_admin_labels` | Locally requested or expected administrator labels; not authoritative |
| `observed_admin_labels` | CI-observed PR labels with actor/provenance metadata |

Declared scope and observed diff are separate. Declared scope records the plan
or owner instruction. Observed diff records what actually changed. Required
checks and final reconciliation are derived from observed diff, task kind,
persona, and owner directives.

The same objective principle applies to every claimed artifact, not only to
scope. Declared docs and test evidence are reconciled against the observed diff:
a `docs_events` or `test_events` path that does not appear in the observed
changed-file set is recorded as claimed-but-unverified and does not satisfy a
docs or test obligation on its own. The ledger records both what the agent
declared and what git actually shows, and the evaluator trusts the git-observed
facts over the declarations. An agent stating that it changed a file is a claim;
the observed diff is the evidence.

Committed gate records must record behavior, not local-machine details. The
ledger may store command names, argv expressed in repo-relative form, exit
codes, timestamps, tool versions, repo-relative paths, git object ids, file
surface classes, content fingerprints, and compact sanitized summaries. The
ledger must not store:

- absolute local filesystem paths;
- local usernames, home directories, temporary directories, or virtualenv paths;
- environment variable dumps;
- raw stdout or stderr transcripts;
- local browser profile paths, local service URLs with secrets, or machine
  identifiers;
- dependency cache paths or tool installation paths.

Detailed command transcripts may be written only to local ignored paths such as
`.workflow/local/**`. Those local logs are convenience artifacts and must not be
committed or pushed. If a detailed transcript is needed for review, it must be
converted into a sanitized summary or committed as an explicit audit artifact
that contains no local environment details.

Check evidence is incremental. A check event remains valid only for the covered
surface and input fingerprint it recorded. A later Python edit invalidates
Python lint/type/test evidence for that surface. A later docs-only edit does
not automatically invalidate unrelated backend unit-test evidence. A gate
record edit invalidates reconciliation evidence when it changes obligations,
but it does not necessarily invalidate already recorded source test evidence.

Hotfix work may begin from a human owner directive before every bug is fully
triaged. Before PR readiness, however, the issue concern must be satisfied:
each fixed bug is linked to an existing issue or a newly created one, and a
batch hotfix records the list of issues in the same gate ledger. This permits
live debugging without allowing untracked bug fixes to enter history.

Guided work may also begin from a human owner directive and may expand through
later owner directives. Each meaningful directive must be recorded in the
ledger. `guided` is broader than `hotfix`; it may include feature, bugfix,
refactor, docs, or maintenance work. Its default persona is
`live_implementer`. It does not bypass issue linkage, docs, tests, checks,
protected-path authorization, branch protection, or CI.

During an active owner-guided `hotfix` or `guided` session, the agent may delay
gate commands and complete gate fields while diagnosing and editing. This is a
live-work allowance, not a delivery bypass. Before commit, push, or PR
creation, the agent must create or update the ledger and bring it back to a
complete state: issue linkage, scope or directive coverage, docs/tests/check
evidence, admin labels where required, and tier-selected check
reconciliation must all pass.

Manager tasks also require issue linkage. A coordination-only manager task may
use a lightweight tracking issue, but it must still be visible in the issue
tracker before PR readiness.

### 7.3 Persona Rules

Personas are routing labels. They help decide which kind of agent should do a
task, but they do not grant permissions and they do not change quality gates.

There are six repository personas:

| Persona | Use | Required skill | Root policy |
|---|---|---|---|
| `manager` | Coordinate agents, maintain checklists, prepare merges, summarize status | `manager` | Must obey root `AGENTS.md`, gate scope, branch isolation, and owner scheduling decisions |
| `implementer` | Implement code, tests, tool wiring, docs generated from implementation | `implementer` | Must obey root `AGENTS.md`, gate ledger, tests, documentation landing, and code quality checks |
| `adr_author` | Draft or revise ADR/spec governance text and schemas | `adr-author` | Must obey root `AGENTS.md`, ADR schema, document structure rules, and governance-file review requirements |
| `audit_reviewer` | Inspect diffs, audit findings, CI failures, and conformance gaps | `audit-reviewer` | Must obey root `AGENTS.md`, review-only scope unless explicitly assigned a fix, and finding-first reporting |
| `test_engineer` | Design tests, add test evidence, run runtime validation, and produce e2e evidence | `test-engineer` | Must obey root `AGENTS.md`, test-engineer production-code boundary, gate ledger, and runtime evidence rules |
| `live_implementer` | Carry out owner-directed live implementation where scope evolves through directives | `live-implementer` | Must obey root `AGENTS.md`, the guided-work rule, directive ledger, observed-diff reconciliation, and all final CI-quality gates |

Every AI task must declare one persona in the gate ledger. A task may change
persona only by appending a ledger event with owner or manager rationale.
Persona declarations are AI-agnostic: Codex, Claude Code, Gemini, local CLI
agents, and future agent runtimes use the same persona names and the same
policy checks.

`live_implementer` must have its own persona guide and specific rule document.
It must not inherit the ordinary implementer workflow by implication. The
persona guide must explain how owner directive events expand scope, when to stop
and ask for clarification, how to keep the ledger current during an interactive
session, and which final checks are still mandatory before PR readiness.

### 7.4 Runtime Configuration, Constitution, Skills, And Memory

AI runtimes commonly load project-local configuration from runtime-specific
directories, such as `.claude/`. ADR-042 adopts that pattern, but keeps it
AI-agnostic: no repository rule may exist only for one AI runtime when the same
concept applies to others.

Root policy, constitution, skills, memory, and workflow docs have distinct
roles:

| Layer | Location | Role |
|---|---|---|
| Root policy | `AGENTS.md` | Hard repository rules every agent must obey |
| AI runtime config roots | `.agents/**`, `.claude/**`, `.codex/**`, `.gemini/**`, or successor runtime roots | Project-specific AI assets loaded by each runtime |
| AI constitution | Runtime config root | Stable project principles and non-negotiable engineering values for AI runtimes |
| Persona skills | Runtime config root skill directories for the supported personas | Short operational entry points that route work and link to canonical procedures |
| Runtime memory | Runtime config root memory files | Project-specific recall and reusable context; not a hard policy layer |
| Workflow docs | `docs/ai-developer/**` and contributor workflow docs | Procedures used by skills, agents, and contributors |

Skills are pointers and workflow helpers. They must not duplicate or override
root policy. Runtime memory may summarize project facts, but it must not create
hidden requirements or bypass gates. The canonical rule is:

- root policy lives in `AGENTS.md`;
- AI constitution, skills, and memory live in project-local AI runtime config
  directories, with equivalent assets for every supported runtime;
- the AI constitution records stable project principles for repository AI work;
- SpecKit's `.specify/memory/constitution.md` is a separate feature-planning
  artifact and is not the main repository AI constitution;
- all supported AI runtimes must be able to read the same root policy,
  constitution, persona skills, and project memory at equivalent fidelity;
- workflow procedures live under canonical AI developer and contributor docs;
- skills link to those workflows and provide only runtime-specific command
  details;
- `persona_policy` verifies that the declared persona has a matching skill,
  AI constitution, and root-policy reference in that runtime's config root;
- `skill_pointer_sync` verifies that pointers remain valid across runtime
  config roots.

No tool, workflow, skill, or documentation may privilege one AI runtime over
another. A governance rule is valid only if it can be implemented for all
supported runtimes or cleanly degraded into the same report-only diagnostic for
all of them.

### 7.5 AI Restriction Tool Set

The gate record evaluator is the single source of truth for AI restriction
tools. Individual tools may calculate findings, but they must receive their
inputs from the evaluator and must not keep independent rule sets for task
kinds, required checks, local/CI differences, or bypass semantics.

| Risk | Tool or evaluator responsibility |
|---|---|
| Agent work has no gate ledger | `gate_record init` and evaluator ledger discovery |
| Agent stages files outside allowed owner/directive model | Evaluator scope reconciliation using declared scope plus observed diff |
| Agent declares an unsupported persona or runtime-specific policy | `persona_policy.check` called by the evaluator |
| Agent starts from a new issue when an existing issue should be closed | Issue-link checks recorded in the ledger |
| Agent omits required tests or normative checks | Evaluator obligation inference plus ledger check/test events |
| Agent omits required documentation landing | `docs_landing.check` called by the evaluator |
| Agent modifies protected core components without administrator authorization | `core_change_guard` called by the evaluator |
| Agent modifies governance rules without review | `governance_mod_guard` called by the evaluator |
| Agent weakens CI, lint, tests, or thresholds | `weakened_ci_check` called by the evaluator |
| Agent records Sentrux evidence incorrectly | `sentrux_gate` called by the evaluator as advisory or blocking according to the active ADR-042 addendum semantics |
| Agent or PR claims human bypass without maintainer label provenance | `human_bypass_guard` in CI mode |
| Agent writes to the wrong worktree or outside the assigned worktree | `worktree_write_guard` before tool mutation and evaluator reconciliation afterward |
| Test engineer edits production code without authorization | `test_engineer_scope_guard` called by the evaluator |
| Agent edits disallowed paths | Evaluator path allowlist checks in hooks and CI |
| Agent omits required provenance | Gate ledger finalization, commit trailers, and CI issue closure checks |
| Agent attempts to merge a PR | `pr_merge_guard` in CI or merge-automation mode |
| Agent writes weak self-confirming tests | `test_quality` and mutation testing where enabled |

These tools enforce AI-specific process. They do not decide whether code is
correct; correctness remains the responsibility of tests, code review, runtime
validation, and code/documentation consistency tools.

The agent-facing `gate_record` CLI is organized around the workflow, not around
low-level ledger events. Agents must not be asked to manually call one command
per fact, guard, or tool. Internal events such as observed diffs, inferred
obligations, guard results, and sanitized check summaries are recorded
automatically by the workflow-level commands.

The required agent-facing commands are:

| Command | Workflow concern | Agent supplies | Tool automatically does |
|---|---|---|---|
| `init` | Scope And Issue | Task kind, persona, runtime, branch, owner directive, issue seed when known, initial include/exclude scope when known | Creates or updates the ledger, records branch/task identity, initializes lifecycle concerns, records sanitized repo-relative state, and prints task-specific instructions for the selected persona/task/scope |
| `plan` | Plan | Planned files, expected docs/tests/checks, N/A rationales, owner directives, or task-kind profile details | Updates the ledger plan, normalizes fields, observes current diff when useful, and recomputes provisional obligations |
| `amend` | Any concern | Field additions or corrections with rationale | Appends a correction event without running expensive checks; recomputes obligations when the correction affects scope, issues, docs, tests, or checks |
| `check` | Test And Checks | Optional added fields or explicit N/A rationale before running checks | Observes the current git diff, infers the tier-selected CI-equivalent check set, runs the required local commands, records sanitized check events, runs guard reconciliation, writes local-only raw logs if needed, and reports unsatisfied obligations |
| `finalize` | Commit And Submit PR | Commit SHA, PR body path before PR creation, PR URL/number after PR creation, issue closure intent, optional final field updates | Re-observes the diff, runs final reconciliation, records commit provenance before PR creation, records PR provenance after PR creation, verifies issue closure evidence, and reports whether the ledger is PR-ready |

Every command must support additive field updates. For example, if `check`
finds that the observed diff exceeds the previous scope, the agent must be able
to rerun `plan` or `check` with additional scope, docs, tests, or N/A fields.
The tool appends a new event and reconciles again; the agent must not recreate
the ledger from scratch.

The common update surface is:

| Field class | Allowed on commands | Purpose |
|---|---|---|
| owner directive | `init`, `plan`, `amend`, `check`, `finalize` | Record the instruction that justifies current work or scope expansion |
| scope include/exclude | `init`, `plan`, `amend`, `check`, `finalize` | Add or narrow declared scope as the task evolves |
| issue links | `init`, `plan`, `amend`, `check`, `finalize` | Add issues found during debugging or audit |
| docs landing | `plan`, `amend`, `check`, `finalize` | Record docs paths or N/A rationale |
| test evidence or N/A | `plan`, `amend`, `check`, `finalize` | Record changed tests, runtime/e2e evidence, or owner-approved N/A |
| check expectation or N/A | `plan`, `amend`, `check`, `finalize` | Add task-specific checks or accepted N/A rationale |
| requested admin label | `plan`, `amend`, `check`, `finalize` | Record an expected PR label for AI work; local record is not authoritative |

`amend` is the dedicated low-cost edit command for correcting ledger fields
without running the full plan or check flow. It is still append-only: it records
what changed and why, then the evaluator interprets the latest effective state.
It must not silently rewrite or delete old ledger events.

`gate_record check` is the main local parity command. It must not require the
agent to manually run `ruff`, `mypy`, `pytest`, frontend checks, full audit, or
guard commands one by one. The evaluator derives the required check set from
the current diff, task kind, persona, plan, and repository CI configuration;
the command runs that set, records sanitized ledger events, and leaves raw
transcripts only under ignored local paths.

Optional CLI fields are optional at input time only. The evaluator may still
require the corresponding ledger fact before PR readiness. To avoid
guess-and-reject loops, every workflow command that performs reconciliation
must print an "unsatisfied obligations" section with exact follow-up commands
or arguments.

For example, if tests are required but missing, `check` should print a
repo-specific repair hint such as:

```text
Unsatisfied obligations:
- tests.changed-test-required
  Add a changed test path:
  python -m scistudio.qa.governance.gate_record amend \
    --reason "Add regression coverage for #1234" \
    --test-path tests/api/test_file_endpoints.py
```

The expected agent instruction pattern is therefore short:

```text
Start gate record for this task, plan from my directive, implement, run
gate_record check, follow the unsatisfied-obligation repair hints, then
finalize when the ledger is PR-ready.
```

Agents should not try to pre-fill every optional field. They should provide the
known task identity and owner directive at `init`, use `plan` for known scope
and expected artifacts, and rely on `check` to derive the full obligation set
from the real diff.

`init` must also generate task-specific instructions immediately after the
ledger is created. The instruction output is derived from task kind, persona,
strictness tier, initial scope, issues, governance-touch status, and
changed-file hints when available. It tells the agent what fields and evidence
are expected at each workflow concern before the agent starts implementation.

The generated instruction must include:

- task identity and selected persona;
- issue closure expectations;
- scope and owner-directive rules for this task kind;
- likely docs, tests, and checks required by the declared scope;
- whether implementation test changes are expected;
- whether runtime/e2e evidence is expected;
- whether governance/protected-path authorization is likely required;
- which `plan`, `amend`, `check`, and `finalize` arguments the agent is likely
  to need;
- a reminder that `check` will infer the final tier-selected check obligations
  from the actual diff.

The instruction is guidance, not a substitute for reconciliation. It reduces
avoidable missing-field loops, while `check` remains the authoritative
candidate-specific evaluator.

CI uses the same evaluator in CI mode. CI may invoke an internal entry point or
`gate_record check --mode ci`, but that is workflow plumbing, not an additional
manual agent step.

Bypass and administrator authorization use explicit labels, not free-form text
or review references.

| Field | Allowed values | Authority |
|---|---|---|
| `--admin-label` | `admin-approved:bypass`, `admin-approved:core-change`, `admin-approved:merge` | Local mode records requested or expected label only; CI mode verifies observed PR label and actor provenance |

The evaluator must distinguish the AI-admin labels:

| Label | Satisfies | Does not satisfy |
|---|---|---|
| `admin-approved:bypass` | Bypass AI gate workflow steps when CI verifies provenance | Branch protection, normal CI quality jobs, owner review |
| `admin-approved:core-change` | Protected core path authorization only | Scope, issue linkage, docs landing, check evidence, receipt/ledger validity, tier-selected checks |
| `admin-approved:merge` | Authorization for AI-assisted merge into `origin/main` only | Tests, docs, audit, workflow-gate correctness, owner review |

The ledger may store requested labels before the PR exists so local tools can
explain what will be needed. It must not treat requested labels as verified.
Only CI can promote a requested label into an observed authorization event after
reading PR labels and verifying actor permissions.

Human-authored work is outside the AI gate-record workflow. A human developer
may commit and open a PR without a gate record, without AI commit trailers, and
without being blocked by ADR-042 AI governance hooks or guards. The
`human-authored` label is a PR-level CI signal, not a `gate_record` CLI field.
When CI observes a maintainer/admin-applied `human-authored` label and no AI
evidence requires normal AI gate handling, CI skips AI-only harness checks for
that PR. Repository quality checks, security checks, tests, docs checks, branch
protection, and normal review still run according to repository policy.

Compatibility aliases for older commands may exist during migration, but they
must delegate to the ledger implementation.

The complete callable CLI contract is:

#### `init`

Create or update the ledger for the current task.

```bash
python -m scistudio.qa.governance.gate_record init \
  --task-kind hotfix|bugfix|feature|refactor|docs|maintenance|manager|guided \
  --persona manager|implementer|adr_author|audit_reviewer|test_engineer|live_implementer \
  --runtime codex|claude-code|gemini|<runtime-id> \
  --branch <branch> \
  --owner-directive "<owner instruction>" \
  --slug <short-task-slug> \
  --session-id <local-session-id> \
  --issue <number> \
  --include <path-or-glob> \
  --exclude <path-or-glob> \
  --governance-touch true|false
```

Arguments:

| Argument | Required | Repeatable | Meaning |
|---|---:|---:|---|
| `--record` | no | no | Optional explicit committed ledger path under `.workflow/records/`; normally generated automatically |
| `--task-kind` | yes | no | Task profile |
| `--persona` | yes | no | Persona profile |
| `--runtime` | yes | no | AI runtime executing the task (Codex, Claude Code, Gemini, or a local CLI agent) |
| `--branch` | yes | no | Branch this ledger governs |
| `--owner-directive` | yes | yes | Initial or additional owner instruction |
| `--slug` | no | no | Short human-readable task slug used for generated record path |
| `--session-id` | no | no | Local session identifier under `.git/scistudio/gates/`; generated automatically when omitted |
| `--issue` | no | yes | GitHub issue number linked to the task |
| `--include` | no | yes | Declared in-scope repo-relative path or glob |
| `--exclude` | no | yes | Declared out-of-scope repo-relative path or glob |
| `--governance-touch` | no | no | Whether governance surfaces may be changed |
| `--print-instructions` | no | no | Print task-specific instructions after init; default true |
| `--instructions-output` | no | no | Optional repo-relative path to also write the generated instructions |

When `--record` is omitted, `init` creates the ledger path automatically under
`.workflow/records/`. The generated path should prefer
`.workflow/records/<issue>-<slug>.json` when an issue is known and
`.workflow/records/<branch-slug>-<slug>.json` otherwise. If `--slug` is omitted,
the tool derives a stable slug from the branch name or owner directive.

`init` prints the selected ledger path. It may be rerun for the same task to
append issues, directives, or scope fields. It must not erase earlier ledger
events.

`init` also prints generated task instructions by default. If
`--instructions-output` is provided, the same instructions are written to a
repo-relative path suitable for local use or committed planning docs when the
gate plan explicitly includes that path.

#### `plan`

Append or amend planning fields without running the full check set.

```bash
python -m scistudio.qa.governance.gate_record plan \
  --owner-directive "<scope or plan update>" \
  --include <path-or-glob> \
  --exclude <path-or-glob> \
  --issue <number> \
  --docs-updated <path> \
  --docs-na "<class>:<rationale>" \
  --test-path <path> \
  --test-na "<class>:<rationale>" \
  --check <check-name> \
  --check-na "<check-name>:<rationale>" \
  --admin-label admin-approved:bypass|admin-approved:core-change|admin-approved:merge
```

Arguments:

| Argument | Required | Repeatable | Meaning |
|---|---:|---:|---|
| `--record` | no | no | Optional explicit ledger path; normally auto-discovered from current branch |
| `--owner-directive` | no | yes | Owner or manager instruction that changes plan or scope |
| `--include` | no | yes | Add declared in-scope path or glob |
| `--exclude` | no | yes | Add declared out-of-scope path or glob |
| `--issue` | no | yes | Add issue link |
| `--docs-updated` | no | yes | Repo-relative docs/spec/ADR/changelog/checklist path |
| `--docs-na` | no | yes | Documentation class plus rationale |
| `--test-path` | no | yes | Changed or expected test/runtime/e2e evidence path |
| `--test-na` | no | yes | Test class plus rationale |
| `--check` | no | yes | Add an expected check beyond inferred tier-selected obligations |
| `--check-na` | no | yes | Check name plus accepted N/A rationale |
| `--admin-label` | no | yes | Requested or expected admin label: `admin-approved:bypass`, `admin-approved:core-change`, or `admin-approved:merge` |

When `--record` is omitted, `plan` discovers the active ledger for the current
branch. Discovery must fail with a clear error if zero or multiple active
ledgers match. `plan` observes the current diff when available and recomputes
provisional obligations, but it does not run expensive checks.

#### `amend`

Append a correction or field update to the ledger.

```bash
python -m scistudio.qa.governance.gate_record amend \
  --reason "<why the ledger is being corrected>" \
  --owner-directive "<new or corrected owner instruction>" \
  --task-kind hotfix|bugfix|feature|refactor|docs|maintenance|manager|guided \
  --persona manager|implementer|adr_author|audit_reviewer|test_engineer|live_implementer \
  --branch <branch> \
  --issue <number> \
  --remove-issue <number> \
  --include <path-or-glob> \
  --exclude <path-or-glob> \
  --remove-include <path-or-glob> \
  --remove-exclude <path-or-glob> \
  --governance-touch true|false \
  --docs-updated <path> \
  --docs-na "<class>:<rationale>" \
  --test-path <path> \
  --test-na "<class>:<rationale>" \
  --check <check-name> \
  --check-na "<check-name>:<rationale>" \
  --admin-label admin-approved:bypass|admin-approved:core-change|admin-approved:merge \
  --record .workflow/records/<record>.json
```

Arguments:

| Argument | Required | Repeatable | Meaning |
|---|---:|---:|---|
| `--record` | no | no | Optional explicit ledger path; normally auto-discovered from current branch |
| `--reason` | yes | no | Human-readable reason for the amendment |
| `--owner-directive` | no | yes | Add or correct owner instruction |
| `--task-kind` | no | no | Correct task kind when the original classification was wrong |
| `--persona` | no | no | Correct persona when routing changes |
| `--branch` | no | no | Correct branch metadata |
| `--issue` | no | yes | Add issue link |
| `--remove-issue` | no | yes | Mark an issue link as superseded or added in error |
| `--include` | no | yes | Add declared in-scope path or glob |
| `--exclude` | no | yes | Add declared out-of-scope path or glob |
| `--remove-include` | no | yes | Mark an include pattern as superseded |
| `--remove-exclude` | no | yes | Mark an exclude pattern as superseded |
| `--governance-touch` | no | no | Correct governance-touch declaration |
| `--docs-updated` | no | yes | Add docs landing path |
| `--docs-na` | no | yes | Add docs N/A rationale |
| `--test-path` | no | yes | Add test/runtime/e2e evidence path |
| `--test-na` | no | yes | Add test N/A rationale |
| `--check` | no | yes | Add expected check |
| `--check-na` | no | yes | Add check N/A rationale |
| `--admin-label` | no | yes | Add expected admin label |

When `--record` is omitted, `amend` discovers the active ledger for the current
branch. `amend` observes the current diff only when the amended field affects
scope, obligations, or protected-path evaluation. It does not run expensive
checks.

#### `check`

Run tier-selected local CI checks and reconcile the ledger.

```bash
python -m scistudio.qa.governance.gate_record check \
  --base origin/main \
  --head HEAD \
  --mode local \
  --pr-body-file .workflow/local/pr-body.md \
  --owner-directive "<late scope update>" \
  --include <path-or-glob> \
  --exclude <path-or-glob> \
  --issue <number> \
  --docs-updated <path> \
  --docs-na "<class>:<rationale>" \
  --test-path <path> \
  --test-na "<class>:<rationale>" \
  --check <check-name> \
  --check-na "<check-name>:<rationale>" \
  --admin-label admin-approved:bypass|admin-approved:core-change|admin-approved:merge \
  --only <check-name> \
  --skip-execution
```

Arguments:

| Argument | Required | Repeatable | Meaning |
|---|---:|---:|---|
| `--record` | no | no | Optional explicit ledger path; normally auto-discovered from current branch |
| `--base` | no | no | Base ref for diff; default `origin/main` |
| `--head` | no | no | Head ref for diff; default `HEAD` |
| `--mode` | no | no | `local`, `pre-push`, `pre-pr`, or `ci`; default `local` |
| `--pr-body-file` | no | no | Intended PR body file for pre-PR issue-closure checks |
| `--owner-directive` | no | yes | Late owner instruction or scope update |
| `--include` | no | yes | Add declared in-scope path or glob before reconciliation |
| `--exclude` | no | yes | Add declared out-of-scope path or glob before reconciliation |
| `--issue` | no | yes | Add issue link before reconciliation |
| `--docs-updated` | no | yes | Record docs landing before reconciliation |
| `--docs-na` | no | yes | Record docs N/A rationale before reconciliation |
| `--test-path` | no | yes | Record test/runtime/e2e evidence path before reconciliation |
| `--test-na` | no | yes | Record test N/A rationale before reconciliation |
| `--check` | no | yes | Add a task-specific required check before inference |
| `--check-na` | no | yes | Record accepted N/A rationale for a check |
| `--admin-label` | no | yes | Requested or expected admin label; local mode records intent only, CI verifies provenance |
| `--only` | no | yes | Run only selected checks for recovery; reconciliation must still report missing obligations |
| `--skip-execution` | no | no | Reconcile ledger without running commands; never sufficient for final PR readiness unless all obligations are already satisfied |

`check` automatically:

1. observes the current git diff;
2. infers required checks from changed files, task kind, persona, plan, and CI
   configuration;
3. runs all required local commands unless `--only` or `--skip-execution` is
   used;
4. writes raw transcripts only under ignored local paths;
5. records sanitized check events in the committed ledger;
6. runs all applicable guards through the shared evaluator;
7. records a reconciliation event;
8. exits nonzero when required obligations remain unsatisfied.

When `--record` is omitted, `check` discovers the active ledger for the current
branch. Discovery must be deterministic: exactly one current-branch ledger is
accepted, zero ledgers reports "run init", and multiple ledgers reports the
candidate paths and asks for `--record`.

`gate_record check` is the local CI-equivalent preflight runner for the current
candidate. A normal agent should be able to call it once and get every required
local check for the selected tier. The command must not rely on the agent
remembering to run separate lint, type, test, docs, audit, frontend, or guard
commands.

The core promise is local/CI agreement at the strictness level selected by the
task kind. GitHub Actions workflow definitions, or a generated check manifest
derived from those workflows, are the source of command truth. Local check
inference must align upward to CI. The local implementation must not maintain a
looser hand-written copy of CI behavior.

The required check set is derived from three inputs:

1. strictness tier from task kind, possibly escalated by observed diff per
   Section 7.6;
2. observed changed-file surfaces from git.
3. the current CI workflow graph and path filters.

The evaluator starts from the tier baseline, reads the CI graph, and then
selects jobs/commands:

- Tier 1 runs a full local mirror of the repository's merge-blocking CI command
  surfaces, whether or not the observed diff appears to need every job.
- Tier 2 runs most CI command surfaces: the common governance/lint/audit
  baseline plus all CI jobs that are relevant to the observed diff.
- Tier 3 runs only mandatory checks for the observed diff and repository gate
  rules.

When CI uses path filters, the local selector must use the same filters. PR-only
review automation that has no local readiness command is recorded as PR-only
and is not treated as a local `check` failure. If the local tool cannot parse a
workflow or cannot map a required CI job to a local command, it must fail closed
for PR readiness and explain the missing local parity mapping.

Current CI command-source snapshot:

| CI workflow/job | CI command or behavior | Local `gate_record check` behavior |
|---|---|---|
| `ci.yml` / `Lint & Format` | `ruff check .`; `ruff format --check .` | Tier 1 and Tier 2 baseline; Tier 3 when Python/source/test/config surfaces are changed |
| `ci.yml` / `Type Check` | `mypy src/scistudio/ --ignore-missing-imports` on Python 3.13 when `src/scistudio` exists | Tier 1 baseline; Tier 2 and Tier 3 when Python source or QA/governance source surfaces are changed |
| `ci.yml` / `Architecture Tests` | `pytest tests/architecture/ -v --no-cov` | Tier 1 baseline; Tier 2 and Tier 3 when architecture contracts, import boundaries, or architecture-governed files are affected |
| `ci.yml` / `Full Audit` | `PYTHONPATH=src python -m scistudio.qa.audit.full_audit --repo-root . --format json --output .audit/full-audit.json` | Tier 1, Tier 2, and Tier 3 baseline for AI-authored work |
| `ci.yml` / `Test (Python 3.11, 3.13)` | Python 3.13: `timeout 600 pytest -n auto --timeout=60 --timeout-method=thread`; Python 3.11: same with `--no-cov` | Tier 1 baseline; Tier 2 and Tier 3 when Python implementation, tests, runtime, package, or tooling behavior surfaces are affected |
| `ci.yml` / `Import Contracts` | `lint-imports` when `src/scistudio` exists | Tier 1 baseline; Tier 2 and Tier 3 when Python source, architecture, package-boundary, or import-contract surfaces are affected |
| `ci.yml` / `Frontend` | In `frontend/`: `npm ci`, `npm run lint`, `npm run format:check`, `npm run typecheck`, `npm test`, `npm run build`; then frontend/dist freshness check | Tier 1 baseline; Tier 2 and Tier 3 when frontend source/config/test/dist surfaces are affected |
| `ci.yml` / `Wheel Release Smoke` | Build frontend, copy `frontend/dist` into package static assets, build wheel, inspect SPA contents, install wheel, smoke-test GUI root | Tier 1 baseline; Tier 2 and Tier 3 when packaging/release/static bundle surfaces are affected |
| `workflow-gate.yml` / `Verify Workflow Compliance` | Validate gate records, human bypass, labels, issue/docs/scope/guard orchestration, mod/core/merge/weakened-CI checks, Sentrux advisory warnings | Tier 1, Tier 2, and Tier 3 baseline; facts that cannot exist before PR creation are represented as explicit pre-PR mode gaps |
| `semantic-dup-scan.yml` / `Semantic duplication ratchet` | Path-filtered scan for `src/scistudio/**/*.py`, `scripts/semantic_dup_scan.py`, semantic baseline/addendum/workflow files | Run `python scripts/semantic_dup_scan.py --check docs/audit/baselines/semantic-dup-baseline.json --out <local-log> --json-out <local-json>` when the workflow path filters match; Tier 1 may also run it as a full-mirror diagnostic |
| `ai-review.yml` / `Codex PR Review` | AI review automation on PRs | Not a local readiness command; it is PR-only review automation and does not become a local `gate_record check` obligation |

Tier controls both up-front gate evidence and local check breadth. Observed diff
and CI graph still add mandatory commands inside each tier. For example, Tier 3
docs does not run backend pytest for a docs-only diff because Python test
execution is not mandatory for that candidate; Tier 1 does run backend pytest
because Tier 1 mirrors the full merge-blocking CI command surface.

Tier 2 and Tier 3 use surface-specific selection from the CI graph:

| Source | Required local checks |
|---|---|
| Python source under `src/**` | CI lint/format, typecheck, Python test matrix, import contracts when import surfaces are affected |
| Python tests under `tests/**` | CI lint/format plus Python test matrix or relevant CI-equivalent subset for recovery; final readiness must satisfy the matrix obligation |
| QA/governance source under `src/scistudio/qa/**` | Python source checks plus workflow-gate/shared evaluator checks and full audit when governance surfaces are affected |
| ADR/spec/architecture/governed Markdown | Full audit and workflow-gate docs/closure checks |
| AI developer workflow docs under `docs/ai-developer/**` | Treated as governance docs: full audit and workflow-gate docs/closure checks, plus persona/skill-pointer and `governance_touch` checks when persona or routing docs change |
| Docs-only non-governance Markdown | Only CI jobs mapped to that docs surface; do not add unrelated pytest |
| Frontend source/config/tests/dist | CI frontend job commands and dist freshness check |
| GitHub workflow or hook files | Workflow-gate guard orchestration, weakened-CI check, mod guard, and any workflow syntax checks configured in CI |
| Packaging/build/release files | Wheel release smoke job or its exact local equivalent |
| Semantic duplication path filters | Semantic duplication ratchet workflow command |
| Protected core paths | CI-equivalent Python/runtime tests for the affected surface plus required admin-label validation |

For example, a Tier 3 docs-only change to an ADR or spec should run the docs
and full-audit checks for that surface, but it should not run backend pytest
solely because the repository has Python tests. If the same change also edits
Python source, the observed diff adds Python lint/type/test obligations.

`--only` is a recovery aid, not a final readiness mode. A final PR-ready
`check` must run or validate the complete tier-selected check set.
`--skip-execution` may only reconcile already recorded valid check events; it
cannot create final readiness when required check evidence is absent or stale.

#### `finalize`

Record commit and PR provenance and perform final reconciliation.

`finalize` has two valid modes:

- **pre-PR finalize** records the current commit candidate and intended PR body
  before the PR exists. It must not require `--pr`.
- **post-PR finalize** records the PR URL or number after the PR exists. It
  must not be required before PR creation.

```bash
python -m scistudio.qa.governance.gate_record finalize \
  --base origin/main \
  --head HEAD \
  --commit <sha> \
  --pr-body-file .workflow/local/pr-body.md \
  --closes "#<issue>" \
  --owner-directive "<final owner instruction>" \
  --include <path-or-glob> \
  --exclude <path-or-glob> \
  --issue <number> \
  --docs-updated <path> \
  --docs-na "<class>:<rationale>" \
  --test-path <path> \
  --test-na "<class>:<rationale>" \
  --admin-label admin-approved:bypass|admin-approved:core-change|admin-approved:merge

python -m scistudio.qa.governance.gate_record finalize \
  --commit <sha> \
  --pr <url-or-number> \
  --pr-body-file .workflow/local/pr-body.md
```

Arguments:

| Argument | Required | Repeatable | Meaning |
|---|---:|---:|---|
| `--record` | no | no | Optional explicit ledger path; normally auto-discovered from current branch |
| `--base` | no | no | Base ref for final diff; default `origin/main` |
| `--head` | no | no | Head ref for final diff; default `HEAD` |
| `--commit` | yes | yes | Commit SHA included in the candidate or PR |
| `--pr` | conditional | no | PR URL or number; required only for post-PR finalization |
| `--pr-body-file` | conditional | no | Intended or actual PR body used for issue-closure validation; required before PR creation |
| `--closes` | no | yes | Issue closure token, e.g. `#1234` |
| `--owner-directive` | no | yes | Final owner instruction or rationale |
| `--include` | no | yes | Last allowed scope addition before reconciliation |
| `--exclude` | no | yes | Last excluded scope addition before reconciliation |
| `--issue` | no | yes | Add issue link before final reconciliation |
| `--docs-updated` | no | yes | Record docs landing before final reconciliation |
| `--docs-na` | no | yes | Record docs N/A rationale before final reconciliation |
| `--test-path` | no | yes | Record test/runtime/e2e evidence before final reconciliation |
| `--test-na` | no | yes | Record test N/A rationale before final reconciliation |
| `--admin-label` | no | yes | Expected admin label; authoritative only when CI observes it on the PR |

Pre-PR `finalize` must re-observe the current diff, validate the intended PR
body, and rerun reconciliation without requiring a PR URL or number. It records
that the candidate is ready to open a PR if all non-PR-state obligations pass.

Post-PR `finalize` records the PR URL or number and reruns reconciliation with
PR metadata when available. It fails when checks are stale, required issue
closure is missing from the PR body, required docs or tests are absent, or
tier-selected check obligations are unsatisfied.

When `--record` is omitted, `finalize` discovers the active ledger for the
current branch using the same rule as `check`.

#### Shared Exit Codes

| Exit code | Meaning |
|---:|---|
| 0 | Command completed and current reconciliation passed, when applicable |
| 1 | Command completed but current reconciliation failed |
| 2 | Invalid CLI usage or unsupported argument combination |
| 3 | Ledger schema or migration error |
| 4 | Required external tool unavailable and no accepted N/A rationale exists |
| 5 | Privacy/sanitization violation in a would-be committed ledger event |

### 7.6 Gate Strictness Tiers

Gate strictness tiers are derived from task kind and then escalated by the
observed diff. They do not change the repository CI quality bar. They define how
much gate workflow structure must be declared before implementation, before
checks, and before PR readiness.

Tier numbers run from strict to light:

| Tier | Meaning | Task kinds | Workflow expectation |
|---|---|---|---|
| Tier 1 | Strict gate | `feature`, `refactor`; any task escalated by observed diff (see below) | The task should be planned before implementation. Scope, issue, expected tests, docs impact, and expected checks must be declared early. `check` must run a full local mirror of merge-blocking CI command surfaces. Missing plan fields are hard failures before PR readiness. |
| Tier 2 | Standard gate | `bugfix`, `hotfix`, `maintenance`, default `guided` | The task may discover details during debugging. `hotfix` and `guided` may delay full gate completion during the live session, but issue linkage, scope/directive coverage, regression/test evidence, docs impact, governance/lint/audit baseline, and changed-surface CI checks must reconcile before commit, push, or PR readiness. |
| Tier 3 | Lightweight gate | `docs`, `manager` | The task may start with a sparse plan or coordination directive. `check` runs only mandatory checks for the observed diff and repository gate rules. The final observed diff must still satisfy issue, docs/test N/A, admin-label, and mandatory check obligations. |

The evaluator derives `strictness_tier` in two steps; agents never choose a tier
directly. First it assigns a baseline tier from `task_kind`. Then it escalates
(never lowers) that tier based on the observed implementation: any task whose
observed diff touches protected core or runtime/engine paths, governance or
workflow files, or constitutes a broad cross-module change is raised to Tier 1,
regardless of its starting `task_kind`. A Tier 3 `docs` task that ends up
editing protected core code, or a Tier 2 `maintenance` task that rewrites a
governance surface, is evaluated at Tier 1. `guided` is the most common
escalation case — it defaults to Tier 2 as an implementation mode and escalates
to Tier 1 for feature, core/runtime, governance, or broad-refactor work — but
the escalation rule applies to every task kind. Beyond tier escalation, changed
files may also add specific obligations such as protected-path authorization,
governance checks, frontend checks, or runtime/e2e evidence.

Tier behavior:

| Concern | Tier 1 | Tier 2 | Tier 3 |
|---|---|---|---|
| `init` | Requires issue when known, branch, owner directive, persona, task kind, and initial scope | Requires branch, owner directive, persona, task kind; issue and scope may be completed during plan/check | Requires branch, owner directive, persona, task kind; issue and scope may be completed later |
| `plan` | Required before implementation or broad edits; must declare expected docs/tests/checks or N/A | Required before final check; may be partial during debugging | Optional unless the evaluator needs early docs/tests/scope guidance |
| `amend` | Allowed, but every scope or obligation correction needs a reason | Normal way to add discovered scope, tests, docs, or issues | Normal way to record live owner directives and late discovered fields |
| `check` | Must run the full merge-blocking CI mirror; `--only` is recovery-only and not final | Must run the common governance/lint/audit baseline plus all changed-surface CI checks for PR readiness | Must run only mandatory checks for the observed diff and repository gate rules; sparse planning does not reduce mandatory checks |
| `finalize` | Fails if any plan/test/docs/check/issue field is missing | Fails if current observed diff lacks issue/test/docs/check reconciliation | Fails if current observed diff lacks issue/test/docs/check reconciliation |
| N/A rationale | Must be specific and tied to owner directive, ADR, spec, or issue | Must be specific enough for review | May be shorter, but must still be explicit and reviewable |
| Admin label | Required for protected core, AI gate bypass, or merge automation | Same as Tier 1 | Same as Tier 1 |

Tier 3 is not a quality bypass. It only allows less up-front ceremony and a
minimal local check set. The final `check` and `finalize` reconciliation still
enforce mandatory obligations and repository protection rules.

Tier-specific CLI requiredness is:

| Command | Tier 1 required ledger facts | Tier 2 required ledger facts | Tier 3 required ledger facts |
|---|---|---|---|
| `init` | `--task-kind`, `--persona`, `--branch`, `--owner-directive`, `--issue`, at least one `--include` | `--task-kind`, `--persona`, `--branch`, `--owner-directive`; `--issue` and `--include` may be added later if unknown | `--task-kind`, `--persona`, `--branch`, `--owner-directive`; issue and scope may be added by `plan`, `amend`, `check`, or `finalize` |
| `plan` | Before implementation/check: `--include`, `--test-path` or `--test-na`, `--docs-updated` or `--docs-na`, expected `--check` when not inferable | Before PR readiness: `--include`, `--test-path` or `--test-na`, `--docs-updated` or `--docs-na` as applicable | Optional unless the evaluator needs early scope/docs/test guidance; missing facts may be repaired after `check` |
| `amend` | Requires `--reason`; used to add or supersede any required fact with rationale | Requires `--reason`; normal repair path for discovered scope/issues/tests/docs | Requires `--reason`; normal repair path for live owner directives and late fields |
| `check` | Must run the full local CI mirror for PR readiness; `--only` and `--skip-execution` are recovery-only | Must run the Tier 2 baseline plus all changed-surface checks for PR readiness; `--only` and `--skip-execution` are recovery-only | Must run mandatory diff/gate checks for PR readiness; sparse planning does not reduce mandatory check execution |
| `finalize` pre-PR | `--commit`, `--pr-body-file`, `--closes` for each closing issue; all Tier 1 plan facts must already reconcile | `--commit`, `--pr-body-file`, `--closes` for each closing issue; all Tier 2 required facts must reconcile | `--commit`, `--pr-body-file`, `--closes` for each closing issue; all observed-diff obligations must reconcile |
| `finalize` post-PR | `--commit`, `--pr`, `--pr-body-file` | Same as Tier 1 | Same as Tier 1 |

CLI arguments marked optional in the syntax tables are optional for command
parsing only. The evaluator enforces the tier-required ledger facts above
before PR readiness.

For `hotfix` and `guided`, Tier 2 permits live editing before the ledger is
complete. That allowance ends at commit, push, and PR creation boundaries. At
those boundaries, the evaluator treats missing issue linkage, unexplained
observed diff, missing docs/test N/A, stale checks, or missing admin labels as
hard failures.

### 7.7 Task And Persona Obligation Matrix

The evaluator must derive instructions and final checks from the same
obligation matrix. The matrix below defines what each task kind and persona
must provide at each workflow concern.

`init` and `plan` obligations are instruction-time obligations: the tool should
tell the agent what to provide early. `check` and `finalize` obligations are
gate obligations: the evaluator must fail when they are missing and no accepted
N/A rationale or required admin label exists.

#### 7.7.1 Task-Kind Matrix

| Task kind | `init` fields | `plan` fields | `amend` use | `check` obligations | `finalize` obligations |
|---|---|---|---|---|---|
| `hotfix` | Tier 2; `task_kind`, `persona`, `branch`, owner directive, issue when known, initial scope when known; full gate may be incomplete during live diagnosis | Fixed bug list, likely changed surfaces, expected regression tests or N/A, docs N/A or docs paths; may be completed after diagnosis | Add discovered issues, scope expansion, test paths, docs impact, or owner directive from live debugging | Before commit/push/PR: actual diff must be explained by directive/scope; targeted regression or owner-approved N/A; Tier 2 baseline plus changed-surface checks; docs landing or N/A | Close every fixed issue or record owner-approved follow-up; record commit; pre-PR body must contain closure intent |
| `bugfix` | Tier 2; `task_kind`, `persona`, `branch`, owner directive, issue required unless owner says issue is being created | Bug reproduction path, affected files, expected regression test, docs impact | Add scope or test path when debugging finds the real surface | Regression test required unless N/A is explicit; implementation changes require test evidence; Tier 2 baseline plus changed-surface checks; docs landing when behavior or public contract changes | PR body closes the bug issue; commit and PR provenance recorded |
| `feature` | Tier 1; `task_kind`, `persona`, `branch`, owner directive, issue, initial feature scope | Planned files, tests, docs/spec/ADR impact, runtime/e2e expectation when user-visible | Add scope, docs/spec paths, tests, or owner-approved scope change | Implementation tests required; docs/spec/ADR required when contracts, schemas, runtime behavior, API, UI semantics, or storage change; full local CI mirror required | PR closes feature issue; final ledger names docs/tests/check evidence |
| `refactor` | Tier 1; `task_kind`, `persona`, `branch`, owner directive, issue, refactor scope | Behavior-preservation strategy, affected modules, tests proving unchanged contracts | Add affected files discovered during refactor | Tests must cover affected contracts or N/A must explain why unchanged behavior is proven another way; full local CI mirror required; docs only when architecture or public shape changes | PR states behavior-preserving intent and closes issue |
| `docs` | Tier 3; `task_kind`, `persona`, `branch`, owner directive, issue when known, docs scope | Docs paths, governing ADR/spec links, docs checks, implementation tests N/A by default | Add docs paths or N/A rationales | Frontmatter/structure/full-audit checks as applicable; implementation tests N/A unless code changes appear in observed diff | PR closes docs issue; final ledger records docs landing |
| `maintenance` | Tier 2; `task_kind`, `persona`, `branch`, owner directive, issue, maintenance surface | Tool/config/package/workflow scope, expected checks, protected-rule impact | Add affected config, workflow, QA, or package scope | Tier 2 baseline plus changed-surface checks; escalates to full local CI mirror when the diff touches protected, governance, runtime, or workflow surfaces; governance weakening/protected checks when applicable; tests for tooling behavior when implementation changes | PR closes maintenance issue and records check evidence |
| `manager` | Tier 3; `task_kind`, `persona=manager`, branch, owner directive, tracking issue | Coordination artifacts, dispatch/checklist/evidence paths, product-code N/A by default | Add report paths, checklist paths, issue links, or owner scheduling decisions | Product code changes fail unless explicit owner directive changes task shape; manager evidence/checklist docs must be recorded; mandatory changed-file checks required | PR closes or updates tracking issue; final ledger records coordination evidence |
| `guided` | Tier 2 by default, Tier 1 for feature/core/runtime/governance/broad-refactor work; `task_kind=guided`, `persona=live_implementer`, branch, owner directive, issue when known, initial scope when known; full gate may be incomplete during live owner-guided work | Current owner instructions, likely scope, known docs/tests/checks; plan may be partial only while scope is still emerging | Primary command for recording new owner directives, new scope, issues, docs/tests/check fields during live work | Before commit/push/PR: actual diff must be explainable by owner directive events; Tier 2 baseline plus changed-surface checks by default, or full local CI mirror when escalated to Tier 1 | PR cannot open until current diff, issue linkage, docs/tests/checks, and closure intent reconcile |

#### 7.7.2 Persona Matrix

| Persona | `init` fields | `plan` fields | `amend` use | `check` obligations | `finalize` obligations |
|---|---|---|---|---|---|
| `manager` | `persona=manager`, owner directive, tracking issue, coordination scope | Dispatch/checklist/report paths, integration/e2e evidence expectations | Add delegated issue links, checklist paths, or owner scheduling updates | Product-code changes blocked unless separately authorized; coordination evidence and changed-file checks required | Final PR or report must name evidence and issue status |
| `implementer` | `persona=implementer`, task kind, issue, implementation scope | Planned implementation files, tests, docs/spec impacts, expected checks | Add discovered implementation surfaces, tests, docs, or owner-approved scope changes | Implementation changes require test evidence; docs/spec updates required for contract/runtime/API/storage/UI changes; tier-selected checks required | Final ledger records tests/docs/checks and issue closure |
| `adr_author` | `persona=adr_author`, issue, governed docs scope | ADR/spec/docs files, document standard checks, implementation N/A when docs-only | Add governed files, related ADR/spec links, docs N/A rationales | Frontmatter/structure/full-audit checks required; source changes fail unless scope explicitly includes tooling or schema implementation | Final ledger records docs landing and issue closure |
| `audit_reviewer` | `persona=audit_reviewer`, audit issue or tracking issue, read-only scope by default | Audit report paths, target artifacts, expected checks to inspect | Add finding report paths, issue links, or owner-approved fix scope | Product changes blocked unless owner changes persona/scope; audit report evidence required; checks for changed docs/reports required | Final ledger records findings, evidence, and issue disposition |
| `test_engineer` | `persona=test_engineer`, issue, test/evidence scope | Test files, fixtures, runtime/e2e evidence paths, production-code N/A by default | Add test/evidence paths or owner-approved production-code exception | Production code blocked by `test_engineer_scope_guard` unless explicitly authorized; test/runtime/e2e evidence required according to task | Final ledger records test evidence and any handoff/fix issue closure |
| `live_implementer` | `persona=live_implementer`, `task_kind=guided`, branch, owner directive, issue when known | Initial live-work plan, expected docs/tests/checks when known | Primary way to record new owner instructions, scope expansions, issue additions, and N/A rationales | Same quality obligations as implementer for the selected tier; dynamic scope allowed only through directive events; tier-selected checks required | Final ledger proves the live session reached ordinary PR readiness |

#### 7.7.3 Field Semantics

The evaluator treats fields as follows:

| Field | Required before PR readiness when |
|---|---|
| `issue` | Always, unless the task is an explicitly owner-approved exploratory audit that produces no PR |
| `owner_directive` | Always |
| `persona` | Always |
| `runtime` | Always |
| `session_id` | Optional; generated automatically when omitted |
| `task_kind` | Always |
| `branch` | Always |
| `include` / declared scope | Required for planned task kinds; optional at `guided` start but final observed diff must be explained by directive events or amended scope |
| `docs-updated` or `docs-na` | Required when docs, contracts, schemas, runtime behavior, API behavior, UI semantics, governance, or user-visible behavior change |
| `test-path` or `test-na` | Required when implementation, runtime, frontend, tooling, workflow, or package behavior changes |
| `check` evidence | Required for every tier-selected check obligation |
| `admin-label` | Required when protected core paths, governance weakening, AI gate bypass, or merge automation are involved |
| `pr-body-file` | Required for pre-PR finalization so issue closure can be validated before opening the PR |
| `pr` | Required only after the PR exists |

#### 7.7.4 Task-Kind CLI Argument Profiles

The instruction generator must emit command guidance using these argument
profiles. Angle-bracket values are placeholders; bracketed groups are included
when the task evidence exists or the evaluator requires it.

| Task kind | `init` arguments | `plan` arguments | `amend` arguments | `check` arguments | `finalize` arguments |
|---|---|---|---|---|---|
| `hotfix` | `init --task-kind hotfix --persona <persona> --branch <branch> --owner-directive "<hotfix directive>" [--issue <n>] [--include <path>] [--exclude <path>] [--governance-touch true]` | `plan --owner-directive "<bug list or hotfix plan>" --include <path> [--issue <n>] --test-path <path> OR --test-na "<class>:<rationale>" --docs-updated <path> OR --docs-na "<class>:<rationale>" [--admin-label <label>]` | `amend --reason "<new bug/scope/test/docs found>" [--owner-directive "<directive>"] [--issue <n>] [--include <path>] [--exclude <path>] [--test-path <path>] [--docs-updated <path>] [--docs-na "<class>:<rationale>"] [--admin-label <label>]` | `check --base <base> --head HEAD [--owner-directive "<late directive>"] [--include <path>] [--issue <n>] [--test-path <path>] [--docs-na "<class>:<rationale>"] [--admin-label <label>]` | Pre-PR: `finalize --base <base> --head HEAD --commit <sha> --pr-body-file <path> --closes "#<n>"`; post-PR: `finalize --commit <sha> --pr <url-or-number> --pr-body-file <path>` |
| `bugfix` | `init --task-kind bugfix --persona <persona> --branch <branch> --owner-directive "<bug directive>" --issue <n> [--include <path>] [--exclude <path>]` | `plan --include <path> --test-path <regression-test> OR --test-na "<class>:<rationale>" --docs-updated <path> OR --docs-na "<class>:<rationale>" [--check <name>]` | `amend --reason "<debugging changed scope/evidence>" [--include <path>] [--test-path <path>] [--docs-updated <path>] [--docs-na "<class>:<rationale>"] [--check <name>]` | `check --base <base> --head HEAD [--test-path <path>] [--docs-na "<class>:<rationale>"]` | Pre-PR: `finalize --base <base> --head HEAD --commit <sha> --pr-body-file <path> --closes "#<issue>"`; post-PR: `finalize --commit <sha> --pr <url-or-number> --pr-body-file <path>` |
| `feature` | `init --task-kind feature --persona <persona> --branch <branch> --owner-directive "<feature directive>" --issue <n> --include <path> [--exclude <path>]` | `plan --include <implementation-path> --test-path <test-path> --docs-updated <doc-or-spec-path> [--check <name>] [--admin-label <label>]` | `amend --reason "<feature scope changed>" [--owner-directive "<directive>"] [--include <path>] [--test-path <path>] [--docs-updated <path>] [--check <name>] [--admin-label <label>]` | `check --base <base> --head HEAD [--include <path>] [--test-path <path>] [--docs-updated <path>] [--admin-label <label>]` | Pre-PR: `finalize --base <base> --head HEAD --commit <sha> --pr-body-file <path> --closes "#<issue>"`; post-PR: `finalize --commit <sha> --pr <url-or-number> --pr-body-file <path>` |
| `refactor` | `init --task-kind refactor --persona <persona> --branch <branch> --owner-directive "<refactor directive>" --issue <n> --include <path> [--exclude <path>]` | `plan --include <path> --test-path <behavior-preservation-test> OR --test-na "<class>:<rationale>" --docs-updated <path> OR --docs-na "<class>:<rationale>" [--check <name>]` | `amend --reason "<refactor affected additional surface>" [--include <path>] [--exclude <path>] [--test-path <path>] [--docs-na "<class>:<rationale>"]` | `check --base <base> --head HEAD [--test-path <path>] [--docs-na "<class>:<rationale>"]` | Pre-PR: `finalize --base <base> --head HEAD --commit <sha> --pr-body-file <path> --closes "#<issue>"`; post-PR: `finalize --commit <sha> --pr <url-or-number> --pr-body-file <path>` |
| `docs` | `init --task-kind docs --persona adr_author|manager|audit_reviewer --branch <branch> --owner-directive "<docs directive>" [--issue <n>] --include <docs-path>` | `plan --docs-updated <path> [--docs-updated <path>] --test-na "implementation:<docs-only rationale>" [--check frontmatter_lint] [--check full_audit]` | `amend --reason "<docs scope changed>" [--include <docs-path>] [--docs-updated <path>] [--docs-na "<class>:<rationale>"] [--test-na "implementation:<rationale>"]` | `check --base <base> --head HEAD [--docs-updated <path>] [--test-na "implementation:<rationale>"]` | Pre-PR: `finalize --base <base> --head HEAD --commit <sha> --pr-body-file <path> [--closes "#<issue>"]`; post-PR: `finalize --commit <sha> --pr <url-or-number> --pr-body-file <path>` |
| `maintenance` | `init --task-kind maintenance --persona <persona> --branch <branch> --owner-directive "<maintenance directive>" --issue <n> --include <path> [--governance-touch true]` | `plan --include <path> --test-path <tooling-test> OR --test-na "<class>:<rationale>" --docs-updated <path> OR --docs-na "<class>:<rationale>" [--check <name>] [--admin-label <label>]` | `amend --reason "<maintenance surface changed>" [--include <path>] [--test-path <path>] [--docs-updated <path>] [--check <name>] [--admin-label <label>]` | `check --base <base> --head HEAD [--test-path <path>] [--docs-updated <path>] [--admin-label <label>]` | Pre-PR: `finalize --base <base> --head HEAD --commit <sha> --pr-body-file <path> --closes "#<issue>"`; post-PR: `finalize --commit <sha> --pr <url-or-number> --pr-body-file <path>` |
| `manager` | `init --task-kind manager --persona manager --branch <branch> --owner-directive "<manager directive>" --issue <n> --include <planning-or-report-path>` | `plan --docs-updated <checklist-or-report-path> --test-na "implementation:<manager-only rationale>" [--check <integration-check>]` | `amend --reason "<coordination update>" [--issue <n>] [--include <path>] [--docs-updated <path>] [--owner-directive "<directive>"]` | `check --base <base> --head HEAD [--docs-updated <path>] [--test-na "implementation:<rationale>"]` | Pre-PR: `finalize --base <base> --head HEAD --commit <sha> --pr-body-file <path> --closes "#<tracking-issue>"`; post-PR: `finalize --commit <sha> --pr <url-or-number> --pr-body-file <path>` |
| `guided` | `init --task-kind guided --persona live_implementer --branch <branch> --owner-directive "<live owner directive>" [--issue <n>] [--include <path>] [--exclude <path>] [--governance-touch true]` | `plan --owner-directive "<current owner instruction>" [--include <path>] [--issue <n>] [--test-path <path>] [--test-na "<class>:<rationale>"] [--docs-updated <path>] [--docs-na "<class>:<rationale>"] [--admin-label <label>]` | `amend --reason "<owner redirected live work>" --owner-directive "<new owner instruction>" [--issue <n>] [--include <path>] [--exclude <path>] [--test-path <path>] [--docs-updated <path>] [--docs-na "<class>:<rationale>"] [--admin-label <label>]` | `check --base <base> --head HEAD [--owner-directive "<late owner instruction>"] [--include <path>] [--issue <n>] [--test-path <path>] [--docs-updated <path>] [--docs-na "<class>:<rationale>"] [--admin-label <label>]` | Pre-PR: `finalize --base <base> --head HEAD --commit <sha> --pr-body-file <path> --closes "#<issue>"`; post-PR: `finalize --commit <sha> --pr <url-or-number> --pr-body-file <path>` |

#### 7.7.5 Persona CLI Argument Overlays

Persona overlays add or constrain arguments on top of the selected task-kind
profile.

| Persona | Required/expected CLI arguments |
|---|---|
| `manager` | `init --persona manager --task-kind manager|guided|maintenance --owner-directive "<coordination directive>" --issue <tracking-issue> --include <planning-or-report-path>`; `plan --docs-updated <checklist-or-report-path> --test-na "implementation:<manager-only rationale>"`; `check --docs-updated <path> --test-na "implementation:<rationale>"`; `finalize --closes "#<tracking-issue>"` |
| `implementer` | `init --persona implementer --task-kind hotfix|bugfix|feature|refactor|maintenance --owner-directive "<implementation directive>" --issue <n> --include <implementation-path>`; `plan --test-path <path> --docs-updated <path> OR --docs-na "<class>:<rationale>"`; `amend --include <path> --test-path <path>` when implementation scope expands; `check --test-path <path>`; `finalize --closes "#<issue>"` |
| `adr_author` | `init --persona adr_author --task-kind docs|feature|maintenance --owner-directive "<ADR/spec directive>" --include docs/adr/<path> OR --include docs/specs/<path> [--issue <n>]`; `plan --docs-updated <adr-or-spec-path> --test-na "implementation:<docs-only rationale>" --check frontmatter_lint --check full_audit`; `check --docs-updated <path> --test-na "implementation:<rationale>"`; `finalize [--closes "#<issue>"]` |
| `audit_reviewer` | `init --persona audit_reviewer --task-kind manager|docs|maintenance --owner-directive "<audit directive>" --issue <tracking-issue> --include <audit-report-path>`; `plan --docs-updated <audit-report-path> --test-na "implementation:<audit-only rationale>"`; `amend --docs-updated <finding-report-path> --issue <followup-issue>`; `check --docs-updated <path> --test-na "implementation:<rationale>"`; `finalize --closes "#<tracking-issue>" OR --closes "#<audit-issue>"` |
| `test_engineer` | `init --persona test_engineer --task-kind bugfix|maintenance|manager --owner-directive "<test directive>" --issue <n> --include tests/** OR --include frontend/e2e/** OR --include docs/audit/**`; `plan --test-path <path> [--docs-updated <validation-report>] --docs-na "<class>:<rationale>"`; `amend --test-path <path> --docs-updated <path> [--admin-label admin-approved:core-change]` if production-code exception is owner-approved; `check --test-path <path>`; `finalize --closes "#<issue>"` |
| `live_implementer` | `init --persona live_implementer --task-kind guided --owner-directive "<live owner directive>" [--issue <n>] [--include <path>]`; `plan --owner-directive "<current instruction>" [--include <path>] [--test-path <path>] [--docs-updated <path>] [--docs-na "<class>:<rationale>"]`; `amend --reason "<owner redirected live work>" --owner-directive "<new instruction>" [--include <path>] [--issue <n>] [--test-path <path>] [--docs-updated <path>]`; `check [--owner-directive "<late instruction>"] [--include <path>] [--test-path <path>]`; `finalize --closes "#<issue>"` |

The `init` instruction generator must render the applicable rows from this
matrix into concrete guidance for the agent. `check` must use the same rows to
produce unsatisfied obligations and repair hints.

### 7.8 Repository Rule Protection

Repository governance files include:

- `AGENTS.md`;
- `.agents/**`;
- `.claude/**`;
- `.codex/**`;
- `.gemini/**`;
- `.github/workflows/**`;
- `.pre-commit-config.yaml`;
- `pyproject.toml` tool sections;
- `pyrightconfig.json`;
- `.codespellrc`;
- `.yamllint`;
- `.markdownlint.yaml`;
- `MAINTAINERS`;
- docs that define workflow or governance rules, including all AI developer
  workflow docs under `docs/ai-developer/**` (rules, persona guides, specific
  rules, templates, and skills);
- scripts and modules under `scripts/audit/**` and `src/scistudio/qa/**`.

Changes under `docs/ai-developer/**` are treated as governance changes, not
ordinary documentation. Editing the AI developer rules, persona guides, specific
task rules, dispatch templates, or skills changes how every AI agent behaves, so
these edits require focused scope, a `governance_touch` declaration, owner
review, and the governance docs/closure checks defined in Section 7.5. A `docs`
task that only edits non-governance Markdown stays Tier 3, but a task that edits
`docs/ai-developer/**` is a governance-surface change and is evaluated
accordingly.

Changes to these files require focused scope, owner review, and hard-fail
checks for weakening patterns. A PR may strengthen governance rules as part of
its scope. It may not weaken them incidentally.

Protected core component paths require administrator authorization before an AI
agent may stage or commit changes:

- `src/scistudio/core/**`;
- `src/scistudio/engine/**`;
- `src/scistudio/blocks/**`;
- `src/scistudio/workflow/**`;
- `src/scistudio/utils/**`.

The authorization is represented by GitHub-native labels, not by a free-form
local record. Without that authorization signal, `core_change_guard` fails for
AI-authored protected-path changes where the signal is available and in remote
CI.

AI agents may not merge PRs. `pr_merge_guard` blocks AI-initiated merge
commands and CI must reject missing administrator authorization for any
automation path that attempts to merge. Repository administrators may merge
after review and CI according to normal branch protection.

Administrator authorization uses GitHub-native labels rather than free-form
records. Required labels include:

| Operation | Required label |
|---|---|
| Human AI-harness bypass | `human-authored` label |
| Protected core component change | `admin-approved:core-change` label |
| AI merge automation | `admin-approved:merge` label |
| AI gate workflow bypass | `admin-approved:bypass` label |

CI verifies the label actor has administrator or maintainer permission. If
label provenance cannot be verified, the authorization is invalid. This avoids
asking humans to fill a separate authorization record.

### 7.9 Test Quality Supervision

AI-generated tests are prone to verifying implementation shape rather than
behavior. ADR-042 therefore requires test-quality checks:

- AST checks for empty assertions, mocked-away behavior, snapshot-only tests,
  broad exception swallowing, and skipped tests without tracked rationale.
- Mutation testing for QA tools and selected critical logic.
- Test-first evidence for changes where owner policy requires it.
- Coverage ratchets with stronger thresholds for new QA tooling.
- Runtime validation or e2e evidence when a claim cannot be proven by static
  audit or unit tests.

Full audit is not runtime proof. The gate ledger may record full-audit evidence,
but runtime behavior claims require the relevant contract, integration,
frontend, runtime, or e2e checks.

### 7.10 Local And CI Tool Version And Environment Parity

Section 7.5 makes CI the source of truth for *which* checks run. This section
makes CI the source of truth for *which tool versions* run them and for *the
environment* they run in. Command parity without version and environment parity
still produces "green locally, red in CI" failures, which is the original reason
agents kept failing basic lint and type checks even after running the same
checks repeatedly.

Two parity gaps must be closed:

- **Tool version drift.** The same file can pass one `ruff` or `mypy` version
  and fail another. Pinned pre-commit versions, an agent's locally installed
  versions, and CI's installed versions must not diverge. There is one tool
  version source of truth, and CI is that source. Local `gate_record check` must
  run the same resolved tool versions CI uses; when CI installs a version, local
  installs that same resolved version into its isolated environment rather than
  whatever the developer machine happens to have.

- **Environment reproducibility.** Several CI jobs import `scistudio` (for
  example type checking and tests). CI makes the package importable with an
  editable or system install. The repository forbids `pip install -e .` because
  it pollutes the *shared* environment, not because importing the package is
  wrong. Local `gate_record check` must reproduce a CI-equivalent importable
  environment *without* polluting the shared environment: it uses an isolated
  per-worktree environment, or the CI-equivalent `PYTHONPATH=src` invocation
  that CI's full-audit job already uses, so the same commands actually run
  locally.

The decision is: CI is unchanged and authoritative; local aligns up to CI. Local
tooling reads the tool version and environment definition from the same source
CI uses, installs into an isolated per-worktree environment, and never relies on
ambient developer-machine tool versions. A small version-drift window is
acceptable only when CI itself resolves an unpinned latest version; in that case
local resolves the same latest version at run time rather than a stale pin.

`gate_record check` is responsible for setting up or validating this
CI-equivalent local environment before running checks. If it cannot reproduce
the CI tool versions or a CI-equivalent importable environment, it must fail
closed for PR readiness and report the parity gap rather than running a looser
local approximation. This is what makes the central promise true: completing the
gate locally predicts a passing CI run, because the local checks are the CI
checks at the same versions in an equivalent environment.

## 3. Implementation And Migration

Implementation should proceed as a delete-and-replace implementation, not
piecemeal patching and not deprecation beside the old code.

The old governance implementation must not remain as a parallel authority. The
implementation branch should remove the existing governance files, tests, hook
entry points, and wrapper behavior that encode old semantics before adding the
new ledger/evaluator implementation. Compatibility command names may exist only
as aliases implemented by the new code; old modules must not continue to own
validation decisions.

1. Add a spec for the ledger schema, event types, evaluator inputs, evaluator
   modes, task-kind profiles, and compatibility aliases.
2. Inventory every currently implemented hook, guard, and governance tool. The
   rewrite must include each current capability or explicitly map it to a
   replacement ledger/evaluator responsibility.
3. Delete the old implementation files under `src/scistudio/qa/governance/**`
   and the old behavior-specific tests under `tests/qa/**` in the same
   implementation branch. Preserve any reusable behavior only by porting it
   into the new ledger/evaluator design.
4. Delete or replace hook and wrapper entry points that call old validation
   semantics.
5. Implement the new ledger schema and shared evaluator.
6. Re-add guard capabilities as evaluator-owned calculators, not independent
   authorities.
7. Port local hooks, PR wrapper, and workflow-gate CI to the evaluator.
8. Replace receipt files with ledger check and reconcile events.
9. Update AI developer rules, persona docs, and command examples.
10. Replace tests that assert old receipt/gate-record duplication with tests for
   ledger reconciliation and tier-selected local/CI agreement.
11. Validate representative fixtures for docs-only, bugfix, feature,
   maintenance, governance-touch, and guided work.

The initial inventory must cover at least:

- `gate_record` schema, CLI, validation, stage handling, I/O, and workflow
  orchestration;
- `gate_receipt` behavior, folded into ledger check and reconcile events;
- `workflow_gate`;
- `docs_landing`;
- `issue_link`;
- `persona_policy`;
- `core_change_guard`;
- `human_bypass_guard`;
- `pr_merge_guard`;
- `mod_guard`;
- `weakened_ci_check`;
- `sentrux_gate`;
- `test_engineer_scope_guard`;
- `worktree_write_guard`;
- hook scripts under `scripts/hooks/**`;
- PR wrapper behavior in `scripts/scistudio_pr_create.py`;
- existing workflow label vocabulary, including migration from any older
  `admin-approved:ai-override` references to `admin-approved:bypass`;
- existing tests under `tests/qa/**` that define accepted guard behavior.

## 4. Verification

The rewrite is accepted only when tests prove:

- observed changed files are derived from git, not only declared by the agent;
- declared docs and test evidence is reconciled against the observed git diff,
  so a claimed docs or test path that is not actually changed does not satisfy
  its obligation;
- local and CI modes use the same evaluator;
- local checks run the same resolved tool versions as CI in a CI-equivalent
  importable environment, and `check` fails closed when that parity cannot be
  reproduced;
- hook, wrapper, and CI reports agree for the same fixture;
- required checks are inferred from actual changed surfaces;
- prior check evidence remains valid only for unchanged covered surfaces;
- gate-record edits invalidate reconciliation evidence when obligations change;
- governance weakening is still blocked;
- protected core paths still require authorization;
- task-kind profiles produce the expected obligations;
- `guided` work can expand through owner directive events without bypassing
  final tier-selected check obligations.
- committed gate records do not contain absolute local paths, raw command
  transcripts, environment dumps, or other local developer environment details.

## 5. Consequences

Positive consequences:

- gate record becomes the single source of truth;
- receipt duplication disappears;
- local and CI behavior become explainably identical;
- check evidence can be incremental;
- task-kind profiles reduce unnecessary ceremony without weakening CI;
- owner-guided implementation becomes representable without pretending all
  scope was known up front.

Risks:

- the rewrite touches critical governance, hook, wrapper, and CI paths;
- existing docs and command examples may be stale during migration;
- compatibility aliases can preserve old assumptions if kept too long;
- the ledger schema must stay small enough for agents and reviewers to use.

## 6. Alternatives Considered

| Alternative | Reason rejected |
|---|---|
| Keep gate record and receipt separate | They duplicate candidate state and create invalidation conflicts |
| Patch each guard independently | This preserves the current no-single-source problem |
| Make local checks advisory only | This weakens Addendum 5 and preserves avoidable CI failures |
| Require fully planned scope for all tasks | This does not match owner-guided interactive implementation |
| Use `explore` as the new task kind name | It sounds read-only, while the intended mode allows implementation |
