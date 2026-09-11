---
title: "Headless End-To-End Tests"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs: []
related_specs: []
language_source: en
---

# Headless End-To-End Tests

## 1. What The Suite Covers

`tests/e2e/` runs SciStudio the way a user does, minus the window: it starts a
real `python -m scistudio serve` process, builds projects on disk, runs
workflows in worker processes, and talks to the server over HTTP and the `/ws`
WebSocket the GUI uses (#2298). The in-process suites cannot catch what this
catches: server startup, drop-in type/block/previewer discovery from project
files, worker-process execution, lineage records, the GUI event protocol,
interactive pauses, and cancellation.

The scenarios are built from the core tutorials, because those are the
product's own reference workflows:

| Scenario | Tutorial | What it proves |
| --- | --- | --- |
| Normalize and save | welcome-to-scistudio | A project block runs; the workflow API round-trips; the saved CSV and a preview session are correct |
| IC50 with the AI Block | what-ai-can-do | Four project blocks and an AI Block subclass chain to IC50 ≈ 29.3 µM |
| Fit without doses | what-ai-can-do | A failing block fails the run and reports why on `block_error` |
| Segment two micrographs | what-is-a-type | A project type, loader, and previewer work; a two-item output arrives as a collection |
| Review labels | what-is-a-type | An interactive block pauses, serves its panel, and applies the user's answer |
| Cancel at review | what-is-a-type | `cancel_workflow` during a pause cancels the run and writes nothing |

## 2. Running It

The suite skips itself unless `SCISTUDIO_RUN_E2E=1`, so the normal test run is
unaffected. CI runs it in the separate **E2E (headless)** job.

```bash
SCISTUDIO_RUN_E2E=1 PYTHONPATH=./src pytest tests/e2e -o addopts="-ra -q" --timeout=300
```

It takes well under a minute locally. On a failure, the fixture prints the tail
of the server log, and the test names the recent WebSocket events it saw.

## 3. How The Harness Works

`tests/e2e/harness.py` holds all of it:

- `ServeProcess` starts the server on a free `127.0.0.1` port. `HOME`,
  `USERPROFILE`, the SciStudio store, and the log directory all point into a
  temporary directory, so a run never touches your real library or recent
  projects. `PYTHONPATH` points at the checkout under test.
- `build_tutorial_project()` creates a project through the API, then copies
  tutorial assets into it with the same `source → destination` pairs the
  tutorial's `copy:` steps use, then calls `POST /api/blocks/reload`.
- `Backend` wraps the HTTP calls. `execute()` returns the new run id, and
  `wait_for_run()` polls `GET /api/runs/{run_id}` until the run is terminal.
  Judge the outcome from that record: `workflow_completed` fires before it is
  finalized.
- `EventStream` is one GUI WebSocket session. Keep it open (use the `events`
  fixture) whenever a run is in flight. The server cancels runs shortly after
  the last GUI socket closes, as it does for a closed window.

## 4. Adding A Scenario

Build the project from shipped assets rather than hand-written fixtures, run
it, and assert on what a user would see: the run record, the events, the
files written, or a preview. Keep each test independent. The server is shared
across the session, but every test gets its own project directory.
