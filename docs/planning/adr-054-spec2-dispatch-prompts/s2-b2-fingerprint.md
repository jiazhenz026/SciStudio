---
title: "ADR-054 Spec 2 Dispatch Prompt: S2-B2 The Fingerprint"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# S2-B2 — The Fingerprint

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
- Agent branch: feat/2231-fingerprint
- Agent worktree: C:/Users/jiazh/workspace/SciStudio/.worktrees/s2-b2-fingerprint
- Gate record: .workflow/records/2231-feat-2231-fingerprint.json (yours; create it with `gate_record init`)
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
- **docs/specs/adr-054-notebook-dependency-analysis.md — this is your specification. FR-024, FR-025, FR-029, and the "Fingerprints by type" paragraph of §4.1 are yours. Read all of it for context.**

## Scope

You own only:

- `src/scistudio/explore/fingerprint.py`
- `tests/explore/test_fingerprint.py`
- `.workflow/records/2231-feat-2231-fingerprint.json`

You must not touch:

- `src/scistudio/explore/__init__.py` — agent S2-B1 owns it and is creating the
  package right now. Your module must be importable as
  `scistudio.explore.fingerprint` without your editing the package `__init__`;
  the manager integrates the export.
- `src/scistudio/explore/dependency_analysis.py` and
  `tests/explore/test_dependency_analysis.py` — agent S2-B1 owns those.
- `tests/architecture/**` — agent S2-B1 owns the layer rule.
- `tests/explore/test_analysis_differential.py` and `tests/explore/fixtures/**`
  — agent S2-D1 owns those.
- Every other path in the repository.

If you need an out-of-scope path, stop and report back.
Do not edit it.

Note: `src/scistudio/explore/` may not exist when you start. Create the
directory and your file inside it; do **not** create or edit its `__init__.py`.
If your test needs the package importable, the directory plus the file is
enough for `PYTHONPATH=./src` imports once S2-B1's `__init__.py` lands. If your
tests cannot run without it, write a minimal placeholder `__init__.py`
containing only a module docstring, report that you did so, and expect the
manager to take S2-B1's version at integration.

## Coordination

- You are not alone in this codebase. S2-B1 is implementing
  `dependency_analysis.py` in a separate worktree at the same time. Your module
  MUST NOT import it.
- MUST work only on your assigned branch.
- MUST work only in your assigned worktree.
- MUST NOT use `pip install -e .`. Every python invocation needs `PYTHONPATH=./src`.
- Do not revert or overwrite other agents' work.
- Do not broaden scope.
- MUST target your PR to `track/adr-054-spec2-dependency-analysis`.
- MUST NOT target your PR to `main`.
- MUST NOT merge any PR.
- Edit only your checklist rows (row `S2-B2` in §6, and the `S2-B2` line in §7.3).

## TODO And Deferral Rule

Deferred work must be tracked in the repo.
Use `TODO(#NNN): <reason>` and cite an issue, ADR, spec, or follow-up ticket.
Do not leave hidden V1, MVP, or later work.

Known deferred items:

- The namespace comparison of FR-026, the observation record of FR-027 to
  FR-030, and the unobservable diagnostic's placement are agent S2-C1's tasks
  and are **not** deferred work — do not write a TODO for them. Provide the
  `Fingerprint` value type of the spec's Key Entities section (digest,
  observable flag, the type it was computed for) that the comparison will
  consume, and stop there.

## Work To Do

Implement task T-007 of the spec's §4.3 implementation sequence.

1. A pure fingerprint function mapping an object to a `Fingerprint`: equal for
   an unchanged object, different within the stated bound for an object mutated
   in place (FR-024).
2. Content inspection for numpy arrays, pandas frames and series, lists,
   tuples, dicts, sets, strings, bytes, and numbers. Every other type falls
   back to identity with the result marked unobservable (FR-024, FR-029).
3. One declared cost constant and one declared sample size, in one place
   (FR-025). Below the bound hash the whole content; above it sample at fixed
   strides across the full extent together with shape, dtype, and length.
4. Arrays hash their bytes through the `xxhash` dependency SciStudio already
   carries; frames hash their numeric blocks the same way and sample their
   object columns; containers hash their elements recursively. See the
   "Fingerprints by type" paragraph of §4.1.
5. Import numpy and pandas **lazily and only inside the fingerprint**, per
   FR-035. `import scistudio.stability` is the only SciStudio import allowed.
6. Apply the stability markers the repository uses to every public symbol you
   add. Read how a neighbouring subsystem does it rather than inventing a form.

Design constraints you must not violate:

- Do not reuse `scistudio.utils.hashing.content_hash`. §4.1 states why it is
  unsuitable: it hashes arrays whole with no bound and falls back to `repr`.
- A fingerprint must never guess from `repr`. A false observation is worse than
  an unobservable one.
- FR-004: pure. No filesystem, no execution beyond hashing the object given.

## Required Tests And Checks

- `PYTHONPATH=./src python -m pytest tests/explore/test_fingerprint.py -q`
- SC-006 is a hard requirement: the fingerprint detects an in-place mutation of
  a numpy array, a pandas frame, a pandas series, a list, a dict, and a set,
  each with its own test. Test the unchanged-equality direction for each too.
- Test the size bound: an object above the bound is sampled, the sample spans
  the full extent, and the cost stays inside the declared constant. Measure the
  cost on the largest fixture and record the number.
- Test the unobservable fallback with a type that has a random or stateful
  `repr`, and assert the fallback is reported rather than silently hashed.
- `PYTHONPATH=./src python -m scistudio.qa.governance.gate_record check --mode pre-pr --base origin/track/adr-054-spec2-dependency-analysis --head HEAD --pr-body-file .workflow/local/pr-body.md`
- Your branch is stacked on `track/adr-054-spec2-dependency-analysis`, not on
  `main`. Record it with `--base-ref origin/track/adr-054-spec2-dependency-analysis`
  at `init`, and pass `--base origin/track/adr-054-spec2-dependency-analysis`
  to every `check` and `finalize`.
- `PYTHONPATH=./src python -m scistudio.qa.governance.gate_record finalize --commit <sha> --pr-body-file .workflow/local/pr-body.md --closes "#2231"` before PR creation
- `PYTHONPATH=./src python scripts/scistudio_pr_create.py` for the PR (do not use `gh pr create` directly)
- Docs: N/A. Record `--docs-na "spec:the governing spec docs/specs/adr-054-notebook-dependency-analysis.md landed in PR 2228 and this change implements it without adding a documented surface"`.
- `git add -A` before every commit.

## Output Required

Before reporting done, provide:

- Changed file paths.
- Tests/checks run and results, including the exact pytest summary line.
- The measured fingerprint cost against the declared bound.
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
