---
title: "AI Gated Workflow Specific Rules"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
related_specs:
  - adr-042-gate-record-sentrux-workflow
language_source: en
---

# AI Gated Workflow Specific Rules

## 1. What Is The Gate Workflow

The gate workflow is the required delivery lifecycle for AI-authored work in
SciStudio. It turns an AI task into reviewable repository evidence by recording
scope, issue linkage, plan, docs, tests, checks, commit provenance, and PR
provenance in a committed gate record.

The gate is not a replacement for issues, branches, review, CI, or owner
approval. It is the AI work record that lets local hooks, CI, and reviewers
verify that an agent stayed within scope and produced the required evidence.

The gate has six stages:

1. Scope And Issue
2. Plan
3. Implement
4. Update Docs
5. Test And Checks
6. Commit And Submit PR

The gate record is committed repository evidence. Local-only state and chat
self-attestation are not gate evidence.

## 2. Required AI Gate CLI

AI agents must use the repository-owned gate-record CLI to create, update, and
validate the committed gate record. The CLI may expose additional convenience
aliases, but the commands below are the normative AI-facing interface.

Start a gate record:

```bash
python -m scistudio.qa.governance.gate_record start \
  --task-kind feature|bugfix|hotfix|refactor|docs|maintenance|manager \
  --issue <number> \
  --branch <branch> \
  --owner-directive "<owner instruction>" \
  --include <path-or-glob> \
  --exclude <path-or-glob> \
  --record .workflow/records/<issue>-<task-slug>.json
```

Record the plan:

```bash
python -m scistudio.qa.governance.gate_record plan \
  --record .workflow/records/<issue>-<task-slug>.json \
  --files <path-or-glob> \
  --docs <path-or-na> \
  --tests <path-or-na> \
  --checks ruff,format,pytest,full_audit,sentrux
```

Amend scope:

```bash
python -m scistudio.qa.governance.gate_record amend \
  --record .workflow/records/<issue>-<task-slug>.json \
  --reason "<why scope changed>" \
  --include <path-or-glob>
```

Record documentation landing:

```bash
python -m scistudio.qa.governance.gate_record docs \
  --record .workflow/records/<issue>-<task-slug>.json \
  --updated <path> \
  --na <doc-class>:<reason>
```

Record a completed check:

```bash
python -m scistudio.qa.governance.gate_record check \
  --record .workflow/records/<issue>-<task-slug>.json \
  --name <check-name> \
  --command "<command or MCP tool id>" \
  --status pass|fail|skipped \
  --exit-code <code> \
  --output <path-or-summary>
```

Record Sentrux evidence:

```bash
python -m scistudio.qa.governance.gate_record sentrux \
  --record .workflow/records/<issue>-<task-slug>.json \
  --mode free-tier \
  --status pass|fail|skipped \
  --evidence <json-path-or-summary>
```

Finalize commit and PR provenance:

```bash
python -m scistudio.qa.governance.gate_record finalize \
  --record .workflow/records/<issue>-<task-slug>.json \
  --commit <sha> \
  --pr <url> \
  --closes "#<issue>"
```

Validate local and CI boundaries:

```bash
python -m scistudio.qa.governance.gate_record pre-commit --staged

python -m scistudio.qa.governance.gate_record pre-commit \
  --staged \
  --bypass-label human-authored|admin-approved:ai-override|admin-approved:core-change|admin-approved:merge

python -m scistudio.qa.governance.gate_record commit-msg <commit-msg-file> \
  --bypass-label human-authored|admin-approved:ai-override|admin-approved:core-change|admin-approved:merge

python -m scistudio.qa.governance.gate_record pre-push \
  --bypass-label human-authored|admin-approved:ai-override|admin-approved:core-change|admin-approved:merge

python -m scistudio.qa.governance.gate_record ci \
  --gate-record .workflow/records/<issue>-<task-slug>.json \
  --base <base-ref> \
  --head <head-ref> \
  --pr-body <path-or-text>
```

The legacy `.workflow/gate.py` may remain as a migration helper, but it is not
sufficient gate evidence unless it delegates to this CLI or emits the committed
gate record required by this workflow.

## 3. Step-By-Step Procedure

### 3.1 Before Step 1

1. Read `AGENTS.md`.
2. Read this workflow.
3. Select the correct persona:
   - `manager`
   - `implementer`
   - `adr_author`
   - `audit_reviewer`
4. Select the task kind:
   - `hotfix`
   - `bugfix`
   - `feature`
   - `refactor`
   - `docs`
   - `maintenance`
   - `manager`
5. Identify the relevant task-specific rule under
   `docs/ai-developer/specific_rules/`.
6. Identify whether the task touches source, package, workflow, architecture,
   governance, Sentrux rule, or documentation-only files.

