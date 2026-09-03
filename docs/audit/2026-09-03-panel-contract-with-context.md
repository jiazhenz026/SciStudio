---
title: "Audit — ADR-054 spec 1, the panel contract (with-context)"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 48
  - 51
  - 54
related_specs:
  - adr-054-panel-contract
language_source: en
---

# Audit — ADR-054 spec 1, the panel contract (with-context)

Audit mode: **with-context** (`W5-audit-wc`, `audit_reviewer` persona).
Subject: `track/adr-054-spec1-panel-contract` @ `448c64c42`, the candidate
behind umbrella PR #2230 `[DO NOT MERGE]`, closing #2229.
Audit branch: `audit/2229-panel-with-context`.
Gate ledger: `.workflow/records/2229-audit-2229-panel-with-context.json`.

**Verdict: pass-with-fixes.** The engineering is unusually good. Every retired
module is gone, the one loader and the one version constant are real, the
capability gate is structural rather than a check, the sandbox is one
permission, the shim's removal condition is three inspectable clauses, and
every agent stayed inside its declared ledger scope. What this audit found is
not sloppiness; it is **three places where a task was marked done against
evidence that does not reach the requirement it claims**, and one deferral
pointing at a closed issue.

Two findings are P1. Neither is a defect in the panel mechanism itself:

- **A-1** — a person editing an unmigrated user- or project-tier previewer
  gets a save that reports success and is thrown away on the next registry
  rebuild. FR-028 exists to prevent exactly this experience.
- **A-2** — T-010's editing capability ships as an API with no consumer.
  FR-028's *"the host must report the failure explicitly and offer to revert"*
  is an obligation on the host, and no host chrome offers it; nothing in the
  frontend calls any of the four editing endpoints. The checklist marks T-010
  `[x]` on backend evidence alone.

Neither blocks review; both should land before the PR merges, and A-1 is a
three-line refusal.

---

## 1. What I checked, and how

| Check | Result |
|---|---|
| `pytest tests/panels tests/api tests/architecture tests/adr052_contract tests/tutorials tests/blocks tests/engine -q --no-cov -p no:randomly` | **40 failed, rest green.** All 40 are in `tests/blocks/io/**` and all 40 are `ModuleNotFoundError: No module named 'openpyxl'`. Verified `import openpyxl` fails in this machine's ambient python; discounted. **Zero failures outside `tests/blocks/io/`.** |
| `npm ci && npm test` | 2274 passed, 1 failed: `src/__tests__/eslint-config.test.ts` timed out at 5000 ms while my pytest run had the CPU. Re-run alone: **8 passed in 1.75 s**. Environmental. |
| `npm run typecheck` | pass (`tsc --noEmit`, exit 0) |
| `npm run lint` | pass — 42 warnings, 0 errors, all pre-existing `react-refresh/only-export-components` noise |
| `npm run build` | pass, built in 4.53 s |
| `ruff check src tests` | **All checks passed** |
| `ruff format --check src tests` | **899 files already formatted** |
| `lint-imports` | **13 contracts kept, 0 broken** — including the new `Panels must not depend on engine, blocks, workflow, ai, or api` |
| `scripts/audit/generate_facts.py --check` | pass — see the note below |
| `full_audit` | **status: pass.** 0 error findings, 8 warnings (all `vulture.dead-code`). D-014's expected finding is gone: all four `planned_governs` entries have been migrated to `governs`. |
| `gate_record check --mode local --base origin/main --head HEAD` | tier 1, 11 checks, one unsatisfied obligation: `guard.core_change_guard` (see F-7) |
| `gate_record check --mode local --base track/... --head HEAD` | tier **3**, 2 checks, *"recovery reconciliation passed"* (see F-8) |
| Sentrux | not installed in this environment; no binary on PATH, no package. N/A, as recorded for every agent in the prompt file. |

**A note on `docs/facts/generated.yaml`, for whoever runs the final gate.** The
file is gitignored, so a fresh worktree has none and `full_audit` fails on
`facts.generated-stale` until it is written. Less obviously, it must be written
by the **worktree's own venv interpreter**
(`.workflow/local/venv/Scripts/python`), not the ambient one: the gate runs
`full_audit` through that venv (`checks.py:540`), the two interpreters produce
different expected text, and regenerating with the ambient python leaves the
gate reporting staleness that `--force-checks` will not clear. Regenerating via
the venv turned my own `checks.full_audit` obligation from unsatisfied to
`reconciliation passed` with no other change. This is ambient tooling friction
rather than a finding against this PR, but it will cost the manager an hour at
`finalize` if it is met cold.

---

## 2. T-001 to T-016 — delivered against the task's own verification column

