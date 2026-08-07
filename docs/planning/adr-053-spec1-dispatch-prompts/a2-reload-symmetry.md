[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Deliver ADR-053 Spec 1 in full as two reviewable PRs; this slice is spec §12.2 step 2, plus the previewer analogue the owner folded in.
- Task kind: bugfix
- Persona: implementer
- Issues: #2021 and #2009
- Issue URLs: https://github.com/jiazhenz026/SciStudio/issues/2021 , https://github.com/jiazhenz026/SciStudio/issues/2009
- Umbrella PR: #2027 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-053-spec1-personal-tool-library
- Tracking branch (your merge target): fix/2020-adr-053-registry-runtime-defects
- Agent branch: fix/2021-registry-reload-symmetry
- Agent worktree: C:/Users/jiazh/workspace/SciStudio-wt-a2
- Gate record: create with `gate_record init --slug 2021-registry-reload-symmetry`
- Checklist: docs/planning/adr-053-spec1-personal-tool-library-checklist.md (§7.3 rows A2)

Your branch starts from the tracking branch **after A1 (#2020) has landed**. The shared
drop-in provisioning helper `src/scistudio/core/dropins.py` already exists; use it, do not
duplicate its logic.

## Required Rules

Read and follow:

- The GitHub issues `#2021` and `#2009`.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/bug-fix.md
- docs/ai-developer/personas/implementer.md
- docs/specs/adr-053-personal-tool-library.md — §2.6, §10.4 (FR-062 – FR-065)

## Scope

You own only:

- `src/scistudio/api/routes/git.py`
- `src/scistudio/api/routes/packages.py`
- `src/scistudio/api/runtime/_projects.py` (refresh entry points only)
- `src/scistudio/previewers/**` and the previewer refresh entry point, for #2009
- `tests/api/test_registry_reload_symmetry.py` (new)
- `CHANGELOG.md` (one entry)

You must not touch:

- `src/scistudio/core/dropins.py` — A1 owns it; consume it, do not modify it
- `src/scistudio/blocks/registry/_scan.py` — A3 owns it
- `src/scistudio/core/types/base.py` — protected core, owned by B2
- `src/scistudio/api/routes/{blocks,types,user_library}.py` — Track B
- Any `frontend/**` path
- `docs/ai-developer/**`

If you need an out-of-scope path, stop and report back. Do not edit it.

## Coordination

- You are not alone in this codebase. A3 runs in parallel on `blocks/registry/**`; a
  second manager's spec 2 track runs on `track/adr-053-work-import`.
- MUST work only on your assigned branch, in your assigned worktree.
- MUST NOT use `pip install -e .`. Use `PYTHONPATH=./src`.
- Do not revert or overwrite other agents' work.
- MUST NOT open a PR. Push your branch and report; the manager integrates.
- MUST NOT merge anything.
- Edit only your own checklist rows (§7.3 rows beginning `A2`).

## TODO And Deferral Rule

Deferred work must be tracked in the repo with `TODO(#NNN): <reason>` citing an issue,
ADR, spec, or follow-up ticket. The owner directive is **complete delivery with no
deferred scope** — if something must be deferred, stop and report it as a blocker.

Known deferred items: N/A

## Work To Do

1. **FR-062 — the audit is the deliverable as much as the fix.** Enumerate every site
   that calls `refresh_block_registry` and evaluate each against the type registry and the
   previewer registry. The known five are branch switch
   (`src/scistudio/api/routes/git.py:493`) and four package install/uninstall call sites in
   `src/scistudio/api/routes/packages.py`. They are the known ones, not necessarily all of
   them. Report the complete list you found.

2. **FR-063** — package install and uninstall MUST refresh the type registry. A package
   can ship types; today installing one leaves them undiscovered until the next project
   switch.

3. **FR-064** — branch switch MUST refresh the type registry. Switching branches can
   change `{project}/types/` exactly as it changes `{project}/blocks/`.

4. **#2009 — the same defect for previewers.** The previewer registry is not refreshed on
   package install/uninstall or branch switch either. Fix it at the same call sites. This
   is the owner's explicit addition to scope; it is recorded in the checklist §1.2.

   Scope guard: #2009 is the **refresh** defect only. Do NOT add a user-level previewer
   tier and do NOT extend `OwnerKind` — that is #2017 and the spec explicitly excludes it.

5. **FR-065** — after a user library write, the refresh MUST reach every process holding a
   registry, not only the one that served the request. The write endpoint itself is Track B
   (#1996) and does not exist yet on your branch. Your obligation here is to make the
   refresh mechanism reachable and cross-process-capable, and to document the entry point
   B1 will call. If you conclude the cross-process part cannot land without the write
   endpoint, say so explicitly in your report so the manager can sequence it into B1 —
   do not silently drop it.

6. Prefer one refresh entry point that covers block, type, and previewer registries over
   three call sites repeated at every invalidation event. Three registries refreshed by
   hand at five sites is the same drift #2020 just removed.

7. **Write `tests/api/test_registry_reload_symmetry.py`**: installing a package that ships
   types makes them discoverable without a project switch (FR-063); switching to a branch
   with a different `{project}/types/` refreshes the type registry (FR-064); the same for
   previewers (#2009).

8. Update `CHANGELOG.md` with one entry.

## Required Tests And Checks

- `PYTHONPATH=./src python -m pytest tests/api/test_registry_reload_symmetry.py -q`
- `PYTHONPATH=./src python -m pytest tests/api tests/previewers -q`
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr --base fix/2020-adr-053-registry-runtime-defects --head HEAD`
- `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#2021"`
- Do NOT run `scripts/scistudio_pr_create.py`; you are not opening a PR.

No wrapper, hook, gate-record, CI, or AI-runtime behavior changes, so
`docs/ai-developer/**` needs no update; record that N/A rationale and record
`CHANGELOG.md` as the docs update.

## Output Required

- Changed file paths.
- The complete list of registry-invalidating call sites you found (FR-062 audit result).
- Whether FR-065 cross-process refresh landed here or must sequence into B1, with reasons.
- Tests/checks run and results.
- Checklist rows updated.
- Commit SHA and branch name.
- Any blocker or scope issue.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file.
- Refreshing the type or previewer registry at a call site breaks an existing test — that
  is the "behaviour change to a path outside the headline feature" risk in spec §14 and
  the manager must see it.
- FR-065 cannot be satisfied without the Track B write endpoint.
- CI or local checks fail for unclear reasons.
- You cannot add/update required tests.
