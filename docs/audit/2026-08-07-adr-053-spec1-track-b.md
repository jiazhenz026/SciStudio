---
title: "Audit: ADR-053 Spec 1 Track B (personal tool library)"
status: Final
owners:
  - "@jiazhenz026"
related_adrs:
  - 53
language_source: en
---

# Audit: ADR-053 Spec 1 Track B (personal tool library)

- Date: 2026-08-07
- Persona: `audit_reviewer`, audit mode `with-context`
- Audit branch / worktree: `audit/adr-053-spec1-track-b` / `SciStudio-wt-audit-b`
- Audited branch: `feat/1995-adr-053-personal-tool-library` @ `327ae238`
  (B1 `19e31a10` + B3 `9d50bf00` + B2 `3a65d12f` + B4 `25ce0c18` + B6 `52d47616`
  + B5 `11871bef`, integrated by the manager)
- Base: `fix/2020-adr-053-registry-runtime-defects` @ merge-base `6a9eae24`
- Issues: `#1995`, `#1996`, `#2023`, `#2024`, `#2025`, `#2026`
- Judged against: `docs/specs/adr-053-personal-tool-library.md` §3, §4, §6–§9,
  §10.1, §10.2, §11, §14, §15; `docs/specs/frontend-block-palette.md`;
  `docs/adr/ADR-053.md` §3;
  `docs/planning/adr-053-spec1-personal-tool-library-checklist.md` §1.2, §2,
  §6.2, §8, §9; `AGENTS.md`; `docs/ai-developer/rules.md`;
  `docs/ai-developer/personas/audit-reviewer.md`

**Recommendation: pass-with-fixes.** No P1. Two P2 findings, six P3. Every
functional requirement in the track's scope is delivered and genuinely tested,
the six manager claims put to me all hold on the evidence, and the two P2s are
about the *strength of two anti-drift guards*, not about behaviour: one guard
test cannot detect the regression it was written to prevent, and one refusal
set diverges between the frontend entry points and the MCP tool in a narrow
case the spec's own vocabulary covers.

## 1. Verification Performed

| Check | Result |
|---|---|
| `cd frontend && npm run check:ci` | **PASS**, exit 0 — eslint, prettier `format:check`, `tsc` typecheck, 133 test files / **1381 tests passed**, production build |
| `PYTHONPATH=./src python -m pytest tests -q` | **9 failures, all pre-existing host failures** — see §1.1. Coverage gate met (87.03% ≥ 70%). |
| Track B backend subset (6 files, `--no-cov`) | **169 passed, 2 skipped, 0 failed**, exit 0 |
| import-linter (`lint-imports`) | **13 contracts kept, 0 broken**, 341 files / 1134 dependencies |
| Sentrux | **unavailable on this host** — no `sentrux` on `PATH`, no Sentrux MCP server reachable in this session. Recorded as unavailable, not as clean. |
| Browser smoke check of the palette | **NOT PERFORMED.** This environment has no browser and no way to drive one. The Data types tab, the empty-state sections, popover clickability and drag are covered by jsdom component tests (`BlockPalette.test.tsx`, `TypePalette.test.tsx`, `entryPoints.test.tsx`, `useHoverPopover.test.tsx`) which I read and which do assert those behaviours — but that is not a browser smoke check and I am not claiming one. |
| Symlink containment | **Partially verified locally.** This host does not permit symlink creation, so `test_symlink_escaping_the_user_root_is_not_in_that_tier` (FR-002) and `test_a_symlink_escaping_the_library_is_refused` (FR-007) **skip** here. I read both and confirm they would exercise the case; Linux CI is the authoritative evidence. The *directory-junction* escape case (`test_a_linked_subdirectory_cannot_smuggle_a_nested_write`) does run on Windows via `mklink /J` and passes, so the FR-007 "resolved real path, not string prefix" rule is exercised on this platform for the directory case. |

Note on the frontend run: my first `npm run check:ci` in this worktree exited
"successfully" only because `node_modules` was absent and every stage failed
with `'eslint' is not recognized`, with the exit code swallowed by a pipe. The
result recorded above is from a real run after `npm ci`, with the exit code
captured. Flagging it because a checklist row filled from the first run would
have been false evidence.

### 1.1 Python Suite

`PYTHONPATH=./src python -m pytest tests -q` produced **exactly the nine
failures the manager documented** (checklist §9, `2026-08-07 | manager`) and no
others:

| Failing test | Documented class |
|---|---|
| `tests/api/test_filesystem_browse.py::…::test_overlength_path_returns_400_not_500` | Windows overlength path |
| `tests/api/test_mcp_transport_publish.py::test_project_open_route_starts_project_mcp_socket` | AF_UNIX |
| `tests/api/test_mcp_transport_publish.py::test_project_open_route_rebinds_missing_project_mcp_socket` | AF_UNIX |
| `tests/cli/test_install.py::test_claude_and_codex_share_identical_mcp_env` | TOML backslash escaping |
| `tests/desktop/test_terminal_post_rc.py::test_zsh_invocation_writes_zdotdir_that_reprepends_after_user_rc` | POSIX shell rc |
| `tests/desktop/test_terminal_post_rc.py::test_bash_invocation_uses_rcfile_that_reprepends` | POSIX shell rc |
| `tests/qa/test_gate_record_hooks.py::test_write_guard_hook_allows_write_inside_linked_worktree` | #2011 `/bin/sh` hook family |
| `tests/qa/test_gate_record_hooks.py::test_write_guard_hook_blocks_write_targeting_main_checkout` | #2011 `/bin/sh` hook family |
| `tests/qa/test_gate_record_hooks.py::test_write_guard_hook_allows_bypass_label_for_main_checkout` | #2011 `/bin/sh` hook family |

