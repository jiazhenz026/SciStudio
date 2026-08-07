[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Deliver ADR-053 Spec 1 in full as two reviewable PRs; this slice is spec §12.2 step 1, the foundation every other slice sits on.
- Task kind: refactor
- Persona: implementer
- Issue: #2020
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2020
- Umbrella PR: #2027 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-053-spec1-personal-tool-library
- Tracking branch (your PR/merge target): fix/2020-adr-053-registry-runtime-defects
- Agent branch: fix/2020-dropin-provisioning-helper
- Agent worktree: C:/Users/jiazh/workspace/SciStudio-wt-a1
- Gate record: create with `gate_record init --slug 2020-dropin-provisioning-helper`
- Checklist: docs/planning/adr-053-spec1-personal-tool-library-checklist.md (§7.3 rows A1)

## Required Rules

Read and follow:

- The GitHub issue `#2020` and all owner instructions in it.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/personas/implementer.md
- docs/specs/adr-053-personal-tool-library.md — §2.4, §2.6, §10.3 (FR-057 – FR-061), §12.2
- docs/adr/ADR-053.md §3

## Scope

You own only:

- `src/scistudio/core/dropins.py` (new)
- `src/scistudio/core/types/serialization.py`
- `src/scistudio/core/types/registry.py` (scan-order reconciliation only, FR-061)
- `src/scistudio/api/runtime/_projects.py`
- `src/scistudio/ai/agent/mcp/runtime.py`
- `src/scistudio/blocks/io/_unified_dispatch.py`
- `tests/api/test_registry_provisioning_parity.py` (new)
- `CHANGELOG.md` (one entry)

You must not touch:

- `src/scistudio/blocks/registry/_scan.py` — owned by A3 (#2022)
- `src/scistudio/api/routes/**` — owned by A2 and Track B
- `src/scistudio/core/types/base.py` — protected core, owned by B2
- Any `frontend/**` path
- `docs/ai-developer/**`

If you need an out-of-scope path, stop and report back. Do not edit it.

## Coordination

- You are not alone in this codebase. A2, A3, and a second manager's spec 2 track run in parallel.
- MUST work only on your assigned branch, in your assigned worktree.
- MUST NOT use `pip install -e .`. Use `PYTHONPATH=./src` for every command.
- Do not revert or overwrite other agents' work.
- Do not broaden scope.
- MUST NOT open a PR. Push your branch and report; the manager integrates into the tracking branch.
- MUST NOT merge anything.
- Edit only your own checklist rows (§7.3 rows beginning `A1`).

## TODO And Deferral Rule

Deferred work must be tracked in the repo. Use `TODO(#NNN): <reason>` citing an issue,
ADR, spec, or follow-up ticket. Do not leave hidden V1, MVP, or later work.

The owner directive for this dispatch is **complete delivery with no deferred scope**. If
you believe something must be deferred, stop and report it as a blocker instead of writing
a TODO.

Known deferred items: N/A

## Work To Do

1. **Create the shared helper** at `src/scistudio/core/dropins.py`.

   It MUST live in `scistudio.core` or lower. The import-linter contract "Core must not
   depend on blocks, engine, api, ai, or workflow" forbids `scistudio.core` importing
   `scistudio.blocks`, and `scistudio.core.types.serialization` is one of the four
   consumers — so the helper cannot live under `scistudio.blocks`. Do not place it under
   `scistudio/core/types/`: the "core.types submodules are acyclic" contract applies there
   and `serialization.py` would import a sibling.

   Required surface (name it as you see fit, but it must cover exactly these concerns):

   - drop-in **scan directories** for a given tier and project context, for blocks and for types;
   - drop-in **import roots** for executing a drop-in module (project types dir, user types
     dir, and the existing user site dir from `scistudio.desktop.paths.user_python_import_roots`);
   - **user-tier roots** (`~/.scistudio/blocks/`, `~/.scistudio/types/`) as the single
     answer to "where does the user tier live" (FR-058).

   Callers MAY pass their own project directory and MAY declare whether a project context
   exists. Callers MUST NOT decide which directories the tier comprises or which roots go
   on `sys.path` (FR-057).

2. **Rewire all four registration points** to consume the helper:

   - `src/scistudio/api/runtime/_projects.py` — `refresh_block_registry`, `refresh_type_registry`
   - `src/scistudio/ai/agent/mcp/runtime.py` — `_build_block_registry`, `_build_type_registry`
   - `src/scistudio/core/types/serialization.py` — worker-side reconstruction (reads `SCISTUDIO_PROJECT_DIR`)
   - `src/scistudio/blocks/io/_unified_dispatch.py` — `_scan_runtime_registry` and its two callers

   Delete the now-redundant `always_home` parameter rather than leaving it inert; the
   helper owns that decision after FR-060.

3. **FR-059** — the agent runtime MUST register project-level and user-level **type**
   directories. `_build_type_registry()` registers none today. Fix the `make_mcp_runtime`
   docstring, which currently claims coverage it does not have.

4. **FR-060** — user-tier discovery MUST be unconditional at all four points, for blocks
   and for types alike. Project-tier discovery still requires a project. Today the
   behaviour is unconditional for types under the API, unconditional for blocks under the
   agent, and conditional for blocks under the API; after this it is unconditional
   everywhere. This settles spec §13 OQ-2 — do not re-open it.

5. **FR-061** — `BlockRegistry.scan()` runs builtins -> drop-in -> entry-point ->
   package-src; `TypeRegistry.scan_all()` runs builtins -> entry-point -> package-src ->
   drop-in. Both claim entry-point registrations win on duplicates and both achieve it,
   one by ordering and one by skip-if-present. Either reconcile the orders or record the
   reason at **both** call sites. If you reconcile, prove the observable precedence is
   unchanged with a test.

6. **Write the parity test** `tests/api/test_registry_provisioning_parity.py`: for a given
   project context, all four registration sites resolve identical drop-in directories and
   identical import roots (FR-057, FR-058); user-tier directories are present with no
   active project and project-tier directories are not (FR-060).

7. Update `CHANGELOG.md` with one entry describing the consolidation and the agent
   type-visibility fix.

## Required Tests And Checks

- `PYTHONPATH=./src python -m pytest tests/api/test_registry_provisioning_parity.py -q`
- `PYTHONPATH=./src python -m pytest tests/api tests/blocks tests/core -q` (regression sweep for the rewired call sites)
- `PYTHONPATH=./src python -m lint_imports` or the repository's import-linter command — the new module MUST NOT introduce a layering inversion
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr --base origin/main --head HEAD`
  to run tier-selected CI-equivalent checks and reconcile the gate ledger
- `python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#2020"`
- Do NOT run `scripts/scistudio_pr_create.py`; you are not opening a PR.

This task does not change wrapper, hook, gate-record, CI, or AI-runtime behavior, so
`docs/ai-developer/**` needs no update — record that as the docs N/A rationale for that
class, and record `CHANGELOG.md` as the docs update.

## Output Required

Before reporting done, provide:

- Changed file paths.
- The helper's public surface (function names and signatures) — the manager freezes this
  for A3 and B1.
- Tests/checks run and results.
- Checklist rows updated.
- Commit SHA and branch name.
- Any blocker or scope issue.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file.
- The helper cannot be placed without an import-linter violation.
- Reconciling the scan order changes observable precedence.
- CI or local checks fail for unclear reasons.
- You cannot add/update required tests.
