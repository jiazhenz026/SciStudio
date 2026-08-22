---
session_id: "lc-level-1-regression"
title: "Tutorial 1 (welcome-to-scistudio) still completes end-to-end after the P1 vocabulary batch"
created: "2026-08-21"
owner: "@jiazhenz026"
trigger:
  kind: "regression-check"
  ref: "track/learning-center-levels after PR feat/2061-tutorial-step-vocabulary merges"
related_adrs:
  - 53
status: "passed"
language_source: en
---

# E2E Session — Tutorial 1 regression after the vocabulary batch

> Chrome MCP is not connected in this session; the run is driven by
> Playwright (chromium, real browser) against a live backend, per the
> manager checklist. Evidence and verdict land in Section 7 as usual.

## 1. Goal And Out-Of-Scope

- **Goal**: prove the P1 runtime changes (step trigger, vocabulary
  extensions, ui_event targets, session steps outline) did not break the one
  shipped tutorial: welcome-to-scistudio starts, every step advances by its
  designed condition, and completion is recorded.
- **Out of scope**: the new vocabulary's own behaviour (covered by P1's unit
  tests); levels 2-6; the reading surface (tested in the L5 session).

## 2. Preconditions

- **Repo state**: `track/learning-center-levels` @ post-P1-merge tip
- **Working tree**: clean (manager umbrella worktree)
- **Worktree to run from**: `C:/Users/jiazh/workspace/SciStudio-wt-lc-mgr`
- **Backend port**: 8031 (non-default, avoids the owner's own GUI)
- **Frontend mode**: Vite dev server on 5181 with
  `SCISTUDIO_API_PROXY=http://127.0.0.1:8031`
- **Required services / env vars**: backend launched with `USERPROFILE`
  pointed at a scratch dir so tutorial progress, the tutorial parent dir,
  and the user library start clean
- **Required data / fixtures**: none beyond the tutorial's own assets
- **External accounts**: none (tutorial 1 is zero-config by design)

## 3. Launch Plan

- **Backend start**:
  ```powershell
  $env:USERPROFILE = "<scratch>\lc-e2e-home"; $env:PYTHONPATH = "./src"
  python -m scistudio.cli.main serve --host 127.0.0.1 --port 8031
  ```
- **Frontend start**:
  ```powershell
  cd frontend; $env:SCISTUDIO_API_PROXY = "http://127.0.0.1:8031"
  npm run dev -- --host 127.0.0.1 --port 5181
  ```
- **Readiness probe**: GET http://127.0.0.1:8031/api/health returns ok
- **Cleanup commands**: stop the two dev processes; delete the scratch home

## 4. Affordances Under Test

- Learning Center window — catalogue lists welcome-to-scistudio; Start
- Tutorial floating step card — say text, Check again, Continue gating
- Canvas palette drag (load_data), config panel Browse + core_type/format
- New custom block flow with prefilled name; block palette refresh after the
  tutorial's entry-action write
- Save block config; Run; previewer node_selected ui_event
- Plots tab: new plot with prefilled name; plot run; plot_rendered
- The scripted break (entry-action write) → run failure → History Restore →
  block re-registration → final run
- Completion: progress recorded; step card closes; no work-import offer
  (milestone unset until L4 merges)

## 5. Steps

### Step 1 — Launch and first-run landing
- **Action**: open http://127.0.0.1:5181 in the Playwright-driven Chrome
- **Expected**: app loads; Learning Center opens (fresh profile has no
  progress); catalogue shows the core group with welcome-to-scistudio
- **Capture**: screenshot

### Step 2 — Start tutorial 1
- **Action**: click the tutorial row, press Start
- **Expected**: POST /sessions returns the active session; a tutorial
  project is created; the step card shows "Welcome"
- **Capture**: screenshot, network

### Step 3..16 — Walk every manifest step in order
- **Action**: perform each step's designed user action exactly as the step
  text instructs (drag Load; select it; Browse to
  data/raw/cell_viability_fluorescence.csv + CSV format; New custom block
  keeping the offered name; drag Normalize Fluorescence + connect; drag Save
  + connect; Browse to data/processed; Run; click the block (previewer);
  New plot bound to normalized output; Run the plot; Run after the scripted
  break and watch it fail; History → select the earlier run → Restore; Run
  again; final Continue)
- **Expected**: each judged step flips to satisfied WITHOUT pressing Check
  again where an event mapping exists; Continue enables only when the
  backend says satisfied; the break step genuinely fails the run; Restore
  re-registers the block
- **Capture**: screenshot at each step boundary; console; failed-run log

### Step 17 — Completion
- **Action**: final Continue on the last step
- **Expected**: session completes; progress shows 1 completed in the core
  group; the Learning Center does NOT auto-reopen on a reload (the #2079
  fix, folded into this track); no work-import offer appears
- **Capture**: screenshot, GET /api/tutorials/unlock response

## 6. Regression Sentinels

- **Console errors**: no uncaught React errors
- **Network errors**: no 5xx; /api/tutorials/* stays 2xx/404-by-design
- **Native dialogs**: alert/confirm never fires
- **Process health**: backend stays up; Vite stays responsive

## 7. Results

### 7.1 Verdict

**PASS** (product behaviour) — 2026-08-22, track/learning-center-levels @ 7ec90e8ec
(post P1/P2/L4/L5/L6 integration).

### 7.2 What ran

Playwright (chromium, real browser) drove the full 16-step walkthrough against
a live `scistudio serve` backend on an isolated short-path USERPROFILE and a
Vite dev server: LC auto-open on fresh profile → Start → welcome → palette add
Load → select → config path+CSV via typed input (product-equivalent to Browse;
done_when judges config state) → New custom block with the step-prefilled name
into this project → back to the workflow tab → palette add the new block →
click-connect Load→Normalize (backend-verified) → add Save, connect
(backend-verified) → Save config data/processed (filename prefilled) → real
engine run → node-select previewer (real DataFrame preview) → New plot
(prefilled name, bound to normalized output) → Create → plot card Run → real
figure rendered (bar chart observed) → scripted break → run fails as designed
→ History → earlier completed run → Restore (advisory checks observed, confirm
after they finish) → block re-registered → final run → finish.

Backend truth after the run: `GET /api/tutorials/catalogue` → core group
**completed: 1 of 4**; `GET /api/tutorials/unlock` →
`{"work_import_offer_pending": false}` (correct — the milestone is tutorial 4).
Completion UI verified visually: LC reopens, Welcome shows Complete, ring 1/4.

Evidence: step screenshots under the session scratchpad `pw-artifacts/`
(00-learning-center … 14-restored, completion frame); driver spec
`frontend/e2e-live/tutorial1.live.ts` (untracked harness in the manager
worktree).

### 7.3 Product observations recorded for audit

1. Transient unhandled rejection `Unknown block type: my_block` between the
   New-custom-block template write and the tutorial's overwrite (page error,
   self-heals). To file.
2. React duplicate-key warning for canvas edges when an edge is created twice
   (`source:port->target:port` used as key). To file.
3. A rapid scripted edit sequence can lose a just-drawn edge to the
   autosave/version race (#1891 class); the harness works around it by
   verifying edges against the backend. To file with repro notes.
4. Preview-cache paths exceed Windows MAX_PATH under deep homes — filed as
   #2116 during this session.
5. Harness-level: after session completion (and in left-session states), the
   automation protocol channel can wedge (expect/page.request hang) while the
   page itself stays healthy; product UI verified fine visually. Automation
   artifact — final verification moved outside the browser.

### 7.4 Sentinels

No 5xx after the #2116 path fix; the only page error is observation 1;
backend and Vite stayed up throughout.
