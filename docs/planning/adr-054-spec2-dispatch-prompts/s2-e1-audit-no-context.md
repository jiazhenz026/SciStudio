---
title: "ADR-054 Spec 2 Dispatch Prompt: S2-E1 No-Context Audit"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# S2-E1 — No-Context Audit

Filled from
`docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`.

```markdown
[DISPATCH-TEMPLATE-V1: audit-no-context]

## Task Identity

- Repository: SciStudio
- Persona: audit_reviewer
- Audit mode: no-context
- Audit branch: audit/2231-no-context
- Audit worktree: C:/Users/jiazh/workspace/SciStudio/.worktrees/s2-e1-audit-nc
- Allowed audit surfaces:
  - `src/scistudio/explore/**`
  - `tests/explore/**`
  - `tests/architecture/test_layer_deps.py`
  - `docs/specs/adr-054-notebook-dependency-analysis.md`
  - `docs/adr/ADR-054.md`
  - Any repository document these lead you to.
- Audit report path: docs/audit/2026-09-04-explore-dependency-analysis-no-context.md

## Context Limits

You must not read or use:

- The current owner request.
- Any GitHub issue.
- Manager checklist files — specifically
  `docs/planning/adr-054-spec2-*` and `docs/planning/adr-054-spec3-*`.
- Dispatch prompts — the whole `docs/planning/adr-054-spec2-dispatch-prompts/`
  and `docs/planning/adr-054-spec3-dispatch-prompts/` directories.
- PR descriptions, PR comments, or commit messages for this work.
- Gate ledgers under `.workflow/records/`.
- Chat summaries or manager summaries of what changed.

Read the diff with `git diff origin/main...HEAD -- src tests` so you do not
incidentally read commit messages. You may read only: repository docs,
repository code, tests, committed generated facts, and tool output from
commands you run yourself.

## Required Reading

- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/personas/audit-reviewer.md
- The governing spec and ADR discovered from the allowed surfaces.

## Audit Goal

Independently check whether docs, code, tests, and declared contracts agree. Do
not assume what anyone intended to change.

Look for:

- Docs that claim behavior code does not implement.
- Code behavior not covered by the governing docs.
- Tests missing for documented contracts.
- ADR/spec governed paths that do not exist.
- Public signatures or schemas that drift from docs.
- Generated docs edited by hand.

Two failure shapes have been found in this repository before and are worth
hunting deliberately:

1. **An assertion weaker than the coverage it claims.** A parametrised test that
   passes for every parameter because a fixture stubs out the path that would
   fail. Run the tests, then break the production code deliberately in a scratch
   copy and see which tests actually notice.
2. **A requirement with a number in it that nobody measured.** The spec states
   cost bounds and success criteria with measurable outcomes. Check whether each
   was measured or merely asserted.

Go and run things. Do not audit by reading alone.

## Coordination

- MUST work only on your assigned audit branch and worktree.
- MUST NOT use `pip install -e .`. `PYTHONPATH=./src` on every python call.
- MUST NOT merge any PR.
- MUST NOT edit implementation files.
- MUST NOT edit any manager checklist.
- MUST write the audit report to the repository file named above and commit it.
- **Do not open a pull request.** Commit, push your branch, and report.

## Checks

Run or verify:

- `PYTHONPATH=./src python -m pytest tests/explore tests/architecture/test_layer_deps.py -q`
- `PYTHONPATH=./src python -m ruff check src/scistudio/explore tests/explore`
- `PYTHONPATH=./src python -m mypy src/scistudio/explore`
- `sentrux scan .` and `sentrux check .` if the CLI is available; otherwise
  record that it is unavailable.

## Output Required

- Audit report path.
- The commit that contains the audit report file.
- Findings ordered by severity (P1 / P2 / P3), each with evidence from docs,
  code, tests, or tool output you produced.
- No statement about anyone's intent unless it is visible in repository docs.
- Recommendation: pass, pass-with-fixes, or block.

## Stop Conditions

Stop and report back if you are asked to read issue/checklist/PR context, the
audit requires hidden context, or you need to edit implementation code.
```
