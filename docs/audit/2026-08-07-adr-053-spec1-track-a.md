---
title: "Audit: ADR-053 Spec 1 Track A (registry runtime defects)"
status: Final
owners:
  - "@jiazhenz026"
related_adrs:
  - 53
language_source: en
---

# Audit: ADR-053 Spec 1 Track A (registry runtime defects)

- Date: 2026-08-07
- Persona: `audit_reviewer`, audit mode `with-context`
- Audit branch / worktree: `audit/adr-053-spec1-track-a` / `SciStudio-wt-audit-a`
- Audited branch: `fix/2020-adr-053-registry-runtime-defects` @ `e3e95a75`
  (A1 `24a1426a` + A2 `329f8737` + A3 `62a452d9`, integrated by the manager)
- Base: `origin/main` @ `b485e293`
- Issues: `#2020`, `#2021`, `#2009`, `#2022`
- Judged against: `docs/specs/adr-053-personal-tool-library.md` §2.4–§2.6, §5,
  §10.3, §10.4, §11, §13, §14; `docs/adr/ADR-053.md` §3;
  `docs/planning/adr-053-spec1-personal-tool-library-checklist.md` §1.2, §2,
  §6.2, §7, §9; `AGENTS.md`; `docs/ai-developer/rules.md`;
  `docs/ai-developer/personas/audit-reviewer.md`;
  `docs/ai-developer/specific_rules/agent-dispatch.md`

**Recommendation: pass-with-fixes.** Two P1 findings must land before PR A opens.
Both are in FR-016. Everything else in the track — FR-057 through FR-061,
FR-062 through FR-064, #2009, FR-012 through FR-015 — is delivered, and the §2.5
reproduction is genuinely fixed.

---

## 0. What I Actually Ran

Every claim marked **observed** rests on one of these. Scripts live in the
session scratchpad; each is reproduced inline in the section that uses it.

| Command | Result |
|---|---|
| `pytest tests/blocks/test_dropin_type_import.py tests/api/test_registry_provisioning_parity.py tests/api/test_registry_reload_symmetry.py --no-cov` | 38 passed |
| `pytest tests/api tests/blocks tests/core tests/previewers --no-cov -p no:randomly` | 3 failed, rest pass; all 3 reproduce on `origin/main` (§6) |
| `gate_record check --record <track-A ledger> --mode pre-pr --base origin/main --head HEAD` | 9 checks inferred; 8 satisfied, `python_tests` red with 9 known environmental failures (§6) |
| `python -c "from importlinter.cli import lint_imports_command; …"` | 13 contracts kept, 0 broken |
| `ruff check src tests` / `ruff format --check src tests` | clean / 776 files already formatted |
| `mypy src` | Success, no issues in 343 source files |
| Own §2.5 reproduction, run on `origin/main` and on `e3e95a75` | §1 |
| Own FR-016 reproduction (`{project}/types/json.py`, `TypeRegistry`) | §2.1 |
| Own FR-016 worker reproduction (real `python -m scistudio.engine.runners.worker`) | §2.2 |
| Own `dropin_type_roots_for_block_dirs` tier-combination sweep | §4.4 |
| Independent enumeration of registry-invalidating call sites | §3 |

Sentrux: no `sentrux` executable on PATH in this worktree and no Sentrux MCP
server configured for this session. **Sentrux evidence is unavailable and is not
claimed.** Checklist §4 already carries an unchecked "Sentrux baseline recorded,
or N/A reason recorded" row; it remains outstanding.

---

## 1. Spec §2.5 Reproduced Independently, Before And After

I did not use A3's fixtures. I built the §2.5 case from the spec text: a project
with `types/spectrum.py` defining `SpectrumData(DataObject)` and
`blocks/uses_spectrum.py` doing `from spectrum import SpectrumData` and declaring
it on both ports, scanned the way `ApiRuntime.refresh_type_registry` /
`refresh_block_registry` scan, under an isolated fake `HOME`.

