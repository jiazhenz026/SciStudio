---
title: "ADR-054 Spec 2 Dispatch Prompt: S2-F1 Findings Fix"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# S2-F1 — Findings Fix

Filled from `docs/ai-developer/templates/agent-dispatch-prompt-template.md`.

```markdown
[DISPATCH-TEMPLATE-V1: fix]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-054 spec 2 in full, with a final adversarial test engineer and a no-context auditor.
- Task kind: bugfix
- Persona: implementer
- Issue: #2231
- Umbrella PR: #2232 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-054-spec2-dependency-analysis
- Agent branch: fix/2231-audit-findings
- Agent worktree: C:/Users/jiazh/workspace/SciStudio/.worktrees/s2-f1-fix
- Gate record: .workflow/records/2231-fix-2231-audit-findings.json
- Checklist: docs/planning/adr-054-spec2-dependency-analysis-checklist.md

## Required Rules

- The GitHub issue `#2231`.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/bug-fix.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/personas/implementer.md
- **docs/specs/adr-054-notebook-dependency-analysis.md**
- The audit reports under `docs/audit/` named in your dispatch message, and the
  adversarial test engineer's findings list.

## Scope

You own only:

- `src/scistudio/explore/**`
- `tests/explore/**`
- `.workflow/records/2231-fix-2231-audit-findings.json`

You must not touch:

- `docs/audit/**` — the audit reports are evidence and are not edited by the
  agent fixing what they found.
- `tests/architecture/**` unless the manager explicitly assigns it in your
  dispatch message.
- Every other path.

## Coordination

- MUST work only on your assigned branch and worktree.
- MUST NOT use `pip install -e .`. `PYTHONPATH=./src` on every python call.
- **Do not open a pull request.** Commit, push your branch, and report.
- Edit only your checklist rows (`S2-F1` in §6).

## TODO And Deferral Rule

Use `TODO(#NNN): <reason>` citing an issue for anything deferred. A P3 finding
you are told to defer needs a tracked follow-up issue, not a chat mention.

## Work To Do

1. Fix every P1 finding. A P1 is not closed until a test that failed before your
   change passes after it.
2. Fix every P2 finding, or state precisely why it should be deferred and open
   the follow-up issue.
3. For each P3, either fix it or record a `TODO(#NNN)` citing a follow-up issue.
4. Where a finding is that a test asserts less than it claims, strengthen the
   test — do not weaken it to pass.
5. **Never weaken a test, a threshold, or a check to make something pass.** If a
   finding cannot be fixed without doing that, stop and report.
6. For each finding, record in your report: the finding, the fix, the test that
   now covers it, and the commit.

## Required Tests And Checks

- `PYTHONPATH=./src python -m pytest tests/explore tests/architecture/test_layer_deps.py -q`
- `PYTHONPATH=./src python -m ruff check src/scistudio/explore tests/explore`
- `PYTHONPATH=./src python -m mypy src/scistudio/explore`
- `PYTHONPATH=./src python -m scistudio.qa.governance.gate_record check --mode local --base origin/track/adr-054-spec2-dependency-analysis --head HEAD`
- Record `--base-ref origin/track/adr-054-spec2-dependency-analysis` at `init`.
- `git add -A` before every commit. Trailers: `Gate-Record:`,
  `Task-Kind: bugfix`, `Issue: #2231`, `Assisted-by: Claude:claude-opus-5`.

## Output Required

- A finding-by-finding table: finding, severity, fix, covering test, commit.
- Changed file paths.
- Exact pytest summary line.
- Your branch head sha.
- Anything you did not fix and why.

## Stop Conditions

Stop and report back if a finding cannot be fixed without weakening a test or a
check, if a finding contradicts the spec, or if two findings contradict each
other.
```
