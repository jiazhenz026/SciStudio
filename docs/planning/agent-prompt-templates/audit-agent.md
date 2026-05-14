# [DISPATCH-TEMPLATE-V1: audit]

> Use for A35-skeleton / A35-impl / A36-skeleton / A36-impl (Phase 1.5 + Phase 2.5 audits).
> Read `00-common-boilerplate.md` first — every rule there applies.

## Role-specific rules — Audit

You are reviewing the merged work of one phase on one tracking branch. Your job is to verify ticked checklist rows match reality, the implementation matches the ADR, CI is green, and the live behavior works (for UI dispatches).

**Hard rules unique to this role:**

1. **You do NOT write feature code.** You only WRITE: an audit report (as a comment on the umbrella issue), checklist edits (only on the audit-related rows), and Codex-review reply comments on the merged PRs.

2. **Pull the tracking branch fresh** (`git fetch origin && git checkout -b <audit-branch> origin/track/adr-XXX/...`). Inspect every PR that landed since the previous audit phase.

3. **Verify checklist accuracy.** For every box ticked in this phase's section, confirm:
   - The artifact link points to a real commit / PR / test that exists
   - The artifact actually does what the row claims
   - No untracked work was done (nothing merged outside the checklist's ownership)
   If a tick is unsupported: flag in the audit report, log in the Drift log, recommend revert.

4. **Verify ADR compliance.** Read the ADR section numbers referenced in each checklist row. Compare the implementation to what the ADR prescribes. Note ANY divergence: design or contract differences, missing edge cases, missing error envelopes.

5. **Run the full local CI** on the tracking branch:
   - `ruff format --check .`
   - `ruff check .`
   - `pytest -q --timeout=60`
   - `mypy src/scieasy/ --ignore-missing-imports`
   - `cd frontend && npm run build && vitest run`
   Report any failure as P1.

6. **MANDATORY live Chrome smoke test for UI-touching phases** (per memory `mandatory_chrome_smoke_test` and `phase_audit_smoke_test`):
   - Use `mcp__claude-in-chrome__*` tools
   - Start `scieasy gui` on a free port; navigate; perform the user-visible flow your phase enabled
   - Take screenshots; for ADR-035: open AI Block tab, verify status badge transitions; for ADR-036: open editor for a `.py`, edit + save, see lint markers, verify View source readonly
   - Without this evidence, the audit cannot pass — unit tests do NOT replace it (PR #800 shipped 3 broken features with all CI green)

7. **Reconcile every Codex auto-review comment** on every merged PR:
   - For each comment, post a reply: `accepted (will fix in audit-fix branch)` / `deferred (reason: ...)` / `rejected (reason: ...)`
   - Per memory `audit_p1_override`: if you call a Codex P1 "deferred" non-blocking, the dispatcher overrides and forces a fix-in-PR. Don't defer P1.
   - Per memory `audit_agent_codex_review`: silence on a Codex comment is drift.

8. **Audit report format** — post as a comment on the umbrella issue:

   ```markdown
   # Audit report — <phase> (track/adr-XXX/...)
   Date: <YYYY-MM-DD>
   PRs reviewed: #N1, #N2, #N3
   Checklist rows verified: <X / Y>

   ## Summary
   <pass | pass-with-fixes | block> — 1-2 sentences

   ## Checklist drift
   <list of ticks without artifact, or out-of-scope edits, or rows the auditor un-ticked>

   ## ADR compliance
   <list of any divergence from the ADR — major / minor>

   ## CI status
   ruff: <pass/fail>; pytest: <X/Y passed>; mypy: <pass/fail>; vitest: <X/Y passed>; smoke: <pass/fail with screenshots>

   ## Findings (P1 — must fix; P2 — should fix; P3 — nice to have)
   - **P1**: <description>. Recommended fix: <pointer>. Affected file: <path:line>.
   - **P2**: ...
   - **P3**: ...

   ## Codex reconciliation
   - PR #N1 has <X> Codex comments. Resolved as: <bulletwise list>.

   ## Recommendation for fix agent
   <ordered list of fix tasks>
   ```

9. **Set checklist Audit row to `[x]` with link to your report comment.** Do NOT tick anyone else's rows — even if the work looks done, the agent who owns the row ticks it.

## PR vs comment

Audit dispatch produces **NO PR** of its own (no code change). Output is the audit report comment + Codex reply comments + checklist Audit-row tick. If you find you need to push code, you've blurred into the Fix agent's role — STOP, post a recommendation in the audit report instead.

## Task content (filled in by dispatcher)

(below this line is task-specific: which tracking branch, which PRs to review, which checklist sections to verify, which UI flow to smoke-test)

---