**Observed — `origin/main` @ `b485e293`:**

```
helper_present: False
=== TypeRegistry ===
SpectrumData registered: True
  module_path: _scistudio_type_dropin_spectrum_1786091161_0082b674
=== BlockRegistry ===
uses_spectrum present: False
dropin_failures: <attribute does not exist on this checkout>
```

**Observed — `fix/2020-adr-053-registry-runtime-defects` @ `e3e95a75`:**

```
helper_present: True
=== TypeRegistry ===
SpectrumData registered: True
=== BlockRegistry ===
uses_spectrum present: True
  runtime_import_roots: ['...\proj\types', '...\home\.scistudio\types']
dropin_failures: []
```

The defect is fixed, and fixed the way FR-012/FR-013/FR-014 require: the block
registers, the roots are stamped on the spec for the worker, and the project tier
precedes the user tier. §2.5's "the failure is silent" is also ended — my first
(deliberately malformed) probe block surfaced as a `DropinFailure` carrying the
file, `TypeError`, and the message, without my asking for it.

---

## 2. P1 Findings

### P1-1 — FR-016's "the real module still resolves" fails in the worker process

FR-016 (as amended by A3, spec line 435): *"a type file whose stem collides with
an importable top-level module MUST be rejected with an error reported through
the FR-015 surface, **and the module it collides with MUST still resolve to the
installed package**"*. Spec §14 says the rejection closes the hazard "by refusing
the file and binding the real module **before any drop-in runs**".

That binding happens in `_reject_shadowing_type_files`
(`src/scistudio/blocks/registry/_scan.py:190`), which is called only from
`_scan_tier1`. The worker never runs `_scan_tier1`. It runs
`_prepend_runtime_import_roots` (`src/scistudio/engine/runners/worker.py:96`),
which inserts the stamped type roots at `sys.path[0]` permanently and calls
`importlib.invalidate_caches()`, and then reconstructs the block from its file.
Nothing pre-binds the colliding module there.

**Observed.** An installed `sample_dep.py` on `PYTHONPATH`, a colliding
`{project}/types/sample_dep.py`, and a drop-in block that reports at *run* time
which one it got, executed by a real
`python -m scistudio.engine.runners.worker` subprocess:

```
=== parent (API) process ===
dropin_failures: [('DropinTypeNameCollision', 'sample_dep.py')]
parent `import sample_dep` -> installed | ...\site\sample_dep.py
runtime_import_roots: ['...\proj\types', '...\home\.scistudio\types']

=== worker process ===
returncode: 0
outputs: {'origin': 'SHADOWED-BY-TYPE-FILE',
          'file': '...\proj\types\sample_dep.py'}
```

