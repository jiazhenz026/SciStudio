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
status: "passed"
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

- **Repo state**: `test/2081-level-e2e-sessions` @ `c00bb197c`
  (= `track/learning-center-levels` with all six core tutorials)
- **Worktree to run from**: `C:/Users/jiazh/workspace/SciStudio-wt-lcE2E`
- **Backend port**: 8032; **Frontend**: Vite 5182 with SCISTUDIO_API_PROXY
  (a sibling session owns 8031/5181)
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

## 7. Results

### 7.1 Verdict

**PASS** — 2026-08-22, `test/2081-level-e2e-sessions` @ `c00bb197c`
(= `track/learning-center-levels` with all six core tutorials integrated).
First run on `5ca880d7f`; re-run unchanged on `c00bb197c` after core tutorial 3
landed, which is the result recorded below.

Playwright (chromium, a real browser) drove the whole reading level against a
live `scistudio serve` backend on an isolated profile home. 8/8 cards, 34/34
pages, no page errors, no 5xx. Total wall time 23.6s.

### 7.2 What ran

Learning Center opens on the fresh profile → the reading tutorial is started
from the catalogue → the **reading window** opens (and the floating step card
does **not**, asserted explicitly) → the top sentence renders the manifest
`summary` → the grid names **all eight cards up front** → each card is opened
in turn and every one of its pages is paged through to the end → the last page
offers "Back to the cards" and returns to the grid → Continue lights up only
once the backend agrees the card's whole page set was served → the eighth card
completes the tutorial.

Assertions that carry the verdict:

- Card names visible before any reading, in manifest order:
  `["Workflow","Block","Data type","Previewer","Plot card","History","My library","Others"]`
  — this is the session steps outline doing its job; without it the unread
  slots would render as "Card 5", "Card 6", …
- Initial card states: `["current","unread","unread","unread","unread","unread","unread","unread"]`
  — named but not openable, so the reader cannot skip ahead.
- Per-card page counts observed and matched against the manifest:
  4, 4, 4, 4, 5, 5, 3, 5 = **34 pages**, every one rendered (asserted not to
  be left on the "Loading…" state, and `reading-page-error` asserted hidden).
- `Continue` was disabled until the last page of each card had been served,
  then enabled — i.e. the step is judged on `page_reached`, not on the click.

Backend truth after the run — `GET /api/tutorials/catalogue`:

```
group SciStudio -> completed 1 of 6
    scistudio-at-a-glance     = complete      <-- this session
    welcome-to-scistudio      = not_started
    what-is-a-type            = not_started
    two-modalities-one-answer = unavailable   (needs what-is-a-type first)
    what-ai-can-do            = not_started
    start-your-own-project    = not_started
```

`GET /api/tutorials/unlock` → `{"work_import_offer_pending": false}` — correct:
the milestone is tutorial 4, and a reading level must not move it.

The reading tutorial created **no project**, as designed (no `bootstrap`).

Evidence: `t5-00-catalogue.png`, `t5-01-grid.png`, `t5-02-first-page.png`,
`t5-03-all-read.png` under the session scratchpad `pw-artifacts/`; driver
`tutorial5.live.ts` in the out-of-repo harness.

### 7.3 Product observations

1. **A finished card shows no tick until Continue is pressed** (severity: low,
   cosmetic). A card's `data-reading-state` stays `current` after the reader
   reaches its last page and returns to the grid; the ✓ appears only once
   Continue advances to the next card. The observed state after finishing each
   card was `current` for all eight. The Continue button lighting up is the
   real signal and it is unambiguous, so nothing is blocked — but the tick is
   the affordance a reader's eye goes to, and it lags the thing it reports.
2. **No 5xx, no uncaught page errors** across the session (`pageErrors: []`).
   The only console noise is two `403` responses from
   `GET /api/packages/updates` at startup, which is pre-existing and unrelated
   to this level (seen identically in the level-1 and level-2 sessions).

### 7.4 Sentinels

None fired. Backend and Vite stayed up; `alert`/`confirm` never fired.
