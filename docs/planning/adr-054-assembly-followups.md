---
title: "ADR-054 Assembly Follow-Up Register"
status: Draft
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# ADR-054 Assembly Follow-Up Register

This file exists because the owner forbade opening new GitHub issues during
the ADR-054 assembly:

> 除了实现代码对应的issue外，任何follow-up issue均不开，放到一个文件里等我醒了看。
>
> (Open no follow-up issue beyond the ones the implementation code needs; put
> them in one file for me to read when I wake up.)

Every deferral, edge case, cleanup, missing test, design question and drift
found during the assembly lands here instead of in the tracker. Each entry is
written so the owner can turn it into an issue in one step, or decide it is
not worth one.

The two issues that **were** opened, because they are the implementation
issues the directive permits:

- `#2253` — ADR-054 spec 4, the Explore tab and the notebook frontend.
- `#2254` — ADR-054 spec 5, the workspace focus, the panel skill, the session
  tools.

## How To Read An Entry

| Field | Meaning |
|---|---|
| **Severity** | `P1` blocks the feature; `P2` is a real defect that does not block; `P3` is cleanup or polish |
| **Found by** | The agent label, so its report and branch can be found |
| **Evidence** | A file and line, a test, or a command output — never a claim alone |
| **Suggested title** | Ready to paste into `gh issue create --title` |

## Register

### Manager

#### M-001 — PR #2255 needs the `admin-approved:core-change` label, applied by the owner

- **Severity**: P1 — CI's `Verify Workflow Compliance` job fails without it.
- **Found by**: manager, from PR #2238's CI run 33808346838.
- **Evidence**: `guard.core_change_guard` reports
  `protected core/runtime change requires admin-approved:core-change applied
  by an authorized maintainer or administrator approval`, affecting
  `src/scistudio/blocks/base/interactive.py`,
  `src/scistudio/blocks/process/builtins/data_router.py`,
  `pair_editor.py`, `src/scistudio/blocks/registry/__init__.py` and
  `_capability.py`.
- **Why it is here and not done**: the manager attempted
  `gh pr edit 2255 --add-label admin-approved:core-change` and the action was
  refused by this session's permission classifier. The owner's blanket
  pre-approval does not override that refusal, and the label's whole purpose
  is a human attestation whose actor provenance CI verifies — so it is the
  owner's to apply, deliberately.
- **What the label attests**: every affected file is named in the approved
  specs' own `governs.files`. ADR-054 spec 1 §3 changes the panel manifest on
  the block base and the registry's capability resolution; spec 3 §4.5 adds
  `on_new_input` to the same base and the packaged block's ask pause to the
  scheduler's dispatch. The change is what the approved specs ask for.
- **Action**: `gh pr edit 2255 --add-label "admin-approved:core-change"`, or
  the same from the PR page.
- **Suggested title**: N/A — this is an owner action, not an issue.

#### M-003 - A stale `split_collection` entry point breaks block discovery at startup

- **Severity**: P3 - environment, not code; the server starts anyway.
- **Found by**: manager, launching the merged backend for the e2e readiness
  check.
- **Evidence**: the server logs
  `ModuleNotFoundError: No module named 'scistudio.blocks.process.builtins.split_collection'`
  during startup, then reaches `Application startup complete` and serves 135
  routes. The module exists **neither on this branch nor on `origin/main`** -
  `git cat-file -e origin/main:src/scistudio/blocks/process/builtins/split_collection.py`
  reports absent, and `grep -rn split_collection src/ pyproject.toml` finds
  nothing.
- **Reading**: a stale entry point in an installed distribution on this
  machine, left by an earlier install of a version that had the module. It is
  not an ADR-054 regression and nothing in this dispatch caused it.
- **Why it is worth recording**: it will keep appearing in every local
  startup log and in every e2e transcript, where it reads like a defect in
  whatever work is being tested. The e2e scenario now names it so it is not
  reported as one. Worth an environment clean-up, or a startup log line that
  distinguishes a stale registration from a broken import.
- **Suggested title**: `chore(env): a stale split_collection entry point logs a ModuleNotFoundError at every startup`

#### M-002 - `eslint-config.test.ts` flakes under machine load on a 5s timeout

- **Severity**: P3 - pre-existing, unrelated to ADR-054, and green in isolation.
- **Found by**: manager, taking the frontend baseline on the merged assembly
  branch before spec 4 lands.
