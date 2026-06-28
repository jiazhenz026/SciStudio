---
title: "Docstring Public API Surface — Filled Dispatch Prompts"
status: Approved
owners:
  - "@jiazhenz026"
related_adrs:
  - 52
language_source: en
---

# Docstring Public API Surface — Filled Dispatch Prompts

Evidence of the prompts dispatched for the #1845 docstring cleanup. Built from
`docs/ai-developer/templates/agent-dispatch-prompt-template.md` (implementer)
and `docs/ai-developer/templates/agent-dispatch-audit-no-context-prompt-template.md`
(audit). One shared body per role; per-agent parameters in the tables.

## Implementer agents — shared body

```markdown
[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity
- Repository: SciStudio
- Owner request: De-jargon + standardize docstrings of the pushed ADR-052 public API surface and document public attributes/properties so they render in the reference.
- Task kind: docs · Persona: implementer
- Issue: #1845 (focused slice of umbrella #1843)
- Umbrella PR: #1846 [DO NOT MERGE] · Protected branch: main
- Umbrella branch: manager/1845-docstring-public-api
- Agent branch: {{BRANCH}} · Agent worktree: {{WORKTREE}}
- Gate record (manager-owned, do not edit): .workflow/records/1845-docstring-public-api.json
- Convention (authoritative): docs/contributing/docstring-style.md

## Required Reading
- docs/contributing/docstring-style.md  (the standard you apply)
- AGENTS.md · docs/ai-developer/personas/implementer.md
- GitHub issue #1845 and umbrella #1843 (context only)

## Scope — you own ONLY
{{WRITE_SET}}
Out of scope (stop and report if you need these):
- every other path, docs/user/reference/** (generated), tests, the gate ledger,
  the checklist, any other module.

## Work To Do
1. Enumerate the PUBLIC symbols of your module: names in each subpackage's
   `__all__`, plus non-underscore `@stable`/`@provisional` classes/functions.
   Skip `_`-prefixed and `internal`-tier members.
2. For every public class / function / block, rewrite the docstring to the
   convention shape: one-line summary; plain-language purpose (write for a
   bench scientist who is not a fluent coder); contract (Google `Args`/
   `Returns`/`Yields`/`Raises`; for blocks also ports + config in prose); and a
   short runnable `Example:` where it helps.
3. Remove internal record citations from docstring PROSE — ADR-NNN, FR-NNN,
   BUG-NNN, TRK-NNN, DSN-NNN, SC-NNN, OQ/ECA/OBS/BCP/AC-NNN, "Addendum N",
   decision suffixes (e.g. "ADR-027 D7", "ADR-020-Add5"), and bare #issue
   numbers. KEEP the behavior they described. KEEP external standards (UTF-8,
   ISO-8601, RFC 3339, SHA-256, ruff codes, MIME types) and KEEP Sphinx roles
   (:class:`X`, :meth:`X`, ...). A citation may move to a `#` maintainer comment.
   Also reword internal taxonomy labels ("Tier 1/2/3") into plain descriptions.
4. Document EVERY public attribute/property of your public classes with an
   attribute docstring (string literal on the line after the assignment) so it
   renders in the generated reference — e.g. block `ui_icon`/`ui_color`, config
   `ClassVar`s, public properties. A `#` comment is NOT enough. Verified
   mechanism — see docstring-style.md §2.3.

## Hard Constraints
- DOCSTRINGS AND COMMENTS ONLY. No signature, behavior, import, or logic change.
- Work ONLY in {{WORKTREE}} on branch {{BRANCH}} (absolute paths). You are not
  alone in the repo; do not touch other modules or revert others' work.
- Do NOT run any `gate_record` command (manager owns the single ledger).
- Do NOT open a PR and do NOT `git push`. Commit locally on your branch only.

