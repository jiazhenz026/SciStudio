# Panel migration regression review (#2229)

**Persona:** test_engineer, no-context adversarial
**Branch:** `test/2229-panel-migration-regression`
**Compared:** `origin/main` (`cae11210c`, pre-migration) against
`track/adr-054-spec1-panel-contract` (`448c64c42`, post-migration)

## Question

Did any behaviour a person depended on before the previewer-to-panel migration
quietly change or disappear?

## Answer

**Mostly no, with one exception that costs a person a working panel.**

The routing ladder, the per-type choice, drop-in discovery, the collision guard,
path confinement, the bounded-read limits and the failure surfaces all survived,
and the new suite defends them better than the old one did. The retired
`scistudio.previewers` import path resolves, the `scistudio.previewers`
entry-point group is still scanned, the `get_previewers()` factory name is still
honoured, `<project>/previewers` and `~/.scistudio/previewers` are still the
drop-in directories, and a `previewer-choices.json` left by an older build is
still read and carried across.

What did not survive is **the way a pre-rename author actually wrote a spec.**
The compatibility package keeps the *name* `PreviewerSpec` importable but it
re-exports the renamed class itself, and that class renamed a field. A drop-in
file already sitting in someone's project — the exact file the pre-rename docs
taught and the pre-rename suite itself wrote — no longer registers.

## Method

No issue, checklist, dispatch prompt, PR, commit message or gate ledger was
read. The pre-migration contract was derived from `origin/main` directly:
the old subsystem source, and the old test suite, which is the most concrete
statement of the old contract that exists.

Two trees were materialised side by side and probed with the same scripts, so
every claim below is a measured difference rather than a reading of the diff.

Surviving tests were checked for vacuity by **mutation**: break the production
code the test names, and confirm the test goes red. A test not seen to fail is
recorded as unverified.

> One false lead, recorded because it nearly became a P0. An early mutation
> harness restored a file by `mv`-ing back a copy of identical byte length
> within the same second, which is precisely the `(mtime, size)` collision
> Python's bytecode cache cannot see — the repo has its own test for that hazard
> (`test_rescan_sees_same_size_same_second_edit`). A stale `.pyc` made
> `_EXACT_TIERS` read `(USER, PROJECT, PACKAGE)` and produced a convincing
> "FR-003 tier precedence is inverted" failure against a clean working tree.
> The harness now purges `__pycache__` and asserts `git diff --quiet src/`
> after every restore. All mutation results below were re-run under it.

## Inventory

Every test under `tests/previewers/**` and the four pre-migration API test files
on `origin/main`: **204 test functions across 18 files**.

Mechanical check, with `previewer`→`panel` normalised away: **every one has a
same-named counterpart in the new tree. Nothing was dropped.** Eleven of the
eighteen files are byte-identical modulo the rename and four more differ only
in trailing whitespace, leaving three with real content changes — which is
where every finding below came from.