Evidence below is what I opened, not what a checklist row claimed.

| Task | Verdict | Evidence I checked |
|---|---|---|
| T-001 rename, one commit, no behaviour change | **delivered, with one rule broken** | `abe12536a^2` is a single commit `782678f3b` touching 150 files. But it **adds** `tests/panels/test_previewers_alias.py` (61 lines, 6 new assertions). D-002 says *"No test may be added or deleted in the rename commit"*; SC-011 says *"no test modified in that commit"*. See F-4. |
| T-002 contract into core | **delivered** | `src/scistudio/core/panels.py` (22.9 kB) owns `PANEL_API_VERSION`, `PanelCapability`, `PanelManifest`, `PanelTier`, the declaration errors. `blocks/base/interactive.py:61` imports from it. `lint-imports` keeps the new Panels contract. |
| T-003 on-disk form, four tiers | **delivered** | `tests/panels/test_panel_tiers.py` (14 tests), `test_panel_contract.py` (21). Shadowing order project > user > package > core is asserted. |
| T-004 merged asset route | **delivered** | `tests/panels/test_panel_asset_route.py`: 15 tests, `@parametrize("tier", list(PanelTier))` on the entry document, on every escape in `ESCAPES`, and on the suffix allowlist. Confinement is exercised against all four roots, not one. |
| T-005 frame host, message contract | **delivered** | `panelFrame.ts` + 27 tests; `PANEL_FRAME_SANDBOX = "allow-scripts"` at `panelFrame.ts:63`, one permission, matching FR-008 exactly. |
| T-006 capability gate | **delivered** | `panelCapability.ts` drops the emit consumer at construction for a displaying mount rather than checking on delivery. See SC-007. |
| T-007 one loader, retired modules deleted | **delivered** | `panelModuleLoader.ts`, `dynamicPreviewer.ts`, `previewerHostApi.ts`, `coreViewers.tsx`, `PlotViewer.tsx`, `TableViewer.tsx`, `DynamicPanel.tsx`, `previewerCatalogSlice.ts` all deleted in the diff. |
| T-008 backend names the fallback | **delivered** | `schemas.py:567` `fallback_panel_id`, `:570` `fallback_panel` as a full descriptor. `CoreFallbackRenderer` gone. |
| T-009 eleven built-in panels | **delivered** | 11 directories under `src/scistudio/panels/builtin/`, each exactly `panel.json` + `index.html`; ids match D-015; 9 displaying, 2 producing. 35 tests. |
| T-010 read, write, copy-on-write, revert | **PARTIAL — backend only** | `editing.py` and the routes are real and tested (22 tests). But of D-020's nine endpoints the frontend consumes five — assets, `GET /api/panels`, `POST /reload`, and the choice endpoints (`PanelPalette.tsx:9-14`, `lib/api/data.ts:73,183`) — and **none of the three editing ones**. `grep -rn "panels/.*source\|/override" frontend/src` returns nothing; `PanelErrorSurface.tsx` offers no revert. FR-028's *"offer to revert"* is a host obligation and is unimplemented. See A-2. |
| T-011 hot reload + state hook | **delivered** | `usePanelReload.ts`, `handleFileChanged.ts:172`. A-007 is not assumed — `panelReload.test.ts:71` drives a `file_changed` event with source `"agent"` and asserts the reload fires. |
| T-012 compatibility shim | **delivered** | `compat.py` wraps on the *backend* into a real panel directory, so no second frontend mount path exists. 19 python tests + 6 host-side tests in `panelCompat.test.tsx`. |
| T-013 layer enumeration, frozen inventory | **delivered, one clause of FR-041 unmet** | `tests/architecture/test_layer_deps.py:176,218,271` name the renamed subsystem; `expected_surface.json` gains `scistudio.core.panels`. But FR-041's second clause — *"the spec MUST state how the renamed symbols' stability markers are derived"* — is nowhere in the spec. See F-5. |
| T-014 the two addenda | **delivered** | `ADR-048-addendum1.md` §5, `ADR-051-addendum2.md`. |
| T-015 entry-point group, directory registration, provider | **delivered** | Fixture package declares `[project.entry-points."scistudio.panels"] fixture = "scistudio_blocks_fixture.panels"` — a directory, no Python object — and ships `fixture.image.viewer/{panel.json,index.html}`. 26 tests including the broken-provider-is-a-diagnostic case. |
| T-016 capability-aware resolution, per-capability choice | **delivered** | `test_panel_resolution.py`, 22 tests, both halves of SC-015 plus the per-capability choice layering. |

---

## 3. SC-001 to SC-016 — measured, not accepted

