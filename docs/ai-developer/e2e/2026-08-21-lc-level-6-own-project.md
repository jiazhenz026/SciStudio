---
session_id: "lc-level-6-own-project"
title: "Core tutorial 6 (start-your-own-project) walks end to end"
created: "2026-08-21"
owner: "@jiazhenz026"
trigger:
  kind: "feature-sweep"
  ref: "PR #2114 on track/learning-center-levels (#2085)"
related_adrs:
  - 53
status: "passed"
language_source: en
---

# E2E Session — Tutorial 6 own-project walkthrough

> Driven by Playwright (chromium, real browser) against a live backend with an
> isolated USERPROFILE, per the manager checklist.

## 1. Goal And Out-Of-Scope

- **Goal**: prove the level's participation mechanics on the integrated
  track: the bootstrap lands the pretend-"your own" folder; the import
  trigger moves its files into data/raw (judged file_exists); the reader
  wires load → summarize block → save into data/processed; the run succeeds
  (since_step_entry); the plot renders (targeted ui_event); the export beat
  reads honestly as a continue step; completion records.
- **Out of scope**: the four-bucket copy's wording (content audit); other levels.

## 2. Preconditions

- **Repo state**: `test/2081-level-e2e-sessions` @ `c00bb197c`
  (= `track/learning-center-levels` with all six core tutorials)