| Pre-migration file | → now | Tests | Status |
|---|---|---|---|
| `tests/previewers/test_preview_routing.py` | `tests/panels/test_preview_routing.py` | 25 | defended (mutation-verified) |
| `tests/previewers/test_previewer_choice.py` | `tests/panels/test_panel_choice.py` | 24 | defended, **8 degraded** (below) |
| `tests/previewers/test_previewer_dropins.py` | `tests/panels/test_panel_dropins.py` | 24 | defended (mutation-verified) |
| `tests/previewers/test_preview_data_access.py` | `tests/panels/test_preview_data_access.py` | 21 | defended (mutation-verified) |
| `tests/previewers/test_preview_registry.py` | `tests/panels/test_preview_registry.py` | 11 | defended (mutation-verified) |
| `tests/previewers/test_preview_security.py` | `tests/panels/test_preview_security.py` | 7 | 6 defended, **1 vacuous** (below) |
| `tests/previewers/test_fallback_array.py` | `tests/panels/test_fallback_array.py` | 4 | defended (pure rename) |
| `tests/previewers/test_preview_session_manifest.py` | same path | 4 | defended (pure rename) |
| `tests/previewers/test_preview_session_package_imports.py` | same path | 3 | defended (pure rename) |
| `tests/previewers/test_preview_session_exports.py` | same path | 2 | defended (pure rename) |
| `tests/previewers/test_table_cache_surface.py` | same path | 2 | defended (pure rename) |
| `tests/previewers/test_preview_session_cache_key.py` | same path | 1 | defended (pure rename) |
| `tests/api/test_previewers.py` | `tests/api/test_panels.py` | 19 | defended (pure rename) |
| `tests/api/test_plot_preview_wiring.py` | same path | 20 | defended (pure rename) |
| `tests/api/test_previewer_choice_routes.py` | `tests/api/test_panel_choice_routes.py` | 13 | defended; URLs and file schema changed |
| `tests/api/test_previewer_discovery.py` | `tests/api/test_panel_discovery.py` | 11 | defended; **fixture changed authoring form** |
| `tests/api/test_preview_plot_jobs.py` | same path | 7 | defended (pure rename) |
| `tests/api/test_interactive_panels.py` | same path | 6 | 5 defended, **1 vacuous (pre-existing)** |

### The properties that stopped being defended

**1. `test_preview_security.py::test_sanitize_svg_back_compat_reexport_from_fallbacks` — vacuous.**
Created by #1823 to hold one promise: `scistudio.previewers.fallbacks` stays a
back-compat re-export of `sanitize_svg` "so out-of-tree packages do not
hard-break before migrating". The migration rewrote the subject to
`scistudio.panels.fallbacks` — the *current* path, which needs no back-compat
promise — while leaving the name and the word "legacy" in the docstring. The
test now asserts a tautology about the new module. The path it was written to
protect no longer imports.

**2. Eight tests in `test_panel_choice.py` — degraded.**
The pre-migration versions pinned the on-disk name as a literal
(`tmp_path / "previewer-choices.json"`); the migrated versions use
`CHOICES_FILENAME`. A file name is not an identifier — it exists on disks this
build did not write — and pinning it to the constant means the constant can move
and the tests move with it. The three tests covering the legacy-file migration
in `test_panel_resolution.py` have the same shape. **Mutation-verified:** setting
`LEGACY_CHOICES_FILENAME` to `previewer-choices-DISABLED.json` and running
`tests/panels`, `tests/api/test_panel_choice_routes.py` and
`tests/api/test_panel_source_routes.py` produced **zero failures**. The
behaviour is correct today; nothing would notice if it stopped being.

**3. `tests/api/test_panel_discovery.py`'s drop-in fixture — property moved, not kept.**
On `origin/main` this fixture wrote a drop-in importing
`scistudio.previewers.models` and passing `capabilities=`. It was the suite's
only end-to-end exercise of the pre-rename authoring form. It now writes
`scistudio.panels.models` and `features=`, so the compatibility path it used to
cover is uncovered — which is how P1 below stayed invisible.

**4. `tests/api/test_interactive_panels.py::test_panel_asset_route_rejects_path_escape` — vacuous, but pre-existing.**
Asserts only `status_code == 404` for `"../secret.js"`, which is also what a
missing file returns; removing the confinement check leaves it green. Identical
on `origin/main`, so **not a migration regression**. The new
`tests/panels/test_panel_asset_route.py` covers confinement properly and does
bite.

**5. Choice precedence is now implemented twice — degraded.**
`origin/main` had one merge (`load_choices`). The new tree has `load_choices`
and `load_choice_layers`, and `build_preview_service` uses the second. The three
tests naming this property all go through the first. **Mutation-verified:**
breaking project-over-user in `load_choice_layers` leaves
`test_the_project_layer_overrides_the_user_layer`,
`test_the_user_layer_shows_through_for_types_the_project_did_not_override` and
`test_load_choices_keeps_the_project_layer_over_the_user_layer` all green; only
one API test notices.

