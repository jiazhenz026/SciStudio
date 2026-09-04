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
- Gate record: `.workflow/records/2231-adr-054-spec2-restart.json`
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
earlier checklist and prompt files are replaced by this dispatch.

The earlier **gate ledger was retained and amended** for most of this work, on
the reasoning that it was the append-only record for this branch and issue. That
was wrong, and the pre-PR check caught it: the ledger recorded
`runtime: kimi`, so forty commits of Claude-authored work carried a false
attribution, and `guard.persona_policy` refused it because `kimi` maps to no
ADR-042 runtime config root. `gate_record` cannot correct a runtime — `init`
sets it only when the file does not exist and `amend` has no `--runtime` — and
hand-editing committed gate evidence is forbidden. The ledger was therefore
replaced with `.workflow/records/2231-adr-054-spec2-restart.json`, carrying the
correct runtime and the full scope, docs, and test plan. The tooling gap is
#2245.

What is lost in the replacement is the amendment event log. The narrative it
carried is in §9 below, which is the human-readable record of the same
decisions and was written as they were made.

## 2. Scope

- In scope:
  - `src/scistudio/explore/__init__.py`
  - `src/scistudio/explore/dependency_analysis.py`
  - `src/scistudio/explore/fingerprint.py`
  - `tests/explore/**`
  - `tests/architecture/test_layer_deps.py`
  - `docs/planning/adr-054-spec2-dependency-analysis-checklist.md`
  - `docs/planning/adr-054-spec2-dispatch-prompts/**`
  - `tests/architecture/test_placement.py` — its `known_packages` set enumerates
    top-level packages independently of the layer test and fails for whichever
    branch first creates the subsystem.
  - `docs/adr/ADR-054.md` — front matter and the one §11 sentence the front-matter
    change makes false. Authorised by §11 itself: "the surfaces in
    `planned_governs` become governed as they land." Nothing else in that file.
  - `docs/specs/adr-054-notebook-dependency-analysis.md` — front matter, plus the
    FR-003, FR-011, FR-035, and SC-011 corrections the adversarial pass and the
    two audits forced. See the drift log.
  - `docs/audit/**` (audit reports only)
  - `.workflow/records/2231-*.json`
- Out of scope:
  - Everything the explore-session spec owns: the kernel, the queue, the marks
    as the session applies them, packaging, lineage, the API.
  - Every frontend path.
  - `docs/specs/adr-054-explore-session.md` and every other ADR-054 spec — spec 3
    migrates its own front matter on its own branch.
  - `docs/architecture/**` — owner-controlled.
  - The **behaviour** of FR-015's unresolved-read exception. Both audits found it
    unauthorised and its justifying comment false; the comment is corrected here
    and the rule is left alone, because changing it either way needs the
    within-cell statement order FR-001 forbids the analysis from modelling.
    Owner decision, tracked as #2243.
- Scope corrections: this block originally declared `docs/specs/adr-054-*.md`
  out of scope as "approved input, not work product". Three findings forced the
  spec itself to change, each recorded in §9 with its gate-record amendment. The
  with-context audit (F-04) found the block still saying the opposite of what the
  dispatch had authorised, which made the PR's own scope statement false. It is
  corrected above rather than quietly.
