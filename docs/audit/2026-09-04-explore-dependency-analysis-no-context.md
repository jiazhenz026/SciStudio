# Audit: ADR-054 Notebook Dependency Analysis (`scistudio.explore`) — no-context

- Date: 2026-09-04
- Persona: `audit_reviewer`, `no-context` mode
- Branch / worktree: `audit/2231-no-context` @
  `C:/Users/jiazh/workspace/SciStudio/.worktrees/s2-e1-audit-nc`
- Change under review: `git diff origin/main...HEAD -- src tests`
  (`origin/main` = `43e9313f2`, merge base = `cae11210c`, head = `42fd9a53c`);
  21 files, 8650 insertions, 1 deletion.
- Judged against: `docs/specs/adr-054-notebook-dependency-analysis.md`,
  `docs/adr/ADR-054.md` §6.1–§6.2, and the repository's own architecture and
  governance tests.
- Environment: Windows 11 26200, CPython 3.13.12.

Per the dispatch I did not read the owner request, any GitHub issue, any
planning checklist under `docs/planning/adr-054-spec2-*`, any dispatch prompt
other than my own, any PR text, any commit message, or any ledger under
`.workflow/records/`. The diff was read with `git diff origin/main...HEAD`
restricted to `src` and `tests`. Every claim below rests on the spec text, the
source tree, or a command I ran myself.

## 0. What I Actually Ran

| Command | Result |
|---|---|
| `pytest tests/explore tests/architecture/test_layer_deps.py -q --no-cov` | 430 collected, **all pass** |
| `pytest tests/architecture -q --no-cov` | all pass (1 pre-existing skip in `test_registries.py`) |
| `pytest tests/qa/test_architecture_drift.py tests/qa/test_audit_*drift*.py tests/qa/test_audit_frontmatter_lint.py tests/qa/test_audit_signature_contracts.py tests/adr052_contract tests/qa/test_governance_paths.py tests/stability tests/docs` | all pass (pre-existing skips only) |
| `ruff check src/scistudio/explore tests/explore` | All checks passed |
| `ruff format --check src/scistudio/explore tests/explore tests/architecture` | 28 files already formatted |
| `mypy src/scistudio/explore` | Success, 3 files |
| `mypy tests/explore` | Success, 6 files |
| `python scripts/deferral_scan.py` | exit 0; 47 untracked word-matches repo-wide, 2 of them new in `explore/` (benign prose) |
| `sentrux scan .` / `sentrux check .` | **unavailable** — not on `PATH`, and `python -m sentrux` reports no such module |
| **Mutation testing: 57 behavioural mutations across two rounds** | **47 killed, 10 survived** (§1) |
| Targeted measurement scripts (fingerprint extent, cost bounds, tokeniser fallback fuzz) | see §2–§4 |

### 0.1 Method

I did not audit by reading. The primary technique was mutation testing: each
mutation was written into `src/scistudio/explore/*.py`, the whole of
`tests/explore` plus `tests/architecture/test_layer_deps.py` was run, and the
file was restored. Fifty-seven mutations were applied in two rounds. The working
tree was verified clean (`git status --short` empty) after each round.

Forty-seven mutations were killed. That is a genuinely strong suite — the ten
weakest points below were found only because the mutations were aimed at the
sentences the code's own docstrings claim, not at arbitrary operators.

## 1. Headline

The implementation is careful, the test suite is unusually good, and every
functional requirement I could exercise is met. **Nothing here is a P1.**

What I found is concentrated in two places: **claims that are not measured by
the thing that says it measures them**, and **documentation inside the tests
that describes a product state that no longer exists**. Both are the kind of
defect a with-context auditor is least likely to catch, because the surrounding
materials assert the opposite.

Recommendation: **pass-with-fixes**.

## 2. Findings — P2

### P2-1 — `xxhash` is a third-party import that FR-003, FR-035 and SC-011 forbid, and SC-011's named measurement cannot see it

**Observed.** `src/scistudio/explore/fingerprint.py:217-227` imports `xxhash`
inside `_new_hasher`. `xxhash>=3.4` is a declared dependency
(`pyproject.toml:27`), so nothing breaks at runtime.

The spec disagrees with itself about whether that is allowed:

