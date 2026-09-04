# Audit: ADR-054 Explore Session (`scistudio.explore`, the session runtime) — no-context

- Date: 2026-09-04
- Persona: `audit_reviewer`, `no-context` mode
- Branch / worktree: `audit/2240-no-context` @
  `C:/Users/jiazh/workspace/SciStudio/.worktrees/s3-e1-audit-nc`
- Change under review: `git diff origin/main...HEAD -- src tests`
  (`origin/main` = `43e9313f2`, merge base = `cae11210c`, head = `348228d8a`);
  70 files, 40 035 insertions, 74 deletions under `src/` and `tests/`
  (128 files / 66 217 insertions across the whole diff).
- Judged against: `docs/specs/adr-054-explore-session.md`,
  `docs/specs/adr-054-notebook-dependency-analysis.md`, `docs/adr/ADR-054.md`,
  `pyproject.toml`, `.github/workflows/ci.yml`, and the repository's own
  architecture and governance tests.
- Environment: Windows 11 26200, CPython 3.13.12.

Per the dispatch I did not read the owner request, any GitHub issue, any
planning checklist under `docs/planning/adr-054-spec2-*` or
`docs/planning/adr-054-spec3-*`, any dispatch prompt other than my own, any PR
text, any commit message, or any ledger under `.workflow/records/`. The diff
was read with `git diff origin/main...HEAD -- src tests` so no commit message
was incidentally visible. Nothing below is a statement about anyone's intent;
where I describe a purpose it is quoted from a repository document or from a
docstring in the change itself.

---

## 1. Verdict

**Pass with fixes.**

The implementation is unusually well covered. Thirty deliberate
mutations of behaviour the specification names — the admission whitelist, both
clauses of FR-024's skip rule, every packaging refusal, the temporary-index
commit, the ref namespace, output stripping, the pack interval, the ref-safe
session-id guard, the `.git` entry-path guard, `on_new_input` precedence and
default, the dispatch's replay branch, `%pip` detection, coalescing, the panel
freeze, the environment content address, the analysis-record round trip, the
enabled flag, the block-call session foreign key, and the ADR-038 version
opt-in — were **all** caught by the committed tests once the tests that need a
real kernel can run (§6). I found no surviving mutant.

What I found instead sits in three places the mutation campaign cannot reach:
one test that cannot pass wherever it runs, two architecture tests that check
less than their own docstrings say they check, and three requirements whose
library half is written and whose production wire is not.

One finding blocks CI (§3, P1-1). The rest are fixes.

---

## 2. What I ran

| Check | Result |
|---|---|
| `pytest tests/explore tests/api/test_explore_routes.py tests/architecture/test_layer_deps.py` (shared `.venv`) | pass, 84 skips (no `ipykernel`) |
| `pytest tests/explore` with a real ipykernel 7.3.0 | pass, 1 skip (message-mode is POSIX-only) |
| `pytest tests/api/test_explore_*.py` with a real ipykernel 7.3.0 | **1 failure** — see P1-1 |
| `pytest -n auto -m "not serial"` (whole repository) | pass, 0 failures, 42 skips |
| `pytest -n 0 -m serial` (whole repository, real kernel) | 1 failure (the same one), 5 min 26 s |
| `pytest tests/blocks tests/core tests/engine` (the protected paths) | pass, 0 failures |
| `ruff check src/scistudio/explore`; `ruff check src tests` | pass |
| `mypy src/scistudio/explore` | pass, 12 files |
| `governs` manifest of both specs resolved against the tree | every module, contract, file and test path resolves |
| `sentrux scan .` / `sentrux check .` | **not available** — not on `PATH`, not importable as `python -m sentrux`. Not run. |
| 31 mutations across 11 modules | 30 applied, 29 caught, 0 survived (1 inert control) |
| Hostile HTTP probe: 47 requests against the real router | no 5xx, no orphan files (§5, P3-1 is the one behavioural note) |
| Real-kernel orphan probe: kernel PID before/after backend shutdown | no orphan — `shutdown_session_services()` works against a real process |

### 2.1 The environment gap, and how I closed it

The shared `.venv` cannot import `jupyter_client` or `ipykernel`, so 84 tests
skip there. `pyproject.toml` declares both as **core** dependencies in this
change (FR-059), so CI's `uv pip install --system -e ".[dev]"` installs them
and those 84 tests **do** run in CI. An audit that only ran the shared
interpreter would have judged a suite that CI does not run.