| SC | How I measured it | Result |
|---|---|---|
| SC-001 one version constant, one loader | `grep -rn "PANEL_API_VERSION\|API_VERSION"` over `src/`; `grep` for version literals over `frontend/src` | **pass.** One definition, `core/panels.py:49 PANEL_API_VERSION = "1"`; every other site imports it. No frontend file spells a version literal — the host reads `accepted_api_version` off the descriptor (`panelDescriptor.ts:83`). |
| SC-002 retired modules absent | `git diff --diff-filter=D` | **pass.** Both loaders and the retired host API module are deleted, not wrapped. |
| SC-003 eleven panels through the frame | directory listing + absence of compiled-in viewers | **pass.** 11 directories; `DataPreview.parts/` retains only workflow port inspectors, no data viewers. |
| SC-004 copy a built-in, edit, save, redraw without reopening | manual verification | **cannot be performed through the product.** The redraw half works (edit the file in the project and the watcher fires). The *copy* half has no UI at all; `PUT /api/panels/{id}/source` is the only path. See A-2. |
| SC-005 an agent's edit triggers the same reload | read the test | **pass.** `panelReload.test.ts` drives the `"agent"` source explicitly. |
| SC-006 three failure paths | read the tests | **pass.** `panelFrame.test.ts:220` never-answers, `:270` malformed traffic, and the version gate at `panelDescriptor.ts:83` with its `version_mismatch` headline in `PanelErrorSurface`. All three leave the data visible via the backend-named fallback. |
| SC-007 displaying panel granted no outbound type, **from the host's side** | read `panelCapability.ts` and `PanelHost.test.tsx` | **pass, and better than asked.** The gate does not check on delivery — for a displaying mount the emit consumer is never captured (`panelCapability.ts`, `const emitConsumer = capability === "producing" ? … : null`). `PanelHost.test.tsx:240` and `:266` assert nothing reaches the consumer; `:553` proves it still refuses `emit` from a mount that was just granted `resource` and `host_action`. |
| SC-008 confinement + allowlist across four roots | read the test | **pass.** Parametrised over `list(PanelTier)` for the document, every escape, and the allowlist. |
| SC-009 shim renders, gains nothing | read both halves | **pass.** `panelCompat.test.tsx:129` no bindings, `:138` an emit reaches no consumer. |
| SC-010 no frontend kind→panel mapping | absence search | **pass.** `coreViewers.tsx` deleted; `fallback_panel_id`/`fallback_panel` in the response schema. Two residual `target.kind === "plot_artifact"` checks survive, but they select a *tutorial highlight target*, not a panel. |
| SC-011 the rename commit changes no behaviour | read the commit | **fail on the letter, pass on the substance.** See F-4. |
| SC-012 layer test, drift audit, frozen inventory all pass | ran all three | **pass.** `full_audit` status `pass`, 0 errors; layer test green; `lint-imports` 13/0. |
| SC-013 removal condition stated in the addendum | read it | **pass, and it is the best-written part of this change.** `ADR-048-addendum1.md:214` states three clauses, each *"settled by looking rather than by judging"*, and `compat.py`'s docstring lists the exact deletion set. |
| SC-014 fixture package + fixture project | read both | **pass.** Directory-valued entry point in the fixture's `pyproject.toml`; `test_a_project_registers_a_panel_by_containing_a_directory`. |
| SC-015 producing resolution and its fallback | read the tests | **pass.** Both halves, plus `test_the_core_fallback_serves_a_producing_request_with_no_outbound_path`. |
| SC-016 displaying-only block panel refused at discovery | read the check and the test | **pass.** `blocks/registry/_capability.py:344` raises with a message naming the block and the panel; `test_panel_capability_gate.py:54`. |

---

## 4. The manager's decisions D-001 to D-020 — followed, and right?

The dispatch asked whether each ruling was *right*, not merely obeyed. Sixteen
are both. Four are worth the owner's attention.

