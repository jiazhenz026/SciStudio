---
title: "ADR-054 Spec 2 Dispatch Prompt: S2-B1 Static Facts And The Graph"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# S2-B1 — Static Facts And The Graph

Filled from `docs/ai-developer/templates/agent-dispatch-prompt-template.md`.

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-054 spec 2, the notebook dependency analysis, in full and from scratch.
- Task kind: feature
- Persona: implementer
- Issue: #2231
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2231
- Umbrella PR: #2232 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-054-spec2-dependency-analysis
- Agent branch: feat/2231-dep-analysis-graph
- Agent worktree: C:/Users/jiazh/workspace/SciStudio/.worktrees/s2-b1-graph
- Gate record: .workflow/records/2231-feat-2231-dep-analysis-graph.json (yours; create it with `gate_record init`)
- Checklist: docs/planning/adr-054-spec2-dependency-analysis-checklist.md

## Required Rules

Read and follow:

- The GitHub issue `#2231` and all owner instructions in it.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/new-feature.md
- docs/ai-developer/personas/implementer.md
- **docs/specs/adr-054-notebook-dependency-analysis.md — this is your specification. Read all of it.**
- docs/adr/ADR-054.md sections 6.1 and 6.2 for the surrounding design.

## Scope

You own only:

- `src/scistudio/explore/__init__.py`
- `src/scistudio/explore/dependency_analysis.py`
- `tests/explore/__init__.py` (if the test layout needs one)
- `tests/explore/test_dependency_analysis.py`
- `tests/architecture/test_layer_deps.py`
- `.workflow/records/2231-feat-2231-dep-analysis-graph.json`

You must not touch:

- `src/scistudio/explore/fingerprint.py` and `tests/explore/test_fingerprint.py` — agent S2-B2 owns those and is writing them right now.
- `tests/explore/test_analysis_differential.py` and `tests/explore/fixtures/**` — agent S2-D1 owns those.
- Every other path in the repository, including `docs/specs/**`, `docs/architecture/**`, and every frontend path.

If you need an out-of-scope path, stop and report back.
Do not edit it.

## Coordination

- You are not alone in this codebase. S2-B2 is implementing `fingerprint.py` in
  a separate worktree at the same time, from the same spec. Your module MUST
  NOT import it and MUST NOT define it.
- MUST work only on your assigned branch.
- MUST work only in your assigned worktree.
- MUST NOT use `pip install -e .`. Every python invocation needs `PYTHONPATH=./src`.
- Do not revert or overwrite other agents' work.
- Do not broaden scope.
- MUST target your PR to `track/adr-054-spec2-dependency-analysis`.
- MUST NOT target your PR to `main`.
- MUST NOT merge any PR.
- Edit only your checklist rows (row `S2-B1` in §6, and the `S2-B1` line in §7.3).
- Record every completed row with a PR, commit, test, report, or gate evidence.

## TODO And Deferral Rule

Deferred work must be tracked in the repo.
Use `TODO(#NNN): <reason>` and cite an issue, ADR, spec, or follow-up ticket.
Do not leave hidden V1, MVP, or later work.

Known deferred items:

- The runtime observation (FR-024 to FR-030), the metadata codec (FR-031 to
  FR-034), and the stability markers are agent S2-C1's tasks and are **not**
  deferred work — do not write a TODO for them. Leave the seams they need:
  the graph builder MUST accept a per-cell observed changed set as an argument
  and union it into the cell's changed set per FR-002 and FR-022, even though
  nothing produces observations yet.

## Work To Do

Implement tasks T-001 to T-006 of the spec's §4.3 implementation sequence.

1. **T-001.** Create `src/scistudio/explore/` as a new subsystem package with
   its `__init__.py` exporting the public surface you add. Add the subsystem to
   the enumeration in `tests/architecture/test_layer_deps.py` and add the
   assertion FR-035 requires: the explore analysis modules import from the
   standard library and (lazily, inside the fingerprint only) numpy and pandas,
   and import nothing from SciStudio beyond `scistudio.stability`. Read the
   existing rules in that file and follow their shape; do not invent a second
   mechanism.
