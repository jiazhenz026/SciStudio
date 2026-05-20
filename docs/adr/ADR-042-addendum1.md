---
adr: 42
addendum: 1
title: "CI-Reviewed Gate Records And Sentrux Free-Tier Checks"
status: Accepted
date_created: 2026-05-20
date_accepted: 2026-05-20
date_superseded: null

supersedes: []
superseded_by: null
related: [42]
closes_issues: []
tracking_issue: null

is_code_implementation: true
governs:
  modules:
    - scieasy.qa.governance
    - scieasy.qa.governance.gate_record
    - scieasy.qa.governance.sentrux_gate
    - scieasy.qa.governance.human_bypass_guard
    - scieasy.qa.governance.core_change_guard
    - scieasy.qa.governance.pr_merge_guard
    - scieasy.qa.schemas.frontmatter
  contracts:
    - scieasy.qa.schemas.frontmatter.ArchitectureFrontmatter
    - scieasy.qa.governance.gate_record.GateRecord
    - scieasy.qa.governance.gate_record.CheckEvidence
    - scieasy.qa.governance.gate_record.SentruxEvidence
    - scieasy.qa.governance.gate_record.FullAuditEvidence
    - scieasy.qa.governance.gate_record.validate_gate_record
    - scieasy.qa.governance.gate_record.check_pre_commit
    - scieasy.qa.governance.gate_record.check_commit_msg
    - scieasy.qa.governance.gate_record.check_pr
    - scieasy.qa.governance.sentrux_gate.verify_free_tier_claims
    - scieasy.qa.governance.human_bypass_guard.check
    - scieasy.qa.governance.core_change_guard.check
    - scieasy.qa.governance.pr_merge_guard.check
  entry_points: []
  files:
    - docs/adr/ADR-042-addendum1.md
    - docs/specs/adr-042-gate-record-sentrux-workflow.md
    - docs/contributing/workflows/human-bypass.md
    - docs/architecture/ARCHITECTURE.md
    - .workflow/**
    - .sentrux/rules.toml
    - .github/workflows/**
    - .pre-commit-config.yaml
    - scripts/hooks/**
    - src/scieasy/qa/**
    - tests/qa/**
  excludes: []

tests:
  - tests/qa/test_gate_record.py
  - tests/qa/test_gate_record_hooks.py
  - tests/qa/test_gate_record_ci.py
  - tests/qa/test_sentrux_gate.py
  - tests/qa/test_human_bypass_guard.py
  - tests/qa/test_core_change_guard.py
  - tests/qa/test_pr_merge_guard.py
  - tests/qa/test_audit_frontmatter_lint.py
agent_editable: false
assisted_by:
  - "Codex:gpt-5"

phase: planning
tags: [qa, ci, ai-governance, workflow-gate, sentrux]
owner: "@jiazhenz026"
co_authors: ["@codex"]
language_source: en
translations: []
---

# ADR-042 Addendum 1: CI-Reviewed Gate Records And Sentrux Free-Tier Checks

## 1. Decision Summary

This addendum makes the following decisions for ADR-042 gate and architecture
governance:

| Decision | Change | Enforcement target | Detailed section |
|---|---|---|---|
| D1. Sentrux free-tier architecture evidence | Add Sentrux free-tier checks and metrics to required gate evidence for architecture-relevant changes | Local check recording and CI verification | Section 2 |
| D2. Committed gate records | Replace ADR-042 Section 7.2 local-only gate state with repository-visible gate records | CI validates the committed record against the PR diff | Section 3 |
| D3. Six-stage gate | Define the canonical stages as Scope And Issue, Plan, Implement, Update Docs, Test And Checks, Commit And Submit PR | Local hooks and CI gate validation | Section 3 |
| D4. QA full audit requirement | Require ADR-042 QA full audit evidence in the gate when the tool is available; unresolved failures are tracked as technical debt during the transition | CI ultimately blocks non-compliant PRs after the debt-handling phase | Section 5 |
| D5. Free-tier honesty rule | Forbid claiming Sentrux Pro-only diagnostics or unchecked rules as completed gate evidence | Local hooks, CI, and review | Section 2 |
| D6. Override-label consistency | Reuse ADR-042's administrator labels for human bypass, AI override, protected core changes, and merge automation | CI validates label provenance through ADR-042 guards | Section 5 |
| D7. Implementation tests required | Require implementation-category tasks to add or modify tests as part of the PR | Local hooks and CI reject implementation work without test changes | Section 3 |
| D8. Legacy gate removal | Delete `.workflow/gate.py` and replace the old `.workflow/active` CI lookup with committed gate-record validation | Workflow-gate CI has one normative gate authority | Section 3 |
| D9. Conflict-prone generated artifacts | Ignore generated gate/audit artifacts and explicitly migrate any tracked workflow files before treating them as ignored | `.gitignore`, review, and gate implementation docs | Section 3 |
| D10. AI gate CLI | Require agents to use the repository-owned gate-record CLI for each gate stage | Agent workflow, local hooks, and CI consume the same committed record | Section 3 |
| D11. Architecture frontmatter audit | Include `docs/architecture/ARCHITECTURE.md` in ADR-042 frontmatter audit coverage | Full audit and frontmatter lint fail invalid architecture metadata | Section 5 |

This addendum supersedes ADR-042 Section 7.2 only where that section defines
gate state as local-only state under `.git/scieasy/gates/`. Local gate state may
still exist as a pre-commit helper, but it is not sufficient for delivery.

### 1.1 Problems Addressed

| Problem | Risk | Decision | Detailed section |
|---|---|---|---|
| Local-only gate state cannot be reviewed by CI | A PR can claim gate completion without durable evidence | Commit a gate record and validate it in CI | Section 3 |
| Issue linkage was separated from scope | Agents can plan or implement work before traceability is established | Combine scope and issue linkage as the first gate stage | Section 3 |
| Documentation landing happened too late or too vaguely | Full audit and drift checks catch documentation problems only after docs exist | Add an explicit Update Docs stage before Test And Checks | Section 3 |
| Commit and PR submission were split across two handoff points | Agents can leave work half-delivered after commit or before PR | Treat commit and PR submission as one final gate stage | Section 3 |
| PRs can reference but not close issues | Completed work leaves zombie issues open | Require closing keywords for every gate issue before PR readiness | Section 3 |
| Architecture checks need a deterministic gate signal | Layering and dependency drift can pass ordinary tests | Require Sentrux free-tier evidence where applicable | Section 2 |
| Sentrux Pro is unavailable | Gate rules could depend on checks the project cannot run | Limit blocking semantics to free-tier executed checks | Section 2 |
| QA full audit evidence is not yet part of the gate | ADR-042 consistency tools can be skipped even when available | Require full-audit evidence, with temporary technical-debt handling before hard fail | Section 5 |
| Override labels can drift between docs and implementation | Human bypass or admin approval checks can disagree about valid labels | Reuse one fixed label set from ADR-042 and validate it in CI | Section 5 |
| Implementation tasks can claim tests were run without adding tests | Bug fixes and features can land without regression or behavior coverage | Require changed test files for implementation-category tasks | Section 3 |
| The legacy CI gate can remain as a parallel source of truth | A PR can pass or fail against obsolete `.workflow/gate.py` or `.workflow/active` state instead of the committed record | Delete `.workflow/gate.py` and replace the legacy workflow-gate state lookup with gate-record validation | Section 3 |
| Generated workflow artifacts cause noisy merge conflicts | Agents repeatedly resolve conflicts in files that should be local evidence, not canonical text | Ignore generated gate/audit artifacts and explicitly migrate any tracked canonical workflow files | Section 3 |
| Agents need a concrete command surface | Agents otherwise treat the workflow as prose and skip durable state updates | Define a mandatory `gate_record` CLI for AI use | Section 3 |
| Architecture metadata can drift outside audit coverage | The top-level architecture document can become stale or ownerless despite having frontmatter | Validate architecture frontmatter in `frontmatter_lint` | Section 5 |

## 2. Sentrux Free-Tier Integration

Sentrux is adopted as an architecture sensor for dependency health, layering,
boundary checks, cycle count, complexity ceilings, and quality-signal evidence.
The executable rule source is `.sentrux/rules.toml`.

During the free-tier period:

- gate and CI may require `sentrux check` or MCP `check_rules` to pass;
- gate records must identify the execution mode as `free-tier`;
- gate records may store `quality_signal`, cycle count, complexity ceiling,
  DSM summary, and test-gap summary as evidence;
- blocking claims are limited to rules the free-tier tool reports as checked;
- Pro-only diagnostics, complete root-cause analysis, or unchecked rules must
  not be described as completed gate evidence.

Sentrux evidence is required when a PR changes source, package, workflow,
architecture, governance, or Sentrux rule files. Documentation-only changes may
record Sentrux as not applicable unless they modify architecture or governance
rules.

## 3. Gate Workflow Supersession

This addendum replaces ADR-042 Section 7.2's local-only gate workflow with a
CI-reviewed gate-record workflow. The gate remains a development lifecycle, not
a substitute for issue tracking, branch protection, review, or CI.

The canonical gate has six stages:

| Stage | Required record | Blocking rule |
|---|---|---|
| 1. Scope And Issue | Task kind, owner directive, branch, in-scope paths, out-of-scope paths, governance-touch flag, issue link | No committed scope and issue linkage means no AI-authored PR readiness |
| 2. Plan | Planned files, expected docs/tests/checks, expected Sentrux applicability, ADR/spec/changelog expectation, implementation-test expectation | Diff outside plan requires a recorded amendment |
| 3. Implement | Changed files remain within scope; amendments explain any scope change | Scope violations fail local hooks and CI |
| 4. Update Docs | Required docs, specs, ADR addenda, changelog, checklist, or explicit N/A rationale | Missing documentation landing fails local hooks and CI |
| 5. Test And Checks | Required checks after docs landing, QA full audit evidence, command or tool id, exit code/status, timestamp, output path or compact result | Missing or failing required checks fail local hooks and CI, subject to temporary debt handling for known full-audit findings |
| 6. Commit And Submit PR | Commit trailers, gate record path, closing issue link, PR URL or CI-discoverable PR association | Missing durable provenance or missing issue-closing keywords fails commit-msg hooks or CI |

Existing `.workflow/gate.py` records and commands are obsolete for ADR-042 gate
compliance, and `.workflow/gate.py` must be deleted from the repository. Agents
must not use `.workflow/gate.py` as the gate entry point, local evidence source,
or CI evidence source. The existing workflow-gate CI step that searches
`.workflow/active` for local state must be replaced by committed gate-record
validation; CI must not keep both checks as parallel authorities.

Generated gate and audit outputs that are not canonical repository
documentation should be ignored to avoid recurring branch conflicts. If the
project decides that an already tracked canonical workflow file such as
`CHANGELOG.md` should no longer be version-controlled, the implementation must
remove it from the Git index and update gate semantics; adding a tracked file
to `.gitignore` alone is not sufficient.

### 3.1 Required AI Gate CLI

AI agents must use the repository-owned gate-record CLI to create and update
the committed gate record. The command surface is:

```bash
python -m scieasy.qa.governance.gate_record start \
  --task-kind feature|bugfix|hotfix|refactor|docs|maintenance|manager \
  --issue <number> \
  --branch <branch> \
  --owner-directive "<owner instruction>" \
  --include <path-or-glob> \
  --exclude <path-or-glob> \
  --record .workflow/records/<issue>-<task-slug>.json

python -m scieasy.qa.governance.gate_record plan \
  --record .workflow/records/<issue>-<task-slug>.json \
  --files <path-or-glob> \
  --docs <path-or-na> \
  --tests <path-or-na> \
  --checks ruff,format,pytest,full_audit,sentrux

python -m scieasy.qa.governance.gate_record amend \
  --record .workflow/records/<issue>-<task-slug>.json \
  --reason "<why scope changed>" \
  --include <path-or-glob>

python -m scieasy.qa.governance.gate_record docs \
  --record .workflow/records/<issue>-<task-slug>.json \
  --updated <path> \
  --na <doc-class>:<reason>

python -m scieasy.qa.governance.gate_record check \
  --record .workflow/records/<issue>-<task-slug>.json \
  --name <check-name> \
  --command "<command or MCP tool id>" \
  --status pass|fail|skipped \
  --exit-code <code> \
  --output <path-or-summary>

python -m scieasy.qa.governance.gate_record sentrux \
  --record .workflow/records/<issue>-<task-slug>.json \
  --mode free-tier \
  --status pass|fail|skipped \
  --evidence <json-path-or-summary>

python -m scieasy.qa.governance.gate_record finalize \
  --record .workflow/records/<issue>-<task-slug>.json \
  --commit <sha> \
  --pr <url> \
  --closes "#<issue>"

python -m scieasy.qa.governance.gate_record pre-commit --staged
python -m scieasy.qa.governance.gate_record commit-msg <commit-msg-file>
python -m scieasy.qa.governance.gate_record ci \
  --gate-record .workflow/records/<issue>-<task-slug>.json \
  --base <base-ref> \
  --head <head-ref> \
  --pr-body <path-or-text>
```

The CLI may expose additional convenience aliases, but the commands above are
the normative AI-facing interface. They must update the committed gate record or
validate it; self-attestation in chat is not gate evidence.

### 3.2 Required Agent Procedure

Agents must execute the gate as an explicit sequence. Each step updates the
committed gate record before moving to the next step.

#### Step 1. Scope And Issue

The agent must:

1. Create or update `.workflow/records/<issue>-<task-slug>.json` with
   `python -m scieasy.qa.governance.gate_record start`.
2. Record `task_kind`, `branch`, `owner_directive`, `scope.include`,
   `scope.exclude`, `governance_touch`, and expected artifact classes.
3. Link an existing issue or create a new issue before implementation work is
   considered committable.
4. Record the issue number and URL in the gate record. For hotfix batches,
   record every issue fixed by the batch.
5. If Sentrux is available, start a Sentrux session baseline:

```text
mcp__sentrux__.scan(path=<repo-root>)
mcp__sentrux__.session_start()
```

6. Record the Sentrux session start result in the gate record when available.

If Sentrux MCP is unavailable, the gate record must state that explicitly and
record the fallback command expected in CI, usually `sentrux check .`.

No AI-authored PR is ready when the gate record lacks issue linkage.

#### Step 2. Plan

The agent must:

1. Record planned files and directories with
   `python -m scieasy.qa.governance.gate_record plan`.
2. Record expected docs, tests, changelog, ADR/spec/addendum, and checklist
   landing.
3. Record required checks. At minimum, source or governance changes require:
   `ruff`, relevant tests, ADR-042 QA full audit, and Sentrux applicability
   evidence. Frontend changes require the configured frontend checks.
4. For implementation-category tasks, record the expected test files that will
   be added or modified. Implementation-category tasks include feature, bugfix,
   hotfix, refactor, and maintenance work that changes source, package,
   frontend, workflow, gate, or governance implementation files.
5. Record whether Sentrux applies. If it does not apply, record a short N/A
   rationale.

Scope additions after this point require a gate-record amendment before the
agent stages or commits the extra files.

#### Step 3. Implement

The agent must:

1. Keep changes within `scope.include` and outside `scope.exclude`.
2. Update the gate record with
   `python -m scieasy.qa.governance.gate_record amend` before touching newly
   discovered files outside the original plan.
3. For implementation-category tasks, add or modify at least one test file in
   the same PR.
4. Record deferred work only with tracked issues. Untracked TODOs or deferrals
   violate the gate.
5. Avoid weakening governance, CI, Sentrux, or quality thresholds unless the
   owner directive explicitly authorized that scope.

#### Step 4. Update Docs

The agent must update documentation before running the final test and audit
stage. This mirrors ADR-042's original requirement that documentation landing
is explicit rather than inferred after the fact.

The agent must:

1. Update required docs, specs, ADR addenda, changelog entries, and checklists.
2. Record the updated paths in the gate record with
   `python -m scieasy.qa.governance.gate_record docs`.
3. For each documentation class that is not required, record an explicit N/A
   rationale.
4. Update the plan amendment if documentation work expands the file scope.

This step must happen before QA full audit because full audit, frontmatter
lint, doc drift, fact drift, signature drift, and closure checks evaluate
documentation state.

#### Step 5. Test And Checks

The agent must run and record the checks declared in the plan after Update Docs
is complete. For a typical source, governance, or architecture-relevant change,
the required check set is:

```bash
ruff check .
ruff format --check .
pytest <targeted-tests-or-test-directory>
python -m scieasy.qa.audit.full_audit \
  --repo-root . \
  --format json \
  --output docs/audit/full-audit-latest.json
```

Each completed check must be recorded with
`python -m scieasy.qa.governance.gate_record check`; Sentrux evidence must be
recorded with `python -m scieasy.qa.governance.gate_record sentrux`.

When generated facts are part of the change or full audit reports stale facts,
the agent must also run:

```bash
python scripts/audit/generate_facts.py --check
```

For Sentrux MCP-capable sessions, the agent must run:

```text
mcp__sentrux__.rescan()
mcp__sentrux__.check_rules()
mcp__sentrux__.health()
mcp__sentrux__.session_end()
```

When Sentrux MCP is unavailable but the CLI is available, the agent must run:

```bash
sentrux scan .
sentrux check .
```

The gate record must store each check's command or MCP tool id, status or exit
code, timestamp, and output path or compact machine-readable result. For QA full
audit, the record must store the output path, `blocks_merge` status when
reported, and any known-debt classification. During the technical-debt handling
phase, known full-audit findings may be recorded without immediately blocking
every PR, but missing full-audit evidence is still a gate violation.

For implementation-category tasks, the gate record must also store the changed
test paths. Running tests is not sufficient when no test file is added or
modified.

For Sentrux, the record must store `free-tier` mode, `rules_checked`,
`total_rules_defined` when reported, pass/fail status, relevant thresholds from
`.sentrux/rules.toml`, and `pro_required: false`.

#### Step 6. Commit And Submit PR

The agent must:

1. Commit the gate record with the code or documentation change.
2. Include these commit trailers:

```text
Gate-Record: .workflow/records/<record>.json
Task-Kind: hotfix|bugfix|feature|docs|maintenance|manager
Issue: #<number>
Assisted-by: <runtime>:<model-or-agent-id>
```

3. Push the branch and open the PR.
4. Record final commit and PR evidence with
   `python -m scieasy.qa.governance.gate_record finalize`.
5. Ensure the PR body names the gate record path and closes every issue listed
   in the gate record using GitHub closing keywords: `Closes #N`, `Fixes #N`,
   or `Resolves #N`.
6. Let CI re-run gate validation, QA full audit, and Sentrux checks. Local
   evidence helps review; CI evidence is authoritative.

Referencing an issue without a closing keyword is not sufficient. If a gate
record lists multiple issues, the PR body must close all of them or explicitly
mark non-closed issues as follow-up references with owner-approved rationale.

## 4. Required Gate Record

Gate records are repository-visible artifacts committed with the PR. The
recommended location is `.workflow/records/<issue>-<task-slug>.json`.

Each gate record must contain:

- `task_id`, `task_kind`, `branch`, `owner_directive`;
- linked `issues`;
- `scope.include`, `scope.exclude`, and `governance_touch`;
- planned files and recorded amendments;
- changed test paths for implementation-category tasks;
- administrator labels and provenance when an override is used;
- required checks and check results;
- ADR-042 QA full audit evidence when the tool is available;
- documentation landing records or explicit N/A rationales;
- Sentrux evidence when applicable;
- final commit and PR provenance.

Sentrux evidence must include at least:

- `name: "sentrux.free_tier"`;
- execution method, such as CLI command or MCP tool id;
- `status`;
- `rules_checked` when reported by the tool;
- `total_rules_defined` when reported by the tool;
- relevant threshold values from `.sentrux/rules.toml`;
- `pro_required: false`.

## 5. Interception And CI Semantics

Local hooks provide early feedback. CI is the final gate verifier.

Pre-commit should block AI-authored commits when:

- no gate record exists for the branch;
- staged files are outside `scope.include` or inside `scope.exclude`;
- governance files are touched without `governance_touch=true`;
- required checks, including applicable Sentrux evidence, are missing;
- QA full audit evidence is missing when the tool is available;
- Sentrux free-tier checks fail for applicable changes.

Commit-message hooks should require machine-readable trailers:

```text
Gate-Record: .workflow/records/<record>.json
Task-Kind: hotfix|bugfix|feature|docs|maintenance|manager
Issue: #<number>
Assisted-by: <runtime>:<model-or-agent-id>
```

CI must re-read the committed gate record and compare it with the PR diff. CI
fails when:

- no gate record is present for AI-authored work;
- the record branch, issue, or changed files do not match the PR;
- the PR body does not close every issue listed in the gate record;
- changed files exceed scope without an amendment;
- an implementation-category task changes implementation files without adding
  or modifying test files;
- required docs, tests, changelog, or N/A rationales are missing;
- QA full audit evidence is missing;
- Sentrux is applicable but missing or failing;
- the record claims Pro-only Sentrux evidence;
- governance or Sentrux rules are weakened without owner-approved scope.

The valid administrator labels are exactly:

| Label | Meaning |
|---|---|
| `human-authored` | Human-authored PR bypass for AI-only harness requirements |
| `admin-approved:ai-override` | One-off AI harness override |
| `admin-approved:core-change` | Protected core component change approval |
| `admin-approved:merge` | Approved merge automation |

CI must validate label provenance through the ADR-042 guard contracts. The
label vocabulary in code, CI, specs, and contributor docs must stay identical.

During the initial technical-debt handling phase, QA full audit may report known
repository findings without immediately blocking every PR. The gate record must
still include the full-audit result, output path, and classification of any
known debt. After the owner accepts the baseline or cleanup queue, missing full
audit evidence or unclassified full-audit failures become CI-blocking.

## 6. Scope, Non-Goals, And Consequences

In scope:

- committed gate records;
- CI validation of gate completeness;
- Sentrux free-tier check evidence;
- ADR-042 QA full audit evidence;
- local hooks as fast feedback.

Out of scope:

- requiring Sentrux Pro;
- replacing review, branch protection, or normal CI;
- treating Sentrux quality signal as a universal score gate before a baseline
  policy is accepted;
- automatic approval of governance changes by tools.

Positive consequences:

- gate evidence becomes reviewable and durable;
- CI can validate scope, checks, and Sentrux evidence;
- architecture drift receives an early automated signal.

Negative consequences:

- each AI-authored PR gains one committed process artifact;
- gate record schema and CI validators must be maintained;
- QA full audit findings need a temporary baseline or cleanup queue before
  full hard-fail enforcement;
- Sentrux free-tier limits must be represented honestly in records and docs.

## 7. Alternatives Considered

| Alternative | Reason rejected |
|---|---|
| Keep gate state local-only | CI cannot verify completeness or scope claims |
| Depend on Sentrux Pro | Pro is not available and still under development |
| Use Sentrux quality signal as the only architecture gate | A single score is useful evidence but does not replace explicit rule checks |
| Keep commit and PR as separate gate stages | The handoff can leave AI work committed but not delivered for review |
