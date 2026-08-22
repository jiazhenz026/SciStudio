# Audit: Learning Center Tutorial System And Shipped Core Levels (no-context)

- Date: 2026-08-22
- Persona: `audit_reviewer`, **no-context** mode
- Branch / worktree: `audit/lc-levels-no-context` @
  `C:/Users/jiazh/workspace/SciStudio-wt-lcA2`
- Audit surfaces: `src/scistudio/tutorials/**` (runtime, schema, and the six
  tutorials under `core/`), `src/scistudio/api/routes/tutorials.py`,
  `src/scistudio/api/routes/user_library.py`,
  `src/scistudio/api/routes/ai_pty/replay.py`, `src/scistudio/previewers/**`,
  `src/scistudio/core/dropins.py`, `frontend/src/components/LearningCenter*`,
  `frontend/src/components/promotion/**`, and the tests covering all of it.
- Judged against: `docs/specs/adr-053-learning-center.md` and `docs/adr/ADR-053.md`
  as committed in this tree, the published manifest schema
  (`src/scistudio/tutorials/schema/tutorial.schema.json`), and the product code
  the shipped tutorial copy makes claims about.

Per the dispatch I read no issue, no PR text, no dispatch prompt, no
`docs/planning/**`, no `docs/ai-developer/e2e/**`, no other auditor's report
under `docs/audit/`, no commit messages, and no chat or manager summary. I ran
no `git log`, `gh pr view`, or `gh issue view`. Everything below comes from
committed source, committed specs, and commands I ran myself.

**This audit is truncated.** The dispatch carried a stop condition: report
immediately on a P1 rather than continuing. P1-1 below was found early, so the
sweep stopped at the point recorded in §3 (Method). §3 states exactly what was
and was not covered so the next pass can resume rather than repeat.

**Recommendation: block.** P1-1 is a deterministic failure of the repository's
own test suite against the shipped artifact, on the default `pytest` invocation
with no marker or deselection protecting it.

---

## 1. Findings

### P1 — blocks release

#### P1-1. A shipped test fails deterministically: tutorial 3's runtime walk cannot start its own tutorial

**Evidence**

`tests/tutorials/test_core_tutorial_two_modalities.py::test_the_whole_tutorial_walks_through_the_real_runtime`
fails on a clean checkout of this branch:

```
$ PYTHONPATH=./src python -m pytest \
    "tests/tutorials/test_core_tutorial_two_modalities.py::test_the_whole_tutorial_walks_through_the_real_runtime" \
    -q --no-cov
...
src/scistudio/tutorials/session.py:713: TutorialUnavailableError
E   scistudio.tutorials.session.TutorialUnavailableError: tutorial
    'two-modalities-one-answer' cannot be started: needs the tutorial
    'what-is-a-type' from the same source to be completed first
```

The failing call is at `tests/tutorials/test_core_tutorial_two_modalities.py:961`:

```python
view = runtime.start(TutorialKey.core("two-modalities-one-answer"))
```

The cause is a collision between two committed facts that do not know about
each other:

1. `src/scistudio/tutorials/core/two-modalities-one-answer/tutorial.yaml:44-46`
   declares the FR-008 sibling prerequisite:

   ```yaml
   tutorials:
     - what-is-a-type
   ```

2. The test's runtime is built at
   `tests/tutorials/test_core_tutorial_two_modalities.py:890-899` with a
   progress store rooted at a throwaway home:

   ```python
   progress=ProgressStore(fake_home / ".scistudio"),
   ```

   That store is empty, so `what-is-a-type` is never recorded complete, so
   discovery marks `two-modalities-one-answer` unavailable, and
   `TutorialRuntime.start` refuses it at `src/scistudio/tutorials/session.py:711-713`:

   ```python
   if tutorial.unavailable_reason is not None:
       raise TutorialUnavailableError(key, tutorial.unavailable_reason)
   ```

