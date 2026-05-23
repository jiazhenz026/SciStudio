---
name: scistudio-e2e-test
description: Drive a live end-to-end SciStudio session — start the backend (and Vite if needed), open Chrome via Chrome MCP, walk the scenario file the user points at, capture screenshots/console/network as evidence, and write a pass/fail verdict back into that file. Trigger whenever the user says "跑 e2e", "do an e2e", "run e2e on PR #N", "verify in Chrome", "hotfix repro", or otherwise asks you to take a SciStudio change for a real spin in the browser instead of trusting CI alone. Also trigger when the user hands you a path under docs/ai-developer/e2e/.
metadata:
  type: scistudio-skill
  related_personas: [manager, implementer, test_engineer]
  related_rules:
    - .claude/rules/frontend-smoke-test.md
    - docs/ai-developer/specific_rules/hotfix.md
    - docs/ai-developer/personas/manager.md
language_source: en
---

# Skill — SciStudio E2E Test

## 1. What This Skill Is For

This skill turns a filled e2e scenario file into a real, observed run of
SciStudio: backend up, browser open, every step exercised, every regression
sentinel watched, every artifact captured, and a verdict written back into
the same file.

Use it when:

- The user asks for an e2e on a PR before merging.
- The user is in `hotfix` mode and needs the live repro of a reported bug.
- The user wants the UI driven and observed (Chrome MCP), not just unit
  tests and CI.
- The user hands you a path under `docs/ai-developer/e2e/` and says go.

Do **not** use this skill for:

- Pure CI / shell-only checks (pytest, ruff, mypy, vitest run). Those
  belong in normal implementer flow.
- Static review (read code, read docs). Use the audit-reviewer persona.
- Long-form feature design. Use ADR author.

## 2. Inputs Required Before You Start

You must have, before running anything:

- A scenario file under `docs/ai-developer/e2e/`. If the user did not
  name one, ask which file (or ask them to copy `template.md` to a new
  dated filename first).
- The scenario file's Section 2 (Preconditions) and Section 5 (Steps)
  filled. If they contain `TODO` placeholders, stop and ask the user
  to fill them before you run.

Verify before launch:

- Working tree matches Section 2's expected branch + SHA. Mismatch is
  a hard stop unless the user explicitly overrides.
- No stale Vite / `scistudio gui` process is squatting on the port from
  Section 2 (see `references/dev-server-lifecycle.md`). Kill stale
  processes before launching, **not** during the run.

## 3. The Run Loop

For every e2e session, execute the phases below in order. Each phase
has a clear deliverable; do not collapse them.

### 3.1 Pre-flight

1. Read the scenario file end to end. Do not skim. Step intent matters
   for interpreting Expecteds later.
2. Audit stale processes per `references/dev-server-lifecycle.md`.
3. Mark the scenario `status: running` (edit the frontmatter in place).
4. Note the start timestamp; you will use it in the verdict.

### 3.2 Launch

1. Run the **Backend start** command from Section 3 in the background.
2. Run the **Frontend start** command (if present) in the background.
3. Poll the **Readiness probe** until it succeeds, with a 60s ceiling.
   If it times out, mark the session ABORTED in Section 7, capture
   backend stderr into the Artifacts list, and stop.

### 3.3 Open Chrome

1. Load Chrome MCP via `ToolSearch` if its tools are deferred.
2. Call `tabs_context_mcp` first to see what tabs are open. **Never**
   reuse a tab ID from a prior session.
3. Open a new tab at the backend URL with `tabs_create_mcp`.
4. Activate the tab and verify `document.visibilityState === "visible"`
   before any screenshot — see `references/screenshot-recipes.md` §1
   for the activation sequence. Hidden tabs give you blank screenshots.

### 3.4 Walk The Steps

For each numbered step in Section 5:

1. State out loud (in a user-facing message, one short sentence) which
   step you are starting. The user is watching the Chrome window;
   silence is confusing.
