# Phase 1.5 — Audit Skeleton (one agent per ADR)

> Dispatch prompt template prepared by manager 2026-05-14. Substitute `<NNN>` with `035` or `036` and `<UMBRELLA>` with `842` or `843` and `<S-PR>` with the skeleton PR number.

---

[DISPATCH-TEMPLATE-V1: audit]

You are **Auditor A<NNN>-skeleton** for the ADR-<NNN> skeleton phase. Tracking branch **`track/adr-<NNN>/<short-name>`** (`ai-block-pty` for 035, `code-editor` for 036). Skeleton PR to audit: **#<S-PR>**. Umbrella issue: **#<UMBRELLA>**.

## STEP 0 — read

1. `docs/planning/agent-prompt-templates/00-common-boilerplate.md`
2. `docs/planning/agent-prompt-templates/audit-agent.md`
3. `docs/adr/ADR-<NNN>.md`
4. `docs/planning/adr-035-036-checklist.md` — your job is to verify the "Skeleton (S<NNN>)" rows are accurately ticked, every artifact link is real, no out-of-scope rows touched, and the comment-block coverage is sufficient for implementation agents.

## STEP 1 — set up

```
git fetch origin
git checkout -b audit/skeleton-<NNN>-<datestamp> origin/track/adr-<NNN>/<short-name>
```

## STEP 2 — verify checklist accuracy

For every box ticked in the Skeleton section:
- Does the linked commit/PR/file exist?
- Does the artifact actually deliver what the row claims (not just "exists, but empty")?
- Was anything ticked outside the Skeleton (S<NNN>) section that shouldn't have been?

Log any drift in the report's `## Checklist drift` section + propose un-ticking + log in checklist `Drift log`.

## STEP 3 — verify ADR compliance + comment-block sufficiency

For every NotImplementedError stub:
- Does the preceding comment block contain Purpose / Signature contract / Implementation steps / Edge cases / Test plan / References?
- Are the references to ADR section numbers + line ranges of analogous existing code accurate?
- Could an implementation agent build the function without re-reading the ADR? (gut check)

Rate each as Sufficient / Needs more / Wrong contract. Log in report.

## STEP 4 — run local CI

```
ruff format --check .
ruff check .
pytest -q --timeout=60   # xfail / skip stubs expected
mypy src/scistudio/ --ignore-missing-imports
cd frontend && npm run build && npx vitest run --reporter=basic
cd ..
```

Any failure = P1 in the report.

## STEP 5 — Codex reconcile

For every Codex auto-review comment on PR #<S-PR>:
- Reply: `accepted (will fix in audit-fix branch)` / `deferred (reason: ...)` / `rejected (reason: ...)`.
- Per memory `audit_p1_override`: do NOT defer Codex P1 as "non-blocking". The dispatcher will override.

## STEP 6 — write the report

**REQUIRED: save the report as a markdown file**:
```
docs/audit/<YYYY-MM-DD>-adr-<NNN>-skeleton.md
```

Commit on a tiny branch (e.g. `chore/audit-skeleton-<NNN>`) and PR to `track/adr-<NNN>/<short-name>` (audit-output PRs are exempt from no-PR rule per audit-agent.md §8). PR body has `Closes #<UMBRELLA>` reference.

Also POST the same content as a comment on umbrella issue #<UMBRELLA>.

Report shape (per audit-agent.md §9):
```markdown
# Audit report — Skeleton (track/adr-<NNN>/...)
Date: <YYYY-MM-DD>
PR reviewed: #<S-PR>
Checklist rows verified: <X / Y>

## Summary
<pass | pass-with-fixes | block> — 1-2 sentences

## Checklist drift
<list>

## ADR compliance + comment sufficiency
<list>

## CI status
ruff: <pass/fail>; pytest: <X xfail / Y passed>; mypy: <pass/fail>; vitest: <X/Y passed>

## Findings (P1/P2/P3)
- ...

## Codex reconciliation
- PR #<S-PR> has <X> comments. Resolved: <bulletwise>.

## Recommendation for fix agent (if any)
<ordered list>
```

## STEP 7 — checklist + report back

Tick checklist "Audit-skeleton report posted on umbrella issue (Owner: A<NNN>-skeleton)" with link to your report file commit + umbrella comment.

Report back to dispatcher: audit verdict (pass / pass-with-fixes / block), report URL, count of Codex comments and their disposition, recommendations for fix phase. Under 400 words.

## Stop conditions

Same as common boilerplate. NOTE: skeleton phase does NOT require live Chrome smoke (no behavior to smoke-test yet). That kicks in for Phase 2.5 audits.
