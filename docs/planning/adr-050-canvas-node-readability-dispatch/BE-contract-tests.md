[DISPATCH-TEMPLATE-V1: test_engineer]

## Task Identity
- Repository: SciStudio
- Owner request: Verify and strengthen the package→registry→API block-schema contracts that feed the new canvas square node + BottomPanel config, WITHOUT changing package or backend production code.
- Task kind: feature
- Persona: test_engineer
- Issue: #1698 — https://github.com/zjzcpj/SciStudio/issues/1698
- Umbrella PR: pending `[DO NOT MERGE]`
- Protected branch: main
- Umbrella branch: feat/1698-canvas-node-readability
- Agent branch: feat/1698-be-contract-tests
- Agent worktree: /Users/jiazhenz/SciStudio/.worktrees/feat-1698-be-contract-tests
- Gate record: .workflow/records/1698-canvas-node-readability.json
- Checklist: docs/planning/adr-050-canvas-node-readability-checklist.md
- Governing docs: docs/adr/ADR-050.md, docs/specs/adr-050-canvas-node-readability.md

## Required Rules
Read and follow: the issue #1698; AGENTS.md; docs/ai-developer/rules.md; docs/ai-developer/personas/test-engineer.md; docs/ai-developer/specific_rules/test-engineering.md; docs/specs/adr-050-canvas-node-readability.md (esp. FR-027..FR-033, SC-010..SC-012).

## Scope — you own ONLY (test files):
- tests/api/test_blocks.py
- tests/blocks/test_registry.py
- tests/blocks/test_dynamic_ports.py
- tests/blocks/test_registry_package_layout.py
- tests/packaging/test_adr043_package_capabilities.py

Production code is OUT OF SCOPE for editing (test_engineer default). You may READ any src/** and packages/** to understand contracts, but you must NOT edit src/**, packages/**, or any frontend/**. If a test reveals a real production gap, STOP and report it to the manager (do NOT fix it yourself — manager will amend scope).

## Work To Do (ADR-050 §5, spec FR-027..FR-033)
1. Verify + strengthen contract tests proving `BlockSpec`, `BlockSummary`, and `BlockSchemaResponse` still expose, for both core and package-provided blocks: `base_category`/`subcategory`, input/output ports, `dynamic_ports`, variadic flags + min/max port limits + allowed variadic types, `format_capabilities`, and `config_schema` metadata including `ui_priority` and `ui_widget` (SC-010, FR-027/FR-029/FR-030).
2. Add/confirm assertions that representative package-provided blocks from imaging, spectroscopy, LCMS, and SRS resolve through the registry/API with that metadata intact (SC-011, FR-033) — these are the blocks the square node + BottomPanel must render without package source edits.
3. Confirm NO package-facing schema field is removed (this PR does not change schemas). Tests should fail loudly if a future change drops category/port/dynamic-port/variadic/config-schema/capability metadata (SC-012, FR-031/FR-032).
4. Keep these tests green against current `src/**` (no production change is expected). If green requires a production change, that is a finding → STOP and report.

## Coordination
You are not alone. Work ONLY in your worktree/branch. Do NOT `pip install -e .` (use `PYTHONPATH=src`). Do not edit production or frontend code. Commit to your branch with AI trailers; do NOT open a PR; do NOT merge.

## TODO And Deferral Rule
`TODO(#1698): <reason>` for any deferral; report production gaps rather than working around them.

## Required Tests And Checks (run in your worktree)
- `PYTHONPATH=src pytest tests/api/test_blocks.py tests/blocks/test_registry.py tests/blocks/test_dynamic_ports.py tests/blocks/test_registry_package_layout.py tests/packaging/test_adr043_package_capabilities.py -q`
- Commit on `feat/1698-be-contract-tests` with trailers `Gate-Record: .workflow/records/1698-canvas-node-readability.json`, `Task-Kind: feature`, `Issue: #1698`, `Assisted-by: claude-code:opus-4.8`.

## Output Required
Report: changed/created test paths; full pytest result (counts); which imaging/spectroscopy/LCMS/SRS blocks you exercised; any production gap finding (with file+line); final commit SHA.

## Stop Conditions
Stop and report if: a contract test can only pass by editing production code; a required package is not importable under PYTHONPATH=src; you cannot add/update required tests.
