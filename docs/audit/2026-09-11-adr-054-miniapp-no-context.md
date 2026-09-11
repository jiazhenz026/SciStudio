---
title: "Audit — ADR-054 Panel Python And MiniApps, With Both ADR-054 Specs (no-context)"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 54
  - 17
  - 22
  - 41
  - 48
  - 51
  - 53
  - 55
related_specs:
  - adr-054-miniapp
  - adr-054-panels
  - adr-053-personal-tool-library
  - adr-053-learning-center
language_source: en
---

# Audit — ADR-054 Panel Python And MiniApps, With Both ADR-054 Specs (no-context)

## 1. Change Summary

This report is the only file this change adds. It is a no-context audit of
`docs/adr/ADR-054.md` (status `Proposed`, `phase: planning`) and its two
specifications, `docs/specs/adr-054-miniapp.md` and `docs/specs/adr-054-panels.md`,
with emphasis on the sections that add panel Python (`panel.py`, the `call`
operation, a resident subprocess) and MiniApps (ADR-054 §10, §11).

- Persona and mode: `audit_reviewer`, **no-context**.
- Branch and worktree: `audit/2341-adr-054-miniapp-no-context` in
  `.worktrees/audit-2341-no-context`.
- Audited tree: the parent of the commit that adds this report.
- Line references such as `ADR-054 L703` point into the audited files. A
  `path:line` reference is to this repository.

**Recommendation: pass-with-fixes.** The documents agree with each other on
the core model: which contexts provide `call`, that previews and interactive
windows never start Python, and the message and route shapes. Every
structural check passes (§3). Most statements about existing code hold.

Two P1 findings must be fixed in the text before merge:

- a MiniApp's resident process has no defined end when the frontend goes away;
- the set of functions a page may `call` includes whatever `panel.py`
  imports.

Seven P2 findings correct false or ambiguous statements about existing code, or
close gaps an implementer would hit. Twelve P3 findings are editorial or
governance gaps.

Counts: 2 P1, 7 P2, 12 P3.

`gate_record` was not run, per the dispatch. Sentrux: N/A (documentation
surfaces). Browser smoke: N/A.

## 2. Findings

### 2.1 P1

#### P1-1 — A MiniApp process has no defined end when its frontend disconnects or reloads

- **Where:**
  - ADR-054 §10 L707-711: the process "ends when its context closes — its tab
    is closed, its project is closed, or SciStudio exits".
  - `adr-054-miniapp` FR-013 (L403-407) and FR-019 (L426-427): a MiniApp tab
    "MUST NOT be persisted across restarts".
  - `adr-054-panels` FR-010 (L504-507): contexts "close with their mount, their
    preview tab, or their block's resume or cancel".
- **What is wrong:** Each named trigger is a frontend act, a project action, or
  backend exit. None fires when the browser reloads, crashes, or closes.
  - After a reload, the tab is gone by design (FR-019). The backend context and
    its process stay alive, holding the full dataset in memory (ADR-054 L708-711).
    No surface lists or closes them.
  - ADR-055 §7 (ADR-055 L313-315) keeps the backend running after
    "closing the connection window or browser", so in background-runtime and
    browser deployments the leak lasts until an explicit shutdown.
  - ADR-022 admits no memory for any process (ADR-022 L54-55, L81-82), so
    nothing else bounds the leak.
- **Precedent in the code:** the backend already cancels browser-owned
  workflow runs once every GUI WebSocket has been gone for a grace period
  (`src/scistudio/api/ws.py:40-41`, `ws.py:160`, `ws.py:205-215`,
  `ws.py:358-362`). The same rule applied to panel contexts would close this
  gap.
- **Suggested fix:**
  - Bind each context to the WebSocket client, or to a host heartbeat, that
    opened it.
  - Close the context and end its process after a stated grace period with no
    owner, reusing the `_GUI_DISCONNECT_GRACE_SEC` pattern.
  - Add the case to ADR-054 §10, the miniapp spec's Edge Cases and FR-013, US8,
    and SC-004.
  - State whether this rule also applies to `preview` and `interactive`
    contexts. Those hold tokens but no process.

#### P1-2 — The functions a page may `call` include every callable `panel.py` imports

- **Where:**
  - `adr-054-miniapp` FR-007 (L375-379): "Callable functions are the module's
    public, module-level callables other than `setup` and `teardown`."
  - FR-010 (L390-395): `{fn, args}` is forwarded as-is.
  - ADR-054 §10 L713-718: "The page still reaches nothing directly."
