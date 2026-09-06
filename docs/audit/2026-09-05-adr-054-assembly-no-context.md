---
title: "Audit — ADR-054 as one assembled feature (no-context)"
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
  - adr-054-notebook-dependency-analysis
  - adr-054-explore-session
  - adr-054-explore-frontend
  - adr-054-agent-enablement
  - adr-054-documentation
language_source: en
---

# Audit — ADR-054 as one assembled feature (no-context)

Audit mode: **no-context** (agent `INT-E1`, `audit_reviewer` persona).
Subject: ADR-054 as **one assembled feature**, and specifically the seams
between its five implemented specs — not any one spec on its own.
Audit branch: `audit/2255-assembly-no-context`, worktree `.worktrees/int-e1`.
Base: `origin/main` at `56b73f03d`; diff is 579 files, +176,874 / −13,370.
Gate ledger: `.workflow/records/2255-adr-054-assembly-no-context-audit.json`.

**Context discipline.** I read no GitHub issue, PR, PR comment or commit
message; I ran no `gh`; I read no `git log` message for the ADR-054 branches;
I read no assembly checklist, no other dispatch prompt, no follow-up register,
and nothing under `.workflow/records/**`. I read no report under
`docs/audit/**`, before or after writing this one — where a grep incidentally
surfaced a line from one, I did not open the file or let it steer a finding.
Every conclusion below comes from the repository as it stands and from tool
output I produced myself.

**Verdict: `block`.** Not because the work is poor — the opposite is true, and
§6 records how much of the assembly is genuinely well joined. It is `block`
because two checks that gate CI fail on this branch and did not fail on
`origin/main`, and because one seam (S-1) leaves the ADR's central claim —
"one panel contract serves display and production" — with no reachable path
through the assembled product for any type SciStudio ships, while every suite
that would have caught it either uses a panel id that does not exist or was
never written.

---

## 0. What I actually ran

| Command | Result |
|---|---|
| `PYTHONPATH=./src pytest tests/ -q --no-cov -x --ignore=tests/blocks/io -p no:randomly` | **FAILED** at `tests/api/test_explore_branch_switch.py::test_a_branch_switch_kills_the_real_kernel_process` (`-x` stopped the run). See S-3. |
| `PYTHONPATH=./src pytest tests/ -q --no-cov --ignore=tests/blocks/io -p no:randomly` (no `-x`) | **exit 1, exactly one failure** — the same `test_a_branch_switch_kills_the_real_kernel_process`. Everything else passed; 8 xfailed (all `#1454`), ~60 skips (POSIX-only, Rscript/Fiji/Octave opt-ins, symlink elevation, the sanctioned `.xlsx`/R exceptions). |
| `PYTHONPATH=./src pytest tests/blocks/io -q --no-cov -p no:randomly` | **exit 0, all passed.** |
| `PYTHONPATH=./src pytest tests/architecture tests/docs -q --no-cov -p no:randomly` | **625 passed, 1 skipped**, exit 0. The skip is `tests/architecture/test_registries.py:138` — an empty entry-point parameter set. |
| `npm ci` in `frontend/` | `node_modules` was absent; installed, exit 0. |
| `npm run test` in `frontend/` | **2570 passed / 1 failed** (217 files). The failure is `src/__tests__/eslint-config.test.ts` — `Test timed out in 5000ms` (actual 11084 ms). See I-4: pre-existing/environmental. |
| `npm run lint` in `frontend/` | **exit 1 — 1 error**, 71 warnings. The error is new on this branch. See I-1. |
| `npm run build` in `frontend/` | exit 0, built in 3.17 s. |
| `ruff check .` | `All checks passed!`, exit 0. |
| `ruff format --check .` | **exit 1** — `Would reformat: tests\contracts\test_workspace_focus_wire_contract.py` (1 of 1000). New file on this branch. See I-2. |
| `python -m mypy src/scistudio/ --ignore-missing-imports` | `Success: no issues found in 418 source files`, exit 0. |
| `lint-imports` | **15 contracts kept, 0 broken.** (The `lint-imports` console script aborts with `uv trampoline failed to canonicalize script path` in this environment; run through `importlinter.cli.lint_imports_command` instead. Same for `mypy`/`ruff` shims.) |
| `python scripts/audit/generate_facts.py --check` | exit 1 — `docs/facts/generated.yaml` missing. It is `.gitignore`d (line 36) and absent on `origin/main` too, so this is a fresh-worktree condition, not a finding. After `--write`, `--check` exits 0. |
| `python -m scistudio.qa.governance.gate_record check --mode pre-pr` | `no gate ledger found; run init first` (exit 2) before I created one; I then ran `init`/`plan` for this audit (tier 3, `docs`/`audit_reviewer`, `--include docs/audit/**`) and re-ran `check` after committing. **exit 1**, with a test run of its own and two guard obligations. See §0.2 and §2.1. |
| Bespoke probes | The wire differ of §1.1, the message-vocabulary sweep of §1.2, the live panel-registry query of S-1, and the `PYTHONPATH` bisection of S-3 — all executed against the real code. |

