---
title: "Learning Center Agent Dispatch Checklist"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 53
language_source: en
---

# Learning Center Agent Dispatch Checklist

> Mandatory tracking file. Every agent edits only rows it owns.
> Drift is a protocol violation.
> Source template:
> `docs/ai-developer/templates/agent-dispatch-checklist-template.md`

## 1. Change Summary

- Owner request: implement the ADR-053 Learning Center infrastructure spec in
  full, plus the first core tutorial level in full, and deliver one combined PR.
- Task kind: `feature`
- Manager persona: `manager`
- Issue: `#2056`, `#2057`, `#2058`
- Gate record: `.workflow/records/2056-learning-center.json`
- Branch/worktree plan: manager on `feat/learning-center` at
  `.worktrees/learning-center`; each dispatched agent gets
  `feat/lc-<slice>` at `.worktrees/lc-<slice>`, branched from
  `feat/learning-center`, merged back by the manager.
- Protected branch: `main`
- Umbrella branch: `feat/learning-center`
- Umbrella PR: `#2060`
- Umbrella PR title: `[DO NOT MERGE] Learning Center dispatch umbrella`
- Final PR target: `main`
- Dispatch prompt templates:
  - Work: `docs/ai-developer/templates/agent-dispatch-prompt-template.md`
  - Audit with context:
    `docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`
  - Audit no context:
    `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`

## 2. Scope

- In scope:
  - `src/scistudio/core/entry_points.py` (new shared entry-point contract)
  - `src/scistudio/blocks/registry/_scan.py`,
    `src/scistudio/core/types/registry.py`,
    `src/scistudio/previewers/registry.py` (moved onto the shared contract)
  - `src/scistudio/core/dropins.py` (tutorial drop-in tier + scoped library)
  - `src/scistudio/tutorials/**` (new package: manifest, discovery, driver,
    conditions, actions, session, projects, progress, schema, core tutorials)
  - `src/scistudio/api/routes/tutorials.py` (replaced entirely)
  - `src/scistudio/api/routes/projects.py`,
    `src/scistudio/api/runtime/_projects.py` (tutorial marker + listing filter)
  - `src/scistudio/api/routes/ai_pty/**` (scripted replay byte source)
  - `frontend/src/**` (Learning Center surface; deletion of the old tutorial)
  - `tests/**`, `frontend/src/**/__tests__/**`
  - `docs/specs/adr-053-learning-center.md`, `docs/adr/ADR-053.md`,
    `docs/planning/learning-center-checklist.md`, `CHANGELOG.md`
  - `pyproject.toml` (entry-point group docs + the ADR-052 §7A citation)