- **FR-003**: "The analysis MUST depend on the standard library only."
- **FR-035**: "The analysis and fingerprint modules MUST import from the
  standard library and, lazily and only inside the fingerprint, **numpy and
  pandas**." — a closed allowlist that does not name `xxhash`.
- **SC-011**: "The two modules import nothing from SciStudio beyond stability
  markers and **nothing third-party except numpy and pandas** lazily inside the
  fingerprint. **Measured by the architecture layer test.**"
- **§4.1 "Fingerprints by type"**: "Arrays hash their bytes through the
  `xxhash` dependency SciStudio already carries".

The code follows §4.1 and the tests entrench it:
`tests/explore/test_fingerprint.py:668` asserts
`{"numpy", "pandas", "xxhash"} <= lazy`, i.e. the suite *requires* the import
FR-035 and SC-011 exclude.

**And the criterion is not measured.** SC-011 names the architecture layer test
as its measurement. `tests/architecture/test_layer_deps.py:259-288`
(`test_explore_imports_are_allowlisted`) says in its own docstring that
`_get_imports_from_file` "collects **module-level** imports only — it never
descends into a function body — so an import written lazily inside the
fingerprint … is invisible here **by construction**." So the test that SC-011
points at is structurally incapable of checking the half of SC-011 that says
"nothing third-party except numpy and pandas". A fourth lazy third-party import
added tomorrow would pass every check in this change.

**Fix:** amend FR-003/FR-035/SC-011 to name `xxhash` (§4.1 already assumes it),
and either point SC-011 at
`tests/explore/test_fingerprint.py::test_fr035_numpy_and_pandas_are_imported_inside_functions`
— which does inspect function bodies — or extend the layer test with a
lazy-import allowlist so the criterion has a measurement that can fail.

### P2-2 — Ten tests and two module docstrings assert defects the shipped code does not have

**Observed.** `tests/explore/test_adversarial_analysis.py:29-34` states: "the
ones that **fail** carry a `FINDING` line in the first sentence of their
docstring … They are left failing on purpose: a fix agent owns the repairs, and
a test that is skipped, xfailed, or softened to pass is a finding that has been
filed and closed in the same motion."

Nothing in that file fails. All 64 tests pass; all 430 tests in scope pass.
`tests/explore/test_analysis_differential.py:20` likewise says "Two fixtures are
here because they **fail**." Both pass.

Verified individually — all eight `FINDING` tests in
`test_adversarial_analysis.py` pass (`8 passed, 56 deselected`), as do both
`FINDING P1` tests in `test_analysis_differential.py`.

Of those ten, **seven carry docstrings that are now factually false about the
code**, in the present tense, and three of the seven say "I believe the product
is wrong":

| Test | Docstring claim | Actual code |
|---|---|---|
| `test_fr006_a_global_augmented_assignment_inside_a_function_is_a_module_read` (P1) | "`_collect_module_level_reads` … walks only the module level and never enters the function body"; "That fixture's differential test fails alongside this one" | `dependency_analysis.py:802-819` walks every `def`/`class` and collects `global` names; the fixture's test passes |
| `test_fr006_a_global_del_inside_a_function_is_a_module_read` (P2) | "missed for the same reason" | not missed |
| `test_fr012_a_cell_holding_an_unpaired_surrogate_is_flagged_rather_than_raising` (P2) | "`analyse_cell` … says it never raises. It does." | `source_hash` encodes with `surrogatepass` (`dependency_analysis.py:487-500`); it does not raise |
| `test_fr016_every_version_edge_source_is_a_version_node` (P3) | "`_version_edges` builds a source node for it anyway … I believe the product is wrong" | `build_graph` publishes `unknown_versions` nodes (`dependency_analysis.py:1171-1181`); no dangling source |
| `test_fr025_a_container_above_the_bound_is_sampled_across_its_full_extent` (P1) | "The function computes `step = length // keep` and then truncates … I believe the product is wrong and the fix is one line" | `_sample_step` already uses `ceil` (`fingerprint.py:342-344`) and there is no truncation |
| `test_sc003_global_counter_slice_reproduces_the_notebook` (P1) | "its backward slice omits the cell that initialises the counter, and running the slice raises `NameError`" | slice is correct; test passes |
| `test_sc003_wrapped_operator_slice_reproduces_the_notebook` (P1) | "The continuation line `    % count` is such a line, so it is removed" | FR-011 and the code are both tokeniser-based now; the read survives |

