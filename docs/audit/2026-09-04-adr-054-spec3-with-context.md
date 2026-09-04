---
title: "Audit — ADR-054 spec 3 Explore Session runtime (with-context)"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
related_specs:
  - adr-054-explore-session
language_source: en
---

# Audit — ADR-054 spec 3 Explore Session runtime (with-context)

Audit mode: **with-context** (agent `S3-E2`, `audit_reviewer` persona).
Subject: `track/adr-054-spec3-explore-session` as integrated at `348228d8a`,
the candidate behind umbrella PR #2241, closing #2240.
Audit branch: `audit/2240-with-context`.
Gate ledger: `.workflow/records/2240-2240-audit-with-context.json`.
Base for every diff in this report:
`origin/track/adr-054-spec2-dependency-analysis`.

**Verdict: block.**

The subsystem is real and large — 45,932 added lines across 87 files, twelve
explore modules, twenty-three routes, and a test suite that runs 1,680 tests
green in this worktree with no failures. Several of the hardest things in the
spec are genuinely done and genuinely proved: the plumbing commits leave the
working tree and the branch alone under a thirty-commit test, the interrupt
ends a real spinning cell on a real ipykernel, the `explore_sessions` migration
copies every legacy row, and the layer rule has a planted-violation control.
Both P1s the adversarial pass raised — the lineage writer and the environment
snapshot store, each "a module built correctly and called by nothing" — are
now wired for real, and I traced each from the route a person actually reaches
rather than from a test.

I am recommending block anyway, for six reasons. One is mechanical and
embarrassing: the integration commit `348228d8a` committed **unresolved merge
conflict markers into production source**, inside a docstring where Python
still parses them, which is why every test passed and why CI's Lint & Format
job is red right now. The other five are the same defect class the adversarial
pass twice identified and the fix agent twice closed — a module built correctly
and called by nothing — surviving in five more places nobody looked. One of
them loses the person's data: FR-055's durable-output half has no production
caller, so the retention sweep that runs automatically after every successful
workflow run treats every object a session produced as a reclaim candidate,
outside the per-workflow floor guard that protects everything else.

None of the six needs a redesign. Four are a missing call site.

---

## 1. What I checked, and how

- Read the spec (`docs/specs/adr-054-explore-session.md`, 1,139 lines), the
  manager checklist, all fourteen dispatch prompts, all fifteen gate ledgers,
  issue #2240, and the twenty commits on the track branch.
- Walked FR-001 to FR-060 clause by clause against the code and against the
  test that claims to prove it, reading each test's assertions rather than its
  name.
- Diffed each of the six protected core paths and read the pre-existing suite
  that guards it.
- Ran the dispatch's four checks, plus `ruff format --check`,
  `scripts/deferral_scan.py`, and the pre-existing lineage/versioning suites
  the agent rows named.
- Read the live CI state of PR #2241 rather than the claims about it.

Everything below that says "verified" means I reproduced it in this worktree.

### 1.1 Check results

| Check | Result |
|---|---|
| `pytest tests/explore tests/api/test_explore_routes.py tests/blocks tests/engine tests/core tests/architecture -q` | exit 0 |
| `pytest` over the spec-3 suites (explore, explore routes/mount/branch-switch, interaction policy, block version source, lineage table, ref commits, architecture) | **1,680 passed, 84 skipped, 0 failed** |
| `ruff check src/scistudio/explore` | All checks passed |
| `mypy src/scistudio/explore` | Success, 12 source files |
| `ruff format --check .` (the CI command) | **FAIL — 1 file would be reformatted** |
| `gate_record check --mode local --base ... --head HEAD` | "no gate ledger found" on this branch until I ran `init` |
| `scripts/deferral_scan.py --check` | **FAIL — `later: 26 > ratchet 21`** |
| CI on PR #2241 @ `348228d8a` | **Lint & Format FAILURE, Deferral ratchet FAILURE, Verify Workflow Compliance FAILURE**; Test (3.11) and Test (3.13) had not completed |

The 84 skips are all `jupyter_client`/`ipykernel` gates. The shared `.venv`
does not have them despite FR-059 adding them to `pyproject.toml`, so roughly
5% of the explore suite — including every real-kernel proof for FR-013,
FR-051, FR-053 and SC-002/SC-005 — does not run here. CI installs
`-e ".[dev]"` and would run them; CI's Test jobs have not completed on this
head, so **no run of the real-kernel half exists anywhere I can point at.**
The manager's own drift log flagged this and its follow-up ("verify the
interrupt test actually ran in CI before calling FR-013 covered") is still
open.

---

## 2. FR coverage — FR-001 to FR-060

`covered` = implemented and proved by a test that really asserts the
obligation. `partial` = a named clause is missing or is proved only by a test
that supplies the thing under test. `impl-no-test` = built, unproved.

