---
title: "ADR-054 Assembly — Follow-Up Register"
status: Active
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# ADR-054 Assembly — Follow-Up Register

The owner forbade new GitHub issues for this dispatch beyond the two
implementation issues (`#2253`, `#2254`). Every deferral, edge case, cleanup and
follow-up an assembly agent finds is recorded here instead, under that agent's
heading, and cited from the `TODO(#NNN)` that defers it.

An entry is a deferral, not a decision. The manager triages this register when
the assembly lands and opens issues for what survives triage.

## S5-B1

### F-B1-1 — The standalone MCP bridge reports no workspace focus

`StandaloneMCPRuntime` (`src/scistudio/ai/agent/mcp/runtime.py`) sets
`workspace_focus = None`, so a bridge-attached agent always reads mode `canvas`
and every session tool refuses unless it names a session explicitly. The
persisted focus is on disk at `<project>/.scistudio/active_workflow.json`, so a
bridge attached to a project could read the live focus rather than reporting
none.

Deferred because `active_workflow_id` has exactly the same gap and the two must
move together, and because ADR-054 spec 5 FR-002 scopes restoration to the
backend runtime — its affected-files table names `api/runtime/_projects.py`, not
the bridge. Fixing one without the other would leave the bridge reporting a
focus over a workflow id it still reports as `None`.

Cited from the `TODO(#2254)` on `StandaloneMCPRuntime.workspace_focus`.

### F-B1-2 — The focus field list is stated twice, once per layer

`scistudio.ai.agent.mcp._focus.FOCUS_FIELDS` / `FOCUS_MODES` and
`scistudio.api.runtime._projects._FOCUS_FIELDS` / `_FOCUS_MODES` are the same
two lists, written out on both sides of the api/ai boundary. The duplication is
deliberate: `scistudio.api.runtime` must not import
`scistudio.ai.agent.mcp._focus`, because importing any module under
`scistudio/ai/agent/mcp/` executes that package's `__init__`, which eagerly
imports every tool module and FastMCP so the `@mcp.tool` decorators run — about
1.7s and the whole tool graph, added to a package that today imports neither.

`tests/ai/test_workspace_focus.py::test_the_two_layers_agree_on_the_focus_record`
asserts the two lists are equal, so the drift is caught rather than merely
warned about. A durable fix would move the field list to a module both layers
can import cheaply — `scistudio/core/` is where `core/panels.py` went for the
same "the one type all three read sits below all three" reason — or make the MCP
package's `__init__` lazy. Both are larger changes than this task's scope, and
the second would touch every tool module.

### F-B1-3 — `focus_is_stale` only checks that the notebook file exists

FR-004 defines a stale focus as one "naming a session whose notebook no longer
exists", and that is exactly what is implemented: the path is resolved under the
project root and `is_file()` is checked. A notebook that still exists but whose
kernel has died, or whose session the service has closed, is *not* reported
stale — the session tools will get the session API's own error for that, which
is more specific than "stale" would be.

If the assembled surface shows agents confused by a live-looking focus over a
dead session, the fix is to consult `SessionService.sessions()` from the context
tool rather than to widen the file check. That was not done here because the AI
layer must not import `scistudio.explore` or reach the session service directly
(the session tools go through the API), and because it would make a read-only
context tool depend on live session state.

### F-B1-4 — The CI parallel test phase is over its 600s budget on this track

`ci.yml` runs the parallel phase as `timeout 600 pytest -n auto -m "not serial"
--timeout=60`. On `track/adr-054-integration` — before any spec 5 work existed —
run 33952874542 hit `exit code 124` at 96% on Python 3.13 with
`pytest parallel phase exceeded 600s shell timeout`. PR #2258 reproduces the
same stop at the same 96% on 3.13, so the cap is a property of the assembled
track, not of any one agent's tests. Python 3.11 fails separately on the known
`tests/explore/test_explore_session.py::test_a_kernel_killed_from_outside_is_reported_dead_and_offers_a_restart`
Linux failure the checklist already tracks against `#2251`.

No individual test exceeds `--timeout=60`, so this is aggregate cost rather than
a hang, and every agent still to land on this track adds to it. S5-B1's own
contribution was cut from ~40s to ~13s by scoping the app fixture in
`tests/ai/test_workspace_focus.py` to the module instead of the test, which is
worth doing but is not the fix. The fix is the manager's: either raise the cap,
or move the slowest suites to the serial phase, or split the job.
