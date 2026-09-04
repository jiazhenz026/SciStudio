---
title: "Audit — ADR-054 spec 2 notebook dependency analysis (with-context)"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
related_specs:
  - adr-054-notebook-dependency-analysis
language_source: en
---

# Audit — ADR-054 spec 2 notebook dependency analysis (with-context)

Audit mode: **with-context** (agent `S2-E2`, `audit_reviewer` persona).
Subject: `track/adr-054-spec2-dependency-analysis` as integrated at
`42fd9a53c`, the candidate behind umbrella PR #2232, closing #2231.
Audit branch: `audit/2231-with-context`.
Gate ledger: `.workflow/records/2231-2231-audit-with-context.json`.

**Verdict: pass-with-fixes.** The implementation is real, the tests are real,
and the strongest claim in the spec — SC-003, that the backward slice
reproduces the notebook — is proven by executing ten fixture notebooks in
subprocesses rather than asserted. Every one of the eight defects the
adversarial test engineer filed has either been fixed or been consciously
accepted, and I re-verified each one by hand. What is wrong is smaller and
almost entirely about record-keeping: one new correctness defect I found that
six agents missed (P2), a deliberate spec deviation whose tracking issue is
cited nowhere in the repository (P2), seven test docstrings that still describe
fixed defects as live (P2), three paths in the diff that no scope block
declares (P2), and two gate ledgers that record a failing final state or no
diff at all (P2). None of it blocks; all of it is cheap to repair.

## 1. What I did

- Read the spec, ADR-054 §6.1/§6.2/§11, the checklist, and all eight dispatch
  prompts under `docs/planning/adr-054-spec2-dispatch-prompts/`.
- Read `src/scistudio/explore/__init__.py`,
  `dependency_analysis.py` (1,558 lines), and `fingerprint.py` (1,053 lines) in
  full for the parts each FR names.
- Ran the required checks (§6) and the SC-012 suites.
- Wrote and ran seven independent probe scripts against the delivered modules,
  outside the shipped test suite, to try to break FR-005, FR-006, FR-011 and
  FR-015 rather than to confirm them. One of them found a new defect (F-01).
- Diffed `origin/main...HEAD` against every declared write set and every gate
  ledger's `declared_scope` and `observed_diff`.
- Checked GitHub for #2231, #2232, #2242 and #2243, and searched the whole
  repository for each of those numbers.

I edited no implementation file and no test file. Everything below is
reproducible from `42fd9a53c`.

## 2. Requirement coverage — FR-001 to FR-036

`impl` names the primary implementing symbol; `test` names the proof. "—" in
the test column would be a finding; there are none. Two rows carry a defect
marker instead.