- **What is wrong:**
  - A module-level callable includes imported names. For example,
    `from subprocess import run`, `from shutil import rmtree`, and
    `from pathlib import Path` all make `run`, `rmtree`, and `Path` public
    module-level callables of `panel.py`.
  - Any script running in the page can name them. ADR-054 §6 L575-577 lets
    custom panels load scripts from jsDelivr, cdnjs, and unpkg, and unpkg
    serves any published npm package.
  - In the `miniapp` context, the sandbox of §4 therefore no longer bounds what
    page script can cause. The bound becomes whatever `panel.py` happens to
    import, running as the user (§10 L720-724).
  - The ADR states the page boundary "honestly" for data leaks (§4 L392-399)
    but does not state this extension of it.
- **Suggested fix:**
  - Restrict `call` to functions defined in `panel.py` itself (`fn.__module__`
    equal to the panel module), or to an explicit export list such as
    `__all__`.
  - Refuse any other name with a defined error code.
  - Add to ADR-054 §10: in the `miniapp` context, a page's reach is the set of
    functions `panel.py` exports, and a third-party script in the page shares
    that reach.
  - Consider whether the CDN allowlist should apply unchanged in a context that
    provides `call`.

### 2.2 P2

#### P2-1 — There is no single process registry for block processes and agent commands

- **Where:**
  - ADR-054 §1 L193-194: "MiniApps reuse the process registry that tracks
    block processes (ADR-017) and the commands the agent runs (ADR-055 §5.3)".
  - §10 L703-706: "registered in the process registry that already tracks
    block processes and the commands the agent runs".
  - `adr-054-miniapp` FR-008 (L380-384): "the process registry the API
    exposes"; FR-013 (L406-407): "the registry's `terminate_all`".
- **Evidence:** there are two `ProcessRegistry` instances.
  - `ApiRuntime.process_registry` (`src/scistudio/api/runtime/__init__.py:366-367`)
    is handed to `LocalRunner` and the scheduler, and tracks block processes.
  - `app.state.registry` (`src/scistudio/api/app.py:74`) is the one the
    shutdown `terminate_all` runs on (`app.py:240`). It is also the one
    exposed to MCP tools and used by `run_command` (`app.py:166-171`;
    `src/scistudio/api/deps.py:54-58`;
    `src/scistudio/ai/agent/mcp/tools_execution.py:11-15,837-868`).
- **Why it matters:** An implementer who follows "the registry that tracks
  block processes" registers MiniApp processes where shutdown never terminates
  them.
- **Suggested fix:**
  - Name `app.state.registry` (the command registry that
    `get_process_registry` returns) in ADR-054 §1, §10, and FR-008.
  - Drop "that already tracks block processes".

#### P2-2 — FR-024 attributes graded availability to a route that has none, and its "create nothing" rule conflicts with the path it reuses

- **Where:**
  - `adr-054-miniapp` FR-024 (L445-454): "check agent availability first, with
    the same graded reasons as `POST /api/work-import/sessions`, and create
    nothing when a session cannot start".
  - US1 AS4 (L160-162).
  - Assumption (L709-711).
  - Edge Case (L324-325): "the template remains".
  - SC-001 (L684-685): the template tab is visible in under two seconds.
- **Evidence:**
  - The work-import route grades nothing. It returns 400 for an unknown or
    unsupported provider, and 503 or 500 when the spawn fails
    (`src/scistudio/api/routes/work_import.py:228-256,301-306`).
  - The four graded states of ADR-053 §5.2 (ADR-053 L555-567) come from
    `GET /api/ai/availability` (`src/scistudio/ai/agent/availability.py:150-165`;
    `frontend/src/lib/api/agentAvailability.ts:77,105-108`). The Bring In My
    Work dialog calls that endpoint before it calls the route
    (`frontend/src/components/BringInMyWorkDialog.parts/useAgentAvailability.ts`).
  - The route writes the brief and then spawns, and a missing binary is a 503
    after the write (`work_import.py:285-306`). Reusing that order leaves the
    MiniApp directory behind whenever the spawn fails. This is the spec's own
    Edge Case, but it contradicts "create nothing" in FR-024.
  - A live availability call can take up to `REPORT_BUDGET_SECONDS` = 20 s
    (`availability.py:267-282`), with a 60 s cache. If the create route runs
    it with a cold cache, SC-001 cannot be met.
