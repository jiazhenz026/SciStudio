---
title: "AI Gated Workflow Specific Rules"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
related_specs:
  - adr-042-gate-ledger-runtime
language_source: en
---

# AI Gated Workflow Specific Rules

## 1. What Is The Gate Workflow

The gate workflow is the required delivery lifecycle for AI-authored work in
SciStudio. It turns an AI task into reviewable repository evidence by recording
scope, issue linkage, plan, docs, tests, checks, commit provenance, and PR
provenance in a committed gate ledger.

The gate is not a replacement for issues, branches, review, CI, or owner
approval. It is the AI work record that lets local hooks, CI, and reviewers
verify that an agent stayed within scope and produced the required evidence.

Per ADR-042 Addendum 6, the gate record is now an **append-only ledger** that
is the single source of truth. Receipt state is folded into the ledger as
ledger events. Local hooks, the PR wrapper, and CI all use **one shared
evaluator** — `gate_record check` — rather than separate tools. There is no
longer a distinct `gate_receipt` tool; its role is performed by
`gate_record check` and `gate_record finalize`.

The gate has six required lifecycle concerns:

1. Scope And Issue
2. Plan
3. Implement
4. Update Docs
5. Test And Checks
6. Commit And Submit PR

These concerns remain mandatory. The ledger records them as append-only events
rather than as a linear sequence of stages. Later work may add new directive,
diff, check, docs, test, guard, or reconcile events. The current candidate is
valid when the shared evaluator can reconcile the ledger against the current
git diff and PR metadata.

The gate ledger is committed repository evidence. Local-only logs may exist as
helper artifacts under `.workflow/local/**`, but they must not be committed.
Chat self-attestation is not gate evidence.

### 1.1 Gate Strictness Tiers

The evaluator derives a strictness tier from `task_kind` and then escalates
based on the observed diff. Agents never choose a tier directly.

| Tier | Task kinds (baseline) | Escalation trigger |
|---|---|---|
| Tier 1 (Strict) | `feature`, `refactor` | Any task whose diff touches protected core/runtime/engine paths, governance/workflow files, or constitutes a broad cross-module change |
| Tier 2 (Standard) | `bugfix`, `hotfix`, `maintenance`, `guided` (default) | — |
| Tier 3 (Lightweight) | `docs`, `manager` | — |

Tier 3 is not a quality bypass. It allows less up-front ceremony and a minimal
local check set, but final `check` and `finalize` reconciliation still enforce
mandatory obligations and repository protection rules.

### 1.2 Supported Task Kinds

| Kind | Notes |
|---|---|
| `hotfix` | Live-debug bug batch; may start from owner directive; formal issues required before commit |
| `bugfix` | Fix one known issue; prefer existing issue |
| `feature` | New behavior; usually requires spec and/or ADR links |
| `refactor` | Behavior-preserving code movement or cleanup |
| `docs` | Write or update documentation; still requires scope, checks, and issue linkage |
| `maintenance` | Cleanup, dependency/config hygiene, repository housekeeping |
| `manager` | Agent-manager coordination, checklist updates, merge preparation |
| `guided` | Owner-directed live implementation; scope expands through recorded owner directives |

### 1.3 Supported Personas

| Persona | Use |
|---|---|
| `manager` | Coordinate agents, maintain checklists, prepare merges |
| `implementer` | Implement code, tests, tool wiring, docs generated from implementation |
| `adr_author` | Draft or revise ADR/spec governance text and schemas |
| `audit_reviewer` | Inspect diffs, audit findings, CI failures, conformance gaps |
| `test_engineer` | Design tests, add test evidence, run runtime validation, produce e2e evidence |
| `live_implementer` | Carry out owner-directed live implementation (`guided` task kind) |

## 2. Required AI Gate CLI

AI agents must use the repository-owned gate-record CLI to create, update, and
validate the committed gate ledger. The five normative workflow commands are
`init`, `plan`, `amend`, `check`, and `finalize`. Compatibility aliases for
older subcommand names delegate to these five commands.

The quick command index is also routed from
`docs/ai-developer/rules.md#5-gate-cli-command-set`, `AGENTS.md`, and each
persona guide so all AI runtimes land on the same command set.

