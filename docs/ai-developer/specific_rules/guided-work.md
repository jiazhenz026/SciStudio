---
title: "AI Guided Work Specific Rules"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
language_source: en
---

# AI Guided Work Specific Rules

## 1. Purpose

- Use these rules for AI-authored `guided` task-kind work: owner-directed live
  implementation where scope evolves through recorded owner directive events.

- MUST also run `docs/ai-developer/specific_rules/gated-workflow.md`.

- The `guided` task kind is distinct from `hotfix` and `feature`:
  - `hotfix` is narrow: live-debug one or a few related bugs with owner on-call.
  - `feature` is fully pre-planned: scope, tests, docs, and checks declared
    before implementation.
  - `guided` is owner-directed interactive work that may include feature, bugfix,
    refactor, docs, or maintenance scope, and where the full scope only emerges
    through successive owner directives during the session.

- The persona for `guided` work is always `live_implementer`.
  Read `docs/ai-developer/personas/live-implementer.md` before starting.

## 2. When To Use `guided`

- Use `guided` when:
  - The owner is actively directing work in real time and scope will expand
    through successive directives.
  - The work is too broad to plan fully up front but too deliberate to call a
    hotfix.
  - The owner-guided scope spans multiple task categories (feature + refactor,
    bugfix + docs, etc.).

- Do NOT use `guided` to bypass issue linkage, tests, docs, checks,
  protected-path authorization, branch protection, or CI.
  `guided` adjusts when scope must be declared, not whether it must be.

- Do NOT use `guided` when a `hotfix`, `bugfix`, `feature`, `refactor`, or
  `maintenance` task kind fits exactly. Prefer the narrower kind.

## 3. Strictness Tier Behavior

- `guided` defaults to **Tier 2** (Standard gate).

- The evaluator escalates to **Tier 1** when the observed diff touches:
  - protected core or runtime/engine paths,
  - governance or workflow files,
  - or constitutes a broad cross-module change.

- Agents never choose a tier. The evaluator derives it from `task_kind` and
  then escalates based on what the diff actually touches.

- Tier 2 behavior for `guided`:
  - `init` requires `task_kind=guided`, `persona=live_implementer`, branch, and
    initial owner directive. Issue and scope may be added during the session.
  - Full gate may be incomplete during live owner-guided work.
  - Issue linkage, scope/directive coverage, regression/test evidence, docs
    impact, governance/lint/audit baseline, and changed-surface CI checks MUST
    reconcile before PR readiness.

- When escalated to Tier 1:
  - `check` must run the full local mirror of the merge-blocking CI command
    surface.
  - Missing plan fields are hard failures before PR readiness.

## 4. Scope Expansion Through Owner Directive Events

- Scope expands only through recorded owner directive events.
  An agent MUST NOT edit files outside the current declared scope unless a new
  owner directive explicitly authorizes the expansion.

- Every meaningful owner instruction that redirects or expands work MUST be
  recorded in the ledger using `amend`:

  ```bash
  python -m scistudio.qa.governance.gate_record amend \
    --reason "<why scope is being redirected or expanded>" \
    --owner-directive "<exact or paraphrased owner instruction>" \
    [--include <newly authorized path-or-glob>] \
    [--issue <n>]
  ```

- Directive events are the audit trail that explains why the observed diff
  exceeds the original declared scope. The evaluator trusts recorded directive
  events plus observed diff over unrecorded agent declarations.

- When the owner says "also fix X" or "now refactor Y", the agent must:
  1. Record the directive with `amend` before editing the new surface.
  2. Add the new scope path to `--include`.
  3. Continue implementation.

- If the observed diff at `check` or `finalize` cannot be explained by
  the combination of declared scope plus recorded directive events, the
  evaluator fails reconciliation. There is no silent scope tolerance.

## 5. Stopping To Clarify

- When a directive is ambiguous enough that multiple reasonable interpretations
  lead to materially different code paths, STOP and ask the owner before
  implementing.

- Describe the ambiguity and propose the interpretation you would take.
  Wait for confirmation before recording the directive or editing files.

- Do not silently adopt the broadest interpretation. Prefer the narrowest
  interpretation that satisfies the owner's stated goal.

## 6. Keeping The Ledger Current During A Live Session

- Run `init` at session start before any edits:

  ```bash
  python -m scistudio.qa.governance.gate_record init \
    --task-kind guided \
    --persona live_implementer \
    --runtime <runtime-id> \
    --branch <branch> \
    --owner-directive "<initial owner instruction>" \
    [--issue <n>] \
    [--include <initial-path>]
  ```

- Run `plan` after the initial directive is understood and initial scope is
  known:

  ```bash
  python -m scistudio.qa.governance.gate_record plan \
    --owner-directive "<current owner instruction>" \
    [--include <path>] \
    [--issue <n>] \
    [--test-path <path> | --test-na "<class>:<rationale>"] \
    [--docs-updated <path> | --docs-na "<class>:<rationale>"]
  ```

- Use `amend` as the primary way to record new owner directives and expand
  scope during live work:

  ```bash
  python -m scistudio.qa.governance.gate_record amend \
    --reason "<owner redirected live work>" \
    --owner-directive "<new owner instruction>" \
    [--issue <n>] \
    [--include <path>] \
    [--test-path <path>] \
    [--docs-updated <path>] \
    [--docs-na "<class>:<rationale>"]
  ```