### 0.1 The full Python suite

The un-`-x`'d full run completed: **exit 1, with exactly one `FAILED` line** —

```
FAILED tests/api/test_explore_branch_switch.py::test_a_branch_switch_kills_the_real_kernel_process
```

That is S-3, and it is the only Python test failure on this branch.
`tests/blocks/io`, run separately per the dispatch, is **exit 0, all passed**.

The explore suites spawn real `ipykernel` processes under
`@pytest.mark.serial` with 60 s idle timeouts, which is why the wall clock is
long; the run is otherwise clean.

### 0.2 The gate check ran its own suite, and found five other failures

`gate_record check --mode pre-pr` narrows a run to the observed diff. Because
my audit branch is based on the assembly, the diff it observed is the whole
ADR-054 change, so its run is a second, independent measurement worth
recording:

```
5 failed, 9502 passed, 80 skipped, 8 xfailed, 105 warnings in 411.28s

FAILED tests/ai/test_mcp_tools_disk_integration.py::test_concurrent_write_workflow_serialises
FAILED tests/api/test_workflows.py::test_workflow_execute_and_execute_from_reuses_cached_outputs
FAILED tests/api/test_system_vertical.py::test_completed_run_lineage_outputs_are_previewable
FAILED tests/api/test_workflows.py::test_execute_after_completion_is_allowed
FAILED tests/workflow/test_serializer_property.py::test_relativify_inverts_absolutify
```

**None of the five reproduced.** My own full run over the same tree — all of
`tests/` including every one of these four files — finished with exactly one
`FAILED` line, and it was S-3. So all five passed when run in the ordinary
order.

That includes
`tests/api/test_system_vertical.py::test_completed_run_lineage_outputs_are_previewable`,
which is the one I would otherwise not have waved through, since "previewable"
is precisely the surface ADR-054 renamed and re-routed. It passes.

All four files are also untouched by the ADR-054 diff
(`git diff --numstat origin/main...<assembly> --` on each returns nothing), and
the failure profile fits: three of the five
(`test_concurrent_write_workflow_serialises` and the two cached-output
`test_workflows.py` cases) are concurrency- or ordering-sensitive and
`test_relativify_inverts_absolutify` is a property test. I read these as
artefacts of the gate's narrowed, differently-ordered selection rather than
regressions — but they are worth knowing about, because a reviewer who runs
only `gate_record check` will see five red lines that a full run does not
reproduce.

---

## 1. How I looked for a wire whose two ends disagree

The dispatch names this as a repeated failure mode here, so I did not eyeball
it. I wrote a differ that imports the backend Pydantic models, parses the
TypeScript interfaces out of `frontend/src/types/*.ts` as text (resolving
`extends`), and reports fields present on one side only plus nullability
mismatches.

### 1.1 The Explore session wire: clean

36 model/interface pairs across `src/scistudio/api/routes/explore.py` and
`frontend/src/types/explore.ts` — every response model, request model and
nested model the session API defines. **0 mismatches.** Field names, presence
and nullability agree on both sides, including the awkward ones
(`PackageResponse.problems`, `BindingModel.exists_in_kernel`,
`CellModel.cell_id: str | None`). This is the best-joined wire in the change
and I want it on the record as such.

### 1.2 The panel message vocabulary: clean

The contract's 15 message names — 8 host→panel, 7 panel→host — agree across
all four consumers I could check mechanically:
`frontend/src/panels/panelMessages.ts`, the eleven built-in panel documents
under `src/scistudio/panels/builtin/`, the agent scaffold in
`src/scistudio/ai/agent/mcp/tools_panels/`, and
`src/scistudio/_agent_reference/panel-contract.md` (which names all 13 it
should). `src/scistudio/panels/compat.py` speaks all of them **except** `emit`
and `state` — which is correct, and is exactly what ADR-054 §9.4 requires of a
shim that must not grow the producing surface.

There is one `PANEL_API_VERSION`, defined at `src/scistudio/core/panels.py:49`
and imported everywhere else; no frontend file spells a version literal. All
eleven built-in `panel.json` files and the fixture package's panel declare
`api_version: "1"`.

### 1.3 The panel catalogue wire: **not clean** — see S-2

---

## 2. Findings

Ordered by severity. Each is marked **seam** (between two specs) or
**inside** (within one).

### 2.1 Two gate obligations the assembled diff carries

Recorded first because they are observations about the whole change, not
defects in any one spec, and because I must be careful about what they prove.
`gate_record check` fired both guards against **my** ledger, which declares
neither — and the diff it observed is my branch against `origin/main`, which
contains the entire assembly. So this is evidence that **the assembled diff
carries these obligations**, not evidence that the ADR-054 ledgers failed to
declare them. I could not check the latter: `.workflow/records/**` is outside
my context limits.