- Protected paths:
  - None. Spec 2 adds a new subsystem and touches two architecture tests.
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
      `.workflow/records/2231-adr-054-spec2-restart.json`.
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
| `S2-B1` | `implementer` | `N/A` | `docs/planning/adr-054-spec2-dispatch-prompts/s2-b1-graph.md` | T-001 to T-006: the package, the layer rule, per-cell static facts, flags, declarations, the graph, the four queries | `feat/2231-dep-analysis-graph` | `.worktrees/s2-b1-graph` | `src/scistudio/explore/__init__.py`, `src/scistudio/explore/dependency_analysis.py`, `tests/explore/test_dependency_analysis.py`, `tests/architecture/test_layer_deps.py`, `tests/architecture/test_placement.py` (amended) | `src/scistudio/explore/fingerprint.py`, `tests/explore/test_fingerprint.py`, everything outside `src/scistudio/explore/` and `tests/explore/` | `#2231` | `[x]` |
| `S2-B2` | `implementer` | `N/A` | `docs/planning/adr-054-spec2-dispatch-prompts/s2-b2-fingerprint.md` | T-007: the fingerprint, the size bound, the unobservable fallback | `feat/2231-fingerprint` | `.worktrees/s2-b2-fingerprint` | `src/scistudio/explore/fingerprint.py`, `tests/explore/test_fingerprint.py` | `src/scistudio/explore/__init__.py`, `src/scistudio/explore/dependency_analysis.py`, `tests/architecture/**` | `#2231` | `[x]` |
| `S2-C1` | `implementer` | `N/A` | `docs/planning/adr-054-spec2-dispatch-prompts/s2-c1-observation.md` | T-008, T-009, T-011: the namespace comparison, the observation record with source-hash invalidation, the metadata codec, stability markers | `feat/2231-observation-codec` | `.worktrees/s2-c1-observation` | `src/scistudio/explore/__init__.py`, `src/scistudio/explore/dependency_analysis.py`, `src/scistudio/explore/fingerprint.py`, `tests/explore/test_dependency_analysis.py`, `tests/explore/test_fingerprint.py` | `tests/architecture/**`, everything outside `src/scistudio/explore/` and `tests/explore/` | `#2231` | `[x]` |
| `S2-D1` | `test_engineer` | `N/A` | `docs/planning/adr-054-spec2-dispatch-prompts/s2-d1-adversarial.md` | T-010 and adversarial coverage: the differential harness, the fixtures, and tests that try to break the analysis rather than confirm it | `test/2231-adversarial` | `.worktrees/s2-d1-adversarial` | `tests/explore/**` | Every production path. Report defects, do not fix them. | `#2231` | `[x]` |
| `S2-E1` | `audit_reviewer` | `no-context` | `docs/planning/adr-054-spec2-dispatch-prompts/s2-e1-audit-no-context.md` | Independent audit of the explore analysis subsystem against the repository's own documents | `audit/2231-no-context` | `.worktrees/s2-e1-audit-nc` | `docs/audit/2026-09-04-explore-dependency-analysis-no-context.md` | Every implementation and test path. Read-only. | `#2231` | `[x]` |
| `S2-E2` | `audit_reviewer` | `with-context` | `docs/planning/adr-054-spec2-dispatch-prompts/s2-e2-audit-with-context.md` | Audit of the delivered spec 2 work against the spec, the issue, and this checklist | `audit/2231-with-context` | `.worktrees/s2-e2-audit-wc` | `docs/audit/2026-09-04-adr-054-spec2-with-context.md` | Every implementation and test path. Read-only. | `#2231` | `[x]` |
| `S2-F2` | `implementer` | `N/A` | `docs/planning/adr-054-spec2-dispatch-prompts/s2-f1-fix.md` | Second fix round: the union of both audits' findings — the walrus-in-a-comprehension defect, the mapping and set sampling, four surviving mutations, the tokeniser error-recovery test, the allowlist test's depth, the timing ceilings, and ten stale finding docstrings | `fix/2231-audit-round-two` | `.worktrees/s2-f2-fix2` | `src/scistudio/explore/**`, `tests/explore/**`, `tests/architecture/**` | `docs/**`; the behaviour of FR-015's exception (#2243) | `#2231` | `[~]` |
| `S2-G1` | `adr_author` | `N/A` | `docs/planning/adr-054-spec2-dispatch-prompts/s2-g1-governs-migration.md` | Move the ADR-054 and spec-2 `planned_governs` entries that now resolve into `governs`, and correct the one §11 sentence the move makes false | `docs/2231-governs-migration` | `.worktrees/s2-g1-governs` | `docs/adr/ADR-054.md` (front matter and one sentence), `docs/specs/adr-054-notebook-dependency-analysis.md` (front matter) | Every path under `src/` and `tests/`; every other ADR-054 spec; `docs/architecture/**` | `#2231` | `[x]` |
| `S2-F1` | `implementer` | `N/A` | `docs/planning/adr-054-spec2-dispatch-prompts/s2-f1-fix.md` | Fix the P1 and P2 findings the audits and the adversarial test engineer produce | `fix/2231-audit-findings` | `.worktrees/s2-f1-fix` | `src/scistudio/explore/**`, `tests/explore/**` | Everything else | `#2231` | `[x]` |

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
- [x] `S2-C1` observation, codec, stability markers -> delivered on
      `feat/2231-observation-codec`. `tests/explore` 311 passed, of which 82 are
      new (`test_dependency_analysis.py` 162 -> 227, `test_fingerprint.py`
      67 -> 84); `scistudio.explore.fingerprint` 100% and
      `scistudio.explore.dependency_analysis` 99% statement coverage (the one
      uncovered line, the `MatchMapping` rest binding, predates this branch).
      `tests/architecture/test_layer_deps.py`, `test_placement.py`,
      `tests/api/test_public_surface.py`, and `tests/api/test_stability_decorators.py`
      456 passed together; `tests/adr052_contract tests/stability tests/docs`
      202 passed / 7 skipped, so A-009 holds and the frozen surface inventory is
      unchanged. Two integration facts the manager should carry forward: the
      package facade does **not** re-export the `fingerprint` function, because
      the name would shadow the submodule of the same name and break
      `from scistudio.explore import fingerprint`; and
      `dependency_analysis` now imports `ObservedChange` from `fingerprint` for
      the codec, which the FR-035 allowlist already permits
      (`EXPLORE_ALLOWED_SCISTUDIO_IMPORTS` includes `scistudio.explore`).
      Gate ledger: `.workflow/records/2231-feat-2231-observation-codec.json`.
