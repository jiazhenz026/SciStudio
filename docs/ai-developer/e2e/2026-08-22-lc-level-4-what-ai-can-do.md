---
session_id: "lc-level-4-what-ai-can-do"
title: "Core tutorial 4 (what-ai-can-do) walks end to end and fires the work-import milestone"
created: "2026-08-22"
owner: "@jiazhenz026"
trigger:
  kind: "feature-sweep"
  ref: "PR #2118 on track/learning-center-levels (#2083)"
related_adrs:
  - 53
status: "passed"
language_source: en
---

# E2E Session — Tutorial 4 scripted AI replay

> Chrome MCP is not connected in this session; the run is driven by Playwright
> (chromium, a real browser) against a live backend, per the manager checklist.

## 1. Goal And Out-Of-Scope

- **Goal**: prove the declared-fake AI level does what it claims — each reader
  press plays the next scripted reply into ONE terminal tab; every claim the
  transcript makes is matched by real project state landing before the claim is
  readable; the planted `KeyError` run genuinely fails and the agent's fix
  genuinely succeeds; and completing the level fires the work-import milestone
  (FR-079) with the provider introduction ahead of the import question.
- **Out of scope**: the transcript's prose (content audit); real agent
  providers (`requires.agent: false` — the whole point of the fake); the
  Bring-in-my-work dialog's own pages (#2086's surface).

## 2. Preconditions

- **Repo state**: `test/2081-level-e2e-sessions` @ `c00bb197c`
  (= `track/learning-center-levels` including core tutorial 3)
