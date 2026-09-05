---
title: "ADR-054 Spec 2 Dispatch Prompt: S2-D1 Adversarial Test Engineering"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# S2-D1 — Adversarial Test Engineering

Filled from `docs/ai-developer/templates/agent-dispatch-prompt-template.md`.

```markdown
[DISPATCH-TEMPLATE-V1: test_engineer]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-054 spec 2 in full, with a final adversarial test engineer.
- Task kind: feature
- Persona: test_engineer
- Issue: #2231
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2231
- Umbrella PR: #2232 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-054-spec2-dependency-analysis
- Agent branch: test/2231-adversarial
- Agent worktree: C:/Users/jiazh/workspace/SciStudio/.worktrees/s2-d1-adversarial
- Gate record: .workflow/records/2231-test-2231-adversarial.json
- Checklist: docs/planning/adr-054-spec2-dependency-analysis-checklist.md

## Required Rules

Read and follow:

- The GitHub issue `#2231`.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/test-engineering.md
- docs/ai-developer/personas/test-engineer.md
- **docs/specs/adr-054-notebook-dependency-analysis.md — all of it, especially
  §4.4 Verification Plan and §5 Success Criteria.**

## Scope

You own only:

- `tests/explore/test_analysis_differential.py`
- `tests/explore/fixtures/**`
- `tests/explore/test_adversarial_analysis.py`
- `.workflow/records/2231-test-2231-adversarial.json`

You must not touch:

- Every path under `src/`. Production code is out of scope for this persona.
- `tests/explore/test_dependency_analysis.py` and
  `tests/explore/test_fingerprint.py` — the implementers own those.
- `tests/architecture/**`.
- Every other path in the repository.

**When you find a defect, you write a failing test and report it. You do not
fix production code.** A fix agent handles the repairs. If a test you believe is
correct fails, that is your deliverable, not your problem to solve — but say
clearly in your report whether you believe the test or the product is wrong,
and why.

## Coordination

- MUST work only on your assigned branch and worktree.
- MUST NOT use `pip install -e .`. `PYTHONPATH=./src` on every python call.
- **Do not open a pull request.** Commit, push your branch, and report.
- Edit only your checklist rows (`S2-D1` in §6 and §7.3).

## TODO And Deferral Rule

Use `TODO(#NNN): <reason>` citing an issue, ADR, spec, or ticket for anything
deferred.

Known deferred items:

- N/A.

## Work To Do

You have two jobs. The second is the one that matters.

**Job one — T-010, the differential test.** Build the harness §4.4 describes.
Execute each fixture notebook cell by cell **in a subprocess** with the
observation running, record the declared outputs, then execute only the
backward slice of the output cells on a fresh namespace and record the outputs
again. The two MUST be equal. A difference means the slice omitted a cell whose
effect the outputs depend on, and it fails outright.

The fixtures MUST include the six-cell notebook of the spec's User Story 2 and
its three mutation variants, plus the in-place, subscript, library-function, and
helper variants, so each is proven caught by the observation rather than
assumed. SC-002 and SC-003 are the acceptance bar.

**Job two — break it.** Everything above is what the implementers already knew
they would be measured on. Your value is the tests nobody wrote because nobody
wanted the answer. Attack, at minimum:

- **Assertions weaker than the coverage they claim.** Read the existing tests in
  `tests/explore/` and find cases where a fixture is stubbed such that the
  failure path is never reached, or where a parametrised test passes for every
  parameter because the interesting branch is never taken. This exact shape has
  bitten this repository before.
- **The union invariant (FR-002, FR-030).** Construct a case where an
  observation would remove an edge if the code took the observation as
  replacement rather than union.
- **The nearest-enabled-definer rule (FR-015).** Disabled cells between reader
  and definer, a definer below the reader, a self-read, a name defined twice,
  a read of a builtin, a read shadowing a builtin.
- **The flags (FR-011 to FR-013, FR-036).** A cell that is only a magic line. A
  `%%` cell magic whose body is valid Python. A syntax error on the last line. A
  star import combined with an unresolved read. `%run`. A cell that is empty. A
  cell that is only a comment. Non-ASCII identifiers. A very long cell.
- **The source-hash keying (FR-027).** Whitespace-only edits, an edit that
  restores the original source, two cells with identical source.
- **The fingerprint's honesty (FR-024, FR-029).** An object whose `__eq__` lies.
  A numpy view versus its base. A pandas frame with object columns holding
  unhashable values. A NaN. A `-0.0`. An object above the size bound mutated
  *outside* the sampled positions — the spec admits this is missed; write the
  test that documents the admitted miss rather than pretending it is caught.
- **Determinism (FR-017).** Build the same graph twice from the same inputs in
  a fresh process and compare, including iteration order of every collection
  the API exposes.
- **Purity (FR-004).** Assert the analysis touches no filesystem and executes
  nothing — a test that monkeypatches `open` and `exec` and fails if either is
  reached is worth more than a comment saying the module is pure.

## Required Tests And Checks

- `PYTHONPATH=./src python -m pytest tests/explore -q`
- Report the exact summary line, and list every test you added that **fails**
  against the current implementation, with the reason you believe it should
  pass.
- Measure the analysis on a generated notebook of several hundred cells and
  record the number against SC-010.
- `PYTHONPATH=./src python -m scistudio.qa.governance.gate_record check --mode local --base origin/track/adr-054-spec2-dependency-analysis --head HEAD`
- Record `--base-ref origin/track/adr-054-spec2-dependency-analysis` at `init`.
- Docs N/A: `--docs-na "spec:test-only change against the spec that landed in PR 2228"`.
- `git add -A` before every commit. Trailers: `Gate-Record:`,
  `Task-Kind: feature`, `Issue: #2231`, `Assisted-by: Claude:claude-opus-5`.

## Output Required

- Changed file paths.
- Exact pytest summary line.
- **A findings list**: every defect found, its severity (P1 blocks, P2 should
  fix, P3 nice to have), the failing test that proves it, and whether you
  believe the test or the product is wrong.
- The measured analysis cost against SC-010.
- Your branch head sha.
- Checklist rows updated.

## Stop Conditions

Stop and report back if you need to edit production code, the spec is ambiguous
about what the correct behaviour is, or the implementation is missing entirely.
```
