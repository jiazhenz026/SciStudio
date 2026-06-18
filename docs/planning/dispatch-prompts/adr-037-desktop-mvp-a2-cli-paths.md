---
title: "ADR-037 Desktop MVP A2 CLI Paths Dispatch"
status: Draft
owners: ["@jiazhenz026"]
related_adrs: [37, 38, 39, 42]
language_source: en
---

[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Build an MVP desktop distribution on the desktop branch.
- Task kind: feature
- Persona: implementer
- Issue: #1502
- Protected branch: main
- Desktop integration branch: desktop
- Agent branch: adr-037-mvp-a2-cli-paths
- Agent worktree: C:\Users\jiazh\Desktop\workspace\SciStudio-desktop-a2
- Gate record: .workflow/records/1502-adr-037-desktop-mvp-manager.json
- Checklist: docs/planning/adr-037-desktop-mvp-checklist.md

## Scope

You own only:

- src/scistudio/cli/main.py
- src/scistudio/desktop/paths.py
- tests/cli/test_cli.py

You must not touch:

- desktop/**
- src/scistudio/blocks/registry/**
- frontend/**

## Work To Do

1. Add `scistudio.desktop.paths` with platformdirs-backed user/resource directory
   helpers and stdlib fallback.
2. Extend `scistudio gui` with `--bundled` and ephemeral port support.
3. Emit exactly one JSON ready line for Electron:
   `{"event":"scistudio.ready","host":"127.0.0.1","port":N,"url":"http://127.0.0.1:N"}`.
4. Preserve existing `scistudio gui` behavior when `--bundled` is absent.
5. Add/update CLI tests.

## Required Tests And Checks

- `$env:PYTHONPATH='src'; pytest tests/cli/test_cli.py --timeout=60`

## TODO And Deferral Rule

Use TODO(#1502) for deferred ADR-037 items. Do not implement first-run
installer UI.
