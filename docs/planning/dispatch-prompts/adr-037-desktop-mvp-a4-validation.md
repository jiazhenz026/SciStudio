---
title: "ADR-037 Desktop MVP A4 Validation Dispatch"
status: Draft
owners: ["@jiazhenz026"]
related_adrs: [37, 39, 42]
language_source: en
---

[DISPATCH-TEMPLATE-V1: test_engineer]

## Task Identity

- Repository: SciStudio
- Owner request: Build an MVP desktop distribution on the desktop branch.
- Task kind: feature
- Persona: test_engineer
- Issue: #1502
- Protected branch: main
- Desktop integration branch: desktop
- Agent branch: adr-037-mvp-a4-validation
- Agent worktree: C:\Users\jiazh\Desktop\workspace\SciStudio-desktop-a4
- Gate record: .workflow/records/1502-adr-037-desktop-mvp-manager.json
- Checklist: docs/planning/adr-037-desktop-mvp-checklist.md

## Scope

You own only:

- tests/packaging/**
- desktop/scripts/** validation helpers if needed
- docs/planning/adr-037-desktop-mvp-checklist.md rows for A4 only

Production code is out of scope unless the manager explicitly amends scope.

## Work To Do

1. Add low-cost tests or validation scripts that check desktop resources and
   package metadata without launching a full installer.
2. Run `npm --prefix frontend run build` and `npm --prefix desktop run stage`
   if desktop scaffold exists.
3. Record exact commands and failures in your checklist row.

## Required Tests And Checks

- `npm --prefix frontend run build`
- `npm --prefix desktop run stage`
- `$env:PYTHONPATH='src'; pytest tests/packaging --timeout=60` if you add tests

## TODO And Deferral Rule

Use TODO(#1502) for unimplemented release-matrix checks.
