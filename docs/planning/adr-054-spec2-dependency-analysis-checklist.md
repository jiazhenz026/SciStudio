---
title: "ADR-054 Spec 2 Notebook Dependency Analysis Agent Dispatch Checklist"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs: [42, 51, 54]
language_source: en
---

# ADR-054 Spec 2 Notebook Dependency Analysis Agent Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: Manage the complete implementation of ADR-054 spec 2
  (`docs/specs/adr-054-notebook-dependency-analysis.md`): dispatch an
  implementer, a no-context adversarial test engineer, and a no-context audit
  reviewer, and deliver one final PR whose title carries `ADR-054 Spec 2`.
- Task kind: `manager`
- Manager persona: `manager`
- Issue: `#2231`
- Gate record: `.workflow/records/2231-track-adr-054-spec2-dependency-analysis.json`
- Branch/worktree plan: manager branch `track/adr-054-spec2-dependency-analysis`
  in `.worktrees/mgr-2231-spec2-dep-analysis`; agent branches
  `feat/2231-dep-analysis-impl`, `test/2231-dep-analysis-adversarial`,
  `audit/2231-dep-analysis-no-context` with dedicated worktrees under
  `.worktrees/`.
- Protected branch: `main`
- Umbrella branch: `track/adr-054-spec2-dependency-analysis`
- Umbrella PR: `#2232`
- Umbrella PR title: `[DO NOT MERGE] ADR-054 Spec 2: notebook dependency analysis`
- Final PR target: `main`
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context:
    `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context:
    `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`

## 2. Scope

- In scope:
  - `src/scistudio/explore/__init__.py`
  - `src/scistudio/explore/dependency_analysis.py`
  - `src/scistudio/explore/fingerprint.py`
  - `tests/explore/test_dependency_analysis.py`
  - `tests/explore/test_fingerprint.py`
  - `tests/explore/test_analysis_differential.py`
  - `tests/explore/fixtures/**`
  - `tests/architecture/test_layer_deps.py` (subsystem enumeration + FR-035)
  - `docs/audit/2026-09-03-adr-054-spec2-no-context.md` (audit report)
- Out of scope:
  - The kernel, execution queue, stale/out-of-order marking application,
    packaged-block run (explore-session spec)
  - The dependency-graph view and cell enable/disable control
    (explore-frontend spec)
  - Notebook file loading/saving (explore-session spec)
  - The panel contract (#2229, in flight under another dispatch)
  - Any frontend (`frontend/**`, `desktop/**`) change
  - Any change under `docs/ai-developer/**` (governance surface)
- Protected paths:
  - None of the in-scope paths are protected-core; layer test change is a
    test file edit.
- Deferred work:
  - N/A

## 3. Conventions

- `[ ]` not started
- `[~]` in progress
- `[x]` done
- `[!]` blocked
- Every completed row MUST include an artifact:
  PR link, commit, test command, report path, or gate-record entry.
- Chat messages are not checklist evidence.
- Agents edit only their own rows.
- Scope changes require gate-record amendment before work continues.

## 4. Manager Preflight

- [x] Dedicated manager branch and worktree created.
      -> `.worktrees/mgr-2231-spec2-dep-analysis` on
      `track/adr-054-spec2-dependency-analysis`
- [x] Existing issue linked, or new issue created only if none exists.
      -> #2231 (created; #2209 is the ADR-level tracker and stays open,
      #2229 tracks spec 1)
- [x] Gate record started.
      -> `.workflow/records/2231-track-adr-054-spec2-dependency-analysis.json`
- [x] Scope include/exclude recorded in the gate record.
      -> ledger init event
- [x] Umbrella branch created. -> `track/adr-054-spec2-dependency-analysis`,
      pushed at 38125e1f6
- [x] Umbrella PR opened. -> https://github.com/jiazhenz026/SciStudio/pull/2232
- [x] Umbrella PR title includes `[DO NOT MERGE]`.
- [x] Protected branch and umbrella PR number recorded in this checklist.
      -> `main`, `#2232`
- [x] No `pip install -e .` environment pollution found.
      -> The shared `.venv` carries a stale editable `.pth` pointing at a
      different checkout; all Python invocations in worktrees MUST set
      `PYTHONPATH="$PWD/src"` (recorded in every dispatch prompt).
- [x] Dispatch checklist copied from the template and committed. -> 38125e1f6
- [~] Dispatch prompts created from the correct prompt template and linked
      below. -> `a-impl.md` committed at 38125e1f6; `a-test.md` and
      `a-audit.md` are written when their dispatch starts (they need the
      integration state at that point).
- [x] Sentrux baseline recorded, or N/A reason recorded.
      -> N/A: Sentrux MCP is not available in this session; agents record
      the CLI fallback or N/A in their own ledgers.

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `N/A`
- Owner authorization source: `N/A`
- Reason: `N/A`

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scistudio.qa.governance.gate_record check --mode pre-commit` | `N/A` | `[ ]` | `<commit hooks removed in #2150; pre-pr mode owns these checks>` |
| Commit message | `python -m scistudio.qa.governance.gate_record check --mode commit-msg` | `N/A` | `[ ]` | `<validated at pre-pr/ci per #2150>` |
| Pre-push | `python -m scistudio.qa.governance.gate_record check --mode pre-push --base origin/main --head HEAD` | `N/A` | `[ ]` | `<reconcile event>` |
| Pre-PR reconcile | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `N/A` | `[ ]` | `<reconcile event>` |

## 5.1 Docs Impact Check

- Wrapper/hook/gate-record/receipt/CI/runtime behavior changed: `no`
- AI docs checked:
  `docs/ai-developer/rules.md`,
  `docs/ai-developer/specific_rules/gated-workflow.md`,
  `docs/ai-developer/specific_rules/agent-dispatch.md`,
  `docs/ai-developer/templates/*dispatch*.md`
- Updated docs or N/A rationale: `N/A — no AI-workflow surface changes; this is
  a new analysis subsystem plus tests.`

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| `A-impl` | `implementer` | `N/A` | `docs/planning/adr-054-spec2-dispatch-prompts/a-impl.md` | Implement the explore dependency-analysis subsystem (spec T-001..T-009, T-011 production code) | `feat/2231-dep-analysis-impl` | `.worktrees/spec2-impl` | `src/scistudio/explore/**`, `tests/architecture/test_layer_deps.py`, own gate ledger | `tests/explore/**`, everything else | `#2231` | `[ ]` |
| `A-test` | `test_engineer` | `no-context (owner-directed adversarial)` | `docs/planning/adr-054-spec2-dispatch-prompts/a-test.md` | Write the adversarial test suite (`tests/explore/**` + fixtures) against the spec and the real code | `test/2231-dep-analysis-adversarial` | `.worktrees/spec2-test` | `tests/explore/**`, own gate ledger | all production code | `#2231` | `[ ]` |
| `A-audit` | `audit_reviewer` | `no-context` | `docs/planning/adr-054-spec2-dispatch-prompts/a-audit.md` | Independent audit of the integrated diff against the spec and ADR-054 | `audit/2231-dep-analysis-no-context` | `.worktrees/spec2-audit` | `docs/audit/2026-09-03-adr-054-spec2-no-context.md`, own gate ledger | all implementation and test code | `#2231` | `[ ]` |

For `test_engineer` rows, the write set defaults to tests, fixtures,
validation scripts, e2e scenarios, audit evidence, and explicitly assigned
QA/governance tooling. Production code paths require a recorded scope
amendment. `A-test` reports production-code defects as findings; fixes land
through `A-impl` (or a manager-sequenced fix dispatch), never through `A-test`.

## 7. Track: ADR-054 Spec 2 — Notebook Dependency Analysis

### 7.1 Track Scope

- Owner: `manager` (this session)
- In scope:
  - Per-cell static facts (symtable + ast, stdlib only): assigned/read names,
    output/input declarations, block calls, magic stripping, flags (FR-005 to
    FR-013)
  - The graph over enabled cells with edge origins, version nodes, unresolved
    reads (FR-014 to FR-019)
  - The four queries (FR-020 to FR-023)
  - Fingerprint + namespace comparison + source-hash-keyed observation
    (FR-024 to FR-030)
  - Cell-metadata record codec (FR-031 to FR-034)
  - Architecture layer test enumeration (FR-035) and stability markers (T-011)
  - The full test suite and fixtures (spec §4.2 test files)
- Out of scope:
  - Everything listed in §2 out-of-scope above
- Required docs:
  - This checklist; the audit report; spec/ADR already exist. No user docs
    (the subsystem has no user-visible surface yet — explore-session spec owns
    that).
- Required tests:
  - `tests/explore/test_dependency_analysis.py`
  - `tests/explore/test_fingerprint.py`
  - `tests/explore/test_analysis_differential.py`
  - `tests/explore/fixtures/**`
  - `tests/architecture/test_layer_deps.py` (modified)

### 7.2 Dispatch

- [ ] Prompt file created or dispatch prompt recorded.
- [ ] Correct prompt template selected.
- [ ] Audit mode recorded when persona is `audit_reviewer` -> `no-context`.
- [ ] Agent branch/worktree assigned.
- [ ] Write set and out-of-scope paths included in prompt.
- [ ] TODO rule included in prompt.
- [ ] Required checks included in prompt.

### 7.3 Implementation

- [ ] `A-impl`: explore package + layer test -> `<commit>`
- [ ] `A-test`: adversarial tests + fixtures -> `<commit>`
- [ ] Audit report committed -> `docs/audit/2026-09-03-adr-054-spec2-no-context.md`

### 7.4 Audit

- [ ] Audit agent assigned, or manager audit completed. -> `A-audit`, no-context
- [ ] Audit report file path assigned.
      -> `docs/audit/2026-09-03-adr-054-spec2-no-context.md`
- [ ] Audit report committed.
- [ ] Audit report merged into final PR evidence path.
- [ ] Findings recorded.
- [ ] P1 findings fixed before integration.
- [ ] P2/P3 findings fixed or tracked with owner-approved rationale.

### 7.5 Integration

- [ ] Agent output reviewed by manager.
- [ ] Scope compliance verified.
- [ ] Conflicts resolved intentionally.
- [ ] Track merged or integrated.

## 8. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Gate ledger check (local) | `python -m scistudio.qa.governance.gate_record check --mode local --base origin/main --head HEAD` | `[ ]` | `<reconcile event or summary>` |
| Targeted tests | `PYTHONPATH="$PWD/src" ../../.venv/Scripts/python.exe -m pytest tests/explore tests/architecture/test_layer_deps.py` | `[ ]` | `<output summary>` |
| Pre-push gate check | `python -m scistudio.qa.governance.gate_record check --mode pre-push --base origin/main --head HEAD` | `[ ]` | `<reconcile event or summary>` |
| Gate ledger check (pre-PR) | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `[ ]` | `<reconcile event or summary>` |
| Gate finalize (pre-PR) | `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#2231"` | `[ ]` | `<ledger path>` |
| Wrapper preflight | `python scripts/scistudio_pr_create.py --dry-run --title "<title>" --body "<body>"` | `[ ]` | `<output>` |

## 9. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| - | - | - | - | - |

## 10. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux
      evidence when needed, commit, and PR evidence.
- [ ] PR closes every issue fixed by the dispatch.
- [ ] CI passed.
- [ ] Checklist final state matches PR and gate record.
