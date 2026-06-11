# Dispatch Prompt — S3-docs (ADR-048 SPEC 3 developer docs rewrite)

[DISPATCH-TEMPLATE-V1: implementer]

## Task Identity
- Repository: SciStudio
- Owner request: Implement ADR-048 SPEC 3 in full (no v1 reductions) — delete-and-rewrite the active block/package developer docs from current contracts + a recent-ADR impact matrix, fix the scaffold templates, refresh AI skills + imaging README + cli-integration, and add the previewers-and-plots author guide.
- Task kind: docs · Persona: implementer
- Issue: #1576 — https://github.com/zjzcpj/SciStudio/issues/1576
- Umbrella PR: (SPEC 3, stacked on SPEC 2) — manager opens it; base = `track/adr-048-spec2-plot-tools`
- Protected branch: main · Umbrella branch: track/adr-048-spec3-docs
- Agent branch: feat/adr-048-docs · Agent worktree: C:/Users/jiazh/Desktop/workspace/sci-wt/s3-docs (ALREADY CREATED)
- Gate record (manager-owned): .workflow/records/1576-track-adr-048-spec3-docs.json
- Checklist: docs/planning/adr-048-implementation-checklist.md

## Setup
```bash
cd "C:/Users/jiazh/Desktop/workspace/sci-wt/s3-docs"
```
Your base branch already contains all of SPEC 1 + SPEC 2 (previewers + plot tools). Do NOT use `pip install -e .`. For any test run: `SCISTUDIO_DEV=1 PYTHONPATH="C:/Users/jiazh/Desktop/workspace/sci-wt/s3-docs/src" python -m pytest ...`.

## Required Rules
- AGENTS.md, docs/ai-developer/rules.md, docs/ai-developer/personas/implementer.md, docs/ai-developer/specific_rules/docs-change.md
- docs/adr/ADR-048.md (§10), docs/specs/adr-048-developer-docs-refresh.md (YOUR CONTRACT — FR-001..FR-031, SC-001..SC-011, the Documentation Inventory + recent-ADR review tables), docs/planning/adr-048-developer-docs-scope.md.

## Scope — you own ONLY
- `docs/block-development/**` (rewrite the 9 pages + add `previewers-and-plots.md` + examples)
- `docs/cli-integration.md`
- `packages/scistudio-blocks-imaging/README.md` (expand the package-owned previewer section)
- `src/scistudio/_skills/scistudio/scistudio-inspect-data/SKILL.md`, `scistudio-write-block/SKILL.md` (narrow xref only), `SKILL.md` (index, if needed) — `scistudio-write-plot/SKILL.md` already landed in SPEC 2 (do not rewrite it; you may cross-link).
- `src/scistudio/cli/templates/block_package/**` (fix stale executable docs)
- tests: `tests/cli/test_new_block_package.py`, `tests/api/test_blocks_template.py`, `tests/blocks/test_registry_package_layout.py`, `tests/integration/test_block_sdk_e2e.py`, `tests/packaging/test_wheel_skills.py`, `tests/agent_provisioning/test_skills.py`, `tests/cli/test_install.py`, and a NEW `tests/docs/test_block_development_docs.py` (stale-phrase + link checks)
- `docs/planning/adr-048-impact-matrix.md` (NEW — the recent-ADR impact matrix; or embed it in the rewrite per FR-029/FR-030)