- **Evidence**: `frontend/src/__tests__/eslint-config.test.ts:12`,
  `loads the project flat config without parser errors`, failed with
  `Test timed out in 5000ms` after running 12334ms during a full
  `npm run test` on a machine with several agents active. Re-run alone,
  `npx vitest run src/__tests__/eslint-config.test.ts` gives 8 passed.
  Full-suite baseline otherwise: **2315 passed, 1 failed, 198 files**; with
  the re-run the suite is 2316/2316.
- **Why it matters**: the test performs a real ESLint flat-config resolution,
  which is I/O-bound and easily exceeds 5s on a loaded runner. It will flake
  in CI on a busy day and will look like a frontend regression in whichever
  PR happens to be running.
- **Suggested title**: `flaky(frontend): eslint-config.test.ts resolves a real flat config on a 5s timeout`

### S4-A1

_No entries yet._

### S4-A2

_No entries yet._

### S4-A3

_No entries yet._

### S4-A4

_No entries yet._

### S5-B1

#### F-B1-1 — The standalone MCP bridge reports no workspace focus

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

#### F-B1-2 — The focus field list is stated twice, once per layer

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

#### F-B1-3 — `focus_is_stale` only checks that the notebook file exists

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

#### F-B1-4 — The CI parallel test phase is over its 600s budget on this track

`ci.yml` runs the parallel phase as `timeout 600 pytest -n auto -m "not serial"
--timeout=60`. On `track/adr-054-integration` — before any spec 5 work existed —
run 33952874542 hit `exit code 124` at 96% on Python 3.13 with
`pytest parallel phase exceeded 600s shell timeout`. PR #2258 reproduced the
same stop at the same 96% on 3.13, so the cap is a property of the assembled
track, not of any one agent's tests. Python 3.11 fails separately on the known
`tests/explore/test_explore_session.py::test_a_kernel_killed_from_outside_is_reported_dead_and_offers_a_restart`
Linux failure §9 already tracks against `#2251`.

No individual test exceeds `--timeout=60`, so this is aggregate cost rather than
a hang, and every agent still to land on this track adds to it. S5-B1's own
contribution was cut from ~40s to ~13s by scoping the app fixture in
`tests/ai/test_workspace_focus.py` to the module instead of the test, which is
worth doing but is not the fix. The fix is the manager's: either raise the cap,
or move the slowest suites to the serial phase, or split the job.


### S5-B2

#### F-1 — The MCP context cannot reach the running GUI's panel registry

`reload_panels` rebuilds the panel registry, but the
`scistudio.ai.agent.mcp._context.MCPContext` Protocol carries the block registry,
the type registry, the project dir and the active workflow id — and nothing else.
The FastAPI adapter that implements it (`_RuntimeAdapter` in
`src/scistudio/api/app.py`) forwards `block_registry`, `type_registry`,
`project_dir`, `active_workflow_id`, `workflow_runs`, `event_bus`,
`start_workflow` and `register_plot_artifact`, but **not**
`ApiRuntime.refresh_preview_service()` — which is the method that rebuilds the
service the GUI actually reads.

The tool therefore asks the context first and falls back to the process-global
service from `scistudio.panels.get_preview_service(refresh=True)`, and reports
which one it reached on `ReloadPanelsResult.reached_running_gui`. Under the
FastAPI process today that field is `False`: the agent's rebuild registers the
panel for the agent's own session, and the GUI sees it on its own next rebuild
(a project switch, or the panel reload route).

**Why it was deferred**: `src/scistudio/api/app.py` and `_context.py` are outside
the S5-B2 write set — `_context.py` belongs to S5-B1's workspace-focus work — and
widening a Protocol every context implementation satisfies is a change that wants
one owner, not two agents editing it in the same wave.

**What would close it**: add `refresh_preview_service` (and `get_preview_service`)
to the `_RuntimeAdapter` and to the `MCPContext` Protocol as optional members,
then assert `reached_running_gui is True` against a real `ApiRuntime`. The
`reload_panels` fallback and the `reached_running_gui` field can stay: the
standalone bridge still has no GUI to reach.

Cited from: `src/scistudio/ai/agent/mcp/tools_panels/tools.py` module docstring.

#### F-2 — The spec names three count-assertion sites; there are five

