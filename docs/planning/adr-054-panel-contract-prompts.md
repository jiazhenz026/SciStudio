---
title: "ADR-054 Panel Contract Dispatch Prompts"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 48
  - 51
  - 54
language_source: en
---

# ADR-054 Panel Contract Dispatch Prompts

The filled dispatch prompts for the agents listed in
`docs/planning/adr-054-panel-contract-checklist.md` section 6. Each prompt is
filled from the template named in its heading. Prompts are appended as waves are
dispatched; a prompt is never edited after its agent has been dispatched.

## Manager decisions binding on every agent

These are manager rulings on questions the spec leaves to the implementer. They
are recorded here so the audit can check them rather than rediscover them.

- **D-001 — The rename keeps the Python compatibility surface importable.**
  `scistudio.previewers` remains an importable module that re-exports the
  renamed symbols, because FR-045 requires the `scistudio.previewers`
  entry-point group and its `get_previewers()` factory to keep being
  discovered, and a package that supplies that factory imports `PreviewerSpec`
  from that module path. FR-038 permits the retired word to survive in the
  compatibility shim, and this alias is part of it. It carries a deprecation
  note and the ADR-048 addendum's removal condition.
- **D-002 — What "the rename commit changes no behaviour" (SC-011) means
  here.** Files may be moved, and identifiers, imports, module paths, symbol
  names, and the mechanical spelling of a name inside a test may change. No
  assertion's meaning, no fixture behaviour, no control flow, and no test count
  may change. No test may be added or deleted in the rename commit.
- **D-003 — The rename does not touch user-visible copy.** Interface strings a
  person reads stay as they are; revising them belongs to `#2211`, the human
  documentation spec. The rename is a code rename.
- **D-004 — The rename does not change the HTTP wire.** Route paths and
  response field names keep their current spelling in the rename commit.
  Bringing the endpoints under the panel naming is FR-023 behaviour work owned
  by `W3-api`. The one exception is the FR-051 `capabilities` to `features`
  rename, which is explicitly required to land in the rename commit and is
  therefore renamed on both sides of the wire at once.
- **D-005 — The on-disk tier directories keep their names in the rename
  commit.** `~/.scistudio/previewers/`, `<project>/previewers/`, and
  `.scistudio/previewers.json` are read by projects that already exist on
  disk. FR-020 and FR-046 require them to keep working; carrying them over
  under the panel naming is behaviour work owned by `W2-core`.
- **D-006 — `docs/architecture/ARCHITECTURE.md` is not edited.** It is
  owner-controlled and outside this spec's scope. If a drift audit fails
  against it, report the failure to the manager; do not edit the file and do
  not weaken the audit.

---

## W1-rename

Filled from `docs/ai-developer/templates/agent-dispatch-prompt-template.md`.

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-054 spec 1, the unified panel contract; this
  agent delivers its first task, the vocabulary rename that every later task is
  written against.
- Task kind: refactor
- Persona: implementer
- Issue: #2229
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2229
- Umbrella PR: #2230 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-054-spec1-panel-contract
- Agent branch: refactor/2229-panel-rename
- Agent worktree: C:\Users\jiazh\workspace\SciStudio\.worktrees\w1-panel-rename
- Gate record: .workflow/records/2229-refactor-2229-panel-rename.json
  (create it yourself with `gate_record init`)
- Checklist: docs/planning/adr-054-panel-contract-checklist.md

## Required Rules

Read and follow:

- The GitHub issue `#2229` and all owner instructions in it.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/personas/implementer.md
- docs/specs/adr-054-panel-contract.md, in particular FR-038 to FR-041,
  FR-051, task T-001 in section 4.3, SC-011, and the "The rename runs first"
  paragraph in section 4.1.
- The manager decisions D-001 to D-006 in
  docs/planning/adr-054-panel-contract-prompts.md.

## Scope

You own the whole tree for one purpose only: the mechanical rename of the
previewer concept to the panel concept.