**`guard.core_change_guard`** — "protected core/runtime change requires
`admin-approved:core-change` applied by an authorized maintainer".
Affected: `src/scistudio/blocks/base/interactive.py`,
`src/scistudio/blocks/code/backends/notebook.py`,
`src/scistudio/blocks/process/builtins/data_router.py`,
`src/scistudio/blocks/process/builtins/pair_editor.py`,
`src/scistudio/blocks/registry/__init__.py`.

**`guard.mod_guard`** — "governance-critical file changed without
authorization; declare `governance_touch` in the ledger and obtain owner
review". Affected: `.github/workflows/ci.yml`,
`docs/ai-developer/e2e/2026-09-05-adr054-explore-assembly.md`,
`docs/ai-developer/gate-cli-command-set.md`,
`docs/ai-developer/specific_rules/gated-workflow.md`, `pyproject.toml`.

All five are genuinely in the assembly diff (`ci.yml` +46/−9,
`gate-cli-command-set.md` +40, `gated-workflow.md` +66, the e2e scenario +364,
`pyproject.toml` +102/−…). `AGENTS.md` §3.7 is explicit that
`docs/ai-developer/**` is a governance surface requiring a `governance_touch`
declaration, focused scope and owner review. A change that edits the gate CLI
reference and the gated-workflow rule *while being gated by them* is exactly
the case that rule exists for, and it is worth the owner's eyes regardless of
what the assembly ledgers declare.

### S-1 — P1 — **seam** (spec 1 ↔ spec 4): no producing panel is reachable for any type SciStudio ships

ADR-054 §1 states the feature's central claim: "One panel contract serves
display and production… the same panel serves either." §3.3 says "A producing
panel bound to a notebook variable is routed by that variable's type, which
puts it back on the first ladder." §10.3 puts "a small set of producing
panels" and "panel-to-code generation" in the **first** slice.

In the assembled tree, the type ladder can never return a producing panel.

**Every producing panel declares no target type.** Read straight off disk:

```
core.array.basic              displaying  target_types=['Array']
core.artifact.basic           displaying  target_types=['Artifact']
core.base.fallback            displaying  target_types=['DataObject']
core.collection.basic         displaying  target_types=['Collection']
core.composite.basic          displaying  target_types=['CompositeData']
core.dataframe.basic          displaying  target_types=['DataFrame']
core.interactive.data_router  producing   target_types=[]
core.interactive.pair_editor  producing   target_types=[]
core.plot.basic               displaying  target_types=['PlotArtifact']
core.series.basic             displaying  target_types=['Series']
core.text.basic               displaying  target_types=['Text']
```

That is correct on spec 1's own terms — §3.3 says a block-addressed panel is
named by its block and "no routing question arises", so it rightly declares no
type.

**The catalogue route excludes exactly those panels whenever a type is asked
for.** `src/scistudio/api/routes/panels.py:349-350` filters
`registry.all_specs()` to `spec.target_type == target_type`; the block-
addressed panels, which never enter the type registry, are appended **only**
when `target_type is None` (line 357). So `GET /api/panels?target_type=X` can
structurally never contain a producing row.

**The frontend's producing request goes through that route and nothing else.**
`frontend/src/explore/PanelSlots.tsx:137-152` is the whole of it:

```ts
const listing = await dataApi.listPanels(typeName);
const rows = ((listing.panels ?? []) as PanelCatalogueRow[]).filter((row) => row.descriptor);
const producing = rows.find(
  (row) => isPanelCapability(row.capability) && capabilitySatisfies(row.capability, "producing"),
);
if (producing?.descriptor) {
  return { descriptor: producing.descriptor, fellBackToDisplay: false };
}
const displaying = rows[0];
if (!displaying?.descriptor) return null;
return { descriptor: displaying.descriptor, fellBackToDisplay: true };
```

That is also correct on spec 4's own terms — FR-048's "first candidate that
declares at least the required capability", FR-049's displaying fallback.

**Verified against the live registry**, not inferred:

```
$ PYTHONPATH=./src python -c "... build_preview_service() ..."
target_type=DataFrame    -> 1 row(s), producing candidates: []
target_type=Array        -> 1 row(s), producing candidates: []
target_type=Series       -> 1 row(s), producing candidates: []
target_type=Text         -> 1 row(s), producing candidates: []
target_type=Collection   -> 1 row(s), producing candidates: []
```

**Consequence.** `VariableStrip.tsx:139` calls `resolveProducingPanel` on every
click on a live variable, unconditionally. For every type SciStudio ships it
returns `fellBackToDisplay: true` and mounts a **displaying** panel with no
outbound path. The person clicks "produce from this variable" and gets a
viewer. The emission path built beside it — the `emit` message, the AST
whitelist of §3.6, `POST /api/explore/sessions/{id}/snippets`,
`EmitSnippetResponse` — is complete, tested, and has nothing that can call it.