Use the GitHub MCP if available for issue and PR metadata. If it is not
available, use `gh`.

### 3.2 Step 1: Scope And Issue

Create or update the gate record with:

```bash
python -m scistudio.qa.governance.gate_record start \
  --task-kind <task-kind> \
  --issue <number> \
  --branch <branch> \
  --owner-directive "<owner instruction>" \
  --include <path-or-glob> \
  --exclude <path-or-glob> \
  --record .workflow/records/<issue>-<task-slug>.json
```

The gate record must capture `task_kind`, `branch`, `owner_directive`,
`scope.include`, `scope.exclude`, `governance_touch`, and expected artifact
classes.

Find or create the GitHub issue before implementation work is committable.
Prefer an existing issue when one already tracks the work.

With `gh`:

```bash
gh issue list --search "<keywords>"
gh issue view <issue-number>
gh issue create --title "<title>" --body "<body>"
```

Record the issue number and URL in the gate record. For hotfix batches, record
every issue fixed by the batch.

If Sentrux MCP is available, start a Sentrux baseline:

```text
mcp__sentrux__.scan(path=<repo-root>)
mcp__sentrux__.session_start()
```

Record the Sentrux session start result in the gate record when available. If
Sentrux MCP is unavailable, the gate record must state that explicitly and
record the fallback command expected in CI, usually:

```bash
sentrux check .
```

No AI-authored PR is ready when the gate record lacks issue linkage.

### 3.3 Step 2: Plan

Record planned files and directories with:

```bash
python -m scistudio.qa.governance.gate_record plan \
  --record .workflow/records/<issue>-<task-slug>.json \
  --files <path-or-glob> \
  --docs <path-or-na> \
  --tests <path-or-na> \
  --checks ruff,format,pytest,full_audit,sentrux
```

The plan must record:

- planned files and directories;
- expected docs, tests, changelog, ADR/spec/addendum, and checklist landing;
- required checks;
- expected Sentrux applicability;
- implementation-test expectation;
- whether the change touches governance files or protected core paths.

At minimum, source or governance changes require `ruff`, relevant tests,
ADR-042 QA full audit, and Sentrux applicability evidence. Frontend changes
require the configured frontend checks.

For implementation-category tasks, record the expected test files that will be
added or modified. Implementation-category work includes feature, bugfix,
hotfix, refactor, and maintenance work that changes source, package, frontend,
workflow, gate, or governance implementation files.

Record whether Sentrux applies. If it does not apply, record a short N/A
rationale.

Scope additions after this point require a gate-record amendment before the
agent stages or commits the extra files.

### 3.4 Step 3: Implement

Keep changes within `scope.include` and outside `scope.exclude`.

Before touching newly discovered files outside the original plan, update the
gate record with:

```bash
python -m scistudio.qa.governance.gate_record amend \
  --record .workflow/records/<issue>-<task-slug>.json \
  --reason "<why scope changed>" \
  --include <path-or-glob>
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
python -m scistudio.qa.governance.gate_record docs \
  --record .workflow/records/<issue>-<task-slug>.json \
  --updated <path> \
  --na <doc-class>:<reason>
```

The agent must update required docs, specs, ADR addenda, changelog entries, and
checklists. For each documentation class that is not required, record an
explicit N/A rationale.

If documentation work expands the file scope, amend the gate record before
editing the new files.

This step must happen before QA full audit because full audit, frontmatter
lint, doc drift, fact drift, signature drift, and closure checks evaluate
documentation state.

### 3.6 Step 5: Test And Checks

Run and record the checks declared in the plan after Update Docs is complete.

For a typical source, governance, or architecture-relevant change:

```bash
ruff check .
ruff format --check .
pytest <targeted-tests-or-test-directory>
python -m scistudio.qa.audit.full_audit \
  --repo-root . \
  --format json \
  --output docs/audit/full-audit-latest.json
```

Each completed check must be recorded with:

```bash
python -m scistudio.qa.governance.gate_record check \
  --record .workflow/records/<issue>-<task-slug>.json \
  --name <check-name> \
  --command "<command or MCP tool id>" \
  --status pass|fail|skipped \
  --exit-code <code> \
  --output <path-or-summary>
```

When generated facts are part of the change or full audit reports stale facts,
also run and record:

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

When Sentrux MCP is unavailable but the CLI is available, run:

```bash
sentrux scan .
sentrux check .
```

Record Sentrux evidence with:

```bash
python -m scistudio.qa.governance.gate_record sentrux \
  --record .workflow/records/<issue>-<task-slug>.json \
  --mode free-tier \
  --status pass|fail|skipped \
  --evidence <json-path-or-summary>
```

The gate record must store each check's command or MCP tool id, status or exit
code, timestamp, and output path or compact machine-readable result.

