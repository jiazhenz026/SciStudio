---
title: "ADR-054 Spec 3 Dispatch Prompt: S3-A1 Dependencies And The Notebook Store"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# S3-A1 — Dependencies And The Notebook Store

Filled from `docs/ai-developer/templates/agent-dispatch-prompt-template.md`.

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-054 spec 3, the Explore Session runtime, in full.
- Task kind: feature
- Persona: implementer
- Issue: #2240
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2240
- Umbrella PR: #2241 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-054-spec3-explore-session
- Agent branch: feat/2240-notebook-store
- Agent worktree: C:/Users/jiazh/workspace/SciStudio/.worktrees/s3-a1-notebook
- Gate record: .workflow/records/2240-feat-2240-notebook-store.json (yours; create it with `gate_record init`)
- Checklist: docs/planning/adr-054-spec3-explore-session-checklist.md

## Required Rules

Read and follow:

- The GitHub issue `#2240` and all owner instructions in it.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/new-feature.md
- docs/ai-developer/personas/implementer.md
- **docs/specs/adr-054-explore-session.md — this is your specification. Read all of it; T-001 and T-005 of §4.3, and FR-005, FR-027, FR-032, FR-033, FR-059 are yours.**
- docs/adr/ADR-054.md for the surrounding design.

## Scope

You own only:

- `pyproject.toml` — the `ipykernel` and `jupyter_client` dependencies (FR-059)
- `src/scistudio/explore/notebook.py`
- `tests/explore/test_notebook_store.py`
- `CHANGELOG.md` — one entry for the two new runtime dependencies
- `.workflow/records/2240-feat-2240-notebook-store.json`

You must not touch:

- `tests/architecture/test_layer_deps.py` — agent S3-C3 owns it, and spec 2's
  version of that file merges forward first.
- Every other file under `src/scistudio/explore/` — other agents own them.
- Every frontend path, `docs/specs/**`, and `docs/architecture/**`.

If you need an out-of-scope path, stop and report back.
Do not edit it.

## Coordination

- You are not alone in this codebase. Several agents are implementing other
  modules of the same spec in separate worktrees right now. The write sets are
  disjoint by design; keep to yours.
- MUST work only on your assigned branch.
- MUST work only in your assigned worktree.
- MUST NOT use `pip install -e .`. Every python invocation needs `PYTHONPATH=./src`.
- Do not revert or overwrite other agents' work.
- Do not broaden scope.
- **Do not open a pull request.** Commit your work and push your branch. The
  manager integrates every branch into
  `track/adr-054-spec3-explore-session` and runs the pre-PR gate once for the
  whole candidate. Opening a PR per agent would multiply CI load for no signal.
- MUST NOT merge anything.
- Edit only your checklist rows (your row in §6, and your line in §7.3).

## TODO And Deferral Rule

Deferred work must be tracked in the repo.
Use `TODO(#NNN): <reason>` and cite an issue, ADR, spec, or follow-up ticket.
Do not leave hidden V1, MVP, or later work.

Known deferred items:

- The session service that calls your store, the commit path that strips
  outputs into a ref, and the analysis codec are other agents' tasks and are
  **not** deferred work — do not write a TODO for them. Expose the seams they
  need: a function that reads a notebook into cells with their metadata intact,
  a function that writes it back preserving unrecognised metadata keys, and a
  function that returns the notebook with outputs stripped without writing it
  anywhere.

## Work To Do

Implement T-001 (the dependency half) and T-005 of the spec's §4.3 sequence.

1. **T-001, dependencies.** Add `ipykernel` and `jupyter_client` to
   `pyproject.toml` in the same dependency group the runtime already uses for
   packages the bundled interpreter must carry. Pin them the way the file pins
   its neighbours. Add a `CHANGELOG.md` entry. Do **not** attempt to rebuild
   the bundled runtime; note in your report that a release cannot ship the
   session until the runtime is rebuilt, which the spec's §4.5 already records
   as a release-checklist item.
2. **T-005, the notebook store.** Read and write the `.ipynb` on disk with
   outputs (FR-027). Preserve cell metadata across a round trip, including keys
   the store does not recognise (FR-033) — another agent's analysis records live
   under the `scistudio` key and must survive. Strip outputs for the committed
   form without disturbing the on-disk file (FR-032). Detect an external edit
   and reload (FR-005's reload clause).
3. Use the standard library's JSON handling; do not add `nbformat` or any other
   notebook library as a dependency.
4. Apply the repository's stability markers to every public symbol you add.
   Read how a neighbouring subsystem does it rather than inventing a form.

## Required Tests And Checks

- `PYTHONPATH=./src python -m pytest tests/explore/test_notebook_store.py -q`
- Round-trip tests are the point of this module: a notebook with unrecognised
  metadata keys, with outputs, with a mix of code and markdown cells, and with
  a cell carrying an analysis record must come back byte-equivalent in every
  field the store did not deliberately change.
- Test the external-reload path with a file changed underneath an open handle.
- Test the stripped form: outputs absent, everything else identical.
- `PYTHONPATH=./src python -m scistudio.qa.governance.gate_record check --mode local --base origin/track/adr-054-spec3-explore-session --head HEAD`
- Your branch is stacked on `track/adr-054-spec3-explore-session`, not on
  `main`. Record it with `--base-ref origin/track/adr-054-spec3-explore-session`
  at `gate_record init`, and pass
  `--base origin/track/adr-054-spec3-explore-session` to every `check`.
  Without it the gate measures your branch against `origin/main`, reads spec 2's
  commits as yours, and reports false out-of-scope findings.
- Docs: `--docs-na "spec:the governing spec docs/specs/adr-054-explore-session.md landed in PR 2228 and this change implements one of its tasks without adding a separately documented surface"`, unless your task section above says otherwise.
- `git add -A` before every commit.
- Commit trailers are required on every commit:
  `Gate-Record:`, `Task-Kind: feature`, `Issue: #2240`, `Assisted-by: Claude:claude-opus-5`.

## Output Required

Before reporting done, provide:

- Changed file paths.
- Tests/checks run and results, including the exact pytest summary line.
- The commit sha of your branch head.
- Checklist rows updated.
- Any blocker, scope issue, or spec ambiguity.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file.
- The task conflicts with AGENTS.md, ADR-054, the spec, or the gate record.
- Local checks fail for unclear reasons.
- Another agent's work blocks yours.
- You cannot add/update required tests.
- The spec is ambiguous in a way that changes a contract another agent builds
  against. Do not guess; report the ambiguity and your proposed reading.
```