- Out of scope:
  - `docs/architecture/ARCHITECTURE.md` — see §2.1 below.
  - The block palette tips strip (#1997); spec `scope.out`.
  - Core tutorials 2–6; only tutorial 1 is authored here (#2058).
  - A user-level previewer tier (#2017); spec assumption A-006.
  - Adding `data/processed/` to the project scaffold; owner-held.
  - Any package-shipped tutorial content.
- Protected paths:
  - `src/scistudio/core/**`, `src/scistudio/blocks/**` — protected-core per
    ADR-042 Addendum 6 §7.8. Requires `admin-approved:core-change` applied by
    the owner on the PR. Recorded as a requested label in the gate ledger;
    CI verifies provenance.
- Deferred work:
  - `TODO(#2059)`: `docs/architecture/ARCHITECTURE.md` §12.4 correction
    (spec FR-034). See §2.1.

### 2.1 The one deliberate omission: ARCHITECTURE.md §12.4

Spec FR-034 requires `docs/architecture/ARCHITECTURE.md` §12.4 to drop the
removed `scistudio.runners` row and add `scistudio.tutorials`. That file is
owner-controlled: `architecture_doc_guard` (#2054, merged as PR #2055) hard-fails
in CI any change to it without `admin-approved:architecture-doc` applied by the
owner or an administrator approval review. The owner's standing instruction is
that the document is never edited without their specific prior approval, and
that approval was not available for this session.

Every other half of FR-034 is delivered: the live entry-point group set is
documented in exactly one place, `src/scistudio/core/entry_points.py`, and
`pyproject.toml`'s false "ADR-052 §7A" citation is corrected (FR-035). The
two-row table edit is tracked at #2059 and is a single commit once the owner
approves it.

## 3. Conventions

- `[ ]` not started
- `[~]` in progress
- `[x]` done
- `[!]` blocked
- Every completed row MUST include an artifact:
  PR link, commit, test command, report path, or gate-record entry.
- Chat messages are not checklist evidence.
- Agents edit only their own rows.
- Scope changes require gate-record amendment before work continues.

## 4. Manager Preflight

- [x] Dedicated manager branch and worktree created. -> `feat/learning-center`
      at `.worktrees/learning-center`
- [x] Existing issue linked, or new issue created only if none exists. ->
      searched open issues; none tracked this work; opened #2056, #2057, #2058
- [x] Gate record started. -> `.workflow/records/2056-learning-center.json`
- [x] Scope include/exclude recorded in the gate record. -> `init --include`
- [x] Umbrella branch created. -> `feat/learning-center`
- [x] Umbrella PR opened. -> #2060
- [x] Umbrella PR title includes `[DO NOT MERGE]`.
- [x] Protected branch and umbrella PR number recorded in this checklist. ->
      §1
- [x] No `pip install -e .` environment pollution found. -> gate parity venv
      only; agents instructed `PYTHONPATH=$PWD/src`
- [x] Dispatch checklist copied from the template and committed.
- [x] Dispatch prompts created from the correct prompt template and linked
      below. -> §6, prompts stored under `.workflow/local/dispatch/` (ignored)
      and reproduced in §7 track scopes
- [x] Sentrux baseline recorded, or N/A reason recorded. -> Sentrux MCP is not
      connected in this session; `gate_record check` records Sentrux guard
      evidence through the shared evaluator.

## 5. Local Gate Hook Bypass Evidence

- Authorized bypass label: `admin-approved:core-change` (requested, not a
  broad bypass)
- Owner authorization source: not obtained in-session — the owner was asleep.
  Recorded as a pre-PR requested label; CI verifies provenance and will fail
  until the owner applies it.
- Reason: the entry-point symmetry work and the tutorial drop-in tier change
  `src/scistudio/core/**` and `src/scistudio/blocks/**`, which the spec
  requires (FR-025 … FR-031).

| Hook | Command | Bypass label | Status | Evidence |
|---|---|---|---|---|
| Pre-commit | `python -m scistudio.qa.governance.gate_record check --mode pre-commit` | `N/A` | `[ ]` | pending |
| Commit message | `python -m scistudio.qa.governance.gate_record check --mode commit-msg` | `N/A` | `[ ]` | pending |
| Pre-push | `python -m scistudio.qa.governance.gate_record check --mode pre-push` | `N/A` | `[ ]` | pending |
| Pre-PR reconcile | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `admin-approved:core-change` | `[ ]` | pending |

### 5.1 Docs Impact Check

- Wrapper/hook/gate-record/receipt/CI/runtime behavior changed: `no`
- AI docs checked:
  `docs/ai-developer/rules.md`,
  `docs/ai-developer/specific_rules/gated-workflow.md`,
  `docs/ai-developer/specific_rules/agent-dispatch.md`,
  `docs/ai-developer/templates/*dispatch*.md`
- Updated docs or N/A rationale: N/A — this change adds a product feature and
  a shared discovery contract. It changes no wrapper, hook, gate-record, CI, or
  AI-runtime behaviour, so no AI developer workflow doc is affected.

## 6. Dispatch Matrix

| Agent | Persona | Audit mode | Prompt | Task | Branch | Worktree | Write set | Out of scope | Issue/PR | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| `A1` | `implementer` | `N/A` | §7.1 | Entry-point symmetry | `feat/lc-entry-points` | `.worktrees/lc-entry-points` | `src/scistudio/core/entry_points.py`, the three registries, `pyproject.toml`, `tests/packages/**`, `tests/api/test_registry_*` | `src/scistudio/tutorials/**`, `frontend/**`, `docs/architecture/**` | #2056 | `[ ]` |
| `A2` | `implementer` | `N/A` | §7.2 | Manifest, conditions, actions | `feat/lc-manifest` | `.worktrees/lc-manifest` | `src/scistudio/tutorials/{__init__,manifest,conditions,actions}.py`, `src/scistudio/tutorials/schema/**`, `tests/tutorials/**` | everything else | #2057 | `[x]` |
| `A3` | `implementer` | `N/A` | §7.3 | Tutorial projects, scoped library, progress | `feat/lc-projects` | `.worktrees/lc-projects` | `src/scistudio/tutorials/{projects,progress}.py`, `src/scistudio/core/dropins.py`, `src/scistudio/api/runtime/_projects.py`, `src/scistudio/api/routes/projects.py`, `tests/tutorials/**`, `tests/api/test_tutorial_project_visibility.py` | `src/scistudio/tutorials/{manifest,conditions,actions,discovery,driver,session}.py` | #2057 | `[ ]` |
| `A4` | `implementer` | `N/A` | §7.4 | Frontend Learning Center | `feat/lc-frontend` | `.worktrees/lc-frontend` | `frontend/src/**` | `src/**`, `tests/**`, `docs/**` | #2057 | `[x]` |
| `A5` | `implementer` | `N/A` | §7.5 | Discovery, driver, session | `feat/lc-runtime` | `.worktrees/lc-runtime` | `src/scistudio/tutorials/{discovery,driver,session}.py`, `tests/tutorials/**` | wave-1 files | #2057 | `[ ]` |
| `A6` | `implementer` | `N/A` | §7.6 | API routes + replay | `feat/lc-routes` | `.worktrees/lc-routes` | `src/scistudio/api/routes/tutorials.py`, `src/scistudio/api/routes/ai_pty/**`, `src/scistudio/api/app.py`, `tests/api/**` | `src/scistudio/tutorials/**` except read | #2057 | `[ ]` |
| `A7` | `implementer` | `N/A` | §7.7 | Core tutorial 1 + fixture tutorials | `feat/lc-tutorial-1` | `.worktrees/lc-tutorial-1` | `src/scistudio/tutorials/core/**`, `tests/tutorials/fixtures/**` | runtime modules | #2058 | `[ ]` |
| `A8` | `adr_author` | `N/A` | §7.8 | ADR-053 revisions, spec sync, CHANGELOG | `feat/lc-docs` | `.worktrees/lc-docs` | `docs/adr/ADR-053.md`, `docs/specs/adr-053-learning-center.md`, `CHANGELOG.md` | `docs/architecture/ARCHITECTURE.md`, all code | #2057 | `[ ]` |
| `A9` | `audit_reviewer` | `no-context` | §7.9 | Independent conformance audit | `feat/lc-audit` | `.worktrees/lc-audit` | `docs/audit/**` | everything else (read-only) | #2057 | `[ ]` |

## 6.1 Shared contracts — the interfaces agents build against

These are manager-owned. An agent that needs one changed stops and reports;
it does not change it unilaterally.

### 6.1.1 `src/scistudio/core/entry_points.py` (A1 owns, A5 consumes)

Location decision: the spec §4.2 left this open between a new
`scistudio.packages`, a single `scistudio/entry_points.py`, and a home under
`core/`, and explicitly permitted the choice at implementation time. It goes
under `core/` because `core/dropins.py` is already the settled precedent for
"one answer shared by the block, type, and previewer registries", because
import-linter forbids `scistudio.core` from importing `blocks`/`engine`/`api`/
`ai`/`workflow` and the helper needs none of them, and because "package"
already denotes an installed plugin distribution in this repository, whose
lifecycle code lives in `desktop/package_*.py`.

```python
LIVE_ENTRY_POINT_GROUPS: tuple[str, ...]   # the four live groups, FR-034

@dataclass(frozen=True)
class EntryPointDiagnostic:
    group: str
    entry_point: str          # "" when the failure is enumeration itself
    stage: str                # "enumerate" | "load" | "invoke" | "register"
    message: str

def enumerate_group(group, *, diagnostics=None) -> tuple[EntryPoint, ...]
def load_entry_point(ep, group, *, diagnostics=None) -> object | None
def resolve_payload(loaded, *, group, entry_point, allow_bare_class, diagnostics=None)
def plugin_import_roots() -> tuple[Path, ...]
def prepared_plugin_import_roots() -> AbstractContextManager[None]
def resolve_entry_point_directory(ep, *, diagnostics=None) -> Path | None
```

`resolve_entry_point_directory` is FR-029a: it maps an entry-point *value* to a
directory using distribution metadata only (`ep.dist.files` /
`Distribution.locate_file`). It MUST NOT call `EntryPoint.load()`,
`importlib.import_module`, or `importlib.util.find_spec`, because `find_spec`
imports parent packages and FR-018 forbids importing a package module while
listing the catalogue.

`allow_bare_class` is `True` only for `scistudio.blocks` (FR-029), and the
reason is recorded in this module rather than in each registry.

### 6.1.2 `src/scistudio/tutorials/` module boundaries

| Module | Owns | Must not import |
|---|---|---|
| `manifest.py` | manifest model, schema load, validation, tier rules | `discovery`, `session`, `driver`, `scistudio.api` |
| `conditions.py` | vocabulary, `Condition` model, parser, evaluator, event map | `session`, `driver`, `scistudio.api` |
| `actions.py` | action model, parser, execution, containment | `session`, `driver`, `scistudio.api` |
| `discovery.py` | four sources, catalogue entries, requirement checks | `session`, `scistudio.api` |
| `driver.py` | driver protocol, `ManifestDriver`, package driver loading | `session`, `scistudio.api` |
| `session.py` | lifecycle, persistence, event subscription, one-at-a-time | `scistudio.api` |
| `projects.py` | tutorial project creation, marking, deletion, scoped library | `session`, `driver` |
| `progress.py` | progress storage, grouping, milestone unlock | `session`, `driver` |

No module under `src/scistudio/tutorials/` may import `scistudio.api`. The API
route layer injects what the runtime needs. This keeps the package testable
without a FastAPI app and keeps `api -> tutorials` a one-way edge.

### 6.1.3 Product-state port (A2 declares, A3/A5/A6 satisfy)

`conditions.py` reads product truth through one injected protocol rather than
importing the API runtime:

```python
class ProductState(Protocol):
    project_dir: Path | None
    tutorial_library_dir: Path | None
    def workflow(self) -> WorkflowDefinition | None: ...
    def block_type_names(self) -> frozenset[str]: ...
    def data_type_names(self) -> frozenset[str]: ...
    def previewer_type_ids(self) -> frozenset[str]: ...
    def plot_bindings(self) -> tuple[tuple[str, str, str], ...]:  # (plot_id, node_id, output_port)
    def run_records(self) -> tuple[RunSummary, ...]: ...
    def port_has_output(self, node_id: str, port: str) -> bool: ...
    def git_branches(self) -> frozenset[str]: ...
    def git_current_branch(self) -> str | None: ...
    def library_entries(self) -> frozenset[tuple[str, str]]:  # (kind, name)
    def interactions_completed(self) -> frozenset[str]: ...
    def pages_reached(self) -> frozenset[str]: ...
    def ui_events(self) -> frozenset[str]: ...
```

Evaluation is side-effect free (FR-055). Every method is a pure read.

### 6.1.4 Completion-condition vocabulary (FR-047)

Exactly these sixteen terms, plus the `all` and `any` combinators (FR-048).
Negation is deliberately absent.

`node_exists`, `edge_exists`, `config_equals`, `run_succeeded`,
`port_has_output`, `block_registered`, `type_registered`,
`previewer_registered`, `plot_exists`, `file_exists`, `git_branch_exists`,
`git_current_branch`, `library_contains`, `interaction_completed`,
`page_reached`, `ui_event`.

### 6.1.5 Event map (FR-050) — import the constants, never the literals

| Constant | Module | Terms re-evaluated |
|---|---|---|
| `WORKFLOW_CHANGED` | `scistudio.engine.events` | `node_exists`, `edge_exists`, `config_equals` |
| `WORKFLOW_COMPLETED`, `BLOCK_DONE`, `BLOCK_ERROR` | `scistudio.engine.events` | `run_succeeded`, `port_has_output` |
| `BLOCKS_RELOADED` | `scistudio.api.ws` | `block_registered`, `type_registered`, `previewer_registered`, `library_contains` |
| `GIT_HEAD_CHANGED` | `scistudio.engine.events` | `git_branch_exists`, `git_current_branch` |
| `FILE_CHANGED_EVENT_TYPE` | `scistudio.api.file_contracts` | `file_exists` |
| `INTERACTIVE_COMPLETE` | `scistudio.engine.events` | `interaction_completed` |

`BLOCKS_RELOADED` and `FILE_CHANGED_EVENT_TYPE` live outside `engine/events.py`
because that module is frozen by ADR-035/036 hard-scope rules
(`src/scistudio/api/ws.py:44-48`). `session.py` may not import
`scistudio.api`, so the API layer passes the two string constants in when it
wires the subscription; the session declares the mapping in terms of names it
receives, not literals it invents.

### 6.1.6 HTTP contract (A6 implements, A4 consumes)

All under `/api/tutorials`. `source_kind` is `core|package|user|project`;
`source_id` is `""` for core, the distribution name for a package, `user` or
`project` for the other two.

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/catalogue` | — | `CatalogueResponse` |
| GET | `/sessions/active` | — | `SessionResponse \| null` |
| POST | `/sessions` | `{source_kind, source_id, tutorial_id, restart}` | `SessionResponse`; 409 when another session is active |
| POST | `/sessions/active/evaluate` | — | `SessionResponse` (FR-053) |
| POST | `/sessions/active/ui-event` | `{name}` | `SessionResponse` (FR-052) |
| POST | `/sessions/active/continue` | — | `SessionResponse` (FR-012 reading steps) |
| POST | `/sessions/active/leave` | — | 204 (FR-090, session preserved) |
| GET | `/progress` | — | `ProgressResponse` |
| GET | `/data/clear-preview` | — | `{directories: [str]}` (FR-088) |
| POST | `/data/clear` | `{confirm: true}` | `{deleted_directories: [str]}` |
| GET | `/unlock` | — | `{work_import_offer_pending: bool}` (FR-079) |
| POST | `/unlock/dismiss` | — | 204 |
| GET | `/{source_kind}/{source_id}/{tutorial_id}/cover` | — | image bytes |
| GET | `/{source_kind}/{source_id}/{tutorial_id}/pages/{name}` | — | page content (FR-006 `pages/`) |

```
CatalogueResponse = {
  groups: [ { source_kind, source_id, label, completed, total,
              tutorials: [ CatalogueEntry ] } ],
  active: SessionResponse | null,
  diagnostics: [str],
}
CatalogueEntry = { source_kind, source_id, id, title, summary, cover_url|null,
                   order, state, unavailable_reason|null,
                   project_directory|null }
SessionResponse = { source_kind, source_id, tutorial_id, title,
                    project_id|null, project_path|null,
                    step: { id, index, total, say|null, highlight|null,
                            route_to|null, awaiting_continue } | null,
                    satisfied_step_ids: [str],
                    status: "active"|"complete"|"error", error|null,
                    replay: { surface, tab_id } | null }
ProgressResponse = { groups: [ { source_kind, source_id, label,
                                 completed, total } ] }
```

`state` is `not_started | in_progress | complete | unavailable`. No aggregate
count across groups is reported (FR-076).

### 6.1.7 Replay surface (FR-061a)

The closed surface set has exactly one member, named `ai_chat_terminal`, and
it is declared once in `actions.py` as `REPLAY_SURFACES`. Delivery reuses the
existing PTY path (`src/scistudio/api/routes/ai_pty/`): a scripted byte source
is inserted into `_state._active_ptys` under a tab id with the
`_engine_prespawned` marker before the frontend connects, so the tab strip, the
terminal component, and the tab lifecycle stay the product's real ones and only
the byte source changes. It exposes the same small interface the WebSocket
route depends on — `read(timeout)`, `is_alive()`, `write(data)`,
`resize(cols, rows)`, `kill_tree()` — and `write` discards input, because a
replay must not accept user input back into the scripted session (FR-061a).

## 7. Tracks

### 7.1 Track A1 — Entry-point symmetry (#2056)

- Owner: `A1`
- In scope: FR-025 … FR-033, FR-035. New `src/scistudio/core/entry_points.py`;
  `_scan.py`, `core/types/registry.py`, `previewers/registry.py` moved onto it;
  `pyproject.toml:118` citation corrected; parity test.
- Out of scope: `docs/architecture/ARCHITECTURE.md` (FR-034's table edit,
  see §2.1); `src/scistudio/tutorials/**`; frontend.
- Required docs: module docstring in `core/entry_points.py` recording the live
  group set (FR-034's "exactly one place"), the `scistudio.blocks` bare-class
  compatibility affordance (FR-029), the `scistudio.tutorials` metadata-only
  exemption and its reason (FR-029a), and the previewer companion fallback as
  history rather than pattern (FR-032, recorded where it lives).
- Required tests: `tests/packages/test_entry_point_symmetry.py` (FR-033) plus
  extensions to `tests/api/test_registry_provisioning_parity.py` and
  `tests/api/test_registry_reload_symmetry.py` (FR-031).

#### 7.1.2 Dispatch

- [x] Prompt file created or dispatch prompt recorded.
- [x] Correct prompt template selected.
- [x] Audit mode recorded when persona is `audit_reviewer`. -> N/A
- [x] Agent branch/worktree assigned.
- [x] Write set and out-of-scope paths included in prompt.
- [x] TODO rule included in prompt.
- [x] Required checks included in prompt.

#### 7.1.3 Implementation

- [ ] Shared helper -> `<artifact>`
- [ ] Three registries moved onto it -> `<artifact>`
- [ ] Parity test -> `<artifact>`
- [ ] `pyproject.toml` citation -> `<artifact>`

### 7.2 Track A2 — Manifest, conditions, actions (#2057)

- Owner: `A2`
- In scope: FR-005 … FR-015, FR-020, FR-020a, FR-045 … FR-061c.
- Out of scope: discovery, session, driver, projects, progress, routes,
  frontend.
- Required docs: `src/scistudio/tutorials/schema/tutorial.schema.json` is the
  published schema (FR-013).
- Required tests: `tests/tutorials/test_manifest_schema.py`,
  `test_conditions.py`, `test_actions.py`, `test_tier_asset_rules.py`,
  `test_replay.py`.

#### 7.2.2 Dispatch

- [x] Prompt recorded; template selected; branch/worktree assigned; write set,
      out-of-scope paths, TODO rule, and required checks included.

#### 7.2.3 Implementation

- [x] Manifest model + schema + validation -> `feat/lc-manifest` c7777b3c
- [x] Condition vocabulary + evaluator -> `feat/lc-manifest` c7777b3c
- [x] Actions + containment + replay segments -> `feat/lc-manifest` c7777b3c
- [x] Closed `ROUTE_TARGETS` / `HIGHLIGHT_TARGETS` / `UI_EVENT_NAMES` -> `feat/lc-manifest` 2d98a1b4
- [x] Tests -> `pytest tests/tutorials` 224 passed; ruff, mypy, lint-imports (13 kept), deferral scan at baseline

### 7.3 Track A3 — Tutorial projects, scoped library, progress (#2057)

- Owner: `A3`
- In scope: FR-062 … FR-081, and the `core/dropins.py` tutorial tier required
  by FR-016 and FR-031.
- Out of scope: manifest, conditions, actions, discovery, driver, session.
- Required tests: `tests/api/test_tutorial_project_visibility.py`,
  `tests/tutorials/test_scoped_library.py`, `tests/tutorials/test_progress.py`,
  plus the extensions to the two parity tests for the tutorial drop-in tier.

#### 7.3.2 Dispatch

- [x] Prompt recorded; template selected; branch/worktree assigned; write set,
      out-of-scope paths, TODO rule, and required checks included.

#### 7.3.3 Implementation

- [ ] Tutorial project creation, marker, listing filter -> `<artifact>`
- [ ] Scoped library -> `<artifact>`
- [ ] Progress + milestone unlock -> `<artifact>`

### 7.4 Track A4 — Frontend Learning Center (#2057)

- Owner: `A4`
- In scope: FR-001 (frontend half), FR-002, FR-082 … FR-090; the API client
  in §6.1.6; the `ui_event` reporter (FR-052) and the explicit evaluate request
  (FR-053).
- Out of scope: all of `src/**`, `tests/**` outside `frontend/`, `docs/**`.
- Required tests: `frontend/src/components/__tests__/LearningCenter.test.tsx`.

#### 7.4.2 Dispatch

- [x] Prompt recorded; template selected; branch/worktree assigned; write set,
      out-of-scope paths, TODO rule, and required checks included.

#### 7.4.3 Implementation

- [x] Old tutorial modules deleted with all their wiring -> `feat/lc-frontend` d5fcbd80 (8 files deleted; grep confirms no judging predicate and no `runFirstWorkflowTutorial*` localStorage key survives)
- [x] Learning Center + active step surface -> `feat/lc-frontend` d5fcbd80
- [x] Toolbar entry, dot, first-run landing -> `feat/lc-frontend` d5fcbd80
- [x] Tests -> `npm run check:ci`: lint 0 errors, format clean, `tsc --noEmit` exit 0, 1581/1581 tests, `vite build` ok
- [ ] `route_to` / `highlight` acted on rather than rendered as text -> follow-up, see drift log

### 7.5 Track A5 — Discovery, driver, session (#2057)

- Owner: `A5`
- In scope: FR-016 … FR-024, FR-029a (consumer side), FR-036 … FR-044.
- Out of scope: wave-1 files, routes, frontend.
- Required tests: `tests/tutorials/test_discovery_tiers.py`,
  `test_discovery_no_import.py`, `test_session_lifecycle.py`,
  `test_driver_parity.py`, `test_condition_events.py`.

#### 7.5.3 Implementation

- [ ] Four-source discovery -> `<artifact>`
- [ ] Driver interface + manifest driver + package driver loading -> `<artifact>`
- [ ] Session lifecycle, persistence, event subscription -> `<artifact>`

### 7.6 Track A6 — API routes and replay (#2057)

- Owner: `A6`
- In scope: FR-003 (route removal), the §6.1.6 contract, FR-061a's byte-source
  injection, and the event wiring that hands `session.py` the two non-engine
  event constants.
- Out of scope: `src/scistudio/tutorials/**` beyond reading it.
- Required tests: `tests/api/test_tutorial_routes.py`, replay delivery test.

#### 7.6.3 Implementation

- [ ] Routes -> `<artifact>`
- [ ] Replay byte source -> `<artifact>`
- [ ] Event subscription wiring -> `<artifact>`

### 7.7 Track A7 — Core tutorial 1 and test fixtures (#2058)

- Owner: `A7`
- In scope: `src/scistudio/tutorials/core/welcome-to-scistudio/` (manifest +
  assets), and the fixture tutorials the spec's §4.3 requires as test material
  — one exercising every vocabulary term and every action type, one declaring a
  driver, one malformed, one with unmet requirements.
- Out of scope: every runtime module.
- Required tests: the fixtures are consumed by A2's and A5's tests; A7 adds a
  test that the shipped core tutorial validates against the published schema
  and that every condition term it uses is in the vocabulary.

#### 7.7.3 Implementation

- [ ] Tutorial 1 manifest + assets -> `<artifact>`
- [ ] Fixture tutorials -> `<artifact>`

### 7.8 Track A8 — ADR-053 revisions and spec sync (#2057)

- Owner: `A8`
- In scope: FR-091 … FR-094 (ADR-053 §1.1, §2, §2.1, §2.2, §4.2, §8);
  syncing `docs/specs/adr-053-learning-center.md` frontmatter to the delivered
  file set; `CHANGELOG.md`.
- Out of scope: `docs/architecture/ARCHITECTURE.md`; all code.

#### 7.8.3 Implementation

- [ ] ADR-053 revisions -> `<artifact>`
- [ ] Spec frontmatter sync -> `<artifact>`
- [ ] CHANGELOG -> `<artifact>`

### 7.9 Track A9 — Independent audit (#2057)

- Owner: `A9`
- Audit mode: `no-context`
- In scope: read the repository's docs, code, and tests and report where the
  delivered Learning Center diverges from the spec it claims to implement.
- Out of scope: any fix. Report only.
- Report path: `docs/audit/2026-08-09-learning-center-conformance.md`

#### 7.9.4 Audit

- [ ] Audit agent assigned, or manager audit completed.
- [ ] Audit report file path assigned.
- [ ] Audit report committed.
- [ ] Audit report merged into final PR evidence path.
- [ ] Findings recorded.
- [ ] P1 findings fixed before integration.
- [ ] P2/P3 findings fixed or tracked with owner-approved rationale.

## 8. Verification Evidence

| Check | Command or tool | Status | Evidence |
|---|---|---|---|
| Gate ledger check (local) | `python -m scistudio.qa.governance.gate_record check --mode local --base origin/main --head HEAD` | `[ ]` | pending |
| Targeted tests | `pytest tests/tutorials tests/packages tests/api/test_tutorial_routes.py tests/api/test_tutorial_project_visibility.py` | `[ ]` | pending |
| Frontend tests | `npm --prefix frontend run test` | `[ ]` | pending |
| Gate ledger check (pre-PR) | `python -m scistudio.qa.governance.gate_record check --mode pre-pr --pr-body-file .workflow/local/pr-body.md` | `[ ]` | pending |
| Gate finalize (pre-PR) | `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#2056"` | `[ ]` | pending |
| Wrapper preflight | `python scripts/scistudio_pr_create.py --dry-run --title <title> --body <body>` | `[ ]` | pending |

## 8.1 Manager-owned integration tasks

Work that belongs to no single track because it depends on the merged file
layout. The manager does these after integrating, before the pre-PR check.

- [ ] **Wheel packaging.** `[tool.setuptools.package-data]` in `pyproject.toml`
      lists every non-Python file that ships. The new
      `src/scistudio/tutorials/schema/tutorial.schema.json` and the whole core
      tutorial tree (`tutorials/core/**`: `tutorial.yaml`, `assets/data/*.csv`,
      `assets/code/*.py`, covers) are not covered by any existing pattern, and
      `packages.find` will not pick up `assets/code/*.py` either because those
      directories are deliberately not importable packages. Without explicit
      entries a released wheel installs a Learning Center with no schema and no
      tutorials, and the `wheel-release-smoke` CI job would not notice — it
      inspects the SPA bundle only. Add the patterns and an assertion that the
      shipped core tutorial is present. Same class of gap as #2032.
- [ ] **ADR-053 §7 verification table.** Rows at `docs/adr/ADR-053.md:536-538`
      attribute Learning Center verification to #1998, which is closed. A8
      re-points them at #2056/#2057/#2058.
- [ ] **Cross-track merge conflicts.** A1 and A3 both extend
      `tests/api/test_registry_provisioning_parity.py` and
      `tests/api/test_registry_reload_symmetry.py` — A1 for the fourth
      entry-point group, A3 for the tutorial drop-in tier. Resolve
      intentionally; both additions must survive.

## 9. Drift Log

Append only.

| Date | Agent | Drift | Action | Follow-up |
|---|---|---|---|---|
| 2026-08-09 | manager | Spec §4.2 named `src/scistudio/packages/entry_points.py`; that package does not exist and the name collides with installed-distribution semantics. | Chose `src/scistudio/core/entry_points.py`, which §4.2 explicitly permits. Spec frontmatter synced by A8. | N/A |
| 2026-08-09 | manager | Spec FR-034 requires an `ARCHITECTURE.md` §12.4 edit; that file is owner-gated by `architecture_doc_guard` and the owner was unavailable. | Delivered the rest of FR-034 and all of FR-035; left the table edit out. | #2059 |
| 2026-08-09 | manager | Spec §4.3 says entry-point symmetry "should ship on its own"; the owner directed one combined PR. | Followed the owner. Kept it a separate issue (#2056) and separate commits so it stays independently revertable. | N/A |

## 10. Final Readiness

- [ ] All dispatched agents have final outputs.
- [ ] Manager reviewed every changed file.
- [ ] Gate record includes issue, scope, plan, docs, tests, checks, Sentrux
      evidence when needed, commit, and PR evidence.
- [ ] PR closes every issue fixed by the dispatch.
- [ ] CI passed.
- [ ] Checklist final state matches PR and gate record.
