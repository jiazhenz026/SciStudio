---
session_id: "lc-level-2-what-is-a-type"
title: "Core tutorial 2 (what-is-a-type) walks end to end on the integrated track"
created: "2026-08-22"
owner: "@jiazhenz026"
trigger:
  kind: "feature-sweep"
  ref: "PR #2122 on track/learning-center-levels (#2081); re-verified after the #2134 validator fix"
related_adrs:
  - 53
status: "passed"
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

- **Repo state**: `test/2081-level-e2e-sessions` @ `a7cd4b862`
  (= `track/learning-center-levels` with core tutorial 3 and the #2134 fix).
  The superseded FAIL was observed at `5ca880d7f` and `c00bb197c`.
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

**PASS — 22/22 steps.** 2026-08-22, `test/2081-level-e2e-sessions` @ `a7cd4b862`
(= `track/learning-center-levels` with the #2134 validator fix).

> **This verdict supersedes an earlier FAIL.** On the first tip tested
> (`5ca880d7f`, still failing at `c00bb197c`) this level stopped dead at step 14
> of 22: the workflow API refused the Segment Cells → Review Labels edge with
> `Source port 'labels' produces ['Image'] but target port 'labels' accepts
> ['Image']` (HTTP 422). That was a real P1 and it is now fixed — see 7.3.1 for
> the diagnosis, which the fix confirmed, and which is kept here as provenance.

The level now completes by its own designed actions: the type is created and
registered, the capability error is met and answered, the previewer is written
and takes effect, the segmentation is run and argued with, the interactive block
pauses the run and takes the reader's decision, the areas table is exported, and
all three artefacts are promoted into My Library.

Backend truth after the run:

```
group SciStudio -> completed 1 of 6
    what-is-a-type            = complete      <-- this session
    two-modalities-one-answer = not_started   <-- gate cleared by that completion
```

The tutorial-scoped library afterwards — the whole point of the ending:

```
<home>/SciStudio Tutorials/.library/types/image.py
<home>/SciStudio Tutorials/.library/blocks/segment_cells.py
<home>/SciStudio Tutorials/.library/previewers/image_preview.py
```

`GET /api/tutorials/unlock` → `{"work_import_offer_pending": false}` — correct;
the milestone is tutorial 4.

### 7.2 What ran

Every step was driven by the action its own text asks for, in a real browser
against a live backend, from a clean profile. Wall time 7.1m.

| Steps | Outcome | Notes |
|-------|---------|-------|
| 1 | pass | Data types tab lists the core types and no `Image` — the gap the level opens on |
| 2 | pass | New → New data type, filename prefilled `image`, destination "this project"; `types/image.py` lands |
| 3 | pass | Entry action rewrites the template; `Image` registers (`type_registered`) |
| 4 | pass | Load added from the palette |
| 5 | pass | `data/raw/cells.tif` + `core_type: Image`. The step's claim that the reader's own Image is in the list **holds**: `["Array","DataFrame","Series","Text","Artifact","CompositeData","DataObject","Image"]` |
| 6 | pass | The wall, met for real: `ValueError: Load: no load capability is registered for type 'Image'.` — quoted verbatim by the manifest and raised verbatim by the product |
| 7 | pass | Loader trigger writes `blocks/load_tiff_image.py`; the re-run genuinely reads the TIFF |
| 8 | pass | The number-table fallback — the core Array previewer walking the type chain |
| 9 | pass | Previewer trigger writes `previewers/image_preview.py`; `previewer_registered` |
| 10 | pass | Segmentation trigger writes the block; Load → Segment Cells wired, backend-verified |
| 11 | pass | Run + node inspection; the label map really is computed |
| 12 | pass | `method: adaptive` + run |
| 13 | pass | `method: threshold` + run |
| **14** | **pass** | **Segment Cells → Review Labels now connects** — the edge the old P1 refused |
| 15 | pass | Run pauses on the interactive block, its window opens on the real label map, the nine-pixel intruder is removed by hand, the run resumes (`interaction_completed`) |
| 16 | pass | Save added and the **areas** output (not labels) wired into it |
| 17 | pass | Save pointed at `data/processed`, filename prefilled `cell_areas.csv` |
| 18 | pass | Final run through the panel; **`data/processed/cell_areas.csv` genuinely lands** |
| 19 | pass | `Image` promoted from the Data types tab (E5) — file moves into the library |
| 20 | pass | `segment_cells` promoted from the palette (E5) |
| 21 | pass | `image_preview.py` opened from the project tree and promoted from the editor toolbar (E1) |
| 22 | pass | Closing step; session completes |

The interactive block was exercised twice (steps 15 and 18) and behaved
identically both times: seven labels, one of them the nine-pixel debris speck,
`Apply (remove 1)`, run resumes, six rows written.

Evidence: step screenshots `t2-01-data-types.png` … `t2-22-final.png` under the
session scratchpad `pw-artifacts/`; driver `tutorial2.live.ts` in the
out-of-repo harness.

### 7.3 Product observations

**1. P1, FIXED and verified — the static workflow validator rejected two drop-in
blocks that shared a drop-in type.**

> Fixed on the track in `34b7b9eea` (issue #2134) after this session reported it:
> `validate_connection` now falls back to `same_registered_type` when
> `issubclass` says no, so two by-path imports of one project type connect while
> genuinely different types still refuse — both pinned by new tests in
> `tests/blocks/test_port_subclass.py`. Re-verified live here: step 14 connects
> and the level completes. The diagnosis below is kept as provenance.

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
and fails the whole run. Evidence for #2047.**

> Recorded here in full, with its reproduction inline, because #2047 has been
> carried as a *flaky test*. This is not flaky-test behaviour: it is a missing
> retry around a non-atomic Windows directory rename in the storage layer, and
> it fails real runs in front of real readers. The numbers below are the
> measurement to cite.

Seen live twice during this session, on two different blocks (`load_data`,
`segment_cells`) and under two different profile homes — one under `%TEMP%`, one
not — so it is not an artefact of a heavily scanned temp tree:

```
File "src/scistudio/core/storage/zarr_backend.py", line 104, in write
    Path(tmp_dir).rename(target)
PermissionError: [WinError 5] Access is denied:
    '...\data\zarr\main\<block>\.zarr_tmp_xxxxxxxx'
    -> '...\data\zarr\main\<block>\<hash>.zarr'
=> RuntimeError: auto_flush failed for Image at ...
```

It is a **race, not a deterministic break**: the same block succeeds on a later
attempt. Step 12 of this session needed 2 Run presses for exactly this reason —
which is also why it reads as flakiness from a test's point of view.

**Mechanism.** `zarr_backend.write` publishes a store by building it in a
`.zarr_tmp_*` directory and then renaming that directory into place. On Windows
`os.rename` of a *directory* fails with `WinError 5` (ACCESS_DENIED) whenever
anything still holds a handle inside it — an indexer, a scanner, or the writer's
own not-yet-closed file objects. The call has **no retry**, so a transient
handle becomes a failed block, a failed run, and an unsatisfiable tutorial step.

**Measurement.** Reproduced with a standalone script that does not import
SciStudio at all — it performs the same publish shape (write a small directory
tree, then rename it next to its siblings) in a loop:

```
14 failures in 400 publishes (3.50%) in 1.5s
```

Run against `C:\Users\jiazh\lce2e-zarrrepro` (deliberately **not** under
`%TEMP%`), Windows 11, this repository's Python. Every failure was `WinError 5`
on the rename; none were on the writes.

<details>
<summary>Reproduction script (self-contained; imports no SciStudio code)</summary>

```python
"""Reproduce the intermittent zarr-store publish failure on Windows (#2047).

Drives the same publish shape ZarrBackend.write uses -- build a directory tree,
then rename it into place beside its siblings -- and reports how often the
rename fails.

Usage:  python repro_zarr_rename.py [iterations] [root]
"""
from __future__ import annotations

import os
import secrets
import sys
import time
from pathlib import Path


def publish_once(parent: Path) -> None:
    """One write-then-rename publish, shaped like ZarrBackend.write."""
    tmp = parent / f".zarr_tmp_{secrets.token_hex(4)}"
    tmp.mkdir(parents=True, exist_ok=False)
    # A zarr store is a directory of small files; write a few.
    (tmp / "zarr.json").write_text('{"zarr_format":3,"node_type":"group"}', encoding="utf-8")
    chunks = tmp / "c"
    chunks.mkdir()
    for i in range(8):
        (chunks / str(i)).write_bytes(os.urandom(4096))
    target = parent / f"{secrets.token_hex(6)}.zarr"
    Path(tmp).rename(target)          # <-- the call that intermittently raises


def main() -> int:
    iterations = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    root = Path(sys.argv[2] if len(sys.argv) > 2 else "./zarr-repro").resolve()
    parent = root / "main" / "block-0"
    parent.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    started = time.time()
    for i in range(iterations):
        try:
            publish_once(parent)
        except OSError as exc:            # WinError 5, and WinError 183 friends
            failures.append(f"iter {i}: {type(exc).__name__}: {exc}")
            print(f"FAIL iter {i}: {exc}")

    elapsed = time.time() - started
    print(
        f"\n{len(failures)} failures in {iterations} publishes "
        f"({100 * len(failures) / iterations:.2f}%) in {elapsed:.1f}s"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

</details>

**Why the rate matters.** 3.5% per publish is not rare. A run persists one store
per block output, and this level has seven runs; the chance a 22-step reader
gets through without meeting it is small. When they do meet it they see a red
run on a step whose text promises green, with no explanation and no hint that
pressing Run again clears it.

**Suggested fix.** A short bounded retry with a small backoff around the publish
rename — the standard Windows remedy for a transient sharing violation — plus
closing any store handles before the rename. That turns a failed run into a few
milliseconds of delay.

Core storage defect, not a Learning Center one. Tutorial 2 is simply the first
shipped surface that persists zarr-backed (Array-family) types; tutorial 1
persists DataFrames to parquet, a single-file write that never takes this path.

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

**8. P2 (new) — the interactive block's panel is mounted twice into one
container, and the leak is not only a dev-mode artefact.**

Observed on every run of steps 15 and 18:

```
OBS t2-15 interactive panel mounted 2 times into one container
```

The Review Labels window then shows **every label twice** and carries **two
Apply buttons**. A reader can still finish — the second (live) panel works —
but they are looking at a dialog that lists fourteen objects when the run found
seven, in a step whose entire lesson is "seven objects, six cells".

Mechanism, in `App.parts/InteractiveModals.parts/DynamicPanel.tsx`:

```ts
void mountDynamicPanel(manifest, container, host, importer).then((result) => {
  if (disposed) return;                 // <-- drops the instance on the floor
  if (result.ok) instanceRef.current = result.instance;
  ...
});
return () => {
  disposed = true;
  if (instanceRef.current) { instanceRef.current.unmount(); ... }   // still null
};
```

The mount is asynchronous. When the effect is torn down before the promise
resolves, cleanup runs while `instanceRef.current` is still `null`, so it
unmounts nothing; the promise then resolves, sees `disposed`, and returns
**without unmounting the DOM the panel module has already appended**. The first
panel is orphaned in the container and the second mount appends beside it.

`React.StrictMode` (enabled in `main.tsx`) makes this deterministic in dev by
running every effect mount→unmount→mount, which is why it reproduces every time
under the dev server. But the leak is not caused by StrictMode: any unmount that
beats the mount promise does it — a reader who cancels quickly, or a prompt
superseded by another. StrictMode is the microscope, not the disease.

Fix: unmount in the `disposed` branch rather than returning, i.e.
`if (disposed) { if (result.ok) result.instance.unmount(); return; }`.

### 7.4 Sentinels

- No 5xx from the API. The 422 in 7.3.1 is a deliberate validation rejection,
  not a server error — it is the defect, not a sentinel hit.
- Console: the React duplicate-key warning (7.3.5); two `403`s from
  `GET /api/packages/updates` at startup (pre-existing, unrelated to this level,
  seen identically in the level-1 and level-5 sessions).
- `alert`/`confirm` never fired. Backend and Vite stayed up throughout.

### 7.5 Follow-ups

Filed / to be filed by the manager — this session changed no product code:

1. ~~**P1** static `validate_connection` must use `same_registered_type`~~ —
   **fixed** in `34b7b9eea` (#2134) and re-verified live here.
2. **P1** `zarr_backend.write` needs a bounded retry around the publish rename.
   Evidence and a standalone reproduction are in 7.3.2 — this is the measurement
   for **#2047**, which has been carried as a flaky test rather than a product
   defect. Across the runs in this session it forced extra Run presses at steps
   7, 11, 12 and 13, and once consumed a whole 25-minute test budget.
3. **P2** `DynamicPanel` leaks its panel when the mount promise resolves after
   unmount, so the interactive window renders twice (7.3.8).
4. **Moderate** tutorial 2 steps 4-5 should route back to the canvas
   (`route_to: canvas`) or say so in their text (7.3.3).
5. **Low** suppress the palette tip while a tutorial step highlights the palette.
6. **Low** de-duplicate identical edges on workflow save.
7. **Low** drop `DataObject` from the Load/Save `core_type` enum.
