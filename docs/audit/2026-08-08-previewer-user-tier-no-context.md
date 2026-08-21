# Audit: Previewer User Tier And Drop-in Guards (no-context)

- Date: 2026-08-08
- Persona: `audit_reviewer`, **no-context** mode
- Branch / worktree: `audit/2017-previewer-user-tier-no-context` @
  `C:/Users/jiazh/workspace/SciStudio-wt-2017-audit`
- Audit surfaces: `src/scistudio/previewers/`, `src/scistudio/core/dropins.py`,
  `src/scistudio/ai/work_import/brief_template.md`, `tests/previewers/`,
  `tests/ai/test_work_import_brief.py`, `docs/adr/ADR-048.md`,
  `docs/specs/adr-048-preview-system.md`, `docs/specs/adr-052-public-api-surface.md`,
  `docs/specs/adr-053-personal-tool-library.md`, `docs/specs/adr-053-work-import.md`,
  `docs/architecture/ARCHITECTURE.md` (§9.6, §12).
- Judged against: the governing ADR/specs above as committed in this tree.

Per the dispatch I did not read any issue or PR text, manager checklists,
dispatch prompts, `.workflow/**`, chat/manager summaries, or git history for the
audit surfaces. The tree was audited as it stands. Everything below comes from
committed source, committed specs/ADRs, and commands I ran myself.

---

## 0. What I actually ran

| Command | Result |
|---|---|
| `PYTHONPATH=src python -m pytest tests/previewers/ -q --no-cov` | 93 passed |
| `PYTHONPATH=src python -m pytest tests/ai/test_work_import_brief.py -q --no-cov` | 71 passed |
| `PYTHONPATH=src python -m ruff check src/scistudio/previewers/ src/scistudio/core/dropins.py tests/previewers/` | All checks passed |
| Existence check of every test path declared in ADR-048 / spec frontmatter | one missing (P2-3) |
| Sentrux MCP | N/A — not available in this session |

(Interpreter: `C:/Users/jiazh/workspace/SciStudio/.venv/Scripts/python`, run from
the audit worktree root.)

---

## 1. Findings

### P2-1 — ADR-048 §3 precedence ladder omits the user tier the rest of the contract implements

**Evidence.**

- `docs/adr/ADR-048.md` §3 ("Previewer Resolution Contract", lines 169-184)
  lists a 9-step resolution order: project exact Collection/T, package exact
  Collection/T, project parent, package parent, core collection fallback, core
  base fallback, unknown/error. No user tier appears anywhere in the ladder.
- The same ADR already knows the tier exists: §2's role table says
  "`PreviewerRegistry` | Registry of core, package, user, and project previewer
  specs" and §11 requires tests for "previewer registry discovery for core,
  package, user, and project previewers".
