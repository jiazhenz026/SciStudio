---
title: "ADR-054 Guided Session: Embedded AI Guidance And Tutorial Migration"
status: Draft
owners: ["@jiazhenz026"]
related_adrs: [40, 48, 49, 51, 52, 54, 55]
related_specs: [adr-054-panels, adr-054-miniapp]
language_source: en
---

# Embedded AI Guidance Session Checklist

## 1. Change Summary

Owner-directed guided session tracked under #2295, with independent prompt
unification under #2383. Improve the guidance delivered to AI assistants inside
SciStudio so users can request useful scientific workflows without having to
debug framework contracts themselves. Complete ADR-054 Phase C and migrate all
bundled tutorials at the end of the session. This checklist records decisions
and remaining work; it does not claim implementation or validation completion.

The GUI skill is the first local implementation slice. The remaining sections
are the session backlog; record each concrete write scope in the gate ledger
before editing. Historical audit reports remain historical evidence.

## 2. Owner Decisions

- [x] Use task kind `guided` and persona `live_implementer`.
- [x] Investigate current startup instructions, provisioned references, skills,
  and the workflow-authoring path before rewriting them.
- [x] Unify common AI knowledge in project `AGENTS.md`; remove the Claude-only
  injected system-prompt route. A GPT-5.6 Sol agent owns #2383 and its own PR.
- [x] Keep detailed task skills and references available on demand.
- [x] Add `scistudio-use-gui` as a general guide to operating the SciStudio GUI.
  Keep panel verification and decisions about when to call the skill in the
  routing layer and authoring skills, not in this skill's scope or instructions.
- [x] Do not automatically invoke GUI checks for plots, workflows, or ordinary
  run debugging. Keep panel checks to the requested view and main interaction.
- [x] Migrate all tutorials in the final session scope, superseding the earlier
  #2295 exclusion of What Is A Type. Reconcile issue/spec wording before closure.
- [x] Preserve the ongoing Phase D work; use its final implementation as the
  contract baseline before completing MiniApp and panel documentation.

## 3. Common Instructions And Delivery

- [ ] **#2383, delegated:** remove Claude-only prompt injection; consolidate
  common guidance into `AGENTS.md`; preserve provider MCP and initial task
  prompts; verify safe managed-file refresh; submit PR and obtain passing CI.
- [ ] Review startup guidance for capability selection, context discovery,
  task completion, and when a question actually needs the user's input.
- [ ] Consolidate duplicated instructions across the base skill, project guide,
  task skills, references, and user guide; keep one maintained source per fact.