The full consolidated CLI reference — every argument table, the `--mode`
family, exit codes, strictness tiers, per-task-kind and per-persona obligation
profiles, and a soft-routing decision guide — is
`docs/ai-developer/gate-cli-command-set.md`. This section summarizes the same
contract for the procedure walkthrough; consult the reference for the complete
argument detail.

### 2.1 `init` — Create Or Update The Ledger

```bash
python -m scistudio.qa.governance.gate_record init \
  --task-kind hotfix|bugfix|feature|refactor|docs|maintenance|manager|guided \
  --persona manager|implementer|adr_author|audit_reviewer|test_engineer|live_implementer \
  --runtime <runtime-id> \
  --branch <branch> \
  --owner-directive "<owner instruction>" \
  [--slug <task-slug>] \
  [--issue <number>] \
  [--include <path-or-glob>] \
  [--exclude <path-or-glob>] \
  [--governance-touch true|false]
```

`init` creates or updates the ledger, records branch/task identity, prints the
chosen ledger path, and prints task-specific instructions by default. The
generated ledger path prefers `.workflow/records/<issue>-<slug>.json` when an
issue is known, or `.workflow/records/<branch-slug>-<slug>.json` otherwise.
`init` may be rerun to append issues, directives, or scope fields without
erasing earlier ledger events. The issue is optional at `init` for Tier 2 and
Tier 3 tasks; it must be recorded before PR readiness.

Compatibility alias: `start` delegates to `init`.

### 2.2 `plan` — Record Planning Fields

```bash
python -m scistudio.qa.governance.gate_record plan \
  [--owner-directive "<scope or plan update>"] \
  [--include <path-or-glob>] \
  [--exclude <path-or-glob>] \
  [--issue <number>] \
  [--docs-updated <path>] \
  [--docs-na "<class>:<rationale>"] \
  [--test-path <path>] \
  [--test-na "<class>:<rationale>"] \
  [--check <check-name>] \
  [--check-na "<check-name>:<rationale>"] \
  [--admin-label admin-approved:bypass|admin-approved:core-change|admin-approved:merge]
```

`plan` appends planning fields without running the full check set. It observes
the current diff when available and recomputes provisional obligations. All
field arguments are optional and repeatable.

Compatibility alias: `plan` (unchanged name; argument profile updated to match
the above flags; old positional or `--files`/`--checks` flags are compatibility
aliases).

### 2.3 `amend` — Append A Correction Or Field Update

```bash
python -m scistudio.qa.governance.gate_record amend \
  --reason "<why the ledger is being corrected>" \
  [--owner-directive "<new or corrected owner instruction>"] \
  [--task-kind <kind>] \
  [--persona <persona>] \
  [--issue <number>] \
  [--remove-issue <number>] \
  [--include <path-or-glob>] \
  [--remove-include <path-or-glob>] \
  [--exclude <path-or-glob>] \
  [--remove-exclude <path-or-glob>] \
  [--governance-touch true|false] \
  [--docs-updated <path>] \
  [--docs-na "<class>:<rationale>"] \
  [--test-path <path>] \
  [--test-na "<class>:<rationale>"] \
  [--check <check-name>] \
  [--check-na "<check-name>:<rationale>"] \
  [--admin-label admin-approved:bypass|admin-approved:core-change|admin-approved:merge]
```

`amend` is the dedicated low-cost correction command. It is append-only: it
appends a correction event and recomputes obligations when the amended field
affects scope, issues, docs, tests, or checks. It does not run expensive
checks. Removals are recorded as supersession events, never deletions.

Note: the old `docs` subcommand is a compatibility alias for
`amend --docs-updated <path>` or `amend --docs-na "<class>:<rationale>"`.

### 2.4 `check` — Run Tier-Selected CI Checks And Reconcile

`gate_record check` is the **main local CI-equivalent preflight**. It derives
and runs the full tier-selected check set from the observed diff, task kind,
persona, plan, and CI workflow graph. Agents must not manually run ruff, mypy,
pytest, frontend checks, full audit, or guard commands one by one; `check`
does all of that and records sanitized check events in the committed ledger.