An isolated venv at `C:/Users/jiazh/AppData/Local/Temp/kv` has real
`ipykernel` 7.3.0 and `jupyter_client` 8.10.0 but could not collect
`tests/api`: `fastmcp` refused to import its server support. The cause is not
`fastmcp` — it is `mcp.os.win32.utilities` importing `pywintypes`, which the
shared `.venv` supplies through `pywin32.pth` (`win32`, `win32\lib`,
`Pythonwin`) and which a venv built from it does not inherit. Putting those
three directories on `PYTHONPATH` closes the gap:

```
PYTHONPATH="<worktree>/src;<.venv>/Lib/site-packages/win32;.../win32/lib;.../Pythonwin"
```

With that, every kernel-backed test in `tests/explore` **and** `tests/api` runs
on this machine. That is how P1-1 was found: it hides in exactly the set of
tests that ran in neither interpreter.

---

## 3. P1 — blocks

### P1-1. The one real-kernel API test asserts a type name production does not produce, and will fail CI

`tests/api/test_explore_routes.py:1935`

```python
assert by_name["greeting"]["type_name"] == "str"
```

The value is `"Text"`. `scistudio.explore.kernel_bridge.bindings()` sets
`type_name=_safe_scistudio_type_name(value) or native`, and
`scistudio_type_name` (`src/scistudio/explore/kernel_bridge.py:308-309`)
returns `"Text"` for any `str` — deliberately, with a docstring explaining that
answering `type(value).__name__` "would hand packaging a *native* name — `str`,
`ndarray` — that resolves against nothing".

The sibling assertion 900 lines above, over the fake bridge, has the right
expectation:

```python
tests/api/test_explore_routes.py:1026:  assert by_name["greeting"]["type_name"] == "Text"
```

so the two tests in the same file disagree about the same field.

**Evidence.** Run twice, with a real ipykernel 7.3.0, once as part of
`tests/api/test_explore_*` and once as part of the whole `-m serial` phase:

```
FAILED tests/api/test_explore_routes.py::test_a_real_kernel_runs_a_cell_and_publishes_its_events
E       AssertionError: assert 'Text' == 'str'
E         - str
E         + Text
tests\api\test_explore_routes.py:1935: AssertionError
```

**Why this reaches CI.** The test carries `@needs_kernel`, which skips only
when `jupyter_client`/`ipykernel` are not importable. This change adds both to
`[project].dependencies`, and `.github/workflows/ci.yml:127` installs
`-e ".[dev]"`, so both are importable on the runner. The test also carries
`@pytest.mark.serial`, and CI runs a second phase `pytest -n 0 -m serial`
(`ci.yml:163`), so it is collected. Its own fixture (`real_harness`) prepends
`Path(scistudio.__file__).parent.parent` to `PYTHONPATH`, which guarantees the
kernel can import `scistudio` — which is precisely the condition under which
the bridge answers `"Text"`. There is no environment in which this test both
runs and passes.

**Fix.** Change the expectation to `"Text"` (and, if the native reading is
wanted too, assert `native_type_name == "str"`, which the `Binding` already
carries).

---

## 4. P2 — fix before merge

### P2-1. The FR-008/FR-060 depth rule checks three files, not the subsystem — and the nine it skips are the ones its docstring says it exists for

`tests/architecture/test_layer_deps.py:301-330`

`test_explore_never_imports_upward_at_any_depth` opens:

> `test_layer_does_not_import_forbidden` walks each module's top level. That is
> the correct depth for "what does importing this cost", and the wrong depth
> for "what may this subsystem reach": the explore runtime defers imports
> inside functions as a matter of course — `jupyter_client` in `build_kernel`,
> `packaging` in `cell_marks`, the kernel and bridge classes in the service's
> factories — **so a lazy `import scistudio.api` inside a method is the shape a
> violation would actually take here**, and the module-level walk cannot see
> it.

Its loop is then:

```python
for filepath in (f for f in _collect_py_files("explore") if f.name in FR_035_CONSTRAINED_MODULES):
```

