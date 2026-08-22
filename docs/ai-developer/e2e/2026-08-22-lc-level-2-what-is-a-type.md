---
session_id: "lc-level-2-what-is-a-type"
title: "Core tutorial 2 (what-is-a-type) walks end to end on the integrated track"
created: "2026-08-22"
owner: "@jiazhenz026"
trigger:
  kind: "feature-sweep"
  ref: "PR #2122 on track/learning-center-levels (#2081); re-verified at tip c00bb197c"
related_adrs:
  - 53
status: "failed"
language_source: en
---

# E2E Session — Tutorial 2 type-system walkthrough

> Chrome MCP is not connected in this session; the run is driven by
> Playwright (chromium, a real browser) against a live backend, per the
> manager checklist. Evidence and verdict land in Section 7.

## 1. Goal And Out-Of-Scope

- **Goal**: prove the richest core level works as shipped on the integrated
  track — a reader can create a project-tier `Image` type, meet the real
  "no load capability" dispatch error, gain a TIFF loader and an Image
  previewer through step triggers, segment the micrograph, argue with the
  result through block config, fix by hand what no method fixes through an
  interactive block, export the per-cell areas, and promote the type, the
  block and the previewer into My Library.
- **Out of scope**: the manifest's prose and pedagogy (content audit); the
  colour-picking invitation in step 3, which the manifest deliberately leaves
  unjudged; levels 1 and 3-6 (their own sessions).

## 2. Preconditions

- **Repo state**: `test/2081-level-e2e-sessions` @ `5ca880d7f` for the runs
  below, re-checked at `c00bb197c` (the tip that adds core tutorial 3)
- **Working tree**: clean apart from the untracked gate ledger
- **Worktree to run from**: `C:/Users/jiazh/workspace/SciStudio-wt-lcE2E`
- **Backend port**: 8032 (a sibling session owns 8031)
- **Frontend mode**: Vite dev server on 5182 with
  `SCISTUDIO_API_PROXY=http://127.0.0.1:8032`