```bash
python -m scistudio.qa.governance.gate_record check \
  [--base origin/main] \
  [--head HEAD] \
  [--mode local|pre-commit|commit-msg|pre-push|pre-pr|ci] \
  [--pr-body-file .workflow/local/pr-body.md] \
  [--owner-directive "<late scope update>"] \
  [--include <path-or-glob>] \
  [--issue <number>] \
  [--docs-updated <path>] \
  [--docs-na "<class>:<rationale>"] \
  [--test-path <path>] \
  [--test-na "<class>:<rationale>"] \
  [--check <check-name>] \
  [--check-na "<check-name>:<rationale>"] \
  [--admin-label admin-approved:bypass|admin-approved:core-change|admin-approved:merge] \
  [--only <check-name>] \
  [--skip-execution]
```

`check` automatically:

1. Observes the current git diff (objective changed-file set, not agent
   declarations).
2. Infers the tier-selected CI-equivalent check set from the CI workflow graph
   using the same path filters CI uses.
3. Runs all required local commands at CI-resolved tool versions in a
   CI-equivalent importable environment (without `pip install -e .`).
4. Writes raw transcripts only to ignored local paths under
   `.workflow/local/**`.
5. Records sanitized check events in the committed ledger.
6. Runs all applicable guards through the shared evaluator.
7. Records a reconciliation event.
8. Exits nonzero when required obligations remain unsatisfied and prints an
   "Unsatisfied obligations" section with exact repair hints.

The `--mode` argument dispatches behavior for different callers:

| Mode | Caller | Behavior |
|---|---|---|
| `local` | Manual `gate_record check` | Full local CI-equivalent preflight at the selected tier; PR-state facts recorded as pre-PR gaps, not failures |
| `pre-commit` | Pre-commit hook | Fast structural reconciliation on staged diff |
| `commit-msg` | Commit-msg hook | Validate required commit trailers |
| `pre-push` | Pre-push hook | Pre-push reconciliation |
| `pre-pr` | PR wrapper and pre-PR hook | Pre-PR readiness with `--pr-body-file`; pre-PR-impossible findings handled internally |
| `ci` | CI workflow | Authoritative mode with full PR context; verifies label provenance |

Local and CI modes use the same evaluator. The only difference is that CI mode
has real PR metadata and verifies label-actor provenance, while local modes
record those as known pre-PR gaps.

`--only` is a recovery aid, not a final readiness mode. A final PR-ready
`check` must run or validate the complete tier-selected check set.
`--skip-execution` may only reconcile already-recorded valid check events.

Tier-selected check breadth:

- **Tier 1**: runs a full local mirror of the merge-blocking CI command surface,
  whether or not the observed diff appears to need every job.
- **Tier 2**: runs the common governance/lint/audit baseline plus all CI jobs
  relevant to the observed diff.
- **Tier 3**: runs only mandatory checks for the observed diff and repository
  gate rules.

Compatibility aliases exposed by the current CLI:

- `start` delegates to `init`
- `pre-commit` delegates to `check --mode pre-commit`
- `commit-msg <file>` delegates to `check --mode commit-msg <file>`
- `pre-push` delegates to `check --mode pre-push`
- `pr-ready` delegates to `check --mode pre-pr`
- `ci` delegates to `check --mode ci`

### 2.5 `finalize` — Record Commit And PR Provenance

`finalize` has two valid modes. `--pr` is not required before the PR exists,
and `--pr-body-file` is not required after the PR exists.

**Pre-PR finalize** (before the PR exists):

```bash
python -m scistudio.qa.governance.gate_record finalize \
  --base origin/main \
  --head HEAD \
  --commit <sha> \
  --pr-body-file .workflow/local/pr-body.md \
  --closes "#<issue>" \
  [--owner-directive "<final owner instruction>"] \
  [--include <path-or-glob>] \
  [--docs-updated <path>] \
  [--docs-na "<class>:<rationale>"] \
  [--test-path <path>] \
  [--test-na "<class>:<rationale>"]
```

**Post-PR finalize** (after the PR is created):

