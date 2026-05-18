# Impl Record: Track D1 — Doc Skeletons (contributing/ + doc-guide/)

- **Track**: D1
- **Commit**: b168037c
- **Branch**: feat/phase-1-5-cleanup/1d-skeletons-contributing
- **Date**: 2026-05-18
- **Issue**: #1185
- **Plan ref**: `~/.claude/plans/polished-zooming-shell.md` Track D1

## Files created (18 new)

### docs/contributing/

| File | Frontmatter schema | Lines |
|---|---|---|
| index.md | WorkflowDocFrontmatter | 43 |
| onboarding.md | WorkflowDocFrontmatter | 38 |
| first-pr.md | WorkflowDocFrontmatter | 38 |
| configuring-your-agent.md | WorkflowDocFrontmatter | 39 |
| workflows/_template.md | WorkflowDocFrontmatter | 35 |
| workflows/new-feature.md | WorkflowDocFrontmatter | 38 |
| workflows/bug-fix.md | WorkflowDocFrontmatter | 38 |
| workflows/hotfix.md | WorkflowDocFrontmatter | 37 |
| workflows/file-adr-or-spec.md | WorkflowDocFrontmatter | 37 |
| workflows/testing.md | WorkflowDocFrontmatter | 39 |
| workflows/agent-dispatch.md | WorkflowDocFrontmatter | 39 |
| policy/ai-assistance.md | WorkflowDocFrontmatter | 38 |
| reference/gate-cli.md | WorkflowDocFrontmatter | 33 |
| reference/trailer-conventions.md | WorkflowDocFrontmatter | 31 |
| handbooks/README.md | WorkflowDocFrontmatter | 30 |

### docs/doc-guide/

| File | Frontmatter schema | Lines |
|---|---|---|
| how-to-write-a-doc.md | DocGuideFrontmatter | 47 |
| auto-vs-hand.md | DocGuideFrontmatter | 44 |
| ownership-and-review.md | DocGuideFrontmatter | 41 |

## Validation status

- `doc_length_lint`: **DEFERRED** — module is a Phase 1D deliverable
  (stub in `src/scieasy/qa/audit/doc_length_lint.py` raises
  `NotImplementedError`; not importable as CLI). All files are ≤80
  lines by visual inspection. Activation: when Track C ships the
  full implementations, re-run CI on umbrella.
- `frontmatter_lint`: **DEFERRED** — same reason as above.
- `auto_generated_lint`: **DEFERRED** — same reason. No file claims
  `generation: auto` (none of these files are auto-generated).
- `ruff format --check .`: **PASS** (no Python files added)
- `ruff check .`: **PASS** (no Python files added)

## STOP conditions triggered

- `doc_length_lint` / `frontmatter_lint` CLI tools not available →
  escalated via this impl record. Validation deferred to Track C
  merge per plan §STOP conditions.

## ADR-044 §9 scope note

§9.1 specifies exactly 3 files for `docs/doc-guide/`. All three are
shipped: `how-to-write-a-doc.md`, `auto-vs-hand.md`,
`ownership-and-review.md`.

## Out of scope

- `docs/user/**` — Track D2 scope
- `docs/prod-agent/**` — Track D2 scope
- `docs/contributing/reference/` files OTHER than gate-cli.md and
  trailer-conventions.md — not listed in ADR-044 §6.1
- `docs/contributing/handbooks/` files OTHER than README.md — ADR-044 §6.3 deferred
