---
title: "ADR-054 Spec 2 Notebook Dependency Analysis Agent Dispatch Checklist"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# ADR-054 Spec 2 Notebook Dependency Analysis Agent Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: `Implement ADR-054 spec 2 and spec 3 in full, restarting spec 2 from scratch, with a final adversarial test engineer and a no-context auditor, delivered as two PRs for owner review.`
- Task kind: `manager`
- Manager persona: `manager`
- Issue: `#2231`
- Gate record: `.workflow/records/2231-track-adr-054-spec2-dependency-analysis.json`
- Branch/worktree plan: manager on `track/adr-054-spec2-dependency-analysis` in
  `.worktrees/mgr-2231-spec2-dep-analysis`; agents on `feat/2231-*`,
  `test/2231-*`, `audit/2231-*` branches, one dedicated worktree each under
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

### 1.1 Restart Note

An earlier dispatch of this spec produced a checklist, three prompt files, and
a gate ledger, and no implementation. The owner directed a full restart. The
earlier checklist and prompt files are replaced by this dispatch; the gate
ledger is retained and amended, because it is the append-only record for this
branch and issue.

## 2. Scope

- In scope:
  - `src/scistudio/explore/__init__.py`
  - `src/scistudio/explore/dependency_analysis.py`
  - `src/scistudio/explore/fingerprint.py`
  - `tests/explore/**`
  - `tests/architecture/test_layer_deps.py`
  - `docs/planning/adr-054-spec2-dependency-analysis-checklist.md`
  - `docs/planning/adr-054-spec2-dispatch-prompts/**`
  - `docs/audit/**` (audit reports only)
  - `.workflow/records/2231-*.json`
- Out of scope:
  - Everything the explore-session spec owns: the kernel, the queue, the marks
    as the session applies them, packaging, lineage, the API.
  - Every frontend path.
  - `docs/specs/adr-054-*.md` — the specs are approved input, not work product.
  - `docs/architecture/**` — owner-controlled.
- Protected paths:
  - None. Spec 2 adds a new subsystem and touches one architecture test.
- Deferred work:
  - N/A at dispatch time. Any deferral must be a `TODO(#NNN)` citing an issue.

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
      `track/adr-054-spec2-dependency-analysis` in
      `.worktrees/mgr-2231-spec2-dep-analysis`.
- [x] Existing issue linked, or new issue created only if none exists.
      `#2231` already tracked this work; no new issue created.
- [x] Gate record started.
      `.workflow/records/2231-track-adr-054-spec2-dependency-analysis.json`.
- [x] Scope include/exclude recorded in the gate record.
- [x] Umbrella branch created.
- [x] Umbrella PR opened. `#2232`.
- [x] Umbrella PR title includes `[DO NOT MERGE]`.
- [x] Protected branch and umbrella PR number recorded in this checklist.
- [x] No `pip install -e .` environment pollution found.
      Every agent prompt forbids it and every gate command uses `PYTHONPATH=./src`.
- [x] Dispatch checklist copied from the template and committed.
- [x] Dispatch prompts created from the correct prompt template and linked
      below.
