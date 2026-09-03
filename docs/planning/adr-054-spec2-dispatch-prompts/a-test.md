[DISPATCH-TEMPLATE-V1: test_engineer]

## Task Identity

- Repository: SciStudio
- Owner request: Write the adversarial test suite for the notebook dependency
  analysis subsystem, deriving every expectation from the spec and the actual
  behavior of the code you can read — not from anyone's claims about it.
- Task kind: `feature`
- Persona: `test_engineer`
- Issue: #2231
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2231
- Protected branch: `main`
- Umbrella branch: `track/adr-054-spec2-dependency-analysis`
- Agent branch: `test/2231-dep-analysis-adversarial`
- Agent worktree: `C:/Users/jiazh/workspace/scistudio/.worktrees/spec2-test`
- Gate record: `.workflow/records/2231-test-2231-dep-analysis-adversarial.json`
  (created by your `init`)
- Checklist: `docs/planning/adr-054-spec2-dependency-analysis-checklist.md`
  (read-only for you; the manager edits your rows)

## Context Limits (owner-directed: no-context, adversarial)

You must not read or use:

- Manager dispatch prompts for other agents
  (`docs/planning/adr-054-spec2-dispatch-prompts/a-impl.md`, `a-audit.md`).
- PR descriptions, PR comments, or commit-message claims about what the
  implementation does.
- Any chat or manager summary of the implementation.

You may read only:

- Repository docs, including the spec
  `docs/specs/adr-054-notebook-dependency-analysis.md` (your contract — read
  it fully) and ADR-054 §6.1/§6.2 in `docs/adr/ADR-054.md`.
- Repository code, including the implementation under
  `src/scistudio/explore/`.
- Tests and committed generated facts.
- Tool output from commands you run yourself.

## Required Rules

Read and follow:

- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/test-engineering.md
- docs/ai-developer/personas/test-engineer.md

## Scope

You own only:

- `tests/explore/test_dependency_analysis.py` (create)
- `tests/explore/test_fingerprint.py` (create)
- `tests/explore/test_analysis_differential.py` (create)
- `tests/explore/fixtures/**` (create; fixture notebooks as `.ipynb` JSON,
  including the six-cell notebook of Story 2 and its three mutation variants)
- Your own gate ledger under `.workflow/records/`

You must not touch:

- All production code (`src/**`). This is absolute for your dispatch: when a
  test you wrote exposes a production defect, record it as a finding in your
  final report with the reproducing test and stop there — the fix lands
  through another agent.
- `tests/architecture/test_layer_deps.py` (owned by the implementer).
- Any other path.

If you need an out-of-scope path, stop and report back. Do not edit it.

## Coordination

- You are not alone in this codebase. Do not revert or overwrite anything you
  did not write.
- MUST work only on your assigned branch.
- MUST work only in your assigned worktree.
- MUST NOT use `pip install -e .`.
- Do NOT open a PR. The manager integrates your branch. Commit and push and
  report the head SHA.
- Python environment: the shared venv carries a STALE editable `.pth`
  pointing at a different checkout. Every Python invocation MUST be run from
  your worktree root as
  `PYTHONPATH="$PWD/src" ../../.venv/Scripts/python.exe -m ...`
  Verify `import scistudio` resolves inside YOUR worktree before trusting any
  test result.

## TODO And Deferral Rule

Deferred work must be tracked in the repo.
Use `TODO(#NNN): <reason>` and cite an issue, ADR, spec, or follow-up ticket.
Do not leave hidden V1, MVP, or later work.

Known deferred items:

- N/A

## Work To Do

Write the test suite the spec's §4.2 assigns to `tests/explore/**`, and make
it adversarial: your job is to BREAK the implementation, not to confirm it.
Derive every expected value from the spec's FRs, user stories, edge cases,
and success criteria — then check what the code actually does.

1. `test_dependency_analysis.py` — one test per assignment form in FR-005
   (assignment targets incl. tuple/star/annotated, walrus at module scope,
   augmented assignment, `for`/`with ... as`/`except ... as` targets,
   imports, function/class defs, `del`; nested-scope binds must NOT count);
   module-scope reads incl. nested scopes (FR-006); a cell that assigns and
   reads the same name (read still recorded); output/input/block-call
   declarations (FR-008..FR-010, incl. non-literal block call flagged);
   magic/shell stripping, opaque `%%` cells, syntax errors, star imports and
   `%run` (FR-011..FR-013); the graph rules (nearest enabled definer, never
   self, builtins excluded from unresolved, disabled cells absent, version
   nodes agree with cell edges, edge origins — FR-014..FR-019); the four
   queries (FR-020..FR-023) over fixtures you construct; the Story 1 A/B/C
   definer scenario (SC-013); the enabled/disable toggle scenarios (Story 4,
   SC-004).