`FR_035_CONSTRAINED_MODULES` is `{"__init__.py", "dependency_analysis.py",
"fingerprint.py"}` (line 447), the spec-2 allowlist. So the nine modules that
"defer imports inside functions as a matter of course" — `session.py`,
`kernel.py`, `kernel_bridge.py`, `block_call.py`, `notebook.py`,
`notebook_api.py`, `queue.py`, `packaging.py`, `lineage.py` — are the nine the
test does not walk. FR-060 and SC-014 are enforced for them at module level
only.

**Evidence.** I appended to `src/scistudio/explore/session.py`:

```python
def _planted_violation():
    import scistudio.api.routes.explore  # planted
    from scistudio.engine.scheduler import _dispatch  # planted
    return scistudio, _dispatch
```

`pytest tests/architecture/test_layer_deps.py` → **19 passed**. The same
`import scistudio.api` written at module level in the same file fails
`test_layer_does_not_import_forbidden[explore]` as expected. File restored;
`git status` clean.

`test_the_explore_depth_rule_catches_a_planted_import` does not cover this: it
exercises `_runtime_imports_at_any_depth` against a `scratch` **string**, so it
proves the helper works and says nothing about which files the helper is
pointed at.

**Fix.** Walk every file under `explore/` in the depth test; keep
`FR_035_CONSTRAINED_MODULES` for the *third-party allowlist* test, which is
what spec 2 FR-035 actually scopes to those three modules.

### P2-2. The other direction — engine → explore — is module-level only, and import-linter has no explore contract

`tests/architecture/test_layer_deps.py:404-426`

`test_engine_does_not_import_explore` uses `_get_imports_from_file`, which
walks `tree.body` only. Its docstring says "Without this, the engine could take
a direct dependency on the session service and every other rule here would
still pass" — but the engine's interactive dispatch already imports lazily
inside the function (`from scistudio.blocks.base.interactive import ...` at
`_dispatch.py:487`), so a lazy import is the shape a violation would take there
too.

**Evidence.** I inserted at the top of `_run_interactive` in
`src/scistudio/engine/scheduler/_dispatch.py`:

```python
from scistudio.explore.session import SessionService  # planted lazy engine->explore import
```

`pytest tests/architecture` → all pass (1 unrelated skip). File restored;
`git status` clean.

Separately: `pyproject.toml`'s `[tool.importlinter]` section carries contracts
for core, blocks, engine, utils, workflow, ai and previewers, and **none for
`scistudio.explore`**. The CI job "Import Contracts" (`ci.yml:181`) therefore
checks nothing about this subsystem in either direction.

**Fix.** Use `_runtime_imports_at_any_depth` in the engine test as well, and
add a `forbidden` contract for `scistudio.explore` (and an engine → explore
one) to `[tool.importlinter]` so the rule has a second, independent enforcer.

### P2-3. FR-055's durable half is written but never wired: an object a notebook declares through `scistudio.output` is a reclaim candidate

FR-055: *"Objects named in `scistudio.output` MUST be durable; every other
object a session produces MUST be a reclaim candidate."*

Both halves exist as code. Only the reclaim half is reachable.

- `DECLARED_OUTPUT_DIRECTION` (`core/lineage/store.py:69`) is written in
  exactly one place in `src/`: `ExploreLineage.declare_output`
  (`explore/lineage.py:446`).
- `declare_output` has **no caller in `src/`**. Grep over the whole tree finds
  it only in `tests/explore/test_explore_lineage.py:427,449`. The same is true
  of `durable_paths` and `reclaimable_paths`.
- `plan_retention` reads the durable set through
  `store.session_declared_output_paths()`
  (`core/lineage/retention.py:271`), whose SQL requires a `block_io` row with
  `direction = 'declared_output'`. With no writer, that set is always empty.
- The reclaim half *is* live: `record_block_call` fills
  `produced_by_execution` on every output row
  (`explore/lineage.py:392`), which is exactly what
  `artifact_paths_produced_by_sessions()` selects on.

**Evidence** (scripted, against a real `LineageStore` and a real artifact
directory under `data/zarr/`):

```
blocked_reason       : None
durable_session_paths: frozenset()
candidates           : ['...\\data\\zarr\\wf-1\\blk-1\\declared.zarr']
declared_output edges: set()
```

The object was produced by a block call inside a session and would have been
named by `scistudio.output`. Retention offers it for reclamation.

The session side does track declarations — `KernelBridge.declared_outputs`
and `notebook_api.declared_outputs()` hold name → declaration — but nothing
joins that to the `DataObjectRow` retention decides on.

