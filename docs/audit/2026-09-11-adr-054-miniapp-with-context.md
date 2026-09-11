---
title: "Audit — ADR-054 panel Python and MiniApp revision (with-context)"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 54
  - 42
  - 17
  - 22
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

# Audit — ADR-054 Panel Python And MiniApp Revision (with-context)

## 1. Change Summary

This report is the only file this change adds. It is a with-context audit of the
ADR-054 revision for issue #2341. The revision adds panel Python (`panel.py` and
the `call` operation) and the `miniapp` context, and it adds the
`adr-054-miniapp` spec.

- Persona: `audit_reviewer`, **with-context** mode, task kind `docs`.
- Audited branch: `docs/2341-adr-054-miniapp` at `41529e01b`. Delta:
  `origin/main..41529e01b` (one commit, 4 files, +1365/-68). `origin/main` is
  `e9dcd01aa`.
- Audit branch and worktree: `audit/2341-adr-054-miniapp-with-context` at
  `.worktrees/audit-2341-with-context`.
- Files audited: `docs/adr/ADR-054.md`, `docs/specs/adr-054-miniapp.md` (new),
  `docs/specs/adr-054-panels.md`, and
  `.workflow/records/2341-docs-2341-adr-054-miniapp.json`.
- Judged against:
  - the authoritative owner decisions of 2026-09-11, given in the dispatch; they
    supersede the issue body where the two differ;
  - issue #2341;
  - ADR-017, ADR-022, ADR-051, ADR-053, and ADR-055, the ADR-053 personal-tool-library
    and learning-center specs, and `docs/specs/adr-055-enterprise-support.md`;
  - the ADR-042 document standards;
  - the code at `41529e01b`.
- Line numbers such as `ADR L461` refer to `docs/adr/ADR-054.md`, and `spec L380`
  to `docs/specs/adr-054-miniapp.md`, both at `41529e01b`.

**Recommendation: pass-with-fixes.**

- **What holds.** All 13 owner decisions are recorded faithfully (§3). The
  renumbering from §10–14 to §12–16 left every internal cross-reference correct.
  Every `governs.files` path resolves, no `planned_governs` surface exists yet, and
  the spec's FR, SC, and T ids are contiguous.
  `frontmatter_lint` passes on the three documents (0 findings) and `full_audit`
  passes; its only findings for these documents are the expected info-level
  unresolved planned surfaces.
- **What needs fixing.** Six P2 findings:
  - two statements about today's code are inaccurate: the process registry, and
    opening tabs;
  - two sentences still say "three operations";
  - the committed gate ledger records an empty diff;
  - two spec behaviours need one sentence each: dismissing the tutorial dialog,
    and reloading around `__pycache__`.
- **Counts:** 0 P1, 6 P2, 11 P3.

Checks run (read-only; `gate_record` was not run in this worktree):

| Check | Result |
|---|---|
| `PYTHONPATH=./src python -m scistudio.qa.audit.frontmatter_lint --repo-root . docs/adr/ADR-054.md docs/specs/adr-054-miniapp.md docs/specs/adr-054-panels.md` | pass, 3 paths, 0 findings |
| `PYTHONPATH=./src python -m scistudio.qa.audit.full_audit --repo-root . --format json` (output to scratch) | pass; for the three documents only info-level `closure.planned-*` and `doc-drift.planned-*` findings |
| Every ADR `governs.files` path (49) and the spec's `governs.files` | all resolve |
| ADR and spec `planned_governs` (6 paths, 2 modules) | none exists yet, as `phase: planning` requires |
| FR / SC / T id contiguity | FR-001–FR-040, SC-001–SC-007, T-001–T-014: contiguous, and every FR reference resolves |
| Sentrux; frontend/browser smoke | N/A: documentation-only change |

## 2. Findings

### P1 — blocks merge

None.

### P2 — fix before completion

**P2-1. The ADR says one process registry tracks both block processes and the
agent's commands. The code has two.**

The ADR claims this in two places:

- ADR L193-195: "MiniApps reuse the process registry that tracks block processes
  (ADR-017) and the commands the agent runs (ADR-055 §5.3)".
- ADR L703-706: "registered in the process registry that already tracks block
  processes and the commands the agent runs
  (`src/scistudio/engine/runners/process_handle.py`; ADR-055 §5.3)".

In the code these are two separate `ProcessRegistry` instances:

- Block runs register in `ApiRuntime.process_registry`
  (`src/scistudio/api/runtime/__init__.py:366-367`, handed to `LocalRunner`).
- The agent's `run_command` registers in `app.state.registry`
  (`src/scistudio/api/app.py:74`). The MCP context exposes that registry at
  `app.py:167-171`, and commands use it under the key half
  `COMMAND_REGISTRY_NAMESPACE = "mcp-command"`
  (`src/scistudio/ai/agent/mcp/tools_execution.py:96`).
- The lifespan's shutdown `terminate_all` runs only on `app.state.registry`
  (`app.py:240`).

The spec's FR-008 and FR-013 (spec L380-384, L403-407) implicitly pick the
command registry: "the registry the API exposes", plus its `terminate_all`. That
choice works, but the ADR text misdescribes today's code.

*Fix:* in ADR §1 and §10, name the registry precisely. For example: "registered in
the backend's process registry — the one the agent's commands use and the
backend's shutdown `terminate_all` stops (`src/scistudio/api/app.py`) — through a
handle modelled on block and command handles". In FR-008, name
`app.state.registry` explicitly.

**P2-2. "No tool can open a tab today" is overstated, and the spec's
"no tool or event" is false.**

- ADR L788-790: "No tool today can ask the frontend to open a tab — `open_gui`
  only returns an address for the agent's own browser — so a tool and a matching
  realtime event are added."
- Spec §6 Assumptions (spec L712-713): "No tool or event today asks the frontend
  to open a tab (source: existing-system)".

Neither holds in full. `handleWorkflowStartedAutoOpen`
(`frontend/src/hooks/useWebSocket.parts/handleLifecycle.ts:35-61`) opens a
workflow tab when the agent's `run_workflow` tool starts a run. Its comment
(L36-39) says it mirrors the existing `workflow.changed` `kind=created`
auto-open path. So agent actions already open workflow tabs, as a side effect of
realtime events. The true statement is narrower: no tool exists whose job is to
open a chosen tab, and `open_gui` only returns a URL
(`src/scistudio/ai/agent/mcp/tools_qa.py:413-450`). The WebMCP bridge mirrors
backend tools only (`frontend/src/webmcp/register.ts:1-15`), so it adds none.

*Fix:* restate both sentences. For example: "No tool asks the frontend to open a
tab of the agent's choosing; the frontend only auto-opens a workflow tab on
`workflow_started` or a created `workflow.changed` (`handleLifecycle.ts`).
`open_miniapp` follows that event-to-dispatcher pattern with an event of its
own." Then change the assumption's wording to match.

**P2-3. Two sentences still say "three operations".**

ADR L158-161 and the §2 table (ADR L224-229) now define four operations: read,
write back, call, and sync. Two sentences still count three:

- §4, ADR L461: "a whitelist to express what three operations already say".
- §16, ADR L1005: "the whitelist restates what three operations express
  directly".

The dispatch asked specifically that no sentence be left saying "three
operations". No sentence still says a panel has no Python at all: the remaining
"no Python" wording is scoped to reading (ADR L514) or to previews (ADR L208,
L599).

*Fix:* make both sentences count-free, e.g. "what the operations already say".

**P2-4. The committed gate ledger records an empty diff.**

At `41529e01b`, `.workflow/records/2341-docs-2341-adr-054-miniapp.json` records
evidence that predates the commit:

- `observed_diff`: `base_sha` = `head_sha` = `e9dcd01aa`, `changed_files: []`;
- `diff_fingerprint`: `sha256:e3b0c442…b855`, which is the SHA-256 of empty input;
- `reconcile_events[0]`: carries the same empty-diff fingerprint;
- every `docs_events` entry: `verified_in_diff: null`.

