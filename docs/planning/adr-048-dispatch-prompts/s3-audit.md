# Dispatch Prompt — S3-audit (ADR-048 SPEC 3 with-context audit)

[DISPATCH-TEMPLATE-V1: audit-with-context]

## Task Identity
- Repository: SciStudio · Persona: audit_reviewer · Audit mode: with-context
- Issue: #1576 · Owner request: Fully implement ADR-048 SPEC 3 (developer docs delete-and-rewrite), no v1 reductions.
- Umbrella PR: #1581 `[DO NOT MERGE]` (stacked on SPEC 2) · Umbrella branch: track/adr-048-spec3-docs
- Audit branch: audit/adr-048-spec3 · Audit worktree: C:/Users/<user>/Desktop/workspace/sci-wt/s3-audit (ALREADY CREATED)
- Gate record: .workflow/records/1576-track-adr-048-spec3-docs.json
- Audit report path: docs/audit/2026-06-10-adr-048-spec3.md

## Required Reading
- Issue #1576; `docs/specs/adr-048-developer-docs-refresh.md` (contract — FR-001..FR-031, SC-001..SC-011, Documentation Inventory + recent-ADR review tables); ADR-048 §10; the checklist.
- The SPEC 3 diff: `git -C <worktree> diff origin/track/adr-048-spec2-plot-tools...HEAD`.
- AGENTS.md, docs/ai-developer/rules.md, docs/ai-developer/personas/audit-reviewer.md. Codex review on PR #1581.

## Setup
Read-only on the repo; you WRITE only `docs/audit/2026-06-10-adr-048-spec3.md`. Do NOT `pip install -e .`. For checks: `SCISTUDIO_DEV=1 PYTHONPATH="C:/Users/<user>/Desktop/workspace/sci-wt/s3-audit/src" python -m pytest ...`.

## Audit Goal & Scope
Independently verify SPEC 3 against the spec. Owner FORBADE scope reduction. Verify specifically:
- The recent-ADR impact matrix (`docs/planning/adr-048-impact-matrix.md`) covers ADR-036..048 + ADR-042 add 1-6 + ADR-046 add 1, with the 4-way classification (SC-010/SC-011), and every package/block/AI-authoring item is represented in the rewritten docs.
- All 9 `docs/block-development/**` pages were rewritten from current contracts (not patched): quickstart, block-contract, publishing, custom-types, testing, data-types, collection-guide, memory-safety, architecture-for-block-devs; `previewers-and-plots.md` exists and covers `PreviewerSpec`/`PreviewDataAccess`/manifests/routing/project previewers + plot manifests/templates/cache/preview-only.
- NO stale `OutputPort.produced_type` guidance remains (SC-001); concrete-port-by-default (SC-002); `scistudio.blocks`/`types`/`previewers` taught as 3 entry points (SC-003); the scaffold `blocks.py.tpl` is fixed + valid; `test_block_development_docs.py` actually enforces stale-phrase + link checks.
- Skills (`scistudio-inspect-data` no stale `preview_data`; `scistudio-write-block` xref) + imaging README previewer section + cli-integration consistency.
- Historical ADRs/specs NOT deleted; `block_base_template.py` (protected) NOT edited (its generic-port default documented in prose); generated docs/facts not hand-edited; any deferral tracked.
- Check the residual `get_block_package()`/`produced_type` mentions the S3-docs agent flagged in publishing.md + impact-matrix are legitimately framed as "legacy also-accepted / removed-pattern" documentation, not active stale guidance.

Reconcile each Codex comment on #1581. Note `gh pr checks 1581`.

## Output Required
- Audit report path + commit/branch (push `audit/adr-048-spec3`).
- Findings by severity (P1/P2/P3 + file:line); scope drift / missing FRs; Codex reconciliation; CI status; recommendation; any P1 to fix before owner-merge.

## Commit (report only) + push
```
docs(audit): ADR-048 SPEC 3 developer-docs audit report

Refs #1576
Gate-Record: .workflow/records/1576-track-adr-048-spec3-docs.json
Task-Kind: docs
Issue: #1576
Assisted-by: claude-code:claude-fable-5
```
Then `git push -u origin audit/adr-048-spec3`.

## Stop Conditions
Stop and report if you must change implementation/docs code, evidence is unavailable, or the audit scope conflicts with the spec/gate record.
