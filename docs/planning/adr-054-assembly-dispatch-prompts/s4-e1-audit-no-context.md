---
title: "ADR-054 Assembly Dispatch — S4-E1 No-Context Audit Of The Explore Frontend"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# S4-E1 — No-Context Audit Of The Explore Frontend

```markdown
[DISPATCH-TEMPLATE-V1: audit-no-context]

## Task Identity

- Repository: SciStudio
- Persona: audit_reviewer
- Audit mode: no-context
- Audit branch: audit/2253-no-context
- Audit worktree: .worktrees/s4-e1
- Allowed audit surfaces:
  - `frontend/src/explore/**`
  - `frontend/src/store/exploreSlice.ts` and `frontend/src/store/types.ts`
  - `frontend/src/types/api.ts`, `frontend/src/types/ui.ts`
  - `frontend/src/App.tsx`, `frontend/src/App.parts/ProjectWorkspace.tsx`
  - `frontend/src/hooks/useWebSocket.parts/**`
  - `frontend/src/components/WorkflowCanvas*`, `nodes/BlockNode.tsx`,
    `ProjectTree*`, `BlockPalette*`, `DataPreview.tsx`
  - `frontend/e2e/**`
  - `docs/adr/ADR-054.md` and `docs/specs/adr-054-explore-frontend.md`
  - `docs/specs/adr-054-panel-contract.md` and
    `docs/specs/adr-054-explore-session.md`, as the contracts the frontend
    consumes
  - `src/scistudio/api/routes/explore.py`, `src/scistudio/api/routes/panels.py`
    and `src/scistudio/api/ws.py`, **read-only**, as the server side of every
    wire the frontend claims to speak
- Audit report path: `docs/audit/<YYYY-MM-DD>-adr-054-spec4-no-context.md`

## Context Limits

You are a no-context auditor. You must not read or use:

- Any GitHub issue, PR description, PR comment, or commit message for this
  work. Do not run `gh`. Do not read `git log` messages for the branches under
  audit.
- `docs/planning/adr-054-assembly-checklist.md`.
- `docs/planning/adr-054-assembly-dispatch-prompts/**` other than this file.
- `docs/planning/adr-054-assembly-followups.md`.
- `.workflow/records/**`.
- Any manager summary of what changed.

You may read only:

- Repository docs, code and tests, as bounded by the audit surfaces above.
- Generated facts and audit outputs already committed in the repository.
- Tool output from commands you run yourself.

This limit is the point of the dispatch. A with-context auditor reads the
claim and checks it; you read the repository and form your own. Where those
two disagree is where the value is, and you cannot produce that if you have
read the claim.

## Required Reading

- `AGENTS.md`
- `docs/ai-developer/rules.md`
- `docs/ai-developer/personas/audit-reviewer.md`
- The governing ADR and specs discovered from the surfaces above.

## Audit Goal

Independently check whether the documents, the code, the tests and the
declared contracts agree. Do not assume what anyone intended to build.

Look hardest for:

- **A wire the two sides disagree about.** The frontend's `types/api.ts` and
  the server's response models are written by different hands. Compare them
  field by field for every session, panel and event payload. A hand-written
  frontend fixture that agrees with the frontend code while both disagree with
  what the server actually sends is a known, repeated failure mode in this
  repository — look for it specifically, and check the fixtures, not just the
  types.
- **Runtime truth held in the frontend.** The specs forbid the frontend from
  computing a mark, a kernel state or a binding. Find any place it does —
  including a derivation that looks like presentation, a default that
  substitutes for an unreceived event, or an optimistic update applied before
  its event arrives.
- Docs that claim behaviour the code does not implement.
- Code behaviour no governing document describes.
- Tests missing for documented contracts, and tests that assert the
  implementation rather than the contract.
- Spec-governed paths that do not exist, or exist at a different path.
- A deleted surface something still imports.
- Generated docs edited by hand.

## Coordination

- MUST work only on `audit/2253-no-context` in `.worktrees/s4-e1`.
- MUST NOT use `pip install -e .`.
- MUST NOT merge any PR.
- MUST NOT edit implementation files. You are read-only apart from your report.
- MUST NOT edit any checklist.
- MUST write the audit report to the repository path above and commit it.
  A finding that exists only in chat is not a finding.

## Checks

Run yourself, and report what they actually said:

- `npm run test`, `npm run lint`, `npm run build` in `frontend/`.
- `PYTHONPATH=./src python -m pytest tests/api tests/panels -q --no-cov`
- Any targeted command your findings need.
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr` for your
  own branch's ledger reconciliation. This needs no manager context.

## Output Required

- The audit report path, and the commit that contains it.
- Findings ordered by severity, each with evidence from docs, code, tests or
  tool output — a file and line, or a command and its output. Never a claim
  alone.
- No statement about anyone's intent unless it is visible in a repository
  document.
- A recommendation: `pass`, `pass-with-fixes`, or `block`.

## Stop Conditions

Stop and report back if:

- You are asked to read issue, checklist, PR or manager context.
- The audit cannot proceed without hidden context.
- You need to edit implementation code.
```