## Validate before committing
- `PYTHONPATH=$PWD/src python -c "import <your top module>"` imports clean.
- `python -m py_compile` (or import) on every changed file — no syntax error
  from a malformed/unterminated docstring.
- `ruff check <changed files>` and `ruff format <changed files>` — fix any new
  lint (watch docstring line length); changes must stay docstring/comment-only.

## Commit (on your branch, no push)
Message must carry these trailers:
    Gate-Record: .workflow/records/1845-docstring-public-api.json
    Task-Kind: docs
    Issue: #1845
    Assisted-by: claude-code:claude-opus-4-8

## Output Required (report back)
- Changed file paths · count of symbols + attributes documented.
- Validation commands run and results.
- Commit SHA on {{BRANCH}}.
- Any internal citation you were unsure whether to keep, and why.
- Any blocker / out-of-scope need.
```

### Implementer per-agent parameters

| Agent | {{BRANCH}} | {{WORKTREE}} | {{WRITE_SET}} |
|---|---|---|---|
| core-types | docs/1845-core-types | /Users/jiazhenz/scistudio-wt-1845-core-types | `src/scistudio/core/types/**` |
| core-infra | docs/1845-core-infra | /Users/jiazhenz/scistudio-wt-1845-core-infra | `src/scistudio/core/storage/**`, `core/lineage/**`, `core/versioning/**`, `core/meta/**` |
| blocks-base | docs/1845-blocks-base | /Users/jiazhenz/scistudio-wt-1845-blocks-base | `src/scistudio/blocks/base/**` |
| blocks-process | docs/1845-blocks-process | /Users/jiazhenz/scistudio-wt-1845-blocks-process | `src/scistudio/blocks/process/**` |
| blocks-io | docs/1845-blocks-io | /Users/jiazhenz/scistudio-wt-1845-blocks-io | `src/scistudio/blocks/io/**` |
| blocks-appsub | docs/1845-blocks-appsub | /Users/jiazhenz/scistudio-wt-1845-blocks-appsub | `src/scistudio/blocks/app/**`, `blocks/subworkflow/**` |
| blocks-code | docs/1845-blocks-code | /Users/jiazhenz/scistudio-wt-1845-blocks-code | `src/scistudio/blocks/code/**` |
| blocks-ai | docs/1845-blocks-ai | /Users/jiazhenz/scistudio-wt-1845-blocks-ai | `src/scistudio/blocks/ai/**` |
| blocks-registry | docs/1845-blocks-registry | /Users/jiazhenz/scistudio-wt-1845-blocks-registry | `src/scistudio/blocks/registry/**` |
| plot | docs/1845-plot | /Users/jiazhenz/scistudio-wt-1845-plot | `src/scistudio/plot/**` |
| previewers | docs/1845-previewers | /Users/jiazhenz/scistudio-wt-1845-previewers | `src/scistudio/previewers/**` |

## Audit agents — no-context

Built from the audit-no-context template. Each audit reads only repository
docs/code/tests it discovers, plus `docs/contributing/docstring-style.md` as the
standard, and writes a report. Audit surfaces:

| Agent | Audit branch | Worktree | Allowed surfaces | Report |
|---|---|---|---|---|
| audit-1 | audit/1845-1 | /Users/jiazhenz/scistudio-wt-1845-audit1 | `src/scistudio/blocks/**` public docstrings + the convention | docs/audit/2026-06-28-docstring-public-api-no-context-1.md |
| audit-2 | audit/1845-2 | /Users/jiazhenz/scistudio-wt-1845-audit2 | `src/scistudio/core/**` + `src/scistudio/plot/**` public docstrings + the convention | docs/audit/2026-06-28-docstring-public-api-no-context-2.md |
| audit-3 | audit/1845-3 | /Users/jiazhenz/scistudio-wt-1845-audit3 | `src/scistudio/previewers/**` public docstrings + cross-module consistency + generated reference | docs/audit/2026-06-28-docstring-public-api-no-context-3.md |
