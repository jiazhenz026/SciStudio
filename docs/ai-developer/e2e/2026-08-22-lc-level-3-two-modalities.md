---
session_id: "lc-level-3-two-modalities"
title: "Core tutorial 3 (two-modalities-one-answer) — prerequisite gate and the level-2 library bridge"
created: "2026-08-22"
owner: "@jiazhenz026"
trigger:
  kind: "feature-sweep"
  ref: "PR #2082 on track/learning-center-levels; re-verified after the #2134 fix"
related_adrs:
  - 53
status: "passed"
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

- **Repo state**: `test/2081-level-e2e-sessions` @ `a7cd4b862`
- **Worktree**: `C:/Users/jiazh/workspace/SciStudio-wt-lcE2E`
- **Backend**: 8032; **Vite**: 5182 (a sibling session owns 8031/5181)
- **Env**: isolated short-path `USERPROFILE` (`C:/Users/jiazh/lce2e`)
- **Phase A (gate)**: a profile with tutorial 2 **not** completed
- **Phase B (bridge)**: the profile on which tutorial 2 had just been completed
  end to end — the reader's own path, no seeding

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

**Gate: PASS. Bridge: PASS, on the real reader path. Steps 5-20: not tested.**
2026-08-22, `test/2081-level-e2e-sessions` @ `a7cd4b862`.

> **This supersedes an earlier verdict of "level FAIL — unreachable".** When
> this session first ran, tutorial 3 could not be reached by any reader because
> its prerequisite, tutorial 2, could not be completed (the #2134 validator
> defect). That is fixed. Tutorial 2 now completes end to end, its last three
> steps put the `Image` type, the `Segment Cells` block and the `Image`
> previewer into the tutorial-scoped library, and tutorial 3's gate opens on
> that completion. **No seeding was used for the run recorded below** — an
> earlier, clearly-labelled seeded run reached the same conclusion, and this one
> confirms it on the path a reader actually walks.

What is verified: the prerequisite gate, and the level-2 → level-3 bridge, which
is the level's whole premise. What is **not** verified: steps 5-20 — index
pairing, the PairEditor interaction, the k-means block, the plot, and the two
git-branch beats. Those need their own session.

### 7.2 Phase A — the prerequisite gate: PASS

On a profile with tutorial 2 not completed:

```
{"id":"two-modalities-one-answer","order":3,"state":"unavailable",
 "reason":"needs the tutorial 'what-is-a-type' from the same source to be completed first"}
```

Through the UI a reader actually sees:

- the level **listed** at position 3, carrying the unavailable warning icon;
- the **"Unavailable"** badge in the detail pane;
- the reason printed there (FR-085 — it does not just refuse, it says what to do);
- `tutorial-detail-start` with **count 0** — no Start control at all, rather
  than a disabled one.

And the gate **opens on completion**: immediately after tutorial 2 finished in
the same profile, the catalogue reported

```
what-is-a-type            = complete
two-modalities-one-answer = not_started      <-- no longer unavailable
```

Evidence: `t3-00-gated.png`.

### 7.3 Phase B — the bridge, on the real path: PASS

Tutorial 3 was started on the profile tutorial 2 had just completed. With no
help from the driver:

- **Step 2 (`type_registered: Image`) was satisfied on entry.** This level builds
  no type; `Image` arrived from the tutorial-scoped library into a brand-new
  project, which is exactly the claim the level's premise rests on.
- The Data types tab in tutorial 3's fresh project listed
  `["Array","Artifact","CompositeData","DataFrame","DataObject","Series","Text","Image"]`
  — the reader's own type beside the core ones, in a project that never created it.
- **Step 4 (`run_succeeded` + `node_selected`) passed.** The preview pane showed
  the collection as `3 IMAGE (SHOWING 3)`, the three sections named `S05`, `S09`,
  `S01`, typed as `Image`, with **no table element in the pane**.
- Opening one section rendered **actual pixels**:

```
{"imgs":1,"imgSrc":"data:image/png;base64,iVBORw0KGgoAAAANSU...",
 "canvases":0,"tables":0}
```

  and the screenshot shows the micrograph — a dark field with bright cell blobs
  (`t3-05-section-opened.png`).

**The #2125 shape did not reproduce.** The previewer travelled with the type, and
an `Image` knows how to show itself in a project that never defined it. That is
the design's central claim, and on the reader's own path it holds.