`test_the_wrapped_operator_read_is_lost_without_a_flag` is worse than stale: its
**name** asserts the read is lost while its body asserts
`"count" in facts.read` — the opposite.

That the drift is an oversight rather than a convention is provable from the
same file: `test_fr011_a_magic_line_inside_a_string_literal_is_left_alone`
(line 671) *was* rewritten — "The finding above, closed" — with its assertions
inverted and its narrative updated. The other seven were not.

**Why this is P2 and not cosmetic.** Anyone reading this suite — a reviewer, a
release checklist, the next agent — is told there are four open P1 defects, one
of which is a `NameError` in a packaged block's slice. There are none. This is
the single most misleading artefact in the change.

**Fix:** rewrite the seven docstrings the way
`test_fr011_a_magic_line_inside_a_string_literal_is_left_alone` was rewritten;
rename `test_the_wrapped_operator_read_is_lost_without_a_flag`; correct both
module docstrings. The three docstrings that say "documented rather than failed"
(`test_fr024_a_large_set_…`, `test_fr015_a_read_only_the_cell_itself_binds_…`,
`test_fr027_two_cells_with_identical_source_…`) are accurate and should stay.

### P2-3 — For dicts and sets, FR-025's "fixed strides across its full extent" holds in neither half, and nothing tests it

**Observed.** Two mutations survived the whole suite:

- `N01`: replace the strided dict/set sample with a plain prefix
  (`islice(iterator, keep)`) → **suite still green**.
- `M01`: replace `_sample_step`'s `ceil` with `floor` → **suite still green**.

Direct measurement (`container_items = 512`), mutating the **last** element:

```
  n= 1024  list=True  tuple=True  dict=False
  n= 1536  list=True  tuple=True  dict=False
  n= 2048  list=True  tuple=True  dict=False
```

A change to the last-inserted entry of a 1024-entry dict is **never** observed.
Lists, tuples, arrays, frames, strings and byte buffers all take an explicit
tail (`_stride_indices` appends `length - 1`; `_digest_ndarray` feeds
`flat[-1:]`; `_digest_values` feeds `values.iloc[-1:]`; `_digest_text` feeds
`obj[-1]`). `_sampled_entries` (`fingerprint.py:591-604`), the dict/set path,
does not. It also still uses the `length // keep` floor step that
`_stride_indices`' own docstring (`fingerprint.py:314-340`) explains at length is
the wrong formula.

The same floor step breaks the count half of the bound:

```
  list n= 1000: nodes=  502   stride indices=  501 (bound 512+1)
  dict n= 1000: nodes= 2001   (bound ~1024)
  dict n= 2000: nodes= 1335   (bound ~1024)
```

A 1000-entry dict walks and digests all 1000 entries where `container_items`
declares at most 512.

The module docstring (`fingerprint.py:32-38`) makes the guarantee globally:
"above it, the content is sampled at fixed strides *across its full extent* —
**first element to last** — together with its shape, dtype, and length". That is
true of every container path except the two this finding is about.

§4.5 admits a *stride* that skips positions; it does not admit a path that never
looks at the final entry, and `_stride_indices`' docstring says the extent
property "holds literally". It does not hold for `dict` or `set`.

**Fix:** give `_sampled_entries` the same treatment `_stride_indices` got —
`ceil` step and an explicit final entry — and add the dict/set rows to whatever
test covers the list/array/frame tails.

### P2-4 — `test_a_shell_line_the_tokeniser_cannot_read_is_still_stripped` does not exercise the clause it names

This is the classic shape: an assertion weaker than the coverage it claims.

**Observed.** Mutation `N14` deletes FR-011's error-recovery fallback entirely
(`_magic_line_numbers` no longer calls `_textual_magic_lines` after a tokeniser
error) — **the suite stays green**, including
`test_a_shell_line_the_tokeniser_cannot_read_is_still_stripped`
(`tests/explore/test_dependency_analysis.py:648-658`), whose docstring says "Every
physical line from there on is classified textually".

Its input is `"df = load()\n!cat it's-a-file\npeaks = find(df)\n"`. The `!` is
the first token of its logical line, so the **lexical** pass already marks line 2
before the tokeniser reaches the apostrophe. The textual fallback contributes
nothing, and the test passes whether or not it exists.

