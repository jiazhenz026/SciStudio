# A3 Reachability Prompt

Use the SciStudio implementer persona.

Task: implement conservative reachability helpers for the change contract gate.
Issue: close `#1620` in your PR body.

Branch/worktree:
- Create or use branch `feat/change-contract-gate-reachability`.
- Use dedicated worktree `C:\Users\jiazh\Desktop\workspace\sci-wt\ccg-reachability`.
- Base from umbrella branch `track/change-contract-gate-implementation`.

Ownership:
- You own `src/scistudio/qa/audit/change_contract_reachability.py`.
- You own reachability-focused tests, preferably
  `tests/qa/test_change_contract_reachability.py`.

Out of scope:
- Do not own schema models.
- Do not own baseline reconciliation.
- Do not wire `full_audit` or `gate_record`.

Requirements:
- Python modules: build an import graph rooted at declared production roots.
- Frontend components: build a TypeScript import graph rooted at declared UI
  roots using conservative static import parsing.
- Entry points: parse Python packaging metadata and registered group names where
  available.
- Dynamic cases: expose a path for explicit entrypoint or canary declarations
  instead of failing hard on dynamic loading.
- Return structured findings that A2 can consume without depending on test-only
  paths.
- Use tracked TODO format only: `TODO(#NNN): ...`.

Verification:
- Run targeted reachability tests for reachable Python module, test-only Python
  module, reachable frontend component, test-only frontend component, missing
  entrypoint, and explicit canary override.
- Final response must list changed files, test commands, and any blockers.