- **Suggested fix:**
  - Point FR-024 at `resolve_availability`, the resolver behind
    `GET /api/ai/availability`, and allow a cached result from when the dialog
    opened.
  - Choose one outcome for a spawn that fails after creation: roll the
    directory back, or keep it. Make FR-024 and the Edge Case say the same
    thing.
  - Measure SC-001 from the moment the route returns.

#### P2-3 — Reload-on-change has no mechanism, and the existing watcher ignores the file the acceptance test names

- **Where:**
  - `adr-054-miniapp` FR-022 (L434-436): "the host MUST watch the panel
    directory".
  - US1 AS3 (L158-159): "When the agent rewrites `index.html`, Then the tab
    reloads within two seconds".
  - ADR-054 §11.2 L782-783.
- **Evidence:**
  - The host is the frontend, which cannot watch the filesystem.
  - The only project-wide watcher, `_ProjectFileHandler`
    (`src/scistudio/api/routes/workflow_watcher.py:386-406`), emits
    `file.changed` only for suffixes in `ADR036_FILE_ALLOWLIST`
    (`src/scistudio/api/file_contracts.py:11-21`). That list has no `.html`,
    `.js`, or `.css`.
  - The watcher covers only the project. User-tier panels (`~/.scistudio/panels/`)
    are not watched.
  - The spec adds exactly one realtime event, `panel.open_miniapp` (FR-030;
    §4.2 L601).
- **Suggested fix:**
  - Specify a backend watcher over the panel directories of open MiniApps, at
    the project and user tiers, and the event it emits.
  - Add that event to `ws.py` `_OUTBOUND_EVENTS` and to the dispatcher.
  - Add `workflow_watcher.py`, or the new watcher module, to `governs`.

#### P2-4 — A MiniApp target is specified in two incompatible shapes, and nothing maps one to the other

- **Where:**
  - `adr-054-miniapp` FR-004 (L360-364): the target is "a preview target
    (`adr-054-panels` FR-009)", which is `{kind, ref}` (`adr-054-panels`
    L497-499).
  - Elsewhere the spec addresses a MiniApp's data by workflow, block, and
    port, as the output of the latest successful run:
    - FR-029 (L478): `open_miniapp(panel_id, workflow_id, block_id, port)`;
    - FR-034 (L499-503): the picker;
    - the `MiniAppCreateRequest` entity (L557-558);
    - ADR-054 §11.3 L794-798.
- **Evidence:**
  - `PreviewTarget` carries `kind` and `ref`, and its `source` (workflow, node,
    port) is "for UI display only — carries no workflow truth"
    (`frontend/src/types/api.ts:562-580`).
  - A query for the latest successful run exists
    (`src/scistudio/core/lineage/store.py:1058`,
    `latest_successful_run_per_workflow`). But no requirement, route, or task
    turns (workflow, block, port) into a `{kind, ref}`, or lists outputs by
    declared type for the picker.
- **Suggested fix:** Add one requirement and one route that do both jobs:
  resolve (workflow, block, port) to a preview target, and list the outputs of
  latest successful runs by type. Say which side, the MCP tool or the
  frontend, calls it for `open_miniapp`.

#### P2-5 — What happens after a call times out, and to a backlog of calls, is undefined

- **Where:** `adr-054-miniapp` FR-011 (L396-399), FR-015 (L412-414), and
  SC-002 (L686-687); ADR-054 §10 L666-668 on the read budgets.
- **What is weak:**
  - Calls run one at a time. A call that times out does so "without ending the
    process".
  - The bootstrap is single-threaded, so a function that never returns leaves
    the process permanently busy. Every later call times out, and the state
    display still says `running`: FR-015 has no busy or unresponsive state.
  - A slider that emits calls faster than they complete queues them without
    bound.
  - Call results have no size limit. §10 rejects "pushing the whole dataset
    into the browser", but nothing stops a call from returning a whole stack.
- **Suggested fix:**
  - Define the state after a timeout (for example `unresponsive`, with Restart
    offered).
  - Let the SDK drop or supersede queued calls, for example so the latest call
    wins.
  - Add a result size limit and the error it returns.

#### P2-6 — The panels spec creates a skill it never provisions

- **Where:** `adr-054-panels` FR-045 (L706-712) and T-018 create
  `scistudio-write-panel/SKILL.md`. The spec's `governs` (L40-103) and §4.2
  (L788-814) do not include `src/scistudio/agent_provisioning/skills.py`.
