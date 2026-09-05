---
title: "ADR-054 Spec 2 Dispatch Prompt: S2-G1 The planned_governs Migration"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 42
  - 54
language_source: en
---

# S2-G1 — The `planned_governs` Migration

Filled from `docs/ai-developer/templates/agent-dispatch-prompt-template.md`.

Three implementers independently hit the same wall and correctly refused to
widen their own scope to clear it: creating `src/scistudio/explore/` makes the
`planned_governs` entries in ADR-054 and in the spec resolve, and `full_audit`
requires a resolved entry to move into `governs`. `full_audit` is owned by
`ci.yml`, so `--check-na` records a rationale and still blocks. No implementer's
write set covers governance front matter, and the move cannot be pre-applied on
a branch without the package, because the audit then fails the other way. This
dispatch exists to make that move once, as its own reviewable change.

```markdown
[DISPATCH-TEMPLATE-V1: adr_author]

## Task Identity

- Repository: SciStudio
- Owner request: Implement ADR-054 spec 2 in full; the owner pre-approved every label and approval this work needs.
- Task kind: docs
- Persona: adr_author
- Issue: #2231
- Issue URL: https://github.com/jiazhenz026/SciStudio/issues/2231
- Umbrella PR: #2232 `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: track/adr-054-spec2-dependency-analysis
- Agent branch: docs/2231-governs-migration
- Agent worktree: C:/Users/jiazh/workspace/SciStudio/.worktrees/s2-g1-governs
- Gate record: .workflow/records/2231-docs-2231-governs-migration.json
- Checklist: docs/planning/adr-054-spec2-dependency-analysis-checklist.md

## Required Rules

Read and follow:

- The GitHub issue `#2231`.
- AGENTS.md
- docs/ai-developer/rules.md
- docs/ai-developer/specific_rules/agent-dispatch.md
- docs/ai-developer/specific_rules/gated-workflow.md
- docs/ai-developer/specific_rules/docs-change.md
- docs/ai-developer/specific_rules/document-standards.md
- docs/ai-developer/personas/adr-author.md
- **docs/specs/adr-054-notebook-dependency-analysis.md**
- docs/adr/ADR-054.md, especially §11, whose text says this ADR "governs no
  implementation yet" and which stops being true when you are done.

## Scope

You own only:

- `docs/adr/ADR-054.md` — front matter, and the one sentence in §11 that the
  front-matter change makes false.
- `docs/specs/adr-054-notebook-dependency-analysis.md` — front matter only.
- `.workflow/records/2231-docs-2231-governs-migration.json`

You must not touch:

- Any file under `src/` or `tests/`.
- `docs/specs/adr-054-explore-session.md` and every other ADR-054 spec — spec 3
  makes its own move on its own branch. Touching it here fails the audit the
  other way, because the files it names do not exist on this branch.
- `docs/architecture/**` — owner-controlled.
- Every other path.

**`docs/adr/ADR-054.md` carries `agent_editable: false`.** The owner
pre-approved every approval this work needs, and this specific edit is the one
the ADR itself prescribes: §11 says "the surfaces in `planned_governs` become
governed as they land." You are authorised to make exactly that change and
nothing else in that file. Do not restructure it, do not revise its prose beyond
the sentence named above, and do not change `status`, `date_accepted`,
`supersedes`, `closes_issues`, or `tracking_issue`.

## Coordination

- MUST work only on your assigned branch and worktree.
- MUST NOT use `pip install -e .`. `PYTHONPATH=./src` on every python call.
- **Do not open a pull request.** Commit, push your branch, and report.
- Edit only your checklist rows (`S2-G1` in §6 and §7.3).

## TODO And Deferral Rule

Use `TODO(#NNN): <reason>` citing an issue for anything deferred.

Known deferred items:

- `tests/explore/test_analysis_differential.py` and `tests/explore/fixtures/**`
  do not exist yet; agent `S2-D1` creates them. Leave them in
  `planned_governs`. A second short pass moves them once they land. This is
  sequencing, not deferral — do not write a TODO for it.

## Work To Do

1. Run `full_audit` first and read its actual findings. Work from what the tool
   says resolves, not from this prompt's summary of it:

   ```bash
   PYTHONPATH=./src python -m scistudio.qa.governance.gate_record check --only full_audit --base origin/main --head HEAD
   ```

   The findings land in `.audit/full-audit.json`.

2. Move every `planned_governs` entry that **now resolves** into `governs`, in
   both files, preserving the surrounding comments and the list ordering
   conventions the files already use. An entry that does not resolve stays where
   it is. Expect at least:
   - `docs/adr/ADR-054.md`: module `scistudio.explore`, file
     `src/scistudio/explore/**`. The contract `explore-panel-host-api` belongs to
     spec 1, which has not merged; **leave it in `planned_governs`.**
   - `docs/specs/adr-054-notebook-dependency-analysis.md`: the modules,
     contracts, and files that exist on this branch.

3. ADR-054's `governs.files` carries a comment explaining that the previewer,
   panel-loader, and lineage surfaces are governed by ADR-048 and ADR-051 and
   that governance moves with the addenda rather than being claimed there. That
   comment is still true and must survive. Do not claim surfaces this branch did
   not build.

4. `phase:` in ADR-054's front matter is `planning`. Decide whether the schema
   and the audits require it to become `implementation` now that the ADR governs
   real modules, and say in your report which way you went and why. If the
   audits do not require it, **leave it** and say so — do not change metadata on
   taste.

5. Revise the sentence in §11 that says the ADR "is in planning phase and
   governs no implementation yet; the surfaces in `planned_governs` become
   governed as they land" so that it is true after your change. Keep it to that
   sentence, in the document's existing register.

6. Re-run `full_audit` and confirm zero error-severity findings attributable to
   this branch. Informational findings from other ADRs are pre-existing; say how
   many there are and that they are unchanged.

## Required Tests And Checks

- `PYTHONPATH=./src python -m scistudio.qa.governance.gate_record check --mode local --base origin/track/adr-054-spec2-dependency-analysis --head HEAD`
- Record `--base-ref origin/track/adr-054-spec2-dependency-analysis` at `init`.
- Tests: N/A for a front-matter and one-sentence change. Record
  `--test-na "docs:front matter and one sentence of prose; the audits that read this metadata are the coverage, and full_audit runs in CI"`.
- Docs: this change **is** the docs change; record the two paths with
  `--docs-updated`.
- `git add -A` before every commit. Trailers: `Gate-Record:`,
  `Task-Kind: docs`, `Issue: #2231`, `Assisted-by: Claude:claude-opus-5`.

## Output Required

- Changed file paths and the exact front-matter diff.
- The `full_audit` finding count before and after, by severity.
- Your decision on `phase:` and the reason.
- Your branch head sha.
- Checklist rows updated.
- Anything that resolved which you deliberately did not move, and why.

## Stop Conditions

Stop and report back if:

- Moving an entry makes the audit fail a different way.
- The audit demands a change to a file outside your scope.
- The schema requires a front-matter change the ADR's own text contradicts.
- You believe the correct fix is to change the audit rather than the document.
```
