[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-054 spec 2, the notebook dependency analysis,
  exactly per `docs/specs/adr-054-notebook-dependency-analysis.md`.
- Task kind: `feature`
- Persona: `implementer`
- Issue: #2231
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2231
- Umbrella PR: (recorded in the manager checklist; `[DO NOT MERGE]`)
- Protected branch: `main`
- Umbrella branch: `track/adr-054-spec2-dependency-analysis`
- Agent branch: `feat/2231-dep-analysis-impl`
- Agent worktree: `C:/Users/jiazh/workspace/scistudio/.worktrees/spec2-impl`
- Gate record: `.workflow/records/2231-feat-2231-dep-analysis-impl.json`
  (created by your `init`)
- Checklist: `docs/planning/adr-054-spec2-dependency-analysis-checklist.md`

## Required Rules

Read and follow (from your worktree, which is at origin/main + the manager
checklist):

- The GitHub issue `#2231` (`gh issue view 2231`).
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/new-feature.md
- docs/ai-developer/personas/implementer.md
- The spec: `docs/specs/adr-054-notebook-dependency-analysis.md` — this is
  your contract. Read it fully before writing any code.
- ADR-054 §6.1 and §6.2 in `docs/adr/ADR-054.md` for the design rationale.

## Scope

You own only:

- `src/scistudio/explore/__init__.py` (create)
- `src/scistudio/explore/dependency_analysis.py` (create)
- `src/scistudio/explore/fingerprint.py` (create)
- `tests/architecture/test_layer_deps.py` (modify: add the `explore`
  subsystem to the enumeration and assert the FR-035 import constraint)
- Your own gate ledger under `.workflow/records/`

You must not touch:

- `tests/explore/**` — a separately dispatched test engineer owns the entire
  test suite and fixtures. Do NOT create `tests/explore/`.
- Any other path. In particular nothing under `frontend/`, `desktop/`,
  `docs/ai-developer/**`, or existing `src/scistudio/**` modules outside
  `explore/`.

If you need an out-of-scope path, stop and report back. Do not edit it.

## Coordination

- You are not alone in this codebase. Another dispatch (spec 1, panel
  contract) is in flight on other branches; do not revert or overwrite
  anything you did not write.
- MUST work only on your assigned branch.
- MUST work only in your assigned worktree.
- MUST NOT use `pip install -e .`.
- Do not broaden scope.
- Do NOT open a PR. The manager integrates your branch into the umbrella
  branch. Commit and push your branch and report the head SHA.
- Edit only your checklist rows (none — report to the manager instead).
- Python environment: the shared venv carries a STALE editable `.pth`
  pointing at a different checkout. Every Python invocation MUST be run from
  your worktree root as
  `PYTHONPATH="$PWD/src" ../../.venv/Scripts/python.exe -m ...`
  (pytest, mypy, gate_record, everything). Verify with
  `python -c "import scistudio; print(scistudio.__file__)"` that it resolves
  inside YOUR worktree before trusting any test result.

## TODO And Deferral Rule

Deferred work must be tracked in the repo.
Use `TODO(#NNN): <reason>` and cite an issue, ADR, spec, or follow-up ticket.
Do not leave hidden V1, MVP, or later work.

Known deferred items:

- N/A

## Work To Do

Implement the spec's §4.3 sequence T-001 through T-009 and T-011
(production code only; T-010, the test harness and fixtures, belongs to the
test engineer):

1. Create the `scistudio.explore` package; add it to the layer enumeration in
   `tests/architecture/test_layer_deps.py` with the FR-035 import constraint
   (stdlib only; numpy/pandas lazily inside the fingerprint only; nothing
   from SciStudio beyond stability markers).
2. `dependency_analysis.py`: per-cell static facts via `symtable` + a single
   `ast` walk — assigned names (all forms in FR-005), read names (FR-006),
   output declarations / input declarations / block calls (FR-008..FR-010),
   magic/shell stripping and opaque-cell and syntax-error flags (FR-011,
   FR-012), star imports and `%run` (FR-013).
3. The graph over enabled cells: nearest-enabled-definer edges with origins
   (FR-014, FR-015, FR-019), version nodes (FR-016), determinism (FR-017),
   linear build (FR-018).
4. The four queries: downstream set (FR-020), backward slice with unresolved
   reads (FR-021), changed set as static-union-observation (FR-022),
   written-order definer (FR-023).
5. `fingerprint.py`: fingerprint function with declared size bound and
   strided sampling (FR-024, FR-025), namespace comparison (FR-026),
   source-hash-keyed observation record with invalidation (FR-027),
   unpredicted-change diagnostic (FR-028), unobservable reporting (FR-029),
   union-only semantics (FR-030).
6. The cell-metadata codec under the `scistudio` metadata key, JSON-only,
   unknown keys preserved, edges never stored, hash-mismatch re-analysis
   (FR-031..FR-034).
7. The closed `AnalysisFlag` enumeration with exactly the flags in FR-036.
8. Stability markers on every public symbol per T-011 (mirror the convention
   used by neighboring subsystems; `scistudio.explore` is NOT a canonical
   public root — do not touch the frozen surface inventory).
9. Self-verify with throwaway scripts under `.workflow/local/` (never
   committed) — but do not write committed tests; that is the test
   engineer's scope.

The spec is the contract: honor every FR and the Key Entities section's
attribute lists. Where the spec is silent, choose the simplest design that
satisfies the FRs, and record assumptions in your final report.

## Required Tests And Checks

- `tests/architecture/test_layer_deps.py` must pass:
  `PYTHONPATH="$PWD/src" ../../.venv/Scripts/python.exe -m pytest tests/architecture/test_layer_deps.py -x`
- Gate ledger (run from your worktree root, with the PYTHONPATH prefix above):
  - `python -m scistudio.qa.governance.gate_record init --task-kind feature --persona implementer --runtime kimi --branch feat/2231-dep-analysis-impl --base-ref track/adr-054-spec2-dependency-analysis --issue 2231 --owner-directive "Implement ADR-054 spec 2 production code per docs/specs/adr-054-notebook-dependency-analysis.md" --include "src/scistudio/explore/**" --include "tests/architecture/test_layer_deps.py"`
  - Record the plan, docs (this spec/ADR already exist — record
    `--docs-updated docs/specs/adr-054-notebook-dependency-analysis.md` is
    wrong; use `--docs-na` with a class rationale, e.g. the subsystem has no
    user-visible surface yet), and `--test-na "implementation-tests:tests owned by separately dispatched test engineer A-test per manager dispatch; see docs/planning/adr-054-spec2-dependency-analysis-checklist.md"`.
  - `python -m scistudio.qa.governance.gate_record check --mode local --base origin/track/adr-054-spec2-dependency-analysis --head HEAD`
    before reporting done. Follow its repair hints. Your branch is an
    intermediate integration branch; the manager owns final PR readiness.
- Commits MUST carry the AI trailers (Gate-Record, Task-Kind, Issue,
  Assisted-by) and be Conventional Commits.
- Sentrux MCP/CLI: record N/A in your ledger if unavailable.

## Output Required

Before reporting done, provide:

- Changed file paths.
- Commands run and results (layer test, gate check).
- Your gate ledger path and head commit SHA.
- Any spec ambiguity you resolved and how.
- Any blocker or scope issue.

## Stop Conditions

Stop and report back if:

- You need an out-of-scope file.
- The task conflicts with AGENTS.md, ADR, spec, or gate record.
- Local checks fail for unclear reasons.
- Another agent's work blocks yours.
- The spec and the existing codebase disagree on a constraint you cannot
  resolve locally (e.g. the layer test's enumeration mechanism).