- src/scistudio/previewers/** -> src/scistudio/panels/**
- every Python import, symbol, and identifier that names the concept
- frontend/src/** file names, symbols, and identifiers that name the concept
- tests/previewers/** -> tests/panels/**, and every test identifier that names
  the concept

You must not touch:

- docs/architecture/**  (owner-controlled; D-006)
- docs/user/**, docs/package-development/**  (owned by #2211)
- src/scistudio/_skills/**, src/scistudio/_agent_reference/**
- src/scistudio/plot/runtime.py
- docs/planning/adr-054-panel-contract-checklist.md except your own rows
- any behaviour at all

If you need an out-of-scope path, stop and report back. Do not edit it.

## Coordination

- You are not alone in this codebase.
- MUST work only on your assigned branch.
- MUST work only in your assigned worktree.
- MUST NOT use `pip install -e .`.
- Do not revert or overwrite other agents' work.
- Do not broaden scope.
- Do NOT open a pull request. Push your branch; the manager integrates it into
  the umbrella branch.
- MUST NOT merge any PR.
- Edit only your checklist rows.
- Record every completed row with a commit, test, or gate evidence.

## TODO And Deferral Rule

Deferred work must be tracked in the repo.
Use `TODO(#NNN): <reason>` and cite an issue, ADR, spec, or follow-up ticket.
Do not leave hidden V1, MVP, or later work.

Known deferred items:

- TODO(#2211): user-visible interface copy still says previewer; the human
  documentation revision owns it.

## Work To Do

This is T-001. Its whole value is that it is reviewable at its size because it
provably changes nothing. Work in this order.

1. Establish the baseline. Run, and record the result:
   `PYTHONPATH=./src python -m pytest tests/previewers tests/api/test_previewers.py
   tests/api/test_previewer_discovery.py tests/api/test_interactive_panels.py
   tests/architecture tests/adr052_contract -q --no-cov -p no:randomly`
   and the frontend suite for the previewer and interactive-panel surfaces.
   It is green on the branch point; if it is not, stop and report.
2. Rename the Python subsystem: `src/scistudio/previewers/` becomes
   `src/scistudio/panels/`. Use `git mv` so history follows.
3. Rename the Python symbols the concept names: `PreviewerSpec` becomes
   `PanelSpec`, and so on for every symbol, function, parameter, local, and
   docstring mention that names the concept. Keep the names of things that are
   not the concept.
4. Per D-001, leave `src/scistudio/previewers/__init__.py` in place as a thin
   module that re-exports the renamed symbols under their old names, with a
   deprecation docstring that says it exists for the `scistudio.previewers`
   entry-point group (FR-045) and will be removed under the ADR-048 addendum's
   condition. It must contain no logic of its own.
5. FR-051: the free-form `capabilities` tuple that carries feature tags such as
   table and sort becomes `features`, everywhere it is written and read,
   including the API response field and the frontend that reads it, so that the
   word capability is left free to name only the displaying or producing
   capability that later tasks introduce.
6. Rename the frontend files and symbols that name the concept. Move
   `frontend/src/components/DataPreview.parts/dynamicPreviewer.ts`,
   `previewerHostApi.ts`, the previewer store slices, the previewer palette,
   and their tests to the panel spelling. Do not merge, delete, or restructure
   anything; later tasks do that.
7. Move `tests/previewers/` to `tests/panels/` and update identifiers. Obey
   D-002: no assertion's meaning changes and no test is added or deleted.
8. Obey D-003, D-004 and D-005: user-visible copy, HTTP route paths, response
   field names other than the FR-051 rename, and the on-disk tier directory
   names are all left alone.
9. Update `tests/architecture/test_layer_deps.py` and the ADR-052 frozen
   public-symbol inventory only as far as the rename requires to keep them
   passing. If the inventory's stability markers cannot be carried across the
   rename mechanically, stop and report rather than guessing; deriving them is
   FR-041 and belongs to a later task.
10. Re-run the baseline commands from step 1. They must produce the same result
    as they did before the rename.
11. Produce, and include in your report, the list of every name you renamed as
    `old -> new`, and a statement of anything you deliberately left with the
    retired spelling and why.

## Required Tests And Checks

- `PYTHONPATH=./src python -m pytest tests/panels tests/api tests/architecture
  tests/adr052_contract -q --no-cov -p no:randomly`
- the frontend test suite for the renamed surfaces (`npm test` in `frontend/`,
  narrowed to the affected files, then the whole suite once)
- `PYTHONPATH=./src python -m scistudio.qa.governance.gate_record init
  --task-kind refactor --persona implementer --runtime claude-code
  --branch refactor/2229-panel-rename --issue 2229
  --base-ref track/adr-054-spec1-panel-contract
  --owner-directive "<the owner request above>" --include "<your real scope>"`
  Recording `--base-ref` is mandatory: this branch is stacked on the track
  branch, and without it the gate measures your work against origin/main and
  reads other agents' commits as yours.
- `PYTHONPATH=./src python -m scistudio.qa.governance.gate_record check
  --mode local --base track/adr-054-spec1-panel-contract --head HEAD`
- Do not run `gate_record finalize` and do not create a PR; the manager owns
  the final gate evidence and the PR.
- Sentrux: run it if the MCP or CLI is available; record explicitly if it is
  not.

If the task changes wrapper, hook, gate-record, receipt, CI, or AI-runtime
behavior, check whether these docs need updates and record updated paths or
N/A rationale: `docs/ai-developer/rules.md`,
`docs/ai-developer/specific_rules/gated-workflow.md`,
`docs/ai-developer/specific_rules/agent-dispatch.md`, and
`docs/ai-developer/templates/*dispatch*.md`.

## Output Required

Before reporting done, provide:

- Changed file paths, and the `old -> new` rename table.
- Tests/checks run and results, before and after.
- Checklist rows updated.
- The commit sha on `refactor/2229-panel-rename`, pushed.
- Any blocker or scope issue.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file.
- A rename cannot be made without changing behaviour.
- A test would have to change its meaning to keep passing.
- The ADR-052 stability markers cannot be carried across mechanically.
- The task conflicts with AGENTS.md, the ADR, the spec, or the gate record.
- CI or local checks fail for unclear reasons.
```

---

## Manager contract sheet: D-007 to D-013

Added before wave 2. These fix the cross-agent interfaces so that agents working
in parallel converge instead of inventing incompatible shapes. They are derived
from ADR-054 sections 3.2 to 3.6 and 9.2 and from the spec's FR list; where the
spec is silent the manager has chosen, and the choice is recorded here so the
audit can check it rather than rediscover it.

- **D-007 - The on-disk panel form.** A panel is a directory holding
  `panel.json` and its entry document, `index.html` by default (ADR-054 3.3).
  `panel.json` fields:
  `panel_id` (str, required), `display_name` (str, required),
  `target_types` (list[str], required, may be empty only for a
  block-addressed panel), `capability` (`"displaying"` or `"producing"`,
  required), `entry` (str, required, a file name inside the directory),
  `api_version` (str, required), and optional `features` (list[str], the
  FR-051 free-form tags), `priority` (int, default 0),
  `supports_collection` (bool, default false), `provider` (str, a dotted
  reference to a Python provider, FR-047). A declaration missing a required
  field is refused at discovery with a diagnostic naming the directory and the
  field (FR-003).
- **D-008 - The merged asset route.**
  `GET /api/panels/assets/{panel_id}/{asset_path:path}`. One path-confinement
  check and one suffix allowlist for all four tiers, differing only in the root
  each tier resolves to (FR-021). The allowlist is today's previewer set plus
  `.html`: `.html .js .mjs .css .map .json .svg .png .jpg .jpeg .woff .woff2`.
  The route answers read-only cross-origin requests, because a panel runs at an
  opaque origin; no other route gains cross-origin headers. An oversized
  document is a load failure with a readable diagnostic. The two existing routes
  (`/api/previews/assets/...` and `/api/blocks/panels/...`) keep serving their
  existing clients for the duration of the migration (FR-022).
- **D-009 - The core contract module.** `src/scistudio/core/panels.py` owns
  `PANEL_API_VERSION`, `PanelCapability` (exactly two members, `displaying` and
  `producing`, FR-006), `PanelManifest`, `PanelTier`, and the declaration
  validation errors. `src/scistudio/blocks/base/interactive.py` imports
  `PanelManifest` from there rather than defining its own (FR-001, ADR-054 9.2).
- **D-010 - Exactly one API version constant, and it is the backend's.**
  FR-004 and SC-001 require one definition shared by host and panels. It is
  `PANEL_API_VERSION` in `src/scistudio/core/panels.py`. The frontend host MUST
  NOT define or hard-code a version of its own; it receives the accepted version
  from the backend in the panel descriptor it is already reading and compares
  the panel's declared version against that. Any frontend constant spelling a
  version literal is a defect against SC-001.
- **D-011 - The message contract.** Every message in both directions is
  `{ scistudio_panel: 1, token: <per-mount token>, type: <string>, payload: <object> }`.
  The host issues the token at mount; a message without the matching token is
  ignored (FR-008), and the host additionally requires
  `event.source === frame.contentWindow`. The frame is mounted with
  `sandbox="allow-scripts"` and nothing else.
  Host to panel: `init` (the accepted api version, the panel id, the granted
  capability, the opening snapshot or the variable bindings, the read limits,
  and the asset base URL), `update` (a reason and what changed, FR-010),
  `read_result` (a request id and the window read), `error`, `state_request`,
  `teardown`.
  Panel to host: `ready` (the panel's declared api version) which completes the
  handshake, `read` (a request id and a query), `emit` (the code a producing
  panel emits, FR-012), `error`, `state` (the optional serialisable snapshot,
  FR-031).
  The host sends `init` once the frame has loaded and treats a panel that has
  not answered `ready` within a bounded wait as a load failure (FR-009). The
  bounded wait is a named constant, not a scattered literal.
  The host grants `emit` only to a panel mounted with the producing capability;
  an `emit` from a displaying mount is dropped and reported, and the grant is
  enforced by the host rather than by the panel's restraint (FR-011, SC-007).
- **D-012 - Where the frontend host lives.** `frontend/src/panels/`, with
  `PanelHost.tsx` and `PanelHost.test.tsx` — ADR-054's `tests:` list names both
  paths, so they are fixed. Alongside them: `panelMessages.ts` (the D-011
  envelope and its type guards), `panelFrame.ts` (frame creation, token issue,
  handshake, bounded wait), `panelCapability.ts` (the outbound grant), and the
  reload hook. One loader and one host API; the two retired loader modules and
  the retired host API module are deleted, not wrapped (SC-002).
- **D-013 - The backend names the fallback.** The response the host already
  reads gains the id of the fallback panel to mount when the chosen panel fails
  (FR-015). The frontend's `CoreFallbackRenderer` switch on envelope kind in
  `coreViewers.tsx` is deleted (FR-036, SC-010); its error surface and
  diagnostics banner survive as host chrome and must still render when the frame
  mechanism itself is unavailable (FR-035).
- **Out of scope, stated so no agent adds it:** the AST whitelist that admits
  only rebinding assignments, imports, and `scistudio.output` calls
  (ADR-054 3.6) sits where an emission is queued, which is the explore session.
  FR-012 says the panel loading machinery MUST NOT interpret what a panel emits.
  Do not implement the whitelist in this spec.

---

## Manager contract sheet: D-014 to D-016

Added after `W2-host` landed the frame host and reported back.

- **D-014 - The `planned_governs` migration is the manager's, and one finding is
  expected until integration.** `full_audit` raises, at error severity,
  `docs/specs/adr-054-panel-contract.md: planned governed file path or glob
  already resolves and must move to governs: <path>` as soon as a path listed
  under the spec's `planned_governs.files` starts to exist. The list contains
  `src/scistudio/core/panels.py`, `src/scistudio/panels/**`,
  `src/scistudio/api/routes/panels.py`, and `frontend/src/panels/**`, so every
  wave-2 and wave-3 agent creating one of them will see this finding on its own
  branch. **Do not fix it. Do not edit `docs/specs/**`.** The manager migrates
  all four entries from `planned_governs` to `governs` once at integration,
  when they all resolve; migrating one at a time would only trade this finding
  for its mirror image, a governed path that does not yet exist. Report the
  finding in your output and treat `full_audit` as otherwise clean if this is
  its only error-severity entry.
- **D-015 - Where the built-in panels live.**
  `src/scistudio/panels/builtin/<panel_id>/` holding `panel.json` and
  `index.html` in the D-007 form. The nine displaying panels keep the ids their
  `PanelSpec`s already carry (`core.dataframe.basic`, `core.array.basic`,
  `core.series.basic`, `core.text.basic`, `core.artifact.basic`,
  `core.composite.basic`, `core.collection.basic`, `core.plot.basic`,
  `core.base.fallback`) and the two producing panels keep theirs
  (`core.interactive.data_router`, `core.interactive.pair_editor`). Their
  Python providers are unchanged (FR-033). `core.base.fallback` is the panel the
  backend names as the fallback under D-013, so it must be the one that renders
  from the least information.
- **D-016 - Three additions to the D-011 message contract, from the host that
  implements it.** The backend conforms to these; they are not open for
  reinterpretation.
  1. `init.restored_state` — the state hook's return half. D-011 gave
     `state_request` -> `state` outbound but no route back, and `init` is the
     only message a fresh mount receives, so FR-031's remount half rides there.
  2. `error.request_id`, nullable, on the host-to-panel `error` — it lets a
     failed or timed-out read terminate without the panel waiting out its own
     timeout, and keeps `read_result` at the two fields D-011 names.
  3. The panel descriptor the backend sends MUST carry `accepted_api_version`
     (the backend's `PANEL_API_VERSION`, per D-010) and `read_limits`. The host
     refuses to mount without either rather than inventing a bound or a
     version, so a descriptor missing them is a backend defect, not a host
     fallback.
- **Sentrux is unavailable in this environment.** No `sentrux` on PATH, no
  Python package; only `.sentrux/rules.toml` is present. Recorded once here for
  every agent in this dispatch; state it in your report rather than rediscovering
  it.

---

## W2-core

Filled from `docs/ai-developer/templates/agent-dispatch-prompt-template.md`.
Dispatched after T-001 and T-005/T-006 were integrated into the track branch.

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-054 spec 1, the unified panel contract; you
  deliver its backend core — the shared contract in the core layer, the on-disk
  panel form, four-tier discovery, registration, and capability-aware
  resolution.
- Task kind: feature
- Persona: implementer
- Issue: #2229
- Umbrella PR: #2230 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-054-spec1-panel-contract
- Agent branch: feat/2229-panel-core-contract
- Agent worktree: .worktrees/w2-panel-core
- Gate record: created by the agent with `gate_record init`
- Checklist: docs/planning/adr-054-panel-contract-checklist.md

## Required Rules

AGENTS.md; docs/ai-developer/rules.md; specific_rules/agent-dispatch.md;
specific_rules/gated-workflow.md; personas/implementer.md;
docs/specs/adr-054-panel-contract.md tasks T-002, T-003, T-013, T-015, T-016
(FR-001 to FR-006, FR-016 to FR-020, FR-040, FR-041, FR-045 to FR-050, SC-012,
SC-014, SC-015, SC-016); docs/adr/ADR-054.md sections 3.3 and 9.2; and the
manager decisions D-001 to D-016 in this file, of which D-005, D-007, D-009,
D-010, D-014 and D-015 govern the work directly.

## What already landed on the branch point

T-001 is done: `src/scistudio/panels/`, `PanelSpec`, `PanelRegistry`,
`features` in place of the free-form `capabilities`, and four alias modules at
`src/scistudio/previewers/{__init__,models,data_access,helpers}.py` that are
imports and aliases only. T-005/T-006 are done: `frontend/src/panels/` holds
the sandboxed-frame host, the message contract, and the capability gate; the
agent must read `panelMessages.ts` and `panelDescriptor.ts` before designing
the backend descriptor, because the host refuses a descriptor without
`accepted_api_version` and `read_limits` (D-016). `PanelSpec.previewer_id`
keeps its name deliberately (D-004); `W3-api` renames it with the endpoints.

## Scope

Owns: `src/scistudio/core/panels.py` (create); `src/scistudio/panels/**` except
`builtin/**`; `core/dropins.py`; `core/entry_points.py`;
`blocks/base/interactive.py` and the block-registry discovery check FR-050
needs; `tests/panels/**` except `test_builtin_panels.py`;
`tests/architecture/test_layer_deps.py`; `tests/adr052_contract/**`; fixtures
under `tests/fixtures/**`.

Must not touch: `src/scistudio/panels/builtin/**` and
`tests/panels/test_builtin_panels.py` (a parallel agent owns them);
`src/scistudio/api/**` (read only); `frontend/**` (read only); `docs/specs/**`
and `docs/adr/**` (D-014); `docs/architecture/**`, `docs/user/**`,
`docs/package-development/**`; `src/scistudio/previewers/**`; `docs/planning/**`.

## Coordination

Not alone in the codebase: `W4-builtin` works in parallel on
`src/scistudio/panels/builtin/**` from the same branch point. Own branch, own
worktree, no `pip install -e .`, no PR, no merge; push the branch and the
manager integrates.

## TODO And Deferral Rule

`TODO(#NNN): <reason>` citing an issue, ADR, spec, or ticket. Known deferrals:
`TODO(#2212)` the plot panel's producing capability; `TODO(#2211)` interface
copy still says previewer.

## Work To Do

**T-002** — create `src/scistudio/core/panels.py` owning `PANEL_API_VERSION`,
`PanelCapability` (exactly two members, FR-006), `PanelManifest`, `PanelTier`
and the declaration-validation errors, per D-009; the placement is a layering
constraint, not taste (ADR-054 9.2). `blocks/base/interactive.py` imports
`PanelManifest` from core rather than defining its own. Collapse the two
`PANEL_API_VERSION` definitions T-001 deliberately left onto the core one —
FR-004 and SC-001 require exactly one in the tree.

**T-003** — implement the D-007 on-disk form; validate every required field at
discovery and refuse a declaration missing one with a diagnostic naming the
directory and the field (FR-003). Discover from four tiers with project over
user library over package over core shadowing (FR-018, FR-019); a collision
within one tier is a discovery error. Per D-005 and FR-020 the existing
`previewers/` drop-in directories and `.scistudio/previewers.json` keep
working; carry the project default-panel declaration over under the panel
naming (FR-046), decide the precedence when both exist, test it, and state the
decision. The core tier is a directory on disk (D-015) whose contents arrive
from a parallel agent; test core-tier discovery against an owned fixture.

**T-015** — add the `scistudio.panels` entry-point group resolving to panel
*directories*, with no Python object required to register a panel (FR-045),
keeping `scistudio.previewers` and `get_previewers()` discovered. The user
library and the project register by containing a directory (FR-046), taking
effect after a registry rebuild. A declaration may name a Python provider
(FR-047), resolved from its own tier, and a provider that fails to import is a
discovery diagnostic naming the panel rather than a mount-time load failure.
SC-014 wants a fixture package registering a panel with a directory and no
Python object, and a fixture project registering one by containing a directory.

**T-016** — every request states its required capability and candidates are
filtered before the ladder and the choice apply (FR-048); a producing panel
satisfies a displaying request (FR-006). Record the choice per type *and per
capability* (FR-049), migrating the existing `previewer-choices.json` shape and
stating what an existing file does on first read. A producing request with no
producing panel falls back to the displaying resolution mounted with no
outbound path. FR-050: a block-declared panel must declare producing, checked
at block discovery with a diagnostic naming the block (SC-016). The ladder and
the per-type choice are otherwise carried over without redesign (FR-016,
A-006).

**T-013** — extend the layer enumeration for `scistudio.core.panels` (FR-040);
update `tests/adr052_contract/expected_surface.json` and the stability markers
for every symbol added or moved, and state how each new symbol's tier and
`since` were derived (FR-041). T-001 carried the renamed symbols across at
`tier: provisional`, `since: 0.3.1`, unchanged.

## Required Tests And Checks

Create `tests/panels/test_panel_contract.py`,
`test_panel_capability_gate.py` (backend half), `test_panel_tiers.py`,
`test_panel_registration.py`, `test_panel_resolution.py`.

`pytest tests/panels tests/api tests/architecture tests/adr052_contract
tests/blocks`; `ruff check` and `ruff format --check`; `lint-imports` must stay
13 kept / 0 broken. Known environment failures, not the agent's: ~40
`tests/blocks/io/**` tests fail on a missing `openpyxl` in this machine's
ambient python. `gate_record init --task-kind feature --persona implementer
--base-ref track/adr-054-spec1-panel-contract` (mandatory: the branch is
stacked) then `gate_record check --mode local --base
track/adr-054-spec1-panel-contract`. Two known non-blockers in that check: the
D-014 `planned_governs` finding once `core/panels.py` exists, and
`core_change_guard`, which the manager handles at PR time. No `finalize`, no
PR. Sentrux is not installed in this environment.

Commit trailers: `Gate-Record`, `Task-Kind: feature`, `Issue: #2229`,
`Assisted-by`.

## Output Required

Changed and created paths; the exact `panel.json` schema validated field by
field and what a missing field's diagnostic says; the backend panel descriptor
field by field for checking against `panelDescriptor.ts`; the
`previewers.json` precedence decision and what an existing
`previewer-choices.json` does on first read; how each new symbol's ADR-052 tier
and `since` were derived; where the single `PANEL_API_VERSION` lives and proof
no second definition survives; tests and results with counts plus the openpyxl
baseline; the pushed commit sha; any blocker.

## Stop Conditions

An out-of-scope file is needed, in particular if T-016 seems to need an API
route change; a D-00x decision conflicts with the spec; carrying the on-disk
choice file across the per-capability shape would silently lose a person's
setting; the ADR-052 stability derivation is genuinely ambiguous; the task
conflicts with AGENTS.md, the ADR, the spec, or the gate record.
```

---

## W4-builtin

Filled from `docs/ai-developer/templates/agent-dispatch-prompt-template.md`.
Dispatched in parallel with `W2-core` from the same branch point; the two
agents' write sets are disjoint by directory.

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-054 spec 1, the unified panel contract; you
  deliver its eleven built-in panels, rewritten as self-contained documents on
  disk.
- Task kind: feature
- Persona: implementer
- Issue: #2229
- Umbrella PR: #2230 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-054-spec1-panel-contract
- Agent branch: feat/2229-builtin-panels
- Agent worktree: .worktrees/w4-builtin-panels
- Gate record: created by the agent with `gate_record init`
- Checklist: docs/planning/adr-054-panel-contract-checklist.md

## Required Rules

AGENTS.md; docs/ai-developer/rules.md; specific_rules/agent-dispatch.md;
specific_rules/gated-workflow.md; personas/implementer.md;
docs/specs/adr-054-panel-contract.md task T-009 (FR-002, FR-033, FR-034,
FR-035, FR-037, SC-003, and assumption A-004, which explains why the
duplication between these documents is accepted and must not be resolved by a
shared runtime import); docs/adr/ADR-054.md section 3.2; and the manager
decisions D-001 to D-016 in this file, of which D-007, D-010, D-011, D-015 and
D-016 define the work exactly.

## Scope

Owns, and creates: `src/scistudio/panels/builtin/**` — eleven panel
directories, each `panel.json` + `index.html`;
`tests/panels/test_builtin_panels.py` and only that test file; the packaging
declaration needed so these non-Python files ship in the wheel (CI has a
`Wheel Release Smoke` job, so a missing declaration is a real CI failure),
touching only the lines that add these files.

Must not touch: anything else under `src/scistudio/panels/**`, and
`fallbacks.py` in particular — **the Python providers are unchanged (FR-033)**;
`src/scistudio/core/**`, `api/**`, `blocks/**`; `frontend/**` (read only, and
reading it is required); any other test file; `docs/specs/**`, `docs/adr/**`,
`docs/architecture/**`, `docs/user/**`; `docs/planning/**`.

## Coordination

Not alone in the codebase: `W2-core` works in parallel from the same branch
point on everything under `src/scistudio/panels/` except `builtin/`. Own
branch, own worktree, no `pip install -e .`, no PR, no merge; push the branch
and the manager integrates.

## TODO And Deferral Rule

`TODO(#NNN): <reason>` citing an issue, ADR, spec, or ticket. Known deferral:
`TODO(#2212)` the plot panel gains the producing capability later; this one
declares `displaying` only.

## The eleven panels

Nine displaying panels, whose ids, target types, providers and features are
already in `src/scistudio/panels/fallbacks.py::core_panel_specs()`:
`core.dataframe.basic` (DataFrame, `dataframe_panel`),
`core.array.basic` (Array, `array_panel`),
`core.series.basic` (Series, `series_panel`),
`core.text.basic` (Text, `text_panel`),
`core.artifact.basic` (Artifact, `artifact_panel`),
`core.composite.basic` (CompositeData, `composite_panel`),
`core.collection.basic` (Collection sentinel, `supports_collection=True`,
`collection_panel`), `core.plot.basic` (PlotArtifact, `plot_panel`), and
`core.base.fallback` (DataObject sentinel, `priority=-100`,
`base_fallback_panel`).

Two producing panels declared on their block classes:
`core.interactive.data_router` (`blocks/process/builtins/data_router.py`) and
`core.interactive.pair_editor` (`blocks/process/builtins/pair_editor.py`).

## Work To Do

1. Read the host first: `frontend/src/panels/panelMessages.ts` is the contract
   the documents speak, `panelFrame.ts` shows the handshake, the token and the
   bounded wait, `PanelHost.tsx` shows what `init` carries. Every message is
   `{ scistudio_panel: 1, token, type, payload }`; the panel answers `init`
   with `ready` carrying its declared api version, within the bounded wait or
   it is a load failure.
2. Read what each panel must render: `coreViewers.tsx`, `TableViewer.tsx`,
   `PlotViewer.tsx`, and for the producing pair
   `App.parts/InteractiveModals.parts/`. Port pagination, sorting, the array
   slice controls and colormap, the plot format menu, composite slot
   navigation, and collection sampling. Do not delete or edit those React
   components; a later agent retires them.
3. Write each panel as `src/scistudio/panels/builtin/<panel_id>/` holding
   `panel.json` in the D-007 schema exactly and `index.html`. The ids are fixed
   by D-015. Nine declare `capability: "displaying"`, two declare
   `"producing"`. Each names its `provider` where one exists.
4. Strictly self-contained (FR-034, A-004): markup, styles and script in one
   document; no `<script src>`, no `<link rel=stylesheet>`, no shared runtime
   import, no CDN. Several render similar tables and that duplication is
   accepted — the property being protected is that a document can be opened
   directly in a browser to see whether it works, and that a person forking one
   gets everything in the file they opened. Report what was knowingly
   duplicated.
5. A displaying panel emits nothing. The two producing panels emit code through
   the single outbound path and must not interpret it. **Do not implement any
   AST or statement whitelist** — ADR-054 3.6 puts that where an emission is
   queued, which is the explore session and out of scope (FR-012).
6. The plot panel moves across unchanged in kind (A-005): displaying only,
   Python side untouched, `TODO(#2212)` for the rest.
7. Bulk data comes from the asset route (D-008) via the `asset_base_url` the
   host hands the panel in `init`, not through the message channel; windowed
   reads go through `read` / `read_result`.
8. Write `tests/panels/test_builtin_panels.py`: each of the eleven has a
   directory; each `panel.json` validates against D-007 with the right id,
   target types and capability; self-containment asserted mechanically (no
   `<script src=`, no `<link rel="stylesheet"`, no external `import(`); the two
   interactive panels declare producing and the nine others displaying; the
   packaging declaration actually includes the files. Do not import the panel
   registry — a parallel agent is changing it — test the files on disk.
9. Prove one document actually works: drive at least the plot and dataframe
   panels from a stub `init` and confirm they answer `ready` and render. If
   that cannot be done without out-of-scope files, say so precisely rather than
   claiming it.

Order: the plot panel first (a single image and a format control is the
simplest complete exercise of the path, per the spec's own risk note), then the
dataframe panel, then the rest.

## Required Tests And Checks

`pytest tests/panels`; `ruff check` and `ruff format --check`; the frontend
suite only if a frontend test was added. `gate_record init --task-kind feature
--persona implementer --base-ref track/adr-054-spec1-panel-contract`
(mandatory: the branch is stacked) then `gate_record check --mode local --base
track/adr-054-spec1-panel-contract`. Known non-blockers: ~40
`tests/blocks/io/**` failures from a missing `openpyxl`; and per D-014, no
`planned_governs` finding is fixed by editing `docs/specs/**`. No `finalize`,
no PR. Sentrux is not installed in this environment.

Commit trailers: `Gate-Record`, `Task-Kind: feature`, `Issue: #2229`,
`Assisted-by`.

## Output Required

Every created path; one `panel.json` in full for checking against D-007; one
line per panel saying what it renders and which component's behaviour it
replaces; the knowingly duplicated code and why factoring it out would break
A-004; what was actually proved about a document working and by what harness,
distinguishing a static check from a document that answered `ready` and
rendered; the packaging change and how shipping was verified; tests and results
with counts; the pushed commit sha; any blocker.

## Stop Conditions

An out-of-scope file is needed; a provider's payload cannot be rendered without
importing something shared, i.e. FR-034 and the payload are in genuine
conflict; the message contract cannot express something a panel needs; the
documents cannot be made to ship in the wheel without a packaging change larger
than adding the files; the task conflicts with AGENTS.md, the ADR, the spec, or
the gate record.
```