- [x] `S2-D1` differential harness, fixtures, adversarial tests -> delivered on
      `test/2231-adversarial`. `tests/explore` **8 failed, 399 passed**; 96 tests are
      new (`test_analysis_differential.py` 32, `test_adversarial_analysis.py` 64) and
      ten fixture notebooks landed under `tests/explore/fixtures/`. The eight failures
      are the deliverable, not a regression: each is a defect with a named test, and
      no pre-existing test changed. **Two are P1 and both are proven by execution, not
      by assertion** — the backward slice of `global_counter.ipynb` and of
      `wrapped_operator.ipynb` raises `NameError` when it runs, which is the SC-003
      failure User Story 2 exists to prevent, and in both cases FR-021's unresolved-read
      list is empty so packaging would have accepted the notebook. A third P1 is in the
      fingerprint: `_stride_indices` truncates its index list after the stride is
      chosen, so a list of 513 to 2047 elements has an unsampled middle region and a
      write into it is not observed. Fifty-one mutations were run against the delivered
      modules with only the implementers' tests in place: 42 killed, 9 survived, of
      which 5 were genuine coverage holes (now closed) and 4 equivalent mutants (now
      documented). SC-010 measured on this runner: 500 cells analyse in 49 ms and build
      in 11 ms, 60 ms total against the 500 ms bound; 1000 cells cost 139 ms, so the
      cost is linear. `full_audit` reports 6 errors, all of the expected
      `planned-*-is-resolved` shape on the spec front matter — `ObservedChange` plus the
      two entries this agent's files made resolve; `test_adversarial_analysis.py` is in
      neither `governs` nor `planned_governs` and the second migration pass should add
      it. `tests/architecture` and `tests/api/test_public_surface.py` 540 passed / 1
      skipped. Gate ledger: `.workflow/records/2231-test-2231-adversarial.json`.
