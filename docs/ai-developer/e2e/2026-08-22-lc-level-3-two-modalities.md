---
session_id: "lc-level-3-two-modalities"
title: "Core tutorial 3 (two-modalities-one-answer) — prerequisite gate and the level-2 library bridge"
created: "2026-08-22"
owner: "@jiazhenz026"
trigger:
  kind: "feature-sweep"
  ref: "PR #2082 on track/learning-center-levels (tip c00bb197c)"
related_adrs:
  - 53
status: "failed"
language_source: en
---

# E2E Session — Tutorial 3 gate and bridge

> Chrome MCP is not connected in this session; the run is driven by Playwright
> (chromium, a real browser) against a live backend, per the manager checklist.

## 1. Goal And Out-Of-Scope

- **Goal**: two things. First, that the prerequisite gate (#2088) works as
  designed — on a profile that has not finished tutorial 2 the level is listed,
  is marked unavailable, says why, and cannot be started. Second, the
  level-2 → level-3 **bridge**: the `Image` type, the `Segment Cells` block and
  the `Image` previewer arrive from the tutorial-scoped library into tutorial
  3's fresh project, and a slice renders as a PICTURE rather than falling back
  to the core Array number table (the #2125 shape).
- **Out of scope**: steps 5-20 (index pairing, the PairEditor interaction,
  k-means clustering, the git-branch beats). This session stops at the bridge —
  see 7.1 for why, and what would be needed to go further.

## 2. Preconditions

- **Repo state**: `test/2081-level-e2e-sessions` @ `c00bb197c`
- **Worktree**: `C:/Users/jiazh/workspace/SciStudio-wt-lcE2E`
- **Backend**: 8032; **Vite**: 5182 (a sibling session owns 8031/5181)
- **Env**: isolated short-path `USERPROFILE` (`C:/Users/jiazh/lce2e`)
- **Phase A (gate)**: a profile with tutorial 2 **not** completed
- **Phase B (bridge)**: a **seeded** profile — see 7.1, this is stated openly
  because it is not the reader's path

## 3. Launch Plan

Same harness as the other level sessions: reset the profile home → backend on
8032 → Vite on 5182 → Playwright spec. Phase B additionally seeds the profile
before launch (commands recorded in 7.1).

## 4. Affordances Under Test

- Catalogue: `requires.tutorials` → `state: "unavailable"` +
  `unavailable_reason` (FR-085), and the detail pane's Start control
- The tutorial-scoped library (FR-070) as the carrier between levels
- `type_registered` judged against a type the level never builds
- The preview pane choosing a project/library previewer over the core Array
  fallback for a custom type

## 5. Steps

### Phase A — the gate
1. On a profile without tutorial 2 completed, read `GET /api/tutorials/catalogue`
2. Open the Learning Center and select the level
3. **Expected**: listed at order 3; `state: "unavailable"`; a reason naming what
   to do first; **no** Start control

### Phase B — the bridge
4. Seed the library artefacts and tutorial 2's completion, restart the backend
5. **Expected**: the level's state clears to `not_started`
6. Start it; step 2 (`type_registered: Image`) must be satisfied on entry
7. Add Load, point it at `data/raw/sections.tif`, type `Image`, Run, click Load
8. **Expected**: the preview shows the sections as **pictures**, not a number
   table

## 6. Regression Sentinels

- No uncaught page errors; no 5xx; backend and Vite stay up.

## 7. Results

### 7.1 Verdict

**Gate: PASS. Bridge: PASS (on a seeded profile). Level as a whole: FAIL —
unreachable by a real reader.**
2026-08-22, `test/2081-level-e2e-sessions` @ `c00bb197c`.

The gate and the bridge both work. The level is nevertheless **not reachable by
any reader on this tip**, because its prerequisite is tutorial 2 and
**tutorial 2 cannot be completed** — the workflow validator refuses the edge its
step 14 requires (full write-up in
`2026-08-22-lc-level-2-what-is-a-type.md`, observation 7.3.1). The level-2 P1
therefore blocks two levels, not one. That is the single most important fact in
this file.

**The seeding, stated plainly.** To test anything past the gate, this session
reproduced the state a completed tutorial 2 leaves behind, rather than
completing tutorial 2 (which is impossible here):

```
<home>/SciStudio Tutorials/.library/types/image.py            <- from t2 assets/code/image.py
<home>/SciStudio Tutorials/.library/blocks/segment_cells.py   <- from t2 assets/code/segment_cells.py
<home>/SciStudio Tutorials/.library/previewers/image_preview.py <- from t2 assets/code/image_preview.py
<home>/.scistudio/tutorial-progress.json
    completed += {"source_kind":"core","source_id":"","tutorial_id":"what-is-a-type"}
```

These are exactly the three files tutorial 2's steps 19-21 promote and the
progress record its completion writes. Everything after the seed is the product
doing its own work, unaided. This is **not** the reader's path and no claim in
this file should be read as evidence that the reader's path works.

### 7.2 Phase A — the prerequisite gate: PASS

On a profile with tutorial 2 not completed:

```
{"id":"two-modalities-one-answer","order":3,"state":"unavailable",
 "reason":"needs the tutorial 'what-is-a-type' from the same source to be completed first"}
core group: completed 1 of 6
```

And through the UI a reader actually sees:

- the level is **listed** in the catalogue at position 3, with the ⚠ unavailable
  icon;
- the detail pane shows the **"Unavailable"** badge;
- the reason is printed in the detail pane (FR-085 satisfied — it does not just
  refuse, it says what to do);
- `tutorial-detail-start` has **count 0** — there is no Start control at all,
  rather than a disabled one.

Evidence: `t3-00-gated.png`.

### 7.3 Phase B — the bridge: PASS

After seeding, the level's state cleared from `unavailable` to `not_started`,
so the gate opens on completion rather than on anything incidental.

Then, with no help from the driver:

- **Step 2 (`type_registered: Image`) was satisfied on entry.** The level builds
  no type; `Image` arrived from the tutorial-scoped library into a brand-new
  project.
- The Data types tab in tutorial 3's fresh project listed:
  `["Array","Artifact","CompositeData","DataFrame","DataObject","Series","Text","Image"]`
  — `Image` beside the core types, in a project that never created it.
- **Step 4 (`run_succeeded` + `node_selected`) passed**, and the preview pane
  showed the collection as `3 IMAGE (SHOWING 3)` with the three sections named
  `S05`, `S09`, `S01` — typed as `Image`, **no table element in the pane**.
- Opening one section rendered **actual pixels**:

```
{"imgs":1,"imgSrc":"data:image/png;base64,iVBORw0KGgoAAAANSU...",
 "canvases":0,"tables":0}
```

  and the screenshot shows the micrograph — a dark field with bright cell blobs
  (`t3-05-section-opened.png`).

**The #2125 shape did not reproduce.** The previewer travelled with the type,
and an `Image` knows how to show itself in a project that never defined it.
This is the design's central claim and it holds.

Evidence: `t3-01-welcome.png`, `t3-02-library-types.png`, `t3-03-load-config.png`,
`t3-04-image-preview.png`, `t3-05-section-opened.png`; driver
`tutorial3.live.ts` and `tutorial3gate.live.ts` in the out-of-repo harness.

### 7.4 Product observations

1. **P1 (inherited, not this level's fault) — tutorial 3 is unreachable.** Its
   prerequisite is tutorial 2, and tutorial 2 stops at step 14 on this tip. The
   fix is the level-2 follow-up 1 (static `validate_connection` must use
   `same_registered_type`); nothing in tutorial 3 needs changing for this.
2. **Low — the unavailable reason speaks in manifest ids.** It reads
   *"needs the tutorial 'what-is-a-type' from the same source to be completed
   first"*. Two rows above it in the same list the tutorial is called
   **"What is a type"**. `'what-is-a-type'` is the internal id and "from the
   same source" is internal vocabulary (it distinguishes core from package
   sources, which a reader has no model for). It is still actionable — the id
   is close enough to the title to find — so this is copy polish, not a defect.
3. **Low — the opened section is labelled `application/octet-stream`.** The
   preview toolbar shows that MIME type beside a control row while displaying a
   PNG the previewer just produced. Cosmetic, but it is the one place the pane
   tells the reader what they are looking at.
4. **P2 — core tutorial 3 landed on the track with its own runtime test red.**
   Found while running the gate's Python suite on this branch (whose diff is
   docs-only, so the failure is inherited from the base):

   ```
   FAILED tests/tutorials/test_core_tutorial_two_modalities.py::
          test_the_whole_tutorial_walks_through_the_real_runtime

   scistudio.tutorials.session.TutorialUnavailableError:
     tutorial 'two-modalities-one-answer' cannot be started:
     needs the tutorial 'what-is-a-type' from the same source to be completed first
   ```

   The test walks the level through the real runtime but never marks tutorial 2
   complete, so `TutorialRuntime.start()` refuses at the prerequisite the level
   itself declares. The gate is working; the test simply does not satisfy it.
   Same shape as the seeding this session had to do by hand (7.1) — the fix is
   to mark `what-is-a-type` completed in the test's progress store before
   `start()`, and to place the three library artefacts the level consumes.

5. **Not observed here:** the intermittent zarr publish failure (level-2
   observation 7.3.2) did not fire in the four runs of this session, though this
   level does persist `Image` (zarr) outputs. Consistent with a ~3.5%
   per-publish race rather than absence.

6. **Separately, the suite carries one rotating flake.** Across three full runs
   a single extra test failed each time and **passed in isolation** every time —
   a different one each run
   (`tests/api/test_workflows.py::test_cancel_block_and_cancel_workflow_propagate_terminal_states`,
   then `tests/ai/test_providers_registry.py::test_kimi_mcp_read_retries_while_the_file_is_busy`).
   Both are timing-sensitive. Recorded so the next reader of a red suite does not
   chase it.

   A clean full run on this branch, with no live e2e backend competing for the
   machine, measures:

   ```
   2 failed, 7194 passed, 81 skipped, 8 xfailed in 137s
     FAILED tests/tutorials/test_core_tutorial_two_modalities.py::test_the_whole_tutorial_walks_through_the_real_runtime   <- real, inherited
     FAILED tests/ai/test_providers_registry.py::test_kimi_mcp_read_retries_while_the_file_is_busy                        <- passes in isolation
   ```

   **One deterministic failure**, and it is the level-3 test above. Note that an
   earlier run made while this session's own backend and Vite were still up
   reported twelve failures; eleven of those were contention, and all eleven
   passed once the e2e processes were stopped. Anyone re-measuring should stop
   the live harness first.

### 7.5 Sentinels

None fired. `pageErrors: []`; no 5xx; backend and Vite stayed up.

### 7.6 Follow-ups

1. **P2** fix `test_core_tutorial_two_modalities.py`'s runtime walk to satisfy
   the prerequisite it declares (see 7.4.4) — it is red on the track today.
2. **Blocked on level-2 follow-up 1.** Once the validator is fixed, tutorial 2
   should be completed honestly end-to-end and this session re-run **without the
   seed**, walking steps 5-20 (index pairing, the PairEditor interaction, the
   k-means block, and the two git-branch beats), which this session did not
   touch.
3. **Low** reword the unavailable reason to use the tutorial's title.
4. **Low** the preview's MIME label for a previewer-rendered image.