| D | Followed | Right | Note |
|---|---|---|---|
| D-001 `scistudio.previewers` stays importable | yes | **yes** | Forced by FR-045. But the alias root is no longer in the ADR-052 frozen surface — see F-6. |
| D-002 what "no behaviour change" means for the rename | **no** | **right in substance, wrongly located** | The ruling is correct: a rename that may not touch a test is unimplementable. But it *rewrites SC-011*, and it does so in `docs/planning/`, which the spec's own `governs.excludes` excludes. And the rename commit broke D-002 anyway (F-4). |
| D-003 rename leaves user-visible copy alone | yes | yes | `PanelPalette.tsx:174` carries the deferral marker. |
| D-004 wire unchanged except `capabilities`→`features` | yes | yes | `schemas.py:542,631` carry `features`; the remaining `format_capabilities` is unrelated ADR-043. |
| D-005 tier directory names survive the rename | yes | yes | `test_a_project_that_still_has_the_old_file_keeps_working` proves the carry-over. |
| D-006 `ARCHITECTURE.md` untouched | yes | yes | Not in the diff. `#2059`'s `TODO` is pre-existing. |
| D-007 the on-disk form | yes | yes | All eleven `panel.json` files validate against it. |
| D-008 the merged route + allowlist | yes | yes | `.html` added; W3-fe's report notes T-011 emitted no event without it. |
| D-009 core contract module | yes | yes | |
| D-010 one version constant, the backend's | yes | **yes, and load-bearing** | This is what makes SC-001 measurable by absence rather than by trust. |
| D-011 the message contract | yes | yes | |
| D-012 where the host lives | yes | yes | |
| D-013 backend names the fallback | yes | yes | |
| **D-014 the `planned_govern`s migration is the manager's; do not fix the finding** | yes | **yes — and the manager did do it** | Verified independently: the spec's `planned_governs` is now four empty lists, `governs.files` carries all four paths, and `full_audit` reports **0 error findings**. The one instruction in this dispatch that told every agent to leave a real error-severity finding alone was honoured on both sides. |
| D-015 where the built-ins live | yes | yes | ids match exactly. |
| D-016 three additions to the contract | yes | yes | `accepted_api_version` + `read_limits` on the descriptor is what removes the frontend's last excuse for a version literal. |
| **D-017 `read`/`resource`/`host_action` granted to displaying mounts too** | yes | **necessary, but it widened FR-011 and the spec never followed** | FR-011 says a displaying panel is granted **no** outbound type. Read literally that contradicts FR-009 (`ready`) and FR-010 (a bounded read, an error channel), so a reinterpretation was unavoidable. But `host_action` goes further than those two require: four *displaying* panels (`core.plot.basic`, `core.artifact.basic`, `core.text.basic`, `core.base.fallback`) now ask the host to write a file to disk or hand off to the editor. That is defensible — it preserves the plot export button the migration must not lose — and the code argues it carefully in `panelCapability.ts`'s docstring. It is still a widening of a governing FR recorded only in a planning file. **The spec should say what shipped.** |
| D-018 Confirm/Cancel are host chrome | yes | yes | `InteractivePanelHost.tsx:199-227`; disabled until the first emission. |
| **D-019 the host keeps the tutorial surface** | yes | **yes, and it was the right refusal** | `TODO(#2229)` on a shipped tutorial would have been an orphan the moment the PR merged. The host now fires `preview_item_opened` (`PreviewHost.tsx:294`) and carries `data-tutorial-target="preview_item"` on its own chrome (`PanelTutorialChrome.tsx:69`). The rider *"the tutorial test must still pass unchanged"* was wrong and the manager later said so — see F-3. |
| D-020 the panel API surface | yes | **right as far as it goes** | Nine endpoints, all implemented. The gap is that D-020 defined the API and no decision ever assigned its *consumer*, which is how T-010 shipped with no UI (A-2). |

### The owner-directed scope expansion

The `scope.out` note of 2026-09-03 brought *settling a produced value in the
interactive-block context* into scope. **The reasoning is sound** — FR-033 and
FR-050 make DataRouter and PairEditor producing panels and FR-012 makes `emit`
their only outbound path, so without it the PR would have shipped two built-in
blocks that cannot be confirmed. It was recorded as a directive event on the
track ledger (`15:25:20Z`) with scope amendments in the same breath, and the
§3.6 statement whitelist was correctly kept out (`interactive.py:335`,
`:384` both say so explicitly).

It is also the single largest new risk surface in this PR, and it deserves
saying plainly: **it turns a WebSocket message into `exec` on the scheduler's
event loop.** Two consequences, F-2 and B-1 below.

---

## 5. Scope discipline, per ledger

Eleven ledgers under `.workflow/records/2229-*.json`. I reconstructed each
agent's true file set from its merge commit's second parent against the merge
base, and matched it against the ledger's `declared_scope.include` plus every
`add-include` scope event.

| Ledger | Files | Outside declared scope | Verdict |
|---|---|---|---|
| `2229-refactor-2229-panel-rename` | 150 | 0 | clean |
| `2229-feat-2229-panel-frame-host` | 13 | 0 | clean |
| `2229-feat-2229-builtin-panels` (2 merges) | 25 + 12 | 0 | clean |
| `2229-docs-2229-panel-addenda` | 3 | 0 | clean |
| `2229-feat-2229-panel-core-contract` | 34 | 0 | clean; also respected its own two `exclude` patterns |
| `2229-feat-2229-panel-frontend` | 43 | 0 | clean |
| `2229-feat-2229-panel-api` | 15 | 0 | clean |
| `2229-feat-2229-panel-compat-shim` | 8 | 0 | clean |
| `2229-feat-2229-panel-emission-consumer` | 8 | 0 | clean |
| `2229-feat-2229-tutorial-panel-migration` | 8 | 0 | clean |