- `docs/specs/adr-048-preview-system.md` FR-003 states the implemented 12-step
  ladder — "project exact collection, project exact item, user exact collection,
  user exact item, package exact collection, package exact item, project parent,
  user parent, package parent, core collection fallback, core base fallback,
  then unknown/error fallback. The user tier (#2017) sits between project and
  package at every specificity class".
- Code matches FR-003 exactly: `src/scistudio/previewers/router.py:51-55`
  (`_EXACT_TIERS`/`_PARENT_TIERS` = project, user, package) and the docstring
  ladder at `router.py:6-19`.
- Tests pin the implemented order: `tests/previewers/test_preview_routing.py:134-220`
  (14 user-tier precedence tests, all passing).

**Why it matters.** ADR-048 is the top-level contract; a reader of §3 alone gets
a precedence order the router does not implement, and the ADR is internally
inconsistent (§2/§11 name the user tier, §3 does not). The companion spec is
correct; the ADR's §3 numbered list was not updated when the tier was added.

### P2-2 — The `.scistudio/previewers.json` manifest is documented as registering previewer specs; the code only reads defaults

**Evidence.**

- `src/scistudio/previewers/project.py` module docstring (lines 12-19) describes
  the manifest as "a declarative manifest listing project previewer specs and
  default-previewer declarations".
- `docs/architecture/ARCHITECTURE.md` §12.5 (line 2181) says of
  `<project>/previewers/`: "a `.scistudio/previewers.json` manifest can also
  register them."
- The only code that touches the manifest is
  `project.py:_load_manifest_defaults` (lines 96-109), which reads solely
  `data.get("default_previewers")`. A repo-wide search for `previewers.json` /
  `default_previewers` finds no other consumer. No code path registers a
  previewer *spec* from the manifest, and no test exercises manifest-based spec
  registration.

**Why it matters.** Both the module docstring and the architecture document
describe unimplemented behavior as current. `docs/ai-developer/rules.md` §3
requires planned behavior to be labeled planned, not described as implemented. A
project author following either document would write a manifest `previewers`
list that is silently ignored. Either the docstring and §12.5 should be narrowed
to "default-previewer declarations", or the missing registration path should be
tracked as a labeled plan/TODO.

### P2-3 — ADR-048 declares a governed test path that does not exist

**Evidence.**

- `docs/adr/ADR-048.md` frontmatter `tests:` (line 65) lists
  `tests/previewers/test_preview_sampling.py`.
- That file does not exist anywhere in the tree (glob over `tests/**` finds no
  `test_preview_sampling.py`). The actual `tests/previewers/` contents are:
  `test_fallback_array.py`, `test_preview_data_access.py`,
  `test_preview_registry.py`, `test_preview_routing.py`,
  `test_preview_security.py`, `test_preview_session_cache_key.py`,
  `test_preview_session_exports.py`, `test_preview_session_manifest.py`,
  `test_previewer_dropins.py`, `test_table_cache_surface.py`.
- Every other test path in the ADR-048 and spec frontmatter that falls inside
  the audit surfaces exists and passes.

**Why it matters.** The ADR's `tests:` block is part of its governed surface; a
declared path that does not exist makes the governance record unverifiable as
written. The fix is trivial — repoint the entry at the file(s) that actually
carry the sampling coverage (e.g. `test_preview_data_access.py`) or add the
missing file.

### P3-1 — FR-005 scopes project-default tie-breaking to project/package matches; the router applies it to every tier

**Evidence.**

- `docs/specs/adr-048-preview-system.md` FR-005: "Projects must be able to
  declare explicit default previewers for a target type to resolve otherwise
  ambiguous **project or package** matches." (ADR-048 §3 itself is broader:
  "to resolve ambiguity".)
- `src/scistudio/previewers/router.py:_resolve_candidates` (lines 191-220)
  consults `registry.project_default_for(type_name)` for a priority tie in
  *any* tier — user exact/parent and the core fallback buckets included.
- `tests/previewers/test_preview_routing.py:213-220` pins ambiguity inside the
  user tier only for the no-default case; no test pins whether a project default
  resolves a user-tier or core-tier tie.

**Why it matters.** Low: the broader behavior is consistent with the
project > user > package direction and with ADR-048 §3's broader wording, so the
code is arguably the more defensible reading. But the spec text and the code
disagree on scope, and the divergence is untested either way. Worth a one-line
spec clarification or a pinning test.

### P3-2 — `previewers/__init__.py` opening summary omits the user tier

**Evidence.** `src/scistudio/previewers/__init__.py` lines 6-8: "Installed
packages add their own previewers through the ``scistudio.previewers`` entry
point, and a project may register project-local previewers and defaults." The
user library (`~/.scistudio/previewers`, loaded unconditionally by
`build_preview_service` at lines 124-125 and documented in the same file's
operational-layer list at line 22) is absent from the introductory sentence.
Cosmetic, but this is the package's front door.

### P3-3 — ADR-052 spec §8 inventory records stale file sizes

**Evidence.** `docs/specs/adr-052-public-api-surface.md` line 936 records
"`__init__.py` (164), `registry.py` (282), `router.py` (234), `session.py`
(617), `project.py` (120), `assets.py` (161)". Current sizes: 188 / 293 / 223 /
700 / 200 lines respectively (`assets.py` not re-measured here). The §8.4 table
itself (line 1053) *was* updated for the user tier (`load_user_previewers`,
`PROJECT_PREVIEWERS_MANIFEST`, "#2017"), so only the parenthetical counts are
stale. Pure record hygiene.

---

## 2. Verified consistent (no finding)

- **FR-002 user-tier discovery.** `registry.py` docstring tiers,
  `project.py:load_user_previewers` (unconditional, never raises),
  `build_preview_service` loads project before user so a project spec shadows a
  user spec with the same id — all pinned by
  `tests/previewers/test_previewer_dropins.py:200-234`, including the
  no-project-open case. Matches spec FR-002 and ADR-053 FR-060's analog.