```bash
python -m scistudio.qa.governance.gate_record finalize \
  --commit <sha> \
  --pr <url-or-number> \
  --pr-body-file .workflow/local/pr-body.md
```

Pre-PR `finalize` re-observes the diff, validates the intended PR body's issue
closure, and reruns reconciliation. It records that the candidate is ready to
open a PR if all non-PR-state obligations pass.

Post-PR `finalize` records the PR URL or number and reruns reconciliation with
PR metadata. It fails when checks are stale, required issue closure is missing
from the PR body, required docs or tests are absent, or tier-selected check
obligations are unsatisfied.

CI mode still discovers and validates this post-PR finalized ledger after it is
committed back to the PR branch. Finalized ledger state is excluded only from
ordinary local active-session discovery, where it means "do not keep editing this
completed gate as the current task."

### 2.6 Compatibility Aliases

| Old subcommand | Delegates to |
|---|---|
| `start` | `init` |
| `pre-commit` | `check --mode pre-commit` |
| `commit-msg <file>` | `check --mode commit-msg <file>` |
| `pre-push` | `check --mode pre-push` |
| `pr-ready` | `check --mode pre-pr` |
| `ci` | `check --mode ci` |

Compatibility aliases delegate to the ledger implementation. They must not own
validation decisions independently. New instructions should prefer the
canonical `init`, `amend`, `check`, and `finalize` commands.

### 2.7 Bypass Labels

The valid administrator bypass labels are:

| Label | Satisfies |
|---|---|
| `admin-approved:bypass` | Bypass AI gate workflow steps when CI verifies provenance |
| `admin-approved:core-change` | Protected core path authorization only |
| `admin-approved:merge` | Authorization for AI-assisted merge into `origin/main` only |
| `human-authored` | Human AI-harness bypass at PR level |

Local ledger records of requested labels are not authoritative; CI verifies the
observed PR label and actor provenance.

### 2.8 CLI Exit Codes

| Code | Meaning |
|---:|---|
| 0 | Command completed; current reconciliation passed |
| 1 | Command completed; reconciliation failed (unsatisfied obligations) |
| 2 | Invalid CLI usage |
| 3 | Ledger schema or migration error |
| 4 | Required external tool unavailable and no accepted N/A rationale exists |
| 5 | Privacy/sanitization violation in a would-be committed ledger event |

## 3. Step-By-Step Procedure

### 3.1 Before Step 1

1. Read `AGENTS.md`.
2. Read this workflow.
3. Select the correct persona (see §1.3 above).
4. Select the task kind (see §1.2 above).
5. Identify the relevant task-specific rule under
   `docs/ai-developer/specific_rules/`.
6. Identify whether the task touches source, package, workflow, architecture,
   governance, Sentrux rule, or documentation-only files.
7. Identify whether docs under `docs/ai-developer/**` are in scope.
   Changes to AI developer workflow docs are governance-surface changes and
   require `--governance-touch true`.

Use the GitHub MCP if available for issue and PR metadata. If it is not
available, use `gh`.

### 3.2 Step 1: Scope And Issue

Create or update the ledger with:

```bash
python -m scistudio.qa.governance.gate_record init \
  --task-kind <task-kind> \
  --persona <persona> \
  --runtime <runtime-id> \
  --branch <branch> \
  --owner-directive "<owner instruction>" \
  [--issue <number>] \
  [--include <path-or-glob>] \
  [--exclude <path-or-glob>] \
  [--governance-touch true|false]
```

The ledger must capture `task_kind`, `persona`, `runtime`, `branch`,
`owner_directive`, declared scope when known, `governance_touch`, and issue
links when known.

- For Tier 1 tasks (`feature`, `refactor`): issue and `--include` are required
  at `init`.
- For Tier 2 tasks: issue and scope may be added during plan, amend, or check,
  but must reconcile before PR readiness.
- For Tier 3 tasks: issue and scope may be added by plan, amend, check, or
  finalize, but must reconcile before PR readiness.

Find or create the GitHub issue before implementation work is committable.
Prefer an existing issue when one already tracks the work.

With `gh`:

```bash
gh issue list --search "<keywords>"
gh issue view <issue-number>
gh issue create --title "<title>" --body "<body>"
```

