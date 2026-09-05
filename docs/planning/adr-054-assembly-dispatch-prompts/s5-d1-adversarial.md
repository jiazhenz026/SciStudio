---
title: "ADR-054 Assembly Dispatch — S5-D1 Adversarial Testing Of The Agent Surface"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# S5-D1 — Adversarial Tests Against The Assembled Agent-Enablement Surface

```markdown
[DISPATCH-TEMPLATE-V1: test_engineer]

## Task Identity

- Repository: SciStudio
- Owner request: Try to break ADR-054 spec 5's workspace focus, panel tools
  and session tools. Write the tests that fail, and report what they prove.
- Task kind: feature
- Persona: test_engineer
- Issue: #2254
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2254
- Umbrella PR: #2255 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-054-integration
- Track branch (your PR base): track/adr-054-spec5-agent-enablement
- Agent branch: test/2254-adversarial
- Agent worktree: .worktrees/s5-d1
- Gate record: .workflow/records/2254-test-2254-adversarial.json
- Checklist: docs/planning/adr-054-assembly-checklist.md
- Shared preamble: docs/planning/adr-054-assembly-dispatch-prompts/_common.md
  — read it first.

## Required Rules

Everything in the shared preamble, plus:

- `docs/ai-developer/personas/test-engineer.md`
- `docs/ai-developer/specific_rules/test-engineering.md`
- `docs/specs/adr-054-agent-enablement.md` — the contract you test against.

## Scope

**Production code is out of scope by default for a `test_engineer` dispatch.**
You own only:

- `tests/ai/**`, `tests/agent_provisioning/**` — new adversarial files, and
  additions to existing ones.
- Test fixtures and scripted-API stubs under those trees.
- `docs/planning/adr-054-assembly-followups.md` — under `## S5-D1`.

You must not touch:

- Every `src/scistudio/**` path. If a test proves a defect, the test is your
  deliverable and the fix is the manager's to dispatch. **Do not fix it
  yourself, and do not weaken the test until it passes.**
- Every `frontend/**` path.

If a finding can only be proven by changing production code, stop and report.

## TODO And Deferral Rule

Per the shared preamble. Do not open an issue; append to
`docs/planning/adr-054-assembly-followups.md` under `## S5-D1`.

## Your Posture

Four agents already wrote tests that pass. You are here to find what those
tests were shaped not to ask.

The owner stated one hard requirement for this whole spec: **the agent must
always know whether the person is on the canvas or in an explore session.**
Everything else in spec 5 is in service of that. So the question that matters
most is: *is there a state in which the agent believes it knows where the
person is, and is wrong?* Spend your first effort there.

Read the spec's §4.5 risk list — it is the implementers' own statement of what
worried them, and by omission a map of what did not.

## Where To Push

Starting points, not a checklist.

1. **A focus that lies (FR-001 to FR-004).** The focus is persisted, restored,
   and reported. Between those three there is room for a stale answer. Try:
   the backend restarted between the report and the read; the project file
   edited or truncated underneath; two projects open; a focus reported for a
   workflow that no longer exists; a focus reported for a session that closes
   a moment later; a report that arrives out of order with a previous one; a
   report with a mode the backend does not know.
   FR-004 says a focus naming a missing notebook reads as **stale**. Find the
   window between "the notebook is gone" and "the focus says so".
2. **The refusal as the enforcement (FR-005).** The spec is explicit that the
   skill's rule is advice and the tools' refusal is the guarantee. So: call
   every session tool with the focus on canvas, with a stale focus, with no
   focus ever reported, with an explicit session path that does not exist,
   with an explicit path that exists but is not a session, and with an
   explicit path pointing outside the project. Each must refuse, and the
   refusal must say **how to open a session** — assert the message content,
   not merely that an exception was raised.
3. **The thinness rule (FR-024).** A session tool must go through the session
   API and must not reach the kernel, the notebook file, or the queue
   directly. This is a structural claim. Assert it structurally — over the
   import graph and the call graph of every module under `tools_explore/`,
   at every depth, including imports written lazily inside functions, which is
   where a shortcut would actually be written.
4. **`open_explore_session` must not change the focus (FR-019).** The person's
   focus is the person's. Assert the focus before and after, including when
   the open fails, when it opens a session that already exists, and when it is
   called twice.
5. **The harness (FR-015).** The spec's own §4.5 names harness drift as a
   risk and claims the mitigation is that it is generated from the same
   contract module the host uses. Test the claim: change the contract module's
   message names in a fixture and assert the harness follows or the test
   fails. A harness that has hand-copied the contract will pass a
   does-it-render test and fail this one.
6. **The counts (FR-025) and the catalogs (FR-026).** Eleven tools, two
   groups, four places the skill count lives. Assert the count is derived from
   the registry rather than restated — a test that hardcodes 11 in a second
   place is the same bug the requirement exists to prevent. Assert every
   registered tool appears in every catalog, and that a tool added without a
   catalog entry fails the suite.
7. **Scaffolding into a tier (FR-014).** Scaffold into a tier that does not
   exist, into one that is read-only, twice with the same name, with a target
   type that is not registered, with a capability the type cannot support.
8. **`run_cell` and `package_notebook` refusals (FR-021, FR-023).** Both
   return a refusal as a **result**. Prove the refusal is not swallowed,
   re-raised, or reported as success — including when the queue refuses for a
   reason the tool did not anticipate.

## Required Tests And Checks

- Every test must state in its docstring **what it proves and why the existing
  tests did not**.
- A failing test is a **success** for this dispatch. Leave it failing, mark it
  clearly, and report it.
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr
  --base track/adr-054-spec5-agent-enablement --head HEAD
  --pr-body-file .workflow/local/pr-body.md`
- Pre-PR `finalize`, `python scripts/scistudio_pr_create.py`, post-PR
  `finalize`. Base your PR on `track/adr-054-spec5-agent-enablement`.
- Docs: `--docs-na "user-docs:the human documentation revision is ADR-054
  spec 6, issue #2236"`.

## Output Required

Per the shared preamble. Additionally:

- Every defect found, with the test that proves it and a severity.
- Every place you pushed and found the implementation correct.

## Stop Conditions

Per the shared preamble. Additionally: stop if proving a finding requires
changing production code.
```
