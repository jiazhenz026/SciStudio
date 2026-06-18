---
title: "ADR-048 PR1577 Packaging And E2E Dispatch"
status: Draft
owners:
  - "@jiazhenz026"
related_adrs:
  - 48
language_source: en
---

# ADR-048 PR1577 Packaging And E2E Dispatch

Persona: `test_engineer`
Task kind: `bugfix`
Issue: #1644
Base: PR #1577 head (`track/adr-048-spec1-preview-system`)

## Task

Fix or verify the owner-reported packaging bug: installed packages such as
`scistudio-blocks-imaging` need a `[project.entry-points."scistudio.previewers"]`
group. Monorepo dev fallback can hide this, but installed deployment should
discover package previewers through entry points.

Also produce committed ADR-048 viewer e2e scenario/evidence for final PR head.

## Write Set

- `packages/scistudio-blocks-imaging/pyproject.toml`
- `pyproject.toml` only if the root package must declare its own previewers.
- `packages/scistudio-blocks-imaging/tests/test_previewer_registration.py`
- `tests/previewers/**`
- `docs/ai-developer/e2e/**`
- `docs/planning/adr-048-pr1577-fix-checklist.md`

## Out Of Scope

- Plot MCP internals.
- MCP inspection no-compat cleanup.
- Broad packaging refactor unrelated to previewer discovery.

## Required Result

- Add/update tests that would fail when the installed entry point group is
  missing.
- Add the entry point group in the correct package metadata.
- Add an e2e scenario or evidence file covering each ADR-048 viewer category:
  DataFrame, Array, Series, Text, Artifact, CompositeData, Collection,
  Image/Label package previewers, and Plot.
- Report changed paths and exact test commands run.
