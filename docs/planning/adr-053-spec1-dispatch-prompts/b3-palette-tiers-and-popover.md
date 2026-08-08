[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Deliver ADR-053 Spec 1 in full as two reviewable PRs; this slice is spec §12.2 steps 9, 10, and 11 — the palette's grouping change, tier sections, and the interactive popover.
- Task kind: feature
- Persona: implementer
- Issues: #1995 (frontend half) and #2025 (popover half)
- Issue URLs: https://github.com/jiazhenz026/SciStudio/issues/1995 , https://github.com/jiazhenz026/SciStudio/issues/2025
- Umbrella PR: #2029 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-053-spec1-personal-tool-library
- Tracking branch (your merge target): feat/1995-adr-053-personal-tool-library
- Agent branch: feat/1995-palette-tiers-and-popover
- Agent worktree: C:/Users/jiazh/workspace/SciStudio-wt-b3
- Gate record: create with `gate_record init --slug 1995-palette-tiers-and-popover`
- Checklist: docs/planning/adr-053-spec1-personal-tool-library-checklist.md (§8.3 rows B3)

## Required Rules

Read and follow:

- The GitHub issues `#1995` and `#2025`.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/new-feature.md
- docs/ai-developer/personas/implementer.md
- docs/specs/adr-053-personal-tool-library.md — §2.2, §2.10, §2.12, §9.1 (FR-034 – FR-038), §9.3 (FR-044 – FR-046), §10.1 (FR-047), §10.2, §14
- docs/specs/frontend-block-palette.md — you amend it
- docs/adr/ADR-053.md §3

## Scope

You own only:

- `frontend/src/components/BlockPalette.tsx`
- `frontend/src/components/BlockPalette.parts/**` (including `paletteModel.ts` and its tests)
- `frontend/src/components/BlockDetailPopover.tsx`
- `frontend/src/components/palette/**` (new — the shared helpers you extract)
- `frontend/src/App.tsx` (the `leftTab` type and first-tab label only)
- `frontend/src/App.parts/ProjectWorkspace.tsx` (the first-tab label only)
- `frontend/src/lib/api/` block-listing types (the `origin` field only)
- `docs/specs/frontend-block-palette.md` — §4 Sections And Ordering, the grouping change, and the popover
- `CHANGELOG.md` (one entry)

You must not touch:

- `frontend/src/components/TypePalette.tsx` — B4 creates it
- `frontend/src/config/typeColorMap.ts` — B4 owns it
- `frontend/src/components/nodes/**`, `frontend/src/components/WorkflowCanvas.tsx` — B4 owns them
- `frontend/src/App.parts/useProjectActions.ts`, `frontend/src/components/Toolbar.parts/**` — B5 owns them
- Any `src/scistudio/**` backend path
- `docs/ai-developer/**`

**Third-tab warning.** B4 adds the `Data types` tab to `App.tsx` and `ProjectWorkspace.tsx`
after you. You widen `leftTab` and rename the first tab; you do NOT add the types tab.
Leave the `leftTab` union easy to widen.

If you need an out-of-scope path, stop and report back. Do not edit it.

## Coordination

- You are not alone. B1 lands the backend `origin` field in parallel; B4 then B5 build on
  your shared helpers and your popover.
- MUST work only on your assigned branch, in your assigned worktree.
- MUST NOT use `pip install -e .`.
- Do not revert or overwrite other agents' work.
- MUST NOT open a PR. Push your branch and report; the manager integrates.
- Edit only your own checklist rows (§8.3 rows beginning `B3`).

## TODO And Deferral Rule

Deferred work must be tracked with `TODO(#NNN): <reason>` citing an issue, ADR, spec, or
follow-up ticket. The owner directive is **complete delivery with no deferred scope** —
if something must be deferred, stop and report it as a blocker.

Known deferred items: N/A. In particular the palette **tips strip (#1997) is out of scope**
— spec §1 moves it to the Learning Center spec. Do not build it.

## Frozen Contracts (manager-set)

**Block origin vocabulary** (delivered by B1):
`builtin` | `user` | `project` | `package` | `custom`.
`custom` is the unresolvable-path fallback only, and MUST still render somewhere sensible
rather than disappearing — treat it as project-tier-adjacent and say what you chose.

**Type origin vocabulary** (B4 will use it, your shared helpers must accommodate it):
`core` | `user` | `project` | `package` | `custom`.

## Work To Do

1. **FR-038 — this is a grouping-dimension change, not a section split.**
   `buildPaletteSections` currently groups by package via `derivePackage`. It MUST group by
   **origin tier first and package second**. Spec §9.1 states explicitly that this is larger
   than the "split one section in two" framing in #1995, and §14 records that every existing
   palette ordering test is therefore in scope. Expect to rewrite tests, not just add them.

2. **FR-035** — the single `Custom` section separates into `My Library` (user tier) and
   `This Project` (project tier).

3. **FR-036** — section order MUST be: `Data I/O` (pinned) -> `Built-in` -> `My Library` ->
   `This Project` -> plugin packages A→Z. The user tier is ordered above the project tier
   because it is the container the product is asking users to invest in; ordering it last
   would state the opposite.

4. **FR-037 — the empty states are load-bearing, not polish.** `My Library` and
   `This Project` MUST render when empty, each carrying one line stating what the section is
   for. Spec §9.1 and ADR-053 §3 both call this the cheapest discovery surface in the entire
   feature: it is the only moment a user who has never heard of a personal library is
   guaranteed to be looking at the place it would live. Other sections keep their current
   omit-when-empty behaviour.

   Issue #1995 suggests the copy: *"My Library — No blocks of your own yet. Save a block
   here and every project can use it."* Match that register.

5. **FR-034** — rename the left panel's first tab to `Blocks`.

6. **§10.1 shared helpers (FR-047)** — extract, so the Data types surface B4 builds cannot
   drift from this one:

   | Concern | Shape |
   |---|---|
   | Search filtering | `filterItems<T>(items, search, toHaystack)` — generalised from `filterBlocks` / `matchesSearch` |
   | Section building | `buildSections<T>(items, groupOf, pinnedOrder)` — the Map-group → ordered-take → remainder-A→Z skeleton |
   | Section model | `Section<T>`, generalised from `PaletteSection` |
   | Tile | one tile component: colour swatch, label, hover trigger, drag hook |
   | Popover | one popover (FR-046) |
   | Filter chips | generalised from `CategoryChips` |
   | Hover positioning | anchor computation, `POPOVER_GAP`, `POPOVER_MAX_HEIGHT`, open delay |

   **FR-047 is a hard constraint**: after the grouping change both surfaces group primarily
   by origin tier, so `buildSections<T>` MUST fit both **without per-surface special-casing**.
   If it cannot, the grouping contract is wrong and MUST be revised rather than special-cased
   — stop and report if you hit that.

   **§10.2 — do NOT generalise these.** `derivePackage`, `isIoSource` / `isIoSink` /
   `isDataIoBlock`, `CATEGORY_KEYS` (`io`/`process`/`code`/`app`/`ai`), and `portSignature`
   are block concepts and MUST stay on the block side.

7. **FR-044 — the popover becomes interactive.** `BlockDetailPopover` is rendered with
   `pointer-events-none` (`frontend/src/components/BlockDetailPopover.tsx:35`) and its
   visibility is driven entirely by the tile (`handleTileEnter` opens after
   `POPOVER_OPEN_DELAY_MS`, `clearHover` closes). Remove `pointer-events-none`; the popover
   maintains its own hover state so it stays open while the pointer is inside it; and the
   `POPOVER_GAP` between tile and popover MUST NOT close it in transit.

   You are making it *capable* of holding a button. B5 adds the actual promotion action row
   later — leave a clean place for it and say where in your report.

8. **FR-045** — tile dragging MUST keep working unchanged. `handleDragStart` and the
   popover's new interactivity MUST NOT interfere. Spec §11 requires this to be covered by
   a test; write it.

9. **FR-046** — one popover implementation serves both blocks and types. Yours is the one;
   B4 reuses it for the Data types tab.

10. **Tests** — extend
    `frontend/src/components/BlockPalette.parts/__tests__/paletteModel.test.ts` for the
    user/project split, the full section order, origin-first grouping, and both empty states.
    Add popover tests for interactivity, the tile→popover gap, and drag-unaffected.
    Category-chip filtering and text search must behave for the new sections exactly as for
    existing ones — test that too.

11. **Docs** — amend `docs/specs/frontend-block-palette.md`: §4 Sections And Ordering for
    the renamed tab, the two tier sections, and the new order; the grouping-dimension change;
    and the interactive popover. Do NOT document the Data types tab — B4 amends the same file
    for that after you, and duplicating it will conflict.

12. Update `CHANGELOG.md` with one entry.

## Required Tests And Checks

- `cd frontend && npm run test` (vitest) — or the repository's frontend test command
- `cd frontend && npx tsc --noEmit`
- `cd frontend && npm run lint` and the prettier/format check the repo uses
- `cd frontend && npm run build`
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr --base feat/1995-adr-053-personal-tool-library --head HEAD`
- `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#1995"`
- Do NOT run `scripts/scistudio_pr_create.py`; you are not opening a PR.

No wrapper, hook, gate-record, CI, or AI-runtime governance behavior changes, so
`docs/ai-developer/**` needs no update; record that N/A rationale. Record
`docs/specs/frontend-block-palette.md` and `CHANGELOG.md` as docs updates.

## Output Required

- Changed file paths.
- The shared helper module path and the exact exported signatures of `filterItems`,
  `buildSections`, `Section<T>`, the tile component, the popover component, and the filter
  chips — the manager freezes these and hands them to B4, who must reuse rather than
  reimplement.
- Where B5 should attach the promotion action row inside the popover.
- What you did with the `custom` fallback origin in the section model.
- Tests/checks run and results, including the count of pre-existing palette tests you had
  to rewrite for the grouping change.
- Checklist rows updated.
- Commit SHA and branch name.
- Any blocker or scope issue.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file.
- `buildSections<T>` cannot serve both surfaces without per-surface special-casing (FR-047).
- The backend `origin` field is not present on the block list response on your base branch —
  B1 delivers it; if it is missing, report rather than inventing a client-side path comparison.
- Making the popover interactive breaks tile dragging in a way you cannot resolve.
- CI or local checks fail for unclear reasons.
- You cannot add/update required tests.
