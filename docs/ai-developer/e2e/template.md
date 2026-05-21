---
session_id: "<short-kebab-name; matches filename without .md>"
title: "<one-line goal of this e2e run>"
created: "YYYY-MM-DD"
owner: "@jiazhenz026"
trigger:
  kind: "<one of: pr-readiness | hotfix-repro | feature-sweep | regression-check>"
  ref: "<PR #N, issue #N, branch name, or ADR-NNN>"
related_adrs:
  - <ADR number(s) that govern the scope under test, or omit if none>
status: "<draft | running | passed | failed | aborted>"
language_source: en
---

# E2E Session — <short title>

> **How to use this file.** Fill the sections below before invoking the
> `scistudio-e2e-test` skill. Anything you leave as `TODO` will block the run.
> The skill reads this file top-to-bottom and executes Section 5 step by step.
> The skill writes back into Section 7 (Results) — leave it empty.

## 1. Goal And Out-Of-Scope

- **Goal**: <one sentence — what does a green run prove?>
- **Out of scope**: <list scenarios that look adjacent but are not tested here>

## 2. Preconditions

- **Repo state**: <branch + commit SHA expected, e.g. "main @ 9591de29" or
  "PR #1234 head">
- **Working tree**: <"clean" | acceptable dirty paths>
- **Worktree to run from**: <`.` for main, or
  `.claude/worktrees/<name>` if avoiding parallel-session collision>
- **Backend port**: <e.g. 8000 or a non-default to avoid colliding with
  user's own GUI>
- **Frontend mode**: <"prebuilt SPA via `scistudio gui`" |
  "Vite dev server on port NNNN against `scistudio serve`">
- **Required services / env vars**: <anything beyond a clean dev install>
- **Required data / fixtures**: <project folders, sample inputs, BLOB paths>
- **External accounts**: <e.g. ANTHROPIC_API_KEY for AIBlock scenarios>

## 3. Launch Plan

Fill the commands the skill should run. Leave the defaults if a clean
`scistudio gui` is enough.

- **Backend start**:
  ```powershell
  scistudio gui --port 8000 --no-browser
  ```
- **Frontend start** (only if Vite dev server is needed):
  ```powershell
  cd frontend; npm run dev -- --port 5180
  ```
- **Readiness probe**:
  ```powershell
  until curl -s http://localhost:8000/api/health | Select-String '"ok"'; do Start-Sleep 0.5; done
  ```
- **Cleanup commands** (will run at end of session, even on failure):
  ```powershell
  Get-Process node, python | Where-Object { $_.CommandLine -match 'vite|scistudio' } | Stop-Process -Force
  ```

## 4. Affordances Under Test

List the concrete UI / API surfaces this session touches. The skill uses
this to scope its observation:

- <e.g. "Workflow canvas — adding a `LoadData` block via palette drag">
- <e.g. "AIChat panel — `/run_workflow` slash command end-to-end">
- <e.g. "Lineage tab — Methods export dialog">

## 5. Steps

Number each step. Each step has an **Action** (what to do), an **Expected**
(what should be true after the action), and optional **Capture** (artifacts
the skill should grab). The skill will execute in order and halt on the
first failure unless `on_failure: continue` is set on the step.

### Step 1 — <short label>

- **Action**: <imperative — "Click the `+ New Project` button in the top bar">
- **Expected**: <observable — "Folder picker dialog opens" OR
  "POST /api/projects returns 201 with `{id, name}` body">
- **Capture**: <"screenshot" | "console messages matching /pattern/" |
  "network request to /api/foo" | "none">
- **On failure**: <"halt" (default) | "continue and mark step failed">

### Step 2 — <short label>

- **Action**:
- **Expected**:
- **Capture**:
- **On failure**:

<!-- Add more steps as needed. Keep each step atomic — one action,
     one observable. Long composite steps hide which sub-action failed. -->

## 6. Regression Sentinels

Things that MUST NOT happen during the run. Skill checks these continuously
and fails the session if any fires, even mid-step:

- **Console errors**: <"no uncaught React errors" | regex list>
- **Network errors**: <"no 5xx responses" | specific URLs that must stay 2xx>
- **Native dialogs**: <"`alert`/`confirm` never fires" — recommended default>
- **Process health**: <"backend process does not exit"
  | "frontend dev server stays responsive">

## 7. Results (skill fills in)

> Leave empty when filling out the template. The skill rewrites this section
> after each run with: per-step pass/fail, sentinel hits, screenshot paths,
> final verdict, and a one-paragraph summary suitable for pasting into the
> PR body or issue comment.

### 7.1 Verdict

<PASS | FAIL | ABORTED — filled by skill>

### 7.2 Per-Step Outcome

| Step | Outcome | Evidence | Notes |
|------|---------|----------|-------|
|      |         |          |       |

### 7.3 Sentinel Hits

<none | list>

### 7.4 Artifacts

<paths to screenshots, console dumps, network logs, GIFs>

### 7.5 Follow-Ups

<bugs found that are out-of-scope for this session — opened as issues #N>
