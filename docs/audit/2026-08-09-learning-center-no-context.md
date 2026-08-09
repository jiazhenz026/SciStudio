---
title: "ADR-053 Learning Center — independent no-context audit"
audit_date: 2026-08-09
auditor: audit_reviewer (no-context)
branch: feat/lc-audit
governing_documents:
  - docs/specs/adr-053-learning-center.md
  - docs/adr/ADR-053.md
recommendation: block
---

# ADR-053 Learning Center — Independent No-Context Audit

## 1. Scope And Method

This audit was performed without access to the owner request, the GitHub issue,
any manager checklist, dispatch prompts, PR descriptions, commit messages, or
`.workflow/records/**`. No `git log`, `git show`, `gh issue view`, `gh pr view`,
or `gh pr diff` was run. Every conclusion below rests on the governing spec, the
repository's code and tests, and tool output produced during this audit.

The method was spec-first: FR-001 … FR-094 and SC-001 … SC-014 were taken from
`docs/specs/adr-053-learning-center.md` and each was checked against the
delivered repository, with particular attention to requirements that fail
silently when unmet.

## 2. Tool Output

Every command was run in `/Users/jiazhenz/SciStudio/.worktrees/lc-audit`.

| Check | Command | Result |
|---|---|---|
| Backend tests | `pytest tests/tutorials tests/packages tests/api -q --no-cov -n0` | **exit 0** — 1456 tests: 1448 passed, 8 skipped, 0 failed |
| Type check | `mypy src/scistudio/ --ignore-missing-imports` | **3 errors** (see F-15) |
| Lint | `ruff check src tests` | **exit 0** — All checks passed |
| Import contracts | `lint-imports` | **exit 0** — contracts kept |
| Repo audit | `python -m scistudio.qa.audit.full_audit --repo-root . --format json` | **exit 1, status `fail`** (see F-05) |
| Deferral scan | `python scripts/deferral_scan.py` | **exit 0** |
| Frontend | `npm --prefix frontend run check:ci` | **exit 0** — 146 files, 1607 tests passed |
| Wheel packaging | `python -m build --wheel` | **exit 0** — tutorial schema and core tutorial assets present |
| Sentrux | — | **N/A** — no `sentrux` CLI on PATH and no Sentrux MCP server available in this session |

The 8 skipped backend tests are platform-specific (Windows path semantics,
Windows dialogs) plus one requiring an R interpreter; none relate to this spec.

## 3. Findings

Ordered by severity. Each finding is classified as a **spec-conformance gap**, a
**correctness bug**, a **test that does not test what it claims**, or
**documentation drift**.

---

### F-01 — FR-078 is not implemented: uninstalling a package never deletes its progress group

**Class:** spec-conformance gap, compounded by a test that does not test what it claims.

FR-078 (spec:948-949): *"Uninstalling a package MUST delete that package's
progress group. Reinstalling MUST start it from zero."*

`ProgressStore.remove_package_group` exists at
`src/scistudio/tutorials/progress.py:305-311`, delegating to `remove_group`
at `:285-303`. It has **zero production callers**. The uninstall path is
`DELETE /api/packages/{package_name}` at
`src/scistudio/api/routes/packages.py:240-251` → `package_manager.delete_package`
(`src/scistudio/desktop/package_manager.py:482-510`, removes install dir and
backup only) → `_after_package_change` (`src/scistudio/api/routes/packages.py:108-118`,
calls `refresh_all_registries()` and `_refresh_active_project_package_docs()`).
No `ProgressStore` reference appears anywhere in `packages.py`,
`package_manager.py`, or `package_installer.py`.

Observable consequence: completions persist in `~/.scistudio/tutorial-progress.json`
after uninstall. They are invisible while the package is absent, because
`build_catalogue` iterates discovered sources
(`src/scistudio/tutorials/discovery.py:783`) — but on **reinstall the records
return**, so the group does not start from zero, which is exactly what FR-078's
second sentence forbids.

The requirement appears covered because
`tests/tutorials/test_progress.py:186-219` calls `store.remove_package_group(...)`
**directly**. It tests the method, never the uninstall path. The suite passes
while the requirement is unimplemented — this is the highest-value class of
finding named in the audit brief.

Acceptance scenario US-3.3 (spec:310-312) is therefore not met.

---

### F-02 — FR-079 is not delivered: the one product behaviour progress drives never fires

**Class:** spec-conformance gap.

