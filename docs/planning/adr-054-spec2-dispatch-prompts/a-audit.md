[DISPATCH-TEMPLATE-V1: audit-no-context]

## Task Identity

- Repository: SciStudio
- Persona: `audit_reviewer`
- Audit mode: `no-context`
- Audit branch: `audit/2231-dep-analysis-no-context`
- Audit worktree: `C:/Users/jiazh/workspace/scistudio/.worktrees/spec2-audit`
- Allowed audit surfaces:
  - `docs/specs/adr-054-notebook-dependency-analysis.md`
  - `docs/adr/ADR-054.md` (especially §6.1, §6.2, §10.1, §11)
  - `src/scistudio/explore/**`
  - `tests/explore/**`
  - `tests/architecture/test_layer_deps.py`
  - `AGENTS.md`, `docs/ai-developer/rules.md`,
    `docs/ai-developer/personas/audit-reviewer.md`
- Audit report path: `docs/audit/2026-09-03-adr-054-spec2-no-context.md`

## Context Limits

You must not read or use:

- The current owner request.
- The current GitHub issue.
- Manager checklist files for the current work
  (`docs/planning/adr-054-spec2-dependency-analysis-checklist.md`).
- Dispatch prompts for the current work
  (`docs/planning/adr-054-spec2-dispatch-prompts/**`).
- PR descriptions, PR comments, or commit messages for the current work.
- Chat summaries or manager summaries of what changed.
- Gate ledgers under `.workflow/records/` for the current work.

You may read only:

- Repository docs.
- Repository code.
- Tests.
- Generated facts or audit outputs already committed in the repository.
- Tool output from commands you run yourself.

## Required Reading

Read and follow:

- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/personas/audit-reviewer.md
- Governing ADRs, specs, and docs discovered from the allowed audit surfaces
  (start from `docs/specs/adr-054-notebook-dependency-analysis.md` and
  ADR-054 §6.1/§6.2).

## Audit Goal

Independently check whether docs, code, tests, and declared contracts agree.
Do not assume what the manager intended to change.

Look for:

- FRs in the spec that the code does not implement or implements differently.
- Spec acceptance scenarios and edge cases with no corresponding test.
- Tests that assert behavior the spec forbids, or that are vacuous
  (assert nothing, tautologies, over-mocked).
- Code behavior not covered by the governing docs.
- Public symbols missing the stability markers the spec's T-011 requires.
- The FR-035 import constraint (stdlib only; numpy/pandas lazily inside the
  fingerprint only; nothing from SciStudio beyond stability markers).
- FR-036: the flag enumeration must contain exactly the seven named flags.
- FR-002: no rule may drop an edge the static estimate implies.
- The declared fingerprint bound and sampling actually being honored.
- Docs that claim behavior code does not implement.
- Generated docs edited by hand.

Be adversarial: write and run your own throwaway probes under
`.workflow/local/` (never committed) when reading the code is not enough to
settle a question.

## Coordination

- MUST work only on your assigned audit branch.
- MUST work only in your assigned audit worktree.
- MUST NOT use `pip install -e .`.
- MUST NOT merge any PR.
- MUST NOT edit implementation or test files. The audit report is your only
  committed write.
- MUST NOT edit the manager checklist.
- MUST write the audit report to the repository file named above.
- The manager merges the audit report into the final PR evidence path.
- Python environment: the shared venv carries a STALE editable `.pth`
  pointing at a different checkout. Every Python invocation MUST be run from
  your worktree root as
  `PYTHONPATH="$PWD/src" ../../.venv/Scripts/python.exe -m ...`
  Verify `import scistudio` resolves inside YOUR worktree before trusting any
  result.

## Checks

Run or verify:

- `PYTHONPATH="$PWD/src" ../../.venv/Scripts/python.exe -m pytest tests/explore tests/architecture/test_layer_deps.py -q`
- Your own probes under `.workflow/local/`.
- Sentrux MCP/CLI: record N/A in the report if unavailable.

## Output Required

- Audit report path.
- Commit that contains the audit report file (push your branch).
- Findings ordered by severity (P1/P2/P3), each with evidence from docs,
  code, tests, or tool output you produced.
- No statement about manager intent unless it is visible in repository docs.
- Recommendation: pass, pass-with-fixes, or block.

## Stop Conditions

Stop and report back if:

- You are asked to read issue/checklist/PR context.
- The audit requires hidden manager context.
- You need to edit implementation code.
