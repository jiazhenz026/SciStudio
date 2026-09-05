---
title: "ADR-054 Assembly Dispatch — S5-E1 No-Context Audit Of The Agent Surface"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# S5-E1 — No-Context Audit Of The Agent-Enablement Surface

```markdown
[DISPATCH-TEMPLATE-V1: audit-no-context]

## Task Identity

- Repository: SciStudio
- Persona: audit_reviewer
- Audit mode: no-context
- Audit branch: audit/2254-no-context
- Audit worktree: .worktrees/s5-e1
- Allowed audit surfaces:
  - `src/scistudio/ai/agent/mcp/**`
  - `src/scistudio/api/routes/ai.py`, `src/scistudio/api/runtime/_projects.py`
  - `src/scistudio/_skills/**`
  - `src/scistudio/_agent_reference/**`
  - `src/scistudio/agent_provisioning/**`
  - `tests/ai/**`, `tests/agent_provisioning/**`
  - `docs/adr/ADR-054.md` and `docs/specs/adr-054-agent-enablement.md`
  - `docs/specs/adr-054-panel-contract.md`,
    `docs/specs/adr-054-explore-session.md` and
    `docs/specs/embedded-coding-agent-spec.md`, as the contracts this surface
    consumes and catalogs
  - `src/scistudio/explore/**` and `src/scistudio/panels/**`, **read-only**, as
    the runtimes the tools call
- Audit report path: `docs/audit/<YYYY-MM-DD>-adr-054-spec5-no-context.md`

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

- **A tool that can act on the wrong thing.** The governing document states
  one hard requirement: the agent must always know whether the person is on
  the canvas or in an explore session. Find any path by which a tool acts on a
  session the person is not in, or reports a focus that is no longer true.
  Persistence, restoration and reporting are three separate steps and a stale
  answer can live between any two of them.
- **A tool that reaches past the API it is supposed to be thin over.** The
  spec forbids a session tool from touching the kernel, the notebook file or
  the queue directly. Check the import graph and the call graph at every
  depth, including imports written inside functions.
- **A count restated rather than derived.** The tool counts and the skill
  count each live in several places. Find one that was moved in some places
  and not others, and find any assertion that hardcodes a number a registry
  could have told it.
- **A document that teaches a retired form.** The panel section of the agent
  reference was supposed to stop describing an older panel form. Check that
  nothing under `_agent_reference/**` or `_skills/**` still teaches it, and
  that the reference describes what the panel code actually does rather than
  what a spec says it should.
- **A skill carrying inline code.** The governing document says skills stay
  short and carry none; contracts belong in the reference, worked patterns in
  the examples corpus.
- **A harness that has drifted from the host.** If a scaffolded panel ships a
  harness that stands in for the host's side of a message contract, check
  whether it is generated from the same module the host uses or hand-copied
  from it. Hand-copied is a finding.
- Docs claiming behaviour the code does not implement; code behaviour no
  document describes; tests missing for documented contracts; spec-governed
  paths that do not exist; generated docs edited by hand.

## Coordination

- MUST work only on `audit/2254-no-context` in `.worktrees/s5-e1`.
- MUST NOT use `pip install -e .`. Use `PYTHONPATH=./src`.
- MUST NOT merge any PR.
- MUST NOT edit implementation files. You are read-only apart from your report.
- MUST NOT edit any checklist.
- MUST write the audit report to the repository path above and commit it.
  A finding that exists only in chat is not a finding.

## Checks

Run yourself, and report what they actually said:

- `PYTHONPATH=./src python -m pytest tests/ai tests/agent_provisioning -q --no-cov`
- `PYTHONPATH=./src python -m pytest tests/architecture -q --no-cov`
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