| FR | Requirement | Implementation | Test | Verdict |
|---|---|---|---|---|
| FR-001 | The unit is the cell; no statement order, no branch, no nested-scope internals | `analyse_cell` operates per cell; no statement-order state anywhere | `test_read_written_after_the_binding_is_still_recorded`, `test_a_cell_never_depends_on_itself` | covered (structural; no dedicated test, correctly so — it is a negative property) |
| FR-002 | Never omit an assignment the code shows; changed set is the union | `_resolve_changed_sets` | `test_the_changed_set_is_the_union_of_the_estimate_and_the_observation`, `test_an_observation_never_removes_a_static_edge`, `test_fr030_*` (3) | **violated in one form — see F-01** |
| FR-003 | Standard library only; no IPython, no notebook lib, no static-analysis pkg | module imports of both modules | `test_explore_does_not_import_ipython_or_a_notebook_library` | covered |
| FR-004 | Pure: no execution, no kernel, no filesystem | `analyse_cell`, `fingerprint`, codec | `test_adversarial_analysis.py:137/173/205`, `test_dependency_analysis.py:1951`, `test_fingerprint.py:615/1061` | covered (patches `open`/`exec` and asserts they are never reached) |
| FR-005 | Every binding form recorded | `_symtable_names`, `_collect_bindings`, `_collect_comprehension_targets` | 21 per-form tests + `test_every_fr_005_form_has_its_own_test` (the SC-001 ratchet) | **one form incomplete — see F-01** |
| FR-006 | Module-scope reads, including nested-scope reads that resolve to module scope | `_symtable_names`, `_collect_module_level_reads`, `_collect_nested_module_scope` | 20 tests, incl. the two `global` blind spots S2-D1 found and S2-F1 fixed | covered |
| FR-007 | No mutation, alias, or callee analysis; no list of mutating methods | absence, enforced | `test_in_place_method_call_assigns_nothing`, `test_call_that_mutates_its_argument_assigns_nothing`, `test_alias_of_a_frame_is_not_tracked` | covered |
| FR-008 | `scistudio.output` calls, keyword and argument names | `_collect_calls`, `_output_declaration` | 5 tests | covered |
| FR-009 | `scistudio.input` string literals | `_collect_calls` | 3 tests, incl. the non-literal negative | covered |
| FR-010 | Block id literal; non-literal flagged | `_collect_calls`, `BlockCall` | 4 tests | covered |
| FR-011 | `%%` opaque textually; magics identified lexically by logical line | `_magic_line_numbers`, `_strip_magic_lines`, `_textual_magic_lines` | 15 tests | covered — independently re-verified, see §4 |
| FR-012 | Unparseable cell flagged, never raises, never blocks another cell | `_syntax_error_facts` | 5 tests + `test_no_cell_ever_raises` (parametrised), incl. the lone-surrogate case S2-F1 fixed | covered |
| FR-013 | Star import / `%run` bind an unknown set; unresolved reads fall back to the nearest such cell above | `analyse_cell` flag + `build_graph`'s `latest_unknown` | 8 tests, incl. "below the reader does not resolve" and "a real definer beats it" | covered |
| FR-014 | Graph over enabled cells only; the flag is read, never written | `build_graph` | 8 tests, incl. `test_build_graph_does_not_write_the_enabled_flag` | covered |
| FR-015 | Nearest enabled definer above; no self-dependency; unresolved list, builtins exempt | `build_graph` | 7 tests | **deviation — see F-02** |
| FR-016 | Version nodes and version edges from the same facts | `version_nodes`, `_version_edges` | 6 tests, incl. the dangling-source case S2-F1 fixed | covered |
| FR-017 | Deterministic in source, order, flags, observations | `build_graph` | `test_the_graph_is_a_deterministic_function_of_its_inputs`, plus the PEP 709 interpreter-independence tests | covered |
| FR-018 | Linear, with a measured bound | one pass with a running definer map | `test_fr018_the_cost_grows_linearly_with_the_number_of_cells` (250 vs 1000 cells) | covered — measured, not asserted |
| FR-019 | Every edge carries its origin | `EdgeOrigin`, `_edge_origin` | 3 tests, one per origin | covered |
| FR-020 | Downstream set, in written order | `DependencyGraph.downstream` | 4 tests | covered |
| FR-021 | Backward slice with the unresolved reads inside it | `DependencyGraph.backward_slice`, `SliceResult` | 6 unit tests + all 32 differential tests | covered — the unresolved list is correctly scoped to the slice, verified independently |
| FR-022 | Changed set = estimate ∪ observation | `DependencyGraph.changed_set` | 4 tests | covered |
| FR-023 | Which cell written order says defines a name | `DependencyGraph.definer_for` | 5 tests | covered |
| FR-024 | Fingerprint per type, identity fallback marked unobservable | `fingerprint`, `_digest*` family | 12 tests, one per type plus the fallback | covered |
| FR-025 | Cost bounded by one declared constant, sampled at fixed strides across the full extent | `FingerprintBudget`, `FINGERPRINT_BUDGET`, `_stride_indices` | 9 tests, incl. the stride P1 S2-F1 fixed | covered — `_stride_indices` now uses `ceil`, verified |
| FR-026 | Namespace comparison: changed, appeared, disappeared | `compare_namespaces` | 7 tests | covered |
| FR-027 | Observation keyed to the source hash, discarded on edit | `ObservedChange.applies_to`, `_observation_is_current`, `_decode_observation` | 7 tests | covered |
| FR-028 | Unpredicted-change diagnostic names cell and name | `observation_flags` | 3 tests | covered |
| FR-029 | Unobservable name reported once per cell run | `observation_flags`, `Fingerprint.observable` | 7 tests | covered |
| FR-030 | An observation only adds | `_resolve_changed_sets` | 3 `fr030` tests | covered |
| FR-031 | Record under the `scistudio` key; notebook record holds the version | `CELL_RECORD_KEY`, `encode_cell_record`, `encode_notebook_record` | 4 tests | covered |
| FR-032 | Edges not stored; recomputed on load; hash mismatch discards | `decode_cell_record` | 4 `fr032` tests | covered |
| FR-033 | JSON primitives only; unknown keys survive a rewrite | `_RECOGNISED_CELL_KEYS`, `encode_cell_record` | 4 `fr033` tests | covered |
| FR-034 | Standard-library JSON handling | codec | `test_sc009_the_round_trip_survives_json_itself` | covered |
| FR-035 | Stdlib + lazily numpy and pandas inside the fingerprint; SciStudio only for stability markers; layer test enumerates | module imports; `EXPLORE_ALLOWED_SCISTUDIO_IMPORTS` | `test_explore_imports_are_allowlisted` | **partially — see F-05** |
| FR-036 | Exactly seven flags, each with a message | `AnalysisFlag` (StrEnum), `_FLAG_MESSAGES` | `test_the_flag_enumeration_holds_exactly_the_seven_spec_flags` + per-flag message test | covered — I enumerated the seven independently |