- [x] Sentrux baseline recorded, or N/A reason recorded.
      N/A: Sentrux MCP is not connected in this session. `gate_record check`
      records the guard event from the CLI when it is available.

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `N/A`
- Owner authorization source: `Owner pre-approved every label this work needs (chat, 2026-09-04). No bypass label is expected for spec 2, which touches no protected path.`
- Reason: `N/A — no bypass needed.`

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scistudio.qa.governance.gate_record check --mode pre-commit` | `N/A` | `[ ]` | |
| Commit message | `python -m scistudio.qa.governance.gate_record check --mode commit-msg` | `N/A` | `[ ]` | |
| Pre-push | `python -m scistudio.qa.governance.gate_record check --mode pre-push` | `N/A` | `[ ]` | |
| Pre-PR reconcile | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `N/A` | `[ ]` | |

## 5.1 Docs Impact Check

- Wrapper/hook/gate-record/receipt/CI/runtime behavior changed: `no`
- AI docs checked:
  `docs/ai-developer/rules.md`,
  `docs/ai-developer/specific_rules/gated-workflow.md`,
  `docs/ai-developer/specific_rules/agent-dispatch.md`,
  `docs/ai-developer/templates/*dispatch*.md`
- Updated docs or N/A rationale: `N/A — spec 2 adds a pure analysis subsystem and changes no AI workflow surface. The governing spec, docs/specs/adr-054-notebook-dependency-analysis.md, already landed in PR #2228.`

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| `S2-B1` | `implementer` | `N/A` | `docs/planning/adr-054-spec2-dispatch-prompts/s2-b1-graph.md` | T-001 to T-006: the package, the layer rule, per-cell static facts, flags, declarations, the graph, the four queries | `feat/2231-dep-analysis-graph` | `.worktrees/s2-b1-graph` | `src/scistudio/explore/__init__.py`, `src/scistudio/explore/dependency_analysis.py`, `tests/explore/test_dependency_analysis.py`, `tests/architecture/test_layer_deps.py`, `tests/architecture/test_placement.py` (amended) | `src/scistudio/explore/fingerprint.py`, `tests/explore/test_fingerprint.py`, everything outside `src/scistudio/explore/` and `tests/explore/` | `#2231` | `[!]` |
| `S2-B2` | `implementer` | `N/A` | `docs/planning/adr-054-spec2-dispatch-prompts/s2-b2-fingerprint.md` | T-007: the fingerprint, the size bound, the unobservable fallback | `feat/2231-fingerprint` | `.worktrees/s2-b2-fingerprint` | `src/scistudio/explore/fingerprint.py`, `tests/explore/test_fingerprint.py` | `src/scistudio/explore/__init__.py`, `src/scistudio/explore/dependency_analysis.py`, `tests/architecture/**` | `#2231` | `[ ]` |
| `S2-C1` | `implementer` | `N/A` | `docs/planning/adr-054-spec2-dispatch-prompts/s2-c1-observation.md` | T-008, T-009, T-011: the namespace comparison, the observation record with source-hash invalidation, the metadata codec, stability markers | `feat/2231-observation-codec` | `.worktrees/s2-c1-observation` | `src/scistudio/explore/__init__.py`, `src/scistudio/explore/dependency_analysis.py`, `src/scistudio/explore/fingerprint.py`, `tests/explore/test_dependency_analysis.py`, `tests/explore/test_fingerprint.py` | `tests/architecture/**`, everything outside `src/scistudio/explore/` and `tests/explore/` | `#2231` | `[ ]` |
| `S2-D1` | `test_engineer` | `N/A` | `docs/planning/adr-054-spec2-dispatch-prompts/s2-d1-adversarial.md` | T-010 and adversarial coverage: the differential harness, the fixtures, and tests that try to break the analysis rather than confirm it | `test/2231-adversarial` | `.worktrees/s2-d1-adversarial` | `tests/explore/**` | Every production path. Report defects, do not fix them. | `#2231` | `[ ]` |
| `S2-E1` | `audit_reviewer` | `no-context` | `docs/planning/adr-054-spec2-dispatch-prompts/s2-e1-audit-no-context.md` | Independent audit of the explore analysis subsystem against the repository's own documents | `audit/2231-no-context` | `.worktrees/s2-e1-audit-nc` | `docs/audit/2026-09-04-explore-dependency-analysis-no-context.md` | Every implementation and test path. Read-only. | `#2231` | `[ ]` |
| `S2-E2` | `audit_reviewer` | `with-context` | `docs/planning/adr-054-spec2-dispatch-prompts/s2-e2-audit-with-context.md` | Audit of the delivered spec 2 work against the spec, the issue, and this checklist | `audit/2231-with-context` | `.worktrees/s2-e2-audit-wc` | `docs/audit/2026-09-04-adr-054-spec2-with-context.md` | Every implementation and test path. Read-only. | `#2231` | `[ ]` |
| `S2-F1` | `implementer` | `N/A` | `docs/planning/adr-054-spec2-dispatch-prompts/s2-f1-fix.md` | Fix the P1 and P2 findings the audits and the adversarial test engineer produce | `fix/2231-audit-findings` | `.worktrees/s2-f1-fix` | `src/scistudio/explore/**`, `tests/explore/**` | Everything else | `#2231` | `[ ]` |

For `test_engineer` rows, the write set should default to tests, fixtures,
validation scripts, e2e scenarios, audit evidence, and explicitly assigned
QA/governance tooling. Production code paths require a recorded scope
amendment.

## 7. Track: Notebook Dependency Analysis

### 7.1 Track Scope

- Owner: manager
- In scope:
  - The `scistudio.explore` package and its place in the architecture layer test.
  - Per-cell static facts from `symtable` and `ast`: assigned names, read names,
    output declarations, input declarations, block calls (FR-005 to FR-013).
  - Magic and shell stripping, opaque cell magics, star imports, unparseable
    cells, and the flag each produces (FR-036).
  - The dependency graph over enabled cells, version nodes, edge origins, and
    the four queries (FR-014 to FR-023).
  - The fingerprint, the namespace comparison, and the observation record
    (FR-024 to FR-030).
  - The notebook cell metadata codec keyed to the cell source hash
    (FR-031 to FR-034).
  - The import constraint of FR-035 asserted by the layer test.
- Out of scope:
  - The kernel, the execution queue, the marks as the session applies them, and
    the packaged block's run. Spec 3 owns those.
  - The dependency-graph view and the enable/disable control. The
    explore-frontend spec owns those.
- Required docs:
  - N/A. `docs/specs/adr-054-notebook-dependency-analysis.md` is the governing
    document and already landed in PR #2228. This work implements it and adds
    no new user-facing or developer-facing surface that a guide describes.
- Required tests:
  - `tests/explore/test_dependency_analysis.py`
  - `tests/explore/test_fingerprint.py`
  - `tests/explore/test_analysis_differential.py`
  - `tests/explore/fixtures/**`
  - `tests/architecture/test_layer_deps.py`

### 7.2 Dispatch

- [x] Prompt file created or dispatch prompt recorded.
- [x] Correct prompt template selected.
- [x] Audit mode recorded when persona is `audit_reviewer`.
- [x] Agent branch/worktree assigned.
- [x] Write set and out-of-scope paths included in prompt.
- [x] TODO rule included in prompt.
- [x] Required checks included in prompt.

### 7.3 Implementation

- [x] `S2-B1` package, layer rule, static facts, graph, queries -> merged into the
      track branch. `tests/explore/test_dependency_analysis.py` 162 passed,
      `tests/architecture/test_layer_deps.py` 10 passed, and the wider
      `tests/architecture tests/adr052_contract tests/stability tests/docs tests/explore`
      run 870 passed / 8 skipped. The agent ran 23 mutations against its own
      implementation and all 23 were caught. Gate ledger:
      `.workflow/records/2231-feat-2231-dep-analysis-graph.json`, scope amended to
      include `tests/architecture/test_placement.py`, whose
      `test_no_py_files_outside_known_packages` enumerates top-level packages
      independently of `test_layer_deps.py`.
- [x] `S2-B2` fingerprint with bound and fallback -> merged into the track branch.
      `tests/explore/test_fingerprint.py` 67 passed, 100% statement coverage of
      `src/scistudio/explore/fingerprint.py`, measured worst case 10.4 ms against the
      declared 250 ms bound. Benchmarking found and fixed a real defect: leaf handlers
      copied a full megabyte per element before the byte ceiling truncated it.
      Gate ledger: `.workflow/records/2231-feat-2231-fingerprint.json`.
- [ ] `S2-C1` observation, codec, stability markers -> artifact pending
- [ ] `S2-D1` differential harness, fixtures, adversarial tests -> artifact pending
- [x] docs -> N/A, rationale recorded in §7.1.

### 7.4 Audit

- [ ] Audit agent assigned, or manager audit completed.
- [ ] Audit report file path assigned.
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
| Gate ledger check (local) | `PYTHONPATH=./src python -m scistudio.qa.governance.gate_record check --mode local --base origin/main --head HEAD` | `[ ]` | |
| Targeted tests | `PYTHONPATH=./src python -m pytest tests/explore tests/architecture/test_layer_deps.py -q` | `[ ]` | |
| Pre-push gate check | `PYTHONPATH=./src python -m scistudio.qa.governance.gate_record check --mode pre-push --base origin/main --head HEAD` | `[ ]` | |
| Gate ledger check (pre-PR) | `PYTHONPATH=./src python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `[ ]` | |
| Gate finalize (pre-PR) | `PYTHONPATH=./src python -m scistudio.qa.governance.gate_record finalize --commit SHA --pr-body-file .workflow/local/pr-body.md --closes "#2231"` | `[ ]` | |
| Wrapper preflight | `PYTHONPATH=./src python scripts/scistudio_pr_create.py --dry-run --title TITLE --body BODY` | `[ ]` | |

## 9. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| 2026-09-04 | manager | The earlier spec 2 dispatch left a checklist and three prompts with no implementation behind them. | Owner directed a full restart. Replaced the checklist and the prompt directory; retained and amended the gate ledger. | N/A |

## 10. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux
      evidence when needed, commit, and PR evidence.
- [ ] PR closes every issue fixed by the dispatch.
- [ ] CI passed.
- [ ] Checklist final state matches PR and gate record.
