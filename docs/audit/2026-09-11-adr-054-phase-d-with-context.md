---
title: "ADR-054 Phase D With-Context Audit — Panel Python And MiniApps"
status: Final
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 51
  - 53
  - 54
  - 55
related_specs:
  - adr-054-miniapp
  - adr-054-panels
  - adr-053-learning-center
language_source: en
---

# ADR-054 Phase D With-Context Audit — Panel Python And MiniApps

## 1. Change Summary

- Audit kind: `audit-with-context` · Persona: `audit_reviewer`
- Issue: `#2354` · Umbrella PR: `#2368` `[DO NOT MERGE]`
- Audited tree: `audit/2354-phase-d-context` @
  `/Users/jiazhenz/SciStudio/.worktrees/2354-audit-context`
- Audited diff: `git diff feat/2294-panels-phase-b...HEAD` —
  122 files, +14162 / −397
- Governing spec: `docs/specs/adr-054-miniapp.md` (FR-001..FR-040,
  SC-001..SC-007), checklist `docs/planning/adr-054-phase-d-checklist.md`
- Gate ledger: `.workflow/records/2354-feat-2354-miniapp-phase-d.json`

**Recommendation: pass-with-fixes.**

The implementation is real. Every one of FR-001..FR-040 has code behind it, the
process host is a genuine subprocess with a genuine kill-the-tree handle, and
the tests that matter most — setup-once, binary results, author exceptions,
timeouts, crash, the child process that must not survive, the child that must
exit when the backend pipe closes — launch real interpreters and assert on real
pids rather than on mocks. The Phase B failure mode the brief warns about (many
tests sharing one wrong assumption) does not repeat at the process or payload
layer; `panels/miniapp.py::_wire` is explicitly written against that class of
bug and `test_setup_receives_the_target_as_its_recorded_type` verifies it.

Two requirements are nonetheless not delivered as written, one of them with a
test that asserts something other than what it claims. The gate ledger carries
no check, test, docs, commit, or PR evidence at all, so nothing in §10 of the
checklist is yet true.

## 2. Verification Performed

| What | Result |
|---|---|
| `pytest tests/panels tests/api/test_panel_call_route.py tests/api/test_miniapp_create.py tests/api/test_user_library_panel_promotion.py tests/api/test_ws_client_identity.py tests/ai/test_mcp_panels_tools.py` (scistudio env, clean `HOME`, `-n0`) | 235 passed, **1 failed** — see F-002 |
| Same single test re-run 5× in isolation | 5 passed — confirms a race, not a defect in the code under test |
| `pytest tests/agent_provisioning tests/ai/test_mcp_fastmcp.py tests/ai/test_finish_ai_block_skeleton.py tests/contracts tests/cli/test_mcp_bridge.py tests/cli/test_install.py tests/packaging/test_wheel_skills.py tests/tutorials` | all passed (MCP tool counts 52 / 38 consistently bumped) |
| `npx vitest run` over every Phase D frontend area | 79 files, 873 tests passed |
| `docs/architecture/ARCHITECTURE.md` | **untouched** — correct |
| Gate ledger evidence | `check_events: 0`, `test_events: 0`, `docs_events: 0`, `commit: null`, `pull_request: null` |

## 3. Findings

Ordered by severity.

### F-001 (P1) — FR-033's "expand the collapsed column first" is not implemented, and its test asserts a flag nothing reads

FR-033: *"Opening the list while the column is collapsed, as the tutorial route
of FR-040 can, MUST expand the column first."*

`frontend/src/components/DataPreview.tsx:93-95`:

```ts
export function openAllPreviewers(): void {
  useAppStore.setState({ previewCollapsed: false });
```

with the comment at line 83 claiming *"`ProjectWorkspace` owns the panel handle
that turns that flag into an expanded column."* It does not. Grepping every
non-test source for `previewCollapsed` finds exactly four consumers: the
slice's own initial value and `togglePreview` (`store/uiSlice.ts:17,110`), the
persist whitelist (`store/index.ts:95`), and the type declaration
(`store/types.ts:366`). `ProjectWorkspace.tsx:525-533` has a `paletteCollapsed`→
`leftPanelRef.collapse()/expand()` effect, and line 538 adds the new
`previewPanelRef` — but that ref is passed only to `useMiniAppPreviewColumn`
(line 539) and to the panel element (line 779). Nothing anywhere reads
`previewCollapsed` to call `panel.expand()`.