No FR has an implementation and no test. Thirty-four of thirty-six are clean.

## 3. Success criteria — SC-001 to SC-013

The S2-E2 prompt says "SC-001 to SC-010". The spec has thirteen. I walked all
thirteen; the prompt's range is a transcription slip, not a scope reduction
(F-09).

| SC | Criterion | Measured or asserted | Evidence |
|---|---|---|---|
| SC-001 | Every FR-005 form has a test that fails if the form stops being recognised | **measured**, and machine-checked | 21 per-form tests plus `test_every_fr_005_form_has_its_own_test`, which fails if a named form loses its test. Caveat: the "walrus target" row's test covers only the statement-level form (F-01) |
| SC-002 | The Story 2 six-cell fixture slices to 1,2,3,4,6, and so do its three mutation variants | **measured** | `test_sc002_the_story_two_slice_is_one_two_three_four_and_six` over all four fixtures; I read `story_two_in_place.ipynb` and it is literally Story 2's notebook |
| SC-003 | For every fixture, the slice on a fresh namespace reproduces the whole notebook's outputs | **measured**, and the strongest evidence in the delivery | `test_analysis_differential.py`: ten fixtures executed in real subprocesses with real `fingerprint`/`compare_namespaces`, plus two negative controls proving the harness can fail (`test_the_harness_detects_a_slice_that_dropped_a_mutating_cell`, `..._a_definer`) |
| SC-004 | Disabling a definer moves the edge; disabling the only definer leaves the read unresolved | **measured** | 4 dedicated tests plus the `alternatives_disabled.ipynb` differential fixture |
| SC-005 | Line magic, shell line, cell magic, star import, syntax error each flag and none raises | **measured** | 15 magic tests, 5 flag tests, and `test_no_cell_ever_raises` parametrised over the pathological cells |
| SC-006 | The fingerprint detects in-place mutation of array, frame, series, list, dict, set, and is equal for each unchanged | **measured** | one test per type per direction, and each mutation deliberately leaves length and shape alone |
| SC-007 | Fingerprinting the largest namespace completes within the declared bound | **measured** | `test_sc007_*` times an 8M-element array, a 1M-cell frame, a 200k list, a 50k dict and a 2 MB string against `max_seconds × n`. The namespace is synthetic rather than a fixture's, which is *harder* than the SC asks |
| SC-008 | An observation counts, is discarded on edit, never removes a static edge | **measured** | 3 tests, plus the codec's `test_fr027_a_stored_observation_for_other_source_is_discarded_on_load` |
| SC-009 | Metadata round trip yields an equal graph | **measured** | 2 tests, one of which round-trips through `json.dumps`/`json.loads` |
| SC-010 | 500 cells build in under 500 ms | **measured** | `test_building_the_graph_of_a_five_hundred_cell_notebook_is_fast` and `test_sc010_*`; the checklist's reported 49 ms + 11 ms is consistent with what I saw |
| SC-011 | The modules import nothing from SciStudio beyond stability markers and nothing third-party except numpy and pandas lazily | **half measured, half unmeasurable as written, and the unmeasured half is false** | the module-level half is asserted by `test_explore_imports_are_allowlisted`; the lazy half is invisible to it by construction, and `fingerprint._new_hasher` lazily imports `xxhash`, which SC-011 does not name (F-05) |
| SC-012 | Layer test, architecture drift audit, and frozen surface inventory all pass | **measured** — I ran them | `full_audit` → `pass`, 0 errors (9 child audits); `tests/architecture tests/api/test_public_surface.py tests/api/test_stability_decorators.py tests/adr052_contract tests/stability tests/docs` → all pass, 8 skips all pre-existing |
| SC-013 | The definer query returns the nearest enabled definer above, or none | **measured** | `test_the_definer_query_answers_with_the_written_order_definer` over the A/B/C fixture Story 1 names |

Twelve of thirteen are genuinely measured. SC-011 is the one that is partly
asserted, and the asserted part is not true as written.

## 4. The three things I was asked to verify rather than accept

### 4.1 The narrowed FR-011 is what the implementation does

Yes. FR-011 was rewritten during this work from a first-character textual test
to a lexical one, and the narrowing turns on one distinction: the tokeniser's
`NEWLINE` ends a logical line and its `NL` does not. `_magic_line_numbers`
honours exactly that — `NL` is handled in its own branch and never sets
`at_logical_start`, `INDENT`/`DEDENT`/`COMMENT` are ignored, and the
`TokenError` path falls back to the older textual test from the failing line
onward, as the spec's last clause requires.

