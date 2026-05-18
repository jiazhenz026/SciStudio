---
description: Test discipline for SciEasy test files
paths:
  - tests/**
---

# Test Discipline

- Use the `test-author` skill before writing or revising tests.
- Assert observable behavior, not mere execution, non-null values, or mock calls
  without a result assertion.
- Run focused pytest with an explicit timeout when practical, for example
  `pytest --timeout=60 <test path>`.
- Do not start long-lived services from tests or test hooks.

TODO(#1113): Move the canonical testing procedure to
`docs/contributing/workflows/testing.md` and retarget this rule once ADR-044
contributor docs exist. Out of scope per ADR-043 §5 / ADR-044 §11.
Followup: #1113.
