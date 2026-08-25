---
title: "Audit — Learning Center levels track (with-context)"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 53
  - 42
related_specs:
  - adr-053-learning-center
language_source: en
---

# Audit — Learning Center levels track (with-context)

Audit mode: **with-context** (agent A1, `audit_reviewer` persona).
Subject: `track/learning-center-levels` @ `c00bb197c`, the candidate for the
final PR closing #2061 #2062 #2063 #2066 #2075 #2079 #2081 #2082 #2083 #2084
#2085 #2086 #2088 #2089.
Audit branch: `audit/lc-levels-with-context`.
Gate ledger: `.workflow/records/2081-lc-levels-with-context.json`.

**Verdict: block.** One P1 fails CI on the candidate as it stands. Eleven P2
findings follow, most of them shipped reader-facing copy that is confidently
wrong about the product — including one manager-supplied "corrected fact" that
is itself wrong and is recorded in the checklist Drift Log.

## 1. Findings

### P1 — blocks the final PR

#### P1-1. `c00bb197c` breaks the level-3 walkthrough test; CI fails on the candidate

`tests/tutorials/test_core_tutorial_two_modalities.py:961` calls
`runtime.start(TutorialKey.core("two-modalities-one-answer"))`. Since
`c00bb197c` added `requires.tutorials: [what-is-a-type]` to
`src/scistudio/tutorials/core/two-modalities-one-answer/tutorial.yaml:50-51`,
`TutorialsService.start` refuses it at
`src/scistudio/tutorials/session.py:712-713`:

```
scistudio.tutorials.session.TutorialUnavailableError: tutorial
'two-modalities-one-answer' cannot be started: needs the tutorial
'what-is-a-type' from the same source to be completed first
```

Reproduced on the tip:

```
PYTHONPATH=./src python -m pytest tests/tutorials tests/api/test_public_surface.py \
  tests/api/test_tutorial_routes.py tests/api/test_tutorial_library_write.py \
  tests/api/test_user_library_write.py tests/api/test_tutorial_project_visibility.py \
  tests/api/test_tutorial_replay.py tests/api/test_registry_provisioning_parity.py \
  tests/api/test_registry_reload_symmetry.py tests/previewers -q -p no:randomly
=> 1 failed, everything else passed
FAILED tests/tutorials/test_core_tutorial_two_modalities.py::test_the_whole_tutorial_walks_through_the_real_runtime
```

`git diff c00bb197c^ c00bb197c -- tests/tutorials/test_core_tutorial_two_modalities.py`
is empty: the commit updated `tests/tutorials/test_core_tutorials.py` for the new
gate but not the level-3 end-to-end walkthrough, which is the one test that
actually starts the session.

Why the test's own environment does not save it: the walkthrough builds
`TutorialRuntime(..., environment=DiscoveryEnvironment(scistudio_version="0.3.1",
git_available=True), progress=ProgressStore(fake_home / ".scistudio"))`
(`tests/tutorials/test_core_tutorial_two_modalities.py:890-896`). Because an
environment **is** injected, `TutorialsService.discover()`
(`src/scistudio/tutorials/session.py:633-636`) skips the `#2088` branch that
states the runtime's own progress store, and `completed_tutorials` stays `None`
— so the prerequisite is judged against a store the test never writes to.

Production is not affected: `src/scistudio/api/routes/tutorials.py:1132-1141`
constructs `TutorialRuntime` with neither `environment` nor `progress`, so the
`#2088` branch runs and the runtime's store is the one consulted. Verified by
probe — a clean install lists tutorial 3 unavailable naming `what-is-a-type`,
and stating tutorial 2's key as completed clears it and re-discovers it as
startable.

**Failure scenario:** the final PR's CI job runs the tutorials suite and fails.

**Note for the fix (secondary, worth a follow-up issue):** the failure exposes a
real seam, not only a stale test. `TutorialRuntime` accepts an `environment`
*and* a `progress` store and reconciles neither; injecting an environment for an
unrelated reason (pinning a version, stating git availability) silently moves
the source of prerequisite truth to a probe of the default `ProgressStore()`.
`discover()`'s own docstring names this hazard ("the two must be the same store,
or a test's progress and a test's catalogue would disagree about what is
unlocked") but the constructor does not enforce it. A `DiscoveryEnvironment`
built by `TutorialRuntime` should inherit `completed_tutorials` from the
runtime's progress store when the caller left that field unstated.

### P2 — fix before completion

#### P2-1. `c00bb197c` removed the assertion that made a prerequisite deadlock impossible

`tests/tutorials/test_core_tutorials.py:440-470` dropped
`assert tutorial.is_startable` from
`test_every_shipped_tutorial_is_startable_in_this_tree` and states every shipped
tutorial as completed. The new companion,
`test_a_prerequisite_is_the_only_thing_that_may_hold_a_core_tutorial_back`,
`continue`s past any startable tutorial and, for the rest, only checks that the
required id is *shipped*.

