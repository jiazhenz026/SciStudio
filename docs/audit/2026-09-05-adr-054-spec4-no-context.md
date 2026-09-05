# Audit: ADR-054 Spec 4 — The Explore Frontend (no-context)

- Date: 2026-09-05
- Persona: `audit_reviewer`, **no-context** mode
- Agent: S4-E1
- Branch / worktree: `audit/2253-no-context` @
  `C:/Users/jiazh/workspace/SciStudio/.worktrees/s4-e1`
- Subject: `frontend/src/explore/**`, `frontend/src/store/exploreSlice.ts`,
  `frontend/src/store/types.ts`, `frontend/src/types/api.ts`,
  `frontend/src/types/explore.ts`, `frontend/src/types/ui.ts`,
  `frontend/src/App.tsx`, `frontend/src/App.parts/ProjectWorkspace.tsx`,
  `frontend/src/hooks/useWebSocket.parts/**`,
  `frontend/src/components/WorkflowCanvas*`, `nodes/BlockNode.tsx`,
  `ProjectTree*`, `BlockPalette*`, `DataPreview.tsx`, `frontend/e2e/**`
- Judged against: `docs/specs/adr-054-explore-frontend.md` (FR-001..FR-036,
  SC-001..SC-014), `docs/adr/ADR-054.md`, and — as the contracts this spec
  consumes — `docs/specs/adr-054-explore-session.md` and
  `docs/specs/adr-054-panel-contract.md`
- Server side read read-only as the other half of every wire:
  `src/scistudio/api/routes/explore.py`, `src/scistudio/api/routes/panels.py`,
  `src/scistudio/api/ws.py`, plus `src/scistudio/explore/session.py`,
  `kernel.py`, `dependency_analysis.py`, `src/scistudio/api/schemas.py` and
  `src/scistudio/engine/scheduler/_dispatch.py` where a payload had to be
  traced to its emitting call site.

Per the dispatch I read no GitHub issue, PR, PR comment, commit message, gate
ledger, assembly checklist, follow-up register, or other dispatch prompt, and
ran no `gh` and no `git log`/`git show` for the branches under audit. Where a
source file's own comment cites `docs/planning/adr-054-assembly-followups.md`,
I quote the comment as evidence that the gap is disclosed in the tree; I did
not open that register. Everything below is from the source tree, the
governing documents, and commands I ran.

---

## 0. What I Actually Ran

| Command | Result |
|---|---|
| `npm ci` in `frontend/` (`node_modules` was absent) | exit 0 |
| `npm run test` (`vitest run`) | **2570 passed / 1 failed** across 217 files, exit **1**. The one failure is `src/__tests__/eslint-config.test.ts > loads the project flat config without parser errors` — `Error: Test timed out in 5000ms`, actual 13438 ms. A machine-speed timeout in a config-loading test, in no explore surface. The same test failed the same way in this repository's `docs/audit/2026-09-03-panel-contract-no-context.md` (11374 ms), so it is pre-existing and environmental. **Discounted.** |
| `npm run lint` (`eslint .`) | **✖ 72 problems (1 error, 71 warnings)**, exit **1**. The single error is in a file this work created — see F-1. |
| `npm run build` (`tsc -b && vite build`) | exit **0**, `✓ built in 5.28s`. This is SC-008's build half: the frontend builds with `InteractiveModals` deleted. |
| `npm run typecheck` (`tsc --noEmit`) | exit 0, clean |
| `npm run format:check` (`prettier --check .`) | exit 0, "All matched files use Prettier code style!" |
| `PYTHONPATH=./src python -m pytest tests/api tests/panels -q --no-cov` | **2127 outcomes: 2115 passed, 11 skipped, 1 failed**, exit 1. The one failure is `tests/api/test_explore_branch_switch.py::test_a_branch_switch_kills_the_real_kernel_process`, and it is an artifact of the command my dispatch specifies rather than a defect — see the note below. The 11 skips are platform opt-outs (symlink-needs-elevation ×4, POSIX-only semantics ×3, macOS-only ×2, an R interpreter, an environment probe). |
| `PYTHONPATH=<absolute>/src python -m pytest tests/api/test_explore_branch_switch.py -q --no-cov` | **all 5 passed**, exit 0 |
| `grep -rniE "ws://\|wss://\|jupyter\|zmq\|kernel_id\|kernelUrl" frontend/src` | Only `components/AIChat/hooks/usePtyWebSocket.ts` (the pre-existing AI PTY socket) and prose in `explore/NotebookShell.tsx` / `explore/OutputRenderer.tsx`. **SC-013 holds.** |
| `ls frontend/e2e/specs/` | `adr050-canvas-readability.spec.ts`, `system-flows.spec.ts` — see F-2 |
| `ls frontend/src/App.parts/InteractiveModals*` | absent — see F-12 |