The dangling flag itself is pre-existing (Ctrl+D has toggled a flag nobody reads
since before this branch). What is new in Phase D is *depending* on it for a
normative MUST, and asserting the dependency in a test that cannot see the
failure:

`frontend/src/components/__tests__/DataPreviewAllPreviewers.test.tsx:148-160`

```ts
it("expands a collapsed column before showing the list (FR-033)", () => {
  ...
  useAppStore.setState({ previewCollapsed: true });
  ...
  expect(useAppStore.getState().previewCollapsed).toBe(false);
});
```

The test renders `DataPreview` alone, never mounts a `ResizablePanel`, and
asserts the store flag flipped. That is a restatement of the implementation, not
evidence that a column expanded. It is exactly the shape the brief names: the
fixture encodes the same wrong assumption as the code.

**Failure scenario.** A reader collapses the preview column (drag it shut, or
Ctrl+D once the flag is wired). They start `welcome-to-scistudio` and reach the
`where-previewers-live` step. `applyStepRoute` dispatches `previewers` →
`openAllPreviewers` → the store flag flips and the list mounts *inside a column
that is still zero-width*. The step's `previewer_palette` highlight rings an
element of zero size. The tutorial appears to do nothing, which is the precise
failure `targets.ts` is written to make impossible (its own docstring, line
276-281, says so).

**Fix.** Either add the missing `previewCollapsed` → `previewPanelRef` effect in
`ProjectWorkspace` (which also repairs Ctrl+D), or have `openAllPreviewers`
publish through the same channel `useMiniAppPreviewColumn` already holds. The
test must mount the panel and assert `panel.isCollapsed() === false`, or assert
on the expand call, not on the flag.

**Verdict: FR-033 PARTIAL.**

### F-002 (P2) — `test_close_stops_and_deregisters_the_process` is racy and will fail CI intermittently

`tests/panels/test_miniapp_context.py:144-158`. Observed failing in a full-suite
run, passing 5/5 in isolation:

```
assert registry.get_handle('panel-context', 'context-pc-dc57…') is None
E   AssertionError: assert <PanelProcessHandle object …> is None
```

The test polls until the pid is gone (up to 10 s) and then asserts
deregistration *immediately*. Since `PanelContexts._detach`
(`src/scistudio/panels/contexts.py:137-150`) now runs `process.stop()` on its
own thread — correctly, for SC-005 — the ordering inside
`PanelProcess.stop()` is `_terminate_tree()` (pid disappears) → `_reap()` →
state → `_fail_pending()` → `_deregister()` (`process.py:330-348`). The pid can
vanish before the detach thread reaches `_deregister`, and under load it does.

**Failure scenario.** CI, under `-n auto`, fails this test on a run where
nothing changed, and the next agent spends a cycle chasing a non-defect. The
production behaviour is correct; only the assertion is unsynchronised.

**Fix.** Poll for the handle the way the test already polls for the pid, or
expose a join on the stop thread for tests.

### F-003 (P2) — SC-005's API-level responsiveness test does not exist, and the call route's threading model makes the criterion doubtful

Spec §4.4 requires *"An API responsiveness test while a `panel.py` hangs and
while one crashes"*, and SC-005 requires *"the API answers a health request
within one second in 100% of the responsiveness tests."*

The only test in this area is
`tests/panels/test_miniapp_context.py:435::test_closing_a_hanging_panel_answers_at_once`,
which exercises the **store lock** during a hung `teardown`. It never starts an
app, never issues an HTTP request, and never has a `call` in flight. No test in
the diff issues any HTTP request while a `panel.py` call is hanging.

The gap matters because the mechanism is plausibly broken. `panel_call`
(`src/scistudio/api/routes/panels.py:641`) is a **sync `def`** endpoint, so
FastAPI runs it on AnyIO's default thread limiter (40 threads), and it blocks
there on `PanelProcess.call` → `job.done.wait(call_timeout())` — 60 s by default
(`process.py:390-394`). FR-011 permits 16 waiting calls *per context*, and
nothing caps calls across contexts.

**Failure scenario.** A user has three MiniApps open. One `panel.py` enters an
infinite loop in a called function. Its page keeps firing calls on slider moves;
16 queue up plus one in flight. A second MiniApp's page does the same. At 40
in-flight `POST …/call` requests the AnyIO thread limiter is exhausted, and
every other **sync** route in the application stops being served — including
`GET /api/runs/_health` (`src/scistudio/api/routes/runs.py:50-51`, a sync `def`).
SC-005 fails and the workbench appears frozen, though the panel host itself is
behaving exactly as FR-011 specifies.