2. `test_fingerprint.py` — per-type mutation detection and unchanged
   equality for numpy arrays, pandas frames/series, lists, tuples, dicts,
   sets, strings, bytes, numbers (SC-006); the declared size bound and
   strided sampling above it (FR-025); identity fallback reported
   unobservable (FR-024, FR-029); namespace comparison: changed / appeared /
   disappeared (FR-026); source-hash invalidation (FR-027); union-only
   semantics — an observation never removes a static edge (FR-030, SC-008);
   the unpredicted-change diagnostic (FR-028); a timed check against the
   declared bound on the largest fixture namespace (SC-007).
3. `test_analysis_differential.py` — the differential test of §4.4: execute
   each fixture notebook cell by cell in a subprocess with the observation
   running, record declared outputs; then execute only the backward slice of
   the output cells on a fresh namespace; the outputs MUST be equal (SC-003).
   Cover the in-place, subscript, library-function, and helper variants
   (Story 2). Include the SC-010 timed test over a generated 500-cell
   notebook.
4. The codec round trip: analyse from source, add observations, write records
   to cell metadata, load, rebuild — the graphs must be equal; a record whose
   source hash no longer matches is discarded and recomputed; unknown keys
   under the `scistudio` metadata key survive a rewrite (FR-031..FR-034,
   SC-009).

Adversarial guidance (at minimum probe these):

- The spec's own Edge Cases section — every bullet is a test.
- Statement-order traps: `df = load(); df.head()` must still record the read
  (the spec demands the extra edge); `df = df.dropna()` must resolve the
  read upward, never to the cell itself.
- `a, b = f()`, starred targets, annotated assignments, walrus at module
  scope vs inside a comprehension.
- A cell that is only `%matplotlib inline`; a cell mixing a magic line with
  real code; `%%time` followed by assignments (must be opaque: assigns
  nothing).
- Unicode identifiers, comments containing `%`/`!`, indented lines starting
  with `%` after stripping (line's FIRST non-blank character rule).
- Empty cells, whitespace-only cells, a notebook of one cell.
- Fingerprint traps: NaN in arrays/frames, negative strides, object-dtype
  columns, dict ordering, sets, a list containing an unobservable object,
  mutation of a nested element (`d["k"].append(x)`), pandas copy-on-write
  behavior with pandas 3.
- A fingerprint above the bound: change one element inside the sampled
  stride and one outside it — assert what the spec's stated limit allows and
  nothing more.
- Observations keyed to a stale source hash must be discarded even when the
  record is otherwise valid JSON.
- The graph build must be deterministic: build twice from the same inputs
  and compare.

Where the spec and the code disagree, the spec wins: write the test the spec
demands, let it fail, and report the failure as a finding with the FR number.

## Required Tests And Checks

- Your suite must run green against the implementation OR every failure must
  be a spec-backed finding in your report:
  `PYTHONPATH="$PWD/src" ../../.venv/Scripts/python.exe -m pytest tests/explore -x -q`
- Gate ledger (from your worktree root, with the PYTHONPATH prefix):
  - `python -m scistudio.qa.governance.gate_record init --task-kind feature --persona test_engineer --runtime kimi --branch test/2231-dep-analysis-adversarial --base-ref feat/2231-dep-analysis-impl --issue 2231 --owner-directive "Adversarial no-context test suite for ADR-054 spec 2 per docs/specs/adr-054-notebook-dependency-analysis.md" --include "tests/explore/**"`
  - Record the plan; tests are your deliverable so record each
    `--test-path`; docs: `--docs-na "user-docs:test-only dispatch, no behavior or contract change by these files"`.
  - `python -m scistudio.qa.governance.gate_record check --mode local --base origin/feat/2231-dep-analysis-impl --head HEAD`
    before reporting done. Follow its repair hints. Your branch is an
    intermediate integration branch; the manager owns final PR readiness.
- Commits MUST carry the AI trailers (Gate-Record, Task-Kind, Issue,
  Assisted-by) and be Conventional Commits.

## Output Required

Before reporting done, provide:

- Changed file paths.
- Test counts and the full pass/fail summary.
- Every failure that is a spec-backed production finding, with the FR number
  and the reproducing test name — this is the point of your dispatch.
- Your gate ledger path and head commit SHA.
- Any spec ambiguity you had to resolve to write an expectation, and how.
- Any blocker or scope issue.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file (including production code fixes).
- The task conflicts with AGENTS.md, ADR, spec, or gate record.
- Tests fail for reasons you cannot attribute to either the spec or the
  implementation.
- The implementation is missing a surface the spec requires you to test
  (report the gap; write the failing test against the spec's contract).