The tests do not catch this, and it is worth being precise about why. I removed
the durable half from the planner (`session_durable = set()`) and two tests
failed:

```
FAILED tests/explore/test_explore_lineage.py::test_retention_keeps_the_declared_object_and_reclaims_the_rest
FAILED tests/explore/test_explore_lineage.py::test_a_project_with_only_sessions_is_not_an_empty_lineage_database
```

Both build their fixture through `_session_with_two_objects`
(`tests/explore/test_explore_lineage.py:431`), which calls
`lineage.declare_output(...)` itself. So the **only writer of a
`declared_output` edge anywhere in the repository is a test helper**: the
planner's durable branch is well tested against input no running system
produces.

**Fix.** Call `declare_output` from wherever a session's declared name resolves
to a recorded object (the cell-run or block-call recording path), or, if the
join genuinely cannot be made in session mode, say so in the spec instead of
stating FR-055 as a MUST.

### P2-4. FR-042's reopen-from-node has no route: `reopen_target` is built and called by nothing

FR-042: *"Double-clicking a packaged block's node MUST open a session on the
block's notebook copy **bound to the node's most recent run inputs**, and
packaging again from that session MUST replace the copy and the declaration in
place."*

`packaging.reopen_target` (`explore/packaging.py:1109`) resolves the copy, the
declaration and the recorded commit, and its own docstring ends:

> binding the session to the node's most recent run inputs is **the caller's**,
> because only the caller knows which run that was.

There is no caller. Grep over `src/` finds `reopen_target` only at its own
definition; the two other hits are in
`tests/explore/test_packaged_block.py:577,586`.

The API cannot substitute for it. `POST /api/explore/sessions` with
`source: "notebook"` calls `service.open_notebook(payload.path)`
(`api/routes/explore.py:862`) and ignores `run_id`; the request model's own
docstring says this source "binds to nothing"
(`api/routes/explore.py:392-394`). `SessionService.open_notebook` accepts a
`bound_run` keyword, and the route never passes one. So a frontend can reopen
the copy, or bind a session to a run, but not both — which is the whole of
FR-042.

`test_every_operation_of_fr_056_has_a_route` does not catch this because
FR-056's sentence does not name "reopen a packaged block's notebook"; the
surface test is faithful to FR-056 and FR-042 falls between the two
requirements.

**Fix.** Either give the `notebook` source an optional `block_id`/`run_id` that
`open_notebook` binds, or add the reopen operation to FR-056 and route it —
and add the case to the FR-056 surface table so it stays routed.

### P2-5. The SC-007 end-to-end test compares two hand-written shims, on a docstring premise that is no longer true

`tests/explore/test_packaged_block.py:22-31`:

> **The notebook helpers.** `scistudio.input` / `scistudio.output` are T-004's
> module and **are not on this branch yet**. The fixture notebook therefore
> binds the name `scistudio` in its first cell to a small object that reads and
> writes the exchange folders […] When T-004 lands, the first cell of the
> fixture is deleted and nothing else here changes.

T-004 has landed on this branch. `src/scistudio/explore/notebook_api.py`
implements `input`, `output` and `load` in both modes, and
`src/scistudio/__init__.py` exposes them lazily:

```
>>> import scistudio
>>> scistudio.input, scistudio.output, scistudio.load
(<function input ...>, <function output ...>, <function load ...>)
```