The manager reports re-running `check` at `41529e01b`, but that result is not in
the committed ledger. The audit-reviewer persona requires `observed_diff` to
reflect the actual changed files. At this commit it does not.

*Fix:* on the docs branch, after the two audit reports are merged in, run
`gate_record check --mode pre-pr`, commit the refreshed ledger, then
`finalize`. The ledger should then show the 4 to 6 changed files and
`verified_in_diff: true` for the three document paths.

**P2-5. FR-040 opens a dialog from a tutorial route but never says what closes
it.**

- FR-033 (spec L496-498) puts All Previewers in a dialog.
- FR-040 (spec L532-537) makes `route_to: previewers` open that dialog and
  resolves `previewer_palette` inside it.

Two tutorial flows depend on it:

- In `welcome-to-scistudio`, the step after `where-previewers-live` is
  `create-the-plot`
  (`src/scistudio/tutorials/core/welcome-to-scistudio/tutorial.yaml:381-392`).
  That step routes to `plots` and rings `plots_new_button`. A dialog still open
  from the previous step would cover it.
- In `what-is-a-type`, `save-the-previewer` asks the reader to use the per-type
  choice controls inside the dialog. That requires the tutorial highlight and
  dialogue to render above the dialog.

The spec states neither behaviour.

*Fix:* add to FR-040:

1. The dialog opened by a route closes when the tutorial leaves that step, or on
   the next `route_to`.
2. The tutorial's highlight ring and dialogue render above the dialog.

Also add a run-through test of both steps to §4.4. Its existing run-through
bullet names the steps but not this behaviour.

**P2-6. Reload-on-change will fire on the process's own `__pycache__`.**

The chain is:

1. FR-006 (spec L370-374) puts the panel directory on the subprocess's import path.
2. FR-007 imports `panel.py`, so CPython writes `__pycache__/panel.*.pyc` inside
   the panel directory.
3. FR-022 (spec L434-436) watches "the panel directory" and reloads — a new frame,
   context, and process — whenever "a file in it changes".

Every newly opened project-tier or user-tier MiniApp therefore restarts once
right after starting. That includes the template tab that FR-025 opens straight
after creation. And a `panel.py` that writes a result or cache into its own
directory would restart in a loop.

*Fix:* in FR-022, watch only the panel's source files (`panel.json`,
`index.html`, `panel.py`, and page assets), or ignore `__pycache__`. In FR-006,
start the subprocess with bytecode writing disabled (`PYTHONDONTWRITEBYTECODE=1`).
Add an edge case for a `panel.py` that writes into its own directory.

### P3 — improvements

**P3-1.** `related` (ADR L11) adds ADR-034 and ADR-040, but the body never cites
either (0 occurrences). ADR-034 is the filesystem watcher (`app.py` comment
"ADR-034 Phase 2: workflow filesystem watcher") and ADR-040 is the MCP tool
surface. *Fix:* cite them where §11.2 relies on them — the directory watch, and
the tool — or drop them from `related`.

**P3-2.** #2296 is cited nowhere. Issue #2341 says implementation is "a new
ADR-054 phase coordinated under #2296", and the gate ledger's test N/A rationale
names #2296. ADR §14 and the spec cite only #2288. *Fix:* name #2296 as Phase
D's coordination issue in the spec's §1 or §4.3, or confirm that #2288 alone is
intended.

**P3-3.** User-story priorities are not unique, and one story is out of order.
The spec has P1 ×3, P2 ×4, and P3 ×1, and US8 (P2, spec L295) follows US7 (P3,
spec L277). `document-standards.md` §3.4 says priorities "start at P1 and are
unique within the spec". The sibling spec `adr-054-panels` repeats priorities
the same way, and `frontmatter_lint` does not enforce the rule. This is drift
between the written standard and house practice. *Fix:* at least move US8 before
US7; the owner decides whether the uniqueness rule applies.