I fuzzed 960 permutations of tokeniser-breaking lines, magic lines and code
lines to find inputs where the fallback is load-bearing; **60 differ**. The
smallest:

```python
# source
"df = 1\n!cat it's-a-file\n%pip install x\n"
#   shipped      : assigned=['df'],  flags=[]
#   fallback gone: assigned=[],      flags=['syntax_error']
```

Two magic lines, the first of which stops the tokeniser: the second is only
removed by the textual fallback. FR-011's final clause is real and correct in the
code; it is simply not covered.

**Fix:** add the two-magic-line case above as a test.

### P2-5 — `build_graph` adds a second exemption to FR-015 that the spec does not authorise

**Observed.** FR-015: "A read with no enabled definer above it MUST be recorded
as unresolved, **except that** a read of a name in Python's builtins namespace
draws no edge and is not recorded as unresolved." One exception.

`dependency_analysis.py:1149-1161` adds a second: a read of a name in the
*reading cell's own* changed set is silently skipped. The test that documents it
(`test_fr015_a_read_only_the_cell_itself_binds_is_not_reported_unresolved`) shows
the consequence: a first cell reading `df = df.dropna()` raises `NameError` the
moment it runs, and FR-021's unresolved list — which US2 scenario 5 exists so
that packaging can refuse such a notebook — stays silent about `df`.

The same test also demonstrates that the justification written in the code
comment ("every `import pandas as pd` cell would report `pd` unresolved") is
false: `analyse_cell("c1", "import pandas as pd").read == frozenset()`.

The behaviour may well be the right trade-off — telling `df = df.dropna()` from
`total = 0; total += 1` needs the statement order FR-001 forbids — but the spec
was not amended and the code comment's stated reason does not hold. Spec and code
disagree on a MUST.

**Fix:** owner decision, then either FR-015 gains the exception (with the real
justification, not the `import pandas as pd` one) or FR-001 gains a narrow
within-cell rule.

### P2-6 — SC-010's five hundred milliseconds is applied to the cheap half; the expensive half gets an undeclared two-second ceiling

**Observed.** SC-010: "**Analysing** a generated notebook of five hundred cells,
each assigning and reading a few names, **builds the graph** in under five
hundred milliseconds on the CI runner."

Both timed tests bound `build_graph` alone:

- `tests/explore/test_dependency_analysis.py:1362-1378` — `elapsed < 0.5` around
  `build_graph` only.
- `tests/explore/test_adversarial_analysis.py:1269` — `build_ms < 500.0`, then
  `analyse_ms + build_ms < 2000.0`.

Measured on this machine for the 500-cell generated notebook:

```
SC-010: analyse 61.5 ms  build 11.9 ms
```

So the spec's own number (500 ms) governs the 12 ms half with 42x headroom,
while the 62 ms half is given a **2000 ms** ceiling that appears nowhere in the
spec — invented in the test, five hundred milliseconds notwithstanding.

The saving grace is
`test_fr018_the_cost_grows_linearly_with_the_number_of_cells`, which asserts a
*shape* (4x the cells must not cost 16x the time) rather than a wall clock. That
is the right kind of assertion and it is the one that would actually catch an
accidental quadratic.

**Fix:** apply SC-010's 500 ms to analyse + build (73 ms here leaves ample room),
or amend SC-010 to state the split and the second number.

## 3. Findings — P3

### P3-1 — `_whole_limit`'s docstring overstates its own effect by roughly 500x

`fingerprint.py:272-282`: "Without this, a list of five hundred one-megabyte
arrays copies five hundred megabytes to hash four."

**Measured** — instrumenting `_feed` and counting whole-array copies of ≥1 MiB
over exactly that value:

```
shipped        : whole-array copies fed >=1MiB: 3  bytes: 3145728
clamp removed  : whole-array copies fed >=1MiB: 4  bytes: 4194304
```

One extra megabyte, not five hundred, because `_digest` already returns early on
`_remaining(ctx) <= 0` before descending into the next element. Mutation `M16`
(removing the clamp) survives the suite for the same reason. The guard is
worth keeping as defence in depth; the claim beside it is not true.

### P3-2 — `FingerprintBudget.max_seconds` cites a measurement no committed test performs

`fingerprint.py:135-148`: "The measured worst case over the fixtures in
`tests/explore/test_fingerprint.py` is 10.4 ms — a **one-million-entry dict**".