2. **T-002.** Compute the assigned and read names per cell with `symtable`
   (FR-005, FR-006). Every assignment form the spec names needs its own test.
3. **T-003.** Strip `%` and `!` lines; mark opaque `%%` cells, syntax errors,
   star imports, and `%run` (FR-011, FR-012, FR-013). No cell may raise, and a
   bad cell must not affect any other.
4. **T-004.** Record output declarations, input declarations, and block calls
   from one `ast` walk (FR-008, FR-009, FR-010).
5. **T-005.** Build the graph over enabled cells with edges, edge origins,
   unresolved reads, and version nodes (FR-014 to FR-019). Builtins draw no
   edge and are not unresolved.
6. **T-006.** Implement the four queries: downstream, backward slice, changed
   set, and written-order definer (FR-020 to FR-023).
7. Define the closed `AnalysisFlag` enumeration of FR-036 with all seven
   members, even though two of them (unpredicted change, unobservable name)
   are raised by S2-C1's work.
8. Match the Key Entities section of the spec for names and attributes:
   `CellFacts`, `DependencyGraph`, `Edge`, `VersionNode`, `SliceResult`,
   `AnalysisFlag`. Another agent builds against these names.

Design constraints you must not violate:

- FR-003: standard library only. No IPython, no `nbformat`, no static-analysis
  package.
- FR-004: pure. No execution, no filesystem, no kernel.
- FR-007: carry no list of mutating methods or functions. Static facts are
  assignments only.
- FR-002: every uncertain rule resolves toward the extra edge.

## Required Tests And Checks

- `PYTHONPATH=./src python -m pytest tests/explore/test_dependency_analysis.py -q`
- `PYTHONPATH=./src python -m pytest tests/architecture/test_layer_deps.py -q`
- SC-001 is a hard requirement: **every** assignment form named in FR-005 has
  its own test that fails if the form stops being recognised. SC-004 and SC-005
  likewise.
- `PYTHONPATH=./src python -m scistudio.qa.governance.gate_record check --mode pre-pr --base origin/track/adr-054-spec2-dependency-analysis --head HEAD --pr-body-file .workflow/local/pr-body.md`
- Your branch is stacked on `track/adr-054-spec2-dependency-analysis`, not on
  `main`. Record it with `--base-ref origin/track/adr-054-spec2-dependency-analysis`
  at `init`, and pass `--base origin/track/adr-054-spec2-dependency-analysis`
  to every `check` and `finalize`. Without it the gate reads the track branch's
  commits as yours.
- `PYTHONPATH=./src python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#2231"` before PR creation
- `PYTHONPATH=./src python scripts/scistudio_pr_create.py` for the PR (do not use `gh pr create` directly)
- `PYTHONPATH=./src python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr <url> --pr-body-file <path>` after the PR is created
- Docs: N/A. The governing spec already landed in PR #2228 and this work adds
  no new documented surface. Record `--docs-na "spec:the governing spec docs/specs/adr-054-notebook-dependency-analysis.md landed in PR 2228 and this change implements it without adding a documented surface"`.
- Sentrux: run `sentrux scan .` and `sentrux check .` if the CLI is available;
  otherwise record that it is unavailable.
- `git add -A` before every commit. pre-commit stashing unstaged files is the
  usual cause of a confusing `/bin/sh not found` failure.

## Output Required

Before reporting done, provide:

- Changed file paths.
- Tests/checks run and results, including the exact pytest summary line.
- Checklist rows updated.
- PR number or commit.
- Any blocker or scope issue.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file.
- The task conflicts with AGENTS.md, ADR-054, the spec, or the gate record.
- CI or local checks fail for unclear reasons.
- Another agent's work blocks yours.
- You cannot add/update required tests.
- The spec is ambiguous in a way that changes the contract another agent builds
  against. Do not guess; report the ambiguity and your proposed reading.
```