I did not take the shipped tests' word for it. I ran the analysis directly on
twenty-one cell shapes, including every case FR-011 names and several it does
not:

| Cell | Result | Correct? |
|---|---|---|
| `ratio = (\n total\n % count\n)` | `assigned={ratio}`, `read={count,total}`, no flag | yes — the case the narrowing exists for |
| `flag = (\n total\n != count\n)` | `read={count,total}` | yes |
| `a = 1 \`⏎`% b` (backslash continuation) | `assigned={a}`, `read={b}` | yes — "after a backslash continuation" |
| `s = '''⏎%fake⏎'''⏎z = s` | `assigned={s,z}`, `read={s}` | yes — "inside a string literal" |
| `v = [1,⏎ 2 % 3]` | `assigned={v}`, no strip | yes — "within an open bracket" |
| `%pip install \`⏎`  somepkg⏎w = 1` | both physical lines removed, `assigned={w}` | yes — "every physical line the magic's logical line spans" |
| `!cat it's-a-file⏎q = 3` | tokeniser stops; textual fallback strips line 1; `assigned={q}` | yes — the `TokenError` clause |
| `# c⏎%pip install x⏎d = 1` | magic after a comment-only line still stripped | yes |
| `⏎⏎%pip install x⏎e = 1` | magic after blank lines still stripped | yes |
| `%%time⏎df = 1` | opaque, assigns nothing, reads nothing | yes |
| `x = 1⏎%%time⏎y = 2` | `%%` not on the first non-blank line, so stripped as a magic line, not opaque | yes — FR-011 scopes the opaque test to the first non-blank line |
| `n = 7⏎n %= 3` | `%=` is one token, never a magic | yes |
| `s = f'{100 % 3}'` | untouched | yes |

The narrowing is honest work, prototyped before it was written (the drift log
says so and the code bears it out), and the implementation matches it clause by
clause. The one wrinkle: an indented `%timeit` inside a `def` body is treated
as a magic and stripped, which is the spec's literal instruction
("indent, dedent … ignored") but leaves a `def` with an empty body, so the cell
lands in FR-012 anyway. Same outcome either way; not a finding.

### 4.2 The `AnalysisRecord` drop is justified, not convenient

Justified. Key Entities defines `AnalysisRecord` as "the JSON shape stored in
cell metadata", not as a type, and FR-033 requires keys the analysis does not
recognise to survive a rewrite — which `encode_cell_record` implements by
carrying every key outside `_RECOGNISED_CELL_KEYS` through untouched, and which
`test_fr033_a_key_the_analysis_does_not_recognise_survives_a_rewrite` proves. A
frozen dataclass cannot express "and whatever else was there"; a class invented
to satisfy the manifest line would have constrained nothing, which is precisely
what the front-matter comment says. S2-C1 was right to refuse to invent it and
S2-G1 was right to drop rather than resolve it.

Two details worth recording. The reason is kept as a YAML comment where the
entry stood, which is the right place — it survives with the manifest rather
than in a report. And `ObservedChange`, which *is* a type, was correctly moved
into `governs` rather than dropped with it. The drop is not a shortcut.

### 4.3 The unfixed finding (#2243, FR-015's unresolved-read exception)

**Leaving it was the right call. Recording it was not finished.**

The deviation is real. FR-015 admits exactly one exception to "a read with no
enabled definer above it MUST be recorded as unresolved" — a name in Python's
builtins. `build_graph` adds a second: a read of a name the reading cell's own
changed set contains. I confirmed both halves independently:

- The exception's stated justification in the source comment is that without it
  "every `import pandas as pd` cell would report `pd` unresolved". For a *bare*
  `import pandas as pd` that is false — `symtable` reports `pd` as imported and
  not referenced, so the cell reads nothing and the exception never fires. The
  adversarial test engineer caught the same false premise and says so.
- The premise is nevertheless substantively right for the shape people actually
  write. `import pandas as pd` followed in the *same cell* by
  `df = pd.read_csv('f')` does read `pd`, and without the exception every such
  cell would report `pd` unresolved and packaging would refuse it. Same for
  `def f(n): return f(n-1)` and for `total = 0; total += 1`.
- The cost is a real false negative: a first cell that says `df = df.dropna()`
  raises `NameError` when it runs, and FR-021's unresolved list stays empty, so
  packaging accepts a notebook that fails. I reproduced this.

Telling the two apart needs within-cell statement order, which FR-001 forbids
the analysis to model. So the resolution genuinely is the owner's — either
FR-015 gains this exception or FR-001 gains a narrow ordering rule — and an
implementer inventing either would have been worse. Leaving it: correct.