(The only "outside" path in each set is the ledger's own JSON, which the gate
excludes by construction.)

**Amendments were recorded before the work, not retrofitted.** The strongest
example: `2229-feat-2229-panel-compat-shim` amended at `15:46:44Z` to change
`frontend/src/panels/panelCompat.test.ts` to `.tsx`, with the reason *"the
host-side SC-009 proof renders PanelHost, so it is a .tsx test file rather than
the .ts named at plan time"* — a one-character scope change recorded rather
than absorbed. `2229-feat-2229-panel-core-contract` amended six paths in one
event before touching the frozen-surface snapshot.

**Every file in the 267-file diff is declared by some ledger.** That is partly
because the manager's track ledger declares `src/scistudio/**`,
`frontend/src/**` and `tests/**`, so the union test is weak — which is why I
ran it per agent instead, where it is not weak at all. This is the cleanest
scope discipline I have measured on a dispatch this size.

---

## 6. Findings, by severity

### A-1 (P1) — a save that succeeds and is thrown away

`src/scistudio/panels/editing.py:316`, `src/scistudio/panels/compat.py:675`

`build_compat_panel` sets the wrapped panel's tier from the previewer's owner:

```python
tier = spec.owner_kind if isinstance(spec.owner_kind, PanelTier) else PanelTier.PACKAGE
```

`OwnerKind is PanelTier` (`models.py:78`), so a previewer supplied by a **user
library or project drop-in** — which FR-020 requires to keep being discovered —
gets tier `USER` or `PROJECT`, while its `directory` points inside the
disposable shim root that `compat_shim_root()` recreates on every registry
build. `save_panel_source` then takes the editable-tier branch and writes *in
place*, into the temp directory.

I proved it rather than reasoned about it:

```
--- owner_kind=user: tier=user is_compat=True editable_in_place=True
    under disposable shim root? True
    SAVE -> tier=user copied=False
    wrote into the disposable shim dir? True
    project got a copy? False
    EDIT SURVIVES A REGISTRY REBUILD? False
--- owner_kind=project: … identical
```

The person sees the edit take effect (the reload token bumps, the frame
remounts from the just-written file), and then it silently disappears at the
next `POST /api/panels/reload` or restart. FR-028 is written against precisely
this: *"It MUST NOT silently fall back to the panel that was shadowed, because
a silent fallback reads as an edit that was never saved."*

The shim's own docstring already states the invariant being violated —
`compat.py:530`, *"it must not look like something a person edits"* — and
`is_compat_panel()` exists and is not consulted.

**Fix:** refuse in `save_panel_source` when `is_compat_panel(panel)`, with a
diagnostic saying the panel is a wrapped ADR-048 previewer and the way to edit
it is to migrate it. Three lines and one test.

### A-2 (P1) — T-010 shipped without its host half; FR-028 is unimplemented

`frontend/src/panels/PanelErrorSurface.tsx`, `frontend/src/lib/api/`

FR-028: *"When an edited panel fails to load, **the host** MUST report the
failure explicitly **and offer to revert**."* The host reports (the error
surface names the panel, the reason code and the message — FR-014 is
satisfied). It offers nothing. `grep -rni "revert" frontend/src` returns four
hits, none of them about panels.

The split is clean and easy to check. Of D-020's nine endpoints the frontend
consumes five: the asset route (`lib/api/data.ts:73`), `GET /api/panels`
(`data.ts:183`), `POST /api/panels/reload`, and the two choice endpoints — all
cited in `PanelPalette.tsx:9-14`. It consumes **none** of the three editing
endpoints: `grep -rn "panels/.*source\|/override" frontend/src` returns nothing
and there is no `frontend/src/lib/api/panels.ts`.

The consequence for the success criteria: **SC-004 cannot be manually verified
against the product.** Its "edit, save, redraw" half works through the ordinary
code editor now that panels are files on disk, but its *"copy a built-in panel
into a project"* half has no affordance outside curl.

This is a decomposition gap, not an agent failure. D-020 defined nine endpoints
and named `W3-api` as producer and `W3-fe` as consumer; `W3-fe`'s assigned
tasks are T-007, T-008's frontend half and T-011. Nobody owned T-010's
frontend. The checklist nevertheless marks T-010 `[x]` with an artifact that
describes only the write path's confinement.