The block resolves the installed module during the palette scan and the type file
at run time. That is the exact cross-process divergence FR-013 and FR-057 exist
to eliminate ("A block that imports successfully during palette scanning but fails
at run time is not a fix"), and it is a **new** hazard: on `origin/main` the type
directories were never on `sys.path` at all, so this could not happen before this
branch. It is also the precise failure mode the owner's OQ-1 answer names as
"among the hardest failures in this product to diagnose".

Severity is P1: an explicit MUST in the governing spec is violated, the violation
is introduced by this PR, and the spec's own risk section asserts a mitigation
that does not exist on the worker path.

Not covered by any test. A3's 18 tests exercise the parent process only.

### P1-2 — The rejected type file still registers a usable type

Owner decision, checklist §1.2: *"Reject the file and report an error —
**registration is refused**, not merely warned."*

A3's rejection lives in `blocks/registry/_scan.py`. `TypeRegistry.scan_all()`
(`src/scistudio/core/types/registry.py:505`) reaches `_scan_filesystem_dirs`,
which loads every `*.py` under the type roots by path under a synthetic module
name and registers any `DataObject` subclass defined there. It has no knowledge
of the rejection, and `ApiRuntime.refresh_type_registry` never consults the block
registry.

**Observed.** `{project}/types/json.py` defining `JsonBlob(DataObject)`, scanned
exactly as `ApiRuntime.refresh_type_registry` scans:

```
=== FR-016: is the colliding type refused? ===
JsonBlob registered in TypeRegistry: True
  module_path: _scistudio_type_dropin_json_1786091188_d427f7ba
  resolve('JsonBlob') -> TypeSpec(name='JsonBlob', …)
  load_class('JsonBlob') -> <class '…JsonBlob'> (usable: True)

=== FR-016: is the collision reported? ===
  DropinTypeNameCollision | json.py
    json.py is rejected: the name 'json' already belongs to an importable
    module (…\Lib\json\__init__.py), which this file would shadow once the
    types directory joins sys.path. Rename it to a name no installed module
    uses.

=== FR-016: does `import json` still get the stdlib? ===
  json -> …\Lib\json\__init__.py
```

Plainly, what the user experiences: **they are shown an error telling them the
file is rejected and that they must rename it, while the type declared in that
file silently keeps working.** Nothing in the product reconciles the two. If they
never rename it, the error is permanent and inert. Track B's Data types tab
(FR-039) will list `JsonBlob` with no indication that its file was refused.

The safety half of FR-016 holds in the API process — the stdlib `json` still
wins — so this limb is a state-consistency and honesty defect rather than a
shadowing hazard. But the owner adjudicated OQ-1 specifically, in the words
"registration is refused", and registration is not refused.

Not covered by any test. **No test in `tests/blocks/test_dropin_type_import.py`
constructs a `TypeRegistry` at all** — I checked every one of the 18.

The architectural reason is worth stating for whoever fixes this: the refusal is
recorded on the *block* registry (`_dropin_failures`) and the registration happens
in the *type* registry, and the two are built independently by
`refresh_all_registries`. A fix has to give the type-side scan the same collision
predicate — `_shadowed_top_level_module` is the reusable half, but it currently
lives in `scistudio.blocks`, which `scistudio.core` may not import. The natural
home is `scistudio.core.dropins`, next to the tier definition it already owns.

### P1 impact on FR-016's checklist row

Checklist §7.3 row *"`A3` colliding type filename rejected with an error
(FR-016, OQ-1)"* is still `[ ]`. It should not be checked as delivered until
P1-1 and P1-2 land.

---

## 3. Independent Enumeration Of Registry-Invalidating Call Sites (FR-062)

I enumerated `refresh_block_registry` call sites on `origin/main` myself before
reading A2's answer.

| # | Site | On `origin/main` | On `e3e95a75` |
|---|---|---|---|
| 1 | `api/routes/git.py:493` branch switch | blocks only | `refresh_all_registries()` |
| 2 | `api/routes/packages.py:128` install local | blocks only | `_after_package_change` |
| 3 | `api/routes/packages.py:211` update | blocks only | `_after_package_change` |
| 4 | `api/routes/packages.py:226` rollback | blocks only | `_after_package_change` |
| 5 | `api/routes/packages.py:241` delete | blocks only | `_after_package_change` |
| 6 | `api/runtime/_projects.py:311` `open_project` | types + blocks + previewers | `refresh_all_registries()` |
| 7 | `api/runtime/__init__.py:419` `_configure_static_registries` | types + blocks | unchanged |

**A2's count of seven is correct**, and the two it called "unlisted" relative to
the issue's five — `open_project` and `_configure_static_registries` — are exactly
the two extras. That claim is sound.

### P2-1 — but the FR-062 audit stops at `refresh_block_registry`

FR-062 is written in terms of **events**: *"Every event that invalidates the block
registry MUST be evaluated against the type registry."* Three such events do not
call `refresh_block_registry` at all and were not evaluated:

| Site | Event | Type registry |
|---|---|---|
| `api/routes/blocks.py:289` `POST /api/blocks/reload` | the palette Reload button | not refreshed |
| `api/routes/projects.py:491` `_maybe_reload_blocks_after_save` | save of a clean `{project}/blocks/*.py` | not refreshed |
| `ai/agent/mcp/tools_authoring.py:434` MCP `reload_blocks` | agent edits/scaffolds a block | not refreshed |

All three rebuild the block registry from disk via `hot_reload()`. Two
consequences follow:

- A user who edits `{project}/types/spectrum.py` and presses **Reload** gets a
  fresh block registry and a stale type registry. `_maybe_reload_blocks_after_save`
  is gated on `_is_under_project_blocks_dir`, so **a save under
  `{project}/types/` triggers no refresh of anything.** This is the same
  user-visible failure FR-063 argues for fixing ("a user would install a package
  and watch its types fail to appear"), on a path the user hits far more often
  than package install.
- The MCP `reload_blocks` path matters more after this branch than before it,
  because FR-059 has just given the agent a populated type registry that can now
  go stale.

The regression test A2 added is also narrower than its docstring claims.
`test_no_route_refreshes_one_registry_on_its_own`
(`tests/api/test_registry_reload_symmetry.py:151`) greps `api/routes/*.py` for the
literals `refresh_block_registry(`, `refresh_type_registry(`,
`refresh_preview_service(`. It cannot see `registry.hot_reload()`, which is how
two of the three sites above invalidate. Its docstring says "Every invalidating
route goes through the unified entry point (FR-062)"; what it actually pins is
"no route names a single refresh method".

I judge this P2 rather than P1: the shipped `refresh_all_registries` behaviour is
correct as far as it goes, no existing behaviour regresses, and the fix is
additive. But checklist §7.3's `[x]` on the FR-062 audit row overstates what was
audited.

---

## 4. Manager-Accepted Judgments, Re-Verified

### 4.1 `_configure_static_registries` left out of the unified refresh — **sound**

`_configure_static_registries` (`api/runtime/__init__.py:416`) calls
`refresh_type_registry()` + `refresh_block_registry()`. `refresh_all_registries`
additionally calls `refresh_preview_service`, which in `api/runtime/_data.py:248`
calls `build_preview_service(...)` unconditionally, whereas `get_preview_service`
(`_data.py:229`) builds lazily on first use and caches. So the reasoning is
mechanically correct: unifying there would build the preview service eagerly at
runtime construction.

I also checked it is not merely a performance argument hiding a staleness bug. It
is not. If a project is opened, `open_project` → `refresh_all_registries` rebuilds
the service for that project. If none is opened, the lazy build sees
`active_project is None` and builds the same thing the eager build would have.
There is no window in which the preview service is stale because of this
omission. **Accept.**

### 4.2 `src/scistudio/previewers/**` needed no change — **sound**

`refresh_preview_service` already existed on `origin/main` at
`src/scistudio/api/runtime/_data.py:248` and was already called from
`open_project`. `git diff --stat origin/main...HEAD -- src/scistudio/previewers/
tests/previewers/` is empty. #2009 was a call-site defect and is fixed at the call
sites. **Accept.**

I also confirmed the #2009 fix did not grow into the out-of-scope #2017 work: the
only `OwnerKind` references in the diff are four lines in
`tests/api/test_registry_reload_symmetry.py` using the existing
`OwnerKind.PROJECT` / `OwnerKind.PACKAGE` members. No user tier, no enum change.

### 4.3 A3's `dropin_type_roots_for_block_dirs` rationale — **sound**

A3's claim was that the API server never sets `SCISTUDIO_PROJECT_DIR`, so
`project_dir_from_env()` would return `None` and FR-012 would be broken on the
primary surface.

Verified. Every write of that variable in `src/` targets a *child* process
environment dict, never the current process:
`engine/runners/local.py:193` (`env["SCISTUDIO_PROJECT_DIR"] = …` on the worker
subprocess env, per the #1365 comment at `local.py:298`) and `cli/install.py:220`
(writing an MCP client config). `cli/mcp_bridge.py` and
`core/types/serialization.py` only *read* it. Nothing in the API server's own
startup sets it. The claim holds, and deriving the type roots from the scan
directories the registry was actually given is the right answer for a registry
that is handed directories rather than a project root.

### 4.4 FR-014 ordering in every tier combination — **holds**

**Observed**, with `Path.home()` patched:

| Input block dirs | Derived type roots |
|---|---|
| `[<proj>/blocks, ~/.scistudio/blocks]` (project open) | `[<proj>/types, ~/.scistudio/types]` |
| `[~/.scistudio/blocks]` (no project) | `[~/.scistudio/types]` |
| `[]` (registry given nothing) | `[]` |

Project tier first in the project case, user tier alone in the no-project case,
inert when empty. `dict.fromkeys` dedupe is what collapses the duplicate
`~/.scistudio/types` that `type_scan_dirs(~/.scistudio)` contributes twice, and it
preserves first-occurrence order, so the project tier cannot be displaced.

I confirmed the reversed-order and foreign-directory inputs below are not
reachable from product code: `add_scan_dir` is called from exactly one place in
`src/`, `scistudio.core.dropins._register` (`dropins.py:230`). Every other
occurrence in `src/` is a docstring. FR-057's "no call site independently decides
which directories the tier comprises" is genuinely satisfied, and there is no
surviving `Path.home() / ".scistudio" / "blocks"|"types"` anywhere in `src/`.

---

## 5. Requirement-By-Requirement

| Requirement | Verdict | Evidence |
|---|---|---|
| FR-057 shared helper, four consumers | **Pass** | `core/dropins.py`; only `_register` calls `add_scan_dir`; four consumers verified in `_projects.py`, `mcp/runtime.py`, `types/serialization.py`, `io/_unified_dispatch.py` |
| FR-058 one tier definition for blocks and types | **Pass** | `_tier_dirs` with a child name; `user_library_dir()` the single answer |
| FR-059 agent registers type dirs | **Pass** | `_build_type_registry(project_dir)`; `make_mcp_runtime` docstring now states the coverage it has and names the old false claim |
| FR-060 user tier unconditional at all four points | **Pass** | `always_home` deleted from `_unified_dispatch`; `_projects.py` un-gated; parity test `test_user_tier_is_discovered_with_no_project_at_every_site` |
| FR-061 scan orders documented at **both** call sites | **Pass** | `TypeRegistry` module docstring carries the record; `BlockRegistry.scan()` (`registry/__init__.py:403`) carries a back-pointer naming it. See §5.1 |
| FR-062 invalidation audit complete | **Partial** | §3, P2-1 |
| FR-063 package install/uninstall refreshes types | **Pass** | `_after_package_change` on all four routes; tests |
| FR-064 branch switch refreshes types | **Pass** | `routes/git.py:495` |
| #2009 previewer refresh, no scope growth | **Pass** | §4.2 |
| FR-065 cross-process refresh | **Deferred, recorded in-repo** | §5.2 |
| FR-012 drop-in block imports drop-in type | **Pass** | §1 |
| FR-013 worker parity, block actually runs | **Pass** | `test_dropin_block_runs_in_a_fresh_worker` spawns a real worker and asserts on `outputs`, not registration. I re-ran my own worker subprocess in §2.2 and it executed |
| FR-014 project shadows user | **Pass** | §4.4 and `TestProjectTierShadowsUserTier` |
| FR-015 failures visible; #1531 hardening intact | **Pass** | §5.3 |
| FR-016 rejection | **Fail** | §2, P1-1 and P1-2 |
| Spec §13 OQ-1 marked Resolved | **Pass, with a caveat** | §5.4 |

### 5.1 FR-061 back-pointer — delivered correctly

The manager reassigned this from A1 to A3. A3 delivered it at
`src/scistudio/blocks/registry/__init__.py:403`:

> The pass order below deliberately differs from
> `scistudio.core.types.registry.TypeRegistry.scan_all`. The reason is recorded
> in that module's docstring under "Scan order versus BlockRegistry"
> (ADR-053 FR-061).

It points at the type-registry record rather than duplicating it, which is the
right call — a duplicated rationale is a second thing to drift. A reader standing
at `BlockRegistry.scan()` learns both that the divergence is deliberate and where
the reasoning lives. FR-061's "recorded at both call sites" is satisfied.

The record itself is sound and I checked its two load-bearing claims are true:
`_scan_tier1` registers unconditionally (so a drop-in block does override a
builtin — pinned by `test_dropin_block_overrides_a_builtin_of_the_same_name`), and
`_scan_filesystem_dirs` skips names already in `self._registry` (so a drop-in type
cannot shadow a core type — pinned by
`test_dropin_type_cannot_shadow_a_core_type`). Both orders are pinned by
`test_type_registry_scan_order_is_unchanged` /
`test_block_registry_scan_order_is_unchanged`.

### 5.2 FR-065 — the handoff is in the repository, not only in chat

Checklist §7.3 marks it `[!]` partial, §9 logs the reason, and
`docs/planning/adr-053-spec1-dispatch-prompts/b1-origin-and-write-path.md` §9a
carries it as "SEQUENCED INTO YOUR SLICE. Not optional", committed as
`10436915`. The in-process half is delivered (`refresh_all_registries` is the
entry point, and `test_refresh_all_registries_picks_up_a_user_library_write`
pins it). This satisfies the dispatch's requirement that the handoff be recorded
in the repository. Nothing to fix here.

### 5.3 FR-015 — historical wording and #1531 hardening both intact

`_scan_tier1` keeps `"Failed to import block from %s"` at both the inner
(`_scan.py:283`) and outer (`_scan.py:328`) handlers, with a comment explaining
why the wording must not change. The `#1531` skip-don't-crash structure is
unchanged and its `TODO(#1531)` is preserved verbatim. `git diff origin/main...HEAD
| grep '^+.*TODO('` returns nothing: **this track added no new TODO**, so the
owner's no-deferred-scope directive holds on that axis.

`test_one_failure_does_not_stop_the_rest_of_the_scan` pins the hardening;
`test_rescan_rebuilds_rather_than_appends` pins that `_dropin_failures` is rebuilt
rather than accumulated.

### 5.4 Spec §13 OQ-1 — marked Resolved, but the FR-016 text drifted toward the implementation

OQ-1 is marked *Resolved* with the owner's answer and its rationale, and §11's
acceptance row was updated from "Shadowing warning" to "Shadowing rejection".
That is what the dispatch asked for.

**P2-2.** But A3 also rewrote FR-016 itself, and the rewrite is not a neutral
transcription of the owner's decision:

- The owner's recorded wording is "registration is refused, not merely warned".
  The new FR-016 says "rejected with an error reported through the FR-015
  surface" and says nothing about registration. As shipped, the error is reported
  and the type registers (P1-2) — so the requirement as rewritten is satisfiable
  by an implementation the owner's decision excludes.
- The new §11 acceptance row reads "rejected with an error, and the real module
  still imports". Both halves pass in the parent process, so the acceptance
  criterion certifies a build that fails P1-1 in the worker.
- §14's risk paragraph now asserts the hazard is closed "by refusing the file and
  binding the real module before any drop-in runs". §2.2 shows that is false on
  the worker path.

I am not calling this bad faith — the added clause *"and the module it collides
with MUST still resolve to the installed package"* is a real strengthening, and
it is the clause that P1-1 violates. But the net effect is that the governing
spec now describes what was built rather than what was decided, and the
acceptance table would have passed this branch. When P1-1/P1-2 are fixed, FR-016
should regain the owner's "registration is refused" language explicitly.

---

## 6. Tests, CI-Equivalent Checks, And Environment

`pytest tests/api tests/blocks tests/core tests/previewers --no-cov` →
3 failures:

- `tests/api/test_filesystem_browse.py::…::test_overlength_path_returns_400_not_500`
- `tests/api/test_mcp_transport_publish.py::test_project_open_route_starts_project_mcp_socket`
- `tests/api/test_mcp_transport_publish.py::test_project_open_route_rebinds_missing_project_mcp_socket`

**All three reproduce identically on unmodified `origin/main` @ `b485e293`** in a
separate detached worktree. Windows path semantics and POSIX unix sockets. Not
attributable to this work.

`gate_record check --mode pre-pr` against the Track A delivery ledger inferred
`['architecture_tests', 'deferral_discipline', 'format_check', 'full_audit',
'import_contracts', 'lint_format', 'python_tests', 'semantic_dup', 'type_check']`
at tier 1. Eight are satisfied. `python_tests` is red with
**9 failed, 5598 passed, 70 skipped, 8 xfailed** — exactly the nine families
checklist §9 records as environmental on this host (2 POSIX unix socket, 1 Windows
path, 2 POSIX shell rc, 1 TOML escaping, 3 `#2011` `/bin/sh` hook). Linux CI is
authoritative.

I ran that check with `--record` pointed at the manager's ledger and then
`git checkout --` restored the file, so no event I generated is committed to a
record I do not own.

- `mypy src` → clean, 343 files.
- `ruff check` / `ruff format --check` → clean.
- **Import-linter → 13 contracts kept, 0 broken.** "Core must not depend on
  blocks, engine, api, ai, or workflow" is KEPT, and "core.types submodules are
  acyclic" is KEPT — `core/dropins.py` sits directly under `core`, not under
  `core.types`, which is what keeps `core.types.serialization` importing it from
  being a sibling edge. The §6.2 frozen-contract constraint holds.

Test-change requirement: satisfied. Three new test files (38 tests) plus two
existing files updated (`tests/api/test_packages.py`,
`tests/blocks/test_registry_package_layout.py`).

Outstanding gate obligations for the manager, not defects in the agents' work:
the Track A delivery ledger `2020-adr-053-spec1-track-a-runtime-defects.json`
has zero `check_events`, no `commit`, and no `pull_request`, and
`requested_admin_labels` carries `admin-approved:core-change` with
`applied_by: null`. Checklist §5's four hook rows are all `[ ]`.

---

## 7. P3 Findings

**P3-1 — FR-016 detection misses directory packages.** The collision sweep
(`_reject_shadowing_type_files`) iterates `root.glob("*.py")`. A directory package
`{project}/types/json/__init__.py` shadows just as effectively and is not
detected. **Observed:** with that layout, `dropin_failures` is empty and no
collision is reported; the probe block got the stdlib only because `json` happened
to be pre-imported by the app itself. Combined with P1-1 the exposure widens,
since the worker has no pre-import to fall back on.

**P3-2 — the rejection imports the shadowed module as a side effect.**
`_reject_shadowing_type_files` calls `importlib.import_module(py_file.stem)` for
every collision, inside every `scan()` and `hot_reload()`. That is the mechanism
that makes the mitigation work, so it is intentional — but it means a
`{project}/types/tensorflow.py` makes every palette refresh import TensorFlow.
Worth a comment at minimum; a `sys.modules` guard would make it once-only.

**P3-3 — the type-root derivation infers a sibling `types/` for any scan dir.**
`dropin_type_roots_for_block_dirs` takes `Path(block_dir).parent / "types"`.
`BlockRegistry.add_scan_dir` is public and documented, so a caller registering
`~/mydir` would put `~/types` on `sys.path` during drop-in execution. Not
reachable from product code today (§4.4), but the invariant "every block scan dir
is `<tier-root>/blocks`" is now load-bearing and is only stated in a docstring.

**P3-4 — checklist §9 does not log two accepted scope additions.** Both were
correctly declared in the agents' ledgers before the edits, so this is checklist
hygiene, not agent drift:

| Agent | File outside its §6 matrix write set | Where declared |
|---|---|---|
| A2 | `src/scistudio/api/runtime/__init__.py` | ledger plan include, with rationale in the later `remove-include` event |
| A3 | `src/scistudio/api/schemas.py` | ledger plan include |
| A3 | `tests/blocks/test_registry_package_layout.py` | ledger amend, ADR-047 C9 rationale |

§9 logs only A2's `tests/api/test_packages.py`. All three files are inside the
checklist §2 overall in-scope list, and none is a protected path beyond the
already-authorized `admin-approved:core-change` surface.

---

## 8. Scope, Deferral, And Ledger Hygiene

- **Scope drift: none material.** Every changed file is inside checklist §2's
  in-scope list. The three matrix-vs-ledger deltas are P3-4. A2's `remove-include`
  of `src/scistudio/previewers/**` is a narrowing, correctly reasoned.
- **Deferral drift: none.** No `TODO(` added anywhere in `src/`, `tests/`, or
  `docs/` on this branch. FR-065 is sequenced into B1 with a committed record, not
  written as a TODO.
- **Ledger sanitization: clean.** Scanning the four new ledger files for
  `C:\Users\<name>`, `/home/<name>`, the operator's username, temp dirs, `.venv`,
  and `site-packages` returns zero matches.
- **Governance surface:** `governance_touch` is `false` on all three agent
  ledgers and no file under `docs/ai-developer/**` was touched. Correct.

---

## 9. Checklist Drift To Report To The Manager

I own only §7.4 and did not edit `docs/planning/**`. Reporting instead:

1. §7.3 row *"`A2` FR-062 audit found **seven** invalidation sites"* is `[x]`. The
   count is right but the audit is incomplete (§3, P2-1). Suggest re-scoping the
   row or adding a follow-up row for the three `hot_reload` events.
2. §7.3 rows for A3 (FR-012 – FR-016, §2.5 reproduction, docs) are all still `[ ]`
   with `<commit>` placeholders although A3 landed as `62a452d9`. FR-012 – FR-015
   and the §2.5 row are verifiably delivered and can be checked with that commit;
   the FR-016 row must not be checked until P1-1 and P1-2 land.
3. §7.2 dispatch rows are all `[ ]` although all four prompts are committed under
   `docs/planning/adr-053-spec1-dispatch-prompts/`.
4. §4 "Sentrux baseline recorded, or N/A reason recorded" is `[ ]` and I could not
   supply it — no CLI, no MCP server (§0).
5. §5's four hook rows and §7.5's integration rows are `[ ]`; the Track A delivery
   ledger has no `check_events`, `commit`, or `pull_request` yet (§6).

---

## 10. Recommendation

**pass-with-fixes.**

Must fix before PR A opens:

- **P1-1** — pre-bind colliding modules (or otherwise enforce FR-016) on the
  worker path, so `import <name>` resolves to the installed package in the worker
  as it does in the API process. Add a worker-subprocess test in the shape of
  `test_dropin_block_runs_in_a_fresh_worker`.
- **P1-2** — refuse *registration* of a colliding type file, not just report it,
  so the product's behaviour matches the error it shows the user and the owner's
  recorded OQ-1 answer. Add the first `TypeRegistry` test to
  `tests/blocks/test_dropin_type_import.py`.

Should fix before completion:

- **P2-1** — evaluate the three `hot_reload` invalidation events against the type
  registry, and widen `test_no_route_refreshes_one_registry_on_its_own` so its
  assertion matches its docstring.
- **P2-2** — restore the owner's "registration is refused" language to FR-016 and
  correct §14's claim about binding "before any drop-in runs", once the fixes land.

P3-1 through P3-4 are follow-ups, not merge blockers.

Everything else in Track A is solid work. The provisioning helper genuinely
collapses four divergent answers into one — I could not find a single surviving
bypass — the scan-order record is the best documentation in the diff, the §2.5
defect is really fixed on both the parent and worker paths, and FR-015 ends the
silent disappearance the spec complained about. The two P1s are both the same
missing edge: the FR-016 refusal knows about blocks and does not know about types
or about the worker.