- Run `check` before PR creation. `check` is the main local
  CI-equivalent preflight. The agent must not manually run individual lint,
  type, test, docs, audit, frontend, or guard commands; `check` derives and
  runs the full tier-selected set:

  ```bash
  python -m scistudio.qa.governance.gate_record check \
    --base origin/main \
    --head HEAD \
    [--owner-directive "<late owner instruction>"] \
    [--include <path>] \
    [--issue <n>] \
    [--test-path <path>] \
    [--docs-na "<class>:<rationale>"]
  ```

- Run `finalize` in two stages:
  - Pre-PR (before opening the PR). This reuses current check evidence by
    default; run `check --mode pre-pr` once before this step:

    ```bash
    python -m scistudio.qa.governance.gate_record finalize \
      --base origin/main \
      --head HEAD \
      --commit <sha> \
      --pr-body-file .workflow/local/pr-body.md \
      --closes "#<issue>"
    ```

  - Post-PR (after the PR is created). This records PR provenance locally;
    CI validates label actor/permission provenance:

    ```bash
    python -m scistudio.qa.governance.gate_record finalize \
      --commit <sha> \
      --pr <url-or-number> \
      --pr-body-file .workflow/local/pr-body.md
    ```

## 7. Issue Linkage

- `guided` work does not bypass issue linkage.

- If an issue is known at session start, record it at `init`.

- If an issue is discovered or created during the session (for example a bug
  found while implementing a directive), record it with `amend --issue <n>`.

- Every issue that will be closed by the PR must be linked in the ledger before
  PR readiness. The PR body must close every linked issue with a GitHub closing
  keyword.

- If no issue exists yet, creating or linking one is the agent's responsibility
  before committing or opening a PR. A `guided` session without any issue link
  fails finalize.

## 8. Documentation, Tests, And Checks

All three are mandatory. `guided` does not change the obligation; it changes
when the obligation is recorded.

### 8.1 Documentation

- Update required docs, specs, ADR addenda, changelog entries, and checklists
  before running the final `check`.

- For each documentation class that is not required, record an explicit N/A
  rationale with `--docs-na "<class>:<rationale>"`.

- Changes to `docs/ai-developer/**` are governance-surface changes and require
  `--governance-touch true` plus owner review.

### 8.2 Tests

- For any implementation change: add or modify at least one test file.

- If tests are not required (rare owner-approved exception), record the
  rationale explicitly: `--test-na "implementation:<rationale>"`.

- The evaluator reconciles declared test paths against the observed diff. A
  test path that does not appear in the diff is claimed-but-unverified and does
  not satisfy the test obligation.

### 8.3 Checks

- `gate_record check` runs the tier-selected CI-equivalent check set.

- Do not manually run ruff, mypy, pytest, frontend checks, full audit, or guard
  commands one by one. `check` derives the full set and records sanitized
  evidence.

- When escalated to Tier 1, `check` runs the full local mirror of the
  merge-blocking CI surface.

- When running at Tier 2 (default for `guided`), `check` runs the common
  governance/lint/audit baseline plus all CI jobs relevant to the observed diff.

## 9. Protected-Path Authorization

- `guided` does not bypass protected-path authorization.

- Changes to protected core paths require `admin-approved:core-change`:
  - `src/scistudio/core/**`
  - `src/scistudio/engine/**`
  - `src/scistudio/blocks/**`
  - `src/scistudio/workflow/**`
  - `src/scistudio/utils/**`

- Record expected admin labels before PR creation:
  `amend --admin-label admin-approved:core-change`

- CI verifies label provenance. A locally recorded expected label is not
  authoritative.

## 10. Branch Protection And CI

- `guided` work follows the same branch and PR rules as all AI-authored work.

- Do not push directly to protected branches.

- CI is authoritative. Local gate evidence helps review; CI evidence decides.

- Wait for CI to pass before treating the session as complete.

## 11. Commit Trailers

AI-authored commits for `guided` work must include these trailers:

```text
Gate-Record: .workflow/records/<record>.json
Task-Kind: guided
Issue: #<number>
Assisted-by: <runtime>:<model-or-agent-id>
```

## 12. Definition Of Done For Guided Work

A `guided` session is done only when all of the following are true:

1. All owner directives are recorded in the ledger.
2. Every observed diff file is explained by declared scope or recorded
   directive events.
3. Issue linkage exists and every linked issue has a closing keyword in the PR
   body.
4. Required documentation is updated or explicitly marked N/A with rationale.
5. Required tests are present in the observed diff, or N/A is explicitly
   recorded.
6. `gate_record check --mode pre-pr` passes at the tier selected for this task
   (Tier 2 default, Tier 1 if escalated) and records current check evidence.
7. `gate_record finalize` (pre-PR) confirms the candidate is PR-ready by
   reusing that evidence.
8. PR is opened, post-PR finalize is run, and CI passes.

## 13. Route

Use these rules with:

- `docs/ai-developer/rules.md`
- `docs/ai-developer/specific_rules/gated-workflow.md`
- `docs/ai-developer/personas/live-implementer.md`
- `docs/ai-developer/personas/implementer.md` for implementation work within
  the session
- `docs/ai-developer/personas/adr-author.md` when the session produces ADR or
  spec changes
- `docs/ai-developer/specific_rules/hotfix.md` when the owner explicitly
  switches to hotfix mode mid-session

The `scripts/scistudio_pr_create.py` wrapper is mandatory for every `guided`
PR; see `docs/ai-developer/specific_rules/gated-workflow.md` §3 Step 6.