**Fix.** Add the test §4.4 asks for (a `TestClient` request against a live app
while a fixture `panel.py` blocks), and either make `panel_call` `async def` and
await `asyncio.to_thread`, or bound concurrent in-flight calls application-wide
rather than per context.

### F-004 (P2) — the Windows half of FR-008 / FR-013 / SC-004 has no evidence anywhere

SC-004 says *"in 100% of lifecycle tests **on Windows and POSIX**"*, and §4.4
repeats *"including the process lifecycle on Windows and POSIX runners"*.

The POSIX side is genuinely proven —
`tests/panels/test_panel_process.py:242::test_child_process_is_killed_on_stop`
spawns a real grandchild via `subprocess.Popen` inside `setup`, then asserts
`not psutil.pid_exists(child_pid)` within 10 s, and
`:365::test_shutdown_terminate_all_ends_the_panel_tree` does the same through
the registry's `terminate_all`. That is real evidence for SC-004 on this
platform.

The Windows path is a different code path entirely — `PanelProcessHandle._stop`
takes the Job Object branch when `self.pgid is None`
(`process.py:157-165`), and `live_members` calls
`job_active_process_count` (`process.py:110-114`). Every test that would
exercise a process tree is `@pytest.mark.skipif(sys.platform == "win32")`, and
`.github/workflows/ci.yml` is `runs-on: ubuntu-latest` for every job. So the
Windows branch of the handle has never been executed by any test, on any
runner, and SC-004's stated scope cannot be claimed.

**Failure scenario.** A Windows user opens a MiniApp whose `panel.py` starts a
worker process. `create_job_object` returns `None` on an unexpected API failure;
`_stop` then falls to `terminate_tree(self.pid, grace)`, which does not reach a
grandchild that reparented. Ten seconds after the tab closes a process of the
tree is still alive, and nothing would have caught it.

**Fix.** Either state in the checklist and the spec that SC-004 is claimed for
POSIX only pending a Windows runner (tracked), or add a Windows job. Do not
leave the criterion asserting a platform nothing tests.

### F-005 (P2) — the gate ledger carries no evidence of any kind

`.workflow/records/2354-feat-2354-miniapp-phase-d.json`:

```
check_events: []   test_events: []   docs_events: []
guard_events: []   reconcile_events: []
commit: null       pull_request: null
strictness_tier: null
```

Checklist §5 has both hook rows `[ ]`, §4 has "Dispatch prompts created …" `[ ]`,
and every row of §10 Final Readiness is `[ ]`. Per AGENTS.md §3.1 this work is
not complete and, per §3.9, not done. Nothing here contradicts the code; the
point is that at this moment the *evidence* half of the audit question — "is the
evidence real?" — has no answer, because there is none.

Note also that `gate_record check` has not observed the diff, so the scope
violation in F-006 has not been surfaced by the tooling either. Per the
"Gate check after commit" rule, run `check` after the integration commits, not
before.

### F-006 (P2) — three files fall outside the ledger's declared scope

Matching every changed path against `declared_scope.include` (ten entries) plus
the seven `scope_events` amendments:

| File | Why it is out |
|---|---|
| `src/scistudio/engine/gui_presence.py` (new, 56 lines) | scope declares only `src/scistudio/engine/runners/process_handle.py` under `engine/` — which, note, this diff does not touch at all |
| `src/scistudio/ai/agent/system_prompt.py` | scope declares `src/scistudio/ai/agent/mcp/**` only |
| `docs/cli-integration.md` | scope declares only the two `docs/specs/` files and the checklist |

All three are load-bearing and correct changes — `gui_presence` is the shared
presence registry FR-013 and FR-030 both need and is properly placed under
`engine/` for the import-linter contract; the other two are the tool-count and
skill-count surfaces that must move when an MCP tool and a skill are added.
The defect is the declaration, not the code.

**Failure scenario.** `gate_record check` reports `scope.out-of-scope` on three
paths and the PR gate exits non-zero, at the point where the manager expected
a clean pre-PR finalize.

