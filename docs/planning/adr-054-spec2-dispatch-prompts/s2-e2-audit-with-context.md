---
title: "ADR-054 Spec 2 Dispatch Prompt: S2-E2 With-Context Audit"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# S2-E2 — With-Context Audit

Filled from
`docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`.

```markdown
[DISPATCH-TEMPLATE-V1: audit-with-context]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-054 spec 2 in full, restarting from scratch, with a final adversarial test engineer and a no-context auditor.
- Persona: audit_reviewer
- Audit mode: with-context
- Issue: #2231
- Umbrella PR: #2232 `[DO NOT MERGE]`
- Audit branch: audit/2231-with-context
- Audit worktree: C:/Users/jiazh/workspace/SciStudio/.worktrees/s2-e2-audit-wc
- Checklist: docs/planning/adr-054-spec2-dependency-analysis-checklist.md
- Audit report path: docs/audit/2026-09-04-adr-054-spec2-with-context.md

## Required Reading

- The GitHub issue `#2231`.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/personas/audit-reviewer.md
- docs/ai-developer/specific_rules/gated-workflow.md
- **docs/specs/adr-054-notebook-dependency-analysis.md**
- docs/adr/ADR-054.md §6.1 and §6.2
- The checklist and every dispatch prompt under
  `docs/planning/adr-054-spec2-dispatch-prompts/`.

## Audit Goal

Judge whether the delivered work is what the spec asked for, whether the
evidence claimed is real, and whether the gate record tells the truth.

Specifically:

1. **Requirement coverage.** Walk FR-001 to FR-036 and record, for each, the
   code that implements it and the test that proves it, or its absence. A
   requirement with an implementation and no test is a finding.
2. **Success criteria.** Walk SC-001 to SC-010 and record whether each was
   measured or merely asserted.
3. **Scope discipline.** `git diff origin/main...HEAD --stat` against the
   checklist's declared write sets. Anything outside is a finding.
4. **Gate evidence.** Does the gate ledger's claimed docs, tests, and checks
   match what the diff actually contains?
5. **The claim-versus-reality gap.** Where a commit message, checklist row, or
   prompt claims something was done, verify it independently. Do not accept a
   summary as evidence.

## Coordination

- MUST work only on your assigned audit branch and worktree.
- MUST NOT use `pip install -e .`. `PYTHONPATH=./src` on every python call.
- MUST NOT merge any PR.
- MUST NOT edit implementation files.
- MUST NOT edit the manager checklist.
- MUST write the audit report to the repository file named above and commit it.
- **Do not open a pull request.** Commit, push your branch, and report.

## Checks

- `PYTHONPATH=./src python -m pytest tests/explore tests/architecture/test_layer_deps.py -q`
- `PYTHONPATH=./src python -m ruff check src/scistudio/explore tests/explore`
- `PYTHONPATH=./src python -m mypy src/scistudio/explore`
- `PYTHONPATH=./src python -m scistudio.qa.governance.gate_record check --mode local --base origin/main --head HEAD`

## Output Required

- Audit report path and the commit containing it.
- An FR-by-FR coverage table and an SC-by-SC measurement table.
- Findings ordered by severity (P1 / P2 / P3) with evidence.
- Recommendation: pass, pass-with-fixes, or block.

## Stop Conditions

Stop and report back if you need to edit implementation code, or the
implementation is missing entirely.
```
