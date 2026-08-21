---
title: "Learning Center Levels Dispatch Prompts"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 53
related_specs:
  - adr-053-learning-center
language_source: en
---

# Learning Center Levels Dispatch Prompts

Filled from `docs/ai-developer/templates/agent-dispatch-prompt-template.md`.
Checklist: `docs/planning/learning-center-levels-checklist.md`. Umbrella PR
#2087 `[DO NOT MERGE]`; umbrella branch `track/learning-center-levels`.

Shared required reading for every dispatched agent:

- The GitHub issue(s) assigned to you
- `AGENTS.md`
- `docs/ai-developer/rules.md`
- `docs/ai-developer/specific_rules/agent-dispatch.md`
- `docs/ai-developer/specific_rules/gated-workflow.md`
- Your persona file under `docs/ai-developer/personas/`
- `docs/specs/adr-053-learning-center.md` (the system contract)
- `docs/planning/learning-center-scenarios.md` (the level designs)
- `src/scistudio/tutorials/core/welcome-to-scistudio/tutorial.yaml` (the
  authoring idiom)

Shared coordination rules (apply to every prompt below):

- You are not alone in this codebase. Work only on your assigned branch in
  your assigned worktree. Never `pip install -e .`. Do not revert or overwrite
  other agents' work. Do not broaden scope; if you need an out-of-scope path,
  stop and report back to the manager.
- Init your own gate ledger (`gate_record init`) in your worktree before
  editing; amend before touching anything outside your declared scope.
- PRs target `track/learning-center-levels` (pass
  `--base track/learning-center-levels` through
  `python scripts/scistudio_pr_create.py`). Never target `main`. Never merge.
- Deferred work needs `TODO(#NNN)` citing an issue. No untracked "later".
- Update only your own checklist rows.

---

## §P1 — Tutorial vocabulary, step trigger, and manifest batch

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Extend the tutorial runtime vocabulary and step model so the
  designed Learning Center levels 2-6 are expressible, with the matching spec
  revisions.
- Task kind: feature
- Persona: implementer
- Issues: #2061 #2062 #2063 #2066 #2088 #2089 (your PR closes all six)
- Umbrella PR: #2087 [DO NOT MERGE]
- Protected branch: main
- Umbrella branch: track/learning-center-levels
- Agent branch: feat/2061-tutorial-step-vocabulary
- Agent worktree: C:/Users/jiazh/workspace/SciStudio-wt-lcP1
- Gate record: create via gate_record init (--task-kind feature --persona
  implementer --branch feat/2061-tutorial-step-vocabulary --issue 2061
  --issue 2062 --issue 2063 --issue 2066 --issue 2088 --issue 2089)
- Checklist: docs/planning/learning-center-levels-checklist.md (rows P1)

## Scope

You own only:

- src/scistudio/tutorials/** (manifest.py, conditions.py, actions.py,
  driver.py, session.py, discovery.py, schema/tutorial.schema.json) — runtime
  changes; do NOT author level content
- src/scistudio/api/routes/tutorials.py and
  src/scistudio/api/routes/ai_pty/replay.py
- docs/specs/adr-053-learning-center.md — you are the ONLY agent allowed to
  edit the spec in this wave
- Frontend, narrowly: LearningCenter.parts/ActiveStep.tsx (trigger button),
  LearningCenter.parts/targets.ts + prefill.ts, lib/api/learningCenter.ts,
  store/learningCenterSlice.ts, the four ui-event emitter sites, the toolbar
  data-tutorial-target additions, App.parts/useProjectActions.ts (defaultStem
  for new data type)
- tests/tutorials/**, tests/api/test_tutorial_*.py, frontend tests for the
  surfaces above
- CHANGELOG.md

You must not touch:

- src/scistudio/tutorials/core/** (level content; welcome-to-scistudio's
  tutorial.yaml must remain VALID AND UNMODIFIED — it is your back-compat
  proof)
- src/scistudio/previewers/**, src/scistudio/core/dropins.py (P2's surface)
- docs/ai-developer/**, docs/architecture/ARCHITECTURE.md

## Work To Do

Read the gap findings first; every item below carries file:line evidence from
a completed capability survey.

1. **#2061 — step-level user-triggered action.** A step may declare a trigger:
   a label plus an ordered `do` list run when the reader clicks, distinct from
   entry `do`. Manifest field + schema; StepView widens by exactly this field
   (driver.py:139-190 is the FR-041 boundary); POST
   /api/tutorials/sessions/active/trigger endpoint; execution reuses the entry
   action machinery (perform_step_entry, actions.py:699-729) including the
   registry settle hook; ActiveStep.tsx renders the button. Spec revision:
   FR-011 (new core-owned field), FR-041 (closed set widens by this one field;
   closure principle preserved), FR-056/FR-059/FR-059a (triggered timing:
   actions and registry re-scan complete before the trigger reports done),
   FR-060 (trigger failure is surfaced on the step and retryable — it must NOT
   end the session; state this explicitly).
2. **#2062 — block_type selectors.** run_succeeded's node filter,
   port_has_output, plot_exists's node binding, and interaction_completed gain
   a `block_type` alternative to `node_id` (one-of), reading "any node of that
   type". Copy the in-tree pattern (node_exists/edge_exists/config_*,
   conditions.py:120-141). Touches TERM_SPECS, the four evaluators,
   ProductState resolution (routes/tutorials.py), FR-047 row text.
3. **#2063 part 1 — ui_event target argument.** UI_EVENT_NAMES
   (conditions.py:230-249) grows a per-name argument spec (FR-089b precedent,
   spec:1097-1105): block_source_viewed→block_type, node_selected→block_type,
   plot_rendered→plot_id, preview_expanded→none. Frontend emitters attach the
   target (useBottomPanelControls.ts:64, PlotsTab.tsx:96,
   fileTabActions.ts:16x, the preview emitter). Bare-name manifests stay
   valid (welcome yaml uses bare names). Revise FR-052 + the FR-047 ui_event
   row.
4. **#2063 part 2 — reserved workflows/ asset dir.** RESERVED_ASSET_DIRS +
   EXECUTABLE_ASSET_DIRS gain `workflows` (manifest.py:135-142); FR-006
   revision; FR-020a grades it executable-adjacent; update the spec's
   'at minimum' destination floor (spec:618) to match EXECUTED_PROJECT_PATHS
   (actions.py:100-110). Settle: a write landing under project workflows/ must
   reach the open canvas — extend the settle hook (routes/tutorials.py:854-944
   currently rescans blocks/+types/ only) to broadcast a workflow reload, with
   a test proving the frontend event path (workflow.changed or equivalent)
   fires.
5. **#2066 part 1 — since-step-entry scoping.** run_succeeded/run_failed gain
   optional `since_step_entry: true`; the session supplies the current step's
   entry time as evaluation context. Spec: FR-047 rows + one FR-046 sentence
   (evaluation context includes session-supplied step-entry time). FR-054
   untouched.
6. **#2066 part 2 — backend plot_rendered term.** A rendered figure exists for
   a plot (artifacts under .scistudio/previews/<workflow_id>/<node_id>/...),
   keyed by plot_id or block_type+port consistent with item 2. FR-047 term +
   FR-050 mapping (map to workflow_completed/block_done; file.changed's
   allowlist excludes images — say so). KEEP the existing ui_event
   plot_rendered name (welcome yaml uses it); document the coexistence in the
   spec (ui_event = the reader saw it render; backend term = a figure exists).
7. **#2088 — requires.tutorials.** `requires` gains a completed-tutorials list
   (same-source ids); discovery.unmet_requirement (discovery.py:306-328) lists
   the tutorial unavailable naming the unmet level (FR-024 pattern). Schema +
   FR-008 revision + catalogue surfacing test.
8. **#2089 — replay continuation.** A replay action may declare
   `continue_tab: true`: append segments to the surface's open replay tab
   instead of close-then-open (session.py:1083-1106, ai_pty/replay.py). Error
   if no tab is open. FR-061 revisions. Combined with item 1, a trigger's do
   list may carry a replay action — that is the L4 conversation pacing
   mechanism; add a test covering trigger-driven replay continuation and
   FR-061b ordering per appended action.
9. **Reading step pages field.** Reading steps gain an optional
   `pages: [<name>, ...]` field naming files under assets/pages/ (validated to
   exist, FR-014 containment); StepView exposes it; is_reading_only treats a
   step whose done_when is all/any of page_reached as reading (verify + test,
   conditions.py:252-267). Spec: FR-011 lists the field; one paragraph beside
   FR-084a stating the core-owned reading surface renders reading steps as
   cards with paged content served by the existing pages route. (Level 5's
   frontend consumes this; you build no reading UI.)
10. **Target/prefill vocabulary odds.** ROUTE_TARGETS gains the Data types
    left tab (backend manifest route_to validation + frontend targets.ts);
    PREFILL_SPECS gains new_data_type with a filename stem
    (manifest.py:249-262 + prefill wiring + createNewDataType defaultStem,
    useProjectActions.ts:459-467); HIGHLIGHT_SPECS gains the Bring-in-my-work
    toolbar entry (+ data-tutorial-target attribute on that button,
    Toolbar.parts). FR-011b/FR-089b tables updated.

Ordering guidance: commit incrementally, one concern per commit (2062 and
2063.1 first — they are small and unblock level authoring reviews; 2061 and
2089 are the deep cuts). The spec revision may land as one commit or ride each
concern; keep spec and code consistent at every commit.

## Required Tests And Checks

- Unit tests for every new term, argument, field, endpoint, and failure mode;
  session-lifecycle tests for trigger and replay continuation; schema
  validation tests incl. back-compat (welcome yaml validates unmodified);
  frontend vitest for the trigger button and emitter payloads.
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr` before
  PR creation; pre-PR `finalize`; PR via
  `python scripts/scistudio_pr_create.py --base track/learning-center-levels`;
  post-PR `finalize`.

## Output Required

Changed paths; tests run + results; checklist row P1 updated with artifacts;
PR number; any spec-consistency decision you made that a reviewer should see
first; blockers.

## Stop Conditions

Stop and report if: a change would break welcome-to-scistudio; FR-041's
closure cannot be preserved; you need previewer-registry or dropins changes
(P2's surface); local checks fail for unclear reasons.
```

---

## §P3 — Learning Center Windows test repairs

```markdown
[DISPATCH-TEMPLATE-V1: test_engineer]

## Task Identity

- Repository: SciStudio
- Owner request: Make the eight Windows-failing Learning Center tests pass on
  Windows for the right reasons.
- Task kind: bugfix
- Persona: test_engineer
- Issue: #2075 (your PR closes it)
- Umbrella PR: #2087 [DO NOT MERGE]
- Protected branch: main
- Umbrella branch: track/learning-center-levels
- Agent branch: fix/2075-lc-windows-tests
- Agent worktree: C:/Users/jiazh/workspace/SciStudio-wt-lcP3
- Gate record: create via gate_record init (--task-kind bugfix --persona
  test_engineer --branch fix/2075-lc-windows-tests --issue 2075)
- Checklist: docs/planning/learning-center-levels-checklist.md (row P3)

## Scope

You own only:

- tests/api/test_tutorial_routes.py
- tests/api/test_tutorial_project_visibility.py
- tests/tutorials/test_replay.py
- tests/tutorials/test_session_lifecycle.py
- tests/tutorials/test_manifest_schema.py
- shared test helpers/fixtures those files use (conftest additions allowed)

You must not touch production code. `api/runtime/_helpers.py` already has
`_rmtree_force` — use it from tests; do not modify it.

## Work To Do

Follow the classification in issue #2075 exactly:

1. Four rmtree failures: simulate out-of-product deletes with the product's
   own `_rmtree_force` (or an equivalent test helper that clears read-only
   bits) instead of bare `shutil.rmtree` on git-initialised projects.
2. Two CRLF failures: write replay/text fixtures as bytes or with
   `newline=""` so POSIX literals compare equal on Windows.
3. One separator failure: record `PurePath.as_posix()` in RecordingDelivery
   comparisons.
4. One symlink failure: capability-probe (attempt the symlink, `pytest.skip`
   with the privilege reason on OSError) rather than a blanket platform skip.
   Repository policy is fix-over-skip: a skip must state the missing OS
   capability, not the OS.

Verify: the eight tests pass on this Windows machine; the full
tests/tutorials + tests/api tutorial subset stays green; no new skips beyond
item 4's capability probe.

## Required Tests And Checks

- `python -m pytest tests/tutorials tests/api/test_tutorial_routes.py tests/api/test_tutorial_project_visibility.py` (Windows, this machine)
- `gate_record check --mode pre-pr`; pre-PR finalize; PR via wrapper with
  `--base track/learning-center-levels`; post-PR finalize.

## Output Required

Changed paths; the eight tests' before/after status; checklist row P3;
PR number; blockers.

## Stop Conditions

Stop and report if any of the eight turns out to reflect a product defect
rather than a test defect (that becomes a new issue, not a test change), or
if you need a production file.
```

---

## §L5 — Core tutorial 5: the summary level (reading)

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Author core tutorial 5 — the reading-only summary level: one
  window, one top sentence, eight cards, paged card content.
- Task kind: feature
- Persona: implementer
- Issue: #2084 (your PR closes it)
- Umbrella PR: #2087 [DO NOT MERGE]
- Protected branch: main
- Umbrella branch: track/learning-center-levels
- Agent branch: feat/2084-core-tutorial-5
- Agent worktree: C:/Users/jiazh/workspace/SciStudio-wt-lcL5
- Gate record: create via gate_record init (--task-kind feature --persona
  implementer --branch feat/2084-core-tutorial-5 --issue 2084)
- Checklist: docs/planning/learning-center-levels-checklist.md (row L5)

## Scope

You own only:

- src/scistudio/tutorials/core/<your-tutorial-id>/** (manifest + assets/pages)
- New frontend reading-surface components under
  frontend/src/components/LearningCenter.parts/ (e.g. ReadingSurface.tsx and
  parts) and their wiring into LearningCenter.tsx (replacing the TODO(#2057)
  at LearningCenter.tsx:59-66)
- frontend/src/lib/api/learningCenter.ts additions needed to fetch pages
- Tests: tests/tutorials/ manifest-validation for your tutorial, frontend
  vitest for the reading surface
- CHANGELOG.md

You must not touch:

- src/scistudio/tutorials/*.py, tutorial.schema.json, or
  docs/specs/adr-053-learning-center.md — agent P1 owns them THIS WAVE. The
  `pages:` step field and its spec text are being added by P1
  (feat/2061-tutorial-step-vocabulary). Build content first; build the UI
  against the contract below; integrate live after P1 merges into the
  umbrella and you have merged the umbrella back into your branch.
- ActiveStep.tsx, targets.ts, prefill.ts (P1's files)
- Other tutorials' directories

## The Contract (agreed with P1; do not redesign)

- A reading tutorial = every step waits on continue or page_reached only
  (is_reading_only, conditions.py:252-267). No bootstrap (no project).
- One step per card, 8 steps. Step `title` = card name; step `say` = the
  card's one-line summary; step `pages: [<page-name>, ...]` lists its pages in
  reading order (files under assets/pages/, flat, markdown); step `done_when`
  = all of page_reached for that card's pages.
- Tutorial `summary` = the window's top sentence. Write a placeholder the
  owner will iterate: it must say, in one sentence, what SciStudio's core
  concept is (workflow of blocks over typed data, reproducible by design).
  Flag it clearly in the PR body for owner wording review.
- The reading surface (your frontend work): when the active session's
  tutorial is reading-only, render a window instead of the floating step
  card — top sentence, then the 8 cards in 2 rows in step order
  (workflow, block, data type, previewer, plot card, history, my library,
  others); a card opens a paged reader that fetches
  GET /api/tutorials/.../pages/{name} (this records page_reached); reading
  the last page returns to the grid; completed cards show their state
  (step satisfied); the tutorial completes through the normal
  continue/advance flow. Design for any reading tutorial, not just this one.

## Content: the eight cards

Source of truth: `docs/planning/learning-center-scenarios.md` 关卡 5 section
(card-by-card page outlines, owner-decided) and issue #2084's content
contracts. EVERY factual claim must be verified against the code before it
ships — the scenarios doc lists file:line evidence for most; re-verify, do
not trust it blindly. Non-negotiable facts (already re-verified once; verify
again yourself): six base block categories from _infer_category; six
built-ins (Load, Save, DataRouter, PairEditor, MergeCollection, Split; never
MergeBlock); IO = 2 blocks + format capabilities; Re-run is REMOVED,
run-from-here retained (ADR-038 Add.1) — restore-then-you-press-Run is two
deliberate steps; tidy writes only node.layout, focus is view-only; port
colours resolve through the types API single source; previewer fallback walks
the type chain then core, tiers project > package > core; plots are
preview-only and overwritten — export is the only way to keep a figure;
pre-run auto-commit with `auto` prefix; git-unavailable degradation; My
Library = user-level, project-tier stays in the project; CompositeData is the
one type the reader never used (flag the asymmetry in the card); others card
closes with the persistent "Bring in my work" toolbar entry.

Write the pages in English (repository language), reader-facing tone, short
pages (a screen each), markdown. Cards cross-reference each other where the
scenarios doc says so (block ↔ my library; plot card ↔ history's
"recipe not results").

## Work Ordering

1. Author all pages + the manifest (content-first; the manifest will not
   validate until P1's `pages:` field lands — keep it ready and validate
   after the umbrella merge-back).
2. Build the reading surface against mocked step views (vitest).
3. When the manager announces P1 has merged into the umbrella: merge
   track/learning-center-levels into your branch, validate the manifest,
   wire live, and verify end-to-end locally (backend + Vite).

## Required Tests And Checks

- Manifest schema validation test for your tutorial; is_reading_only holds;
  every named page file exists; frontend vitest for grid/pager/page_reached
  fetch; `gate_record check --mode pre-pr`; pre-PR finalize; PR via wrapper
  `--base track/learning-center-levels`; post-PR finalize.

## Output Required

Changed paths; page inventory (card → pages); every factual claim you could
NOT verify in code (list them explicitly — the manager audits these);
checklist row L5; PR number; blockers.

## Stop Conditions

Stop and report if the contract above cannot express something the scenarios
doc requires; if you need a runtime or spec change; if P1's landed contract
differs from the one described here.
```