**Fix.** `gate_record amend --add-include` for the three patterns before
`check`. Also drop or use the two declared-but-untouched entries
(`engine/runners/process_handle.py`, and `docs/specs/adr-054-miniapp.md`, whose
`status:` is still `Draft` although checklist §2 lists it in scope for a status
change).

### F-007 (P3) — FR-023 is narrowed to the open workflow, and the narrowing is not in the checklist's Deferred work

FR-023 requires the dialog to ask for *"the data (a block output **in the open
project**)"*. `frontend/src/miniapps/CreateMiniAppDialog.tsx:94-101` says so
itself:

```
 * The scope is the OPEN workflow. FR-023 says "a block output in the open
 * project" …
 * TODO(#2288): offer every workflow's outputs here once a panel-independent
 *   source listing exists;
```

The deviation is honest and tracked to `#2288`, which is better than hiding it.
Two things are still wrong with it. First, the TODO does not carry the format
AGENTS.md §3.6 requires — there is no `Out of scope per <ADR/spec/PR/owner
decision>.` line and no `Followup: <URL>` line. Second, checklist §2 "Deferred
work" lists exactly one deferral (the e2e scenario) and does not mention this
one, so an owner reading the checklist would believe FR-023 shipped whole.

**Failure scenario.** A user with two workflows opens New MiniApp from the
toolbar while workflow A is on the canvas, and cannot reach the output of
workflow B that they actually want — with no explanation on screen. The target
picker (FR-034) *can* reach it, so the two entries to the same feature disagree.

**Fix.** Add the deferral to checklist §2 and reformat the TODO; or list the
project's workflows, which `GET /api/panels/miniapps/{id}/sources` already
proves is cheap.

### F-008 (P3) — `test_close_for_disconnected_client_stops_the_process` does not test what its name says

`tests/panels/test_miniapp_context.py:176-182`:

```python
def test_close_for_disconnected_client_stops_the_process(tmp_path: Path) -> None:
    ...
    store.close_for_client("ws-9")
    assert context.context_id not in store.contexts
```

The name promises the process stopped; the body asserts only that the context
left the dictionary. Every neighbouring lifecycle test in the same file
(`test_project_switch_closes_and_stops`, `test_close_stops_and_deregisters_…`)
polls `psutil.pid_exists`. This one does not.

**Failure scenario.** A future refactor makes `close_for_client` drop the
context without detaching the process — the FR-013 leak the whole grace-period
machinery exists to prevent — and this test still passes, because the context is
still absent from the map. The test name is then a false guarantee in the
suite's own index.

**Fix.** Capture the pid and poll it out, as the sibling tests do.

### F-009 (P3) — a stale integration TODO and a now-unnecessary `type: ignore`

`src/scistudio/ai/agent/mcp/tools_panels.py:146-152`:

```python
# TODO(#2354): drop the type: ignore once the realtime slice's
#   ``scistudio.engine.gui_presence`` (Phase D contract §2.1) is on the
#   integrated branch …
from scistudio.engine import gui_presence  # type: ignore[attr-defined]
```

`src/scistudio/engine/gui_presence.py` **is** on the integrated branch. The TODO
describes a condition that no longer holds, and the suppression now hides
nothing. Left in, it will read to the next reader as a real unresolved gap.

**Fix.** Delete both lines. (Also worth confirming mypy's
`warn_unused_ignores` is not on, or this is a CI failure rather than a nit.)

### F-010 (P3) — a freshly opened MiniApp tab reloads itself once, killing and restarting a process nobody asked to restart

`frontend/src/miniapps/MiniAppTab.tsx:48-53`:

```ts
useEffect(() => {
  if (changeSeq === 0) return;
  const timer = setTimeout(() => setReloadKey((v) => v + 1), MINIAPP_RELOAD_DEBOUNCE_MS);
  return () => clearTimeout(timer);
}, [changeSeq]);
```

`panelFilesChangedSeq[panelId]` is a monotonic per-panel counter in the UI slice
that is never reset per tab. The guard is `changeSeq === 0`, not "changed since
this pane mounted".

**Failure scenario.** The agent finishes writing `threshold_explorer`; the
counter for that panel id is now, say, 12. The user closes the tab, and later
opens the same MiniApp on a different block output from the MiniApps tab. The
new pane mounts with `changeSeq === 12`, the effect fires, and 500 ms later the
tab remounts `PanelFrame`: a new context, a new frame, and a second `panel.py`
process, with the first one's `setup` work — which FR-007 exists to make
expensive-once — thrown away. For a MiniApp whose `setup` loads a large stack
the user sees it start, blank, and start again.