Rather than take the attribution on trust I checked it structurally:
`git diff 6a9eae24 327ae238` touches **none** of the modules these nine
exercise — `api/routes/filesystem.py`, `api/routes/projects.py`,
`api/mcp_transport.py`, `cli/install.py`, `desktop/**`, `qa/**` are all outside
the Track B diff. Combined with the manager's and AUDIT-A's independent
reproduction on the base tree, the attribution holds. Linux CI on PR B remains
the authoritative evidence for `python_tests`.

Two additional skips are Track B's own and are the symlink cases recorded in
the table above.

To get a positive signal on the track's own surface I ran the six Track B
backend test files directly:

```
PYTHONPATH=./src python -m pytest tests/api/test_block_origin_tiers.py \
  tests/api/test_user_library_write.py tests/api/test_types_routes.py \
  tests/ai/test_mcp_tools_library.py tests/core/test_type_colour.py \
  tests/core/test_types.py --no-cov -q
→ 169 passed, 2 skipped, exit 0
```

## 2. The Six Manager Claims

### Claim 1 — FR-025, one promotion implementation reaching E1, E2, E5, and matching E3

**Upheld, with one narrow exception recorded as P2-2.**

The structural claim is true and stronger than the grep the manager ran.
`promoteToUserLibrary(` has exactly one definition
(`frontend/src/components/promotion/promoteToUserLibrary.ts:236`) and one
non-test call site (`runPromotion.ts:28`). `runPromotion(` has exactly one
call site — `PromoteToLibraryAction.tsx:63`. And `PromoteToLibraryAction` is
the *only* control any entry point renders:

| Entry point | Renders | File |
|---|---|---|
| E1 | `<PromoteToLibraryAction entryPoint="E1" …>` | `Toolbar.parts/FileOperationsGroup.tsx:137` |
| E2 | `<PromoteToLibraryAction entryPoint="E2" …>` in `NodeActionToolbar`'s new `trailing` slot | `nodes/BlockNode.tsx:172` |
| E5 (blocks) | `<PromoteToLibraryAction entryPoint="E5" …>` | `BlockPalette.tsx:51` |
| E5 (types) | `<PromoteToLibraryAction entryPoint="E5" …>` | `TypePalette.tsx:54` |

So the path is: four render sites → one component → one `runPromotion` → one
`promoteToUserLibrary`. The per-entry-point code is confined to building a
`PromotableItem` in `promotable.ts` (`promotableBlock`, `promotableType`,
`promotableFileTab`), which is the difference §6.2 permits.

`entryPoints.test.tsx` proves it rather than asserting it: it mocks
`runPromotion` and shows all three surfaces call the same mock with items that
`toMatchObject({ target: "blocks", kind: "block", origin: "project" })`.

The E3 correspondence is where it is not exact — see **P2-2**.

### Claim 2 — FR-019 hidden, not disabled; resolved origin, not tier-1

**Upheld.**

Three independent layers, and all three test the *resolved* origin:

1. `isPromotableOrigin(origin) => origin === "project"` (`promotable.ts:61`).
   Not `source === "tier1"`, not "has a file path". `promotable.test.ts:39`
   pins the exact trap the spec names: *"refuses a user-library block even
   though it is tier-1 with a file path"*.
2. `PromoteToLibraryAction` returns `null` — not a disabled button — when
   `!isPromotable(item)` (`PromoteToLibraryAction.tsx:55`).
3. **The `actions` prop itself is withheld.** The manager's reading of B5's
   reasoning is correct and I verified the mechanism: `DetailPopover` renders
   `{actions ? <div className="mt-2 border-t border-stone-100 pt-2">…</div> : null}`
   (`palette/DetailPopover.tsx:70`). A JSX element is always truthy, so passing
   `<PromoteToLibraryAction/>` that renders `null` would leave an empty ruled
   strip under every built-in tile. Both palettes therefore decide *before*
   passing: `promoteAction()` returns `undefined` for a non-promotable item
   (`BlockPalette.tsx:48`, `TypePalette.tsx:51`).

Test coverage for all three FR-019 cases, on the surfaces that render them:
`entryPoints.test.tsx:185` is `it.each` over **built-in, packaged, and already
in the library** for E2, and `:236` the same three for E5-blocks — the latter
additionally asserting `queryByTestId("palette-popover-actions")` is absent,
which is the hairline-strip claim tested directly.
`promoteToUserLibrary.test.ts:120` adds defence-in-depth for a programmatic
caller.

Gap, minor: the E5-**types** hidden case is tested only for `core`
(`entryPoints.test.tsx:281`); `user` and `package` type origins are covered by
the pure `isPromotableOrigin` unit tests but not through the type popover.
Recorded as P3-5.

### Claim 3 — FR-067, the loading window, and whether the test is vacuous

**Upheld. No placeholder colour exists anywhere in the path, and the test is
not vacuous.**

The no-placeholder claim, traced end to end:

- `typesSlice.ts:28` initialises `declaredTypeColors: undefined`; the only
  writer is `setTypes`, which sets it to a real map built from a complete
  listing (`:33`). There is no intermediate value.
- `useDeclaredTypeColors()` returns that field verbatim and triggers the load
  (`useTypeCatalog.ts:92`). `loadTypeCatalog` swallows a failure with a warning
  and never publishes a partial catalogue (`:66`).
- `resolveTypeColor` / `resolveRingColor` read `declared?.get(name)` — an
  optional chain, so `undefined` short-circuits to the pre-ADR-053 branches
  (`typeColorMap.ts:234`, `:280`).
- Both canvas consumers pass it straight through: `PortHandles.tsx:206` and
  `WorkflowCanvas.tsx:334`.