FR-079 (spec:951-954): *"Exactly one product behaviour MUST be driven by
progress: completing a named core tutorial MUST present the work-import offer,
once."*

Two independent reasons it cannot happen:

1. **No frontend consumer.** `getTutorialUnlock`
   (`frontend/src/lib/api/learningCenter.ts:217`) and `dismissTutorialUnlock`
   (`:219`) are defined, and the backend routes exist
   (`src/scistudio/api/routes/tutorials.py:1130`, `:1142`). A whole-tree grep for
   `unlock` outside `__tests__` returns only those client definitions and one
   comment (`frontend/src/store/learningCenterSlice.ts:72`). **No component,
   hook, or store action calls either function.** `useLearningCenter.ts` has four
   effects; none is the unlock.
2. **No milestone is configured.** `DEFAULT_WORK_IMPORT_MILESTONE: str | None = None`
   at `src/scistudio/tutorials/progress.py:79`, with a correctly-formed
   `TODO(#2057)` at `:70-76` deferring the choice to the scenarios spec per
   assumption A-005 (spec:1386-1388). `work_import_offer_pending()` therefore
   always returns `False` (`:331-336`).

The *mechanism* FR-079 requires — that the named tutorial be configuration and
not a constant — **is** satisfied: `progress.py:124-150` resolves env var
`SCISTUDIO_WORK_IMPORT_MILESTONE` (`:68`), then `work_import_milestone` in
`~/.scistudio/learning-center.json` (`:64`), then the default. Both override
paths are tested (`tests/tutorials/test_progress.py:227-241`).

Item 2 is a tracked deferral and defensible. Item 1 is not deferred anywhere:
the client functions are dead code and User Story 5 (spec:353-374) and its three
acceptance scenarios have no implementation. No test asserts an offer is
presented, front or back.

---

### F-03 — SC-012 is false: a user- or project-tier tutorial can plant an executable file the product executes

**Class:** spec-conformance gap (correctness-relevant).

SC-012 (spec:1356-1358): *"A user-level or project-level tutorial cannot place an
executable file anywhere the product imports or executes it."*

`EXECUTED_PROJECT_DIRS` at `src/scistudio/tutorials/actions.py:99` is
`frozenset({"blocks", "types", "previewers", "plots"})` — exactly FR-020a's
stated minimum, and `destination_head`
(`src/scistudio/tutorials/actions.py:182-185`) matches on the first path segment
only.

`.claude/` is not in that set, and the product both provisions and executes it:

- `src/scistudio/agent_provisioning/hooks.py:61` — `_HOOKS_DIR_REL = ".claude/hooks"`;
  `:62` — `_SETTINGS_REL = ".claude/settings.json"`; `:534-535` create them.
- `src/scistudio/api/runtime/_projects.py:296-300` calls
  `install_project_agent_assets(project_path, force=False)` on **every**
  `create_project`, and tutorial projects go through that same method
  (`src/scistudio/tutorials/projects.py:10-12`).
- `src/scistudio/api/routes/ai_pty/validation.py:1-4` — the frontend-supplied
  `project_dir` "becomes the spawned subprocess `cwd=`"; `engine.py:300`, `:357`.

So opening AI Chat inside a tutorial project spawns an agent whose hook scripts
are read from that project's `.claude/`.

Verified by executing the delivered validator rather than by reading it
(`load_manifest(..., source_kind=TutorialSourceKind.PROJECT)`):

```
.claude/hooks/hook_protect_data_dir.py        -> ACCEPTED
.claude/settings.json                         -> ACCEPTED
.codex/config.toml                            -> ACCEPTED
blocks/evil.py                                -> REJECTED
workflows/w.yaml                              -> ACCEPTED
data/raw/ok.csv                               -> ACCEPTED
```

FR-020a (spec:580-591) says the restricted set is *"at minimum"* those four, so
the implementation is conformant to FR-020a's letter. SC-012 states the outcome
absolutely, and that outcome does not hold.

Note this is *not* a shortcoming of the tier tests, which are genuinely
thorough (`tests/tutorials/test_tier_asset_rules.py`, parametrized across both
graded-out tiers × all three asset dirs × all four executed dirs, plus the
copy-tree and bootstrap routes, with positive controls at `:62-72`, `:169-174`).
The set they check is pinned to FR-020a's minimum at `:35-37`. The gap is in the
set, not the enforcement.

---

