---
title: "Learning Center Levels Agent Dispatch Checklist"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 53
related_specs:
  - adr-053-learning-center
language_source: en
---

# Learning Center Levels Agent Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: Implement all remaining Learning Center levels (core
  tutorials 2-6) and their prerequisite work; Chrome-test each level after
  completion; deliver one final PR; then launch backend + desktop frontend
  for owner level-by-level acceptance.
- Task kind: `manager`
- Manager persona: `manager`
- Issues: prerequisites #2061 #2062 #2063 #2066 #2075 #2086; in-flight
  fold-ins #2079 #2080; level authoring #2081 (L2) #2082 (L3) #2083 (L4)
  #2084 (L5) #2085 (L6). Design question #2067 surfaced to owner, not closed
  by this dispatch.
- Gate record: `.workflow/records/track-learning-center-levels-learning-center-levels.json`
- Branch/worktree plan: manager branch `track/learning-center-levels` in
  `C:/Users/jiazh/workspace/SciStudio-wt-lc-mgr`; agent branches
  `feat/<issue>-<slug>` or `fix/<issue>-<slug>`, each in a dedicated
  `C:/Users/jiazh/workspace/SciStudio-wt-lc<agent>` worktree.
- Protected branch: `main`
- Umbrella branch: `track/learning-center-levels`
- Umbrella PR: `#2087` (opened 2026-08-21)
- Umbrella PR title: `[DO NOT MERGE] track: Learning Center levels 2-6 and prerequisites`
- Final PR target: `main` (the umbrella PR is retitled/promoted or a final PR
  is cut from the umbrella branch once integration completes; final PR closes
  every issue listed above except #2067)
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context:
    `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context:
    `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`
- Dispatch prompts file: `docs/planning/learning-center-levels-dispatch-prompts.md`

## 2. Scope

- In scope:
  - `src/scistudio/tutorials/**` (runtime vocabulary/driver/session additions;
    new core tutorial directories `core/<id>/`)
  - `src/scistudio/previewers/**` only as far as #2086 requires (scoped-library
    previewer tier scan)
  - `docs/specs/adr-053-learning-center.md` revisions required by #2061 #2062
    #2063 #2066
  - `src/scistudio/api/routes/tutorials.py` and tutorial-facing API surface
  - Frontend tutorial surfaces: step view, replay terminal, reading/pages
    renderer, provider-intro modal, Learning Center window
  - `tests/tutorials/**`, `tests/api/test_tutorial_*.py`, frontend tutorial
    tests (fixes for #2075 and new coverage)
  - `docs/planning/learning-center-levels-checklist.md`,
    `docs/planning/learning-center-levels-dispatch-prompts.md`,
    `docs/planning/learning-center-scenarios.md` (status annotations only)
  - `docs/ai-developer/e2e/2026-08-*-lc-level-*.md` scenario files (manager-owned
    e2e evidence; governance_touch declared in the manager gate ledger)
  - `CHANGELOG.md`, user docs pages for the Learning Center where behaviour
    changes
  - #2080 fold-in surface: public tutorials API root docs/build files as staged
    on `feat/2080-tutorials-public-root`
- Out of scope:
  - `docs/architecture/ARCHITECTURE.md` (owner-controlled; propose text only)
  - `docs/ai-developer/**` other than the e2e scenario files above
  - Engine/scheduler internals, personal tool library production surfaces
    beyond #2086, work-import internals (only the unlock hand-off is touched)
  - Package-authored tutorials, #2067's FR-020a set change (owner decision)
- Protected paths:
  - `docs/ai-developer/**` (governance surface), protected core paths per
    repository guard config
- Deferred work:
  - Any level-scoped deferral must land as `TODO(#2081..#2086)` with the issue
    cited, or a new follow-up issue. N/A at dispatch.

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

- [x] Dedicated manager branch and worktree created. ->
      `track/learning-center-levels`, `C:/Users/jiazh/workspace/SciStudio-wt-lc-mgr`
- [x] Existing issues linked; new issues created only where none existed. ->
      #2081-#2085 (levels, none existed), #2086 (scoped-library previewer tier,
      none existed); prerequisites reuse #2061 #2062 #2063 #2066 #2075.
- [x] Gate record started. ->
      `.workflow/records/track-learning-center-levels-learning-center-levels.json`
- [x] Scope include/exclude recorded in the gate record. -> init + amend events
- [x] Umbrella branch created. -> `track/learning-center-levels`
- [x] Umbrella PR opened. -> #2087
- [x] Umbrella PR title includes `[DO NOT MERGE]`. -> see §1
- [x] Protected branch and umbrella PR number recorded in this checklist. -> §1
- [x] No `pip install -e .` environment pollution found. -> not used by this
      dispatch; agents instructed likewise
- [x] Dispatch checklist copied from the template and committed. -> this file
- [x] Dispatch prompts created from the correct prompt template and linked
      below. -> `docs/planning/learning-center-levels-dispatch-prompts.md` (wave 1: P1/P3/L5)
- [x] Sentrux baseline recorded, or N/A reason recorded. -> Sentrux MCP not
      connected in this session; CLI present (`sentrux.exe`); Sentrux guard
      evidence is recorded by `gate_record check` per ledger workflow.

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `N/A`
- Owner authorization source: `N/A`
- Reason: `N/A`

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scistudio.qa.governance.gate_record check --mode pre-commit` | `N/A` | `[ ]` | `` |
| Commit message | `python -m scistudio.qa.governance.gate_record check --mode commit-msg` | `N/A` | `[ ]` | `` |
| Pre-push | `python -m scistudio.qa.governance.gate_record check --mode pre-push` | `N/A` | `[ ]` | `` |
| Pre-PR reconcile | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `N/A` | `[ ]` | `` |

## 5.1 Docs Impact Check

- Wrapper/hook/gate-record/receipt/CI/runtime behavior changed: `no`
- AI docs checked: `docs/ai-developer/rules.md`,
  `docs/ai-developer/specific_rules/gated-workflow.md`,
  `docs/ai-developer/specific_rules/agent-dispatch.md`,
  `docs/ai-developer/templates/*dispatch*.md`
- Updated docs or N/A rationale: N/A — this dispatch changes tutorial runtime
  and content, not gate/wrapper/CI behaviour. Revisit if any track touches
  hooks or gate tooling.

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| `P0` | `implementer` | `N/A` | prompts file §P0 | Finish #2080 public tutorials root (WIP staged) | `feat/2080-tutorials-public-root` | `C:/Users/jiazh/workspace/SciStudio-wt-2080` | staged file set of that branch | everything else | #2080 | `[ ]` |
| `P1` | `implementer` | `N/A` | prompts file §P1 | Vocabulary + manifest + spec revision batch (#2061 #2062 #2063 #2066 #2088 #2089) | `feat/2061-tutorial-step-vocabulary` | `C:/Users/jiazh/workspace/SciStudio-wt-lcP1` | tutorials runtime, schema, spec §§, step-view frontend, tests | core tutorial dirs, previewer registry | #2061 #2062 #2063 #2066 #2088 #2089 | `[~]` implementation complete: trigger + trigger endpoint, block_type selectors, ui_event targets, workflows/ asset dir + canvas settle, since_step_entry, backend plot_rendered, requires.tutorials, replay continue_tab, pages field, session steps outline (manager addendum), vocabulary odds; spec FRs revised in step with each commit; welcome yaml untouched; gate reconciliation + pre/post-PR finalize passed; PR #2104 |
| `P2` | `implementer` | `N/A` | prompts file §P2 | Scoped-library previewer tier (#2086) | `feat/2086-tutorial-library-previewer-tier` | `C:/Users/jiazh/workspace/SciStudio-wt-lcP2` | projects.py, conditions.py (unsatisfiable set), previewer registry scan, tests | manifest schema, spec | #2086 | `[ ]` |
| `P3` | `test_engineer` | `N/A` | prompts file §P3 | Windows-failing LC tests (#2075) | `fix/2075-lc-windows-tests` | `C:/Users/jiazh/workspace/SciStudio-wt-lcP3` | the 8 named test files/fixtures only | production code | #2075 / PR #2098 | `[x]` merged into track |
| `L2` | `implementer` | `N/A` | prompts file §L2 | Core tutorial 2 — What is a type | `feat/2081-core-tutorial-2` | `C:/Users/jiazh/workspace/SciStudio-wt-lcL2` | `src/scistudio/tutorials/core/<t2-id>/**`, its tests | runtime code, other tutorials | #2081 | `[ ]` |
| `L3` | `implementer` | `N/A` | prompts file §L3 | Core tutorial 3 — Multimodal + git branches | `feat/2082-core-tutorial-3` | `C:/Users/jiazh/workspace/SciStudio-wt-lcL3` | `src/scistudio/tutorials/core/<t3-id>/**`, its tests | runtime code, other tutorials | #2082 | `[ ]` |
| `L4` | `implementer` | `N/A` | prompts file §L4 | Core tutorial 4 — fake AI replay + import unlock | `feat/2083-core-tutorial-4` | `C:/Users/jiazh/workspace/SciStudio-wt-lcL4` | `src/scistudio/tutorials/core/<t4-id>/**`, unlock milestone config, provider-intro modal, tests | other tutorials, work-import internals | #2083 | `[~]` implementation complete: tutorial `what-ai-can-do` (14 steps; 9-reply continue_tab replay with per-segment bound writes; judged via block_registered, node/edge, run_failed/run_succeeded since_step_entry, ui_event node_selected, config_equals, plot_rendered, file_exists); DEFAULT_WORK_IMPORT_MILESTONE = what-ai-can-do (resolves TODO(#2057)); frontend replay-tab adoption (session.replay consumer, tutorial-replay tab source) + availability-driven provider intro ahead of the offer; tests: tests/tutorials/test_core_tutorial_what_ai_can_do.py (19) incl. full runtime walk, progress/conformance updates, 3 vitest files; live API e2e of all beats passed (real engine runs incl. the KeyError break/fix, plot render, canned AI block, unlock fired; Vite 127.0.0.1 proxy verified); commit 09338e623; PR pending |
| `L5` | `implementer` | `N/A` | prompts file §L5 | Core tutorial 5 — summary (reading) | `feat/2084-core-tutorial-5` | `C:/Users/jiazh/workspace/SciStudio-wt-lcL5` | `src/scistudio/tutorials/core/<t5-id>/**`, reading renderer if missing, tests | other tutorials | #2084 | `[~]` |
| `L6` | `implementer` | `N/A` | prompts file §L6 | Core tutorial 6 — start your own project | `feat/2085-core-tutorial-6` | `C:/Users/jiazh/workspace/SciStudio-wt-lcL6` | `src/scistudio/tutorials/core/<t6-id>/**`, its tests | other tutorials | #2085 | `[ ]` |
| `A1` | `audit_reviewer` | `with-context` | prompts file §A1 | Integration audit of the umbrella candidate | `audit/lc-levels-with-context` | `C:/Users/jiazh/workspace/SciStudio-wt-lcA1` | `docs/audit/2026-08-*-lc-levels-with-context.md` | production code | audit report | `[ ]` |
| `A2` | `audit_reviewer` | `no-context` | prompts file §A2 | Independent audit (repo-only) | `audit/lc-levels-no-context` | `C:/Users/jiazh/workspace/SciStudio-wt-lcA2` | `docs/audit/2026-08-*-lc-levels-no-context.md` | production code | audit report | `[ ]` |

Sequencing constraints (manager-enforced):

- P0, P1, P3 dispatch immediately in parallel; #2079 branch is folded into the
  umbrella by the manager (clean merge verified against `origin/main`).
- P2 dispatches after P1 merges into the umbrella (both touch
  `conditions.py`; manager sequences the shared file).
- L4, L5, L6 dispatch after P1 lands in the umbrella. L2 dispatches after P1+P2
  land. L3 dispatches after L2 lands (library bridge) and its e2e passes.
- Each level merge into the umbrella is followed by a manager-run Chrome e2e
  before dependent levels dispatch.
- A1/A2 dispatch after L2-L6 are integrated; audit fixes precede the final PR.

## 7. Track P0 — In-Flight Fold-Ins (#2079, #2080)

### 7.1 Track Scope

- Owner: manager (fold-in) + agent P0 (#2080 completion)
- In scope: merging `guided/2079-learning-center-auto-open` into the umbrella;
  completing the staged WIP on `feat/2080-tutorials-public-root`.
- Out of scope: new behaviour beyond the two issues.
- Required docs: #2080's staged docs set; #2079 N/A (behaviour fix documented
  in CHANGELOG by its own commits).
- Required tests: #2079 branch already carries its tests; #2080 per its
  acceptance criteria.

### 7.2 Dispatch

- [ ] P0 prompt recorded in prompts file.
- [ ] P0 agent assigned to `SciStudio-wt-2080`.

### 7.3 Implementation

- [ ] #2079 branch merged into umbrella -> merge commit
- [ ] #2080 completed and merged into umbrella -> PR/commit

## 8. Track P — Prerequisites (#2061 #2062 #2063 #2066 #2086 #2075)

### 8.1 Track Scope

- Owner: agents P1, P2, P3
- In scope: manifest/vocabulary/runtime/spec revisions; scoped-library
  previewer tier; Windows test repairs.
- Out of scope: tutorial content.
- Required docs: spec revisions land with P1; #2086 updates the spec's
  library section if it names the tier set.
- Required tests: every vocabulary term and runtime addition tested; #2075 is
  test-only by definition.

### 8.2 Dispatch

- [~] P1/P3 prompts recorded and dispatched 2026-08-21; P2 waits on P1 merge.
- [~] P1/P3 branches+worktrees created; P2 pending.

### 8.3 Implementation

- [ ] P1 merged into umbrella -> PR
- [ ] P2 merged into umbrella -> PR
- [ ] P3 merged into umbrella -> PR

## 9. Tracks L2-L6 — Level Authoring (#2081-#2085)

### 9.1 Track Scope

- Owner: agents L2-L6, one per level.
- In scope: one `src/scistudio/tutorials/core/<id>/` directory per level
  (manifest + assets), level-specific frontend surfaces named in the prompt,
  tests per level.
- Out of scope: runtime vocabulary changes (stop and report to manager — they
  belong to P-track follow-ups).
- Required docs: user-facing Learning Center docs updated once at integration;
  CHANGELOG entries per level.
- Required tests: manifest schema validation + judged-step coverage per level;
  session lifecycle test per new kind used.

### 9.2 Dispatch

- [~] L5 prompt recorded and dispatched 2026-08-21; L2/L3/L4/L6 pending their waves.

### 9.3 Implementation

- [ ] L2 merged -> PR; manager Chrome e2e -> scenario file verdict
- [ ] L3 merged -> PR; manager Chrome e2e -> scenario file verdict
- [ ] L4 merged -> PR; manager Chrome e2e -> scenario file verdict
- [ ] L5 merged -> PR; manager Chrome e2e -> scenario file verdict
- [ ] L6 merged -> PR; manager Chrome e2e -> scenario file verdict

## 10. Track A — Audits

- [ ] Audit mode recorded before dispatch: A1 `with-context`, A2 `no-context`.
- [ ] A1 report committed -> path
- [ ] A2 report committed -> path
- [ ] Findings recorded; P1 findings fixed before final PR.
- [ ] Audit reports merged into final PR evidence path.

## 11. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Gate ledger check (local) | `python -m scistudio.qa.governance.gate_record check --mode local --base origin/main --head HEAD` | `[ ]` | `` |
| Per-level Chrome e2e | Playwright-driven Chrome against live backend + Vite, scenario files under `docs/ai-developer/e2e/` | `[ ]` | `` |
| Full-path e2e (levels 1-6 in order) | same harness, one continuous session | `[ ]` | `` |
| Targeted tests | per-track test commands recorded in gate ledger | `[ ]` | `` |
| Gate ledger check (pre-PR) | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `[ ]` | `` |
| Gate finalize (pre-PR) | `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes ...` | `[ ]` | `` |
| Wrapper preflight | `python scripts/scistudio_pr_create.py --dry-run ...` | `[ ]` | `` |
| Owner acceptance run | backend + desktop frontend launched for level-by-level owner testing | `[ ]` | `` |

## 12. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| 2026-08-21 | manager | Dispatch facts corrected by L5's code audit: palette built-ins are FIVE (SplitBlock excluded in registry/_scan.py:134-137, alongside MergeBlock); previewer tier order is project > user > package > core (user tier landed with #2017/PR #2072); figure_size is R-only. | Later level prompts use the corrected facts; L5 content already follows the code. | scenarios doc annotation at integration |
| 2026-08-21 | manager | L5 surfaced a contract gap: StepView carries only the current step's pages, so the reading grid cannot name all 8 cards up front. | Scope addendum sent to P1 (item 11): session response gains a read-only steps outline {index,id,title,say,pages} + current index; L5 consumes it at merge-back. | recorded in P1 ledger amend |

## 13. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux
      evidence when needed, commit, and PR evidence.
- [ ] PR closes every issue fixed by the dispatch.
- [ ] CI passed.
- [ ] Checklist final state matches PR and gate record.
