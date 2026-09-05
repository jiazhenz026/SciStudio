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

The owner has forbidden new GitHub issues beyond `#2253` and `#2254` for this
dispatch. Every deferral, edge case, cleanup and finding an agent produces is
recorded here under its own agent heading, and every `TODO(#NNNN)` in the code
that defers work to this dispatch cites the entry by heading.

An entry states what was deferred, why it was out of scope, and what would close
it. The manager triages the register when the wave lands.

## S5-B2

### F-1 — The MCP context cannot reach the running GUI's panel registry

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

### F-2 — The spec names three count-assertion sites; there are five

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

### F-3 — The panel message contract is mirrored in Python, not shared

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

### F-4 — The harness browser test needs `npm ci` in `frontend/` and is not in CI

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

### F-5 — The tool group is registered in `__init__.py`, not `server.py`

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

### F-6 — `list_panel_examples` returns nothing until the corpus lands

FR-017 requires the examples corpus to gain at least one displaying and one
producing panel; those entries are T-008's (S5-B4). `list_panel_examples` scans
`src/scistudio/_user_guide/examples/` for directories holding a `panel.json`,
returns them when they exist, and returns an empty list with a diagnostic
pointing at `read_panel_source` on a `core.*` panel when they do not. Both
behaviours are tested. Nothing here needs changing when the corpus lands; this
entry exists so the empty result today is not read as a defect.

### F-7 — The scaffolded panel declares no `provider`

`scaffold_panel` writes a declaration without the optional `provider` field, so a
scaffolded panel's windowed reads are served by the shared bounded data-access
layer. That is the right default (it windows every core type), but a panel for a
package-owned type that needs its own windowing has to add the field by hand
after reading `panel-contract.md`. A `provider` argument on the tool, which would
also scaffold the Python callable, was not added: it is a second file in a second
language and a second thing to get wrong on the first call.

**What would close it**: a follow-up `provider=` argument on `scaffold_panel`
once there is a real panel that needs one, or a worked example in the corpus.