Neither test constrains the prerequisite **graph**. A core tutorial that
requires itself — or two that require each other — is shipped-and-unreachable
and passes both.

Verified empirically against real discovery (probe replaying both tests'
assertions over an in-memory mutation that makes `two-modalities-one-answer`
require itself; no file was modified):

```
--- self-requirement (deadlock)
  new test 1 (startable-in-this-tree, progress stated): PASS
  new test 2 (prerequisite-only holdback):              PASS
  removed assertion (every tutorial startable):         FAIL: two-modalities-one-answer is discovered but not startable
```

**What the change got right:** the version-specifier defect the original
docstring describes is still caught. `completed_tutorials` only short-circuits
`requires.tutorials`; `unmet_requirement`
(`src/scistudio/tutorials/discovery.py:340-362`) still evaluates packages, the
`scistudio` specifier, `agent`, and the git term against the stated
environment. The reasoning that a prerequisite is a different kind of
unavailability from an unrunnable installation is sound.

**What it lost:** reachability. The fix is one added assertion — every core
tutorial must be reachable by completing prerequisites in some order (the
prerequisite graph is a DAG over shipped ids and closes), which is what
`assert tutorial.is_startable` was implicitly buying.

**Failure scenario:** an author adds level 7 and copy-pastes
`requires.tutorials` from level 3 without changing the id, or a two-level track
gates each on the other. Both tests are green; a first-time reader opens the
Learning Center and can never start the level, with a card telling them to
finish a level they cannot reach.

#### P2-2. The main merge reverted main's Windows coverage of the symlink-escape test

`d17cb5a68` resolved `tests/tutorials/test_manifest_schema.py` to the track's
side. Main's `#2075` fix (`4345232e7:tests/tutorials/test_manifest_schema.py:536`)
used `tests.helpers.link_to_directory`, which falls back to a Windows
**directory junction** when the symlink privilege is missing — `os.path.realpath`
follows a junction identically, and a real-path comparison is exactly how the
loader detects the escape, so the case stays covered. The track's version
(`tests/tutorials/test_manifest_schema.py:532-538`) probes for the symlink
privilege and `pytest.skip`s when it is absent.

The two are **not** semantically identical. On the tip, the run reports:

```
SKIPPED [1] tests\tutorials\test_manifest_schema.py:538: symlink creation is not permitted in this environment
```

`tests/helpers.py:29` is present in the tree (it arrived with the merge) and is
still used by `tests/api/test_user_library_write.py:228,257` — only this call
site lost it. Merging the track back into main therefore un-fixes part of
#2075: the tutorial asset symlink-escape security test goes back to skipping on
a default Windows dev machine and CI agent, and a skip is green.

(The other #2075 test-file resolutions **are** equivalent and were verified:
`tests/tutorials/test_replay.py:75-76` uses `write_bytes` where main used
`write_text(..., newline="")`; `tests/tutorials/conftest.py:53-56` keeps
`newline=""`; `tests/api/test_tutorial_routes.py:30,297` and
`tests/api/test_tutorial_project_visibility.py:24,285` both use `_rmtree_force`,
imported from the `scistudio.api.runtime` re-export rather than
`scistudio.api.runtime._helpers`. `tests/api/test_user_library_write.py:210`
skips on both sides — it needs a *file* symlink, which no junction can stand in
for.)

#### P2-3. Level 6 tells the reader to press a control that does not exist

`src/scistudio/tutorials/core/start-your-own-project/tutorial.yaml:293`:

> Export is the only way a figure survives: press Export on the plot card
> and save it somewhere of yours.

Two facts are wrong:

- The **plot card** in the Plots tab
  (`frontend/src/components/BottomPanel.parts/PlotsTab.tsx:257-321`) offers
  `Edit plot code`, `Delete plot`, `Run plot`, and `Relink data source`. There
  is no export or save control on it.
- The control is in the **Preview pane**, on `PlotViewer`
  (`frontend/src/components/DataPreview.parts/PlotViewer.tsx:264-272`,
  `data-testid="plot-export-button"`), and its visible label is **`Save`**,
  with a format select beside it (`aria-label="Save format"`).

This lands on a step that judges nothing (`export-or-lose-it` has no
`done_when`), so nothing corrects the reader.

**Failure scenario:** the reader is told to press Export on the plot card, opens
the Plots tab, finds four buttons and no Export, and the only thing the product
will accept from them is Continue. Correct copy: the previous step's Run already
put the figure in the Preview pane; press **Save** there and choose a format.

`assets/pages/plot-tips.md:8` ("**Export is the only way a figure survives.**")
and `scistudio-at-a-glance/tutorial.yaml:90` ("preview only, export to keep")
use "export" as a concept rather than a control name; they are defensible but
reinforce a name the UI does not use.

#### P2-4. Level 3 asks the reader to press a button and tick a box that are not in the dialog it names

`two-modalities-one-answer/tutorial.yaml:212-218` (step `they-do-not-line-up`):