**Fix.** Record the counter value at mount and compare against it, rather than
against zero.

### F-011 (P3) — `promote_to_user_library` is still dropped from the rendered tool catalogue, beside a new comment warning about exactly that

`src/scistudio/ai/agent/system_prompt.py:185-196` gains, in this diff:

```python
# ADR-054 FR-029 — `category:panels`. This map is the whole of what the
# prompt renders: `grouped` is built from its keys, so a category
# missing here drops its tools from the catalogue silently.
"panels": "### (f) MiniApps & panels",
```

`tools_library.py:193` tags `promote_to_user_library` as `category:library`, and
`library` is not in `category_titles`. The render loop iterates
`category_titles.items()` (line 212), so that tool is silently absent from every
system prompt. The diff's own comment names the bug class; the one existing
instance of it is two lines away and untouched. Phase D also updated the *static
fallback* in `src/scistudio/_skills/scistudio/SKILL.md` to list `Library (1)`,
so the fallback and the live catalogue now disagree.

This is an ADR-053 defect, not an ADR-054 one, so fixing it here would widen
scope. It should be a one-line follow-up issue rather than silence.

## 4. Requirement-By-Requirement Verdict

| FR | Verdict | Evidence |
|---|---|---|
| FR-001 | IMPLEMENTED | `panels/descriptor.py:105,114`; `tests/panels/test_panel_python_detection.py:32-62`. (Landed in the Phase B base; the tests are new here.) |
| FR-002 | IMPLEMENTED | `descriptor.py:134-136,150`; `test_panel_python_detection.py:64-99` — asserts `panel.py` is detected and never imported |
| FR-003 | IMPLEMENTED | `contexts.py:89-95` (`provides`), `routes/panels.py:649-650`, `panels/bridge.ts:174`, `sdk/1/scistudio-panel.js:236`; `test_miniapp_context.py:241,467`, `test_panel_sdk.py:44,51`, `test_panel_call_route.py:185` |
| FR-004 | IMPLEMENTED | `contexts.py:287-344`; `panels/miniapp.py:49-80` (latest successful run, type/subtype refusal); context id `secrets.token_hex(16)` = 128 bits |
| FR-005 | IMPLEMENTED | `panels/miniapp.py:137-152` |
| FR-006 | IMPLEMENTED | `process.py:_process_env`, `start_panel_process`; interpreter matches `engine/runners/local.py:321` (`sys.executable`); `test_miniapp_context.py:283,301` |
| FR-007 | IMPLEMENTED | `bootstrap.py:_import_panel`, `_collect_callables`, `_reconstruct`; `test_panel_process.py:129` (imported name not callable), `:265` (class not callable) |
| FR-008 | IMPLEMENTED (POSIX) | `process.py:PanelProcessHandle`; `api/app.py:78,245`; `test_panel_process.py:365`. Windows branch untested — F-004 |
| FR-009 | IMPLEMENTED | `bootstrap.py:_reserve_channel` dups fd 0/1 then `dup2(2,1)`, so `print` cannot reach the channel; `test_panel_process.py:210,350` |
| FR-010 | IMPLEMENTED | `routes/panels.py:641-684`; opaque-origin refusal is global (`panels/security.py:12`) and covers POST |
| FR-011 | IMPLEMENTED | `process.py:372-410`, `bootstrap.py:_result_frame`; `test_panel_process.py:102,141,158` |
| FR-012 | IMPLEMENTED | `process.py:236-244`; `test_panel_process.py:187` |
| FR-013 | IMPLEMENTED | `process.py:stop`, `contexts.py:close_for_client`, `api/ws.py:_close_panel_contexts_after_grace`; `test_ws_client_identity.py`. Windows caveat per F-004 |
| FR-014 | IMPLEMENTED | `contexts.py:restart`, `process.py:status/log_tail`, `MiniAppTab.tsx:81-89`; `test_panel_process.py:171` |
| FR-015 | IMPLEMENTED | `process.py:resident_memory` sums the tree; `useMiniAppProcess.ts` polls at 5 s; `test_panel_process.py:286` |
| FR-016 | IMPLEMENTED | `scistudio-panel.js:236-268`; `test_panel_sdk.py:35,58,82` |
| FR-017 | IMPLEMENTED | `panels/files.py:ASSET_SUFFIXES` excludes `.py`; `test_panel_call_route.py:215` |
| FR-018 | IMPLEMENTED | `store/tabSlice.parts/miniAppTabActions.ts`; `store/__tests__/miniAppTab.test.ts` |
| FR-019 | IMPLEMENTED | `store/index.ts:112` persists file tabs only; `tabHelpers.ts:60`; `MiniAppTab.tsx` layer keeps panes mounted |
| FR-020 | IMPLEMENTED | `MiniAppTab.tsx:useMiniAppPreviewColumn`; `ProjectWorkspace.tsx:538-539,779` |
| FR-021 | IMPLEMENTED | `miniapps/MiniAppToolbar.tsx` |
| FR-022 | IMPLEMENTED | `panels/watcher.py` (tier filter, page-file filter, 500 ms debounce) + `api/ws.py:PANEL_FILES_CHANGED` + `MiniAppTab.tsx:48`; see F-010 for the mount-time nit |
| FR-023 | **PARTIAL** | `CreateMiniAppDialog.tsx` — open workflow only, not the open project. F-007 |
| FR-024 | IMPLEMENTED | `routes/panels.py:create_miniapp` (availability first, then template, then brief, then session); `panels/miniapp_create.py`; `test_miniapp_create.py:206,229,252` |
| FR-025 | IMPLEMENTED | `ProjectWorkspace.tsx:790-802` opens the tab from the create result; `CreateMiniAppDialog.test.tsx` |
| FR-026 | IMPLEMENTED | `panels/template/index.html` + `panel.py` (no-op `setup`); `test_miniapp_create.py:272,290` |
| FR-027 | IMPLEMENTED | `miniapp_create.py:compose_create_brief` — names the skill, the directory confinement, keeping id/contexts/types, and `validate_panel` |
| FR-028 | IMPLEMENTED | `_skills/scistudio/scistudio-write-miniapp/SKILL.md`; `agent_provisioning/skills.py:_SKILL_NAMES`; `test_skills.py`, `test_wheel_skills.py` |
| FR-029 | IMPLEMENTED | `ai/agent/mcp/tools_panels.py`; `test_mcp_panels_tools.py` (13 tests) |
| FR-030 | IMPLEMENTED | `tools_panels.py:open_miniapp` + `api/ws.py:PANEL_OPEN_MINIAPP` + `useWebSocket.parts/handleMiniApp.ts`; `test_mcp_panels_tools.py:277,367`, `test_ws_client_identity.py:35` |
| FR-031 | IMPLEMENTED | `components/ActivityBar.tsx` (slot swap), `miniapps/MiniAppPalette.tsx`; `ActivityBar.test.tsx`, `MiniAppPalette.test.tsx` |
| FR-032 | IMPLEMENTED | `MiniAppPalette.tsx:345-371` uses the shared `DetailPopover`, Promote gated on the project tier |
| FR-033 | **PARTIAL** | `DataPreview.tsx` mounts the unchanged `PreviewerPalette` inside the column with a back control — correct. The collapsed-column expand is not wired. F-001 |
| FR-034 | IMPLEMENTED | `MiniAppTargetPicker.tsx` + `GET /api/panels/miniapps/{id}/sources`; `test_miniapp_create.py:317` |
| FR-035 | IMPLEMENTED | `WorkflowCanvas.tsx` — directional `isDeclaredSubtype`, `producedOutputPorts`, disabled entries with `NO_OUTPUTS_REASON`; `WorkflowCanvas.test.tsx` |
| FR-036 | IMPLEMENTED | `miniapps/ConvertToBlockDialog.tsx`, `routes/panels.py:convert_miniapp`, `miniapp_create.py:compose_convert_brief`; `test_miniapp_create.py:365` asserts the MiniApp is unchanged |
| FR-037 | IMPLEMENTED | `Toolbar.parts/FileOperationsGroup.tsx`; `FileOperationsGroup.test.tsx` |
| FR-038 | IMPLEMENTED | `palette/tips/tipPool.ts` — four tips incl. All Previewers; `tipPool.test.ts` |
| FR-039 | IMPLEMENTED | `api/routes/user_library.py` directory route — confined walk, no symlink follow, staged rename, degrade-to-copy; `test_user_library_panel_promotion.py` (11 tests) |
| FR-040 | IMPLEMENTED | `LearningCenter.parts/targets.ts`, `useLearningCenter.ts`, both tutorial YAMLs, `tutorials/manifest.py`, `docs/specs/adr-053-learning-center.md:1527`. Owner comments kept. Its runtime effect depends on F-001 |

