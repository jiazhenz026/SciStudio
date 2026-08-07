[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Deliver ADR-053 Spec 1 in full as two reviewable PRs; this slice is spec §12.2 steps 6, 7, and 8 — declared type colour, per-type extensions, and the types API.
- Task kind: feature
- Persona: implementer
- Issues: #2023 and #2024 (backend half)
- Issue URLs: https://github.com/jiazhenz026/SciStudio/issues/2023 , https://github.com/jiazhenz026/SciStudio/issues/2024
- Umbrella PR: #2029 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-053-spec1-personal-tool-library
- Tracking branch (your merge target): feat/1995-adr-053-personal-tool-library
- Agent branch: feat/2023-type-colour-and-types-api
- Agent worktree: C:/Users/jiazh/workspace/SciStudio-wt-b2
- Gate record: create with `gate_record init --slug 2023-type-colour-and-types-api`
- Checklist: docs/planning/adr-053-spec1-personal-tool-library-checklist.md (§8.3 rows B2)

Track A and agent B1 have already landed on your base branch. `src/scistudio/core/dropins.py`
(the shared drop-in provisioning helper) and the shared origin resolver both exist. Consume
them.

## PROTECTED CORE PATH — READ THIS FIRST

`src/scistudio/core/types/base.py` is a protected core path. FR-053 requires the
implementing PR to carry `admin-approved:core-change`, verified in CI.

**The owner has authorized this label** (checklist §1.2) and will apply it to PR B himself.
You do not apply labels and you do not open the PR. Record the label in your gate ledger
with `--admin-label admin-approved:core-change` so the local evaluator knows the
authorization exists.

`admin-approved:core-change` authorizes the protected path only. It does not bypass scope,
issue linkage, docs, tests, or check obligations.

Keep the core change minimal and additive: two optional class attributes defaulting to
`None`. Spec §14 accepts this precisely because the precedence rule (FR-051) keeps every
existing type's appearance byte-identical.

## Required Rules

Read and follow:

- The GitHub issues `#2023` and `#2024`.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/new-feature.md
- docs/ai-developer/personas/implementer.md
- docs/specs/adr-053-personal-tool-library.md — §2.7, §2.8, §2.9, §7 (FR-026 – FR-028), §7.1 (FR-049 – FR-053, FR-066), §7.2 (FR-054 – FR-056), §14
- docs/adr/ADR-053.md §3

## Scope

You own only:

- `src/scistudio/core/types/base.py` — **protected core**, two optional colour attributes only
- `src/scistudio/core/types/registry.py`
- `src/scistudio/api/routes/types.py` (new)
- `src/scistudio/api/schemas.py` (type-listing models only)
- `src/scistudio/api/__init__.py` or wherever routers are registered
- `src/scistudio/blocks/io/_config_enrichment.py` or a sibling helper, for extension derivation
- `tests/api/test_types_routes.py` (new)
- `tests/core/test_type_colour.py` (new)
- `CHANGELOG.md` (one entry)

You must not touch:

- `src/scistudio/core/dropins.py` — A1 owns it; consume it
- `src/scistudio/api/_block_source.py`, `routes/blocks.py`, `routes/user_library.py` — B1 owns them; consume the shared origin resolver
- `src/scistudio/blocks/registry/**`
- Any `frontend/**` path — B4 consumes your endpoint
- `docs/ai-developer/**`

If you need an out-of-scope path, stop and report back. Do not edit it.

## Coordination

- MUST work only on your assigned branch, in your assigned worktree.
- MUST NOT use `pip install -e .`. Use `PYTHONPATH=./src`.
- Do not revert or overwrite other agents' work.
- MUST NOT open a PR. Push your branch and report; the manager integrates.
- Edit only your own checklist rows (§8.3 rows beginning `B2`).

## TODO And Deferral Rule

Deferred work must be tracked with `TODO(#NNN): <reason>` citing an issue, ADR, spec, or
follow-up ticket. The owner directive is **complete delivery with no deferred scope** —
if something must be deferred, stop and report it as a blocker.

Known deferred items: N/A

## Frozen Contracts (manager-set)

**Type origin vocabulary** (FR-005): `core` | `user` | `project` | `package` | `custom`.
`custom` is the unresolvable-path fallback only.

**Shared origin resolver** (FR-003): B1 created it. You MUST consume it. Writing a second
path comparison for types is a protocol violation — FR-003 exists specifically to prevent
two resolvers that can diverge. B1's report gives you the module path and signature; if it
does not fit types, stop and report rather than forking it.

**User library roots**: obtained from `src/scistudio/core/dropins.py`. Never hardcode
`Path.home() / ".scistudio"`.

## Work To Do

1. **FR-049** — `DataObject` gains optional class attributes letting a type declare its own
   appearance: a fill colour and a ring colour, both CSS hex strings, both defaulting to
   `None`. Naming mirrors the block precedent (#1839): `ui_color`, `ui_ring_color`.

2. **FR-050** — `TypeRegistry` collects the declared colours onto the type spec, and the
   types listing endpoint surfaces them. That endpoint is the **single source of type
   colour for the whole product**.

3. **FR-052** — an invalid colour value is ignored with a warning and falls through to the
   next precedence level. A malformed hex string in a user's type file MUST NOT break the
   palette or the canvas. Validate at collection time, not at render time.

4. **Do NOT revive `TypeHierarchyEntry.ui_ring_color`.** Spec §7.1 (FR-066) rejects it
   explicitly: it would create a second supply point for type colour that has to be kept in
   step by hand. `type_hierarchy` keeps serving type *hierarchy* (`base_type` lookups) and
   stops being a colour transport. Leave the dead field dead.

5. **FR-054 – FR-056** — the types listing endpoint reports, per type, the file extensions
   it can be **loaded from** and **saved to**, derived from registered `FormatCapability`
   records (`src/scistudio/blocks/io/capabilities.py:267`) grouped by `data_type`.
   `io_capable_type_names` (`src/scistudio/blocks/io/_config_enrichment.py:28`) already
   groups by `capability.data_type.__name__`; reuse that machinery rather than re-walking
   the registry.

   Load and save MUST be reported **separately** — a type readable from a format it cannot
   be written back to is a real and useful asymmetry. A type with no format capability
   reports **empty lists**, not an omitted field: B4 renders that as an explicit
   "no file formats registered", because absence of IO support is information.

6. **FR-026** — a types listing endpoint under a new `src/scistudio/api/routes/types.py`,
   returning per registered type: name, base type, description, origin tier (FR-005),
   `file_path` when resolvable, the declared colours, and the supported extensions.

7. **FR-027** — the endpoint is independent of the block list response. The Data types tab
   MUST NOT depend on a blocks request to populate or refresh. `type_hierarchy` on the
   block response is unchanged and keeps serving port colour resolution until B4 lands
   FR-066.

8. **FR-028** — a type template endpoint on the same router, mirroring
   `GET /api/blocks/template` (`src/scistudio/api/routes/blocks.py:340`), returning a
   minimal `DataObject` subclass skeleton with the same response shape
   (`{kind, content, suggested_filename}`). The skeleton MUST include the colour attributes
   as **commented-out optional lines**, so a user authoring a type discovers that declaring
   a colour is possible.

9. **Tests**:
   - `tests/core/test_type_colour.py` — a type declaring a colour surfaces it on the spec
     (FR-049, FR-050); an invalid colour warns and falls through without raising (FR-052);
     an undeclared type is unchanged.
   - `tests/api/test_types_routes.py` — listing carries name, base type, description,
     origin tier, `file_path`, colours, and separately-reported load/save extensions;
     a type with no capability reports empty lists; the endpoint works without a blocks
     request (FR-027); the template endpoint returns the right shape and contains the
     commented colour lines (FR-028); origin resolution for a user-tier and a project-tier
     type, plus the `custom` fallback (FR-005).

10. Update `CHANGELOG.md` with one entry.

## Required Tests And Checks

- `PYTHONPATH=./src python -m pytest tests/core/test_type_colour.py tests/api/test_types_routes.py -q`
- `PYTHONPATH=./src python -m pytest tests/core tests/api tests/blocks -q` (core change regression sweep)
- import-linter must still pass — `scistudio.core` MUST NOT gain a dependency on `scistudio.blocks`. Extension derivation reads `FormatCapability`, which lives under `scistudio.blocks.io`; that logic therefore belongs on the API side or the blocks side, **not** inside `core/types/registry.py`.
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr --base feat/1995-adr-053-personal-tool-library --head HEAD --admin-label admin-approved:core-change`
- `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#2023"`
- Do NOT run `scripts/scistudio_pr_create.py`; you are not opening a PR.

No wrapper, hook, gate-record, CI, or AI-runtime governance behavior changes, so
`docs/ai-developer/**` needs no update; record that N/A rationale and record `CHANGELOG.md`
as the docs update.

## Output Required

- Changed file paths, with `src/scistudio/core/types/base.py` called out explicitly and
  its diff quoted in full, so the manager can hand the owner the exact protected-core change.
- The types listing endpoint's method, path, and response model field-by-field — B4 codes
  the frontend against this and must not guess.
- The type template endpoint's shape.
- The declared-colour attribute names and their validation behaviour.
- Confirmation that you consumed B1's shared origin resolver, naming it.
- Tests/checks run and results.
- Checklist rows updated.
- Commit SHA and branch name.
- Any blocker or scope issue.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file.
- B1's shared origin resolver cannot resolve a type spec without forking it.
- Extension derivation cannot be placed without an import-linter violation.
- The protected-core guard blocks you even with `--admin-label admin-approved:core-change`.
- CI or local checks fail for unclear reasons.
- You cannot add/update required tests.