- **Evidence:**
  - Skills are installed only by name from `_SKILL_NAMES`
    (`src/scistudio/agent_provisioning/skills.py:63-71,172-178`).
  - The miniapp spec knows this: FR-028 (L468-470) explicitly adds its own
    skill to that list.
- **Consequence:** As specified, the Phase C panel skill ships in the wheel but
  is never written into any project. FR-045's e2e scenario (US10) would fail.
- **Suggested fix:**
  - Add the `_SKILL_NAMES` entry to FR-045.
  - Add `skills.py` and `tests/agent_provisioning/test_skills.py` to the
    panels spec.

#### P2-7 — The workspace rules assume a right preview column, which AI presentation mode does not have

- **Where:**
  - ADR-054 §11.3 L801-807.
  - `adr-054-miniapp` FR-020 (L428-431), and FR-033 (L496-498), which puts the
    All Previewers button in the preview column.
- **Evidence:**
  - The right preview panel (`workspace-preview`) exists only when
    `!isAi` (`frontend/src/App.parts/ProjectWorkspace.tsx:692-709`).
  - In AI presentation mode, the preview is a left-rail entry
    (`frontend/src/components/ActivityBar.tsx:61-64`) rendered as a sidebar
    pane (`ProjectWorkspace.tsx:203-205`).
  - FR-020's collapse-and-restore rule therefore has nothing to act on in that
    mode. The MiniApp tab and the preview then compete for the same sidebar.
- **Suggested fix:** State the behaviour in AI presentation mode, or state that
  MiniApp tabs follow the workbench layout only.

### 2.3 P3

- **P3-1 — ADR-041 is cited for "the interpreter the user's blocks run on".**
  - ADR-054 §10 L701-702 cites "(ADR-017, ADR-041)".
  - ADR-041 is "CodeBlock v2 Script-as-AppBlock". It lets a script choose a
    discovered interpreter or environment (ADR-041 L233-279), which is not the
    block runtime.
  - FR-006 (L371-372) correctly pins "the interpreter the local runner uses for
    block workers".
  - Fix: cite ADR-017 alone, or say which interpreter is meant.
- **P3-2 — "Promotion is a move" is attributed to the ADR that says "copy".**
  - ADR-054 §11.4 L818-819 says "Promotion keeps ADR-053's rules: it is a
    move".
  - ADR-053 §3 L396-397 says "Promotion is a copy, not a move".
  - The move rule is `adr-053-personal-tool-library` FR-017 (L529); the code
    implements it (`src/scistudio/api/routes/user_library.py:432-435`).
  - Fix: cite that spec's FR-017, FR-019, and FR-025.
- **P3-3 — `related` lists ADRs the body never cites.**
  - ADR-054 L11 includes ADR-034 and ADR-040. A count of `ADR-0NN` in the body
    finds neither.
- **P3-4 — ADR-054 §13 treats the panels specification as future.**
  - L891-893 lists "the implementation specification (#2287)" under
    "Documents that follow". `docs/specs/adr-054-panels.md` exists, and the ADR
    never names its path.
- **P3-5 — The panels spec says it is the only spec for ADR-054.**
  - `adr-054-panels` L145-147 says "it is the single implementation spec for
    that ADR". This contradicts its own Phase D row (L165) and the existence of
    `adr-054-miniapp`.
- **P3-6 — "No tool or event today asks the frontend to open a tab" is only
  half true.**
  - The miniapp spec assumption at L712-713 says it.
  - The engine already sends `block_pty_opened`, "the broadcast that tells the
    frontend to open a tab it did not ask for"
    (`src/scistudio/api/routes/ai_pty/engine.py:337-338,368-369`), and the
    dispatcher handles it (`frontend/src/hooks/useWebSocket.parts/dispatchEvent.ts:99-101`).
  - ADR-054 §11.2's narrower claim, about tools, holds: `open_gui` returns only
    a URL (`src/scistudio/ai/agent/mcp/tools_qa.py:98-106,413-414`).
  - Fix: cite `block_pty_opened` as the precedent.
- **P3-7 — FR-040 changes a contract another spec defines.**
  - `adr-053-learning-center` L1518-1520 defines the `route_to` value
    `previewers` as "the left panel's ... Previewers tab".
  - FR-040 (L532-543) makes it open a dialog.
  - `adr-053-learning-center` is not in the miniapp spec's `related_specs`, and
    no update to it is planned.
  - The `TODO(#2135)` comment at
    `src/scistudio/tutorials/core/what-is-a-type/tutorial.yaml:715-721` also
    names "The Previewers tab's card" and would go stale.