For QA full audit, the record must store the output path, `blocks_merge` status
when reported, and any known-debt classification. During the technical-debt
handling phase, known full-audit findings may be recorded without immediately
blocking every PR, but missing full-audit evidence is still a gate violation.

For implementation-category tasks, the gate record must also store the changed
test paths. Running tests is not sufficient when no test file is added or
modified.

For Sentrux, the record must store free-tier mode, `rules_checked`,
`total_rules_defined` when reported, pass/fail status, relevant thresholds from
`.sentrux/rules.toml`, and `pro_required: false`.

### 3.7 Step 6: Commit And Submit PR

Commit the gate record with the code or documentation change.

AI-authored commits must include these trailers:

```text
Gate-Record: .workflow/records/<record>.json
Task-Kind: hotfix|bugfix|feature|refactor|docs|maintenance|manager
Issue: #<number>
Assisted-by: <runtime>:<model-or-agent-id>
```

Push the branch and open the PR. **Prefer the
`scripts/scistudio_pr_create.py` wrapper over invoking `gh pr create`
directly** (#1360): it pre-flights `gate_record ci` with the real PR body
locally and short-circuits the open-PR step when CI would reject the
record. The wrapper filters `core_change_guard` / `pr_merge_guard` /
`human_bypass_guard` findings because those guards depend on PR labels
that cannot exist before the PR does — CI is the authoritative enforcer
for that subset.

```bash
git push -u origin HEAD
python scripts/scistudio_pr_create.py \
  --title "<type>(#<issue>): <summary>" \
  --body "<body>"
```

The wrapper accepts every `gh pr create` flag verbatim and passes them
through. `--dry-run` runs the pre-flight without invoking `gh`. Set
`SCISTUDIO_SKIP_PREFLIGHT=1` only for emergency one-off escapes; CI will
still run the full guard set in the cloud.

Direct `gh pr create` invocation remains supported for non-AI work or
when the wrapper is unavailable, but AI-authored PRs that skip the
wrapper SHOULD expect more CI fix-and-push iterations.

Record final commit and PR evidence with:

```bash
python -m scistudio.qa.governance.gate_record finalize \
  --record .workflow/records/<issue>-<task-slug>.json \
  --commit <sha> \
  --pr <url> \
  --closes "#<issue>"
```

The PR body must name the gate record path and close every issue listed in the
gate record using GitHub closing keywords:

```text
Gate record: .workflow/records/<record>.json

Closes #1234
Fixes #1235
Resolves #1236
```

Referencing an issue without a closing keyword is not sufficient. If a gate
record lists multiple issues, the PR body must close all of them or explicitly
mark non-closed issues as follow-up references with owner-approved rationale.

Let CI re-run gate validation, QA full audit, and Sentrux checks. Local
evidence helps review; CI evidence is authoritative.

## 4. MUSTs

- MUST use `python -m scistudio.qa.governance.gate_record` for AI gate record
  creation, updates, and validation.
- MUST keep `AGENTS.md` as the hard policy entry point.
- MUST use a committed gate record for AI-authored work.
- MUST record issue linkage before implementation work is committable.
- MUST record scope include/exclude paths before editing.
- MUST amend the gate record before touching files outside the current plan.
- MUST update docs before recording final test and audit evidence.
- MUST add or modify tests for implementation-category work.
- MUST record QA full audit evidence when the tool is available.
- MUST record Sentrux free-tier evidence when Sentrux applies.
- MUST state when Sentrux MCP is unavailable and record the CLI fallback.
- MUST avoid claiming Sentrux Pro-only or unchecked diagnostics as completed.
- MUST include AI commit trailers.
- MUST close every gate issue in the PR body with closing keywords.
- MUST treat CI evidence as authoritative.
- MUST use bypass labels exactly as accepted by the gate CLI.
- MUST use local bypass labels only when the owner authorizes that bypass.
- MUST record bypass label use in the gate record or manager checklist.
- MUST never merge a PR as an AI agent without explicit administrator
  authorization.

## 5. Hard Fail Points

Local hooks or CI must fail AI-authored work when:

- no committed gate record exists for the branch or PR;
- the gate record was not created or updated through the repository-owned gate
  CLI;
- the gate record lacks issue linkage;
- the gate record branch, issue, or changed files do not match the PR;
- staged or changed files exceed `scope.include` without an amendment;
- staged or changed files match `scope.exclude`;
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
- the gate record claims Pro-only Sentrux diagnostics;
- the PR body does not close every issue listed in the gate record;
- required commit trailers are missing;
- protected core paths are changed without valid administrator authorization;
- human or administrator bypass labels have invalid provenance;
- an AI agent attempts to merge without valid administrator authorization.