2. Perform the **Action** using Chrome MCP tools (see
   `references/chrome-mcp-recipes.md` for the recipes you will need —
   Monaco direct manipulation, fetch interception, native-dialog
   bypass, alert capture, project-tree button matching).
3. Check the **Expected** by reading the affordance the step names —
   DOM state via `javascript_tool`, network response via
   `read_network_requests`, console message via `read_console_messages`,
   or backend API response via PowerShell `curl`. Do not rely on "it
   looked right" — quote the observed value.
4. Capture the artifacts named in **Capture**. Screenshots use the
   recipe in `references/screenshot-recipes.md`. Save to
   `C:\Users\jiazh\Downloads\scistudio-e2e-<session-id>-step<N>.png` so
   they can be sent to the user's phone via `SendUserFile` if the user
   is remote.
5. Evaluate the regression sentinels in Section 6 immediately after
   the step. A sentinel hit fails the step even if the Expected was
   met.
6. Record the outcome in your own working state:
   `step N: PASS|FAIL — <one-line evidence>`. You will write this into
   Section 7 at the end.
7. On failure, honor the **On failure** policy. Default is `halt`.

### 3.5 Sentinel Sweep

Even outside specific steps, the regression sentinels in Section 6
are continuous. Read `read_console_messages` and `read_network_requests`
between steps to surface things the per-step check missed. A continuous
sentinel hit goes into Section 7.3 with the step number it fired
during.

### 3.6 Cleanup

Always run the cleanup commands from Section 3 of the scenario file,
even on failure or abort. Capture any cleanup errors but do not let
them mask the run verdict.

### 3.7 Write Section 7

Edit the scenario file in place. Fill Section 7 exactly per the
template's headings:

- **7.1 Verdict**: `PASS` only if every step passed and no sentinel
  fired. `FAIL` if any step or sentinel failed. `ABORTED` if pre-flight,
  launch, or Chrome open failed.
- **7.2 Per-Step Outcome**: one row per step with the evidence you
  recorded.
- **7.3 Sentinel Hits**: every hit with the step it fired during.
- **7.4 Artifacts**: absolute paths to every screenshot, console dump,
  network log, GIF you produced.
- **7.5 Follow-Ups**: any out-of-scope bugs you saw. Open them as
  issues per the bug-fix specific rule and link the issue numbers
  here.

Set `status:` in the frontmatter to `passed`, `failed`, or `aborted`
to match the verdict.

### 3.8 Report Back

Use the report template in `references/report-template.md` for the
final user-facing message. Keep it short: verdict, link to the scenario
file, one-line summary of any failures. If the user is remote, push
the headline screenshot to their phone via `SendUserFile` with
`status: proactive` (see `references/screenshot-recipes.md` §3).

## 4. Mode Variants

These are minor variations on the loop above. They share Section 3
but adjust pre-flight, sentinels, or post-run handling.

### 4.1 PR Readiness Mode

Trigger: `trigger.kind: pr-readiness` in the scenario.

Additions:

- Before launching, verify the PR's CI is green via
  `gh pr view <N> --json statusCheckRollup`. Do not run an e2e against
  a PR with red CI — fix CI first, or get explicit user override.
- After the run, if PASS, add a comment to the PR via `gh pr comment <N>`
  linking the scenario file and pasting the 7.1 verdict + 7.2 table.
- Do **not** merge the PR. Merging is a user action; this skill never
  merges.

### 4.2 Hotfix Repro Mode

Trigger: `trigger.kind: hotfix-repro` in the scenario, OR the user is
already in hotfix mode (see `docs/ai-developer/specific_rules/hotfix.md`).

Additions:

- Read the ADR(s) named in the scenario's `related_adrs` before
  launching. The hotfix entry ritual (re-read governing artifacts)
  applies here too — quote the section you read in your first
  step-start message.
- The point of a hotfix repro is to **fail** the run on `main` or on
  the buggy branch and **pass** it on the fix branch. A `PASS` verdict
  before the fix is a sign you did not actually reproduce the bug.
  Add a note in 7.5.
