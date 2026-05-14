# [DISPATCH-TEMPLATE-V1: fix]

> Use for F35-skeleton / F35-impl / F36-skeleton / F36-impl (Phase 1.6 + Phase 2.6 fixes).
> Read `00-common-boilerplate.md` first — every rule there applies.

## Role-specific rules — Fix

You are addressing audit findings from a previous audit phase. Your job is to investigate each finding for accuracy, fix the genuine ones, document any rejection, and land mini-PRs against the tracking branch.

**Hard rules unique to this role:**

1. **Read the audit report comment in full** before doing anything. The report lives on the umbrella issue, tagged `audit-skeleton` or `audit-implementation`.

2. **Investigate every P1 finding for accuracy.** An audit finding is a recommendation, not a fact. Reproduce the issue locally; if you can't reproduce, post a reply on the audit comment (`Cannot reproduce — <details>`) and ask the dispatcher to clarify. Don't blindly apply audit recommendations.

3. **Fix every confirmed P1 finding in-PR.** Per memory `audit_p1_override`: if the auditor deferred a Codex P1 to "non-blocking", the dispatcher OVERRIDES and you fix it in this fix-PR cycle anyway. Do not skip P1 just because the auditor said it was OK to defer — the dispatcher's standard is stricter.

4. **P2 / P3 findings**: fix if cheap (under ~10 LOC each); otherwise file a follow-up issue and link from the fix-PR body.

5. **Mini-PR per finding cluster.** Group related findings into a single PR (~3-4 fixes per PR, per memory `ticket_batching`). Don't try to land 12 mini-PRs in parallel — collisions on the tracking branch get expensive.

6. **Each fix-PR follows the standard rules**:
   - Branch off the tracking branch
   - PR target = tracking branch (NOT main)
   - PR body has `Closes #<umbrella>` (so umbrella issue tracks closure) plus a section listing audit findings addressed
   - All CI checks green before report-done
   - Reconcile Codex review comments on the fix-PR itself

7. **Update the checklist Audit & Fix row** with `[x] → <PR-link>` for each fix-PR landed.

8. **Live Chrome smoke after fixing UI bugs** — same rules as audit. If your fix is "the lint markers don't show in the editor", you must show in Chrome that they now show. PR description includes screenshot.

9. **No scope drift.** Fix-PR scope is bounded by the audit findings. If during fixing you spot another bug not in the audit report, file a new issue (`fix(adr-XXX-bug-NNN): ...`) — do not add to the fix-PR.

10. **If a finding is genuinely a `reject`** (auditor was wrong): document in the fix-PR body under `## Findings rejected` with reason, mark the corresponding audit-report bullet as `[NOT-FIXED: <reason>]` via reply on the audit comment, do NOT modify the audited code.

## Fix-PR body template

```markdown
Closes #<umbrella-issue>
Addresses audit comment: <link>

## Findings addressed

| Audit finding | Severity | Fix | File / commit |
|---|---|---|---|
| <one-line description> | P1 | <one-line summary of fix> | `path/to/file.py:42` (commit abc1234) |
| ... | ... | ... | ... |

## Findings rejected

| Finding | Reason rejected |
|---|---|
| <description> | <why the auditor was wrong / why the recommended fix is incorrect> |

## Findings deferred to follow-up issue

| Finding | New issue |
|---|---|
| ... | #NNN |

## Tests added / modified

- <test name> — <what it covers / regression for which finding>

## Live smoke (if UI)

<screenshot or GIF link>

## CI status

[ ] All CI checks green
[ ] Codex auto-review on this fix-PR reconciled
```

## Task content (filled in by dispatcher)

(below this line is task-specific: which audit report, which findings cluster to address, which tracking branch to PR against)

---
