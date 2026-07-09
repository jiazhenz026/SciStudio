---
title: "ADR-037 Desktop MVP A1 Desktop Shell Dispatch"
status: Draft
owners: ["@jiazhenz026"]
related_adrs: [37, 39, 42]
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
- Agent branch: adr-037-mvp-a1-desktop-shell
- Agent worktree: C:\Users\<user>\Desktop\workspace\SciStudio-desktop-a1
- Gate record: .workflow/records/1502-adr-037-desktop-mvp-manager.json
- Checklist: docs/planning/adr-037-desktop-mvp-checklist.md

## Required Rules

Read and follow AGENTS.md, docs/ai-developer/rules.md,
docs/ai-developer/specific_rules/agent-dispatch.md,
docs/ai-developer/specific_rules/gated-workflow.md,
docs/ai-developer/personas/implementer.md, and ADR-037.

## Scope

You own only:

- desktop/**

You must not touch:

- src/**
- frontend/src/**
- .github/**
- docs/adr/**

## Coordination

You are not alone in this codebase. Work only in your assigned worktree and
branch. Do not use `pip install -e .`. Do not revert other work.

## TODO And Deferral Rule

Deferred work must be tracked in the repo using TODO(#1502) and ADR-037
section references. Known deferrals: signing, auto-update, PyPI plugin browser,
per-plugin venvs, first-run installer UI.

## Work To Do

1. Add `desktop/package.json` for Electron MVP scripts.
2. Add `desktop/main.js` to spawn `scistudio gui --port 0 --bundled`, parse a
   JSON ready line, open a BrowserWindow, and terminate the child on quit.
3. Add `desktop/preload.js` only if needed for safe metadata exposure.
4. Add resource staging scripts under `desktop/scripts/` that copy
   `frontend/dist` and `src` into `desktop/resources/`.
5. Preserve existing `fetch-git-portable` scripts and resource layout.

## Required Tests And Checks

- `npm --prefix desktop install`
- `npm --prefix desktop run stage`
- `npm --prefix desktop run lint` if you add one; otherwise N/A with reason

## Output Required

Report changed paths, commands run, and checklist rows updated.
