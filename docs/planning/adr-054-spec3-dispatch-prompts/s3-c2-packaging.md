---
title: "ADR-054 Spec 3 Dispatch Prompt: S3-C2 Packaging A Notebook Into A Block"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# S3-C2 — Packaging A Notebook Into A Block

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
- Agent branch: feat/2240-packaging
- Agent worktree: C:/Users/jiazh/workspace/SciStudio/.worktrees/s3-c2-packaging
- Gate record: .workflow/records/2240-feat-2240-packaging.json
- Checklist: docs/planning/adr-054-spec3-explore-session-checklist.md

## Required Rules

Read and follow:

- The GitHub issue `#2240`.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/new-feature.md
- docs/ai-developer/personas/implementer.md
- **docs/specs/adr-054-explore-session.md — T-014 and the second half of T-015 of §4.3, and FR-037 to FR-043 and FR-046 are yours. Read all of it.**
- **docs/specs/adr-054-notebook-dependency-analysis.md — the analysis you
  consume. Already implemented and merged into your branch's history.**
- docs/adr/ADR-054.md for the surrounding design.

## Scope

You own only:

- `src/scistudio/explore/packaging.py`
- `src/scistudio/blocks/code/backends/notebook.py`
- `tests/explore/test_packaged_block.py`
- `.workflow/records/2240-feat-2240-packaging.json`

You must not touch:

- `src/scistudio/blocks/base/interactive.py` and
  `src/scistudio/engine/scheduler/_dispatch.py` — agent S3-A4 owns the
  `on_new_input` setting and the remap policy. You supply the packaged block's
  prompt and decision through the seam that agent left; if the seam is missing,
  report it rather than editing those files.
- Every other explore module, every frontend path, `docs/specs/**`,
  `docs/architecture/**`.

If you need an out-of-scope path, stop and report back. Do not edit it.

## Coordination

- You are not alone in this codebase. Several agents are implementing other
  modules of the same spec in separate worktrees. The write sets are disjoint by
  design; keep to yours.
- MUST work only on your assigned branch and worktree.
- MUST NOT use `pip install -e .`. `PYTHONPATH=./src` on every python call.
- Do not revert or overwrite other agents' work.
- **Do not open a pull request.** Commit, push your branch, and report. The
  manager integrates every branch and runs the pre-PR gate once.
- MUST NOT merge anything.
- Edit only your checklist rows (your row in §6, your line in §7.3).

## TODO And Deferral Rule

Use `TODO(#NNN): <reason>` citing an issue, ADR, spec, or ticket for anything
deferred. No hidden V1, MVP, or later work.

Known deferred items:

- The Explore tab that a packaged block's ask pause opens is the
  explore-frontend spec's and is out of scope for this whole spec. Do not write
  a TODO for it; the spec already records it as another spec's work.

## Work To Do

Implement T-014 and the second half of T-015 of the spec's §4.3 sequence. Read
§4.1's paragraphs "Packaging produces a Code Block, because that is what it is"
and "Asking reuses the pause that exists" first.

1. **The checks that refuse.** A notebook with a stale cell in its slice, or a
   call to an interactive block, is refused, and the refusal **names the cells**
   (FR-037, FR-038). Each refusal condition needs its own fixture.
2. **The generated declaration.** A Python file in the project's blocks
   directory defining a `CodeBlock` subclass with the ports and the notebook as
   its script, plus a copy of the notebook beside it (FR-039). The tier-1 scan
   is **not recursive**, which is why the declaration sits directly in the
   blocks directory rather than in a subdirectory. Ports come from the
   notebook's `scistudio.input` and `scistudio.output` declarations, read from
   the dependency analysis (FR-041).
3. **Cell selection in the notebook backend** (FR-040). A Code Block already
   runs a `.ipynb` through `nbconvert` from the project root with exchange
   folders for its ports. The one addition is materialising the graph's backward
   slice as a temporary notebook so `nbconvert` runs **exactly** the selected
   cells and nothing else. The backend must ignore the selection when it is
   absent, so existing Code Blocks are unaffected.
4. **Reopening from the node and repackaging** (FR-042, FR-043).
5. **The ask pause** (FR-046): a packaged block set to ask raises a prompt
   naming the notebook and the run's inputs, and the decision it remembers is a
   notebook commit.
6. Apply the repository's stability markers to every public symbol you add.

## Required Tests And Checks

- `PYTHONPATH=./src python -m pytest tests/explore/test_packaged_block.py -q`
- `PYTHONPATH=./src python -m pytest tests/blocks/code -q` — you changed the
  notebook backend; prove existing Code Blocks are unaffected.
- End to end is the acceptance bar: a fixture notebook is packaged, the
  generated block is **discovered by the registry**, a workflow runs it, and its
  outputs equal the session's. Not a unit test of the generator.
- The packaged block runs the slice and **not** the whole notebook — assert on
  which cells executed, for instance through a side effect in an excluded cell.
- Each refusal condition has its own fixture and its message names the cells.
- `PYTHONPATH=./src python -m scistudio.qa.governance.gate_record check --mode local --base origin/track/adr-054-spec3-explore-session --head HEAD`
- Record `--base-ref origin/track/adr-054-spec3-explore-session` at
  `gate_record init` and pass
  `--base origin/track/adr-054-spec3-explore-session` to every `check`. Without
  it the gate measures your branch against `origin/main`, reads spec 2's
  commits as yours, and reports false out-of-scope findings.
- Docs: `--docs-na "spec:the governing spec docs/specs/adr-054-explore-session.md landed in PR 2228 and this change implements one of its tasks without adding a separately documented surface"` unless your task says otherwise.
- `git add -A` before every commit. Trailers on every commit: `Gate-Record:`,
  `Task-Kind: feature`, `Issue: #2240`, `Assisted-by: Claude:claude-opus-5`.

## Output Required

- Changed file paths.
- Exact pytest summary lines.
- Your branch head sha.
- Checklist rows updated.
- Any blocker, scope issue, or spec ambiguity.

## Stop Conditions

Stop and report back if you need an out-of-scope file, the task conflicts with
AGENTS.md or the spec, checks fail for unclear reasons, another agent's work
blocks yours, you cannot add the required tests, or the spec is ambiguous in a
way that changes a contract another agent builds against.
```