- Skip the Pre-Flight CI check; hotfix mode bypasses gates per
  CLAUDE.md §11.5.

### 4.3 Regression Check Mode

Trigger: `trigger.kind: regression-check`.

Additions:

- The scenario lists a previously-fixed bug. The run should PASS. A
  FAIL here is a regression — open a new issue immediately and link
  it in 7.5 with `regression: true` in the body.

## 5. Non-Negotiables

These rules come from prior incidents. Violating them silently regresses
work the user already did.

- **Never run `npm run dev` without a `Stop-Process` in cleanup.** Stale
  Vite servers from prior sessions serve old code from deleted worktrees
  and have caused multiple "the UI didn't change" debugging sessions.
  See `references/dev-server-lifecycle.md`.

- **Never trust a screenshot without checking `document.visibilityState`.**
  A hidden Chrome tab still responds to DOM JS but paints nothing. The
  screenshot will show whichever other tab IS active — usually a blank
  cream block. See `references/screenshot-recipes.md` §1.

- **Never click a button that may open a native dialog without hooking
  `window.alert` / `window.confirm` first.** Native dialogs freeze Chrome
  MCP and the only recovery is the user manually dismissing in their
  browser. See `references/chrome-mcp-recipes.md` §3.

- **Never declare a step passed because "code looks right + unit test
  passes".** Live runtime evidence is the bar. CI green is necessary
  but not sufficient — multiple PRs have shipped fully broken features
  with all CI green because unit tests asserted on internal state, not
  on the real DOM/event flow.

- **Never modify the scenario's Sections 1–6.** Those are the user's
  intent and acceptance criteria. You write only Section 7 and the
  frontmatter `status`. If the user's scenario is wrong or unclear,
  stop and ask — do not rewrite their spec.

- **Never run an e2e that mutates shared infra** (production data, the
  user's real ANTHROPIC account quota, network shares) without the
  scenario file naming the exact resource and the user authorizing it
  in chat. E2E sessions are normally hermetic — local backend, local
  Chrome, local data fixtures.

## 6. When You Must Stop And Ask

Auto mode does not relieve you of these:

- Scenario file has `TODO` placeholders in Sections 1–6 → stop.
- Working tree does not match Section 2's expected SHA → stop unless
  the user has overridden in this turn.
- Backend readiness probe times out at 60s → stop, do not retry blindly.
- Chrome MCP tabs context shows a tab you do not recognize and the
  scenario does not name a target window → ask which window to use.
- Step's Action would mutate a shared resource you cannot identify as
  local → stop.
- You hit two consecutive failures of the same Chrome MCP tool → stop
  and surface the error per the "Avoid rabbit holes" guidance in the
  Chrome MCP system prompt.

## 7. Where The Rest Of This Skill Lives

- `references/chrome-mcp-recipes.md` — Monaco model manipulation, fetch
  interception, alert capture, project-tree button matching, native
  dialog bypass. Read whichever section the current step needs.

- `references/dev-server-lifecycle.md` — backend/frontend start/stop,
  port selection, stale-process audit, editable-install restart rules.

- `references/screenshot-recipes.md` — DPI-aware capture, multi-monitor
  bounds, Chrome tab activation, sending to user's phone.

- `references/report-template.md` — the final user-facing summary
  format.

## 8. Related Documents

- `docs/ai-developer/e2e/template.md` — the scenario template the user
  fills before invoking this skill.
- `docs/ai-developer/e2e/README.md` — workflow and naming conventions
  for scenario files.
- `docs/ai-developer/personas/manager.md` — manager persona owns
  coordinated e2e and PR readiness sweeps.
- `docs/ai-developer/specific_rules/hotfix.md` — hotfix rules govern
  hotfix-repro mode.
- `.claude/rules/frontend-smoke-test.md` — repo-wide rule for when a
  smoke check is required at all.
- `AGENTS.md` §2 — the broader "how to work here" guide.