Record the issue number in the ledger. For hotfix batches and guided sessions,
record every issue fixed by the batch.

If Sentrux MCP is available, start a Sentrux baseline:

```text
mcp__sentrux__.scan(path=<repo-root>)
mcp__sentrux__.session_start()
```

When Sentrux MCP is unavailable, record that explicitly. Sentrux evidence is
recorded as a guard event inside `gate_record check`; the CLI fallback is:

```bash
sentrux scan .
sentrux check .
```

No AI-authored PR is ready when the ledger lacks issue linkage.

### 3.3 Step 2: Plan

Record planned files and expected artifacts with:

```bash
python -m scistudio.qa.governance.gate_record plan \
  [--include <path-or-glob>] \
  [--owner-directive "<plan details>"] \
  [--docs-updated <path> | --docs-na "<class>:<rationale>"] \
  [--test-path <path> | --test-na "<class>:<rationale>"] \
  [--check <check-name>] \
  [--admin-label <label>]
```

The plan must record:

- planned files and directories;
- expected docs, tests, changelog, ADR/spec/addendum, and checklist landing,
  or explicit N/A rationale for each documentation class not required;
- required checks (the evaluator infers a baseline from the diff, but
  task-specific extras may be declared here);
- expected Sentrux applicability;
- implementation-test expectation;
- whether the change touches governance files or protected core paths.

For Tier 1 tasks: plan is required before implementation or broad edits, and
must declare expected docs/tests/checks or N/A rationale.
For Tier 2 tasks: plan is required before final check; may be partial during
live debugging.
For Tier 3 tasks: plan is optional unless the evaluator needs early
docs/tests/scope guidance.

Scope additions after this point require a gate-record amendment before the
agent stages or commits the extra files.

### 3.4 Step 3: Implement

Keep changes within declared scope plus any recorded owner directive events.

The worktree write guard PreToolUse hook
(`scripts/hooks/check-worktree-write-guard.sh`) prevents AI agents that have
not set up a dedicated worktree from writing to the main checkout. AI-authored
work must happen in a linked git worktree. The guard blocks writes when the
target file resolves into the main (primary) working tree and allows all writes
inside linked worktrees and all writes outside the repository entirely. New
worktrees are auto-provisioned with this hook via
`src/scistudio/agent_provisioning/templates/hook_worktree_write_guard.py`.

Before touching newly discovered files outside the original declared scope,
update the ledger with:

```bash
python -m scistudio.qa.governance.gate_record amend \
  --reason "<why scope changed>" \
  --include <path-or-glob>
```

For `guided` work specifically, record every owner directive that authorizes a
scope expansion before editing the newly authorized surface:

```bash
python -m scistudio.qa.governance.gate_record amend \
  --reason "<owner redirected live work>" \
  --owner-directive "<new owner instruction>" \
  [--include <path>]
```

For implementation-category tasks, add or modify at least one test file in the
same PR. Running tests is not enough.

Record deferred work only with tracked issues. Untracked TODOs or deferrals
violate the gate.

Avoid weakening governance, CI, Sentrux, or quality thresholds unless the owner
directive explicitly authorized that scope.

### 3.5 Step 4: Update Docs

Update documentation before running the final test and audit stage.

Record updated paths and explicit N/A rationales with:

```bash
# Record a docs update:
python -m scistudio.qa.governance.gate_record amend \
  --reason "<docs updated>" \
  --docs-updated <path>

# Record docs N/A:
python -m scistudio.qa.governance.gate_record amend \
  --reason "<docs N/A>" \
  --docs-na "<doc-class>:<reason>"
```

The agent must update required docs, specs, ADR addenda, changelog entries, and
checklists. For each documentation class that is not required, record an
explicit N/A rationale.

If documentation work expands the file scope, amend the ledger before editing
the new files.

This step must happen before running `gate_record check` because full audit,
frontmatter lint, doc drift, fact drift, signature drift, and closure checks
evaluate documentation state.

### 3.6 Step 5: Test And Checks

Run `gate_record check` after Update Docs is complete. This is the single
command that replaces manually running ruff, mypy, pytest, full audit, and
guard commands separately.