I grepped every `declaredTypeColors` / `buildDeclaredTypeColors` reference in
`frontend/src`; there is no default value, no `?? new Map()`, no sentinel
colour.

The non-vacuity claim is also correct, and specifically at
`typeColorSource.test.tsx:199` (*"does not re-layout any port when the listing
lands"*): it snapshots `{top,left,right}` for two ports, lands the catalogue,
asserts both geometries unchanged **and then** asserts
`handleFor(container,"declaring").style.backgroundColor === DECLARED_RGB` with
the comment *"so the no-re-layout assertion above is not vacuous"*. Something
demonstrably changed in the same act.

One observation, not a finding: the sibling test *"does not flash an undeclared
port when the listing lands"* (`:192`) asserts only `after === before` and
would pass on a component that rendered nothing. It is non-vacuous *in
combination* with `:199`, which shares the fixture and proves the listing
landed. I would not ask for a change.

Also worth stating plainly: a type that **does** declare a colour genuinely
changes colour when the listing arrives. That is inherent to FR-066's
two-response design and §14 accepts it; FR-067's actual obligation — that the
fallback be the correct pre-ADR-053 answer rather than a placeholder, so the
window is invisible for every type in the product today — is met.

### Claim 4 — FR-051, an undeclared type renders unchanged

**Upheld, verified independently against the base tree.**

I diffed `frontend/src/config/typeColorMap.ts` across the range. For a type
with no entry in `declared` (which includes `declared === undefined`):

- `resolveTypeColor`: the only added code is
  `const own = declared?.get(name)?.fill; if (own) return own;` ahead of the
  existing chain. `own` is `undefined`, so control reaches `typeColorMap[name]`
  → `typeHierarchy` `base_type` → `hashTypeName` exactly as before. **Byte
  identical.**
- `resolveRingColor`: `own?.ring` and `own?.fill` are both `undefined`, so
  control reaches `subtypeRingColorMap[name]` → the hash-derived ring, as
  before. The **one deletion** in the range is the
  `typeHierarchy → entry.ui_ring_color` branch, which spec §2.8 records as
  never populated and which I re-verified is still never populated (Claim 5).
  So its removal is a no-op for every type that exists.

Independent corroboration beyond reading: `typeColorMap.test.ts:66` asserts a
`type_hierarchy` entry carrying `ui_ring_color: "#123456"` is ignored;
`typeColorSource.test.tsx:155` asserts an undeclared type is identical on both
surfaces; `TypePalette.test.tsx:155` asserts *"leaves an undeclared type on
today's colour"*; `tests/core/test_type_colour.py:123`
(`test_an_undeclared_type_is_unchanged`) covers the backend half.

The blast radius §14 bounds is therefore genuinely confined to types that opt
in.

### Claim 5 — FR-066, `TypeHierarchyEntry.ui_ring_color` left dead

**Upheld on the fact. The regression guard is weak — P2-1.**

The fact: `routes/blocks.py:446` constructs `TypeHierarchyEntry(name=…,
base_type=…, description=…)` and nothing else, so the field keeps its
`None` default. I grepped every `ui_ring_color` in `src/`, `frontend/src/` and
`tests/`; the only *populating* assignment is `types.py:161`, which fills the
**new** `TypeSummary.ui_ring_color` on the types listing — that is FR-050's
required supply point, a different model. There is no second supply point:
`resolveRingColor` no longer reads `typeHierarchy` at all, and
`buildDeclaredTypeColors` is fed only from `TypesSlice.types`, whose only
writer is the `GET /api/types/` response.

The weakness is the guard B2 claims closes the door — see **P2-1**.

### Claim 6 — B6 package-name parity, and whether the residual is incompleteness

**Upheld on both halves.**

Agreement is structural, as claimed. `routes/blocks.py:226` computes
`package_name = raw_pkg if _is_plugin_package(raw_pkg) else ""` from
`BlockSpec.package_name`. `routes/types.py:98`
(`package_names_by_import_root`) walks **the same** `block_registry.all_specs()`,
reads **the same** `spec.package_name`, and filters with **the same**
`_is_plugin_package` imported from `routes.blocks`. One string, read once, from
one registry. Types join on the import root
(`TypeSpec.package_root`, recorded first-hand by the discovery pass —
`registry.py:_spec_for_class`), never inferred from a file path.

`test_one_installed_distribution_names_itself_once_across_both_tabs`
(`tests/api/test_types_routes.py:440`) is the right shape for the claim: it
writes a real source package shipping one block and one type, scans both
through real `BlockRegistry` / `TypeRegistry` discovery, and asserts
`listed.package_name == _block_summary(block_spec, blocks).package_name`. Not a
hand-built spec.

The stated residual is incompleteness, not contradiction, and I checked the
mechanism rather than taking it: a distribution whose `PackageInfo.name` is a
display string (`"SRS Imaging"`) fails `_is_plugin_package`, so the **block**
side blanks it too and the Blocks tab titles that section from the frontend
`derivePackage` dotted-prefix heuristic. The types side has no equivalent and
declines to invent one, returning `null`, and those types land in the lumped
`Packages` section (`typeModel.ts:72`, `PACKAGES_SECTION_ID`). The two tabs
therefore never report two different names for one distribution; the types tab
is simply less granular. `_AMBIGUOUS` handles the two-distributions-one-root
case the same way. Nothing is dropped —
`test_a_distribution_the_blocks_tab_does_not_name_reports_null` and
`typeModel.test.ts:76` pin that.

Narrowness worth recording: every plugin shipped in this repository is named
`scistudio-blocks-*`; `"SRS Imaging"` appears only in a test fixture
(`tests/blocks/test_registry.py:359`). The residual is close to hypothetical
today. Recorded as P3-1 so it is visible rather than lost.

## 3. Findings

### P2-1 — The FR-066 dead-field guard cannot detect the regression it was written to prevent

`tests/api/test_types_routes.py:288`
(`test_type_hierarchy_still_carries_its_dead_colour_field`) asserts
`all(entry["ui_ring_color"] is None for entry in hierarchy)` against the shared
`client` fixture. That fixture (`tests/api/conftest.py:23`) builds an app over
an isolated empty home, so the only registered types are the six core bases —
**none of which declares a colour**. Every `TypeSpec.ui_ring_color` in that
fixture is already `None`.

Consequence: if someone reintroduced the rejected design by writing
`ui_ring_color=entry.ui_ring_color` into the `TypeHierarchyEntry` construction
at `routes/blocks.py:446`, this test would still pass. Its docstring claims the
opposite — *"this assertion is what stops the rejected design from being
reintroduced"* — and checklist §8.3 records the same claim for B2.

The underlying contract is intact today (Claim 5); this is about the guard, and
it is the "test exists but asserts nothing meaningful" category rather than a
behaviour defect.

Fix: register a type that *does* declare a ring colour before asserting — the
file already has `_write_type(..., ui_color=…)` and a user-types-dir fixture
pattern for exactly this — then assert the hierarchy entry is still `None`
while the `/api/types/` entry for the same type carries the declared value.
That version fails on the rejected design and passes on this one.

### P2-2 — E3's refusal set is narrower than E1/E2/E5's, and the correspondence table omits the difference

`promoteToUserLibrary.ts:17-24` states the E3 correspondence *"refusal for
refusal"* as a table. It is accurate for the three rows it lists, and silent on
a fourth.

The frontend condition is `origin === "project"`, so it refuses **five** origins
(`builtin`, `package`, `user`, and the FR-002 `custom` fallback). The MCP tool
refuses only two cases (`tools_library.py:154-171`):

- no `file_path` → built-in/packaged;
- `source.parent == library_root` → already in the library.

It has no test for the `custom` tier at all. A tier-1 block whose `file_path`
resolves under neither root — a symlink inside `{project}/blocks/` pointing
outside it, or a differing Windows drive, the two cases FR-002 names — is
**hidden** by E1/E2/E5 and **accepted** by `promote_to_user_library`.

Second-order cause, and the part worth the manager's attention: the tool cannot
consume the FR-003 shared resolver. `resolve_origin` lives in
`scistudio.api._block_source`, and the import-linter contract *"AI must not
depend on api"* forbids the AI layer from importing it, so B1 wrote a narrower
equality check instead. `scistudio.core.dropins` — which both layers already
import, and which checklist §6.2 established as the home for exactly this kind
of shared answer — would have been reachable from both.

Impact is bounded: the worst outcome is the agent copying a file the user could
have copied by hand, into the user's own library. But "refusal for refusal" is
asserted in a module docstring, in `CHANGELOG.md`, and in checklist §8.3, and it
is not currently true.

Fix options, smallest first: (a) narrow the docstring/CHANGELOG claim to the
three rows it actually covers and add the `custom` row as a known difference;
(b) add the missing refusal to `tools_library.py` by resolving the source path
against both tier roots; (c) move `resolve_origin` (or just its containment
predicate) into `scistudio.core.dropins` so the AI layer and the API share one
implementation, which is what FR-003 is written to require. Only (c) closes it
structurally.

### P3-1 — FR-040's per-package split is achieved only for `scistudio-blocks-*` distributions

B6's stated residual, verified in §2 Claim 6. A distribution whose
`PackageInfo.name` is a display string gets a named section on the Blocks tab
(from the frontend `derivePackage` heuristic) and no matching section on the
Data types tab. No contradiction and nothing dropped; FR-040's *"one section per
package A→Z"* is simply partial for that class of package. Follow-up material,
not a Track B fix — the honest alternative was inventing a name.

### P3-2 — E1 infers `project` from the tab path rather than reading the resolved origin

`promotableFileTab` (`promotable.ts:125`) hardcodes `origin: "project"` for any
project file tab whose path starts with `blocks/` or `types/`. For the FR-002
fallback case — a symlinked drop-in escaping the project — the palette and the
canvas hide the action (backend-resolved `custom`) while the editor toolbar
offers it. The same class of divergence as P2-2, on the frontend side.

The reasoning in the docstring is sound for the ordinary case and the file
containment checks are careful (nested paths and non-`.py` refused,
`promotable.test.ts:119` and `:123`). Worth a one-line note in the docstring
that the inference is a path-shape claim rather than the backend's answer, or a
lookup through the block summary when one exists.

### P3-3 — Creating a file in the user library still requires an open project

`createDropinFile` early-returns on `!currentProject`
(`useProjectActions.ts:420`, `:437`) and `App.tsx`'s `whenProjectOpen` passes
`undefined` to the toolbar without one, so both New-menu entries are disabled.
FR-029/FR-030 make the library a first-class destination and FR-060 establishes
that the user tier has no relationship to which project is open, so the
library half of E4 is unreachable exactly when a first-run user would most
benefit from it. The project half legitimately needs a project (for the
`projectName` in the dialog copy and the project write). Small, and arguably
Learning-Center territory; recording it rather than deciding it.

### P3-4 — `resolveRingColor` keeps a now-unused `typeHierarchy` parameter

After FR-066 removed the `ui_ring_color` branch, `typeHierarchy` is read
nowhere in `resolveRingColor` (`typeColorMap.ts:274`). It is still passed at
every call site. Keeping it preserves positional parity with `resolveTypeColor`
and avoids churn at four call sites, which is a defensible choice — but a
reader has no way to tell that from the signature. One comment, or `_typeHierarchy`,
would settle it.

### P3-5 — FR-019's hidden case is tested for only one type origin on the types popover

`entryPoints.test.tsx:281` covers `core`. `user` and `package` type origins
reach `isPromotableOrigin` through the same one-line predicate and are covered
as pure units (`promotable.test.ts`), so the risk is low, but the block side got
the full `it.each` over all three and the type side did not. One `it.each` would
make the two surfaces symmetric.

### P3-6 — FR-003's implementation-level anti-drift test is weaker than its docstring

`tests/api/test_block_origin_tiers.py:207`
(`test_the_two_surfaces_are_the_same_function`) asserts only that the two
`OriginSurface` constants carry the expected labels and directories. Its
docstring says *"If a second path comparison is ever added for types, this stops
being true"* — it would not. A second comparison added anywhere would leave this
test green.

I discharged the check by hand instead and it passes: I grepped
`is_relative_to`, `realpath`, `commonpath` and `.parts` across
`src/scistudio/api/`, `src/scistudio/core/types/` and
`src/scistudio/ai/agent/mcp/`. Every origin-tier comparison routes through
`_block_source.resolve_origin`; `routes/types.py::_type_origin` is a pure
adapter holding no rule (pinned by
`test_the_origin_adapter_delegates_the_whole_vocabulary`); the only other path
containment on this subject is `tools_library.py`'s, which is P2-2. So **FR-003
holds** — but it holds because nobody has added a second one, not because a
test would catch it.

## 4. Spec §11 Test Plan — Row By Row

Only the rows in Track B's scope are walked; the §5 / §10.3 / §10.4 rows belong
to Track A and were audited separately.

| §11 row (FRs) | Test | What it asserts | Fails if the requirement is removed? | Verdict |
|---|---|---|---|---|
| Origin tiers (FR-001, FR-002) | `tests/api/test_block_origin_tiers.py` ×7 | user / project / no-project fallback / outside-both / absent path / builtin+package unchanged / Windows other-drive | Yes — each asserts a distinct returned label | **Pass** |
| Origin tiers, symlink case (FR-002) | same file, `test_symlink_escaping_the_user_root_is_not_in_that_tier` | realpath before containment | Yes, **but skipped on this host** (no symlink privilege). Linux CI authoritative. | **Pass (unverified locally)** |
| Shared resolver (FR-003) | `test_one_resolver_serves_the_type_surface`; `test_the_two_surfaces_are_the_same_function`; `test_the_origin_adapter_delegates_the_whole_vocabulary` | the type surface resolves the whole vocabulary through `resolve_origin`; the adapter delegates | Behaviourally yes. Structurally **no** — see P3-6 | **Pass with P3-6** |
| Block list carries origin (FR-004) | `test_block_list_carries_each_tier`, `test_block_schema_and_source_endpoints_agree_with_the_palette` | all three endpoints report the same resolved tier | Yes | **Pass** |
| Types listing origin vocabulary (FR-005) | `test_user_and_project_types_report_their_own_tiers`, `test_a_dropin_outside_both_tiers_falls_back_to_custom`, `test_a_core_types_file_path_never_reads_as_a_tier` | `core` / `user` / `project` / `package` / `custom`, incl. the "core has a real file too" trap | Yes | **Pass** |
| Write endpoint (FR-006 – FR-008) | `tests/api/test_user_library_write.py` ×14 | both targets land; target never inferred from content; traversal / drive-relative / non-`.py` / empty refused; symlink and junction escapes 403; existing file 409; overwrite opt-in only | Yes. Symlink row skips locally; the **junction** row runs on Windows and passes | **Pass** |
| Project endpoint unchanged (FR-009) | `test_the_project_endpoint_still_rejects_escaping_paths`, `test_the_project_endpoint_cannot_reach_the_user_library` | the first door did not widen | Yes — asserts a 403 the new door would have to break to pass | **Pass** |
| Registry refresh (FR-010) | `test_a_written_block_is_discoverable_without_a_restart`, `…_type_…` | written file is registered without restart | Yes | **Pass** |
| MCP promotion (FR-011) | `tests/ai/test_mcp_tools_library.py` ×16 | copies, refreshes, renames, refuses builtin / already-in-library / unregistered / hostile name; bridge visibility | Yes. **Does not cover the `custom` tier** — P2-2 | **Pass with P2-2** |
| Promotion semantics (FR-017 – FR-019) | `promoteToUserLibrary.test.ts:95` (copy not move — asserts the io recorded reads only and writes only into the library); `entryPoints.test.tsx:185`/`:236` `it.each` over built-in, packaged, already-in-library; `promotable.test.ts:39` | copy-only; hidden not disabled for all three; the condition is resolved origin not tier-1 | Yes, all three | **Pass** |
| Collision prompt (FR-018) | `promoteToUserLibrary.test.ts:132` ×3; `dialogs.test.tsx:118` ×3 | first write is `overwrite:false`; overwrite only after the user clicks; a rename re-enters with `overwrite` back at `false` | Yes — the `overwrite` flag is asserted on the recorded write calls | **Pass** |
| Reveal (FR-020) | `revealInLibrary.test.tsx` ×6 | palette expanded, catalogue refreshed, search narrowed, tab switched, inline confirmation names the item and section, warnings verbatim, failure reported | Yes | **Pass** |
| Cascade (FR-021 – FR-024) | `cascade.test.ts` ×10, `promoteToUserLibrary.test.ts:203` ×6, `dialogs.test.tsx:45` ×4, `pythonImports.test.ts` | AST-ish static parse (docstrings stripped, continuations joined, aliases resolved); classification by transported backend origin; single confirmed action; **declining still promotes and warns**; second level reported never promoted; never walks past level two | Yes — `:235` asserts the block is still written after a decline **and** that the warning text names the types | **Pass** |
| One implementation (FR-025) | `entryPoints.test.tsx:291` | E1, E2, E5 all reach one mocked `runPromotion` with matching items | Yes | **Pass** (E3 caveat: P2-2) |
| Type colour declaration (FR-049, FR-050) | `tests/core/test_type_colour.py` ×13; `test_a_declared_colour_reaches_the_listing` | `DataObject` gains two `ClassVar`s defaulting to `None`; registry collects and normalises; listing surfaces them | Yes | **Pass** |
| Colour precedence (FR-051) | `typeColorMap.test.ts` ×~12; `TypePalette.test.tsx:149`/`:155`; `typeColorSource.test.tsx:155` | declared > `typeColorMap` > hash; undeclared unchanged, on both surfaces | Yes | **Pass** |
| Colour parity (FR-066, FR-051) | `typeColorSource.test.tsx:146` | one file renders a palette tile and a canvas port and asserts the same RGB | Yes — and it is the right shape, since parity is a claim about two surfaces agreeing | **Pass** |
| Colour load window (FR-067) | `typeColorSource.test.tsx:176`, `:192`, `:199` | pre-listing fallback is the pre-ADR-053 answer; undeclared port unchanged on landing; geometry unchanged **and the declaring port did change** | Yes, non-vacuously (see Claim 3) | **Pass** |
| Invalid colour (FR-052) | `typeColorSource.test.tsx:222`; `typeColorMap.test.ts` ×3; `test_type_colour.py:158`, `:189`, `:202`, `:213`, `:260` | warns and falls through on both surfaces, backend and frontend | Yes | **Pass** |
| Extensions per type (FR-054 – FR-056) | `test_types_routes.py:135`, `:143`, `:154`; `typeModel.test.ts:241` ×3 | derived from `FormatCapability`; load/save separate incl. a real save-only asymmetry; empty lists → explicit no-formats copy | Yes | **Pass** |
| Palette sections (FR-035 – FR-038) | `BlockPalette.test.tsx:219` ×10; `paletteModel.test.ts`; `sections.test.ts` ×12 | order, both tiers rendered empty with teaching copy, teaching copy dropped under a filter, origin-first grouping, `custom` → This Project, backend-without-origin still renders | Yes — `:238` asserts full section order and `:251` the empty-state copy | **Pass** |
| Data types tab (FR-039 – FR-041) | `TypePalette.test.tsx` ×15; `typeModel.test.ts` ×~25 | panel titled `Data types`, mirrors Blocks structure, tier sections + empty states, tile fill+ring through the FR-051 precedence | Yes | **Pass** |
| Package attribution (FR-026, FR-040) | `test_types_routes.py:352`, `:368`, `:383`, `:399`, `:440`; `typeModel.test.ts:71`, `:76`, `:82`, `:119`, `:130` | one distribution named identically on both tabs through real discovery; two distributions kept apart; unnamed → `null` and still listed; ambiguous root → `null`; one section per package A→Z | Yes | **Pass** |
| Type popover contents (FR-042, FR-043) | `TypePalette.test.tsx:163` ×7; `typeModel.test.ts:224` ×3 | name, description, parent with core base when it differs, no redundant `Array (Array)`, extensions split, no-formats copy, origin label | Yes | **Pass** |
| Popover (FR-044, FR-045) | `BlockPalette.test.tsx:313` ×5; `useHoverPopover.test.tsx` ×12; `TypePalette.test.tsx:215` | `pointer-events-none` gone; survives the tile→popover gap; closes when the pointer reaches neither; **dragging still works** and the card gets out of the way | Yes — `:374` is the FR-045 test the spec explicitly requires | **Pass** |
| One popover (FR-046) | read, not asserted by a dedicated test | `BlockDetailPopover` and `TypeDetailPopover` both compose `palette/DetailPopover`; no second implementation exists | Structurally true; no test would fail if a second were added | **Pass (structural)** |
| Shared helpers (FR-047, §10.1/§10.2) | `sections.test.ts` ×12 | `buildSections<T>`/`filterItems<T>` carry no block or type knowledge — every surface fact arrives as a callback | Yes for the generic behaviour. §10.2 verified by grep: `derivePackage`, `isIoSource`/`isIoSink`/`isDataIoBlock`, `CATEGORY_KEYS`, `portSignature` appear **only** on the block side | **Pass** |
| New-file flows (FR-029 – FR-033) | `newDropinFile.test.tsx` ×8 | destination asked first and names both real directories; each choice routes probe **and** write; refuses an existing file at the chosen destination; type template lands a `DataObject` skeleton in either destination; **both kinds run the same prompt/probe/write/open sequence and share one validator** | Yes — `:219` compares the recorded call sequences of the two flows | **Pass** |
| Types API independence (FR-027) | `test_the_data_types_tab_needs_no_block_request`, `test_the_listing_is_served_by_its_own_router`; `TypePalette.test.tsx:235` | own router; the tab fetches the catalogue itself and takes no blocks prop | Yes | **Pass** |
| Type template (FR-028) | `test_types_routes.py:493`, `:501`, `:509`, `:531`, `:538` | same three-field shape as the block template; content is a valid data-type module; **colour attributes present as commented-out lines and not assigned** | Yes — `:528` asserts `ui_ring_color` is not among the *assigned* names, which is the precise obligation | **Pass** |
| Cross-process refresh (FR-065) | `test_a_block_promoted_through_the_agent_appears_in_the_palette`; `test_mcp_tools_library.py:244`, `:259`, `:266`, `:277`, `:287` | the bridge sees another process's write, sees a deletion, and does **not** rescan when nothing moved | Yes | **Pass** |

**No row in Track B's scope is unimplemented or untested.** Two rows carry a
caveat (FR-011 → P2-2; FR-003 structural → P3-6), one is structural-only
(FR-046), and two skip locally for want of symlink privilege.

## 5. Governance

### 5.1 Protected core

The audit prompt asked me to confirm the protected-core diff is confined to
`src/scistudio/core/types/base.py`. **It is not** — and that is correct rather
than a violation, because `PROTECTED_CORE_PATTERNS` covers
`src/scistudio/{core,engine,blocks,workflow,utils}/**`, which spec §12.1's
FR-053 wording predates. Track B's protected-path diff is:

| Path | Change | Declared where |
|---|---|---|
| `src/scistudio/core/types/base.py` | +22, **zero deletions** — two `ClassVar[str \| None] = None` and their docstrings, no behavioural code touched | spec §12.1, checklist §2 and §6 (B2) |
| `src/scistudio/core/types/registry.py` | `TypeSpec` gains 5 fields; `_spec_for_class` replaces three inline construction sites; `package_root` recorded | spec §12.1, checklist §6 (B2) |
| `src/scistudio/core/types/_templates/` | new package (`__init__.py` + `type_base_template.py`), mirroring `scistudio/blocks/_templates/` | **B2's gate ledger `declared_scope.include`** — but **not** checklist §2 or §6 |
| `src/scistudio/blocks/io/_config_enrichment.py` | +24, one new pure function `format_extensions_by_type` | checklist §6 (B2) |

I verified the `base.py` claim myself: the diff is purely additive, two
attributes defaulting to `None`, no deletion anywhere in the file. FR-049 and
FR-053 are satisfied and the change is as minimal as the requirement allows.

`admin-approved:core-change` is authorized for PR B by the owner (checklist
§1.2, §5) and must be present on the PR; CI verifies actor provenance. Not
verifiable pre-PR from this worktree.

One check I want to record because it would have been a silent product defect:
`_templates/type_base_template.py` defines a real `MyDataType(Array)` subclass
inside an importable package under `src/scistudio/core/types/`. It is **not**
picked up by discovery — `TypeRegistry.scan_builtins` registers an explicit
seven-class list (`registry.py:568`) rather than walking the package — so the
template class cannot appear in the Data types tab as a core type. Verified.

### 5.2 Scope drift

| Item | Verdict |
|---|---|
| B5 edited `components/nodes/BlockNode.tsx` and `BlockNode.parts/NodeActionToolbar.tsx` (the manager's prompt listed `components/nodes/**` out of scope) | **Accept.** E2 has no other home, and the edit is the minimum shape: `NodeActionToolbar` gains one additive optional `trailing?: ReactNode` rendered after Delete, with no behaviour change for a caller that omits it; `BlockNode` passes `<PromoteToLibraryAction>` guarded by `summary ? … : null`. Crucially it is a **node**, not an `onPromote` callback — a callback would have put a second copy of the FR-019 decision in `BlockNode`, which is exactly what FR-025 forbids. `test-utils.tsx` was updated alongside. Minimal and correct. |
| B5 edited `App.tsx`, `App.parts/AppDialogs.tsx`, `App.parts/ProjectWorkspace.tsx` | **Accept.** `AppDialogs` mounts `<UserLibraryDialogs />` once — one line, and it is what makes the collision prompt the canvas shows and the one the palette shows literally the same component. `ProjectWorkspace` adds the FR-039 tab, widens `LeftTab`, and adds the FR-020 tab-switch effect; the effect is 5 lines and lives where the state it sets lives. `App.tsx` widens the `leftTab` state type, threads `createNewDataType`, and factors three repeated `currentProject ? () => void run() : undefined` closures into one `whenProjectOpen` helper — behaviourally identical, verified line by line. All minimal. |
| B2 touched `src/scistudio/core/types/_templates/**` and `src/scistudio/api/app.py`, neither in checklist §6's B2 write set | **Accept on substance, record as checklist drift.** Both are declared in B2's gate ledger `declared_scope.include`, so the ledger discipline held; §9 has no entry. Same class as the A2/A3 entries the manager already logged. |
| B3's `frontend/src/types/api.ts` addition | Already recorded in §9. Confirmed: `BlockOrigin` and `BlockSummary.origin?` live there and `lib/api/blocks.ts` is untouched. |

### 5.3 Deferral drift

- **No new `TODO(` was added anywhere in the range.** `git diff … | grep '^+.*TODO('` returns nothing. Every TODO in the tree cites a pre-existing issue.
- **B3's `TODO(#2025)` is gone**, as §9 required AUDIT-B to confirm. `ProjectWorkspace.tsx` now renders `<TypePalette />`.
- **The tips strip (#1997) was not built.** No match for `tips`, `tipsStrip`, or `#1997` anywhere in `frontend/src/` or `docs/specs/frontend-block-palette.md`.
- **Cascade was not reduced to warn-only.** Spec §15 records "Cascade promotion is required rather than warn-only" as an owner assumption, and the implementation honours it: `promoteToUserLibrary` actually *writes* each included dependency into `~/.scistudio/types/` before writing the item (`promoteToUserLibrary.ts:281-299`), with the ordering deliberately chosen so a mid-flight cancel leaves the library without the item rather than with an item whose types are missing. Warning is the **decline** branch only (FR-023), plus the FR-024 second-level report. `promoteToUserLibrary.test.ts:212` asserts the dependency write happens; `:235` asserts the decline path still promotes and warns.

### 5.4 Test-change requirement

Every implementation change in the range added or modified tests. Backend:
`test_block_origin_tiers.py` (+308), `test_user_library_write.py` (+368),
`test_types_routes.py` (+542), `test_mcp_tools_library.py` (+303),
`test_type_colour.py` (+276), `test_types.py` (+58), plus consequential updates
to `test_mcp_fastmcp.py`, `test_mcp_bridge.py`,
`test_finish_ai_block_skeleton.py`, `test_runtime_import_contract.py`,
`test_phase2_mcp_end_to_end.py`. Frontend: 16 new or extended test files across
`promotion/`, `TypePalette.parts/`, `palette/`, `config/`, `store/`, `lib/`,
`App.parts/`. No source file in the range lacks a corresponding test change.

### 5.5 Ledger sanitization

I scanned all seven committed gate ledgers in the range for `C:\Users`,
`/home/<user>`, the owner's username, `AppData`, temp directories,
`site-packages`, `.venv`, and worktree names. **No match.** No raw transcripts;
events are structured records.

### 5.6 Docs

`docs/specs/adr-053-personal-tool-library.md` correctly promotes
`routes/types.py` and `TypePalette.tsx` from `planned_governs` to `governs` now
that both exist, extends FR-026 with the package-name obligation, and adds the
§11 package-attribution row. `docs/specs/frontend-block-palette.md` gains 309
lines for the renamed panel, tier sections, grouping change, interactive
popover, and the Data types tab. `CHANGELOG.md` carries 201 lines across the
six issues. Checklist §8.1's "Required docs" row is satisfied.

## 6. Checklist Drift (reported, not edited)

The checklist lives on the manager branch and is not present in this worktree,
and my dispatch instruction was to report drift rather than edit
`docs/planning/**`. §8.4's rows are therefore for the manager to tick; the
suggested content is at the end of this section.


1. **§8.3 B5 rows are still `[ ]`** (`B5 promotion action…`, `B5 cascade…`, `B5 New data type…`, `Docs: frontend-block-palette + CHANGELOG`) although B5 landed at `11871bef` / `327ae238` and both docs are updated.
2. **§9 is missing two accepted scope additions**: B2 → `src/scistudio/core/types/_templates/**` and `src/scistudio/api/app.py`; B5 → `components/nodes/**`, `App.tsx`, `App.parts/{AppDialogs,ProjectWorkspace}.tsx`. Both were declared in the agents' ledgers; §9 is where the manager records the acceptance.
3. **§2 "Protected paths" says only `base.py` requires the label.** As §5.1 above shows, four protected paths are touched. The wording should mirror the PR A drift-log entry that already corrected this for Track A.
4. **§8.3's B2 FR-066 row overstates the guard** — "with a test asserting it stays unpopulated so the rejected second colour supply point cannot be reintroduced". Per P2-1 the test cannot detect the reintroduction. Reword or fix the test.
5. **Track B is stacked on an older Track A tip.** `feat/1995-…` branches from `6a9eae24`; `fix/2020-…` is now `bcb85a1f`, three commits ahead (`2edeffaa` pre-PR gate evidence, `2667e0cb` PR provenance, `bcb85a1f` docstring reword). Not a defect — GitHub computes the PR diff from the merge base — but Track B should take those three before PR B opens so the stacked PR does not appear to revert them.

Three §9 items B3 asked AUDIT-B to confirm, all **confirmed sound**:

- *Empty states suppressed while a filter is active.* Correct product judgment and correctly implemented (`withoutEmptyHints`), tested both ways on both surfaces, and documented in the palette spec.
- *The `custom` fallback groups into `This Project`.* Correct, and the reasoning holds: `This Project` renders unconditionally, so an unresolvable drop-in can never vanish; filing it under `My Library` would assert cross-project reuse the backend never claimed. Same rule on both tabs (`paletteModel.ts:154`, `typeModel.ts:69`), tested on both.
- *`TODO(#2025)` gone by PR time.* Confirmed.

### 6.1 Suggested §8.4 rows

```
- [x] `AUDIT-B` assigned (`with-context`) -> commit <this commit>
- [x] Audit report path assigned: `docs/audit/2026-08-07-adr-053-spec1-track-b.md`
- [x] Audit report committed -> <this commit>
- [ ] Audit reports merged into PR B evidence path
- [x] Findings recorded. **Recommendation: pass-with-fixes.** 0 P1, 2 P2, 6 P3.
- [x] P1 findings fixed before integration -> `N/A — no P1 findings`
- [ ] P2/P3 findings fixed or tracked with owner-approved rationale
```

## 7. Recommendation

**pass-with-fixes.**

Nothing here blocks merge on correctness. The write path is careful — the
constraint is genuinely inverted rather than relaxed, containment is decided on
`realpath` + `commonpath` with a direct-parent check on top, the project
endpoint is untouched and tested to still refuse escapes, and the collision
path cannot reach `overwrite: true` without a user answer. The palette work
changed the grouping *dimension* as §14 predicted rather than bolting sections
on, and the empty states ADR-053 §3 calls load-bearing are there, tested, and
correctly suppressed under a filter. The FR-051 blast-radius bound holds
verifiably. FR-067 is solved by not having a loading state at all, which is the
right answer, and its test is not vacuous.

Before PR B is opened I would fix **P2-1** (a guard that cannot fail is worse
than no guard, because checklist §8.3 now cites it as evidence) and at minimum
option (a) of **P2-2** (stop claiming refusal-for-refusal in a docstring, a
CHANGELOG entry, and a checklist row while a refusal is missing). Option (c) —
moving the containment predicate into `scistudio.core.dropins` so the AI layer
and the API share one implementation — is the structurally right fix and is
small; it is what FR-003 asks for and what the import-linter contract currently
prevents.

The P3s are follow-up material. None needs to land in this PR.
