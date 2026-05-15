# [DISPATCH-TEMPLATE-V1: audit] Phase 0.5 — Documentation audit (no-context)

> This is a **no-context audit agent**. Your prompt is intentionally minimal.
> You have **no access to the manager's session context, plan file, memory,
> the cascade checklist, or prior dispatch prompts**. Your inputs are limited
> to the file list below. This isolation is by design — it lets you spot
> inconsistencies that a context-aware reader would unconsciously paper over.

## Your task

Read ADR-038 (`docs/adr/ADR-038.md`) and ADR-039 (`docs/adr/ADR-039.md`) once, in full, to understand the architectural decisions the project just made. Then audit the project's documentation set listed below for:

1. **Internal inconsistencies** — places where two docs disagree about a behavior, schema, file location, or terminology.
2. **Residual references to deprecated concepts** — every mention of `metadata.db` should now be `<project>/.scieasy/lineage.db`, every `MetadataStore` should be the unified `LineageStore`, every `bump_revision` / `If-Match` flow should be gone, every `<project>/checkpoints/` should be `<project>/.scieasy/pause/`, the old flat `LineageRecord` schema with `input_hashes`/`output_hashes`/`batch_info` should be gone, the old "5 key packages" environment-snapshot default should be `uv pip freeze`. Find every leftover.
3. **Factual errors against the ADRs** — claims in the docs that contradict ADR-038 or ADR-039 (wrong schema field name, wrong path, wrong default value, wrong feature set).
4. **Missing cross-references** — pointers to ADR-032 (now superseded) that don't mention ADR-038, pointers to the old lineage layout that don't mention the new schema, etc.

You may NOT read:
- `docs/planning/` (cascade tracking; would expose session context)
- `docs/audit/` (prior audit reports; would bias you)
- `~/.claude/` (manager's plan / memory)
- `CLAUDE.md` (project rules — not relevant to a docs audit)
- the source code (you are auditing docs against ADRs, not docs against code)
- any sub-issue or umbrella issue threads on GitHub (would expose context)

You MAY read:
- `docs/adr/ADR-038.md` (the unified lineage decision)
- `docs/adr/ADR-039.md` (the git source control decision)
- `docs/architecture/ARCHITECTURE.md` (refactored architecture document)
- `docs/architecture/PROJECT_TREE.md` (refactored project tree)
- `docs/adr/ADR.md` (consolidated historical ADRs 001-030; modified for cross-refs)
- `docs/adr/ADR-031.md` through `ADR-037.md` (individual ADR files; some modified for cross-refs)
- `docs/block-development/architecture-for-block-devs.md` (developer doc; added "blocks alongside git" section)
- `docs/block-development/memory-safety.md` (developer doc)
- `docs/cli-integration.md` (developer doc; added "Git compatibility" section)
- `CHANGELOG.md` (only the `[Unreleased]` section's most recent `Changed` entry — for context on what the refactor PR changed)

## Output

Create the file `docs/audit/2026-05-15-adr-038-039-docs-audit.md` with the following structure:

```markdown
# Documentation audit — ADR-038 + ADR-039 Phase 0 refactor
Date: 2026-05-15
Auditor: <no-context audit agent>
Files reviewed: <list every file you actually opened>

## Summary
<one paragraph: pass / pass-with-fixes / block. Mention the number of P1/P2/P3 findings.>

## P1 findings (must fix before docs PR merges)
- **P1-1**: <one-line summary>
  - **File**: `<path>:<line range or section heading>`
  - **Issue**: <what's wrong>
  - **Evidence in ADR**: <quote the ADR section that contradicts it>
  - **Recommended fix**: <what to change to>
- **P1-2**: ...

## P2 findings (should fix; not release-blocking)
- **P2-1**: ...

## P3 findings (nits, polish, optional)
- **P3-1**: ...

## Cross-doc consistency check
<table or paragraph: are all docs internally consistent with each other? List any inter-doc divergence.>

## Terminology audit
<list every place the docs still say "metadata.db", "MetadataStore", "bump_revision", "If-Match", "<project>/checkpoints/", old "LineageRecord" schema names, "batch_info", "5 key packages" — even in justified historical / supersession contexts. Manager will classify each as legitimate or stale.>

## Out-of-scope findings (file via GitHub issue, not in this PR)
<list any other doc problems you spotted that are NOT caused by ADR-038/039. Examples: typos elsewhere, links pointing at deleted files, formatting drift, ADRs older than ADR-031 that have their own internal inconsistencies. These get filed as separate GitHub issues by the manager during Phase 0.75 — do NOT try to fix them in this audit.>
```

## Hard rules

1. **Do not write any code.** Output is exactly one new file: `docs/audit/2026-05-15-adr-038-039-docs-audit.md`. Nothing else.
2. **Do not edit any other file** — not the docs you are auditing, not the checklist (you don't even know the checklist exists), not the ADRs.
3. **Quote evidence**. For every finding, paste the offending snippet AND the ADR snippet that contradicts it. The manager needs to verify your audit without re-reading everything.
4. **Be exhaustive on terminology**. The point of this audit is to catch residual stale references before the docs PR merges. Grep-equivalent thoroughness expected — every "metadata.db" mention in every doc, every "bump_revision", every "If-Match", every "checkpoints/" with old meaning.
5. **No CI / no test runs.** This is a docs-only audit. You do not start the backend, you do not run pytest, you do not need Chrome MCP.
6. **No Codex reconciliation step** — this audit precedes any sub-issue PR.

## Output validation

Before reporting done, verify:
- File `docs/audit/2026-05-15-adr-038-039-docs-audit.md` exists
- File parses as the structure above (P1/P2/P3 sections + terminology audit + out-of-scope section)
- Every finding cites a file path AND quotes the offending text AND quotes the contradicting ADR text
- You did not modify any other file

## How to submit

Commit the audit file on a small branch `chore/audit-output-phase-0.5` off `docs/adr-038-039/architecture-refactor`. PR body: `Closes <docs-audit sub-issue #N>` (the manager will create the sub-issue and pass you the number). Title: `chore(docs-audit): Phase 0.5 ADR-038/039 documentation audit`.

After PR opens and CI runs, exit. The manager handles fix application in Phase 0.75.
