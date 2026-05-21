# Phase 1.6 — Fix Skeleton (one agent per ADR, conditional)

> Dispatch prompt template prepared by manager 2026-05-14. Substitute `<NNN>`,
> `<UMBRELLA>`, the audit report file path, and the list of P1 findings.

---

[DISPATCH-TEMPLATE-V1: fix]

You are **Fix agent F<NNN>-skeleton** for the ADR-<NNN> skeleton phase. Tracking branch **`track/adr-<NNN>/<short-name>`**. Audit report: `docs/audit/<DATE>-adr-<NNN>-skeleton.md`. Umbrella issue **#<UMBRELLA>**.

## STEP 0 — read

1. `docs/planning/agent-prompt-templates/00-common-boilerplate.md`
2. `docs/planning/agent-prompt-templates/fix-agent.md`
3. The audit report file at `docs/audit/<DATE>-adr-<NNN>-skeleton.md` — IN FULL.
4. The Codex auto-review comments on the skeleton PR (the auditor flagged some as `accepted (will fix in audit-fix branch)` — those are yours).
5. `docs/planning/adr-035-036-checklist.md` — your row: "All P1 findings fixed (or explicitly justified deferral) (Owner: F<NNN>-skeleton)".

## STEP 1 — set up

```
git fetch origin
git checkout -b fix/audit-skeleton-<NNN> origin/track/adr-<NNN>/<short-name>
```

## STEP 2 — investigate every P1

For each P1 finding in the audit report:
- Reproduce locally; if you cannot reproduce, post a reply on the audit comment (`Cannot reproduce — <details>`) and mark as `[NOT-FIXED: cannot-reproduce]` in your fix-PR body. Don't guess.
- Per memory `audit_p1_override`: even if the auditor said "non-blocking deferred" on a Codex P1, **fix it anyway**. Dispatcher standard is stricter.

## STEP 3 — fix in mini-PRs

Group related findings into ONE mini-PR (~3-4 fixes per PR). For skeleton phase, mini-PRs are usually: missing comment blocks, wrong NotImplementedError signature, missing test stubs, ADR-section reference errors. All low-risk.

Each fix-PR:
- Branches off `track/adr-<NNN>/<short-name>`
- Targets `track/adr-<NNN>/<short-name>` (NOT main)
- Body has `Closes #<UMBRELLA>` (umbrella) + table of findings addressed
- Wait CI green
- Reconcile Codex review on the fix-PR itself

## STEP 4 — handle rejected findings

If a finding is genuinely a `reject` (auditor was wrong):
- Document in fix-PR body under `## Findings rejected`
- Reply on audit comment: `[REJECTED: <reason>]`
- Do NOT modify the audited code

## STEP 5 — verify locally before each push

```
ruff format --check . || (ruff format . && git add -u)
ruff check .
pytest -q --timeout=60   # xfail/skip stubs expected
mypy src/scistudio/ --ignore-missing-imports
cd frontend && npm run build && npx vitest run --reporter=basic
cd ..
```

## STEP 6 — checklist + report

Tick the audit-fix row in checklist with `→ <fix-PR link(s)>`. Report back to dispatcher:
- Number of findings (P1/P2/P3 split)
- Number addressed / deferred / rejected
- Fix-PR URL(s)
- Smoke evidence if any UI fix
Under 400 words.

## Stop conditions

- An audit finding requires modifying a forbidden file → STOP, post on umbrella issue, exit
- A "fix" would change the contract the implementation phase depends on → STOP, escalate
