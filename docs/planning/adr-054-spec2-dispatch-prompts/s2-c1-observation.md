---
title: "ADR-054 Spec 2 Dispatch Prompt: S2-C1 Observation, Codec, And Markers"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# S2-C1 — Observation, Codec, And Markers

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
- Agent branch: feat/2231-observation-codec
- Agent worktree: C:/Users/jiazh/workspace/SciStudio/.worktrees/s2-c1-observation
- Gate record: .workflow/records/2231-feat-2231-observation-codec.json
- Checklist: docs/planning/adr-054-spec2-dependency-analysis-checklist.md

## Required Rules

Read and follow:

- The GitHub issue `#2231`.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/new-feature.md
- docs/ai-developer/personas/implementer.md
- **docs/specs/adr-054-notebook-dependency-analysis.md — FR-026 to FR-034 and
  FR-036 are yours. Read all of it.**

## Scope

You own only:

- `src/scistudio/explore/__init__.py`
- `src/scistudio/explore/dependency_analysis.py`
- `src/scistudio/explore/fingerprint.py`
- `tests/explore/test_dependency_analysis.py`
- `tests/explore/test_fingerprint.py`
- `.workflow/records/2231-feat-2231-observation-codec.json`

You must not touch:

- `tests/architecture/**`
- `tests/explore/test_analysis_differential.py` and `tests/explore/fixtures/**`
- Every other path in the repository.

You are extending code two other agents wrote and the manager already
integrated. Read it before you change it, and do not restructure it to your
taste — a rewrite is out of scope and makes the audits unable to tell your work
from theirs.

## Coordination

- MUST work only on your assigned branch and worktree.
- MUST NOT use `pip install -e .`. `PYTHONPATH=./src` on every python call.
- Do not revert or overwrite other agents' work.
- **Do not open a pull request.** Commit, push your branch, and report.
- Edit only your checklist rows (`S2-C1` in §6 and §7.3).

## TODO And Deferral Rule

Use `TODO(#NNN): <reason>` citing an issue, ADR, spec, or ticket for anything
deferred. No hidden V1, MVP, or later work.

Known deferred items:

- The differential test harness and its fixtures (T-010) belong to agent
  `S2-D1` and are **not** deferred work — do not write a TODO for them.

## Work To Do

Implement tasks T-008, T-009, and T-011 of the spec's §4.3 sequence.

1. **T-008, the namespace comparison and the observation record.** A function
   taking the fingerprints of every top-level name before and after a run and
   reporting names whose fingerprint differs, names that appeared, and names
   that disappeared (FR-026). An `ObservedChange` recorded on the cell keyed to
   the hash of the cell source at the time of the run, discarded when the
   source hash changes (FR-027). An observed change to a name the static
   estimate does not include produces the unpredicted-change diagnostic naming
   the cell and the name (FR-028). A name whose fingerprint fell back to
   identity is reported unobservable once per cell run (FR-029). An observation
   only ever **adds** to a cell's changed set and never removes a statically
   estimated name (FR-030) — this is the invariant the whole design rests on;
   test it directly.
2. **T-009, the metadata codec.** The per-cell record under the `scistudio`
   key of cell metadata, holding the static facts, the flags, the source hash
   they were computed from, and the observation with its own source hash; a
   notebook-level record holding the analysis version (FR-031). Edges are not
   stored and the graph is recomputed on load; a record whose source hash does
   not match its cell is discarded and the cell re-analysed (FR-032). Only
   JSON-serialisable primitives, and **keys the analysis does not recognise are
   preserved on rewrite** (FR-033). Standard-library JSON only (FR-034).
3. **T-011, stability markers.** Every public symbol in the package carries a
   tier and a since version. Read how a neighbouring subsystem does it. The
   frozen surface inventory should be unchanged because this package is not a
   canonical root — confirm that rather than assuming it.
4. Wire the two `AnalysisFlag` members that only your work can raise —
   unpredicted change and unobservable name — into the enumeration the graph
   agent defined. Do not add an eighth flag; FR-036 closes the set at seven.

## Required Tests And Checks

- `PYTHONPATH=./src python -m pytest tests/explore -q`
- `PYTHONPATH=./src python -m pytest tests/architecture/test_layer_deps.py -q`
  — you did not edit it, but your imports can break it.
- SC-008 and SC-009: the codec round trip yields an identical graph, and a
  mismatched source hash triggers re-analysis. Both need their own test.
- Preserving unknown metadata keys needs a test that writes a record beside a
  key your code has never heard of and reads both back.
- The FR-030 invariant needs a test where the observation reports a *smaller*
  set than the static estimate and the changed set stays the union.
- `PYTHONPATH=./src python -m scistudio.qa.governance.gate_record check --mode local --base origin/track/adr-054-spec2-dependency-analysis --head HEAD`
- Record `--base-ref origin/track/adr-054-spec2-dependency-analysis` at `init`.
- Docs N/A: `--docs-na "spec:the governing spec landed in PR 2228 and this change implements it without adding a documented surface"`.
- `git add -A` before every commit. Trailers: `Gate-Record:`,
  `Task-Kind: feature`, `Issue: #2231`, `Assisted-by: Claude:claude-opus-5`.

## Output Required

- Changed file paths.
- Exact pytest summary lines.
- Your branch head sha.
- Checklist rows updated.
- Any blocker, scope issue, or spec ambiguity.

## Stop Conditions

Stop and report back if you need an out-of-scope file, the task conflicts with
the spec, checks fail for unclear reasons, another agent's work blocks yours,
you cannot add the required tests, or the spec is ambiguous in a way that
changes a contract someone else builds against.
```