> Drag the rows in one list until each row holds the same section on both
> sides, then **Apply**. Before you do, tick **"Remember my choice and skip this
> dialog"** …

- The Pair Editor's footer
  (`frontend/src/components/PairEditorModal.tsx:188-196`) renders exactly two
  buttons: `Cancel` and **`Confirm`**. "Apply" appears nowhere in the modal —
  it is the label on tutorial *2*'s own hand-written panel
  (`what-is-a-type/assets/panels/review_labels/panel.mjs:78-82`), carried across
  to a different, core-registry dialog. The same error repeats at
  `tutorial.yaml:418` ("line the sections up once more and Apply").
- "Remember my choice and skip this dialog" exists in exactly one place,
  `frontend/src/components/BottomPanel.parts/ConfigPanel.tsx:364` — the selected
  block's **Config panel**. It is not in the modal, and the modal is
  `fixed inset-0 z-[9999]` (`PairEditorModal.tsx:126-129`), so the Config panel
  is unreachable while the dialog is paused. The instruction "Before you do,
  tick …" cannot be carried out at all.

**Failure scenario:** the reader hunts a full-screen modal for a checkbox and a
button neither of which exist, and ends up pressing Confirm without the
interaction memory the next two steps assume they set. Tutorial 2 states the
same fact correctly (`what-is-a-type/tutorial.yaml:357-360`: an interactive
block's *settings* carry it), so the correct copy already exists in the track:
tick it in the block's settings **before pressing Run**.

#### P2-5. Level 3 names a menu that does not hold the action the step judges

`two-modalities-one-answer/tutorial.yaml:253-254` (step `read-the-source`):
"Open the Segment Cells node's menu and choose View source."

The canvas node's floating toolbar
(`frontend/src/components/nodes/BlockNode.parts/NodeActionToolbar.tsx:47-62`)
holds `Run block` and `Remove block`; its only `trailing` slot is
`PromoteToLibraryAction` ("Move to My Library",
`frontend/src/components/nodes/BlockNode.tsx:177`). There is no canvas context
menu. "View source" is a **top-toolbar** button
(`frontend/src/components/Toolbar.parts/WorkflowGroups.tsx:84-91`) that acts on
the *selected* node.

The step's `done_when` (`ui_event: block_source_viewed`) is satisfiable — but
only through a surface the prose never names.

**Failure scenario:** a judged step that will not advance until the reader
finds, by themselves, a control the instruction points at the wrong place.

#### P2-6. Level 2 enumerates six core types where the product shows seven

`what-is-a-type/tutorial.yaml:60-63`: "look at the Data types tab on the left:
these are the kinds of thing SciStudio can hold. Array, Series, DataFrame,
Text, Artifact, CompositeData — **every one of them**." And
`tutorial.yaml:126-127`: "open the core_type list — your own Image is in it,
alongside **the six core types**."

`src/scistudio/core/types/registry.py:587-596` registers **seven** builtins:
`DataObject`, Array, Series, DataFrame, Text, Artifact, CompositeData.
`src/scistudio/api/routes/types.py:311-323` lists every registered spec with no
filter, and `TypePalette.parts/__tests__/typeModel.test.ts:144` explicitly
expects `"DataObject"` in the Core section. On the `core_type` enum,
`src/scistudio/blocks/io/_config_enrichment.py:35-40` ends with
`ordered.extend(sorted(registered - set(ordered)))`, which appends `DataObject`
too.

This is the same class as the palette built-in count the track already corrected
(five, not six) — a confident enumeration the reader can falsify by looking at
their screen.

#### P2-7. Level 3's `.gitignore` claim is numerically wrong

`two-modalities-one-answer/tutorial.yaml:477-480`: "a new project's .gitignore
excludes **two directories** on purpose: data/ … and .scistudio/ …".

`src/scistudio/core/versioning/gitignore_template.py:23-49` excludes **seven**
directory patterns — `data/`, `.scistudio/`, `__pycache__/`, `*-venv/`,
`*.venv/`, `.idea/`, `.vscode/` — plus four file patterns. The two named
directories and the reasons given for them are right; only the count is false,
and it is the kind a reader checks by opening the file the step just told them
git version-controls.

#### P2-8. The palette ships **nine** built-ins, not five — and the track contradicts itself about it

This one starts upstream of the levels. The checklist Drift Log
(`docs/planning/learning-center-levels-checklist.md:284`) records as a corrected
fact that "palette built-ins are FIVE (SplitBlock excluded in
registry/_scan.py:134-137, alongside MergeBlock)". **The exclusion is real; the
count is not.** `src/scistudio/blocks/registry/_scan.py:153-164` registers nine:
`LoadData`, `SaveData`, `AIBlock`, `SubWorkflowBlock`, `CodeBlock`, `AppBlock`,
`DataRouter`, `MergeCollection`, `PairEditor`. `MergeBlock`/`SplitBlock` are
excluded *on top of* those nine, not out of a set of six.