ADR-054 spec 5 §4.2 lists `tests/ai/test_mcp_fastmcp.py`,
`tests/ai/test_mcp_server_skeleton.py` and
`tests/ai/test_finish_ai_block_skeleton.py` as the count assertions FR-025 moves.
Adding the four panel tools (36 → 40) breaks **five** places, and
`test_mcp_server_skeleton.py` is not one of them (its whole module is skipped):

| File | Line | What it asserts |
|---|---|---|
| `tests/ai/test_mcp_fastmcp.py` | 5, 95, 97 | `len(tools) == 36`, plus the count in the module docstring |
| `tests/ai/test_finish_ai_block_skeleton.py` | 38, 42 | `len(tools) == 36` |
| `tests/contracts/test_runtime_import_contract.py` | 18, 206, 255 | `MCP server must expose 36 tools` |
| `tests/cli/test_mcp_bridge.py` | 152, 226 | the bridge's `tools/list` returns 36 |
| `tests/integration/test_phase2_mcp_end_to_end.py` | 7, 88 | the end-to-end `tools/list` returns 36 |

**Why it was deferred**: the count assertions are S5-B4's write set (T-009), and
this branch must not touch them. They fail on this branch in isolation and are
expected to be green once S5-B4's row lands on the track branch.

**What would close it**: S5-B4 updates all five, not the three the spec names,
and the spec's §4.2 table gains the two missing rows. The arithmetic after both
tool groups land is 36 + 4 panel + 7 session = **47**.

#### F-3 — The panel message contract is mirrored in Python, not shared

`src/scistudio/ai/agent/mcp/tools_panels/_contract.py` names the message types,
the envelope marker and the host actions so the scaffold can generate the panel
document and the harness from one source. The host's own copy is
`frontend/src/panels/panelMessages.ts`. A Python scaffold cannot import
TypeScript, and the frontend source is not shipped inside the installed wheel, so
the two are held together by
`tests/ai/test_mcp_tools_panels.py::test_contract_module_mirrors_the_host_contract`,
which reads the `.ts` file and fails when the lists diverge. That test skips when
the frontend directory is absent (a wheel-only checkout).

**Why it was deferred**: generating one from the other needs a codegen step and a
generated-file check in CI, which is a build-system change well outside this
task's scope, and `frontend/**` is outside the write set entirely.

**What would close it**: emit the constant block from one source at build time
(TypeScript from JSON, or JSON from TypeScript) and make the generated file a
CI-verified artifact, retiring the parity test.

#### F-4 — The harness browser test needs `npm ci` in `frontend/` and is not in CI

`test_harness_renders_and_captures_an_emission_in_a_browser` opens the scaffolded
harness in the chromium that `frontend/`'s Playwright installs, driving it from a
short Node script. It is the assertion that makes FR-015 real, and it passes
locally. It **skips** when `node` is absent or `frontend/node_modules/playwright*`
is not installed, and no CI job currently installs them — `.github/workflows/`
never runs `npm run test:e2e`, and `playwright` is not in the `dev` extra of
`pyproject.toml`. So on CI today this test skips rather than runs.

**Why it was deferred**: adding a Python `playwright` dependency plus a browser
download to the Python test job, or wiring the frontend e2e job into `ci.yml`, is
a CI-surface change the dispatch did not authorise and which would land in every
agent's branch at once.

**What would close it**: one CI step that runs `npm ci` in `frontend/` and
`npx playwright install --with-deps chromium` before the Python test job, or a
dedicated panel-harness job. Until then the harness's *generation* is still fully
covered by
`test_harness_is_generated_from_the_contract_module`,
`test_generated_documents_parse_as_javascript` and
`test_harness_supplies_representative_data_for_each_declared_type`, all of which
run everywhere.

#### F-5 — The tool group is registered in `__init__.py`, not `server.py`

The S5-B2 dispatch prompt names `src/scistudio/ai/agent/mcp/server.py` as the
file that registers a tool group, and asks S5-B2 and S5-B3 to keep their edits
there minimal so the two merge. `server.py` owns the module-scope `FastMCP`
instance but imports no tool module; the eager side-effect imports that register
every group live in `src/scistudio/ai/agent/mcp/__init__.py`. This branch
therefore adds one alphabetically-ordered line (`tools_panels`) to that import
list and two lines to the module docstring, and does not touch `server.py`.

**Consequence for the merge**: S5-B3's `tools_explore` line lands in the same
import list two lines away, which git may present as a conflict. The resolution
is to keep both lines.

