# Report Template

How to write Section 7 of the scenario file and the user-facing message
at the end of the run. Keep it concise — the user already knows the
intent (they wrote Sections 1–6); they want the outcome and the
evidence.

## 1. Section 7 — In-File Report

Fill these exactly. Do not invent extra headings.

### 7.1 Verdict

One word: `PASS`, `FAIL`, or `ABORTED`. No qualifications.

- `PASS` only if every step in Section 5 passed AND no regression
  sentinel in Section 6 fired.
- `FAIL` if any step Expected was not met, or any sentinel fired.
- `ABORTED` if pre-flight, launch, or Chrome activation failed before
  the steps could run.

Below the verdict, one sentence — what is the headline?

```
**Verdict**: PASS — all 7 steps passed, no sentinels fired.
```

```
**Verdict**: FAIL — Step 4 (drag LoadData onto canvas) saw 0 nodes
added; React error "ReactFlow not initialized" in console.
```

```
**Verdict**: ABORTED — backend did not become ready within 60s;
stderr in artifacts/backend-launch.log.
```

### 7.2 Per-Step Outcome

Markdown table, one row per step. Evidence is one short phrase that
points at the artifact or the value observed:

```markdown
| Step | Outcome | Evidence | Notes |
|------|---------|----------|-------|
| 1 — Open new project | PASS | screenshot step1 | folder picker bypassed via POST /api/projects |
| 2 — Add LoadData block | PASS | nodeCount 1→2 | |
| 3 — Wire LoadData→Save | FAIL | edges.length stayed 0 | drag released outside handle |
```

### 7.3 Sentinel Hits

One bullet per hit. If none, write `None.` and move on.

```markdown
- Step 3 — Console error: "Cannot read property 'id' of undefined" at edges.tsx:142
- Step 5 — Network 500: POST /api/workflows/validate
```

### 7.4 Artifacts

Absolute paths, one per line. Group by step if there are many.

```markdown
- C:\Users\jiazh\Downloads\scieasy-e2e-2026-05-20-pr-1300-step1.png
- C:\Users\jiazh\Downloads\scieasy-e2e-2026-05-20-pr-1300-step3.png
- C:\Users\jiazh\Downloads\scieasy-e2e-2026-05-20-pr-1300-console.log
```

### 7.5 Follow-Ups

Out-of-scope issues you saw, with issue numbers if you opened any:

```markdown
- #1305 — Edge wire animation jitters on first drag (cosmetic; not in scope)
- #1306 — Console warning "validateDOMNesting" on every Palette render
```

If none, write `None.`

## 2. User-Facing Final Message

After writing Section 7, send one short message to the user. Template:

```
E2E session <session-id>: <PASS|FAIL|ABORTED>.

<one-line headline — what passed, or what specifically failed and where>

Scenario file: docs/ai-developer/e2e/<filename>.md
<N> screenshots captured under Downloads/scieasy-e2e-<session-id>-*.png
<If FAIL/ABORTED, name the first thing the user should look at>
```

Examples:

```
E2E session 2026-05-20-pr-1300-readiness: PASS.

All 7 steps green, no console errors, no sentinel hits.

Scenario file: docs/ai-developer/e2e/2026-05-20-pr-1300-readiness.md
7 screenshots captured under Downloads/scieasy-e2e-2026-05-20-pr-1300-*.png
PR #1300 is ready to merge from an e2e standpoint.
```

```
E2E session 2026-05-20-hotfix-869: FAIL.

Step 4 (stuck-loading tab repro) did not reproduce — tabs[0].loading
stayed false after reload. The fetch-delay race may need a larger
delay or the persist payload may already include `loading: false`.

Scenario file: docs/ai-developer/e2e/2026-05-20-hotfix-869.md
3 screenshots; the relevant one is step4.png.
Open the file and look at Section 7.2 + 7.3 for details.
```

## 3. PR Readiness Mode — Extra Comment

If the scenario is `trigger.kind: pr-readiness` AND verdict is PASS,
post a comment to the PR with the verdict + table:

```powershell
$body = @"
## E2E Verdict — PASS

Scenario: ``docs/ai-developer/e2e/<filename>.md``

<paste 7.2 table>

<paste 7.3 sentinel hits or "Sentinels: none">
"@
gh pr comment <N> --body $body
```

Do not merge. Merging is always a user action.

## 4. Hotfix Mode — Repro vs Verify

In hotfix mode, you run twice:
1. On the buggy branch / `main` — expect FAIL (you reproduced the bug)
2. On the fix branch — expect PASS (the fix works)

Section 7 of the same scenario file captures both runs. Add a `### Run 1`
and `### Run 2` subheading inside 7.1 so the history is clear:

```markdown
### Run 1 — main @ <SHA> (pre-fix)
**Verdict**: FAIL — bug reproduced.
...

### Run 2 — hotfix/<branch> @ <SHA>
**Verdict**: PASS — fix verified.
...
```

The final user message names both runs:

```
E2E session 2026-05-20-hotfix-869: FAIL on main → PASS on hotfix/869-stuck-loading.

Bug reproduced on main (Run 1, step 4: tabs[0].loading stuck at true
after rehydration). Fix verified on hotfix branch (Run 2, all steps
green). Safe to PR.

Scenario file: docs/ai-developer/e2e/2026-05-20-hotfix-869.md
```