### Success criteria

| SC | Verdict |
|---|---|
| SC-001 (template tab < 2 s) | not measured; the ordering FR-024 requires is implemented and tested |
| SC-002 (< 50 ms median call) | not measured |
| SC-003 (no process, no `call` in preview/interactive) | **MET** — `test_miniapp_context.py:241,467`, `test_panel_sdk.py:44,51`, `test_panel_call_route.py:185` |
| SC-004 (nothing alive 10 s after close) | **MET on POSIX**, unproven on Windows — F-004 |
| SC-005 (health answered in 1 s) | **NOT MET as stated** — no API-level test exists, and the threading model is doubtful. F-003 |
| SC-006 (e2e) | deferred with the e2e scenario, declared in checklist §2 |
| SC-007 (four entries reach the dialog) | MET — MiniApps tab, New menu, canvas context menu, and the agent path each have a test |

### Acceptance scenarios in spec §2 with no test

Each is named rather than summarised:

- **US1 AS3** ("the tab reloads within two seconds") — the 500 ms frontend
  debounce and the 500 ms watcher debounce are each tested, but nothing asserts
  the end-to-end budget. Acceptable.
- **US5 AS3** — the "control that returns to the preview" is tested
  (`all-previewers-back`); the "expand a collapsed column" half is not (F-001).