- **FR-003/FR-004 routing.** The table-driven ladder implements the spec's
  12-step order; priority ties raise `RoutingAmbiguityError`; a collection
  target never resolves to an item-only previewer. 14 user-tier routing tests
  pass (`test_preview_routing.py:134-220`).
- **Drop-in security (the audit's named focus).** In
  `src/scistudio/core/dropins.py` and its previewer consumer
  `project.py:_scan_previewer_dropins`:
  - *sys.path scoping* — scan-time and render-time imports run inside
    `prepended_sys_paths(...)`; no permanent `sys.path.insert`
    (`project.py:152-155`, `session.py:396-398`). Tested:
    `test_scan_does_not_permanently_mutate_sys_path`,
    `test_lazy_string_provider_resolves_with_scoped_import_roots` (asserts the
    dir is off `sys.path` before and after a render).
  - *Name-collision guarding (FR-016)* — `guard_dropin_roots` refuses drop-in
    files whose stem an installed module owns, binds the installed module so it
    keeps winning, refuses the name outright via `_RefusedNameFinder` when the
    installed module cannot be imported (fail-closed), covers
    underscore-prefixed names in the collision question, and releases a refusal
    once the warranting entry is removed. Tested:
    `test_colliding_dropin_is_refused_and_recorded`,
    `test_underscore_dropin_collision_is_guarded_but_not_registered`,
    `test_refusal_releases_after_file_removed`.
  - *Bytecode freshness (FR-062)* — `evict_cached_bytecode` runs before every
    drop-in exec (`project.py:150`). Tested:
    `test_rescan_sees_same_size_same_second_edit`.
  - *Exception isolation* — `BaseException` (incl. `sys.exit()`) in a drop-in
    module or its factory is caught, recorded on registry diagnostics, and the
    scan continues; `KeyboardInterrupt` is re-raised (`project.py:156-179`).
    Tested: `test_broken_dropin_is_recorded_and_scan_continues`,
    `test_sys_exit_in_dropin_does_not_kill_scan`,
    `test_sys_exit_in_factory_does_not_kill_scan`.
  - One observation, not a finding: a failed drop-in leaves its half-executed
    module in `sys.modules` under the synthetic `_scistudio_<tier>_previewer_*`
    name (`project.py:147`). The name cannot shadow anything and is overwritten
    on the next scan; no action needed.
- **ADR-053 spec posture.** `docs/specs/adr-053-personal-tool-library.md` line
  36 and lines 114-115 explicitly record that the user previewer tier later
  landed as its own change (#2017), superseding the spec's original exclusion —
  the spec does not contradict the code.
- **Architecture docs.** ARCHITECTURE.md §9.6 (user/project previewer
  paragraphs) and §12 (§12.2.3 precedence sentence, §12.5 drop-in table) match
  the implemented discovery and routing, apart from the §12.5 manifest clause
  covered by P2-2.
- **Work-import brief.** `brief_template.md` carries the user-tier guidance
  ("Previewers do have a user-level tier (#2017): `~/.scistudio/previewers/` …
  project > user > package > core, ADR-048 FR-003", lines 138-142), which matches
  the implemented behavior. `tests/ai/test_work_import_brief.py` enforces that
  the template is spec §4.6's fenced block verbatim and that composition
  substitutes only inside "What they told us"; all 71 tests pass, so template,
  spec §4.6, and `brief.py` agree. `brief.py` writes no prose of its own and
  reads skip wording out of the template, as its docstring claims.
- **Public API surface.** `previewers/models.py.__all__` and
  `previewers/__init__.py.__all__` match the ADR-052 §8.1/§8.4 dispositions
  (operational layer and runtime-raised errors excluded from the advertised
  surface, `UnknownPreviewerError`/`UnknownTargetError` back-compat re-exports
  kept out of `__all__`).

---

## 3. Recommendation

**pass-with-fixes.**

Nothing found blocks on correctness or security: the user tier is implemented
per FR-002/FR-003 with passing tests at every rung of the ladder, and the
drop-in security properties named in the dispatch (sys.path scoping,
name-collision guarding, bytecode freshness, exception isolation) are all
implemented in the shared `dropins.py` and pinned by tests. The three P2 items
are documentation/governance-record drift — ADR-048 §3's stale precedence
ladder, the manifest registration over-claim (code docstring + ARCHITECTURE.md
§12.5), and a declared test path that does not exist — and should be corrected
before the work is treated as done under AGENTS.md §3.9 ("Documentation is part
of the change"; "MUST NOT describe future or missing behavior as implemented").