The fixture still injects `SHIM_CELL` — a five-line `_Exchange` class — as
cell one of every packaged run, and `run_as_session` injects a separate
`_Session` object for the comparison. SC-007 states *"A packaged fixture
notebook registers as a block with the declared ports, runs in a workflow, and
produces outputs equal to the session's."* As written, the outputs compared are
two shims', not the shipped helpers'. FR-011 (packaged mode reads and writes
the Code Block's exchange folders) is unit-tested well in
`tests/explore/test_notebook_api.py` — in-process, both modes, real exchange
folders — but is never exercised through a real `nbconvert` run of a real
packaged block.

Second, smaller point on the same test: `_nbconvert_executable()` skips the
whole end-to-end case when `jupyter-nbconvert` is not on `PATH`.
`nbconvert` appears nowhere in `pyproject.toml` (neither core nor `[dev]`), so
on a CI runner the skip fires and SC-007 is not measured there. On this machine
it ran only because a base conda install happens to put
`jupyter-nbconvert` on `PATH`. The test file names this as an existing
repository pattern, so it is not new — but it means User Story 4's acceptance
bar is unverified in CI.

**Fix.** Delete `SHIM_CELL` as the docstring's own plan says, and let the
fixture use the real helpers; and either declare `nbconvert` in `[dev]` or
record explicitly that SC-007 is measured locally and not in CI.

---

## 5. P3 — worth fixing, not blocking

### P3-1. `open over a file` accepts absolute paths and `../` traversal out of the project

FR-002 says a session is openable "over a file **in the project's data tree**".
`SessionService.open_over_file` (`explore/session.py:1758-1760`) does no
containment check: an absolute path is made project-relative through
`_relative_posix`, and a relative path is used verbatim.

**Evidence** — real requests against the real router (no 5xx anywhere in a
47-request probe; these three returned 200):

```
200 POST /api/explore/sessions {"source":"file","path":"../../../../etc/passwd"}
200 POST /api/explore/sessions {"source":"file","path":"C:/Windows/win.ini"}
200 POST /api/explore/sessions {"source":"file","path":"does/not/exist.csv"}

EXPLORE DIR: ['a_b.ipynb','con.ipynb','escape.ipynb','exist.ipynb',
              'passwd.ipynb','t-2.ipynb','t.ipynb','win.ipynb']
```

The generated first cell records the escaping path verbatim:

```python
>>> first_cell_source(file_path="../../../../etc/passwd")
'import scistudio\n\npasswd = scistudio.load("../../../../etc/passwd")'
```

The notebook *file* is contained — the `name` is sanitised, so `name:
"../escape"` produced `explore/escape.ipynb` — so this is not a write-escape.
It is a spec deviation with two practical costs: the notebook is not portable,
and a project's explore directory can hold a notebook whose data source is
outside the project. A missing file being accepted is correct and documented
(spec §2 edge cases); a path outside the data tree is not.

### P3-2. The CI serial phase now has ~54 % of its wall-clock budget consumed on a fast machine

`ci.yml` wraps the serial phase in `timeout 600`. Measured here with a real
kernel:

- whole repository, `pytest -n 0 -m serial`: **5 min 26 s** (326 s)
- ADR-054's own serial tests alone: **3 min 13 s** (193 s), no single test over
  5.4 s (so `--timeout=60` is not at risk)

326 s against a 600 s shell kill, on a 32-core development machine, with a
GitHub-hosted runner generally slower. This is an observation about headroom,
not a defect; it is worth knowing before the next batch of process-spawning
serial tests lands.

### P3-3. A-009's "the cost is the same order" was not measured; it holds, and nothing keeps it holding

A-009 says explore commits are written with plumbing "rather than the
add-and-commit path ADR-054 §6.6 measured; **the cost is the same order**".
ADR-054 §6.6 states 27–31 ms for add+commit. No test in
`tests/core/versioning/test_explore_ref_commits.py` measures anything (no
`perf_counter`, no bound).

I measured it. Fifty-cell notebook (9 142 bytes), 200 tracked files, 40
commits, same repository, same machine:

| path | min | median | p90 |
|---|---|---|---|
| `GitEngine.commit_entries_to_ref` (plumbing) | 77.7 ms | **85.0 ms** | 102.5 ms |
| `git add` + `git commit` | 56.9 ms | **61.4 ms** | 78.9 ms |

1.4x — same order, so **the assumption survives measurement**. Two notes: the
ADR's 27–31 ms is not reproducible on Windows for either path (process spawn
dominates, and the plumbing path spawns five git processes to add+commit's
two), and the working tree and branch log were confirmed untouched after 40
explore commits (`git status --porcelain` empty, branch log still 1 entry),
which is FR-029 holding in the same run.

### P3-4. ADR-054 §11 understates what has landed, and the ADR is `agent_editable: false`

`docs/adr/ADR-054.md:1266-1271` now reads "governs the `scistudio.explore`
package, **whose dependency analysis (§6) has landed**; the surfaces still in
`planned_governs` become governed as they land." The session runtime of §4,
§5, §6.3–§6.7 and §7 has also landed in this change — `session.py`,
`kernel.py`, `kernel_bridge.py`, `block_call.py`, `queue.py`, `packaging.py`,
`lineage.py`, `notebook*.py` — so the sentence is behind the tree.

