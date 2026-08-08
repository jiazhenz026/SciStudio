[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Deliver ADR-053 Spec 1 in full as two reviewable PRs; this slice is spec §12.2 steps 14, 15, and 16 — the promotion action, cascade promotion, and the new-file flows. It is the action the whole feature exists to provide.
- Task kind: feature
- Persona: implementer
- Issues: #1996 (frontend half) and #2026
- Issue URLs: https://github.com/jiazhenz026/SciStudio/issues/1996 , https://github.com/jiazhenz026/SciStudio/issues/2026
- Umbrella PR: #2029 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-053-spec1-personal-tool-library
- Tracking branch (your merge target): feat/1995-adr-053-personal-tool-library
- Agent branch: feat/1996-promotion-and-new-file-flows
- Agent worktree: C:/Users/jiazh/workspace/SciStudio-wt-b5
- Gate record: create with `gate_record init --slug 1996-promotion-and-new-file-flows`
- Checklist: docs/planning/adr-053-spec1-personal-tool-library-checklist.md (§8.3 rows B5)

Track A, B1, B2, B3, and B4 have all landed on your base branch. The user library write
endpoint and its existence probe exist (B1). The types listing endpoint exists (B2). The
interactive popover and shared palette helpers exist (B3). The Data types tab exists (B4).
B3 and B4 each left a clean attachment point for your promotion action row — use them.

## Required Rules

Read and follow:

- The GitHub issues `#1996` and `#2026`.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/new-feature.md
- docs/ai-developer/personas/implementer.md
- docs/specs/adr-053-personal-tool-library.md — §2.3, §2.11, §6 (FR-017 – FR-025), §6.1 (FR-021 – FR-024), §6.2, §8 (FR-029 – FR-033), §10.1, §14
- docs/adr/ADR-053.md §3

## Scope

You own only:

- `frontend/src/App.parts/useProjectActions.ts`
- `frontend/src/components/Toolbar.parts/FileOperationsGroup.tsx`
- `frontend/src/lib/api/userLibrary.ts` (new) and any client additions for the write/probe endpoints
- `frontend/src/components/promotion/**` (new — the one shared promotion action)
- The block source editor toolbar component (E1) and the canvas node context menu component (E2) — find them; they are existing components
- `frontend/src/components/BlockDetailPopover.tsx` — **the action row only**, at B3's attachment point
- `frontend/src/components/TypePalette.tsx` — **the action row only**, at B4's attachment point
- Tests for all of the above
- `CHANGELOG.md` (one entry)

You must not touch:

- `frontend/src/components/BlockPalette.parts/**`, `frontend/src/components/palette/**` — B3 owns them
- `frontend/src/config/typeColorMap.ts`, `frontend/src/components/nodes/**`, `WorkflowCanvas.tsx` — B4 owns them
- Any `src/scistudio/**` backend path — B1 built the write endpoint and the MCP tool
- `docs/ai-developer/**`

**Toolbar warning.** The parallel spec 2 manager is adding a "Bring in my work" toolbar
entry. You own `FileOperationsGroup.tsx` only. Do not restructure the toolbar.

If you need an out-of-scope path, stop and report back. Do not edit it.

## Coordination

- MUST work only on your assigned branch, in your assigned worktree.
- MUST NOT use `pip install -e .`.
- Do not revert or overwrite other agents' work — you are last in the Track B chain, so a
  careless edit here silently undoes four agents.
- MUST NOT open a PR. Push your branch and report; the manager integrates.
- Edit only your own checklist rows (§8.3 rows beginning `B5`).

## TODO And Deferral Rule

Deferred work must be tracked with `TODO(#NNN): <reason>` citing an issue, ADR, spec, or
follow-up ticket. The owner directive is **complete delivery with no deferred scope** —
if something must be deferred, stop and report it as a blocker.

Known deferred items: N/A. **Cascade promotion is required, not warn-only** — spec §15
records that as an explicit owner assumption. Do not reduce it to a warning.

## Work To Do

### Part 1 — the promotion action (#1996)

1. **FR-025 — one implementation.** Entry points E1, E2, E3, and E5 MUST share one
   implementation of the promotion action, including collision prompting and cascade.
   E3 is the agent's MCP tool, already built by B1 on the backend; your job is that E1, E2,
   and E5 all call one frontend action, and that its semantics match E3's.
   Spec §6.2: "Four copies of this logic is exactly the drift this spec is written to avoid."

   | # | Entry point | Where |
   |---|---|---|
   | E1 | Block source editor toolbar | beside the existing save / view-source affordances |
   | E2 | Canvas node context menu | the existing canvas menu |
   | E3 | Agent (MCP tool) | **already done by B1** — match its semantics |
   | E4 | New-file target choice | Part 2 below — creation-time, not promotion |
   | E5 | Palette hover popover button | B3's block popover and B4's type popover |

2. **FR-017 — promotion copies, never moves.** The originating project MUST keep working
   exactly as before.

3. **FR-018** — a name collision in the destination MUST prompt with **overwrite** and
   **save as new name** options. Silent overwrite is forbidden. B1's write endpoint reports
   the collision rather than overwriting (FR-008) and requires an explicit opt-in; drive the
   prompt from that, not from a client-side guess.

4. **FR-019 — the visibility condition is the resolved origin, not the tier.** Promotion is
   offered only for items whose resolved origin is **`project`**. Built-in and packaged
   items already live in a library; items already in the user library are already at the
   destination, and promoting one would copy a file onto itself and raise a meaningless
   overwrite prompt. In all three cases the action MUST be **hidden, not shown disabled**.

   Spec §6 is explicit that the broader "is it tier-1" test is wrong: a user-library block
   is also tier-1 with a resolvable `file_path`, so it would offer promotion for an item
   that is already promoted. Use the `origin` field B1 put on the block list response and
   B2 put on the types listing.

5. **FR-020** — on success, confirm inline **and reveal the item in its new section in the
   palette**. The action exists to teach that the container exists; a silent success wastes
   the teaching moment. This is the payoff for B3's `My Library` section — land the user
   looking at it.

6. **Cascade promotion (FR-021 – FR-024)**:

   - **FR-021** — before promoting a block, determine which project-level custom types that
     block depends on.
   - **FR-022** — dependency detection parses the block's imports **statically (AST)** and
     resolves each imported name against the type registry, classifying each resolved type
     by origin using the shared resolver. Static parsing is sufficient because after the
     Track A drop-in import fix (#2022) a block expresses a type dependency as a real
     import statement.
   - **FR-023** — when project-level type dependencies are found, offer promotion of those
     types alongside the block, **as a single confirmed action**. Declining MUST still allow
     the block to be promoted, with an explicit warning that it will fail to load in other
     projects.
   - **FR-024** — cascade is **one level deep** in this spec. A type that itself imports
     another project-level type is out of scope and MUST be **reported** rather than
     silently missed. Spec §14 accepts the one-level limit precisely because the residue is
     visible; do not let it become silent.

   Decide and report where the AST parse runs. If it needs a backend endpoint that B1 did
   not build, that is a blocker to report — do not add backend code yourself.

### Part 2 — the new-file flows (#2026)

7. **FR-029 — E4.** The new-file flow MUST ask **where the file goes**: the user library or
   the current project. Spec §8 calls this the cheapest possible moment to teach that the
   library exists, because the user is already deciding where their work lives.

8. **FR-030** — choosing the library routes to B1's user library write endpoint; choosing
   the project keeps the current `putProjectFile` behaviour.

9. **FR-031** — collision probing runs against **whichever destination was chosen**.
   `probeProjectFileExistence` covers only the project today; B1 built the user library
   counterpart — use it.

10. **FR-032 — a New data type toolbar action**, mirroring `createNewCustomBlock`
    (`frontend/src/App.parts/useProjectActions.ts:280`): prompt for a filename, validate it
    as a Python identifier, probe the chosen destination, fetch the **type template**
    (B2's endpoint, FR-028), write, and open the file for editing. Expose it from the
    toolbar as `createNewCustomBlock` is exposed from
    `frontend/src/components/Toolbar.parts/FileOperationsGroup.tsx:84`.

11. **FR-033** — the new-block and new-data-type flows MUST **share** their prompt,
    validation, collision-probe, write-dispatch, and open-file steps. Only the target
    subdirectory and the template kind differ. Two parallel copies would drift the first
    time either changes.

12. **Tests** covering: promotion copies rather than moves (FR-017); collision prompts with
    overwrite and rename, and never silently overwrites (FR-018); the action is hidden — not
    disabled — for built-in, packaged, and already-in-library items (FR-019); success
    confirms inline and reveals the item in `My Library` (FR-020); all of E1, E2, E5 route
    through one implementation (FR-025); a block with a project-level type dependency offers
    cascade, declining warns, and a second-level dependency is reported (FR-021 – FR-024);
    the destination choice routes to the right endpoint and probes the right destination
    (FR-029 – FR-031); New data type produces a valid `DataObject` skeleton at the chosen
    destination (FR-032); and the two flows share their steps (FR-033).

13. Update `CHANGELOG.md` with one entry.

## Required Tests And Checks

- `cd frontend && npm run test`
- `cd frontend && npx tsc --noEmit`
- `cd frontend && npm run lint` and the prettier/format check the repo uses
- `cd frontend && npm run build`
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr --base feat/1995-adr-053-personal-tool-library --head HEAD`
- `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#1996"`
- Do NOT run `scripts/scistudio_pr_create.py`; you are not opening a PR.

Record `CHANGELOG.md` as the docs update and `docs/ai-developer/**` as N/A. If you change
user-visible behaviour that `docs/specs/frontend-block-palette.md` describes and B3/B4 did
not already cover, amend it and record that too.

## Output Required

- Changed file paths.
- The shared promotion action's module path and signature, and proof that E1, E2, and E5
  all call it (FR-025).
- Where the AST cascade detection runs, and how second-level dependencies are reported.
- The new-file destination-choice UX you built, and how the block and type flows share steps.
- Tests/checks run and results.
- Checklist rows updated.
- Commit SHA and branch name.
- Any blocker or scope issue.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file, especially any backend path.
- Cascade dependency detection needs a backend endpoint B1 did not build.
- B3's or B4's popover attachment point does not exist or cannot hold a button.
- The `origin` field needed for FR-019 is missing on either listing response.
- CI or local checks fail for unclear reasons.
- You cannot add/update required tests.
