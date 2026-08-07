# Audit: filesystem-write surfaces and `sys.path` manipulation (no-context)

> **Handling note.** P1-1 in this report was an unpatched remote-code-execution
> defect when the report was written. Its runnable reproduction has been redacted
> from this file (see the notice in §5). Do not reintroduce exploit detail into
> this file, the changelog, the spec, or commit messages.


- Date: 2026-08-07
- Persona: `audit_reviewer`, **no-context** mode
- Branch / worktree: `audit/adr-053-spec1-write-path` @
  `C:/Users/jiazh/workspace/SciStudio-wt-audit-sec`
- Tree judged: head `327ae238`, merge-base with `origin/main` = `b485e293`
- Host: Windows 11 Pro 26200, CPython 3.13, `PYTHONPATH=./src` (no editable install)
- Judged against: `docs/specs/adr-053-personal-tool-library.md`,
  `docs/adr/ADR-053.md`, `docs/architecture/ARCHITECTURE.md`,
  `docs/architecture/sentrux-rules.md`, and the source tree itself.

Per the dispatch I did not read any issue, any file under `docs/planning/`, any
other dispatch prompt, any PR text, or any commit message for the work under
review. I also deliberately did not read `docs/audit/2026-08-07-adr-053-spec1-track-a.md`,
even though committed audit output is permitted, because reading another
reviewer's findings would have told me where to look and destroyed the
independence this dispatch exists to buy. Every claim below rests on the source
tree, the governing docs, or a command I ran myself.

Where history was needed to answer "did adding the second door weaken the
first", I used `git diff <merge-base>..HEAD -- <path>` — code, not commit
messages.

---

## 0. What I actually ran

| Command | Result |
|---|---|
| `pytest tests/api tests/blocks tests/core -q --no-cov` | 3 failures, all reproduce at merge-base `b485e293` (§7.1) |
| Same 3 tests re-run in the merge-base worktree `C:/Users/jiazh/workspace/SciStudio` (@ `b485e293`) | all 3 fail identically → environmental, not attributable to this tree |
| `pytest tests/api/test_user_library_write.py tests/blocks/test_dropin_type_import.py --cov=scistudio.api.routes.user_library --cov=scistudio.core.dropins --cov-report=term-missing` | `user_library.py` 77 %, `core/dropins.py` 93 %; missing lines drive P2-5 |
| import-linter (`importlinter.cli.lint_imports_command`, `--config pyproject.toml`) | **13 contracts kept, 0 broken** |
| `scripts/docs/build_reference.py --generate-only` then `git diff` | generated reference drifts (§P3-7); drift is **pre-existing** — `git diff b485e293..HEAD` touches none of those paths. Working tree restored. |
| Sentrux | **not available on this host** — `sentrux` is not on `PATH` and no Sentrux MCP tool was exposed to this session. No Sentrux claim is made anywhere in this report. |
| Probe 1 `p1_userlib_paths.py` — 37 filename shapes through `_resolve_user_library_file` | §2.1 |
| Probe 2 / 2b / 2c `p2_shadowing.py`, `p2b_strptime.py`, `p2c_inprocess.py` | P1-1 |
| Probe 3 `p3_write_effects.py` — drive the real `PUT` handler; symlink escape | §2.1, P2-2; symlink creation **blocked by host** |
| Probe 4 `p4_junction_escape.py` — NTFS junction reparse-point escape, both endpoints | §2.2 — **rejected** |
| Probe 5 `p5_tmp_and_scan.py` — does the scanner execute the write path's temp file? | P2-2 — **yes** |
| Probe 6 `p6_hostile_dropin.py` — `SystemExit` / `os._exit` / infinite loop in a drop-in | P2-1 |
| Probe 7 `p7_scaffold_block.py` — MCP `scaffold_block` name argument | P2-3 — **escapes** |
| Probe 8b `p8b_concurrency.py` — interleaved `prepended_sys_paths` windows | P3-1 |
| Probe 9 `p9_export_path.py` — `POST /api/workflows/export-path` | P2-4 — **no containment at all** |
| Probe 10 `p10_rule4.py` — junction to a deeper dir inside the root | §2.2 — **rejected** |

All probes ran against scratch trees created with `tempfile.mkdtemp` and a
`Path.home` patched to point inside them. No probe touched the real
`~/.scistudio`. One probe (`p7`, the `scaffold_block` traversal) escaped its own
scratch root and left `%TEMP%\.bashrc_like.py`; I verified and deleted it.

### Host limitation that bears directly on this audit

**This host does not permit creating symbolic links.**

```
OSError: [WinError 1314] A required privilege is not held by the client:
  '...\outside\victim.py' -> '...\.scistudio\blocks\escape.py'
```

The repository's own symlink test skips for the same reason:

```
SKIPPED [1] tests\api\test_user_library_write.py:179: symlink creation is not permitted in this environment
SKIPPED [1] tests\api\test_block_origin_tiers.py:158: symlink creation is not permitted in this environment
```

So: **I did not execute a symlink escape and I am not reporting symlink
containment as verified.** What I *did* execute is the closest available
equivalent — an NTFS **directory junction**, which needs no privilege and which
`os.path.realpath` follows identically. Those escapes were attempted and
rejected (§2.2). A junction is a real reparse point, so this does establish that
the containment is a resolved-real-path test rather than a string-prefix test;
it does **not** establish behaviour for a file symlink specifically. Anyone
reading this should treat POSIX/CI symlink coverage as the outstanding half.