## You MUST NOT touch (out of scope / protected)
- `docs/ai-developer/**` (governance surface — out of scope, do NOT edit; no governance_touch needed since you don't touch it).
- `src/scistudio/blocks/_templates/block_base_template.py` — PROTECTED (`blocks/**`). Do NOT edit it. FR-018 says "reviewed so generated block examples align with concrete-port guidance OR clearly mark generic ports as deliberate" — satisfy this in PROSE (document in the rewritten block-contract/quickstart that the standalone block template's empty `accepted_types` is a deliberate generic default, and tell authors to choose concrete types). If you believe it truly must be edited, STOP and report (needs owner core-change label).
- Historical ADRs/specs (do NOT delete/rewrite; `docs/specs/data-preview-3d-viewer.md` and any legacy preview-provider spec stay historical — at most a narrow supersession cross-reference).
- Any SPEC 1 / SPEC 2 source (`src/scistudio/previewers/**`, `ai/agent/mcp/tools_plot/**`, `frontend/**`, `api/**`) — read-only here. Generated docs/facts must stay generated (do NOT hand-edit; run the generator if needed).

## VERIFIED current-state facts (confirm against the code)
- `OutputPort` has NO `produced_type` field (`src/scistudio/blocks/base/ports.py`) — the scaffold `src/scistudio/cli/templates/block_package/blocks.py.tpl` emits `OutputPort(..., produced_type=None)` which is STALE/invalid → fix to `accepted_types=[...]`. Also reconcile `__init__.py.tpl` / `pyproject.toml.tpl` entry-point callable + return type (`get_blocks() -> list[type]` vs `get_block_package() -> tuple[PackageInfo, list[type]]`) so they are consistent and valid (mirror `packages/scistudio-blocks-imaging` which uses `get_block_package`).
- Three distinct package entry points exist: `scistudio.blocks`, `scistudio.types`, and the NEW `scistudio.previewers` (SPEC 1). Publishing/custom-types docs must teach all three as separate surfaces; previewers register display behavior, types register semantic data types.
- Plot jobs (SPEC 2) are PREVIEW-ONLY: never workflow blocks/DAG nodes/lineage; bound by workflow path + node id + output port, never block label; the `scistudio-write-plot` skill is the AI path.
- The 9 `docs/block-development/**` pages to delete-and-rewrite (per the spec's Documentation Inventory): `quickstart.md`, `block-contract.md`, `publishing.md`, `custom-types.md`, `testing.md`, `data-types.md`, `collection-guide.md`, `memory-safety.md`, `architecture-for-block-devs.md`; ADD `previewers-and-plots.md`.
- Recent-ADR impact matrix must cover ADR-036 → ADR-048 (+ ADR-042 addenda 1-6, ADR-046 addendum 1) per the spec table, classifying each item: package/block docs · AI skill/docs · implementation-only · not developer-facing. Rewritten docs must include every item classified as package/block/previewer/plot/IO/workflow-authoring/CodeBlock/registry/distribution/AI authoring guidance.

## Work To Do (implement docs/specs/adr-048-developer-docs-refresh.md IN FULL)
1. Build the recent-ADR impact matrix (`docs/planning/adr-048-impact-matrix.md`) covering ADR-036..048 + addenda, with the 4-way classification (FR-029/FR-030/SC-010/SC-011).
2. Delete-and-rewrite the 9 `docs/block-development/**` pages from current contracts (authoritative sources: `blocks/base/{block,ports,package_info}.py`, `blocks/registry/_scan.py`, `core/types/registry.py`, the scaffold templates + their tests, the SPEC 1 previewer contracts, the SPEC 2 plot contracts). Remove all `produced_type` guidance; teach concrete-port-by-default (empty `accepted_types` valid but deliberate); distinguish the 3 entry points; reflect CodeBlock v2 (ADR-041), IO capabilities (ADR-043), SubWorkflow (ADR-044), registry decomposition (ADR-047), etc. per the matrix.
3. Add `docs/block-development/previewers-and-plots.md` — the ADR-048 author guide: `PreviewerSpec`, `PreviewDataAccess`, backend provider + frontend manifest, same-origin asset loading, routing precedence, package/project previewers + project default + ambiguity; plot manifests (`plots/<id>/plot.yaml`), Python/R templates, target binding, preview cache, supported formats, validation/run, export/save, and the "plot jobs are preview-only, not workflow blocks" rule.
4. Fix `src/scistudio/cli/templates/block_package/**` (produced_type → accepted_types; entry-point/return-type consistency). Regenerate/relabel `docs/block-development/examples/**` from the current scaffold (or mark legacy with a tracked reason). Document the standalone block template's generic-port default in prose (do NOT edit the protected `block_base_template.py`).
5. Refresh `scistudio-inspect-data/SKILL.md` (current preview/`preview_data` behavior, no stale signatures); add a narrow previewers/plots cross-link in `scistudio-write-block/SKILL.md`. Ensure `docs/cli-integration.md` is consistent (SPEC 2 already added the plot skill/tools — verify counts). Expand `packages/scistudio-blocks-imaging/README.md` package-owned Image/Label previewer section.
6. Tests: update the template/registry/skill/install count tests as needed for the corrected templates; add `tests/docs/test_block_development_docs.py` asserting NO stale phrases (`produced_type=`, label-only plot binding, hardcoded-image-in-core, old `preview_data` arg examples) and that referenced ADR-048 spec/skill/README/template links resolve. Keep `tests/cli/test_new_block_package.py` + `tests/api/test_blocks_template.py` GREEN against the corrected templates (run them).
7. Any deferred docs item needs a tracked `TODO(#NNN)` / follow-up issue (not chat-only). Add a SPEC 3 CHANGELOG entry.

## Required checks (run from worktree; green) — SCISTUDIO_DEV=1 + PYTHONPATH
```bash
WT="C:/Users/jiazh/Desktop/workspace/sci-wt/s3-docs"
SCISTUDIO_DEV=1 PYTHONPATH="$WT/src" python -m pytest tests/cli/test_new_block_package.py tests/api/test_blocks_template.py tests/blocks/test_registry_package_layout.py tests/packaging/test_wheel_skills.py tests/agent_provisioning/test_skills.py tests/cli/test_install.py tests/docs/test_block_development_docs.py -q --no-cov -p no:cacheprovider
ruff check src/scistudio/cli/templates tests/docs/test_block_development_docs.py 2>/dev/null || true
python scripts/audit/generate_facts.py --check 2>&1 | tail -3   # if generated facts reference these docs
```
Also do a markdown self-check that every new ADR-048 link (specs/skills/READMEs/templates) resolves. Fix until green.

## Commit + deliver (NO PR, NO gate_record)
Commit with trailers:
```
docs(block-development): ADR-048 SPEC 3 — rewrite developer docs from current contracts

<body>

Refs #1576
Gate-Record: .workflow/records/1576-track-adr-048-spec3-docs.json
Task-Kind: docs
Issue: #1576
Assisted-by: claude-code:claude-fable-5
```
Then `git push -u origin feat/adr-048-docs`.

## Output Required
- Changed/created file paths (incl. the impact matrix + previewers-and-plots guide).
- A summary of the impact matrix classification + which rewritten pages cover which ADR items.
- Confirmation the scaffold template `produced_type` is removed + templates valid (test output).
- Test/lint outputs with pass counts; confirmation no stale phrases remain.
- Commit SHA + branch (confirm pushed). Any blocker/scope issue (esp. if `block_base_template.py` truly needs editing).

## Stop Conditions
Stop and report if: you need to edit a protected/out-of-scope file (`blocks/_templates/**`, `docs/ai-developer/**`, SPEC 1/2 source); a template fix would break `test_new_block_package`/`test_blocks_template` and you cannot reconcile; generated docs/facts would need hand-editing.
