[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Deliver ADR-053 Spec 1 in full as two reviewable PRs, with no deferred scope. This slice closes the one partial requirement B4 reported.
- Task kind: feature
- Persona: implementer
- Issues: #2025 (FR-040), #2024 (the `TypeSummary` contract)
- Umbrella PR: #2029 `[DO NOT MERGE]`
- Protected branch: main
- Tracking branch (your merge target): feat/1995-adr-053-personal-tool-library
- Agent branch: feat/2025-type-package-attribution
- Agent worktree: C:/Users/jiazh/workspace/SciStudio-wt-b6
- Gate record: create with `gate_record init --slug 2025-type-package-attribution`
- Checklist: docs/planning/adr-053-spec1-personal-tool-library-checklist.md (§8.3)

## The gap

**FR-040** requires the Data types tab to mirror the Blocks tab: core pinned, then
`My Library`, then `This Project`, **then packages A→Z**.

The Blocks tab splits per-package sections from `BlockSummary.package_name`. `TypeSummary`
has no equivalent field — the package root name is discarded at type-scan time — so B4
renders **one lumped `Packages` section**. Ordering is met; the per-package A→Z split is
not.

B4 deliberately did **not** infer a package name from `file_path`, and that judgment stands:
an inferred name could contradict the Blocks tab's real name for the same distribution,
which is precisely the drift this spec exists to remove. The fix is to carry the real name,
not to guess it.

B4 also reports that `typeSectionIdFor` in `TypePalette.parts/typeModel.ts` is the single
frontend switch, so the tab lights up with essentially no other frontend change once the
field exists.

## Required Rules

- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/new-feature.md
- docs/ai-developer/personas/implementer.md
- docs/specs/adr-053-personal-tool-library.md — §7 (FR-026), §9.2 (FR-040), §10.1, §10.2

## Scope

You own:

- `src/scistudio/core/types/registry.py` — record the owning package on the type spec
- `src/scistudio/api/schemas.py` — `TypeSummary.package_name`
- `src/scistudio/api/routes/types.py` — populate it
- `frontend/src/types/api.ts` — the field on the client type
- `frontend/src/components/TypePalette.parts/typeModel.ts` — the `typeSectionIdFor` switch
- `frontend/src/components/TypePalette.parts/__tests__/**`
- `tests/api/test_types_routes.py`, `tests/core/test_type_colour.py` if the spec shape moves
- `CHANGELOG.md`

You must not touch:

- `frontend/src/components/TypePalette.tsx` beyond what the section split strictly needs — **B5 is editing its popover mount site in parallel**
- `frontend/src/App.parts/useProjectActions.ts`, `frontend/src/components/promotion/**`, `BlockDetailPopover.tsx` — B5 owns them
- `src/scistudio/api/_block_source.py` — consume the shared resolver, do not change it
- `src/scistudio/core/types/base.py` — protected core, already settled by B2
- `docs/planning/**` — the manager owns the checklist

## Work To Do

1. Record the owning package name on the type spec at scan time. `BlockSummary.package_name`
   is the precedent — match its semantics and its value for the same distribution, so the
   Blocks tab and the Data types tab name a package identically. If they can disagree for
   any discovery tier, say so in your report rather than papering over it.

2. Surface it as `package_name: string | null` on `TypeSummary`. `null` for core, user-tier,
   project-tier, and any type whose package cannot be determined. Do **not** infer it from
   `file_path`.

3. Switch `typeSectionIdFor` so package-tier types group per package, and the section order
   becomes core (pinned) → `My Library` → `This Project` → packages A→Z, exactly as the
   Blocks tab does. Reuse B3's `buildSections<T>` remainder behaviour rather than adding a
   second ordering path.

4. Keep the lumped-`Packages` fallback for a package-tier type with a `null` name, if that
   state is reachable. A type must never vanish from the tab because its package could not
   be named.

5. Tests: a packaged type reports its real package name; two types from different packages
   land in different sections ordered A→Z; a `null` name degrades without dropping the type;
   and the name matches what the Blocks tab reports for the same distribution.

## Required Tests And Checks

- `PYTHONPATH=./src python -m pytest tests/api/test_types_routes.py --no-cov -q`
- `cd frontend && npm run check:ci`
- `SCISTUDIO_GATE_BASE=feat/1995-adr-053-personal-tool-library python -m scistudio.qa.governance.gate_record check --mode pre-pr --admin-label admin-approved:core-change`

## Output Required

- Changed file paths.
- The final `TypeSummary.package_name` semantics, and confirmation it matches
  `BlockSummary.package_name` for the same distribution.
- Whether any discovery tier can make the two disagree.
- Tests/checks run and results.
- Commit SHA and branch name.

## Stop Conditions

Stop and report back if:

- The owning package genuinely cannot be recovered at type-scan time without a change
  outside your write set.
- Matching `BlockSummary.package_name` semantics would require touching the block side.
- You need a file B5 owns.