---

## 1. Complete enumeration of filesystem-write endpoints

"Endpoint" here means an HTTP route or MCP tool that causes bytes to be written,
renamed, or removed on disk. Column *New?* is relative to merge-base `b485e293`.

| # | Surface | New? | Root the write is confined to | How containment is decided | Overwrite |
|---|---|---|---|---|---|
| W1 | `PUT /api/user-library/file` (`routes/user_library.py`) | **yes** | `~/.scistudio/{blocks,types}` | bare-filename validation → `mkdir` → `os.path.realpath` on root and candidate → `os.path.commonpath` → resolved parent **must equal** root → suffix must be `.py` | **409 unless `overwrite:true`** |
| W2 | `GET /api/user-library/file` | **yes** | same as W1 (read; shares `_resolve_user_library_file`) | same | n/a |
| W3 | MCP `promote_to_user_library` (`ai/agent/mcp/tools_library.py`) | **yes** | `~/.scistudio/blocks` | `_library_filename` (bare `.py`, drive/abs/`..`/separator rejected) → `_safe_under(library_root, name)` → `destination.parent != library_root` → refuse | **`FileExistsError` unless `overwrite=True`** |
| W4 | `PUT /api/projects/{id}/file` (`routes/projects.py`) | no (constraint unchanged; see §3) | project root, any depth | `..`-segment reject → `realpath` + `commonpath` → extension in `ADR036_FILE_ALLOWLIST` (9 ext.) → parent dir must exist | **silent overwrite** |
| W5 | `POST /api/workflows/export-path` | no | **none** | `Path(body["path"])` used verbatim | **silent overwrite** (P2-4) |
| W6 | `POST /api/workflows/import`, `/import-path` | no | `<project>/workflows/{id}.yaml` via `runtime.workflow_path` | id-derived filename under `require_active_project()`; duplicate-id conflict → 409 | overwrite of the canonical id path |
| W7 | `POST /api/workflows/import-subworkflow` | no | `<project>/subworkflows/` | `Path(project.path) / "subworkflows" / src.name`; numeric suffix on collision | never (suffixes) |
| W8 | `POST /api/data/upload` | no | `<project>/data/raw/` | `Path(filename).name`, reject empty / dot-leading | **silent overwrite** |
| W9 | `POST /api/previews/sessions/{s}/resources/{r}/save` | no | `$HOME` or system temp | must be absolute → `_resolve_safe_path` (`realpath` + `commonpath` against home/tempdir) → parent must be a dir | silent overwrite |
| W10 | `GET|POST /api/diagnostics/bundle` with `{"path": …}` | no | `$HOME` or system temp | identical to W9 (same helper) | silent overwrite |
| W11 | `POST /api/plots` , `POST /api/plots/{id}/relink` | no | `<project>/plots/<plot_id>/` | `validate_plot_id` regex → `.resolve()` → `relative_to(plots_root)` | `FileExistsError` unless `overwrite` |
| W12 | `POST /api/tutorials/run-first-workflow/bootstrap` | no | caller-supplied `parent_path` (project creation) | `runtime.create_project` + `FileExistsError` → 409 | no |
| W13 | `POST /api/packages/local`, `/{pkg}/update`, `/rollback`, `DELETE /{pkg}` | no (refresh call widened only) | `~/.scistudio/plugins/packages/…` | gated on `_is_bundled_desktop_run()` → 403 otherwise; package-manager internal | manager-controlled |
| W14 | `POST /api/git/*` (`commit`, `restore`, `branch/*`, `merge/*`) | no | project git repo | git plumbing | git semantics |
| W15 | MCP `scaffold_block` (`tools_authoring.py`) | no | **nominally `<project>/blocks/`, actually none** | `blocks_dir / f"{name}.py"` — `name` is **unvalidated** (P2-3) | `FileExistsError` if target exists |
| W16 | MCP `write_workflow`, `update_block_config`, `finish_ai_block` | no | project root | `_resolve_project_path` → `_resolve_project_root` + `_safe_under` (`resolve()` + `relative_to`) | atomic replace |
| W17 | MCP/API side-effect writes: `.scistudio/mcp.sock.port`, `.scistudio/mcp.json`, `.scistudio/.session-state/**` | no | project `.scistudio/` | derived from project root | n/a |

Answering the dispatch's sub-questions for the three **new** doors (W1–W3),
with probe output in §2:

- **Traversal** (`..`, encoded, nested, mixed separators): rejected on W1/W2/W3.
- **Symlink escape**: resolved-real-path first, then `commonpath` — not a string
  prefix. Verified with junctions, **not** with symlinks (host limitation).
- **Absolute / UNC / drive-relative / other drive**: all rejected on W1/W2/W3.
- **Case / trailing separator**: trailing separators rejected; `.PY` **accepted**
  (P3-2); trailing space stripped; trailing dot rejected (415).
- **File type**: `.py` only on W1–W3 — but see P1-1, an underscore-prefixed `.py`
  is accepted and is exactly the class the FR-016 guard does not check.
- **Nested subdirectory**: refused on W1–W3 (rule 4 verified, §2.2).
- **Overwrite without opt-in**: not possible on W1–W3. **Possible** on W4, W5,
  W8, W9, W10 (P3-8).