And the fallback is **silent**. `fellBackToDisplay` is computed at
`PanelSlots.tsx:151` and read nowhere — `grep -rn "fellBackToDisplay"
frontend/src/` returns three hits, all of them the declaration, the `false`
branch and the `true` branch inside `PanelSlots.tsx` itself.
`VariableStrip.tsx:139-147` takes `resolved.descriptor` and discards the flag.
So in the shipped product the flag is `true` on every producing request, and
nothing tells the person that the panel they just opened cannot produce.

A sub-case: `VariableStrip.tsx:138` resolves with
`entry.typeName ?? entry.nativeTypeName`, so a variable the kernel reports
only natively (`str`, `dict`) queries `?target_type=str`, gets zero rows, and
`resolveProducingPanel` returns `null` — `if (!resolved) return;` — so the
click is a **silent no-op** with no diagnostic.

**Why this is a seam and not a defect inside either spec.** Neither half is
wrong by itself. Spec 1 shipped two producing panels and routed them the way
§3.3 says block-addressed panels are routed. Spec 4 built the ladder call
§3.3 says a notebook-bound producing panel uses. Nobody owned the question of
whether a panel exists that both halves can meet on, and nothing in the
repository records it as deferred: the `TODO(#2253)` at
`PanelSlots.tsx:132` defers the *specificity walk and the FR-049 per-type
choice*, not the absence of any producing candidate at all.

**Why no suite caught it.** The two frontend suites that exercise this path —
`frontend/src/explore/PanelSlots.test.tsx:54` and
`frontend/src/explore/VariableStrip.test.tsx:93` — both use
`panel_id: "core.dataframe.editor"` with `capability: "producing"`. That panel
does not exist anywhere in the tree; the string appears in those two test
files and nowhere else. This is precisely the failure mode the dispatch names:
a hand-written fixture that agrees with the frontend code while both disagree
with the server. And the one test that could not have been faked — FR-036's
end-to-end scenario, which requires "open a panel, **emit a cell from it**" —
was never written (S-4).

**Fix shape** (the owner's call, not mine): either ship at least one
type-routed producing panel in the first slice as §10.3 says, or make
`GET /api/panels?target_type=` reachable by `PreviewRouter.resolve_request` so
a block-addressed producing panel can be offered, or record the absence as a
tracked deferral and have `VariableStrip` say so instead of silently mounting
a viewer.

---

### S-2 — P1 — **seam** (spec 1 ↔ spec 4): the catalogue wire is described twice, and the consumer widened the shared type locally

`PanelSpecModel` gained a `descriptor` field
(`src/scistudio/api/schemas.py:643`, `descriptor: PanelDescriptorModel | None`,
docstring "What the frame host mounts this panel from"). The shared frontend
type never learned it: `PanelSpecSummary`
(`frontend/src/types/api.ts:787-808`) declares eleven fields and ends at
`shadows`. `frontend/src/types/api.ts` is governed by the explore-frontend
spec.

The consumer that needs the field re-declared the shape locally rather than
fixing the shared one — `frontend/src/explore/PanelSlots.tsx:103-105`:

```ts
type PanelCatalogueRow = PanelSpecSummary & {
  readonly descriptor?: PanelDescriptorResponse | null;
};
```

and then casts the response into it at line 142.

This is my differ's only hit across the panel models (the two other reported
deltas — `key` and `max_bytes` on `PanelDescriptorResponse` — are artefacts of
my regex reading the inline `read_limits: { max_rows; max_bytes; [key: string] }`
object literal as top-level fields; I checked and they are not real).

Two ends of one wire, described in two places, with the gap papered over at
one call site. It works today. The next consumer either repeats the local
widening or reads `PanelSpecSummary`, concludes `descriptor` is not on the
wire, and issues a second request for something it already had. Note also that
the local type says `descriptor?` while the backend always emits the key
(possibly `null`).

**Fix:** add `descriptor: PanelDescriptorResponse | null` to `PanelSpecSummary`
and delete `PanelCatalogueRow`.

---

### S-3 — P1 — **seam** (spec 3 ↔ the repository's own development contract): a real kernel cannot import `scistudio` under `PYTHONPATH=./src`

`AGENTS.md` §3.1 makes this a hard rule: "Do not use `pip install -e .`. Use
`PYTHONPATH=./src`." My dispatch repeats it. Under exactly that invocation, a
real Explore kernel cannot import `scistudio`.

```
$ PYTHONPATH=./src python -m pytest tests/api/test_explore_branch_switch.py::test_a_branch_switch_kills_the_real_kernel_process -q --no-cov
FAILED

scistudio.explore.kernel_bridge.BridgeProtocolError: The kernel bridge did not answer:
ModuleNotFoundError: No module named 'scistudio'. The usual cause is a kernel whose
interpreter cannot import scistudio.
```

**Mechanism**, and I bisected it rather than guessing.
`src/scistudio/explore/kernel.py:769` inherits the parent environment
(`env = dict(os.environ)`) and line 773 sets the child's working directory to
the project (`launch_kwargs["cwd"] = str(self._working_directory)`, fed from
`session.py:1610`, `working_directory=self._project_dir`). `PYTHONPATH=./src`
is **relative**, so in the child it resolves against the project directory —
`<project>/src`, which does not exist.