- **Worktree**: `C:/Users/jiazh/workspace/SciStudio-wt-lcE2E`
- **Backend**: 8032; **Vite**: 5182 (a sibling session owns 8031/5181)
- **Env**: isolated short-path `USERPROFILE` (`C:/Users/jiazh/lce2e`), wiped
  before the run so progress, the tutorial parent dir and the library start
  clean, and so the preview cache stays under Windows MAX_PATH (#2116)
- **External accounts**: none, by design

## 3. Launch Plan

- Backend: `USERPROFILE=<scratch> PYTHONPATH=./src python -m scistudio.cli.main serve --host 127.0.0.1 --port 8032`
- Frontend: `SCISTUDIO_API_PROXY=http://127.0.0.1:8032 npx vite --host 127.0.0.1 --port 5182 --strictPort`
- Readiness: `GET /api/tutorials/catalogue` returns 200
- Cleanup: kill only the PIDs listening on 8032/5182; delete the scratch home

## 4. Affordances Under Test

- Step **trigger** buttons driving a `replay` (9 replies, `continue_tab`)
- Replay tab adoption (`session.replay.tab_id` → a `tutorial-replay` terminal
  tab) and the WebSocket that carries the scripted bytes
- Bound writes landing before the reply is readable (FR-061b): block sources,
  `workflows/main.yaml`, plot scaffold, `data/agent_log/*.txt`
- `block_registered`, `node_exists`/`edge_exists`, `run_failed`/`run_succeeded`
  with `since_step_entry`, `ui_event: node_selected`, `config_equals`,
  `plot_rendered`
- The AI Block beat (a real `AIBlock` subclass with a canned run)
- FR-079: the work-import milestone, the provider introduction, and the
  permanent "Bring in my work" toolbar entry

## 5. Steps

### Step 1 — Start and read the honesty step
- **Action**: start `what-ai-can-do` on a fresh profile
- **Expected**: project bootstraps; step 1 of 14 explains the session is a
  recording
- **Capture**: screenshot

### Steps 2-13 — Press each beat in order
- **Action**: press each step's trigger, then perform the reader action the
  step asks for (Run; click the QC node; type `sigma_threshold` = 2; Run;
  render the plot; Run the AI Block)
- **Expected**: the replay appends into ONE tab; the palette, the canvas, the
  run outcomes, the table, the figure and the AI Block output are all real
- **Capture**: screenshots, backend graph, console

### Step 14 — Completion and the milestone
- **Action**: final Continue
- **Expected**: the tutorial records complete; `work_import_offer_pending`
  flips to true; the provider introduction is shown BEFORE the import question
- **Capture**: `GET /api/tutorials/unlock`, screenshots, DOM hit-test

## 6. Regression Sentinels

- No uncaught page errors; no 5xx; `alert`/`confirm` never fires; backend and
  Vite stay up.

## 7. Results

### 7.1 Verdict

**PASS, with two product defects worth fixing before this level ships as the
milestone.** 2026-08-22, `test/2081-level-e2e-sessions` @ `c00bb197c`.

All 14 steps completed by their own designed actions, every judged condition
satisfied by real product state, and the milestone fired. But the level's two
signature moments are both delivered somewhere the reader is not looking:

- the scripted session plays in the **Terminal** surface while every replay
  step routes the reader to **AI Chat** (7.3.1), and
- the provider introduction the closing step promises is mounted **underneath
  the Learning Center window** and is invisible until the reader closes it
  (7.3.2).

Neither blocks completion. Both defeat the point of the beat they belong to.

### 7.2 What ran

Fresh profile → start `what-ai-can-do` → the honesty step → nine trigger
presses, each playing the next reply → the reader's own Run, node click,
threshold edit, plot render and AI Block run → final Continue. Wall time 3.3m.

Every claim the transcript makes was checked against product truth, not against
the transcript:

| Beat | Checked | Result |
|------|---------|--------|
| reply 1-2 | the replay tab exists and reply 2 appends to it | ONE `Scripted AI session` tab across both (`continue_tab` works) |
| reply 3 | the palette really gains QC Outlier Filter | `palette_block[qc_outlier_filter]` visible; `block_registered` satisfied |
| reply 4 | the canvas really changes | backend graph **0 nodes/0 edges → 4 nodes/3 edges**; all four block types present on the canvas |
| step 6 | the planted `KeyError` really fails the run | `run_failed` (`since_step_entry`) satisfied — the run genuinely went red |
| step 8 | the agent's fix really works | `run_succeeded` (`since_step_entry`) satisfied on the same graph |
| step 9 | the reader's own look is required | step needed BOTH the bound log write and `node_selected` on the QC node |
| step 10 | the reader decides, not the agent | `config_equals sigma_threshold = 2` satisfied only after the value was typed |
| step 12 | the figure really renders | `plot_rendered[qc_before_after]` satisfied |
| step 13 | the AI Block is real | `tutorial_ai_agent` node present; `run_succeeded` scoped to that block |

Backend truth after the run:

```
group SciStudio -> completed 1 of 6
    what-ai-can-do = complete
GET /api/tutorials/unlock -> {"work_import_offer_pending": true}
```

The milestone fired. On a profile where tutorial 4 had **not** been completed
the same endpoint read `false` before the run, so the flip is attributable to
this completion.

Ordering of the milestone UI, watched for 45s in the same page session (both
are transient, so a reload cannot be used to observe them):

```
t+0s   provider-intro=0  work-import-dialog=0
t+3s   provider-intro=1  work-import-dialog=0
...    provider-intro=1  work-import-dialog=0   (stable to t+42s)
```

The introduction appears and the import question does **not** appear before it —
the FR-079 ordering is correct. (An earlier probe that checked only at t+0s
reported "no intro"; that was the probe being three seconds early, not the
product. Recorded here because it is exactly the kind of false negative this
beat invites.)

Evidence: `t4-01-welcome.png`, `t4-02-terminal-surface.png`, `t4-04-qc-block.png`,
`t4-05-assembled.png`, `t4-06-broken.png`, `t4-08-green.png`, `t4-09-qc-table.png`,
`t4-10-sigma-2.png`, `t4-12-plot.png`, `t4-13-ai-block.png`,
`t4-15-provider-intro.png`, `t4-15b-intro-after-lc-closed.png`,
`t4-17-after-completion.png` under the session scratchpad `pw-artifacts/`;
driver `tutorial4.live.ts` in the out-of-repo harness.

### 7.3 Product observations

**1. P1 — the scripted session plays in the Terminal surface, but every replay
step sends the reader to AI Chat.**

Measured directly, right after the first reply:

```
OBS replay tab location: AI Chat surface=0, Terminal surface=1;
     terminal strip=["main *","Scripted AI session×"]
```

The chain is visible in the source and matches the measurement:

- `adoptTutorialReplayTab` (`store/terminalTabsSlice.ts`) creates the tab with
  `provider: USER_TERMINAL_PROVIDER` — deliberately, and the comment explains
  why: the WS query validates the provider against a whitelist.
- `TerminalTabs.tabBelongsToSurface` (`components/AIChat/TerminalTabs.tsx`)
  routes tabs by exactly that field: the `terminal` surface takes
  `provider === "user-terminal"`, the AI Chat surface takes everything else.
- So the replay tab belongs to the **Terminal** surface — while
  `useTutorialReplayTab` calls `openBottomTab("ai")`, every replay step declares
  `route_to: ai_chat`, and step 2's copy says *"The reply appears in the AI Chat
  terminal below"*.

What the reader gets on pressing the first button: the AI Chat panel opens on a
**"Choose provider…" setup screen** — the one thing the level opens by promising
they will not have to configure. The transcript is one tab away, in Terminal,
and nothing points there.

The tab itself is healthy: the WebSocket opens against the right id
(`/api/ai/pty/<replay tab id>?…&provider=user-terminal`) and `continue_tab`
correctly appends replies 2-9 into that one tab.

Fix is a routing decision, not a mechanism change: either the replay tab needs a
surface that follows its `source: "tutorial-replay"` rather than its `provider`,
or the steps should route to `terminal`. The first keeps the manifests and the
copy honest.

**2. P2 — the provider introduction is mounted underneath the Learning Center
and is invisible until the reader closes it.**

Hit-tested at its own centre, 3s after the final Continue:

```
provider intro hit-test: {"box":{"w":414,"h":322},
                          "topmostAtCentre":"tutorial-detail",
                          "coveredByLC":true}
after closing the Learning Center:
                         {"topmostAtCentre":"provider-intro","covered":false}
```

`WorkImportOffer` (App.tsx:601) and `LearningCenter` (App.tsx:604) are both
`fixed inset-0 z-50`. Equal z-index resolves in DOM order, and the Learning
Center is rendered second — so it paints over the offer. On completion the
Learning Center reopens showing "What AI can do — Complete", and the promised
introduction sits behind it, full size, untouched.

It is recoverable **in that session**: closing the Learning Center reveals it.
It is not recoverable afterwards — on a fresh page load with
`work_import_offer_pending` still `true`, the offer overlay does not mount at
all (`work-import-offer=0`), so a reader who closes the app instead of the
Learning Center never sees the one-time offer. The flag stays `true`
indefinitely, and the permanent "Bring in my work" toolbar entry — which is
present, as the closing step promises — becomes the only route.

**3. Low — no page errors at all.** `pageErrors: []` across the whole 14-step
run, including nine replay presses, four real engine runs and a plot render.
Worth recording because the level touches more moving parts than any other.

**4. Low — the pre-existing startup `403`s** from `GET /api/packages/updates`
appear here too (twice, at load). Unrelated to this level; noted in the level-1,
level-2, level-5 and level-6 sessions as well, so it is a product-wide startup
observation rather than anything the Learning Center introduces.

### 7.4 Sentinels

None fired. No 5xx; no uncaught page errors; `alert`/`confirm` never fired;
backend and Vite stayed up throughout.

### 7.5 Follow-ups

To be filed by the manager — this session changed no product code:

1. **P1** route the scripted replay tab by its `source` (`tutorial-replay`)
   rather than its `provider`, so it lands in the AI Chat surface the steps and
   the copy send the reader to.
2. **P2** raise the work-import offer above the Learning Center (or close/defer
   the Learning Center when the offer fires), and make the offer re-mountable
   while `work_import_offer_pending` is true so it is not lost on reload.
