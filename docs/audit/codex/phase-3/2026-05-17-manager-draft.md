# Phase 3 — Manager Merged Draft (Codex)
Date: 2026-05-17
Inputs: R1 + R2 reconciliation reports

## Merge method
- Keep architecture-principle items at A when both R1/R2 agree principle is stable.
- Escalate to C when both reports indicate implementation/context-dependent contract drift.
- Use B for partially aligned items requiring documentation hardening or boundary tightening.

## Master candidate list

| module | interface_item | final_abcd | action_type | rationale | evidence |
|---|---|---|---|---|---|
| M01 | DataObject typed contract + metadata stratification | A | none | Core principle stable; disputes are mostly wording/anchor depth | R1/R2 + phase-1.5 code/docs |
| M01 | dual history join (`workflow_git_commit`) | A | none | Strong alignment across architecture/docs | R1/R2 |
| M02 | Block base contract (typed ports/lifecycle) | A | none | Stable and implemented contract | R1/R2 |
| M02 | dynamic/variadic port semantics | A | none | No conflicting evidence | R1/R2 |
| M02 | registry strictness vs fallback path | B | docs-fix | Needs explicit normative levels and fallback semantics | R1/R2 |
| M03 | DAG lifecycle protocol | A | none | Protocol exists and is coherent | R1/R2 |
| M03 | checkpoint wire schema details | B | docs-fix | Schema shape implemented but insufficiently centralized in docs | R1/R2 |
| M03 | scheduler responsibility width | B | code-change | Coupling breadth should be narrowed/clarified | R2 |
| M04 | AI proposal vs runtime validation boundary | A | none | Principle aligned with architecture | R1/R2 |
| M04 | dual runtime paths auditability | B | docs-fix | Behavior exists; docs need explicit decision tree | R1/R2 |
| M05 | REST workflow/block schema | A | none | Implemented and documented at high level | R1/R2 |
| M05 | WS/SSE frame typing strength | B | code-change | stringly protocol and weak typing risk | R1/R2 |
| M05 | API/runtime cross-layer coupling | C | code-change | concrete mismatch risk affecting contract stability | R2 + A-diff |
| M06 | workflow graph SoT + validate entrypoint | A | none | principle remains correct | R1/R2 |
| M06 | validation depth varies by registry availability | C | code-change | same workflow can yield inconsistent diagnostics | R1/R2 |
| M07 | frontend as editor/viewer (not runtime truth) | A | none | principle stable | R1/R2 |
| M07 | watcher/protocol reverse-coupling | B | docs-fix | needs clearer contract ownership and payload boundaries | R1/R2 |
| M08 | CLI install/mcp-bridge contract | A | none | generally aligned | R1/R2 |
| M08 | scaffold conformance verification | B | docs-fix | missing normative acceptance checks | R1/R2 |
| M09 | plugin entry/test harness boundary | B | docs-fix | contract exists but centralized normative text lacking | R1/R2 |
| M09 | `supported_extensions` doc-first gap | C | code-change | documented requirement not fully enforced in implementation | R1/R2 |

## Distribution
- A: 10
- B: 8
- C: 3
- D: 0

## Next
Phase 4 audits validate correctness of A/B/C labels and architecture consistency.