Level 5's `assets/pages/block-built-ins.md:3-16` lists five (Load, Save,
DataRouter, PairEditor, MergeCollection) and closes:

> Everything else you will ever need is a block someone writes — you, the AI,
> or a package.

AI Agent, Code Block, App Block, and Sub-Workflow are shipped built-ins that
nobody writes. And the track already contains the correct answer: tutorial 4's
own replay transcript,
`what-ai-can-do/assets/replay/02-list-blocks.txt:4-14`, prints all nine and says
"**Nine**, in this project: the core palette."

**Failure scenario:** a reader finishes level 4 watching the agent enumerate
nine built-ins, then reads level 5 — the level whose entire job is to be the
reference — being told there are five and that the other four are third-party.
The Drift Log entry should be corrected in the same pass, because it is the
record later work will trust.

#### P2-9. Level 5 has `process` and `code` inverted — the reader's own blocks are `process`

`scistudio-at-a-glance/assets/pages/block-six-kinds.md:7-8`:

> - **process** — ready-made processing blocks that ship with SciStudio.
> - **code** — a Python function you write. **Your custom blocks are these.**

`_infer_category` (`src/scistudio/blocks/registry/_spec.py:285-296`) tests
`issubclass(cls, ProcessBlock) -> "process"` before
`issubclass(cls, CodeBlock) -> "code"`. Every custom block the track teaches
subclasses `ProcessBlock` and therefore lands in **`process`**:
`welcome-to-scistudio/assets/code/normalize_fluorescence.py:20`,
`what-is-a-type/assets/code/segment_cells.py:72`,
`what-ai-can-do/assets/code/qc_outlier_filter.py:34`,
`start-your-own-project/assets/code/summarize_growth.py:26`. `code` is
`CodeBlock` — "run project-local scripts through typed file exchange"
(`src/scistudio/blocks/code/code_block.py:181,216`) — an *external script*
driven through `data/exchange`, which level 6 describes correctly at
`start-your-own-project/tutorial.yaml:239-242`. The two levels contradict each
other.

The same page closes "You have already used **four of the six** by hand"
(`block-six-kinds.md:13`). Across levels 1-4 the reader touches `io`,
`process`, and (in level 4, placed by the scripted agent rather than by hand)
`ai`. No `CodeBlock`, `AppBlock`, or `SubWorkflowBlock` appears anywhere in
levels 1-4.

**Failure scenario:** the summary level teaches the reader the wrong name for
the category their own four blocks are in, on the page that exists to give them
the vocabulary — and then the palette groups those blocks under a heading the
page told them means something else.

#### P2-10. Level 6 misdescribes the data buckets it is built to teach

`start-your-own-project/tutorial.yaml:75-76`: "data/zarr, data/parquet, and
data/artifacts are the system's stores — named for how a payload is persisted,
**filled during runs**". And `:212-213`: "**data/zarr and data/parquet is where
each block's output is persisted, each type in the store built for it.**"

`_derive_output_dir` (`src/scistudio/engine/runners/local.py:112-124`) sends
**every** block's output to `<project>/data/zarr/<workflow_id>/<block_id>`,
whatever the type. `src/scistudio/core/lineage/retention.py:3-5` states it
outright, and `Block.persist_table`
(`src/scistudio/blocks/base/block.py:644-651`) writes a DataFrame's `.parquet`
file *inside* that `data/zarr` path. `src/scistudio/api/project_layout.py:37-39`
documents `data/parquet` as "explicitly saved tables" and `data/artifacts` as
"opaque files"; nothing writes to either during a run — the only other
references are a read-only MCP walker (`ai/agent/mcp/tools_qa.py:319`) and
`SaveData` resolving a user-chosen path (`local.py:284`).

**Failure scenario:** level 6 is the geography level. The reader is told which
folder to look in for a run's output, looks in `data/parquet`, and finds it
empty. There is no per-type split to find.

#### P2-11. Two more "press X" instructions in level 6 name controls that do not exist

- `start-your-own-project/tutorial.yaml:124-125`: "Leave core_type as DataFrame
  and **set format to CSV**." The Load block has no `format` setting.
  `LoadData.config_schema` (`blocks/io/loaders/load_data.py:155-167`) declares
  only `core_type`; `enrich_io_config_schema`
  (`blocks/io/_config_enrichment.py:82-96`) adds `path` and makes the required
  set `["path", "core_type"]`. Format is derived from the extension by
  `_detect_format`/`_LOAD_EXTENSION_MAP` (`load_data.py:171-188`). Secondary:
  the field's UI title is **"Type"**, not `core_type`
  (`_config_enrichment.py:87`).
- `start-your-own-project/tutorial.yaml:123`: "press **Browse**". There is no
  button captioned Browse; it is an icon button with
  `title="Browse filesystem"`
  (`frontend/src/components/BottomPanel.parts/ConfigField.tsx:199`).

