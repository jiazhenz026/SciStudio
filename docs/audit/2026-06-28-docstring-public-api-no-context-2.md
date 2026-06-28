# Audit: Docstring Quality Of The Public API Surface (no-context, run 2)

- Date: 2026-06-28
- Persona: audit_reviewer (no-context)
- Branch / worktree: `audit/1845-2` @ `/Users/jiazhenz/scistudio-wt-1845-audit2`
- Issue: #1845 (task-kind `docs`)
- Standard judged against: `docs/contributing/docstring-style.md`

## 1. Scope Audited

Public symbols on the read-only audit surface `src/scistudio/core/**` and
`src/scistudio/plot/**`. "Public" per the standard = a name in a module's
`__all__` or a non-underscore `@stable` / `@provisional` class/function.
`_`-prefixed and `@internal` members are out of scope.

Public surface inventory (from each module's `__all__` / stability markers):

- `scistudio.core.types`: `Array`, `Artifact`, `Collection`, `CompositeData`,
  `DataFrame`, `Series`, `Text`, `DataObject`, `TypeSignature`,
  `StorageReference` (10). `TypeRegistry` / `TypeSpec` / `serialization.*` /
  `_backend_defaults` are Internal/private and excluded.
- `scistudio.core.meta`: `ChannelInfo`, `FrameworkMeta`, `with_meta_changes` (3).
- `scistudio.core.storage`: `ArrowBackend`, `BackendRouter`, `CompositeStore`,
  `FilesystemBackend`, `StorageBackend`, `StorageMissingError`,
  `StorageReference`, `StorageReferenceInvalidError`, `ZarrBackend`,
  `get_router` (10).
- `scistudio.core.versioning`: `GitEngine`, `GitError`, `GitBinary`,
  `BundledGitMissing`, `DEFAULT_GITIGNORE`, `write_default_gitignore`,
  `is_dirty`, `modified_files` (8). The `versioning/_*_ops.py` modules are
  package-private and excluded.
- `scistudio.core.lineage`: `LineageStore`, `LineageRecorder`, `RunRecord`,
  `BlockExecutionRecord`, `DataObjectRow`, `BlockIORow`, `EnvironmentSnapshot`,
  `RunContext`, `get_run_context`, `set_run_context`, `reset_run_context` (11).
  `methods_export.*`, `hash_artifact_file`, and the SQL-schema constants are
  not exported and are excluded.
- `scistudio.plot`: 40 names re-exported via `plot/__init__.__all__` (models,
  context contract, target discovery, load/validate, scaffold/relink,
  execution, examples). `_context`, `_harness` are private.

## 2. Method

1. Mapped the public surface from every `__all__` and `@stable`/`@provisional`
   marker on the surface.
2. De-jargon: grepped the full internal-record citation family
   (`ADR-NNN`, `FR/DSN/SC/TRK/BUG/OQ-NNN`, `Addendum N`, `Add5`, `D7`-style
   decision suffixes, `Tier N`, `Phase Dxx`, `Codex`, `T-0xx`, bare `#NNNN`)
   across both trees, then opened every hit that landed in a docstring (not a
   `#` comment) to confirm whether the enclosing symbol is public.
3. Shape / attributes: programmatically iterated every `__all__` symbol and
   reported any public class/function/property/method with no docstring, and
   listed pydantic fields without a description, then confirmed attribute
   docstrings in source.
4. Example usability: ran `doctest` over the surface, both per-file and via a
   proper-import `testmod` harness (`PYTHONPATH=$PWD/src`), 55 examples total.
5. Reference render: ran `scripts/docs/build_reference.py` (generate +
   `mkdocs build --strict`) and confirmed it is green and that `core.types`
   (10/10 marked) and `core.meta` (3/3 marked) render.
6. Behavior: spot-read function bodies alongside their docstrings; no
   suspicious non-docstring change observed.

Validation results:
- `mkdocs build --strict OK` (full reference build green).
- doctest: 53 of 55 examples pass; the only 2 failures are both in
  `Array.sel` (finding P2-3 below).
- No public symbol, method, or property is missing a docstring anywhere on
  the surface.

## 3. Findings (ordered by severity)

### P1 — must fix before merge

**P1-1. `DEFAULT_GITIGNORE` ships internal ADR citations into every user's
project `.gitignore`.**
`src/scistudio/core/versioning/gitignore_template.py:26` and `:41`.

`DEFAULT_GITIGNORE` is a public `:data:` symbol (`__all__`), and
`write_default_gitignore()` writes its value verbatim into a new project's
`.gitignore` (`gitignore_template.py:74`). Its content contains:

- line 26: `# Data files (not versioned — see ADR-038 for run lineage)`
- line 41: `# Plugin venvs (per ADR-037)`

`docs/contributing/docstring-style.md` §2.1 forbids internal project records
in "a docstring (and **any prose a user reads**)". A `.gitignore` written into
the user's own project is the most directly user-facing prose on this surface,
and removing exactly this kind of citation is the purpose of the work. The
module docstring and the `:data:` attribute docstring (line 50) were already
cleaned; only the constant body still leaks. Suggested fix: drop the citations,
e.g. `# Data files (not versioned; tracked by the lineage layer instead)` and
`# Plugin virtual environments`.

### P2 — should fix

**P2-1. `PlotRunResult.stdout` / `.stderr` Field descriptions cite `FR-029`.**
`src/scistudio/plot/models.py:528` and `:530`.

```
stdout: str = Field(default="", description="Truncated stdout (FR-029).")
stderr: str = Field(default="", description="Truncated, sanitized stderr (FR-029).")
```

`PlotRunResult` is a public model. A pydantic `Field(description=...)` is
user-facing prose — it populates the JSON/tool schema surfaced to API and AI
callers — so the internal requirement tag `(FR-029)` violates §2.1. The
inconsistency is visible in place: the attribute docstrings immediately below
(lines 529, 531) are already clean ("Captured standard output ...",
"Captured standard error ..."). Fix: drop "(FR-029)" from both descriptions.
(No other Field description on the surface carries a citation — these two are
the only ones.)

**P2-2. `Array.sel` Example is not runnable.**
`src/scistudio/core/types/array.py:204-206`.

```
Example:
    >>> plane = stack.sel(z=10, c=0)    # one z-plane, one channel
    >>> band = stack.sel(z=slice(0, 5))  # the first five z-planes
```

These lines use the `>>>` doctest form but reference an undefined name `stack`
(and a `c` axis that is never set up), so `python -m doctest` reports 2
failures — the only failing doctests of the 55 on the surface. §2.2/§4 require
examples to be runnable. `Array` is one of the most-read user types, so the
example matters. Two clean fixes: (a) make it a real doctest by constructing
`stack` first — note `sel` reads from a storage backend, so a fully runnable
example needs a persisted array; or (b) convert it to an illustrative
`Example::` literal block (the form `Array.iter_over` already uses) so it is
not parsed as an executable doctest.

### P3 — nits

**P3-1. A few non-trivial public plot functions have no `Example:`.**
`validate_plot` (`plot/validation.py`), `load_plot` (`plot/validation.py`),
`relink_plot` (`plot/relink.py`), `preview_cache_dir` (`plot/runtime.py`).
The standard expects examples "almost always for ... non-trivial functions".
Coverage is otherwise good and uneven only here — peers `discover_targets`,
`run_plot_job`, `scaffold_plot_files`, `cache_key_for`, and `list_examples`
all carry examples. These four need project/filesystem setup, so a runnable
example is awkward; an illustrative snippet would still help a reader. Low
priority.

### Informational / out of scope (not findings)

- `scistudio.core.metadata_store` is a deprecation shim whose module/class/
  method docstrings cite `ADR-038` heavily (e.g. lines 1-5, 106-176). It
  carries **no** `__all__` and **no** `@stable`/`@provisional`/`@internal`
  marker, is not re-exported from `scistudio.core`, and is not one of the nine
  canonical reference roots, so it is not on the audited public surface. Noted
  only so a future reader does not mistake it for a gap.
- Internal-record citations remain abundant — and are **correctly retained** —
  in `#` maintainer comments and in private/`@internal` members:
  `types/registry.py`, `types/serialization.py`, `types/_backend_defaults.py`,
  the `versioning/_*_ops.py` modules, the SQL-schema string constants in
  `lineage/store.py`, and the docstrings of `@internal`/`_`-prefixed members
  (`Array.iter_over`, `DataObject.get_in_memory_data`, `FrameworkMeta.derive`,
  `FrameworkMeta.with_lineage_id`, `LineageRecorder._record_io`,
  `_extract_type_name`, `_wire_items_for_port`, `_validate_user`). §2.1
  explicitly allows moving citations into `#` comments and does not govern
  non-public members. The de-jargon pass on the *public* docstrings is
  thorough: every candidate citation found inside a docstring traced to an
  `@internal` or `_`-prefixed member.
- External standards / tooling kept correctly (not flagged): `UTF-8`,
  `xxhash`, `WAL`, `SQLite`, MIME-ish format names, and Sphinx roles
  (`:class:`, `:meth:`, `:func:`, `:attr:`, `:data:`, `:mod:`) render cleanly
  in the strict build.

## 4. Per-Module Summary

| Module | Verdict | Notes |
|---|---|---|
| `core/types` | pass-with-fixes | All 10 symbols + their public attrs/methods documented; `TypeSignature`/`Array` ClassVars carry attribute docstrings; 4/6 doctests pass. Only blemish: `Array.sel` non-runnable example (P2-2). |
| `core/meta` | pass | `ChannelInfo`/`FrameworkMeta`/`with_meta_changes` fully documented; all fields have attribute docstrings; 12 doctests pass; zero public-surface citations. |
| `core/storage` | pass | No citations anywhere; no missing docstrings; `StorageReference` doctests pass. |
| `core/versioning` | pass-with-fixes | All symbols documented and clean **except** the `DEFAULT_GITIGNORE` content citations (P1-1). |
| `core/lineage` | pass | Public surface clean; all citations live in private members / SQL constants / `#` comments. |
| `plot` | pass-with-fixes | Models are exemplary (every field has a Field description and/or attribute docstring + class examples); functions have strong shape. Fix `FR-029` Field descriptions (P2-1) and consider a few missing examples (P3-1). |

## 5. Overall Recommendation

**pass-with-fixes.**

The de-jargon of the actual public-surface docstrings is thorough and correct,
attribute documentation is comprehensive (no public symbol/method/property/attr
is undocumented), 53/55 doctests pass, and the strict reference build is green.
The remaining issues are small and localized: one citation leak written into
every user's `.gitignore` (P1-1, the only must-fix because it directly
contradicts the rule this work enforces and ships to users), two Field
descriptions still tagged `FR-029` (P2-1), and one non-runnable `Array.sel`
example (P2-2), plus an optional handful of missing plot examples (P3-1). None
indicate a behavior change.