- [ ] `S2-G1` the `planned_governs` migration -> branch `docs/2231-governs-migration`
      pushed, awaiting integration. `full_audit` went from `fail` (13 error, 88 info)
      to `pass` (0 error, 88 info): the 13 `planned-*-is-resolved` errors on
      `docs/adr/ADR-054.md` and `docs/specs/adr-054-notebook-dependency-analysis.md`
      are cleared, and the 88 informational findings from other documents are
      unchanged. `phase: planning` deliberately left as is — `phase: implementation`
      makes `doc_drift` demand an *active* related spec, and spec 2 is `Draft`, so
      the change trades 13 errors for one. Second pass, after `S2-C1` and `S2-D1`
      merged: `full_audit` `fail` (3 error, 85 info) to `pass` (0 error, 84 info).
      `ObservedChange`, `tests/explore/test_analysis_differential.py`, and
      `tests/explore/fixtures/**` moved into `governs`, and
      `tests/explore/test_adversarial_analysis.py`, which was in neither list, was
      added. `AnalysisRecord` was dropped rather than moved, with the reason left
      as a comment where it stood: Key Entities defines it as the JSON shape in
      cell metadata and FR-033 requires unrecognised keys to survive, which no
      closed Python type expresses. The spec's `planned_governs` is now empty.
      The same pass narrowed FR-011 from a textual first-character test to a
      lexical one, which is the `S2-D1` P1 finding
      `test_sc003_wrapped_operator_slice_reproduces_the_notebook`. Third pass, on
      both audit reports: FR-003, FR-035 and SC-011 now name `xxhash` alongside
      numpy and pandas, and SC-011 requires a measurement that collects imports at
      any depth, since the one it named could not see a lazy import at all. The
      spec's `tests:` list gained `test_adversarial_analysis.py` and
      `test_placement.py`, ADR-054's gained the same two, `governs.files` gained
      `tests/explore/__init__.py`, and §4.2 gained the three rows it was missing.
      `full_audit` was `pass` (0 error, 84 info) before and after — this pass fixes
      contradictions that no audit measures, which is the audits' own point. Gate
      ledger: `.workflow/records/2231-docs-2231-governs-migration.json`.
- [x] docs -> N/A, rationale recorded in §7.1.

### 7.4 Audit

- [x] Audit agent assigned, or manager audit completed.
      Both modes dispatched: `S2-E1` no-context and `S2-E2` with-context. Neither
      was redundant — see §9.
- [x] Audit report file path assigned.
- [x] Audit report committed.
      `docs/audit/2026-09-04-explore-dependency-analysis-no-context.md` (commit
      `2eaecd322`) and `docs/audit/2026-09-04-adr-054-spec2-with-context.md`
      (commit `ffafdba0a`).
- [x] Audit report merged into final PR evidence path.
      Merged into `track/adr-054-spec2-dependency-analysis` at `7d836ad29`.
- [x] Findings recorded.
      No-context: 0 P1, 6 P2, 11 P3, from 57 behavioural mutations (47 killed,
      10 survived) and a 960-permutation fuzz over the tokeniser path.
      With-context: 0 P1, 7 P2, 4 P3, from an FR-by-FR and SC-by-SC walk. Both
      recommend pass-with-fixes.
- [x] P1 findings fixed before integration.
      Neither audit found a P1. The three P1s in this delivery came from the
      adversarial test engineer and were fixed by `S2-F1`.
- [~] P2/P3 findings fixed or tracked with owner-approved rationale.
      `S2-F2` is closing the union of both reports. The one deliberately not
      fixed is FR-015's exception, tracked as #2243 with both options costed,
      because deciding it either way needs statement ordering FR-001 forbids.
      #2242 tracks the latent `governs.contracts` coupling.

### 7.5 Integration

- [x] Agent output reviewed by manager.
      Every branch reviewed before merge; each integration commit states what
      the agent found and what it declined to do. Two agents declined a manager
      instruction and were right both times — recorded in §9.
- [x] Scope compliance verified.
      Three scope expansions were requested by agents, granted by gate-record
      amendment before the edit, and are listed in §2 and §9. No agent edited
      outside its write set.
- [x] Conflicts resolved intentionally.
      Checklist conflicts were resolved by taking the completed row from
      whichever side recorded it. The one substantive conflict — spec 2's FR-035
      allowlist applied to the whole package versus spec 3's runtime needing
      `core` — was resolved on spec 3's branch by scoping the rule to its stated
      subject, not by relaxing it.