Separately, `ADR-054.md` carries `agent_editable: false`, and this change edits
both its frontmatter (the `governs` / `planned_governs` migration) and §11.
`docs/ai-developer/specific_rules/document-standards.md:56` defines that flag
as "`false` for governance ADRs **unless owner explicitly allows edits**".
Whether the owner allowed it is not visible in any repository document I am
permitted to read, so I record this as needing owner confirmation rather than
as a violation. It is worth noting that spec §4.2 explicitly declines to edit
ADR-039 for the same reason, which makes the different treatment of ADR-054
worth a sentence somewhere in the record.

### P3-5. A-012's first half is vacuous as built

A-012: *"The file watcher that suppresses product-written files must not
suppress notebook writes the session needs to observe from outside, and must
not reload the session on its own writes. **T-005 verifies both.**"*

The second half is verified (`tests/explore/test_notebook_store.py:711` ff.,
`test_explore_session.py:445` — the store's own write is not an external edit,
by digest). The first half has no test, and cannot: the only filesystem
watcher in the tree, `api/routes/workflow_watcher.py`, observes
canvas-relevant edits and does not watch `{project}/explore/`. External-change
detection is pull-based through `NotebookStore.has_external_change()`. The
assumption is harmless as built; the sentence claiming T-005 verifies both is
not accurate.

### P3-6. Small dead ends

Introduced by this change and called from nowhere in `src/` outside their own
file (tests aside):

- `ExploreLineage.origin_of`, `uses_of`, `session_of`, `session_behind_step`
  — the FR-054 "the session the step came from is reachable from the run"
  queries. Written and tested; no production caller and no route, so nothing
  surfaces them.
- `LineageStore.list_explore_sessions`, `list_session_block_executions` — same.
- `notebook_api.clear_declared_outputs` — appears only in `__all__`.

These are defensible as a query API for the frontend spec to build on. They are
listed so the choice is deliberate rather than accidental.

---

## 6. What the tests do prove (the mutation campaign)

Thirty mutations plus one inert control, applied one at a time to production
modules with the file restored afterwards, each run against the tests that name
the behaviour.
Run with the real-ipykernel interpreter, because with the shared `.venv`
three of them survive purely because the tests that would catch them skip.

| # | Mutation | Requirement | Result |
|---|---|---|---|
| M1 | `_plain_name_target` admits `Subscript`/`Attribute` | FR-018 | caught (5) |
| M2 | drop the marks clause of the skip rule | FR-024 / A-004 | caught (1) |
| M3 | drop the last-bound-by clause of the skip rule | FR-024 / A-004 | caught (2) |
| M4 | run-with-upstream no longer forces the named cell | FR-024 | caught (1) |
| M5 | block default beats node override | FR-044 | caught (11) |
| M6 | default policy becomes `replay` | FR-044 / FR-045 | caught (2) |
| M7 | dispatch never takes the replay branch | FR-045 | caught (4) |
| M8 | `cell_installs_packages` always `False` | FR-012 | caught (6) |
| M9 | drop `GIT_INDEX_FILE` (use the real index) | FR-029 | caught (9) |
| M10 | pack interval 256 → 100 000 | FR-031 | caught (1) |
| M11 | ref namespace → `refs/heads/explore/` | FR-028 / FR-029 | caught (31) |
| M12 | `strip_outputs` returns the document unchanged | FR-028 | caught (4) |
| M13 | session-id ref guard accepts anything | FR-001 | caught (13) |
| M14 | entry-path guard accepts `.git`, `..` | (safety) | caught (9) |
| M15 | packaging ignores never-run/stale/out-of-order | FR-039 | caught (10) |
| M16 | packaging ignores unresolved reads | FR-039 | caught (3) |
| M17 | packaging ignores interactive block calls | FR-039 / FR-050 | caught (3) |
| M19 | packaged run executes the whole notebook | FR-040 | caught (6) |
| M20 | version opt-in applies to any block | FR-054 / ADR-038 §3.3 | caught (4) |
| M21 | block-call record loses its session FK | FR-051 | caught (14) |
| M22 | `set_analysis_record` is a no-op | FR-032 | caught (4) |
| M23 | run-with-upstream never skips | FR-024 | caught (2) |
| M24 | every cell reads as enabled | FR-033 / analysis FR-014 | caught (8) |
| M25 | no coalescing of a queued cell | FR-017 | caught (2) |
| M26 | no panel freeze during a run | FR-025 | caught (3) |
| M27 | environment reference is random, not content-addressed | FR-034 | caught (6) |
| M28 | branch commit payload keeps outputs | FR-028 / FR-036 | caught (1) |
| M29 | *control:* an inert comment edit | — | survived, as intended |
| M30 | retention drops the FR-055 durable set (wide selection) | FR-055 | caught (3) |
| M31 | retention drops the FR-055 durable set (Explore-side only) | FR-055 | caught (3) — but see P2-3 |

