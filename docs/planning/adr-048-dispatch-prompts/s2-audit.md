# Dispatch Prompt — S2-audit (ADR-048 SPEC 2 with-context audit)

[DISPATCH-TEMPLATE-V1: audit-with-context]

## Task Identity
- Repository: SciStudio · Persona: audit_reviewer · Audit mode: with-context
- Issue: #1575 — https://github.com/zjzcpj/SciStudio/issues/1575
- Owner request: Fully implement ADR-048 SPEC 2 (AI plot tools + preview-side plot jobs); verify completeness/scope/correctness/spec-conformance, no v1 reductions.
- Umbrella PR: #1580 `[DO NOT MERGE]` (stacked on SPEC 1) · Umbrella branch: track/adr-048-spec2-plot-tools
- Audit branch: audit/adr-048-spec2 · Audit worktree: C:/Users/<user>/Desktop/workspace/sci-wt/s2-audit (ALREADY CREATED)
- Gate record: .workflow/records/1575-track-adr-048-spec2-plot-tools.json
- Audit report path: docs/audit/2026-06-10-adr-048-spec2.md

## Required Reading
- Issue #1575; `docs/adr/ADR-048.md` (§5, §9); `docs/specs/adr-048-ai-plot-tools.md` (the contract — FR-001..FR-035, SC-001..SC-010); `docs/planning/adr-048-implementation-checklist.md`.
- The SPEC 2 diff: `git -C <worktree> diff origin/track/adr-048-spec1-preview-system...HEAD` (SPEC 2 changes only, base = SPEC 1).
- AGENTS.md, docs/ai-developer/rules.md, docs/ai-developer/personas/audit-reviewer.md.
- Codex auto-review on PR #1580 (`gh pr view 1580 --comments`).

## Setup
- Read-only on implementation; you only WRITE `docs/audit/2026-06-10-adr-048-spec2.md`. Do NOT `pip install -e .`.
- For python checks: `SCISTUDIO_DEV=1 PYTHONPATH="C:/Users/<user>/Desktop/workspace/sci-wt/s2-audit/src" python -m pytest ... -m "not requires_r"`. (The sci-stack pandas/tifffile/matplotlib may be absent in this minimal venv → those tests skip locally; note it. CI installs them via [dev].)

## Audit Goal & Scope
Independently verify SPEC 2 against the spec. Owner FORBADE scope reduction — hunt for hidden V1/MVP cuts, unimplemented FRs, placeholder modules, untracked TODOs, contract gaps. Specifically check:
- All 6 MCP tools exist with `category:plot`, correct read/write tags, `next_step` on write/run; tool count 27→33; the `scistudio-write-plot` skill + provisioning + CLI install + count tests (12→14 skills, `_TASK_SKILLS`).
- `plot.yaml` strict schema + Python/R templates match the spec; `scaffold_plot` rejects label-only selection; `validate_plot` covers schema/path-confinement/target/format/language/entrypoint/runner; `run_plot_job` enforces timeout/output-size/file-count caps + sanitized errors.
- Preview-side runtime writes `.scistudio/previews/<workflow_id>/<node_id>/<output_port>/<plot_id>/current.*` + `current.json` (current-overwrite, failure-state recorded); reuses the CodeBlock runner by IMPORT ONLY (no `blocks/**` edits — verify `git diff` touches no protected path); plot jobs mutate NO workflow YAML / scheduler / lineage / downstream (verify the test asserts this); artifacts consumable by SPEC 1 `core.plot.basic`.
- Path confinement (`_resolve_project_path`) on all path args; target binding by workflow path + node id + output port (never label).
- R: validate-always + run skip-if-unavailable (`requires_r`).
- The matplotlib `[dev]` governance_touch — is it justified/minimal? (record a finding either way.)

Reconcile each Codex comment on #1580 (accept / defer-with-issue / reject + reasoning). Read `gh pr checks 1580` (CI is green).

## Output Required
- Audit report path + commit/branch (push `audit/adr-048-spec2`).
- Findings by severity (P1/P2/P3) with file:line.
- Scope drift / missing FRs / missing tests, if any.
- Codex reconciliation; CI status; recommendation (pass / pass-with-fixes / block); any P1 to fix before owner-merge.

## Commit (report only) + push
```
docs(audit): ADR-048 SPEC 2 integrated audit report

Refs #1575
Gate-Record: .workflow/records/1575-track-adr-048-spec2-plot-tools.json
Task-Kind: feature
Issue: #1575
Assisted-by: claude-code:claude-fable-5
```
Then `git push -u origin audit/adr-048-spec2`.

## Stop Conditions
Stop and report if you must change implementation code, evidence is unavailable, or the audit scope conflicts with the spec/gate record.