`npm run check:ci` in `frontend/package.json` is
`lint && format:check && typecheck && test && build`. Two of its five stages
fail as the tree stands: `lint` on F-1, `test` on the pre-existing
`eslint-config` timeout.

**A note on the Python failure, because it would otherwise be reported as a
regression.** `PYTHONPATH=./src` is a *relative* path. The test starts a real
`ipykernel` process, and that subprocess is launched with the temporary project
directory as its working directory, so `./src` resolves to
`<pytest tmpdir>/projects/demo-project/src`, which does not exist. The kernel
therefore cannot import `scistudio`, and the bridge install fails with the
message the code itself predicts:

```
scistudio.explore.kernel_bridge.BridgeProtocolError: The kernel bridge did not
answer: ModuleNotFoundError: No module named 'scistudio'. The usual cause is a
kernel whose interpreter cannot import scistudio.
```

Re-running the same file with an absolute `PYTHONPATH` passes all five tests.
The failure is a property of the relative path in the dispatch's command
(AGENTS.md forbids `pip install -e .`, which is what would otherwise put
`scistudio` on the kernel's path), not of the code. **Discounted** — and worth
noting for anyone else running this suite the same way.

---

## 1. Blocking Findings (P1)

### F-1 — `npm run lint` fails on dead scaffolding in a file this work created

```
C:\...\.worktrees\s4-e1\frontend\src\explore\regions\ExploreRegions.tsx
  62:10  error  'Placeholder' is defined but never used.
                Allowed unused vars must match /^_/u   @typescript-eslint/no-unused-vars

✖ 72 problems (1 error, 71 warnings)
LINT_EXIT=1
```

`frontend/src/explore/regions/ExploreRegions.tsx:62` defines a `Placeholder`
component that the module's own docstring explains was the seam each region
owner would replace ("one placeholder component per region … an owner replaces
a body here"). Every region has since been replaced with its real component —
`NotebookRegion`, `VariableStripRegion`, `PanelSlotRegion`, `GraphViewRegion`,
`ToolbarRunControls`, `ToolbarKernelControls`, `ToolbarPauseControls` all
render real children — and `grep -n "Placeholder" ExploreRegions.tsx` returns
the definition and nothing else. The scaffold is dead and ESLint says so.

This is a regression against the recorded baseline: this repository's
`docs/audit/2026-09-03-panel-contract-no-context.md` §0 records
`npm run lint` at "**0 errors**, 42 warnings". It is now 1 error, 71 warnings,
and the error is in `frontend/src/explore/**`.

Blocking because `check:ci` runs `lint` first. Fix is a one-line deletion.

### F-2 — FR-036 / SC-014 / T-016: the end-to-end scenario does not exist

`docs/specs/adr-054-explore-frontend.md` names it twice:

- line 90, frontmatter `tests:` — `frontend/e2e/specs/adr054-explore.spec.ts`
- line 649, §4.2 — `| frontend/e2e/specs/adr054-explore.spec.ts | create | The
  end-to-end scenario (FR-036). |`

The file does not exist:

```
$ ls frontend/e2e/specs/
adr050-canvas-readability.spec.ts
system-flows.spec.ts

$ grep -rn "adr054-explore" frontend/ docs/specs docs/adr
docs/specs/adr-054-explore-frontend.md:90
docs/specs/adr-054-explore-frontend.md:649
```

`frontend/playwright.config.ts:4` sets `testDir: "./e2e/specs"`, so the
scenario has nowhere else to live, and `grep -i explore` over
`frontend/e2e/specs/system-flows.spec.ts` and
`frontend/e2e/support/systemMocks.ts` returns nothing — the existing e2e
suites do not cover a session either.

FR-036 requires "one end-to-end scenario MUST open a session from a block, run
a cell, open a panel, emit a cell from it, see a stale mark, run the stale set,
and package". SC-014 measures it. §4.4 states the reason it is required:

> It exists because the pieces this spec assembles are proven individually
> elsewhere and the failure this spec can introduce is between them.

So the one class of failure the spec identified as this spec's own is the one
class with no test. Unit coverage of the parts (which is good — see §4) does
not substitute, by the spec's own argument.

### F-3 — FR-004, FR-030 and SC-010 are inert: the packaged-notebook marker is not on the wire

`frontend/src/types/api.ts:236` declares a field the server does not send:

```ts
  notebook_filename?: string | null;
```

The server's `BlockSummary` (`src/scistudio/api/schemas.py:165-207`) has no
such field, and `grep -c notebook_filename src/scistudio/api/routes/blocks.py`
returns `0` — `_summary` never sets it. The only places `notebook_filename`
exists in the backend are `ClassVar`s on the generated block class
(`src/scistudio/explore/packaging.py:1222,1338`) and one user-guide example,
none of which reach the palette response.

The consequence is total, because one predicate gates both features:

```ts
// frontend/src/explore/packagedBlock.ts:61
export function isPackagedNotebookBlock(summary: BlockSummary | undefined): boolean {
  return Boolean(summary?.notebook_filename);
}
```

It answers `false` for every block the running product will ever see.
Therefore:

- **FR-030** ("A packaged block's node MUST carry a notebook badge") — the
  badge at `frontend/src/components/nodes/BlockNode.tsx:267-274` never renders.
- **FR-004** ("Double-click on a packaged block's node MUST open its notebook")
  — `useCanvasHandlers`'s packaged branch never fires; the double-click keeps
  its pre-ADR-054 subworkflow-only behaviour.
- **US5 acceptance scenario 4** cannot pass.
- **SC-010**'s badge and double-click halves are unmeasurable outside unit
  tests that supply the field themselves —
  `frontend/src/components/nodes/__tests__/BlockNode/notebookBadge.test.tsx:41,61`
  pass `notebook_filename: "segment_cells.ipynb"` by hand.

**This is not a hidden failure.** It is the repository's known "a hand-written
fixture agreeing with the frontend while both disagree with the server" shape,
but the authors caught it: `frontend/src/explore/packagedBlock.ts:10-27` states
the gap and carries a tracked `TODO(#2253)`; the type's own doc comment
(`types/api.ts:222-235`) says "**the backend does not send this field yet**";
the badge test's header says "as the backend stands, `BlockSummary` does not
carry `notebook_filename` at all … so *every* node today takes the 'not on
others' branch"; and
`frontend/src/components/WorkflowCanvas.parts/__tests__/exploreContextMenu.test.tsx:243-256`
asserts the production behaviour explicitly ("treats no block as packaged while
the backend sends no marker"), deleting the field from the fixture first.

What makes it P1 anyway is the governing document. `docs/specs/adr-054-explore-frontend.md`
still states FR-004, FR-030 and SC-010 as unqualified MUSTs, its
`planned_governs` block is empty, and nothing in the spec or in `ADR-054.md`
records that two of its functional requirements are unmet in the shipped
product. A reader of the spec would conclude the badge works. Either the spec
needs the deferral written into it, or the one backend field needs adding.

---

## 2. Non-Blocking Findings (P2)

### F-4 — FR-002's "has outputs" is answered from a store that does not survive a reload

This is the one undisclosed instance of the dispatch's "a default substituting
for an unreceived event", and the two sides genuinely disagree.

The canvas menu gates the explore action on an in-memory event log:

```ts
// frontend/src/components/WorkflowCanvas.parts/useCanvasHandlers.ts:297-307
      const canExplore = hasExploreableOutputs(node.id, blockOutputs);
      ...
        disabledReason: canExplore ? null : NOTHING_TO_EXPLORE_REASON,
```

```ts
// frontend/src/explore/packagedBlock.ts:44-51
  const outputs = blockOutputs?.[nodeId];
  if (!outputs) return false;
  return Object.keys(outputs).length > 0;
```

`blockOutputs` is written only from live `block_done` events
(`frontend/src/store/executionSlice.ts:45`), is initialised to `{}`
(`:17`), is cleared by `resetExecution` (`:73`), and is **not** in the
persistence whitelist — `frontend/src/store/index.ts:140-169` persists
`activeBottomTab`, `paletteCollapsed`, `previewCollapsed`,
`bottomPanelCollapsed`, `panelSizes`, `terminalTabs`, `activeTerminalTabId`,
`tabs` and `activeTabId`, and nothing else.

The server answers the same question from the persisted lineage store:

```python
# src/scistudio/explore/session.py:2525-2542
    def latest_block_outputs(self, block_id: str) -> BoundRun | None:
        """The outputs of the most recent completed run of *block_id*."""
        rows = self._store.execute_query(
            """
            SELECT be.block_execution_id, be.run_id
            FROM block_executions be
            JOIN runs r ON be.run_id = r.run_id
            WHERE be.block_id = ? AND be.termination = 'completed'
            ORDER BY be.started_at DESC, be.rowid DESC
            LIMIT 1
```

So after a page reload — or on the ordinary case of opening SciStudio on a
project whose workflow ran yesterday — every block node's "Explore outputs"
action is disabled with "This block has not produced any outputs yet", while
`POST /api/explore/sessions` with `source: "block_outputs"` would open a
session over exactly those outputs. FR-002's disabled state is meant for a
block that "has never produced" outputs; here it fires for one that has.

The runtime's own refusal path for this is written and unreachable:
`NothingToExploreError` is mapped to `409 nothing_to_explore`
(`src/scistudio/api/routes/explore.py`, `_REFUSALS`), and the menu never lets
a request get far enough to receive it.

`packagedBlock.ts:35-43` states the rule it implements — "'The runtime reports
no outputs' is the whole test: `blockOutputs` is written from the engine's
`block_done` events, so a node absent from it … has produced nothing **in this
session**" — which is accurate about the mechanism and is precisely the
problem: "in this session" is not what FR-002 asks. Unlike F-5, F-6, F-7 and
F-10, this one carries no `TODO` and no follow-up reference.

### F-5 — FR-026's escalation guesses which run is paused

`frontend/src/explore/ExploreTab.tsx:108-120`:

```ts
  const carried = prompt.data?.run_id;
  let runId = typeof carried === "string" && carried !== "" ? carried : null;
  if (!runId) {
    const listed = await lineageApi.lineage.getRuns({ workflowId: prompt.workflowId, limit: 1 });
    runId = listed.runs[0]?.run_id ?? null;
```

The fallback is not a fallback — it is the only path. The engine's
`interactive_prompt` payload (`src/scistudio/engine/scheduler/_dispatch.py:638-670`)
carries `workflow_id`, `block_type`, `panel_manifest`, `panel_descriptor`,
`panel_payload` and `input_signature`, and **no `run_id`**. So every
escalation binds the notebook to "the newest run of that workflow" rather than
to the run that is paused.

FR-026 says the control "opens a session over the paused run's inputs". With
two runs of the same workflow in flight, or a newer run started while an
earlier one sits at a pause, the notebook opens over the wrong run's inputs
and the person explores data that is not the data their decision is about.
This is the dispatch's "a default substituting for an unreceived event" shape.

Disclosed in the tree with a `TODO(#2253)` at `ExploreTab.tsx:102-107`. The
fix is one field on the engine event, which is spec 3's surface, not this
spec's.

### F-6 — The version graph is derived in two places; the backend's answer is dropped by the route

The backend already computes version edges:

```python
# src/scistudio/explore/dependency_analysis.py:1125
def _version_edges(edges: Sequence[Edge], changed_sets: Mapping[str, frozenset[str]]) -> tuple[VersionEdge, ...]:
    """Derive the version-level edges from the cell-level ones (FR-016)."""
```

and puts them on the graph (`dependency_analysis.py:1276`,
`version_edges=_version_edges(edges, changed_sets)`). But `GraphResponse`
(`src/scistudio/api/routes/explore.py:658-668`) publishes `cells`, `edges`,
`unresolved_reads`, `unknown_binding_cells` and `changed_sets` — and never
`version_edges`. So `frontend/src/explore/GraphView.tsx`'s `buildVersionGraph`
(line 121) re-performs the derivation from the two inputs.

The module says so itself, at `GraphView.tsx:14-35`, and carries a
`TODO(#2253)`. Recorded as a finding regardless because the spec's own §4.5
names this exact failure shape for marks — "a mark computed in two places
would disagree in exactly the cases that matter" — and the mitigation the spec
chose for marks (send them, never derive them) is available here for one line
of `GraphResponse`. The route is dropping an answer the runtime already has.

FR-032's wording ("edges from the analysis event with their origin") reads as
though the version edges arrive; they do not.

### F-7 — FR-010's delete and move are unimplementable, and two specs disagree about it

`frontend/src/explore/NotebookShell.tsx:320-347` renders Move up, Move down and
Delete permanently `disabled`, with:

```ts
const NO_ROUTE_TITLE =
  "The Explore session API carries no route for this yet — see the ADR-054 follow-up register, S4-A2 F-A2-001.";
```

That is accurate. The session router
(`src/scistudio/api/routes/explore.py`) exposes `GET`/`POST` on
`/cells`, `PUT` on `/cells/{cell_id}` and `/cells/{cell_id}/enabled`, and no
delete or reorder. `ExploreNotebookDocument.remove_cell` exists
(`src/scistudio/explore/notebook.py:587`) and nothing routes to it.

The disagreement is between the two specs:

- `docs/specs/adr-054-explore-frontend.md` FR-010: "The shell MUST offer add,
  delete, and move for cells, a per-cell run control, and a per-cell enable
  toggle, **each sent to the session API**".
- `docs/specs/adr-054-explore-session.md` FR-056's operation list, as
  summarised in `explore.py`'s own module docstring: "read and write cells;
  run one cell, the stale set, or a cell with its upstream; toggle a cell
  enabled" — no delete, no move.

Spec 4 requires a route spec 3 never promised. The deferral is tracked in code
per AGENTS.md §3.6, but neither spec records it, and FR-010 still reads as a
satisfied MUST.

### F-8 — FR-017's external-edit re-read is missed on a second consecutive external edit

`frontend/src/explore/NotebookShell.tsx:421`:

```ts
  const reloadReason = session?.lastAnalysisReason ?? null;
```

and the effect at `:631-645` is keyed on `reloadReason`, firing
`readExploreCells` when it equals `"external_edit"`.

`frontend/src/store/exploreSlice.ts`'s `applyEventToSession` handles
`explore.analysis_updated` by writing `lastAnalysisReason` and nothing else —
no counter, no timestamp. The runtime publishes the event as
`{"reason": "external_edit"}` with no discriminator
(`src/scistudio/explore/session.py:605`).

So a second external edit with no intervening `analysis_updated` of another
reason leaves `lastAnalysisReason === "external_edit"` unchanged, React's
dependency array does not change, the effect does not re-run, and the shell
goes on showing the notebook as it was before that second edit. FR-017
requires the shell to "reconcile a reload event with unsaved edits"; here the
reload event is silently dropped.

The same file carries a separate tracked `TODO(#2253)` at `:648-657` for a
related gap: a conflicting draft is lost on a tab switch because drafts live in
the component rather than the slice. That contradicts the spec's edge case
"an editor with unsaved edits for a cell whose id survived keeps its draft and
is marked as conflicting **until saved or discarded**".

### F-9 — An interrupted cell is indistinguishable from one that finished

The kernel reports three statuses:

```python
# src/scistudio/explore/kernel.py:225
    status: Literal["ok", "error", "abort"]
```

and `cell_output` carries it verbatim
(`src/scistudio/explore/session.py:1276-1282`). The slice maps one of the
three:

```ts
// frontend/src/store/exploreSlice.ts, applyCellOutput
      runState: payload.status === "error" ? "error" : cell.runState,
```

`"abort"` falls through, and the `cell_state` idle event that follows the run
(`session.py:1293`) then renders the interrupted cell as plain `idle`.
`frontend/src/types/ui.ts:200` confirms there is no state to render it as:

```ts
export type ExploreCellRunState = "never-run" | "queued" | "running" | "idle" | "error";
```

Spec US2 acceptance scenario 6: "**Given** a running cell, **When** the person
interrupts, **Then** the interrupt is sent and the cell shows the interrupted
state when the event arrives." The interrupt is sent; the interrupted state is
not shown. The runtime's own word for it is on the wire and is discarded.

### F-10 — FR-019's producing resolution is an exact type match, not the capability ladder

`frontend/src/explore/PanelSlots.tsx`'s `resolveProducingPanel` asks
`GET /api/panels?target_type=<typeName>`. That route filters by string
equality:

```python
# src/scistudio/api/routes/panels.py:349-350
    if target_type is not None:
        specs = [spec for spec in specs if spec.target_type == target_type]
```

No supertype walk, no per-type producing choice. A variable whose SciStudio
type has no exactly-registered panel gets nothing mounted, even where a panel
registered for its supertype would serve it — which is the resolution
`docs/specs/adr-054-panel-contract.md` defines and `PreviewRouter.resolve_request`
implements for a *request*, but which no HTTP route exposes for a bare type
name.

Disclosed at `PanelSlots.tsx:117-133` with a tracked `TODO(#2253)`. FR-019
("requesting the producing capability for the variable's type") is met in
letter for exactly-matched types and not met for inherited ones.

I checked the capability half and it is correct: `panel_descriptor_model(panel)`
at `panels.py:318` is called without `granted_capability`, so the descriptor
carries `manifest.capability` (`src/scistudio/panels/descriptor.py:149`), and
`resolveProducingPanel` selects a row only when
`capabilitySatisfies(row.capability, "producing")` — so a producing mount gets
a producing descriptor and the displaying fallback gets a displaying one, which
is what panel-contract FR-049 requires.

---

## 3. Minor And Informational (P3)

### F-11 — Spec §4.2 and frontmatter name paths that do not exist, and one file that was not touched

Every path in `governs.files` resolves (the `frontend/src/explore/**` and
`ProjectTree.parts/**` globs cover the files added under them). The `tests:`
list and the §4.2 table do not:

| Spec says | Actually |
|---|---|
| `frontend/src/store/exploreSlice.test.ts` | `frontend/src/store/__tests__/exploreSlice.test.ts` (plus `exploreDispatch.test.ts`) |
| `frontend/src/explore/SessionToolbar.test.tsx` | `frontend/src/explore/SessionToolbar.runControls.test.tsx` |
| `frontend/src/components/WorkflowCanvas.parts/useCanvasHandlers.test.ts` | `frontend/src/components/WorkflowCanvas.parts/__tests__/exploreContextMenu.test.tsx` |
| `frontend/e2e/specs/adr054-explore.spec.ts` | **absent** — F-2 |

§4.2 lists `frontend/src/components/DataPreview.tsx | modify | Not rendered
while an Explore tab is active (FR-005)`. `grep -i explore DataPreview.tsx`
returns nothing: the file was not touched. FR-005 is satisfied entirely by
`frontend/src/App.parts/ProjectWorkspace.tsx:654-661`, which is correct — the
table over-claims the file.

§4.2 also does not name four modules that shipped under
`frontend/src/explore/**`: `KernelList.tsx`, `regions/ExploreRegions.tsx`,
`packagedBlock.ts`, and `workspaceFocus.ts`. The first three are ordinary
splits of listed components. `workspaceFocus.ts` implements spec 5's FR-001
and is accounted for by `docs/specs/adr-054-agent-enablement.md:529`, which
names it and defers governance to this spec's glob — correct, but spec 4's own
narrative never mentions it.

### F-12 — `InteractiveModals` is retired; one sibling spec is now stale about it

Verified retired:

- `frontend/src/App.parts/InteractiveModals.tsx` — absent.
- `frontend/src/App.parts/InteractiveModals.parts/` — absent.
- `grep -rn "InteractiveModal" frontend/src` returns only prose comments plus
  the two negative assertions in
  `frontend/src/hooks/useWebSocket.parts/dispatchEvent.test.ts:96-109`.
- `npm run build` exits 0 with them gone, which is the spec's own proof
  ("The frontend build must succeed with the modal deleted, which is what
  proves nothing else imported it", §4.4) — and SC-008's build half.
- `frontend/src/App.tsx:13` carries the note that it is gone; nothing mounts it.
- `frontend/src/panels/index.ts:6` and
  `frontend/src/panels/__tests__/panelHostilePayload.test.ts:16` reference the
  old paths only in comments describing what was superseded.

One stale document: `docs/specs/adr-054-panel-contract.md:714` still carries
`| frontend/src/App.parts/InteractiveModals.tsx | modify | …`. That spec
predates FR-024's delete. `docs/specs/adr-051-interactive-blocks.md:340`
records the supersession explicitly ("**Deleted by ADR-054 spec 4 FR-024**"),
so the pattern for fixing it exists; the panel-contract spec has not had it
applied.

### F-13 — The kernel list is arbitrated in the frontend

`frontend/src/explore/KernelList.tsx:89-124` merges
`GET /api/explore/kernels` with the per-session `kernel` views: it **drops** a
row the response returned (`if (stated && !LIVE_STATES.includes(state) &&
!needsRestart) continue;`) and **adds** rows the response did not carry. Every
individual value is a runtime statement, and `isStated()` at `:69-71` is a
careful guard against reading `emptySession`'s `"not-started"` default as a
runtime answer — this is good work. But *which rows the project's kernel list
has* is a frontend decision, and the rendered list can differ from what
`GET /api/explore/kernels` said. FR-015 ("from the kernel-state events") is met
in letter. Recorded because it is the one place the frontend arbitrates
between two runtime answers rather than drawing one.

### F-14 — `changed_names.unobservable` is flattened session-wide

The runtime sends `unobservable` per cell
(`src/scistudio/explore/session.py:1284-1290`); `applyChangedNames` in
`frontend/src/store/exploreSlice.ts` writes it to
`session.unobservableNames`, so the last cell to run overwrites the previous
cell's list. No FR governs this field, and nothing renders it today.
Informational.

### F-15 — `runStateFromWire` accepts a state the runtime never publishes

`frontend/src/store/exploreSlice.ts`'s `runStateFromWire` maps `"queued"`, but
the runtime publishes `cell_state` only with `"running"`
(`session.py:1117-1119`) and `"idle"` (`session.py:1293-1294`). Harmless dead
branch; noted only because it is the one place the frontend's event vocabulary
is wider than the server's.

---

## 4. What Checked Out

These are the two things the dispatch weighted most, and I found no defect in
either beyond what is above.

### 4.1 The wire, field by field

I compared `frontend/src/types/explore.ts` (re-exported wholesale by
`frontend/src/types/api.ts`) against every pydantic model in
`src/scistudio/api/routes/explore.py:477-853` — name, optionality and type —
and against every event payload at its emitting call site in
`src/scistudio/explore/session.py`. **They agree.** Specifically:

- All 25 request/response models map one-to-one, including the awkward ones:
  `CellModel.cell_id: str | None`, `PackagingProblemModel.refuses` (server
  default `True`, always serialised, so required on the frontend is right),
  `BindingModel`'s four optional type fields, `KernelListItem.started_at:
  float | None` → `number | null`.
- All nine event types in `SessionEventType`
  (`src/scistudio/explore/session.py:374-382`) are present, prefixed, in
  `EXPLORE_EVENT_TYPES`, and the prefix constant matches
  `EXPLORE_EVENT_PREFIX = "explore."` (`explore.py:97`).
- The frame envelope matches `serialise_session_event` (`explore.py:319-334`):
  `session_id` at the top level, payload under `data`, ISO timestamp. The
  frontend comments on exactly this and re-types the frame rather than passing
  it as a `WorkflowEventMessage` (`dispatchEvent.ts:105-128`).
- The three shapes of `cell_state` are documented in
  `types/explore.ts` and all three handled by `applyCellState` — including the
  restart shape `{reason, marks}` with no `cell_id`.
- `ExploreKernelState` matches `KernelState = Literal["not-started",
  "starting", "idle", "busy", "dead"]` (`src/scistudio/explore/kernel.py:127`)
  exactly, and `types/explore.ts` explains why `ui.ts`'s display union is
  deliberately wider.
- `opened_over`'s vocabulary (`"block_outputs" | "paused_run" |
  "packaged_block" | "file"`, `session.py:2060,2544,2552,1679`) matches the
  one string `VariableStrip.declaredOutputNames` compares against.
- `POST /sessions/{id}/commit` takes `message` as `Body(embed=True)`
  (`explore.py:1041-1046`) and the client sends `{"message": …}`
  (`lib/api/explore.ts:74-80`). `DELETE /sessions/{id}` takes `commit` as a
  query param and the client sends it as one.

**The fixtures are the server's, not the frontend's.** I checked
`frontend/src/store/__tests__/exploreSlice.test.ts:132-280` payload by payload
against the emitting call site: `session_opened` `{notebook_path, opened_over,
run_id}`, `session_closed` `{notebook_path, branch_commit}`, `kernel_state`
`{state, pid, memory_bytes, needs_restart}`, `cell_state` in both its running
and idle shapes, `cell_output` `{cell_id, status, execution_count, outputs}`,
`changed_names` `{cell_id, changed, unobservable}`, `analysis_updated`
`{reason, cell_id}`, `commit_recorded` in both its branch and per-run shapes,
`packaged` with all seven fields. Each matches. The repository's known failure
mode — a hand-written fixture agreeing with the code beside it — is **not**
present in the slice suite. It is present exactly once, at
`BlockSummary.notebook_filename` (F-3), and there the authors caught it and
wrote a test asserting the production behaviour.

### 4.2 Runtime truth

FR-034 holds in the slice. `frontend/src/store/exploreSlice.ts` computes no
mark, no kernel state and no binding:

- Marks are copied from the runtime's `marks` map and filtered only to the
  runtime's own three-value vocabulary (`MARK_KINDS`, matching
  `ExploreCellMarkKind`, matching `CellMark`'s wire values). `applyMarksMap`
  writes the *absences* too, which is what makes a cleared mark clear.
- `VariableEntry.live` is `BindingModel.exists_in_kernel` copied
  (`bindingFromModel`), with the comment "Copied, never guessed".
- Kernel state is stored verbatim with `needsRestart` kept as a separate flag;
  the one place they are collapsed into a word is a pure render
  (`SessionToolbar.kernelLabel`, lines 41-53), which is the right place.
- `CellMarks.tsx` renders and computes nothing — no graph, no source
  comparison.
- Ordering is handled by keyed, idempotent writes plus a `lastEventAt` /
  `lastMarksAt` guard, and events for an unknown session id are buffered and
  drained (capped at 200 with a tracked TODO for the silent overflow). This is
  a real answer to the spec's "Events out of order" risk, not a claim.
- `applyExploreRunRequests` is the one write that reflects a command without an
  event, and it is defensible: it writes `queued` from the run *response*,
  whose `RequestModel.state` is the runtime's own word, because the runtime
  publishes no event for a merely-waiting request. It refuses to demote a cell
  the runtime already said is running. FR-034's first clause allows responses.

FR-023's freeze reads two runtime sources and unions them —
`session.graph.changedSets[cellId]` (from `GraphResponse.changed_sets`, the
same map the backend's own freeze uses) and `cell.changedNames` (from
`explore.changed_names`) — with "which cell is running" taken from
`cell_state` alone (`PanelSlots.frozenNamesOf`, lines 201-210). Reads continue
while a submission is refused, and the backend refuses independently, so the
two can only differ in how early the person is told.

The emission path is not optimistic: `onEmit` sends, and only on the response
re-reads the cells and applies the queued request
(`PanelSlots.tsx`, `onEmit`). Interrupt, restart and commit write nothing at
all (`ExploreRegions.ToolbarRunControls`), leaving `kernel_state` and
`commit_recorded` to do it.

Three places do derive, and all three are above: the version graph (F-6), the
paused run id (F-5), and the kernel-list membership (F-13).

### 4.3 Other requirements spot-checked and satisfied

| Requirement | Evidence |
|---|---|
| FR-001 tab identity, dedup, persistence, re-fetch | `store/tabSlice.parts/exploreTabActions.ts:26-28` (`explore:<path>`), `store/index.ts:45-60,155-167` (persist by path, drop `sessionId`, exclude pause tabs), `exploreTabActions.ts:137-165` (restore via `source: "notebook"`, which `explore.py:502` supports) |
| FR-002/FR-003 four entries, two new context menus | canvas: `WorkflowCanvas.parts/NodeContextMenu.tsx` + `__tests__/exploreContextMenu.test.tsx`; tree: `ProjectTree.parts/ContextMenu.tsx:57-68` + `ProjectTree.tsx:224-229`, offered only under `rootPath === "data"`; disabled reason in `packagedBlock.NOTHING_TO_EXPLORE_REASON` |
| FR-005/FR-006 layout and collapse | `App.parts/ProjectWorkspace.tsx:375-383` (centre branch, before preview and editor) and `:645-661` (right column swap inside the existing collapsible `ResizablePanel`); left pane and bottom panel untouched |
| FR-008 virtualisation | `NotebookShell.tsx:124-160`, `IntersectionObserver` with a documented no-observer fallback |
| FR-009 markdown | `react-markdown` + `remark-gfm`, already in the bundle, edit-in-place at `NotebookShell.tsx:291-298,389-396` |
| FR-011 MIME bundle, ANSI, sandboxed HTML | `OutputRenderer.tsx` — own SGR parser (no new dependency), `<iframe sandbox="">` at `:320-334` granting nothing |
| FR-024/FR-025 pause tab sends the modal's messages | `PanelSlots.EMITTED_CODE_KEY = "code"`, pinned against `src/scistudio/blocks/base/interactive.py`; `dispatchEvent.openPauseTab` places the tab with `notebookVisible: false` |
| FR-027 packaged-ask | `PanelSlots.DECISION_COMMIT_KEY = "notebook_commit"` and `EXPLORE_SESSION_PANEL_ID = "core.explore.session"`, both named against `src/scistudio/explore/packaging.py` |
| FR-028 packaging report | `PackagingReport.canConfirmPackaging` gates on `report.is_packageable` — the runtime's verdict, not re-derived |
| FR-029/FR-031 palette | `BlockPalette.tsx:196-215` refreshes on a changed `packagedSignature`, and offers `InsertBlockCallAction` only while an Explore tab is active |
| FR-032 graph library | `@xyflow/react` + `elkjs` — the pair `WorkflowCanvas` and `WorkflowCanvas.parts/autoLayout.ts` already use, satisfying A-008 with no new dependency |
| FR-033 event routing | `dispatchEvent.ts:123-128` routes by prefix, so a new session event type reaches the slice without a second edit |
| FR-035 / SC-013 | no kernel URL, no second socket — see §0 |

I found no generated document edited by hand in the audited surfaces.

---

## 5. Recommendation

**pass-with-fixes**, with F-1 and F-2 required before merge.

The engineering here is unusually careful: the wire matches field for field,
the slice keeps FR-034 honestly and explains why at each decision, the fixtures
are built from the server's payloads rather than from the frontend's types, and
every gap the authors could not close from inside their write set carries a
tracked `TODO(#2253)` naming the reason. That is why most of §2 is disclosed
rather than discovered. F-4 is the exception, and the one finding I would put
in front of the implementer first: it is undisclosed, it needs no backend
change, and it is the ordinary case rather than an edge case — a person who
opens SciStudio on yesterday's project cannot right-click into any of it.

What must change:

1. **F-1** — delete the dead `Placeholder` in
   `frontend/src/explore/regions/ExploreRegions.tsx:62`. One line;
   `npm run lint` and therefore `check:ci` fail without it. This is a
   regression against a recorded 0-error baseline.
2. **F-2** — write `frontend/e2e/specs/adr054-explore.spec.ts`, or amend the
   spec to defer it with a tracked follow-up. FR-036 and SC-014 are the spec's
   own answer to the only failure class it claims to own, and neither the file
   nor a deferral exists.
3. **F-3** — either add `notebook_filename` to
   `src/scistudio/api/schemas.py::BlockSummary` and `routes/blocks.py::_summary`,
   or write into `docs/specs/adr-054-explore-frontend.md` that FR-004, FR-030
   and SC-010 are unmet pending that field. As it stands the spec asserts two
   MUSTs the product does not deliver.

4. **F-4** — the fix is inside this spec's write set and does not need the
   backend: either persist `blockOutputs`, or ask the runtime. `POST
   /api/explore/sessions` already answers `409 nothing_to_explore` correctly,
   so offering the action enabled and rendering that refusal would be closer to
   FR-002 than the current pre-emptive disable. Whichever is chosen, the menu
   must stop treating an empty in-session event log as "this block has never
   produced outputs".

F-7 also wants a document change rather than code: FR-010 requires routes
spec 3 never promised, and one of the two specs is wrong.

F-5, F-6, F-8, F-9 and F-10 are correctness gaps that do not block: F-8 and F-9
are fixable inside this spec's write set; F-5, F-6 and F-10 each need one field
or one route on the backend and are therefore follow-up work by construction.