- **Required services / env vars**: backend launched with `USERPROFILE`
  pointed at a short scratch home (`C:/Users/jiazh/lce2e`) so tutorial progress,
  the tutorial parent directory and the user library all start clean, and so
  the preview cache path stays under Windows MAX_PATH (#2116). An earlier run
  used a home under `%TEMP%`; both were tried while diagnosing 7.3.2 and the
  zarr race reproduced under each.
- **Required data / fixtures**: none beyond the tutorial's own assets
  (`assets/data/cells.tif` — a real 120x120 uint8 micrograph)
- **External accounts**: none (`requires.agent: false`)

## 3. Launch Plan

- **Backend start**:
  ```powershell
  $env:USERPROFILE = "C:/Users/jiazh/lce2e"; $env:PYTHONPATH = "./src"
  python -m scistudio.cli.main serve --host 127.0.0.1 --port 8032
  ```
- **Frontend start**:
  ```powershell
  cd frontend; $env:SCISTUDIO_API_PROXY = "http://127.0.0.1:8032"
  npx vite --host 127.0.0.1 --port 5182 --strictPort
  ```
- **Readiness probe**: `GET http://127.0.0.1:8032/api/tutorials/catalogue`
  returns 200
- **Cleanup commands**: kill only the PIDs listening on 8032/5182 (a sibling
  session owns node processes on other ports); delete the scratch home

## 4. Affordances Under Test

- Data types tab — the gap the level opens on (core types, no `Image`)
- New menu → **New data type**, destination "this project", step-prefilled
  filename; the entry action that rewrites the template (FR-059) and the
  registry settling on the write (FR-059a)
- Load block config: `path`, and the dynamic `core_type` enum that must list
  a registered type even before it owns a load capability
- The real dispatch failure — `no load capability is registered for type
  'Image'` — met as a genuine failed run (`run_failed`, `since_step_entry`)
- Step **trigger** buttons (#2061) at steps 7, 9, 10 and 14, each writing a
  real file into the project
- The previewer fallback walking the type chain (number table), then a
  project previewer claiming `target_type: "Image"`
- Block config as an experiment surface: `method` threshold ↔ adaptive, each
  followed by a real run
- The **interactive block**: a run that pauses, a panel window mounted from a
  hand-written ES module the block carries beside it, a decision returned
  through `host.confirm`, and the run resuming (`interaction_completed`)
- Multi-output wiring: `review_labels.areas` (a core `DataFrame`) into Save,
  chosen over the block's other output
- The three promotions into My Library (`library_contains`) from three
  different entry points: E5 type row, E5 palette tile, E1 editor toolbar

## 5. Steps

### Step 1 — Start the level
- **Action**: open the app on a fresh profile, start `what-is-a-type` from
  the Learning Center catalogue
- **Expected**: a tutorial project bootstraps with `data/raw/cells.tif`; the
  step card shows "Step 1 of 22"; the Data types tab lists the core types and
  no `Image`
- **Capture**: screenshot, the rendered type list

### Steps 2-22 — Walk every manifest step in order
- **Action**: perform each step's designed user action exactly as its text
  instructs — New data type keeping the offered filename into this project;
  read the rewritten `types/image.py`; add Load; point it at
  `data/raw/cells.tif` and pick `Image` from the type list; Run and read the
  capability error; press the loader trigger and Run again; click Load and
  meet the number table; press the previewer trigger and click Load again;
  press the segmentation trigger, add Segment Cells and wire Load into it;
  Run and inspect the labels; switch to `adaptive` and Run; switch back to
  `threshold` and Run; press the review trigger, add Review Labels and wire
  the labels output in; Run, remove the nine-pixel intruder in the panel and
  Apply; add Save and wire the **areas** output into it; Browse to
  `data/processed`; Run through the panel once more; then the three "Move to
  My Library" promotions and the closing step
- **Expected**: every judged step flips to satisfied on the reader's own
  action; Continue enables only when the backend says the step is satisfied;
  the capability run genuinely fails; the segmentation genuinely finds seven
  objects where six are cells; the interactive run genuinely pauses and
  resumes; `data/processed/cell_areas.csv` genuinely lands
- **Capture**: screenshot at each beat; console; backend workflow state

### Step 23 — Completion
- **Action**: final Continue on step 22
- **Expected**: the session completes and the catalogue records
  `what-is-a-type` complete
- **Capture**: `GET /api/tutorials/catalogue`, `GET /api/tutorials/unlock`

## 6. Regression Sentinels

- **Console errors**: no uncaught React errors
- **Network errors**: no 5xx
- **Native dialogs**: `alert`/`confirm` never fires
- **Process health**: backend stays up; Vite stays responsive

## 7. Results

### 7.1 Verdict

**FAIL — P1.** 2026-08-22, `test/2081-level-e2e-sessions` @ `5ca880d7f`,
still failing at `c00bb197c` (the merge that added core tutorial 3 does not
touch `src/scistudio/blocks/base/ports.py`, so nothing about this changed).

**This blocker gates two levels, not one.** Core tutorial 3 declares
`requires.tutorials: [what-is-a-type]`, so while tutorial 2 cannot be completed,
tutorial 3 cannot be started by any reader either. See
`2026-08-22-lc-level-3-two-modalities.md`.

**Core tutorial 2 cannot be completed by a real reader.** Step 14
(`add-the-review-block`) requires an edge from Segment Cells to Review Labels,
and the product refuses to create it. The workflow API rejects that edge with
HTTP 422 and a self-contradictory message:

```
Edge 'segment_cells-...:labels' -> 'review_labels-...:labels':
Source port 'labels' produces ['Image'] but target port 'labels' accepts ['Image']
```

Both ports declare the same type. The step's `done_when` can therefore never be
satisfied, and the level stops dead at step 14 of 22 — with the interactive
block, the export, the three My Library promotions and the closing payoff all
behind it.

This is **not a tutorial defect**. It is a core workflow-validation defect that
core tutorial 2 happens to be the first shipped surface to exercise (see 7.3.1).

Reproduced on **three consecutive independent runs** from a clean profile.

### 7.2 How far the level got

Steps 1-13 all behaved as designed, driven by their own designed actions in a
real browser against a live backend:

| Steps | Outcome | Notes |
|-------|---------|-------|
| 1 | pass | Data types tab lists the core types and no `Image` — the gap the level opens on |
| 2 | pass | New → New data type; filename prefilled `image`; destination "this project"; `types/image.py` lands |
| 3 | pass | Entry action rewrites the template; `Image` registers (`type_registered`) |
| 4 | pass | Load added from the palette |
| 5 | pass | `data/raw/cells.tif` + `core_type: Image`. The step's claim that the reader's own Image is in the list **holds**: `["Array","DataFrame","Series","Text","Artifact","CompositeData","DataObject","Image"]` |
| 6 | pass | The wall, met for real: `ValueError: Load: no load capability is registered for type 'Image'.` — the manifest quotes this error verbatim and the product raises it verbatim |
| 7 | pass | Loader trigger writes `blocks/load_tiff_image.py`; the re-run genuinely reads the TIFF |
| 8 | pass | The number-table fallback — the core Array previewer walking the type chain |
| 9 | pass | Previewer trigger writes `previewers/image_preview.py`; `previewer_registered` |
| 10 | pass | Segmentation trigger writes the block; Load → Segment Cells wired and backend-verified |
| 11 | pass | Run + node inspection (`run_succeeded` + `node_selected`) |
| 12 | pass | `method: adaptive` + run — **needed 2 Run presses** (see 7.3.2) |
| 13 | pass | `method: threshold` + run |
| **14** | **FAIL** | Review Labels registers and lands on the canvas, but **the edge Segment Cells → Review Labels is refused** |
| 15-22 | not reached | interactive panel, areas → Save, `data/processed/cell_areas.csv`, the three promotions, the closing step |

### 7.3 Product observations

**1. P1 — the static workflow validator rejects two drop-in blocks that share a
drop-in type.**

`validate_connection` (`src/scistudio/blocks/base/ports.py`, ~line 205) decides
compatibility purely by class identity:

```python
for src_type in source_port.accepted_types:
    if any(
        issubclass(src_type, tgt_type) or issubclass(tgt_type, src_type)
        for tgt_type in target_port.accepted_types
    ):
        return True, ""
```

A by-path drop-in import yields a **distinct class object sharing `__name__`**,
so `issubclass` is false in both directions for two `Image` classes that denote
the same registered type — and the error then prints both sides as `['Image']`,
which is how the contradiction reaches the reader.

This exact failure class was already diagnosed and fixed once, for the
*runtime* path, in **#1950** (`db864299a`, "fix save_data validation
false-reject + runtime by-path type-identity mismatch"). That commit added
`same_registered_type()` (`src/scistudio/core/types/base.py:670`) and applied it
in `port_accepts_type`, whose docstring now claims it is tolerant
*"so runtime validation matches what the static workflow validator accepts"*.
The claim is inverted: the runtime gate was made tolerant and the **static**
gate was left comparing raw identity. `same_registered_type` is exactly the
predicate `validate_connection` needs.

Reproduction against a live server, no browser required, with the tutorial-2
project open at step 14:

```
PUT /api/workflows/main?project_id=<id>
  edges += {"source": "segment_cells-<id>:labels",
            "target": "review_labels-<id>:labels"}
-> 422 {"detail": "Workflow validation failed: Edge ...:
        Source port 'labels' produces ['Image'] but target port 'labels' accepts ['Image']"}
```

Note that an isolated, single-generation registry scan **passes**: the probes
kept in the session scratchpad (`probe_dropin_identity.py`,
`probe_dropin_identity2.py`) resolve both ports to one class object and
`validate_connection` returns `True`. So the identity skew is introduced by the
live server's reload/scan sequence, not by the manifest — which is why the
durable fix is to stop comparing identity in the static validator rather than to
chase the sequence.

Handoff: an implementer, not this persona. No product code was changed here.

**2. P1 (intermittent) — persisting a zarr-backed type dies with `WinError 5`
and fails the whole run.**

Seen live twice, on two different blocks (`load_data`, `segment_cells`) and
under two different profile homes (one under `%TEMP%`, one not — so it is not an
artefact of a scanned temp tree):

```
File "src/scistudio/core/storage/zarr_backend.py", line 104, in write
    Path(tmp_dir).rename(target)
PermissionError: [WinError 5] Access is denied:
    '...\data\zarr\main\<block>\.zarr_tmp_xxxxxxxx'
    -> '...\data\zarr\main\<block>\<hash>.zarr'
=> RuntimeError: auto_flush failed for Image at ...
```

It is a **race, not a deterministic break**: the same block succeeds on a later
attempt. Step 12 of this session needed 2 Run presses for exactly this reason.

Quantified with a standalone reproduction that does not involve SciStudio at
all — write a small directory tree, then rename it into place, in a loop
(`repro_zarr_rename.py`, kept in the session scratchpad):

```
14 failures in 400 publishes (3.50%) in 1.5s
```

3.5% per publish is not rare. A 22-step level with seven runs, each persisting
several outputs, will hit it regularly — and when it does the reader sees a red
failed run on a step whose text promises green, with no explanation and no hint
that simply pressing Run again clears it. `zarr_backend.write` performs the
publish rename with **no retry**; a short bounded retry (the standard Windows
remedy for a transient sharing/scanner handle) would remove it.

Core storage defect. Tutorial 2 exposes it because it is the first level to
persist zarr-backed (Array-family) types — tutorial 1 persists DataFrames to
parquet, a single-file write.

**3. Moderate — after "New data type", the level never brings the canvas back.**

The step-2 dialog opens `types/image.py` as an editor tab. Step 4
(`route_to: block_palette`) and step 5 (`route_to: config`) route the left and
bottom panels, but nothing routes the **main editor area** back to the workflow.
Step 4's text says "Drag a Load block onto the canvas" and step 5's says "Click
the Load block" — while the canvas is hidden behind the `image.py` tab.
Observed directly and logged every run:
`at step 4 the workflow canvas is HIDDEN behind the image.py editor tab`.

Tutorial 1 has the same shape at its step 6 and handles it in copy ("The block
editor opened as a tab; return to the workflow tab"). Tutorial 2 does not, and
the vocabulary already has a `route_to: canvas` target that would do it.
Recoverable — the `main` tab is right there and labelled — so not a blocker, but
it is a dead end the reader has to solve for themselves, twice.

**4. Low — the palette tip card lands on top of the tutorial's own target.**

The rotating palette tip (`palette-tip`, e.g. "Every run is kept") floats over
the block palette while a tutorial step is highlighting a tile in that same
palette and telling the reader to click it (captured in a step-14 screenshot).
Harmless with a mouse — the reader dismisses it — but the product's two guidance
systems are competing for the same screen region at the same moment.

**5. Low — the backend accepts and persists duplicate identical edges.**

The live workflow held the same edge twice:

```
edges: [ {source: 'load_data-...:data', target: 'segment_cells-...:image'},
         {source: 'load_data-...:data', target: 'segment_cells-...:image'} ]
```

This is the persisted counterpart of the React "two children with the same key"
warning recorded in the level-1 session as a DOM-only issue — it is in
`workflows/main.yaml`, so it survives reload and travels with the project. It
also actively hides missing connections from any edge-**count** check (it did so
in the level-6 session before that check was made pair-aware).

**6. Low — the Load block's type list offers `DataObject`.**

Step 5's list was
`["Array","DataFrame","Series","Text","Artifact","CompositeData","DataObject","Image"]`,
and the Data types tab shows the same seven rows. Step 1's text names six core
types. `DataObject` is the abstract base every type descends from; offering it
as a selectable "Type" is at best noise in a level whose whole subject is what a
type is.

**7. By design, recorded for the record — step 3 asks for something it cannot
judge.** Its `done_when` is `type_registered`, already true on entry from the
entry action, so the step arrives satisfied and its actual reader instruction
(uncomment two lines and choose your own colours) is unverified. The manifest
comments say this is deliberate and explain why, and this session did **not**
fake the colour edit. Worth knowing that a reader can press straight through the
level's one piece of self-expression without noticing it.

### 7.4 Sentinels

- No 5xx from the API. The 422 in 7.3.1 is a deliberate validation rejection,
  not a server error — it is the defect, not a sentinel hit.
- Console: the React duplicate-key warning (7.3.5); two `403`s from
  `GET /api/packages/updates` at startup (pre-existing, unrelated to this level,
  seen identically in the level-1 and level-5 sessions).
- `alert`/`confirm` never fired. Backend and Vite stayed up throughout.

### 7.5 Follow-ups

To be filed by the manager — this session changed no product code:

1. **P1** static `validate_connection` must use `same_registered_type`; blocks
   core tutorial 2 at step 14. Precedent: #1950.
2. **P1** `zarr_backend.write` needs a bounded retry around the publish rename;
   intermittently fails whole runs on Windows (~3.5% per publish measured).
3. **Moderate** tutorial 2 steps 4-5 should route back to the canvas
   (`route_to: canvas`) or say so in their text.
4. **Low** suppress the palette tip while a tutorial step highlights the palette.
5. **Low** de-duplicate identical edges on workflow save.
6. **Low** drop `DataObject` from the Load/Save `core_type` enum.