**Proof:**

| Invocation | Result |
|---|---|
| `PYTHONPATH=./src python -m pytest …::test_a_branch_switch_kills_the_real_kernel_process` | **FAILED** |
| `PYTHONPATH=<abs>/src python -m pytest …::test_a_branch_switch_kills_the_real_kernel_process` | **passed** |

Same commit, same test, one environment variable made absolute.

**This is new**, not pre-existing: the test and the module are added by this
branch (`tests/api/test_explore_branch_switch.py`, +136 for the sibling
contract file, the whole `explore/` package new).

**Why it is a seam and why it is more than a test bug.** The kernel module's
own docstring at `kernel.py:404` states the assumption that breaks: the
interpreter "in a source checkout is the environment the service runs in".
That is true of `sys.executable` and false of `sys.path` the moment the child's
cwd moves — and moving it is correct, because a notebook must resolve relative
data paths against the project. Neither decision is wrong; the combination is,
and it meets the repository's own mandated dev invocation head-on. A developer
or agent running SciStudio from a source checkout the sanctioned way gets a
kernel in which `scistudio.output` (§3.6), in-kernel block calls (§5.5) and the
bridge (§5.2) all fail — which means packaging fails too.

**Fix shape:** absolutise `PYTHONPATH` entries when building the kernel's env
in `KernelHandle._launch`, or inject the resolved `scistudio` location
explicitly. Either is a few lines and removes a class of confusion that will
otherwise be rediscovered as "the kernel is broken on my machine".

---

### I-1 — P1 — **inside** spec 4: `npm run lint` fails, and the failure is new

```
frontend/src/explore/regions/ExploreRegions.tsx
  62:10  error  'Placeholder' is defined but never used. Allowed unused vars must match /^_/u
✖ 72 problems (1 error, 71 warnings)
LINT_EXIT=1
```

`ExploreRegions.tsx` is added by this branch (+257, 0 deletions), so the error
cannot pre-exist on `origin/main`.

It is worth naming what `Placeholder` was. The file's own docstring calls it
"the seam between them: one placeholder component per region, each with the
props the real component takes, so an owner replaces a body here rather than
restructuring a layout they do not own." Every region was duly taken over by
its sub-track owner; the last one to land left the scaffold helper behind.
Assembly residue, and CI-blocking.

---

### I-2 — P1 — **inside** spec 5: `ruff format --check .` fails, and the failure is new

```
$ ruff format --check .
Would reformat: tests\contracts\test_workspace_focus_wire_contract.py
1 file would be reformatted, 999 files already formatted
exit 1
```

The diff is one assertion message that ruff wants on a single line
(`test_the_focus_rides_the_existing_active_context_channel`, ~line 133). The
file is added by this branch (+136, 0 deletions).

There is an irony worth recording rather than glossing: this is the one file
in the change written specifically to guard a seam — it compares
`WorkspaceFocusModel` (spec 5) against the TypeScript `WorkspaceFocusPayload`
(spec 4) by reading the `.ts` as text, precisely because "both can agree with
themselves while disagreeing with each other." It is a good test. It is also
the single file that fails the format gate.

**Note for whoever fixes it, and a disclosure.** `gate_record check` applies
this fix itself — when I ran it against my own ledger it reformatted the file
in my working tree. I reverted that edit before committing, because this audit
is read-only outside its report and carrying someone else's fix would have
erased the finding. The file on this branch is therefore still unformatted and
`ruff format --check` still exits 1, which is the state I am reporting.

---

### S-4 — P2 — **seam** (spec 4 ↔ spec 1): FR-036's mandatory end-to-end scenario does not exist

`docs/specs/adr-054-explore-frontend.md:514` — "**FR-036**: … one end-to-end
scenario MUST open a session from a block, run a cell, open a panel, emit a
cell from it, see a stale mark, run the stale set, and package."
Line 649 lists `frontend/e2e/specs/adr054-explore.spec.ts` as `create`.
Line 670 is task T-016. Line 758 is SC-014.

```
$ ls frontend/e2e/specs/
adr050-canvas-readability.spec.ts
system-flows.spec.ts

$ grep -rln "explore" frontend/e2e/
(no output)
```

A MUST requirement with a named task, a named file and a named success
criterion, absent with no deferral recorded in the spec.

I raise it above a bookkeeping gap because of what it would have exercised.
"Open a panel, **emit a cell from it**" is the one step that cannot be
satisfied by a hand-written descriptor: it needs a real producing panel
resolved by a real ladder. It is the exact scenario that would have failed
against S-1, and it is the scenario that was not written.

**In fairness — the gap was recognised, and a manual scenario was drafted for
it.** `docs/ai-developer/e2e/2026-09-05-adr054-explore-assembly.md` (364 lines,
added by this branch) is a `scistudio-e2e-test` scenario whose stated goal is
exactly this loop, and whose rationale is exactly the one this audit was
dispatched for: "no unit test proves it, because every piece of it was built by
a different agent against a different spec."

