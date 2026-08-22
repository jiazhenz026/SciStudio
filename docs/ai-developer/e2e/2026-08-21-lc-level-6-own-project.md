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
status: "draft"
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

- **Repo state**: `track/learning-center-levels` @ post-#2114 tip
- **Worktree**: `C:/Users/jiazh/workspace/SciStudio-wt-lc-mgr`
- **Backend**: 8031; **Vite**: 5181; isolated USERPROFILE scratch home

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

## 7. Results (skill fills in)

### 7.1 Verdict

<!-- filled after the run -->