| FR | Obligation (short) | Implementation | Test | Verdict |
|---|---|---|---|---|
| 001 | Notebook in `explore/`; **API addresses it by project-relative path**; ref-safe id in metadata; one kernel per notebook | `explore/session.py:1449,1814,2381,2388,1763`; `api/project_layout.py:41` | `test_explore_session.py::test_the_explore_directory_is_created_…`, `::…_session_id_is_written_into_the_notebook_and_read_back`, `::…_returns_that_session`; `test_explore_ref_commits.py::test_session_ref_refuses_ids_git_would_refuse` | **partial** — every route is `/sessions/{session_id}` with no `:path` converter, so a project-relative path (always contains `/`) cannot address a session over HTTP. Clause dropped without a record. `test_the_session_id_is_a_ref_safe_component` is tautological. |
| 002 | Open over block outputs / a file / a paused run; refuse a block with no outputs | `session.py:1690,1727,1748`, `NothingToExploreError:173`; `routes/explore.py:838,305` | `test_explore_session.py::test_opening_over_a_block_with_no_outputs_is_refused`; `test_explore_routes.py::test_nothing_to_explore_is_a_refusal_with_a_reason` | covered — `open_over_file` does not confine the path to the project tree |
| 003 | Bind to the most recent **completed** run; record which | `session.py:2258,2283`; recorded `:1566` | `test_explore_session.py::test_the_resolver_binds_the_most_recent_completed_run`; `test_session_lineage.py::test_a_session_opened_over_a_run_records_the_run_it_was_opened_over` | covered — the "completed" filter is never negatively tested (both seeded runs are completed) |
| 004 | First cell loads each input; does not run automatically | `session.py:2343,2373,1814` | `test_explore_session.py::test_the_first_cell_names_every_output_port`, `::test_the_first_cell_does_not_run_when_a_session_opens` | covered |
| 005 | Persist edits + re-analyse; **reload when the file changes on disk from outside** | edits `session.py:511,1251`; reload `session.py:562 reload_if_changed` | edits covered; reload tested only by tests that call the method by hand | **partial (P1)** — `reload_if_changed` has **zero production callers**. No watcher, no route, `read_cells` does not call it. An external edit is never noticed. |
| 006 | Close ends the kernel, writes, commits if changed; list every notebook + kernel flag | `session.py:1937,1966,1341,1887` | `test_explore_session.py::test_closing_commits_only_when_the_notebook_changed_…`, `::test_listing_reports_every_notebook_and_whether_it_has_a_kernel` | covered — `glob("*.ipynb")` is non-recursive |
| 007 | ipykernel from the bundled interpreter via `jupyter_client`; service is the only client | `explore/kernel.py:353,547,742,425`; `session.py:1500` | `test_kernel_session.py::test_start_launches_a_real_ipykernel_process`, `::test_the_kernel_module_imports_no_jupyter_server` | covered |
| 008 | Explore imports no api/ai/engine; engine imports no explore | structural; `session.py:47-77` | `test_layer_deps.py::test_explore_never_imports_upward_at_any_depth`, `::test_engine_does_not_import_explore` | covered (see FR-060 for the depth test's real reach) |
| 009 | Bridge: fingerprints, window via the real preview provider, bindings, memory; never a cell | `kernel_bridge.py:243,420,342,375,1019,1352`; `kernel.py:708` | `test_kernel_bridge.py::test_a_bridge_call_leaves_no_cell` (reads the kernel's own history back), `::test_a_window_equals_the_preview_provider` | covered |
| 010 | Three helpers importable at top level; session-mode semantics; mode from an env var | `scistudio/__init__.py:12,24,27`; `notebook_api.py:394,426,473,273,102`; `kernel_bridge.py:594` | `test_notebook_api.py::test_the_helpers_are_the_top_level_ones`, `::test_session_mode_declares_without_writing` | covered |
| 011 | Packaged mode reads/writes the exchange folders through the adapters | `notebook_api.py:660,698,826,850`; `blocks/code/backends/notebook.py:208` | `test_notebook_api.py::test_packaged_output_writes_through_the_adapters`, `::test_the_same_notebook_runs_in_both_modes` | covered |
| 012 | `%pip`/`!pip`/`%conda` triggers a new snapshot after the run, stored by reference | `kernel_bridge.py:562`; `session.py:1104-1108,936` | `test_kernel_bridge.py::test_an_install_changes_the_snapshot_and_is_stored_once` (real kernel) | covered (skips locally) |
| 013 | Interrupt / restart / stop | `session.py:970,982,1024`; `kernel.py:602,561,581,308` | `test_kernel_session.py::test_interrupt_ends_a_hung_cell_and_the_session_survives`; `test_explore_routes.py::test_interrupting_a_real_kernel_ends_a_hung_cell_through_the_route` | covered **but unrun** — every proof is kernel-gated and CI has not completed |
| 014 | Branch switch retires every kernel **after** writing every notebook; sessions report needs-restart | `session.py:2015`; `routes/explore.py:165`; `routes/git.py:279,661,689` | `test_explore_session.py::test_a_branch_change_writes_every_notebook_before_the_kernels_go`; `test_explore_branch_switch.py` (real ipykernel through the route) | covered |
| 015 | Detect a dead kernel, end the running cell **with an error**, report dead, offer restart | `kernel.py:644,853`; `session.py:1008`; `queue.py:706` | `test_kernel_session.py::test_a_process_killed_from_outside_ends_the_running_cell`; the route-level test **fakes** the death by calling `report_kernel_died()` | **partial** — no test kills a real kernel while a cell is in flight through the queue; the join of the three clauses is unproved |
| 016 | List every live kernel with session, memory, and a way to end it | `session.py:1991,2011,308`; `kernel.py:488`; routes `:1177,1201` | `test_explore_session.py::test_every_live_kernel_is_listed_with_its_session_and_its_memory`, `::test_ending_a_kernel_from_the_list_terminates_its_process` | covered |
| 017 | One queue, one at a time, in order; coalesce a queued-not-started duplicate; never cancel a running request | `queue.py:496,657-661,591,699,718` | `test_queue_and_marks.py::test_a_submission_of_the_running_cell_is_not_coalesced_with_it`, `::test_stopping_cancels_what_is_queued_and_never_the_running_request` | covered |
| 018 | Parse a snippet before queueing; whitelist; refuse naming the panel and the statement; insert nothing on refusal; insert after the current cell | `queue.py:322,223,213,270,158`; `session.py:791,826` | `test_queue_and_marks.py::test_the_whitelist_refuses_every_other_statement_form`, `::test_a_refused_emission_inserts_no_cell`; `test_adversarial_session.py::test_a_freshly_opened_session_inserts_a_panel_emission_after_its_first_cell` | covered |
| 019 | Compare graph-definer vs last-binder before a run; mark out-of-order; run regardless | `session.py:1174,213,629,1091` | `test_queue_and_marks.py::test_an_out_of_order_rerun_still_runs_the_cell`; `test_adversarial_session.py::test_running_a_downstream_cell_first_is_marked_out_of_order` | covered |
| 020 | Keep last-bound-by per session, updated from each observation | `session.py:635,1200,996,1019,1039` | `test_queue_and_marks.py::test_a_name_a_cell_unbinds_leaves_the_last_bound_by_map` | covered |
| 021 | Fingerprint around each run **through the bridge**, hand both to **the dependency-analysis spec's comparison**, record, re-analyse | `session.py:1076,1089,1101,1200,1251`; comparison is `queue.py:449 observe_namespaces` | `test_queue_and_marks.py::test_observation_reports_what_moved_appeared_and_disappeared`; `test_explore_routes.py::test_the_event_sequence_of_a_cell_run` | **partial** — the analysis spec's own `fingerprint.compare_namespaces` has **no caller in `src/`**; the session runs a second implementation, and the two disagree on unobservable names that appeared or differed |
| 022 | Mark the downstream set stale; clear the run cell's marks when its reads resolved in order; enqueue nothing | `session.py:1200` | `test_queue_and_marks.py::test_rerunning_b_marks_it_out_of_order_marks_c_stale_and_runs_nothing`, `::test_marking_alone_enqueues_nothing_at_all` | covered |
| 023 | Exactly three marks; session state; restart resets to never-run | `session.py:191,1293,1003,1020,1041` | `test_queue_and_marks.py::test_a_kernel_restart_resets_every_cell_to_never_run` | covered |
| 024 | run-stale in written order; run-with-upstream = backward slice minus undisturbed cells | `session.py:736,745,780` | `test_queue_and_marks.py::test_run_stale_enqueues_the_stale_cells_in_written_order`, `::test_run_with_upstream_skips_an_undisturbed_upstream_cell` | **partial** — `session.py:786` exempts the *named* cell from the skip rule, which the spec sentence does not. Deliberate, documented, pinned by a test, unratified in the spec. |
| 025 | Freeze panel submissions bound to the running cell's changed set; reads continue; other panels accepted | `queue.py:616,735`; `session.py:869,839` | `test_queue_and_marks.py::test_the_freeze_is_armed_before_the_request_is_visible_as_running` | covered |
| 026 | After a run report the changed names and the updated marks | `session.py:1225,1302` | `test_explore_routes.py::test_the_event_sequence_of_a_cell_run` | covered — the marks half is asserted only against `marks == {}`; no test asserts a non-empty marks payload on the post-run event |
| 027 | Keep outputs on disk; write the notebook before each run | `session.py:1081,1149,1114`; `notebook.py:517` | `test_adversarial_session.py::test_a_cell_run_leaves_its_output_in_the_notebook_on_disk` (real kernel, reads the bytes), `::test_the_notebook_is_written_to_disk_by_the_run_itself` | covered — **the reported P2 is genuinely fixed**; the write path is reached from a real run |
| 028 | One commit per run on `refs/scistudio/explore/<id>`, captured at execution time, outputs stripped, written after the result returns | `session.py:1082,1115,2036,2068`; `_commit_ops.py:208,427` | `test_adversarial_session.py::test_an_edit_after_execution_cannot_change_what_the_commit_carries` (edits from the worker thread while holding the git call) | covered |
| 029 | Plumbing against a temporary index; tree and branch index untouched; never on the branch | `_commit_ops.py:427` | `test_explore_ref_commits.py::test_thirty_commits_leave_the_working_tree_and_index_untouched`, `::test_the_plumbing_path_never_runs_a_working_tree_command`, `::test_refuses_to_write_a_branch_ref` | covered |
| 030 | Retry off the path, never block a run, **report once** | `session.py:2156,2225,2089,139` | `test_explore_session.py::test_a_failing_commit_is_reported_once_and_never_blocks_a_run` | **partial** — `_reported_commit_failure` (`session.py:1434`) is never cleared, so "once" is once per session for ever. `test_adversarial_session.py::test_a_failure_after_a_recovery_is_never_reported_again` **pins the wrong behaviour as expected**. |
| 031 | Ensure packing at a bounded count | `_commit_ops.py:499,191` | `test_explore_ref_commits.py::test_packing_fires_at_the_bound_and_not_before`, `::test_packing_counts_the_ref_not_the_process` | covered |
| 032 | Preserve the analysis record on every write | `notebook.py:693,595` | `test_notebook_store.py::TestRoundTrip::test_the_analysis_record_survives_a_round_trip` (+4 more) | covered — `notebook.py:554 set_analysis_record` has no production caller, so preservation is only exercised on records that arrived in the file |
| 033 | Enabled flag in cell metadata; written when toggled through the API | `notebook.py:504`; `session.py:523`; route `:976` | `test_notebook_store.py::TestEnabledFlag::…`; `test_explore_routes.py::test_toggle_enabled_takes_a_cell_out_of_the_graph` | covered |
| 034 | Environment snapshot stored once per distinct environment, referenced from records | `core/lineage/environment.py:206,116`; `session.py:936,921,999,1108,1583` | `test_session_lineage.py::test_a_cell_run_names_the_environment_it_ran_in`, `::test_the_environment_of_a_second_session_is_stored_once` | covered — **the reported P1 is genuinely fixed**; the store is called from `start_kernel`, `restart_kernel` and the `%pip` path |
| 035 | Report the current notebook commit | `session.py:477,1323,1336` | `test_adversarial_session.py::test_the_reported_commit_follows_the_second_branch_commit` | covered — **the reported P3 is fixed** |
| 036 | Branch commit on request and on close when changed | `session.py:1966,1937,1319`; `_commit_ops.py:521` | `test_explore_session.py::test_closing_commits_only_when_the_notebook_changed_…`; `test_explore_ref_commits.py::test_branch_commit_leaves_the_working_tree_and_staged_work_alone` | covered |
| 037 | Declaration + notebook copy in `blocks/`, discovered by the tier-1 scan | `packaging.py:987,1078-1091,1163,967` | `test_packaged_block.py::test_the_generated_declaration_is_discovered_by_the_registry` (real `BlockRegistry().scan()`) | covered |
| 038 | Ports from the declarations, typed from the bindings, extension from the materialisation layer; **a file-opened session's load line rewritten to a port read** | `packaging.py:534,481,826,1069`; `session.py:694` | `test_packaged_block.py::test_ports_come_from_the_declarations_and_are_typed_from_the_bindings`; the rewrite tests **pass `file_ports` explicitly** | **partial** — `file_ports` is caller-supplied, nothing derives it, `ExploreSession` never records that it was opened over a file, and no frontend caller exists. The default path packages a file-opened session into a block with **no input port** and a hardcoded `scistudio.load("data/raw/…")`. |
| 039 | Refuse a bad slice naming cells/reads; wait for the queue to drain | `packaging.py:645,439,744`; drain `routes/explore.py:1232,1283,1322` | nine refusal tests in `test_packaged_block.py`; `test_explore_routes.py::test_a_packaging_check_waits_for_the_queue_to_drain` (asserts elapsed time, so an early answer fails) | covered — **the reported P2 is fixed**. See P1-4: the refusal list interacts badly with FR-049. |
| 040 | Run the backward slice and nothing else; backend takes a cell selection | `packaging.py:400,1390`; `blocks/code/backends/notebook.py:123,213,258` | unit level covered; the end-to-end `test_a_workflow_runs_the_packaged_block_and_reproduces_the_session` is **skip-gated on `nbconvert`, which is in neither the core nor the dev dependency set** | covered at unit level; the "and nothing else" proof never runs |
| 041 | Block version = the notebook commit; packaging records it | `packaging.py:1219,1042,1350`; `blocks/registry/_spec.py:107` | `test_packaged_block.py::test_the_declaration_records_the_notebook_commit`; `test_block_version_source.py::test_an_opted_in_block_records_its_own_version` | covered |
| 042 | Double-click opens a session on the copy **bound to the node's most recent run inputs**; repackaging replaces in place | in-place `packaging.py:1076-1090`; resolution `packaging.py:1109 reopen_target` | `test_packaged_block.py::test_repackaging_replaces_both_files_in_place` | **partial (P2)** — `reopen_target` has **no production caller**. No route resolves a packaged block to a session; `POST /sessions` with `source:"notebook"` never passes `bound_run`; no resolver returns a node's most recent run inputs. |
| 043 | Leave the exploration notebook untouched | `packaging.py:1071,1065-1092` | `test_packaged_block.py::test_packaging_leaves_the_exploration_notebook_untouched` (byte identity) | covered |
| 044 | `on_new_input` on every interactive block, declared with a default, **overridable on the node**; packaged→replay, authored→ask | `blocks/base/interactive.py:86,129,267,453`; `packaging.py:1374` | `test_interaction_policy.py::TestPolicyResolution::…` (hand-written block, not a generated one) | **partial** — for a packaged block the value is a *packaging-time class choice* (`packaging.py:1186` picks `PackagedNotebookBlock` or `AskingPackagedNotebookBlock`), so a node override `on_new_input="ask"` on a replay-packaged block is inert: the block is not `ExecutionMode.INTERACTIVE`, so `_dispatch` never reaches `resolve_interaction_policy` |
| 045 | Authored block: `ask` = today's behaviour, `replay` ignores the signature | `engine/scheduler/_dispatch.py:542-559`; `interactive.py:453` | `test_interaction_policy.py::TestReplayPolicy::…` + `TestDefaultPreservesExistingBehaviour::…` — drives the real `DAGScheduler._run_interactive` | covered |
| 046 | Packaged block's memory is the packaging commit; ask pauses like an interactive block; the prompt names notebook, commit, inputs | `packaging.py:1482,1512,1530` | `test_packaged_block.py::test_the_ask_prompt_names_the_notebook_the_commit_and_the_runs_inputs` | covered |
| 047 | Confirm carries a commit and runs that commit's slice; **cancel cancels the node and closes the session opened for it** | confirm `packaging.py:1502-1510,1419,1471,1266`; cancel **NONE** | `test_interaction_policy.py::…::test_ask_pause_carries_the_confirmed_notebook_commit_to_compute`; no cancel test | **partial** — the cancel clause is absent. No production code closes an explore session on node cancellation, and the engine cannot import explore. |
| 048 | The pause holds nothing resident and reuses the existing interactive pause | `packaging.py:1500`; `_dispatch.py:505-575` | `test_interaction_policy.py::…::test_the_pause_holds_nothing_resident` | covered |
| 049 | A cell calls a block through an in-kernel adapter, not the workflow runner | `block_call.py:906,963,1163,711,792,846`; `kernel_bridge.py:676,739` | `test_block_call_adapter.py::test_the_block_runs_in_the_calling_process` (+4) | covered at the adapter; see P1-4 for the packaging interaction |
| 050 | An interactive block called from a cell opens its panel **through the session service** and blocks the cell; such a notebook is refused at packaging | blocking `block_call.py:342,432,1221`; refusal `packaging.py:744,751,800` | blocking + refusal proved; the panel test uses a `RecordingChannel` **double** | **partial (P1)** — `InteractionChannel` (`block_call.py:468`) has **no production implementation**. `kernel_bridge.py:671` builds the adapter with `interaction=None`; `set_block_call_adapter` is called only from tests; there is no session event or route to settle a pending interaction. In production the call always raises `InteractionUnavailableError` (`block_call.py:1247`). |
| 051 | A block call writes a `BlockExecutionRecord` FK'd to the session, with `block_io` edges | `block_call.py:202` → `kernel_bridge.py:861` → `session.py:1131,1630,1659` → `lineage.py:311` → `store.py:267` | `test_session_lineage.py::test_a_block_a_cell_called_is_recorded_against_the_session` (real kernel, asserts `run_id is None` and the edge) | covered (skips locally) |
| 052 | `explore_sessions` parallels `runs` field for field | `record.py:69`; `store.py:223,376,847,888,914,975`; written `session.py:1579,1597` | `test_session_lineage.py::test_a_file_session_writes_its_anchor_…`; `test_explore_sessions_table.py::test_an_execution_must_have_exactly_one_anchor`, `::test_a_legacy_database_keeps_every_row_and_gains_the_anchor` | covered |
| 053 | Every cell run writes a record with session, commit, cell id, environment ref | `lineage.py:256`; called `session.py:2080,2060,2096` | `test_session_lineage.py::test_a_cell_run_records_the_commit_that_carries_the_notebook_it_ran` (`git rev-parse`s the ref) | covered (skips locally) |
| 054 | A packaged block's run is an ordinary run whose block version is the notebook commit | `_spec.py:42,80,107`; `packaging.py:1350`; `lineage.py:556`; `store.py:1022` | `test_packaged_block.py::test_a_workflow_runs_the_packaged_block_and_reproduces_the_session` (real `DAGScheduler` + `LineageRecorder`); `test_block_version_source.py` (10 cases) | covered |
| 055 | Objects named in `scistudio.output` are **durable**; every other session object is a reclaim candidate | planner `retention.py:224,271-290,347`; `store.py:1571,1601`; writer `lineage.py:416 declare_output` | the blocking half is proved end to end; the durable half is proved **only by tests that call `declare_output` themselves** | **partial (P1)** — `declare_output` has **no production caller**. `notebook_api.output()` registers names and writes nothing; nothing bridges `bridge.declared_outputs()` to the store. The durable set is always empty at runtime. See P1-2. |
| 056 | Every listed operation has a route | `api/routes/explore.py`, 23 routes; router mounted `app.py:323` | `test_explore_routes.py::test_every_operation_of_fr_056_has_a_route` — data-driven, asserts both directions | covered — **operations with no route: none** (see §2.1) |
| 057 | Nine event types on the existing hub; **cell output as it streams** | `session.py:343` + publish sites; `routes/explore.py:226,242`; `ws.py:262-300` | `test_explore_routes.py::test_every_event_type_of_fr_057_reaches_the_hub`, `::test_a_cell_run_reaches_the_websocket_from_the_queue_thread` | **partial** — every event is published from production code, but cell output **does not stream**: `kernel.py:881-905` gathers the whole iopub burst and `session.py:1226` emits one frame after the cell finishes. Also nothing asserts `kernel_state` carries memory. |
| 058 | The API reaches the kernel only through the queue and the bridge | `routes/explore.py` imports neither `explore.kernel` nor `jupyter_client`; refusals mapped by name `:293-302` | `test_explore_routes.py::test_the_route_module_never_imports_the_kernel_or_the_bridge` (AST walk incl. function bodies) | covered |
| 059 | `ipykernel` + `jupyter_client` in core deps; **the bundled runtime must be rebuilt before a release that ships the session** | `pyproject.toml:47-48` | NONE for either clause | **partial (P2)** — nothing records the runtime-rebuild obligation. `docs/ai-developer/release-runbook.md`, `desktop/`, `scripts/` and `.github/` contain no mention of `ipykernel`. No tracked TODO. |
| 060 | The layer test enumerates the explore subsystem with FR-008's forbidden imports | `tests/architecture/test_layer_deps.py:242-261,298,404` | `::test_layer_does_not_import_forbidden[explore]`, `::test_engine_does_not_import_explore`, `::test_the_explore_depth_rule_catches_a_planted_import` | covered — but see P2-5: the depth test's loop filters to `FR_035_CONSTRAINED_MODULES`, which is **3 of the 12 explore modules**. `session.py`, `packaging.py`, `block_call.py` and `kernel_bridge.py` — the ones that defer imports by design — are not covered by it. |

**Totals: 43 covered, 17 partial, 0 missing, 0 impl-no-test.**

### 2.1 FR-056 — every operation has a route

Verified against `src/scistudio/api/routes/explore.py`: open (`:838`, with all
three sources plus a fourth `notebook` source), list (`:877`), close (`:907`),
commit-to-branch (`:921`), read cells (`:943`), write cells (`:950`, `:965`),
run one cell (`:996`), run-stale (`:1006`), run-with-upstream (`:1015`),
toggle enabled (`:976`), interrupt (`:1030`), restart (`:1039`), graph
(`:1053`), marks (`:1071`), bindings with type names and exists-in-kernel
(`:1096`), window (`:1141`), snippet (`:1155`), kernel list (`:1178`), end a
kernel (`:1202`), packaging check (`:1262`), package (`:1306`).
**Nothing in FR-056 lacks a route.** One extra route
(`GET /sessions/{session_id}`) is declared as non-FR-056 in the test's own
table.

### 2.2 FR-057 — every event has a production publish site

`session_opened` `session.py:1845`; `session_closed` `:1959`; `kernel_state`
`:1351` (carries `memory_bytes`) plus `:1022`; `cell_state` `:1244`, `:1006`,
`:1093`; `cell_output` `:1226`; `changed_names` `:1235`; `analysis_updated`
`:521,533,559,581,1247`; `commit_recorded` `:1982,2083,2103`; `packaged`
`routes/explore.py:1356`. **No event is published only from test code.** The
one unmet sub-clause is "as it streams".

---

## 3. Success criteria — measured or asserted

| SC | Claim | Measured? | Evidence / gap |
|---|---|---|---|
| 001 | First cell names every port; a block with no outputs is refused | **measured** | `test_the_first_cell_names_every_output_port`, `test_opening_over_a_block_with_no_outputs_is_refused` |
| 002 | `%pip install` installs and a new snapshot is recorded by reference | **measured, never run** | `test_an_install_changes_the_snapshot_and_is_stored_once` — real offline install into a throwaway venv, kernel-gated; skipped here, CI's Test jobs incomplete |
| 003 | A, B, C fixture behaves as Story 2 states | **measured** | `test_rerunning_b_marks_it_out_of_order_marks_c_stale_and_runs_nothing`, `test_run_stale_runs_the_stale_set_and_nothing_else`, `test_run_with_upstream_…` |
| 004 | A snippet outside the whitelist is refused and inserts no cell | **measured** | `test_a_refused_emission_inserts_no_cell`, `test_a_refused_emission_leaves_no_cell_behind` |
| 005 | Interrupt ends a hung cell within the timeout; the session survives | **measured, never run** | `test_interrupt_ends_a_hung_cell_and_the_session_survives` (real spinning cell); kernel-gated |
| 006 | Exactly one commit per run, outputs stripped, tree/index/branch unchanged | **measured** | `test_many_runs_leave_the_branch_the_index_and_the_working_tree_alone`, `test_thirty_commits_leave_the_working_tree_and_index_untouched` |
| 007 | A packaged fixture notebook registers, runs in a workflow, and produces the session's outputs | **asserted** | The only end-to-end test, `test_a_workflow_runs_the_packaged_block_and_reproduces_the_session`, is skip-gated on `nbconvert`, which is in **neither** the core nor the dev dependency set of `pyproject.toml` and is not installed here. It has never run in CI. One agent ran it once in a private venv; nobody can reproduce that. |
| 008 | Each packaging refusal condition is refused with the cells or reads named | **measured** | nine tests in `test_packaged_block.py`, one per condition, plus `test_every_refusal_is_reported_not_just_the_first` |
| 009 | Packaged replay never pauses; ask pauses on a changed signature; confirm runs the confirmed commit | **measured** | `TestPackagedBlockReusesTheInteractivePause::…` through the real dispatch |
| 010 | Authored block: replay never pauses; ask behaves as today | **measured** | `TestReplayPolicy::…`, `TestDefaultPreservesExistingBehaviour::…` |
| 011 | An object resolves in both directions; a packaged run record carries the commit | **half measured** | The packaged-run half is measured (`test_a_workflow_runs_the_packaged_block…` asserts `block_version == COMMIT`). The "resolves in both directions" half depends on FR-055's `declare_output`, which nothing calls — see P1-2. |
| 012 | Every kernel listed with memory; ending one terminates its process; a branch switch retires all | **measured** | `test_every_live_kernel_is_listed_with_its_session_and_its_memory`, `test_ending_a_kernel_from_the_list_terminates_its_process` (asserts the process, not a flag), `test_a_branch_change_retires_every_kernel` |
| 013 | Every FR-056 operation has a route; every FR-057 event is emitted during a scripted session | **measured** | `test_every_operation_of_fr_056_has_a_route` (bidirectional), `test_every_event_type_of_fr_057_reaches_the_hub`, `test_the_event_sequence_of_a_cell_run` |
| 014 | Explore imports no api/ai/engine; the engine does not import explore | **partly measured** | The module-level rule covers all 12 modules. The **depth** rule — the one the checklist claims was proven by planting an import into `session.py` — covers 3 of 12, and `session.py` is not one of them. |
| 015 | The bundled runtime built for the release carries ipykernel and jupyter_client | **not measured, not measurable** | Nothing rebuilds, verifies, or even mentions the bundled runtime. No runbook entry, no desktop build change, no tracked TODO. T-001's verification criterion "the runtime carries ipykernel" has no artifact. |

**11 of 15 measured; SC-002 and SC-005 measured but never executed anywhere;
SC-007 and SC-015 asserted rather than measured; SC-011 and SC-014 half.**

---

## 4. Protected paths — is each change additive?

The checklist declares four protected paths and promises each touch is
additive per spec §4.5. Two more were added later by ledger amendment. CI's
`guard.core_change_guard` reports **six** affected files and the
`admin-approved:core-change` label is **not applied to PR #2241**
(`PR_LABELS_JSON: []`).

| Path | What changed | Additive? | Evidence |
|---|---|---|---|
| `core/lineage/record.py` | `ExploreSessionRecord` added; `BlockExecutionRecord` gains `session_id` and `environment_ref` with defaults; `RunRecord` untouched | **yes** | No field removed, no default changed. `tests/core` green. |
| `core/lineage/__init__.py` | one export added | **yes** | export-only |
| `core/lineage/environment.py` | `reference()`, `EnvironmentSnapshotStore`, `capture(executable=…)` | **yes** | `_run_pip_freeze()` keeps its old behaviour when `executable is None`; the default path is byte-identical |
| `core/lineage/retention.py` | open sessions block the sweep; session artifacts decided ahead of the per-workflow guards | **no, but inert on legacy data** | A project with zero `explore_sessions` rows takes exactly the old path (`sessions_in_progress()` empty, `session_durable`/`session_reclaimable` empty). It is a behaviour change gated on new data, not an addition. **And with FR-055's writer absent it is a data-loss change on new data — see P1-2.** A crashed session left `running` also blocks retention permanently; `_abandon_stale_sessions` only reaps at service construction. |
| **`core/lineage/store.py`** | **`LINEAGE_SCHEMA_VERSION` 1 → 2; `explore_sessions` created; `block_executions` rebuilt to relax `run_id NOT NULL` and add a polymorphic-anchor CHECK** | **no — this is a migration** | `store.py:452 _migrate_block_executions_session_anchor`. I read it line by line and it is careful: legacy columns are a module constant, every row is copied verbatim, `UNIQUE (run_id, block_id)` and all three indexes are recreated, `PRAGMA foreign_key_check` runs inside the transaction and aborts on a violation, and it is a no-op once `session_id` exists. `PRAGMA foreign_keys=OFF` is issued outside a transaction, which is correct. `tests/core/lineage/test_explore_sessions_table.py::test_a_legacy_database_keeps_every_row_and_gains_the_anchor` proves the copy. **But spec §4.5's rollback promise — "reverting them leaves existing behaviour intact" — does not hold for the on-disk database.** Reverting the code leaves `user_version = 2` and a rebuilt table forever; nothing downgrades, and nothing refuses a database stamped newer than the build. Old code still writes correctly (its INSERTs name columns and always supply `run_id`), so the practical risk is low — but the risk statement is wrong and should say so. |
| `core/versioning/_commit_ops.py` | four new plumbing functions | **yes** | 483 insertions, **zero deletions**. `tests/core/versioning` + `tests/core/test_git_engine.py` green. |
| `core/versioning/git_engine.py` | binds the four onto `GitEngine` with `provisional(since="0.3.4")` markers | **yes** | 24 insertions, zero deletions; added by recorded ledger amendment (drift log rows 3 and 4) |
| `blocks/base/interactive.py` | `InteractionPolicy`, `ON_NEW_INPUT_KEY`, `DEFAULT_INTERACTION_POLICY`, `resolve_interaction_policy`, `InteractiveMixin.on_new_input = ASK` | **yes** | 145 insertions, zero deletions. The default reproduces pre-ADR-054 behaviour exactly. `__all__` deliberately unchanged, so ADR-052's frozen `scistudio.blocks.base` surface is preserved — the comment at the bottom of the file says why. `tests/blocks` green (1,511 passed in the combined run). |
| `blocks/registry/_spec.py` | `_resolve_spec_version` wraps `_resolve_distribution_version` behind an opt-in class attribute | **yes** | A block that does not declare `block_version_source = "self"` gets the identical string. `test_block_version_source.py` pins that `AIBlock` and every scanned in-tree block still record the SciStudio version. |
| `blocks/code/backends/notebook.py` | cell selection + packaged-mode env vars | **yes, with one caveat** | The selection is optional and absent selection reproduces `shutil.copy2` exactly. The caveat: `notebook_run_environment` now also injects `codeblock_exchange_env(context)` into **every** notebook Code Block run, not only packaged ones. The docstring calls this out and argues it is what the Python and R backends already do; it is a behaviour change for pre-existing notebook blocks, small and defensible. `tests/blocks/code` green. |
| `engine/scheduler/_dispatch.py` | reads `on_new_input` before the remap check | **yes** | 50 changed lines; the `ask` branch is the previous code verbatim, and `ask` is what a node with no setting resolves to. `tests/engine` green (522 passed in the combined run). |

**Summary: nine of eleven touches are genuinely additive. `store.py` is a
migration, and the spec's rollback statement should be corrected to say so.
`retention.py` is a behaviour change gated on new data, and with FR-055's
writer missing it is the one that loses data.**

---

## 5. Scope discipline

`git diff origin/track/adr-054-spec2-dependency-analysis...HEAD --stat`:
**87 files, 45,932 insertions, 155 deletions.**

Against the checklist §2 in-scope list, three files are out of scope:

1. **`docs/specs/adr-054-explore-session.md` (+173/-57).** §2 declares
   `docs/specs/adr-054-*.md` explicitly **out of scope** — "approved input,
   not work product" — and no drift-log row records the reversal. The edit is
   recorded as a docs event in
   `.workflow/records/2240-docs-2240-governs-migration.json`, whose
   `declared_scope` is `{include: [], exclude: []}` — it declares no scope at
   all. So the mandatory tracking file says one thing and a ledger says
   another. **The content of the edit is good** — §4.2 now describes what was
   built and marks each divergence rather than quietly correcting it, and the
   `planned_governs` migration is honest about the two contracts that are gone
   rather than moved. The problem is only that the checklist was never
   updated to permit it. (Cosmetic: the blank line before
   `### 4.3 Implementation Sequence` was eaten.)
2. **`src/scistudio/explore/dependency_analysis.py`.** Owned by spec 2. The
   only change is the merge-conflict damage — see P1-1.
3. **`src/scistudio/explore/__init__.py`.** Also spec-2-owned by §4.2's own
   note; the change is a docstring expansion. Harmless, unrecorded.

Everything else outside §2's list is covered: `api/app.py` and
`api/routes/git.py` by the S3-C3 row and spec §4.2's "Not planned" entries,
`blocks/registry/_spec.py` by the S3-C2 manager amendment,
`core/versioning/git_engine.py` and `tests/core/test_git_engine.py` by drift-log
rows 3 and 4, `tests/api/helpers.py` by spec §4.2's own admission.

**Against the gate ledger CI actually reads**
(`.workflow/records/2240-explore-session-dispatch.json`) the picture is much
worse: its `declared_scope.include` is six globs, and **33 changed files fall
outside it**, including every `src/scistudio/api/**`, `blocks/**`, `core/**`
and `engine/**` path, `pyproject.toml`, `CHANGELOG.md`, and the spec. See §6.

---

## 6. Gate evidence

The per-agent ledgers are real and carry check events. The **manager dispatch
ledger**, which is the one `guard`s read in CI, does not:

| Field | Value | Consequence |
|---|---|---|
| `declared_scope.include` | 6 globs | 33 changed files outside it |
| `governance_touch` | `false` | CI `guard.mod_guard` fails on `pyproject.toml` |
| `requested_admin_labels` | `admin-approved:core-change`, `applied_by: null` | never applied |
| `observed_admin_labels` | `[]` | CI `guard.core_change_guard` fails on six protected files |
| `docs_events` | `[]` | the CHANGELOG entry is unrecorded |
| `test_events` | `[]` | none of the suites the agents ran are recorded |
| `check_na` | `[]` | — |
| `required_obligations` | all five lists empty | — |
| `commit`, `pull_request` | `null`, `null` | no provenance |

Live CI on PR #2241 @ `348228d8a` confirms all three guards fail. The
checklist's §8 verification table is honestly all-unchecked, and §7.4/§7.5 are
honestly unstarted, so this is an incomplete record rather than a false one —
but nothing in the repository currently attests that this work meets its own
gate.

Two specific claim-versus-reality gaps:

- **Commit `ba1e8122f` is titled "…clear the ratchet".** The deferral ratchet
  is not cleared: CI reports `later: 26 > ratchet 21`, up from the 22 the
  S3-C3 row recorded on its base. I reproduced it locally. The substance is
  benign — 16 of the 26 hits are prose about FR-038's "the **later**
  declaration in written order wins" — but it is a red required check and the
  claim is wrong.
- **The S3-C3 row claims the FR-060 depth rule was "proven by planting the
  import into `src/scistudio/explore/session.py` and watching the module-level
  rule pass while the depth rule failed".** The shipped test filters its file
  set to `FR_035_CONSTRAINED_MODULES` = `{__init__.py, dependency_analysis.py,
  fingerprint.py}`. I enumerated it: 3 of 12 modules, and `session.py` is not
  among them. The planted-import control test operates on a scratch string,
  not on the file set, so it cannot catch the narrowing.

---

## 7. The deferred decisions

All four issues exist and are open. I am judging whether deferring was right
and whether it is honestly recorded, not the eventual answer.

| Issue | Subject | Right to defer? | Honestly recorded? |
|---|---|---|---|
| **#2242** | Promoting an ADR-054 spec out of Draft must add its contracts to `ADR-054.governs.contracts` | **yes.** It is a governance-process question about ADR-054's own manifest, not about this runtime, and answering it inside a feature PR would be exactly the kind of governance drive-by the rules forbid. | **no.** Cited nowhere in the checklist or the spec. |
| **#2243** | Spec 2's FR-015 unresolved-read exception rests on a false premise | **yes.** It is spec 2's, and the deferral carries a proper `TODO(#2243)` at `explore/dependency_analysis.py:1237` with two more references in tests. | **yes**, and it is the only one of the four that follows AGENTS.md §3.6's TODO form. |
| **#2247** | ADR-039 addendum for the additive `explore_kernels` field on `POST /api/git/branch/switch` | **yes, and well argued.** The reasoning in the issue is the best writing in this dispatch: ADR-039 is `agent_editable: false`, and the text that documents the response shape sits inside Addendum 1's record of what it *superseded*, so editing it would make Addendum 1 appear to have decided something it never saw. Refusing to rewrite a supersession record is the right instinct. | **partly.** Spec §4.2 records the deferral but says it is "tracked under **#2240**" — the umbrella issue — not #2247, the dedicated issue that was actually filed. A reader following the spec's own pointer lands on the wrong ticket. |
| **#2248** | A packaged slice can ship source that never ran, because an edited cell carries no mark | **yes.** Closing it needs a fourth mark in FR-023 and a fourth entry in FR-039's refusal list — a spec change, which an implementer must not make unilaterally. Pinning today's behaviour with a passing test rather than an `xfail` was the right call, since the implementation is literally conformant to FR-023 and FR-039 as written. | **no, and this is the one that matters.** This is a substantive gap in FR-039's stated purpose — the packaged slice is not necessarily the code that ran — and it is recorded in neither the checklist nor the spec. Checklist §2's "Deferred work" row still reads "N/A at dispatch time." |

**Judgment: all four deferrals were correct. Three of the four are invisible
to anyone reading the tracking file the manager calls mandatory.**

---

## 8. Findings

### P1

**P1-1 — Unresolved merge-conflict markers are committed to production
source.** `src/scistudio/explore/dependency_analysis.py:1622-1626` contains
literal `<<<<<<< HEAD`, `=======`, and
`>>>>>>> origin/track/adr-054-spec2-dependency-analysis`. Introduced by
`348228d8a`, whose subject is "merge spec 2 forward — the quadratic fix and
the CI corrections". They sit inside a docstring, so the module parses, imports
and passes every test; `ruff check` passes too. `ruff format --check .` — the
CI command — fails, and I confirmed it is the sole cause of the red **Lint &
Format** job on PR #2241. `pre-commit`'s `check-merge-conflict` hook is bound
to the `manual` stage and runs only through the pre-PR evaluator's
`commit_hygiene` check, which has not been run on this branch. Fix: resolve
the conflict (the two sides differ by one word, "subsequent" vs "newer") and
re-run `ruff format --check`.

One thing to be careful of while fixing it, which I hit myself: running
`gate_record check` re-formats in place, and `ruff format`'s answer to this
file is to **indent the conflict markers inside the docstring** rather than
fail on them. The formatter then reports the file as clean, and a subsequent
`grep '^<<<<<<< '` finds nothing because the markers are no longer at column
zero. Resolve the conflict by hand before running any formatting step, or the
tooling will bury it.

**P1-2 — FR-055's durable half is dead code, and the automatic retention sweep
therefore deletes every object a session produced.**
`ExploreLineage.declare_output` (`explore/lineage.py:416`) is the only writer of
the durable edge, and it has **no caller in `src/`** — only two tests call it.
`notebook_api.output()` in session mode registers names and writes nothing
(`notebook_api.py:493-498`), and nothing bridges `bridge.declared_outputs()`
to the store. So `store.session_declared_output_paths()` always returns empty.
Meanwhile `retention.py:271-290` computes
`artifact_paths_produced_by_sessions() - session_durable - live_resolved` and
adds every result to `candidates`, `continue`-ing **before** the per-workflow
floor guard increments `scanned_per_workflow` — so session artifacts are also
exempt from the "retention always leaves one complete run on disk" invariant
that protects everything else. The sweep is not opt-in: `_schedule_artifact_
retention` (`api/runtime/_runs.py:290`) runs after **every successful workflow
run** and is enabled unless `SCISTUDIO_ARTIFACT_RETENTION` is explicitly
switched off (`:261`). The open-session guard blocks it only while a session is
open. Net effect: close your session, run any workflow, and every artifact a
block call in that session produced is deleted — including the ones you named
in `scistudio.output`, which FR-055 exists to protect. Fix: call
`declare_output` from wherever `bridge.declared_outputs()` is drained.

**P1-3 — FR-050's panel channel has no production implementation.**
`InteractionChannel` (`block_call.py:468`) is a `Protocol` with no
implementer. `kernel_bridge.py:671` constructs the process-wide adapter as
`BlockCallAdapter(session_id=…, on_call=record_block_call_lineage)` — no
`interaction` argument, so it defaults to `None`. `set_block_call_adapter`
(`kernel_bridge.py:628`) is called only from tests. There is no
`SessionEventType` for an opened panel and no route to settle a pending
interaction. In production, calling an interactive block from a cell raises
`InteractionUnavailableError` (`block_call.py:1247`), every time. The test that
appears to prove the requirement,
`test_the_panel_request_carries_what_the_session_needs_to_open_it`, passes a
`RecordingChannel` double — it mocks away exactly the thing the FR requires.
FR-050 is a MUST and is unmet.

**P1-4 — FR-049 and FR-039 are mutually exclusive on a real notebook.** The
bridge injects `blocks` into the kernel namespace (`kernel_bridge.py:739`), so
`blocks.run("Smooth", data=x)` is the affordance a person is given. But
`blocks` is not in `BUILTIN_NAMES` (`dependency_analysis.py:115`) and has no
exemption, so the analysis records it as an unresolved read and packaging
refuses on `unresolved_read` (`packaging.py:714`). I reproduced it:

```
>>> analyse_cell('a', 'import scistudio\ntotal = blocks.run("Smooth", data=1)\n…')
read       = ['blocks', 'scistudio', 'total']
>>> build_graph([f]).unresolved_reads
(UnresolvedRead(cell_id='a', name='blocks'),)
```

The obvious workaround does not work either: `import blocks` raises
`ModuleNotFoundError` — there is no importable top-level `blocks` module, which
is precisely what S3-B2 reported. Yet all three packaging tests that cover a
block call (`test_packaged_block.py:317,338,354`) begin their cell with
`import blocks`, a line that would raise in a live kernel. So the combination
of "call a block from a cell" and "package the notebook" has never been
exercised, and cannot work today. S3-C2 reported both halves of this to the
manager; the fix landed only the `scistudio` half (`session.py:2362`).

**P1-5 — A project switch leaves the cached session service holding a closed
lineage store, and leaves its kernels running.** `open_project`
(`api/runtime/_projects.py:450`) calls `_init_lineage_store`, which closes the
prior `LineageStore` (`:184-190`). `LineageStore.close()` sets `_closed = True`
and `_connect()` then raises `sqlite3.ProgrammingError("LineageStore is
closed")` (`store.py:563-566`). But `routes/explore.py:106` caches one
`SessionService` per project path, built once with whatever store was live at
build time, and `SessionService.__init__` captures it into `ExploreLineage`
for the service's lifetime (`session.py:1436`). Nothing clears `_services`
except application shutdown (`app.py:209-211`). So after switching away from a
project and back, every FR-052 to FR-055 write for that project's sessions
raises and is swallowed into a log line plus `provenance_degraded`
(`session.py:1673-1682`). The same gap leaks kernels: there is no
project-switch equivalent of FR-014's branch-switch retirement, so ipykernel
processes rooted in the old project stay alive — and `_projects.py:679-690`
deletes a project's tree without retiring them, which on Windows will fail.

**P1-6 — FR-005's external-reload clause is a method nobody calls.**
`ExploreSession.reload_if_changed` (`session.py:562`) has **no caller in
`src/`**. There is no file watcher, no route, and `read_cells`
(`routes/explore.py:943`) does not call it. Both tests
(`test_explore_session.py:438,451`) invoke the method directly, so the
mechanism is proved and the obligation is not. A notebook edited in JupyterLab
or rewritten by a `git checkout` is never picked up by a running session — and
spec A-012 makes the file-watcher interaction an explicit assumption that
"T-005 verifies", which it does not.

### P2

**P2-1 — SC-007 and FR-040's strongest assertion never run.** The single
end-to-end packaging test is gated on `nbconvert`, which appears **nowhere in
`pyproject.toml`** — not in core, not in `[dev]`. CI installs `-e ".[dev]"`, so
CI skips it too. The S3-C2 row's claim that "the end-to-end acceptance ran
against a real Jupyter nbconvert in an isolated venv outside the repository" is
true of one agent's private environment and is reproducible by nobody. Related:
FR-059 added `ipykernel` and `jupyter_client` to core but not `nbconvert`, so a
rebuilt bundled runtime will ship a product that can package a notebook block
and cannot run one.

**P2-2 — FR-059's second clause has no artifact anywhere.** "The bundled
runtime MUST be rebuilt before a release that ships the session" and spec
§4.5's "the release checklist must carry it" produced nothing:
`docs/ai-developer/release-runbook.md`, `desktop/`, `scripts/` and `.github/`
contain no occurrence of `ipykernel`. There is no tracked `TODO(#NNNN)`. SC-015
is consequently unmeasurable. This is the failure mode the release runbook
exists to prevent: a release that ships the session without the rebuild ships a
session that cannot start.

**P2-3 — FR-030's "reported once" is once per session, for ever.**
`_reported_commit_failure` (`session.py:1434`) is a set that is never cleared,
so a second commit outage after a recovery is silent. The adversarial test
`test_a_failure_after_a_recovery_is_never_reported_again` **pins that as the
expected behaviour** in its docstring. Whether the spec means "once per run" or
"once per outage" is a fair question, but "once per session for ever" is not a
reading of it, and pinning the behaviour rather than raising the question hides
the choice.

**P2-4 — FR-038's load-line rewrite is caller-opt-in and nobody opts in.**
`file_ports` is supplied by the caller at `routes/explore.py:692`; nothing
derives it, `ExploreSession` never records that it was opened over a file, and
`grep file_ports frontend/src` finds nothing. Package a file-opened session
without that argument and you get a block with no input port whose first cell
still hardcodes `scistudio.load("data/raw/…")` — a block that reads a path
instead of a port, which is the opposite of what FR-038 requires. Both proving
tests pass `file_ports` explicitly.

**P2-5 — The FR-060 depth rule covers 3 of 12 explore modules.**
`test_explore_never_imports_upward_at_any_depth` docstrings itself as "FR-060
over the whole file", and its loop filters to `FR_035_CONSTRAINED_MODULES`
(`test_layer_deps.py:319,451`). I enumerated the two sets: covered are
`__init__.py`, `dependency_analysis.py`, `fingerprint.py`; not covered are
`session.py`, `packaging.py`, `block_call.py`, `kernel_bridge.py`, `kernel.py`,
`lineage.py`, `notebook.py`, `notebook_api.py`, `queue.py` — the nine modules
that defer imports by design and are therefore the only place a violation
would plausibly be written. SC-014 is weaker than the checklist claims.

**P2-6 — FR-042 has no entry point.** `packaging.reopen_target:1109` has no
production caller; no route resolves a packaged block to a session;
`POST /sessions` with `source:"notebook"` never passes a `bound_run` even
though `open_notebook` accepts one; and no resolver returns a node's most
recent run inputs. The double-click affordance FR-042 describes does not exist
on the backend. Reasonable to leave to the frontend spec — but nothing says so.

**P2-7 — FR-047's cancel clause is absent.** "Cancelling MUST cancel the node
and close the session opened for it." Nothing in production closes an explore
session on node cancellation, and the engine cannot import explore (FR-008), so
this needs a deliberate seam that was never built. No test, no TODO.

**P2-8 — The manager dispatch ledger records almost nothing.** See §6. Six
scope globs against 33 out-of-scope files, `governance_touch: false` against a
`pyproject.toml` change, no docs events, no test events, no commit, no PR, and
the `admin-approved:core-change` label requested but never applied. All three
CI guards fail on it.

**P2-9 — The deferral ratchet is red and the commit that claims to have
cleared it did not.** `later: 26 > ratchet 21`, up from 22. Benign in
substance (mostly FR-038's "the later declaration wins" prose), red as a
required check.

**P2-10 — Issue #2248 is recorded nowhere in the repository.** A known gap in
FR-039's stated guarantee — a packaged slice may contain source that never ran
— appears in neither the checklist's Deferred Work row (still "N/A at dispatch
time") nor the spec.

**P2-11 — FR-021 runs a second comparison and the spec's own one is
unreferenced.** `fingerprint.compare_namespaces` — the dependency-analysis
spec's FR-026 comparison, exported and heavily tested — has no caller in
`src/`. The session uses `queue.observe_namespaces` instead, and the two
disagree: `compare_namespaces` reports a name unobservable whenever either
side's fingerprint is non-observable, `observe_namespaces` only considers
`shared - differing`, so an opaque name that *appeared* is never reported.
Either delete the duplicate or add a differential test.

**P2-12 — The spec was edited while declared out of scope.** §5. The content
is good; the record is contradictory.

### P3

- **P3-1** Spec §4.2 says the ADR-039 addendum is "tracked under #2240"; the
  actual issue is **#2247**.
- **P3-2** `FR-057`'s "cell output as it streams" does not stream: one frame is
  emitted after the cell completes (`kernel.py:881-905`, `session.py:1226`).
  Defensible given the execute-channel design, but it is an unmet MUST with no
  record.
- **P3-3** `FR-044`: a node cannot override a replay-packaged block to `ask`,
  because the policy is a packaging-time class choice (`packaging.py:1186`) and
  a non-interactive block never reaches `resolve_interaction_policy`.
- **P3-4** `FR-024` exempts the named cell from the skip rule; deliberate,
  pinned by a test, unratified in the spec text.
- **P3-5** `FR-015`: no test kills a real kernel while a cell is in flight
  through the queue; the route-level test fakes the death.
- **P3-6** `FR-001`: the API addresses sessions by id, not by project-relative
  path. Arguably the better design; the deviation is unrecorded.
- **P3-7** A crashed session left `status = running` blocks retention
  permanently; `_abandon_stale_sessions` reaps only at service construction.
- **P3-8** `test_the_session_id_is_a_ref_safe_component`
  (`test_explore_session.py:309`) is tautological — it restates
  `_explore_session_ref`'s body. The real proof is
  `test_explore_ref_commits.py:151`.
- **P3-9** `notebook.py:554 set_analysis_record` and `packaging.py:1109
  reopen_target` have no production callers; `list_sessions` globs
  non-recursively; `open_over_file` does not confine paths to the project tree;
  `retire_kernels` sets `needs_restart` on sessions that never had a kernel.
- **P3-10** `CHANGELOG.md` documents the two dependencies but not "the session
  surface" that §7.1 requires; the checklist row is honestly still `[ ]`. §5.1
  also claims "the release-runbook note about rebuilding the bundled runtime",
  which does not exist (P2-2).
- **P3-11** Missing blank line before `### 4.3 Implementation Sequence` in the
  spec.

---

## 9. Recommendation

**Block.**

The four P1s that are missing call sites — P1-2, P1-3, P1-5, P1-6 — are the
same defect the adversarial pass found twice and the fix agent closed twice.
That two rounds of review closed two instances and left four more is the
finding behind the findings: this dispatch has a systematic blind spot for
"reachable from a test" versus "reachable from a person", and the remedy is a
sweep for public methods in `explore/**` and `core/lineage/**` with no
production caller, not four more point fixes. `declare_output`,
`reload_if_changed`, `reopen_target`, `set_analysis_record`,
`compare_namespaces`, `InteractionChannel` and `set_block_call_adapter` are the
list I found; it took one `grep` each.

P1-2 is the one that must not ship: it deletes the person's data, silently,
after an unrelated workflow run.

P1-1 is a five-minute fix and must happen before anything else, because CI's
Lint & Format job cannot go green without it and nothing else can be judged
against a red pipeline.

What I would ask for before re-review:

1. Resolve the conflict markers (P1-1) and get all three red CI checks green:
   apply `admin-approved:core-change`, declare `governance_touch` in the
   dispatch ledger for `pyproject.toml`, put `Closes #2240` in the PR body,
   and settle the ratchet (P2-1, P2-8, P2-9).
2. Wire `declare_output` (P1-2), an `InteractionChannel` implementation
   (P1-3), `reload_if_changed` (P1-6), and the project-switch invalidation of
   `_services` (P1-5).
3. Decide P1-4: either exempt `blocks` from the unresolved-read check, or make
   a `blocks` module importable, or accept that a notebook calling a block
   cannot be packaged and say so in FR-039. Any of the three is fine; the
   current state is none of them, and the tests hide it.
4. Add `nbconvert` to `[dev]` so SC-007 stops being a claim (P2-1); write the
   bundled-runtime rebuild into the release runbook (P2-2).
5. Correct spec §4.5's rollback statement to say the lineage schema change is a
   migration, correct §4.2's #2240 to #2247, record #2242/#2247/#2248 in the
   checklist's Deferred Work row, and record the spec edit as an in-scope
   amendment.
6. Widen the FR-060 depth rule to all twelve modules (P2-5), and either fix
   FR-030's report-once or raise it as an owner question instead of pinning it
   (P2-3).

Everything else on the P2/P3 list can be tracked.
