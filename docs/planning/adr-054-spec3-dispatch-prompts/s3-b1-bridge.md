---
title: "ADR-054 Spec 3 Dispatch Prompt: S3-B1 The Kernel Bridge, The Helpers, And Variable Windows"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# S3-B1 — The Kernel Bridge, The Helpers, And Variable Windows

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
- Agent branch: feat/2240-kernel-bridge
- Agent worktree: C:/Users/jiazh/workspace/SciStudio/.worktrees/s3-b1-bridge
- Gate record: .workflow/records/2240-feat-2240-kernel-bridge.json
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
- **docs/specs/adr-054-explore-session.md — T-003, T-004, T-010, T-011 of §4.3, and FR-008 to FR-012, FR-034, FR-049, FR-050 are yours. Read all of it.**
- **docs/specs/adr-054-notebook-dependency-analysis.md — the analysis you
  consume. Already implemented and merged into your branch's history.**
- docs/adr/ADR-054.md for the surrounding design.

## Scope

You own only:

- `src/scistudio/explore/kernel_bridge.py`
- `src/scistudio/explore/notebook_api.py`
- `src/scistudio/__init__.py` — the three helpers, exposed lazily
- `src/scistudio/core/lineage/environment.py` — snapshot by reference (FR-034)
- `tests/explore/test_kernel_bridge.py`
- `tests/explore/test_notebook_api.py`
- `.workflow/records/2240-feat-2240-kernel-bridge.json`

You must not touch:

- `src/scistudio/explore/kernel.py` — agent S3-A2 wrote it; you call it, you do
  not change it. If it is missing a capability you need, report that rather than
  adding it yourself.
- `src/scistudio/explore/session.py`, `queue.py`, `packaging.py`,
  `block_call.py`, `notebook.py`, `lineage.py` — other agents own them.
- Every other file under `src/scistudio/core/lineage/` — agent S3-C1 owns them.
- Every frontend path, `docs/specs/**`, `docs/architecture/**`.

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

- The queue that calls your fingerprint hook around each run, the session that
  owns the kernel, and the panel that renders your window are other agents'
  tasks and are **not** deferred work. Do not write TODOs for them.

## Work To Do

Implement T-003, T-004, T-010, and T-011 of the spec's §4.3 sequence.

1. **T-003, the bridge.** A small module the service injects at kernel start. A
   bridge call executes on the kernel's execute channel **with its output
   suppressed**, so nothing appears as a cell (§4.1, "The bridge, and why panels
   read through the kernel"). It answers: namespace fingerprints, bindings,
   memory. Fingerprints use `scistudio.explore.fingerprint` from the
   dependency-analysis spec, imported **inside the kernel**.
2. **T-004, the three helpers.** `scistudio.input`, `scistudio.output`, and
   `scistudio.load`, with mode selection driven by an environment variable the
   launcher sets (FR-010, FR-011). In session mode they speak to the bridge:
   `input` returns the bound run's port artefact reference, `load` resolves it
   through the storage layer, `output` registers names. In packaged mode they
   speak to the Code Block's exchange folders. **The same notebook lines must
   work unchanged in both modes** — that is the whole point; test it.
3. **T-010, variable windows.** A window request wraps the native object into
   its SciStudio type by construction from data and runs the existing preview
   provider for that type, so a table window in a session is produced by the
   same code that produces it in the workflow preview. Find that provider; do
   not write a second renderer.
4. **T-011, `%pip` detection and environment snapshot by reference.** Detect an
   install through the kernel and re-snapshot the environment, stored once by
   reference rather than copied (FR-034).
5. Expose the three helpers **lazily** at `scistudio`'s top level so importing
   `scistudio` does not drag the explore subsystem in. Read how the package
   already does lazy exposure rather than inventing a mechanism.
6. Apply the repository's stability markers to every public symbol you add.

## Required Tests And Checks

- `PYTHONPATH=./src python -m pytest tests/explore/test_kernel_bridge.py tests/explore/test_notebook_api.py -q`
- The test that matters most: the same fixture notebook runs in session mode and
  in packaged mode with identical source and produces the same outputs.
- A bridge call must produce **no cell** — assert on the kernel's message
  stream, not on a comment saying output is suppressed.
- A window equals the preview provider's output for the same object. Compare
  against the provider directly rather than against a golden file.
- The environment snapshot changes after an install and is stored once.
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