There is no one-million-entry dict in that file. The largest mapping fixture is
`dict_200k`; the only reference to `max_scan_items` (1 Mi, the branch that makes
a one-million-entry dict the worst case) is at line 470-478, with the budget
**overridden** to `max_scan_items=1000`. So the shipped budget's own worst-case
branch is never timed.

The number is honest — I reproduced **10.74 ms** for `{i: i for i in range(1_000_000)}` —
but SC-007 leans on a figure that no test would defend against a regression.

Printed output of the committed SC-007 test on this machine (bound 250 ms):

```
  array_64mb                  0.037 ms      dict_200k       3.575 ms
  array_non_contiguous        0.042 ms      set_200k        1.910 ms
  frame_500k_x_8              0.713 ms      str_16mb        0.100 ms
  frame_mixed_dtypes          1.762 ms      nested_containers 7.660 ms
  list_200k                   1.131 ms
```

Worst case 7.66 ms against a 250 ms bound — 32x headroom, which is defensible for
a shared runner.

### P3-3 — SC-007's namespace-level assertion is effectively unfalsifiable

`test_sc007_fingerprinting_a_whole_namespace_stays_inside_the_declared_bound`
compares the whole namespace against `max_seconds * len(namespace)` = 2 250 ms.

**Measured:** 4.7 ms → **476x headroom**. This assertion cannot fail short of a
five-hundred-fold regression, which makes it a statement rather than a
measurement. (Its sibling, the per-call `test_largest_fixture_costs_less_than_the_declared_time_bound`
at 32x, is the one doing the work.)

### P3-4 — `_iter_module_level`'s descent into `except` and `match_case` bodies is untested

Mutation `N05` (drop the `ast.ExceptHandler | ast.match_case` branch,
`dependency_analysis.py:699-701`) survives. The shipped behaviour is correct —

```
except body augassign      assigned=['total']  read=['Exception','risky','total']
match case augassign       assigned=['total']  read=['total','value']
```

— and the FR-021 consequence is real: with the branch removed, the slice of a
notebook whose second cell does `except Exception: total += 1` drops the cell
that initialised `total`, which is the same `NameError` class of failure the
differential harness exists to catch. No test covers either form.

### P3-5 — FR-029's unobservable report is untested for a name that only exists after the run

Mutation `N09` (drop the `observable` check on the `after` mapping in
`compare_namespaces`) survives. Shipped behaviour is correct — a name that
appears during the run and falls back to identity is reported both as changed and
as unobservable — but nothing asserts it.

### P3-6 — the string sample's *stride* is untested (only its tail is)

Mutation `N28` (feed `obj[:keep]` instead of `obj[::step]`, keeping the tail
feed) survives. `test_survivor_a_long_string_is_sampled_to_its_last_character`
covers the final character; a change in the middle of a long string is covered by
nothing. Compare `test_fr025_an_array_above_the_bound_misses_a_change_off_its_stride`
and `test_fr025_a_frame_above_the_row_bound_misses_a_change_off_its_stride`, which
do pin the stride for arrays and frames.

### P3-7 — the fingerprint's cost guards are asserted only through `hashed_bytes`

Mutations `M16` (`_whole_limit` clamp) and `N20` (`_flat` copies instead of
viewing) both survive. Every cost assertion in `test_fingerprint.py` reads
`ctx.hashed_bytes`, which `_feed` truncates unconditionally — so it is true
however much content was *materialised* to produce it. The copy-avoidance
guards, which are what `_flat`'s and `_whole_limit`'s docstrings are about, have
no assertion at all. (`test_cost_does_not_grow_with_content_above_the_bound`
compares `hashed_bytes`, not work.)

### P3-8 — spec front matter and §4.2 do not describe the change

- `tests/explore/test_adversarial_analysis.py` (1 337 lines, and the file
  carrying most of the load-bearing coverage) appears in the spec's
  `governs.files` but **not** in the spec's `tests:` list, **not** in the §4.2
  Affected Files table, **not** in any §4.3 task, **not** in §4.4, and **not** in
  ADR-054's `tests:` list.
- `tests/architecture/test_placement.py` is modified by this change and appears
  in neither `governs.files` nor §4.2.
- `tests/explore/__init__.py` is added and appears in neither.

None of the repository's frontmatter or governance tests fail on this, so it is
drift rather than a broken gate.

