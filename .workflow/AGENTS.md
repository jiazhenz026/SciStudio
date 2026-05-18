---
scope: .workflow/**
parent_agents_md: ../AGENTS.md
applies_to_agents: [Claude, Codex, Cursor, Aider, Gemini]
governing_adrs: [42, 43]
---

# Workflow Gate Instructions

## Identity

`.workflow/**` owns the gate state machine and local workflow tracking files
that enforce traceable task execution.

## Policy

- Root `AGENTS.md` applies first.
- Treat `gate.py` and `schema.json` as workflow contract surfaces.
- Do not bypass or weaken gates to make a task convenient.
- Active state files are task/session state; avoid unrelated churn.

## Routing

| Trigger | Route | Reference |
|---|---|---|
| Gate procedure | Skill: `workflow-gate` | Temporary: `CLAUDE.md` Appendix A |
| Gate code/schema edit | ADR/spec review | ADR-042 workflow rules |
| Hook interaction | Scaffold hook files | `scripts/hooks/**` |

## Data classification

| Path | Class | Handling |
|---|---|---|
| `.workflow/gate.py`, `.workflow/schema.json` | internal | Workflow contract; review carefully |
| `.workflow/active/**` | internal | Session state; avoid unrelated edits |
| `.workflow/hooks/**` | internal | Local automation surface |

## Assessment rubric

| ID | Criterion | Verify with |
|---|---|---|
| WF1 | Gate stage ordering is preserved | Focused gate tests or manual status check |
| WF2 | Schema changes are documented | Diff review |
| WF3 | No workflow state unrelated to the task changed | `git diff -- .workflow` |

## Paths

| Boundary | Path | Reason |
|---|---|---|
| ✅ | `.workflow/AGENTS.md` | Layered instruction scaffold for this subtree |
| ⚠️ | `.workflow/gate.py`, `.workflow/schema.json` | Gate contract |
| ⚠️ | `.workflow/active/**`, `.workflow/hooks/**` | Runtime/session automation |
| 🚫 | Local secrets or credentials in workflow state | Secret material |