- **Worktree**: `C:/Users/jiazh/workspace/SciStudio-wt-lcE2E`
- **Backend**: 8032; **Vite**: 5182 (a sibling session owns 8031/5181)
- **Env**: isolated short-path USERPROFILE (`C:/Users/jiazh/lce2e`) so progress,
  the tutorial parent dir and the user library start clean, and the preview
  cache path stays under Windows MAX_PATH (#2116)

## 3. Launch Plan

Same harness as the level-1 session (`run-lc-e2e.sh` pattern).

## 4. Affordances Under Test

- Tutorial bootstrap copy (incoming-example/); step trigger buttons (#2061)
- file_exists judging on trigger-moved files; config_matches on save path
- run_succeeded since_step_entry; targeted plot_rendered ui_event
- Honest continue on the export beat; completion

## 5. Steps

### Step 1 — Start tutorial 6
- **Action**: start start-your-own-project from the catalogue
- **Expected**: project bootstraps with incoming-example/ present
- **Capture**: screenshot

### Step 2 — The import trigger
- **Action**: press the step's trigger ("do it with me" import)
- **Expected**: files land in data/raw; the step satisfies via file_exists
- **Capture**: screenshot

### Step 3 — Wire and run
- **Action**: follow the steps: load the CSV, add the summarize block, add
  save into data/processed, Run
- **Expected**: run succeeds; the result lands in data/processed; steps judge

### Step 4 — Plot and export beat
- **Action**: create/render the growth-curves plot; read the export step
- **Expected**: targeted plot_rendered satisfies; the export step is a
  continue step whose copy says it cannot be checked
- **Capture**: screenshot

### Step 5 — Complete
- **Action**: finish the remaining reading steps
- **Expected**: completion recorded in the catalogue
- **Capture**: catalogue API response

## 6. Regression Sentinels

- No uncaught page errors; no 5xx; backend and vite stay up.

## 7. Results

### 7.1 Verdict

**PASS** — 2026-08-22, `test/2081-level-e2e-sessions` @ `c00bb197c`
(= `track/learning-center-levels` with all six core tutorials integrated).
First run on `5ca880d7f`; re-run unchanged on `c00bb197c` after core tutorial 3
landed, which is the result recorded below.

All 16 steps completed in a real browser against a live backend, each by its
own designed action. No page errors, no 5xx. Wall time 51.4s.

### 7.2 What ran

Learning Center → start `start-your-own-project` → the project bootstraps with
`incoming-example/` → the three framing reading steps → the **import trigger**
copies the folder into `data/raw` → Load added and pointed at
`data/raw/growth_measurements.csv` → the step-7 entry action writes
`blocks/summarize_growth.py` and the palette already lists it → Summarize Growth
added and wired from Load → Save added and wired from the summary → Save pointed
at `data/processed` (filename prefilled `growth_summary.csv`) → a real engine
run → the result is on disk → the `data/exchange` reading beat → a new plot
bound to the **Load** block's table output (name prefilled `growth_curves`) →
the step-14 entry action writes `plots/growth_curves/render.py` and the plot
card renders → the honest continue on the export beat → done.

Backend truth after the run — `GET /api/tutorials/catalogue`:

```
group SciStudio -> completed 1 of 6
    start-your-own-project = complete     <-- this session
```

`GET /api/tutorials/unlock` → `{"work_import_offer_pending": false}` — correct:
the milestone is tutorial 4, and this level must not move it.

Product truth on disk, read straight from the tutorial project:

```
incoming-example/     growth_measurements.csv, notes.txt    (bootstrap)
data/raw/             growth_measurements.csv, notes.txt    (after the trigger)
data/processed/       <empty>                  before the run
data/processed/       growth_summary.csv       after the run
blocks/               summarize_growth.py      (step-7 entry action)
plots/growth_curves/  plot.yaml, render.py     (step-14 entry action)
```

Final workflow on the backend: **3 nodes, 2 edges** — Load → Summarize Growth →
Save, no duplicates.

The beats that carry the level's teaching all held up:

- **The import trigger moves the whole folder, notes and all.** `data/raw` was
  empty before the press and held both `growth_measurements.csv` and `notes.txt`
  after it. The step judges `file_exists` on both, and both are real.
- **"Nothing lands in data/processed on its own" is literally true.**
  `data/processed` was observed **empty immediately before the run** and held
  `growth_summary.csv` only after it. The step-9 copy makes a claim about
  product behaviour and the product honours it.
- **The palette lists a block the moment its file is written.** The step-7 tile
  was asserted visible before the block was placed — the step's own lesson about
  `blocks/` being live.
- **The plot binds to a non-terminal block.** The picker offered
  `["Python", "R", "Save · output run first", "Load · data DataFrame",
  "Summarize Growth · summary DataFrame"]`; the plot was bound to **Load**, not
  the last block, which is the point the step makes. A real figure rendered — a
  "Growth curves" line chart, three cultures over four days — verified visually
  in `t6-14-plot-rendered.png`, not merely from the `plot_rendered` event.
- **The export beat is an honest continue.** The backend reported
  `{"id": "export-or-lose-it", "satisfied": false, "awaiting_continue": true}`:
  no condition claims to have seen an export, the copy says so ("We cannot check
  this one for you"), and Continue is live anyway. The design working as written.

Evidence: `t6-01-welcome.png`, `t6-04-imported.png`, `t6-06-load-config.png`,
`t6-07-summarize-wired.png`, `t6-10-run.png`, `t6-13-plot-created.png`,
`t6-14-plot-rendered.png`, `t6-15-export-beat.png`, `t6-16-final.png` under the
session scratchpad `pw-artifacts/`; driver `tutorial6.live.ts` in the out-of-repo
harness.

### 7.3 Product observations

1. **Low — the plot binding picker mixes languages with block outputs, and one
   label runs together.** The options read
   `["Python", "R", "Save · output run first", "Load · data DataFrame",
   "Summarize Growth · summary DataFrame"]`. "Python" and "R" are the plot's
   *language*, not a binding, yet they sit in the same option list the step tells
   the reader to pick a binding from. And `Save · output` carries the status
   "run first" with no separator, so its accessible text reads
   `Save · outputrun first`. Neither blocks the step; both are the kind of thing
   a reader stumbles over once.
2. **Low — the rotating palette tip overlaps the palette during tutorial steps.**
   Same as the level-2 session's observation 4, so it is systemic rather than
   level-2 specific. Captured here in `t6-14-plot-rendered.png`, where the tip
   card sits over the bottom of the palette while the tutorial step card is also
   on screen.
3. **Low — the React duplicate-key warning fired at steps 7 and 8** (canvas edge
   keys), the same warning recorded in the level-1 session. Its persisted
   counterpart — the backend storing an identical edge twice — is written up in
   the level-2 scenario file, observation 5. This level's final graph was clean
   (2 edges, no duplicates), so the duplication is intermittent.
4. **Not reproduced here, and that is expected rather than reassuring.** The
   intermittent zarr publish failure (`WinError 5`, level-2 observation 2) did
   not fire in this level, because this level persists DataFrames — parquet,
   single-file writes — rather than Array-family types, which use zarr directory
   stores and the rename that races.

### 7.4 Sentinels

None fired. `pageErrors: []`; no 5xx; `alert`/`confirm` never fired; backend and
Vite stayed up throughout. The only console noise is the pre-existing pair of
`403`s from `GET /api/packages/updates` at startup.
