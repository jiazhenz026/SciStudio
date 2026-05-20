# Spec And ADR Rules

## 1. Decision Summary

Use issues for task traceability, specs for behavior and contract definition,
and ADRs for architectural decisions. Use SpecKit for significant feature-level
design. Do not hide design decisions inside implementation commits.

## 2. Before Coding

Before implementation, confirm:

1. The issue being solved.
2. Scope and acceptance criteria.
3. Whether a spec is required.
4. Whether an ADR is required.
5. Which tests and docs should land with the change.

## 3. When A Spec Is Required

Write or update a spec when work changes:

- object model;
- block protocol;
- runtime execution behavior;
- storage behavior;
- API contracts;
- plugin contracts;
- major UI semantics;
- AI orchestration behavior;
- external app integration model.

If the change needs requirements analysis, design choices, or task
decomposition, use SpecKit before implementation:

```text
/speckit.specify "Feature summary"
/speckit.clarify
/speckit.plan
/speckit.tasks
/speckit.analyze
```

For small, obvious changes, skip SpecKit and use the GitHub issue plus gate
change plan as the task spec.

## 4. When An ADR Is Required

Write or update an ADR when a decision is:

- architectural;
- hard to reverse;
- likely to affect multiple modules;
- likely to be questioned later;
- a tradeoff between competing long-term options.

Examples include workflow graph ownership, storage model, primitive object
types, plugin strategy, external app execution semantics, or governance model
changes.

## 5. Bugfix Decision Rules

Classify the bug before coding:

| Issue type | Needs ADR? | Needs spec? |
|---|---:|---:|
| Simple bug with clear fix | no | no |
| Bug with multiple valid design choices | yes | maybe |
| Behavior change affecting contracts | yes | maybe |
| New feature or subsystem | yes | yes |

Simple bug fixes should include regression tests when practical. If the fix
reveals a different bug, open or link a separate issue instead of broadening
the current PR silently.

## 6. Implementation Task Rules

For every task from a SpecKit `tasks.md`, run the active `.workflow/gate.py`
workflow separately. SpecKit designs the feature; the gate controls each
reviewable implementation task.
