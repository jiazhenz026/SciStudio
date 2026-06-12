# V1 Audit Prompt

Use the SciStudio audit_reviewer persona after A1-A4 outputs are integrated.

Task: audit the integrated change contract gate implementation against
`docs/specs/adr-042-change-contract-gate.md` and issue `#1617`.

Branch/worktree:
- Create or use branch `audit/change-contract-gate`.
- Use dedicated worktree `C:\Users\jiazh\Desktop\workspace\sci-wt\ccg-audit`.
- Base from the current umbrella branch after manager integration.

Ownership:
- You own `docs/audit/change-contract-gate-implementation-audit.md`.
- You may add test-only audit fixtures only if the manager amends scope.

Out of scope:
- Do not modify production code unless the manager explicitly asks for a fix
  pass.

Audit focus:
- Spec coverage for FR-001 through FR-018 and SC-001 through SC-009.
- Whether frontmatter remains the governance index and contracts stay
  per-change evidence.
- Baseline no-new-violations behavior and stable finding identity.
- Reachability false-positive risk and dynamic canary escape path.
- Gate-record routing, full audit integration, and docs authoring accuracy.
- Test coverage depth and missing negative tests.

Verification:
- Run targeted tests identified by implementation agents.
- Run full audit if feasible.
- Final response must list findings by severity with file/line references,
  commands run, and residual risks.