Both sit inside `point-load-at-your-file`, a judged step
(`config_matches` on `load_data`'s `path`).

### P3 — follow-up

#### P3-0. Smaller content inaccuracies in the same class

None of these strand a reader, but all are checkable and wrong:

- `two-modalities-one-answer/tutorial.yaml:358` — "Press **New** in the Plots
  tab". The button reads **"New plot"**
  (`frontend/src/components/BottomPanel.parts/PlotsTab.tsx:198-209`, and the
  empty state at `:215-217` quotes the same label).
- `what-is-a-type/tutorial.yaml:175-176` — "**sixty lines** of standard
  library". `assets/code/load_tiff_image.py:55-95` is 41 lines (≈55 counting
  its tag tables), and it is not purely stdlib: `:95` is `np.frombuffer`.
  The sibling claim about the hand-built PNG (`struct` + `zlib` + `base64`) *is*
  genuinely stdlib and is correct.
- `two-modalities-one-answer/tutorial.yaml:79-80` — "a few hundred measured
  positions per section". The generator
  (`tests/tutorials/test_core_tutorial_two_modalities.py:142-145`,
  `np.arange(2, 96, 4)` meshgridded) yields 576 rows per sheet; the guard test
  only bounds it `100 <= n <= 999`.
- `two-modalities-one-answer/tutorial.yaml:281-282` — "two standard methods,
  **twenty lines each**". `assets/code/normalize_expression.py:61-66` is 6 lines
  of body; `:69-93` is ~25.
