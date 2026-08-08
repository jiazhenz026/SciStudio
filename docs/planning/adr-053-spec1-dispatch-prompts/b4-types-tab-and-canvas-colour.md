[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Deliver ADR-053 Spec 1 in full as two reviewable PRs; this slice is spec §12.2 steps 12 and 13 — the canvas colour source switch and the Data types tab.
- Task kind: feature
- Persona: implementer
- Issues: #2025 (tab half) and #2024 (frontend half)
- Issue URLs: https://github.com/jiazhenz026/SciStudio/issues/2025 , https://github.com/jiazhenz026/SciStudio/issues/2024
- Umbrella PR: #2029 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-053-spec1-personal-tool-library
- Tracking branch (your merge target): feat/1995-adr-053-personal-tool-library
- Agent branch: feat/2025-data-types-tab-and-canvas-colour
- Agent worktree: C:/Users/jiazh/workspace/SciStudio-wt-b4
- Gate record: create with `gate_record init --slug 2025-data-types-tab-and-canvas-colour`
- Checklist: docs/planning/adr-053-spec1-personal-tool-library-checklist.md (§8.3 rows B4)

Track A, B1, B2, and B3 have already landed on your base branch. The types listing endpoint
exists (B2). The shared palette helpers and the interactive popover exist (B3). **Reuse
them; do not reimplement.** The manager's integration notes give you B2's response model
and B3's helper signatures — read them from those agents' committed work if the notes are
incomplete.

## Required Rules

Read and follow:

- The GitHub issues `#2025` and `#2024`.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/new-feature.md
- docs/ai-developer/personas/implementer.md
- docs/specs/adr-053-personal-tool-library.md — §2.7, §2.8, §2.12, §7.1 (FR-051, FR-052, FR-066, FR-067), §7.2, §9.2 (FR-039 – FR-043), §10.1, §14
- docs/specs/frontend-block-palette.md — B3 amended it; you amend the tab section
- docs/adr/ADR-053.md §3

## Scope

You own only:

- `frontend/src/components/TypePalette.tsx` (new)
- `frontend/src/config/typeColorMap.ts`
- `frontend/src/components/nodes/BlockNode.parts/PortHandles.tsx`
- `frontend/src/components/WorkflowCanvas.tsx` (type-colour resolution only)
- `frontend/src/lib/api/code.ts` (types listing and type template clients)
- `frontend/src/store/**` — a types slice, if you need one
- `frontend/src/App.tsx` and `frontend/src/App.parts/ProjectWorkspace.tsx` — the third tab only
- `frontend/src/components/__tests__/TypePalette.test.tsx` and colour tests
- `docs/specs/frontend-block-palette.md` — the Data types tab section only
- `CHANGELOG.md` (one entry)

You must not touch:

- `frontend/src/components/BlockPalette.tsx`, `BlockPalette.parts/**`, `BlockDetailPopover.tsx`, `frontend/src/components/palette/**` — B3 owns them; **consume** the shared helpers and the popover
- `frontend/src/App.parts/useProjectActions.ts`, `frontend/src/components/Toolbar.parts/**` — B5 owns them
- Any `src/scistudio/**` backend path
- `docs/ai-developer/**`

If you need an out-of-scope path, stop and report back. Do not edit it.

## Coordination

- B5 lands after you and will add the promotion action row to your type popover. Leave a
  clean attachment point, mirroring where B3 left one in the block popover.
- MUST work only on your assigned branch, in your assigned worktree.
- MUST NOT use `pip install -e .`.
- Do not revert or overwrite other agents' work.
- MUST NOT open a PR. Push your branch and report; the manager integrates.
- Edit only your own checklist rows (§8.3 rows beginning `B4`).

## TODO And Deferral Rule

Deferred work must be tracked with `TODO(#NNN): <reason>` citing an issue, ADR, spec, or
follow-up ticket. The owner directive is **complete delivery with no deferred scope** —
if something must be deferred, stop and report it as a blocker.

Known deferred items: N/A

## Work To Do

### Part 1 — the canvas colour source switch (do this first)

Spec §12.2 deliberately sequences this **before** the Data types tab, "so that the moment
either surface can show a declared colour, both read it from the same source and cannot
disagree."

1. **FR-066** — canvas port colour resolution consumes the **types listing response**
   rather than `BlockSchemaResponse.type_hierarchy`. Without this the two surfaces diverge:
   the palette would read declared colours from the endpoint while the canvas resolves from
   `type_hierarchy`, whose `TypeHierarchyEntry` carries no fill-colour field at all — so a
   type declaring `ui_color` would render in its declared colour in the palette and in a
   hash-derived colour on the canvas.

   `type_hierarchy` keeps serving type *hierarchy* (`base_type` lookups). It stops being a
   colour transport. Do NOT add `ui_color` to `TypeHierarchyEntry` — spec §7.1 rejects that
   explicitly as a second supply point.

2. **FR-051 — colour precedence**, applied identically to palette tiles and canvas ports so
   a type looks the same in both places:

   1. type-declared colour (from the types endpoint),
   2. the existing `typeColorMap` entry,
   3. the `hashTypeName` fallback.

   A declared colour wins; an **undeclared type must behave exactly as it does today**.
   That is testable: snapshot the current resolution for a set of core and unknown types and
   assert it is unchanged.

3. **FR-052** — an invalid colour value is ignored with a warning and falls through to the
   next precedence level. A malformed hex string in a user's type file MUST NOT break the
   palette or the canvas. B2 validates server-side; be defensive client-side too.

4. **FR-067 — the loading window is the risk in this slice.** Colour and block data arrive
   in one response today and therefore always arrive together; routing colour through a
   separate endpoint introduces a window where ports exist and colours do not. Ports MUST
   fall back to the existing resolution during that window and MUST NOT flash or re-layout
   when the data lands.

   Spec §14: "a wrong fallback shows every port in the wrong colour for a moment on every
   canvas open, which is far more visible than the drift it prevents." Test the loading
   window explicitly — render before the types response resolves, then after, and assert
   no flash and no re-layout.

### Part 2 — the Data types tab

5. **FR-039** — a third tab, `Data types`, between `Blocks` and `Project`. `leftTab` widens
   from `"blocks" | "project"` to include `"types"`. The user-facing label is `Data types`
   (`Types` is too abstract standing alone next to `Blocks`); the internal key stays `types`.

6. **FR-040** — the tab mirrors the Blocks tab: search input, filter chips, and tier
   sections with core pinned at the top, then `My Library`, then `This Project`, then
   packages A→Z. Empty-state behaviour follows FR-037 — the two tier sections render even
   when empty and teach the concept in one line.

   Build this on **B3's shared helpers** (`filterItems`, `buildSections<T>`, `Section<T>`,
   the tile component, the filter chips, the hover positioning). FR-047 requires
   `buildSections<T>` to fit both surfaces without per-surface special-casing — if you find
   yourself special-casing, that is a contract failure to report, not to work around.