- [ ] Verify all providers can discover the same shipped skills and references.
- [ ] Assess core reference/user-guide refresh for existing projects. Existing
  files are currently preserved by ordinary provisioning; choose and record a
  delivery policy before implementing any refresh change (#2295).

## 4. GUI Skill And Panel Authoring

- [x] Author `src/scistudio/_skills/scistudio/scistudio-use-gui/SKILL.md` with
  current-instance access, workspace navigation, browser/computer-use controls,
  observation, and unavailable-tool handling. This is authored content, not
  evidence of a real browser test.
- [x] Register and verify delivery of the GUI skill to both provider trees,
  including adding it on reopen without overwriting customized skills.
- [ ] Add focused GUI-skill navigation to the unified `AGENTS.md` after #2383;
  avoid competing edits to that agent's template/base-skill work.
- [x] Add `scistudio-write-panel` with working preview and interactive examples,
  descriptor validation, local libraries/CDN limits, sample mode, and live checks.
- [x] Connect panel authoring to the GUI guide, referencing the Phase D MiniApp
  authoring contract. Keep plot/workflow/debug skills free of automatic browser work.
- [ ] **Phase D ownership (#2354):** MiniApp skill changes belong to Phase D.
  Reconcile its GUI-guide routing after final Phase D delivery; Phase C treats
  that skill as a read-only reference.
- [x] Refine `open_gui` documentation and its returned hint to point to available
  browser/computer-use tooling and the GUI skill, retaining its address-only role.
- [x] Reconcile the GUI guide with the committed Phase D tool inventory; do not teach
  a planned screenshot or navigation tool as already available.

## 5. Workflow And Analysis Guidance

- [ ] Review the path from research intent and real input data to suitable
  existing blocks, types, and package capabilities.
- [ ] Clarify when to use configuration, a custom block, an interactive panel,
  a plot, or a MiniApp; put these choices at the relevant entry points.
- [ ] Review `scistudio-build-workflow`, `scistudio-write-block`,
  `scistudio-inspect-data`, `scistudio-debug-run`, `scistudio-write-plot`,
  `scistudio-project-qa`, and the final `scistudio-write-miniapp` skill.
- [ ] Replace instructions that hand routine implementation errors or conflicting
  framework documentation back to the user with a bounded diagnosis/repair path;
  retain questions for material scientific choices and missing user information.
- [ ] Define completion around real outputs, appropriate data interpretation,
  accessible parameters, and clear next use, not only a valid YAML or running job.
- [ ] Check worked examples against installed contracts and runnable examples;
  do not invent block names, port names, constructors, or tool signatures.

## 6. References, User Guide, And Phase C Documentation

- [ ] Update agent reference `README.md`, `public-api.md`, `data-types.md`,
  `block-contract.md`, `workflow-schema.md`, `plot-contract.md`, and
  `package-discovery.md` where current contracts or routing require it.
- [ ] Make installed-package references discoverable when package types,
  constructors, or domain methods are needed.
- [ ] Update the shipped user guide and worked examples, including how SciStudio
  works, using the GUI, AI assistance, block/type authoring, and plots.
- [ ] Generate affected API reference pages from their maintained sources;
  do not hand-edit generated reference output.
- [ ] Add `docs/package-development/panels.md`; reduce `previewers.md` to legacy
  forms and migration; update related index/architecture/blocks/publishing pages
  and relevant types/tutorials links.
- [ ] Explain superseded frontend contracts in the ADR-048 and ADR-051 specs.
- [ ] Verify ADR-049 panel contract rows and the scope of its legacy security
  statements against Phase A/B evidence.
- [ ] Update ADR-055 identity-seam/enterprise panel notes to the implemented
  token-prefix delegation, removing obsolete "panels paused" statements.
- [ ] Prepare ARCHITECTURE.md §9.6, §12.2.3, §5.3.1 and project-layout proposals.
  Applying protected architecture prose remains a separate owner-reviewed step.
- [ ] Reconcile Phase C issue/spec scope, implementation status, and tutorial
  decisions; close #2013/#2197 only after their replaced acceptance is accounted
  for, including the old interactive-scaffold request.

## 7. Tutorials: Final Migration

Review all four bundled tutorials, including copy, code/data assets, workflow
definitions, UI targets, and AI-facing example instructions. Migrate affected
parts consistently with final A/B/D behavior, without rewriting unaffected copy.

- [ ] `welcome-to-scistudio`
- [ ] `what-is-a-type` (including legacy panel and previewer assets)
- [ ] `what-ai-can-do`
- [ ] `two-modalities-one-answer`
- [ ] Verify tutorial progression, referenced files, runnable workflow examples,
  and affected panel interactions after migration.

## 8. Existing Related Work And Final Verification

- [ ] Reconcile Phase D #2354 when its final PR is available; visibility PR #2368
  is not the final delivery. Do not infer completion from that visibility PR.
- [ ] Inspect #2375 / PR #2377 (documentation tools reading the project) before
  changing documentation lookup guidance; do not implement a duplicate fix.
- [ ] Inspect #2376 / PR #2380 (core IO steering) before revising related guidance.
- [ ] Account for #2384 (block scaffold correctness) when validating examples;
  keep its implementation separately tracked.
- [ ] Add the Phase C panel-authoring e2e scenario and appropriate evidence;
  distinguish skill structure/provisioning checks from actual agent/browser use.
- [ ] Validate packaging, fresh project installation, reopening existing projects,
  and preservation of user-customized guidance for changed delivery behavior.
- [ ] Run gate-selected checks, review the final diff, update changelog/specs and
  committed gate evidence, submit the complete Phase C PR, and wait for CI.
- [ ] Keep #2288 and partially overlapping issues open for remaining tracked
  deferrals; no automatic merge is authorized by this session.

## 9. Current Evidence

- Original main baseline: `8d9426df`. To align the MiniApp skill and actual
  screenshot API, the earlier session branch stacked on committed Phase D snapshot
  `3e966a1b5373efd451923c578636047671673252`. Phase D's writable worktree is
  untouched; reconcile with its final delivery before the Phase C PR.
- Session history branch: `codex/2295-ai-guidance-session`.
- PR branch: `codex/2295-panel-gui-guidance-pr`, created from `origin/main` with
  only the session's net Phase C changes. Phase D implementation and the MiniApp
  skill are not carried into this PR. MiniApp registration remains Phase D's work.
- Owner requested `SCISTUDIO_SKIP_PREFLIGHT=1` for this PR. No local preflight
  is rerun on this new main-based branch; CI provides current-head validation.
  The 172-test result below is historical evidence from the Phase D-based session.
- This focused PR closes #2013 (the panel skill supersedes the earlier previewer
  skill proposal). #2295 stays open for the remainder of Phase C. Phase D #2354
  remains the dependency for validator, shared renderer, and MiniApp references.
- Gate ledger: `.workflow/records/2295-ai-guidance-session.json`.
- Prompt unification: [issue #2383](https://github.com/jiazhenz026/SciStudio/issues/2383),
  branch `codex/unify-agent-instructions`, independent agent/worktree.
- GUI skill and provisioning implementation: originally `5b7fec60`, replayed
  onto the Phase D baseline as `440b24a1`.
- Local gate reconciliation passed with format, lint, audit, import contracts,
  type checks, and Python tests; the provisioning test selection passed all
  120 tests. Evidence is recorded in the gate ledger, with raw logs under the
  ignored `.workflow/local/logs/` directory.
- No live browser or real AI-provider GUI session was run for this content
  change. Panel authoring now routes to the guide; unified AGENTS routing,
  integration with #2383/final Phase D, the final Phase C PR, and CI remain pending.
- Current addition: general `open_gui` tool description/hint, panel authoring
  skill, installation/reopen coverage, and executable
  descriptor/SDK sample tests, committed as `18ea62d0`.
- The current addition passed all seven local gate checks. The diff-selected
  Python suite passed **172 tests**, including both descriptor/SDK sample-mode
  examples, complete URL-prefix handling, and installation/reopen preservation.
  These are automated contract checks, not real browser interaction evidence.
- Ownership correction: withdrew the MiniApp skill edits from `18ea62d0` and
  restored that file exactly to the pinned Phase D baseline. Its presence here
  was inherited from that stacked baseline; it is absent from the main-based PR.
- Owner boundary: edit only this worktree. The desktop implementation is
  Electron; unsupported Qt wording introduced during drafting was removed from
  all four affected guidance/spec files before the implementation commit.