(M18 — "a notebook with no declared output is not refused" — was not applied:
the pattern was not unique in the file. The condition is covered by
`test_a_notebook_with_no_declared_output_refuses`.)

Nothing survived except the deliberate control. Where a mutation was caught by
a single test, that test was the one the requirement names. M30/M31 are the
exception that proves P2-3: the durable branch is caught, by tests that write
the `declared_output` edge themselves.

Other things I checked and found sound, listed so a reader knows they were
looked at rather than skipped:

- **No orphan process.** A real ipykernel launched through the routes is gone
  after `TestClient` exits the lifespan (`shutdown_session_services` in
  `api/app.py:204-211`). PID observed alive during the run, absent 2 s after
  shutdown.
- **No bare 500.** 47 hostile requests across every route: unknown session ids,
  unknown cell ids, refused snippets, packaging a notebook that cannot be
  packaged, a window with no kernel, ending a kernel that does not exist. Every
  answer was a 200, 404, 409 or 422 in the documented refusal shape. The one
  deliberate design note is at `_refusals()`
  (`api/routes/explore.py:338-353`): the map is a closed list and anything
  unrecognised becomes a 500 on purpose.
- **No half-written block.** A refused `POST .../package` leaves
  `{project}/blocks/` empty.
- **Block-name sanitisation.** `block_file_stem` reduces `../../evil` → `evil`,
  `a/b` → `a_b`, `C:/abs` → `c_abs`, and refuses `..`, `""` and whitespace.
- **The WebSocket really carries the events.** `tests/api/test_explore_routes.py`
  connects a real `/ws` client, exchanges the workflow's own ping/pong on the
  same socket, and asserts the five-frame sequence of a cell run — including
  the cross-thread hop that `ws.py` adds. That is a genuine end-to-end
  assertion, not a subscriber-list check.
- **The fake bridge does not lie.** `_FakeBridge.bindings` calls the production
  `scistudio_type_name` rather than mirroring it, and says why in its
  docstring. This is the right shape; P1-1 is the one assertion that was not
  brought along.
- **The timed criteria are measured, not assumed.** SC-007's fingerprint bound
  and SC-010's 500-cell bound are real timed tests with a documented sampling
  method, published margins, and a `dict_1m` fixture built specifically because
  the budget's worst-case branch had never been timed. FR-025's "declared in
  one place" is asserted by counting the assignment in the source.
- **The `governs` manifests resolve.** Every module, contract, file and test
  path in both specs' frontmatter exists (the single failure to import
  `scistudio.explore.kernel` is this machine's missing `jupyter_client`).
- **The protected paths are additive.** `tests/blocks`, `tests/core` and
  `tests/engine` pass unchanged, and the whole non-serial suite passes with
  zero failures. The one behavioural change to a pre-existing path worth naming
  is `notebook_run_environment`: every notebook Code Block run now receives the
  `SCISTUDIO_*` exchange variables, not only packaged ones. It is additive in
  the sense that a notebook ignoring them is unaffected, and
  `tests/blocks/code/test_codeblock_notebooks.py` passes untouched.
- **Deferred work is tracked.** `TODO(#2243)` in `dependency_analysis.py:1237`
  and the `#2240` reference in the session teardown carry what is deferred, why,
  and the decision they rest on, in the AGENTS.md §3.6 shape.

---

## 7. Recommendation

**Pass with fixes.** P1-1 must be fixed before this can go green in CI. P2-1
through P2-5 should be fixed in the same pass: two of them are architecture
tests that would report success while the rule they name is broken, and three
are requirements stated as MUST whose production wire is absent. The P3 items
are for the record and the owner's judgement.

Not run, and not substitutable: `sentrux scan .` / `sentrux check .` — neither
a `sentrux` executable nor a `sentrux` module is present in this environment.
