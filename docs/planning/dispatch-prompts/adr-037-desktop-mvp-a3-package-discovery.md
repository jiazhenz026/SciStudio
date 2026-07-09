---
title: "ADR-037 Desktop MVP A3 Package Discovery Dispatch"
status: Draft
owners: ["@jiazhenz026"]
related_adrs: [25, 37, 38, 43, 47]
language_source: en
---

[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity

- Repository: SciStudio
- Owner request: Build an MVP desktop distribution with hard-installed source
  packages.
- Task kind: feature
- Persona: implementer
- Issue: #1502
- Protected branch: main
- Desktop integration branch: desktop
- Agent branch: adr-037-mvp-a3-package-discovery
- Agent worktree: C:\Users\<user>\Desktop\workspace\SciStudio-desktop-a3
- Gate record: .workflow/records/1502-adr-037-desktop-mvp-manager.json
- Checklist: docs/planning/adr-037-desktop-mvp-checklist.md

## Scope

You own only:

- src/scistudio/blocks/registry/**
- tests/blocks/test_desktop_package_discovery.py

You must not touch:

- desktop/**
- src/scistudio/cli/main.py
- frontend/**
- scheduler internals

## Work To Do

1. Add package-source discovery for `packages/*/src` without changing the
   entry-point contract.
2. Discovery sources:
   - `SCISTUDIO_PLUGIN_PACKAGE_DIRS` paths;
   - `<desktop resources>/packages`;
   - source-checkout `desktop/packages`.
3. Preserve ADR-047 Path D split: helper code belongs in `_scan.py`; class API
   remains in `__init__.py`.
4. Add a test with a fake `scistudio-blocks-*` source package exposing
   `get_blocks()` or `get_block_package()`.

## Required Tests And Checks

- `$env:PYTHONPATH='src'; pytest tests/blocks/test_desktop_package_discovery.py --timeout=60`

## TODO And Deferral Rule

Use TODO(#1502) for full ADR-037 plugin system deferrals. Do not implement
PyPI search, per-plugin venvs, or uv installation.
