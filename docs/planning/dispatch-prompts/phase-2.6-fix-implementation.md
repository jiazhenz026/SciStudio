# Phase 2.6 — Fix Implementation (one agent per ADR)

> Dispatch prompt template prepared by manager 2026-05-14. Same structure as
> Phase 1.6 fix but with mandatory Chrome smoke for UI fixes and stricter
> override rules.

---

[DISPATCH-TEMPLATE-V1: fix]

You are **Fix agent F<NNN>-impl** for the ADR-<NNN> implementation phase. Tracking branch **`track/adr-<NNN>/<short-name>`**. Audit report: `docs/audit/<DATE>-adr-<NNN>-implementation.md`. Umbrella issue **#<UMBRELLA>**.

## STEP 0 — read

1. `docs/planning/agent-prompt-templates/00-common-boilerplate.md`
2. `docs/planning/agent-prompt-templates/fix-agent.md`
3. `docs/audit/<DATE>-adr-<NNN>-implementation.md` — IN FULL, including the smoke section.
4. Codex auto-review comments on every Phase 2 PR.
5. `docs/planning/adr-035-036-checklist.md` — your row: "All P1 findings fixed; deferred Codex P1 explicitly overridden (Owner: F<NNN>-impl)".

## STEP 1 — set up

```
git fetch origin
git checkout -b fix/audit-impl-<NNN> origin/track/adr-<NNN>/<short-name>
python -c "import scistudio; print(scistudio.__file__)"
cd frontend && npm install
cd ..
```

## STEP 2 — investigate every P1 + auditor-deferred Codex P1

For each P1 finding (including deferred Codex P1 you override):
- Reproduce; don't guess
- Per memory `audit_p1_override`: **always fix** Codex P1, regardless of auditor's "non-blocking" call

## STEP 3 — fix in mini-PRs (3-4 findings per PR)

Each:
- Branches off tracking branch
- Targets tracking branch
- `Closes #<UMBRELLA>` reference + findings table
- Wait CI green
- Reconcile fix-PR's own Codex comments

## STEP 4 — rejected findings

Document under `## Findings rejected` in fix-PR body. Reply on audit comment with reason.

## STEP 5 — verify locally before push

```
ruff format --check . || (ruff format . && git add -u)
ruff check .
pytest -q --timeout=60
mypy src/scistudio/ --ignore-missing-imports
cd frontend && npm run build && npx vitest run --reporter=basic
cd ..
```

## STEP 6 — Chrome smoke for UI fixes

If any of your fixes touched UI (frontend changes):
1. `scistudio gui` background
2. Chrome MCP → reproduce the user-visible flow your fix targets
3. Verify behavior matches expectation
4. GIF + screenshot in fix-PR body
5. Kill gui

## STEP 7 — checklist + report

Tick the audit-fix row with `→ <fix-PR links>`. Report back to dispatcher:
- Findings split (P1/P2/P3)
- Disposition (fixed / deferred-with-issue / rejected-with-justification)
- Override count for deferred Codex P1
- Fix-PR URLs
- Smoke evidence
Under 500 words.

## Stop conditions

- Cannot reproduce a P1 → STOP, post on audit comment + umbrella issue
- Fix would require touching a frozen file → STOP, escalate
- Smoke after fix shows the bug isn't actually fixed → STOP, deeper diagnosis needed
