# Phase 2.5 — Audit Implementation (one agent per ADR)

> Dispatch prompt template prepared by manager 2026-05-14. Substitute `<NNN>` with `035` or `036`, `<UMBRELLA>` with `842` or `843`, and the implementation PR numbers.

---

[DISPATCH-TEMPLATE-V1: audit]

You are **Auditor A<NNN>-impl** for the ADR-<NNN> implementation phase. Tracking branch **`track/adr-<NNN>/<short-name>`**. PRs to audit: <list of merged Phase 2 PRs for this track>. Umbrella issue: **#<UMBRELLA>**.

## STEP 0 — read

1. `docs/planning/agent-prompt-templates/00-common-boilerplate.md`
2. `docs/planning/agent-prompt-templates/audit-agent.md`
3. `docs/adr/ADR-<NNN>.md` — full read. You verify the implementation matches the design in detail.
4. `docs/planning/adr-035-036-checklist.md` — your job covers ALL "Phase 2*" rows under ADR-<NNN>.

## STEP 1 — set up

```
git fetch origin
git checkout -b audit/impl-<NNN>-<datestamp> origin/track/adr-<NNN>/<short-name>
python -c "import scieasy; print(scieasy.__file__)"
cd frontend && npm install
cd ..
```

## STEP 2 — verify checklist accuracy

For every box ticked in Phase 2A / 2B / 2C sections:
- Artifact link valid?
- Implementation actually exists and does what the row claims?
- Out-of-scope rows touched?

Drift → report + revert recommendation.

## STEP 3 — verify ADR compliance

For each Phase 2 sub-issue:
- Read the ADR sections referenced
- Compare implementation line-by-line where critical
- Note ANY divergence (design, contract, error envelopes, edge cases)

Severity:
- P1 = correctness divergence (wrong contract, wrong state machine, missing error path)
- P2 = behavior divergence (missing edge case, missing log, missing test)
- P3 = nice-to-have (style, doc improvement)

## STEP 4 — run full local CI

```
ruff format --check .
ruff check .
pytest -q --timeout=60
mypy src/scieasy/ --ignore-missing-imports
cd frontend && npm run build && npx vitest run --reporter=basic
cd ..
```

Any failure = P1.

## STEP 5 — MANDATORY live Chrome smoke

Per `feedback_mandatory_chrome_smoke_test` and `feedback_phase_audit_smoke_test`. Unit tests do NOT replace this.

```
scieasy gui --port <free> --no-browser   # background
```

Use Chrome MCP (`mcp__claude-in-chrome__*` tools — load via ToolSearch first).

**For ADR-035**: build a minimal workflow (`LoadImage` with 1 input → `AIBlock` with provider=Claude Code, permission=Bypass, prompt = "echo 'hi' to outputs/x.csv then call finish_ai_block({metadata: 'outputs/x.csv'})" → `SaveData`). Run. Verify:
- AI Block tab opens automatically (block_pty_opened event)
- Status badge transitions (spinner → done)
- Mark-done button visible during PAUSED, hidden after DONE
- Tab survives DONE (still interactive)
- Workflow continues PAUSED → DONE
- The CSV file is produced

**For ADR-036**: 
- Open editor for an existing `.py` from project tree → Monaco renders + lint markers appear after typing
- Edit a char → wait 800 ms → verify mtime advanced on disk
- Click "View source" on a workflow → Monaco renders YAML readonly; re-click dedups
- Toolbar swap: switch to file tab → Run/Pause/etc hidden, Save shown
- "New" menu shows three options; click "New custom block" → file appears in `blocks/`, opens in editor with template content

GIF screenshots via `mcp__claude-in-chrome__gif_creator`. Kill the gui process and close Chrome tabs at end.

If the smoke fails on a P1 path, mark the audit as `block`.

## STEP 6 — Codex reconcile

For every Codex auto-review comment on every Phase 2 PR:
- Reply: `accepted` / `deferred (reason)` / `rejected (reason)`
- Per memory `audit_p1_override`: do NOT defer Codex P1. If you do, the dispatcher overrides.

## STEP 7 — write report + commit

**REQUIRED: save report file** at:
```
docs/audit/<YYYY-MM-DD>-adr-<NNN>-implementation.md
```

Tiny PR (audit-output exempt from no-PR rule). Body `Closes #<UMBRELLA>` reference.

Also post identical content as comment on umbrella issue #<UMBRELLA>.

Report shape (audit-agent.md §9) plus a `## Smoke evidence` section linking the GIF + screenshots.

## STEP 8 — checklist + report back

Tick "Audit-implementation report posted on umbrella issue, includes Chrome smoke results" with links.

Report to dispatcher: verdict (pass / pass-with-fixes / block), audit-report URL, count of Codex comments + disposition, count of P1/P2/P3 findings, smoke evidence summary. Under 500 words.

## Stop conditions

If smoke reveals a release-blocking issue (e.g. AI Block tab never opens, editor hangs, save destroys file content), mark `block` and recommend immediate hotfix. Per `feedback_phase_audit_smoke_test`: 30 seconds of real clicking surfaces bugs all CI green missed.