- **P3-8 — The miniapp spec's `governs` misses files its requirements must
  change.**
  - `src/scistudio/ai/agent/mcp/__init__.py:61-73` imports every tool module
    eagerly. `tools_panels.py` registers no tools until it is added there
    (FR-029).
  - `UserLibraryTarget` is a closed `Literal` in
    `src/scistudio/api/schemas.py:846` and `frontend/src/types/api.ts:329`
    (FR-039).
  - The move source is resolved by `_resolve_project_file`, which refuses any
    suffix outside `ADR036_FILE_ALLOWLIST` (`src/scistudio/api/routes/projects.py`
    L201). A directory source cannot pass it (FR-039).
  - The watcher of P2-3.
  - Also: ADR-054's `tests` (L97-104) lists no MiniApp test.
- **P3-9 — ADR-054 §11.3 disagrees with the spec about the New menu.**
  - L794-796 says: "Opened from its card or the New menu, it asks which block
    output to open on".
  - In the spec, the New menu opens the create dialog (FR-023, FR-037), and
    only a card opens the target picker (FR-034).
  - §11.2 L773 describes the dialog as "two questions". FR-023 also asks for a
    provider and a permission mode.
- **P3-10 — Which panels the Previewers list shows is ambiguous.**
  - `adr-054-panels` FR-005 (L474-478) surfaces panels "with tier, contexts,
    types" in the Previewers list. The miniapp spec moves that list behind All
    Previewers (FR-033) and lists MiniApps separately (FR-031).
  - Neither spec says whether interactive-only and MiniApp-only panels appear
    under All Previewers.
- **P3-11 — Two security details are unspecified for the call path.**
  - The routes that start and call user Python "authenticate as the read route
    does" (FR-010 L395). In local mode that is no session.
  - The only origin control specified is refusing `Origin: null`
    (`adr-054-panels` FR-030, L618-619).
  - `context_id` has no stated entropy. The per-mount token has one (≥128 bits,
    FR-025).
  - ADR-055 §7 L324-326 says loopback "does not justify arbitrary cross-origin
    calls".
  - Fix: make context ids unguessable, and refuse non-allowlisted origins on
    `/api/panels/contexts/**`.
- **P3-12 — Document-standard notes.**
  - `document-standards.md` L146 says priorities are "unique within the spec".
    The miniapp spec repeats P1 three times and P2 four times; the panels spec
    repeats P1 four times.
  - 25 of the 33 specs under `docs/specs/` with user stories also repeat
    priorities, so this is recorded as information, not as a defect of these
    two specs.
  - Miniapp US8 (P2) follows US7 (P3).
  - A panel that declares both `preview` and `miniapp`, as miniapp US3 does, is
    held to exactly one `types` entry by FR-001. That also narrows its preview
    routing. Say so in FR-001.

## 3. Checked And Found Correct

**Structure**

- `frontmatter_lint` passes with 0 findings on all three documents.
- Every `governs.files` path exists: 49 in the ADR, 18 in the miniapp spec, and
  45 in the panels spec.
- No `planned_governs` path exists yet. That is correct for `Proposed`,
  `planning`, and `Draft`.
- Both specs have the six required H2s and the `4.1`-`4.5` subsections.
- FR, SC, and T ids are contiguous: miniapp 40, 7, and 14; panels 49, 10,
  and 19.
- Every user story has Why, Independent Test, and at least one Given/When/Then.
- Every ADR §1.1 "Detailed section" target exists.
- The ADR's internal references (§14, §16, §11.5, §12) and the miniapp spec's
  scope references to ADR-054 §10, §11.1, §11.5, §12, and §16 resolve.

**Consistency between the ADR and its specs**

- Only `miniapp` provides `call`.
- `preview` provides `read` and `open`; `interactive` provides one `writeBack`.
- `save` is available everywhere; `sync` is reserved.
- `.py` is never served. Today's allowlist has no `.py`
  (`src/scistudio/previewers/assets.py:33`), and `adr-054-panels` FR-027 does
  not add it.

**Statements about existing code that hold**

- *Process handling.*
  - Registry keys are `(workflow_id, block_id)`.
  - The command handle registers under a namespace, with a Job Object or
    process group per command. FR-008's `panel-context` /
    `context-<id>` pattern follows it
    (`process_handle.py:140-163`; `tools_execution.py:17-22,303-320,867-868`).
