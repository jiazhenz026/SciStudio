---
title: "ADR-054 Assembly Dispatch — S4-D1 Adversarial Testing Of The Explore Frontend"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# S4-D1 — Adversarial Tests Against The Assembled Explore Frontend

```markdown
[DISPATCH-TEMPLATE-V1: test_engineer]

## Task Identity

- Repository: SciStudio
- Owner request: Try to break ADR-054 spec 4's Explore frontend. Write the
  tests that fail, and report what they prove.
- Task kind: feature
- Persona: test_engineer
- Issue: #2253
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2253
- Umbrella PR: #2255 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-054-integration
- Track branch (your PR base): track/adr-054-spec4-explore-frontend
- Agent branch: test/2253-adversarial
- Agent worktree: .worktrees/s4-d1
- Gate record: .workflow/records/2253-test-2253-adversarial.json
- Checklist: docs/planning/adr-054-assembly-checklist.md
- Shared preamble: docs/planning/adr-054-assembly-dispatch-prompts/_common.md
  — read it first.

## Required Rules

Everything in the shared preamble, plus:

- `docs/ai-developer/personas/test-engineer.md`
- `docs/ai-developer/specific_rules/test-engineering.md`
- `docs/specs/adr-054-explore-frontend.md` — the contract you test against.

## Scope

**Production code is out of scope by default for a `test_engineer` dispatch.**
You own only:

- `frontend/src/**/*.test.ts` and `*.test.tsx` — new adversarial files, and
  additions to existing ones.
- `frontend/src/**/__fixtures__/**` and any test fixture directory.
- `frontend/e2e/**` — scenarios and their fixtures.
- `docs/planning/adr-054-assembly-followups.md` — under `## S4-D1`.

You must not touch:

- Any non-test file under `frontend/src/**`. If a test proves a defect, the
  test is your deliverable and the fix is the manager's to dispatch. **Do not
  fix it yourself, and do not weaken the test until it passes.**
- Every `src/scistudio/**` path.

If a finding can only be proven by changing production code, stop and report.

## TODO And Deferral Rule

Per the shared preamble. Do not open an issue; append to
`docs/planning/adr-054-assembly-followups.md` under `## S4-D1`.

## Your Posture

You are not here to confirm the implementation works. Four agents already
wrote tests that pass. You are here to find what those tests were shaped not
to ask. Assume every agent tested the path it had in mind and stopped there.

Read the spec's §4.5 risk list first — it is the implementers' own statement
of what they were worried about, which makes it a map of where they were
careful and, by omission, where they were not.

## Where To Push

Starting points, not a checklist. Follow what you find.

1. **The one-source-of-truth rule (FR-034).** The frontend must never hold
   runtime truth. Construct a state where a locally-derived mark, kernel state
   or binding would differ from the runtime's — a cell-state event arriving
   after a conflicting response, a binding that exists in the analysis but not
   in the kernel, a kernel that dies mid-run — and assert the frontend shows
   the runtime's answer. A frontend that quietly recomputes passes every
   happy-path test and fails exactly here.
2. **Event ordering.** §4.5 claims events apply idempotently by cell id and
   state so order does not matter. Test it: deliver every session event type
   out of order, duplicated, and interleaved across two sessions. Deliver a
   cell-state event **before** the response to the command that caused it.
   Deliver events for a session whose tab has been closed.
3. **Editor virtualisation (FR-008).** Prove only visible cells carry editors
   on a notebook of a few hundred cells, and that a draft in a cell scrolled
   out of view and back is still there. Then scroll fast, edit during a
   scroll, and delete the cell being edited.
4. **The output renderer (FR-011).** Feed it malformed MIME bundles: an
   unknown type with no text fallback, HTML that tries to escape the sandbox,
   an image with a corrupt payload, a traceback with ANSI sequences that do
   not terminate, an output larger than anything reasonable. It must degrade,
   not take the shell down with it.
5. **The pause tab (FR-024, FR-025).** The claim is that confirm and cancel
   send exactly what the modal sent, so the backend path is unchanged. Verify
   against the deleted modal's actual message shapes — read them out of git
   history if they are gone from the tree. Then: confirm twice, cancel after
   confirm, close the tab without answering, receive a second prompt while one
   is open.
6. **The submission freeze (FR-023).** While a cell runs, submissions from
   panels bound to a name in the changed set are refused and reading
   continues. Test the boundary: a panel bound to a name that enters the
   changed set mid-run; a run that fails; a run that is interrupted; two
   panels bound to the same name.
7. **The refresh scoping (FR-022).** Only panels bound to changed names
   refresh. Prove an unbound panel does **not**, including when the changed
   set is empty and when it names something no panel is bound to.
8. **Packaging (FR-028).** Confirm must be impossible with refusals present.
   Try to reach it anyway: a report that arrives twice, refusals that arrive
   after confirm is enabled, a package command sent while a check is in flight.
9. **The tab identity (FR-001).** Tabs are keyed by notebook path. Open the
   same session twice, open a session whose notebook is renamed underneath,
   reload with a session tab open whose session has since closed.

## Required Tests And Checks

- Every test you add must state in its docstring **what it proves and why the
  existing tests did not**. A test that duplicates coverage is noise.
- A failing test is a **success** for this dispatch. Leave it failing, mark it
  clearly, and report it. Do not `xfail` it into silence without saying so in
  your report and in the follow-up register.
- `npm run test`, `npm run lint` in `frontend/`.
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr
  --base track/adr-054-spec4-explore-frontend --head HEAD
  --pr-body-file .workflow/local/pr-body.md`
- Pre-PR `finalize`, `python scripts/scistudio_pr_create.py`, post-PR
  `finalize`. Base your PR on `track/adr-054-spec4-explore-frontend`.
- Docs: `--docs-na "user-docs:the human documentation revision is ADR-054
  spec 6, issue #2236"`.

## Output Required

Per the shared preamble. Additionally:

- Every defect found, with the test that proves it and a severity.
- Every place you pushed and found the implementation correct — a negative
  result is evidence too, and it tells the manager where not to look again.

## Stop Conditions

Per the shared preamble. Additionally: stop if proving a finding requires
changing production code.
```
