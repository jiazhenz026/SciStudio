---
session_id: "lc-level-5-summary"
title: "Core tutorial 5 (scistudio-at-a-glance) reading window walks end to end"
created: "2026-08-21"
owner: "@jiazhenz026"
trigger:
  kind: "feature-sweep"
  ref: "PR #2109 on track/learning-center-levels (#2084)"
related_adrs:
  - 53
status: "draft"
language_source: en
---

# E2E Session — Tutorial 5 reading window

> Driven by Playwright (chromium, real browser) against a live backend with an
> isolated USERPROFILE, per the manager checklist. The implementing agent's own
> live verification (13/13 Playwright checks) preceded this; this session is the
> manager's independent pass on the integrated track.

## 1. Goal And Out-Of-Scope

- **Goal**: prove the reading level works as shipped on the track: the
  catalogue lists it in the Reading tab, starting it opens the reading window
  (not the floating card), the 8 cards are named up front via the session
  steps outline, a card's pager serves every page (recording page_reached),
  steps advance card-by-card, and completing all cards completes the tutorial.
- **Out of scope**: content accuracy of the 34 pages (audited separately);
  levels 1-4/6.

## 2. Preconditions

- **Repo state**: `track/learning-center-levels` @ post-#2109 tip
- **Worktree to run from**: `C:/Users/jiazh/workspace/SciStudio-wt-lc-mgr`
- **Backend port**: 8031; **Frontend**: Vite 5181 with SCISTUDIO_API_PROXY
- **Env**: isolated USERPROFILE scratch home (fresh progress)

## 3. Launch Plan

Same harness as the level-1 session (`run-lc-e2e.sh` pattern): reset scratch
home → backend serve → vite → Playwright spec.

## 4. Affordances Under Test

- Learning Center Reading tab; Start on the reading tutorial
- ReadingSurface window: top sentence, 2×4 card grid with all names visible
- Paged reader: page fetch → page_reached; last page returns to grid
- Card state (satisfied) reflection; Continue/advance flow; completion

## 5. Steps

### Step 1 — Start from the Reading tab
- **Action**: open the Learning Center, switch to the Reading tab, start
  scistudio-at-a-glance
- **Expected**: the reading window renders (not the floating step card); top
  sentence shown; 8 cards named: Workflow, Block, Data type, Previewer,
  Plot card, History, My library, Others
- **Capture**: screenshot

### Step 2 — Read the first card fully
- **Action**: open the Workflow card; page through all 4 pages
- **Expected**: each page renders markdown; the backend records page_reached
  (step satisfied after the last page); reader returns to the grid; card
  shows done state
- **Capture**: screenshot

### Step 3 — Walk the remaining 7 cards
- **Action**: repeat for Block(4), Data type(4), Previewer(4), Plot card(5),
  History(5), My library(3), Others(5)
- **Expected**: every step satisfies exactly when its page set is exhausted

### Step 4 — Complete
- **Action**: advance through the final continue
- **Expected**: session completes; catalogue records the tutorial complete;
  reading tutorials carry no group count regression
- **Capture**: screenshot, catalogue API response

## 6. Regression Sentinels

- No uncaught page errors; no 5xx; backend and vite stay up.

## 7. Results (skill fills in)

### 7.1 Verdict

<!-- filled after the run -->