- *Resource admission.* ADR-022 reserves memory for no process (ADR-022
  L81-82; `src/scistudio/engine/resources.py:70-71`).
- *Bring In My Work.*
  - The session writes its brief under `.scistudio/work-import/`, then opens a
    pre-spawned tab (`work_import.py:76,285-300`; `engine.py:330-335`).
  - ADR-053 §4.1 and §5.2 say what ADR-054 cites.
- *Realtime events and MCP.*
  - `_OUTBOUND_EVENTS` has no tab-open event (`ws.py:51-77`).
  - `open_gui` returns a URL only.
- *Skills.* Skills install from `_SKILL_NAMES` (`skills.py:63-71`).
- *User-library route.* It writes a single bare `.py` file into a tier root and
  consumes a project source through `move_from`, so "extended from a single
  file" is accurate (`user_library.py:26-52,111-117,186-231,463-508`).
- *Tabs.*
  - The tab union is workflow, file, and preview (`frontend/src/store/types.ts:955`).
  - A preview tab is dropped when focus moves (`types.ts:902-906`;
    `tabSlice.parts/fileTabActions.ts:90`).
- *Sidebar.*
  - The activity bar has a Previewers entry (`ActivityBar.tsx:43`).
  - `PreviewerPalette` groups by tier, with reload, diagnostics, and per-type
    choices (`PreviewerPalette.tsx:3-14`).
- *Canvas.*
  - Canvas nodes have no context menu today. `ContextMenu` appears only in
    `ProjectTree` and `TerminalView`.
  - A hover action toolbar exists (`nodes/BlockNode.tsx:13,34`).
- *Tips, popover, promotion.*
  - The tips card overlays every left-panel tab (`tipPool.ts:1-14`;
    `ProjectWorkspace.tsx:253`).
  - `DetailPopover` has the `actions` slot promotion uses
    (`DetailPopover.tsx:27-31`).
  - `promotable.ts` models single-file sources only (L32-35).
- *New menu.* It holds New workflow and New custom block
  (`FileOperationsGroup.tsx:97-106`).
- *Tutorials.* Both steps and the exact sentence FR-040 quotes exist:
  - `welcome-to-scistudio/tutorial.yaml:371-377`;
  - `what-is-a-type/tutorial.yaml:722-730`;
  - `targets.ts:61,96,184`.
- *Retention.* Retention keeps the most recent successful run per workflow, as
  §11.3 says (`core/lineage/retention.py:1-13`).
- *Cited ADR text.*
  - ADR-051 §3 and §4 (ADR-051 L186-201, L242-246, L272-277) support "nothing
    resident" and "self-contained".
  - ADR-055 §5.3 (L263-274) supports the run-as-user framing.

## 4. Method And Context Boundary

**Read:**

- the policy files: `AGENTS.md`, `docs/ai-developer/rules.md`,
  `personas/audit-reviewer.md`, and `specific_rules/document-standards.md`;
- the three audited documents;
- the cited sections of ADR-017, ADR-022, ADR-041, ADR-043, ADR-051, ADR-053,
  and ADR-055;
- `adr-053-personal-tool-library` and `adr-053-learning-center`;
- the code named in §2 and §3;
- `docs/audit/2026-09-11-adr-054-panels-no-context.md`, as a format reference
  only.

**Not read:**

- any issue or PR (`gh` was not run);
- commit messages (no `git log`, `git show`, or `git blame`);
- `.workflow/records/`;
- other worktrees;
- chat or manager summaries;
- any other 2026-09-11 ADR-054 MiniApp audit.

**Commands run in the worktree:**

- `python -m scistudio.qa.audit.frontmatter_lint --format json` on each
  document, with `PYTHONPATH=./src`;
- a Python check that every `governs`, `planned_governs`, and `tests` path
  resolves;
- a Python check of spec headings, FR, SC, and T contiguity, and user-story
  sections;
- a count of duplicate user-story priorities across `docs/specs/`;
- `grep`, `sed`, and `ls` searches cited inline.

## 5. Recommendation

**Pass-with-fixes.**

- **Before merge:** P1-1 and P1-2. Both are text changes to ADR-054 §10 and to
  the miniapp spec.
- **In the same revision:** P2-1 through P2-7. They correct statements that are
  false against the code (P2-1, P2-2), or give an implementer the mechanism the
  text assumes (P2-3 through P2-7).
- **Later:** P3 items are editorial or governance, and may be batched.
