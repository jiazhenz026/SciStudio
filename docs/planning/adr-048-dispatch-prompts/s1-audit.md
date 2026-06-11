# Dispatch Prompt — S1-audit (ADR-048 SPEC 1 with-context audit)

[DISPATCH-TEMPLATE-V1: audit-with-context]

## Task Identity
- Repository: SciStudio · Persona: audit_reviewer · Audit mode: with-context
- Issue: #1574 — https://github.com/zjzcpj/SciStudio/issues/1574
- Owner request: Fully implement ADR-048 SPEC 1 (extensible preview system); verify completeness, scope, correctness, spec-conformance.
- Umbrella PR: #1577 `[DO NOT MERGE]` · Protected branch: main · Umbrella branch: track/adr-048-spec1-preview-system
- Audit branch: audit/adr-048-spec1 · Audit worktree: C:/Users/jiazh/Desktop/workspace/sci-wt/s1-audit (ALREADY CREATED by manager)
- Gate record: .workflow/records/1574-track-adr-048-spec1-preview-system.json
- Checklist: docs/planning/adr-048-implementation-checklist.md
- PRs/commits to audit: PR #1577 (merge commits f961170f backend, 6d57fb9c frontend, fb1489f1 imaging, + manager integration/CI-fix commits)
- Audit report path: docs/audit/2026-06-10-adr-048-spec1.md

## Required Reading
- The issue #1574 and owner instructions.
- `docs/adr/ADR-048.md`, `docs/specs/adr-048-preview-system.md` (the governing contract), `docs/planning/adr-048-implementation-checklist.md`.
- The integrated diff: `git -C <worktree> diff origin/main...HEAD` (or `git log --stat origin/main..HEAD`).
- AGENTS.md, docs/ai-developer/rules.md, docs/ai-developer/personas/audit-reviewer.md.
- The Codex auto-review comments on PR #1577 (via `gh pr view 1577 --comments` / `gh api`).

## Audit Goal
Verify the integrated SPEC 1 against the spec, code, tests, and CI. Report findings first, ordered by severity (P1 blocks/contract break · P2 should-fix · P3 improvement/follow-up).

## Scope — audit these claims/surfaces
- Spec conformance: routed `PreviewerRegistry`/`PreviewRouter` with the ADR-048 §3 9-tier precedence + priority tie-break + ambiguity error; `scistudio.previewers` entry point + monorepo fallback; project-local previewers + project default; bounded `PreviewDataAccess` (no full-array/Zarr materialization); 8 core fallback previewers incl. generic-only ArrayPreviewer (no image-domain LUT/OME in core) and PlotPreviewer (PNG/JPEG/SVG-sanitized/PDF); session API + legacy compat adapter preserving exact legacy `preview.kind` shapes; frontend PreviewHost + same-origin manifest ESM loading + fallback; imaging package-owned Image/Label previewers + core Array fallback when imaging absent (FR-026).
- Surfaces: `src/scistudio/previewers/**`, `src/scistudio/api/{routes/data.py,runtime/_data.py,runtime/__init__.py,schemas.py,app.py}`, `frontend/src/components/DataPreview*.{tsx,parts/**}`, `frontend/src/{lib/api/data.ts,store/previewSlice.ts,types/api.ts}`, `packages/scistudio-blocks-imaging/src/scistudio_blocks_imaging/previewers/**`, the tests, and the semantic-dup baseline re-ratchet (#1578) + the manifest-via-metadata.extra seam.
- Look specifically for: hidden V1/MVP reductions or unimplemented FRs (the owner forbade scope reduction); untracked TODOs; placeholder modules; any FR-001..FR-030 / SC-001..SC-010 not satisfied; the manifest-delivery seam (`metadata.extra["frontend_manifest"]`) — is it a sound contract or should it be a first-class envelope/session field? (record as a finding either way); whether SVG plot rendering is actually sanitized; whether bounded reads truly avoid materialization.

## Coordination
- Work only on `audit/adr-048-spec1` in your worktree. Do NOT use `pip install -e .`. Do NOT edit implementation code (read-only) — if a fix is needed, report it as a finding for the manager.
- Write the audit report to the repository file `docs/audit/2026-06-10-adr-048-spec1.md`, commit it (trailers below), and push the `audit/adr-048-spec1` branch so the manager can merge it into the umbrella PR evidence path.

## Checks to run/verify (read-only)
- Confirm the spec's FR/SC list against the code (cite file:line for each gap).
- Optionally run targeted tests with `SCISTUDIO_DEV=1 PYTHONPATH=<worktree>/src python -m pytest tests/previewers tests/api/test_previewers.py -q --no-cov` to confirm behavior.
- Read CI results for #1577 (`gh pr checks 1577`) and the Codex review; for each Codex comment, explicitly accept / defer (with tracked issue) / reject with reasoning in the report.

## Output Required
- Audit report path + commit/branch that contains it.
- Findings ordered by severity (P1/P2/P3) with file:line.
- Scope drift, missing tests/docs/FRs, if any.
- Codex review reconciliation (per-comment accept/defer/reject).
- CI status summary.
- Recommendation: pass / pass-with-fixes / block.

## Commit (report only)
```
docs(audit): ADR-048 SPEC 1 integrated audit report

Refs #1574
Gate-Record: .workflow/records/1574-track-adr-048-spec1-preview-system.json
Task-Kind: feature
Issue: #1574
Assisted-by: claude-code:claude-fable-5
```
Then `git push -u origin audit/adr-048-spec1`.

## Stop Conditions
Stop and report if you need to change implementation code, required evidence is unavailable, or the audit scope conflicts with the spec/gate record.