```bash
python -m scistudio.qa.governance.gate_record check \
  --base origin/main \
  --head HEAD \
  [--test-path <path>] \
  [--docs-updated <path>] \
  [--docs-na "<class>:<rationale>"] \
  [--admin-label <label>]
```

`gate_record check` derives the required check set from the observed diff,
task kind, persona, plan, and the CI workflow graph using the same path filters
CI uses. It runs required commands at the CI-resolved tool versions in a
CI-equivalent importable environment, records sanitized check events in the
committed ledger, runs all applicable guards, records a reconciliation event,
and exits nonzero with repair hints when any obligation remains unsatisfied.

Check evidence is incremental. A check event remains valid only for the covered
surface and input fingerprint it recorded. A later Python edit invalidates
Python lint/type/test evidence for that surface; it does not automatically
invalidate unrelated backend unit-test evidence.

Committed ledger events must not contain absolute local filesystem paths, raw
stdout/stderr transcripts, local usernames, home directories, temp directories,
virtualenv paths, or environment variable dumps. Raw transcripts are written
only to ignored local paths under `.workflow/local/**` and must never be
committed.

When generated facts are part of the change or full audit reports stale facts,
also run:

```bash
python scripts/audit/generate_facts.py --check
```

For Sentrux MCP-capable sessions, run:

```text
mcp__sentrux__.rescan()
mcp__sentrux__.check_rules()
mcp__sentrux__.health()
mcp__sentrux__.session_end()
```

When Sentrux MCP is unavailable but the CLI is available:

```bash
sentrux scan .
sentrux check .
```

Sentrux evidence is recorded automatically as a guard event inside
`gate_record check`. There is no separate Sentrux gate-recording subcommand in
the current workflow; run the scanner only when diagnosing or when a
gate-selected check asks for supporting local output.

For a pre-PR preflight that also validates the intended PR body:

```bash
python -m scistudio.qa.governance.gate_record check \
  --mode pre-pr \
  --base origin/main \
  --head HEAD \
  --pr-body-file .workflow/local/pr-body.md
```

Raw terminal output and chat summaries are not gate evidence. The committed
ledger's sanitized check events and reconciliation events are the machine-
readable proof.

### 3.7 Step 6: Commit And Submit PR

Commit the gate ledger together with the code or documentation change.

AI-authored commits must include these trailers:

```text
Gate-Record: .workflow/records/<record>.json
Task-Kind: hotfix|bugfix|feature|refactor|docs|maintenance|manager|guided
Issue: #<number>
Assisted-by: <runtime>:<model-or-agent-id>
```

Run pre-PR finalize to confirm the candidate is ready before opening the PR:

```bash
python -m scistudio.qa.governance.gate_record finalize \
  --base origin/main \
  --head HEAD \
  --commit <sha> \
  --pr-body-file .workflow/local/pr-body.md \
  --closes "#<issue>"
```

Push and open the PR using the gate-aware wrapper:

```bash
git push -u origin HEAD
python scripts/scistudio_pr_create.py \
  --title "<type>(#<issue>): <summary>" \
  --body "<body>"
```

The wrapper runs `gate_record check --mode pre-pr` (or pre-PR finalize)
locally before invoking `gh pr create`. Pre-PR-impossible findings (core-change
label provenance, merge-guard) are handled internally by the evaluator's pre-PR
mode rather than by a caller-side filter. `--dry-run` runs the pre-flight
without invoking `gh`. Set `SCISTUDIO_SKIP_PREFLIGHT=1` only for emergency
one-off escapes; CI will still run the full evaluator in the cloud.

Direct `gh pr create` invocation remains supported for non-AI work or when the
wrapper is unavailable, but AI-authored PRs that skip the wrapper should expect
more CI fix-and-push iterations.

After the PR is created, run post-PR finalize:

```bash
python -m scistudio.qa.governance.gate_record finalize \
  --commit <sha> \
  --pr <url-or-number> \
  --pr-body-file .workflow/local/pr-body.md
```

Commit and push the resulting ledger update. The CI workflow's
`gate_record check --mode ci` discovery includes finalized ledgers so the
committed PR provenance remains machine-verifiable.