**6. `tests/panels/test_previewers_alias.py::test_a_spec_built_through_the_alias_is_a_panel_spec` — new, and vacuous about its own claim.**
Its docstring is "An unmigrated `get_previewers()` factory still builds a live
spec." It passes only the four required fields, every one of which the rename
left alone, so it cannot reach the one field that moved.

## Findings

### P1 — a pre-rename drop-in on disk no longer registers

The advertised-features field was renamed `capabilities` → `features` with no
keyword alias, and `PreviewerSpec` is the renamed class itself rather than a
wrapper. `capabilities` is the spelling the pre-rename `PreviewerSpec`
docstring used in its own worked example.

Same file, same location, both trees:

```
origin/main   REGISTERED: [... 'core.text.basic', 'probe.project']
migrated      REGISTERED: [... 'core.text.basic']
              TypeError: PanelSpec.__init__() got an unexpected keyword
              argument 'capabilities'. Did you mean 'capability'?
```

The scan survives and records a diagnostic — that part is right — but the panel
is simply absent from the palette. `PANEL_API_VERSION` is still `1`, so nothing
signals the incompatibility to a package that declares it targets version 1.

The same break reaches installed packages: the `scistudio.previewers`
entry-point group is still scanned, so an unmigrated package is still *found*,
and then its factory raises.

Wire shape changed with it: `spec.to_dict()` and the listing endpoint now emit
`features` where they emitted `capabilities`.

This is not only a legacy-disk concern. `docs/package-development/previewers.md`
— the shipped package-authoring guide, byte-identical to `origin/main` — still
teaches the broken call at line 43:

```python
PreviewerSpec(
    ...
    capabilities=("plot", "navigate", "diagnostics", "export"),
)
```

A package author following the in-repo guide today writes code that raises.
Replacing that guide is tracked (`docs/specs/adr-054-documentation.md` FR-012
marks it for deletion), so the stale doc itself is scheduled work rather than an
oversight — but replacing the guide does not translate `capabilities=` for the
drop-ins and packages already written against it, which is what the alias
package exists to protect and what this finding is about.

Left red: `tests/panels/test_unmigrated_author_surface.py::test_a_pre_rename_spec_still_accepts_the_capabilities_keyword`
and `::test_a_pre_rename_dropin_on_disk_still_registers`.

**What this finding is not.** The whole preview subsystem is declared
*provisional* — `models.py` says so in its own module docstring, and the
ADR-052 surface snapshot records `PanelSpec` at `tier: provisional` on both
trees. A breaking field rename is therefore *permitted* by the stability
policy, and this is not a contract violation. The finding is narrower and,
I think, still worth acting on: the alias package exists specifically so that
"an unmigrated package or an on-disk drop-in still loads", and for any spec
that declares features it does not achieve that; the break is silent from the
person's side (a diagnostic in a log, an absent entry in the palette); and
`PANEL_API_VERSION` stayed `1`, so there is no version signal a package could
have keyed on. Whether to add a keyword shim, bump the API version, or accept
the break and say so is a design call, not mine — but it should be a call
someone makes rather than a thing that happens.

Note also that `scistudio.previewers` no longer appears in
`tests/adr052_contract/expected_surface.json` at all, so the contract suite
does not cover the alias package in either direction. The two green tests in
the new file are the only automated statement that the entry-point group name
and the drop-in directory name are compatibility surfaces.

### P1 — positional construction is silently mis-bound

`target_types` was inserted as the fifth field, ahead of `supports_collection`.
A pre-rename positional caller gets no error:

| `PreviewerSpec("p", PACKAGE, "acme", "Image", True, 10, ("slice",))` | `origin/main` | migrated |
|---|---|---|
| `supports_collection` | `True` | `10` |
| `priority` | `10` | `('slice',)` |
| `target_types` | — | `True` |