---

## 2. Escapes attempted, and what happened

### 2.1 Filename shapes against `_resolve_user_library_file` (probe 1)

37 shapes; the interesting rows, verbatim:

```
dotdot posix    '../evil.py'                    REJECTED 403: The user library accepts a bare filename, not a path
dotdot win      '..\\evil.py'                   REJECTED 403: The user library accepts a bare filename, not a path
nested dotdot   '../../../../../../../../Windows/Temp/evil.py'  REJECTED 403
subdir          'sub/evil.py'                   REJECTED 403
abs win         'C:\\Windows\\Temp\\evil.py'    REJECTED 403: Absolute and drive-relative paths are not allowed
abs posix-style '/tmp/evil.py'                  REJECTED 403
drive-relative  'C:evil.py'                     REJECTED 403
other drive-rel 'D:evil.py'                     REJECTED 403
UNC             '\\\\server\\share\\evil.py'    REJECTED 403
UNC fwd         '//server/share/evil.py'        REJECTED 403
extended-length '\\\\?\\C:\\Windows\\Temp\\evil.py'  REJECTED 403
device ns       '\\\\.\\C:\\evil.py'            REJECTED 403
trailing sep    'evil.py/'                      REJECTED 403
trailing sep win 'evil.py\\'                    REJECTED 403
trailing dot    'evil.py.'                      REJECTED 415
empty / spaces  '' / '   '                      REJECTED 400
--- accepted ---
uppercase       'EVIL.PY'                       ACCEPTED -> ...\blocks\EVIL.PY
mixed           'evil.Py'                       ACCEPTED -> ...\blocks\evil.Py
underscore      '_strptime.py'                  ACCEPTED -> ...\blocks\_strptime.py
dunder          '__init__.py'                   ACCEPTED
ADS stream      'a.py:b.py'                     ACCEPTED (write later fails, WinError 123)
reserved        'NUL.py' / 'CON.py' / 'COM1.py' ACCEPTED (real files created on this host)
null byte       'ev\x00il.py'                   ACCEPTED (write raises uncaught ValueError)
newline in name 'evil\n.py'                     ACCEPTED (write fails, WinError 123)
url-encoded     '%2e%2e%2fevil.py'              ACCEPTED as a literal filename (contained; harmless)
```

