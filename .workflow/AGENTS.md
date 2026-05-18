---
scope: .workflow/**
parent_agents_md: AGENTS.md
applies_to_agents: [Claude, Codex, Cursor, Aider, Gemini]
governing_adrs: [42]
---

# .workflow/AGENTS.md — Gate state machine

## Scope

The `.workflow/gate.py` state machine and its on-disk state under `.workflow/state/`. The gate is the **single source of truth** for whether each of the 6 (legacy) / 7 (Workflow v2, shadow) workflow stages was completed.

## Policy

- The gate CLI is authoritative: agents cannot self-attest completion; only `gate.py advance` records count.
- State files under `.workflow/state/<task-id>/` are append-only event journals. Never hand-edit, never delete.
- Stage advancement order is fixed: `start → create_issue → write_change_plan → create_branch → update_docs → update_changelog → submit_pr`. New stages are added only via Workflow v2 (ADR-042 §19) and only by the QA cascade.
- The gate binary MUST NOT depend on any non-stdlib Python package (it runs in pre-commit and bootstrap contexts).
- Any new validator at a stage MUST be additive — never relax an existing check (ADR-043 §3.4 monotonic strengthening).

## Routing

| Need | Where |
|---|---|
| Run the gate | `python .workflow/gate.py start "title"` then `advance` per stage |
| Check status | `python .workflow/gate.py status <task-id>` |
| Validate reachability | `python .workflow/gate.py validate <task-id> <stage>` |
| Per-stage validator (v2 shadow) | `src/scieasy/qa/workflow/validators/<stage>.py` |
| Workflow v2 spec | ADR-042 §19 |

## Data classification

| Path | Class | Handling |
|---|---|---|
| `.workflow/gate.py` | public | Governance; changes require ADR-042 reference |
| `.workflow/state/**` | internal | Append-only event journal |
| `.workflow/state/<task>/events.jsonl` | internal | Never hand-edit |

## Assessment rubric

In addition to root R1–R11:

| ID | Criterion | Verify with |
|---|---|---|
| R1-wf | Stage advancement is strictly monotonic | `python .workflow/gate.py validate <task> <stage>` |
| R2-wf | Gate state never deleted in commit | `git log --diff-filter=D .workflow/state/` empty |
| R3-wf | No new dependency added to `gate.py` | `grep -n "^import\|^from" .workflow/gate.py` — stdlib only |
| R4-wf | Workflow v2 validators are additive over v1 | Compare validator list against ADR-042 §19 |

## Paths

| Boundary | Path | Reason |
|---|---|---|
| ⚠️ | `.workflow/gate.py` | Governance; ADR-042 §19 governs |
| 🚫 | `.workflow/state/**` (hand-edit or delete) | Append-only audit |

## Out-of-scope

Per root AGENTS.md `## Out-of-scope format`. The current `gate.py` enforces v1 6-stage flow; v2 7-stage is shadow-only (Phase 1H sub-PR 1, #1150). Hard-gating v2 is Phase 1G work and MUST be TODO-tagged when referenced.
