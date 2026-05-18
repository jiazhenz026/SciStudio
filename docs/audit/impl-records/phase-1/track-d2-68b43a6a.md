# Impl record: Track D2 — user/ + prod-agent/ doc-set skeletons

- **Issue**: #1186
- **Branch**: `feat/phase-1-5-cleanup/1d-skeletons-user-prod`
- **Commit**: `68b43a6a`
- **Date**: 2026-05-18
- **Author**: @claude (Claude Sonnet 4.6)
- **PR target**: `consolidate/phase-1-preview`

## Summary

Phase 1.5 pre-checkpoint cleanup Track D2 (TC-1D.8 slice 2).
Creates 23 new files under `docs/user/` and `docs/prod-agent/`
per ADR-044 §7 + §8.

## Files created

### Hand-authored user docs (UserDocFrontmatter + 7-section body)

- `docs/user/index.md` — routing hub with cross-links to install/quickstart/user-guide
- `docs/user/install.md` — installation guide skeleton
- `docs/user/quickstart.md` — first workflow in 5 minutes skeleton
- `docs/user/plugin-authoring.md` — plugin authoring guide skeleton
- `docs/user/glossary.md` — sklearn-style glossary skeleton
- `docs/user/faq.md` — FAQ skeleton
- `docs/user/prod-env-artifacts.md` — explains CLAUDE.md/AGENTS.md/.claude/.codex artifacts

### User-guide concept pages

- `docs/user/user-guide/workflow-graph.md`
- `docs/user/user-guide/blocks-and-contracts.md`
- `docs/user/user-guide/data-objects.md`
- `docs/user/user-guide/execution-model.md`
- `docs/user/user-guide/code-runners.md`
- `docs/user/user-guide/ai-blocks.md`

### Tutorial stubs (sphinx-gallery exempt per ADR-044 §7.2)

- `docs/user/tutorials/01-first-workflow/README.md`
- `docs/user/tutorials/02-using-r-runner/README.md`

### Reference directory holders

- `docs/user/reference/api/.gitkeep`
- `docs/user/reference/blocks/.gitkeep`
- `docs/user/reference/schemas/.gitkeep`

### Generated-marker stubs (generation: auto + source: AutoGenSource)

- `docs/user/reference/cli.md` — `scieasy.qa.docs.generators.cli_reference.generate`
- `docs/user/reference/server-api.md` — `scieasy.qa.docs.generators.openapi_reference.generate`
- `docs/user/reference/entry-points.md` — `scieasy.qa.docs.generators.entry_point_catalog.generate`

### llms.txt placeholder

- `docs/user/llms.txt` — populated by `scieasy.qa.docs.generators.llms_txt.generate` at build time

### prod-agent (ProdAgentDocFrontmatter + ADR-044 §8.2 mandatory sections)

- `docs/prod-agent/README.md` — What this is / What it produces / Known issues / Upgrade flow / How to extend

## Lint results

```
doc_length_lint: 0 findings (PASS)
frontmatter_lint: 0 findings (PASS)
auto_generated_lint: 3 INFO findings (PASS — no-baseline for 3 new
  generated stubs; expected first-run case per auto_generated_lint.py
  algorithm: "missing entries surface as INFO findings (no false positives
  during the first audit cycle)")
ruff format --check: PASS (701 files already formatted)
ruff check: PASS (All checks passed)
```

## Deviations from dispatch

None. All files created as specified. `generation: auto` used (not
`generation: auto-from-code`) per actual linter code — `auto_generated_lint.py`
checks `frontmatter.get("generation") != "auto"`, and `UserDocFrontmatter`
schema enumerates `auto`/`hand`/`hybrid` (not `auto-from-code`).