- `two-modalities-one-answer/tutorial.yaml:419-420` — "one section has no third
  cluster at all". The `[14, 8, 5]` half is recomputed
  (`test_core_tutorial_two_modalities.py:106,619-630`); the per-section half is
  covered nowhere — `test_the_right_method_gives_three_of_each_cluster_on_every_section`
  (`:633-645`) is parametrized only over `(1, "total_count")` and
  `(2, "median_ratio")` and never crosstabs `(2, "total_count")`. The file's own
  standard (`tutorial.yaml:24-25`: "Every number quoted in a step below is
  recomputed from the shipped assets by tests/…") is not met for this one.
- `start-your-own-project/tutorial.yaml:256` and
  `two-modalities-one-answer/tutorial.yaml:358` — "Press **New**" in the Plots
  tab; the button reads "New plot".
- `start-your-own-project/tutorial.yaml:290-292` and
  `scistudio-at-a-glance/assets/pages/plot-tips.md:6-7` — a plot figure is
  "overwritten on the next run". `_clear_current_artifacts` is called only from
  `run_plot_job` (`src/scistudio/plot/runtime.py:637`); a *workflow* run never
  touches the preview cache. In level 6 the sentence follows two steps after
  "Press Run", so the reader will read it as the workflow run.
- `scistudio-at-a-glance/assets/pages/plot-what-it-is.md:8-9` — "run the
  workflow again and the figure redraws from the new data". Plots are never
  scheduled and never auto-render; `run_plot_job` is reached only from the plot
  route and the Plots-tab Run button (`PlotsTab.tsx:80`). The same tutorial's
  `plot-tips.md:5-6` says the opposite and is correct ("A plot is not part of
  the workflow graph, is never scheduled").
- `scistudio-at-a-glance/assets/pages/block-built-ins.md:12-13` —
  MergeCollection has "as many input ports as you need". The cap is 8
  (`blocks/process/builtins/merge_collection.py:63,66`).
- `scistudio-at-a-glance/assets/pages/type-canonical-zone.md:5-8` — "what the
  run records is which capability read it — a stable id". Nothing records it by
  default: neither `LoadData` nor `SaveData` declares `capability_id` in
  `config_schema`, it is only read opportunistically
  (`savers/save_data.py:303`), and the lineage schema has no capability column
  anywhere (`core/lineage/store.py:200-278`). The UI states the precondition —
  "choose one to persist a stable capability_id"
  (`BottomPanel.parts/FormatCapabilityConfig.tsx:27`). The page's own
  two-packages-both-handle-`.csv` example is exactly the case where nothing
  distinguishing is recorded.
- `scistudio-at-a-glance/assets/pages/others-ask-the-ai.md:5-6` — the agent can
  "create types and previewers". Blocks, plots, and workflows each have MCP
  authoring tools and a shipped skill; types and previewers have neither
  (`ai/agent/mcp/tools_authoring.py`, `src/scistudio/_skills/scistudio/`). A CLI
  agent could write the raw files, but the sentence implies a parity the product
  does not provide.
- `scistudio-at-a-glance/assets/pages/others-ask-the-ai.md:3` — "the **AI
  tab**"; the tab is labelled "AI Chat"
  (`BottomPanel.parts/TabBar.tsx:29`), which every other level uses.
- `scistudio-at-a-glance/assets/pages/workflow-running.md:6-7` — "**Run from
  here** … the restart control on a node is this". The mechanism is right
  (`useWorkflowExecutionActions.ts:203` calls `executeFrom`) but the node
  control is captioned "Run block"
  (`nodes/BlockNode.parts/NodeActionToolbar.tsx:47-48`); no control anywhere is
  named "Run from here".
- `scistudio-at-a-glance/assets/pages/block-built-ins.md:5` — "Load and Save —
  the only two IO blocks". True of built-ins, but the reader authored a third
  and fourth `io` block in levels 2 and 3
  (`what-is-a-type/tutorial.yaml:166-171`,
  `two-modalities-one-answer/tutorial.yaml:67-68`), both of which register in
  the palette under "This Project" with `base_category = "io"`.
- `start-your-own-project/tutorial.yaml:149,301-302` — the project's own tools
  live in "blocks/, types/, and previewers/". The project drop-in set is four:
  `tutorials/` is the fourth (`api/project_layout.py:55-60`,
  `core/dropins.py:225-238`).

#### P3-1. The prerequisite message shows a slug, and the level-5/6 copy assumes a level the catalogue now locks

On a clean install the catalogue is: 1 startable, 2 startable, **3 unavailable**,
4 startable, 5 startable, 6 startable (verified by probe against real discovery).
`TutorialDetail.tsx:107-109` renders `unavailable_reason` verbatim:
"needs the tutorial 'what-is-a-type' from the same source to be completed first"
— a slug plus an authoring phrase ("from the same source") in reader-facing text.

Meanwhile levels 5 and 6, both open on a clean install, assert the reader has
already done the locked level:
`scistudio-at-a-glance/assets/pages/history-branches.md:4` ("You did this in
level 3"), `library-what-it-is.md:6-7` ("level 3 reused the Image type you built
in level 2"), `history-tips.md:5`, `start-your-own-project/tutorial.yaml:230`
("back in level 3"). This is soft (the reader continues, mildly confused) where
level 3's was hard (a judged step that could never be satisfied), so the
manager's scoping is defensible — but the asymmetry is now structural and
reader-visible, and either gating 5/6 or softening the copy would close it.

#### P3-2. `export-or-lose-it` ships an unjudgeable ask with no tracked follow-up

`UI_EVENT_SPECS` (`src/scistudio/tutorials/conditions.py:264-269`) holds exactly
four names: `preview_expanded`, `block_source_viewed`, `node_selected`,
`plot_rendered`. There is no `plot_exported`/`plot_saved`, so the level 6 step
genuinely cannot be judged today and its copy says so ("We cannot check this one
for you"). That is honest, but `UI_EVENT_NAMES`' own docstring describes exactly
how the set grows ("a new member is only meaningful once the frontend reports
it, so adding one requires a matching frontend change in the same breath"), and
the emitter site is two lines away from the Save handler. Per AGENTS.md §3.6 this
belongs in a tracked `TODO(#NNN)` rather than only in prose.

#### P3-3. Reading pages are served with a guessed media type

`_page` (`src/scistudio/api/routes/tutorials.py:1633-1652`) resolves a page by
**stem** — any extension matches — and returns
`FileResponse(resolved, media_type=mimetypes.guess_type(...) or "text/plain")`.
`assets/pages/` is deliberately not in `EXECUTABLE_ASSET_DIRS`
(`src/scistudio/tutorials/manifest.py:142`), so a **user- or project-tier**
tutorial may ship one; `assets/pages/intro.html` or `intro.svg` would then be
served as `text/html` / `image/svg+xml` from the app origin at a stable,
guessable URL.

Not an active vector: `fetchTutorialPage`
(`frontend/src/lib/api/learningCenter.ts:366-372`) reads `.text()` and
`ReadingSurface.tsx:219` hands it to `PageMarkdown`, which emits text nodes only
and never parses HTML. Nothing in the product navigates to the URL. Hardening:
pin the page response to `text/markdown`/`text/plain` regardless of extension,
or restrict the pages directory to `.md`.

#### P3-4. The only recorded e2e verdict predates the integrated tip by nine commits

`docs/ai-developer/e2e/2026-08-21-lc-level-1-regression.md:120` records
**PASS** at `track/learning-center-levels @ 7ec90e8ec`. That commit is *before*
`d17cb5a68` (which brought in the activity-bar layout #2106 and previewer choice
#2110, both of which touch the Learning Center surface), before tutorial 2
(PR #2122), before tutorial 3 (PR #2130), and before `c00bb197c`. The level-5 and
level-6 scenario files are `status: draft` with Section 7 unfilled; levels 2, 3,
and 4 have no scenario file. Checklist §11 already carries these as unticked, so
this is a statement of the evidence gap rather than a claim of drift.

#### P3-5. Level 5 declares no `requires` block

`scistudio-at-a-glance/tutorial.yaml` has no `requires:` at all, where every
other level declares `scistudio: ">=0.3.1"` with the comment "Same floor as the
other levels". It is a reading level and makes no API claim, so the omission is
harmless — but it is the one level whose version floor the shipped-startability
test can never exercise.

## 2. What was verified and found sound

### 2.1 The three manager-made changes

**`d17cb5a68` (the origin/main merge) — sound apart from P2-2.**
Recomputed the auto-merge with `git merge-tree --write-tree` and diffed it
against the commit: the manual resolutions touch exactly
`previewers/__init__.py`, `tutorials/actions.py`, `tutorials/conditions.py`, and
the five #2075 test files, and nothing else. All three source resolutions are
correct unions:

- `src/scistudio/previewers/__init__.py:114-137` keeps P2's tutorial-scoped
  wording *and* `load_user_previewers(registry, project_dir)` *and* #2110's
  `registry.set_previewer_choices(load_choices(project_dir))` paragraph and call.
- `src/scistudio/tutorials/actions.py:343-352` keeps main's
  `"""The scripted material, delivered in order."""` *and* P1's `continue_tab`
  field with its comment.
- `src/scistudio/tutorials/conditions.py:1004-1012` keeps main's
  `@provisional(since="0.3.4")` *and* P1's `entered_at` parameter and
  `_TIME_SCOPED_TERMS`.

Cross-checked the auto-merged files for the same class of silent loss. Every
line either parent added is present in the result except known-good
supersessions (`previewer_scan_dirs` gaining `library_root_for_project`,
`load_user_previewers` gaining `project_dir`, `UserLibraryTarget` gaining
`"previewers"`, `tutorial_library_tier_dirs` gaining the previewers root). A
decorator-integrity sweep over every `.py` in the merge — comparing each
decorated symbol's decorator set in main against the merge result — reports
exactly one loss, `DeclaresConditions` losing `@provisional`, which is finding 2
below. The same sweep against `HEAD` and against both parents reports nothing.

**`83eea9880` (the `@provisional` restoration) — correct and complete.**
`src/scistudio/tutorials/driver.py:513-515` restores
`@provisional(since="0.3.4")` on `DeclaresConditions` while leaving it on P1's
new `DeclaresTriggerActions` (`driver.py:495-497`), which is where git had
misfiled it. `tests/api/test_public_surface.py` passes at the tip. The
decorator sweep above is the answer to "did the same class of loss happen
anywhere else the frozen-surface test would not catch": it did not.

**`c00bb197c` (tutorial 3's prerequisite) — the mechanism is right, the tests
are not (P1-1, P2-1).**
The product side is correct and was verified against real discovery rather than
read:

- `unmet_requirement` builds the sibling key as
  `TutorialKey(source_kind=str(manifest.source_kind), source_id=<same source>,
  tutorial_id=required_id)` (`discovery.py:352-362`), which matches
  `DiscoveredTutorial.key` exactly for core
  (`TutorialKey(source_kind='core', source_id='', tutorial_id='what-is-a-type')`).
- On a clean install tutorial 3 is unavailable naming `what-is-a-type`; stating
  tutorial 2's key completed clears it and re-discovery reports it startable.
- The premise holds: tutorial 3's judged steps name `segment_cells` and the
  `Image` type, which only tutorial 2 puts in the scoped library, and tutorial
  2's promoting steps 19/20/21 (`save-the-type`, `save-the-block`,
  `save-the-previewer`) all carry `done_when` — so a completion of tutorial 2
  cannot be reached without those artifacts existing.
- The class is correctly scoped to one level. Levels 4 and 6 consume only blocks
  they ship themselves (`qc_outlier_filter`, `summarize_metrics`,
  `tutorial_ai_agent`; `summarize_growth`), so no other level has the same latent
  dead end.
- Restart does not re-lock a downstream level: `_discard`
  (`session.py:984-1004`) deletes the project and the session record but never
  touches `ProgressStore`, so completing 2 then restarting 2 leaves 3 reachable.
  "Clear tutorial data" deletes progress *and* the scoped library together
  (`routes/tutorials.py:1549-1567`, `progress.py:323-329`), so the two cannot
  disagree.

### 2.2 Level content and vocabulary

- **Continue-only steps, counted and challenged.** welcome-to-scistudio 4/16
  (unchanged by this track — `git diff` over its directory is empty, so the
  byte-identical claim holds), what-is-a-type 2/22, two-modalities-one-answer
  2/20, what-ai-can-do 2/14, scistudio-at-a-glance **0/8**,
  start-your-own-project 6/16. Every continue-only step in levels 2, 3, 4 is an
  opening or closing narrative beat with nothing to judge. Level 5, the reading
  level, judges all eight steps — the strongest FR-054a showing in the track.
  Of level 6's six, four (`welcome`, `the-project-is-a-folder`,
  `the-four-buckets`, `the-exchange-folder`) are genuine reading cards and
  `your-own-project` is the closing beat; the sixth, `export-or-lose-it`, asks
  for an action the vocabulary cannot express — see P2-3 and P3-2.
- **FR-020a holds.** `EXECUTABLE_ASSET_DIRS` is
  `{code, panels, replay, workflows}` (`manifest.py:142`), and `pages` is
  correctly outside it: a reading page is content, and `PageMarkdown`
  (`frontend/src/components/LearningCenter.parts/PageMarkdown.tsx`) renders it as
  React text nodes with no `dangerouslySetInnerHTML` and no HTML parsing, so a
  user- or project-tier page cannot script the surface. All five new tutorials
  are core-tier, so their `assets/code`, `assets/replay`, `assets/panels`, and
  `assets/workflows` trees are permitted.
- **FR-070/FR-071 hold.** `previewer_scan_dirs`
  (`core/dropins.py:435-447`) routes the user tier through
  `library_root_for_project`, which returns `tutorial_library_dir()` only for a
  path under the tutorial parent and `user_library_dir()` otherwise, including
  the no-project case (`dropins.py:354-369`). `load_user_previewers`
  (`previewers/project.py:91-105`) reads the root off `previewer_scan_dirs(...)[-1]`
  rather than recomputing `~/.scistudio/previewers`, and registers as
  `OwnerKind.USER` — so the scoped library rides the user-tier slot and the
  precedence stays project > user > package > core with no fourth tier.
  `tutorial_scan_dirs` deliberately does **not** apply the swap
  (`dropins.py:417-432`), which is what keeps a user's own tutorials visible
  while a tutorial runs. `tests/tutorials/test_scoped_library.py` and
  `tests/api/test_registry_provisioning_parity.py:678-695` pin both halves and
  pass.
- **Level content facts that hold.** The manager-corrected baselines are all
  honoured by the shipped copy: previewer resolution is project > user >
  package > core with the parent-chain walk (`previewers/router.py:14-16,98-107`,
  `registry.py:18-19`); `tifffile` is a dev-only extra
  (`pyproject.toml:68`, absent from `[project].dependencies`) and level 2's TIFF
  loader reads the baseline contract with `struct`; plots are preview-only,
  cached under `.scistudio/previews/<wf>/<node>/<port>/<plot>/` and never a
  workflow node (`plot/runtime.py:9,56-72`, `api/routes/plots.py:24`), with the
  render script at `plots/<plot_id>/render.py` (`plot/scaffold.py:184,228-249`).
  Also verified: the dispatch error quoted verbatim
  (`blocks/io/_unified_dispatch.py:338`); `SimpleLoader` as an `IOBlock`
  registering exactly one `(Image, "tiff", .tif/.tiff)` capability;
  `ui_color`/`ui_ring_color` existing, hex-validated, and colouring ports; Pair
  Editor's variadic 2-8 inputs, zero initial ports, `+` rails and
  `AddPortDialog` `port_N` names (`blocks/process/builtins/pair_editor.py:80-96`);
  `paireditor_block` as the `type_name`; the xlsx fan-out label
  `"run1_counts.xlsx — S01"` including the em dash
  (`blocks/io/loaders/load_data.py:299-318`); interaction memory keyed on
  per-port item labels so a new file re-asks
  (`blocks/base/interactive.py:322-341`); branch create-then-switch with
  checkout auto-commit and workflow reload-from-disk
  (`Git/BranchPicker.tsx:126-127`, `store/gitSlice.ts:327-359`); "Move to My
  Library" on all three surfaces including `previewers/`
  (`promotion/promotable.ts:107-122`); block-source tabs read-only
  (`store/tabSlice.parts/fileTabActions.ts:280`); the "Data types" and "Logs"
  tab labels; every `route_to`/`highlight`/`prefill` target used by levels 2 and
  3 being in `LearningCenter.parts/targets.ts`; and the recomputed numerics
  (7 objects / 6 cells / 9-px speck at (16,103) / 73 adaptive / 6 rows;
  12 genes; 9 regions per section; 27 regions; 9-9-9; 14-8-5; 7-18-2;
  S05/S09/S01 vs S01/S05/S09).
- **Test suite.** Everything under `tests/tutorials`, `tests/previewers`, and the
  nine tutorial/registry API test modules passes at the tip except P1-1.
  `tests/api/test_public_surface.py` is green.

## 3. Recommendation

**Block** the final PR until P1-1 is fixed. Every P2 should land in the same
pass:

- P2-1 is one added assertion.
- P2-2 is a regression against `main` that this merge carries back.
- P2-3 to P2-11 are shipped reader-facing copy that is wrong about the
  product. Five of them (P2-3, P2-4, P2-5, P2-11, and the `core_type` half of
  P2-6) point the reader at a control that is not where the step says it is,
  and three of those sit on **judged** steps, where the reader cannot proceed by
  ignoring the copy. P2-8 additionally needs the checklist Drift Log entry
  corrected, because that entry is the record later work will trust.

Two facts the levels get right that are worth keeping visible while fixing the
above: level 5 judges all eight of its steps, the strongest FR-054a showing in
the track; and tutorial 4's replay transcript is the one place in the track that
states the built-in count correctly.

P3 items are follow-up issues.