**Fix:** either implement the revert offer and a copy affordance, or move
T-010's frontend half to a tracked follow-up issue and correct the checklist
row and SC-004's measurement so the PR does not claim it.

### F-1 (P2) — every `TODO(#2211)` this change introduces cites a **closed** issue

Three live sites plus three planning references:

- `frontend/src/components/PanelPalette.tsx:174`
- `docs/adr/ADR-048-addendum1.md:284`
- `docs/adr/ADR-051-addendum2.md:279`
- `docs/planning/adr-054-panel-contract-checklist.md:77` (§2 "Deferred work")
- `docs/planning/adr-054-panel-contract-prompts.md:146,457`

`gh issue view 2211` → **CLOSED**, *"docs(ADR-054): specify the architecture,
developer, and generated documentation revision"*. It is the spec-**authoring**
issue, the sibling of #2213 which this dispatch correctly treats as closed. It
was never the issue that performs the revision. Every one of these deferrals is
therefore orphaned on arrival, and the drift log routes the stale
`docs/user/reference/*.md` staleness to it as well.

For contrast, `TODO(#2212)` (six sites) is exactly right: #2212 is **OPEN** and
titled *"feat(panels): let a plot panel declare the producing capability"*,
which is what the TODOs defer. `TODO(#2135)` in `tutorial.yaml:720` is
pre-existing, not introduced here.

**No `TODO(#2229)` survives in code.** The three textual occurrences are (a) a
test comment quoting the phrase, and (b) the checklist and prompt entries where
D-019 *rejects* a `TODO(#2229)`. The one class of deferral this dispatch was
warned about was correctly prevented.

**Fix:** open the documentation-revision implementation issue and retarget the
three live TODOs, or point them at #2209 which is open and tracks ADR-054 whole.

### F-2 (P2) — an emission's key is `"code"`, and any block's decision of that
shape becomes Python

`src/scistudio/blocks/base/interactive.py:250,470`

```python
INTERACTIVE_EMISSION_KEY = "code"
```

`is_panel_emission` fires when the payload is a dict whose *only* key is
`"code"` and whose value is a string. The implementers saw this and wrote the
caveat into the docstring themselves — *"A decision that happened to be exactly
`{"code": "<some string>"}` would be read as an emission. No block in the tree
has such a decision"* — and that survey is honest and correct for this
repository. It does not cover ADR-051 interactive blocks shipped by packages,
where a decision naming a code, an identifier, or a language is unremarkable.
Such a block stops working: its value is parsed as Python, calls no
`scistudio.output`, and raises `InteractiveEmissionError`.

Loud rather than silent, as the docstring says — but loud and *broken* for a
third-party block that was working, in a change whose Story 4 is *"an unmigrated
package keeps working"*.

**Fix:** make the envelope key unambiguous (`"__scistudio_panel_emission__"`,
or `{"kind": "emission", "code": …}`). The emitting side is host chrome shipped
by this same PR, so the change costs one constant and one test.

### F-3 (P2) — three drift-log omissions and one understatement

The drift log (checklist §9) is 24 rows and is, overall, unusually candid — it
records the manager's own YAML-quoting mistake that blinded every
frontmatter-driven audit, and it records `W4-builtin` leaving a document in a
mixed state and self-catching it. Against the ledgers and the diff, four things
do not match:

1. **Missing: the tutorial tier-guard security gap.** `448c64c42` fixes a real
   hole — the rename introduced a `<project>/panels` root that
   `EXECUTED_PROJECT_PATHS` and `_SCANNED_PROJECT_DIRS` did not name, so a
   user- or project-level tutorial could write a `panels/` directory the product
   serves into a frame and whose `panel.json` may name a Python provider it
   imports. It is recorded in the commit message and in a `17:46:34Z` track-ledger
   amendment. It is **not in the drift log**, which is the artifact a reviewer
   reads.
2. **Missing: the rename commit added a test.** F-4 below. Two named rules broken,
   no row.
3. **Missing: two agents have no dispatch-matrix row.**
   `feat/2229-panel-emission-consumer` and `feat/2229-tutorial-panel-migration`
   each have a full gate ledger, a merge commit, and 8 files, and neither appears
   in checklist §6. They exist in the drift log only as passing references inside
   another agent's row.
4. **Understated: "those three assertions".** The `W4-compat` row says the
   tutorial migration was blocked by *"three assertions in
   `test_core_tutorial_what_is_a_type.py` [that] pin the retired `.mjs` form."*
   The file actually changed by **+168 / −50**: 14 assertions removed, 47 added,
   three test functions renamed and two rewritten. The direction is right (the
   test gained coverage and the two rewrites target exactly the retired form the
   spec §4.2 retires) — but "three assertions" is not what a reviewer trusting
   that row would expect to find.

