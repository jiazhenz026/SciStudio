---
title: "ADR-054 Assembly Dispatch — S5-B1 Workspace Focus"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# S5-B1 — The Workspace Focus And The Session-Tool Refusal

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-054 spec 5's one hard requirement — the agent
  must always know whether the person is on the canvas or in an explore
  session — by widening the existing active-workflow channel into a workspace
  focus that persists, restores, and is reported by the context tool, with a
  refusal the session tools call when no session is active.
- Task kind: feature
- Persona: implementer
- Issue: #2254
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2254
- Umbrella PR: #2255 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-054-integration
- Track branch (your PR base): track/adr-054-spec5-agent-enablement
- Agent branch: feat/2254-workspace-focus
- Agent worktree: .worktrees/s5-b1
- Gate record: .workflow/records/2254-feat-2254-workspace-focus.json
- Checklist: docs/planning/adr-054-assembly-checklist.md
- Shared preamble: docs/planning/adr-054-assembly-dispatch-prompts/_common.md
  — read it first.

## Required Rules

Everything in the shared preamble, plus:

- `docs/specs/adr-054-agent-enablement.md` — your spec. You implement
  **T-001 and T-002** of its §4.3, covering FR-001 to FR-005.
- ADR-040 Addendum 5 — the active-workflow channel you are widening. Read the
  landed implementation before changing it; the focus is "the same shape with
  more fields", not a new mechanism.
- `docs/specs/embedded-coding-agent-spec.md` for the context tool's contract.

## Scope

You own only:

- `src/scistudio/api/routes/ai.py` — the focus report on the active-workflow
  route.
- `src/scistudio/api/runtime/_projects.py` — focus persistence beside the
  active workflow id, in the same per-project file.
- `src/scistudio/ai/agent/mcp/runtime.py` and
  `src/scistudio/ai/agent/mcp/_context.py` — the focus record reaching the
  tools.
- `src/scistudio/ai/agent/mcp/tools_workflow/read.py` — the context tool
  reporting the focus.
- One shared refusal helper the session tools import. Put it where the MCP
  tool modules can reach it without importing each other; state where you put
  it in your report, because S5-B3 imports it.
- `tests/ai/test_workspace_focus.py` — new.

You must not touch:

- `src/scistudio/ai/agent/mcp/tools_panels/**` — S5-B2.
- `src/scistudio/ai/agent/mcp/tools_explore/**` — S5-B3. You provide the
  refusal; S5-B3 writes the tools that call it.
- `src/scistudio/_skills/**`, `src/scistudio/agent_provisioning/**` — S5-B4.
- `src/scistudio/_agent_reference/**` — S5-B2.
- Every `frontend/**` path. **The frontend half of FR-001 is spec 4's**: the
  ADR-054 spec 4 agent writes the caller that reports the focus on tab change.
  You own the channel that receives it. Define the request shape precisely and
  state it in your report so the manager can assert the wire at integration.
- `src/scistudio/explore/**` — spec 3's runtime, already landed.
- `docs/architecture/**` — the tool table lands with spec 6 (#2236).

If you need an out-of-scope path, stop and report back. Do not edit it.

## Coordination

Everything in the shared preamble. In addition: **S5-B3 depends on your
refusal helper and on the focus record reaching the tools.** Land those two
first and push, then finish the rest.

## TODO And Deferral Rule

Per the shared preamble. Do not open an issue; append to
`docs/planning/adr-054-assembly-followups.md` under `## S5-B1`.

## Work To Do

1. **T-001 — widen the channel.**
   The frontend reports the workspace focus whenever the active tab changes:
   mode `canvas` with the workflow id; mode `explore` with the session's
   notebook path, its bound run, and the current cell id; mode `pause` with
   the paused node and its run. The report travels along the **existing**
   active-workflow channel (FR-001) — do not add a route. The backend
   persists the focus beside the active workflow id, in the same per-project
   file, and restores it on project open and on backend restart exactly as it
   restores the active workflow id (FR-002). The runtime's field becomes a
   small record. Keep every field additive: absent focus fields must behave
   exactly as today.
2. **T-002 — report it, and refuse without it.**
   The context tool the agent already has for the active workflow reports the
   focus: its existing fields unchanged, plus the mode and the mode's
   identifiers (FR-003). A focus that has never been reported reads as mode
   `canvas` with the persisted workflow. A focus naming a session whose
   notebook no longer exists is reported as **stale**, and session tools
   refuse until a new focus is reported (FR-004).
   Write the refusal helper FR-005 requires: every session tool acts on the
   focused session by default, accepts an explicit session path instead, and
   refuses with a message that says no explore session is active **and how to
   open one**, when neither is available. The refusal is the enforcement — a
   skill can tell the agent to check the mode first and it does, but the
   refusal is what makes the rule hold when the agent forgets, so the message
   must let the agent recover in one step.

## Required Tests And Checks

`tests/ai/test_workspace_focus.py` must cover, end to end on the backend:

- Each mode posted on the route, read back from the runtime **and from the
  file**, with the runtime object restarted in between (FR-001, FR-002).
- The context tool reporting each mode, and a never-reported focus reading as
  canvas with the persisted workflow (FR-003).
- A focus naming a missing notebook reading as stale (FR-004).
- The refusal, called with the focus on canvas and with a stale session,
  asserting the message names the way to open a session (FR-005).
- Absent focus fields behaving as today, which is what proves the change is
  additive.

Then:

- `python -m scistudio.qa.governance.gate_record check --mode pre-pr
  --base track/adr-054-spec5-agent-enablement --head HEAD
  --pr-body-file .workflow/local/pr-body.md`
- Pre-PR `finalize`, then `python scripts/scistudio_pr_create.py`, then
  post-PR `finalize`. Base your PR on `track/adr-054-spec5-agent-enablement`.
- Docs: `--docs-na "user-docs:the human documentation revision is ADR-054
  spec 6, issue #2236"`.

## Output Required

Per the shared preamble. Additionally, state exactly:

- The request shape the frontend must POST, field by field, for each mode.
  The manager asserts this wire against spec 4's caller at integration.
- Where the refusal helper lives and its signature, because S5-B3 imports it.

## Stop Conditions

Per the shared preamble.
```
