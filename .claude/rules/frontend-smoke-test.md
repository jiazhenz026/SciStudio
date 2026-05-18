---
description: Frontend smoke-test expectations
paths:
  - frontend/**
---

# Frontend Smoke Test

- Root and `frontend/AGENTS.md` apply first.
- For meaningful UI changes, use the in-app browser for a local smoke check
  when a local target is known or obvious.
- Do not run `npm run dev` as a long-lived service unless the task requires an
  interactive frontend target; prefer bounded test/build commands.
- Verify visible UI text does not overlap and runtime truth is not frontend-only.

TODO(#1113): Retarget the full browser-smoke procedure to
`docs/contributing/workflows/testing.md` after ADR-044 lands contributor docs.
Out of scope per ADR-043 §5 / ADR-044 §11. Followup: #1113.
