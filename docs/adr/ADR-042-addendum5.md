---
adr: 42
addendum: 5
title: "Local CI-Parity Gate Receipts And Worktree Guards"
status: Accepted
date_created: 2026-05-23
date_accepted: 2026-05-23
date_superseded: null

supersedes: []
superseded_by: null
related: [42]
closes_issues: []
tracking_issue: 1492

is_code_implementation: true
governs:
  modules:
    - scistudio.qa.governance
    - scistudio.qa.governance.gate_record
  contracts:
    - scistudio.qa.governance.gate_record.validation.validate_gate_record
    - scistudio.qa.governance.gate_record.validation.check_pre_push
    - scistudio.qa.governance.gate_record.validation.check_pr_ready
    - scistudio.qa.governance.gate_record.validation.check_pr
    - scistudio.qa.governance.gate_record.workflow.run_ci
    - scistudio.qa.governance.core_change_guard.check
    - scistudio.qa.governance.human_bypass_guard.check
  entry_points: []
  files:
    - docs/adr/ADR-042-addendum5.md
    - docs/specs/adr-042-local-gate-receipts.md
    - AGENTS.md
    - .agents/rules/rules.md
    - .claude/rules/rules.md
    - .codex/rules/rules.md
    - docs/ai-developer/rules.md
    - docs/ai-developer/specific_rules/gated-workflow.md
    - docs/ai-developer/specific_rules/agent-dispatch.md
    - docs/ai-developer/personas/*.md
    - docs/ai-developer/templates/agent-dispatch-checklist-template.md
    - docs/ai-developer/templates/agent-dispatch-prompt-template.md
    - scripts/scistudio_pr_create.py
    - scripts/hooks/**
    - src/scistudio/agent_provisioning/**
    - src/scistudio/qa/governance/**
    - tests/qa/**
    - .gitignore
  excludes: []

tests:
  - tests/qa/test_gate_record.py
  - tests/qa/test_gate_record_ci.py
  - tests/qa/test_gate_record_hooks.py
  - tests/qa/test_core_change_guard.py
  - tests/qa/test_human_bypass_guard.py
  - tests/qa/test_gate_receipt.py
  - tests/qa/test_worktree_write_guard.py

agent_editable: false
assisted_by:
  - "Codex:gpt-5"

phase: implementation
tags: [qa, ci, ai-governance, workflow-gate, local-preflight]
owner: "@jiazhenz026"
co_authors: ["@codex"]
language_source: en
translations: []
---

# ADR-042 Addendum 5: Local CI-Parity Gate Receipts And Worktree Guards

## 1. Decision Summary

This addendum accepts a stricter local gate model for AI-authored SciStudio
work. The model closes the gap between local claims and CI evidence by making
the exact push candidate prove its required checks before `git push` or PR
creation.

The implementation is tracked by issue #1492. The initial implementation adds
`gate_receipt`, shared `gate_record ci` orchestration, scoped local bypass
semantics, PR-wrapper receipt validation, push/PR hook receipt validation, and
AI write-guard provisioning.

| Decision | Change | Enforcement target | Detailed section |
|---|---|---|---|
| D1. CI-parity local gate | Local preflight must evaluate the same blocking workflow-gate rules as CI, except PR-state facts that cannot exist before PR creation | `gate_record ci`, PR wrapper, workflow-gate CI | Section 3 |
| D2. Scoped override semantics | `admin-approved:core-change` authorizes only protected core path changes and must not bypass scope, issue, docs, receipt, or required-check rules | Local hooks and CI guards | Section 4 |
| D3. Local gate receipts | Phase 5 checks must be recorded as machine-readable JSON plus stdout/stderr transcript for the exact push candidate | Pre-push and pre-PR hooks | Section 5 |
| D4. Fingerprint validity | Receipt validity is based on HEAD, base, diff, gate record, PR body, and label/env fingerprints, not on a short time window | Receipt validator | Section 5 |
| D5. Required-check completeness | Every Phase 5 required check plus every diff-inferred CI parity check must appear in the receipt with exit code 0 | Receipt runner and hooks | Section 6 |
| D6. Worktree write guard | AI write tools must be blocked when the target path is outside the assigned worktree or gate scope | Claude Code and Codex project hooks | Section 7 |
| D7. Local-only receipt storage | Receipt logs and JSON files live under `.workflow/local/gate-receipts/`, are gitignored, and must not become committed gate evidence | Git ignore, mod guard, review | Section 5 |
| D8. Runtime parity | The same hard gate must apply to every supported AI runtime working in the repository | Project hook provisioning and AI docs | Section 8 |

### 1.1 Problems Addressed

| Problem | Risk | Decision | Detailed section |
|---|---|---|---|
| Local gate commands and GitHub CI evaluate different guard sets | Agents can pass local checks and still fail avoidable workflow-gate CI | Make local gate validation call the same orchestration as CI | Section 3 |
| `admin-approved:core-change` can locally bypass unrelated checks | A narrow protected-path approval becomes a broad gate escape hatch | Scope override labels to their specific guard only | Section 4 |
| Agents can claim that checks ran without durable stdout/stderr evidence | Reviewers cannot distinguish real verification from self-attestation | Require receipt JSON and transcript logs | Section 5 |
| Agents can run checks, then change files, then push without rerunning | CI catches errors that should have been blocked locally | Bind receipts to exact input fingerprints | Section 5 |
| Frontend/typecheck/build checks can be missed locally | Ordinary CI jobs become the first detector for predictable failures | Infer CI parity checks from the current diff | Section 6 |
| Agents can write to the wrong physical worktree before gate hooks run | Parallel sessions collide or root `main` receives task edits | Add worktree and path guards at write time | Section 7 |
| Runtime-specific hook coverage is uneven | One AI runtime can bypass rules that another runtime enforces | Provision equivalent hooks for supported runtimes | Section 8 |

## 2. Scope

In scope:

- local and CI Workflow Gate parity for AI-authored PR readiness;
- local receipt JSON and transcript logs for Phase 5 checks;
- diff-inferred check requirements that mirror repository CI;
- scoped administrator override semantics;
- write-time worktree and scope enforcement for AI tools;
- AI developer documentation that tells agents how the hard gate works;
- tests for stale receipts, changed diffs, missing checks, nonzero exits,
  wrong worktrees, and scoped bypass behavior.

Out of scope:

- weakening CI, branch protection, Sentrux, quality thresholds, or governance
  path protection;
- treating local receipt logs as committed evidence;
- replacing the committed gate record;
- automatic application of GitHub labels or administrator approvals;
- requiring Sentrux Pro or unchecked diagnostics.

## 3. CI-Parity Gate Orchestration

The Workflow Gate Check in GitHub Actions is the authoritative remote
enforcement point. Local tooling must not implement a looser copy of those
rules.

The implementation must extract the CI guard orchestration into a repository
Python entry point that both GitHub Actions and local commands call. The shared
orchestration must cover at least:

- gate-record schema and stage validation;
- issue closure validation;
- docs landing validation;
- scope include/exclude validation;
- governance-touch validation;
- `core_change_guard`;
- `mod_guard`;
- `weakened_ci_check`;
- Sentrux advisory reporting as defined by ADR-042 Addendum 3.

PR-state guards such as `human_bypass_guard` and `pr_merge_guard` remain CI
authoritative because their required evidence cannot exist before the PR does.

Local pre-PR execution may filter only findings that are structurally
impossible before the PR exists, such as administrator-applied PR labels or a
PR URL recorded by finalization. It must not filter issue, docs, scope, gate
record, receipt, or required-check findings.

## 4. Scoped Override Semantics

Override labels are not interchangeable.

| Label | Allowed scope | Must not bypass |
|---|---|---|
| `human-authored` | AI-only harness checks after authorized label provenance is verified | Repository quality checks, CI, issue closure when required by PR policy |
| `admin-approved:core-change` | Protected core path authorization only | Scope include/exclude, issue linkage, docs landing, full audit, receipt validity, required checks, CI parity |
| `admin-approved:merge` | AI-initiated merge automation only | Test, docs, audit, receipt, and workflow-gate correctness |
| `admin-approved:ai-override` | Explicit one-off AI gate override | Branch protection, normal CI quality checks, owner review |

Local hook bypass handling must be guard-specific. A valid
`admin-approved:core-change` signal may satisfy `core_change_guard`, but the
remaining gate validation must continue to run.

## 5. Local Gate Receipts

The `gate_receipt` implementation must write local-only evidence under:

```text
.workflow/local/gate-receipts/<head-sha>.json
.workflow/local/gate-receipts/<head-sha>.log
```

When a PR body participates in the candidate fingerprint, the implementation
may add a short PR-body hash suffix, for example
`<head-sha>-pr-<bodyhash>.json`, so the pre-push and pre-PR receipts for the
same HEAD can coexist.

The JSON file is the machine-readable receipt. The log file is a human-readable
stdout/stderr transcript. Hooks must validate the JSON file; they must not
parse free-form log text.

The receipt must record at least:

- schema version;
- repository root;
- current branch;
- base ref;
- head SHA;
- diff fingerprint;
- changed files and status summary;
- gate record path and content hash;
- PR body hash when PR body is available;
- relevant bypass labels or local override environment;
- required check list and how it was derived;
- executed command list;
- per-command cwd, argv, started time, ended time, exit code, stdout/stderr
  log offsets or references;
- final pass/fail status.

Receipt validity is an equality check against the current push or PR candidate.
A receipt is invalid when any of these inputs differ from the current state:

- `HEAD`;
- base ref;
- diff fingerprint;
- gate record hash;
- PR body hash when PR body is part of validation;
- bypass label/env fingerprint;
- required-check set.

A time limit may remain as a stale-file safety check, but it is not the primary
correctness rule. A recent receipt for a different diff is invalid.

Receipt logs are local-only. `.workflow/local/**` is ignored and must not be
committed. Committed gate records remain the durable review evidence.

### 5.1 Pre-PR And Pre-Push Candidate Modes

Receipt generation must not depend on an already-created PR. The pre-PR
candidate uses the intended PR body from a local ignored file, commonly
`.workflow/local/pr-body.md`. The PR wrapper must create the PR from the same
body so the receipt's PR-body hash matches the actual candidate.

There are two valid local receipt modes:

| Mode | Required before | Fingerprint includes | Does not require |
|---|---|---|---|
| Pre-PR receipt | `scripts/scistudio_pr_create.py` opens a PR | `HEAD`, base ref, diff, gate record hash, intended PR body hash | Existing PR URL or PR number |
| Pre-push receipt | `git push` sends commits | `HEAD`, base ref, diff, gate record hash | Existing PR URL or PR body |

After PR creation, `gate_record finalize` records PR URL and commit evidence in
the committed gate record. That changes the gate record hash and therefore
invalidates the previous local receipt by design. The agent must generate a new
receipt for the finalize commit before pushing it. CI remains authoritative for
the final PR metadata and label-provenance facts.

## 6. Required Checks

The receipt runner must satisfy two sources of check requirements:

1. checks declared in the gate record's Phase 5 plan;
2. CI parity checks inferred from the current diff.

The hook must fail if any required check is missing, skipped without an
accepted N/A rule, or recorded with a nonzero exit code.

The initial CI parity matrix must include:

| Diff surface | Required local receipt checks |
|---|---|
| Python source, QA, governance, scripts, or tests | `ruff check .`, `ruff format --check .`, `mypy src/scistudio/ --ignore-missing-imports` where dependencies are available, targeted or full `pytest`, `lint-imports` when import contracts apply |
| ADR, spec, architecture, or governed Markdown | `frontmatter_lint` for changed governed docs and ADR-042 `full_audit` |
| Frontend source, package, tests, or config | `npm run lint`, `npm run format:check`, `npm run typecheck`, `npm test`, `npm run build` from `frontend/` |
| Packaging or frontend bundle surfaces | wheel/static smoke checks equivalent to the CI release smoke job |
| GitHub workflow, pre-commit, gate, or governance config | workflow syntax checks where available plus `mod_guard` and `weakened_ci_check` |

The implementation may start with a conservative matrix. If the matrix cannot
determine that a check is unnecessary, it should require the check rather than
letting the candidate reach CI unverified.

## 7. Worktree Write Guard

The worktree guard must run before AI write tools mutate files. It must block
when:

- the current branch is `main` or `HEAD` for AI-authored task work;
- the tool cwd is not the assigned worktree;
- the target path resolves outside the assigned worktree;
- the target path is outside the gate record scope and no gate amendment has
  been recorded;
- the target path is inside `scope.exclude`;
- the gate record branch does not match the current branch.

The guard must normalize absolute paths before comparison. It must treat path
prefix checks as filesystem checks, not string-only checks.

## 8. Runtime Parity

The local gate must apply to every supported AI runtime that works in the
repository.

The implementation must update:

- Claude Code project hooks;
- Codex project hooks or project config;
- runtime provisioning templates under `src/scistudio/agent_provisioning/`;
- AI developer docs and dispatch templates as needed.

Runtime-specific files may only point to canonical policy and shared scripts.
They must not define separate policy.

## 9. Agent Procedure

AI agents must use one of the repository-owned commands before push or PR
creation:

```bash
python -m scistudio.qa.governance.gate_receipt run \
  --gate-record .workflow/records/<record>.json \
  --base origin/main \
  --pr-body-file .workflow/local/pr-body.md
```

For an individual command:

```bash
python -m scistudio.qa.governance.gate_receipt exec \
  --name mypy \
  --gate-record .workflow/records/<record>.json \
  --base origin/main \
  -- mypy src/scistudio/ --ignore-missing-imports
```

Raw command output outside the wrapper may help exploration, but it is not
hard-gate evidence. The pre-push and pre-PR hooks accept only valid receipt
JSON for the exact candidate.

## 10. Verification

The implementation must add regression tests for:

- local `gate_record ci` parity with the CI workflow-gate orchestration;
- `admin-approved:core-change` satisfying only core-change authorization;
- stale receipt rejection after a new commit;
- stale receipt rejection after a gate record edit;
- stale receipt rejection after PR body changes;
- missing required check rejection;
- nonzero command exit rejection;
- frontend diff requiring frontend lint, format, typecheck, test, and build;
- wrong-worktree write rejection;
- outside-scope write rejection;
- `.workflow/local/**` ignored and rejected if staged.

## 11. Consequences

Positive consequences:

- avoidable CI failures move to local hard failures;
- reviewers can inspect real command transcripts when needed;
- local gate evidence becomes candidate-specific instead of self-attested;
- administrator overrides become narrower and safer;
- parallel AI sessions receive earlier physical isolation enforcement.

Negative consequences:

- local preflight becomes heavier for broad diffs;
- hook and receipt tooling must be maintained across AI runtimes;
- contributors need a documented recovery path when local dependencies are
  unavailable.

## 12. Alternatives Considered

| Alternative | Reason rejected |
|---|---|
| Keep a five-minute freshness check only | It does not catch the common case where an agent runs checks, edits files, and pushes within the window |
| Store receipts as committed evidence | Logs can contain local paths or sensitive environment details, and committed gate records already provide durable review evidence |
| Let agents paste stdout in chat | Chat is not repository evidence and cannot be validated by hooks |
| Rely on CI only | This preserves avoidable CI churn and does not prevent repeated low-level failures |
| Use one runtime-specific hook policy | Different AI runtimes would enforce different rules, which violates ADR-042 policy centralization |