When wrapper, hook, gate-record, CI, or AI-runtime behavior changes, explicitly
check whether these docs also need updates:
`docs/ai-developer/rules.md`,
`docs/ai-developer/specific_rules/gated-workflow.md`,
`docs/ai-developer/specific_rules/agent-dispatch.md`, and
`docs/ai-developer/templates/*dispatch*.md`. Record updated paths or N/A
rationales in the ledger docs events.

The PR body must name the gate record path and close every issue listed in the
ledger using GitHub closing keywords:

```text
Gate record: .workflow/records/<record>.json

Closes #1234
Fixes #1235
Resolves #1236
```

Referencing an issue without a closing keyword is not sufficient. If the ledger
lists multiple issues, the PR body must close all of them or explicitly mark
non-closed issues as follow-up references with owner-approved rationale.

Let CI re-run gate validation, QA full audit, and Sentrux checks. Local
evidence helps review; CI evidence is authoritative.

## 4. MUSTs

- MUST use `python -m scistudio.qa.governance.gate_record` for AI gate ledger
  creation, updates, and validation.
- MUST keep `AGENTS.md` as the hard policy entry point.
- MUST use a committed gate ledger for AI-authored work.
- MUST record issue linkage before implementation work is committable.
- MUST record scope include/exclude paths or owner directive events before
  editing.
- MUST amend the ledger before touching files outside the current declared
  scope or directive-authorized surface.
- MUST update docs before recording final test and audit evidence.
- MUST add or modify tests for implementation-category work.
- MUST run `gate_record check` which records QA full audit evidence, Sentrux
  guard evidence, and all tier-selected CI-equivalent check evidence.
- MUST state when Sentrux MCP is unavailable and record the CLI fallback.
- MUST avoid claiming Sentrux Pro-only or unchecked diagnostics as completed.
- MUST include AI commit trailers.
- MUST close every gate issue in the PR body with closing keywords.
- MUST treat CI evidence as authoritative.
- MUST use bypass labels exactly as accepted by the gate CLI. The valid bypass
  labels are: `admin-approved:bypass`, `admin-approved:core-change`,
  `admin-approved:merge`, `human-authored`.
- MUST use local bypass labels only when the owner authorizes that bypass.
- MUST treat `admin-approved:core-change` as authorization for protected core
  paths only, not as a broad gate or bypass.
- MUST record bypass label use in the ledger or manager checklist.
- MUST use `gate_record check --mode pre-pr` or pre-PR `finalize` before PR
  creation; raw command output is not gate evidence.
- MUST never merge a PR as an AI agent without explicit administrator
  authorization.
- MUST NOT commit or push raw transcripts, absolute paths, usernames, temp
  directories, virtualenv paths, or environment dumps in ledger events.

## 5. Hard Fail Points

Local hooks or CI must fail AI-authored work when:

- no committed gate ledger exists for the branch or PR;
- the gate ledger was not created or updated through the repository-owned gate
  CLI;
- the gate ledger lacks issue linkage;
- the gate ledger branch, issue, or changed files do not match the PR;
- new gate ledgers omit `persona` or use an unsupported persona;
- observed diff contains files outside the effective scope (declared scope plus
  recorded owner directive events) without a recorded amendment;
- governance files are touched without `governance_touch=true`;
- governance, CI, Sentrux, or quality thresholds are weakened without
  owner-approved scope;
- implementation-category work changes implementation files without adding or
  modifying test files;
- required docs, tests, changelog entries, or N/A rationales are missing;
- required checks are missing or failing;
- QA full audit evidence is missing when the tool is available;
- full-audit failures are unclassified during the transition phase;
- Sentrux applies but evidence is missing or failing;
- the gate ledger claims Pro-only Sentrux diagnostics;
- the PR body does not close every issue listed in the gate ledger;
- required commit trailers are missing;
- protected core paths are changed without valid administrator authorization;
- human or administrator bypass labels have invalid provenance;
- an AI agent attempts to merge without valid administrator authorization;
- committed ledger events contain absolute local paths, raw transcripts,
  environment dumps, or other local-machine details.