Recording it: **incomplete, and this is F-02.** Issue #2243 exists on GitHub,
is open, and its title states the problem accurately. It is cited *nowhere in
the repository*: not as a `TODO(#2243)`, not in the checklist drift log (which
does cite #2242 for the sibling governance follow-up), not in either of the two
test docstrings that document the behaviour, and not in any gate ledger.
AGENTS.md §3.6 requires deferred work to be visible in the repository with a
tracked TODO citing an issue, and the S2-F1 prompt repeats that rule verbatim.
A reader who lands on `test_fr015_a_read_only_the_cell_itself_binds_is_not_
reported_unresolved` sees a green test that documents a deviation from a MUST
and has no thread back to the decision.

The behaviour itself *is* honestly described — the adversarial docstring lays
out the false premise, the real cost, and the two options, and does not pretend
the exception is authorised. That is more honesty than most deferrals get. It
is the traceability that is missing, not the candour.

## 5. Scope discipline

`git diff origin/main...HEAD --stat`: 39 files, +14,125 / −27.

Checklist §2 declares the in-scope set as `src/scistudio/explore/*`,
`tests/explore/**`, `tests/architecture/test_layer_deps.py`, the checklist, the
prompt directory, `docs/audit/**`, and `.workflow/records/2231-*.json`. Three
changed paths are outside it:

| Path | Lines | Declared where | Verdict |
|---|---|---|---|
| `docs/specs/adr-054-notebook-dependency-analysis.md` | 62 | §6 gives it to S2-G1 — but §2 lists `docs/specs/adr-054-*.md` as **out of scope**, "approved input, not work product" | contradiction, F-04 |
| `docs/adr/ADR-054.md` | 23 | §6 gives it to S2-G1; §2 does not list it either way | undeclared, F-04 |
| `tests/architecture/test_placement.py` | 1 | §6 (amended) and S2-B1's gate ledger scope; not in §2 | amended correctly in the ledger; §2 never caught up, F-04 |

The spec edit is the one that matters: FR-011 was materially rewritten and
`planned_governs` was restructured on a branch whose own checklist calls the
specs approved input. The edits are right (§4.1, §4.2); the authorisation for
them lives in the §6 matrix and the drift log rather than in §2, and §2 still
says the opposite. Nothing else in the diff is outside scope: every
`src/scistudio/explore/` and `tests/explore/` path is declared, and the seven
`.workflow/records/2231-*.json` files match the pattern.

The dispatch-prompt directory is `docs/planning/`, not `docs/ai-developer/`, so
`governance_touch: false` on every ledger is correct — this work did not touch
a governance surface.

## 6. Gate evidence

I read every `2231-*` ledger's `declared_scope`, `docs_events`,
`check_events` and `observed_diff` and compared them to the diff.

| Ledger | Final check state | Observed diff | Problem |
|---|---|---|---|
| `2231-track-…-dependency-analysis` (manager) | **no checks at all**; `required_obligations` empty; no commit, no PR | none recorded | The ledger for the branch that becomes PR #2232 carries zero evidence. Its `declared_scope` also omits `docs/adr/ADR-054.md`, `docs/specs/…`, and `tests/architecture/test_placement.py`, all of which the integrated diff changes. F-06 |
| | | | Its `docs_events` still names `docs/planning/adr-054-spec2-dispatch-prompts/a-impl.md`, a file from the **abandoned first dispatch** (commit `38125e1f6`) that no longer exists. F-08 |
| `2231-feat-…-dep-analysis-graph` (S2-B1) | `full_audit: fail`, waived by `check_na` with a long rationale; everything else pass | 7 files, matches, includes `test_placement.py` | the waiver's condition (the `planned_governs` entries could not be moved by an implementer) was real and is now discharged by S2-G1; `full_audit` passes today. Acceptable in hindsight, but a CI-owned check was waived by ledger declaration. F-07 |
| `2231-feat-…-fingerprint` (S2-B2) | **`architecture_tests: fail`, `full_audit: fail`** as the last recorded state | 3 files, matches | checklist §7.3 claims this agent "merged into the track branch" with clean evidence; the ledger's final recorded state is two failures, never re-run to pass. F-06 |
| `2231-feat-…-observation-codec` (S2-C1) | `full_audit: fail`, rest pass | 7 files, matches | same `planned_governs` cause; discharged. F-07 |
| `2231-test-…-adversarial` (S2-D1) | **`python_tests: fail`, `full_audit: fail`**; every check ran at `scope=repo` | **`changed_files: 0`, every surface count 0** | the ledger for ~3,300 lines of tests and ten fixtures observed *no diff at all* — the checks were run against an empty diff, so they fell back to repo scope. The largest test contribution in the delivery has no diff-scoped gate evidence. F-03 |
| `2231-docs-…-governs-migration` (S2-G1) | `commit_hygiene: pass`, `full_audit: pass` | 3 files — spec, checklist, ledger; **not `docs/adr/ADR-054.md`** | the final `observed_diff` is the second pass's, so the ADR edit made in the first pass is invisible in the ledger a reviewer reads. F-08 |
| `2231-fix-…-audit-findings` (S2-F1) | all seven required checks **pass** | 5 files, matches | `declared_scope.include` is **empty** despite the prompt naming a write set. F-06 |

Claims that *do* hold: every ledger names #2231 with `close_in_pr`; every
`docs_events` N/A rationale ("the governing spec landed in PR #2228 and this
change implements it") is true — the spec did land in #2228 and no new
user-facing surface exists; the checklist's per-file test counts
(`test_analysis_differential.py` 32, `test_adversarial_analysis.py` 64) match
what I collected exactly, with no inflation; and S2-B1's recorded commit sha
`037535546` is a real commit reachable from `HEAD`.

## 7. Nothing from the abandoned dispatch survives — except one line

The restart is clean in the working tree. Commit `38125e1f6` added three files;
`a-impl.md` is gone, and the checklist and ledger were rewritten. The single
survivor is the `docs_events` entry in the retained manager ledger that still
claims `a-impl.md` as a documentation path (F-08). It is one stale JSON row,
but it is exactly the kind of thing the restart note promised had been cleared.

## 8. Findings

### P1

None. Nothing here fails CI, corrupts data, or breaks a shipped behaviour.

### P2

**F-01 — A walrus target inside a list, set, or dict comprehension is not
recorded as assigned. FR-002's one guarantee is violated.**

New; found by my own probing, not reported by any prior agent.

```python
# cell 1
vals = [y := i for i in range(3)]
# cell 2
out = y + 1
```

Python binds `y` at module scope (PEP 572); `exec` confirms `{'vals', 'y'}`.
The analysis reports `assigned == {'vals'}`. Consequences, all reproduced at
`42fd9a53c`:

- `downstream('c1') == ()` — re-running cell 1 does **not** mark cell 2 stale.
  That is the exact defect ADR-054 §6.1 was written to remove.
- `unresolved_reads == [('c2', 'y')]` — packaging would **refuse** a notebook
  that runs correctly.
- `backward_slice(['c2']) == ('c2',)` — the slice drops the definer.

Root cause, in `analyse_cell`: `assigned` comes from `_symtable_names`. On
CPython 3.12+ PEP 709 inlines list/set/dict comprehensions, and `symtable`
reports the inlined walrus target at module scope with `is_assigned() == False`
and `is_local() == False`, so it is never collected. `_collect_bindings` *does*
see the `ast.Name` in `Store` context and puts it in `explicit_bindings` — but
`explicit_bindings` is only ever used **subtractively**
(`comprehension_only = comprehension_targets - explicit_bindings`), never
additively, exactly as its own docstring says. A generator expression is still
a real child scope, so `_collect_nested_module_scope` catches *its* walrus:
`total = sum(z := v for v in [1, 2])` correctly reports `{'total', 'z'}`. The
asymmetry is the tell.

Affected forms (verified): list comprehension, set comprehension, dict
comprehension, nested comprehension. Unaffected: statement-level walrus,
generator expression.

Why nobody caught it: `FR_005_FORMS`' "walrus target at module scope" row maps
to `test_assigned_walrus_target`, which tests `if (value := compute()):` — the
statement-level form. SC-001's ratchet checks that the *form has a test*, not
that the test covers the form's variants, so the meta-test stayed green.

Fix shape: union the walrus targets `_collect_bindings` already collects back
into `assigned`, i.e. make `explicit_bindings` additive for `ast.NamedExpr`
targets rather than subtractive only. One test per comprehension kind, added to
`FR_005_FORMS` as its own row so the ratchet covers it.

Mitigation that bounds this: once the cell has run, the observation adds `y`
and the edge appears (`origin='observed_change'`, verified). So the damage
window is a notebook loaded but not yet run — which is also precisely the
window FR-002 says the static estimate exists to cover.

**F-02 — Issue #2243 is cited nowhere in the repository.**

Full analysis in §4.3. The deviation is the right call and is well described in
`test_fr015_a_read_only_the_cell_itself_binds_is_not_reported_unresolved`, but
`grep -rn 2243` over the whole repository returns nothing. AGENTS.md §3.6 and
the S2-F1 prompt both require a `TODO(#NNN)`. The sibling follow-up #2242 *is*
cited, in the checklist drift log, which shows the team knows how to do this.
Fix: a `TODO(#2243)` beside the exception in `build_graph`, a drift-log row, and
the issue number in the two test docstrings.

**F-03 — S2-D1's gate ledger observed an empty diff.**

`2231-test-2231-adversarial.json` records `observed_diff.changed_files: 0` and
every surface count at zero, and every check ran at `scope=repo` because there
was no diff to narrow to. The agent delivered
`test_adversarial_analysis.py` (1,337 lines), `test_analysis_differential.py`
(355 lines), `fixtures/_run_notebook.py` (215 lines) and ten fixture notebooks.
The most likely cause is `check` run before the work was committed. The ledger
therefore carries no diff-scoped evidence for the single largest test
contribution, and its last recorded `python_tests` state is `fail` with no
`check_na` and no re-check after S2-F1 closed the eight findings. Fix: re-run
`check` on the integrated branch and record the result.

**F-04 — Three changed paths are outside the checklist's §2 scope, one of them
explicitly declared out of scope.**

Detail in §5. `docs/specs/adr-054-notebook-dependency-analysis.md` is named in
§2 as out of scope ("approved input, not work product") and was materially
edited — FR-011 rewritten, `planned_governs` restructured. `docs/adr/ADR-054.md`
and `tests/architecture/test_placement.py` are undeclared in §2. The §6 matrix
and the drift log authorise all three; §2 was never reconciled and now
contradicts §6. The edits are correct on the merits; the scope block is false.
Fix: reconcile §2 before the PR, so the PR's own scope statement is true.

**F-05 — `xxhash` is a lazy third-party import that FR-035 and SC-011 do not
permit, and the test that would catch it cannot see it.**

`fingerprint._new_hasher` does `import xxhash` inside the function. FR-035
permits "lazily and only inside the fingerprint, numpy and pandas"; SC-011 says
"nothing third-party except numpy and pandas lazily inside the fingerprint".
Spec §4.1 *directs* xxhash ("the `xxhash` dependency SciStudio already
carries"), so the spec contradicts itself. The drift log records the conflict
and resolves it by observing that `test_explore_imports_are_allowlisted` reads
module-level imports only — the test's own docstring says a lazy import "is
invisible here by construction". The resolution is recorded as "No document
change needed", but the document is now false as measured, and the check that
SC-011 names cannot measure the half that matters: a lazy `import requests`
would pass today. Fix: add `xxhash` to FR-035 and SC-011 (one clause), and
either add an AST check for lazy third-party imports inside `explore/` with a
named allowlist, or state in SC-011 that the lazy half is unmeasured.

**F-06 — Two ledgers end on a failing state, one ledger has no evidence at all,
and two ledgers declare no scope.**

Table in §6. `2231-feat-2231-fingerprint.json` ends with `architecture_tests`
and `full_audit` at `fail` while the checklist claims a clean merge for that
agent. The manager ledger — the one that backs PR #2232 — has zero check
events, empty `required_obligations`, no commit and no PR, and a
`declared_scope` that three changed paths fall outside of.
`2231-fix-2231-audit-findings.json` and `2231-test-2231-adversarial.json` both
have an empty `declared_scope.include`. Fix: run `check` and `finalize` on the
track branch before the PR, and amend the manager ledger's scope to the real
write set.

**F-07 — Seven test docstrings still describe fixed defects as live, and the
adversarial module header still says the failing tests are "left failing on
purpose".**

All 430 tests pass. Eight docstrings still open with `FINDING P<n>` and present
tense. Exactly one was rewritten when it was fixed
(`test_fr011_a_magic_line_inside_a_string_literal_is_left_alone`, now "The
finding above, closed"), which shows the right pattern and makes the other
seven look like oversight rather than convention:

| Test | Docstring still claims | Reality |
|---|---|---|
| `test_fr025_a_container_above_the_bound_is_sampled_across_its_full_extent` | "It does not [hold]… every position from 512 to 998 is invisible… the fix is one line" | `_stride_indices` uses `ceil`; fixed |
| `test_fr016_every_version_edge_source_is_a_version_node` | "the current state asks every consumer to discover the dangling reference for itself" | `build_graph` publishes `unknown_versions` nodes; fixed |
| `test_fr012_a_cell_holding_an_unpaired_surrogate_is_flagged_rather_than_raising` | "It does [raise]" | fixed |
| `test_fr006_a_global_augmented_assignment_inside_a_function_is_a_module_read` | "a nested-scope read FR-006 requires and the analysis does not record" | fixed |
| `test_fr006_a_global_del_inside_a_function_is_a_module_read` | "is missed for the same reason" | fixed |
| `test_sc003_global_counter_slice_reproduces_the_notebook` | "I believe the product is wrong and this test is right" | fixed |
| `test_sc003_wrapped_operator_slice_reproduces_the_notebook` | quotes the **old** FR-011 text and proposes a fix that already landed | fixed; FR-011 rewritten |
| module header, `test_adversarial_analysis.py` | "They are left failing on purpose" | nothing fails |

One is worse than stale: `test_the_wrapped_operator_read_is_lost_without_a_flag`
now asserts `"count" in facts.read`, i.e. the read is **not** lost — the test
name says the opposite of what the test proves, and its inline message still
reads "which is FR-011 working as specified" about a strip that no longer
happens. The test suite is the de-facto defect record for this subsystem; seven
entries in it are wrong about the shipped product. Fix: rewrite each docstring
in the `…is_left_alone` pattern — what was found, that it is closed, and what
closed it — and rename the one misnamed test.

### P3

**F-08 — Two stale ledger rows.** The manager ledger's `docs_events` still
names `docs/planning/adr-054-spec2-dispatch-prompts/a-impl.md` from the
abandoned first dispatch (§7). S2-G1's ledger's final `observed_diff` omits
`docs/adr/ADR-054.md`, which that agent did change (§6). Neither is a false
claim about the *product*; both make the ledgers a worse record than the diff.

**F-09 — The checklist and this prompt are internally inconsistent about
status and scope.** §6's status column says S2-B1 `[!]` blocked, S2-B2 `[ ]`,
S2-G1 `[ ]`, while §7.3 marks the same agents `[x]` with merge evidence and the
commit history shows all three integrated. §7.4 (audit), §7.5 (integration) and
the whole of §8 (verification evidence — every row `[ ]`, every evidence cell
empty) are unfilled on a branch the manager is proposing as a PR candidate.
Separately, the S2-E2 prompt asks for "SC-001 to SC-010" where the spec has
thirteen. Fix: reconcile §6 with §7.3 and fill §8 before the PR.

**F-10 — The spec's `tests:` front-matter list omits
`tests/explore/test_adversarial_analysis.py`,** which `governs.files` does
include. 1,337 lines of the delivered coverage are governed but not listed as
the spec's tests. One line.

**F-11 — Two source/test comments repeat a false example.** The FR-015
exception's justification, in both `build_graph`'s comment and
`test_a_name_the_reading_cell_binds_itself_is_not_unresolved`'s docstring, says
"every `import pandas as pd` cell would report `pd` unresolved". A bare
`import pandas as pd` reads nothing and never fires the exception; the true
example is the same import followed in one cell by `pd.read_csv(...)`, which is
what the test actually uses. Correct the example so the justification stands on
the real case.

## 9. Checks run

| Check | Result |
|---|---|
| `pytest tests/explore tests/architecture/test_layer_deps.py -q` | **430 passed**, 0 failed |
| `ruff check src/scistudio/explore tests/explore` | All checks passed |
| `mypy src/scistudio/explore` | Success: no issues found in 3 source files |
| `python -m scistudio.qa.audit.full_audit` | **pass**, 0 errors across 9 child audits |
| `pytest tests/architecture tests/api/test_public_surface.py tests/api/test_stability_decorators.py tests/adr052_contract tests/stability tests/docs -q` | pass; 8 skips, all pre-existing and sanctioned |
| `gate_record check --mode local --base origin/main --head HEAD` | "no gate ledger found" on the audit branch before `init`; ledger created for this audit |

Per-file collection, for the record: `test_dependency_analysis.py` 240,
`test_fingerprint.py` 84, `test_adversarial_analysis.py` 64,
`test_analysis_differential.py` 32, `test_layer_deps.py` 10.

## 10. Recommendation

**pass-with-fixes.**

The delivery does what the spec asks. The graph is right, the queries are
right, the fingerprint is right, the codec is right, and — the part that is
hard to fake and was not faked — SC-003 is proven by running ten notebooks in
subprocesses with two negative controls that prove the harness can fail. The
spec was edited twice during the work and both edits improve it: FR-011's
narrowing is correct and correctly implemented, and dropping `AnalysisRecord`
is the right answer to a manifest line that could not be satisfied honestly.

Before the PR:

1. Fix **F-01** (the comprehension walrus) — it is a missing edge, the one
   direction FR-002 forbids, and the fix is small.
2. Land **F-02** as a `TODO(#2243)` plus a drift-log row.
3. Repair the seven stale docstrings and the one misnamed test (**F-07**), and
   rerun S2-D1's ledger check (**F-03**).
4. Reconcile checklist §2 with what was actually written (**F-04**), fill §8,
   and reconcile §6 with §7.3 (**F-09**).
5. Amend FR-035 and SC-011 for `xxhash`, or say plainly that the lazy half is
   unmeasured (**F-05**).
6. Run `check` and `finalize` on the track branch so PR #2232 has a ledger
   behind it (**F-06**).

F-08, F-10 and F-11 are one-line repairs that can ride along or be deferred
with a tracked issue.