The failure is environment-independent: the home directory is a `tmp_path`
monkeypatch (`Path.home` is stubbed at line 842), so no real `~/.scistudio`
can rescue it, and it reproduces in isolation as well as inside the full
`tests/tutorials` run. Nothing deselects it — `pyproject.toml:271` sets
`addopts = "-ra -q --cov=scistudio ..."` and the declared markers at
`pyproject.toml:281-285` (`requires_r`, `requires_fiji`, `serial`) are not on
this test.

**Failure scenario a real user could hit**

The user-facing half of the same collision is real and worse than the test
failure. `two-modalities-one-answer` is a *core* tutorial whose gate is another
core tutorial's completion, and the completion that clears the gate is recorded
in backend progress under `~/.scistudio` (FR-074, FR-075). Every documented way
of losing that file leaves the reader locked out of level 3 with level 2 already
done:

- FR-088's "clear tutorial progress" wipes progress *and* the tutorial
  projects. A reader who finishes levels 1–2, clears to reclaim disk, and comes
  back finds level 3 permanently unavailable, reading "needs the tutorial
  'what-is-a-type' from the same source to be completed first" — with level 2's
  own project deleted, so redoing it means redoing all twenty-odd steps.
- FR-062a explicitly contemplates the session store and the tutorial directory
  disagreeing ("a hand-deleted session file, a home directory restored from a
  backup without `~/.scistudio`"). The same divergence de-gates nothing and
  re-gates level 3.

Nothing in the spec sanctions a core level being unreachable in that state, and
`unavailable_reason` names only the prerequisite, not the recovery.

**Which side is wrong is a design call, not an audit call.** Two readings are
available and the repository does not decide between them:

- If the gate is intended, the test is stale and must seed the prerequisite
  into its `ProgressStore` before calling `start`.
- If the test is right, the manifest's `requires.tutorials` entry is the
  defect — and the other five shipped manifests support that reading. Both
  `what-is-a-type/tutorial.yaml:30-35` and `start-your-own-project/tutorial.yaml:29-35`
  carry a comment saying the opposite of what tutorial 3 does:

  > `# Deliberately no requires.tutorials entry: gating the core levels on each`
  > `# other is a track-integration decision, and a shipped core tutorial must be`
  > `# startable in the tree that ships it`
  > `# (test_core_tutorials.py::test_every_shipped_tutorial_is_startable_in_this_tree).`

  Tutorial 3 is the one core level that breaks that stated rule, and it is the
  one core level whose walk test fails. The named guard,
  `test_core_tutorials.py::test_every_shipped_tutorial_is_startable_in_this_tree`,
  passes — so whatever it asserts, it does not catch this.

Either way the tree ships red.

---

### P2 — should fix

#### P2-1. The summary level's block-taxonomy card contradicts every block the reader built

`src/scistudio/tutorials/core/scistudio-at-a-glance/assets/pages/block-six-kinds.md`
is the level-5 review card for what a block is. Two of its six lines are wrong
about the product, and both are wrong in the direction that misdescribes the
reader's own work:

```markdown
- **process** — ready-made processing blocks that ship with SciStudio.
- **code** — a Python function you write. Your custom blocks are these.
```

Verified against the code:

- `src/scistudio/blocks/registry/_spec.py:270-297` (`_infer_category`) resolves
  the category by walking the class hierarchy, `ProcessBlock -> "process"` and
  `CodeBlock -> "code"`.
- Every custom block the reader gains across levels 1, 2, 3, 4 and 6 subclasses
  `ProcessBlock` (or `IOBlock`, or `AIBlock`) — none subclasses `CodeBlock`:

  | Asset | Base class | Category |
  |---|---|---|
  | `welcome-to-scistudio/assets/code/normalize_fluorescence.py:20` | `ProcessBlock` | `process` |
  | `what-is-a-type/assets/code/segment_cells.py:72` | `ProcessBlock` | `process` |
  | `what-is-a-type/assets/code/review_labels.py:62` | `InteractiveMixin, ProcessBlock` | `process` |
  | `what-is-a-type/assets/code/load_tiff_image.py:98` | `SimpleLoader` (an `IOBlock`, `src/scistudio/blocks/io/simple_io.py:72`) | `io` |
  | `two-modalities-one-answer/assets/code/normalize_expression.py:96` | `ProcessBlock` | `process` |
  | `two-modalities-one-answer/assets/code/joint_region_profiles.py:140` | `ProcessBlock` | `process` |
  | `two-modalities-one-answer/assets/code/load_section_stack.py:128` | `IOBlock` | `io` |
  | `what-ai-can-do/assets/code/qc_outlier_filter.py:34` | `ProcessBlock` | `process` |
  | `what-ai-can-do/assets/code/summarize_metrics.py:20` | `ProcessBlock` | `process` |
  | `what-ai-can-do/assets/code/tutorial_ai_agent.py:52` | `AIBlock` | `ai` |
  | `start-your-own-project/assets/code/summarize_growth.py:26` | `ProcessBlock` | `process` |

  So "process = ready-made blocks that ship with SciStudio" describes the
  category the reader's own blocks actually land in, and "your custom blocks
  are `code`" describes a category none of them is in.

- `code` in the product is `CodeBlock`, which
  `src/scistudio/blocks/_templates/block_base_template.py:36` describes as "Run
  a project-local Python / R / Julia script" — a script runner, not "a Python
  function you write".

The same card opens with "Every block is one of six base kinds", which the
product also contradicts for the one path the tutorials teach the reader to
take. `block_base_template.py:193` scaffolds `class MyBlock(Block)` — a direct
`Block` subclass — and `_infer_category` has no branch for `Block`, so it
returns the seventh value:

```
$ PYTHONPATH=./src python -c "...; print(_infer_category(MyBlock))"
category for a plain Block subclass: unknown
```

`src/scistudio/blocks/registry/_spec.py:297` is the `return "unknown"` that
produces it.

**Failure scenario.** A reader finishes level 5 believing their
`normalize_fluorescence` block is a "code" block. They open the palette's
category grouping (`BlockPalette` groups by `base_category`) and find it filed
under process, next to Data Router. Level 5 is explicitly review — its licence
to be reading-only is that it "names and organises what the reader already did"
(`scistudio-at-a-glance/tutorial.yaml:4-7`) — so a wrong name here mislabels
work the reader has already done and can see on screen.

The card's closing line, "You have already used four of the six by hand", is
also unsupported by the shipped levels: by hand the reader places `io` (Load,
Save), `process` (their own blocks, Pair Editor) and `ai` (the level-4
`tutorial_ai_agent` node) — three. `code` and `app` appear only as prose in
level 6's `the-exchange-folder` step, and `subworkflow` appears nowhere.

---

### P3 — follow-up

#### P3-1. "The built-ins" names five of the nine blocks the palette actually ships

`src/scistudio/tutorials/core/scistudio-at-a-glance/assets/pages/block-built-ins.md`
introduces itself as the complete list — "The palette ships a small set on
purpose:" — names Load, Save, DataRouter, PairEditor and MergeCollection, and
closes "Everything else you will ever need is a block someone writes."

The registry ships nine:

```
$ PYTHONPATH=./src python -c "from scistudio.blocks.registry import BlockRegistry; \
    from scistudio.blocks.registry._scan import _scan_builtins; \
    r=BlockRegistry(); _scan_builtins(r); \
    [print(tn, r.get_spec(tn).base_category) for tn in sorted(r.all_specs())]"
AI Agent      ai
App Block     app
Code Block    code
Data Router   process
Load          io
Merge Collection process
Pair Editor   process
Save          io
Sub-Workflow  subworkflow
```

`src/scistudio/blocks/registry/_scan.py:152-164` is the registration list. The
four omitted entries — AI Agent, App Block, Code Block, Sub-Workflow — are
exactly the four kinds the adjacent `block-six-kinds.md` card describes, so a
reader who looks at their palette while reading these two cards sees the
product name four things the "built-ins" card told them do not ship.

#### P3-2. "The six core types" is seven tiles in the Data types tab

Level 2's first step tells the reader to look at the tab and enumerates what is
there (`what-is-a-type/tutorial.yaml:60-65`):

> "look at the Data types tab on the left: these are the kinds of thing
> SciStudio can hold. Array, Series, DataFrame, Text, Artifact, CompositeData"

and level 5's `type-six-core.md` repeats it as a closed set ("why there are
exactly these six"). The registry registers seven and the route does not filter
any of them:

```
$ PYTHONPATH=./src python -c "from scistudio.core.types.registry import TypeRegistry; \
    r=TypeRegistry(); r.scan_builtins(); print(sorted(r.all_types()))"
['Array', 'Artifact', 'CompositeData', 'DataFrame', 'DataObject', 'Series', 'Text']
```

`src/scistudio/core/types/registry.py:586-593` registers `DataObject` alongside
the six; `src/scistudio/api/routes/types.py:313-322` (`list_types`) maps
`type_registry.all_types().values()` straight through with no exclusion; and
`frontend/src/components/TypePalette.tsx` / `TypePalette.parts/*` carry no
`DataObject` filter. The reader is told to count the tiles on a step whose
entire purpose is "the gap is seen, not announced" and finds an unnamed
seventh.

Either the copy should account for `DataObject` (the base, not a shape you
hold) or the tab should hide it. Both fixes are small; leaving them apart makes
the one step in the course that asks the reader to verify a claim against the
screen the one step where the screen disagrees.

#### P3-3. Level 6's import step narrates a copy it does not perform

`start-your-own-project/tutorial.yaml:82-99`. The step text says:

> "Press the button below and we will copy everything from incoming-example/
> into data/raw/ for you."

The trigger copies from the tutorial's own assets, not from the project
directory the sentence names:

```yaml
trigger:
  label: Copy my files into data/raw
  do:
    - copy:
        source: assets/data
        destination: data/raw
```

The two are byte-identical today because the bootstrap populated
`incoming-example/` from the same `assets/data` (lines 41-49), so the observable
result matches the promise. It stops matching the moment the reader touches
`incoming-example/` — deleting or editing a file there, which is a natural thing
to do in a step about moving your own files around, leaves the button producing
the pristine originals while claiming to have moved what was in the folder. The
step's `done_when` checks only that both filenames exist in `data/raw`
(lines 95-99), so the divergence is never caught.

---

## 2. Verified And Found Sound

These were checked and hold. They are listed so the next auditor does not
re-derive them.

**Test surfaces that pass.** Everything except P1-1:

- `tests/api/test_tutorial_routes.py`, `tests/api/test_tutorial_project_visibility.py`,
  `tests/api/test_tutorial_replay.py`, `tests/api/test_tutorial_library_write.py`,
  `tests/api/test_tutorial_package_lifecycle.py`, and all of `tests/packages/`
  — 148 passed, 0 failed.
- `tests/tutorials/` — all but P1-1 pass. Four skips, all self-explaining and
  legitimate: `test_core_tutorials.py:248,266` ("this tutorial ships no code
  assets"), `:361` ("no project blocks"), and `test_manifest_schema.py:538`
  ("symlink creation is not permitted in this environment" — a Windows
  privilege skip, not a coverage gap on other platforms).
- Frontend: `LearningCenter.test.tsx`, `tutorialAutoAdvance.test.tsx`,
  `tutorialProjectOpens.test.tsx`, `tutorialTargets.test.tsx`, and
  `LearningCenter.parts/__tests__` — 11 files, 157 tests, all passing.

**Tutorial copy that the code confirms.**

- *Restore restores the whole recorded tree, and does not run.*
  `scistudio-at-a-glance/assets/pages/history-restore.md` — consistent with
  ADR-053 spec A-007 as committed, which records ADR-038 Addendum 1 widening
  Restore from one workflow YAML to the run's full recorded tree and adding
  advisory input/environment checks that warn without blocking.
- *Plots live in the preview cache and are not version-controlled.*
  `plot-tips` / `start-your-own-project`'s `export-or-lose-it` and
  `two-modalities`' `draw-it` all name `.scistudio/previews/`;
  `src/scistudio/plot/runtime.py:46,60` defines `_PREVIEW_ROOT = ".scistudio/previews"`
  and the `<workflow_id>/<node_id>/<output_port>/<plot_id>/` layout the spec's
  FR-047 quotes for `plot_rendered`.
- *`data/` and `.scistudio/` are gitignored, which is why a branch switch leaves
  a stale figure.* `two-modalities`' `git-stores-the-recipe` step; confirmed by
  `src/scistudio/core/versioning/gitignore_template.py:24-33`, whose
  `DEFAULT_GITIGNORE` excludes exactly those two directories with the same
  reasoning.
- *What a plot's `render` receives.* `plot-collection.md` names
  `collection.types`, `collection.items`, `.open()` and `.open_one()`;
  all four exist at `src/scistudio/plot/_harness.py:332,350,357,374` and are
  the API the scaffold documents at `src/scistudio/plot/scaffold.py:49-54`.
- *Previewers follow types, the lookup walks up the type chain, and the closest
  tier wins: project > user > package > core.* `previewer-typed.md`; confirmed
  by `src/scistudio/previewers/router.py:14-18,54,104-117`, whose documented
  order is exactly "project parent, user parent, package parent, core base
  fallback" with `_TIER_ORDER` at line 54. This is also the mechanism level 2's
  `numbers-not-pictures` step depends on (Image has no previewer, Image is an
  Array, the Array previewer answers) — the step is describing real behaviour,
  not a staged one.
- *Six base block kinds exist as a closed set in the product.* True as a set —
  `_infer_category` returns one of `io | process | code | app | ai | subworkflow`
  (`_spec.py:270-297`). It is only the per-kind descriptions and the `unknown`
  seventh return that are wrong (P2-1).
- *`paireditor_block` is the right identifier for Pair Editor.* `PairEditor`
  declares no `type_name`, so `_type_name_for_class` (`_spec.py:299-305`)
  derives `paireditor_block` — which is what
  `two-modalities-one-answer/tutorial.yaml` names in `node_exists`,
  `edge_exists` and `highlight`. Verified by running the derivation.
- *The rename that breaks level 1 really does deregister the block.*
  `welcome-to-scistudio/assets/code/normalize_fluorescence_renamed.py:35`
  changes `type_name` to `normalise_fluorescence`, so the
  `restore-what-broke` step's `block_registered: {block_type: normalize_fluorescence}`
  is genuinely false on entry and genuinely becomes true on Restore. The step
  is not auto-satisfied.
- *Level 4's workflow overwrite preserves the reader's threshold.* The
  `one-more-trick` step overwrites `workflows/main.yaml` with
  `assets/workflows/main-with-metadata.yaml`, which carries
  `sigma_threshold: 2` (line 28) rather than the original `3`
  (`assets/workflows/main.yaml:27`) — so the decision the reader made two steps
  earlier survives the overwrite. The asset's own header comment says this is
  deliberate.

**Contract points that hold between the spec and the schema.**

- FR-010's `steps` xor `driver`, FR-007a's `manifest_version`, FR-008's
  `requires.tutorials`, FR-011's `pages`/`trigger`/`title`, FR-011b's
  `prefill`, and FR-061b's `replay.segments[].do` all appear in
  `schema/tutorial.schema.json` with the FR citations attached, and the schema
  deliberately does *not* restate the vocabulary
  (`conditions.VOCABULARY`), the replay surfaces (`actions.REPLAY_SURFACES`),
  the highlight targets (`manifest.HIGHLIGHT_SPECS`), the prefill targets
  (`manifest.PREFILL_SPECS`) or the route targets (`manifest.ROUTE_TARGETS`) —
  each is declared in exactly one place as FR-041/FR-061a/FR-089b require, with
  the schema pointing at it by dotted path.
- FR-020a's restricted destination set is a single named constant,
  `actions.EXECUTED_PROJECT_PATHS`, referenced by both the spec text and
  `manifest.py`'s module docstring, and `manifest.EXECUTABLE_ASSET_DIRS`
  matches the four asset directories the FR names.
- The `ai_chat`/`history` naming mismatch between `ROUTE_TARGETS` and the
  frontend's `BottomTab` union is documented in place
  (`manifest.py:161-186`) rather than left to be rediscovered as a bug.

---

## 3. Method — And What This Pass Did Not Cover

**Covered.**

1. Read `docs/specs/adr-053-learning-center.md` end to end (FR-001…FR-094,
   SC-001…SC-014, A-001…A-008) and the published manifest schema.
2. Read all six shipped `tutorial.yaml` manifests in full and the level-5
   reading pages for blocks, types, previewers, plots and history.
3. Cross-checked every factual claim in those pages and manifests that names a
   product fact, against the code that owns the fact — block categories, the
   built-in palette set, the core type set, the previewer resolution order, the
   plot render API and cache location, the gitignore contents, the `type_name`
   derivation for Pair Editor, and the level-1 rename.
4. Ran, in the foreground:
   - `python -m pytest tests/tutorials -q` (full),
   - `python -m pytest tests/api/test_tutorial_*.py tests/packages -q --no-cov`,
   - `npx vitest run` over the five Learning Center frontend test paths,
   - ad-hoc `python -c` probes against `BlockRegistry`, `TypeRegistry` and
     `_infer_category` to enumerate what the product actually registers.
5. Confirmed P1-1 reproduces in isolation and is not marker-deselected, by
   reading `pyproject.toml:271,281-285`.

**Not covered — resume here.** The stop condition ended the sweep before these:

- **Driving the tutorial API against a live backend.** No `serve` process was
  started and no session was driven over HTTP. Everything above about step
  satisfaction is read from the manifests and from the runtime code, not
  observed end to end. In particular, the auto-satisfied-step question is only
  partly answered: `what-is-a-type`'s `make-it-image` step self-documents that
  its `type_registered` condition is "typically already true here"
  (`tutorial.yaml:73-79`), which FR-054 permits and FR-054a defuses by
  requiring an explicit continue — but no other step was checked for the same
  shape by observation.
- **`src/scistudio/api/routes/user_library.py` and `ai_pty/replay.py`** were
  listed as surfaces and not read. In particular `library_contains`'s three
  `kind` values (`block`, `type`, `previewer`) against what the promotion
  routes actually write, which level 2's last three steps depend on
  (`save-the-type`, `save-the-block`, `save-the-previewer`).
- **`frontend/src/components/promotion/**`** was not read.
- **Tier and containment violations** (FR-020, FR-020a) were confirmed only as
  far as "the constants exist and are single-sourced"; no adversarial manifest
  was constructed to test the rejection paths beyond what
  `tests/tutorials/test_tier_asset_rules.py` already asserts.
- **Frontend/backend contract parity** on `UI_EVENT_SPECS`, `HIGHLIGHT_SPECS`,
  `PREFILL_SPECS` and `ROUTE_TARGETS` was not compared element by element
  against the frontend's `targets.ts` / `prefill.ts`; the parity tests pass, but
  I did not verify that they cover every member.
- **`replay` `continue_tab` semantics** (FR-061b, "an error when no replay tab
  is open") were not exercised. Level 4 uses `continue_tab: true` on eight of
  its nine replay actions.

**Environment note.** `frontend/node_modules` was absent in this worktree; I
created a directory junction to the main checkout's copy so the frontend tests
could run. That junction is untracked and outside the write set — it should be
removed if the worktree is kept.