### F-04 — FR-034 is not satisfied: ARCHITECTURE.md §12.4 still advertises a removed entry-point group

**Class:** documentation drift / spec-conformance gap.

FR-034 (spec:705-710): *"The set of live entry-point groups MUST be documented in
exactly one place, and `docs/architecture/ARCHITECTURE.md` §12.4 MUST be
corrected."*

`docs/architecture/ARCHITECTURE.md:2158-2163` still reads:

```
| `scistudio.blocks`     | Block classes, plus optional `PackageInfo` … |
| `scistudio.types`      | Additional `DataObject` subclasses …         |
| `scistudio.previewers` | Type-specific previewers via get_previewers().|
| `scistudio.runners`    | CodeBlock runner backends …                  |
```

The removed `scistudio.runners` is still listed and `scistudio.tutorials` is
absent — so the set is documented in **two** places
(`src/scistudio/core/entry_points.py:133-138` being the intended single one),
and the second is wrong in both directions. This is the precise harm FR-034
names: "a package author reading the architecture document today is told to use
a group that does not exist."

The deferral is tracked and correctly formed, at
`src/scistudio/core/entry_points.py:127-132`, citing `TODO(#2059)` and an
owner-approval gate on `architecture_doc_guard`. That makes it a legitimate
deferral of a governance-restricted file, but FR-034 as written is unmet and
SC-003's documentation half is not delivered.

---

### F-05 — the repository's own audit tool fails, with six errors, five naming ADR-053

**Class:** documentation drift (CI-blocking).

`python -m scistudio.qa.audit.full_audit --repo-root . --format json` returns
`status: fail` (exit 1). Two children fail: `doc_drift` and `closure`.

Six **error**-severity findings (the rest are `info`-level planned-governs
notes for ADR-049/ADR-052):

```
[error] doc-drift.phantom-file  docs/adr/ADR-053.md: frontend/src/store/tutorialSlice.ts
[error] doc-drift.phantom-file  docs/adr/ADR-053.md: frontend/src/components/TutorialPanel.tsx
[error] doc-drift.phantom-file  docs/adr/ADR-053.md: frontend/src/App.parts/useRunFirstWorkflowTutorial.ts
[error] doc-drift.phantom-file  docs/adr/ADR-053.md: frontend/src/tutorials/runFirstWorkflow/content.ts
[error] doc-drift.phantom-file  docs/adr/ADR-053.md: frontend/src/lib/api/tutorials.ts
[error] doc-drift.planned-file-is-resolved docs/adr/ADR-049.md: tests/packages/**
```

Cause 1: `docs/adr/ADR-053.md:32, 33, 38, 39, 40` (`governs.files`) still claim
the five frontend modules FR-001 required deleted. The deletion is real and correct — the
frontmatter was not updated to match. `closure` reports the same five as
`closure.unresolved-file-claim`.