### F-4 (P2) — the rename commit broke D-002 and SC-011, unrecorded

`tests/panels/test_previewers_alias.py` (new, 61 lines, 6 assertions) is added
in `782678f3b`, the single rename commit. D-002: *"No test may be added or
deleted in the rename commit."* SC-011: *"the full suite passing on both sides
of it with no test modified in that commit."*

The addition is defensible in itself — it pins the D-001 alias, which is the one
genuinely new thing the rename introduces — and I confirmed no other test file
was added or deleted (`tests/panels/__init__.py` for
`tests/previewers/__init__.py` is a move). But a rule the manager wrote
explicitly, one release before an auditor reads it, was broken without a drift
row, and SC-011's own measurement no longer means what it says.

**Fix:** a drift-log row, and either an amended D-002 (*"except a test that pins
a compatibility alias the rename introduces"*) or an amended SC-011.

### F-5 (P3) — FR-041's obligation on the spec is unmet

FR-041 requires *"the spec MUST state how the renamed symbols' stability markers
are derived."* Searching `docs/specs/adr-054-panel-contract.md` for `derive`,
`marker`, `@stable`: the requirement is stated at line 489, the affected-files
table mentions it at 708, and §4.5 at 776-780 says *"the mitigation is that
FR-041 requires the spec to state how the renamed symbols' markers are derived
rather than leaving it to the implementer."* The spec never states it.

The risk it guards did not materialise, and I checked rather than assumed:
every symbol under `scistudio.previewers.models` and
`scistudio.previewers.data_access` was `provisional` on `origin/main`, and every
symbol under `scistudio.panels.models`, `scistudio.panels.data_access` and the
new `scistudio.core.panels` is `provisional` now. Nothing was silently reset,
because there was nothing above provisional to reset.

### F-6 (P3) — the compatibility surface D-001 promises is not in the frozen
inventory

`origin/main`'s `expected_surface.json` carried `scistudio.previewers.models`
and `scistudio.previewers.data_access` as frozen roots. The new file carries
`scistudio.core.panels`, `scistudio.panels.models` and
`scistudio.panels.data_access`, and **no `scistudio.previewers.*` root at all**
— even though D-001 keeps those modules importable precisely because packages
import `PreviewerSpec` from them, and the ADR-048 addendum's removal condition
names their contents as a clause.

`tests/panels/test_previewers_alias.py` does pin them, so they are not
unguarded; but the ADR-052 contract test — the mechanism that exists to notice a
public symbol vanishing — no longer covers the surface a package actually
imports.

### F-7 (P3) — `admin-approved:core-change` is requested but not applied

`gate_record check --base origin/main` leaves exactly one obligation
unsatisfied:

```
guard.core_change_guard
  Affected: src/scistudio/blocks/base/interactive.py,
            src/scistudio/blocks/process/builtins/data_router.py,
            src/scistudio/blocks/process/builtins/pair_editor.py,
            src/scistudio/blocks/registry/__init__.py,
            src/scistudio/blocks/registry/_capability.py
```

`2229-feat-2229-panel-core-contract.json` has
`requested_admin_labels: [admin-approved:core-change]` with `applied_at: null`
and `observed_admin_labels: []`. The manager flagged this in the drift log and
says it will request the label from the owner. Expected and correctly handled —
recorded here so it is not lost between the umbrella PR and the final one.
**Every one of those paths is in the spec's own `governs.files`**, so the change
is authorised by an approved spec; what is missing is the label, not the
authority.

### F-8 (P3) — the final PR must pin `origin/main` as its gate base

My audit branch is byte-identical to the track branch, and that made the hazard
visible:

- `check --base origin/main` → tier **1**, 11 checks, `core_change_guard` fires.
- `check --base track/adr-054-spec1-panel-contract` → 0 files observed,
  tier **3**, 2 checks, *"recovery reconciliation passed."*

The track ledger's `base_ref` is `null` (every agent ledger correctly carries
`origin/track/adr-054-spec1-panel-contract`, which is right for that agent's own
diff). If the final PR's gate resolves its base to the track branch, it will
observe nothing and pass on an empty diff. Set `--base-ref origin/main` on the
track ledger before `finalize`.

### F-9 (P3) — the checklist's own status is wrong in both directions

§7.3 marks **T-002, T-003, T-013, T-015 and T-016 as `[ ]` not started**, and
§6 marks `W2-core` `[~] re-dispatched`, `W3-api` `[ ]`, `W3-fe` `[ ]`,
`W5-test` `[ ]` and both audits `[ ]`. All five of those tasks were merged in
`3ac851856 merge(#2229): integrate T-002, T-003, T-013, T-015 and T-016`, and
their code, tests and frozen-surface entries are in the tree. Meanwhile §7.3
marks T-010 `[x]` on evidence that covers half of it (A-2).