Two things keep it from closing FR-036. Its frontmatter says
`status: "draft"`, and its "## 7. Results (skill fills in)" section is empty —
the file ends at line 364 — so **it has never been run**. And it is a manual
browser scenario for a human-driven skill, not the automated Playwright spec
at `frontend/e2e/specs/adr054-explore.spec.ts` that FR-036, T-016 and SC-014
name.

It is also a prediction. Step by step it asks the operator to "open a panel
from the variable strip, have that panel emit code back into the notebook."
Per S-1, that step cannot succeed for any type SciStudio ships. Running this
scenario is the cheapest way to confirm S-1 independently of my analysis.

---

### S-5 — P2 — **seam** (spec 1 ↔ the ADR-048 addendum it required): the shim's removal condition describes a tree that does not exist

ADR-054 §9.4 is unusually firm: a compatibility shim without a removal
condition "is a second implementation with a friendly name", and the removal
must be "named in the ADR-048 addendum rather than left to a later judgement
call." `docs/adr/ADR-048-addendum1.md` §5 duly answers it in three clauses
"written to be settled by inspection so that the reading is not an argument."

Clause two (line 223) reads: "`src/scistudio/previewers/` holds only the
**four** alias modules and no logic".

```
$ ls src/scistudio/previewers/*.py | wc -l
14
```

`__init__.py` plus thirteen alias modules: `_raster`, `_table_cache`,
`assets`, `choices`, `data_access`, `fallbacks`, `helpers`, `models`,
`open_as`, `project`, `registry`, `router`, `session`. The package's own
docstring enumerates ten of them "alongside the three canonical author roots"
— thirteen, by its own count.

`ADR-048-addendum1.md:238` repeats "the four alias modules", as does
`src/scistudio/panels/compat.py:50`.

The condition was written against the plan (four) and the build came in at
thirteen; nobody reconciled them. Clause two is therefore unsatisfiable as
written, which returns the removal to exactly the "later judgement call" §9.4
exists to prevent. The fix is a number, but the thing being fixed is the one
guarantee that keeps the compatibility surface temporary.

---

### S-6 — P2 — **seam** (spec 4 ↔ spec 3): the frontend re-derives the runtime's version edges

ADR-054 is explicit that the runtime computes and the frontend draws.
`frontend/src/explore/GraphView.tsx:29-35` admits the exception in its own
docstring:

```
TODO(#2253): the version-edge derivation is duplicated from the backend's
  `_version_edges`, because `GraphResponse` publishes the cell-level edges
  and the changed sets but not the version edges themselves.
```

`buildVersionGraph` (lines 119-188) mirrors
`src/scistudio/explore/dependency_analysis.py:1125` `_version_edges`. The two
have **already diverged**: the backend `extend`s one `VersionEdge` per
(edge, reader-version) pair with no de-duplication; the frontend keys on
`(source, target, name)` and skips repeats (line 176). The visible result is
the same today; the second implementation is real and can drift further.

This is a **tracked** deferral — `TODO(#2253)` plus a follow-up register entry
— so it is not a gate failure under `AGENTS.md` §3.6. It is still a second
source for one truth, live in the tree, and the cheap end of the fix is one
field on `GraphResponse`.

---

### I-3 — P2 — **inside** spec 4: four declared test paths do not exist

`docs/specs/adr-054-explore-frontend.md` `tests:` frontmatter names paths that
are not there. I checked every `governs.files` and `tests` entry across
ADR-054 and all six specs programmatically; these are the only misses.

| Declared | Reality |
|---|---|
| `frontend/src/explore/SessionToolbar.test.tsx` | absent; coverage is `SessionToolbar.runControls.test.tsx` |
| `frontend/src/store/exploreSlice.test.ts` | absent; coverage is `frontend/src/store/__tests__/exploreSlice.test.ts` |
| `frontend/src/components/WorkflowCanvas.parts/useCanvasHandlers.test.ts` | absent; nearest is `WorkflowCanvas.parts/__tests__/exploreContextMenu.test.tsx` |
| `frontend/e2e/specs/adr054-explore.spec.ts` | absent, and never written — see S-4 |

The first three are renames; the coverage exists. The contrast with the
explore-session spec is instructive and to that spec's credit: it recorded
every rename and every dropped name in a `planned_governs` comment
(`PackagingReport`→`PackagingPlan`, `ExploreSessionRecord`'s move to
`core.lineage.record`, four test-file merges), specifically so that a reader
is not left to guess. The frontend spec did none of that.

Also, both `adr-054-explore-frontend.md` and `adr-054-panel-contract.md` still
list `frontend/src/App.parts/InteractiveModals.tsx` and
`InteractiveModals.parts/**` under `governs.files`, though both are deleted.
Both specs record the deletion in their body tables, so I read this as
governing the retirement rather than an error; noting it only so the next
frontmatter audit does not re-report it as a surprise.

---