A `TypeError` is recoverable; binding a bool to a tuple field and a tuple to an
int field is not. Reported separately from the keyword case because the fix for
one need not fix the other.

Left red: `::test_the_field_order_a_positional_caller_relied_on_is_unchanged`.

### P2 — ten retired module paths no longer import

`scistudio.previewers.{registry, router, session, fallbacks, assets, choices,
project, open_as, _raster, _table_cache}` all resolved on `origin/main` and now
raise `ModuleNotFoundError`. The alias package keeps only `__init__`, `models`,
`helpers`, `data_access`.

Most were core-internal and carried no stability promise. **`fallbacks` did**:
#1823 kept it precisely as a back-compat door for out-of-tree packages, and the
test guarding it is finding 1 above.

Left red: `::test_the_retired_fallbacks_reexport_still_resolves`.

### P3 — `scistudio.previewers.load_choices` no longer resolves

The pre-rename package imported it into its namespace, so
`from scistudio.previewers import load_choices` worked. It was never in
`__all__` and was never advertised author surface. Recorded for completeness.

Left red: `::test_the_alias_package_still_exposes_load_choices`.

### Not a defect — recorded so the next reader does not re-derive it

- **Five HTTP endpoints moved URL**: `GET /api/previews/previewers`,
  `POST /api/previews/reload` and the three `/api/previews/choices` routes are
  now under `/api/panels`. `/api/previews/sessions*` and
  `/api/previews/assets/*` still answer. The frontend was migrated in step —
  swept `frontend/src/**` for `/api/previews/` and every remaining call is a
  session or asset route that still exists. No stale caller found.
- **The choices file schema changed** from a flat `{type: id}` map to one map
  per capability, and the file was renamed to `panel-choices.json`. The legacy
  file is read, carried across on first write, and never deleted — verified
  end-to-end on both trees. Behaviour is correct; only its defence was thin.
- **`previewer_id` was *not* renamed** on the spec or on the wire, so that half
  of the authoring surface is untouched.
- **The failure surface is byte-identical on the wire.** `PreviewErrorCode` has
  the same eight members with the same values on both trees, including
  `unknown_previewer` and `duplicate_previewer_id`, which were deliberately left
  un-renamed. A frontend or a log reader keying on those codes is unaffected.
  Covered by the migrated suite; not mutation-verified, because the codes are
  data rather than behaviour.

## Tests added

`tests/panels/test_unmigrated_author_surface.py` — 7 tests, **5 red by design**

| Test | Defends | Now |
|---|---|---|
| `test_a_pre_rename_spec_still_accepts_the_capabilities_keyword` | the documented spec keyword | **red (P1)** |
| `test_the_field_order_a_positional_caller_relied_on_is_unchanged` | positional field order | **red (P1)** |
| `test_the_retired_fallbacks_reexport_still_resolves` | #1823's back-compat door | **red (P2)** |
| `test_the_alias_package_still_exposes_load_choices` | the retired convenience import | **red (P3)** |
| `test_a_pre_rename_dropin_on_disk_still_registers` | end-to-end: a project drop-in still appears | **red (P1)** |
| `test_the_project_dropin_directory_is_still_the_one_on_disk` | `<project>/previewers` named literally | green |
| `test_the_previewer_entry_point_group_is_still_the_group_scanned` | the group name named literally | green |

`tests/panels/test_choice_file_names_on_disk.py` — 6 tests, all green, all
mutation-verified to bite

| Test | Defends |
|---|---|
| `test_the_legacy_choices_file_is_the_name_that_is_on_disk` | `previewer-choices.json` as a literal |
| `test_the_current_choices_file_name_is_pinned` | `panel-choices.json` as a literal |
| `test_a_file_named_on_disk_by_a_pre_rename_build_is_read` | the migration read, through the literal name |
| `test_the_written_file_is_the_panel_named_one` | writes land on the new name, old one untouched |
| `test_the_runtime_merge_keeps_the_project_layer_over_the_user_layer` | precedence in `load_choice_layers`, the path the runtime uses |
| `test_the_two_merge_paths_agree` | the duplicated rule stays one rule |