**P3-4.** ADR L757-758 says "the tutorial steps that pointed at the tab point at
the button". FR-040 and owner decision 13 say instead that `route_to:
previewers` opens All Previewers and the highlight lands on the list inside it.
*Fix:* "the tutorial steps that opened the tab open the list the button opens".

**P3-5.** ADR L795-796 says a MiniApp "opened from its card or the New menu … asks
which block output to open on and offers the outputs of its declared type". The
New menu does not open an existing MiniApp: it creates one, and the create
dialog asks for the data before any type is declared (ADR L773-774, FR-023).
*Fix:* "Opened from its card, it asks…; created from the New menu, the create
dialog asks for the data."

**P3-6.** Promotion entry points beyond the route and the frontend model are not
covered.

- ADR-053 spec §6.2 and FR-025 make four entries share one promotion
  implementation: E1, E2 (canvas node context menu), E3 (the agent's MCP tool),
  and E5.
- FR-039 (spec L522-528) extends only the user-library route and
  `promotable.ts`.
- The agent tool `promote_to_user_library` accepts a bare `.py` file only
  (`src/scistudio/ai/agent/mcp/tools_library.py:148-174`, `:190-273`).
- The canvas node context menu that ADR-053's E2 assumes does not exist in code.
  FR-035's new menu is where it would land.

*Fix:* say whether E3 promotes MiniApp directories and whether FR-035's menu
carries E2 for blocks, or record either as a tracked deferral.

**P3-7.** ADR L980-981 says "resource admission does not count it". Admission
does apply soft back-pressure on OS memory percent
(`src/scistudio/engine/resources.py:222-228`), so a MiniApp's resident memory
counts indirectly: above the 95% watermark it can pause new block dispatch. The
§10 wording "reserves memory for no process" (ADR L709-711) is accurate, and the
claim that ADR-022 reserves no memory holds (`resources.py:233`). *Fix:*
"reserves nothing for it, though its memory counts toward the OS-level watermark
that pauses new block dispatch".

**P3-8.** Documents that describe the Previewers tab are not listed as follow-ons.

- `docs/specs/adr-053-learning-center.md:1507,1519` describes the Previewers tab
  as a tutorial route target.
- Two English developer comments describe the tab or the left panel:
  - `src/scistudio/tutorials/core/welcome-to-scistudio/tutorial.yaml:360-364`
    ("the second has to switch the left panel to Previewers");
  - the `TODO(#2135)` at `what-is-a-type/tutorial.yaml:715`.

*Fix:* list the learning-center spec under ADR §13 "Documents that follow", or in
spec §4.2. Update the English comments when FR-040 lands; the owner's Chinese
design comments stay, as FR-040 requires.

**P3-9.** Spec §4.2 and `governs` omit files the plan implies:

- `src/scistudio/ai/agent/mcp/__init__.py`, which imports each `tools_*` module
  (L65-66), so a new `tools_panels.py` must be added there;
- `src/scistudio/api/routes/work_import.py` and
  `src/scistudio/api/routes/ai_pty/engine.py`, if the brief-writing and
  pre-spawned session path is extracted for reuse (FR-024);
- possibly `frontend/src/components/nodes/BlockNode.tsx`, for the node context
  menu.

*Fix:* add those that will change.

**P3-10.** FR-036 (spec L508-514) goes further than owner decision 11, which says
"a dialog asks what outputs":

- it also asks "what the decision is" and the destination tier;
- it requires the MiniApp to stay unchanged.

Meanwhile ADR L830-831 says the agent "rewrites the MiniApp as an interactive
block". *Fix:* have the owner confirm the extra questions. Align the ADR wording,
e.g. "writes an interactive block from the MiniApp, leaving the MiniApp in
place".

**P3-11.** ADR §12 (ADR L860) scopes "the agent session, skill, tool, and realtime
event" — one tool. The spec adds two: `validate_panel` and `open_miniapp`
(FR-029). *Fix:* say "tools".

## 3. Owner Decisions Checked

| # | Owner decision (2026-09-11) | Where recorded | Verdict |
|---|---|---|---|
| 1 | Merged into ADR-054; no separate ADR, no addendum; ADR-056 unused | ADR frontmatter `closes_issues: [2285, 2341]`; §16 "A separate ADR for MiniApps"; no ADR-056 file exists | Faithful |
| 2 | Any panel may carry `panel.py`, called via `scistudio.call(name, args)`; not a MiniApp-only exception; preview and interactive never start it; only a context providing `call` (today `miniapp`) | §2 table and L248-255; §3 tree; §7 L610-612; §10 L670-685; §16 "Python only for MiniApps … Rejected"; spec FR-002, FR-003, FR-016 | Faithful |
| 3 | Resident subprocess, one per open context, in the process registry; not per call and not in the backend; hand-written HTML, no framework | §10 L687-711; §16 two alternatives; §11.1 L734-735; spec FR-006–FR-014 and the edge case "two tabs and two processes" | Faithful. The registry is misdescribed: P2-1 |
| 4 | A MiniApp leaves only itself; no lineage, no workflow hookup | §11.1 L740-746; §12 out of scope; spec scope.out | Faithful |
| 5 | One data type; user picks compatible data on open; right-clicking a block lists MiniApps for its output type | §3 L341-343; §11.3 L794-799; spec FR-001, FR-034, FR-035 | Faithful (wording: P3-5) |
| 6 | Four entries (tab, New menu, block context menu, chat with skill and tools, AI judges fit); create dialog then an agent session in the bottom AI tab through the ADR-053 mechanism | §11.2 L750-790; spec FR-023–FR-030. ADR-053 §4.1 "Import Is A Guided Agent Session" and §5.2 "Agent Availability Is Graded" exist | Faithful |
| 7 | Template page opens at once and reloads as the agent writes | §11.2 L775-783; spec FR-024–FR-026, FR-022, US1 | Faithful (reload defect: P2-6) |
| 8 | Centre tab; preview column collapses; right column is not a chat | §11.3 L801-807; spec FR-018–FR-020 | Faithful |
| 9 | Previewers tab removed and replaced by a MiniApps tab (list + New only); All Previewers button in the preview column opens the same list; introduction in the tips card | §11.2 L754-771; §15 L989-991; spec FR-031, FR-033, FR-038. The spec's search box mirrors the existing tab (`PreviewerPalette.tsx:153-193`) | Faithful |
| 10 | Hover detail popover with Promote to My Library; four tiers; new MiniApps default to the project | §11.4 L811-821; spec FR-032, FR-039. `DetailPopover.tsx` is the ADR-053 shared popover (FR-046) | Faithful (entry-point gap: P3-6) |
| 11 | Convert to interactive block: a dialog asks outputs, then an agent rewrites; ADR-051 unchanged; nothing mechanical | §11.5 L825-843; §16; spec FR-036 | Faithful (extra dialog fields: P3-10) |
| 12 | Name "MiniApp" | Used consistently; no "Mini App" or "Miniapp" variants | Faithful |
| 13 | The two tutorial steps keep `route_to: previewers`, which now opens All Previewers; the what-is-a-type sentence changes lightly and is marked as awaiting owner review | Spec FR-040 ("in wording proposed here for the owner's review") and the §6 assumption; ADR L757-758. Step ids, `route_to`, `highlight`, and the current copy match the YAML (`welcome-to-scistudio/tutorial.yaml:371-377`, `what-is-a-type/tutorial.yaml:722-730`) | Faithful and correctly marked as a proposal. Dialog dismissal: P2-5; ADR wording: P3-4 |

Claim 14, overclaim checks against the code:

| Statement | Evidence | Verdict |
|---|---|---|
| ADR-022 resource admission reserves memory for no process | `src/scistudio/engine/resources.py:222-233`: psutil watermark only; "Memory is not reserved" | True (but see P3-7 for "does not count it") |
| No tool can open a frontend tab | `handleLifecycle.ts:35-61` auto-opens workflow tabs on agent-driven events | Overstated: P2-2 |
| ADR-053 promotion handles single files only | `src/scistudio/api/routes/user_library.py` module rules 2 and 4 (bare `.py` basename, lands directly in the root); `_validate_filename` at L186; the agent tool's `_library_filename` | True |
| Canvas nodes have no context menu today | No `onContextMenu` or `onNodeContextMenu` in `WorkflowCanvas.tsx` or `components/nodes/`; the only context menus are in the terminal and the project tree | True |
| Block processes and agent commands share one registry | Two instances: P2-1 | False as written |
| Previewers tab, New menu, tips card #1997, the preview tab dropped on focus change (#2112), and #1983 keeping the last successful run | `ActivityBar.tsx:43`; `FileOperationsGroup.tsx:99-106`; `PaletteTipCard.tsx:8`; `tabSlice.parts/workflowTabActions.ts:111`; `core/lineage/retention.py:1` | True |

## 4. Structure And Cross-References

- **ADR outline.**
  - The first H2 is `## 1. Decision Summary`, followed by `### 1.1 Problems
    Addressed`, and the table has the four required columns.
  - All 13 "Detailed section" values (Sections 2, 3, 4, 5, 6, 8, 9, 10, and 11)
    point at later sections that exist and explain the problem.
  - Scope (§12), verification (§14), consequences (§15), and alternatives (§16)
    are present.
  - The frontmatter keeps `status: Proposed`, `phase: planning`,
    `agent_editable: false`, and `date_accepted: null`.
  - The owner's authorization to edit the body is recorded in the ledger's
    `owner_directive`.
- **Renumbering.** Old §10–14 (Scope through Alternatives) are now §12–16. Every
  internal reference was checked:
  - "(Section 14)" at L406 now names Verification, as the old "Section 12" did.
  - "(Section 16)" at L745 names Alternatives, which contains "A notebook beside a
    panel".
  - Sections 10, 11, and 11.5 are cited correctly throughout.
  - Cross-ADR sections resolve: ADR-051 §2, §3, and §4; ADR-053 §4.1 and §5.2;
    ADR-055 §5.3 ("Arbitrary Code Is An Intended Capability"), §2, and §8.
- **`adr-054-panels.md`.** It cites only ADR-054 §2–§9 (L32-34, 239, 299, 342,
  363, 385, 564, 877). None of those sections was renumbered, and each still
  points at matching text. Its FR-002 and FR-005 edits and its Phase D row agree
  with the new spec. The scope-out line narrowed to "Per-panel Python providers
  for reads" matches ADR §5.
- **`adr-054-miniapp.md`.**
  - All required SpecKit sections are present, including the §4.1–§4.5
    subsections.
  - Every user story has "Why this priority", an independent test, and at least one
    Given/When/Then scenario.
  - Assumptions carry sources.
  - The change summary names the manual owner request and #2341.
  - Its references to `adr-054-panels` FR-002, FR-009, FR-012, and FR-016, and
    to Phase A T-001, T-005, T-010, and T-011, resolve to the matching
    requirements and tasks.
  - The priority issue is P3-3.
- **Consistency between the spec and ADR-054.**
  - The `miniapp` row of the context table (read, call, no write back, no `open`)
    matches FR-004.
  - The project-tier root `<project>/panels/` in FR-024 matches `adr-054-panels`
    FR-004.
  - `.py` is kept off the token-scoped route (FR-017), consistent with ADR §4's
    file-type allowlist.
- **Superseded issue text.**
  - The issue's "No Panels tab: the Previewers tab stays" is superseded by owner
    decision 9, and the documents follow the later decision.
  - The issue's deferral of sample-based panel preview is out of this change's
    scope: the issue says it will be recorded under #2288 when implementation
    resumes. `adr-054-panels.md` still specifies `panel.sample.json`
    (FR-046, T-010). Information only.