### S-7 — P3 — **seam** (the unlanded sixth spec): the published docs still teach the retired form, with no notice in the docs

The dispatch asks me to be precise about gap versus defect. The **revision**
is a tracked gap: `adr-054-documentation.md` is the sixth spec and is not
implemented — nothing under `docs/package-development/`, `mkdocs.yml`,
`docs/architecture/` or `CHANGELOG.md` is in the diff — and two `TODO(#2211)`
markers record it.

What is a defect today is *where the markers are*. Both live in ADR addenda
(`ADR-048-addendum1.md:284`, `ADR-051-addendum2.md:279`). A package author
reading the guide sees nothing:

- `docs/package-development/previewers.md` still teaches `PreviewerSpec`,
  `FrontendManifest` and "the JS/CSS the inspector loads" (lines 31, 93, 119)
  — the ES-module form ADR-054 retires — with no deprecation notice in the
  file (`grep -n "2211\|ADR-054\|retired\|deprecated"` → nothing).
- `mkdocs.yml:32-33` publishes `scistudio.previewers.models` and
  `scistudio.previewers.data_access` as the API reference nav. Those are the
  **alias shim**. Neither `scistudio.panels.models` nor
  `scistudio.panels.data_access` appears in the nav.

So the shipped documentation site presents the compatibility shim as the
canonical author API, and ADR-054 §9.3's "one vocabulary" is not yet true
where authors read. Deferred is fine; deferred silently, on the surface a
package author is told to follow, is the part worth fixing early — a one-line
banner on `previewers.md` costs nothing and stops new panels being written
against a form scheduled for deletion.

Other retired things I searched by name and found **clean**: the interactive
modal (`InteractiveModals.tsx` / `.parts/` deleted, and
`frontend/src/hooks/useWebSocket.parts/dispatchEvent.test.ts:96-108` asserts
their absence and that `App.tsx` no longer references them); `dynamicPreviewer`
and `panelModuleLoader` (no source file, only prose in ADRs/specs); the second
API version (one constant). The three asset routes still registered —
`/api/panels/assets/…`, `/api/previews/assets/…`, `/api/blocks/panels/…` —
are one implementation behind three addresses, retained deliberately by FR-022
and documented as such at `panels.py:22-24`; that satisfies §9.1. The only
stale teaching reference I found outside the docs is
`docs/ai-developer/e2e/2026-08-22-lc-level-2-what-is-a-type.md:470`, which
diagnoses a bug in the now-deleted `DynamicPanel.tsx`; it is a dated session
record, so historical rather than instructional. Not a finding.

---

### I-4 — P3 — **inside** none: `eslint-config.test.ts` times out (pre-existing / environmental)

`src/__tests__/eslint-config.test.ts > loads the project flat config without
parser errors` — `Test timed out in 5000ms`, actual 11084 ms. Neither the test
nor `frontend/eslint.config.js` nor the vitest config is in the diff
(`git diff --stat origin/main...HEAD --` on all three returns nothing), so this
is a machine-speed failure independent of ADR-054. Recording it so the "1
failed" in the frontend run is not mistaken for a regression.

---

## 3. The layering, read as well as run

The dispatch warns that a rule relaxed to let a new subsystem compile is a
finding even when the suite is green. I diffed the rules themselves.

They were **strengthened**, not relaxed:

- `tests/architecture/test_layer_deps.py` (+489) adds the `explore` entry to
  `LAYER_RULES`, `test_engine_does_not_import_explore` (the other half of a
  one-directional rule), `test_explore_never_imports_upward_at_any_depth`
  (which walks function and class bodies, because the explore runtime defers
  imports inside functions by design), `test_explore_imports_are_allowlisted`
  (stdlib-only for the analysis and fingerprint), and
  `test_the_panel_contract_is_reachable_downward_from_every_consumer` — which
  exists precisely because the per-layer rules "would still pass if the
  contract were duplicated instead of shared."
- `pyproject.toml` renames the Previewers contract to Panels and **widens** its
  `source_modules` to `["scistudio.panels", "scistudio.previewers"]` so the
  shim cannot be used to satisfy the contract by the back door.
- Two new contracts, `Explore must not depend on api, ai, or engine` and
  `Engine must not depend on explore`. Their `ignore_imports` carve-outs are
  the same lazy AIBlock leaf edges already carved out in the Blocks, Engine and
  Workflow contracts — consistent, not new latitude.
- `tests/architecture/test_placement.py` adds `panels`, `previewers` and
  `explore` to the known-packages allowlist. Additive only.

`lint-imports`: 15 kept, 0 broken. `tests/architecture` + `tests/docs`: 625
passed. ADR-054 §9.2's placement requirement holds — the contract is in
`src/scistudio/core/panels.py`, `blocks/base/interactive.py:64` imports it
downward, and no upward import exists.

---

## 4. Contracts implemented consistently by more than one spec

Checked, and clean:

- **The session API's three callers.** The frontend goes over HTTP; the agent's
  session tools reach the **same `SessionService` instance** — `_RuntimeAdapter`
  in `api/app.py:158-182` answers `get_session_service()` from
  `explore.live_session_service(rt)`, which reads the same `_services`
  registry the routes act on (`routes/explore.py:108`). The crossing runs
  API→AI, not AI→API, which is what keeps the `AI must not depend on api`
  contract intact. Packaging is the same pair of module functions in both
  paths, called with the session's own marks, bindings and observations. One
  implementation, no second policy.
- **A block-declared panel must be producing**, checked at discovery (ADR §3.3)
  — enforced at `blocks/registry/_capability.py:340`, covered by
  `tests/panels/test_panel_capability_gate.py`.
- **Marks, kernel state and bindings are drawn, not computed.**
  `frontend/src/explore/CellMarks.tsx` filters the runtime's own array in the
  runtime's own vocabulary; `exploreSlice.ts:118-123` reads the `never_run`
  mark rather than inferring it. `ExploreKernelDisplayState` (`ui.ts:186`)
  collapses `state` + `needs_restart` into one value to draw — a presentation
  transform over two runtime facts, not a second computation. The one real
  second computation is S-6.
- **Deferrals.** Every `TODO`/`FIXME`/`XXX` added under `src/`,
  `frontend/src/`, `tests/`, `desktop/`, `skills/`, `docs/adr/` and
  `docs/specs/` cites an issue number: #1817, #2135, #2211, #2212, #2229,
  #2233, #2236, #2237, #2240, #2243, #2250, #2253, #2254. I found no untracked
  "later" / "for now" / "MVP" / "V1" deferral in code. (I could not check
  whether each cited issue is *open* — that would require `gh`, which my
  context limits forbid.)
- **Eleven built-in panels**, matching ADR §3.3's "today's nine previewers and
  two interactive panels", all `api_version: "1"`, all served through the one
  confined asset route.

---

## 5. What I could not check

- Whether the issues cited by the `TODO`s are open. Requires `gh`; forbidden.
- Whether the assembly's own gate ledgers declared the `governance_touch` and
  the core-change label that §2.1's guards ask for. `.workflow/records/**` is
  outside my context limits.
- Playwright e2e — there is no ADR-054 scenario to run (S-4), and the manual
  scenario that exists is unrun and out of my scope to run.
- Anything that would have required reading the issue, the checklist, the
  follow-up register, the PR, or another auditor's report.

---

## 6. Assessment

The pieces are good. The Explore session wire is the cleanest large wire I
have measured in this repository — 36 model/type pairs, zero drift. The
message vocabulary is genuinely one contract across four independently written
consumers. The layer rules were tightened rather than loosened, including a
test written specifically to catch the failure the ADR predicted. The agent
tools share the runtime's own session service instead of building a parallel
one. Someone wrote a cross-spec wire-contract test for the one channel two
specs split, and wrote down exactly why. That is not the profile of five
features that happen to compile together.

It is, however, not yet one feature. The thing that binds ADR-054's two halves
— a panel that produces, routed by the type of a notebook variable — has no
reachable path through the assembled product (S-1), the shared type describing
the catalogue that resolution reads has two incompatible descriptions (S-2),
and the end-to-end scenario that was supposed to walk that path was never
written (S-4). Those three are one story, and they are the story the seams
were supposed to be checked for.

The Python suite is otherwise genuinely green — one failure in the whole tree,
and it is S-3.

**Recommendation: `block`.**

Blocking, minimally:

1. **I-1** and **I-2** — two CI gates fail on this branch and pass on
   `origin/main`. One unused identifier and one line-length reflow. These are
   minutes of work and there is no argument for merging past them.
2. **S-1** — either ship a type-routed producing panel, expose the router's
   capability-aware resolution over HTTP, or record the absence as a tracked
   deferral and stop the strip silently mounting a viewer for a producing
   click. Running the drafted scenario in
   `docs/ai-developer/e2e/2026-09-05-adr054-explore-assembly.md` will confirm
   or refute this in one session, and is the cheapest next step.
3. **S-3** — absolutise `PYTHONPATH` when launching the kernel; the repository's
   own mandated dev invocation currently breaks the kernel bridge, and it is
   the only failing test in the suite.
4. **§2.1** — the assembled diff touches five protected-core files and five
   governance-critical files (`.github/workflows/ci.yml` and three under
   `docs/ai-developer/**`). Both obligations are CI-verified, so they will
   block regardless; the owner should confirm the label and the
   `governance_touch` declaration are in place rather than discovering them in
   a failing CI run.

Then `pass-with-fixes` on S-2, S-4, S-5, S-6, I-3 and S-7, none of which need
to hold the merge if they are tracked with the same discipline the rest of this
change has shown.

One closing note for whoever reads this next to the with-context audit. My
strongest finding (S-1) is one that reading the claim would have made harder to
see, not easier: every spec's own account of itself is accurate, every suite
that covers it is green, and the defect lives only in the space between two
correct statements. That space is what a no-context pass is for.