Section 3 of the checklist says *"Every completed row MUST include an
artifact"*; the inverse rule — a delivered task must not read as not-started —
matters as much when the checklist is what the owner reads at merge time.

### F-10 (P3) — the shim's removal is deferred work with no tracking issue

`ADR-048-addendum1.md:236` says *"The check belongs to the owner of the
imaging-package migration, on the issue that tracks it"* — and names no issue
number. There is no `TODO(#NNN)` on `compat.py`. The three clauses are excellent
and inspectable; what is missing is the one thing AGENTS.md §3.6 asks for, a
place the work is visible. `deferral_discipline` does not catch it because there
is no TODO to catch.

### B-1 (observation, for the owner rather than a fix) — the emission path's
new exposure

`settle_panel_emission` (`interactive.py:365`) `exec`s a WebSocket-delivered
snippet on the scheduler's event loop, in a namespace with `__builtins__ = {}`
and one bound name. The docstring is admirably honest about the bound it does
not have:

> *"An emission that does not terminate — `while True: pass` — is not refused,
> and this runs on the scheduler's event loop, so it would wedge the whole
> engine rather than one block."*

Three things follow, none of which I am calling a defect:

1. That unbounded-execution exposure is **recorded in a docstring and nowhere
   else** — no `TODO(#NNN)`, no issue. Given AGENTS.md §3.6, it should be
   tracked even if the answer is "accepted, out of scope".
2. `settle_interactive_response` does **not** check that the paused block
   declared a producing panel before executing. FR-050's discovery-time refusal
   makes a displaying-only block panel impossible, so this is defence in depth
   rather than a hole — but the exec is reached from payload shape alone.
3. The escalation is real and worth naming: under ADR-048 a package's panel had
   no outbound path at all. Under this contract a package can declare a
   producing panel on a block, and that panel's frame can hand the backend a
   string it will `exec`. The trust model ("a panel document is installed the
   way a block is") is stated and is coherent. The owner should confirm he means
   it.

The `_refuse_dunder_reach` denylist looked tight to me under review — with no
builtins there is no `getattr`, so the classic `().__class__.__bases__` walk is
what matters and it is closed at the AST. **I did not attempt to break it**;
the adversarial test engineer is the right owner for that, and agreement
between us would be signal.

---

## 7. What was done well, and should not be lost in a findings list

- **The capability gate is structural.** `panelCapability.ts` never captures the
  emit consumer for a displaying mount, so there is no reference for later code
  to reach by accident. SC-007 asked for a host-side test; the implementation
  made the test almost redundant.
- **D-014 was honoured on both sides.** The manager told every agent to leave a
  standing error-severity `full_audit` finding alone and promised to clear it at
  integration. Every agent did; the manager did; `full_audit` is at zero errors.
  That is the hardest kind of instruction to get obeyed in a parallel dispatch.
- **D-019 refused a `TODO(#2229)`.** A deferral pointing at the issue the PR
  closes is orphaned by construction, and the manager caught it, verified the
  five dependencies, and specified the fix instead of accepting the marker.
- **The shim wraps on the backend.** Wrapping into a real panel directory rather
  than adding a second frontend mount path is what keeps SC-001 and SC-002
  measurable by absence. `compat.py`'s docstring explains why, and lists its own
  deletion set.
- **Scope discipline is exact.** Ten agent branches, 0 files outside declared
  scope, amendments recorded before the work including a one-character
  `.ts`→`.tsx` change.
- **A-007 was verified, not assumed.** The spec flagged the watcher behaviour as
  unverified; `panelReload.test.ts` drives an `"agent"`-sourced event and proves
  it.

---

## 8. Recommendation

**pass-with-fixes.**

Before the final PR:

1. **A-1** — refuse `save_panel_source` for a compat panel. Three lines.
2. **A-2** — either implement FR-028's revert offer and a copy affordance, or
   open a follow-up issue and correct the T-010 row and SC-004's claim.
3. **F-1** — retarget the three live `TODO(#2211)`s at an open issue.
4. **F-7** — obtain `admin-approved:core-change`.
5. **F-8** — set the track ledger's `base_ref` to `origin/main` before
   `finalize`.
6. **F-3, F-4, F-9** — bring the checklist and drift log up to what the tree
   shows.

Owner decisions, not fixes: **D-017's widening of FR-011** (should the spec say
what shipped?), **F-2's envelope key**, and **B-1's exec exposure**.

Everything else in this change is ready.