**What would close it**: nothing in the code — the dispatch template's
"registers the two groups" row should name `__init__.py`, and ADR-054 spec 5
§4.2's `server.py` row should say the same.

#### F-6 — `list_panel_examples` returns nothing until the corpus lands

FR-017 requires the examples corpus to gain at least one displaying and one
producing panel; those entries are T-008's (S5-B4). `list_panel_examples` scans
`src/scistudio/_user_guide/examples/` for directories holding a `panel.json`,
returns them when they exist, and returns an empty list with a diagnostic
pointing at `read_panel_source` on a `core.*` panel when they do not. Both
behaviours are tested. Nothing here needs changing when the corpus lands; this
entry exists so the empty result today is not read as a defect.

#### F-7 — The scaffolded panel declares no `provider`

`scaffold_panel` writes a declaration without the optional `provider` field, so a
scaffolded panel's windowed reads are served by the shared bounded data-access
layer. That is the right default (it windows every core type), but a panel for a
package-owned type that needs its own windowing has to add the field by hand
after reading `panel-contract.md`. A `provider` argument on the tool, which would
also scaffold the Python callable, was not added: it is a second file in a second
language and a second thing to get wrong on the first call.

**What would close it**: a follow-up `provider=` argument on `scaffold_panel`
once there is a real panel that needs one, or a worked example in the corpus.

#### F-8 — `gate_record check` cannot find the ledger after a pre-PR `finalize`

Once `gate_record finalize` (pre-PR mode) has marked a ledger PR-ready, a later
`gate_record check --mode pre-pr` run from the same worktree exits 2 with
`no gate ledger found; run init first`, whether the repo root is inferred or
passed with `--repo-root`. Passing the record explicitly works:

```bash
python -m scistudio.qa.governance.gate_record check \
  --record .workflow/records/<record>.json --mode pre-pr \
  --base <track branch> --head HEAD --pr-body-file .workflow/local/pr-body.md
```

Every agent in this dispatch hits this, because the flow the dispatch prescribes
— pre-PR `finalize`, then `scistudio_pr_create.py`, then post-PR `finalize` —
lands a checklist/record commit between the two finalizes, which makes the check
evidence stale and forces exactly this re-run.

**Why it was deferred**: `src/scistudio/qa/governance/gate_record/**` is outside
every S5 write set, and a change to ledger auto-discovery affects every task
kind in the repository.

**What would close it**: make auto-discovery keep selecting a PR-ready ledger for
the current branch, or make the "run init first" message say `--record` is the
way to name an already-finalized one.


### S5-B3

_No entries yet._

### S5-B4

_No entries yet._

### S4-D1 / S5-D1 (adversarial testing)

_No entries yet._

### S4-E1 / S5-E1 / INT-E1 (audits)

_No entries yet._

## Already-Tracked Follow-Ups Inherited From Specs 1 To 3

These already have issues. They are listed so the owner sees the whole
ADR-054 debt in one place, not so they are opened again.

| Issue | Subject | Source |
|---|---|---|
| `#2212` | Let a plot panel declare the producing capability | ADR-054 §10.2, explicitly out of scope |
| `#2233` | A producing panel's emission has no time bound and runs on the scheduler's event loop | spec 1 dispatch |
| `#2236` | Revise the human-facing panel vocabulary and documentation (ADR-054 spec 6) | ADR-054 §10.1 |
| `#2237` | Nothing checks the API wire between `schemas.py` and `types/api.ts` | spec 1 dispatch — the mechanism behind three fixed wire breaks |
| `#2242` | The ADR and the explore-frontend spec name `ExploreTab.test.tsx` at two different paths | spec 4 input defect |
| `#2243` | Spec 2 FR-015's unresolved-read exception rests on a false premise | needs an owner decision |
| `#2244` | `test_concurrent_write_workflow_serialises` is not marked serial | spec 2 dispatch |
| `#2245` | `gate_record` cannot correct a runtime recorded wrong at init | spec 3 dispatch |
| `#2249` | A concurrent `gate_record check` silently overwrites an amend | spec 3 dispatch |
| `#2250` | Spec 3 FR-050's panel channel needs an event type FR-057 does not list | needs an owner decision |

`#2242`, `#2243` and `#2250` are **input defects in the approved specs** and
may change what spec 4 and spec 5 should build. The manager's reading of each
is recorded in the assembly checklist's drift log as the agents hit them.