The Windows-specific containment the dispatch asked about is genuinely present
and correct: absolute, UNC, extended-length (`\\?\`), device-namespace (`\\.\`),
and drive-relative (`C:evil.py`) forms are all refused, and the drive test is a
separate condition rather than an implication of the basename test — which is
right, because `Path("C:evil.py").name` is the innocent-looking `evil.py`.

### 2.2 Reparse-point escapes (probes 4 and 10) — attempted, rejected

Symlinks are unavailable (see §0). Junctions are not, and `realpath` follows
them the same way.

```
[user-library] junction ...\.scistudio\blocks\escape.py -> ...\outside   created=True
[user-library] REJECTED 403: Path escapes the user library root
[project]      junction ...\project\blocks\out -> ...\outside            created=True
[project]      junction traversal    REJECTED 403: Path escapes project root
[project]      dotdot                REJECTED 403: Path traversal is not allowed
[project]      abs other path        REJECTED 403: Path escapes project root
[project]      abs other drive       REJECTED 403: Path escapes project root
[project]      UNC                   REJECTED 403: Path escapes project root
[project]      nested dotdot mixed   REJECTED 403: Path traversal is not allowed
```

Rule 4 ("the file must land directly in the root") — junction inside the root
pointing at a *deeper* directory inside the same root, i.e. the one case that
passes `commonpath` and must still be refused:

```
junction ...\blocks\deep.py -> ...\blocks\inner\sub
  deep.py     REJECTED 403: User library files must live directly in the target directory
  shallow.py  ACCEPTED -> ...\blocks\inner        (PUT then returns 400 "Path is a directory")
```

So the containment logic on W1–W4 is sound for every escape I was able to
execute on this platform.

### 2.3 One case the containment does *not* cover, by construction

`root = os.path.realpath(str(declared_root))` resolves the **root** before
comparing. If `~/.scistudio/blocks` is itself a reparse point, every write
follows it:

```
declared root  : ...\scistudio_probe_linkroot_...\.scistudio\blocks
resolved target: ...\scistudio_probe_linkroot_...\real_blocks_target\x.py
```

This is inherent to `realpath` and the root is by definition user-owned, so I do
not call it a defect. It is worth knowing that "confined to `~/.scistudio/blocks`"
means "confined to wherever that name resolves to".

---

## 3. Do any two write endpoints have inconsistent constraints? Did the second weaken the first?

**Inconsistent: yes.** W1 and W4 differ on every axis — extension set (`.py`
only vs. nine extensions), depth (root only vs. any depth), and overwrite (409
vs. silent). That asymmetry is defensible: W4 is an editor save and W1 is a
library deposit. It is recorded here because the two are presented in the code
as siblings ("Error shapes match the project endpoint so one frontend error path
serves both") and only the *error shapes* actually match.

**Weakened by the second door: no, on the path constraint.**
`git diff b485e293..HEAD -- src/scistudio/api/routes/filesystem.py src/scistudio/api/file_contracts.py src/scistudio/ai/agent/mcp/_context.py` is **empty**, and the diff of `routes/projects.py` does not touch `_resolve_project_file`. `_safe_under` — the helper W3 newly shares with W16 — is byte-identical to merge-base; W3 passes it a different `root`, which is what the helper's `root` parameter is for. Probe 4 re-verifies W4's rejections directly. FR-009 holds.

**But one thing did widen, and it is worth naming precisely.**
`_maybe_reload_blocks_after_save` changed from

```python
if not _is_under_project_blocks_dir(project_root, target): return
... runtime.block_registry.hot_reload()
```

to

```python
if _project_dropin_dir(project_root, target) is None: return      # blocks OR types
... runtime.refresh_all_registries()
```

The *path* constraint on W4 is unchanged; the *consequence* of a permitted write
is not. `PUT /api/projects/{id}/file?path=types/<name>.py` previously did
nothing beyond writing bytes; it now triggers a full registry rebuild, which puts
`<project>/types` on `sys.path` and imports what is there. That makes W4 a second
door onto the FR-016 surface, and it inherits P1-1 through it. Nothing about
that is hidden — the docstring says so — but "the older endpoint gained a new
code-execution consequence" is the honest description, and it is not what FR-009
was written to protect against.

---

## 4. `sys.path` manipulation

### 4.1 Which directories, from where, for how long

`scistudio.core.dropins.dropin_import_roots(project_dir)` returns
`(<project>/types, ~/.scistudio/types, <user python site>)` — project tier
first, user tier unconditional. Four sites put them on `sys.path`:

| Site | Mechanism | Lifetime | Guard called first? |
|---|---|---|---|
| `blocks/registry/_scan.py::_scan_tier1` | `prepended_sys_paths(import_roots)` | scoped to `exec_module` | yes (`guard_dropin_type_roots`, reporting adapter) |
| `blocks/registry/__init__.py::instantiate` | `prepended_sys_paths(runtime_import_roots)` | scoped to the re-import | yes |
| `engine/runners/worker.py::_prepend_runtime_import_roots` | direct `sys.path.insert(0, …)` | **permanent, process lifetime** | yes |
| `core/types/registry.py::_scan_filesystem_dirs` | loads by file path, does **not** touch `sys.path` | n/a | yes, `bind=False` (verdict only) |
| `blocks/io/_unified_dispatch.py` | reaches `sys.path` transitively via `_scan_tier1` | scoped | via `_scan_tier1` |

Restoration on every exit path including exceptions: **yes**, verified.
`prepended_sys_paths` restores in `finally`; probe 2c:

```
sys.path restored exactly: True
sys.path restored after exception: True
```

`_sys_path_without` in `core/dropins.py` uses the same `finally` pattern.

**But restoring `sys.path` does not undo the import.** Anything imported inside
the window stays bound in `sys.modules` for the process lifetime (probe 2c):

```
inside window,  _pydecimal.__file__ = ...\.scistudio\types\_pydecimal.py
sys.path restored exactly: True
after window,   sys.modules['_pydecimal'].__file__ = ...\.scistudio\types\_pydecimal.py
after window,   marker still reachable: drop-in _pydecimal
```

So the scoping bounds *when a name can first be captured*, not *how long the
capture lasts*. This is the amplifier under P1-1.

**Concurrency: not safe** — see P3-1.

**Cross-process agreement (dispatch Q6): yes.** All four registration points go
through `core.dropins`; `blocks/io/_unified_dispatch.py` and
`core/types/serialization.py` read `SCISTUDIO_PROJECT_DIR`, which
`engine/runners/local.py::_worker_env` sets from the active project. I found no
directory trusted in one process and not another. `tests/api/test_registry_provisioning_parity.py` pins this.

### 4.2 Module shadowing detection — see P1-1

---

## 5. Findings

### P1 — blocking

#### P1-1. The FR-016 collision guard silently exempts every `_`-prefixed importable name, and a test pins the gap with a rationale that is factually wrong

`core/dropins.py::_importable_entries`:


> **Reproduction redacted by the manager.** This finding was an unpatched arbitrary-code-execution defect at the time this report was written, and this repository is public. The payload contents, probe script and step-by-step reproduction have been removed; the finding, the vulnerable code path and the required fix are unchanged above and below. The full reproduction remains in this file's git history and in the fix branch's regression tests.


The governing spec is explicit about what must be checked
(`docs/specs/adr-053-personal-tool-library.md` §5, FR-016):

> A name is any entry the directory makes importable, which is `<name>.py`
> *and* `<name>/__init__.py`; a plain subdirectory is not, since a namespace
> portion cannot displace a regular module found elsewhere on `sys.path`.

`_strptime.py` **is** an entry the directory makes importable. The code narrows
the spec's definition; the narrowing removes exactly the class of name that
matters most, because the most dangerous shadowable stdlib modules are
underscore-prefixed pure-Python modules that are imported *lazily*, long after
any scan: `_strptime` (imported by `datetime.strptime` / `time.strptime`),
`_pydecimal`, `_threading_local`, `_collections_abc`, `_pyio`, `_compat_pickle`.

**Probe 2 — the guard's verdict.** Six candidate files in a scratch
`~/.scistudio/types`:


**Probe 2b — what actually happens.** One file, `~/.scistudio/types/_strptime.py`,
containing a side effect and a hostile `_strptime_datetime`. Roots placed on
`sys.path` exactly as the product places them, then an ordinary
`datetime.strptime` call:


Arbitrary code from a user-writable directory ran, and every `strptime` call in
that process now returns whatever the file says.

**Two product-provided doors write such a file.** Probe 1 shows
`PUT /api/user-library/file?target=types&filename=_strptime.py` is accepted
(no drive, no separator, no `..`, `Path(name).name == name`, suffix `.py`), and
§3 shows `PUT /api/projects/{id}/file?path=types/_strptime.py` is accepted by
the allowlist and now triggers the registry rebuild that puts the directory on
`sys.path`. Neither door applies the FR-016 rule at write time — that is fine in
itself, the rule is a scan-time concept — but the scan-time rule then declines
to look.

**The gap is pinned by a test whose stated reason is untrue**
(`tests/blocks/test_dropin_type_import.py:496`):


A `_`-prefixed `.py` file on `sys.path` is importable by name — that is the
whole content of probe 2b. The docstring is the reason the gap survives review,
so fixing the code without fixing this test's justification will not hold.

Severity. I considered whether §14's "the blast radius is bounded by these
directories already executing arbitrary user code in-process (#1531)" covers
this, and I do not think it does. #1531 is about a *block* file the user
deliberately put in a scan directory being executed as a block. FR-016 is about
a *type* file capturing a module name so that **unrelated code silently gets the
wrong module**, in every process, for the process lifetime. The accident case is
ordinary: a user writes `types/_helpers.py` or `types/_strptime.py` as a private
helper — underscore precisely because they mean "don't register me" — and the
product responds by shadowing a stdlib module with no error anywhere. That is
the failure FR-016 exists to prevent, and the guard does not prevent it.

Shape of a fix (not a design instruction, just what the evidence bounds):
`_importable_entries` needs to yield `_`-prefixed `.py` files and `_`-prefixed
packages for the **collision** question, while the two registries keep skipping
them for the **registration** question. Those are different questions and the
underscore rule currently answers both.

---

### P2 — should fix

#### P2-1. A drop-in raising `BaseException` kills the process; the docstring says it cannot

`_scan_tier1` wraps `exec_module` in `except Exception`. `SystemExit`,
`KeyboardInterrupt`, and `os._exit` are outside that. There is also no timeout.

Probe 6 — hostile/broken file scanned first, healthy neighbour second, whole
scan run in a child process:

```
systemexit         rc=7           ['SCAN RAISED: SystemExit 7']
os_exit            rc=9           []
keyboardinterrupt  rc=3221225786  ['SCAN RAISED: KeyboardInterrupt ']
plain_exception    rc=0           ['SCAN COMPLETED; blocks = 12']
infinite_loop      *** TIMED OUT after 25s — the scan never returns ***
recursion          rc=0           ['SCAN COMPLETED; blocks = 12']
```

The `_scan_tier1` docstring states:

> Hostile or corrupt drop-ins are isolated by the try/except below — a failing
> module is logged as a warning and skipped without crashing the palette refresh.

That is true for `Exception` and false for the rest. The accident case is not
exotic: a script converted into a block that still carries an `argparse` error
path, a `sys.exit(main())` idiom, or a top-level `raise SystemExit` will kill the
backend on every startup, produce **no** `DropinFailure` record (so FR-015's
"silent disappearance ends" is not met for this class), and leave the user with
no in-product way to remove the file — the palette they would use to find it is
what died.

The infinite-loop case has no bound at all. `TODO(#1531)` defers the full
sandbox, which is fair, but a `BaseException` catch and a wall-clock bound are
not the sandbox.

#### P2-2. The write path's temp file lives in the scanned directory, is globbed as a drop-in, and leaks on non-`OSError` failures

Both W1 and W4 create `tempfile.mkstemp(prefix=".__scistudio_write_", suffix=".py", dir=<destination dir>)`.
The block scan does `scan_dir.glob("*.py")` and skips only `py_file.name.startswith("_")`.
`.__scistudio_write_abc123.py` starts with `.`, not `_`.

Probe 5 — a file with that exact name placed in a scratch `~/.scistudio/blocks`,
then a normal `BlockRegistry.scan()`:

```
registered scan dirs: (...\home\.scistudio\blocks,)
marker file written by temp file?  True
```

The scanner executed it. Two consequences:

1. **Race.** A palette refresh concurrent with a save can import a
   partially-written temp file. The `user_library.py` docstring claims
   *"the write itself is atomic … so a failure never leaves a half-written block
   where the registry will find it."* Atomicity covers the destination *name*;
   the temp file is a different name in the same globbed directory, so the
   registry can find it.
2. **Leak.** The cleanup handler is `except OSError`. A filename containing an
   embedded NUL makes `os.replace` raise `ValueError`, which is not caught:

   ```
   null byte  'ev\x00il.py'   RAISED ValueError: replace: embedded null character in dst
   ```

   and the directory listing after probe 3 shows the orphan surviving:

   ```
   == directory listing after writes ==
       '.__scistudio_write_7puzqcfa.py'      <- leaked by the ValueError path
       '_strptime.py'  'COM1.py'  'CON.py'  'NUL.py'  'ok.py'  'SHOUT.PY'
     glob('*.py') sees: ['.__scistudio_write_7puzqcfa.py', 'COM1.py', ..., 'ok.py']
   ```

   Caller-controlled content, in a directory that is executed on every scan,
   under a name the user cannot see in the palette or delete through the
   product. The same `except OSError` shape is in `routes/projects.py` and
   `tools_library.py::_atomic_write`.

   Note the `ValueError` also escapes the handler entirely, so the endpoint
   returns an unhandled-exception 500 rather than a 4xx.

#### P2-3. MCP `scaffold_block` performs an unvalidated path join and writes outside the project

`tools_authoring.py`:

```python
blocks_dir = root / "blocks"
blocks_dir.mkdir(parents=True, exist_ok=True)
target = blocks_dir / f"{name}.py"
if target.exists(): raise FileExistsError(...)
...
target.write_text(text, encoding="utf-8")
```

`name` comes straight from the agent. `Path.__truediv__` with an absolute
right-hand side discards the left side. Probe 7:

```
traversal        '../../outside/escaped'     WROTE ...\project\blocks\..\..\outside\escaped.py
traversal win    '..\\..\\outside\\escaped_win'  WROTE ...
absolute         'C:\...\outside\absolute_escape'  WROTE ...\outside\absolute_escape.py
dotfile          '../../../.bashrc_like'     WROTE ...\project\blocks\..\..\..\.bashrc_like.py

files created outside the project root:
    ...\outside\absolute_escape.py
    ...\outside\escaped.py
    ...\outside\escaped_win.py
```

(The fourth landed in `%TEMP%\.bashrc_like.py`, outside my scratch root; deleted.)

This is **pre-existing** — `git diff b485e293..HEAD -- src/scistudio/ai/agent/mcp/tools_authoring.py` touches only `reload_blocks`. It is in this report because the dispatch scopes `ai/agent/mcp/` write tools, and because `scaffold_block` is now the *only* MCP write tool that does not route through `_resolve_project_path` / `_safe_under` — every sibling in `tools_workflow/` and `tools_inspection/` does, and `tools_library.py` newly does. The inconsistency is now conspicuous.

The `target.exists()` check means it can create but not destroy.

#### P2-4. `POST /api/workflows/export-path` has no containment and silently overwrites

```python
target = Path(file_path)
save_yaml(definition, target)
```

Probe 9, against a file that has nothing to do with any project:

```
absolute outside anything -> {'status': 'ok', 'path': '...\definitely_outside_any_project\victim.yaml'}
traversal                 -> {'status': 'ok', 'path': '...\a\..\traversed.yaml'}
victim.yaml first line now: workflow:
```

The pre-existing file was destroyed. Pre-existing (`routes/workflows.py` is not in `git diff b485e293..HEAD -- src/`), and the sibling save-dialog endpoints W9/W10 do apply `_resolve_safe_path`, so the home/temp allowlist already exists and this route simply does not use it.

#### P2-5. Four of the user-library containment rules have zero test coverage

`pytest tests/api/test_user_library_write.py tests/blocks/test_dropin_type_import.py --cov=scistudio.api.routes.user_library --cov-report=term-missing`:

```
src\scistudio\api\routes\user_library.py   107  25  77%   110, 112, 134-135, 145, 149, 169, 173-176, 205, 211, 235-241, 247-248, 271-273
```

Never-executed lines that are containment rules:

| Line | Rule | Would deleting it fail a test? |
|---|---|---|
| 110 | `raise _reject(403, "Path traversal is not allowed")` — the `name in (".","..") or ".." in name.split(".")` branch | **no** — `../x.py` is caught two lines earlier by the separator rule, so this line is unreachable for every input any test supplies |
| 112 | `raise _reject(403, …)` — the `Path(name).name != name` branch | **no** |
| 145 | `except ValueError` from `commonpath` — the different-drive case the module docstring calls out by name | **no** — `Z:\elsewhere\evil.py` is caught earlier by the `isabs` check, so the cross-drive branch is never entered |
| 149 | `raise _reject(403, "User library files must live directly in the target directory")` — rule 4 of the module docstring | **no** |

Rule 4 *does* work — I executed it in probe 10 (§2.2) — but no test does. The two symlink tests that look like they cover this space are `test_a_symlink_escaping_the_library_is_refused` (skipped on this host) and `test_a_linked_subdirectory_cannot_smuggle_a_nested_write` (runs, via the junction fallback, but exits at line 142 `commonpath`, not 149). The dispatch asked whether each containment rule has a test that would fail if the rule were removed; for these four the answer is no.

Line 205 (413 size cap) and 211 (400 directory) are also untested.

---

### P3 — follow-up

**P3-1. `prepended_sys_paths` is neither reentrant nor thread-safe.** It snapshots `sys.path` on entry and does `sys.path[:] = original` on exit, so two interleaved windows in one process cannot both be correct. Probe 8b (A enters, B enters, A exits, B exits):

```
B's root still on sys.path inside B's own window: False
final sys.path == baseline                      : False
leaked entries after both windows closed        : ['...\probe_root_A_0dlaikdt']
```

Both failure modes fire: an inner user loses its roots mid-window, and an outer user's root leaks permanently. `_sys_path_without` in `core/dropins.py` has the identical shape, so a concurrent scan can make the FR-016 guard evaluate against the wrong `sys.path` and report a false verdict either way. In the API process today the scans run directly on the event loop (`async def` handlers calling `refresh_all_registries()` / `hot_reload()` without `run_in_threadpool`), and the worker is single-threaded, so I found no live corruption path — the hazard is latent, and it is one `asyncio.to_thread` away from being real.

**P3-2. `.PY` behaves differently per platform and is invisible to the bridge's change detector.** `_validate_filename` lowercases the suffix before comparing, so `SHOUT.PY` is accepted (probe 1). On Windows `glob("*.py")` matches it (probe 3: `glob('*.py') sees: [..., 'SHOUT.PY', ...]`), so it is a live drop-in; on POSIX it is not. Separately, `ai/agent/mcp/runtime.py::dropin_revision` filters with `entry.suffix != ".py"` — case-sensitive — so writing or editing a `.PY` file never moves the standalone bridge's revision signature and never triggers `sync_dropins()`. Either accept `.py` only, or make both comparisons agree.

**P3-3. Reserved Windows device names are accepted.** `NUL.py`, `CON.py`, `COM1.py` all passed validation and, on this host, produced real files (probe 3, `exists=True size=6`). Whether Win32 resolves `X.py` to the device is version- and API-dependent, so on another Windows build the same request can silently write to a device or fail late in `os.replace`. Cheap to reject at `_validate_filename`.

**P3-4. `_safe_under`'s contract text no longer matches its callers.** Its docstring says *"reject paths that escape *root* … Used by tools that accept user-supplied paths (`get_doc`, `get_workflow`, etc.)"* and it raises `PermissionError(f"Path {target} resolves outside project root {root}")`. `promote_to_user_library` now calls it with the user library root, so a promotion failure reports "outside project root" for a path that has nothing to do with a project. The behaviour is right; the message is not.

**P3-5. `ARCHITECTURE.md` does not describe either new behaviour.** §12.5 still says drop-in directories are *"scanned into the registries at startup and on project open"* and lists `~/.scistudio/blocks/`, `~/.scistudio/types/` with no mention that (a) the types directories now join `sys.path` in four processes, (b) a name collision there is a hard refusal, or (c) the product now has a write door into `~/.scistudio` (`PUT /api/user-library/file`). `grep -rn "sys.path" docs/architecture/` returns nothing; `grep -rln "api/user-library" docs/` returns nothing — the endpoint exists only in `frontend/src/**` and the spec. For a security-relevant surface, ARCHITECTURE.md §12.5 is the place a reader would look and would not find it. `docs/architecture/sentrux-rules.md` is a dependency-layering/complexity document and makes no claim about these surfaces, so it is correctly silent — no drift there.

**P3-6. The spec does not govern the module it calls its highest-risk surface.** `docs/specs/adr-053-personal-tool-library.md` `governs.files` is `[the spec itself, src/scistudio/api/routes/types.py, frontend/src/components/TypePalette.tsx]`. Every path listed exists (I checked all `governs`/`planned_governs`/`tests` entries in both the spec and `docs/adr/ADR-053.md` — **no missing paths**). But §14 says *"this is the highest-risk surface in the spec and warrants the closest review"* about the user-library write path, and neither `src/scistudio/api/routes/user_library.py`, `src/scistudio/core/dropins.py`, nor `src/scistudio/ai/agent/mcp/tools_library.py` is governed by any spec or ADR frontmatter. A future change to `_validate_filename` or `guard_dropin_type_roots` has no governance anchor.

**P3-7. Generated reference docs are stale — pre-existing, not attributable to this tree.** Running `scripts/docs/build_reference.py --generate-only` produces a diff in `docs/user/reference/index.md` (version stamp `0.3.2a0` → `0.3.3a0`) and in `src/scistudio/_user_guide/api-reference/scistudio.blocks.code.md` (a `codeblock_config_payload` docstring paragraph). `git diff --stat b485e293..HEAD -- src/scistudio/blocks/code/ src/scistudio/_user_guide/ docs/user/reference/` is **empty**, so both predate this branch. I restored the working tree. No hand-edited generated doc was found.

**P3-8. Overwrite semantics are inconsistent across the write surfaces.** W1/W3/W11/W15 require an opt-in or refuse; W4/W5/W8/W9/W10 destroy silently. FR-008 established "no silent overwrite" as a product rule for the new door; the older doors do not follow it. Worth a deliberate decision rather than an accident of authorship order.

**P3-9. `dropin_revision` cannot see package-shaped drop-ins.** It stats only `*.py` entries directly under each scan dir. `_importable_entries` treats `<name>/__init__.py` as importable and `guard_dropin_type_roots` refuses collisions on it, so a package-shaped drop-in type is a first-class citizen of the guard but invisible to the standalone bridge's change detector — edit one and `sync_dropins()` never fires.

**P3-10. `_installed_origin` reports `"built-in"` for a namespace package.** `found.origin` is `None` for a namespace package, and `return found.origin or "built-in"` turns that into the string `built-in`. Reporting the collision is arguably right (a regular module does displace a namespace portion), but the user-facing FR-015 message will name `built-in` as the origin of a package that is on disk.

---

## 6. Answers to the dispatch's eight questions, condensed

1. **Every write endpoint enumerated** — §1, 17 surfaces. Containment defeated on W5 (no containment) and W15 (unvalidated join). W1–W4 held against every escape I could execute.
2. **Inconsistent constraints / did the second weaken the first** — §3. Inconsistent yes; path constraint on the older door unchanged (diff + probe); its *consequence* widened via the reload hook.
3. **`sys.path` manipulation** — §4.1. Restored on every exit path including exceptions (verified). Not safe under concurrency (P3-1). `sys.modules` capture outlives the scoped window (§4.1).
4. **Module shadowing** — detected for ordinary names, **not detected** for `_`-prefixed names (P1-1). No false positives found; `test_a_type_file_never_reports_itself_as_a_collision` covers the self-report case and the `_sys_path_without` design is correct for it.
5. **Failure handling** — one broken drop-in does not stop the others for `Exception` (probe 6, and `test_one_failure_does_not_stop_the_rest_of_the_scan`). It **does** for `BaseException`, and an infinite loop hangs the scan forever (P2-1).
6. **Cross-process consistency** — yes, all four sites resolve through `core.dropins`; `SCISTUDIO_PROJECT_DIR` is set by `_worker_env`. No divergence found.
7. **Docs vs. code** — spec §4/§5/§10.3 accurately describe W1–W3 and the provisioning helper. Divergences: FR-016's own definition of "importable name" vs. `_importable_entries` (P1-1); `_scan_tier1`'s isolation claim (P2-1); `user_library.py`'s atomicity claim (P2-2); ARCHITECTURE.md silence (P3-5); `_safe_under`'s contract text (P3-4).
8. **Tests** — four containment rules have no test that would fail if removed (P2-5); the symlink test skips on the development platform (§0); and one test actively pins the P1-1 gap with an incorrect rationale.

---

## 7. Environment notes

### 7.1 Test failures, attributed

`pytest tests/api tests/blocks tests/core -q --no-cov` → 3 failures:

```
FAILED tests/api/test_filesystem_browse.py::TestBrowseFilesystem::test_overlength_path_returns_400_not_500
FAILED tests/api/test_mcp_transport_publish.py::test_project_open_route_starts_project_mcp_socket
FAILED tests/api/test_mcp_transport_publish.py::test_project_open_route_rebinds_missing_project_mcp_socket
```

All three re-run in the merge-base worktree (`C:/Users/jiazh/workspace/SciStudio` @ `b485e293`) fail identically. They are the Windows overlength-path and AF_UNIX-socket families and are **not attributable to the tree under review**. The first touches `_resolve_safe_path`, which is in scope, so I checked it specifically: that helper is byte-identical to merge-base.

### 7.2 What I could not verify

- **Symlink containment** (see §0). Junction-based reparse-point escapes were executed and rejected; file-symlink behaviour on this platform, and all POSIX behaviour, is unverified here.
- **Sentrux** — not installed on `PATH`, no Sentrux MCP tool available to this session. No Sentrux result is claimed.
- **Frontend** — out of the dispatch's audit surface; not examined.
- I did not read `docs/audit/2026-08-07-adr-053-spec1-track-a.md` (see the header note), so anything it already found is independently rediscovered or independently missed here.

### 7.3 Gate ledger: the issue link is a derivation, not a verified link

`gate_record check --mode pre-pr` and the pre-commit gate hook both require
`guard.issue_link`, and the CLI offers no exploratory-task escape hatch. The
dispatch forbids reading any GitHub issue, so I could not look the number up.

The ledger therefore records **#2022**, derived from a permitted source:
`tests/blocks/test_dropin_type_import.py` L21 reads *"The FR-016 section carries
two findings from the Track A audit (#2022)"*, and this audit's P1 is an FR-016
finding in exactly that area. The `amend --reason` on the ledger says the same
thing. Treat it as a traceable derivation from repository test code, **not** as
a verified tracker link — whoever files the P1 fix should re-point it.

`check` run without an explicit `--base` observes the diff against `origin/main`
rather than against this audit branch's parent (`327ae238`), so it attributes the
whole feature branch to this record and reports `guard.core_change_guard` over
`core/dropins.py`, `blocks/registry/**`, and `blocks/io/**`. Those are not files
this audit touched — its entire diff is one report under `docs/audit/`. The
correct base for this record is `327ae238`.

---

## 8. Recommendation

**Block**, on P1-1 alone.

Everything else is *pass-with-fixes*: the new write path's containment is well
constructed and survived every escape I could execute on this host — traversal,
absolute, UNC, extended-length, device-namespace, drive-relative, cross-drive,
trailing-separator, and reparse-point — and it is a real
`realpath`+`commonpath`+parent-equality test, not a string prefix. FR-009 holds:
the project endpoint's constraint is unchanged and I re-verified it directly.

P1-1 is the exception because the guard whose entire purpose is to stop a
user-writable directory from capturing an installed module name declines to look
at a whole class of names, the product's own endpoints accept those names, the
capture survives the scoped `sys.path` window, and a test asserts the exemption
is correct on a premise that is demonstrably false. The accident case
(`types/_helpers.py`, `types/_strptime.py`) is more likely than the hostile one
and is silent in both directions — no palette error, no log line, no
`DropinFailure`.

Unblocking needs: the collision question asked of `_`-prefixed entries, the
registration question left as it is, and
`test_underscore_prefixed_type_files_are_ignored` replaced by a test that asserts
the collision *is* reported for `_`-prefixed names — with its docstring
corrected, because that docstring is what will otherwise reintroduce this.