- [~] Track merged or integrated.
      Pending `S2-F2` and the final pre-PR gate check.

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
| 2026-09-04 | `S2-D1` | The adversarial pass found three P1s, two of which would have shipped: a `global` augmented assignment inside a function was never a module read, so the backward slice dropped the initialising cell, raised `NameError`, and reported an **empty** unresolved list; and FR-011 as written stripped the continuation line a formatter emits for a wrapped operator, so the cell parsed and a read vanished with no flag. | The first was a product defect, fixed by `S2-F1`. The second was a **spec** defect: `S2-G1` narrowed FR-011 to a lexical rule and `S2-F1` implemented it. | N/A |
| 2026-09-04 | `S2-G1` | Its own first draft of the narrowed FR-011 reproduced the defect through a different door: `tokenize` emits `NEWLINE`, which terminates a logical line, and `NL`, which does not and is what appears inside an open bracket. Treating `NL` as a terminator makes a continuation line look like the start of one. | Caught by prototyping the rule rather than reasoning about it. The published rule names both token kinds and states that collapsing them restores the bug. | N/A |
| 2026-09-04 | manager | I instructed `S2-F1` to delete `test_augmented_assignment_inside_a_nested_scope_is_not_a_module_read`, relaying the test engineer's claim that it pinned behaviour the spec contradicts. It does not — its body has no `global` declaration, so the name is a function local FR-006 never reaches. | The agent declined, kept the assertion, rewrote its genuinely-wrong docstring, and added four contrast cases. My instruction was wrong and I had not verified the claim before relaying it. | N/A |
| 2026-09-04 | `S2-E1`, `S2-E2` | Both audits independently found that `xxhash` is directed by §4.1 and forbidden by FR-003, FR-035 and SC-011, and that SC-011's named measurement cannot see lazy imports **by construction** — so the criterion had no test that could fail. An earlier drift-log row had closed this same conflict as "No document change needed". | `S2-G1` named the exception in FR-003 and fenced it to the fingerprint, and rewrote SC-011 to require imports collected at any depth, stating why a module-level reader does not measure it. `S2-F2` strengthens the test. The earlier row is superseded. | N/A |
| 2026-09-04 | `S2-E2` | Found a defect neither the 51-mutation nor the 57-mutation campaign caught: a walrus target inside a comprehension is not recorded as assigned, so the reader is never marked stale and packaging refuses a working notebook. PEP 709 inlines those comprehensions and `symtable` reports the target as neither assigned nor local. | Assigned to `S2-F2`. Also worth noting the shape: the with-context audit found what the mutation campaigns could not, because no mutation of existing code produces a case the code never handled. | N/A |
| 2026-09-04 | manager | The pre-PR check refused the branch on `guard.persona_policy`: the manager ledger, inherited from the abandoned dispatch, recorded `runtime: kimi` for work Claude authored, and `kimi` maps to no ADR-042 runtime config root. | Replaced the ledger rather than hand-editing committed gate evidence, which the rules forbid. Every agent ledger already carried a valid Claude runtime; only the inherited manager one was wrong. Retaining it at restart was my call and this is its cost. | #2245 |
| 2026-09-04 | `S2-E2` | F-04: §2 of this checklist still declared `docs/specs/adr-054-*.md` out of scope while the spec was being materially rewritten under §6 and drift-log authorisation, making the PR's own scope statement false. | §2 corrected above, with the correction itself recorded rather than made silently. | N/A |
| 2026-09-04 | manager | The earlier spec 2 dispatch left a checklist and three prompts with no implementation behind them. | Owner directed a full restart. Replaced the checklist and the prompt directory; retained and amended the gate ledger. | N/A |
| 2026-09-04 | `S2-B1`, `S2-B2`, `S3-A1` | Three agents independently hit the same blocker and each correctly refused to widen its own scope: creating `src/scistudio/explore/` makes the ADR-054 and spec `planned_governs` entries resolve, and `full_audit` requires a resolved entry to move into `governs`. No implementer's write set covers governance front matter, and the move cannot be pre-applied on a branch without the package. | Manager added agent `S2-G1` (`adr_author`) to make the move once, as its own reviewable change, and amended the ledger to include the two documents. | A second short pass moves `tests/explore/test_analysis_differential.py` and `tests/explore/fixtures/**` once `S2-D1` creates them. |
| 2026-09-04 | `S2-B1` | `tests/architecture/test_placement.py::test_no_py_files_outside_known_packages` enumerates top-level packages independently of the layer test and fails for whichever branch first creates the subsystem. | Scope amended; `S2-B1` added the one line. | N/A |
| 2026-09-04 | `S2-G1` | ADR-054's `governs.contracts` is `[]` while spec 2's names three. `doc_drift`'s `missing-adr-governance` rule is silent only because it counts a spec active at status `Planned` or `Implemented`, and every ADR-054 spec is `Draft`. | Left the statuses at `Draft`, which matches `docs/specs/adr-053-personal-tool-library.md`'s precedent, and opened a follow-up so the coupling is visible in the repository rather than in one agent's report. | #2242 |
| 2026-09-04 | `S2-G1` | The spec's `planned_governs` names contracts `AnalysisRecord` and `ObservedChange`, which no delivered module defines. | Sequencing, not drift: both are `S2-C1`'s (the observation record and the metadata codec). A second migration pass moves them, and `S2-D1`'s differential test and fixtures, once those land. | N/A |
| 2026-09-04 | `S2-B2` | Raised that SC-011 names only numpy and pandas as permitted lazy third-party imports while §4.1 directs arrays through `xxhash`. | Resolved by the shape of `S2-B1`'s allowlist test, which reads module-level imports only, so a lazy `xxhash` inside the fingerprint is permitted on the same terms as numpy and pandas. No document change needed. | N/A |
| 2026-09-04 | `S2-D1`, `S2-G1` | FR-011 as written ("a line whose first non-blank character is `%` or `!` MUST be removed") is too broad. A formatter-wrapped `    % count` is such a line, so it was stripped, the cell still parsed as `ratio = (total)`, no flag was raised, and `count` vanished from the read set; the slice then ran the original source and raised `NameError`. `!=` and a magic-looking line inside a triple-quoted string share the root cause. | The implementation obeyed FR-011 exactly, so the defect is the spec's. `S2-G1` narrowed FR-011 to identify a magic line lexically — a `%` or `!` token that is the first token of a logical line — rather than by the first character of a physical line. The rule was prototyped against both acceptance tests and eleven other shapes before it was written. | `S2-F1` implements it. `tests/explore/test_adversarial_analysis.py::test_fr011_a_magic_line_inside_a_string_literal_is_stripped_too` asserts the old behaviour in its P3 half and must be updated with the fix. |
| 2026-09-04 | `S2-G1` | Superseding the `AnalysisRecord` row above: `ObservedChange` was sequencing and has landed, but `AnalysisRecord` is not a Python type at all. Key Entities defines it as the JSON shape stored in cell metadata and FR-033 requires unrecognised keys to survive a rewrite. | Dropped from `planned_governs.contracts` on the manager's direction rather than satisfied by a type invented to fill a manifest line, with the reason kept as a front-matter comment where the entry stood. `S2-C1` was right to refuse to invent it. | N/A |
| 2026-09-04 | `S2-E1`, `S2-E2`, `S2-G1` | Reopening the `S2-B2` row above, which closed this as "No document change needed". Both audits reached the same finding independently (no-context P2-1, with-context F-05): FR-003, FR-035 and SC-011 permit no third-party import but numpy and pandas, while §4.1 directs the fingerprint through `xxhash` and the code follows §4.1. The earlier resolution turned on the allowlist test not seeing lazy imports — but that is the defect, not the answer: a criterion nothing can fail is not a criterion, and a lazy `import requests` would have passed too. | `S2-G1` amended FR-003, FR-035 and SC-011 to name `xxhash` on the same terms as numpy and pandas, and rewrote SC-011 to require its measurement to collect imports at any depth. §4.1's direction is left alone; its reasoning is sound and the boundary rule was the half that was wrong. | `S2-F1` is strengthening `test_explore_imports_are_allowlisted` to match. Manager reconciles at integration if the landed test and the written criterion diverge. |
| 2026-09-04 | `S2-G1` | Checked, on the manager's instruction, whether the false FR-015 justification the audits found in `build_graph`'s comment and a test docstring ("every `import pandas as pd` cell would report `pd` unresolved") also appears in the spec. | It does not. The spec carries no `import pandas as pd` example anywhere, and §4.1's description of `symtable` already draws the distinction correctly — "every name that is assigned or imported and every name that is referenced". No spec edit; the correction is `S2-F1`'s in the code alone. FR-015's rule left untouched per #2243. | #2243 |

## 10. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux
      evidence when needed, commit, and PR evidence.
- [ ] PR closes every issue fixed by the dispatch.
- [ ] CI passed.
- [ ] Checklist final state matches PR and gate record.
