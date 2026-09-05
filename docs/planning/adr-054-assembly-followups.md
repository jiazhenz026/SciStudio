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

PR #2261's CI, run 33958351227: **9 jobs pass** (Lint & Format, Type Check,
Import Contracts, Architecture Tests, Full Audit, Deferral discipline ratchet,
Desktop, Wheel Release Smoke, Verify Workflow Compliance). Three fail, none of
them this branch's code: Test (3.11) is **6 failed, 9443 passed** and every
failure is a `36`-tool count assertion (F-B3-8, S5-B4's row); Test (3.13) hit
the same two count failures and then `pytest parallel phase exceeded 600s`
at 96% (S5-B1's F-B1-4); Frontend is F-B3-11 below.

#### F-B3-1 — The MCP context cannot reach the person's live session service

- **Severity**: P1 — under the topology the desktop app actually runs, the
  agent's session tools act on a *second* `SessionService` over the same
  notebooks as the person's.
- **Found by**: S5-B3, implementing T-006.
- **Evidence**: `scistudio.ai.agent.mcp._context.MCPContext` declares
  `block_registry`, `type_registry`, `project_dir`, `active_workflow_id` and
  `workspace_focus` and nothing else. The production implementation
  (`_RuntimeAdapter` in `src/scistudio/api/app.py:120`) forwards exactly those
  members plus `workflow_runs`, `event_bus`, `start_workflow` and
  `register_plot_artifact`. The session service registry is
  `_services` in `src/scistudio/api/routes/explore.py:108`, and the AI layer
  must not import it: the import-linter contract "AI must not depend on api"
  (`pyproject.toml`) forbids the edge with no carve-out.

**What the tools do instead.**
`src/scistudio/ai/agent/mcp/tools_explore/_service.py::session_service` asks the
context for `get_session_service` / `session_service` by name — nothing
implements either today — and otherwise builds a service of its own over the
open project, cached per project directory.

**Why it matters.** `scistudio mcp-bridge` first tries the running GUI's
project-local socket (`_try_connect_attached` in
`src/scistudio/cli/mcp_bridge.py:68`) and proxies the agent's stdio into the
FastAPI process's in-process MCP server. So in the ordinary desktop case the
tools execute *inside* the process that already holds the person's
`SessionService`, and the fallback stands up a second one beside it. Two
services over one notebook means two `NotebookStore` documents over one file,
and an appended cell that reaches the person only when their own session next
reloads — which is exactly the "appears through the same events the person's
own edits produce" claim FR-024 is written to guarantee.

**Mitigations already in place** (they reduce the harm; they do not close it):
the fallback is cached per project so a process never holds more than one, and
`_service.session_for` calls `ExploreSession.reload_if_changed()` — the session
API's own answer to an outside edit — before any tool reads or writes.

**What would close it**: add `get_session_service` to `_RuntimeAdapter` (the
route's `get_session_service(runtime)` is already the right callable) and to the
`MCPContext` Protocol as an optional member, then assert against a real
`ApiRuntime` that a tool-appended cell lands in the session the HTTP routes
serve. The fallback and the accessor lookup can both stay: the standalone bridge
still has no API process to ask.

- **Suggested title**: `fix(#2254): the MCP context cannot reach the running backend's explore SessionService`
- **Status**: **fixed** on `fix/2254-session-service-forwarding` (issue #2254),
  exactly as the closing paragraph above describes. See the `fix-sessvc`
  section below for what the fix did, what it deliberately left, and the two
  smaller follow-ups it found. No issue is needed for F-B3-1 itself.

#### F-B3-2 — A bridge with no lineage store cannot open a session over a block's outputs

- **Severity**: P2 — `open_explore_session(source='block_outputs')` fails in a
  standalone bridge; `source='file'` works.
- **Found by**: S5-B3.
- **Evidence**: `SessionService._require_resolver`
  (`src/scistudio/explore/session.py:2073`) raises `NothingToExploreError`
  when the service was built without `block_outputs` or `lineage_store`. The
  fallback in `tools_explore/_service.py::_build_service` takes the store from
  `scistudio.core.metadata_store._active_lineage_store()`, which the API
  publishes when it opens a project (`api/runtime/_projects.py:203`). In a
  standalone `scistudio mcp-bridge` process nothing has published one, so the
  resolver is absent.
- **Why it is here and not fixed**: opening a second `LineageStore` on
  `<project>/.scistudio/lineage.db` from the bridge would make a second writer
  to a database the backend already owns, which is a bigger decision than a tool
  wiring change. It is also downstream of F-B3-1: a context that carried the
  service would carry a service that already has the store.
- **Suggested title**: `fix(#2254): the standalone MCP bridge cannot resolve a block's outputs for an explore session`

#### F-B3-3 — `run_cell` has no way to follow a run it stopped waiting for

- **Severity**: P3.
- **Found by**: S5-B3.
- **Evidence**: `ExploreSession` exposes `run_cell` (returns an
  `ExecutionRequest`) and `wait_until_idle`, and nothing that answers "what is
  the state of request X now". `RunCellResult.completed=False` therefore hands
  the agent a `request_id` it cannot look up; its only recourse is to call
  `read_notebook` again and read the cell's outputs.
- **What would close it**: a session-API read that answers one request's state
  by id — the WebSocket already publishes `cell_state`, so the state exists; it
  is only not readable by a caller that is not subscribed.
- **Suggested title**: `feat(#2254): let a caller read one execution request's state by id`

#### F-B3-4 — Cell outputs are bounded by the tool, and the HTTP route returns none at all

- **Severity**: P3 — a divergence, not a defect.
- **Found by**: S5-B3.
- **Evidence**: `CellModel` in `src/scistudio/api/routes/explore.py:820` carries
  `cell_id`, `cell_type`, `source`, `enabled` and `marks` — no outputs; the
  frontend reads them from the notebook it already has. FR-020 requires the
  session tool to return outputs, so
  `tools_explore/_models.py::CellOutputModel` renders them: stream text, the
  `text/plain` representation, and the error name/value/traceback, each bounded
  at `OUTPUT_TEXT_LIMIT` (4000 chars), with every other MIME type reported by
  name rather than by value so a base64 PNG never reaches the agent's context.
- **Why it is here**: the bound is the tool's own policy and lives in the AI
  layer, so two clients could disagree about what an output is. If a second
  client ever needs the same thing, the rendering belongs beside the session.
- **Suggested title**: `refactor(#2254): move the bounded cell-output rendering beside the session API`

#### F-B3-5 — The spec still says `server.py` registers the tool groups

- **Severity**: P3 — documentation drift, already found by S5-B2 as F-5.
- **Found by**: S5-B3, confirming it independently.
- **Evidence**: ADR-054 spec 5 §4.2 has the row
  `src/scistudio/ai/agent/mcp/server.py | modify | Registers the two groups.`
  `server.py` owns the module-scope `FastMCP` instance and imports no tool
  module; the eager side-effect imports live in
  `src/scistudio/ai/agent/mcp/__init__.py`. This branch adds `tools_explore` to
  that import list and two lines to the module docstring, and does not touch
  `server.py` — the same resolution S5-B2 took, so the two lines land two apart
  in one alphabetically-ordered list and the merge keeps both.
- **What would close it**: correct the §4.2 row and the dispatch template's
  "registers the two groups" wording.
- **Suggested title**: N/A — folded into S5-B2's F-5.

#### F-B3-6 — The packaging tools re-scan the block registry the runtime already holds

- **Severity**: P3 — a latency cost, not a wrong answer.
- **Found by**: S5-B3.
- **Evidence**: `check_packaging` and `package_notebook`
  (`src/scistudio/explore/packaging.py:645`, `:987`) take an optional
  `registry`, and default to scanning a fresh block registry to resolve port
  extensions and interactive block ids. Neither
  `api/routes/explore.py`'s packaging routes nor these tools pass one, so every
  check pays for a full registry scan — while `MCPContext.block_registry` is a
  scanned registry sitting right there.
- **Why it is here and not done**: passing it would make the tool's answer
  differ from the HTTP route's for the same notebook whenever the two registries
  disagree, and the route is the fact. Both callers should start passing one, or
  neither should.
- **Suggested title**: `perf(#2254): pass the runtime's block registry to the packaging check instead of re-scanning`

#### F-B3-7 — `test_write_class_tools_have_next_step` names its write-class tools by hand

- **Severity**: P2 for S5-B4 — it is not only the *counts* that move.
- **Found by**: S5-B3.
- **Evidence**: `tests/ai/test_mcp_fastmcp.py:105` builds `write_class` as a
  literal set. It does not contain the two panel write tools (`scaffold_panel`,
  `reload_panels`) that S5-B2 landed, and will not contain the four session
  write tools (`open_explore_session`, `append_cell`, `run_cell`,
  `package_notebook`) this branch lands. The assertion therefore passes while
  silently covering fewer tools than it claims to.
- **Note**: the four session result models each carry `next_step`, and
  `tests/ai/test_mcp_tools_explore.py::test_every_write_class_session_tool_result_carries_a_next_step`
  asserts it locally — so adding the six names to the shared set is safe.
- **What would close it**: derive `write_class` from the registered `write` tag
  rather than restating it, which is the tag every group already sets.
- **Suggested title**: `test(#2254): derive the write-class tool set from the registered tag`

#### F-B3-8 — Confirmed: five count-assertion sites fail at 47 tools, not three

- **Severity**: P2 for S5-B4 — corroborates S5-B2's F-2 with the run.
- **Found by**: S5-B3, on this branch with both tool groups present.
- **Evidence**: `PYTHONPATH=./src python -m pytest tests/ai tests/architecture
  tests/contracts tests/cli/test_mcp_bridge.py
  tests/integration/test_phase2_mcp_end_to_end.py` fails exactly five tests, all
  of them the number `36`:
  `tests/ai/test_mcp_fastmcp.py::test_fastmcp_lists_36_tools` (asserts 47 now),
  `tests/ai/test_finish_ai_block_skeleton.py::test_registry_now_has_36_tools`,
  `tests/contracts/test_runtime_import_contract.py::test_mcp_server_exposes_36_tools`,
  `tests/cli/test_mcp_bridge.py::test_run_standalone_mode_returns_tools_list`,
  `tests/cli/test_mcp_bridge.py::test_run_attached_mode_proxies_to_backend`, and
  `tests/integration/test_phase2_mcp_end_to_end.py::test_mcp_server_initialize_tools_list_and_call`
  — six test functions across five files. `36 + 4 panel + 7 session = 47` is the
  arithmetic, and `await mcp.list_tools()` returns 47 on this branch.
- **Suggested title**: N/A — this is S5-B4's T-009 row, recorded so it is not
  re-derived.

#### F-B3-9 — `deferral_scan.py --diff` crashes on Windows before it can report anything

- **Severity**: P2 — the diff gate every agent trips is unrunnable locally on
  Windows, so it is only ever discovered in CI.
- **Found by**: S5-B3, trying to reproduce the CI failure locally.
- **Evidence**:

  ```
  python scripts/deferral_scan.py --diff "track/adr-054-spec5-agent-enablement"
  File "scripts/deferral_scan.py", line 235, in _diff_added_lines
    for raw in out.splitlines():
  AttributeError: 'NoneType' object has no attribute 'splitlines'
  ```

  The real error is upstream and is swallowed into `stdout=None`:
  `_diff_added_lines` runs `subprocess.run(..., text=True)` without an
  `encoding`, so Python decodes git's output with the console codepage. On a
  machine whose default is GBK, a diff carrying an em dash raises
  `UnicodeDecodeError` on the reader thread and `.stdout` comes back `None`.
  Passing `encoding="utf-8", errors="replace"` fixes it; the same call in
  `_run_diff_gate`'s sibling scan paths deserves the same.
- **Why it is here**: `scripts/deferral_scan.py` is CI surface and outside every
  S5 write set.
- **Workaround used**: the gate was reproduced by driving `deferral_scan`'s own
  `_COMPILED`, `TRACKING_RE` and `EXCLUSIONS` over a `git diff` decoded
  explicitly.
- **Suggested title**: `fix(ci): deferral_scan --diff decodes git output with the console codepage and dies on Windows`

#### F-B3-10 — A PR that conflicts with its base gets no CI at all, and reads as unverified rather than failing

- **Severity**: P2 for this dispatch — several stacked branches will hit it as
  the track moves under them.
- **Found by**: S5-B3, when PR #2261 sat with zero check runs.
- **Evidence**: `gh pr view 2261 --json mergeable` returned `CONFLICTING`, and
  `gh api repos/.../commits/<sha>/check-suites` listed `claude`,
  `cloudflare-workers-and-pages` and `codacy-production` but **no
  `github-actions` suite**. GitHub cannot build the merge commit a
  `pull_request` event runs against, so `ci.yml` never fires — the PR shows no
  failing check, it shows no check. Merging the base into the branch made it
  `MERGEABLE` and all three workflows started within seconds.
- **Why it matters here**: the track branch moves while agents work on it, so
  "the PR is green" and "the PR has not run" look the same in the PR list. An
  agent that reports CI status without checking `mergeable` will report a
  branch as unverified-but-fine.
- **What would close it**: nothing in the code — a line in the dispatch
  preamble telling agents to check `mergeable` before reading CI, and to merge
  the track branch in when it has moved.
- **Suggested title**: N/A — a note for `docs/planning/adr-054-assembly-dispatch-prompts/_common.md`.


#### F-B3-11 — `OpenAsDialog.test.tsx` fails on the spec 5 track, and it is not the eslint flake

- **Severity**: P2 — the Frontend job is red on this track for a reason nobody
  has claimed, and it is a real assertion failure rather than a timeout.
- **Found by**: S5-B3, reading PR #2261's CI.
- **Evidence**: run 33958351227, Frontend job 101285657534,
  **2315 passed, 1 failed (198 files)**:

  ```
  FAIL src/components/__tests__/OpenAsDialog.test.tsx > OpenAsDialog (#2112)
       > lists every candidate with its tier and preselects the most specific
  AssertionError: expected false to be true
    src/components/__tests__/OpenAsDialog.test.tsx:110
      expect(radioFor("SRSImage").checked).toBe(true);
  ```

- **Why it is not this branch's**: `git diff track/adr-054-spec5-agent-enablement...HEAD`
  on `feat/2254-session-tools` names **no** `frontend/**` path. The branch cannot
  change what this test does.
- **Why it is not M-002**: M-002 is `eslint-config.test.ts` timing out at 5000ms
  under load. This is a different file, a different failure mode (a checked
  radio that is not checked), and it reproduced on a runner that was not
  otherwise loaded — the same suite's other 2315 tests passed in 70s.
- **What it probably is**: the dialog preselects "the most specific" candidate,
  and spec 1's panel/previewer rename or spec 3's packaged-notebook block
  changes the tier or the candidate ordering `#2112` assumed. Someone who owns
  the panel tiers should read it against `OpenAsDialog.tsx`.
- **Suggested title**: `fix(frontend): OpenAsDialog no longer preselects the most specific candidate on the ADR-054 track`


### fix-sessvc (the F-B3-1 fix)

**What the fix did.** `MCPContext` now declares `get_session_service`, the
`_RuntimeAdapter` in `src/scistudio/api/app.py` implements it, and
`src/scistudio/api/routes/explore.py` exposes `live_session_service(runtime)` —
a wrapper over the route dependency `get_session_service`, so the tools reach
the *same registry entry* the routes serve, with the same stale-store retirement
and the same `broadcast_session_event` subscription. The AI layer still imports
nothing from the API layer: the API pushes the service down through the
structural Protocol both sides already share, which is the same shape S5-B1 used
for the workspace focus. `lint-imports` stays at 15 kept, 0 broken.

`tests/ai/test_mcp_session_service_forwarding.py` holds it shut against a live
app: the tool and the routes resolve the same `SessionService` and the same
`ExploreSession`, and a cell the agent appends produces the
`explore.analysis_updated` frame on the person's WebSocket. That last one is the
assertion that fails without the fix and that a content assertion would not have
caught — `GET /sessions/{id}/cells` calls `reload_if_changed`, so a cell written
by a second service shows up there anyway.

Reverting the adapter method and re-running the module fails all four attached
tests, and turns up a symptom F-B3-1 had not named: the second service's
`open_notebook` reaches `LineageStore.insert_explore_session` with a session id
the first service already registered, and the run logs
`sqlite3.IntegrityError: UNIQUE constraint failed: explore_sessions.session_id`.
Two services over one notebook were not only diverging in memory; they were
colliding in the project's lineage database.

#### F-FS-1 — The detached service is observable to a log and to a caller, not to the agent

- **Severity**: P3 — the P1 hazard is closed; this is about how loudly the
  remaining, correct fallback announces itself.
- **Found by**: fix-sessvc.
- **Evidence**: `scistudio.ai.agent.mcp.tools_explore._service.resolve_session_service`
  returns a `ServiceOrigin` (`ORIGIN_RUNTIME` / `ORIGIN_DETACHED`, the project
  dir, and a `detail` naming the condition), and the first detached build for a
  project logs a WARNING carrying that same `detail`. Both are visible to a
  person reading a log or to code that asks. Neither reaches the **agent**: the
  seven tool results have no field for it.
- **Why it is here and not done**: putting it in front of the agent means a new
  field on the session result models — `tools_explore/tools.py` and `_models.py`
  — and those are the surfaces S5-B4's tool-count and catalog work is live on in
  this dispatch. Widening a tool's output schema underneath a concurrent agent's
  count assertions is how two correct changes produce one red branch.
- **What would close it**: one optional `service_origin: str | None` on the
  shared session result base, populated from
  `resolve_session_service()[1]` and left `None` in the attached case so the
  ordinary answer does not grow. `open_explore_session` is the one that most
  wants it, since it is where an agent decides whether to trust what follows.
- **Suggested title**: `feat(#2254): tell the agent when its session tools are on a detached notebook copy`

#### F-FS-2 — `StandaloneMCPRuntime` could answer the new accessor, and does not

- **Severity**: P3 — the correct behaviour today; recorded because the shape now
  exists for it.
- **Found by**: fix-sessvc.
- **Evidence**: `StandaloneMCPRuntime` (`src/scistudio/ai/agent/mcp/runtime.py`)
  does not implement `get_session_service`, so `resolve_session_service` reads
  "the runtime carries no session service accessor" and builds a detached
  service. That is right for a bridge with no backend behind it, and it is the
  case the fallback exists for.
- **Why it is worth recording**: it is the same gap as F-B1-1 and F-B1-2 — a
  bridge attached to a project on disk that reports none of what the project has
  — and the three want one decision rather than three. A bridge that could see
  the running backend at all would want the focus, the workflow id **and** the
  session service from it; one that cannot should keep reporting none of them.
  `runtime.py` is outside this fix's write set in any case.
- **Suggested title**: `fix(#2254): the standalone MCP bridge reports no focus, no workflow id, and no session service`

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