## Mutation log

Every mutation reverted; `git diff --quiet src/` asserted clean after each.

| # | Production change | Target | Result |
|---|---|---|---|
| M1 | `_EXACT_TIERS` PROJECT/USER swapped | `test_preview_routing.py` | red — bites |
| M2 | `sanitize_svg` returns input unchanged | `test_preview_security.py` | 4 red — bites |
| M3 | project layer stops overriding user in `load_choice_layers` | choice tests | 1 red (API only) — **thin** |
| M4 | `page_size` no longer capped at `max_rows` | `test_preview_data_access.py` | 2 red — bites |
| M5 | `LEGACY_CHOICES_FILENAME` → a name no disk has | panels + 2 API files | **0 red — vacuous** |
| M6 | asset-route confinement check removed | asset-route tests | 6 red — bites |
| M7 | asset-suffix allowlist removed | asset-route tests | 5 red — bites |
| M8 | collision guard always reports none | `test_panel_dropins.py` | 4 red — bites |
| M9 | duplicate-id diagnostic text broken | `test_preview_registry.py` | 1 red — bites |

**Not verified by mutation**, and why: the plot-wiring, plot-jobs, session
manifest/exports/cache-key/package-imports and table-cache files are pure
renames of tests whose subjects the migration did not touch, so a mutation
would have measured the pre-migration suite rather than the migration. Their
status is "unchanged", not "proved to bite".

## Behaviour changed but not tested

- **The five moved HTTP endpoints.** A test asserting the old URLs must return
  would be asserting a decision back into place, not defending a person; the
  frontend moved with them and no stale caller exists. Recorded, not tested.
- **The `capabilities` → `features` wire key** on `GET /api/panels`. Same
  reasoning: the only consumer moved in step. The Python-side break is what
  reaches a person, and that is tested.
- **The choices file schema change** to per-capability maps. Covered by the
  migrated suite and verified working end-to-end on both trees.

## Checks run

| Check | Result |
|---|---|
| `pytest tests/panels` (before any change) | all pass; 3 skipped (symlink, needs elevation) |
| `pytest tests/panels tests/api` (baseline, before any change) | exit 0, no failures |
| `pytest tests/panels tests/api tests/architecture tests/adr052_contract tests/tutorials tests/blocks tests/engine` | **45 failures, every one accounted for**: 40 pre-existing `openpyxl`, 5 mine by design. Nothing else failed. |
| `ruff check src tests` | All checks passed |
| `ruff format --check src tests` | 901 files already formatted |
| frontend `npm test` | 194 files, **2275 passed** |
| frontend `npm run typecheck` | clean |
| frontend `npm run lint` | 0 errors, 42 pre-existing warnings |

The full-suite failure list, in full:

- `tests/blocks/io/test_io_coverage_matrix.py` — 29
- `tests/blocks/io/test_xlsx_io.py` — 11
- `tests/panels/test_unmigrated_author_surface.py` — 5 (mine, deliberate)

`tests/blocks/io` openpyxl failures: **40 here and 40 on `origin/main`**, the
latter verified directly in a materialised `origin/main` tree
(`grep -c "No module named 'openpyxl'"` = 40 on both). Pre-existing,
ambient-environment, not migration-related, discounted — and the count matching
exactly is what rules out the migration having added any of them.

`gate_record check --mode local` reports **one unsatisfied obligation: the test
check, failing on the five deliberate reds.** That is the gate working, not the
gate being wrong, and it is left that way. Making it green would mean editing
the five tests until they stop reporting the difference they were written to
report. `finalize` was not run.

Sentrux is not installed here; not attempted.