### P3-9 — FR-024's equality guarantee does not hold across processes for a large set

Independently reproduced:

```
PYTHONHASHSEED=0       b0492f149313440e
PYTHONHASHSEED=524287  8add937283591d65
```

for `fingerprint({f'name-{i}' for i in range(4000)})`. FR-024 states the value
"is equal for an unchanged object" without qualification.
`test_fr024_a_large_set_fingerprints_differently_in_two_processes` documents the
boundary honestly and argues it does not matter because FR-031 stores changed
*names*, not digests — which I agree with. The gap is that the spec does not say
so; the boundary lives only in a test docstring.

### P3-10 — Sentrux unavailable

`sentrux` is not on `PATH` in this environment and `python -m sentrux` reports no
such module. Recorded as unavailable, per the dispatch.

### P3-11 — Two new untracked word-matches in `deferral_scan`

`src/scistudio/explore/dependency_analysis.py:1534` ("a later release refuse
records it cannot read") and `src/scistudio/explore/fingerprint.py:49` ("stated
here rather than discovered later"). Both are ordinary prose, both are the
word-matching false positive the scanner is known for, and the script exits 0.
Noted only so nobody re-derives it.

## 4. What I Checked And Found Sound

Recorded because a no-context audit that lists only problems misrepresents the
change.

- **The graph rules.** Twenty-eight of thirty first-round mutations were killed,
  including nearest-definer resolution, the self-dependency prohibition, the
  builtins exemption ordering against FR-013's unknown-binding fallback, the
  enabled-flag filter, edge origins, version-node/version-edge agreement,
  duplicate-id rejection, and unresolved-read recording.
- **FR-002 / FR-030, the union.** Both directions are pinned: an observation that
  reports *fewer* names cannot shrink the changed set (`M04` killed), and a stale
  observation contributes nothing (`M03`, `M24`, `N25` killed).
- **FR-011, the tokeniser rule.** Collapsing `NL` into `NEWLINE` — the exact
  misreading the FR warns about — is killed by
  `test_sc003_wrapped_operator_slice_reproduces_the_notebook`. Wrapped `%` and
  `!=` operators, magics inside string literals, indented magics, magics after
  blank and comment-only lines, and multi-physical-line magics all have tests
  that bite.
- **FR-005 / FR-006.** Import bindings, comprehension-target exclusion (with the
  PEP 709 interpreter difference handled in `_collect_comprehension_targets`),
  nested-scope `global` assignment and read, augmented-assignment and `del`
  reads — every one killed its mutation.
- **The codec.** Version mismatch, source-hash mismatch, malformed records,
  unknown-key preservation, and bool-vs-int version confusion all kill their
  mutants.
- **The differential harness has a working negative control.**
  `test_the_harness_detects_a_slice_that_dropped_a_mutating_cell` and
  `test_the_harness_detects_a_slice_that_dropped_a_definer` mean the SC-003 rows
  are not vacuous, and
  `test_sc003_the_slice_reproduces_the_whole_notebook_outputs` asserts `whole` is
  non-empty before comparing. The subprocess isolation is real and its rationale
  is correct.
- **T-011 stability markers** are enforced by
  `test_t011_every_markable_public_symbol_carries_a_tier_and_a_since`, including
  a negative list for the symbols that cannot carry one.
- **A-009** holds: `tests/adr052_contract` and the frozen public-symbol
  inventory pass unchanged.
- **Purity (FR-004)** is asserted directly, and the "a namespace that never
  imported pandas must not pay for pandas" subprocess test is the right shape.

## 5. Recommendation

**pass-with-fixes.**

No finding blocks. Nothing is functionally broken, CI-visible checks are green,
and the mutation kill rate (47/57) is the highest I have measured in this
repository.

The two that should be fixed before this is treated as finished are **P2-2**
(ten tests and two module docstrings assert defects that no longer exist — this
actively misinforms the next reader) and **P2-1** (a MUST that the code violates
and whose stated measurement cannot detect the violation). **P2-3** is the one
finding with a behavioural edge — a mutated dict entry that the observation never
sees — and it is a small, self-contained fix to `_sampled_entries`.

P2-5 and P2-6 need an owner decision on the spec text rather than code. The P3
items are coverage and documentation-accuracy work that can travel with the next
change to these modules.
