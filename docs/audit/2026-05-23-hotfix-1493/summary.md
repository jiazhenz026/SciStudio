# ADR-042 full audit evidence — #1493 hotfix (2026-05-23)

Live owner-guided hotfix session per docs/ai-developer/specific_rules/hotfix.md. Frontend-only fixes for 7 GUI bugs surfaced after PR #1491 merge.

## Checks

- frontend lint (npx eslint src): pass — 0 errors, only pre-existing warnings on files outside hotfix scope.
- frontend typecheck (npx tsc --noEmit): pass.
- frontend tests (npx vitest run): pass — 62 files, 595 tests pass, 13 skipped (no new skips).
- sentrux scan / check_rules / health (MCP free-tier): pass — quality_signal=4547, 3/15 rules checked, 0 violations.

## Live Chrome MCP smoke

- Bug 1: PortInfoPanel now occupies basis-[38%] bottom slice with own scroll and single divider above (verified in Chrome MCP screenshot ss_62674l7hn).
- Bug 2: LoadData core_type Artifact → Series → Array refreshes the right-pane "OUTPUT PORT" type live (ss_7918sobu6).
- Bug 3: Code Block / Fiji variadic ports (port_1 Series input, port_2 Text output) appear in the right pane and stay synced after add (ss_897489g35, ss_0843irji7).
- Bug 4 + 5: Array → Series mismatch shows red dashed edge with "! type mismatch" label between Load and Fiji (zoomed screenshot).
- Bug 6: Drag Code Block output back to its own input → "Cannot connect a block to itself." banner, no edge created (ss_1075fkffj).
- Bug 7: Config-panel "+ Add output" mirrors into canvas + right pane immediately (ss_3430mnd0u).

## Out of scope

- Code Block panel re-layout to match Fiji's PortEditorTable — still tracked under #1324 per owner direction.
- Backend `validate_workflow` cycle check remains the authoritative gate at workflow save / run.

