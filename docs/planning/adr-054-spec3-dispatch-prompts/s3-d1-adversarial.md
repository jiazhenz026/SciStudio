---
title: "ADR-054 Spec 3 Dispatch Prompt: S3-D1 Adversarial Test Engineering"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# S3-D1 — Adversarial Test Engineering

Filled from `docs/ai-developer/templates/agent-dispatch-prompt-template.md`.

```markdown
[DISPATCH-TEMPLATE-V1: test_engineer]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-054 spec 3 in full, with a final adversarial test engineer.
- Task kind: feature
- Persona: test_engineer
- Issue: #2240
- Umbrella PR: #2241 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-054-spec3-explore-session
- Agent branch: test/2240-adversarial
- Agent worktree: C:/Users/jiazh/workspace/SciStudio/.worktrees/s3-d1-adversarial
- Gate record: .workflow/records/2240-test-2240-adversarial.json
- Checklist: docs/planning/adr-054-spec3-explore-session-checklist.md

## Required Rules

- The GitHub issue `#2240`.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/test-engineering.md
- docs/ai-developer/personas/test-engineer.md
- **docs/specs/adr-054-explore-session.md — all of it, especially §2 User
  Scenarios, §4.4 Verification Plan, and §5 Success Criteria.**

## Scope

You own only:

- `tests/explore/test_adversarial_session.py`
- `tests/explore/fixtures/**`
- `tests/api/test_explore_routes.py` — additions only
- `.workflow/records/2240-test-2240-adversarial.json`

You must not touch:

- Every path under `src/`. Production code is out of scope for this persona.
- The other agents' test files, except `tests/api/test_explore_routes.py` where
  you add and never rewrite.
- Every other path.

**When you find a defect, you write a failing test and report it. You do not fix
production code.** Say clearly whether you believe the test or the product is
wrong, and why.

## Coordination

- MUST work only on your assigned branch and worktree.
- MUST NOT use `pip install -e .`. `PYTHONPATH=./src` on every python call.
- **Do not open a pull request.** Commit, push your branch, and report.
- Edit only your checklist rows (`S3-D1` in §6 and §7.3).

## TODO And Deferral Rule

Use `TODO(#NNN): <reason>` citing an issue for anything deferred.

## Work To Do

Your job is to break this. The implementers already wrote the tests they knew
they would be measured on; your value is the ones nobody wanted the answer to.
Attack, at minimum:

- **The interrupt (ADR-054 §5.2).** This is one of two blockers the ADR names.
  Run a real kernel, run an infinite loop, interrupt it, and assert the process
  is alive and responsive afterwards. If the existing test mocks the kernel,
  that is a finding by itself: a mocked kernel passes a test a real interrupt
  fails.
- **Kernel lifecycle leaks.** A test that spawns a kernel and fails must still
  kill it. Find the ones that do not. Then: a kernel whose process is killed
  from outside, a kernel that never starts, two sessions on one branch, a branch
  switch mid-execution.
- **The marks never execute anything.** Assert, over the A, B, C fixture and the
  six-cell fixture, the exact set of cells each control enqueues — and assert
  that marking alone enqueues nothing. Then try to find an input where
  run-with-upstream's skip rule runs a cell the person did not name.
- **The admission whitelist.** Every refused statement form, plus the ones
  nobody thought of: a lambda, a comprehension with a side effect, a decorator, a
  walrus, a string that contains a newline and a second statement, a semicolon,
  a `__import__`, an f-string with an embedded call.
- **Commits stay off the execution path.** After N cell runs: `git status` is
  clean, the branch index is unchanged, the branch log has none of them, and the
  working tree the person is editing is untouched. Then: a cell run while a
  commit is in flight, two runs whose commits race, a run whose notebook changes
  between execution and commit — §4.1 promises the commit carries the notebook
  *as captured at execution time*, so prove a later edit cannot change it.
- **Packaging refusals.** A stale cell in the slice, a call to an interactive
  block, a notebook with no declared outputs, a declared output no cell binds, a
  notebook whose slice is empty, a repackage over an edited notebook.
- **The packaged block runs the slice and nothing else.** Put a side effect in an
  excluded cell and assert it did not happen.
- **`on_new_input` defaults preserve behaviour.** An existing authored
  interactive block with no setting behaves exactly as it did before.
- **Lineage across the boundary.** An object produced in a session and consumed
  by a workflow run resolves both ways; a packaged block's run carries the
  notebook commit.
- **The API's failure shapes.** Every route with a missing session, a closed
  session, a dead kernel, and a malformed body. A bare 500 that leaves an orphan
  behind is a defect shape this repository has shipped before — hunt it.
- **Assertions weaker than the coverage they claim.** Read every test the
  implementers wrote. Find the parametrised ones that pass for every parameter
  because a fixture stubs the failing path. Prove it by breaking the production
  code in a scratch copy and seeing which tests stay green.

## Required Tests And Checks

- `PYTHONPATH=./src python -m pytest tests/explore tests/api/test_explore_routes.py -q`
- Every process-spawning test carries the repository's serial marker and kills
  what it started, including on failure.
- `PYTHONPATH=./src python -m scistudio.qa.governance.gate_record check --mode local --base origin/track/adr-054-spec3-explore-session --head HEAD`
- Record `--base-ref origin/track/adr-054-spec3-explore-session` at `init`.
- Docs N/A: `--docs-na "spec:test-only change against the spec that landed in PR 2228"`.
- `git add -A` before every commit. Trailers: `Gate-Record:`,
  `Task-Kind: feature`, `Issue: #2240`, `Assisted-by: Claude:claude-opus-5`.

## Output Required

- Changed file paths.
- Exact pytest summary line.
- **A findings list**: every defect found, its severity (P1 / P2 / P3), the
  failing test that proves it, and whether you believe the test or the product
  is wrong.
- Which of the ADR's two named blockers — the interrupt, and bundled-runtime
  dependency drift — you were able to test for real, and which you could not.
- Your branch head sha.

## Stop Conditions

Stop and report back if you need to edit production code, the spec is ambiguous
about correct behaviour, or an implementation is missing entirely.
```