7. **FR-041** — each type tile carries a colour swatch, **solid fill plus ring**, resolved
   through the FR-051 precedence so a type reads identically in the palette and on a canvas
   port. No new colour table is introduced. `resolveTypeColor()` (solid fill) and
   `resolveRingColor()` (ring) already exist in `frontend/src/config/typeColorMap.ts` and
   the solid-plus-ring treatment is already implemented for canvas port handles — reuse it.

8. **FR-042** — each type gets a hover popover, using **B3's popover component** (FR-046),
   carrying:

   | Row | Content |
   |---|---|
   | Name | the registered type name |
   | Parent | the immediate base class, and the core base type when it differs |
   | Description | the type's docstring-derived description |
   | Extensions | loadable-from and saveable-to, **reported separately** (FR-055), or an explicit "no file formats registered" (FR-056) |
   | Origin | which tier the type came from (FR-005) |
   | Action | Promote to My Library — **B5 adds this row; leave the attachment point** |

9. **FR-043** — the parent row shows the chain position rather than only the immediate
   parent when the two differ. `resolveCoreBaseType`
   (`frontend/src/config/typeColorMap.ts:179`) already returns the highest ancestor below
   `DataObject` and returns `null` when the type is itself a core base, so no redundant
   `Array (Array)` is rendered. Use it rather than writing a second traversal.

10. **Tests** — `frontend/src/components/__tests__/TypePalette.test.tsx` and colour tests
    covering: the tab structure mirrors blocks and the label is `Data types` (FR-039,
    FR-040); tile colour follows the FR-051 precedence (FR-041); popover contents including
    the parent chain when it differs and the explicit no-formats row (FR-042, FR-043,
    FR-056); declared colour beats `typeColorMap` beats hash, and an undeclared type is
    unchanged from today (FR-051); a type declaring `ui_color` renders in that colour on
    **both** a palette tile and a canvas port (FR-066); ports render with the fallback
    before type data arrives and do not flash or re-layout when it lands (FR-067); a
    malformed hex warns and falls through without breaking either surface (FR-052).

11. **Docs** — amend `docs/specs/frontend-block-palette.md` for the Data types tab. B3
    already amended §4 for the renamed tab, tier sections, grouping change, and the
    interactive popover — do not restate those.

12. Update `CHANGELOG.md` with one entry.

## Required Tests And Checks

- `cd frontend && npm run test`
- `cd frontend && npx tsc --noEmit`
- `cd frontend && npm run lint` and the prettier/format check the repo uses
- `cd frontend && npm run build`
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr --base feat/1995-adr-053-personal-tool-library --head HEAD`
- `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#2025"`
- Do NOT run `scripts/scistudio_pr_create.py`; you are not opening a PR.

Record `docs/specs/frontend-block-palette.md` and `CHANGELOG.md` as docs updates and
`docs/ai-developer/**` as N/A.

## Output Required

- Changed file paths.
- How the types listing data is fetched and cached, and the exact loading-window behaviour
  you implemented for FR-067.
- Where B5 should attach the promotion action row in the type popover.
- Confirmation that you consumed B3's shared helpers and popover, naming each.
- Evidence that an undeclared type's colour is byte-identical to today (FR-051).
- Tests/checks run and results.
- Checklist rows updated.
- Commit SHA and branch name.
- Any blocker or scope issue.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file.
- B3's `buildSections<T>` needs per-surface special-casing to serve types (FR-047 contract failure).
- B2's types endpoint does not carry a field FR-042 requires.
- The FR-067 loading window cannot be made flash-free without changing how block data is fetched.
- CI or local checks fail for unclear reasons.
- You cannot add/update required tests.
