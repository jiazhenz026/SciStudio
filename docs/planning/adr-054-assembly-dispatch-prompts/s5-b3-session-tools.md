---
title: "ADR-054 Assembly Dispatch — S5-B3 The Session Tools"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# S5-B3 — The Session Tools Over The Session API

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-054 spec 5's session tools — seven thin tools
  that let the agent work inside the person's explore session, every one of
  them a call to the session API with the workspace focus resolved first.
- Task kind: feature
- Persona: implementer
- Issue: #2254
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2254
- Umbrella PR: #2255 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-054-integration
- Track branch (your PR base): track/adr-054-spec5-agent-enablement
- Agent branch: feat/2254-session-tools
- Agent worktree: .worktrees/s5-b3
- Gate record: .workflow/records/2254-feat-2254-session-tools.json
- Checklist: docs/planning/adr-054-assembly-checklist.md
- Shared preamble: docs/planning/adr-054-assembly-dispatch-prompts/_common.md
  — read it first.

## Required Rules

Everything in the shared preamble, plus:

- `docs/specs/adr-054-agent-enablement.md` — your spec. You implement
  **T-006** of its §4.3, covering FR-019 to FR-024.
- `docs/specs/adr-054-explore-session.md` §3 — the session API your tools
  call. The **landed** implementation at `src/scistudio/explore/notebook_api.py`,
  `session.py` and `src/scistudio/api/routes/explore.py` is the fact.
- Agent S5-B1 landed the workspace focus and the refusal helper on
  `feat/2254-workspace-focus`, merged into your base. **Read its report or its
  code for the helper's location and signature before writing.**

## Scope

You own only:

- `src/scistudio/ai/agent/mcp/tools_explore/**` — new.
- `src/scistudio/ai/agent/mcp/server.py` — registering the explore group only.
  **Coordinate**: S5-B2 registers the panel group in the same file. Keep your
  edit minimal and additive so the two merge cleanly.
- `tests/ai/test_mcp_tools_explore.py` — new.

You must not touch:

- `src/scistudio/ai/agent/mcp/tools_panels/**` — S5-B2.
- The workspace-focus files (`api/routes/ai.py`, `api/runtime/_projects.py`,
  `mcp/runtime.py`, `_context.py`, `tools_workflow/read.py`) — S5-B1. You
  **import** the refusal helper; you do not change it.
- `src/scistudio/_skills/**`, `src/scistudio/agent_provisioning/**`,
  `tools_authoring.py`, the count assertions and the catalogs — S5-B4.
- `src/scistudio/_agent_reference/**` — S5-B2 and S5-B4.
- **`src/scistudio/explore/**` — spec 3's landed runtime.** Your tools call
  its API. If a tool needs something the API does not offer, that is a finding
  to report, not a reason to change the runtime.
- Every `frontend/**` path.

If you need an out-of-scope path, stop and report back. Do not edit it.

## TODO And Deferral Rule

Per the shared preamble. Do not open an issue; append to
`docs/planning/adr-054-assembly-followups.md` under `## S5-B3`.

## Work To Do

The design constraint that governs all seven tools: **they are thin.** Each is
a call to the session API with the focus resolved first. FR-024 makes this
absolute — a session tool must go through the session API and must **not**
reach the kernel, the notebook file, or the queue directly. The whole point of
the session service is that every execution passes through it; an agent tool
that bypassed it would be a second door. An appended cell must appear in the
person's notebook through the same events the person's own edits produce.

Every tool acts on the **focused** session by default, accepts an explicit
session path instead, and otherwise refuses through S5-B1's helper (FR-005).

1. `open_explore_session` — opens a session over a named block's outputs or a
   named file through the session API and returns the session path. **It must
   not change the focus** (FR-019). The person's focus is the person's.
2. `read_notebook` — returns the session's cells with their source, enabled
   flag, marks and outputs; the bindings with their type names and whether
   each is live; the declared outputs; and the graph (FR-020).
3. `append_cell` — inserts a cell after the session's **current** cell through
   the session API and returns its id (FR-021).
4. `run_cell` — submits a cell to the session's queue and returns its outputs
   and changed names when the run completes, **or the queue's refusal**
   (FR-021). A refusal is a result, not an exception to swallow.
5. `get_bindings` — the bindings alone, for the common case where the agent
   needs to know what exists before writing (FR-022).
6. `check_packaging` — returns the packaging report (FR-023).
7. `package_notebook` — packages and returns the block id, **or the report
   when packaging is refused** (FR-023).

## Required Tests And Checks

`tests/ai/test_mcp_tools_explore.py`, against a **scripted** session API — the
real session is covered by spec 3's own suite, so what you assert here is the
request each tool makes and the shape of what it returns:

- Each of the seven tools issues exactly the API call the spec names, with the
  focused session resolved, and returns the documented shape.
- Each tool with an explicit session path uses it instead of the focus.
- Each tool with the focus on canvas, and with a stale session, refuses
  through S5-B1's helper with a message that names how to open a session.
- `open_explore_session` does not change the focus — assert the focus before
  and after.
- `run_cell` returns the queue's refusal as a result.
- `package_notebook` returns the report on refusal.
- **A test that no tool module imports the kernel, the notebook file writer,
  or the queue directly** — FR-024 is a structural claim and deserves a
  structural assertion, not only behavioural ones.

Then:

- `python -m scistudio.qa.governance.gate_record check --mode pre-pr
  --base track/adr-054-spec5-agent-enablement --head HEAD
  --pr-body-file .workflow/local/pr-body.md`
- Pre-PR `finalize`, `python scripts/scistudio_pr_create.py`, post-PR
  `finalize`. Base your PR on `track/adr-054-spec5-agent-enablement`.
- Docs: `--docs-na "user-docs:the human documentation revision is ADR-054
  spec 6, issue #2236"`.

## Output Required

Per the shared preamble. Additionally: state the seven tool names **exactly as
registered**, because S5-B4 writes them into the catalogs and the count
assertions and will stop rather than guess.

## Stop Conditions

Per the shared preamble. Additionally: stop if the session API does not offer
what a tool needs — report the gap rather than reaching past the API.
```