- **US7 AS4** ("browser reloaded or closed → context closes, process ends after
  the grace period") — the grace-period function is tested with a stubbed store
  (`test_ws_client_identity.py:92`), and `close_for_client` is tested without
  asserting the process died (F-008). No test connects the two.
- **Edge case** "the agent changes `contexts` or `types` … a MiniApp whose
  `types` no longer matches its open target is closed with a message" — I found
  no implementation and no test. Edge cases are not FRs, so this is noted, not
  scored.

## 5. Things Done Well (recorded so a later reader does not re-litigate them)

- `bootstrap.py:_reserve_channel` reserves fd 0/1 *before any author code runs*
  and points fd 1 at the log. This is the stronger form of FR-009: a C-level
  write or a child process inheriting stdout cannot corrupt the frame protocol.
  Many implementations would have redirected `sys.stdout` only.
- `PanelProcessHandle._posix_group_members` signals each member by pid rather
  than `killpg`, with a start-time tolerance, and cites the prior incidents
  (#2292 / #1542) it is modelled on.
- `PanelContexts.close_all` stops processes in parallel off the store lock and
  joins once with a bounded wait — the right shape for SC-005, and the reason it
  is right is written down.
- `panels/miniapp.py:_wire` documents the exact bug it prevents (a bare
  `DataObject` reaching `setup` when the type chain lived only on the catalog
  record) and is covered by a test that asserts the reconstructed class.
- The `_CALL_RESPONSE` OpenAPI block uses `anyOf` and explains why `oneOf` would
  reject the very body it describes.
- `user_library.py`'s directory route restates ADR-053 FR-017's ordering and its
  reason, refuses symlinks in both directions, and lands by rename.

## 6. Recommendation

**pass-with-fixes.**

Required before the final PR:

1. F-001 — wire the collapsed-column expand, and replace the flag assertion with
   one that can fail.
2. F-005 — run `gate_record check` after the integration commits, then
   `finalize`; §5 and §10 of the checklist must carry artifacts.
3. F-006 — amend the ledger scope for `gui_presence.py`, `system_prompt.py`, and
   `docs/cli-integration.md` before `check`.
4. F-002 — desynchronise the deregistration assertion.

Strongly recommended:

5. F-003 — add the §4.4 responsiveness test; decide on `async def` for
   `panel_call`.
6. F-004 — say which platforms SC-004 is claimed for, or test Windows.
7. F-007, F-008 — record the FR-023 deferral in checklist §2; make the
   disconnected-client test assert the process.

Housekeeping: F-009 (stale TODO), F-010 (spurious first reload), F-011
(follow-up issue for the dropped `library` catalogue category). Separately, the
integration branch is one commit behind `feat/2294-panels-phase-b` (`64efc4fc`,
"answer the six review findings"); rebase before opening the final PR so those
fixes are not lost in the stack.
