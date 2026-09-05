---
title: "ADR-054 Assembly Dispatch — INT-E1 No-Context Audit Of The Assembled Whole"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# INT-E1 — No-Context Audit Of The Assembled ADR-054

```markdown
[DISPATCH-TEMPLATE-V1: audit-no-context]

## Task Identity

- Repository: SciStudio
- Persona: audit_reviewer
- Audit mode: no-context
- Audit branch: audit/2255-assembly-no-context
- Audit worktree: .worktrees/int-e1
- Allowed audit surfaces: the whole repository as it stands on your branch.
  The subject is ADR-054 as a **single assembled feature**, not any one part
  of it.
- Audit report path: `docs/audit/<YYYY-MM-DD>-adr-054-assembly-no-context.md`

## Context Limits

You are a no-context auditor. You must not read or use:

- Any GitHub issue, PR description, PR comment, or commit message for this
  work. Do not run `gh`. Do not read `git log` messages for the ADR-054
  branches.
- `docs/planning/adr-054-assembly-checklist.md`.
- `docs/planning/adr-054-assembly-dispatch-prompts/**` other than this file.
- `docs/planning/adr-054-spec2-*` and `docs/planning/adr-054-spec3-*`.
- `docs/planning/adr-054-assembly-followups.md`.
- `.workflow/records/**`.
- `docs/audit/**` written for this work — you may note that a report exists,
  but do not let another auditor's conclusions shape yours. Read them, if at
  all, only **after** you have written your own findings, and say so if you
  did.
- Any manager summary of what changed.

You may read only:

- Repository docs, code and tests.
- Generated facts already committed in the repository.
- Tool output from commands you run yourself.

## Required Reading

- `AGENTS.md`
- `docs/ai-developer/rules.md`
- `docs/ai-developer/personas/audit-reviewer.md`
- `docs/adr/ADR-054.md` and every `docs/specs/adr-054-*.md`.
- `docs/architecture/ARCHITECTURE.md`, as the statement of what the system is
  supposed to be. It is owner-controlled and **read-only** to you.

## Audit Goal

Six specs were written for ADR-054 and five of them are implemented on this
branch. Each was built separately. Your subject is what happens **between**
them — the seams, not the pieces. Each piece has already been checked on its
own; if you spend your effort re-checking one, the dispatch has wasted you.

The specific question: **does this assemble into the one feature ADR-054
describes, or into five features that happen to compile together?**

Look hardest for:

1. **A contract two specs implement differently.** The panel contract is
   defined once and consumed by the previewer path, the interactive-block
   path, the explore panels, and the agent's scaffolding tool. Check that all
   four speak the same contract, at the same version, with the same field
   names. The same question for the session API: the frontend, the agent's
   session tools, and the packaging path all call it.
2. **A wire whose two ends disagree.** Backend response models and frontend
   types are written by different hands, and a hand-written frontend fixture
   that agrees with the frontend code while both disagree with what the server
   sends is a known, repeated failure mode in this repository. Compare the
   models to the types field by field, and check the fixtures against the
   models rather than against the types.
3. **A retired thing that is still reachable.** ADR-054 retires an
   interactive modal, an ES-module panel form, an asset route, and a second
   API version. Search for every one of them by name across code, tests, docs,
   fixtures and skills. Something that still imports, still routes to, still
   documents or still teaches a retired form is a finding.
4. **Two sources for one truth.** The ADR is explicit that a mark, a kernel
   state and a binding are computed by the runtime and only drawn elsewhere.
   Find any second computation, including one that looks like a default or a
   presentation convenience.
5. **A layering the assembly broke.** `tests/architecture/` states the layer
   rules. Run it. Then read it: a rule that was relaxed to let a new subsystem
   compile is a finding even when the suite is green.
6. **Something declared and not built.** Every spec's `governs` and `tests`
   frontmatter names paths. Check each one exists and is what it claims. An
   ADR that lists a test file no longer at that path, or governs a module that
   was renamed, is exactly what this audit is for.
7. **A deferral that is not tracked.** Search the whole diff against
   `origin/main` for `TODO`, `FIXME`, `XXX`, `later`, `for now`, `MVP` and
   `V1`. Each must cite an issue or a tracked reference. An untracked one is a
   gate failure, not a style note.
8. **Documentation that is now wrong.** ADR-054 changes vocabulary that the
   `docs/package-development/` guides and the generated reference teach. Some
   of that revision is deliberately deferred to a later tranche — note what is
   inaccurate today and be precise about whether it is a gap or a defect.

## Coordination

- MUST work only on `audit/2255-assembly-no-context` in `.worktrees/int-e1`.
- MUST NOT use `pip install -e .`. Use `PYTHONPATH=./src`.
- MUST NOT merge any PR.
- MUST NOT edit implementation files. You are read-only apart from your report.
- MUST NOT edit any checklist.
- MUST write the audit report to the repository path above and commit it.

## Checks

Run yourself, and report what they actually said. Where a suite fails, say
whether it also fails on `origin/main` — a pre-existing failure and a new one
are different findings.

- `PYTHONPATH=./src python -m pytest tests/ -q --no-cov -x --ignore=tests/blocks/io`
  (and then the parts you excluded, separately, so one failure does not hide
  the rest)
- `PYTHONPATH=./src python -m pytest tests/architecture tests/docs -q --no-cov`
- `npm run test`, `npm run lint`, `npm run build` in `frontend/`
- `ruff check .` and `ruff format --check .`
- `mypy src/scistudio/ --ignore-missing-imports`
- `lint-imports`
- `python scripts/audit/generate_facts.py --check`
- `python -m scistudio.qa.governance.gate_record check --mode pre-pr` for your
  own branch's ledger.

## Output Required

- The audit report path, and the commit that contains it.
- Findings ordered by severity, each with evidence — a file and line, or a
  command and its output. Never a claim alone.
- For each finding, say explicitly whether it is a **seam** defect (between
  two specs) or a defect **inside** one. The seam findings are why you exist.
- A recommendation: `pass`, `pass-with-fixes`, or `block`.

## Stop Conditions

Stop and report back if:

- You are asked to read issue, checklist, PR or manager context.
- The audit cannot proceed without hidden context.
- You need to edit implementation code.
```
