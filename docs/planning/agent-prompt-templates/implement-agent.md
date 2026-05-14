# [DISPATCH-TEMPLATE-V1: implement]

> Use for I35a / I35b / I35c / I36a / I36b / I36c (Phase 2 implementation).
> Read `00-common-boilerplate.md` first — every rule there applies.

## Role-specific rules — Implement

You are filling in the bodies of the skeleton stubs landed in Phase 1. Your job is to follow the skeleton's implementation comments, write the real logic + tests, and merge cleanly.

**Hard rules unique to this role:**

1. **Follow the skeleton's implementation comments.** Each function you implement has a comment block describing Purpose / Signature contract / Implementation steps / Edge cases / Test plan / References. Do NOT redesign the contract; if you think the comment is wrong, STOP and post on the umbrella issue — escalation, not silent change.

2. **Write the tests the skeleton's test plan listed.** Convert each xfail/skip test into a real pytest / vitest test. Add additional tests for things you discover during implementation. Tests that exercise integration points (not just one function) belong in `tests/integration/` not the unit dirs.

3. **Stay within your dispatched scope.** Your dispatch lists exact files in scope. Do NOT touch files outside that list — even if "while you're there, this related thing also needs fixing". File a follow-up issue and let it be a separate PR. Per memory `agent_discipline_and_pytest_timeout`, scope drift was a major cause of past breakage (#810/#811).

4. **Coordinate with sibling agents.** If your phase has 3 parallel agents (e.g. I35a + I35b + I35c), they all branch from the **same** tracking branch and PR back to it. If two PRs touch the same file (e.g. Toolbar.tsx in I36b + I36c), the second one merges with `git merge origin/track/...` after the first lands and resolves conflicts. The dispatcher sequences sibling agents to minimize collisions.

5. **Test coverage threshold.** Your PR must include tests for every code path the skeleton's test plan lists. If you skip one, justify in the PR body with `Test deferred: <reason>` — and the auditor will judge.

6. **Run the full local CI before push** (per common boilerplate §12). PRs blocked by lint or formatting waste reviewer time.

7. **For UI-touching changes (any frontend agent)**: include screenshots / a short GIF in the PR body. Use Chrome MCP if available. Without visible-behavior evidence, the audit phase cannot verify your change.

8. **Update the checklist as you go.** Every checklist row in your "Phase 2X" section gets ticked with `→ <commit-sha or test-name>` as soon as the implementation lands. Don't batch ticks at the end — that loses the artifact mapping.

## PR body template — Implement

```markdown
Closes #<issue>

## What this implements

ADR-0<35|36> §<sections>, building on the Phase 1 skeleton from PR #<skeleton-PR>.

## Files modified

- <path 1> — <one-line summary of change>
- <path 2> — ...

## Tests added

- <test file>::<test name> — <what it covers>
- ...

## Test plan coverage

Every test plan from the skeleton's comments is implemented:
- [x] <test from skeleton plan>
- [ ] <test from skeleton plan> — deferred, reason: <...>

## Cross-agent coordination

(if applicable) This PR touches `<file>` which is also in scope for #<other-PR>. Merged after #<other-PR> with conflict resolution at <line range>.

## Screenshots / GIF

(UI changes only) <embed link>

## Checklist updates

Ticked rows in `docs/planning/adr-035-036-checklist.md` under
`Phase 2X — ... (I##)`:
- <bullet list with → commit-sha or PR comment link>

## CI status

[ ] All CI checks green
[ ] Codex auto-review reconciled (every comment accepted / deferred / rejected)
```

## Task content (filled in by dispatcher)

(below this line is task-specific: dispatch lists exact files in scope, exact files out of scope for this agent, exact skeleton PR to build on, exact sibling-agent coordination notes)

---