Cause 2: `docs/adr/ADR-049.md:79` declares `tests/packages/**` under
`planned_governs`. That glob now resolves, because this work created
`tests/packages/` (`__init__.py`, `test_entry_point_symmetry.py` — the only two
files present, and `tests/packages/test_entry_point_symmetry.py` is listed in
this spec's own `tests:` block at spec:102). Adding the directory tripped
ADR-049's planned-governs contract.

Both are small frontmatter fixes, but the tool is a CI gate and currently fails.

Note the same five phantom paths also appear in
`docs/specs/adr-053-learning-center.md:79-87`; the tool does not flag them there,
and that spec carries `status: Draft` (spec:4) while `docs/adr/ADR-053.md:4`
carries `status: Proposed`.

---

### F-06 — FR-047 `library_contains` can never become true through the product's own write path

**Class:** correctness bug / spec-conformance gap.

FR-070 (spec:917-919) requires a tutorial project to scan a tutorial-scoped
library *in place of* the user-wide one, and FR-047 (spec:777) defines
`library_contains` as "the tutorial-scoped library holds a named block, type, or
previewer".

The **read** path is correct and well tested: `library_root_for_project`
(`src/scistudio/core/dropins.py:320-334`) returns `tutorial_library_dir()` for a
project under the tutorial parent and `user_library_dir()` otherwise;
`_tier_dirs` (`:347-361`) returns exactly two entries, so the user library is
swapped out, not appended. `tests/tutorials/test_scoped_library.py:72` asserts
precisely the "in place of" property.

The **write** path never consults it. `src/scistudio/api/routes/user_library.py:82`
imports `user_blocks_dir, user_types_dir` and binds them at `:92-95`:

```python
_TARGET_ROOTS = {
    "blocks": user_blocks_dir,
    "types": user_types_dir,
}
```

`:220-230` calls `root_factory()` with no project context. The MCP tool does the
same (`src/scistudio/ai/agent/mcp/tools_library.py:67, 260`). A repo-wide grep
confirms `library_root_for_project` appears only in `core/dropins.py` and one
docstring in `tutorials/projects.py:30` — never in a write path.

Consequences:

1. A save-to-library performed *inside a tutorial* lands in `~/.scistudio/`,
   which the tutorial project does not scan. `library_contains`
   (`src/scistudio/api/routes/tutorials.py:545-581`, reading `tutorial_library_dir`)
   therefore **cannot become true** via the product's own save action. A step
   using it would wait forever.
2. It produces exactly the outcome the design says it exists to prevent —
   `src/scistudio/core/dropins.py:288-291`: the teaching type is deposited into
   the user's real library and is seen by every real project afterwards.
3. It survives clearing, since clearing only removes
   `~/SciStudio Tutorials/.library` (F-14).

`tests/tutorials/test_scoped_library.py` never exercises `PUT /api/user-library/file`
or the MCP tool, which is why the suite is silent on this.

---

### F-07 — FR-047 `page_reached` can never become true: no surface ever requests a page

**Class:** spec-conformance gap.

FR-047 (spec:779) defines `page_reached` as "a reading step reached a given
page", and FR-006 (spec:503-507) reserves `assets/pages/` "for reading content".

The chain exists but is not connected to any product surface:

- Evaluator: `src/scistudio/tutorials/conditions.py:545` reads
  `state.pages_reached()`; protocol member at `:408`.
- Backing store: `_RecordedSignals.pages` at
  `src/scistudio/api/routes/tutorials.py:291`; exposed at `:588-589`.
- Only writer: `record_page` at `:296-297`, called from exactly one place —
  `:1187`, inside `_page()`.
- `_page()` is reached only by `GET /api/tutorials/{...}/pages/{name}`
  (`:1229`) and its core variant (`:1235`).

**Nothing calls those routes.** `frontend/src/lib/api/learningCenter.ts` exposes
`cover_url` (`:44`, rendered at `LearningCenter.tsx:93-94`) but no page URL, and
no Learning Center component fetches `/pages/`.

More fundamentally, the step view cannot carry a page reference at all:
`StepView` (`src/scistudio/tutorials/driver.py:137-146`) is
`id, index, total, say, highlight, route_to, awaiting_continue` — matching
FR-011 and enforced by `StepView.of` (`:148-167`), which FR-041 requires. So a
manifest has no way to tell the frontend to display a page.

A tutorial step declaring `done_when: {page_reached: {page: X}}` validates
cleanly and then hangs forever. This is the "step a reader would wait on
forever" case the brief asked about. Reading steps themselves *do* work, via
FR-012's `awaiting_continue` path — but that is a different mechanism, and
`page_reached` is unreachable.

---

### F-08 — FR-028 diagnostics reach a product surface for one group out of four

**Class:** spec-conformance gap.

FR-028 (spec:649-653): *"A load or registration failure MUST be recorded as a
diagnostic **the product can surface**, for every group. Logging alone is not
sufficient."*

All four stores exist:

| Group | Store | Accessor |
|---|---|---|
| blocks | `src/scistudio/blocks/registry/__init__.py:360` | `:617-629` |
| types | `src/scistudio/core/types/registry.py:314` | `:317-329` |
| previewers | `src/scistudio/previewers/registry.py:62` | `:104-106` |
| tutorials | `src/scistudio/tutorials/discovery.py:427` | `:429-432` |

Only `scistudio.tutorials` reaches a user: `CatalogueResponse.diagnostics`
(`src/scistudio/api/routes/tutorials.py:224`, populated `:886`) rendered at
`frontend/src/components/LearningCenter.tsx:354-365`. A repo-wide grep for
consumers of the other three returns no API route, WS event, MCP tool, or
frontend reader — the only readers are tests
(`tests/packages/test_entry_point_symmetry.py:550, 556, 563`).

The docstring at `src/scistudio/blocks/registry/__init__.py:620-624` states the
user-facing rationale FR-028 gives. The recording exists; the surfacing does
not, for three of the four groups the requirement names.

---

### F-09 — FR-033 / SC-003: the parity test does not assert parity as broadly as it claims

**Class:** test that does not test what it claims.

SC-003 (spec:1327-1330) requires **one** parity test covering all four groups
under enumeration failure, single-entry-point load failure, and refresh, such
that a fifth group cannot be added divergently without failing.

What genuinely holds: a fifth group cannot be added silently. Three real guards
fire — `tests/packages/test_entry_point_symmetry.py:525-540`
(`_GROUPS_WITHOUT_A_REGISTRY` asserted empty),
`tests/api/test_registry_reload_symmetry.py:433-450` (both-directions
exhaustiveness on the refresh map), and `:296-302` / `:493-501` (bare-class and
metadata-only sets pinned to one member each). The per-group section at
`tests/packages/test_entry_point_symmetry.py:589-650` does what FR-033 asks.

What does not hold:

1. **The helper-level tests are group-agnostic and therefore near-vacuous.**
   `enumerate_group` and `resolve_payload` contain no per-group branching —
   `group` is an opaque diagnostic label and `allow_bare_class` is supplied *by
   the test* (`:241, 319, 345, 374`). So `:167`, `:228`, and `:266` run an
   identical assertion four times. They pin the helper; they cannot detect a
   divergent registry.
2. **The previewer registry's real failure path is not parity-tested.**
   `resolve_payload` does not appear in `src/scistudio/previewers/registry.py` at
   all; the registry calls `load_entry_point` (`:155`) then
   `_register_from_factory` (`:158`), which has its own `try/except` and appends
   free-form strings (`:271-290`) rather than `EntryPointDiagnostic` objects. The
   parametrized case for `group="scistudio.previewers"` at `:228` therefore
   exercises code that registry never executes.
3. **Tutorials are excluded from every load-failure parametrization**
   (`:204, 228, 305, 336, 353` all filter out `METADATA_ONLY_GROUPS`). The
   tutorial analogue at `:476-490` asserts a diagnostic and `None` for one
   unresolvable entry point but **never asserts the remaining entry points still
   resolve** — which is FR-027's actual claim. That assertion exists for three of
   four groups.
4. **`_scan_registry` falls through unsafely.** `:559-563` returns
   `PreviewerRegistry().diagnostics` for any unrecognised `kind`, so
   `test_a_clean_scan_leaves_no_diagnostics` (`:641-650`) would pass **vacuously**
   for a fifth group.
5. Refresh parity lives in a second file
   (`tests/api/test_registry_reload_symmetry.py:500-520`, over three groups), so
   SC-003's "one parity test" is split, and tutorial refresh is proved by
   statelessness (`:453-488`) rather than by a parity assertion.

Separately, the FR-030 import-root test hardcodes its group list
(`tests/api/test_registry_provisioning_parity.py:434`) rather than deriving it
from `LIVE_ENTRY_POINT_GROUPS`, so a fifth group would silently not be covered
there.

---

### F-10 — FR-025: the previewer registry still owns its own invoke-stage error handling and diagnostic shape

**Class:** spec-conformance gap.

FR-025 (spec:637-640): each registry "keeps its own registration logic; none
keeps its own enumeration, error handling, or diagnostic reporting."

Enumeration is genuinely centralised — `grep -rn "entry_points(" src/` returns
exactly one live call site, `src/scistudio/core/entry_points.py:249`, and all
four scans route through `enumerate_group`
(`blocks/registry/_scan.py:372`, `core/types/registry.py:639`,
`previewers/registry.py:153`, `tutorials/discovery.py:541`).

But `resolve_payload` is imported only by blocks (`_scan.py:401`) and types
(`registry.py:646`). The previewer registry hands the loaded object straight to
`_register_from_factory` (`previewers/registry.py:155-158`), which keeps its own
`try/except`, its own shape check, and its own free-form diagnostic strings
(`:271-290`) carrying no group or stage. The error-handling and
diagnostic-reporting halves of FR-025 are unmet for that group.

---

### F-11 — FR-027: the type registry contains only `ValueError` at the registration stage

**Class:** correctness bug.

FR-027 (spec:646-647) requires a load failure be contained to that entry point
for **every** group.

`src/scistudio/core/types/registry.py:685-686`:

```python
try: self.register_class(...)
except ValueError:
```

Any other exception raised by `register_class` escapes the loop, escapes
`_scan_entrypoint_types`, and never reaches the diagnostic publish at `:701` —
so one malformed package type can both abort the remaining entry points and
suppress the diagnostics for the whole scan. Blocks contains everything
(`src/scistudio/blocks/registry/_scan.py:487`, `except Exception as exc:`) and
previewers contains broadly (`previewers/registry.py:275`). This is a genuine
surviving per-group asymmetry at the registration stage, and F-09's parity test
does not reach it.

---

### F-12 — FR-086: the unfinished-work dot is suppressed at launch for the users it targets

**Class:** spec-conformance gap, pinned by a passing test.

FR-086 (spec:980-983): the dot appears "when the core group is not fully
complete **and** the user has dismissed the first-run landing."

The predicate is exactly right
(`frontend/src/store/learningCenterSlice.ts:122-128`), reads only the core group
(`:73`, so FR-080 holds), and there is no permanent-dismissal affordance
(`frontend/src/components/Toolbar.tsx:230` has only `onClick=openLearningCenter`;
nothing tutorial-shaped is persisted, `frontend/src/store/index.ts:100`).

The gap is the "dismissed" flag's lifetime. `learningCenterFirstRunDismissed` is
set in exactly one place — `closeLearningCenter`
(`learningCenterSlice.ts:210-215`) — and is session-scoped by design
(`frontend/src/store/types.ts:118-124`). A **returning** user with recorded
progress never sees the first-run landing
(`frontend/src/App.parts/useLearningCenter.ts:62` bails on
`hasRecordedTutorialProgress`), so the flag is `false` at every launch and the
dot **does not show** until that user manually opens and closes the panel in that
session. That is precisely the population FR-086 exists for: a user with
unfinished core tutorials returning to the product.

The behaviour is locked in by a passing test
(`frontend/src/components/__tests__/LearningCenter.test.tsx:405-413`).

---

### F-13 — FR-072 is vacuous: no shipped tutorial teaches save-to-library

**Class:** spec-conformance gap (untriggered obligation).

FR-072 (spec:923-926) requires a step teaching save-to-library to state that the
same action in the user's own project writes to their real library.

`src/scistudio/tutorials/core/welcome-to-scistudio/tutorial.yaml` is the only
tutorial shipped under `src/scistudio/tutorials/core/`. It has 13 steps and a
case-insensitive grep for `library` returns **zero hits**; its `add-save` step
uses the `save_data` block, not save-to-library. There is no `library_contains`
condition anywhere in shipped content.

The obligation is therefore untriggered and untested. Read together with F-06,
if such a step were added today the action it teaches would write to the real
user library.

---

### F-14 — SC-009 residual: clearing deletes by directory listing, not by the FR-064 marker

**Class:** correctness bug (bounded and disclosed).

SC-009 (spec:1347-1348) requires clearing to leave user projects untouched.
FR-064 (spec:906) requires a marker distinguishing a tutorial project, and it
exists and works (`src/scistudio/api/runtime/models.py:50-52`, plus a second copy
in `project.yaml` at `src/scistudio/api/runtime/_projects.py:254-265`).

The delete preview does not use it. `src/scistudio/tutorials/projects.py:398-402`:

```python
parent = tutorial_parent_dir()
projects = sorted(child for child in parent.iterdir() if child.is_dir() and child != library)
```

The only guard is containment (`_guarded_remove`, `:344-360`, which refuses
anything not under `tutorial_parent_dir()` and refuses the parent itself). A
user project created inside `~/SciStudio Tutorials/` is deleted, marker or no
marker.

Mitigating: the choice is documented at `:394-396`, and the confirmation names
every directory (`src/scistudio/api/routes/tutorials.py:1074-1082`, rendered as
individual monospace list items at
`frontend/src/components/LearningCenter.tsx:388-400`), satisfying FR-088. But
`tests/api/test_tutorial_project_visibility.py:303-320` covers only a user
project **outside** the parent, so the case is untested. Given the marker exists,
using it here would cost nothing.

---

### F-15 — mypy reports three errors

**Class:** correctness (low), outside the audited surface.

```
src/scistudio/workflow/serializer.py:129: error: Returning Any from function declared to return "str"  [no-any-return]
src/scistudio/plot/scaffold.py:302:      error: Returning Any from function declared to return "str"  [no-any-return]
src/scistudio/api/runtime/_runs.py:172:  error: Returning Any from function declared to return "str"  [no-any-return]
```

None of the three files appears in this spec's `governs.files` (spec:54-91), so
these are very likely pre-existing rather than introduced here — a claim I could
not confirm without reading commit history, which this audit is barred from.
Recorded because the command was required and did not pass.

---

### F-16 — assorted requirements whose tests do not assert them

**Class:** test that does not test what it claims. None of these indicates a
defect; each means the requirement is unguarded against regression.

- **SC-011** — `tests/api/test_tutorial_project_visibility.py:328-337` asserts
  only that `"/api/work-import/sessions"` is in `client.app.routes`. Route-table
  membership is a static fact independent of progress and cannot fail from a
  progress gate. The toolbar entry FR-081 actually names is not touched. (The
  code is correct: `frontend/src/components/Toolbar.tsx:262-281` renders the
  entry unconditionally, `disabled` only on `!currentProject`.)
- **FR-082** — `LearningCenter.test.tsx:385-393` asserts the button exists and is
  enabled, with no catalogue in the store, so it cannot distinguish permanence
  from an empty catalogue.
- **FR-083** — no test anywhere. (Code is correct and backend-derived:
  `useLearningCenter.ts:57-65`, no localStorage.)
- **FR-089** — nothing renders `ActiveStep`. (Code is correct: `ActiveStep.tsx:41-45`
  is a `<section>` in document flow with no `fixed`/`absolute`, mounted at
  `App.tsx:466`; the highlight ring is `pointer-events-none`,
  `StepHighlight.tsx:91-98`.)
- **FR-090** — no test renders the leave button or exercises
  `leaveActiveTutorialSession` outside mock stubs.
- **FR-065** — `test_tutorial_project_visibility.py:169-178` checks one route
  rather than the three surfaces FR-065 names. This is *sufficient in fact*,
  because only one listing route exists and all three UI surfaces derive from it
  (`api.listProjects()` → `useWorkflowSync.ts:78-79` → `projectSlice.ts:17` →
  `WelcomeScreen.tsx:65`, `ProjectsDropdown.tsx:61`, `RecentProjectsList.tsx:78`),
  but the test does not establish that chain.
- **FR-065 operability half** — `:181-209` covers GET, PUT, file-read,
  file-write, DELETE; not git, runs, workflows, `/tree`, or plots.
- **FR-069** — `:274-286` asserts the predicate but never drives
  `TutorialRuntime.active_session()`, so the invalidate-and-reoffer behaviour at
  `src/scistudio/tutorials/session.py:783-792` is unasserted there.

## 4. Requirements Verified Satisfied

Recorded because they are the requirements most likely to fail silently, and
because a reader should know they were checked rather than assumed.

**FR-018 / SC-002 — listing imports no package module. Satisfied, and the proof
is not vacuous.** `tests/tutorials/test_discovery_no_import.py` installs a
`sys.meta_path` tripwire that raises on any import of the guarded package
(`:46-57`), stubs `EntryPoint.load()` to raise (`:85-87`), and — critically —
asserts the listing was **complete**: title, summary, cover, order, and
`is_startable` are all read back (`:180-184`). This defeats the two vacuity
routes: a discovery pass that skipped the package would also import nothing, and
the broad `except Exception` in `resolve_entry_point_directory`
(`src/scistudio/core/entry_points.py:421`) would otherwise swallow the tripwire's
`AssertionError`. Both are caught by the completeness assertions plus
`tripwire.attempts == []` (`:186`) and `_GUARDED not in sys.modules` (`:188-189`).
Resolution itself is metadata-only — `dist.locate_file` and `dist.files`
(`core/entry_points.py:437-459`) — with no `find_spec`, `import_module`, or
`__import__`, and the docstring at `:388-394` correctly notes that `find_spec`
would import parent packages and is no safer.

**FR-051 / SC-006 — no polling loop.** No `asyncio.sleep`, `time.sleep`,
`while True`, timer, or scheduled task exists in `src/scistudio/tutorials/**` or
`src/scistudio/api/routes/tutorials.py` (the only matches are the words
"polling"/"scheduler" in prose). No `setInterval`/`setTimeout` in any Learning
Center frontend module. Re-evaluation is bound to the FR-050 event constants
(`src/scistudio/tutorials/conditions.py:572-574`), an explicit request, or step
entry.

**FR-020a — implemented to its stated minimum and thoroughly enforced.**
`validate_tier_rules` (`src/scistudio/tutorials/manifest.py:707-748`) covers the
`driver` field, `replay` actions, and write/copy destination heads;
`validate_tier_assets` (`:751-777`) covers carried assets under
`assets/{code,panels,replay}/`; `_reject_executed_landing` (`:780-799`) closes
the copy-a-tree-to-the-project-root route. Each rejection names the tier, the
field, and the restriction. See F-03 for the set's scope.

**FR-055 — side-effect free**, tested at `tests/tutorials/test_conditions.py:330-357`,
including `assert state.reads` so the test cannot pass by evaluating nothing.

**FR-040 / FR-041 — driver parity and step-view containment.** `StepView.of`
(`src/scistudio/tutorials/driver.py:148-167`) reconstructs a plain `StepView`
from exactly `STEP_VIEW_FIELDS`, so a richer object or a subclass is reduced at
the boundary. Asserted at `tests/tutorials/test_driver_parity.py:268-302`
(`type(view.step) is StepView`, `set(vars(...))` equality) and `:222-254`
(identity-free response equality across both driver kinds).

**FR-035 — the corrected citation resolves.** `pyproject.toml:122-128` replaces
"ADR-052 §7A" with `docs/specs/adr-052-public-api-surface.md` §7A. Verified both
halves: `docs/adr/ADR-052.md` contains no "7A" and its sections stop at §10;
`docs/specs/adr-052-public-api-surface.md:825` is `## 7A`, and the owner's
2026-06-27 ruling to delete `runner_registry.py` and `runners/*` is at `:1566`.
Minor imprecision: that ruling sits in §18 Decision Log, not inside §7A itself.

**FR-061a — closed replay surface set.** `REPLAY_SURFACES` is a single
declaration with exactly one member (`src/scistudio/tutorials/actions.py:84`),
and the schema deliberately does not restate it (`:87-89`).

**FR-065 / SC-008 hiding half.** Exactly one listing route exists
(`src/scistudio/api/routes/projects.py:48-71`, filtered at `:70`); `desktop/`
never reads `known_projects`; no WS payload or MCP tool returns a project list.

**FR-076 — no aggregate across groups** in any response model
(`src/scistudio/api/routes/tutorials.py:208-240`), the store
(`src/scistudio/tutorials/progress.py:99-111, 261-281`), the catalogue builder
(`src/scistudio/tutorials/discovery.py:763-796`), or the frontend.

**Packaging — tutorial material ships in the wheel.** A real
`python -m build --wheel` produced `scistudio-0.3.3a0-py3-none-any.whl`
containing `scistudio/tutorials/schema/tutorial.schema.json` and all five
`scistudio/tutorials/core/welcome-to-scistudio/**` files. The `package-data`
patterns at `pyproject.toml:166-167` are correct, and the rationale recorded at
`:158-165` is accurate: neither path is reachable by `packages.find`. No
packaging gap.

## 5. Recommendation

**Block.**

Five items are load-bearing:

1. **F-01** — FR-078 has no implementation; only a method and tests for that
   method. Reinstall does not start from zero.
2. **F-02** — FR-079's offer, the single product behaviour this whole spec says
   progress exists to drive, has no frontend consumer. User Story 5 is
   undelivered and not deferred.
3. **F-03** — SC-012 is falsifiable in one command; `.claude/hooks/*.py` is
   accepted for the tiers the grading exists to constrain, and the product
   executes it.
4. **F-06 and F-07** — two of FR-047's sixteen vocabulary terms
   (`library_contains`, `page_reached`) cannot become true against the delivered
   product. Steps using them validate cleanly and then hang.
5. **F-05** — the repository's own `full_audit` gate fails with six errors, five
   of them naming ADR-053's own frontmatter.

F-05 and F-14 are small, mechanical fixes. F-03 is a one-line set change plus a
test row. F-06 is a one-call fix in the write path. F-01 is one call in
`_after_package_change`. F-02 and F-07 are genuine missing surfaces and are the
largest remaining work. F-04 is correctly deferred to #2059 behind an
owner-approval gate on `ARCHITECTURE.md` and should be confirmed with the owner
rather than treated as an oversight.

The engineering under audit is, on the whole, unusually careful: the no-import
proof, the tier-grading enforcement, the step-view reduction, and the
side-effect-free evaluator are all implemented and tested to a standard that
resists exactly the vacuity this audit went looking for. The findings above are
concentrated in the seams — where a mechanism was built and then not connected to
the surface that would exercise it.
