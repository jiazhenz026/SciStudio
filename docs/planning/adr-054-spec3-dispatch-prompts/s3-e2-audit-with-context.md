---
title: "ADR-054 Spec 3 Dispatch Prompt: S3-E2 With-Context Audit"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# S3-E2 — With-Context Audit

Filled from
`docs/ai-developer/templates/agent-dispatch-audit-with-context-prompt-template.md`.

```markdown
[DISPATCH-TEMPLATE-V1: audit-with-context]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-054 spec 3 in full, with a final adversarial test engineer and a no-context auditor.
- Persona: audit_reviewer
- Audit mode: with-context
- Issue: #2240
- Umbrella PR: #2241 `[DO NOT MERGE]`
- Audit branch: audit/2240-with-context
- Audit worktree: C:/Users/jiazh/workspace/SciStudio/.worktrees/s3-e2-audit-wc
- Checklist: docs/planning/adr-054-spec3-explore-session-checklist.md
- Audit report path: docs/audit/2026-09-04-adr-054-spec3-with-context.md

## Required Reading

- The GitHub issue `#2240`.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/personas/audit-reviewer.md
- docs/ai-developer/specific_rules/gated-workflow.md
- **docs/specs/adr-054-explore-session.md**
- docs/adr/ADR-054.md
- The checklist and every dispatch prompt under
  `docs/planning/adr-054-spec3-dispatch-prompts/`.

## Audit Goal

Judge whether the delivered work is what the spec asked for, whether the
evidence claimed is real, and whether the gate record tells the truth.

1. **Requirement coverage.** Walk FR-001 to FR-060 and record, for each, the
   code that implements it and the test that proves it, or its absence. A
   requirement with an implementation and no test is a finding.
2. **Success criteria.** Walk §5 and record whether each was measured or merely
   asserted.
3. **Protected paths.** Four core paths were changed under an
   `admin-approved:core-change` label on the promise that each change is
   additive. Verify that promise against the diff and against the pre-existing
   suites, one path at a time.
4. **Scope discipline.** `git diff origin/track/adr-054-spec2-dependency-analysis...HEAD --stat`
   against the checklist's declared write sets. Anything outside is a finding.
5. **Gate evidence.** Does the gate ledger's claimed docs, tests, and checks
   match what the diff actually contains?
6. **The claim-versus-reality gap.** Where a commit message, a checklist row, or
   a prompt claims something was done, verify it independently.

## Coordination

- MUST work only on your assigned audit branch and worktree.
- MUST NOT use `pip install -e .`. `PYTHONPATH=./src` on every python call.
- MUST NOT merge any PR.
- MUST NOT edit implementation files or the manager checklist.
- MUST write the audit report to the repository file named above and commit it.
- **Do not open a pull request.** Commit, push your branch, and report.

## Checks

- `PYTHONPATH=./src python -m pytest tests/explore tests/api/test_explore_routes.py tests/blocks tests/engine tests/core tests/architecture -q`
- `PYTHONPATH=./src python -m ruff check src/scistudio/explore`
- `PYTHONPATH=./src python -m mypy src/scistudio/explore`
- `PYTHONPATH=./src python -m scistudio.qa.governance.gate_record check --mode local --base origin/track/adr-054-spec2-dependency-analysis --head HEAD`

## Output Required

- Audit report path and the commit containing it.
- An FR-by-FR coverage table and a success-criteria measurement table.
- A protected-path table: path, what changed, whether additive, evidence.
- Findings ordered by severity (P1 / P2 / P3) with evidence.
- Recommendation: pass, pass-with-fixes, or block.

## Stop Conditions

Stop and report back if you need to edit implementation code, or an
implementation is missing entirely.
```