Evidence: `t3-01-welcome.png`, `t3-02-library-types.png`, `t3-03-load-config.png`,
`t3-04-image-preview.png`, `t3-05-section-opened.png`; drivers
`tutorial3.live.ts` and `tutorial3gate.live.ts` in the out-of-repo harness.

### 7.4 Product observations

1. ~~**P1 (inherited) — tutorial 3 is unreachable.**~~ **Resolved.** Its
   prerequisite is tutorial 2, which could not be completed until `34b7b9eea`
   (#2134). With that fix in, tutorial 2 completes, the gate opens on its
   completion, and tutorial 3 starts normally. Nothing in tutorial 3 needed
   changing. Re-verified live on the unseeded path.
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

6. **P2 (cross-cutting, blocks a green local gate) — the run-execution and
   websocket API tests flake under the full parallel suite.**

   `gate_record check --mode pre-pr` was run **nine times** on this docs-only
   branch. It never came out green, and the failing set shuffled every time:

   ```
   2 failed · 4 failed · 8 failed · 3 failed · 4 failed · 6 failed
   … then, after cleaning up this session's own leftovers: 1 · 1 · 4
   ```

   Every failure came from the same family, and no other part of the suite ever
   failed:

   ```
   tests/api/test_workflows.py::test_cancel_block_and_cancel_workflow_propagate_terminal_states
   tests/api/test_workflows.py::test_workflow_pause_and_resume_keeps_downstream_block_ready
   tests/api/test_workflows.py::test_workflow_execute_and_execute_from_reuses_cached_outputs
   tests/api/test_workflows.py::test_execute_while_running_is_rejected_with_409
   tests/api/test_workflows.py::test_execute_after_completion_is_allowed
   tests/api/test_system_vertical.py::test_execute_from_records_parent_run_and_websocket_completion
   tests/api/test_system_vertical.py::test_execute_broadcasts_runtime_lifecycle_events_to_websocket
   tests/api/test_system_vertical.py::test_multi_session_execute_broadcasts_terminal_state_and_get_matches
   tests/api/test_system_vertical.py::test_completed_run_lineage_outputs_are_previewable
   ```

   **They all pass in isolation.** Both files together: `23 passed in 38s`
   serially, and `23 passed in 15s` under `-n auto`. A single failing test alone:
   `1 passed in 3.3s`. They only fail when the *whole* suite runs in parallel.

   These tests spawn real block subprocesses and drive websockets — precisely
   the category the repository already has a mechanism for. `pyproject.toml`
   defines a `serial` marker for "process/PTY/thread/timing-sensitive tests that
   must run OUTSIDE xdist", and `scistudio.qa.testing.run_python_tests` runs a
   two-phase batch for it (#1867, #1896). **Neither file contains a single
   `pytest.mark.serial`** (`grep -c` → 0 in both). Marking this family `serial`
   is the fix the mechanism was built for.

   One caveat learned the hard way, and worth passing on: leftover
   `chrome-headless-shell` processes from a live e2e session make this much
   worse — the failure count dropped from 8/6/4 to a steady 1 as soon as this
   session's browsers were killed. Anyone measuring the suite should stop any
   live harness first, or they will misattribute the noise.

   This is inherited, not caused here: this branch's diff touches only `docs/**`
   and its own gate ledger.

### 7.5 Sentinels

None fired. `pageErrors: []`; no 5xx; backend and Vite stayed up.

### 7.6 Follow-ups

1. ~~**P2** fix `test_core_tutorial_two_modalities.py`'s runtime walk~~ —
   **fixed** on the track (`5e6bd60f0`); `tests/tutorials` is green again.
1b. **P2** mark the run-execution / websocket API tests `serial` (7.4.6). They
   are the only thing standing between this branch and a green local gate, and
   the `serial` mechanism (#1867, #1896) already exists for exactly them.
2. **Still open — steps 5-20 are untested.** Once the validator is fixed, tutorial 2
   should be completed honestly end-to-end and this session re-run **without the
   seed**, walking steps 5-20 (index pairing, the PairEditor interaction, the
   k-means block, and the two git-branch beats), which this session did not
   touch.
3. **Low** reword the unavailable reason to use the tutorial's title.
4. **Low** the preview's MIME label for a previewer-rendered image.
